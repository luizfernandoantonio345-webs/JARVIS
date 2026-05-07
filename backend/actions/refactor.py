"""
refactor action — LLM-powered code refactoring with structured output.

Auto-discovered via ACTION_NAME convention.
No execute() — dispatched through LLM pipeline.
"""

ACTION_NAME = "refactor"

SYSTEM_PROMPT = (
    "You are a senior software engineer specializing in code refactoring. "
    "Improve the provided code for readability, maintainability, performance, "
    "and idiomatic style WITHOUT changing observable external behaviour.\n\n"
    "Structure your response with these exact sections:\n"
    "## Issues Found\n"
    "List specific problems: naming, complexity, duplication, anti-patterns.\n\n"
    "## Refactored Code\n"
    "Complete, runnable refactored version in a single code block.\n\n"
    "## What Changed\n"
    "Bullet list of every change made and why.\n\n"
    "## Behaviour Warnings\n"
    "List any subtle behaviour changes (edge cases, error handling differences). "
    "Write 'None' if there are none.\n\n"
    "Be direct. Do not pad with unnecessary prose."
)


def preprocess(content: str) -> str:
    # If no code fence present, wrap it
    if "```" not in content:
        # Try to detect the language from common keywords
        lang = "python"
        if any(kw in content for kw in ["function ", "const ", "let ", "var ", "=>"]):
            lang = "javascript"
        elif any(kw in content for kw in ["public class", "void ", "System.out"]):
            lang = "java"
        elif any(kw in content for kw in ["#include", "int main", "std::"]):
            lang = "cpp"
        return f"Refactor this {lang} code:\n```{lang}\n{content}\n```"
    return content

