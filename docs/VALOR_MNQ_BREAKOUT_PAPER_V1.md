# MNQ breakout paper-forward rollout v1

User scope: update MNQ to the 30-minute breakout candidate after the strict-cash historical study. This implementation is PAPER ONLY. No real-money order is authorized. Other instruments keep their existing strategy paths.

## Rules

- Signal: the latest fully completed one-minute MNQ close is strictly above the high, or below the low, of the PRECEDING 30 completed one-minute bars. This is a rolling range, not just the opening range. The signal bar is excluded from the range.
- Require 31 contiguous, timezone-aware, tick-grid-valid OHLC candles for the same exact quarterly MNQ contract. Candles come from the existing OAuth/DXLink Candle feed, not ETFs, Yahoo continuous prices, or sampled quote approximations. Missing/stale/invalid candles block entries; there is no GEX fallback.
- At most one open MNQ position, exactly one contract. Only paper mode is permitted. Existing database cooldown, pending-intent barrier, daily-loss and margin checks remain in force.
- Entry window: 08:30 through before 14:55 America/Chicago on a full cash session; before 11:55 on an early-close session. Holidays and the January 9, 2025 closure are explicitly represented. Calendar coverage ends in 2026; later dates fail closed until reviewed.
- Entry is the first usable current paper execution after the completed-bar decision, with a maximum delay of 45 seconds from the planned minute boundary. No retroactive next-open fill is invented. The quote must identify the same actual contract and satisfy the existing freshness checks.
- Persist the exit deadline at entry: the earlier of planned entry plus 240 minutes or five minutes before the cash close. A restart does not extend that deadline.
- Exit uses the actual observed paper bid/ask fill when due. Delays are recorded in the close reason. A missing quote keeps the position open and blocks another entry; it does not fabricate a timely exit.

## No protective stop: deliberate paper-only restriction

The research candidate had time/pre-close exits, not a protective stop, profit target, SAR, or trailing stop. This paper implementation preserves that definition. Public position risk and stop fields are null where stop-defined risk is unavailable, not zero risk. The historical candidate's reported annual closed-trade drawdown reached $5,152 under stress; real intratrade risk may be worse. Adding protective stops requires a separate research version and no live promotion is made here.

The source MNQ_BREAKOUT_30M is refused by independent order-validation, execute-signal, direct-live-entry and direct-live-close guards. New GEX/SAR entries for MNQ are not opened. Old MNQ positions retain their original management and pending broker-fill reconciliation; history is not relabeled or reset. If global mode changes to live, this paper strategy does not trade and its paper positions are not sent to a real broker.

## Comparison boundaries

The historical study was `valor-cash-v8-20260923-30608e350e634ed2`, price-only `breakout_30m`, 240-minute maximum. Its 2023-2025 diagnostic totals were $20,386 at modeled baseline costs and $17,396 under stress across 1,495 trades, with no unresolved positions. Those results are not deposited into the account or represented as forward profit.

Forward execution differs from the bar simulation: observed bid/ask plus the existing paper execution configuration replaces idealized minute-open fills. Boundary polling latency, current actual contract choice, source-vendor candle construction, portfolio/margin guards and cooldowns can differ. The status reports the actual configured paper fee/slippage; it does not claim the historical $5/$7 cost assumptions were broker-verified. GEX/Bayesian probabilities are not used or described as calibrated for this strategy.

New trades and scans carry MNQ_BREAKOUT_30M and structured versioned decision metadata, including the raw candle snapshot hash, timestamps, range, scheduled exit, code version and quote evidence. The status API exposes separate forward counts/P&L; the frontend displays the paper-only, time-exit warning. Existing aggregate history still includes legacy strategies, so use the source-filtered breakout record for evaluation. New outcomes are excluded from the old GEX ML training and do not update its Bayesian/direction feedback loop.

## Operational controls

`VALOR_MNQ_BREAKOUT_PAPER_ENABLED` defaults to true for this user-requested paper rollout; set false to pause NEW breakout entries. Pausing does not disable exits or resume the old GEX strategy. Restarts and duplicate scans are guarded by a deterministic per-contract/minute order intent plus the existing cross-process lifecycle lock. No balances, old trade rows, other ticker settings, or live-mode configuration are reset.

A normal main deployment restarts the API. The workflow and changes do not create a paid data subscription or issue Databento downloads. Read-only existing broker market-data access is used. Cold-start candle collection may block a scan briefly; it is bounded and cached per completed minute while the existing position monitor remains active.

## Tests and outstanding validation

47 offline tests passed locally and in the isolated GitHub integration job on September 23, 2026. Tests exercise the real pure strategy, models, adapter and selected existing execution methods; database, locks and broker are mocked. They cover causal ranges, partial-bar exclusion, data validation, timing and DST, early closes, stop/risk representation, one-contract/mode restrictions, durable deadlines, exact-contract requirements, live-entry/close refusal, legacy reconciliation preservation, no GEX feedback contamination, and margin/position guards.

The integration workflow also compiles Python and transpiles the changed TSX for syntax. This is not a full application TypeScript build or a verified authenticated Candle subscription. Deployment/runtime checks and the next cash-session feed/entry/exit observation remain required before treating forward operation as confirmed. Unit tests and historical profitability do not certify live trading.
