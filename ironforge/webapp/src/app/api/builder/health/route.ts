/**
 * One-shot health check for all four bot Builder/snapshot endpoints.
 *
 * Hits /api/{bot}/builder/snapshot for FLAME, SPARK, INFERNO, BLAZE and
 * asserts the shape invariants that were established in the 2026-05-17
 * audit (PRs #2328/#2329/#2330):
 *
 *   - max_loss_at_expiry matches (width - credit) × 100 × contracts for ICs
 *     and -debit × 100 × contracts for BLAZE (within 1% tolerance to
 *     absorb rounding).
 *   - sl_mult is non-null for IC bots (read from {bot}_config); null for
 *     BLAZE (intentional — uses DEFAULT_BLAZE_CONFIG hardcoded thresholds).
 *   - strategy_type matches the expected family per bot. BLAZE in
 *     particular must NOT be 'iron_condor' — that's the regression
 *     signal that the vertical-debit branch in the snapshot route got
 *     bypassed and IC math is running on zero-padded leg columns again.
 *   - max_loss_at_expiry equals the legacy max_loss alias.
 *
 * GET /api/builder/health
 *   200 → { overall: 'pass'|'fail'|'no_positions', bots: {...} }
 * GET /api/builder/health?format=text
 *   200 → plain text report
 *
 * Single curl replaces the manual four-bot loop the operator used to run.
 */
import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

type BotName = 'flame' | 'spark' | 'inferno' | 'blaze'

interface BotCheck {
  bot: BotName
  status: 'pass' | 'fail' | 'no_position'
  strategy_type: string | null
  position_id: string | null
  contracts: number | null
  max_loss_at_expiry: number | null
  expected_max_loss: number | null
  stop_target_loss: number | null
  sl_mult: number | null
  failures: string[]
}

interface HealthReport {
  overall: 'pass' | 'fail' | 'no_positions'
  generated_at: string
  bots: Record<BotName, BotCheck>
}

const EXPECTED_STRATEGY: Record<BotName, RegExp> = {
  flame: /^put_credit_spread$/,
  spark: /^iron_condor$/,
  inferno: /^iron_condor$/,
  blaze: /^vertical_debit_(call|put)$/,
}

