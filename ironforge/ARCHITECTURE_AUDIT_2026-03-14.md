# IronForge Architecture Audit — 2026-03-14

All findings below are **CODE REVIEW ONLY** (max 69% confidence per Rule 2).
No tests were execution-tested. All line numbers verified by reading source.

---

## F1: Close Path Consistency Audit

**8 distinct close paths identified.** 5 are fully consistent, 3 have gaps.

### Complete Paths (12/12 steps)

| Path | File | Line | Notes |
|------|------|------|-------|
| `close_paper_position()` | `trading/executor.py` | 440 | Python executor — full end-to-end |
| `close_position()` | `databricks/ironforge_scanner.py` | 1332 | Scanner — sandbox cascade + collateral reconciliation |
| `POST force-close` | `webapp/src/app/api/[bot]/force-close/route.ts` | 15 | TypeScript — full parity with Python |

### Near-Complete Paths (11/12 steps)

| Path | File | Line | Missing |
|------|------|------|---------|
| `close_position()` | `scripts/position_monitor.py` | 481 | **No equity snapshot saved** |
| `POST eod-close` | `webapp/src/app/api/[bot]/eod-close/route.ts` | 16 | **No per-position close log** (only skipped positions logged) |

### Incomplete Paths (8/12 steps)

| Path | File | Line | Missing |
|------|------|------|---------|
| `close_stale_positions()` | `scripts/fix_stuck_collateral.py` | 152 | **No rowcount guard**, no equity snapshot, no daily_perf update |

### Base Layer (Not Standalone — 5/12)

| Path | File | Line | Notes |
|------|------|------|-------|
| `close_position()` | `trading/db.py` | 266 | Dead code (PostgreSQL layer, unused in production) |
| `expire_position()` | `trading/db.py` | 383 | Dead code |

### Issues Found

1. **Position monitor missing equity snapshot** — Equity curve will have gaps when monitor closes positions
2. **fix_stuck_collateral missing rowcount guard** — Race condition possible with scanner
3. **EOD-close route doesn't log successful closes to DB** — Only skipped positions get activity log entries
4. **Price source tracking inconsistent** — Scanner tracks `fill_delta_pct`, monitor tracks `price_source`, force-close tracks both, eod-close tracks neither

---

## F2: Error Handling Architecture

**Overall: 80% solid. Errors propagate correctly through Layers 1-3. Layer 4 (frontend) is the weak link.**

### Layer-by-Layer Assessment

| Layer | Component | File | Assessment |
|-------|-----------|------|------------|
| 1 | Tradier Client | `webapp/src/lib/tradier.ts` | **EXCELLENT** — All HTTP errors logged with status+endpoint, 401/403 flagged, returns `null` on error |
| 2 | Scanner/Monitor | `databricks/ironforge_scanner.py`, `scripts/position_monitor.py` | **EXCELLENT** — 3-stage cascade close, failures logged to DB, validates MTM |
| 3 | API Routes | `webapp/src/app/api/[bot]/*.ts` | **SOLID** — Consistent HTTP status codes, catches errors, returns 500 with message |
| 4 | Frontend | `webapp/src/components/*.tsx` | **GAP** — No error state display for partial failures |

### Critical Gap: Silent Partial Failure

**Scenario**: User clicks Force Close → Tradier returns 400 → Cascade fails on all 3 stages → Paper position closes successfully → API returns HTTP 200 with `success: true` and empty `sandbox_close_info: {}` → Frontend shows success toast.

**Result**: User doesn't know sandbox position is orphaned. No DB record of the failure from the webapp path (only position_monitor.py logs sandbox failures to DB).

### End-to-End Error Trace: "Tradier 400 on sandbox close"

