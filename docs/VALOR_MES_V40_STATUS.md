# VALOR MES v40 status

**Recommendation: reject the intraday VWAP-extension rejection family and do
not use its apparent winners or losers to change trade size.** The attractive
120-minute diagnostic contained only 16 trades, one fifth of the frozen
discovery minimum. The sequential firewall therefore kept 2024 and 2025
unopened, and calendar 2026 remains sealed.

## Evidence boundary

- Study: `valor-mes-v40-vwap-reversion-20260926`
- Verdict: `FAMILY_FAIL_DISCOVERY`
- Code commit: `fb659ab2edf48e37fc9a634507c41db96d125ef4`
- Runner SHA-256: `66c08354a91d15f65be35e87ddfd22f24d487e9eadc45337f283e6a879e38503`
- Cached 2023 source SHA-256:
  `2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580`
- Persisted at: `2026-09-26T15:06:49.183683Z`
- Data opened: checksummed Databento MES one-minute OHLCV, calendar 2023 only
- Sessions: 154 usable; 96 excluded because exact-contract prior ATR was unavailable
- Events: 35; three additional events failed the frozen risk band
- Fill evidence: one-minute trade-print OHLC proxy, not executable bid/ask,
  queue, latency, or market-depth evidence
- Production/broker impact: none; `live_ready=false`

## Frozen discovery matrix

Dollar figures are for one MES contract. `Net 2t` includes the $3 round-trip
fee and two adverse ticks on entry and exit; `Net 4t` is the four-tick-per-side
stress case.

| Extension | Min R/R | Hold | Trades | Net 2t | Avg 2t | PF 2t | MDD 2t | Best month removed | Net 4t | Pass |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 0.50 ATR | 1.0 | 30m | 34 | -$73.25 | -$2.15 | 0.899 | $251.00 | -$166.00 | -$243.25 | No |
| 0.50 ATR | 1.0 | 60m | 25 | $232.50 | $9.30 | 1.459 | $130.75 | $80.50 | $107.50 | No |
| 0.50 ATR | 1.0 | 120m | 17 | $204.00 | $12.00 | 1.464 | $190.50 | $35.00 | $119.00 | No |
| 0.50 ATR | 1.5 | 30m | 32 | -$113.50 | -$3.55 | 0.841 | $291.25 | -$206.25 | -$273.50 | No |
| 0.50 ATR | 1.5 | 60m | 23 | $212.25 | $9.23 | 1.449 | $130.75 | $60.25 | $97.25 | No |
| 0.50 ATR | 1.5 | 120m | 16 | $262.00 | $16.38 | 1.687 | $132.50 | $93.00 | $182.00 | No |
| 0.75 ATR | 1.0 | 30m | 4 | -$177.00 | -$44.25 | 0.000 | $177.00 | -$166.50 | -$197.00 | No |
| 0.75 ATR | 1.0 | 60m | 2 | -$47.25 | -$23.63 | 0.463 | $88.00 | $0.00 | -$57.25 | No |
| 0.75 ATR | 1.0 | 120m | 1 | -$88.00 | -$88.00 | 0.000 | $88.00 | $0.00 | -$93.00 | No |
| 0.75 ATR | 1.5 | 30m | 4 | -$177.00 | -$44.25 | 0.000 | $177.00 | -$166.50 | -$197.00 | No |
| 0.75 ATR | 1.5 | 60m | 2 | -$47.25 | -$23.63 | 0.463 | $88.00 | $0.00 | -$57.25 | No |
| 0.75 ATR | 1.5 | 120m | 1 | -$88.00 | -$88.00 | 0.000 | $88.00 | $0.00 | -$93.00 | No |

The best diagnostic was 0.50 ATR / 1.5 minimum R/R / 120 minutes: eight
winners and eight losers, +$262 selection net, +$16.38 average, PF 1.687, and
+$182 under stress. It failed the controlling gate because 16 trades was below
the preregistered 80-trade minimum.

## Win/loss cluster review

No avoidance or size-up condition qualified because every subgroup had fewer
than the required 40 trades. The largest losing streak was three trades and
-$126.50 from August 10 through August 29. The worst five-active-session window
was -$132.50 ending November 10. The largest winning streak was two trades and
+$169 ending May 10.

Small descriptive samples are not rules. Normal relative volume was the worst
five-trade subgroup (-$24.75 average, PF 0.218), while high relative volume was
the best seven-trade subgroup (+$50.57 average, PF 4.837). Neither is authorized
for avoidance or size because the samples miss the frozen 40-trade minimum.

## Decision

Reject v40 without threshold relaxation or subgroup mining. The next family
must produce materially more independent opportunities and must remain subject
to the same sequential-year, cost-stress, cluster, and untouched-2026 controls.
