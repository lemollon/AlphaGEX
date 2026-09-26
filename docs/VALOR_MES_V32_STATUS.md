# VALOR MES v32 research status

- **Current version:** v32
- **Current stage:** compact router audit completed; isolated Render runner
  manually suspended
- **Research environment:** cached Postgres MES development data only
- **Live/production impact:** none; no trader, broker, sizing, routing, scheduler,
  or root Render configuration changed
- **Execution boundary:** trade-print proxy; the one-tick planning case is
  unverified and is not labeled realistic
- **2026 status:** untouched
- **Verification:** 11 focused v31/v32 tests pass, including prior-date-only
  thresholds, same-day batching, warmup, global non-overlap, cost accounting,
  and autorun isolation; Python compilation passes; persisted study status is
  `completed`
- **Verdict:** no winning architecture. Do not build another OHLCV-only MES
  router, do not open 2026, and do not change production.
- **Next action:** acquire executable MES quote/fill calibration and genuinely
  new microstructure predictors before another strategy iteration

## Completed annual audit

The one-tick case is an unverified planning proxy, not realistic execution.

| Variant | Year | Trades | Trades/session | Raw P&L | Planning P&L | Planning PF | Planning avg | Planning MDD | Severe P&L |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| combined baseline | 2023 | 1,209 | 4.875 | $2,717.50 | -$3,932.00 | 0.855 | -$3.25 | $5,601.25 | -$12,999.50 |
| combined baseline | 2024 | 1,229 | 4.936 | $1,422.50 | -$5,337.00 | 0.822 | -$4.34 | $5,389.00 | -$14,554.50 |
| combined baseline | 2025 | 1,217 | 4.927 | -$1,108.75 | -$7,802.25 | 0.818 | -$6.41 | $7,969.25 | -$16,929.75 |
| ATR low-tercile exclusion | 2023 | 903 | 3.641 | $3,082.50 | -$1,884.00 | 0.910 | -$2.09 | $3,729.50 | -$8,656.50 |
| ATR low-tercile exclusion | 2024 | 926 | 3.719 | $1,478.75 | -$3,614.25 | 0.853 | -$3.90 | $4,059.75 | -$10,559.25 |
| ATR low-tercile exclusion | 2025 | 977 | 3.955 | -$1,921.25 | -$7,294.75 | 0.805 | -$7.47 | $8,509.25 | -$14,622.25 |
| ATR shadow router | 2023 | 137 | 0.552 | $235.00 | -$518.50 | 0.827 | -$3.78 | $1,086.75 | -$1,546.00 |
| ATR shadow router | 2024 | 12 | 0.048 | -$163.75 | -$229.75 | 0.645 | -$19.15 | $496.50 | -$319.75 |
| ATR shadow router | 2025 | 0 | 0.000 | $0.00 | $0.00 | n/a | n/a | $0.00 | $0.00 |

No variant was positive in all three development years under fees-only, the
one-tick planning case, or severe execution. The shadow router also failed the
activity requirement.

## Worst repeated loss evidence

- The largest planning cluster was eight 120-minute opening-morning
  mean-reversion losses from December 8-17, 2025, totaling -$1,080.25.
- The same cluster lost -$1,140.25 under severe execution.
- Low ATR was repeatably associated with losses, but excluding the low tercile
  did not rescue 2023-2025 net expectancy.

## Evidence boundary and required new information

- The current cached minute OHLCV-derived entry, horizon, and regime features
  are insufficient. v17-v32 now cover fixed continuation, event engines and
  their inversions, dense direction models, raw horizon/time maps, and a causal
  ATR router without producing an all-year cost-adjusted candidate.
- Execution calibration is also insufficient: 118 quote changes and zero
  historical fill/fee rows cannot establish realistic MES slippage.
- Another iteration requires materially new data, specifically historical MES
  executable bid/ask quotes with enough coverage around signal and exit times,
  actual broker fills and fees, and synchronized trade/depth features such as
  aggressor volume and order-book imbalance. Parameter tuning on the existing
  OHLCV feature set is not justified.

## Frozen scope

The runner evaluates only `combined_baseline`,
`atr_low_tercile_exclusion`, and `atr_tercile_shadow_router` on the four frozen
v31 raw-gross survivors. ATR thresholds and shadow performance are prior-date
only, same-day updates are batched, and the selected portfolio holds at most one
MES position at a time.
