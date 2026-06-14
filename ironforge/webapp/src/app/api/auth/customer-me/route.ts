import { NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET() {
  const session = await getCustomerSession()
  if (!session.customerId) {
    return NextResponse.json({ ok: false }, { status: 401 })
  }
  return NextResponse.json({
    ok: true,
    customer: {
      id: session.customerId,
      email: session.email,
      emailVerified: session.emailVerified,
      onboardingStep: session.onboardingStep,
    },
  })
}
