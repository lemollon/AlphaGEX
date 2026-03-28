# CLAUDE.md - IronForge

## What Is IronForge

IronForge is a **standalone SPY Iron Condor paper trading system** that runs independently from the main AlphaGEX platform. It uses **PostgreSQL on Render** for all data storage and runs as a **Render-hosted Next.js web service** (dashboard + scanner in one process).

It runs three bots — **FLAME** (2DTE), **SPARK** (1DTE), and **INFERNO** (0DTE) — that trade SPY Iron Condors using real Tradier market data with paper execution. INFERNO is a FORTRESS-style aggressive bot that allows unlimited trades/day with multiple simultaneous positions.

## Architecture

### HARD RULES — violating these causes production failures

| Layer | Technology | Status |
|-------|-----------|--------|
| Frontend + API + Scanner | Next.js 14 on **Render** (single web service) | ACTIVE |
| Database | **PostgreSQL** on Render | ACTIVE |
| DB Client | `@/lib/db.ts` (dbQuery, dbExecute, query, escapeSql, sharedTable, botTable, validateBot, dteMode) | ACTIVE |
| Scanner | `@/lib/scanner.ts` (runs inside Next.js process, 1-min interval) | ACTIVE |
| DDL Script | `setup_tables.py` (PostgreSQL table creation) | ACTIVE |
| Databricks | **DEAD** — too expensive, migrated to Render | NEVER |
| `@/lib/databricks-sql.ts` | **DEAD** — Databricks REST API client | NEVER IMPORT |
| `ironforge/databricks/` | **DEAD** — Databricks scanner and API | NEVER TOUCH |

### Architecture enforcement:
1. If ANY file imports from `@/lib/databricks-sql` — that file is **broken** and must use `@/lib/db`
2. Every database operation goes through `dbQuery()`, `dbExecute()`, or `query()` from `@/lib/db.ts`
3. Table names use `botTable(bot, 'tablename')` → `{bot}_{tablename}`
4. Shared tables use `sharedTable('tablename')` → `{tablename}`
5. All times are Central Time (America/Chicago)
6. Upserts use PostgreSQL `INSERT ... ON CONFLICT ... DO UPDATE SET` (NOT Databricks `MERGE INTO`)

### Render Environment Variables (required)
- `DATABASE_URL` — PostgreSQL connection string (from Render database)
- `TRADIER_API_KEY` — for live market data quotes
- `TRADIER_SANDBOX_KEY_USER` — sandbox account key (User)
- `TRADIER_SANDBOX_KEY_MATT` — sandbox account key (Matt)
- `TRADIER_SANDBOX_KEY_LOGAN` — sandbox account key (Logan)

