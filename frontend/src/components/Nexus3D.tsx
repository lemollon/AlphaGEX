'use client'

import { useRef, useMemo, useState, useEffect, Suspense, Component, ReactNode, useCallback } from 'react'
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
// ERROR BOUNDARY
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
  // Data integration props
  gexValue?: number        // -1 to 1 normalized GEX value
  vixValue?: number        // VIX level (10-80 typical range)
  spotPrice?: number       // SPY spot price
}

// =============================================================================
// COLOR PALETTE
// =============================================================================

const COLORS = {
  coreCenter: '#0c1929',
  coreRim: '#22d3ee',
  fiberInner: '#38bdf8',
  fiberOuter: '#1e40af',
  particleBright: '#e0f2fe',
  particleGlow: '#60a5fa',
  background: '#030712',
  nebula1: '#1e3a8a',
  nebula2: '#312e81',
  lightning: '#a5f3fc',
  flare: '#67e8f9',
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
// MOUSE TRACKER - Provides mouse position to scene
// =============================================================================

function useMousePosition() {
  const mouse = useRef(new THREE.Vector2(0, 0))
  const mouse3D = useRef(new THREE.Vector3(0, 0, 0))

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      mouse.current.x = (e.clientX / window.innerWidth) * 2 - 1
      mouse.current.y = -(e.clientY / window.innerHeight) * 2 + 1
      // Project to 3D space approximately
      mouse3D.current.set(mouse.current.x * 10, mouse.current.y * 10, 0)
    }
    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [])

  return { mouse2D: mouse, mouse3D: mouse3D }
}

// =============================================================================
// BREATHING CORE - GEX Reactive
// =============================================================================

function BreathingCore({ gexValue = 0, vixValue = 15 }: { gexValue?: number, vixValue?: number }) {
  const groupRef = useRef<THREE.Group>(null)
  const rimRef = useRef<THREE.Mesh>(null)
  const innerRef = useRef<THREE.Mesh>(null)

  // GEX affects size (more positive = larger)
  const gexScale = 1 + gexValue * 0.3

  // VIX affects pulse speed (higher VIX = faster heartbeat)
  const pulseSpeed = 0.5 + (vixValue / 30) * 1.5

  useFrame((state) => {
    const t = state.clock.elapsedTime
    const breathe = gexScale * (1 + Math.sin(t * pulseSpeed) * 0.1)

    if (groupRef.current) {
      groupRef.current.scale.setScalar(breathe)
    }
    if (rimRef.current) {
      const rimPulse = 0.2 + Math.sin(t * pulseSpeed * 2) * 0.1
      ;(rimRef.current.material as THREE.MeshBasicMaterial).opacity = rimPulse
    }
    if (innerRef.current) {
      innerRef.current.rotation.y = t * 0.15
      innerRef.current.rotation.x = Math.sin(t * 0.3) * 0.1
    }
  })

  // Color shifts based on GEX (negative = more red tint, positive = more green tint)
  const coreColor = gexValue > 0 ? '#0c2919' : gexValue < 0 ? '#290c19' : COLORS.coreCenter
  const rimColor = gexValue > 0 ? '#22eeb8' : gexValue < 0 ? '#ee2268' : COLORS.coreRim

  return (
    <group ref={groupRef}>
      {/* Outer rim glow */}
      <Sphere ref={rimRef} args={[1.8, 64, 64]}>
        <meshBasicMaterial color={rimColor} transparent opacity={0.2} />
      </Sphere>

      {/* Secondary glow */}
      <Sphere args={[1.5, 48, 48]}>
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.1} />
      </Sphere>

      {/* Main core */}
      <Sphere ref={innerRef} args={[1, 64, 64]}>
        <MeshDistortMaterial
          color={coreColor}
          emissive={rimColor}
          emissiveIntensity={2.5 + Math.abs(gexValue)}
          roughness={0.1}
          metalness={0.9}
          distort={0.2 + (vixValue / 100) * 0.2}
          speed={2 + vixValue / 20}
        />
      </Sphere>

      {/* Inner bright core */}
      <Sphere args={[0.35, 32, 32]}>
        <meshBasicMaterial color={COLORS.particleBright} transparent opacity={0.95} />
      </Sphere>

      {/* Rim ring */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.3, 0.02, 16, 100]} />
        <meshBasicMaterial color={rimColor} transparent opacity={0.7} />
      </mesh>

      {/* Core label */}
      <Html position={[0, -2.2, 0]} center distanceFactor={8}>
        <div className="text-cyan-300 text-sm font-bold whitespace-nowrap bg-black/60 px-3 py-1 rounded-full select-none border border-cyan-500/30">
          GEX CORE
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// CORE VORTEX - Swirling particles around core
// =============================================================================

