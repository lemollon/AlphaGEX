'use client'

import { useRef, useMemo, useState, useEffect, Suspense, useCallback } from 'react'
import { Canvas, useFrame, useThree, extend } from '@react-three/fiber'
import {
  OrbitControls,
  Sphere,
  Stars,
  Html,
  Line,
  Text,
  Torus,
} from '@react-three/drei'
import * as THREE from 'three'

// =============================================================================
// TYPES
// =============================================================================

interface VIXData {
  vix_spot: number
  vix_m1: number
  vix_m2: number
  term_structure_pct: number
  structure_type: 'contango' | 'backwardation' | 'flat'
  vvix: number | null
  iv_percentile: number
  realized_vol_20d: number
  iv_rv_spread: number
  vol_regime: string
  vix_stress_level: string
  position_size_multiplier: number
}

interface VIXSolarSystemProps {
  vixData?: VIXData | null
  onPlanetClick?: (planetId: string) => void
  className?: string
}

// =============================================================================
// VIX DATA LINES - The scrolling text on the sphere
// =============================================================================

const VIX_DATA_LINES = [
  'VIX VOLATILITY INDEX',
  'CBOE MARKET FEAR GAUGE',
  'IV_PERCENTILE: {iv_pct}%',
  'TERM_STRUCTURE: {structure}',
  'VIX_SPOT: {vix_spot}',
  'VIX_M1: {vix_m1}',
  'VIX_M2: {vix_m2}',
  'REALIZED_VOL_20D: {rv}%',
  'IV_RV_SPREAD: {spread}',
  'VOL_REGIME: {regime}',
  'STRESS_LEVEL: {stress}',
  'VVIX: {vvix}',
  'POSITION_SIZE: {pos_size}%',
  '================================',
  'GAMMA_EXPOSURE_ANALYSIS',
  'DEALER_POSITIONING_ACTIVE',
  'OPTIONS_FLOW_MONITORING',
  'VOLATILITY_SURFACE_SCAN',
  '================================',
]

// =============================================================================
// COLOR SCHEMES BASED ON VIX LEVEL
// =============================================================================

const getVIXColorScheme = (vixLevel: number) => {
  if (vixLevel < 15) {
    return {
      primary: '#22c55e',    // Green - Low volatility
      secondary: '#4ade80',
      glow: '#86efac',
      text: '#dcfce7',
      label: 'COMPLACENT'
    }
  } else if (vixLevel < 20) {
    return {
      primary: '#06b6d4',    // Cyan - Normal
      secondary: '#22d3ee',
      glow: '#67e8f9',
      text: '#cffafe',
      label: 'NORMAL'
    }
  } else if (vixLevel < 25) {
    return {
      primary: '#eab308',    // Yellow - Elevated
      secondary: '#facc15',
      glow: '#fde047',
      text: '#fef9c3',
      label: 'ELEVATED'
    }
  } else if (vixLevel < 30) {
    return {
      primary: '#f97316',    // Orange - High
      secondary: '#fb923c',
      glow: '#fdba74',
      text: '#ffedd5',
      label: 'HIGH'
    }
  } else {
    return {
      primary: '#ef4444',    // Red - Extreme fear
      secondary: '#f87171',
      glow: '#fca5a5',
      text: '#fee2e2',
      label: 'EXTREME'
    }
  }
}

// =============================================================================
// VIX TEXT SPHERE - Scrolling text on a sphere like the reference image
// =============================================================================

