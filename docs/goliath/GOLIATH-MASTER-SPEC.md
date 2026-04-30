# GOLIATH — Master Spec (Recovered)

**Source:** Recovered from chat session `https://claude.ai/chat/e0e6fb84-8a04-4f3f-b671-31fc7c649f88` ("Understanding the wheel of options strategy") via conversation_search on 2026-04-29.
**Author of original spec:** Leron + Claude collaborative session, pre-Phase-0 of GOLIATH.
**Status of this document:** Spec content recovered verbatim. Phase 1.5 status updated to current state. Open questions clearly marked.

---

## Label legend

- **[RECOVERED]** — Verbatim from the source chat session above.
- **[CONFIRMED-CURRENT]** — Verified against current code/repo state by Claude Code in audits during 2026-04-28/29.
- **[OPEN]** — Real ambiguity that Leron should resolve before relying on this doc.
- **[STANDARD]** — Universal trading bot best practice that applies regardless of GOLIATH-specific design.

---

## 1. Strategy

### 1.1 What GOLIATH is

**[RECOVERED]** GOLIATH sells defined-risk put credit spreads on leveraged single-name ETFs, simultaneously buys OTM calls on the same LETF funded by the spread credit, never owns the underlying shares, and uses GEX data on the *underlying* (not the LETF) to inform strike placement.

### 1.2 Why this exists

**[RECOVERED]** The standard Wheel strategy breaks on leveraged ETFs because of decay mechanics. Owning shares plus selling covered calls produces negative expected value because volatility drag destroys principal faster than premium income compensates. GOLIATH is an asymmetric alternative — bounded downside per trade (defined by the put spread width), uncapped upside (from the long call), no share ownership, no decay drag.

### 1.3 What GOLIATH does NOT do

**[RECOVERED]**

- Does not own LETF shares (no covered calls phase)
- Does not run iron condors on LETFs (slippage too high on 4-leg structures)
- Does not roll positions (closing positions when wrong is mandatory)
- Does not trade index LETFs like TQQQ/SOXL (different strategy class entirely)
- Does not connect to IronForge in any way (stays in AlphaGEX research lab)

### 1.4 Universe

**[RECOVERED]** Five LETFs, all 2×:

| LETF | Underlying | Notes |
|------|------------|-------|
| MSTU | MSTR | BTC catalyst, primary validation target |
| TSLL | TSLA | Largest single-stock LETF, deepest options chain |
| NVDL | NVDA | AI catalyst, high IV around earnings |
| CONL | COIN | Crypto exchange exposure, lower volume |
| AMDL | AMD | AI/semi diversifier |

GEX data comes from the *underlying*, not the LETF, because dealer hedging happens in the larger options chain.

### 1.5 Trade structure — three legs

**[RECOVERED]** Every GOLIATH trade is exactly this structure. No exceptions.

| Leg | Action | Instrument | Strike rule |
|-----|--------|------------|-------------|
| 1 | SELL | Short put on the LETF | ~25-30 delta, 7 DTE — collects premium |
| 2 | BUY | Long put on the LETF | 1 strike below short put, 7 DTE — caps downside |
| 3 | BUY | Long call on the LETF | 15-25% OTM, 7 DTE — funded by spread credit, uncapped upside |

**[RECOVERED]**

- Net cost: typically -$6 to +$5 (small debit or small credit)
- Capital required: ~$37-50 per contract
- Max loss: defined (put spread width minus net credit)
- Max upside: uncapped

### 1.6 Architecture

**[RECOVERED]** GOLIATH is a shared engine plus per-LETF instances. One codebase, five configured instances. Each instance has its own state, P&L tracking, and kill switch. Failures are isolated — GOLIATH-MSTU blowing up cannot affect GOLIATH-NVDL. Each instance runs under its own `bot_guard` tag (`GOLIATH-MSTU`, `GOLIATH-TSLL`, etc.).

### 1.7 Cadence

**[RECOVERED]** Weekly cadence:

- **Enter:** Monday 10:30–11:30 AM ET
- **DTE:** 7 (Friday expiry same week)
- Avoids Monday open volatility
- Captures full theta decay window
- Small weekend gap risk by design

### 1.8 Calibrated parameters from Phase 1.5

