# VALOR MES v32 research status

- **Current version:** v32
- **Current stage:** compact router implemented and focused tests passing;
  cached 2023-2025 research run pending
- **Research environment:** cached Postgres MES development data only
- **Live/production impact:** none; no trader, broker, sizing, routing, scheduler,
  or root Render configuration changed
- **Execution boundary:** trade-print proxy; the one-tick planning case is
  unverified and is not labeled realistic
- **2026 status:** untouched
- **Verification:** 11 focused v31/v32 tests pass, including prior-date-only
  thresholds, same-day batching, warmup, global non-overlap, cost accounting,
  and autorun isolation; Python compilation passes
- **Next action:** run the fixed 2023-2025 study, inspect the annual promotion
  audit, and leave production unchanged regardless of the historical outcome

## Frozen scope

The runner evaluates only `combined_baseline`,
`atr_low_tercile_exclusion`, and `atr_tercile_shadow_router` on the four frozen
v31 raw-gross survivors. ATR thresholds and shadow performance are prior-date
only, same-day updates are batched, and the selected portfolio holds at most one
MES position at a time.
