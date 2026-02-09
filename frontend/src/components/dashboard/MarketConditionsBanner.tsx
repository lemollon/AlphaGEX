'use client'

import useSWR from 'swr'
import { Activity, TrendingUp, TrendingDown, Minus, AlertTriangle, Shield, Zap, Eye } from 'lucide-react'

interface GEXData {
  success?: boolean
  data?: {
    spot_price?: number
    net_gex?: number
    flip_point?: number
    call_wall?: number
    put_wall?: number
    regime?: string
    mm_state?: string
  }
  spot_price?: number
  net_gex?: number
  flip_point?: number
  call_wall?: number
  put_wall?: number
  regime?: string
  mm_state?: string
}

interface VIXData {
  success?: boolean
  data?: {
    vix_spot?: number
    vix_close?: number
    change_pct?: number
  }
  vix_spot?: number
}

interface ProphetData {
  success?: boolean
  status?: string
  is_trained?: boolean
  model_version?: string
  recommendation?: string
  strategy?: string
  confidence?: number
}

const fetcher = async (url: string) => {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}${url}`)
    if (!res.ok) return {}
    return res.json()
  } catch {
    return {}
  }
}

// VIX regime thresholds
const getVIXRegime = (vix: number): { label: string; color: string; bgColor: string } => {
  if (vix < 15) return { label: 'LOW', color: 'text-green-400', bgColor: 'bg-green-900/30' }
  if (vix < 22) return { label: 'NORMAL', color: 'text-blue-400', bgColor: 'bg-blue-900/30' }
  if (vix < 28) return { label: 'ELEVATED', color: 'text-yellow-400', bgColor: 'bg-yellow-900/30' }
  if (vix < 35) return { label: 'HIGH', color: 'text-orange-400', bgColor: 'bg-orange-900/30' }
  return { label: 'EXTREME', color: 'text-red-400', bgColor: 'bg-red-900/30' }
}

// GEX regime display
const getGEXRegime = (regime: string | undefined): { label: string; color: string; bgColor: string; description: string } => {
  if (!regime) return { label: 'UNKNOWN', color: 'text-gray-400', bgColor: 'bg-gray-900/30', description: 'Data unavailable' }

  const r = regime.toUpperCase()
  if (r.includes('POSITIVE')) {
    return {
      label: 'POSITIVE',
      color: 'text-green-400',
      bgColor: 'bg-green-900/30',
      description: 'Mean reversion likely',
    }
  }
  if (r.includes('NEGATIVE')) {
    return {
      label: 'NEGATIVE',
      color: 'text-red-400',
      bgColor: 'bg-red-900/30',
      description: 'Trend continuation likely',
    }
  }
  return {
    label: 'NEUTRAL',
    color: 'text-yellow-400',
    bgColor: 'bg-yellow-900/30',
    description: 'Mixed signals',
  }
}

// Prophet recommendation display
const getProphetRecommendation = (data: ProphetData): { label: string; color: string; bgColor: string; icon: typeof Shield } => {
  const rec = data.recommendation?.toUpperCase() || data.strategy?.toUpperCase() || ''

  if (rec.includes('IRON') || rec.includes('IC') || rec.includes('CONDOR')) {
    return { label: 'IRON CONDOR', color: 'text-blue-400', bgColor: 'bg-blue-900/30', icon: Shield }
  }
  if (rec.includes('DIRECTIONAL') || rec.includes('SPREAD')) {
    return { label: 'DIRECTIONAL', color: 'text-purple-400', bgColor: 'bg-purple-900/30', icon: Zap }
  }
  if (rec.includes('WAIT') || rec.includes('NO_TRADE') || rec.includes('SKIP')) {
    return { label: 'WAIT', color: 'text-yellow-400', bgColor: 'bg-yellow-900/30', icon: AlertTriangle }
  }

  return { label: 'ANALYZING', color: 'text-gray-400', bgColor: 'bg-gray-900/30', icon: Eye }
}

export default function MarketConditionsBanner() {
  // Fetch market data
  const { data: gexData } = useSWR<GEXData>('/api/gex/SPY', fetcher, { refreshInterval: 120000 })
  const { data: vixData } = useSWR<VIXData>('/api/vix/current', fetcher, { refreshInterval: 60000 })
  const { data: prophetData } = useSWR<ProphetData>('/api/prophet/status', fetcher, { refreshInterval: 30000 })

  // Normalize data
  const gex = gexData?.data || gexData || {}
  const vix = vixData?.data?.vix_spot || vixData?.vix_spot || 0
  const spotPrice = gex.spot_price || 0
  const flipPoint = gex.flip_point || 0
  const callWall = gex.call_wall || 0
  const putWall = gex.put_wall || 0

  const vixRegime = getVIXRegime(vix)
  const gexRegime = getGEXRegime(gex.regime)
  const prophet = getProphetRecommendation(prophetData || {})
  const ProphetIcon = prophet.icon

  // Calculate distance to walls
  const distanceToCallWall = callWall && spotPrice ? ((callWall - spotPrice) / spotPrice) * 100 : 0
  const distanceToPutWall = putWall && spotPrice ? ((spotPrice - putWall) / spotPrice) * 100 : 0

  // Determine market direction indicator
  const getDirectionIndicator = () => {
    const mmState = gex.mm_state?.toUpperCase() || ''
    if (mmState.includes('BULLISH') || (spotPrice > flipPoint && flipPoint > 0)) {
      return { icon: TrendingUp, color: 'text-green-400', label: 'Bullish Bias' }
    }
    if (mmState.includes('BEARISH') || (spotPrice < flipPoint && flipPoint > 0)) {
      return { icon: TrendingDown, color: 'text-red-400', label: 'Bearish Bias' }
    }
    return { icon: Minus, color: 'text-gray-400', label: 'Neutral' }
  }

  const direction = getDirectionIndicator()
  const DirectionIcon = direction.icon

  return (
    <div className="bg-gradient-to-r from-gray-900 via-gray-900 to-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <div className="px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-4">
          {/* VIX Regime */}
          <div className={`flex items-center gap-3 px-4 py-2 rounded-lg ${vixRegime.bgColor}`}>
            <Activity className={`w-5 h-5 ${vixRegime.color}`} />
            <div>
              <div className="text-xs text-gray-500">VIX Regime</div>
              <div className="flex items-center gap-2">
                <span className={`font-bold ${vixRegime.color}`}>{vixRegime.label}</span>
                <span className="text-gray-400 text-sm">{vix.toFixed(2)}</span>
              </div>
            </div>
          </div>

          {/* GEX Regime */}
          <div className={`flex items-center gap-3 px-4 py-2 rounded-lg ${gexRegime.bgColor}`}>
            <DirectionIcon className={`w-5 h-5 ${gexRegime.color}`} />
            <div>
              <div className="text-xs text-gray-500">GEX Regime</div>
              <div className="flex items-center gap-2">
                <span className={`font-bold ${gexRegime.color}`}>{gexRegime.label}</span>
              </div>
              <div className="text-xs text-gray-500">{gexRegime.description}</div>
            </div>
          </div>

          {/* Prophet Recommendation */}
          <div className={`flex items-center gap-3 px-4 py-2 rounded-lg ${prophet.bgColor}`}>
            <ProphetIcon className={`w-5 h-5 ${prophet.color}`} />
            <div>
              <div className="text-xs text-gray-500">Prophet Says</div>
              <div className={`font-bold ${prophet.color}`}>{prophet.label}</div>
              {prophetData?.confidence && (
                <div className="text-xs text-gray-500">
                  {(prophetData.confidence * 100).toFixed(0)}% confidence
                </div>
              )}
            </div>
          </div>

          {/* Key Levels */}
          <div className="flex items-center gap-4 px-4 py-2 rounded-lg bg-gray-800/50">
            <div>
              <div className="text-xs text-gray-500">Flip Point</div>
              <div className="text-white font-medium">${flipPoint.toFixed(2)}</div>
            </div>
            <div className="h-8 w-px bg-gray-700" />
            <div>
              <div className="text-xs text-red-400">Call Wall</div>
              <div className="text-white font-medium">
                ${callWall.toFixed(0)}
                <span className="text-xs text-gray-500 ml-1">+{distanceToCallWall.toFixed(1)}%</span>
              </div>
            </div>
            <div className="h-8 w-px bg-gray-700" />
            <div>
              <div className="text-xs text-green-400">Put Wall</div>
              <div className="text-white font-medium">
                ${putWall.toFixed(0)}
                <span className="text-xs text-gray-500 ml-1">-{distanceToPutWall.toFixed(1)}%</span>
              </div>
            </div>
          </div>

          {/* Market Direction */}
          <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800/50">
            <DirectionIcon className={`w-5 h-5 ${direction.color}`} />
            <div>
              <div className="text-xs text-gray-500">Dealers</div>
              <div className={`font-medium ${direction.color}`}>{direction.label}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