**[CONFIRMED-CURRENT]** Phase 1.5 (now in progress) calibrates four spec parameters that drive strike mapping. Default values pending Phase 1.5 Step 9 results:

| Parameter | Spec default | Used in |
|-----------|--------------|---------|
| Wall concentration threshold | `2.0× median` | Gate G03 + strike mapping |
| Tracking error fudge factor | `0.1` | Strike confidence on LETF mapping |
| Vol drag coefficient | theoretical formula | LETF return prediction |
| Realized vol window | `30 days` | Vol estimation |

---

## 2. The 10 Pre-Entry Gates

**[RECOVERED]** All 10 must pass before any trade executes. Failure logging is data — persist gate failure reasons to PostgreSQL even when no trade happens.

| Gate | Check | Notes |
|------|-------|-------|
| G01 | SPY GEX not in extreme negative regime | Global market regime check |
| G02 | Underlying GEX not in extreme negative regime | Per-LETF regime check |
| G03 | Underlying has identifiable positive gamma wall below spot | If no wall, no trade |
| G04 | Underlying earnings not within 7 days | Different volatility regime |
| G05 | LETF IV Rank ≥ 60 | Premium must be elevated to fund the call |
| G06 | All 3 LETF strikes have OI ≥ 200 | Liquidity check on each leg |
| G07 | Bid-ask spread on each leg ≤ 20% of mid | Slippage protection |
| G08 | Net cost on entry ≤ 30% of long call cost | Spread must subsidize the call |
| G09 | Underlying not in active downtrend (above 50-day MA) | Trend filter |
| G10 | Total open GOLIATH positions ≤ 3 across all instances | Platform concentration cap |

**[RECOVERED]** Gate logging requirements:

- `goliath_gate_failures` table persists every failed evaluation
- `gates_passed_before_failure` lists exactly the gates that passed before the first fail
- `attempted_structure` is populated when applicable (gates G06+ have a structure to fail against)
- `letf_ticker` and `underlying_ticker` populated correctly
- Cold-start IV-rank case logs `INSUFFICIENT_HISTORY` and skips trade
- Earnings yfinance failure → fail closed (no trade), do not assume safe

---

## 3. Strike Mapping Algorithm

**[RECOVERED]** This is the most technically tricky part. Naive linear leverage mapping is wrong because:

1. **2x leverage is daily, not terminal.** Over 7 DTE, the relationship breaks down due to volatility drag and path dependence.
2. **Volatility drag accumulates.** `drag ≈ -0.5 × L × (L-1) × σ² × t` where σ is annualized vol and t is time in years.
3. **Strike step sizes don't match.** TSLA strikes are $2.50 increments; TSLL strikes are $0.50 increments. Rounding matters.
4. **"Wall" needs a quantitative definition.** A wall is gamma concentration meaningfully larger than surrounding strikes — defined as ≥ 2× median gamma of strikes within ±5% of spot.

**[RECOVERED]** Algorithm steps:

- **Step 1: Find the wall.** From underlying gamma levels, identify largest positive gamma below spot where gamma ≥ 2× the median gamma of strikes within ±5% of spot. If no qualifying wall exists, fail Gate G03 and return None.
- **Step 2: Map underlying target to LETF target.** Translate the underlying wall price to an equivalent LETF price using vol-drag-adjusted formula (the four Phase 1.5 calibrated parameters drive this math).
- **Subsequent steps:** detailed math is in source chat; implementation belongs to Phase 2.

### 3.1 Strike mapping required tests

**[RECOVERED]** Minimum 13 tests covering:

1. Happy path with clean wall, sufficient OI, valid economics
2. No wall meeting concentration threshold → returns None
3. Wall exists but no LETF strikes in target range → returns None
4. Strikes exist but OI too low → returns None
5. Strikes exist but bid-ask too wide → returns None
6. Net cost exceeds 30% of call → returns None
7. Volatility drag computed correctly for known inputs
8. Tracking error band sensible for realistic volatilities (test multiple sigma values)
9. Short put strike selection respects "below central target" rule
10. Long call strike selection respects "above central target" rule
11. Long put is correctly 1 strike below short put
12. Edge case: short put is lowest available strike → returns None
13. Real-world data test using actual TSLA/TSLL chains pulled from your data sources

---

## 4. Position Management — 8 Exit Triggers

