import { useEffect, useMemo, useState } from 'react'
import './JarvisDashboard.css'

type PipelineTrace = {
  trace_id: string
  timestamp: string
  source: string
  stages: Record<string, number>
  total_ms: number
  intent_detected: string | null
  intent_confidence: number
  fallback_to_chat: boolean
  success: boolean
  error: string | null
}

type AuditEvent = {
  audit_id: string
  timestamp: string
  action_type: string
  risk_level: string
  target: string
  preview: string
  decision: string
  confirmed_by?: string | null
  result: string
}

type SystemState = {
  mode: string
  circuitBreakers: Record<string, string>
  autonomyPending: number
  sentinelEvent: string
}

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) ?? 'ws://localhost:8000/ws/jarvis'

export default function JarvisDashboard() {
  const [traces, setTraces] = useState<PipelineTrace[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([])
  const [state, setState] = useState<SystemState>({
    mode: 'LISTENING',
    circuitBreakers: {},
    autonomyPending: 0,
    sentinelEvent: 'none',
  })
  const [showHistory, setShowHistory] = useState(true)
  const [riskFilter, setRiskFilter] = useState('all')

  useEffect(() => {
    refreshData()
    const interval = window.setInterval(refreshData, 15_000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    const ws = new WebSocket(WS_URL)
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'pipeline_trace' && payload.trace) {
          setTraces((prev) => [payload.trace, ...prev].slice(0, 20))
        }
        if (payload.type === 'state_change') {
          setState((prev) => ({ ...prev, mode: payload.state ?? prev.mode }))
        }
        if (payload.type === 'audit_event' && payload.event) {
          setAuditEvents((prev) => [payload.event, ...prev].slice(0, 50))
        }
        if (payload.type === 'intent_result' && payload.trace) {
          setTraces((prev) => [payload.trace, ...prev].slice(0, 20))
        }
      } catch {
        // Ignore non-dashboard WS messages.
      }
    }
    return () => ws.close()
  }, [])

  const latestTrace = traces[0]
  const filteredAudit = auditEvents.filter((event) => riskFilter === 'all' || event.risk_level === riskFilter)
  const intentStats = useMemo(() => buildIntentStats(traces), [traces])

  async function refreshData() {
    const [traceRes, summaryRes, auditRes, heartbeatRes, sentinelRes] = await Promise.allSettled([
      fetch('/telemetry/traces?limit=20').then((res) => res.json()),
      fetch('/telemetry/summary').then((res) => res.json()),
      fetch('/audit/log?limit=50').then((res) => res.json()),
      fetch('/system/heartbeat').then((res) => res.json()),
      fetch('/sentinel/status').then((res) => res.json()),
    ])
    if (traceRes.status === 'fulfilled') setTraces(traceRes.value.traces ?? [])
    if (summaryRes.status === 'fulfilled') setSummary(summaryRes.value)
    if (auditRes.status === 'fulfilled') setAuditEvents(auditRes.value.events ?? [])
    if (heartbeatRes.status === 'fulfilled') {
      setState((prev) => ({
        ...prev,
        autonomyPending: heartbeatRes.value.autonomy_pending ?? 0,
      }))
    }
    if (sentinelRes.status === 'fulfilled') {
      setState((prev) => ({
        ...prev,
        sentinelEvent: sentinelRes.value.last_event ?? sentinelRes.value.running ? 'running' : 'stopped',
      }))
    }
  }

  async function decideAudit(auditId: string, decision: 'approved' | 'blocked') {
    await fetch(`/audit/log/${auditId}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    })
    await refreshData()
  }

  return (
    <section className="jarvis-dashboard" aria-label="Jarvis system dashboard">
      <div className="dashboard-header">
        <div>
          <h2>JARVIS Control</h2>
          <p>{summary?.count ?? 0} traces | erro {(Number(summary?.error_rate ?? 0) * 100).toFixed(1)}%</p>
        </div>
        <button type="button" onClick={refreshData}>Atualizar</button>
      </div>

      <div className="dashboard-grid">
        <section className="dash-panel pipeline-panel">
          <div className="panel-title">
            <h3>Pipeline</h3>
            <label>
              <input type="checkbox" checked={showHistory} onChange={(e) => setShowHistory(e.target.checked)} />
              Historico
            </label>
          </div>
          {latestTrace ? <PipelineBars trace={latestTrace} /> : <Empty text="Sem traces ainda" />}
          {showHistory && (
            <div className="trace-list">
              {traces.slice(0, 20).map((trace) => (
                <div className="trace-row" key={trace.trace_id}>
                  <span>{trace.intent_detected ?? 'chat'}</span>
                  <strong className={latencyClass(trace.total_ms)}>{Math.round(trace.total_ms)}ms</strong>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="dash-panel">
          <div className="panel-title"><h3>System State</h3></div>
          <div className="state-stack">
            <Metric label="Modo" value={state.mode} />
            <Metric label="Autonomia" value={`${state.autonomyPending} pendentes`} />
            <Metric label="Sentinel v2" value={state.sentinelEvent} />
            <Metric label="Circuit breakers" value={Object.keys(state.circuitBreakers).length ? 'ativos' : 'sem alertas'} />
          </div>
        </section>

        <section className="dash-panel">
          <div className="panel-title"><h3>Intent Stats</h3></div>
          <div className="stats-line">
            <Metric label="Reconhecidos" value={`${intentStats.recognized}%`} />
            <Metric label="Fallback" value={`${intentStats.fallback}%`} />
            <Metric label="Conf. media" value={intentStats.avgConfidence.toFixed(2)} />
          </div>
          <div className="intent-list">
            {intentStats.top.map(([name, count]) => (
              <div className="trace-row" key={name}><span>{name}</span><strong>{count}</strong></div>
            ))}
          </div>
        </section>

        <section className="dash-panel audit-panel">
          <div className="panel-title">
            <h3>Audit Feed</h3>
            <select value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
              <option value="all">todos</option>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
            </select>
          </div>
          <div className="audit-list">
            {filteredAudit.slice(0, 12).map((event) => (
              <article className="audit-row" key={event.audit_id}>
                <div>
                  <span className={`risk risk-${event.risk_level}`}>{event.risk_level}</span>
                  <strong>{event.action_type}</strong>
                  <p>{event.preview || event.target || event.decision}</p>
                </div>
                {event.decision === 'pending_confirmation' && (
                  <div className="audit-actions">
                    <button type="button" onClick={() => decideAudit(event.audit_id, 'approved')}>Aprovar</button>
                    <button type="button" onClick={() => decideAudit(event.audit_id, 'blocked')}>Bloquear</button>
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>

        <section className="dash-panel">
          <div className="panel-title"><h3>Telemetria</h3></div>
          <div className="stats-line">
            <Metric label="Media" value={`${Math.round(summary?.avg_ms ?? 0)}ms`} />
            <Metric label="p95" value={`${Math.round(summary?.p95_ms ?? 0)}ms`} />
            <Metric label="p99" value={`${Math.round(summary?.p99_ms ?? 0)}ms`} />
          </div>
          <MiniChart traces={traces} />
        </section>
      </div>
    </section>
  )
}

function PipelineBars({ trace }: { trace: PipelineTrace }) {
  const stages = Object.entries(trace.stages).filter(([name]) => name !== 'total_ms')
  const max = Math.max(1, ...stages.map(([, value]) => value))
  return (
    <div className="pipeline-bars">
      {stages.map(([name, value]) => (
        <div className="stage-row" key={name}>
          <span>{name.replace('_ms', '')}</span>
          <div className="stage-track"><div className={`stage-fill ${latencyClass(value)}`} style={{ width: `${Math.max(6, (value / max) * 100)}%` }} /></div>
          <strong>{Math.round(value)}ms</strong>
        </div>
      ))}
    </div>
  )
}

function MiniChart({ traces }: { traces: PipelineTrace[] }) {
  const data = traces.slice(0, 24).reverse()
  const max = Math.max(1, ...data.map((trace) => trace.total_ms))
  return (
    <div className="mini-chart">
      {data.map((trace) => (
        <span key={trace.trace_id} className={trace.success ? 'bar-ok' : 'bar-error'} style={{ height: `${Math.max(8, (trace.total_ms / max) * 100)}%` }} />
      ))}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>
}

function Empty({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>
}

function latencyClass(value: number) {
  if (value < 500) return 'latency-ok'
  if (value < 2000) return 'latency-warn'
  return 'latency-bad'
}

function buildIntentStats(traces: PipelineTrace[]) {
  if (!traces.length) return { recognized: 0, fallback: 0, avgConfidence: 0, top: [] as [string, number][] }
  const recognized = traces.filter((trace) => trace.intent_detected && !trace.fallback_to_chat).length
  const fallback = traces.filter((trace) => trace.fallback_to_chat).length
  const avgConfidence = traces.reduce((sum, trace) => sum + (trace.intent_confidence || 0), 0) / traces.length
  const counts = traces.reduce<Record<string, number>>((acc, trace) => {
    const name = trace.intent_detected ?? 'chat'
    acc[name] = (acc[name] ?? 0) + 1
    return acc
  }, {})
  return {
    recognized: Math.round((recognized / traces.length) * 100),
    fallback: Math.round((fallback / traces.length) * 100),
    avgConfidence,
    top: Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10),
  }
}
