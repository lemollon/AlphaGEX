import type { SessionOptions, IronSession } from 'iron-session'
import { getIronSession } from 'iron-session'
import { cookies } from 'next/headers'

/**
 * Customer session — DISTINCT from the operator session (src/lib/auth/session.ts).
 * The operator gate reads only `ironforge_session`; the customer gate reads only
 * `ironforge_customer`. They are never cross-honored, so a customer session can
 * never satisfy operator gating. (Sub-project: customer auth, Approach A.)
 */
export interface CustomerSessionData {
  customerId?: string // users.id (uuid) in the ironforge-customers DB
  email?: string
  emailVerified?: boolean
  onboardingStep?: string
}

export const CUSTOMER_SESSION_COOKIE = 'ironforge_customer'

export const customerSessionOptions: SessionOptions = {
  password: process.env.IRONFORGE_SESSION_SECRET || '',
  cookieName: CUSTOMER_SESSION_COOKIE,
  cookieOptions: {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: '/',
  },
}

/** Route-handler / server-component accessor (Node runtime only). */
export async function getCustomerSession(): Promise<IronSession<CustomerSessionData>> {
  return getIronSession<CustomerSessionData>(cookies(), customerSessionOptions)
}
