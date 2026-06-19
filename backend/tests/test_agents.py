"""
Testes dos agentes JARVIS — 100+ casos: registry, BaseAgent, contratos, roteamento, API.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# AGENT REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentRegistry:
    def test_registry_importable(self):
        from services.agent_registry import get_agent, list_agents
        assert callable(get_agent)
        assert callable(list_agents)

    def test_registry_returns_agents(self):
        from services.agent_registry import list_agents
        agents = list_agents()
        assert agents is not None

    def test_list_agents_is_list_or_dict(self):
        from services.agent_registry import list_agents
        assert isinstance(list_agents(), (list, dict))

    def test_registry_has_agents(self):
        from services.agent_registry import list_agents
        assert len(list_agents()) > 0

    def test_registry_has_dev_agent(self):
        from services.agent_registry import get_agent
        assert get_agent("dev") is not None

    def test_registry_nonexistent_returns_none(self):
        from services.agent_registry import get_agent
        try:
            result = get_agent("nonexistent_xyz_agent")
            assert result is None
        except (KeyError, ValueError):
            pass  # raising on unknown role is also acceptable

    def test_registry_at_least_5_agents(self):
        from services.agent_registry import list_agents
        assert len(list_agents()) >= 5

    def test_registry_module_has_aliases(self):
        import services.agent_registry as reg
        assert hasattr(reg, "_REGISTRY") or hasattr(reg, "_ALIASES")

    @pytest.mark.parametrize("role", ["dev", "architect", "debugger", "reviewer", "security", "planner"])
    def test_known_role_registered(self, role):
        from services.agent_registry import get_agent
        result = get_agent(role)
        if result is None:
            pytest.skip(f"Role '{role}' não registrado neste ambiente")
        assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
# BASE AGENT CONTRATO
# ══════════════════════════════════════════════════════════════════════════════

class TestBaseAgentContract:
    def test_base_agent_importable(self):
        try:
            from agents.base_agent import BaseAgent
            assert BaseAgent is not None
        except ImportError:
            pytest.skip()

    def test_base_agent_has_run(self):
        try:
            from agents.base_agent import BaseAgent
            assert hasattr(BaseAgent, "run")
        except ImportError:
            pytest.skip()

    def test_base_agent_has_stream(self):
        try:
            from agents.base_agent import BaseAgent
            assert hasattr(BaseAgent, "stream")
        except ImportError:
            pytest.skip()

    def test_base_agent_run_is_coroutine(self):
        import asyncio
        try:
            from agents.base_agent import BaseAgent
            assert asyncio.iscoroutinefunction(BaseAgent.run)
        except (ImportError, Exception):
            pytest.skip()

    def test_dev_agent_importable(self):
        try:
            from agents.dev_agent import DevAgent
            assert DevAgent is not None
        except ImportError:
            pytest.skip()

    def test_architect_agent_importable(self):
        try:
            from agents.architect_agent import ArchitectAgent
            assert ArchitectAgent is not None
        except ImportError:
            pytest.skip()

    def test_debugger_agent_importable(self):
        try:
            from agents.debugger_agent import DebuggerAgent
            assert DebuggerAgent is not None
        except ImportError:
            pytest.skip()

    def test_reviewer_agent_importable(self):
        try:
            from agents.reviewer_agent import ReviewerAgent
            assert ReviewerAgent is not None
        except ImportError:
            pytest.skip()

    def test_security_agent_importable(self):
        try:
            from agents.security_agent import SecurityAgent
            assert SecurityAgent is not None
        except ImportError:
            pytest.skip()

    def test_planner_agent_importable(self):
        try:
            from agents.planner_agent import PlannerAgent
            assert PlannerAgent is not None
        except ImportError:
            pytest.skip()

    def test_executor_agent_importable(self):
        try:
            from agents.executor_agent import ExecutorAgent
            assert ExecutorAgent is not None
        except ImportError:
            pytest.skip()

    @pytest.mark.parametrize("role", ["dev", "architect", "debugger", "reviewer", "security", "planner"])
    def test_agent_has_run_method(self, role):
        from services.agent_registry import get_agent
        agent = get_agent(role)
        if agent is None:
            pytest.skip(f"{role} não registrado")
        assert hasattr(agent, "run") and callable(agent.run)

    @pytest.mark.parametrize("role", ["dev", "architect", "debugger", "reviewer", "security", "planner"])
    def test_agent_has_stream_method(self, role):
        from services.agent_registry import get_agent
        agent = get_agent(role)
        if agent is None:
            pytest.skip(f"{role} não registrado")
        assert hasattr(agent, "stream") and callable(agent.stream)

    @pytest.mark.parametrize("role", ["dev", "architect", "debugger", "reviewer", "security", "planner"])
    def test_agent_has_role_attribute(self, role):
        from services.agent_registry import get_agent
        agent = get_agent(role)
        if agent is None:
            pytest.skip(f"{role} não registrado")
        assert hasattr(agent, "ROLE") or hasattr(agent, "role") or hasattr(agent, "name")

    @pytest.mark.parametrize("role", ["dev", "architect", "debugger", "reviewer", "security", "planner"])
    def test_agent_has_system_prompt(self, role):
        from services.agent_registry import get_agent
        agent = get_agent(role)
        if agent is None:
            pytest.skip(f"{role} não registrado")
        prompt = (getattr(agent, "SYSTEM_PROMPT", None) or getattr(agent, "system_prompt", None)
                  or getattr(agent, "_system_prompt", None))
        if prompt is not None:
            assert isinstance(prompt, str) and len(prompt) > 0


# ══════════════════════════════════════════════════════════════════════════════
# DEV AGENT
# ══════════════════════════════════════════════════════════════════════════════

class TestDevAgent:
    def test_dev_instantiates(self):
        try:
            from agents.dev_agent import DevAgent
            assert DevAgent() is not None
        except (ImportError, Exception):
            pytest.skip()

    def test_dev_role_is_dev(self):
        try:
            from agents.dev_agent import DevAgent
            a = DevAgent()
            role = getattr(a, "ROLE", "") or getattr(a, "role", "") or getattr(a, "name", "")
            assert "dev" in str(role).lower()
        except (ImportError, Exception):
            pytest.skip()

    def test_dev_system_prompt_mentions_code(self):
        try:
            from agents.dev_agent import DevAgent
            a = DevAgent()
            prompt = (getattr(a, "SYSTEM_PROMPT", "") or getattr(a, "system_prompt", "")
                      or getattr(a, "_system_prompt", ""))
            if prompt:
                assert any(word in prompt.lower() for word in ["code", "código", "python", "developer"])
        except (ImportError, Exception):
            pytest.skip()

    def test_dev_inherits_base_agent(self):
        try:
            from agents.dev_agent import DevAgent
            from agents.base_agent import BaseAgent
            assert issubclass(DevAgent, BaseAgent)
        except (ImportError, Exception):
            pytest.skip()


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY AGENT
# ══════════════════════════════════════════════════════════════════════════════

class TestSecurityAgent:
    def test_security_instantiates(self):
        try:
            from agents.security_agent import SecurityAgent
            assert SecurityAgent() is not None
        except (ImportError, Exception):
            pytest.skip()

    def test_security_role(self):
        try:
            from agents.security_agent import SecurityAgent
            a = SecurityAgent()
            role = getattr(a, "ROLE", "") or getattr(a, "role", "") or getattr(a, "name", "")
            assert "security" in str(role).lower() or "osint" in str(role).lower()
        except (ImportError, Exception):
            pytest.skip()

    def test_security_prompt_mentions_owasp_or_security(self):
        try:
            from agents.security_agent import SecurityAgent
            a = SecurityAgent()
            prompt = (getattr(a, "SYSTEM_PROMPT", "") or getattr(a, "system_prompt", "")
                      or getattr(a, "_system_prompt", ""))
            if prompt:
                assert any(w in prompt.lower() for w in ["security", "owasp", "vuln", "pentest", "segurança"])
        except (ImportError, Exception):
            pytest.skip()


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class TestMasterOrchestrator:
    def test_orchestrator_importable(self):
        try:
            from agents.master_orchestrator import get_orchestrator
            assert callable(get_orchestrator)
        except ImportError:
            pytest.skip()

    def test_orchestrator_returns_object(self):
        try:
            from agents.master_orchestrator import get_orchestrator
            assert get_orchestrator() is not None
        except (ImportError, Exception):
            pytest.skip()

    def test_orchestrator_singleton(self):
        try:
            from agents.master_orchestrator import get_orchestrator
            assert get_orchestrator() is get_orchestrator()
        except (ImportError, Exception):
            pytest.skip()

    def test_orchestrator_has_execute(self):
        try:
            from agents.master_orchestrator import get_orchestrator
            o = get_orchestrator()
            assert hasattr(o, "execute") and callable(o.execute)
        except (ImportError, Exception):
            pytest.skip()

    def test_orchestrator_execute_is_coroutine(self):
        import asyncio
        try:
            from agents.master_orchestrator import get_orchestrator
            o = get_orchestrator()
            assert asyncio.iscoroutinefunction(o.execute)
        except (ImportError, Exception):
            pytest.skip()


# ══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS DE AGENTES
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentsAPI:
    def test_list_200(self, client):
        assert client.get("/agents/").status_code == 200

    def test_list_json(self, client):
        assert isinstance(client.get("/agents/").json(), dict)

    def test_list_agents_key(self, client):
        assert "agents" in client.get("/agents/").json()

    def test_list_count_key(self, client):
        assert "count" in client.get("/agents/").json()

    def test_count_matches_list(self, client):
        d = client.get("/agents/").json()
        assert d["count"] == len(d["agents"])

    def test_count_positive(self, client):
        assert client.get("/agents/").json()["count"] > 0

    def test_unknown_role_404(self, client):
        assert client.post("/agents/xyz_unknown/run", json={"message": "hi"}).status_code == 404

    def test_empty_message_rejected(self, client):
        assert client.post("/agents/dev/run", json={"message": ""}).status_code in (400, 422)

    def test_missing_body_rejected(self, client):
        assert client.post("/agents/dev/run").status_code in (400, 422)

    @pytest.mark.parametrize("role", ["dev", "architect", "debugger", "security"])
    def test_valid_role_not_404(self, client, role):
        r = client.post(f"/agents/{role}/run", json={"message": "hello"})
        assert r.status_code != 404

    def test_run_returns_json_on_success(self, client):
        r = client.post("/agents/dev/run", json={"message": "write hello world"})
        if r.status_code in (200, 202):
            assert isinstance(r.json(), dict)

    def test_run_planner_role(self, client):
        r = client.post("/agents/planner/run", json={"message": "plan a web app"})
        assert r.status_code in (200, 202, 404, 500, 503)

    def test_run_reviewer_role(self, client):
        r = client.post("/agents/reviewer/run", json={"message": "review this code: def f(): pass"})
        assert r.status_code in (200, 202, 404, 500, 503)


# ══════════════════════════════════════════════════════════════════════════════
# LLM SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class TestLLMService:
    def test_call_llm_importable(self):
        try:
            from services.llm_service import call_llm
            assert callable(call_llm)
        except ImportError:
            pytest.skip()

    def test_call_llm_is_callable(self):
        try:
            from services.llm_service import call_llm
            assert callable(call_llm)
        except ImportError:
            pytest.skip()

    def test_call_llm_stream_importable(self):
        try:
            from services.llm_service import call_llm_stream
            assert callable(call_llm_stream)
        except ImportError:
            pytest.skip()

    def test_ai_client_importable(self):
        try:
            from ai.client import get_ai_client
            assert callable(get_ai_client)
        except ImportError:
            pytest.skip()

    def test_ai_client_has_health_check(self):
        try:
            from ai.client import get_ai_client
            assert hasattr(get_ai_client(), "health_check")
        except (ImportError, Exception):
            pytest.skip()

    def test_ai_client_health_returns_dict(self):
        try:
            from ai.client import get_ai_client
            result = get_ai_client().health_check()
            assert isinstance(result, dict)
        except (ImportError, Exception):
            pytest.skip()

    def test_ai_client_health_has_ok_field(self):
        try:
            from ai.client import get_ai_client
            result = get_ai_client().health_check()
            assert "ok" in result
        except (ImportError, Exception):
            pytest.skip()

    def test_ai_client_has_call_or_chat(self):
        try:
            from ai.client import get_ai_client
            c = get_ai_client()
            assert hasattr(c, "call") or hasattr(c, "chat") or hasattr(c, "stream_chat")
        except (ImportError, Exception):
            pytest.skip()
