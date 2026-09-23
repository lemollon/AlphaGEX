# MES historical GEX filter results: completed-study review

## Decision

No MES specification passes the frozen v5 development gate. Preserve the study as negative evidence; do not activate a new MES strategy or modify MNQ. The study completed on September 23, 2026 at 14:32:15 UTC (09:32:15 America/Chicago), with 144 unique scenario summaries and zero numerical passes.

This review reads the completed database results. Its commits contain research documentation and read-only audit SQL only. It does not change main, deploy the API, alter broker/account settings, place orders, or download vendor data. The earlier v5 deployment did restart the API; this review does not claim the entire preceding workflow had zero operational impact.

## Source and scope

Source database: Render alphagex-db, public.valor_mes_gex_v5_state and public.valor_mes_gex_v5_results. Study ID: valor-mes-gex-overlay-v5-20260923. Source SHA256: 29631d32438470918e6155f1c8a965646792ced0fb06373025527af9efe032af. Base study: valor-mes-rebuild-v4-20260923; pinned base source SHA256: a89b8b6eb6b0cf51896672f9238c09e2e8030bbc72ea0f366bd50d8b2dc7ea3c.

The baseline is the saved, fixed 2023/2024 MES trade cohort. Entries, stops, targets, raw price paths and sizing are unchanged. GEX filters remove trades without substituting later entries. Therefore this is an exploratory paired-cohort filter analysis, not a fully regenerated strategy backtest.

Two separate lagged daily proxies were tested: SPX_ORATS_7DTE_PROXY (SPX option gamma/open-interest, default 0-7 DTE construction) and SPY_BASELINE_PROXY (seeded reconstructed SPY baseline). They are not measured dealer inventory, not interchangeable series, and not a three-year minute-GEX archive. Same-day end-of-day values are excluded. Primary lag is one prior observed source session, maximum four calendar days; sensitivity lag is two sessions, maximum seven calendar days. Original release times and revision-free source vintages remain unverified.

This stage uses 2023 and 2024 only. It reads no 2025 or 2026 outcomes. That does not make those entire years untouched: they were partly examined in earlier research.

All dollar figures below are modeled closed-trade P&L for one MES contract, not account returns or compounding. Base friction: two adverse ticks per side plus an assumed $3 round-trip fee, totaling $8. Stress: four ticks per side plus the same assumed fee, totaling $13. The fee is not broker-verified. Each MES tick is 0.25 points and $1.25; each point is $5. CME source checked during review: https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.html .

## Primary-lag results, including the matched baseline

SPX and SPY in the following tables refer to the separately defined GEX proxies, not the instrument traded. All trades are MES. N counts closed trades. Unresolved missing-data/roll positions are excluded from realized P&L and reported separately.

| Setup | Proxy | Filter | 2023 N | 2023 base net | 2023 stress net | 2024 N | 2024 base net | 2024 stress net |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Opening acceptance/retest | SPX | All matched | 169 | -1432.00 | -2277.00 | 180 | -106.25 | -1006.25 |
| Opening acceptance/retest | SPX | Positive only | 90 | -660.00 | -1110.00 | 116 | 40.75 | -539.25 |
| Opening acceptance/retest | SPX | Negative only | 79 | -772.00 | -1167.00 | 64 | -147.00 | -467.00 |
| Opening acceptance/retest | SPY | All matched | 170 | -1493.75 | -2343.75 | 180 | -106.25 | -1006.25 |
| Opening acceptance/retest | SPY | Positive only | 42 | -178.50 | -388.50 | 92 | -62.25 | -522.25 |
| Opening acceptance/retest | SPY | Negative only | 128 | -1315.25 | -1955.25 | 88 | -44.00 | -484.00 |
| Prior-day extreme reclaim | SPX | All matched | 108 | -1250.25 | -1790.25 | 89 | -138.25 | -583.25 |
| Prior-day extreme reclaim | SPX | Positive only | 57 | -759.75 | -1044.75 | 62 | 606.50 | 296.50 |
| Prior-day extreme reclaim | SPX | Negative only | 51 | -490.50 | -745.50 | 27 | -744.75 | -879.75 |
| Prior-day extreme reclaim | SPY | All matched | 108 | -1250.25 | -1790.25 | 89 | -138.25 | -583.25 |
| Prior-day extreme reclaim | SPY | Positive only | 26 | -403.00 | -533.00 | 48 | 532.25 | 292.25 |
| Prior-day extreme reclaim | SPY | Negative only | 82 | -847.25 | -1257.25 | 41 | -670.50 | -875.50 |
| Gap fill after opening failure | SPX | All matched | 5 | 20.00 | -5.00 | 1 | 27.00 | 22.00 |
| Gap fill after opening failure | SPX | Positive only | 4 | 31.75 | 11.75 | 0 | 0.00 | 0.00 |
| Gap fill after opening failure | SPX | Negative only | 1 | -11.75 | -16.75 | 1 | 27.00 | 22.00 |
| Gap fill after opening failure | SPY | All matched | 5 | 20.00 | -5.00 | 1 | 27.00 | 22.00 |
| Gap fill after opening failure | SPY | Positive only | 1 | 22.00 | 17.00 | 0 | 0.00 | 0.00 |
| Gap fill after opening failure | SPY | Negative only | 4 | -2.00 | -22.00 | 1 | 27.00 | 22.00 |

