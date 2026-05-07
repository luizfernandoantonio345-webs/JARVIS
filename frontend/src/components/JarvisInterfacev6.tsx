import React, { useRef, useMemo, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Bloom, EffectComposer } from '@react-three/postprocessing';
import * as THREE from 'three';
import './JarvisInterfacev6.css';

// ---------------------------------------------------------
// 1. O NÚCLEO (A ORBE CENTRAL) - Shaders GLSL Customizados
// ---------------------------------------------------------
const OrbShader = {
  uniforms: {
    uTime: { value: 0 },
    uColorBase: { value: new THREE.Color('#00E5FF') }, // Ciano Stark
    uColorPlasma: { value: new THREE.Color('#0047AB') }, // Azul Cobalto Profundo
    uIntensity: { value: 1.0 }
  },
  vertexShader: `
    varying vec2 vUv;
    varying vec3 vNormal;
    void main() {
      vUv = uv;
      vNormal = normalize(normalMatrix * normal);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    varying vec2 vUv;
    varying vec3 vNormal;
    uniform float uTime;
    uniform vec3 uColorBase;
    uniform vec3 uColorPlasma;
    uniform float uIntensity;
    
    void main() {
      // Efeito de Plasma e Ruído
      float pulse = 0.5 + 0.5 * sin(uTime * 3.0);
      float rim = 1.0 - max(dot(vNormal, vec3(0.0, 0.0, 1.0)), 0.0);
      float glow = pow(rim, 4.0) * (1.0 + pulse * 0.4);
      
      // Mistura das cores com efeito de transparência
      vec3 finalColor = mix(uColorPlasma, uColorBase, glow);
      
      gl_FragColor = vec4(finalColor * uIntensity * glow, glow);
    }
  `
};

interface JarvisData {
  status?: string;
  message?: string;
  cpu_usage?: number;
  ts?: number;
  source?: string;
  audio_url?: string;
}

interface JarvisInterfaceProps {
  jarvisData: JarvisData;
  autonomyData: { pending: number; status: string };
  connState: 'connecting' | 'connected' | 'disconnected';
}

const AnimatedOrb = ({ isSpeaking }: { isSpeaking: boolean }) => {
  const meshRef = useRef<THREE.Mesh>(null!);
  const materialRef = useRef<THREE.ShaderMaterial>(null!);

  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    materialRef.current.uniforms.uTime.value = t;
    
    // Rotação sutil e contínua da orbe
    meshRef.current.rotation.y = t * 0.15;
    meshRef.current.rotation.z = t * 0.05;

    // A orbe reage dinamicamente quando o JARVIS está "falando"
    const scaleFactor = isSpeaking ? 1.05 + Math.sin(t * 15) * 0.03 : 1.0;
    meshRef.current.scale.lerp(new THREE.Vector3(scaleFactor, scaleFactor, scaleFactor), 0.1);
    materialRef.current.uniforms.uIntensity.value = 1.0 + (isSpeaking ? 0.3 : 0.0);
  });

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[1, 64, 64]} />
      <shaderMaterial
        ref={materialRef}
        args={[OrbShader]}
        transparent
        blending={THREE.AdditiveBlending}
      />
    </mesh>
  );
};

// ---------------------------------------------------------
// 2. OS WIDGETS (JANELAS HOLOGRÁFICAS FLUTUANTES) - Localizados em PT-BR
// ---------------------------------------------------------
interface HolographicWidgetProps {
  title: string;
  children: React.ReactNode;
  position: string; // Ex: 'top-left', 'bottom-right'
}

const HolographicWidget: React.FC<HolographicWidgetProps> = ({ title, children, position }) => {
  const posClasses = {
    'top-left': 'top-left',
    'top-right': 'top-right',
    'bottom-left': 'bottom-left',
    'bottom-right': 'bottom-right'
  }[position] || 'top-10 left-10';

  return (
    <div className={`jarvis-v6-widget ${posClasses}`}>
      <div className="jarvis-v6-widget-header">
        <span>{title}</span>
        <div className="jarvis-v6-widget-pulse" />
      </div>
      <div className="jarvis-v6-widget-content">
        {children}
      </div>
    </div>
  );
};

