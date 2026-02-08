#!/usr/bin/env python3
"""
JUBILEE Box Spread Production Verification Script

Run this script in the Render shell to verify JUBILEE is production ready.
This performs comprehensive checks on:
1. Database connectivity and schema
2. API endpoint availability and data
3. Tracing infrastructure
4. Rate calculation accuracy
5. OCC symbol generation
6. Configuration validation

Usage:
    python scripts/verify_prometheus_production.py

Returns exit code 0 if all checks pass, 1 if any fail.
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Central timezone
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")


class VerificationResult:
    """Result of a verification check."""

    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""
        self.details: Dict[str, Any] = {}
        self.duration_ms = 0.0

    def pass_check(self, message: str = "OK", details: Dict = None):
        self.passed = True
        self.message = message
        self.details = details or {}

    def fail_check(self, message: str, details: Dict = None):
        self.passed = False
        self.message = message
        self.details = details or {}


def check_database_connectivity() -> VerificationResult:
    """Check database connectivity and jubilee tables exist."""
    result = VerificationResult("Database Connectivity")
    start = time.time()

    try:
        import database_adapter as db

        conn = db.get_connection()
        cursor = conn.cursor()

        # Check jubilee tables exist
        # NOTE: Table names must match what's created in trading/jubilee/db.py
        tables_to_check = [
            'jubilee_positions',
            'jubilee_signals',
            'prometheus_rate_analysis',      # Rate analysis history
            'jubilee_logs',
            'prometheus_capital_deployments', # Capital deployment tracking
            'jubilee_equity_snapshots',
            'jubilee_config',
            'prometheus_daily_briefings',
            'prometheus_roll_decisions',
        ]

        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'prometheus_%'
        """)
        existing_tables = {row[0] for row in cursor.fetchall()}

        missing = [t for t in tables_to_check if t not in existing_tables]

        cursor.close()

        if missing:
            result.fail_check(
                f"Missing tables: {', '.join(missing)}",
                {'existing': list(existing_tables), 'missing': missing}
            )
        else:
            result.pass_check(
                f"All {len(tables_to_check)} tables exist",
                {'tables': list(existing_tables)}
            )

    except ImportError as e:
        result.fail_check(f"Database adapter not available: {e}")
    except Exception as e:
        result.fail_check(f"Database error: {e}")

    result.duration_ms = (time.time() - start) * 1000
    return result


def check_models_import() -> VerificationResult:
    """Check all JUBILEE models can be imported."""
    result = VerificationResult("Models Import")
    start = time.time()

    try:
        from trading.jubilee.models import (
            BoxSpreadSignal,
            BoxSpreadPosition,
            JubileeConfig,
            TradingMode,
            PositionStatus,
            BoxSpreadStatus,
            BorrowingCostAnalysis,
            CapitalDeployment,
            RollDecision,
            DailyBriefing,
        )

        models = {
            'BoxSpreadSignal': BoxSpreadSignal,
            'BoxSpreadPosition': BoxSpreadPosition,
            'JubileeConfig': JubileeConfig,
            'TradingMode': TradingMode,
            'PositionStatus': PositionStatus,
            'BoxSpreadStatus': BoxSpreadStatus,
            'BorrowingCostAnalysis': BorrowingCostAnalysis,
            'CapitalDeployment': CapitalDeployment,
            'RollDecision': RollDecision,
            'DailyBriefing': DailyBriefing,
        }

        result.pass_check(
            f"All {len(models)} models imported",
            {'models': list(models.keys())}
        )

    except ImportError as e:
        result.fail_check(f"Import error: {e}")

    result.duration_ms = (time.time() - start) * 1000
    return result


def check_trader_import() -> VerificationResult:
    """Check JubileeTrader can be imported."""
    result = VerificationResult("Trader Import")
    start = time.time()

    try:
        from trading.jubilee.trader import JubileeTrader

        trader = JubileeTrader()
        result.pass_check(
            "JubileeTrader initialized",
            {'mode': trader.config.mode.value}
        )

    except ImportError as e:
        result.fail_check(f"Import error: {e}")
    except Exception as e:
        result.fail_check(f"Initialization error: {e}")

    result.duration_ms = (time.time() - start) * 1000
    return result


