"""Rotas de health check, métricas e capacidades — JARVIS v8.0."""
import logging
import time

import httpx
from fastapi import APIRouter

router = APIRouter()
log = logging.getLogger(__name__)

_START_TIME = time.time()
_JARVIS_VERSION = "8.0"


async def _check_ollama(url: str, timeout: float = 1.0) -> tuple[bool, list[str]]:
    try:
        clean = url.replace("localhost", "127.0.0.1")
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=0.5)) as c:
            r = await c.get(f"{clean}/api/tags")
            if r.status_code != 200:
                return False, []
            models = [m.get("name", "") for m in r.json().get("models", [])]
            return True, [m for m in models if m]
    except Exception:
        return False, []


@router.get("/health")
async def health_check():
    import asyncio
    from config import get_config
    from runtime.watchdog import get_watchdog

    cfg = get_config()
    wd = get_watchdog()
    uptime_s = wd.uptime()
    h, rem = divmod(uptime_s, 3600)
    m, s = divmod(rem, 60)

    try:
        ollama_ok, models = await asyncio.wait_for(_check_ollama(cfg.ollama_url), timeout=1.5)
    except Exception:
        ollama_ok, models = False, []

    degraded = [] if ollama_ok else ["ollama"]

    return {
        "status":   "ok" if not degraded else "degraded",
        "service":  "JARVIS API",
        "version":  "6.0",
        "uptime":   f"{h:02d}:{m:02d}:{s:02d}",
        "uptime_seconds": uptime_s,
        "models": {
            "active":  os_env("JARVIS_MODEL", cfg.local_model),
            "ollama":  "ok" if ollama_ok else "error",
            "list":    models,
        },
        "degraded": degraded,
    }


@router.get("/status")
async def status():
    from config import get_config
    from runtime.watchdog import get_watchdog
    cfg = get_config()
    wd = get_watchdog()
    import os
    return {
        "jarvis":          "online",
        "model":           os.getenv("JARVIS_MODEL", cfg.local_model),
        "uptime_seconds":  wd.uptime(),
        "voice":           os.getenv("JARVIS_VOICE_ENABLED", "true") == "true",
        "ollama_url":      cfg.ollama_url,
    }


@router.get("/metrics")
async def get_metrics():
    """Métricas reais do sistema via psutil — usadas pelo frontend."""
    try:
        import psutil

        cpu     = psutil.cpu_percent(interval=0.3)
        ram     = psutil.virtual_memory()
        disk    = psutil.disk_usage("C:\\" if __import__("sys").platform == "win32" else "/")
        net     = psutil.net_io_counters()
        procs   = len(psutil.pids())

        # Top 3 processos por CPU
        top_procs = []
        try:
            all_procs = [
                p.info for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"])
                if p.info.get("cpu_percent") is not None
            ]
            top_procs = sorted(all_procs, key=lambda x: x["cpu_percent"] or 0, reverse=True)[:3]
            top_procs = [{"name": p["name"], "cpu": round(p["cpu_percent"], 1)} for p in top_procs]
        except Exception:
            pass

        return {
            "cpu_percent":   round(cpu, 1),
            "ram_percent":   round(ram.percent, 1),
            "ram_used_gb":   round(ram.used  / 1024**3, 1),
            "ram_total_gb":  round(ram.total / 1024**3, 1),
            "ram_free_gb":   round(ram.available / 1024**3, 1),
            "disk_percent":  round(disk.percent, 1),
            "disk_used_gb":  round(disk.used  / 1024**3, 1),
            "disk_free_gb":  round(disk.free  / 1024**3, 1),
            "disk_total_gb": round(disk.total / 1024**3, 1),
            "net_sent_mb":   round(net.bytes_sent / 1024**2, 1),
            "net_recv_mb":   round(net.bytes_recv / 1024**2, 1),
            "process_count": procs,
            "top_processes": top_procs,
        }
    except ImportError:
        return {"error": "psutil não instalado", "cpu_percent": 0, "ram_percent": 0}
    except Exception as e:
        log.warning("[METRICS] Erro: %s", e)
        return {"error": str(e), "cpu_percent": 0, "ram_percent": 0}


