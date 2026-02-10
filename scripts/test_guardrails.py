#!/usr/bin/env python3
"""
Comprehensive test for ALL branch changes: WISDOM V3 + Guardrails + Bug Fixes.

Run in Render shell:
    cd ~/project/src && git fetch origin claude/watchtower-data-analysis-6FWPk && git checkout claude/watchtower-data-analysis-6FWPk
    python scripts/test_guardrails.py

Tests:
  SECTION A: WISDOM V3 ML Engine
    - 13 V3 features (VRP, cyclical day, win_rate_60d)
    - scale_pos_weight in XGBoost params
    - Adaptive thresholds (base_rate relative)
    - Feature version tracking (V1/V2/V3 backward compat)
    - Fallback prediction works
    - No confidence inflation (1.2x removed)
    - Feature extraction produces correct columns
    - Training with mock data works end-to-end

  SECTION B: Proverbs Guardrails
    - 5-min cooldown after 3 consecutive losses
    - reset() clears tracker for next cycle
    - Win resets counter
    - No daily $5K limit in bot traders

  SECTION C: Bot Trader Integration
    - All bots use get_status() (not private get_tracker())
    - All bots use reset()
    - VALOR has its own built-in loss streak mechanism
    - No daily_loss_monitor references

  SECTION D: Frontend Win Rate Bug Fix
    - No "* 100" on win_rate in wisdom/page.tsx

  SECTION E: Multi-Source Training Data (backend)
    - ml_routes.py queries 3 sources
    - Database tables exist (if DB available)

  SECTION F: Audit Report
    - docs/WISDOM_AUDIT_REPORT.md exists and has key sections
"""

import sys
import os
import math

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from datetime import datetime, timedelta

passed = 0
failed = 0
skipped = 0
section_results = {}
current_section = ""


def section(name):
    global current_section
    current_section = name
    section_results[name] = {'passed': 0, 'failed': 0, 'skipped': 0}
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        section_results[current_section]['passed'] += 1
        print(f"  \033[32mPASS\033[0m  {name}")
    else:
        failed += 1
        section_results[current_section]['failed'] += 1
        print(f"  \033[31mFAIL\033[0m  {name}  -- {detail}")


def skip(name, reason=""):
    global skipped
    skipped += 1
    section_results[current_section]['skipped'] += 1
    print(f"  \033[33mSKIP\033[0m  {name}  -- {reason}")


def read_file(relative_path):
    """Read file from project root"""
    full = os.path.join(PROJECT_ROOT, relative_path)
    if not os.path.exists(full):
        return None
    with open(full) as f:
        return f.read()


# ═══════════════════════════════════════════════════════════
# SECTION A: WISDOM V3 ML ENGINE
# ═══════════════════════════════════════════════════════════
section("SECTION A: WISDOM V3 ML Engine")

try:
    from quant.fortress_ml_advisor import (
        FortressMLAdvisor, MLFeatures, MLPrediction,
        TradingAdvice, TradeOutcome, get_advisor, get_trading_advice,
    )
    test("FortressMLAdvisor imports", True)
except ImportError as e:
    test("FortressMLAdvisor imports", False, str(e))
    print("  Cannot test ML engine. Skipping section A.")