async function checkOne(origin: string, bot: BotName): Promise<BotCheck> {
  const out: BotCheck = {
    bot,
    status: 'no_position',
    strategy_type: null,
    position_id: null,
    contracts: null,
    max_loss_at_expiry: null,
    expected_max_loss: null,
    stop_target_loss: null,
    sl_mult: null,
    failures: [],
  }

  try {
    const res = await fetch(`${origin}/api/${bot}/builder/snapshot?account_type=sandbox`, {
      cache: 'no-store',
    })
    if (!res.ok) {
      out.failures.push(`snapshot fetch returned ${res.status}`)
      out.status = 'fail'
      return out
    }
    const d = await res.json()
    if (d?.position == null) {
      // No closed/open position yet — nothing to validate. Don't fail.
      return out
    }
    const p = d.position
    const m = d.metrics ?? {}
    out.strategy_type = d.strategy_type ?? null
    out.position_id = p.position_id ?? null
    out.contracts = typeof p.contracts === 'number' ? p.contracts : null
    out.max_loss_at_expiry = typeof m.max_loss_at_expiry === 'number' ? m.max_loss_at_expiry : null
    out.stop_target_loss = m.stop_target_loss ?? null
    out.sl_mult = m.sl_mult ?? null

    // 1. strategy_type matches expected family.
    if (out.strategy_type == null || !EXPECTED_STRATEGY[bot].test(out.strategy_type)) {
      out.failures.push(
        `strategy_type=${out.strategy_type ?? 'null'} does not match ${EXPECTED_STRATEGY[bot]} ` +
        `(BLAZE regression canary: 'iron_condor' here means the vertical-debit branch was bypassed)`,
      )
    }

    // 2. Expected max loss math. For BLAZE use debit; for IC bots use
    //    (spread_width - credit) * 100 * contracts.
    const contracts = out.contracts ?? 0
    let expected: number | null = null
    if (bot === 'blaze' && typeof p.debit === 'number') {
      expected = -p.debit * 100 * contracts
    } else if (typeof p.spread_width === 'number' && typeof p.entry_credit === 'number') {
      const width = p.spread_width
      const credit = p.entry_credit
      expected = (credit - width) * 100 * contracts
    }
    out.expected_max_loss = expected != null ? Math.round(expected * 100) / 100 : null

    if (out.max_loss_at_expiry != null && out.expected_max_loss != null) {
      const tolerance = Math.max(1, Math.abs(out.expected_max_loss) * 0.01)
      if (Math.abs(out.max_loss_at_expiry - out.expected_max_loss) > tolerance) {
        out.failures.push(
          `max_loss_at_expiry=${out.max_loss_at_expiry} differs from expected=${out.expected_max_loss} ` +
          `by more than 1% (tolerance=${tolerance.toFixed(2)})`,
        )
      }
    } else if (out.max_loss_at_expiry == null) {
      out.failures.push('max_loss_at_expiry is null')
    }

    // 3. legacy max_loss alias must match max_loss_at_expiry.
    if (typeof m.max_loss === 'number' && out.max_loss_at_expiry != null
        && Math.abs(m.max_loss - out.max_loss_at_expiry) > 0.5) {
      out.failures.push(
        `legacy max_loss=${m.max_loss} differs from max_loss_at_expiry=${out.max_loss_at_expiry}`,
      )
    }

    // 4. sl_mult expectation: non-null for IC bots, null for BLAZE.
    if (bot === 'blaze') {
      if (out.sl_mult != null) {
        out.failures.push(`sl_mult=${out.sl_mult} should be null for BLAZE (no config-load)`)
      }
    } else {
      if (out.sl_mult == null) {
        out.failures.push(`sl_mult is null — config-load query in snapshot route is stale or {bot}_config missing`)
      }
    }

    out.status = out.failures.length === 0 ? 'pass' : 'fail'
  } catch (err: unknown) {
    out.failures.push(`exception: ${err instanceof Error ? err.message : String(err)}`)
    out.status = 'fail'
  }

  return out
}

export async function GET(req: NextRequest) {
  const origin = req.nextUrl.origin
  const format = req.nextUrl.searchParams.get('format') || 'json'
  const bots: BotName[] = ['flame', 'spark', 'inferno', 'blaze']

  const results = await Promise.all(bots.map((b) => checkOne(origin, b)))
  const byBot = {} as Record<BotName, BotCheck>
  for (const r of results) byBot[r.bot] = r

  const anyFail = results.some((r) => r.status === 'fail')
  const anyPos = results.some((r) => r.status === 'pass')
  const overall: HealthReport['overall'] = anyFail
    ? 'fail'
    : anyPos ? 'pass' : 'no_positions'

  const report: HealthReport = {
    overall,
    generated_at: new Date().toISOString(),
    bots: byBot,
  }

  if (format === 'text') {
    return new NextResponse(toText(report), {
      status: 200,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    })
  }
  return NextResponse.json(report, { status: overall === 'fail' ? 500 : 200 })
}

function toText(r: HealthReport): string {
  const lines: string[] = []
  lines.push(`Builder snapshot health: ${r.overall.toUpperCase()}`)
  lines.push(`Generated: ${r.generated_at}`)
  lines.push('')
  for (const bot of ['flame', 'spark', 'inferno', 'blaze'] as BotName[]) {
    const c = r.bots[bot]
    lines.push(`[${c.status.toUpperCase()}] ${bot.toUpperCase()}`)
    if (c.position_id) {
      lines.push(`  position: ${c.position_id} (${c.contracts ?? '?'}c)`)
      lines.push(`  strategy: ${c.strategy_type}`)
      lines.push(`  max_loss_at_expiry: ${c.max_loss_at_expiry}  expected: ${c.expected_max_loss}`)
      lines.push(`  stop_target_loss:   ${c.stop_target_loss}    sl_mult: ${c.sl_mult}`)
    } else {
      lines.push(`  (no position to validate)`)
    }
    for (const f of c.failures) lines.push(`  ! ${f}`)
    lines.push('')
  }
  return lines.join('\n')
}
