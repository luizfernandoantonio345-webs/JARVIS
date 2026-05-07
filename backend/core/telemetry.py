"""
telemetry — Structured Telemetry: OpenTelemetry traces + Prometheus metrics  (FASE 13D)

Usage
-----
    from core.telemetry import tracer, metrics, trace_span

    # Tracing
    with trace_span("my_operation", attributes={"user_id": session_id}):
        ...

    # Metrics
    metrics.llm_latency.record(latency_ms, {"model": "gpt-4o-mini", "tier": "complex"})
    metrics.job_counter.add(1, {"status": "done"})

Prometheus scrape endpoint: GET /metrics  (mounted in main.py)

OpenTelemetry export:
  - OTLP gRPC if JARVIS_OTEL_ENDPOINT is set (e.g. http://localhost:4317)
  - Console exporter if JARVIS_OTEL_CONSOLE=true
  - No-op if neither configured
"""

from __future__ import annotations

import logging
import os
import time
import uuid
import asyncio
from collections import Counter, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Awaitable, Callable, Generator

log = logging.getLogger(__name__)

_pipeline_traces: deque[dict[str, Any]] = deque(maxlen=100)
_trace_broadcaster: Callable[[dict[str, Any]], Awaitable[None]] | None = None


def set_trace_broadcaster(broadcaster: Callable[[dict[str, Any]], Awaitable[None]] | None) -> None:
    global _trace_broadcaster
    _trace_broadcaster = broadcaster


async def record_pipeline_trace(
    *,
    source: str,
    stages: dict[str, float],
    intent_detected: str | None = None,
    intent_confidence: float = 0.0,
    fallback_to_chat: bool = False,
    success: bool = True,
    error: str | None = None,
) -> dict[str, Any]:
    trace = {
        "trace_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "stages": stages,
        "total_ms": round(float(stages.get("total_ms", sum(stages.values()))), 2),
        "intent_detected": intent_detected,
        "intent_confidence": round(float(intent_confidence or 0.0), 4),
        "fallback_to_chat": bool(fallback_to_chat),
        "success": bool(success),
        "error": error,
    }
    _pipeline_traces.appendleft(trace)
    if _trace_broadcaster:
        try:
            await _trace_broadcaster({"type": "pipeline_trace", "trace": trace})
        except Exception:
            log.debug("pipeline trace broadcast failed", exc_info=True)
    return trace


def get_pipeline_traces(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    return list(_pipeline_traces)[:limit]


def get_pipeline_summary() -> dict[str, Any]:
    traces = list(_pipeline_traces)
    if not traces:
        return {
            "count": 0,
            "avg_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "error_rate": 0.0,
            "fallback_rate": 0.0,
            "top_intents": [],
            "stage_averages": {},
        }
    totals = [float(item.get("total_ms") or 0.0) for item in traces]
    errors = [item for item in traces if not item.get("success")]
    fallbacks = [item for item in traces if item.get("fallback_to_chat")]
    intents = Counter(item.get("intent_detected") or "none" for item in traces)
    stage_names = sorted({name for item in traces for name in item.get("stages", {})})
    return {
        "count": len(traces),
        "avg_ms": round(mean(totals), 2),
        "p95_ms": _percentile(totals, 95),
        "p99_ms": _percentile(totals, 99),
        "error_rate": round(len(errors) / len(traces), 4),
        "fallback_rate": round(len(fallbacks) / len(traces), 4),
        "top_intents": intents.most_common(10),
        "stage_averages": {
            name: round(mean([float(t.get("stages", {}).get(name, 0.0)) for t in traces]), 2)
            for name in stage_names
        },
    }


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return round(ordered[index], 2)

# ── OpenTelemetry bootstrap ────────────────────────────────────────────────────

_tracer = None
_meter  = None
_otel_initialized = False


def _init_otel() -> None:
    global _tracer, _meter, _otel_initialized
    if _otel_initialized:
        return
    _otel_initialized = True

    try:
        from opentelemetry import trace as otel_trace, metrics as otel_metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter, PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": "jarvis", "service.version": "5.0.0"})

        # ── Tracer provider ──────────────────────────────────────────────────
        tracer_provider = TracerProvider(resource=resource)
        otel_endpoint = os.getenv("JARVIS_OTEL_ENDPOINT", "")
        console_traces = os.getenv("JARVIS_OTEL_CONSOLE", "false").lower() == "true"

        if otel_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
                tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                log.info("telemetry: OTLP trace exporter → %s", otel_endpoint)
            except ImportError:
                log.warning("telemetry: opentelemetry-exporter-otlp not installed")
        if console_traces:
            tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            log.info("telemetry: console trace exporter enabled")

        otel_trace.set_tracer_provider(tracer_provider)
        _tracer = otel_trace.get_tracer("jarvis")

        # ── Meter provider ───────────────────────────────────────────────────
        readers = []
        if otel_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
                readers.append(PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=otel_endpoint, insecure=True),
                    export_interval_millis=15000,
                ))
            except ImportError:
                pass
        if console_traces:
            readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=60000))

        meter_provider = MeterProvider(resource=resource, metric_readers=readers)
        otel_metrics.set_meter_provider(meter_provider)
        _meter = otel_metrics.get_meter("jarvis")

        log.info("telemetry: OpenTelemetry initialized (tracer=%s, meter=%s)", _tracer, _meter)
    except ImportError:
        log.info("telemetry: opentelemetry-sdk not installed — using no-op telemetry")
    except Exception as exc:
        log.warning("telemetry: OTel init failed: %s", exc)


