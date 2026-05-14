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
import { dispatch, evaluateFlipCross, evaluateWallBreak, evaluateWallFade, FlipBuffer } from './setups'
import { DEFAULT_BLAZE_CONFIG, Direction, GexSnapshot, SetupType } from './types'

// Module-level rolling buffer; persists across scanner ticks while process is alive.
const FLIP_BUFFER = new FlipBuffer(DEFAULT_BLAZE_CONFIG.flip_buffer_minutes)

// Tracks consecutive quote-fetch failures per position (cleared on success).
const _streakByPos: Record<number, number> = {}

// Signal-reset re-entry gate: blocks re-opening the same (setup,direction)
// until BOTH (a) the trigger has been observed FALSE on a later tick, and
// (b) a 15-min cooldown has elapsed. Without this gate the bot re-enters
// identical trades a second after a close because evaluateWallFade is a
// state check ("call_wall within 0.30 sigma overhead") that persists for
// hours when SPY pins near a wall — there's no "fresh trigger" requirement.
const RE_ENTRY_MIN_COOLDOWN_MS = 15 * 60_000
const _closedAtByKey: Map<string, number> = new Map()
const _triggerOffSeenByKey: Map<string, boolean> = new Map()

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

export async function runMonitorCycle(): Promise<void> {
  const positions = await getOpenBlazePositions()
  if (!positions.length) return
  const ct = ctNow()

  for (const pos of positions) {
    // Use mid prices (matches the dashboard's value_to_close_last/mid display)
    // instead of `long_bid - short_ask` (worst-case bid/ask). The bid-ask gap
    // on a near-ATM 1DTE option is $0.05-$0.10, so the worst-case
    // calc was systematically below the displayed P&L — the bot kept
    // "missing" PT exits because its internal calc said 18% while the
    // dashboard read 29%. Mid-mid aligns trigger and display.
    let longMid: number | null = null
    let shortMid: number | null = null
    try {
      const [longQ, shortQ] = await Promise.all([
        getOptionQuote(pos.long_symbol),
        getOptionQuote(pos.short_symbol),
      ])
      if (longQ && shortQ) {
        longMid = (longQ.bid + longQ.ask) / 2
        shortMid = (shortQ.bid + shortQ.ask) / 2
      }
    } catch {
      // fall through to streak handling
    }
    if (longMid == null || shortMid == null) {
      _streakByPos[pos.id] = (_streakByPos[pos.id] || 0) + 1
      continue
    }
    _streakByPos[pos.id] = 0

    const markToClose = longMid - shortMid
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
    // Arm signal-reset gate for this (setup,direction) so the entry cycle
    // can't immediately re-enter the same trade.
    const gateKey = `${pos.setup_type}_${pos.direction}`
    _closedAtByKey.set(gateKey, Date.now())
    _triggerOffSeenByKey.set(gateKey, false)
    await insertSignalActivity({
      outcome: 'TRADE',
      detail: `close ${pos.setup_type} ${pos.direction} ${decision.reason} pnl=${realized_pnl.toFixed(2)}`,
    })
  }
}

/**
 * Mark the gate's "trigger has been observed FALSE since the last close"
 * flag for each armed (setup,direction). Called every entry tick before
 * dispatch — checks whether the just-closed setup-direction's trigger is
 * STILL firing on the current snap. If not, the gate can release once the
 * 15-min cooldown elapses.
 */
function refreshTriggerOffSeen(snap: GexSnapshot, config: typeof DEFAULT_BLAZE_CONFIG): void {
  if (_triggerOffSeenByKey.size === 0) return
  _triggerOffSeenByKey.forEach((alreadyOff, key) => {
    if (alreadyOff) return
    const [setup, direction] = key.split('_') as [SetupType, Direction]
    let stillFiring = false
    if (setup === 'wall_fade') {
      const a = evaluateWallFade(snap, config)
      stillFiring = a !== null && a.direction === direction
    } else if (setup === 'wall_break') {
      const a = evaluateWallBreak(snap, config)
      stillFiring = a !== null && a.direction === direction
    } else if (setup === 'flip_cross') {
      const a = evaluateFlipCross(snap, FLIP_BUFFER, config)
      stillFiring = a !== null && a.direction === direction
    }
    if (!stillFiring) _triggerOffSeenByKey.set(key, true)
  })
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
  // Refresh the signal-reset gate BEFORE dispatch so that even if dispatch
  // would have picked the same setup-direction we just closed, we'll have
  // already noted whether the trigger went off between then and now.
  refreshTriggerOffSeen(snap, DEFAULT_BLAZE_CONFIG)
  const state = await loadDailyState()
  const action = dispatch(snap, state, FLIP_BUFFER, DEFAULT_BLAZE_CONFIG)
  if (!action) {
    await insertSignalActivity({
      outcome: 'NO_TRADE',
      detail: `regime=${snap.regime} spot=${snap.spot.toFixed(2)} cw=${snap.call_wall} pw=${snap.put_wall}`,
    })
    return
  }

  // Signal-reset gate: block re-entering the same (setup,direction) until
  // the trigger has been observed FALSE since last close AND the 15-min
  // cooldown has elapsed. Prevents the "close PT then re-open identical
  // trade in the same scan tick" pattern that drove 5/13's back-to-back
  // SL losses on wall_fade puts (-$560, -$574).
  const gateKey = `${action.setup}_${action.direction}`
  const closedAt = _closedAtByKey.get(gateKey)
  if (closedAt !== undefined) {
    const elapsedMs = Date.now() - closedAt
    const triggerReset = _triggerOffSeenByKey.get(gateKey) === true
    if (elapsedMs < RE_ENTRY_MIN_COOLDOWN_MS || !triggerReset) {
      const elapsedMin = Math.floor(elapsedMs / 60_000)
      await insertSignalActivity({
        outcome: 'SKIP',
        detail: `signal_unchanged_since_${gateKey} elapsed=${elapsedMin}min reset=${triggerReset}`,
      })
      return
    }
    // Gate cleared — release it so we don't re-evaluate on every future tick.
    _closedAtByKey.delete(gateKey)
    _triggerOffSeenByKey.delete(gateKey)
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