```
ironforge/
├── databricks/                # ⚠️ DEAD — Databricks-native backend (deprecated)
│
├── trading/                   # Python trading engine (reference only — scanner.ts is active)
│   ├── models.py              # BotConfig, IronCondorPosition, IronCondorSignal, PaperAccount
│   ├── trader.py              # Trader orchestrator (run_cycle, position management, exit logic)
│   ├── signals.py             # SignalGenerator (Tradier quotes, SD-based strikes, symmetric wings)
│   ├── executor.py            # PaperExecutor (open/close paper positions, collateral math)
│   ├── db.py                  # TradingDatabase (all SQL: positions, PDT, signals, equity, logs)
│   └── tradier_client.py      # Standalone Tradier API client (quotes, chains, VIX)
│
├── jobs/                      # Python entry points (reference only — scanner.ts runs in webapp)
│
└── webapp/                    # Next.js 14 dashboard (App Router) — deployed on Render
    ├── package.json           # next 14.2, react 18, recharts, swr, tailwind
    ├── src/
    │   ├── lib/
    │   │   ├── db.ts              # PostgreSQL client (dbQuery, dbExecute, query, botTable, sharedTable, validateBot, dteMode)
    │   │   ├── databricks-sql.ts  # ⚠️ DEAD — Databricks REST API client, do NOT import
    │   │   ├── fetcher.ts         # SWR fetcher
    │   │   ├── format.ts          # Number/date formatters
    │   │   ├── pt-tiers.ts        # Market hours, CT time helpers
    │   │   ├── scanner.ts         # Trading scanner (1-min interval, all 3 bots)
    │   │   └── tradier.ts         # Server-side Tradier client for position monitor
    │   ├── components/
    │   │   ├── BotDashboard.tsx    # Main bot dashboard (tabs: Equity, Performance, Positions, Trades, Logs)
    │   │   ├── StatusCard.tsx      # Account status summary
    │   │   ├── EquityChart.tsx     # Recharts equity curve (intraday + historical)
    │   │   ├── PerformanceCard.tsx # Win rate, P&L stats
    │   │   ├── PositionTable.tsx   # Open positions with live MTM
    │   │   ├── TradeHistory.tsx    # Closed trades table
    │   │   ├── LogsTable.tsx       # Activity logs
    │   │   ├── PdtCard.tsx         # PDT (Pattern Day Trader) enforcement card
    │   │   ├── PdtCalendar.tsx     # 4-week rolling PDT calendar grid
    │   │   ├── PTTimeline.tsx      # Paper trading timeline
    │   │   └── Nav.tsx             # Navigation bar
    │   └── app/
    │       ├── page.tsx            # Home — bot cards, strategy config, signal flow
    │       ├── flame/page.tsx      # FLAME dashboard (BotDashboard bot="flame")
    │       ├── spark/page.tsx      # SPARK dashboard (BotDashboard bot="spark")
    │       ├── inferno/page.tsx    # INFERNO dashboard (BotDashboard bot="inferno")
    │       ├── accounts/page.tsx   # Account management
    │       ├── compare/page.tsx    # Side-by-side bot comparison
    │       ├── layout.tsx          # Root layout with Nav
    │       ├── globals.css         # Dark theme (forge-bg, forge-card, fire-divider)
    │       └── api/[bot]/          # Dynamic API routes (bot = flame | spark | inferno)
    │           ├── status/route.ts
    │           ├── positions/route.ts
    │           ├── position-monitor/route.ts
    │           ├── position-detail/route.ts
    │           ├── equity-curve/route.ts
    │           ├── equity-curve/intraday/route.ts
    │           ├── trades/route.ts
    │           ├── performance/route.ts
    │           ├── daily-perf/route.ts
    │           ├── config/route.ts
    │           ├── toggle/route.ts
    │           ├── force-trade/route.ts
    │           ├── force-close/route.ts
    │           ├── logs/route.ts
    │           ├── fix-collateral/route.ts # Fix stuck collateral (diagnose + repair)
    │           ├── diagnose-trade/route.ts # Diagnose why bot isn't trading
    │           ├── diagnose-pnl/route.ts  # Diagnose P&L discrepancies
    │           ├── eod-close/route.ts     # Force close all positions (EOD)
    │           ├── signals/route.ts       # Recent signals
    │           ├── pdt/route.ts         # ✅ Databricks — PDT status + toggle/reset
    │           └── pdt/audit/route.ts   # ✅ Databricks — PDT audit log
    └── .env.local.example
```

### Migration Status — ✅ COMPLETE (Render/PostgreSQL)

All API routes use PostgreSQL via `@/lib/db`. Zero imports from `@/lib/databricks-sql` remain.
Scanner runs inside the Next.js process via `@/lib/scanner.ts`.

