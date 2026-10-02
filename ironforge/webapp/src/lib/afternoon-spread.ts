/**
 * PAPER-ONLY RESEARCH TRACKER — "dynamic hedge V2" (Leron, 2026-09-26: "Put on
 * paper to track it"). Independently re-derived and placebo-tested in
 * C:\Users\lemol\dev\meltup\VERIFY_dynamic_hedge_v2v3.md and
 * RESULT_profit_protection_h1_h5.md — read those before touching this file.
 *
 * The lead: every trading day, at SPY spot as of 13:05 CT, watch for the
 * spot approaching EITHER FLAME's own EBB put strike (P, $1 OTM below spot)
 * or FLINT's own call strike (C, ceil(spot+1)). When one side gets
 * threatened, sell a SAME-DAY, $1-wide vertical on the OPPOSITE side:
 *
 *   - Down trigger (spot falls toward P)  -> sell a CALL vertical.
 *   - Up trigger   (spot rises toward C)  -> sell a PUT vertical.
 *
 * The placebo test found the specific trigger MINUTE adds ~nothing (V2 sits
 * at the 57.5th percentile of a random-minute draw on the same days) — the
 * money is in DAY SELECTION: 474/478 fires (99%) land on days FLAME's own
 * VIX decay gate would have SKIPPED (ratio > 0.80), which carry 98% of the
 * net P&L. This tracker exists to log gate_pass/gate_skip on every row so
 * that finding can be checked forward, live.
 *
 * This file holds ONLY pure, DB/network-free logic — same split as
 * lib/ebb-sizing.ts — so it is unit-testable without mocking Postgres or
 * Tradier. lib/afternoon-spread-tracker.ts does the DB/Tradier orchestration
 * and NEVER places an order — see that file's own header.
 */

export type AfternoonSpreadSide = 'down_call' | 'up_put'
export type AfternoonSpreadGateTag = 'gate_pass' | 'gate_skip'
export type AfternoonSpreadStatus = 'tracked' | 'settled' | 'skipped'

/** Trigger scan window, Central Time, HHMM — inclusive both ends. */
export const TRIGGER_WINDOW_START_HHMM = 1310
export const TRIGGER_WINDOW_END_HHMM = 1445

/** Both hedge verticals are $1-wide, per spec. */
export const VERTICAL_WIDTH = 1

/** Distance (dollars) inside the reference strike that arms each trigger. */
export const TRIGGER_BUFFER = 0.50

/**
 * Round-trip commission per contract, per the task spec's settlement
 * formula verbatim: `(credit - intrinsic) x 100 - $1.40`.
 */
export const AFTERNOON_SPREAD_COMMISSION_PER_CONTRACT = 1.40

/**
 * FLAME's own VIX decay gate ceiling (scanner.ts `VIX_DECAY_CEILING.flame`,
 * frozen at 0.80 since 2026-09-08). Hardcoded here rather than imported: the
 * tracker (lib/afternoon-spread-tracker.ts) is called INTO by scanner.ts each
 * cycle, so importing scanner.ts from this side would be circular, and this
 * value is a deliberate, reviewed spec constant, not a live lookup.
 */
export const FLAME_VIX_GATE_CEILING = 0.80

/**
 * AFTERNOON_SPREAD_PAPER — on|off, unset = off. This is the ONLY switch this
 * feature has; there is no "live"/"armed" value anywhere. 'on' enables paper
 * tracking (reads quotes, writes rows to the tracker's own table). Anything
 * else — unset, '', 'off', a typo — fails CLOSED to no tracking at all.
 */
export function getAfternoonSpreadPaperMode(): boolean {
  return (process.env.AFTERNOON_SPREAD_PAPER ?? '').trim().toLowerCase() === 'on'
}

/** Is this Central Time HHMM inside the 13:10-14:45 trigger scan window? */
export function isInTriggerWindow(
  hhmm: number,
  start: number = TRIGGER_WINDOW_START_HHMM,
  end: number = TRIGGER_WINDOW_END_HHMM,
): boolean {
  return hhmm >= start && hhmm <= end
}

/**
 * P — the strike FLAME's own EBB put spread would sell at the 13:05 CT PM
 * clock: $1 OTM below spot, rounded to the nearest whole dollar. This is
 * `Math.round(spot - otmAbs)` with `otmAbs = 1.0` — byte-for-byte the
 * `putShort` formula in scanner.ts's `botStructure('flame')` path. Not
 * imported directly (see the module header on the circular-import reason);
 * the offset is the specification, per scanner.ts's own comment: "the
 * offsets ARE the specification."
 */
export function referencePutStrike(spot: number): number {
  return Math.round(spot - 1)
}

/**
 * C — "FLINT's rule" per the research spec: ceil(spot + 1), the first
 * whole-dollar strike at least $1 above spot. (FLINT itself — a live SPY
 * 0DTE call-spread sleeve using this exact formula — is in-flight on a
 * separate, unmerged branch; this tracker implements the formula directly
 * rather than depending on that branch's code, so it works standalone off
 * `main` and never drags in unreviewed/unmerged logic.)
 */
