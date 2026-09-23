# MES v6 completed session-study results

## Decision and verified completion

Study `valor-mes-session-v6-20260923` completed on September 23, 2026 at 15:32:54.206465 UTC (10:32:54 AM America/Chicago). No candidate passed the frozen development gate. No new MES trading strategy was activated. MNQ trading logic, sizing, account balances and mode settings were not changed by this study.

The closest candidate in this specific three-hypothesis study is morning continuation, but it remains negative after baseline costs, deteriorates under stressed costs, and exceeds the unresolved-observation limit. It is a research lead, not a validated profitable strategy.

Sources: fresh read-only queries of `public.valor_mes_session_v6_state` and `public.valor_mes_session_v6_results` in the AlphaGEX Render Postgres database. Implementation commit: `59f963f23f4d8771bb8ab6cbcf092529b646f7c3`. Source SHA256: `d3de6fbd29767a0c89c3816ffbbbcdb17f188952f9cecd75a2f8dea6892aceb0`. The frozen design is in `docs/VALOR_MES_SESSION_V6_PROTOCOL.md`.

## Data, costs and interpretation

The worker evaluated 353,177 cached MES one-minute bars for 2023 and 354,823 for 2024: 708,000 bars in total. Each year has 18 summaries: three hypotheses times signal/long/short variants times two cost scenarios. Source bars retain exact contract identifiers, and the cache checksums are verified before use. There were no new vendor data requests.

All results are one-contract modeled CLOSED-trade P&L. They are not account returns, a compounded portfolio, or quote-level executable fills. The three hypotheses are evaluated separately; summing their results would not constitute a portfolio test.

Baseline costs: two adverse ticks per side plus an assumed $3 round-trip fee = $8 per MES round trip. Stress: four adverse ticks per side plus the same assumed fee = $13. MES is modeled at $5 per index point and $1.25 per 0.25-point tick. Broker fees and realized slippage have not been verified. Raw paths and entry decisions are identical between the two cost scenarios.

Signals use completed price context. Entries occur at the following minute's open. Scheduled exits use a predetermined future minute's OPEN, without examining that bar's later high or low. An adverse price gap through a stop fills at the observed open. This still idealizes execution at bar boundaries. Missing entry/exit bars, interrupted paths and contract changes produce unresolved observations, not zero-profit trades. They remain excluded from realized P&L. Their precise causes have not been independently classified in this review.

## Three frozen hypotheses

- Morning continuation: entry 09:00 Central, scheduled exit 12:00. Direction follows the first 08:30-09:00 move, requiring displacement of at least 25% of the opening range and price on the matching side of the bar-derived VWAP.
- Afternoon continuation: entry 13:00, scheduled exit 14:55. Direction from cash open must agree with the latest 30-minute move and price versus bar-derived VWAP.
- Closing continuation: entry 14:30, scheduled exit 14:55. The first 30-minute direction must agree with the latest 30-minute move and price versus bar-derived VWAP.

Each has at most one daily attempt and an initial stop one first-30-minute range from the completed signal reference, with a four-point floor. No profit target, trailing stop, SAR, compounding or cost-free breakeven. These are price-only hypotheses; GEX is not used in v6.

## Actual signal results

| Hypothesis | Year | Decisions | Closed trades | Unresolved | Baseline net | Stress net | Baseline PF | Stress PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Morning continuation | 2023 | 172 | 169 | 3 | -32.00 | -877.00 | 0.994666 | 0.863793 |
| Morning continuation | 2024 | 169 | 166 | 3 | -28.00 | -858.00 | 0.995748 | 0.878689 |
| Afternoon continuation | 2023 | 131 | 131 | 0 | -300.50 | -955.50 | 0.905925 | 0.731733 |
| Afternoon continuation | 2024 | 125 | 125 | 0 | -885.00 | -1510.00 | 0.778279 | 0.651973 |
| Closing continuation | 2023 | 83 | 83 | 0 | -884.00 | -1299.00 | 0.437480 | 0.299258 |
| Closing continuation | 2024 | 85 | 85 | 0 | -1046.25 | -1471.25 | 0.463048 | 0.337051 |

| Hypothesis | Combined closed trades | Combined baseline net | Combined stress net |
|---|---:|---:|---:|
| Morning continuation | 335 | -60.00 | -1735.00 |
| Afternoon continuation | 256 | -1185.50 | -2465.50 |
| Closing continuation | 168 | -1930.25 | -2770.25 |

Pooled morning profit factor is 0.995233 at baseline and 0.871591 under stress, computed by pooling gross wins and losses, not averaging annual profit factors.

## What is useful about the morning result, and what still fails

On the 335 resolved morning paths, raw price P&L totals $2,620. Baseline modeled costs total $2,680, leaving -$60. Average raw gain is approximately $7.82 per closed trade, below the $8 baseline allowance. This is algebraic attribution of those same paths, not an independent no-cost strategy simulation and not evidence that cheaper real-world fills are available.

There were six unresolved morning observations out of 341 decisions: 1.76% combined. Individually, the fractions are 3/172 = 1.74% in 2023 and 3/169 = 1.78% in 2024. Both exceed the fixed 1% limit. Their outcomes could materially change the near-zero baseline total, so the -$60 should not be treated as complete account P&L.

