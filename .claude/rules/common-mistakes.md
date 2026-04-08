# Common Mistakes to Avoid

These are real, recurring bugs from our codebase history. Every single item below caused a production issue at least once. AI assistants MUST review this section before making changes.

## 1. Equity Curve / Snapshot Bugs (11 fixes — Most Recurring)
- **Never use per-trade P&L for equity curves** — always use CUMULATIVE running sum of realized_pnl
- **Every bot MUST save equity snapshots every cycle** — if snapshots aren't saved, intraday equity charts are blank
- **Equity chart endpoints must query the DATABASE directly** — never require the Trader class to be initialized
- **Always add a "live snapshot fallback"** — if no snapshots exist yet today, calculate one from open positions
- **Intraday chart must draw a LINE from open to now** — a single dot is useless; always have at least 2 data points
- **Filter equity curves by instrument** when the bot trades multiple instruments (VALOR lesson)
- **Never return an empty chart without explanation** — show "No closed trades yet" or similar
- **Historical equity must query ALL closed trades** — no date filter on SQL; filter the output only

## 2. Position Closing / Stranded Positions (10 fixes)
- **Always implement EOD position closing** — positions left open overnight cause accounting nightmares
- **EOD closers MUST have fallback logic** — 4-leg → 2x 2-leg → 4 individual legs (cascade)
- **Handle "quotes unavailable" in close logic** — use last known price or market order
- **Detect stale/overnight holdover positions** — add catch-up logic
- **Close ALL positions before market close on Fridays** — never hold 0DTE/1DTE over the weekend
- **Implement orphan detection** — reconcile broker vs database positions regularly
- **Add a close-only mode** — bot should be able to only close without opening new positions
- **Track stranded positions** — need SQL script or API to force-close stuck positions

## 3. Trader Initialization Failures (6 fixes)
- **Never let data/read endpoints depend on Trader class initialization** — if Trader fails, ALL endpoints return 500s
- **Decouple data endpoints from trading logic** — use Database class directly for reads
- **If Trader init fails, the scheduler job must still register** — use lazy re-initialization
- **Add heartbeat logging** — detect silently dead bots
- **Never fatal re-raise in `_ensure_tables()`** — log and continue
- **Add emergency checks** — detect if bot has been down for hours

## 4. TypeScript / Frontend Build Failures (7 fixes)
- **Never spread a `Set` in TypeScript** — use `Array.from()` or plain arrays
- **Always handle `null`/`undefined`** — add null guards before accessing nested properties
- **Type `catch` errors as `unknown`, not `Error`** — use type narrowing
- **Copy static assets in standalone Next.js builds** — CSS/images will be missing otherwise
- **Enable `output: 'standalone'`** in `next.config.js` for Render deployments
- **Always add missing helper functions** — one missing helper = build fails
- **Run `npm run build` before pushing frontend changes**

## 5. Timezone Bugs (5 fixes)
- **ALL timestamps must be Central Time (America/Chicago)** — never display UTC
- **Use `::timestamptz AT TIME ZONE 'America/Chicago'`** in SQL queries
- **Chart X-axes must format in CT**
- **Tooltip times must be formatted in CT**
- **Session windows must be consistent across ALL files**

## 6. NULL Database Values Crashing Everything (6 fixes)
- **Always handle NULL `realized_pnl`** — use `COALESCE` in SQL
- **Backfill NULL columns after schema changes**
- **Frontend must null-guard ALL API response fields**
- **Never let a single failing API call crash the whole page**
- **Bot reports must handle 0-trade days**
- **Shared components (DriftStatusCard, OracleWidget) MUST have null guards**

## 7. API Key / Secret Management (5 fixes)
- **Never hardcode API keys** — use environment variables exclusively
- **Add `.env.local` to `.gitignore` immediately**
- **Separate sandbox URLs from production URLs**
- **Verify API keys are actually wired up** — bots can silently use fallback/mock data
- **Add `node_modules` and lock files to `.gitignore` early**

## 8. Broker Order Execution (Iron Condors) (7 fixes)
- **Always implement cascade fallback**: 4-leg → 2x 2-leg → 4 individual legs
- **Use market orders for sandbox** — limit orders rarely fill
- **MTM must use real quotes** — verify parameter names match API exactly
- **Use batch quote API** — `get_quotes([list])` not individual calls
- **OCC symbol root matters** — `SPX` for monthly, `SPXW` for weeklies
- **Round strikes to valid intervals** — SPX uses $5 intervals
- **Box spread pricing: verify bid/ask leg direction**

## 9. Frontend Performance (7 fixes)
- **Never fire 50+ API calls on page load** — use batch endpoints
- **Lazy-load heavy pages** — `dynamic(() => import(...), { ssr: false })`
- **Lazy-load the chatbot widget**
- **Gate API calls behind active tab** — only fetch for visible tab
- **Increase DB connection pool** — use `max=40, min=5`
- **Track bundle size** — pages over 200KB need code splitting
- **Never load ALL bot data on a dashboard** — only load active bots

## 10. Database Table & Migration Issues (7 fixes)
- **Auto-create tables on first use** — fresh deploy with no migrations = 500s
- **Use savepoints in migrations**
- **Never use `DEFAULT` values in Databricks** — only PostgreSQL supports them
- **Migration order matters** — create referenced tables first
- **Verify table names in BOT_REGISTRY match actual tables**
- **Remove legacy columns before INSERT**
- **Run `SELECT 1 FROM table LIMIT 1` health check** after creation

