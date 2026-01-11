#!/usr/bin/env python3
"""
ML Training Readiness Checker
=============================

Checks all database tables to determine which ML models can be trained
from available data.

Usage:
    python scripts/check_ml_training_readiness.py
    python scripts/check_ml_training_readiness.py --train-all  # Train all ready models
    python scripts/check_ml_training_readiness.py --json       # JSON output

Returns status for each ML model:
- READY: Has enough data to train
- BLOCKED: Missing required data
- TRAINED: Model already exists

Author: AlphaGEX Quant
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


# Model configurations
ML_MODELS = {
    'gex_probability': {
        'name': 'GEX Probability Models (5 models)',
        'description': 'Direction, flip gravity, magnet attraction, volatility, pin zone',
        'train_script': 'scripts/train_gex_probability_models.py',
        'model_path': 'models/gex_signal_generator.joblib',
        'min_records': 100,
        'data_tables': ['gex_structure_daily'],
        'priority': 'HIGH',
        'used_by': ['ATHENA', 'Apache Strategy'],
    },
    'oracle': {
        'name': 'Oracle Advisor',
        'description': 'Trade/skip decision with win probability',
        'train_script': 'scripts/train_oracle_model.py',
        'model_path': None,  # Stored in database
        'db_model_table': 'oracle_trained_models',
        'min_records': 50,
        'data_tables': ['oracle_training_outcomes', 'backtest_results', 'autonomous_closed_trades'],
        'priority': 'HIGH',
        'used_by': ['ARES', 'ATHENA', 'PHOENIX'],
    },
    'gex_directional': {
        'name': 'GEX Directional ML',
        'description': 'Predict daily direction from gamma structure',
        'train_script': 'scripts/train_directional_ml.py',
        'model_path': 'models/gex_directional_model.joblib',
        'min_records': 100,
        'data_tables': ['gex_structure_daily'],
        'priority': 'MEDIUM',
        'used_by': ['Backtests', 'Directional Signals'],
    },
    'ares_ml': {
        'name': 'ARES ML Advisor',
        'description': 'Iron Condor optimization from backtest patterns',
        'train_script': 'scripts/train_ares_ml.py',
        'model_path': 'quant/.models/ares_advisor_model.pkl',
        'min_records': 50,
        'data_tables': ['backtest_results', 'backtest_trades'],
        'priority': 'MEDIUM',
        'used_by': ['ARES Iron Condor'],
    },
    'prometheus': {
        'name': 'Prometheus ML',
        'description': 'SPX Wheel trade quality prediction',
        'train_script': 'scripts/train_prometheus_model.py',
        'model_path': None,  # Stored in database
        'db_model_table': 'prometheus_live_model',
        'min_records': 30,
        'data_tables': ['spx_wheel_ml_outcomes', 'backtest_results'],
        'priority': 'HIGH',
        'used_by': ['ATLAS SPX Wheel'],
    },
}


def get_connection():
    """Get PostgreSQL connection"""
    import psycopg2
    from urllib.parse import urlparse

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    result = urlparse(database_url)
    return psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )


def check_table_count(cursor, table: str) -> Tuple[int, Optional[str], Optional[str]]:
    """Check record count and date range for a table"""
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]

        # Try to get date range
        min_date, max_date = None, None
        for date_col in ['trade_date', 'timestamp', 'created_at', 'date']:
            try:
                cursor.execute(f"SELECT MIN({date_col}), MAX({date_col}) FROM {table}")
                row = cursor.fetchone()
                if row[0]:
                    min_date = str(row[0])[:10]
                    max_date = str(row[1])[:10]
                    break
            except:
                continue

        return count, min_date, max_date
    except Exception as e:
        return -1, None, None  # Table doesn't exist


def check_model_exists(model_config: Dict) -> bool:
    """Check if trained model already exists"""
    # Check file-based model
    if model_config.get('model_path'):
        if os.path.exists(model_config['model_path']):
            return True

    # Check database-stored model
    if model_config.get('db_model_table'):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {model_config['db_model_table']}")
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except:
            pass

    return False


def check_gex_from_tradier(cursor) -> Dict:
    """Check if we have GEX data collected from Tradier/live sources"""
    result = {
        'gex_history': {'count': 0, 'min_date': None, 'max_date': None},
        'can_populate_structure': False,
        'message': ''
    }

    # Check gex_history table (populated by live GEX snapshots)
    count, min_date, max_date = check_table_count(cursor, 'gex_history')
    result['gex_history']['count'] = count
    result['gex_history']['min_date'] = min_date
    result['gex_history']['max_date'] = max_date

    if count >= 20:
        result['can_populate_structure'] = True
        result['message'] = f'Found {count} GEX snapshots in gex_history'

    return result


def check_all_models() -> Dict:
    """Check training readiness for all ML models"""
    results = {
        'timestamp': datetime.now().isoformat(),
        'models': {},
        'data_sources': {},
        'summary': {
            'ready': 0,
            'blocked': 0,
            'trained': 0,
        }
    }

    try:
        conn = get_connection()
        cursor = conn.cursor()
    except Exception as e:
        return {
            'error': str(e),
            'message': 'Cannot connect to database. Set DATABASE_URL environment variable.'
        }

    # Check all data source tables
    all_tables = set()
    for model in ML_MODELS.values():
        all_tables.update(model['data_tables'])

    # Also check alternative data sources
    all_tables.update(['gex_history', 'orat_options_eod', 'options_snapshots'])

    for table in sorted(all_tables):
        count, min_date, max_date = check_table_count(cursor, table)
        results['data_sources'][table] = {
            'count': count,
            'min_date': min_date,
            'max_date': max_date,
            'exists': count >= 0
        }

    # Check GEX from Tradier/live data
    tradier_gex = check_gex_from_tradier(cursor)
    results['tradier_data'] = tradier_gex

    # Evaluate each model
    for model_id, config in ML_MODELS.items():
        model_result = {
            'name': config['name'],
            'description': config['description'],
            'priority': config['priority'],
            'used_by': config['used_by'],
            'train_script': config['train_script'],
            'min_records': config['min_records'],
            'status': 'UNKNOWN',
            'data_available': 0,
            'data_needed': config['min_records'],
            'blocking_reason': None,
            'tables_checked': {},
        }

        # Check if model already exists
        if check_model_exists(config):
            model_result['status'] = 'TRAINED'
            results['summary']['trained'] += 1
            results['models'][model_id] = model_result
            continue

        # Check data availability across all tables
        max_count = 0
        best_table = None

        for table in config['data_tables']:
            table_data = results['data_sources'].get(table, {})
            count = table_data.get('count', 0)
            model_result['tables_checked'][table] = count

            if count > max_count:
                max_count = count
                best_table = table

        model_result['data_available'] = max_count
        model_result['best_data_source'] = best_table

        # Determine status
        if max_count >= config['min_records']:
            model_result['status'] = 'READY'
            results['summary']['ready'] += 1
        else:
            model_result['status'] = 'BLOCKED'
            results['summary']['blocked'] += 1
            model_result['blocking_reason'] = f"Need {config['min_records']} records, have {max_count}"

            # Suggest how to get the data
            if model_id in ['gex_probability', 'gex_directional']:
                if results['data_sources'].get('orat_options_eod', {}).get('count', 0) > 0:
                    model_result['fix'] = 'Run: python scripts/populate_gex_structures.py'
                elif tradier_gex['gex_history']['count'] > 20:
                    model_result['fix'] = 'GEX snapshots available - need populate script for structure'
                else:
                    model_result['fix'] = 'Need historical options data (ORAT) or more GEX snapshots'
            elif model_id == 'oracle':
                model_result['fix'] = 'Run backtests or accumulate live trading outcomes'
            elif model_id == 'prometheus':
                model_result['fix'] = 'Run: python scripts/train_prometheus_model.py --generate-synthetic'

        results['models'][model_id] = model_result

    conn.close()
    return results


def print_results(results: Dict):
    """Print human-readable results"""
    print("\n" + "=" * 70)
    print("ML MODEL TRAINING READINESS CHECK")
    print("=" * 70)
    print(f"Timestamp: {results.get('timestamp', 'N/A')}")

    if 'error' in results:
        print(f"\nERROR: {results['error']}")
        print(results.get('message', ''))
        return

    # Data Sources Summary
    print("\n" + "-" * 70)
    print("DATA SOURCES")
    print("-" * 70)
    print(f"{'Table':<35} {'Records':>10} {'Date Range':>25}")
    print("-" * 70)

    for table, data in sorted(results['data_sources'].items()):
        count = data['count']
        if count < 0:
            count_str = "NOT FOUND"
            date_range = ""
        elif count == 0:
            count_str = "0 (empty)"
            date_range = ""
        else:
            count_str = f"{count:,}"
            if data['min_date'] and data['max_date']:
                date_range = f"{data['min_date']} to {data['max_date']}"
            else:
                date_range = ""

        print(f"{table:<35} {count_str:>10} {date_range:>25}")

    # Tradier/Live Data
    if results.get('tradier_data'):
        td = results['tradier_data']
        if td['gex_history']['count'] > 0:
            print(f"\nLive GEX Snapshots: {td['gex_history']['count']} records")
            if td['can_populate_structure']:
                print("  -> Can potentially populate gex_structure_daily from this data")

    # Model Status
    print("\n" + "-" * 70)
    print("MODEL STATUS")
    print("-" * 70)

    status_icons = {
        'READY': '✅ READY',
        'BLOCKED': '❌ BLOCKED',
        'TRAINED': '🎯 TRAINED',
        'UNKNOWN': '❓ UNKNOWN'
    }

    for model_id, model in results['models'].items():
        status = status_icons.get(model['status'], model['status'])
        print(f"\n{model['name']}")
        print(f"  Status: {status}")
        print(f"  Priority: {model['priority']}")
        print(f"  Used by: {', '.join(model['used_by'])}")
        print(f"  Data: {model['data_available']}/{model['data_needed']} records")

        if model['status'] == 'READY':
            print(f"  Train: python {model['train_script']}")
        elif model['status'] == 'BLOCKED':
            print(f"  Reason: {model['blocking_reason']}")
            if model.get('fix'):
                print(f"  Fix: {model['fix']}")

    # Summary
    print("\n" + "-" * 70)
    print("SUMMARY")
    print("-" * 70)
    summary = results['summary']
    total = summary['ready'] + summary['blocked'] + summary['trained']
    print(f"  Ready to train: {summary['ready']}/{total}")
    print(f"  Already trained: {summary['trained']}/{total}")
    print(f"  Blocked (need data): {summary['blocked']}/{total}")

    # Action items
    if summary['ready'] > 0:
        print("\n" + "-" * 70)
        print("RECOMMENDED ACTIONS")
        print("-" * 70)
        print("Run these commands to train available models:\n")

        for model_id, model in results['models'].items():
            if model['status'] == 'READY':
                print(f"  python {model['train_script']}")

        print("\nOr run: python scripts/check_ml_training_readiness.py --train-all")

    print("\n" + "=" * 70)


def train_ready_models(results: Dict) -> Dict:
    """Train all models that are ready"""
    trained = []
    failed = []

    for model_id, model in results['models'].items():
        if model['status'] == 'READY':
            print(f"\n{'='*60}")
            print(f"Training: {model['name']}")
            print(f"{'='*60}")

            try:
                import subprocess
                result = subprocess.run(
                    ['python', model['train_script']],
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minute timeout
                )

                if result.returncode == 0:
                    print(f"SUCCESS: {model['name']}")
                    trained.append(model_id)
                else:
                    print(f"FAILED: {model['name']}")
                    print(result.stderr)
                    failed.append(model_id)

            except Exception as e:
                print(f"ERROR: {e}")
                failed.append(model_id)

    return {
        'trained': trained,
        'failed': failed
    }


def main():
    parser = argparse.ArgumentParser(description='Check ML Training Readiness')
    parser.add_argument('--train-all', action='store_true',
                       help='Train all ready models')
    parser.add_argument('--json', action='store_true',
                       help='Output as JSON')
    args = parser.parse_args()

    results = check_all_models()

    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return

    print_results(results)

    if args.train_all and results.get('summary', {}).get('ready', 0) > 0:
        print("\n" + "=" * 70)
        print("TRAINING ALL READY MODELS")
        print("=" * 70)

        train_results = train_ready_models(results)

        print("\n" + "-" * 70)
        print("TRAINING COMPLETE")
        print("-" * 70)
        print(f"  Trained: {len(train_results['trained'])}")
        print(f"  Failed: {len(train_results['failed'])}")

        if train_results['failed']:
            print(f"\n  Failed models: {', '.join(train_results['failed'])}")


if __name__ == '__main__':
    main()
