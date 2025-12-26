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
  targetX: number
  targetY: number
  progress: number
  speed: number
  size: number
  opacity: number
  color: string
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
}

export interface BotStatus {
  ares?: 'active' | 'idle' | 'trading' | 'error'
  athena?: 'active' | 'idle' | 'trading' | 'error'
  phoenix?: 'active' | 'idle' | 'trading' | 'error'
  atlas?: 'active' | 'idle' | 'trading' | 'error'
  oracle?: 'active' | 'idle' | 'trading' | 'error'
  gex?: 'active' | 'idle' | 'trading' | 'error'
}

interface NexusCanvasProps {
  botStatus?: BotStatus
  onNodeClick?: (nodeId: string) => void
  onNodeHover?: (nodeId: string | null) => void
  showLabels?: boolean
  className?: string
}

// =============================================================================
// CONSTANTS
// =============================================================================

const COLORS = {
  background: '#0a0e1a',
  core: '#3b82f6',
  coreGlow: '#60a5fa',
  fiber: '#1e40af',
  fiberGlow: '#3b82f6',
  particle: '#60a5fa',
  nodeActive: '#10b981',
  nodeIdle: '#6b7280',
  nodeTrading: '#f59e0b',
  nodeError: '#ef4444',
  text: '#f3f4f6',
  textSecondary: '#9ca3af',
}

const STATUS_COLORS = {
  active: { fill: '#10b981', glow: '#34d399' },
  idle: { fill: '#6b7280', glow: '#9ca3af' },
  trading: { fill: '#f59e0b', glow: '#fbbf24' },
  error: { fill: '#ef4444', glow: '#f87171' },
}

// =============================================================================
// COMPONENT
// =============================================================================

