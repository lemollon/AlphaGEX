# Permanent options report requirements

The executable contract is `backend/report_contract.py`; inference and display
rules are `backend/report_policy.py`.

Version `2026-10-14.1` adds `day_strategy.tv_structure_check` (+1 field, day_strategy
only — not near_forward_strategy/forward_strategy, since TradingVolatility's structure
pick reflects today's regime, not a 2-5 session or 1-4 week horizon). SPY/QQQ's own
day plan previously carried only the fixed, textbook `structure` field (the registered
package disclaimer plus `_structure_family_hint`'s rich/cheap premium reading) regardless
of today's condition. This reuses — never duplicates — the same TradingVolatility
structure-selection path `trade_volatility_scan`/`engine_consensus` already surface: the
`structures` field on whichever of `top_long_setups`/`top_short_setups` rows matches
ticker SPY or QQQ this checkpoint (`/market-structure`, also called by the collector,
does not return a structure field, so it is not used here). `build_strategy_blocks`'s
`_tv_structure_check` compares that vendor pick against the registered Edge Board setup's
own `strategy` (`report_contract.py`'s `STRATEGY_FIELDS` registration, unchanged) by
coarse structure family (`_structure_family`, so "credit_spread" vendor naming and our
"put_credit_spread" registration are not read as a disagreement) and records
agree/disagree/no-data per symbol — it never overwrites the registered setup's own
`structure` field or `strategy` value. `_narrative_strategy` (shared by day_strategy's
HTML and markdown rendering) appends a sentence only on disagreement: "TradingVolatility's
engine suggests X while the registered setup is Y." Agreement and no-data cases stay in
the raw `/data` JSON only, since they don't change what the reader does next.

Version `2026-10-13.1` adds `trade_volatility_scan` (34th section, +5 fields:
`top_long_setups`, `top_short_setups`, `income_setups`, `put_call_ratio`,
`expected_move_trend`): Leron, 2026-10-13 — "which stock show the best
opprotunity to go long in the short term bullish or bearish... what are the
strikes and expirations", "put call ratio does is support the read", "is it
widenening or collapsing". TradingVolatility's v2 API (already integrated for
`engine_consensus.trading_volatility_status`) already computes all of this,
cross-ticker, versioned and deterministic; `backend/report_trading_volatility_scan.py`
is a new, independent collector (separate from `trading_volatility_context.py`'s
module-level cache/rate-limit state, which belongs to the live `qqq_retest_watch`
alert loop) that calls `/top-setups` (long and short), `/income-setups`, and
`/tickers/{SPY,QQQ,IWM,VIX}/market-structure` + `/series` for put/call ratio and
an IV-rank-trend-based expected-move-widening/collapsing read. Every value is
TradingVolatility's own output, clearly sourced — the report never fabricates
a strike, score, or direction here; `section_meaning` explicitly labels it
"their engine's read, not this report's own signal."

Version `2026-10-08.3` retains the
day/near-forward/forward plans, horizon comparisons, adaptation rules, data
integrity, persisted visual delivery and market control, drops `risk`/
`session`/`hunt` from engine consensus (redundant with `risk_on_defensive`
and `candidate_analysis`, and never actually used), adds flow's
`price_vix_confirmation`, and adds the decision-first narrative layer (opening
pieces + per-section "what it means for the day"), unchanged by the narrative
layer since it renders from existing field values, not new requirements.

Version `2026-10-10.1` adds `morning_comparison.regime_shift`: the morning
report's gamma/control/premium-suitability snapshot per symbol, diffed against
the current read every time the report renders. The Positioning & Levels panel
surfaces the result as a Plan status line (HOLDING / CHANGED since this
morning / first read of the day), so an intraday reversal of the morning call
is stated explicitly instead of requiring the reader to notice it by comparing
two separate reports: **33 sections and 243 required fields**.

Version `2026-10-10.2`: Leron — "make the read detailed and fun to read... each
section should flow into each [other]." Every section now carries the "Section
summary" / "What it means for the day" pair, not just the 19 originally judged
decision-relevant; the 14 bookkeeping sections get an honest line describing
their real role (several explicitly say "not a market read" rather than
inventing one). `market_control`'s line additionally calls back to Today's
Mission's verdict — agreeing or in tension with it — the one section with its
own genuine bull/bear-leaning read; no other section's line claims a direction
it doesn't actually carry. No new REQUIREMENTS fields.

Every delivered report carries its policy version and SHA-256 schema/rule hash.

## Reader experience

Morning, opening and intraday reports use the same dark layout: Today's mission,
a 30-second scoreboard, a Today vs forward table, four decision-first opening
panels (Market story, Edge board, Biggest traps, If/then day plan), the entire
required contract, and eleven PNG panels. HTML shows the charts beside their
corresponding topics. The original panels and data points remain present.
Every one of the 33 sections (`SECTION_SUMMARY_SECTIONS` in `report_policy.py`)
has its required fields followed by a "Section summary" line (a mechanical
recap of up to three of that section's own populated field:value pairs) and a
"What it means for the day" line (a deterministic lookup against that
section's own field values — never a new number, never a specific
structure/strategy recommendation, since the trader this serves runs every
options strategy, not credit spreads alone). For the 14 sections that are
honestly bookkeeping or audit trail (contract_packages, entry_watches,
candidate_analysis, position_management, trigger_accountability,
paper_scorecard, scanner, event_study, engine_consensus, morning_comparison,
horizon_comparison, adaptation_rules, visuals, data_integrity), that line says
so plainly rather than forcing a trading signal onto evidence that doesn't
carry one. Missing observations have source-specific reasons; dated
last-known observations retain their clocks. Arbitrary model narrative is
stored only for diagnosis and cannot introduce facts into the canonical
rendered report — the decision-first lines above are templated code, not
model output, and are covered by the same no-model-prose rule.

## Website and historical archive

The private Report Desk reads the same persistent `sw_full_reports` snapshots
and stored chart bytes as scheduled delivery. `/reports/history` provides bounded
date/type pagination in America/Chicago and excludes diagnostic verification
runs; `/reports/{id}/data` exposes the immutable full contract to the reader.
Reading either route never collects market data, changes a report, sends a
notification or executes a trade. All newly persisted morning, opening and
intraday reports appear automatically without a second report schedule.
The website retains all 34 sections/250 fields and reconciles all eleven chart
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

## VIX contradiction-calling (2026-10-12)

`risk_on_defensive.change_vs_baselines` already carried `market_comparison`'s
free-form per-symbol dict (SPY/QQQ price vs morning/prior baseline) with zero
fixed schema, so this adds a `'VIX'` entry to that same dict via a new
`vix_comparison` producer (`full_options_report.py`) rather than a new field
name — no contract version bump. It reads the VIX level already persisted
under each stored report's `evidence.volatility.indices.VIX` (every report
snapshot already carries the full `core` dict; VIX's own level was simply
never read back out before now) and compares it to the current level, same
shape as the SPY/QQQ rows (`price_change_pct`, `baseline_session_matches`,
etc).

`decision_brief_lines` (`report_policy.py`) uses it to flag the one
contradiction VIX can carry: VIX normally moves opposite price, so VIX up
while SPY/QQQ both rally, or VIX down while both sell off, is flagged as a
real contradiction (gated on `regime_side != neutral`, a same-session
baseline, and a >3% VIX move to filter noise) — never fabricated from a
missing or stale VIX reading.

## Flat regime label (2026-10-12.2)

Leron, repeatedly: "come out and say if its risk on day, choppy day, defensive
day" and "if thing changed from choppy to risk on say it" -- the existing
`risk_on_defensive.verdict` text ("Risk-on price confirmation" / "Defensive
price confirmation" / "Mixed price confirmation") required inference. Two new
fields fix this with zero new evidence, just a relabel of the same
risk/defensive/mixed computation plus a stored-baseline comparison, same
pattern as every other morning/prior-hour field here:

- `risk_on_defensive.regime_label` -- `"RISK-ON"`, `"DEFENSIVE"`, or
  `"CHOPPY"` (CHOPPY is the existing "mixed" state: SPY and QQQ returns
  disagree in sign). Same gate as `verdict` -- both SPY and QQQ must have a
  valid return, or the field is unavailable, never guessed.
- `morning_comparison.regime_label_shift` -- `{morning_label,
  prior_hour_label, current_label, changed_since_morning,
  changed_since_prior_hour}`. Reads the label out of the stored
  morning/prior-hour report the same way `regime_shift` already reads
  net-GEX/control-side/suitability off the baseline's `report_blocks`.

`decision_brief_lines` (`report_policy.py`) opens every report with this
label as line one -- `"CHOPPY."` or, when it flipped,
`"CHOPPY -- changed from RISK-ON since this morning."` -- instead of the
former hedge ("price is leaning defensive"). Falls back to the old hedged
phrasing only if `regime_label` itself is unavailable (degraded evidence),
never fabricating a label SPY/QQQ returns don't support.

## Macro yield delta and put/call ratio naming the flat regime label (2026-10-14)

Two small narrative fixes, zero new producer fields, same pattern as "VIX
contradiction-calling" above (no contract version bump).

`macro.rates`'s 10-year yield was a snapshot only -- today's level, no sense of
"how has it changed." `collect_macro` (`report_producers.py`) already fetches a
14-day FRED window to find the latest valid `DGS10` row; the prior valid row in
that same window just sat unused. Each FRED-sourced rate (`rates_2y/5y/10y/
30y`) now also carries `change_1day_bp` and `prior_observation_date` when a
second valid row exists, no new API call. `_narrative_macro`
(`report_policy.py`) folds the 10-year's delta into its existing sentence --
`"the 10-year yield is 4.12% (up 6bp day-over-day)"` -- same real-sentence
style as every other section_summary builder.

`trade_volatility_scan.put_call_ratio`'s "what it means for the day" line
already tied SPY's put/call-ratio read back to the mission call (agree/
conflict), same cross-section pattern `market_control` uses against
`mission_side` -- but it named both possible sides verbatim in every sentence
("the defensive/risk-on mission call above") regardless of which one was
actually in play, and it never referenced the flat `regime_label` the Decision
Brief actually opens with. `section_meaning` (`report_policy.py`) now takes an
optional `regime_label` argument (same shape as `mission_side`, both call
sites in `report_policy.py`/`full_options_report.py` compute it from
`risk_on_defensive.regime_label` the same way `decision_brief_lines` already
does); when present, the tie-in sentence names it directly --
`"...in tension with today's flat DEFENSIVE regime call."` Falls back to the
prior hedged `mission_side` wording, naming only the side that actually
applies, when `regime_label` itself is unavailable -- never fabricating
a label the underlying returns don't support.

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
  spreadworks/tests/test_market_structure.py spreadworks/tests/test_report_refresh.py spreadworks/tests/test_tradier_report_source.py spreadworks/tests/test_intraday_watch.py spreadworks/tests/test_theta_flow.py spreadworks/tests/test_thetadata_proxy.py spreadworks/tests/test_report_email.py \
  spreadworks/tests/test_report_trading_volatility_scan.py spreadworks/tests/test_trading_volatility_context.py -q
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

2026-10-14: contract_packages and day_strategy.contracts were permanently unavailable on every report because the stored option_strike_selection is stamped at the setup's last ENTRY_READY transition, not at report-build time, so qualify_package()'s <=90s freshness check always rejected it. Report generation now re-fetches a live option selection for each currently ENTRY_READY setup at build time (same fetch_option_selection() the watcher itself calls) and only fills these fields when they are still unavailable — never overrides a package the normal path already qualified. No new producer fields, no contract version change.

2026-10-14: the Edge Board (markdown and HTML) is now a ranked list of competing trade ideas instead of one fixed row per horizon. Candidates: the three registered horizons (day/near/forward, skipping PENDING EVIDENCE), a contained-range idea per symbol with real profile+gamma coverage (SPY/QQQ today), and an explicit "No trade" option that always ranks last except when nothing else qualifies. IWM is tracked by the watcher for price/triggers but has no gamma/profile/control_side producer yet, so it cannot appear as a range candidate. Every candidate is built from fields already required and rendered elsewhere; no new producer fields, no contract version change.

2026-10-14: the 30-second scoreboard adds live SPY/QQQ/VIX price rows ("778.37, +0.09% from baseline; fresh at ...") sourced entirely from risk_on_defensive.change_vs_baselines, and a "No-trade condition" row that always mirrors the ranked Edge Board's own top candidate rather than computing a second, possibly-conflicting read. IWM has no price row for the same reason it has no Edge Board range candidate -- market_comparison() only iterates core['surface'], which is SPY/QQQ-only. No new producer fields, no contract version change.

2026-10-14: Market story's opening fragment is now _narrative_risk_on_defensive's price-leader/breadth read (falls back to the flat verdict label when evidence is unavailable) instead of the flat verdict label alone, and a new second fragment carries market_control's dealer-positioning read with its existing agree/conflict callback to the mission verdict above -- both reads already existed for exactly this cross-referencing purpose but only ever surfaced in the per-field appendix. No new producer fields, no contract version change.

2026-10-14: a new top-level "Options flow" section (markdown and HTML) promotes _narrative_flow's existing per-symbol dominant-flow-type + $ premium + price-confirms/conflicts read out of the per-field appendix, mirroring how Market story promotes risk_on_defensive/market_control. Falls back to a plain "coverage too thin" sentence when classified flow can't support a direction. No new producer fields, no contract version change.

2026-10-14: a new top-level "Dealer positioning" section (markdown and HTML) promotes _narrative_market_control's existing per-symbol "who's running this today, how confident, does forward flow agree" read out of the per-field appendix, same pattern as Options flow. Distinct from Market story's market_control fragment, which stays as section_meaning's single aggregate agree/conflict sentence against the mission verdict -- this is the richer per-symbol breakdown. Falls back to the same "coverage too thin" disclosure section_meaning already uses for this block. No new producer fields, no contract version change.

2026-10-14: a new top-level "Surface, smile & term structure" section (markdown and HTML) combines _narrative_surface's existing per-symbol ATM IV + term-structure-shape + IV-vs-realized-gap read and _narrative_smile's existing per-symbol skew-lean read, out of the per-field appendix where they previously surfaced separately under "### Surface" and "### Smile". Same promotion pattern as Options flow and Dealer positioning. No new producer fields, no contract version change.
