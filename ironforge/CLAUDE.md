# CLAUDE.md - IronForge

## What Is IronForge

IronForge is a **standalone SPY Iron Condor paper trading system** that runs independently from the main AlphaGEX platform. It was originally built for Databricks, then migrated to **Render + PostgreSQL** for simpler deployment and lower cost.

It runs two bots — **FLAME** (2DTE) and **SPARK** (1DTE) — that trade SPY Iron Condors using real Tradier market data with paper execution.

## Architecture

```
ironforge/
├── config.py                  # PostgreSQL + Tradier config (reads DATABASE_URL, TRADIER_API_KEY)
├── setup_tables.py            # DDL for all PostgreSQL tables
├── requirements.txt           # psycopg2-binary, requests
├── render.yaml                # Render deployment: 1 web service + 2 workers + 1 DB
│
├── trading/                   # Python trading engine (shared by both bots)
│   ├── models.py              # BotConfig, IronCondorPosition, IronCondorSignal, PaperAccount
│   ├── trader.py              # Trader orchestrator (run_cycle, position management, exit logic)
│   ├── signals.py             # SignalGenerator (Tradier quotes, SD-based strikes, symmetric wings)
│   ├── executor.py            # PaperExecutor (open/close paper positions, collateral math)
│   ├── db.py                  # TradingDatabase (all SQL: positions, PDT, signals, equity, logs)
│   ├── db_adapter.py          # psycopg2 connection helper
│   └── tradier_client.py      # Standalone Tradier API client (quotes, chains, VIX)
│
├── jobs/                      # Entry points for Render workers
│   ├── run_flame.py           # FLAME (2DTE) — runs every 5 min
│   └── run_spark.py           # SPARK (1DTE) — runs every 5 min
│
└── webapp/                    # Next.js 14 dashboard (App Router)
    ├── package.json           # next 14.2, pg, react 18, recharts, swr, tailwind
    ├── src/
    │   ├── lib/
    │   │   ├── db.ts          # PostgreSQL pool (node-pg), botTable(), query(), validateBot()
    │   │   ├── fetcher.ts     # SWR fetcher
    │   │   └── tradier.ts     # Server-side Tradier client for position monitor
    │   ├── components/
    │   │   ├── BotDashboard.tsx    # Main bot dashboard (tabs: Equity, Performance, Positions, Trades, Logs)
    │   │   ├── StatusCard.tsx      # Account status summary
    │   │   ├── EquityChart.tsx     # Recharts equity curve (intraday + historical)
    │   │   ├── PerformanceCard.tsx # Win rate, P&L stats
    │   │   ├── PositionTable.tsx   # Open positions with live MTM
    │   │   ├── TradeHistory.tsx    # Closed trades table
    │   │   ├── LogsTable.tsx       # Activity logs
    │   │   └── Nav.tsx             # Navigation bar
    │   └── app/
    │       ├── page.tsx            # Home: bot cards, strategy config, signal flow, FLAME vs SPARK
    │       ├── flame/page.tsx      # FLAME dashboard (BotDashboard bot="flame")
    │       ├── spark/page.tsx      # SPARK dashboard (BotDashboard bot="spark")
    │       ├── compare/page.tsx    # Side-by-side FLAME vs SPARK comparison
    │       ├── layout.tsx          # Root layout with Nav
    │       ├── globals.css         # Dark theme (forge-bg, forge-card, fire-divider)
    │       └── api/[bot]/          # Dynamic API routes (bot = flame | spark)
    │           ├── status/route.ts
    │           ├── positions/route.ts
    │           ├── position-monitor/route.ts
    │           ├── equity-curve/route.ts
    │           ├── equity-curve/intraday/route.ts
    │           ├── trades/route.ts
    │           ├── performance/route.ts
    │           └── logs/route.ts
    └── .env.local.example
```

## Bots

| Bot | DTE | Description |
|-----|-----|-------------|
| **FLAME** | 2DTE | Longer-duration Iron Condors. More premium, more time to work. |
| **SPARK** | 1DTE | Shorter-duration Iron Condors. Faster theta decay, quicker resolution. |

Both share identical config except `min_dte`. Key parameters:
- Ticker: SPY
- Starting capital: $5,000 (paper)
- Spread width: $5
- SD multiplier: 1.2x
- Profit target: 30% of credit
- Stop loss: 100% of credit
- Max 1 trade/day, 10 max contracts
- VIX skip: > 32
- PDT limit: 3 day trades / 5 rolling days
- Entry window: 8:30 AM - 2:00 PM CT
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

