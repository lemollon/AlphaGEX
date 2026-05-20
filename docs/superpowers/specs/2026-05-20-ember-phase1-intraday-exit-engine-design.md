# EMBER — IronForge Backtester · Phase 1 Design Spec

**Date**: 2026-05-20
**Status**: Spec — pending review
**Author**: Claude (with operator)
**Project**: EMBER — the IronForge backtesting platform (fire lineage: SPARK → **EMBER** → FLAME → BLAZE → INFERNO)
**Phase**: 1 of 4 — headless intraday credit-spread exit engine
**Branch**: `claude/ember-phase1-intraday-exit-engine`
**Data substrate**: `helios_options_intraday` (production Postgres `dpg-d4132pje5dus738rkoug-a`; ThetaData-sourced SPY 1-min bid/ask, 2023-01-03 → 2025-12-05)

---

## 1. Purpose

Turn the existing SPY 1-minute option dataset (`helios_options_intraday`, 11.8M rows, with **bid + ask** per strike per minute) into a working backtester that finds the **optimal intraday exit policy for 1DTE SPY credit spreads** — SPARK first. The dataset's unique value is that it can price option spreads minute-by-minute with real bid/ask, which the existing parquet-based `spark_flame_backtest.py` cannot do (it runs on EOD-ish data and cannot model intraday exits at all).

EMBER is the larger IronForge backtesting platform. **This spec covers Phase 1 only**: the headless engine that produces a defensible, out-of-sample-validated exit policy from one command. The IronForge UI is a later phase that wraps this engine — it is explicitly out of scope here.

## 2. The platform and its phasing

EMBER is decomposed into five layers, built in four phases. Each phase gets its own spec → plan → build cycle.

| Layer | Phase |
|---|---|
| 1. Intraday data layer (minute bid/ask → spot, greeks, combo pricing) | **Phase 1** |
| 2. Strategy adapters (SPARK IC; later BLAZE vertical) | **Phase 1** (SPARK) |
| 3. Exit/replay engine + parameter sweep | **Phase 1** |
| 4. Run API + persistence (extend `backtest_routes.py`, `backtest_runs`/`backtest_results`) | Phase 2 |
| 5. IronForge web UI (`ironforge/webapp`) | Phase 3 |
| (generalize adapters to more SPY bots) | Phase 4 |

**Build order is engine-first** because a UI over a non-working engine is hollow. Phase 1 proves both the data and the edge.

## 3. Goal & non-goals

### Goal
Produce, reproducibly from a single CLI command, the exit policy (profit-target / stop-loss / time-stop / trailing) that maximizes risk-adjusted expectancy for a representative 1DTE SPY iron condor, validated out-of-sample, with realistic bid/ask exit fills, and compared head-to-head against SPARK's current live exit config.

### Non-goals (Phase 1)
- No API, no persistence to `backtest_runs`/`backtest_results` (Phase 2).
- No frontend / IronForge UI (Phase 3).
- No BLAZE or other adapters yet — but the engine must be adapter-agnostic so they slot in later (Phase 4).
- No SPX, no 0DTE, no LETF, no non-SPY underlyings (different data, not available intraday).
- No change to live SPARK config as part of this phase. EMBER produces a *recommendation*; applying it is a separate, deliberate step (note: SPARK config is force-reset by `ironforge/webapp/src/lib/db.ts` `ensureTables()` — see `project_spark_config_locks`).

## 4. Data realities & hard constraints

These are verified against the live table and SPARK's trade history, and they bound the whole design:

1. **SPY only.** No SPX/LETF intraday. (ORAT has those EOD-only.)
2. **1DTE dominant, no 0DTE.** DTE distribution: dte=1 → 567 days / 9.2M rows; dte=3 → 132 days; dte=2/4 minor. `min(dte)=1` — **there is no expiry-day (0DTE) chain.** So EMBER studies **same-day (day-T) exits of a 1DTE position**, which is exactly what SPARK does (79 of 80 live closes are same-day; only 2 held to expiry day). Holding into expiry day is out of scope.
3. **No greeks, no spot in the table.** Columns are `trade_date, expiration_date, strike, right, bar_time, open, high, low, close, volume, bid, ask`. Spot and greeks must be **derived** (§6).
4. **Coverage ends 2025-12-05.** SPARK's real trades are all 2026 (Feb–May), **outside** the data window. Therefore Phase 1 **synthesizes** SPARK-style entries over 2023–2025 rather than replaying real ones. Real 2026 SPARK trades are used only as an external sanity check (§10).
5. **Strikes $371–$698, 328 of them; full 09:30–16:00 ET session, ~390 min/day.** Wide enough for ATM ± wings.

## 5. Architecture