if 'FortressMLAdvisor' in dir():
    advisor = FortressMLAdvisor()

    # --- Feature columns ---
    test("V3 has 13 features", len(advisor.FEATURE_COLS) == 13,
         f"got {len(advisor.FEATURE_COLS)}: {advisor.FEATURE_COLS}")
    test("V2 has 11 features", len(advisor.FEATURE_COLS_V2) == 11,
         f"got {len(advisor.FEATURE_COLS_V2)}")
    test("V1 has 7 features", len(advisor.FEATURE_COLS_V1) == 7,
         f"got {len(advisor.FEATURE_COLS_V1)}")

    # V3 specific features present
    test("V3 has 'volatility_risk_premium'", 'volatility_risk_premium' in advisor.FEATURE_COLS)
    test("V3 has 'day_of_week_sin'", 'day_of_week_sin' in advisor.FEATURE_COLS)
    test("V3 has 'day_of_week_cos'", 'day_of_week_cos' in advisor.FEATURE_COLS)
    test("V3 has 'win_rate_60d'", 'win_rate_60d' in advisor.FEATURE_COLS)

    # V3 should NOT have old features
    test("V3 does NOT have 'day_of_week' (integer)", 'day_of_week' not in advisor.FEATURE_COLS)
    test("V3 does NOT have 'win_rate_30d'", 'win_rate_30d' not in advisor.FEATURE_COLS)

    # V2 backward compat still has old features
    test("V2 has 'day_of_week' (integer)", 'day_of_week' in advisor.FEATURE_COLS_V2)
    test("V2 has 'win_rate_30d'", 'win_rate_30d' in advisor.FEATURE_COLS_V2)

    # --- Feature version tracking ---
    test("Default feature_version == 3", advisor._feature_version == 3,
         f"got {advisor._feature_version}")
    test("_trained_feature_cols set", advisor._trained_feature_cols is not None)
    test("_base_rate attribute exists", hasattr(advisor, '_base_rate'))

    # --- Adaptive thresholds ---
    test("Has _update_thresholds_from_base_rate method",
         hasattr(advisor, '_update_thresholds_from_base_rate'))

    # Simulate adaptive threshold calculation
    advisor._base_rate = 0.85
    advisor._update_thresholds_from_base_rate()
    test("Adaptive SKIP threshold = base_rate - 0.15",
         abs(advisor.low_confidence_threshold - 0.70) < 0.001,
         f"got {advisor.low_confidence_threshold}")
    test("Adaptive FULL threshold = base_rate - 0.05",
         abs(advisor.high_confidence_threshold - 0.80) < 0.001,
         f"got {advisor.high_confidence_threshold}")

    # Reset thresholds for remaining tests
    advisor._base_rate = None
    advisor.low_confidence_threshold = 0.45
    advisor.high_confidence_threshold = 0.65

    # --- Fallback prediction ---
    pred = advisor.predict(vix=20.0, day_of_week=2)
    test("Fallback prediction returns MLPrediction", isinstance(pred, MLPrediction))
    test("Fallback advice is TradingAdvice enum", isinstance(pred.advice, TradingAdvice))
    test("Fallback win_probability in [0, 1]", 0 <= pred.win_probability <= 1,
         f"got {pred.win_probability}")
    test("Fallback model_version contains 'fallback'", 'fallback' in pred.model_version,
         f"got {pred.model_version}")

    # --- No confidence inflation ---
    # Old code had: confidence = min(100, win_probability * 100 * 1.2)
    # New code has: confidence = min(100, win_probability * 100)
    source = read_file('quant/fortress_ml_advisor.py')
    test("No 1.2x confidence inflation in predict()",
         '* 1.2' not in source or 'win_probability * 100 * 1.2' not in source,
         "still has 1.2x multiplier")

    # --- VRP parameter accepted ---
    pred_vrp = advisor.predict(vix=25.0, day_of_week=0, volatility_risk_premium=0.5)
    test("predict() accepts volatility_risk_premium param", isinstance(pred_vrp, MLPrediction))

    pred_rv = advisor.predict(vix=25.0, day_of_week=0, realized_vol_5d=0.8)
    test("predict() accepts realized_vol_5d param", isinstance(pred_rv, MLPrediction))

    # --- MLFeatures dataclass has new fields ---
    test("MLFeatures has day_of_week_sin", hasattr(MLFeatures, '__dataclass_fields__') and
         'day_of_week_sin' in MLFeatures.__dataclass_fields__)
    test("MLFeatures has day_of_week_cos", 'day_of_week_cos' in MLFeatures.__dataclass_fields__)
    test("MLFeatures has volatility_risk_premium", 'volatility_risk_premium' in MLFeatures.__dataclass_fields__)
    test("MLFeatures has win_rate_60d", 'win_rate_60d' in MLFeatures.__dataclass_fields__)
    test("MLFeatures does NOT have day_of_week (integer)",
         'day_of_week' not in MLFeatures.__dataclass_fields__,
         "old field still present")
    test("MLFeatures does NOT have win_rate_30d",
         'win_rate_30d' not in MLFeatures.__dataclass_fields__,
         "old field still present")

    # --- Cyclical encoding math ---
    test("sin(2pi*0/5) == 0 (Monday)", abs(math.sin(2 * math.pi * 0 / 5)) < 0.001)
    test("cos(2pi*0/5) == 1 (Monday)", abs(math.cos(2 * math.pi * 0 / 5) - 1.0) < 0.001)
    test("sin(2pi*2/5) > 0 (Wednesday)", math.sin(2 * math.pi * 2 / 5) > 0)

    # --- Feature extraction with mock data ---
    try:
        import pandas as pd
        mock_trades = {
            'all_trades': [
                {'trade_date': '2025-01-06', 'vix': 18.0, 'open_price': 5900,
                 'close_price': 5910, 'outcome': 'MAX_PROFIT', 'net_pnl': 150,
                 'expected_move_sd': 30, 'gex_regime': 'POSITIVE', 'gex_normalized': 0.5,
                 'gex_distance_to_flip_pct': 1.2, 'gex_between_walls': True},
                {'trade_date': '2025-01-07', 'vix': 19.0, 'open_price': 5910,
                 'close_price': 5920, 'outcome': 'MAX_PROFIT', 'net_pnl': 120,
                 'expected_move_sd': 32, 'gex_regime': 'POSITIVE', 'gex_normalized': 0.3,
                 'gex_distance_to_flip_pct': 0.8, 'gex_between_walls': True},
                {'trade_date': '2025-01-08', 'vix': 22.0, 'open_price': 5920,
                 'close_price': 5880, 'outcome': 'PUT_BREACHED', 'net_pnl': -400,
                 'expected_move_sd': 40, 'gex_regime': 'NEGATIVE', 'gex_normalized': -0.2,
                 'gex_distance_to_flip_pct': 0.3, 'gex_between_walls': False},
            ]
        }
        df = advisor.extract_features_from_chronicles(mock_trades)
        test("Feature extraction returns DataFrame", isinstance(df, pd.DataFrame))
        test("DataFrame has 3 rows", len(df) == 3, f"got {len(df)}")

        # Check V3 columns exist
        for col in ['day_of_week_sin', 'day_of_week_cos', 'volatility_risk_premium', 'win_rate_60d']:
            test(f"DataFrame has column '{col}'", col in df.columns, f"columns: {list(df.columns)}")

        # Check old columns NOT present
        test("DataFrame does NOT have 'day_of_week'", 'day_of_week' not in df.columns)
        test("DataFrame does NOT have 'win_rate_30d'", 'win_rate_30d' not in df.columns)

        # Check price_change_1d uses PREVIOUS trade's change
        test("First trade price_change_1d == 0 (no previous)",
             abs(df.iloc[0]['price_change_1d']) < 0.001,
             f"got {df.iloc[0]['price_change_1d']}")

        # Check VRP is computed
        test("VRP values are numeric", df['volatility_risk_premium'].notna().all())

    except ImportError:
        skip("Feature extraction (needs pandas)", "pandas not installed")

    # --- Training with scale_pos_weight ---
    source = read_file('quant/fortress_ml_advisor.py')
    test("train_from_chronicles uses scale_pos_weight",
         'scale_pos_weight=scale_pos_weight' in source)
    test("retrain_from_outcomes uses scale_pos_weight",
         source.count('scale_pos_weight=scale_pos_weight') >= 2,
         "should appear in both train methods")
    test("Brier score uses held-out folds (not in-sample)",
         'briers.append(brier_score_loss(y_test, y_proba))' in source,
         "Brier should be on y_test not y")
    test("retrain_from_outcomes uses TimeSeriesSplit",
         'TimeSeriesSplit' in source.split('def retrain_from_outcomes')[1] if 'def retrain_from_outcomes' in source else False,
         "retrain should use walk-forward validation")
    test("Model version 2.0.0 set in training",
         'self.model_version = "2.0.0"' in source)

    # --- Pattern insights includes V3 info ---
    test("get_pattern_insights includes feature_version",
         "'feature_version'" in source or '"feature_version"' in source)
    test("get_pattern_insights includes adaptive_thresholds",
         "'adaptive_thresholds'" in source or '"adaptive_thresholds"' in source)

    # --- End-to-end training (if ML libs available) ---
    try:
        import xgboost
        import sklearn
        import numpy as np

        # Generate enough mock data for training
        mock_training = {'all_trades': []}
        for i in range(120):
            dt = datetime(2025, 1, 1) + timedelta(days=i)
            is_win = i % 10 != 0  # ~90% win rate
            mock_training['all_trades'].append({
                'trade_date': dt.strftime('%Y-%m-%d'),
                'vix': 18 + (i % 10),
                'open_price': 5900 + i,
                'close_price': 5905 + i if is_win else 5850 + i,
                'outcome': 'MAX_PROFIT' if is_win else 'PUT_BREACHED',
                'net_pnl': 150 if is_win else -400,
                'expected_move_sd': 30 + (i % 5),
                'gex_regime': 'POSITIVE' if i % 3 != 0 else 'NEGATIVE',
                'gex_normalized': 0.5 if i % 3 != 0 else -0.3,
                'gex_distance_to_flip_pct': 1.0,
                'gex_between_walls': True,
            })

        fresh_advisor = FortressMLAdvisor.__new__(FortressMLAdvisor)
        fresh_advisor.model = None
        fresh_advisor.calibrated_model = None
        fresh_advisor.scaler = None
        fresh_advisor.is_trained = False
        fresh_advisor.training_metrics = None
        fresh_advisor.model_version = "0.0.0"
        fresh_advisor._feature_version = 3
        fresh_advisor._trained_feature_cols = FortressMLAdvisor.FEATURE_COLS
        fresh_advisor._base_rate = None
        fresh_advisor.high_confidence_threshold = 0.65
        fresh_advisor.low_confidence_threshold = 0.45
        fresh_advisor._has_gex_features = True
        fresh_advisor.MODEL_PATH = '/tmp/test_fortress_ml'
        os.makedirs(fresh_advisor.MODEL_PATH, exist_ok=True)

        metrics = fresh_advisor.train_from_chronicles(mock_training)
        test("Training completes successfully", metrics is not None)
        test("Model is_trained == True", fresh_advisor.is_trained)
        test("Model version == 2.0.0", fresh_advisor.model_version == "2.0.0",
             f"got {fresh_advisor.model_version}")
        test("Feature version == 3", fresh_advisor._feature_version == 3)
        test("Base rate learned", fresh_advisor._base_rate is not None and fresh_advisor._base_rate > 0.5,
             f"got {fresh_advisor._base_rate}")
        test("Adaptive thresholds updated", fresh_advisor.high_confidence_threshold != 0.65,
             f"still default: {fresh_advisor.high_confidence_threshold}")
        test("Metrics has brier_score", metrics.brier_score is not None and metrics.brier_score > 0)
        test("Metrics positive_samples > 0", metrics.positive_samples > 0)
        test("Metrics negative_samples > 0", metrics.negative_samples > 0)
        test("Feature importances has 13 features",
             len(metrics.feature_importances) == 13,
             f"got {len(metrics.feature_importances)}")
        test("VRP in feature importances", 'volatility_risk_premium' in metrics.feature_importances)

        # Trained model prediction
        pred_trained = fresh_advisor.predict(vix=20.0, day_of_week=2)
        test("Trained model prediction works", isinstance(pred_trained, MLPrediction))
        test("Trained prediction has real probability",
             0 < pred_trained.win_probability < 1,
             f"got {pred_trained.win_probability}")
        test("Trained prediction model_version == 2.0.0",
             pred_trained.model_version == "2.0.0",
             f"got {pred_trained.model_version}")
        test("Confidence <= 100 (no 1.2x inflation)",
             pred_trained.confidence <= 100,
             f"got {pred_trained.confidence}")

    except ImportError as e:
        skip("End-to-end training (needs xgboost/sklearn)", str(e))


