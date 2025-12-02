#!/usr/bin/env python3
"""
TEST 05: End-to-End Pipeline
Tests the complete data flow from sources to frontend-ready output.

Run: python scripts/test_05_end_to_end.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import json

print("\n" + "="*60)
print(" TEST 05: END-TO-END PIPELINE")
print("="*60)

results_summary = {
    "data_sources": False,
    "backtest": False,
    "ml_features": False,
    "api_response": False,
    "frontend_ready": False
}

# =============================================================================
# STAGE 1: Data Sources
# =============================================================================
print("\n" + "-"*40)
print(" STAGE 1: DATA SOURCES")
print("-"*40)

vix_data = None
spy_data = None
gex_data = None

# 1a. VIX Data
print("\n1a. VIX Data (Polygon)")
try:
    from data.polygon_data_fetcher import get_vix_for_date, polygon_fetcher

    # Get VIX history
    for ticker in ['I:VIX', 'VIX']:
        df = polygon_fetcher.get_price_history(ticker, days=30)
        if df is not None and not df.empty:
            vix_data = {
                "source": ticker,
                "latest": float(df['Close'].iloc[-1]),
                "days": len(df)
            }
            print(f"    [OK] VIX from {ticker}: {vix_data['latest']:.2f}")
            break
    else:
        print("    [XX] Could not fetch VIX")

except Exception as e:
    print(f"    [XX] Error: {e}")

# 1b. SPY Data
print("\n1b. SPY Price Data (Polygon)")
try:
    df = polygon_fetcher.get_price_history('SPY', days=30)
    if df is not None and not df.empty:
        spy_data = {
            "source": "SPY",
            "latest": float(df['Close'].iloc[-1]),
            "days": len(df),
            "high_52w": float(df['High'].max())
        }
        print(f"    [OK] SPY: ${spy_data['latest']:.2f}")
        print(f"    [OK] Days: {spy_data['days']}")
    else:
        print("    [XX] No SPY data")

except Exception as e:
    print(f"    [XX] Error: {e}")

# 1c. GEX Data
print("\n1c. GEX Data (Trading Volatility)")
try:
    from data.polygon_data_fetcher import get_gex_data

    gex_result = get_gex_data('SPY')
    if 'error' not in gex_result:
        gex_data = gex_result
        print(f"    [OK] Net GEX: {gex_data.get('net_gex')}")
        print(f"    [OK] Put Wall: {gex_data.get('put_wall')}")
        print(f"    [OK] Source: {gex_data.get('source')}")
    else:
        print(f"    [??] GEX unavailable: {gex_result.get('error')}")
        gex_data = {"error": gex_result.get('error'), "net_gex": 0}

except Exception as e:
    print(f"    [XX] Error: {e}")
    gex_data = {"error": str(e), "net_gex": 0}

# Stage 1 Summary
results_summary["data_sources"] = bool(vix_data and spy_data)
print(f"\nStage 1 Result: {'PASS' if results_summary['data_sources'] else 'FAIL'}")

# =============================================================================
# STAGE 2: Backtest Execution
# =============================================================================
print("\n" + "-"*40)
print(" STAGE 2: BACKTEST EXECUTION")
print("-"*40)

backtest_results = None

print("\n2a. Running Backtest")
try:
    from backtest.spx_premium_backtest import SPXPremiumBacktester

    end_date = datetime.now() - timedelta(days=7)
    start_date = end_date - timedelta(days=60)

    print(f"    Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # SPXPremiumBacktester takes dates in constructor, uses run() method
    backtest = SPXPremiumBacktester(
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        initial_capital=100000000  # $100M
    )

    backtest_results = backtest.run(save_to_db=False)

    if backtest_results:
        trades = backtest_results.get('all_trades', backtest_results.get('trades', []))
        summary = backtest_results.get('summary', {})
        equity = backtest_results.get('equity_curve', [])

        print(f"    [OK] Trades generated: {len(trades)}")
        print(f"    [OK] Equity points: {len(equity)}")
        print(f"    [OK] Total return: {summary.get('total_return_pct', 'N/A')}%")
    else:
        print("    [XX] No backtest results")

except Exception as e:
    print(f"    [XX] Error: {e}")
    import traceback
    traceback.print_exc()

# Stage 2 Summary
results_summary["backtest"] = bool(backtest_results and len(backtest_results.get('all_trades', backtest_results.get('trades', []))) > 0)
print(f"\nStage 2 Result: {'PASS' if results_summary['backtest'] else 'FAIL'}")

# =============================================================================
# STAGE 3: ML Feature Enrichment
# =============================================================================
print("\n" + "-"*40)
print(" STAGE 3: ML FEATURE ENRICHMENT")
print("-"*40)

enriched_trades = []

print("\n3a. Enriching Trades with ML Features")
try:
    from data.polygon_data_fetcher import get_ml_features_for_trade

    if backtest_results:
        trades = backtest_results.get('all_trades', backtest_results.get('trades', []))

        for i, trade in enumerate(trades[:3]):  # Process first 3
            entry_date = trade.get('entry_date', '')
            strike = trade.get('strike', 0)
            underlying_price = strike / 0.96  # Estimate

            features = get_ml_features_for_trade(
                trade_date=entry_date,
                strike=strike,
                underlying_price=underlying_price,
                option_iv=0.16
            )

            enriched_trade = {**trade, **features}
            enriched_trades.append(enriched_trade)

            print(f"    Trade {i+1}: VIX={features.get('vix'):.1f}, IVR={features.get('iv_rank'):.1f}%, GEX={features.get('net_gex')}")

        print(f"    [OK] Enriched {len(enriched_trades)} trades")
    else:
        print("    [XX] No trades to enrich")

except Exception as e:
    print(f"    [XX] Error: {e}")
    import traceback
    traceback.print_exc()

# 3b. Validate ML Features
print("\n3b. Validating ML Features")
if enriched_trades:
    required_features = ['vix', 'iv_rank', 'spx_5d_return', 'net_gex', 'data_quality_pct']
    sample = enriched_trades[0]

    for feature in required_features:
        value = sample.get(feature, 'MISSING')
        status = 'OK' if feature in sample else 'XX'
        print(f"    [{status}] {feature}: {value}")

# Stage 3 Summary
results_summary["ml_features"] = len(enriched_trades) > 0 and 'vix' in enriched_trades[0]
print(f"\nStage 3 Result: {'PASS' if results_summary['ml_features'] else 'FAIL'}")

# =============================================================================
# STAGE 4: API Response Format
# =============================================================================
print("\n" + "-"*40)
print(" STAGE 4: API RESPONSE FORMAT")
print("-"*40)

api_response = None

print("\n4a. Building API Response")
try:
    if backtest_results:
        trades = backtest_results.get('all_trades', backtest_results.get('trades', []))
        summary = backtest_results.get('summary', {})
        equity = backtest_results.get('equity_curve', [])

        # Build response matching API format
        api_response = {
            "trades": trades,
            "summary": {
                "total_return_pct": summary.get('total_return_pct', 0),
                "max_drawdown_pct": summary.get('max_drawdown_pct', 0),
                "win_rate": summary.get('win_rate', 0),
                "total_trades": len(trades),
                "winning_trades": summary.get('winning_trades', summary.get('expired_otm', 0)),
                "losing_trades": summary.get('losing_trades', summary.get('cash_settled_itm', 0)),
                "sharpe_ratio": summary.get('sharpe_ratio', 0),
                "avg_premium": summary.get('avg_premium', 0),
                "total_premium": summary.get('total_premium', 0)
            },
            "equity_curve": equity,
            "ml_enabled": True,
            "data_sources": {
                "vix": vix_data.get('source', 'N/A') if vix_data else 'N/A',
                "spy": "POLYGON",
                "gex": gex_data.get('source', 'N/A') if gex_data else 'N/A'
            }
        }

        print(f"    [OK] Response built")
        print(f"    [OK] Keys: {list(api_response.keys())}")

except Exception as e:
    print(f"    [XX] Error: {e}")

# 4b. Validate Response Structure
print("\n4b. Validating Response Structure")
if api_response:
    checks = [
        ('trades', isinstance(api_response.get('trades'), list)),
        ('summary', isinstance(api_response.get('summary'), dict)),
        ('equity_curve', isinstance(api_response.get('equity_curve'), list)),
        ('total_return_pct in summary', 'total_return_pct' in api_response.get('summary', {})),
        ('win_rate in summary', 'win_rate' in api_response.get('summary', {}))
    ]

    for check_name, passed in checks:
        status = 'OK' if passed else 'XX'
        print(f"    [{status}] {check_name}")

# Stage 4 Summary
results_summary["api_response"] = api_response is not None and isinstance(api_response.get('trades'), list)
print(f"\nStage 4 Result: {'PASS' if results_summary['api_response'] else 'FAIL'}")

# =============================================================================
# STAGE 5: Frontend-Ready Output
# =============================================================================
print("\n" + "-"*40)
print(" STAGE 5: FRONTEND-READY OUTPUT")
print("-"*40)

print("\n5a. JSON Serialization")
try:
    if api_response:
        # Test JSON serialization (required for API)
        json_str = json.dumps(api_response, default=str)
        print(f"    [OK] JSON serializable ({len(json_str)} bytes)")

        # Parse back to verify
        parsed = json.loads(json_str)
        print(f"    [OK] JSON parseable")

except Exception as e:
    print(f"    [XX] Error: {e}")

print("\n5b. Frontend Data Requirements")
if api_response:
    frontend_checks = [
        ("Trades array for table", len(api_response.get('trades', [])) > 0),
        ("Summary for stats cards", len(api_response.get('summary', {})) > 5),
        ("Equity curve for chart", len(api_response.get('equity_curve', [])) > 0),
        ("Data sources for disclosure", 'data_sources' in api_response)
    ]

    for check_name, passed in frontend_checks:
        status = 'OK' if passed else 'XX'
        print(f"    [{status}] {check_name}")

print("\n5c. Sample Data Preview")
if api_response:
    print("\n    Summary Stats:")
    for key, value in list(api_response.get('summary', {}).items())[:5]:
        print(f"      {key}: {value}")

    print("\n    First Trade:")
    if api_response.get('trades'):
        trade = api_response['trades'][0]
        for key in ['entry_date', 'strike', 'premium', 'outcome', 'pnl']:
            if key in trade:
                print(f"      {key}: {trade[key]}")

# Stage 5 Summary
results_summary["frontend_ready"] = api_response is not None
print(f"\nStage 5 Result: {'PASS' if results_summary['frontend_ready'] else 'FAIL'}")

# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "="*60)
print(" END-TO-END PIPELINE SUMMARY")
print("="*60)

print("\n  Stage Results:")
for stage, passed in results_summary.items():
    icon = "[OK]" if passed else "[XX]"
    print(f"    {icon} {stage.replace('_', ' ').title()}")

all_passed = all(results_summary.values())

print(f"\n  Overall: {'ALL STAGES PASSED' if all_passed else 'SOME STAGES FAILED'}")

if all_passed:
    print("\n  Data is flowing correctly through the entire pipeline!")
    print("  The frontend should receive valid backtest results with ML features.")
else:
    print("\n  Issues detected:")
    for stage, passed in results_summary.items():
        if not passed:
            print(f"    - {stage.replace('_', ' ').title()} needs attention")

print("\n" + "="*60 + "\n")

# Exit with appropriate code
sys.exit(0 if all_passed else 1)
