"""
Ponte entre o laço de agente (síncrono, bloqueante) e o mundo async do
WebSocket.

Três problemas para resolver:

1. `run_agent` é síncrono e faz chamadas HTTP bloqueantes. Rodar direto no
   event loop congela o servidor inteiro — vai para uma thread.
2. Os eventos nascem na thread e precisam chegar ao cliente pelo loop. Passam
   por uma fila, postados com `call_soon_threadsafe`.
3. A confirmação de ação irreversível tem que bloquear a thread até o humano
   responder do outro lado da rede — ou liberar sozinha se ele fechou a aba.
   `threading.Event` com timeout, recusando no estouro.

Sem WebSocket nenhum nada aqui depende: `enviar` é qualquer callable async que
receba dict. Isso deixa a ponte testável sem subir servidor.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .agent_loop import AgentResult, run_agent
from .agent_safety import PedidoConfirmacao

log = logging.getLogger("jarvis.core.agent_bridge")

TIMEOUT_CONFIRMACAO = 120.0

# Marca o fim da fila de eventos. Sem ela, "tarefa acabou e fila vazia" é um
# falso fim: call_soon_threadsafe só agenda o put_nowait, e um laço rápido
# termina antes de o callback rodar — os eventos iam para o lixo.
_FIM = object()

Enviar = Callable[[dict[str, Any]], Awaitable[None]]


# ── Quando vale acionar o laço com ferramentas ────────────────────────────────

# "oi" não precisa de 9 schemas de ferramenta no contexto nem de 25 iterações.
# Modelo pequeno com ferramenta demais na frente se perde. Estes são os sinais
# de que o pedido é trabalho, não conversa.
_SINAIS_DE_TAREFA = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\b(cria|crie|criar|escrev[ae]|escrever|implementa|implemente|implementar)\b",
    r"\b(conserta|consert[ae]|corrig[ei]|corrigir|arruma|arrume|ajusta|ajuste)\b",
    r"\b(roda|rode|rodar|executa|execute|executar|testa|teste|testar)\b",
    r"\b(l[êe]|ler|abre|abra|abrir|mostra|mostre)\s+(o\s+)?(arquivo|c[óo]digo|arq)\b",
    r"\b(procura|procure|busca|busque|pesquisa|pesquise)\b",
    r"\b(refatora|refatore|refatorar|renomeia|renomeie|move|mover|apaga|apague)\b",
    r"\b(commit|git|pytest|npm|pip|docker|branch|deploy)\b",
    r"\b(analisa|analise|analisar|revisa|revise|revisar)\s+\S+",
    r"\barquivo\b.*\b(onde|qual|existe|tem)\b",
    r"\.(py|js|ts|tsx|json|md|yml|yaml|html|css|sql|bat|sh)\b",
    r"\b(instala|instale|instalar|configura|configure|configurar)\b",
    r"\b(write|create|fix|run|read|search|refactor|implement)\b",
))

_CONVERSA_CURTA = re.compile(
    r"^\s*(oi|ol[áa]|e a[íi]|bom dia|boa tarde|boa noite|tudo bem|beleza|valeu|"
    r"obrigad[oa]|t[áa]|ok|sim|n[ãa]o|jarvis|hey jarvis|hi|hello|thanks)\s*[!.?]*\s*$",
    re.IGNORECASE)


def precisa_de_ferramentas(texto: str) -> bool:
    """
    Diz se o pedido pede o laço com ferramentas ou a conversa normal.

    Erra para o lado da conversa: um falso negativo custa uma repetição do
    usuário, um falso positivo custa dezenas de chamadas ao modelo.
    """
    t = (texto or "").strip()
    if not t or _CONVERSA_CURTA.match(t):
        return False
    if len(t) < 12:
        return False
    return any(regex.search(t) for regex in _SINAIS_DE_TAREFA)


# ── Ponte ─────────────────────────────────────────────────────────────────────

@dataclass
class _Pendencia:
    evento: threading.Event = field(default_factory=threading.Event)
    aprovado: bool = False


class PonteAgente:
    """
    Roda o laço numa thread e entrega os eventos por `enviar`.

        ponte = PonteAgente(enviar=ws.send_json)
        resultado = await ponte.executar("roda os testes e conserta o que quebrar")

    Quando o laço pedir confirmação, `enviar` recebe
    {'type': 'agent_confirm', 'id': ..., 'name': ..., 'risk': ..., 'preview': ...}
    e o cliente responde chamando `responder(id, True|False)`.
    """

    def __init__(self, *, enviar: Enviar,
                 timeout_confirmacao: float = TIMEOUT_CONFIRMACAO,
                 auto_aprovar: bool = False) -> None:
        self._enviar = enviar
        self._timeout = timeout_confirmacao
        self._auto_aprovar = auto_aprovar
        self._pendencias: dict[str, _Pendencia] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._fila: asyncio.Queue | None = None

    # — chamado pelo cliente, no loop —

    def responder(self, id_pedido: str, aprovado: bool) -> bool:
        """Libera a thread que está esperando. False se o pedido não existe mais."""
        with self._lock:
            pendencia = self._pendencias.pop(id_pedido, None)
        if pendencia is None:
            log.warning("[PONTE] confirmação %r desconhecida ou já expirada", id_pedido)
            return False
        pendencia.aprovado = bool(aprovado)
        pendencia.evento.set()
        return True

    def pendencias_abertas(self) -> list[str]:
        with self._lock:
            return list(self._pendencias)

    # — chamados na thread do laço —

    def _postar(self, mensagem: dict[str, Any]) -> None:
        if self._loop is None or self._fila is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._fila.put_nowait, mensagem)
        except RuntimeError:  # loop fechou no meio
            log.debug("[PONTE] loop indisponível; evento descartado")

    def _on_event(self, tipo: str, dados: dict[str, Any]) -> None:
        # confirm_required vem antes do handler e não carrega id: quem avisa o
        # cliente de forma acionável é o handler abaixo.
        if tipo == "confirm_required":
            return
        self._postar({"type": "agent_event", "event": tipo, **dados})

    def _confirmar(self, pedido: PedidoConfirmacao) -> bool:
        if self._auto_aprovar:
            log.info("[PONTE] auto-aprovado: %s", pedido.resumo())
            return True

        id_pedido = uuid.uuid4().hex[:12]
        pendencia = _Pendencia()
        with self._lock:
            self._pendencias[id_pedido] = pendencia

        self._postar({
            "type": "agent_confirm",
            "id": id_pedido,
            "name": pedido.ferramenta,
            "risk": pedido.nivel_risco,
            "reason": pedido.motivo,
            "preview": pedido.preview,
            "timeout_s": self._timeout,
        })

        if not pendencia.evento.wait(self._timeout):
            with self._lock:
                self._pendencias.pop(id_pedido, None)
            log.warning("[PONTE] confirmação expirou em %.0fs — recusando: %s",
                        self._timeout, pedido.resumo())
            self._postar({"type": "agent_confirm_timeout", "id": id_pedido,
                          "name": pedido.ferramenta})
            return False
        return pendencia.aprovado

    # — entrada pública —

    async def executar(self, objetivo: str, *, session_id: str | None = None,
                       history: list[dict] | None = None,
                       max_iterations: int | None = None,
                       use_memory: bool = True,
                       safety_level: str | None = None) -> AgentResult:
        self._loop = asyncio.get_running_loop()
        self._fila = asyncio.Queue()

        kwargs: dict[str, Any] = {
            "history": history,
            "session_id": session_id,
            "use_memory": use_memory,
            "on_event": self._on_event,
            "confirm_handler": self._confirmar,
            "safety_level": safety_level,
        }
        if max_iterations is not None:
            kwargs["max_iterations"] = max_iterations

        def _trabalho():
            # A sentinela vai no finally: erro no laço também tem que fechar a
            # fila, senão a drenagem fica esperando um evento que não vem.
            try:
                return run_agent(objetivo, **kwargs)
            finally:
                self._postar(_FIM)

        tarefa = asyncio.create_task(asyncio.to_thread(_trabalho))
        drenagem = asyncio.create_task(self._drenar(tarefa))
        try:
            resultado = await tarefa
        finally:
            await drenagem           # escoa tudo até a sentinela
            self._descartar_pendencias()
        return resultado

    async def _drenar(self, tarefa: asyncio.Task) -> None:
        """
        Entrega eventos até a sentinela.

        `to_thread` resolve a tarefa pelo mesmo call_soon_threadsafe, e a fila é
        FIFO: quando `tarefa.done()` fica visível, a sentinela já entrou. O
        timeout é só para o caso de o loop ter fechado no meio e a sentinela ter
        se perdido — travar aqui prenderia a resposta do usuário para sempre.
        """
        assert self._fila is not None
        while True:
            try:
                mensagem = await asyncio.wait_for(self._fila.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if tarefa.done():
                    log.debug("[PONTE] sentinela não chegou; encerrando drenagem")
                    return
                continue
            if mensagem is _FIM:
                return
            try:
                await self._enviar(mensagem)
            except Exception as exc:  # cliente caiu; o laço segue até o fim
                log.debug("[PONTE] envio falhou: %s", exc)

    def _descartar_pendencias(self) -> None:
        """Se o laço acabou, ninguém mais espera resposta: solta as threads."""
        with self._lock:
            abertas = list(self._pendencias.values())
            self._pendencias.clear()
        for pendencia in abertas:
            pendencia.aprovado = False
            pendencia.evento.set()


# ── Protocolo de resposta do cliente ──────────────────────────────────────────

_RESPOSTA = re.compile(r"^__confirm__:([0-9a-f]{4,32}):(yes|no|sim|nao|não)$",
                       re.IGNORECASE)


def ler_resposta_confirmacao(texto: str) -> tuple[str, bool] | None:
    """
    Reconhece `__confirm__:<id>:yes|no` vindo do cliente.

    Devolve (id, aprovado) ou None se a mensagem é outra coisa.
    """
    m = _RESPOSTA.match((texto or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2).lower() in ("yes", "sim")


__all__ = [
    "PonteAgente",
    "precisa_de_ferramentas",
    "ler_resposta_confirmacao",
    "TIMEOUT_CONFIRMACAO",
]
