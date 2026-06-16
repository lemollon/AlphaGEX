/**
 * FLARE — scan cycle. Called once per IronForge scanner tick (60s).
 * Cloned from blaze/scanner.ts; differences:
 *   - imports from ./db, ./executor, ./exit, ./setups, ./gex-client, ./types (FLARE versions)
 *   - uses DEFAULT_FLARE_CONFIG (SL=100%)
 *   - references flare_* tables
 *   - kill-switch reads flare_pdt_config WHERE bot_name = 'FLARE'
 *   - exports scanFlare (renamed from scanBlaze)
 *   - bot_name strings are 'FLARE'/'flare'
 */
import { query } from '../db'
import { getOptionQuote, getQuote } from '../tradier'
import { computeImbalance, decideHedge, sigMove, HEDGE_FLOOR } from './hedge'
import { closeFlarePosition, getOpenFlarePositions, getPaperBalance, getSpotMinutesAgo, insertSignalActivity, isDirectionInCooldown, setDirectionHalted, loadDailyState, bumpDailyState } from './db'
import { decideExit } from './exit'
import { openVertical, openImbalanceHedge } from './executor'
import { fetchGexSnapshot, GexStaleError } from './gex-client'
import { dispatch, evaluateFlipCross, evaluateWallBreak, evaluateWallFade, FlipBuffer } from './setups'
import { DEFAULT_FLARE_CONFIG, Direction, GexSnapshot, SetupType } from './types'

// Module-level rolling buffer; persists across scanner ticks while process is alive.
const FLIP_BUFFER = new FlipBuffer(DEFAULT_FLARE_CONFIG.flip_buffer_minutes)

// Tracks consecutive quote-fetch failures per position (cleared on success).
const _streakByPos: Record<number, number> = {}

// Signal-reset re-entry gate: blocks re-opening the same (setup,direction)
// until BOTH (a) the trigger has been observed FALSE on a later tick, and
// (b) a 15-min cooldown has elapsed.
const RE_ENTRY_MIN_COOLDOWN_MS = 15 * 60_000
const _closedAtByKey: Map<string, number> = new Map()
const _triggerOffSeenByKey: Map<string, boolean> = new Map()

function ctNow(): Date {
  const s = new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' })
  return new Date(s)
}

function isMarketHours(ct: Date): boolean {
  // Entry window only — monitor runs unconditionally before this gate.
  // Hard cutoff at 14:00 CT (operator rule): never open a 0DTE inside the last
  // hour, when liquidity collapses and Tradier stops quoting expiring contracts
  // cleanly. Any leftover position gets TIME_STOP'd at eod_time_ct=14:45.
  const dow = ct.getDay()
  if (dow === 0 || dow === 6) return false
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  return hhmm >= 830 && hhmm <= 1400
}

function minutesSinceOpen(ct: Date): number {
  const open = new Date(ct.getFullYear(), ct.getMonth(), ct.getDate(), 8, 30, 0)
  return Math.max(0, Math.floor((ct.getTime() - open.getTime()) / 60_000))
}

async function isFlareEnabled(): Promise<boolean> {
  try {
    const res = await query<{ pdt_enabled: boolean }>(
      `SELECT pdt_enabled FROM flare_pdt_config WHERE bot_name = 'FLARE' LIMIT 1`,
    )
    // Reusing pdt_enabled as the master kill switch. Default-off until operator flips it on.
    if (!res.length) return false
    return Boolean(res[0].pdt_enabled)
  } catch {
    return false
  }
}

/** Arm the (setup,direction) signal-reset gate after any close. */
function armResetGate(setup: string, direction: string): void {
  const gateKey = `${setup}_${direction}`
  _closedAtByKey.set(gateKey, Date.now())
  _triggerOffSeenByKey.set(gateKey, false)
}

