"""
Portão de segurança do laço de agente.

O agente escreve arquivos e roda comandos de shell sozinho. Quase tudo que ele
faz é reversível — um arquivo errado se corrige, um teste que quebra se
conserta. O que não volta é pouco e dá para listar: apagar recursivamente,
sobrescrever histórico remoto do git, derrubar banco, formatar disco, executar
script baixado da internet.

Este módulo separa os dois casos. Em `trusted` (padrão) o agente trabalha sem
interrupção e só para no que é irreversível. Em `strict` toda escrita pede
confirmação. Em `off` nada é checado.

A tabela de risco continua sendo a do SafetyGate: aqui só traduzimos o
`action_type` das ferramentas para as chaves que ele já usa e acrescentamos a
classificação do texto do comando, que o gate não faz porque `run_command`
aceita shell arbitrário.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("jarvis.core.agent_safety")

NIVEIS = ("off", "trusted", "strict")
NIVEL_PADRAO = "trusted"

# action_type das ferramentas → chave do SafetyGate.RISK_LEVELS
_MAPA_ACOES = {
    "file_read": "read_file",
    "file_write": "write_file",
    "file_delete": "delete_file",
    "command_execute": "run_command",
    "web_read": "web_request",
    "api_call": "web_request",
    "memory_read": "read_file",
    "memory_write": "write_file",
    "unknown": "write_file",
}

# Comandos que não têm desfazer. Cada par é (regex, o que acontece em português).
_IRREVERSIVEIS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(padrao, re.IGNORECASE), descricao)
    for padrao, descricao in (
        (r"\brm\b(?=[^|;&]*\s-[a-z]*r)(?=[^|;&]*\s-[a-z]*f)", "apaga arquivos recursivamente, sem lixeira"),
        (r"\brm\b(?=[^|;&]*\s-[a-z]*r)(?=[^|;&]*\s--force)", "apaga arquivos recursivamente, sem lixeira"),
        (r"\brmdir\s+/s\b",                      "apaga diretório inteiro (Windows)"),
        (r"\bgit\s+push\b[^|;&]*(--force\b(?!-with-lease)|\s-f\b)", "reescreve o histórico remoto do git"),
        (r"\bgit\s+reset\s+--hard\b",            "descarta alterações locais sem recuperação"),
        (r"\bgit\s+clean\b[^|;&]*-[a-z]*f",      "apaga arquivos não versionados"),
        (r"\bgit\s+branch\s+-D\b",               "apaga branch sem checar merge"),
        (r"\bdrop\s+(database|schema|table)\b",  "destrói dados do banco"),
        (r"\btruncate\s+table\b",                "esvazia tabela do banco"),
        (r"\bdelete\s+from\b(?![^;]*\bwhere\b)", "apaga todas as linhas da tabela"),
        (r"\bmkfs(\.\w+)?\b",                    "formata sistema de arquivos"),
        (r"\bdd\b[^|;&]*\bof=/dev/",             "escreve direto no disco"),
        (r">\s*/dev/(sd|nvme|hd)",               "escreve direto no disco"),
        (r"\b(shutdown|reboot|halt|poweroff)\b", "desliga ou reinicia a máquina"),
        (r"\bsystemctl\s+(stop|disable|mask)\b", "derruba serviço do sistema"),
        (r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|k)?sh\b", "executa script baixado da internet sem revisão"),
        (r"\bchmod\b[^|;&]*-R[^|;&]*\b777\b",    "abre permissão total recursivamente"),
        (r"\bchown\b[^|;&]*-R\b",                "troca dono de árvore inteira de arquivos"),
        (r"\bdocker\s+system\s+prune\b",         "apaga imagens, volumes e containers"),
        (r"\bdocker\s+volume\s+rm\b",            "apaga volume do docker com os dados dentro"),
        (r"\bkubectl\s+delete\b",                "remove recurso do cluster"),
        (r"\bnpm\s+(publish|unpublish)\b",       "publica ou remove pacote público"),
        (r"\btwine\s+upload\b",                  "publica pacote no PyPI"),
        (r"\bhistory\s+-c\b",                    "apaga o histórico do shell"),
        (r":\(\)\s*\{\s*:\|:&\s*\}\s*;:",        "fork bomb — trava a máquina"),
        (r"\bsudo\b",                            "roda como root, fora da raiz de trabalho"),
    )
)


@dataclass
class PedidoConfirmacao:
    """O que vai para o humano decidir. Sem jargão: ele precisa entender em 2s."""
    ferramenta: str
    argumentos: dict[str, Any]
    nivel_risco: str
    motivo: str
    preview: str = ""

    def resumo(self) -> str:
        linha = f"{self.ferramenta}: {self.preview or self.motivo}"
        return f"[{self.nivel_risco.upper()}] {linha}"


@dataclass
class VeredictoSeguranca:
    permitido: bool
    precisa_confirmar: bool = False
    nivel_risco: str = "low"
    motivo: str = ""
    preview: str = ""
    pedido: PedidoConfirmacao | None = field(default=None, repr=False)


def nivel_configurado() -> str:
    """Lê JARVIS_SAFETY_LEVEL do ambiente ou da config; valor inválido vira o padrão."""
    bruto = os.getenv("JARVIS_SAFETY_LEVEL", "").strip().lower()
    if not bruto:
        try:
            from config import get_config
            bruto = str(getattr(get_config(), "safety_level", "") or "").strip().lower()
        except Exception:
            bruto = ""
    if bruto in NIVEIS:
        return bruto
    if bruto:
        log.warning("[SAFETY] nível %r desconhecido; usando %r", bruto, NIVEL_PADRAO)
    return NIVEL_PADRAO


def _risco_base(action_type: str) -> str:
    chave = _MAPA_ACOES.get(action_type, action_type)
    try:
        from core.safety_gate import SafetyGate
        return SafetyGate.RISK_LEVELS.get(chave, "medium")
    except Exception:
        return "medium"


def classificar_comando(comando: str) -> tuple[bool, str]:
    """
    Diz se um comando de shell é irreversível e por quê.

    Retorna (True, descrição) na primeira regra que casar; (False, "") se nenhuma.
    """
    texto = (comando or "").strip()
    if not texto:
        return False, ""
    for regex, descricao in _IRREVERSIVEIS:
        if regex.search(texto):
            return True, descricao
    return False, ""


def _preview(ferramenta: str, argumentos: dict[str, Any]) -> str:
    if "command" in argumentos:
        return str(argumentos["command"])[:300]
    alvo = argumentos.get("path") or argumentos.get("file") or argumentos.get("target")
    if alvo:
        return f"{ferramenta} em {alvo}"
    return ferramenta


def avaliar(ferramenta: str, argumentos: dict[str, Any] | None = None, *,
            nivel: str | None = None) -> VeredictoSeguranca:
    """
    Decide se uma chamada de ferramenta pode seguir sozinha.

    Falha aberta de propósito: se o registry ou o gate não responderem, o laço
    continua. O portão existe para proteger de ação destrutiva, não para virar
    um ponto único de parada do agente.
    """
    argumentos = argumentos or {}
    nivel = (nivel or nivel_configurado()).lower()

    if nivel == "off":
        return VeredictoSeguranca(permitido=True, motivo="portão desligado")

    try:
        from core.tool_registry import get_tool
        spec = get_tool(ferramenta)
    except Exception as exc:
        log.warning("[SAFETY] registry indisponível (%s); liberando %s", exc, ferramenta)
        return VeredictoSeguranca(permitido=True, motivo="registry indisponível")

    if spec is None:
        # Ferramenta inexistente: o laço já devolve o erro ao modelo.
        return VeredictoSeguranca(permitido=True, motivo="ferramenta desconhecida")

    if spec.read_only:
        return VeredictoSeguranca(permitido=True, motivo="somente leitura")

    risco = _risco_base(spec.action_type)
    preview = _preview(ferramenta, argumentos)

    irreversivel, porque = (False, "")
    if spec.action_type == "command_execute":
        irreversivel, porque = classificar_comando(str(argumentos.get("command", "")))
        if irreversivel:
            risco = "critical"

    if nivel == "strict" or irreversivel:
        motivo = porque or f"ação de risco {risco} fora de leitura"
        pedido = PedidoConfirmacao(
            ferramenta=ferramenta,
            argumentos=argumentos,
            nivel_risco=risco,
            motivo=motivo,
            preview=preview,
        )
        return VeredictoSeguranca(
            permitido=False,
            precisa_confirmar=True,
            nivel_risco=risco,
            motivo=motivo,
            preview=preview,
            pedido=pedido,
        )

    return VeredictoSeguranca(permitido=True, nivel_risco=risco,
                              motivo="dentro da raiz de trabalho", preview=preview)


ConfirmHandler = Callable[[PedidoConfirmacao], bool]

__all__ = [
    "NIVEIS",
    "NIVEL_PADRAO",
    "PedidoConfirmacao",
    "VeredictoSeguranca",
    "ConfirmHandler",
    "avaliar",
    "classificar_comando",
    "nivel_configurado",
]