- `api/[bot]/pdt/route.ts` — PDT status, toggle, reset
- `api/[bot]/pdt/audit/route.ts` — PDT audit log
- `api/[bot]/status/route.ts` — Account balance, P&L, heartbeat
- `api/[bot]/positions/route.ts` — Open positions
- `api/[bot]/position-monitor/route.ts` — Live MTM via Tradier
- `api/[bot]/position-detail/route.ts` — Per-leg quotes, sandbox accounts
- `api/[bot]/equity-curve/route.ts` — Historical equity curve
- `api/[bot]/equity-curve/intraday/route.ts` — Today's equity snapshots
- `api/[bot]/trades/route.ts` — Closed trade history
- `api/[bot]/performance/route.ts` — Win rate, P&L stats
- `api/[bot]/daily-perf/route.ts` — Daily performance summary
- `api/[bot]/config/route.ts` — Config read/upsert (ON CONFLICT)
- `api/[bot]/toggle/route.ts` — Enable/disable bot
- `api/[bot]/force-trade/route.ts` — Force open IC position
- `api/[bot]/force-close/route.ts` — Force close position
- `api/[bot]/logs/route.ts` — Activity logs
- `api/health/route.ts` — PostgreSQL + Tradier connectivity check
- `api/accounts/manage/route.ts` — Account CRUD
- `api/accounts/manage/[id]/route.ts` — Account update/delete
- `api/accounts/test-all/route.ts` — Account connectivity test
- `api/accounts/production/route.ts` — Sandbox account balances with bot attribution

## Bots

| Bot | DTE | Description |
|-----|-----|-------------|
| **FLAME** | 2DTE | Longer-duration Iron Condors. More premium, more time to work. |
| **SPARK** | 1DTE | Shorter-duration Iron Condors. Faster theta decay, quicker resolution. |
| **INFERNO** | 0DTE | FORTRESS-style aggressive Iron Condors. Unlimited trades/day, multiple simultaneous positions. |

FLAME and SPARK share identical config except `min_dte`. INFERNO uses FORTRESS-style aggressive parameters. Key parameters:
- Ticker: SPY
- Starting capital: $10,000 (paper)
- Spread width: $5
- SD multiplier: 1.2x (FLAME/SPARK), 1.0x (INFERNO)
- Profit target: 30% of credit (FLAME/SPARK), 50% (INFERNO)
- Stop loss: 100% of credit / 2.0x (FLAME/SPARK), 100% of credit / 2.0x (INFERNO)
- Max 1 trade/day (FLAME/SPARK), unlimited (INFERNO)
- 3 max contracts (INFERNO), BP-sized (FLAME/SPARK)
- VIX skip: > 32
- PDT limit: 4 day trades / 5 rolling business days (matches FINRA Rule 4210)
- Entry window: 8:30 AM - 2:00 PM CT (FLAME/SPARK), 8:30 AM - 2:30 PM CT (INFERNO)
- EOD cutoff: 2:50 PM CT (scanner.ts isAfterEodCutoff >= 1450)
- Scan frequency: every 1 minute (scanner.ts SCAN_INTERVAL_MS)

## Trading Cycle (trader.py `run_cycle()`)

1. Always manage existing positions first (profit target, stop loss, EOD, stale/expired)
2. Check bot active
3. Check trading window
4. Check open positions (only 1 at a time)
5. Check already-traded-today (max 1/day)
6. PDT check
7. Buying power check (>$200)
8. Generate signal (Tradier spot + VIX, SD strikes, symmetric wings, real bid/ask credits)
9. Size trade (collateral math, 85% BP usage)
10. Race guard (re-check no open position)
11. Execute paper trade
12. Save equity snapshot every cycle

## Exit Logic

| Trigger | Condition |
|---------|-----------|
| Profit target | Cost to close <= 70% of entry credit |
| Stop loss | Cost to close >= 200% of entry credit (2.0x) |
| EOD safety | Time >= 2:50 PM CT |
| Daily loss limit | INFERNO: today's losses >= 3% of balance |
| Post-SL cooldown | INFERNO: 30 min wait after stop loss before re-entry |
| Stale/expired | Position from prior day or past expiration |
| Data failure | 10 consecutive MTM failures |
| Server restart | Force-close if market closed, resume if open |

## Database Tables (PostgreSQL on Render)

