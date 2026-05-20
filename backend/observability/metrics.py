import time, logging
from collections import defaultdict, deque
log = logging.getLogger("jarvis.metrics")

class RuntimeMetrics:
    def __init__(self):
        self._counters = defaultdict(int)
        self._timings  = defaultdict(lambda: deque(maxlen=200))
        self._gauges   = {}
        self._start    = time.time()

    def inc(self, key: str, val: int = 1):
        self._counters[key] += val

    def timing(self, key: str, seconds: float):
        self._timings[key].append(seconds)

    def gauge(self, key: str, val):
        self._gauges[key] = val

    def snapshot(self) -> dict:
        snap = {
            "uptime": int(time.time() - self._start),
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "timings": {}
        }
        for k, vals in self._timings.items():
            lst = list(vals)
            if lst:
                snap["timings"][k] = {
                    "count": len(lst),
                    "avg_ms": round(sum(lst)/len(lst)*1000, 1),
                    "max_ms": round(max(lst)*1000, 1),
                    "p95_ms": round(sorted(lst)[int(len(lst)*0.95)]*1000, 1)
                }
        return snap

_m = None
def get_metrics() -> RuntimeMetrics:
    global _m
    if _m is None:
        _m = RuntimeMetrics()
    return _m
