# VALOR MES v37 preregistration: overnight equity-leader transfer

## Decision and mechanism

Test whether MNQ and M2K establish a shared overnight equity-index direction
that MES either confirms or rejects in the first five cash minutes. This removes
v36's MES overnight magnitude, ATR, and efficiency filters and instead requires
independent agreement from growth/technology and small-cap breadth leaders.

Research only. Read existing Databento `MES.v.0`, `MNQ.v.0`, and `M2K.v.0`
one-minute caches in a read-only transaction. No vendor request, broker, paper
deployment, production, sizing, scheduler, Render change, or calendar-year 2026
access is allowed.

## Causal construction

- Use 2023 for discovery, then open 2024 and 2025 only through the sequential
  firewall below. Calendar year 2026 remains sealed.
- Validate timestamps, finite OHLCV geometry, tick grids, duplicates, and exact
  contract identity with the audited v8 rules. MES and MNQ use 0.25-point ticks;
  M2K uses 0.10-point ticks.
- For MNQ and M2K separately, build the observed overnight path from 17:00 CT on
  the preceding calendar day through 08:29 CT on the cash date. Do not
  forward-fill. Require the first observed bar no later than 17:05, the last
  observed bar exactly 08:29, at least 900 observed minutes, at least 55 of the
  final 60 minutes, monotonic timestamps, and one exact contract within that
  market's path.
- Each leader's overnight return is its first observed open to its 08:29 close.
  Both returns must have the same nonzero sign.
- MES must have a complete v8 cash session in one exact contract. The causal
  cash-open response is the 08:30 MES open to the 08:34 MES close. Decide only
  after the 08:34 bar and enter the 08:35 MES open.

## Frozen family

There are two modes:

1. `leader_confirmed`: the MES first-five-minute response has the same nonzero
   sign as the agreeing leaders; trade the leader sign.
2. `leader_rejected`: the MES first-five-minute response has the opposite
   nonzero sign; trade the first-five-minute response sign.

For each mode, test fixed MES holds of 30, 60, 120, and 240 completed minutes.
Exit at the exact corresponding MES close. Missing entry/exit bars, timestamp
gaps, or an MES contract change skip the trade. One trade per cash date is
possible in each cell.

This is eight cells in the written mode and hold order. No MES overnight
magnitude or ATR filter, volume filter, stop, target, trailing exit, GEX,
same-bar assumption, probability, or after-result filter is allowed.

## Costs, selection, and firewall

MES point value is $5 and tick size is 0.25. Report raw P&L and a $3 assumed
round-trip fee with 0, 1, 2, and 4 adverse MES ticks per side. These are
trade-print planning cases, not executable bid/ask evidence.

Discovery uses 2023 only. A cell is eligible with at least 80 trades, positive
two-tick net dollars, two-tick profit factor at least 1.10, two-tick average
trade at least $8, and positive four-tick net dollars. Rank eligible cells by
two-tick net-to-maximum-drawdown, then average trade, then the fixed written cell
order. Select exactly one cell. If none qualify, 2024 and 2025 remain unopened.

Evaluate the selected cell unchanged in 2024. Open 2025 only if 2024 has at
least 60 trades and meets the same profitability gates. Apply the identical
gate to 2025. Final historical promotion also requires the combined 2024-2025
session-day cluster bootstrap 95% lower confidence bound for mean two-tick
daily P&L above zero, using 10,000 resamples and seed `370037`, including
zero-trade usable sessions.

Report each opened year, all eight 2023 discovery summaries, all cost views,
monthly P&L, maximum drawdown, session exclusions, and a reviewable selected-
trade ledger. A pass is `HISTORICAL_CANDIDATE`, not live profitability;
executable-fill calibration and forward paper evidence remain mandatory.
