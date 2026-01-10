# AlphaGEX Live Trading Bots - Logic Verification Report

**Date:** January 10, 2026
**Auditor:** Claude Code Verification System
**Scope:** All Live Trading Bots (ARES, ATHENA, ICARUS, PEGASUS, TITAN, ATLAS)

---

## Executive Summary

A comprehensive code audit was performed on all live trading bots. **Critical issues were found in every bot** that could prevent trades from executing or closing properly. The most severe issues involve:

1. **Orphaned Positions** - Trades execute at broker but fail to save to database, becoming untracked
2. **Silent Exit Failures** - Positions don't close when price data is unavailable
3. **Disabled Safety Checks** - Win probability thresholds intentionally disabled
4. **Partial Close Limbo** - One leg closes but other leg stays open with no retry

**Risk Level: HIGH** - These bots should not be used in production without fixes.

---

## Critical Issues by Severity

### SEVERITY: CRITICAL (Must Fix Before Production)

| Bot | Issue | Impact | Location |
|-----|-------|--------|----------|
| **ALL BOTS** | Position saved to broker but DB save fails | Orphaned positions, capital trapped | `trader.py` ~line 726-728 |
| **ALL BOTS** | Exit blocked when price unavailable | Positions never close | `trader.py` ~line 650-652 |
| **ARES/PEGASUS** | Win probability threshold DISABLED | Trades any signal regardless of confidence | `signals.py` ~line 860 |
| **ARES/PEGASUS** | VIX filter DISABLED | Trades in dangerous volatility | `signals.py` ~line 497 |
| **ATHENA** | `AttributeError` on `db_persisted` field | Crashes when DB save fails | `trader.py:822` |
| **ATHENA** | Invalid order status creates position | Positions without real orders | `executor.py:371-375` |
| **ATLAS** | Buy-to-close doesn't verify execution | DB says closed but broker open | `spx_wheel_system.py:1856-1889` |
| **ATLAS** | Market hours timezone bug | Trades blocked 8:30-9 AM CT, allowed 3-4 PM CT | `spx_wheel_system.py:1123-1130` |

### SEVERITY: HIGH (Fix Soon)

| Bot | Issue | Impact | Location |
|-----|-------|--------|----------|
| **ALL BOTS** | Partial closes never retried | One leg stays open indefinitely | `trader.py` ~line 643 |
| **ALL BOTS** | DB close failure not propagated | Inconsistent state between broker/DB | `trader.py` ~line 453 |
| **ALL BOTS** | No position reconciliation on restart | Orphaned orders can't be recovered | startup logic |
| **ICARUS** | No retry for failed close orders | Failed closes abandoned | `trader.py:366-378` |
| **ICARUS** | `db_persisted` flag set but never checked | Can't detect orphaned positions | `trader.py:742` |
| **PEGASUS/TITAN** | Rollback failure leaves orphaned orders | Manual intervention required | `executor.py:373-416` |
| **ATLAS** | Roll failure partial execution | Position lost in limbo | `spx_wheel_system.py:1827-1835` |

### SEVERITY: MEDIUM

| Bot | Issue | Impact | Location |
|-----|-------|--------|----------|
| **ALL BOTS** | Bare except clauses | Errors silently swallowed | `db.py` multiple locations |
| **ALL BOTS** | Race condition in position count | Multiple positions could open | `trader.py` ~line 249 |
| **ALL BOTS** | Silent ML feedback failures | Models don't improve | `trader.py` multiple |
| **ATHENA** | Falsy value check skips zero prices | Incomplete P&L reports | `trader.py:1012, 1058` |
| **ATLAS** | Fallback price uses hardcoded SPX=5800 | Wrong entry prices | `spx_wheel_system.py:1417` |
| **ATLAS** | Missing `position_size_pct` attribute | Decision logging crashes | `spx_wheel_system.py:913` |

---

## Detailed Findings by Bot

### ARES (SPY Iron Condor)

