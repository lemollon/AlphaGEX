# CLAUDE.md - IronForge

## What Is IronForge

IronForge is an independently deployed trading application inside the AlphaGEX
monorepo. `ironforge-customer` builds `ironforge/webapp`; Next.js serves the
customer/operator surfaces and runs the one-minute scanner. Internal trading
state uses PostgreSQL through `lib/db.ts`; app-customer execution uses its own
customer database and SnapTrade mirror path.

**Spark and Flame current state: September 28, 2026.** Both run 0DTE EBB SPY put
credit spreads, with different clocks, offsets and widths. They are not the
retired 1DTE/2DTE iron-condor products, and they are not universally paper-only.
Read [the current strategy reference](SPARK_FLAME_CURRENT_STATE_2026-09-28.md)
for sizing, assignment guards, optional FLINT/XSP features, and switch defaults.
INFERNO and other bot descriptions are outside this Spark/Flame update.

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
    │           ├── pdt/route.ts         # PostgreSQL — PDT status + toggle/reset
    │           └── pdt/audit/route.ts   # PostgreSQL — PDT audit log
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

## Spark and Flame parameters (September 28, 2026)

| Parameter | Spark | Flame |
|---|---|---|
| Main strategy | 0DTE EBB put credit spread | 0DTE EBB put credit spread |
| Entry default (CT) | 10:05–10:20 AM | 1:05–1:10 PM |
| Short put | `Math.round(SPY - 2)` | `Math.round(SPY - 1)` |
| Wing width | $5 | $2 |
| Minimum credit code floor | $0.10/share | $0.10/share |
| VIX-decay ratio ceiling | 0.90 | 0.80 |
| Main trades/day default | 1 | 1 |
| Intraday PT default / conventional stop | PT off / stop not consulted | PT off / stop not consulted |
| Internal paper seed | $5,000 | $2,000 |

The VIX ratio uses the prior session close divided by the maximum of the
20 earlier sessions. Missing history blocks entry. Config overrides can affect
entry end, credit, PT, and trade count; scope reads to `0DTE` and account type.
Strike placement and width come from `botStructure`, not SD/delta settings.

### Sizing and customer execution

Customer enrollment defaults to 20% deployment; the saved customer percentage
and fresh broker buying power determine base contracts. Optional customer
floor/calm/FLINT switches are independently default-off. ONE_STRATEGY is a
separate default-off switch routing internal production/sandbox sizing through
the same pure package (N=3, K=0.10, variant G, $50 buffer, calm ratio ≤0.70).
Customer mirrors do not use ONE_STRATEGY, but still use their own switches.
This is not Kelly sizing and `max_contracts=1` in a config display is not a
universal live/customer ceiling.

### Exits and reconciliation

EBB's generic 2:45 PM cutoff is deferred to expiry handling. The assignment
guard runs during the final three minutes before the actual close (including
early-close days), and attempts to buy back at-risk SPY shorts. Source buffer
fallback is $0.50; an environment override can differ. XSP swap legs, when
enabled, are separately cash-settled and guard-exempt. Customer broker fills
and settlement must be reconciled separately from internal paper accounting.

See [the complete current reference](SPARK_FLAME_CURRENT_STATE_2026-09-28.md).
Python `trader.py` cycles and the former generic PT/SL table are reference-only,
not operating rules for Spark or Flame.

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
| `POST /api/{bot}/force-trade` | Force entry through the applicable bot strategy |
| `POST /api/{bot}/force-close` | Force close position |
| `GET /api/{bot}/logs` | Activity logs |
| `GET /api/{bot}/fix-collateral` | Diagnose stuck collateral (read-only) |
| `POST /api/{bot}/fix-collateral` | Fix stuck collateral (close stale positions + reconcile) |
| `GET /api/{bot}/diagnose-trade` | Diagnose why bot isn't trading |
| `GET /api/{bot}/diagnose-pnl` | Diagnose P&L discrepancies |
| `POST /api/{bot}/eod-close` | Force close all positions (EOD safety) |
| `GET /api/{bot}/signals` | Recent signals (scan activity) |
| `GET /api/health` | Runtime database/market-data health check |

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
2. **Executable source governs** — Spark/Flame use `scanner.ts` with distinct clocks and structures; the Python BotConfig factories are historical references.
3. **Separate execution scopes** — internal paper, Tradier sandbox/production, and activated customer brokerage execution have distinct gates and ledgers. Verify the applicable arming switches; do not assume paper-only.
4. **Execution evidence** — bid/ask paper accounting does not prove actual multileg fills; reconcile broker orders and balances independently.
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

