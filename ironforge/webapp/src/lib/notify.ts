/**
 * Discord webhook notifications for IronForge bots.
 *
 * Webhook URL is read per-bot from `DISCORD_WEBHOOK_{BOT}` env vars
 * (uppercased — e.g. DISCORD_WEBHOOK_FLAME). If the env var is unset for a
 * given bot, posts are skipped silently — the bot continues trading
 * regardless of notification health.
 *
 * Failures (network, 4xx, 5xx) are logged to stdout and swallowed. Discord
 * outages must NEVER block scan cycles or trade execution.
 *
 * Activity polling: `notifyNewActivityForBot` is called at the end of each
 * scan cycle. It diffs against in-memory cursors of the highest position id
 * seen for opens and closes, posts an embed for any newer rows, then
 * advances the cursors. On scanner restart the cursors reset to 0 and the
 * NEXT call seeds them from the current max ids without posting — preventing
 * a notification flood for historical trades.
 */

import { query } from './db'

/* ------------------------------------------------------------------ */
/*  Embed colors                                                        */
/* ------------------------------------------------------------------ */

const COLOR_OPEN = 3910908      // green — new position
const COLOR_WIN = 59526         // dark green/teal — profitable close
const COLOR_LOSS = 16725060     // red — losing close
const COLOR_NEUTRAL = 9807270   // grey — non-PT close (EOD, stale, etc.)

/* ------------------------------------------------------------------ */
/*  Activity cursors (per-bot)                                          */
/* ------------------------------------------------------------------ */

interface BotCursors {
  lastOpenId: number     // highest `id` seen with status='open'
  lastClosedId: number   // highest `id` seen with status IN ('closed', 'expired')
  seeded: boolean        // first call seeds from current max without posting
}

const _cursors: Record<string, BotCursors> = {
  flame: { lastOpenId: 0, lastClosedId: 0, seeded: false },
  spark: { lastOpenId: 0, lastClosedId: 0, seeded: false },
  inferno: { lastOpenId: 0, lastClosedId: 0, seeded: false },
}

/* ------------------------------------------------------------------ */
/*  Generic Discord poster                                              */
/* ------------------------------------------------------------------ */

