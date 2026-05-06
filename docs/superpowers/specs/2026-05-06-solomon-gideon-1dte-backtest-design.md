# SOLOMON / GIDEON 1DTE Directional Spread Backtest — Design

**Date:** 2026-05-06
**Author:** Claude (Opus 4.7) for the AlphaGEX team
**Status:** Spec — pending implementation plan

## Problem

SOLOMON and GIDEON are live directional debit-spread bots on SPY 0DTE. Production performance since inception:

| Bot | Trades | Total P&L | Win Rate | Median Hold |
|---|---|---|---|---|
| SOLOMON | 3,607 | −$780,113 | 21.8% | 5 minutes |
| GIDEON | 3,570 | −$2,714,908 | 18.6% | 5 minutes |

91-94% of trades exit via 50% stop-loss. The dominant failure mode is **microstructure whipsaw**: a $0.40 stop on a $0.80 debit fires from bid/ask crossing alone in the first few minutes, before the directional thesis can play out.

We want to test whether the **same GEX-walls signal**, evaluated on a **1DTE horizon** with **no intraday exits**, has any directional edge — i.e., is the strategy fundamentally broken, or is it the 0DTE/intraday-exit combination?

## Goals

- Run an honest 6-year backtest (2020-01-02 → 2025-12-05, ~1,239 trading days) of the SOLOMON and GIDEON entry logic shifted from 0DTE to 1DTE.
- Use the GEX-walls + VIX-gate logic only. No PROPHET, no ML — both because they cannot be reconstructed historically (only 107 prophet_predictions exist) and because we want to isolate the underlying signal's edge.
- Hold every trade to 1DTE expiration. No intraday stops, profit targets, or HJB early-exits. This eliminates the whipsaw failure mode by construction.
- Produce a per-bot scorecard with year-by-year, VIX-bucket, and direction breakdowns sufficient to decide whether the strategy deserves further tuning.

## Non-Goals

- No intraday simulation. ORAT data is EOD-only; we will not fabricate intraday checkpoints.
- No PROPHET / ML signal in v1. (Future iteration may layer it on for the Feb 2026+ window where predictions exist.)
- No commissions or slippage in v1. Bid/ask is recorded per trade for later attribution.
- No live trading changes from this backtest. Output is research only — any live retune is a separate spec.
- No new database tables. Results live entirely on disk.

## Strategy Specification

### Entry signal (per trading day T)

Mirrors `trading/solomon_v2/signals.py:check_wall_proximity` exactly:

1. Skip if VIX outside `[min_vix, max_vix]`.
2. Compute `dist_to_put_wall_pct = (spot - put_wall) / spot * 100` and `dist_to_call_wall_pct = (call_wall - spot) / spot * 100`.
3. If `|dist_to_put_wall_pct| <= wall_filter_pct` → BULLISH (bull call spread).
4. If `|dist_to_call_wall_pct| <= wall_filter_pct` → BEARISH (bear put spread).
5. If both within filter, pick the wall with smaller absolute dollar distance to spot (deterministic; bullish wins exact ties).
6. Otherwise, skip with reason `NOT_NEAR_WALL`.

### Strike selection

Mirrors `trading/solomon_v2/signals.py:calculate_spread_strikes`:

- BULLISH (bull call spread): `long_strike = round(spot)`, `short_strike = long_strike + width`
- BEARISH (bear put spread): `long_strike = round(spot)`, `short_strike = long_strike - width`
- `width` per bot config below.

### Entry pricing

- **Expiration choice:** the soonest expiration after T whose date is itself a trading day in our data (so we have an EOD chain to settle from). This is *almost always* the next trading day in the modern SPY daily-expiration era (post-2022); pre-2022 it can be T+2 or T+3 (Wed/Fri). The trade is still labeled "1DTE" even when the calendar gap is >1 day. If the chosen expiration is more than 4 calendar days out, skip with `NO_NEAR_EXPIRATION` (covers data gaps).
- Pull both legs from `orat_options_eod` for trade_date=T at that expiration.
- Debit = `long_mid - short_mid`. Skip if debit ≤ 0 or debit ≥ width.
- `contracts = floor(risk_per_trade / (debit * 100))`. Skip if < 1.

### Exit (settlement)

- On day T+1 EOD, settle from intrinsic value at `underlying_price` from the T+1 chain:
  - Bull call: `payoff = max(0, min(spot_T+1, short_strike) - long_strike)`
  - Bear put: `payoff = max(0, long_strike - max(spot_T+1, short_strike))`
- `realized_pnl = (payoff - debit) * 100 * contracts`
- No intraday exits, no early exits.

### Bot configurations

```python
SOLOMON = {
    "ticker": "SPY",
    "wall_filter_pct": 1.0,
    "spread_width": 2,
    "min_vix": 12.0,
    "max_vix": 35.0,
    "risk_per_trade": 1000.0,
    "starting_capital": 100000.0,
}

GIDEON = {
    "ticker": "SPY",
    "wall_filter_pct": 1.0,
    "spread_width": 3,
    "min_vix": 12.0,
    "max_vix": 30.0,
    "risk_per_trade": 1000.0,
    "starting_capital": 100000.0,
}
```

