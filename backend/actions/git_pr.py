"""
git_pr action — commits changes and creates GitHub PR.

Requires: Repo cloned via git_clone, GITHUB_TOKEN set.

Input: \"pr owner/repo 'commit msg' [branch=your-branch] [base=main]\"
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from github import Github
from git import Repo

from .file_reader import ALLOWED_BASE_DIR

log = logging.getLogger(__name__)

ACTION_NAME = "git_pr"

SYSTEM_PROMPT = "Review changes and confirm PR details."

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
g = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None

def execute(input_str: str) -> str:
    if not GITHUB_TOKEN or g is None:
        return "❌ GITHUB_TOKEN environment variable not set."

    parts = input_str.split(maxsplit=3)
    if len(parts) < 2:
        return "❌ Usage: 'pr owner/repo commit-msg [branch] [base]'"

    repo_slug = parts[1]
    commit_msg = parts[2]
    branch = parts[3] if len(parts) > 3 else "feature-branch"
    base = "main"

    owner, repo_name = repo_slug.split('/')
    local_path = ALLOWED_BASE_DIR / "repos" / f"{owner}-{repo_name}"

    if not local_path.exists():
        return f"❌ No local repo: {local_path}. Clone first."

    try:
        repo = Repo(local_path)
        repo.git.add(all=True)
        repo.index.commit(commit_msg)
        repo.git.push("origin", branch, set_upstream=True)

        gh_repo = g.get_repo(f"{owner}/{repo_name}")
        pr = gh_repo.create_pull(
            title=commit_msg[:100],
            body="Automated PR by JARVIS",
            head=f"{owner}:{branch}",
            base=base
        )
        return f"✅ PR created: {pr.html_url}"
    except Exception as exc:
        return f"❌ PR failed: {exc}"

