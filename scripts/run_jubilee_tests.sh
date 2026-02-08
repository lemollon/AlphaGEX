#!/bin/bash
# =============================================================================
# JUBILEE Box Spread Tests Runner
# =============================================================================
# Run this script in the Render shell to verify JUBILEE functionality.
#
# Usage:
#   chmod +x scripts/run_prometheus_tests.sh
#   ./scripts/run_prometheus_tests.sh
#
# Or run individual test files:
#   pytest tests/test_jubilee.py -v
#   pytest backend/tests/test_jubilee_routes.py -v
# =============================================================================

echo "========================================"
echo "JUBILEE Box Spread Test Suite"
echo "========================================"
echo ""

# Unit tests for business logic
echo "[1/2] Running Unit Tests (tests/test_jubilee.py)..."
echo "----------------------------------------"
python -m pytest tests/test_jubilee.py -v --tb=short
UNIT_RESULT=$?
echo ""

# API integration tests
echo "[2/2] Running API Integration Tests (backend/tests/test_jubilee_routes.py)..."
echo "----------------------------------------"
python -m pytest backend/tests/test_jubilee_routes.py -v --tb=short
API_RESULT=$?
echo ""

echo "========================================"
echo "Test Results Summary"
echo "========================================"
if [ $UNIT_RESULT -eq 0 ]; then
    echo "Unit Tests:       PASSED"
else
    echo "Unit Tests:       FAILED"
fi

if [ $API_RESULT -eq 0 ]; then
    echo "Integration Tests: PASSED"
else
    echo "Integration Tests: FAILED"
fi

echo ""
echo "Test files created:"
echo "  - tests/test_jubilee.py (27 unit tests)"
echo "  - backend/tests/test_jubilee_routes.py (25 integration tests)"
echo ""
echo "Per STANDARDS.md requirements:"
echo "  - Unit tests cover: models, OCC symbols, rate calculations, enums"
echo "  - Integration tests cover: all required API endpoints"
echo "    (/status, /positions, /closed-trades, /equity-curve, /logs, /scan-activity)"
echo ""

# Exit with failure if any tests failed
if [ $UNIT_RESULT -ne 0 ] || [ $API_RESULT -ne 0 ]; then
    exit 1
fi

exit 0
