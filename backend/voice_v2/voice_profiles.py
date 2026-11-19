"""
Perfis de voz do JARVIS.

O que faz uma voz soar como o JARVIS do Stark não é a identidade de quem fala
— é o CARÁTER dela: grave, pausada, articulada, sem entusiasmo. Uma voz que
informa, não que vende. O Ultron é a mesma base puxada para baixo e para
devagar, com pausas maiores: o que assusta nele é a calma, não o volume.

Isso se obtém com três controles do edge-tts:

    voice   timbre base
    rate    velocidade — negativo deixa pausado e deliberado
    pitch   altura — negativo aprofunda

Nomes de voz mudam de tempos em tempos no serviço da Microsoft. Por isso cada
perfil declara uma cadeia de fallback, e `resolver_voz()` confere contra a
lista real antes de usar. Nome inválido falharia silenciosamente na hora de
falar — o pior tipo de defeito.

Uso:

    from voice_v2.voice_profiles import perfil, PERFIS
    p = perfil("jarvis")
    comm = edge_tts.Communicate(texto, p.voice, rate=p.rate, pitch=p.pitch)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

log = logging.getLogger("jarvis.voice.profiles")


@dataclass(frozen=True)
class PerfilVoz:
    nome: str
    descricao: str
    voice: str
    rate: str
    pitch: str
    # Tentadas em ordem se `voice` não existir no serviço.
    alternativas: tuple[str, ...] = field(default_factory=tuple)

    def como_dict(self) -> dict[str, str]:
        return {
            "nome": self.nome,
            "descricao": self.descricao,
            "voice": self.voice,
            "rate": self.rate,
            "pitch": self.pitch,
        }


# pt-BR-AntonioNeural e en-GB-RyanNeural são as duas que este projeto já usa,
# então são as únicas que posso afirmar que existem. As demais entram como
# alternativa, e a validação decide.
PERFIS: dict[str, PerfilVoz] = {
    "jarvis": PerfilVoz(
        nome="jarvis",
        descricao=(
            "Assistente formal: grave, pausado, articulado. Informa sem "
            "entusiasmo. É o registro do mordomo britânico, em português."
        ),
        voice="pt-BR-AntonioNeural",
        rate="-14%",
        pitch="-18Hz",
        alternativas=("pt-BR-FabioNeural", "pt-PT-DuarteNeural"),
    ),
    "jarvis_en": PerfilVoz(
        nome="jarvis_en",
        descricao="O mesmo registro, em inglês britânico.",
        voice="en-GB-RyanNeural",
        rate="-10%",
        pitch="-12Hz",
        alternativas=("en-GB-ThomasNeural", "en-US-GuyNeural"),
    ),
    "ultron": PerfilVoz(
        nome="ultron",
        descricao=(
            "Mais fundo e mais lento que o jarvis, com pausas maiores. "
            "A ameaça vem da calma, não do volume."
        ),
        voice="pt-BR-AntonioNeural",
        rate="-22%",
        pitch="-32Hz",
        alternativas=("pt-BR-FabioNeural", "pt-PT-DuarteNeural"),
    ),
    "operacional": PerfilVoz(
        nome="operacional",
        descricao="Rápido e direto, para quando você quer a resposta e não o clima.",
        voice="pt-BR-AntonioNeural",
        rate="+6%",
        pitch="-6Hz",
        alternativas=("pt-BR-FabioNeural",),
    ),
    "neutro": PerfilVoz(
        nome="neutro",
        descricao="Sem tratamento: a voz como o serviço entrega.",
        voice="pt-BR-AntonioNeural",
        rate="+0%",
        pitch="+0Hz",
        alternativas=("pt-BR-FabioNeural",),
    ),
}

PERFIL_PADRAO = "jarvis"

# Cache da lista real de vozes: a consulta é de rede e não muda durante a sessão.
_vozes_disponiveis: set[str] | None = None


async def listar_vozes(force: bool = False) -> set[str]:
    """Nomes de voz que o serviço realmente oferece. Vazio se não der para consultar."""
    global _vozes_disponiveis
    if _vozes_disponiveis is not None and not force:
        return _vozes_disponiveis
    try:
        import edge_tts
        vozes = await edge_tts.list_voices()
        _vozes_disponiveis = {v["ShortName"] for v in vozes}
        log.info("[VOZ] %d vozes disponíveis", len(_vozes_disponiveis))
    except Exception as exc:
        # Sem rede, confiamos no perfil. Melhor tentar do que ficar mudo.
        log.warning("[VOZ] não consegui listar vozes (%s) — usando o perfil sem validar", exc)
        _vozes_disponiveis = set()
    return _vozes_disponiveis


async def resolver_voz(p: PerfilVoz | str | None) -> str:
    """
    Devolve o primeiro nome de voz do perfil que exista de fato.

    Aceita o perfil ou o nome dele — todas as outras funções públicas daqui
    recebem string, e a assimetria só rendia AttributeError em quem chamava.

    Se a lista não puder ser consultada, devolve a primeira escolha: ficar mudo
    por excesso de zelo é pior do que tentar.
    """
    if not isinstance(p, PerfilVoz):
        p = perfil(p)
    disponiveis = await listar_vozes()
    if not disponiveis:
        return p.voice
    for candidata in (p.voice, *p.alternativas):
        if candidata in disponiveis:
            if candidata != p.voice:
                log.warning("[VOZ] %r indisponível — usando %r", p.voice, candidata)
            return candidata
    log.error("[VOZ] nenhuma voz do perfil %r existe — usando %r assim mesmo",
              p.nome, p.voice)
    return p.voice


def perfil(nome: str | None = None) -> PerfilVoz:
    """Perfil pelo nome, caindo no padrão se não existir."""
    chave = (nome or PERFIL_PADRAO).strip().lower()
    encontrado = PERFIS.get(chave)
    if encontrado is None:
        log.warning("[VOZ] perfil %r não existe — usando %r", nome, PERFIL_PADRAO)
        return PERFIS[PERFIL_PADRAO]
    return encontrado


def listar_perfis() -> list[dict[str, str]]:
    return [p.como_dict() for p in PERFIS.values()]


async def parametros_de_fala(nome: str | None = None) -> dict[str, str]:
    """
    Tudo que o edge_tts.Communicate precisa, com a voz já validada.

        p = await parametros_de_fala("ultron")
        edge_tts.Communicate(texto, p["voice"], rate=p["rate"], pitch=p["pitch"])
    """
    p = perfil(nome)
    return {"voice": await resolver_voz(p), "rate": p.rate, "pitch": p.pitch}


__all__ = [
    "PerfilVoz", "PERFIS", "PERFIL_PADRAO", "perfil", "listar_perfis",
    "listar_vozes", "resolver_voz", "parametros_de_fala",
]
