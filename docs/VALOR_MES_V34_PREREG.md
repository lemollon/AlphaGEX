# VALOR MES v34 preregistration: MNQ breakout transferred to MES

## Decision and mechanism

Test the direct cross-market version of the historically promising MNQ rule:
when MNQ closes outside its preceding 30 completed one-minute bars, trade MES in
the same direction. The mechanism is common equity-index price discovery led by
the more volatile Nasdaq contract. This is not the failed v33 residual catch-up
rule and is not the already-tested MES-own-price breakout.

Research only. No production, broker, sizing, scheduler, Render, or paper-bot
change is authorized. Read only the existing Databento `MES.v.0` and `MNQ.v.0`
one-minute cache. No vendor request is allowed. Calendar year 2026 stays sealed.

## Frozen rule

- Use exact synchronized, complete cash-session MES and MNQ bars under the v8
  calendar, geometry, tick, duplicate, contiguity, and contract checks.
- At each completed MNQ minute `t`, compare its close with the high and low of
  the preceding 30 completed MNQ bars; the signal bar is excluded.
- Close above the prior high signals long MES. Close below the prior low signals
  short MES. Equality is no signal.
- Enter at the next MES minute open. The MES and MNQ signal histories must be
  contiguous; the MES entry-to-exit path must remain one exact contract.
- Hold for at most 240 completed minutes, exiting at the earlier of the fixed
  horizon or the v8 five-minute pre-close boundary. Use the close of the last
  completed MES holding bar. No stop, target, trailing exit, GEX, ATR, beta,
  probability, or regime filter is allowed.
- At most one MES position at a time. An entry at the exact prior exit timestamp
  is allowed. Missing bars, contract changes, or unavailable exits skip the
  candidate; no price is fabricated.

There is one cell only: lookback 30 minutes, same-direction transfer, maximum
hold 240 minutes. No threshold or parameter search occurs.

## Costs and sequential firewall

Report raw gross and a $3 assumed round-trip fee with 0, 1, 2, and 4 adverse MES
ticks on each side. These remain trade-print planning scenarios, not executable
bid/ask evidence.

Open 2023 first. Continue to 2024 only if the two-tick case has at least 80
trades, positive net dollars, profit factor at least 1.10, average net trade at
least $8, and positive four-tick net dollars. Apply the identical gate to 2024
before opening 2025, and to 2025 for the final annual pass.

The final historical candidate also requires the combined 2024-2025 day-cluster
bootstrap 95% lower confidence bound for mean two-tick daily P&L above zero,
using 10,000 deterministic resamples and including zero-trade sessions.

Report each opened year, monthly P&L, maximum drawdown, all cost views, and a
reviewable selected-trade ledger. No rule changes after a result. A historical
pass is `HISTORICAL_CANDIDATE`, not live profitability; it still requires
executable MES quote/fill calibration and a forward paper ledger.
