# CLAUDE.md - IronForge

## What Is IronForge

IronForge is a **standalone SPY Iron Condor paper trading system** that runs independently from the main AlphaGEX platform. It uses **Databricks (Delta Lake)** for all data storage and a **Vercel-hosted Next.js dashboard** for the frontend.

It runs three bots — **FLAME** (2DTE), **SPARK** (1DTE), and **INFERNO** (0DTE) — that trade SPY Iron Condors using real Tradier market data with paper execution. INFERNO is a FORTRESS-style aggressive bot that allows unlimited trades/day with multiple simultaneous positions.

## Architecture

### HARD RULES — violating these causes production failures

| Layer | Technology | Status |
|-------|-----------|--------|
| Frontend | Next.js 14 on **Vercel** | ACTIVE |
| Database | **Databricks** (alpha_prime.default schema, Delta Lake) | ACTIVE |
| DB Client | `@/lib/databricks-sql.ts` (dbQuery, dbExecute, escapeSql, sharedTable, botTable, validateBot, dteMode) | ACTIVE |
| Scanner | `ironforge/databricks/ironforge_scanner.py` (runs on Databricks) | ACTIVE |
| API | `ironforge/databricks/ironforge_api.py` (FastAPI on Databricks) | ACTIVE |
| PostgreSQL | **DEAD** — suspended, no data, never use | NEVER |
| Render | **DEAD** — never used for IronForge | NEVER |
| `@/lib/db.ts` | **DEAD** — PostgreSQL client from failed migration attempt | NEVER IMPORT |
| `setup_tables.py` | **DEAD** — PostgreSQL DDL script | NEVER TOUCH |

### Architecture enforcement:
1. If ANY file imports from `@/lib/db` — that file is **broken** and must be migrated to `@/lib/databricks-sql`
2. If ANY reference to Render, PostgreSQL, `DATABASE_URL`, `pg`, or `Pool` exists — it is **dead code**
3. Every database operation goes through `dbQuery()` or `dbExecute()` from `@/lib/databricks-sql.ts`
4. Table names use `botTable(bot, 'tablename')` → `alpha_prime.default.{bot}_{tablename}`
5. Shared tables use `sharedTable('tablename')` → `alpha_prime.default.{tablename}`
6. All times are Central Time (America/Chicago)

### Vercel Environment Variables (required)
- `DATABRICKS_SERVER_HOSTNAME` — SQL warehouse hostname
- `DATABRICKS_HTTP_PATH` — warehouse HTTP path
- `DATABRICKS_TOKEN` — personal access token or service principal token
- `TRADIER_API_KEY` — for live market data quotes

```
ironforge/
├── databricks/                # Databricks-native backend
│   ├── ironforge_scanner.py   # Trading scanner (runs on Databricks compute)
│   ├── ironforge_api.py       # FastAPI endpoints (runs on Databricks)
│   └── sql/                   # DDL scripts for Delta Lake tables
│
├── trading/                   # Python trading engine (shared by all bots)
│   ├── models.py              # BotConfig, IronCondorPosition, IronCondorSignal, PaperAccount
│   ├── trader.py              # Trader orchestrator (run_cycle, position management, exit logic)
│   ├── signals.py             # SignalGenerator (Tradier quotes, SD-based strikes, symmetric wings)
│   ├── executor.py            # PaperExecutor (open/close paper positions, collateral math)
│   ├── db.py                  # TradingDatabase (all SQL: positions, PDT, signals, equity, logs)
│   └── tradier_client.py      # Standalone Tradier API client (quotes, chains, VIX)
│
├── jobs/                      # Entry points for bot workers
│   ├── run_flame.py           # FLAME (2DTE) — runs every 5 min
│   ├── run_spark.py           # SPARK (1DTE) — runs every 5 min
│   └── run_inferno.py         # INFERNO (0DTE) — runs every 5 min
│
└── webapp/                    # Next.js 14 dashboard (App Router) — deployed on Vercel
    ├── package.json           # next 14.2, react 18, recharts, swr, tailwind
    ├── src/
    │   ├── lib/
    │   │   ├── databricks-sql.ts  # Databricks SQL client (dbQuery, dbExecute, botTable, sharedTable, validateBot, dteMode)
    │   │   ├── db.ts              # ⚠️ DEAD — PostgreSQL client, do NOT import
    │   │   ├── fetcher.ts         # SWR fetcher
    │   │   ├── format.ts          # Number/date formatters
    │   │   ├── pt-tiers.ts        # Market hours, CT time helpers
    │   │   ├── scanner.ts         # Scanner status helpers
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
    │           ├── pdt/route.ts         # ✅ Databricks — PDT status + toggle/reset
    │           └── pdt/audit/route.ts   # ✅ Databricks — PDT audit log
    └── .env.local.example
```

### Migration Status