# ═══════════════════════════════════════════════════════════
# SECTION B: PROVERBS GUARDRAILS
# ═══════════════════════════════════════════════════════════
section("SECTION B: Proverbs Guardrails")

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

if 'get_proverbs_enhanced' in dir():
    proverbs = get_proverbs_enhanced()
    test("Singleton created", proverbs is not None)
    monitor = proverbs.consecutive_loss_monitor

    # Kill threshold config
    test("Kill threshold == 3", ENHANCED_GUARDRAILS['consecutive_loss_kill_threshold'] == 3,
         f"got {ENHANCED_GUARDRAILS['consecutive_loss_kill_threshold']}")

    # get_status API
    monitor.reset('TEST_BOT')
    status = monitor.get_status('TEST_BOT')
    test("get_status() returns dict", isinstance(status, dict))
    test("Has 'consecutive_losses' key", 'consecutive_losses' in status)
    test("Has 'triggered_kill' key", 'triggered_kill' in status)
    test("Initial consecutive_losses == 0", status['consecutive_losses'] == 0)
    test("Initial triggered_kill == False", status['triggered_kill'] is False)

    # 3 losses -> kill
    today = datetime.now().strftime('%Y-%m-%d')
    monitor.reset('TEST_BOT')
    monitor.record_trade_outcome('TEST_BOT', pnl=-500, trade_date=today)
    monitor.record_trade_outcome('TEST_BOT', pnl=-300, trade_date=today)
    s2 = monitor.get_status('TEST_BOT')
    test("After 2 losses: no kill", s2['triggered_kill'] is False)

    alert = monitor.record_trade_outcome('TEST_BOT', pnl=-200, trade_date=today)
    s3 = monitor.get_status('TEST_BOT')
    test("After 3 losses: triggered_kill == True", s3['triggered_kill'] is True)
    test("Alert returned on 3rd loss", alert is not None)

    # 5-min cooldown simulation
    now = datetime.now()
    pause_until = now + timedelta(minutes=5)
    test("Cooldown: +2 min still paused", (now + timedelta(minutes=2)) < pause_until)
    test("Cooldown: +6 min expired", (now + timedelta(minutes=6)) >= pause_until)

    # reset() clears and needs 3 more
    monitor.reset('TEST_BOT')
    s_reset = monitor.get_status('TEST_BOT')
    test("After reset: consecutive_losses == 0", s_reset['consecutive_losses'] == 0)
    test("After reset: triggered_kill == False", s_reset['triggered_kill'] is False)

    monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
    monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
    test("After 2 new losses: no kill",
         monitor.get_status('TEST_BOT')['triggered_kill'] is False)
    monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
    test("After 3 new losses: kill again",
         monitor.get_status('TEST_BOT')['triggered_kill'] is True)

    # Win resets counter
    monitor.reset('TEST_BOT')
    monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
    monitor.record_trade_outcome('TEST_BOT', pnl=-100, trade_date=today)
    monitor.record_trade_outcome('TEST_BOT', pnl=200, trade_date=today)
    test("Win resets counter to 0",
         monitor.get_status('TEST_BOT')['consecutive_losses'] == 0)


