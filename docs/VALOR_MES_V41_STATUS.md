# VALOR MES v41 status

**Recommendation: reject the unfiltered opening-range retest family, do not
trade it, and do not increase size.** Advance only the preregistered
`gap_alignment=opposed` diagnostic to a separate unchanged 2024 holdout test.
Calendar 2026 remains sealed.

## Evidence boundary

- Study: `valor-mes-v41-opening-range-retest-20260926`
- Verdict: `FAMILY_FAIL_DISCOVERY`
- Code commit: `d3a170731d9b685b1fc9fa63e4f15ca944a7f506`
- Runner SHA-256: `3d83cffa896d852fd7e072daaa13b17d884a42f746f837b971920ffd5fa84ec6`
- Cached 2023 source SHA-256:
  `2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580`
- Persisted at: `2026-09-26T15:23:13.239494Z`
- Data opened: checksummed Databento MES one-minute OHLCV, calendar 2023 only
- Sessions: 154 usable; 96 excluded because exact-contract prior ATR was unavailable
- Candidate events: 122 at 0.05 ATR and 87 at 0.10 ATR
- Fill evidence: one-minute trade-print OHLC proxy, not executable bid/ask,
  queue, latency, or market-depth evidence
- Production/broker impact: none; `live_ready=false`

## Frozen discovery matrix

| Buffer | Target | Hold | Trades | Net 2t | Avg 2t | PF 2t | MDD 2t | Best month removed | Net 4t | Pass |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 0.05 ATR | 1.5R | 30m | 122 | -$1,043.50 | -$8.55 | 0.568 | $1,166.50 | -$1,065.75 | -$1,653.50 | No |
| 0.05 ATR | 1.5R | 60m | 118 | -$879.00 | -$7.45 | 0.681 | $1,093.75 | -$941.25 | -$1,469.00 | No |
| 0.05 ATR | 1.5R | 120m | 109 | -$522.00 | -$4.79 | 0.804 | $922.50 | -$609.00 | -$1,067.00 | No |
| 0.05 ATR | 2.0R | 30m | 122 | -$994.75 | -$8.15 | 0.588 | $1,141.75 | -$1,044.50 | -$1,604.75 | No |
| 0.05 ATR | 2.0R | 60m | 118 | -$1,046.50 | -$8.87 | 0.626 | $1,287.50 | -$1,171.25 | -$1,636.50 | No |
| 0.05 ATR | 2.0R | 120m | 109 | -$793.25 | -$7.28 | 0.721 | $1,166.50 | -$954.00 | -$1,338.25 | No |
| 0.10 ATR | 1.5R | 30m | 87 | -$76.00 | -$0.87 | 0.949 | $481.50 | -$202.00 | -$511.00 | No |
| 0.10 ATR | 1.5R | 60m | 82 | -$184.75 | -$2.25 | 0.891 | $463.75 | -$364.75 | -$594.75 | No |
| 0.10 ATR | 1.5R | 120m | 71 | $300.75 | $4.24 | 1.186 | $277.00 | $186.25 | -$54.25 | No |
| 0.10 ATR | 2.0R | 30m | 87 | -$221.00 | -$2.54 | 0.853 | $571.50 | -$374.50 | -$656.00 | No |
| 0.10 ATR | 2.0R | 60m | 81 | -$481.75 | -$5.95 | 0.721 | $768.00 | -$691.75 | -$886.75 | No |
| 0.10 ATR | 2.0R | 120m | 70 | $52.50 | $0.75 | 1.030 | $467.50 | -$127.50 | -$297.50 | No |

The best diagnostic was 0.10 ATR / 1.5R / 120 minutes. It failed the frozen
80-trade, $8-average, and positive-stress gates. Its six-trade largest loss
streak lost $263 from August 11 through August 21; its worst five-active-session
window lost $225 ending August 18.

## Preregistered cluster finding

No avoidance rule qualified. One size-up diagnostic met the frozen 2023 cluster
criteria: the 0.10 ATR / 1.5R / 120-minute signal when the cash gap opposed the
eventual trade direction.

- 41 trades across 11 active months
- +$797 at the two-tick selection cost; +$19.44 average; PF 2.307
- $165.75 maximum drawdown; +$550.25 after removing the best month
- +$592 under four-tick stress; stress PF 1.847
- active-session bootstrap mean-trade 95% interval: +$3.16 to +$36.42

This is a discovered 2023 subgroup, not a validated strategy and not permission
to trade two contracts. It may advance only as a fixed one-contract v42
hypothesis tested first on 2024. A 2024 failure must keep 2025 unopened.
