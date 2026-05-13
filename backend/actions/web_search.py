"""Pesquisa na web com modo normal e comparacao."""
from __future__ import annotations

import urllib.parse
import webbrowser

import httpx


def web_search(parameters: dict, player=None) -> str:
    query = parameters.get("query", "")
    mode = parameters.get("mode", "search")
    items = parameters.get("items", [])
    aspect = parameters.get("aspect", "geral")

    if not query and not items:
        return "Informe o que deseja pesquisar."

    try:
        if mode == "compare" and items:
            compare_query = f"comparacao {' vs '.join(items)} {aspect}"
            encoded = urllib.parse.quote(compare_query)
            webbrowser.open(f"https://www.google.com/search?q={encoded}")
            return f"Comparando {' vs '.join(items)} em relacao a {aspect}. Resultados abertos no browser."

        encoded_query = urllib.parse.quote(query)

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_redirect=1&no_html=1"
                )
                data = resp.json()

                abstract = data.get("AbstractText", "")
                answer = data.get("Answer", "")

                if abstract:
                    result = abstract[:500]
                    if player:
                        player.write_log(f"WebSearch: {result[:100]}")
                    webbrowser.open(f"https://www.google.com/search?q={encoded_query}")
                    return result
                if answer:
                    return answer

                webbrowser.open(f"https://www.google.com/search?q={encoded_query}")
                return f"Abrindo pesquisa no browser: {query}"
        except Exception:
            webbrowser.open(f"https://www.google.com/search?q={encoded_query}")
            return f"Pesquisa aberta no browser: {query}"

    except Exception as e:
        return f"Erro web_search: {e}"


def execute(query: str) -> str:
    return web_search({"query": query})
