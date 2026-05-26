#!/usr/bin/env python
"""
JARVIS v6.0 - Health Monitor

Continuous monitoring of system health with alerts.
Checks backend, Ollama, database, and system resources.

Usage:
    python scripts/health_monitor.py
    python scripts/health_monitor.py --interval 30
    python scripts/health_monitor.py --alert-webhook https://...
"""

import asyncio
import json
import psutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import httpx
import logging
import argparse
from dataclasses import dataclass, asdict
from enum import Enum

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

BACKEND_URL = "http://localhost:8000"
OLLAMA_URL = "http://localhost:11434"
CHECK_INTERVAL = 30  # seconds
LOG_FILE = "logs/health_monitor.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE) if Path("logs").exists() else logging.NullHandler()
    ]
)
logger = logging.getLogger("HEALTH_MONITOR")


# ════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════════════════════

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    message: str
    response_time_ms: float = 0
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class SystemMetrics:
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    disk_free_gb: float
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class HealthReport:
    timestamp: str
    overall_status: HealthStatus
    components: Dict[str, ComponentHealth]
    metrics: SystemMetrics
    alerts: list


# ════════════════════════════════════════════════════════════════════════════
# HEALTH CHECKS
# ════════════════════════════════════════════════════════════════════════════

async def check_backend() -> ComponentHealth:
    """Check if backend is running and responsive."""
    
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{BACKEND_URL}/health")
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                return ComponentHealth(
                    name="Backend",
                    status=HealthStatus.HEALTHY,
                    message=f"Status: {data.get('status', 'ok')}",
                    response_time_ms=duration
                )
            else:
                return ComponentHealth(
                    name="Backend",
                    status=HealthStatus.CRITICAL,
                    message=f"HTTP {response.status_code}",
                    response_time_ms=duration
                )
    except asyncio.TimeoutError:
        return ComponentHealth(
            name="Backend",
            status=HealthStatus.CRITICAL,
            message="Timeout (>5s)"
        )
    except Exception as e:
        return ComponentHealth(
            name="Backend",
            status=HealthStatus.CRITICAL,
            message=f"Error: {str(e)}"
        )


async def check_ollama() -> ComponentHealth:
    """Check if Ollama is running and has models."""
    
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                if models:
                    model_names = [m.get("name", "unknown") for m in models[:3]]
                    return ComponentHealth(
                        name="Ollama",
                        status=HealthStatus.HEALTHY,
                        message=f"Models: {', '.join(model_names)}",
                        response_time_ms=duration
                    )
                else:
                    return ComponentHealth(
                        name="Ollama",
                        status=HealthStatus.DEGRADED,
                        message="No models available",
                        response_time_ms=duration
                    )
            else:
                return ComponentHealth(
                    name="Ollama",
                    status=HealthStatus.CRITICAL,
                    message=f"HTTP {response.status_code}",
                    response_time_ms=duration
                )
    except Exception as e:
        return ComponentHealth(
            name="Ollama",
            status=HealthStatus.CRITICAL,
            message="Not responding"
        )


async def check_database() -> ComponentHealth:
    """Check if database file is healthy."""
    
    db_path = Path("data/jarvis_memory.db")
    
    if not db_path.exists():
        return ComponentHealth(
            name="Database",
            status=HealthStatus.CRITICAL,
            message=f"File not found: {db_path}"
        )
    
    try:
        size_mb = db_path.stat().st_size / (1024 * 1024)
        
        if size_mb > 500:
            return ComponentHealth(
                name="Database",
                status=HealthStatus.DEGRADED,
                message=f"Large DB: {size_mb:.1f}MB (max 500MB)"
            )
        
        # Try to query database
        import sqlite3
        conn = sqlite3.connect(str(db_path), timeout=2)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM experiences")
        count = cursor.fetchone()[0]
        conn.close()
        
        return ComponentHealth(
            name="Database",
            status=HealthStatus.HEALTHY,
            message=f"OK ({count} experiences, {size_mb:.1f}MB)"
        )
    except Exception as e:
        return ComponentHealth(
            name="Database",
            status=HealthStatus.CRITICAL,
            message=f"Error: {str(e)}"
        )


def check_system_resources() -> SystemMetrics:
    """Check CPU, RAM, and disk usage."""
    
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    
    return SystemMetrics(
        cpu_percent=cpu_percent,
        memory_percent=memory.percent,
        disk_percent=disk.percent,
        disk_free_gb=disk.free / (1024**3)
    )


# ════════════════════════════════════════════════════════════════════════════
# ALERTING
# ════════════════════════════════════════════════════════════════════════════

def check_thresholds(metrics: SystemMetrics, components: Dict) -> list:
    """Check for threshold violations and generate alerts."""
    
    alerts = []
    
    # CPU threshold
    if metrics.cpu_percent > 80:
        alerts.append(f"⚠️ CPU HIGH: {metrics.cpu_percent:.0f}%")
    
    # Memory threshold
    if metrics.memory_percent > 85:
        alerts.append(f"⚠️ MEMORY HIGH: {metrics.memory_percent:.0f}%")
    
    # Disk threshold
    if metrics.disk_free_gb < 5:
        alerts.append(f"⚠️ DISK LOW: {metrics.disk_free_gb:.1f}GB free")
    
    # Component status
    for name, component in components.items():
        if component.status == HealthStatus.CRITICAL:
            alerts.append(f"❌ {name} CRITICAL: {component.message}")
        elif component.status == HealthStatus.DEGRADED:
            alerts.append(f"⚠️ {name} DEGRADED: {component.message}")
    
    return alerts


