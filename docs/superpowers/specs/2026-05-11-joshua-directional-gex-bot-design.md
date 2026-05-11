# JOSHUA Directional GEX Bot — Design Spec

**Date**: 2026-05-11
**Status**: Spec — pending review
**Author**: Claude (with operator)
**Internal codename**: HELIOS (existing scaffold)
**Display name**: JOSHUA
**Branch**: `claude/joshua-directional-gex-bot` (this spec); execution branches off it
**Predecessor specs**: `2026-05-07-helios-1dte-directional-design.md` (NO-GO 5/8), `2026-05-10-1dte-directional-research-design.md` (Phase 1 NO-GO 5/10, Phase 2 NO-GO 5/10)

---

## 1. Purpose

Build a 1DTE SPY directional trading bot that consumes the **live AlphaGEX GEX feed** (`/api/gex/SPY`) and trades a setup-stack of structurally-defined directional plays: wall-fade in positive-gamma regimes, wall-break in negative-gamma regimes, and flip-cross on regime transitions.

The previous three NO-GOs (HELIOS magnet 63% WR, Phase 1 walls 29% WR, Phase 2 skew+charm 19.5% WR) all attempted to **reconstruct GEX from raw chain quotes**. This bot consumes the production-grade GEX signals that the AlphaGEX dashboard already produces — same Net GEX, Flip, Call Wall, Put Wall, regime label, ±1σ band that the operator looks at when trading manually.

## 2. Goal & non-goals

### Goal
Validate (or reject) the hypothesis: **a 3-setup directional stack driven by the production AlphaGEX GEX feed produces ≥60% WR / +$5 EV per trade on 1DTE SPY debit verticals.**

### Non-goals
- No reconstruction of GEX from chain quotes — that's been tested three times and failed
- No ML / PROPHET / regime_signals gating in V1 — keeping the stack pure to isolate the signal's edge
- No multi-symbol (SPY only V1) — confirmed by operator
- No event-blackout filter in V1 — keeping the stack pure; can add later
- No trailing stop — Phase 2 showed it killed winners on 1DTE noise

## 3. Background

The AlphaGEX dashboard at `/gex/SPY` (and its API at `/api/gex/SPY`) already produces all the structural signals that previous NO-GO experiments tried to reconstruct:

| Field | Source | Type |
|---|---|---|
| `net_gex` | TradingVolatility (after-hours) / Tradier (live) | signed dollar gamma |
| `regime` | derived from net_gex | 7-level: EXTREME_NEGATIVE / HIGH_NEGATIVE / MODERATE_NEGATIVE / NEUTRAL / MODERATE_POSITIVE / HIGH_POSITIVE / EXTREME_POSITIVE |
| `flip_point` | per-strike GEX sum-zero crossing | dollar strike |
| `call_wall` | argmax(call_gamma * OI) strike | dollar strike |
| `put_wall` | argmax(put_gamma * OI) strike | dollar strike |
| `spot_price` | live tradier or TradingVolatility | dollar |
| `sigma_1d_band_width` | ±1σ expected move (computed from ATM IV × √(t)) | dollar |

The bot consumes this feed at 60-second cadence during market hours and applies a 3-setup decision stack.

## 4. Hypothesis

**A 1DTE SPY debit vertical fires positive expectancy when:**
1. **Wall-fade**: in positive-gamma regime, when spot is close enough to a wall that mean-reversion gravity dominates (EM-relative threshold)
2. **Wall-break**: in negative-gamma regime, when spot has clearly broken through a wall with momentum (EM-relative threshold)
3. **Flip-cross**: when spot crosses the flip point with a regime sign-flip confirming, on a fixed-distance hysteresis

**Why this might work where the previous three didn't**: the signal substrate is *production-grade* (TradingVolatility's institutional GEX feed, same one professional dealers use), not a reconstruction from chain bars. The three NO-GOs failed largely because their inputs were stale, sparse, or approximate; this bot uses inputs that are live and structurally sound.

**Why it might fail**: same as before — the market may simply already price these structural levels efficiently, leaving no edge for retail-side direction trades. The 1DTE theta drag may kill winners even with a correct signal.

## 5. Reuse strategy

HELIOS (display: JOSHUA) is already scaffolded on the unmerged branch `claude/helios-1dte-directional-design`. Per the HELIOS spec/memo:

