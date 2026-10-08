# Permanent options report requirements

The executable contract is `backend/report_contract.py`; inference and display
rules are `backend/report_policy.py`. Version `2026-10-08.3` retains the
day/near-forward/forward plans, horizon comparisons, adaptation rules, data
integrity, persisted visual delivery and market control, drops `risk`/
`session`/`hunt` from engine consensus (redundant with `risk_on_defensive`
and `candidate_analysis`, and never actually used), adds flow's
`price_vix_confirmation`, and adds the decision-first narrative layer (opening
pieces + per-section "what it means for the day"): **33 sections and 242
required fields**, unchanged by the narrative layer since it renders from
existing field values, not new requirements.
Every delivered report carries its policy version and SHA-256 schema/rule hash.

## Reader experience

Morning, opening and intraday reports use the same dark layout: Today's mission,
a 30-second scoreboard, a Today vs forward table, four decision-first opening
panels (Market story, Edge board, Biggest traps, If/then day plan), the entire
required contract, and eleven PNG panels. HTML shows the charts beside their
corresponding topics. The original panels and data points remain present.
Within the 19 sections most relevant to a same-day/forward trading decision
(§§ risk_on_defensive, market_control, gamma, flow, premium_selling,
day/near-forward/forward strategy, expected_move, smile, surface,
forward_strikes, range_stall, breadth, profile, sector_credit, macro,
futures_context, event_calendar — `SECTION_SUMMARY_SECTIONS` in
`report_policy.py`), each section's required fields are followed by a
"Section summary" line (a mechanical recap of up to three of that section's
own populated field:value pairs) and a "What it means for the day" line (a
deterministic lookup against that section's own field values — never a new
number, never a specific structure/strategy recommendation, since the trader
this serves runs every options strategy, not credit spreads alone). Bookkeeping
sections (contract_packages, entry_watches, candidate_analysis,
position_management, trigger_accountability, paper_scorecard, scanner,
event_study, engine_consensus, morning_comparison, horizon_comparison,
adaptation_rules, visuals, data_integrity) are deliberately excluded from this
layer; they remain raw evidence only. Missing observations have source-specific
reasons; dated last-known observations retain their clocks. Arbitrary model
narrative is stored only for diagnosis and cannot introduce facts into the
canonical rendered report — the decision-first lines above are templated code,
not model output, and are covered by the same no-model-prose rule.

## Website and historical archive

The private Report Desk reads the same persistent `sw_full_reports` snapshots
and stored chart bytes as scheduled delivery. `/reports/history` provides bounded
date/type pagination in America/Chicago and excludes diagnostic verification
runs; `/reports/{id}/data` exposes the immutable full contract to the reader.
Reading either route never collects market data, changes a report, sends a
notification or executes a trade. All newly persisted morning, opening and
intraday reports appear automatically without a second report schedule.
The website retains all 33 sections/242 fields and reconciles all eleven chart
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

## Market control (2026-10-08.1)

`control_side`, `control_evidence`, `control_confidence` and
`forward_control_outlook` answer who is in control today — call sellers, put
sellers, or neither — and whether that reading should hold into the forward
window. `control_side` is a deterministic read of §7 classified call-sell vs
put-sell premium by expiry bucket: one side must exceed the other by 1.5x to
be called, otherwise the bucket is `mixed`. The read is gated on §7's own
`classified_contract_fraction`; below 0.5 classified coverage the bucket is
always `inconclusive`, never a guess. `control_confidence` carries that same
fraction with a HIGH/MEDIUM/LOW_FORCES_INCONCLUSIVE label.

`forward_control_outlook` never extrapolates today's control_side on its own.
It compares the 0DTE control_side against the forward_strategy (1–4 week)
thesis's directional-pressure read: the same-direction case is `persists`,
the opposite-direction case is `flips`, and a missing or balanced/unclassified
forward read is `fades`. No control_side, or no qualifying forward pressure,
leaves the field unavailable.

## Flow price/VIX confirmation and engine consensus (2026-10-08.2)

`flow.price_vix_confirmation` is now populated (it previously stayed
unavailable — the producer never wrote it). Per symbol, it compares the
flow-implied lean (`calls_bought`+`puts_sold` premium vs `calls_sold`+
`puts_bought` premium, classified §7 flow only) against the observed
price direction since prior close: `confirms` when they agree, `conflicts`
when they disagree, `inconclusive` when either side is too thin/flat to
call. VIX has no persisted prior-close baseline, so its level rides along
as context only — the verdict itself never depends on an unmeasured VIX
direction.

`engine_consensus` no longer carries `risk`/`session`/`hunt`: `risk` only
ever duplicated `risk_on_defensive.verdict`, `session` was just a
timestamp, and `hunt` duplicated `candidate_analysis`. Only `squeeze`,
`trading_volatility_status` and `contradictions` remain.

## Decision-first narrative (2026-10-08.3)

Reports stayed accurate but required the reader to manually synthesize "what
does this mean" from 33 sections of raw evidence. Four new opening panels and
one per-section recap close that gap, both rendered by `report_policy.py`
(`market_story`, `edge_board`, `biggest_traps`, `if_then_day_plan`,
`section_summary`, `section_meaning`) with zero new producer fields:

- **Market story** — one line combining `risk_on_defensive.verdict`,
  `premium_selling.suitability` and the gamma meaning below.
