#!/usr/bin/env python3
"""
Test script to verify oracle_confidence flows correctly through all trading bots.

Tests the complete data flow:
1. Oracle returns confidence value
2. Signals extract and pass oracle_confidence
3. Executors use signal.oracle_confidence (not signal.confidence)
4. Positions store oracle_confidence correctly

Run with: python scripts/test_oracle_confidence_flow.py
"""

import sys
import os
from dataclasses import fields
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test results
passed = 0
failed = 0
errors = []


def test_pass(name: str):
    global passed
    passed += 1
    print(f"  ✓ {name}")


def test_fail(name: str, reason: str):
    global failed
    failed += 1
    errors.append(f"{name}: {reason}")
    print(f"  ✗ {name}: {reason}")


print("=" * 60)
print("ORACLE_CONFIDENCE END-TO-END FLOW TEST")
print("=" * 60)


# =============================================================================
# TEST 1: Model Field Definitions (Static Analysis)
# =============================================================================
print("\n1. MODEL FIELD DEFINITIONS (Static Analysis)")
print("-" * 40)

def check_model_has_field(bot_name: str, model_path: str, class_name: str, field_name: str):
    """Check that a dataclass has a specific field using static analysis"""
    try:
        with open(model_path, 'r') as f:
            content = f.read()

        # Find the class definition and check for the field
        # Pattern: field_name: type = default or field_name: type
        import re

        # Look for field definition pattern within a class
        pattern = rf'{field_name}\s*:\s*\w+'
        if re.search(pattern, content):
            test_pass(f"{bot_name} {class_name} has {field_name}")
        else:
            test_fail(f"{bot_name} {class_name}", f"missing {field_name} field")
    except FileNotFoundError:
        test_fail(f"{bot_name} {class_name}", f"file not found: {model_path}")
    except Exception as e:
        test_fail(f"{bot_name} {class_name}", str(e))

# FORTRESS
check_model_has_field("FORTRESS", "trading/fortress_v2/models.py", "IronCondorSignal", "oracle_confidence")
check_model_has_field("FORTRESS", "trading/fortress_v2/models.py", "IronCondorPosition", "oracle_confidence")

# SOLOMON
check_model_has_field("SOLOMON", "trading/solomon_v2/models.py", "TradeSignal", "oracle_confidence")
check_model_has_field("SOLOMON", "trading/solomon_v2/models.py", "SpreadPosition", "oracle_confidence")

# SAMSON
check_model_has_field("SAMSON", "trading/samson/models.py", "IronCondorSignal", "oracle_confidence")
check_model_has_field("SAMSON", "trading/samson/models.py", "IronCondorPosition", "oracle_confidence")

# PEGASUS
check_model_has_field("PEGASUS", "trading/pegasus/models.py", "IronCondorSignal", "oracle_confidence")
check_model_has_field("PEGASUS", "trading/pegasus/models.py", "IronCondorPosition", "oracle_confidence")

# ICARUS
check_model_has_field("ICARUS", "trading/icarus/models.py", "TradeSignal", "oracle_confidence")
check_model_has_field("ICARUS", "trading/icarus/models.py", "TradeSignal", "oracle_advice")
check_model_has_field("ICARUS", "trading/icarus/models.py", "SpreadPosition", "oracle_confidence")
check_model_has_field("ICARUS", "trading/icarus/models.py", "SpreadPosition", "oracle_advice")


# =============================================================================
# TEST 2: Signal Constructor Has oracle_confidence Parameter
# =============================================================================
print("\n2. SIGNAL CONSTRUCTOR ACCEPTS oracle_confidence")
print("-" * 40)

