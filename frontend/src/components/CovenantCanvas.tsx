'use client'

import { useEffect, useRef, useState, useCallback } from 'react'

// =============================================================================
// TYPES
// =============================================================================

interface BotNode {
  id: string
  name: string
  label: string
  x: number
  y: number
  radius: number
  color: string
  glowColor: string
  status: 'active' | 'idle' | 'trading' | 'error'
  description: string
}

interface Particle {
  x: number
  y: number
  startX: number
  startY: number
  targetX: number
  targetY: number
  controlX: number
  controlY: number
  progress: number
  speed: number
  size: number
  opacity: number
  color: string
  type: 'signal' | 'entry' | 'exit' | 'profit' | 'loss'
  fromNode: string
  toNode: string
}

interface NeuralFiber {
  fromX: number
  fromY: number
  toX: number
  toY: number
  controlX: number
  controlY: number
  opacity: number
  width: number
  pulseOffset: number
}

interface PulseWave {
  radius: number
  maxRadius: number
  opacity: number
  speed: number
  color: string
}

interface TradeSignal {
  type: 'entry' | 'exit'
  bot: string
  direction: 'long' | 'short'
  profit?: number
  timestamp: number
}

export interface BotStatus {
  fortress?: 'active' | 'idle' | 'trading' | 'error'
  solomon?: 'active' | 'idle' | 'trading' | 'error'
  lazarus?: 'active' | 'idle' | 'trading' | 'error'
  cornerstone?: 'active' | 'idle' | 'trading' | 'error'
  prophet?: 'active' | 'idle' | 'trading' | 'error'
  gex?: 'active' | 'idle' | 'trading' | 'error'
}

interface CovenantCanvasProps {
  botStatus?: BotStatus
  onNodeClick?: (nodeId: string) => void
  onNodeHover?: (nodeId: string | null) => void
  showLabels?: boolean
  className?: string
  tradeSignals?: TradeSignal[]
  marketSentiment?: 'bullish' | 'bearish' | 'neutral'
}

// =============================================================================
// CONSTANTS
// =============================================================================

const COLORS = {
  background: '#050810',
  core: '#3b82f6',
  coreGlow: '#60a5fa',
  coreInner: '#93c5fd',
  fiber: '#1e40af',
  fiberGlow: '#3b82f6',
  particle: '#60a5fa',
  nodeActive: '#10b981',
  nodeIdle: '#6b7280',
  nodeTrading: '#f59e0b',
  nodeError: '#ef4444',
  text: '#f3f4f6',
  textSecondary: '#9ca3af',
  profit: '#10b981',
  loss: '#ef4444',
  entry: '#3b82f6',
  exit: '#f59e0b',
}

const STATUS_COLORS = {
  active: { fill: '#10b981', glow: '#34d399' },
  idle: { fill: '#4b5563', glow: '#6b7280' },
  trading: { fill: '#f59e0b', glow: '#fbbf24' },
  error: { fill: '#ef4444', glow: '#f87171' },
}

// =============================================================================
// COMPONENT
// =============================================================================

