"""
Testes da escalada para modelo forte.

O ponto central: um modelo pequeno que entrou em loop não percebe que entrou
em loop. Quem percebe é o laço — então o que precisa de teste é a detecção
vista de fora e a decisão do que fazer com ela.

Nenhuma chamada de rede acontece aqui: o consultor é injetado.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import escalation as esc        # noqa: E402
from core.agent_loop import ToolCall      # noqa: E402


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    for chave in ("JARVIS_ESCALATE", "JARVIS_ESCALATE_PROVIDER",
                  "JARVIS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY",
                  "JARVIS_OPENAI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(chave, raising=False)


# ── Detecção ──────────────────────────────────────────────────────────────────

def test_mesma_chamada_de_novo_e_impasse():
    d = esc.DetectorDeImpasse()
    assert d.registrar_chamada("read_file", {"path": "a.py"}, erro=False) is None
    impasse = d.registrar_chamada("read_file", {"path": "a.py"}, erro=False)
    assert impasse is not None and impasse.tipo == "repeticao"


def test_argumentos_diferentes_nao_sao_repeticao():
    d = esc.DetectorDeImpasse()
    for caminho in ("a.py", "b.py", "c.py"):
        assert d.registrar_chamada("read_file", {"path": caminho}, erro=False) is None


def test_ordem_dos_argumentos_nao_cria_falsa_diferenca():
    d = esc.DetectorDeImpasse()
    d.registrar_chamada("write_file", {"path": "a.py", "content": "x"}, erro=False)
    impasse = d.registrar_chamada("write_file", {"content": "x", "path": "a.py"}, erro=False)
    assert impasse is not None and impasse.tipo == "repeticao"


def test_tres_erros_seguidos_e_impasse():
    d = esc.DetectorDeImpasse()
    assert d.registrar_chamada("run_command", {"command": "a"}, erro=True) is None
    assert d.registrar_chamada("run_command", {"command": "b"}, erro=True) is None
    impasse = d.registrar_chamada("run_command", {"command": "c"}, erro=True)
    assert impasse is not None and impasse.tipo == "erros"


def test_sucesso_no_meio_zera_a_contagem():
    d = esc.DetectorDeImpasse()
    d.registrar_chamada("run_command", {"command": "a"}, erro=True)
    d.registrar_chamada("run_command", {"command": "b"}, erro=True)
    d.registrar_chamada("run_command", {"command": "c"}, erro=False)
    assert d.registrar_chamada("run_command", {"command": "d"}, erro=True) is None


def test_dois_turnos_vazios_sao_impasse():
    d = esc.DetectorDeImpasse()
    assert d.registrar_turno_vazio() is None
    impasse = d.registrar_turno_vazio()
    assert impasse is not None and impasse.tipo == "vazio"


def test_esquecer_limpa_o_historico():
    d = esc.DetectorDeImpasse()
    d.registrar_chamada("read_file", {"path": "a.py"}, erro=False)
    d.esquecer()
    assert d.registrar_chamada("read_file", {"path": "a.py"}, erro=False) is None


# ── Configuração ──────────────────────────────────────────────────────────────

def test_sem_chave_a_escalada_fica_desligada():
    assert esc.provedor_disponivel() is None
    assert esc.habilitada() is False


def test_chave_da_anthropic_habilita_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")
    assert esc.provedor_disponivel() == "claude"
    assert esc.habilitada() is True


def test_chave_da_openai_habilita_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste")
    assert esc.provedor_disponivel() == "openai"


def test_provedor_preferido_vence(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-a")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-o")
    monkeypatch.setenv("JARVIS_ESCALATE_PROVIDER", "openai")
    assert esc.provedor_disponivel() == "openai"


def test_preferido_sem_chave_cai_no_que_existe(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-o")
    monkeypatch.setenv("JARVIS_ESCALATE_PROVIDER", "claude")
    assert esc.provedor_disponivel() == "openai"


def test_politica_off_desliga_mesmo_com_chave(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")
    monkeypatch.setenv("JARVIS_ESCALATE", "off")
    assert esc.habilitada() is False


def test_politica_invalida_cai_no_padrao(monkeypatch):
    monkeypatch.setenv("JARVIS_ESCALATE", "talvez")
    assert esc.politica() == esc.POLITICA_PADRAO


# ── Consulta ao modelo forte ──────────────────────────────────────────────────

def _impasse():
    return esc.Impasse("repeticao", "read_file chamada de novo")


def test_conselho_sem_provedor_devolve_none():
    assert esc.pedir_conselho("objetivo", "tentativas", _impasse(),
                              consultor=lambda *_: "nunca chamado") is None


def test_conselho_chega_e_leva_o_contexto(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")
    capturado = {}

    def consultor(pergunta, provedor):
        capturado["pergunta"] = pergunta
        capturado["provedor"] = provedor
        return "Chame search_code em vez de read_file."

    resposta = esc.pedir_conselho("achar a função X", "- read_file(a.py) → ok: ...",
                                  _impasse(), consultor=consultor,
                                  ferramentas="read_file, search_code")
    assert resposta and "search_code" in resposta
    assert capturado["provedor"] == "claude"
    assert "achar a função X" in capturado["pergunta"]
    assert "read_file chamada de novo" in capturado["pergunta"]
    assert "read_file, search_code" in capturado["pergunta"]


def test_erro_do_modelo_forte_nao_virar_conselho(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")
    assert esc.pedir_conselho("x", "y", _impasse(),
                              consultor=lambda *_: "ERRO: chave inválida") is None


def test_consultor_que_explode_devolve_none(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")

    def explode(*_):
        raise TimeoutError("sem rede")

    assert esc.pedir_conselho("x", "y", _impasse(), consultor=explode) is None


def test_resposta_vazia_devolve_none(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")
    assert esc.pedir_conselho("x", "y", _impasse(), consultor=lambda *_: "   ") is None


def test_assumir_tarefa_devolve_a_resposta(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")
    resposta = esc.assumir_tarefa("somar 2+2", "- run_command(python) → ERRO",
                                  consultor=lambda *_: "A resposta é 4.")
    assert resposta == "A resposta é 4."


# ── Resumo das tentativas ─────────────────────────────────────────────────────

def test_resumo_mostra_ferramenta_argumento_e_erro():
    chamadas = [
        ToolCall(name="read_file", arguments={"path": "a.py"},
                 result="conteudo do arquivo", error=False),
        ToolCall(name="run_command", arguments={"command": "pytest"},
                 result="ERRO: comando falhou", error=True),
    ]
    resumo = esc.resumir_tentativas(chamadas)
    assert "read_file" in resumo and "path=a.py" in resumo and "ok" in resumo
    assert "run_command" in resumo and "ERRO" in resumo


def test_resumo_sem_chamadas():
    assert esc.resumir_tentativas([]) == "(nada ainda)"


def test_resumo_limita_o_que_manda():
    chamadas = [ToolCall(name=f"t{i}", arguments={}, result="x") for i in range(30)]
    assert len(esc.resumir_tentativas(chamadas, limite=5).splitlines()) == 5


# ── Integração com o laço ─────────────────────────────────────────────────────
#
# Aqui o que está sendo provado é a fiação: o laço detecta o impasse sozinho,
# chama a escalada, injeta o conselho e continua — ou aceita a entrega e para.

from core import agent_loop as al   # noqa: E402


def _turno(texto="", chamadas=()):
    return {"text": texto, "calls": list(chamadas),
            "ids": [f"id{i}" for i in range(len(chamadas))], "raw": {}}


@pytest.fixture
def laco_sem_rede(monkeypatch):
    """Modelo e ferramentas dublados; sobra o laço de verdade."""
    monkeypatch.setattr(al, "_provider", lambda: "ollama")
    monkeypatch.setattr(al, "_execute",
                        lambda call, **kw: ToolCall(name=call.name,
                                                    arguments=call.arguments,
                                                    result="mesmo resultado de sempre",
                                                    error=False))


def test_laco_pede_conselho_sozinho_e_continua(laco_sem_rede, monkeypatch):
    turnos = [
        _turno(chamadas=[ToolCall(name="read_file", arguments={"path": "a.py"})]),
        _turno(chamadas=[ToolCall(name="read_file", arguments={"path": "a.py"})]),
        _turno(texto="Agora entendi: a função está em outro arquivo."),
    ]
    monkeypatch.setattr(al, "_one_turn", lambda msgs: turnos.pop(0))
    monkeypatch.setattr(al.esc, "habilitada", lambda: True)
    monkeypatch.setattr(al.esc, "pedir_conselho",
                        lambda *a, **k: "Use search_code, não read_file.")

    eventos = []
    r = al.run_agent("achar a função X", use_memory=False,
                     on_event=lambda t, d: eventos.append((t, d)))

    assert r.stopped_reason == "completed"
    assert "outro arquivo" in r.final_text
    tipos = [t for t, _ in eventos]
    assert "escalating" in tipos and "escalated" in tipos
    assert next(d for t, d in eventos if t == "escalating")["reason"] == "repeticao"
    assert next(d for t, d in eventos if t == "escalated")["mode"] == "advice"
    # O conselho tem que ter entrado no contexto, ou o modelo não o vê.
    assert any("search_code" in str(m.get("content", "")) for m in r.messages)


def test_conselho_que_nao_resolve_vira_entrega(laco_sem_rede, monkeypatch):
    chamada = ToolCall(name="read_file", arguments={"path": "a.py"})
    monkeypatch.setattr(al, "_one_turn", lambda msgs: _turno(chamadas=[chamada]))
    monkeypatch.setattr(al.esc, "habilitada", lambda: True)
    monkeypatch.setattr(al.esc, "pedir_conselho", lambda *a, **k: "Tente outra coisa.")
    monkeypatch.setattr(al.esc, "assumir_tarefa",
                        lambda *a, **k: "A função X está em core/router.py.")

    eventos = []
    r = al.run_agent("achar a função X", use_memory=False, max_iterations=12,
                     on_event=lambda t, d: eventos.append((t, d)))

    assert r.stopped_reason == "escalated"
    assert "core/router.py" in r.final_text
    modos = [d["mode"] for t, d in eventos if t == "escalated"]
    assert modos == ["advice", "handover"]


def test_escalada_desligada_deixa_o_laco_bater_no_teto(laco_sem_rede, monkeypatch):
    chamada = ToolCall(name="read_file", arguments={"path": "a.py"})
    monkeypatch.setattr(al, "_one_turn", lambda msgs: _turno(chamadas=[chamada]))
    chamou = {"sim": False}

    def nao_deveria(*a, **k):
        chamou["sim"] = True
        return "conselho"

    monkeypatch.setattr(al.esc, "pedir_conselho", nao_deveria)
    monkeypatch.setattr(al.esc, "assumir_tarefa", nao_deveria)

    r = al.run_agent("achar a função X", use_memory=False, max_iterations=4,
                     escalate=False)
    assert r.stopped_reason == "max_iterations"
    assert chamou["sim"] is False


def test_teto_batido_vai_direto_para_entrega(laco_sem_rede, monkeypatch):
    """No teto não há laço para continuar: conselho ali não serviria de nada."""
    monkeypatch.setattr(al, "_one_turn",
                        lambda msgs: _turno(chamadas=[ToolCall(
                            name="run_command",
                            arguments={"command": f"echo {len(msgs)}"})]))
    monkeypatch.setattr(al.esc, "habilitada", lambda: True)
    pediu = {"conselho": False}

    def conselho(*a, **k):
        pediu["conselho"] = True
        return "algo"

    monkeypatch.setattr(al.esc, "pedir_conselho", conselho)
    monkeypatch.setattr(al.esc, "assumir_tarefa", lambda *a, **k: "Resposta do forte.")

    r = al.run_agent("tarefa longa", use_memory=False, max_iterations=3)
    assert r.stopped_reason == "escalated"
    assert r.final_text == "Resposta do forte."
    assert pediu["conselho"] is False


def test_turno_vazio_e_cutucado_antes_de_escalar(laco_sem_rede, monkeypatch):
    turnos = [_turno(), _turno(texto="Pronto, Sir.")]
    monkeypatch.setattr(al, "_one_turn", lambda msgs: turnos.pop(0))
    monkeypatch.setattr(al.esc, "habilitada", lambda: True)

    r = al.run_agent("qualquer coisa", use_memory=False)
    assert r.stopped_reason == "completed"
    assert r.final_text == "Pronto, Sir."


def test_turnos_vazios_sem_escalada_nao_devolvem_resposta_vazia(laco_sem_rede,
                                                                monkeypatch):
    monkeypatch.setattr(al, "_one_turn", lambda msgs: _turno())
    r = al.run_agent("qualquer coisa", use_memory=False, escalate=False)
    assert r.stopped_reason == "empty_turns"
    assert r.final_text.strip(), "usuário não pode receber resposta em branco"
