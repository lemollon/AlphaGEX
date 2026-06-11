import { NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST() {
  const session = await getCustomerSession()
  session.destroy()
  return NextResponse.json({ ok: true })
}
