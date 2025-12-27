'use client'

import { useRef, useMemo, useState, useEffect, Suspense, Component, ReactNode, useCallback, createContext } from 'react'
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

export type ColorTheme = 'cyan' | 'purple' | 'green' | 'red'

interface Nexus3DProps {
  botStatus?: BotStatus
  onNodeClick?: (nodeId: string) => void
  className?: string
  gexValue?: number
  vixValue?: number
  spotPrice?: number
  pnlValue?: number
  pnlPercent?: number
  signalStrength?: number
  onTrade?: (type: 'buy' | 'sell', success: boolean) => void
}

// =============================================================================
// COLOR THEMES
// =============================================================================

interface ColorScheme {
  coreCenter: string
  coreRim: string
  fiberInner: string
  fiberOuter: string
  particleBright: string
  particleGlow: string
  background: string
  nebula1: string
  nebula2: string
  lightning: string
  flare: string
  accent: string
}

const COLOR_THEMES: Record<ColorTheme, ColorScheme> = {
  cyan: {
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
    accent: '#06b6d4',
  },
  purple: {
    coreCenter: '#1a0c29',
    coreRim: '#c084fc',
    fiberInner: '#a855f7',
    fiberOuter: '#6b21a8',
    particleBright: '#f3e8ff',
    particleGlow: '#c084fc',
    background: '#0a0514',
    nebula1: '#581c87',
    nebula2: '#4c1d95',
    lightning: '#e9d5ff',
    flare: '#d8b4fe',
    accent: '#a855f7',
  },
  green: {
    coreCenter: '#0c291a',
    coreRim: '#4ade80',
    fiberInner: '#22c55e',
    fiberOuter: '#166534',
    particleBright: '#dcfce7',
    particleGlow: '#86efac',
    background: '#030d07',
    nebula1: '#14532d',
    nebula2: '#064e3b',
    lightning: '#bbf7d0',
    flare: '#86efac',
    accent: '#22c55e',
  },
  red: {
    coreCenter: '#290c0c',
    coreRim: '#f87171',
    fiberInner: '#ef4444',
    fiberOuter: '#991b1b',
    particleBright: '#fee2e2',
    particleGlow: '#fca5a5',
    background: '#0d0303',
    nebula1: '#7f1d1d',
    nebula2: '#831843',
    lightning: '#fecaca',
    flare: '#fca5a5',
    accent: '#ef4444',
  },
}

let COLORS: ColorScheme = COLOR_THEMES.cyan

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
// KONAMI CODE EASTER EGG
// =============================================================================

const KONAMI_CODE = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'KeyB', 'KeyA']

function useKonamiCode(callback: () => void) {
  const inputRef = useRef<string[]>([])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      inputRef.current = [...inputRef.current, e.code].slice(-10)
      if (inputRef.current.join(',') === KONAMI_CODE.join(',')) {
        callback()
        inputRef.current = []
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [callback])
}

// =============================================================================
// MOUSE TRACKER
// =============================================================================

function useMousePosition() {
  const mouse = useRef(new THREE.Vector2(0, 0))
  const mouse3D = useRef(new THREE.Vector3(0, 0, 0))

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      mouse.current.x = (e.clientX / window.innerWidth) * 2 - 1
      mouse.current.y = -(e.clientY / window.innerHeight) * 2 + 1
      mouse3D.current.set(mouse.current.x * 10, mouse.current.y * 10, 0)
    }
    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [])

  return { mouse2D: mouse, mouse3D: mouse3D }
}

// =============================================================================
// KEYBOARD CONTROLS HOOK
// =============================================================================

function useKeyboardControls(
  controlsRef: React.RefObject<any>,
  setPaused: (paused: boolean) => void,
  paused: boolean
) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!controlsRef.current) return

      const rotateSpeed = 0.1
      switch (e.code) {
        case 'ArrowLeft':
          controlsRef.current.setAzimuthalAngle(
            controlsRef.current.getAzimuthalAngle() - rotateSpeed
          )
          break
        case 'ArrowRight':
          controlsRef.current.setAzimuthalAngle(
            controlsRef.current.getAzimuthalAngle() + rotateSpeed
          )
          break
        case 'ArrowUp':
          controlsRef.current.setPolarAngle(
            Math.max(0.1, controlsRef.current.getPolarAngle() - rotateSpeed)
          )
          break
        case 'ArrowDown':
          controlsRef.current.setPolarAngle(
            Math.min(Math.PI - 0.1, controlsRef.current.getPolarAngle() + rotateSpeed)
          )
          break
        case 'Space':
          e.preventDefault()
          setPaused(!paused)
          break
        case 'KeyR':
          controlsRef.current.reset()
          break
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [controlsRef, setPaused, paused])
}

// =============================================================================
// CAMERA CONTROLLER - For double-click zoom and keyboard
// =============================================================================

function CameraController({
  controlsRef,
  zoomTarget,
  paused,
  setPaused
}: {
  controlsRef: React.RefObject<any>
  zoomTarget: THREE.Vector3 | null
  paused: boolean
  setPaused: (p: boolean) => void
}) {
  const { camera } = useThree()

  useKeyboardControls(controlsRef, setPaused, paused)

  useFrame(() => {
    if (zoomTarget && controlsRef.current) {
      const currentTarget = controlsRef.current.target
      currentTarget.lerp(zoomTarget, 0.03)

      // Calculate desired camera position - offset from target for good viewing angle
      const distance = camera.position.distanceTo(zoomTarget)
      const targetDistance = 8 // How close to get to the target

      if (distance > targetDistance) {
        // Calculate offset direction from target to camera
        const cameraOffset = new THREE.Vector3(3, 4, 8)
        const desiredPosition = zoomTarget.clone().add(cameraOffset)

        camera.position.lerp(desiredPosition, 0.025)
      }
    }
  })

  return null
}

// =============================================================================
// GRAVITY WELL EFFECT
// =============================================================================

function GravityWell({ position, active }: { position: THREE.Vector3, active: boolean }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const particlesRef = useRef<THREE.InstancedMesh>(null)
  const count = 30

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      angle: Math.random() * Math.PI * 2,
      radius: 1 + Math.random() * 2,
      speed: 2 + Math.random() * 2,
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    if (!active) return
    const t = state.clock.elapsedTime

    if (meshRef.current) {
      meshRef.current.scale.setScalar(1 + Math.sin(t * 3) * 0.1)
    }

    particles.forEach((p, i) => {
      const angle = p.angle + t * p.speed
      const radius = p.radius * (1 - (t % 1) * 0.5)
      const x = position.x + Math.cos(angle) * radius
      const z = position.z + Math.sin(angle) * radius
      const y = position.y + (Math.random() - 0.5) * 0.2

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(0.03)
      dummy.updateMatrix()
      particlesRef.current?.setMatrixAt(i, dummy.matrix)
    })
    if (particlesRef.current) {
      particlesRef.current.instanceMatrix.needsUpdate = true
    }
  })

  if (!active) return null

  return (
    <group>
      <Sphere ref={meshRef} args={[0.3, 16, 16]} position={position}>
        <meshBasicMaterial color={COLORS.accent} transparent opacity={0.3} />
      </Sphere>
      <instancedMesh ref={particlesRef} args={[undefined, undefined, count]} position={[0, 0, 0]}>
        <sphereGeometry args={[1, 6, 6]} />
        <meshBasicMaterial color={COLORS.particleBright} />
      </instancedMesh>
    </group>
  )
}

// =============================================================================
// TRADE EXPLOSION EFFECT
// =============================================================================

function TradeExplosion({
  position,
  type,
  active,
  onComplete
}: {
  position: THREE.Vector3
  type: 'buy' | 'sell'
  active: boolean
  onComplete: () => void
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const count = 50
  const startTime = useRef(0)
  const [started, setStarted] = useState(false)

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      direction: new THREE.Vector3(
        (Math.random() - 0.5) * 2,
        (Math.random() - 0.5) * 2,
        (Math.random() - 0.5) * 2
      ).normalize(),
      speed: 3 + Math.random() * 5,
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    if (!active) return

    if (!started) {
      startTime.current = state.clock.elapsedTime
      setStarted(true)
    }

    const elapsed = state.clock.elapsedTime - startTime.current
    if (elapsed > 1.5) {
      onComplete()
      setStarted(false)
      return
    }

    const progress = elapsed / 1.5

    particles.forEach((p, i) => {
      const dist = p.speed * elapsed * (1 - progress * 0.5)
      const pos = position.clone().add(p.direction.clone().multiplyScalar(dist))

      dummy.position.copy(pos)
      dummy.scale.setScalar(0.08 * (1 - progress))
      dummy.updateMatrix()
      meshRef.current?.setMatrixAt(i, dummy.matrix)
    })
    if (meshRef.current) {
      meshRef.current.instanceMatrix.needsUpdate = true
    }
  })

  if (!active) return null

  const color = type === 'buy' ? '#22c55e' : '#ef4444'

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial color={color} transparent opacity={0.9} />
    </instancedMesh>
  )
}

// =============================================================================
// ALERT PULSE EFFECT
// =============================================================================

function AlertPulse({ active, botStatus }: { active: boolean, botStatus: BotStatus }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const hasError = Object.values(botStatus).some(s => s === 'error')

  useFrame((state) => {
    if (!meshRef.current || !hasError) return
    const t = state.clock.elapsedTime
    const pulse = Math.sin(t * 8) * 0.5 + 0.5
    meshRef.current.scale.setScalar(12 + pulse * 3)
    ;(meshRef.current.material as THREE.MeshBasicMaterial).opacity = 0.03 + pulse * 0.05
  })

  if (!hasError) return null

  return (
    <Sphere ref={meshRef} args={[1, 32, 32]}>
      <meshBasicMaterial color="#ef4444" transparent opacity={0.05} side={THREE.BackSide} />
    </Sphere>
  )
}

// =============================================================================
// SUCCESS CELEBRATION
// =============================================================================

function SuccessCelebration({ active, onComplete }: { active: boolean, onComplete: () => void }) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const count = 100
  const startTime = useRef(0)
  const [started, setStarted] = useState(false)

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      position: new THREE.Vector3(
        (Math.random() - 0.5) * 15,
        -8,
        (Math.random() - 0.5) * 15
      ),
      velocity: new THREE.Vector3(
        (Math.random() - 0.5) * 2,
        5 + Math.random() * 8,
        (Math.random() - 0.5) * 2
      ),
      color: Math.random() > 0.5 ? '#fbbf24' : '#22c55e',
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    if (!active) return

    if (!started) {
      startTime.current = state.clock.elapsedTime
      setStarted(true)
    }

    const elapsed = state.clock.elapsedTime - startTime.current
    if (elapsed > 3) {
      onComplete()
      setStarted(false)
      return
    }

    particles.forEach((p, i) => {
      const y = p.position.y + p.velocity.y * elapsed - 4.9 * elapsed * elapsed
      const x = p.position.x + p.velocity.x * elapsed
      const z = p.position.z + p.velocity.z * elapsed

      dummy.position.set(x, y, z)
      dummy.scale.setScalar(0.08)
      dummy.updateMatrix()
      meshRef.current?.setMatrixAt(i, dummy.matrix)
    })
    if (meshRef.current) {
      meshRef.current.instanceMatrix.needsUpdate = true
    }
  })

  if (!active) return null

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial color="#fbbf24" transparent opacity={0.9} />
    </instancedMesh>
  )
}

// =============================================================================
// ORBIT TRAILS
// =============================================================================

function OrbitTrails() {
  const count = 8
  const trailsRef = useRef<THREE.Group>(null)

  const trails = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      radius: 6 + i * 0.8,
      speed: 0.3 - i * 0.02,
      offset: (i / count) * Math.PI * 2,
      tilt: (Math.random() - 0.5) * 0.3,
    }))
  }, [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (trailsRef.current) {
      trailsRef.current.rotation.y = t * 0.02
    }
  })

  return (
    <group ref={trailsRef}>
      {trails.map((trail, i) => (
        <mesh key={i} rotation={[trail.tilt, 0, 0]}>
          <torusGeometry args={[trail.radius, 0.008, 8, 100]} />
          <meshBasicMaterial color={COLORS.fiberOuter} transparent opacity={0.15 - i * 0.015} />
        </mesh>
      ))}
    </group>
  )
}

// =============================================================================
// PLASMA TENDRILS
// =============================================================================

function PlasmaTendrils() {
  const count = 6
  const groupRef = useRef<THREE.Group>(null)

  const tendrils = useMemo(() => {
    return Array.from({ length: count }, (_, i) => {
      const baseAngle = (i / count) * Math.PI * 2
      const points: [number, number, number][] = []
      for (let j = 0; j <= 20; j++) {
        const t = j / 20
        const radius = 2 + t * 6
        const angle = baseAngle + t * 0.5
        const wobble = Math.sin(t * Math.PI * 3) * 0.5
        points.push([
          Math.cos(angle) * radius + wobble,
          Math.sin(t * Math.PI) * 2 - 1,
          Math.sin(angle) * radius + wobble
        ])
      }
      return { points, phase: i }
    })
  }, [])

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.1
    }
  })

  return (
    <group ref={groupRef}>
      {tendrils.map((tendril, i) => (
        <Line
          key={i}
          points={tendril.points}
          color={COLORS.lightning}
          lineWidth={1}
          transparent
          opacity={0.2}
        />
      ))}
    </group>
  )
}

// =============================================================================
// MATRIX RAIN
// =============================================================================

function MatrixRain({ performanceMode }: { performanceMode: boolean }) {
  const count = performanceMode ? 30 : 80
  const meshRef = useRef<THREE.InstancedMesh>(null)

  const drops = useMemo(() => {
    return Array.from({ length: count }, () => ({
      x: (Math.random() - 0.5) * 30,
      z: (Math.random() - 0.5) * 30 - 15,
      speed: 2 + Math.random() * 4,
      offset: Math.random() * 20,
    }))
  }, [count])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    drops.forEach((drop, i) => {
      const y = ((drop.offset + t * drop.speed) % 20) - 10

      dummy.position.set(drop.x, y, drop.z)
      dummy.scale.set(0.02, 0.15, 0.02)
      dummy.updateMatrix()
      meshRef.current?.setMatrixAt(i, dummy.matrix)
    })
    if (meshRef.current) {
      meshRef.current.instanceMatrix.needsUpdate = true
    }
  })

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <boxGeometry args={[1, 1, 1]} />
      <meshBasicMaterial color={COLORS.accent} transparent opacity={0.3} />
    </instancedMesh>
  )
}

// =============================================================================
// WAVEFORM RINGS
// =============================================================================

function WaveformRings({ vixValue = 15 }: { vixValue?: number }) {
  const ringsRef = useRef<THREE.Group>(null)
  const ringCount = 5

  useFrame((state) => {
    if (!ringsRef.current) return
    const t = state.clock.elapsedTime
    const speed = 1 + vixValue / 30

    ringsRef.current.children.forEach((ring, i) => {
      const mesh = ring as THREE.Mesh
      const phase = (t * speed + i * 0.5) % 3
      const scale = 2 + phase * 3
      mesh.scale.setScalar(scale)
      ;(mesh.material as THREE.MeshBasicMaterial).opacity = 0.15 * (1 - phase / 3)
    })
  })

  return (
    <group ref={ringsRef} rotation={[Math.PI / 2, 0, 0]}>
      {Array.from({ length: ringCount }).map((_, i) => (
        <mesh key={i}>
          <ringGeometry args={[0.95, 1, 64]} />
          <meshBasicMaterial color={COLORS.accent} transparent opacity={0.15} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  )
}

// =============================================================================
// CONSTELLATION LINES
// =============================================================================

function ConstellationLines() {
  const lines = useMemo(() => {
    const starPositions: THREE.Vector3[] = []
    for (let i = 0; i < 20; i++) {
      starPositions.push(new THREE.Vector3(
        (Math.random() - 0.5) * 25,
        (Math.random() - 0.5) * 25,
        (Math.random() - 0.5) * 25 - 10
      ))
    }

    const connections: { points: [number, number, number][], opacity: number }[] = []
    for (let i = 0; i < starPositions.length; i++) {
      for (let j = i + 1; j < starPositions.length; j++) {
        const dist = starPositions[i].distanceTo(starPositions[j])
        if (dist < 8) {
          connections.push({
            points: [
              [starPositions[i].x, starPositions[i].y, starPositions[i].z],
              [starPositions[j].x, starPositions[j].y, starPositions[j].z]
            ],
            opacity: 0.1 * (1 - dist / 8)
          })
        }
      }
    }
    return { stars: starPositions, connections }
  }, [])

  return (
    <group>
      {lines.connections.map((line, i) => (
        <Line
          key={i}
          points={line.points}
          color={COLORS.fiberOuter}
          lineWidth={0.5}
          transparent
          opacity={line.opacity}
        />
      ))}
      {lines.stars.map((pos, i) => (
        <Sphere key={`star-${i}`} args={[0.05, 8, 8]} position={pos}>
          <meshBasicMaterial color={COLORS.particleBright} />
        </Sphere>
      ))}
    </group>
  )
}

// =============================================================================
// FLOATING MARKET STATS
// =============================================================================

function FloatingMarketStats({
  spotPrice,
  gexValue,
  vixValue
}: {
  spotPrice?: number
  gexValue?: number
  vixValue?: number
}) {
  const groupRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.3) * 0.1
      groupRef.current.position.y = 4 + Math.sin(state.clock.elapsedTime * 0.5) * 0.2
    }
  })

  return (
    <group ref={groupRef} position={[0, 4, -3]}>
      <Html center distanceFactor={10}>
        <div className="flex gap-4 text-xs font-mono select-none">
          {spotPrice !== undefined && (
            <div className="bg-black/70 border border-cyan-500/30 rounded px-3 py-1.5 backdrop-blur">
              <div className="text-gray-400">SPY</div>
              <div className="text-cyan-400 text-lg font-bold">${spotPrice.toFixed(2)}</div>
            </div>
          )}
          {gexValue !== undefined && (
            <div className="bg-black/70 border border-cyan-500/30 rounded px-3 py-1.5 backdrop-blur">
              <div className="text-gray-400">GEX</div>
              <div className={`text-lg font-bold ${gexValue >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {gexValue >= 0 ? '+' : ''}{(gexValue * 100).toFixed(1)}%
              </div>
            </div>
          )}
          {vixValue !== undefined && (
            <div className="bg-black/70 border border-cyan-500/30 rounded px-3 py-1.5 backdrop-blur">
              <div className="text-gray-400">VIX</div>
              <div className={`text-lg font-bold ${vixValue < 20 ? 'text-green-400' : vixValue < 30 ? 'text-yellow-400' : 'text-red-400'}`}>
                {vixValue.toFixed(1)}
              </div>
            </div>
          )}
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// P&L METER
// =============================================================================

function PnLMeter({ pnlValue = 0, pnlPercent = 0 }: { pnlValue?: number, pnlPercent?: number }) {
  const groupRef = useRef<THREE.Group>(null)
  const barRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.position.y = -3 + Math.sin(state.clock.elapsedTime * 0.4) * 0.1
    }
    if (barRef.current) {
      const targetScale = Math.min(Math.abs(pnlPercent) / 10, 1)
      barRef.current.scale.x = THREE.MathUtils.lerp(barRef.current.scale.x, targetScale, 0.1)
    }
  })

  const isPositive = pnlValue >= 0

  return (
    <group ref={groupRef} position={[0, -3, 3]}>
      <Html center distanceFactor={10}>
        <div className="bg-black/70 border border-cyan-500/30 rounded-lg px-4 py-2 backdrop-blur min-w-[120px]">
          <div className="text-gray-400 text-xs text-center">P&L</div>
          <div className={`text-xl font-bold text-center ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isPositive ? '+' : ''}{pnlPercent.toFixed(2)}%
          </div>
          <div className={`text-sm text-center ${isPositive ? 'text-green-300' : 'text-red-300'}`}>
            {isPositive ? '+' : ''}${Math.abs(pnlValue).toLocaleString()}
          </div>
          <div className="mt-1 h-1 bg-gray-700 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all ${isPositive ? 'bg-green-500' : 'bg-red-500'}`}
              style={{ width: `${Math.min(Math.abs(pnlPercent) * 10, 100)}%` }}
            />
          </div>
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// SIGNAL STRENGTH BARS
// =============================================================================

function SignalStrengthBars({ strength = 0.5 }: { strength?: number }) {
  const groupRef = useRef<THREE.Group>(null)
  const bars = 5

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.2
    }
  })

  return (
    <group ref={groupRef} position={[6, 0, 0]}>
      {Array.from({ length: bars }).map((_, i) => {
        const isActive = (i + 1) / bars <= strength
        const height = 0.3 + i * 0.2
        return (
          <mesh key={i} position={[i * 0.25, height / 2, 0]}>
            <boxGeometry args={[0.15, height, 0.15]} />
            <meshBasicMaterial
              color={isActive ? COLORS.accent : '#333'}
              transparent
              opacity={isActive ? 0.9 : 0.3}
            />
          </mesh>
        )
      })}
      <Html position={[0.5, -0.5, 0]} center>
        <div className="text-xs text-gray-400 whitespace-nowrap">SIGNAL</div>
      </Html>
    </group>
  )
}

// =============================================================================
// MARKET MOOD RING
// =============================================================================