async def send_alert(message: str, webhook_url: Optional[str] = None) -> None:
    """Send alert to webhook (if configured)."""
    
    if not webhook_url:
        return
    
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                webhook_url,
                json={
                    "timestamp": datetime.now().isoformat(),
                    "message": message,
                    "severity": "warning"
                }
            )
    except Exception as e:
        logger.error(f"Failed to send webhook alert: {e}")


# ════════════════════════════════════════════════════════════════════════════
# MAIN MONITORING LOOP
# ════════════════════════════════════════════════════════════════════════════

async def perform_health_check(webhook_url: Optional[str] = None) -> HealthReport:
    """Perform complete health check."""
    
    logger.info("Starting health check...")
    
    # Check all components
    components = {
        "backend": await check_backend(),
        "ollama": await check_ollama(),
        "database": await check_database(),
    }
    
    # Get system metrics
    metrics = check_system_resources()
    
    # Check for alerts
    alerts = check_thresholds(metrics, components)
    
    # Determine overall status
    critical_components = [c for c in components.values() if c.status == HealthStatus.CRITICAL]
    degraded_components = [c for c in components.values() if c.status == HealthStatus.DEGRADED]
    
    if critical_components:
        overall_status = HealthStatus.CRITICAL
    elif degraded_components or metrics.cpu_percent > 80 or metrics.memory_percent > 85:
        overall_status = HealthStatus.DEGRADED
    else:
        overall_status = HealthStatus.HEALTHY
    
    # Create report
    report = HealthReport(
        timestamp=datetime.now().isoformat(),
        overall_status=overall_status,
        components=components,
        metrics=metrics,
        alerts=alerts
    )
    
    # Log report
    logger.info(f"Health check complete: {overall_status.value}")
    
    if alerts:
        for alert in alerts:
            logger.warning(alert)
            await send_alert(alert, webhook_url)
    
    return report


def print_report(report: HealthReport) -> None:
    """Pretty-print health report."""
    
    status_icon = {
        HealthStatus.HEALTHY: "✅",
        HealthStatus.DEGRADED: "⚠️",
        HealthStatus.CRITICAL: "❌",
        HealthStatus.UNKNOWN: "❓"
    }
    
    print(f"\n{'='*80}")
    print(f"JARVIS HEALTH REPORT — {report.timestamp}")
    print(f"Overall Status: {status_icon[report.overall_status]} {report.overall_status.value.upper()}")
    print(f"{'='*80}")
    
    print("\n📊 COMPONENTS:")
    for name, component in report.components.items():
        icon = status_icon.get(component.status, "❓")
        print(f"  {icon} {component.name:15} | {component.message} ({component.response_time_ms:.0f}ms)")
    
    print("\n💻 SYSTEM METRICS:")
    print(f"  CPU:    {report.metrics.cpu_percent:5.1f}%")
    print(f"  Memory: {report.metrics.memory_percent:5.1f}%")
    print(f"  Disk:   {report.metrics.disk_percent:5.1f}% ({report.metrics.disk_free_gb:.1f}GB free)")
    
    if report.alerts:
        print(f"\n🚨 ALERTS ({len(report.alerts)}):")
        for alert in report.alerts:
            print(f"  {alert}")
    
    print(f"{'='*80}\n")


async def monitor_loop(
    interval: int = CHECK_INTERVAL,
    webhook_url: Optional[str] = None,
    duration_minutes: Optional[int] = None
) -> None:
    """Continuous monitoring loop."""
    
    logger.info(f"Starting health monitor (interval: {interval}s)")
    
    start_time = time.time()
    iteration = 0
    
    try:
        while True:
            iteration += 1
            logger.info(f"Check #{iteration}")
            
            report = await perform_health_check(webhook_url)
            print_report(report)
            
            # Check duration limit
            if duration_minutes:
                elapsed_minutes = (time.time() - start_time) / 60
                if elapsed_minutes > duration_minutes:
                    logger.info(f"Duration limit reached ({duration_minutes}m)")
                    break
            
            # Wait for next check
            await asyncio.sleep(interval)
    
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
    except Exception as e:
        logger.error(f"Monitor error: {e}", exc_info=True)
        raise


async def main():
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description="JARVIS v6.0 Health Monitor"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=CHECK_INTERVAL,
        help="Check interval in seconds (default: 30)"
    )
    parser.add_argument(
        "--webhook",
        help="Webhook URL for alerts"
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Run for N minutes then exit"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit"
    )
    
    args = parser.parse_args()
    
    if args.once:
        # Single check
        report = await perform_health_check(args.webhook)
        print_report(report)
        sys.exit(0 if report.overall_status == HealthStatus.HEALTHY else 1)
    else:
        # Continuous monitoring
        await monitor_loop(
            interval=args.interval,
            webhook_url=args.webhook,
            duration_minutes=args.duration
        )


if __name__ == "__main__":
    asyncio.run(main())