## 11. Hardcoded Values That Break (5 fixes)
- **Never hardcode `starting_capital`** — read from config table
- **Never hardcode position limits** — read from config
- **Never hardcode box spread notional**
- **Never hardcode paper account balances**
- **PDT rules differ between live and sandbox**

## 12. Stale Data / Caching (5 fixes)
- **Database config can override code config** — DB wins silently
- **Add diagnostic logging at every gate/filter**
- **Kill switches can get stuck** — add auto-resume and stale detection
- **Tradier cache blocks TradingVolatility data**
- **Freeze after-hours data** — stop updating after market close

## 13. Trading Gates That Block Everything (8 fixes — Second Most Recurring)
- **Overly strict gates silently kill all trading**
- **RTH-only gates block extended-hours bots** (VALOR)
- **Negative gamma regime restriction was too strict** — Oracle should decide
- **Negative confidence scores mean the gate math is wrong**
- **Cold start floors needed** — new bots with no history fail confidence checks
- **Test overnight signal generation separately**
- **Quote re-fetch gates can hard-block trading** — use last known quote
- **When removing gates, remove ALL related code**

## 14. Market Hours & Session Handling (8 fixes)
- **Pre-market and after-hours candles must be included**
- **After market close, load next trading day's data**
- **Session fallback must walk past holidays**
- **When market is closed, show last session data**
- **Friday expirations need special handling** — trade 7 DTE, not today's 0DTE
- **Overnight persistence for WebSocket data**
- **Data source switching at market open** — TradingVolatility → Tradier
- **Different session windows for different strategies** — VALOR: 5PM-3PM; ARES: 8:30AM-3PM

## 15. Wrong Method Names & Parameter Mismatches (5 fixes)
- **Tradier API method names change** — always verify against actual client
- **MTM parameter names must match API exactly** — wrong names silently ignored
- **Database adapter methods get deprecated** — dead methods crash silently
- **Prophet vs Tradier method names differ**
- **Field names in database vs code diverge**

## 16. Chart & Visualization Iterations (10 fixes)
- **Define bar chart direction FIRST before coding**
- **Y-axis range must accommodate all data**
- **Sort strikes by proximity to current price**
- **Set z-index for reference lines**
- **GEX zone bands must update with price**
- **Tooltips must show formatted values**
- **Add countdown timers to candles**
- **Chart backgrounds must be solid** — transparent breaks dark themes
- **Test with NO data, ONE data point, and FULL data**
- **Clean up ALL old code when migrating chart libraries**

## 17. Capital Architecture & Position Sizing (6 fixes)
- **Box spread is the sole capital source for JUBILEE**
- **Box spread opens ONCE, IC trader trades DAILY**
- **Paper box spreads should auto-extend, not roll**
- **Position sizing must be balance-aware** — read actual account balance
- **Kelly criterion sizing requires real data**
- **Capital deployment tables need schema alignment**

## 18. Bot Registration & Wiring (4 fixes)
- **New bots must be registered in bot branding**
- **New bots must be added to unified metrics**
- **New bots must be added to the scheduler**
- **New bots must have ALL standard endpoints**

## 19. Destructive Auto-Resets (CRITICAL)
- **NEVER auto-reset equity or position data** — RECONCILE, don't wipe
- **VALOR lost all position history from an auto-reset** — unrecoverable
- **Always prefer reconciliation over reset**

## 20. Deployment & Infrastructure (6 fixes)
- **Next.js standalone mode is required for Render**
- **CSS/static assets must be copied in standalone builds**
- **Verification scripts must use external Render URLs**
- **CI must pass before merge**
- **Always run post-deploy verification**
- **Databricks and Render have different SQL dialects**

## 21. WebSocket & Real-Time Streaming (6 fixes)
- **WebSocket handlers need extended hours support**
- **Persist streaming data to DB**
- **Fallback to last session after hours**
- **Don't replace working chart implementations**
- **Test streaming with market open, closed, and pre-market**
- **Audit systematically** — one audit found 7 separate failure modes

## 22. Duplicate Work Across Branches
- **Check if a feature already exists on another branch**
- **Clean up dead code when migrating**
- **Resolve merge conflicts carefully**
- **Don't split frontend+backend across separate PRs**

## 23. Multi-Instrument / Multi-Account Gotchas (5 fixes)
- **Portfolio stats must filter by selected instrument**
- **Instrument count must be derived dynamically**
- **Pagination is required for account balance API**
- **Restrict trade mirroring per-bot**
- **Per-instrument GEX data** — new instruments need GEX support

## 24. Report Generation (3 fixes)
- **Reports must generate even on 0-trade days**
- **Surface trade fetch errors in reports**
- **Add report diagnostics endpoint**

## 25. Backtest vs Production Alignment (4 fixes)
- **Backtest defaults must match production config**
- **Use correct database URL** — ORAT_DATABASE_URL for backtest, DATABASE_URL for production
- **Verify code against production before running**
- **Add GO/NO-GO gates** — explicit pass/fail criteria

## 26. Long-Running Script Output Lost
- **ALWAYS pipe through `| tee /tmp/output.txt`** — Render's web shell has zero scrollback