New Python package `backtest/ember/`, reusing `backtest/backtest_framework.py` for cost model, metrics (win rate / EV / Sharpe / drawdown), and the trade-audit pattern.

```
backtest/ember/
  __init__.py
  __main__.py        # `python -m backtest.ember ...`
  cli.py             # arg parsing, run orchestration
  data.py            # DataLayer: load chain, derive spot/greeks, combo pricing  (Layer 1)
  bs.py              # Black-Scholes IV inversion + greeks (port from HELIOS bs.py)
  adapters/
    __init__.py
    base.py          # StrategyAdapter protocol + Position dataclass        (Layer 2)
    spark.py         # SparkRepresentativeIC adapter
  engine.py          # ExitEngine: minute replay + exit-policy evaluation    (Layer 3)
  policy.py          # ExitPolicy dataclass + grid generation
  fills.py           # FillModel: ask-cross / mid / mid+slippage
  report.py          # per-trade CSV, summary metrics, sweep heatmap, markdown
  walkforward.py     # train/OOS split + overfit comparison
tests/backtest/ember/
  ...                # unit tests per module (TDD)
```

**Data flow:** `cli` → `DataLayer` loads per-day dte=1 chain → `SparkAdapter.build_entry()` constructs the IC `Position` at entry minute → `ExitEngine` walks minute bars, computing the combo price path via `FillModel`, and evaluates each `ExitPolicy` in the sweep → `walkforward` splits in-sample/OOS → `report` emits artifacts.

## 6. Data layer (`data.py`, `bs.py`)

Per (trade_date, expiration_date=trade_date+1) chain, loaded once and cached.

- **Synthetic spot** (per minute): put-call parity at the near-ATM strike(s): `S ≈ (C_mid − P_mid) + K·e^(−rT)`. Average over the 2–3 strikes nearest the money for stability. Discount negligible at 1DTE but included. Validate the series against cached yfinance EOD SPY and ORAT `underlying_prices` (must agree at the close to within a few cents).
- **IV + greeks** (per option per minute): invert Black-Scholes for IV from the option mid given `(S, K, T, r)`, then compute delta/gamma/theta/vega. `T` = minutes from `bar_time` to 16:00 ET on `expiration_date`, in years. `r` = constant (default 0.05; configurable). Used only for **strike selection** by delta — not for pricing (pricing is always observed bid/ask).
- **Combo pricing** for an iron condor (short put spread + short call spread):
  - **Entry credit received** (conservative): `(put_short.bid − put_long.ask) + (call_short.bid − call_long.ask)`.
  - **Exit cost to close** (conservative, "ask-cross"): `(put_short.ask − put_long.bid) + (call_short.ask − call_long.bid)`.
  - **Mid** variants use leg mids. P&L per spread = `entry_credit − exit_cost` (× 100 × contracts).
- **Liquidity guards:** drop/flag minutes where a required leg has zero or crossed bid/ask, or width beyond a threshold. Record excluded minutes in the audit.

## 7. Strategy adapter — SPARK representative IC (`adapters/spark.py`)

Implements the `StrategyAdapter` protocol (§11). One IC per eligible 1DTE day.

- **Eligibility:** trade_date has a dte=1 chain with enough strikes around the money and a clean entry-minute quote.
- **Entry time:** configurable; default **10:00 ET** (gives a near-full session to manage). Entry time is also an optional secondary sweep dimension.
- **Short strikes:** target short delta `Δ_short` (default **0.16**), pick the nearest strike each side at the entry minute.
- **Wings:** fixed dollar width (default **$5**), configurable; expected-move-based wings optional (EM derived from the ATM straddle mid × factor).
- **Sizing:** 1 contract for the study (P&L reported per-contract; sizing is a live concern, not an exit-policy concern).
- The adapter returns a `Position` (four legs + entry credit + entry minute). It does **not** decide exits — the engine does.

This is deliberately *representative*, not SPARK-exact (SPARK selects strikes off GEX walls, and we only have EOD GEX in-sample). Rationale: keep entry-replication error out of the exit study; the exit edge transfers across entry styles; the adapter interface preserves a faithful adapter for later.

## 8. Exit policy & sweep (`policy.py`, `engine.py`)

An `ExitPolicy` is the set of rules evaluated against a position's minute-by-minute combo P&L path. The engine evaluates the whole grid in one pass per position.

**Sweep dimensions (defaults):**
- `profit_target_pct` (% of credit captured): `[20, 30, 40, 50, 60]`
- `stop_loss_mult` (× credit; loss side): `[0.5, 1.0, 1.5, 2.0, 2.5]` — note SPARK's live `0.5×` is unusually tight (see `project_spark_config_locks`); the sweep tests whether widening helps.
- `time_stop` (force-close by): `[12:00, 13:00, 14:00, 15:00, 15:55]` ET and `None`
- `trailing` (optional): activation % of credit + give-back % of peak; off by default
- `min_hold_minutes`: default 5 (avoid instantaneous exits on entry-minute noise)

