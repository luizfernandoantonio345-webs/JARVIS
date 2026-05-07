from __future__ import annotations


def evaluate_examples(base_outputs: list[str], tuned_outputs: list[str]) -> dict:
    pairs = list(zip(base_outputs, tuned_outputs))
    if not pairs:
        return {"ok": False, "reason": "No outputs to compare"}
    avg_delta = sum(len(tuned) - len(base) for base, tuned in pairs) / len(pairs)
    return {"ok": True, "pairs": len(pairs), "avg_length_delta": avg_delta}

