# Execution calibration — evidence before settings

Run `python -u scripts/calibrate_valor_execution.py` in the deployed Render shell.
No application imports, broker order methods, trading settings writes, resets,
or live-mode changes are used. Broker reads use the installed tastytrade SDK.
Only a new research table, `valor_execution_calibration`, is written. It stores a
checksummed gzip evidence bundle and JSON summary. Account numbers and secrets
are never printed or stored in that bundle. Defaults: 30 days of futures history,
60 seconds of changed MES streaming quotes; 25,000 history rows and 50,000 quote
events maximum. A truncated history window is explicitly flagged.

The configured TASTYTRADE_ACCOUNT_ID is used. Otherwise a single non-test-drive,
open, futures-approved account must exist. Account ambiguity or missing history
is reported; it never triggers account selection by guess or new real orders.

Fee analysis retains signed broker fee components, including credits/rebates,
and reconciles them to signed value minus net value. Exclude estimated fees,
reversed transactions, missing fee components, and reconciliation mismatches.
Report opening and closing cost per contract separately, by futures product.
Do not substitute a missing product/side with a zero fee or pool different
products. Historical rates are observations; subsequent adjustments still need
review. No fee setting is changed automatically.

Shadow scenarios test 100/250/500/1000 ms delays, 1/5 contracts, both sides, and
100%/50% of displayed liquidity. Each hypothetical order uses the first changed
book observation at or after assumed arrival (maximum additional gap 2 seconds).
Displayed quantity is used only once, and any unfilled remainder stays unfilled.
This is top-of-book sensitivity analysis, not a queue/depth or partial-fill
prediction. Scenarios are independent alternatives, not cumulative trades.
Observed delay is recorded because event spacing may exceed assumed latency.

A minute of observations cannot justify production latency/slippage parameters.
Historical fills without contemporaneous arrival quotes cannot establish actual
broker slippage, and transaction execution times alone cannot measure client-to-
exchange latency. Zero broker quote times remain explicitly unverified; local
reception does not prove exchange freshness. Existing paper settings stay in
place until the collected evidence is reviewed. The next step is per-product fee
review and repeated session samples; real orders are not required by this probe.

SDK reference: https://tastyworks-api.readthedocs.io/en/latest/api/account.html
