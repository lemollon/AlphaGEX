/**
 * SMS notifications for SPARK trade events (Commit N1).
 *
 * Informational only — does NOT affect trading. The scanner fires these
 * after the DB state has settled (post-open confirmation, post-close
 * update). Every send is wrapped in try/catch so a Twilio outage, bad
 * credentials, or a rate-limit cannot block or alter a real trade.
 *
 * Required env vars (add to IronForge Render):
 *   TWILIO_ACCOUNT_SID
 *   TWILIO_AUTH_TOKEN
 *   TWILIO_FROM_NUMBER   (your Twilio-owned phone, format: +15551234567)
 *
 * If any of those are missing, sendSms() logs "TWILIO_NOT_CONFIGURED"
 * and returns success=false — subscribers still sit in the DB, just no
 * text is sent. Flip the three env vars on and it starts working.
 *
 * Cost reference: Twilio SMS is ~$0.0079/msg to US numbers. At 2 events
 * per trade × ~1 trade/day × 1 subscriber = ~$0.47/month. Cheap.
 */
import { dbQuery } from './db'

const TWILIO_API_URL = (sid: string) =>
  `https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`

// ── Types ──────────────────────────────────────────────────────────────

export interface TradeOpenContext {
  position_id: string
  person: string | null
  account_type: 'sandbox' | 'production'
  ticker: string
  expiration: string
  put_long: number
  put_short: number
  call_short: number
  call_long: number
  contracts: number
  total_credit: number
  spy_at_entry: number | null
  vix_at_entry: number | null
  collateral: number
  open_time_iso: string
}

export interface TradeCloseContext {
  position_id: string
  person: string | null
  account_type: 'sandbox' | 'production'
  close_reason: string
  close_price: number
  realized_pnl: number
  total_credit: number
  contracts: number
  hold_minutes: number | null
}

interface Subscriber {
  id: number
  phone_number: string
  enabled: boolean
  notify_open: boolean
  notify_close: boolean
  label: string | null
}

// ── Twilio client (no SDK — one fetch is cheaper than pulling twilio.js) ─

async function sendSms(toNumber: string, body: string): Promise<{ success: boolean; error?: string }> {
  const sid = process.env.TWILIO_ACCOUNT_SID
  const token = process.env.TWILIO_AUTH_TOKEN
  const from = process.env.TWILIO_FROM_NUMBER
  if (!sid || !token || !from) {
    console.warn(`[notifications] TWILIO_NOT_CONFIGURED — skipping SMS to ${toNumber} (need TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER in IronForge Render env)`)
    return { success: false, error: 'TWILIO_NOT_CONFIGURED' }
  }

  const auth = Buffer.from(`${sid}:${token}`).toString('base64')
  const params = new URLSearchParams({ To: toNumber, From: from, Body: body.slice(0, 1500) })

  try {
    const resp = await fetch(TWILIO_API_URL(sid), {
      method: 'POST',
      headers: {
        Authorization: `Basic ${auth}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    })
    if (!resp.ok) {
      const text = await resp.text().catch(() => '<unreadable>')
      console.warn(`[notifications] Twilio ${resp.status} sending to ${toNumber}: ${text.slice(0, 200)}`)
      return { success: false, error: `twilio_http_${resp.status}` }
    }
    return { success: true }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[notifications] Twilio send failed to ${toNumber}: ${msg}`)
    return { success: false, error: msg }
  }
}

// ── Subscriber lookup ──────────────────────────────────────────────────

async function loadSubscribers(kind: 'open' | 'close'): Promise<Subscriber[]> {
  const col = kind === 'open' ? 'notify_open' : 'notify_close'
  try {
    const rows = await dbQuery(
      `SELECT id, phone_number, enabled, notify_open, notify_close, label
       FROM spark_sms_subscribers
       WHERE enabled = TRUE AND ${col} = TRUE`,
    )
    return rows.map((r) => ({
      id: Number(r.id),
      phone_number: String(r.phone_number),
      enabled: Boolean(r.enabled),
      notify_open: Boolean(r.notify_open),
      notify_close: Boolean(r.notify_close),
      label: r.label ?? null,
    }))
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    if (/relation .* does not exist/i.test(msg)) return []
    console.warn(`[notifications] loadSubscribers error: ${msg}`)
    return []
  }
}

// ── Message formatters ─────────────────────────────────────────────────

function formatCtShort(isoTs: string): string {
  try {
    return new Date(isoTs).toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
    })
  } catch {
    return isoTs.slice(0, 16)
  }
}

function fmtDollar(v: number, decimals = 2): string {
  if (!Number.isFinite(v)) return '—'
  const s = Math.abs(v).toFixed(decimals)
  return v < 0 ? `-$${s}` : `$${s}`
}

