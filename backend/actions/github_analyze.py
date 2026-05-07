"""
github_analyze action — deep-dives a GitHub repository.

Input formats accepted:
  "https://github.com/owner/repo"
  "owner/repo"
  "analyze repo owner/repo"

Requires no API key for public repos.
Set GITHUB_TOKEN env var for private repos or to raise rate limits.

Defines execute() so the executor calls it directly (no extra LLM hop needed
for data fetching); the action internally calls the LLM to synthesize findings.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

ACTION_NAME = "github_analyze"

_GITHUB_API  = "https://api.github.com"
_TIMEOUT     = 15
_MAX_COMMITS = 10
_MAX_ISSUES  = 5

SYSTEM_PROMPT = (
    "You are a senior software architect performing a GitHub repository analysis. "
    "Given raw repository metadata, synthesize a professional technical report covering:\n"
    "## Repository Overview\n"
    "## Tech Stack & Languages\n"
    "## Activity & Health Metrics\n"
    "## Code Quality Signals\n"
    "## Risks & Recommendations\n\n"
    "Be specific and actionable. Cite numbers from the data."
)

_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


def preprocess(content: str) -> str:
    return content


# ── Helpers ────────────────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    h = {
        "Accept":     "application/vnd.github.v3+json",
        "User-Agent": "JARVIS/2.0",
    }
    if _GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {_GITHUB_TOKEN}"
    return h


def _extract_repo(input_str: str) -> tuple[str, str] | None:
    """
    Parse owner/repo from various input formats.
    Returns (owner, repo) or None if not parseable.
    """
    # Full GitHub URL
    url_match = re.search(r"github\.com/([^/\s]+)/([^/\s]+)", input_str)
    if url_match:
        return url_match.group(1), url_match.group(2).rstrip(".git")

    # owner/repo shorthand (possibly with leading words)
    slug_match = re.search(r"\b([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\b", input_str)
    if slug_match:
        return slug_match.group(1), slug_match.group(2)

    return None


def _age_str(iso_date: str | None) -> str:
    if not iso_date:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        if days < 1:
            return "today"
        if days < 30:
            return f"{days}d ago"
        if days < 365:
            return f"{days // 30}mo ago"
        return f"{days // 365}y ago"
    except Exception:
        return iso_date[:10]


# ── Data fetchers ──────────────────────────────────────────────────────────────

def _fetch_repo(client: httpx.Client, owner: str, repo: str) -> dict:
    resp = client.get(f"{_GITHUB_API}/repos/{owner}/{repo}", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def _fetch_languages(client: httpx.Client, owner: str, repo: str) -> dict[str, int]:
    try:
        resp = client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/languages", headers=_headers()
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def _fetch_commits(client: httpx.Client, owner: str, repo: str) -> list[dict]:
    try:
        resp = client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/commits",
            headers=_headers(),
            params={"per_page": _MAX_COMMITS},
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def _fetch_issues(client: httpx.Client, owner: str, repo: str) -> list[dict]:
    try:
        resp = client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/issues",
            headers=_headers(),
            params={"state": "open", "per_page": _MAX_ISSUES},
        )
        resp.raise_for_status()
        return [i for i in resp.json() if "pull_request" not in i]  # exclude PRs
    except Exception:
        return []


def _fetch_readme(client: httpx.Client, owner: str, repo: str) -> str:
    try:
        import base64
        resp = client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/readme", headers=_headers()
        )
        resp.raise_for_status()
        data = resp.json()
        raw  = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        # Trim to first 1500 chars to keep context manageable
        return raw[:1500].strip()
    except Exception:
        return ""


# ── Report builder ─────────────────────────────────────────────────────────────

def _build_raw_report(owner: str, repo: str) -> str:
    """Fetch data from GitHub and format as structured plain text."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        try:
            meta = _fetch_repo(client, owner, repo)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return f"❌ Repository `{owner}/{repo}` not found or is private."
            if exc.response.status_code == 403:
                return "❌ GitHub API rate limit exceeded. Set GITHUB_TOKEN env var."
            return f"❌ GitHub API error: {exc.response.status_code}"
        except Exception as exc:
            return f"❌ Failed to fetch repository: {exc}"

        langs   = _fetch_languages(client, owner, repo)
        commits = _fetch_commits(client, owner, repo)
        issues  = _fetch_issues(client, owner, repo)
        readme  = _fetch_readme(client, owner, repo)

    # ── Format ──────────────────────────────────────────────────────────────
    total_lang_bytes = max(sum(langs.values()), 1)
    lang_lines = [
        f"  {lang}: {bytes_}/{total_lang_bytes*100:.0f}% ({bytes_:,} B)"
        if False
        else f"  {lang}: {bytes_ / total_lang_bytes * 100:.1f}%"
        for lang, bytes_ in sorted(langs.items(), key=lambda x: -x[1])
    ]

    commit_lines = []
    for c in commits:
        msg    = (c.get("commit", {}).get("message", "") or "").split("\n")[0][:80]
        author = (c.get("commit", {}).get("author", {}) or {}).get("name", "unknown")
        date   = _age_str((c.get("commit", {}).get("author", {}) or {}).get("date"))
        sha    = (c.get("sha") or "")[:7]
        commit_lines.append(f"  [{sha}] {date} by {author}: {msg}")

    issue_lines = []
    for iss in issues:
        title  = (iss.get("title") or "")[:80]
        labels = ", ".join(l["name"] for l in iss.get("labels", []))
        age    = _age_str(iss.get("created_at"))
        issue_lines.append(f"  #{iss['number']} [{age}] {title}" + (f" ({labels})" if labels else ""))

    report_parts = [
        f"REPOSITORY: {meta.get('full_name', f'{owner}/{repo}')}",
        f"Description: {meta.get('description') or 'N/A'}",
        f"URL: {meta.get('html_url', '')}",
        "",
        "STATS:",
        f"  Stars:     {meta.get('stargazers_count', 0):,}",
        f"  Forks:     {meta.get('forks_count', 0):,}",
        f"  Watchers:  {meta.get('watchers_count', 0):,}",
        f"  Open issues: {meta.get('open_issues_count', 0):,}",
        f"  Size:      {meta.get('size', 0):,} KB",
        f"  Created:   {_age_str(meta.get('created_at'))}",
        f"  Updated:   {_age_str(meta.get('updated_at'))}",
        f"  Default branch: {meta.get('default_branch', 'main')}",
        f"  License:   {(meta.get('license') or {}).get('spdx_id', 'None')}",
        f"  Topics:    {', '.join(meta.get('topics', [])) or 'None'}",
        "",
        "LANGUAGES:",
        *(lang_lines if lang_lines else ["  N/A"]),
        "",
        f"RECENT COMMITS (last {len(commits)}):",
        *(commit_lines if commit_lines else ["  No commits found"]),
        "",
        f"OPEN ISSUES (sample of {len(issues)}):",
        *(issue_lines if issue_lines else ["  No open issues"]),
    ]

    if readme:
        report_parts += ["", "README (excerpt):", readme[:800]]

    return "\n".join(report_parts)


# ── Public execute ─────────────────────────────────────────────────────────────

def execute(input_str: str) -> str:
    """Fetch GitHub repo data and synthesize a technical analysis report."""
    parsed = _extract_repo(input_str)
    if not parsed:
        return (
            "❌ Could not find a valid GitHub repository reference.\n"
            "Usage: `github_analyze owner/repo` or paste a GitHub URL."
        )

    owner, repo = parsed
    log.info("Analyzing GitHub repo: %s/%s", owner, repo)

    raw_report = _build_raw_report(owner, repo)
    if raw_report.startswith("❌"):
        return raw_report

    # Pass raw data to the LLM for synthesis
    from services.llm_service import call_llm
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Analyze this repository data:\n\n{raw_report}"},
    ]
    try:
        return call_llm(messages, force_api=True)
    except Exception as exc:
        log.error("LLM synthesis failed for github_analyze: %s", exc)
        # Return raw report as fallback
        return f"## Raw Repository Data\n\n```\n{raw_report}\n```"
