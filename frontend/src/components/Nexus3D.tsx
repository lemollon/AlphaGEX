'use client'

import { useRef, useMemo, useState, useEffect, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import {
  OrbitControls,
  Sphere,
  Float,
  Stars,
  Text,
  MeshDistortMaterial,
  Line
} from '@react-three/drei'
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
// CORE SPHERE WITH DISTORT MATERIAL
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

      {/* Main core sphere with distort effect */}
      <Sphere ref={meshRef} args={[1, 64, 64]}>
        <MeshDistortMaterial
          color="#3b82f6"
          emissive="#60a5fa"
          emissiveIntensity={1.2}
          roughness={0.2}
          metalness={0.8}
          distort={0.15}
          speed={2}
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

      {/* Core label - using default font */}
      <Text
        position={[0, 0, 1.2]}
        fontSize={0.25}
        color="#ffffff"
        anchorX="center"
        anchorY="middle"
      >
        GEX CORE
      </Text>
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
          emissiveIntensity={hovered ? 1.5 : 0.8}
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

      {/* Label */}
      <Text
        position={[0, 0.9, 0]}
        fontSize={0.18}
        color="#ffffff"
        anchorX="center"
        anchorY="middle"
      >
        {name}
      </Text>

      {/* Status indicator */}
      <Text
        position={[0, -0.75, 0]}
        fontSize={0.1}
        color={color}
        anchorX="center"
        anchorY="middle"
      >
        {status.toUpperCase()}
      </Text>
    </group>
  )
}

// =============================================================================
// MINI FEATURE NODE
// =============================================================================

function FeatureNode({
  id,
  name,
  angle,
  radius,
  y
}: {
  id: string
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
            emissive="#60a5fa"
            emissiveIntensity={1.0}
            roughness={0.4}
            metalness={0.6}
          />
        </Sphere>

        {/* Tiny label */}
        <Text
          position={[0, 0.35, 0]}
          fontSize={0.08}
          color="#93c5fd"
          anchorX="center"
          anchorY="middle"
        >
          {name}
        </Text>
      </group>
    </Float>
  )
}

// =============================================================================
// NEURAL CONNECTIONS
// =============================================================================

function NeuralConnection({
  start,
  end,
  color = '#3b82f6'
}: {
  start: [number, number, number]
  end: [number, number, number]
  color?: string
}) {
  const points = useMemo(() => {
    const curve = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(...start),
      new THREE.Vector3(
        (start[0] + end[0]) / 2,
        (start[1] + end[1]) / 2 + 1,
        (start[2] + end[2]) / 2
      ),
      new THREE.Vector3(...end)
    )
    return curve.getPoints(50).map(p => [p.x, p.y, p.z] as [number, number, number])
  }, [start, end])

  return (
    <Line
      points={points}
      color={color}
      lineWidth={1.5}
      transparent
      opacity={0.5}
    />
  )
}

// =============================================================================
// PARTICLE FLOW
// =============================================================================

