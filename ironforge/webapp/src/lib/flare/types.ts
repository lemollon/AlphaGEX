/**
 * FLARE — types. Re-exports all shared types from BLAZE, then defines
 * FLARE's own config with a wide stop (SL = 100% of debit).
 *
 * The only config difference vs BLAZE is stop_loss_pct: 100.0
 * (BLAZE uses 30.0). PT stays at 20% (same as DEFAULT_BLAZE_CONFIG).
 * FLARE is 0DTE, so expiration is always the same trading day.
 */
export * from '../blaze/types'
import { DEFAULT_BLAZE_CONFIG, BlazeConfig } from '../blaze/types'

export interface FlareConfig extends BlazeConfig {
  // Per-direction force-close stop. When the aggregate UNREALIZED P&L of one
  // side (all open call OR all open put debit spreads) drops below
  //   -perdir_force_close_pct * current_account_balance,
  // force-close that entire side, then COOL DOWN new entries on it for
  // perdir_cooldown_minutes (NOT the rest of the session — the operator wants
  // FLARE to keep trading all day). Evaluated every scan tick by runMonitorCycle.
  //
  // Why per-side + force-close (not an account-level entry halt): FLARE's blow-ups
  // were always one-directional — it stacked the wrong side into a trend (6/04:
  // 138 put fades, 3 wins, -$52k). A realized-PnL daily stop never fired (loss was
  // unrealized until the 14:45 time-stop guillotine), and an account-level halt
  // still let already-open losers ride. A per-side force-close checked on the
  // timer guillotines the bleeding side fast — whether it bleeds quick (6/04) or
  // slow (6/03) — while a healthy side keeps running.
  // Backtest on FLARE's own 8-day live tape (reset $10k, flat 5%/trade):
  //   baseline   -$30,451  PF 0.54  maxDD 570%
  //   per-dir FC 5% + cap20  +$12,790  PF 3.15  maxDD 33%  worst day -$618
  perdir_force_close_pct: number
  // Minutes a side is blocked from re-entry after a force-close. A short cooldown
  // (the signal-reset gate already spaces same-setup re-entries ~15min, so this
  // is nearly free) so the side keeps trading all day rather than halting.
  perdir_cooldown_minutes: number
  // Post-force-close SIZE-DOWN. After each force-close on a side, that side's
  // next entries are sized by perdir_size_mult_after_fc ^ (force-closes today).
  // A repeatedly-wrong side keeps trading all day but at rapidly shrinking size
  // (1 -> 0.33 -> 0.11 -> 0.037 ...), so a one-way trend day can't run away.
  // Resets each morning (counter is keyed on trade_date). This is the lever that
  // manages risk WITHOUT ever stopping a direction from trading.
  perdir_size_mult_after_fc: number
  // Hard ceiling on simultaneously-open positions per direction. Bounds the
  // intraday swing / blast radius independent of the force-close stop.
  max_concurrent_per_direction: number
  // ---- wall-break entry gate (wall_fade only) ----
  // FLARE's whole loss was one failure mode: it FADED A WALL while price was
  // breaking THROUGH it (6/04: 142 put fades as SPY ground up through the call
  // wall). The wall_fade trigger fires when price is NEAR the faded wall — but
  // "near" includes "right at / already through it", which is exactly the trap.
  // These two filters add a guard band:
  //   * wall_fade_min_room: refuse the fade unless price still has >= this many
  //     points of ROOM to the faded wall (put fade: call_wall - spot; call fade:
  //     spot - put_wall). Fades with <1pt room were 51-54% WR / big losers on the
  //     tape; >=1pt room was 71% WR.
  //   * wall_fade_max_adverse_trend: refuse the fade if price is TRENDING INTO the
  //     faded wall — i.e. moved >= this many points toward it over the last
  //     wall_fade_trend_lookback_minutes (put fade: spot rose; call fade: fell).
  // Backtest on FLARE's own 581-trade / 10-day tape (flare_gate_sim.py, flat
  // $500/trade): room>=1 AND adverse<0.5 took the tape from -$28,473 to +$4,168,
  // 58%->77% WR, worst day -$40,603 -> -$2,043, maxDD 592%->53% (kept the chop-day
  // winners 5/29 + 6/08; killed 141 of 142 fades on the 6/04 trend day). Primary
  // value is TAIL PROTECTION (makes a 6/04 structurally impossible), measured on a
  // 10-day sample so the marginal-edge number is directional, not a sign-off.
  wall_fade_min_room: number
  wall_fade_trend_lookback_minutes: number
  wall_fade_max_adverse_trend: number
  // ---- quick-ITM morning sleeve (ADDITIVE experimental leg) ----
  // A SEPARATE intraday play that runs ALONGSIDE the two-regime legs (does not
  // replace them): on positive-GEX days, buy a 0DTE ITM call in the morning and
  // sell it SAME-DAY in the early afternoon — capturing the pos-GEX grind-up
  // (validated 71% up morning->afternoon; helios 54-day round-trip-bid/ask test:
  // $5-ITM call buy 9:00 CT / sell 1:00 PM CT = +$135/ct, 79% win on 24 days).
  // SMALL/UNVALIDATED: only a 54-day single-regime sample and a NAKED long call,
  // so it ships at quick_itm_contracts=1 behind its own enable flag. Independent
  // of the put-credit leg — on a pos-GEX day FLARE does BOTH (morning call + 2:45
  // put-credit).
  quick_itm_enabled: boolean
  quick_itm_contracts: number   // fixed lot count (naked long call; unvalidated -> start at 1)
  quick_itm_strike_itm: number  // dollars in-the-money for the long call strike (round(spot) - this)
  quick_itm_entry_start: number // CT hhmm entry window open  (e.g. 900)
  quick_itm_entry_end: number   // CT hhmm entry window close (e.g. 930)
  quick_itm_exit_hhmm: number   // CT hhmm to sell same-day  (e.g. 1300 = 1:00 PM CT)
  // ---- per-leg sizing ----
  // The two FLARE legs have very different risk profiles: the bullish put-credit
  // (pos-GEX) wins ~88% and is DURABLE; the conviction directional debit (neg-GEX)
  // wins ~41% and is FRAGILE (losses cluster). Bootstrap sizing shows that when
  // both legs share one risk fraction, the fragile leg CAPS how big the whole book
  // can size — so put-credit is left under-sized. Solution: size each leg
  // separately. Put-credit uses the full risk_per_trade_pct; the conviction leg
  // (setup_type 'gex_momentum') uses risk_per_trade_pct * conviction_size_mult, so
  // it contributes less capital-at-risk and can't drag the book's ruin. This per-leg
  // policy was the most profitable of {equal, per-leg, put-credit-only} at every
  // account >= $5k while KEEPING the directional leg (2026-06-24 sizing study).
  conviction_size_mult: number
}

