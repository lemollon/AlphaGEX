# VALOR MES v35 preregistration: dual-leader breadth breakout

## Decision and mechanism

Test whether a breakout shared by both MNQ and M2K identifies a broad equity
shock with enough persistence to trade MES after costs. MNQ supplies growth/tech
leadership; M2K supplies small-cap breadth. Requiring both to break in the same
direction is a new cross-market participation mechanism, not a retune of v34 and
not an MES-own-price rule.

Research only. Read existing Databento one-minute caches for `MES.v.0`,
`MNQ.v.0`, and `M2K.v.0` in a read-only transaction. No vendor request, paper
deployment, production, broker, sizing, scheduler, or Render change is allowed.
Calendar year 2026 remains sealed.

## Frozen rule

- Use synchronized, complete cash sessions under the v8 calendar and strict
  timestamp, geometry, tick, duplicate, contiguity, and exact-contract checks.
- For each completed minute `t`, separately compare the MNQ and M2K close with
  that instrument's preceding 30 completed one-minute highs and lows. Exclude
  the signal bar from both ranges.
- Long MES only when both closes are strictly above their own preceding highs on
  the same minute. Short MES only when both closes are strictly below their own
  preceding lows on the same minute. Mixed or one-sided breaks are no signal.
- Enter the next MES minute open. Hold at most 240 completed minutes, exiting at
  the earlier of the fixed horizon or the v8 five-minute pre-close boundary,
  using the last completed MES bar close.
- At most one MES position. Exact-exit-time re-entry is allowed. The leader
  histories and MES entry-to-exit path must be contiguous and stay within one
  exact contract per instrument. Missing bars or contract changes skip the
  candidate; no price is invented.
- No stop, target, beta, GEX, ATR, volume, probability, or regime filter. There
  is one cell only: two 30-minute same-direction leader breakouts and a maximum
  240-minute MES hold.

## Costs and firewall

Report gross P&L and a $3 assumed round-trip fee with 0, 1, 2, and 4 adverse MES
ticks per side. These are planning scenarios, not executable bid/ask evidence.

Open 2023 first. Continue to the next year only if the unchanged rule has at
least 60 trades, positive two-tick net dollars, two-tick profit factor at least
1.10, two-tick average trade at least $8, and positive four-tick net dollars.
Apply the same gate sequentially to 2024 and 2025.

Final historical promotion additionally requires the combined 2024-2025
day-cluster bootstrap 95% lower confidence bound for mean two-tick daily P&L
above zero, with 10,000 deterministic resamples including zero-trade sessions.
Report each opened year, all cost views, monthly P&L, maximum drawdown, and a
reviewable trade ledger. A pass is `HISTORICAL_CANDIDATE`, not live profitability;
it still requires executable-fill calibration and forward paper evidence.
