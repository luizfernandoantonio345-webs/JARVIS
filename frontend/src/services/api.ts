const API_URL = '/chat'
const TASKS_URL = '/tasks'

// ── Chat ──────────────────────────────────────────────────────────────────────

export async function sendMessage(message: string, sessionId: string): Promise<string> {
  const res = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'API error')
  }
  const data = await res.json()
  return data.response
}

export async function clearSession(sessionId: string): Promise<void> {
  await fetch(`${API_URL}/${sessionId}`, { method: 'DELETE' })
}

export async function getMemory(sessionId: string, limit = 20): Promise<{ message: string; response: string }[]> {
  const res = await fetch(`${API_URL}/memory/${sessionId}?limit=${limit}`)
  if (!res.ok) return []
  const data = await res.json()
  return data.history
}

export async function getSessions(): Promise<{ session_id: string; turns: number; last_seen: string }[]> {
  const res = await fetch(`${API_URL}/sessions`)
  if (!res.ok) return []
  const data = await res.json()
  return data.sessions
}

export interface ModelInfo {
  local_model: string
  claude_available: boolean
  openai_available: boolean
  claude_model: string | null
  openai_model: string | null
  complex_threshold: number
}

export async function getModelInfo(): Promise<ModelInfo | null> {
  try {
    const res = await fetch(`${API_URL}/model-info`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

// ── Streaming chat ────────────────────────────────────────────────────────────

export interface StreamEvent {
  type: 'plan' | 'token' | 'done' | 'error'
  content?: string
  steps?: { action: string; input?: string; description?: string }[]
  action?: string
  task_id?: string | null
  detail?: string
}

/**
 * Open a streaming chat connection via SSE (POST /chat/stream).
 * Returns an AbortController so the caller can cancel.
 */
export function streamMessage(
  message: string,
  sessionId: string,
  onEvent: (event: StreamEvent) => void,
  onDone: () => void,
  onError: (err: string) => void,
): AbortController {
  const controller = new AbortController()

  fetch(`${API_URL}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Stream error' }))
        onError(err.detail || 'Stream error')
        return
      }
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const evt: StreamEvent = JSON.parse(line.slice(6))
              onEvent(evt)
              if (evt.type === 'done' || evt.type === 'error') {
                onDone()
              }
            } catch {
              // ignore malformed line
            }
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message || 'Connection error')
        onDone()
      }
    })

  return controller
}

// ── Tasks ─────────────────────────────────────────────────────────────────────

export interface TaskStep {
  index: number
  description: string
  action: string
  success: boolean
  attempts: number
  result_preview: string
}

export interface Task {
  id: string
  session_id: string
  goal: string
  state: 'pending' | 'in_progress' | 'completed' | 'failed'
  current_step: number
  total_steps: number
  progress_pct: number
  created_at: string
  updated_at: string
  steps: TaskStep[]
}

export async function getTasks(sessionId: string): Promise<Task[]> {
  try {
    const res = await fetch(`${TASKS_URL}/${sessionId}`)
    if (!res.ok) return []
    const data = await res.json()
    return data.tasks
  } catch {
    return []
  }
}

export async function getTaskDetail(taskId: string): Promise<Task | null> {
  try {
    const res = await fetch(`${TASKS_URL}/detail/${taskId}`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function createTask(goal: string, sessionId: string, runNow = true) {
  const res = await fetch(TASKS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ goal, session_id: sessionId, run_now: runNow }),
  })
  if (!res.ok) throw new Error('Failed to create task')
  return res.json()
}

// ── Cockpit (FASE 4) ──────────────────────────────────────────────────────────

export interface ActiveProject {
  goal: string
  domain: string
  stack: string[]
  files: string[]
  status: string
}

export interface ProjectStatus {
  session_id: string
  project: Partial<ActiveProject>
  recent_goals: string[]
  has_project: boolean
}

export interface WorkspaceFile {
  path: string
  size_bytes: number
  extension: string
}

export interface WorkspaceStatus {
  session_id: string
  workspace: string
  files: WorkspaceFile[]
  exists: boolean
  total_files: number
}

export interface RecentIntent {
  message: string
  response: string
  intent: {
    goal: string
    domain: string
    ambiguity_score: number
    subgoals: string[]
    constraints: string[]
  }
  created_at: string
}

export async function getProjectStatus(sessionId: string): Promise<ProjectStatus | null> {
  try {
    const res = await fetch(`/cockpit/project/${sessionId}`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function getWorkspaceFiles(sessionId: string): Promise<WorkspaceStatus | null> {
  try {
    const res = await fetch(`/cockpit/workspace/${sessionId}`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function getRecentIntents(sessionId: string, limit = 8): Promise<RecentIntent[]> {
  try {
    const res = await fetch(`/cockpit/recent-intents/${sessionId}?limit=${limit}`)
    if (!res.ok) return []
    const data = await res.json()
    return data.intents ?? []
  } catch {
    return []
  }
}

