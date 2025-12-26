'use client'

import { useRef, useMemo, useState, useEffect, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Sphere, Float, Stars, Html } from '@react-three/drei'
import * as THREE from 'three'

// =============================================================================
// TYPES
// =============================================================================

export interface BotStatus {
  ares?: 'active' | 'idle' | 'trading' | 'error'
  athena?: 'active' | 'idle' | 'trading' | 'error'
  phoenix?: 'active' | 'idle' | 'trading' | 'error'
  atlas?: 'active' | 'idle' | 'trading' | 'error'
  oracle?: 'active' | 'idle' | 'trading' | 'error'
  gex?: 'active' | 'idle' | 'trading' | 'error'
}

interface Nexus3DProps {
  botStatus?: BotStatus
  onNodeClick?: (nodeId: string) => void
  className?: string
}

// =============================================================================
// CONSTANTS
// =============================================================================

const STATUS_COLORS = {
  active: '#10b981',
  idle: '#6b7280',
  trading: '#f59e0b',
  error: '#ef4444',
}

const BOT_NODES = [
  { id: 'oracle', name: 'ORACLE', angle: 0, description: 'ML Predictions' },
  { id: 'ares', name: 'ARES', angle: Math.PI * 2 / 5, description: 'Iron Condor' },
  { id: 'athena', name: 'ATHENA', angle: Math.PI * 4 / 5, description: 'Spreads' },
  { id: 'atlas', name: 'ATLAS', angle: Math.PI * 6 / 5, description: 'Wheel' },
  { id: 'phoenix', name: 'PHOENIX', angle: Math.PI * 8 / 5, description: '0DTE' },
]

const FEATURE_NODES = [
  { id: 'gex-analysis', name: 'GEX', angle: Math.PI * 0.3, radius: 5, y: 1.5 },
  { id: 'vix', name: 'VIX', angle: Math.PI * 0.7, radius: 5.5, y: -1 },
  { id: 'gamma', name: 'GAMMA', angle: Math.PI * 1.1, radius: 4.5, y: 2 },
  { id: 'signals', name: 'SIGNALS', angle: Math.PI * 1.5, radius: 5, y: -1.5 },
  { id: 'risk', name: 'RISK', angle: Math.PI * 1.9, radius: 5.2, y: 0.5 },
  { id: 'ml', name: 'ML', angle: Math.PI * 0.1, radius: 4.8, y: -0.8 },
  { id: 'data', name: 'DATA', angle: Math.PI * 0.5, radius: 5.3, y: 1.2 },
  { id: 'flow', name: 'FLOW', angle: Math.PI * 1.3, radius: 4.6, y: -1.8 },
]

// =============================================================================
// CORE SPHERE - Simplified without MeshDistortMaterial
// =============================================================================

