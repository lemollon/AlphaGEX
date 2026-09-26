# VALOR MES v41 preregistration: opening-range breakout retest continuation

## Recommendation and mechanism

Test one structurally new MES mechanism: continuation after a completed
opening-range breakout, a later controlled retest of the broken boundary, and a
still-later completed-bar resumption. This requires three distinct stages and
is not v34's one-minute MNQ breakout transfer, v39's overnight-level rejection,
or v40's VWAP mean reversion.

Research only. Read the existing checksummed Databento MES one-minute cache in
a read-only transaction. No vendor request, broker action, paper deployment,
production rule, scheduler, or real-money size change is authorized. Calendar
year 2026 stays sealed.

## Causal construction

- Use the audited v39 exact-contract complete-session and prior-ATR
  construction. Prior ATR is the simple mean true range of the preceding 20
  complete cash sessions; current-day prices never enter it.
- The opening range is the observed 08:30-08:59 CT high and low. Require all 30
  contiguous one-minute bars, positive range, finite OHLCV geometry, and one
  exact contract.
- Build non-overlapping completed five-minute bars beginning at 09:00 CT. Scan
  through the last time each cell can complete its full hold before the
  exchange cash close.
- Long sequence: a completed five-minute close first exceeds the opening-range
  high by the frozen breakout buffer; a later completed block trades back to no
  more than 0.05 prior ATR above that high while closing no more than 0.05 ATR
  inside it; a still-later completed block closes beyond the original breakout
  buffer again. Short is the exact mirror below the opening-range low.
- A close more than 0.05 ATR back inside the range before resumption invalidates
  that side's sequence. At most the first completed sequence per side and date
  is eligible. The breakout, retest, and resumption must be separate blocks.
- Enter at the next observed one-minute open. The stop is the adverse extreme
  across the retest and resumption blocks plus a 0.05-ATR buffer, rounded away
  from the entry side. Planned signal-close risk must be 0.10-0.60 prior ATR.
- The target is the frozen reward/risk multiple of signal-close risk, rounded
  away from the entry. Entry gaps through stop or target are handled explicitly;
  no price is invented.

## Frozen family

Test breakout buffers `{0.05, 0.10}` prior ATR, reward/risk targets `{1.5,
2.0}`, and maximum holds `{30, 60, 120}` completed minutes. This is 12 cells in
the written buffer/target/hold order.

Within each cell, allow at most two trades per cash date, one open position at
a time, and a 30-minute cooldown after exit. Stops are evaluated before targets
when both occur in one minute. A target requires one MES tick of trade-through.
If neither level is reached, exit at the final hold-minute close. No trend,
VWAP, volume, time-bucket, news, GEX, overnight-direction, cross-market, or
post-result filter is allowed.

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
using 10,000 deterministic resamples and seed `410041`. Calendar 2026 remains
a one-shot final holdout.

## Frozen win/loss cluster review

For the selected cell, or the best diagnostic cell with at least 40 trades,
audit only single prior-known conditions: time bucket, side, causal ATR regime,
overnight range/ATR, overnight return and cash-gap alignment, prior
15/30/60-minute return alignment, prior 60-minute efficiency, causal VWAP
relation, cumulative relative volume, opening-range width regime, and opening
drive alignment. Do not fit interactions.

An avoidance condition requires at least 40 trades, PF below 0.80, negative
two-tick net, and a session-bootstrap 95% upper bound below zero. A size-up
condition requires at least 40 trades, PF at least 1.40, average at least $12,
positive four-tick net, bootstrap lower bound above zero, both half-years
positive, and activity in at least six months. Advance at most one of each.
Size-up remains diagnostic and never authorizes real size.

## Output and safety

Persist immutable research evidence only to `valor_mes_v41_results`, plus local
JSON/CSV output. Record years opened, source hashes, every cell, monthly results,
drawdown, win/loss clusters, and the selected ledger. `HISTORICAL_CANDIDATE`
would still require untouched 2026, executable-fill calibration, and forward
shadow evidence before any live use.
