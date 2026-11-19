"""
Testes da memória ligada ao agente.

A regra que atravessa tudo aqui: memória que falha NUNCA pode derrubar a
tarefa. Banco travado, embedding indisponível, ChromaDB fora do ar — nada
disso pode impedir o agente de trabalhar. Memória é melhoria, não requisito.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import tools_memory as tm  # noqa: E402
from core.tool_registry import all_tools, get_tool  # noqa: E402


# ── Registro ──────────────────────────────────────────────────────────────────

def test_ferramentas_de_memoria_registradas():
    nomes = {t.name for t in all_tools()}
    for esperado in ("recall", "remember", "remember_preference", "search_knowledge"):
        assert esperado in nomes


def test_leitura_e_escrita_marcadas_corretamente():
    assert get_tool("recall").read_only is True
    assert get_tool("search_knowledge").read_only is True
    assert get_tool("remember").read_only is False
    assert get_tool("remember_preference").read_only is False


# ── Sessão ────────────────────────────────────────────────────────────────────

def test_sessao_padrao_quando_nao_informada():
    tm.definir_sessao(None)
    assert tm.sessao_atual() == tm.SESSAO_PADRAO


def test_sessao_e_respeitada():
    tm.definir_sessao("projeto-x")
    assert tm.sessao_atual() == "projeto-x"
    tm.definir_sessao(None)


# ── recall ────────────────────────────────────────────────────────────────────

def test_recall_junta_preferencias_contexto_e_historico(monkeypatch):
    import services.memory_service as ms
    monkeypatch.setattr(ms, "get_relevant_preferences",
                        lambda s, q, limit=5: {"formato": "respostas curtas"})
    monkeypatch.setattr(ms, "get_relevant_project_context",
                        lambda s, q, limit=3: {"stack": "FastAPI + Postgres"})
    monkeypatch.setattr(ms, "get_relevant_memory",
                        lambda s, q, limit=5: [("qual o banco?", "Postgres")])

    saida = tm.recall("banco de dados do projeto")
    assert "respostas curtas" in saida
    assert "FastAPI + Postgres" in saida
    assert "Postgres" in saida


def test_recall_sem_nada_diz_isso_claramente(monkeypatch):
    import services.memory_service as ms
    monkeypatch.setattr(ms, "get_relevant_preferences", lambda *a, **k: {})
    monkeypatch.setattr(ms, "get_relevant_project_context", lambda *a, **k: {})
    monkeypatch.setattr(ms, "get_relevant_memory", lambda *a, **k: [])

    assert tm.recall("assunto nunca visto").startswith("Nada na memória")


def test_falha_parcial_nao_perde_o_resto(monkeypatch):
    """Se preferências quebram, histórico ainda deve voltar."""
    import services.memory_service as ms

    def explode(*a, **k):
        raise RuntimeError("banco travado")

    monkeypatch.setattr(ms, "get_relevant_preferences", explode)
    monkeypatch.setattr(ms, "get_relevant_project_context", explode)
    monkeypatch.setattr(ms, "get_relevant_memory",
                        lambda s, q, limit=5: [("pergunta", "resposta")])

    saida = tm.recall("algo")
    assert "resposta" in saida


# ── remember ──────────────────────────────────────────────────────────────────

def test_remember_grava_e_confirma(monkeypatch):
    import services.memory_service as ms
    gravado = {}
    monkeypatch.setattr(ms, "save_memory",
                        lambda sid, msg, resp, action="chat": gravado.update(
                            sid=sid, msg=msg, action=action))

    r = tm.remember("o deploy é na Hetzner", "decidido hoje")
    assert r.startswith("OK")
    assert gravado["msg"] == "o deploy é na Hetzner"
    assert gravado["action"] == "remember"


def test_remember_recusa_vazio():
    assert tm.remember("   ").startswith("ERRO")


def test_remember_erro_vira_texto_legivel(monkeypatch):
    import services.memory_service as ms

    def explode(*a, **k):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(ms, "save_memory", explode)
    r = tm.remember("algo")
    assert r.startswith("ERRO")
    assert "disco cheio" in r


# ── preferências ──────────────────────────────────────────────────────────────

def test_preferencia_exige_key_e_value():
    assert tm.remember_preference("", "x").startswith("ERRO")
    assert tm.remember_preference("x", "").startswith("ERRO")


def test_preferencia_grava(monkeypatch):
    import services.memory_service as ms
    capturado = {}
    monkeypatch.setattr(ms, "set_preference",
                        lambda sid, k, v, confidence=0.85: capturado.update(k=k, v=v))
    r = tm.remember_preference("formato_resposta", "curto e direto")
    assert r.startswith("OK")
    assert capturado["k"] == "formato_resposta"


# ── contexto automático ───────────────────────────────────────────────────────

def test_contexto_vazio_quando_nao_ha_memoria(monkeypatch):
    """Bloco oco no prompt gasta contexto e não ajuda."""
    monkeypatch.setattr(tm, "recall", lambda q, limit=4: "Nada na memória sobre: x")
    assert tm.contexto_inicial("objetivo") == ""


def test_contexto_vazio_quando_memoria_falha(monkeypatch):
    monkeypatch.setattr(tm, "recall", lambda q, limit=4: "ERRO: memória indisponível")
    assert tm.contexto_inicial("objetivo") == ""


def test_contexto_vem_rotulado_para_o_modelo_saber_o_que_e(monkeypatch):
    monkeypatch.setattr(tm, "recall", lambda q, limit=4: "Preferências:\n  - x: y")
    ctx = tm.contexto_inicial("objetivo")
    assert "x: y" in ctx
    assert "ignore se não for pertinente" in ctx


# ── integração com o laço ─────────────────────────────────────────────────────

def test_memoria_quebrada_nao_derruba_o_agente(monkeypatch):
    """O requisito mais importante deste módulo."""
    from core import agent_loop

    def explode(*a, **k):
        raise RuntimeError("memória fora do ar")

    monkeypatch.setattr(agent_loop.tools_memory, "contexto_inicial", explode)
    monkeypatch.setattr(agent_loop, "_one_turn",
                        lambda msgs: {"text": "pronto", "calls": [], "ids": [], "raw": {}})

    r = agent_loop.run_agent("faça algo", use_memory=True)
    assert r.ok
    assert r.final_text == "pronto"


def test_use_memory_false_nao_toca_na_memoria(monkeypatch):
    from core import agent_loop
    chamou = {"n": 0}

    def contar(*a, **k):
        chamou["n"] += 1
        return ""

    monkeypatch.setattr(agent_loop.tools_memory, "contexto_inicial", contar)
    monkeypatch.setattr(agent_loop, "_one_turn",
                        lambda msgs: {"text": "ok", "calls": [], "ids": [], "raw": {}})

    agent_loop.run_agent("faça algo", use_memory=False)
    assert chamou["n"] == 0


def test_contexto_entra_antes_do_objetivo(monkeypatch):
    """O modelo precisa ler o contexto antes de saber o que fazer com ele."""
    from core import agent_loop

    monkeypatch.setattr(agent_loop.tools_memory, "contexto_inicial",
                        lambda goal, sid: "CONTEXTO_MARCADOR")
    capturado = {}

    def capturar(msgs):
        capturado["msgs"] = list(msgs)
        return {"text": "ok", "calls": [], "ids": [], "raw": {}}

    monkeypatch.setattr(agent_loop, "_one_turn", capturar)
    agent_loop.run_agent("OBJETIVO_MARCADOR", use_memory=True)

    textos = [str(m.get("content")) for m in capturado["msgs"]]
    assert any("CONTEXTO_MARCADOR" in t for t in textos)
    idx_ctx = next(i for i, t in enumerate(textos) if "CONTEXTO_MARCADOR" in t)
    idx_obj = next(i for i, t in enumerate(textos) if "OBJETIVO_MARCADOR" in t)
    assert idx_ctx < idx_obj