export async function runMonitorCycle(): Promise<void> {
  const positions = await getOpenFlarePositions()
  if (!positions.length) return
  const ct = ctNow()
  const balance = await getPaperBalance()

  // Positions that survive this tick's individual PT/SL/TIME_STOP exits, with
  // their live MTM — fed into the per-direction force-close stop below.
  const survivors: { pos: (typeof positions)[number]; markToClose: number; unrealized: number }[] = []

  for (const pos of positions) {
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
      config: DEFAULT_FLARE_CONFIG,
    })
    if (decision.should_exit && decision.reason) {
      const realized_pnl = (markToClose - pos.debit) * 100 * pos.contracts
      await closeFlarePosition(pos.id, {
        mark_to_close: markToClose,
        exit_reason: decision.reason,
        realized_pnl,
      })
      delete _streakByPos[pos.id]
      armResetGate(pos.setup_type, pos.direction)
      await insertSignalActivity({
        outcome: 'TRADE',
        detail: `close ${pos.setup_type} ${pos.direction} ${decision.reason} pnl=${realized_pnl.toFixed(2)}`,
      })
      continue
    }

    survivors.push({ pos, markToClose, unrealized: (markToClose - pos.debit) * 100 * pos.contracts })
  }

  // Per-direction force-close stop. If one side's aggregate UNREALIZED P&L is
  // below -perdir_force_close_pct * balance, guillotine that whole side and put
  // it on a perdir_cooldown_minutes cooldown (it resumes after — NOT a day-halt;
  // the operator wants all-day trading). The force-close is the lever that
  // converts FLARE from ruin (-$30k/PF 0.54) to profitable on its own tape.
  const riskBase = Math.max(balance, 0)
  const threshold = -DEFAULT_FLARE_CONFIG.perdir_force_close_pct * riskBase
  for (const dir of ['call', 'put'] as const) {
    const side = survivors.filter((s) => s.pos.direction === dir)
    if (!side.length) continue
    const sideUnreal = side.reduce((a, s) => a + s.unrealized, 0)
    if (sideUnreal >= threshold) continue
    for (const s of side) {
      await closeFlarePosition(s.pos.id, {
        mark_to_close: s.markToClose,
        exit_reason: 'RISK_FORCE_CLOSE',
        realized_pnl: s.unrealized,
      })
      delete _streakByPos[s.pos.id]
      armResetGate(s.pos.setup_type, dir)
    }
    const reason =
      `aggregate ${dir} unrealized $${sideUnreal.toFixed(0)} < $${threshold.toFixed(0)} ` +
      `(${(DEFAULT_FLARE_CONFIG.perdir_force_close_pct * 100).toFixed(0)}% of $${balance.toFixed(0)})`
    await setDirectionHalted(dir, reason)
    await insertSignalActivity({
      outcome: 'TRADE',
      detail: `RISK_FORCE_CLOSE ${dir} x${side.length} pnl=${sideUnreal.toFixed(2)} cooldown_${DEFAULT_FLARE_CONFIG.perdir_cooldown_minutes}min [${reason}]`,
    })
  }

  // Net-imbalance hedge — the LIVE risk mechanism that replaces the (neutralized)
  // force-close. When the directional book is over-exposed one way beyond the
  // tolerance floor, BUY an opposing debit spread sized to recover the excess on
  // an adverse move. One hedge per side at a time; it closes via the normal
  // PT/SL/14:45 exit path. Best-effort — never blocks the monitor.
  try {
    const im = computeImbalance(
      positions.map((p) => ({ direction: p.direction, debit: p.debit, contracts: p.contracts, setup_type: p.setup_type })),
    )
    if (im.heavyDir !== 'none' && im.netImbalance > HEDGE_FLOOR) {
      const [spyQ, vixQ] = await Promise.all([getQuote('SPY'), getQuote('VIX')])
      const spot = spyQ?.last ?? 0
      const sig = sigMove(spot, vixQ?.last ?? 0)
      const d = decideHedge({ imbalance: im, sigMove: sig })
      const alreadyHedged = positions.some((p) => p.setup_type === 'imbalance_hedge' && p.direction === d.hedgeSide)
      if (d.hedge && d.hedgeSide && spot > 0 && sig > 0 && !alreadyHedged) {
        const res = await openImbalanceHedge(
          { hedgeSide: d.hedgeSide, targetOffset: d.targetOffset, spot, sigMove: sig },
          DEFAULT_FLARE_CONFIG,
        )
        await insertSignalActivity({
          outcome: 'TRADE',
          detail: res
            ? `HEDGE ${d.hedgeSide} x${res.contracts} debit=${res.debit.toFixed(2)} (${im.heavyDir}-heavy $${im.netImbalance}, target $${d.targetOffset}, σ=$${sig})`
            : `HEDGE_SKIP ${d.hedgeSide} (target $${d.targetOffset}) — no chain quote`,
        })
      }
    }
  } catch (e) {
    console.warn(`[flare] imbalance hedge failed (non-fatal): ${e instanceof Error ? e.message : String(e)}`)
  }
}

