/**
 * BLAZE — scan cycle. Called once per IronForge scanner tick (60s).
 * Mirrors trading/helios/trader.HeliosTrader.run_cycle + monitor cycle.
 */
import { query } from '../db'
import { getOptionQuote } from '../tradier'
import { closeBlazePosition, getOpenBlazePositions, insertSignalActivity, loadDailyState, bumpDailyState } from './db'
import { decideExit } from './exit'
import { openVertical } from './executor'
import { fetchGexSnapshot, GexStaleError } from './gex-client'
import { dispatch, FlipBuffer } from './setups'
import { DEFAULT_BLAZE_CONFIG } from './types'

// Module-level rolling buffer; persists across scanner ticks while process is alive.
const FLIP_BUFFER = new FlipBuffer(DEFAULT_BLAZE_CONFIG.flip_buffer_minutes)

// Tracks consecutive quote-fetch failures per position (cleared on success).
const _streakByPos: Record<number, number> = {}

function ctNow(): Date {
  const s = new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' })
  return new Date(s)
}

function isMarketHours(ct: Date): boolean {
  const dow = ct.getDay()
  if (dow === 0 || dow === 6) return false
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  return hhmm >= 830 && hhmm <= 1555
}

function minutesSinceOpen(ct: Date): number {
  const open = new Date(ct.getFullYear(), ct.getMonth(), ct.getDate(), 8, 30, 0)
  return Math.max(0, Math.floor((ct.getTime() - open.getTime()) / 60_000))
}

async function isBlazeEnabled(): Promise<boolean> {
  try {
    const res = await query<{ pdt_enabled: boolean }>(
      `SELECT pdt_enabled FROM blaze_pdt_config WHERE bot_name = 'BLAZE' LIMIT 1`,
    )
    // We're reusing pdt_enabled as the master kill switch since blaze_config doesn't exist yet.
    // Default-off until operator flips it on.
    if (!res.length) return false
    return Boolean(res[0].pdt_enabled)
  } catch {
    return false
  }
}

async function runMonitorCycle(): Promise<void> {
  const positions = await getOpenBlazePositions()
  if (!positions.length) return
  const ct = ctNow()

  for (const pos of positions) {
    let longBid: number | null = null
    let shortAsk: number | null = null
    try {
      const [longQ, shortQ] = await Promise.all([
        getOptionQuote(pos.long_symbol),
        getOptionQuote(pos.short_symbol),
      ])
      if (longQ && shortQ) {
        longBid = longQ.bid
        shortAsk = shortQ.ask
      }
    } catch {
      // fall through to streak handling
    }
    if (longBid == null || shortAsk == null) {
      _streakByPos[pos.id] = (_streakByPos[pos.id] || 0) + 1
      continue
    }
    _streakByPos[pos.id] = 0

    const markToClose = longBid - shortAsk
    const decision = decideExit({
      debit: pos.debit,
      mark_to_close: markToClose,
      now_ct: ct,
      quotes_unavail_streak: _streakByPos[pos.id] || 0,
      config: DEFAULT_BLAZE_CONFIG,
    })
    if (!decision.should_exit || !decision.reason) continue

    const realized_pnl = (markToClose - pos.debit) * 100 * pos.contracts
    await closeBlazePosition(pos.id, {
      mark_to_close: markToClose,
      exit_reason: decision.reason,
      realized_pnl,
    })
    delete _streakByPos[pos.id]
    await insertSignalActivity({
      outcome: 'TRADE',
      detail: `close ${pos.setup_type} ${pos.direction} ${decision.reason} pnl=${realized_pnl.toFixed(2)}`,
    })
  }
}

