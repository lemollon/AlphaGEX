import { NextRequest, NextResponse } from 'next/server'
import { getLiveTrade } from '@/lib/live/summary'
import { resolveLiveViewer, isLiveBot, type LiveBot } from '@/lib/live/viewer'
import { acquireStreamSlot, releaseStreamSlot } from '@/lib/live/stream-registry'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Sub-5-second live positions/P&L stream — fulfils the dev-handoff's
 * `/ws/positions` contract over Server-Sent Events rather than a WebSocket.
 * Next.js route handlers on this single Render web service cannot host a
 * WebSocket server (ironforge/CLAUDE.md: "Frontend + API + Scanner | Next.js 14
 * on Render (single web service)"); SSE is a one-way server→client push over
 * plain HTTP, which is exactly what a positions/P&L feed needs, and both
 * EventSource (web) and a pure-JS reader (mobile, see src/api/sparky.ts for the
 * existing `expo/fetch` streaming pattern) can consume it with no new
 * dependency.
 *
 * DATA SOURCE: getLiveTrade() — the exact function GET /api/live/trade already
 * calls. No new marks, no new pricing path; this only pushes the same payload
 * on a tighter clock instead of waiting for the client's next poll.
 *
 * AUTH: resolveLiveViewer(req), the same scoping every other /api/live/* route
 * uses (cookie or mobile bearer; customers see only their own mapped bot(s) via
 * ironforge_customer_bots; operators see the fleet). No bot this viewer does not
 * own can ever be requested via `?account=`.
 *
 * FRESHNESS, HONESTLY: a push every PUSH_INTERVAL_MS re-runs getLiveTrade(),
 * which fetches a live Tradier mark when the bot is Tradier-configured
 * (isConfigured() in lib/tradier.ts) — so SPARK's and a configured FLAME's
 * numbers really are that fresh. When Tradier is not configured for a bot,
 * getLiveTrade() falls back to the scanner's own position_snapshots row, which
 * the scanner writes once a minute (ironforge/CLAUDE.md: "Scanner runs every
 * minute") — this stream then delivers that same once-a-minute number faster,
 * not fresher. See PR description for which path each bot is on.
 */
const PUSH_INTERVAL_MS = 2_500
const HEARTBEAT_MS = 15_000
const MAX_STREAMS_PER_VIEWER = 3

function sseEvent(event: string, data: unknown): Uint8Array {
  return new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
}

function sseHeartbeat(): Uint8Array {
  // Comment-line ping: ignored by EventSource/SSE parsers, but keeps
  // intermediary proxies and the connection itself from going idle.
  return new TextEncoder().encode(`: heartbeat ${Date.now()}\n\n`)
}

function sseHeaders(): HeadersInit {
  return {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    // Disables response buffering on nginx-style proxies in front of Render,
    // so pushes aren't held until a buffer fills.
    'X-Accel-Buffering': 'no',
  }
}

type Viewer = Awaited<ReturnType<typeof resolveLiveViewer>>

/**
 * One push's payload.
 *
 * `?account=<bot>` (the web Live page, pinned to one agent) gets back exactly
 * the LiveTrade shape /api/live/trade returns, so the client can drop it
 * straight into the existing SWR cache for that key.
 *
 * No `account` param (the mobile Forge screen, which shows every owned agent at
 * once) gets every allowed bot's trade, matching /api/live/agents' per-agent
 * `trade` field.
 */
async function buildPayload(bots: LiveBot[], viewer: Viewer, single: boolean) {
  const results = await Promise.all(
    bots.map(async (bot) => {
      const person = viewer.persons?.[bot] ?? (bot === viewer.bot ? viewer.person : null)
      const trade = await getLiveTrade(bot, person, viewer.isOperator)
      return { bot, trade }
    }),
  )
  if (single && results.length === 1) return results[0].trade
  return { agents: results, as_of: new Date().toISOString() }
}

export async function GET(req: NextRequest) {
  const viewer = await resolveLiveViewer(req)

  if (!viewer.bot) {
    // Same empty-state contract as /api/live/trade: an unmapped viewer (fresh
    // signup / anonymous) gets an honest empty stream, never another
    // account's positions.
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(sseEvent('positions', { empty: true }))
        controller.close()
      },
    })
    return new Response(stream, { headers: sseHeaders() })
  }

  const requested = req.nextUrl.searchParams.get('account')
  const single = requested != null
  const scopedBots: LiveBot[] =
    isLiveBot(requested) && viewer.allowedBots.includes(requested)
      ? [requested]
      : requested
        ? [] // requested a bot this viewer does not own — stream nothing, not a leak
        : viewer.allowedBots

  // Concurrency cap, scoped to the signed-in identity. Operators and
  // anonymous/public-mode viewers carry no customerId, so they're capped by
  // the resolved bot+person pair instead — the same thing that distinguishes
  // them everywhere else in this module (see viewer.ts).
  const slotKey =
    viewer.customerId ?? `${viewer.isOperator ? 'operator' : 'anon'}:${viewer.bot}:${viewer.person ?? ''}`
  if (!acquireStreamSlot(slotKey, MAX_STREAMS_PER_VIEWER)) {
    return NextResponse.json(
      { error: 'Too many open position streams for this account. Close another tab and try again.' },
      { status: 429 },
    )
  }

  let pushTimer: ReturnType<typeof setInterval> | undefined
  let heartbeatTimer: ReturnType<typeof setInterval> | undefined
  let torndown = false

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const teardown = () => {
        if (torndown) return
        torndown = true
        if (pushTimer) clearInterval(pushTimer)
        if (heartbeatTimer) clearInterval(heartbeatTimer)
        releaseStreamSlot(slotKey)
        try {
          controller.close()
        } catch {
          // already closed by the consumer disconnecting
        }
      }

      const pushOnce = async () => {
        try {
          const payload = await buildPayload(scopedBots, viewer, single)
          controller.enqueue(sseEvent('positions', payload))
        } catch (err: unknown) {
          try {
            const msg = err instanceof Error ? err.message : String(err)
            controller.enqueue(sseEvent('error', { error: msg }))
          } catch {
            // the controller itself is gone — the client disconnected mid-push
            teardown()
          }
        }
      }

      try {
        await pushOnce()
        pushTimer = setInterval(pushOnce, PUSH_INTERVAL_MS)
        heartbeatTimer = setInterval(() => {
          try {
            controller.enqueue(sseHeartbeat())
          } catch {
            teardown()
          }
        }, HEARTBEAT_MS)
      } catch {
        teardown()
        return
      }

      // `cancel()` can run while the `await pushOnce()` above was still
      // pending (the client disconnected before the first push landed) — in
      // that race, torndown is already true by the time we get here, and the
      // two setInterval calls just above would otherwise leak (cancel() ran
      // before they existed, so it had nothing to clear). Catch that now
      // instead of trusting ordering between two independent microtask
      // queues.
      if (torndown) {
        clearInterval(pushTimer)
        clearInterval(heartbeatTimer)
        return
      }

      // Only while the client is connected: the moment the request is
      // aborted (tab closed, EventSource.close(), app backgrounded on
      // mobile), tear down the timers and release the slot immediately
      // rather than continuing to query Tradier/Postgres for no one.
      req.signal.addEventListener('abort', teardown)
    },
    cancel() {
      // Fires when the consumer stops reading without an abort signal
      // (e.g. some fetch/stream adapters) — same cleanup, idempotent.
      if (torndown) return
      torndown = true
      if (pushTimer) clearInterval(pushTimer)
      if (heartbeatTimer) clearInterval(heartbeatTimer)
      releaseStreamSlot(slotKey)
    },
  })

  return new Response(stream, { headers: sseHeaders() })
}
