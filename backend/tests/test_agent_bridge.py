"""
Testes da ponte entre o laço de agente e o WebSocket.

Nada aqui fala com LLM: `run_agent` é substituído por dublês que exercitam
justamente o que é difícil — evento nascendo na thread e chegando no loop,
confirmação bloqueando a thread até a resposta vir pela rede, e o estouro de
tempo quando a resposta nunca vem.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import agent_bridge as ab                      # noqa: E402
from core.agent_loop import AgentResult                   # noqa: E402
from core.agent_safety import PedidoConfirmacao           # noqa: E402


# ── Detector de tarefa ────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "cria um endpoint de login no backend",
    "conserta o teste que está quebrando",
    "roda os testes e me diz o que falhou",
    "lê o arquivo backend/main.py",
    "procura onde está a função run_agent",
    "faz um commit com o que mudou",
    "refatora o router para ficar mais limpo",
    "analisa o tool_registry.py",
    "instala o httpx no venv",
    "implement a retry in the http client",
])
def test_pedido_de_trabalho_usa_ferramentas(texto):
    assert ab.precisa_de_ferramentas(texto), f"deveria usar ferramentas: {texto}"


@pytest.mark.parametrize("texto", [
    "oi", "olá", "bom dia", "tudo bem?", "valeu", "obrigado",
    "jarvis", "hey jarvis", "ok", "sim", "não", "beleza",
    "", "   ", "quem é você?", "me conta uma piada",
    "o que você acha de python?",
])
def test_conversa_nao_usa_ferramentas(texto):
    assert not ab.precisa_de_ferramentas(texto), f"não deveria: {texto}"


# ── Protocolo de resposta ─────────────────────────────────────────────────────

def test_le_resposta_de_confirmacao():
    assert ab.ler_resposta_confirmacao("__confirm__:abc123:yes") == ("abc123", True)
    assert ab.ler_resposta_confirmacao("__confirm__:abc123:no") == ("abc123", False)
    assert ab.ler_resposta_confirmacao("__confirm__:abc123:sim") == ("abc123", True)
    assert ab.ler_resposta_confirmacao("__confirm__:abc123:nao") == ("abc123", False)


def test_mensagem_normal_nao_e_confirmacao():
    assert ab.ler_resposta_confirmacao("roda os testes") is None
    assert ab.ler_resposta_confirmacao("__confirm__:abc123") is None
    assert ab.ler_resposta_confirmacao("") is None


# ── Eventos atravessando a thread ─────────────────────────────────────────────

def test_eventos_chegam_na_ordem(monkeypatch):
    def dubl(objetivo, **kw):
        emit = kw["on_event"]
        emit("thinking", {"text": "vou ler o arquivo", "iteration": 1})
        emit("tool_call", {"name": "read_file", "arguments": {"path": "x.py"}})
        emit("tool_result", {"name": "read_file", "error": False, "result": "ok"})
        emit("done", {"reason": "completed", "iterations": 1})
        return AgentResult(final_text="pronto", stopped_reason="completed")

    monkeypatch.setattr(ab, "run_agent", dubl)
    recebidas = []

    async def enviar(m):
        recebidas.append(m)

    async def cenario():
        ponte = ab.PonteAgente(enviar=enviar)
        return await ponte.executar("lê o arquivo x.py")

    resultado = asyncio.run(cenario())
    assert resultado.final_text == "pronto"
    eventos = [m["event"] for m in recebidas if m["type"] == "agent_event"]
    assert eventos == ["thinking", "tool_call", "tool_result", "done"]


def test_cliente_caido_nao_derruba_o_laco(monkeypatch):
    def dubl(objetivo, **kw):
        for i in range(5):
            kw["on_event"]("thinking", {"text": f"passo {i}", "iteration": i})
        return AgentResult(final_text="terminei mesmo assim")

    monkeypatch.setattr(ab, "run_agent", dubl)

    async def enviar(_m):
        raise ConnectionResetError("aba fechada")

    async def cenario():
        return await ab.PonteAgente(enviar=enviar).executar("qualquer coisa")

    assert asyncio.run(cenario()).final_text == "terminei mesmo assim"


# ── Confirmação ───────────────────────────────────────────────────────────────

def _pedido():
    return PedidoConfirmacao(
        ferramenta="run_command",
        argumentos={"command": "rm -rf build"},
        nivel_risco="critical",
        motivo="apaga arquivos recursivamente, sem lixeira",
        preview="rm -rf build",
    )


def test_usuario_aprova_e_a_thread_segue(monkeypatch):
    decisao = {}

    def dubl(objetivo, **kw):
        decisao["aprovado"] = kw["confirm_handler"](_pedido())
        return AgentResult(final_text="apagado")

    monkeypatch.setattr(ab, "run_agent", dubl)
    vistas = []

    async def cenario():
        ponte = ab.PonteAgente(enviar=None, timeout_confirmacao=5.0)

        async def enviar(m):
            vistas.append(m)
            if m["type"] == "agent_confirm":
                ponte.responder(m["id"], True)

        ponte._enviar = enviar
        return await ponte.executar("apaga a pasta build")

    resultado = asyncio.run(cenario())
    assert decisao["aprovado"] is True
    assert resultado.final_text == "apagado"
    pedido = next(m for m in vistas if m["type"] == "agent_confirm")
    assert pedido["risk"] == "critical"
    assert pedido["preview"] == "rm -rf build"
    assert pedido["reason"]


def test_usuario_recusa_e_a_thread_sabe(monkeypatch):
    decisao = {}

    def dubl(objetivo, **kw):
        decisao["aprovado"] = kw["confirm_handler"](_pedido())
        return AgentResult(final_text="nao apaguei")

    monkeypatch.setattr(ab, "run_agent", dubl)

    async def cenario():
        ponte = ab.PonteAgente(enviar=None, timeout_confirmacao=5.0)

        async def enviar(m):
            if m["type"] == "agent_confirm":
                ponte.responder(m["id"], False)

        ponte._enviar = enviar
        return await ponte.executar("apaga a pasta build")

    asyncio.run(cenario())
    assert decisao["aprovado"] is False


def test_confirmacao_sem_resposta_expira_recusando(monkeypatch):
    decisao = {}

    def dubl(objetivo, **kw):
        decisao["aprovado"] = kw["confirm_handler"](_pedido())
        return AgentResult(final_text="expirou")

    monkeypatch.setattr(ab, "run_agent", dubl)
    avisos = []

    async def enviar(m):
        avisos.append(m["type"])          # ninguém responde de propósito

    async def cenario():
        ponte = ab.PonteAgente(enviar=enviar, timeout_confirmacao=0.3)
        return await ponte.executar("apaga a pasta build")

    asyncio.run(cenario())
    assert decisao["aprovado"] is False
    assert "agent_confirm_timeout" in avisos


def test_auto_aprovar_nao_pergunta(monkeypatch):
    decisao = {}

    def dubl(objetivo, **kw):
        decisao["aprovado"] = kw["confirm_handler"](_pedido())
        return AgentResult(final_text="feito")

    monkeypatch.setattr(ab, "run_agent", dubl)
    vistas = []

    async def enviar(m):
        vistas.append(m["type"])

    async def cenario():
        ponte = ab.PonteAgente(enviar=enviar, auto_aprovar=True)
        return await ponte.executar("apaga a pasta build")

    asyncio.run(cenario())
    assert decisao["aprovado"] is True
    assert "agent_confirm" not in vistas


def test_resposta_para_id_inexistente_e_ignorada():
    async def enviar(_m):
        pass
    ponte = ab.PonteAgente(enviar=enviar)
    assert ponte.responder("naoexiste", True) is False


def test_pendencia_nao_sobrevive_ao_fim_do_laco(monkeypatch):
    """Thread travada em confirmação não pode ficar presa depois do laço acabar."""
    def dubl(objetivo, **kw):
        return AgentResult(final_text="acabou sem perguntar")

    monkeypatch.setattr(ab, "run_agent", dubl)

    async def enviar(_m):
        pass

    async def cenario():
        ponte = ab.PonteAgente(enviar=enviar)
        ponte._pendencias["orfa"] = ab._Pendencia()
        await ponte.executar("qualquer coisa")
        return ponte
    ponte = asyncio.run(cenario())
    assert ponte.pendencias_abertas() == []

@pytest.mark.parametrize("rodada", range(12))
def test_laco_instantaneo_nao_perde_evento(monkeypatch, rodada):
    """
    Regressão: a drenagem terminava quando a tarefa acabava e a fila estava
    vazia. Num laço que retorna na hora, os put_nowait ainda estavam agendados
    e não executados — fila "vazia", eventos perdidos. Passava ou falhava por
    sorte de escalonamento, daí as repetições.
    """
    def dubl(objetivo, **kw):
        emit = kw["on_event"]
        for i in range(4):
            emit("tool_call", {"name": "read_file", "arguments": {"path": f"{i}.py"}})
        emit("done", {"reason": "completed", "iterations": 4})
        return AgentResult(final_text="pronto")

    monkeypatch.setattr(ab, "run_agent", dubl)
    recebidas = []

    async def enviar(m):
        recebidas.append(m)

    async def cenario():
        return await ab.PonteAgente(enviar=enviar).executar("lê quatro arquivos")

    asyncio.run(cenario())
    eventos = [m["event"] for m in recebidas if m["type"] == "agent_event"]
    assert eventos.count("tool_call") == 4, eventos
    assert eventos[-1] == "done"


def test_erro_no_laco_nao_trava_a_drenagem(monkeypatch):
    """Exceção no laço também tem que fechar a fila, ou a ponte fica esperando."""
    def dubl(objetivo, **kw):
        kw["on_event"]("thinking", {"text": "vou falhar", "iteration": 1})
        raise RuntimeError("provedor fora do ar")

    monkeypatch.setattr(ab, "run_agent", dubl)

    async def enviar(_m):
        pass

    async def cenario():
        with pytest.raises(RuntimeError):
            await asyncio.wait_for(
                ab.PonteAgente(enviar=enviar).executar("qualquer coisa"), timeout=5)

    asyncio.run(cenario())