- 8 `helios_*` DB tables already applied to production postgres
- 13 routes at `/api/joshua/*` registered in `backend/main.py`
- `/joshua` frontend dashboard page (1114 lines)
- Scheduler entry wired in `scheduler/trader_scheduler.py`
- `trading/helios/{models, executor, monitor, trader, db}.py` — orchestration layer

**Strategy**: rebase / repurpose the HELIOS branch by replacing only the *signal logic* — keep all the DB tables, routes, frontend page, scheduler entry, executor, monitor, trader, and paper-account infrastructure unchanged.

**Files replaced**:
- `trading/helios/signals.py` — swap from "compute walls from chain" to "consume /api/gex/SPY + setup stack dispatch"
- `trading/helios/strategy.py` — swap from magnet-direction to wall-fade / wall-break / flip-cross routing

**Files added**:
- `trading/helios/gex_client.py` — polling client for `/api/gex/SPY`, dataclass `GexSnapshot`
- `trading/helios/setups/__init__.py`
- `trading/helios/setups/wall_fade.py`
- `trading/helios/setups/wall_break.py`
- `trading/helios/setups/flip_cross.py`

**Files modified (minor)**:
- `trading/helios/trader.py` — wire new signals
- `trading/helios/monitor.py` — drop trailing stop logic; keep PT/SL/TIME_STOP only
- `trading/helios/models.py` — add `SetupType` enum, `helios_daily_state` table fields
- `trading/helios/db.py` — add `load_daily_state`, `upsert_daily_state` helpers
- `migrations/2026-05-11-helios-daily-state.sql` — new table

**Files unchanged**: 8 helios_* DB tables (existing), 13 backend routes, frontend page, executor, paper_account flow.

## 6. Setup logic (concrete)

### 6.1 Daily state

A new table `helios_daily_state` tracks per-bot, per-day setup-fired flags. Reset implicitly at market open (no row for today = all setups armed).

```sql
CREATE TABLE helios_daily_state (
    trade_date DATE NOT NULL,
    wall_fade_fired BOOLEAN NOT NULL DEFAULT FALSE,
    wall_break_fired BOOLEAN NOT NULL DEFAULT FALSE,
    flip_cross_fired BOOLEAN NOT NULL DEFAULT FALSE,
    last_signal_minute INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date)
);
```

Each setup is independently armed at market open and locks for the day after it fires.

### 6.2 Setup 1 — wall_fade (positive-gamma mean-reversion)

**Regime gate**: `regime ∈ {MODERATE_POSITIVE, HIGH_POSITIVE, EXTREME_POSITIVE}`

**Trigger** (EM-relative):
- **Fire put vertical** when `(call_wall - spot) / sigma_1d_band_width < 0.30` AND `spot < call_wall`. The call wall sits within 30% of expected-move distance overhead → strong overhead resistance; fade down toward flip.
- **Fire call vertical** when `(spot - put_wall) / sigma_1d_band_width < 0.30` AND `spot > put_wall`. Put wall below acts as floor; fade up toward flip.

**Vehicle**: 1DTE $1-wide debit vertical. Long ATM, short ATM±1 in fade direction.

### 6.3 Setup 2 — wall_break (negative-gamma momentum)

**Regime gate**: `regime ∈ {MODERATE_NEGATIVE, HIGH_NEGATIVE, EXTREME_NEGATIVE}`

**Trigger** (EM-relative):
- **Fire call vertical** when `spot > call_wall` AND `(spot - call_wall) / sigma_1d_band_width > 0.20`. Spot has cleared the call wall by ≥20% of expected-move distance; dealer hedging amplifies the breakout.
- **Fire put vertical** when `spot < put_wall` AND `(put_wall - spot) / sigma_1d_band_width > 0.20`. Mirror.

**Vehicle**: 1DTE $1-wide debit vertical. Long ATM, short ATM±1 in direction of break.

### 6.4 Setup 3 — flip_cross (regime-transition directional)

**Inputs**: 5-minute rolling buffer of `(spot, flip_point, regime, net_gex)`.

**Trigger** (fixed-distance with hysteresis):
- **Fire call vertical** when:
  - 5-min-ago `spot < flip_point - 0.15%`
  - Current `spot > flip_point + 0.15%`
  - `net_gex` changed sign from negative→positive within last 5 min
- **Fire put vertical** mirror

**Vehicle**: same as above.

### 6.5 Conflict resolution

