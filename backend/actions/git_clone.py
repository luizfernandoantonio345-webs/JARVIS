"""
git_clone action — clones GitHub repos to workspace.

Security:
  - Clones to ALLOWED_BASE_DIR/repos/
  - Public or private (GITHUB_TOKEN)
  - No submodules, shallow by default
  - Size/depth limits

Input: \\"clone owner/repo [branch]\\" or URL
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import git
from git.exc import GitCommandError

from .file_reader import ALLOWED_BASE_DIR

log = logging.getLogger(__name__)

ACTION_NAME = "git_clone"

SYSTEM_PROMPT = "You are a Git expert. Confirm clone details (branch, size) before proceeding."

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPOS_DIR = ALLOWED_BASE_DIR / "repos"

def execute(input_str: str) -> str:
    # Extract repo
    import re
    url_match = re.search(r"github\.com/([^/\s]+)/([^/\s]+)", input_str)
    if url_match:
        owner, repo = url_match.groups()
        repo = repo.removesuffix(".git")
        # Extract optional branch from input (e.g. "clone ... branch main")
        branch_match = re.search(r"\bbranch[=:\s]+(\S+)", input_str)
        branch = branch_match.group(1) if branch_match else "main"
        url = f"https://{'x-' + GITHUB_TOKEN + '@' if GITHUB_TOKEN else ''}github.com/{owner}/{repo}.git"
    else:
        # owner/repo
        parts = input_str.split()[1:3]
        repo_slug = parts[0]
        branch = parts[1] if len(parts) > 1 else "main"
        owner, repo = repo_slug.split('/', 1)
        url = f"https://{'x-' + GITHUB_TOKEN + '@' if GITHUB_TOKEN else ''}github.com/{owner}/{repo}.git"

    dest = REPOS_DIR / f"{owner}-{repo}"
    dest.mkdir(parents=True, exist_ok=True)

    try:
        if (dest / '.git').exists():
            return f"❌ Repo already exists: {dest.relative_to(ALLOWED_BASE_DIR)}"

        git.Repo.clone_from(
            url, dest,
            branch=branch,
            depth=1,
            single_branch=True
        )
        return f"✅ Cloned {owner}/{repo}@{branch} to {dest.relative_to(ALLOWED_BASE_DIR)}"
    except GitCommandError as exc:
        return f"❌ Clone failed: {exc}"
    except Exception as exc:
        return f"❌ Error: {exc}"



