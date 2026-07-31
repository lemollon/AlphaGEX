import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { customerQuery, customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'
import { errorEnvelope, statusFor } from '@/lib/enrollment/errors'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Customer automation pause (spec §23). Pausing stops NEW positions immediately;
 * open positions still close per the strategy's exit rules — the executor's gate
 * blocks opens on status='paused' but never gates closes, so a pause can never
 * strand risk in the account. Trial days keep counting while paused (ADR 0008).
 */

interface ActivationRow {
  activation_id: string
  agent_code: string
  status: string
  paused_at: string | null
}

async function liveActivations(userId: string): Promise<ActivationRow[]> {
  return customerQuery<ActivationRow>(
    `SELECT a.id AS activation_id, ac.agent_code, a.status, a.paused_at
       FROM activations a
       JOIN agent_configs ac ON ac.id = a.config_id
      WHERE ac.user_id = $1 AND a.status IN ('active', 'paused')
      ORDER BY a.activated_at DESC NULLS LAST`,
    [userId],
  )
}

export async function GET() {
  const session = await getCustomerSession()
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: true, activations: [] })

  const rows = await liveActivations(session.customerId)
  return NextResponse.json({
    ok: true,
    activations: rows.map((r) => ({
      activation_id: r.activation_id,
      agent: r.agent_code,
      paused: r.status === 'paused',
      paused_at: r.paused_at,
    })),
  })
}

export async function POST(req: NextRequest) {
  const session = await getCustomerSession()
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Automation controls are temporarily unavailable.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  const body = (await req.json().catch(() => ({}))) as { paused?: unknown; agent?: unknown }
  if (typeof body.paused !== 'boolean') {
    const e = errorEnvelope('VALIDATION_FAILED', 'Send { "paused": true } or { "paused": false }.', { field: 'paused' })
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  const agent = typeof body.agent === 'string' ? body.agent.toLowerCase() : null
  if (agent !== null && agent !== 'spark' && agent !== 'flame') {
    const e = errorEnvelope('VALIDATION_FAILED', 'Unknown agent.', { field: 'agent' })
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  const nextStatus = body.paused ? 'paused' : 'active'
  const updated = await customerExecute(
    `UPDATE activations a
        SET status = $2,
            paused_at = CASE WHEN $2 = 'paused' THEN now() ELSE a.paused_at END,
            updated_at = now()
       FROM agent_configs ac
      WHERE ac.id = a.config_id
        AND ac.user_id = $1
        AND a.status IN ('active', 'paused')
        AND a.status IS DISTINCT FROM $2
        AND ($3::text IS NULL OR ac.agent_code = $3)`,
    [session.customerId, nextStatus, agent],
  )

  if (updated > 0) {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, $2, $3)`,
      [session.customerId, body.paused ? 'AUTOMATION_PAUSED' : 'AUTOMATION_RESUMED', JSON.stringify({ agent: agent ?? 'all' })],
    ).catch(() => {})
  }

  const rows = await liveActivations(session.customerId)
  return NextResponse.json({
    ok: true,
    updated,
    activations: rows.map((r) => ({
      activation_id: r.activation_id,
      agent: r.agent_code,
      paused: r.status === 'paused',
      paused_at: r.paused_at,
    })),
  })
}
