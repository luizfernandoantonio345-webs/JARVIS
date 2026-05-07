from __future__ import annotations

from pathlib import Path


class FineTunedModelManager:
    def __init__(self, model_dir: str = "backend/training/runs/latest") -> None:
        self.model_dir = Path(model_dir)
        self._pipeline = None

    def available(self) -> bool:
        return self.model_dir.exists() and any(self.model_dir.iterdir())

    def load(self):
        if self._pipeline is not None:
            return self._pipeline
        if not self.available():
            return None
        try:
            from transformers import pipeline
            self._pipeline = pipeline("text-generation", model=str(self.model_dir), tokenizer=str(self.model_dir))
            return self._pipeline
        except Exception:
            return None

    def generate(self, prompt: str) -> str | None:
        pipe = self.load()
        if pipe is None:
            return None
        output = pipe(prompt, max_new_tokens=512, do_sample=True, temperature=0.7)
        return output[0]["generated_text"]


_manager = FineTunedModelManager()


def get_fine_tuned_model_manager() -> FineTunedModelManager:
    return _manager
