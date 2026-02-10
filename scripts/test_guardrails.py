#!/usr/bin/env python3
"""
Test Proverbs guardrails: 5-minute cooldown after 3 consecutive losses.

Run in Render shell:
    python scripts/test_guardrails.py

Tests:
  1. Proverbs module loads and creates tracker
  2. Record 3 consecutive losses -> kill switch triggers
  3. Kill switch sets 5-min pause on bot (not permanent)
  4. After cooldown, reset() clears tracker -> needs 3 more losses
  5. A win resets the consecutive loss counter
  6. Daily loss limit is NOT checked (removed)
"""

import sys
import os

# Ensure project root is on path (for Render shell)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  -- {detail}")


# ─────────────────────────────────────────────────────────
# TEST 1: Proverbs module loads
# ─────────────────────────────────────────────────────────
print("\n=== TEST 1: Module import ===")
try:
    from quant.proverbs_enhancements import (
        get_proverbs_enhanced,
        ConsecutiveLossTracker,
        ConsecutiveLossMonitor,
        ENHANCED_GUARDRAILS,
    )
    test("Proverbs module imports", True)
except ImportError as e:
    test("Proverbs module imports", False, str(e))
    print("\nCannot continue without module. Exiting.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────
# TEST 2: Create Proverbs and get monitor
# ─────────────────────────────────────────────────────────
print("\n=== TEST 2: Create Proverbs singleton ===")
try:
    proverbs = get_proverbs_enhanced()
    test("get_proverbs_enhanced() returns object", proverbs is not None)
    test("has consecutive_loss_monitor", hasattr(proverbs, 'consecutive_loss_monitor'))
    monitor = proverbs.consecutive_loss_monitor
    test("monitor is ConsecutiveLossMonitor", isinstance(monitor, ConsecutiveLossMonitor))
except Exception as e:
    test("get_proverbs_enhanced()", False, str(e))
    print("\nCannot continue. Exiting.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────
# TEST 3: get_status() returns dict (not get_tracker)
# ─────────────────────────────────────────────────────────
print("\n=== TEST 3: get_status() API ===")
monitor.reset('TEST_BOT')
status = monitor.get_status('TEST_BOT')
test("get_status returns dict", isinstance(status, dict), f"got {type(status)}")
test("dict has 'consecutive_losses'", 'consecutive_losses' in status, f"keys: {list(status.keys())}")
test("dict has 'triggered_kill'", 'triggered_kill' in status, f"keys: {list(status.keys())}")
test("initial consecutive_losses == 0", status['consecutive_losses'] == 0, f"got {status['consecutive_losses']}")
test("initial triggered_kill == False", status['triggered_kill'] is False, f"got {status['triggered_kill']}")

# ─────────────────────────────────────────────────────────
# TEST 4: Record 3 consecutive losses -> kill triggers
# ─────────────────────────────────────────────────────────
print("\n=== TEST 4: 3 consecutive losses triggers kill ===")
monitor.reset('TEST_BOT')
today = datetime.now().strftime('%Y-%m-%d')

alert1 = monitor.record_trade_outcome('TEST_BOT', pnl=-500, trade_date=today)
s1 = monitor.get_status('TEST_BOT')
test("After loss 1: consecutive_losses == 1", s1['consecutive_losses'] == 1, f"got {s1['consecutive_losses']}")
test("After loss 1: triggered_kill == False", s1['triggered_kill'] is False)
test("After loss 1: no alert", alert1 is None, f"got {alert1}")

alert2 = monitor.record_trade_outcome('TEST_BOT', pnl=-300, trade_date=today)
s2 = monitor.get_status('TEST_BOT')
test("After loss 2: consecutive_losses == 2", s2['consecutive_losses'] == 2, f"got {s2['consecutive_losses']}")
test("After loss 2: triggered_kill == False", s2['triggered_kill'] is False)

alert3 = monitor.record_trade_outcome('TEST_BOT', pnl=-200, trade_date=today)
s3 = monitor.get_status('TEST_BOT')
test("After loss 3: consecutive_losses == 3", s3['consecutive_losses'] == 3, f"got {s3['consecutive_losses']}")
test("After loss 3: triggered_kill == True", s3['triggered_kill'] is True, f"got {s3['triggered_kill']}")
test("After loss 3: alert returned", alert3 is not None, "no alert returned")
if alert3:
    test("Alert type is CONSECUTIVE_LOSS_KILL", alert3.get('type') == 'CONSECUTIVE_LOSS_KILL', f"got {alert3.get('type')}")

# ─────────────────────────────────────────────────────────
# TEST 5: Simulate 5-minute cooldown logic (as bots do)
# ─────────────────────────────────────────────────────────
print("\n=== TEST 5: 5-minute cooldown simulation ===")

# Bot detects triggered_kill, sets pause
now = datetime.now()
loss_streak_pause_until = None

status = monitor.get_status('TEST_BOT')
if status.get('triggered_kill') and loss_streak_pause_until is None:
    loss_streak_pause_until = now + timedelta(minutes=5)
    test("Kill detected -> pause set for 5 min", loss_streak_pause_until is not None)
    test("Pause is ~5 min from now", 290 < (loss_streak_pause_until - now).total_seconds() <= 300,
         f"got {(loss_streak_pause_until - now).total_seconds()}s")

# Simulate: still in cooldown
simulated_now = now + timedelta(minutes=2)
in_cooldown = simulated_now < loss_streak_pause_until
test("At +2 min: still in cooldown", in_cooldown is True)

# Simulate: cooldown expired
simulated_now = now + timedelta(minutes=6)
cooldown_expired = simulated_now >= loss_streak_pause_until
test("At +6 min: cooldown expired", cooldown_expired is True)

# ─────────────────────────────────────────────────────────
# TEST 6: reset() clears tracker, needs 3 more losses
# ─────────────────────────────────────────────────────────
print("\n=== TEST 6: reset() clears tracker ===")
monitor.reset('TEST_BOT')
s_after_reset = monitor.get_status('TEST_BOT')
test("After reset: consecutive_losses == 0", s_after_reset['consecutive_losses'] == 0)
test("After reset: triggered_kill == False", s_after_reset['triggered_kill'] is False)

# Need 3 MORE losses to trigger again
monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
s_mid = monitor.get_status('TEST_BOT')
test("After 2 new losses: consecutive_losses == 2", s_mid['consecutive_losses'] == 2)
test("After 2 new losses: triggered_kill == False", s_mid['triggered_kill'] is False)

monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
s_trigger2 = monitor.get_status('TEST_BOT')
test("After 3 new losses: triggered_kill == True", s_trigger2['triggered_kill'] is True)

# ─────────────────────────────────────────────────────────
# TEST 7: A win resets the counter
# ─────────────────────────────────────────────────────────
print("\n=== TEST 7: Win resets counter ===")
monitor.reset('TEST_BOT')
monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
s_2loss = monitor.get_status('TEST_BOT')
test("After 2 losses: consecutive_losses == 2", s_2loss['consecutive_losses'] == 2)

monitor.record_trade_outcome('TEST_BOT', pnl=200, trade_date=today)
s_after_win = monitor.get_status('TEST_BOT')
test("After win: consecutive_losses == 0", s_after_win['consecutive_losses'] == 0)
test("After win: triggered_kill == False", s_after_win['triggered_kill'] is False)

# ─────────────────────────────────────────────────────────
# TEST 8: Daily loss limit NOT present in bot traders
# ─────────────────────────────────────────────────────────
print("\n=== TEST 8: No daily $5K limit in bot traders ===")

# Verify that daily_loss_monitor.get_daily_stats is NOT called in traders
bot_files = [
    'trading/fortress_v2/trader.py',
    'trading/samson/trader.py',
    'trading/anchor/trader.py',
]
for filepath in bot_files:
    full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filepath)
    with open(full_path) as f:
        content = f.read()
    has_daily_loss = 'daily_loss_monitor' in content or 'get_daily_stats' in content
    bot_name = filepath.split('/')[1].upper()
    test(f"{bot_name}: no daily_loss_monitor reference", not has_daily_loss,
         "still has daily loss check!")

# ─────────────────────────────────────────────────────────
# TEST 9: Bot traders use get_status() not get_tracker()
# ─────────────────────────────────────────────────────────
print("\n=== TEST 9: Bots use get_status() (not get_tracker()) ===")
for filepath in bot_files:
    full_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filepath)
    with open(full_path) as f:
        content = f.read()
    bot_name = filepath.split('/')[1].upper()
    uses_get_tracker = 'get_tracker(' in content
    uses_get_status = 'get_status(' in content
    uses_reset = '.reset(' in content
    test(f"{bot_name}: does NOT use get_tracker()", not uses_get_tracker,
         "still using private _get_tracker API!")
    test(f"{bot_name}: uses get_status()", uses_get_status)
    test(f"{bot_name}: uses reset()", uses_reset)

# ─────────────────────────────────────────────────────────
# TEST 10: Verify kill threshold is 3
# ─────────────────────────────────────────────────────────
print("\n=== TEST 10: Configuration ===")
test("Kill threshold == 3", ENHANCED_GUARDRAILS['consecutive_loss_kill_threshold'] == 3,
     f"got {ENHANCED_GUARDRAILS['consecutive_loss_kill_threshold']}")

# ─────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print(f"{'='*50}")

if failed > 0:
    print("\nFAILED TESTS DETECTED - review output above")
    sys.exit(1)
else:
    print("\nAll tests passed!")
    sys.exit(0)
