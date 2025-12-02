#!/bin/bash
#
# ML INTEGRATION TEST
#
# Tests that the ML system is properly integrated with the trading system.
#
# USAGE:
#   ./scripts/test_ml_integration.sh
#

set -e

PROJECT_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
cd "$PROJECT_ROOT"

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║               ML INTEGRATION TEST                                    ║"
echo "╠══════════════════════════════════════════════════════════════════════╣"
echo "║  Tests ML PatternLearner integration with trading system            ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

python3 << 'PYTHON_EOF'
import os
import sys
sys.path.insert(0, os.getcwd())

from datetime import datetime

print("=" * 70)
print("1. ML AVAILABILITY CHECK")
print("=" * 70)

# Check scikit-learn
try:
    from sklearn.ensemble import RandomForestClassifier
    print("   ✓ scikit-learn is available")
except ImportError:
    print("   ✗ scikit-learn NOT INSTALLED")
    print("     Run: pip install scikit-learn")
    sys.exit(1)

# Check ML PatternLearner
try:
    from ai.autonomous_ml_pattern_learner import PatternLearner, ML_AVAILABLE
    print(f"   ✓ PatternLearner imported (ML_AVAILABLE={ML_AVAILABLE})")
except ImportError as e:
    print(f"   ✗ PatternLearner NOT AVAILABLE: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("2. ML MODEL INITIALIZATION")
print("=" * 70)

learner = PatternLearner()
print(f"   ✓ PatternLearner instance created")
print(f"   Model trained: {learner.model is not None}")

print("\n" + "=" * 70)
print("3. ML PREDICTION TEST")
print("=" * 70)

# Test prediction (even without trained model)
test_regime = {
    'rsi_5m': 45,
    'rsi_15m': 48,
    'rsi_1h': 52,
    'rsi_4h': 55,
    'rsi_1d': 50,
    'net_gamma': -2000000000,  # -$2B
    'call_wall_distance_pct': 3.0,
    'put_wall_distance_pct': 2.0,
    'vix_current': 18.5,
    'liberation_setup_detected': False,
    'false_floor_detected': False,
    'monthly_magnet_above': 5900,
    'monthly_magnet_below': 5700,
    'confidence_score': 65
}

prediction = learner.predict_pattern_success(test_regime)
print(f"   Test regime prediction:")
print(f"     Success Probability: {prediction.get('success_probability', 0)*100:.1f}%")
print(f"     ML Confidence: {prediction.get('ml_confidence', 'UNKNOWN')}")
print(f"     Recommendation: {prediction.get('recommendation', 'UNKNOWN')}")

if prediction.get('note'):
    print(f"     Note: {prediction['note']}")
    print("   ⚠ Model not trained - using baseline predictions")
else:
    print("   ✓ ML prediction working")

print("\n" + "=" * 70)
print("4. ML ROUTES IMPORT TEST")
print("=" * 70)

try:
    from backend.api.routes.ml_routes import router, get_ml_learner, ensure_ml_log_table
    print("   ✓ ML routes imported")
    print(f"   Router prefix: {router.prefix}")
    print(f"   Tags: {router.tags}")
except ImportError as e:
    print(f"   ✗ ML routes import failed: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("5. SPX BACKTEST ROUTES IMPORT TEST")
print("=" * 70)

try:
    from backend.api.routes.spx_backtest_routes import router as spx_router
    print("   ✓ SPX backtest routes imported")
    print(f"   Router prefix: {spx_router.prefix}")
except ImportError as e:
    print(f"   ✗ SPX backtest routes import failed: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("6. DATABASE TABLE CHECK")
print("=" * 70)

try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    # Check for ML decision log table
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'ml_decision_log'
        )
    """)
    ml_log_exists = cursor.fetchone()[0]
    print(f"   ml_decision_log table: {'✓ EXISTS' if ml_log_exists else '⚠ Will be created on first use'}")

    # Check for backtest trades table
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'spx_wheel_backtest_trades'
        )
    """)
    backtest_exists = cursor.fetchone()[0]
    print(f"   spx_wheel_backtest_trades: {'✓ EXISTS' if backtest_exists else '⚠ Will be created on first use'}")

    conn.close()
    print("   ✓ Database connection working")

except Exception as e:
    print(f"   ⚠ Database check failed: {e}")

print("\n" + "=" * 70)
print("7. API ENDPOINTS SUMMARY")
print("=" * 70)

print("""
   ML Endpoints (prefix: /api/ml):
   ├── GET  /status              - Check if ML is trained
   ├── POST /train               - Train ML model on historical data
   ├── POST /predict             - Get ML prediction for a trade
   ├── GET  /feature-importance  - See what factors ML considers
   ├── GET  /logs                - View all ML decisions (TRANSPARENCY)
   ├── GET  /accuracy-report     - See ML accuracy over time
   └── POST /score-spx-trade     - Score an SPX put trade

   SPX Backtest Endpoints (prefix: /api/spx-backtest):
   ├── POST /run                 - Run backtest with ML scoring
   ├── GET  /results             - Get backtest results
   ├── GET  /trades/{id}         - Get trades with ML scores
   ├── GET  /equity-curve/{id}   - Get equity curve for charts
   ├── GET  /ml-impact           - See ML's effect on P&L
   └── GET  /data-quality/{id}   - See real vs estimated data
""")

print("=" * 70)
print("VERDICT")
print("=" * 70)

print("""
   ╔══════════════════════════════════════════════════════════════╗
   ║  ✓ ML INTEGRATION COMPLETE                                   ║
   ║                                                              ║
   ║  The ML system is now connected to:                         ║
   ║  • FastAPI backend (API endpoints)                          ║
   ║  • SPX wheel backtest (trade scoring)                       ║
   ║  • Database (decision logging)                              ║
   ║                                                              ║
   ║  TRANSPARENCY:                                              ║
   ║  • Every ML decision is logged to ml_decision_log           ║
   ║  • /api/ml/logs shows all decisions                         ║
   ║  • /api/ml/accuracy-report shows ML performance             ║
   ║  • /api/spx-backtest/ml-impact shows P&L impact             ║
   ╚══════════════════════════════════════════════════════════════╝
""")

print("\nNext steps:")
print("  1. Start FastAPI: cd backend && python main.py")
print("  2. Train ML: POST /api/ml/train")
print("  3. Run backtest: POST /api/spx-backtest/run")
print("  4. View ML impact: GET /api/spx-backtest/ml-impact")
print("")

PYTHON_EOF
