import logging
from typing import Callable, Awaitable

log = logging.getLogger(__name__)

class MasterOrchestrator:
    ROUTING_RULES = {
        "code_agent":     ["código", "code", "programa", "script",
                           "python", "javascript", "bug", "erro",
                           "função", "classe", "debug", "fix"],
        "time_agent":     ["que horas", "what time", "hora atual",
                           "data de hoje", "que dia", "what day"],
        "math_agent":     ["calcule", "calculate", "quanto é",
                           "quanto vale", "compute", "resultado de"],
        "system_agent":   ["cpu", "ram", "memória do sistema", "desempenho",
                           "performance do sistema", "uso de memória",
                           "temperatura", "processos"],
        "file_agent":     ["listar arquivos", "list files",
                           "o que tem na pasta", "arquivos no diretório"],
        "computer_agent": ["abrir", "fechar", "executar", "terminal",
                           "pasta", "navegador", "chrome",
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
        elif agent == "time_agent":
            return await self._time_agent(message, session_id, on_token)
        elif agent == "math_agent":
            return await self._math_agent(message, session_id, on_token)
        elif agent == "system_agent":
            return await self._system_agent(message, session_id, on_token)
        elif agent == "file_agent":
            return await self._file_agent(message, session_id, on_token)
        else:
            return await self._chat_agent(message, session_id, on_token)

    async def _chat_agent(self, message, session_id, on_token):
        from ai.client import get_ai_client
        from memory.persistent_memory import get_persistent_memory
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
        from ai.client import get_ai_client
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
        from memory.persistent_memory import get_persistent_memory
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
        from ai.client import get_ai_client
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

    async def _time_agent(self, message, session_id, on_token):
        from datetime import datetime
        now = datetime.now()
        pt = any(w in message.lower() for w in ["hora", "dia", "data"])
        if pt:
            resp = (f"São {now.strftime('%H:%M')} de "
                    f"{now.strftime('%d/%m/%Y')}, Senhor.")
        else:
            resp = (f"It's {now.strftime('%I:%M %p')}, "
                    f"{now.strftime('%B %d, %Y')}, Sir.")
        if on_token:
            await on_token(resp)
        return resp

    async def _math_agent(self, message, session_id, on_token):
        import re
        try:
            expr = re.sub(r'[^0-9+\-*/().,% ]', '', message).replace(',', '.')
            stripped = expr.strip()
            if stripped:
                result = eval(stripped, {"__builtins__": {}}, {})
                resp = f"The result is {result}, Sir."
                if on_token:
                    await on_token(resp)
                return resp
        except Exception:
            pass
        return await self._llm_fallback(message, session_id, on_token)

    async def _system_agent(self, message, session_id, on_token):
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            resp = (f"CPU at {cpu:.0f}%, RAM at {ram.percent:.0f}% "
                    f"({ram.used // 1024 // 1024 // 1024:.1f}GB used), Sir.")
            if on_token:
                await on_token(resp)
            return resp
        except Exception:
            return await self._llm_fallback(message, session_id, on_token)

    async def _file_agent(self, message, session_id, on_token):
        import pathlib
        files = [f.name for f in pathlib.Path('.').iterdir()
                 if not f.name.startswith('.')][:10]
        resp = f"Current directory contains: {', '.join(files)}, Sir."
        if on_token:
            await on_token(resp)
        return resp

    async def _llm_fallback(self, message, session_id, on_token):
        return await self._chat_agent(message, session_id, on_token)


_orch = None
def get_orchestrator() -> MasterOrchestrator:
    global _orch
    if _orch is None:
        _orch = MasterOrchestrator()
    return _orch
