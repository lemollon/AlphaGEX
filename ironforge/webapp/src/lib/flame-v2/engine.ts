/**
 * FLAME v2 / SPARK v2 — the integration surface scanner.ts calls. Wires
 * math.ts (pure) + theta-proxy.ts (live data) + signal-store.ts (Postgres
 * history) into one decision per sleeve per scan tick, and is itself the
 * ONLY place that mode-branches (shadow vs live vs off) — see flags.ts.
 *
 * SAFETY INVARIANT (do not weaken this): every exported function here is
 * wrapped so it can NEVER throw into the caller. A bug in any of this new
 * code must degrade to "could not compute, logged, no behavior change" —
 * never to an unhandled rejection that could take down the scan tick that
 * also runs FLAME/SPARK's real order placement in the same process.
 */
import {
  calmMeasure, isCalmFromHistory, isLongg, igexFormulaNet,
  trainDepth2Tree, predictDepth2Tree, D2Features, D2TrainRow,
  pickTrailingWinner, RulePnls, s1Admits,
  callSpreadStrikes, callSpreadTier, callSpreadContracts, callGuardShouldClose,
} from './math'
import { fetchVixMinuteWindow, fetchLiveGexChain } from './theta-proxy'
import { priorCalmMeasures, priorBandEligibleRows, recordDailySignal, BotKey } from './signal-store'
import {
  flameRegimeBrainMode, flameCallSpreadMode, sparkTrailingBandMode, sparkSignalFilterMode,
  isEnabled, isLive,
} from './flags'

const ENTRY_HHMMSS: Record<BotKey, string> = { flame: '14:05:00', spark: '11:05:00' }
const ENTRY_MOD: Record<BotKey, number> = { flame: 845, spark: 665 }

export type SignalSnapshot = {
  calm: { available: boolean; isCalm: boolean; measure: number | null; threshold: number | null; reason: string | null }
  longg: { available: boolean; isLongg: boolean; igexNet: number | null; reason: string | null }
}

/** Computes CALM + LONGG for one bot on one date. Never throws — any failure
 *  surfaces as `available:false` with a `reason`, which is exactly "missing
 *  input" per the build spec (unchanged behavior upstream). */
export async function computeSignalSnapshot(bot: BotKey, dateStr: string): Promise<SignalSnapshot> {
  const out: SignalSnapshot = {
    calm: { available: false, isCalm: false, measure: null, threshold: null, reason: null },
    longg: { available: false, isLongg: false, igexNet: null, reason: null },
  }
  try {
    const vixRes = await fetchVixMinuteWindow(dateStr, ENTRY_HHMMSS[bot])
    if (!vixRes.ok) {
      out.calm.reason = vixRes.reason
    } else {
      const measure = calmMeasure(vixRes.data)
      if (measure === null) {
        out.calm.reason = 'calm_measure_unavailable'
      } else {
        const priors = await priorCalmMeasures(bot, dateStr)
        const { isCalm, threshold } = isCalmFromHistory(measure, priors)
        if (priors.length < 20) {
          out.calm = { available: false, isCalm: false, measure, threshold: null, reason: `calm_insufficient_history(have=${priors.length} need=20)` }
        } else {
          out.calm = { available: true, isCalm, measure, threshold, reason: null }
        }
      }
    }
  } catch (e) {
    out.calm.reason = `calm_exception(${e instanceof Error ? e.message.slice(0, 80) : 'error'})`
  }

  try {
    const chainRes = await fetchLiveGexChain('SPY', 60)
    if (!chainRes.ok) {
      out.longg.reason = chainRes.reason
    } else {
      const net = igexFormulaNet(chainRes.data.spot, chainRes.data.rows, ENTRY_MOD[bot])
      out.longg = { available: true, isLongg: isLongg(net), igexNet: net, reason: null }
    }
  } catch (e) {
    out.longg.reason = `longg_exception(${e instanceof Error ? e.message.slice(0, 80) : 'error'})`
  }

  return finishSnapshot(bot, dateStr, out)
}

async function finishSnapshot(bot: BotKey, dateStr: string, snap: SignalSnapshot): Promise<SignalSnapshot> {
  try {
    await recordDailySignal(bot, dateStr, {
      calmMeasure: snap.calm.measure, isCalm: snap.calm.available ? snap.calm.isCalm : null,
      igexNet: snap.longg.igexNet, isLongg: snap.longg.available ? snap.longg.isLongg : null,
    })
  } catch { /* best-effort history write; never blocks the decision */ }
  return snap
}

