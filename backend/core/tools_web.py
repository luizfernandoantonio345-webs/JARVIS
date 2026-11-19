"""
Ferramentas de web e de consulta a outros modelos.

Motivação: quando o JARVIS não sabe algo, ele deve ir buscar em vez de
inventar. Dois caminhos:

    web_search / fetch_url  →  informação pública atual
    ask_stronger_model      →  um modelo maior resolve o que o local não dá conta

A `actions/web_search.py` original abre o navegador do usuário e devolve o
resumo instantâneo do DuckDuckGo. Isso serve para uma pessoa olhar, mas não
para um agente: ele precisa do TEXTO de volta para continuar raciocinando.

Importar este módulo registra as ferramentas no tool_registry.
"""

from __future__ import annotations

import logging
import os
import re
import urllib.parse

import httpx

from .tool_registry import tool, truncate

log = logging.getLogger("jarvis.tools.web")

HTTP_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; JARVIS/1.0)"


def _strip_html(html: str) -> str:
    """Extrai texto legível de HTML sem depender de biblioteca externa."""
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</(p|div|li|h[1-6]|tr)>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = (
        text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
        .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    )
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


@tool(
    name="web_search",
    description=(
        "Pesquisa na web e devolve os resultados em texto. Use sempre que a "
        "pergunta envolver informação atual, versão de biblioteca, preço, "
        "notícia, ou qualquer coisa que você não tenha certeza. "
        "Prefira buscar a responder de memória."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "O que pesquisar"},
            "max_results": {"type": "integer", "description": "Quantos resultados (padrão 5)"},
        },
        "required": ["query"],
    },
    action_type="web_read",
    read_only=True,
)
def web_search(query: str, max_results: int = 5) -> str:
    encoded = urllib.parse.quote(query)
    results: list[str] = []

    # 1) Resposta direta do DuckDuckGo, quando existir.
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as c:
            data = c.get(
                f"https://api.duckduckgo.com/?q={encoded}&format=json"
                f"&no_redirect=1&no_html=1"
            ).json()
        if data.get("AbstractText"):
            src = data.get("AbstractURL", "")
            results.append(f"[resumo] {data['AbstractText']}\n  fonte: {src}")
        if data.get("Answer"):
            results.append(f"[resposta direta] {data['Answer']}")
    except Exception as exc:  # degrada sem derrubar o agente
        log.debug("[WEB] instant answer falhou: %s", exc)

    # 2) Resultados orgânicos pelo HTML leve do DuckDuckGo.
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT},
                          follow_redirects=True) as c:
            html = c.get(f"https://html.duckduckgo.com/html/?q={encoded}").text
        blocks = re.findall(
            r'(?is)<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
            r'.*?(?:class="result__snippet"[^>]*>(.*?)</a>)?',
            html,
        )
        for href, title, snippet in blocks[:max_results]:
            t = _strip_html(title)
            s = _strip_html(snippet or "")
            # O DDG embrulha o destino real em uma URL de redirecionamento.
            m = re.search(r"uddg=([^&]+)", href)
            url = urllib.parse.unquote(m.group(1)) if m else href
            results.append(f"- {t}\n  {url}\n  {s}".rstrip())
    except Exception as exc:
        log.warning("[WEB] busca falhou: %s", exc)

    if not results:
        return (
            f"Nenhum resultado para: {query}. "
            "Tente reformular com outros termos, ou use fetch_url se souber o endereço."
        )
    return truncate("\n\n".join(results), 10_000)


@tool(
    name="fetch_url",
    description=(
        "Abre uma URL e devolve o conteúdo em texto limpo. Use depois de "
        "web_search para ler a página inteira, ou quando já souber o endereço "
        "(documentação, repositório, artigo)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Endereço completo, com https://"},
        },
        "required": ["url"],
    },
    action_type="web_read",
    read_only=True,
)
def fetch_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT},
                          follow_redirects=True) as c:
            resp = c.get(url)
        if resp.status_code >= 400:
            return f"ERRO: {url} respondeu HTTP {resp.status_code}."
        ctype = resp.headers.get("content-type", "")
        body = resp.text if "html" in ctype or "text" in ctype or "json" in ctype else ""
        if not body:
            return f"ERRO: conteúdo não textual ({ctype})."
        return truncate(_strip_html(body) if "html" in ctype else body, 15_000)
    except Exception as exc:
        return f"ERRO ao abrir {url}: {exc}"


@tool(
    name="ask_stronger_model",
    description=(
        "Consulta um modelo mais forte (Claude ou GPT) quando a tarefa passa do "
        "que você consegue resolver sozinho: raciocínio longo, arquitetura "
        "complexa, bug difícil. Custa dinheiro, então use só quando precisar "
        "de verdade, e mande uma pergunta completa e autocontida — o modelo "
        "consultado não vê esta conversa."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Pergunta completa, com todo o contexto necessário",
            },
            "provider": {
                "type": "string",
                "enum": ["claude", "openai"],
                "description": "Qual provedor consultar (padrão: claude)",
            },
        },
        "required": ["question"],
    },
    action_type="api_call",
    read_only=True,
)
def ask_stronger_model(question: str, provider: str = "claude") -> str:
    # Import tardio: evita ciclo e permite que o módulo carregue sem o serviço.
    try:
        from services.llm_service import _call_claude, _call_openai  # type: ignore
    except Exception as exc:
        return f"ERRO: serviço de LLM indisponível: {exc}"

    messages = [{"role": "user", "content": question}]
    try:
        if provider == "openai":
            if not os.getenv("JARVIS_OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY"):
                return "ERRO: chave da OpenAI não configurada."
            return truncate(_call_openai(messages))
        if not os.getenv("JARVIS_ANTHROPIC_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
            return "ERRO: chave da Anthropic não configurada."
        return truncate(_call_claude(messages))
    except Exception as exc:
        return f"ERRO ao consultar {provider}: {exc}"


__all__ = ["web_search", "fetch_url", "ask_stronger_model"]