export function referenceCallStrike(spot: number): number {
  return Math.ceil(spot + 1)
}

/** Down trigger: spot has fallen to within (or below) `buffer` of P, EBB's put strike. */
export function downTriggerFires(spot: number, p: number, buffer: number = TRIGGER_BUFFER): boolean {
  return spot <= p + buffer
}

/** Up trigger: spot has risen to within (or above) `buffer` of C, FLINT's call strike. */
export function upTriggerFires(spot: number, c: number, buffer: number = TRIGGER_BUFFER): boolean {
  return spot >= c - buffer
}

/** Down-trigger structure: sell a $1-wide CALL vertical. short = ceil(spot)+1, long = short+1. */
export function downTriggerCallVertical(spot: number, width: number = VERTICAL_WIDTH): { short: number; long: number } {
  const short = Math.ceil(spot) + 1
  return { short, long: short + width }
}

/** Up-trigger structure: sell a $1-wide PUT vertical. short = floor(spot)-1, long = short-1. */
export function upTriggerPutVertical(spot: number, width: number = VERTICAL_WIDTH): { short: number; long: number } {
  const short = Math.floor(spot) - 1
  return { short, long: short - width }
}

/**
 * Entry credit: short leg at BID, long leg at ASK (the same conservative
 * paper-fill convention every spread in this codebase uses). Returns null
 * — never a floored zero — when the credit is non-positive; the caller must
 * skip and log, per spec.
 */
export function entryCredit(shortBid: number, longAsk: number): number | null {
  const credit = Math.round((shortBid - longAsk) * 10000) / 10000
  return credit > 0 ? credit : null
}

/** Settlement intrinsic of a short CALL vertical, clamped to the wing width. */
export function callVerticalIntrinsic(close: number, short: number, long: number): number {
  const width = long - short
  return Math.min(Math.max(close - short, 0), width)
}

/** Settlement intrinsic of a short PUT vertical, clamped to the wing width. */
export function putVerticalIntrinsic(close: number, short: number, long: number): number {
  const width = short - long
  return Math.min(Math.max(short - close, 0), width)
}

/**
 * P&L per contract: (credit - intrinsic) x 100 x contracts, minus the
 * round-trip commission. Per spec, this is a 1-lot research tracker —
 * `contracts` defaults to 1 and there is no sizing ladder here.
 */
export function settlementPnl(credit: number, intrinsic: number, contracts: number = 1): number {
  const gross = (credit - intrinsic) * 100 * contracts
  const commission = AFTERNOON_SPREAD_COMMISSION_PER_CONTRACT * contracts
  return Math.round((gross - commission) * 100) / 100
}

/**
 * gate_pass = FLAME's own VIX decay gate would have let it trade that day
 * (ratio <= ceiling). gate_skip = the ratio was elevated or unreadable —
 * the research found 98% of this lead's edge sits on gate_skip days.
 */
export function tagGate(ratio: number | null, ceiling: number = FLAME_VIX_GATE_CEILING): AfternoonSpreadGateTag {
  return ratio != null && ratio <= ceiling ? 'gate_pass' : 'gate_skip'
}

/* ------------------------------------------------------------------ */
/*  Ledger summarization — pure, so the operator route's totals math   */
/*  is unit-testable without a database.                                */
/* ------------------------------------------------------------------ */

export interface AfternoonSpreadLedgerRow {
  trade_date: string
  side: AfternoonSpreadSide
  gate_tag: AfternoonSpreadGateTag
  status: AfternoonSpreadStatus
  realized_pnl: number | null
}

export interface AfternoonSpreadBucketTotals {
  rows: number
  settled: number
  skipped: number
  net_pnl: number
}

export interface AfternoonSpreadTotals {
  by_side: Record<string, AfternoonSpreadBucketTotals>
  by_gate: Record<string, AfternoonSpreadBucketTotals>
}

function bump(
  bucket: Record<string, AfternoonSpreadBucketTotals>,
  key: string,
  row: Pick<AfternoonSpreadLedgerRow, 'status' | 'realized_pnl'>,
): void {
  if (!bucket[key]) bucket[key] = { rows: 0, settled: 0, skipped: 0, net_pnl: 0 }
  bucket[key].rows += 1
  if (row.status === 'settled') {
    bucket[key].settled += 1
    bucket[key].net_pnl += row.realized_pnl ?? 0
  } else if (row.status === 'skipped') {
    bucket[key].skipped += 1
  }
}

/** Running totals by side (down_call/up_put) and by gate tag (gate_pass/gate_skip). Pure — no DB. */
export function summarizeAfternoonSpreadLedger(rows: AfternoonSpreadLedgerRow[]): AfternoonSpreadTotals {
  const bySide: Record<string, AfternoonSpreadBucketTotals> = {}
  const byGate: Record<string, AfternoonSpreadBucketTotals> = {}
  for (const r of rows) {
    bump(bySide, r.side, r)
    bump(byGate, r.gate_tag, r)
  }
  for (const b of [...Object.values(bySide), ...Object.values(byGate)]) {
    b.net_pnl = Math.round(b.net_pnl * 100) / 100
  }
  return { by_side: bySide, by_gate: byGate }
}