function CoreVortex() {
  const count = 80
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const particles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      radius: 1.2 + Math.random() * 0.8,
      height: (Math.random() - 0.5) * 1.5,
      speed: 1.5 + Math.random() * 1,
      phase: (i / count) * Math.PI * 2,
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    particles.forEach((p, i) => {
      const angle = p.phase + t * p.speed
      const x = Math.cos(angle) * p.radius
      const z = Math.sin(angle) * p.radius
      const y = p.height + Math.sin(t * 2 + p.phase) * 0.2

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(0.03 + Math.sin(t * 3 + p.phase) * 0.01)
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
// RADIAL FIBER WITH MOUSE REPULSION
// =============================================================================

function RadialFiber({
  phi,
  theta,
  baseRadius,
  length,
  speed,
  particleCount = 3,
  mousePos
}: {
  phi: number
  theta: number
  baseRadius: number
  length: number
  speed: number
  particleCount?: number
  mousePos: React.MutableRefObject<THREE.Vector3>
}) {
  const groupRef = useRef<THREE.Group>(null)

  const endPoint = useMemo(() => {
    const r = baseRadius + length
    return new THREE.Vector3(
      r * Math.sin(phi) * Math.cos(theta),
      r * Math.sin(phi) * Math.sin(theta),
      r * Math.cos(phi)
    )
  }, [phi, theta, baseRadius, length])

  const { points, curve } = useMemo(() => {
    const start = new THREE.Vector3(0, 0, 0)
    const mid = endPoint.clone().multiplyScalar(0.5)
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

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (groupRef.current) {
      // Base sway
      let swayX = Math.sin(t * speed + phi) * 0.02
      let swayY = Math.cos(t * speed * 0.7 + theta) * 0.02

      // Mouse repulsion
      const fiberEnd = endPoint.clone()
      const dist = fiberEnd.distanceTo(mousePos.current)
      if (dist < 5) {
        const repulsion = (5 - dist) / 5 * 0.1
        const dir = fiberEnd.clone().sub(mousePos.current).normalize()
        swayX += dir.x * repulsion
        swayY += dir.y * repulsion
      }

      groupRef.current.rotation.x = swayX
      groupRef.current.rotation.y = swayY
    }
  })

  const fiberOpacity = 0.35 + (length / 8) * 0.3

  return (
    <group ref={groupRef}>
      <Line
        points={points}
        color={COLORS.fiberInner}
        lineWidth={1.2}
        transparent
        opacity={fiberOpacity}
      />

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
// FIBER PARTICLE
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
    const progress = ((t * speed * 0.3 + offset + phi) % 1)
    const point = curve.getPoint(progress)

    if (meshRef.current) {
      meshRef.current.position.copy(point)
      const sparkle = 0.035 + Math.sin(t * 10 + offset * 20) * 0.015
      meshRef.current.scale.setScalar(sparkle)
    }
    if (glowRef.current) {
      glowRef.current.position.copy(point)
      glowRef.current.scale.setScalar(0.1 + Math.sin(t * 5 + offset * 10) * 0.03)
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
// RADIAL FIBER BURST
// =============================================================================

function RadialFiberBurst({ mousePos }: { mousePos: React.MutableRefObject<THREE.Vector3> }) {
  const fibers = useMemo(() => {
    const result = []
    const fiberCount = 60
    const goldenAngle = Math.PI * (3 - Math.sqrt(5))

    for (let i = 0; i < fiberCount; i++) {
      const y = 1 - (i / (fiberCount - 1)) * 2
      const theta = goldenAngle * i
      const phi = Math.acos(y)
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
          mousePos={mousePos}
        />
      ))}
    </group>
  )
}

// =============================================================================
// INNER DENSE SHELL - Extra fibers near core
// =============================================================================

function InnerDenseShell({ mousePos }: { mousePos: React.MutableRefObject<THREE.Vector3> }) {
  const fibers = useMemo(() => {
    const result = []
    const fiberCount = 30
    const goldenAngle = Math.PI * (3 - Math.sqrt(5))

    for (let i = 0; i < fiberCount; i++) {
      const y = 1 - (i / (fiberCount - 1)) * 2
      const theta = goldenAngle * i * 1.5
      const phi = Math.acos(y)
      const length = 1.5 + Math.random() * 1.5
      const speed = 0.5 + Math.random() * 0.3

      result.push({ phi, theta, length, speed })
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
          baseRadius={1.2}
          length={fiber.length}
          speed={fiber.speed}
          particleCount={1}
          mousePos={mousePos}
        />
      ))}
    </group>
  )
}

// =============================================================================
// MULTIPLE PULSE WAVES - VIX Reactive
// =============================================================================

function MultiplePulseWaves({ vixValue = 15 }: { vixValue?: number }) {
  const ring1Ref = useRef<THREE.Mesh>(null)
  const ring2Ref = useRef<THREE.Mesh>(null)
  const ring3Ref = useRef<THREE.Mesh>(null)

  // VIX affects pulse frequency
  const pulseInterval = Math.max(1.5, 4 - vixValue / 15)

  useFrame((state) => {
    const t = state.clock.elapsedTime

    // Ring 1
    const pulse1 = (t % pulseInterval) / pulseInterval
    if (ring1Ref.current) {
      ring1Ref.current.scale.setScalar(1 + pulse1 * 10)
      ;(ring1Ref.current.material as THREE.MeshBasicMaterial).opacity = 0.5 * (1 - pulse1)
    }

    // Ring 2 (offset)
    const pulse2 = ((t + pulseInterval / 3) % pulseInterval) / pulseInterval
    if (ring2Ref.current) {
      ring2Ref.current.scale.setScalar(1 + pulse2 * 10)
      ;(ring2Ref.current.material as THREE.MeshBasicMaterial).opacity = 0.4 * (1 - pulse2)
    }

    // Ring 3 (offset)
    const pulse3 = ((t + pulseInterval * 2 / 3) % pulseInterval) / pulseInterval
    if (ring3Ref.current) {
      ring3Ref.current.scale.setScalar(1 + pulse3 * 10)
      ;(ring3Ref.current.material as THREE.MeshBasicMaterial).opacity = 0.3 * (1 - pulse3)
    }
  })

  return (
    <group>
      <mesh ref={ring1Ref} rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.95, 1, 64]} />
        <meshBasicMaterial color={COLORS.coreRim} transparent opacity={0.5} side={THREE.DoubleSide} />
      </mesh>
      <mesh ref={ring2Ref} rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.9, 0.95, 64]} />
        <meshBasicMaterial color={COLORS.fiberInner} transparent opacity={0.4} side={THREE.DoubleSide} />
      </mesh>
      <mesh ref={ring3Ref} rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.85, 0.9, 64]} />
        <meshBasicMaterial color={COLORS.particleGlow} transparent opacity={0.3} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

