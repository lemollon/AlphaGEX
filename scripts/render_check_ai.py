#!/usr/bin/env python3
"""
Render Shell Script: Check AI Features

Run in Render shell:
    python scripts/render_check_ai.py
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def ok(msg): print(f"[OK] {msg}")
def fail(msg): print(f"[FAIL] {msg}")
def warn(msg): print(f"[WARN] {msg}")
def info(msg): print(f"[INFO] {msg}")

print("=" * 60)
print("CHECKING AI FEATURES")
print("=" * 60)

errors = []

# Check API keys
print("\n-- API Keys --")
claude_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
if claude_key:
    ok(f"Claude API key configured: {claude_key[:10]}...")
else:
    warn("No Claude API key - Extended Thinking won't work")

# Learning Memory
print("\n-- Learning Memory --")
try:
    from ai.counselor_learning_memory import get_learning_memory, CounselorLearningMemory

    memory = get_learning_memory()
    ok("Learning Memory instance created")

    # Test recording
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")
    except:
        import pytz
        CENTRAL_TZ = pytz.timezone("America/Chicago")

    test_context = {
        "gex_regime": "TEST",
        "vix": 15.0,
        "spot_price": 590.0,
        "day_of_week": datetime.now(CENTRAL_TZ).weekday()
    }

    pred_id = memory.record_prediction(
        prediction_type="test",
        prediction="Test prediction",
        confidence=0.8,
        context=test_context
    )
    ok(f"Prediction recorded: {pred_id}")

    result = memory.record_outcome(
        prediction_id=pred_id,
        outcome="Test outcome",
        was_correct=True,
        notes="Verification test"
    )
    ok("Outcome recorded")

    insights = memory.get_learning_insights()
    info(f"Total predictions: {insights.get('total_predictions', 0)}")
    info(f"Accuracy: {insights.get('overall_accuracy_pct', 0):.1f}%")

except Exception as e:
    fail(f"Learning Memory error: {e}")
    errors.append("Learning Memory")

# Extended Thinking
print("\n-- Extended Thinking --")
try:
    from ai.counselor_extended_thinking import (
        analyze_with_extended_thinking,
        analyze_strike_selection,
        evaluate_trade_setup
    )
    ok("Extended Thinking module loaded")

    if claude_key:
        info("Extended Thinking API calls will work")
    else:
        warn("Extended Thinking needs API key to function")

except Exception as e:
    fail(f"Extended Thinking error: {e}")
    errors.append("Extended Thinking")

# COUNSELOR Personality
print("\n-- COUNSELOR Personality --")
try:
    from ai.counselor_personality import (
        build_counselor_system_prompt,
        get_counselor_welcome_message,
        COUNSELOR_NAME,
        USER_NAME
    )
    ok(f"COUNSELOR Personality loaded")
    info(f"COUNSELOR Name: {COUNSELOR_NAME}")
    info(f"User Name: {USER_NAME}")

    prompt = build_counselor_system_prompt()
    ok(f"System prompt: {len(prompt)} chars")

except Exception as e:
    fail(f"COUNSELOR Personality error: {e}")
    errors.append("COUNSELOR Personality")

# COUNSELOR Tools
print("\n-- COUNSELOR Tools --")
try:
    from ai.counselor_tools import COUNSELOR_TOOLS, get_system_status
    ok(f"COUNSELOR Tools loaded: {len(COUNSELOR_TOOLS)} tools")

    # List tools
    for name in list(COUNSELOR_TOOLS.keys())[:5]:
        info(f"  - {name}")
    if len(COUNSELOR_TOOLS) > 5:
        info(f"  ... and {len(COUNSELOR_TOOLS) - 5} more")

except Exception as e:
    fail(f"COUNSELOR Tools error: {e}")
    errors.append("COUNSELOR Tools")

# Bot Learning Memory Integration
print("\n-- Bot Learning Memory Integration --")
try:
    from trading.fortress_v2.trader import FortressTrader, LEARNING_MEMORY_AVAILABLE as ARES_LM
    has_pred = hasattr(FortressTrader, '_record_learning_memory_prediction')
    has_out = hasattr(FortressTrader, '_record_learning_memory_outcome')

    if ARES_LM and has_pred and has_out:
        ok("FORTRESS: Learning Memory fully integrated")
    else:
        warn(f"FORTRESS: LM={ARES_LM}, pred={has_pred}, out={has_out}")
except Exception as e:
    warn(f"FORTRESS check skipped: {e}")

try:
    from trading.solomon_v2.trader import SolomonTrader, LEARNING_MEMORY_AVAILABLE as SOLOMON_LM
    has_pred = hasattr(SolomonTrader, '_record_learning_memory_prediction')
    has_out = hasattr(SolomonTrader, '_record_learning_memory_outcome')

    if SOLOMON_LM and has_pred and has_out:
        ok("SOLOMON: Learning Memory fully integrated")
    else:
        warn(f"SOLOMON: LM={SOLOMON_LM}, pred={has_pred}, out={has_out}")
except Exception as e:
    warn(f"SOLOMON check skipped: {e}")

# Summary
print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} AI features have errors")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("SUCCESS: All AI features working")
    sys.exit(0)
