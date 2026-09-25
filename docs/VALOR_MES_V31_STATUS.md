# VALOR MES research status

- **Current version:** v31
- **Current stage:** cached 2023-2025 edge map completed; isolated Render runner suspended
- **Latest settled result:** 570 annual cell rows, 1,140 loss-cluster rows, and
  2,508 diagnostics. Four raw-gross cells were positive in all three years, but
  none survived fees in all three years and none survived the one-tick planning
  case in all three years.
- **Current blocker:** broker execution calibration contains 118 quote changes, zero historical fee rows, and no calibrated slippage; 1 tick/side is therefore an unverified planning proxy
- **Next action:** run the frozen v32 ATR regime-router audit on the four
  raw-gross survivors; keep 2026 and production untouched

## Completed v31 decision

- Gross all-year survivors: 30-minute afternoon momentum, 60-minute afternoon
  momentum, 120-minute late-morning momentum, and 120-minute opening-morning
  mean reversion.
- Their gross average trades were too small to cover even observed fees in
  every year. They are research inputs, not executable strategies.
- Low ATR was the only repeated, same-sign loss-cluster diagnostic with useful
  separation across all three years, and only for the 30-minute afternoon
  momentum and 120-minute opening-morning mean-reversion cells.
- This supports one preregistered v32 regime-router audit. It does not support
  a live strategy, a realistic-execution claim, or opening 2026.

## Frozen v31 design

- 2023-2025 development data only; 2026 remains untouched.
- Decisions every 15 minutes from 08:45 CT when enough completed history exists.
- One fixed signal: sign of the completed trailing 15-minute return.
- Directions: momentum and mean reversion.
- Holds: 15, 30, 60, and 120 minutes, always exiting by the 15:00 CT cash close.
- Entry buckets: opening/morning, late morning, midday, afternoon, and late session.
- One MES position at a time inside each independently evaluated cell.
- Fill proxy: next-minute trade-print open to final hold-minute trade-print close.
- Cost views: gross; $3 fee with 0, 1, 2, and 4 adverse ticks per side.
- The 1-tick case is not labeled realistic until broker fills and fees calibrate it.
- No VALOR trader, scheduler, broker setting, or production strategy rule changes.