@router.get("/system/info")
async def system_info():
    """Snapshot completo do sistema — versão, modelo, config, agentes ativos."""
    import os, sys, platform
    from config import get_config
    from runtime.watchdog import get_watchdog
    cfg = get_config()
    wd = get_watchdog()
    uptime_s = wd.uptime()

    info: dict = {
        "jarvis_version": "6.0",
        "python_version": sys.version.split()[0],
        "platform": platform.system() + " " + platform.release(),
        "model": os.getenv("JARVIS_MODEL", cfg.local_model),
        "ollama_url": cfg.ollama_url,
        "uptime_seconds": uptime_s,
        "uptime_human": f"{int(uptime_s//3600):02d}:{int((uptime_s%3600)//60):02d}:{int(uptime_s%60):02d}",
        "tts_voice": cfg.tts_voice,
        "voice_enabled": cfg.voice_enabled,
        "safe_mode": cfg.safe_mode,
        "debug": cfg.debug,
    }

    try:
        import psutil
        info["cpu_count"] = psutil.cpu_count()
        ram = psutil.virtual_memory()
        info["ram_total_gb"] = round(ram.total / 1024**3, 1)
        info["ram_used_gb"]  = round(ram.used  / 1024**3, 1)
    except Exception:
        pass

    try:
        from routes.agents import list_agents_route
        agents_data = list_agents_route()
        info["agent_count"] = agents_data.get("count", 0)
    except Exception:
        info["agent_count"] = 0

    return info


@router.get("/audit")
async def get_audit_log(limit: int = 50):
    """Retorna as últimas entradas do audit log (apenas localhost)."""
    try:
        from middleware.audit import get_recent_audit
        entries = get_recent_audit(limit)
        return {"count": len(entries), "entries": entries}
    except Exception as e:
        return {"error": str(e), "entries": []}


@router.get("/security/status")
async def security_status():
    """Estado da camada de segurança — middlewares ativos."""
    checks = {}
    try:
        from middleware.security_headers import SecurityHeadersMiddleware
        checks["security_headers"] = "active"
    except Exception:
        checks["security_headers"] = "inactive"
    try:
        from middleware.input_guard import InputGuardMiddleware
        checks["input_guard"] = "active"
    except Exception:
        checks["input_guard"] = "inactive"
    try:
        from middleware.audit import AuditMiddleware
        checks["audit_log"] = "active"
    except Exception:
        checks["audit_log"] = "inactive"
    try:
        from middleware.ws_guard import check_ws_allowed
        checks["ws_guard"] = "active"
    except Exception:
        checks["ws_guard"] = "inactive"
    try:
        from utils.crypto import generate_token
        checks["crypto"] = "active"
    except Exception:
        checks["crypto"] = "inactive"

    active = sum(1 for v in checks.values() if v == "active")
    total = len(checks)
    return {
        "security_score": f"{active}/{total}",
        "level": "MAXIMUM" if active == total else "PARTIAL" if active >= 3 else "MINIMAL",
        "checks": checks,
    }


@router.get("/network/info")
async def network_info():
    """
    Retorna os IPs locais do PC para o utilizador conectar o celular.
    O celular acede a http://[IP]:8000 no mesmo WiFi.
    """
    import socket
    hostname = socket.gethostname()
    ips: list[str] = []

    # Método 1: getaddrinfo
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ":" not in ip:
                if ip not in ips:
                    ips.append(ip)
    except Exception:
        pass

    # Método 2: UDP trick (mais confiável para achar o IP da rede ativa)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
        if primary and primary not in ips and not primary.startswith("127."):
            ips.insert(0, primary)
    except Exception:
        pass

    primary_ip = ips[0] if ips else "—"
    port = 8000

    return {
        "hostname": hostname,
        "primary_ip": primary_ip,
        "all_ips": ips,
        "port": port,
        "jarvis_url": f"http://{primary_ip}:{port}",
        "qr_hint": f"Abra http://{primary_ip}:{port} no celular (mesmo WiFi)",
    }


def os_env(key: str, default: str = "") -> str:
    import os
    return os.getenv(key, default)


@router.get("/ping")
async def ping():
    """Ultra-leve liveness check — responde em <1ms."""
    return {"pong": True, "ts": time.time(), "version": _JARVIS_VERSION}


@router.get("/ready")
async def ready():
    """Readiness probe — verifica se Ollama está acessível."""
    from fastapi.responses import JSONResponse
    from config import get_config
    cfg = get_config()
    ollama_ok, _ = await _check_ollama(cfg.ollama_url, timeout=2.0)
    return JSONResponse(
        content={"ready": ollama_ok, "ollama": "up" if ollama_ok else "down", "version": _JARVIS_VERSION},
        status_code=200 if ollama_ok else 503,
    )