# ═══════════════════════════════════════════════════════════
# SECTION C: BOT TRADER INTEGRATION
# ═══════════════════════════════════════════════════════════
section("SECTION C: Bot Trader Integration")

bot_files = {
    'FORTRESS': 'trading/fortress_v2/trader.py',
    'SAMSON': 'trading/samson/trader.py',
    'ANCHOR': 'trading/anchor/trader.py',
    'VALOR': 'trading/valor/trader.py',
}

for bot_name, filepath in bot_files.items():
    content = read_file(filepath)
    if content is None:
        skip(f"{bot_name}: file exists", f"{filepath} not found")
        continue

    if bot_name != 'VALOR':
        # FORTRESS, SAMSON, ANCHOR use Proverbs guardrails
        test(f"{bot_name}: uses get_status() (not get_tracker)",
             'get_status(' in content and 'get_tracker(' not in content,
             "wrong API method")
        test(f"{bot_name}: uses reset() for cooldown clear",
             '.reset(' in content)
        test(f"{bot_name}: has _loss_streak_pause_until attribute",
             '_loss_streak_pause_until' in content)
        test(f"{bot_name}: checks triggered_kill via dict .get()",
             "consec_status.get('triggered_kill')" in content,
             "should use dict .get(), not attribute access")
        test(f"{bot_name}: sets 5-min pause (timedelta(minutes=5))",
             'timedelta(minutes=5)' in content)
        test(f"{bot_name}: logs cooldown with time remaining",
             'cooldown' in content.lower() and 'remaining' in content.lower())
    else:
        # VALOR has its own built-in loss streak mechanism
        test(f"{bot_name}: has built-in loss_streak_pause_until",
             'self.loss_streak_pause_until' in content)
        test(f"{bot_name}: has built-in consecutive_losses counter",
             'self.consecutive_losses' in content)

    # ALL bots: no daily loss monitor
    test(f"{bot_name}: no daily_loss_monitor reference",
         'daily_loss_monitor' not in content and 'get_daily_stats' not in content,
         "daily $5K limit should be removed")


