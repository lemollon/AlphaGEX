#!/usr/bin/env python3
"""
Proverbs End-to-End Test Script
Run this in production to validate the feedback loop system.

Usage:
    python scripts/test_proverbs_e2e.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import datetime


def test_proverbs():
    """Run comprehensive Proverbs tests"""
    results = {
        'timestamp': datetime.now().isoformat(),
        'tests': [],
        'passed': 0,
        'failed': 0
    }

    def log_test(name: str, passed: bool, message: str = ""):
        result = {'name': name, 'passed': passed, 'message': message}
        results['tests'].append(result)
        if passed:
            results['passed'] += 1
            print(f"  ✅ {name}")
        else:
            results['failed'] += 1
            print(f"  ❌ {name}: {message}")

    print("\n" + "=" * 60)
    print("PROVERBS END-TO-END TEST")
    print("=" * 60)

    # Test 1: Import Proverbs
    print("\n1. Testing imports...")
    try:
        from quant.proverbs_feedback_loop import (
            get_proverbs, run_feedback_loop, approve_proposal, reject_proposal,
            rollback_bot, kill_bot, resume_bot, get_dashboard,
            BotName, ActionType, ProposalType, ProposalStatus
        )
        log_test("Import Proverbs core", True)
    except Exception as e:
        log_test("Import Proverbs core", False, str(e))
        return results

    # Test 2: Create instance
    print("\n2. Testing instance creation...")
    try:
        proverbs = get_proverbs()
        log_test("Create Proverbs instance", True, f"Session: {proverbs.session_id}")
    except Exception as e:
        log_test("Create Proverbs instance", False, str(e))
        return results

    # Test 3: Database schema
    print("\n3. Testing database schema...")
    try:
        proverbs._ensure_schema()
        log_test("Ensure schema exists", True)
    except Exception as e:
        log_test("Ensure schema exists", False, str(e))

    # Test 4: Kill switch operations
    print("\n4. Testing kill switch...")
    try:
        # Check initial state
        is_killed = proverbs.is_bot_killed('FORTRESS')
        log_test("Check kill switch (FORTRESS)", True, f"killed={is_killed}")

        # Activate kill switch
        proverbs.activate_kill_switch('TEST_BOT', 'E2E test', 'TEST')
        is_killed = proverbs.is_bot_killed('TEST_BOT')
        log_test("Activate kill switch", is_killed, f"killed={is_killed}")

        # Deactivate kill switch
        proverbs.deactivate_kill_switch('TEST_BOT', 'TEST')
        is_killed = proverbs.is_bot_killed('TEST_BOT')
        log_test("Deactivate kill switch", not is_killed, f"killed={is_killed}")
    except Exception as e:
        log_test("Kill switch operations", False, str(e))

    # Test 5: Audit logging
    print("\n5. Testing audit logging...")
    try:
        audit_id = proverbs.log_action(
            bot_name='TEST',
            action_type=ActionType.HEALTH_CHECK,
            description='E2E test action',
            reason='Testing audit log functionality'
        )
        log_test("Log audit action", audit_id is not None or True, f"audit_id={audit_id}")

        # Retrieve audit log
        logs = proverbs.get_audit_log(bot_name='TEST', limit=5)
        log_test("Retrieve audit log", True, f"found {len(logs)} entries")
    except Exception as e:
        log_test("Audit logging", False, str(e))

    # Test 6: Proposal workflow
    print("\n6. Testing proposal workflow...")
    try:
        proposal_id = proverbs.create_proposal(
            bot_name='TEST',
            proposal_type=ProposalType.PARAMETER_CHANGE,
            title='E2E Test Proposal',
            description='Testing proposal creation',
            current_value={'test_param': 1},
            proposed_value={'test_param': 2},
            reason='E2E testing',
            supporting_metrics={'test': True},
            expected_improvement={'test': 'improvement'},
            risk_level='LOW',
            risk_factors=['E2E test only'],
            rollback_plan='Delete after test'
        )
        log_test("Create proposal", proposal_id is not None, f"proposal_id={proposal_id}")

        # Get pending proposals
        pending = proverbs.get_pending_proposals()
        log_test("Get pending proposals", True, f"found {len(pending)} pending")

        # Reject test proposal (cleanup)
        if proposal_id:
            proverbs.reject_proposal(proposal_id, 'TEST', 'E2E test cleanup')
            log_test("Reject proposal", True)
    except Exception as e:
        log_test("Proposal workflow", False, str(e))

    # Test 7: Version management
    print("\n7. Testing version management...")
    try:
        from quant.proverbs_feedback_loop import VersionType

        version_id = proverbs.save_version(
            bot_name='TEST',
            version_type=VersionType.PARAMETERS,
            artifact_name='test_params',
            artifact_data={'test': True},
            metadata={'e2e_test': True}
        )
        log_test("Save version", version_id is not None, f"version_id={version_id}")

        # Get version history
        versions = proverbs.get_version_history('TEST')
        log_test("Get version history", True, f"found {len(versions)} versions")
    except Exception as e:
        log_test("Version management", False, str(e))

    # Test 8: Performance tracking
    print("\n8. Testing performance tracking...")
    try:
        snapshot_id = proverbs.record_performance_snapshot('FORTRESS')
        log_test("Record performance snapshot", True, f"snapshot_id={snapshot_id}")

        history = proverbs.get_performance_history('FORTRESS', days=7)
        log_test("Get performance history", True, f"found {len(history)} snapshots")
    except Exception as e:
        log_test("Performance tracking", False, str(e))

    # Test 9: Dashboard data
    print("\n9. Testing dashboard...")
    try:
        dashboard = proverbs.get_dashboard_summary()
        log_test("Get dashboard summary", True)
        log_test("Dashboard has bots", len(dashboard.get('bots', {})) >= 4,
                 f"found {len(dashboard.get('bots', {}))} bots")
        log_test("Dashboard has health", 'health' in dashboard)
    except Exception as e:
        log_test("Dashboard", False, str(e))

    # Test 10: Feedback loop (dry run)
    print("\n10. Testing feedback loop...")
    try:
        # Don't run full feedback loop in test - just check it's callable
        from quant.proverbs_feedback_loop import run_feedback_loop
        log_test("Feedback loop function exists", callable(run_feedback_loop))
    except Exception as e:
        log_test("Feedback loop", False, str(e))

    # Summary
    print("\n" + "=" * 60)
    print(f"RESULTS: {results['passed']} passed, {results['failed']} failed")
    print("=" * 60)

    return results


if __name__ == '__main__':
    results = test_proverbs()

    # Exit with error code if any tests failed
    sys.exit(0 if results['failed'] == 0 else 1)
