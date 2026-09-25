# VALOR MES research status

- **Current version:** v31
- **Current stage:** implementation verified locally; production research run pending
- **Latest settled result:** v30 completed with 15,114 opportunities and no viable variant
- **Current blocker:** broker execution calibration contains 118 quote changes, zero historical fee rows, and no calibrated slippage; 1 tick/side is therefore an unverified planning proxy
- **Next action:** run the fixed v31 edge matrix against cached 2023-2025 MES bars, inspect all-year survivors and loss clusters, then build v32 only if the evidence supports a regime router

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