**[RECOVERED]** Profit targets and stops, all mechanical:

| # | Trigger | Action |
|---|---------|--------|
| 1 | Long call 3× of cost | Close call leg, hold put spread to expiry |
| 2 | Long call 5× of cost | Close entire position |
| 3 | Put spread at 50% of max profit | Close put spread, hold call |
| 4 | Total loss > 80% of defined max | Close everything |
| 5 | Short strike breached + 3 DTE | Close everything |
| 6 | Material news mid-trade | Close everything (manual flag for v0.2; not auto-detected) |
| 7 | Thursday 3:00 PM ET | Mandatory close, regardless of P&L |
| 8 | Underlying GEX flip occurred mid-trade | Re-evaluate; close if regime now adverse |

**[RECOVERED]**

- Mandatory close has hard cutoff — cannot be overridden
- **No rolling allowed in v0.2.** If a trade doesn't work, close it. Rolling is how every short-vol strategy dies.
- Position state machine: `OPEN → MANAGING → CLOSING → CLOSED`
- Each exit reason logged distinctly for post-hoc analysis

---

## 5. Position Sizing — Two-Level Caps

**[RECOVERED]** Account assumed at $5,000 starting capital.

| Cap | Value | Notes |
|-----|-------|-------|
| Per-trade risk | 1.5% = $75 | Max defined loss per single trade |
| Per-instance allocation (MSTU/TSLL/NVDL) | $200 each | Higher-IV LETFs |
| Per-instance allocation (CONL/AMDL) | $150 each | Lower-volume LETFs |
| Platform total cap | $750 (15%) | Sum across all 5 instances |
| Max concurrent positions | 3 | Across the entire platform |
| Hard cap per trade | 2 contracts | Even if math allows more |

**[RECOVERED]** Sizing algorithm: `min(by_per_trade_risk, by_instance_remaining, by_platform_remaining, 2_hard_cap)`. Returns 0 contracts if no allocation room → skip trade.

---

## 6. Kill Switches

**[RECOVERED]** Per-instance triggers (kills only that instance):

- **I-K1:** Instance drawdown > 30% of allocation
- **I-K2:** 5 consecutive losses on the instance
- **I-K3:** 20 trades without an upside hit (≥ +$50)

**[RECOVERED]** Platform-level triggers (kills everything):

- **P-K1:** Platform drawdown > 15% of GOLIATH allocation
- **P-K2:** Single-trade loss > 1.5× defined max
- **P-K3:** VIX > 35 sustained 3+ days
- **P-K4:** Trading Volatility API down > 24 hours

**[RECOVERED]** Required behaviors:

- Kill state persisted across process restarts
- Manual override requires explicit Leron action — no automatic recovery
- All kill events logged with reason and snapshot data

---

## 7. Order Execution

**[RECOVERED]** Submit as 3-leg combo order at midpoint:

1. Compute initial limit price at midpoint of all three legs
2. Submit combo order, type `NET_DEBIT`
3. If not filled in 60 seconds, walk price toward bid/ask by $0.02 increments
4. Maximum 5 walk attempts (5 minutes total)
5. If still not filled after 5 minutes, cancel and skip the trade
6. Log skipped trade with reason `poor_execution`

**[CONFIRMED-2026-04-29]** Broker: **Tradier** (Leron decision; matches AlphaGEX convention). [STANDARD] order safety requirements (idempotent, atomic across legs, fill confirmation before recording position) all apply.

---

## 8. Data Source — Trading Volatility API

**[RECOVERED]** Endpoints needed:

| Endpoint | Purpose | When |
|----------|---------|------|
| `/api/gex/latest` | Current GEX snapshot (flip_price, skew_adjusted_gex, gex_per_1pct_chg, IV) | Pre-entry |
| `/api/gex/levels` | Gamma levels by strike (finds the wall) | Pre-entry, daily refresh |
| `/api/gex/strikes` | Gamma distribution across strikes | Pre-entry |
| `/api/gex/history` | Historical GEX | Backtest module (v0.3 scope, not now) |

**[RECOVERED]**

- Cache responses for 1 hour minimum
- Handle rate limits gracefully with exponential backoff
- If API down > 24 hours, trigger platform kill switch P-K4
- Data tier assumption: daily snapshots (design so intraday becomes an upgrade, not a rewrite)

