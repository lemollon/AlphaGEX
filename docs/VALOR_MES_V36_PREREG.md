# VALOR MES v36 preregistration: overnight inventory transfer

## Decision and mechanism

Test whether the full MES Globex overnight path creates cash-open inventory that
either continues when the first five cash minutes confirm it or unwinds when
those minutes reject it. Prior MES work used only a cash-open gap scalar; v36
uses the entire observed overnight path, its directional efficiency, and an
independent cash-open response.

Research only. Read the existing Databento `MES.v.0` one-minute caches in a
read-only transaction. No vendor request, broker, paper deployment, production,
sizing, scheduler, or Render change is allowed. Calendar year 2026 stays sealed.

## Causal session construction

- Validate raw MES timestamps, OHLCV geometry, tick grid, duplicates, and exact
  contract identity with the v8 engine.
- A cash date is usable only when its 08:30-to-close cash session is complete and
  one exact MES contract is present.
- Its overnight window is 17:00 CT on the preceding calendar day through 08:29 CT
  on the cash date. Use only observed trade bars; do not forward-fill missing
  minutes. Require the first observed bar no later than 17:05, the last observed
  bar exactly 08:29, at least 900 observed minutes, at least 55 of the final 60
  minutes, monotonic timestamps, and one exact contract matching the cash
  session. The known daily maintenance break is outside the window.
- Overnight return is first observed open to 08:29 close. Directional efficiency
  is absolute overnight price change divided by the sum of absolute consecutive
  observed close changes, including first-open to first-close. The last-hour
  return is the first observed close at or after 07:30 to the 08:29 close.
- Prior ATR is the simple mean true range of the preceding 20 complete cash
  sessions for the same contract-continuous daily series. Current-day data never
  enters it. Require all 20 observations and positive ATR.
- The cash-open response is 08:30 open to 08:34 close, using five complete bars.
  Decide after the 08:34 bar and enter at the 08:35 MES open.

## Frozen discovery family

Require absolute overnight move of at least `{0.25, 0.50}` prior ATR and
directional efficiency of at least `{0.05, 0.10}`. Test two mechanism modes:

1. `confirmed_continuation`: overnight return, final-hour return, and first-five-
   minute response all have the same nonzero sign; trade that sign.
2. `opening_rejection`: the first-five-minute response has the opposite nonzero
   sign to the overnight return; trade the opening-response sign. The final-hour
   sign is reported but does not gate this mode.

For each mode/magnitude/efficiency combination, test fixed holds of `{30, 60,
120}` completed minutes. This is 24 cells. One position is possible per cash
date by construction. Exit at the exact hold-minute close, never past the v8
five-minute pre-close boundary. Missing entry/exit bars or a contract change skip
the trade; no price is invented. No stop, target, GEX, cross-market input, volume
threshold, or after-result filter is allowed.

## Selection, costs, and firewall

MES point value is $5 and tick size is 0.25. Report raw P&L and a $3 assumed
round-trip fee with 0, 1, 2, and 4 adverse ticks per side. These are trade-print
planning scenarios, not executable bid/ask evidence.

Discovery uses 2023 only. A cell is eligible with at least 80 trades, positive
two-tick net dollars, two-tick PF at least 1.10, two-tick average trade at least
$8, and positive four-tick net dollars. Rank eligible cells by two-tick
net-to-maximum-drawdown, then average trade, then the written mode, magnitude,
efficiency, and hold order. Select one cell.

Open 2024 only for that unchanged cell. It passes with at least 60 trades and the
same four financial gates. Open 2025 only after a 2024 pass and apply the same
gate. Final historical promotion also requires the combined 2024-2025
day-cluster bootstrap 95% lower confidence bound for mean two-tick daily P&L
above zero, using 10,000 deterministic resamples including zero-trade usable
sessions.

Report every opened year, all 24 discovery summaries, monthly P&L, maximum
drawdown, session exclusion counts, and a reviewable selected-trade ledger. A
pass is `HISTORICAL_CANDIDATE`, not live profitability; executable-fill
calibration and forward paper evidence remain mandatory.