function CoreSphere() {
  const meshRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)
  const ringRef = useRef<THREE.Mesh>(null)
  const ring2Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (meshRef.current) {
      meshRef.current.rotation.y = t * 0.1
      meshRef.current.rotation.z = Math.sin(t * 0.5) * 0.1
    }
    if (glowRef.current) {
      glowRef.current.scale.setScalar(1 + Math.sin(t * 2) * 0.05)
    }
    if (ringRef.current) {
      ringRef.current.rotation.z = t * 0.3
      ringRef.current.rotation.x = Math.PI / 2 + Math.sin(t * 0.5) * 0.1
    }
    if (ring2Ref.current) {
      ring2Ref.current.rotation.z = -t * 0.2
      ring2Ref.current.rotation.y = t * 0.15
    }
  })

  return (
    <group>
      {/* Outer glow */}
      <Sphere ref={glowRef} args={[1.8, 32, 32]}>
        <meshBasicMaterial color="#3b82f6" transparent opacity={0.08} />
      </Sphere>

      {/* Middle glow */}
      <Sphere args={[1.4, 32, 32]}>
        <meshBasicMaterial color="#60a5fa" transparent opacity={0.15} />
      </Sphere>

      {/* Main core sphere - using standard material instead of distort */}
      <Sphere ref={meshRef} args={[1, 64, 64]}>
        <meshStandardMaterial
          color="#3b82f6"
          emissive="#1e40af"
          emissiveIntensity={0.5}
          roughness={0.2}
          metalness={0.8}
        />
      </Sphere>

      {/* Inner bright core */}
      <Sphere args={[0.5, 32, 32]}>
        <meshBasicMaterial color="#93c5fd" transparent opacity={0.9} />
      </Sphere>

      {/* Rotating ring 1 */}
      <mesh ref={ringRef}>
        <torusGeometry args={[1.3, 0.02, 16, 100]} />
        <meshBasicMaterial color="#60a5fa" transparent opacity={0.8} />
      </mesh>

      {/* Rotating ring 2 */}
      <mesh ref={ring2Ref}>
        <torusGeometry args={[1.5, 0.015, 16, 100]} />
        <meshBasicMaterial color="#93c5fd" transparent opacity={0.6} />
      </mesh>

      {/* Core label using Html instead of Text */}
      <Html position={[0, 0, 1.5]} center>
        <div className="text-white text-xs font-bold whitespace-nowrap bg-black/50 px-2 py-1 rounded">
          GEX CORE
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// BOT NODE
// =============================================================================

function BotNode({
  id,
  name,
  angle,
  status = 'idle',
  onClick
}: {
  id: string
  name: string
  angle: number
  status?: string
  onClick?: () => void
}) {
  const meshRef = useRef<THREE.Mesh>(null)
  const [hovered, setHovered] = useState(false)

  const radius = 4
  const x = Math.cos(angle) * radius
  const z = Math.sin(angle) * radius
  const y = Math.sin(angle * 2) * 0.5

  const color = STATUS_COLORS[status as keyof typeof STATUS_COLORS] || STATUS_COLORS.idle

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (meshRef.current) {
      meshRef.current.position.y = y + Math.sin(t * 1.5 + angle) * 0.15
      meshRef.current.rotation.y = t * 0.5
    }
  })

  return (
    <group position={[x, y, z]}>
      {/* Glow */}
      <Sphere args={[0.7, 16, 16]}>
        <meshBasicMaterial color={color} transparent opacity={hovered ? 0.3 : 0.15} />
      </Sphere>

      {/* Main sphere */}
      <Sphere
        ref={meshRef}
        args={[0.45, 32, 32]}
        onClick={onClick}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={hovered ? 0.8 : 0.4}
          roughness={0.3}
          metalness={0.7}
        />
      </Sphere>

      {/* Status ring for trading */}
      {status === 'trading' && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.6, 0.02, 16, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.8} />
        </mesh>
      )}

      {/* Labels using Html instead of Text */}
      <Html position={[0, 0.9, 0]} center>
        <div className="text-white text-[10px] font-bold whitespace-nowrap">{name}</div>
      </Html>
      <Html position={[0, -0.75, 0]} center>
        <div className="text-[8px] font-medium whitespace-nowrap" style={{ color }}>
          {status.toUpperCase()}
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// MINI FEATURE NODE
// =============================================================================

function FeatureNode({
  name,
  angle,
  radius,
  y
}: {
  name: string
  angle: number
  radius: number
  y: number
}) {
  const meshRef = useRef<THREE.Mesh>(null)

  const x = Math.cos(angle) * radius
  const z = Math.sin(angle) * radius

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (meshRef.current) {
      meshRef.current.position.y = y + Math.sin(t * 2 + angle * 3) * 0.1
    }
  })

  return (
    <Float speed={2} rotationIntensity={0.5} floatIntensity={0.5}>
      <group position={[x, y, z]}>
        {/* Mini glow */}
        <Sphere args={[0.25, 12, 12]}>
          <meshBasicMaterial color="#60a5fa" transparent opacity={0.2} />
        </Sphere>

        {/* Mini sphere */}
        <Sphere ref={meshRef} args={[0.15, 16, 16]}>
          <meshStandardMaterial
            color="#93c5fd"
            emissive="#3b82f6"
            emissiveIntensity={0.5}
            roughness={0.4}
            metalness={0.6}
          />
        </Sphere>

        {/* Tiny label */}
        <Html position={[0, 0.35, 0]} center>
          <div className="text-blue-300 text-[8px] font-medium whitespace-nowrap">{name}</div>
        </Html>
      </group>
    </Float>
  )
}