The setups are mutually exclusive *in trigger logic* by regime gate:
- wall_fade requires positive regime
- wall_break requires negative regime
- flip_cross requires regime sign-flip

Same-minute multi-fire is impossible. Same-day sequential fires are allowed (e.g., wall_break in the morning, regime stabilizes positive, wall_fade in the afternoon).

**Dispatch order** (deterministic): `flip_cross` > `wall_break` > `wall_fade`. If multiple somehow qualify in a malformed snapshot, the regime-transition signal wins.

## 7. Polling + scan loop

```
[60s scan tick]
   │
   ├─► gex_client.get_spy()  →  GET /api/gex/SPY  →  GexSnapshot
   │     • fail-open: stale snapshot > 90s → log skip:gex_stale, no fire
   │     • retry once on 5xx with 5s backoff
   │
   ├─► load_daily_state()  →  helios_daily_state row (insert if absent)
   │
   ├─► For setup in [flip_cross, wall_break, wall_fade]:
   │     if state.{setup}_fired: continue
   │     action = setup.evaluate(snapshot, history_buffer)
   │     if action: break  (first unfired qualifying wins)
   │
   ├─► If action == None: write helios_scan_activity (NO_TRADE) row
   │
   └─► If action:
         ├─► trader.open_position(action)
         │     ├─► Pull current chain via Tradier (NOT /api/gex)
         │     ├─► Build $1-wide debit vertical: long ATM, short ATM±1
         │     ├─► Size: Kelly cap = 20% × current_balance × 0.85
         │     │        contracts = floor(capital_at_risk / (debit × 100))
         │     ├─► Place 2-leg sandbox order, cascade fallback if needed
         │     ├─► Write helios_positions + helios_signals rows
         │     └─► upsert_daily_state(setup.name + '_fired' = TRUE)
         └─► Continue scan loop
```

## 8. Position management

Monitor cycle runs every 60s alongside scan. For each open helios position:

- `mark = long.bid - short.ask` (conservative; long.bid because we'd sell to close, short.ask because we'd buy to close)
- `pnl_pct = (mark / debit - 1) × 100`

**Exit triggers** (first-match, no trailing stop):
- `pnl_pct >= 20` → close PT
- `pnl_pct <= -30` → close SL
- `now_ct >= 15:55 CT` → close TIME_STOP
- `quotes_unavailable_streak >= 10 cycles` → close DATA_FAILURE

No trailing stop. Phase 2 proved trail kills winners on 1DTE noise.

## 9. Sizing

Per-trade Kelly cap: `risk_per_trade_pct = 0.20` of current balance.
Overall BP usage cap: `buying_power_usage_pct = 0.85`.

```python
capital_at_risk = balance × 0.20 × 0.85
contracts = max(1, floor(capital_at_risk / (debit × 100)))
```

Same shape as FLAME/SPARK/INFERNO post-fix from 2026-05-11. Matches operator policy.

## 10. Components — file map

```
trading/helios/
├── gex_client.py        # NEW — GexSnapshot dataclass, polling, staleness check
├── setups/
│   ├── __init__.py      # NEW
│   ├── wall_fade.py     # NEW — evaluate(snap, state) → SignalAction | None
│   ├── wall_break.py    # NEW
│   └── flip_cross.py    # NEW — uses 5-min history buffer
├── signals.py           # REPLACE — orchestrates setup stack, returns first qualifying
├── strategy.py          # REPLACE — wraps signals.py for trader.py
├── trader.py            # MODIFY — call new signals; rest unchanged
├── monitor.py           # MODIFY — drop trailing stop logic
├── models.py            # MODIFY — add SetupType enum + daily_state fields
├── db.py                # MODIFY — load_daily_state, upsert_daily_state
└── executor.py          # UNCHANGED

migrations/
└── 2026-05-11-helios-daily-state.sql   # NEW — single-table migration

backend/api/routes/
└── joshua_routes.py     # UNCHANGED (13 existing routes)

frontend/src/app/joshua/
└── page.tsx             # UNCHANGED (existing dashboard)

backtest/joshua_replay/   # NEW — 3-month replay harness for validation
├── __init__.py
├── replay.py            # Iterates watchtower_snapshots; replays setup stack
├── report.py            # Markdown + CSV; same shape as touch_pin/skew_signal
└── cli.py               # python -m backtest.joshua_replay --start ... --end ...

tests/helios/
├── test_gex_client.py        # NEW
├── test_wall_fade.py         # NEW
├── test_wall_break.py        # NEW
├── test_flip_cross.py        # NEW
├── test_signals_dispatch.py  # NEW
└── test_replay_smoke.py      # NEW

docs/superpowers/reports/
└── 2026-05-11-joshua-replay.md   # Phase A replay report (committed)
```

