import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useJarvisSocket } from '../hooks/useJarvisSocket'
import { useVoice } from '../hooks/useVoice'
import { OrbStatus } from '../types/ws'
import './JarvisNeuralCore.css'

interface AnimationState {
  t: number
  al: number
  tal: number
  speaking: boolean
  wvis: boolean
  alertMode: boolean
}

const CODE_SNIPPETS = [
  `<span class="ln">16</span><span class="kw">import</span> jarvis.neural <span class="kw">as</span> nn
<span class="ln">17</span>
<span class="ln">18</span><span class="kw">def</span> <span class="fn">optimize_neural_path</span>(self, data_stream):
<span class="ln">19</span>    <span class="kw">return</span> data_stream.processed
<span class="ln">20</span>
<span class="ln">21</span><span class="kw">def</span> <span class="fn">optimize_procalpath</span>(self, data_stream):
<span class="ln">22</span>    data_stream.stream = deste.data_stream
<span class="ln">23</span>    <span class="kw">return</span> data_stream.procset(self)
<span class="ln">24</span>
<span class="ln">25</span><span class="kw">def</span> <span class="fn">data_me</span>(self, seam):
<span class="ln">26</span>    <span class="kw">return</span> data_stream.processed
<span class="ln">27</span>
<span class="ln">28</span><span class="kw">def</span> <span class="fn">morocsa</span>(self, seam):
<span class="ln">29</span>    <span class="kw">return</span> data_stream.prowked(data_stream)`,
  `<span class="ln">30</span>
<span class="ln">31</span><span class="cm"># Neural defense — Stark v10 —</span>
<span class="ln">32</span><span class="kw">class</span> <span class="fn">NeuralCore</span>:
<span class="ln">33</span>    version = <span class="st">"10.4-stark"</span>
<span class="ln">34</span>    <span class="kw">def</span> <span class="fn">__init__</span>(self):
<span class="ln">35</span>        self.active = <span class="kw">True</span>
<span class="ln">36</span>        self.mode = <span class="st">"stark_priority"</span>
<span class="ln">37</span>    <span class="kw">def</span> <span class="fn">intercept</span>(self, vector):
<span class="ln">38</span>        <span class="kw">return</span> self.neutralize(vector)
<span class="ln">39</span>    <span class="kw">def</span> <span class="fn">neutralize</span>(self, v):
<span class="ln">40</span>        <span class="kw">return</span> v.route(self.mode)`,
  `<span class="ln">41</span>
<span class="ln">42</span><span class="kw">async def</span> <span class="fn">listen_voice</span>():
<span class="ln">43</span>    audio = <span class="kw">await</span> capture_stream()
<span class="ln">44</span>    <span class="cm"># STT pipeline stark mark X</span>
<span class="ln">45</span>    text = stt.transcribe(audio)
<span class="ln">46</span>    response = <span class="kw">await</span> orq.process(
<span class="ln">47</span>        text, source=<span class="st">"voice_input"</span>,
<span class="ln">48</span>        mode=<span class="st">"stark_priority_v10"</span>
<span class="ln">49</span>    )
<span class="ln">50</span>    <span class="kw">return</span> tts.speak(response)`,
]

