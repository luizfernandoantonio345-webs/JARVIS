"""
Agent loop — o laço que transforma o JARVIS de gerador de texto em agente.

O ciclo é este, e é ele que faz a diferença:

    modelo decide chamar ferramenta
        → nós executamos
        → o RESULTADO volta para o modelo
        → ele vê o que deu certo, o que deu erro, e corrige
        → repete até terminar

Sem essa volta, o modelo escreve código que parece certo. Com ela, ele roda o
teste, lê o traceback e conserta. É a diferença entre parecer e funcionar.

Três defesas contra "se perder", que é a falha clássica de agente longo:

    1. Teto de iterações        — nunca roda para sempre
    2. Compactação de contexto  — conversa longa é resumida, não truncada no meio
    3. Objetivo reafirmado      — o alvo volta ao contexto a cada compactação

Uso:

    from core.agent_loop import run_agent
    resultado = run_agent("Corrija o teste que está falhando em test_api.py")
    print(resultado.final_text)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from .tool_registry import all_tools, get_tool, schemas_for, truncate
from . import tools_web      # noqa: F401  — registra as ferramentas de web
from . import tools_memory   # noqa: F401  — registra as ferramentas de memória
from . import agent_safety
from .agent_safety import ConfirmHandler, PedidoConfirmacao

log = logging.getLogger("jarvis.agent")

MAX_ITERATIONS = int(os.getenv("JARVIS_AGENT_MAX_ITERATIONS", "25"))
COMPACT_AFTER_MESSAGES = int(os.getenv("JARVIS_AGENT_COMPACT_AFTER", "40"))
REQUEST_TIMEOUT = 180

SYSTEM_PROMPT = """Você é o JARVIS, assistente pessoal do Luiz Fernando, desenvolvedor back-end.

Você tem ferramentas de verdade. Use-as. Não descreva o que faria — faça.

Como trabalhar:

1. ENTENDA antes de agir. Leia os arquivos envolvidos com read_file e search_code
   antes de alterar qualquer coisa. Nunca edite um arquivo que você não leu.

2. AJA em passos pequenos e verificáveis. Uma alteração, uma verificação.

3. VERIFIQUE sempre. Depois de mexer em código, rode os testes ou execute o que
   for necessário com run_command. Se falhar, leia o erro e corrija. Um trabalho
   só está pronto quando você viu funcionar, não quando parece certo.

4. BUSQUE em vez de inventar. Se não souber a versão de uma biblioteca, a sintaxe
   de uma API ou qualquer fato atual, use web_search. Nunca invente nome de função,
   parâmetro ou endpoint. Se precisar de raciocínio além do seu alcance, use
   ask_stronger_model com uma pergunta completa.

