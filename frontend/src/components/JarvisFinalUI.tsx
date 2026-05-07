import React, { useRef, useMemo, useState, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Bloom, EffectComposer, Noise, Vignette } from '@react-three/postprocessing';
import { Float, MeshDistortMaterial, Points, PointMaterial } from '@react-three/drei';
import * as THREE from 'three';
import { Cpu, ShieldAlert, Activity, Database, Terminal } from 'lucide-react';

// ---------------------------------------------------------
// 1. O NÚCLEO CINÉTICO (Anéis e Partículas)
// ---------------------------------------------------------
const KineticCore = ({ isSpeaking }: { isSpeaking: boolean }) => {
  const groupRef = useRef<THREE.Group>(null!);
  const particlesRef = useRef<THREE.Points>(null!);

  // Gerar partículas para o campo de dados ao redor
  const particles = useMemo(() => {
    const coords = new Float32Array(2000 * 3);
    for (let i = 0; i < 2000; i++) {
      const r = 1.5 + Math.random() * 0.5;
      const theta = Math.random() * 2 * Math.PI;
      const phi = Math.acos(2 * Math.random() - 1);
      coords.set([
        r * Math.sin(phi) * Math.cos(theta),
        r * Math.sin(phi) * Math.sin(theta),
        r * Math.cos(phi)
      ], i * 3);
    }
    return coords;
  }, []);

  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    groupRef.current.rotation.y = t * 0.2;
    groupRef.current.rotation.z = t * 0.1;
    
    if (particlesRef.current) {
      particlesRef.current.rotation.y = -t * 0.05;
    }

    // Reação de pulso à fala
    const s = isSpeaking ? 1 + Math.sin(t * 20) * 0.05 : 1;
    groupRef.current.scale.lerp(new THREE.Vector3(s, s, s), 0.1);
  });

  return (
    <group ref={groupRef}>
      {/* Esfera Central Distorcida (Plasma) */}
      <Float speed={5} rotationIntensity={2} floatIntensity={2}>
        <mesh>
          <sphereGeometry args={[0.7, 64, 64]} />
          <MeshDistortMaterial
            color="#00d2ff"
            speed={isSpeaking ? 5 : 2}
            distort={0.4}
            radius={1}
            emissive="#0047AB"
            emissiveIntensity={2}
            transparent
            opacity={0.6}
          />
        </mesh>
      </Float>

      {/* Anéis de Dados (Wireframes) */}
      {[1.1, 1.25, 1.4].map((radius, i) => (
        <mesh key={i} rotation={[Math.random(), Math.random(), 0]}>
          <torusGeometry args={[radius, 0.005, 16, 100]} />
          <meshBasicMaterial color="#00e5ff" transparent opacity={0.3} />
        </mesh>
      ))}

      {/* Nuvem de Partículas */}
      <points ref={particlesRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={particles.length / 3}
            array={particles}
            itemSize={3}
          />
        </bufferGeometry>
        <PointMaterial
          transparent
          color="#00e5ff"
          size={0.015}
          sizeAttenuation={true}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
};

// ---------------------------------------------------------
// 2. WIDGETS HOLOGRÁFICOS ESTILIZADOS
// ---------------------------------------------------------
const ModernWidget = ({ title, icon: Icon, children, position }: any) => {
  const posBase = "absolute p-4 border-l-2 border-cyan-500/50 bg-cyan-950/10 backdrop-blur-xl transition-all duration-500";
  const posClasses = {
    'top-left': `${posBase} top-10 left-10 rounded-r-lg`,
    'top-right': `${posBase} top-10 right-10 rounded-l-lg text-right border-l-0 border-r-2`,
    'bottom-left': `${posBase} bottom-10 left-10 rounded-r-lg`,
    'bottom-right': `${posBase} bottom-10 right-10 rounded-l-lg text-right border-l-0 border-r-2`
  }[position];

  return (
    <div className={posClasses} style={{ width: '320px' }}>
      <div className={`flex items-center gap-3 mb-3 ${position.includes('right') ? 'flex-row-reverse' : ''}`}>
        <div className="p-2 bg-cyan-500/20 rounded-full animate-pulse">
          <Icon size={16} className="text-cyan-400" />
        </div>
        <h2 className="text-[10px] font-black tracking-[0.3em] text-cyan-100 uppercase">{title}</h2>
      </div>
      <div className="font-mono text-[11px] text-cyan-400/80 leading-relaxed">
        {children}
      </div>
      {/* Detalhes de Interface (Linhas Decorativas) */}
      <div className="absolute -bottom-2 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" />
    </div>
  );
};

// ---------------------------------------------------------
// 3. COMPONENTE PRINCIPAL
// ---------------------------------------------------------
export default function JarvisFinalUI() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [cpuLoad, setCpuLoad] = useState(45);

  useEffect(() => {
    const interval = setInterval(() => setCpuLoad(Math.floor(Math.random() * 20) + 40), 3000);
    // Simular fala
    const speech = setInterval(() => setIsSpeaking(!isSpeaking), 5000);
    return () => { clearInterval(interval); clearInterval(speech); };
  }, [isSpeaking]);

  return (
    <div className="relative w-full h-screen bg-[#020202] text-white overflow-hidden">
      {/* Background Grid */}
      <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-10" />
      
      {/* 3D Core Rendering */}
      <Canvas camera={{ position: [0, 0, 4], fov: 45 }}>
        <color attach="background" args={['#020202']} />
        <ambientLight intensity={0.5} />
        <KineticCore isSpeaking={isSpeaking} />
        
        <EffectComposer>
          <Bloom luminanceThreshold={0.1} intensity={1.5} levels={9} mipmapBlur />
          <Noise opacity={0.05} />
          <Vignette eskil={false} offset={0.1} darkness={1.1} />
        </EffectComposer>
      </Canvas>

      {/* Central Identity */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center pointer-events-none">
        <div className="relative">
          <div className="absolute -inset-10 bg-cyan-500/10 blur-3xl rounded-full" />
          <h1 className="text-6xl font-black tracking-[0.4em] text-transparent bg-clip-text bg-gradient-to-b from-white via-cyan-300 to-cyan-600 drop-shadow-[0_0_20px_rgba(0,255,255,0.5)]">
            JARVIS
          </h1>
          <div className="h-[1px] w-full bg-cyan-500/50 my-2" />
          <p className="text-[10px] tracking-[0.8em] text-cyan-400 uppercase opacity-80">System v5.2 | Luiz (Chefe)</p>
        </div>
      </div>

      {/* Holographic HUD Overlay */}
      <ModernWidget title="Status do Núcleo" icon={Cpu} position="top-left">
        <div className="space-y-2">
          <div className="flex justify-between"><span>CPU LOAD</span><span className="text-white">{cpuLoad}%</span></div>
          <div className="w-full h-1 bg-cyan-950 rounded-full overflow-hidden">
            <div className="h-full bg-cyan-500 transition-all duration-1000" style={{ width: `${cpuLoad}%` }} />
          </div>
          <div className="text-[9px] opacity-50">TEMP: 42°C | UPTIME: 144:12:05</div>
        </div>
      </ModernWidget>

      <ModernWidget title="Relatório Geopolítico" icon={ShieldAlert} position="top-right">
        <div className="space-y-1">
          <p className="text-red-400">● ANOMALIA DETECTADA NO SETOR 7</p>
          <p>Sincronizando satélites com Projeto Insight...</p>
          <p className="text-green-400">Criptografia: Nível Stark Ativo</p>
        </div>
      </ModernWidget>

      <ModernWidget title="Análise de Fluxo" icon={Activity} position="bottom-left">
        <div className="h-16 flex items-end gap-1">
          {[40, 70, 45, 90, 65, 80, 30, 50].map((h, i) => (
            <div key={i} className="flex-1 bg-cyan-500/40 animate-pulse" style={{ height: `${h}%` }} />
          ))}
        </div>
        <p className="mt-2">Processando pacotes neurais...</p>
      </ModernWidget>

      <ModernWidget title="Protocolos Ativos" icon={Database} position="bottom-right">
        <ul className="list-none space-y-1 text-[10px]">
          <li>{'>'} SENTINEL NODE MONITORING</li>
          <li>{'>'} AUTO-REPAIR SEQUENCE</li>
          <li className="text-cyan-200 animate-pulse">{'>'} VOICE COMMAND RECOGNITION</li>
        </ul>
      </ModernWidget>

      {/* Bottom Bar Info */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-10 text-[9px] font-mono tracking-[0.2em] text-cyan-500/60 uppercase">
        <span>Gps: -23.5505, -46.6333</span>
        <span className="text-cyan-300">Safe Mode: Active</span>
        <span>Secure Line: 128-bit</span>
      </div>
    </div>
  );
}
