"""
config — FASE 12C

Centralized configuration via Pydantic BaseSettings.
All settings can be overridden via environment variables with JARVIS_ prefix.

Usage:
    from config import get_config
    cfg = get_config()
    print(cfg.ollama_url)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

# Load .env from project root
_root_dir = Path(__file__).parent.parent  # backend/.. = project root
_env_file = _root_dir / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)
    # Verify it loaded
    if os.getenv("JARVIS_OLLAMA_URL"):
        pass  # .env loaded successfully

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _USE_PYDANTIC_SETTINGS = True
except ImportError:
    from pydantic import BaseModel as BaseSettings  # type: ignore[assignment]
    _USE_PYDANTIC_SETTINGS = False

from pydantic import Field


class JarvisConfig(BaseSettings):
    """
    Complete Jarvis configuration.
    All fields can be overridden via env vars: JARVIS_<FIELD_NAME_UPPER>.
    """

    # ── Paths ─────────────────────────────────────────────────────────────────
    jarvis_jobs_dir:    Path = Field(default=Path("D:/JAVIS/jobs"),   description="AutoDev jobs base directory")
    jarvis_watch_dirs:  str  = Field(default="",                      description="Colon-separated dirs to watch (FileSystemWatcher)")
    jarvis_log_file:    Path = Field(default=Path("jarvis.log"),      description="Log file path for LogWatcher")
    jarvis_reports_dir: Path = Field(default=Path("reports"),         description="Directory for daily/weekly reports")

    # ── LLM ──────────────────────────────────────────────────────────────────
    ollama_url:         str  = Field(default="http://localhost:11434", description="Ollama server URL")
    model:              str  = Field(default="qwen2:0.5b",            description="Default Ollama model")
    embedding_model:    str  = Field(default="nomic-embed-text",      description="Embedding model")
    timeout:            int  = Field(default=60,                      description="Request timeout")
    max_retries:        int  = Field(default=3,                       description="Max retries for API calls")
    claude_model:       str  = Field(default="claude-3-haiku-20240307", description="Anthropic Claude model")
    openai_model:       str  = Field(default="gpt-4o-mini",           description="OpenAI model")
    anthropic_api_key:  str  = Field(default="",                      description="Anthropic API key")
    openai_api_key:     str  = Field(default="",                      description="OpenAI API key")
    complex_threshold:  float = Field(default=0.45,                   description="Complexity score threshold for external LLM routing")
    llm_api_timeout:    int  = Field(default=45,                      description="External LLM API timeout in seconds")

    # ── Autonomy ──────────────────────────────────────────────────────────────
    autonomy_enabled:               bool  = Field(default=True,  description="Enable System Event Loop on startup")
    autonomy_max_actions_per_minute: int  = Field(default=3,     description="Rate limit: autonomous actions per minute")
    autonomy_safe_mode:             bool  = Field(default=True,  description="Require confirmation before file writes")
    idle_timeout_minutes:           float = Field(default=5.0,   description="Minutes of inactivity before IdleWatcher fires")
    autonomy_v2_level:              int   = Field(default=0,     description="Autonomy v2 level: 0=reactive, 1=suggestions, 2=auto-safe")

    # ── Operational mode ───────────────────────────────────────────────────────
    operational_mode: Literal["dev", "assistant", "silent"] = Field(
        default="assistant",
        description="System mode: dev=verbose+debug, assistant=normal, silent=minimal output",
    )

    # ── Night Mode ─────────────────────────────────────────────────────────────
    night_mode_enabled:      bool = Field(default=True,  description="Enable autonomous night mode scheduler")
    night_mode_start_hour:   int  = Field(default=23,    description="Hour (0-23) to enter night mode and start work")
    night_mode_morning_hour: int  = Field(default=7,     description="Hour (0-23) to deliver morning briefing")

    # ── Turbo Mode ─────────────────────────────────────────────────────────────
    turbo_mode_enabled:        bool  = Field(default=True,  description="Enable Turbo mode: semantic cache + tier routing")
    turbo_similarity_threshold: float = Field(default=0.92, description="Cosine similarity threshold for semantic cache hits")

    # ── Voice ─────────────────────────────────────────────────────────────────
    voice_enabled:     bool  = Field(default=True,     description="Enable voice input/output")
    wake_word:         str   = Field(default="jarvis", description="Wake word for always-on listening")
    voice_language:    str   = Field(default="pt-BR",  description="Voice recognition language")
    voice_tts_engine:  str   = Field(default="pyttsx3", description="TTS engine: pyttsx3 | gTTS | elevenlabs")
    tts_voice:         str   = Field(default="pt-BR-AntonioNeural", description="TTS voice identifier")
    stm_model:         str   = Field(default="small",  description="Speech-to-text model size")
    user_title:        str   = Field(default="Senhor", description="User title (Sr./Sra. etc)")

    # ── Logging & Debug ────────────────────────────────────────────────────────
    debug:             bool  = Field(default=False,    description="Enable debug mode")
    log_level:         str   = Field(default="INFO",   description="Logging level")
    safe_mode:         bool  = Field(default=True,     description="Enable safe mode")

    # ── Safety ────────────────────────────────────────────────────────────────
    risk_tolerance:              Literal["low", "medium", "high"] = Field(
        default="medium", description="Default risk tolerance (overridden by BehaviorProfile)"
    )
    confirmation_timeout_seconds: int = Field(default=30, description="Seconds to wait for confirmation")

    # ── Memory ────────────────────────────────────────────────────────────────
    memory_db_path:       Path = Field(default=Path("memory.db"),    description="SQLite database path")
    memory_max_size_mb:   int  = Field(default=500,                  description="Max memory DB size before cleanup")
    memory_retain_days:   int  = Field(default=30,                   description="Days of history to retain")

    # ── Server ────────────────────────────────────────────────────────────────
    host:     str = Field(default="0.0.0.0", description="Server bind address")
    port:     int = Field(default=8000,      description="Server port")
    workers:  int = Field(default=1,         description="Uvicorn workers (1 for dev, 4+ for prod)")

    if _USE_PYDANTIC_SETTINGS:
        model_config = SettingsConfigDict(
            env_prefix="JARVIS_",
            case_sensitive=False,
            extra="ignore",
            populate_by_name=True,
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_config: JarvisConfig | None = None


def get_config() -> JarvisConfig:
    global _config
    if _config is None:
        _config = JarvisConfig(
            ollama_url=os.getenv("JARVIS_OLLAMA_URL") or "http://localhost:11434",
            model=os.getenv("JARVIS_MODEL") or "qwen2:0.5b",
            embedding_model=os.getenv("JARVIS_EMBEDDING_MODEL") or "nomic-embed-text",
        )
    return _config
