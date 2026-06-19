"""
Testes para os agentes especializados do JARVIS.
Testa o registry, aliases, e que todos os agentes têm ROLE e SYSTEM_PROMPT.
Não faz chamadas ao LLM (testes unitários puros).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ── Agent Registry ─────────────────────────────────────────────────────────────

def test_registry_loads_without_error():
    from services.agent_registry import list_agents
    agents = list_agents()
    assert isinstance(agents, list)
    assert len(agents) >= 6


def test_all_expected_roles_registered():
    from services.agent_registry import list_agents
    agents = list_agents()
    for expected in ["dev", "architect", "debugger", "reviewer", "security", "planner"]:
        assert expected in agents, f"Agente '{expected}' não encontrado no registry"


def test_get_agent_by_canonical_name():
    from services.agent_registry import get_agent
    agent = get_agent("dev")
    assert agent is not None
    assert agent.ROLE == "dev"


def test_get_agent_by_alias():
    from services.agent_registry import get_agent
    agent = get_agent("coder")
    assert agent.ROLE == "dev"


def test_get_agent_alias_debug():
    from services.agent_registry import get_agent
    agent = get_agent("debug")
    assert agent.ROLE == "debugger"


def test_get_agent_alias_arch():
    from services.agent_registry import get_agent
    agent = get_agent("arch")
    assert agent.ROLE == "architect"


def test_get_unknown_agent_raises_key_error():
    from services.agent_registry import get_agent
    with pytest.raises(KeyError):
        get_agent("definitely_not_an_agent_xyz")


def test_agent_info_returns_list_of_dicts():
    from services.agent_registry import agent_info
    info = agent_info()
    assert isinstance(info, list)
    for item in info:
        assert "role" in item
        assert "class" in item
        assert "description" in item


# ── BaseAgent contract ─────────────────────────────────────────────────────────

def test_all_agents_have_role():
    from services.agent_registry import _REGISTRY
    for role, agent in _REGISTRY.items():
        assert hasattr(agent, "ROLE"), f"{agent.__class__.__name__} sem ROLE"
        assert agent.ROLE, f"{agent.__class__.__name__} ROLE vazio"


def test_all_agents_have_system_prompt():
    from services.agent_registry import _REGISTRY
    for role, agent in _REGISTRY.items():
        assert hasattr(agent, "SYSTEM_PROMPT"), f"{agent.__class__.__name__} sem SYSTEM_PROMPT"
        assert len(agent.SYSTEM_PROMPT) > 50, f"{agent.__class__.__name__} SYSTEM_PROMPT muito curto"


def test_all_agents_have_run_method():
    from services.agent_registry import _REGISTRY
    for role, agent in _REGISTRY.items():
        assert callable(getattr(agent, "run", None)), f"{agent.__class__.__name__} sem método run()"


def test_all_agents_have_stream_method():
    from services.agent_registry import _REGISTRY
    for role, agent in _REGISTRY.items():
        assert callable(getattr(agent, "stream", None)), f"{agent.__class__.__name__} sem método stream()"


# ── Agents específicos ─────────────────────────────────────────────────────────

def test_reviewer_agent_has_review_method():
    from agents.reviewer_agent import ReviewerAgent
    agent = ReviewerAgent()
    assert callable(getattr(agent, "review", None))


def test_architect_agent_role():
    from agents.architect_agent import ArchitectAgent
    agent = ArchitectAgent()
    assert agent.ROLE == "architect"


def test_debugger_agent_role():
    from agents.debugger_agent import DebuggerAgent
    agent = DebuggerAgent()
    assert agent.ROLE == "debugger"


def test_dev_agent_role():
    from agents.dev_agent import DevAgent
    agent = DevAgent()
    assert agent.ROLE == "dev"


def test_security_agent_role():
    from agents.security_agent import SecurityAgent
    agent = SecurityAgent()
    assert agent.ROLE == "security"


# ── Build messages ─────────────────────────────────────────────────────────────

def test_build_messages_no_history():
    from agents.dev_agent import DevAgent
    agent = DevAgent()
    msgs = agent._build_messages("hello", None)
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "hello"


def test_build_messages_with_history():
    from agents.dev_agent import DevAgent
    agent = DevAgent()
    history = [
        {"role": "user", "content": "pergunta anterior"},
        {"role": "assistant", "content": "resposta anterior"},
    ]
    msgs = agent._build_messages("nova pergunta", history)
    assert len(msgs) == 4  # system + 2 history + user
    assert msgs[1]["content"] == "pergunta anterior"
    assert msgs[-1]["content"] == "nova pergunta"


def test_build_messages_filters_invalid_roles():
    from agents.dev_agent import DevAgent
    agent = DevAgent()
    history = [
        {"role": "user", "content": "ok"},
        {"role": "invalid_role", "content": "ignorar"},
    ]
    msgs = agent._build_messages("test", history)
    roles = [m["role"] for m in msgs]
    assert "invalid_role" not in roles