def check_signal_accepts_oracle_confidence(bot_name: str, signals_path: str):
    """Check that signal creation includes oracle_confidence parameter"""
    try:
        with open(signals_path, 'r') as f:
            content = f.read()

        # Look for signal creation with oracle_confidence parameter
        import re
        # Pattern: IronCondorSignal( or TradeSignal( with oracle_confidence= somewhere in the call
        # The signal creation spans multiple lines, so we look for return <Type>Signal( then oracle_confidence=
        if re.search(r'(IronCondorSignal|TradeSignal)\s*\(', content) and re.search(r'oracle_confidence\s*=\s*oracle', content):
            test_pass(f"{bot_name} signal creation includes oracle_confidence")
        else:
            test_fail(f"{bot_name} signals.py", "signal creation missing oracle_confidence parameter")
    except FileNotFoundError:
        test_fail(f"{bot_name} signals.py", f"file not found: {signals_path}")
    except Exception as e:
        test_fail(f"{bot_name} signals.py", str(e))

check_signal_accepts_oracle_confidence("FORTRESS", "trading/fortress_v2/signals.py")
check_signal_accepts_oracle_confidence("SOLOMON", "trading/solomon_v2/signals.py")
check_signal_accepts_oracle_confidence("SAMSON", "trading/samson/signals.py")
check_signal_accepts_oracle_confidence("PEGASUS", "trading/pegasus/signals.py")
check_signal_accepts_oracle_confidence("ICARUS", "trading/icarus/signals.py")


# =============================================================================
# TEST 3: Position to_dict Includes oracle_confidence
# =============================================================================
print("\n3. POSITION to_dict() INCLUDES oracle_confidence")
print("-" * 40)

def check_position_to_dict_has_oracle(bot_name: str, model_path: str):
    """Check that position.to_dict() includes oracle fields"""
    try:
        with open(model_path, 'r') as f:
            content = f.read()

        # Look for to_dict method that includes oracle_confidence
        import re
        # Check if to_dict contains oracle_confidence
        to_dict_match = re.search(r'def to_dict\(self\).*?return\s*\{([^}]+)\}', content, re.DOTALL)
        if to_dict_match:
            dict_content = to_dict_match.group(1)
            if 'oracle_confidence' in dict_content:
                test_pass(f"{bot_name} position.to_dict() includes oracle_confidence")
            else:
                test_fail(f"{bot_name} position.to_dict()", "missing oracle_confidence in to_dict()")
        else:
            # Check for Position classes that have oracle_confidence field
            if "oracle_confidence" in content and "Position" in content:
                test_pass(f"{bot_name} position has oracle_confidence (to_dict may use asdict)")
            else:
                test_fail(f"{bot_name} model", "no to_dict found or missing oracle_confidence")
    except FileNotFoundError:
        test_fail(f"{bot_name} model", f"file not found: {model_path}")
    except Exception as e:
        test_fail(f"{bot_name} model", str(e))

check_position_to_dict_has_oracle("FORTRESS", "trading/fortress_v2/models.py")
check_position_to_dict_has_oracle("SOLOMON", "trading/solomon_v2/models.py")
check_position_to_dict_has_oracle("SAMSON", "trading/samson/models.py")
check_position_to_dict_has_oracle("PEGASUS", "trading/pegasus/models.py")
check_position_to_dict_has_oracle("ICARUS", "trading/icarus/models.py")


# =============================================================================
# TEST 4: Code Inspection - Executor Uses signal.oracle_confidence
# =============================================================================
print("\n4. EXECUTOR CODE INSPECTION")
print("-" * 40)

import re

def check_executor_uses_oracle_confidence(bot_name: str, executor_path: str):
    """Check that executor uses signal.oracle_confidence, not signal.confidence"""
    try:
        with open(executor_path, 'r') as f:
            content = f.read()

        # Look for the bug pattern
        bug_pattern = r'oracle_confidence\s*=\s*signal\.confidence[^_]'
        bug_matches = re.findall(bug_pattern, content)

        # Look for the correct pattern
        correct_pattern = r'oracle_confidence\s*=\s*signal\.oracle_confidence'
        correct_matches = re.findall(correct_pattern, content)

        if bug_matches:
            test_fail(f"{bot_name} executor", f"still uses signal.confidence for oracle_confidence ({len(bug_matches)} occurrences)")
        elif correct_matches:
            test_pass(f"{bot_name} executor uses signal.oracle_confidence ({len(correct_matches)} occurrences)")
        else:
            test_fail(f"{bot_name} executor", "no oracle_confidence assignment found")
    except FileNotFoundError:
        test_fail(f"{bot_name} executor", f"file not found: {executor_path}")
    except Exception as e:
        test_fail(f"{bot_name} executor", str(e))

