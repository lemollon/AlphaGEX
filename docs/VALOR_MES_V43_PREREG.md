# VALOR MES v43 preregistration: intraday cross-asset risk pulse

## Decision and mechanism

Test one independent, price-only cross-asset mechanism instead of adding a
second-generation filter to a rejected MES setup. Rising crude oil paired with
falling gold is treated as a risk-on pulse; falling crude oil paired with
rising gold is treated as a risk-off pulse. MES is the traded instrument, but
MES price direction is not an input to the signal.

Research only. Read the existing checksummed Databento one-minute cache for
`MES.v.0`, `MCL.v.0`, and `MGC.v.0` through a read-only transaction. Use 2023
for discovery, then open 2024 and 2025 only through the sequential firewall.
No vendor request, broker, paper deployment, production, sizing, scheduler, or
live trading change is authorized. Calendar year 2026 remains sealed.

## Causal construction and all-day scan

- Require synchronized, complete 08:30-14:59 CT sessions for all three
  instruments under the existing MES exchange calendar. Validate finite OHLCV,
  nonnegative volume, monotonic unique minute timestamps, valid bar geometry,
  and each market's tick grid: MES 0.25, MCL 0.01, and MGC 0.10.
- Exclude a date if any instrument changes contract during the synchronized
  cash window. The three instruments do not need the same contract identifier.
- Scan a fixed 15-minute decision grid from 09:00 through 14:15 CT. At decision
  time `t`, use exactly the 30 completed bars from `t-30` through `t-1`.
- Oil return is MCL last close / first open minus one. Gold return is MGC last
  close / first open minus one. Both returns must be finite and nonzero.
- A signal exists only when the return signs oppose. MCL positive and MGC
  negative is `risk_on` and buys MES. MCL negative and MGC positive is
  `risk_off` and sells MES. Same-sign returns create no trade.
- Enter the exact MES open at `t`. Exit at the close of the fixed holding
  window. Missing paths, timestamp gaps, contract changes, exits after the
  existing 14:55 CT flat policy, and overlapping positions skip the entry.
- Each cell holds at most one MES position at a time, while continuing to scan
  the full fixed grid for later opportunities.

## Frozen family

Test fixed holds of 15, 30, 60, and 120 completed minutes, in that order. This
is four cells. There is no magnitude threshold, MES trend filter, stop, target,
trailing exit, GEX input, volatility input, overnight input, after-result
parameter, or second signal definition.

MES point value is $5 and tick size is 0.25. Report raw P&L and a $3 assumed
round-trip fee with 0, 1, 2, and 4 adverse MES ticks per side. These are
one-minute trade-print planning scenarios, not executable bid/ask evidence.

## Discovery, validation, and firewall

For each cell and opened year, report trade count, net, average trade, profit
factor, maximum drawdown, monthly P&L, best-month-removed net, first-half and
second-half net, active months, long/short counts, day-cluster bootstrap, and
execution skips. Use 10,000 resamples with seed `430043`.

A year passes only when all of these hold at the two-tick selection cost:

- at least 120 completed trades and at least nine active months;
- positive net, average trade at least $8, and profit factor at least 1.20;
- positive best-month-removed net;
- positive first-half and second-half net;
- positive four-tick stress net; and
- day-cluster bootstrap 95% lower confidence bound above zero, including every
  usable synchronized session as a zero-P&L day when no trade occurs.

Select the passing 2023 cell with highest two-tick net-to-drawdown, then higher
average trade, then written hold order. If no cell passes, 2024 and 2025 remain
unopened. Evaluate the selected cell unchanged in 2024; a failure keeps 2025
unopened. Evaluate unchanged in 2025 only after a 2024 pass. Final historical
promotion also requires the combined 2024-2025 day-cluster bootstrap lower
bound above zero. A pass is `HISTORICAL_CANDIDATE`, never a claim of live
profitability.

## Win/loss cluster review

For the selected 2023 cell, or the fixed-order diagnostic leader if no cell
passes, report streaks, five-active-session windows, and single-dimension
cohorts frozen before results:

- decision block: `morning` 09:00-10:29, `midday` 10:30-11:59, or `afternoon`
  12:00-14:15 CT;
- pulse direction: `risk_on` or `risk_off`; and
- dominant absolute return: `oil` when absolute MCL return is greater than
  absolute MGC return, otherwise `gold`.

Each cohort reports count, two-tick and four-tick economics, and a mean-trade
bootstrap. A cohort is only an `avoid_lead` when it has at least 30 trades,
negative four-tick net, and bootstrap upper bound below zero. It is only a
`size_lead` when it has at least 30 trades, positive four-tick net, and
bootstrap lower bound above zero. These labels are descriptive research leads,
not permission to skip trades or trade larger; any use requires a separately
preregistered untouched-year holdout plus executable-fill and forward-paper
evidence.