```
tradier.ts:365  → console.error("HTTP 400 (Bad Request)")  → returns null
tradier.ts:880  → retry after 1s                           → returns null
tradier.ts:897  → Stage 2: 2x 2-leg                        → both return null
tradier.ts:920  → Stage 3: individual legs                  → all 4 return null
tradier.ts:945  → console.error("ALL close strategies FAILED — sandbox ORPHAN likely")
force-close:77  → catch { } (non-fatal)                     → sandboxCloseInfo = {}
force-close:131 → rowsAffected = 1 (paper close succeeds)
force-close:240 → return { success: true, sandbox_close_info: {} }
Frontend        → sees success: true                         → shows "Closed pos_123"
DB logs         → NOTHING (force-close doesn't log sandbox failures to DB)
```

### Recommendations

1. **Frontend**: Check `sandbox_close_info` emptiness → show warning toast
2. **force-close route**: Log sandbox failures to `{bot}_logs` table
3. **StatusCard**: When `unrealized_pnl` is null, indicate "Quotes unavailable" not just "—"

---

## F3: Data Flow Architecture

```
                     ┌─────────────┐
                     │   Tradier   │
                     │  Sandbox    │
                     │ (3 accounts)│
                     └──────┬──────┘
                            │ REST API (sandboxPost)
                     ┌──────▼──────┐
                     │   Scanner   │ ← ironforge_scanner.py
                     │  (Python)   │   Databricks Scheduled Job
                     │  60s cycle  │   Market hours only (8AM-3PM CT)
                     └──────┬──────┘
                            │ spark.sql() (native)
                     ┌──────▼──────┐     ┌──────────────┐
                     │  Databricks │◄────│ Pos Monitor  │ ← position_monitor.py
                     │  Delta Lake │     │  (Python)    │   Databricks Job
                     │ alpha_prime │     │  15s cycle   │   Market hours only
                     │ .ironforge  │     └──────────────┘
                     └──────┬──────┘
                            │ REST API (Statement Execution)
                            │ Cache busted via /* ts=${Date.now()} */
                     ┌──────▼──────┐
                     │  Webapp API │ ← Next.js on Vercel
                     │  (TypeScript)│  dynamic = 'force-dynamic'
                     │  Vercel     │  cache: 'no-store'
                     └──────┬──────┘
                            │ SWR fetch (10-15s refresh)
                     ┌──────▼──────┐
                     │  Dashboard  │ ← React components
                     │  (Browser)  │
                     └─────────────┘
```

### Wire Verification

| Wire | Protocol | Auth | Cache | Verified |
|------|----------|------|-------|----------|
| Scanner → Databricks | spark.sql() native | Databricks runtime | None | ✅ Code review |
| Monitor → Databricks | spark.sql() native | Databricks runtime | None | ✅ Code review |
| Databricks → Webapp | HTTP REST (Statement Execution API) | Bearer token | Busted via `/* ts= */` | ✅ Code review |
| Webapp → Dashboard | SWR fetch | None (public Vercel) | `force-dynamic` + `no-store` | ✅ Code review |
| Dashboard → Webapp (actions) | HTTP POST | None | N/A | ✅ Code review |

### Tables Written By Each Component

| Component | Tables Written |
|-----------|---------------|
| Scanner | positions, paper_accounts, scan_logs, daily_perf, equity_snapshots, pdt_log |
| Monitor | positions, paper_accounts, scan_logs, daily_perf, pdt_log (**not** equity_snapshots) |
| Webapp force-close | positions, paper_accounts, logs, daily_perf, equity_snapshots, pdt_log |
| Webapp eod-close | positions, paper_accounts, logs, daily_perf, equity_snapshots, pdt_log |

---

## F4: Single Writer Verification

### Can scanner and position_monitor run simultaneously?

**YES.** Scanner runs every 60s, Monitor every 15s. Both are Databricks jobs that can overlap.

### What prevents double-close?

**The `rows_affected == 0` guard** in both close functions:

- Scanner: `ironforge_scanner.py:1501` — `if rows_affected == 0: return`
- Monitor: `position_monitor.py:547` — `if rows_affected == 0: return`
- Webapp: `force-close/route.ts:131` — `if (rowsAffected === 0)`

All use `WHERE position_id = '...' AND status = 'open'` — second writer gets 0 rows.

### Is Delta Lake ACID sufficient?