function MarketMoodRing({ gexValue = 0, vixValue = 15 }: { gexValue?: number, vixValue?: number }) {
  const ringRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)

  // Calculate mood: positive GEX + low VIX = bullish, negative GEX + high VIX = bearish
  const mood = (gexValue + 0.5) * (1 - Math.min(vixValue / 50, 1))
  const moodColor = mood > 0.3 ? '#22c55e' : mood < -0.3 ? '#ef4444' : '#fbbf24'

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (ringRef.current) {
      ringRef.current.rotation.z = t * 0.5
    }
    if (glowRef.current) {
      glowRef.current.scale.setScalar(1 + Math.sin(t * 2) * 0.1)
    }
  })

  return (
    <group position={[-6, 0, 0]}>
      <mesh ref={glowRef}>
        <torusGeometry args={[1, 0.3, 16, 32]} />
        <meshBasicMaterial color={moodColor} transparent opacity={0.2} />
      </mesh>
      <mesh ref={ringRef}>
        <torusGeometry args={[1, 0.1, 16, 32]} />
        <meshBasicMaterial color={moodColor} transparent opacity={0.8} />
      </mesh>
      <Html position={[0, -1.8, 0]} center>
        <div className="text-xs text-center">
          <div className="text-gray-400">MOOD</div>
          <div style={{ color: moodColor }} className="font-bold">
            {mood > 0.3 ? 'BULLISH' : mood < -0.3 ? 'BEARISH' : 'NEUTRAL'}
          </div>
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// STOCK TICKERS DATA - Real-time prices from market API
// =============================================================================

// Fallback prices when API is unavailable
const FALLBACK_PRICES = [
  { symbol: 'SPY', price: 585, change: 0 },
  { symbol: 'QQQ', price: 505, change: 0 },
  { symbol: 'AAPL', price: 248, change: 0 },
  { symbol: 'NVDA', price: 138, change: 0 },
  { symbol: 'TSLA', price: 425, change: 0 },
  { symbol: 'AMZN', price: 225, change: 0 },
  { symbol: 'META', price: 612, change: 0 },
  { symbol: 'GOOGL', price: 192, change: 0 },
  { symbol: 'MSFT', price: 435, change: 0 },
  { symbol: 'AMD', price: 125, change: 0 },
]

// Real-time stock prices fetched from Tradier via backend API
const useStockPrices = () => {
  const [prices, setPrices] = useState(FALLBACK_PRICES)
  const [isLive, setIsLive] = useState(false)

  useEffect(() => {
    const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

    const fetchPrices = async () => {
      try {
        const response = await fetch(`${API_URL}/api/apollo/batch-quotes`)
        const result = await response.json()

        if (result.success && result.data && result.data.length > 0) {
          setPrices(result.data.map((q: any) => ({
            symbol: q.symbol,
            price: q.price || 0,
            change: q.change_pct || 0
          })))
          setIsLive(true)
        }
      } catch (error) {
        // Keep using fallback/last known prices on error
        console.log('Stock prices: using fallback data')
      }
    }

    // Fetch immediately
    fetchPrices()

    // Then refresh every 30 seconds (reasonable for visualization, avoids rate limits)
    const interval = setInterval(fetchPrices, 30000)

    return () => clearInterval(interval)
  }, [])

  return { prices, isLive }
}

const STOCK_TICKERS = [
  { symbol: 'SPY', basePrice: 585 },
  { symbol: 'QQQ', basePrice: 505 },
  { symbol: 'AAPL', basePrice: 248 },
  { symbol: 'NVDA', basePrice: 138 },
  { symbol: 'TSLA', basePrice: 425 },
  { symbol: 'AMZN', basePrice: 225 },
  { symbol: 'META', basePrice: 612 },
  { symbol: 'GOOGL', basePrice: 192 },
  { symbol: 'MSFT', basePrice: 435 },
  { symbol: 'AMD', basePrice: 125 },
]

// =============================================================================
// SOLAR SYSTEM DEFINITIONS - Each with unique flares and planet effects
// =============================================================================

// Planet routes for navigation
const PLANET_ROUTES: Record<string, string> = {
  // SOLOMON planets
  'Analysis': '/ai-copilot',
  'Strategy': '/strategies',
  'Insight': '/psychology',
  // ARGUS planets
  'Gamma': '/gamma',
  'Delta': '/gex',
  'Theta': '/vix',
  // ORACLE planets
  'Prediction': '/oracle',
  'Probability': '/probability',
  'Confidence': '/ml',
  // KRONOS planets
  'History': '/backtesting',
  'Backtest': '/zero-dte-backtest',
  'Patterns': '/setups',
  // SYSTEMS planets
  'Health': '/system/processes',
  'Data': '/database',
  'Network': '/data-transparency',
}

const SOLAR_SYSTEMS = [
  {
    id: 'solomon',
    name: 'SOLOMON',
    subtitle: 'AI Wisdom',
    route: '/solomon',
    position: [-22, 8, -20] as [number, number, number],  // Far upper left
    sunColor: '#f59e0b',
    glowColor: '#fbbf24',
    flareType: 'wisdom' as const,  // Golden rays of wisdom
    planets: [
      { name: 'Analysis', color: '#22d3ee', size: 0.18, orbit: 1.8, speed: 0.6, effect: 'rings' as const, moons: 1 },
      { name: 'Strategy', color: '#a855f7', size: 0.15, orbit: 2.8, speed: 0.4, effect: 'crystals' as const, moons: 2 },
      { name: 'Insight', color: '#10b981', size: 0.12, orbit: 3.6, speed: 0.25, effect: 'aura' as const, moons: 0 },
    ]
  },
  {
    id: 'argus',
    name: 'ARGUS',
    subtitle: 'All-Seeing Eye',
    route: '/argus',
    position: [24, 5, -18] as [number, number, number],  // Far right
    sunColor: '#06b6d4',
    glowColor: '#22d3ee',
    flareType: 'pulse' as const,  // Scanning pulse waves
    planets: [
      { name: 'Gamma', color: '#f97316', size: 0.22, orbit: 2.0, speed: 0.8, effect: 'fire' as const, moons: 2 },
      { name: 'Delta', color: '#ef4444', size: 0.16, orbit: 3.0, speed: 0.5, effect: 'electric' as const, moons: 1 },
      { name: 'Theta', color: '#8b5cf6', size: 0.13, orbit: 3.8, speed: 0.35, effect: 'spiral' as const, moons: 3 },
    ]
  },
  {
    id: 'oracle',
    name: 'ORACLE',
    subtitle: 'Future Sight',
    route: '/oracle',
    position: [0, 15, -25] as [number, number, number],  // High above center
    sunColor: '#8b5cf6',
    glowColor: '#a855f7',
    flareType: 'mystic' as const,  // Mystical swirling energy
    planets: [
      { name: 'Prediction', color: '#22d3ee', size: 0.20, orbit: 2.2, speed: 0.7, effect: 'glow' as const, moons: 1 },
      { name: 'Probability', color: '#10b981', size: 0.17, orbit: 3.2, speed: 0.45, effect: 'orbit_rings' as const, moons: 2 },
      { name: 'Confidence', color: '#f59e0b', size: 0.14, orbit: 4.0, speed: 0.3, effect: 'pulse' as const, moons: 0 },
    ]
  },
  {
    id: 'kronos',
    name: 'KRONOS',
    subtitle: 'Time Master',
    route: '/backtesting',
    position: [-18, -8, -22] as [number, number, number],  // Lower left
    sunColor: '#ef4444',
    glowColor: '#f87171',
    flareType: 'eruption' as const,  // Violent solar eruptions
    planets: [
      { name: 'History', color: '#6b7280', size: 0.19, orbit: 2.4, speed: 0.55, effect: 'dust' as const, moons: 1 },
      { name: 'Backtest', color: '#3b82f6', size: 0.16, orbit: 3.4, speed: 0.38, effect: 'data_stream' as const, moons: 2 },
      { name: 'Patterns', color: '#fbbf24', size: 0.13, orbit: 4.2, speed: 0.25, effect: 'hexagon' as const, moons: 1 },
    ]
  },
  {
    id: 'systems',
    name: 'SYSTEMS',
    subtitle: 'Core Hub',
    route: '/system/processes',
    position: [20, -6, -20] as [number, number, number],  // Lower right
    sunColor: '#10b981',
    glowColor: '#34d399',
    flareType: 'network' as const,  // Network connection beams
    planets: [
      { name: 'Health', color: '#22c55e', size: 0.18, orbit: 2.0, speed: 0.7, effect: 'heartbeat' as const, moons: 0 },
      { name: 'Data', color: '#3b82f6', size: 0.15, orbit: 3.0, speed: 0.45, effect: 'binary' as const, moons: 1 },
      { name: 'Network', color: '#ec4899', size: 0.12, orbit: 3.8, speed: 0.3, effect: 'connections' as const, moons: 2 },
    ]
  },
]

// =============================================================================
// ASTEROIDS WITH TICKERS
// =============================================================================

function AsteroidWithTicker({
  initialPosition,
  velocity,
  ticker,
  onComplete
}: {
  initialPosition: THREE.Vector3
  velocity: THREE.Vector3
  ticker: { symbol: string, price: number, change: number }
  onComplete: () => void
}) {
  const groupRef = useRef<THREE.Group>(null)
  const meshRef = useRef<THREE.Mesh>(null)
  const startTime = useRef(0)
  const [started, setStarted] = useState(false)

  useFrame((state) => {
    if (!started) {
      startTime.current = state.clock.elapsedTime
      setStarted(true)
    }

    const elapsed = state.clock.elapsedTime - startTime.current
    if (elapsed > 8) {
      onComplete()
      return
    }

    if (groupRef.current) {
      groupRef.current.position.set(
        initialPosition.x + velocity.x * elapsed,
        initialPosition.y + velocity.y * elapsed,
        initialPosition.z + velocity.z * elapsed
      )
    }
    if (meshRef.current) {
      meshRef.current.rotation.x += 0.02
      meshRef.current.rotation.y += 0.03
    }
  })

  const isPositive = ticker.change >= 0

  return (
    <group ref={groupRef} position={initialPosition}>
      {/* Asteroid rock */}
      <mesh ref={meshRef}>
        <dodecahedronGeometry args={[0.4, 0]} />
        <meshBasicMaterial color="#6b7280" />
      </mesh>
      {/* Fire trail */}
      <mesh position={[-0.5, 0, 0]}>
        <coneGeometry args={[0.2, 0.8, 8]} />
        <meshBasicMaterial color="#f97316" transparent opacity={0.6} />
      </mesh>
      {/* Ticker label */}
      <Html position={[0, 0.8, 0]} center>
        <div className="bg-black/80 border border-cyan-500/50 rounded px-2 py-1 whitespace-nowrap">
          <span className="text-cyan-400 font-bold">{ticker.symbol}</span>
          <span className="text-white ml-2">${ticker.price.toFixed(2)}</span>
          <span className={`ml-1 ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isPositive ? '+' : ''}{ticker.change.toFixed(2)}%
          </span>
        </div>
      </Html>
    </group>
  )
}

function AsteroidField({ paused, stockPrices }: { paused: boolean, stockPrices: Array<{ symbol: string, price: number, change: number }> }) {
  const [asteroids, setAsteroids] = useState<Array<{
    id: number
    position: THREE.Vector3
    velocity: THREE.Vector3
    ticker: { symbol: string, price: number, change: number }
  }>>([])
  const nextId = useRef(0)
  const lastSpawn = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Spawn asteroid every 45-90 seconds
    if (t - lastSpawn.current > 45 + Math.random() * 45) {
      lastSpawn.current = t
      // Use real-time stock prices if available
      const stockData = stockPrices[Math.floor(Math.random() * stockPrices.length)]
      const side = Math.random() > 0.5 ? 1 : -1

      setAsteroids(prev => [...prev, {
        id: nextId.current++,
        position: new THREE.Vector3(side * 20, (Math.random() - 0.5) * 10, -5 + Math.random() * 10),
        velocity: new THREE.Vector3(-side * 3, (Math.random() - 0.5) * 0.5, 0),
        ticker: {
          symbol: stockData.symbol,
          price: stockData.price,
          change: stockData.change
        }
      }])
    }
  })

  return (
    <group>
      {asteroids.map(asteroid => (
        <AsteroidWithTicker
          key={asteroid.id}
          initialPosition={asteroid.position}
          velocity={asteroid.velocity}
          ticker={asteroid.ticker}
          onComplete={() => setAsteroids(prev => prev.filter(a => a.id !== asteroid.id))}
        />
      ))}
    </group>
  )
}

// =============================================================================
// COMET WITH TRAIL
// =============================================================================

function CometWithTrail({ paused }: { paused: boolean }) {
  const [comets, setComets] = useState<Array<{
    id: number
    startPos: THREE.Vector3
    endPos: THREE.Vector3
    startTime: number
  }>>([])
  const nextId = useRef(0)
  const lastSpawn = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Spawn comet every 60-120 seconds
    if (t - lastSpawn.current > 60 + Math.random() * 60) {
      lastSpawn.current = t
      setComets(prev => [...prev, {
        id: nextId.current++,
        startPos: new THREE.Vector3(
          (Math.random() - 0.5) * 30,
          10 + Math.random() * 5,
          -10 - Math.random() * 10
        ),
        endPos: new THREE.Vector3(
          (Math.random() - 0.5) * 30,
          -15,
          5
        ),
        startTime: t
      }])
    }

    // Clean up old comets
    setComets(prev => prev.filter(c => t - c.startTime < 5))
  })

  return (
    <group>
      {comets.map(comet => (
        <Comet key={comet.id} startPos={comet.startPos} endPos={comet.endPos} startTime={comet.startTime} />
      ))}
    </group>
  )
}

function Comet({ startPos, endPos, startTime }: { startPos: THREE.Vector3, endPos: THREE.Vector3, startTime: number }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const trailRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const elapsed = state.clock.elapsedTime - startTime
    const progress = Math.min(elapsed / 4, 1)
    const pos = startPos.clone().lerp(endPos, progress)

    if (meshRef.current) {
      meshRef.current.position.copy(pos)
    }
    if (trailRef.current) {
      trailRef.current.position.copy(pos)
      trailRef.current.scale.x = 2 + progress * 3
      const mat = trailRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = 0.6 * (1 - progress)
    }
  })

  return (
    <group>
      {/* Comet head */}
      <Sphere ref={meshRef} args={[0.15, 16, 16]}>
        <meshBasicMaterial color="#a5f3fc" />
      </Sphere>
      {/* Comet tail */}
      <mesh ref={trailRef} rotation={[0, 0, Math.PI / 4]}>
        <coneGeometry args={[0.1, 2, 8]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.6} />
      </mesh>
    </group>
  )
}

// =============================================================================
// ASTEROID BELT
// =============================================================================

function AsteroidBelt({ performanceMode }: { performanceMode: boolean }) {
  const count = performanceMode ? 40 : 100
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const groupRef = useRef<THREE.Group>(null)

  const asteroids = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      angle: (i / count) * Math.PI * 2,
      radius: 11 + (Math.random() - 0.5) * 1.5,
      yOffset: (Math.random() - 0.5) * 0.8,
      speed: 0.02 + Math.random() * 0.02,
      rotSpeed: Math.random() * 0.1,
      scale: 0.03 + Math.random() * 0.04,
    }))
  }, [count])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    const t = state.clock.elapsedTime

    if (groupRef.current) {
      groupRef.current.rotation.y = t * 0.01
    }

    asteroids.forEach((a, i) => {
      const angle = a.angle + t * a.speed
      const x = Math.cos(angle) * a.radius
      const z = Math.sin(angle) * a.radius
      const y = a.yOffset + Math.sin(t + a.angle) * 0.1

      dummy.position.set(x, y, z)
      dummy.rotation.set(t * a.rotSpeed, t * a.rotSpeed * 0.7, 0)
      dummy.scale.setScalar(a.scale)
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
        <dodecahedronGeometry args={[1, 0]} />
        <meshBasicMaterial color="#4b5563" />
      </instancedMesh>
    </group>
  )
}

// =============================================================================
// SHOOTING STARS
// =============================================================================

function ShootingStars({ paused }: { paused: boolean }) {
  const [stars, setStars] = useState<Array<{
    id: number
    start: THREE.Vector3
    end: THREE.Vector3
    startTime: number
  }>>([])
  const nextId = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Random shooting star
    if (Math.random() < 0.003) {
      const startX = (Math.random() - 0.5) * 40
      setStars(prev => [...prev, {
        id: nextId.current++,
        start: new THREE.Vector3(startX, 15 + Math.random() * 5, -15),
        end: new THREE.Vector3(startX + (Math.random() - 0.5) * 10, -10, -10),
        startTime: t
      }])
    }

    // Clean up
    setStars(prev => prev.filter(s => t - s.startTime < 1))
  })

  return (
    <group>
      {stars.map(star => (
        <ShootingStar key={star.id} start={star.start} end={star.end} startTime={star.startTime} />
      ))}
    </group>
  )
}

function ShootingStar({ start, end, startTime }: { start: THREE.Vector3, end: THREE.Vector3, startTime: number }) {
  const lineRef = useRef<any>(null)

  const points = useMemo(() => {
    const pts: [number, number, number][] = []
    for (let i = 0; i <= 10; i++) {
      const t = i / 10
      const p = start.clone().lerp(end, t)
      pts.push([p.x, p.y, p.z])
    }
    return pts
  }, [start, end])

  useFrame((state) => {
    const elapsed = state.clock.elapsedTime - startTime
    if (lineRef.current) {
      const mat = lineRef.current.material
      mat.opacity = Math.max(0, 1 - elapsed)
    }
  })

  return (
    <Line
      ref={lineRef}
      points={points}
      color="#ffffff"
      lineWidth={2}
      transparent
      opacity={1}
    />
  )
}

// =============================================================================
// SOLAR FLARES
// =============================================================================

function SolarFlares({ vixValue = 15, paused }: { vixValue?: number, paused: boolean }) {
  const [flares, setFlares] = useState<Array<{
    id: number
    angle: number
    startTime: number
    intensity: number
  }>>([])
  const nextId = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Higher VIX = more flares
    const flareChance = 0.002 + (vixValue / 100) * 0.01
    if (Math.random() < flareChance) {
      setFlares(prev => [...prev, {
        id: nextId.current++,
        angle: Math.random() * Math.PI * 2,
        startTime: t,
        intensity: 0.5 + Math.random() * 0.5
      }])
    }

    // Clean up
    setFlares(prev => prev.filter(f => t - f.startTime < 2))
  })

  return (
    <group>
      {flares.map(flare => (
        <SolarFlare key={flare.id} angle={flare.angle} startTime={flare.startTime} intensity={flare.intensity} />
      ))}
    </group>
  )
}

function SolarFlare({ angle, startTime, intensity }: { angle: number, startTime: number, intensity: number }) {
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const elapsed = state.clock.elapsedTime - startTime
    const progress = elapsed / 2

    if (meshRef.current) {
      const scale = intensity * (1 + progress * 3) * (1 - progress)
      meshRef.current.scale.set(0.3, scale * 3, 0.3)
      meshRef.current.position.set(
        Math.cos(angle) * (1.5 + progress * 2),
        Math.sin(angle) * (1.5 + progress * 2),
        0
      )
      meshRef.current.rotation.z = angle - Math.PI / 2
      const mat = meshRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = 0.8 * (1 - progress)
    }
  })

  return (
    <mesh ref={meshRef}>
      <coneGeometry args={[1, 1, 8]} />
      <meshBasicMaterial color="#fbbf24" transparent opacity={0.8} />
    </mesh>
  )
}

// =============================================================================
// AURORA BOREALIS
// =============================================================================

function AuroraBorealis({ paused }: { paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)
  const ribbonCount = 5

  const ribbons = useMemo(() => {
    return Array.from({ length: ribbonCount }, (_, i) => ({
      yOffset: 8 + i * 1.5,
      zOffset: -20 - i * 3,
      phase: i * 0.5,
      color: i % 2 === 0 ? '#22d3ee' : '#a855f7'
    }))
  }, [])

  useFrame((state) => {
    if (paused || !groupRef.current) return
    const t = state.clock.elapsedTime
    groupRef.current.children.forEach((child, i) => {
      const mesh = child as THREE.Mesh
      mesh.position.x = Math.sin(t * 0.2 + ribbons[i].phase) * 5
      const mat = mesh.material as THREE.MeshBasicMaterial
      mat.opacity = 0.1 + Math.sin(t + ribbons[i].phase) * 0.05
    })
  })

  return (
    <group ref={groupRef}>
      {ribbons.map((ribbon, i) => (
        <mesh key={i} position={[0, ribbon.yOffset, ribbon.zOffset]} rotation={[0.2, 0, 0]}>
          <planeGeometry args={[30, 2, 20, 1]} />
          <meshBasicMaterial color={ribbon.color} transparent opacity={0.1} side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  )
}

// =============================================================================
// BLACK HOLE WARP
// =============================================================================

function BlackHoleWarp({ paused }: { paused: boolean }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const ringRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    if (meshRef.current) {
      meshRef.current.rotation.z = t * 0.3
    }
    if (ringRef.current) {
      ringRef.current.rotation.z = -t * 0.5
      ringRef.current.scale.setScalar(1 + Math.sin(t * 2) * 0.1)
    }
  })

  return (
    <group position={[15, 5, -25]}>
      {/* Event horizon */}
      <Sphere ref={meshRef} args={[1.5, 32, 32]}>
        <meshBasicMaterial color="#000000" />
      </Sphere>
      {/* Accretion disk */}
      <mesh ref={ringRef} rotation={[Math.PI / 3, 0, 0]}>
        <torusGeometry args={[2.5, 0.3, 16, 64]} />
        <meshBasicMaterial color="#f97316" transparent opacity={0.5} />
      </mesh>
      {/* Gravitational lensing ring */}
      <mesh rotation={[Math.PI / 3, 0, 0]}>
        <torusGeometry args={[3, 0.05, 8, 64]} />
        <meshBasicMaterial color="#a855f7" transparent opacity={0.3} />
      </mesh>
    </group>
  )
}

// =============================================================================
// SUPERNOVA BURST
// =============================================================================

function SupernovaBurst({ active, onComplete }: { active: boolean, onComplete: () => void }) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const coreRef = useRef<THREE.Mesh>(null)
  const count = 200
  const startTime = useRef(0)
  const [started, setStarted] = useState(false)

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => ({
      direction: new THREE.Vector3(
        (Math.random() - 0.5) * 2,
        (Math.random() - 0.5) * 2,
        (Math.random() - 0.5) * 2
      ).normalize(),
      speed: 5 + Math.random() * 15,
      color: Math.random() > 0.5 ? '#fbbf24' : '#ef4444'
    }))
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    if (!active) return

    if (!started) {
      startTime.current = state.clock.elapsedTime
      setStarted(true)
    }

    const elapsed = state.clock.elapsedTime - startTime.current
    if (elapsed > 3) {
      onComplete()
      setStarted(false)
      return
    }

    const progress = elapsed / 3

    // Core flash
    if (coreRef.current) {
      coreRef.current.scale.setScalar(3 * (1 - progress))
      const mat = coreRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = 1 - progress
    }

    // Expanding particles
    particles.forEach((p, i) => {
      const dist = p.speed * elapsed
      const pos = p.direction.clone().multiplyScalar(dist)

      dummy.position.copy(pos)
      dummy.scale.setScalar(0.1 * (1 - progress * 0.5))
      dummy.updateMatrix()
      meshRef.current?.setMatrixAt(i, dummy.matrix)
    })
    if (meshRef.current) {
      meshRef.current.instanceMatrix.needsUpdate = true
    }
  })

  if (!active) return null

  return (
    <group>
      <Sphere ref={coreRef} args={[1, 32, 32]}>
        <meshBasicMaterial color="#ffffff" transparent opacity={1} />
      </Sphere>
      <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
        <sphereGeometry args={[1, 6, 6]} />
        <meshBasicMaterial color="#fbbf24" transparent opacity={0.9} />
      </instancedMesh>
    </group>
  )
}

// =============================================================================
// HOLOGRAPHIC TICKER TAPE
// =============================================================================

function HolographicTickerTape({ stockPrices }: { stockPrices: Array<{ symbol: string, price: number, change: number }> }) {
  const groupRef = useRef<THREE.Group>(null)

  const tickers = useMemo(() => {
    return stockPrices.map((stock, i) => ({
      ...stock,
      angle: (i / stockPrices.length) * Math.PI * 2,
    }))
  }, [stockPrices])

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.1
    }
  })

  return (
    <group ref={groupRef} position={[0, 2, 0]}>
      {tickers.map((ticker, i) => {
        const angle = ticker.angle
        const radius = 7
        const x = Math.cos(angle) * radius
        const z = Math.sin(angle) * radius
        const isPositive = ticker.change >= 0

        return (
          <group key={i} position={[x, 0, z]} rotation={[0, -angle + Math.PI / 2, 0]}>
            <Html center>
              <div className="bg-black/60 border border-cyan-500/30 rounded px-2 py-0.5 whitespace-nowrap text-xs">
                <span className="text-cyan-400 font-bold">{ticker.symbol}</span>
                <span className="text-white ml-1">${ticker.price.toFixed(2)}</span>
                <span className={`ml-1 ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                  {isPositive ? '▲' : '▼'}
                </span>
              </div>
            </Html>
          </group>
        )
      })}
    </group>
  )
}

// =============================================================================
// FLOATING P&L ORB (Replaces bottom P&L)
// =============================================================================