## Architecture

```
backtest/directional_1dte/
├── __init__.py
├── __main__.py        # CLI entry
├── config.py          # BOT_CONFIGS dict
├── data.py            # ORAT loaders
├── signals.py         # Wall-proximity → BULLISH | BEARISH | SKIP
├── pricing.py         # Strike selection + chain debit lookup
├── payoff.py          # Hold-to-expiration intrinsic settlement
├── engine.py          # Daily loop driver
├── report.py          # Scorecard CSV/JSON writers
└── tests/
    ├── test_signals.py
    ├── test_pricing.py
    ├── test_payoff.py
    └── test_engine.py
```

**Output:** `backtest/results/2026-05-06-solomon-gideon-1dte/{solomon,gideon}/`
- `summary.json` — headline stats
- `equity_curve.csv` — day-by-day equity
- `trades.csv` — full ledger including bid/ask per leg for slippage attribution
- `skips.csv` — every skipped day with categorized reason
- `by_year.csv`, `by_vix_bucket.csv`, `by_direction.csv` — breakdowns
- `top_trades.csv`, `worst_trades.csv` — best/worst 10
- `run.json` — reproducibility metadata (config, runtime, row counts at each filter stage)
- `run.log` — structured run log

Top-level `comparison.json` and `comparison.md` summarize SOLOMON vs GIDEON side-by-side.

## Components

### `config.py`
Two dicts (SOLOMON, GIDEON) per the spec above. No mutable global state. Validated at engine start.

### `data.py`
Pure functions backed by ORAT (`ORAT_DATABASE_URL`). All read-only.

- `load_trading_days(start, end) -> list[date]` — distinct trade_date from `orat_options_eod` where ticker='SPY' between start and end inclusive.
- `load_chain(trade_date) -> DataFrame` — all SPY rows for that date with bid/ask/mid for both calls and puts, indexed by (expiration_date, strike).
- `load_vix(trade_date) -> float | None` — close from `vix_history`. Returns None if missing.
- `load_gex_walls(trade_date) -> dict | None` — pulled from `gex_strikes` for SPY: `call_wall` is the strike with peak |gex| above spot, `put_wall` is the strike with peak |gex| below spot. Falls back to `gex_structure_daily` if `gex_strikes` returns nothing for that day. Returns `{call_wall, put_wall, spot}` or None.

### `signals.py`
One pure function:
```python
def generate_signal(walls, spot, vix, config) -> Signal | None
```
Mirrors `solomon_v2/signals.py:check_wall_proximity` semantics exactly. No side effects.

### `pricing.py`
- `select_strikes(spot, direction, width) -> (long_strike, short_strike)` — ATM-rounded.
- `lookup_debit(chain, expiration, long_strike, short_strike, direction) -> float | None` — returns mid-debit or None if either strike is missing or bid > ask. Records both legs' bid/ask for the trade ledger.

### `payoff.py`
- `compute_payoff(spread_type, long_strike, short_strike, spot_at_expiry) -> float` — per-share payoff at expiration; bounded by [0, width].

### `engine.py`
`run(bot_name, start, end) -> BacktestResult`:
1. Load trading days. For each day T (excluding the last):
2. Locate T+1 = next trading day. If `(T+1 - T).days > 3`, skip with `LONG_WEEKEND`.
3. Load chain_T, walls_T, vix_T. Generate signal.
4. If skip → record reason and continue.
5. Select strikes, look up debit, size contracts. Skip with reason if any check fails.
6. Load chain_T+1 → spot_T+1 (median of `underlying_price` if multi-row). Settle. Append trade.
7. Maintain running equity series.

Implicit contract: every day produces exactly one of: a recorded trade, a recorded skip. No silent drops.

### `report.py`
Pure formatters. Take a `BacktestResult`, write all CSVs/JSON listed above. Headline stats: total_trades, total_pnl, sharpe (annualized), max_dd, win_rate, avg_win, avg_loss, expectancy, profit_factor.

### `__main__.py`
```
python -m backtest.directional_1dte \
    --bot {solomon,gideon,both} \
    --start YYYY-MM-DD \
    --end YYYY-MM-DD \
    [--output-dir PATH]
```
Defaults: `--bot both`, `--start 2020-01-02`, `--end 2025-12-05`, `--output-dir backtest/results/<today>-solomon-gideon-1dte/`.

## Data flow per simulated trade

```
Day T at EOD:
  ORAT.orat_options_eod (SPY, T)
  ORAT.gex_strikes      (SPY, T)        ──▶ data.py  ──▶  {chain_T, walls_T, spot_T, vix_T}
  ORAT.vix_history      (T)                                         │
                                                                    ▼
                                                       signals.generate_signal(...)
                                                                    │
                                                          ┌─────────┴─────────┐
                                                       SKIP                 Signal
                                                          │                   │
                                                  log skip & continue          ▼
                                                                  pricing.select_strikes(...)
                                                                              │
                                                                              ▼
                                                          pricing.lookup_debit(chain_T, T+1, ...)
                                                                              │
                                                                  contracts = floor($1000 / (debit * 100))
                                                                              │
                                                                              ▼
                                                                  Trade(T, debit, strikes, contracts)

Day T+1 at EOD:
  ORAT.orat_options_eod (SPY, T+1) ──▶ spot_T+1 ──▶ payoff.compute_payoff(...)
                                                                │
                                                                ▼
                                          realized_pnl = (payoff - debit) * 100 * contracts
                                                                │
                                                                ▼
                                       append to ledger; update equity_T+1 = equity_T + pnl
```