Routes migrated to Databricks (`@/lib/databricks-sql`):
- `api/[bot]/pdt/route.ts` — PDT status, toggle, reset
- `api/[bot]/pdt/audit/route.ts` — PDT audit log
- `api/accounts/manage/route.ts` — Account CRUD
- `api/accounts/manage/[id]/route.ts` — Account update/delete
- `api/accounts/test-all/route.ts` — Account connectivity test

Routes still on dead `@/lib/db` (need migration):
- `api/[bot]/status/route.ts`
- `api/[bot]/positions/route.ts`
- `api/[bot]/position-monitor/route.ts`
- `api/[bot]/position-detail/route.ts`
- `api/[bot]/equity-curve/route.ts`
- `api/[bot]/equity-curve/intraday/route.ts`
- `api/[bot]/trades/route.ts`
- `api/[bot]/performance/route.ts`
- `api/[bot]/daily-perf/route.ts`
- `api/[bot]/config/route.ts`
- `api/[bot]/toggle/route.ts`
- `api/[bot]/force-trade/route.ts`
- `api/[bot]/force-close/route.ts`
- `api/[bot]/logs/route.ts`
- `api/health/route.ts`
- `api/accounts/production/route.ts`

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
- Stop loss: 100% of credit (FLAME/SPARK), 200% (INFERNO)
- Max 1 trade/day (FLAME/SPARK), unlimited (INFERNO)
- 10 max contracts
- VIX skip: > 32
- PDT limit: 4 day trades / 5 rolling business days (matches FINRA Rule 4210)
- Entry window: 8:30 AM - 2:00 PM CT (FLAME/SPARK), 8:30 AM - 2:30 PM CT (INFERNO)
- EOD cutoff: 2:45 PM CT (3:45 PM ET)
- Scan frequency: every 5 minutes

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
| Stop loss | Cost to close >= 200% of entry credit |
| EOD safety | Time >= 2:45 PM CT |
| Stale/expired | Position from prior day or past expiration |
| Data failure | 10 consecutive MTM failures |
| Server restart | Force-close if market closed, resume if open |

## Database Tables (Databricks Delta Lake — alpha_prime.default schema)

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
| Frontend + API routes | **Vercel** | Next.js 14, auto-deploys from main branch |
| Database | **Databricks** | Delta Lake tables in `alpha_prime.default` schema |
| Scanner | **Databricks** | `ironforge_scanner.py` runs on Databricks compute |
| FastAPI | **Databricks** | `ironforge_api.py` serves additional endpoints |

## API Routes

All routes are dynamic: `/api/[bot]/...` where bot is `flame`, `spark`, or `inferno`.

| Route | Description | DB Client |
|-------|-------------|-----------|
| `GET /api/{bot}/pdt` | PDT status, day trade count, trigger trades | databricks-sql |
| `POST /api/{bot}/pdt` | Toggle PDT enforcement, reset counter | databricks-sql |
| `GET /api/{bot}/pdt/audit` | PDT audit log (last 10 events) | databricks-sql |
| `GET /api/{bot}/status` | Account balance, P&L, open positions, heartbeat | db.ts (needs migration) |
| `GET /api/{bot}/positions` | Open positions with live data | db.ts (needs migration) |
| `GET /api/{bot}/position-monitor` | Live MTM, P&L %, profit target/stop loss proximity | db.ts (needs migration) |
| `GET /api/{bot}/equity-curve` | Historical equity curve from closed trades | db.ts (needs migration) |
| `GET /api/{bot}/equity-curve/intraday` | Today's equity snapshots (5-min intervals) | db.ts (needs migration) |
| `GET /api/{bot}/trades` | Closed trade history | db.ts (needs migration) |
| `GET /api/{bot}/performance` | Win rate, total P&L, avg win/loss, best/worst trade | db.ts (needs migration) |
| `GET /api/{bot}/logs` | Activity logs | db.ts (needs migration) |

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
5. **Databricks Delta Lake** — all persistence via Databricks SQL warehouse. Next.js API routes use `@/lib/databricks-sql.ts` client
6. **Oracle fields stored but not yet wired** — position table has oracle_confidence, oracle_win_probability, etc. but signal generator doesn't call Oracle yet

## Running Locally

```bash
# Frontend
cd ironforge/webapp
npm install

# Set Databricks credentials in .env.local:
# DATABRICKS_SERVER_HOSTNAME=...
# DATABRICKS_HTTP_PATH=...
# DATABRICKS_TOKEN=...
# TRADIER_API_KEY=...

npm run dev
# → http://localhost:3000
```

## Relationship to AlphaGEX

IronForge lives inside the AlphaGEX monorepo at `ironforge/` but is **completely independent**. It shares no code with the main AlphaGEX backend/frontend. It was designed as a lightweight, portable system that can run without the complexity of the full AlphaGEX infrastructure.

The `ironforge/databricks/` directory contains the Databricks-native scanner and API. The `ironforge/webapp/` directory contains the Next.js dashboard deployed on Vercel.