Per-bot tables (prefix = `flame_`, `spark_`, or `inferno_`):
- `{bot}_positions` — All positions (open, closed, expired). Key columns: strikes, credits, oracle data, wings_adjusted, status, realized_pnl
- `{bot}_signals` — Every signal generated (executed or skipped)
- `{bot}_paper_account` — Paper account state (balance, cumulative P&L, collateral, buying power, HWM, drawdown)
- `{bot}_equity_snapshots` — Periodic snapshots (every 5-min cycle) for intraday chart
- `{bot}_daily_perf` — Daily performance summary
- `{bot}_logs` — Activity log (TRADE_OPEN, TRADE_CLOSE, SKIP, ERROR, RECOVERY, CONFIG)
- `{bot}_pdt_log` — PDT day trade records (written by scanner)
- `{bot}_pdt_config` — PDT enforcement config (per-bot)
- `{bot}_pdt_audit_log` — PDT audit trail (UI actions)

Shared tables:
- `ironforge_pdt_config` — Shared PDT config (read/written by scanner + webapp)
- `ironforge_pdt_log` — Shared PDT audit log (written by scanner)
- `ironforge_accounts` — Tradier account credentials
- `bot_heartbeats` — Shared heartbeat table for all bots

## Deployment

| Layer | Platform | Details |
|-------|----------|---------|
| Frontend + API + Scanner | **Render** | Next.js 14 standalone, single web service |
| Database | **Render PostgreSQL** | Auto-created tables via `db.ts` on first use |

## API Routes

All routes are dynamic: `/api/[bot]/...` where bot is `flame`, `spark`, or `inferno`.

| Route | Description |
|-------|-------------|
| `GET /api/{bot}/pdt` | PDT status, day trade count, trigger trades |
| `POST /api/{bot}/pdt` | Toggle PDT enforcement, reset counter |
| `GET /api/{bot}/pdt/audit` | PDT audit log (last 10 events) |
| `GET /api/{bot}/status` | Account balance, P&L, open positions, heartbeat |
| `GET /api/{bot}/positions` | Open positions with live data |
| `GET /api/{bot}/position-monitor` | Live MTM, P&L %, profit target/stop loss proximity |
| `GET /api/{bot}/position-detail` | Per-leg quotes, sandbox accounts, PT tier |
| `GET /api/{bot}/equity-curve` | Historical equity curve from closed trades |
| `GET /api/{bot}/equity-curve/intraday` | Today's equity snapshots (5-min intervals) |
| `GET /api/{bot}/trades` | Closed trade history |
| `GET /api/{bot}/performance` | Win rate, total P&L, avg win/loss, best/worst trade |
| `GET /api/{bot}/daily-perf` | Last 30 days daily performance summary |
| `GET /api/{bot}/config` | Bot config (merged defaults + DB) |
| `PUT /api/{bot}/config` | Update bot config (MERGE upsert) |
| `POST /api/{bot}/toggle` | Enable/disable bot |
| `POST /api/{bot}/force-trade` | Force open IC position |
| `POST /api/{bot}/force-close` | Force close position |
| `GET /api/{bot}/logs` | Activity logs |
| `GET /api/{bot}/fix-collateral` | Diagnose stuck collateral (read-only) |
| `POST /api/{bot}/fix-collateral` | Fix stuck collateral (close stale positions + reconcile) |
| `GET /api/{bot}/diagnose-trade` | Diagnose why bot isn't trading |
| `GET /api/{bot}/diagnose-pnl` | Diagnose P&L discrepancies |
| `POST /api/{bot}/eod-close` | Force close all positions (EOD safety) |
| `GET /api/{bot}/signals` | Recent signals (scan activity) |
| `GET /api/health` | Databricks connectivity check |

## Frontend Pages

| Route | Description |
|-------|-------------|
| `/` | Home — bot cards, shared strategy config, signal flow diagram |
| `/flame` | FLAME dashboard (StatusCard + PdtCard + tabbed content) |
| `/spark` | SPARK dashboard (same layout, blue accent) |
| `/inferno` | INFERNO dashboard (same layout, red accent — 0DTE FORTRESS-style) |
| `/compare` | Side-by-side comparison of all bots |
| `/accounts` | Account management (Tradier credentials) |

