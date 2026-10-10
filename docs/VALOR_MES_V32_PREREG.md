# VALOR MES v32 preregistration

## Decision

Run one compact, research-only ATR regime audit on the four v31 raw-gross
all-year survivors. Do not touch the production trader, broker, scheduler,
root Render Blueprint, or 2026 data.

## Frozen data and fill boundary

- Development years: 2023, 2024, and 2025 only. The runner imports v31's
  checksummed cached Postgres opportunity construction and cannot request vendor
  data.
- Frozen cells, in deterministic collision priority order:
  1. 30-minute afternoon momentum
  2. 60-minute afternoon momentum
  3. 120-minute late-morning momentum
  4. 120-minute opening-morning mean reversion
- Fill convention: next-minute trade-print open to final hold-minute trade-print
  close. This is a trade-print proxy, not executable BBO.
- Cost views: raw gross; $3 round-trip fee with zero adverse ticks; $3 plus one
  adverse tick on entry and exit; and $3 plus four adverse ticks on entry and
  exit. The one-tick case is explicitly an **unverified planning proxy**, not a
  realistic fill model, because calibration has zero historical fill/fee rows.
- Every variant enforces one global MES position at a time. An entry at the
  exact prior exit timestamp is allowed.

## Frozen variants

1. `combined_baseline`: combine all four cells. Simultaneous candidates use the
   frozen cell order above; no outcome-based ranking is allowed.
2. `atr_low_tercile_exclusion`: only 30-minute afternoon momentum and 120-minute
   opening-morning mean reversion may exclude a trade. After 60 prior exact-cell
   observations, exclude current ATR below the expanding prior-date 33rd
   percentile. Before warmup, preserve baseline behavior. The other two cells
   are unchanged.
3. `atr_tercile_shadow_router`: after 60 prior exact-cell ATR observations,
   classify each opportunity low/mid/high using expanding 33rd/67th percentiles.
   A cell/bin is eligible only after 60 prior shadow observations and prior
   one-tick planning results have positive net dollars, profit factor at least
   1.10, and positive average net trade. Rank simultaneous eligible routes by
   prior planning average net, then by the frozen cell order.

The quantile definition is deterministic linear interpolation at
`(n - 1) * probability` (R-7 / NumPy default). Values equal to the 33rd
percentile are mid; values equal to the 67th percentile are high.

## Causality rule

Thresholds, bins, route metrics, and ranks for a date use prior dates only.
Every opportunity on one date is evaluated from the same opening snapshot.
That date's ATR values and planning outcomes enter shadow history only after all
decisions for the date are frozen. Shadow history includes every causally
classified opportunity, even when portfolio overlap prevents an actual
selection.

## Promotion audit

Audit the one-tick planning view without optimizing or changing a threshold:

- preferred activity: at least 180 selected trades in each year;
- required evidence: positive net P&L in every year;
- preferred quality: profit factor at least 1.20 in each year and average net
  trade at least $8 in each year (the target band is $8-$10; results above $10
  are not penalized).

Passing does not arm or promote anything. The one-tick view remains unverified,
2026 remains untouched, and any forward test requires a separate frozen review.