// =============================================================================
// CLICK SHOCKWAVE
// =============================================================================

function ClickShockwave({ shockwaveTime }: { shockwaveTime: number }) {
  const ringRef = useRef<THREE.Mesh>(null)
  const [active, setActive] = useState(false)
  const startTime = useRef(0)

  useEffect(() => {
    if (shockwaveTime > 0) {
      setActive(true)
      startTime.current = shockwaveTime
    }
  }, [shockwaveTime])

  useFrame((state) => {
    if (!active || !ringRef.current) return

    const elapsed = state.clock.elapsedTime - startTime.current
    if (elapsed > 1.5) {
      setActive(false)
      return
    }

    const progress = elapsed / 1.5
    ringRef.current.scale.setScalar(1 + progress * 15)
    ;(ringRef.current.material as THREE.MeshBasicMaterial).opacity = 0.8 * (1 - progress)
  })

  if (!active) return null

  return (
    <mesh ref={ringRef} rotation={[Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.8, 1.2, 64]} />
      <meshBasicMaterial color="#ffffff" transparent opacity={0.8} side={THREE.DoubleSide} />
    </mesh>
  )
}

// =============================================================================
// LIGHTNING ARCS
// =============================================================================

function LightningArcs() {
  const [arcs, setArcs] = useState<Array<{ start: THREE.Vector3, end: THREE.Vector3, id: number }>>([])
  const nextId = useRef(0)

  useFrame((state) => {
    // Randomly spawn lightning
    if (Math.random() < 0.01) {
      const node1 = BOT_NODES[Math.floor(Math.random() * BOT_NODES.length)]
      const node2 = BOT_NODES[Math.floor(Math.random() * BOT_NODES.length)]
      if (node1 !== node2) {
        const radius = 5
        const start = new THREE.Vector3(
          Math.cos(node1.angle) * radius,
          0,
          Math.sin(node1.angle) * radius
        )
        const end = new THREE.Vector3(
          Math.cos(node2.angle) * radius,
          0,
          Math.sin(node2.angle) * radius
        )
        setArcs(prev => [...prev.slice(-3), { start, end, id: nextId.current++ }])
      }
    }
  })

  return (
    <group>
      {arcs.map(arc => (
        <LightningArc key={arc.id} start={arc.start} end={arc.end} />
      ))}
    </group>
  )
}

