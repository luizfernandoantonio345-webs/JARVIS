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
        self.ollama_url = cfg.ollama_url
        self.model = cfg.model
        self.embedding_model = cfg.embedding_model
        self.timeout = cfg.timeout
        self.max_retries = cfg.max_retries
        connect_timeout = 10
        per_attempt_read_timeout = max(60, self.timeout)
        self.request_timeout = (connect_timeout, per_attempt_read_timeout)
        self.health_timeout = (5, 15)
        self._session = _build_session(pool_connections=6, pool_maxsize=6)

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = min(2 ** attempt, 8)
        time.sleep(delay)

    def _log_request_exception(self, endpoint: str, exc: Exception) -> None:
        logger.warning("Ollama request to %s failed: %s", endpoint, exc)

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
        messages = self._compress_for_local(messages)
        payload = {"model": self.model, "messages": messages, "stream": stream, "keep_alive": "30m"}
        for attempt in range(self.max_retries):
            try:
                content = self._post_chat(payload)
                if content:
                    return content

                logger.warning("Attempt %s: /api/chat fallback to /api/generate", attempt + 1)
                content = self._post_generate(messages)
                if content:
                    return content
            except Exception as e:
                logger.warning("Attempt %s error: %s", attempt + 1, e)
            if attempt < self.max_retries - 1:
                self._sleep_before_retry(attempt)

        # Final fallback: try tinyllama
        logger.warning("All attempts with %s failed — trying fallback model %s", self.model, FALLBACK_MODEL)
        try:
            fallback_payload = {"model": FALLBACK_MODEL, "messages": messages, "stream": False, "keep_alive": "30m"}
            content = self._post_chat(fallback_payload)
            if content:
                return content
            content = self._post_generate(messages, model=FALLBACK_MODEL)
            if content:
                return content
        except Exception as e:
            logger.warning("Fallback model %s also failed: %s", FALLBACK_MODEL, e)

        return "Erro: Não foi possível conectar ao serviço de IA. Verifique a configuração do Ollama."

    def stream(self, messages: List[Dict]) -> Generator[str, None, None]:
        messages = self._compress_for_local(messages)
        payload = {"model": self.model, "messages": messages, "stream": True, "keep_alive": "30m"}
        try:
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
            else:
                yield f"Erro: Status {response.status_code}"
        except Exception as e:
            yield f"Erro: {str(e)}"

    async def stream_chat(
        self,
        messages: List[Dict],
        on_token: Callable[[str], Awaitable[None]]
    ) -> str:
        messages = self._compress_for_local(messages)
        url = f"{self.ollama_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
            "options": {"temperature": 0.7, "num_predict": 512}
        }
        full = []
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                async with client.stream("POST", url, json=payload) as resp:
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
        except Exception as e:
            logger.warning("stream_chat failed: %s", e)
            full.append(f"Erro: {str(e)}")
        return "".join(full)

    def embed(self, text: str) -> List[float]:
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
        return []

_client: JarvisAIClient | None = None

def get_ai_client() -> JarvisAIClient:
    global _client
    if _client is None:
        _client = JarvisAIClient()
    return _client