export async function postDiscord(botName: string, payload: object): Promise<void> {
  const url = process.env[`DISCORD_WEBHOOK_${botName.toUpperCase()}`]
  if (!url) return  // no webhook configured — skip silently
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'IronForge/1.0',
      },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const txt = await res.text().catch(() => '')
      console.warn(`[notify] ${botName.toUpperCase()}: Discord HTTP ${res.status}: ${txt.slice(0, 200)}`)
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[notify] ${botName.toUpperCase()}: Discord post failed: ${msg}`)
  }
}

/* ------------------------------------------------------------------ */
/*  Embed formatters                                                    */
/* ------------------------------------------------------------------ */

function fmtMoney(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '$0.00'
  const sign = n < 0 ? '-' : ''
  const abs = Math.abs(n)
  return `${sign}$${abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPrice(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '$0.0000'
  return `$${n.toFixed(4)}`
}

function fmtExp(exp: any): string {
  if (!exp) return ''
  const s = exp.toISOString?.()?.slice(0, 10) ?? String(exp).slice(0, 10)
  return s
}

interface OpenRow {
  position_id: string
  ticker: string
  expiration: any
  put_short_strike: number | null
  put_long_strike: number | null
  call_short_strike: number | null
  call_long_strike: number | null
  contracts: number
  total_credit: number
  max_profit: number | null
  max_loss: number | null
  collateral_required: number | null
  underlying_at_entry: number | null
  vix_at_entry: number | null
  person: string | null
  account_type: string | null
}

interface CloseRow extends OpenRow {
  close_time: any
  close_price: number | null
  realized_pnl: number | null
  close_reason: string | null
}

function strategyLabel(row: OpenRow): string {
  const isPutSpread = !row.call_short_strike || Number(row.call_short_strike) === 0
  if (isPutSpread) {
    return `${row.ticker} ${row.put_long_strike}/${row.put_short_strike} Put Credit Spread`
  }
  return `${row.ticker} ${row.put_long_strike}P-${row.put_short_strike}P / ${row.call_short_strike}C-${row.call_long_strike}C IC`
}

function buildOpenEmbed(botName: string, row: OpenRow): object {
  const acctTag = (row.account_type === 'production' ? 'PROD' : 'PAPER') +
    (row.person ? ` · ${row.person}` : '')
  const isPutSpread = !row.call_short_strike || Number(row.call_short_strike) === 0
  const fields: any[] = [
    { name: 'Strikes', value: isPutSpread
      ? `${row.put_long_strike}P / ${row.put_short_strike}P (long / short)`
      : `${row.put_long_strike}/${row.put_short_strike}P · ${row.call_short_strike}/${row.call_long_strike}C`,
      inline: true },
    { name: 'Contracts', value: String(row.contracts), inline: true },
    { name: 'Expiration', value: fmtExp(row.expiration), inline: true },
    { name: 'Credit', value: `${fmtPrice(Number(row.total_credit))} per spread`, inline: true },
    { name: 'Max Profit', value: fmtMoney(Number(row.max_profit)), inline: true },
    { name: 'Collateral', value: fmtMoney(Number(row.collateral_required)), inline: true },
  ]
  if (row.underlying_at_entry != null) {
    fields.push({ name: row.ticker, value: `$${Number(row.underlying_at_entry).toFixed(2)}`, inline: true })
  }
  if (row.vix_at_entry != null) {
    fields.push({ name: 'VIX', value: Number(row.vix_at_entry).toFixed(2), inline: true })
  }
  fields.push({ name: 'Account', value: acctTag, inline: true })

  return {
    embeds: [{
      title: `${botName.toUpperCase()} · OPEN · ${strategyLabel(row)}`,
      color: COLOR_OPEN,
      fields,
      footer: { text: `IronForge · ${botName.toUpperCase()} · ${row.position_id}` },
      timestamp: new Date().toISOString(),
    }],
  }
}

function closeColorFor(row: CloseRow): { color: number; tag: string } {
  const reason = row.close_reason || 'unknown'
  const pnl = Number(row.realized_pnl ?? 0)
  if (reason.startsWith('profit_target') || reason === 'trailing_lockin') {
    return { color: pnl >= 0 ? COLOR_WIN : COLOR_NEUTRAL, tag: 'Win recorded. Capital released.' }
  }
  if (reason === 'stop_loss') {
    return { color: COLOR_LOSS, tag: 'Loss taken. Risk contained.' }
  }
  if (reason === 'eod_cutoff' || reason === 'stale_holdover') {
    return { color: pnl > 0 ? COLOR_WIN : pnl < 0 ? COLOR_LOSS : COLOR_NEUTRAL, tag: 'Force-closed at end of day.' }
  }
  if (reason === 'data_feed_failure') {
    return { color: COLOR_LOSS, tag: 'Data feed failed — closed at entry credit.' }
  }
  if (reason.startsWith('broker_')) {
    return { color: COLOR_NEUTRAL, tag: 'Broker reconciliation close.' }
  }
  return { color: pnl > 0 ? COLOR_WIN : pnl < 0 ? COLOR_LOSS : COLOR_NEUTRAL, tag: '' }
}

function buildCloseEmbed(botName: string, row: CloseRow): object {
  const { color, tag } = closeColorFor(row)
  const pnl = Number(row.realized_pnl ?? 0)
  const maxProfit = Number(row.max_profit ?? 0)
  const pctOfMax = maxProfit !== 0 ? ((pnl / maxProfit) * 100) : 0
  const acctTag = (row.account_type === 'production' ? 'PROD' : 'PAPER') +
    (row.person ? ` · ${row.person}` : '')
  const fields: any[] = [
    { name: 'Reason', value: row.close_reason || 'unknown', inline: true },
    { name: 'Contracts', value: String(row.contracts), inline: true },
    { name: 'Expiration', value: fmtExp(row.expiration), inline: true },
    { name: 'Entry Credit', value: `${fmtPrice(Number(row.total_credit))} per spread`, inline: true },
    { name: 'Close Price', value: `${fmtPrice(Number(row.close_price ?? 0))} per spread`, inline: true },
    { name: 'Account', value: acctTag, inline: true },
    {
      name: 'Realized P&L',
      value: maxProfit !== 0
        ? `${pnl >= 0 ? '+' : ''}${fmtMoney(pnl)} (${pctOfMax >= 0 ? '+' : ''}${pctOfMax.toFixed(1)}% of max)`
        : `${pnl >= 0 ? '+' : ''}${fmtMoney(pnl)}`,
      inline: false,
    },
  ]

  return {
    embeds: [{
      title: `${botName.toUpperCase()} · CLOSE · ${strategyLabel(row)}`,
      color,
      fields,
      footer: { text: `IronForge · ${botName.toUpperCase()} · ${row.position_id}${tag ? ` · ${tag}` : ''}` },
      timestamp: new Date().toISOString(),
    }],
  }
}

/* ------------------------------------------------------------------ */
/*  Activity poller — call at end of each scan cycle                    */
/* ------------------------------------------------------------------ */

export async function notifyNewActivityForBot(botName: string, dte: string): Promise<void> {
  const url = process.env[`DISCORD_WEBHOOK_${botName.toUpperCase()}`]
  if (!url) return  // no webhook — skip the DB query entirely

  const cursor = _cursors[botName]
  if (cursor == null) return

  const posTable = `${botName}_positions`

  try {
    if (!cursor.seeded) {
      // First call after process start: seed cursors from current max ids
      // without posting. Prevents a flood of historical-position notifications.
      const seedRows = await query(
        `SELECT
           COALESCE(MAX(CASE WHEN status = 'open' THEN id END), 0) AS max_open_id,
           COALESCE(MAX(CASE WHEN status IN ('closed','expired') THEN id END), 0) AS max_closed_id
         FROM ${posTable}
         WHERE dte_mode = $1`,
        [dte],
      )
      const r = seedRows[0] ?? {}
      cursor.lastOpenId = Number(r.max_open_id ?? 0)
      cursor.lastClosedId = Number(r.max_closed_id ?? 0)
      cursor.seeded = true
      return
    }

    // Newly-opened positions
    const openRows = await query(
      `SELECT id, position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, max_profit, max_loss,
              collateral_required, underlying_at_entry, vix_at_entry,
              person, COALESCE(account_type, 'sandbox') AS account_type
       FROM ${posTable}
       WHERE dte_mode = $1 AND status = 'open' AND id > $2
       ORDER BY id ASC
       LIMIT 20`,
      [dte, cursor.lastOpenId],
    )
    for (const row of openRows) {
      await postDiscord(botName, buildOpenEmbed(botName, row as OpenRow))
      cursor.lastOpenId = Math.max(cursor.lastOpenId, Number(row.id))
    }

    // Newly-closed positions
    const closeRows = await query(
      `SELECT id, position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, max_profit, max_loss,
              collateral_required, underlying_at_entry, vix_at_entry,
              close_time, close_price, realized_pnl, close_reason,
              person, COALESCE(account_type, 'sandbox') AS account_type
       FROM ${posTable}
       WHERE dte_mode = $1 AND status IN ('closed','expired') AND id > $2
       ORDER BY id ASC
       LIMIT 20`,
      [dte, cursor.lastClosedId],
    )
    for (const row of closeRows) {
      await postDiscord(botName, buildCloseEmbed(botName, row as CloseRow))
      cursor.lastClosedId = Math.max(cursor.lastClosedId, Number(row.id))
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[notify] ${botName.toUpperCase()}: activity poll failed: ${msg}`)
  }
}

/** @internal — exported for testing only */
export const _notifyTesting = {
  _cursors,
  buildOpenEmbed,
  buildCloseEmbed,
  closeColorFor,
}