// =============================================================================
// NEURAL CONNECTIONS - Using simple lines
// =============================================================================

function NeuralConnection({
  start,
  end,
  color = '#3b82f6'
}: {
  start: THREE.Vector3
  end: THREE.Vector3
  color?: string
}) {
  const lineRef = useRef<THREE.Line>(null)

  const geometry = useMemo(() => {
    const mid = new THREE.Vector3(
      (start.x + end.x) / 2,
      (start.y + end.y) / 2 + 1,
      (start.z + end.z) / 2
    )
    const curve = new THREE.QuadraticBezierCurve3(start, mid, end)
    const points = curve.getPoints(30)
    return new THREE.BufferGeometry().setFromPoints(points)
  }, [start, end])

  useFrame((state) => {
    if (lineRef.current) {
      const material = lineRef.current.material as THREE.LineBasicMaterial
      material.opacity = 0.3 + Math.sin(state.clock.elapsedTime * 2) * 0.1
    }
  })

  return (
    <primitive object={new THREE.Line(geometry, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.4 }))} />
  )
}

// =============================================================================
// PARTICLE FLOW
// =============================================================================

function ParticleFlow() {
  const count = 150
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      angle: Math.random() * Math.PI * 2,
      radius: 1.5 + Math.random() * 5,
      speed: 0.2 + Math.random() * 0.5,
      offset: Math.random() * Math.PI * 2,
      y: (Math.random() - 0.5) * 4,
      ySpeed: (Math.random() - 0.5) * 0.5,
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    particles.forEach((p, i) => {
      const angle = p.angle + t * p.speed
      const x = Math.cos(angle) * p.radius
      const z = Math.sin(angle) * p.radius
      const y = p.y + Math.sin(t * p.ySpeed + p.offset) * 0.5

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(0.02 + Math.sin(t * 2 + p.offset) * 0.01)
      dummy.updateMatrix()
      meshRef.current?.setMatrixAt(i, dummy.matrix)
    })
    if (meshRef.current) {
      meshRef.current.instanceMatrix.needsUpdate = true
    }
  })

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial color="#60a5fa" transparent opacity={0.8} />
    </instancedMesh>
  )
}

// =============================================================================
// OUTER NEURAL WEB - Simplified
// =============================================================================

function NeuralWeb() {
  const groupRef = useRef<THREE.Group>(null)
  const webCount = 40

  const webNodes = useMemo(() => {
    return Array.from({ length: webCount }, (_, i) => {
      const phi = Math.acos(-1 + (2 * i) / webCount)
      const theta = Math.sqrt(webCount * Math.PI) * phi
      const radius = 7 + Math.random() * 2
      return {
        x: radius * Math.sin(phi) * Math.cos(theta),
        y: radius * Math.sin(phi) * Math.sin(theta),
        z: radius * Math.cos(phi),
      }
    })
  }, [])

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.02
      groupRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.1) * 0.05
    }
  })

  return (
    <group ref={groupRef}>
      {webNodes.map((node, i) => (
        <Sphere key={i} args={[0.06, 8, 8]} position={[node.x, node.y, node.z]}>
          <meshBasicMaterial color="#3b82f6" transparent opacity={0.6} />
        </Sphere>
      ))}
    </group>
  )
}

// =============================================================================
// MAIN SCENE
// =============================================================================

