"""
system_monitor action — reports real-time system resource usage.

Uses psutil. Defines execute() for direct executor dispatch (no LLM needed).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

ACTION_NAME = "system_monitor"

SYSTEM_PROMPT = (
    "You are a systems reliability engineer. "
    "Analyze the provided system metrics and identify any concerns. "
    "Recommend actions if resources are under pressure."
)


def preprocess(content: str) -> str:
    return content


# ── Execution ──────────────────────────────────────────────────────────────────

def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


def execute(_input: str) -> str:
    """Collect and format system metrics. Input is ignored."""
    try:
        import psutil
    except ImportError:
        return "❌ `psutil` is not installed. Run: `pip install psutil`"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # ── CPU ────────────────────────────────────────────────────────────────────
    cpu_pct      = psutil.cpu_percent(interval=0.5)
    cpu_count    = psutil.cpu_count(logical=True)
    cpu_phys     = psutil.cpu_count(logical=False)
    cpu_freq     = psutil.cpu_freq()
    freq_str     = f"{cpu_freq.current:.0f} MHz" if cpu_freq else "N/A"
    load_avg     = getattr(psutil, "getloadavg", lambda: (0, 0, 0))()
    load_str     = f"{load_avg[0]:.2f} / {load_avg[1]:.2f} / {load_avg[2]:.2f}"

    # ── Memory ─────────────────────────────────────────────────────────────────
    mem      = psutil.virtual_memory()
    swap     = psutil.swap_memory()

    # ── Disk ───────────────────────────────────────────────────────────────────
    disk_lines: list[str] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            bar   = _usage_bar(usage.percent)
            disk_lines.append(
                f"  {part.mountpoint:<20} {_fmt_bytes(usage.used):>10} / "
                f"{_fmt_bytes(usage.total):<10} {bar} {usage.percent:.1f}%"
            )
        except PermissionError:
            continue

    # ── Network ────────────────────────────────────────────────────────────────
    net   = psutil.net_io_counters()
    net_str = (
        f"↑ {_fmt_bytes(net.bytes_sent)}  ↓ {_fmt_bytes(net.bytes_recv)}  "
        f"Pkts ↑{net.packets_sent:,} ↓{net.packets_recv:,}"
    )

    # ── Top processes (by CPU) ─────────────────────────────────────────────────
    procs: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            if info["cpu_percent"] is not None:
                procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    top_cpu = sorted(procs, key=lambda x: x["cpu_percent"] or 0, reverse=True)[:5]
    top_mem = sorted(procs, key=lambda x: x["memory_percent"] or 0, reverse=True)[:5]

    top_cpu_str = "\n".join(
        f"  {p['pid']:>6}  {(p['name'] or 'N/A')[:25]:<25}  CPU {p['cpu_percent']:>5.1f}%"
        for p in top_cpu
    )
    top_mem_str = "\n".join(
        f"  {p['pid']:>6}  {(p['name'] or 'N/A')[:25]:<25}  MEM {p['memory_percent']:>5.1f}%"
        for p in top_mem
    )

    cpu_bar  = _usage_bar(cpu_pct)
    mem_bar  = _usage_bar(mem.percent)
    swap_bar = _usage_bar(swap.percent)

    report = f"""\
## System Monitor — {now}

### CPU
  Usage    : {cpu_bar} {cpu_pct:.1f}%
  Cores    : {cpu_count} logical / {cpu_phys} physical
  Frequency: {freq_str}
  Load avg : {load_str} (1m/5m/15m)

### Memory
  RAM  : {mem_bar} {mem.percent:.1f}%  ({_fmt_bytes(mem.used)} / {_fmt_bytes(mem.total)})
  Swap : {swap_bar} {swap.percent:.1f}%  ({_fmt_bytes(swap.used)} / {_fmt_bytes(swap.total)})

### Disk
{chr(10).join(disk_lines) if disk_lines else "  No disks found."}

### Network (cumulative since boot)
  {net_str}

### Top 5 Processes — CPU
{top_cpu_str or "  N/A"}

### Top 5 Processes — Memory
{top_mem_str or "  N/A"}
"""

    return report.strip()


def _usage_bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    bar    = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"
