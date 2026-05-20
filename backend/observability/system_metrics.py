import asyncio, logging
log = logging.getLogger("jarvis.sysmetrics")

async def collect(interval: int = 30):
    while True:
        try:
            import psutil
            from backend.observability.metrics import get_metrics
            m = get_metrics()
            m.gauge("cpu_percent",  psutil.cpu_percent(interval=None))
            vm = psutil.virtual_memory()
            m.gauge("ram_percent",  vm.percent)
            m.gauge("ram_used_mb",  vm.used // 1024 // 1024)
            m.gauge("ram_total_mb", vm.total // 1024 // 1024)
            try:
                disk = psutil.disk_usage("C:/")
                m.gauge("disk_percent", disk.percent)
                m.gauge("disk_free_gb", disk.free // 1024**3)
            except Exception:
                pass
        except ImportError:
            log.debug("[SYSMETRICS] psutil nao instalado")
            return
        except Exception as e:
            log.warning("[SYSMETRICS] %s", e)
        await asyncio.sleep(interval)
