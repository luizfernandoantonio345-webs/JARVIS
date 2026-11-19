"""
Teste de ponta a ponta do caminho do agente no WebSocket.

Fala com o app pela interface ASGI, sem TestClient: o portal bloqueante do
Starlette entra em deadlock com o `asyncio_mode = auto` do pytest.ini, e aqui
o alvo é o protocolo, não o cliente HTTP. Sem threads e sem portal, cada
mensagem é entregue e lida na ordem — nenhuma corrida de tempo.

`run_agent` é substituído por dublês. O que está sendo verificado é o contrato
entre backend e frontend: os eventos chegam, a pergunta de confirmação chega
com id, a resposta do cliente destrava a thread do laço, e "bom dia" não
aciona o laço.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.agent_loop import AgentResult           # noqa: E402
from core.agent_safety import PedidoConfirmacao   # noqa: E402


# ── Cliente WebSocket sobre ASGI ──────────────────────────────────────────────

class SocketFalso:
    """Cliente WebSocket mínimo, direto no app ASGI."""

    def __init__(self, app, caminho: str = "/ws/jarvis") -> None:
        self._app = app
        self._caminho = caminho
        self._para_app: asyncio.Queue = asyncio.Queue()
        self._do_app: asyncio.Queue = asyncio.Queue()
        self._tarefa: asyncio.Task | None = None

    async def __aenter__(self) -> "SocketFalso":
        scope = {
            "type": "websocket", "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1", "scheme": "ws",
            "path": self._caminho, "raw_path": self._caminho.encode(),
            "query_string": b"", "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
            "subprotocols": [], "state": {},
        }
        await self._para_app.put({"type": "websocket.connect"})
        self._tarefa = asyncio.create_task(
            self._app(scope, self._para_app.get, self._do_app.put))
        primeira = await self._bruta()
        assert primeira["type"] == "websocket.accept", primeira
        return self

    async def __aexit__(self, *_) -> None:
        await self._para_app.put({"type": "websocket.disconnect", "code": 1000})
        if self._tarefa:
            try:
                await asyncio.wait_for(self._tarefa, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._tarefa.cancel()

    async def _bruta(self, timeout: float = 10.0) -> dict:
        return await asyncio.wait_for(self._do_app.get(), timeout=timeout)

    async def enviar(self, texto: str) -> None:
        await self._para_app.put({"type": "websocket.receive", "text": texto})

    async def receber(self, timeout: float = 10.0) -> dict:
        """Próxima mensagem JSON do servidor, pulando o heartbeat."""
        while True:
            m = await self._bruta(timeout)
            if m["type"] == "websocket.close":
                raise AssertionError(f"servidor fechou: {m}")
            if m["type"] != "websocket.send":
                continue
            dados = json.loads(m.get("text") or "{}")
            if dados.get("type") in ("ping", "pong"):
                continue
            return dados

    async def coletar(self, ate: str, limite: int = 25) -> list[dict]:
        """Lê até ver uma mensagem do tipo `ate`; o limite evita teste travado."""
        recebidas = []
        for _ in range(limite):
            m = await self.receber()
            recebidas.append(m)
            if m.get("type") == ate:
                return recebidas
        raise AssertionError(f"{ate!r} não chegou em {limite} mensagens: {recebidas}")


@pytest.fixture
def app():
    import main
    return main.app


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """
    O caminho de conversa tenta o Ollama e espera 120s por tentativa. Nenhum
    teste aqui quer exercitar isso: o alvo é o protocolo do socket.
    """
    import agents.master_orchestrator as mo

    class _Orquestrador:
        async def execute(self, texto, session_id, on_token=None):
            resposta = "Bom dia, Sir."
            if on_token:
                await on_token(resposta)
            return resposta

    monkeypatch.setattr(mo, "get_orchestrator", lambda: _Orquestrador())


def _pedido(comando: str = "rm -rf build", motivo: str = "apaga arquivos recursivamente, sem lixeira"):
    return PedidoConfirmacao(
        ferramenta="run_command", argumentos={"command": comando},
        nivel_risco="critical", motivo=motivo, preview=comando,
    )


# ── Caminho do agente ─────────────────────────────────────────────────────────

async def test_pedido_de_trabalho_aciona_o_laco(app, monkeypatch):
    from core import agent_bridge as ab

    def dubl(objetivo, **kw):
        emit = kw["on_event"]
        emit("tool_call", {"name": "read_file", "arguments": {"path": "main.py"}})
        emit("tool_result", {"name": "read_file", "error": False, "result": "..."})
        emit("done", {"reason": "completed", "iterations": 1})
        return AgentResult(final_text="Li o arquivo, Sir.", iterations=1)

    monkeypatch.setattr(ab, "run_agent", dubl)

    async with SocketFalso(app) as ws:
        await ws.receber()                      # saudação
        await ws.enviar("lê o arquivo backend/main.py e me diz o que tem nele")
        msgs = await ws.coletar(ate="done")

        eventos = [m["event"] for m in msgs if m.get("type") == "agent_event"]
        texto = "".join(m.get("content", "") for m in msgs if m.get("type") == "token")
        assert "tool_call" in eventos and "done" in eventos, msgs
        assert "Li o arquivo" in texto
        assert next(m for m in msgs if m.get("type") == "done")["action"] == "agent"


async def test_conversa_nao_aciona_o_laco(app, monkeypatch):
    """"bom dia" não pode custar 25 idas ao modelo."""
    from core import agent_bridge as ab
    chamou = {"sim": False}

    def dubl(objetivo, **kw):
        chamou["sim"] = True
        return AgentResult(final_text="nunca deveria chegar aqui")

    monkeypatch.setattr(ab, "run_agent", dubl)

    async with SocketFalso(app) as ws:
        await ws.receber()
        await ws.enviar("bom dia")
        msgs = await ws.coletar(ate="done")
        assert chamou["sim"] is False
        assert next(m for m in msgs if m.get("type") == "done")["action"] == "chat"


# ── Confirmação atravessando a rede ───────────────────────────────────────────

async def test_confirmacao_vai_e_volta_pelo_socket(app, monkeypatch):
    from core import agent_bridge as ab
    decisao = {}

    def dubl(objetivo, **kw):
        decisao["aprovado"] = kw["confirm_handler"](_pedido())
        return AgentResult(final_text="Feito, Sir.")

    monkeypatch.setattr(ab, "run_agent", dubl)

    async with SocketFalso(app) as ws:
        await ws.receber()
        await ws.enviar("apaga a pasta build do projeto")

        pedido = (await ws.coletar(ate="agent_confirm"))[-1]
        assert pedido["id"] and pedido["risk"] == "critical"
        assert pedido["preview"] == "rm -rf build"
        assert pedido["reason"] and pedido["timeout_s"] > 0

        await ws.enviar(f"__confirm__:{pedido['id']}:yes")
        ack = (await ws.coletar(ate="agent_confirm_ack"))[-1]
        assert ack["approved"] is True and ack["handled"] is True

        await ws.coletar(ate="done")
        assert decisao["aprovado"] is True


async def test_negar_pelo_socket_bloqueia(app, monkeypatch):
    from core import agent_bridge as ab
    decisao = {}

    def dubl(objetivo, **kw):
        decisao["aprovado"] = kw["confirm_handler"](
            _pedido("git push --force", "reescreve o histórico remoto do git"))
        return AgentResult(final_text="Não executei.")

    monkeypatch.setattr(ab, "run_agent", dubl)

    async with SocketFalso(app) as ws:
        await ws.receber()
        await ws.enviar("faz um git push --force na main")
        pedido = (await ws.coletar(ate="agent_confirm"))[-1]
        await ws.enviar(f"__confirm__:{pedido['id']}:no")
        await ws.coletar(ate="agent_confirm_ack")
        await ws.coletar(ate="done")
        assert decisao["aprovado"] is False


async def test_confirmacao_orfa_recebe_ack_negativo(app):
    """Resposta sem laço rodando não pode explodir a conexão."""
    async with SocketFalso(app) as ws:
        await ws.receber()
        await ws.enviar("__confirm__:deadbeef:yes")
        ack = await ws.receber()
        assert ack["type"] == "agent_confirm_ack"
        assert ack["handled"] is False
