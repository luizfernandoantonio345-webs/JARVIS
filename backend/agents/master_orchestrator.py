"""
Master Orchestrator — roteamento inteligente com action wiring real.
Cada agente agora chama o módulo de action correspondente em vez de código inline.
"""
from __future__ import annotations

import logging
import re
import webbrowser
from typing import Callable

log = logging.getLogger(__name__)


# ── Keywords por agente (PT + EN) ─────────────────────────────────────────────
_RULES: dict[str, list[str]] = {
    "time_agent": [
        "que horas", "what time", "hora atual", "que hora são", "horas agora",
        "data de hoje", "que dia", "what day", "que data", "hoje é",
        "dia da semana", "mês atual", "ano atual", "current time", "current date",
    ],
    "math_agent": [
        "calcule", "calculate", "quanto é", "quanto vale", "compute",
        "resultado de", "me diga quanto", "qual é o resultado",
        "some ", "subtraia", "multiplique", "divida", "raiz quadrada",
        "porcentagem de", "% de", "what is 2", "what is 3",
        "quanto é 1", "quanto é 2", "quanto é 3",
    ],
    "system_agent": [
        "cpu", "uso do processador", "processador está",
        "memória ram", "uso de ram", "ram usage", "memory usage",
        "temperatura do", "processos ativos", "top processos",
        "status do sistema", "system status", "monitor do sistema",
        "quanto de ram", "desempenho do pc", "performance do sistema",
        "disco rígido", "espaço em disco", "disk space",
        "temperatura", "velocidade do cpu",
    ],
    "file_agent": [
        "listar arquivos", "list files", "o que tem na pasta",
        "arquivos no diretório", "mostrar pasta", "arquivos em",
        "ver pasta", "ver arquivos", "show files",
        "criar arquivo", "criar pasta", "create file", "create folder",
        "novo arquivo", "nova pasta", "new file", "new folder",
        "deletar arquivo", "apagar arquivo", "delete file", "remover arquivo",
        "mover arquivo", "move file", "copiar arquivo", "copy file",
        "renomear", "rename", "ler arquivo", "read file",
        "tamanho do disco", "disk usage", "espaço livre",
        "maiores arquivos", "largest files", "arquivos grandes",
        "encontrar arquivo", "find file", "procurar arquivo",
        "conteúdo do arquivo", "informações do arquivo",
    ],
    "computer_agent": [
        "abrir", "abra", "abre", "abri", "open", "launch", "start",
        "iniciar", "inicia", "execute o app", "executar aplicativo",
        "fechar", "close", "encerrar programa",
        "chrome", "google chrome", "firefox", "edge", "browser", "navegador",
        "spotify", "discord", "whatsapp", "telegram", "slack",
        "vscode", "visual studio code", "vs code",
        "terminal", "cmd", "powershell", "prompt",
        "calculadora", "calculator", "notepad", "bloco de notas",
        "excel", "word", "powerpoint", "outlook", "office",
        "steam", "vlc", "obs", "audacity",
        "explorador de arquivos", "file explorer", "explorer",
        "gerenciador de tarefas", "task manager",
        "paint", "mspaint",
    ],
    "web_agent": [
        "pesquisar", "pesquisa sobre", "busca sobre", "buscar sobre",
        "procurar na internet", "search for", "google",
        "o que é ", "o que foi ", "quem é ", "quando foi ", "onde fica ",
        "como funciona ", "explique ", "what is ", "who is ", "where is ",
        "notícias de", "noticias de", "news about",
        "informações sobre", "information about",
        "previsão do tempo", "weather forecast",
        "comparar ", "compare ", " vs ",
        "pesquise sobre", "me explique",
    ],
    "shell_agent": [
        "execute o comando", "run command", "executar comando",
        "rodar o comando", "shell:", "bash:", "cmd:",
        "git status", "git log", "git commit", "git push",
        "npm install", "npm run", "pip install", "pip list",
        "python script", "pytest", "uvicorn",
        "ls ", "dir ", "pwd", "mkdir ",
    ],
    "code_agent": [
        "código", "code", "programa", "script", "codificar",
        "escrever código", "write code", "criar função",
        "python", "javascript", "typescript", "java ", " c++ ", "rust",
        "html", "css", "sql",
        "bug no código", "erro no código", "fix this code",
        "corrigir código", "debugar", "debug this",
        "função", "classe", "método", "algorithm", "algoritmo",
        "otimizar código", "refatorar", "refactor",
        "escrever um script", "write a script", "make a program",
        "implementar", "implement",
    ],
    "memory_agent": [
        "lembra que", "lembre-se que", "remember that",
        "salvar na memória", "save to memory", "anota que",
        "o que você sabe sobre mim", "o que você lembra",
        "histórico de conversa", "conversation history",
        "o que falamos", "nossa conversa anterior",
        "salvar fato", "guardar informação",
        "o que eu disse antes", "what did i say",
        "lembro que", "lembras",
    ],
    "voice_agent": [
        "fala isso", "diga isso", "diz isso", "fale isso",
        "leia em voz alta", "pronuncia ", "repete ",
        "speak this", "say this", "read aloud",
        "falar ", "dizer ",
    ],
}

