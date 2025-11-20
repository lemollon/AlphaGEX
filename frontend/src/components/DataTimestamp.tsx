'use client'

import { useState, useEffect } from 'react'
import { Clock, RefreshCw } from 'lucide-react'

interface DataTimestampProps {
  timestamp: string | Date | null
  label?: string
  onRefresh?: () => void
  refreshing?: boolean
  showRefreshButton?: boolean
}

export default function DataTimestamp({
  timestamp,
  label = 'Last updated',
  onRefresh,
  refreshing = false,
  showRefreshButton = true
}: DataTimestampProps) {
  const [timeAgo, setTimeAgo] = useState<string>('--')
  const [colorClass, setColorClass] = useState<string>('text-gray-400')

  useEffect(() => {
    if (!timestamp) {
      setTimeAgo('Never')
      setColorClass('text-gray-500')
      return
    }

    const updateTimeAgo = () => {
      try {
        const now = new Date()
        const then = typeof timestamp === 'string' ? new Date(timestamp) : timestamp
        const diffMs = now.getTime() - then.getTime()
        const diffMinutes = Math.floor(diffMs / 60000)

        let displayText = ''
        let color = 'text-gray-400'

        if (diffMinutes < 1) {
          displayText = 'Just now'
          color = 'text-green-400'
        } else if (diffMinutes < 5) {
          displayText = `${diffMinutes}m ago`
          color = 'text-green-400'
        } else if (diffMinutes < 15) {
          displayText = `${diffMinutes}m ago`
          color = 'text-yellow-400'
        } else if (diffMinutes < 60) {
          displayText = `${diffMinutes}m ago`
          color = 'text-orange-400'
        } else if (diffMinutes < 1440) {
          const hours = Math.floor(diffMinutes / 60)
          displayText = `${hours}h ago`
          color = 'text-red-400'
        } else {
          const days = Math.floor(diffMinutes / 1440)
          displayText = `${days}d ago`
          color = 'text-red-500'
        }

        setTimeAgo(displayText)
        setColorClass(color)
      } catch (error) {
        setTimeAgo('Invalid')
        setColorClass('text-gray-500')
      }
    }

    // Update immediately
    updateTimeAgo()

    // Update every 10 seconds
    const interval = setInterval(updateTimeAgo, 10000)

    return () => clearInterval(interval)
  }, [timestamp])

  return (
    <div className="flex items-center gap-3 text-sm">
      <div className="flex items-center gap-2">
        <Clock className={`w-4 h-4 ${colorClass}`} />
        <span className="text-gray-400">{label}:</span>
        <span className={`font-medium ${colorClass}`}>{timeAgo}</span>
      </div>

      {showRefreshButton && onRefresh && (
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="p-1.5 rounded-lg hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          title="Refresh data"
        >
          <RefreshCw
            className={`w-4 h-4 text-gray-400 hover:text-blue-400 transition-colors ${
              refreshing ? 'animate-spin' : ''
            }`}
          />
        </button>
      )}
    </div>
  )
}
