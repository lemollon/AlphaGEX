"""
Master Backtest Runner

Runs ALL AlphaGEX backtests and generates comparison dashboard:
- Psychology Trap Detection (13 patterns)
- GEX Strategies (5 strategies)
- Options Strategies (11 strategies)
- Combined performance analysis

Usage:
    python run_all_backtests.py --symbol SPY --start 2022-01-01 --end 2024-12-31
"""

import argparse
from datetime import datetime
from backtest_gex_strategies import GEXBacktester
from backtest_options_strategies import OptionsBacktester
from psychology_backtest import PsychologyBacktester
from database_adapter import get_connection


class MasterBacktestRunner:
    """Run all backtests and generate comparison dashboard"""

    def __init__(self, symbol: str, start_date: str, end_date: str):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.results = {}

    def run_all(self):
        """Run all backtests sequentially"""
        print("\n" + "=" * 80)
        print("🚀 ALPHAGEX MASTER BACKTEST - RUNNING ALL STRATEGIES")
        print("=" * 80)
        print(f"Symbol: {self.symbol}")
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80 + "\n")

        # 1. Psychology Trap Detection
        print("\n" + "🧠 " + "="*75)
        print("1. PSYCHOLOGY TRAP DETECTION (13 Patterns)")
        print("="*77)
        try:
            psych_backtester = PsychologyBacktester(symbol=self.symbol)
            # PsychologyBacktester has different interface - uses separate methods
            # For now, skip it as it needs database data, not just price history
            print("⚠️ Psychology backtest requires historical regime signal data from database")
            print("   Use psychology_backtest.py directly after running the system for 90+ days")
            self.results['psychology'] = None
        except Exception as e:
            print(f"❌ Psychology backtest failed: {e}")
            self.results['psychology'] = None

        # 2. GEX Strategies
        print("\n" + "🎯 " + "="*75)
        print("2. GEX STRATEGIES (5 Strategies)")
        print("="*77)
        try:
            gex_backtester = GEXBacktester(
                symbol=self.symbol,
                start_date=self.start_date,
                end_date=self.end_date
            )
            self.results['gex'] = gex_backtester.run_backtest()
        except Exception as e:
            print(f"❌ GEX backtest failed: {e}")
            self.results['gex'] = None

        # 3. Options Strategies
        print("\n" + "📊 " + "="*75)
        print("3. OPTIONS STRATEGIES (11 Strategies)")
        print("="*77)
        try:
            options_backtester = OptionsBacktester(
                symbol=self.symbol,
                start_date=self.start_date,
                end_date=self.end_date
            )
            self.results['options'] = options_backtester.run_backtest()
        except Exception as e:
            print(f"❌ Options backtest failed: {e}")
            self.results['options'] = None

        # Generate comparison dashboard
        self.generate_dashboard()

    def generate_dashboard(self):
        """Generate comprehensive comparison dashboard"""
        print("\n" + "=" * 80)
        print("📊 BACKTEST COMPARISON DASHBOARD")
        print("=" * 80)

        # Filter out None results
        valid_results = {k: v for k, v in self.results.items() if v is not None}

        if not valid_results:
            print("❌ No valid backtest results to compare")
            return

        # Print comparison table
        print(f"\n{'Strategy Category':<25} {'Trades':<8} {'Win%':<8} {'Expect%':<10} {'Return%':<10} {'Status':<15}")
        print("-" * 80)

        for category, result in valid_results.items():
            status = self.get_status(result)
            print(f"{category.upper():<25} {result.total_trades:<8} {result.win_rate:<8.1f} "
                  f"{result.expectancy_pct:<10.2f} {result.total_return_pct:<10.2f} {status:<15}")

        # Best performing strategy
        print("\n" + "=" * 80)
        if valid_results:
            best_category = max(valid_results.items(), key=lambda x: x[1].expectancy_pct)
            print(f"🏆 BEST PERFORMING: {best_category[0].upper()}")
            print(f"   Expectancy: {best_category[1].expectancy_pct:+.2f}% per trade")
            print(f"   Win Rate: {best_category[1].win_rate:.1f}%")
            print(f"   Total Return: {best_category[1].total_return_pct:+.2f}%")

        # Recommendations
        print("\n" + "=" * 80)
        print("💡 RECOMMENDATIONS")
        print("=" * 80)

        profitable_strategies = [
            (cat, res) for cat, res in valid_results.items()
            if res.expectancy_pct > 0.5 and res.win_rate > 55
        ]

        if profitable_strategies:
            print("\n✅ PROFITABLE STRATEGIES (Safe to paper trade):")
            for cat, res in profitable_strategies:
                print(f"   - {cat.upper()}: {res.expectancy_pct:+.2f}% expectancy, {res.win_rate:.1f}% win rate")
        else:
            print("\n⚠️  NO HIGHLY PROFITABLE STRATEGIES FOUND")
            print("   All strategies need improvement before trading")

        marginal_strategies = [
            (cat, res) for cat, res in valid_results.items()
            if 0 < res.expectancy_pct <= 0.5 or 50 < res.win_rate <= 55
        ]

        if marginal_strategies:
            print("\n⚠️  MARGINAL STRATEGIES (Proceed with caution):")
            for cat, res in marginal_strategies:
                print(f"   - {cat.upper()}: {res.expectancy_pct:+.2f}% expectancy, {res.win_rate:.1f}% win rate")

        losing_strategies = [
            (cat, res) for cat, res in valid_results.items()
            if res.expectancy_pct <= 0 or res.win_rate <= 50
        ]

        if losing_strategies:
            print("\n❌ LOSING STRATEGIES (Do not trade these):")
            for cat, res in losing_strategies:
                print(f"   - {cat.upper()}: {res.expectancy_pct:+.2f}% expectancy, {res.win_rate:.1f}% win rate")

        print("\n" + "=" * 80)
        print("🎯 NEXT STEPS")
        print("=" * 80)
        print("1. Review individual strategy results in database")
        print("2. Paper trade ONLY the profitable strategies for 90 days")
        print("3. Start with smallest position sizes ($100-200 per trade)")
        print("4. Track actual vs backtested performance")
        print("5. Scale up ONLY if results hold in paper trading")
        print("=" * 80 + "\n")

    def get_status(self, result) -> str:
        """Get status label based on performance"""
        if result.expectancy_pct > 0.5 and result.win_rate > 55:
            return "✅ PROFITABLE"
        elif result.expectancy_pct > 0 and result.win_rate > 50:
            return "⚠️ MARGINAL"
        else:
            return "❌ LOSING"

    def export_summary(self):
        """Export summary to database"""
        conn = get_connection()
        c = conn.cursor()

        # Check if table exists with old schema and drop it
        c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename='backtest_summary'")
        if c.fetchone():
            # Check schema
            c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='backtest_summary'")
            columns = [row[0] for row in c.fetchall()]
            # If old schema (missing 'symbol' column), drop and recreate
            if 'symbol' not in columns:
                print("🔄 Dropping old backtest_summary table (wrong schema)")
                c.execute("DROP TABLE backtest_summary")
                conn.commit()

        c.execute('''
            CREATE TABLE IF NOT EXISTS backtest_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT,
                start_date TEXT,
                end_date TEXT,
                psychology_trades INTEGER,
                psychology_win_rate REAL,
                psychology_expectancy REAL,
                gex_trades INTEGER,
                gex_win_rate REAL,
                gex_expectancy REAL,
                options_trades INTEGER,
                options_win_rate REAL,
                options_expectancy REAL
            )
        ''')

        c.execute('''
            INSERT INTO backtest_summary (
                symbol, start_date, end_date,
                psychology_trades, psychology_win_rate, psychology_expectancy,
                gex_trades, gex_win_rate, gex_expectancy,
                options_trades, options_win_rate, options_expectancy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            self.symbol, self.start_date, self.end_date,
            self.results.get('psychology').total_trades if self.results.get('psychology') else 0,
            self.results.get('psychology').win_rate if self.results.get('psychology') else 0,
            self.results.get('psychology').expectancy_pct if self.results.get('psychology') else 0,
            self.results.get('gex').total_trades if self.results.get('gex') else 0,
            self.results.get('gex').win_rate if self.results.get('gex') else 0,
            self.results.get('gex').expectancy_pct if self.results.get('gex') else 0,
            self.results.get('options').total_trades if self.results.get('options') else 0,
            self.results.get('options').win_rate if self.results.get('options') else 0,
            self.results.get('options').expectancy_pct if self.results.get('options') else 0
        ))

        conn.commit()
        conn.close()

        print("✓ Exported summary to database (backtest_summary table)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run all AlphaGEX backtests')
    parser.add_argument('--symbol', default='SPY', help='Symbol to backtest')
    parser.add_argument('--start', default='2022-01-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', default='2024-12-31', help='End date YYYY-MM-DD')
    args = parser.parse_args()

    runner = MasterBacktestRunner(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end
    )

    runner.run_all()
    runner.export_summary()

    print("\n✅ ALL BACKTESTS COMPLETE!")
    print("Results saved to database (PostgreSQL)")
    print("Check backtest_results and backtest_summary tables for full details\n")
