"""
command_mapper — FASE 12A

Maps recognized voice commands to HTTP API calls or internal functions.
Provides verbosity-aware response summarization.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

import httpx

log = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000"


class VoiceCommandMapper:
    """
    Translates voice utterances into API calls and formats responses
    according to the current verbosity setting.
    """

    # Pattern → (api_call_fn, response_format_fn)
    COMMANDS: list[tuple[str, str]] = [
        (r"seja\s+um(?:a)?\s+(.+?)\s+e\s+(.+)", "jarvis_ask"),
        (r"analise\s+(esse|este|o|essa|esta|a)\s+(.+)", "jarvis_ask"),
        (r"como\s+(engenheiro|especialista|s[eÃª]nior)\s+de\s+(.+)", "jarvis_ask"),
        (r"fa[cÃ§]a\s+um(?:a)?\s+(.+?)\s+nesse\s+(.+)", "jarvis_ask"),
        (r"cadastrar\s+minha\s+voz", "voice_enroll_wizard"),
        (r"quais\s+dom[iÃ­]nios\s+(voc[eÃª]\s+)?conhece", "known_domains"),
        (r"pausa?\s*a?\s*autonomi", "autonomy_pause"),
        (r"retoma?\s*a?\s*autonomi", "autonomy_resume"),
        (r"para\s*a?\s*autonomi|stop\s*autonomy", "autonomy_stop"),
        (r"(qual|o que).{0,20}status", "system_status"),
        (r"modo\s*silencioso|silent\s*mode", "set_minimal_verbosity"),
        (r"modo\s*(normal|default)", "set_normal_verbosity"),
        (r"modo\s*detalhado|verbose\s*mode", "set_detailed_verbosity"),
        (r"o que (você|voce) fez hoje|what.*today", "daily_log"),
        (r"cancela?\s*(o\s*)?(job|tarefa)\s*atual?", "cancel_current_job"),
        (r"bom\s*dia|good\s*morning", "daily_briefing"),
        (r"modo\s*trabalho|work\s*mode", "work_mode"),
        (r"pausa?\s*(a\s*)?(sess[aã]o|tarefa)", "pause_work"),
        (r"status\s*do\s*dia|today.*status", "work_status"),
        (r"pula?\s*(essa|esta|a)?\s*task?|skip\s*task", "skip_task"),
    ]

    async def handle(self, text: str) -> str:
        """
        Match text against command patterns and execute the corresponding action.

        Returns:
            Response string suitable for TTS playback.
        """
        text_lower = text.strip().lower()
        for pattern, handler_name in self.COMMANDS:
            if re.search(pattern, text_lower):
                fn = getattr(self, f"_cmd_{handler_name}", None)
                if fn:
                    try:
                        result = await fn(text_lower)
                        return self._format_response(result, handler_name)
                    except Exception as exc:
                        log.error("VoiceCommandMapper: %s failed: %s", handler_name, exc)
                        return "Ocorreu um erro ao executar o comando."
        # No match — treat as free-form chat
        return ""

    def _format_response(self, raw: Any, handler: str) -> str:
        verbosity = self._get_verbosity()
        if isinstance(raw, str):
            if verbosity == "minimal":
                # Return first sentence only
                sentences = re.split(r'[.!?]', raw)
                return (sentences[0].strip() + ".") if sentences else raw
            elif verbosity == "normal":
                return raw[:300]
            else:
                return raw
        return str(raw)

    def _get_verbosity(self) -> str:
        try:
            from behavior.profile_manager import get_profile_manager
            return get_profile_manager().get().verbosity
        except Exception:
            return "normal"

    # ── Command handlers ──────────────────────────────────────────────────────

    async def _cmd_autonomy_pause(self, _: str) -> str:
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE_URL}/autonomy/pause")
        return "Autonomia pausada."

    async def _cmd_autonomy_resume(self, _: str) -> str:
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE_URL}/autonomy/resume")
        return "Autonomia retomada."

    async def _cmd_autonomy_stop(self, _: str) -> str:
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE_URL}/autonomy/stop")
        return "Loop autônomo parado."

    async def _cmd_system_status(self, _: str) -> str:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE_URL}/autonomy/status")
        d = r.json()
        state = d.get("state", "desconhecido")
        events = d.get("events_today", 0)
        actions = d.get("actions_taken", 0)
        return (
            f"Sistema {state}. {events} eventos detectados hoje, "
            f"{actions} ações tomadas."
        )

    async def _cmd_set_minimal_verbosity(self, _: str) -> str:
        async with httpx.AsyncClient() as c:
            await c.put(f"{BASE_URL}/behavior/profile",
                        json={"verbosity": "minimal"})
        return "Modo silencioso ativado."

    async def _cmd_set_normal_verbosity(self, _: str) -> str:
        async with httpx.AsyncClient() as c:
            await c.put(f"{BASE_URL}/behavior/profile",
                        json={"verbosity": "normal"})
        return "Verbosity normal."

    async def _cmd_set_detailed_verbosity(self, _: str) -> str:
        async with httpx.AsyncClient() as c:
            await c.put(f"{BASE_URL}/behavior/profile",
                        json={"verbosity": "detailed"})
        return "Modo detalhado ativado."

    async def _cmd_daily_log(self, _: str) -> str:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE_URL}/autonomy/log?limit=10")
        entries = r.json().get("log", [])
        if not entries:
            return "Nenhuma ação autônoma registrada hoje."
        done = sum(1 for e in entries if e.get("status") == "success")
        err  = sum(1 for e in entries if e.get("status") == "error")
        return f"Nas últimas ações: {done} bem-sucedidas, {err} com erro."

    async def _cmd_cancel_current_job(self, _: str) -> str:
        # Find the first active job and signal stop
        try:
            from autodev.loop import _active_jobs
            for job_id, loop in list(_active_jobs.items()):
                if loop._state and loop._state.status not in {"done", "escalated", "error"}:
                    loop._state.status = "error"
                    return f"Job {job_id} cancelado."
        except Exception as exc:
            log.debug("[voice.command_mapper] suppressed exception", exc_info=exc)
            pass
        return "Nenhum job ativo para cancelar."

    async def _cmd_daily_briefing(self, _: str) -> str:
        from autonomy.daily_briefing import DailyBriefing
        return await DailyBriefing().deliver()

    async def _cmd_work_mode(self, _: str) -> str:
        from autonomy.work_session import get_work_session
        session = get_work_session()
        wp = session._decomposer.load_today()
        if wp:
            import asyncio
            asyncio.create_task(session.start())
            return "Modo trabalho ativado. Executando o workplan do dia."
        return "Nenhum workplan para hoje. Diga o objetivo do dia primeiro."

    async def _cmd_pause_work(self, _: str) -> str:
        from autonomy.work_session import get_work_session
        await get_work_session().pause()
        return "Sessão de trabalho pausada."

    async def _cmd_jarvis_ask(self, text: str) -> str:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(f"{BASE_URL}/jarvis/ask", data={"text": text})
        d = r.json()
        return d.get("response") or d.get("message") or "Analise concluida."

    async def _cmd_voice_enroll_wizard(self, _: str) -> str:
        return "Cadastro de voz iniciado. Envie cinco amostras pelo endpoint /voice/enroll."

    async def _cmd_known_domains(self, _: str) -> str:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE_URL}/expertise/domains")
        domains = r.json().get("domains", [])
        if not domains:
            return "Ainda nao aprendi dominios dinamicos."
        names = ", ".join(d.get("domain", "") for d in domains[:10])
        return f"Conheco estes dominios: {names}."

    async def _cmd_work_status(self, _: str) -> str:
        from autonomy.work_session import get_work_session
        st = get_work_session().status()
        done = st.get("done", 0)
        total = st.get("total_tasks", 0)
        goal = st.get("goal", "não definido")
        return f"Objetivo: {goal}. {done} de {total} tarefas concluídas."

    async def _cmd_skip_task(self, _: str) -> str:
        from autonomy.work_session import get_work_session
        get_work_session().skip_current_task()
        return "Tarefa pulada. Avançando para a próxima."
