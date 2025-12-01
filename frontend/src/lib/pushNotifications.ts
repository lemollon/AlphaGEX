/**
 * Push Notifications Service
 *
 * Handles browser push notifications for critical alerts
 * Supports:
 * - Browser Push API (Web Push)
 * - Notification permissions
 * - Service worker registration
 * - Alert preferences
 */
import { logger } from '@/lib/logger'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface NotificationPreferences {
  enabled: boolean
  criticalAlerts: boolean
  highAlerts: boolean
  liberationSetups: boolean
  falseFloors: boolean
  regimeChanges: boolean
  sound: boolean
}

export class PushNotificationService {
  private static instance: PushNotificationService
  private preferences: NotificationPreferences
  private subscription: PushSubscription | null = null

  private constructor() {
    this.preferences = this.loadPreferences()
  }

  public static getInstance(): PushNotificationService {
    if (!PushNotificationService.instance) {
      PushNotificationService.instance = new PushNotificationService()
    }
    return PushNotificationService.instance
  }

  /**
   * Check if push notifications are supported
   */
  public isSupported(): boolean {
    return (
      'Notification' in window &&
      'serviceWorker' in navigator &&
      'PushManager' in window
    )
  }

  /**
   * Get current notification permission status
   */
  public getPermissionStatus(): NotificationPermission {
    if (!this.isSupported()) return 'denied'
    return Notification.permission
  }

  /**
   * Request notification permissions
   */
  public async requestPermission(): Promise<boolean> {
    if (!this.isSupported()) {
      logger.warn('Push notifications not supported')
      return false
    }

    try {
      const permission = await Notification.requestPermission()

      if (permission === 'granted') {
        logger.info('Notification permission granted')
        await this.subscribeToNotifications()
        return true
      } else {
        logger.warn('Notification permission denied')
        return false
      }
    } catch (error) {
      logger.error('Error requesting notification permission:', error)
      return false
    }
  }

  /**
   * Subscribe to push notifications
   */
  private async subscribeToNotifications(): Promise<void> {
    try {
      // Register service worker
      const registration = await this.registerServiceWorker()

      if (!registration) {
        logger.error('Service worker registration failed')
        return
      }

      // Check if already subscribed
      let subscription = await registration.pushManager.getSubscription()

      if (!subscription) {
        // Create new subscription
        const vapidPublicKey = await this.getVapidPublicKey()

        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: this.urlBase64ToUint8Array(vapidPublicKey)
        })

        logger.info('Push subscription created')
      }

      // Send subscription to server
      await this.sendSubscriptionToServer(subscription)