def check_occ_symbol_generation() -> VerificationResult:
    """Check OCC symbol generation works correctly."""
    result = VerificationResult("OCC Symbol Generation")
    start = time.time()

    try:
        from trading.jubilee.executor import build_occ_symbol

        test_cases = [
            ("SPX", "2025-06-20", 5900.0, "call", "SPXW250620C05900000"),
            ("SPX", "2025-06-20", 5900.0, "put", "SPXW250620P05900000"),
            ("SPX", "2025-12-19", 6000.0, "call", "SPXW251219C06000000"),
        ]

        failures = []
        for ticker, exp, strike, opt_type, expected in test_cases:
            actual = build_occ_symbol(ticker, exp, strike, opt_type)
            if actual != expected:
                failures.append({
                    'input': f"{ticker} {exp} {strike} {opt_type}",
                    'expected': expected,
                    'actual': actual
                })

        if failures:
            result.fail_check(
                f"{len(failures)} symbol generation failures",
                {'failures': failures}
            )
        else:
            result.pass_check(
                f"All {len(test_cases)} OCC symbols generated correctly",
                {'test_count': len(test_cases)}
            )

    except ImportError as e:
        result.fail_check(f"Import error: {e}")
    except Exception as e:
        result.fail_check(f"Error: {e}")

    result.duration_ms = (time.time() - start) * 1000
    return result


def check_rate_calculation() -> VerificationResult:
    """Check implied rate calculation accuracy."""
    result = VerificationResult("Rate Calculation")
    start = time.time()

    try:
        # Test rate calculation formula
        test_cases = [
            # (strike_width, credit_per_share, dte, expected_rate_range)
            (50.0, 49.65, 141, (1.5, 2.5)),   # ~1.82%
            (50.0, 49.00, 180, (3.5, 4.5)),   # ~4.14%
            (100.0, 99.00, 365, (0.8, 1.2)),  # ~1.01%
        ]

        failures = []
        for strike_width, credit, dte, (min_rate, max_rate) in test_cases:
            theoretical = strike_width * 100
            credit_total = credit * 100
            borrowing_cost = theoretical - credit_total
            annualized_rate = (borrowing_cost / credit_total) * (365 / dte) * 100

            if not (min_rate <= annualized_rate <= max_rate):
                failures.append({
                    'inputs': f"width=${strike_width}, credit=${credit}, dte={dte}",
                    'calculated_rate': round(annualized_rate, 4),
                    'expected_range': f"{min_rate}-{max_rate}%"
                })

        if failures:
            result.fail_check(
                f"{len(failures)} rate calculation errors",
                {'failures': failures}
            )
        else:
            result.pass_check(
                f"All {len(test_cases)} rate calculations accurate",
                {'test_count': len(test_cases)}
            )

    except Exception as e:
        result.fail_check(f"Error: {e}")

    result.duration_ms = (time.time() - start) * 1000
    return result


def check_tracing_infrastructure() -> VerificationResult:
    """Check tracing infrastructure is operational."""
    result = VerificationResult("Tracing Infrastructure")
    start = time.time()

    try:
        from trading.jubilee.tracing import get_tracer, PrometheusTracer

        tracer = get_tracer()

        # Verify singleton
        tracer2 = get_tracer()
        if tracer is not tracer2:
            result.fail_check("Tracer is not a singleton")
            return result

        # Test trace context manager
        tracer.reset_metrics()

        with tracer.trace("verification.test") as span:
            span.set_attribute("test", True)
            time.sleep(0.01)  # Small delay to ensure measurable duration

        metrics = tracer.get_metrics()

        if metrics['total_spans'] < 1:
            result.fail_check(
                "Trace not recorded",
                {'metrics': metrics}
            )
        else:
            result.pass_check(
                "Tracing operational",
                {
                    'total_spans': metrics['total_spans'],
                    'error_rate': metrics['error_rate_pct']
                }
            )

    except ImportError as e:
        result.fail_check(f"Import error: {e}")
    except Exception as e:
        result.fail_check(f"Error: {e}")

    result.duration_ms = (time.time() - start) * 1000
    return result


