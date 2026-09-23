# MES historical GEX filter results - September 23, 2026

## Verified outcome

Study `valor-mes-gex-overlay-v5-20260923` completed at **2026-09-23 14:32:15.474102 UTC**. Postgres reports 144 summary rows for 2023 and 2024 and **zero numerical development passes**. No MES strategy was promoted or activated. MNQ trading code, sizing, balances and live-mode settings were not changed. No new vendor downloads or broker API calls were made by this study.

The research deployment `dep-dapu4efavr4c73f2srj0`, commit `d44734c98c5c423e8ed84b013327e02d4042dffe`, became live at 14:32:17 UTC. It changed one research startup import in backend/main.py and added the analysis script, tests and protocol. The API restarted; this was not zero operational impact. The newer database thread-pool stability fix was preserved. No SpreadWorks or IronForge source was edited.

Source of results: read-only queries against `public.valor_mes_gex_v5_state` and `public.valor_mes_gex_v5_results` in AlphaGEX Postgres. Those tables preserve complete summaries, compressed retained-trade evidence, the GEX source-date snapshots and hashes. Source SHA256: `29631d32438470918e6155f1c8a965646792ced0fb06373025527af9efe032af`.

## What was tested

The three saved MES v4 entry/exit paths were held fixed: opening-range breakout acceptance followed by a retest, a reclaim following a sweep of the prior session's extreme, and an overnight gap-fill attempt after opening-range failure. A blocked trade was not replaced by a later opportunity. This is a paired filter analysis of the original cohort, not full strategy regeneration.

GEX filters were all matched trades, positive-only, and negative-only. SPX ORATS-derived daily GEX and the separate SPY baseline daily proxy were tested separately. Primary timing uses the previous observed source session, strictly before the Chicago signal date; the sensitivity uses two previous source sessions. The code never substitutes daily GEX for a minute-level archive and does not read 2025 or 2026 outcomes.

Each source has 250 daily observations in 2023 and 252 in 2024. The sources disagree in sign on 83 of the 250 shared 2023 dates and 49 of the 252 shared 2024 dates; they are not interchangeable. These are reconstructed daily proxies with unverified as-published vintages, not measured dealer inventories. Source methods and timing limitations are in `docs/VALOR_MES_GEX_V5_PROTOCOL.md`.

All dollar values below are **one-MES-contract simulated closed-trade net P&L**. Baseline assumes two adverse ticks per side plus a $3 round-trip fee, or $8 total friction per round trip. Stress assumes four adverse ticks per side plus the same $3 fee, or $13. The fee is an assumption, not a broker-verified charge. Both cost scenarios use identical raw paths. Drawdown below is closed-trade drawdown, not account/intratrade drawdown. Positions interrupted by missing minutes or contract changes remain separately censored and excluded from realized P&L.

## Primary lag: opening-range acceptance and retest

| GEX source/filter | 2023 closed trades | 2023 baseline net | 2023 stressed net | 2024 closed trades | 2024 baseline net | 2024 stressed net |
|---|---:|---:|---:|---:|---:|---:|
| SPX, all matched | 169 | -1432.00 | -2277.00 | 180 | -106.25 | -1006.25 |
| SPX, positive only | 90 | -660.00 | -1110.00 | 116 | 40.75 | -539.25 |
| SPX, negative only | 79 | -772.00 | -1167.00 | 64 | -147.00 | -467.00 |
| SPY, all matched | 170 | -1493.75 | -2343.75 | 180 | -106.25 | -1006.25 |
| SPY, positive only | 42 | -178.50 | -388.50 | 92 | -62.25 | -522.25 |
| SPY, negative only | 128 | -1315.25 | -1955.25 | 88 | -44.00 | -484.00 |

SPX has one unmatched closed trade in 2023, which is excluded from its matched baseline as well as its filtered groups. SPY matches all closed trades. There is one censored 2023 position: in SPX positive-only and SPY negative-only. There are no censored positions for this setup in 2024.

Interpretation: positive-only filtering reduces some losses but does not create a consistently profitable setup. With the SPY proxy, stressed P&L improves from -3350.00 unfiltered to -910.75 positive-only over both years, but trading also falls from 350 to 134 closed trades. Expected stressed net per trade remains negative in each year (-9.25 in 2023 and -5.676630 in 2024). A smaller total loss is not proof of a profitable edge.

## Primary lag: reclaim after a prior-session extreme sweep

