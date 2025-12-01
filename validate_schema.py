#!/usr/bin/env python3
"""
Static Schema Validator
Parses route files and compares SQL queries against database schema
"""

import re
import os

# Define actual database schema based on db/config_and_database.py
SCHEMA = {
    'conversations': ['id', 'timestamp', 'user_message', 'ai_response', 'context_data', 'session_id'],
    'probability_outcomes': ['id', 'timestamp', 'prediction_type', 'predicted_probability', 'actual_outcome', 'correct_prediction', 'outcome_timestamp'],
    'probability_weights': ['id', 'weight_name', 'weight_value', 'description', 'last_updated', 'calibration_count'],
    'calibration_history': ['id', 'timestamp', 'calibration_date', 'weight_name', 'old_value', 'new_value', 'reason', 'performance_delta'],
    'scanner_history': ['id', 'timestamp', 'symbols_scanned', 'results', 'scan_type', 'duration_ms'],
    'alerts': ['id', 'created_at', 'symbol', 'alert_type', 'condition', 'threshold', 'comparison', 'active', 'triggered_at', 'notification_sent', 'message'],
    'alert_history': ['id', 'timestamp', 'alert_id', 'symbol', 'alert_type', 'triggered_value', 'threshold', 'message', 'condition', 'actual_value'],
    'autonomous_equity_snapshots': ['id', 'timestamp', 'equity', 'cash', 'positions_value', 'daily_pnl', 'cumulative_pnl', 'drawdown_pct', 'high_water_mark'],
    'autonomous_open_positions': ['id', 'symbol', 'strategy', 'strike', 'option_type', 'contracts', 'entry_date', 'entry_time', 'entry_price', 'current_price', 'unrealized_pnl', 'status', 'entry_spot_price', 'current_spot_price', 'gex_regime', 'created_at'],
    'autonomous_closed_trades': ['id', 'symbol', 'strategy', 'strike', 'option_type', 'contracts', 'entry_date', 'entry_time', 'entry_price', 'exit_date', 'exit_time', 'exit_price', 'realized_pnl', 'exit_reason', 'hold_time_hours', 'entry_spot_price', 'exit_spot_price', 'entry_vix', 'exit_vix', 'gex_regime', 'created_at'],
    'autonomous_trade_activity': ['id', 'timestamp', 'activity_date', 'activity_time', 'action_type', 'symbol', 'details', 'position_id', 'pnl_impact', 'success', 'error_message'],
    'ml_models': ['id', 'created_at', 'model_name', 'model_type', 'version', 'accuracy', 'training_samples', 'features', 'hyperparameters', 'status'],
    'ml_predictions': ['id', 'timestamp', 'model_name', 'symbol', 'prediction', 'confidence', 'actual_outcome', 'features_used'],
    'trade_setups': ['id', 'created_at', 'symbol', 'setup_type', 'strike', 'option_type', 'entry_price', 'target_price', 'stop_price', 'contracts', 'expiration_date', 'reasoning', 'confidence', 'status', 'executed_at', 'result'],
    'gex_history': ['id', 'timestamp', 'symbol', 'net_gex', 'flip_point', 'call_wall', 'put_wall', 'spot_price', 'mm_state', 'regime', 'data_source'],
    'historical_open_interest': ['id', 'date', 'symbol', 'strike', 'expiration_date', 'call_oi', 'put_oi', 'call_volume', 'put_volume'],
    'recommendations': ['id', 'timestamp', 'symbol', 'strategy', 'confidence', 'entry_price', 'target_price', 'stop_price', 'option_strike', 'option_type', 'dte', 'reasoning', 'mm_behavior', 'outcome', 'pnl'],
    'regime_signals': ['id', 'timestamp', 'spy_price', 'net_gamma', 'primary_regime_type', 'secondary_regime_type', 'confidence_score', 'trade_direction', 'risk_level', 'description', 'rsi_5m', 'rsi_15m', 'rsi_1h', 'rsi_4h', 'rsi_1d', 'vix_current', 'liberation_setup_detected', 'liberation_expiry_date', 'false_floor_detected', 'false_floor_expiry_date'],
    'psychology_notifications': ['id', 'timestamp', 'notification_type', 'regime_type', 'message', 'severity', 'data', 'read', 'created_at'],
    'backtest_results': ['id', 'timestamp', 'strategy_name', 'symbol', 'start_date', 'end_date', 'total_trades', 'win_rate', 'profit_factor', 'max_drawdown', 'sharpe_ratio', 'total_return', 'parameters'],
    'backtest_trades': ['id', 'run_id', 'trade_number', 'strategy', 'entry_date', 'exit_date', 'entry_price', 'exit_price', 'contracts', 'pnl', 'pnl_pct', 'hold_time_hours', 'exit_reason', 'symbol', 'strike', 'option_type'],
    'positions': ['id', 'timestamp', 'symbol', 'option_type', 'strike', 'expiration', 'contracts', 'entry_price', 'exit_price', 'current_price', 'status', 'pattern_type', 'confidence_score', 'realized_pnl', 'unrealized_pnl', 'entry_reason', 'exit_reason'],
    'performance': ['id', 'date', 'total_pnl', 'trades_count', 'win_count', 'loss_count', 'win_rate', 'avg_win', 'avg_loss', 'max_drawdown', 'sharpe_ratio'],
    'vix_history': ['id', 'timestamp', 'vix_value', 'vix_open', 'vix_high', 'vix_low', 'vix_close', 'vix9d', 'vix3m', 'contango_pct'],
    'strike_performance': ['id', 'timestamp', 'strategy_name', 'strike_distance_pct', 'total_trades', 'win_rate', 'avg_return', 'best_trade', 'worst_trade'],
    'ai_insights': ['id', 'timestamp', 'insight_type', 'symbol', 'content', 'confidence', 'source', 'metadata'],
    'market_data': ['id', 'timestamp', 'symbol', 'spot_price', 'vix', 'net_gex', 'data_source'],
    'gex_levels': ['id', 'timestamp', 'symbol', 'call_wall', 'put_wall', 'flip_point', 'net_gex', 'gex_regime'],
    'psychology_analysis': ['id', 'timestamp', 'symbol', 'regime_type', 'confidence', 'psychology_trap', 'reasoning'],
    'price_history': ['id', 'timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'timeframe', 'data_source'],
    'autonomous_trade_log': ['id', 'timestamp', 'date', 'time', 'action', 'symbol', 'strike', 'option_type', 'contracts', 'price', 'reason', 'success', 'details'],
    'autonomous_live_status': ['id', 'timestamp', 'status', 'last_scan', 'positions_open', 'daily_trades', 'daily_pnl', 'message'],
    'autonomous_config': ['id', 'key', 'value', 'updated_at'],
}

# Known non-existent columns that were in the code (for reference)
KNOWN_BAD_COLUMNS = {
    'conversations': ['context'],  # should be context_data
    'probability_outcomes': ['prediction_date', 'pattern_type'],  # should be timestamp, prediction_type
    'scanner_history': ['symbols'],  # should be symbols_scanned
    'alerts': ['status', 'triggered_value'],  # should be active (boolean), removed triggered_value
    'autonomous_equity_snapshots': ['sharpe_ratio', 'max_drawdown_pct', 'snapshot_date', 'snapshot_time', 'starting_capital', 'total_realized_pnl', 'total_unrealized_pnl', 'account_value', 'daily_return_pct', 'total_return_pct', 'win_rate', 'total_trades'],
    'autonomous_open_positions': ['action', 'expiration_date', 'contract_symbol', 'entry_bid', 'entry_ask', 'unrealized_pnl_pct', 'confidence', 'entry_net_gex', 'entry_flip_point', 'entry_iv', 'entry_delta', 'current_iv', 'current_delta', 'trade_reasoning'],
    'autonomous_closed_trades': ['action', 'expiration_date', 'contract_symbol', 'entry_bid', 'entry_ask', 'realized_pnl_pct', 'confidence', 'entry_net_gex', 'entry_flip_point', 'entry_iv', 'entry_delta', 'current_iv', 'current_delta', 'trade_reasoning'],
    'ml_models': ['last_trained'],  # should be created_at
    'gex_history': ['call_gex', 'put_gex', 'gamma_flip', 'max_pain'],
    'historical_open_interest': ['snapshot_date', 'expiration', 'total_oi', 'put_call_ratio'],  # should be date, expiration_date, calculated
    'recommendations': ['direction', 'strike', 'expiration', 'stop_loss', 'status', 'actual_outcome'],  # should be option_strike, dte, stop_price, outcome
    'trade_setups': ['position_size', 'max_risk_dollars', 'time_horizon', 'catalyst', 'money_making_plan', 'risk_reward'],
}


def extract_sql_columns(sql):
    """Extract column names from a SELECT statement"""
    # Normalize whitespace
    sql = ' '.join(sql.split())

    # Find SELECT ... FROM
    match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    select_part = match.group(1)

    # Handle SELECT *
    if select_part.strip() == '*':
        return ['*']

    # Split by comma, handling functions and aliases
    columns = []
    depth = 0
    current = ''

    for char in select_part:
        if char == '(':
            depth += 1
            current += char
        elif char == ')':
            depth -= 1
            current += char
        elif char == ',' and depth == 0:
            columns.append(current.strip())
            current = ''
        else:
            current += char

    if current.strip():
        columns.append(current.strip())

    # Extract just column names (remove aliases, functions, etc.)
    clean_columns = []
    for col in columns:
        # Skip NULL as ...
        if col.upper().startswith('NULL'):
            continue
        # Handle "table.column" or "column as alias"
        col = col.split(' as ')[0].split(' AS ')[0]
        col = col.split('.')[-1]
        # Handle functions like COALESCE(), SUM(), etc.
        if '(' in col:
            # Extract column from inside function
            inner = re.search(r'\(([^)]+)\)', col)
            if inner:
                inner_cols = inner.group(1).split(',')
                for ic in inner_cols:
                    ic = ic.strip()
                    if ic and not ic.replace('.', '').replace("'", '').isdigit():
                        ic = ic.split('.')[-1]
                        if ic not in ['0', '1', '2'] and not ic.startswith("'"):
                            clean_columns.append(ic)
        else:
            clean_columns.append(col)

    return clean_columns


def extract_table_name(sql):
    """Extract table name from SQL"""
    match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'INTO\s+(\w+)', sql, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'UPDATE\s+(\w+)', sql, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def find_sql_in_file(filepath):
    """Find all SQL queries in a Python file"""
    with open(filepath, 'r') as f:
        content = f.read()

    # Find triple-quoted strings that look like SQL
    sql_pattern = r'(?:execute|read_sql_query)\s*\(\s*["\'\`]{1,3}(.*?)["\'\`]{1,3}'
    matches = re.findall(sql_pattern, content, re.DOTALL | re.IGNORECASE)

    # Also find f-strings with SQL
    fstring_pattern = r'(?:execute|read_sql_query)\s*\(\s*f["\'\`]{1,3}(.*?)["\'\`]{1,3}'
    matches.extend(re.findall(fstring_pattern, content, re.DOTALL | re.IGNORECASE))

    return matches


def validate_route_file(filepath):
    """Validate SQL queries in a route file against schema"""
    issues = []

    sqls = find_sql_in_file(filepath)

    for sql in sqls:
        table = extract_table_name(sql)
        if not table or table not in SCHEMA:
            continue

        columns = extract_sql_columns(sql)
        if '*' in columns:
            continue  # Can't validate SELECT *

        valid_columns = SCHEMA[table]
        bad_columns = KNOWN_BAD_COLUMNS.get(table, [])

        for col in columns:
            col_clean = col.strip().lower()
            # Skip PostgreSQL keywords and functions
            if col_clean in ['count', 'sum', 'avg', 'max', 'min', 'coalesce', 'case', 'when', 'then', 'else', 'end', 'now', 'current_timestamp', 'interval', 'date', 'true', 'false']:
                continue

            col_lower = [c.lower() for c in valid_columns]
            if col_clean not in col_lower:
                if col_clean in [b.lower() for b in bad_columns]:
                    issues.append(f"  ❌ KNOWN BAD: '{col}' in {table} (previously identified)")
                else:
                    issues.append(f"  ⚠️  POTENTIAL: '{col}' may not exist in {table}")

    return issues


def main():
    routes_dir = '/home/user/AlphaGEX/backend/api/routes'

    print("\n" + "="*70)
    print("STATIC SCHEMA VALIDATION - ROUTE FILES")
    print("="*70 + "\n")

    all_issues = {}

    for filename in sorted(os.listdir(routes_dir)):
        if filename.endswith('_routes.py'):
            filepath = os.path.join(routes_dir, filename)
            issues = validate_route_file(filepath)

            if issues:
                all_issues[filename] = issues
                print(f"\n📄 {filename}:")
                for issue in issues:
                    print(issue)
            else:
                print(f"✅ {filename} - OK")

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    if all_issues:
        total = sum(len(v) for v in all_issues.values())
        print(f"\n⚠️  Found {total} potential issues in {len(all_issues)} files")
        print("\nNote: Some 'POTENTIAL' issues may be false positives (calculated columns, aliases)")
        print("      'KNOWN BAD' issues indicate columns we previously fixed - verify they're gone")
    else:
        print("\n✅ No obvious schema issues found!")


if __name__ == '__main__':
    main()
