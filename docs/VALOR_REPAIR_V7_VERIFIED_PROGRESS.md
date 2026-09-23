# Verified VALOR repair progress - September 23, 2026

Checkpoint: 17:25:45 UTC / 12:25:45 America/Chicago. Source: fresh read-only queries against Render alphagex-db, public.valor_repair_v7_runs and public.valor_repair_v7_jobs. This document is on the research branch only; it does not redeploy the API.

## Actual deployed change

Main deployed commit 61da16ef38a45bdb83c0815e84d5b582cc38a0fc, live since 17:11:22 UTC. Coordinator SHA256: b877a44daf9a43c8147e23ce312186440fa136341f53f7d2af3a2350c139d640.

The active research launcher uses scripts.valor_research_repair_v7 rather than the old v2-v6 run functions. The pure evaluators are kept pinned for exact reproductions; old archived runners have not each been edited. New results require matching source/data/config/cost/runtime fingerprints, complete scenario coverage, artifact checksums, summary/evidence agreement and applicable ledger accounting. No completed status bypasses those checks.

The original signed-zero integration failure remains preserved. PostgreSQL JSONB normalized -0.0 to 0.0; canonicalization now treats those economic zeros identically without rounding nonzero values or ignoring actual data changes. The corrected run passed that integration point. Tests executed: 32 initial local regression tests plus seven targeted normalization tests. These are not proof of profitability.

## Current execution - not yet complete

Active run: valor-all-affected-repair-v7-20260923-de7fe6332a0e3c82a2e0.

Status: evaluating. Stored: 51/63 family/contract/year jobs and 2612/3276 scenario summaries. MES, MNQ, Russell 2000/M2K and gold jobs are complete. Natural gas has completed 2023 and 2024 and is evaluating its 2025 jobs. Crude oil remains queued in the same run. All years 2023-2025 are diagnostic/reused data, not blind holdouts. MNG does not have a full 2023 history; its cache begins in November.

The new coordinator recomputed 256 comparable old scenarios at this checkpoint. All 256 match prior net P&L and trade counts. This supports reproducibility for those scenarios, not the hypothesis that stale cached results caused those losses. There are zero artifact-hash mismatches in the stored jobs.

All 144 comparable 2023/2024 daily-GEX summaries also match the previous totals after candidate orders were regenerated from raw MES bars. Daily sign is constant within a date, so processing all candidate orders before filtering need not change the eventual trade. These GEX sources remain separate reconstructed daily proxies with unverified publication vintages, not minute-by-minute GEX.

Coverage: v2 contract hypotheses for all six futures; v3 exit specialists for all six; MES v4 rebuild; regenerated MES v5 GEX filters; MES v6 session hypotheses and controls; and the initial five-rule screen with changed next-open, non-overlapping, exact-clock and roll-aware execution. No previously failed development gate skips 2025 diagnostic testing.

## Fresh MES results

One-contract modeled results. Baseline assumes two adverse ticks each side plus $3 round-trip fees, $8 total for MES. Stress assumes four ticks each side plus the same fee, $13 total. Fees are not broker-verified. Unknown outcomes are excluded from realized P&L and explicitly reported.

| MES morning continuation | Closed trades | Baseline net | Stress net | Unresolved |
|---|---:|---:|---:|---:|
| 2023 | 169 | -32.00 | -877.00 | 3 |
| 2024 | 166 | -28.00 | -858.00 | 3 |
| 2025 | 181 | -620.50 | -1525.50 | 4 |
| Total | 516 | -680.50 | -3260.50 | 10 |

The old 2023/24 results were recomputed, not copied. The 2025 result was previously skipped and is now evaluated. This does not make 2025 a blind holdout.

Other new MES 2025 baseline/stress results:
- Opening acceptance/retest: -2971.50 / -3861.50; 178 closed, 3 unresolved.
- Prior-day extreme reclaim: +874.75 / +359.75; 103 closed, 0 unresolved. Prior 2023 and 2024 losses leave its three-year baseline total -513.75 and stressed total -2013.75.
- Gap fill after opening failure: +17.00 / +12.00 on just one trade, inadequate evidence by itself.
- Afternoon continuation: -1473.25 / -2118.25; 129 closed, 0 unresolved.
- Closing continuation: -726.00 / -1161.00; 87 closed, 0 unresolved.

These are separate strategies, not a combined account or compounded portfolio. No MES strategy has been activated.

## Additional limitations kept visible

The corrected initial long-hold screen still generates many unresolved positions where the planned holding interval crosses an unobserved segment or market closure. Example: MES 240-minute RTH 30-minute momentum has 744 closed and 774 unresolved observations. Its positive +1411.75 baseline aggregate must not be advertised as valid performance. Session-calendar/early-close treatment and unresolved outcomes need further execution validation.

The changed initial MNQ breakout-30m, RTH, 120-minute version yields baseline +445.50, -4421.50, -471.50 in 2023/24/25 with 60/75/67 unresolved observations. Execution and costs differ from the initial screen, so the difference is not solely a cache effect. It does not validate the old +7627 claim. Production MNQ settings are not changed by this repair.

A fresh byte-check verified all 18 raw futures cache files, 83,727,046 bytes total, with zero checksum mismatches. This proves stored-byte consistency, not original exchange accuracy. The MES nominal intraday gap audit finds two one-minute gaps in 2023 and none in 2024 or 2025. Unknown intervals are not forward-filled or assigned invented outcomes.

The latest stored broker calibration has zero transaction-history rows, no observed fee rates and broker_slippage_calibrated=false. Quote-level fills and actual costs remain unverified. No cost assumptions were made friendlier to manufacture a winner.

At the 2446-summary checkpoint, a separate read-only arithmetic check found zero monthly-total mismatches and zero cost-difference/count errors across 1145 paired cost scenarios outside v2. V2 preserves its original fill-dependent brackets for direct reproduction and is intentionally excluded from that same-path friction assertion.

## Operational boundary

No new paid data request, vendor download, broker call, production strategy change, sizing change, balance reset or live activation was made by the repair. Its one startup-import change did cause a normal API restart. Another agent's existing GEX-expiration correction was preserved. Raw data and prior result tables remain intact.

The completion watch was updated to the new run and ignores older completed studies and the superseded signed-zero failure. Full completion requires 63 validated jobs, not this partial checkpoint. Even completion is not live-trading certification.