function LightningArc({ start, end }: { start: THREE.Vector3, end: THREE.Vector3 }) {
  const lineRef = useRef<THREE.Line>(null)
  const [opacity, setOpacity] = useState(1)
  const birthTime = useRef(0)

  const points = useMemo(() => {
    const pts: [number, number, number][] = []
    const segments = 8
    for (let i = 0; i <= segments; i++) {
      const t = i / segments
      const p = start.clone().lerp(end, t)
      // Add jagged offset
      if (i > 0 && i < segments) {
        p.x += (Math.random() - 0.5) * 0.5
        p.y += (Math.random() - 0.5) * 0.5
        p.z += (Math.random() - 0.5) * 0.5
      }
      pts.push([p.x, p.y, p.z])
    }
    return pts
  }, [start, end])

  useFrame((state) => {
    if (birthTime.current === 0) birthTime.current = state.clock.elapsedTime
    const elapsed = state.clock.elapsedTime - birthTime.current
    setOpacity(Math.max(0, 1 - elapsed * 3))
  })

  if (opacity <= 0) return null

  return (
    <Line
      points={points}
      color={COLORS.lightning}
      lineWidth={2}
      transparent
      opacity={opacity}
    />
  )
}

// =============================================================================
// LENS FLARE
// =============================================================================

function LensFlare() {
  const flare1Ref = useRef<THREE.Mesh>(null)
  const flare2Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (flare1Ref.current) {
      flare1Ref.current.scale.setScalar(2 + Math.sin(t * 2) * 0.3)
      ;(flare1Ref.current.material as THREE.MeshBasicMaterial).opacity = 0.08 + Math.sin(t * 3) * 0.03
    }
    if (flare2Ref.current) {
      flare2Ref.current.scale.setScalar(3 + Math.sin(t * 1.5) * 0.5)
      ;(flare2Ref.current.material as THREE.MeshBasicMaterial).opacity = 0.04 + Math.sin(t * 2) * 0.02
    }
  })

  return (
    <group>
      <Sphere ref={flare1Ref} args={[1, 32, 32]}>
        <meshBasicMaterial color={COLORS.flare} transparent opacity={0.08} />
      </Sphere>
      <Sphere ref={flare2Ref} args={[1, 32, 32]}>
        <meshBasicMaterial color={COLORS.particleBright} transparent opacity={0.04} />
      </Sphere>
    </group>
  )
}

// =============================================================================
// HOLOGRAPHIC SCANLINES
// =============================================================================