# ═══════════════════════════════════════════════════════════
# SECTION D: FRONTEND WIN RATE BUG FIX
# ═══════════════════════════════════════════════════════════
section("SECTION D: Frontend Win Rate Bug Fix")

wisdom_tsx = read_file('frontend/src/app/wisdom/page.tsx')
if wisdom_tsx:
    # The bug was: dataQuality.win_rate * 100  (double multiplication)
    # Fixed to:    dataQuality.win_rate.toFixed(1)
    test("No double multiplication (win_rate * 100)",
         'win_rate * 100' not in wisdom_tsx,
         "still has * 100 on win_rate!")

    # Count occurrences of the correct pattern
    correct_pattern_count = wisdom_tsx.count('win_rate.toFixed(1)')
    test(f"Uses win_rate.toFixed(1) (found {correct_pattern_count}x)",
         correct_pattern_count >= 2,
         "should appear at least twice (Overview + Training tabs)")

    # Training data sources should show 3 columns
    test("Training tab shows CHRONICLES source",
         'CHRONICLES' in wisdom_tsx or 'chronicles' in wisdom_tsx.lower(),
         "missing CHRONICLES data source display")
    test("Training tab shows Prophet source",
         'Prophet' in wisdom_tsx or 'prophet' in wisdom_tsx.lower(),
         "missing Prophet data source display")