export default function NexusCanvas({
  botStatus = {},
  onNodeClick,
  onNodeHover,
  showLabels = true,
  className = '',
}: NexusCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animationRef = useRef<number>(0)
  const particlesRef = useRef<Particle[]>([])
  const fibersRef = useRef<NeuralFiber[]>([])
  const nodesRef = useRef<BotNode[]>([])
  const hoveredNodeRef = useRef<string | null>(null)
  const timeRef = useRef<number>(0)
  const dimensionsRef = useRef({ width: 0, height: 0, centerX: 0, centerY: 0 })

  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  // Initialize nodes with positions relative to center
  const initializeNodes = useCallback((centerX: number, centerY: number, scale: number) => {
    const coreRadius = 60 * scale
    const orbitRadius = 180 * scale
    const nodeRadius = 35 * scale

    const nodes: BotNode[] = [
      // Central GEX Core
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
      // ORACLE - Top
      {
        id: 'oracle',
        name: 'ORACLE',
        label: 'ORACLE',
        x: centerX,
        y: centerY - orbitRadius,
        radius: nodeRadius,
        color: '#8b5cf6',
        glowColor: '#a78bfa',
        status: botStatus.oracle || 'active',
        description: 'ML Prediction Engine',
      },
      // ARES - Top Right
      {
        id: 'ares',
        name: 'ARES',
        label: 'ARES',
        x: centerX + orbitRadius * 0.87,
        y: centerY - orbitRadius * 0.5,
        radius: nodeRadius,
        color: '#ef4444',
        glowColor: '#f87171',
        status: botStatus.ares || 'idle',
        description: 'Iron Condor Strategy',
      },
      // ATHENA - Bottom Right
      {
        id: 'athena',
        name: 'ATHENA',
        label: 'ATHENA',
        x: centerX + orbitRadius * 0.87,
        y: centerY + orbitRadius * 0.5,
        radius: nodeRadius,
        color: '#3b82f6',
        glowColor: '#60a5fa',
        status: botStatus.athena || 'idle',
        description: 'Directional Spreads',
      },
      // ATLAS - Bottom Left
      {
        id: 'atlas',
        name: 'ATLAS',
        label: 'ATLAS',
        x: centerX - orbitRadius * 0.87,
        y: centerY + orbitRadius * 0.5,
        radius: nodeRadius,
        color: '#10b981',
        glowColor: '#34d399',
        status: botStatus.atlas || 'idle',
        description: 'SPX Wheel Strategy',
      },
      // PHOENIX - Bottom Left
      {
        id: 'phoenix',
        name: 'PHOENIX',
        label: 'PHOENIX',
        x: centerX - orbitRadius * 0.87,
        y: centerY - orbitRadius * 0.5,
        radius: nodeRadius,
        color: '#f59e0b',
        glowColor: '#fbbf24',
        status: botStatus.phoenix || 'idle',
        description: '0DTE Options',
      },
    ]

    nodesRef.current = nodes
    return nodes
  }, [botStatus])

  // Initialize neural fibers (connections from core to nodes)
  const initializeFibers = useCallback((nodes: BotNode[], centerX: number, centerY: number) => {
    const fibers: NeuralFiber[] = []
    const coreNode = nodes.find(n => n.id === 'gex-core')
    if (!coreNode) return fibers

    // Create multiple fibers per connection for the neural effect
    nodes.forEach(node => {
      if (node.id === 'gex-core') return

      // Create 3-5 fibers per connection with slight variations
      const fiberCount = 3 + Math.floor(Math.random() * 3)
      for (let i = 0; i < fiberCount; i++) {
        const angle = Math.atan2(node.y - centerY, node.x - centerX)
        const spread = (Math.random() - 0.5) * 0.3
        const adjustedAngle = angle + spread

        // Control point for bezier curve
        const dist = Math.sqrt(Math.pow(node.x - centerX, 2) + Math.pow(node.y - centerY, 2))
        const controlDist = dist * (0.4 + Math.random() * 0.2)
        const controlAngle = adjustedAngle + (Math.random() - 0.5) * 0.5

        fibers.push({
          fromX: centerX + Math.cos(adjustedAngle) * coreNode.radius * 0.8,
          fromY: centerY + Math.sin(adjustedAngle) * coreNode.radius * 0.8,
          toX: node.x - Math.cos(angle) * node.radius,
          toY: node.y - Math.sin(angle) * node.radius,
          controlX: centerX + Math.cos(controlAngle) * controlDist,
          controlY: centerY + Math.sin(controlAngle) * controlDist,
          opacity: 0.2 + Math.random() * 0.3,
          width: 1 + Math.random() * 1.5,
        })
      }
    })

    // Add ambient fibers radiating outward
    for (let i = 0; i < 40; i++) {
      const angle = (Math.PI * 2 * i) / 40 + Math.random() * 0.1
      const length = 250 + Math.random() * 150
      const controlDist = length * (0.3 + Math.random() * 0.4)
      const controlAngle = angle + (Math.random() - 0.5) * 0.8

      fibers.push({
        fromX: centerX + Math.cos(angle) * 60,
        fromY: centerY + Math.sin(angle) * 60,
        toX: centerX + Math.cos(angle) * length,
        toY: centerY + Math.sin(angle) * length,
        controlX: centerX + Math.cos(controlAngle) * controlDist,
        controlY: centerY + Math.sin(controlAngle) * controlDist,
        opacity: 0.1 + Math.random() * 0.15,
        width: 0.5 + Math.random() * 1,
      })
    }

    fibersRef.current = fibers
    return fibers
  }, [])

  // Create a new particle
  const createParticle = useCallback((fromNode: BotNode, toNode: BotNode): Particle => {
    const angle = Math.atan2(toNode.y - fromNode.y, toNode.x - fromNode.x)
    return {
      x: fromNode.x + Math.cos(angle) * fromNode.radius,
      y: fromNode.y + Math.sin(angle) * fromNode.radius,
      targetX: toNode.x - Math.cos(angle) * toNode.radius,
      targetY: toNode.y - Math.sin(angle) * toNode.radius,
      progress: 0,
      speed: 0.005 + Math.random() * 0.01,
      size: 2 + Math.random() * 3,
      opacity: 0.6 + Math.random() * 0.4,
      color: fromNode.id === 'gex-core' ? toNode.glowColor : fromNode.glowColor,
      fromNode: fromNode.id,
      toNode: toNode.id,
    }
  }, [])

  // Spawn particles periodically
  const spawnParticles = useCallback(() => {
    const nodes = nodesRef.current
    const coreNode = nodes.find(n => n.id === 'gex-core')
    if (!coreNode) return

    // Spawn particles from core to outer nodes
    nodes.forEach(node => {
      if (node.id === 'gex-core') return
      if (Math.random() < 0.02) { // 2% chance per frame
        particlesRef.current.push(createParticle(coreNode, node))
      }
      // Occasionally send signals back to core
      if (node.status === 'trading' && Math.random() < 0.03) {
        particlesRef.current.push(createParticle(node, coreNode))
      }
    })

    // Also spawn particles between adjacent bot nodes occasionally
    const outerNodes = nodes.filter(n => n.id !== 'gex-core')
    if (Math.random() < 0.01) {
      const idx = Math.floor(Math.random() * outerNodes.length)
      const nextIdx = (idx + 1) % outerNodes.length
      particlesRef.current.push(createParticle(outerNodes[idx], outerNodes[nextIdx]))
    }
  }, [createParticle])

  // Update particles
  const updateParticles = useCallback(() => {
    particlesRef.current = particlesRef.current.filter(p => {
      p.progress += p.speed

      // Bezier curve interpolation for smooth movement
      const t = p.progress
      const mt = 1 - t

      // Simple quadratic bezier
      const midX = (p.x + p.targetX) / 2 + (Math.random() - 0.5) * 20
      const midY = (p.y + p.targetY) / 2 + (Math.random() - 0.5) * 20

      p.x = mt * mt * p.x + 2 * mt * t * midX + t * t * p.targetX
      p.y = mt * mt * p.y + 2 * mt * t * midY + t * t * p.targetY

      // Fade out as particle nears destination
      if (p.progress > 0.7) {
        p.opacity = (1 - p.progress) / 0.3 * 0.8
      }

      return p.progress < 1
    })
  }, [])

  // Draw the canvas
  const draw = useCallback((ctx: CanvasRenderingContext2D, time: number) => {
    const { width, height, centerX, centerY } = dimensionsRef.current

    // Clear canvas
    ctx.fillStyle = COLORS.background
    ctx.fillRect(0, 0, width, height)

    // Draw radial gradient background
    const bgGradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, Math.max(width, height) * 0.6)
    bgGradient.addColorStop(0, 'rgba(30, 64, 175, 0.15)')
    bgGradient.addColorStop(0.5, 'rgba(30, 64, 175, 0.05)')
    bgGradient.addColorStop(1, 'transparent')
    ctx.fillStyle = bgGradient
    ctx.fillRect(0, 0, width, height)

    // Draw neural fibers
    fibersRef.current.forEach(fiber => {
      ctx.beginPath()
      ctx.moveTo(fiber.fromX, fiber.fromY)
      ctx.quadraticCurveTo(fiber.controlX, fiber.controlY, fiber.toX, fiber.toY)

      // Pulsing opacity
      const pulse = Math.sin(time * 0.001 + fiber.fromX * 0.01) * 0.1 + 0.9
      ctx.strokeStyle = `rgba(59, 130, 246, ${fiber.opacity * pulse})`
      ctx.lineWidth = fiber.width
      ctx.stroke()
    })

    // Draw particles
    particlesRef.current.forEach(particle => {
      ctx.beginPath()
      ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2)

      // Glow effect
      const gradient = ctx.createRadialGradient(
        particle.x, particle.y, 0,
        particle.x, particle.y, particle.size * 3
      )
      gradient.addColorStop(0, particle.color)
      gradient.addColorStop(0.5, `${particle.color}80`)
      gradient.addColorStop(1, 'transparent')

      ctx.fillStyle = gradient
      ctx.globalAlpha = particle.opacity
      ctx.fill()
      ctx.globalAlpha = 1
    })

    // Draw nodes
    nodesRef.current.forEach(node => {
      const isHovered = hoveredNodeRef.current === node.id
      const isCore = node.id === 'gex-core'
      const statusColor = STATUS_COLORS[node.status] || STATUS_COLORS.idle

      // Outer glow
      const glowSize = isHovered ? node.radius * 2.5 : node.radius * 2
      const glowGradient = ctx.createRadialGradient(
        node.x, node.y, node.radius * 0.5,
        node.x, node.y, glowSize
      )

      if (isCore) {
        // Pulsing core glow
        const pulse = Math.sin(time * 0.002) * 0.3 + 0.7
        glowGradient.addColorStop(0, `${node.glowColor}${Math.floor(pulse * 80).toString(16).padStart(2, '0')}`)
        glowGradient.addColorStop(0.5, `${node.glowColor}40`)
        glowGradient.addColorStop(1, 'transparent')
      } else {
        glowGradient.addColorStop(0, `${statusColor.glow}60`)
        glowGradient.addColorStop(0.5, `${statusColor.glow}20`)
        glowGradient.addColorStop(1, 'transparent')
      }

      ctx.beginPath()
      ctx.arc(node.x, node.y, glowSize, 0, Math.PI * 2)
      ctx.fillStyle = glowGradient
      ctx.fill()

      // Node circle
      ctx.beginPath()
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)

      if (isCore) {
        // Core has special gradient
        const coreGradient = ctx.createRadialGradient(
          node.x - node.radius * 0.3, node.y - node.radius * 0.3, 0,
          node.x, node.y, node.radius
        )
        coreGradient.addColorStop(0, '#60a5fa')
        coreGradient.addColorStop(0.5, '#3b82f6')
        coreGradient.addColorStop(1, '#1e40af')
        ctx.fillStyle = coreGradient
      } else {
        // Outer nodes
        const nodeGradient = ctx.createRadialGradient(
          node.x - node.radius * 0.3, node.y - node.radius * 0.3, 0,
          node.x, node.y, node.radius
        )
        nodeGradient.addColorStop(0, statusColor.glow)
        nodeGradient.addColorStop(0.7, statusColor.fill)
        nodeGradient.addColorStop(1, `${statusColor.fill}cc`)
        ctx.fillStyle = nodeGradient
      }

      ctx.fill()

      // Node border
      ctx.strokeStyle = isHovered ? '#ffffff' : `${node.glowColor}aa`
      ctx.lineWidth = isHovered ? 3 : 2
      ctx.stroke()

      // Inner ring for core
      if (isCore) {
        const ringPulse = Math.sin(time * 0.003) * 0.2 + 0.8
        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius * 0.6, 0, Math.PI * 2)
        ctx.strokeStyle = `rgba(255, 255, 255, ${ringPulse * 0.3})`
        ctx.lineWidth = 2
        ctx.stroke()

        // Rotating arc
        const rotationAngle = time * 0.001
        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius * 0.75, rotationAngle, rotationAngle + Math.PI * 0.5)
        ctx.strokeStyle = `rgba(255, 255, 255, 0.5)`
        ctx.lineWidth = 3
        ctx.stroke()
      }

      // Node label
      if (showLabels) {
        ctx.font = isCore ? 'bold 14px Inter, sans-serif' : 'bold 11px Inter, sans-serif'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillStyle = COLORS.text

        if (isCore) {
          ctx.fillText('GEX', node.x, node.y - 8)
          ctx.font = '10px Inter, sans-serif'
          ctx.fillStyle = COLORS.textSecondary
          ctx.fillText('CORE', node.x, node.y + 10)
        } else {
          ctx.fillText(node.name, node.x, node.y)
        }

        // Status indicator dot
        if (!isCore) {
          const dotY = node.y + node.radius + 12
          ctx.beginPath()
          ctx.arc(node.x, dotY, 4, 0, Math.PI * 2)
          ctx.fillStyle = statusColor.fill
          ctx.fill()

          // Status text
          ctx.font = '9px Inter, sans-serif'
          ctx.fillStyle = COLORS.textSecondary
          ctx.fillText(node.status.toUpperCase(), node.x, dotY + 14)
        }
      }

      // Hover tooltip
      if (isHovered && !isCore) {
        const tooltipY = node.y - node.radius - 30
        ctx.font = '11px Inter, sans-serif'
        ctx.fillStyle = COLORS.textSecondary
        ctx.fillText(node.description, node.x, tooltipY)
      }
    })

    // Draw ambient particles (star field effect)
    for (let i = 0; i < 50; i++) {
      const x = (Math.sin(i * 1234.5 + time * 0.0001) * 0.5 + 0.5) * width
      const y = (Math.cos(i * 5678.9 + time * 0.00015) * 0.5 + 0.5) * height
      const twinkle = Math.sin(time * 0.003 + i) * 0.5 + 0.5

      ctx.beginPath()
      ctx.arc(x, y, 1 + twinkle, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(96, 165, 250, ${0.1 + twinkle * 0.2})`
      ctx.fill()
    }
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
    if (ctx) {
      ctx.scale(dpr, dpr)
    }

    const width = rect.width
    const height = rect.height
    const centerX = width / 2
    const centerY = height / 2
    const scale = Math.min(width, height) / 500

    dimensionsRef.current = { width, height, centerX, centerY }

    const nodes = initializeNodes(centerX, centerY, scale)
    initializeFibers(nodes, centerX, centerY)
  }, [initializeNodes, initializeFibers])

  // Handle mouse move for hover detection
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

  // Handle click
  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (hoveredNodeRef.current) {
      onNodeClick?.(hoveredNodeRef.current)
    }
  }, [onNodeClick])

  // Initialize and cleanup
  useEffect(() => {
    handleResize()
    window.addEventListener('resize', handleResize)
    animationRef.current = requestAnimationFrame(animate)

    return () => {
      window.removeEventListener('resize', handleResize)
      cancelAnimationFrame(animationRef.current)
    }
  }, [handleResize, animate])

  // Update nodes when bot status changes
  useEffect(() => {
    const { centerX, centerY } = dimensionsRef.current
    const scale = Math.min(dimensionsRef.current.width, dimensionsRef.current.height) / 500
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