function ParticleFlow() {
  const count = 200
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
// SIGNAL PARTICLES (flowing between nodes)
// =============================================================================

function SignalParticles() {
  const count = 50
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const signals = useMemo(() => {
    return BOT_NODES.flatMap((node, nodeIdx) =>
      Array.from({ length: 10 }, () => ({
        nodeIdx,
        progress: Math.random(),
        speed: 0.3 + Math.random() * 0.4,
        toCore: Math.random() > 0.5,
      }))
    )
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    signals.forEach((s, i) => {
      const node = BOT_NODES[s.nodeIdx]
      const radius = 4
      const nodeX = Math.cos(node.angle) * radius
      const nodeZ = Math.sin(node.angle) * radius
      const nodeY = Math.sin(node.angle * 2) * 0.5

      s.progress = (s.progress + state.clock.getDelta() * s.speed) % 1

      const p = s.toCore ? s.progress : 1 - s.progress
      const x = nodeX * (1 - p)
      const z = nodeZ * (1 - p)
      const y = nodeY * (1 - p) + Math.sin(p * Math.PI) * 0.5

      dummy.position.set(x, y, z)
      const scale = 0.04 * Math.sin(p * Math.PI)
      dummy.scale.setScalar(Math.max(0.01, scale))
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
      <meshBasicMaterial color="#ffffff" transparent opacity={0.9} />
    </instancedMesh>
  )
}

// =============================================================================
// OUTER NEURAL WEB
// =============================================================================

function NeuralWeb() {
  const groupRef = useRef<THREE.Group>(null)
  const webCount = 60

  const { webNodes, connections } = useMemo(() => {
    const nodes = Array.from({ length: webCount }, (_, i) => {
      const phi = Math.acos(-1 + (2 * i) / webCount)
      const theta = Math.sqrt(webCount * Math.PI) * phi
      const radius = 7 + Math.random() * 2
      return {
        x: radius * Math.sin(phi) * Math.cos(theta),
        y: radius * Math.sin(phi) * Math.sin(theta),
        z: radius * Math.cos(phi),
      }
    })

    // Create connections between nearby nodes
    const conns: Array<{ from: number; to: number }> = []
    nodes.forEach((node, i) => {
      nodes.forEach((other, j) => {
        if (i < j) {
          const dist = Math.sqrt(
            Math.pow(node.x - other.x, 2) +
            Math.pow(node.y - other.y, 2) +
            Math.pow(node.z - other.z, 2)
          )
          if (dist < 4 && conns.filter(c => c.from === i).length < 3) {
            conns.push({ from: i, to: j })
          }
        }
      })
    })

    return { webNodes: nodes, connections: conns }
  }, [])

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.02
      groupRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.1) * 0.05
    }
  })

  return (
    <group ref={groupRef}>
      {/* Web nodes */}
      {webNodes.map((node, i) => (
        <Sphere key={i} args={[0.06, 8, 8]} position={[node.x, node.y, node.z]}>
          <meshBasicMaterial color="#3b82f6" transparent opacity={0.6} />
        </Sphere>
      ))}

      {/* Connections */}
      {connections.map((conn, i) => {
        const from = webNodes[conn.from]
        const to = webNodes[conn.to]
        return (
          <Line
            key={i}
            points={[[from.x, from.y, from.z], [to.x, to.y, to.z]]}
            color="#1e40af"
            lineWidth={0.5}
            transparent
            opacity={0.3}
          />
        )
      })}
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
      <ambientLight intensity={0.3} />
      <pointLight position={[10, 10, 10]} intensity={1} color="#ffffff" />
      <pointLight position={[-10, -10, -10]} intensity={0.5} color="#3b82f6" />
      <pointLight position={[0, 0, 0]} intensity={2} color="#60a5fa" />

      {/* Background stars */}
      <Stars radius={50} depth={50} count={3000} factor={4} saturation={0} fade speed={0.5} />

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
          id={node.id}
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
            start={[0, 0, 0]}
            end={[x, y, z]}
            color={STATUS_COLORS[botStatus[node.id as keyof BotStatus] as keyof typeof STATUS_COLORS] || '#3b82f6'}
          />
        )
      })}

      {/* Particle effects */}
      <ParticleFlow />
      <SignalParticles />

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

function ErrorFallback({ message }: { message?: string }) {
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
        {message && (
          <p className="text-xs text-gray-500 font-mono bg-gray-800/50 p-2 rounded max-w-md mx-auto">
            {message}
          </p>
        )}
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
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Check for WebGL support
    try {
      const canvas = document.createElement('canvas')
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl')
      if (!gl) {
        setError('WebGL is not supported on this device')
        return
      }
    } catch (e) {
      setError('Failed to initialize WebGL')
      return
    }

    setMounted(true)
  }, [])

  if (error) {
    return <ErrorFallback message={error} />
  }

  if (!mounted) {
    return <LoadingFallback />
  }

  return (
    <div className={`w-full h-full bg-[#030712] ${className}`}>
      <Canvas
        camera={{ position: [0, 3, 12], fov: 60 }}
        gl={{
          antialias: true,
          alpha: false,
          powerPreference: 'high-performance',
          failIfMajorPerformanceCaveat: false
        }}
        dpr={[1, 2]}
        onCreated={({ gl }) => {
          gl.setClearColor('#030712')
        }}
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
