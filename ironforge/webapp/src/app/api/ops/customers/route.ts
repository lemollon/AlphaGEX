import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { hashPassword } from '@/lib/auth/password'
import { normalizeEmail } from '@/lib/signup-validation'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { dbQuery, dbExecute } from '@/lib/db'
import { LIVE_BOTS, LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/bots'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Operator customer admin — create customer profiles and (later) map each to
 * the live bot(s) they own. This is the tool that makes a customer's own
 * account visible: a profile with NO bot mapping lands on the empty state, so
 * the operator adds the profile here first, then maps it to spark / spark2.
 *
 *   GET  /api/ops/customers                      → list profiles + their bot mappings
 *   POST /api/ops/customers {action:'create',…}  → create a customer profile
 *   POST /api/ops/customers {action:'map',…}     → grant a bot to a customer
 *   POST /api/ops/customers {action:'unmap',…}   → revoke a bot from a customer
 *
 * Operator session required (ops login / magic link). Customers can never reach
 * this. Writes an audit_events row for every create/map/unmap.
 */

interface UserRow {
  id: string
  email: string
  first_name: string
  last_name: string
  account_status: string
  email_verified: boolean
  created_at: string
}

function isLiveBot(v: unknown): v is LiveBot {
  return typeof v === 'string' && (LIVE_BOTS as readonly string[]).includes(v)
}

async function requireOperator(): Promise<{ ok: true; who: string } | { ok: false; res: NextResponse }> {
  const ops = await getSession()
  if (!ops.userId) {
    return { ok: false, res: NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 }) }
  }
  return { ok: true, who: ops.username ?? String(ops.userId) }
}

export async function GET() {
  const gate = await requireOperator()
  if (!gate.ok) return gate.res
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Customers DB not configured.' }, { status: 503 })
  }

  const users = await customerQuery<UserRow>(
    `SELECT id, email, first_name, last_name, account_status, email_verified, created_at
       FROM users ORDER BY created_at DESC LIMIT 200`,
  )
  // Bot mappings live in the bot DB, keyed by customers-DB users.id (as text).
  const maps = await dbQuery<{ customer_id: string; bot: string }>(
    `SELECT customer_id, bot FROM ironforge_customer_bots`,
  )
  const byCustomer = new Map<string, string[]>()
  for (const m of maps) {
    const list = byCustomer.get(m.customer_id) ?? []
    if (isLiveBot(m.bot)) list.push(m.bot)
    byCustomer.set(m.customer_id, list)
  }

  return NextResponse.json({
    ok: true,
    bots: LIVE_BOTS.map((b) => ({ id: b, label: LIVE_BOT_LABEL[b] })),
    customers: users.map((u) => ({
      id: u.id,
      email: u.email,
      name: `${u.first_name} ${u.last_name}`.trim(),
      status: u.account_status,
      emailVerified: u.email_verified,
      createdAt: u.created_at,
      bots: (byCustomer.get(u.id) ?? []).sort(),
    })),
  })
}

async function audit(userId: string | null, eventType: string, who: string, metadata: Record<string, unknown>) {
  try {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, $2, $3)`,
      [userId, eventType, JSON.stringify({ operator: who, ...metadata })],
    )
  } catch (e) {
    console.error('[ops/customers] audit failed:', eventType, e)
  }
}

export async function POST(req: NextRequest) {
  const gate = await requireOperator()
  if (!gate.ok) return gate.res
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Customers DB not configured.' }, { status: 503 })
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const action = String(body.action ?? '')

  // ---- map / unmap a bot to an existing customer -------------------------
  if (action === 'map' || action === 'unmap') {
    const customerId = String(body.customerId ?? '').trim()
    const bot = body.bot
    if (!customerId) return NextResponse.json({ ok: false, error: 'customerId is required.' }, { status: 400 })
    if (!isLiveBot(bot)) return NextResponse.json({ ok: false, error: `bot must be one of ${LIVE_BOTS.join(', ')}.` }, { status: 400 })

    const exists = await customerQuery<{ id: string }>(`SELECT id FROM users WHERE id = $1 LIMIT 1`, [customerId])
    if (exists.length === 0) return NextResponse.json({ ok: false, error: 'No such customer.' }, { status: 404 })

    if (action === 'map') {
      await dbExecute(
        `INSERT INTO ironforge_customer_bots (customer_id, bot) VALUES ($1, $2) ON CONFLICT DO NOTHING`,
        [customerId, bot],
      )
    } else {
      await dbExecute(`DELETE FROM ironforge_customer_bots WHERE customer_id = $1 AND bot = $2`, [customerId, bot])
    }
    await audit(customerId, action === 'map' ? 'OPS_BOT_MAPPED' : 'OPS_BOT_UNMAPPED', gate.who, { bot })
    return NextResponse.json({ ok: true })
  }

  // ---- create a customer profile -----------------------------------------
  if (action === 'create') {
    const email = normalizeEmail(String(body.email ?? ''))
    const firstName = String(body.firstName ?? '').trim()
    const lastName = String(body.lastName ?? '').trim()
    const phone = String(body.phone ?? '').trim()
    const state = String(body.state ?? '').trim()
    const password = String(body.password ?? '')

    const errors: Record<string, string> = {}
    if (!email.includes('@') || !email.includes('.')) errors.email = 'Enter a valid email.'
    if (!firstName) errors.firstName = 'First name is required.'
    if (!lastName) errors.lastName = 'Last name is required.'
    if (password.length < 8) errors.password = 'Password must be at least 8 characters.'
    if (Object.keys(errors).length > 0) {
      return NextResponse.json({ ok: false, error: 'Please correct the highlighted fields.', fields: errors }, { status: 400 })
    }

    const existing = await customerQuery<{ id: string }>(`SELECT id FROM users WHERE email = $1 LIMIT 1`, [email])
    if (existing.length > 0) {
      return NextResponse.json({ ok: false, code: 'duplicate_email', error: 'A profile with that email already exists.' }, { status: 409 })
    }

    const passwordHash = await hashPassword(password)
    // Operator-created: email pre-verified and onboarding skipped to the end so
    // the customer can sign in immediately with the password the operator sets.
    const rows = await customerQuery<{ id: string }>(
      `INSERT INTO users
         (password_hash, first_name, last_name, email, phone, state,
          account_status, onboarding_step, email_verified)
       VALUES ($1,$2,$3,$4,$5,$6,'active','brokerage_connected',TRUE)
       RETURNING id`,
      [passwordHash, firstName, lastName, email, phone, state],
    )
    const id = rows[0].id
    await audit(id, 'OPS_PROFILE_CREATED', gate.who, { email, name: `${firstName} ${lastName}`.trim() })
    return NextResponse.json({ ok: true, id })
  }

  return NextResponse.json({ ok: false, error: `Unknown action "${action}".` }, { status: 400 })
}
