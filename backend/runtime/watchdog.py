import asyncio, logging, time
log = logging.getLogger("jarvis.watchdog")

class SystemWatchdog:
    def __init__(self):
        self._checks = {}
        self._failures = {}
        self._start = time.time()

    def register(self, name: str, fn):
        self._checks[name] = fn
        self._failures[name] = 0

    async def run(self, interval: int = 60):
        while True:
            await asyncio.sleep(interval)
            for name, fn in self._checks.items():
                try:
                    ok = await fn() if asyncio.iscoroutinefunction(fn) else fn()
                    if ok:
                        self._failures[name] = 0
                    else:
                        self._failures[name] += 1
                        log.warning("[WATCHDOG] %s falhou (%dx)", name, self._failures[name])
                except Exception as e:
                    log.error("[WATCHDOG] Erro em %s: %s", name, e)
                    self._failures[name] += 1

    def uptime(self) -> int:
        return int(time.time() - self._start)

    def status(self) -> dict:
        return {
            "uptime_seconds": self.uptime(),
            "checks": {k: {"failures": v} for k, v in self._failures.items()}
        }

_wd = None
def get_watchdog() -> SystemWatchdog:
    global _wd
    if _wd is None:
        _wd = SystemWatchdog()
    return _wd