function VIXTextSphere({
  vixData,
  colorScheme
}: {
  vixData: VIXData | null
  colorScheme: ReturnType<typeof getVIXColorScheme>
}) {
  const groupRef = useRef<THREE.Group>(null)
  const innerGlowRef = useRef<THREE.Mesh>(null)
  const outerGlowRef = useRef<THREE.Mesh>(null)
  const [textOpacity, setTextOpacity] = useState(0.9)

  // Generate text lines with real data
  const textLines = useMemo(() => {
    if (!vixData) return VIX_DATA_LINES

    return VIX_DATA_LINES.map(line => {
      return line
        .replace('{iv_pct}', vixData.iv_percentile?.toFixed(0) || '--')
        .replace('{structure}', vixData.structure_type?.toUpperCase() || 'UNKNOWN')
        .replace('{vix_spot}', vixData.vix_spot?.toFixed(2) || '--')
        .replace('{vix_m1}', vixData.vix_m1?.toFixed(2) || '--')
        .replace('{vix_m2}', vixData.vix_m2?.toFixed(2) || '--')
        .replace('{rv}', vixData.realized_vol_20d?.toFixed(1) || '--')
        .replace('{spread}', vixData.iv_rv_spread?.toFixed(1) || '--')
        .replace('{regime}', vixData.vol_regime?.toUpperCase() || 'UNKNOWN')
        .replace('{stress}', vixData.vix_stress_level?.toUpperCase() || 'UNKNOWN')
        .replace('{vvix}', vixData.vvix?.toFixed(1) || '--')
        .replace('{pos_size}', ((vixData.position_size_multiplier || 1) * 100).toFixed(0))
    })
  }, [vixData])

  useFrame((state) => {
    const t = state.clock.elapsedTime

    if (groupRef.current) {
      // Slow rotation
      groupRef.current.rotation.y = t * 0.15
      groupRef.current.rotation.x = Math.sin(t * 0.1) * 0.1
    }

    if (innerGlowRef.current) {
      const scale = 1.8 + Math.sin(t * 2) * 0.1
      innerGlowRef.current.scale.setScalar(scale)
    }

    if (outerGlowRef.current) {
      const scale = 2.2 + Math.sin(t * 1.5 + Math.PI) * 0.15
      outerGlowRef.current.scale.setScalar(scale)
    }

    // Pulsing text opacity
    setTextOpacity(0.7 + Math.sin(t * 3) * 0.2)
  })

  return (
    <group>
      {/* Outer glow sphere */}
      <Sphere ref={outerGlowRef} args={[1, 32, 32]}>
        <meshBasicMaterial
          color={colorScheme.glow}
          transparent
          opacity={0.05}
          side={THREE.BackSide}
        />
      </Sphere>

      {/* Inner glow sphere */}
      <Sphere ref={innerGlowRef} args={[1, 32, 32]}>
        <meshBasicMaterial
          color={colorScheme.secondary}
          transparent
          opacity={0.1}
          side={THREE.BackSide}
        />
      </Sphere>

      {/* Main dark sphere */}
      <Sphere args={[1.5, 64, 64]}>
        <meshBasicMaterial
          color="#0a0a0a"
          transparent
          opacity={0.95}
        />
      </Sphere>

      {/* Rotating text group */}
      <group ref={groupRef}>
        {/* Text rings around the sphere */}
        {textLines.map((line, ringIndex) => {
          const phi = (ringIndex / textLines.length) * Math.PI // From top to bottom
          const radius = 1.55 + Math.sin(phi) * 0.05 // Slightly varying radius

          return (
            <group key={ringIndex} rotation={[phi - Math.PI / 2, 0, 0]}>
              {/* Each character positioned around the ring */}
              {line.split('').map((char, charIndex) => {
                const theta = (charIndex / line.length) * Math.PI * 2
                const x = Math.cos(theta) * radius
                const z = Math.sin(theta) * radius

                return (
                  <Text
                    key={`${ringIndex}-${charIndex}`}
                    position={[x, 0, z]}
                    rotation={[0, -theta + Math.PI / 2, 0]}
                    fontSize={0.08}
                    color={colorScheme.primary}
                    anchorX="center"
                    anchorY="middle"
                    fillOpacity={textOpacity}
                    font="/fonts/JetBrainsMono-Regular.woff"
                  >
                    {char}
                  </Text>
                )
              })}
            </group>
          )
        })}
      </group>

      {/* Equatorial ring highlight */}
      <Torus args={[1.6, 0.02, 16, 100]} rotation={[Math.PI / 2, 0, 0]}>
        <meshBasicMaterial color={colorScheme.primary} transparent opacity={0.6} />
      </Torus>

      {/* Polar rings */}
      <Torus args={[0.8, 0.015, 16, 50]} rotation={[0, 0, 0]} position={[0, 1.3, 0]}>
        <meshBasicMaterial color={colorScheme.secondary} transparent opacity={0.4} />
      </Torus>
      <Torus args={[0.8, 0.015, 16, 50]} rotation={[0, 0, 0]} position={[0, -1.3, 0]}>
        <meshBasicMaterial color={colorScheme.secondary} transparent opacity={0.4} />
      </Torus>
    </group>
  )
}