// ---------------------------------------------------------
// 3. O COMPONENTE PRINCIPAL (JARVIS UI v6)
// ---------------------------------------------------------
const JarvisInterfacev6: React.FC<JarvisInterfaceProps> = ({ jarvisData, autonomyData, connState }) => {
  const isSpeaking = jarvisData.status === 'speaking';
  const cpu = jarvisData.cpu_usage?.toFixed(0) ?? '--';
  const statusLabel = jarvisData.status?.toUpperCase() ?? 'IDLE';
  const lastInput = jarvisData.message ?? 'Aguardando comando...';

  return (
    <div className="relative w-full h-screen bg-black overflow-hidden select-none">
      {/* CENA 3D (O NÚCLEO) - Fundo Preto Absoluto */}
      <div className="absolute inset-0 z-0">
        <Canvas camera={{ position: [0, 0, 3] }}>
          <color attach="background" args={['#000000']} />
          <AnimatedOrb isSpeaking={isSpeaking} />
          {/* Efeito de Bloom (Glow) crucial para o visual Stark */}
          <EffectComposer>
            <Bloom intensity={1.8} luminanceThreshold={0.05} radius={0.4} />
          </EffectComposer>
        </Canvas>
      </div>

      {/* RÓTULO CENTRAL DO NÚCLEO */}
      <div className="jarvis-v6-central-label absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
        <h1 className="jarvis-v6-title">JARVIS</h1>
        <p className="jarvis-v6-subtitle">LUIZ (CHEFE)</p>
      </div>

      {/* WIDGET SUPERIOR ESQUERDO (Relatório do Sistema) */}
      <HolographicWidget title="PROTOCOLO DE SESSÃO" position="top-left">
        <div className="flex flex-col gap-1 text-gray-300">
          <p><span className="status-cyan">Status do Sistema:</span> <span className={isSpeaking ? 'status-green' : 'status-cyan'}>ATIVO</span></p>
          <p><span className="status-cyan">Versão:</span> v6.0</p>
          <p><span className="status-cyan">Conexão:</span> <span className={connState === 'connected' ? 'status-green' : connState === 'connecting' ? 'status-yellow' : 'status-red'}>{connState.toUpperCase()}</span></p>
          <p className="border-t border-cyan-500/10 pt-1 mt-1 text-[10px]">CPU: <span className="status-yellow">{cpu}%</span> | Autonomia Pendente: {autonomyData.pending}</p>
        </div>
      </HolographicWidget>

      {/* WIDGET SUPERIOR DIREITO (Código Dinâmico) */}
      <HolographicWidget title="ARQUIVO DE CÓDIGO: NÚCLEO NEURAL" position="top-right">
        <pre>{`# Exemplo de Geração Dinâmica de Código
def otimizar_caminho_neural(fluxo_dados):
    # Analisa fluxo de dados e otimiza a latência
    return fluxo_dados.processar().filtrar(
        regra_stark='prioridade_voz_v6'
    )`}</pre>
      </HolographicWidget>

      {/* WIDGET INFERIOR ESQUERDO (Cibersegurança) */}
      <HolographicWidget title="PROTOCOLO DE SEGURANÇA: AUDITORIA X" position="bottom-left">
        <div className="text-gray-300">
          <p><span className="status-red">VULNERABILIDADE DETECTADA:</span> Entrada não sanitizada encontrada em endpoint: \`api/v1/debug\` (Line: 14)</p>
          <p className="status-yellow">Risco: Médio</p>
          <button className="jarvis-v6-widget-btn">Aplicar Correção Automática</button>
        </div>
      </HolographicWidget>

      {/* WIDGET INFERIOR DIREITO (Entrada/Saída de Dados) */}
      <HolographicWidget title="ARQUIVO DE MEMÓRIA & VOZ" position="bottom-right">
        <div className="flex flex-col gap-1.5 text-gray-300">
          <p><span className="status-cyan">Entrada Atual (Chefe):</span> <span className="italic">"{lastInput}"</span></p>
          <p><span className="status-cyan">Ação do JARVIS:</span> {statusLabel}</p>
          <p><span className="status-cyan">Estado de Fala:</span> {isSpeaking ? <span className="status-green animate-pulse">Falando</span> : 'Inativo'}</p>
        </div>
      </HolographicWidget>

      {/* CONNECTION STATUS DOT (from original App) */}
      <div
        style={{
          position: 'fixed', top: 14, left: 14,
          width: 8, height: 8, borderRadius: '50%',
          background: connState === 'connected' ? '#00ff88' : connState === 'connecting' ? '#ffd700' : '#ff4444',
          boxShadow: connState === 'connected' ? '0 0 8px #00ff88' : connState === 'connecting' ? '0 0 8px #ffd700' : '0 0 8px #ff4444',
          transition: 'all 0.3s',
        }}
        title={connState === 'connected' ? 'JARVIS Conectado' : connState === 'connecting' ? 'Conectando...' : 'Desconectado'}
      />
    </div>
  );
};

export default JarvisInterfacev6;