**Entry Logic:**
- Win probability threshold **DISABLED** at `signals.py:960-962`
- VIX filter **DISABLED** at `signals.py:497-498`
- Signal defaults to 50% confidence if ML and Oracle both fail

**Exit Logic:**
- Position valuation failure returns `(False, "")` - position won't close
- Partial close marked in DB but never retried
- No fallback close mechanism when pricing unavailable

**Order Execution:**
- Rollback failure logs orphaned order but doesn't verify DB write
- Paper trading uses fake order IDs that could confuse live mode

**Critical Code Path:**
```python
# signals.py:960 - DISABLED!
logger.info(f"[ARES] Win probability threshold check DISABLED - proceeding with trade")
```

---

### ATHENA (Directional Spreads)

**Entry Logic:**
- `AttributeError` crash when DB save fails (references non-existent `db_persisted` field)
- Invalid order status (`expired`, `partial`, `unknown`) still creates position
- Transient API errors not retried

**Exit Logic:**
- Exit blocked if `current_value is None` - no fallback
- Zero-value positions invisible in P&L reports (falsy check bug)

**Order Execution:**
- Retry loop exits immediately on empty result (doesn't retry transient failures)

**Critical Code Path:**
```python
# trader.py:822 - CRASHES!
position.db_persisted = False  # SpreadPosition has no db_persisted field!
```

---

### ICARUS (Aggressive Directional)

**Entry Logic:**
- Structurally sound but `db_persisted` flag set and never checked

**Exit Logic:**
- Silent exit prevention when pricing fails (returns False, "")
- No retry mechanism for failed close orders
- Circuit breaker margin tracking hardcoded to 0

**Order Execution:**
- Failed closes abandoned rather than retried
- Orphaned order tracking exists but never called

**Critical Code Path:**
```python
# trader.py:632-633
if current_value is None:
    return False, ""  # SILENT - position stays open!
```

---

### PEGASUS (SPX Iron Condor)

**Entry Logic:**
- Win probability threshold **DISABLED** (same as ARES)
- Effective win prob defaults to 50% when ML/Oracle fail

**Exit Logic:**
- Same valuation failure issue - returns (False, "")
- Partial close leaves one leg open with no retry
- Stop loss **disabled by default** (`use_stop_loss: bool = False`)

**Order Execution:**
- Rollback failure logs orphaned order
- DB save failure doesn't return early - orphaned positions created

**Critical Code Path:**
```python
# models.py:217-220 - STOP LOSS DISABLED!
use_stop_loss: bool = False  # Losses can run unlimited
```

---

### TITAN (Aggressive SPX Iron Condor)

**Entry Logic:**
- Position executed at broker but DB save failure doesn't return early
- Code continues as if position was saved

**Exit Logic:**
- Same valuation failure issue
- Partial close positions accumulate (never cleaned up)

**Order Execution:**
- If put spread succeeds but call fails, rollback attempted
- If rollback fails and `db=None`, orphaned order never logged

**Critical Code Path:**
```python
# trader.py:726-728 - NO EARLY RETURN!
if not self.db.save_position(position):
    logger.error(f"Position executed but not saved!")
    # BUG: Code continues! No return statement!
```

---

### ATLAS (SPX Wheel)

**Entry Logic:**
- Market hours check uses wrong timezone (blocks 8:30-9 AM CT, allows 3-4 PM CT)
- Missing `position_size_pct` attribute causes crash in decision logging

**Exit Logic:**
- Buy-to-close updates DB **before** verifying broker execution
- Partial fills accepted without validation
- Roll failures can leave positions in limbo

**Order Execution:**
- Bare except clause silently swallows alert failures
- Fallback price uses hardcoded SPX=5800 when all data sources fail

**Critical Code Path:**
```python
# spx_wheel_system.py:1123-1130 - WRONG TIMEZONE!
if now.hour < 9 or now.hour >= 16:  # Uses CT but checks ET times!
    return False  # Blocks valid trades 8:30-9 AM CT
```

---

## Common Patterns Across All Bots

### Pattern 1: Orphaned Position Creation
```python
# Execute order at broker (succeeds)
position = self.executor.execute_iron_condor(signal)

# Try to save to DB (fails)
if not self.db.save_position(position):
    logger.error("Failed to save!")
    # BUG: Should return None here!

# Code continues, returning position that isn't in DB
return position  # ORPHANED!
```

### Pattern 2: Silent Exit Failure
```python
def _check_exit_conditions(self, pos):
    current_value = self.executor.get_position_current_value(pos)
    if current_value is None:
        return False, ""  # Position stays open forever!

    # Profit/loss checks never reached
```

### Pattern 3: Partial Close Abandonment
```python
if success == 'partial_put':
    self.db.partial_close_position(...)
    logger.error("Manual intervention required")
    continue  # Never retried!
```

---

## Recommended Fixes

### Priority 1: CRITICAL (Implement Immediately)

1. **Add early return on DB save failure:**
```python
if not self.db.save_position(position):
    logger.error(f"CRITICAL: Position executed but DB save failed!")
    # NEW: Track as orphaned and return None
    self._log_orphaned_position(position)
    return None, signal
```

2. **Re-enable win probability threshold (ARES/PEGASUS):**
```python
# Remove the disabled check, restore original logic:
if effective_win_prob < self.config.min_win_probability:
    return None  # Skip low-confidence signals
```

3. **Fix ATHENA AttributeError:**
- Either add `db_persisted: bool = True` to `SpreadPosition` dataclass
- Or remove the line that sets it

4. **Fix ATLAS timezone bug:**
```python
# Correct market hours for Central Time
if now.hour < 8 or (now.hour == 8 and now.minute < 30) or now.hour >= 15:
    return False
```

### Priority 2: HIGH (Next Sprint)

1. **Add retry logic for partial closes:**
```python
if success == 'partial_put':
    # Retry closing call leg 3 times
    for attempt in range(3):
        time.sleep(5)
        call_result = self.executor.close_call_spread(pos)
        if call_result:
            break
```

2. **Add fallback for pricing failures:**
```python
if current_value is None:
    # Use last known price or force close at market
    current_value = self._get_last_known_value(pos)
    if current_value is None:
        logger.warning("Forcing market close due to pricing failure")
        return True, "PRICING_FAILURE_FORCE_CLOSE"
```

3. **Implement position reconciliation on startup:**
```python
def _reconcile_positions_on_startup(self):
    broker_positions = self.tradier.get_positions()
    db_positions = self.db.get_open_positions()

    for bp in broker_positions:
        if bp.order_id not in [dp.order_id for dp in db_positions]:
            logger.error(f"Orphaned position found: {bp}")
            self.db.log_orphaned_order(bp)
```

### Priority 3: MEDIUM (Future Enhancement)

1. Replace bare except clauses with specific exceptions
2. Add row-level locking for position updates
3. Implement proper margin tracking for circuit breaker
4. Add unit tests for all exit condition scenarios

---

## Verification Checklist

| Check | ARES | ATHENA | ICARUS | PEGASUS | TITAN | ATLAS |
|-------|------|--------|--------|---------|-------|-------|
| Entry logic traces correctly | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Exit logic handles all cases | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Orders actually submitted | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| DB persistence verified | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Partial closes handled | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Safety thresholds active | ❌ | ✅ | ✅ | ❌ | ✅ | ✅ |
| Error recovery exists | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## Conclusion

**All live trading bots have critical issues that could cause:**
- Trades to silently fail to close
- Positions to become orphaned (in broker but not database)
- Capital to remain at risk without bot awareness
- P&L tracking to become inaccurate

**Recommendation:** Do not use these bots in production until critical issues are fixed. The most urgent fixes are:
1. Add early return on DB save failure
2. Re-enable win probability thresholds
3. Fix ATHENA AttributeError crash
4. Fix ATLAS timezone bug

---

*Report generated by Claude Code verification audit*
