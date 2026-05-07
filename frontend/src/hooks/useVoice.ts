import { useState, useCallback, useEffect, useRef } from 'react'

type OnTranscript = (text: string) => void

const DEBOUNCE_MS = 1500        // Cooldown between voice captures in push-to-talk
const ALWAYS_ON_RESTART_MS = 300 // Delay before restarting recognition in always-on mode

export function useVoice(onTranscript: OnTranscript) {
  const [listening, setListening] = useState(false)
  const [alwaysOn, setAlwaysOnState] = useState(false)
  const supported =
    typeof window !== 'undefined' &&
    ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)

  const recRef = useRef<SpeechRecognition | null>(null)
  const cooldownRef = useRef(false)
  const alwaysOnRef = useRef(false)
  const onTranscriptRef = useRef(onTranscript)

  // Keep callback ref fresh without restarting recognition
  useEffect(() => {
    onTranscriptRef.current = onTranscript
  }, [onTranscript])

  useEffect(() => {
    if (!supported) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SR = ((window as any).SpeechRecognition ??
      (window as any).webkitSpeechRecognition) as typeof SpeechRecognition

    const rec = new SR()
    rec.lang = 'pt-BR'
    rec.interimResults = false
    rec.continuous = false   // always-on auto-restarts on 'onend' instead
    rec.maxAlternatives = 1

    rec.onresult = (e: SpeechRecognitionEvent) => {
      if (cooldownRef.current) return
      // In continuous mode the browser fires multiple result events;
      // pick the last final result.
      let transcript = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) {
          transcript += e.results[i][0].transcript
        }
      }
      if (transcript.trim()) {
        cooldownRef.current = true
        onTranscriptRef.current(transcript.trim())
        setTimeout(() => { cooldownRef.current = false }, DEBOUNCE_MS)
      }
    }

    rec.onend = () => {
      // In always-on mode, restart automatically after a short pause
      if (alwaysOnRef.current) {
        setTimeout(() => {
          if (!alwaysOnRef.current) return
          try {
            recRef.current?.start()
          } catch {
            // Already started or no permission — ignore
          }
        }, ALWAYS_ON_RESTART_MS)
      } else {
        setListening(false)
      }
    }

    rec.onerror = (e: SpeechRecognitionErrorEvent) => {
      if (e.error === 'aborted') return   // user stopped manually — not a real error
      if (e.error !== 'no-speech') console.warn('Speech error:', e.error)
      if (!alwaysOnRef.current) setListening(false)
    }

    recRef.current = rec
  }, [supported])

  /** Push-to-talk: toggle listening on/off */
  const toggle = useCallback(() => {
    if (!recRef.current || cooldownRef.current || alwaysOnRef.current) return
    if (listening) {
      recRef.current.stop()
      setListening(false)
    } else {
      try {
        recRef.current.start()
        setListening(true)
      } catch {
        // Already started — ignore
      }
    }
  }, [listening])

  /** Always-on mode: microphone stays active continuously, auto-restarts */
  const setAlwaysOn = useCallback((enabled: boolean) => {
    alwaysOnRef.current = enabled
    setAlwaysOnState(enabled)
    if (enabled) {
      setListening(true)
      try {
        recRef.current?.start()
      } catch {
        // Already started
      }
    } else {
      setListening(false)
      try {
        recRef.current?.stop()
      } catch {
        // Already stopped
      }
    }
  }, [])

  return { listening, alwaysOn, supported, toggle, setAlwaysOn }
}

export function speak(text: string, enabled: boolean) {
  if (!enabled || !('speechSynthesis' in window)) return
  // Strip markdown for cleaner TTS
  const clean = text
    .replace(/```[\s\S]*?```/g, 'bloco de código')
    .replace(/[#*`_~]/g, '')
    .trim()
  if (!clean) return
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(clean)
  utter.lang = 'pt-BR'
  utter.rate = 1.05
  utter.pitch = 1.0
  window.speechSynthesis.speak(utter)
}

