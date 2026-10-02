# VALOR MES fresh-start research status

## Decision

Do not promote or retune any MES v33-v38 family. All six frozen families failed
their preregistered discovery gate, 2024 and 2025 were never opened, and calendar
year 2026 stayed sealed. The next useful step is a free historical-data cost
estimate, not another OHLCV parameter search.

## Why MNQ does not establish success

The MNQ breakout is a historical 2023-2025 candidate, not a proven strategy.
Its current forward paper record is only 4 closed trades, 1 win, and -$59 net.
That is neither live evidence nor sufficient forward evidence.

The exact same breakout rule also has different economics on MES. Before costs,
the MES record was:

| Year | Trades | Raw gross |
|---|---:|---:|
| 2023 | 498 | +$3,507.50 |
| 2024 | 501 | +$108.75 |
| 2025 | 497 | +$3,482.50 |

After a $3 round-trip fee plus two adverse ticks per side, those years became
-$476.50, -$3,899.25, and -$493.50. MNQ retained positive historical results
under its tested cost model; MES did not. A signal can therefore transfer while
its post-cost edge does not.

## Frozen family record

| Version | Frozen mechanism | Verdict | Deciding evidence |
|---|---|---|---|
| v33 | Causal MNQ-to-MES residual catch-up, 24 cells | `FAMILY_FAIL_DISCOVERY` | All 24 two-tick cells lost money. |
| v34 | MNQ preceding-30-bar breakout transferred to MES | `FAILED_2023_DISCOVERY` | 497 trades; two-tick net -$769.75. |
| v35 | Same-minute MNQ+M2K breadth breakout | `FAILED_2023_DISCOVERY` | 425 trades; two-tick net -$1,966.25. |
| v36 | MES overnight inventory continuation/rejection | `FAMILY_FAIL_DISCOVERY` | Best cell: 14 trades, +$479.25; rejected below 80 trades. |
| v37 | MNQ+M2K overnight leader agreement | `FAMILY_FAIL_DISCOVERY` | Best cell: 8 trades, +$308.50; rejected below 80 trades. |
| v38 | MES CLV volume-pressure/price-response proxy | `FAMILY_FAIL_DISCOVERY` | Best cell: 93 trades, +$174.75, PF 1.05, average +$1.88; rejected. |

No thresholds, exits, sample gates, or cost assumptions were relaxed after any
result was observed.

## Data boundary

The multiyear cached research data contains only `ohlcv-1m`. It does not contain
historical bid/ask, aggressor-side trades, market depth, or opening-auction data.
Existing forward exact-contract MES level-one snapshots cover only 2026-09-22
through 2026-09-25, which is too short for a credible historical or forward
verdict.

That boundary now matters more than another OHLCV-derived feature. v33-v38
tested cross-market response, leader breakouts, overnight inventory, breadth,
and a close-location volume proxy without finding a qualifying MES family.

## Recommended next step

Use the configured Render Databento key only to call `metadata.get_cost` for
`MES.FUT` 2023-2025 `trades` and `mbp-1` data. The metadata estimate is free and
would establish the exact dollar cost of adding real aggressor-trade and
best-bid/offer evidence.

Downloads remain disabled. Any data download or spend requires owner approval
and an explicit dollar cap. No live, broker, paper, Render-service, scheduler,
or other production change is authorized.
