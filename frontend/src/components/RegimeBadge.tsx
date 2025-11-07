'use client'

import { Shield, TrendingUp, TrendingDown, Activity, AlertTriangle, Zap } from 'lucide-react'

export interface RegimeInfo {
  primary_type: string
  secondary_type?: string | null
  confidence: number
  description?: string
  trade_direction?: string
  risk_level?: string
  timeline?: string | null
}

interface RegimeBadgeProps {
  regime: RegimeInfo
  size?: 'sm' | 'md' | 'lg'
  showConfidence?: boolean
  showIcon?: boolean
  className?: string
}

const REGIME_CONFIG = {
  'LIBERATION_IMMINENT': {
    label: 'LIBERATION TRADE',
    color: 'from-emerald-500 to-green-600',
    textColor: 'text-emerald-50',
    borderColor: 'border-emerald-400',
    bgColor: 'bg-emerald-500/10',
    icon: Zap,
    description: 'High probability reversal setup'
  },
  'OPPRESSION_BUILDING': {
    label: 'OPPRESSION TRADE',
    color: 'from-rose-500 to-red-600',
    textColor: 'text-rose-50',
    borderColor: 'border-rose-400',
    bgColor: 'bg-rose-500/10',
    icon: TrendingDown,
    description: 'Breakdown momentum setup'
  },
  'FALSE_FLOOR': {
    label: 'FALSE FLOOR',
    color: 'from-amber-500 to-orange-600',
    textColor: 'text-amber-50',
    borderColor: 'border-amber-400',
    bgColor: 'bg-amber-500/10',
    icon: AlertTriangle,
    description: 'Trap detection - avoid longs'
  },
  'NEUTRAL': {
    label: 'NEUTRAL',
    color: 'from-slate-500 to-slate-600',
    textColor: 'text-slate-50',
    borderColor: 'border-slate-400',
    bgColor: 'bg-slate-500/10',
    icon: Activity,
    description: 'No clear setup'
  },
  'COILING': {
    label: 'COILING',
    color: 'from-purple-500 to-purple-600',
    textColor: 'text-purple-50',
    borderColor: 'border-purple-400',
    bgColor: 'bg-purple-500/10',
    icon: Activity,
    description: 'Building energy for move'
  },
  'SQUEEZE_PLAY': {
    label: 'SQUEEZE PLAY',
    color: 'from-cyan-500 to-blue-600',
    textColor: 'text-cyan-50',
    borderColor: 'border-cyan-400',
    bgColor: 'bg-cyan-500/10',
    icon: TrendingUp,
    description: 'Volatility expansion coming'
  }
}

export default function RegimeBadge({
  regime,
  size = 'md',
  showConfidence = true,
  showIcon = true,
  className = ''
}: RegimeBadgeProps) {
  const regimeType = regime.primary_type?.toUpperCase().replace(/\s+/g, '_') || 'NEUTRAL'
  const config = REGIME_CONFIG[regimeType as keyof typeof REGIME_CONFIG] || REGIME_CONFIG.NEUTRAL

  const Icon = config.icon

  // Size configurations
  const sizeClasses = {
    sm: {
      container: 'px-2 py-1 text-xs',
      icon: 'w-3 h-3',
      confidence: 'text-[10px]'
    },
    md: {
      container: 'px-3 py-1.5 text-sm',
      icon: 'w-4 h-4',
      confidence: 'text-xs'
    },
    lg: {
      container: 'px-4 py-2 text-base',
      icon: 'w-5 h-5',
      confidence: 'text-sm'
    }
  }

  const sizes = sizeClasses[size]

  // Confidence color
  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 80) return 'text-emerald-300'
    if (confidence >= 60) return 'text-amber-300'
    return 'text-rose-300'
  }

  return (
    <div className={`inline-flex items-center gap-2 ${sizes.container} rounded-lg bg-gradient-to-r ${config.color} ${config.textColor} font-bold shadow-lg border-2 ${config.borderColor} ${className}`}>
      {showIcon && <Icon className={sizes.icon} />}
      <span>{config.label}</span>
      {showConfidence && (
        <span className={`${sizes.confidence} font-semibold ${getConfidenceColor(regime.confidence)}`}>
          {regime.confidence}%
        </span>
      )}
    </div>
  )
}

// Mini version for compact display
export function RegimeBadgeMini({ regime }: { regime: RegimeInfo }) {
  const regimeType = regime.primary_type?.toUpperCase().replace(/\s+/g, '_') || 'NEUTRAL'
  const config = REGIME_CONFIG[regimeType as keyof typeof REGIME_CONFIG] || REGIME_CONFIG.NEUTRAL
  const Icon = config.icon

  return (
    <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold ${config.bgColor} ${config.borderColor} border`}>
      <Icon className="w-3 h-3" />
      <span className="text-white">{config.label}</span>
    </div>
  )
}

// Full card with description
export function RegimeCard({ regime }: { regime: RegimeInfo }) {
  const regimeType = regime.primary_type?.toUpperCase().replace(/\s+/g, '_') || 'NEUTRAL'
  const config = REGIME_CONFIG[regimeType as keyof typeof REGIME_CONFIG] || REGIME_CONFIG.NEUTRAL
  const Icon = config.icon

  return (
    <div className={`p-4 rounded-lg border-2 ${config.borderColor} ${config.bgColor} shadow-lg`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon className="w-6 h-6 text-white" />
          <h3 className="text-lg font-bold text-white">{config.label}</h3>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-white">{regime.confidence}%</div>
          <div className="text-xs text-gray-300">Confidence</div>
        </div>
      </div>

      {regime.description && (
        <p className="text-sm text-gray-200 mb-2">{regime.description}</p>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs">
        {regime.trade_direction && (
          <div>
            <span className="text-gray-400">Direction:</span>
            <span className="ml-1 font-semibold text-white">{regime.trade_direction}</span>
          </div>
        )}
        {regime.risk_level && (
          <div>
            <span className="text-gray-400">Risk:</span>
            <span className="ml-1 font-semibold text-white">{regime.risk_level}</span>
          </div>
        )}
        {regime.timeline && (
          <div className="col-span-2">
            <span className="text-gray-400">Timeline:</span>
            <span className="ml-1 font-semibold text-white">{regime.timeline}</span>
          </div>
        )}
      </div>
    </div>
  )
}
