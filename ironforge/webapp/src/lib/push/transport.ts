/**
 * Expo Push Service transport.
 *
 * Chosen because every outbound channel in this codebase is already "one env-guarded
 * fetch() to a vendor HTTPS endpoint" (email.ts, sms.ts, discord.ts) and this fits that
 * mould exactly. Direct APNs would add .p8 key handling + JWT signing + rotation;
 * direct FCM would add firebase-admin (~40 transitive packages) and a service-account
 * secret — both real operational weight for a handful of customers.
 *
 * The whole vendor surface is confined to this file. Swapping to APNs/FCM later is a
 * one-file change. Revisit if iOS critical alerts or custom interruption levels are
 * ever needed, since Expo does not expose those.
 */
import type { PushMessage } from '@/lib/push/types'

const EXPO_ENDPOINT = 'https://exp.host/--/api/v2/push/send'

/** Expo caps a batch at 100 messages. */
const MAX_BATCH = 100

export function isPushConfigured(): boolean {
  // Expo accepts unauthenticated sends for tokens it issued, so the transport works
  // without a key. EXPO_ACCESS_TOKEN is optional hardening (it stops anyone who
  // scrapes a token from pushing to your users) and should be set in production.
  return process.env.PUSH_ENABLED === 'true'
}

export function isExpoPushToken(token: string): boolean {
  return /^Expo(nent)?PushToken\[[^\]]+\]$/.test(token)
}

export interface PushTicket {
  status: 'ok' | 'error'
  id?: string
  message?: string
  details?: { error?: string }
}

/**
 * Send a batch. Returns one ticket per message, in order.
 *
 * Never throws: a notification failure must not take down the trade loop or the HTTP
 * request that triggered it. Transport errors come back as synthetic error tickets so
 * the caller can still record them.
 */
export async function sendExpoPush(messages: PushMessage[]): Promise<PushTicket[]> {
  if (messages.length === 0) return []
  if (!isPushConfigured()) {
    return messages.map(() => ({ status: 'error' as const, message: 'push_disabled' }))
  }

  const headers: Record<string, string> = {
    'content-type': 'application/json',
    accept: 'application/json',
  }
  if (process.env.EXPO_ACCESS_TOKEN) {
    headers.authorization = `Bearer ${process.env.EXPO_ACCESS_TOKEN}`
  }

  const tickets: PushTicket[] = []
  for (let i = 0; i < messages.length; i += MAX_BATCH) {
    const batch = messages.slice(i, i + MAX_BATCH)
    try {
      const res = await fetch(EXPO_ENDPOINT, {
        method: 'POST',
        headers,
        body: JSON.stringify(batch),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        console.error(`[push] Expo returned ${res.status}: ${text.slice(0, 200)}`)
        tickets.push(...batch.map(() => ({ status: 'error' as const, message: `http_${res.status}` })))
        continue
      }
      const json = (await res.json()) as { data?: PushTicket[] }
      const data = Array.isArray(json.data) ? json.data : []
      // Pad if Expo returned fewer tickets than messages, so ticket[i] always
      // corresponds to message[i] and a device can never be mis-attributed.
      for (let j = 0; j < batch.length; j++) {
        tickets.push(data[j] ?? { status: 'error', message: 'missing_ticket' })
      }
    } catch (e) {
      console.error('[push] transport threw:', e)
      tickets.push(...batch.map(() => ({ status: 'error' as const, message: 'transport_error' })))
    }
  }
  return tickets
}

/**
 * Expo's signal that a token is dead (app uninstalled, or reinstalled with a new token).
 * The device row must be disabled or it will accumulate failures forever.
 */
export function isDeviceGone(ticket: PushTicket): boolean {
  return ticket.status === 'error' && ticket.details?.error === 'DeviceNotRegistered'
}
