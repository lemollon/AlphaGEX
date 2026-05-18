# SpreadWorks Auto-Bots — Design

**Date:** 2026-05-18
**Status:** Approved — ready for implementation plan
**Author:** Brainstorming session with user

---

## 1. Problem & Goal

SpreadWorks today is a manual spread builder + position tracker. It supports
Iron Condor, Iron Butterfly, Double Calendar, Double Diagonal, and Butterfly
in its UI, but every trade is hand-entered.

Goal: add 3 automated paper-trading bots to SpreadWorks, each owning one
non-IC strategy:

- **FROST** — Iron Butterfly, 0DTE
- **TIDE** — Double Calendar, 1DTE front / 14DTE back
- **DRIFT** — Double Diagonal, 1DTE front / 14DTE back

The bots mirror IronForge's FLAME/SPARK/INFERNO pattern (per-bot Postgres
tables, per-bot dashboard pages, 1-minute scanner running in-process,
PT/SL/EOD exits, equity snapshots) but live inside the SpreadWorks codebase
and use simulated mid-price fills (no Tradier sandbox).

## 2. Scope

**In scope**
- Backend scanner module (`spreadworks/backend/bots/`)
- Per-bot Postgres tables (5 per bot)
- API routes under `/api/spreadworks/bots/{bot}/*`
- Frontend pages: `/bots` overview + `/bots/{bot}` per-bot dashboards
- Per-strategy entry + exit logic
- Discord notifications (optional, gated by config flag)
- Event blackout integration (reuses existing `economic_events.py`)

**Out of scope**
- Real broker integration (Tradier sandbox or production fills)
- Per-bot ML models / advisory layer (PROPHET equivalent)
- Multi-account support (single `paper` account label per bot)
- Roll logic for TIDE/DRIFT — they simply close at front-leg expiry, no auto-reopen
- Backtest harness (existing AlphaGEX backtest tools can be applied later)

## 3. Architecture

### 3.1 Code layout

```
spreadworks/
  backend/
    bots/                          # NEW
      __init__.py
      scanner.py                   # APScheduler job, 1-min cadence
      executor.py                  # Open/close/MTM (mid-price, no broker)
      monitor.py                   # PT/SL/EOD logic shared across bots
      registry.py                  # BOT_REGISTRY: name -> display, strategy, config defaults
      db.py                        # Per-bot table helpers (bot_table('frost', 'positions'))
      strategies/
        __init__.py
        iron_butterfly.py          # FROST entry
        double_calendar.py         # TIDE entry
        double_diagonal.py         # DRIFT entry
    routes_bots.py                 # NEW — /api/spreadworks/bots/{bot}/* handlers
    models.py                      # EXTEND — add per-bot table classes
    __init__.py                    # EXTEND — register scan_bots APScheduler job
  frontend/
    src/
      pages/
        BotsOverview.jsx           # NEW — 3 bot cards w/ status + equity sparkline
        BotDashboard.jsx           # NEW — tabs: Equity / Performance / Positions / Trades / Logs / Config
      hooks/
        useBotStatus.js            # NEW
        useBotPositions.js         # NEW
        useBotEquity.js            # NEW
      lib/
        botRegistry.js             # NEW — mirrors backend/bots/registry.py
```

### 3.2 Scanner integration

A single new APScheduler job, `scan_bots`, fires every 60 seconds during
08:30–15:00 CT. The job iterates `BOT_REGISTRY` and, for each enabled bot:

1. Wraps the per-bot run in `asyncio.wait_for(..., timeout=15s)` to prevent
   one slow bot from starving the others. (Mirrors the 2026-05-15 IronForge
   hung-scanner fix.)
2. If a position is open: monitor MTM, check PT/SL/EOD.
3. If no position + within entry window + not blocked: try opening.
4. Log scan outcome to `{bot}_scan_activity`, write equity snapshot.