5. USE A MEMÓRIA. Você conversa com a mesma pessoa há tempo, não com um
   estranho a cada vez.
   - recall antes de perguntar algo que talvez já tenha sido dito, e sempre que
     ele mencionar algo como se você já soubesse ("aquele projeto", "como
     combinamos").
   - remember quando algo for decidido ou quando ele contar algo que vai
     importar depois. Grave o fato em uma ou duas frases, não a conversa.
   - remember_preference quando ele corrigir seu comportamento. "responde mais
     curto", "não me explica o básico", "prefere Postgres a Mongo" — isso é
     como ele quer trabalhar, e você deve lembrar sem ele repetir.
   - search_knowledge para consultar documentação e código já indexados.

6. SEJA HONESTO sobre o que não deu certo. Se tentou três caminhos e nenhum
   funcionou, diga isso e explique o que descobriu. Não entregue algo quebrado
   dizendo que está pronto.

Quando a tarefa estiver concluída, responda em texto, sem chamar mais ferramentas,
dizendo o que você fez e o que verificou."""


# ── Resultado ─────────────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: str = ""
    error: bool = False
    duration_ms: int = 0


@dataclass
class AgentResult:
    final_text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    iterations: int = 0
    stopped_reason: str = "completed"
    messages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.stopped_reason == "completed"


# ── Camada de provedor ────────────────────────────────────────────────────────

def _provider() -> str:
    """Escolhe o provedor pelas chaves disponíveis; cai no Ollama local."""
    forced = os.getenv("JARVIS_AGENT_PROVIDER", "").strip().lower()
    if forced:
        return forced
    if os.getenv("JARVIS_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("JARVIS_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "ollama"


def _anthropic_turn(messages: list[dict], tools: list[dict]) -> dict[str, Any]:
    key = os.getenv("JARVIS_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
    model = os.getenv("JARVIS_ANTHROPIC_MODEL", "claude-sonnet-4-5")
    with httpx.Client(timeout=REQUEST_TIMEOUT) as c:
        resp = c.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 8192,
                "system": SYSTEM_PROMPT,
                "messages": messages,
                "tools": tools,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    calls = [
        ToolCall(name=b["name"], arguments=b.get("input", {}))
        for b in data.get("content", [])
        if b.get("type") == "tool_use"
    ]
    ids = [b["id"] for b in data.get("content", []) if b.get("type") == "tool_use"]
    return {"text": text, "calls": calls, "ids": ids, "raw": data.get("content", [])}


def _openai_compatible_turn(messages: list[dict], tools: list[dict], base: str,
                            model: str, key: str | None) -> dict[str, Any]:
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "tools": tools,
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT) as c:
        resp = c.post(f"{base}/chat/completions", headers=headers, json=payload)
    resp.raise_for_status()
    msg = resp.json()["choices"][0]["message"]
    calls = []
    ids = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(name=fn.get("name", ""), arguments=args))
        ids.append(tc.get("id", ""))
    return {"text": msg.get("content") or "", "calls": calls, "ids": ids, "raw": msg}


def _one_turn(messages: list[dict]) -> dict[str, Any]:
    provider = _provider()
    if provider == "anthropic":
        return _anthropic_turn(messages, schemas_for("anthropic"))
    if provider == "openai":
        return _openai_compatible_turn(
            messages, schemas_for("openai"), "https://api.openai.com/v1",
            os.getenv("JARVIS_OPENAI_MODEL", "gpt-4o"),
            os.getenv("JARVIS_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"),
        )
    base = os.getenv("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/v1"
    return _openai_compatible_turn(
        messages, schemas_for("openai"), base,
        os.getenv("JARVIS_MODEL", "llama3.1:8b"), None,
    )


# ── Execução de ferramenta ────────────────────────────────────────────────────

def _execute(call: ToolCall, *, confirm_handler: ConfirmHandler | None = None,
             safety_level: str | None = None,
             emit: Callable[[str, dict], None] | None = None) -> ToolCall:
    started = time.perf_counter()

    # Portão de segurança antes de qualquer efeito colateral. O resultado de uma
    # recusa volta como texto para o modelo, que entende e relata — bloquear em
    # silêncio faria o agente insistir no mesmo comando até esgotar as iterações.
    try:
        veredicto = agent_safety.avaliar(call.name, call.arguments, nivel=safety_level)
    except Exception as exc:  # o portão nunca derruba a tarefa
        log.warning("[SAFETY] avaliação falhou (%s); seguindo", exc)
        veredicto = None

    if veredicto is not None and veredicto.precisa_confirmar:
        pedido = veredicto.pedido or PedidoConfirmacao(
            ferramenta=call.name, argumentos=call.arguments,
            nivel_risco=veredicto.nivel_risco, motivo=veredicto.motivo)
        if emit:
            emit("confirm_required", {"name": call.name, "risk": pedido.nivel_risco,
                                      "reason": pedido.motivo, "preview": pedido.preview})
        aprovado = False
        if confirm_handler is not None:
            try:
                aprovado = bool(confirm_handler(pedido))
            except Exception as exc:
                log.warning("[SAFETY] handler de confirmação falhou: %s", exc)
                aprovado = False
        if not aprovado:
            call.result = (
                f"BLOQUEADO: {call.name} não foi executado porque {pedido.motivo}. "
                f"Risco {pedido.nivel_risco}. Comando/alvo: {pedido.preview}. "
                "Peça a confirmação do usuário ou proponha uma alternativa reversível."
            )
            call.error = True
            call.duration_ms = int((time.perf_counter() - started) * 1000)
            log.warning("[SAFETY] %s bloqueado: %s", call.name, pedido.motivo)
            return call
        log.info("[SAFETY] %s aprovado pelo usuário (%s)", call.name, pedido.motivo)

    spec = get_tool(call.name)
    if spec is None:
        call.result = (
            f"ERRO: ferramenta {call.name!r} não existe. "
            f"Disponíveis: {', '.join(t.name for t in all_tools())}"
        )
        call.error = True
    else:
        try:
            call.result = str(spec.handler(**call.arguments))
            call.error = call.result.startswith("ERRO")
        except TypeError as exc:
            call.result = f"ERRO: argumentos inválidos para {call.name}: {exc}"
            call.error = True
        except PermissionError as exc:
            call.result = f"ERRO: {exc}"
            call.error = True
        except Exception as exc:  # o erro volta para o modelo corrigir
            call.result = f"ERRO inesperado em {call.name}: {type(exc).__name__}: {exc}"
            call.error = True
    call.duration_ms = int((time.perf_counter() - started) * 1000)
    call.result = truncate(call.result)
    log.info("[AGENT] %s(%s) → %s em %dms", call.name,
             ", ".join(call.arguments), "erro" if call.error else "ok", call.duration_ms)
    return call


# ── Compactação de contexto ───────────────────────────────────────────────────

def _compact(messages: list[dict], goal: str) -> list[dict]:
    """
    Conversa longa some do começo e o agente esquece o objetivo. Em vez de
    truncar no meio — o que corta um par chamada/resultado e confunde o modelo —
    preservamos as primeiras e as últimas mensagens e reafirmamos o alvo.
    """
    if len(messages) <= COMPACT_AFTER_MESSAGES:
        return messages
    head = messages[:4]
    tail = messages[-(COMPACT_AFTER_MESSAGES - 6):]
    marker = {
        "role": "user",
        "content": (
            "[contexto compactado — passos intermediários omitidos]\n"
            f"Objetivo original, que continua valendo: {goal}\n"
            "Continue de onde parou. Se não lembrar do estado de algum arquivo, "
            "leia de novo com read_file antes de alterar."
        ),
    }
    log.info("[AGENT] contexto compactado: %d → %d mensagens", len(messages),
             len(head) + 1 + len(tail))
    return head + [marker] + tail


# ── Laço principal ────────────────────────────────────────────────────────────

def run_agent(
    goal: str,
    *,
    history: list[dict] | None = None,
    session_id: str | None = None,
    max_iterations: int = MAX_ITERATIONS,
    use_memory: bool = True,
    on_event: Callable[[str, dict], None] | None = None,
    confirm_handler: ConfirmHandler | None = None,
    safety_level: str | None = None,
) -> AgentResult:
    """
    Executa o agente até concluir o objetivo ou atingir o teto de iterações.

    goal          o que precisa ser feito, em linguagem natural
    history       mensagens anteriores, para continuar uma conversa
    session_id    separa a memória por conversa; None usa a sessão global
    use_memory    desligue para rodar sem puxar nem gravar memória
    on_event      callback(tipo, dados) para acompanhar: 'thinking',
                  'tool_call', 'tool_result', 'confirm_required', 'done'
    confirm_handler  callback(PedidoConfirmacao) -> bool, chamado antes de uma
                  ação irreversível. Sem ele, a ação é recusada e o agente é
                  avisado em texto
    safety_level  'off', 'trusted' (padrão) ou 'strict'; None lê
                  JARVIS_SAFETY_LEVEL
    """
    provider = _provider()
    messages: list[dict[str, Any]] = list(history or [])

    # Memória antes de começar: o que já se sabe sobre este usuário e este
    # trabalho entra no contexto, para o agente não recomeçar do zero.
    if use_memory:
        tools_memory.definir_sessao(session_id)
        try:
            contexto = tools_memory.contexto_inicial(goal, session_id)
            if contexto:
                messages.append({"role": "user", "content": contexto})
                log.info("[AGENT] contexto de memória injetado (%d chars)", len(contexto))
        except Exception as exc:  # memória nunca derruba a tarefa
            log.warning("[AGENT] memória indisponível: %s", exc)

    messages.append({"role": "user", "content": goal})

    result = AgentResult(stopped_reason="completed")
    emit = on_event or (lambda *_: None)

    for iteration in range(1, max_iterations + 1):
        result.iterations = iteration
        messages = _compact(messages, goal)

        try:
            turn = _one_turn(messages)
        except Exception as exc:
            log.exception("[AGENT] falha ao chamar o modelo")
            result.final_text = f"Falha ao falar com o modelo ({provider}): {exc}"
            result.stopped_reason = "provider_error"
            break

        if turn["text"]:
            emit("thinking", {"text": turn["text"], "iteration": iteration})

        # Sem chamada de ferramenta = o modelo terminou.
        if not turn["calls"]:
            result.final_text = turn["text"]
            result.stopped_reason = "completed"
            break

        # Registra a vez do assistente no formato do provedor.
        if provider == "anthropic":
            messages.append({"role": "assistant", "content": turn["raw"]})
        else:
            messages.append(turn["raw"])

        tool_results = []
        for call, call_id in zip(turn["calls"], turn["ids"]):
            emit("tool_call", {"name": call.name, "arguments": call.arguments})
            executed = _execute(call, confirm_handler=confirm_handler,
                                safety_level=safety_level, emit=emit)
            result.tool_calls.append(executed)
            emit("tool_result", {"name": executed.name, "error": executed.error,
                                 "result": executed.result[:500]})

            if provider == "anthropic":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": executed.result,
                    "is_error": executed.error,
                })
            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": executed.result,
                })

        if provider == "anthropic" and tool_results:
            messages.append({"role": "user", "content": tool_results})
    else:
        result.stopped_reason = "max_iterations"
        result.final_text = (
            f"Parei em {max_iterations} iterações sem concluir. "
            f"Executei {len(result.tool_calls)} chamadas de ferramenta. "
            "Diga se quer que eu continue de onde parei."
        )

    result.messages = messages
    emit("done", {"reason": result.stopped_reason, "iterations": result.iterations,
                  "tool_calls": len(result.tool_calls)})
    return result


__all__ = ["run_agent", "AgentResult", "ToolCall", "SYSTEM_PROMPT"]
