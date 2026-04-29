# GOLIATH v0.3 TODOs

Tracked items deferred from earlier phases. None of these block v0.2
paper-trading research.

Each item has an ID (`V03-XXX`) for cross-reference from code comments and
commit messages. Sorted by phase of origin, then by dependency order
within phase.

---

## Origin: Phase 1.5 (calibration)

### V03-DATA-1: Strike-level GEX snapshot collector

**What:** Daily collector script that pulls `/curves/gex_by_strike` for each
universe underlying and writes a row per `(ticker, snapshot_date, strike,
call_gamma, put_gamma, total_gamma)` into a `goliath_strike_snapshots`
table.

**Why:** Phase 1.5 wall concentration calibration was downgraded to a
cross-sectional sanity check (5 single-day observations across the universe)
because TV's v2 API does not expose historical strike-level snapshots. All
TV endpoints checked — see [GOLIATH-BLOCKED] resolution in this branch's
commit history. Once we accumulate 30+ days of our own snapshots we can
re-run wall calibration with real per-underlying time-series.

**File:** `scripts/goliath_strike_snapshot_collector.py` (~80 lines)

**Storage:** New table `goliath_strike_snapshots` with at minimum:
- `ticker VARCHAR(10) NOT NULL`
- `snapshot_date DATE NOT NULL`
- `strike DECIMAL(10, 2) NOT NULL`
- `call_gamma DECIMAL(20, 6)`
- `put_gamma DECIMAL(20, 6)`
- `total_gamma DECIMAL(20, 6)`
- `spot_at_snapshot DECIMAL(10, 2)`
- `created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()`
- `UNIQUE (ticker, snapshot_date, strike)` — idempotent rerun safe

**Schedule:** Daily at market close (3 PM CT) via existing scheduler
infrastructure (see `scheduler/trader_scheduler.py` for cron patterns
used by other bots).

**Trigger to build:** Now (parallel to Phase 1.5; not blocking). Earlier
start = sooner usable data when V03-WALL-RECAL becomes actionable.

**Estimated effort:** ~80 lines for the script + scheduler entry +
table creation.

**Dependencies:** Phase 1 v2 client (already in production main).

---

### V03-WALL-RECAL: Re-run wall concentration calibration with real time-series

**What:** Once V03-DATA-1 has accumulated 30+ days of snapshots, re-run
`wall_concentration.calibrate()` against the historical
`goliath_strike_snapshots` table to produce real P25/P50/P75/P90
distributions per underlying — the validation the spec originally
called for.

**Why:** Validates the spec default 2.0× threshold against actual
historical wall concentration distribution rather than 5
cross-sectional sanity points.

**Concrete change required:**
1. Update `trading/goliath/calibration/wall_concentration.py` to read
   from `goliath_strike_snapshots` when available; keep current-snapshot
   fallback for fresh installs / new tickers.
2. Restore P25/P75/P90 fields to `WallConcentrationResult` (deferred
   in v0.2; deletion was the right call for the cross-sectional regime).
3. Restore the `CALIB-OK` / `CALIB-ADJUST` tagging logic alongside the
   `CALIB-SANITY-OK` / `CALIB-FINDING` tags. Pick whichever applies
   based on data depth.
4. Update v0.3 recovery doc Module Contracts to reflect restored fields.

**Depends on:** V03-DATA-1 having accumulated ≥ 30 days of data.

**Trigger to run:** After 30+ days of V03-DATA-1 collection.

---

## Origin: Phase 0 (spec deltas, deferred deliverables)

### V3-1: True ATM-IV-from-Tradier IV-rank module

**What:** Pull real ATM IV from Tradier option chains daily and maintain a
252-day rolling percentile to compute true `iv_rank`. Replaces the current
TV `iv_rank` (which works) and the Tradier ATM-IV Tier-2 fallback already
implemented in Phase 1.

**Why:** TV's pre-computed `iv_rank` is the authoritative source today;
this is a backup if TV ever degrades. Keep deferred.

**Trigger to build:** Pre-live-trading or if TV `iv_rank` proves
unreliable.

---

### V3-2: NASDAQ public earnings calendar fallback

**What:** Use NASDAQ's public earnings calendar at
`api.nasdaq.com/api/calendar/earnings` as a fallback to yfinance for
Gate G04 (earnings-blackout window).

**Trigger to build:** If yfinance failure rate > 5% over 30 days.

---

### V3-3: Cross-bot exposure aggregator

**What:** Monitoring module that aggregates total MSTU notional across
GOLIATH-MSTU + AGAPE-SPOT-MSTU and enforces a platform-level
concentration cap.

**Why:** v0.2 paper trading is acceptable per [GOLIATH-DELTA] (Leron
accepted). Live trading authorization should not happen without this
guard.

**Trigger to build:** Pre-live-trading.

---

### V3-4: Backtest engine

**What:** GOLIATH backtest engine using TV `/series` historical data.

**Trigger to build:** After 4+ weeks of paper-trade results.

---

### V3-5: Live-trading mode unlock

**What:** Remove the two-key safety lock (`paper_only` flag + `mode=PAPER`
check) in `trading/goliath/executor.py` once backtest validation +
concentration check + Leron's explicit go-ahead are in place.

**Trigger:** After V3-3, V3-4, and Leron approval.

---

### V3-6: Frontend dashboard

**What:** Next.js dashboard for GOLIATH state (positions, P&L, calibration
metrics).

**Trigger to build:** After v0.2 stable.

---

### V3-7: Alerting / notifications

**What:** Push notifications for trade events, kill switches, calibration
drift.

**Trigger to build:** After v0.2 stable.

---

### V3-8: Convert sizing caps from absolute dollars to percentage of allocated capital

**What:** Replace per-instance dollar caps in `GoliathConfig` with
percentage-of-capital caps so the bot scales gracefully when capital
allocation increases beyond the $5K research-scale starting point.

**Trigger to build:** When GOLIATH validates and capital base exceeds
$5K.
