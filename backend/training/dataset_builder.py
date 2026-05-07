from __future__ import annotations


def is_quality_example(item: dict) -> bool:
    instruction = str(item.get("user_input", "")).strip()
    response = str(item.get("response", "")).strip()
    if len(instruction) < 12 or len(response) < 24:
        return False
    if response.lower() in {"ok", "sim", "erro interno."}:
        return False
    return True


def build_dataset(raw_items: list[dict]) -> list[dict]:
    dataset: list[dict] = []
    for item in raw_items:
        if not is_quality_example(item):
            continue
        dataset.append({
            "instruction": item["user_input"],
            "response": item["response"],
            "metadata": {"intent": item.get("intent"), "timestamp": item.get("timestamp")},
        })
    return dataset