export default function JarvisNeuralCore() {
  const { data: jarvisData, connState, send } = useJarvisSocket()
  const [animState, setAnimState] = useState<AnimationState>({
    t: 0,
    al: 0,
    tal: 0,
    speaking: false,
    wvis: false,
    alertMode: false,
  })

  const canvasRefs = {
    stars: useRef<HTMLCanvasElement>(null),
    rings: useRef<HTMLCanvasElement>(null),
    orb: useRef<HTMLCanvasElement>(null),
    fx: useRef<HTMLCanvasElement>(null),
  }

  const stateRef = useRef({
    W: 0,
    H: 0,
    CX: 0,
    CY: 0,
    R: 0,
    lastT: performance.now(),
    cpuH: Array.from({ length: 80 }, () => 38 + Math.random() * 44),
    ramH: Array.from({ length: 80 }, () => 50 + Math.random() * 24),
    speakingTimer: null as ReturnType<typeof setTimeout> | null,
    codeIndex: 0,
    lastMetricsUpdate: 0,
  })

  const handleVoiceTranscript = useCallback((text: string) => {
    const cmd = text.trim().toLowerCase()
    runCommand(cmd)
  }, [])

  const { listening, alwaysOn, toggle: toggleListening, setAlwaysOn } = useVoice(handleVoiceTranscript)

  // Initialize
  useEffect(() => {
    const resize = () => {
      const W = window.innerWidth
      const H = window.innerHeight
      stateRef.current.W = W
      stateRef.current.H = H
      stateRef.current.CX = W / 2
      stateRef.current.CY = H / 2
      stateRef.current.R = Math.min(W, H) * 0.22

      Object.values(canvasRefs).forEach((ref) => {
        if (ref.current) {
          ref.current.width = W
          ref.current.height = H
        }
      })

      buildMap()
    }

    resize()
    window.addEventListener('resize', resize)

    // Initialize data streams
    buildStreams()

    // Rotate code snippets
    const codeInterval = setInterval(() => {
      stateRef.current.codeIndex = (stateRef.current.codeIndex + 1) % CODE_SNIPPETS.length
      const cEl = document.getElementById('codeEl')
      if (cEl) {
        cEl.style.opacity = '0'
        setTimeout(() => {
          if (cEl) {
            cEl.innerHTML = CODE_SNIPPETS[stateRef.current.codeIndex]
            cEl.style.opacity = '1'
            const clinf = document.getElementById('clinf')
            if (clinf) clinf.textContent = `SL#${17 + stateRef.current.codeIndex * 12} / 060`
          }
        }, 340)
      }
    }, 5000)

    // Set initial code
    const cEl = document.getElementById('codeEl')
    if (cEl) {
      cEl.innerHTML = CODE_SNIPPETS[0]
    }

    return () => {
      window.removeEventListener('resize', resize)
      clearInterval(codeInterval)
    }
  }, [])

  // Update metrics periodically
  useEffect(() => {
    const interval = setInterval(() => {
      const state = stateRef.current
      const c = Math.max(14, Math.min(95, state.cpuH[state.cpuH.length - 1] + (Math.random() - 0.45) * 15))
      const r = Math.max(40, Math.min(84, state.ramH[state.ramH.length - 1] + (Math.random() - 0.5) * 6))
      const n = Math.max(8, Math.min(78, Math.random() * 68))

      state.cpuH.push(c)
      state.cpuH.shift()
      state.ramH.push(r)
      state.ramH.shift()

      const cpuPercent = Math.round(c)
      const ramPercent = Math.round(r)
      const netPercent = Math.round(n)

      document.getElementById('cpuv')!.textContent = cpuPercent + '%'
      document.getElementById('ramv')!.textContent = ramPercent + '%'
      document.getElementById('netv')!.textContent = netPercent + '%'
      document.getElementById('cpuv2')!.textContent = cpuPercent + '%'
      document.getElementById('ramv2')!.textContent = ramPercent + '%'
      document.getElementById('cpubar')!.style.width = cpuPercent + '%'
      document.getElementById('rambar')!.style.width = ramPercent + '%'
      document.getElementById('netbar')!.style.width = netPercent + '%'

      updateCharts()
    }, 1600)

    return () => clearInterval(interval)
  }, [])

  // Handle backend status changes
  useEffect(() => {
    const isSpeaking = jarvisData.status === OrbStatus.speaking || jarvisData.status === OrbStatus.thinking
    if (isSpeaking && !animState.speaking) {
      setSpeaking(true, 3000)
    } else if (!isSpeaking && animState.speaking && jarvisData.status === OrbStatus.idle) {
      setSpeaking(false)
    }
  }, [jarvisData.status, animState.speaking])

  const setSpeaking = (speaking: boolean, duration?: number) => {
    setAnimState((prev) => ({ ...prev, speaking }))

    const sb = document.getElementById('sbar')
    const sl = document.getElementById('stlive')
    const bc = document.getElementById('botctr')
    const bls = document.getElementById('blstat')
    const lr = document.getElementById('lring')

    if (speaking) {
      sb?.classList.add('on')
      lr?.classList.add('on')
      if (sl) sl.textContent = 'STATUS: ONLINE (SPEAKING)'
      if (bc) bc.textContent = 'STATUS: SPEAKING'
      if (bls) bls.textContent = 'STATUS: SPEAKING'

      if (stateRef.current.speakingTimer) {
        clearTimeout(stateRef.current.speakingTimer)
      }
      if (duration) {
        stateRef.current.speakingTimer = setTimeout(() => setSpeaking(false), duration)
      }
    } else {
      sb?.classList.remove('on')
      lr?.classList.remove('on')
      if (sl) sl.textContent = 'STATUS: STANDBY'
      if (bc) bc.textContent = 'STANDBY'
      if (bls) bls.textContent = 'STATUS: ONLINE'
    }
  }

  const showWidget = (i: number) => {
    const el = document.getElementById(`w${i}`)
    const rail = document.getElementById(`r${i}`)
    if (el) el.classList.add('show')
    if (rail) rail.classList.add('show')
    setAnimState((prev) => ({ ...prev, wvis: true }))
  }

  const closeWidget = (i: number) => {
    const el = document.getElementById(`w${i}`)
    const rail = document.getElementById(`r${i}`)
    if (el) el.classList.remove('show')
    if (rail) rail.classList.remove('show')

    const anyVisible = [0, 1, 2, 3].some((idx) => {
      const w = document.getElementById(`w${idx}`)
      return w?.classList.contains('show')
    })
    if (!anyVisible) {
      setAnimState((prev) => ({ ...prev, wvis: false }))
    }
  }

  const showAll = () => {
    setAnimState((prev) => ({ ...prev, wvis: true }))
    ;[0, 1, 2, 3].forEach((i, idx) => setTimeout(() => showWidget(i), idx * 115))
  }

  const hideAll = () => {
    ;[0, 1, 2, 3].forEach((i) => closeWidget(i))
  }

  const setAlert = (on: boolean) => {
    setAnimState((prev) => ({ ...prev, alertMode: on }))
    document.body.classList.toggle('alert', on)
    if (on) {
      const sl = document.getElementById('stlive')
      if (sl) sl.textContent = '⚠ ALERT: THREAT DETECTED'
      setSpeaking(true)
    }
  }

  const runCommand = (cmd: string) => {
    const commands: Record<string, () => void> = {
      'mostrar codigo': () => {
        showWidget(0)
        setSpeaking(true, 3000)
      },
      'show code': () => {
        showWidget(0)
        setSpeaking(true, 3000)
      },
      'mostrar mapa': () => {
        showWidget(1)
        setSpeaking(true, 2500)
      },
      'show map': () => {
        showWidget(1)
        setSpeaking(true, 2500)
      },
      'mostrar dados': () => {
        showWidget(2)
        setSpeaking(true, 2500)
      },
      'show data': () => {
        showWidget(2)
        setSpeaking(true, 2500)
      },
      'mostrar protocolos': () => {
        showWidget(3)
        setSpeaking(true, 2500)
      },
      'show protocols': () => {
        showWidget(3)
        setSpeaking(true, 2500)
      },
      'mostrar tudo': () => {
        showAll()
        setSpeaking(true, 4000)
      },
      'show all': () => {
        showAll()
        setSpeaking(true, 4000)
      },
      'fechar': () => {
        hideAll()
        setSpeaking(false)
      },
      'hide': () => {
        hideAll()
        setSpeaking(false)
      },
      'alerta': () => setAlert(true),
      'alert': () => setAlert(true),
      'normal': () => setAlert(false),
      'analise': () => {
        showAll()
        setSpeaking(true, 5000)
      },
      'analyze': () => {
        showAll()
        setSpeaking(true, 5000)
      },
    }

    let ran = false
    for (const key in commands) {
      if (cmd.includes(key)) {
        commands[key]()
        ran = true
        break
      }
    }

    if (!ran && cmd.length > 2) {
      send(cmd)
      showAll()
      setSpeaking(true, 3500)
    }
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement).id === 'cmdtext') return

    if (e.key === ' ') {
      e.preventDefault()
      const cmdinput = document.getElementById('cmdinput')
      const cmdtext = document.getElementById('cmdtext') as HTMLInputElement
      cmdinput?.classList.toggle('show')
      if (cmdinput?.classList.contains('show')) {
        cmdtext?.focus()
      }
      return
    }

    if (e.key === 'Escape') {
      const cmdinput = document.getElementById('cmdinput')
      cmdinput?.classList.remove('show')
      hideAll()
      setSpeaking(false)
      return
    }

    if (e.key === 'a' || e.key === 'A') {
      setAlert(!animState.alertMode)
      return
    }

    if (e.key >= '1' && e.key <= '4') {
      const i = parseInt(e.key) - 1
      const el = document.getElementById(`w${i}`)
      if (el?.classList.contains('show')) {
        closeWidget(i)
      } else {
        showWidget(i)
        setSpeaking(true, 2500)
      }
      return
    }

    if (e.key === '0') {
      hideAll()
      setSpeaking(false)
    }
  }

  const handleCmdSubmit = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const value = (e.target as HTMLInputElement).value
      runCommand(value)
      const cmdinput = document.getElementById('cmdinput')
      cmdinput?.classList.remove('show')
    }
    if (e.key === 'Escape') {
      const cmdinput = document.getElementById('cmdinput')
      cmdinput?.classList.remove('show')
    }
  }

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [animState.alertMode])

  const updateCharts = () => {
    const state = stateRef.current
    drawChart('cc', state.cpuH, 'rgba(0,229,255,0.72)', 'rgba(0,229,255,0.062)')
    drawChart('rc', state.ramH, 'rgba(255,200,80,0.65)', 'rgba(255,200,80,0.05)')
  }

  // Main animation loop
  useEffect(() => {
    let animId: number
    let lastTime = performance.now()

    const loop = (now: number) => {
      const dt = Math.min((now - lastTime) / 1000, 0.05)
      lastTime = now

      setAnimState((prev) => {
        const newT = prev.t + dt
        return { ...prev, t: newT }
      })

      animId = requestAnimationFrame(loop)
    }

    animId = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(animId)
  }, [])

  return (
    <div id="scene">
      {/* CANVAS STACK */}
      <canvas ref={canvasRefs.stars} id="c-stars"></canvas>
      <canvas ref={canvasRefs.rings} id="c-rings"></canvas>
      <canvas ref={canvasRefs.orb} id="c-orb"></canvas>
      <canvas ref={canvasRefs.fx} id="c-fx"></canvas>

      <div id="hexgrid"></div>
      <div id="vig"></div>
      <div id="scan"></div>
      <div id="chrab"></div>

      {/* CORNERS */}
      <div className="corner" id="co-tl">
        <svg width="85" height="85" viewBox="0 0 85 85">
          <path d="M2 52 L2 2 L52 2" fill="none" stroke="rgba(0,229,255,0.16)" strokeWidth="0.8" />
          <path d="M2 2 L20 2" fill="none" stroke="rgba(0,229,255,0.65)" strokeWidth="1.8" />
          <path d="M2 2 L2 20" fill="none" stroke="rgba(0,229,255,0.65)" strokeWidth="1.8" />
          <circle cx="2" cy="2" r="2.8" fill="rgba(0,229,255,0.7)" />
          <line x1="9" y1="2" x2="9" y2="7" stroke="rgba(0,229,255,0.22)" strokeWidth="0.5" />
          <line x1="16" y1="2" x2="16" y2="9" stroke="rgba(0,229,255,0.16)" strokeWidth="0.5" />
          <line x1="24" y1="2" x2="24" y2="6" stroke="rgba(0,229,255,0.1)" strokeWidth="0.5" />
        </svg>
      </div>
      <div className="corner" id="co-tr">
        <svg width="85" height="85" viewBox="0 0 85 85">
          <path d="M2 52 L2 2 L52 2" fill="none" stroke="rgba(0,229,255,0.16)" strokeWidth="0.8" />
          <path d="M2 2 L20 2" fill="none" stroke="rgba(0,229,255,0.65)" strokeWidth="1.8" />
          <path d="M2 2 L2 20" fill="none" stroke="rgba(0,229,255,0.65)" strokeWidth="1.8" />
          <circle cx="2" cy="2" r="2.8" fill="rgba(0,229,255,0.7)" />
        </svg>
      </div>
      <div className="corner" id="co-bl">
        <svg width="85" height="85" viewBox="0 0 85 85">
          <path d="M2 52 L2 2 L52 2" fill="none" stroke="rgba(0,229,255,0.16)" strokeWidth="0.8" />
          <path d="M2 2 L20 2" fill="none" stroke="rgba(0,229,255,0.65)" strokeWidth="1.8" />
          <path d="M2 2 L2 20" fill="none" stroke="rgba(0,229,255,0.65)" strokeWidth="1.8" />
          <circle cx="2" cy="2" r="2.8" fill="rgba(0,229,255,0.7)" />
        </svg>
      </div>
      <div className="corner" id="co-br">
        <svg width="85" height="85" viewBox="0 0 85 85">
          <path d="M2 52 L2 2 L52 2" fill="none" stroke="rgba(0,229,255,0.16)" strokeWidth="0.8" />
          <path d="M2 2 L20 2" fill="none" stroke="rgba(0,229,255,0.65)" strokeWidth="1.8" />
          <path d="M2 2 L2 20" fill="none" stroke="rgba(0,229,255,0.65)" strokeWidth="1.8" />
          <circle cx="2" cy="2" r="2.8" fill="rgba(0,229,255,0.7)" />
        </svg>
      </div>

      <div className="dstream" id="ds-l"></div>
      <div className="dstream" id="ds-r"></div>

      <div id="lring"></div>

      {/* CENTER LABEL */}
      <div id="lbl">
        <div id="jt">JARVIS</div>
        <div id="sbar">
          <div className="sb"></div>
          <div className="sb"></div>
          <div className="sb"></div>
          <div className="sb"></div>
          <div className="sb"></div>
          <div className="sb"></div>
          <div className="sb"></div>
          <div className="sb"></div>
          <div className="sb"></div>
        </div>
      </div>

      {/* WIDGETS */}
      <div className="w ltl" id="w0">
        <div className="wh">
          <span className="wt">CODE ARCHIVE: CORE SYSTEM v6.0</span>
          <div className="wc">
            <button className="wbtn" onClick={() => closeWidget(0)}>
              ▲
            </button>
            <button className="wbtn" onClick={() => closeWidget(0)}>
              ✕
            </button>
            <div className="wdot"></div>
          </div>
        </div>
        <div className="wb">
          <pre className="code" id="codeEl"></pre>
          <div className="cfoot">
            <span id="clinf">SL#17 / 060</span>
            <span>▲ ▼</span>
          </div>
        </div>
      </div>

      <div className="w ltr" id="w1">
        <div className="wh">
          <span className="wt">INTELLIGENCE REPORT: GLOBAL ANOMALIES</span>
          <div className="wc">
            <button className="wbtn" onClick={() => closeWidget(1)}>
              ▲
            </button>
            <button className="wbtn" onClick={() => closeWidget(1)}>
              ✕
            </button>
            <div className="wdot"></div>
          </div>
        </div>
        <div className="wb">
          <div className="mwrap" id="mapwrap">
            <div className="mgline" style={{ top: '33%', left: 0, right: 0, height: '1px' }}></div>
            <div className="mgline" style={{ top: '66%', left: 0, right: 0, height: '1px' }}></div>
            <div className="mgline" style={{ left: '25%', top: 0, bottom: 0, width: '1px' }}></div>
            <div className="mgline" style={{ left: '50%', top: 0, bottom: 0, width: '1px' }}></div>
            <div className="mgline" style={{ left: '75%', top: 0, bottom: 0, width: '1px' }}></div>
          </div>
          <div className="anom">
            <span className="adot"></span>Unusual seismic activity — Sector 4
          </div>
          <div className="anom">Data pattern correlation high — historical events</div>
          <div className="anom">Anomalous signal — origin: UNCLASSIFIED</div>
          <div className="anom">Neural intercept: 3 new vectors identified</div>
        </div>
      </div>

      <div className="w lbl" id="w2">
        <div className="wh">
          <span className="wt">DATA FLOW ANALYSIS</span>
          <div className="wc">
            <button className="wbtn" onClick={() => closeWidget(2)}>
              ▲
            </button>
            <button className="wbtn" onClick={() => closeWidget(2)}>
              ✕
            </button>
            <div className="wdot"></div>
          </div>
        </div>
        <div className="wb">
          <div className="mrow">
            <span className="mrlabel">CPU</span>
            <div className="mrbar">
              <div className="mrfill cpu" id="cpubar" style={{ width: '74%' }}></div>
            </div>
            <span className="mrval" id="cpuv">
              74%
            </span>
          </div>
          <div className="mrow">
            <span className="mrlabel">RAM</span>
            <div className="mrbar">
              <div className="mrfill ram" id="rambar" style={{ width: '61%' }}></div>
            </div>
            <span className="mrval" id="ramv">
              61%
            </span>
          </div>
          <div className="mrow">
            <span className="mrlabel">NET</span>
            <div className="mrbar">
              <div className="mrfill net" id="netbar" style={{ width: '32%' }}></div>
            </div>
            <span className="mrval" id="netv">
              32%
            </span>
          </div>
          <div className="chlbl" style={{ marginTop: '5px' }}>
            CPU: <span id="cpuv2">74%</span>
          </div>
          <canvas className="mc" id="cc" height="36"></canvas>
          <div className="chlbl">RAM: <span id="ramv2">61%</span></div>
          <canvas className="mc" id="rc" height="36"></canvas>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '5.5px', color: 'rgba(0,229,255,0.12)', borderTop: '1px solid rgba(0,229,255,0.04)', paddingTop: '4px', letterSpacing: '1px' }}>
            <span>CPU STATUS</span>
            <span id="blstat">STATUS: ONLINE</span>
            <span>SAFE STATUS</span>
          </div>
        </div>
      </div>

      <div className="w lbr" id="w3">
        <div className="wh">
          <span className="wt">ACTIVE PROTOCOLS</span>
          <div className="wc">
            <button className="wbtn" onClick={() => closeWidget(3)}>
              ▲
            </button>
            <button className="wbtn" onClick={() => closeWidget(3)}>
              ✕
            </button>
            <div className="wdot"></div>
          </div>
        </div>
        <div className="wb">
          <div className="pi">
            <span>Sentinel Node monitoring</span>
            <span className="pbadge run">RUN</span>
          </div>
          <div className="pi">
            <span>Project Insight simulation</span>
            <span className="pbadge run">RUN</span>
          </div>
          <div className="pi">
            <span>Neural Defense v3 sweep</span>
            <span className="pbadge run">RUN</span>
          </div>
          <div className="pi">
            <span>Sentinel Node monitoring</span>
            <span className="pbadge stn">STN</span>
          </div>
          <div className="pi">
            <span>Perimeter scan — alpha</span>
            <span className="pbadge wrn">WRN</span>
          </div>
          <div className="pi">
            <span>Project Insight simulation</span>
            <span className="pbadge run">RUN</span>
          </div>
          <div className="pfooter">
            <span>▲ ▼</span>
            <span>SYSTEM MONITORING</span>
            <span>◉</span>
          </div>
        </div>
      </div>

      {/* RAILS */}
      <div className="rail" id="r0">
        <div className="rico">●</div>
        <div className="rico">▲</div>
        <div className="rico">◈</div>
      </div>
      <div className="rail" id="r1">
        <div className="rico">●</div>
        <div className="rico">▲</div>
        <div className="rico">◈</div>
      </div>
      <div className="rail" id="r2">
        <div className="rico">◈</div>
        <div className="rico">●</div>
        <div className="rico">■</div>
      </div>
      <div className="rail" id="r3">
        <div className="rico">▲</div>
        <div className="rico">◉</div>
        <div className="rico">▼</div>
      </div>

      {/* STATUS BAR */}
      <div id="stbar">
        <span className="seg">SYSTEM: JARVIS MARK X</span>
        <span className="seg" id="stlive">
          STATUS: STANDBY
        </span>
        <span className="seg">SAFE MODE: ACTIVE</span>
      </div>

      {/* BOTTOM ROW */}
      <div id="botrow">
        <span>CPU STATUS</span>
        <span id="botctr">STANDBY</span>
        <span>SAFE STATUS</span>
      </div>

      {/* COMMAND INPUT */}
      <div id="cmdinput">
        <span id="cmdprompt">JARVIS ›</span>
        <input
          id="cmdtext"
          type="text"
          autoComplete="off"
          spellCheck={false}
          placeholder="ENTER COMMAND..."
          onKeyDown={handleCmdSubmit}
        />
        <div id="cmdcursor"></div>
      </div>

      {/* HINT */}
      <div id="hint">[ SPACE — COMMAND · 1-4 — TOGGLE PANELS · ESC — CLEAR ]</div>

      {/* SPARKLE */}
      <div id="spark">
        <svg className="spksvg" width="16" height="16" viewBox="0 0 20 20">
          <defs>
            <filter id="sf">
              <feGaussianBlur stdDeviation="1.4" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <path
            d="M10 0L11.9 8.1L20 10L11.9 11.9L10 20L8.1 11.9L0 10L8.1 8.1Z"
            fill="rgba(255,255,255,0.52)"
            filter="url(#sf)"
          />
        </svg>
      </div>
    </div>
  )
}