@router.get("/capabilities")
async def get_capabilities():
    """Lista todas as capacidades do JARVIS v8.0 — endpoints, agentes, power modes."""
    import os
    model = os_env("JARVIS_MODEL", "qwen2:0.5b")
    return {
        "version": _JARVIS_VERSION,
        "model": model,
        "uptime_seconds": round(time.time() - _START_TIME),
        "endpoints": {
            "chat": ["POST /chat", "POST /chat/stream", "GET /chat/history", "DELETE /chat/{session_id}"],
            "voice": ["POST /voice/command", "GET /voice/tts", "GET /voice/status"],
            "osint": ["POST /investigate"],
            "analysis": ["POST /analyze"],
            "architect": ["POST /architect"],
            "generation": [
                "POST /generate/code", "POST /generate/tests", "POST /generate/docs",
                "POST /generate/regex", "POST /generate/diagram", "POST /generate/api",
                "POST /generate/docker", "POST /generate/readme", "POST /generate/refactor",
                "POST /generate/convert", "POST /generate/explain", "POST /generate/fix",
                "POST /generate/review", "POST /generate/optimize", "POST /generate/summarize",
            ],
            "tasks": ["POST /tasks", "GET /tasks", "GET /tasks/{id}", "DELETE /tasks/{id}", "POST /tasks/{id}/retry"],
            "agents": ["GET /agents", "POST /agents/{role}/run", "POST /agents/run"],
            "memory": ["GET /memory/search", "POST /memory/semantic", "GET /memory/stats"],
            "system": ["GET /health", "GET /status", "GET /metrics", "GET /system/info", "GET /ping", "GET /ready", "GET /network/info"],
        },
        "power_modes": {
            "F2": "OSINT Investigation — /investigate",
            "F3": "Code Analysis — /analyze",
            "F4": "System Architect — /architect",
            "F5": "Code Generator — /generate/code (v8.0)",
            "F6": "Summarizer — /generate/summarize (v8.0)",
        },
        "languages_supported": [
            "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "PHP",
            "Ruby", "Swift", "Kotlin", "Dart/Flutter", "C#", "C++", "C",
            "SQL", "Shell", "PowerShell", "YAML", "HTML", "CSS", "Terraform",
        ],
        "agent_roles": [
            "dev", "security", "architect", "qa", "devops", "ml", "osint",
            "hacker", "pentest", "cloud", "mobile", "fullstack",
        ],
    }


@router.get("/disk")
async def disk_info():
    """Informações detalhadas de disco."""
    try:
        import psutil, sys
        path = "C:\\" if sys.platform == "win32" else "/"
        disk = psutil.disk_usage(path)
        partitions = []
        for p in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(p.mountpoint)
                partitions.append({
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total_gb": round(usage.total / 1024**3, 1),
                    "used_gb": round(usage.used / 1024**3, 1),
                    "free_gb": round(usage.free / 1024**3, 1),
                    "percent": usage.percent,
                })
            except Exception:
                pass
        return {
            "primary_total_gb": round(disk.total / 1024**3, 1),
            "primary_used_gb": round(disk.used / 1024**3, 1),
            "primary_free_gb": round(disk.free / 1024**3, 1),
            "primary_percent": disk.percent,
            "partitions": partitions,
        }
    except ImportError:
        return {"error": "psutil não instalado"}


@router.get("/processes")
async def top_processes(limit: int = 10):
    """Top processos por uso de CPU e memória."""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = p.info
                if info["cpu_percent"] is not None:
                    procs.append(info)
            except Exception:
                pass
        procs.sort(key=lambda x: x.get("cpu_percent", 0) or 0, reverse=True)
        return {
            "count": len(procs),
            "top_cpu": procs[:limit],
            "top_memory": sorted(procs, key=lambda x: x.get("memory_percent", 0) or 0, reverse=True)[:limit],
        }
    except ImportError:
        return {"error": "psutil não instalado"}


@router.get("/env")
async def safe_env():
    """Variáveis de ambiente JARVIS (sem secrets) — para diagnóstico."""
    import os
    safe_keys = [
        "JARVIS_MODEL", "JARVIS_OLLAMA_URL", "JARVIS_HOST", "JARVIS_PORT",
        "JARVIS_DEBUG", "JARVIS_VOICE_ENABLED", "JARVIS_AUTONOMY_ENABLED",
        "JARVIS_SAFE_MODE", "JARVIS_TTS_VOICE", "JARVIS_CORS_ORIGINS",
        "JARVIS_LOG_LEVEL", "JARVIS_TURBO_MODE_ENABLED", "JARVIS_NIGHT_MODE_ENABLED",
        "OLLAMA_HOST", "OLLAMA_KEEP_ALIVE", "OMP_NUM_THREADS",
    ]
    return {k: os.getenv(k, "—") for k in safe_keys}
