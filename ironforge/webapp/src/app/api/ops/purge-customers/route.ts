import { NextRequest, NextResponse } from 'next/server'
import { isCustomersDbConfigured, customerQuery, customerTransaction } from '@/lib/customers-db'
import { dbExecute } from '@/lib/db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * ONE-TIME customer purge (2026-07-31, operator-requested reset before launch):
 * wipes every customer account and all data hanging off it so everyone signs up
 * fresh. Stripe subscriptions must be canceled IN STRIPE FIRST — this endpoint
 * refuses to run while any live Stripe-linked subscription row remains (override
 * with force:true only after verifying Stripe is clean).
 *
 * DARK BY DEFAULT: without the CUSTOMER_PURGE_TOKEN env var this route is a 404
 * on every deployment. Arming it is a deliberate operator act (set the env, call
 * once with the token + confirm phrase, remove the env). Remove this route after
 * use — a purge endpoint has no business living in the codebase long-term.
 *
 * What it deletes: TRUNCATE users CASCADE — every table with an FK chain to users
 * (subscriptions, enrollments, legal acceptances, brokerage connections, broker
 * accounts, agent configs, activations, trials, audit events, community messages,
 * verification tokens, oauth states, idempotency keys, customer positions, attio
 * queue). What it keeps: legal_documents and community_channels (seed/registry
 * data, no user FK) and EVERYTHING in the trading DB except the
 * ironforge_customer_bots viewer mappings (which point at deleted customer ids).
 * ironforge_accounts — real-money trading — is NEVER touched here.
 */
export async function POST(req: NextRequest) {
  const token = process.env.CUSTOMER_PURGE_TOKEN
  if (!token) return NextResponse.json({ ok: false }, { status: 404 })
  if (req.headers.get('x-purge-token') !== token) {
    return NextResponse.json({ ok: false }, { status: 403 })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'customers DB not configured' }, { status: 503 })
  }

  const body = (await req.json().catch(() => ({}))) as { confirm?: string; force?: boolean }
  if (body.confirm !== 'PURGE ALL CUSTOMERS') {
    return NextResponse.json(
      { ok: false, error: 'Body must be {"confirm":"PURGE ALL CUSTOMERS"}.' },
      { status: 400 },
    )
  }

  // Never orphan live billing: a deleted account with a live Stripe subscription
  // keeps charging a card that no longer maps to anyone.
  const liveSubs = await customerQuery<{ bot: string; status: string; stripe_subscription_id: string }>(
    `SELECT bot, status, stripe_subscription_id FROM customer_bot_subscriptions
      WHERE stripe_subscription_id IS NOT NULL AND status IN ('trialing','active','past_due')`,
  )
  if (liveSubs.length > 0 && body.force !== true) {
    return NextResponse.json(
      { ok: false, error: 'Live Stripe-linked subscriptions exist — cancel in Stripe first or pass force:true.', live_subs: liveSubs },
      { status: 409 },
    )
  }

  const before = await customerQuery<{ users: string; subs: string; enrollments: string; connections: string }>(
    `SELECT (SELECT count(*) FROM users) AS users,
            (SELECT count(*) FROM customer_bot_subscriptions) AS subs,
            (SELECT count(*) FROM enrollments) AS enrollments,
            (SELECT count(*) FROM brokerage_connections) AS connections`,
  )

  await customerTransaction(async (run) => {
    await run(`TRUNCATE users CASCADE`)
  })

  // Trading DB: drop the customer→bot viewer mappings (they reference the deleted
  // customer ids). ironforge_accounts and all bot tables are untouched.
  let mappingsCleared = 0
  try {
    mappingsCleared = await dbExecute(`DELETE FROM ironforge_customer_bots`)
  } catch (e) {
    console.error('[purge-customers] mapping clear failed:', e)
  }

  const after = await customerQuery<{ users: string }>(`SELECT count(*) AS users FROM users`)
  console.log('[purge-customers] PURGED', JSON.stringify({ before: before[0], mappingsCleared }))

  return NextResponse.json({
    ok: true,
    purged: before[0],
    users_after: Number(after[0]?.users ?? -1),
    trading_db_mappings_cleared: mappingsCleared,
    stripe_live_subs_at_purge: liveSubs.length,
  })
}
