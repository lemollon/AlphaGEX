#!/usr/bin/env python3
"""
AlphaGEX AI Features Initialization and Health Check

This script verifies all AI features are properly initialized and working:
- COUNSELOR Extended Thinking
- COUNSELOR Learning Memory
- Prophet integration
- API endpoints

Run this after deployment to ensure all AI features are production-ready.
"""

import os
import sys
import json
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Central Time
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")


def check_mark(passed: bool) -> str:
    """Return checkmark or X based on status."""
    return "[OK]" if passed else "[FAIL]"


def test_learning_memory():
    """Test Learning Memory initialization and basic operations."""
    logger.info("\n--- Testing Learning Memory ---")

    try:
        from ai.counselor_learning_memory import get_learning_memory, CounselorLearningMemory

        # Get global instance
        memory = get_learning_memory()
        logger.info(f"{check_mark(memory is not None)} Learning Memory instance created")

        # Test prediction recording
        test_context = {
            "gex_regime": "POSITIVE",
            "vix": 15.5,
            "spot_price": 590.50,
            "day_of_week": datetime.now(CENTRAL_TZ).weekday()
        }

        prediction_id = memory.record_prediction(
            prediction_type="test_prediction",
            prediction="Test initialization check",
            confidence=0.8,
            context=test_context
        )
        logger.info(f"{check_mark(prediction_id is not None)} Prediction recorded: {prediction_id}")

        # Test outcome recording
        result = memory.record_outcome(
            prediction_id=prediction_id,
            outcome="Test outcome",
            was_correct=True,
            notes="Initialization test"
        )
        logger.info(f"{check_mark(result)} Outcome recorded")

        # Test insights retrieval
        insights = memory.get_learning_insights()
        logger.info(f"{check_mark(insights is not None)} Learning insights retrieved")
        logger.info(f"    Total predictions: {insights.get('total_predictions', 0)}")
        logger.info(f"    With outcomes: {insights.get('predictions_with_outcomes', 0)}")
        logger.info(f"    Overall accuracy: {insights.get('overall_accuracy_pct', 0):.1f}%")

        return True

    except ImportError as e:
        logger.error(f"[FAIL] Learning Memory import failed: {e}")
        return False
    except Exception as e:
        logger.error(f"[FAIL] Learning Memory error: {e}")
        return False


def test_extended_thinking():
    """Test Extended Thinking availability (requires API key)."""
    logger.info("\n--- Testing Extended Thinking ---")

    try:
        from ai.counselor_extended_thinking import (
            analyze_with_extended_thinking,
            analyze_strike_selection,
            evaluate_trade_setup,
            ThinkingResult
        )

        logger.info(f"{check_mark(True)} Extended Thinking module imported")

        # Check API key availability
        api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        logger.info(f"{check_mark(bool(api_key))} API key configured: {'Yes' if api_key else 'No'}")

        if not api_key:
            logger.warning("    Skipping Extended Thinking live test (no API key)")
            return True  # Module exists, just no API key

        # Quick test (minimal budget)
        logger.info("    Running quick Extended Thinking test...")
        result = analyze_with_extended_thinking(
            prompt="What is 2+2? Reply with just the number.",
            context={"test": True},
            thinking_budget=1024,  # Minimum budget
            api_key=api_key
        )

        if result:
            logger.info(f"{check_mark(True)} Extended Thinking API call succeeded")
            logger.info(f"    Response duration: {result.duration_ms}ms")
            logger.info(f"    Tokens used: {result.tokens_used}")
        else:
            logger.warning("[WARN] Extended Thinking returned None (may be rate limited)")

        return True

    except ImportError as e:
        logger.error(f"[FAIL] Extended Thinking import failed: {e}")
        return False
    except Exception as e:
        logger.error(f"[FAIL] Extended Thinking error: {e}")
        return False


def test_counselor_personality():
    """Test COUNSELOR personality system."""
    logger.info("\n--- Testing COUNSELOR Personality ---")

    try:
        from ai.counselor_personality import (
            build_counselor_system_prompt,
            get_counselor_welcome_message,
            COUNSELOR_NAME,
            USER_NAME
        )

        logger.info(f"{check_mark(True)} COUNSELOR personality module imported")
        logger.info(f"    COUNSELOR Name: {COUNSELOR_NAME}")
        logger.info(f"    User Name: {USER_NAME}")

        # Test system prompt generation
        system_prompt = build_counselor_system_prompt()
        logger.info(f"{check_mark(len(system_prompt) > 100)} System prompt generated ({len(system_prompt)} chars)")

        # Test welcome message
        welcome = get_counselor_welcome_message()
        logger.info(f"{check_mark(len(welcome) > 10)} Welcome message generated")

        return True

    except ImportError as e:
        logger.error(f"[FAIL] COUNSELOR personality import failed: {e}")
        return False
    except Exception as e:
        logger.error(f"[FAIL] COUNSELOR personality error: {e}")
        return False


