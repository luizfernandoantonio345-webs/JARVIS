import logging, asyncio, httpx
log = logging.getLogger("jarvis.research")

class DeepResearcher:
    def __init__(self):
        self.active = False
        self.current_query = ""
        self.steps = []

    async def research(self, query: str, session_id: str, on_update=None) -> str:
        self.active = True
        self.current_query = query
        self.steps = []
        log.info("[RESEARCH] Iniciando: %s", query[:60])

        async def step(name: str, result: str):
            self.steps.append({"step": name, "result": result[:300]})
            if on_update:
                try:
                    await on_update({"step": name, "preview": result[:100]})
                except Exception:
                    pass

        try:
            from backend.experience.engine import get_experience
            similar = get_experience().find(query, limit=3)
            if similar:
                exp_txt = "\n".join([f"- {e['title']}: {e['solution'][:100]}" for e in similar])
                await step("experiencias_anteriores", exp_txt)

            analysis = await self._analyze(query)
            await step("analise", analysis)

            gh = await self._search_github(query)
            if gh:
                await step("github", gh)

            solution = await self._synthesize(query, analysis, similar, gh)
            await step("sintese", solution)

            get_experience().save(
                category="research", title=query[:80],
                problem=query, solution=solution,
                tags=["deep_research", session_id]
            )

            from backend.core.event_bus import get_event_bus
            await get_event_bus().emit("research.completed", {"query": query[:80], "steps": len(self.steps), "session": session_id})

            return solution
        finally:
            self.active = False

    async def _analyze(self, query: str) -> str:
        try:
            from backend.services.llm_service import call_llm
            return await call_llm([
                {"role": "system", "content": "Analista tecnico senior. Identifique causa raiz, abordagens, riscos. Seja conciso."},
                {"role": "user", "content": query}
            ])
        except Exception as e:
            return f"Analise indisponivel: {e}"

    async def _search_github(self, query: str) -> str:
        try:
            clean = query[:60].replace(" ", "+")
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(
                    f"https://api.github.com/search/repositories?q={clean}&sort=stars&per_page=3",
                    headers={"Accept": "application/vnd.github.v3+json"}
                )
                if r.status_code == 200:
                    items = r.json().get("items", [])[:3]
                    return "\n".join([f"- {i['full_name']} [{i['stargazers_count']}]: {(i.get('description') or '')[:60]}" for i in items])
        except Exception as e:
            log.debug("[RESEARCH] GitHub: %s", e)
        return ""

    async def _synthesize(self, query, analysis, similar, github) -> str:
        try:
            from backend.services.llm_service import call_llm
            ctx = [f"Problema: {query}", f"Analise: {analysis[:400]}"]
            if similar:
                ctx.append("Experiencias: " + "; ".join([e["title"] for e in similar]))
            if github:
                ctx.append(f"GitHub: {github[:300]}")
            return await call_llm([
                {"role": "system", "content": "Arquiteto senior de IA. Sintetize solucao clara e implementavel em portugues. Seja direto e tecnico."},
                {"role": "user", "content": "\n".join(ctx)}
            ])
        except Exception as e:
            return f"Sintese indisponivel: {e}"

    def status(self) -> dict:
        return {"active": self.active, "query": self.current_query[:80], "steps_done": len(self.steps), "steps": self.steps[-5:]}

_res = None
def get_researcher() -> DeepResearcher:
    global _res
    if _res is None:
        _res = DeepResearcher()
    return _res
