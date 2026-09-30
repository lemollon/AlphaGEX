# Three-year Spark and Flame replay — running

Baseline: AlphaGEX `3637fd18396b9ab532ee0d9bd42281338353a8a2` (September 28, 2026).
Window: September 29, 2023–September 28, 2026; 751 regular or half-day sessions.
Separate accounts: Flame $2,000; Spark $5,000. No subsequent deposits.

## Profiles

1. Current customer package: 20% base sizing; N=3/K=.10 variant-G floor;
   $50 margin; pre-trigger calm +1; post-trigger calm +1 subject to $4,000
   deposit minimum; customer FLINT netted against actual/planned host risk.
2. Internal ONE_STRATEGY: identical pure sizing functions plus internal
   liquidity caps and the literal current internal FLINT planning caller.
3. Legacy high-water dollar-rung ladder, FLINT and Flame favorable upsize.
4. Legacy profit ladder plus per-bot fast-start rules and FLINT.

These are SEPARATE profiles. The superseded dollar-rung ladder is not stacked
on top of the September 28 customer sizing package.

Each profile runs natural bid/ask and 3-cent adverse entry/close cases.
FLINT and XSP routing are enabled. Missing XSP quotes use the source's SPY
fallback. An accepted XSP swap without authentic SPX settlement is unresolved.
Main default profit target and conventional stop are disabled. Put/call
assignment-guard buffers are $.50/$.25, checked during the final three minutes
before the actual close. Entries retry within the source-default bot windows.
Source defaults are frozen; account-specific DB overrides are not applied.

## Data and execution boundaries

The private ThetaData proxy supplies SPY minute bars, official daily closes,
and historical option bid/ask/depth. Stock minute OPEN is the contemporaneous
spot proxy; quote snapshots are not verified broker executions. Spread prices
use sell-bid/buy-ask with checks on the required execution sides. A zero-bid
long contributes zero sale proceeds at buyback; its zero bid size does not
invalidate the short option's valid ask. Positive long bids require size. Fees are $1.40 per spread,
with $50 monthly subscription reported externally over 36 billing cycles.

Historical gamma now uses a uniform reconstruction across the requested window,
including 20 pre-window warmup sessions. Inputs are historical ThetaData closing
chains from the prior session, morning OI (reported as the prior session's
closing OI), and SPY spot at 11:05 ET. The once-per-day shared gamma context
mirrors the scanner's morning Spark evaluation before Flame.

For each 0..60 DTE contract, infer prior-close IV from quote mids using
Black-Scholes (r=.045, q=.012), then recompute gamma at the entry time and spot.
Apply gamma × OI × 100 × spot² × .01, summed separately over calls and puts.
Missing/unusable contract IV is reconstructed from the same-expiry, same-side
prior IV curve: interpolate variance between strikes and use flat endpoint IV
outside its observed wings. Counts of interpolated/extrapolated contracts are
reported. For an entirely missing same-side expiry, interpolate total variance
between surrounding observed expirations at the same strike, or use nearest-expiry
IV beyond the observed maturity range. Term interpolation/extrapolation counts
and affected expiry/side pairs are reported explicitly. A day without any
usable prior same-side surface still fails; missing positive OI is never dropped.
The prior-close bulk lookup is supplemented with exact expirations omitted
by weekend/holiday DTE shifts, before using any term surface estimates.
Time-to-expiry uses actual half-day closes, with a five-minute lower bound.

The native p67 / 20-session upsizing function compares this reconstruction
against its own trailing values. No Tradier observations are spliced into the
modelled series. This validates the modelled historical hypothesis; it does not
prove exact agreement with historical Tradier Greeks or broker executions.
The full-feature exact-validation flag remains false for that reason.

The existing long net-gamma baseline lives in SpreadWorks; it is not used as a
replacement for FLINT's call-side gamma input. XSP historical quotes are read
per selected contract; settlement uses the CBOE SPX history CSV's SPX column /10.
Explicit provider no-observation responses are recorded as quote absences.

The event blackout master is disabled in frozen source. Historical NYSE
closures include January 9, 2025, independently of the source's limited
2025–2027 calendar. Flame's afternoon entries skip half days; Spark's morning
entry remains eligible and its guard uses the early close.

The collector retries individual requests. Transport failures (fetch/abort/timeouts,
429, and provider 5xx) now roll back the entire attempted day and retry that
same day with capped 15/30/60-second waits. The last successfully completed
session is checkpointed while waiting, including the retry phase. Neither the
completed count nor account equity advances across a missing day. A permanent
schema, identity, or data-integrity error stops immediately at the failed date.
History and gamma warmup use the same transport recovery. Independent SPX
history must load before replay. Missing payoff data invalidates account paths. Partial paths cannot be presented as complete.
Intraday mark gaps are counted; marked drawdown is an observed bound when
coverage is incomplete.

## Verification completed

- Pure-function boundary checks: sizing, calm add-on, floor/cushion, guard
  costs, CSV decoding, timezone conversion, holiday exclusions.
- Synthetic integration: 16 account paths, scaled P&L and fees, adverse fills,
  XSP fallback, no orders. This is NOT a market-performance result.
- 24 isolated fault-injection regressions: bounded provider retries/timeouts,
  explicit no-data handling, provider/contract identity, weekend expiry supplements,
  strike and term IV surface estimates, same-side missing surfaces, future-data
  and mixed-source exclusion, early closes, independent XSP settlement, missing
  marks/guard quotes, isolated DB enforcement, exact checkpoint restoration,
  code-version mismatch, checkpoint corruption, and failed-day account rollback.
- Mutation verification: deliberately removing retries, the weekend supplement,
  or account restoration causes the suite to fail in each case.
