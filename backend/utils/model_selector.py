import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RamInfo:
    total_gb: Optional[float]
    source: str


def _ram_total_gb_windows_wmi() -> Optional[float]:
    # Uses WMI: TotalPhysicalMemory returns bytes
    try:
        # Prefer PowerShell (available on Windows)
        cmd = (
            "powershell -NoProfile -Command "
            "\"(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory\""
        )
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        if not out:
            return None
        total_bytes = int(out)
        return total_bytes / (1024 ** 3)
    except Exception:
        return None


def _ram_total_gb_fallback() -> Optional[float]:
    # Best-effort fallback: parse systeminfo (Windows)
    try:
        if platform.system().lower().startswith("windows"):
            out = subprocess.check_output("systeminfo", shell=True, text=True, stderr=subprocess.DEVNULL)
            # Example line: "Total Physical Memory:  16.384.00 GB"
            for line in out.splitlines():
                if "Total Physical Memory" in line:
                    # extract last token with GB
                    if "GB" in line:
                        # keep digits and dot/comma
                        s = line.split(":")[-1].strip().replace(".", "").replace(",", ".")
                        # sometimes: "16.384,00 GB" -> normalize
                        parts = [p for p in s.split() if p]
                        if parts:
                            val = parts[0]
                            return float(val)
        return None
    except Exception:
        return None


def get_total_ram_gb() -> RamInfo:
    # Respect manual override if user sets it (useful for testing)
    forced = os.getenv("JARVIS_TOTAL_RAM_GB", "").strip()
    if forced:
        try:
            return RamInfo(total_gb=float(forced), source="env:JARVIS_TOTAL_RAM_GB")
        except Exception:
            pass

    if platform.system().lower().startswith("windows"):
        v = _ram_total_gb_windows_wmi()
        if v is not None:
            return RamInfo(total_gb=v, source="windows:wmi")
    # fallback
    v = _ram_total_gb_fallback()
    if v is not None:
        return RamInfo(total_gb=v, source="systeminfo")
    return RamInfo(total_gb=None, source="unknown")


def select_model_by_ram_gb(ram_gb: float) -> str:
    # Conservative mappings tuned for local CPU/RAM pressure.
    # You can adjust the models later without touching the rest of the logic.
    #
    # Expected Ollama models present in your setup:
    # - smollm2:135m (default currently)
    # - phi:latest (not always present, but supported)
    # - tinyllama (fallback)
    if ram_gb < 4:
        return "tinyllama"
    if ram_gb < 6:
        return "smollm2:135m"
    if ram_gb < 8:
        return "phi:latest"
    if ram_gb < 12:
        return "smollm2:135m"
    return "phi:latest"


def resolve_model_from_config(cfg) -> str:
    """
    Resolve final model to use.
    Priority:
      1) JARVIS_MODEL override (manual)
      2) cfg.model_selection: if "auto" then RAM-based
      3) fallback to cfg.model (current default)
    """
    manual = os.getenv("JARVIS_MODEL", "").strip()
    if manual:
        return manual

    strategy = getattr(cfg, "model_selection", "auto")
    if strategy != "auto":
        # keep existing config choice
        return getattr(cfg, "model", "smollm2:135m")

    ram = get_total_ram_gb()
    if ram.total_gb is None:
        return getattr(cfg, "model", "smollm2:135m")

    return select_model_by_ram_gb(ram.total_gb)
