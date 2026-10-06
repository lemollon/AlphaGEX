import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isPublicMode } from '@/lib/auth/access'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { ENROLL_FUNNEL_STEPS } from '@/lib/analytics/events'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/ops/analytics/summary — operator-only read side of the events
 * pipe. Two shapes:
 *
 *  - `counts`: one row per (event, day) over the requested window, the raw
 *    material for "is anyone hitting cta_click" style questions.
 *  - `enrollFunnel`: distinct viewers (by user_id, falling back to anon_id)
 *    who ever fired `enroll_step_view` for each rail step, in step order
 *    (lib/enrollment/steps.ts PAGE_RANK order) — a classic drop-off funnel,
 *    plus the matching `enroll_step_complete` count per step.
 *
 * Gated the same way as /api/ops/traffic: a public-mode deployment has no
 * login wall, so it is already-authorized; everyone else needs an operator
 * session.
 */

const DEFAULT_DAYS = 30
const MAX_DAYS = 90

async function requireOperator(): Promise<{ ok: true } | { ok: false; res: NextResponse }> {
  if (isPublicMode()) return { ok: true }
  const ops = await getSession()
  if (!ops.userId) {
    return { ok: false, res: NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 }) }
  }
  return { ok: true }
}

interface CountRow {
  day: string
  event: string
  c: number
}

interface FunnelRow {
  step: string
  viewers: number
  completers: number
}

export async function GET(req: NextRequest) {
  const gate = await requireOperator()
  if (!gate.ok) return gate.res
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'Customers DB not configured.' }, { status: 503 })
  }

  const requested = Number(req.nextUrl.searchParams.get('days') ?? DEFAULT_DAYS)
  const days = Number.isFinite(requested) && requested > 0 ? Math.min(Math.trunc(requested), MAX_DAYS) : DEFAULT_DAYS

  const [countRows, funnelRows] = await Promise.all([
    customerQuery<CountRow>(
      `SELECT (created_at AT TIME ZONE 'America/Chicago')::date::text AS day, event, count(*)::int AS c
         FROM analytics_events
        WHERE created_at > now() - interval '${days} days'
        GROUP BY 1, 2
        ORDER BY 1, 2`,
    ),
    customerQuery<FunnelRow>(
      `WITH viewer AS (
         SELECT coalesce(user_id::text, anon_id) AS who,
                props->>'step' AS step
           FROM analytics_events
          WHERE event = 'enroll_step_view' AND props->>'step' IS NOT NULL
       ),
       completer AS (
         SELECT coalesce(user_id::text, anon_id) AS who,
                props->>'step' AS step
           FROM analytics_events
          WHERE event = 'enroll_step_complete' AND props->>'step' IS NOT NULL
       )
       SELECT v.step AS step,
              count(DISTINCT v.who)::int AS viewers,
              (SELECT count(DISTINCT c.who)::int FROM completer c WHERE c.step = v.step) AS completers
         FROM viewer v
        GROUP BY v.step`,
    ),
  ])

  const byDay: Record<string, Record<string, number>> = {}
  for (const row of countRows) {
    byDay[row.day] ??= {}
    byDay[row.day][row.event] = row.c
  }

  const funnelByStep = new Map(funnelRows.map((r) => [r.step, r]))
  const enrollFunnel = ENROLL_FUNNEL_STEPS.map((step) => ({
    step,
    viewers: funnelByStep.get(step)?.viewers ?? 0,
    completers: funnelByStep.get(step)?.completers ?? 0,
  }))

  return NextResponse.json({
    ok: true,
    generatedAt: new Date().toISOString(),
    tz: 'America/Chicago',
    days,
    counts: byDay,
    enrollFunnel,
  })
}
