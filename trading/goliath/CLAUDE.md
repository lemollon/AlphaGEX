# GOLIATH

GOLIATH is the LETF earnings-week options bot in the AlphaGEX research lab. Currently in Phase 1.5 (calibration). Sibling to SPARK.

## Universe

MSTR, TSLA, NVDA, COIN, AMD (5 underlyings, each with a paired LETF).

## Current phase

Phase 1.5 — empirical calibration of 4 spec parameters against 90d real data from Trading Volatility `/gex/historical` and yfinance.

Spec for current phase: `@docs/goliath/GOLIATH-PHASE-1.5-RECOVERY.md`

## Execution rules

**One step per response, then STOP.** Phase 1.5 has a 10-step build order in the recovery doc. Do exactly one step, commit, report `[GOLIATH-STEP-COMPLETE]`, then stop and wait for "next" before advancing. Do not batch steps. Prior sessions died of stream timeout when too much was generated in one response.

**Audit before resuming.** If the user says "resume" instead of "next", re-run the Step 0 audit from the recovery doc to determine what's already on disk before writing anything.

**Real data only in production modules.** No synthetic data in `data_fetch.py`, the orchestrator, or any module the calibration report depends on. Tests can and should use synthetic inputs. If TV API fails for any underlying → STOP, report `[GOLIATH-BLOCKED]`, escalate to Leron.

**Cache 90d pulls.** Parquet cache directory: `.goliath_cache/` (add to `.gitignore`). Per-day invalidation.

**Spec defaults are sticky.** Phase 1.5 may recommend changes to wall threshold, fudge factor, drag coefficient, or vol window. The dataclass accepts new params, but defaults stay at spec values (2.0×, 0.1, theoretical-formula, 30d) until Leron explicitly approves recommendations.

**Module contracts are fixed.** Each metric module exposes `calibrate(data, config) -> Result` with the exact signature in the recovery doc. Don't deviate.

## Tag conventions

- `[GOLIATH-AUDIT]` — disk state report (Step 0)
- `[GOLIATH-STEP-COMPLETE]` — end of one step in the build order
- `[GOLIATH-FINDING]` — something noteworthy in data or codebase
- `[GOLIATH-DELTA]` — proposed change to spec or build plan; categorize green/yellow/red light
- `[GOLIATH-BLOCKED]` — cannot proceed, need Leron input
- `[GOLIATH-PHASE-COMPLETE]` — final report at end of phase

## Universe failure rule

If any underlying fails coverage or produces unusable calibration results, escalate to Leron immediately with the failure data. Do not work around it. Universe may need to change.
