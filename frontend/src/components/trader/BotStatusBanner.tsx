'use client'

import { useState, useEffect } from 'react'
import { Activity, Clock, TrendingUp, TrendingDown, Zap, Pause, AlertCircle } from 'lucide-react'

interface BotStatusBannerProps {
  botName: 'ATHENA' | 'ARES' | 'PEGASUS' | 'PHOENIX' | 'ATLAS' | 'ICARUS' | 'TITAN'
  isActive: boolean
  isPaused?: boolean
  lastScan?: string | null
  nextScanMinutes?: number
  openPositions: number
  todayPnl: number
  todayTrades: number
  scanInterval?: number  // in minutes
  hasError?: boolean
  errorMessage?: string
}

export default function BotStatusBanner({
  botName,
  isActive,
  isPaused = false,
  lastScan,
  nextScanMinutes = 30,
  openPositions,
  todayPnl,
  todayTrades,
  scanInterval = 30,
  hasError = false,
  errorMessage
}: BotStatusBannerProps) {
  const [countdown, setCountdown] = useState<string>('')
  const [secondsToNext, setSecondsToNext] = useState<number>(0)

  // Calculate countdown to next scan
  useEffect(() => {
    if (!lastScan || isPaused || !isActive) {
      setCountdown('')
      return
    }

    const calculateCountdown = () => {
      const lastScanTime = new Date(lastScan).getTime()
      const nextScanTime = lastScanTime + (scanInterval * 60 * 1000)
      const now = Date.now()
      const diff = nextScanTime - now

      if (diff <= 0) {
        setCountdown('Scanning...')
        setSecondsToNext(0)
        return
      }

      const minutes = Math.floor(diff / 60000)
      const seconds = Math.floor((diff % 60000) / 1000)
      setSecondsToNext(diff / 1000)

      if (minutes > 0) {
        setCountdown(`${minutes}m ${seconds}s`)
      } else {
        setCountdown(`${seconds}s`)
      }
    }

    calculateCountdown()
    const interval = setInterval(calculateCountdown, 1000)
    return () => clearInterval(interval)
  }, [lastScan, scanInterval, isPaused, isActive])

  // Determine status color and icon
  const getStatusConfig = () => {
    if (hasError) {
      return {
        bg: 'bg-red-500/20',
        border: 'border-red-500/50',
        dot: 'bg-red-500',
        text: 'text-red-400',
        label: 'ERROR',
        pulse: false
      }
    }
    if (isPaused) {
      return {
        bg: 'bg-yellow-500/20',
        border: 'border-yellow-500/50',
        dot: 'bg-yellow-500',
        text: 'text-yellow-400',
        label: 'PAUSED',
        pulse: false
      }
    }
    if (!isActive) {
      return {
        bg: 'bg-gray-500/20',
        border: 'border-gray-500/50',
        dot: 'bg-gray-500',
        text: 'text-gray-400',
        label: 'INACTIVE',
        pulse: false
      }
    }
    if (secondsToNext <= 10 && secondsToNext > 0) {
      return {
        bg: 'bg-blue-500/20',
        border: 'border-blue-500/50',
        dot: 'bg-blue-500',
        text: 'text-blue-400',
        label: 'SCANNING SOON',
        pulse: true
      }
    }
    return {
      bg: 'bg-green-500/20',
      border: 'border-green-500/50',
      dot: 'bg-green-500',
      text: 'text-green-400',
      label: 'ACTIVE',
      pulse: true
    }
  }

  const status = getStatusConfig()
  const pnlPositive = todayPnl >= 0

  return (
    <div className={`${status.bg} border ${status.border} rounded-lg px-4 py-3 mb-4`}>
      <div className="flex items-center justify-between flex-wrap gap-3">
        {/* Left: Status */}
        <div className="flex items-center gap-3">
          {/* Pulsing dot */}
          <div className="flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              {status.pulse && (
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${status.dot} opacity-75`}></span>
              )}
              <span className={`relative inline-flex rounded-full h-3 w-3 ${status.dot}`}></span>
            </span>
            <span className={`font-bold ${status.text}`}>{botName}</span>
            <span className={`text-xs px-2 py-0.5 rounded ${status.bg} ${status.text} border ${status.border}`}>
              {status.label}
            </span>
          </div>

          {/* Error message if any */}
          {hasError && errorMessage && (
            <span className="text-xs text-red-300 flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />
              {errorMessage}
            </span>
          )}
        </div>

        {/* Center: Next Scan Countdown */}
        {isActive && !isPaused && !hasError && (
          <div className="flex items-center gap-2 text-sm">
            <Clock className="w-4 h-4 text-gray-400" />
            <span className="text-gray-400">Next scan:</span>
            <span className={`font-mono font-bold ${secondsToNext <= 10 ? 'text-blue-400' : 'text-white'}`}>
              {countdown || '--:--'}
            </span>
          </div>
        )}

        {/* Right: Quick Stats */}
        <div className="flex items-center gap-4">
          {/* Open Positions */}
          <div className="flex items-center gap-1.5">
            <Zap className="w-4 h-4 text-purple-400" />
            <span className="text-gray-400 text-sm">Open:</span>
            <span className={`font-bold ${openPositions > 0 ? 'text-purple-400' : 'text-gray-500'}`}>
              {openPositions}
            </span>
          </div>

          {/* Today's Trades */}
          <div className="flex items-center gap-1.5">
            <Activity className="w-4 h-4 text-blue-400" />
            <span className="text-gray-400 text-sm">Trades:</span>
            <span className="font-bold text-white">{todayTrades}</span>
          </div>

          {/* Today's P&L */}
          <div className="flex items-center gap-1.5">
            {pnlPositive ? (
              <TrendingUp className="w-4 h-4 text-green-400" />
            ) : (
              <TrendingDown className="w-4 h-4 text-red-400" />
            )}
            <span className="text-gray-400 text-sm">P&L:</span>
            <span className={`font-bold ${pnlPositive ? 'text-green-400' : 'text-red-400'}`}>
              {pnlPositive ? '+' : ''}${Math.abs(todayPnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