function Scene({ botStatus, onNodeClick }: { botStatus: BotStatus, onNodeClick?: (id: string) => void }) {
  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.4} />
      <pointLight position={[10, 10, 10]} intensity={1} color="#ffffff" />
      <pointLight position={[-10, -10, -10]} intensity={0.5} color="#3b82f6" />
      <pointLight position={[0, 0, 0]} intensity={2} color="#60a5fa" />

      {/* Background stars */}
      <Stars radius={50} depth={50} count={2000} factor={4} saturation={0} fade speed={0.5} />

      {/* Core */}
      <CoreSphere />

      {/* Bot nodes */}
      {BOT_NODES.map((node) => (
        <BotNode
          key={node.id}
          id={node.id}
          name={node.name}
          angle={node.angle}
          status={botStatus[node.id as keyof BotStatus] || 'idle'}
          onClick={() => onNodeClick?.(node.id)}
        />
      ))}

      {/* Feature nodes */}
      {FEATURE_NODES.map((node) => (
        <FeatureNode
          key={node.id}
          name={node.name}
          angle={node.angle}
          radius={node.radius}
          y={node.y}
        />
      ))}

      {/* Neural connections from core to bots */}
      {BOT_NODES.map((node) => {
        const radius = 4
        const x = Math.cos(node.angle) * radius
        const z = Math.sin(node.angle) * radius
        const y = Math.sin(node.angle * 2) * 0.5
        return (
          <NeuralConnection
            key={node.id}
            start={new THREE.Vector3(0, 0, 0)}
            end={new THREE.Vector3(x, y, z)}
            color={STATUS_COLORS[botStatus[node.id as keyof BotStatus] as keyof typeof STATUS_COLORS] || '#3b82f6'}
          />
        )
      })}

      {/* Particle effects */}
      <ParticleFlow />

      {/* Outer neural web */}
      <NeuralWeb />

      {/* Camera controls */}
      <OrbitControls
        enablePan={false}
        enableZoom={true}
        minDistance={5}
        maxDistance={20}
        autoRotate
        autoRotateSpeed={0.5}
        maxPolarAngle={Math.PI * 0.85}
        minPolarAngle={Math.PI * 0.15}
      />
    </>
  )
}

// =============================================================================
// ERROR FALLBACK
// =============================================================================

function ErrorFallback() {
  return (
    <div className="w-full h-full bg-[#030712] flex items-center justify-center">
      <div className="text-center p-8">
        <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-red-500/20 flex items-center justify-center">
          <svg className="w-10 h-10 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold text-white mb-2">3D Visualization Error</h2>
        <p className="text-gray-400 mb-4">WebGL may not be supported on this device</p>
      </div>
    </div>
  )
}

// =============================================================================
// LOADING FALLBACK
// =============================================================================

function LoadingFallback() {
  return (
    <div className="w-full h-full bg-[#030712] flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto mb-4" />
        <p className="text-blue-400">Loading NEXUS...</p>
      </div>
    </div>
  )
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function Nexus3D({
  botStatus = {},
  onNodeClick,
  className = ''
}: Nexus3DProps) {
  const [mounted, setMounted] = useState(false)
  const [hasError, setHasError] = useState(false)

  useEffect(() => {
    setMounted(true)

    // Check for WebGL support
    try {
      const canvas = document.createElement('canvas')
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl')
      if (!gl) {
        setHasError(true)
      }
    } catch {
      setHasError(true)
    }
  }, [])

  if (!mounted) {
    return <LoadingFallback />
  }

  if (hasError) {
    return <ErrorFallback />
  }

  return (
    <div className={`w-full h-full bg-[#030712] ${className}`}>
      <Canvas
        camera={{ position: [0, 3, 12], fov: 60 }}
        gl={{
          antialias: true,
          alpha: false,
          failIfMajorPerformanceCaveat: false,
          powerPreference: 'default'
        }}
        dpr={[1, 1.5]}
        onCreated={({ gl }) => {
          gl.setClearColor('#030712')
        }}
        onError={() => setHasError(true)}
      >
        <color attach="background" args={['#030712']} />
        <fog attach="fog" args={['#030712', 15, 35]} />

        <Suspense fallback={null}>
          <Scene botStatus={botStatus} onNodeClick={onNodeClick} />
        </Suspense>
      </Canvas>
    </div>
  )
}