async function runEntryCycle(): Promise<void> {
  // Don't open if a position is already open (one-at-a-time, matches JOSHUA).
  const open = await getOpenBlazePositions()
  if (open.length > 0) {
    await insertSignalActivity({ outcome: 'SKIP', detail: 'position_already_open' })
    return
  }

  let snap
  try {
    snap = await fetchGexSnapshot('SPY', DEFAULT_BLAZE_CONFIG.gex_stale_max_seconds)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    if (err instanceof GexStaleError) {
      await insertSignalActivity({ outcome: 'SKIP', detail: `gex_stale:${msg}` })
    } else {
      await insertSignalActivity({ outcome: 'ERROR', detail: `gex_fetch:${msg}` })
    }
    return
  }

  FLIP_BUFFER.add(snap)
  const state = await loadDailyState()
  const action = dispatch(snap, state, FLIP_BUFFER, DEFAULT_BLAZE_CONFIG)
  if (!action) {
    await insertSignalActivity({
      outcome: 'NO_TRADE',
      detail: `regime=${snap.regime} spot=${snap.spot.toFixed(2)} cw=${snap.call_wall} pw=${snap.put_wall}`,
    })
    return
  }

  try {
    const result = await openVertical(action, snap, DEFAULT_BLAZE_CONFIG)
    if (!result) {
      await insertSignalActivity({ outcome: 'SKIP', detail: `open_paper:invalid_${action.setup}` })
      return
    }
    await bumpDailyState(action.setup, minutesSinceOpen(ctNow()))
    await insertSignalActivity({
      outcome: 'TRADE',
      detail: `open ${action.setup} ${action.direction} ${result.contracts}x@$${result.debit.toFixed(2)}`,
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    await insertSignalActivity({ outcome: 'ERROR', detail: `open:${msg.substring(0, 200)}` })
  }
}

/**
 * Lazy DDL — runs once at first scan. Creates the gex-history table
 * (Phase 2) if it doesn't exist. Mirrors the auto-create-tables-on-first-use
 * pattern from common-mistakes.md so a fresh deploy doesn't 500 on missing
 * tables.
 */
let _gexHistoryEnsured = false
async function ensureGexHistoryTable(): Promise<void> {
  if (_gexHistoryEnsured) return
  try {
    await query(
      `CREATE TABLE IF NOT EXISTS blaze_gex_history (
         id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
         snapshot_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
         spot_price NUMERIC(10, 2),
         vix NUMERIC(6, 2),
         net_gex NUMERIC(18, 2),
         call_wall NUMERIC(10, 2),
         put_wall NUMERIC(10, 2),
         flip_point NUMERIC(10, 2),
         regime TEXT,
         sigma_1d_band NUMERIC(10, 4)
       )`,
    )
    await query(
      `CREATE INDEX IF NOT EXISTS idx_blaze_gex_history_time
         ON blaze_gex_history (snapshot_time DESC)`,
    )
    _gexHistoryEnsured = true
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] BLAZE gex_history table ensure failed: ${msg}`)
  }
}

/**
 * Write a row to blaze_gex_history so the DirectionalChart can draw
 * time-varying wall/flip overlays. Fetches a fresh snapshot reusing the
 * same gex-client the entry cycle uses (no extra TV/alphagex calls — the
 * entry cycle already fetched one earlier this minute, but the scanner
 * runs every minute regardless of entry-window state, and the snapshot
 * captures the after-hours / outside-window state too).
 *
 * Tolerates stale GEX (passes a generous 600s staleness gate) since this
 * is for visualization, not trade entry. Skips silently on fetch failure.
 */
async function writeGexHistory(): Promise<void> {
  await ensureGexHistoryTable()
  if (!_gexHistoryEnsured) return
  try {
    const snap = await fetchGexSnapshot('SPY', 600)
    await query(
      `INSERT INTO blaze_gex_history
        (spot_price, vix, net_gex, call_wall, put_wall, flip_point, regime, sigma_1d_band)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [
        snap.spot,
        snap.vix,
        snap.net_gex,
        snap.call_wall,
        snap.put_wall,
        snap.flip_point,
        snap.regime,
        snap.sigma_1d_band_width,
      ],
    )
  } catch (err) {
    // Stale or fetch failure is fine — we just skip this cycle's history row.
    // Bot trading is unaffected (entry cycle has its own staleness gate).
    if (err instanceof GexStaleError) return
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] BLAZE gex_history write skipped: ${msg}`)
  }
}

/**
 * Compute live unrealized P&L for open BLAZE positions and write an equity
 * snapshot so the dashboard chart has data. Runs every scan cycle.
 *
 * Mirrors the IC scanner's snapshot pattern (scanner.ts:3454) but with
 * vertical-spread MTM math (long_bid - short_ask, capped to spread width).
 */
async function writeEquitySnapshot(): Promise<void> {
  try {
    const acctRows = await query<{ current_balance: number | string; cumulative_pnl: number | string }>(
      `SELECT current_balance, cumulative_pnl FROM blaze_paper_account
       WHERE is_active = TRUE LIMIT 1`,
    )
    if (!acctRows.length) return
    const balance = Number(acctRows[0].current_balance) || 0
    const realizedPnl = Number(acctRows[0].cumulative_pnl) || 0

    const open = await getOpenBlazePositions()
    let unrealizedPnl = 0
    for (const pos of open) {
      try {
        const [longQ, shortQ] = await Promise.all([
          getOptionQuote(pos.long_symbol),
          getOptionQuote(pos.short_symbol),
        ])
        if (!longQ || !shortQ) continue
        const spreadWidth = Math.abs(pos.short_strike - pos.long_strike)
        const closeValue = Math.min(Math.max(0, longQ.bid - shortQ.ask), spreadWidth)
        unrealizedPnl += (closeValue - pos.debit) * 100 * pos.contracts
      } catch { /* skip leg on quote failure */ }
    }

    await query(
      `INSERT INTO blaze_equity_snapshots
        (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode, account_type)
       VALUES ($1, $2, $3, $4, 'scan', '1DTE', 'sandbox')`,
      [balance, realizedPnl, Math.round(unrealizedPnl * 100) / 100, open.length],
    )
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] BLAZE snapshot write failed: ${msg}`)
  }
}

