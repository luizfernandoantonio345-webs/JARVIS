"""
config.py -- JARVIS OMEGA v6.0
Configuracao centralizada via pydantic-settings.
Todos os campos sobrescriveis via env JARVIS_<CAMPO>.
"""
from __future__ import annotations

import os
from pathlib import Path

# Load .env from project root
_root_dir = Path(__file__).parent.parent
_env_file = _root_dir / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=True)
    except ImportError:
        with open(_env_file) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _, _v = _line.partition("=")
                    os.environ[_k.strip()] = _v.strip()

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _USE_PYDANTIC = True
except ImportError:
    from pydantic import BaseModel as BaseSettings  # type: ignore
    _USE_PYDANTIC = False

from pydantic import Field


class JarvisConfig(BaseSettings):
    # LLM
    ollama_url:      str   = Field(default="http://localhost:11434")
    model:           str   = Field(default="tinyllama:latest")
    local_model:     str   = Field(default="tinyllama:latest")
    fallback_model:  str   = Field(default="tinyllama:latest")
    embedding_model: str   = Field(default="nomic-embed-text")
    timeout:         int   = Field(default=60)
    max_retries:     int   = Field(default=2)

    # External APIs
    anthropic_api_key: str   = Field(default="")
    openai_api_key:    str   = Field(default="")
    claude_model:      str   = Field(default="claude-3-haiku-20240307")
    openai_model:      str   = Field(default="gpt-4o-mini")
    complex_threshold: float = Field(default=0.45)
    llm_api_timeout:   int   = Field(default=45)

    # Server
    host:    str = Field(default="0.0.0.0")
    port:    int = Field(default=8000)
    workers: int = Field(default=1)

    # TTS
    tts_voice:        str  = Field(default="pt-BR-AntonioNeural")
    tts_rate:         str  = Field(default="-12%")
    tts_pitch:        str  = Field(default="-15Hz")
    voice_enabled:    bool = Field(default=True)
    wake_word:        str  = Field(default="jarvis")
    voice_language:   str  = Field(default="pt-BR")
    voice_tts_engine: str  = Field(default="edge_tts")
    stm_model:        str  = Field(default="small")
    user_title:       str  = Field(default="Senhor")
    disable_voice:    bool = Field(default=False)

    # Paths
    data_dir:              str  = Field(default="data")
    memory_db:             str  = Field(default="data/jarvis_memory.db")
    memory_db_path:        Path = Field(default=Path("memory.db"))
    memory_max_size_mb:    int  = Field(default=500)
    memory_retain_days:    int  = Field(default=30)
    jarvis_jobs_dir:       Path = Field(default=Path("jobs"))
    jarvis_log_file:       Path = Field(default=Path("jarvis.log"))
    jarvis_reports_dir:    Path = Field(default=Path("reports"))
    jarvis_watch_dirs:     str  = Field(default="")

    # Modes
    test_mode:                    bool  = Field(default=False)
    debug:                        bool  = Field(default=False)
    log_level:                    str   = Field(default="INFO")
    safe_mode:                    bool  = Field(default=True)
    operational_mode:             str   = Field(default="assistant")
    risk_tolerance:               str   = Field(default="medium")
    confirmation_timeout_seconds: int   = Field(default=30)

    # Autonomy
    autonomy_enabled:                 bool  = Field(default=True)
    autonomy_max_actions_per_minute:  int   = Field(default=3)
    autonomy_safe_mode:               bool  = Field(default=True)
    idle_timeout_minutes:             float = Field(default=5.0)
    autonomy_v2_level:                int   = Field(default=0)

    # Night / Turbo
    night_mode_enabled:          bool  = Field(default=True)
    night_mode_start_hour:       int   = Field(default=23)
    night_mode_morning_hour:     int   = Field(default=7)
    turbo_mode_enabled:          bool  = Field(default=True)
    turbo_similarity_threshold:  float = Field(default=0.92)


if _USE_PYDANTIC:
    JarvisConfig.model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

try:
    JarvisConfig.model_rebuild()
except Exception:
    pass


# -- Singleton ----------------------------------------------------------------
_config: JarvisConfig | None = None


def get_config() -> JarvisConfig:
    global _config
    if _config is None:
        _config = JarvisConfig()
    return _config
