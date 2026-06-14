import type { IronSession } from 'iron-session'
import { getIronSession } from 'iron-session'
import { cookies } from 'next/headers'
import { customerSessionOptions, type CustomerSessionData } from '@/lib/auth/customer-session'

/**
 * Route-handler / server-component accessor (Node runtime only).
 *
 * Split out of `customer-session.ts` because that module is in the middleware
 * (Edge) import graph and must stay free of `next/headers`. Importing
 * `next/headers` into the Edge bundle fails the production build.
 */
export async function getCustomerSession(): Promise<IronSession<CustomerSessionData>> {
  return getIronSession<CustomerSessionData>(cookies(), customerSessionOptions)
}