// FLARE = 0DTE, validated config: PT 20% / SL 100% of debit (vs BLAZE's SL 30%).
//
// Sizing: with SL=100 the debit deployed IS the max loss per trade, so BLAZE's
// risk_per_trade_pct 0.20 x buying_power_usage_pct 0.85 = ~17%/trade would be
// ruinous here (a 3-loss cluster ~= -45%, and account_sim.py shows 25%/trade
// backtested to a -66% drawdown). Cut to ~4%/trade (0.05 x 0.85 = 4.25% of the
// account deployed) for a sane drawdown profile (~-15% on the historical path).
//
// Per-setup daily cap effectively removed: backtest showed cap=3 leaves real
// money on the table (2.25 trades/day) vs 5.46/day at 74.6% WR / PF 2.72 when
// only the signal-reset gate enforces re-entry discipline.
export const DEFAULT_FLARE_CONFIG: FlareConfig = {
  ...DEFAULT_BLAZE_CONFIG,
  stop_loss_pct: 100.0,
  // $5-wide (BLAZE default is $1). CRITICAL: both validated FLARE legs — the
  // conviction directional debit (neg-GEX) and the bullish put credit (pos-GEX) —
  // were validated $5-wide. At $1-wide the bid/ask eats the entire edge
  // (+$0.4/trade ≈ zero); the $5 width is what clears the spread cost. Do not
  // narrow without re-validating on real bid/ask.
  spread_width: 5,
  // PUT-CREDIT (pos-GEX) leg risk fraction = the BASE size. 20% = AGGRESSIVE, set
  // to the SLIPPAGE-ADJUSTED full-Kelly PEAK (operator chose aggressive 2026-06-24).
  // Kelly study: raw in-sample full-Kelly base was ~31%, but after a realistic
  // fill/slippage haircut the growth-maximizing fraction drops to ~20% — and going
  // ABOVE 20% takes more risk for LESS expected growth (25% = the <5%-ruin ceiling
  // for pure variance; 31% raw is strictly worse on every axis once fills count).
  // So 20% is the most aggressive level that still maximizes growth (in-sample CAGR
  // ~69%, but worst-case drawdowns ~85-90% — this is the aggressive end). At $8,790
  // paper that's ~3 put-credit contracts (~16% of acct) on a premium day. The
  // conviction leg sizes DOWN from this via conviction_size_mult (-> ~6.6%).
  // To dial back to the robust/moderate setting use 0.10; to the ruin ceiling 0.25.
  risk_per_trade_pct: 0.20,
  // Quick-ITM morning sleeve (additive; see FlareConfig doc). Ships small + on its
  // own flag because it's a 54-day single-regime sample and a naked long call.
  quick_itm_enabled: true,
  quick_itm_contracts: 1,
  quick_itm_strike_itm: 5,
  quick_itm_entry_start: 900,
  quick_itm_entry_end: 930,
  quick_itm_exit_hhmm: 1300,
  // Conviction (gex_momentum) leg sizes at risk_per_trade_pct * this (=> ~3.3%).
  // The directional leg is fragile (41% win, losses cluster); per-leg sizing keeps
  // it small so it can't cap the durable put-credit leg's size (2026-06-24 study:
  // per-leg was the most profitable policy at every account >= $5k while keeping
  // FLARE directional). Applied in executor.openVertical.
  conviction_size_mult: 0.33,
  max_trades_per_setup_per_day: 999,
  // Per-direction risk controls (see FlareConfig doc above). The "trade all day
  // AND manage risk" equilibrium (operator decision 2026-06-08): 5% per-side
  // force-close caps each adverse cluster; a 15-min cooldown keeps the side
  // trading all day (no halt); and each force-close shrinks that side's next
  // entries x0.33 so a repeatedly-wrong side throttles itself instead of being
  // shut off. 20 concurrent-per-side cap bounds the blast radius.
  // Validated on FLARE's own 8-day tape (flare_equilibrium.py, flat $500/trade):
  //   FC5% + cd15 + size x0.33/FC + cap20 = +$12,681  PF 2.66  maxDD 47%
  //     worst day -$1,967  (~41 trades/day, NEVER halts a direction)
  // vs permanent-halt (+$12,790 / 31/day / -$618) and flat-45m cooldown
  //   (+$14,128 / 37/day / -$2,073 / DD50%). Size-down = most all-day trading
  //   with the lowest drawdown of any >=40/day policy. Loosening FC% was worse
  //   on that (blow-up) tape.
  //
  // 2026-06-08 (operator): loosened 0.05 -> 0.10 after the post-6/04 live tape
  // showed the 5% guillotine doing 15/16 exits, ALL losses (-$1,757), tripping
  // on choppy-regime noise before positions could revert to PT (only 1 PT in 16).
  // The blow-up brake still fires at half the 6/04 damage; size-down + cap20 keep
  // the blast radius bounded. Revisit if a one-way trend day reappears.
  // 2026-06-16 (operator): REVERTED to the free-trading original. The per-direction
  // guillotine (force-close / cooldown / size-down / concurrent cap) and the
  // wall-break entry gate are NEUTRALIZED — FLARE trades freely again, and the
  // NET-IMBALANCE HEDGE (lib/flare/hedge) replaces them as the risk mechanism:
  // instead of CUTTING the stacked side (which created the -$1.5k 6/15 batch loss
  // and tripped on chop), we HEDGE the unhedged directional exposure. To restore
  // the old controls, set: FC 0.10 / cd 15 / size 0.33 / cap 20 / room 1.0 / adverse 0.5.
  perdir_force_close_pct: 100.0,    // never fires (>10000% of balance)
  perdir_cooldown_minutes: 0,       // no cooldown
  perdir_size_mult_after_fc: 1.0,   // no size-down
  max_concurrent_per_direction: 9999, // effectively unbounded
  wall_fade_min_room: 0.0,          // room>=0 → entry gate always passes
  wall_fade_trend_lookback_minutes: 15,
  wall_fade_max_adverse_trend: 9999, // never blocks on trend
  // 0DTE timing override (vs BLAZE's 1DTE 15:55).
  //   - Entries cut off at 14:30 in scanner.ts:isMarketHours.
  //   - 14:45 TIME_STOP closes anything still open 15min before 15:00 settlement.
  // The earlier eod_time_ct also forces close BEFORE Tradier stops quoting
  // expired 0DTE contracts, avoiding the stranded-open reconciliation case.
  eod_time_ct: '14:45',
}