# ── Prometheus metrics ─────────────────────────────────────────────────────────

_prom_initialized = False
_prom_registry    = None

# Metric handles (populated on first use)
_llm_latency_histogram   = None
_job_counter             = None
_event_counter           = None
_ws_connections_gauge    = None
_cache_hits_counter      = None
_agent_latency_histogram = None


def _init_prometheus() -> None:
    global _prom_initialized, _prom_registry
    global _llm_latency_histogram, _job_counter, _event_counter
    global _ws_connections_gauge, _cache_hits_counter, _agent_latency_histogram

    if _prom_initialized:
        return
    _prom_initialized = True

    try:
        from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, REGISTRY

        _prom_registry = REGISTRY

        _llm_latency_histogram = Histogram(
            "jarvis_llm_latency_ms",
            "LLM call latency in milliseconds",
            ["model", "tier", "cached"],
            buckets=[50, 100, 200, 500, 1000, 2000, 5000, 10000],
        )
        _job_counter = Counter(
            "jarvis_autodev_jobs_total",
            "AutoDev jobs completed",
            ["status"],
        )
        _event_counter = Counter(
            "jarvis_events_total",
            "Autonomy/agent events processed",
            ["event_type"],
        )
        _ws_connections_gauge = Gauge(
            "jarvis_ws_connections",
            "Active WebSocket connections",
        )
        _cache_hits_counter = Counter(
            "jarvis_cache_hits_total",
            "Cache hits (exact or semantic)",
            ["cache_type"],
        )
        _agent_latency_histogram = Histogram(
            "jarvis_agent_latency_ms",
            "Agent execution latency in milliseconds",
            ["agent_role"],
            buckets=[100, 300, 500, 1000, 2000, 5000, 15000],
        )

        log.info("telemetry: Prometheus metrics initialized")
    except ImportError:
        log.info("telemetry: prometheus_client not installed — metrics disabled")
    except ValueError:
        # Already registered (e.g., hot reload) — ignore
        pass
    except Exception as exc:
        log.warning("telemetry: Prometheus init failed: %s", exc)


# ── Metric recording helpers ───────────────────────────────────────────────────

def record_llm_latency(latency_ms: float, model: str, tier: str, cached: bool = False) -> None:
    _init_prometheus()
    if _llm_latency_histogram:
        try:
            _llm_latency_histogram.labels(
                model=model, tier=tier, cached=str(cached).lower()
            ).observe(latency_ms)
        except Exception:
            pass


def record_job(status: str) -> None:
    _init_prometheus()
    if _job_counter:
        try:
            _job_counter.labels(status=status).inc()
        except Exception:
            pass


def record_event(event_type: str) -> None:
    _init_prometheus()
    if _event_counter:
        try:
            _event_counter.labels(event_type=event_type).inc()
        except Exception:
            pass


def set_ws_connections(count: int) -> None:
    _init_prometheus()
    if _ws_connections_gauge:
        try:
            _ws_connections_gauge.set(count)
        except Exception:
            pass


def record_cache_hit(cache_type: str) -> None:
    _init_prometheus()
    if _cache_hits_counter:
        try:
            _cache_hits_counter.labels(cache_type=cache_type).inc()
        except Exception:
            pass


def record_agent_latency(latency_ms: float, agent_role: str) -> None:
    _init_prometheus()
    if _agent_latency_histogram:
        try:
            _agent_latency_histogram.labels(agent_role=agent_role).observe(latency_ms)
        except Exception:
            pass


# ── Tracing context manager ────────────────────────────────────────────────────

@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Generator:
    """
    Context manager that creates an OTel span if available,
    otherwise falls through transparently.
    """
    _init_otel()
    if _tracer is not None:
        try:
            with _tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, str(v))
                yield span
            return
        except Exception as exc:
            log.debug("trace_span: suppressed OTel error: %s", exc)
    # No-op fallback
    yield None


def get_current_trace_id() -> str | None:
    """Return the current OTel trace ID as hex string, or None."""
    try:
        from opentelemetry import trace as otel_trace
        span = otel_trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None


# ── Initialize on import ──────────────────────────────────────────────────────

def initialize() -> None:
    """Call once at startup to set up all telemetry providers."""
    _init_otel()
    _init_prometheus()
