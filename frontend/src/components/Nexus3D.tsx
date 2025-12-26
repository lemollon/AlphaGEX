'use client'

import { useRef, useMemo, useState, useEffect, Suspense, Component, ReactNode } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import {
  OrbitControls,
  Sphere,
  Stars,
  Html,
  MeshDistortMaterial,
  Line
} from '@react-three/drei'
import * as THREE from 'three'

// =============================================================================
// ERROR BOUNDARY - Catches runtime errors in 3D components
// =============================================================================

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

class Canvas3DErrorBoundary extends Component<{ children: ReactNode, fallback: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode, fallback: ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Nexus3D Error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback
    }
    return this.props.children
  }
}

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
// COLOR PALETTE - Updated for reference image aesthetic
// =============================================================================

const COLORS = {
  coreCenter: '#0c1929',      // Dark blue center
  coreRim: '#22d3ee',         // Electric cyan rim
  fiberInner: '#38bdf8',      // Sky blue
  fiberOuter: '#1e40af',      // Deep blue
  particleBright: '#e0f2fe',  // Near white
  particleGlow: '#60a5fa',    // Light blue
  background: '#030712',      // Near black
  nebula1: '#1e3a8a',         // Deep blue nebula
  nebula2: '#312e81',         // Indigo nebula
}

const STATUS_COLORS = {
  active: '#10b981',
  idle: '#60a5fa',
  trading: '#f59e0b',
  error: '#ef4444',
}

const BOT_NODES = [
  { id: 'oracle', name: 'ORACLE', angle: 0 },
  { id: 'ares', name: 'ARES', angle: Math.PI * 2 / 5 },
  { id: 'athena', name: 'ATHENA', angle: Math.PI * 4 / 5 },
  { id: 'atlas', name: 'ATLAS', angle: Math.PI * 6 / 5 },
  { id: 'phoenix', name: 'PHOENIX', angle: Math.PI * 8 / 5 },
]

// =============================================================================
// BREATHING CORE - Pulsing central sphere with bright rim
// =============================================================================

function BreathingCore() {
  const groupRef = useRef<THREE.Group>(null)
  const rimRef = useRef<THREE.Mesh>(null)
  const innerRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const t = state.clock.elapsedTime
    // Breathing effect
    const breathe = 1 + Math.sin(t * 0.8) * 0.08

    if (groupRef.current) {
      groupRef.current.scale.setScalar(breathe)
    }
    if (rimRef.current) {
      // Pulsing rim glow
      const rimPulse = 0.15 + Math.sin(t * 2) * 0.05
      ;(rimRef.current.material as THREE.MeshBasicMaterial).opacity = rimPulse
    }
    if (innerRef.current) {
      innerRef.current.rotation.y = t * 0.1
    }
  })

  return (
    <group ref={groupRef}>
      {/* Outer rim glow - bright edge */}
      <Sphere ref={rimRef} args={[1.6, 64, 64]}>
        <meshBasicMaterial color={COLORS.coreRim} transparent opacity={0.15} />
      </Sphere>

      {/* Secondary glow layer */}
      <Sphere args={[1.4, 48, 48]}>
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.1} />
      </Sphere>

      {/* Main core with distort */}
      <Sphere ref={innerRef} args={[1, 64, 64]}>
        <MeshDistortMaterial
          color={COLORS.coreCenter}
          emissive={COLORS.coreRim}
          emissiveIntensity={2.5}
          roughness={0.1}
          metalness={0.9}
          distort={0.2}
          speed={3}
        />
      </Sphere>

      {/* Inner bright core */}
      <Sphere args={[0.4, 32, 32]}>
        <meshBasicMaterial color={COLORS.particleBright} transparent opacity={0.95} />
      </Sphere>

      {/* Rim rings */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.2, 0.015, 16, 100]} />
        <meshBasicMaterial color={COLORS.coreRim} transparent opacity={0.6} />
      </mesh>

      {/* Core label */}
      <Html position={[0, -2, 0]} center distanceFactor={8}>
        <div className="text-cyan-300 text-sm font-bold whitespace-nowrap bg-black/50 px-3 py-1 rounded-full select-none border border-cyan-500/30">
          GEX CORE
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// RADIAL FIBER - Single fiber with organic curve and particles
// =============================================================================

