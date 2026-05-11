# JOSHUA Replay Report — Phase A

**Date**: 2026-05-11
**Branch**: `claude/joshua-directional-gex-bot`
**Spec**: `docs/superpowers/specs/2026-05-11-joshua-directional-gex-bot-design.md`

---

## TL;DR

**Verdict: NO-GO via this replay** — but the failure mode is **data insufficiency in the available historical window**, not a definitive signal-failure conclusion.

- `watchtower_snapshots` only started populating `call_wall` / `put_wall` / `flip_point` on **2026-05-11**. All ~3,800 historical rows in Feb-May 2026 have zero walls/flip and are useless for setup evaluation.
- `gex_history` has populated walls only for **2025-11-06 → 2025-12-25** (~30 trading days, ~9,500 snapshots), then becomes sparse.
- That 6-week Nov-Dec 2025 window was **sustained EXTREME_POSITIVE gamma**:
  - 9,234 of 9,537 snaps (96.8%) were in some POSITIVE regime
  - Only 91 snaps (0.95%) were in any NEGATIVE regime
  - **wall_break cannot be validated** — negative gamma never lasts long enough to qualify
  - **flip_cross cannot be validated** — regime sign-flips are rare

---

## Replay attempt (default thresholds)

**Window**: 2025-11-01 -> 2025-12-25 (8 weeks)
**Source**: `gex_history` (watchtower_snapshots fallback)
**Snapshots loaded**: 9,537
**Total trades**: 11
**Overall WR**: 45.5%
**Overall EV/trade**: $8.73

| Setup | Trades | WR | PT% | SL% | TIME_STOP% | EV/trade ($) |
|---|---:|---:|---:|---:|---:|---:|
| wall_fade | 11 | 45.5% | 45.5% | 0.0% | 54.5% | 8.73 |
| wall_break | 0 | — | — | — | — | — |
| flip_cross | 0 | — | — | — | — | — |

### GO/NO-GO check (default thresholds)

- n >= 30 trades: **FAIL** (11)
- WR >= 55%: **FAIL** (45.5%)
- EV >= +$3/trade: **PASS** ($8.73)
- 2+ setups firing: **FAIL** (1)

---

## Parameter sweep — loosened wall_fade threshold

| fade_thr | break_thr | n | WR | EV/trade | setups firing |
|---:|---:|---:|---:|---:|---:|
| 0.30 (spec) | 0.20 (spec) | 11 | 45.5% | $8.73 | 1 |
| 0.50 | 0.20 | 15 | 40.0% | $8.36 | 1 |
| 0.70 | 0.20 | 15 | 46.7% | $7.21 | 1 |
| 1.00 | 0.20 | 15 | 46.7% | $7.21 | 1 |
| 0.30 | 0.05 | 11 | 45.5% | $8.73 | 1 |

Loosening break_thr never helps because NEGATIVE-regime snaps are nearly absent. Loosening fade_thr caps out at 15 trades — still well below the n=30 bar.

---

## Why the prior 3 NO-GOs do not necessarily generalize here

The previous 1DTE direction-only NO-GOs (HELIOS magnet 63% WR, Phase 1 walls 29% WR, Phase 2 skew+charm 19.5% WR) all had **ample data** showing definitive signal failure. This replay's failure is **different**: 11 wall_fade trades show a marginally-positive EV (+$8.73/trade) but with WR below the bar. The sample is too small to make a confident GO or NO-GO call on the signal itself; the historical data window is the bottleneck.

## What this run does show

- **wall_fade EV is positive in EXTREME_POSITIVE gamma** — every losing trade was a TIME_STOP, not an SL hit. The signal correctly identifies wall-fade setups; the issue is theta drag killing winners that don't make 20% PT quickly enough.
- **wall_break and flip_cross cannot be evaluated** in any historical window currently available in the AlphaGEX prod DB.
- The replay harness itself works correctly: 8/8 unit tests pass, the data loader produces valid snapshots, the setup-stack dispatch + simulate_intraday integration both function.

---

## Recommendation

Two paths, both for operator decision:

### Path A — proceed to Phase B (paper live)

- The replay can't reject the bot, but it also can't validate it. The only remaining option to validate the 3-setup stack is to run it in paper-live for 4-6 weeks across mixed regimes.
- Pre-merge requirement: apply `migrations/2026-05-11-helios-daily-state.sql` on production postgres (operator authorization needed).
- Enabled gate stays paper-only via `helios_config.enabled` flag.
- Risk: another NO-GO after 4 weeks of paper trading. Cost: zero $ since paper, but operator attention time.

### Path B — defer until backtest is feasible

- Wait for `watchtower_snapshots` to accumulate ~3 months of wall-populated data (i.e., starting 2026-05-11 -> 2026-08-11).
- During wait, the harness in `backtest/joshua_replay/` is committed and ready to re-run.
- Risk: 3-month opportunity cost on a potentially-edge-positive strategy.

---

## Artifacts

- Harness: `backtest/joshua_replay/` (data, quotes, engine, report, cli)
- Tests: `tests/backtest/joshua_replay/` (8 tests, all passing)
- Trade CSV: `backtest/joshua_replay/output/trades.csv`
- Migration: `migrations/2026-05-11-helios-daily-state.sql` (NOT yet applied to prod)
- Branch: `claude/joshua-directional-gex-bot` (NOT yet merged)
