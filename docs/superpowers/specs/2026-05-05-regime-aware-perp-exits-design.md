# Regime-aware adaptive exits for AGAPE perp/futures bots

**Date:** 2026-05-05
**Owner:** lemol (operator), Claude (impl)
**Status:** approved, awaiting plan

## Problem

The 11 AGAPE perp/futures bots (BTC, ETH, SOL, AVAX, XRP, DOGE, SHIB-PERP,
SHIB-FUT, LINK-FUT, LTC-FUT, BCH-FUT) use a single fixed exit profile
(`no_loss_activation_pct`, `no_loss_trail_distance_pct`, `max_unrealized_loss_pct`,
`max_hold_hours`) regardless of market regime. The user observes that
non-BTC/ETH bots "make money and then give it back" — they go profitable in
chop, fail to lock gains because the trail is sized for trending moves, then
round-trip to the max-loss floor.

A single set of exit knobs cannot be optimal in both regimes:

- **Chop**: small wins are common, retraces eat them quickly. Need tight
  activation, tight trail, hard take-profit cap, short max-hold.
- **Trend**: wide initial activation lets winners run; tight trail kills them
  via noise. Need wider activation, looser trail, no fixed cap, longer
  max-hold.

## Goal

Bots remain profitable in chop AND in trend without operator intervention,
by selecting exit behaviour from the entry-time market regime and adding a
"give-back N% of MFE" exit layer that works alongside the existing trail.

## Non-goals (v1)

- Mid-trade regime re-evaluation. Regime is stamped at entry; the trade
  rides that profile to close. Avoids whipsaw from regime-detector noise.
  Revisit if backtests show static stamping leaves money on the table.
- Replacing the existing no-loss trailing stop. The new MFE-giveback exit
  runs *in addition to* the trail; either can fire.
- Touching SAR or funding-flip exits.
- Touching the existing options/equity bots (FORTRESS, SAMSON, etc.).

## Design

### 1. Regime classification

New shared module `trading/agape_shared/regime_classifier.py`:

```python
def classify_regime(snapshot) -> Literal["chop", "trend", "unknown"]
```

Rules in order:

1. `combined_signal in ("LONG","SHORT")` AND
   `combined_confidence in ("MEDIUM","HIGH")` → **trend**
2. `combined_signal == "RANGE_BOUND"` → **chop**
3. `combined_signal in ("LONG","SHORT")` with `LOW` confidence → **chop**
   (a directional read with low confidence is a chop play in disguise).
4. Tiebreaker if `combined_signal` is missing/None:
   `crypto_gex_regime == "NEGATIVE"` → **trend**;
   `crypto_gex_regime == "POSITIVE"` → **chop**.
5. Anything else → **unknown** (treated as chop downstream — more
   conservative).

Result is stamped on every position as `regime_at_entry`.

### 2. Per-regime exit profile

Each bot's `AgapeXxxConfig` gains two `ExitProfile` instances. The dataclass
lives in `trading/agape_shared/exit_profile.py`:

```python
@dataclass
class ExitProfile:
    activation_pct: float
    trail_distance_pct: float
    profit_target_pct: float       # 0 = no fixed cap (rides for trend)
    mfe_giveback_pct: float        # 0..100; 0 = disabled
    max_hold_hours: int
    max_unrealized_loss_pct: float
    emergency_stop_pct: float = 5.0
```

Initial defaults (each bot can override; backtester tunes per coin):

| Field                       | chop | trend |
|-----------------------------|-----:|------:|
| activation_pct              | 0.30 | 0.70  |
| trail_distance_pct          | 0.15 | 0.50  |
| profit_target_pct           | 1.00 | 0.00  |
| mfe_giveback_pct            | 40   | 60    |
| max_hold_hours              | 6    | 24    |
| max_unrealized_loss_pct     | 1.50 | 2.50  |

Fallback: when a bot has no `exit_profile_chop` / `exit_profile_trend` set,
the existing flat config keys are wrapped into a single profile and used
for all regimes (so the migration is non-breaking).

### 3. MFE-giveback exit (new exit type)

Tracked off the existing `high_water_mark`. Math (long side; short
symmetric):

```
mfe_pct        = (hwm - entry) / entry * 100
giveback_pct   = profile.mfe_giveback_pct
giveback_floor = entry + (hwm - entry) * (1 - giveback_pct/100)
```

