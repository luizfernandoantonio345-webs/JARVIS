from __future__ import annotations

from pathlib import Path

DEFAULT_TRAINING_CONFIG = {
    "base_model": "meta-llama/Llama-3.1-8B-Instruct",
    "lora_r": 8,
    "lora_alpha": 16,
    "lora_dropout": 0.05,
    "epochs": 1,
    "batch_size": 1,
    "learning_rate": 2e-4,
}


def train_lora(dataset: list[dict], output_dir: str = "backend/training/runs/latest", config: dict | None = None) -> dict:
    if len(dataset) < 10:
        return {"ok": False, "reason": "Need at least 10 high-quality examples before training."}
    cfg = {**DEFAULT_TRAINING_CONFIG, **(config or {})}
    try:
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer

        tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])
        model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], device_map="auto")
        model = get_peft_model(model, LoraConfig(r=cfg["lora_r"], lora_alpha=cfg["lora_alpha"], lora_dropout=cfg["lora_dropout"], task_type="CAUSAL_LM"))

        def format_item(item):
            text = f"### Instruction:\n{item['instruction']}\n\n### Response:\n{item['response']}"
            return tokenizer(text, truncation=True, max_length=1024)

        ds = Dataset.from_list(dataset).map(format_item)
        args = TrainingArguments(output_dir=output_dir, num_train_epochs=cfg["epochs"], per_device_train_batch_size=cfg["batch_size"], learning_rate=cfg["learning_rate"])
        Trainer(model=model, args=args, train_dataset=ds).train()
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)
        return {"ok": True, "output_dir": str(Path(output_dir)), "config": cfg}
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "config": cfg}

