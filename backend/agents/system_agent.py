"""
SystemAgent — OS and browser automation agent for JARVIS.

Capabilities:
  - OS-level file operations (via FSController — workspace-scoped)
  - Clipboard read/write (pyperclip, best-effort)
  - Browser automation via Playwright (headless, safe)
  - Process listing (read-only)
  - Screenshot (headless browser only)

Security:
  - All file ops go through FSController (workspace-scoped)
  - Browser only opens HTTP/HTTPS URLs
  - No system-critical process manipulation
  - Playwright runs headless by default

Dependencies (optional):
  - playwright  → pip install playwright && playwright install chromium
  - pyperclip   → pip install pyperclip
  If not installed, those capabilities gracefully degrade.
"""

from __future__ import annotations

import logging
import shutil
from typing import Generator

from agents.base_agent import BaseAgent, AgentResult

log = logging.getLogger(__name__)


class SystemAgent(BaseAgent):
    ROLE = "system"

    SYSTEM_PROMPT = """\
You are the System Agent inside the JARVIS multi-agent system.

## Role
Interact with the local OS and browser environment in a CONTROLLED, SAFE manner.

## Capabilities
- Read/write files (workspace only)
- List directory contents
- Open URLs in a headless browser and extract content
- Take browser screenshots
- Read clipboard text

## Output Format
Always respond with:

**Action**: `<action performed>`
**Result**: `<outcome>`
**Data**: (if applicable)
```
<content returned>
```

## Rules
- NEVER access files outside the workspace
- NEVER open external URLs that could be malicious
- NEVER execute system commands directly
- NEVER use elevated privileges
- Always sanitize and truncate large outputs (max 4KB)
- Report any errors clearly without retrying infinitely
"""

    # ── File operations ────────────────────────────────────────────────────────

    def read_file(self, path: str) -> AgentResult:
        """Read a workspace file."""
        from services.fs_controller import get_fs
        fs = get_fs()
        r = fs.read_file(path)
        if r.success:
            content = str(r.data)[:4096]
            return AgentResult(
                agent=self.ROLE,
                response=f"**Action**: read_file `{path}`\n**Result**: ✅ Success\n**Data**:\n```\n{content}\n```",
            )
        return AgentResult(agent=self.ROLE, response=f"❌ Read failed: {r.error}")

    def list_dir(self, path: str = ".") -> AgentResult:
        """List directory contents in workspace."""
        from services.fs_controller import get_fs
        fs = get_fs()
        r = fs.list_dir(path)
        if r.success:
            items = "\n".join(r.data) if isinstance(r.data, list) else str(r.data)
            return AgentResult(
                agent=self.ROLE,
                response=f"**Action**: list_dir `{path}`\n**Result**: ✅\n**Data**:\n```\n{items}\n```",
            )
        return AgentResult(agent=self.ROLE, response=f"❌ List failed: {r.error}")

    # ── Browser automation ─────────────────────────────────────────────────────

    def browse_url(self, url: str, extract: str = "text") -> AgentResult:
        """
        Open a URL in headless Chromium and extract content.

        Args:
            url:     HTTP/HTTPS URL to visit.
            extract: "text" (default), "html", or "screenshot" (base64 PNG).

        Returns:
            AgentResult with extracted content.
        """
        # Safety: only HTTP/HTTPS
        if not url.startswith(("http://", "https://")):
            return AgentResult(
                agent=self.ROLE,
                response=f"❌ URL must start with http:// or https://. Got: {url[:80]}",
            )

        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            return AgentResult(
                agent=self.ROLE,
                response="⚠️ Playwright not installed. Run: pip install playwright && playwright install chromium",
            )

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=15000, wait_until="domcontentloaded")

                if extract == "screenshot":
                    import base64
                    img_bytes = page.screenshot(type="png")
                    img_b64 = base64.b64encode(img_bytes).decode()[:8192]
                    browser.close()
                    return AgentResult(
                        agent=self.ROLE,
                        response=f"**Action**: screenshot `{url}`\n**Result**: ✅\n**Data**: [PNG base64 truncated at 8KB]",
                        metadata={"screenshot_b64": img_b64},
                    )

                if extract == "html":
                    content = page.content()[:4096]
                else:
                    content = page.inner_text("body")[:4096]

                title = page.title()
                browser.close()

            return AgentResult(
                agent=self.ROLE,
                response=(
                    f"**Action**: browse_url `{url}`\n"
                    f"**Title**: {title}\n"
                    f"**Result**: ✅\n"
                    f"**Data**:\n```\n{content}\n```"
                ),
            )

        except Exception as exc:
            log.error("SystemAgent.browse_url error: %s", exc)
            return AgentResult(agent=self.ROLE, response=f"❌ Browser error: {exc}")

    # ── Clipboard ──────────────────────────────────────────────────────────────

    def read_clipboard(self) -> AgentResult:
        """Read system clipboard text (best-effort)."""
        try:
            import pyperclip  # type: ignore
            text = pyperclip.paste()
            return AgentResult(
                agent=self.ROLE,
                response=f"**Action**: read_clipboard\n**Result**: ✅\n**Data**:\n```\n{text[:2048]}\n```",
            )
        except ImportError:
            return AgentResult(
                agent=self.ROLE,
                response="⚠️ pyperclip not installed. Run: pip install pyperclip",
            )
        except Exception as exc:
            return AgentResult(agent=self.ROLE, response=f"❌ Clipboard error: {exc}")

    def write_clipboard(self, text: str) -> AgentResult:
        """Write text to system clipboard (best-effort)."""
        if len(text) > 64 * 1024:
            return AgentResult(agent=self.ROLE, response="❌ Text too large for clipboard (>64KB)")
        try:
            import pyperclip  # type: ignore
            pyperclip.copy(text)
            return AgentResult(
                agent=self.ROLE,
                response=f"**Action**: write_clipboard\n**Result**: ✅ Wrote {len(text)} chars to clipboard",
            )
        except ImportError:
            return AgentResult(
                agent=self.ROLE,
                response="⚠️ pyperclip not installed. Run: pip install pyperclip",
            )
        except Exception as exc:
            return AgentResult(agent=self.ROLE, response=f"❌ Clipboard error: {exc}")

    # ── Process listing (read-only) ────────────────────────────────────────────

    def list_processes(self) -> AgentResult:
        """List running processes (name + pid only, read-only)."""
        try:
            import psutil  # type: ignore
            procs = [
                f"{p.info['name']} (pid={p.info['pid']})"
                for p in psutil.process_iter(["name", "pid"])
            ][:50]
            text = "\n".join(procs)
            return AgentResult(
                agent=self.ROLE,
                response=f"**Action**: list_processes\n**Result**: ✅ ({len(procs)} shown)\n**Data**:\n```\n{text}\n```",
            )
        except ImportError:
            return AgentResult(
                agent=self.ROLE,
                response="⚠️ psutil not installed. Run: pip install psutil",
            )
        except Exception as exc:
            return AgentResult(agent=self.ROLE, response=f"❌ Process list error: {exc}")

    # ── LLM-routed entry point ─────────────────────────────────────────────────

    def run(
        self,
        message: str,
        history: list[dict] | None = None,
        force_local: bool = False,
        force_api: bool = False,
    ) -> AgentResult:
        """
        Route message to the appropriate system capability.
        Falls back to LLM for complex requests.
        """
        lower = message.lower().strip()

        if lower.startswith("read "):
            return self.read_file(message[5:].strip())
        if lower.startswith("list ") or lower.startswith("ls "):
            path = message.split(maxsplit=1)[1] if " " in message else "."
            return self.list_dir(path.strip())
        if lower.startswith("browse ") or lower.startswith("open "):
            parts = message.split(maxsplit=1)
            url = parts[1].strip() if len(parts) > 1 else ""
            return self.browse_url(url)
        if lower.startswith("screenshot "):
            parts = message.split(maxsplit=1)
            url = parts[1].strip() if len(parts) > 1 else ""
            return self.browse_url(url, extract="screenshot")
        if lower == "clipboard" or lower == "read clipboard":
            return self.read_clipboard()
        if lower.startswith("write clipboard "):
            return self.write_clipboard(message[16:].strip())
        if lower in ("processes", "list processes", "ps"):
            return self.list_processes()

        # Fallback: LLM response describing what this agent can do
        return super().run(message, history, force_local, force_api)