// =============================================================================
// VIX PLANET - Orbiting planet representing a VIX metric
// =============================================================================

interface VIXPlanetProps {
  name: string
  value: string | number
  unit?: string
  color: string
  orbitRadius: number
  orbitSpeed: number
  size: number
  description: string
  effect?: 'glow' | 'rings' | 'pulse' | 'electric'
  onClick?: () => void
}

function VIXPlanet({
  name,
  value,
  unit = '',
  color,
  orbitRadius,
  orbitSpeed,
  size,
  description,
  effect = 'glow',
  onClick
}: VIXPlanetProps) {
  const groupRef = useRef<THREE.Group>(null)
  const planetRef = useRef<THREE.Mesh>(null)
  const [hovered, setHovered] = useState(false)
  const [angle, setAngle] = useState(Math.random() * Math.PI * 2)

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime

    // Update orbit angle
    setAngle(prev => prev + orbitSpeed * delta)

    if (groupRef.current) {
      // Orbital motion
      groupRef.current.position.x = Math.cos(angle) * orbitRadius
      groupRef.current.position.z = Math.sin(angle) * orbitRadius
      groupRef.current.position.y = Math.sin(angle * 2) * 0.3 // Slight vertical oscillation
    }

    if (planetRef.current) {
      // Self rotation
      planetRef.current.rotation.y += 0.02

      // Pulse effect when hovered
      if (hovered) {
        const pulse = 1 + Math.sin(t * 5) * 0.1
        planetRef.current.scale.setScalar(pulse)
      } else {
        planetRef.current.scale.setScalar(1)
      }
    }
  })

  return (
    <group ref={groupRef}>
      {/* Planet sphere */}
      <Sphere
        ref={planetRef}
        args={[size, 32, 32]}
        onClick={onClick}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <meshBasicMaterial color={color} />
      </Sphere>

      {/* Glow effect */}
      {effect === 'glow' && (
        <Sphere args={[size * 1.3, 16, 16]}>
          <meshBasicMaterial color={color} transparent opacity={0.2} side={THREE.BackSide} />
        </Sphere>
      )}

      {/* Rings effect */}
      {effect === 'rings' && (
        <>
          <Torus args={[size * 1.5, size * 0.1, 8, 32]} rotation={[Math.PI / 3, 0, 0]}>
            <meshBasicMaterial color={color} transparent opacity={0.5} />
          </Torus>
          <Torus args={[size * 1.8, size * 0.05, 8, 32]} rotation={[Math.PI / 3, 0, 0]}>
            <meshBasicMaterial color={color} transparent opacity={0.3} />
          </Torus>
        </>
      )}

      {/* Pulse effect */}
      {effect === 'pulse' && (
        <PulseRing color={color} size={size} />
      )}

      {/* Electric effect */}
      {effect === 'electric' && (
        <ElectricArc color={color} size={size} />
      )}

      {/* Label */}
      <Html position={[0, size + 0.3, 0]} center distanceFactor={15}>
        <div
          className={`text-center transition-all duration-200 ${hovered ? 'scale-110' : ''}`}
          style={{ pointerEvents: 'none' }}
        >
          <div
            className="text-xs font-bold tracking-wider uppercase px-2 py-0.5 rounded"
            style={{
              color: color,
              backgroundColor: 'rgba(0,0,0,0.7)',
              border: `1px solid ${color}40`
            }}
          >
            {name}
          </div>
          <div
            className="text-lg font-mono font-bold mt-1 px-2 py-0.5 rounded"
            style={{
              color: '#ffffff',
              backgroundColor: 'rgba(0,0,0,0.8)',
              textShadow: `0 0 10px ${color}`
            }}
          >
            {value}{unit}
          </div>
          {hovered && (
            <div
              className="text-[10px] mt-1 px-2 py-0.5 rounded max-w-[120px]"
              style={{
                color: '#9ca3af',
                backgroundColor: 'rgba(0,0,0,0.8)'
              }}
            >
              {description}
            </div>
          )}
        </div>
      </Html>
    </group>
  )
}