# ── APP name mapping ───────────────────────────────────────────────────────────
_APP_MAP: dict[str, str] = {
    "chrome": "chrome", "google chrome": "google chrome",
    "firefox": "firefox", "edge": "edge",
    "spotify": "spotify", "discord": "discord",
    "whatsapp": "whatsapp", "telegram": "telegram",
    "slack": "slack",
    "vscode": "vscode", "vs code": "vscode",
    "visual studio code": "vscode",
    "terminal": "terminal", "cmd": "cmd",
    "powershell": "powershell",
    "calculadora": "calculator", "calculator": "calculator",
    "notepad": "notepad", "bloco de notas": "notepad",
    "excel": "excel", "word": "word",
    "powerpoint": "powerpoint", "outlook": "outlook",
    "steam": "steam", "vlc": "vlc", "obs": "obs",
    "audacity": "audacity",
    "explorador": "explorer", "explorer": "explorer",
    "file explorer": "explorer",
    "gerenciador de tarefas": "task manager",
    "task manager": "task manager",
    "paint": "paint", "mspaint": "paint",
}

# ── Sites que abrem direto no browser ─────────────────────────────────────────
_SITE_MAP: dict[str, str] = {
    "youtube": "https://youtube.com",
    "gmail": "https://gmail.com",
    "google": "https://google.com",
    "github": "https://github.com",
    "netflix": "https://netflix.com",
    "reddit": "https://reddit.com",
    "twitter": "https://twitter.com",
    "instagram": "https://instagram.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "linkedin": "https://linkedin.com",
}

# ── File path shortcuts ────────────────────────────────────────────────────────
_PATH_SHORTCUTS = ["desktop", "downloads", "documents", "home", "pictures", "music", "videos"]

# ── Verbs para extrair action de arquivo ──────────────────────────────────────
_FILE_ACTION_MAP = [
    (["listar", "list", "mostrar", "ver", "show", "o que tem", "conteúdo da pasta"], "list"),
    (["criar arquivo", "create file", "novo arquivo", "new file"], "create_file"),
    (["criar pasta", "create folder", "nova pasta", "new folder"], "create_folder"),
    (["deletar", "apagar", "delete", "remover", "excluir"], "delete"),
    (["mover", "move"], "move"),
    (["copiar", "copy"], "copy"),
    (["renomear", "rename"], "rename"),
    (["ler", "read", "conteúdo do arquivo", "abrir arquivo"], "read"),
    (["espaço em disco", "disk usage", "espaço livre", "disk space", "tamanho do disco"], "disk_usage"),
    (["maiores arquivos", "largest", "arquivo grande"], "largest"),
    (["encontrar", "find", "procurar arquivo", "buscar arquivo"], "find"),
    (["informações", "info sobre", "detalhes de"], "info"),
]


