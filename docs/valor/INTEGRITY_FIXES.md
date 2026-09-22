# Valor lifecycle and performance integrity fixes

This change preserves every historical trade and the raw paper balance. It does not enable live trading, rewrite historical fills, reset the account, or retrain/approve a model.

## Behavior

- Serialize entry, management, SAR and close operations across processes with a PostgreSQL advisory lock. Nested operations share the lock. Lock/database failures cannot authorize an order.
- Allow one open position per instrument and at least 60 seconds after its last open/close before another entry. Checks query the database, so they survive restarts. Existing multiple positions remain managed to exit.
- Record durable order intents before execution. An uncertain broker submission or failed post-execution persistence leaves a pending intent that blocks further entries for that instrument. Live closes also have a durable intent to prevent duplicate orders.
- Quarantine CL new entries by default, including SAR paths. Existing CL positions remain monitored. Configuration explicitly exposes `quarantined_tickers` and `entry_cooldown_seconds`.
- Run exits before scan entry/loss-limit gates; enforce the configured maximum holding time in the frequent monitor before trailing logic. Never fabricate an entry-price exit when quotes are unavailable. Market closures and quote outages can still delay an exit; those trades are excluded from screened research.
- Paper fills use the correct instrument's current bid/ask. Store the actual simulated entry price; stop exits account for observed gaps instead of assuming the requested stop filled perfectly. Reject stale/missing-time, non-finite and crossed quotes. Yahoo is paper-only; ETF-derived futures fills are removed.
- Commit paper position insertion/closure and account P&L/margin changes in the same transaction. Count zero-P&L closes. Duplicate saves do not reopen positions or allocate margin twice.
- SAR closes its original leg and routes any reversal through the common order path. The cooldown generally suppresses the immediate reversal; it no longer creates a database-only position.
- OAuth uses `/oauth/token`, Bearer authorization, expiry-relative refresh, and a product User-Agent. Retired password authentication is not used. Broker acceptance without a confirmed positive fill is not booked as a completed trade. Live entry symbols use the signal's ticker.

OAuth protocol reference: https://developer.tastytrade.com/docs/authentication/oauth2/

## Screened reporting

`GET /api/valor/performance/quality` returns raw/excluded counts, gross paper P&L, expectancy, profit factor, realized drawdown, mean MAE/MFE, and ticker/regime/direction/source/hour buckets. The dashboard labels its existing balance as raw and links this report. The non-destructive `valor_trade_quality` view is installed with Valor's normal schema initialization.

Screen v1 excludes recapitalization records, invalid records, watchdog closures, excessive holding periods and entire duplicate-candidate clusters. Duplicate candidates match instrument/contract, side, quantity, entry/exit prices and entry/exit seconds. These are heuristics, not proof that every excluded trade was invalid or every retained trade was real. Priority classification assigns one exclusion reason per row.

ML training samples must link to an eligible position. New watchdog outcomes do not update Bayesian or external learning feedback. Previously trained models and accumulated trackers are not retroactively repaired; review/retrain them on screened data before relying on them.

Historical quotes, contract rolls, commissions, slippage and executable liquidity cannot be reconstructed from the ledger. Metrics are gross, realized-only paper statistics, not net executable returns. No Sharpe ratio is claimed from these transaction-level observations.

## Validation and deployment

Targeted command:

```sh
python -m pytest -o addopts='' tests/test_valor_integrity_fixes.py tests/test_valor_rty_gate.py -q
```

The screened performance SELECT was executed successfully against the live Render database in a read-only CTE, without creating a production view or changing data. The older overnight/GEX suites have 11 failures and 5 setup errors, reproduced identically on untouched main at 307e7d7 (fixtures omit ticker/win_tracker arguments and contain outdated expectations).

Deploy this branch through the normal review process. Verify the additive view/table migration, monitor heartbeat, single-position entry rule, CL quarantine, and quote availability. The stricter quote rule can stop paper entries if only delayed Yahoo data is available.

Pending intents are deliberately not automatically retried or deleted. For a live intent, reconcile broker order status, quantities and fills against its external identifier and local ledger before marking it complete. This patch does not implement an asynchronous broker-fill reconciler; it fails closed on uncertain results. No real-money readiness or live broker execution test is claimed.
