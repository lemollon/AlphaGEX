# VALOR MES v36 status

## Verdict

`FAMILY_FAIL_DISCOVERY`

The overnight-inventory family did not qualify in 2023. No cell met the
preregistered minimum of 80 trades, so the sequential firewall kept 2024 and
2025 unopened. Calendar year 2026 remains sealed.

## Evidence

- Opened years: 2023 only.
- Usable 2023 sessions: 154.
- Session exclusions: 92 `prior_atr_unavailable`; 4
  `overnight_contract_change`.
- Eligible discovery cells: 0 of 24.
- Best two-tick planning cell: `opening_rejection`, 0.50 prior-ATR overnight
  magnitude, 0.05 directional efficiency, 120-minute hold.
- Best-cell two-tick result: 14 trades, +$479.25 net, +$34.232143 average trade,
  2.261184 profit factor, and $228 maximum drawdown.
- Binding failure: 14 trades was below the preregistered 80-trade discovery
  minimum.

## Boundary

This was research-only trade-print evidence with assumed fees and adverse-tick
costs. It is not executable-fill evidence, is not live-ready, and made no paper,
broker, scheduler, Render, or other production change.