## HARD RULE: Scope Discipline

The user cares more about shipping the requested change cleanly than about
catching every adjacent bug. Stay inside the approved scope:

1. **Fix only what was asked.** If an audit or grep surfaces extra bugs that
   are not in the approved plan, report them at the end of the task and ask
   before touching them. Do not silently expand scope with "while I'm in
   here" cleanups — every extra file in a diff is more review surface and
   more regression risk on a real-money system.
2. **Don't run or fix tests outside the files you changed.** `npm run build`
   is the default verification. Running the full Jest / Vitest suite drags in
   pre-existing failures that have nothing to do with the current change,
   wastes reviewer attention, and tempts scope creep. Only run the test files
   you touched or the ones that directly assert against code you changed.
3. **Don't refactor adjacent code.** Renames, formatting, doc rewrites, and
   dead-code removal belong in their own PR unless the user explicitly asked
   for them. A bug fix should be a minimal diff that only contains the fix.
4. **When auditing, report — don't fix.** Audit prompts should return a
   ranked bug list with file:line citations. Applying fixes from the audit
   without a follow-up user approval pushes scope beyond what was authorized.
5. **If a "nice-to-have" keeps cropping up, name it and defer it.** List it
   under "Still outstanding" in the task summary and let the user decide
   whether to spin a follow-up. Do not ship it alongside the current work.
6. **Operational vs code fixes.** Data-state problems (stranded positions,
   orphan DB rows, config drift) are usually operational — prefer a single
   diagnostic/fix endpoint per the pattern below over ad-hoc edits. Keep
   each endpoint focused on one cleanup; don't fold multiple fixes into one
   route just because they're "related."

## HARD RULE: All Backend Fixes Must Live in the Webapp

**ALL diagnostic tools, fix scripts, and backend operations MUST be implemented as API routes in `ironforge/webapp/src/app/api/`.** Do NOT create:
- Standalone Python scripts in `ironforge/scripts/`
- Databricks notebooks in `ironforge/databricks/`
- Any backend code outside the webapp

**Why:** The Render-hosted webapp is the deployed IronForge backend. Put supported operational endpoints in the webapp and use the authenticated operator surface. The retired Databricks runtime is not an operational path.

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
4. **Scope mismatch**: wrong PostgreSQL instance, account type, person, or retired DTE tag — reads a different ledger from the current 0DTE strategy.

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

### Spark/Flame broker positions and expiry

Reconcile pending orders and filled positions on the correct brokerage account.
A database close or paper settlement does not prove that a broker position
closed. Inspect the existing close order before attempting another, and compare
contracts, cash, assignment and buying power after settlement. Do not stack
orders or treat a collateral repair as evidence of a broker fill.

EBB defaults hold toward expiry; it does not close every position at 2:45 PM.
The final-three-minute assignment guard follows the actual close, including
early-close days. An expired contract cannot be closed as a new option trade
the next morning; reconcile settlement/assignment instead. See the current
reference for SPY guard handling and the XSP exemption.

## Operations Runbook

### Daily Spark/Flame health check

1. Verify deployed commit and surface. Use authenticated operator routes for
   `/api/{bot}/status` and `/api/{bot}/config`; customer-only surfaces can 404 them.
2. Select the correct person, account type and current `0DTE` ledger. Old
   `1DTE`/`2DTE` records are retained history, not the active configuration.
3. Check heartbeat, entry-window decisions, VIX history/gate, feature switches,
   and order errors. The scanner runs every minute.
4. Reconcile internal account basis, P&L and open-position collateral within
   the same scope. Paper seeds are Spark $5,000 / Flame $2,000.
5. For customers, inspect saved authorization and fresh broker balances plus
   actual order/fill records in the customer execution path. A master position
   alone does not establish a customer fill.

### Dashboard or collateral discrepancy

Start with read-only status and diagnostic routes on the operator service.
Compare with PostgreSQL using `DATABASE_URL`, `dte_mode='0DTE'`, account type
and person filters. Customer records use `CUSTOMERS_DATABASE_URL` separately.
If a repair is needed, inspect the implementation and its mutation scope before
calling its POST endpoint; reconcile broker state independently afterward.

### Deployment verification

Create a reviewed PR to `main`; Render services following main can auto-deploy.
Verify the actual live commit on each affected service and the correct surface.
A source default or successful build does not prove an environment feature is
armed, a customer is eligible, or an order filled. Historical Databricks and
Vercel instructions do not apply to this runtime.
