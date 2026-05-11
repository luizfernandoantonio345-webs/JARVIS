"""
Intent Classifier — Modo Turbo Phase 1 (~4h)

Classifies user queries into tiers for <500ms responses:
- simple: rule cache hit or trivial (fast_path_intent() or len<20, ambiguity<0.3)
- cached: semantic similar past response via memory_v2 (200-500ms)
- complex: full LLM pipeline

Target: 80% queries <500ms via simple/cached paths.

Usage:
  classifier = IntentClassifier()
  tier = classifier.classify(query)  # 'simple' | 'cached' | 'complex'
  if tier == 'simple':
    intent = fast_path_intent(query)
"""

from __future__ import annotations

import time
from typing import Literal, Optional

from core.intent_cache import fast_path_intent, cache_get, cache_stats
from core.intent_engine import extract_intent, IntentModel
from core.telemetry import record_llm_latency, record_cache_hit
from memory_v2.vector_store import get_vector_store
from memory_v2.schemas import RetrievedMemory


SimpleTier = Literal["simple", "cached", "complex"]

COMPUTER_INTENTS = {
    "open_app": ["abre", "abrir", "lanca", "inicia", "open", "launch"],
    "browser": ["chrome", "firefox", "edge", "navegador", "browser", "site", "pesquisa"],
    "screen": ["tela", "screen", "screenshot", "o que tem", "veja", "olha"],
    "settings": ["volume", "brilho", "desligar", "reiniciar", "bloquear", "dark mode"],
    "computer_control": ["clica", "digita", "pressiona", "scroll", "mouse"],
    "file_processor": ["arquivo", "pdf", "excel", "word", "imagem", "audio", "video"],
    "dev_agent": ["cria projeto", "desenvolve", "programa", "codigo", "script"],
    "desktop": ["desktop", "wallpaper", "organiza", "area de trabalho"],
}


class IntentClassifier:
    def __init__(self):
        self.memory = get_vector_store()
        self.simple_patterns = [
            "status", "health", "help", "clear", "memory", "sessions",
            "oi", "olá", "tudo bem", "bom dia", "ok", "sim", "não"
        ]

    def classify(self, query: str) -> SimpleTier:
        """
        Classify query tier. Synchronous, <50ms.
        """
        t0 = time.monotonic()

        # Tier 1: Fast path rules or trivial
        if fast_path_intent(query) or self._is_simple_query(query):
            latency = (time.monotonic() - t0) * 1000
            record_llm_latency(latency, "classifier", "simple", cached=True)
            record_cache_hit("rule_fastpath")
            return "simple"

        # Computer intents are deterministic enough for turbo path.
        if self.detect_computer_intent(query):
            latency = (time.monotonic() - t0) * 1000
            record_llm_latency(latency, "classifier", "computer_simple", cached=True)
            record_cache_hit("computer_keywords")
            return "simple"

        # Tier 2: Exact cache hit (existing LRU)
        cached_intent = cache_get(query)
        if cached_intent:
            latency = (time.monotonic() - t0) * 1000
            record_llm_latency(latency, "classifier", "cache_exact", cached=True)
            record_cache_hit("exact")
            return "simple"  # treat exact cache as simple tier

        # Tier 3: Semantic cache via memory (fallback to complex)
        similar = self.memory.query_similar(query, top_k=3)
        if similar and similar[0].distance < 0.25:  # threshold tunable
            latency = (time.monotonic() - t0) * 1000
            record_llm_latency(latency, "classifier", "semantic", cached=True)
            record_cache_hit("semantic")
            return "cached"

        # Complex: full LLM
        latency = (time.monotonic() - t0) * 1000
        record_llm_latency(latency, "classifier", "complex")
        return "complex"

    def _is_simple_query(self, query: str) -> bool:
        q = query.strip().lower()
        return (len(q) < 25 or
                any(p in q for p in self.simple_patterns) or
                q in {"ok", "sim", "não", "clear", "stop", "cancel"})

    def detect_computer_intent(self, query: str) -> str | None:
        q = query.strip().lower()
        for intent_name, keywords in COMPUTER_INTENTS.items():
            if any(keyword in q for keyword in keywords):
                return intent_name
        return None

    def get_simple_response(self, query: str, session_id: str = "default") -> Optional[str]:
        """
        For simple/cached tier: return fast response or cached.
        Returns None for complex.
        """
        tier = self.classify(query)
        if tier == "complex":
            return None

        q = query.strip().lower()
        if q in {"oi", "ola", "olá", "oi jarvis", "bom dia"}:
            try:
                from core.context_memory import build_context_summary
                context = build_context_summary(session_id)
                if context:
                    first_line = context.splitlines()[0][:120]
                    return f"Bom dia. Em andamento: {first_line}. Por onde quer comecar?"
            except Exception:
                pass
            return "Bom dia. Qual e o foco de hoje?"

        if q in {"para", "cancela", "cancelar", "stop"}:
            return "Cancelado."

        if q in {"ok", "sim"}:
            return "Certo."

        # Rules or exact cache
        intent = fast_path_intent(query) or cache_get(query)
        if intent:
            # Execute simple action? Stub for now: confirm/log
            try:
                from services.message_bus import MessageBus
                MessageBus.get_instance().broadcast({
                    "event": "turbo_simple",
                    "query": query,
                    "intent": intent.model_dump(),
                    "tier": tier
                })
            except Exception:
                # MessageBus pode não estar disponível - não falha o fluxo
                pass
            return f"Pronto. {intent.goal[:50]}."

        # Semantic similar: adapt top similar memory
        similar = self.memory.query_similar(query, top_k=1)
        if similar:
            try:
                # Tentar usar call_llm se disponível, senão fallback simples
                from services.llm_service import call_llm
                prompt = f"""Adapt this previous similar response for new query:

Previous: {similar[0].text[:200]}

New query: {query}

Keep response concise (<100 words)."""
                try:
                    msgs = [{"role": "user", "content": prompt}]
                    response = call_llm(msgs)
                    if response:
                        return response
                except Exception:
                    pass
            except Exception:
                pass
            # Fallback: return truncated similar
            return similar[0].text[:120] + "..."

        return None

    def stats(self) -> dict:
        """
        Return stats about classifier and caching.
        Safe from AttributeErrors.
        """
        try:
            memory_size = len(self.memory._fallback_rows) if hasattr(self.memory, '_fallback_rows') else '?'
        except Exception:
            memory_size = '?'
        
        return {
            "cache": cache_stats(),
            "simple_patterns": len(self.simple_patterns),
            "memory_size": memory_size
        }


# Singleton
_classifier: IntentClassifier | None = None


def get_intent_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier

