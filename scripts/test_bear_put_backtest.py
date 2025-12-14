#!/usr/bin/env python3
"""
Test Bear Put Spread backtest and compare with other directional strategies.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester
from datetime import datetime, timedelta

def run_strategy_backtest(strategy_type: str, start_date: str, end_date: str):
    """Run backtest for a specific strategy"""
    print(f"\n{'='*60}")
    print(f"Running {strategy_type.upper()} backtest: {start_date} to {end_date}")
    print(f"{'='*60}")

    try:
        backtester = HybridFixedBacktester(
            ticker='SPX',
            start_date=start_date,
            end_date=end_date,
            initial_capital=100000,
            strategy_type=strategy_type,
            spread_width=5,
            sd_multiplier=1.0,
        )

        results = backtester.run()

        if results:
            print(f"\n📊 {strategy_type.upper()} Results:")
            print(f"   Total Trades: {results.get('total_trades', 0)}")
            print(f"   Win Rate: {results.get('win_rate', 0):.1f}%")
            print(f"   Total P&L: ${results.get('total_pnl', 0):,.2f}")
            print(f"   Total Return: {results.get('total_return', 0):.2f}%")
            print(f"   Profit Factor: {results.get('profit_factor', 0):.2f}")
            print(f"   Max Drawdown: {results.get('max_drawdown_pct', 0):.2f}%")
            print(f"   Sharpe Ratio: {results.get('sharpe_ratio', 0):.2f}")

            # Avg win/loss
            avg_win = results.get('avg_win', 0)
            avg_loss = results.get('avg_loss', 0)
            print(f"   Avg Win: ${avg_win:,.2f}")
            print(f"   Avg Loss: ${avg_loss:,.2f}")

            return results
        else:
            print(f"   ❌ No results returned")
            return None

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    # Use last 3 months of data
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    print(f"\n🔬 DIRECTIONAL STRATEGY COMPARISON")
    print(f"Period: {start_date} to {end_date}")
    print(f"Ticker: SPX, Spread Width: $5, 0-DTE")

    strategies = [
        'bear_put',      # Bearish debit
        'bull_call',     # Bullish debit
        'bear_call',     # Bearish credit
        'bull_put',      # Bullish credit
        'apache_directional',  # GEX-based adaptive
    ]

    results_summary = {}

    for strategy in strategies:
        result = run_strategy_backtest(strategy, start_date, end_date)
        if result:
            results_summary[strategy] = {
                'trades': result.get('total_trades', 0),
                'win_rate': result.get('win_rate', 0),
                'pnl': result.get('total_pnl', 0),
                'profit_factor': result.get('profit_factor', 0),
                'sharpe': result.get('sharpe_ratio', 0)
            }

    # Print comparison table
    print(f"\n{'='*80}")
    print("📈 STRATEGY COMPARISON SUMMARY")
    print(f"{'='*80}")
    print(f"{'Strategy':<20} {'Trades':>8} {'Win%':>8} {'P&L':>12} {'PF':>8} {'Sharpe':>8}")
    print(f"{'-'*80}")

    for strategy, data in sorted(results_summary.items(), key=lambda x: x[1]['pnl'], reverse=True):
        print(f"{strategy:<20} {data['trades']:>8} {data['win_rate']:>7.1f}% ${data['pnl']:>10,.0f} {data['profit_factor']:>8.2f} {data['sharpe']:>8.2f}")


if __name__ == "__main__":
    main()
