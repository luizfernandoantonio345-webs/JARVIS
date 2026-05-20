from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from backend.intents.risk_evaluator import evaluate_risk
from backend.intents.schemas import Intent
from backend.services.llm_service import call_llm

log = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = """
You convert natural language into one structured executable intent.
Return JSON only. Do not include markdown, commentary, or extra keys.
Allowed actions include: open_app, open_browser, go_to_url, navigate, fill_form,
download_file, purchase, delete_file, system_change, status, stop, voice_mute,
voice_enable, create_file, run_command, git_commit, daily_report, next_steps,
search_web, night_mode, clear_memory, take_screenshot.
Never place raw user text in an executable command.
Schema:
{
  "action": "string",
  "parameters": {},
  "steps": ["string"],
  "risk_level": "low|medium|high",
  "requires_confirmation": true,
  "confidence": 0.0,
  "source": "llm"
}
"""


@dataclass(frozen=True)
class IntentCandidate:
    action: str
    phrase: str
    confidence: float
    parameters: dict[str, Any]
    risk_level: str = "low"
    requires_confirmation: bool = False


class AmbiguousIntentError(ValueError):
    def __init__(self, candidate: IntentCandidate, user_input: str):
        self.candidate = candidate
        self.user_input = user_input
        super().__init__(
            f"Nao entendi bem. Voce quis dizer '{candidate.action}'?"
        )


COMMAND_PATTERNS: dict[str, dict[str, Any]] = {
    "status": {
        "phrases": ["status", "como ta", "como voce ta", "tudo bem", "situacao"],
        "risk": "low",
    },
    "stop": {
        "phrases": ["para", "cancela", "cancela tudo", "stop", "para tudo"],
        "risk": "low",
    },
    "voice_mute": {
        "phrases": ["modo silencioso", "cala boca", "sem voz", "mudo"],
        "risk": "low",
    },
    "voice_enable": {
        "phrases": ["pode falar", "fala", "ativa voz"],
        "risk": "low",
    },
    "create_file": {
        "phrases": ["cria arquivo", "cria um arquivo", "novo arquivo"],
        "risk": "medium",
    },
    "run_command": {
        "phrases": ["executa", "roda", "run"],
        "risk": "high",
        "requires_confirmation": True,
    },
    "git_commit": {
        "phrases": ["commita", "faz commit", "commit"],
        "risk": "medium",
        "requires_confirmation": True,
    },
    "open_app": {
        "phrases": ["abre o vscode", "abre o vs code", "vscode", "abre o chrome", "chrome"],
        "risk": "low",
    },
    "daily_report": {
        "phrases": ["o que fiz hoje", "resumo do dia", "relatorio"],
        "risk": "low",
    },
    "next_steps": {
        "phrases": ["o que falta", "proximos passos", "o que fazer"],
        "risk": "low",
    },
    "search_web": {
        "phrases": ["pesquisa", "busca", "procura", "search"],
        "risk": "low",
    },
    "night_mode": {
        "phrases": ["modo noite", "night mode", "pode dormir"],
        "risk": "low",
    },
    "clear_memory": {
        "phrases": ["esquece tudo", "limpa memoria", "reset"],
        "risk": "high",
        "requires_confirmation": True,
    },
    "take_screenshot": {
        "phrases": ["tira um print", "print", "screenshot"],
        "risk": "low",
    },
    "go_to_url": {
        "phrases": ["vai para", "abre site", "navega para"],
        "risk": "low",
    },
}


def normalize_text(text: str) -> str:
    lowered = (text or "").lower().strip()
    without_accents = unicodedata.normalize("NFD", lowered)
    without_accents = "".join(ch for ch in without_accents if unicodedata.category(ch) != "Mn")
    cleaned = re.sub(r"[^a-z0-9:/._ -]+", " ", without_accents)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def strip_wake_noise(text: str) -> str:
    normalized = normalize_text(text)
    replacements = [
        r"^jar\s*vis\b",
        r"^jarvis\b",
        r"^jarves\b",
        r"^javis\b",
    ]
    for pattern in replacements:
        normalized = re.sub(pattern, "", normalized).strip()
    normalized = re.sub(r"^(faz|vai|por favor|pfv|pra mim)\b", "", normalized).strip()
    return normalized