// =============================================================================
// VISUAL EFFECTS
// =============================================================================

function PulseRing({ color, size }: { color: string, size: number }) {
  const ringRef = useRef<THREE.Mesh>(null)

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (ringRef.current) {
      const scale = 1 + (t % 2) * 0.5
      ringRef.current.scale.setScalar(scale)
      const mat = ringRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = 0.5 - (t % 2) * 0.25
    }
  })

  return (
    <Torus ref={ringRef} args={[size * 1.2, size * 0.05, 8, 32]} rotation={[Math.PI / 2, 0, 0]}>
      <meshBasicMaterial color={color} transparent opacity={0.5} />
    </Torus>
  )
}

function ElectricArc({ color, size }: { color: string, size: number }) {
  const groupRef = useRef<THREE.Group>(null)

  const arcs = useMemo(() => {
    return Array.from({ length: 4 }, (_, i) => ({
      angle: (i / 4) * Math.PI * 2,
      length: size * 0.8 + Math.random() * size * 0.4
    }))
  }, [size])

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.z = state.clock.elapsedTime * 2
    }
  })

  return (
    <group ref={groupRef}>
      {arcs.map((arc, i) => (
        <Line
          key={i}
          points={[
            [Math.cos(arc.angle) * size, Math.sin(arc.angle) * size, 0],
            [Math.cos(arc.angle) * (size + arc.length), Math.sin(arc.angle) * (size + arc.length), 0]
          ]}
          color={color}
          lineWidth={2}
          transparent
          opacity={0.8}
        />
      ))}
    </group>
  )
}

// =============================================================================
// ORBITAL PATHS
// =============================================================================

function OrbitalPath({ radius, color }: { radius: number, color: string }) {
  const points = useMemo(() => {
    const pts: THREE.Vector3[] = []
    for (let i = 0; i <= 64; i++) {
      const angle = (i / 64) * Math.PI * 2
      pts.push(new THREE.Vector3(
        Math.cos(angle) * radius,
        0,
        Math.sin(angle) * radius
      ))
    }
    return pts
  }, [radius])

  return (
    <Line
      points={points}
      color={color}
      lineWidth={1}
      transparent
      opacity={0.15}
      dashed
      dashScale={10}
      dashSize={0.5}
      gapSize={0.3}
    />
  )
}

// =============================================================================
// VIX SOLAR SYSTEM SCENE
// =============================================================================