- The existing research test entrypoint requires the hardening suite, so the
  configured Render build command runs it automatically on future deployments.
  Fault tests use synthetic inputs and an in-memory database; they never contact
  providers or a real database. Native self-tests run separately outside the VM.
- Node syntax and whitespace checks.

## Execution

Node 24.19.0. The isolated checkpoint store uses pinned pg 8.16.3; no broker SDK is loaded.

```sh
node research/spark_flame_current_3y_20260928.cjs --self-test
node research/spark_flame_current_3y_20260928.test.cjs
node research/spark_flame_current_3y_20260928.cjs
```

The remote job needs `THETADATA_BASE_URL=http://thetadata-proxy:10000` in the
same Render region/network. All status/result endpoints require the
`RESEARCH_ACCESS_TOKEN` bearer token. Only `/health` is unauthenticated and
contains no strategy, progress, or results.

Checkpoints are gzip-compressed state in the isolated alphagex_backtest database,
in spark_flame_research_checkpoints. The connection is an environment secret.
The job verifies the database name before creating or writing that research table.
Keys include the run ID and both research source hashes, so a changed version
cannot reuse an old performance result. A restart resumes the same fresh run;
completed results stay retrievable after an idle restart. Raw CSV files remain
process-local; their scope, retrieval timestamp and SHA-256 hashes are retained.
Reports and trades are also exported by the read-only observer. No live trading code, customer
balances, credentials, kill switches, or production database schemas change.

## Current status

User approved the authenticated free research service on September 29, 2026.
The earlier run stopped during gamma warmup on September 18, 2023, before
any backtest sessions completed. The prior-close 61-DTE request omitted an
expiry within Monday's 60-DTE band. Exact-expiry supplemental requests now
correct the weekend/holiday mismatch. The updated runner also calculates and
flags missing expiry surfaces from observed prior-session term variance.
The corrected runner passed the blocked September 18, 2023 warmup date with
all 2,324 positive-OI contracts included and zero unpriced contracts. As of
September 29, 2026 at 8:48 PM CT, the live run had completed 145/751 study
sessions with no data errors or unresolved account paths. Final results remain
pending. Adding the reliability tests did not restart or change this run.

Service: https://dashboard.render.com/web/srv-dau3ni7lot8c739htsv0
Execution branch: `research/spark-flame-current-3y-20260928`.
Recovery runner commit: `4d2855748888cd36a12591a4cab2ef11f048102f`.
Recovery regression commit: `3780010a0998d85059d08a059cd7afd9f3825ca0`.

A read-only observer polls authenticated status every 45 seconds and saves
existing report/trade/daily exports every five minutes. Quotes retrieved
within this run are reused for later scanner minutes of the same contract.
The collector requests historical market data only and never sends orders.
The observer now keeps checking after blocked/incomplete states rather than
exiting. It logs non-advancement after ten minutes, using stage, date, request
count, completed count and run start time. It records failures; it cannot
repair a new failure or deliver a proactive notification by itself.

Regular-session stock bars exclude intervals starting at the market close.
Expiry settlement uses the independently retrieved official daily close;
empty post-close OHLC records do not invalidate prior session trades.

Verification: the independent CBOE SPX settlement series contains every one of
this replay's 751 requested sessions. Contract-level XSP quote availability
is checked during execution; missing observations follow the native SPY fallback.

## September 29 overnight recovery

The prior run recorded transport failures on June 21 and June 24, 2024.
It continued diagnostically, so those paths are invalid and will not be
presented as completed returns. The corrected collector waits for the same
session instead of skipping it. A fresh run under a new source-hash key is
being deployed; no old equity/performance checkpoint is reused. Production
strategy rules and the September 28 baseline remain frozen. Three new tests
verify same-day state rollback/retry, permanent-error classification, and
checkpoint recovery while waiting. All 24 fault tests and all mutation checks
passed before deployment. Final export reconciliation has seven tests and
must pass across all 751 sessions and 16 paths before delivery.


## September 30 guard-quote recovery

The ec9ce9ff engine processed all 751 sessions, but final export reconciliation
failed: five Spark paths had an unresolved November 24, 2025 FLINT guard exit.
Eleven paths reconciled. The full study is therefore not complete and its
unresolved compounded results must not be delivered as valid performance.

A bounded read-only research probe reproduced the identical source CSV hashes.
The SPY 669 call at 15:57:00 ET had bid $0.53 and ask $0.48; the crossed quote
was correctly rejected. The 671 call long had bid $0.00. Authentic one-second
history first supplied synchronized valid quotes at 15:57:02 ET: short bid/ask
$0.48/$0.48 with ask size 23, long bid $0.00. No theoretical price is substituted.

The new research runner scans the first valid synchronized one-second quote
only within a triggered guard minute when the minute quote cannot support an
exit. It records the quote timestamp and modeled execution delay in quoteRepair.
No future minute, stale quote, price interpolation or broker execution claim is
used. Unresolved day exits now stop immediately and roll back the whole day.
XSP transport/provider errors also propagate rather than being silently treated
as absent XSP quotes. Genuine provider 404 absence retains native fallback.

All 28 fault tests, the native/integration tests and seven reconciliation tests
pass. The new numerical engine SHA-256 is
`75214ba4a85515a0e8700b9e388ec569bbb6222d927fb4f199ce0f6e8398e583`.
The gamma helper remains
`d86d19ebc95421cbc1cb1ac06a756554bf230967a47e3c6c1c2ef1b3be7d909f`.
A fresh full replay starts under the new hash; no prior account results are
reused. The September 28 production baseline and live strategies remain frozen.
The final ZIP is withheld until all 751 sessions and all 16 paths pass audit.
