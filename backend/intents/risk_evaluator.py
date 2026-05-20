from __future__ import annotations

from backend.intents.schemas import Intent, RiskLevel

LOW_ACTIONS = {"open_app", "open_browser", "go_to_url", "navigate", "search_web"}
MEDIUM_ACTIONS = {"fill_form", "download_file", "upload_file"}
HIGH_ACTIONS = {"purchase", "delete_file", "system_change", "install_software", "run_shell"}

MEDIUM_TERMS = {"form", "download", "upload", "login", "credential", "senha"}
HIGH_TERMS = {
    "buy", "purchase", "comprar", "delete", "deletar", "apagar", "remove",
    "pagamento", "payment", "install", "instalar", "system", "sistema",
    "registry", "format", "shutdown", "reboot",
}


def evaluate_risk(intent: Intent) -> Intent:
    text = " ".join(
        [intent.action, *intent.steps, *[str(v) for v in intent.parameters.values()]]
    ).lower()

    risk: RiskLevel
    if intent.action in HIGH_ACTIONS or any(term in text for term in HIGH_TERMS):
        risk = "high"
    elif intent.action in MEDIUM_ACTIONS or any(term in text for term in MEDIUM_TERMS):
        risk = "medium"
    elif intent.action in LOW_ACTIONS:
        risk = "low"
    else:
        risk = intent.risk_level if intent.risk_level in {"low", "medium", "high"} else "medium"

    requires_confirmation = intent.requires_confirmation or risk == "high"
    return intent.model_copy(update={"risk_level": risk, "requires_confirmation": requires_confirmation})

