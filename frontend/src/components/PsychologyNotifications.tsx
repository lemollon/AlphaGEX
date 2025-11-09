'use client'

import React, { useState, useEffect, useRef } from 'react'
import { Bell, BellOff, AlertCircle, Zap, Target, TrendingDown, X, Settings, History } from 'lucide-react'

interface Notification {
  id: number
  timestamp: string
  urgency: 'critical' | 'high' | 'medium'
  title: string
  action: string
  pattern: string
  price: number
  confidence: number
  direction: string
  risk_level: string
  description: string
  psychology_trap: string
  vix?: number
  vix_spike?: boolean
  at_flip_point?: boolean
  volatility_regime?: string
}

interface NotificationStats {
  total_notifications: number
  critical_count: number
  high_priority_count: number
  by_pattern: Record<string, number>
  active_subscribers: number
  last_check_time: string | null
}

export default function PsychologyNotifications() {
  const [enabled, setEnabled] = useState(false)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [stats, setStats] = useState<NotificationStats | null>(null)
  const [browserPermission, setBrowserPermission] = useState<NotificationPermission>('default')
  const [showHistory, setShowHistory] = useState(false)
  const [unreadCount, setUnreadCount] = useState(0)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    // Check browser notification permission
    if ('Notification' in window) {
      setBrowserPermission(Notification.permission)
    }

    // Load notification stats
    fetchStats()

    // Load notification history
    fetchHistory()
  }, [])

  useEffect(() => {
    if (enabled) {
      connectToNotifications()
    } else {
      disconnectFromNotifications()
    }

    return () => {
      disconnectFromNotifications()
    }
  }, [enabled])

  const fetchStats = async () => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
      const response = await fetch(`${backendUrl}/api/psychology/notifications/stats`)
      const data = await response.json()
      if (data.success) {
        setStats(data.stats)
      }
    } catch (error) {
      console.error('Failed to fetch notification stats:', error)
    }
  }

  const fetchHistory = async () => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
      const response = await fetch(`${backendUrl}/api/psychology/notifications/history?limit=20`)
      const data = await response.json()
      if (data.success) {
        setNotifications(data.notifications.reverse()) // Newest first
      }
    } catch (error) {
      console.error('Failed to fetch notification history:', error)
    }
  }

  const connectToNotifications = () => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
      const eventSource = new EventSource(`${backendUrl}/api/psychology/notifications/stream`)

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)

          if (data.type === 'connected') {
            console.log('Connected to notification stream')
            return
          }

          if (data.type === 'ping') {
            // Keepalive ping
            return
          }

          // New notification received
          handleNewNotification(data)
        } catch (error) {
          console.error('Error parsing notification:', error)
        }
      }

      eventSource.onerror = (error) => {
        console.error('SSE connection error:', error)
        // Auto-reconnect handled by EventSource
      }

      eventSourceRef.current = eventSource
    } catch (error) {
      console.error('Failed to connect to notifications:', error)
    }
  }

  const disconnectFromNotifications = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }

  const handleNewNotification = (notification: Notification) => {
    // Add to notifications list
    setNotifications((prev) => [notification, ...prev].slice(0, 50)) // Keep last 50

    // Increment unread count
    setUnreadCount((prev) => prev + 1)

    // Show browser notification if permission granted
    if (browserPermission === 'granted') {
      showBrowserNotification(notification)
    }

    // Play sound for critical notifications (optional)
    if (notification.urgency === 'critical') {
      playNotificationSound()
    }

    // Update stats
    fetchStats()
  }

  const showBrowserNotification = (notification: Notification) => {
    try {
      const browserNotif = new Notification(notification.title, {
        body: notification.action,
        icon: '/favicon.ico',
        badge: '/favicon.ico',
        tag: `psychology-${notification.id}`,
        requireInteraction: notification.urgency === 'critical',
        data: notification
      })

      browserNotif.onclick = () => {
        window.focus()
        setShowHistory(true)
        browserNotif.close()
      }
    } catch (error) {
      console.error('Failed to show browser notification:', error)
    }
  }

  const playNotificationSound = () => {
    // Simple beep using Web Audio API
    try {
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
      const oscillator = audioContext.createOscillator()
      const gainNode = audioContext.createGain()

      oscillator.connect(gainNode)
      gainNode.connect(audioContext.destination)

      oscillator.frequency.value = 800
      oscillator.type = 'sine'
      gainNode.gain.value = 0.1

      oscillator.start()
      oscillator.stop(audioContext.currentTime + 0.2)
    } catch (error) {
      console.error('Failed to play notification sound:', error)
    }
  }

  const requestNotificationPermission = async () => {
    if ('Notification' in window) {
      const permission = await Notification.requestPermission()
      setBrowserPermission(permission)

      if (permission === 'granted') {
        setEnabled(true)
      }
    }
  }

  const toggleNotifications = () => {
    if (!enabled && browserPermission !== 'granted') {
      requestNotificationPermission()
    } else {
      setEnabled(!enabled)
    }
  }

  const clearNotifications = () => {
    setNotifications([])
    setUnreadCount(0)
  }

  const getUrgencyColor = (urgency: string) => {
    switch (urgency) {
      case 'critical':
        return 'bg-red-500/10 border-red-500/30 text-red-400'
      case 'high':
        return 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400'
      default:
        return 'bg-blue-500/10 border-blue-500/30 text-blue-400'
    }
  }

  const getUrgencyIcon = (urgency: string) => {
    switch (urgency) {
      case 'critical':
        return <Zap className="w-5 h-5" />
      case 'high':
        return <AlertCircle className="w-5 h-5" />
      default:
        return <Target className="w-5 h-5" />
    }
  }

  return (
    <div className="space-y-4">
      {/* Notification Control Panel */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Bell className={`w-6 h-6 ${enabled ? 'text-green-400' : 'text-gray-500'}`} />
            <div>
              <h2 className="text-xl font-bold">Push Notifications</h2>
              <p className="text-sm text-gray-400">
                Get alerted for critical psychology trap patterns
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Notification History Button */}
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="relative px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors flex items-center gap-2"
            >
              <History className="w-4 h-4" />
              History
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                  {unreadCount}
                </span>
              )}
            </button>

            {/* Enable/Disable Toggle */}
            <button
              onClick={toggleNotifications}
              className={`px-6 py-2 rounded-lg font-medium transition-colors ${
                enabled
                  ? 'bg-green-600 hover:bg-green-700 text-white'
                  : 'bg-purple-600 hover:bg-purple-700 text-white'
              }`}
            >
              {enabled ? (
                <span className="flex items-center gap-2">
                  <Bell className="w-4 h-4" />
                  Enabled
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <BellOff className="w-4 h-4" />
                  Enable Notifications
                </span>
              )}
            </button>
          </div>
        </div>

        {/* Browser Permission Status */}
        {browserPermission !== 'granted' && (
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-yellow-300 font-medium">
                Browser notifications not enabled
              </p>
              <p className="text-xs text-yellow-400/80 mt-1">
                Click "Enable Notifications" to receive alerts for critical patterns
              </p>
            </div>
          </div>
        )}

        {/* Stats */}
        {stats && enabled && (
          <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-gray-800">
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-400">{stats.active_subscribers}</div>
              <div className="text-xs text-gray-500">Active Connections</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-red-400">{stats.critical_count}</div>
              <div className="text-xs text-gray-500">Critical Alerts</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-yellow-400">{stats.high_priority_count}</div>
              <div className="text-xs text-gray-500">High Priority</div>
            </div>
          </div>
        )}

        {/* Critical Patterns Info */}
        <div className="mt-4 pt-4 border-t border-gray-800">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Critical Alert Patterns:</h3>
          <div className="flex flex-wrap gap-2">
            <span className="px-3 py-1 bg-purple-500/10 border border-purple-500/30 rounded-full text-xs text-purple-300">
              ⚡ GAMMA_SQUEEZE_CASCADE
            </span>
            <span className="px-3 py-1 bg-purple-500/10 border border-purple-500/30 rounded-full text-xs text-purple-300">
              🎯 FLIP_POINT_CRITICAL
            </span>
            <span className="px-3 py-1 bg-red-500/10 border border-red-500/30 rounded-full text-xs text-red-300">
              ⚠️ CAPITULATION_CASCADE
            </span>
          </div>
        </div>
      </div>

      {/* Notification History Panel */}
      {showHistory && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold">Recent Notifications</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={clearNotifications}
                className="px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 rounded transition-colors"
              >
                Clear All
              </button>
              <button
                onClick={() => {
                  setShowHistory(false)
                  setUnreadCount(0)
                }}
                className="p-2 hover:bg-gray-800 rounded transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          <div className="space-y-3 max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <Bell className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>No notifications yet</p>
                <p className="text-xs mt-1">You'll see alerts here when critical patterns are detected</p>
              </div>
            ) : (
              notifications.map((notif, idx) => (
                <div
                  key={notif.id || idx}
                  className={`border rounded-lg p-4 ${getUrgencyColor(notif.urgency)}`}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0">{getUrgencyIcon(notif.urgency)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <h4 className="font-bold text-sm">{notif.title}</h4>
                        <span className="text-xs text-gray-500 whitespace-nowrap">
                          {new Date(notif.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-sm mb-2">{notif.action}</p>
                      <div className="flex items-center gap-4 text-xs text-gray-400">
                        <span>Price: ${notif.price.toFixed(2)}</span>
                        <span>Confidence: {notif.confidence}%</span>
                        {notif.vix && <span>VIX: {notif.vix.toFixed(1)}</span>}
                      </div>
                      {notif.psychology_trap && (
                        <p className="text-xs text-yellow-400 mt-2">
                          🧠 {notif.psychology_trap}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