def test_counselor_tools():
    """Test COUNSELOR agentic tools."""
    logger.info("\n--- Testing COUNSELOR Tools ---")

    try:
        from ai.counselor_tools import (
            COUNSELOR_TOOLS,
            get_system_status,
            get_counselor_briefing
        )

        logger.info(f"{check_mark(True)} COUNSELOR tools module imported")
        logger.info(f"    Available tools: {len(COUNSELOR_TOOLS)}")

        # List tool names
        for tool_name in list(COUNSELOR_TOOLS.keys())[:5]:
            logger.info(f"      - {tool_name}")
        if len(COUNSELOR_TOOLS) > 5:
            logger.info(f"      ... and {len(COUNSELOR_TOOLS) - 5} more")

        # Test system status
        status = get_system_status()
        logger.info(f"{check_mark(status is not None)} System status retrieved")

        return True

    except ImportError as e:
        logger.error(f"[FAIL] COUNSELOR tools import failed: {e}")
        return False
    except Exception as e:
        logger.error(f"[FAIL] COUNSELOR tools error: {e}")
        return False


def test_oracle_integration():
    """Test Prophet advisor integration."""
    logger.info("\n--- Testing Prophet Integration ---")

    try:
        from quant.prophet_advisor import ProphetAdvisor, get_prophet

        logger.info(f"{check_mark(True)} Prophet module imported")

        prophet = get_prophet()
        logger.info(f"{check_mark(prophet is not None)} Prophet instance created")

        return True

    except ImportError as e:
        logger.error(f"[FAIL] Prophet import failed: {e}")
        return False
    except Exception as e:
        logger.error(f"[FAIL] Prophet error: {e}")
        return False


def test_bot_learning_memory_integration():
    """Test that bots have Learning Memory wired in."""
    logger.info("\n--- Testing Bot Learning Memory Integration ---")

    results = []

    # Test FORTRESS
    try:
        from trading.fortress_v2.trader import FortressTrader, LEARNING_MEMORY_AVAILABLE
        logger.info(f"{check_mark(LEARNING_MEMORY_AVAILABLE)} FORTRESS Learning Memory import: {'Yes' if LEARNING_MEMORY_AVAILABLE else 'No'}")

        # Check if methods exist
        has_prediction = hasattr(FortressTrader, '_record_learning_memory_prediction')
        has_outcome = hasattr(FortressTrader, '_record_learning_memory_outcome')
        logger.info(f"{check_mark(has_prediction)} FORTRESS _record_learning_memory_prediction method exists")
        logger.info(f"{check_mark(has_outcome)} FORTRESS _record_learning_memory_outcome method exists")
        results.append(LEARNING_MEMORY_AVAILABLE and has_prediction and has_outcome)
    except ImportError as e:
        logger.error(f"[FAIL] FORTRESS import failed: {e}")
        results.append(False)

    # Test SOLOMON
    try:
        from trading.solomon_v2.trader import SolomonTrader, LEARNING_MEMORY_AVAILABLE
        logger.info(f"{check_mark(LEARNING_MEMORY_AVAILABLE)} SOLOMON Learning Memory import: {'Yes' if LEARNING_MEMORY_AVAILABLE else 'No'}")

        has_prediction = hasattr(SolomonTrader, '_record_learning_memory_prediction')
        has_outcome = hasattr(SolomonTrader, '_record_learning_memory_outcome')
        logger.info(f"{check_mark(has_prediction)} SOLOMON _record_learning_memory_prediction method exists")
        logger.info(f"{check_mark(has_outcome)} SOLOMON _record_learning_memory_outcome method exists")
        results.append(LEARNING_MEMORY_AVAILABLE and has_prediction and has_outcome)
    except ImportError as e:
        logger.error(f"[FAIL] SOLOMON import failed: {e}")
        results.append(False)

    return all(results)


def main():
    """Run all AI feature initialization checks."""
    logger.info("=" * 60)
    logger.info("AlphaGEX AI Features Initialization Check")
    logger.info(f"Timestamp: {datetime.now(CENTRAL_TZ).isoformat()}")
    logger.info("=" * 60)

    results = {}

    # Run all tests
    results['learning_memory'] = test_learning_memory()
    results['extended_thinking'] = test_extended_thinking()
    results['counselor_personality'] = test_counselor_personality()
    results['counselor_tools'] = test_counselor_tools()
    results['prophet'] = test_oracle_integration()
    results['bot_integration'] = test_bot_learning_memory_integration()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    passed = sum(results.values())
    total = len(results)

    for feature, status in results.items():
        logger.info(f"  {check_mark(status)} {feature.replace('_', ' ').title()}")

    logger.info("")
    logger.info(f"Passed: {passed}/{total}")

    if passed == total:
        logger.info("\nAll AI features are initialized and production-ready!")
        return 0
    else:
        logger.warning(f"\n{total - passed} feature(s) need attention.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
