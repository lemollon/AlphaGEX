'use client'

import { useState, useEffect } from 'react'
import { Bell, BellOff, Volume2, VolumeX, Check, X, AlertTriangle } from 'lucide-react'
import { pushNotifications, NotificationPreferences } from '@/lib/pushNotifications'

export default function NotificationSettings() {
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null)
  const [permission, setPermission] = useState<NotificationPermission>('default')
  const [supported, setSupported] = useState(false)
  const [testSent, setTestSent] = useState(false)

  useEffect(() => {
    // Check if supported
    setSupported(pushNotifications.isSupported())

    // Load preferences
    setPreferences(pushNotifications.getPreferences())

    // Check permission status
    setPermission(pushNotifications.getPermissionStatus())
  }, [])

  const handleEnableNotifications = async () => {
    const granted = await pushNotifications.requestPermission()

    if (granted) {
      setPermission('granted')
      setPreferences(pushNotifications.getPreferences())
    } else {
      setPermission('denied')
    }
  }

  const handleTogglePreference = (key: keyof NotificationPreferences) => {
    if (!preferences) return

    const newPreferences = {
      ...preferences,
      [key]: !preferences[key]
    }

    pushNotifications.updatePreferences(newPreferences)
    setPreferences(newPreferences)
  }

  const handleTestNotification = async () => {
    await pushNotifications.showNotification('Test Alert', {
      body: 'This is a test notification from AlphaGEX',
      icon: '/icons/icon-192x192.png',
      tag: 'test',
      requireInteraction: false
    })

    setTestSent(true)
    setTimeout(() => setTestSent(false), 3000)
  }

  if (!supported) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <BellOff className="w-5 h-5 text-gray-500" />
          Push Notifications
        </h2>
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded p-4">
          <p className="text-yellow-400 text-sm">
            Push notifications are not supported in this browser. Please use a modern browser like Chrome, Firefox, or Edge.
          </p>
        </div>
      </div>
    )
  }

  if (permission === 'denied') {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <BellOff className="w-5 h-5 text-red-500" />
          Push Notifications
        </h2>
        <div className="bg-red-500/10 border border-red-500/30 rounded p-4">
          <p className="text-red-400 text-sm mb-3">
            Notification permission was denied. To enable notifications:
          </p>
          <ol className="text-red-300 text-sm space-y-2 ml-4 list-decimal">
            <li>Click the lock icon in your browser's address bar</li>
            <li>Find "Notifications" in the permissions list</li>
            <li>Change it to "Allow"</li>
            <li>Refresh this page</li>
          </ol>
        </div>
      </div>
    )
  }

  if (permission !== 'granted') {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Bell className="w-5 h-5 text-blue-500" />
          Enable Push Notifications
        </h2>
        <div className="space-y-4">
          <p className="text-gray-300">
            Get instant alerts for:
          </p>
          <ul className="space-y-2 text-sm text-gray-400">
            <li className="flex items-center gap-2">
              <Check className="w-4 h-4 text-green-500" />
              <span>CRITICAL market regime changes</span>
            </li>
            <li className="flex items-center gap-2">
              <Check className="w-4 h-4 text-green-500" />
              <span>Liberation setup detections</span>
            </li>
            <li className="flex items-center gap-2">
              <Check className="w-4 h-4 text-green-500" />
              <span>False floor warnings</span>
            </li>
            <li className="flex items-center gap-2">
              <Check className="w-4 h-4 text-green-500" />
              <span>High-confidence trade setups</span>
            </li>
          </ul>
          <button
            onClick={handleEnableNotifications}
            className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
          >
            <Bell className="w-5 h-5" />
            Enable Notifications
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-green-500/30 bg-gradient-to-br from-green-500/5 to-blue-500/5 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Bell className="w-5 h-5 text-green-500" />
          Notification Preferences
        </h2>
        <div className="flex items-center gap-2 text-xs text-green-400">
          <Check className="w-4 h-4" />
          <span>Enabled</span>
        </div>
      </div>

      {preferences && (
        <div className="space-y-4">
          {/* Master Toggle */}
          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-white flex items-center gap-2">
                  {preferences.enabled ? <Bell className="w-4 h-4" /> : <BellOff className="w-4 h-4" />}
                  All Notifications
                </div>
                <div className="text-xs text-gray-400 mt-1">
                  Master switch for all alerts
                </div>
              </div>
              <button
                onClick={() => handleTogglePreference('enabled')}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  preferences.enabled ? 'bg-green-600' : 'bg-gray-600'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    preferences.enabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Alert Level Preferences */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-300">Alert Levels</h3>

            <div className="bg-gray-800/30 rounded-lg p-3 flex items-center justify-between">
              <div>
                <div className="text-sm text-white">Critical Alerts</div>
                <div className="text-xs text-gray-400">Urgent market events</div>
              </div>
              <button
                onClick={() => handleTogglePreference('criticalAlerts')}
                disabled={!preferences.enabled}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  preferences.criticalAlerts ? 'bg-red-600' : 'bg-gray-600'
                } ${!preferences.enabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    preferences.criticalAlerts ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div className="bg-gray-800/30 rounded-lg p-3 flex items-center justify-between">
              <div>
                <div className="text-sm text-white">High Priority Alerts</div>
                <div className="text-xs text-gray-400">Important market signals</div>
              </div>
              <button
                onClick={() => handleTogglePreference('highAlerts')}
                disabled={!preferences.enabled}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  preferences.highAlerts ? 'bg-orange-600' : 'bg-gray-600'
                } ${!preferences.enabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    preferences.highAlerts ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Event Type Preferences */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-gray-300">Event Types</h3>

            <div className="bg-gray-800/30 rounded-lg p-3 flex items-center justify-between">
              <div>
                <div className="text-sm text-white">Liberation Setups</div>
                <div className="text-xs text-gray-400">Gamma wall expiration alerts</div>
              </div>
              <button
                onClick={() => handleTogglePreference('liberationSetups')}
                disabled={!preferences.enabled}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  preferences.liberationSetups ? 'bg-purple-600' : 'bg-gray-600'
                } ${!preferences.enabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    preferences.liberationSetups ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div className="bg-gray-800/30 rounded-lg p-3 flex items-center justify-between">
              <div>
                <div className="text-sm text-white">False Floor Warnings</div>
                <div className="text-xs text-gray-400">Temporary support alerts</div>
              </div>
              <button
                onClick={() => handleTogglePreference('falseFloors')}
                disabled={!preferences.enabled}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  preferences.falseFloors ? 'bg-yellow-600' : 'bg-gray-600'
                } ${!preferences.enabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    preferences.falseFloors ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div className="bg-gray-800/30 rounded-lg p-3 flex items-center justify-between">
              <div>
                <div className="text-sm text-white">Regime Changes</div>
                <div className="text-xs text-gray-400">Market regime transitions</div>
              </div>
              <button
                onClick={() => handleTogglePreference('regimeChanges')}
                disabled={!preferences.enabled}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  preferences.regimeChanges ? 'bg-blue-600' : 'bg-gray-600'
                } ${!preferences.enabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    preferences.regimeChanges ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Sound Toggle */}
          <div className="bg-gray-800/30 rounded-lg p-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              {preferences.sound ? <Volume2 className="w-4 h-4 text-white" /> : <VolumeX className="w-4 h-4 text-gray-500" />}
              <div>
                <div className="text-sm text-white">Sound</div>
                <div className="text-xs text-gray-400">Play notification sound</div>
              </div>
            </div>
            <button
              onClick={() => handleTogglePreference('sound')}
              disabled={!preferences.enabled}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                preferences.sound ? 'bg-green-600' : 'bg-gray-600'
              } ${!preferences.enabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  preferences.sound ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          {/* Test Button */}
          <button
            onClick={handleTestNotification}
            disabled={!preferences.enabled}
            className={`w-full px-4 py-2 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 ${
              testSent
                ? 'bg-green-600 text-white'
                : preferences.enabled
                ? 'bg-gray-700 hover:bg-gray-600 text-white'
                : 'bg-gray-800 text-gray-500 cursor-not-allowed'
            }`}
          >
            {testSent ? (
              <>
                <Check className="w-4 h-4" />
                Test Sent!
              </>
            ) : (
              <>
                <AlertTriangle className="w-4 h-4" />
                Send Test Notification
              </>
            )}
          </button>
        </div>
      )}
    </div>
  )
}
