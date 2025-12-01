/**
 * Frontend logging utility
 *
 * Provides conditional logging that can be disabled in production.
 * All console.* calls should go through this module.
 */

const isDevelopment = process.env.NODE_ENV === 'development'
const isDebugEnabled = process.env.NEXT_PUBLIC_DEBUG === 'true'

// Enable logging in development or when debug flag is set
const shouldLog = isDevelopment || isDebugEnabled

export const logger = {
  debug: (...args: unknown[]) => {
    if (shouldLog) {
      console.debug('[DEBUG]', ...args)
    }
  },

  info: (...args: unknown[]) => {
    if (shouldLog) {
      console.info('[INFO]', ...args)
    }
  },

  warn: (...args: unknown[]) => {
    // Always log warnings
    console.warn('[WARN]', ...args)
  },

  error: (...args: unknown[]) => {
    // Always log errors
    console.error('[ERROR]', ...args)
  },

  // For WebSocket connection status - useful to keep
  ws: (...args: unknown[]) => {
    if (shouldLog) {
      console.log('[WS]', ...args)
    }
  },

  // For API calls - useful to keep
  api: (...args: unknown[]) => {
    if (shouldLog) {
      console.log('[API]', ...args)
    }
  }
}

export default logger
