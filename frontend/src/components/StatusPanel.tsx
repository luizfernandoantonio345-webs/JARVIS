import { useState, useEffect, useCallback } from 'react'
import {
  getProjectStatus,
  getWorkspaceFiles,
  getRecentIntents,
  type ProjectStatus,
  type WorkspaceStatus,
  type RecentIntent,
} from '../services/api'
import './StatusPanel.css'

interface Props {
  sessionId: string
  /** Bump this number to trigger a manual refresh */
  refreshTick: number
}

const DOMAIN_ICONS: Record<string, string> = {
  web_dev: '🌐', api: '⚙️', mobile: '📱', data: '📊',
  security: '🔒', devops: '🚀', system: '🖥', automation: '🤖',
  analysis: '🔍', chat: '💬',
}

const EXT_ICONS: Record<string, string> = {
  '.py': '🐍', '.ts': '📘', '.tsx': '📘', '.js': '📒', '.jsx': '📒',
  '.html': '🌐', '.css': '🎨', '.json': '📋', '.md': '📄',
  '.yaml': '📋', '.yml': '📋', '.sh': '⚙️', '.sql': '🗃',
}

function extIcon(ext: string) {
  return EXT_ICONS[ext] ?? '📄'
}

function formatBytes(b: number) {
  if (b < 1024) return `${b}B`
  return `${(b / 1024).toFixed(1)}KB`
}

export default function StatusPanel({ sessionId, refreshTick }: Props) {
  const [project, setProject] = useState<ProjectStatus | null>(null)
  const [workspace, setWorkspace] = useState<WorkspaceStatus | null>(null)
  const [intents, setIntents] = useState<RecentIntent[]>([])
  const [loading, setLoading] = useState(false)
  const [filesOpen, setFilesOpen] = useState(true)
  const [intentOpen, setIntentOpen] = useState(true)

  const refresh = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const [p, w, i] = await Promise.all([
        getProjectStatus(sessionId),
        getWorkspaceFiles(sessionId),
        getRecentIntents(sessionId, 6),
      ])
      setProject(p)
      setWorkspace(w)
      setIntents(i)
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    refresh()
  }, [refresh, refreshTick])

  const hasProject = project?.has_project
  const proj = project?.project

  return (
    <div className="status-panel">
      <div className="sp-header">
        <span className="sp-title">COCKPIT</span>
        <button className="sp-refresh" onClick={refresh} disabled={loading} title="Refresh">
          {loading ? '⟳' : '↺'}
        </button>
      </div>

      {/* ── Active Project ──────────────────────────────────────────────── */}
      <section className="sp-section">
        <div className="sp-section-label">PROJETO ATIVO</div>
        {hasProject && proj ? (
          <div className="sp-project">
            <div className="sp-project-domain">
              <span className="sp-domain-icon">{DOMAIN_ICONS[proj.domain ?? ''] ?? '🤖'}</span>
              <span className="sp-domain-text">{proj.domain?.toUpperCase()}</span>
              <span className={`sp-status-badge sp-status-${proj.status}`}>{proj.status}</span>
            </div>
            <div className="sp-project-goal">{proj.goal}</div>
            {proj.stack && proj.stack.length > 0 && (
              <div className="sp-tags">
                {proj.stack.map(s => <span key={s} className="sp-tag">{s}</span>)}
              </div>
            )}
          </div>
        ) : (
          <div className="sp-empty">Nenhum projeto ativo</div>
        )}
      </section>

      {/* ── Workspace Files ─────────────────────────────────────────────── */}
      <section className="sp-section">
        <button className="sp-section-toggle" onClick={() => setFilesOpen(o => !o)}>
          <span className="sp-section-label">ARQUIVOS ({workspace?.total_files ?? 0})</span>
          <span className="sp-chevron">{filesOpen ? '▲' : '▼'}</span>
        </button>
        {filesOpen && (
          workspace?.exists && workspace.files.length > 0 ? (
            <div className="sp-files">
              {workspace.files.slice(0, 30).map(f => (
                <div key={f.path} className="sp-file-row" title={f.path}>
                  <span className="sp-file-icon">{extIcon(f.extension)}</span>
                  <span className="sp-file-path">{f.path}</span>
                  <span className="sp-file-size">{formatBytes(f.size_bytes)}</span>
                </div>
              ))}
              {(workspace.files.length > 30) && (
                <div className="sp-file-more">+{workspace.files.length - 30} more</div>
              )}
            </div>
          ) : (
            <div className="sp-empty">Nenhum arquivo criado ainda</div>
          )
        )}
      </section>

      {/* ── Recent Intents ──────────────────────────────────────────────── */}
      <section className="sp-section">
        <button className="sp-section-toggle" onClick={() => setIntentOpen(o => !o)}>
          <span className="sp-section-label">INTENÇÕES RECENTES</span>
          <span className="sp-chevron">{intentOpen ? '▲' : '▼'}</span>
        </button>
        {intentOpen && (
          intents.length > 0 ? (
            <div className="sp-intents">
              {intents.map((it, idx) => (
                <div key={idx} className="sp-intent-row">
                  <div className="sp-intent-meta">
                    <span className="sp-intent-domain">
                      {DOMAIN_ICONS[it.intent?.domain ?? ''] ?? '💬'} {it.intent?.domain ?? 'chat'}
                    </span>
                    {it.intent?.ambiguity_score != null && (
                      <span
                        className={`sp-ambiguity ${it.intent.ambiguity_score > 0.6 ? 'sp-ambiguity-high' : ''}`}
                        title={`Ambiguity: ${it.intent.ambiguity_score}`}
                      >
                        {(it.intent.ambiguity_score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <div className="sp-intent-goal">{it.intent?.goal || it.message?.slice(0, 80)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="sp-empty">Sem histórico nesta sessão</div>
          )
        )}
      </section>

      {/* ── Goal History ────────────────────────────────────────────────── */}
      {project?.recent_goals && project.recent_goals.length > 0 && (
        <section className="sp-section">
          <div className="sp-section-label">HISTÓRICO DE OBJETIVOS</div>
          <div className="sp-goal-chain">
            {project.recent_goals.map((g, i) => (
              <div key={i} className="sp-goal-item">
                <span className="sp-goal-bullet">→</span>
                <span className="sp-goal-text">{g}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