export default function CovenantCanvas({
  botStatus = {},
  onNodeClick,
  onNodeHover,
  showLabels = true,
  className = '',
  tradeSignals = [],
  marketSentiment = 'neutral',
}: CovenantCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animationRef = useRef<number>(0)
  const particlesRef = useRef<Particle[]>([])
  const fibersRef = useRef<NeuralFiber[]>([])
  const nodesRef = useRef<BotNode[]>([])
  const pulseWavesRef = useRef<PulseWave[]>([])
  const hoveredNodeRef = useRef<string | null>(null)
  const timeRef = useRef<number>(0)
  const dimensionsRef = useRef({ width: 0, height: 0, centerX: 0, centerY: 0, scale: 1 })

  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  // Initialize nodes with positions relative to center
  const initializeNodes = useCallback((centerX: number, centerY: number, scale: number) => {
    const coreRadius = 70 * scale
    const orbitRadius = 200 * scale
    const nodeRadius = 40 * scale

    const nodes: BotNode[] = [
      {
        id: 'gex-core',
        name: 'GEX',
        label: 'GEX CORE',
        x: centerX,
        y: centerY,
        radius: coreRadius,
        color: COLORS.core,
        glowColor: COLORS.coreGlow,
        status: botStatus.gex || 'active',
        description: 'Gamma Exposure Analysis Engine',
      },
      {
        id: 'prophet',
        name: 'PROPHET',
        label: 'PROPHET',
        x: centerX,
        y: centerY - orbitRadius,
        radius: nodeRadius,
        color: '#8b5cf6',
        glowColor: '#a78bfa',
        status: botStatus.prophet || 'active',
        description: 'ML Prediction Engine',
      },
      {
        id: 'fortress',
        name: 'FORTRESS',
        label: 'FORTRESS',
        x: centerX + orbitRadius * 0.95,
        y: centerY - orbitRadius * 0.31,
        radius: nodeRadius,
        color: '#ef4444',
        glowColor: '#f87171',
        status: botStatus.fortress || 'idle',
        description: 'Iron Condor Strategy',
      },
      {
        id: 'solomon',
        name: 'SOLOMON',
        label: 'SOLOMON',
        x: centerX + orbitRadius * 0.59,
        y: centerY + orbitRadius * 0.81,
        radius: nodeRadius,
        color: '#3b82f6',
        glowColor: '#60a5fa',
        status: botStatus.solomon || 'idle',
        description: 'Directional Spreads',
      },
      {
        id: 'cornerstone',
        name: 'CORNERSTONE',
        label: 'CORNERSTONE',
        x: centerX - orbitRadius * 0.59,
        y: centerY + orbitRadius * 0.81,
        radius: nodeRadius,
        color: '#10b981',
        glowColor: '#34d399',
        status: botStatus.cornerstone || 'idle',
        description: 'SPX Wheel Strategy',
      },
      {
        id: 'lazarus',
        name: 'LAZARUS',
        label: 'LAZARUS',
        x: centerX - orbitRadius * 0.95,
        y: centerY - orbitRadius * 0.31,
        radius: nodeRadius,
        color: '#f59e0b',
        glowColor: '#fbbf24',
        status: botStatus.lazarus || 'idle',
        description: '0DTE Options',
      },
    ]

    nodesRef.current = nodes
    return nodes
  }, [botStatus])

  // Initialize neural fibers with enhanced density
  const initializeFibers = useCallback((nodes: BotNode[], centerX: number, centerY: number, scale: number) => {
    const fibers: NeuralFiber[] = []
    const coreNode = nodes.find(n => n.id === 'gex-core')
    if (!coreNode) return fibers

    // Create multiple fibers per connection to bot nodes
    nodes.forEach(node => {
      if (node.id === 'gex-core') return

      const fiberCount = 5 + Math.floor(Math.random() * 4)
      for (let i = 0; i < fiberCount; i++) {
        const angle = Math.atan2(node.y - centerY, node.x - centerX)
        const spread = (Math.random() - 0.5) * 0.4
        const adjustedAngle = angle + spread

        const dist = Math.sqrt(Math.pow(node.x - centerX, 2) + Math.pow(node.y - centerY, 2))
        const controlDist = dist * (0.3 + Math.random() * 0.4)
        const controlAngle = adjustedAngle + (Math.random() - 0.5) * 0.6

        fibers.push({
          fromX: centerX + Math.cos(adjustedAngle) * coreNode.radius * 0.9,
          fromY: centerY + Math.sin(adjustedAngle) * coreNode.radius * 0.9,
          toX: node.x - Math.cos(angle) * node.radius * 0.9,
          toY: node.y - Math.sin(angle) * node.radius * 0.9,
          controlX: centerX + Math.cos(controlAngle) * controlDist,
          controlY: centerY + Math.sin(controlAngle) * controlDist,
          opacity: 0.15 + Math.random() * 0.25,
          width: 1 + Math.random() * 2,
          pulseOffset: Math.random() * Math.PI * 2,
        })
      }
    })

    // Add MANY ambient fibers radiating outward (like Image 1)
    const ambientFiberCount = 120
    for (let i = 0; i < ambientFiberCount; i++) {
      const baseAngle = (Math.PI * 2 * i) / ambientFiberCount
      const angleVariation = (Math.random() - 0.5) * 0.15
      const angle = baseAngle + angleVariation

      const minLength = 300 * scale
      const maxLength = Math.max(dimensionsRef.current.width, dimensionsRef.current.height) * 0.7
      const length = minLength + Math.random() * (maxLength - minLength)

      const controlDist = length * (0.2 + Math.random() * 0.5)
      const controlAngle = angle + (Math.random() - 0.5) * 0.6

      fibers.push({
        fromX: centerX + Math.cos(angle) * coreNode.radius * 0.95,
        fromY: centerY + Math.sin(angle) * coreNode.radius * 0.95,
        toX: centerX + Math.cos(angle) * length,
        toY: centerY + Math.sin(angle) * length,
        controlX: centerX + Math.cos(controlAngle) * controlDist,
        controlY: centerY + Math.sin(controlAngle) * controlDist,
        opacity: 0.08 + Math.random() * 0.15,
        width: 0.5 + Math.random() * 1.5,
        pulseOffset: Math.random() * Math.PI * 2,
      })
    }

    // Inter-node connections
    const outerNodes = nodes.filter(n => n.id !== 'gex-core')
    for (let i = 0; i < outerNodes.length; i++) {
      const nextIdx = (i + 1) % outerNodes.length
      const nodeA = outerNodes[i]
      const nodeB = outerNodes[nextIdx]

      const midX = (nodeA.x + nodeB.x) / 2
      const midY = (nodeA.y + nodeB.y) / 2
      const ctrlOffset = 30 * scale * (Math.random() - 0.5)

      fibers.push({
        fromX: nodeA.x,
        fromY: nodeA.y,
        toX: nodeB.x,
        toY: nodeB.y,
        controlX: midX + ctrlOffset,
        controlY: midY + ctrlOffset,
        opacity: 0.1 + Math.random() * 0.1,
        width: 0.8 + Math.random() * 0.8,
        pulseOffset: Math.random() * Math.PI * 2,
      })
    }

    fibersRef.current = fibers
    return fibers
  }, [])

  // Create particle with bezier path
  const createParticle = useCallback((
    fromNode: BotNode,
    toNode: BotNode,
    type: Particle['type'] = 'signal'
  ): Particle => {
    const angle = Math.atan2(toNode.y - fromNode.y, toNode.x - fromNode.x)
    const startX = fromNode.x + Math.cos(angle) * fromNode.radius
    const startY = fromNode.y + Math.sin(angle) * fromNode.radius
    const targetX = toNode.x - Math.cos(angle) * toNode.radius
    const targetY = toNode.y - Math.sin(angle) * toNode.radius

    // Random control point for curved path
    const midX = (startX + targetX) / 2
    const midY = (startY + targetY) / 2
    const perpAngle = angle + Math.PI / 2
    const curvature = (Math.random() - 0.5) * 80

    let color = COLORS.particle
    let size = 3 + Math.random() * 3

    if (type === 'entry') {
      color = COLORS.entry
      size = 5 + Math.random() * 3
    } else if (type === 'exit') {
      color = COLORS.exit
      size = 5 + Math.random() * 3
    } else if (type === 'profit') {
      color = COLORS.profit
      size = 6 + Math.random() * 4
    } else if (type === 'loss') {
      color = COLORS.loss
      size = 6 + Math.random() * 4
    }

    return {
      x: startX,
      y: startY,
      startX,
      startY,
      targetX,
      targetY,
      controlX: midX + Math.cos(perpAngle) * curvature,
      controlY: midY + Math.sin(perpAngle) * curvature,
      progress: 0,
      speed: 0.008 + Math.random() * 0.012,
      size,
      opacity: 0.8 + Math.random() * 0.2,
      color,
      type,
      fromNode: fromNode.id,
      toNode: toNode.id,
    }
  }, [])

  // Create pulse wave from center
  const createPulseWave = useCallback((color?: string) => {
    const { scale } = dimensionsRef.current
    pulseWavesRef.current.push({
      radius: 70 * scale,
      maxRadius: Math.max(dimensionsRef.current.width, dimensionsRef.current.height) * 0.8,
      opacity: 0.4,
      speed: 3 + Math.random() * 2,
      color: color || COLORS.coreGlow,
    })
  }, [])

  // Spawn particles periodically
  const spawnParticles = useCallback(() => {
    const nodes = nodesRef.current
    const coreNode = nodes.find(n => n.id === 'gex-core')
    if (!coreNode) return

    // Regular signal particles from core
    nodes.forEach(node => {
      if (node.id === 'gex-core') return

      // More frequent particles for active/trading nodes
      const spawnRate = node.status === 'trading' ? 0.04 : node.status === 'active' ? 0.025 : 0.01

      if (Math.random() < spawnRate) {
        particlesRef.current.push(createParticle(coreNode, node, 'signal'))
      }

      // Signals back to core from trading bots
      if (node.status === 'trading' && Math.random() < 0.05) {
        const type = Math.random() > 0.5 ? 'profit' : 'signal'
        particlesRef.current.push(createParticle(node, coreNode, type))
      }
    })

    // Inter-node communication
    const outerNodes = nodes.filter(n => n.id !== 'gex-core')
    if (Math.random() < 0.015) {
      const idx = Math.floor(Math.random() * outerNodes.length)
      const nextIdx = (idx + 1 + Math.floor(Math.random() * 2)) % outerNodes.length
      particlesRef.current.push(createParticle(outerNodes[idx], outerNodes[nextIdx], 'signal'))
    }

    // Periodic pulse waves
    if (Math.random() < 0.005) {
      createPulseWave()
    }
  }, [createParticle, createPulseWave])

  // Update particles with bezier interpolation
  const updateParticles = useCallback(() => {
    particlesRef.current = particlesRef.current.filter(p => {
      p.progress += p.speed

      // Quadratic bezier interpolation
      const t = p.progress
      const mt = 1 - t

      p.x = mt * mt * p.startX + 2 * mt * t * p.controlX + t * t * p.targetX
      p.y = mt * mt * p.startY + 2 * mt * t * p.controlY + t * t * p.targetY

      // Fade out near end
      if (p.progress > 0.75) {
        p.opacity = (1 - p.progress) / 0.25 * 0.8
      }

      return p.progress < 1
    })

    // Update pulse waves
    pulseWavesRef.current = pulseWavesRef.current.filter(wave => {
      wave.radius += wave.speed
      wave.opacity = 0.4 * (1 - wave.radius / wave.maxRadius)
      return wave.radius < wave.maxRadius && wave.opacity > 0.01
    })
  }, [])

  // Main draw function
  const draw = useCallback((ctx: CanvasRenderingContext2D, time: number) => {
    const { width, height, centerX, centerY, scale } = dimensionsRef.current

    // Clear with dark background
    ctx.fillStyle = COLORS.background
    ctx.fillRect(0, 0, width, height)

    // Deep space gradient
    const spaceGradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, Math.max(width, height) * 0.8)
    spaceGradient.addColorStop(0, 'rgba(30, 58, 138, 0.25)')
    spaceGradient.addColorStop(0.3, 'rgba(30, 58, 138, 0.1)')
    spaceGradient.addColorStop(0.6, 'rgba(15, 23, 42, 0.05)')
    spaceGradient.addColorStop(1, 'transparent')
    ctx.fillStyle = spaceGradient
    ctx.fillRect(0, 0, width, height)

    // Ambient star field
    for (let i = 0; i < 150; i++) {
      const x = (Math.sin(i * 1234.5 + time * 0.00005) * 0.5 + 0.5) * width
      const y = (Math.cos(i * 5678.9 + time * 0.00008) * 0.5 + 0.5) * height
      const twinkle = Math.sin(time * 0.002 + i * 0.5) * 0.5 + 0.5
      const size = 0.5 + twinkle * 1.5

      ctx.beginPath()
      ctx.arc(x, y, size, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(147, 197, 253, ${0.1 + twinkle * 0.3})`
      ctx.fill()
    }

    // Draw pulse waves
    pulseWavesRef.current.forEach(wave => {
      ctx.beginPath()
      ctx.arc(centerX, centerY, wave.radius, 0, Math.PI * 2)
      ctx.strokeStyle = `${wave.color}${Math.floor(wave.opacity * 255).toString(16).padStart(2, '0')}`
      ctx.lineWidth = 2
      ctx.stroke()
    })

    // Draw neural fibers with glow
    fibersRef.current.forEach((fiber, idx) => {
      const pulse = Math.sin(time * 0.002 + fiber.pulseOffset) * 0.3 + 0.7
      const opacity = fiber.opacity * pulse

      // Glow layer
      ctx.beginPath()
      ctx.moveTo(fiber.fromX, fiber.fromY)
      ctx.quadraticCurveTo(fiber.controlX, fiber.controlY, fiber.toX, fiber.toY)
      ctx.strokeStyle = `rgba(59, 130, 246, ${opacity * 0.3})`
      ctx.lineWidth = fiber.width + 3
      ctx.lineCap = 'round'
      ctx.stroke()

      // Core fiber
      ctx.beginPath()
      ctx.moveTo(fiber.fromX, fiber.fromY)
      ctx.quadraticCurveTo(fiber.controlX, fiber.controlY, fiber.toX, fiber.toY)
      ctx.strokeStyle = `rgba(96, 165, 250, ${opacity})`
      ctx.lineWidth = fiber.width
      ctx.stroke()

      // Bright tip particles along fibers
      if (idx % 3 === 0) {
        const fiberPulse = (time * 0.001 + fiber.pulseOffset) % 1
        const t = fiberPulse
        const mt = 1 - t
        const px = mt * mt * fiber.fromX + 2 * mt * t * fiber.controlX + t * t * fiber.toX
        const py = mt * mt * fiber.fromY + 2 * mt * t * fiber.controlY + t * t * fiber.toY

        const particleOpacity = Math.sin(fiberPulse * Math.PI) * 0.6
        if (particleOpacity > 0.1) {
          ctx.beginPath()
          ctx.arc(px, py, 2, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(147, 197, 253, ${particleOpacity})`
          ctx.fill()
        }
      }
    })

    // Draw traveling particles with trails
    particlesRef.current.forEach(particle => {
      // Trail
      const trailLength = 5
      for (let i = 0; i < trailLength; i++) {
        const trailProgress = Math.max(0, particle.progress - i * 0.02)
        const tt = trailProgress
        const mtt = 1 - tt
        const tx = mtt * mtt * particle.startX + 2 * mtt * tt * particle.controlX + tt * tt * particle.targetX
        const ty = mtt * mtt * particle.startY + 2 * mtt * tt * particle.controlY + tt * tt * particle.targetY

        const trailOpacity = particle.opacity * (1 - i / trailLength) * 0.5
        const trailSize = particle.size * (1 - i / trailLength * 0.5)

        ctx.beginPath()
        ctx.arc(tx, ty, trailSize, 0, Math.PI * 2)
        ctx.fillStyle = `${particle.color}${Math.floor(trailOpacity * 255).toString(16).padStart(2, '0')}`
        ctx.fill()
      }

      // Main particle with glow
      const glowGradient = ctx.createRadialGradient(
        particle.x, particle.y, 0,
        particle.x, particle.y, particle.size * 4
      )
      glowGradient.addColorStop(0, particle.color)
      glowGradient.addColorStop(0.3, `${particle.color}80`)
      glowGradient.addColorStop(1, 'transparent')

      ctx.beginPath()
      ctx.arc(particle.x, particle.y, particle.size * 4, 0, Math.PI * 2)
      ctx.fillStyle = glowGradient
      ctx.globalAlpha = particle.opacity
      ctx.fill()
      ctx.globalAlpha = 1

      // Bright core
      ctx.beginPath()
      ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2)
      ctx.fillStyle = '#ffffff'
      ctx.globalAlpha = particle.opacity * 0.9
      ctx.fill()
      ctx.globalAlpha = 1
    })

    // Draw bot nodes
    nodesRef.current.forEach(node => {
      const isHovered = hoveredNodeRef.current === node.id
      const isCore = node.id === 'gex-core'
      const statusColor = STATUS_COLORS[node.status] || STATUS_COLORS.idle

      if (isCore) {
        // === CORE NODE - Enhanced ===

        // Outer glow rings
        for (let ring = 3; ring >= 0; ring--) {
          const ringRadius = node.radius * (1.5 + ring * 0.4)
          const ringOpacity = 0.1 - ring * 0.02
          const pulse = Math.sin(time * 0.002 + ring * 0.5) * 0.3 + 0.7

          ctx.beginPath()
          ctx.arc(node.x, node.y, ringRadius, 0, Math.PI * 2)
          ctx.strokeStyle = `rgba(96, 165, 250, ${ringOpacity * pulse})`
          ctx.lineWidth = 1
          ctx.stroke()
        }

        // Intense center glow
        const coreGlow = ctx.createRadialGradient(
          node.x, node.y, 0,
          node.x, node.y, node.radius * 2.5
        )
        const glowPulse = Math.sin(time * 0.003) * 0.2 + 0.8
        coreGlow.addColorStop(0, `rgba(147, 197, 253, ${0.6 * glowPulse})`)
        coreGlow.addColorStop(0.3, `rgba(96, 165, 250, ${0.3 * glowPulse})`)
        coreGlow.addColorStop(0.6, `rgba(59, 130, 246, ${0.1 * glowPulse})`)
        coreGlow.addColorStop(1, 'transparent')

        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius * 2.5, 0, Math.PI * 2)
        ctx.fillStyle = coreGlow
        ctx.fill()

        // Main orb gradient
        const orbGradient = ctx.createRadialGradient(
          node.x - node.radius * 0.3, node.y - node.radius * 0.3, 0,
          node.x, node.y, node.radius
        )
        orbGradient.addColorStop(0, '#93c5fd')
        orbGradient.addColorStop(0.4, '#3b82f6')
        orbGradient.addColorStop(0.8, '#1e40af')
        orbGradient.addColorStop(1, '#1e3a8a')

        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
        ctx.fillStyle = orbGradient
        ctx.fill()

        // Border glow
        ctx.strokeStyle = `rgba(147, 197, 253, ${0.8 + Math.sin(time * 0.004) * 0.2})`
        ctx.lineWidth = 3
        ctx.stroke()

        // Inner concentric rings
        const innerRings = [0.8, 0.6, 0.4]
        innerRings.forEach((ratio, idx) => {
          const ringPulse = Math.sin(time * 0.004 + idx) * 0.3 + 0.7
          ctx.beginPath()
          ctx.arc(node.x, node.y, node.radius * ratio, 0, Math.PI * 2)
          ctx.strokeStyle = `rgba(255, 255, 255, ${0.15 * ringPulse})`
          ctx.lineWidth = 1.5
          ctx.stroke()
        })

        // Rotating energy arcs
        const arcCount = 3
        for (let i = 0; i < arcCount; i++) {
          const arcAngle = time * 0.001 * (i % 2 === 0 ? 1 : -1) + (i * Math.PI * 2 / arcCount)
          const arcLength = Math.PI * 0.3

          ctx.beginPath()
          ctx.arc(node.x, node.y, node.radius * 0.85, arcAngle, arcAngle + arcLength)
          ctx.strokeStyle = `rgba(255, 255, 255, ${0.5 + Math.sin(time * 0.003 + i) * 0.2})`
          ctx.lineWidth = 3
          ctx.lineCap = 'round'
          ctx.stroke()
        }

        // Center bright point
        const centerGlow = ctx.createRadialGradient(
          node.x, node.y, 0,
          node.x, node.y, node.radius * 0.3
        )
        centerGlow.addColorStop(0, 'rgba(255, 255, 255, 0.9)')
        centerGlow.addColorStop(0.5, 'rgba(147, 197, 253, 0.5)')
        centerGlow.addColorStop(1, 'transparent')

        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius * 0.3, 0, Math.PI * 2)
        ctx.fillStyle = centerGlow
        ctx.fill()

      } else {
        // === OUTER BOT NODES ===

        // Glow
        const glowSize = isHovered ? node.radius * 2.5 : node.radius * 2
        const nodeGlow = ctx.createRadialGradient(
          node.x, node.y, node.radius * 0.5,
          node.x, node.y, glowSize
        )
        nodeGlow.addColorStop(0, `${statusColor.glow}50`)
        nodeGlow.addColorStop(0.5, `${statusColor.glow}20`)
        nodeGlow.addColorStop(1, 'transparent')

        ctx.beginPath()
        ctx.arc(node.x, node.y, glowSize, 0, Math.PI * 2)
        ctx.fillStyle = nodeGlow
        ctx.fill()

        // Node body
        const bodyGradient = ctx.createRadialGradient(
          node.x - node.radius * 0.3, node.y - node.radius * 0.3, 0,
          node.x, node.y, node.radius
        )
        bodyGradient.addColorStop(0, statusColor.glow)
        bodyGradient.addColorStop(0.6, statusColor.fill)
        bodyGradient.addColorStop(1, `${statusColor.fill}dd`)

        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
        ctx.fillStyle = bodyGradient
        ctx.fill()

        // Border
        ctx.strokeStyle = isHovered ? '#ffffff' : `${statusColor.glow}cc`
        ctx.lineWidth = isHovered ? 3 : 2
        ctx.stroke()

        // Activity indicator for trading
        if (node.status === 'trading') {
          const pulseRadius = node.radius * (1.2 + Math.sin(time * 0.008) * 0.15)
          ctx.beginPath()
          ctx.arc(node.x, node.y, pulseRadius, 0, Math.PI * 2)
          ctx.strokeStyle = `${statusColor.glow}60`
          ctx.lineWidth = 2
          ctx.stroke()
        }
      }

      // Labels
      if (showLabels) {
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'

        if (isCore) {
          ctx.font = `bold ${16 * scale}px Inter, system-ui, sans-serif`
          ctx.fillStyle = COLORS.text
          ctx.fillText('GEX', node.x, node.y - 10 * scale)

          ctx.font = `${12 * scale}px Inter, system-ui, sans-serif`
          ctx.fillStyle = COLORS.textSecondary
          ctx.fillText('CORE', node.x, node.y + 12 * scale)
        } else {
          ctx.font = `bold ${12 * scale}px Inter, system-ui, sans-serif`
          ctx.fillStyle = COLORS.text
          ctx.fillText(node.name, node.x, node.y)

          // Status below node
          const statusY = node.y + node.radius + 16 * scale
          ctx.beginPath()
          ctx.arc(node.x, statusY, 5 * scale, 0, Math.PI * 2)
          ctx.fillStyle = statusColor.fill
          ctx.fill()

          ctx.font = `${10 * scale}px Inter, system-ui, sans-serif`
          ctx.fillStyle = COLORS.textSecondary
          ctx.fillText(node.status.toUpperCase(), node.x, statusY + 16 * scale)
        }
      }
    })

  }, [showLabels])

  // Animation loop
  const animate = useCallback((time: number) => {
    timeRef.current = time
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!ctx) return

    spawnParticles()
    updateParticles()
    draw(ctx, time)

    animationRef.current = requestAnimationFrame(animate)
  }, [spawnParticles, updateParticles, draw])

  // Handle resize
  const handleResize = useCallback(() => {
    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas) return

    const rect = container.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1

    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    canvas.style.width = `${rect.width}px`
    canvas.style.height = `${rect.height}px`

    const ctx = canvas.getContext('2d')
    if (ctx) ctx.scale(dpr, dpr)

    const width = rect.width
    const height = rect.height
    const centerX = width / 2
    const centerY = height / 2
    const scale = Math.min(width, height) / 600

    dimensionsRef.current = { width, height, centerX, centerY, scale }

    const nodes = initializeNodes(centerX, centerY, scale)
    initializeFibers(nodes, centerX, centerY, scale)
  }, [initializeNodes, initializeFibers])

  // Mouse handlers
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return

    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    let foundNode: string | null = null
    for (const node of nodesRef.current) {
      const dist = Math.sqrt(Math.pow(x - node.x, 2) + Math.pow(y - node.y, 2))
      if (dist < node.radius + 10) {
        foundNode = node.id
        break
      }
    }

    if (foundNode !== hoveredNodeRef.current) {
      hoveredNodeRef.current = foundNode
      setHoveredNode(foundNode)
      onNodeHover?.(foundNode)
    }
  }, [onNodeHover])

  const handleClick = useCallback(() => {
    if (hoveredNodeRef.current) {
      onNodeClick?.(hoveredNodeRef.current)
      // Trigger pulse wave on click
      createPulseWave(nodesRef.current.find(n => n.id === hoveredNodeRef.current)?.glowColor)
    }
  }, [onNodeClick, createPulseWave])

  // Initialize
  useEffect(() => {
    handleResize()
    window.addEventListener('resize', handleResize)
    animationRef.current = requestAnimationFrame(animate)

    // Initial pulse wave
    setTimeout(() => createPulseWave(), 500)

    return () => {
      window.removeEventListener('resize', handleResize)
      cancelAnimationFrame(animationRef.current)
    }
  }, [handleResize, animate, createPulseWave])

  // Update on bot status change
  useEffect(() => {
    const { centerX, centerY, scale } = dimensionsRef.current
    if (centerX && centerY) {
      initializeNodes(centerX, centerY, scale)
    }
  }, [botStatus, initializeNodes])

  return (
    <div ref={containerRef} className={`w-full h-full ${className}`}>
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onClick={handleClick}
        className={`w-full h-full ${hoveredNode ? 'cursor-pointer' : 'cursor-default'}`}
      />
    </div>
  )
}