def parse_intent_candidate(user_input: str) -> IntentCandidate:
    command = strip_wake_noise(user_input)
    best: IntentCandidate | None = None

    for action, spec in COMMAND_PATTERNS.items():
        for phrase in spec["phrases"]:
            phrase_norm = normalize_text(phrase)
            if command == phrase_norm or command.startswith(phrase_norm + " "):
                return IntentCandidate(
                    action=action,
                    phrase=phrase,
                    confidence=1.0,
                    parameters=_extract_parameters(action, command, phrase_norm),
                    risk_level=spec.get("risk", "low"),
                    requires_confirmation=bool(spec.get("requires_confirmation", False)),
                )

            score = difflib.SequenceMatcher(None, command, phrase_norm).ratio()
            if command.startswith(phrase_norm[: max(3, len(phrase_norm) // 2)]):
                score = max(score, 0.81)
            confidence = 0.92 if score > 0.90 else 0.82 if score > 0.80 else score
            candidate = IntentCandidate(
                action=action,
                phrase=phrase,
                confidence=confidence,
                parameters=_extract_parameters(action, command, phrase_norm),
                risk_level=spec.get("risk", "low"),
                requires_confirmation=bool(spec.get("requires_confirmation", False)),
            )
            if best is None or candidate.confidence > best.confidence:
                best = candidate

    return best or IntentCandidate("unknown", "", 0.0, {}, "low", False)


async def parse_intent(user_input: str, *, threshold: float = 0.70) -> Intent:
    if not user_input or not user_input.strip():
        raise ValueError("user_input is empty")

    candidate = parse_intent_candidate(user_input)
    if candidate.confidence >= threshold and candidate.action != "unknown":
        return _candidate_to_intent(candidate, user_input)

    if 0.55 <= candidate.confidence < threshold and candidate.action != "unknown":
        raise AmbiguousIntentError(candidate, user_input)

    raw = await _parse_with_llm(user_input)
    intent = Intent.model_validate(raw)
    if intent.confidence <= 0:
        intent = intent.model_copy(update={"confidence": 0.65})
    if not intent.source:
        intent = intent.model_copy(update={"source": "llm"})
    if not intent.raw_text:
        intent = intent.model_copy(update={"raw_text": user_input.strip()})
    return evaluate_risk(intent)


def _candidate_to_intent(candidate: IntentCandidate, user_input: str) -> Intent:
    intent = Intent(
        action=candidate.action,
        parameters=candidate.parameters,
        steps=[f"Deterministic PT-BR match: {candidate.phrase}"],
        risk_level=candidate.risk_level,  # type: ignore[arg-type]
        requires_confirmation=candidate.requires_confirmation,
        confidence=candidate.confidence,
        source="deterministic",
        raw_text=user_input.strip(),
    )
    return evaluate_risk(intent)


def _extract_parameters(action: str, command: str, phrase: str) -> dict[str, Any]:
    rest = command.removeprefix(phrase).strip()
    if action == "open_app":
        if "chrome" in command:
            return {"app": "chrome"}
        return {"app": "vscode"}
    if action == "go_to_url":
        url = rest or _last_urlish_token(command)
        return {"url": url} if url else {}
    if action == "search_web":
        query = rest
        for prefix in ("pesquisa", "busca", "procura", "search"):
            query = query.removeprefix(prefix).strip()
        return {"query": query or command}
    if action == "create_file":
        target = _extract_path(rest) or _extract_path(command)
        return {"path": target or "novo_arquivo.txt", "content": ""}
    if action == "run_command":
        return {"command": rest}
    if action == "git_commit":
        message = rest.removeprefix("com").strip()
        return {"message": message or "chore: update jarvis"}
    return {}


def _extract_path(text: str) -> str | None:
    match = re.search(r"([a-z0-9_./\\-]+\.[a-z0-9]+)", text)
    return match.group(1) if match else None


def _last_urlish_token(text: str) -> str:
    tokens = text.split()
    for token in reversed(tokens):
        if "." in token or token.startswith(("http://", "https://", "localhost")):
            return token
    return ""


async def _parse_with_llm(user_input: str) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_input.strip()},
    ]

    last_error: Exception | None = None
    for attempt in range(2):
        raw = await asyncio.to_thread(call_llm, messages, False, True)
        try:
            return _extract_json(raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            log.warning("intent.parse_failed attempt=%d error=%s raw=%r", attempt + 1, exc, raw[:500])
            messages = [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Your previous response was invalid. Return valid JSON only for: "
                    + user_input.strip(),
                },
            ]
    raise ValueError(f"Could not parse intent: {last_error}")


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))
