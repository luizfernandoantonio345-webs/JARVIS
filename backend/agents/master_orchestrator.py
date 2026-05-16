import logging
from typing import Callable, Awaitable

log = logging.getLogger(__name__)

class MasterOrchestrator:
    ROUTING_RULES = {
        "code_agent":     ["código", "code", "programa", "script",
                           "python", "javascript", "bug", "erro",
                           "função", "classe", "debug", "fix"],
        "computer_agent": ["abrir", "fechar", "executar", "terminal",
                           "arquivo", "pasta", "navegador", "chrome",
                           "youtube", "spotify", "vscode", "app"],
        "memory_agent":   ["lembra", "memoria", "histórico", "contexto",
                           "salva", "anota", "remember", "anterior"],
        "research_agent": ["pesquisa", "busca", "explica", "o que é",
                           "como funciona", "pesquise", "search"],
        "voice_agent":    ["fala", "diz", "pronuncia", "repete"],
    }

    def route(self, message: str) -> str:
        msg_lower = message.lower()
        for agent, keywords in self.ROUTING_RULES.items():
            if any(k in msg_lower for k in keywords):
                return agent
        return "chat_agent"

    async def execute(
        self,
        message: str,
        session_id: str,
        on_token: Callable = None
    ) -> str:
        agent = self.route(message)
        log.info("[ORCH] Roteando para %s: %s", agent, message[:50])

        if agent == "computer_agent":
            return await self._computer_agent(message, session_id)
        elif agent == "code_agent":
            return await self._code_agent(message, session_id, on_token)
        elif agent == "memory_agent":
            return await self._memory_agent(message, session_id)
        elif agent == "research_agent":
            return await self._research_agent(message, session_id, on_token)
        else:
            return await self._chat_agent(message, session_id, on_token)

    async def _chat_agent(self, message, session_id, on_token):
        from backend.ai.client import get_ai_client
        from backend.memory.persistent_memory import get_persistent_memory
        mem = get_persistent_memory()
        context = mem.build_context(session_id)
        system = (
            "Você é JARVIS, assistente pessoal de alto nível. "
            "Responda sempre em português, de forma direta e inteligente. "
            "Trate o usuário como 'Senhor'.\n\n" + context
        )
        messages = [{"role": "system", "content": system}]
        for m in mem.get_recent(session_id, 8):
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": message})

        if on_token:
            resp = await get_ai_client().stream_chat(messages, on_token)
        else:
            resp = get_ai_client().call(messages)

        mem.save(session_id, "user", message)
        mem.save(session_id, "assistant", resp)
        return resp

    async def _code_agent(self, message, session_id, on_token):
        from backend.ai.client import get_ai_client
        system = (
            "Você é um engenheiro de software sênior assistindo o Senhor. "
            "Escreva código limpo, comentado e funcional. "
            "Use Python por padrão, a menos que especificado. "
            "Explique brevemente o que o código faz."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message}
        ]
        if on_token:
            return await get_ai_client().stream_chat(messages, on_token)
        return get_ai_client().call(messages)

    async def _computer_agent(self, message, session_id):
        msg = message.lower()
        if any(w in msg for w in ["chrome", "navegador", "browser"]):
            import subprocess
            subprocess.Popen(["chrome.exe"])
            return "Abrindo Chrome, Senhor."
        if any(w in msg for w in ["vscode", "vs code", "code"]):
            import subprocess
            subprocess.Popen(["code", "."])
            return "Abrindo VS Code, Senhor."
        if any(w in msg for w in ["terminal", "cmd", "powershell"]):
            import subprocess
            subprocess.Popen(["powershell.exe"])
            return "Abrindo terminal, Senhor."
        if any(w in msg for w in ["youtube"]):
            import webbrowser
            webbrowser.open("https://youtube.com")
            return "Abrindo YouTube, Senhor."
        if any(w in msg for w in ["spotify"]):
            import subprocess
            subprocess.Popen(["spotify.exe"])
            return "Abrindo Spotify, Senhor."
        return "Comando de computador recebido. Especifique o que deseja abrir, Senhor."

    async def _memory_agent(self, message, session_id):
        from backend.memory.persistent_memory import get_persistent_memory
        mem = get_persistent_memory()
        msg = message.lower()
        if any(w in msg for w in ["histórico", "conversas", "lembra"]):
            recent = mem.get_recent(session_id, 5)
            if not recent:
                return "Não encontrei conversas anteriores, Senhor."
            lines = [f"{m['role'].upper()}: {m['content'][:80]}" for m in recent]
            return "Últimas interações:\n" + "\n".join(lines)
        if any(w in msg for w in ["salva", "anota", "remember"]):
            fact = message.replace("salva","").replace("anota","").strip()
            mem.save_fact(fact, session_id)
            return f"Anotado, Senhor: '{fact}'"
        return "Memória consultada, Senhor."

    async def _research_agent(self, message, session_id, on_token):
        from backend.ai.client import get_ai_client
        system = (
            "Você é um pesquisador especializado. "
            "Explique de forma clara, estruturada e completa. "
            "Use bullet points quando adequado. Responda em português."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message}
        ]
        if on_token:
            return await get_ai_client().stream_chat(messages, on_token)
        return get_ai_client().call(messages)

_orch = None
def get_orchestrator() -> MasterOrchestrator:
    global _orch
    if _orch is None:
        _orch = MasterOrchestrator()
    return _orch