function HolographicScanlines() {
  const groupRef = useRef<THREE.Group>(null)
  const line1Ref = useRef<THREE.Mesh>(null)
  const line2Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (line1Ref.current) {
      line1Ref.current.position.y = ((t * 2) % 20) - 10
    }
    if (line2Ref.current) {
      line2Ref.current.position.y = ((t * 2 + 10) % 20) - 10
    }
  })

  return (
    <group ref={groupRef}>
      <mesh ref={line1Ref} rotation={[0, 0, 0]}>
        <planeGeometry args={[30, 0.02]} />
        <meshBasicMaterial color={COLORS.coreRim} transparent opacity={0.1} side={THREE.DoubleSide} />
      </mesh>
      <mesh ref={line2Ref} rotation={[0, 0, 0]}>
        <planeGeometry args={[30, 0.015]} />
        <meshBasicMaterial color={COLORS.fiberInner} transparent opacity={0.08} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

// =============================================================================
// GLITCH EFFECT
// =============================================================================

function GlitchEffect() {
  const [glitching, setGlitching] = useState(false)
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    // Random glitch trigger
    if (!glitching && Math.random() < 0.002) {
      setGlitching(true)
      setTimeout(() => setGlitching(false), 100 + Math.random() * 150)
    }

    if (meshRef.current && glitching) {
      meshRef.current.position.x = (Math.random() - 0.5) * 0.3
      meshRef.current.position.y = (Math.random() - 0.5) * 0.3
    } else if (meshRef.current) {
      meshRef.current.position.set(0, 0, 0)
    }
  })

  if (!glitching) return null

  return (
    <mesh ref={meshRef}>
      <planeGeometry args={[20, 20]} />
      <meshBasicMaterial color={COLORS.coreRim} transparent opacity={0.05} side={THREE.DoubleSide} />
    </mesh>
  )
}

// =============================================================================
// OUTER PARTICLE RING
// =============================================================================

function OuterParticleRing() {
  const count = 150
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const groupRef = useRef<THREE.Group>(null)

  const particles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      angle: (i / count) * Math.PI * 2,
      radius: 9 + (Math.random() - 0.5) * 1,
      yOffset: (Math.random() - 0.5) * 0.5,
      speed: 0.05 + Math.random() * 0.03,
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime

    if (groupRef.current) {
      groupRef.current.rotation.y = t * 0.02
    }

    particles.forEach((p, i) => {
      const angle = p.angle + t * p.speed
      const x = Math.cos(angle) * p.radius
      const z = Math.sin(angle) * p.radius
      const y = p.yOffset + Math.sin(t + p.angle) * 0.1

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(0.025 + Math.sin(t * 2 + p.angle) * 0.01)
      dummy.updateMatrix()
      meshRef.current?.setMatrixAt(i, dummy.matrix)
    })
    if (meshRef.current) {
      meshRef.current.instanceMatrix.needsUpdate = true
    }
  })

  return (
    <group ref={groupRef}>
      <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
        <sphereGeometry args={[1, 6, 6]} />
        <meshBasicMaterial color={COLORS.fiberOuter} transparent opacity={0.6} />
      </instancedMesh>
    </group>
  )
}

// =============================================================================
// CONNECTING ARCS BETWEEN BOT NODES
// =============================================================================

function ConnectingArcs() {
  const arcs = useMemo(() => {
    const result = []
    for (let i = 0; i < BOT_NODES.length; i++) {
      const next = (i + 1) % BOT_NODES.length
      const node1 = BOT_NODES[i]
      const node2 = BOT_NODES[next]
      const radius = 5

      const start = new THREE.Vector3(
        Math.cos(node1.angle) * radius,
        0,
        Math.sin(node1.angle) * radius
      )
      const end = new THREE.Vector3(
        Math.cos(node2.angle) * radius,
        0,
        Math.sin(node2.angle) * radius
      )
      const mid = start.clone().add(end).multiplyScalar(0.5)
      mid.y = 1.5 // Arc upward

      const curve = new THREE.QuadraticBezierCurve3(start, mid, end)
      const points = curve.getPoints(30).map(p => [p.x, p.y, p.z] as [number, number, number])
      result.push({ points, id: i })
    }
    return result
  }, [])

  return (
    <group>
      {arcs.map(arc => (
        <Line
          key={arc.id}
          points={arc.points}
          color={COLORS.fiberOuter}
          lineWidth={0.5}
          transparent
          opacity={0.2}
        />
      ))}
    </group>
  )
}

// =============================================================================
// BOT NODE WITH ACTIVITY FLARES
// =============================================================================

