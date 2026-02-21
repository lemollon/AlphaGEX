# PRE-DEPLOYMENT CONFIRMATION — JUBILEE IC Root Cause Fixes

**Date**: 2026-02-21
**Branch**: `claude/jubilee-ic-root-cause-8bzxC`
**Deployer**: Claude Code (awaiting Leron's confirmation)

---

## TRADIER API SAFETY VERIFICATION

| Check | Result |
|-------|--------|
| `data/tradier_data_fetcher.py` modified? | NO |
| `unified_config.py` modified? | NO |
| `config.py` modified? | NO |
| Any executor Tradier client code modified? | NO |
| Any env var names changed? | NO |
| Any API URLs changed? | NO |
| Any credential loading logic changed? | NO |

**Tradier health check**: Run `python3 system_audit/tradier_health_check.py --save-baseline` BEFORE deploying. Run `python3 system_audit/tradier_health_check.py --compare` AFTER deploying.

---

## FILES CHANGED (9 files, +1135 lines, -12 lines)

### Production code changes (3 files):
1. **`scheduler/trader_scheduler.py`** (+293 lines)
   - Added EOD safety net (`scheduled_jubilee_ic_eod_logic`) with CronTrigger at 3:01 PM CT
   - Added close-only mode (15 min post-market grace period)
   - Added lazy re-initialization (`_jubilee_ic_try_reinit`)
   - Added emergency DB check (`_jubilee_ic_emergency_check`)
   - Added heartbeat logging to every 5-min cycle
   - Upgraded init failure logging from `warning` to `critical`

2. **`trading/jubilee/db.py`** (+3/-8 lines)
   - Removed fatal `raise` from `_ensure_tables()` — was killing trader init on transient DB errors

3. **`trading/jubilee/signals.py`** (+8/-5 lines)
   - Fixed Kelly criterion dead code — replaced nonexistent `DatabaseAdapter().execute_query()` with working `get_connection()` pattern

### Trader additions (1 file):
4. **`trading/jubilee/trader.py`** (+90 lines)
   - Added `force_close_all()` method — used by EOD safety net
   - Added `run_close_only_cycle()` method — exit checks only, no new entries

### SQL scripts (1 file — NOT auto-executed):
5. **`jubilee_tests/fix1_close_stranded_positions.sql`** (+93 lines)
   - Closes 5 stranded positions from Feb 13 that expired OTM on Feb 20
   - Must be run manually by Leron after review

### Audit/diagnostic scripts (4 files — read-only, no production impact):
6. **`system_audit/audit_all_bots.py`** — Checks all bots for fake vs real data
7. **`system_audit/check_modes.py`** — Scans LIVE vs PAPER mode flags
8. **`system_audit/check_tradier_account.py`** — Queries Tradier account state
9. **`system_audit/reconcile_positions.py`** — Compares DB vs Tradier positions

### Health check script (1 file — added this session):
10. **`system_audit/tradier_health_check.py`** — Pre/post deploy Tradier verification

---

## RISK ASSESSMENT

| Risk | Level | Mitigation |
|------|-------|------------|
| Tradier connectivity | NONE | Zero Tradier files changed |
| Existing bot behavior | LOW | Changes are additive (new methods, new jobs) |
| Database schema | NONE | No schema changes; SQL script requires manual execution |
| Other bots (ARES, TITAN, etc.) | NONE | Only JUBILEE IC code modified |
| Scheduler stability | LOW | New jobs use same patterns as existing SAMSON EOD job |
| Init failure on deploy | MITIGATED | Lazy re-init now retries every 5 min instead of dying forever |

---

## ROLLBACK PLAN

If anything goes wrong after deploy:
1. Run `python3 system_audit/tradier_health_check.py --compare` to verify Tradier still works
2. If Tradier is broken: git revert the merge commit and redeploy
3. If only JUBILEE IC is broken: the emergency check still protects open positions via DB-direct close
4. All changes are backwards-compatible — no other bot is affected

---

## DEPLOYMENT STEPS

1. Run baseline: `python3 system_audit/tradier_health_check.py --save-baseline`
2. Deploy branch `claude/jubilee-ic-root-cause-8bzxC`
3. Run verify: `python3 system_audit/tradier_health_check.py --compare`
4. Check JUBILEE IC init in logs: search for "JUBILEE_IC_INIT" and "jubilee_ic_trader"
5. Verify EOD job registered: search for "jubilee_ic_eod" in scheduler logs
6. Run Fix 1 SQL manually (only after confirming positions are still stranded)

---

## LERON CONFIRMATION

- [ ] I have reviewed the file change list above
- [ ] I confirm no Tradier API credentials, URLs, or client code were modified
- [ ] I approve deploying this branch to production
- [ ] I will run the Tradier health check before and after deployment
- [ ] I will review Fix 1 SQL before executing it against the database