/**
 * Mark the gate's "trigger has been observed FALSE since the last close"
 * flag for each armed (setup,direction). Called every entry tick before dispatch.
 */
function refreshTriggerOffSeen(snap: GexSnapshot, config: typeof DEFAULT_FLARE_CONFIG): void {
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
  // Parallel entries permitted. Re-entry discipline is enforced by the
  // (setup,direction) signal-reset gate below, not by an open-position count.
  let snap
  try {
    snap = await fetchGexSnapshot('SPY', DEFAULT_FLARE_CONFIG.gex_stale_max_seconds)
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
  refreshTriggerOffSeen(snap, DEFAULT_FLARE_CONFIG)
  const state = await loadDailyState()
  const action = dispatch(snap, state, FLIP_BUFFER, DEFAULT_FLARE_CONFIG)
  if (!action) {
    await insertSignalActivity({
      outcome: 'NO_TRADE',
      detail: `regime=${snap.regime} spot=${snap.spot.toFixed(2)} cw=${snap.call_wall} pw=${snap.put_wall}`,
    })
    return
  }

  // ---- wall-break entry gate (wall_fade only) ----
  // Refuse to FADE a wall that price is sitting at / breaking through. The
  // wall_fade trigger fires whenever price is NEAR the faded wall, and "near"
  // includes "already at/through it" — the exact 6/04 trap (142 put fades as SPY
  // ground up through the call wall, -$40.6k). Two filters (flare_gate_sim.py):
  //   (a) require >= wall_fade_min_room points of ROOM to the faded wall, and
  //   (b) refuse if price is TRENDING INTO that wall over the lookback window.
  // Applied to wall_fade ONLY — wall_break intentionally trades the break, so the
  // same geometry would be backwards for it.
  if (action.setup === 'wall_fade') {
    const cfg = DEFAULT_FLARE_CONFIG
    // Faded wall: a put fade fades the CALL wall (overhead); a call fade fades the
    // PUT wall (below). evaluateWallFade guarantees the relevant wall is > 0 and
    // on the correct side, so room is well-defined and positive when it fires.
    const room = action.direction === 'put'
      ? snap.call_wall - snap.spot
      : snap.spot - snap.put_wall
    if (!(room >= cfg.wall_fade_min_room)) {
      await insertSignalActivity({
        outcome: 'SKIP',
        detail: `wall_break_gate ${action.direction} room=${room.toFixed(2)}<${cfg.wall_fade_min_room} (price at/through faded wall)`,
      })
      return
    }
    // Trend INTO the faded wall over the lookback: a put fade fails on an up-move,
    // a call fade on a down-move. Fail-open (allow) when history is too thin to
    // measure (e.g. the first ~15 min of a session) — the room floor still applies.
    const pastSpot = await getSpotMinutesAgo(cfg.wall_fade_trend_lookback_minutes)
    if (pastSpot != null) {
      const adverse = action.direction === 'put'
        ? snap.spot - pastSpot      // rising pushes up through the call wall
        : pastSpot - snap.spot      // falling pushes down through the put wall
      if (adverse >= cfg.wall_fade_max_adverse_trend) {
        await insertSignalActivity({
          outcome: 'SKIP',
          detail: `wall_break_gate ${action.direction} adverse=${adverse.toFixed(2)}>=${cfg.wall_fade_max_adverse_trend} /${cfg.wall_fade_trend_lookback_minutes}min (trending into faded wall)`,
        })
        return
      }
    }
  }

  // Per-direction cooldown: if this side was force-closed within the last
  // perdir_cooldown_minutes (aggregate unrealized breached the force-close
  // stop), hold off new entries on it until the cooldown elapses — then resume.
  // This replaced the old rest-of-day halt so FLARE keeps trading all day.
  if (await isDirectionInCooldown(action.direction, DEFAULT_FLARE_CONFIG.perdir_cooldown_minutes)) {
    await insertSignalActivity({ outcome: 'SKIP', detail: `dir_cooldown_${action.direction}` })
    return
  }

  // Per-direction concurrency cap: bound simultaneous same-side exposure so a
  // single bad side can't pile up unbounded before the force-close stop trips.
  const openNow = await getOpenFlarePositions()
  const sameDirOpen = openNow.filter((p) => p.direction === action.direction).length
  if (sameDirOpen >= DEFAULT_FLARE_CONFIG.max_concurrent_per_direction) {
    await insertSignalActivity({
      outcome: 'SKIP',
      detail: `max_concurrent_${action.direction}=${sameDirOpen}/${DEFAULT_FLARE_CONFIG.max_concurrent_per_direction}`,
    })
    return
  }

  // Signal-reset gate: block re-entering the same (setup,direction) until
  // the trigger has been observed FALSE since last close AND the 15-min
  // cooldown has elapsed.
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
    const result = await openVertical(action, snap, DEFAULT_FLARE_CONFIG)
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
 * Lazy DDL — runs once at first scan. Creates the flare gex-history table
 * if it doesn't exist.
 */
let _gexHistoryEnsured = false
async function ensureGexHistoryTable(): Promise<void> {
  if (_gexHistoryEnsured) return
  try {
    await query(
      `CREATE TABLE IF NOT EXISTS flare_gex_history (
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
      `CREATE INDEX IF NOT EXISTS idx_flare_gex_history_time
         ON flare_gex_history (snapshot_time DESC)`,
    )
    _gexHistoryEnsured = true
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] FLARE gex_history table ensure failed: ${msg}`)
  }
}

/**
 * Write a row to flare_gex_history so the DirectionalChart can draw
 * time-varying wall/flip overlays. Runs every scan cycle.
 */
async function writeGexHistory(): Promise<void> {
  await ensureGexHistoryTable()
  if (!_gexHistoryEnsured) return
  try {
    const snap = await fetchGexSnapshot('SPY', 600)
    await query(
      `INSERT INTO flare_gex_history
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
    if (err instanceof GexStaleError) return
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] FLARE gex_history write skipped: ${msg}`)
  }
}

/**
 * Compute live unrealized P&L for open FLARE positions and write an equity
 * snapshot so the dashboard chart has data. Runs every scan cycle.
 */
async function writeEquitySnapshot(): Promise<void> {
  try {
    const acctRows = await query<{ current_balance: number | string; cumulative_pnl: number | string }>(
      `SELECT current_balance, cumulative_pnl FROM flare_paper_account
       WHERE is_active = TRUE LIMIT 1`,
    )
    if (!acctRows.length) return
    const balance = Number(acctRows[0].current_balance) || 0
    const realizedPnl = Number(acctRows[0].cumulative_pnl) || 0

    const open = await getOpenFlarePositions()
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
      `INSERT INTO flare_equity_snapshots
        (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode, account_type)
       VALUES ($1, $2, $3, $4, 'scan', '0DTE', 'sandbox')`,
      [balance, realizedPnl, Math.round(unrealizedPnl * 100) / 100, open.length],
    )
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] FLARE snapshot write failed: ${msg}`)
  }
}

/** Main scan entry. Called once per IronForge tick from scanner.ts.runAllScans. */
export async function scanFlare(_ct?: Date): Promise<void> {
  const ct = _ct || ctNow()

  // Always monitor open positions first (matches FLAME/SPARK/BLAZE pattern)
  try {
    await runMonitorCycle()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] FLARE monitor error: ${msg}`)
  }

  // Write equity snapshot every cycle (required for dashboard chart).
  await writeEquitySnapshot()

  // Capture GEX snapshot for DirectionalChart wall/flip overlays.
  await writeGexHistory()

  if (!isMarketHours(ct)) return
  if (!(await isFlareEnabled())) return  // operator-gated kill switch

  try {
    await runEntryCycle()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[scanner] FLARE entry error: ${msg}`)
    await insertSignalActivity({ outcome: 'ERROR', detail: `cycle:${msg.substring(0, 200)}` })
  }

  // Heartbeat
  try {
    await query(
      `INSERT INTO bot_heartbeats (bot_name, last_heartbeat, status, scan_count, details)
       VALUES ('FLARE', NOW(), 'active', 1, $1)
       ON CONFLICT (bot_name) DO UPDATE SET
         last_heartbeat = NOW(), status = 'active',
         scan_count = bot_heartbeats.scan_count + 1,
         details = EXCLUDED.details`,
      [JSON.stringify({ buffer_size: FLIP_BUFFER['snaps']?.length ?? 0 })],
    )
  } catch { /* non-fatal */ }
}
