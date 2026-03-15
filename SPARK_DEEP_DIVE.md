# SPARK Bot Deep Dive — Complete Architecture & Behavior Analysis

> **Date:** 2026-03-15
> **System:** IronForge (standalone SPY Iron Condor paper trading platform)
> **Bot:** SPARK — 1DTE SPY Iron Condor Paper Trader
> **Codebase Root:** `/home/user/AlphaGEX/ironforge/`

---

## Table of Contents

1. [Entry Logic](#1-entry-logic)
2. [Exit Logic](#2-exit-logic)
3. [Position Structure](#3-position-structure)
4. [Scheduling & Execution Flow](#4-scheduling--execution-flow)
5. [Data Layer](#5-data-layer)
6. [Risk Management](#6-risk-management)
7. [API & External Dependencies](#7-api--external-dependencies)
8. [Configuration & Parameters](#8-configuration--parameters)
9. [Logging & Monitoring](#9-logging--monitoring)
10. [Known Issues & Tech Debt](#10-known-issues--tech-debt)
11. [Differences from FLAME & INFERNO](#11-differences-from-flame--inferno)

---

## 1. ENTRY LOGIC

### 1.1 Exact Entry Conditions

For SPARK to open a position, ALL of the following must be true (checked in order):

| # | Gate | Condition | Code Location |
|---|------|-----------|---------------|
| 1 | Bot active | `is_active = TRUE` in `spark_paper_account` table | `trader.py:163` / `ironforge_scanner.py:~3570` |
| 2 | Market open | Weekday, 8:30 AM – 3:00 PM CT | `trader.py:175-181` / `ironforge_scanner.py:1106` |
| 3 | Entry window | Time < 2:00 PM CT (`entry_end=1400`) | `trader.py:190-202` / `ironforge_scanner.py:1125-1131` |
| 4 | No open position | 0 positions with `status='open' AND dte_mode='1DTE'` | `trader.py:204-225` / `ironforge_scanner.py:2428-2432` |
| 5 | Not already traded today | 0 trades opened today (max_trades_per_day=1) | `trader.py:204-225` / `ironforge_scanner.py:1838-1845` |
| 6 | PDT check | Day trade count < `max_day_trades` (4) in rolling 5-business-day window | `trader.py:239-249` / `ironforge_scanner.py:1847-1850` |
| 7 | Buying power | Available BP >= $200 | `trader.py:251-261` / `ironforge_scanner.py:1876` |
| 8 | VIX filter | VIX <= 32.0 | `signals.py:384-392` / `ironforge_scanner.py:1819` |
| 9 | Signal valid | Credit >= $0.05 (min_credit) | `signals.py:261-319` / `ironforge_scanner.py:1906` |
| 10 | Advisor gate | Oracle win_probability >= 0.42 (if advisor returns SKIP and WP < 0.42, skip) | `signals.py:470-511` / `ironforge_scanner.py:1878-1883` |
| 11 | Race guard | Re-check no position opened since gate #4 | `trader.py:325-339` / `ironforge_scanner.py:~2800` |

**Critical gate for SPARK:** Gate #5 — after the first trade of the day, ALL subsequent scans return `skip:already_traded_today`. No more trades possible until the next calendar day.

### 1.2 Entry Time Window

- **Start:** 8:30 AM CT (market open)
- **End:** 2:00 PM CT (`entry_end="14:00"`)
- **Source:** `models.py:63` / `ironforge_scanner.py:92` (`entry_end: 1400`)
- After 2:00 PM CT, no new positions are opened. Existing positions continue to be monitored.

### 1.3 Strike Selection

**Algorithm** (`signals.py:166-194` / `ironforge_scanner.py:1290-1314`):

```
SD multiplier = 1.2 (configurable)
Spread width = $5 (configurable)

expected_move = VIX / 100 / sqrt(252) * spot_price
effective_em = max(expected_move, spot_price * 0.005)  # 0.5% floor

put_short  = floor(spot - SD * effective_em)
call_short = ceil(spot + SD * effective_em)
put_long   = put_short - width    # $5 below
call_long  = call_short + width   # $5 above
```

**Expiration targeting** (`signals.py:97-119` / `ironforge_scanner.py:1885-1886`):
- Target: 1 trading day out (skips weekends/holidays)
- Validated against Tradier's available expirations list
- Falls back to nearest valid expiration if exact target unavailable

**Symmetric wings enforcement** (`signals.py:196-259`):
- After initial strike calculation, verifies `put_spread_width == call_spread_width`
- If asymmetric, adjusts the wider wing inward to match the narrower
- Validates proposed strikes against available strikes from option chain (if provided)

### 1.4 Position Sizing

**Algorithm** (`executor.py:217-241` / `ironforge_scanner.py:1910-1923`):

```
spread_width = put_short - put_long  # = $5
collateral_per_contract = (spread_width - credit) * 100
                        # e.g., ($5 - $0.40) * 100 = $460

usable_bp = buying_power * 0.85  # Use 85% of available BP
bp_contracts = floor(usable_bp / collateral_per_contract)
contracts = min(10, bp_contracts)  # Cap at max_contracts=10
```

**Example:** SPY $600, credit $0.40 → collateral $460/contract → BP $10,000 × 85% = $8,500 → 18 contracts → capped at 10.

### 1.5 Entry Filters & Guards

| Filter | Threshold | Effect |
|--------|-----------|--------|
| VIX too high | > 32.0 | Skip trade entirely |
| Credit too low | < $0.05 | Skip — spread not worth trading |
| Insufficient BP | < $200 | Skip — can't size a position |
| Oracle SKIP | win_prob < 0.42 | Skip — advisor rejects trade |
| Collateral calc fails | spread_width <= 0 or collateral <= 0 | Skip — math error |

### 1.6 GEX/Volatility-Based Entry Conditions

**Status: NOT IMPLEMENTED**

GEX fields are **hardcoded placeholders** (`signals.py:87-91` / `ironforge_scanner.py:3520-3523`):
- `call_wall = 0`, `put_wall = 0`, `gex_regime = "UNKNOWN"`, `flip_point = 0`, `net_gex = 0`
- These fields are stored in the position/signal tables but not used for strike selection
- Strike selection relies solely on SD-based calculation using VIX

---

## 2. EXIT LOGIC

### 2.1 All Exit Conditions

| # | Trigger | Condition | Priority | Code Location |
|---|---------|-----------|----------|---------------|
| 1 | **Profit Target** | `cost_to_close <= entry_credit * (1 - pt_pct)` | Normal | `trader.py:539-556` / `ironforge_scanner.py:1735-1749` |
| 2 | **Stop Loss** | `cost_to_close >= entry_credit * sl_mult` (2.0x) | Normal | `trader.py:559` / `ironforge_scanner.py:1751-1768` |
| 3 | **EOD Cutoff** | Time >= 2:45 PM CT (3:45 PM ET) | High | `trader.py:570-577` / `ironforge_scanner.py:1657-1676` |
| 4 | **Stale Holdover** | Position from a prior trading day | High | `trader.py:446-495` / `ironforge_scanner.py:1657-1676` |
| 5 | **Expired** | Position past expiration date | High | `trader.py:446-495` |
| 6 | **MTM Data Failure** | 10 consecutive Tradier quote failures | Emergency | `trader.py:507-534` / `ironforge_scanner.py:1691` |

### 2.2 Sliding Profit Target

The profit target percentage **decreases throughout the day** (`trader.py:658-693` / `ironforge_scanner.py:1140-1172`):

| Time Window (CT) | PT % | PT Price (if credit = $1.00) | Tier |
|-------------------|------|------------------------------|------|
| 8:30 AM – 10:29 AM | 30% | Close at $0.70 | MORNING |
| 10:30 AM – 12:59 PM | 20% | Close at $0.80 | MIDDAY |
| 1:00 PM – 2:44 PM | 15% | Close at $0.85 | AFTERNOON |
| 2:45 PM+ | Any | Force close (EOD) | EOD |

Formula: `profit_target_price = entry_credit * (1 - current_pt_pct)`

The base PT (30%) is configurable. Midday = `max(10%, base - 10%)`, afternoon = `max(10%, base - 15%)`.

### 2.3 Stop Loss

- **Multiplier:** 2.0x entry credit (configurable as `stop_loss_pct=200`)
- **Formula:** `stop_loss_price = entry_credit * 2.0`
- **Example:** Entry credit $0.50 → stop at cost_to_close >= $1.00
- **Max loss:** `collateral_per_contract = (spread_width - credit) * 100`

### 2.4 Exit Order Type

All exits are **paper** — no actual orders placed. Close price is determined by:
- **For SPARK:** Calculated MTM (mark-to-market) from live Tradier quotes
- **Conservative fill assumption:** Buy at ask, sell at bid
- **Fallback:** If MTM unavailable, force-close at entry credit ($0 P&L)

### 2.5 Multiple Exit Conditions

Position management checks triggers in this order every cycle (`trader.py:435-579`):
1. Stale/expired positions (force close immediately)
2. EOD cutoff (force close if past 2:45 PM CT)
3. MTM data failure counter (force close at 10 consecutive failures)
4. Profit target (sliding by time-of-day)
5. Stop loss (2.0x entry credit)

First trigger that fires wins. No trailing stop or dynamic adjustment logic exists.

### 2.6 End of Day / Near Expiration

- **EOD cutoff:** 2:45 PM CT (configurable as `eod_cutoff_et="15:45"` = 3:45 PM ET)
- **Behavior:** All open positions force-closed regardless of P&L
- **Frontend auto-close:** `BotDashboard.tsx:171-199` — after 2:45 PM CT, frontend triggers `POST /api/{bot}/eod-close` if positions still open
- **1DTE expiration:** Since SPARK targets 1DTE, positions expire next trading day. If a position is still open at next-day market open, it's detected as a "stale holdover" and force-closed at entry credit.

---

## 3. POSITION STRUCTURE

### 3.1 Iron Condor Leg Structure

```
CALL SIDE:                         PUT SIDE:
  Long Call  (buy) ── call_long      Long Put  (buy) ── put_long
       ↑ $5 width                         ↑ $5 width
  Short Call (sell) ── call_short    Short Put (sell) ── put_short
                                        ↑ spot price ↑
```

**Example** (SPY at $595, VIX at 18):
```
Expected move = 18/100/√252 × $595 = $6.75
Effective EM = max($6.75, $595 × 0.005) = $6.75

Put short  = floor(595 - 1.2 × 6.75) = floor(586.9) = $586
Put long   = $586 - $5 = $581
Call short  = ceil(595 + 1.2 × 6.75) = ceil(603.1) = $604
Call long   = $604 + $5 = $609

IC structure: 581/586 Put Spread — 604/609 Call Spread
```

### 3.2 Spread Definition

- **Width:** Always $5 (configurable via `spread_width`)
- **Distance from ATM:** 1.2σ (SD multiplier) — approximately 1.2× the daily expected move
- **Symmetric wings enforced:** If initial calculation produces asymmetric wings, the wider side is adjusted inward

### 3.3 Max Risk Per Trade

```
collateral_per_contract = (spread_width - credit) × 100
max_loss = collateral_per_contract × contracts

Example: $5 width, $0.40 credit, 10 contracts
  collateral = ($5 - $0.40) × 100 = $460/contract
  max_loss = $460 × 10 = $4,600
```

### 3.4 Partial Fills / Leg-by-Leg Execution

**Not applicable for SPARK.** SPARK is paper-only — no actual orders are placed. The entire 4-leg IC is opened as a single atomic paper trade.

FLAME (which mirrors to Tradier sandbox) handles partial fills with cascade logic: 4-leg → 2×2-leg → 4 individual legs. SPARK skips this entirely (`executor.py:345-348`: "SPARK/INFERNO: no sandbox mirroring").

---

## 4. SCHEDULING & EXECUTION FLOW

### 4.1 How SPARK Is Triggered

SPARK has **two execution paths** (both active):

#### Path A: Databricks Scheduled Job (Primary — Production)

- **Job Name:** `IronForge Scanner`
- **Cron:** `0 0/5 8-15 ? * MON-FRI` (every 5 min, Mon-Fri, 8:00 AM - 3:00 PM CT)
- **Timezone:** America/Chicago
- **Task Type:** Notebook (CRITICAL — must be "Notebook", not "Python script", so Databricks injects the `spark` session)
- **Source:** `ironforge/databricks/ironforge_scanner.py`
- **Cluster:** Single-node, Jobs Compute, Databricks Runtime 14.3 LTS
- **Retries:** 1 retry on failure, 60-second delay
- **Max concurrent runs:** 1
- **Mode:** `SCANNER_MODE=single` — runs one scan cycle per invocation, then exits

#### Path B: Render Worker (Legacy — Also Available)

- **Entry point:** `ironforge/jobs/run_spark.py`
- **Execution:** Infinite loop calling `trader.run_cycle()` with adaptive sleep (60s default)
- **Setup:** Validates config, creates tables, initializes `create_spark_trader()`
- **Status:** The `ironforge/render.yaml` defines workers, but per CLAUDE.md Render is listed as "DEAD — never used for IronForge"

#### Path C: Combined Runner (All bots in one process)

- **Entry point:** `ironforge/jobs/run_all.py`
- **Execution:** Spawns FLAME, SPARK, INFERNO as daemon threads, each in infinite loop
- **Graceful shutdown:** Handles SIGTERM for clean exit

### 4.2 Full Execution Flow (Databricks Path)

```
1. Databricks scheduler fires at cron interval
2. Cluster starts (or reuses warm node)
3. spark session injected by runtime
4. Timezone set: spark.sql("SET TIME ZONE 'America/Chicago'")

5. INITIALIZATION
   ├── Ensure PDT tables exist (_ensure_pdt_tables)
   ├── Ensure pending_orders table exists
   ├── Get current Central Time
   ├── Verify Tradier API key configured
   └── Load sandbox accounts (env vars + hardcoded fallbacks)

6. MARKET HOURS CHECK
   ├── If 8:20-8:29 AM CT → WARM-UP: sleep until 8:30 AM (keeps cluster alive)
   ├── If before 8:20 AM or after 3:00 PM CT → EXIT immediately
   └── If 8:30 AM - 3:00 PM CT → PROCEED

7. LOAD CONFIG OVERRIDES
   └── Query spark_config table, merge with BOT_CONFIG defaults

8. FOR EACH BOT (flame, spark, inferno):
   ├── 8a. Check bot active (paper_account.is_active)
   ├── 8b. COLLATERAL RECONCILIATION (every cycle)
   │   ├── Sum actual collateral from open positions
   │   ├── Compare to stored paper_account.collateral_in_use
   │   └── If drift > $0.01 → auto-reconcile
   ├── 8c. PDT counter auto-decrement (trades falling off rolling window)
   ├── 8d. Check pending order fills (FLAME only, SPARK skips)
   ├── 8e. MANAGE EXISTING POSITIONS
   │   ├── For each open position:
   │   │   ├── Check EOD cutoff (2:45 PM CT)
   │   │   ├── Check stale holdover (from prior day)
   │   │   ├── Get MTM from Tradier (4-leg batch quote)
   │   │   ├── Validate MTM (no zero bids, no inversions, no wide spreads)
   │   │   ├── Check profit target (sliding: 30% → 20% → 15%)
   │   │   └── Check stop loss (2.0x entry credit)
   │   └── Return: closed_count, unrealized_pnl
   ├── 8f. CAN-OPEN-MORE CHECK
   │   └── SPARK: can_open = (max_trades==1 AND no_open_position)
   ├── 8g. ENTRY WINDOW CHECK (8:30 AM - 2:00 PM CT)
   ├── 8h. TRY_OPEN_TRADE (if all gates pass)
   │   ├── VIX gate (skip if > 32)
   │   ├── PDT check (rolling 5 biz day window)
   │   ├── Already-traded-today check
   │   ├── Account check (BP >= $200)
   │   ├── Advisor evaluation
   │   ├── Get target expiration (1 DTE)
   │   ├── Calculate strikes (SD-based, symmetric wings)
   │   ├── Get IC entry credit from Tradier (sell at bid, buy at ask)
   │   ├── Size position (collateral math, 85% BP, cap at 10 contracts)
   │   ├── Race guard (re-check no open position)
   │   ├── INSERT into spark_positions
   │   ├── UPDATE spark_paper_account (deduct collateral)
   │   ├── INSERT spark_signals, spark_pdt_log
   │   └── LOG TRADE_OPEN to spark_logs
   ├── 8i. SAVE EQUITY SNAPSHOT (every cycle)
   ├── 8j. UPDATE bot_heartbeats (MERGE)
   └── 8k. LOG scan activity to spark_logs

9. EXIT — Databricks job completes
10. NEXT TRIGGER — 5 minutes later
```

### 4.3 Warm-Up Mechanism

(`ironforge_scanner.py:3527-3542`)

The Databricks cluster has cold-start latency (5-10 minutes). To ensure the scanner is ready at 8:30 AM market open:
- Cron fires at 8:00 AM, 8:05 AM, etc.
- At 8:20-8:29 AM CT, scanner **sleeps until 8:30** instead of exiting
- This keeps the cluster warm and eliminates cold-start delay at market open

### 4.4 Notebooks

**Primary:** `ironforge/databricks/ironforge_scanner.py` — the monolithic scanner that handles all three bots in a single run

**Supporting notebooks:**
- `ironforge/databricks/ironforge_api.py` — FastAPI endpoints on Databricks
- `ironforge/databricks/diagnose_schema.ipynb` — Schema diagnostics
- `ironforge/databricks/fix_stuck_collateral.ipynb` — Collateral repair
- `ironforge/databricks/01_setup_tables.sql` — Table creation DDL
- `ironforge/databricks/02_pdt_tables.sql` — PDT-specific table DDL

### 4.5 Environment Variables

| Variable | Required | Used By | Purpose |
|----------|----------|---------|---------|
| `TRADIER_API_KEY` | Yes | Scanner + Webapp | Live SPY/VIX quotes, option chains |
| `TRADIER_SANDBOX_KEY_USER` | No (FLAME only) | Scanner | Sandbox mirror — User account |
| `TRADIER_SANDBOX_KEY_MATT` | No (FLAME only) | Scanner | Sandbox mirror — Matt account |
| `TRADIER_SANDBOX_KEY_LOGAN` | No (FLAME only) | Scanner | Sandbox mirror — Logan account |
| `DATABRICKS_SERVER_HOSTNAME` | Yes (webapp) | Webapp | Databricks SQL warehouse hostname |
| `DATABRICKS_WAREHOUSE_ID` | Yes (webapp) | Webapp | Databricks SQL warehouse ID |
| `DATABRICKS_TOKEN` | Yes (webapp) | Webapp | Databricks auth token |
| `DATABRICKS_CATALOG` | No (default: `alpha_prime`) | Both | Databricks catalog |
| `DATABRICKS_SCHEMA` | No (default: `ironforge`) | Both | **MUST be `ironforge`, NEVER `default`** |
| `SCANNER_MODE` | No (default: `single`) | Scanner | `single` = run once + exit; `loop` = infinite |

**CONCERN:** Hardcoded API keys exist as fallbacks in `ironforge_scanner.py:24-41`. These are production Tradier keys visible in source code.

---

## 5. DATA LAYER

### 5.1 Database Technology

**Databricks Delta Lake** — schema: `alpha_prime.ironforge`

All database operations:
- **Scanner:** Uses `spark.sql()` directly (Databricks runtime)
- **Webapp:** Uses `@/lib/databricks-sql.ts` (REST API to Databricks SQL warehouse)
- **PostgreSQL:** DEAD — never used for IronForge production

### 5.2 Tables Read and Written

#### Per-Bot Tables (prefix: `spark_`)

**`spark_positions`** — All positions (open, closed, expired)

| Column | Type | Purpose |
|--------|------|---------|
| `id` | BIGINT IDENTITY | Auto-increment PK |
| `position_id` | STRING | Unique ID: `SPARK-YYYYMMDD-HEXHEX` |
| `ticker` | STRING | Always "SPY" |
| `expiration` | DATE | Option expiration date |
| `put_short_strike` | DECIMAL(10,2) | Short put strike |
| `put_long_strike` | DECIMAL(10,2) | Long put strike |
| `put_credit` | DECIMAL(10,4) | Put spread entry credit |
| `call_short_strike` | DECIMAL(10,2) | Short call strike |
| `call_long_strike` | DECIMAL(10,2) | Long call strike |
| `call_credit` | DECIMAL(10,4) | Call spread entry credit |
| `contracts` | INT | Number of contracts |
| `spread_width` | DECIMAL(10,2) | $5 |
| `total_credit` | DECIMAL(10,4) | Total entry credit per contract |
| `max_loss` | DECIMAL(10,2) | Max loss per contract |
| `max_profit` | DECIMAL(10,2) | Max profit per contract |
| `collateral_required` | DECIMAL(10,2) | Total margin hold |
| `underlying_at_entry` | DECIMAL(10,2) | SPY price at entry |
| `vix_at_entry` | DECIMAL(6,2) | VIX at entry |
| `expected_move` | DECIMAL(10,2) | Calculated expected move |
| `call_wall` | DECIMAL(10,2) | GEX call wall (**always 0 — not wired**) |
| `put_wall` | DECIMAL(10,2) | GEX put wall (**always 0 — not wired**) |
| `gex_regime` | STRING | **Always "UNKNOWN" — not wired** |
| `flip_point` | DECIMAL(10,2) | **Always 0 — not wired** |
| `net_gex` | DECIMAL(15,2) | **Always 0 — not wired** |
| `oracle_confidence` | DECIMAL(5,4) | ML confidence (**not yet wired, defaults to 0.5**) |
| `oracle_win_probability` | DECIMAL(8,4) | ML win probability (**not yet wired, defaults to 0.5**) |
| `oracle_advice` | STRING | Oracle recommendation (**not yet wired**) |
| `oracle_reasoning` | STRING | Reasoning text |
| `oracle_top_factors` | STRING | JSON — top factors |
| `oracle_use_gex_walls` | BOOLEAN | Always FALSE |
| `wings_adjusted` | BOOLEAN | Always FALSE (no dynamic adjustment) |
| `original_put_width` | DECIMAL(10,2) | Original width before adjustment |
| `original_call_width` | DECIMAL(10,2) | Original width before adjustment |
| `put_order_id` | STRING | Always "PAPER" |
| `call_order_id` | STRING | Always "PAPER" |
| `sandbox_order_id` | STRING | Always NULL for SPARK (FLAME uses this) |
| `status` | STRING | 'open', 'closed', 'expired' |
| `open_time` | TIMESTAMP | When position opened (CT) |
| `open_date` | DATE | Date opened |
| `close_time` | TIMESTAMP | When closed (or NULL) |
| `close_price` | DECIMAL(10,4) | Cost to close (or NULL) |
| `close_reason` | STRING | 'profit_target_MORNING', 'stop_loss', 'eod_cutoff', 'stale_holdover', etc. |
| `realized_pnl` | DECIMAL(10,2) | Realized P&L (or NULL if open) |
| `dte_mode` | STRING | "1DTE" |
| `created_at` | TIMESTAMP | Row created |
| `updated_at` | TIMESTAMP | Last update |

**`spark_paper_account`** — Paper account state (single active row)

| Column | Type | Purpose |
|--------|------|---------|
| `id` | BIGINT IDENTITY | PK |
| `starting_capital` | DECIMAL(12,2) | $10,000 |
| `current_balance` | DECIMAL(12,2) | starting + cumulative_pnl |
| `cumulative_pnl` | DECIMAL(12,2) | Sum of all realized P&Ls |
| `total_trades` | INT | Count of opened trades |
| `collateral_in_use` | DECIMAL(12,2) | Margin held by open positions |
| `buying_power` | DECIMAL(12,2) | balance - collateral |
| `high_water_mark` | DECIMAL(12,2) | Peak balance |
| `max_drawdown` | DECIMAL(12,2) | Largest drawdown from HWM |
| `is_active` | BOOLEAN | Bot enabled/disabled toggle |
| `dte_mode` | STRING | "1DTE" |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**`spark_equity_snapshots`** — Periodic snapshots (every scan cycle)

| Column | Type | Purpose |
|--------|------|---------|
| `id` | BIGINT IDENTITY | PK |
| `snapshot_time` | TIMESTAMP | When taken (CT) |
| `balance` | DECIMAL(12,2) | current_balance at snapshot |
| `unrealized_pnl` | DECIMAL(12,2) | Unrealized P&L from open positions |
| `realized_pnl` | DECIMAL(12,2) | cumulative_pnl at snapshot |
| `open_positions` | INT | Count of open positions |
| `note` | STRING | Optional context |
| `dte_mode` | STRING | "1DTE" |

**`spark_signals`** — Every signal generated (executed + skipped)

| Column | Type | Purpose |
|--------|------|---------|
| `id` | BIGINT IDENTITY | PK |
| `signal_time` | TIMESTAMP | When generated |
| `spot_price` | DECIMAL(10,2) | SPY price |
| `vix` | DECIMAL(6,2) | VIX |
| `expected_move` | DECIMAL(10,2) | Calculated EM |
| `put_short` / `put_long` / `call_short` / `call_long` | DECIMAL(10,2) | Proposed strikes |
| `total_credit` | DECIMAL(10,4) | Proposed credit |
| `confidence` | DECIMAL(5,4) | Signal confidence |
| `was_executed` | BOOLEAN | TRUE if trade opened |
| `skip_reason` | STRING | Why skipped (if not executed) |
| `reasoning` | STRING | Full explanation |
| `wings_adjusted` | BOOLEAN | Whether wings were adjusted |
| `dte_mode` | STRING | "1DTE" |

**`spark_logs`** — Activity audit trail

| Column | Type | Purpose |
|--------|------|---------|
| `id` | BIGINT IDENTITY | PK |
| `log_time` | TIMESTAMP | When event occurred |
| `level` | STRING | 'TRADE_OPEN', 'TRADE_CLOSE', 'SKIP', 'ERROR', 'RECOVERY', 'CONFIG', 'INFO' |
| `message` | STRING | Human-readable |
| `details` | STRING | JSON with full context |
| `dte_mode` | STRING | "1DTE" |

**`spark_daily_perf`** — One row per trading day

| Column | Type | Purpose |
|--------|------|---------|
| `trade_date` | DATE | Calendar date (unique) |
| `trades_executed` | INT | Trades opened |
| `positions_closed` | INT | Trades closed |
| `realized_pnl` | DECIMAL(10,2) | Net P&L for day |
| `updated_at` | TIMESTAMP | |

**`spark_pdt_log`** — PDT day trade records

| Column | Type | Purpose |
|--------|------|---------|
| `trade_date` | DATE | When opened |
| `symbol` | STRING | "SPY" |
| `position_id` | STRING | FK to positions |
| `opened_at` | TIMESTAMP | Open time |
| `closed_at` | TIMESTAMP | Close time (or NULL) |
| `is_day_trade` | BOOLEAN | TRUE if same-day open+close |
| `contracts` | INT | |
| `entry_credit` | DECIMAL(10,4) | |
| `exit_cost` | DECIMAL(10,4) | |
| `pnl` | DECIMAL(10,2) | |
| `close_reason` | STRING | |
| `dte_mode` | STRING | "1DTE" |

**`spark_config`** — Bot configuration overrides

| Column | Type | Default |
|--------|------|---------|
| `dte_mode` | STRING | "1DTE" (unique key) |
| `sd_multiplier` | DECIMAL | 1.2 |
| `spread_width` | DECIMAL | 5.0 |
| `min_credit` | DECIMAL | 0.05 |
| `profit_target_pct` | DECIMAL | 30.0 |
| `stop_loss_pct` | DECIMAL | 200.0 |
| `vix_skip` | DECIMAL | 32.0 |
| `max_contracts` | INT | 10 |
| `max_trades_per_day` | INT | 1 |
| `buying_power_usage_pct` | DECIMAL | 0.85 |
| `starting_capital` | DECIMAL | 10000.0 |
| `entry_start` | STRING | "08:30" |
| `entry_end` | STRING | "14:00" |
| `eod_cutoff_et` | STRING | "15:45" |

**`spark_pdt_config`** / **`spark_pdt_audit_log`** — PDT enforcement config and audit trail

#### Shared Tables

| Table | Purpose |
|-------|---------|
| `bot_heartbeats` | Scanner health (bot_name, last_heartbeat, status, scan_count) |
| `ironforge_pdt_config` | Shared PDT config (read by scanner + webapp) |
| `ironforge_pdt_log` | Shared PDT audit log |
| `ironforge_accounts` | Tradier sandbox account credentials |

### 5.3 Position State Tracking

```
Position Lifecycle:
  OPEN → CLOSED (profit target, stop loss, EOD cutoff, force-close)
  OPEN → EXPIRED (stale holdover, past expiration)
```

### 5.4 P&L Calculation

**Realized P&L** (`executor.py:492-493` / `ironforge_scanner.py:1479-1480`):
```
pnl_per_contract = (entry_credit - close_price) * 100
realized_pnl = round(pnl_per_contract * contracts, 2)
```

**Unrealized P&L** (live, from MTM):
```
unrealized_pnl = (entry_credit - cost_to_close) * 100 * contracts
```

**Cost to close** = buy back short legs at ask + sell long legs at bid (conservative)

**Account balance:**
```
current_balance = starting_capital + cumulative_pnl
buying_power = current_balance - collateral_in_use
```

### 5.5 Data Flow

```
Market Data (Tradier API)
  → SPY quote, VIX quote, option chain, option quotes
  → Signal Generator (SD-based strikes, symmetric wings, credit calculation)
  → Entry Gates (VIX, BP, PDT, max trades, advisor)
  → Paper Executor (position_id generation, collateral math)
  → Database (spark_positions INSERT, paper_account UPDATE)
  → Equity Snapshot (spark_equity_snapshots INSERT)
  → Heartbeat (bot_heartbeats MERGE)
  → Activity Log (spark_logs INSERT)
```

---

## 6. RISK MANAGEMENT

### 6.1 PDT Compliance

**Implementation:** `db.py:332-625` / `ironforge_scanner.py:1822-1850`

- **Rule:** FINRA Rule 4210 — max 4 day trades per rolling 5 business days
- **Day trade definition:** Position opened and closed on the same calendar day
- **Rolling window:** 5 business days (skips weekends)
- **Enforcement:** Configurable via `ironforge_pdt_config.pdt_enabled` (currently TRUE for SPARK per `ironforge_pdt_config` table)
- **Counter:** Automatically incremented on same-day close, auto-decremented when trades fall off the rolling window
- **Manual reset:** Available via `POST /api/spark/pdt` with action=reset

**CONCERN:** The CONFIDENCE_REPORT_2026_03_15.md says `pdt_enabled=false` for SPARK, but the CLAUDE.md says PDT is enforced. There may be a discrepancy between documentation and actual DB state.

### 6.2 Max Concurrent Positions

- **SPARK:** 1 position at a time (`max_trades_per_day=1` + check for open positions)
- Once a position is open, no new trades until it closes
- Once a trade has been made today (even if already closed), no more trades

### 6.3 Daily Loss Limits

**No explicit daily loss limit exists.** The stop loss at 2.0x entry credit per position is the only loss control. With max 1 trade/day and max 10 contracts at $460 collateral each, the theoretical max daily loss is $4,600 (46% of $10,000 capital).

**CONCERN:** No daily loss limit or drawdown circuit breaker. A streak of max-loss trades could rapidly deplete the paper account.

### 6.4 Circuit Breakers / Kill Switches

| Mechanism | Location | Behavior |
|-----------|----------|----------|
| Bot toggle | `POST /api/spark/toggle` | Sets `is_active=FALSE`, scanner skips all operations |
| Emergency kill switch | `POST /api/sandbox/emergency-close` | Force-closes ALL paper positions across ALL bots at entry credit ($0 P&L) |
| VIX gate | VIX > 32 | Blocks all new entries |
| EOD cutoff | 2:45 PM CT | Force-closes all positions |

### 6.5 Shared Limits with FLAME/INFERNO

- **PDT is per-bot** — each bot has its own PDT counter and rolling window
- **No shared position limits** — SPARK's max 1 trade doesn't affect FLAME/INFERNO
- **Emergency kill switch** affects ALL bots simultaneously
- **Paper accounts are separate** — each bot has its own $10,000 starting capital

---

## 7. API & EXTERNAL DEPENDENCIES

### 7.1 Market Data API: Tradier

**Client:** `ironforge/trading/tradier_client.py` (standalone, no AlphaGEX imports)

**Base URL:** `https://api.tradier.com/v1` (production — real market data)

| Endpoint | Purpose | Used By |
|----------|---------|---------|
| `GET /markets/quotes?symbols=SPY` | SPY spot price (bid, ask, last) | Signal generation |
| `GET /markets/quotes?symbols=VIX` | VIX value | VIX gate |
| `GET /markets/options/expirations?symbol=SPY` | Available expiration dates | 1DTE target validation |
| `GET /markets/options/chains?symbol=SPY&expiration=YYYY-MM-DD` | Full option chain | Strike validation |
| `GET /markets/options/quotes?symbols=OCC1,OCC2,OCC3,OCC4` | Batch option quotes (4 legs) | Entry credit + MTM |

**OCC symbol format** (`tradier_client.py:21-36`):
```
SPY260227P00585000 = SPY, 2026-02-27, Put, $585.00
```

### 7.2 Order Execution

**SPARK: Paper-only.** No actual orders placed. No Tradier sandbox interaction.

FLAME mirrors to 3 Tradier sandbox accounts; SPARK does not.

### 7.3 Error Handling for API Failures

| Scenario | Handling | Code |
|----------|----------|------|
| SPY/VIX quote fails | Skip trade cycle, log reason | `signals.py:61-95` |
| Option chain unavailable | Skip strike validation, use calculated strikes | `signals.py:97-119` |
| MTM quote fails | Increment failure counter; at 10 consecutive → force-close at entry credit | `trader.py:507-534` |
| All legs zero bid/ask | MTM validation fails, skip exit check | `signals.py:556-599` |
| Inverted market (ask < bid) | MTM validation fails | `signals.py:556-599` |
| Wide spread (> 50% of mid) | MTM flagged as unreliable | `signals.py:556-599` |

**No retry logic on Tradier failures.** Each scan cycle is independent — if a call fails, it simply tries again next cycle (5 min later).

---

## 8. CONFIGURATION & PARAMETERS

### 8.1 Complete Parameter List

| Parameter | SPARK Value | Source | Configurable Via |
|-----------|-------------|--------|------------------|
| `bot_name` | "SPARK" | `models.py:101` | Hardcoded |
| `dte_mode` | "1DTE" | `models.py:102` | Hardcoded |
| `min_dte` | 1 | `models.py:102` | Hardcoded |
| `ticker` | "SPY" | `models.py:38` | Hardcoded |
| `mode` | PAPER | `models.py:37` | Hardcoded |
| `starting_capital` | $10,000 | `models.py:45` | DB config + UI |
| `sd_multiplier` | 1.2 | `models.py:49` | DB config + UI |
| `spread_width` | $5 | `models.py:50` | DB config + UI |
| `min_credit` | $0.05 | `models.py:51` | DB config + UI |
| `max_trades_per_day` | 1 | `models.py:54` | DB config + UI |
| `max_contracts` | 10 | `models.py:73` | DB config + UI |
| `profit_target_pct` | 30.0% | `models.py:57` | DB config + UI |
| `stop_loss_pct` | 200.0 (= 2.0x) | `models.py:58` | DB config + UI |
| `eod_cutoff_et` | "15:45" (3:45 PM ET) | `models.py:59` | DB config |
| `entry_start` | "08:30" (CT) | `models.py:62` | DB config |
| `entry_end` | "14:00" (2:00 PM CT) | `models.py:63` | DB config |
| `vix_skip` | 32.0 | `models.py:66` | DB config + UI |
| `pdt_max_day_trades` | 4 | `models.py:69` | DB config |
| `pdt_rolling_window_days` | 5 | `models.py:70` | Hardcoded |
| `buying_power_usage_pct` | 0.85 (85%) | `models.py:74` | DB config + UI |
| `risk_per_trade_pct` | 0.15 (15%) | `models.py:46` | DB config |
| `min_win_probability` | 0.42 (42%) | `models.py:77` | DB config |

### 8.2 Where Configs Are Stored

1. **Code defaults:** `models.py:30-92` — `BotConfig` dataclass with default values
2. **Database overrides:** `spark_config` table — merged on top of defaults at scanner startup
3. **UI editable:** `PUT /api/spark/config` — writes to `spark_config` table
4. **Scanner loads overrides:** `load_config_overrides()` (`ironforge_scanner.py:108-137`) — maps DB columns to internal config keys

**Config priority:** DB override > code default

### 8.3 What to Change for Risk/Sizing/Strategy Adjustments

| Goal | Parameter | Where |
|------|-----------|-------|
| Wider strikes (safer) | Increase `sd_multiplier` (e.g., 1.5) | UI: Config panel |
| Narrower strikes (more premium) | Decrease `sd_multiplier` (e.g., 1.0) | UI: Config panel |
| More conservative exits | Decrease `profit_target_pct` (e.g., 20%) | UI: Config panel |
| Allow more daily trades | Increase `max_trades_per_day` | UI: Config panel |
| Reduce position size | Decrease `max_contracts` or `buying_power_usage_pct` | UI: Config panel |
| Trade in higher VIX | Increase `vix_skip` (e.g., 40) | UI: Config panel |
| Extend entry window | Change `entry_end` to "15:00" | DB config only |

---

## 9. LOGGING & MONITORING

### 9.1 What SPARK Logs and Where

| What | Table | Level | When |
|------|-------|-------|------|
| Trade opened | `spark_logs` | TRADE_OPEN | Position created |
| Trade closed | `spark_logs` | TRADE_CLOSE | Position closed (PT/SL/EOD) |
| Trade skipped | `spark_logs` | SKIP | Gate blocked entry |
| Error | `spark_logs` | ERROR | Exception during cycle |
| Config change | `spark_logs` | CONFIG | Parameter updated via UI |
| Recovery action | `spark_logs` | RECOVERY | Kill switch, collateral fix |
| Scan activity | `spark_logs` | INFO | Every scan cycle |
| Signal details | `spark_signals` | — | Every signal (executed + skipped) |
| Equity state | `spark_equity_snapshots` | — | Every scan cycle |
| Daily summary | `spark_daily_perf` | — | Aggregated per day |
| PDT actions | `spark_pdt_log` | — | Each trade open/close |
| Scanner heartbeat | `bot_heartbeats` | — | Every scan cycle |

### 9.2 Discord Webhook Notifications

**Status: NONE CONFIGURED**

Per CONFIDENCE_REPORT_2026_03_15.md Phase 7A: "No automated alerting exists. There are no Discord webhooks, Slack integrations, email alerts, or push notifications in the IronForge codebase."

### 9.3 Monitoring via Dashboard

- **Scanner health dot:** Green (< 7 min), Yellow (7-15 min), Red (> 15 min since last heartbeat)
- **Scan countdown:** Shows seconds until next scan (60s interval estimate)
- **PT Tier badge:** Shows current profit target tier (MORNING/MIDDAY/AFTERNOON)
- **Live MTM:** Position monitor endpoint refreshes every 10s with unrealized P&L

### 9.4 Diagnosing a Failed Trade or Missed Entry

Use `GET /api/spark/diagnose-trade` — checks ALL 10 gates and reports which one blocked:
1. Scanner alive (heartbeat < 5 min)
2. Market open
3. Entry window (8:30 AM - 2:00 PM CT)
4. No blocking positions
5. Daily trade limit
6. PDT check
7. Buying power (>= $200)
8. Tradier quotes available
9. VIX gate (<= 32)
10. Account active

For P&L discrepancies: `GET /api/spark/diagnose-pnl` — compares three P&L methods (Tradier spread pricing, manual leg assembly, last snapshot).

---

## 10. KNOWN ISSUES & TECH DEBT

### 10.1 HIGH SEVERITY

| Issue | Location | Impact |
|-------|----------|--------|
| **Hardcoded API keys** | `ironforge_scanner.py:24-38`, `position_monitor.py:22-28` | Production Tradier API keys visible in source code |
| **GEX not integrated** | `signals.py:87-91`, `ironforge_scanner.py:3520-3523` | All GEX fields hardcoded to 0/"UNKNOWN" — strikes use only SD-based math |
| **Oracle not wired** | `signals.py:471-487`, `ironforge_scanner.py:1878-1883` | Oracle/ML advisor fields stored but never populated — defaults to 50% confidence |
| **No daily loss limit** | — | Max daily loss is $4,600 (46% of capital) with no circuit breaker |
| **Position monitor missing equity snapshot** | `position_monitor.py:660` | Equity curve has gaps when monitor (not scanner) closes positions |
| **Monitor doesn't load config overrides** | `position_monitor.py:51-55` | Uses hardcoded BOT_CONFIG — if scanner changes PT/SL in DB, monitor uses stale values |

### 10.2 MEDIUM SEVERITY

| Issue | Location | Impact |
|-------|----------|--------|
| **Frontend doesn't display sandbox close failures** | `StatusCard.tsx` | User unaware of orphaned positions |
| **Force-close route doesn't log sandbox failures** | `force-close/route.ts:77-79` | No audit trail of close failures |
| **EOD-close doesn't log successful closes** | `eod-close/route.ts:145` | Only failures are logged |
| **Min win probability mismatch** | Code: 0.42 vs VALIDATION_FRAMEWORK: 0.50 | Design intent unclear |
| **Paper account not auto-reconciled** | `trader.py` | Balance can drift if position closes outside of executor |

### 10.3 TODOs / FIXMEs / Commented-Out Code

| Item | Location | Status |
|------|----------|--------|
| GEX data integration | `signals.py:38-43` | Logged warning: "GEX data not available" |
| Wings adjustment | Position `wings_adjusted` column always FALSE | Feature built but never activated |
| `oracle_suggested_sd` field | `IronCondorSignal:244` | Stored but never used — intended for dynamic SD adjustment |
| `oracle_use_gex_walls` field | `IronCondorPosition:156` | Stored as FALSE — intended for GEX-based strike adjustment |

### 10.4 Hardcoded Values That Should Be Configurable

| Value | Location | Current | Should Be |
|-------|----------|---------|-----------|
| Min buying power | `ironforge_scanner.py:1876` | $200 | Configurable |
| Min expected move floor | `signals.py:~1295` | 0.5% of spot | Configurable |
| MTM failure threshold | `ironforge_scanner.py:81` | 10 consecutive | Configurable |
| Warm-up window | `ironforge_scanner.py:3527` | 8:20-8:29 AM | Configurable |
| Spread width | `signals.py:1293` | $5 (also in config) | Only config is used |
| Sandbox order timeout | `tradier_client.py:994` | 45 seconds | Configurable (FLAME only, N/A for SPARK) |

### 10.5 CT Timezone Bugs

| Potential Issue | Location | Status |
|----------------|----------|--------|
| EOD cutoff mixing ET/CT | `trader.py:695-706` | **POTENTIAL BUG:** Hard-coded check converts CT time to ET; comment says "2:45 PM ET = 2:45 PM CT" which is wrong (1 hour difference). However, the scanner uses `is_after_eod_cutoff(ct)` checking CT 14:45 directly, which is correct. |
| SQL queries use CT correctly | `databricks-sql.ts:222` | `CONVERT_TIMEZONE('UTC', 'America/Chicago', CURRENT_TIMESTAMP())` — correct |
| Scanner CT | `ironforge_scanner.py` | Uses `get_central_time()` — correct |
| Webapp timestamps | API routes | All use Databricks `CURRENT_TIMESTAMP()` which is set to CT via `SET TIME ZONE` — correct |

**Overall:** Timezone handling appears correct in the Databricks path. The `trader.py` ET/CT confusion exists but is only relevant for the Render path (which is not used in production).

---

## 11. DIFFERENCES FROM FLAME & INFERNO

### 11.1 What Makes SPARK "1DTE"

The **only** difference between SPARK and FLAME in code is `min_dte`:

```python
# models.py
def flame_config(): return BotConfig(bot_name="FLAME", min_dte=2, dte_mode="2DTE")
def spark_config(): return BotConfig(bot_name="SPARK", min_dte=1, dte_mode="1DTE")
```

This single parameter changes:
- **Expiration targeting:** SPARK targets next trading day's expiration; FLAME targets 2 trading days out
- **Theta decay profile:** SPARK options have faster time decay (closer to expiration)
- **Gamma risk:** SPARK options have higher gamma (more sensitive to price moves)
- **Premium collected:** SPARK typically collects less credit (shorter duration = less extrinsic value)

### 11.2 Full Comparison Table

| Aspect | SPARK (1DTE) | FLAME (2DTE) | INFERNO (0DTE) |
|--------|-------------|-------------|----------------|
| **DTE** | 1 | 2 | 0 |
| **SD Multiplier** | 1.2 | 1.2 | 1.0 (tighter strikes) |
| **Spread Width** | $5 | $5 | $5 |
| **Profit Target** | 30% (slides to 15%) | 30% (slides to 15%) | 50% (slides to 10%) |
| **Stop Loss** | 2.0x entry | 2.0x entry | 3.0x entry |
| **Max Trades/Day** | 1 | 1 | Unlimited (0) |
| **Max Contracts** | 10 | 10 | Unlimited (0, sized by BP) |
| **Entry End** | 2:00 PM CT | 2:00 PM CT | 2:30 PM CT |
| **EOD Cutoff** | 2:45 PM CT | 2:45 PM CT | 2:45 PM CT |
| **Starting Capital** | $10,000 | $10,000 | $10,000 |
| **VIX Skip** | > 32 | > 32 | > 32 |
| **Sandbox Mirror** | **NO** | YES (3 accounts) | **NO** |
| **PDT Enforced** | YES | YES | NO (max 0 = unlimited) |
| **UI Accent** | Blue (`#3b82f6`) | Amber (`#f59e0b`) | Red (`#ef4444`) |
| **Concurrent Positions** | 1 max | 1 max | Unlimited |

### 11.3 Shared Code vs SPARK-Specific Code Paths

**100% shared code.** SPARK has zero SPARK-only files. All behavior is parameterized:

| Component | File | Shared? | Parameterized By |
|-----------|------|---------|-----------------|
| Trading orchestrator | `trading/trader.py` | Shared | `BotConfig.min_dte`, `BotConfig.dte_mode` |
| Signal generator | `trading/signals.py` | Shared | `BotConfig.sd_multiplier`, `BotConfig.min_dte` |
| Paper executor | `trading/executor.py` | Shared | `BotConfig.bot_name` (FLAME gets sandbox, SPARK doesn't) |
| Database layer | `trading/db.py` | Shared | Bot name prefix (`spark_` tables) |
| Tradier client | `trading/tradier_client.py` | Shared | No bot-specific logic |
| Models | `trading/models.py` | Shared | `spark_config()` factory function |
| Scanner | `databricks/ironforge_scanner.py` | Shared | Bot config dict |
| Dashboard | `webapp/src/components/BotDashboard.tsx` | Shared | `bot="spark"` prop |
| Dashboard page | `webapp/src/app/spark/page.tsx` | Minimal wrapper | `<BotDashboard bot="spark" accent="blue" />` |
| All API routes | `webapp/src/app/api/[bot]/` | Shared | Dynamic `[bot]` route parameter |

### 11.4 Key Branching Points in Shared Code

The scanner distinguishes bots at these points:

```python
# ironforge_scanner.py

# Sandbox mirroring (FLAME only)
if bot["name"] == "flame" and not _flame_sandbox_paper_only:
    # Mirror to 3 Tradier sandbox accounts
else:
    # SPARK/INFERNO: paper-only, skip sandbox

# Entry end time
entry_end = BOT_CONFIG[bot["name"]]["entry_end"]  # SPARK=1400, INFERNO=1430

# Max trades per day
max_trades = BOT_CONFIG[bot["name"]]["max_trades"]  # SPARK=1, INFERNO=0 (unlimited)

# Profit target
pt_pct = BOT_CONFIG[bot["name"]]["pt_pct"]  # SPARK=0.30, INFERNO=0.50

# Stop loss multiplier
sl_mult = BOT_CONFIG[bot["name"]]["sl_mult"]  # SPARK=2.0, INFERNO=3.0

# Pending order management
if bot["name"] == "flame":
    # Check pending_orders table for sandbox fills
    # SPARK/INFERNO: skip
```

### 11.5 Shared Utility Functions

All bots share these functions with no bot-specific branching:

| Function | Purpose | File |
|----------|---------|------|
| `get_target_expiration(min_dte)` | Find expiration N trading days out | `signals.py` / `ironforge_scanner.py` |
| `calculate_strikes(spot, em, sd, width)` | SD-based strike selection | `signals.py` / `ironforge_scanner.py` |
| `get_ic_entry_credit()` | Fetch 4-leg IC credit from Tradier | `signals.py` / `ironforge_scanner.py` |
| `get_ic_mark_to_market()` | Live 4-leg MTM from Tradier | `signals.py` / `ironforge_scanner.py` |
| `validate_mtm()` | Check MTM data quality | `signals.py` / `ironforge_scanner.py` |
| `evaluate_advisor()` | Lightweight ML-style scoring | `ironforge_scanner.py` |
| `get_sliding_profit_target()` | Time-based PT tier | `trader.py` / `ironforge_scanner.py` |
| `close_position()` | Atomic position close + P&L + collateral | `executor.py` / `ironforge_scanner.py` |
| `save_equity_snapshot()` | Periodic snapshot insert | `db.py` / `ironforge_scanner.py` |

---

## Appendix A: API Routes for SPARK

All routes are dynamic: `/api/spark/...` (same code as `/api/flame/...` and `/api/inferno/...`)

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/spark/status` | Account balance, P&L, open positions, heartbeat |
| GET | `/api/spark/positions` | Open positions |
| GET | `/api/spark/position-monitor` | Live MTM, PT/SL proximity |
| GET | `/api/spark/position-detail` | Per-leg quotes |
| GET | `/api/spark/equity-curve` | Historical equity from closed trades |
| GET | `/api/spark/equity-curve/intraday` | Today's 5-min snapshots |
| GET | `/api/spark/trades` | Closed trade history |
| GET | `/api/spark/performance` | Win rate, P&L stats |
| GET | `/api/spark/daily-perf` | Last 30 days daily summary |
| GET | `/api/spark/config` | Current config (defaults + DB overrides) |
| PUT | `/api/spark/config` | Update config parameters |
| POST | `/api/spark/toggle` | Enable/disable bot |
| POST | `/api/spark/force-trade` | Force open IC position |
| POST | `/api/spark/force-close` | Force close position |
| POST | `/api/spark/eod-close` | Force close all positions (EOD) |
| GET | `/api/spark/logs` | Activity logs |
| GET | `/api/spark/signals` | Recent signals |
| GET | `/api/spark/fix-collateral` | Diagnose stuck collateral |
| POST | `/api/spark/fix-collateral` | Fix stuck collateral |
| GET | `/api/spark/diagnose-trade` | Why isn't bot trading? |
| GET | `/api/spark/diagnose-pnl` | P&L discrepancy check |
| GET | `/api/spark/pdt` | PDT status, day trade count |
| POST | `/api/spark/pdt` | Toggle PDT enforcement, reset counter |
| GET | `/api/spark/pdt/audit` | PDT audit log |

---

## Appendix B: File Index

| File | Purpose | Lines Referenced |
|------|---------|-----------------|
| `ironforge/trading/models.py` | BotConfig, IronCondorPosition, PaperAccount | 30-118, 122-210, 256-282 |
| `ironforge/trading/trader.py` | Trader orchestrator — run_cycle, position mgmt | 129-386, 435-579, 658-706 |
| `ironforge/trading/signals.py` | Signal generator — strikes, credits, MTM | 61-95, 166-259, 261-319, 384-392, 470-511, 556-664 |
| `ironforge/trading/executor.py` | Paper executor — open/close, collateral | 217-241, 243-438, 440-588 |
| `ironforge/trading/db.py` | TradingDatabase — all SQL operations | 65-159, 161-330, 332-625, 631-987 |
| `ironforge/trading/tradier_client.py` | Tradier API client | 21-36, 79-168, 200-523 |
| `ironforge/databricks/ironforge_scanner.py` | Monolithic scanner (all bots) | 24-41, 80-137, 1106-1172, 1290-1314, 1333-1631, 1639-1809, 1817-2218, 2226-2561, 3506-3549 |
| `ironforge/jobs/run_spark.py` | Render entry point (not used in prod) | 1-75 |
| `ironforge/jobs/run_all.py` | Combined runner (all bots, threads) | 1-116 |
| `ironforge/webapp/src/app/spark/page.tsx` | SPARK dashboard page (thin wrapper) | 1-7 |
| `ironforge/webapp/src/lib/databricks-sql.ts` | Databricks SQL client | 15-222 |
| `ironforge/webapp/src/components/BotDashboard.tsx` | Main dashboard component | 65-338 |
| `ironforge/webapp/src/components/StatusCard.tsx` | Status card with config | 94-548 |
| `ironforge/webapp/src/components/PositionTable.tsx` | Position cards with PT/SL bar | 110-389 |
| `ironforge/webapp/src/components/EquityChart.tsx` | Recharts equity curve | 78-439 |
| `ironforge/webapp/src/components/PdtCard.tsx` | PDT status banner | 99-281 |
| `ironforge/webapp/src/app/api/[bot]/status/route.ts` | Status API | Full file |
| `ironforge/webapp/src/app/api/[bot]/config/route.ts` | Config API | 16-182 |
| `ironforge/webapp/src/app/api/[bot]/force-trade/route.ts` | Force trade API | Full file |
| `ironforge/webapp/src/app/api/[bot]/force-close/route.ts` | Force close API | Full file |
| `ironforge/webapp/src/app/api/[bot]/diagnose-trade/route.ts` | Trade diagnosis | 164-262 |
| `ironforge/webapp/src/app/api/[bot]/diagnose-pnl/route.ts` | P&L diagnosis | Full file |
| `ironforge/webapp/src/app/api/sandbox/emergency-close/route.ts` | Kill switch | Full file |
| `ironforge/CLAUDE.md` | IronForge system documentation | Full file |
| `ironforge/ARCHITECTURE_AUDIT_2026-03-14.md` | Architecture audit findings | F1-F5 |
| `ironforge/CONFIDENCE_REPORT_2026_03_15.md` | Validation confidence report | Phases 1-7 |

---

*Generated by automated codebase analysis. All facts verified against source code. Items marked UNKNOWN require runtime verification.*
