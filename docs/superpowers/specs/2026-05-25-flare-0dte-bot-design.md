# FLARE — 0DTE Directional Paper Bot — Design

**Date:** 2026-05-25
**Status:** Design (awaiting review → plan → branch build → review before deploy)
**Branch:** `claude/flare-0dte-bot` (NOT merged — joining the live scanner needs explicit sign-off)

## Summary

FLARE is a new IronForge **paper** bot: BLAZE's GEX directional logic on **0DTE** SPY,
with the configuration the 2026-05-25 full-board backtest validated as a STRONG GO —
**PT 20% / SL 100% of debit**, running **both `wall_fade` and `wall_break`**. It is a
sibling to BLAZE (which stays 1DTE), modeled on the existing per-bot IronForge pattern.

## Why

Full-board backtest ([[project-blaze-gex-0dte-GO-2026-05-24]]): on 0DTE, `wall_fade`
@ SL=100 is positive every year 2023–2025 (PF ~3.1) and `wall_break` adds a second
positive edge (GO 7/9 configs). The production tight stop (SL=30) is the worst config.
FLARE operationalizes that finding for forward (paper) validation on live data.

## Scope (this build)

**In:** a complete paper bot — signals, 0DTE execution, exits, DB tables, scanner
registration, dashboard, API (the dynamic `/api/[bot]/*` routes already cover any
registered bot). **Paper-only**, branch-isolated.

**Out:** any live/real-money trading; touching BLAZE; the live-deploy merge (separate,
gated on operator sign-off + ideally the 1DTE cross-check result).

## Architecture

Mirror the BLAZE per-bot pattern (`ironforge/webapp/src/lib/blaze/`). Two viable
shapes — **decision: clone into a `flare/` lib** (lowest risk; BLAZE's modules are
lightly `blaze`-coupled, and a clone keeps BLAZE untouched and lets FLARE diverge on
expiration + config without conditionals threaded through shared code).

### New: `ironforge/webapp/src/lib/flare/`
- `types.ts` — `FlareConfig` = BLAZE config but `profit_target_pct: 20`, `stop_loss_pct: 100`, plus a `setups_enabled` set incl. `wall_break`. Same `GexSnapshot`/`SetupAction` types.
- `setups.ts` — **reuse BLAZE's setups verbatim** (import from `../blaze/setups`) — identical `wall_fade`/`wall_break`/`flip_cross` math. No duplication.
- `executor.ts` — clone of BLAZE's, except expiration = **same trading day** (today), not `nextTradingDay`. Writes `flare_positions`.
- `exit.ts` — reuse BLAZE's `decideExit` (PT/SL/TIME_STOP) with FLARE's config (SL=100). 0DTE EOD hard-close stays.
- `db.ts` — `flare_*` table helpers (mirror blaze).
- `scanner.ts` — `scanFlare()` mirroring `scanBlaze()` (monitor + entry + equity/gex snapshots), gated by a `flare` kill switch.

### Edits to shared wiring
- `lib/db.ts`: add `flare` to the bot-name maps, `validateBot` (allow `flare`), `dteMode('flare') → '0DTE'`, the `['flame','spark','inferno','blaze']` table/daily-state/PDT loops (→ add `flare`), PDT config row (`['flare','0DTE',0,0]` — no PDT cap, paper).
- `lib/scanner.ts`: register `scanFlare()` in `runAllScans` (after `scanBlaze`).
- `app/flare/page.tsx`: `<BotDashboard bot="flare" accent="..." />` (new accent, e.g. `purple`/`fuchsia`).
- `app/page.tsx` + `BotDashboard` bot union type: add `flare`. `IC Chart` tab label override → "Directional Chart" (like blaze); render `BlazeDirectionalChart` (or a flare variant) for flare.
- Tables auto-create on first use via `ensureTables()` (the loops above) — `flare_positions`, `flare_paper_account`, `flare_equity_snapshots`, `flare_signals`, `flare_logs`, `flare_daily_state`, `flare_gex_history`, `flare_pdt_config`.

### Config (validated)
`spread_width: 1`, `profit_target_pct: 20`, `stop_loss_pct: 100`, ATM `round(spot)` long + 1-wide, `wall_fade` + `wall_break` enabled (`flip_cross` present but dormant), 0DTE same-day expiration, EOD hard-close ~15:50 ET, Kelly/BP sizing as BLAZE, **paper account only**, default **kill-switch OFF** until operator enables.

## Key 0DTE differences from BLAZE
1. **Expiration = today** (same-day), vs BLAZE's next-day. Settlement at 4 PM ET if held; EOD hard-close before that.
2. **SL = 100%** (the validated wide stop) vs BLAZE's 30.
3. **`wall_break` enabled** (BLAZE effectively only ever fired `wall_fade`).

## Testing
- Unit: `flare` config values; executor builds same-day expiration; `dteMode('flare')='0DTE'`; `validateBot('flare')`.
- `npx next build` must pass (TS).
- Scanner test: `scanFlare` registered + no-throw on empty state.

## Rollout / gating
1. Build on branch; `npx next build` green.
2. **Review with operator before merge** — merging deploys it into the live scanner (paper). Default kill-switch OFF, so even merged it won't trade until toggled on.
3. The **1DTE cross-check** (running) informs whether to *also* fix BLAZE's stop — orthogonal to FLARE, but relevant to the operator's overall directional plan.

## Risks
- Touching `db.ts` shared loops can affect existing bots — keep edits additive (append `flare` to lists), run `npx next build`, and verify the existing bot tables/queries are unchanged.
- 0DTE liquidity/assignment: paper-only + EOD hard-close mitigates; backtest used conservative fills.
- EV is real but moderate; this is forward (paper) validation, not a green light to real capital.