function RadialFiber({
  phi,
  theta,
  baseRadius,
  length,
  speed,
  particleCount = 3
}: {
  phi: number
  theta: number
  baseRadius: number
  length: number
  speed: number
  particleCount?: number
}) {
  const lineRef = useRef<THREE.Line>(null)
  const groupRef = useRef<THREE.Group>(null)

  // Calculate end point on sphere
  const endPoint = useMemo(() => {
    const r = baseRadius + length
    return new THREE.Vector3(
      r * Math.sin(phi) * Math.cos(theta),
      r * Math.sin(phi) * Math.sin(theta),
      r * Math.cos(phi)
    )
  }, [phi, theta, baseRadius, length])

  // Create curved fiber path with organic wobble
  const { points, curve } = useMemo(() => {
    const start = new THREE.Vector3(0, 0, 0)
    const mid = endPoint.clone().multiplyScalar(0.5)
    // Add some perpendicular offset for curve
    const perpOffset = new THREE.Vector3(
      Math.sin(theta + Math.PI/2) * 0.3,
      Math.cos(phi) * 0.3,
      Math.sin(phi) * 0.3
    )
    mid.add(perpOffset)

    const c = new THREE.QuadraticBezierCurve3(start, mid, endPoint)
    return {
      points: c.getPoints(30).map(p => [p.x, p.y, p.z] as [number, number, number]),
      curve: c
    }
  }, [endPoint, theta, phi])

  // Fiber sway animation
  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (groupRef.current) {
      // Gentle swaying motion
      groupRef.current.rotation.x = Math.sin(t * speed + phi) * 0.02
      groupRef.current.rotation.y = Math.cos(t * speed * 0.7 + theta) * 0.02
    }
  })

  // Color gradient based on distance
  const fiberOpacity = 0.3 + (length / 8) * 0.3

  return (
    <group ref={groupRef}>
      {/* Main fiber line */}
      <Line
        points={points}
        color={COLORS.fiberInner}
        lineWidth={1}
        transparent
        opacity={fiberOpacity}
      />

      {/* Particles along fiber */}
      {Array.from({ length: particleCount }).map((_, i) => (
        <FiberParticle
          key={i}
          curve={curve}
          offset={i / particleCount}
          speed={speed}
          phi={phi}
        />
      ))}
    </group>
  )
}

// =============================================================================
// FIBER PARTICLE - Glowing particle traveling along fiber
// =============================================================================

function FiberParticle({
  curve,
  offset,
  speed,
  phi
}: {
  curve: THREE.QuadraticBezierCurve3
  offset: number
  speed: number
  phi: number
}) {
  const meshRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const t = state.clock.elapsedTime
    // Outward traveling motion
    const progress = ((t * speed * 0.3 + offset + phi) % 1)
    const point = curve.getPoint(progress)

    if (meshRef.current) {
      meshRef.current.position.copy(point)
      // Sparkle effect
      const sparkle = 0.03 + Math.sin(t * 10 + offset * 20) * 0.015
      meshRef.current.scale.setScalar(sparkle)
    }
    if (glowRef.current) {
      glowRef.current.position.copy(point)
      glowRef.current.scale.setScalar(0.08 + Math.sin(t * 5 + offset * 10) * 0.02)
    }
  })

  return (
    <group>
      <mesh ref={glowRef}>
        <sphereGeometry args={[1, 8, 8]} />
        <meshBasicMaterial color={COLORS.particleGlow} transparent opacity={0.4} />
      </mesh>
      <mesh ref={meshRef}>
        <sphereGeometry args={[1, 8, 8]} />
        <meshBasicMaterial color={COLORS.particleBright} />
      </mesh>
    </group>
  )
}

// =============================================================================
// RADIAL FIBER BURST - 60 fibers in 3D sphere arrangement
// =============================================================================

function RadialFiberBurst() {
  const fibers = useMemo(() => {
    const result = []
    const fiberCount = 60

    // Distribute fibers using golden angle for even sphere coverage
    const goldenAngle = Math.PI * (3 - Math.sqrt(5))

    for (let i = 0; i < fiberCount; i++) {
      const y = 1 - (i / (fiberCount - 1)) * 2 // -1 to 1
      const radius = Math.sqrt(1 - y * y)
      const theta = goldenAngle * i

      const phi = Math.acos(y)

      // Vary fiber length for depth
      const length = 4 + Math.random() * 4
      const speed = 0.3 + Math.random() * 0.4
      const particleCount = 2 + Math.floor(Math.random() * 3)

      result.push({ phi, theta, length, speed, particleCount })
    }
    return result
  }, [])

  return (
    <group>
      {fibers.map((fiber, i) => (
        <RadialFiber
          key={i}
          phi={fiber.phi}
          theta={fiber.theta}
          baseRadius={1.5}
          length={fiber.length}
          speed={fiber.speed}
          particleCount={fiber.particleCount}
        />
      ))}
    </group>
  )
}

// =============================================================================
// OUTWARD PULSE WAVE - Energy ripple from center
// =============================================================================