// ---------------------------------------------------------------------------
// FLAME D2 regime brain — relaxed (0.80, 0.925] VIX band admission.
// SHADOW: compute what D2 would decide and log it alongside today's actual
// "prior-SPY-up" admission decision; change nothing. LIVE: return D2's
// decision for the caller to use AS the admission rule instead.
// ---------------------------------------------------------------------------

export type RegimeBrainDecision = {
  available: boolean
  rule: 0 | 1 | null // 0=R0 (today's prior-SPY-up), 1=R1 (BEST admits)
  admits: boolean | null // null = fall back to today's existing rule
  reason: string
}

/**
 * `features` must be built from already-lagged data only (yesterday's close
 * or earlier) — see scanner.ts call site for how FLAME's existing
 * VIX/SPY-history helpers already guarantee that. `todaysPriorSpyUpRule` is
 * today's STATIC admission result (what the code already computes) so a
 * missing/unfit model always falls back to it byte-for-byte.
 */
export async function flameRegimeBrainDecision(
  dateStr: string, features: D2Features | null, todaysPriorSpyUpRule: boolean,
): Promise<RegimeBrainDecision> {
  const mode = flameRegimeBrainMode()
  if (!isEnabled(mode)) return { available: false, rule: null, admits: null, reason: 'off' }
  if (!features || !Object.values(features).every((v) => Number.isFinite(v))) {
    return { available: false, rule: null, admits: todaysPriorSpyUpRule, reason: 'features_unavailable_fallback_R0' }
  }
  try {
    const priorRows = await priorBandEligibleRows('flame', dateStr)
    const trainRows: D2TrainRow[] = priorRows
      .filter((r) => [r.vixLevel, r.vix1yPct, r.vix20dChg, r.tsRatioL, r.ret20, r.ret60, r.above50dma].every((v) => v !== null))
      .map((r) => ({
        features: {
          vixLevel: r.vixLevel as number, vix1yPct: r.vix1yPct as number, vix20dChg: r.vix20dChg as number,
          tsRatioL: r.tsRatioL as number, ret20: r.ret20 as number, ret60: r.ret60 as number, above50dma: r.above50dma as number,
        },
        label: r.r1Pnl > r.r0Pnl ? 1 : 0,
      }))
    const tree = trainDepth2Tree(trainRows, 40)
    if (!tree) {
      return { available: false, rule: 0, admits: todaysPriorSpyUpRule, reason: `insufficient_training_rows(${trainRows.length}<40)_fallback_R0` }
    }
    const rule = predictDepth2Tree(tree, features)
    // 🚨 2026-10-10 fix: this used to be `rule === 1`, which treats a
    // predicted R0 as an unconditional SKIP. That's wrong per this very
    // function's own rule comment above ("0=R0 (today's prior-SPY-up)")
    // and per the frozen research script's run_d2 (`row["R1_pnl"] if
    // pred==1 else row["R0_pnl"]`, where R0_pnl is itself conditional on
    // prior_up, not always zero). "Predicted R0" means "defer to today's
    // actual prior-SPY-up rule", which can be admit OR skip depending on
    // todaysPriorSpyUpRule -- only "predicted R1" is an unconditional
    // admit. Was latent and inert: the tree never trained (0 rows) until
    // today's seed fix, so this never changed a live decision before now.
    const admits = rule === 1 ? true : todaysPriorSpyUpRule
    const log = `[flame-v2] FLAME regime_brain(${mode}) date=${dateStr} rule=R${rule} admits=${admits} ` +
      `vs_today_prior_spy_up_rule=${todaysPriorSpyUpRule} trained_on=${trainRows.length}_rows`
    console.log(log)
    if (isLive(mode)) return { available: true, rule, admits, reason: 'ok_live' }
    return { available: true, rule, admits: todaysPriorSpyUpRule, reason: 'ok_shadow_no_behavior_change' }
  } catch (e) {
    return { available: false, rule: null, admits: todaysPriorSpyUpRule, reason: `exception(${e instanceof Error ? e.message.slice(0, 80) : 'error'})` }
  }
}

// ---------------------------------------------------------------------------
// SPARK D1 trailing-60-winner — relaxed (0.90, 0.975] VIX band (SPARK has NO
// relaxed band today at all; shadow mode only ever LOGS what D1 would admit,
// it never opens a position SPARK's live code path doesn't already support).
// ---------------------------------------------------------------------------

export type TrailingBandDecision = { available: boolean; rule: 0 | 1 | 2 | 3 | null; admits: boolean; reason: string }