      this.subscription = subscription
    } catch (error) {
      logger.error('Error subscribing to push notifications:', error)
    }
  }

  /**
   * Register service worker
   */
  private async registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
    try {
      if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.register('/sw.js')
        logger.info('Service Worker registered')
        return registration
      }
      return null
    } catch (error) {
      logger.error('Service Worker registration failed:', error)
      return null
    }
  }

  /**
   * Get VAPID public key from server
   */
  private async getVapidPublicKey(): Promise<string> {
    try {
      const response = await fetch(`${API_URL}/api/notifications/vapid-public-key`)
      const data = await response.json()
      return data.public_key
    } catch (error) {
      logger.error('Error fetching VAPID key:', error)
      // Fallback to a default key (should be replaced with your actual VAPID key)
      return 'BCqVrF4RkZxS0zCdV_Y0gHn3DfELfFqW6vqXzJx5lY8QfJ1pZ2X3Y4Z5A6B7C8D9'
    }
  }

  /**
   * Send subscription to server
   */
  private async sendSubscriptionToServer(subscription: PushSubscription): Promise<void> {
    try {
      await fetch(`${API_URL}/api/notifications/subscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          subscription: subscription.toJSON(),
          preferences: this.preferences
        })
      })
      logger.info('Subscription sent to server')
    } catch (error) {
      logger.error('Error sending subscription to server:', error)
    }
  }

  /**
   * Show local notification (fallback for testing)
   */
  public async showNotification(
    title: string,
    options: NotificationOptions = {}
  ): Promise<void> {
    if (!this.isSupported()) {
      logger.warn('Notifications not supported')
      return
    }

    if (Notification.permission !== 'granted') {
      logger.warn('Notification permission not granted')
      return
    }

    try {
      // Try to use service worker notification
      const registration = await navigator.serviceWorker.ready

      await registration.showNotification(title, {
        badge: '/icons/badge-96x96.png',
        icon: '/icons/icon-192x192.png',
        vibrate: [200, 100, 200],
        tag: 'alphagex-alert',
        requireInteraction: true,
        ...options
      })

      // Play sound if enabled
      if (this.preferences.sound) {
        this.playNotificationSound()
      }
    } catch (error) {
      logger.error('Error showing notification:', error)

      // Fallback to basic notification
      new Notification(title, options)
    }
  }

  /**
   * Play notification sound
   */
  private playNotificationSound(): void {
    try {
      const audio = new Audio('/sounds/notification.mp3')
      audio.volume = 0.5
      audio.play().catch(e => logger.warn('Could not play notification sound:', e))
    } catch (error) {
      logger.warn('Could not play notification sound:', error)
    }
  }

  /**
   * Handle alert from server
   */
  public async handleAlert(alert: {
    level: string
    title: string
    message: string
    type?: string
  }): Promise<void> {
    // Check if this type of alert is enabled
    if (!this.shouldShowAlert(alert.level, alert.type)) {
      return
    }

    const icon = this.getAlertIcon(alert.level)
    const urgency = alert.level === 'CRITICAL' ? 'urgent' : 'normal'

    await this.showNotification(alert.title, {
      body: alert.message,
      icon,
      badge: '/icons/badge-96x96.png',
      tag: `alert-${alert.type || 'general'}`,
      requireInteraction: alert.level === 'CRITICAL',
      // @ts-ignore - urgency is not in the standard but supported by some browsers
      urgency
    })
  }

  /**
   * Check if alert should be shown based on preferences
   */
  private shouldShowAlert(level: string, type?: string): boolean {
    if (!this.preferences.enabled) return false

    // Always show critical alerts if any alerts are enabled
    if (level === 'CRITICAL' && this.preferences.criticalAlerts) return true

    // Check high alerts preference
    if (level === 'HIGH' && this.preferences.highAlerts) return true

    // Check type-specific preferences
    if (type === 'liberation' && !this.preferences.liberationSetups) return false
    if (type === 'false_floor' && !this.preferences.falseFloors) return false
    if (type === 'regime_change' && !this.preferences.regimeChanges) return false

    return this.preferences.enabled
  }

  /**
   * Get icon for alert level
   */
  private getAlertIcon(level: string): string {
    switch (level) {
      case 'CRITICAL':
        return '/icons/critical.png'
      case 'HIGH':
        return '/icons/warning.png'
      case 'MEDIUM':
        return '/icons/info.png'
      default:
        return '/icons/icon-192x192.png'
    }
  }

  /**
   * Update preferences
   */
  public updatePreferences(preferences: Partial<NotificationPreferences>): void {
    this.preferences = { ...this.preferences, ...preferences }
    this.savePreferences()

    // Update server preferences if subscribed
    if (this.subscription) {
      this.sendPreferencesToServer()
    }
  }

  /**
   * Send preferences to server
   */
  private async sendPreferencesToServer(): Promise<void> {
    try {
      await fetch(`${API_URL}/api/notifications/preferences`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(this.preferences)
      })
    } catch (error) {
      logger.error('Error updating preferences:', error)
    }
  }

  /**
   * Get current preferences
   */
  public getPreferences(): NotificationPreferences {
    return { ...this.preferences }
  }

  /**
   * Load preferences from localStorage
   */
  private loadPreferences(): NotificationPreferences {
    try {
      const saved = localStorage.getItem('notification_preferences')
      if (saved) {
        return JSON.parse(saved)
      }
    } catch (error) {
      logger.warn('Could not load preferences:', error)
    }

    // Default preferences
    return {
      enabled: true,
      criticalAlerts: true,
      highAlerts: true,
      liberationSetups: true,
      falseFloors: true,
      regimeChanges: true,
      sound: true
    }
  }

  /**
   * Save preferences to localStorage
   */
  private savePreferences(): void {
    try {
      localStorage.setItem('notification_preferences', JSON.stringify(this.preferences))
    } catch (error) {
      logger.warn('Could not save preferences:', error)
    }
  }

  /**
   * Unsubscribe from notifications
   */
  public async unsubscribe(): Promise<void> {
    try {
      if (this.subscription) {
        await this.subscription.unsubscribe()

        // Notify server
        await fetch(`${API_URL}/api/notifications/unsubscribe`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            endpoint: this.subscription.endpoint
          })
        })

        this.subscription = null
        logger.info('Unsubscribed from push notifications')
      }
    } catch (error) {
      logger.error('Error unsubscribing:', error)
    }
  }

  /**
   * Helper: Convert VAPID key
   */
  private urlBase64ToUint8Array(base64String: string): Uint8Array {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')

    const rawData = window.atob(base64)
    const outputArray = new Uint8Array(rawData.length)

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i)
    }

    return outputArray
  }
}

// Export singleton instance
export const pushNotifications = PushNotificationService.getInstance()
