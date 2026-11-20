"""
Testes do porteiro de verificação.

A regra que está sendo provada: o agente não encerra declarando pronto o que
não conferiu. O SYSTEM_PROMPT já pede isso e o modelo pequeno ignora — então a
cobrança é mecânica, e o que precisa de teste é a mecânica.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import verification as vfy      # noqa: E402
from core import agent_loop as al         # noqa: E402
from core.agent_loop import ToolCall      # noqa: E402


# ── O que conta como conferência ──────────────────────────────────────────────

@pytest.mark.parametrize("comando", [
    "pytest backend/tests/ -q",
    "python -m pytest",
    "npm test",
    "npm run build",
    "node --check app.js",
    "ruff check backend/",
    "mypy backend/core",
    "python -m py_compile backend/main.py",
    "curl -s localhost:8000/health",
    "git diff --stat",
])
def test_comando_de_conferencia_com_exit_zero_vale(comando):
    assert vfy.e_conferencia("run_command", {"command": comando},
                             "exit_code: 0\nstdout:\n...", erro=False)


def test_conferencia_que_falhou_nao_vale():
    assert not vfy.e_conferencia("run_command", {"command": "pytest"},
                                 "exit_code: 1\nstderr:\n2 failed", erro=False)


def test_comando_qualquer_nao_vale_como_prova():
    assert not vfy.e_conferencia("run_command", {"command": "echo pronto"},
                                 "exit_code: 0", erro=False)


def test_escrever_arquivo_nao_e_conferencia():
    assert not vfy.e_conferencia("write_file", {"path": "a.py"}, "ok", erro=False)


# ── Rastreador ────────────────────────────────────────────────────────────────

def _escreveu(r, caminho="backend/x.py"):
    r.registrar("write_file", {"path": caminho}, "escrito", erro=False, read_only=False)


def test_leitura_nao_gera_pendencia():
    r = vfy.RastreadorDeVerificacao()
    r.registrar("read_file", {"path": "a.py"}, "conteudo", erro=False, read_only=True)
    assert r.tudo_conferido()


def test_escrita_gera_pendencia_nomeada():
    r = vfy.RastreadorDeVerificacao()
    _escreveu(r)
    assert not r.tudo_conferido()
    assert any("backend/x.py" in p for p in r.pendentes)


def test_teste_que_passa_limpa_a_pendencia():
    r = vfy.RastreadorDeVerificacao()
    _escreveu(r)
    r.registrar("run_command", {"command": "pytest -q"}, "exit_code: 0",
                erro=False, read_only=False)
    assert r.tudo_conferido()


def test_teste_que_falha_mantem_a_pendencia():
    r = vfy.RastreadorDeVerificacao()
    _escreveu(r)
    r.registrar("run_command", {"command": "pytest -q"}, "exit_code: 1",
                erro=False, read_only=False)
    assert not r.tudo_conferido()


def test_escrita_depois_da_conferencia_volta_a_pendurar():
    r = vfy.RastreadorDeVerificacao()
    _escreveu(r, "a.py")
    r.registrar("run_command", {"command": "pytest"}, "exit_code: 0",
                erro=False, read_only=False)
    _escreveu(r, "b.py")
    assert not r.tudo_conferido()
    assert any("b.py" in p for p in r.pendentes)


def test_comando_que_so_olha_nao_pendura():
    r = vfy.RastreadorDeVerificacao()
    for comando in ("ls -la", "cat main.py", "git status", "pip list"):
        r.registrar("run_command", {"command": comando}, "exit_code: 0",
                    erro=False, read_only=False)
    assert r.tudo_conferido()


def test_escrita_que_falhou_nao_pendura():
    r = vfy.RastreadorDeVerificacao()
    r.registrar("write_file", {"path": "a.py"}, "ERRO: sem permissão",
                erro=True, read_only=False)
    assert r.tudo_conferido()


def test_mesma_pendencia_nao_duplica():
    r = vfy.RastreadorDeVerificacao()
    _escreveu(r, "a.py")
    _escreveu(r, "a.py")
    assert len(r.pendentes) == 1


def test_cobranca_tem_limite():
    r = vfy.RastreadorDeVerificacao()
    _escreveu(r)
    for _ in range(vfy.MAX_COBRANCAS):
        assert r.pode_cobrar()
        r.cobrar()
    assert not r.pode_cobrar()


def test_texto_da_cobranca_nomeia_o_que_falta():
    r = vfy.RastreadorDeVerificacao()
    _escreveu(r, "backend/core/router.py")
    texto = r.cobrar()
    assert "backend/core/router.py" in texto
    assert "run_command" in texto


# ── Integração com o laço ─────────────────────────────────────────────────────

def _turno(texto="", chamadas=()):
    return {"text": texto, "calls": list(chamadas),
            "ids": [f"id{i}" for i in range(len(chamadas))], "raw": {}}


@pytest.fixture
def laco(monkeypatch):
    monkeypatch.setattr(al, "_provider", lambda: "ollama")
    monkeypatch.setattr(al.esc, "habilitada", lambda: False)


def _execucao_realista(call, **kw):
    """run_command devolve exit_code como o de verdade; o resto, texto curto."""
    resultado = ("exit_code: 0\nstdout:\n5 passed"
                 if call.name == "run_command" else "escrito")
    return ToolCall(name=call.name, arguments=call.arguments,
                    result=resultado, error=False)


def test_laco_barra_pronto_sem_conferencia(laco, monkeypatch):
    """O caso que mais incomoda: escreveu, disse pronto, não testou."""
    monkeypatch.setattr(al, "_execute", _execucao_realista)
    turnos = [
        _turno(chamadas=[ToolCall(name="write_file",
                                  arguments={"path": "a.py", "content": "x"})]),
        _turno(texto="Pronto, Sir."),                       # tentativa barrada
        _turno(chamadas=[ToolCall(name="run_command",
                                  arguments={"command": "pytest -q"})]),
        _turno(texto="Pronto e testado, Sir."),
    ]
    monkeypatch.setattr(al, "_one_turn", lambda msgs: turnos.pop(0))

    eventos = []
    r = al.run_agent("escreve o arquivo a.py", use_memory=False,
                     on_event=lambda t, d: eventos.append((t, d)))

    assert r.stopped_reason == "completed"
    assert r.final_text == "Pronto e testado, Sir."
    assert r.verified is True
    assert "verification_required" in [t for t, _ in eventos]
    assert not turnos, "o laço deveria ter consumido todos os turnos"


def test_laco_aceita_e_avisa_depois_do_limite(laco, monkeypatch):
    """Insistir para sempre seria loop; avisar é honesto."""
    monkeypatch.setattr(al, "_execute", lambda call, **kw: ToolCall(
        name=call.name, arguments=call.arguments, result="escrito", error=False))
    turnos = [_turno(chamadas=[ToolCall(name="write_file",
                                        arguments={"path": "a.py", "content": "x"})])]
    turnos += [_turno(texto="Pronto, Sir.")] * 6
    monkeypatch.setattr(al, "_one_turn", lambda msgs: turnos.pop(0))

    r = al.run_agent("escreve o arquivo a.py", use_memory=False, max_iterations=8)

    assert r.stopped_reason == "completed"
    assert r.verified is False
    assert "Não consegui confirmar" in r.final_text
    assert "a.py" in r.final_text


def test_tarefa_so_de_leitura_nao_exige_conferencia(laco, monkeypatch):
    monkeypatch.setattr(al, "_execute", lambda call, **kw: ToolCall(
        name=call.name, arguments=call.arguments, result="conteudo", error=False))
    turnos = [
        _turno(chamadas=[ToolCall(name="read_file", arguments={"path": "a.py"})]),
        _turno(texto="O arquivo tem uma função só."),
    ]
    monkeypatch.setattr(al, "_one_turn", lambda msgs: turnos.pop(0))

    r = al.run_agent("lê o a.py", use_memory=False)
    assert r.stopped_reason == "completed"
    assert r.verified is None
    assert "Não consegui confirmar" not in r.final_text


def test_conversa_sem_ferramenta_nao_ganha_aviso(laco, monkeypatch):
    monkeypatch.setattr(al, "_one_turn", lambda msgs: _turno(texto="Boa noite, Sir."))
    r = al.run_agent("boa noite", use_memory=False)
    assert r.final_text == "Boa noite, Sir."
    assert r.verified is None


# ── Dica de argumentos ────────────────────────────────────────────────────────

def test_erro_de_argumento_diz_o_nome_certo():
    """TypeError cru não ensina nada ao modelo; o schema ensina."""
    call = ToolCall(name="read_file", arguments={"arquivo": "a.py"})
    executado = al._execute(call, safety_level="off")
    assert executado.error
    assert "path" in executado.result
    assert "arquivo" in executado.result        # aponta o que não existe