function VIXSolarSystemScene({
  vixData,
  onPlanetClick
}: {
  vixData: VIXData | null
  onPlanetClick?: (planetId: string) => void
}) {
  const controlsRef = useRef<any>(null)
  const colorScheme = getVIXColorScheme(vixData?.vix_spot || 15)

  // Define VIX planets with their metrics
  const planets = useMemo(() => {
    if (!vixData) {
      return [
        { id: 'vix_spot', name: 'VIX Spot', value: '--', unit: '', color: '#ef4444', orbitRadius: 4, orbitSpeed: 0.3, size: 0.4, description: 'Current VIX level', effect: 'glow' as const },
        { id: 'iv_pct', name: 'IV %ile', value: '--', unit: '%', color: '#f97316', orbitRadius: 5.5, orbitSpeed: 0.25, size: 0.35, description: 'IV Percentile rank', effect: 'pulse' as const },
        { id: 'term', name: 'Term Struct', value: '--', unit: '%', color: '#eab308', orbitRadius: 7, orbitSpeed: 0.2, size: 0.3, description: 'Term structure spread', effect: 'rings' as const },
        { id: 'vvix', name: 'VVIX', value: '--', unit: '', color: '#22c55e', orbitRadius: 8.5, orbitSpeed: 0.15, size: 0.35, description: 'Volatility of VIX', effect: 'electric' as const },
        { id: 'rv', name: 'Real Vol', value: '--', unit: '%', color: '#06b6d4', orbitRadius: 10, orbitSpeed: 0.12, size: 0.3, description: '20-day realized volatility', effect: 'glow' as const },
        { id: 'spread', name: 'IV-RV', value: '--', unit: '', color: '#8b5cf6', orbitRadius: 11.5, orbitSpeed: 0.1, size: 0.25, description: 'IV minus realized vol', effect: 'pulse' as const },
      ]
    }

    return [
      {
        id: 'vix_spot',
        name: 'VIX Spot',
        value: vixData.vix_spot?.toFixed(2) || '--',
        unit: '',
        color: vixData.vix_spot > 25 ? '#ef4444' : vixData.vix_spot > 18 ? '#f97316' : '#22c55e',
        orbitRadius: 4,
        orbitSpeed: 0.3,
        size: 0.45,
        description: 'Current VIX level',
        effect: 'glow' as const
      },
      {
        id: 'iv_pct',
        name: 'IV %ile',
        value: vixData.iv_percentile?.toFixed(0) || '--',
        unit: '%',
        color: vixData.iv_percentile > 80 ? '#ef4444' : vixData.iv_percentile > 50 ? '#f97316' : '#22c55e',
        orbitRadius: 5.5,
        orbitSpeed: 0.25,
        size: 0.38,
        description: 'IV Percentile rank',
        effect: 'pulse' as const
      },
      {
        id: 'term',
        name: 'Term Struct',
        value: vixData.term_structure_pct > 0 ? `+${vixData.term_structure_pct?.toFixed(1)}` : vixData.term_structure_pct?.toFixed(1) || '--',
        unit: '%',
        color: vixData.structure_type === 'backwardation' ? '#ef4444' : '#22c55e',
        orbitRadius: 7,
        orbitSpeed: 0.2,
        size: 0.32,
        description: `${vixData.structure_type?.toUpperCase() || 'UNKNOWN'} structure`,
        effect: 'rings' as const
      },
      {
        id: 'vvix',
        name: 'VVIX',
        value: vixData.vvix?.toFixed(1) || '--',
        unit: '',
        color: (vixData.vvix || 0) > 120 ? '#ef4444' : (vixData.vvix || 0) > 90 ? '#eab308' : '#22c55e',
        orbitRadius: 8.5,
        orbitSpeed: 0.15,
        size: 0.38,
        description: 'Volatility of VIX',
        effect: 'electric' as const
      },
      {
        id: 'rv',
        name: 'Real Vol',
        value: vixData.realized_vol_20d?.toFixed(1) || '--',
        unit: '%',
        color: '#06b6d4',
        orbitRadius: 10,
        orbitSpeed: 0.12,
        size: 0.32,
        description: '20-day realized volatility',
        effect: 'glow' as const
      },
      {
        id: 'spread',
        name: 'IV-RV',
        value: vixData.iv_rv_spread > 0 ? `+${vixData.iv_rv_spread?.toFixed(1)}` : vixData.iv_rv_spread?.toFixed(1) || '--',
        unit: '',
        color: vixData.iv_rv_spread > 5 ? '#eab308' : vixData.iv_rv_spread < 0 ? '#22c55e' : '#06b6d4',
        orbitRadius: 11.5,
        orbitSpeed: 0.1,
        size: 0.28,
        description: 'IV minus realized vol',
        effect: 'pulse' as const
      },
    ]
  }, [vixData])

  return (
    <>
      {/* Ambient lighting */}
      <ambientLight intensity={0.2} />
      <pointLight position={[0, 0, 0]} intensity={1} color={colorScheme.primary} />

      {/* Star field background */}
      <Stars
        radius={100}
        depth={50}
        count={3000}
        factor={4}
        saturation={0}
        fade
        speed={0.5}
      />

      {/* Central VIX Sphere with scrolling text */}
      <VIXTextSphere vixData={vixData} colorScheme={colorScheme} />

      {/* VIX Status Label */}
      <Html position={[0, 2.5, 0]} center>
        <div className="text-center">
          <div
            className="text-3xl font-bold font-mono tracking-wider"
            style={{
              color: colorScheme.primary,
              textShadow: `0 0 20px ${colorScheme.glow}`
            }}
          >
            VIX {vixData?.vix_spot?.toFixed(2) || '--'}
          </div>
          <div
            className="text-sm font-bold tracking-widest mt-1 px-3 py-1 rounded"
            style={{
              color: colorScheme.text,
              backgroundColor: `${colorScheme.primary}30`,
              border: `1px solid ${colorScheme.primary}50`
            }}
          >
            {colorScheme.label}
          </div>
        </div>
      </Html>

      {/* Vol Regime indicator */}
      <Html position={[0, -2.5, 0]} center>
        <div className="text-center">
          <div className="text-xs text-gray-500 tracking-wider">VOL REGIME</div>
          <div
            className="text-lg font-bold tracking-wider px-3 py-0.5 rounded mt-1"
            style={{
              color: colorScheme.primary,
              backgroundColor: 'rgba(0,0,0,0.7)',
              border: `1px solid ${colorScheme.primary}40`
            }}
          >
            {vixData?.vol_regime?.toUpperCase().replace('_', ' ') || 'UNKNOWN'}
          </div>
        </div>
      </Html>

      {/* Orbital paths */}
      {planets.map(planet => (
        <OrbitalPath key={`path-${planet.id}`} radius={planet.orbitRadius} color={planet.color} />
      ))}

      {/* VIX Planets */}
      {planets.map(planet => (
        <VIXPlanet
          key={planet.id}
          {...planet}
          onClick={() => onPlanetClick?.(planet.id)}
        />
      ))}

      {/* Camera controls */}
      <OrbitControls
        ref={controlsRef}
        enablePan={false}
        minDistance={8}
        maxDistance={25}
        autoRotate
        autoRotateSpeed={0.3}
        target={[0, 0, 0]}
      />
    </>
  )
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function VIXSolarSystem({
  vixData = null,
  onPlanetClick,
  className = ''
}: VIXSolarSystemProps) {
  const [isClient, setIsClient] = useState(false)

  useEffect(() => {
    setIsClient(true)
  }, [])

  if (!isClient) {
    return (
      <div className={`w-full h-full flex items-center justify-center bg-[#030712] ${className}`}>
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-cyan-400 text-sm">Initializing VIX Solar System...</p>
        </div>
      </div>
    )
  }

  return (
    <div className={`w-full h-full bg-[#030712] ${className}`}>
      <Canvas
        camera={{ position: [0, 5, 15], fov: 60 }}
        gl={{ antialias: true, alpha: true }}
        dpr={[1, 2]}
      >
        <Suspense fallback={null}>
          <VIXSolarSystemScene vixData={vixData} onPlanetClick={onPlanetClick} />
        </Suspense>
      </Canvas>

      {/* Legend overlay */}
      <div className="absolute bottom-4 left-4 bg-black/70 backdrop-blur-sm rounded-lg px-4 py-3 border border-gray-700/50">
        <div className="text-xs text-gray-400 uppercase tracking-wider mb-2">VIX Regime Colors</div>
        <div className="flex flex-wrap gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
            <span className="text-gray-300">&lt;15 Complacent</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-cyan-500" />
            <span className="text-gray-300">15-20 Normal</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
            <span className="text-gray-300">20-25 Elevated</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-orange-500" />
            <span className="text-gray-300">25-30 High</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
            <span className="text-gray-300">&gt;30 Extreme</span>
          </div>
        </div>
      </div>

      {/* Controls hint */}
      <div className="absolute bottom-4 right-4 bg-black/70 backdrop-blur-sm rounded-lg px-3 py-2 border border-gray-700/50">
        <div className="text-xs text-gray-400">
          <span className="text-gray-500">Drag to rotate</span> • <span className="text-gray-500">Scroll to zoom</span>
        </div>
      </div>
    </div>
  )
}