export async function sparkTrailingBandDecision(dateStr: string): Promise<TrailingBandDecision> {
  const mode = sparkTrailingBandMode()
  if (!isEnabled(mode)) return { available: false, rule: null, admits: false, reason: 'off' }
  try {
    const priorRows = await priorBandEligibleRows('spark', dateStr)
    const windowed = priorRows.slice(-60).map((r): RulePnls => [r.r0Pnl, r.r1Pnl, r.r2Pnl, r.r3Pnl])
    const rule = pickTrailingWinner(windowed, 20)
    const admits = rule !== 3 // R3 = skip
    console.log(`[flame-v2] SPARK trailing_band(${mode}) date=${dateStr} rule=R${rule} admits=${admits} window=${windowed.length}_days`)
    // LIVE is intentionally a no-op on admission today: SPARK's relaxed band
    // does not exist in the live order-placement path yet (see PR description
    // "What remains" — flipping this to live requires adding the admission
    // branch to tryOpenFlamePutSpread's SPARK leg, which this PR does not do).
    return { available: true, rule, admits: isLive(mode) ? admits : false, reason: isLive(mode) ? 'ok_live_decision_only_no_order_path_yet' : 'ok_shadow' }
  } catch (e) {
    return { available: false, rule: null, admits: false, reason: `exception(${e instanceof Error ? e.message.slice(0, 80) : 'error'})` }
  }
}

// ---------------------------------------------------------------------------
// SPARK S1 signal-days filter (CALM or LONGG) over SPARK's EXISTING core-gate
// (<=0.90) admissions.
// ---------------------------------------------------------------------------

export type S1Decision = { available: boolean; wouldSkip: boolean; reason: string }

export async function sparkS1Decision(dateStr: string): Promise<S1Decision> {
  const mode = sparkSignalFilterMode()
  if (!isEnabled(mode)) return { available: false, wouldSkip: false, reason: 'off' }
  const snap = await computeSignalSnapshot('spark', dateStr)
  if (!snap.calm.available || !snap.longg.available) {
    return { available: false, wouldSkip: false, reason: `signals_unavailable(calm=${snap.calm.reason ?? 'ok'} longg=${snap.longg.reason ?? 'ok'})` }
  }
  const admits = s1Admits(snap.calm.isCalm, snap.longg.isLongg)
  console.log(`[flame-v2] SPARK s1_filter(${mode}) date=${dateStr} calm=${snap.calm.isCalm} longg=${snap.longg.isLongg} would_skip=${!admits}`)
  return { available: true, wouldSkip: !admits, reason: isLive(mode) ? 'ok_live' : 'ok_shadow' }
}

// ---------------------------------------------------------------------------
// FLAME 14:05 ET SPY 0DTE CALL credit spread.
// ---------------------------------------------------------------------------

export type CallSpreadDecision = {
  available: boolean
  tier: 0 | 1 | 3
  contracts: number
  shortStrike: number | null
  longStrike: number | null
  reason: string
}

export async function flameCallSpreadDecision(
  dateStr: string, spot: number, flameBaseContracts: number,
): Promise<CallSpreadDecision> {
  const mode = flameCallSpreadMode()
  if (!isEnabled(mode)) return { available: false, tier: 0, contracts: 0, shortStrike: null, longStrike: null, reason: 'off' }
  const snap = await computeSignalSnapshot('flame', dateStr)
  if (!snap.calm.available || !snap.longg.available) {
    return {
      available: false, tier: 0, contracts: 0, shortStrike: null, longStrike: null,
      reason: `signals_unavailable(calm=${snap.calm.reason ?? 'ok'} longg=${snap.longg.reason ?? 'ok'})`,
    }
  }
  const tier = callSpreadTier(snap.calm.isCalm, snap.longg.isLongg)
  const contracts = callSpreadContracts(snap.calm.isCalm, snap.longg.isLongg, flameBaseContracts)
  const { short, long } = callSpreadStrikes(spot)
  console.log(
    `[flame-v2] FLAME call_spread(${mode}) date=${dateStr} calm=${snap.calm.isCalm} longg=${snap.longg.isLongg} ` +
    `tier=${tier} contracts=${contracts} short=${short} long=${long} spot=${spot.toFixed(2)}`,
  )
  // Order placement itself (paper/sandbox ledger always, real order when
  // canPlaceLiveOrders('flame') is also true) lives in
  // flame-v2/call-spread-live.ts, which calls this function for the decision
  // and then executes it — this function stays pure/decision-only.
  return { available: true, tier, contracts, shortStrike: short, longStrike: long, reason: isLive(mode) ? 'ok_live' : 'ok_shadow' }
}

