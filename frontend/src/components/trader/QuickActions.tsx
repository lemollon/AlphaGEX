'use client'

import { useState } from 'react'
import { Play, Pause, RefreshCw, Settings, Zap, AlertTriangle } from 'lucide-react'

interface QuickActionsProps {
  botName: 'ATHENA' | 'ARES' | 'ICARUS' | 'PEGASUS' | 'TITAN' | 'PHOENIX' | 'ATLAS'
  isActive: boolean
  isPaused: boolean
  isScanning: boolean
  onRunCycle: () => Promise<void>
  onTogglePause?: () => Promise<void>
  onOpenSettings?: () => void
  lastScanResult?: 'traded' | 'skipped' | 'error' | null
}

export default function QuickActions({
  botName,
  isActive,
  isPaused,
  isScanning,
  onRunCycle,
  onTogglePause,
  onOpenSettings,
  lastScanResult
}: QuickActionsProps) {
  const [isRunning, setIsRunning] = useState(false)
  const [isToggling, setIsToggling] = useState(false)

  const handleRunCycle = async () => {
    if (isRunning || isScanning) return
    setIsRunning(true)
    try {
      await onRunCycle()
    } finally {
      setIsRunning(false)
    }
  }

  const handleTogglePause = async () => {
    if (!onTogglePause || isToggling) return
    setIsToggling(true)
    try {
      await onTogglePause()
    } finally {
      setIsToggling(false)
    }
  }

  const getResultIndicator = () => {
    switch (lastScanResult) {
      case 'traded':
        return <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
      case 'skipped':
        return <span className="w-2 h-2 rounded-full bg-yellow-400"></span>
      case 'error':
        return <span className="w-2 h-2 rounded-full bg-red-400"></span>
      default:
        return null
    }
  }

  return (
    <div className="flex items-center gap-2">
      {/* Force Scan Button */}
      <button
        onClick={handleRunCycle}
        disabled={isRunning || isScanning || !isActive || isPaused}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg font-medium text-sm transition-all ${
          isRunning || isScanning
            ? 'bg-blue-500/20 text-blue-400 cursor-wait'
            : !isActive || isPaused
            ? 'bg-gray-700/50 text-gray-500 cursor-not-allowed'
            : 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 border border-blue-500/30'
        }`}
        title={isPaused ? 'Bot is paused' : 'Run scan cycle now'}
      >
        {isRunning || isScanning ? (
          <RefreshCw className="w-4 h-4 animate-spin" />
        ) : (
          <Zap className="w-4 h-4" />
        )}
        <span>{isRunning || isScanning ? 'Scanning...' : 'Scan Now'}</span>
        {getResultIndicator()}
      </button>

      {/* Pause/Resume Button */}
      {onTogglePause && (
        <button
          onClick={handleTogglePause}
          disabled={isToggling || !isActive}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg font-medium text-sm transition-all ${
            isPaused
              ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30 border border-green-500/30'
              : 'bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 border border-yellow-500/30'
          } ${isToggling ? 'cursor-wait' : ''} ${!isActive ? 'opacity-50 cursor-not-allowed' : ''}`}
          title={isPaused ? 'Resume scanning' : 'Pause scanning'}
        >
          {isToggling ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : isPaused ? (
            <Play className="w-4 h-4" />
          ) : (
            <Pause className="w-4 h-4" />
          )}
          <span>{isPaused ? 'Resume' : 'Pause'}</span>
        </button>
      )}

      {/* Settings Button */}
      {onOpenSettings && (
        <button
          onClick={onOpenSettings}
          className="p-2 rounded-lg bg-gray-700/50 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
          title="Bot settings"
        >
          <Settings className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}
