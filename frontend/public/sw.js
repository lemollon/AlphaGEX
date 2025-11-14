/**
 * Service Worker for Push Notifications
 * Handles background push notifications from the server
 */

// Service worker version (increment to force update)
const VERSION = '1.0.0'
const CACHE_NAME = `alphagex-${VERSION}`

// Install event
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installing version:', VERSION)
  self.skipWaiting()
})

// Activate event
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activating version:', VERSION)

  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    })
  )

  return self.clients.claim()
})

// Push event - handle incoming push notifications
self.addEventListener('push', (event) => {
  console.log('[Service Worker] Push received')

  let data = {
    title: 'AlphaGEX Alert',
    body: 'New alert from AlphaGEX',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/badge-96x96.png',
    tag: 'alphagex-alert',
    requireInteraction: false,
    data: {}
  }

  try {
    if (event.data) {
      const payload = event.data.json()
      data = {
        ...data,
        ...payload,
        icon: payload.icon || data.icon,
        badge: payload.badge || data.badge
      }
    }
  } catch (error) {
    console.error('[Service Worker] Error parsing push data:', error)
  }

  const options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    tag: data.tag,
    requireInteraction: data.requireInteraction,
    vibrate: [200, 100, 200],
    data: data.data,
    actions: [
      {
        action: 'view',
        title: 'View Details'
      },
      {
        action: 'dismiss',
        title: 'Dismiss'
      }
    ]
  }

  event.waitUntil(self.registration.showNotification(data.title, options))
})

// Notification click event
self.addEventListener('notificationclick', (event) => {
  console.log('[Service Worker] Notification clicked:', event.action)

  event.notification.close()

  if (event.action === 'view') {
    // Open the app
    event.waitUntil(
      clients.openWindow('/?notification=' + event.notification.tag)
    )
  } else if (event.action === 'dismiss') {
    // Just close
    return
  } else {
    // Default action - open app
    event.waitUntil(
      clients.openWindow('/')
    )
  }
})

// Notification close event
self.addEventListener('notificationclose', (event) => {
  console.log('[Service Worker] Notification closed:', event.notification.tag)
})

// Message event - handle messages from clients
self.addEventListener('message', (event) => {
  console.log('[Service Worker] Message received:', event.data)

  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting()
  }
})