## Key Design Decisions

1. **Fully standalone** — no imports from the main AlphaGEX codebase. Has its own Tradier client, config, DB layer
2. **Unified code for all bots** — Trader, SignalGenerator, PaperExecutor, TradingDatabase all parameterized by BotConfig (FLAME/SPARK differ only by `min_dte`; INFERNO adds `max_trades_per_day=0` (unlimited) and FORTRESS-style parameters)
3. **Real market data, paper execution** — Tradier production/sandbox API for quotes and option chains, but no actual orders placed
4. **Conservative fills** — sells at bid, buys at ask (worst-case paper fills)
5. **PostgreSQL on Render** — all persistence via PostgreSQL. Next.js API routes use `@/lib/db.ts` client. Tables auto-created on first use.
6. **Oracle fields stored but not yet wired** — position table has oracle_confidence, oracle_win_probability, etc. but signal generator doesn't call Oracle yet

## Running Locally

```bash
# Frontend + Scanner
cd ironforge/webapp
npm install

# Set PostgreSQL + Tradier credentials in .env.local:
# DATABASE_URL=postgresql://localhost:5432/ironforge
# TRADIER_API_KEY=...
# TRADIER_SANDBOX_KEY_USER=...

npm run dev
# → http://localhost:3000
# Scanner auto-starts on first DB connection
```

## Relationship to AlphaGEX

IronForge lives inside the AlphaGEX monorepo at `ironforge/` but is **completely independent**. It shares no code with the main AlphaGEX backend/frontend. It was designed as a lightweight, portable system that can run without the complexity of the full AlphaGEX infrastructure.

The `ironforge/webapp/` directory contains the Next.js dashboard + scanner, deployed on Render as a single web service.

## HARD RULE: All Backend Fixes Must Live in the Webapp

**ALL diagnostic tools, fix scripts, and backend operations MUST be implemented as API routes in `ironforge/webapp/src/app/api/`.** Do NOT create:
- Standalone Python scripts in `ironforge/scripts/`
- Databricks notebooks in `ironforge/databricks/`
- Any backend code outside the webapp

**Why:** The webapp is the only deployed backend. Vercel serves the Next.js API routes. There is no other backend server. Scripts and notebooks require manual Databricks access — the webapp API routes can be called from the browser or curl immediately.

**Pattern for fix/diagnostic endpoints:**
```
GET  /api/{bot}/fix-{issue}  → Read-only diagnostic (safe to call anytime)
POST /api/{bot}/fix-{issue}  → Apply the fix
```

## Known Issues & Fixes

### Stuck Collateral (Collateral > 0 with 0 Open Positions)

**Symptoms:** Dashboard shows non-zero collateral_in_use but 0 open positions. Buying power appears reduced.