class MasterOrchestrator:
    """Roteador com wiring real de actions — sem código inline."""

    @property
    def _router(self):
        """
        SmartRouter criado sob demanda e reaproveitado.

        Preguiçoso de propósito: o roteador importa o llm_service, e carregar
        isso no import do orquestrador criaria ciclo.
        """
        existente = getattr(self, "_smart_router", None)
        if existente is not None:
            return existente
        try:
            from core.router import SmartRouter
            import os
            self._smart_router = SmartRouter(
                _RULES,
                use_llm=os.getenv("JARVIS_ROUTER_LLM", "true").lower() != "false",
            )
        except Exception as exc:  # sem roteador novo, segue o antigo
            log.warning("[ORCH] SmartRouter indisponível, usando palavra-chave: %s", exc)
            self._smart_router = None
        return self._smart_router

    def route(self, message: str) -> str:
        """
        Decide o agente pelo SENTIDO da mensagem, não por substring.

        Camadas: padrão ancorado → modelo local → palavra-chave → chat.
        Devolve só o nome, como antes. Use route_decision() para ver por quê.
        """
        roteador = self._router
        if roteador is not None:
            return roteador.route(message).agent
        return self._route_by_keyword(message)

    def route_decision(self, message: str):
        """Decisão completa: agente, confiança, método e motivo."""
        roteador = self._router
        if roteador is not None:
            return roteador.route(message)
        from core.router import RouteDecision
        return RouteDecision(self._route_by_keyword(message), 0.45, "keyword", "fallback")

    @staticmethod
    def _route_by_keyword(message: str) -> str:
        """Comportamento original, mantido como rede de segurança."""
        msg = message.lower()
        for agent, keywords in _RULES.items():
            if any(k in msg for k in keywords):
                return agent
        return "chat_agent"

    async def execute(
        self,
        message: str,
        session_id: str,
        on_token: Callable = None,
    ) -> str:
        agent = self.route(message)
        log.info("[ORCH] %s → %s | %.60s", session_id, agent, message)

        handlers = {
            "time_agent":     self._time_agent,
            "math_agent":     self._math_agent,
            "system_agent":   self._system_agent,
            "file_agent":     self._file_agent,
            "computer_agent": self._computer_agent,
            "web_agent":      self._web_agent,
            "shell_agent":    self._shell_agent,
            "code_agent":     self._code_agent,
            "memory_agent":   self._memory_agent,
            "voice_agent":    self._voice_agent,
        }

        handler = handlers.get(agent, self._chat_agent)
        try:
            return await handler(message, session_id, on_token)
        except Exception as e:
            log.error("[ORCH] Agente %s falhou: %s — fallback para chat", agent, e)
            return await self._chat_agent(message, session_id, on_token)

    # ── Agentes de utilidade (sem LLM) ────────────────────────────────────────

    async def _time_agent(self, message, session_id, on_token):
        from datetime import datetime
        now = datetime.now()
        pt = any(w in message.lower() for w in ["hora", "dia", "data", "hoje", "mês", "ano"])
        if pt:
            weekdays = ["segunda-feira", "terça-feira", "quarta-feira",
                        "quinta-feira", "sexta-feira", "sábado", "domingo"]
            wd = weekdays[now.weekday()]
            resp = (f"São {now.strftime('%H:%M')} de {wd}, "
                    f"{now.strftime('%d/%m/%Y')}, Senhor.")
        else:
            resp = (f"It is {now.strftime('%I:%M %p')}, "
                    f"{now.strftime('%A, %B %d, %Y')}, Sir.")
        if on_token:
            await on_token(resp)
        return resp

    async def _math_agent(self, message, session_id, on_token):
        import re
        from utils.math_eval import safe_eval_math
        expr = re.sub(r'[^0-9+\-*/().,% ^]', ' ', message)
        expr = expr.strip()
        if expr:
            try:
                result = safe_eval_math(expr)
                resp = f"O resultado é {result}, Senhor."
                if on_token:
                    await on_token(resp)
                return resp
            except Exception:
                pass
        return await self._chat_agent(message, session_id, on_token)

    async def _system_agent(self, message, session_id, on_token):
        try:
            from actions.system_monitor import execute as sysmon
            report = await _run_sync(sysmon, "")
            # Keep it concise for voice/chat — first section only
            lines = report.split("\n")
            short = "\n".join(lines[:20])
            if on_token:
                await on_token(short)
            return short
        except Exception:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            resp = (f"CPU at {cpu:.0f}%, RAM at {ram.percent:.0f}% "
                    f"({ram.used//1024//1024//1024:.1f}GB / {ram.total//1024//1024//1024:.0f}GB), Sir.")
            if on_token:
                await on_token(resp)
            return resp

    async def _file_agent(self, message, session_id, on_token):
        from actions.file_controller import file_controller
        msg = message.lower()

        action = "list"
        for keywords, act in _FILE_ACTION_MAP:
            if any(k in msg for k in keywords):
                action = act
                break

        path = "."
        for shortcut in _PATH_SHORTCUTS:
            if shortcut in msg:
                path = shortcut
                break

        params = {"action": action, "path": path}

        # Extract specific filename/content if provided
        if action in ("create_file", "write"):
            # Look for filename after action words
            m = re.search(r'(?:criar|create|novo|new)\s+arquivo\s+["\']?([^\s"\']+)', msg)
            if m:
                params["path"] = m.group(1)

        if action in ("read", "delete", "info"):
            m = re.search(r'(?:arquivo|file|ficheiro)\s+["\']?([^\s"\']+)', msg)
            if m:
                params["path"] = m.group(1)

        try:
            result = await _run_sync(file_controller, params)
            resp = f"{result}"
            if on_token:
                await on_token(resp)
            return resp
        except Exception as e:
            return f"Erro ao acessar arquivos, Senhor: {e}"

    async def _computer_agent(self, message, session_id, on_token):
        msg = message.lower()

        # Check website shortcuts first
        for site_key, url in _SITE_MAP.items():
            if site_key in msg:
                webbrowser.open(url)
                resp = f"Abrindo {site_key.title()} no browser, Senhor."
                if on_token:
                    await on_token(resp)
                return resp

        # Find app name
        app_name = None
        for key, val in _APP_MAP.items():
            if key in msg:
                app_name = val
                break

        if app_name:
            try:
                from actions.open_app import open_app
                result = await _run_sync(open_app, {"app_name": app_name})
                resp = f"{result}, Senhor."
                if on_token:
                    await on_token(resp)
                return resp
            except Exception as e:
                log.warning("[COMPUTER] open_app falhou: %s", e)

        # Fallback to LLM to understand what to do
        return await self._chat_agent(message, session_id, on_token)

    async def _web_agent(self, message, session_id, on_token):
        # Extract query by stripping trigger words
        stopwords = [
            "pesquisar sobre", "pesquisa sobre", "busca sobre", "buscar sobre",
            "procurar na internet", "search for", "pesquisar", "pesquisa", "buscar",
            "o que é", "o que foi", "quem é", "quando foi", "onde fica",
            "como funciona", "explique sobre", "me explique", "explique",
            "informações sobre", "information about", "me fale sobre",
            "what is", "who is", "where is", "news about", "notícias de",
            "previsão do tempo para", "weather in", "tempo em",
        ]
        query = message
        for sw in sorted(stopwords, key=len, reverse=True):
            query = re.sub(re.escape(sw), "", query, flags=re.IGNORECASE).strip()
        query = query.strip(" .,?!")

        if not query or len(query) < 2:
            query = message

        try:
            from actions.web_search import web_search
            result = await _run_sync(web_search, {"query": query})

            # If we got a real abstract (not "abrindo no browser"), summarize with LLM
            if result and len(result) > 80 and "brindo" not in result and "browser" not in result.lower():
                from ai.client import get_ai_client
                from core.jarvis_persona import _build_identity
                system = (
                    _build_identity() + "\n\n"
                    "Resuma a informação encontrada em 2-3 frases, em português, "
                    "de forma clara e objetiva. Não cite a fonte."
                )
                msgs = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Encontrei isso sobre '{query}':\n{result}\n\nFaça um resumo, Senhor."},
                ]
                if on_token:
                    return await get_ai_client().stream_chat(msgs, on_token)
                return get_ai_client().call(msgs)

            if on_token:
                await on_token(result)
            return result
        except Exception as e:
            log.warning("[WEB] web_search falhou: %s", e)
            return await self._chat_agent(message, session_id, on_token)

    async def _shell_agent(self, message, session_id, on_token):
        # Extract the command from the message
        msg = message
        patterns = [
            r'(?:execute|run|executar|rodar|shell|bash|cmd)[\s:]+(.+)',
            r'`([^`]+)`',
            r'"([^"]+)"',
        ]
        command = None
        for pattern in patterns:
            m = re.search(pattern, msg, re.IGNORECASE)
            if m:
                command = m.group(1).strip()
                break

        if not command:
            # Last resort: take everything after common trigger words
            for trigger in ["execute", "run", "executar", "rodar"]:
                if trigger in msg.lower():
                    idx = msg.lower().index(trigger) + len(trigger)
                    command = msg[idx:].strip(" :\"'`")
                    break

        if not command:
            return await self._chat_agent(message, session_id, on_token)

        try:
            from actions.shell_exec import execute as shell_exec
            result = await _run_sync(shell_exec, command)
            if on_token:
                await on_token(result)
            return result
        except Exception as e:
            log.warning("[SHELL] falhou: %s", e)
            return f"Erro ao executar comando, Senhor: {e}"

    async def _code_agent(self, message, session_id, on_token):
        from ai.client import get_ai_client
        from core.jarvis_persona import _build_identity
        system = (
            _build_identity() + "\n\n"
            "MODO ENGENHEIRO DE SOFTWARE SÊNIOR:\n"
            "- Escreva código limpo, funcional e bem estruturado\n"
            "- Use Python 3.11+ por padrão a menos que especificado\n"
            "- Explique brevemente o que o código faz em 1-2 frases\n"
            "- Inclua type hints em Python\n"
            "- Para bugs: identifique a causa raiz antes de corrigir"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": message},
        ]
        if on_token:
            return await get_ai_client().stream_chat(messages, on_token)
        return get_ai_client().call(messages)

    async def _memory_agent(self, message, session_id, on_token):
        from memory.persistent_memory import get_persistent_memory
        mem = get_persistent_memory()
        msg = message.lower()

        if any(w in msg for w in ["histórico", "conversa", "lembra", "o que falamos", "conversation"]):
            recent = mem.get_recent(session_id, 8)
            if not recent:
                resp = "Não encontrei conversas anteriores nesta sessão, Senhor."
            else:
                lines = [f"[{m['role'].upper()}] {m['content'][:100]}" for m in recent]
                resp = "Últimas interações desta sessão:\n" + "\n".join(lines)
            if on_token:
                await on_token(resp)
            return resp

        if any(w in msg for w in ["salvar", "salva", "anota", "remember", "guardar"]):
            # Extract the fact to remember
            for trigger in ["que ", "that ", "isso: ", "this: ", ":"]:
                if trigger in msg:
                    fact = message[message.lower().index(trigger) + len(trigger):].strip()
                    mem.save_fact(fact, session_id)
                    resp = f"Anotado, Senhor: '{fact}'"
                    if on_token:
                        await on_token(resp)
                    return resp
            resp = "Por favor, me diga o que devo memorizar, Senhor."
            if on_token:
                await on_token(resp)
            return resp

        # Show known facts
        facts = mem.get_facts(10)
        profile = mem.get_profile()
        if facts or profile:
            lines = []
            if profile:
                lines.append("Perfil: " + ", ".join(f"{k}={v}" for k, v in profile.items()))
            if facts:
                lines.append("Fatos: " + "; ".join(facts[:5]))
            resp = "O que sei sobre o Senhor:\n" + "\n".join(lines)
        else:
            resp = "Ainda não tenho informações salvas sobre o Senhor."
        if on_token:
            await on_token(resp)
        return resp

    async def _voice_agent(self, message, session_id, on_token):
        # Extract what to speak
        stopwords = ["fala", "diz", "diga", "fale", "speak", "say", "repete", "leia em voz alta"]
        text = message
        for sw in stopwords:
            text = re.sub(r'\b' + sw + r'\b', '', text, flags=re.IGNORECASE).strip()
        text = text.strip(" :.,")

        if not text:
            resp = "O que devo falar, Senhor?"
            if on_token:
                await on_token(resp)
            return resp

        # Speak via TTS (non-blocking)
        try:
            import asyncio
            from voice_v2.output import speak
            asyncio.create_task(speak(text))
        except Exception:
            pass

        resp = f"Falando: '{text}'"
        if on_token:
            await on_token(resp)
        return resp

    # ── Chat principal com memória + raciocínio melhorado ────────────────────

    async def _chat_agent(self, message, session_id, on_token):
        from ai.client import get_ai_client
        from memory.persistent_memory import get_persistent_memory
        from core.jarvis_persona import _build_identity, _build_main_prompt

        mem = get_persistent_memory()

        # ── 1. Contexto de memória persistente ───────────────────────────────
        context = mem.build_context(session_id)

        # ── 2. Tentar injeção de memória semântica (se disponível) ───────────
        semantic_context = ""
        try:
            from memory.semantic_engine import SemanticMemory
            import asyncio
            sem_results = await asyncio.wait_for(
                SemanticMemory().search(message, top_k=3), timeout=1.5
            )
            if sem_results:
                snippets = [r.get("content", "")[:200] for r in sem_results if r.get("content")]
                if snippets:
                    semantic_context = (
                        "\n\nMEMÓRIA SEMÂNTICA RELEVANTE (usar se útil):\n"
                        + "\n".join(f"• {s}" for s in snippets)
                    )
        except Exception:
            pass  # Semântica opcional — não bloqueia

        # ── 3. Montar prompt de sistema completo ─────────────────────────────
        system = _build_main_prompt()
        if context:
            system += f"\n\n{context}"
        if semantic_context:
            system += semantic_context

        # ── 4. Construir histórico de mensagens (últimas 12) ─────────────────
        messages = [{"role": "system", "content": system}]
        for m in mem.get_recent(session_id, 12):
            role = m.get("role", "user")
            if role == "assistant":
                role = "assistant"
            elif role != "user":
                role = "user"
            messages.append({"role": role, "content": m["content"]})
        messages.append({"role": "user", "content": message})

        # ── 5. Gerar resposta (streaming ou síncrono) ─────────────────────────
        if on_token:
            resp = await get_ai_client().stream_chat(messages, on_token)
        else:
            resp = get_ai_client().call(messages)

        # ── 6. Persistir na memória ───────────────────────────────────────────
        try:
            mem.save(session_id, "user", message)
            mem.save(session_id, "assistant", resp or "")
        except Exception as e:
            log.warning("[MEMORY] Não foi possível salvar: %s", e)

        # ── 7. Tentar indexar na memória semântica ────────────────────────────
        try:
            from memory.semantic_engine import SemanticMemory
            import asyncio
            if resp and len(resp) > 30:
                asyncio.create_task(
                    SemanticMemory().add(
                        f"Q: {message[:200]}\nA: {resp[:400]}",
                        {"session_id": session_id, "type": "conversation"}
                    )
                )
        except Exception:
            pass

        return resp


# ── Helper: run sync function in thread pool ──────────────────────────────────

async def _run_sync(fn, *args):
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


# ── Singleton ─────────────────────────────────────────────────────────────────

_orch: MasterOrchestrator | None = None


def get_orchestrator() -> MasterOrchestrator:
    global _orch
    if _orch is None:
        _orch = MasterOrchestrator()
    return _orch
