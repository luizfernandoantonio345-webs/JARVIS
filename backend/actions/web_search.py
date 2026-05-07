"""
web_search action — searches the web via DuckDuckGo Instant Answer API.

No API key required. Results are passed back as structured text so the
LLM can synthesize a coherent answer in the next pipeline step.

Defines execute(input) so the executor calls it directly, not via LLM.
"""

from __future__ import annotations

import logging
import urllib.parse

import httpx

log = logging.getLogger(__name__)

ACTION_NAME = "web_search"

_DDG_URL     = "https://api.duckduckgo.com/"
_SEARCH_URL  = "https://html.duckduckgo.com/html/"
_TIMEOUT     = 10
_MAX_RESULTS = 5

SYSTEM_PROMPT = (
    "You are a research assistant. You have been given raw web search results. "
    "Synthesize them into a clear, concise answer. "
    "Cite sources with their URLs. "
    "If the results are insufficient, say so explicitly."
)


def preprocess(content: str) -> str:
    return content


# ── Execution ──────────────────────────────────────────────────────────────────

def _instant_answer(query: str) -> str | None:
    """Try DuckDuckGo Instant Answer (structured JSON, fast)."""
    try:
        resp = httpx.get(
            _DDG_URL,
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()

        parts: list[str] = []

        abstract = data.get("AbstractText", "").strip()
        source   = data.get("AbstractURL", "")
        if abstract:
            parts.append(f"**Summary:** {abstract}")
            if source:
                parts.append(f"**Source:** {source}")

        # Related topics as additional results
        for topic in data.get("RelatedTopics", [])[:_MAX_RESULTS]:
            if isinstance(topic, dict) and topic.get("Text"):
                url  = topic.get("FirstURL", "")
                text = topic["Text"][:200]
                parts.append(f"- {text}" + (f"\n  {url}" if url else ""))

        return "\n".join(parts) if parts else None
    except Exception as exc:
        log.debug("DDG instant answer failed: %s", exc)
        return None


def _html_search(query: str) -> str:
    """Fallback: scrape DDG HTML results for titles + URLs."""
    try:
        resp = httpx.post(
            _SEARCH_URL,
            data={"q": query},
            headers={"User-Agent": "JARVIS/1.0 (research assistant)"},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()

        # Minimal HTML parse — avoid heavy dep like BeautifulSoup
        import re
        results = re.findall(
            r'<a class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            resp.text,
            re.DOTALL,
        )
        if not results:
            return "No results found."

        lines = []
        for url, title in results[:_MAX_RESULTS]:
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            lines.append(f"- [{clean_title}]({url})")
        return "\n".join(lines)
    except Exception as exc:
        log.error("DDG HTML search failed: %s", exc)
        return f"❌ Search failed: {exc}"


def execute(query: str) -> str:
    """
    Search the web and return structured results.
    Called directly by the executor (no LLM involved in retrieval).
    """
    query = query.strip()
    if not query:
        return "❌ No search query provided."

    result = _instant_answer(query)
    if result:
        return f"**Search results for:** `{query}`\n\n{result}"

    log.debug("Falling back to HTML search for query: %r", query)
    html_results = _html_search(query)
    return f"**Search results for:** `{query}`\n\n{html_results}"
