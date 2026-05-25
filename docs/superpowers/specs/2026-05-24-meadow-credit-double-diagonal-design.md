# MEADOW — Credit Double Diagonal (SpreadWorks paper bot)

**Date:** 2026-05-24
**Status:** Approved — building

## Summary

Add a new SpreadWorks paper bot, **MEADOW**, that trades a **credit double diagonal**
on SPY. It is the credit-side sibling of DRIFT (which trades a *debit* double
diagonal). Origin: a chat screenshot of a "Double Diagonal" builder (SPY $745.70,
6d/9d expirations, net credit, positive theta / negative vega) plus the operator's
note that the meta enters **Mondays and Fridays only**.

DRIFT (existing) pays a debit, is long-vega, and requires back-IV > front-IV.
MEADOW collects a credit, is short-vega and positive-theta, by selling the
near-dated strangle close to the money and buying a slightly-longer-dated strangle
further out of the money.

## Strategy logic

`backend/bots/strategies/double_diagonal_credit.py` → `build_double_diagonal_credit_signal(...)`

- **Underlying:** SPY. **Front:** 6 DTE (short legs). **Back:** 9 DTE (long legs).
- **Shorts:** short put @ `spot − sd_mult×ATM_straddle`, short call @ `spot + sd_mult×ATM_straddle`
  (`sd_mult = 1.0`), snapped to nearest front-chain strikes.
- **Longs:** long put `spread_width` ($5) below the short put, long call $5 above the
  short call, snapped to the nearest back-chain strike in the OTM direction.
- **Credit:** `(short_put_mid + short_call_mid) − (long_put_mid + long_call_mid)`.
  Reject if `< MIN_CREDIT` ($0.25). VIX gate ≤ 32 (matches FLOW).
- **Risk (iron-condor-shaped, conservative):**
  `wing_width = max(put_wing, call_wing)`,
  `max_profit = credit × 100`, `max_loss = (wing_width − credit) × 100`. Reject if `max_loss ≤ 0`.
  (The real loss is smaller because the long legs retain time value in a later
  expiration; using the IC worst case over-estimates risk, which is safe for sizing.)
- **Sizing:** `contracts = floor(equity × bp_pct / max_loss_per)`, `bp_pct = 0.50`,
  uncapped (`max_contracts = 0`).
- **Targets (credit convention):** `pt_target = pt_pct × max_profit × contracts`,
  `sl_target = sl_pct × max_profit × contracts`. Defaults `pt_pct = 0.50`, `sl_pct = 1.00`
  (take half the credit; stop once the loss equals the credit collected).
- Exposes `.credit`; `legs()` lists the two **short front** legs first so the scanner's
  front-expiration / EOD logic keys off the correct expiration.

## Entry-day gate (new, generic)

- New `entry_days` config column (TEXT, CSV of lowercase weekday abbreviations,
  e.g. `"mon,fri"`). Empty string = no restriction (all current bots).
- MEADOW seeds `"mon,fri"`. Added to every `{bot}_config` table via an idempotent
  `ALTER TABLE … ADD COLUMN` migration mirroring the existing `pt_override` pattern.
- `scanner.run_scan_cycle` checks the weekday **before opening** (after the entry-window
  check). New outcome `BLOCKED_ENTRY_DAY`. The monitor/exit path is unaffected — open
  positions are still managed and can exit on any day.

## Credit-strategy centralization (small refactor)

The credit-vs-debit branch is currently a hardcoded `("iron_butterfly","iron_condor")`
tuple in `executor.py`, with a separate `CREDIT_STRATEGIES` set literal in `routes.py`.
Move the canonical set to `backend/bots/strategies/__init__.py` (a leaf module, no import
cycle) and have both import it, adding `double_diagonal_credit`. This makes MTM, close,
and payoff all treat MEADOW as a credit strategy without the sets drifting apart.

```python
CREDIT_STRATEGIES = frozenset({"iron_condor", "iron_butterfly", "double_diagonal_credit"})
```

## Payoff

The DD payoff math (`_scan_pnl_profile` in `routes.py`) is identical for credit and
debit DD — only the `entry_cost` sign differs, and that is already driven by
`CREDIT_STRATEGIES` membership (`entry_cost = −credit` for credit strategies). So
`routes_bots.get_position_payoff` aliases `double_diagonal_credit` onto the existing
`double_diagonal` math. No change to `_scan_pnl_profile` itself.

## Wiring touchpoints

| Layer | File | Change |
|---|---|---|
| Strategy | `backend/bots/strategies/double_diagonal_credit.py` | **new** builder |
| Shared const | `backend/bots/strategies/__init__.py` | `CREDIT_STRATEGIES` |
| Registry | `backend/bots/registry.py` | `meadow` entry (6/9 DTE, defaults, `entry_days="mon,fri"`) |
| Scanner | `backend/bots/scanner.py` | dispatch `double_diagonal_credit`; entry-day gate |
| Executor | `backend/bots/executor.py` | use `CREDIT_STRATEGIES` |
| DB | `backend/bots/db.py` | `entry_days` column + migration + seed (`.get` fallback) |
| Routes | `backend/routes.py` | import `CREDIT_STRATEGIES` (replace literal) |
| Bot routes | `backend/routes_bots.py` | payoff alias; `ConfigUpdate.entry_days` |
| Frontend reg | `frontend/src/lib/botRegistry.js` | `meadow` + `STRATEGY_LABEL` + `BOT_THEME` (emerald) |
| Frontend glyph | `frontend/src/components/bots/BotGlyph.jsx` | `sprout` glyph |
| Frontend config | `frontend/src/components/bots/ConfigTab.jsx` | `entry_days` field |
| Tests | `tests/test_double_diagonal_credit.py`, `tests/test_scanner.py`, `tests/test_registry.py`, fixtures `spy_6dte_chain.json` / `spy_9dte_chain.json` | builder math, day gate, registry count |
| Build | `frontend/dist/` | rebuild + commit (dist-drift gotcha) |

The route layer, DB tables, scheduler (`list_bots()`), nav pill, and dashboard page
are all registry-driven, so registering `meadow` surfaces a full working bot.

## Launch state

Enabled, 50% BP uncapped, paper-only — matches BREEZE/TIDE/DRIFT/FLOW.

## Out of scope (v1)

- Roll/adjustment management (close at front-expiration EOD or on PT/SL — the existing
  DC/DD behavior). Revisit if LowCountryTrades' meta specifies rolls.
- Delta-based strike selection (chain dict has no per-strike delta).
- Wiring MEADOW into the standalone manual Builder page (it's a bot, not a builder preset).