Morning baseline long/short breakdown:

| Year | Long trades | Long net | Short trades | Short net |
|---|---:|---:|---:|---:|
| 2023 | 109 | 70.50 | 60 | -102.50 |
| 2024 | 91 | 454.50 | 75 | -482.50 |

Under stress, the long subset is -$474.50 in 2023 and -$0.50 in 2024; short subsets are -$402.50 and -$857.50. These are post hoc direction diagnostics, not a newly selected long-only strategy. They do not justify turning off shorts and claiming a validated improvement.

Both morning baseline years had five positive months out of twelve. Removing each year's best five trades gives -$1,138.25 for 2023 and -$1,411.75 for 2024 at baseline. These are concentration diagnostics, not proposed trade-exclusion rules.

## Matched-day controls for morning continuation

Each control uses the SAME eligible entry dates and initial risk width as the signal, but a fixed long or short direction. Different stops can produce different exit paths and unresolved counts. The comparison is descriptive, not a significance test or proof of causal value added.

| Year | Variant | Closed | Unresolved | Baseline net | Stress net |
|---|---|---:|---:|---:|---:|
| 2023 | Signal | 169 | 3 | -32.00 | -877.00 |
| 2023 | Always long on matched dates | 169 | 3 | -153.25 | -998.25 |
| 2023 | Always short on matched dates | 168 | 4 | -1012.75 | -1852.75 |
| 2024 | Signal | 166 | 3 | -28.00 | -858.00 |
| 2024 | Always long on matched dates | 167 | 2 | -1103.50 | -1938.50 |
| 2024 | Always short on matched dates | 166 | 3 | -1858.00 | -2688.00 |

Morning beats both matched controls in both years on the stored closed-trade totals. It still loses against doing nothing, whose modeled net is zero. Relative improvement is not absolute profitability.

## Risk diagnostics

| Hypothesis | Year | Baseline closed-trade drawdown | Stress closed-trade drawdown | Baseline resolved minute-mark drawdown | Stress resolved minute-mark drawdown |
|---|---:|---:|---:|---:|---:|
| Morning | 2023 | 880.50 | 1205.25 | 999.75 | 1272.00 |
| Morning | 2024 | 937.75 | 1426.25 | 1059.25 | 1495.50 |
| Afternoon | 2023 | 775.25 | 1065.25 | 826.25 | 1126.25 |
| Afternoon | 2024 | 1049.00 | 1621.50 | 1122.25 | 1679.00 |
| Closing | 2023 | 950.00 | 1350.00 | 982.00 | 1377.00 |
| Closing | 2024 | 1094.75 | 1504.50 | 1131.50 | 1508.25 |

Minute-mark drawdown marks resolved trades at minute closes using modeled liquidation friction. It is not full intrabar account drawdown, excludes unresolved paths and does not incorporate broker margin or portfolio constraints. No combined multi-year drawdown has been calculated in this review. Morning baseline worst closed trades are -$239.25 in 2023 and -$211.75 in 2024.

## Frozen gate and 2025 status

Each of 2023 and 2024 must independently have positive stressed net, stress PF at least 1.10, at least 100 closed trades, and at most 1% unresolved. A signal also must beat both matched controls in both years. Only a passing frozen hypothesis advances.

All three fail the numerical gate. Morning alone beats both directional controls, but that does not waive the numerical or completeness requirements. The selected specification is null. The stored 2025 record has phase `not_tested`, an empty summary and reason `no_development_candidate_passed`. It is NOT zero P&L or an unfinished job.

2023/24 have been repeatedly used in development. 2025 and parts of 2026 were examined in earlier research. No whole-year blind-holdout claim is warranted. No claim of live readiness is made for MES or the preserved MNQ configuration.

## Verification and operational scope

Twenty-nine local synthetic tests passed before deployment. They cover next-bar execution, source validation, future-data invariance, missing bars and contract switches, controls, adverse gaps, cost-path consistency and selection excluding 2025. Unit tests do not establish profitability.

A fresh independent read-only summary audit after completion checked 18 base/stress pairs and found zero cost-difference errors, zero path-count errors, zero closed-plus-unresolved versus decision-count errors, and zero long-plus-short P&L accounting errors. This reconciles the stored aggregates; it is not an independent rerun from raw bars or a quote-level fill audit.

Deployment `dep-dapv0vbm8hqs73aqqpkg` was confirmed live by Render at 15:32:50 UTC. The implementation added a cache-only script, tests and protocol, and changed one launcher import in `backend/main.py`. That restarted the API. It did not replace production trading rules or change MNQ settings. The research runs in a separate low-priority process with capped numerical threads and a shared database advisory lock. This results-document commit is on the research branch only and causes no additional main deployment.

## Next evidence needed, not a claim of work already completed

Before calling morning continuation viable, classify and resolve the six incomplete observations without deleting adverse outcomes, verify actual broker commission and realistic execution-friction distributions, and then test a frozen hypothesis on genuinely unexamined data. Do not lower costs simply to make a near-breakeven line turn green. Further parameter searches on the same years would compound selection bias.

The preceding daily-GEX-filter study also had zero numerical passes, but v6 is not a test of actual timestamped intraday GEX. It would be incorrect to generalize these findings into proof that all MES strategies or all GEX applications fail.
