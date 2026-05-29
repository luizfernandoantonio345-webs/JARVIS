import requests
import time
import logging
import json
import httpx
import asyncio
from typing import List, Dict, Generator, Callable, Awaitable
from requests import RequestException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from backend.config import get_config

# Circuit breaker — if Ollama failed recently, skip and fail fast
_CIRCUIT_OPEN = False
_CIRCUIT_OPEN_AT: float = 0.0
_CIRCUIT_COOLDOWN = 30.0  # seconds before retrying after failure

logger = logging.getLogger(__name__)

# Compact system prompt for local/CPU inference — keeps token count minimal
_LOCAL_SYSTEM_PROMPT = (
    "Você é JARVIS, assistente pessoal do Senhor. "
    "Responda em português, seja conciso e direto. "
    "Chame o usuário de 'Senhor'. Máximo 3 frases por resposta."
)
_LOCAL_PROMPT_THRESHOLD = 400  # chars; replace any system message longer than this

FALLBACK_MODEL = "tinyllama"

def _build_session(pool_connections: int = 6, pool_maxsize: int = 6) -> requests.Session:
    session = requests.Session()
    # urllib3-level retry only for connection/transient errors (not read timeouts)
    retry = Retry(
        total=0,  # handled at application level
        connect=2,
        read=0,
        backoff_factor=0.5,
        status_forcelist=[502, 503, 504],
        allowed_methods=["POST", "GET"],
    )
    adapter = HTTPAdapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        max_retries=retry,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class JarvisAIClient:
    def __init__(self):
        cfg = get_config()
        # Usar 127.0.0.1 em vez de localhost para evitar duplo-timeout IPv6/IPv4 no Windows
        self.ollama_url = cfg.ollama_url.replace("localhost", "127.0.0.1")
        self.model = self._normalize_model(cfg.model)
        self.embedding_model = cfg.embedding_model
        self.timeout = cfg.timeout
        self.max_retries = cfg.max_retries
        # Ollama builds can differ: some setups reject /api/chat with 404.
        # After first 404, prefer /api/generate directly to avoid repeated failures.
        self._chat_supported: bool = True
        connect_timeout = 3
        # Ollama pode demorar no primeiro token durante cold start do modelo.
        # Aumentado para 120s para tolerar modelos pequenos em hardware limitado (Qwen 0.5B pode levar 40-50s no primeira vez)
        per_attempt_read_timeout = max(120, self.timeout)
        self.request_timeout = (connect_timeout, per_attempt_read_timeout)
        self.health_timeout = (3, 5)
        self._session = _build_session(pool_connections=6, pool_maxsize=6)

    @staticmethod
    def _normalize_model(model: str) -> str:
        # No normalization — use model as specified in config
        # phi:latest is lightweight (~260MB) and preferred for resource-constrained systems
        return model

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = min(2 ** attempt, 8)
        time.sleep(delay)

    def _log_request_exception(self, endpoint: str, exc: Exception) -> None:
        logger.warning("Ollama request to %s failed: %s", endpoint, exc)

    def _offline_message(self) -> str:
        return (
            f"JARVIS offline - Ollama nao responde em {self.ollama_url}. "
            "Verifique se o servico esta rodando e se JARVIS_OLLAMA_URL esta correto."
        )

    @staticmethod
    def _compress_for_local(messages: List[Dict]) -> List[Dict]:
        """Replace oversized system messages with the compact local prompt."""
        result = []
        persona_injected = False
        for msg in messages:
            if msg.get("role") == "system" and len(msg.get("content", "")) > _LOCAL_PROMPT_THRESHOLD:
                if not persona_injected:
                    result.append({"role": "system", "content": _LOCAL_SYSTEM_PROMPT})
                    persona_injected = True
                # drop the long system message
            else:
                result.append(msg)
        return result

    def _collect_stream(self, response: requests.Response, content_key: str) -> str | None:
        parts: list[str] = []
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            if content_key == "message":
                content = data.get("message", {}).get("content", "")
            else:
                content = data.get(content_key, "")

            if content:
                parts.append(content)

            if data.get("done"):
                break

        combined = "".join(parts).strip()
        return combined or None

    @staticmethod
    def _messages_to_prompt(messages: List[Dict]) -> str:
        parts: list[str] = []
        for message in messages:
            role = str(message.get("role", "user")).upper()
            content = str(message.get("content", "")).strip()
            if content:
                parts.append(f"{role}: {content}")
        parts.append("ASSISTANT:")
        return "\n\n".join(parts)

    def _post_chat(self, payload: Dict) -> str | None:
        endpoint = f"{self.ollama_url}/api/chat"
        try:
            response = self._session.post(
                endpoint,
                json={**payload, "stream": False},
                timeout=self.request_timeout,
            )
        except RequestException as exc:
            self._log_request_exception(endpoint, exc)
            # Open circuit immediately on read timeout — same host won't answer generate either
            global _CIRCUIT_OPEN, _CIRCUIT_OPEN_AT
            _CIRCUIT_OPEN = True
            _CIRCUIT_OPEN_AT = time.time()
            return None
        if response.status_code == 404:
            self._chat_supported = False
            logger.warning("Chat endpoint unavailable (404) — switching to /api/generate")
            return None
        if response.status_code != 200:
            logger.warning("Chat request failed: %s (%s)", response.status_code, endpoint)
            return None
        try:
            data = response.json()
            return data.get("message", {}).get("content", "").strip() or None
        except Exception:
            return None

    def _post_generate(self, messages: List[Dict], model: str | None = None) -> str | None:
        endpoint = f"{self.ollama_url}/api/generate"
        try:
            response = self._session.post(
                endpoint,
                json={
                    "model": model or self.model,
                    "prompt": self._messages_to_prompt(messages),
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {"num_predict": 32, "num_ctx": 512, "temperature": 0.3},
                },
                timeout=self.request_timeout,
            )
        except RequestException as exc:
            self._log_request_exception(endpoint, exc)
            return None
        if response.status_code != 200:
            logger.warning("Generate request failed: %s (%s)", response.status_code, endpoint)
            return None
        try:
            data = response.json()
            return data.get("response", "").strip() or None
        except Exception:
            return None

    def health_check(self) -> Dict:
        try:
            endpoint = f"{self.ollama_url}/api/tags"
            response = self._session.get(endpoint, timeout=self.health_timeout)
            if response.status_code == 200:
                data = response.json()
                return {"ok": True, "models": [m['name'] for m in data.get('models', [])]}
            else:
                return {"ok": False, "error": f"Status {response.status_code}"}
        except Exception as e:
            self._log_request_exception(f"{self.ollama_url}/api/tags", e)
            return {"ok": False, "error": str(e)}

    def call(self, messages: List[Dict], stream=False) -> str:
        global _CIRCUIT_OPEN, _CIRCUIT_OPEN_AT
        # Circuit breaker: skip if Ollama recently failed
        if _CIRCUIT_OPEN:
            if time.time() - _CIRCUIT_OPEN_AT < _CIRCUIT_COOLDOWN:
                return self._offline_message()
            else:
                _CIRCUIT_OPEN = False
                logger.info("Circuit breaker reset — retrying Ollama")

        messages = self._compress_for_local(messages)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": "30m",
            "options": {"num_predict": 32, "num_ctx": 512, "temperature": 0.3},
        }
        for attempt in range(self.max_retries):
            try:
                content = None
                if self._chat_supported:
                    content = self._post_chat(payload)
                    if content:
                        _CIRCUIT_OPEN = False
                        return content
                    # If circuit just opened inside _post_chat, skip generate and bail
                    if _CIRCUIT_OPEN:
                        break
                    logger.warning("Attempt %s: /api/chat fallback to /api/generate", attempt + 1)
                content = self._post_generate(messages)
                if content:
                    _CIRCUIT_OPEN = False
                    return content
            except Exception as e:
                logger.warning("Attempt %s error: %s", attempt + 1, e)
            if attempt < self.max_retries - 1:
                self._sleep_before_retry(attempt)

        # Skip tinyllama fallback — same dead host, wastes another 8s
        # Open circuit — all models failed
        _CIRCUIT_OPEN = True
        _CIRCUIT_OPEN_AT = time.time()
        return self._offline_message()

    def stream(self, messages: List[Dict]) -> Generator[str, None, None]:
        global _CIRCUIT_OPEN, _CIRCUIT_OPEN_AT
        if _CIRCUIT_OPEN:
            if time.time() - _CIRCUIT_OPEN_AT < _CIRCUIT_COOLDOWN:
                yield self._offline_message()
                return
            else:
                _CIRCUIT_OPEN = False
                logger.info("Circuit breaker reset — retrying Ollama (stream)")
        messages = self._compress_for_local(messages)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
            "options": {"num_predict": 32, "num_ctx": 512, "temperature": 0.3},
        }
        try:
            if self._chat_supported:
                response = self._session.post(
                    f"{self.ollama_url}/api/chat",
                    json=payload,
                    timeout=self.request_timeout,
                    stream=True,
                )
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            try:
                                data = json.loads(line.decode('utf-8'))
                                if 'message' in data and 'content' in data['message']:
                                    yield data['message']['content']
                                if data.get('done', False):
                                    break
                            except Exception:
                                pass
                    return
                if response.status_code == 404:
                    self._chat_supported = False
                logger.warning("stream /api/chat failed: %s — fallback to /api/generate", response.status_code)
                gen_payload = {
                    "model": self.model,
                    "prompt": self._messages_to_prompt(messages),
                    "stream": True,
                    "keep_alive": "30m",
                    "options": {"num_predict": 64, "temperature": 0.3},
                }
                gen_resp = self._session.post(
                    f"{self.ollama_url}/api/generate",
                    json=gen_payload,
                    timeout=self.request_timeout,
                    stream=True,
                )
                if gen_resp.status_code != 200:
                    yield f"Erro: Status {gen_resp.status_code}"
                    return
                for line in gen_resp.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode('utf-8'))
                        token = data.get('response', '')
                        if token:
                            yield token
                        if data.get('done', False):
                            break
                    except Exception:
                        continue
        except Exception as e:
            yield f"Erro: {str(e)}"

    async def stream_chat(
        self,
        messages: List[Dict],
        on_token: Callable[[str], Awaitable[None]]
    ) -> str:
        global _CIRCUIT_OPEN, _CIRCUIT_OPEN_AT
        if _CIRCUIT_OPEN:
            if time.time() - _CIRCUIT_OPEN_AT < _CIRCUIT_COOLDOWN:
                msg = self._offline_message()
                await on_token(msg)
                return msg
            else:
                _CIRCUIT_OPEN = False
                logger.info("Circuit breaker reset — retrying Ollama (stream_chat)")
        messages = self._compress_for_local(messages)
        url = f"{self.ollama_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
            "options": {"temperature": 0.7, "num_predict": 32, "num_ctx": 512}
        }
        full = []
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                if self._chat_supported:
                    async with client.stream("POST", url, json=payload) as resp:
                        if resp.status_code == 200:
                            async for line in resp.aiter_lines():
                                if not line.strip():
                                    continue
                                try:
                                    obj = json.loads(line)
                                    token = obj.get("message", {}).get("content", "")
                                    if token:
                                        full.append(token)
                                        await on_token(token)
                                    if obj.get("done"):
                                        break
                                except Exception:
                                    continue
                            return "".join(full)
                        if resp.status_code == 404:
                            self._chat_supported = False
                        logger.warning("stream_chat /api/chat failed: %s — fallback to /api/generate", resp.status_code)

                gen_payload = {
                    "model": self.model,
                    "prompt": self._messages_to_prompt(messages),
                    "stream": True,
                    "keep_alive": "30m",
                    "options": {"num_predict": 32, "num_ctx": 512, "temperature": 0.7},
                }
                async with client.stream("POST", f"{self.ollama_url}/api/generate", json=gen_payload) as gen_resp:
                    async for line in gen_resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            token = obj.get("response", "")
                            if token:
                                full.append(token)
                                await on_token(token)
                            if obj.get("done"):
                                break
                        except Exception:
                            continue
        except Exception as e:
            logger.warning("stream_chat failed: %s", e)
            full.append(f"Erro: {str(e)}")
        return "".join(full)

    def embed(self, text: str) -> List[float]:
        global _CIRCUIT_OPEN, _CIRCUIT_OPEN_AT
        if _CIRCUIT_OPEN and time.time() - _CIRCUIT_OPEN_AT < _CIRCUIT_COOLDOWN:
            return []
        payload = {"model": self.embedding_model, "prompt": text}
        try:
            response = self._session.post(
                f"{self.ollama_url}/api/embeddings",
                json=payload,
                timeout=self.request_timeout,
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('embedding', [])
            else:
                logger.warning(f"Embed failed: {response.status_code}")
        except Exception as e:
            logger.warning(f"Embed error: {e}")
            _CIRCUIT_OPEN = True
            _CIRCUIT_OPEN_AT = time.time()
        return []

_client: JarvisAIClient | None = None

def get_ai_client() -> JarvisAIClient:
    global _client
    if _client is None:
        _client = JarvisAIClient()
    return _client


def is_ollama_available() -> bool:
    """Return Ollama availability and auto-recover the circuit when service is back."""
    global _CIRCUIT_OPEN, _CIRCUIT_OPEN_AT

    if not _CIRCUIT_OPEN:
        return True

    # If cooldown elapsed, allow normal retry path.
    if time.time() - _CIRCUIT_OPEN_AT >= _CIRCUIT_COOLDOWN:
        _CIRCUIT_OPEN = False
        return True

    # While still in cooldown, do a lightweight probe so we can recover early.
    try:
        cfg = get_config()
        probe_url = cfg.ollama_url.replace("localhost", "127.0.0.1") + "/api/tags"
        resp = requests.get(probe_url, timeout=(1, 2))
        if resp.status_code == 200:
            _CIRCUIT_OPEN = False
            return True
    except Exception:
        pass

    return False