**[CONFIRMED-CURRENT]** Token env var: `TRADING_VOLATILITY_API_TOKEN` (canonical v2 Bearer token, sub_xxx format). Read at `core_classes_and_engines.py:1189`. Currently set on alphagex-backtester service per Leron's 2026-04-29 fix.

---

## 9. Phase Plan

### 9.1 Status

| Phase | Topic | Status |
|-------|-------|--------|
| 0 | Investigation | Complete (chat-only artifacts; partial recovery in this doc) |
| 1 | TV API smoke test | Complete and merged |
| 1.5 | Parameter calibration | Code complete (Steps 1-8 merged); Step 9 (real-data run) pending Render env propagation |
| 2 | Strike mapping | Specced — section 3 above |
| 3 | Entry gates (G01-G10) | Specced — section 2 above |
| 4 | Position management | Specced — section 4 above |
| 5 | Sizing + kill switches | Specced — sections 5 and 6 above |
| 6 | Per-instance runner & orchestration | Specced — Phase 6 details below |
| 7-8 | Logging, monitoring, runbook | [STANDARD] requirements; per-component build TBD |
| 9 | Paper trading | 2 weekly cycles minimum; zero successful trades is acceptable IF gate failure logs are diagnostic |

### 9.2 Phase 6 — Per-Instance Runner & Orchestration

**[RECOVERED]** Files to create:

- `bots/goliath/engine.py` — shared engine combining all components
- `bots/goliath/instance.py` — per-LETF runner
- `bots/goliath/configs/instances.yaml` — 5 LETF configs (all `paper_only: true`)
- `bots/goliath/configs/global.yaml` — platform settings
- `bots/goliath/tests/test_engine.py`
- `bots/goliath/tests/test_instance.py`

**[RECOVERED]** Required interface:

```python
class GoliathEngine:
    """Stateless service - all logic, no state."""
    def __init__(self, gex_client, structure_builder, entry_gates,
                 manager, sizer, kill_switch_monitor):
        ...

    def evaluate_entry(self, instance: GoliathInstance) -> Optional[TradeStructure]:
        """Returns structure to trade, or None if any gate fails."""

    def manage_open_positions(self, instance: GoliathInstance) -> List[ManagementAction]:
        """Returns list of actions to take on open positions."""

class GoliathInstance:
    """Stateful per-LETF wrapper. Holds config + open positions + kill state."""
```

### 9.3 Phase 9 — Paper trading

**[RECOVERED + STANDARD]**:

