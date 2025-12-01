'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import { logger } from '@/lib/logger'
import { Bell, BellOff, Trash2, Check, AlertCircle, Smartphone } from 'lucide-react'

interface PushSubscription {
  id: number
  endpoint: string
  created_at: string
  device_name: string | null
  is_active: boolean
  last_notified: string | null
}

export default function NotificationSettings() {
  const [loading, setLoading] = useState(true)
  const [subscriptions, setSubscriptions] = useState<PushSubscription[]>([])
  const [deleteLoading, setDeleteLoading] = useState<number | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  useEffect(() => {
    fetchSubscriptions()
  }, [])

  const fetchSubscriptions = async () => {
    try {
      setLoading(true)
      const res = await apiClient.getPushSubscriptions()

      if (res.data.success) {
        setSubscriptions(res.data.subscriptions)
      }
    } catch (error) {
      logger.error('Error fetching subscriptions:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteSubscription = async (id: number) => {
    try {
      setDeleteLoading(id)
      const res = await apiClient.deletePushSubscription(id)

      if (res.data.success) {
        setSubscriptions(subscriptions.filter(sub => sub.id !== id))
        showSuccess('Subscription removed successfully')
      }
    } catch (error) {
      logger.error('Error deleting subscription:', error)
    } finally {
      setDeleteLoading(null)
    }
  }

  const showSuccess = (message: string) => {
    setSuccessMessage(message)
    setTimeout(() => setSuccessMessage(null), 3000)
  }

  const formatEndpoint = (endpoint: string) => {
    try {
      const url = new URL(endpoint)
      return `${url.hostname}...`
    } catch {
      return endpoint.substring(0, 30) + '...'
    }
  }

  const activeSubscriptions = subscriptions.filter(sub => sub.is_active)
  const inactiveSubscriptions = subscriptions.filter(sub => !sub.is_active)

  return (
    <div className="flex h-screen bg-gray-900">
      <Navigation />

      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">Notification Settings</h1>
            <p className="text-gray-400">
              Manage push notification subscriptions and preferences
            </p>
          </div>

          {/* Success Message */}
          {successMessage && (
            <div className="mb-6 bg-green-500/20 border border-green-500/30 rounded-lg p-4 flex items-center gap-3">
              <Check className="h-5 w-5 text-green-400" />
              <span className="text-green-400">{successMessage}</span>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            </div>
          ) : (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-blue-100 text-sm mb-1">Active Devices</p>
                      <h3 className="text-3xl font-bold text-white">
                        {activeSubscriptions.length}
                      </h3>
                    </div>
                    <Bell className="h-12 w-12 text-blue-200" />
                  </div>
                </div>

                <div className="bg-gradient-to-br from-gray-600 to-gray-700 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-gray-300 text-sm mb-1">Inactive Devices</p>
                      <h3 className="text-3xl font-bold text-white">
                        {inactiveSubscriptions.length}
                      </h3>
                    </div>
                    <BellOff className="h-12 w-12 text-gray-400" />
                  </div>
                </div>
              </div>

              {/* Notification Info */}
              <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-6 mb-8">
                <div className="flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-blue-400 mt-0.5" />
                  <div>
                    <h3 className="text-white font-medium mb-2">About Push Notifications</h3>
                    <p className="text-sm text-gray-300 mb-2">
                      Receive real-time alerts for trade signals, regime changes, and important market events.
                    </p>
                    <ul className="text-sm text-gray-400 space-y-1">
                      <li>• Liberation signals detected</li>
                      <li>• False floor warnings</li>
                      <li>• GEX regime changes</li>
                      <li>• Trade recommendations from AI</li>
                      <li>• Position entry/exit notifications</li>
                    </ul>
                  </div>
                </div>
              </div>

              {/* Active Subscriptions */}
              <div className="bg-gray-800 rounded-xl shadow-lg mb-8">
                <div className="p-6 border-b border-gray-700">
                  <div className="flex items-center gap-2">
                    <Smartphone className="h-5 w-5 text-green-500" />
                    <h2 className="text-xl font-semibold text-white">Active Devices</h2>
                  </div>
                </div>

                <div className="p-6">
                  {activeSubscriptions.length === 0 ? (
                    <div className="text-center text-gray-400 py-12">
                      <BellOff className="h-16 w-16 mx-auto mb-4 text-gray-600" />
                      <p className="mb-2">No active push notification subscriptions</p>
                      <p className="text-sm">Enable notifications in your browser to receive real-time alerts</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {activeSubscriptions.map((sub) => (
                        <div
                          key={sub.id}
                          className="bg-gray-750 rounded-lg p-4 border border-gray-700 flex items-center justify-between"
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <Smartphone className="h-4 w-4 text-green-500" />
                              <h3 className="text-white font-medium">
                                {sub.device_name || 'Unknown Device'}
                              </h3>
                              <span className="inline-flex items-center gap-1 px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs">
                                <Bell className="h-3 w-3" />
                                Active
                              </span>
                            </div>
                            <div className="grid grid-cols-2 gap-4 text-sm">
                              <div>
                                <span className="text-gray-500">Endpoint:</span>
                                <span className="text-gray-300 ml-2 font-mono text-xs">
                                  {formatEndpoint(sub.endpoint)}
                                </span>
                              </div>
                              <div>
                                <span className="text-gray-500">Subscribed:</span>
                                <span className="text-gray-300 ml-2">
                                  {new Date(sub.created_at).toLocaleDateString()}
                                </span>
                              </div>
                              {sub.last_notified && (
                                <div>
                                  <span className="text-gray-500">Last Notified:</span>
                                  <span className="text-gray-300 ml-2">
                                    {new Date(sub.last_notified).toLocaleString()}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                          <button
                            onClick={() => handleDeleteSubscription(sub.id)}
                            disabled={deleteLoading === sub.id}
                            className="ml-4 p-2 text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded transition disabled:opacity-50"
                            title="Unsubscribe"
                          >
                            {deleteLoading === sub.id ? (
                              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-red-400"></div>
                            ) : (
                              <Trash2 className="h-5 w-5" />
                            )}
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Inactive Subscriptions */}
              {inactiveSubscriptions.length > 0 && (
                <div className="bg-gray-800 rounded-xl shadow-lg">
                  <div className="p-6 border-b border-gray-700">
                    <div className="flex items-center gap-2">
                      <BellOff className="h-5 w-5 text-gray-500" />
                      <h2 className="text-xl font-semibold text-white">Inactive Devices</h2>
                    </div>
                  </div>

                  <div className="p-6">
                    <div className="space-y-4">
                      {inactiveSubscriptions.map((sub) => (
                        <div
                          key={sub.id}
                          className="bg-gray-750 rounded-lg p-4 border border-gray-700 flex items-center justify-between opacity-60"
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <Smartphone className="h-4 w-4 text-gray-500" />
                              <h3 className="text-white font-medium">
                                {sub.device_name || 'Unknown Device'}
                              </h3>
                              <span className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-600/20 text-gray-400 text-xs">
                                <BellOff className="h-3 w-3" />
                                Inactive
                              </span>
                            </div>
                            <div className="text-sm">
                              <span className="text-gray-500">Endpoint:</span>
                              <span className="text-gray-400 ml-2 font-mono text-xs">
                                {formatEndpoint(sub.endpoint)}
                              </span>
                            </div>
                          </div>
                          <button
                            onClick={() => handleDeleteSubscription(sub.id)}
                            disabled={deleteLoading === sub.id}
                            className="ml-4 p-2 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded transition disabled:opacity-50"
                            title="Remove"
                          >
                            {deleteLoading === sub.id ? (
                              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-gray-500"></div>
                            ) : (
                              <Trash2 className="h-5 w-5" />
                            )}
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
