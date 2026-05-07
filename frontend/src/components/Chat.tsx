import { useState, useRef, useEffect, useCallback } from 'react'
import { streamMessage, clearSession, type StreamEvent } from '../services/api'
import { useVoice, speak } from '../hooks/useVoice'
import './Chat.css'

interface PlanStep {
  action: string
  input?: string
  description?: string
}

interface Message {
  role: 'user' | 'jarvis'
  text: string
  /** Plan steps shown in "thinking mode" above the response */
  plan?: PlanStep[]
  /** Task ID if this response was produced by the autonomy layer */
  taskId?: string | null
  /** True while the message is still being streamed */
  streaming?: boolean
  /** Domain badge e.g. "web_dev", "api" — parsed from done event */
  domain?: string | null
}

interface ChatProps {
  onSessionChange?: (sessionId: string) => void
  onNewMessage?: () => void
  onCoreStateChange?: (state: { listening: boolean; thinking: boolean }) => void
}

const COMMANDS = [
  { label: '🔍 Analyze', prefix: '/analyze ' },
  { label: '🏗 Arch', prefix: '/arch ' },
  { label: '▶ Run', prefix: '/run ' },
  { label: '🐙 GitHub', prefix: 'analyze github repo ' },
  { label: '🖥 System', prefix: 'system monitor' },
  { label: '🌐 Search', prefix: 'web_search ' },
]

function generateSessionId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

