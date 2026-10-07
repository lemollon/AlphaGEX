# Permanent options report requirements

The executable contract is `backend/report_contract.py`; inference and display
rules are `backend/report_policy.py`. Version `2026-10-07.1` retains all 179
original fields and adds day/near-forward/forward plans, horizon comparisons,
adaptation rules, data integrity and persisted visual delivery: **32 sections and 241 required fields**.
Every delivered report carries its policy version and SHA-256 schema/rule hash.

## Reader experience

Morning, opening and intraday reports use the same dark layout: Today's mission,
a 30-second scoreboard, a Today vs forward table, the entire required contract,
and eleven PNG panels. HTML shows the charts beside their corresponding topics.
The original panels and data points remain present. Missing observations have
source-specific reasons; dated last-known observations retain their clocks.
Arbitrary model narrative is stored only for diagnosis and cannot introduce
facts into the canonical rendered report.

## Website and historical archive

The private Report Desk reads the same persistent `sw_full_reports` snapshots
and stored chart bytes as scheduled delivery. `/reports/history` provides bounded
date/type pagination in America/Chicago and excludes diagnostic verification
runs; `/reports/{id}/data` exposes the immutable full contract to the reader.
Reading either route never collects market data, changes a report, sends a
notification or executes a trade. All newly persisted morning, opening and
intraday reports appear automatically without a second report schedule.
The website retains all 32 sections/241 fields and reconciles all eleven chart
categories; absent observed data receives an explicit reason, not a fake chart.
Historical report generation and observation clocks remain separate from the
website's retrieval time. Older ENTRY_READY states are historical alert states,
never current execution instructions. A network failure retains the last loaded
archive with an explicit offline notice.

## Durable chart delivery

All report kinds use the same persisted PNG bytes. Before publication, chart
bytes are read back from Postgres, decoded and checked against their SHA-256
identity, dimensions and dark palette; the delivery manifest is a required field.
The HTML embeds verified PNG bytes as data URIs, so charts require no separate
image requests. Missing/corrupt stored images show one explicit delivery error,
never a broken image tag. Old stored reports use the same repaired view path.

`/reports/{id}/assets` returns verified PNG bytes, checksums, sizes, observation
clocks and plotted-data flags. `/charts.pdf` and `/portable.zip` are portable
backups. The ZIP contains the full HTML/Markdown, PNGs, manifest and chart PDF.
The HTML and PDF remain viewable offline. A partial/corrupt image batch returns
503 from export routes rather than silently claiming successful delivery.

ChatGPT delivery must use `scripts/materialize_options_report.py` to decode the
asset JSON (or the same persisted bytes from the read-only Postgres fallback),
validate every selected image and atomically write current-conversation files.
Use only panels with observed data. Inspect PNGs and save them as durable
attachments before linking them; temporary sandbox paths alone are not proof of
upload success. Retain the downloadable chart PDF and canonical report link in
each delivery. If attachment upload fails, disclose it and use those portable
backups. External ChatGPT upload availability cannot be guaranteed by backend
code; never claim an upload succeeded from a valid local PNG alone.

## Day and forward plans

The day plan concerns today's trading session, even when its selected option
expires later. Near-forward evidence covers the next 2–5 trading-session dates;
the longer plan covers 1–4 calendar weeks. Forward sentiment uses actual matching
option expirations and retained strike concentrations; 0DTE pressure alone never
creates a forward thesis. Futures observations are separate confirmation, with
their real contract symbols and clocks; delayed ES is not an executable MES
quote. An exact basis still requires synchronized futures and actual index data.

Each plan includes thesis, evidence/conflicts, registered trigger/invalidation,
conditional structure, matching qualified contracts, lifecycle, liquidity/quote
qualification, risk/exit rules and catalysts. A forward watch is not an entry.
ENTRY_READY requires the same setup's watcher state and confirmation evidence,
fresh underlying proof and matched fresh per-leg BBO. Stale entry quotes downgrade
the publication to WATCH. An open paper trade is never presented as a closed win.

Every report retains the first same-session morning baseline and compares the
previous scheduled checkpoint. Verification/startup reports, other sessions and
future timestamps are excluded. Expected-move usage uses the frozen morning
dollar estimate and bounds; repriced current IV stays separate.

## Integrity and failure behavior

Source timestamps require a timezone and cannot be in the future. Age is
recomputed at publication, not copied from receipt. Market observations exceeding
90 seconds become historical; they are never refreshed by drawing a chart or
rereading an immutable report. Nested macro/futures observations retain their
own clocks. Malformed/nonfinite/low-confidence observations and mock/fixture
provenance are rejected. Empty paper samples have no win rate. Flow contract and
premium aggregates must reconcile with classified/unclassified buckets.

Optional collector/read errors are bounded and isolated, with concrete failures
in Data Integrity. A model-enrichment failure still attempts the deterministic
evidence report with missing setups disclosed. Failed sources are not repaired
by fabricating data. A database outage can still prevent durable storage; an
upstream entitlement or timeout can still prevent observed data completeness.
The format may be complete while data completeness remains INCOMPLETE.