- **Edge board** — a trigger/invalidation/status table for all three
  horizons, reusing `day_strategy`/`near_forward_strategy`/`forward_strategy`.
- **Biggest traps** — HIGH-impact `event_calendar.catalysts` entries plus the
  live `data_integrity.unavailable_fields` count, so blind spots are named,
  never silently absent.
- **If/then day plan** — a direct reprint of `adaptation_rules`
  (`activate`/`cancel`/`switch`/`stand_aside`/`existing_positions`/
  `reassessment`), which already held this content but only appeared at the
  bottom of the report.

Within `SECTION_SUMMARY_SECTIONS` (19 of the 33 sections — see above),
`section_summary` recaps up to three of that section's own populated fields
verbatim, and `section_meaning` is a closed lookup against that section's own
values: verdict text for `risk_on_defensive`, dominant classified side for
`market_control`, net-GEX sign for `gamma`, classified-coverage magnitude for
`flow`, rich/cheap for `premium_selling`, and the registered `status` string
for the three strategy horizons. The remaining 11 sections (expected_move,
smile, surface, forward_strikes, range_stall, breadth, profile, sector_credit,
macro, futures_context, event_calendar) get a fixed, non-numeric sentence
describing that section's role — never a reading of today's specific values —
since they are supporting evidence, not an independent call. None of this
recommends a specific strategy/structure: the reader trades every options
strategy, so the lookup states only which side the evidence favors (sellers
vs buyers, which direction), consistent with `structure`'s own existing text
("no structure invented from directional pressure").

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

## Email delivery (2026-10-08.1)

`backend/report_email.py` adds Resend email as a second, independent
destination for morning and intraday/market-open reports, alongside the
existing Discord webhooks — additive only; it never blocks or replaces
Discord delivery, and a failed/disabled send is swallowed, never raised, so
it cannot cost a Discord delivery lease. Reuses the same `RESEND_API_KEY`
Resend account already live for IronForge's email-verification funnel
(separate sender identity). Gated on three environment variables all being
set: `REPORT_EMAIL_ENABLED=true`, `RESEND_API_KEY`, and `REPORT_EMAIL_TO`
(comma-separated recipients); `REPORT_EMAIL_FROM` must be set to a verified
sender/domain in that Resend account or sends are rejected. The email body
reuses `render_opening_html` (the same mission/scoreboard/today-vs-forward
summary the web view renders) and attaches the same verified chart PDF
`/charts.pdf` serves, built from the already-persisted, already-checked
image evidence — never a re-render.

## Regression gate

From the repository root:

```sh
python -m pytest spreadworks/tests/test_report_policy.py \
  spreadworks/tests/test_full_options_report.py \
  spreadworks/tests/test_report_evidence_integrity.py \
  spreadworks/tests/test_morning_options_report.py \
  spreadworks/tests/test_market_structure.py spreadworks/tests/test_report_refresh.py spreadworks/tests/test_tradier_report_source.py spreadworks/tests/test_intraday_watch.py spreadworks/tests/test_theta_flow.py spreadworks/tests/test_thetadata_proxy.py spreadworks/tests/test_report_email.py -q
```

The independent strict report-policy CI job must pass without `|| true`.
Tests cover every omitted field, invalid clocks and values, nested freshness,
schema/prose corruption, exact-expiry forward evidence, frozen baseline math,
wrong-setup activation, paper/flow reconciliation, optional collector isolation,
PNG embeds and delivery leases. New requirements need corresponding producer,
renderer, integrity and failure-path checks plus a deliberate version change.

## Provider policy (2026-10-07.1)
ThetaData Pro is the primary options-flow source for morning, market-open and
intraday reports. The private proxy supplies actual trades paired with preceding
NBBO quotes. The bounded collector requests SPY/QQQ, up to four listed expirations <=60DTE selected near 0/3/14/45 days,
the six listed strikes nearest fresh spot per expiration (calls and puts), and
the trailing 120 seconds (widened from 3 strikes 2026-10-08, after production logs
showed zero budget-exhaustion and zero proxy-lock contention events at the old
scope). Requests specify individual strikes to bound current-day
history costs. This is not all-strike, all-expiration, full-market or full-session
flow, and retained top-40 concentrations are not aggregate totals. Requested and
completed contracts and expiration failures are retained in the source evidence.
Only regular/auto-executed prints at a preceding NBBO <=1 second old support a
likely initiation estimate; midpoint, missing-clock, complex/auction and unknown
conditions remain unclassified. Cancellation messages are excluded. No opening/
closing inventory, institutional identity or multi-leg intent is inferred.

The isolated minute flow job and refresh-before-publication path persist source
clocks, coverage, categories and exact print evidence. Aggregates must reconcile.
The report policy accepts only the versioned ThetaData trade-time NBBO producer;
legacy ThetaData snapshots remain rejected. Read endpoints return stored evidence
without collecting, sending or trading; the explicit POST flow refresh probe
collects and persists only. A stale tape is never reported live on re-read.

Tradier remains the primary source for underlying/BBO/surface/gamma/index data
and the automatic fallback when Theta flow fails. Tradier REST lacks paired
option trade-time NBBO, so its fallback explicitly marks initiation unavailable;
chain volume and later quotes are never substituted. A last verified flow capture
keeps its original clock, and failure reasons remain disclosed. Daily OI is not
intraminute inventory. Independent macro, news and Trading Volatility retain
provenance. Existing report fields, visuals, schedules and destinations remain.

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