function BotNodeWithFlare({
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
  const flareRef = useRef<THREE.Mesh>(null)
  const [hovered, setHovered] = useState(false)

  const radius = 5
  const x = Math.cos(angle) * radius
  const z = Math.sin(angle) * radius

  const color = STATUS_COLORS[status as keyof typeof STATUS_COLORS] || COLORS.particleGlow
  const isActive = status === 'trading' || status === 'active'

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (groupRef.current) {
      groupRef.current.position.y = Math.sin(t * 1.2 + angle) * 0.2
    }

    // Activity flare for active/trading bots
    if (flareRef.current && isActive) {
      const pulse = Math.sin(t * 4) * 0.5 + 0.5
      flareRef.current.scale.setScalar(0.5 + pulse * 0.3)
      ;(flareRef.current.material as THREE.MeshBasicMaterial).opacity = 0.3 + pulse * 0.2
    }
  })

  return (
    <group ref={groupRef} position={[x, 0, z]}>
      {/* Activity flare */}
      {isActive && (
        <Sphere ref={flareRef} args={[1, 16, 16]}>
          <meshBasicMaterial color={color} transparent opacity={0.4} />
        </Sphere>
      )}

      {/* Outer glow */}
      <Sphere args={[0.35, 16, 16]}>
        <meshBasicMaterial color={color} transparent opacity={hovered ? 0.5 : 0.25} />
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

      {/* Trading ring */}
      {status === 'trading' && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.4, 0.02, 16, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.8} />
        </mesh>
      )}

      {/* Label */}
      <Html position={[0, 0.7, 0]} center distanceFactor={12}>
        <div
          className="text-xs font-bold whitespace-nowrap select-none px-2 py-0.5 rounded bg-black/50"
          style={{ color }}
        >
          {name}
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// SPARKLE FIELD
// =============================================================================