**Root Causes:**
1. **Stale positions**: Positions past expiration or from a prior trading day still marked `status = 'open'`
2. **Orphan positions**: Open positions with wrong/NULL `dte_mode` — invisible to the status API's dte filter but holding collateral
3. **Paper account drift**: `paper_account.collateral_in_use` gets out of sync with actual open positions (e.g., position was closed but collateral wasn't released)
4. **Schema mismatch**: Vercel `DATABRICKS_SCHEMA` env var pointing to `default` instead of `ironforge` — reads completely different stale data

**Fix:**
```
# Diagnose (read-only)
GET /api/inferno/fix-collateral

# Apply fix (closes stale positions + reconciles paper_account)
POST /api/inferno/fix-collateral
```

**How the status API prevents this (live reconciliation):**
The `/api/{bot}/status` route does NOT read `paper_account.collateral_in_use`. Instead it recalculates:
- `collateral` = SUM(collateral_required) FROM positions WHERE status='open' AND dte_mode='{dte}'
- `realized_pnl` = SUM(realized_pnl) FROM positions WHERE status IN ('closed','expired') AND dte_mode='{dte}'
- `balance` = starting_capital + realized_pnl
- `buying_power` = balance - collateral

If the dashboard still shows wrong values despite the database being correct, check that `DATABASE_URL` points to the correct PostgreSQL instance.

### Balance Drift (P&L Doesn't Match Closed Trades)

**Symptoms:** Dashboard balance doesn't equal `starting_capital + sum(realized_pnl from closed trades)`.

**Root Cause:** `paper_account.current_balance` drifted due to double-counting (position P&L added twice) or missed updates.

**Fix:** Same as stuck collateral — `POST /api/{bot}/fix-collateral` reconciles all values.

### Tradier Sandbox Positions Won't Close (400 Errors)

**Symptoms:** Notebook or API trying to close Tradier sandbox positions gets 400 errors on all attempts (4-leg, 2x2-leg, individual).

**Root Causes (in order of likelihood):**
1. **Market is closed** — Options can only be traded during market hours (8:30 AM - 3:00 PM CT). Sandbox rejects orders outside this window.
2. **Options expired** — 0DTE options (same-day expiration) can't be closed after ~2:45 PM CT. They auto-expire at settlement. Wait for overnight settlement, then collateral is released.
3. **Negative buying power** — Even closing orders can be rejected when option buying power is deeply negative. Close smallest positions first to free margin, then close larger ones.
4. **Sandbox quantity limits** — Very large orders (200+ contracts) may be rejected. Split into smaller batches.

**Fix procedure:**
1. Wait until next market day (after 8:30 AM CT)
2. Expired options (0DTE) will have settled overnight — their collateral is released
3. Close remaining open positions (March 16, March 17 expirations) during market hours
4. If 400 errors persist, try smaller quantities or contact Tradier support for sandbox reset

**Prevention:** The scanner's EOD close logic (`eod-close` API route + scanner `close_position()`) should close all positions before 2:45 PM CT daily. If positions are left open:
- Check scanner heartbeat (is it running?)
- Check scanner logs for close failures
- Use `POST /api/{bot}/force-close` during market hours

## Operations Runbook

### Daily Health Check
1. Visit each bot dashboard (FLAME, SPARK, INFERNO)
2. Verify: open_positions matches collateral (0 positions = $0 collateral)
3. Verify: balance = $10,000 + cumulative_pnl
4. Check scanner heartbeat is recent (< 10 min old)

### When Dashboard Shows Wrong Data
```
Step 1: Check database directly (Databricks SQL Editor)
  → SELECT * FROM alpha_prime.ironforge.{bot}_paper_account WHERE is_active = TRUE

Step 2: Check API directly (browser)
  → ironforge-pi.vercel.app/api/{bot}/status

Step 3: Compare database vs API
  → If API matches database but dashboard is wrong → browser cache (Ctrl+Shift+R)
  → If API differs from database → Databricks SQL cache issue (check cacheBust in databricks-sql.ts)
  → If both are wrong → data needs reconciliation (POST /api/{bot}/fix-collateral)
```

### When Positions Are Stuck Open
```
Step 1: Check if market is open (8:30 AM - 3:00 PM CT, Mon-Fri)
  → If closed: wait until next market day

Step 2: Try force-close via webapp
  → POST /api/{bot}/force-close

Step 3: If force-close fails, use fix-collateral
  → POST /api/{bot}/fix-collateral
  (closes stale/expired/orphan positions in the database)

Step 4: For Tradier sandbox positions, run close_all_tradier_positions notebook
  → ONLY during market hours
  → Expired options settle automatically overnight
```

### When Adding New Features or Fixes
1. **ALL backend code goes in `ironforge/webapp/src/app/api/`** — no scripts, no notebooks
2. **Create a PR to `main`** — Vercel auto-deploys from main
3. **Verify deployment** — check Vercel Deployments page, then hit the API endpoint in browser
4. **Test with GET first** — diagnostic endpoints should be read-only on GET, write on POST