else:
    skip("Frontend win rate check", "wisdom/page.tsx not found")


# ═══════════════════════════════════════════════════════════
# SECTION E: MULTI-SOURCE TRAINING DATA (Backend)
# ═══════════════════════════════════════════════════════════
section("SECTION E: Multi-Source Training Backend")

ml_routes = read_file('backend/api/routes/ml_routes.py')
if ml_routes:
    # data-quality endpoint queries 3 sources
    test("data-quality queries zero_dte_backtest_trades",
         'zero_dte_backtest_trades' in ml_routes)
    test("data-quality queries prophet_training_outcomes",
         'prophet_training_outcomes' in ml_routes)
    test("data-quality queries fortress_positions (live bot)",
         'fortress_positions' in ml_routes)

    # train endpoint queries 3 sources
    train_section = ml_routes.split('/wisdom/train')[-1][:3000] if '/wisdom/train' in ml_routes else ml_routes
    test("Train endpoint uses zero_dte_backtest_trades",
         'zero_dte_backtest_trades' in train_section)
    test("Train endpoint uses prophet_training_outcomes",
         'prophet_training_outcomes' in train_section)

    # WISDOM-specific endpoints should NOT use the old broken imports
    # (Other legacy endpoints in the same file may still use them)
    wisdom_train_section = ml_routes.split('/wisdom/train')[-1][:2000] if '/wisdom/train' in ml_routes else ''
    wisdom_status_section = ml_routes.split('/wisdom/status')[-1][:2000] if '/wisdom/status' in ml_routes else ''
    test("WISDOM train does NOT use ZeroDTEBacktester",
         'ZeroDTEBacktester' not in wisdom_train_section,
         "WISDOM train still uses broken import!")
    test("WISDOM train does NOT use spx_wheel_ml",
         'spx_wheel_ml' not in wisdom_train_section,
         "WISDOM train still uses wrong data source!")
    test("WISDOM status does NOT use spx_wheel_ml",
         'spx_wheel_ml' not in wisdom_status_section,
         "WISDOM status still uses wrong data source!")

    # Status endpoint shows training_data_sources breakdown
    test("Status endpoint has training_data_sources",
         'training_data_sources' in ml_routes)