One 2023 opening-retest trade lacks a usable prior SPX source observation and is excluded from that matched baseline. The SPY matched baseline contains all 350 closed opening-retest trades. Zero-trade cells are not evidence of profitability.

Primary-lag unresolved positions: one 2023 opening-retest position (SPX positive / SPY negative), and one 2024 prior-extreme position (positive for both proxies). The 2024 positive reclaim cells therefore have censored fractions 1/63 = 1.59% (SPX) and 1/49 = 2.04% (SPY), both above the 1% gate. All gap-fill cohorts have zero censored positions.

## Fewer trades versus better average outcomes

Pooled profit factors below are total positive net trade P&L divided by absolute total negative net trade P&L, not averages of yearly profit factors.

| Setup / proxy | Matched closed trades | Matched stress net | Matched stress per trade | Positive-only closed trades | Positive-only stress net | Positive-only stress per trade | Positive-only pooled stress PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| Opening acceptance/retest / SPX | 349 | -3283.25 | -9.4076 | 206 | -1649.25 | -8.0061 | 0.7077 |
| Opening acceptance/retest / SPY | 350 | -3350.00 | -9.5714 | 134 | -910.75 | -6.7966 | 0.7376 |
| Prior-day extreme reclaim / SPX | 197 | -2373.50 | -12.0482 | 119 | -748.25 | -6.2878 | 0.7653 |
| Prior-day extreme reclaim / SPY | 197 | -2373.50 | -12.0482 | 74 | -240.75 | -3.2534 | 0.8596 |

Positive filtering improved both total losses and average net outcomes in these pooled cohorts, but all remained negative. This is descriptive selection within reused development data, not a causal or statistically established GEX edge. Reducing exposure to a losing strategy is not the same as finding a profitable strategy.

## Timing sensitivity

Positive-only stressed net, with the same setup and unchanged execution:

| Setup | Proxy | 2023 one-session lag | 2023 two-session lag | 2024 one-session lag | 2024 two-session lag |
|---|---|---:|---:|---:|---:|
| Opening acceptance/retest | SPX | -1110.00 | -1281.00 | -539.25 | -1468.50 |
| Opening acceptance/retest | SPY | -388.50 | -792.75 | -522.25 | -1388.25 |
| Prior-day extreme reclaim | SPX | -1044.75 | -1157.75 | 296.50 | -210.75 |
| Prior-day extreme reclaim | SPY | -533.00 | -587.75 | 292.25 | -208.00 |

The apparent 2024 positive-GEX reclaim improvement changes sign under the extra-session lag. This sensitivity does not prove a particular release delay, but it weakens robustness when historical publication timing is unverified.

For the 2024 one-session-lag positive reclaim cohort, both proxies produced 5 profitable and 7 losing months. SPX June-July-August contributed 607.75 against 296.50 for the entire year; removing those months yields -311.25. SPY June-July-August contributed 561.00 against 292.25 for the entire year; removing those months yields -268.75. These are post hoc concentration diagnostics, not proposed month filters.

## Independent summary-level audit

A fresh read-only SQL audit returned:

- 144 summaries and 144 distinct (year, setup, source, lag, filter, cost) combinations.
- 72 paired base/stress comparisons.
- Zero paired-cohort accounting errors: retained net + blocked matched net = matched baseline net.
- Zero base/stress trade-count or censored-count mismatches.
- Zero friction-difference errors: stressed net - base net = -5 dollars times closed trades.
- Zero result-year versus summary-year mismatches.

This confirms stored aggregate arithmetic. It is not an independent rerun from raw bars, a new audit of every source timestamp, or proof of executable fills. Source evidence and compressed ledgers remain in Postgres.

## Interpretation and next research boundary

All 12 source/setup/sign-filter candidates fail the predeclared primary development gate: stressed profit above zero, stress profit factor at least 1.10, at least 100 closed trades, and at most 1% unresolved positions in EACH year. An extra-session-lag tiny positive gap-fill cell does not override the failed primary gate or its inadequate sample size.

Do not keep tuning these losing five-minute entries against the same two years until a positive cell appears. The useful next experiment is a separate, tightly bounded session/timeframe hypothesis, not an MNQ transplant: for example fixed-rule opening-to-midday continuation or afternoon continuation using completed 15/30-minute context, alongside explicit no-trade and simple directional controls. Such a study must be frozen before inspecting results, use actual MES contracts, preserve source/time alignment and rollover controls, retain unresolved-position reporting, and show stressed costs, direction, session, month and drawdown separately. These are untested proposed hypotheses, not a new job started by this review.

A separate actual intraday-GEX comparison should only use the overlap of fresh, timestamp-verified snapshots and actual MES bars. Daily proxies must not be forward-filled and presented as historical minute GEX. Unknown source availability should remain a documented limitation.

No new MES strategy has earned live activation. MNQ is preserved, not certified; its original +$7,627 screen remains provisional for the previously documented reasons. No actual cumulative data billing or free-credit balance is inferred from this study's zero-new-download status.
