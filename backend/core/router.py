"""
Roteador semântico — decide qual agente atende a mensagem.

Substitui o roteamento por substring, que tem uma falha estrutural: ele casa
pedaço de frase sem olhar o sentido. Casos reais que quebram:

    "temperatura em São Paulo"        → system_agent (temperatura do PROCESSADOR)
    "que horas você tem pra me ajudar"→ time_agent
    "preciso listar meus clientes"    → file_agent (por causa de "listar")

E qualquer frase fora da lista cai no chat genérico, o que desliga na prática
as capacidades que existem no sistema.

Estratégia em três camadas, da mais barata para a mais cara:

    1. padrão ancorado  — regex com borda de palavra, só para o que é inequívoco
    2. modelo local     — classifica pelo SENTIDO, custo baixo, resposta curta
    3. palavra-chave    — a regra antiga, como rede de segurança se o modelo cair

Com cache: a mesma frase não paga classificação duas vezes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache

log = logging.getLogger("jarvis.router")

CONFIDENCE_PATTERN = 0.95
CONFIDENCE_LLM = 0.80
CONFIDENCE_KEYWORD = 0.45
CONFIDENCE_DEFAULT = 0.10


# ── O que cada agente faz ─────────────────────────────────────────────────────
# Esta descrição é o ÚNICO material que o modelo tem para decidir. Se estiver
# vaga, o roteamento erra. Escreva pensando em quem nunca viu o código.

AGENT_DESCRIPTIONS: dict[str, str] = {
    "time_agent": "Data e hora atuais. Que horas são, que dia é hoje, dia da semana.",
    "math_agent": "Conta aritmética explícita para resolver agora: somar, multiplicar, porcentagem.",
    "system_agent": "Estado DESTA máquina: uso de CPU e RAM, espaço em disco, temperatura do hardware, processos.",
    "file_agent": "Arquivos e pastas do computador: listar, criar, ler, mover, apagar, renomear.",
    "computer_agent": "Controlar o computador: abrir programa, mexer em janela, ajustar configuração do sistema.",
    "web_agent": "Buscar informação na internet, abrir site, pesquisar fato atual, notícia, preço.",
    "shell_agent": "Rodar comando de terminal, script, git, docker, instalar dependência.",
    "code_agent": "Escrever, revisar, explicar, refatorar ou depurar código.",
    "memory_agent": "Lembrar ou consultar algo de conversas anteriores, anotações, preferências do usuário.",
    "voice_agent": "Configurar voz, áudio, falar em voz alta, mudar o modo de fala.",
    "chat_agent": "Conversa geral, pergunta de conhecimento, qualquer coisa que não se encaixe acima.",
}

# Só entram aqui frases que não têm outra leitura possível.
_HIGH_CONFIDENCE_PATTERNS: list[tuple[str, str]] = [
    (r"\bque horas s[ãa]o\b", "time_agent"),
    (r"\bque dia (?:é|e) hoje\b", "time_agent"),
    (r"\bdata de hoje\b", "time_agent"),
    (r"\bwhat time is it\b", "time_agent"),
    (r"\bquanto (?:de )?(?:ram|mem[óo]ria) (?:eu )?(?:tenho|estou usando|est[áa] sendo usada)\b", "system_agent"),
    (r"\buso (?:da |do )?(?:cpu|processador)\b", "system_agent"),
    (r"\bespa[çc]o em disco\b", "system_agent"),
    (r"\bquanto (?:é|e) \d+\s*[\+\-\*/x]\s*\d+", "math_agent"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), a) for p, a in _HIGH_CONFIDENCE_PATTERNS]


@dataclass
class RouteDecision:
    agent: str
    confidence: float
    method: str           # 'pattern' | 'llm' | 'keyword' | 'default'
    reason: str = ""

    def __str__(self) -> str:
        return f"{self.agent} ({self.method}, {self.confidence:.2f})"


# ── Camada 1: padrão ancorado ─────────────────────────────────────────────────

def _by_pattern(message: str) -> RouteDecision | None:
    for rx, agent in _COMPILED:
        if rx.search(message):
            return RouteDecision(agent, CONFIDENCE_PATTERN, "pattern",
                                 f"padrão {rx.pattern!r}")
    return None


# ── Camada 2: modelo local ────────────────────────────────────────────────────

def _build_classifier_prompt(message: str) -> list[dict]:
    catalogo = "\n".join(f"- {nome}: {desc}" for nome, desc in AGENT_DESCRIPTIONS.items())
    return [
        {
            "role": "system",
            "content": (
                "Você classifica mensagens de usuário para o agente correto.\n\n"
                f"Agentes disponíveis:\n{catalogo}\n\n"
                "Responda APENAS com o nome exato de um agente da lista. "
                "Sem explicação, sem pontuação, sem aspas.\n"
                "Na dúvida entre dois, escolha o mais específico. "
                "Se nenhum servir, responda chat_agent."
            ),
        },
        {"role": "user", "content": message[:600]},
    ]


def _by_llm(message: str) -> RouteDecision | None:
    try:
        from services.llm_service import call_llm  # import tardio: evita ciclo
    except Exception as exc:
        log.debug("[ROUTER] llm_service indisponível: %s", exc)
        return None

    try:
        bruto = call_llm(_build_classifier_prompt(message), force_local=True, timeout=20)
    except Exception as exc:
        log.warning("[ROUTER] classificação falhou: %s", exc)
        return None

    # O modelo pode devolver "time_agent." ou "Agente: time_agent".
    candidato = (bruto or "").strip().lower()
    for nome in AGENT_DESCRIPTIONS:
        if re.search(rf"\b{re.escape(nome)}\b", candidato):
            return RouteDecision(nome, CONFIDENCE_LLM, "llm", f"modelo respondeu {bruto!r:.60}")

    log.debug("[ROUTER] resposta não reconhecida: %r", bruto[:80])
    return None


# ── Camada 3: palavra-chave (rede de segurança) ───────────────────────────────

def _by_keyword(message: str, rules: dict[str, list[str]]) -> RouteDecision | None:
    msg = message.lower()
    for agent, palavras in rules.items():
        for p in palavras:
            if p in msg:
                return RouteDecision(agent, CONFIDENCE_KEYWORD, "keyword",
                                     f"palavra-chave {p!r}")
    return None


# ── Roteador ──────────────────────────────────────────────────────────────────

class SmartRouter:
    """
    rules        regras de palavra-chave usadas como fallback (as antigas)
    use_llm      desligue para voltar ao comportamento puramente determinístico
    """

    def __init__(self, rules: dict[str, list[str]] | None = None, *, use_llm: bool = True):
        self.rules = rules or {}
        self.use_llm = use_llm
        self._cache: dict[str, RouteDecision] = {}

    def route(self, message: str) -> RouteDecision:
        chave = message.strip().lower()[:200]
        if chave in self._cache:
            return self._cache[chave]

        decisao = _by_pattern(message)

        if decisao is None and self.use_llm:
            decisao = _by_llm(message)

        if decisao is None:
            decisao = _by_keyword(message, self.rules)

        if decisao is None:
            decisao = RouteDecision("chat_agent", CONFIDENCE_DEFAULT, "default",
                                    "nenhuma camada decidiu")

        if len(self._cache) > 512:
            self._cache.clear()
        self._cache[chave] = decisao

        log.info("[ROUTER] %.50s → %s", message, decisao)
        return decisao

    def route_name(self, message: str) -> str:
        """Compatível com a assinatura antiga, que devolvia só o nome."""
        return self.route(message).agent


__all__ = ["SmartRouter", "RouteDecision", "AGENT_DESCRIPTIONS"]
