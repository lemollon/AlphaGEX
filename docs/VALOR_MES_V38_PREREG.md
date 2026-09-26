# VALOR MES v38 preregistration: volume pressure and price response

## Decision and mechanism

Test whether MES opening-bar close location weighted by observed volume provides
a useful pressure proxy when paired with the independent opening price response.
Agreement tests continuation; disagreement tests apparent absorption or
rejection. The signed-volume measure is explicitly an OHLCV proxy, not true
aggressor-side order flow.

Research only. Read the existing Databento `MES.v.0` one-minute cache in a
read-only transaction. Use 2023 for discovery, then open 2024 and 2025 only
through the sequential firewall. No vendor request, broker, paper deployment,
production, sizing, scheduler, or Render change is authorized. Calendar year
2026 remains sealed.

## Causal construction

- Use audited v8 complete MES cash sessions with finite OHLCV geometry,
  nonnegative volume, 0.25-point tick geometry, monotonic timestamps, no
  duplicates, and one exact contract.
- The observation window is exactly 08:30-08:59 CT: 30 completed one-minute
  bars. Decide only after the 08:59 bar and enter the 09:00 MES open.
- Per-bar close-location value is
  `CLV = ((close-low) - (high-close)) / (high-low)`. Set CLV exactly to zero
  when `high == low`.
- Signed-volume pressure is `sum(volume * CLV) / sum(volume)`. Exclude the cash
  date when total observation-window volume is not positive.
- Opening price response is the 08:59 close minus the 08:30 open. Pressure and
  price-response signs must both be nonzero.

## Frozen family

Modes, in fixed order:

1. `flow_follow`: pressure and price response have the same sign; trade that
   sign.
2. `absorption_reversal`: pressure and price response have opposite signs;
   trade the price-response sign, equivalently opposite the pressure proxy.

Pressure regimes, in fixed order:

1. `all`: no pressure-magnitude threshold.
2. `causal_high`: absolute current pressure must be at least the median absolute
   pressure of the prior 60 usable cash sessions. The current session is
   excluded and all 60 prior observations are required.

For every mode/regime pair, test fixed holds of 30, 60, 120, and 240 completed
minutes. Enter the exact 09:00 MES open and exit the exact corresponding MES
close. Missing bars, timestamp gaps, unavailable exits, or a contract change
skip the trade. This is 16 cells in written mode, regime, and hold order, with at
most one trade per date per cell.

No stop, target, trailing exit, GEX, overnight input, cross-market input, second
volume threshold, or after-result filter is allowed.

## Costs, selection, and firewall

MES point value is $5 and tick size is 0.25. Report raw P&L and a $3 assumed
round-trip fee with 0, 1, 2, and 4 adverse MES ticks per side. These are
trade-print planning scenarios, not executable bid/ask evidence.

Discovery uses 2023 only. A cell is eligible with at least 60 trades, positive
two-tick net dollars, two-tick profit factor at least 1.10, two-tick average
trade at least $8, and positive four-tick net dollars. Rank eligible cells by
two-tick net-to-maximum-drawdown, then average trade, then fixed written cell
order. Select exactly one cell. If none qualify, 2024 and 2025 remain unopened.

Evaluate the selected cell unchanged in 2024 and then, only after a 2024 pass,
in 2025. Each validation year requires at least 60 trades and the same financial
gates. Final historical promotion also requires the combined 2024-2025 usable-
session day-cluster bootstrap 95% lower confidence bound for mean two-tick daily
P&L above zero, using 10,000 resamples and seed `380038`, including zero-trade
usable days.

Report all 16 discovery summaries, every opened validation year, all cost views,
monthly P&L, maximum drawdown, session exclusions, and a reviewable selected-
trade CSV. A pass is `HISTORICAL_CANDIDATE`, not live profitability;
executable-fill calibration and forward paper evidence remain mandatory.
