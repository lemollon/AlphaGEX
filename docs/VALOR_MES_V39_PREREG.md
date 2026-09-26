# VALOR MES v39 preregistration: overnight-extreme sweep rejection

## Decision and mechanism

Test whether an MES breach of the completed Globex overnight high or low that
closes back inside the range is a failed liquidity sweep with subsequent
mean-reversion value. Overnight extremes are fixed before the cash session and
commonly concentrate resting stops; the hypothesis is that a sweep without
five-minute acceptance represents liquidation rather than durable price
discovery.

This is research only. Read the existing checksummed Databento `MES.v.0`
one-minute caches for 2023-2025. Do not call a vendor or broker, change any
trader, scheduler, sizing, or production strategy, or read calendar year 2026.
Reported fills are trade-print OHLC planning scenarios, not executable BBO.

## Frozen data and causal construction

- Cash session: audited NYSE cash calendar, 08:30-15:00 America/Chicago on a
  normal session, with published early closes honored.
- Overnight range: observed MES bars from 17:00 on the preceding calendar day
  through 08:29 on the cash date. Require at least 900 observed minutes, the
  first observation no later than 17:05, the final observation exactly 08:29,
  at least 55 of the final 60 minutes, and one exact contract matching cash.
- Prior ATR: simple mean true range of the preceding 20 complete cash sessions,
  resetting at an exact-contract change.
- Signal bars: completed, contiguous five-minute cash bars. First decision is
  08:35. The full cash session is scanned; each hold's last decision is cash
  close minus its full holding period.
- Short: five-minute high breaches the overnight high by the frozen depth and
  the same completed bar closes back below the overnight high.
- Long: five-minute low breaches the overnight low by the frozen depth and the
  same completed bar closes back above the overnight low.
- A second same-side sweep requires an intervening completed five-minute close
  at least 0.25 prior ATR back inside the overnight range.
- If both sides qualify in one five-minute bar, skip the ambiguous signal.
- Entry is the next observed one-minute open. No same-bar entry is allowed.

## Frozen family

- Sweep depths: `{0.10, 0.20}` prior ATR.
- Reward/risk targets: `{1.5, 2.0}`.
- Maximum holds: `{30, 60, 120}` completed minutes.
- Stop: sweep extreme plus a `0.05` prior-ATR buffer, rounded away from price to
  the MES tick grid.
- Planned signal-close risk must be between `0.10` and `0.50` prior ATR.
- Twelve cells total: 2 depths x 2 targets x 3 holds.
- Maximum three closed trades per cash date, one position at a time, with a
  30-minute cooldown after each exit.
- A target requires one-tick trade-through. A stop is evaluated before a target
  on an ambiguous minute. Entry gaps through the stop exit at the observed
  entry open; entry gaps already beyond the target are skipped.
- Every position closes at its stop, target, full time stop, or cash close.

## Cost views and promotion gates

MES point value is $5, tick size is 0.25, and assumed round-trip fees are $3.
Report raw gross and 0, 1, 2, and 4 adverse ticks on both entry and exit. The
two-tick case selects a cell; four ticks is severe stress.

Open 2023 only and evaluate all twelve cells. A cell qualifies with:

- at least 150 trades;
- positive two-tick net dollars;
- two-tick profit factor at least 1.20;
- two-tick average trade at least $8;
- two-tick net profit / maximum drawdown at least 1.0;
- positive four-tick net dollars; and
- positive two-tick net dollars after removing its best month.

Rank qualifiers by two-tick net/drawdown, average trade, then written cell
order. Open 2024 only for the unchanged winner and apply the same annual gates.
Open 2025 only after a 2024 pass. Final historical promotion also requires at
least 180 trades/year on average and a combined 2024-2025 session-day bootstrap
95% lower bound above zero. Calendar 2026 remains a one-shot final holdout.

## Frozen cluster audit

For the selected cell, or the best diagnostic cell if none qualifies, record
only conditions known before entry: time bucket, side, first/repeat sweep,
causal ATR regime, overnight range/ATR, overnight return and cash gap alignment,
prior 15/30/60-minute return alignment, prior 60-minute directional efficiency,
VWAP distance/ATR, and cumulative relative volume versus the prior 20 same-time
cash sessions. MAE and MFE are diagnostics only.

On 2023 only, evaluate single-condition cohorts; no interactions or learned
tree partitions are allowed. An avoidance condition requires at least 40
trades, two-tick PF below 0.80, negative two-tick net, and a session-cluster
bootstrap 95% upper bound below zero. A size-up condition requires at least 40
trades, two-tick PF at least 1.40, average trade at least $12, positive four-tick
net, a session-cluster bootstrap 95% lower bound above zero, profitable first
and second half-years, and activity in at least six calendar months.

Advance at most one avoidance condition and one size-up condition. Report base
one-contract results separately. A two-contract Tier-A simulation is diagnostic
only. No real size increase is permitted without unchanged confirmation in
2024, 2025, untouched 2026, and forward testing.

## Output and safety

Persist only new `valor_mes_v39_results` research evidence plus local JSON/CSV
artifacts. Never write a trading, order, position, account, or scheduler table.
Any source checksum mismatch, missing minute, contract switch, noncausal
timestamp, or attempted 2026 read fails closed.