The scanner has zero dependency on the Trader being initialized — all
data endpoints query Postgres directly (memory rule #3).

### 3.3 Paper-trading model

- No broker. "Fills" use the live Tradier chain mid-price snapshot taken
  at decision time.
- Slippage assumption: 1¢ per leg on entry, 1¢ per leg on exit (configurable).
- Positions persist in `{bot}_positions`; closed trades flow to
  `{bot}_closed_trades`.
- MTM uses live chain quotes every scan cycle.
- `account_label = 'paper'` hardcoded — `executor.py` has no code path that
  calls a broker. (Paper-only lock per memory rule.)

## 4. Bot Registry

Source of truth: `spreadworks/backend/bots/registry.py`. Frontend mirror in
`spreadworks/frontend/src/lib/botRegistry.js` must stay in sync.

| Internal | Display | Strategy         | Front DTE | Back DTE | Default PT | Default SL | EOD CT |
|----------|---------|------------------|-----------|----------|-----------|------------|--------|
| frost     | FROST    | iron_butterfly   | 0         | —        | 30%       | 200% credit| 14:45  |
| tide     | TIDE    | double_calendar  | 1         | 14       | 50%       | 100% debit | 14:45* |
| drift    | DRIFT   | double_diagonal  | 1         | 14       | 50%       | 100% debit | 14:45* |

\* TIDE/DRIFT only force-close at 14:45 CT on the day the front leg expires.
On other days they hold overnight.

## 5. Database Schema

Per-bot tables (5 each). PostgreSQL via existing SQLAlchemy engine in
`backend/db.py`. Tables auto-created on startup via `Base.metadata.create_all`
(matches existing SpreadWorks pattern).

### 5.1 `{bot}_config`
```sql
CREATE TABLE {bot}_config (
  id                SERIAL PRIMARY KEY,
  starting_capital  NUMERIC(12,2) NOT NULL DEFAULT 10000,
  enabled           BOOLEAN NOT NULL DEFAULT false,
  max_contracts     INTEGER NOT NULL DEFAULT 1,
  bp_pct            NUMERIC(4,3) NOT NULL DEFAULT 0.10,  -- buying power % per trade
  sd_mult           NUMERIC(4,2) NOT NULL DEFAULT 1.0,   -- FROST: wing distance
  front_dte         INTEGER NOT NULL DEFAULT 0,
  back_dte          INTEGER,                              -- NULL for FROST
  pt_pct            NUMERIC(5,4) NOT NULL,
  sl_pct            NUMERIC(5,4) NOT NULL,
  entry_start_ct    TIME NOT NULL DEFAULT '08:35',
  entry_end_ct      TIME NOT NULL DEFAULT '10:30',
  eod_close_ct      TIME NOT NULL DEFAULT '14:45',
  discord_alerts    BOOLEAN NOT NULL DEFAULT false,
  delta_skew        INTEGER NOT NULL DEFAULT 0,           -- DRIFT only
  use_gex_walls     BOOLEAN NOT NULL DEFAULT false,       -- FROST only: clip wings to walls
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

A single row per bot, upserted via `ON CONFLICT (id) DO UPDATE SET ...`.
Seeded on first startup with defaults from `BOT_REGISTRY`.

**Important:** `_start_scheduler()` startup hook must NOT overwrite
configured values on restart (memory: SPARK config auto-reset bug in
IronForge `ensureTables()`). Seed only if row is missing.

### 5.2 `{bot}_positions`
```sql
CREATE TABLE {bot}_positions (
  position_id     TEXT PRIMARY KEY,         -- e.g. 'frost-2026-05-18-001'
  ticker          TEXT NOT NULL DEFAULT 'SPY',
  strategy        TEXT NOT NULL,            -- 'iron_butterfly' | 'double_calendar' | 'double_diagonal'
  legs            JSONB NOT NULL,           -- [{side, type, strike, expiration, contracts, entry_price}, ...]
  entry_price     NUMERIC(10,4) NOT NULL,   -- net credit (+) or debit (-)
  contracts       INTEGER NOT NULL,
  entry_time      TIMESTAMPTZ NOT NULL,
  status          TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN | CLOSED | EXPIRED
  mtm_value       NUMERIC(10,4),            -- current mid cost-to-close (per contract)
  mtm_pnl         NUMERIC(10,2),            -- signed P&L in $: positive = profit
  mtm_updated_at  TIMESTAMPTZ,
  pt_target_pnl   NUMERIC(10,2) NOT NULL,   -- close when mtm_pnl >= this ($, position total)
  sl_target_pnl   NUMERIC(10,2) NOT NULL,   -- close when mtm_pnl <= -this ($, position total, positive number)
  max_profit      NUMERIC(10,2) NOT NULL,   -- per contract
  max_loss        NUMERIC(10,2) NOT NULL,   -- per contract (wing breach for IBF; debit for DC/DD)
  account_label   TEXT NOT NULL DEFAULT 'paper',
  notes           TEXT
);
```

### 5.3 `{bot}_closed_trades`
```sql
CREATE TABLE {bot}_closed_trades (
  position_id     TEXT PRIMARY KEY,         -- FK to {bot}_positions.position_id
  close_price     NUMERIC(10,4) NOT NULL,
  close_time      TIMESTAMPTZ NOT NULL,
  close_reason    TEXT NOT NULL,            -- PT | SL | EOD | EXPIRED | FORCE | EVENT_HALT
  realized_pnl    NUMERIC(10,2) NOT NULL,
  contracts       INTEGER NOT NULL,
  legs            JSONB NOT NULL,           -- snapshot of legs at close
  entry_price     NUMERIC(10,4) NOT NULL,   -- copied for reporting
  entry_time      TIMESTAMPTZ NOT NULL,
  ticker          TEXT NOT NULL,
  strategy        TEXT NOT NULL
);
```

### 5.4 `{bot}_equity_snapshots`
```sql
CREATE TABLE {bot}_equity_snapshots (
  id                  BIGSERIAL PRIMARY KEY,
  snapshot_time       TIMESTAMPTZ NOT NULL,
  equity              NUMERIC(12,2) NOT NULL,
  unrealized_pnl      NUMERIC(10,2) NOT NULL DEFAULT 0,
  realized_pnl_today  NUMERIC(10,2) NOT NULL DEFAULT 0,
  cumulative_pnl      NUMERIC(10,2) NOT NULL DEFAULT 0,
  open_positions      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_{bot}_equity_time ON {bot}_equity_snapshots (snapshot_time);
```

One row per scan cycle. Equity = `starting_capital + cumulative_pnl + unrealized_pnl`.

### 5.5 `{bot}_scan_activity`
```sql
CREATE TABLE {bot}_scan_activity (
  id              BIGSERIAL PRIMARY KEY,
  scan_time       TIMESTAMPTZ NOT NULL,
  outcome         TEXT NOT NULL,            -- TRADE | NO_TRADE | MONITOR | BLOCKED_<reason>
  reason          TEXT,
  signal_data     JSONB,                    -- chain snapshot, GEX levels, IV, etc.
  position_id     TEXT                      -- if outcome=TRADE
);
CREATE INDEX idx_{bot}_scan_time ON {bot}_scan_activity (scan_time DESC);
```

Truncate to last 30 days nightly to bound growth.

## 6. Strategy Entry Logic

### 6.1 FROST — Iron Butterfly, 0DTE SPY

**Inputs:** today's 0DTE chain, spot, VIX, optional GEX levels (call_wall, put_wall, flip_point).

**Algorithm:**
1. **Pre-flight gates** (any FALSE → log `BLOCKED_<gate>` and exit):
   - Within entry window (`entry_start_ct ≤ now < entry_end_ct`).
   - No open position.
   - `enabled = true`.
   - Event blackout NOT active for SPY.
   - VIX < 28.
   - GEX flip-point distance from spot > $1 (skip whippy days).
2. **Strike selection:**
   - Body = round(spot) to nearest $1.
   - Wing distance = `sd_mult × today_implied_move`, where
     `today_implied_move = atm_straddle_mid × 0.85` (standard 0DTE
     approximation).
   - Wings = body ± wing_distance, rounded to nearest $1.
   - If `use_gex_walls=true`, clip wings to nearest call_wall (above) and
     put_wall (below) when they fall inside computed wings.
3. **Pricing:**
   - Credit = mid(short_call) + mid(short_put) − mid(long_call) − mid(long_put).
   - Skip if credit < $0.30 (degenerate setup).
4. **Sizing:**
   - `wing_width = body − long_put_strike` (= long_call_strike − body, symmetric).
   - `max_profit = credit × 100` per contract.
   - `max_loss = (wing_width − credit) × 100` per contract.
   - `contracts = min(max_contracts, floor((equity × bp_pct) / max_loss))`.
5. **Open:** insert into `frost_positions` with
   - `pt_target_pnl = pt_pct × max_profit × contracts`
   - `sl_target_pnl = sl_pct × max_profit × contracts` (positive number; compared against −mtm_pnl)
   - `mtm_value` initialized to `credit` (cost to close at entry = credit received).

### 6.2 TIDE — Double Calendar, 1DTE front / 14DTE back, SPY

**Inputs:** chain for front_dte and back_dte expirations, spot, IV per leg.

**Algorithm:**
1. **Pre-flight gates:**
   - Within entry window. No open position. Enabled. Not in event blackout.
   - VIX < 30 (high VIX flattens vega edge).
   - `back_iv − front_iv ≥ 1.0` vol points (otherwise no calendar edge).
2. **Strike selection:**
   - `implied_move = atm_straddle_mid_front_dte`.
   - Call strike = round(spot + implied_move) to nearest $1.
   - Put strike = round(spot − implied_move) to nearest $1.
   - Same strikes used for both front (short) and back (long) months.
3. **Pricing:**
   - Debit = mid(long_back_call) + mid(long_back_put) − mid(short_front_call) − mid(short_front_put).
   - Skip if debit ≤ $0.20 (chain malformed) or > $5 (too rich).
4. **Sizing:**
   - `max_loss = debit × 100` per contract (worst case: huge move both legs).
   - `max_profit = debit × 100` per contract (target profit reference — actual theoretical max is higher but capped by PT %).
   - `contracts = min(max_contracts, floor((equity × bp_pct) / max_loss))`.
5. **Open:** insert with
   - `pt_target_pnl = pt_pct × max_profit × contracts`
   - `sl_target_pnl = sl_pct × max_loss × contracts` (positive number)
   - `mtm_value` initialized to `debit` (current value = debit paid at entry).

### 6.3 DRIFT — Double Diagonal, 1DTE front / 14DTE back, SPY

Same as TIDE with three changes:
1. Long back-month call strike = short front-month call strike + 1 (more OTM).
2. Long back-month put strike = short front-month put strike − 1 (more OTM).
3. Optional `delta_skew` shifts both back strikes up (+) or down (−) by N strikes
   for a directional tilt. Default 0.

Sizing/pricing identical to TIDE; max profit is higher because back strikes
are farther OTM (cheaper longs), max loss is roughly the debit + 1-strike width.

## 7. Exit Logic (shared `monitor.py`)

Every scan cycle, for each open position:

1. Pull live mid prices for all legs.
2. Compute current cost-to-close: `mtm_value = signed sum of leg mids`
   (for IBF credit: `mtm_value = short_call_mid + short_put_mid − long_call_mid − long_put_mid` = cost to buy back).
   (for DC/DD debit: `mtm_value = long_back_call_mid + long_back_put_mid − short_front_call_mid − short_front_put_mid` = current credit you'd receive to unwind).
3. Compute signed P&L:
   - **Credit strats (FROST):** `mtm_pnl = (entry_price − mtm_value) × contracts × 100` (we received `entry_price` credit; profit when buy-back is cheaper).
   - **Debit strats (TIDE/DRIFT):** `mtm_pnl = (mtm_value − entry_price) × contracts × 100` (we paid `entry_price` debit; profit when current value is higher).
4. Update `{bot}_positions.mtm_value`, `mtm_pnl`, `mtm_updated_at`.
5. Decide:
   - **PT hit?** `mtm_pnl ≥ pt_target_pnl` → close with reason `PT`.
   - **SL hit?** `mtm_pnl ≤ −sl_target_pnl` → close with reason `SL`.
   - **Time-of-day PT ladder** (FROST only): override `pt_target_pnl` each scan using `pt_pct_morning=0.30`, `pt_pct_midday=0.40`, `pt_pct_afternoon=0.50` based on CT clock. (Ported from IronForge SPARK fix.) TIDE/DRIFT use static `pt_pct`.
   - **EOD trigger:**
     - FROST: if CT now ≥ `eod_close_ct` → close with reason `EOD`.
     - TIDE/DRIFT: if today is the front-leg expiration date AND CT now ≥ `eod_close_ct` → close with reason `EOD`.
   - **Event blackout** for ticker: close with reason `EVENT_HALT`.
6. On close, write to `{bot}_closed_trades`, update `{bot}_positions.status = 'CLOSED'`,
   recompute equity snapshot.

Each per-bot monitor wrapped in `asyncio.wait_for(..., timeout=15s)`.

## 8. API Routes

Under `/api/spreadworks/bots/{bot}/...`. Bot validated against `BOT_REGISTRY`
keys — anything else returns 404. All routes are read-only except where noted.

```
GET    /status                  -- enabled, last_scan_at, open_positions count, equity
GET    /positions               -- all open positions with live MTM
GET    /position-monitor        -- alias of /positions; matches IronForge naming
GET    /equity-curve            -- historical (all closed trades, cumulative)
GET    /equity-curve/intraday   -- today's snapshots, includes unrealized
GET    /trades?limit=N          -- closed trades, paginated
GET    /performance             -- win rate, avg win, avg loss, total P&L
GET    /daily-perf              -- per-day P&L summary
GET    /config                  -- read config
POST   /config                  -- upsert (write)
POST   /toggle                  -- flip enabled on/off
POST   /force-trade             -- bypass entry window, open now if signal valid
POST   /force-close?position_id=  -- close specific position
GET    /logs                    -- recent log entries (re-uses scan_activity)
GET    /scan-activity           -- last N scans with outcome+reason
```

Authorization: same as existing SpreadWorks routes (no auth; behind
existing infra). Acceptable since paper-only.

## 9. Frontend

### 9.1 `/bots` — Overview

3 bot cards in a row. Each card shows:
- Bot name + strategy badge
- Enabled toggle
- Equity sparkline (last 7 days, sourced from `{bot}_equity_snapshots`)
- Open positions count + current MTM
- Today's P&L
- Link to per-bot dashboard

### 9.2 `/bots/{bot}` — Per-bot dashboard

Tabbed layout (matches IronForge `BotDashboard.tsx`):

- **Equity** — Recharts area chart. Toggle: historical vs intraday. Uses `useBotEquity(bot)`.
- **Performance** — Win rate, avg win, avg loss, expectancy, max DD, total trades, total P&L. By close_reason breakdown.
- **Positions** — Open positions table with per-leg strikes, expirations, entry, current MTM, PT/SL targets, time-in-trade. Force-close button per row.
- **Trades** — Closed trades, sortable. Columns: entry/close time, legs, entry, close, P&L, reason.
- **Logs** — Scan activity feed. Filter by outcome.
- **Config** — Editable form: starting capital, enabled, PT/SL %, BP %, max contracts, entry window, EOD close. Save → POST `/config`. Read-only reflection of registry defaults.

Reuses existing SpreadWorks components: `PayoffDiagram` for positions tab, `format.js`, `priceScale.js`.

### 9.3 Build pipeline note

Per memory `project_spreadworks_dist_drift_2026_05_17`: SpreadWorks Render
service serves committed `spreadworks/frontend/dist/`. Implementation plan
MUST include rebuilding dist (`cd spreadworks/frontend && npm run build`)
and committing the result; src-only commits will not change the live UI.

## 10. Risk Controls

- **Paper-only lock** — `executor.py` has no broker imports. Code search must
  return zero hits for `place_order`, `submit_order`, etc.
- **Kill switch** — `{bot}_config.enabled = false` short-circuits scanner.
- **Per-bot timeout** — 15s wait_for around each bot's scan cycle.
- **Event blackout** — `economic_events.is_blackout_active('SPY', now_ct)`
  blocks both opens and forces closes.
- **Equity snapshots every scan** — never let intraday chart go blank
  (memory rule #1). Live fallback snapshot computed from open positions if
  no row exists for today yet.
- **No auto-reset** — config seeding only runs when row is missing; never
  overwrites user-edited values (memory `project_spark_config_locks`).
- **Starting capital from config** — never hardcoded in any equity endpoint.
- **NULL guards** — all P&L queries use `COALESCE(realized_pnl, 0)`.
- **Discord rate limit** — re-uses existing `_send_webhook_sync` 3-attempt
  retry + 429 backoff.

## 11. Discord Integration

Optional, per-bot config flag `discord_alerts`. When enabled:
- Open: embed with bot name, strategy, legs, entry price, max profit/loss.
- Close: embed with close reason, realized P&L, time in trade.

Reuses existing `_send_webhook_sync(embed)` from `backend/__init__.py`. Same
dedup guard via `_dedup_ok(key, cooldown=300)` — key format
`bot:{bot}:position:{position_id}:{open|close}`.

## 12. Testing

- **Unit:** Per-strategy strike selection given a fixed chain fixture. Per-strategy
  sizing given a fixed equity + bp_pct. PT/SL trigger logic.
- **Integration:** End-to-end scan cycle hitting a test Postgres DB and a
  recorded Tradier chain fixture (no live API calls in CI).
- **Manual:** After deploy, force-trade each bot once via the API, watch
  the position appear on the dashboard, then force-close.

## 13. Open questions / future work

- Multi-account support (currently `account_label='paper'` only).
- Backtest harness — could plug into existing AlphaGEX backtest infra later.
- Roll logic for TIDE/DRIFT — current design simply closes at front expiry.
  A real roll (open new front at same back) is future work.
- ML advisory layer (PROPHET equivalent) — out of scope.

## 14. Acceptance Criteria

The work is complete when:

1. All 3 bots can be enabled via `POST /api/spreadworks/bots/{bot}/toggle`.
2. With market open + no event blackout, each bot opens at least one
   simulated position within its entry window.
3. Each per-bot dashboard renders Equity / Performance / Positions / Trades /
   Logs / Config tabs without errors.
4. PT, SL, and EOD exit conditions each fire correctly in a test fixture.
5. `/api/spreadworks/bots/frost/equity-curve/intraday` returns at least 2
   data points within 2 minutes of bot enable.
6. Force-close API closes an open position and updates `{bot}_closed_trades`.
7. Disabling a bot stops its scanner from opening new positions but does
   NOT auto-close existing ones (manual force-close required).
8. Discord alerts post (when enabled) on open and close with correct
   dedup behavior.
9. SpreadWorks frontend `dist/` is rebuilt + committed so live UI shows
   the new pages.
