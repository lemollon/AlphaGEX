/**
 * SPARK orphan-cleanup diagnostic — mirrors the exact matching logic the
 * scanner uses in `dailySandboxCleanup` (scanner.ts:3046-3073) so we can
 * see, right now, whether the logic would mistakenly flag live legs as
 * orphans.
 *
 * Why this exists: today's live SPARK IC was closed at the broker 22
 * minutes after open, before the 50% sliding PT could fire. The close
 * pattern (4 separate single-leg market orders) matches the "orphan
 * cleanup cascade" rather than any PT or stop-loss exit path. We need
 * to see which DB rows the scanner's SELECT is returning and whether
 * the resulting OCC-prefix set covers the legs actually at Tradier.
 *
 * This endpoint is strictly read-only. It does NOT modify any row, it
 * does NOT place any order, and it does NOT touch the paper_account.
 *
 * Route: GET /api/spark/diagnose-orphan-cleanup
 *
 * SPARK-only — other bots return 400.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, num, int, validateBot } from '@/lib/db'
import {
  buildOccSymbol,
  getLoadedSandboxAccountsAsync,
  getSandboxAccountPositions,
  isConfigured,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== 'spark') {
    return NextResponse.json(
      { error: 'SPARK-only — orphan-cleanup diagnostic mirrors the production scanner path.' },
      { status: 400 },
    )
  }

  if (!isConfigured()) {
    return NextResponse.json({ error: 'Tradier not configured' }, { status: 500 })
  }

  try {
    // ── 1. Mirror the scanner's SELECT exactly (scanner.ts:3046-3051) ──
    const scannerSelect = `
      SELECT position_id, status, account_type, dte_mode, person, ticker,
             put_short_strike, put_long_strike,
             call_short_strike, call_long_strike, expiration,
             open_time, close_time
      FROM spark_positions
      WHERE status = 'open' AND dte_mode = '1DTE'
    `
    const scannerMatchesRows = await dbQuery(scannerSelect)

    // ── 2. Also pull the SUPERSET (no filters) so we can see what rows the ──
    // ── scanner's SELECT is missing vs. rows that actually exist.          ──
    const supersetRows = await dbQuery(
      `SELECT position_id, status, account_type, dte_mode, person, ticker,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike, expiration,
              open_time, close_time
       FROM spark_positions
       WHERE status IN ('open', 'pending')
          OR (status = 'closed' AND close_time >= NOW() - INTERVAL '4 hours')
       ORDER BY open_time DESC NULLS LAST
       LIMIT 20`,
    )

    // ── 3. Build the exact paperOccPrefixes set the scanner builds ──
    const paperOccPrefixes = new Set<string>()
    const scannerExpectedLegs: Array<{
      position_id: string
      occ_symbols: string[]
    }> = []
    for (const row of scannerMatchesRows) {
      const ticker = row.ticker || 'SPY'
      const exp = row.expiration instanceof Date
        ? row.expiration.toISOString().slice(0, 10)
        : String(row.expiration).slice(0, 10)
      const legs = [
        buildOccSymbol(ticker, exp, num(row.put_short_strike), 'P'),
        buildOccSymbol(ticker, exp, num(row.put_long_strike), 'P'),
        buildOccSymbol(ticker, exp, num(row.call_short_strike), 'C'),
        buildOccSymbol(ticker, exp, num(row.call_long_strike), 'C'),
      ]
      legs.forEach((occ) => paperOccPrefixes.add(occ))
      scannerExpectedLegs.push({ position_id: row.position_id, occ_symbols: legs })
    }

    // ── 4. For each loaded account (sandbox + production), fetch the live ──
    // ── Tradier legs and run the orphan classification the scanner runs.  ──
    const accounts = await getLoadedSandboxAccountsAsync()

    const perAccount: Array<{
      name: string
      type: string
      tradier_legs: Array<{ symbol: string; quantity: number; cost_basis: number; market_value: number }>
      would_close_as_orphan: string[]
      would_preserve_as_matched: string[]
    }> = []

    for (const acct of accounts) {
      let legs: Awaited<ReturnType<typeof getSandboxAccountPositions>> = []
      try {
        legs = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
      } catch {
        legs = []
      }
      const nonzero = legs.filter((p) => p.quantity !== 0)
      const orphans = nonzero.filter((p) => !paperOccPrefixes.has(p.symbol))
      const matched = nonzero.filter((p) => paperOccPrefixes.has(p.symbol))

      perAccount.push({
        name: acct.name,
        type: acct.type,
        tradier_legs: nonzero.map((p) => ({
          symbol: p.symbol,
          quantity: p.quantity,
          cost_basis: num(p.cost_basis),
          market_value: num(p.market_value),
        })),
        would_close_as_orphan: orphans.map((p) => p.symbol),
        would_preserve_as_matched: matched.map((p) => p.symbol),
      })
    }

    // ── 5. Verdict ──
    const totalTradierLegs = perAccount.reduce((a, b) => a + b.tradier_legs.length, 0)
    const totalWouldOrphan = perAccount.reduce((a, b) => a + b.would_close_as_orphan.length, 0)

    let verdict: 'safe' | 'no_state_to_analyze' | 'bug_detected'
    let verdictExplanation: string

    if (totalTradierLegs === 0) {
      verdict = 'no_state_to_analyze'
      verdictExplanation =
        'No legs at Tradier right now, so there is nothing for the orphan scan to misclassify at this instant. ' +
        'The bug, if present, fires only while a live IC is open. Re-run this endpoint ~30s after the next SPARK open.'
    } else if (totalWouldOrphan > 0) {
      verdict = 'bug_detected'
      verdictExplanation =
        `Scanner would close ${totalWouldOrphan} Tradier leg(s) as "orphans" right now because the DB SELECT ` +
        `returned ${scannerMatchesRows.length} open rows that produce a paperOccPrefixes set of ` +
        `size ${paperOccPrefixes.size}. Fix target: expand the SELECT to include missing account_type / ` +
        `dte_mode cases, OR add a hard safety guard "never close a leg whose OCC matches ANY spark_positions ` +
        `row with status='open' regardless of dte_mode/account_type filter".`
    } else {
      verdict = 'safe'
      verdictExplanation = 'Scanner SELECT covers every broker leg — no misclassification right now.'
    }

    return NextResponse.json({
      bot: 'spark',
      generated_at: new Date().toISOString(),
      scanner_query_mirror: {
        query: scannerSelect.trim(),
        row_count: scannerMatchesRows.length,
        rows: scannerMatchesRows.map((r) => ({
          position_id: r.position_id,
          status: r.status,
          account_type: r.account_type ?? null,
          dte_mode: r.dte_mode ?? null,
          person: r.person ?? null,
          expiration: r.expiration instanceof Date
            ? r.expiration.toISOString().slice(0, 10)
            : String(r.expiration).slice(0, 10),
          strikes: {
            put_short: num(r.put_short_strike),
            put_long: num(r.put_long_strike),
            call_short: num(r.call_short_strike),
            call_long: num(r.call_long_strike),
          },
          open_time: r.open_time,
          close_time: r.close_time,
        })),
      },
      superset_unfiltered: {
        row_count: supersetRows.length,
        rows: supersetRows.map((r) => ({
          position_id: r.position_id,
          status: r.status,
          account_type: r.account_type ?? null,
          dte_mode: r.dte_mode ?? null,
          person: r.person ?? null,
          expiration: r.expiration instanceof Date
            ? r.expiration.toISOString().slice(0, 10)
            : String(r.expiration).slice(0, 10),
          open_time: r.open_time,
          close_time: r.close_time,
        })),
        note:
          'These are all open + recently-closed rows. Compare against scanner_query_mirror.rows — any row ' +
          'present here but NOT in the scanner query is one the orphan cleanup IGNORES, whose legs would ' +
          'be treated as orphans if they exist at the broker.',
      },
      paper_occ_prefixes: {
        count: paperOccPrefixes.size,
        values: Array.from(paperOccPrefixes).sort(),
        built_from_positions: scannerExpectedLegs,
        note:
          'This is the set the scanner builds from its SELECT. A Tradier leg is classified "orphan" ' +
          '(and scheduled for close) iff its OCC symbol is NOT in this set.',
      },
      per_account_analysis: perAccount,
      verdict,
      verdict_explanation: verdictExplanation,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
