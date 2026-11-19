"""
Testes dos perfis de voz e da porta de saída de áudio.

Dois riscos cobertos aqui:

  1. Nome de voz inválido falha em silêncio na hora de falar. A validação
     contra a lista real precisa funcionar, e precisa degradar quando não
     houver rede para consultar.

  2. Backend e frontend falando ao mesmo tempo — o usuário ouve em dobro.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voice_v2 import voice_profiles as vp  # noqa: E402


# ── Perfis ────────────────────────────────────────────────────────────────────

def test_perfis_essenciais_existem():
    for nome in ("jarvis", "ultron", "operacional", "neutro"):
        assert nome in vp.PERFIS


def test_perfil_desconhecido_cai_no_padrao():
    assert vp.perfil("nao_existe").nome == vp.PERFIL_PADRAO


def test_perfil_aceita_none():
    assert vp.perfil(None).nome == vp.PERFIL_PADRAO


def test_ultron_e_mais_grave_e_mais_lento_que_jarvis():
    """É isso que separa os dois: o Ultron é o mesmo timbre puxado para baixo."""
    j, u = vp.PERFIS["jarvis"], vp.PERFIS["ultron"]
    assert int(u.pitch.rstrip("Hz")) < int(j.pitch.rstrip("Hz"))
    assert int(u.rate.rstrip("%")) < int(j.rate.rstrip("%"))


def test_todo_perfil_tem_parametros_no_formato_do_edge_tts():
    for nome, p in vp.PERFIS.items():
        assert p.voice, nome
        assert p.rate.endswith("%"), f"{nome}: rate precisa terminar em %"
        assert p.pitch.endswith("Hz"), f"{nome}: pitch precisa terminar em Hz"
        assert p.rate[0] in "+-", f"{nome}: rate precisa de sinal"
        assert p.pitch[0] in "+-", f"{nome}: pitch precisa de sinal"


def test_todo_perfil_tem_descricao_util():
    for nome, p in vp.PERFIS.items():
        assert len(p.descricao) > 20, f"{nome} sem descrição que ajude a escolher"


# ── Validação de voz ──────────────────────────────────────────────────────────

def test_usa_a_primeira_escolha_quando_ela_existe(monkeypatch):
    async def fake(force=False):
        return {"pt-BR-AntonioNeural", "pt-BR-FabioNeural"}

    monkeypatch.setattr(vp, "listar_vozes", fake)
    voz = asyncio.run(vp.resolver_voz(vp.PERFIS["jarvis"]))
    assert voz == "pt-BR-AntonioNeural"


def test_cai_na_alternativa_quando_a_principal_sumiu(monkeypatch):
    async def fake(force=False):
        return {"pt-BR-FabioNeural"}        # a principal não está mais lá

    monkeypatch.setattr(vp, "listar_vozes", fake)
    voz = asyncio.run(vp.resolver_voz(vp.PERFIS["jarvis"]))
    assert voz == "pt-BR-FabioNeural"


def test_sem_rede_tenta_a_principal_em_vez_de_ficar_mudo(monkeypatch):
    async def fake(force=False):
        return set()                        # não deu para consultar

    monkeypatch.setattr(vp, "listar_vozes", fake)
    voz = asyncio.run(vp.resolver_voz(vp.PERFIS["ultron"]))
    assert voz == vp.PERFIS["ultron"].voice


def test_parametros_de_fala_entrega_o_que_o_edge_tts_espera(monkeypatch):
    async def fake(force=False):
        return set()

    monkeypatch.setattr(vp, "listar_vozes", fake)
    p = asyncio.run(vp.parametros_de_fala("ultron"))
    assert set(p) == {"voice", "rate", "pitch"}
    assert p["rate"] == vp.PERFIS["ultron"].rate


def test_listar_vozes_nao_propaga_erro_de_rede(monkeypatch):
    vp._vozes_disponiveis = None
    monkeypatch.setattr(vp, "listar_vozes", vp.listar_vozes)  # real
    resultado = asyncio.run(vp.listar_vozes(force=True))
    assert isinstance(resultado, set)       # vazio é aceitável; exceção não


# ── Porta de saída ────────────────────────────────────────────────────────────

def test_modo_browser_nao_toca_no_servidor(monkeypatch):
    """Sem esta porta, backend e navegador falam juntos e ouve-se em dobro."""
    from voice_v2 import output

    monkeypatch.setattr(output, "_saida_configurada", lambda: "browser")

    chamou = {"gerou": False}

    async def nao_deveria(*a, **k):
        chamou["gerou"] = True
        return None

    monkeypatch.setattr(output, "generate_tts_file", nao_deveria)
    assert asyncio.run(output.speak("teste")) is False
    assert chamou["gerou"] is False


def test_modo_server_segue_para_a_geracao(monkeypatch):
    from voice_v2 import output

    monkeypatch.setattr(output, "_saida_configurada", lambda: "server")

    chamou = {"gerou": False}

    async def gerar(*a, **k):
        chamou["gerou"] = True
        return None                          # falha depois; o que importa é ter tentado

    monkeypatch.setattr(output, "generate_tts_file", gerar)
    asyncio.run(output.speak("teste"))
    assert chamou["gerou"] is True


def test_texto_vazio_nao_fala():
    from voice_v2 import output
    assert asyncio.run(output.speak("   ")) is False