## Edge cases

| Condition | Handling |
|---|---|
| ORAT `underlying_price` differs across rows for same trade_date | Use median; warn if max-min > 0.5% |
| `gex_strikes` returns no peak above OR below spot | Skip with `NO_WALLS_FOUND` |
| Both walls within `wall_filter_pct%` of spot | Pick closer wall (deterministic tie-break) |
| Selected strike doesn't exist in T+1 chain | Settle from spot anyway (intrinsic only) |
| Selected strike doesn't exist in entry-day chain | Skip with `STRIKES_MISSING_FROM_CHAIN` |
| Entry debit ≥ spread width | Skip with `DEBIT_INVALID` |
| Entry debit ≤ 0 | Skip with `DEBIT_INVALID` |
| `risk_per_trade / (debit * 100) < 1` | Skip with `SIZE_BELOW_1_CONTRACT` |
| 1DTE expiration falls on a holiday | Walk forward to next trading day; flag `EXPIRY_NOT_T+1` |
| Gap between T and chosen expiration > 4 calendar days | Skip with `NO_NEAR_EXPIRATION` |
| Gap between T and T+1 trading day > 3 calendar days (long holiday) | Allowed; chosen expiration may equal T+1; only blocks if >4 cal days |
| VIX missing for trade_date | Skip with `NO_VIX_DATA` |
| Bid/ask null but mid present | Use mid (log warning) |
| Bid > ask (data corruption) | Skip with `DEBIT_INVALID` |

**Failure modes that crash, not skip:**
- Cannot connect to ORAT
- Schema mismatch in `orat_options_eod`
- `BOT_CONFIGS` missing required key
- Output directory unwritable

**Determinism:** Same input + same config → bit-identical output. No RNG, no wall-clock-dependent logic.

**Reproducibility metadata** (in `run.json`): ORAT data window queried, code git SHA, full config dict, total runtime, row counts at each filter stage.

## Testing strategy

### Unit tests (no DB, synthetic fixtures)

| File | Coverage |
|---|---|
| `test_signals.py` | Bullish trigger near put wall; bearish near call wall; SKIP when neither wall within filter; SKIP outside VIX range; tie-break picks closer wall; missing wall data returns SKIP. |
| `test_pricing.py` | Bull-call selects ATM long + (ATM+width) short; bear-put symmetry; ATM rounds to nearest dollar; debit returns mid; missing strike returns None; bid > ask returns None. |
| `test_payoff.py` | Bull-call full payoff above short strike; zero below long; partial between; bear-put symmetry; payoff bounded by [0, width]. |
| `test_engine.py` | Single-day fixture produces trade or skip (no silent drop); skip categorization; sizing math; long-weekend skipping. |

### Integration tests (`--integration` flag, hits ORAT)

| Test | Proves |
|---|---|
| `test_smoke_one_week` | Engine runs 5 days in March 2024 against real ORAT without exception; every day produces trade-or-skip; equity is monotonic in time. |
| `test_walls_match_live` | For 5 sample dates from production live window (Feb 2026+), wall reconstruction agrees with `solomon_signals.call_wall`/`put_wall` within ±$1. Skipped if no overlap. |
| `test_payoff_against_chain` | For 10 sample expired trades, recomputed payoff agrees with actual T+1 chain price within $0.05. |

### Sanity checks (asserted on full-range run, written to `run.json`)

- Total trades + total skips == total trading days in range
- Sum of per-trade pnl == final equity − starting capital
- Max single-trade loss ≤ risk_per_trade × 1.05
- Equity curve has no NaN
- No duplicate trade dates per bot

### Determinism test
Run engine twice on same range, diff outputs, assert empty.

## Known limitations / honest caveats

1. **EOD-only data.** This backtest cannot model intraday exits. The realized 5-minute holding pattern of live SOLOMON/GIDEON cannot be reproduced; 1DTE hold-to-expiration is a different strategy than the live one. The point is to test whether the *signal* has edge — not to predict live performance.
2. **Wall reconstruction approximation.** `gex_strikes` may not give identical walls to what the live bot saw. We audit this against the production `solomon_signals` table (Feb 2026+ window) where we have both sources. If walls disagree by >$1 on >20% of audit dates, results are suspect.
3. **No commissions or slippage in v1.** Mid-fill assumption is optimistic. Bid/ask is recorded per trade so a slippage haircut can be applied post-hoc.
4. **No PROPHET / ML.** This tests the underlying GEX signal, not the live decision stack. A future iteration may layer PROPHET/ML on for the Feb 2026+ window.
5. **ORAT data ends 2025-12-05.** The actual live trading window (Feb 2026+) is not in scope for the historical backtest. Sister study against live data lives elsewhere.
