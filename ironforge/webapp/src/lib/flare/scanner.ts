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
import { getOptionQuote, getQuote, getDailyHistory } from '../tradier'
import { computeImbalance, decideHedge, sigMove, HEDGE_FLOOR, HEDGE_MIN_TOPUP } from './hedge'
import { closeFlarePosition, countTodaySetups, getOpenFlarePositions, getPaperBalance, getSpotMinutesAgo, insertSignalActivity, isDirectionInCooldown, setDirectionHalted, loadDailyState, bumpDailyState } from './db'
import { decideExit } from './exit'
import { openVertical, openPutCredit, openQuickItmCall, openImbalanceHedge } from './executor'
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

// FLARE 1DTE two-regime state (in-process; resets on restart — worst case a
// mid-day restart could allow a second same-day entry, acceptable on paper).
let _lastTradeDate: string | null = null
// Separate once/day guard for the additive quick-ITM morning sleeve (independent
// of _lastTradeDate so it does NOT block — or get blocked by — the 2:45 two-regime entry).
let _lastQuickItmDate: string | null = null

// Per-day cache of SPY daily closes (for the conviction SMA20/SMA50 signal), so
// the entry tick window (14:45-14:55) doesn't re-hit Tradier history every tick.
let _dailyClosesCache: { date: string; closes: number[] } = { date: '', closes: [] }

/**
 * Conviction trend signal for the negative-GEX leg (THE durable directional
 * FLARE, /tmp/conviction.py). Compares today's spot to SMA20 & SMA50 of the
 * prior daily closes. Returns a tradeable direction ONLY when the two SMAs AGREE
 * (aligned = clean trend, not whipsaw); direction follows SMA50. `null` => no
 * conviction (skip). Validated $5-wide 1DTE held-to-expiry on neg-GEX days:
 * +$19.9/trade, 6/6 yrs green, two-sided (long & short both win), passes
 * concentration. The neg-GEX gate is applied by the caller.
 */