// ── HELPER FUNCTIONS ──
function buildMap() {
  const w = document.getElementById('mapwrap')
  if (!w) return
  w.querySelectorAll('.mdot').forEach((d) => d.remove())
  const dots = [
    { t: '17%', l: '12%', dl: '0s' },
    { t: '31%', l: '49%', dl: '.5s' },
    { t: '59%', l: '67%', dl: '1s' },
    { t: '19%', l: '79%', dl: '.3s' },
    { t: '63%', l: '27%', dl: '.8s' },
    { t: '41%', l: '91%', dl: '1.35s' },
  ]
  dots.forEach((d) => {
    const el = document.createElement('div')
    el.className = 'mdot'
    el.style.top = d.t
    el.style.left = d.l
    el.style.animationDelay = d.dl
    w.appendChild(el)
  })
}

const DSC = '01アイウエオカキABCDEFX¥§∑∂√∞≠≈ΩΨΦ'

function buildStreams() {
  ;['ds-l', 'ds-r'].forEach((id) => {
    const el = document.getElementById(id)
    if (!el) return
    el.innerHTML = ''
    const H = window.innerHeight
    const rows = Math.floor(H / 11) + 5
    for (let i = 0; i < rows; i++) {
      const d = document.createElement('div')
      d.className = 'dsc'
      d.textContent = DSC[Math.floor(Math.random() * DSC.length)]
      d.style.animationDuration = 2 + Math.random() * 4.5 + 's'
      d.style.animationDelay = Math.random() * 5 + 's'
      el.appendChild(d)
    }
  })

  // Update stream characters periodically
  setInterval(() => {
    document.querySelectorAll('.dsc').forEach((el) => {
      if (Math.random() < 0.11) {
        el.textContent = DSC[Math.floor(Math.random() * DSC.length)]
      }
    })
  }, 750)
}