// ---------------------------------------------------------------------------
// Go-forward D1/D2 training recorder. Keeps flame_v2_signal_history's
// band_eligible/r0-r3_pnl columns fresh from live trading days (the seed
// loaded by ensureBandSeedLoaded only covers history through the research
// cutoff) WITHOUT ever fabricating a number.
//
// R0_pnl/R1_pnl's own definitions (band_eligible_table in the frozen
// signal_on_flame_spark.py) mean most of a band-eligible day's outcome is
// derivable with ZERO new data:
//   - R0_pnl = pnl_if_enter if prior_spy_up else 0   -- exactly 0 when
//     prior_spy_up is false, no trade or quote needed to know that.
//   - R1_pnl = pnl_if_enter if best(calm|longg) else 0 -- exactly 0 when
//     best is false, same reasoning.
//   - R2_pnl = pnl_if_enter if (prior_spy_up AND best) else 0.
//   - R3_pnl = 0 always (R3 = skip, by definition never trades).
// `pnl_if_enter` itself is only needed — and only knowable — when the live
// bot actually opened the SPY book's trade that day, in which case it's the
// real realized_pnl, read back after settlement. The one case this can
// NEVER resolve without a shadow quote during the entry window (not built):
// prior_spy_up=false AND best=true, where neither rule's condition for 0
// applies but no real trade exists to read a pnl from. That day is recorded
// as `skip:unobservable_pnl_no_shadow_quote` -- NOTHING is written for it,
// rather than guessing, so trainDepth2Tree's finite-feature filter and
// pickTrailingWinner's pnl sums never see a fabricated number.
// ---------------------------------------------------------------------------

export type BandOutcomeInput = {
  bot: BotKey
  dateStr: string
  ratio: number
  priorSpyUp: boolean
  /** The SPY book's real realized_pnl for this date if the live bot actually
   *  opened a trade that day, else null (admission denied / no trade). */
  realizedPnl: number | null
  /** FLAME only -- D2's 7 features for this date; omit/null for SPARK. */
  features?: D2Features | null
}

export async function recordBandOutcome(input: BandOutcomeInput): Promise<string> {
  const { bot, dateStr, ratio, priorSpyUp, realizedPnl } = input
  try {
    const snap = await computeSignalSnapshot(bot, dateStr)
    if (!snap.calm.available || !snap.longg.available) {
      return `skip:signals_unavailable(calm=${snap.calm.reason ?? 'ok'} longg=${snap.longg.reason ?? 'ok'})`
    }
    const best = snap.calm.isCalm || snap.longg.isLongg

    let r0Pnl: number
    let r1Pnl: number
    let r2Pnl: number
    const r3Pnl = 0
    if (realizedPnl !== null) {
      r0Pnl = priorSpyUp ? realizedPnl : 0
      r1Pnl = best ? realizedPnl : 0
      r2Pnl = priorSpyUp && best ? realizedPnl : 0
    } else if (!priorSpyUp && !best) {
      r0Pnl = 0
      r1Pnl = 0
      r2Pnl = 0
    } else {
      return 'skip:unobservable_pnl_no_shadow_quote'
    }

    const f = input.features ?? null
    await recordDailySignal(bot, dateStr, {
      bandEligible: true, ratio, priorSpyUp, r0Pnl, r1Pnl, r2Pnl, r3Pnl,
      vixLevel: f?.vixLevel ?? null, vix1yPct: f?.vix1yPct ?? null, vix20dChg: f?.vix20dChg ?? null,
      tsRatioL: f?.tsRatioL ?? null, ret20: f?.ret20 ?? null, ret60: f?.ret60 ?? null, above50dma: f?.above50dma ?? null,
    })
    return `recorded(r0=${r0Pnl.toFixed(2)} r1=${r1Pnl.toFixed(2)} best=${best} prior_up=${priorSpyUp})`
  } catch (e) {
    return `error(${e instanceof Error ? e.message.slice(0, 80) : 'error'})`
  }
}

/** Mirrored assignment guard for an (eventually) live call leg: close if spot
 *  has risen within `buffer` of the short strike. Exposed standalone so a
 *  future live order-placement patch can call it without re-deriving the
 *  sign convention. */
export function flameCallGuardShouldClose(spot: number, shortStrike: number, buffer: number): boolean {
  return callGuardShouldClose(spot, shortStrike, buffer)
}
