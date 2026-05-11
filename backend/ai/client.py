import requests
import time
import logging
import json
from typing import List, Dict, Generator
from backend.config import get_config

logger = logging.getLogger(__name__)

class JarvisAIClient:
    def __init__(self):
        cfg = get_config()
        self.ollama_url = cfg.ollama_url
        self.model = cfg.model
        self.embedding_model = cfg.embedding_model
        self.timeout = cfg.timeout
        self.max_retries = cfg.max_retries

    def health_check(self) -> Dict:
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return {"ok": True, "models": [m['name'] for m in data.get('models', [])]}
            else:
                return {"ok": False, "error": f"Status {response.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def call(self, messages: List[Dict], stream=False) -> str:
        payload = {"model": self.model, "messages": messages, "stream": stream}
        for attempt in range(self.max_retries):
            try:
                response = requests.post(f"{self.ollama_url}/api/chat", json=payload, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    return data.get('message', {}).get('content', '')
                else:
                    logger.warning(f"Attempt {attempt+1} failed: {response.status_code}")
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} error: {e}")
            if attempt < self.max_retries - 1:
                time.sleep(1)
        return "Erro: Não foi possível conectar ao serviço de IA. Verifique a configuração do Ollama."

    def stream(self, messages: List[Dict]) -> Generator[str, None, None]:
        payload = {"model": self.model, "messages": messages, "stream": True}
        try:
            response = requests.post(f"{self.ollama_url}/api/chat", json=payload, timeout=self.timeout, stream=True)
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            if 'message' in data and 'content' in data['message']:
                                yield data['message']['content']
                            if data.get('done', False):
                                break
                        except:
                            pass
            else:
                yield f"Erro: Status {response.status_code}"
        except Exception as e:
            yield f"Erro: {str(e)}"

    def embed(self, text: str) -> List[float]:
        payload = {"model": self.embedding_model, "prompt": text}
        try:
            response = requests.post(f"{self.ollama_url}/api/embeddings", json=payload, timeout=self.timeout)
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