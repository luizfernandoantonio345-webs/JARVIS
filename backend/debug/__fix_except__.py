"""Fix all bare except Exception: pass/continue → log.debug"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

FILES = [
    "autodev/auto_fixer.py",
    "autonomy/confirmation_gate.py",
    "autonomy/daily_briefing.py",
    "autonomy/event_detector.py",
    "autonomy/goal_decomposer.py",
    "autonomy/work_session.py",
    "behavior/profile_manager.py",
    "core/boot_restorer.py",
    "core/session_checkpoint.py",
    "routes/health.py",
    "services/agent_manager.py",
    "services/auto_dev.py",
    "services/executor.py",
    "services/llm_service.py",
    "services/task_manager.py",
    "services/terminal_manager.py",
    "voice/command_mapper.py",
]

total = 0
for f in FILES:
    p = ROOT / f.replace("/", "\\")
    src = p.read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines(keepends=True)
    result = []
    i = 0
    changed = 0
    mod = f.replace("/", ".").replace(".py", "")
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)except\s+Exception\s*:\s*\n", line)
        if m and i + 1 < len(lines):
            indent = m.group(1)
            next_stripped = lines[i + 1].strip()
            if next_stripped in ("pass", "continue"):
                result.append(f"{indent}except Exception as exc:\n")
                result.append(
                    f'{indent}    log.debug("[{mod}] suppressed exception", exc_info=exc)\n'
                )
                result.append(lines[i + 1])
                i += 2
                changed += 1
                continue
        result.append(line)
        i += 1
    if changed:
        p.write_text("".join(result), encoding="utf-8")
        print(f"  fixed {changed:2d} in {f}")
        total += changed

print(f"Total fixed: {total}")