**Baseline policy:** SPARK's current live config (PT 30% / SL 0.5×credit / EOD close) is always included and labeled, for a head-to-head delta.

**Exit precedence each minute:** stop-loss → profit-target → trailing → time-stop → EOD (15:55 forced). First trigger wins; record the trigger reason.

## 9. Fill model (`fills.py`)

The differentiator — we have true bid/ask, so exits are modeled as real fills, not mids.

- **Primary (reported as the headline):** combo **ask-cross** on exit, bid-cross on entry — the conservative, SPARK-realistic assumption (matches the documented combo-ask buy-back pain).
- **Sensitivity bands:** **mid** and **mid ± per-leg slippage** (default $0.02–0.05/leg), so we can see how fragile the edge is to fills.
- **Commissions:** per-leg via `backtest_framework` cost model (4 legs × open+close).

Every headline result is reported under all three fill assumptions.

## 10. Walk-forward & validation (`walkforward.py`)

- **In-sample (explore/tune):** 2023-01-03 → 2024-12-31.
- **Out-of-sample (held out):** 2025-01-01 → 2025-12-05 — untouched until a single policy is chosen on the in-sample set, then evaluated once. Report in-sample-best vs. its OOS performance (overfit check).
- **External sanity check:** replay the chosen policy's *logic* against the 80 real 2026 SPARK positions (different period, real entries). Directional sanity only — not validation, since the entries differ.

## 11. Extensibility — `StrategyAdapter` protocol (`adapters/base.py`)

```python
class StrategyAdapter(Protocol):
    def eligible(self, day: TradingDay, chain: Chain) -> bool: ...
    def build_entry(self, day: TradingDay, chain: Chain, cfg: AdapterConfig) -> Position: ...
    # Position exposes: legs (strike, right, qty), entry_minute, entry_credit
```

The `ExitEngine` operates only on the `Position`'s combo price path, so it is strategy-agnostic. A `BlazeVerticalAdapter` (debit vertical) and a `FaithfulSparkAdapter` (GEX-wall strikes) implement the same protocol with **zero engine changes**. This is the seam that lets Phase 4 generalize.

## 12. Outputs & success criteria (`report.py`)

**Artifacts** (written to `backtest/ember/out/<run-id>/`):
- `trades.csv` — per trade: date, entry time/strikes/credit, exit time/reason/cost, pnl, max-favorable/adverse excursion.
- `summary.csv` — per policy: n, win rate, EV/contract, total pnl, Sharpe, max DD, avg hold min, % EOD-forced — under each fill model.
- `sweep.json` — PT × SL (× time-stop) grid for later UI heatmaps.
- `report.md` — best policy, delta vs SPARK baseline, in-sample vs OOS, external 2026 sanity.

**Phase 1 is successful when** (this is an engine deliverable, not a strategy bet):
1. The data layer's derived spot matches EOD references within tolerance, and a hand-checked example position's P&L path is reproduced correctly.
2. The engine emits an OOS-validated optimal exit policy with EV/contract and a head-to-head vs SPARK's live config, under all three fill models.
3. The full run reproduces from one command.

A **NO-GO on the strategy** (no policy meaningfully beats baseline after realistic fills) is still a successful Phase 1 — it is a real answer, and the engine remains the asset that Phases 2–4 build on.

## 13. Risks & open questions

- **BS IV inversion is noisy** at deep-OTM / wide-spread strikes → delta-based strike selection may jump. Mitigation: invert from mid, smooth, fall back to fixed-offset selection if delta is unreliable.
- **Synthetic spot accuracy** via parity → validated against yfinance EOD + ORAT `underlying_prices`; if intraday spot is needed more precisely, SPY minute bars are free on ThetaData's STOCK bundle (no paid sub required).
- **Illiquid / zero-bid minutes** distort fills → guarded and flagged (§6).
- **Representative ≠ SPARK-exact** → results are "best exit for 1DTE SPY ICs," to be forward-tested live before any SPARK config change.
- **Edge cases excluded:** the 12/80 multi-day and 2/80 expiry-day SPARK trades fall outside this model.

## 14. Deferred to later phases
- Phase 2: run API + persistence (`backtest_runs`/`backtest_results`, extend `backtest_routes.py`).
- Phase 3: IronForge EMBER UI in `ironforge/webapp` (pick bot + dates + params → equity curve, per-trade table, sweep heatmaps).
- Phase 4: BLAZE adapter + faithful-SPARK adapter + more SPY bots.
