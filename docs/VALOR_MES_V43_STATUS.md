# VALOR MES v43 status: rejected in discovery

## Decision

Reject the intraday MCL/MGC risk-pulse family. Do not trade it, invert it, add
an after-result filter, or use any cluster to increase size. The frozen family
failed 2023 discovery, so the sequential firewall left 2024 and 2025 unopened.
Calendar year 2026 remained sealed.

Study: `valor-mes-v43-crossasset-riskpulse-20260926`  
Verdict: `FAMILY_FAIL_DISCOVERY`  
Persisted: `2026-09-26T15:51:31.371749Z`  
Runner source SHA-256: `e25a1f47d898a3ae7daf2fddc6f089e577cb0470401c5a8607f489473224aa0f`

This was research only. No broker, order, paper deployment, production strategy,
sizing, or live-money setting changed. Fills remain one-minute trade-print
proxies with a $3 round-trip fee and adverse-tick scenarios, not executable
bid/ask or latency evidence.

## Frozen-family result

All four fixed holds lost money at the two-tick selection cost:

| Hold | Trades | Net | Avg/trade | PF | Max DD | 4-tick net | Day-bootstrap lower 95% |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 15 min | 889 | -$7,180.75 | -$8.08 | 0.447 | $7,180.75 | -$11,625.75 | -$97.10 |
| 30 min | 605 | -$4,445.00 | -$7.35 | 0.603 | $4,445.00 | -$7,470.00 | -$69.36 |
| 60 min | 354 | -$2,633.25 | -$7.44 | 0.728 | $2,924.25 | -$4,403.25 | -$56.23 |
| 120 min | 175 | -$1,967.50 | -$11.24 | 0.690 | $1,967.50 | -$2,842.50 | -$45.95 |

The fixed-order diagnostic leader was the 60-minute hold; it was not eligible.
It lost in both halves of 2023: -$2,486.75 in January-June and -$146.50 in
July-December. Only August (+$161.00) and September (+$193.25) were positive.
Best-month-removed net remained -$2,826.50. The mean daily P&L was -$28.62.

## Coverage and audit trail

There were 92 exact synchronized MES/MCL/MGC sessions. The complete-session
audit excluded 43 dates missing complete MCL, 69 missing complete MGC, and 46
missing both. The 60-minute cell saw 890 opposed-sign signal candidates and
completed 354 non-overlapping trades; 455 candidates were blocked by an open
position, with the remainder lost to exit-window limits or short-session bounds.

Checksummed source rows opened:

- MES 2023: `2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580`
- MCL 2023: `9b61f602ceaf7b5bffe6870f4eeede784cb6e1ebb4506d103d32d255e4302857`
- MGC 2023: `2e5a15938413635193132bd7d86ccdf67f8105f2f2e70a610616619e05719f4b`

No 2024 or 2025 cache row was opened.

## Win/loss cluster review

There was no `size_lead` in any frozen cohort. Every direction and time block
had negative two-tick net P&L.

Two cohorts met the preregistered descriptive `avoid_lead` definition:

- `midday`: 99 trades, -$1,277.00 at two ticks, -$1,772.00 at four ticks,
  PF 0.487, bootstrap mean-trade interval [-$22.43, -$3.09].
- `gold` dominant: 75 trades, -$1,687.50 at two ticks, -$2,062.50 at four
  ticks, PF 0.368, bootstrap interval [-$36.09, -$8.73].

These are not usable filters. The unfiltered family is already decisively
negative, the remaining cohorts are also negative, and removing the worst
observed clusters after seeing 2023 would be selection bias. A filter may be
studied only as a separately preregistered hypothesis on an untouched year.

The largest losing streak was eight trades totaling -$675.25 from March 6-10.
The largest winning streak was five trades totaling +$327.50 from December
12-13. The worst five-active-session window was -$665.75 from January 3-12; the
best was +$520.00 from August 25-September 29. The positive bursts did not
offset the persistent loss distribution.

## Next action

Stop OHLCV-only filter mining. The next defensible path is new MES event data:
NinjaTrader Market Replay or another tick/quote/depth source, followed by a new
preregistration that models event order, bid/ask execution, fees, slippage,
loss clusters, and forward paper fills. Until that data is acquired and a rule
survives untouched validation, the MES decision is **No Trade**.

