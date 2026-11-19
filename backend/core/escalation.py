"""
Escalada quando o modelo local empaca.

O `ask_stronger_model` já existia como ferramenta, mas depender do modelo
pequeno para *decidir* usá-la não funciona: um 7B que entrou em loop não
percebe que entrou em loop — ele repete a mesma chamada com convicção. Quem
precisa perceber é o laço.

Três sinais de impasse, todos observáveis de fora do modelo:

- repetição: a mesma ferramenta com os mesmos argumentos de novo
- erro em sequência: três resultados de erro seguidos
- turno vazio: nem texto nem chamada de ferramenta

No primeiro impasse pede conselho — manda o objetivo e o que já foi tentado,
recebe o próximo passo e devolve ao modelo local, que continua trabalhando.
Isso custa uma chamada e costuma destravar. No segundo, entrega a tarefa: o
modelo forte responde e o laço encerra. Sem chave configurada nada disso
acontece e o laço segue como antes.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("jarvis.core.escalation")

POLITICAS = ("off", "advice", "auto")
POLITICA_PADRAO = "auto"

JANELA = 8            # chamadas lembradas para detectar repetição
ERROS_SEGUIDOS = 3    # erros em sequência que contam como impasse
MAX_ESCALADAS = 2     # conselho, depois entrega; além disso, para


@dataclass
class Impasse:
    tipo: str          # repeticao | erros | vazio | teto
    detalhe: str

    def __str__(self) -> str:
        return f"{self.tipo}: {self.detalhe}"


@dataclass
class DetectorDeImpasse:
    """Observa as chamadas de fora e diz quando o modelo está rodando em falso."""

    janela: int = JANELA
    limite_erros: int = ERROS_SEGUIDOS
    _vistas: deque = field(default_factory=lambda: deque(maxlen=JANELA), repr=False)
    _erros: int = 0
    _vazios: int = 0

    def registrar_chamada(self, nome: str, argumentos: dict[str, Any],
                          erro: bool) -> Impasse | None:
        assinatura = (nome, _assinatura(argumentos))
        repetida = assinatura in self._vistas
        self._vistas.append(assinatura)

        if erro:
            self._erros += 1
        else:
            self._erros = 0
        self._vazios = 0

        if self._erros >= self.limite_erros:
            self._erros = 0
            return Impasse("erros", f"{self.limite_erros} falhas seguidas, a última em {nome}")
        if repetida:
            return Impasse("repeticao", f"{nome} chamada de novo com os mesmos argumentos")
        return None

    def registrar_turno_vazio(self) -> Impasse | None:
        self._vazios += 1
        if self._vazios >= 2:
            self._vazios = 0
            return Impasse("vazio", "dois turnos sem texto e sem ferramenta")
        return None

    def esquecer(self) -> None:
        """Depois de um conselho o passado não serve de prova: começa limpo."""
        self._vistas.clear()
        self._erros = 0
        self._vazios = 0


def _assinatura(argumentos: dict[str, Any]) -> str:
    if not argumentos:
        return ""
    return "|".join(f"{k}={str(v)[:120]}" for k, v in sorted(argumentos.items()))


# ── Configuração ──────────────────────────────────────────────────────────────

def politica() -> str:
    bruto = (os.getenv("JARVIS_ESCALATE", "") or "").strip().lower()
    if bruto in POLITICAS:
        return bruto
    if bruto:
        log.warning("[ESCALADA] política %r desconhecida; usando %r", bruto, POLITICA_PADRAO)
    return POLITICA_PADRAO


def provedor_disponivel() -> str | None:
    """Qual modelo forte dá para usar agora, se algum."""
    preferido = (os.getenv("JARVIS_ESCALATE_PROVIDER", "") or "").strip().lower()
    tem_claude = bool(os.getenv("JARVIS_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    tem_openai = bool(os.getenv("JARVIS_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"))
    if preferido == "claude" and tem_claude:
        return "claude"
    if preferido == "openai" and tem_openai:
        return "openai"
    if tem_claude:
        return "claude"
    if tem_openai:
        return "openai"
    return None


def habilitada() -> bool:
    return politica() != "off" and provedor_disponivel() is not None


# ── Perguntas ao modelo forte ─────────────────────────────────────────────────

_CONSULTOR = Callable[[str, str], str]   # (pergunta, provedor) -> resposta


def _consultor_padrao(pergunta: str, provedor: str) -> str:
    from . import tools_web
    return tools_web.ask_stronger_model(pergunta, provedor)


def resumir_tentativas(chamadas: list[Any], limite: int = 10) -> str:
    """
    O que já foi tentado, em texto curto.

    Resultado inteiro não vai: o que importa para destravar é o que foi
    chamado, com quais argumentos, e se deu erro.
    """
    if not chamadas:
        return "(nada ainda)"
    linhas = []
    for c in chamadas[-limite:]:
        argumentos = _assinatura(getattr(c, "arguments", {}) or {})[:160]
        marca = "ERRO" if getattr(c, "error", False) else "ok"
        trecho = (getattr(c, "result", "") or "")[:200].replace("\n", " ")
        linhas.append(f"- {getattr(c, 'name', '?')}({argumentos}) → {marca}: {trecho}")
    return "\n".join(linhas)


def pedir_conselho(objetivo: str, tentativas: str, impasse: Impasse, *,
                   consultor: _CONSULTOR | None = None,
                   ferramentas: str = "") -> str | None:
    """
    Pede o próximo passo concreto. Devolve None se não deu para consultar.

    A resposta volta para o modelo local como instrução, então o pedido é por
    passo executável — não por explicação.
    """
    provedor = provedor_disponivel()
    if provedor is None:
        return None

    pergunta = (
        "Você está ajudando um agente de IA menor que travou numa tarefa.\n\n"
        f"OBJETIVO:\n{objetivo}\n\n"
        f"O QUE ELE JÁ TENTOU:\n{tentativas}\n\n"
        f"COMO ELE TRAVOU: {impasse}\n\n"
        + (f"FERRAMENTAS QUE ELE TEM: {ferramentas}\n\n" if ferramentas else "")
        + "Responda em português, em no máximo 6 linhas, com o próximo passo "
        "concreto que ele deve executar — qual ferramenta chamar e com quais "
        "argumentos, ou qual suposição dele está errada. Não explique teoria e "
        "não repita o que ele já tentou."
    )
    resposta = _consultar(pergunta, provedor, consultor)
    if resposta is None:
        return None
    log.info("[ESCALADA] conselho obtido de %s (%d chars)", provedor, len(resposta))
    return resposta


def assumir_tarefa(objetivo: str, tentativas: str, *,
                   consultor: _CONSULTOR | None = None) -> str | None:
    """
    Entrega a tarefa ao modelo forte e devolve a resposta final.

    Usado quando o conselho não resolveu. O modelo forte não tem as
    ferramentas, então o que ele pode dar é a resposta ou o caminho — e isso
    ainda é melhor do que o laço gastar 25 iterações para não entregar nada.
    """
    provedor = provedor_disponivel()
    if provedor is None:
        return None

    pergunta = (
        "Um agente de IA menor não conseguiu concluir a tarefa abaixo. "
        "Responda você, direto ao usuário, em português.\n\n"
        f"TAREFA:\n{objetivo}\n\n"
        f"O QUE FOI TENTADO (e o que se descobriu no caminho):\n{tentativas}\n\n"
        "Se os dados coletados já bastam, dê a resposta. Se não bastam, diga "
        "em uma linha o que falta e dê o melhor encaminhamento possível."
    )
    resposta = _consultar(pergunta, provedor, consultor)
    if resposta is None:
        return None
    log.info("[ESCALADA] tarefa assumida por %s (%d chars)", provedor, len(resposta))
    return resposta


def _consultar(pergunta: str, provedor: str,
               consultor: _CONSULTOR | None) -> str | None:
    fn = consultor or _consultor_padrao
    try:
        resposta = (fn(pergunta, provedor) or "").strip()
    except Exception as exc:
        log.warning("[ESCALADA] consulta a %s falhou: %s", provedor, exc)
        return None
    if not resposta or resposta.startswith("ERRO"):
        log.warning("[ESCALADA] %s não respondeu: %s", provedor, resposta[:160])
        return None
    return resposta


__all__ = [
    "POLITICAS", "POLITICA_PADRAO", "MAX_ESCALADAS",
    "Impasse", "DetectorDeImpasse",
    "politica", "provedor_disponivel", "habilitada",
    "pedir_conselho", "assumir_tarefa", "resumir_tentativas",
]