async function convictionSignal(
  spot: number,
  ctDate: string,
): Promise<{ dir: 'call' | 'put'; sma20: number; sma50: number } | null> {
  if (_dailyClosesCache.date !== ctDate) {
    const hist = await getDailyHistory('SPY', 100)
    // Drop today's in-progress bar so the SMA window is the PRIOR closes (matches
    // the backtest's sma(d,n) = mean of the n closes strictly before day d).
    const closes = hist.filter((h) => h.date < ctDate).map((h) => h.close)
    _dailyClosesCache = { date: ctDate, closes }
  }
  const closes = _dailyClosesCache.closes
  if (closes.length < 50) return null
  const mean = (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length
  const sma20 = mean(closes.slice(-20))
  const sma50 = mean(closes.slice(-50))
  const aligned = (spot > sma20) === (spot > sma50)
  if (!aligned) return null
  return { dir: spot > sma50 ? 'call' : 'put', sma20, sma50 }
}

function ctNow(): Date {
  const s = new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' })
  return new Date(s)
}

function isMarketHours(ct: Date): boolean {
  // Entry window only — monitor runs unconditionally before this gate.
  // FLARE is now 1DTE neg-GEX momentum: it enters NEAR THE CLOSE (the actual
  // entry happens >=14:45 in runEntryCycle) and the contracts expire the NEXT
  // day, so the old "never open a 0DTE in the last hour" cutoff doesn't apply —
  // 1DTE options are liquid near today's close. Allow the window up to 14:55.
  const dow = ct.getDay()
  if (dow === 0 || dow === 6) return false
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  return hhmm >= 830 && hhmm <= 1455
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
    // QUICK-ITM sleeve (single 0DTE long call, setup_type 'gex_quick_itm'): no short
    // leg. Sell SAME-DAY at the configured exit time (default 1:00 PM CT); EOD 14:45
    // is a hard fallback so it never rides to settlement. Handled before the generic
    // 2-leg path so the empty short_symbol is never quoted.
    if (pos.setup_type === 'gex_quick_itm') {
      let callQ
      try { callQ = await getOptionQuote(pos.long_symbol) } catch { callQ = null }
      if (!callQ) { _streakByPos[pos.id] = (_streakByPos[pos.id] || 0) + 1; continue }
      _streakByPos[pos.id] = 0
      const hhmm = ct.getHours() * 100 + ct.getMinutes()
      const sellBid = callQ.bid                                   // sell at bid (worst-case)
      const pnl = (sellBid - pos.debit) * 100 * pos.contracts
      if (hhmm >= DEFAULT_FLARE_CONFIG.quick_itm_exit_hhmm || hhmm >= 1445) {
        const reason = hhmm >= 1445 && hhmm < DEFAULT_FLARE_CONFIG.quick_itm_exit_hhmm ? 'TIME_STOP' : 'QUICK_EXIT'
        await closeFlarePosition(pos.id, { mark_to_close: sellBid, exit_reason: reason, realized_pnl: pnl })
        delete _streakByPos[pos.id]
        await insertSignalActivity({ outcome: 'TRADE', detail: `close gex_quick_itm call ${reason} pnl=${pnl.toFixed(2)}` })
      }
      continue   // never enters the 2-leg path or the force-close pool
    }

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
    const ctDate = `${ct.getFullYear()}-${String(ct.getMonth() + 1).padStart(2, '0')}-${String(ct.getDate()).padStart(2, '0')}`
    const hhmm = ct.getHours() * 100 + ct.getMinutes()
    const pnl = (markToClose - pos.debit) * 100 * pos.contracts

    // Both FLARE legs are 1DTE HELD TO EXPIRY — no intraday PT/SL. The conviction
    // directional debit (gex_momentum) and the bullish put credit (gex_putcredit)
    // each pay/collect their spread once at entry and settle at intrinsic. Close
    // only on/after the expiration date near the close (>=14:45 CT). The
    // (mark - debit) P&L works for both debit (debit>0) and credit (debit<0)
    // spreads because markToClose = longMid - shortMid is signed consistently.
    const atExpiry = ctDate >= pos.expiration && hhmm >= 1445
    if (atExpiry) {
      await closeFlarePosition(pos.id, { mark_to_close: markToClose, exit_reason: 'EXPIRY', realized_pnl: pnl })
      delete _streakByPos[pos.id]
      await insertSignalActivity({
        outcome: 'TRADE',
        detail: `close ${pos.setup_type} ${pos.direction} EXPIRY pnl=${pnl.toFixed(2)}`,
      })
      continue
    }

    survivors.push({ pos, markToClose, unrealized: pnl })
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

  // Net-imbalance hedge DISABLED for the 1DTE neg-GEX momentum strategy. It was
  // the old 0DTE bot's risk mechanism (it opens 0DTE opposing spreads); the new
  // strategy holds ONE defined-risk 1DTE directional spread to expiry, so a hedge
  // is both unnecessary (max loss = the debit) and wrong-dated. Left here, inert.
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

  // FLARE = 1DTE TWO-REGIME, validated $5-wide / held-to-expiry. Once a day near
  // the close, read net GEX and pick the regime's leg:
  //   • net GEX < 0  (trend / dealers short gamma) -> CONVICTION DIRECTIONAL DEBIT:
  //       trade the trend direction (spot vs SMA50) only when SMA20 & SMA50 AGREE.
  //   • net GEX >= 0 (pin / dealers long gamma)    -> BULLISH PUT CREDIT spread:
  //       the grind-up thesis; profits if SPY rises or holds.
  // Both enter near the close and are held to next-day expiry (pay the spread once).
  const ct = ctNow()
  const ctDate = `${ct.getFullYear()}-${String(ct.getMonth() + 1).padStart(2, '0')}-${String(ct.getDate()).padStart(2, '0')}`
  const hhmm = ct.getHours() * 100 + ct.getMinutes()

  // ===== ADDITIVE QUICK-ITM MORNING SLEEVE =====
  // Independent of the two-regime entry below. On a positive-GEX day, in the morning
  // window, buy a 0DTE ITM call (monitor sells it same-day ~1 PM CT). Runs ALONGSIDE
  // the 2:45 put-credit — on a pos-GEX day FLARE does both. Its own once/day guard.
  const cfg = DEFAULT_FLARE_CONFIG
  if (
    cfg.quick_itm_enabled &&
    _lastQuickItmDate !== ctDate &&
    snap.net_gex >= 0 &&
    hhmm >= cfg.quick_itm_entry_start &&
    hhmm <= cfg.quick_itm_entry_end &&
    // DB-backed idempotency: if a quick-ITM was already opened today (possibly by
    // another instance / pre-restart), don't open a second. Sync the in-process guard.
    (await countTodaySetups(['gex_quick_itm'])) === 0
  ) {
    try {
      const res = await openQuickItmCall(snap, cfg)
      if (res) {
        _lastQuickItmDate = ctDate
        await insertSignalActivity({ outcome: 'TRADE', detail: `open gex_quick_itm call x${res.contracts}@$${res.debit.toFixed(2)} net_gex=${snap.net_gex.toExponential(2)}` })
      } else {
        await insertSignalActivity({ outcome: 'SKIP', detail: 'quick_itm:no_quote' })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      await insertSignalActivity({ outcome: 'ERROR', detail: `quick_itm:${msg.substring(0, 160)}` })
    }
    // fall through: the two-regime entry below is gated to >=14:45, so it no-ops now.
  }

  if (_lastTradeDate === ctDate) {
    await insertSignalActivity({ outcome: 'NO_TRADE', detail: 'already_traded_today' })
    return
  }
  // Enter near the close (14:45-14:55), matching the backtests' EOD entry.
  if (hhmm < 1445) return

  // DB-backed idempotency for the once/day afternoon entry: survives restarts and
  // Render zero-downtime deploy-overlap (two instances each with a fresh in-process
  // _lastTradeDate). If a put-credit OR conviction was already opened today, stop.
  if ((await countTodaySetups(['gex_putcredit', 'gex_momentum'])) > 0) {
    _lastTradeDate = ctDate
    await insertSignalActivity({ outcome: 'NO_TRADE', detail: 'already_traded_today_db' })
    return
  }

  // ===== GEX REGIME SWITCH =====
  // Positive-GEX (pin/grind) day -> BULLISH PUT CREDIT leg (held to expiry).
  if (snap.net_gex >= 0) {
    try {
      const res = await openPutCredit(snap, DEFAULT_FLARE_CONFIG)
      if (res) {
        _lastTradeDate = ctDate
        await insertSignalActivity({
          outcome: 'TRADE',
          detail: `open gex_putcredit ${res.contracts}x@$${res.debit.toFixed(2)} exp1DTE net_gex=${snap.net_gex.toExponential(2)}`,
        })
      } else {
        await insertSignalActivity({ outcome: 'SKIP', detail: 'putcredit:no_credit_or_quote' })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      await insertSignalActivity({ outcome: 'ERROR', detail: `putcredit:${msg.substring(0, 160)}` })
    }
    return
  }

  // Negative-GEX (trend) day -> CONVICTION DIRECTIONAL DEBIT leg. Require SMA20 &
  // SMA50 agreement; trade the trend direction, $5-wide, hold to expiry.
  const conv = await convictionSignal(snap.spot, ctDate)
  if (!conv) {
    await insertSignalActivity({
      outcome: 'NO_TRADE',
      detail: `neg_gex ${snap.net_gex.toExponential(2)} no_conviction (SMA20/50 not aligned or insufficient history)`,
    })
    return
  }
  const dir = conv.dir
  const L = Math.round(snap.spot)
  const w = DEFAULT_FLARE_CONFIG.spread_width
  const action = {
    setup: 'gex_momentum' as const,
    direction: dir,
    long_strike: L,
    short_strike: dir === 'call' ? L + w : L - w,
    reason: `neg_gex ${snap.net_gex.toExponential(2)} trend ${dir} sma20=${conv.sma20.toFixed(2)} sma50=${conv.sma50.toFixed(2)}`,
  }

  // (Re-entry gate below is inert for gex_momentum: the monitor no longer arms
  // _closedAtByKey for it, so it always passes. Kept for the legacy wall setups.)

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
    _lastTradeDate = ctDate   // one trade per day
    await insertSignalActivity({
      outcome: 'TRADE',
      detail: `open ${action.setup} ${action.direction} ${result.contracts}x@$${result.debit.toFixed(2)} exp1DTE`,
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
        // Quick-ITM sleeve is a single long call (no short leg): mark at its bid.
        if (pos.setup_type === 'gex_quick_itm') {
          const cq = await getOptionQuote(pos.long_symbol)
          if (!cq) continue
          unrealizedPnl += (cq.bid - pos.debit) * 100 * pos.contracts
          continue
        }
        const [longQ, shortQ] = await Promise.all([
          getOptionQuote(pos.long_symbol),
          getOptionQuote(pos.short_symbol),
        ])
        if (!longQ || !shortQ) continue
        const spreadWidth = Math.abs(pos.short_strike - pos.long_strike)
        // Value to close = longBid - shortAsk, signed: a debit spread closes in
        // [0, width]; a CREDIT spread (put-credit leg) closes in [-width, 0].
        // Clamp to [-width, width] so both legs mark correctly.
        const closeValue = Math.min(Math.max(longQ.bid - shortQ.ask, -spreadWidth), spreadWidth)
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
