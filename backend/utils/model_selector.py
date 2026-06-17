"""Seleciona o modelo Ollama ideal com base na RAM disponível."""
import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RamInfo:
    total_gb: Optional[float]
    source: str


def _ram_windows_wmi() -> Optional[float]:
    try:
        out = subprocess.check_output(
            'powershell -NoProfile -Command "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"',
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=8,
        ).strip()
        return int(out) / (1024 ** 3) if out else None
    except Exception:
        return None


def _ram_fallback() -> Optional[float]:
    try:
        if platform.system().lower().startswith("windows"):
            out = subprocess.check_output(
                "systeminfo", shell=True, text=True,
                stderr=subprocess.DEVNULL, timeout=20,
            )
            for line in out.splitlines():
                if "Total Physical Memory" in line and "GB" in line:
                    s = line.split(":")[-1].strip().replace(".", "").replace(",", ".")
                    parts = [p for p in s.split() if p]
                    if parts:
                        return float(parts[0])
        # Linux/Mac
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb / (1024 ** 2)
    except Exception:
        pass
    return None


def get_total_ram_gb() -> RamInfo:
    forced = os.getenv("JARVIS_TOTAL_RAM_GB", "").strip()
    if forced:
        try:
            return RamInfo(total_gb=float(forced), source="env:JARVIS_TOTAL_RAM_GB")
        except Exception:
            pass

    if platform.system().lower().startswith("windows"):
        v = _ram_windows_wmi()
        if v is not None:
            return RamInfo(total_gb=v, source="windows:wmi")

    v = _ram_fallback()
    if v is not None:
        return RamInfo(total_gb=v, source="fallback")

    return RamInfo(total_gb=None, source="unknown")


def select_model_by_ram_gb(ram_gb: float) -> str:
    """
    Mapeia RAM total → modelo Ollama recomendado.
    Conservador (deixa margem para OS + backend).

    RAM     Modelo              Params  VRAM/RAM estimado
    ----    ------              ------  -----------------
    < 4GB   tinyllama           1.1B    ~800MB
    < 6GB   qwen2:0.5b          0.5B    ~450MB
    < 8GB   phi3:mini           3.8B    ~2.5GB
    < 12GB  llama3.2:3b         3.2B    ~2.5GB
    < 16GB  mistral:7b          7B      ~5GB
    < 24GB  mistral:7b          7B      ~5GB
    < 32GB  llama3.1:8b         8B      ~6GB
    >= 32GB mistral:7b          7B      escolha segura para CPU
    """
    if ram_gb < 4:
        return "tinyllama"
    if ram_gb < 6:
        return "qwen2:0.5b"
    if ram_gb < 8:
        return "phi3:mini"
    if ram_gb < 12:
        return "llama3.2:3b"
    if ram_gb < 32:
        return "mistral:7b"
    # 32GB+ — mistral:7b é a escolha segura para CPU sem GPU
    # Se quiser mais qualidade e tiver GPU: "llama3.1:8b" ou "mistral:7b-instruct"
    return "mistral:7b"


def resolve_model(cfg=None) -> str:
    """
    Resolve o modelo final a usar.
    Prioridade:
      1. Variável de ambiente JARVIS_MODEL (override manual sempre vence)
      2. Se cfg.model está definido e não é padrão genérico, usa
      3. Detecção automática por RAM
    """
    manual = os.getenv("JARVIS_MODEL", "").strip()
    if manual:
        log.info("[MODEL] Override manual: %s", manual)
        return manual

    ram = get_total_ram_gb()
    if ram.total_gb is None:
        log.warning("[MODEL] Não foi possível detectar RAM. Usando qwen2:0.5b como fallback.")
        fallback = getattr(cfg, "model", "qwen2:0.5b") if cfg else "qwen2:0.5b"
        return fallback

    chosen = select_model_by_ram_gb(ram.total_gb)
    log.info("[MODEL] RAM detectada: %.1fGB (via %s) → modelo: %s", ram.total_gb, ram.source, chosen)
    return chosen
