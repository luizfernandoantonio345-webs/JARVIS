"""
Porteiro de verificação: o agente não declara pronto o que não conferiu.

O SYSTEM_PROMPT já diz "um trabalho só está pronto quando você viu funcionar".
Modelo grande obedece; 7B escreve o arquivo, diz "pronto, Sir" e encerra. Dizer
de novo, com mais ênfase, não resolve — prompt não é garantia de comportamento.

Então aqui a regra é mecânica. O laço registra o que foi alterado e o que foi
conferido. Quando o modelo tenta encerrar com alteração não conferida, o laço
não aceita: devolve a lista exata do que falta verificar e manda continuar.

Depois de duas tentativas, aceita e avisa. Insistir além disso viraria loop, e
uma resposta honesta ("alterei e não consegui conferir") vale mais do que o
agente girando até bater o teto.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger("jarvis.core.verification")

MAX_COBRANCAS = 2

# Comandos que contam como conferência de verdade. `echo ok` não conta.
_CONFERENCIAS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\bpytest\b", r"\bunittest\b", r"\bpy_compile\b", r"\bpython\s+-m\s+\w",
    r"\bnpm\s+(test|run\s+(test|build|lint|typecheck))\b", r"\byarn\s+(test|build)\b",
    r"\bpnpm\s+(test|build)\b", r"\bnode\s+--check\b", r"\bnode\s+-e\b",
    r"\bruff\b", r"\bflake8\b", r"\bmypy\b", r"\bpylint\b", r"\btsc\b", r"\beslint\b",
    r"\bcargo\s+(test|check|build)\b", r"\bgo\s+(test|build|vet)\b",
    r"\bmvn\s+test\b", r"\bgradle\s+test\b", r"\bdotnet\s+test\b",
    r"\bcurl\b.*\blocalhost\b", r"\bcurl\b.*\b127\.0\.0\.1\b",
    r"\bgit\s+diff\b", r"\bgit\s+status\b",
    r"\bpython3?\s+\S+\.py\b", r"\bbash\s+-n\b", r"\bsh\s+-n\b",
))

_EXIT_ZERO = re.compile(r"exit_code:\s*0\b")


def e_conferencia(nome: str, argumentos: dict, resultado: str, erro: bool) -> bool:
    """
    Diz se esta chamada serve como prova de que o trabalho funciona.

    Conferência que falhou não limpa a pendência — mas o erro já volta para o
    modelo pelo caminho normal, e é com ele que o agente se corrige.
    """
    if erro:
        return False
    if nome != "run_command":
        return False
    comando = str(argumentos.get("command", ""))
    if not any(r.search(comando) for r in _CONFERENCIAS):
        return False
    # Sem exit_code 0 não houve prova; o run_command sempre devolve a linha.
    return bool(_EXIT_ZERO.search(resultado or ""))


def _descrever(nome: str, argumentos: dict) -> str:
    alvo = argumentos.get("path") or argumentos.get("file") or ""
    if alvo:
        return f"{nome} em {alvo}"
    comando = argumentos.get("command")
    if comando:
        return f"{nome}: {str(comando)[:80]}"
    return nome


@dataclass
class RastreadorDeVerificacao:
    """
    Guarda o que mudou desde a última conferência bem-sucedida.

    Só alteração entra na conta: leitura não precisa de prova, e comando que
    não altera nada (um `ls`) também não.
    """

    _pendentes: list[str] = field(default_factory=list)
    cobrancas: int = 0
    # Tarefa só de leitura não tem o que provar: sem isto, "nada pendente"
    # seria confundido com "conferido".
    houve_alteracao: bool = False

    def registrar(self, nome: str, argumentos: dict, resultado: str,
                  erro: bool, read_only: bool) -> None:
        if e_conferencia(nome, argumentos, resultado, erro):
            if self._pendentes:
                log.info("[VERIFY] conferido: %s", ", ".join(self._pendentes))
            self._pendentes.clear()
            return
        if read_only or erro:
            return
        if nome == "run_command" and not _alterou_algo(argumentos):
            return
        self.houve_alteracao = True
        descricao = _descrever(nome, argumentos)
        if descricao not in self._pendentes:
            self._pendentes.append(descricao)

    @property
    def pendentes(self) -> list[str]:
        return list(self._pendentes)

    def tudo_conferido(self) -> bool:
        return not self._pendentes

    def pode_cobrar(self) -> bool:
        return self.cobrancas < MAX_COBRANCAS

    def cobrar(self) -> str:
        """Texto que volta para o modelo nomeando o que falta conferir."""
        self.cobrancas += 1
        lista = "\n".join(f"- {p}" for p in self._pendentes)
        return (
            "Você alterou isto e não conferiu:\n\n"
            f"{lista}\n\n"
            "Não encerre ainda. Rode a verificação com run_command — os testes "
            "do projeto, ou o comando que prova que o que você fez funciona — e "
            "leia a saída. Se falhar, corrija e rode de novo. Se não houver "
            "teste que cubra isso, diga qual comando você usou para conferir."
        )

    def aviso_final(self) -> str:
        """Uma linha honesta para o usuário quando não deu para conferir."""
        return ("\n\n⚠ Não consegui confirmar que isso funciona: "
                + ", ".join(self._pendentes)
                + ". Vale conferir antes de confiar.")


def _alterou_algo(argumentos: dict) -> bool:
    """Comando que só olha não precisa de prova."""
    comando = str(argumentos.get("command", "")).strip().lower()
    if not comando:
        return False
    inofensivos = ("ls", "cat", "head", "tail", "grep", "find", "pwd", "which",
                   "echo", "wc", "git status", "git log", "git diff", "tree",
                   "ollama list", "pip list", "pip show", "python --version")
    return not any(comando.startswith(p) for p in inofensivos)


__all__ = ["RastreadorDeVerificacao", "e_conferencia", "MAX_COBRANCAS"]
