import asyncio, logging, time
log = logging.getLogger("jarvis.reflection")

class ReflectionEngine:
    def __init__(self, batch_size: int = 10):
        self._pending = []
        self._batch_size = batch_size

    def record(self, session_id: str, query: str, response: str,
               duration: float, agent: str, success: bool):
        self._pending.append({
            "session": session_id, "query": query[:200],
            "response": response[:300], "duration": duration,
            "agent": agent, "success": success, "ts": time.time()
        })
        if len(self._pending) >= self._batch_size:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._reflect())
            except Exception:
                pass

    async def _reflect(self):
        if not self._pending:
            return
        batch = self._pending[:self._batch_size]
        self._pending = self._pending[self._batch_size:]
        try:
            from backend.experience.engine import get_experience
            from backend.services.llm_service import call_llm
            summary = "\n".join([
                f"Q:{i['query'][:60]}|A:{i['response'][:60]}|{'OK' if i['success'] else 'FAIL'}|{i['duration']:.1f}s"
                for i in batch
            ])
            resp = await call_llm([
                {"role": "system", "content": "Analise interacoes de IA. Responda JSON com: worked, failed, pattern, improvement. Seja breve."},
                {"role": "user", "content": f"Analise {len(batch)} interacoes:\n{summary}"}
            ])
            import json
            try:
                start = resp.find("{"); end = resp.rfind("}") + 1
                if start >= 0:
                    data = json.loads(resp[start:end])
                    get_experience().reflect(
                        session_id=batch[0]["session"],
                        worked=data.get("worked",""),
                        failed=data.get("failed",""),
                        pattern=data.get("pattern",""),
                        improvement=data.get("improvement","")
                    )
            except Exception:
                pass
        except Exception as e:
            log.warning("[REFLECT] Falhou: %s", e)

_ref = None
def get_reflection() -> ReflectionEngine:
    global _ref
    if _ref is None:
        _ref = ReflectionEngine()
    return _ref
