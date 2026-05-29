"""
Enhanced observability: Metrics, Health checks, Performance tracking
"""

import time
import logging
from typing import Dict, Any

log = logging.getLogger(__name__)

class SystemMetrics:
    """Track JARVIS system performance metrics"""
    
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.latencies = []
        self.llm_latencies = []
    
    def record_request(self, latency_ms: float, success: bool = True):
        """Record an API request"""
        self.request_count += 1
        self.latencies.append(latency_ms)
        if not success:
            self.error_count += 1
        
        # Keep only last 1000 samples
        if len(self.latencies) > 1000:
            self.latencies = self.latencies[-1000:]
    
    def record_llm_call(self, latency_ms: float):
        """Record an LLM API call"""
        self.llm_latencies.append(latency_ms)
        if len(self.llm_latencies) > 500:
            self.llm_latencies = self.llm_latencies[-500:]
    
    def health_score(self) -> int:
        """Calculate system health score 0-100"""
        if self.request_count == 0:
            return 100
        
        error_rate = self.error_count / max(self.request_count, 1)
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        
        # Score: 100 - (error_rate*100) - (avg_latency/10 capped at 20)
        score = 100 - (error_rate * 100) - min(avg_latency / 10, 20)
        return max(0, int(score))
    
    def snapshot(self) -> Dict[str, Any]:
        """Get metrics snapshot"""
        uptime = time.time() - self.start_time
        
        return {
            "uptime_seconds": int(uptime),
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / max(self.request_count, 1),
            "avg_latency_ms": sum(self.latencies) / len(self.latencies) if self.latencies else 0,
            "p95_latency_ms": sorted(self.latencies)[int(len(self.latencies)*0.95)] if len(self.latencies) > 1 else 0,
            "avg_llm_latency_ms": sum(self.llm_latencies) / len(self.llm_latencies) if self.llm_latencies else 0,
            "health_score": self.health_score(),
        }

# Global metrics instance
_metrics = SystemMetrics()

def get_metrics() -> SystemMetrics:
    """Get global metrics instance"""
    return _metrics
