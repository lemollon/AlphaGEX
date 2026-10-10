# VALOR corrected results and cache-only exit specialists

## Completed v2 study

`valor-contract-v2-20260923` finished at 2026-09-23 11:53:52 UTC with 18 ticker-year records and 216 scenario summaries. No tested specification had positive baseline modeled net P&L in either development year (2023 or 2024); MNG has no closed trades in 2023 for these variants. These configurations have not earned promotion.

For diagnostics only, select each ticker's least-negative combined 2023-2024 baseline candidate, then display its previously seen 2025 result:

| Contract | Candidate, 120-minute maximum | 2023 net | 2024 net | 2025 net | Baseline sum | Stress sum | Baseline closed / censored |
|---|---|---:|---:|---:|---:|---:|---:|
| MES | Opening-range rejection | -3922.50 | -3919.50 | -6243.25 | -14085.25 | -22575.25 | 1488 / 7 |
| MNQ | Trend pullback | -236.50 | -2827.50 | -6554.00 | -9618.00 | -15577.00 | 3536 / 23 |
| M2K (RTY) | Opening-range rejection | -994.50 | -3871.50 | -2969.50 | -7835.50 | -10823.50 | 1328 / 32 |
| MGC | Trend-confirmed breakout | -4345.00 | -7270.00 | -8184.00 | -19799.00 | -32181.00 | 2992 / 16 |
| MNG (NG) | Trend-confirmed breakout | No closed trades | -88.00 | -1320.00 | -1408.00 | -2509.00 | 228 / 127 |
| MCL (CL) | Volatility-expansion breakout | -3804.00 | -2753.00 | -3510.00 | -10067.00 | -16262.00 | 1632 / 33 |

All dollar figures are one-contract modeled closed-trade results, not portfolio returns. Baseline uses two adverse ticks per side plus assumed $3 round-trip fees; stress uses four ticks per side plus those fees. V2 stress can change trade paths because levels depend on fill prices. Censored positions are excluded from realized P&L. Drawdown is closed-trade drawdown only.

MNG starts November 2023 and has sparse data; the candidate has 12 closed / 7 censored positions in 2024 and 216 / 120 in 2025. These figures cannot settle natural-gas strategy profitability. Research uses $1000/price point and $1/.001 tick. No production-accounting or historical-paper-ledger changes are made.

The initial MNQ +$7627 result was an unvalidated screen with overlap, same-close-entry and rollover-handling issues; it is not a validated strategy result. V2 also tests different specifications, so its losses are not an apples-to-apples reproduction. Both are futures-native: neither joins historical GEX. V2's different entry families still shared a 4 one-minute ATR stop and 2R target.

Development cost attribution for the same v2 diagnostic paths gives raw price P&L / modeled friction and fees: MES $270 / $8112; MNQ $8891 / $11955; M2K -$506 / $4360; MGC $2420 / $14035; MNG -$4 / $84; MCL $1150 / $7707. This is algebraic attribution of the existing paths, not a new zero-cost strategy replay.

## Frozen v3 study

`valor-exit-specialists-v3-20260923` reads existing checksum-verified Postgres caches only. No new vendor download or broker API is called. Twelve predefined hypotheses change entry gates, frequency and exits jointly; they are not a single-factor causal experiment.

| Contract | Candidate A | Candidate B |
|---|---|---|
| MES | Opening-range rejection to midpoint, 90 min max | Low-volatility reversal to bar-based VWAP, 60 min max |
| MNQ | Trend pullback with trailing exit, 180 min max | Trend breakout with 3R target, 120 min max |
| M2K | Opening-range rejection to midpoint, 90 min max | Range re-entry to midpoint, 60 min max |
| MGC | Trend pullback with trailing exit, 240 min max | Trend breakout with 3R target, 180 min max |
| MNG | Volatility-expansion runner, 180 min max | Trend breakout with 3R target, 120 min max |
| MCL | Opening-range breakout runner, 120 min max | Volatility-expansion breakout with 3R target, 180 min max |

Range exits use observed structure. Trend initial risk uses completed five-minute ATR. Daytime session caps remain; this is not overnight research. Maximum two attempts per local date and 15-minute cooldown. Range/trend directional-efficiency filters are frozen at .35 maximum / .30 minimum. Reversion targets require 1.25 times planned risk and five times the baseline cost allowance. All thresholds are frozen before v3 results.

Eligibility, risk and initial levels use the completed signal bar, never the future opening price. Entry is the next contiguous minute open. An entry gap outside the predetermined bracket is flattened and charged both sides, not selectively skipped. Normal and stressed costs use identical raw paths. Trailing changes become active next minute. Stop-first handles ambiguous bars. Missing-data/roll positions are censored and later segments restart flat for research; this is not complete executable-account simulation.

Selection uses only 2023 and 2024: positive stressed net in EACH year, at least 100 closed trades in EACH year, and at most 1% censored in EACH year. Among passers select the highest minimum yearly stressed net/closed-trade-drawdown ratio with deterministic tie-breaks. Only a passing frozen candidate gets the already-seen 2025 chronological check. Otherwise 2025 is marked NOT TESTED, not zero P&L.

Neither 2025 nor all of 2026 is untouched; both were partly inspected earlier. Repeated 2023-24 development remains subject to overfitting. A genuinely unseen forward period, GEX attribution, quote-level execution, verified broker fees, margin and portfolio risk remain separate validation work. Passing this gate is not live readiness.

## Implementation controls and tests

Study tables: valor_research_v3_state, valor_research_v3_results, valor_research_v3_selections. The worker shares the v2 advisory lock, validates cache hashes and the pinned v2 source hash, and refuses to mix source versions. It resumes completed development jobs and does not rerun a completed study.

Twenty local synthetic tests passed for the exact source blob 34ede39000541d0eacdc30fe2598a7663ba65186. They cover next-bar entries, non-overlap, cooldown/daily limits, missing data, stop-first, adverse gaps, MNG math, identical cost paths, future-perturbation invariance, complete five-minute/opening ranges, trailing causality, selection ignoring 2025, and order decisions unaffected by future opens. Unit tests are not profitability or full production-integration tests.

The research startup import changes through the normal Render deployment; this may restart the API. No trading rules, account balances, live-mode settings, SpreadWorks or IronForge source are changed. Existing v2 results and prior research remain preserved.

See docs/VALOR_RESEARCH_V2_CORRECTION.md for vendor bar conventions and the original correction.
