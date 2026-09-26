# VALOR MES v40 preregistration: intraday VWAP-extension rejection

## Decision and mechanism

Test one structurally new MES mechanism: an intraday displacement away from
causal session VWAP followed by a completed five-minute rejection back toward
VWAP. The hypothesis is inventory/fair-value reversion after an extension; it
is not a retune of v39's overnight-level sweep and does not rely on a published
performance estimate.

Research only. Read the existing checksummed Databento MES one-minute cache in
a read-only transaction. No vendor request, broker action, paper deployment,
production rule, scheduler, or real-money size change is authorized. Calendar
year 2026 stays sealed.

## Causal construction

- Use the audited v39 complete-session and prior-ATR construction. Require one
  exact MES contract, finite OHLCV geometry, 0.25-point tick geometry,
  monotonic timestamps, and a complete cash session.
- Prior ATR is the simple mean true range of the preceding 20 complete cash
  sessions. Current-day prices never enter it.
- Build non-overlapping completed five-minute bars. Start decisions at 09:00 CT
  and continue through the last time each cell can complete its full hold before
  the exchange cash close.
- Causal session VWAP through each signal bar is cumulative
  `sum(typical_price * volume) / sum(volume)`, where typical price is
  `(high + low + close) / 3`. Require positive cumulative volume.
- Track each side's maximum completed-bar absolute displacement from VWAP while
  armed. A rejection exists only when displacement reached at least 0.50 prior
  ATR, the current completed-bar close moved at least 0.10 ATR back toward VWAP,
  and the close remains at least 0.05 ATR on the original side of VWAP.
- After a signal, that side re-arms only after a completed five-minute close is
  within 0.10 ATR of causal VWAP. No future VWAP value is used.
- Enter at the next observed one-minute open. The profit target is the
  signal-time VWAP frozen to the adverse tick; the stop is the signal block's
  adverse extreme plus a 0.05-ATR buffer, rounded away from the entry side.
- Planned reference-to-stop risk must be between 0.10 and 0.60 prior ATR.
  Entry gaps through the stop or target are handled explicitly; no price is
  invented.

## Frozen family

Test extension thresholds `{0.50, 0.75}` prior ATR, minimum signal-time
reward/risk `{1.0, 1.5}`, and maximum holds `{30, 60, 120}` completed minutes.
This is 12 cells in the written threshold/reward/hold order.

Within each cell, allow at most three trades per cash date, one open position at
a time, and a 30-minute cooldown after exit. Stops are evaluated before targets
when both occur in one minute. A target requires one MES tick of trade-through.
If neither level is reached, exit at the final hold-minute close. No trailing
stop, partial exit, time-bucket filter, trend filter, volume threshold, news
calendar, GEX, or cross-market input is allowed.

## Costs and sequential firewall

MES point value is $5 and tick size is 0.25. Report raw gross plus a $3 assumed
round-trip fee with 0, 1, 2, and 4 adverse ticks on both entry and exit. The
two-tick case selects a cell; four ticks is severe stress. These are trade-print
planning scenarios, not executable bid/ask evidence.

Discovery opens 2023 only. A cell qualifies with at least 80 trades, positive
two-tick net, two-tick PF at least 1.15, two-tick average at least $8,
two-tick net/MDD at least 0.75, positive four-tick net, and positive two-tick
net after removing the best month. Rank qualifying cells by two-tick net/MDD,
then average trade, then written cell order. Select exactly one cell.

Open 2024 only for that unchanged cell. It must have at least 60 trades and the
same financial gates. Open 2025 only after a 2024 pass and apply the same gate.
Final historical promotion requires at least 100 trades/year on average and a
combined 2024-2025 usable-session day-bootstrap 95% lower bound above zero,
using 10,000 deterministic resamples and seed `400040`. Calendar 2026 remains
a one-shot final holdout.

## Frozen cluster review

For the selected cell, or the best diagnostic cell with at least 40 trades,
reuse v39's single-condition, prior-known cluster audit: time bucket, side,
first/repeat signal, causal ATR regime, overnight range/ATR, overnight return
and cash-gap alignment, prior 15/30/60-minute return alignment, prior 60-minute
efficiency, causal VWAP relation, and cumulative relative volume versus the
prior 20 same-time sessions. Do not fit interactions.

An avoidance condition requires at least 40 trades, PF below 0.80, negative
two-tick net, and a session-bootstrap 95% upper bound below zero. A size-up
condition requires at least 40 trades, PF at least 1.40, average at least $12,
positive four-tick net, bootstrap lower bound above zero, both half-years
positive, and activity in at least six months. Advance at most one of each.
Size-up is diagnostic only and never authorizes real size.

## Output and safety

Persist immutable research evidence only to `valor_mes_v40_results`, plus local
JSON/CSV output. The runner must record years opened, checksum-validating source
hashes, every cell, monthly results, drawdown, cluster evidence, and the selected
trade ledger. `HISTORICAL_CANDIDATE` would still require untouched 2026,
executable-fill calibration, and forward shadow evidence before any live use.