Before persistence or notification, the final renderer verifies every section
and field, policy identity, source clocks and embedded PNG references. All eleven
generated PNGs are decoded and checked for dimensions/dark palette by assembly.
Production rejects mock mode; presentation examples never enter this pipeline.

## Notification recovery

Existing destinations and schedules stay enabled. Intraday and opening delivery
use an atomic per-date/hour/kind lease and success record. Recovery ticks retry
failed assembly or transport; successful recorded sends are skipped. This avoids
normal duplicate sends across retries/restarts. A crash after a webhook accepts
but before the database records success can still duplicate delivery because the
external webhook has no transaction/idempotency key. No exactly-once guarantee
is made. Morning retains its existing immutable-plan notification recovery.

## Regression gate

From the repository root:

```sh
python -m pytest spreadworks/tests/test_report_policy.py \
  spreadworks/tests/test_full_options_report.py \
  spreadworks/tests/test_report_evidence_integrity.py \
  spreadworks/tests/test_morning_options_report.py \
  spreadworks/tests/test_market_structure.py spreadworks/tests/test_report_refresh.py spreadworks/tests/test_tradier_report_source.py spreadworks/tests/test_intraday_watch.py -q
```

The independent strict report-policy CI job must pass without `|| true`.
Tests cover every omitted field, invalid clocks and values, nested freshness,
schema/prose corruption, exact-expiry forward evidence, frozen baseline math,
wrong-setup activation, paper/flow reconciliation, optional collector isolation,
PNG embeds and delivery leases. New requirements need corresponding producer,
renderer, integrity and failure-path checks plus a deliberate version change.

## Provider policy (2026-10-05)
Morning, market-open and intraday share Tradier-only market collectors. No ThetaData fallback or cached ThetaData report observations are allowed. Surface IV and gamma use explicitly labeled Black-Scholes estimates from fresh two-sided Tradier BBO, not refreshed receipt clocks or stale vendor Greeks. Daily OI publication time is unavailable and is never described as intraminute inventory. Representative expiries and quote qualification coverage are disclosed. Tradier REST does not supply contemporaneous option trade+NBBO evidence: initiation remains unavailable until such evidence exists; chain volume is never substituted. Independent macro, news and Trading Volatility products retain their own provenance.

## Professional Tradier contract packages (2026-10-07.1)

The report, intraday watcher, and ad-hoc contract scanner share one normalized
Tradier professional-chain adapter. A contract can qualify only from a genuine
Tradier bid/ask pair and a fresh underlying quote whose original exchange clocks
are no more than 90 seconds old. Receipt time never refreshes those clocks.

IV, delta, gamma, theta and vega are modeled from the same fresh Tradier BBO
midpoint and are labeled as local Black-Scholes estimates; they are not
misrepresented as exchange-observed Greeks. Volume and open interest remain
provider fields, with OI explicitly treated as daily inventory whose publication
time is unavailable.

The latest normalized chain is persisted in `chain_cache` for diagnostics and
LAST KNOWN context. Persisted contracts never become executable merely because
they were reread: ENTRY_READY and simulated fills still require a freshly
qualified per-leg package. `/api/spreadworks/market-structure/professional-options/{symbol}`
is read-only and exposes the same bounded contract representation for QQQ, SPY,
NVDA and other valid optionable symbols; it creates, modifies and routes no order.

Tradier REST still does not provide contemporaneous option trade-plus-NBBO
evidence for initiation classification. Therefore professional chain access does
not upgrade raw chain volume into buyer/seller flow: that section remains
`FLOW DATA UNAVAILABLE (Tradier live)` unless verified trade-time quote evidence
actually exists.

## Refresh-first and last-known evidence (2026-10-05.3)

Both report kinds refresh context before the final core refresh. Each producer
gets a bounded deadline and one retry; exchange clocks never become request
receipt times. Record every attempt in the required integrity field. Retain a
verified prior observation on failure, with LAST KNOWN, its original update date,
time and age. Partial refreshes retain older per-metric clocks instead of erasing
observed RV/skew/term values. No historical quote qualifies a live entry.

Compare named morning fields separately: price location, frozen same-session
move consumption, range, stall evidence and setup state. Never reuse yesterday's
expected move as today's frozen budget. Charts carry their actual source clocks.
Profile recovery uses a current bounded tape window and discloses incomplete
session coverage; it must not sit hours behind while claiming a session profile.

Every ENTRY_READY alert must reconcile to a modeled paper fill or a persisted
blocked outcome. Old alerts without recorded outcomes stay unresolved, never
retroactively filled. No completed trades means undefined win rate/average P&L.

Holding periods count completed close-to-close trading sessions: 10 is roughly
two trading weeks, 20 roughly a month. Any performance comparison must use the
same verified cohort and fill/cost methodology; it is not forward assurance.

Stored UTC database clocks must regain their explicit UTC offset on reads; restoring timezone identity must never reset the original observation time or age. The strict CI job includes the refresh, source and scanner regression suites.