function fmtSignedDollar(v: number): string {
  if (!Number.isFinite(v)) return '—'
  if (v > 0) return `+$${v.toFixed(2)}`
  if (v < 0) return `-$${Math.abs(v).toFixed(2)}`
  return '$0.00'
}

export function formatOpenMessage(ctx: TradeOpenContext): string {
  const maxProfit = Math.round(ctx.total_credit * 100 * ctx.contracts)
  return [
    `SPARK OPEN · ${formatCtShort(ctx.open_time_iso)} CT`,
    `${ctx.put_long}/${ctx.put_short}P-${ctx.call_short}/${ctx.call_long}C × ${ctx.contracts}`,
    `Credit ${fmtDollar(ctx.total_credit, 2)}/contract · max profit $${maxProfit}`,
    `Collateral ${fmtDollar(ctx.collateral, 0)}`,
    ctx.spy_at_entry != null ? `SPY ${fmtDollar(ctx.spy_at_entry)}` : '',
    ctx.vix_at_entry != null ? `VIX ${ctx.vix_at_entry.toFixed(2)}` : '',
    `${ctx.person ?? '?'} ${ctx.account_type}`,
  ].filter(Boolean).join(' · ')
}

export function formatCloseMessage(ctx: TradeCloseContext): string {
  const pct = ctx.total_credit > 0
    ? Math.round((ctx.realized_pnl / (ctx.total_credit * 100 * ctx.contracts)) * 100)
    : null
  const pctStr = pct != null ? ` (${pct >= 0 ? '+' : ''}${pct}% of credit)` : ''
  const holdStr = ctx.hold_minutes != null
    ? (ctx.hold_minutes >= 60
        ? `${Math.floor(ctx.hold_minutes / 60)}h ${ctx.hold_minutes % 60}m`
        : `${ctx.hold_minutes}m`)
    : ''
  return [
    `SPARK CLOSE · ${new Date().toLocaleString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })} CT`,
    `${fmtSignedDollar(ctx.realized_pnl)}${pctStr}`,
    `Exit: ${ctx.close_reason}`,
    `Close ${fmtDollar(ctx.close_price, 4)} vs entry ${fmtDollar(ctx.total_credit, 4)}`,
    holdStr ? `Hold ${holdStr}` : '',
    `${ctx.person ?? '?'} ${ctx.account_type}`,
  ].filter(Boolean).join(' · ')
}

// ── Public orchestrators ───────────────────────────────────────────────

/** Fire notifications for every enabled open-subscriber. Never throws. */
export async function notifyTradeOpen(ctx: TradeOpenContext): Promise<void> {
  try {
    const subs = await loadSubscribers('open')
    if (subs.length === 0) return
    const body = formatOpenMessage(ctx)
    await Promise.allSettled(subs.map((s) => sendSms(s.phone_number, body)))
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[notifications] notifyTradeOpen swallowed: ${msg}`)
  }
}

/** Fire notifications for every enabled close-subscriber. Never throws. */
export async function notifyTradeClose(ctx: TradeCloseContext): Promise<void> {
  try {
    const subs = await loadSubscribers('close')
    if (subs.length === 0) return
    const body = formatCloseMessage(ctx)
    await Promise.allSettled(subs.map((s) => sendSms(s.phone_number, body)))
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[notifications] notifyTradeClose swallowed: ${msg}`)
  }
}

/** Test hook — for POST /api/spark/notify/test. */
export async function sendTestSms(phoneNumber: string): Promise<{ success: boolean; error?: string }> {
  return sendSms(
    phoneNumber,
    `SPARK notifications test · ${new Date().toLocaleString('en-US', { timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit' })} CT · If you got this, texts are working.`,
  )
}

// ── Polling orchestrator — single hook replaces N scanner call-sites ──

/**
 * Sweep SPARK positions that opened or closed in the last lookback window
 * and fire pending SMS notifications for any that haven't already been
 * notified. Idempotent via `spark_sms_notifications_sent (position_id,
 * event_type)` unique key — re-running within the same cycle is a no-op.
 *
 * Called once per scanner cycle after all bots have finished. Scope
 * confined to SPARK by filtering on dte_mode='1DTE'.
 *
 * Never throws — any DB or Twilio failure is logged and swallowed so a
 * notification hiccup cannot block the trading loop.
 */