- Minimum duration: 2 full weekly cycles (Mon-Fri × 2)
- Bot runs uninterrupted for the full window (or all interruptions are root-caused and addressed)
- Every trade decision (enter, hold, exit) has complete audit log
- Every gate evaluation logged with TRUE/FALSE per trigger
- **Zero successful trades is acceptable IF the gate failure logs are diagnostic** (i.e., we can see which triggers prevented entries and they're all reasonable)
- All alerts during the window are reviewed and either resolved or accepted as expected
- No critical bugs surface

---

## 10. Production Readiness Components (cross-cutting)

### 10.1 Audit & logging

**[STANDARD]** Every trade event produces an immutable audit record:

- Inputs to strike mapping (spot, walls, IV rank, calibration values, configuration)
- All 10 gates evaluated (each with TRUE/FALSE + reason)
- Strike selection output verbatim
- Position size and rationale
- All broker interactions (submit, ack, fill, modification, cancel)
- Slippage per leg
- All management decisions and which one fired
- Final P&L per leg and combined

**[CONFIRMED-2026-04-29]** Storage backend: **Postgres only** (Leron decision). New table `goliath_trade_audit` with append-only constraint enforced at app layer. Phase 6 audit logging implementation; can be extended to S3 in v0.3+ if audit-grade backup becomes required.

### 10.2 Monitoring + alerting

**[STANDARD]**:

- Heartbeat every 60s
- Alerts on: heartbeat missed > 3 min, TV API failures > 3 in 10 min, yfinance failures > 5 in 10 min, token expiry < 7 days, position drift, order rejection, day's drawdown > 1.5% (warn) or > 3% (page)
- Channels: **[OPEN]** Slack `#goliath-alerts` for warnings + PagerDuty for pages? Confirm.

### 10.3 Runbook

**[STANDARD]** `docs/goliath/RUNBOOK.md` answers:

- How to start GOLIATH from cold
- How to restart after a crash
- How to view current open positions
- How to view yesterday's P&L summary
- How to trigger soft kill switch
- How to trigger hard kill switch
- How to roll the TV API token
- How to add or remove an underlying from the universe
- How to respond to each alert type
- How to rebuild from a known good state

Phase 7-8 deliverable; must exist before Phase 9.

### 10.4 Render service deployment

**[OPEN]** GOLIATH runs on its own Render worker service (e.g., `alphagex-goliath`) added to render.yaml alongside existing alphagex-* services. Currently undefined — will be specced when Phase 6 (orchestration) is built.

---

## 11. Decisions log + remaining open items

### 11.1 Resolved by Leron on 2026-04-29

| # | Question | Decision |
|---|----------|----------|
| Q1 | Broker for execution | **Tradier** |
| Q2 | Audit storage backend | **Postgres only** (extensible to S3 in v0.3+) |
| Q5 | Material news flag mechanism (Trigger 6) | **CLI command on Render shell** (no DB flag table in v0.2) |

### 11.2 Deferred — not blocking Phases 2-6

These will be answered before Phase 7-8 (monitoring) or Phase 6 (deployment) work begins, but do not block strike mapping, gates, management, sizing, kill switches, or the engine.

| # | Question | Why deferred |
|---|----------|--------------|
| Q3 | Alert channels (Slack channel + PagerDuty?) | Phase 7-8 concern; not blocking 2-6 |
| Q4 | Render service name + envVars in render.yaml | Phase 6 deployment concern; service config TBD when orchestration is built |
| Q6 | IV-rank cold-start "Option C" fallback details | For Phase 3 build, default to fail-closed on insufficient history; mark as `INSUFFICIENT_HISTORY` and skip trade. Add to v0.3 todos for proper handling. |

---

## 12. Critical path

### 12.1 Now (this week)

1. **Phase 1.5 Step 9** — Render env propagation, then run calibration on real data, commit results to main
2. **Phase 1.5 Step 10** — full test suite, phase complete report
3. **Schedule V03-DATA-1 strike snapshot collector** on Render — purely additive, accumulates data for v0.3 wall recalibration

### 12.2 Next (after Phase 1.5 closes)

1. Leron answers the 6 open questions in section 11
2. Phase 2 build — strike mapping algorithm with the 13 required tests
3. Phase 3 build — 10 entry gates with ~35 tests
4. Phase 4 build — 8 exit triggers + state machine
5. Phase 5 build — sizing + kill switches (7 triggers)
6. Phase 6 build — engine + instance + configs

### 12.3 Pre-paper

1. Audit logging infrastructure
2. Monitoring + alerting + kill switch CLI
3. Runbook
4. Pre-paper integration test suite (full lifecycle simulation)

### 12.4 Paper → live

1. Phase 9 paper trading — 2 weekly cycles minimum
2. Leron explicit go-live signoff
3. Live trading with $5,000 capital per recovered spec

---

## 13. Honest notes on this recovery

**On the recovery process:** This document is a real recovery from a real prior chat session, not invention. Earlier drafts in the current chat session were incomplete because Claude (this assistant) did not search exhaustively before writing. Specifically, the source chat at `https://claude.ai/chat/e0e6fb84-8a04-4f3f-b671-31fc7c649f88` contains the bulk of the spec content above, recovered via `conversation_search` with queries `"GOLIATH bull put credit spread OTM call earnings week strategy"` and similar.

**On what's still unrecovered:** Some details mentioned in the source chat (full strike-mapping math beyond Step 1-2 of the algorithm, "Option C" IV-rank fallback specifics, Phase 7-8 internal structure) are not in the snippets surfaced. These can be recovered via further searches if needed, or developed during the Phase 2/3/4 build sessions.

**On the difference between spec and roadmap:** This document captures the spec's content. The build order, phase decomposition, and operational concerns (Render service config, monitoring channels) need Leron's explicit decisions before this becomes a buildable plan. The 6 open questions in section 11 are the gating items.

---

*End of document. Save as `docs/goliath/GOLIATH-MASTER-SPEC.md` after Leron review of section 11 open questions.*
