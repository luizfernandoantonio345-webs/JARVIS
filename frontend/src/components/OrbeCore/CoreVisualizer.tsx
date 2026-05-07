import { useEffect, useMemo, useRef, useState, type ElementRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { MeshDistortMaterial, Sphere, Float } from '@react-three/drei'
import * as THREE from 'three'
import './CoreVisualizer.css'

function useAudioFrequency(): number {
  const [frequency, setFrequency] = useState(0);
  // Stub - integrate with useVoice audioRef later
  return frequency;
}

interface CoreVisualizerProps {
  isListening?: boolean
  isThinking ?: boolean
}

interface JarvisOrbProps {
  isListening: boolean
  isThinking: boolean
  frequency: number
}

type DistortMaterial = ElementRef<typeof MeshDistortMaterial>

const STATE_COLORS = {
  idle: '#00ffff',
  listening: '#ff3333',
  thinking: '#ffd700',
}

function JarvisOrb({ isListening, isThinking, frequency }: JarvisOrbProps) {
  const orbRef = useRef<THREE.Mesh>(null)
  const materialRef = useRef<DistortMaterial & { speed: number }>(null)
  const targetColor = useMemo(() => new THREE.Color(STATE_COLORS.idle), [])

  useEffect(() => {
    targetColor.set(
      isThinking
        ? STATE_COLORS.thinking
        : isListening
          ? STATE_COLORS.listening
          : STATE_COLORS.idle,
    )
  }, [isListening, isThinking, targetColor])

  useFrame((state) => {
    const t = state.clock.getElapsedTime()
    const orb = orbRef.current
    const material = materialRef.current
    if (!orb || !material) return

    const pulse = frequency / 150 + (isListening ? Math.sin(t * 12) * 0.06 : 0)
    const thinkingPulse = isThinking ? Math.sin(t * 7) * 0.08 : 0
    const baseScale = 1.2 + pulse * 0.2 + thinkingPulse

    orb.rotation.y = t * 0.12
    orb.rotation.x = Math.sin(t * 0.35) * 0.08
    orb.scale.setScalar(baseScale)

    material.color.lerp(targetColor, 0.08)
    material.distort = THREE.MathUtils.lerp(material.distort, isThinking ? 0.62 : isListening ? 0.42 : 0.28 + pulse, 0.08)
    material.speed = isThinking ? 4 : isListening ? 2.3 : 1.35 + pulse * 2
    material.emissive.copy(material.color).multiplyScalar(isThinking ? 0.35 : isListening ? 0.22 : 0.16)
  })

  return (
    <Sphere ref={orbRef} args={[1, 96, 96]}>
      <MeshDistortMaterial
        ref={materialRef}
        color={STATE_COLORS.idle}
        emissive={STATE_COLORS.idle}
        emissiveIntensity={0.18}
        envMapIntensity={0.5}
        clearcoat={0.5}
        clearcoatRoughness={0}
        metalness={0.9}
        roughness={0.1}
        distort={0.28}
        speed={isThinking ? 4 : isListening ? 2.3 : 1.35}
      />
    </Sphere>
  )
}

export function CoreVisualizer({ isListening = false, isThinking = false }: CoreVisualizerProps) {
  const frequency = useAudioFrequency()
  const status = isThinking ? 'PROCESSANDO' : isListening ? 'OUVINDO' : 'IDLE'
  const statusTone = isThinking ? 'thinking' : isListening ? 'listening' : 'idle'

  return (
    <section className="core-visualizer" aria-label="JARVIS Core visualizer">
      <Canvas camera={{ position: [0, 0, 3.3], fov: 48 }} dpr={[1, 2]}>
        <color attach="background" args={['#000005']} />
        <ambientLight intensity={0.24} />
        <pointLight position={[5, 5, 6]} intensity={1.2} color="#ffffff" />
        <pointLight position={[-5, -4, -5]} intensity={0.6} color="#00ffff" />
        <pointLight position={[0, -3, 3]} intensity={isThinking ? 1 : 0.55} color={isThinking ? '#ffd700' : '#00ffff'} />
        <JarvisOrb isListening={isListening} isThinking={isThinking} frequency={frequency} />
      </Canvas>

      <div className={`core-status core-status--${statusTone}`}>
        <span className="core-status__label">JARVIS</span>
        <span className="core-status__value">{status}</span>
      </div>
    </section>
  )
}
