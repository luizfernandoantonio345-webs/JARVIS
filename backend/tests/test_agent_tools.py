"""
Testes do tool_registry e do agent_loop.

O foco não é o LLM — é a camada que o cerca: schema correto, execução de
ferramenta, erro virando texto que o modelo consegue ler, e as defesas contra
o agente se perder ou escrever fora da raiz de trabalho.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import tool_registry as tr  # noqa: E402
from core.agent_loop import ToolCall, _compact, _execute  # noqa: E402


# ── Registro ──────────────────────────────────────────────────────────────────

def test_ferramentas_essenciais_registradas():
    nomes = {t.name for t in tr.all_tools()}
    for esperado in ("read_file", "write_file", "edit_file", "list_dir",
                     "search_code", "run_command", "web_search", "fetch_url"):
        assert esperado in nomes, f"ferramenta ausente: {esperado}"


def test_schema_anthropic_tem_campos_obrigatorios():
    for schema in tr.schemas_for("anthropic"):
        assert schema["name"]
        assert schema["description"], f"{schema['name']} sem descrição"
        assert schema["input_schema"]["type"] == "object"


def test_schema_openai_tem_formato_de_function():
    for schema in tr.schemas_for("openai"):
        assert schema["type"] == "function"
        assert schema["function"]["name"]
        assert "parameters" in schema["function"]


def test_ferramentas_de_leitura_marcadas_read_only():
    for nome in ("read_file", "list_dir", "search_code"):
        assert tr.get_tool(nome).read_only is True


def test_ferramentas_de_escrita_nao_sao_read_only():
    for nome in ("write_file", "edit_file", "run_command"):
        assert tr.get_tool(nome).read_only is False


# ── Limites de caminho ────────────────────────────────────────────────────────

def test_escrita_fora_da_raiz_e_bloqueada():
    """Alucinação do modelo não pode escrever em /etc."""
    with pytest.raises(PermissionError):
        tr._resolve_inside_workspace("/etc/passwd")


def test_path_traversal_e_bloqueado():
    with pytest.raises(PermissionError):
        tr._resolve_inside_workspace("../../../../etc/passwd")


# ── Ciclo de arquivo ──────────────────────────────────────────────────────────

def test_escrever_ler_e_editar(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_WORKSPACE", str(tmp_path))

    assert "OK" in tr.write_file("sub/exemplo.txt", "alfa\nbeta\n")
    assert (tmp_path / "sub" / "exemplo.txt").read_text() == "alfa\nbeta\n"

    lido = tr.read_file("sub/exemplo.txt")
    assert "alfa" in lido and "beta" in lido

    assert "OK" in tr.edit_file("sub/exemplo.txt", "beta", "gama")
    assert "gama" in (tmp_path / "sub" / "exemplo.txt").read_text()
    # sobrescrita preserva backup
    assert (tmp_path / "sub" / "exemplo.txt.bak").exists()


def test_edit_file_recusa_trecho_ambiguo(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_WORKSPACE", str(tmp_path))
    tr.write_file("dup.txt", "x\nx\n")
    resultado = tr.edit_file("dup.txt", "x", "y")
    assert resultado.startswith("ERRO")
    assert "2 vezes" in resultado


def test_read_file_inexistente_devolve_erro_legivel(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_WORKSPACE", str(tmp_path))
    assert tr.read_file("nao/existe.txt").startswith("ERRO")


# ── Comando ───────────────────────────────────────────────────────────────────

def test_run_command_devolve_exit_code_e_saida():
    saida = tr.run_command("echo ola-jarvis")
    assert "exit_code: 0" in saida
    assert "ola-jarvis" in saida


def test_run_command_expoe_falha_em_vez_de_esconder():
    saida = tr.run_command("exit 3")
    assert "exit_code: 3" in saida


# ── Truncamento ───────────────────────────────────────────────────────────────

def test_truncate_preserva_inicio_e_fim():
    texto = "A" * 100 + "MEIO" + "B" * 100
    cortado = tr.truncate(texto, limit=50)
    assert cortado.startswith("A")
    assert cortado.endswith("B")
    assert "omitidos" in cortado


# ── Execução pelo laço ────────────────────────────────────────────────────────

def test_execute_ferramenta_inexistente_lista_as_validas():
    call = _execute(ToolCall(name="nao_existe", arguments={}))
    assert call.error is True
    assert "read_file" in call.result  # ajuda o modelo a se corrigir


def test_execute_argumento_invalido_vira_erro_legivel():
    call = _execute(ToolCall(name="read_file", arguments={"argumento_errado": 1}))
    assert call.error is True
    assert "ERRO" in call.result


def test_execute_registra_duracao():
    call = _execute(ToolCall(name="list_dir", arguments={"path": "."}))
    assert call.duration_ms >= 0


# ── Compactação de contexto ───────────────────────────────────────────────────

def test_compact_nao_mexe_em_conversa_curta():
    msgs = [{"role": "user", "content": str(i)} for i in range(5)]
    assert _compact(msgs, "objetivo") == msgs


def test_compact_encurta_e_reafirma_o_objetivo():
    msgs = [{"role": "user", "content": str(i)} for i in range(200)]
    compactado = _compact(msgs, "corrigir o teste que falha")
    assert len(compactado) < len(msgs)
    texto = " ".join(str(m.get("content")) for m in compactado)
    assert "corrigir o teste que falha" in texto