export async function sweepPendingSparkNotifications(): Promise<void> {
  try {
    const subsOpen = await loadSubscribers('open')
    const subsClose = await loadSubscribers('close')
    // Skip the DB scan entirely when there are no active subscribers.
    // (Still mark rows so they don't accumulate a backlog if a subscriber
    // is added later — they should only get forward-looking alerts.)
    const needAny = subsOpen.length > 0 || subsClose.length > 0

    // Open events: positions that opened in the last 2 hours (forward-
    // looking buffer for late scanner cycles) and have no open-event row.
    const openRows = await dbQuery(
      `SELECT p.position_id, p.person, p.account_type, p.ticker, p.expiration,
              p.put_long_strike, p.put_short_strike,
              p.call_short_strike, p.call_long_strike,
              p.contracts, p.total_credit,
              p.underlying_at_entry, p.vix_at_entry,
              p.collateral_required, p.open_time
       FROM spark_positions p
       LEFT JOIN spark_sms_notifications_sent s
         ON s.position_id = p.position_id AND s.event_type = 'open'
       WHERE p.open_time >= NOW() - INTERVAL '2 hours'
         AND p.dte_mode = '1DTE'
         AND s.position_id IS NULL`,
    ).catch((err) => {
      console.warn(`[notifications] open sweep query failed: ${String(err)}`)
      return [] as Array<Record<string, unknown>>
    })

    for (const r of openRows) {
      const ctx: TradeOpenContext = {
        position_id: String(r.position_id),
        person: (r.person as string | null) ?? null,
        account_type: (r.account_type as 'sandbox' | 'production') ?? 'sandbox',
        ticker: (r.ticker as string | null) ?? 'SPY',
        expiration: r.expiration instanceof Date
          ? r.expiration.toISOString().slice(0, 10)
          : String(r.expiration).slice(0, 10),
        put_long: Number(r.put_long_strike),
        put_short: Number(r.put_short_strike),
        call_short: Number(r.call_short_strike),
        call_long: Number(r.call_long_strike),
        contracts: Number(r.contracts),
        total_credit: Number(r.total_credit),
        spy_at_entry: r.underlying_at_entry != null ? Number(r.underlying_at_entry) : null,
        vix_at_entry: r.vix_at_entry != null ? Number(r.vix_at_entry) : null,
        collateral: Number(r.collateral_required ?? 0),
        open_time_iso: r.open_time instanceof Date
          ? r.open_time.toISOString()
          : String(r.open_time),
      }

      if (needAny && subsOpen.length > 0) {
        try { await notifyTradeOpen(ctx) } catch { /* already swallowed */ }
      }
      // Always mark so we don't re-query this row forever
      try {
        await dbQuery(
          `INSERT INTO spark_sms_notifications_sent (position_id, event_type, subscriber_count)
           VALUES ($1, 'open', $2)
           ON CONFLICT (position_id, event_type) DO NOTHING`,
          [ctx.position_id, subsOpen.length],
        )
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        console.warn(`[notifications] open mark failed ${ctx.position_id}: ${msg}`)
      }
    }

    // Close events: positions closed in the last 2 hours, no close-event row.
    const closeRows = await dbQuery(
      `SELECT p.position_id, p.person, p.account_type,
              p.close_reason, p.close_price, p.realized_pnl,
              p.total_credit, p.contracts,
              p.open_time, p.close_time
       FROM spark_positions p
       LEFT JOIN spark_sms_notifications_sent s
         ON s.position_id = p.position_id AND s.event_type = 'close'
       WHERE p.close_time >= NOW() - INTERVAL '2 hours'
         AND p.status IN ('closed', 'expired')
         AND p.realized_pnl IS NOT NULL
         AND p.dte_mode = '1DTE'
         AND s.position_id IS NULL`,
    ).catch((err) => {
      console.warn(`[notifications] close sweep query failed: ${String(err)}`)
      return [] as Array<Record<string, unknown>>
    })

    for (const r of closeRows) {
      const openTime = r.open_time instanceof Date ? r.open_time : new Date(String(r.open_time))
      const closeTime = r.close_time instanceof Date ? r.close_time : new Date(String(r.close_time))
      const holdMs = closeTime.getTime() - openTime.getTime()
      const holdMin = Number.isFinite(holdMs) && holdMs > 0
        ? Math.round(holdMs / 60000)
        : null
      const ctx: TradeCloseContext = {
        position_id: String(r.position_id),
        person: (r.person as string | null) ?? null,
        account_type: (r.account_type as 'sandbox' | 'production') ?? 'sandbox',
        close_reason: (r.close_reason as string) ?? 'unknown',
        close_price: Number(r.close_price ?? 0),
        realized_pnl: Number(r.realized_pnl ?? 0),
        total_credit: Number(r.total_credit ?? 0),
        contracts: Number(r.contracts ?? 0),
        hold_minutes: holdMin,
      }

      if (needAny && subsClose.length > 0) {
        try { await notifyTradeClose(ctx) } catch { /* already swallowed */ }
      }
      try {
        await dbQuery(
          `INSERT INTO spark_sms_notifications_sent (position_id, event_type, subscriber_count)
           VALUES ($1, 'close', $2)
           ON CONFLICT (position_id, event_type) DO NOTHING`,
          [ctx.position_id, subsClose.length],
        )
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        console.warn(`[notifications] close mark failed ${ctx.position_id}: ${msg}`)
      }
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[notifications] sweep swallowed: ${msg}`)
  }
}