function FloatingPnLOrb({ pnlValue = 0, pnlPercent = 0 }: { pnlValue?: number, pnlPercent?: number }) {
  const groupRef = useRef<THREE.Group>(null)
  const orbRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)

  const isPositive = pnlValue >= 0
  const orbColor = isPositive ? '#22c55e' : '#ef4444'
  const orbScale = 0.4 + Math.min(Math.abs(pnlPercent) / 20, 0.6)

  useFrame((state) => {
    const t = state.clock.elapsedTime

    if (groupRef.current) {
      groupRef.current.position.y = -2 + Math.sin(t * 0.5) * 0.3
      groupRef.current.position.x = -5 + Math.sin(t * 0.3) * 0.5
    }
    if (orbRef.current) {
      orbRef.current.rotation.y = t * 0.5
    }
    if (glowRef.current) {
      glowRef.current.scale.setScalar(orbScale * (1.5 + Math.sin(t * 2) * 0.2))
      const mat = glowRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = 0.2 + Math.sin(t * 3) * 0.1
    }
  })

  return (
    <group ref={groupRef} position={[-5, -2, 2]}>
      {/* Glow */}
      <Sphere ref={glowRef} args={[1, 16, 16]}>
        <meshBasicMaterial color={orbColor} transparent opacity={0.3} />
      </Sphere>
      {/* Core orb */}
      <Sphere ref={orbRef} args={[orbScale, 32, 32]}>
        <MeshDistortMaterial
          color={orbColor}
          emissive={orbColor}
          emissiveIntensity={1}
          distort={0.3}
          speed={2}
        />
      </Sphere>
      {/* Label */}
      <Html position={[0, orbScale + 0.8, 0]} center>
        <div className="text-center select-none">
          <div className="text-gray-400 text-xs">P&L</div>
          <div className={`text-lg font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isPositive ? '+' : ''}{pnlPercent.toFixed(2)}%
          </div>
          <div className={`text-sm ${isPositive ? 'text-green-300' : 'text-red-300'}`}>
            {isPositive ? '+' : ''}${Math.abs(pnlValue).toLocaleString()}
          </div>
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// ROCKET LAUNCHES
// =============================================================================

function RocketLaunches({ botStatus }: { botStatus: BotStatus }) {
  const [rockets, setRockets] = useState<Array<{
    id: number
    startPos: THREE.Vector3
    startTime: number
  }>>([])
  const nextId = useRef(0)
  const prevStatus = useRef<BotStatus>({})

  useFrame((state) => {
    const t = state.clock.elapsedTime

    // Check for status changes to 'trading'
    BOT_NODES.forEach(node => {
      const currentStatus = botStatus[node.id as keyof BotStatus]
      const prevNodeStatus = prevStatus.current[node.id as keyof BotStatus]

      if (currentStatus === 'trading' && prevNodeStatus !== 'trading') {
        const radius = 5
        setRockets(prev => [...prev, {
          id: nextId.current++,
          startPos: new THREE.Vector3(
            Math.cos(node.angle) * radius,
            0,
            Math.sin(node.angle) * radius
          ),
          startTime: t
        }])
      }
    })
    prevStatus.current = { ...botStatus }

    // Clean up old rockets
    setRockets(prev => prev.filter(r => t - r.startTime < 3))
  })

  return (
    <group>
      {rockets.map(rocket => (
        <Rocket key={rocket.id} startPos={rocket.startPos} startTime={rocket.startTime} />
      ))}
    </group>
  )
}

function Rocket({ startPos, startTime }: { startPos: THREE.Vector3, startTime: number }) {
  const groupRef = useRef<THREE.Group>(null)
  const flameRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const elapsed = state.clock.elapsedTime - startTime
    const y = startPos.y + elapsed * 5

    if (groupRef.current) {
      groupRef.current.position.set(startPos.x, y, startPos.z)
    }
    if (flameRef.current) {
      flameRef.current.scale.y = 0.5 + Math.sin(elapsed * 20) * 0.2
    }
  })

  return (
    <group ref={groupRef}>
      {/* Rocket body */}
      <mesh>
        <cylinderGeometry args={[0.05, 0.08, 0.3, 8]} />
        <meshBasicMaterial color="#e5e7eb" />
      </mesh>
      {/* Rocket nose */}
      <mesh position={[0, 0.2, 0]}>
        <coneGeometry args={[0.05, 0.1, 8]} />
        <meshBasicMaterial color="#ef4444" />
      </mesh>
      {/* Flame */}
      <mesh ref={flameRef} position={[0, -0.25, 0]} rotation={[Math.PI, 0, 0]}>
        <coneGeometry args={[0.06, 0.3, 8]} />
        <meshBasicMaterial color="#f97316" transparent opacity={0.8} />
      </mesh>
    </group>
  )
}

// =============================================================================
// SATELLITE ORBITERS
// =============================================================================

function SatelliteOrbiters() {
  const count = 3
  const groupRef = useRef<THREE.Group>(null)

  const satellites = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      radius: 8 + i * 2,
      speed: 0.15 - i * 0.03,
      inclination: (i * 30) * (Math.PI / 180),
      phase: (i / count) * Math.PI * 2
    }))
  }, [])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (groupRef.current) {
      groupRef.current.children.forEach((sat, i) => {
        const s = satellites[i]
        const angle = s.phase + t * s.speed
        sat.position.set(
          Math.cos(angle) * s.radius,
          Math.sin(s.inclination) * Math.sin(angle) * 2,
          Math.sin(angle) * s.radius
        )
        sat.rotation.y = angle
      })
    }
  })

  return (
    <group ref={groupRef}>
      {satellites.map((_, i) => (
        <group key={i}>
          {/* Satellite body */}
          <mesh>
            <boxGeometry args={[0.15, 0.1, 0.1]} />
            <meshBasicMaterial color="#9ca3af" />
          </mesh>
          {/* Solar panels */}
          <mesh position={[0.2, 0, 0]}>
            <boxGeometry args={[0.2, 0.01, 0.15]} />
            <meshBasicMaterial color="#3b82f6" />
          </mesh>
          <mesh position={[-0.2, 0, 0]}>
            <boxGeometry args={[0.2, 0.01, 0.15]} />
            <meshBasicMaterial color="#3b82f6" />
          </mesh>
          {/* Antenna */}
          <mesh position={[0, 0.1, 0]}>
            <cylinderGeometry args={[0.01, 0.01, 0.1, 8]} />
            <meshBasicMaterial color="#d1d5db" />
          </mesh>
        </group>
      ))}
    </group>
  )
}

// =============================================================================
// ENERGY SHIELDS
// =============================================================================

function EnergyShields({ paused }: { paused: boolean }) {
  const shield1Ref = useRef<THREE.Mesh>(null)
  const shield2Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    if (shield1Ref.current) {
      shield1Ref.current.rotation.y = t * 0.2
      shield1Ref.current.rotation.x = Math.sin(t * 0.5) * 0.1
      const mat = shield1Ref.current.material as THREE.MeshBasicMaterial
      mat.opacity = 0.05 + Math.sin(t * 2) * 0.02
    }
    if (shield2Ref.current) {
      shield2Ref.current.rotation.y = -t * 0.15
      shield2Ref.current.rotation.z = Math.cos(t * 0.3) * 0.1
      const mat = shield2Ref.current.material as THREE.MeshBasicMaterial
      mat.opacity = 0.03 + Math.sin(t * 3 + 1) * 0.02
    }
  })

  return (
    <group>
      <mesh ref={shield1Ref}>
        <icosahedronGeometry args={[4, 1]} />
        <meshBasicMaterial color={COLORS.accent} transparent opacity={0.05} wireframe />
      </mesh>
      <mesh ref={shield2Ref}>
        <icosahedronGeometry args={[4.5, 1]} />
        <meshBasicMaterial color={COLORS.fiberInner} transparent opacity={0.03} wireframe />
      </mesh>
    </group>
  )
}

// =============================================================================
// WORMHOLE PORTALS
// =============================================================================

function WormholePortals({ botStatus }: { botStatus: BotStatus }) {
  const activeCount = Object.values(botStatus).filter(s => s === 'active' || s === 'trading').length

  if (activeCount < 2) return null

  return (
    <group>
      <WormholePortal position={new THREE.Vector3(-8, 0, -5)} />
      {activeCount > 2 && <WormholePortal position={new THREE.Vector3(8, 0, -5)} />}
    </group>
  )
}

function WormholePortal({ position }: { position: THREE.Vector3 }) {
  const groupRef = useRef<THREE.Group>(null)
  const ring1Ref = useRef<THREE.Mesh>(null)
  const ring2Ref = useRef<THREE.Mesh>(null)
  const ring3Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const t = state.clock.elapsedTime

    if (groupRef.current) {
      groupRef.current.rotation.z = t * 0.5
    }
    if (ring1Ref.current) {
      ring1Ref.current.rotation.z = t * 2
      ring1Ref.current.scale.setScalar(1 + Math.sin(t * 3) * 0.1)
    }
    if (ring2Ref.current) {
      ring2Ref.current.rotation.z = -t * 1.5
    }
    if (ring3Ref.current) {
      ring3Ref.current.rotation.z = t
    }
  })

  return (
    <group ref={groupRef} position={position}>
      {/* Outer ring */}
      <mesh ref={ring1Ref}>
        <torusGeometry args={[1.2, 0.05, 8, 32]} />
        <meshBasicMaterial color="#a855f7" transparent opacity={0.6} />
      </mesh>
      {/* Middle ring */}
      <mesh ref={ring2Ref}>
        <torusGeometry args={[0.9, 0.03, 8, 32]} />
        <meshBasicMaterial color="#c084fc" transparent opacity={0.5} />
      </mesh>
      {/* Inner ring */}
      <mesh ref={ring3Ref}>
        <torusGeometry args={[0.6, 0.02, 8, 32]} />
        <meshBasicMaterial color="#e9d5ff" transparent opacity={0.4} />
      </mesh>
      {/* Center void */}
      <Sphere args={[0.4, 16, 16]}>
        <meshBasicMaterial color="#1e1b4b" />
      </Sphere>
    </group>
  )
}

// =============================================================================
// QUANTUM ENTANGLEMENT
// =============================================================================

function QuantumEntanglement({ botStatus, paused }: { botStatus: BotStatus, paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)

  const activeNodes = BOT_NODES.filter(
    node => botStatus[node.id as keyof BotStatus] === 'active' ||
            botStatus[node.id as keyof BotStatus] === 'trading'
  )

  const pairs = useMemo(() => {
    const result: Array<{ node1: typeof BOT_NODES[0], node2: typeof BOT_NODES[0] }> = []
    for (let i = 0; i < activeNodes.length; i++) {
      for (let j = i + 1; j < activeNodes.length; j++) {
        result.push({ node1: activeNodes[i], node2: activeNodes[j] })
      }
    }
    return result
  }, [activeNodes])

  useFrame((state) => {
    if (paused || !groupRef.current) return
    // Animation handled by children
  })

  return (
    <group ref={groupRef}>
      {pairs.map((pair, i) => (
        <QuantumPair key={i} node1={pair.node1} node2={pair.node2} paused={paused} />
      ))}
    </group>
  )
}

function QuantumPair({ node1, node2, paused }: { node1: typeof BOT_NODES[0], node2: typeof BOT_NODES[0], paused: boolean }) {
  const particle1Ref = useRef<THREE.Mesh>(null)
  const particle2Ref = useRef<THREE.Mesh>(null)

  const radius = 5
  const pos1 = new THREE.Vector3(Math.cos(node1.angle) * radius, 0, Math.sin(node1.angle) * radius)
  const pos2 = new THREE.Vector3(Math.cos(node2.angle) * radius, 0, Math.sin(node2.angle) * radius)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    const progress = (Math.sin(t * 2) + 1) / 2

    if (particle1Ref.current) {
      const p = pos1.clone().lerp(pos2, progress)
      particle1Ref.current.position.copy(p)
      particle1Ref.current.position.y = Math.sin(t * 5) * 0.3
    }
    if (particle2Ref.current) {
      const p = pos2.clone().lerp(pos1, progress)
      particle2Ref.current.position.copy(p)
      particle2Ref.current.position.y = -Math.sin(t * 5) * 0.3
    }
  })

  return (
    <group>
      <Sphere ref={particle1Ref} args={[0.08, 8, 8]}>
        <meshBasicMaterial color="#22d3ee" />
      </Sphere>
      <Sphere ref={particle2Ref} args={[0.08, 8, 8]}>
        <meshBasicMaterial color="#a855f7" />
      </Sphere>
    </group>
  )
}

// =============================================================================
// BINARY STAR (SPX Core)
// =============================================================================

function BinaryStar({ paused }: { paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)
  const star1Ref = useRef<THREE.Group>(null)
  const star2Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    if (groupRef.current) {
      groupRef.current.rotation.y = t * 0.1
    }

    const orbitRadius = 3
    if (star1Ref.current) {
      star1Ref.current.position.x = Math.cos(t * 0.3) * orbitRadius
      star1Ref.current.position.z = Math.sin(t * 0.3) * orbitRadius
      star1Ref.current.rotation.y = t * 0.5
    }
    if (star2Ref.current) {
      star2Ref.current.position.x = Math.cos(t * 0.3 + Math.PI) * orbitRadius
      star2Ref.current.position.z = Math.sin(t * 0.3 + Math.PI) * orbitRadius
      star2Ref.current.rotation.y = -t * 0.4
    }
  })

  return (
    <group ref={groupRef} position={[-12, 3, -8]}>
      {/* SPX Star (smaller, purple) */}
      <group ref={star1Ref}>
        <Sphere args={[0.5, 32, 32]}>
          <MeshDistortMaterial
            color="#6b21a8"
            emissive="#a855f7"
            emissiveIntensity={1.5}
            distort={0.2}
            speed={2}
          />
        </Sphere>
        <Html position={[0, 0.8, 0]} center>
          <div className="text-purple-400 text-xs font-bold bg-black/50 px-1 rounded">SPX</div>
        </Html>
      </group>
      {/* SPY Star (reference from main core) */}
      <Sphere ref={star2Ref} args={[0.3, 16, 16]}>
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.6} />
      </Sphere>
      {/* Connection line */}
      <Line
        points={[[0, 0, 0], [0, 0, 0]]}
        color="#a855f7"
        lineWidth={0.5}
        transparent
        opacity={0.3}
      />
    </group>
  )
}

// =============================================================================
// SPACE STATION
// =============================================================================

function SpaceStation({ spotPrice, gexValue, vixValue }: { spotPrice?: number, gexValue?: number, vixValue?: number }) {
  const groupRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.05
      groupRef.current.position.y = 6 + Math.sin(state.clock.elapsedTime * 0.2) * 0.3
    }
  })

  return (
    <group ref={groupRef} position={[10, 6, -5]}>
      {/* Central hub */}
      <mesh>
        <cylinderGeometry args={[0.3, 0.3, 0.8, 16]} />
        <meshBasicMaterial color="#6b7280" />
      </mesh>
      {/* Solar array 1 */}
      <mesh position={[0.8, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
        <boxGeometry args={[0.05, 1, 0.4]} />
        <meshBasicMaterial color="#3b82f6" />
      </mesh>
      {/* Solar array 2 */}
      <mesh position={[-0.8, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
        <boxGeometry args={[0.05, 1, 0.4]} />
        <meshBasicMaterial color="#3b82f6" />
      </mesh>
      {/* Modules */}
      <mesh position={[0, 0.5, 0]}>
        <boxGeometry args={[0.2, 0.3, 0.2]} />
        <meshBasicMaterial color="#9ca3af" />
      </mesh>
      {/* Info panel */}
      <Html position={[0, 1.2, 0]} center>
        <div className="bg-black/80 border border-cyan-500/40 rounded-lg px-3 py-2 text-xs">
          <div className="text-cyan-400 font-bold mb-1">ALPHAGEX STATION</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
            <span className="text-gray-400">Status:</span>
            <span className="text-green-400">ONLINE</span>
            <span className="text-gray-400">Orbit:</span>
            <span className="text-white">LEO</span>
          </div>
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// MOON PHASES
// =============================================================================

function MoonPhases({ paused }: { paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)
  const moonRef = useRef<THREE.Mesh>(null)
  const shadowRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    if (groupRef.current) {
      // Orbit around scene
      groupRef.current.position.x = Math.cos(t * 0.02) * 18
      groupRef.current.position.z = Math.sin(t * 0.02) * 18
      groupRef.current.position.y = 8 + Math.sin(t * 0.05) * 2
    }

    if (moonRef.current) {
      moonRef.current.rotation.y = t * 0.05
    }

    if (shadowRef.current) {
      // Simulate moon phase with shadow position
      const phase = (t * 0.02) % (Math.PI * 2)
      shadowRef.current.position.x = Math.cos(phase) * 0.5
      shadowRef.current.rotation.y = phase
    }
  })

  return (
    <group ref={groupRef}>
      {/* Moon surface */}
      <Sphere ref={moonRef} args={[1, 32, 32]}>
        <meshBasicMaterial color="#d1d5db" />
      </Sphere>
      {/* Shadow for phase effect */}
      <Sphere ref={shadowRef} args={[1.01, 32, 32]}>
        <meshBasicMaterial color="#1f2937" transparent opacity={0.7} side={THREE.BackSide} />
      </Sphere>
      {/* Craters (simplified) */}
      <Sphere args={[0.15, 8, 8]} position={[0.3, 0.5, 0.7]}>
        <meshBasicMaterial color="#9ca3af" />
      </Sphere>
      <Sphere args={[0.1, 8, 8]} position={[-0.4, 0.2, 0.8]}>
        <meshBasicMaterial color="#9ca3af" />
      </Sphere>
      {/* Label */}
      <Html position={[0, 1.5, 0]} center>
        <div className="text-gray-400 text-xs bg-black/50 px-2 py-0.5 rounded">
          MARKET MOON
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// NEBULA STORM
// =============================================================================

function NebulaStorm({ vixValue = 15, paused }: { vixValue?: number, paused: boolean }) {
  const cloud1Ref = useRef<THREE.Mesh>(null)
  const cloud2Ref = useRef<THREE.Mesh>(null)
  const cloud3Ref = useRef<THREE.Mesh>(null)

  // Higher VIX = more turbulent nebula
  const turbulence = 0.5 + (vixValue / 50)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    if (cloud1Ref.current) {
      cloud1Ref.current.rotation.x = t * 0.02 * turbulence
      cloud1Ref.current.rotation.y = t * 0.015 * turbulence
      cloud1Ref.current.scale.setScalar(1 + Math.sin(t * turbulence) * 0.1)
    }
    if (cloud2Ref.current) {
      cloud2Ref.current.rotation.x = -t * 0.018 * turbulence
      cloud2Ref.current.rotation.z = t * 0.012 * turbulence
    }
    if (cloud3Ref.current) {
      cloud3Ref.current.rotation.y = t * 0.01 * turbulence
      cloud3Ref.current.rotation.z = -t * 0.02 * turbulence
    }
  })

  const stormColor = vixValue > 30 ? '#7f1d1d' : vixValue > 20 ? '#713f12' : '#1e3a8a'

  return (
    <group>
      <Sphere ref={cloud1Ref} args={[40, 16, 16]} position={[20, 10, -35]}>
        <MeshDistortMaterial
          color={stormColor}
          transparent
          opacity={0.04}
          distort={0.4 * turbulence}
          speed={turbulence}
        />
      </Sphere>
      <Sphere ref={cloud2Ref} args={[35, 16, 16]} position={[-25, -5, -40]}>
        <MeshDistortMaterial
          color={COLORS.nebula2}
          transparent
          opacity={0.03}
          distort={0.3 * turbulence}
          speed={turbulence * 0.8}
        />
      </Sphere>
      <Sphere ref={cloud3Ref} args={[30, 16, 16]} position={[0, -15, -45]}>
        <MeshDistortMaterial
          color={COLORS.nebula1}
          transparent
          opacity={0.025}
          distort={0.35 * turbulence}
          speed={turbulence * 0.6}
        />
      </Sphere>
    </group>
  )
}

// =============================================================================
// SUN FLARE EFFECTS - Unique flare types for each solar system
// =============================================================================

type FlareType = 'wisdom' | 'pulse' | 'mystic' | 'eruption' | 'network'

function SunFlareEffect({ flareType, color, paused }: { flareType: FlareType, color: string, paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)

  // Wisdom: Golden radiating light rays
  const WisdomFlare = () => {
    const raysRef = useRef<THREE.Group>(null)
    const rayCount = 12

    useFrame((state) => {
      if (paused || !raysRef.current) return
      const t = state.clock.elapsedTime
      raysRef.current.rotation.z = t * 0.1
      raysRef.current.children.forEach((ray, i) => {
        const mesh = ray as THREE.Mesh
        const scale = 1 + Math.sin(t * 2 + i * 0.5) * 0.3
        mesh.scale.y = scale
        ;(mesh.material as THREE.MeshBasicMaterial).opacity = 0.3 + Math.sin(t * 3 + i) * 0.2
      })
    })

    return (
      <group ref={raysRef}>
        {Array.from({ length: rayCount }).map((_, i) => {
          const angle = (i / rayCount) * Math.PI * 2
          return (
            <mesh key={i} rotation={[0, 0, angle]} position={[0, 0, 0]}>
              <planeGeometry args={[0.15, 3]} />
              <meshBasicMaterial color={color} transparent opacity={0.4} side={THREE.DoubleSide} />
            </mesh>
          )
        })}
      </group>
    )
  }

  // Pulse: Expanding scanner rings
  const PulseFlare = () => {
    const ringsRef = useRef<THREE.Group>(null)
    const [rings] = useState<number[]>([0, 0.33, 0.66])

    useFrame((state) => {
      if (paused || !ringsRef.current) return
      const t = state.clock.elapsedTime

      ringsRef.current.children.forEach((ring, i) => {
        const mesh = ring as THREE.Mesh
        const phase = (t * 0.5 + i * 0.33) % 1
        const scale = 0.5 + phase * 2
        mesh.scale.setScalar(scale)
        ;(mesh.material as THREE.MeshBasicMaterial).opacity = 0.6 * (1 - phase)
      })
    })

    return (
      <group ref={ringsRef}>
        {rings.map((_, i) => (
          <mesh key={i} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[1.5, 0.04, 8, 32]} />
            <meshBasicMaterial color={color} transparent opacity={0.5} />
          </mesh>
        ))}
      </group>
    )
  }

  // Mystic: Swirling energy spirals
  const MysticFlare = () => {
    const spiralsRef = useRef<THREE.Group>(null)

    useFrame((state) => {
      if (paused || !spiralsRef.current) return
      const t = state.clock.elapsedTime
      spiralsRef.current.rotation.y = t * 0.5
      spiralsRef.current.rotation.x = Math.sin(t * 0.3) * 0.2
    })

    const spiralPoints = useMemo(() => {
      const points: [number, number, number][] = []
      for (let i = 0; i < 50; i++) {
        const angle = (i / 50) * Math.PI * 4
        const r = 0.8 + (i / 50) * 1.5
        const y = (i / 50) * 1 - 0.5
        points.push([Math.cos(angle) * r, y, Math.sin(angle) * r])
      }
      return points
    }, [])

    return (
      <group ref={spiralsRef}>
        <Line points={spiralPoints} color={color} lineWidth={3} transparent opacity={0.6} />
        <Line
          points={spiralPoints.map(([x, y, z]) => [-x, -y, -z])}
          color={color}
          lineWidth={3}
          transparent
          opacity={0.6}
        />
        {/* Floating mystical orbs */}
        {[0, 1, 2].map(i => {
          const angle = (i / 3) * Math.PI * 2
          return (
            <Sphere key={i} args={[0.15, 8, 8]} position={[Math.cos(angle) * 1.5, 0, Math.sin(angle) * 1.5]}>
              <meshBasicMaterial color="#ffffff" />
            </Sphere>
          )
        })}
      </group>
    )
  }

  // Eruption: Explosive solar flares shooting outward
  const EruptionFlare = () => {
    const flaresRef = useRef<THREE.Group>(null)
    const flareCount = 6

    useFrame((state) => {
      if (paused || !flaresRef.current) return
      const t = state.clock.elapsedTime

      flaresRef.current.children.forEach((flare, i) => {
        const group = flare as THREE.Group
        const phase = (t * 0.8 + i * 0.3) % 2

        if (phase < 1) {
          // Erupting outward
          const scale = phase
          group.scale.setScalar(scale)
          group.position.y = phase * 1.2
          group.children.forEach(child => {
            const mesh = child as THREE.Mesh
            if (mesh.material) {
              ;(mesh.material as THREE.MeshBasicMaterial).opacity = 0.8 * (1 - phase)
            }
          })
        } else {
          group.scale.setScalar(0)
        }
      })
    })

    return (
      <group ref={flaresRef}>
        {Array.from({ length: flareCount }).map((_, i) => {
          const angle = (i / flareCount) * Math.PI * 2
          return (
            <group key={i} rotation={[0, 0, angle - Math.PI / 2]}>
              <mesh>
                <coneGeometry args={[0.3, 1.2, 6]} />
                <meshBasicMaterial color={color} transparent opacity={0.7} />
              </mesh>
              <Sphere args={[0.18, 8, 8]} position={[0, 0.8, 0]}>
                <meshBasicMaterial color="#ffffff" transparent opacity={0.8} />
              </Sphere>
            </group>
          )
        })}
      </group>
    )
  }

  // Network: Grid-like connection beams
  const NetworkFlare = () => {
    const nodesRef = useRef<THREE.Group>(null)
    const nodes = useMemo(() => {
      const n: [number, number, number][] = []
      for (let i = 0; i < 8; i++) {
        const angle = (i / 8) * Math.PI * 2
        const r = 1.5 + Math.random() * 0.8
        n.push([Math.cos(angle) * r, (Math.random() - 0.5) * 1.2, Math.sin(angle) * r])
      }
      return n
    }, [])

    useFrame((state) => {
      if (paused || !nodesRef.current) return
      const t = state.clock.elapsedTime
      nodesRef.current.rotation.y = t * 0.2

      // Pulse the connection lines
      nodesRef.current.children.forEach((child, i) => {
        if (child.type === 'Line2') {
          const line = child as any
          if (line.material) {
            line.material.opacity = 0.3 + Math.sin(t * 3 + i) * 0.2
          }
        }
      })
    })

    // Generate connections between nodes
    const connections = useMemo(() => {
      const conns: [[number, number, number], [number, number, number]][] = []
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          if ((i + j) % 2 === 0) { // Deterministic instead of random
            conns.push([nodes[i], nodes[j]])
          }
        }
      }
      return conns
    }, [nodes])

    return (
      <group ref={nodesRef}>
        {/* Connection lines */}
        {connections.map((conn, i) => (
          <Line key={`conn-${i}`} points={conn} color={color} lineWidth={1} transparent opacity={0.4} />
        ))}
        {/* Network nodes */}
        {nodes.map((pos, i) => (
          <group key={i} position={pos}>
            <Sphere args={[0.12, 8, 8]}>
              <meshBasicMaterial color={color} />
            </Sphere>
            <Sphere args={[0.2, 8, 8]}>
              <meshBasicMaterial color={color} transparent opacity={0.3} />
            </Sphere>
          </group>
        ))}
      </group>
    )
  }

  return (
    <group ref={groupRef}>
      {flareType === 'wisdom' && <WisdomFlare />}
      {flareType === 'pulse' && <PulseFlare />}
      {flareType === 'mystic' && <MysticFlare />}
      {flareType === 'eruption' && <EruptionFlare />}
      {flareType === 'network' && <NetworkFlare />}
    </group>
  )
}

// =============================================================================
// PLANET EFFECTS - Unique orbiting effects for each planet
// =============================================================================

type PlanetEffect = 'rings' | 'crystals' | 'aura' | 'fire' | 'electric' | 'spiral' | 'glow' | 'orbit_rings' | 'pulse' | 'dust' | 'data_stream' | 'hexagon' | 'heartbeat' | 'binary' | 'connections'

function PlanetEffectComponent({ effect, color, size, paused }: { effect: PlanetEffect, color: string, size: number, paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (paused || !groupRef.current) return
    const t = state.clock.elapsedTime

    // Apply effects based on type
    switch (effect) {
      case 'pulse':
      case 'heartbeat':
        const pulseScale = 1 + Math.sin(t * (effect === 'heartbeat' ? 6 : 3)) * 0.15
        groupRef.current.scale.setScalar(pulseScale)
        break
      case 'spiral':
        groupRef.current.rotation.y = t * 2
        break
    }
  })

  const renderEffect = () => {
    switch (effect) {
      case 'rings':
        // Saturn-like rings
        return (
          <>
            <mesh rotation={[Math.PI / 3, 0, 0]}>
              <torusGeometry args={[size * 2.2, size * 0.15, 2, 32]} />
              <meshBasicMaterial color={color} transparent opacity={0.5} />
            </mesh>
            <mesh rotation={[Math.PI / 3, 0, 0]}>
              <torusGeometry args={[size * 2.8, size * 0.1, 2, 32]} />
              <meshBasicMaterial color={color} transparent opacity={0.3} />
            </mesh>
          </>
        )

      case 'crystals':
        // Floating crystal shards
        return (
          <>
            {[0, 1, 2, 3, 4].map(i => {
              const angle = (i / 5) * Math.PI * 2
              const dist = size * 2
              return (
                <mesh
                  key={i}
                  position={[Math.cos(angle) * dist, Math.sin(i) * size * 0.5, Math.sin(angle) * dist]}
                  rotation={[i * 0.5, i * 0.3, i * 0.7]}
                >
                  <octahedronGeometry args={[size * 0.3]} />
                  <meshBasicMaterial color={color} transparent opacity={0.7} />
                </mesh>
              )
            })}
          </>
        )

      case 'aura':
        // Glowing energy aura
        return (
          <>
            <Sphere args={[size * 1.8, 16, 16]}>
              <meshBasicMaterial color={color} transparent opacity={0.15} />
            </Sphere>
            <Sphere args={[size * 2.5, 16, 16]}>
              <meshBasicMaterial color={color} transparent opacity={0.08} />
            </Sphere>
          </>
        )

      case 'fire':
        // Fire/plasma particles
        return (
          <>
            {[0, 1, 2, 3, 4, 5].map(i => (
              <Sphere
                key={i}
                args={[size * 0.25, 8, 8]}
                position={[
                  Math.sin(i * 1.1) * size * 1.5,
                  Math.cos(i * 0.9) * size * 1.2,
                  Math.sin(i * 1.3) * size * 1.4
                ]}
              >
                <meshBasicMaterial color="#ff6b35" transparent opacity={0.6} />
              </Sphere>
            ))}
            <Sphere args={[size * 1.5, 8, 8]}>
              <meshBasicMaterial color="#ff4500" transparent opacity={0.2} />
            </Sphere>
          </>
        )

      case 'electric':
        // Electric sparks
        return (
          <>
            {[0, 1, 2].map(i => {
              const angle = (i / 3) * Math.PI * 2
              const points: [number, number, number][] = [
                [0, 0, 0],
                [Math.cos(angle) * size * 1.5, Math.sin(i) * size * 0.5, Math.sin(angle) * size * 1.5],
                [Math.cos(angle + 0.3) * size * 2.5, Math.sin(i + 1) * size * 0.3, Math.sin(angle + 0.3) * size * 2.5]
              ]
              return <Line key={i} points={points} color="#00ffff" lineWidth={2} transparent opacity={0.7} />
            })}
          </>
        )

      case 'spiral':
        // Spiral trail
        const spiralPts: [number, number, number][] = []
        for (let i = 0; i < 30; i++) {
          const angle = (i / 30) * Math.PI * 3
          const r = size * (1.2 + (i / 30) * 0.8)
          spiralPts.push([Math.cos(angle) * r, (i / 30) * size * 0.5, Math.sin(angle) * r])
        }
        return <Line points={spiralPts} color={color} lineWidth={2} transparent opacity={0.5} />

      case 'glow':
        // Enhanced glow
        return (
          <Sphere args={[size * 2, 16, 16]}>
            <meshBasicMaterial color={color} transparent opacity={0.25} />
          </Sphere>
        )

      case 'orbit_rings':
        // Multiple small orbit rings
        return (
          <>
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[size * 1.8, 0.02, 8, 32]} />
              <meshBasicMaterial color={color} transparent opacity={0.4} />
            </mesh>
            <mesh rotation={[Math.PI / 3, Math.PI / 4, 0]}>
              <torusGeometry args={[size * 2.2, 0.02, 8, 32]} />
              <meshBasicMaterial color={color} transparent opacity={0.3} />
            </mesh>
            <mesh rotation={[Math.PI / 4, -Math.PI / 3, 0]}>
              <torusGeometry args={[size * 2.6, 0.02, 8, 32]} />
              <meshBasicMaterial color={color} transparent opacity={0.2} />
            </mesh>
          </>
        )

      case 'dust':
        // Dust cloud
        return (
          <>
            {Array.from({ length: 20 }).map((_, i) => {
              const angle = (i / 20) * Math.PI * 2
              const r = size * (1.5 + (i % 3) * 0.5)
              return (
                <Sphere
                  key={i}
                  args={[size * 0.08, 4, 4]}
                  position={[Math.cos(angle) * r, (i % 5 - 2) * size * 0.2, Math.sin(angle) * r]}
                >
                  <meshBasicMaterial color="#9ca3af" transparent opacity={0.4} />
                </Sphere>
              )
            })}
          </>
        )

      case 'data_stream':
        // Digital data particles flowing
        return (
          <>
            <Line
              points={[[0, -size * 2, 0], [0, size * 2, 0]]}
              color="#3b82f6"
              lineWidth={1}
              transparent
              opacity={0.5}
            />
            <Sphere args={[size * 0.15, 8, 8]} position={[0, size * 1.5, 0]}>
              <meshBasicMaterial color="#60a5fa" />
            </Sphere>
            <Sphere args={[size * 0.12, 8, 8]} position={[0, -size * 1.2, 0]}>
              <meshBasicMaterial color="#3b82f6" />
            </Sphere>
          </>
        )

      case 'hexagon':
        // Hexagonal shield pattern
        return (
          <mesh rotation={[0, 0, 0]}>
            <torusGeometry args={[size * 2, size * 0.08, 6, 6]} />
            <meshBasicMaterial color={color} transparent opacity={0.4} wireframe />
          </mesh>
        )

      case 'binary':
        // Binary data particles
        return (
          <>
            {Array.from({ length: 12 }).map((_, i) => {
              const angle = (i / 12) * Math.PI * 2
              const r = size * 2
              return (
                <Sphere
                  key={i}
                  args={[size * 0.08, 4, 4]}
                  position={[Math.cos(angle) * r, (i % 3 - 1) * size * 0.3, Math.sin(angle) * r]}
                >
                  <meshBasicMaterial color={i % 2 === 0 ? '#22c55e' : '#3b82f6'} />
                </Sphere>
              )
            })}
          </>
        )

      case 'connections':
        // Network connections
        return (
          <>
            {[0, 1, 2].map(i => {
              const angle = (i / 3) * Math.PI * 2
              const dist = size * 3
              return (
                <Line
                  key={i}
                  points={[[0, 0, 0], [Math.cos(angle) * dist, 0, Math.sin(angle) * dist]]}
                  color={color}
                  lineWidth={1}
                  transparent
                  opacity={0.4}
                />
              )
            })}
          </>
        )

      case 'heartbeat':
      case 'pulse':
      default:
        return null
    }
  }

  return <group ref={groupRef}>{renderEffect()}</group>
}

// =============================================================================
// SYSTEM AMBIENT EFFECTS - Unique ambient actions for each solar system
// =============================================================================

function SystemAmbientEffects({
  systemId,
  color,
  sunColor,
  paused
}: {
  systemId: string
  color: string
  sunColor: string
  paused: boolean
}) {
  switch (systemId) {
    case 'solomon':
      return <SolomonEffects color={color} sunColor={sunColor} paused={paused} />
    case 'argus':
      return <ArgusEffects color={color} sunColor={sunColor} paused={paused} />
    case 'oracle':
      return <OracleEffects color={color} sunColor={sunColor} paused={paused} />
    case 'kronos':
      return <KronosEffects color={color} sunColor={sunColor} paused={paused} />
    case 'systems':
      return <SystemsEffects color={color} sunColor={sunColor} paused={paused} />
    default:
      return null
  }
}

// SOLOMON - Wisdom scrolls, knowledge particles, ancient symbols
function SolomonEffects({ color, sunColor, paused }: { color: string, sunColor: string, paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)
  const scrollsRef = useRef<THREE.Group>(null)
  const symbolsRef = useRef<THREE.Group>(null)

  // Floating wisdom symbols (ancient runes)
  const symbols = useMemo(() => ['◈', '◇', '△', '○', '☆', '⬡'], [])

  // Knowledge particles flowing upward
  const particleCount = 30
  const particlePositions = useMemo(() => {
    const positions = new Float32Array(particleCount * 3)
    for (let i = 0; i < particleCount; i++) {
      const angle = (i / particleCount) * Math.PI * 2
      const r = 3 + Math.random() * 2
      positions[i * 3] = Math.cos(angle) * r
      positions[i * 3 + 1] = (Math.random() - 0.5) * 4
      positions[i * 3 + 2] = Math.sin(angle) * r
    }
    return positions
  }, [])

  const particleRef = useRef<THREE.Points>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Rotate scrolls slowly
    if (scrollsRef.current) {
      scrollsRef.current.rotation.y = t * 0.15
    }

    // Orbit symbols
    if (symbolsRef.current) {
      symbolsRef.current.rotation.y = -t * 0.2
      symbolsRef.current.children.forEach((child, i) => {
        child.position.y = Math.sin(t * 0.5 + i) * 0.5
      })
    }

    // Animate particles rising
    if (particleRef.current) {
      const positions = particleRef.current.geometry.attributes.position.array as Float32Array
      for (let i = 0; i < particleCount; i++) {
        positions[i * 3 + 1] += 0.02
        if (positions[i * 3 + 1] > 4) {
          positions[i * 3 + 1] = -4
        }
      }
      particleRef.current.geometry.attributes.position.needsUpdate = true
    }
  })

  return (
    <group ref={groupRef}>
      {/* Floating ancient scrolls */}
      <group ref={scrollsRef}>
        {[0, 1, 2].map((i) => {
          const angle = (i / 3) * Math.PI * 2
          const r = 5
          return (
            <group key={i} position={[Math.cos(angle) * r, Math.sin(i * 2) * 0.5, Math.sin(angle) * r]}>
              <mesh rotation={[0, angle + Math.PI / 2, Math.PI / 6]}>
                <cylinderGeometry args={[0.15, 0.15, 1.2, 8]} />
                <meshBasicMaterial color={sunColor} transparent opacity={0.8} />
              </mesh>
              {/* Scroll paper unfurling */}
              <mesh position={[0.3, 0, 0]} rotation={[0, 0, 0]}>
                <planeGeometry args={[0.8, 1]} />
                <meshBasicMaterial color="#fef3c7" transparent opacity={0.6} side={THREE.DoubleSide} />
              </mesh>
            </group>
          )
        })}
      </group>

      {/* Orbiting wisdom symbols */}
      <group ref={symbolsRef}>
        {symbols.map((symbol, i) => {
          const angle = (i / symbols.length) * Math.PI * 2
          const r = 6.5
          return (
            <Html
              key={i}
              position={[Math.cos(angle) * r, 0, Math.sin(angle) * r]}
              center
            >
              <div
                className="text-2xl font-bold animate-pulse"
                style={{ color: sunColor, textShadow: `0 0 10px ${color}` }}
              >
                {symbol}
              </div>
            </Html>
          )
        })}
      </group>

      {/* Rising knowledge particles */}
      <points ref={particleRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={particleCount}
            array={particlePositions}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial color={sunColor} size={0.08} transparent opacity={0.6} />
      </points>

      {/* Wisdom aura rings */}
      {[0, 1, 2].map((i) => (
        <mesh key={i} rotation={[Math.PI / 2, 0, 0]} position={[0, -1 + i * 1, 0]}>
          <torusGeometry args={[4 + i * 0.5, 0.02, 8, 64]} />
          <meshBasicMaterial color={color} transparent opacity={0.2 - i * 0.05} />
        </mesh>
      ))}
    </group>
  )
}

// ARGUS - Scanning beams, surveillance drones, all-seeing eyes
function ArgusEffects({ color, sunColor, paused }: { color: string, sunColor: string, paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)
  const scannerRef = useRef<THREE.Group>(null)
  const dronesRef = useRef<THREE.Group>(null)
  const [scanAngle, setScanAngle] = useState(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Rotate scanner beam
    if (scannerRef.current) {
      scannerRef.current.rotation.y = t * 0.8
    }

    // Orbit drones
    if (dronesRef.current) {
      dronesRef.current.rotation.y = t * 0.3
      dronesRef.current.children.forEach((drone, i) => {
        const group = drone as THREE.Group
        group.rotation.y = -t * 2
        // Bob up and down
        group.position.y = Math.sin(t * 2 + i * 2) * 0.3
      })
    }

    setScanAngle(t * 0.8)
  })

  return (
    <group ref={groupRef}>
      {/* Scanning laser beams */}
      <group ref={scannerRef}>
        {[0, 1].map((i) => {
          const angle = i * Math.PI
          return (
            <group key={i} rotation={[0, angle, 0]}>
              {/* Main beam */}
              <mesh position={[4, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                <coneGeometry args={[0.05, 8, 8]} />
                <meshBasicMaterial color={color} transparent opacity={0.4} />
              </mesh>
              {/* Beam glow */}
              <mesh position={[4, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
                <coneGeometry args={[0.15, 8, 8]} />
                <meshBasicMaterial color={color} transparent opacity={0.1} />
              </mesh>
            </group>
          )
        })}
      </group>

      {/* Surveillance drones orbiting */}
      <group ref={dronesRef}>
        {[0, 1, 2, 3].map((i) => {
          const angle = (i / 4) * Math.PI * 2
          const r = 6
          return (
            <group key={i} position={[Math.cos(angle) * r, 0, Math.sin(angle) * r]}>
              {/* Drone body */}
              <mesh>
                <octahedronGeometry args={[0.25]} />
                <meshBasicMaterial color={sunColor} />
              </mesh>
              {/* Drone eye */}
              <Sphere args={[0.12, 8, 8]} position={[0, 0, 0.2]}>
                <meshBasicMaterial color="#ef4444" />
              </Sphere>
              {/* Drone ring */}
              <mesh rotation={[Math.PI / 2, 0, 0]}>
                <torusGeometry args={[0.4, 0.03, 8, 16]} />
                <meshBasicMaterial color={color} transparent opacity={0.5} />
              </mesh>
            </group>
          )
        })}
      </group>

      {/* All-seeing eye projections */}
      {[0, 1, 2].map((i) => {
        const angle = (i / 3) * Math.PI * 2 + Math.PI / 6
        const r = 5
        return (
          <group key={i} position={[Math.cos(angle) * r, 1.5, Math.sin(angle) * r]}>
            {/* Eye shape */}
            <mesh rotation={[0, -angle, 0]}>
              <sphereGeometry args={[0.3, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
              <meshBasicMaterial color={color} transparent opacity={0.4} side={THREE.DoubleSide} />
            </mesh>
            {/* Pupil */}
            <Sphere args={[0.1, 8, 8]}>
              <meshBasicMaterial color="#1e3a5f" />
            </Sphere>
          </group>
        )
      })}

      {/* Radar sweep effect */}
      <mesh rotation={[Math.PI / 2, 0, scanAngle]}>
        <ringGeometry args={[0.5, 7, 32, 1, 0, Math.PI / 4]} />
        <meshBasicMaterial color={color} transparent opacity={0.15} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

// ORACLE - Time portals, prophecy crystals, vision echoes
function OracleEffects({ color, sunColor, paused }: { color: string, sunColor: string, paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)
  const portalsRef = useRef<THREE.Group>(null)
  const crystalsRef = useRef<THREE.Group>(null)
  const echoesRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Spin portals
    if (portalsRef.current) {
      portalsRef.current.children.forEach((portal, i) => {
        const mesh = portal as THREE.Mesh
        mesh.rotation.z = t * (0.5 + i * 0.2)
        mesh.rotation.x = Math.sin(t * 0.3 + i) * 0.2
        // Pulse scale
        const scale = 1 + Math.sin(t * 2 + i * 2) * 0.1
        mesh.scale.setScalar(scale)
      })
    }

    // Levitate crystals
    if (crystalsRef.current) {
      crystalsRef.current.rotation.y = t * 0.1
      crystalsRef.current.children.forEach((crystal, i) => {
        const group = crystal as THREE.Group
        group.position.y = Math.sin(t + i * 1.5) * 0.5
        group.rotation.y = t * 0.5
      })
    }

    // Fade vision echoes
    if (echoesRef.current) {
      echoesRef.current.rotation.y = t * 0.05
      echoesRef.current.children.forEach((echo, i) => {
        const mesh = echo as THREE.Mesh
        const phase = (t * 0.5 + i * 0.5) % 3
        const opacity = phase < 1 ? phase * 0.3 : phase < 2 ? 0.3 : (3 - phase) * 0.3
        ;(mesh.material as THREE.MeshBasicMaterial).opacity = opacity
        mesh.scale.setScalar(0.5 + phase * 0.3)
      })
    }
  })

  return (
    <group ref={groupRef}>
      {/* Mystical portals */}
      <group ref={portalsRef}>
        {[0, 1, 2].map((i) => {
          const angle = (i / 3) * Math.PI * 2
          const r = 5.5
          return (
            <mesh
              key={i}
              position={[Math.cos(angle) * r, 0.5, Math.sin(angle) * r]}
              rotation={[Math.PI / 2, 0, 0]}
            >
              <torusGeometry args={[0.8, 0.08, 8, 32]} />
              <meshBasicMaterial color={sunColor} transparent opacity={0.7} />
            </mesh>
          )
        })}
      </group>

      {/* Prophecy crystals */}
      <group ref={crystalsRef}>
        {[0, 1, 2, 3, 4].map((i) => {
          const angle = (i / 5) * Math.PI * 2
          const r = 4.5
          return (
            <group key={i} position={[Math.cos(angle) * r, 0, Math.sin(angle) * r]}>
              <mesh rotation={[0, angle, Math.PI / 6]}>
                <octahedronGeometry args={[0.35]} />
                <meshBasicMaterial color={color} transparent opacity={0.7} />
              </mesh>
              {/* Crystal glow */}
              <Sphere args={[0.5, 8, 8]}>
                <meshBasicMaterial color={sunColor} transparent opacity={0.15} />
              </Sphere>
              {/* Inner light */}
              <Sphere args={[0.15, 8, 8]}>
                <meshBasicMaterial color="#ffffff" />
              </Sphere>
            </group>
          )
        })}
      </group>

      {/* Vision echo spheres */}
      <group ref={echoesRef}>
        {[0, 1, 2, 3, 4, 5].map((i) => {
          const angle = (i / 6) * Math.PI * 2
          const r = 7
          return (
            <Sphere
              key={i}
              args={[0.4, 16, 16]}
              position={[Math.cos(angle) * r, Math.sin(i) * 0.5, Math.sin(angle) * r]}
            >
              <meshBasicMaterial color={sunColor} transparent opacity={0.2} />
            </Sphere>
          )
        })}
      </group>

      {/* Mystical mist effect */}
      <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, -0.5, 0]}>
        <ringGeometry args={[3, 8, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.08} side={THREE.DoubleSide} />
      </mesh>

      {/* Floating tarot-like cards */}
      {[0, 1, 2].map((i) => {
        const angle = (i / 3) * Math.PI * 2 + Math.PI / 3
        const r = 6
        return (
          <mesh
            key={i}
            position={[Math.cos(angle) * r, 1, Math.sin(angle) * r]}
            rotation={[0.2, -angle, 0]}
          >
            <planeGeometry args={[0.5, 0.8]} />
            <meshBasicMaterial color={sunColor} transparent opacity={0.6} side={THREE.DoubleSide} />
          </mesh>
        )
      })}
    </group>
  )
}

// KRONOS - Clock gears, time distortion waves, hourglass particles
function KronosEffects({ color, sunColor, paused }: { color: string, sunColor: string, paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)
  const gearsRef = useRef<THREE.Group>(null)
  const hourglassRef = useRef<THREE.Group>(null)
  const distortionRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Rotate gears at different speeds
    if (gearsRef.current) {
      gearsRef.current.children.forEach((gear, i) => {
        const mesh = gear as THREE.Mesh
        mesh.rotation.z = t * (i % 2 === 0 ? 0.5 : -0.3) * (1 + i * 0.2)
      })
    }

    // Animate hourglass
    if (hourglassRef.current) {
      hourglassRef.current.rotation.y = t * 0.2
      hourglassRef.current.position.y = Math.sin(t * 0.5) * 0.3
    }

    // Pulse distortion waves outward
    if (distortionRef.current) {
      distortionRef.current.children.forEach((wave, i) => {
        const mesh = wave as THREE.Mesh
        const phase = (t * 0.3 + i * 0.5) % 2
        mesh.scale.setScalar(1 + phase * 2)
        ;(mesh.material as THREE.MeshBasicMaterial).opacity = 0.3 * (1 - phase / 2)
      })
    }
  })

  // Generate gear teeth
  const GearMesh = ({ radius, teeth, thickness }: { radius: number, teeth: number, thickness: number }) => {
    return (
      <group>
        {/* Gear body */}
        <mesh>
          <torusGeometry args={[radius, thickness, 8, 32]} />
          <meshBasicMaterial color={sunColor} transparent opacity={0.7} />
        </mesh>
        {/* Gear teeth */}
        {Array.from({ length: teeth }).map((_, i) => {
          const angle = (i / teeth) * Math.PI * 2
          return (
            <mesh
              key={i}
              position={[Math.cos(angle) * (radius + thickness * 1.5), Math.sin(angle) * (radius + thickness * 1.5), 0]}
              rotation={[0, 0, angle]}
            >
              <boxGeometry args={[thickness * 2, thickness * 3, thickness]} />
              <meshBasicMaterial color={sunColor} transparent opacity={0.7} />
            </mesh>
          )
        })}
        {/* Center hub */}
        <mesh>
          <cylinderGeometry args={[radius * 0.3, radius * 0.3, thickness * 2, 8]} />
          <meshBasicMaterial color={color} />
        </mesh>
      </group>
    )
  }

  return (
    <group ref={groupRef}>
      {/* Rotating clock gears */}
      <group ref={gearsRef}>
        {[
          { pos: [5, 0.5, 0], radius: 0.8, teeth: 12 },
          { pos: [-4, -0.3, 3], radius: 0.6, teeth: 8 },
          { pos: [2, 0.2, -5], radius: 1, teeth: 16 },
          { pos: [-3, 0.8, -4], radius: 0.5, teeth: 6 },
        ].map((gear, i) => (
          <group key={i} position={gear.pos as [number, number, number]} rotation={[Math.PI / 2, 0, 0]}>
            <GearMesh radius={gear.radius} teeth={gear.teeth} thickness={0.08} />
          </group>
        ))}
      </group>

      {/* Central hourglass */}
      <group ref={hourglassRef} position={[0, 2, 0]}>
        {/* Top cone */}
        <mesh position={[0, 0.4, 0]}>
          <coneGeometry args={[0.4, 0.8, 8]} />
          <meshBasicMaterial color={color} transparent opacity={0.5} />
        </mesh>
        {/* Bottom cone (inverted) */}
        <mesh position={[0, -0.4, 0]} rotation={[Math.PI, 0, 0]}>
          <coneGeometry args={[0.4, 0.8, 8]} />
          <meshBasicMaterial color={color} transparent opacity={0.5} />
        </mesh>
        {/* Sand particles */}
        <Sphere args={[0.08, 8, 8]} position={[0, 0, 0]}>
          <meshBasicMaterial color={sunColor} />
        </Sphere>
      </group>

      {/* Time distortion waves */}
      <group ref={distortionRef}>
        {[0, 1, 2].map((i) => (
          <mesh key={i} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[2, 0.05, 8, 64]} />
            <meshBasicMaterial color={sunColor} transparent opacity={0.2} />
          </mesh>
        ))}
      </group>

      {/* Clock hands effect */}
      <group position={[0, 0, 4.5]}>
        <Line
          points={[[0, 0, 0], [0.8, 0, 0]]}
          color={sunColor}
          lineWidth={3}
        />
        <Line
          points={[[0, 0, 0], [0, 0.5, 0]]}
          color={color}
          lineWidth={2}
        />
      </group>

      {/* Time particles flowing backward */}
      {Array.from({ length: 8 }).map((_, i) => {
        const angle = (i / 8) * Math.PI * 2
        const r = 6
        return (
          <Sphere
            key={i}
            args={[0.1, 8, 8]}
            position={[Math.cos(angle) * r, Math.sin(i * 0.5) * 0.5, Math.sin(angle) * r]}
          >
            <meshBasicMaterial color={color} transparent opacity={0.5} />
          </Sphere>
        )
      })}
    </group>
  )
}

// SYSTEMS - Server racks, network traffic, health pulses
function SystemsEffects({ color, sunColor, paused }: { color: string, sunColor: string, paused: boolean }) {
  const groupRef = useRef<THREE.Group>(null)
  const serversRef = useRef<THREE.Group>(null)
  const trafficRef = useRef<THREE.Group>(null)
  const [dataPackets, setDataPackets] = useState<Array<{ id: number, start: number, pathIndex: number }>>([])
  const nextPacketId = useRef(0)

  // Network paths between servers
  const networkPaths = useMemo(() => {
    const paths: [number, number, number][][] = []
    const serverPositions = [
      [5, 0, 0], [-4, 0, 3], [2, 0, -5], [-3, 0, -3], [4, 0, 4]
    ]
    for (let i = 0; i < serverPositions.length; i++) {
      for (let j = i + 1; j < serverPositions.length; j++) {
        paths.push([
          serverPositions[i] as [number, number, number],
          serverPositions[j] as [number, number, number]
        ])
      }
    }
    return paths
  }, [])

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Animate server lights
    if (serversRef.current) {
      serversRef.current.children.forEach((server, i) => {
        const group = server as THREE.Group
        // Blink activity lights
        group.children.forEach((child, j) => {
          if (child.type === 'Mesh' && j > 0) {
            const mesh = child as THREE.Mesh
            const blink = Math.sin(t * 10 + i + j * 2) > 0.5
            ;(mesh.material as THREE.MeshBasicMaterial).opacity = blink ? 0.9 : 0.3
          }
        })
      })
    }

    // Spawn new data packets
    if (Math.random() < 0.05) {
      setDataPackets(prev => [...prev.slice(-20), {
        id: nextPacketId.current++,
        start: t,
        pathIndex: Math.floor(Math.random() * networkPaths.length)
      }])
    }

    // Clean old packets
    setDataPackets(prev => prev.filter(p => t - p.start < 2))
  })

  return (
    <group ref={groupRef}>
      {/* Server rack towers */}
      <group ref={serversRef}>
        {[
          [5, 0, 0], [-4, 0, 3], [2, 0, -5], [-3, 0, -3], [4, 0, 4]
        ].map((pos, i) => (
          <group key={i} position={pos as [number, number, number]}>
            {/* Server tower */}
            <mesh>
              <boxGeometry args={[0.5, 1.5, 0.3]} />
              <meshBasicMaterial color="#1f2937" />
            </mesh>
            {/* Server slots/lights */}
            {[0, 1, 2, 3, 4].map((j) => (
              <mesh key={j} position={[0, -0.5 + j * 0.25, 0.16]}>
                <boxGeometry args={[0.4, 0.08, 0.02]} />
                <meshBasicMaterial color={j % 2 === 0 ? color : sunColor} transparent opacity={0.6} />
              </mesh>
            ))}
            {/* Status LED */}
            <Sphere args={[0.08, 8, 8]} position={[0.15, 0.6, 0.16]}>
              <meshBasicMaterial color="#22c55e" />
            </Sphere>
          </group>
        ))}
      </group>

      {/* Network connection lines */}
      {networkPaths.map((path, i) => (
        <Line
          key={i}
          points={path}
          color={color}
          lineWidth={1}
          transparent
          opacity={0.2}
        />
      ))}

      {/* Traveling data packets */}
      {dataPackets.map((packet) => {
        const path = networkPaths[packet.pathIndex]
        if (!path) return null
        const progress = ((Date.now() / 1000 - packet.start) / 2) % 1
        const pos = [
          path[0][0] + (path[1][0] - path[0][0]) * progress,
          path[0][1] + (path[1][1] - path[0][1]) * progress + Math.sin(progress * Math.PI) * 0.3,
          path[0][2] + (path[1][2] - path[0][2]) * progress
        ] as [number, number, number]
        return (
          <Sphere key={packet.id} args={[0.08, 8, 8]} position={pos}>
            <meshBasicMaterial color={sunColor} />
          </Sphere>
        )
      })}

      {/* Health pulse rings */}
      {[0, 1, 2].map((i) => (
        <mesh key={i} rotation={[Math.PI / 2, 0, 0]} position={[0, -0.5, 0]}>
          <torusGeometry args={[3 + i * 1.5, 0.03, 8, 64]} />
          <meshBasicMaterial color={color} transparent opacity={0.15 - i * 0.04} />
        </mesh>
      ))}

      {/* Central hub */}
      <group position={[0, 0, 0]}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.8, 0.8, 0.3, 8]} />
          <meshBasicMaterial color={sunColor} transparent opacity={0.5} />
        </mesh>
        {/* Hub lights */}
        {[0, 1, 2, 3].map((i) => {
          const angle = (i / 4) * Math.PI * 2
          return (
            <Sphere
              key={i}
              args={[0.1, 8, 8]}
              position={[Math.cos(angle) * 0.5, 0.2, Math.sin(angle) * 0.5]}
            >
              <meshBasicMaterial color={i % 2 === 0 ? '#22c55e' : '#3b82f6'} />
            </Sphere>
          )
        })}
      </group>

      {/* Binary stream effect */}
      <Html position={[6, 1.5, 0]} center>
        <div className="text-[10px] font-mono text-green-400 opacity-50">
          {'01001010'}
        </div>
      </Html>
      <Html position={[-5, 1.2, 2]} center>
        <div className="text-[10px] font-mono text-blue-400 opacity-50">
          {'11010110'}
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// SOLAR SYSTEM - Beautiful Mini Solar System with Orbiting Planets
// =============================================================================

function SolarSystem({
  system,
  paused = false,
  onPulseToSystem,
  onSystemClick,
  onPlanetClick
}: {
  system: typeof SOLAR_SYSTEMS[0]
  paused?: boolean
  onPulseToSystem?: (targetId: string) => void
  onSystemClick?: (systemId: string, position: [number, number, number]) => void
  onPlanetClick?: (planetName: string) => void
}) {
  const groupRef = useRef<THREE.Group>(null)
  const sunRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)
  const ringsRef = useRef<THREE.Group>(null)
  const [isHovered, setIsHovered] = useState(false)
  const [pulseIntensity, setPulseIntensity] = useState(0)

  // Handle click to navigate to this system
  const handleClick = useCallback(() => {
    if (onSystemClick) {
      onSystemClick(system.id, system.position)
    }
  }, [onSystemClick, system.id, system.position])

  // Pulse effect when receiving signal
  const triggerPulse = useCallback(() => {
    setPulseIntensity(1)
  }, [])

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Gentle floating motion
    if (groupRef.current) {
      groupRef.current.position.y = system.position[1] + Math.sin(t * 0.3 + system.position[0]) * 0.3
    }

    // Sun pulsing glow
    if (sunRef.current) {
      const pulse = 1 + Math.sin(t * 2) * 0.1
      sunRef.current.scale.setScalar(pulse)
    }

    // Glow breathing
    if (glowRef.current) {
      const glowPulse = 0.4 + Math.sin(t * 1.5) * 0.15 + pulseIntensity * 0.5
      ;(glowRef.current.material as THREE.MeshBasicMaterial).opacity = glowPulse
      glowRef.current.scale.setScalar(1.5 + pulseIntensity * 0.5)
    }

    // Orbital rings rotation
    if (ringsRef.current) {
      ringsRef.current.rotation.x = Math.PI / 2 + Math.sin(t * 0.2) * 0.1
      ringsRef.current.rotation.z = t * 0.05
    }

    // Decay pulse intensity
    if (pulseIntensity > 0) {
      setPulseIntensity(prev => Math.max(0, prev - 0.02))
    }
  })

  // Random pulse to other systems
  useEffect(() => {
    if (paused || !onPulseToSystem) return
    const interval = setInterval(() => {
      if (Math.random() < 0.15) { // 15% chance every interval
        const otherSystems = SOLAR_SYSTEMS.filter(s => s.id !== system.id)
        const target = otherSystems[Math.floor(Math.random() * otherSystems.length)]
        onPulseToSystem(target.id)
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [paused, system.id, onPulseToSystem])

  return (
    <group
      ref={groupRef}
      position={system.position}
      onPointerOver={() => setIsHovered(true)}
      onPointerOut={() => setIsHovered(false)}
      onClick={handleClick}
    >
      {/* Outer glow halo */}
      <Sphere ref={glowRef} args={[1.8, 32, 32]}>
        <meshBasicMaterial color={system.glowColor} transparent opacity={0.25} />
      </Sphere>

      {/* Secondary glow */}
      <Sphere args={[1.2, 32, 32]}>
        <meshBasicMaterial color={system.glowColor} transparent opacity={0.15} />
      </Sphere>

      {/* Central sun with distortion */}
      <Sphere ref={sunRef} args={[0.7, 32, 32]}>
        <MeshDistortMaterial
          color={system.sunColor}
          emissive={system.sunColor}
          emissiveIntensity={isHovered ? 2.5 : 1.5}
          distort={0.35}
          speed={3}
        />
      </Sphere>

      {/* Sun core (bright center) */}
      <Sphere args={[0.3, 16, 16]}>
        <meshBasicMaterial color="#ffffff" />
      </Sphere>

      {/* Orbital rings */}
      <group ref={ringsRef}>
        {system.planets.map((planet, i) => (
          <mesh key={i} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[planet.orbit, 0.008, 8, 64]} />
            <meshBasicMaterial color={planet.color} transparent opacity={0.3} />
          </mesh>
        ))}
      </group>

      {/* Orbiting planets */}
      {system.planets.map((planet, i) => (
        <OrbitingPlanet
          key={i}
          planet={planet}
          systemId={system.id}
          paused={paused}
          phaseOffset={i * Math.PI * 0.7}
          onPlanetClick={onPlanetClick}
        />
      ))}

      {/* Particle corona around sun */}
      <SunCorona color={system.glowColor} paused={paused} />

      {/* Unique sun flare effect */}
      <SunFlareEffect flareType={system.flareType as FlareType} color={system.glowColor} paused={paused} />

      {/* Unique system ambient effects */}
      <SystemAmbientEffects systemId={system.id} color={system.glowColor} sunColor={system.sunColor} paused={paused} />

      {/* System label */}
      <Html position={[0, 1.5, 0]} center>
        <div
          className={`text-center transition-all duration-300 ${isHovered ? 'scale-110' : 'scale-100'}`}
          style={{ opacity: isHovered ? 1 : 0.7 }}
        >
          <div
            className="text-sm font-bold tracking-wider"
            style={{ color: system.sunColor, textShadow: `0 0 10px ${system.glowColor}` }}
          >
            {system.name}
          </div>
          <div className="text-xs text-gray-400">{system.subtitle}</div>
        </div>
      </Html>

      {/* Activation ring when hovered */}
      {isHovered && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[1.2, 0.02, 16, 64]} />
          <meshBasicMaterial color={system.glowColor} transparent opacity={0.8} />
        </mesh>
      )}
    </group>
  )
}

// =============================================================================
// ORBITING PLANET with Trail, Moons, Atmosphere, and Click Navigation
// =============================================================================

function OrbitingPlanet({
  planet,
  systemId,
  paused,
  phaseOffset,
  onPlanetClick
}: {
  planet: { name: string, color: string, size: number, orbit: number, speed: number, effect?: PlanetEffect, moons?: number }
  systemId: string
  paused: boolean
  phaseOffset: number
  onPlanetClick?: (planetName: string) => void
}) {
  const groupRef = useRef<THREE.Group>(null)
  const meshRef = useRef<THREE.Mesh>(null)
  const trailRef = useRef<THREE.Points>(null)
  const atmosphereRef = useRef<THREE.Mesh>(null)
  const [isHovered, setIsHovered] = useState(false)
  const [clickPulse, setClickPulse] = useState(0)

  // Trail positions
  const trailPositions = useMemo(() => new Float32Array(30 * 3), [])
  const trailIndex = useRef(0)

  // Handle planet click
  const handleClick = useCallback((e: { stopPropagation: () => void }) => {
    e.stopPropagation()
    setClickPulse(1)
    if (onPlanetClick) {
      onPlanetClick(planet.name)
    }
  }, [onPlanetClick, planet.name])

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    const angle = t * planet.speed + phaseOffset
    const x = Math.cos(angle) * planet.orbit
    const z = Math.sin(angle) * planet.orbit
    const y = Math.sin(angle * 2) * 0.1 // Slight vertical wobble

    if (groupRef.current) {
      groupRef.current.position.set(x, y, z)
    }

    if (meshRef.current) {
      meshRef.current.rotation.y = t * 2
    }

    // Atmosphere pulse
    if (atmosphereRef.current) {
      const pulse = 1 + Math.sin(t * 3) * 0.05
      atmosphereRef.current.scale.setScalar(pulse)
    }

    // Update trail
    if (trailRef.current) {
      const idx = (trailIndex.current % 30) * 3
      trailPositions[idx] = x
      trailPositions[idx + 1] = y
      trailPositions[idx + 2] = z
      trailIndex.current++
      trailRef.current.geometry.attributes.position.needsUpdate = true
    }

    // Decay click pulse
    if (clickPulse > 0) {
      setClickPulse(prev => Math.max(0, prev - 0.03))
    }
  })

  // Generate moon orbital data
  const moons = useMemo(() => {
    const moonCount = planet.moons || 0
    if (moonCount === 0) return []
    return Array.from({ length: moonCount }, (_, i) => ({
      id: i,
      orbit: planet.size * (2 + i * 0.8),
      speed: 2 + i * 0.5,
      size: planet.size * 0.2,
      phase: (i * Math.PI * 2) / moonCount
    }))
  }, [planet.moons, planet.size])

  return (
    <group>
      {/* Planet trail */}
      <points ref={trailRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={30}
            array={trailPositions}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial color={planet.color} size={0.03} transparent opacity={0.4} />
      </points>

      {/* Planet with effects */}
      <group ref={groupRef}>
        {/* Click pulse ring effect */}
        {clickPulse > 0 && (
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <ringGeometry args={[planet.size * (2 + (1 - clickPulse) * 3), planet.size * (2.1 + (1 - clickPulse) * 3.2), 32]} />
            <meshBasicMaterial color="#ffffff" transparent opacity={clickPulse * 0.8} />
          </mesh>
        )}

        {/* Planet atmosphere glow */}
        <Sphere ref={atmosphereRef} args={[planet.size * 1.3, 16, 16]}>
          <meshBasicMaterial color={planet.color} transparent opacity={isHovered ? 0.35 : 0.15} />
        </Sphere>

        {/* Planet sphere - CLICKABLE */}
        <Sphere
          ref={meshRef}
          args={[planet.size, 16, 16]}
          onPointerOver={() => setIsHovered(true)}
          onPointerOut={() => setIsHovered(false)}
          onClick={handleClick}
        >
          <MeshDistortMaterial
            color={planet.color}
            emissive={planet.color}
            emissiveIntensity={isHovered ? 0.5 : 0.2}
            distort={isHovered ? 0.15 : 0.05}
            speed={2}
          />
        </Sphere>

        {/* Inner core glow */}
        <Sphere args={[planet.size * 0.5, 8, 8]}>
          <meshBasicMaterial color="#ffffff" transparent opacity={0.4} />
        </Sphere>

        {/* Orbiting moons */}
        {moons.map(moon => (
          <OrbitingMoon key={moon.id} moon={moon} planetColor={planet.color} paused={paused} />
        ))}

        {/* Planet unique effect */}
        {planet.effect && (
          <PlanetEffectComponent
            effect={planet.effect}
            color={planet.color}
            size={planet.size}
            paused={paused}
          />
        )}

        {/* Hover tooltip */}
        {isHovered && (
          <Html position={[0, planet.size + 0.3, 0]} center>
            <div className="bg-gray-900/90 border border-gray-700 rounded-lg px-3 py-2 text-center backdrop-blur-sm min-w-[100px]">
              <div className="text-xs font-bold" style={{ color: planet.color }}>
                {planet.name}
              </div>
              <div className="text-[10px] text-gray-400 mt-1">Click to navigate</div>
              <div className="text-[10px] text-gray-500">{PLANET_ROUTES[planet.name] || '/'}</div>
            </div>
          </Html>
        )}

        {/* Enhanced glow when hovered */}
        {isHovered && (
          <>
            <Sphere args={[planet.size * 2, 8, 8]}>
              <meshBasicMaterial color={planet.color} transparent opacity={0.2} />
            </Sphere>
            {/* Pulsing ring */}
            <mesh rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[planet.size * 1.5, 0.01, 8, 32]} />
              <meshBasicMaterial color="#ffffff" transparent opacity={0.8} />
            </mesh>
          </>
        )}
      </group>
    </group>
  )
}

// =============================================================================
// ORBITING MOON - Mini moons around planets
// =============================================================================

function OrbitingMoon({
  moon,
  planetColor,
  paused
}: {
  moon: { id: number, orbit: number, speed: number, size: number, phase: number }
  planetColor: string
  paused: boolean
}) {
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused || !meshRef.current) return
    const t = state.clock.elapsedTime
    const angle = t * moon.speed + moon.phase
    meshRef.current.position.x = Math.cos(angle) * moon.orbit
    meshRef.current.position.z = Math.sin(angle) * moon.orbit
    meshRef.current.rotation.y = t * 3
  })

  return (
    <Sphere ref={meshRef} args={[moon.size, 8, 8]} position={[moon.orbit, 0, 0]}>
      <meshBasicMaterial color={planetColor} transparent opacity={0.7} />
    </Sphere>
  )
}

// =============================================================================
// SUN CORONA - Particle effect around suns
// =============================================================================

function SunCorona({ color, paused }: { color: string, paused: boolean }) {
  const particlesRef = useRef<THREE.Points>(null)
  const count = 50

  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      const r = 0.4 + Math.random() * 0.3
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta)
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
      pos[i * 3 + 2] = r * Math.cos(phi)
    }
    return pos
  }, [])

  useFrame((state) => {
    if (paused || !particlesRef.current) return
    const t = state.clock.elapsedTime
    particlesRef.current.rotation.y = t * 0.2
    particlesRef.current.rotation.x = t * 0.15
  })

  return (
    <points ref={particlesRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial color={color} size={0.04} transparent opacity={0.6} />
    </points>
  )
}

// =============================================================================
// NEURAL SYNAPSE PULSES - Light traveling between solar systems
// =============================================================================

function NeuralSynapsePulses({ paused }: { paused: boolean }) {
  const [pulses, setPulses] = useState<Array<{
    id: number
    sourceId: string
    targetId: string
    startTime: number
    color: string
  }>>([])
  const nextId = useRef(0)
  const lastPulse = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Spawn new pulse every 2-5 seconds
    if (t - lastPulse.current > 2 + Math.random() * 3) {
      lastPulse.current = t

      // Pick random source and target
      const sourceIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      let targetIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      while (targetIdx === sourceIdx) {
        targetIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      }

      const source = SOLAR_SYSTEMS[sourceIdx]
      const target = SOLAR_SYSTEMS[targetIdx]

      // Create pulse with beautiful color gradient
      const colors = ['#22d3ee', '#a855f7', '#f59e0b', '#10b981', '#ef4444', '#ec4899']
      const color = colors[Math.floor(Math.random() * colors.length)]

      setPulses(prev => [...prev, {
        id: nextId.current++,
        sourceId: source.id,
        targetId: target.id,
        startTime: t,
        color
      }])
    }

    // Clean up old pulses
    setPulses(prev => prev.filter(p => t - p.startTime < 1.5))
  })

  return (
    <group>
      {pulses.map(pulse => (
        <SynapsePulse key={pulse.id} pulse={pulse} />
      ))}
    </group>
  )
}

// =============================================================================
// SYNAPSE PULSE - Individual light pulse traveling between systems
// =============================================================================

function SynapsePulse({ pulse }: {
  pulse: { id: number, sourceId: string, targetId: string, startTime: number, color: string }
}) {
  const groupRef = useRef<THREE.Group>(null)
  const glowRef = useRef<THREE.Mesh>(null)
  const trailRef = useRef<any>(null)

  const source = SOLAR_SYSTEMS.find(s => s.id === pulse.sourceId)
  const target = SOLAR_SYSTEMS.find(s => s.id === pulse.targetId)

  // Calculate curved path using quadratic bezier
  const curve = useMemo(() => {
    if (!source || !target) return null

    const start = new THREE.Vector3(...source.position)
    const end = new THREE.Vector3(...target.position)
    const mid = start.clone().add(end).multiplyScalar(0.5)
    // Curve outward from center
    const centerDir = mid.clone().normalize()
    mid.add(centerDir.clone().multiplyScalar(3 + Math.random() * 2))
    mid.y += 2 + Math.random() * 3

    return new THREE.QuadraticBezierCurve3(start, mid, end)
  }, [source, target])

  const trailPoints = useMemo(() => {
    if (!curve) return []
    return curve.getPoints(40).map(p => [p.x, p.y, p.z] as [number, number, number])
  }, [curve])

  useFrame((state) => {
    if (!curve || !groupRef.current) return

    const elapsed = state.clock.elapsedTime - pulse.startTime
    const progress = Math.min(elapsed / 1.2, 1) // 1.2 second travel time

    // Get position along curve
    const point = curve.getPoint(progress)
    groupRef.current.position.copy(point)

    // Pulse glow effect
    if (glowRef.current) {
      const glowPulse = 1 + Math.sin(elapsed * 15) * 0.3
      glowRef.current.scale.setScalar(glowPulse)

      // Fade out at end
      const fadeOut = progress > 0.8 ? (1 - progress) / 0.2 : 1
      ;(glowRef.current.material as THREE.MeshBasicMaterial).opacity = 0.8 * fadeOut
    }

    // Update trail opacity
    if (trailRef.current) {
      trailRef.current.material.opacity = 0.4 * (1 - progress * 0.5)
    }
  })

  if (!source || !target || !curve) return null

  return (
    <>
      {/* Trail line */}
      <Line
        ref={trailRef}
        points={trailPoints}
        color={pulse.color}
        lineWidth={2}
        transparent
        opacity={0.4}
      />

      {/* Moving pulse */}
      <group ref={groupRef}>
        {/* Core bright point */}
        <Sphere args={[0.08, 8, 8]}>
          <meshBasicMaterial color="#ffffff" />
        </Sphere>

        {/* Outer glow */}
        <Sphere ref={glowRef} args={[0.2, 16, 16]}>
          <meshBasicMaterial color={pulse.color} transparent opacity={0.8} />
        </Sphere>

        {/* Sparkle ring */}
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.15, 0.02, 8, 16]} />
          <meshBasicMaterial color={pulse.color} transparent opacity={0.6} />
        </mesh>
      </group>
    </>
  )
}

// =============================================================================
// INTERSTELLAR SHIPS - Ships traveling between solar systems
// =============================================================================

function InterstellarShips({ paused }: { paused: boolean }) {
  const [ships, setShips] = useState<Array<{
    id: number
    sourceIdx: number
    targetIdx: number
    startTime: number
    type: 'cargo' | 'probe' | 'fighter'
  }>>([])
  const nextId = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Spawn new ships periodically
    if (Math.random() < 0.008) {
      const sourceIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      let targetIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      while (targetIdx === sourceIdx) {
        targetIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      }
      const types: ('cargo' | 'probe' | 'fighter')[] = ['cargo', 'probe', 'fighter']
      setShips(prev => [...prev.slice(-10), {
        id: nextId.current++,
        sourceIdx,
        targetIdx,
        startTime: t,
        type: types[Math.floor(Math.random() * types.length)]
      }])
    }

    // Clean old ships
    setShips(prev => prev.filter(s => t - s.startTime < 8))
  })

  return (
    <group>
      {ships.map(ship => (
        <TravelingShip key={ship.id} ship={ship} />
      ))}
    </group>
  )
}

function TravelingShip({ ship }: { ship: { id: number, sourceIdx: number, targetIdx: number, startTime: number, type: string } }) {
  const groupRef = useRef<THREE.Group>(null)
  const trailRef = useRef<THREE.Points>(null)

  const source = SOLAR_SYSTEMS[ship.sourceIdx]
  const target = SOLAR_SYSTEMS[ship.targetIdx]

  const trailPositions = useMemo(() => new Float32Array(30 * 3), [])
  const trailIdx = useRef(0)

  const shipColor = ship.type === 'cargo' ? '#22c55e' : ship.type === 'probe' ? '#3b82f6' : '#ef4444'

  useFrame((state) => {
    if (!groupRef.current || !source || !target) return
    const t = state.clock.elapsedTime
    const elapsed = t - ship.startTime
    const progress = Math.min(elapsed / 6, 1)

    // Curved path
    const start = new THREE.Vector3(...source.position)
    const end = new THREE.Vector3(...target.position)
    const mid = start.clone().add(end).multiplyScalar(0.5)
    mid.y += 5 + Math.sin(ship.id) * 3

    // Quadratic bezier
    const pos = new THREE.Vector3()
    pos.x = (1 - progress) * (1 - progress) * start.x + 2 * (1 - progress) * progress * mid.x + progress * progress * end.x
    pos.y = (1 - progress) * (1 - progress) * start.y + 2 * (1 - progress) * progress * mid.y + progress * progress * end.y
    pos.z = (1 - progress) * (1 - progress) * start.z + 2 * (1 - progress) * progress * mid.z + progress * progress * end.z

    groupRef.current.position.copy(pos)
    groupRef.current.lookAt(end)

    // Update trail
    if (trailRef.current && progress < 0.95) {
      const idx = (trailIdx.current % 30) * 3
      trailPositions[idx] = pos.x
      trailPositions[idx + 1] = pos.y
      trailPositions[idx + 2] = pos.z
      trailIdx.current++
      trailRef.current.geometry.attributes.position.needsUpdate = true
    }
  })

  if (!source || !target) return null

  return (
    <>
      {/* Engine trail */}
      <points ref={trailRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={30} array={trailPositions} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial color={shipColor} size={0.06} transparent opacity={0.5} />
      </points>

      {/* Ship */}
      <group ref={groupRef}>
        {ship.type === 'cargo' && (
          <mesh>
            <boxGeometry args={[0.3, 0.15, 0.5]} />
            <meshBasicMaterial color={shipColor} />
          </mesh>
        )}
        {ship.type === 'probe' && (
          <mesh>
            <octahedronGeometry args={[0.15]} />
            <meshBasicMaterial color={shipColor} />
          </mesh>
        )}
        {ship.type === 'fighter' && (
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <coneGeometry args={[0.1, 0.4, 4]} />
            <meshBasicMaterial color={shipColor} />
          </mesh>
        )}
        {/* Engine glow */}
        <Sphere args={[0.08, 8, 8]} position={[0, 0, 0.25]}>
          <meshBasicMaterial color="#ff6b00" />
        </Sphere>
        <Sphere args={[0.15, 8, 8]} position={[0, 0, 0.25]}>
          <meshBasicMaterial color="#ff6b00" transparent opacity={0.3} />
        </Sphere>
      </group>
    </>
  )
}

// =============================================================================
// ASTEROID BELT - Rotating asteroid ring around each system
// =============================================================================

function SystemAsteroidBelt({ position, color, paused }: { position: [number, number, number], color: string, paused: boolean }) {
  const beltRef = useRef<THREE.Group>(null)
  const asteroidCount = 40

  const asteroids = useMemo(() => {
    return Array.from({ length: asteroidCount }, (_, i) => ({
      angle: (i / asteroidCount) * Math.PI * 2 + Math.random() * 0.3,
      radius: 7 + Math.random() * 2,
      size: 0.08 + Math.random() * 0.12,
      speed: 0.1 + Math.random() * 0.1,
      yOffset: (Math.random() - 0.5) * 0.8,
      rotSpeed: Math.random() * 2
    }))
  }, [])

  useFrame((state) => {
    if (paused || !beltRef.current) return
    const t = state.clock.elapsedTime
    beltRef.current.rotation.y = t * 0.02
  })

  return (
    <group position={position}>
      <group ref={beltRef}>
        {asteroids.map((asteroid, i) => {
          const x = Math.cos(asteroid.angle) * asteroid.radius
          const z = Math.sin(asteroid.angle) * asteroid.radius
          return (
            <mesh
              key={i}
              position={[x, asteroid.yOffset, z]}
              rotation={[asteroid.angle, asteroid.angle * 2, 0]}
            >
              <dodecahedronGeometry args={[asteroid.size, 0]} />
              <meshBasicMaterial color="#6b7280" transparent opacity={0.7} />
            </mesh>
          )
        })}
      </group>
      {/* Belt dust ring */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[8, 1.5, 2, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.03} />
      </mesh>
    </group>
  )
}

// =============================================================================
// MASSIVE ENERGY BEAMS - Dramatic beams between systems
// =============================================================================

function MassiveEnergyBeams({ paused }: { paused: boolean }) {
  const [beams, setBeams] = useState<Array<{
    id: number
    sourceIdx: number
    targetIdx: number
    startTime: number
    color: string
  }>>([])
  const nextId = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Spawn beams occasionally
    if (Math.random() < 0.002) {
      const sourceIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      let targetIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      while (targetIdx === sourceIdx) {
        targetIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      }
      const colors = ['#22d3ee', '#a855f7', '#f59e0b', '#ef4444', '#10b981']
      setBeams(prev => [...prev.slice(-3), {
        id: nextId.current++,
        sourceIdx,
        targetIdx,
        startTime: t,
        color: colors[Math.floor(Math.random() * colors.length)]
      }])
    }

    setBeams(prev => prev.filter(b => t - b.startTime < 2))
  })

  return (
    <group>
      {beams.map(beam => (
        <EnergyBeam key={beam.id} beam={beam} />
      ))}
    </group>
  )
}

function EnergyBeam({ beam }: { beam: { sourceIdx: number, targetIdx: number, startTime: number, color: string } }) {
  const beamRef = useRef<any>(null)
  const glowRef = useRef<any>(null)

  const source = SOLAR_SYSTEMS[beam.sourceIdx]
  const target = SOLAR_SYSTEMS[beam.targetIdx]

  useFrame((state) => {
    if (!beamRef.current || !source || !target) return
    const t = state.clock.elapsedTime
    const elapsed = t - beam.startTime
    const phase = elapsed / 2

    // Pulse opacity
    const opacity = phase < 0.2 ? phase * 5 : phase > 0.8 ? (1 - phase) * 5 : 1
    beamRef.current.material.opacity = opacity * 0.6
    if (glowRef.current) {
      glowRef.current.material.opacity = opacity * 0.2
    }
  })

  if (!source || !target) return null

  const start = new THREE.Vector3(...source.position)
  const end = new THREE.Vector3(...target.position)
  const mid = start.clone().add(end).multiplyScalar(0.5)
  mid.y += 3

  const curve = new THREE.QuadraticBezierCurve3(start, mid, end)
  const points = curve.getPoints(30).map(p => [p.x, p.y, p.z] as [number, number, number])

  return (
    <group>
      <Line ref={beamRef} points={points} color={beam.color} lineWidth={4} transparent opacity={0.6} />
      <Line ref={glowRef} points={points} color={beam.color} lineWidth={12} transparent opacity={0.2} />
    </group>
  )
}

// =============================================================================
// SOLAR FLARE EVENTS - Massive dramatic flare eruptions
// =============================================================================

function SolarFlareEvents({ paused }: { paused: boolean }) {
  const [flares, setFlares] = useState<Array<{
    id: number
    systemIdx: number
    startTime: number
    direction: THREE.Vector3
  }>>([])
  const nextId = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Spawn massive flares occasionally
    if (Math.random() < 0.003) {
      const systemIdx = Math.floor(Math.random() * SOLAR_SYSTEMS.length)
      const angle = Math.random() * Math.PI * 2
      const dir = new THREE.Vector3(Math.cos(angle), 0.5 + Math.random() * 0.5, Math.sin(angle)).normalize()

      setFlares(prev => [...prev.slice(-5), {
        id: nextId.current++,
        systemIdx,
        startTime: t,
        direction: dir
      }])
    }

    setFlares(prev => prev.filter(f => t - f.startTime < 3))
  })

  return (
    <group>
      {flares.map(flare => (
        <MassiveSolarFlare key={flare.id} flare={flare} />
      ))}
    </group>
  )
}

function MassiveSolarFlare({ flare }: { flare: { systemIdx: number, startTime: number, direction: THREE.Vector3 } }) {
  const groupRef = useRef<THREE.Group>(null)
  const system = SOLAR_SYSTEMS[flare.systemIdx]

  useFrame((state) => {
    if (!groupRef.current || !system) return
    const t = state.clock.elapsedTime
    const elapsed = t - flare.startTime
    const progress = elapsed / 3

    // Expand outward
    const scale = progress * 8
    groupRef.current.scale.setScalar(scale)

    // Fade out
    groupRef.current.children.forEach(child => {
      const mesh = child as THREE.Mesh
      if (mesh.material) {
        ;(mesh.material as THREE.MeshBasicMaterial).opacity = Math.max(0, 0.8 * (1 - progress))
      }
    })
  })

  if (!system) return null

  return (
    <group ref={groupRef} position={system.position}>
      {/* Main flare body */}
      <mesh rotation={[0, 0, Math.atan2(flare.direction.z, flare.direction.x)]}>
        <coneGeometry args={[0.3, 2, 8]} />
        <meshBasicMaterial color={system.sunColor} transparent opacity={0.8} />
      </mesh>
      {/* Flare particles */}
      {[0, 1, 2, 3, 4].map(i => (
        <Sphere
          key={i}
          args={[0.15, 8, 8]}
          position={[
            flare.direction.x * (0.5 + i * 0.3),
            flare.direction.y * (0.5 + i * 0.3),
            flare.direction.z * (0.5 + i * 0.3)
          ]}
        >
          <meshBasicMaterial color={system.glowColor} transparent opacity={0.6} />
        </Sphere>
      ))}
      {/* Shockwave ring */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.8, 0.1, 8, 32]} />
        <meshBasicMaterial color={system.sunColor} transparent opacity={0.5} />
      </mesh>
    </group>
  )
}

// =============================================================================
// SYSTEM NEBULA - Colored nebula clouds around each system
// =============================================================================

function SystemNebula({ position, color, paused }: { position: [number, number, number], color: string, paused: boolean }) {
  const nebulaRef = useRef<THREE.Group>(null)

  const clouds = useMemo(() => {
    return Array.from({ length: 8 }, (_, i) => ({
      angle: (i / 8) * Math.PI * 2,
      radius: 10 + Math.random() * 5,
      size: 2 + Math.random() * 3,
      yOffset: (Math.random() - 0.5) * 4,
      opacity: 0.03 + Math.random() * 0.04
    }))
  }, [])

  useFrame((state) => {
    if (paused || !nebulaRef.current) return
    const t = state.clock.elapsedTime
    nebulaRef.current.rotation.y = t * 0.01
  })

  return (
    <group position={position} ref={nebulaRef}>
      {clouds.map((cloud, i) => (
        <Sphere
          key={i}
          args={[cloud.size, 8, 8]}
          position={[
            Math.cos(cloud.angle) * cloud.radius,
            cloud.yOffset,
            Math.sin(cloud.angle) * cloud.radius
          ]}
        >
          <meshBasicMaterial color={color} transparent opacity={cloud.opacity} />
        </Sphere>
      ))}
    </group>
  )
}

// =============================================================================
// AURORA EFFECT - Northern lights dancing around systems
// =============================================================================

function AuroraEffect({ position, color, paused }: { position: [number, number, number], color: string, paused: boolean }) {
  const auroraRef = useRef<THREE.Group>(null)
  const ribbonCount = 5

  useFrame((state) => {
    if (paused || !auroraRef.current) return
    const t = state.clock.elapsedTime

    auroraRef.current.children.forEach((ribbon, i) => {
      const mesh = ribbon as THREE.Mesh
      mesh.rotation.y = t * 0.1 + i * 0.5
      mesh.position.y = 3 + Math.sin(t * 0.5 + i) * 0.5
      ;(mesh.material as THREE.MeshBasicMaterial).opacity = 0.1 + Math.sin(t + i) * 0.05
    })
  })

  return (
    <group position={position} ref={auroraRef}>
      {Array.from({ length: ribbonCount }).map((_, i) => {
        const angle = (i / ribbonCount) * Math.PI * 2
        return (
          <mesh key={i} position={[Math.cos(angle) * 5, 3, Math.sin(angle) * 5]} rotation={[0, angle, Math.PI / 4]}>
            <planeGeometry args={[4, 1.5]} />
            <meshBasicMaterial color={color} transparent opacity={0.12} side={THREE.DoubleSide} />
          </mesh>
        )
      })}
    </group>
  )
}

// =============================================================================
// STARDUST PARTICLES - Ambient floating particles
// =============================================================================

function StardustField({ paused }: { paused: boolean }) {
  const particlesRef = useRef<THREE.Points>(null)
  const count = 200

  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 80
      pos[i * 3 + 1] = (Math.random() - 0.5) * 40
      pos[i * 3 + 2] = (Math.random() - 0.5) * 80
    }
    return pos
  }, [])

  useFrame((state) => {
    if (paused || !particlesRef.current) return
    const t = state.clock.elapsedTime
    particlesRef.current.rotation.y = t * 0.005

    // Gentle floating motion
    const pos = particlesRef.current.geometry.attributes.position.array as Float32Array
    for (let i = 0; i < count; i++) {
      pos[i * 3 + 1] += Math.sin(t + i) * 0.001
    }
    particlesRef.current.geometry.attributes.position.needsUpdate = true
  })

  return (
    <points ref={particlesRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial color="#ffffff" size={0.05} transparent opacity={0.4} />
    </points>
  )
}

// =============================================================================
// ENHANCED THEMATIC EFFECTS - Books, Matrix, Crystal Balls, Pendulum, Terminals
// =============================================================================

// SOLOMON: Floating open books with glowing pages
function FloatingBooks({ position, color, paused }: { position: [number, number, number], color: string, paused: boolean }) {
  const booksRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (paused || !booksRef.current) return
    const t = state.clock.elapsedTime
    booksRef.current.rotation.y = t * 0.08
    booksRef.current.children.forEach((book, i) => {
      book.position.y = Math.sin(t * 0.5 + i * 2) * 0.3
      book.rotation.z = Math.sin(t * 0.3 + i) * 0.1
    })
  })

  return (
    <group position={position} ref={booksRef}>
      {[0, 1, 2].map(i => {
        const angle = (i / 3) * Math.PI * 2 + Math.PI / 6
        const r = 8
        return (
          <group key={i} position={[Math.cos(angle) * r, 1, Math.sin(angle) * r]} rotation={[0.2, -angle, 0]}>
            {/* Book cover */}
            <mesh>
              <boxGeometry args={[0.6, 0.08, 0.8]} />
              <meshBasicMaterial color="#8b4513" />
            </mesh>
            {/* Open pages - left */}
            <mesh position={[-0.2, 0.06, 0]} rotation={[0, 0, -0.3]}>
              <planeGeometry args={[0.35, 0.7]} />
              <meshBasicMaterial color="#fef3c7" transparent opacity={0.9} side={THREE.DoubleSide} />
            </mesh>
            {/* Open pages - right */}
            <mesh position={[0.2, 0.06, 0]} rotation={[0, 0, 0.3]}>
              <planeGeometry args={[0.35, 0.7]} />
              <meshBasicMaterial color="#fef3c7" transparent opacity={0.9} side={THREE.DoubleSide} />
            </mesh>
            {/* Glowing text lines */}
            {[0, 1, 2, 3].map(j => (
              <mesh key={j} position={[0.2, 0.08, -0.2 + j * 0.12]}>
                <boxGeometry args={[0.25, 0.01, 0.02]} />
                <meshBasicMaterial color={color} transparent opacity={0.6} />
              </mesh>
            ))}
          </group>
        )
      })}
    </group>
  )
}

// ARGUS: Matrix-style data rain (thematic effect)
function ArgusMatrixRain({ position, color, paused }: { position: [number, number, number], color: string, paused: boolean }) {
  const [columns, setColumns] = useState<Array<{ x: number, z: number, chars: string[], offset: number }>>([])

  useEffect(() => {
    const cols = []
    for (let i = 0; i < 12; i++) {
      const angle = (i / 12) * Math.PI * 2
      const r = 8 + Math.random() * 2
      cols.push({
        x: Math.cos(angle) * r,
        z: Math.sin(angle) * r,
        chars: Array.from({ length: 8 }, () => String.fromCharCode(0x30A0 + Math.random() * 96)),
        offset: Math.random() * 5
      })
    }
    setColumns(cols)
  }, [])

  return (
    <group position={position}>
      {columns.map((col, i) => (
        <Html key={i} position={[col.x, 2, col.z]} center>
          <div className="flex flex-col text-[10px] font-mono" style={{ color }}>
            {col.chars.map((char, j) => (
              <span key={j} style={{ opacity: 0.3 + (j / col.chars.length) * 0.7 }}>{char}</span>
            ))}
          </div>
        </Html>
      ))}
    </group>
  )
}

// ORACLE: Swirling crystal ball with visions
function CrystalBallVisions({ position, color, paused }: { position: [number, number, number], color: string, paused: boolean }) {
  const ballRef = useRef<THREE.Group>(null)
  const visionsRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    if (ballRef.current) {
      ballRef.current.rotation.y = t * 0.2
    }

    if (visionsRef.current) {
      visionsRef.current.rotation.y = -t * 0.5
      visionsRef.current.rotation.x = Math.sin(t * 0.3) * 0.2
    }
  })

  return (
    <group position={position}>
      <group ref={ballRef} position={[0, 3, 8]}>
        {/* Crystal ball outer */}
        <Sphere args={[0.8, 32, 32]}>
          <meshBasicMaterial color={color} transparent opacity={0.2} />
        </Sphere>
        {/* Inner swirling visions */}
        <group ref={visionsRef}>
          {[0, 1, 2].map(i => {
            const angle = (i / 3) * Math.PI * 2
            return (
              <mesh key={i} position={[Math.cos(angle) * 0.3, 0, Math.sin(angle) * 0.3]}>
                <torusGeometry args={[0.2, 0.05, 8, 16]} />
                <meshBasicMaterial color="#ffffff" transparent opacity={0.5} />
              </mesh>
            )
          })}
        </group>
        {/* Glow */}
        <Sphere args={[1, 16, 16]}>
          <meshBasicMaterial color={color} transparent opacity={0.1} />
        </Sphere>
        {/* Stand */}
        <mesh position={[0, -0.9, 0]}>
          <cylinderGeometry args={[0.3, 0.5, 0.3, 8]} />
          <meshBasicMaterial color="#4a5568" />
        </mesh>
      </group>
    </group>
  )
}

// KRONOS: Giant swinging pendulum
function GiantPendulum({ position, color, paused }: { position: [number, number, number], color: string, paused: boolean }) {
  const pendulumRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (paused || !pendulumRef.current) return
    const t = state.clock.elapsedTime
    pendulumRef.current.rotation.z = Math.sin(t * 0.8) * 0.4
  })

  return (
    <group position={position}>
      <group ref={pendulumRef} position={[8, 5, 0]}>
        {/* Pendulum arm */}
        <mesh position={[0, -1.5, 0]}>
          <cylinderGeometry args={[0.05, 0.05, 3, 8]} />
          <meshBasicMaterial color="#9ca3af" />
        </mesh>
        {/* Pendulum weight */}
        <Sphere args={[0.4, 16, 16]} position={[0, -3.2, 0]}>
          <meshBasicMaterial color={color} />
        </Sphere>
        {/* Weight glow */}
        <Sphere args={[0.6, 16, 16]} position={[0, -3.2, 0]}>
          <meshBasicMaterial color={color} transparent opacity={0.3} />
        </Sphere>
      </group>
      {/* Pivot point */}
      <Sphere args={[0.15, 8, 8]} position={[8, 5, 0]}>
        <meshBasicMaterial color="#6b7280" />
      </Sphere>
    </group>
  )
}

// SYSTEMS: Holographic terminal screens
function HolographicTerminals({ position, color, paused }: { position: [number, number, number], color: string, paused: boolean }) {
  const terminalsRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (paused || !terminalsRef.current) return
    const t = state.clock.elapsedTime
    terminalsRef.current.rotation.y = t * 0.05
  })

  return (
    <group position={position} ref={terminalsRef}>
      {[0, 1, 2].map(i => {
        const angle = (i / 3) * Math.PI * 2
        const r = 9
        return (
          <group key={i} position={[Math.cos(angle) * r, 2, Math.sin(angle) * r]} rotation={[0, -angle + Math.PI, 0.1]}>
            {/* Screen frame */}
            <mesh>
              <boxGeometry args={[1.5, 1, 0.05]} />
              <meshBasicMaterial color="#1f2937" />
            </mesh>
            {/* Screen content */}
            <mesh position={[0, 0, 0.03]}>
              <planeGeometry args={[1.4, 0.9]} />
              <meshBasicMaterial color={color} transparent opacity={0.3} />
            </mesh>
            {/* Scan line effect */}
            <mesh position={[0, 0, 0.04]}>
              <planeGeometry args={[1.4, 0.05]} />
              <meshBasicMaterial color="#ffffff" transparent opacity={0.2} />
            </mesh>
            {/* Data bars */}
            {[0, 1, 2, 3].map(j => (
              <mesh key={j} position={[-0.5 + j * 0.35, -0.2, 0.04]}>
                <boxGeometry args={[0.1, 0.3 + Math.random() * 0.3, 0.01]} />
                <meshBasicMaterial color={color} transparent opacity={0.7} />
              </mesh>
            ))}
          </group>
        )
      })}
    </group>
  )
}

// =============================================================================
// INTERACTIVE SOLAR BURST - Click on sun for explosion
// =============================================================================

function SolarBurstEffect({ position, active, color }: { position: [number, number, number], active: boolean, color: string }) {
  const burstRef = useRef<THREE.Group>(null)
  const [scale, setScale] = useState(0)

  useFrame(() => {
    if (active && scale < 5) {
      setScale(prev => Math.min(prev + 0.15, 5))
    } else if (!active && scale > 0) {
      setScale(prev => Math.max(prev - 0.1, 0))
    }

    if (burstRef.current) {
      burstRef.current.scale.setScalar(scale)
      burstRef.current.rotation.z += 0.05
    }
  })

  if (scale === 0) return null

  return (
    <group ref={burstRef} position={position}>
      {/* Burst rings */}
      {[0, 1, 2].map(i => (
        <mesh key={i} rotation={[Math.PI / 2, 0, i * 0.5]}>
          <torusGeometry args={[0.5 + i * 0.3, 0.08, 8, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.6 - i * 0.15} />
        </mesh>
      ))}
      {/* Burst particles */}
      {Array.from({ length: 12 }).map((_, i) => {
        const angle = (i / 12) * Math.PI * 2
        return (
          <Sphere key={i} args={[0.1, 8, 8]} position={[Math.cos(angle) * 1.5, 0, Math.sin(angle) * 1.5]}>
            <meshBasicMaterial color="#ffffff" />
          </Sphere>
        )
      })}
    </group>
  )
}

// =============================================================================
// ALL SOLAR SYSTEMS CONTAINER
// =============================================================================

function SolarSystemsContainer({
  paused,
  onSystemClick,
  onPlanetClick
}: {
  paused: boolean
  onSystemClick?: (systemId: string, position: [number, number, number]) => void
  onPlanetClick?: (planetName: string) => void
}) {
  const handlePulseToSystem = useCallback((targetId: string) => {
    // This could trigger effects on the target system
    // For now, the neural synapse pulses handle the visual effect
  }, [])

  return (
    <group>
      {/* Core Solar Systems */}
      {SOLAR_SYSTEMS.map(system => (
        <SolarSystem
          key={system.id}
          system={system}
          paused={paused}
          onPulseToSystem={handlePulseToSystem}
          onSystemClick={onSystemClick}
          onPlanetClick={onPlanetClick}
        />
      ))}

      {/* Neural Synapse Connections */}
      <NeuralSynapsePulses paused={paused} />

      {/* === WOW FACTOR 1: Traveling Ships Between Systems === */}
      <InterstellarShips paused={paused} />

      {/* === WOW FACTOR 2: Asteroid Belts Around Each System === */}
      {SOLAR_SYSTEMS.map(system => (
        <SystemAsteroidBelt
          key={`asteroids-${system.id}`}
          position={system.position}
          color={system.sunColor}
          paused={paused}
        />
      ))}

      {/* === WOW FACTOR 3: Massive Energy Beams === */}
      <MassiveEnergyBeams paused={paused} />

      {/* === WOW FACTOR 4: Dynamic Solar Flare Events === */}
      <SolarFlareEvents paused={paused} />

      {/* === WOW FACTOR 5: Nebula Clouds Around Systems === */}
      {SOLAR_SYSTEMS.map(system => (
        <SystemNebula
          key={`nebula-${system.id}`}
          position={system.position}
          color={system.glowColor}
          paused={paused}
        />
      ))}

      {/* === WOW FACTOR 6: Aurora Effects === */}
      {SOLAR_SYSTEMS.map(system => (
        <AuroraEffect
          key={`aurora-${system.id}`}
          position={system.position}
          color={system.sunColor}
          paused={paused}
        />
      ))}

      {/* === WOW FACTOR 7: Ambient Stardust Field === */}
      <StardustField paused={paused} />

      {/* === WOW FACTOR 8: Thematic Enhancements Per System === */}
      {/* SOLOMON - Floating Wisdom Books */}
      <FloatingBooks
        position={SOLAR_SYSTEMS.find(s => s.id === 'solomon')?.position || [-22, 8, -20]}
        color="#f59e0b"
        paused={paused}
      />

      {/* ARGUS - Matrix Rain */}
      <ArgusMatrixRain
        position={SOLAR_SYSTEMS.find(s => s.id === 'argus')?.position || [24, 5, -18]}
        color="#22d3ee"
        paused={paused}
      />

      {/* ORACLE - Crystal Ball Visions */}
      <CrystalBallVisions
        position={SOLAR_SYSTEMS.find(s => s.id === 'oracle')?.position || [0, 15, -25]}
        color="#a855f7"
        paused={paused}
      />

      {/* KRONOS - Giant Pendulum */}
      <GiantPendulum
        position={SOLAR_SYSTEMS.find(s => s.id === 'kronos')?.position || [-18, -8, -22]}
        color="#ef4444"
        paused={paused}
      />

      {/* SYSTEMS - Holographic Terminals */}
      <HolographicTerminals
        position={SOLAR_SYSTEMS.find(s => s.id === 'systems')?.position || [20, -6, -20]}
        color="#10b981"
        paused={paused}
      />
    </group>
  )
}

// =============================================================================
// NEURAL NETWORK VISUAL COMPONENTS
// =============================================================================

// Neural Brain Structure - 3D brain mesh connecting all systems
function NeuralBrainStructure({ paused }: { paused: boolean }) {
  const meshRef = useRef<THREE.Group>(null)
  const nodesRef = useRef<THREE.Points>(null)

  // Generate brain-like nodes
  const nodePositions = useMemo(() => {
    const positions = new Float32Array(200 * 3)
    for (let i = 0; i < 200; i++) {
      // Create brain-like distribution (ellipsoid)
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      const r = 12 + Math.random() * 8
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta) * 1.3 // wider
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.8 - 5 // flatter, lower
      positions[i * 3 + 2] = r * Math.cos(phi) - 15 // depth
    }
    return positions
  }, [])

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime
    if (meshRef.current) {
      meshRef.current.rotation.y = Math.sin(t * 0.1) * 0.1
    }
    if (nodesRef.current) {
      nodesRef.current.rotation.y = t * 0.02
    }
  })

  return (
    <group ref={meshRef} position={[0, 5, -20]}>
      {/* Neural nodes */}
      <points ref={nodesRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={200} array={nodePositions} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial color="#22d3ee" size={0.15} transparent opacity={0.5} />
      </points>
    </group>
  )
}

// Neural Neurons - Individual neurons with dendrites
function NeuralNeurons({ paused }: { paused: boolean }) {
  const neurons = useMemo(() => {
    return Array.from({ length: 8 }, (_, i) => ({
      id: i,
      position: [
        (Math.random() - 0.5) * 40,
        (Math.random() - 0.5) * 20,
        -10 - Math.random() * 20
      ] as [number, number, number],
      color: ['#22d3ee', '#a855f7', '#f59e0b', '#10b981', '#ef4444'][i % 5],
      scale: 0.8 + Math.random() * 0.4
    }))
  }, [])

  return (
    <group>
      {neurons.map(neuron => (
        <NeuronCell key={neuron.id} {...neuron} paused={paused} />
      ))}
    </group>
  )
}

function NeuronCell({ position, color, scale, paused }: {
  position: [number, number, number]
  color: string
  scale: number
  paused: boolean
}) {
  const groupRef = useRef<THREE.Group>(null)
  const [firing, setFiring] = useState(false)

  // Random firing
  useEffect(() => {
    if (paused) return
    const interval = setInterval(() => {
      if (Math.random() < 0.1) {
        setFiring(true)
        setTimeout(() => setFiring(false), 300)
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [paused])

  useFrame((state) => {
    if (paused || !groupRef.current) return
    const t = state.clock.elapsedTime
    groupRef.current.rotation.y = t * 0.2
    groupRef.current.position.y = position[1] + Math.sin(t + position[0]) * 0.3
  })

  // Generate dendrite directions
  const dendrites = useMemo(() => {
    return Array.from({ length: 6 }, (_, i) => {
      const theta = (i / 6) * Math.PI * 2
      const phi = Math.random() * Math.PI
      return {
        direction: [
          Math.sin(phi) * Math.cos(theta),
          Math.sin(phi) * Math.sin(theta),
          Math.cos(phi)
        ] as [number, number, number],
        length: 0.8 + Math.random() * 0.6
      }
    })
  }, [])

  return (
    <group ref={groupRef} position={position} scale={scale}>
      {/* Cell body (soma) */}
      <Sphere args={[0.3, 16, 16]}>
        <meshBasicMaterial color={firing ? '#ffffff' : color} transparent opacity={firing ? 1 : 0.8} />
      </Sphere>

      {/* Firing glow */}
      {firing && (
        <Sphere args={[0.6, 16, 16]}>
          <meshBasicMaterial color={color} transparent opacity={0.5} />
        </Sphere>
      )}

      {/* Dendrites */}
      {dendrites.map((d, i) => (
        <Line
          key={i}
          points={[
            [0, 0, 0],
            [d.direction[0] * d.length, d.direction[1] * d.length, d.direction[2] * d.length]
          ]}
          color={color}
          lineWidth={1}
          transparent
          opacity={0.5}
        />
      ))}
    </group>
  )
}

// Synaptic Firing - Electrical impulses traveling between neurons
function SynapticFiring({ paused }: { paused: boolean }) {
  const [impulses, setImpulses] = useState<Array<{
    id: number
    start: [number, number, number]
    end: [number, number, number]
    startTime: number
    color: string
  }>>([])
  const nextId = useRef(0)
  const lastFire = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Spawn new impulse every 0.5-1.5 seconds
    if (t - lastFire.current > 0.5 + Math.random()) {
      lastFire.current = t
      const systems = SOLAR_SYSTEMS
      const s1 = systems[Math.floor(Math.random() * systems.length)]
      const s2 = systems[Math.floor(Math.random() * systems.length)]

      if (s1.id !== s2.id) {
        setImpulses(prev => [...prev, {
          id: nextId.current++,
          start: s1.position,
          end: s2.position,
          startTime: t,
          color: s1.glowColor
        }])
      }
    }

    // Clean up old impulses
    setImpulses(prev => prev.filter(imp => t - imp.startTime < 2))
  })

  return (
    <group>
      {impulses.map(imp => (
        <SynapticImpulse key={imp.id} impulse={imp} />
      ))}
    </group>
  )
}

function SynapticImpulse({ impulse }: { impulse: {
  start: [number, number, number]
  end: [number, number, number]
  startTime: number
  color: string
}}) {
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (!meshRef.current) return
    const t = state.clock.elapsedTime
    const progress = Math.min((t - impulse.startTime) / 1.5, 1)

    const x = impulse.start[0] + (impulse.end[0] - impulse.start[0]) * progress
    const y = impulse.start[1] + (impulse.end[1] - impulse.start[1]) * progress + Math.sin(progress * Math.PI) * 2
    const z = impulse.start[2] + (impulse.end[2] - impulse.start[2]) * progress

    meshRef.current.position.set(x, y, z)
    meshRef.current.scale.setScalar(1 - progress * 0.5)
  })

  return (
    <group>
      <Sphere ref={meshRef} args={[0.15, 8, 8]} position={impulse.start}>
        <meshBasicMaterial color={impulse.color} />
      </Sphere>
    </group>
  )
}

// Neural Pathways - Glowing pathways representing neural connections
function NeuralPathways({ paused }: { paused: boolean }) {
  const pathwaysRef = useRef<THREE.Group>(null)

  // Generate pathway points between solar systems
  const pathways = useMemo(() => {
    const paths: Array<{
      points: [number, number, number][]
      color: string
    }> = []

    // Create curved paths between all solar systems
    for (let i = 0; i < SOLAR_SYSTEMS.length; i++) {
      for (let j = i + 1; j < SOLAR_SYSTEMS.length; j++) {
        const s1 = SOLAR_SYSTEMS[i]
        const s2 = SOLAR_SYSTEMS[j]

        // Create curved pathway with control points
        const midPoint: [number, number, number] = [
          (s1.position[0] + s2.position[0]) / 2 + (Math.random() - 0.5) * 5,
          (s1.position[1] + s2.position[1]) / 2 + Math.random() * 3,
          (s1.position[2] + s2.position[2]) / 2
        ]

        paths.push({
          points: [s1.position, midPoint, s2.position],
          color: s1.glowColor
        })
      }
    }
    return paths
  }, [])

  useFrame((state) => {
    if (paused || !pathwaysRef.current) return
    const t = state.clock.elapsedTime
    pathwaysRef.current.children.forEach((child, i) => {
      if (child instanceof THREE.Line) {
        const material = child.material as THREE.LineBasicMaterial
        material.opacity = 0.1 + Math.sin(t * 2 + i) * 0.05
      }
    })
  })

  return (
    <group ref={pathwaysRef}>
      {pathways.map((path, i) => (
        <Line
          key={i}
          points={path.points}
          color={path.color}
          lineWidth={0.5}
          transparent
          opacity={0.15}
        />
      ))}
    </group>
  )
}

// =============================================================================
// VIX STORM MODE - Chaos when VIX > 25
// =============================================================================

function VixStormMode({ vixValue = 15, paused }: { vixValue: number, paused: boolean }) {
  const isStormActive = vixValue > 25
  const stormIntensity = Math.min((vixValue - 25) / 25, 1) // 0-1 scale above 25

  if (!isStormActive) return null

  return (
    <group>
      <StormLightning intensity={stormIntensity} paused={paused} />
      <StormClouds intensity={stormIntensity} paused={paused} />
      <WarningPulse intensity={stormIntensity} />
    </group>
  )
}

function StormLightning({ intensity, paused }: { intensity: number, paused: boolean }) {
  const [bolts, setBolts] = useState<Array<{
    id: number
    start: THREE.Vector3
    end: THREE.Vector3
    startTime: number
  }>>([])
  const nextId = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // More frequent lightning with higher intensity
    if (Math.random() < 0.02 * (1 + intensity * 3)) {
      const systems = SOLAR_SYSTEMS
      const s1 = systems[Math.floor(Math.random() * systems.length)]
      const s2 = systems[Math.floor(Math.random() * systems.length)]

      if (s1.id !== s2.id) {
        setBolts(prev => [...prev, {
          id: nextId.current++,
          start: new THREE.Vector3(...s1.position),
          end: new THREE.Vector3(...s2.position),
          startTime: t
        }])
      }
    }

    // Clean up old bolts
    setBolts(prev => prev.filter(b => t - b.startTime < 0.3))
  })

  return (
    <group>
      {bolts.map(bolt => (
        <LightningBolt key={bolt.id} start={bolt.start} end={bolt.end} color="#ef4444" />
      ))}
    </group>
  )
}

function LightningBolt({ start, end, color }: { start: THREE.Vector3, end: THREE.Vector3, color: string }) {
  const points = useMemo(() => {
    const pts: [number, number, number][] = [[start.x, start.y, start.z]]
    const segments = 8
    for (let i = 1; i < segments; i++) {
      const t = i / segments
      const p = start.clone().lerp(end, t)
      // Add jagged offsets
      p.x += (Math.random() - 0.5) * 2
      p.y += (Math.random() - 0.5) * 2
      p.z += (Math.random() - 0.5) * 2
      pts.push([p.x, p.y, p.z])
    }
    pts.push([end.x, end.y, end.z])
    return pts
  }, [start, end])

  return (
    <>
      <Line points={points} color={color} lineWidth={3} transparent opacity={0.9} />
      <Line points={points} color="#ffffff" lineWidth={1} transparent opacity={1} />
    </>
  )
}

function StormClouds({ intensity, paused }: { intensity: number, paused: boolean }) {
  const cloud1Ref = useRef<THREE.Mesh>(null)
  const cloud2Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime
    const speed = 1 + intensity * 2

    if (cloud1Ref.current) {
      cloud1Ref.current.rotation.y = t * 0.1 * speed
      cloud1Ref.current.rotation.x = Math.sin(t * 0.5) * 0.2
    }
    if (cloud2Ref.current) {
      cloud2Ref.current.rotation.y = -t * 0.08 * speed
      cloud2Ref.current.rotation.z = Math.cos(t * 0.4) * 0.15
    }
  })

  return (
    <group>
      <Sphere ref={cloud1Ref} args={[25, 16, 16]} position={[0, 10, -20]}>
        <MeshDistortMaterial
          color="#7f1d1d"
          transparent
          opacity={0.15 * intensity}
          distort={0.5}
          speed={3}
        />
      </Sphere>
      <Sphere ref={cloud2Ref} args={[30, 16, 16]} position={[0, -8, -25]}>
        <MeshDistortMaterial
          color="#991b1b"
          transparent
          opacity={0.12 * intensity}
          distort={0.4}
          speed={2.5}
        />
      </Sphere>
    </group>
  )
}

function WarningPulse({ intensity }: { intensity: number }) {
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (meshRef.current) {
      const pulse = Math.sin(state.clock.elapsedTime * 4) * 0.5 + 0.5
      ;(meshRef.current.material as THREE.MeshBasicMaterial).opacity = 0.05 + pulse * 0.1 * intensity
    }
  })

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[50, 16, 16]} />
      <meshBasicMaterial color="#ef4444" transparent opacity={0.1} side={THREE.BackSide} />
    </mesh>
  )
}

// =============================================================================
// MARKET HOURS LIGHTING - Different ambiance based on market state
// =============================================================================

function MarketHoursLighting({ paused }: { paused?: boolean }) {
  const [marketState, setMarketState] = useState<'premarket' | 'open' | 'afterhours' | 'closed'>('open')
  const lightRef = useRef<THREE.PointLight>(null)

  useEffect(() => {
    const checkMarketHours = () => {
      const now = new Date()
      const hour = now.getUTCHours() - 5 // EST
      const day = now.getUTCDay()

      if (day === 0 || day === 6) {
        setMarketState('closed')
      } else if (hour >= 4 && hour < 9.5) {
        setMarketState('premarket')
      } else if (hour >= 9.5 && hour < 16) {
        setMarketState('open')
      } else if (hour >= 16 && hour < 20) {
        setMarketState('afterhours')
      } else {
        setMarketState('closed')
      }
    }

    checkMarketHours()
    const interval = setInterval(checkMarketHours, 60000)
    return () => clearInterval(interval)
  }, [])

  const lightConfig = {
    premarket: { color: '#f97316', intensity: 0.5, ambient: 0.08 },  // Orange dawn
    open: { color: '#22d3ee', intensity: 1.2, ambient: 0.12 },       // Bright cyan
    afterhours: { color: '#a855f7', intensity: 0.7, ambient: 0.1 },  // Purple twilight
    closed: { color: '#1e3a8a', intensity: 0.3, ambient: 0.05 },     // Dark blue night
  }

  const config = lightConfig[marketState]

  useFrame((state) => {
    if (paused || !lightRef.current) return
    // Gentle flicker
    lightRef.current.intensity = config.intensity + Math.sin(state.clock.elapsedTime * 2) * 0.1
  })

  return (
    <>
      <ambientLight intensity={config.ambient} />
      <pointLight ref={lightRef} position={[0, 15, 0]} color={config.color} intensity={config.intensity} />
      {marketState !== 'open' && (
        <Html position={[0, 8, 0]} center>
          <div className={`px-2 py-1 rounded text-xs font-bold ${
            marketState === 'premarket' ? 'bg-orange-500/20 text-orange-400' :
            marketState === 'afterhours' ? 'bg-purple-500/20 text-purple-400' :
            'bg-blue-900/40 text-blue-400'
          }`}>
            {marketState === 'premarket' ? '🌅 PRE-MARKET' :
             marketState === 'afterhours' ? '🌆 AFTER-HOURS' :
             '🌙 MARKET CLOSED'}
          </div>
        </Html>
      )}
    </>
  )
}

// =============================================================================
// 3D FLOATING CHARTS - Holographic candlestick display
// =============================================================================

function FloatingCandleChart({ paused }: { paused?: boolean }) {
  const groupRef = useRef<THREE.Group>(null)

  // Generate random candle data
  const candles = useMemo(() => {
    const data = []
    let price = 585
    for (let i = 0; i < 20; i++) {
      const open = price
      const change = (Math.random() - 0.5) * 5
      const close = open + change
      const high = Math.max(open, close) + Math.random() * 2
      const low = Math.min(open, close) - Math.random() * 2
      data.push({ open, close, high, low, isGreen: close > open })
      price = close
    }
    return data
  }, [])

  useFrame((state) => {
    if (paused || !groupRef.current) return
    groupRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.2) * 0.3
    groupRef.current.position.y = 5 + Math.sin(state.clock.elapsedTime * 0.5) * 0.5
  })

  const baseY = 580 // Base price for positioning

  return (
    <group ref={groupRef} position={[-8, 5, -6]}>
      {/* Chart background */}
      <mesh position={[2, 0, -0.1]}>
        <planeGeometry args={[6, 3]} />
        <meshBasicMaterial color="#0f172a" transparent opacity={0.7} />
      </mesh>

      {/* Candles */}
      {candles.map((candle, i) => {
        const x = i * 0.25 - 2
        const bodyHeight = Math.abs(candle.close - candle.open) * 0.3
        const bodyY = ((candle.open + candle.close) / 2 - baseY) * 0.3
        const wickHeight = (candle.high - candle.low) * 0.3
        const wickY = ((candle.high + candle.low) / 2 - baseY) * 0.3

        return (
          <group key={i} position={[x, 0, 0]}>
            {/* Wick */}
            <mesh position={[0, wickY, 0]}>
              <boxGeometry args={[0.02, wickHeight, 0.02]} />
              <meshBasicMaterial color={candle.isGreen ? '#22c55e' : '#ef4444'} />
            </mesh>
            {/* Body */}
            <mesh position={[0, bodyY, 0]}>
              <boxGeometry args={[0.12, Math.max(bodyHeight, 0.05), 0.08]} />
              <meshBasicMaterial color={candle.isGreen ? '#22c55e' : '#ef4444'} />
            </mesh>
          </group>
        )
      })}

      {/* Chart label */}
      <Html position={[2, 1.8, 0]} center>
        <div className="text-cyan-400 text-xs font-bold bg-black/50 px-2 py-0.5 rounded">
          SPY 1-MIN
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// METEOR SHOWER EVENT - Intense asteroid bombardment
// =============================================================================

function MeteorShower({ active, intensity = 1 }: { active: boolean, intensity?: number }) {
  const [meteors, setMeteors] = useState<Array<{
    id: number
    position: THREE.Vector3
    velocity: THREE.Vector3
    size: number
    startTime: number
  }>>([])
  const nextId = useRef(0)

  useFrame((state) => {
    if (!active) return
    const t = state.clock.elapsedTime

    // Spawn meteors rapidly
    if (Math.random() < 0.15 * intensity) {
      const angle = Math.random() * Math.PI * 2
      const radius = 25
      setMeteors(prev => [...prev, {
        id: nextId.current++,
        position: new THREE.Vector3(
          Math.cos(angle) * radius,
          10 + Math.random() * 10,
          Math.sin(angle) * radius
        ),
        velocity: new THREE.Vector3(
          -Math.cos(angle) * 8,
          -3 - Math.random() * 2,
          -Math.sin(angle) * 8
        ),
        size: 0.1 + Math.random() * 0.3,
        startTime: t
      }])
    }

    // Clean up old meteors
    setMeteors(prev => prev.filter(m => t - m.startTime < 3))
  })

  if (!active) return null

  return (
    <group>
      {meteors.map(meteor => (
        <Meteor key={meteor.id} meteor={meteor} />
      ))}
    </group>
  )
}

function Meteor({ meteor }: { meteor: { position: THREE.Vector3, velocity: THREE.Vector3, size: number, startTime: number } }) {
  const groupRef = useRef<THREE.Group>(null)
  const trailRef = useRef<any>(null)

  useFrame((state) => {
    if (!groupRef.current) return
    const elapsed = state.clock.elapsedTime - meteor.startTime

    groupRef.current.position.set(
      meteor.position.x + meteor.velocity.x * elapsed,
      meteor.position.y + meteor.velocity.y * elapsed,
      meteor.position.z + meteor.velocity.z * elapsed
    )

    if (trailRef.current) {
      trailRef.current.material.opacity = Math.max(0, 1 - elapsed / 3)
    }
  })

  return (
    <group ref={groupRef}>
      <mesh>
        <dodecahedronGeometry args={[meteor.size, 0]} />
        <meshBasicMaterial color="#f97316" />
      </mesh>
      {/* Trail */}
      <mesh ref={trailRef} position={[meteor.size * 2, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
        <coneGeometry args={[meteor.size * 0.5, meteor.size * 4, 8]} />
        <meshBasicMaterial color="#fbbf24" transparent opacity={0.6} />
      </mesh>
    </group>
  )
}

// =============================================================================
// GRAVITATIONAL LENSING - Black hole warps nearby objects
// =============================================================================

function GravitationalLensing({ position, strength = 1, paused }: { position: [number, number, number], strength?: number, paused: boolean }) {
  const lensRef = useRef<THREE.Mesh>(null)
  const distortRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    if (lensRef.current) {
      lensRef.current.rotation.z = t * 0.5
      const pulse = 1 + Math.sin(t * 2) * 0.1
      lensRef.current.scale.setScalar(pulse)
    }

    if (distortRef.current) {
      distortRef.current.rotation.y = t * 0.3
      distortRef.current.rotation.x = t * 0.2
    }
  })

  return (
    <group position={position}>
      {/* Accretion disk */}
      <mesh ref={lensRef} rotation={[Math.PI / 2.5, 0, 0]}>
        <torusGeometry args={[2, 0.5, 16, 64]} />
        <meshBasicMaterial color="#a855f7" transparent opacity={0.4} />
      </mesh>

      {/* Distortion sphere */}
      <Sphere ref={distortRef} args={[1.5, 32, 32]}>
        <MeshDistortMaterial
          color="#1e1b4b"
          emissive="#4c1d95"
          emissiveIntensity={0.5}
          distort={0.6}
          speed={4}
          transparent
          opacity={0.8}
        />
      </Sphere>

      {/* Event horizon */}
      <Sphere args={[0.8, 32, 32]}>
        <meshBasicMaterial color="#000000" />
      </Sphere>

      {/* Light bending ring */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.2, 0.05, 16, 64]} />
        <meshBasicMaterial color="#f59e0b" transparent opacity={0.8} />
      </mesh>
    </group>
  )
}

// =============================================================================
// TIME WARP CONTROLS - Speed up/slow down animations
// =============================================================================

const TimeWarpContext = createContext<{ timeScale: number, setTimeScale: (s: number) => void }>({
  timeScale: 1,
  setTimeScale: () => {}
})

function TimeWarpController({ children, timeScale }: { children: React.ReactNode, timeScale: number }) {
  // This wraps the scene and affects animation speeds
  return <>{children}</>
}

// =============================================================================
// ACHIEVEMENT SYSTEM - Floating trophies and badges
// =============================================================================

const ACHIEVEMENTS = [
  { id: 'first_trade', name: 'First Trade', icon: '🎯', color: '#22c55e' },
  { id: 'win_streak_5', name: '5 Win Streak', icon: '🔥', color: '#f97316' },
  { id: 'profit_1k', name: '$1K Profit', icon: '💰', color: '#fbbf24' },
  { id: 'profit_10k', name: '$10K Profit', icon: '💎', color: '#06b6d4' },
  { id: 'iron_hands', name: 'Iron Hands', icon: '🦾', color: '#a855f7' },
]

function AchievementDisplay({ achievements = [] }: { achievements?: string[] }) {
  const groupRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.1
    }
  })

  const earnedAchievements = ACHIEVEMENTS.filter(a => achievements.includes(a.id))

  if (earnedAchievements.length === 0) return null

  return (
    <group ref={groupRef} position={[0, -5, 0]}>
      {earnedAchievements.map((achievement, i) => {
        const angle = (i / earnedAchievements.length) * Math.PI * 2
        const radius = 6
        const x = Math.cos(angle) * radius
        const z = Math.sin(angle) * radius

        return (
          <group key={achievement.id} position={[x, 0, z]}>
            <Html center>
              <div
                className="text-2xl p-2 rounded-full animate-bounce"
                style={{ backgroundColor: `${achievement.color}33`, boxShadow: `0 0 20px ${achievement.color}` }}
              >
                {achievement.icon}
              </div>
            </Html>
          </group>
        )
      })}
    </group>
  )
}

// =============================================================================
// TRADE SUPERNOVA - Massive explosion on trade execution
// =============================================================================

function TradeSupernova({ active, position, type, onComplete }: {
  active: boolean
  position: THREE.Vector3
  type: 'profit' | 'loss'
  onComplete: () => void
}) {
  const groupRef = useRef<THREE.Group>(null)
  const sphereRef = useRef<THREE.Mesh>(null)
  const startTime = useRef(0)
  const [started, setStarted] = useState(false)

  const color = type === 'profit' ? '#22c55e' : '#ef4444'
  const particleColor = type === 'profit' ? '#fbbf24' : '#7f1d1d'

  useFrame((state) => {
    if (!active) return

    if (!started) {
      startTime.current = state.clock.elapsedTime
      setStarted(true)
    }

    const elapsed = state.clock.elapsedTime - startTime.current

    if (elapsed > 3) {
      onComplete()
      setStarted(false)
      return
    }

    if (groupRef.current) {
      groupRef.current.position.copy(position)
    }

    if (sphereRef.current) {
      // Rapid expansion then fade
      const scale = elapsed < 0.5 ? elapsed * 20 : 10 + (elapsed - 0.5) * 5
      sphereRef.current.scale.setScalar(scale)
      ;(sphereRef.current.material as THREE.MeshBasicMaterial).opacity = Math.max(0, 1 - elapsed / 2)
    }
  })

  if (!active) return null

  return (
    <group ref={groupRef}>
      {/* Expanding sphere */}
      <Sphere ref={sphereRef} args={[1, 32, 32]}>
        <meshBasicMaterial color={color} transparent opacity={0.8} />
      </Sphere>

      {/* Core flash */}
      <Sphere args={[0.5, 16, 16]}>
        <meshBasicMaterial color="#ffffff" />
      </Sphere>

      {/* Particle burst */}
      <SupernovaParticles color={particleColor} />
    </group>
  )
}

function SupernovaParticles({ color }: { color: string }) {
  const count = 100
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const startTime = useRef(0)
  const [started, setStarted] = useState(false)

  const particles = useMemo(() => {
    return Array.from({ length: count }, () => {
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      const speed = 5 + Math.random() * 10
      return {
        direction: new THREE.Vector3(
          Math.sin(phi) * Math.cos(theta),
          Math.sin(phi) * Math.sin(theta),
          Math.cos(phi)
        ),
        speed,
        size: 0.05 + Math.random() * 0.1
      }
    })
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    if (!meshRef.current) return

    if (!started) {
      startTime.current = state.clock.elapsedTime
      setStarted(true)
    }

    const elapsed = state.clock.elapsedTime - startTime.current

    particles.forEach((p, i) => {
      const dist = p.speed * elapsed
      dummy.position.copy(p.direction).multiplyScalar(dist)
      dummy.scale.setScalar(p.size * Math.max(0, 1 - elapsed / 3))
      dummy.updateMatrix()
      meshRef.current?.setMatrixAt(i, dummy.matrix)
    })
    meshRef.current.instanceMatrix.needsUpdate = true
  })

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 6, 6]} />
      <meshBasicMaterial color={color} />
    </instancedMesh>
  )
}

// =============================================================================
// FLY-THROUGH MODE - First person camera flying through scene
// =============================================================================

function FlyThroughCamera({ active, paused }: { active: boolean, paused: boolean }) {
  const { camera } = useThree()

  useFrame((state) => {
    if (!active || paused) return

    // Auto-fly path through the scene
    const t = state.clock.elapsedTime * 0.2
    const radius = 12 + Math.sin(t * 0.5) * 5
    const height = Math.sin(t * 0.3) * 5

    const x = Math.cos(t) * radius
    const y = height
    const z = Math.sin(t) * radius

    camera.position.set(x, y, z)
    camera.lookAt(0, 0, 0)
  })

  return null
}

// =============================================================================
// WORMHOLE TELEPORTER - Click to teleport camera
// =============================================================================

function WormholeTeleporter({
  position,
  targetPosition,
  onTeleport,
  label
}: {
  position: [number, number, number]
  targetPosition: [number, number, number]
  onTeleport: (target: THREE.Vector3) => void
  label: string
}) {
  const groupRef = useRef<THREE.Group>(null)
  const ringRef = useRef<THREE.Mesh>(null)
  const [hovered, setHovered] = useState(false)

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.z = state.clock.elapsedTime
    }
    if (ringRef.current) {
      ringRef.current.rotation.x = state.clock.elapsedTime * 0.5
      const scale = hovered ? 1.3 : 1
      ringRef.current.scale.setScalar(scale)
    }
  })

  return (
    <group
      ref={groupRef}
      position={position}
      onClick={() => onTeleport(new THREE.Vector3(...targetPosition))}
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
    >
      {/* Outer ring */}
      <mesh ref={ringRef} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1, 0.1, 16, 32]} />
        <meshBasicMaterial color={hovered ? '#22d3ee' : '#6366f1'} />
      </mesh>

      {/* Inner vortex */}
      <Sphere args={[0.7, 32, 32]}>
        <MeshDistortMaterial
          color="#1e1b4b"
          emissive="#4f46e5"
          emissiveIntensity={hovered ? 1.5 : 0.8}
          distort={0.5}
          speed={5}
        />
      </Sphere>

      {/* Label */}
      <Html position={[0, 1.5, 0]} center>
        <div className={`px-2 py-1 rounded text-xs font-bold transition-all ${
          hovered ? 'bg-cyan-500/40 text-white scale-110' : 'bg-black/50 text-cyan-400'
        }`}>
          {label}
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// SCREEN SHAKE EFFECT - Shakes on impacts
// =============================================================================

function ScreenShake({ active, intensity = 1 }: { active: boolean, intensity?: number }) {
  useFrame((state) => {
    if (!active) {
      state.camera.position.x = 0
      state.camera.position.y = 0
      return
    }

    const shake = intensity * 0.1
    state.camera.position.x += (Math.random() - 0.5) * shake
    state.camera.position.y += (Math.random() - 0.5) * shake
  })

  return null
}

// =============================================================================
// NEWS COMET STREAM - Headlines flying by as comets
// =============================================================================

const SAMPLE_HEADLINES = [
  { text: 'Fed Holds Rates Steady', sentiment: 'neutral' },
  { text: 'NVDA Beats Earnings!', sentiment: 'bullish' },
  { text: 'Market Rally Continues', sentiment: 'bullish' },
  { text: 'VIX Spikes on Uncertainty', sentiment: 'bearish' },
  { text: 'SPY Hits All-Time High', sentiment: 'bullish' },
  { text: 'Tech Sector Pullback', sentiment: 'bearish' },
  { text: 'Jobs Report Exceeds', sentiment: 'bullish' },
  { text: 'Oil Prices Surge', sentiment: 'neutral' },
]

function NewsCometStream({ paused }: { paused: boolean }) {
  const [comets, setComets] = useState<Array<{
    id: number
    headline: typeof SAMPLE_HEADLINES[0]
    position: THREE.Vector3
    startTime: number
  }>>([])
  const nextId = useRef(0)
  const lastSpawn = useRef(0)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    // Spawn news comet every 20-40 seconds
    if (t - lastSpawn.current > 20 + Math.random() * 20) {
      lastSpawn.current = t
      const headline = SAMPLE_HEADLINES[Math.floor(Math.random() * SAMPLE_HEADLINES.length)]

      setComets(prev => [...prev, {
        id: nextId.current++,
        headline,
        position: new THREE.Vector3(25, 5 + Math.random() * 5, -10 + Math.random() * 5),
        startTime: t
      }])
    }

    // Clean up
    setComets(prev => prev.filter(c => t - c.startTime < 10))
  })

  return (
    <group>
      {comets.map(comet => (
        <NewsComet key={comet.id} comet={comet} />
      ))}
    </group>
  )
}

function NewsComet({ comet }: { comet: { headline: typeof SAMPLE_HEADLINES[0], position: THREE.Vector3, startTime: number } }) {
  const groupRef = useRef<THREE.Group>(null)

  const color = comet.headline.sentiment === 'bullish' ? '#22c55e' :
                comet.headline.sentiment === 'bearish' ? '#ef4444' : '#fbbf24'

  useFrame((state) => {
    if (!groupRef.current) return
    const elapsed = state.clock.elapsedTime - comet.startTime

    groupRef.current.position.set(
      comet.position.x - elapsed * 4,
      comet.position.y + Math.sin(elapsed * 2) * 0.5,
      comet.position.z
    )
  })

  return (
    <group ref={groupRef}>
      <Html center>
        <div
          className="px-3 py-1.5 rounded-full text-sm font-bold whitespace-nowrap animate-pulse"
          style={{
            backgroundColor: `${color}22`,
            color,
            boxShadow: `0 0 20px ${color}66`,
            border: `1px solid ${color}44`
          }}
        >
          {comet.headline.sentiment === 'bullish' ? '📈 ' :
           comet.headline.sentiment === 'bearish' ? '📉 ' : '📊 '}
          {comet.headline.text}
        </div>
      </Html>

      {/* Trail */}
      <mesh position={[2, 0, 0]}>
        <planeGeometry args={[3, 0.1]} />
        <meshBasicMaterial color={color} transparent opacity={0.3} />
      </mesh>
    </group>
  )
}

// =============================================================================
// HIDDEN MESSAGE (Easter Egg)
// =============================================================================

function HiddenMessage({ visible }: { visible: boolean }) {
  const groupRef = useRef<THREE.Group>(null)

  useFrame((state) => {
    if (groupRef.current && visible) {
      groupRef.current.rotation.y = state.clock.elapsedTime
      groupRef.current.position.y = Math.sin(state.clock.elapsedTime) * 0.5
    }
  })

  if (!visible) return null

  return (
    <group ref={groupRef} position={[0, 0, 0]}>
      <Html center>
        <div className="text-2xl animate-pulse select-none">
          🚀 ALPHA MODE ACTIVATED 🚀
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// BREATHING CORE - GEX Reactive
// =============================================================================

function BreathingCore({ gexValue = 0, vixValue = 15, paused = false }: { gexValue?: number, vixValue?: number, paused?: boolean }) {
  const groupRef = useRef<THREE.Group>(null)
  const rimRef = useRef<THREE.Mesh>(null)
  const innerRef = useRef<THREE.Mesh>(null)

  const gexScale = 1 + gexValue * 0.3
  const pulseSpeed = 0.5 + (vixValue / 30) * 1.5

  useFrame((state) => {
    if (paused) return
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

  const coreColor = gexValue > 0 ? '#0c2919' : gexValue < 0 ? '#290c19' : COLORS.coreCenter
  const rimColor = gexValue > 0 ? '#22eeb8' : gexValue < 0 ? '#ee2268' : COLORS.coreRim

  return (
    <group ref={groupRef}>
      <Sphere ref={rimRef} args={[1.8, 64, 64]}>
        <meshBasicMaterial color={rimColor} transparent opacity={0.2} />
      </Sphere>

      <Sphere args={[1.5, 48, 48]}>
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.1} />
      </Sphere>

      <Sphere ref={innerRef} args={[1, 64, 64]}>
        <MeshDistortMaterial
          color={coreColor}
          emissive={rimColor}
          emissiveIntensity={2.5 + Math.abs(gexValue)}
          roughness={0.1}
          metalness={0.9}
          distort={0.2 + (vixValue / 100) * 0.2}
          speed={paused ? 0 : 2 + vixValue / 20}
        />
      </Sphere>

      <Sphere args={[0.35, 32, 32]}>
        <meshBasicMaterial color={COLORS.particleBright} transparent opacity={0.95} />
      </Sphere>

      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.3, 0.02, 16, 100]} />
        <meshBasicMaterial color={rimColor} transparent opacity={0.7} />
      </mesh>

      <Html position={[0, -2.2, 0]} center distanceFactor={8}>
        <div className="text-cyan-300 text-sm font-bold whitespace-nowrap bg-black/60 px-3 py-1 rounded-full select-none border border-cyan-500/30">
          GEX CORE
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// CORE VORTEX
// =============================================================================

function CoreVortex({ paused = false }: { paused?: boolean }) {
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
    if (paused) return
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
  mousePos,
  gravityWell,
  paused = false
}: {
  phi: number
  theta: number
  baseRadius: number
  length: number
  speed: number
  particleCount?: number
  mousePos: React.MutableRefObject<THREE.Vector3>
  gravityWell: THREE.Vector3 | null
  paused?: boolean
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
    if (paused) return
    const t = state.clock.elapsedTime
    if (groupRef.current) {
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

      // Gravity well attraction
      if (gravityWell) {
        const wellDist = fiberEnd.distanceTo(gravityWell)
        if (wellDist < 8) {
          const attraction = (8 - wellDist) / 8 * 0.15
          const dir = gravityWell.clone().sub(fiberEnd).normalize()
          swayX += dir.x * attraction
          swayY += dir.y * attraction
        }
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
          paused={paused}
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
  phi,
  paused = false
}: {
  curve: THREE.QuadraticBezierCurve3
  offset: number
  speed: number
  phi: number
  paused?: boolean
}) {
  const meshRef = useRef<THREE.Mesh>(null)
  const glowRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
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

function RadialFiberBurst({
  mousePos,
  gravityWell,
  performanceMode,
  paused = false
}: {
  mousePos: React.MutableRefObject<THREE.Vector3>
  gravityWell: THREE.Vector3 | null
  performanceMode: boolean
  paused?: boolean
}) {
  const fibers = useMemo(() => {
    const result = []
    const fiberCount = performanceMode ? 30 : 60
    const goldenAngle = Math.PI * (3 - Math.sqrt(5))

    for (let i = 0; i < fiberCount; i++) {
      const y = 1 - (i / (fiberCount - 1)) * 2
      const theta = goldenAngle * i
      const phi = Math.acos(y)
      const length = 4 + Math.random() * 4
      const speed = 0.3 + Math.random() * 0.4
      const particleCount = performanceMode ? 1 : 2 + Math.floor(Math.random() * 3)

      result.push({ phi, theta, length, speed, particleCount })
    }
    return result
  }, [performanceMode])

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
          gravityWell={gravityWell}
          paused={paused}
        />
      ))}
    </group>
  )
}

// =============================================================================
// INNER DENSE SHELL
// =============================================================================

function InnerDenseShell({
  mousePos,
  gravityWell,
  performanceMode,
  paused = false
}: {
  mousePos: React.MutableRefObject<THREE.Vector3>
  gravityWell: THREE.Vector3 | null
  performanceMode: boolean
  paused?: boolean
}) {
  const fibers = useMemo(() => {
    const result = []
    const fiberCount = performanceMode ? 15 : 30
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
  }, [performanceMode])

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
          gravityWell={gravityWell}
          paused={paused}
        />
      ))}
    </group>
  )
}

// =============================================================================
// MULTIPLE PULSE WAVES
// =============================================================================

function MultiplePulseWaves({ vixValue = 15, paused = false }: { vixValue?: number, paused?: boolean }) {
  const ring1Ref = useRef<THREE.Mesh>(null)
  const ring2Ref = useRef<THREE.Mesh>(null)
  const ring3Ref = useRef<THREE.Mesh>(null)

  const pulseInterval = Math.max(1.5, 4 - vixValue / 15)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime

    const pulse1 = (t % pulseInterval) / pulseInterval
    if (ring1Ref.current) {
      ring1Ref.current.scale.setScalar(1 + pulse1 * 10)
      ;(ring1Ref.current.material as THREE.MeshBasicMaterial).opacity = 0.5 * (1 - pulse1)
    }

    const pulse2 = ((t + pulseInterval / 3) % pulseInterval) / pulseInterval
    if (ring2Ref.current) {
      ring2Ref.current.scale.setScalar(1 + pulse2 * 10)
      ;(ring2Ref.current.material as THREE.MeshBasicMaterial).opacity = 0.4 * (1 - pulse2)
    }

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

function LightningArcs({ paused = false }: { paused?: boolean }) {
  const [arcs, setArcs] = useState<Array<{ start: THREE.Vector3, end: THREE.Vector3, id: number }>>([])
  const nextId = useRef(0)

  useFrame(() => {
    if (paused) return
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
        <LightningArc key={arc.id} start={arc.start} end={arc.end} paused={paused} />
      ))}
    </group>
  )
}

function LightningArc({ start, end, paused = false }: { start: THREE.Vector3, end: THREE.Vector3, paused?: boolean }) {
  const [opacity, setOpacity] = useState(1)
  const birthTime = useRef(0)

  const points = useMemo(() => {
    const pts: [number, number, number][] = []
    const segments = 8
    for (let i = 0; i <= segments; i++) {
      const t = i / segments
      const p = start.clone().lerp(end, t)
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
    if (paused) return
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

function LensFlare({ paused = false }: { paused?: boolean }) {
  const flare1Ref = useRef<THREE.Mesh>(null)
  const flare2Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
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

function HolographicScanlines({ paused = false }: { paused?: boolean }) {
  const line1Ref = useRef<THREE.Mesh>(null)
  const line2Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
    const t = state.clock.elapsedTime
    if (line1Ref.current) {
      line1Ref.current.position.y = ((t * 2) % 20) - 10
    }
    if (line2Ref.current) {
      line2Ref.current.position.y = ((t * 2 + 10) % 20) - 10
    }
  })

  return (
    <group>
      <mesh ref={line1Ref}>
        <planeGeometry args={[30, 0.02]} />
        <meshBasicMaterial color={COLORS.coreRim} transparent opacity={0.1} side={THREE.DoubleSide} />
      </mesh>
      <mesh ref={line2Ref}>
        <planeGeometry args={[30, 0.015]} />
        <meshBasicMaterial color={COLORS.fiberInner} transparent opacity={0.08} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

// =============================================================================
// GLITCH EFFECT
// =============================================================================

function GlitchEffect({ paused = false }: { paused?: boolean }) {
  const [glitching, setGlitching] = useState(false)
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame(() => {
    if (paused) return
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

function OuterParticleRing({ performanceMode, paused = false }: { performanceMode: boolean, paused?: boolean }) {
  const count = performanceMode ? 75 : 150
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const groupRef = useRef<THREE.Group>(null)

  const particles = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      angle: (i / count) * Math.PI * 2,
      radius: 9 + (Math.random() - 0.5) * 1,
      yOffset: (Math.random() - 0.5) * 0.5,
      speed: 0.05 + Math.random() * 0.03,
    }))
  }, [count])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    if (paused) return
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
      mid.y = 1.5

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
  onClick,
  onDoubleClick,
  paused = false
}: {
  id: string
  name: string
  angle: number
  status?: string
  onClick?: () => void
  onDoubleClick?: () => void
  paused?: boolean
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
    if (paused) return
    const t = state.clock.elapsedTime
    if (groupRef.current) {
      groupRef.current.position.y = Math.sin(t * 1.2 + angle) * 0.2
    }

    if (flareRef.current && isActive) {
      const pulse = Math.sin(t * 4) * 0.5 + 0.5
      flareRef.current.scale.setScalar(0.5 + pulse * 0.3)
      ;(flareRef.current.material as THREE.MeshBasicMaterial).opacity = 0.3 + pulse * 0.2
    }
  })

  return (
    <group ref={groupRef} position={[x, 0, z]}>
      {isActive && (
        <Sphere ref={flareRef} args={[1, 16, 16]}>
          <meshBasicMaterial color={color} transparent opacity={0.4} />
        </Sphere>
      )}

      <Sphere args={[0.35, 16, 16]}>
        <meshBasicMaterial color={color} transparent opacity={hovered ? 0.5 : 0.25} />
      </Sphere>

      <Sphere
        args={[0.2, 16, 16]}
        onClick={onClick}
        onDoubleClick={onDoubleClick}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <meshBasicMaterial color={hovered ? COLORS.particleBright : color} />
      </Sphere>

      {status === 'trading' && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.4, 0.02, 16, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.8} />
        </mesh>
      )}

      <Html position={[0, 0.7, 0]} center distanceFactor={12}>
        <div
          className="text-xs font-bold whitespace-nowrap select-none px-2 py-0.5 rounded bg-black/50 cursor-pointer"
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

function SparkleField({ performanceMode, paused = false }: { performanceMode: boolean, paused?: boolean }) {
  const count = performanceMode ? 60 : 120
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
  }, [count])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    if (paused) return
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

function EnergyAccumulation({ paused = false }: { paused?: boolean }) {
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
    if (paused) return
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

function NebulaBackdrop({ paused = false }: { paused?: boolean }) {
  const mesh1Ref = useRef<THREE.Mesh>(null)
  const mesh2Ref = useRef<THREE.Mesh>(null)
  const mesh3Ref = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    if (paused) return
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

function AmbientParticles({ performanceMode, paused = false }: { performanceMode: boolean, paused?: boolean }) {
  const count = performanceMode ? 150 : 350
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
  }, [count])

  const dummy = useMemo(() => new THREE.Object3D(), [])

  useFrame((state) => {
    if (paused) return
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
  onPlanetClick?: (planetName: string) => void
  gexValue?: number
  vixValue?: number
  spotPrice?: number
  pnlValue?: number
  pnlPercent?: number
  signalStrength?: number
  shockwaveTime: number
  performanceMode: boolean
  paused: boolean
  setPaused: (p: boolean) => void
  gravityWell: THREE.Vector3 | null
  tradeExplosion: { position: THREE.Vector3, type: 'buy' | 'sell' } | null
  setTradeExplosion: (e: { position: THREE.Vector3, type: 'buy' | 'sell' } | null) => void
  celebrationActive: boolean
  setCelebrationActive: (a: boolean) => void
  konamiActive: boolean
  zoomTarget: THREE.Vector3 | null
  setZoomTarget: (t: THREE.Vector3 | null) => void
  stockPrices: Array<{ symbol: string, price: number, change: number }>
}

function Scene({
  botStatus,
  onNodeClick,
  onPlanetClick,
  gexValue = 0,
  vixValue = 15,
  spotPrice,
  pnlValue = 0,
  pnlPercent = 0,
  signalStrength = 0.5,
  shockwaveTime,
  performanceMode,
  paused,
  setPaused,
  gravityWell,
  tradeExplosion,
  setTradeExplosion,
  celebrationActive,
  setCelebrationActive,
  konamiActive,
  zoomTarget,
  setZoomTarget,
  stockPrices
}: SceneProps) {
  const { mouse3D } = useMousePosition()
  const controlsRef = useRef<any>(null)

  const handleNodeDoubleClick = useCallback((nodeId: string) => {
    const node = BOT_NODES.find(n => n.id === nodeId)
    if (node) {
      const radius = 5
      const target = new THREE.Vector3(
        Math.cos(node.angle) * radius,
        0,
        Math.sin(node.angle) * radius
      )
      setZoomTarget(target)
    }
  }, [setZoomTarget])

  // Handler for clicking on solar systems - fly camera to that system
  const handleSolarSystemClick = useCallback((systemId: string, position: [number, number, number]) => {
    const target = new THREE.Vector3(position[0], position[1], position[2])
    setZoomTarget(target)
  }, [setZoomTarget])

  return (
    <>
      {/* Camera Controller */}
      <CameraController
        controlsRef={controlsRef}
        zoomTarget={zoomTarget}
        paused={paused}
        setPaused={setPaused}
      />

      {/* Lighting */}
      <ambientLight intensity={0.1} />
      <pointLight position={[0, 0, 0]} intensity={5} color={COLORS.coreRim} />
      <pointLight position={[10, 10, 10]} intensity={1.2} color="#ffffff" />
      <pointLight position={[-10, -10, -10]} intensity={0.6} color={COLORS.fiberInner} />

      {/* Background */}
      <Stars radius={120} depth={120} count={performanceMode ? 5000 : 10000} factor={4} saturation={0} fade speed={paused ? 0 : 0.15} />
      <NebulaBackdrop paused={paused} />
      <ConstellationLines />
      <MatrixRain performanceMode={performanceMode} />

      {/* Lens flare */}
      <LensFlare paused={paused} />

      {/* Core */}
      <BreathingCore gexValue={gexValue} vixValue={vixValue} paused={paused} />
      <CoreVortex paused={paused} />

      {/* Pulse effects */}
      <MultiplePulseWaves vixValue={vixValue} paused={paused} />
      <WaveformRings vixValue={vixValue} />
      <ClickShockwave shockwaveTime={shockwaveTime} />

      {/* Fibers */}
      <RadialFiberBurst mousePos={mouse3D} gravityWell={gravityWell} performanceMode={performanceMode} paused={paused} />
      <InnerDenseShell mousePos={mouse3D} gravityWell={gravityWell} performanceMode={performanceMode} paused={paused} />
      <PlasmaTendrils />
      <OrbitTrails />

      {/* Bot network */}
      <ConnectingArcs />
      <LightningArcs paused={paused} />

      {/* Particles */}
      <EnergyAccumulation paused={paused} />
      <SparkleField performanceMode={performanceMode} paused={paused} />
      <OuterParticleRing performanceMode={performanceMode} paused={paused} />
      <AmbientParticles performanceMode={performanceMode} paused={paused} />

      {/* Effects */}
      <HolographicScanlines paused={paused} />
      <GlitchEffect paused={paused} />
      <AlertPulse active={true} botStatus={botStatus} />

      {/* Gravity well */}
      {gravityWell && <GravityWell position={gravityWell} active={true} />}

      {/* Trade explosion */}
      {tradeExplosion && (
        <TradeExplosion
          position={tradeExplosion.position}
          type={tradeExplosion.type}
          active={true}
          onComplete={() => setTradeExplosion(null)}
        />
      )}

      {/* Celebration */}
      <SuccessCelebration active={celebrationActive} onComplete={() => setCelebrationActive(false)} />

      {/* Easter egg */}
      <HiddenMessage visible={konamiActive} />

      {/* Data displays */}
      <FloatingMarketStats spotPrice={spotPrice} gexValue={gexValue} vixValue={vixValue} />
      <FloatingPnLOrb pnlValue={pnlValue} pnlPercent={pnlPercent} />
      <SignalStrengthBars strength={signalStrength} />
      <MarketMoodRing gexValue={gexValue} vixValue={vixValue} />

      {/* Cosmic features */}
      <AsteroidField paused={paused} stockPrices={stockPrices} />
      <CometWithTrail paused={paused} />
      <AsteroidBelt performanceMode={performanceMode} />
      <ShootingStars paused={paused} />
      <SolarFlares vixValue={vixValue} paused={paused} />
      <AuroraBorealis paused={paused} />
      <BlackHoleWarp paused={paused} />
      <HolographicTickerTape stockPrices={stockPrices} />
      <RocketLaunches botStatus={botStatus} />
      <SatelliteOrbiters />
      <EnergyShields paused={paused} />
      <WormholePortals botStatus={botStatus} />
      <QuantumEntanglement botStatus={botStatus} paused={paused} />
      <BinaryStar paused={paused} />
      <SpaceStation spotPrice={spotPrice || 585} gexValue={gexValue} vixValue={vixValue} />
      <MoonPhases paused={paused} />
      <NebulaStorm vixValue={vixValue} paused={paused} />

      {/* Neural Network Visual Layer */}
      <NeuralBrainStructure paused={paused} />
      <NeuralNeurons paused={paused} />
      <SynapticFiring paused={paused} />
      <NeuralPathways paused={paused} />

      {/* Solar Systems with Neural Synapse Connections */}
      <SolarSystemsContainer paused={paused} onSystemClick={handleSolarSystemClick} onPlanetClick={onPlanetClick} />

      {/* WOW FACTOR FEATURES */}
      {/* VIX Storm Mode - chaos when VIX > 25 */}
      <VixStormMode vixValue={vixValue} paused={paused} />

      {/* Market Hours Lighting - ambient changes based on market state */}
      <MarketHoursLighting paused={paused} />

      {/* 3D Floating Charts - holographic candlesticks */}
      <FloatingCandleChart paused={paused} />

      {/* News Comet Stream - headlines flying by */}
      <NewsCometStream paused={paused} />

      {/* Gravitational Lensing Black Hole */}
      <GravitationalLensing position={[15, -5, -18]} paused={paused} />

      {/* Bot nodes */}
      {BOT_NODES.map((node) => (
        <BotNodeWithFlare
          key={node.id}
          id={node.id}
          name={node.name}
          angle={node.angle}
          status={botStatus[node.id as keyof BotStatus] || 'idle'}
          onClick={() => onNodeClick?.(node.id)}
          onDoubleClick={() => handleNodeDoubleClick(node.id)}
          paused={paused}
        />
      ))}

      {/* Camera controls */}
      <OrbitControls
        ref={controlsRef}
        enablePan={true}
        enableZoom={true}
        minDistance={2}
        maxDistance={80}
        autoRotate={!paused}
        autoRotateSpeed={0.25}
        maxPolarAngle={Math.PI * 0.95}
        minPolarAngle={Math.PI * 0.05}
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
// CONTROL PANEL OVERLAY
// =============================================================================

function ControlPanel({
  theme,
  setTheme,
  performanceMode,
  setPerformanceMode,
  paused,
  setPaused,
  onScreenshot,
  onFullscreen,
  isFullscreen
}: {
  theme: ColorTheme
  setTheme: (t: ColorTheme) => void
  performanceMode: boolean
  setPerformanceMode: (p: boolean) => void
  paused: boolean
  setPaused: (p: boolean) => void
  onScreenshot: () => void
  onFullscreen: () => void
  isFullscreen: boolean
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="absolute top-4 right-4 z-10">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-10 h-10 bg-black/70 border border-cyan-500/30 rounded-lg flex items-center justify-center text-cyan-400 hover:bg-cyan-500/20 transition-colors backdrop-blur"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>

      {expanded && (
        <div className="mt-2 bg-black/80 border border-cyan-500/30 rounded-lg p-4 backdrop-blur min-w-[200px]">
          <h3 className="text-cyan-400 font-bold mb-3 text-sm">NEXUS Controls</h3>

          {/* Theme selector */}
          <div className="mb-3">
            <div className="text-xs text-gray-400 mb-1">Theme</div>
            <div className="flex gap-1">
              {(['cyan', 'purple', 'green', 'red'] as ColorTheme[]).map(t => (
                <button
                  key={t}
                  onClick={() => setTheme(t)}
                  className={`w-6 h-6 rounded-full border-2 transition-all ${theme === t ? 'border-white scale-110' : 'border-transparent'}`}
                  style={{ backgroundColor: COLOR_THEMES[t].accent }}
                />
              ))}
            </div>
          </div>

          {/* Performance mode */}
          <div className="mb-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={performanceMode}
                onChange={(e) => setPerformanceMode(e.target.checked)}
                className="w-4 h-4 rounded border-cyan-500/30 bg-black/50 text-cyan-500"
              />
              <span className="text-xs text-gray-300">Performance Mode</span>
            </label>
          </div>

          {/* Pause */}
          <div className="mb-3">
            <button
              onClick={() => setPaused(!paused)}
              className={`w-full py-1.5 rounded text-xs font-medium transition-colors ${paused ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30' : 'bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30'}`}
            >
              {paused ? '▶ Resume' : '⏸ Pause'}
            </button>
          </div>

          {/* Screenshot */}
          <div className="mb-3">
            <button
              onClick={onScreenshot}
              className="w-full py-1.5 rounded text-xs font-medium bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition-colors"
            >
              📷 Screenshot
            </button>
          </div>

          {/* Fullscreen */}
          <div>
            <button
              onClick={onFullscreen}
              className="w-full py-1.5 rounded text-xs font-medium bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition-colors"
            >
              {isFullscreen ? '⊠ Exit Fullscreen' : '⛶ Fullscreen'}
            </button>
          </div>

          {/* Keyboard shortcuts hint */}
          <div className="mt-3 pt-3 border-t border-cyan-500/20">
            <div className="text-xs text-gray-500">
              <div>← → ↑ ↓ Rotate</div>
              <div>Space: Pause</div>
              <div>R: Reset view</div>
              <div>Double-click: Zoom to node</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// SOLAR SYSTEM NAVIGATOR - Quick travel buttons to each solar system
// =============================================================================

function SolarSystemNavigator({
  onNavigate,
  currentSystem
}: {
  onNavigate: (systemId: string, position: [number, number, number]) => void
  currentSystem: string | null
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="absolute bottom-4 left-4 z-10">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-10 h-10 bg-black/70 border border-purple-500/30 rounded-lg flex items-center justify-center text-purple-400 hover:bg-purple-500/20 transition-colors backdrop-blur mb-2"
        title="Solar System Navigator"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </button>

      {expanded && (
        <div className="bg-black/80 border border-purple-500/30 rounded-lg p-3 backdrop-blur min-w-[180px]">
          <h3 className="text-purple-400 font-bold mb-3 text-xs tracking-wider flex items-center gap-2">
            <span className="text-lg">🚀</span> SOLAR SYSTEMS
          </h3>

          <div className="space-y-1.5">
            {SOLAR_SYSTEMS.map(system => (
              <button
                key={system.id}
                onClick={() => onNavigate(system.id, system.position)}
                className={`w-full py-2 px-3 rounded text-xs font-medium transition-all flex items-center gap-2 ${
                  currentSystem === system.id
                    ? 'bg-gradient-to-r from-purple-500/40 to-cyan-500/40 text-white border border-purple-500/50'
                    : 'bg-gray-800/50 text-gray-300 hover:bg-gray-700/50 border border-transparent'
                }`}
              >
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: system.sunColor, boxShadow: `0 0 8px ${system.glowColor}` }}
                />
                <span className="flex-1 text-left">{system.name}</span>
                <span className="text-gray-500 text-[10px]">{system.subtitle}</span>
              </button>
            ))}
          </div>

          <div className="mt-3 pt-2 border-t border-purple-500/20">
            <button
              onClick={() => onNavigate('home', [0, 0, 0])}
              className="w-full py-1.5 rounded text-xs font-medium bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition-colors"
            >
              🏠 Return to Center
            </button>
          </div>

          <div className="mt-2 text-[10px] text-gray-500">
            Click on any solar system to fly there
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// PAUSE INDICATOR
// =============================================================================

function PauseIndicator({ paused }: { paused: boolean }) {
  if (!paused) return null

  return (
    <div className="absolute top-4 left-4 z-10 bg-yellow-500/20 border border-yellow-500/50 rounded-lg px-3 py-1.5 flex items-center gap-2">
      <span className="text-yellow-400 text-lg">⏸</span>
      <span className="text-yellow-400 text-sm font-medium">PAUSED</span>
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
  spotPrice,
  pnlValue = 0,
  pnlPercent = 0,
  signalStrength = 0.5,
  onTrade
}: Nexus3DProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [mounted, setMounted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shockwaveTime, setShockwaveTime] = useState(0)
  const [theme, setTheme] = useState<ColorTheme>('cyan')
  const [performanceMode, setPerformanceMode] = useState(false)
  const [paused, setPaused] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [gravityWell, setGravityWell] = useState<THREE.Vector3 | null>(null)
  const [tradeExplosion, setTradeExplosion] = useState<{ position: THREE.Vector3, type: 'buy' | 'sell' } | null>(null)
  const [celebrationActive, setCelebrationActive] = useState(false)
  const [konamiActive, setKonamiActive] = useState(false)
  const [shakeActive, setShakeActive] = useState(false)
  const [zoomTarget, setZoomTarget] = useState<THREE.Vector3 | null>(null)
  const [currentSystem, setCurrentSystem] = useState<string | null>(null)
  const holdTimer = useRef<NodeJS.Timeout | null>(null)

  // Handler to navigate to a solar system
  const handleNavigateToSystem = useCallback((systemId: string, position: [number, number, number]) => {
    const target = new THREE.Vector3(position[0], position[1], position[2])
    setZoomTarget(target)
    setCurrentSystem(systemId === 'home' ? null : systemId)
  }, [])

  // Handler to navigate when clicking a planet
  const handlePlanetClick = useCallback((planetName: string) => {
    const route = PLANET_ROUTES[planetName]
    if (route && onNodeClick) {
      // Use the route path (strip the leading /)
      onNodeClick(route)
    }
  }, [onNodeClick])

  // Fetch real-time stock prices
  const { prices: stockPrices, isLive: stockPricesLive } = useStockPrices()

  // Update global COLORS when theme changes
  useEffect(() => {
    COLORS = COLOR_THEMES[theme]
  }, [theme])

  // Konami code easter egg
  useKonamiCode(() => {
    setKonamiActive(true)
    setCelebrationActive(true)
    setTimeout(() => setKonamiActive(false), 5000)
  })

  // Check WebGL support
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

  // Fullscreen change listener
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }, [])

  // Click handler for shockwave
  const handleClick = useCallback(() => {
    setShockwaveTime(Date.now() / 1000)
  }, [])

  // Hold handler for gravity well
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const x = (e.clientX / window.innerWidth) * 2 - 1
    const y = -(e.clientY / window.innerHeight) * 2 + 1

    holdTimer.current = setTimeout(() => {
      setGravityWell(new THREE.Vector3(x * 8, y * 8, 0))
    }, 500)
  }, [])

  const handleMouseUp = useCallback(() => {
    if (holdTimer.current) {
      clearTimeout(holdTimer.current)
      holdTimer.current = null
    }
    setGravityWell(null)
  }, [])

  // Screenshot handler
  const handleScreenshot = useCallback(() => {
    const canvas = containerRef.current?.querySelector('canvas')
    if (canvas) {
      const link = document.createElement('a')
      link.download = `nexus-${Date.now()}.png`
      link.href = canvas.toDataURL('image/png')
      link.click()
    }
  }, [])

  // Fullscreen handler
  const handleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen()
    } else {
      document.exitFullscreen()
    }
  }, [])

  // Trigger trade explosion (can be called from parent)
  useEffect(() => {
    if (onTrade) {
      // This is just to show the effect can be triggered
      // Parent can call these methods via ref if needed
    }
  }, [onTrade])

  if (error) {
    return <ErrorFallback message={error} />
  }

  if (!mounted) {
    return <LoadingFallback />
  }

  const errorFallbackElement = <ErrorFallback message="A rendering error occurred. Please refresh." />

  return (
    <Canvas3DErrorBoundary fallback={errorFallbackElement}>
      <div
        ref={containerRef}
        className={`w-full h-full bg-[#030712] relative ${className} ${shakeActive ? 'animate-shake' : ''}`}
        onClick={handleClick}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {/* Control Panel */}
        <ControlPanel
          theme={theme}
          setTheme={setTheme}
          performanceMode={performanceMode}
          setPerformanceMode={setPerformanceMode}
          paused={paused}
          setPaused={setPaused}
          onScreenshot={handleScreenshot}
          onFullscreen={handleFullscreen}
          isFullscreen={isFullscreen}
        />

        {/* Back to Dashboard Button */}
        <div className="absolute top-4 left-4 z-20">
          <button
            onClick={() => onNodeClick?.('/')}
            className="group flex items-center gap-2 bg-gray-900/80 hover:bg-gray-800 border border-cyan-500/30 hover:border-cyan-400/60 rounded-lg px-4 py-2 text-sm transition-all duration-300 backdrop-blur-sm"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4 text-cyan-400 group-hover:text-cyan-300 transition-colors"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            <span className="text-gray-300 group-hover:text-white transition-colors">Dashboard</span>
          </button>
        </div>

        {/* Pause Indicator */}
        <PauseIndicator paused={paused} />

        {/* Solar System Navigator */}
        <SolarSystemNavigator
          onNavigate={handleNavigateToSystem}
          currentSystem={currentSystem}
        />

        {/* 3D Canvas */}
        <Canvas
          camera={{ position: [0, 2, 10], fov: 60 }}
          gl={{
            antialias: !performanceMode,
            alpha: false,
            powerPreference: performanceMode ? 'low-power' : 'high-performance',
            failIfMajorPerformanceCaveat: false,
            preserveDrawingBuffer: true
          }}
          dpr={performanceMode ? [1, 1] : [1, 2]}
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
              onPlanetClick={handlePlanetClick}
              gexValue={gexValue}
              vixValue={vixValue}
              spotPrice={spotPrice}
              pnlValue={pnlValue}
              pnlPercent={pnlPercent}
              signalStrength={signalStrength}
              shockwaveTime={shockwaveTime}
              performanceMode={performanceMode}
              paused={paused}
              setPaused={setPaused}
              gravityWell={gravityWell}
              tradeExplosion={tradeExplosion}
              setTradeExplosion={setTradeExplosion}
              celebrationActive={celebrationActive}
              setCelebrationActive={setCelebrationActive}
              konamiActive={konamiActive}
              zoomTarget={zoomTarget}
              setZoomTarget={setZoomTarget}
              stockPrices={stockPrices}
            />
          </Suspense>
        </Canvas>

        {/* Bottom status bar */}
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex gap-2 text-xs">
          <div className="bg-black/70 border border-cyan-500/20 rounded px-2 py-1 text-gray-400">
            Theme: <span style={{ color: COLORS.accent }}>{theme.toUpperCase()}</span>
          </div>
          {stockPricesLive && (
            <div className="bg-black/70 border border-green-500/40 rounded px-2 py-1 text-green-400 flex items-center gap-1">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              LIVE PRICES
            </div>
          )}
          {performanceMode && (
            <div className="bg-black/70 border border-yellow-500/20 rounded px-2 py-1 text-yellow-400">
              ⚡ Performance Mode
            </div>
          )}
        </div>
      </div>
    </Canvas3DErrorBoundary>
  )
}
