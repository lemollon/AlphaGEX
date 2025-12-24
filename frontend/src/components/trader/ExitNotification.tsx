'use client'

import { useState, useEffect } from 'react'
import { X, CheckCircle, AlertTriangle, Clock, TrendingUp, TrendingDown, DollarSign } from 'lucide-react'

interface ExitNotificationProps {
  positionId: string
  spreadType: string
  strikes: string
  contracts: number
  entryPrice: number
  exitPrice: number
  pnl: number
  pnlPct: number
  holdTime: string
  exitReason: string
  timestamp: string
  onClose: () => void
  onViewDetails?: () => void
  autoDismissMs?: number  // Auto dismiss after X ms, 0 to disable
}

export default function ExitNotification({
  positionId,
  spreadType,
  strikes,
  contracts,
  entryPrice,
  exitPrice,
  pnl,
  pnlPct,
  holdTime,
  exitReason,
  timestamp,
  onClose,
  onViewDetails,
  autoDismissMs = 15000
}: ExitNotificationProps) {
  const [isVisible, setIsVisible] = useState(true)
  const [progress, setProgress] = useState(100)

  const isWin = pnl >= 0

  useEffect(() => {
    if (autoDismissMs <= 0) return

    const startTime = Date.now()
    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime
      const remaining = Math.max(0, 100 - (elapsed / autoDismissMs) * 100)
      setProgress(remaining)

      if (remaining <= 0) {
        handleClose()
      }
    }, 100)

    return () => clearInterval(interval)
  }, [autoDismissMs])

  const handleClose = () => {
    setIsVisible(false)
    setTimeout(onClose, 300) // Allow animation to complete
  }

  if (!isVisible) return null

  return (
    <div className={`fixed bottom-4 right-4 z-50 animate-slide-in-right max-w-md`}>
      <div className={`rounded-lg shadow-2xl border-2 overflow-hidden ${
        isWin
          ? 'bg-green-900/90 border-green-500/50'
          : 'bg-red-900/90 border-red-500/50'
      }`}>
        {/* Progress bar for auto-dismiss */}
        {autoDismissMs > 0 && (
          <div className="h-1 bg-gray-800">
            <div
              className={`h-full transition-all duration-100 ${isWin ? 'bg-green-400' : 'bg-red-400'}`}
              style={{ width: `${progress}%` }}
            ></div>
          </div>
        )}

        <div className="p-4">
          {/* Header */}
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex items-center gap-2">
              {isWin ? (
                <CheckCircle className="w-6 h-6 text-green-400" />
              ) : (
                <AlertTriangle className="w-6 h-6 text-red-400" />
              )}
              <div>
                <h3 className="font-bold text-white">Position Closed</h3>
                <p className="text-xs text-gray-300">{spreadType}</p>
              </div>
            </div>
            <button
              onClick={handleClose}
              className="p-1 rounded hover:bg-gray-700/50 transition-colors"
            >
              <X className="w-4 h-4 text-gray-400" />
            </button>
          </div>

          {/* P&L Display - Big and prominent */}
          <div className={`text-center py-3 rounded-lg mb-3 ${isWin ? 'bg-green-800/30' : 'bg-red-800/30'}`}>
            <div className="flex items-center justify-center gap-2">
              {isWin ? (
                <TrendingUp className="w-6 h-6 text-green-400" />
              ) : (
                <TrendingDown className="w-6 h-6 text-red-400" />
              )}
              <span className={`text-3xl font-bold ${isWin ? 'text-green-400' : 'text-red-400'}`}>
                {isWin ? '+' : ''}${Math.abs(pnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <p className={`text-sm ${isWin ? 'text-green-300' : 'text-red-300'}`}>
              {isWin ? '+' : ''}{pnlPct.toFixed(1)}%
            </p>
          </div>

          {/* Details Grid */}
          <div className="grid grid-cols-2 gap-2 text-xs mb-3">
            <div className="flex justify-between">
              <span className="text-gray-400">Strikes:</span>
              <span className="text-white font-mono">{strikes}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Contracts:</span>
              <span className="text-white">{contracts}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Entry:</span>
              <span className="text-white">${entryPrice.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Exit:</span>
              <span className="text-white">${exitPrice.toFixed(2)}</span>
            </div>
          </div>

          {/* Exit Reason & Hold Time */}
          <div className="flex items-center justify-between text-xs border-t border-gray-700/50 pt-2">
            <div className="flex items-center gap-1 text-gray-300">
              <span className="text-gray-500">Exit:</span>
              <span className={isWin ? 'text-green-300' : 'text-red-300'}>{exitReason}</span>
            </div>
            <div className="flex items-center gap-1 text-gray-400">
              <Clock className="w-3 h-3" />
              <span>Held {holdTime}</span>
            </div>
          </div>

          {/* View Details Button */}
          {onViewDetails && (
            <button
              onClick={() => {
                onViewDetails()
                handleClose()
              }}
              className="w-full mt-3 py-2 rounded bg-gray-700/50 hover:bg-gray-700 text-sm text-gray-300 hover:text-white transition-colors"
            >
              View Full Details
            </button>
          )}
        </div>
      </div>

      {/* Animation styles */}
      <style jsx>{`
        @keyframes slide-in-right {
          from {
            opacity: 0;
            transform: translateX(100%);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        .animate-slide-in-right {
          animation: slide-in-right 0.3s ease-out;
        }
      `}</style>
    </div>
  )
}

// Container component to manage multiple notifications
interface ExitNotificationContainerProps {
  notifications: Array<ExitNotificationProps & { id: string }>
  onDismiss: (id: string) => void
}

export function ExitNotificationContainer({ notifications, onDismiss }: ExitNotificationContainerProps) {
  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      {notifications.map((notification, index) => (
        <div key={notification.id} style={{ transform: `translateY(-${index * 10}px)` }}>
          <ExitNotification
            {...notification}
            onClose={() => onDismiss(notification.id)}
          />
        </div>
      ))}
    </div>
  )
}