## Database Tables (per bot, prefix = flame_ or spark_)

- `{bot}_positions` — All positions (open, closed, expired). Key columns: strikes, credits, oracle data, wings_adjusted, status, realized_pnl
- `{bot}_signals` — Every signal generated (executed or skipped)
- `{bot}_paper_account` — Paper account state (balance, cumulative P&L, collateral, buying power, HWM, drawdown)
- `{bot}_equity_snapshots` — Periodic snapshots (every 5-min cycle) for intraday chart
- `{bot}_daily_perf` — Daily performance summary
- `{bot}_logs` — Activity log (TRADE_OPEN, TRADE_CLOSE, SKIP, ERROR, RECOVERY, CONFIG)
- `{bot}_pdt_log` — PDT day trade tracking
- `bot_heartbeats` — Shared heartbeat table for both bots

## Deployment (Render)

Defined in `ironforge/render.yaml`:

| Service | Type | Runtime | What It Does |
|---------|------|---------|--------------|
| `ironforge-dashboard` | web | Node.js | Next.js webapp (pages + API routes) |
| `ironforge-flame` | worker | Python | FLAME bot — runs `main()` every 5 min in a loop |
| `ironforge-spark` | worker | Python | SPARK bot — runs `main()` every 5 min in a loop |
| `ironforge-db` | database | PostgreSQL | Free-tier Render PostgreSQL |

**No Vercel needed** — the Next.js app runs on Render as a web service.

Env vars: `DATABASE_URL` (from Render DB), `TRADIER_API_KEY`, `TRADIER_BASE_URL` (sandbox default).

## API Routes

All routes are dynamic: `/api/[bot]/...` where bot is `flame` or `spark`.

| Route | Description |
|-------|-------------|
| `GET /api/{bot}/status` | Account balance, P&L, open positions, heartbeat, scan count |
| `GET /api/{bot}/positions` | Open positions with live data |
| `GET /api/{bot}/position-monitor` | Live MTM, P&L %, profit target/stop loss proximity |
| `GET /api/{bot}/equity-curve` | Historical equity curve from closed trades |
| `GET /api/{bot}/equity-curve/intraday` | Today's equity snapshots (5-min intervals) |
| `GET /api/{bot}/trades` | Closed trade history |
| `GET /api/{bot}/performance` | Win rate, total P&L, avg win/loss, best/worst trade |
| `GET /api/{bot}/logs` | Activity logs |

## Frontend Pages

| Route | Description |
|-------|-------------|
| `/` | Home — bot cards, shared strategy config, signal flow diagram, FLAME vs SPARK comparison |
| `/flame` | FLAME dashboard (StatusCard + tabbed: Equity Curve, Performance, Positions, Trade History, Logs) |
| `/spark` | SPARK dashboard (same layout, blue accent) |
| `/compare` | Side-by-side comparison of both bots |

## Key Design Decisions

1. **Fully standalone** — no imports from the main AlphaGEX codebase. Has its own Tradier client, config, DB layer
2. **Unified code for both bots** — Trader, SignalGenerator, PaperExecutor, TradingDatabase all parameterized by BotConfig (only `min_dte` and `bot_name` differ)
3. **Real market data, paper execution** — Tradier production/sandbox API for quotes and option chains, but no actual orders placed
4. **Conservative fills** — sells at bid, buys at ask (worst-case paper fills)
5. **PostgreSQL on Render** — migrated from Databricks Delta Lake. Uses psycopg2 (Python) and node-pg (Next.js API routes)
6. **Oracle fields stored but not yet wired** — position table has oracle_confidence, oracle_win_probability, etc. but signal generator doesn't call Oracle yet

## Running Locally

```bash
# Backend (one bot)
cd ironforge
pip install -r requirements.txt
export DATABASE_URL=postgresql://...
export TRADIER_API_KEY=...
python jobs/run_flame.py

# Frontend
cd ironforge/webapp
npm install
npm run dev
# → http://localhost:3000
```

## Relationship to AlphaGEX

IronForge lives inside the AlphaGEX monorepo at `ironforge/` but is **completely independent**. It shares no code with the main AlphaGEX backend/frontend. It was designed as a lightweight, portable system that can run on free-tier Render without the complexity of the full AlphaGEX infrastructure.

There is also a `databricks/` directory containing the original Databricks version of IronForge (Delta Lake, Databricks SQL connector, Databricks REST API for the webapp). The `ironforge/` directory is the Render/PostgreSQL migration of that same system.