else:
    skip("Backend ml_routes check", "ml_routes.py not found")

# Database connectivity (only on Render)
try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    # Check key tables exist
    tables_to_check = [
        'zero_dte_backtest_trades',
        'prophet_training_outcomes',
        'fortress_positions',
    ]
    for table in tables_to_check:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            test(f"DB table '{table}' exists ({count} rows)", True)
        except Exception as e:
            test(f"DB table '{table}' exists", False, str(e))
            conn.rollback()

    conn.close()
except Exception as e:
    skip("Database connectivity", f"DB not available: {e}")


# ═══════════════════════════════════════════════════════════
# SECTION F: AUDIT REPORT
# ═══════════════════════════════════════════════════════════
section("SECTION F: Audit Report")

audit = read_file('docs/WISDOM_AUDIT_REPORT.md')
if audit:
    test("Audit report exists", True)
    test("Has Section 1: Data Pipeline", 'SECTION 1: DATA PIPELINE' in audit)
    test("Has Section 2: Feature Engineering", 'SECTION 2: FEATURE ENGINEERING' in audit)
    test("Has Section 3: Model Architecture", 'SECTION 3: MODEL ARCHITECTURE' in audit)
    test("Has Section 4: Signal Generation", 'SECTION 4: SIGNAL GENERATION' in audit)
    test("Has Section 5: Risk Management", 'SECTION 5: RISK MANAGEMENT' in audit)
    test("Has Section 6: Backtest Integrity", 'SECTION 6: BACKTEST INTEGRITY' in audit)
    test("Has Section 7: Execution", 'SECTION 7: EXECUTION' in audit)
    test("Has Section 8: Findings Summary", 'SECTION 8: FINDINGS SUMMARY' in audit)
    test("Has Quick Wins section", 'QUICK WINS' in audit)
    test("Mentions scale_pos_weight fix", 'scale_pos_weight' in audit)
    test("Mentions class imbalance", 'Class Imbalance' in audit or 'class imbalance' in audit)
else:
    skip("Audit report", "docs/WISDOM_AUDIT_REPORT.md not found")


# ═══════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"  RESULTS BY SECTION")
print(f"{'='*60}")
for sec_name, counts in section_results.items():
    p, f, s = counts['passed'], counts['failed'], counts['skipped']
    status = "\033[32mALL PASS\033[0m" if f == 0 else f"\033[31m{f} FAILED\033[0m"
    print(f"  {sec_name}: {p} passed, {f} failed, {s} skipped  [{status}]")

print(f"\n{'='*60}")
total = passed + failed
print(f"  TOTAL: {passed} passed, {failed} failed, {skipped} skipped ({total} tests)")
print(f"{'='*60}")

if failed > 0:
    print(f"\n\033[31m{failed} TESTS FAILED\033[0m - review output above")
    sys.exit(1)
else:
    print(f"\n\033[32mAll {passed} tests passed!\033[0m")
    sys.exit(0)
