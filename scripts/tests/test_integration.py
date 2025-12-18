#!/usr/bin/env python3
"""
Integration Test Script - End-to-End System Tests
Run in Render shell: python scripts/tests/test_integration.py

Tests full system integration including:
- Data flow from ingestion to storage
- AI/ML prediction pipelines
- Trading bot decision flows
- Chatbot interactions
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Configuration
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:8000')


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(test_name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    symbol = "✓" if passed else "✗"
    print(f"  {symbol} [{status}] {test_name}")
    if details:
        print(f"           {details}")


def api_request(endpoint, method='GET', data=None, timeout=60):
    """Make API request and return response"""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {'Content-Type': 'application/json'}

    try:
        if data:
            data = json.dumps(data).encode('utf-8')

        req = Request(url, data=data, headers=headers, method=method)
        response = urlopen(req, timeout=timeout)

        body = response.read().decode('utf-8')
        return {
            'success': True,
            'status': response.status,
            'data': json.loads(body) if body else {}
        }
    except HTTPError as e:
        try:
            body = e.read().decode('utf-8')
            error_data = json.loads(body) if body else {}
        except:
            error_data = {}
        return {
            'success': False,
            'status': e.code,
            'data': error_data,
            'error': str(e)
        }
    except Exception as e:
        return {
            'success': False,
            'status': 0,
            'data': {},
            'error': str(e)
        }


def test_oracle_prediction_flow():
    """Test complete ORACLE prediction flow"""
    print_header("ORACLE PREDICTION FLOW TEST")
    results = []

    # Step 1: Check Oracle status
    print("\n  Step 1: Check Oracle Status")
    resp = api_request('/api/zero-dte/oracle/status')
    oracle_ready = resp['success'] and resp['data'].get('success', False)
    results.append(oracle_ready)
    print_result("Oracle status check", oracle_ready,
                f"Claude: {resp['data'].get('oracle', {}).get('claude_available', 'N/A')}")

    if not oracle_ready:
        print("  ⚠️  Oracle not ready, skipping prediction test")
        return False

    # Step 2: Run test prediction
    print("\n  Step 2: Run Test Prediction")
    test_data = {
        "spot_price": 5900,
        "vix": 18.5,
        "gex_regime": "POSITIVE",
        "day_of_week": datetime.now().weekday(),
        "vix_1d_change": -0.5,
        "normalized_gex": 0.6,
        "distance_to_call_wall": 50,
        "distance_to_put_wall": 80
    }

    resp = api_request('/api/zero-dte/oracle/analyze', method='POST', data=test_data)
    prediction_success = resp['success'] and resp['data'].get('success', False)
    results.append(prediction_success)

    if prediction_success:
        pred = resp['data'].get('prediction', {})
        print_result("Prediction generated", True,
                    f"Advice: {pred.get('advice', 'N/A')}, Win Prob: {pred.get('win_probability', 0)*100:.1f}%")

        # Check for Claude explanation
        has_claude = 'claude_explanation' in resp['data']
        print_result("Claude explanation available", has_claude)
        results.append(has_claude)
    else:
        print_result("Prediction generated", False, resp.get('error', ''))

    # Step 3: Verify prediction was logged
    print("\n  Step 3: Verify Prediction Logged")
    resp = api_request('/api/zero-dte/oracle/logs')
    logs = resp['data'].get('logs', [])
    has_predict_log = any(log.get('type') == 'PREDICT' for log in logs)
    results.append(has_predict_log)
    print_result("Prediction logged", has_predict_log, f"{len(logs)} total logs")

    return all(results)


def test_pythia_calibration_flow():
    """Test PYTHIA probability calibration system"""
    print_header("PYTHIA CALIBRATION FLOW TEST")
    results = []

    # Step 1: Get current weights
    print("\n  Step 1: Get Current Weights")
    resp = api_request('/api/probability/weights')
    weights_success = resp['success'] and resp['data'].get('success', False)
    results.append(weights_success)

    weights = resp['data'].get('weights', [])
    if weights_success and weights:
        print_result("Weights retrieved", True, f"{len(weights)} weight factors")
        for w in weights:
            print(f"           - {w.get('weight_name')}: {w.get('weight_value', 0):.2f}")
    else:
        print_result("Weights retrieved", False)

    # Step 2: Get prediction outcomes
    print("\n  Step 2: Get Prediction Outcomes")
    resp = api_request('/api/probability/outcomes?days=90')
    outcomes_success = resp['success'] and resp['data'].get('success', False)
    results.append(outcomes_success)

    outcomes = resp['data'].get('outcomes', [])
    stats = resp['data'].get('stats', {})
    if outcomes_success:
        print_result("Outcomes retrieved", True,
                    f"{len(outcomes)} outcomes, Accuracy: {stats.get('accuracy_pct', 0):.1f}%")
    else:
        print_result("Outcomes retrieved", outcomes_success)

    # Step 3: Get calibration history
    print("\n  Step 3: Get Calibration History")
    resp = api_request('/api/probability/calibration-history?days=90')
    cal_success = resp['success'] and resp['data'].get('success', False)
    results.append(cal_success)

    cal_history = resp['data'].get('calibration_history', [])
    print_result("Calibration history", cal_success, f"{len(cal_history)} calibration events")

    return all(results)


def test_ml_training_flow():
    """Test PROMETHEUS ML training and prediction flow"""
    print_header("PROMETHEUS ML FLOW TEST")
    results = []

    # Step 1: Check ML status
    print("\n  Step 1: Check ML Status")
    resp = api_request('/api/ml/status')
    ml_available = resp['success']
    results.append(ml_available)

    if ml_available:
        status = resp['data']
        print_result("ML status retrieved", True,
                    f"Model trained: {status.get('model_trained', 'N/A')}")
    else:
        print_result("ML status retrieved", False)

    # Step 2: Check data quality
    print("\n  Step 2: Check Data Quality")
    resp = api_request('/api/ml/data-quality')
    dq_success = resp['success']
    results.append(dq_success)

    if dq_success:
        dq = resp['data']
        print_result("Data quality retrieved", True,
                    f"Total samples: {dq.get('total_samples', 0)}")
    else:
        print_result("Data quality retrieved", False)

    # Step 3: Get feature importance
    print("\n  Step 3: Get Feature Importance")
    resp = api_request('/api/ml/feature-importance')
    fi_success = resp['success']
    results.append(fi_success)

    if fi_success:
        features = resp['data'].get('features', [])
        print_result("Feature importance retrieved", True, f"{len(features)} features")
        # Show top 3 features
        for f in features[:3]:
            print(f"           - {f.get('name')}: {f.get('importance', 0):.3f}")
    else:
        print_result("Feature importance retrieved", False)

    # Step 4: Get strategy explanation
    print("\n  Step 4: Get Strategy Explanation")
    resp = api_request('/api/ml/strategy-explanation')
    se_success = resp['success']
    results.append(se_success)
    print_result("Strategy explanation", se_success)

    return all(results)


def test_wheel_cycle_flow():
    """Test Wheel Strategy cycle management"""
    print_header("WHEEL STRATEGY FLOW TEST")
    results = []

    # Step 1: Get wheel phases
    print("\n  Step 1: Get Wheel Phases")
    resp = api_request('/api/wheel/phases')
    phases_success = resp['success']
    results.append(phases_success)

    phases = resp['data'].get('data', {}).get('phases', [])
    print_result("Wheel phases retrieved", phases_success, f"{len(phases)} phases")

    # Step 2: Get active cycles
    print("\n  Step 2: Get Active Cycles")
    resp = api_request('/api/wheel/active')
    active_success = resp['success']
    results.append(active_success)

    active_cycles = resp['data'].get('data', [])
    print_result("Active cycles retrieved", active_success, f"{len(active_cycles)} active")

    # Step 3: Get wheel summary
    print("\n  Step 3: Get Wheel Summary")
    resp = api_request('/api/wheel/summary')
    summary_success = resp['success']
    results.append(summary_success)

    if summary_success:
        summary = resp['data'].get('data', {})
        print_result("Wheel summary retrieved", True,
                    f"Total cycles: {summary.get('total_cycles', 0)}, P&L: ${summary.get('total_realized_pnl', 0):.2f}")
    else:
        print_result("Wheel summary retrieved", False)

    # Step 4: Get completed cycles
    print("\n  Step 4: Get Completed Cycles")
    resp = api_request('/api/wheel/cycles?status=CALLED_AWAY')
    completed_success = resp['success']
    results.append(completed_success)

    completed = resp['data'].get('data', [])
    print_result("Completed cycles retrieved", completed_success, f"{len(completed)} called away")

    return all(results)


def test_trader_decision_flow():
    """Test Trading Bot decision logging"""
    print_header("TRADER DECISION FLOW TEST")
    results = []

    bots = ['ARES', 'ATLAS', 'PHOENIX', 'HERMES', 'ORACLE']

    # Check decision logs for each bot
    for bot in bots:
        resp = api_request(f'/api/logs/decisions?bot_name={bot}&limit=5')
        success = resp['success']
        results.append(success)

        logs = resp['data'].get('data', {}).get('decisions', [])
        print_result(f"{bot} decision logs", success, f"{len(logs)} logs")

    # Get overall trader status
    print("\n  Trader Status:")
    resp = api_request('/api/trader/status')
    trader_success = resp['success']
    results.append(trader_success)
    print_result("Trader status", trader_success)

    return all(results)


def test_gexis_conversation_flow():
    """Test GEXIS chatbot conversation flow"""
    print_header("GEXIS CONVERSATION FLOW TEST")
    results = []

    # Step 1: Check alerts
    print("\n  Step 1: Check Alerts")
    resp = api_request('/api/ai/gexis/alerts')
    alerts_success = resp['success']
    results.append(alerts_success)

    alert_count = resp['data'].get('count', 0)
    print_result("Alerts check", alerts_success, f"{alert_count} active alerts")

    # Step 2: Get conversation history
    print("\n  Step 2: Get Conversation History")
    resp = api_request('/api/ai/conversations?limit=10')
    conv_success = resp['success']
    results.append(conv_success)

    conversations = resp['data'].get('conversations', [])
    print_result("Conversation history", conv_success, f"{len(conversations)} conversations")

    # Step 3: Test command endpoint
    print("\n  Step 3: Test Command Endpoint")
    resp = api_request('/api/ai/gexis/command', method='POST', data={"command": "/status"})
    cmd_success = resp['success']
    results.append(cmd_success)
    print_result("Command endpoint", cmd_success)

    return all(results)


def test_backtest_data_flow():
    """Test KRONOS backtest data retrieval"""
    print_header("KRONOS BACKTEST FLOW TEST")
    results = []

    # Step 1: Get backtest jobs
    print("\n  Step 1: Get Backtest Jobs")
    resp = api_request('/api/zero-dte/jobs')
    jobs_success = resp['success']
    results.append(jobs_success)

    jobs = resp['data'].get('jobs', [])
    print_result("Backtest jobs retrieved", jobs_success, f"{len(jobs)} jobs")

    # Step 2: Get patterns
    print("\n  Step 2: Get Patterns")
    resp = api_request('/api/zero-dte/patterns')
    patterns_success = resp['success']
    results.append(patterns_success)

    patterns = resp['data'].get('patterns', [])
    print_result("Patterns retrieved", patterns_success, f"{len(patterns)} patterns")

    # Step 3: If we have jobs, get details for the latest one
    if jobs and len(jobs) > 0:
        print("\n  Step 3: Get Latest Job Details")
        latest_job = jobs[0]
        job_id = latest_job.get('job_id')
        if job_id:
            resp = api_request(f'/api/zero-dte/results/{job_id}')
            details_success = resp['success']
            results.append(details_success)
            print_result(f"Job {job_id[:8]}... details", details_success)

    return all(results)


def test_database_operations():
    """Test direct database operations"""
    print_header("DATABASE OPERATIONS TEST")
    results = []

    try:
        from database_adapter import get_connection, is_database_available

        # Check availability
        available = is_database_available()
        results.append(available)
        print_result("Database available", available)

        if not available:
            return False

        conn = get_connection()
        cursor = conn.cursor()

        # Test read operation
        print("\n  Read Operations:")
        tables_to_test = [
            ('gex_snapshots', 'GEX data'),
            ('decision_logs', 'Decision logs'),
            ('oracle_predictions', 'Oracle predictions'),
            ('wheel_cycles', 'Wheel cycles'),
        ]

        for table, description in tables_to_test:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                results.append(True)
                print_result(f"Read {description}", True, f"{count} records")
            except Exception as e:
                results.append(False)
                print_result(f"Read {description}", False, str(e))

        conn.close()
        return all(results)

    except ImportError as e:
        print_result("Database module import", False, str(e))
        return False
    except Exception as e:
        print_result("Database operations", False, str(e))
        return False


def test_environment_config():
    """Test environment configuration"""
    print_header("ENVIRONMENT CONFIGURATION TEST")
    results = []

    env_vars = [
        ('DATABASE_URL', True, 'Database connection'),
        ('ANTHROPIC_API_KEY', True, 'Claude API key'),
        ('POLYGON_API_KEY', False, 'Polygon market data'),
        ('TRADIER_ACCESS_TOKEN', False, 'Tradier trading API'),
        ('FRONTEND_URL', False, 'Frontend URL'),
    ]

    for var, required, description in env_vars:
        value = os.environ.get(var)
        is_set = bool(value)
        passed = is_set or not required
        results.append(passed)

        status_text = "Set" if is_set else ("NOT SET (required!)" if required else "Not set (optional)")
        print_result(f"{var}", passed, f"{description} - {status_text}")

    return all(results)


def main():
    """Run all integration tests"""
    print("\n" + "="*60)
    print("  ALPHAGEX INTEGRATION TEST SUITE")
    print(f"  API Base URL: {API_BASE_URL}")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)

    results = {
        "environment": test_environment_config(),
        "database": test_database_operations(),
        "oracle_flow": test_oracle_prediction_flow(),
        "pythia_flow": test_pythia_calibration_flow(),
        "prometheus_flow": test_ml_training_flow(),
        "wheel_flow": test_wheel_cycle_flow(),
        "trader_flow": test_trader_decision_flow(),
        "gexis_flow": test_gexis_conversation_flow(),
        "kronos_flow": test_backtest_data_flow(),
    }

    # Summary
    print_header("TEST SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        print_result(test_name.upper().replace('_', ' '), result)

    print(f"\n  Overall: {passed}/{total} integration tests passed")

    if passed == total:
        print("\n  ✅ All integration tests passed!")
        return 0
    elif passed >= total * 0.7:
        print("\n  ⚠️  Most tests passed. Check failures above.")
        return 1
    else:
        print("\n  ❌ Multiple critical failures. Review configuration.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