function PulseWave() {
  const ringRef = useRef<THREE.Mesh>(null)
  const [scale, setScale] = useState(1)

  useFrame((state) => {
    const t = state.clock.elapsedTime
    // Pulse every 3 seconds
    const pulse = (t % 3) / 3
    const newScale = 1 + pulse * 8

    if (ringRef.current) {
      ringRef.current.scale.setScalar(newScale)
      ;(ringRef.current.material as THREE.MeshBasicMaterial).opacity = 0.4 * (1 - pulse)
    }
  })

  return (
    <mesh ref={ringRef} rotation={[Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.95, 1, 64]} />
      <meshBasicMaterial color={COLORS.coreRim} transparent opacity={0.4} side={THREE.DoubleSide} />
    </mesh>
  )
}

// =============================================================================
// SPARKLE FIELD - Random bright flashes
// =============================================================================

function SparkleField() {
  const count = 100
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const sparkles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      position: new THREE.Vector3(
        (Math.random() - 0.5) * 16,
        (Math.random() - 0.5) * 16,
        (Math.random() - 0.5) * 16
      ),
      phase: Math.random() * Math.PI * 2,
      speed: 2 + Math.random() * 4,
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    sparkles.forEach((s, i) => {
      dummy.position.copy(s.position)
      // Twinkle effect
      const twinkle = Math.max(0, Math.sin(t * s.speed + s.phase))
      const scale = twinkle * twinkle * 0.05
      dummy.scale.setScalar(scale)
      dummy.updateMatrix()
      meshRef.current?.setMatrixAt(i, dummy.matrix)
    })
    if (meshRef.current) {
      meshRef.current.instanceMatrix.needsUpdate = true
    }
  })

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial color={COLORS.particleBright} />
    </instancedMesh>
  )
}

// =============================================================================
// ENERGY ACCUMULATION - Particles rushing to center periodically
// =============================================================================

function EnergyAccumulation() {
  const count = 30
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const particles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => {
      const phi = Math.acos(-1 + (2 * i) / count)
      const theta = Math.sqrt(count * Math.PI) * phi
      return {
        startRadius: 6 + Math.random() * 2,
        phi,
        theta,
        phase: Math.random(),
      }
    })
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    // Accumulation cycle every 5 seconds
    const cycle = (t % 5) / 5

    particles.forEach((p, i) => {
      // Rush toward center then burst out
      let radius
      if (cycle < 0.7) {
        // Moving inward
        radius = p.startRadius * (1 - cycle / 0.7 * 0.9)
      } else {
        // Burst outward
        const burstProgress = (cycle - 0.7) / 0.3
        radius = p.startRadius * 0.1 + burstProgress * p.startRadius
      }

      const x = radius * Math.sin(p.phi) * Math.cos(p.theta)
      const y = radius * Math.sin(p.phi) * Math.sin(p.theta)
      const z = radius * Math.cos(p.phi)

      dummy.position.set(x, y, z)
      const scale = cycle < 0.7 ? 0.06 : 0.04
      dummy.scale.setScalar(scale)
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
      <meshBasicMaterial color={COLORS.coreRim} transparent opacity={0.8} />
    </instancedMesh>
  )
}

// =============================================================================
// NEBULA BACKDROP - Subtle colored clouds
// =============================================================================

function NebulaBackdrop() {
  const mesh1Ref = useRef<THREE.Mesh>(null)
  const mesh2Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (mesh1Ref.current) {
      mesh1Ref.current.rotation.z = t * 0.01
      mesh1Ref.current.rotation.y = t * 0.005
    }
    if (mesh2Ref.current) {
      mesh2Ref.current.rotation.z = -t * 0.008
      mesh2Ref.current.rotation.x = t * 0.006
    }
  })

  return (
    <group>
      <Sphere ref={mesh1Ref} args={[30, 32, 32]} position={[10, 5, -20]}>
        <meshBasicMaterial color={COLORS.nebula1} transparent opacity={0.03} />
      </Sphere>
      <Sphere ref={mesh2Ref} args={[25, 32, 32]} position={[-15, -8, -25]}>
        <meshBasicMaterial color={COLORS.nebula2} transparent opacity={0.025} />
      </Sphere>
    </group>
  )
}

// =============================================================================
// INTEGRATED BOT NODE - Blended into fiber aesthetic
// =============================================================================