/** Main scan entry. Called once per IronForge tick from scanner.ts.runAllScans. */
export async function scanBlaze(_ct?: Date): Promise<void> {
  const ct = _ct || ctNow()

  // Always monitor open positions first (matches FLAME/SPARK pattern + lets TIME_STOP fire after-hours)
  try {
    await runMonitorCycle()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] BLAZE monitor error: ${msg}`)
  }

  // Write equity snapshot every cycle (mirrors FLAME/SPARK/INFERNO; required for dashboard chart).
  // Outside market hours, snapshot still records balance + realized P&L so the curve doesn't gap.
  await writeEquitySnapshot()

  // Phase 2: capture GEX snapshot so DirectionalChart can render time-varying
  // wall/flip overlays. Independent of equity snapshot — runs every cycle
  // regardless of market hours so we have a continuous history for chart playback.
  await writeGexHistory()

  if (!isMarketHours(ct)) return
  if (!(await isBlazeEnabled())) return  // operator-gated kill switch

  try {
    await runEntryCycle()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] BLAZE entry error: ${msg}`)
    await insertSignalActivity({ outcome: 'ERROR', detail: `cycle:${msg.substring(0, 200)}` })
  }

  // Heartbeat
  try {
    await query(
      `INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
       VALUES ('BLAZE', NOW(), 'active', 1, $1)
       ON CONFLICT (bot_name) DO UPDATE SET
         last_heartbeat = NOW(), status = 'active',
         scan_count = bot_heartbeats.scan_count + 1,
         details = EXCLUDED.details`,
      [JSON.stringify({ buffer_size: FLIP_BUFFER['snaps']?.length ?? 0 })],
    )
  } catch { /* non-fatal */ }
}