export default function Chat({ onSessionChange, onNewMessage, onCoreStateChange }: ChatProps = {}) {
  const [sessionId, setSessionId] = useState(() => {
    const id = generateSessionId()
    return id
  })
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'jarvis',
      text: 'Hello. I am JARVIS — your autonomous AI assistant.\n\nCapabilities:\n• /analyze [code] — deep code review\n• /arch [description] — system architecture\n• /run [python] — execute code\n• analyze github repo owner/repo — analyze any public repo\n• system monitor — live system metrics\n• Just describe a goal → I will plan and execute it autonomously',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [voiceOut, setVoiceOut] = useState(false)
  const [streamingEnabled, setStreamingEnabled] = useState(true)
  const [autoSend, setAutoSend] = useState(false)
  const autoSendTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const handleTranscript = useCallback((text: string) => {
    setInput(prev => (prev ? `${prev} ${text}` : text))

    // FASE 5: auto-send with 2-second cancel window
    if (autoSend) {
      if (autoSendTimerRef.current) clearTimeout(autoSendTimerRef.current)
      autoSendTimerRef.current = setTimeout(() => {
        setInput(current => {
          const trimmed = current.trim()
          if (trimmed) {
            // Simulate send by triggering via a flag + useEffect
            setInput(trimmed)
            // We call handleSend after state settles via the autoSendTrigger mechanism
          }
          return current
        })
        triggerAutoSend()
      }, 2000)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSend])

  const triggerAutoSend = useCallback(() => {
    // Fire handleSend via a deferred queue so input state is already set
    setTimeout(() => {
      setInput(prev => {
        if (prev.trim()) {
          handleSendRef.current()
        }
        return prev
      })
    }, 50)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSendRef = useRef<() => void>(() => {})

  const {
    listening,
    alwaysOn,
    supported: micSupported,
    toggle: toggleMic,
    setAlwaysOn,
  } = useVoice(handleTranscript)

  useEffect(() => {
    onCoreStateChange?.({ listening, thinking: loading })
  }, [listening, loading, onCoreStateChange])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleNewChat = useCallback(async () => {
    abortRef.current?.abort()
    await clearSession(sessionId)
    const newId = generateSessionId()
    setSessionId(newId)
    onSessionChange?.(newId)
    setMessages([{ role: 'jarvis', text: 'New session started. How can I help?' }])
    setInput('')
    setLoading(false)
  }, [sessionId, onSessionChange])

  // Report initial session ID on mount
  useEffect(() => {
    setSessionId(id => {
      onSessionChange?.(id)
      return id
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleStop() {
    abortRef.current?.abort()
    setLoading(false)
    setMessages(prev => {
      const last = prev[prev.length - 1]
      if (last?.streaming) {
        return [
          ...prev.slice(0, -1),
          { ...last, streaming: false, text: last.text + ' [stopped]' },
        ]
      }
      return prev
    })
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    setMessages(prev => [...prev, { role: 'user', text }])
    setInput('')
    setLoading(true)
    onNewMessage?.()

    if (streamingEnabled) {
      // ── Streaming path ────────────────────────────────────────────────────
      // Placeholder message to stream into
      setMessages(prev => [
        ...prev,
        { role: 'jarvis', text: '', streaming: true },
      ])

      let planSteps: PlanStep[] = []
      let taskId: string | null = null
      let buffer = ''

      const ctrl = streamMessage(
        text,
        sessionId,
        (event: StreamEvent) => {
          if (event.type === 'plan') {
            planSteps = event.steps ?? []
            taskId = event.task_id ?? null
            // Attach plan to the placeholder immediately
            setMessages(prev => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last?.streaming) {
                next[next.length - 1] = { ...last, plan: planSteps, taskId }
              }
              return next
            })
          } else if (event.type === 'token') {
            buffer += event.content ?? ''
            setMessages(prev => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last?.streaming) {
                next[next.length - 1] = { ...last, text: buffer }
              }
              return next
            })
          } else if (event.type === 'done') {
            // Parse domain from action field (e.g. "orchestrated_web_dev" → "web_dev")
            const rawAction: string = (event as unknown as Record<string, string>).action ?? ''
            let domainBadge: string | null = null
            if (rawAction.startsWith('orchestrated_')) domainBadge = rawAction.slice(13)
            else if (rawAction.startsWith('autodev_')) domainBadge = rawAction.slice(8)

            setMessages(prev => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last?.streaming) {
                next[next.length - 1] = {
                  ...last,
                  text: buffer,
                  streaming: false,
                  taskId: event.task_id ?? taskId,
                  domain: domainBadge,
                }
              }
              return next
            })
            speak(buffer, voiceOut)
            onNewMessage?.()
            setLoading(false)
          } else if (event.type === 'error') {
            setMessages(prev => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (last?.streaming) {
                next[next.length - 1] = {
                  ...last,
                  text: `❌ ${event.detail ?? 'Unknown error'}`,
                  streaming: false,
                }
              }
              return next
            })
            setLoading(false)
          }
        },
        () => setLoading(false),
        (err) => {
          setMessages(prev => [
            ...prev.slice(0, -1),
            { role: 'jarvis', text: `❌ ${err}` },
          ])
          setLoading(false)
        },
      )
      abortRef.current = ctrl
    } else {
      // ── Non-streaming fallback (uses /chat POST) ───────────────────────────
      try {
        const { sendMessage } = await import('../services/api')
        const response = await sendMessage(text, sessionId)
        setMessages(prev => [...prev, { role: 'jarvis', text: response }])
        speak(response, voiceOut)
        onNewMessage?.()
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Unknown error'
        setMessages(prev => [...prev, { role: 'jarvis', text: `❌ ${msg}` }])
      } finally {
        setLoading(false)
      }
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function applyCommand(prefix: string) {
    setInput(prev => (prev.startsWith(prefix) ? prev : prefix + prev))
    textareaRef.current?.focus()
  }

  // Wire handleSend into the ref so autoSend timer can call it
  useEffect(() => {
    handleSendRef.current = handleSend
  })

  return (
    <div className="chat-container">
      <header className="chat-header">
        <span className="dot" />
        JARVIS
        <div className="header-actions">
          <button
            className={`icon-btn ${streamingEnabled ? 'active' : ''}`}
            onClick={() => setStreamingEnabled(v => !v)}
            title={streamingEnabled ? 'Streaming: ON' : 'Streaming: OFF'}
          >
            ⚡
          </button>
          <button
            className={`icon-btn ${voiceOut ? 'active' : ''}`}
            onClick={() => setVoiceOut(v => !v)}
            title={voiceOut ? 'Voice: ON' : 'Voice: OFF'}
          >
            🔊
          </button>
          <button
            className={`icon-btn ${autoSend ? 'active' : ''}`}
            onClick={() => setAutoSend(v => !v)}
            title={autoSend ? 'Auto-send: ON (voice → auto submit)' : 'Auto-send: OFF'}
          >
            ✈
          </button>
          <button className="new-chat-btn" onClick={handleNewChat}>+ New</button>
        </div>
      </header>

      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <span className="label">{msg.role === 'user' ? 'You' : 'JARVIS'}</span>

            {/* Domain badge from orchestrator/autodev */}
            {msg.domain && (
              <span className="domain-badge">{msg.domain.replace('_', ' ')}</span>
            )}

            {/* Thinking mode: show plan steps */}
            {msg.plan && msg.plan.length > 0 && (
              <div className="thinking-block">
                <span className="thinking-title">⚙ Plan</span>
                {msg.plan.map((step, si) => (
                  <div key={si} className="thinking-step">
                    <span className="step-action">{step.action}</span>
                    <span className="step-desc">{step.description ?? step.input ?? ''}</span>
                  </div>
                ))}
              </div>
            )}

            <p className={msg.streaming ? 'streaming' : ''}>
              {msg.text}
              {msg.streaming && <span className="cursor" />}
            </p>

            {msg.taskId && (
              <span className="task-badge">Task: {msg.taskId.slice(0, 8)}</span>
            )}
          </div>
        ))}
        {/* Non-streaming fallback loading indicator */}
        {loading && !streamingEnabled && (
          <div className="message jarvis">
            <span className="label">JARVIS</span>
            <p className="typing">Processing…</p>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="chat-commands">
        {COMMANDS.map(cmd => (
          <button key={cmd.prefix} className="cmd-btn" onClick={() => applyCommand(cmd.prefix)}>
            {cmd.label}
          </button>
        ))}
      </div>

      <div className="chat-input">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message or goal… (Enter to send, Shift+Enter for newline)"
          rows={2}
          disabled={loading && !streamingEnabled}
        />
        <div className="input-actions">
          {micSupported && (
            <>
              <button
                className={`icon-btn mic-btn ${listening && !alwaysOn ? 'listening' : ''}`}
                onClick={toggleMic}
                title={listening ? 'Stop recording' : 'Speak (push to talk)'}
                disabled={alwaysOn}
              >
                🎤
              </button>
              <button
                className={`icon-btn always-on-btn ${alwaysOn ? 'always-on-active' : ''}`}
                onClick={() => setAlwaysOn(!alwaysOn)}
                title={alwaysOn ? 'Disable always-on listening' : 'Enable always-on listening'}
              >
                {alwaysOn ? '🔴' : '⏺'}
              </button>
            </>
          )}
          {loading && streamingEnabled ? (
            <button onClick={handleStop} className="stop-btn">■ Stop</button>
          ) : (
            <button onClick={handleSend} disabled={loading || !input.trim()} className="send-btn">
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