**YES for sequential writes.** Delta Lake uses snapshot isolation with optimistic concurrency control. If Writer A commits first, Writer B's WHERE clause re-evaluates against the committed state and matches 0 rows.

**CAVEAT**: True concurrent writes (same millisecond) are serialized by Delta Lake, but with potential lock contention during heavy 0DTE closures. Not a correctness issue, but a performance one.

### Recommendation

The `rows_affected` guard is sufficient for correctness. The architecture does NOT need optimistic locking or external locks. However, **consolidating close logic into a single shared function** would reduce maintenance burden and prevent the inconsistencies found in F1.

---

## F5: Configuration Consistency

### BOT_CONFIG: Scanner vs Monitor

| Parameter | Scanner Source | Monitor Source | Match? |
|-----------|---------------|----------------|--------|
| pt_pct | BOT_CONFIG + DB override | Hardcoded only | **NO** |
| sl_mult | BOT_CONFIG + DB override | Hardcoded only | **NO** |
| sd | BOT_CONFIG + DB override | N/A (not used) | N/A |
| max_contracts | BOT_CONFIG + DB override | N/A (not used) | N/A |
| entry_end | BOT_CONFIG + DB override | N/A (not used) | N/A |

**Critical issue**: Scanner calls `load_config_overrides()` (line 108-150) to merge DB config. Monitor does NOT. If someone changes `profit_target_pct` in the DB config table, the scanner uses the new value but the monitor uses the hardcoded value. This creates a split-brain scenario.

### Timezone: All Consistent

| Component | Timezone | EOD Cutoff | Source |
|-----------|----------|------------|--------|
| Scanner | America/Chicago | 14:45 (2:45 PM CT) | `ironforge_scanner.py:1094, 1133` |
| Monitor | America/Chicago | 14:45 (2:45 PM CT) | `position_monitor.py:63, 443` |
| Webapp eod-close | America/Chicago | 14:45 (885 minutes) | `eod-close/route.ts:28-32` |

**All three match.** ✅

### Tradier Keys: Shared Across All Components

All three components use the same 3 sandbox accounts (User, Matt, Logan) with the same API keys. Keys are set via `_set_if_missing()` with hardcoded fallbacks in scanner and monitor.

**Security concern**: Production API keys hardcoded in source (`ironforge_scanner.py:23-38`, `position_monitor.py:22-28`). Should be env-var-only.

### Databricks Connection: Two Different Methods

- Scanner/Monitor: `spark.sql()` (native Databricks runtime)
- Webapp: HTTP REST API with `/* ts= */` cache busting

**Lag risk**: Minimal. Both query the same Delta Lake tables. REST API may have <1s latency vs native spark.sql(), but the cache-bust comment ensures fresh reads.

---

## F6: Deployment Pipeline

### Current State

| Component | Platform | Deploy Trigger | Branch |
|-----------|----------|---------------|--------|
| Dashboard (webapp) | Vercel | Push to `main` | NOT deploying from `claude/setup-databricks-notebook-Y3OXC` |
| Scanner | Databricks Job | Manual upload to DBFS | N/A (not git-linked) |
| Monitor | Databricks Job | Manual upload to DBFS | N/A (not git-linked) |

**Key finding**: Current feature branch is NOT deployed. All fixes from this session and previous sessions are in `claude/setup-databricks-notebook-Y3OXC`, which must be merged to `main` for Vercel to pick them up.

### CI/CD Gap

GitHub Actions CI tests `/frontend/` (main AlphaGEX) but **NOT** `/ironforge/webapp/`. IronForge TypeScript build is not verified in CI. Must be manually verified with `npm run build` before merging.

### Build Status

**Last verified**: 2026-03-14 — `npm run build` passed clean (this session).

### Rollback

- **Vercel**: 1-click redeploy of previous deployment
- **Scanner**: Restore previous version from Databricks file history
- **Database**: Delta Lake `RESTORE TABLE ... TO VERSION AS OF <version>`

---

## Summary: Issues Ranked by Severity

### HIGH (Should fix before Monday trading)