| GEX source/filter | 2023 closed trades | 2023 baseline net | 2023 stressed net | 2024 closed trades | 2024 baseline net | 2024 stressed net |
|---|---:|---:|---:|---:|---:|---:|
| Either source, all matched | 108 | -1250.25 | -1790.25 | 89 | -138.25 | -583.25 |
| SPX, positive only | 57 | -759.75 | -1044.75 | 62 | 606.50 | 296.50 |
| SPX, negative only | 51 | -490.50 | -745.50 | 27 | -744.75 | -879.75 |
| SPY, positive only | 26 | -403.00 | -533.00 | 48 | 532.25 | 292.25 |
| SPY, negative only | 82 | -847.25 | -1257.25 | 41 | -670.50 | -875.50 |

All closed trades have prior GEX. Each positive-only 2024 variant retains one censored position: 1/63 = 1.5873% for SPX and 1/49 = 2.0408% for SPY. These exceed the frozen 1% numerical threshold; the raw baseline itself has only 89 closed 2024 trades, so a filter cannot meet the 100-trades-per-year requirement. Nevertheless, the negative 2023 results independently prevent acceptance.

The positive-only 2024 result is the clearest diagnostic improvement, not a promotion:

| Source | 2023 stressed PF | 2024 stressed PF | 2024 stressed average trade | 2024 closed-trade drawdown | 2024 profitable months |
|---|---:|---:|---:|---:|---:|
| SPX positive | 0.411326 | 1.209689 | 4.782258 | 378.50 | 5 of 12 |
| SPY positive | 0.286479 | 1.302067 | 6.088542 | 273.75 | 5 of 12 |

2024 June-August stressed net totals are 607.75 for SPX and 561.00 for SPY, larger than their respective full-year profits of 296.50 and 292.25. Other months collectively lost money. In 2023 SPX positive had two profitable months and ten losing months; SPY positive had one profitable, seven losing and four zero-trade months.

## Extra-session delay sensitivity

Keeping the same positive-only prior-extreme rule but using two-session-old GEX gives:

| Source | 2023 closed trades | 2023 stressed net | 2024 closed trades | 2024 stressed net | 2024 stressed PF |
|---|---:|---:|---:|---:|---:|
| SPX | 58 | -1157.75 | 54 | -210.75 | 0.851244 |
| SPY | 23 | -587.75 | 41 | -208.00 | 0.801337 |

The 2024 gain does not survive this timing sensitivity. This is evidence of sensitivity, not proof that the primary-lag study contains lookahead. A date lag alone cannot verify the original publication time or historical revisions.

## Gap-fill setup

The baseline has only five closed trades in 2023 and one in 2024. Primary positive-only filters leave four trades then zero (SPX) or one then zero (SPY). There is no useful two-year sample. One two-session-lag SPY positive variant has +17.00 in 2023 and +22.00 in 2024 under stress, but this is **one trade per year**, with no finite profit factor because neither trade loses. It fails the sample-size/PF gate and is not evidence of an investable strategy.

## Decision and limitations

No filter passed the preregistered numerical gate: stressed net positive in each development year, stressed PF >=1.10, at least 100 closed trades in each year, and at most 1% censored. These screens are 12 source/setup/sign combinations with timing and cost sensitivities, not 144 independent discoveries. Passing numbers alone would still not establish live readiness.

The supported conclusion is narrow: **a positive/negative daily GEX filter does not robustly rescue these frozen MES setups in the two reused development years**. It is not a rejection of MES, all gamma-based strategies, intraday GEX changes, or a newly generated state-dependent strategy. No 2025 chronological extension or 2026 outcome test was run for v5. Neither 2025 nor all of 2026 should be called untouched in the broader research program.

MNQ remains preserved as requested, not certified profitable: its old +7627 screening result had known overlap, same-close-entry and rollover problems. This v5 study makes no new MNQ inference.

A more discriminating next experiment would change the MES entry hypothesis rather than keep adding sign filters to these losing entries, and separately validate the timestamped intraday GEX/futures overlap. Any such follow-on must be recorded as a new experiment, keep a price-only comparator, hold costs/position constraints fixed, and preserve a genuinely unseen forward period. That follow-on is not claimed to have run here.

## Reproduction query

```sql
SELECT year, x
FROM public.valor_mes_gex_v5_results
CROSS JOIN LATERAL jsonb_array_elements(summary) x
WHERE study_id = 'valor-mes-gex-overlay-v5-20260923'
ORDER BY year, x->>'spec', x->>'source', x->>'filter',
         (x->>'lag_sessions')::int, (x->>'cost_ticks_each_side')::int;
```

Twenty-two synthetic unit tests passed before deployment; they are code checks, not profitability evidence. All detailed results and snapshots are in the Postgres study tables. This document is stored on a research-only results branch to avoid another production restart merely to publish findings.
