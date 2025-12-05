#!/usr/bin/env python3
"""
COMPREHENSIVE DATABASE SEEDER
Seeds ALL 62 empty tables with initial data to ensure pipelines are working.

Run this script to:
1. Populate all empty tables with seed data
2. Verify INSERT statements work
3. Initialize the system for first-time use

Usage:
    python scripts/seed_all_tables.py
"""

import os
import sys
import json
from datetime import datetime, timedelta
import traceback
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("❌ Database not available")
    sys.exit(1)


def seed_table(table_name: str, insert_sql: str, params: tuple) -> bool:
    """Seed a single table with data"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute(insert_sql, params)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"    ❌ {table_name}: {e}")
        return False


def seed_all_tables():
    """Seed all 62 empty tables"""
    print("=" * 70)
    print("🌱 SEEDING ALL 62 EMPTY TABLES")
    print("=" * 70)

    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    timestamp = now.isoformat()

    results = {"success": 0, "failed": 0, "tables": []}

    # =========================================================================
    # GROUP 1: AI/ML TABLES (8 tables)
    # =========================================================================
    print("\n📊 GROUP 1: AI/ML Tables")

    # 1. ai_analysis_history
    if seed_table('ai_analysis_history', """
        INSERT INTO ai_analysis_history
        (analysis_type, symbol, input_prompt, ai_response, model_used, outcome_tracked)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ('seed', 'SPY', 'Initial seed', 'System initialized', 'seed_script', False)):
        print("    ✅ ai_analysis_history")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 2. ai_performance
    if seed_table('ai_performance', """
        INSERT INTO ai_performance
        (date, total_predictions, correct_predictions, profitable_trades, losing_trades, net_pnl)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (today, 0, 0, 0, 0, 0.0)):
        print("    ✅ ai_performance")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 3. ai_predictions
    if seed_table('ai_predictions', """
        INSERT INTO ai_predictions
        (symbol, prediction_type, predicted_direction, confidence, reasoning)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 'NEUTRAL', 0.5, 'Initial seed data')):
        print("    ✅ ai_predictions")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 4. ai_recommendations
    if seed_table('ai_recommendations', """
        INSERT INTO ai_recommendations
        (symbol, recommendation_type, action, confidence, reasoning)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 'HOLD', 0.5, 'Initial seed data')):
        print("    ✅ ai_recommendations")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 5. ml_decision_logs
    if seed_table('ml_decision_logs', """
        INSERT INTO ml_decision_logs
        (model_name, decision_type, input_features, output, confidence)
        VALUES (%s, %s, %s, %s, %s)
    """, ('seed_model', 'initialization', '{}', 'initialized', 1.0)):
        print("    ✅ ml_decision_logs")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 6. ml_models
    if seed_table('ml_models', """
        INSERT INTO ml_models
        (model_name, model_type, parameters, accuracy, is_active)
        VALUES (%s, %s, %s, %s, %s)
    """, ('seed_model', 'placeholder', '{}', 0.5, False)):
        print("    ✅ ml_models")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 7. ml_predictions
    if seed_table('ml_predictions', """
        INSERT INTO ml_predictions
        (model_name, symbol, prediction, confidence, features_used)
        VALUES (%s, %s, %s, %s, %s)
    """, ('seed_model', 'SPY', 'NEUTRAL', 0.5, '{}')):
        print("    ✅ ml_predictions")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 8. ml_regime_models
    if seed_table('ml_regime_models', """
        INSERT INTO ml_regime_models
        (model_name, regime_type, accuracy, feature_importance, is_active)
        VALUES (%s, %s, %s, %s, %s)
    """, ('seed_regime_model', 'NEUTRAL', 0.5, '{}', False)):
        print("    ✅ ml_regime_models")
        results["success"] += 1
    else:
        results["failed"] += 1

    # =========================================================================
    # GROUP 2: BACKTEST TABLES (6 tables)
    # =========================================================================
    print("\n📈 GROUP 2: Backtest Tables")

    # 9. backtest_results
    if seed_table('backtest_results', """
        INSERT INTO backtest_results
        (strategy_name, symbol, start_date, end_date, total_trades, winning_trades,
         losing_trades, win_rate, total_return_pct, max_drawdown_pct, sharpe_ratio)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, ('SEED_STRATEGY', 'SPY', '2024-01-01', '2024-12-01', 0, 0, 0, 0.0, 0.0, 0.0, 0.0)):
        print("    ✅ backtest_results")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 10. backtest_runs
    if seed_table('backtest_runs', """
        INSERT INTO backtest_runs
        (run_id, strategy_name, symbol, start_date, end_date, status)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ('seed-run-001', 'SEED_STRATEGY', 'SPY', '2024-01-01', '2024-12-01', 'completed')):
        print("    ✅ backtest_runs")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 11. backtest_summary
    if seed_table('backtest_summary', """
        INSERT INTO backtest_summary
        (symbol, start_date, end_date, psychology_trades, psychology_win_rate,
         gex_trades, gex_win_rate, options_trades, options_win_rate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', '2024-01-01', '2024-12-01', 0, 0.0, 0, 0.0, 0, 0.0)):
        print("    ✅ backtest_summary")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 12. backtest_trades
    if seed_table('backtest_trades', """
        INSERT INTO backtest_trades
        (backtest_run_id, strategy_name, trade_number, symbol, entry_date, entry_price,
         exit_date, exit_price, pnl_dollars, pnl_percent, win)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, ('seed-run-001', 'SEED_STRATEGY', 1, 'SPY', '2024-01-01', 100.0, '2024-01-02', 101.0, 1.0, 1.0, True)):
        print("    ✅ backtest_trades")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 13. strike_performance
    if seed_table('strike_performance', """
        INSERT INTO strike_performance
        (strategy_name, strike_distance_pct, strike_type, moneyness, delta, gamma,
         theta, vega, dte, pnl_pct, win)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, ('SEED', 5.0, 'PUT', 'OTM', 0.3, 0.05, -0.02, 0.1, 30, 10.0, 1)):
        print("    ✅ strike_performance")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 14. spread_width_performance
    if seed_table('spread_width_performance', """
        INSERT INTO spread_width_performance
        (strategy_name, spread_type, short_strike_call, long_strike_call,
         call_spread_width_points, pnl_pct, win)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ('SEED', 'vertical_call', 600, 605, 5.0, 5.0, 1)):
        print("    ✅ spread_width_performance")
        results["success"] += 1
    else:
        results["failed"] += 1

    # =========================================================================
    # GROUP 3: GEX/GAMMA TABLES (5 tables)
    # =========================================================================
    print("\n📊 GROUP 3: GEX/Gamma Tables")

    # 15. gex_snapshots_detailed
    if seed_table('gex_snapshots_detailed', """
        INSERT INTO gex_snapshots_detailed
        (symbol, net_gex, flip_point, spot_price, gex_0dte, gex_weekly, gex_monthly)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', 0.0, 600.0, 600.0, 0.0, 0.0, 0.0)):
        print("    ✅ gex_snapshots_detailed")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 16. gex_change_log
    if seed_table('gex_change_log', """
        INSERT INTO gex_change_log
        (symbol, previous_gex, current_gex, change, change_pct, velocity_trend, direction_change)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', 0.0, 0.0, 0.0, 0.0, 'STABLE', False)):
        print("    ✅ gex_change_log")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 17. gamma_correlation
    if seed_table('gamma_correlation', """
        INSERT INTO gamma_correlation
        (symbol, correlation_type, value, description)
        VALUES (%s, %s, %s, %s)
    """, ('SPY', 'gex_price', 0.0, 'Initial seed')):
        print("    ✅ gamma_correlation")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 18. liberation_outcomes
    if seed_table('liberation_outcomes', """
        INSERT INTO liberation_outcomes
        (symbol, detection_timestamp, detection_price, target_price, outcome, pnl_pct)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ('SPY', timestamp, 600.0, 605.0, 'PENDING', 0.0)):
        print("    ✅ liberation_outcomes")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 19. greeks_snapshots
    if seed_table('greeks_snapshots', """
        INSERT INTO greeks_snapshots
        (symbol, strike, option_type, expiration_date, dte, delta, gamma, theta, vega,
         implied_volatility, underlying_price, option_price, data_source, context)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', 600.0, 'call', today, 30, 0.5, 0.05, -0.02, 0.1, 0.2, 600.0, 5.0, 'seed', 'initialization')):
        print("    ✅ greeks_snapshots")
        results["success"] += 1
    else:
        results["failed"] += 1

    # =========================================================================
    # GROUP 4: OPTIONS TABLES (5 tables)
    # =========================================================================
    print("\n📋 GROUP 4: Options Tables")

    # 20. options_chain_snapshots
    if seed_table('options_chain_snapshots', """
        INSERT INTO options_chain_snapshots
        (symbol, expiration_date, chain_data, statistics, bid_ask_spread_avg, iv_avg, volume_total)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', today, '{}', '{}', 0.05, 0.2, 0)):
        print("    ✅ options_chain_snapshots")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 21. options_collection_log
    if seed_table('options_collection_log', """
        INSERT INTO options_collection_log
        (symbol, collection_type, contracts_collected, success, duration_seconds)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 0, True, 0.0)):
        print("    ✅ options_collection_log")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 22. options_flow
    if seed_table('options_flow', """
        INSERT INTO options_flow
        (symbol, total_call_volume, total_put_volume, put_call_ratio, spot_price, data_source)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ('SPY', 0, 0, 1.0, 600.0, 'seed')):
        print("    ✅ options_flow")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 23. greeks_performance
    if seed_table('greeks_performance', """
        INSERT INTO greeks_performance
        (strategy_name, entry_delta, entry_gamma, entry_theta, entry_vega, pnl_pct, win)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ('SEED', 0.3, 0.05, -0.02, 0.1, 5.0, 1)):
        print("    ✅ greeks_performance")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 24. dte_performance
    if seed_table('dte_performance', """
        INSERT INTO dte_performance
        (strategy_name, dte_bucket, avg_pnl_pct, win_rate, total_trades)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SEED', '30-45', 5.0, 0.6, 10)):
        print("    ✅ dte_performance")
        results["success"] += 1
    else:
        results["failed"] += 1

    # =========================================================================
    # GROUP 5: REGIME/PSYCHOLOGY TABLES (6 tables)
    # =========================================================================
    print("\n🧠 GROUP 5: Regime/Psychology Tables")

    # 25. regime_signals
    if seed_table('regime_signals', """
        INSERT INTO regime_signals
        (spy_price, net_gamma, primary_regime_type, confidence_score, trade_direction, risk_level)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (600.0, 0.0, 'NEUTRAL', 0.5, 'NEUTRAL', 'MEDIUM')):
        print("    ✅ regime_signals")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 26. regime_classifications
    if seed_table('regime_classifications', """
        INSERT INTO regime_classifications
        (symbol, regime_type, confidence, net_gex, spot_price, flip_point)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ('SPY', 'NEUTRAL', 0.5, 0.0, 600.0, 600.0)):
        print("    ✅ regime_classifications")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 27. psychology_analysis
    if seed_table('psychology_analysis', """
        INSERT INTO psychology_analysis
        (symbol, regime_type, confidence, psychology_trap, reasoning)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SPY', 'NEUTRAL', 0.5, None, 'Initial seed')):
        print("    ✅ psychology_analysis")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 28. psychology_notifications
    if seed_table('psychology_notifications', """
        INSERT INTO psychology_notifications
        (notification_type, regime_type, message, severity)
        VALUES (%s, %s, %s, %s)
    """, ('seed', 'NEUTRAL', 'System initialized', 'INFO')):
        print("    ✅ psychology_notifications")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 29. sucker_statistics
    if seed_table('sucker_statistics', """
        INSERT INTO sucker_statistics
        (pattern_type, total_detected, successful, failed, win_rate)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SEED', 0, 0, 0, 0.0)):
        print("    ✅ sucker_statistics")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 30. pattern_learning
    if seed_table('pattern_learning', """
        INSERT INTO pattern_learning
        (pattern_name, occurrences, success_rate, avg_pnl, confidence)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SEED_PATTERN', 0, 0.0, 0.0, 0.5)):
        print("    ✅ pattern_learning")
        results["success"] += 1
    else:
        results["failed"] += 1

    # =========================================================================
    # GROUP 6: TRADING/POSITION TABLES (9 tables)
    # =========================================================================
    print("\n💹 GROUP 6: Trading/Position Tables")

    # 31. trades
    if seed_table('trades', """
        INSERT INTO trades
        (symbol, strike, option_type, contracts, entry_price, exit_price, pnl, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', 600.0, 'call', 1, 5.0, 5.0, 0.0, 'seed')):
        print("    ✅ trades")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 32. positions
    if seed_table('positions', """
        INSERT INTO positions
        (symbol, entry_price, quantity, status)
        VALUES (%s, %s, %s, %s)
    """, ('SPY', 600.0, 0, 'seed')):
        print("    ✅ positions")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 33. trading_decisions
    if seed_table('trading_decisions', """
        INSERT INTO trading_decisions
        (symbol, decision_type, action, reasoning, confidence)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 'HOLD', 'System initialization', 0.5)):
        print("    ✅ trading_decisions")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 34. trade_setups
    if seed_table('trade_setups', """
        INSERT INTO trade_setups
        (symbol, setup_type, direction, entry_price, stop_loss, take_profit, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 'NEUTRAL', 600.0, 590.0, 610.0, 'inactive')):
        print("    ✅ trade_setups")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 35. unified_positions
    if seed_table('unified_positions', """
        INSERT INTO unified_positions
        (symbol, position_type, quantity, entry_price, current_price, unrealized_pnl)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 0, 600.0, 600.0, 0.0)):
        print("    ✅ unified_positions")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 36. unified_trades
    if seed_table('unified_trades', """
        INSERT INTO unified_trades
        (symbol, trade_type, quantity, entry_price, exit_price, realized_pnl, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 0, 600.0, 600.0, 0.0, 'closed')):
        print("    ✅ unified_trades")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 37. position_sizing_history
    if seed_table('position_sizing_history', """
        INSERT INTO position_sizing_history
        (symbol, account_value, win_rate, avg_win, avg_loss, kelly_full, kelly_half,
         recommended_size, regime)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', 100000, 0.5, 10.0, 10.0, 0.0, 0.0, 0.0, 'NEUTRAL')):
        print("    ✅ position_sizing_history")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 38. performance
    if seed_table('performance', """
        INSERT INTO performance
        (date, total_trades, winning_trades, losing_trades, net_pnl, win_rate)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (today, 0, 0, 0, 0.0, 0.0)):
        print("    ✅ performance")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 39. market_snapshots
    if seed_table('market_snapshots', """
        INSERT INTO market_snapshots
        (symbol, price, net_gex, call_wall, put_wall, flip_point, vix_spot, gex_regime)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, ('SPY', 600.0, 0.0, 610.0, 590.0, 600.0, 17.0, 'NEUTRAL')):
        print("    ✅ market_snapshots")
        results["success"] += 1
    else:
        results["failed"] += 1

    # =========================================================================
    # GROUP 7: SPX WHEEL TABLES (12 tables)
    # =========================================================================
    print("\n🎡 GROUP 7: SPX Wheel Tables")

    # 40-51 SPX Wheel tables
    spx_tables = [
        ('spx_wheel_positions', """
            INSERT INTO spx_wheel_positions
            (symbol, position_type, strike, expiration, contracts, entry_price, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, ('SPX', 'seed', 6000.0, today, 0, 0.0, 'seed')),

        ('spx_wheel_parameters', """
            INSERT INTO spx_wheel_parameters
            (parameters, is_active)
            VALUES (%s, %s)
        """, ('{}', False)),

        ('spx_wheel_performance', """
            INSERT INTO spx_wheel_performance
            (date, equity, daily_pnl, cumulative_pnl, open_positions)
            VALUES (%s, %s, %s, %s, %s)
        """, (today, 100000, 0.0, 0.0, 0)),

        ('spx_wheel_greeks', """
            INSERT INTO spx_wheel_greeks
            (position_id, delta, gamma, theta, vega, iv)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (0, 0.0, 0.0, 0.0, 0.0, 0.0)),

        ('spx_wheel_reconciliation', """
            INSERT INTO spx_wheel_reconciliation
            (date, expected_equity, actual_equity, difference, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, (today, 100000, 100000, 0.0, 'seed')),

        ('spx_wheel_alerts', """
            INSERT INTO spx_wheel_alerts
            (alert_type, level, subject, body)
            VALUES (%s, %s, %s, %s)
        """, ('seed', 'INFO', 'System initialized', 'Seed alert')),

        ('spx_wheel_multileg_positions', """
            INSERT INTO spx_wheel_multileg_positions
            (strategy_type, legs, total_premium, max_risk, status)
            VALUES (%s, %s, %s, %s, %s)
        """, ('seed', '[]', 0.0, 0.0, 'seed')),

        ('spx_wheel_ml_outcomes', """
            INSERT INTO spx_wheel_ml_outcomes
            (prediction_type, predicted, actual, correct)
            VALUES (%s, %s, %s, %s)
        """, ('seed', 'NEUTRAL', 'NEUTRAL', True)),

        ('spx_wheel_backtest_equity', """
            INSERT INTO spx_wheel_backtest_equity
            (backtest_id, date, equity, daily_return_pct)
            VALUES (%s, %s, %s, %s)
        """, ('seed-001', today, 100000, 0.0)),

        ('spx_wheel_backtest_runs', """
            INSERT INTO spx_wheel_backtest_runs
            (backtest_id, config, summary, data_quality)
            VALUES (%s, %s, %s, %s)
        """, ('seed-001', '{}', '{}', '{}'))
    ]

    for table_name, sql, params in spx_tables:
        if seed_table(table_name, sql, params):
            print(f"    ✅ {table_name}")
            results["success"] += 1
        else:
            results["failed"] += 1

    # spx_wheel_backtest_trades
    if seed_table('spx_wheel_backtest_trades', """
        INSERT INTO spx_wheel_backtest_trades
        (backtest_id, trade_date, trade_type, strike, premium, pnl, data_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ('seed-001', today, 'PUT', 6000.0, 1.0, 0.0, 'seed')):
        print("    ✅ spx_wheel_backtest_trades")
        results["success"] += 1
    else:
        results["failed"] += 1

    # spx_institutional_positions
    if seed_table('spx_institutional_positions', """
        INSERT INTO spx_institutional_positions
        (symbol, institution, position_type, shares, filing_date)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SPX', 'seed', 'long', 0, today)):
        print("    ✅ spx_institutional_positions")
        results["success"] += 1
    else:
        results["failed"] += 1

    # =========================================================================
    # GROUP 8: ALERT/NOTIFICATION TABLES (4 tables)
    # =========================================================================
    print("\n🔔 GROUP 8: Alert/Notification Tables")

    # 52. alerts
    if seed_table('alerts', """
        INSERT INTO alerts
        (symbol, alert_type, condition, threshold, message, is_active)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 'none', 0.0, 'System initialized', False)):
        print("    ✅ alerts")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 53. alert_history
    if seed_table('alert_history', """
        INSERT INTO alert_history
        (alert_id, triggered_value, message)
        VALUES (%s, %s, %s)
    """, (0, 0.0, 'Seed entry')):
        print("    ✅ alert_history")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 54. push_subscriptions
    if seed_table('push_subscriptions', """
        INSERT INTO push_subscriptions
        (endpoint, p256dh, auth, preferences)
        VALUES (%s, %s, %s, %s)
    """, ('seed-endpoint', 'seed-key', 'seed-auth', '{}')):
        print("    ✅ push_subscriptions")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 55. scanner_history
    if seed_table('scanner_history', """
        INSERT INTO scanner_history
        (symbols_scanned, results, scan_type)
        VALUES (%s, %s, %s)
    """, ('SPY', '{}', 'seed')):
        print("    ✅ scanner_history")
        results["success"] += 1
    else:
        results["failed"] += 1

    # =========================================================================
    # GROUP 9: QUANT/VALIDATION TABLES (7 tables)
    # =========================================================================
    print("\n📐 GROUP 9: Quant/Validation Tables")

    # 56. walk_forward_results
    if seed_table('walk_forward_results', """
        INSERT INTO walk_forward_results
        (strategy_name, train_start, train_end, test_start, test_end,
         train_sharpe, test_sharpe, degradation_pct, is_robust)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, ('SEED', '2024-01-01', '2024-06-01', '2024-06-01', '2024-12-01', 0.0, 0.0, 0.0, True)):
        print("    ✅ walk_forward_results")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 57. monte_carlo_kelly
    if seed_table('monte_carlo_kelly', """
        INSERT INTO monte_carlo_kelly
        (strategy_name, simulations, median_kelly, kelly_5th_pct, kelly_95th_pct,
         recommended_fraction, risk_of_ruin)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ('SEED', 1000, 0.0, 0.0, 0.0, 0.0, 0.0)):
        print("    ✅ monte_carlo_kelly")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 58. quant_recommendations
    if seed_table('quant_recommendations', """
        INSERT INTO quant_recommendations
        (strategy_name, recommendation_type, value, confidence, reasoning)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SEED', 'position_size', 0.0, 0.5, 'Initial seed')):
        print("    ✅ quant_recommendations")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 59. ensemble_signals
    if seed_table('ensemble_signals', """
        INSERT INTO ensemble_signals
        (symbol, signal_type, direction, strength, contributing_models)
        VALUES (%s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 'NEUTRAL', 0.0, '[]')):
        print("    ✅ ensemble_signals")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 60. paper_signals
    if seed_table('paper_signals', """
        INSERT INTO paper_signals
        (symbol, signal_type, direction, entry_price, target_price, stop_loss)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ('SPY', 'seed', 'NEUTRAL', 600.0, 610.0, 590.0)):
        print("    ✅ paper_signals")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 61. paper_outcomes
    if seed_table('paper_outcomes', """
        INSERT INTO paper_outcomes
        (signal_id, exit_price, pnl_pct, outcome, days_held)
        VALUES (%s, %s, %s, %s, %s)
    """, (0, 600.0, 0.0, 'seed', 0)):
        print("    ✅ paper_outcomes")
        results["success"] += 1
    else:
        results["failed"] += 1

    # 62. probability_outcomes
    if seed_table('probability_outcomes', """
        INSERT INTO probability_outcomes
        (prediction_id, actual_close_price, prediction_correct, error_pct)
        VALUES (%s, %s, %s, %s)
    """, (0, 600.0, True, 0.0)):
        print("    ✅ probability_outcomes")
        results["success"] += 1
    else:
        results["failed"] += 1

    # =========================================================================
    # GROUP 10: OTHER TABLES (10 tables)
    # =========================================================================
    print("\n📦 GROUP 10: Other Tables")

    other_tables = [
        ('probability_weights', """
            INSERT INTO probability_weights
            (factor_name, weight, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (factor_name) DO UPDATE SET weight = EXCLUDED.weight
        """, ('gex_direction', 0.3, 'GEX regime weight')),

        ('calibration_history', """
            INSERT INTO calibration_history
            (calibration_type, parameters, accuracy_before, accuracy_after)
            VALUES (%s, %s, %s, %s)
        """, ('seed', '{}', 0.5, 0.5)),

        ('vix_term_structure', """
            INSERT INTO vix_term_structure
            (vix_spot, spy_price, regime, data_source)
            VALUES (%s, %s, %s, %s)
        """, (17.0, 600.0, 'NORMAL', 'seed')),

        ('vix_hedge_signals', """
            INSERT INTO vix_hedge_signals
            (signal_type, vix_level, recommended_action, confidence)
            VALUES (%s, %s, %s, %s)
        """, ('seed', 17.0, 'NONE', 0.5)),

        ('vix_hedge_positions', """
            INSERT INTO vix_hedge_positions
            (symbol, position_type, quantity, entry_price, current_value)
            VALUES (%s, %s, %s, %s, %s)
        """, ('VIX', 'seed', 0, 17.0, 17.0)),

        ('conversations', """
            INSERT INTO conversations
            (user_message, ai_response, context_data, confidence_score)
            VALUES (%s, %s, %s, %s)
        """, ('seed', 'System initialized', '{}', 1.0)),

        ('scheduler_state', """
            INSERT INTO scheduler_state
            (job_name, last_run, next_run, status, error_count)
            VALUES (%s, %s, %s, %s, %s)
        """, ('seed_job', timestamp, timestamp, 'idle', 0)),

        ('spx_debug_logs', """
            INSERT INTO spx_debug_logs
            (log_level, component, message, data)
            VALUES (%s, %s, %s, %s)
        """, ('INFO', 'seed', 'System initialized', '{}')),

        ('strategy_competition', """
            INSERT INTO strategy_competition
            (strategy_a, strategy_b, winner, margin_pct, sample_size)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SEED_A', 'SEED_B', 'TIE', 0.0, 0)),

        ('strategy_comparison_history', """
            INSERT INTO strategy_comparison_history
            (strategy_name, comparison_date, metric_name, metric_value)
            VALUES (%s, %s, %s, %s)
        """, ('SEED', today, 'win_rate', 0.0))
    ]

    for table_name, sql, params in other_tables:
        if seed_table(table_name, sql, params):
            print(f"    ✅ {table_name}")
            results["success"] += 1
        else:
            results["failed"] += 1

    # =========================================================================
    # GROUP 11: CORE DATA TABLES (Previously scheduler-only)
    # =========================================================================
    print("\n📊 GROUP 11: Core Data Tables")

    core_tables = [
        ('gex_history', """
            INSERT INTO gex_history
            (symbol, net_gex, flip_point, spot_price, call_wall, put_wall)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, ('SPY', 0.0, 600.0, 600.0, 610.0, 590.0)),

        ('gamma_history', """
            INSERT INTO gamma_history
            (symbol, net_gamma, spot_price, call_gamma, put_gamma)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SPY', 0.0, 600.0, 0.0, 0.0)),

        ('gamma_daily_summary', """
            INSERT INTO gamma_daily_summary
            (date, symbol, avg_net_gamma, max_net_gamma, min_net_gamma)
            VALUES (%s, %s, %s, %s, %s)
        """, (today, 'SPY', 0.0, 0.0, 0.0)),

        ('gamma_expiration_timeline', """
            INSERT INTO gamma_expiration_timeline
            (symbol, expiration_date, gamma_at_expiry, days_to_expiry)
            VALUES (%s, %s, %s, %s)
        """, ('SPY', today, 0.0, 0)),

        ('gamma_strike_history', """
            INSERT INTO gamma_strike_history
            (symbol, strike, gamma_value, call_gamma, put_gamma)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SPY', 600.0, 0.0, 0.0, 0.0)),

        ('forward_magnets', """
            INSERT INTO forward_magnets
            (symbol, magnet_price, magnet_strength, distance_pct)
            VALUES (%s, %s, %s, %s)
        """, ('SPY', 600.0, 0.0, 0.0)),

        ('historical_open_interest', """
            INSERT INTO historical_open_interest
            (date, symbol, strike, expiration_date, call_oi, put_oi)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (today, 'SPY', 600.0, today, 0, 0)),

        ('market_data', """
            INSERT INTO market_data
            (symbol, spot_price, vix, net_gex, data_source)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SPY', 600.0, 17.0, 0.0, 'seed')),

        ('gex_levels', """
            INSERT INTO gex_levels
            (symbol, level_type, price, gamma_value, significance)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SPY', 'seed', 600.0, 0.0, 0.5)),

        ('price_history', """
            INSERT INTO price_history
            (symbol, date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, ('SPY', today, 600.0, 601.0, 599.0, 600.0, 0)),

        ('spy_correlation', """
            INSERT INTO spy_correlation
            (symbol, correlation_type, correlation_value, lookback_days)
            VALUES (%s, %s, %s, %s)
        """, ('SPY', 'seed', 0.0, 20)),

        ('data_collection_log', """
            INSERT INTO data_collection_log
            (collection_type, source, records_collected, success)
            VALUES (%s, %s, %s, %s)
        """, ('seed', 'seed_script', 0, True)),

        ('ml_decision_logs', """
            INSERT INTO ml_decision_logs
            (model_name, decision_type, input_features, output, confidence)
            VALUES (%s, %s, %s, %s, %s)
        """, ('seed_model', 'initialization', '{}', 'initialized', 1.0)),

        ('recommendations', """
            INSERT INTO recommendations
            (symbol, recommendation_type, action, confidence, reasoning)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SPY', 'seed', 'HOLD', 0.5, 'System initialized')),

        ('account_state', """
            INSERT INTO account_state
            (account_value, cash_balance, buying_power)
            VALUES (%s, %s, %s)
        """, (100000, 100000, 100000)),

        ('strategy_config', """
            INSERT INTO strategy_config
            (strategy_name, config_json, is_active)
            VALUES (%s, %s, %s)
        """, ('SEED', '{}', False)),

        ('background_jobs', """
            INSERT INTO background_jobs
            (job_name, status, last_run)
            VALUES (%s, %s, %s)
        """, ('seed_job', 'idle', timestamp))
    ]

    for table_name, sql, params in core_tables:
        if seed_table(table_name, sql, params):
            print(f"    ✅ {table_name}")
            results["success"] += 1
        else:
            results["failed"] += 1

    # =========================================================================
    # GROUP 12: WHEEL SYSTEM TABLES
    # =========================================================================
    print("\n🎡 GROUP 12: Wheel System Tables")

    wheel_tables = [
        ('wheel_cycles', """
            INSERT INTO wheel_cycles
            (symbol, cycle_type, status, start_date)
            VALUES (%s, %s, %s, %s)
        """, ('SPY', 'seed', 'inactive', today)),

        ('wheel_legs', """
            INSERT INTO wheel_legs
            (cycle_id, leg_type, strike, expiration, premium)
            VALUES (%s, %s, %s, %s, %s)
        """, (0, 'seed', 600.0, today, 0.0)),

        ('wheel_activity_log', """
            INSERT INTO wheel_activity_log
            (activity_type, description, details)
            VALUES (%s, %s, %s)
        """, ('seed', 'System initialized', '{}'))
    ]

    for table_name, sql, params in wheel_tables:
        if seed_table(table_name, sql, params):
            print(f"    ✅ {table_name}")
            results["success"] += 1
        else:
            results["failed"] += 1

    # =========================================================================
    # GROUP 13: AUTONOMOUS TRADER TABLES
    # =========================================================================
    print("\n🤖 GROUP 13: Autonomous Trader Tables")

    autonomous_tables = [
        ('autonomous_config', """
            INSERT INTO autonomous_config
            (config_name, config_value)
            VALUES (%s, %s)
        """, ('seed', '{}')),

        ('autonomous_positions', """
            INSERT INTO autonomous_positions
            (symbol, quantity, entry_price, current_price, unrealized_pnl)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SPY', 0, 600.0, 600.0, 0.0)),

        ('autonomous_trade_log', """
            INSERT INTO autonomous_trade_log
            (symbol, action, quantity, price, reason)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SPY', 'seed', 0, 600.0, 'System initialized')),

        ('autonomous_trader_logs', """
            INSERT INTO autonomous_trader_logs
            (log_level, message, details)
            VALUES (%s, %s, %s)
        """, ('INFO', 'System initialized', '{}')),

        ('autonomous_closed_trades', """
            INSERT INTO autonomous_closed_trades
            (symbol, entry_price, exit_price, quantity, pnl, reason)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, ('SPY', 600.0, 600.0, 0, 0.0, 'seed')),

        ('autonomous_open_positions', """
            INSERT INTO autonomous_open_positions
            (symbol, quantity, entry_price, current_price, unrealized_pnl)
            VALUES (%s, %s, %s, %s, %s)
        """, ('SPY', 0, 600.0, 600.0, 0.0)),

        ('autonomous_equity_snapshots', """
            INSERT INTO autonomous_equity_snapshots
            (equity, cash, positions_value)
            VALUES (%s, %s, %s)
        """, (100000, 100000, 0)),

        ('autonomous_live_status', """
            INSERT INTO autonomous_live_status
            (status, equity, open_positions, last_trade)
            VALUES (%s, %s, %s, %s)
        """, ('idle', 100000, 0, None)),

        ('autonomous_trade_activity', """
            INSERT INTO autonomous_trade_activity
            (activity_type, symbol, details)
            VALUES (%s, %s, %s)
        """, ('seed', 'SPY', '{}'))
    ]

    for table_name, sql, params in autonomous_tables:
        if seed_table(table_name, sql, params):
            print(f"    ✅ {table_name}")
            results["success"] += 1
        else:
            results["failed"] += 1

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print("🌱 SEEDING COMPLETE")
    print("=" * 70)
    print(f"\n✅ Successful: {results['success']}")
    print(f"❌ Failed: {results['failed']}")
    print(f"📊 Total: {results['success'] + results['failed']}")

    return results


if __name__ == "__main__":
    seed_all_tables()