function drawChart(id: string, data: number[], color: string, fill: string) {
  const mc = document.getElementById(id) as HTMLCanvasElement
  if (!mc) return
  const mw = mc.offsetWidth || 220
  mc.width = mw
  mc.height = 36
  const mctx = mc.getContext('2d')
  if (!mctx) return
  const h = mc.height

  mctx.clearRect(0, 0, mw, h)
  const pad = 20
  mctx.strokeStyle = 'rgba(0,229,255,0.04)'
  mctx.lineWidth = 0.5
  ;[25, 50, 75, 100].forEach((p) => {
    const y = h - (p / 100) * h * 0.93
    mctx.beginPath()
    mctx.moveTo(pad, y)
    mctx.lineTo(mw, y)
    mctx.stroke()
  })

  mctx.fillStyle = 'rgba(0,229,255,0.18)'
  mctx.font = '5px Courier New'
  ;['100%', '50%', '0%'].forEach((l, i) => {
    mctx.fillText(l, 0, i === 0 ? 8 : i === 1 ? h * 0.53 : h - 1)
  })

  const bw = (mw - pad) / data.length
  data.forEach((v, i) => {
    const bh = (v / 100) * (h * 0.92)
    mctx.fillStyle = fill
    mctx.fillRect(pad + i * bw, h - bh, Math.max(1, bw - 0.8), bh)
  })

  mctx.beginPath()
  data.forEach((v, i) => {
    const x = pad + i * bw + bw / 2
    const y = h - (v / 100) * (h * 0.92)
    i === 0 ? mctx.moveTo(x, y) : mctx.lineTo(x, y)
  })
  mctx.strokeStyle = color
  mctx.lineWidth = 1.1
  mctx.stroke()
}