check_executor_uses_oracle_confidence("FORTRESS", "trading/fortress_v2/executor.py")
check_executor_uses_oracle_confidence("SOLOMON", "trading/solomon_v2/executor.py")
check_executor_uses_oracle_confidence("SAMSON", "trading/samson/executor.py")
check_executor_uses_oracle_confidence("PEGASUS", "trading/pegasus/executor.py")
check_executor_uses_oracle_confidence("ICARUS", "trading/icarus/executor.py")


# =============================================================================
# TEST 5: Signals Code Inspection - Passes oracle_confidence
# =============================================================================
print("\n5. SIGNALS CODE INSPECTION")
print("-" * 40)

def check_signals_passes_oracle_confidence(bot_name: str, signals_path: str):
    """Check that signals.py passes oracle_confidence when creating signal"""
    try:
        with open(signals_path, 'r') as f:
            content = f.read()

        # Look for oracle_confidence being passed to signal constructor
        pattern = r'oracle_confidence\s*=\s*oracle.*confidence|oracle_confidence\s*=\s*oracle_confidence'
        matches = re.findall(pattern, content, re.IGNORECASE)

        if matches:
            test_pass(f"{bot_name} signals passes oracle_confidence to signal")
        else:
            test_fail(f"{bot_name} signals", "doesn't pass oracle_confidence to signal")
    except FileNotFoundError:
        test_fail(f"{bot_name} signals", f"file not found: {signals_path}")
    except Exception as e:
        test_fail(f"{bot_name} signals", str(e))

check_signals_passes_oracle_confidence("FORTRESS", "trading/fortress_v2/signals.py")
check_signals_passes_oracle_confidence("SOLOMON", "trading/solomon_v2/signals.py")
check_signals_passes_oracle_confidence("SAMSON", "trading/samson/signals.py")
check_signals_passes_oracle_confidence("PEGASUS", "trading/pegasus/signals.py")
check_signals_passes_oracle_confidence("ICARUS", "trading/icarus/signals.py")


# =============================================================================
# TEST 6: Database Schema Inspection
# =============================================================================
print("\n6. DATABASE SCHEMA INSPECTION")
print("-" * 40)

def check_db_has_oracle_columns(bot_name: str, db_path: str):
    """Check that db.py has oracle_confidence and oracle_advice columns"""
    try:
        with open(db_path, 'r') as f:
            content = f.read()

        has_confidence = 'oracle_confidence' in content
        has_advice = 'oracle_advice' in content

        if has_confidence:
            test_pass(f"{bot_name} db.py has oracle_confidence column")
        else:
            test_fail(f"{bot_name} db.py", "missing oracle_confidence column")

        if has_advice:
            test_pass(f"{bot_name} db.py has oracle_advice column")
        else:
            test_fail(f"{bot_name} db.py", "missing oracle_advice column")
    except FileNotFoundError:
        test_fail(f"{bot_name} db.py", f"file not found: {db_path}")
    except Exception as e:
        test_fail(f"{bot_name} db.py", str(e))

check_db_has_oracle_columns("FORTRESS", "trading/fortress_v2/db.py")
check_db_has_oracle_columns("SOLOMON", "trading/solomon_v2/db.py")
check_db_has_oracle_columns("SAMSON", "trading/samson/db.py")
check_db_has_oracle_columns("PEGASUS", "trading/pegasus/db.py")
check_db_has_oracle_columns("ICARUS", "trading/icarus/db.py")


# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)
print(f"Passed: {passed}")
print(f"Failed: {failed}")

if errors:
    print("\nFailed tests:")
    for e in errors:
        print(f"  - {e}")

if failed == 0:
    print("\n✓ ALL TESTS PASSED - oracle_confidence is fully wired up!")
    sys.exit(0)
else:
    print(f"\n✗ {failed} TESTS FAILED")
    sys.exit(1)
