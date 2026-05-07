import re
from typing import Tuple

COMMAND_PROMPTS = {
    "analyze": (
        "You are a senior software engineer performing a detailed code review. "
        "Analyze the provided code for: bugs, security issues, performance problems, "
        "and code quality. Suggest specific improvements with examples. "
        "Be structured: use sections like '## Bugs', '## Security', '## Improvements'."
    ),
    "arch": (
        "You are a software architect. Suggest a clean, scalable architecture for the "
        "described system. Include: components, data flow, technology stack choices, "
        "trade-offs, and represent structure using ASCII or text diagrams."
    ),
}

ALIASES = {
    "analyze": ["/analyze", "/analisar", "/code"],
    "arch": ["/arch", "/arquitetura", "/architecture"],
    "run": ["/run", "/executar", "/exec"],
}

def detect_command(message: str) -> Tuple[str, str]:
    """Returns (command_type, content). command_type: 'analyze'|'arch'|'run'|'chat'"""
    msg = message.strip()
    for cmd, prefixes in ALIASES.items():
        for prefix in prefixes:
            if msg.lower().startswith(prefix):
                content = re.sub(r'^\S+\s*', '', msg)
                return cmd, content
    return "chat", msg

def get_command_system_prompt(command: str) -> str | None:
    return COMMAND_PROMPTS.get(command)