Fire only if `mfe_pct >= 0.5` (don't react to noise) and
`current_price < giveback_floor` (or `>` for shorts). Close at
`current_price` with
`close_reason = f"MFE_GIVEBACK_{giveback_pct}pct_of_+{mfe_pct:.1f}%"`.

Exit-priority order in `_manage_position` (first-match-wins):

1. `MAX_LOSS` / `EMERGENCY_STOP`
2. `PROFIT_TARGET` (chop only — trend has it set to 0.0 = disabled)
3. `TRAIL_STOP` (existing armed trail)
4. **`MFE_GIVEBACK`** *(new)*
5. Funding-flip exit (existing)
6. `MAX_HOLD_TIME`

### 4. Schema migration

Each `agape_*_perp_positions` and `agape_*_futures_positions` table gets:

```sql
ALTER TABLE agape_<bot>_positions
  ADD COLUMN IF NOT EXISTS regime_at_entry VARCHAR(20);
```

Done idempotently in each bot's `_ensure_tables()` — same pattern already
used for `trailing_active` and `current_stop`.

`AgapeXxxPosition` dataclass gains an Optional `regime_at_entry: str | None`
field. Persisted on `save_position`.

### 5. Backtest extension

`backtest/perp_exit_optimizer.py` extended to:

- For each historical closed trade, look up the scan-activity row that
  triggered it (via the `position_id` link) to extract entry-time
  `combined_signal` / `combined_confidence` / `crypto_gex_regime`.
- Run those values through the same `classify_regime()` helper.
- Replay the trade with the regime-matched profile.
- Report metrics:
  - per-regime: trade count, win rate, sum P&L, MFE-giveback exit %,
    trail-stop exit %, max-loss exit %, avg MFE, avg giveback (%).
  - combined: same fields aggregated.
- Search grid: 2 profiles × per-bot × hyper-cube. Coarse grid first to
  keep runs short.

New runner: `backtest/run_regime_aware_optimizer.py --bot SOL --since 2026-04-01`.
Persists results to the existing `perp_exit_optimizer_runs` table with
`grid='regime_aware'`.

### 6. Wiring & feature flag

`AgapeXxxConfig` gains `use_regime_aware_exits: bool = False`. When False,
`_manage_position` follows the current path (single flat config, no
MFE-giveback). When True, it goes through the new regime-aware path.

This lets us deploy code without changing live behaviour, then flip per-bot
once the backtest validates.

### 7. Rollout

1. Land schema migration + helper modules + `ExitProfile` config wrapper.
   Feature flag default = False everywhere. **No live behaviour change.**
2. Land regime-aware `_manage_position` path behind the flag.
3. Land backtest extension + runner.
4. Run backtester on **SOL**, **AVAX**, **SHIB-FUT** (pilots — most
   affected by the current giveback). Review per-regime metrics.
5. Set `use_regime_aware_exits=True` on the three pilots via
   `autonomous_config`. Restart trader.
6. Monitor 48–72h via `scripts/audit_perp_exits.py`.
7. If metrics improve, run backtester for the remaining 8 bots and flip
   their flags. If metrics regress on any pilot, flip its flag back off
   and revisit the regime classifier.

## Risk / fallback

- Bug in `classify_regime` mis-stamps every trade → still survivable
  because chop and trend profiles both have `max_unrealized_loss_pct`
  caps; worst case is sub-optimal exits, not blow-ups.
- Schema add is non-destructive (nullable column).
- Feature flag means rollback is one config row per bot.

## Open questions (resolved by defaults)

- *Initial chop/trend numbers* — use the §2 table as v1; backtester tunes.
- *Pilot set* — SOL + AVAX + SHIB-FUT.
- *Mid-trade regime re-eval* — out of scope for v1.

## Operator actions

- After each implementation push: **Manual Deploy `alphagex-trader`** on
  Render so the worker picks up new code.
- After backtest harness lands: run
  `python backtest/run_regime_aware_optimizer.py --bot SOL --since 2026-04-01 --grid coarse`
  (and same for AVAX, SHIB-FUT) on the Render shell; paste output back so
  the chosen profile values can be applied via
  `/api/admin/perp-exit-optimizer/apply`.