## 11. Validation methodology

### Phase A — 3-month replay (1-2 days to build + run)

**Source**: `watchtower_snapshots` table (2026-02-09 → present, intraday cadence). This table stores the same fields as `/api/gex/SPY` returns — net_gex, flip, walls, regime, spot, ±1σ.

**Replay**: iterate the table in chronological order, treat each row as a `GexSnapshot`, run the same setup stack the live bot will run. For each fire, build a synthetic 1DTE vertical from `helios_options_intraday` quotes (the same data Phase 1/2 used) and simulate via `quant.sim.simulate_intraday` with PT=20 / SL=30 / no trail / time-stop at minute 385.

**Output**: per-setup WR, EV, time-stop %, PT-hit %, SL-hit %. ~3 months ≈ 60 trading days; expect 50-150 trades total across the stack.

**GO/NO-GO (replay-light)**:
- Total trades ≥ 30
- Mean PnL/trade ≥ +$3 (lower bar than live — 3 months is small)
- At least 2 of 3 setups firing
- WR ≥ 55%

If replay is GO → proceed to Phase B. If NO-GO → fix or abandon before burning live cycles.

### Phase B — Paper live (4-6 weeks)

**Setup**: merge branch to main → Render auto-deploys → `helios_config.enabled=true` → scheduler fires the bot every 60s during market hours.

**Account**: sandbox-only (no production money). Existing `helios_paper_account` infrastructure handles balance/collateral/BP.

**Monitoring**:
- Daily: scan activity, signal counts, position outcomes
- Weekly: per-setup WR, EV, time-stop %, PT-hit %, SL-hit %, regime distribution of fires

**GO criteria (live, 4-week window)**:
- n ≥ 40 trades total
- WR ≥ 60%
- EV ≥ +$5/trade post-cost (1-tick slippage per leg + $5.20 commission)
- At least 2 of 3 setups firing (proves diversification, not single-signal lottery)
- Time-stop % ≤ 30% (signal is decisive)

If GO → escalate decision to operator on live money rollout. If NO-GO → post-mortem report; archive the bot.

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| GEX feed staleness (TradingVolatility lag, Tradier hiccup) | `gex_client` rejects snapshots > 90s old; logs `skip:gex_stale` |
| Three prior NO-GOs suggest no edge | Phase A replay (3 mo) is cheap insurance |
| Setup parameter calibration (0.30 / 0.20 / 0.15) is initial guess | All thresholds in `helios_config`; tune from replay results before Phase B |
| 1DTE theta killed Phase 1/2 winners | Same vehicle, but no trailing stop this time; signal is structurally different |
| Event days (NFP/CPI/FOMC) skew outcomes | Not blocked in V1; monitor in Phase B; add blocker only if event days dominate loss tail |
| Multiple bots on SPY chain collision | JOSHUA runs on its own paper account (`helios_paper_account`); no collision |
| `/api/gex/SPY` endpoint outage | gex_client retries once + fail-open; bot logs skip but doesn't crash |
| Wall/flip values jump erratically (data quality) | The 5-min history buffer in flip_cross requires sustained cross, not single-tick |

## 13. Out of scope (deferred)

- Multi-symbol (QQQ, IWM, etc.)
- Event-blackout integration
- PROPHET ML confidence gate
- Trailing stop revisit
- Production money — escalation only after Phase B GO
- Live brief integration (separate concern; covered by IronForge brief cadence policy)

## 14. Approval to proceed

Once approved, the next step is to invoke the `writing-plans` skill to produce a concrete step-by-step implementation plan for:
1. Promote HELIOS branch's reusable scaffold into the new branch (or rebase)
2. Build Phase A replay harness (`backtest/joshua_replay/`)
3. Run Phase A replay → GO/NO-GO
4. If GO: build the live components (`gex_client.py`, 3 setups, refactor `signals.py` / `strategy.py` / `monitor.py`)
5. Apply migration, smoke-test paper trading, monitor Phase B

Implementation plan will live at `docs/superpowers/plans/2026-05-11-joshua-directional-gex-bot.md`.
