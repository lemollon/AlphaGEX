# VALOR MES v38 status

## Verdict

`FAMILY_FAIL_DISCOVERY`

The volume-pressure/price-response family did not qualify in 2023. No cell met
all frozen financial gates, so the sequential firewall kept 2024 and 2025
unopened. Calendar year 2026 remains sealed.

## Evidence

- Opened years: 2023 only.
- Usable 2023 sessions: 247.
- Session exclusions: 3 `zero_price_response_sign`.
- Raw-positive discovery cells: 9 of 16.
- Two-tick-positive discovery cells: 1 of 16.
- Eligible discovery cells: 0 of 16.
- Best two-tick cell: `flow_follow`, `causal_high`, 240-minute hold.
- Best-cell two-tick result: 93 trades, +$174.75 net, +$1.879032 average
  trade, 1.050284 profit factor, and $1,224.50 maximum drawdown.
- Four-tick stress for that cell: -$290.25 net.
- Binding failures: profit factor was below 1.10, average trade was below $8,
  and four-tick stress was not positive.

The family is rejected without post-result threshold, regime, or exit changes.

## Boundary

The close-location signed-volume measure was an OHLCV proxy, not true aggressor
flow. This was research-only trade-print evidence with assumed costs. It is not
live-ready and made no paper, broker, scheduler, Render, or other production
change.