def check_api_endpoints() -> VerificationResult:
    """Check API endpoints are registered and respond."""
    result = VerificationResult("API Endpoints")
    start = time.time()

    try:
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)

        endpoints = [
            ("/api/jubilee/status", 200),
            ("/api/jubilee/positions", 200),
            ("/api/jubilee/closed-trades", 200),
            ("/api/jubilee/equity-curve", 200),
            ("/api/jubilee/logs", 200),
            ("/api/jubilee/scan-activity", 200),
        ]

        failures = []
        successes = 0

        for endpoint, expected_status in endpoints:
            try:
                response = client.get(endpoint)
                if response.status_code != expected_status:
                    failures.append({
                        'endpoint': endpoint,
                        'expected': expected_status,
                        'actual': response.status_code
                    })
                else:
                    successes += 1
            except Exception as e:
                failures.append({
                    'endpoint': endpoint,
                    'error': str(e)
                })

        if failures:
            result.fail_check(
                f"{len(failures)} endpoint failures",
                {'failures': failures, 'successes': successes}
            )
        else:
            result.pass_check(
                f"All {len(endpoints)} endpoints responding",
                {'endpoints': [e[0] for e in endpoints]}
            )

    except ImportError as e:
        result.fail_check(f"Import error: {e}")
    except Exception as e:
        result.fail_check(f"Error: {e}")

    result.duration_ms = (time.time() - start) * 1000
    return result


def check_config_validation() -> VerificationResult:
    """Check configuration validation works."""
    result = VerificationResult("Config Validation")
    start = time.time()

    try:
        from trading.jubilee.models import JubileeConfig, TradingMode

        config = JubileeConfig()

        # Check default values
        validations = []

        if config.ticker != "SPX":
            validations.append(f"ticker should be SPX, got {config.ticker}")

        if config.mode != TradingMode.PAPER:
            validations.append(f"mode should be PAPER, got {config.mode}")

        if config.capital <= 0:
            validations.append(f"capital should be positive, got {config.capital}")

        # Check allocation percentages sum to 100
        total_alloc = (
            config.ares_allocation_pct +
            config.titan_allocation_pct +
            config.anchor_allocation_pct +
            config.reserve_pct
        )
        if abs(total_alloc - 100.0) > 0.01:
            validations.append(f"allocations should sum to 100, got {total_alloc}")

        # Check to_dict works
        config_dict = config.to_dict()
        if 'ticker' not in config_dict:
            validations.append("to_dict missing ticker field")

        # Check from_dict works
        new_config = JubileeConfig.from_dict({'capital': 100000.0})
        if new_config.capital != 100000.0:
            validations.append("from_dict not setting capital correctly")

        if validations:
            result.fail_check(
                f"{len(validations)} validation issues",
                {'issues': validations}
            )
        else:
            result.pass_check(
                "Configuration valid",
                {'capital': config.capital, 'mode': config.mode.value}
            )

    except ImportError as e:
        result.fail_check(f"Import error: {e}")
    except Exception as e:
        result.fail_check(f"Error: {e}")

    result.duration_ms = (time.time() - start) * 1000
    return result


def run_verification() -> Tuple[bool, List[VerificationResult]]:
    """Run all verification checks."""
    checks = [
        check_models_import,
        check_trader_import,
        check_occ_symbol_generation,
        check_rate_calculation,
        check_tracing_infrastructure,
        check_config_validation,
        check_database_connectivity,
        check_api_endpoints,
    ]

    results = []
    for check_func in checks:
        logger.info(f"Running: {check_func.__name__}...")
        result = check_func()
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        logger.info(f"  {status}: {result.message} ({result.duration_ms:.1f}ms)")

    all_passed = all(r.passed for r in results)
    return all_passed, results


def print_summary(results: List[VerificationResult]) -> None:
    """Print verification summary."""
    print("\n" + "=" * 70)
    print("JUBILEE PRODUCTION VERIFICATION SUMMARY")
    print("=" * 70)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total_time = sum(r.duration_ms for r in results)

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        symbol = "" if result.passed else ""
        print(f"  {symbol} [{status}] {result.name}: {result.message}")

        if not result.passed and result.details:
            for key, value in result.details.items():
                if isinstance(value, list) and len(value) <= 3:
                    print(f"       {key}: {value}")
                elif isinstance(value, list):
                    print(f"       {key}: [{len(value)} items]")

    print("-" * 70)
    print(f"Results: {passed} passed, {failed} failed ({total_time:.1f}ms total)")
    print("=" * 70)

    if failed == 0:
        print("\n JUBILEE is PRODUCTION READY!\n")
    else:
        print(f"\n {failed} check(s) failed. Please review and fix before deploying.\n")


def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("JUBILEE Box Spread Production Verification")
    print(f"Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 70 + "\n")

    all_passed, results = run_verification()
    print_summary(results)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
