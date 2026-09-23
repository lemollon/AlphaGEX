# MES rebuild v4 results - September 23, 2026

## Observed completion

Read directly from Render workspace tea-d34v9h95pdvs73baesfg, Postgres dpg-d4132pje5dus738rkoug-a, public.valor_mes_v4_state and public.valor_mes_v4_results. Study valor-mes-rebuild-v4-20260923 completed at 2026-09-23 13:51:37.524309 UTC (08:51:37 America/Chicago). State: selected=null, development_years=[2023,2024], test_year_2025=not_tested, gex_used=false, live_ready=false, mnq_changed=false, new_vendor_downloads=0.

Runtime source SHA256: a89b8b6eb6b0cf51896672f9238c09e2e8030bbc72ea0f366bd50d8b2dc7ea3c. Source commit: 546f95ed622d3506b5c793178c53af1ece7e8a70. Code blob: eff90a32e66323fc3b356afe0e3279d61615c00b. The commit changed one research startup import and added the MES script, tests and protocol. It did not change MNQ or any production trading rules/account balances. The normal deployment restarts the API; do not describe it as no production deployment. This results document is saved on an isolated research branch to avoid another main deployment.

## Data coverage

2023: 353,177 cached MES one-minute bars, 2023-01-02 23:00 UTC through 2023-12-29 21:59 UTC. Cache SHA256 2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580.
2024: 354,823 bars, 2024-01-01 23:00 UTC through 2024-12-31 21:59 UTC. Cache SHA256 6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040.
708,000 cached minute bars were loaded across development years. These are not 708,000 independent trades. Signals use completed five-minute bars during the defined cash session; trade fills are next-minute OHLC scenarios.
2025: intentionally NOT TESTED by v4 because no development candidate passed. The stored empty 2025 record is a workflow marker, not a zero-return result or missing calculation. Older studies already examined 2025 and parts of 2026, so neither entire year is untouched.

## One-contract results

Baseline = two adverse ticks on EACH side plus assumed $3 round-trip fees. Stress = four adverse ticks on EACH side plus those fees. With MES $1.25 per tick, modeled round-trip friction is $8 baseline and $13 stress. It includes the chosen adverse-price allowance and fees, not measured broker fills. Raw paths are identical between the two cost scenarios. Do not sum candidate P&L as a simultaneous portfolio.

| MES hypothesis | Year | Closed trades | Censored | Baseline net | Stress net | Baseline PF | Stress PF | Baseline closed-trade max DD | Stress closed-trade max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Opening acceptance/retest | 2023 | 170 | 1 | -1493.75 | -2343.75 | 0.665641 | 0.535914 | 1601.00 | 2343.75 |
| Opening acceptance/retest | 2024 | 180 | 0 | -106.25 | -1006.25 | 0.978950 | 0.821246 | 1257.25 | 1742.25 |
| Prior-extreme reclaim | 2023 | 108 | 0 | -1250.25 | -1790.25 | 0.587478 | 0.478137 | 1250.25 | 1790.25 |
| Prior-extreme reclaim | 2024 | 89 | 1 | -138.25 | -583.25 | 0.944338 | 0.788582 | 626.00 | 739.25 |
| Gap fill after opening failure | 2023 | 5 | 0 | +20.00 | -5.00 | 1.423280 | 0.918699 | 46.50 | 61.50 |
| Gap fill after opening failure | 2024 | 1 | 0 | +27.00 | +22.00 | undefined/no losing trades | undefined/no losing trades | 0 | 0 |

Combined closed-trade net, 2023-24:
- Opening acceptance/retest: -$1,600 baseline, -$3,350 stress; 350 closed trades, 1 censored.
- Prior-extreme reclaim: -$1,388.50 baseline, -$2,373.50 stress; 197 closed trades, 1 censored.
- Gap fill: +$47 baseline, +$17 stress; 6 closed trades. Six trades are insufficient to establish a robust edge; its 2023 stress result is also negative.

Frozen gate: EACH development year must have positive stress net, stress PF >=1.10, at least 100 closed trades and no more than 1% censored entries. NONE passed. No production strategy promotion.

## Interpretation and limits

These results reject these particular implementations under the stated model, not the entire MES market or all breakout/reversal strategies. In 2024 the opening-retest path earned $1,333.75 before modeled friction, but $1,440 in baseline friction turned it into -$106.25. In 2023 that path was already -$133.75 before friction. Therefore fees are part of the problem but do not fully explain both years; merely reducing the cost assumption does not establish durability.

This is futures-native price research, not a GEX backtest. Do not infer that historical GEX was tested or rejected. GEX would need a separate source/availability-timestamp-aligned comparison with an otherwise identical no-GEX baseline. Five-minute signal inputs, next-minute entries, one attempt per strategy per day, same-contract prior levels, stop-first ambiguity handling and adverse gaps are modeled. Quote-level execution, latency, portfolio margin, unseen forward performance and actual broker fees are not validated. Censored positions are excluded from realized P&L; drawdown is closed-trade-only. Results are not account returns or forecasts.

MNQ remains unchanged at the user's request, but the earlier +$7,627 screening result is not a validated strategy result because the initial screen had overlapping-entry, same-close and roll-handling issues. Later negative studies tested different specifications, not an exact corrected rerun of that original candidate. Preserve the original candidate without certifying it.

## Reproduction query

```sql
SELECT r.year, r.manifest->>'phase' AS phase,
 s->>'spec' AS strategy,
 (s->>'cost_ticks_each_side')::int AS adverse_ticks_each_side,
 (s->>'trades')::int AS trades,
 (s->>'net_dollars')::numeric AS net_dollars,
 (s->>'profit_factor')::numeric AS profit_factor,
 (s->>'closed_trade_max_drawdown')::numeric AS closed_trade_max_drawdown,
 (s->>'censored_positions')::int AS censored,
 (s->>'raw_price_pnl')::numeric AS raw_price_pnl
FROM public.valor_mes_v4_results r
LEFT JOIN LATERAL jsonb_array_elements(r.summary) s ON true
WHERE study_id='valor-mes-rebuild-v4-20260923'
ORDER BY strategy,r.year,adverse_ticks_each_side;
```

Full gzip evidence ledgers remain in the results table: 32,064 bytes for 2023, 31,449 bytes for 2024; 22-byte empty list for the intentionally untested 2025 workflow marker. Refer to docs/VALOR_MES_REBUILD_V4_PROTOCOL.md for all predeclared rules and software tests.
