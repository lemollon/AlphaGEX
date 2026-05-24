import { getIronSession, type IronSession } from 'iron-session'
import { cookies } from 'next/headers'
import { sessionOptions, type SessionData } from './session'

/** Route-handler / server-component session accessor (Node runtime only). */
export async function getSession(): Promise<IronSession<SessionData>> {
  return getIronSession<SessionData>(cookies(), sessionOptions)
}