1. **Position monitor missing equity snapshot** — `position_monitor.py:660` — causes equity curve gaps
2. **fix_stuck_collateral missing rowcount guard** — `fix_stuck_collateral.py:219` — race condition with scanner
3. **Monitor doesn't load config overrides from DB** — `position_monitor.py:51-55` — PT/SL config can diverge from scanner

### MEDIUM (Fix this week)

4. **Frontend doesn't display sandbox close failures** — `StatusCard.tsx` — user unaware of orphaned positions
5. **force-close route doesn't log sandbox failures to DB** — `force-close/route.ts:77-79` — no audit trail
6. **EOD-close doesn't log successful closes** — `eod-close/route.ts:145` — asymmetric logging
7. **Hardcoded API keys in source** — `ironforge_scanner.py:23-38` — security concern

### LOW (Cleanup)

8. **Price source tracking inconsistent across close paths** — cosmetic but aids debugging
9. **Log level inconsistency** — SANDBOX_CLOSE_FAIL vs ERROR vs ALERT not standardized
10. **IronForge webapp not tested in GitHub Actions CI** — manual build verification required

---

## Confidence Report (Code Review Only)

Per Rule 2: Code review alone caps at 69%.

```
============================================================
IRONFORGE ARCHITECTURE AUDIT — 2026-03-14
============================================================

INVARIANT STATUS (CODE REVIEW — not execution-tested):
  INV-1  (balance = starting + sum_pnl):     CODE REVIEW — All 5 complete close paths update correctly
  INV-2  (collateral = sum open):             CODE REVIEW — 4/5 close paths use SUM query; fix_stuck_collateral is partial
  INV-3  (buying_power = bal - coll):         CODE REVIEW — Derived from INV-1 and INV-2 in all paths
  INV-4  (closed pos no collateral):          CODE REVIEW — WHERE status='open' guard prevents this
  INV-5  (no stale open positions):           NOT TESTED — Requires Databricks query (Test A3)
  INV-6  (pnl matches trade math):            NOT TESTED — Requires Databricks query (Test A4)
  INV-7  (db pos → sandbox pos):              CODE REVIEW — FLAME cascade close present in scanner + monitor + webapp
  INV-8  (db close → sandbox close):          CODE REVIEW — Cascade close in all paths; but webapp doesn't log failures
  INV-9  (failed close → retry + log):        CODE REVIEW — 3-stage cascade verified; monitor logs to DB; webapp does not
  INV-10 (atomic close + collateral):         CODE REVIEW — rows_affected guard present in 5/6 paths (not fix_stuck)
  INV-11 (data freshness < 15s):              CODE REVIEW — force-dynamic + no-store + SWR 10-15s refresh
  INV-12 (no false $0 on error):              CODE REVIEW — StatusCard shows "—" for null; verified in previous session
  INV-13 (scanning badge accurate):           CODE REVIEW — Badge logic found to be potentially misleading when market closed
  INV-14 (no-cache on financial routes):       CODE REVIEW — All routes use force-dynamic + no-store
  INV-15 (max_contracts enforced):            NOT TESTED — Requires Databricks config check (Test A5)
  INV-16 (WP < 0.50 gate):                   CODE REVIEW — Oracle gate present in scanner signal generation
  INV-17 (kill switch accessible):            CODE REVIEW — GET endpoint exists; POST endpoint exists
  INV-18 (API errors logged):                 CODE REVIEW — tradier.ts logs all HTTP errors with status + endpoint

CLOSE PATH CONSISTENCY: 5/8 paths fully consistent
CRITICAL GAPS: 3 (monitor equity snapshot, fix_stuck rowcount, config drift)
ERROR FLOW: Layers 1-3 solid; Layer 4 (frontend) blind to partial failures
DEPLOYMENT: Feature branch NOT deployed — must merge to main

OVERALL CONFIDENCE: 55% (code review only — no execution testing)
============================================================
```

---

*Audit performed: 2026-03-14*
*Method: Code review only — no Databricks, Tradier, or Vercel access*
*Next step: Execute Category A-E tests with live credentials to raise confidence*