function IntegratedBotNode({
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
  const groupRef = useRef<THREE.Group>(null)
  const [hovered, setHovered] = useState(false)

  const radius = 5
  const phi = Math.PI / 2 // On equator
  const x = Math.cos(angle) * radius
  const z = Math.sin(angle) * radius
  const y = 0

  const color = STATUS_COLORS[status as keyof typeof STATUS_COLORS] || COLORS.particleGlow

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (groupRef.current) {
      // Gentle floating
      groupRef.current.position.y = y + Math.sin(t * 1.2 + angle) * 0.2
    }
  })

  return (
    <group ref={groupRef} position={[x, y, z]}>
      {/* Outer glow */}
      <Sphere args={[0.35, 16, 16]}>
        <meshBasicMaterial color={color} transparent opacity={hovered ? 0.4 : 0.2} />
      </Sphere>

      {/* Core */}
      <Sphere
        args={[0.2, 16, 16]}
        onClick={onClick}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <meshBasicMaterial color={hovered ? COLORS.particleBright : color} />
      </Sphere>

      {/* Status ring */}
      {status === 'trading' && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.3, 0.015, 16, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.8} />
        </mesh>
      )}

      {/* Label */}
      <Html position={[0, 0.6, 0]} center distanceFactor={12}>
        <div
          className="text-xs font-bold whitespace-nowrap select-none px-2 py-0.5 rounded bg-black/40"
          style={{ color }}
        >
          {name}
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// AMBIENT PARTICLE FIELD - Background depth particles
// =============================================================================

function AmbientParticles() {
  const count = 300
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      position: new THREE.Vector3(
        (Math.random() - 0.5) * 20,
        (Math.random() - 0.5) * 20,
        (Math.random() - 0.5) * 20
      ),
      speed: 0.1 + Math.random() * 0.3,
      phase: Math.random() * Math.PI * 2,
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    particles.forEach((p, i) => {
      // Slow drift
      const x = p.position.x + Math.sin(t * p.speed + p.phase) * 0.01
      const y = p.position.y + Math.cos(t * p.speed * 0.7 + p.phase) * 0.01
      const z = p.position.z

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(0.015)
      dummy.updateMatrix()
      meshRef.current?.setMatrixAt(i, dummy.matrix)
    })
    if (meshRef.current) {
      meshRef.current.instanceMatrix.needsUpdate = true
    }
  })

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial color={COLORS.fiberOuter} transparent opacity={0.5} />
    </instancedMesh>
  )
}

// =============================================================================
// MAIN SCENE
// =============================================================================

function Scene({ botStatus, onNodeClick }: { botStatus: BotStatus, onNodeClick?: (id: string) => void }) {
  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.1} />
      <pointLight position={[0, 0, 0]} intensity={4} color={COLORS.coreRim} />
      <pointLight position={[10, 10, 10]} intensity={1} color="#ffffff" />
      <pointLight position={[-10, -10, -10]} intensity={0.5} color={COLORS.fiberInner} />

      {/* Background */}
      <Stars radius={100} depth={100} count={8000} factor={4} saturation={0} fade speed={0.2} />
      <NebulaBackdrop />

      {/* Core with breathing animation */}
      <BreathingCore />

      {/* Pulse wave effect */}
      <PulseWave />

      {/* Radial fiber burst - main visual element */}
      <RadialFiberBurst />

      {/* Energy accumulation effect */}
      <EnergyAccumulation />

      {/* Sparkle field */}
      <SparkleField />

      {/* Ambient particles for depth */}
      <AmbientParticles />

      {/* Bot nodes - integrated into aesthetic */}
      {BOT_NODES.map((node) => (
        <IntegratedBotNode
          key={node.id}
          id={node.id}
          name={node.name}
          angle={node.angle}
          status={botStatus[node.id as keyof BotStatus] || 'idle'}
          onClick={() => onNodeClick?.(node.id)}
        />
      ))}

      {/* Camera controls */}
      <OrbitControls
        enablePan={false}
        enableZoom={true}
        minDistance={4}
        maxDistance={25}
        autoRotate
        autoRotateSpeed={0.3}
        maxPolarAngle={Math.PI * 0.9}
        minPolarAngle={Math.PI * 0.1}
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
        <div className="w-16 h-16 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin mx-auto mb-4" />
        <p className="text-cyan-400">Initializing NEXUS...</p>
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

  const errorFallbackElement = <ErrorFallback message="A rendering error occurred. Please refresh the page." />

  return (
    <Canvas3DErrorBoundary fallback={errorFallbackElement}>
      <div className={`w-full h-full bg-[#030712] ${className}`}>
        <Canvas
          camera={{ position: [0, 2, 10], fov: 60 }}
          gl={{
            antialias: true,
            alpha: false,
            powerPreference: 'high-performance',
            failIfMajorPerformanceCaveat: false
          }}
          dpr={[1, 2]}
          onCreated={({ gl }) => {
            gl.setClearColor(COLORS.background)
          }}
          onError={(e) => {
            console.error('Canvas error:', e)
          }}
        >
          <color attach="background" args={[COLORS.background]} />
          <fog attach="fog" args={[COLORS.background, 20, 50]} />

          <Suspense fallback={null}>
            <Scene botStatus={botStatus} onNodeClick={onNodeClick} />
          </Suspense>
        </Canvas>
      </div>
    </Canvas3DErrorBoundary>
  )
}