function SparkleField() {
  const count = 120
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const sparkles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      position: new THREE.Vector3(
        (Math.random() - 0.5) * 18,
        (Math.random() - 0.5) * 18,
        (Math.random() - 0.5) * 18
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
      const twinkle = Math.max(0, Math.sin(t * s.speed + s.phase))
      dummy.scale.setScalar(twinkle * twinkle * 0.06)
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
// ENERGY ACCUMULATION
// =============================================================================

function EnergyAccumulation() {
  const count = 40
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const particles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => {
      const phi = Math.acos(-1 + (2 * i) / count)
      const theta = Math.sqrt(count * Math.PI) * phi
      return {
        startRadius: 7 + Math.random() * 2,
        phi,
        theta,
      }
    })
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    const cycle = (t % 5) / 5

    particles.forEach((p, i) => {
      let radius
      if (cycle < 0.7) {
        radius = p.startRadius * (1 - cycle / 0.7 * 0.9)
      } else {
        const burstProgress = (cycle - 0.7) / 0.3
        radius = p.startRadius * 0.1 + burstProgress * p.startRadius
      }

      const x = radius * Math.sin(p.phi) * Math.cos(p.theta)
      const y = radius * Math.sin(p.phi) * Math.sin(p.theta)
      const z = radius * Math.cos(p.phi)

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(cycle < 0.7 ? 0.07 : 0.05)
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
// NEBULA BACKDROP
// =============================================================================

function NebulaBackdrop() {
  const mesh1Ref = useRef<THREE.Mesh>(null)
  const mesh2Ref = useRef<THREE.Mesh>(null)
  const mesh3Ref = useRef<THREE.Mesh>(null)

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
    if (mesh3Ref.current) {
      mesh3Ref.current.rotation.y = t * 0.007
    }
  })

  return (
    <group>
      <Sphere ref={mesh1Ref} args={[35, 32, 32]} position={[12, 6, -25]}>
        <meshBasicMaterial color={COLORS.nebula1} transparent opacity={0.035} />
      </Sphere>
      <Sphere ref={mesh2Ref} args={[30, 32, 32]} position={[-18, -10, -30]}>
        <meshBasicMaterial color={COLORS.nebula2} transparent opacity={0.03} />
      </Sphere>
      <Sphere ref={mesh3Ref} args={[25, 32, 32]} position={[0, 15, -35]}>
        <meshBasicMaterial color="#1e1b4b" transparent opacity={0.025} />
      </Sphere>
    </group>
  )
}

// =============================================================================
// AMBIENT PARTICLES
// =============================================================================

function AmbientParticles() {
  const count = 350
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      position: new THREE.Vector3(
        (Math.random() - 0.5) * 24,
        (Math.random() - 0.5) * 24,
        (Math.random() - 0.5) * 24
      ),
      speed: 0.1 + Math.random() * 0.3,
      phase: Math.random() * Math.PI * 2,
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    particles.forEach((p, i) => {
      const x = p.position.x + Math.sin(t * p.speed + p.phase) * 0.015
      const y = p.position.y + Math.cos(t * p.speed * 0.7 + p.phase) * 0.015
      const z = p.position.z

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(0.018)
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

interface SceneProps {
  botStatus: BotStatus
  onNodeClick?: (id: string) => void
  gexValue?: number
  vixValue?: number
  shockwaveTime: number
}

function Scene({ botStatus, onNodeClick, gexValue = 0, vixValue = 15, shockwaveTime }: SceneProps) {
  const { mouse2D, mouse3D } = useMousePosition()

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.1} />
      <pointLight position={[0, 0, 0]} intensity={5} color={COLORS.coreRim} />
      <pointLight position={[10, 10, 10]} intensity={1.2} color="#ffffff" />
      <pointLight position={[-10, -10, -10]} intensity={0.6} color={COLORS.fiberInner} />

      {/* Background */}
      <Stars radius={120} depth={120} count={10000} factor={4} saturation={0} fade speed={0.15} />
      <NebulaBackdrop />

      {/* Lens flare */}
      <LensFlare />

      {/* Core - GEX reactive */}
      <BreathingCore gexValue={gexValue} vixValue={vixValue} />

      {/* Core vortex */}
      <CoreVortex />

      {/* Pulse waves - VIX reactive */}
      <MultiplePulseWaves vixValue={vixValue} />

      {/* Click shockwave */}
      <ClickShockwave shockwaveTime={shockwaveTime} />

      {/* Radial fiber burst with mouse repulsion */}
      <RadialFiberBurst mousePos={mouse3D} />

      {/* Inner dense shell */}
      <InnerDenseShell mousePos={mouse3D} />

      {/* Connecting arcs between bots */}
      <ConnectingArcs />

      {/* Lightning arcs */}
      <LightningArcs />

      {/* Energy accumulation */}
      <EnergyAccumulation />

      {/* Sparkle field */}
      <SparkleField />

      {/* Outer particle ring */}
      <OuterParticleRing />

      {/* Ambient particles */}
      <AmbientParticles />

      {/* Holographic scanlines */}
      <HolographicScanlines />

      {/* Glitch effect */}
      <GlitchEffect />

      {/* Bot nodes with activity flares */}
      {BOT_NODES.map((node) => (
        <BotNodeWithFlare
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
        maxDistance={30}
        autoRotate
        autoRotateSpeed={0.25}
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
        <p className="text-gray-400 mb-4">WebGL may not be supported</p>
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
  className = '',
  gexValue = 0,
  vixValue = 15,
  spotPrice
}: Nexus3DProps) {
  const [mounted, setMounted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shockwaveTime, setShockwaveTime] = useState(0)

  useEffect(() => {
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

  // Click handler for shockwave
  const handleClick = useCallback(() => {
    setShockwaveTime(Date.now() / 1000)
  }, [])

  if (error) {
    return <ErrorFallback message={error} />
  }

  if (!mounted) {
    return <LoadingFallback />
  }

  const errorFallbackElement = <ErrorFallback message="A rendering error occurred. Please refresh." />

  return (
    <Canvas3DErrorBoundary fallback={errorFallbackElement}>
      <div className={`w-full h-full bg-[#030712] ${className}`} onClick={handleClick}>
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
        >
          <color attach="background" args={[COLORS.background]} />
          <fog attach="fog" args={[COLORS.background, 25, 60]} />

          <Suspense fallback={null}>
            <Scene
              botStatus={botStatus}
              onNodeClick={onNodeClick}
              gexValue={gexValue}
              vixValue={vixValue}
              shockwaveTime={shockwaveTime}
            />
          </Suspense>
        </Canvas>
      </div>
    </Canvas3DErrorBoundary>
  )
}
