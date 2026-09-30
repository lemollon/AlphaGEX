# Flame intraday shock and VIX-forward plan

## Purpose

Test whether information observable *before* Flame's 14:05 ET entry can avoid
some large-loss conditions without creating a hindsight filter. This follows the
failed static FOMC-blackout and fixed 10% aggregate-risk-cap study. Nothing in
this document authorizes a live strategy change.

## Stage 1 — historical, pre-entry SPY shock study

Use the existing validated SPY minute series. At 14:04 ET, freeze only:

- 15-minute realized range: `(high - low) / 14:04 open`;
- 15-minute signed return: `14:04 close / 13:49 close - 1`;
- 60-minute realized range;
- whether the day is an official FOMC decision date.

The initial grid must be selected on the training window ending 2025-09-26 and
reported chronologically on 2025-09-29 through 2026-09-28. It must retain
current .80 Flame rules, FLINT, XSP, fees, reconstructed gamma and separate
natural/adverse fills. No threshold may be selected from the validation period.

Acceptance is strict: a candidate must preserve or increase net P&L after the
external subscription in both fills *and* have no worse closed drawdown than
the current .80 baseline. A candidate failing either fill is rejected.

## Stage 2 — prospective intraday-VIX shadow mode

When the VIX feed is available, record a shadow snapshot once per minute from
13:45 through 14:10 ET in the isolated research database. It must include:

- `asof_utc`, feed source, VIX value and source timestamp;
- age in seconds, with `age_seconds <= 90` required for a usable observation;
- 1-, 5- and 15-minute VIX changes, computed only from earlier snapshots;
- matching SPY timestamp/price and the frozen Flame candidate context;
- FOMC-date flag and an explicit `data_usable` / fail-closed reason.

For the first 40 qualifying sessions this is observation only: it must not
block, resize, or submit an order. Freeze a candidate threshold from that
training sample, then forward-validate it over the next 20 qualifying sessions
in paper/shadow mode. Missing, stale, crossed, or mismatched timestamps are
recorded as unusable — never substituted with a later value or interpreted as
"safe."

## Guardrails

- No broker/order endpoints and no modification of the customer strategy.
- No data later than 14:04 ET may affect that day's Stage 1 decision.
- No historical intraday VIX reconstruction from daily closes.
- Gamma and minute-fill limitations retain their existing disclosures.
