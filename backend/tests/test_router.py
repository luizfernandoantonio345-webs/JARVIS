"""
Testes do roteador semântico.

O ponto central: o roteamento por substring erra em casos reais de uso, e a
camada do modelo precisa corrigir sem que o sistema fique dependente dela —
se o modelo cair, a rede de palavra-chave continua respondendo.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import router as rt  # noqa: E402
from core.router import SmartRouter  # noqa: E402

REGRAS = {
    "system_agent": ["temperatura", "cpu", "memória ram"],
    "file_agent": ["listar arquivos", "criar arquivo"],
    "time_agent": ["que horas"],
}


# ── Camada 1: padrão ancorado ─────────────────────────────────────────────────

def test_padrao_resolve_caso_inequivoco_sem_chamar_modelo():
    r = SmartRouter(REGRAS, use_llm=False)
    d = r.route("que horas são")
    assert d.agent == "time_agent"
    assert d.method == "pattern"
    assert d.confidence >= 0.9


def test_padrao_exige_borda_de_palavra():
    """'uso da cpu' casa; uma palavra que apenas contém 'cpu' não deveria."""
    r = SmartRouter({}, use_llm=False)
    assert r.route("uso da cpu agora").agent == "system_agent"
    assert r.route("falar sobre acpuntura").agent == "chat_agent"


# ── Camada 2: modelo ──────────────────────────────────────────────────────────

def test_modelo_corrige_o_erro_classico_do_substring(monkeypatch):
    """
    'temperatura em São Paulo' é clima, não sensor do processador.
    O substring erra; o modelo acerta.
    """
    monkeypatch.setattr(rt, "_by_llm",
                        lambda msg: rt.RouteDecision("web_agent", 0.8, "llm", "mock"))
    r = SmartRouter(REGRAS, use_llm=True)
    d = r.route("qual a temperatura em São Paulo hoje")
    assert d.agent == "web_agent"
    assert d.method == "llm"


def test_sem_modelo_o_substring_erraria(monkeypatch):
    """Registra o comportamento antigo, para o teste acima ter significado."""
    r = SmartRouter(REGRAS, use_llm=False)
    assert r.route("qual a temperatura em São Paulo hoje").agent == "system_agent"


def test_resposta_suja_do_modelo_e_aceita(monkeypatch):
    """Modelo pequeno responde 'Agente: code_agent.' em vez do nome puro."""
    monkeypatch.setattr("services.llm_service.call_llm",
                        lambda *a, **k: "Agente: code_agent.", raising=False)
    assert rt._by_llm("refatora essa função").agent == "code_agent"


def test_resposta_irreconhecivel_cai_para_proxima_camada(monkeypatch):
    monkeypatch.setattr("services.llm_service.call_llm",
                        lambda *a, **k: "sei lá", raising=False)
    assert rt._by_llm("qualquer coisa") is None


def test_falha_do_modelo_nao_derruba_o_roteamento(monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("ollama offline")

    monkeypatch.setattr("services.llm_service.call_llm", explode, raising=False)
    r = SmartRouter(REGRAS, use_llm=True)
    d = r.route("listar arquivos da pasta")
    assert d.agent == "file_agent"       # rede de segurança respondeu
    assert d.method == "keyword"


# ── Camada 3 e padrão ─────────────────────────────────────────────────────────

def test_mensagem_sem_encaixe_vai_para_chat():
    r = SmartRouter(REGRAS, use_llm=False)
    d = r.route("me conta uma curiosidade sobre o oceano")
    assert d.agent == "chat_agent"
    assert d.method == "default"


# ── Cache ─────────────────────────────────────────────────────────────────────

def test_cache_evita_classificar_a_mesma_frase_duas_vezes(monkeypatch):
    chamadas = {"n": 0}

    def contar(msg):
        chamadas["n"] += 1
        return rt.RouteDecision("code_agent", 0.8, "llm", "mock")

    monkeypatch.setattr(rt, "_by_llm", contar)
    r = SmartRouter({}, use_llm=True)
    r.route("escreve um teste pra essa função")
    r.route("escreve um teste pra essa função")
    assert chamadas["n"] == 1


def test_cache_nao_cresce_sem_limite(monkeypatch):
    monkeypatch.setattr(rt, "_by_llm", lambda m: None)
    r = SmartRouter({}, use_llm=True)
    for i in range(600):
        r.route(f"mensagem distinta número {i}")
    assert len(r._cache) <= 512


# ── Catálogo ──────────────────────────────────────────────────────────────────

def test_todo_agente_tem_descricao_util():
    """A descrição é o único material que o modelo tem para decidir."""
    for nome, desc in rt.AGENT_DESCRIPTIONS.items():
        assert len(desc) > 25, f"{nome} tem descrição curta demais para orientar o modelo"


# ── Integração com o orquestrador ─────────────────────────────────────────────

def test_orquestrador_mantem_assinatura_antiga():
    from agents.master_orchestrator import MasterOrchestrator
    orch = MasterOrchestrator()
    os.environ["JARVIS_ROUTER_LLM"] = "false"
    try:
        resultado = orch.route("que horas são")
        assert isinstance(resultado, str)
        assert resultado == "time_agent"
    finally:
        os.environ.pop("JARVIS_ROUTER_LLM", None)


def test_orquestrador_expoe_o_motivo_da_decisao():
    from agents.master_orchestrator import MasterOrchestrator
    orch = MasterOrchestrator()
    os.environ["JARVIS_ROUTER_LLM"] = "false"
    try:
        d = orch.route_decision("que horas são")
        assert d.agent == "time_agent"
        assert d.method
        assert d.reason
    finally:
        os.environ.pop("JARVIS_ROUTER_LLM", None)
