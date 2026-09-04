import { NextRequest, NextResponse } from 'next/server'
import { getLiveSummary, getLiveTrade } from '@/lib/live/summary'
import { getLifetimeStats } from '@/lib/live/home'
import { loadBotTrades } from '@/lib/live/trades-history'
import { computeCardStats, type CardStats } from '@/lib/live/card-stats'
import { resolveLiveViewer, LIVE_BOT_LABEL, type LiveBot } from '@/lib/live/viewer'

export const dynamic = 'force-dynamic'

/**
 * GET /api/live/agents — every agent this viewer owns, each with its own state and trade.
 *
 * UX-002 shows Spark AND Flame side by side, each with its own status, account and open
 * position. Nothing could answer that: /api/live/summary returns one `state` and
 * /api/live/trade returns one `trade`, both for a single resolved bot. The mobile Forge
 * screen consequently rendered one tile and its own comment said so — "the current API
 * returns a single LiveTrade, so this renders the one it has rather than faking a second".
 *
 * This is the fan-out. It reuses getLiveSummary/getLiveTrade per bot rather than
 * reimplementing either, so there is exactly one definition of what an agent's state is
 * and this route cannot drift from the single-agent one.
 *
 * AUTHORIZATION: the bot list is `viewer.allowedBots`, resolved server-side by
 * resolveLiveViewer — never a client-supplied list. A customer gets only their mapped
 * bots; there is no query parameter that widens it.
 *
 * COST: one summary + one trade + one lifetime-stats + one closed-trades query set per
 * bot (the last two feed the Forge card stats row). That is 4× today (Spark, Flame) at a
 * 60s poll, which is why the client must not poll this faster than it polls summary.
 * If the roster ever grows past a handful, this needs a batched query, not more fan-out.
 */
export async function GET(req: NextRequest) {
  try {
    const viewer = await resolveLiveViewer(req)
    const bots = (viewer.allowedBots ?? []).filter(Boolean) as LiveBot[]

    if (bots.length === 0) {
      // No live account (fresh signup / anonymous). An honest empty, never another
      // account's data.
      return NextResponse.json({ empty: true, viewer, agents: [] })
    }

    const agents = await Promise.all(
      bots.map(async (bot) => {
        // PER-BOT owner. viewer.person is the owner of the SELECTED bot only — the
        // interface says so — so reusing it across the fan-out would scope every agent
        // to the first agent's account and quietly show one customer's Flame numbers
        // under their Spark tile. viewer.persons is the bot -> owner map that exists
        // for exactly this case.
        const person = viewer.persons?.[bot] ?? (bot === viewer.bot ? viewer.person : null)

        // Settled, not all-or-nothing: one bot's query failing must not blank the other
        // agent's tile. A failed agent reports itself rather than vanishing, because a
        // silently missing agent reads as "you don't own it".
        //
        // `lifetime` + `trades` feed the Forge card stats row (Account Capital / Growth /
        // Last 10 / Best Trade, handoff/ledger-kpis.md PART 2). They reuse getLifetimeStats
        // (home.ts) and loadBotTrades (trades-history.ts) — the same queries the Home
        // wealth snapshot and Ledger already run — rather than adding new ones.
        const [summary, trade, lifetime, trades] = await Promise.allSettled([
          getLiveSummary(bot, { person, allowAggregate: false }),
          getLiveTrade(bot, person, viewer.isOperator),
          getLifetimeStats(bot, person, viewer.isOperator),
          loadBotTrades(bot, person, (viewer.paperBots ?? []).includes(bot), viewer.isOperator),
        ])

        const s = summary.status === 'fulfilled' ? summary.value : null
        const t = trade.status === 'fulfilled' ? trade.value : null

        // Both halves must load for an honest stats row — partial data (e.g. starting
        // capital but no trade list) would silently misrepresent Growth/Last 10/Best
        // Trade rather than admitting the row isn't available right now.
        const stats: CardStats | null =
          lifetime.status === 'fulfilled' && trades.status === 'fulfilled'
            ? computeCardStats(
                lifetime.value.starting_capital,
                lifetime.value.total_realized_pnl,
                trades.value.map((tr) => ({ realized_pnl: tr.pnl })),
              )
            : null

        return {
          bot,
          label: LIVE_BOT_LABEL[bot] ?? bot,
          paper: (viewer.paperBots ?? []).includes(bot),
          state: s?.state ?? null,
          account: s?.account ?? null,
          trade: t,
          stats,
          error:
            summary.status === 'rejected'
              ? 'state'
              : trade.status === 'rejected'
                ? 'trade'
                : null,
        }
      }),
    )

    return NextResponse.json({ viewer, agents, as_of: new Date().toISOString() })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
