"""
STRATEGY TESTER REPORT - Institutional Quality Backtest Statistics

This produces a report like the MT4/MT5 Strategy Tester with:
- Profit Factor
- Expected Payoff
- Consecutive Wins/Losses
- Largest/Average Profit/Loss
- DATA QUALITY PERCENTAGE (critical for trust)
- Equity Curve

The DATA QUALITY % shows what percentage of prices came from REAL data
vs ESTIMATED. If this is below 80%, the backtest is unreliable.

Like the MT4 warning: "Modelling quality does not match" = FAKE BACKTEST
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class TradeRecord:
    """Single trade for analysis"""
    trade_id: int
    entry_date: str
    exit_date: str
    symbol: str
    direction: str  # 'SHORT_PUT', 'LONG_CALL', etc.
    entry_price: float
    exit_price: float
    contracts: int
    pnl: float
    pnl_pct: float
    price_source: str  # 'POLYGON_HISTORICAL', 'TRADIER_LIVE', 'ESTIMATED'
    is_winner: bool


@dataclass
class StrategyReport:
    """
    Complete Strategy Tester Report - like MT4/MT5

    This is what a billionaire trader needs to see before deploying capital.
    """
    # === HEADER ===
    strategy_name: str
    symbol: str
    period: str  # "2022-01-01 to 2024-12-01"
    timeframe: str  # "Daily"
    initial_capital: float
    final_equity: float

    # === DATA QUALITY (CRITICAL) ===
    data_quality_pct: float  # % of prices from REAL data (not estimated)
    real_data_points: int
    estimated_data_points: int
    data_source: str  # "POLYGON_HISTORICAL"

    # === PERFORMANCE SUMMARY ===
    total_net_profit: float
    gross_profit: float
    gross_loss: float
    profit_factor: float  # gross_profit / abs(gross_loss) - KEY METRIC
    expected_payoff: float  # avg profit per trade
    absolute_drawdown: float
    maximal_drawdown: float
    maximal_drawdown_pct: float
    relative_drawdown_pct: float

    # === TRADE STATISTICS ===
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_trades_pct: float  # winning / total * 100

    # === PROFIT/LOSS ANALYSIS ===
    largest_profit_trade: float
    largest_loss_trade: float
    average_profit_trade: float
    average_loss_trade: float
    avg_win_loss_ratio: float  # avg_profit / abs(avg_loss)

    # === CONSECUTIVE ANALYSIS (shows strategy stability) ===
    max_consecutive_wins: int
    max_consecutive_wins_profit: float
    max_consecutive_losses: int
    max_consecutive_losses_amount: float
    avg_consecutive_wins: float
    avg_consecutive_losses: float

    # === TIMING ===
    avg_trade_duration_days: float
    longest_trade_days: int
    shortest_trade_days: int

    # === RISK METRICS ===
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float  # annual return / max drawdown

    # === RAW DATA ===
    all_trades: List[Dict]
    equity_curve: List[Dict]  # date, equity, drawdown

    def to_dict(self) -> Dict:
        return asdict(self)


class StrategyReportGenerator:
    """
    Generates institutional-quality backtest reports.

    INPUT: List of trades from any backtester
    OUTPUT: StrategyReport with all the statistics a serious trader needs
    """

    def __init__(
        self,
        strategy_name: str,
        symbol: str,
        initial_capital: float,
        start_date: str,
        end_date: str
    ):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.start_date = start_date
        self.end_date = end_date

        self.trades: List[TradeRecord] = []
        self.equity_curve: List[Dict] = []

    def add_trade(
        self,
        trade_id: int,
        entry_date: str,
        exit_date: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        contracts: int,
        pnl: float,
        price_source: str
    ):
        """Add a trade to the report"""
        pnl_pct = (pnl / (entry_price * 100 * contracts)) * 100 if entry_price > 0 else 0

        trade = TradeRecord(
            trade_id=trade_id,
            entry_date=entry_date,
            exit_date=exit_date,
            symbol=self.symbol,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            contracts=contracts,
            pnl=pnl,
            pnl_pct=pnl_pct,
            price_source=price_source,
            is_winner=pnl > 0
        )
        self.trades.append(trade)

    def add_equity_point(self, date: str, equity: float, drawdown_pct: float):
        """Add a point to the equity curve"""
        self.equity_curve.append({
            'date': date,
            'equity': equity,
            'drawdown_pct': drawdown_pct
        })

    def generate(self) -> StrategyReport:
        """Generate the complete report"""
        if not self.trades:
            raise ValueError("No trades to analyze")

        # === DATA QUALITY ===
        real_count = sum(1 for t in self.trades if t.price_source != 'ESTIMATED')
        estimated_count = sum(1 for t in self.trades if t.price_source == 'ESTIMATED')
        total_points = real_count + estimated_count
        data_quality = (real_count / total_points * 100) if total_points > 0 else 0

        # === BASIC STATS ===
        pnls = [t.pnl for t in self.trades]
        winning_trades = [t for t in self.trades if t.is_winner]
        losing_trades = [t for t in self.trades if not t.is_winner]

        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = sum(t.pnl for t in losing_trades)  # This will be negative
        total_net_profit = sum(pnls)
        final_equity = self.initial_capital + total_net_profit

        # === PROFIT FACTOR ===
        # This is THE key metric - gross profit / abs(gross loss)
        # > 1.5 is good, > 2.0 is excellent, > 3.0 is exceptional
        profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')

        # === EXPECTED PAYOFF ===
        expected_payoff = total_net_profit / len(self.trades)

        # === DRAWDOWN ===
        equity = self.initial_capital
        peak_equity = equity
        max_drawdown = 0
        max_drawdown_pct = 0
        absolute_drawdown = 0

        for trade in self.trades:
            equity += trade.pnl
            if equity > peak_equity:
                peak_equity = equity
            drawdown = peak_equity - equity
            drawdown_pct = (drawdown / peak_equity * 100) if peak_equity > 0 else 0

            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct

            if equity < self.initial_capital:
                current_abs_dd = self.initial_capital - equity
                if current_abs_dd > absolute_drawdown:
                    absolute_drawdown = current_abs_dd

        relative_drawdown = max_drawdown_pct

        # === LARGEST/AVERAGE PROFIT/LOSS ===
        largest_profit = max(pnls) if pnls else 0
        largest_loss = min(pnls) if pnls else 0

        avg_profit = (gross_profit / len(winning_trades)) if winning_trades else 0
        avg_loss = (gross_loss / len(losing_trades)) if losing_trades else 0

        avg_win_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')

        # === CONSECUTIVE WINS/LOSSES ===
        max_consec_wins, max_consec_wins_profit = self._calculate_consecutive_wins()
        max_consec_losses, max_consec_losses_amount = self._calculate_consecutive_losses()
        avg_consec_wins = self._calculate_avg_consecutive_wins()
        avg_consec_losses = self._calculate_avg_consecutive_losses()

        # === TRADE DURATION ===
        durations = []
        for t in self.trades:
            try:
                entry = datetime.strptime(t.entry_date[:10], '%Y-%m-%d')
                exit_d = datetime.strptime(t.exit_date[:10], '%Y-%m-%d')
                durations.append((exit_d - entry).days)
            except:
                pass

        avg_duration = sum(durations) / len(durations) if durations else 0
        longest_trade = max(durations) if durations else 0
        shortest_trade = min(durations) if durations else 0

        # === RISK METRICS ===
        sharpe = self._calculate_sharpe_ratio(pnls)
        sortino = self._calculate_sortino_ratio(pnls)
        calmar = self._calculate_calmar_ratio(total_net_profit, max_drawdown)

        return StrategyReport(
            strategy_name=self.strategy_name,
            symbol=self.symbol,
            period=f"{self.start_date} to {self.end_date}",
            timeframe="Daily",
            initial_capital=self.initial_capital,
            final_equity=final_equity,

            # Data quality
            data_quality_pct=data_quality,
            real_data_points=real_count,
            estimated_data_points=estimated_count,
            data_source="POLYGON_HISTORICAL" if data_quality >= 50 else "MOSTLY_ESTIMATED",

            # Performance
            total_net_profit=total_net_profit,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            expected_payoff=expected_payoff,
            absolute_drawdown=absolute_drawdown,
            maximal_drawdown=max_drawdown,
            maximal_drawdown_pct=max_drawdown_pct,
            relative_drawdown_pct=relative_drawdown,

            # Trade stats
            total_trades=len(self.trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate_pct=(len(winning_trades) / len(self.trades) * 100),
            profit_trades_pct=(len(winning_trades) / len(self.trades) * 100),

            # Profit/Loss analysis
            largest_profit_trade=largest_profit,
            largest_loss_trade=largest_loss,
            average_profit_trade=avg_profit,
            average_loss_trade=avg_loss,
            avg_win_loss_ratio=avg_win_loss_ratio,

            # Consecutive
            max_consecutive_wins=max_consec_wins,
            max_consecutive_wins_profit=max_consec_wins_profit,
            max_consecutive_losses=max_consec_losses,
            max_consecutive_losses_amount=max_consec_losses_amount,
            avg_consecutive_wins=avg_consec_wins,
            avg_consecutive_losses=avg_consec_losses,

            # Timing
            avg_trade_duration_days=avg_duration,
            longest_trade_days=longest_trade,
            shortest_trade_days=shortest_trade,

            # Risk
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,

            # Raw data
            all_trades=[asdict(t) for t in self.trades],
            equity_curve=self.equity_curve
        )

    def _calculate_consecutive_wins(self) -> Tuple[int, float]:
        """Calculate max consecutive wins and their total profit"""
        max_streak = 0
        max_streak_profit = 0
        current_streak = 0
        current_profit = 0

        for trade in self.trades:
            if trade.is_winner:
                current_streak += 1
                current_profit += trade.pnl
                if current_streak > max_streak:
                    max_streak = current_streak
                    max_streak_profit = current_profit
            else:
                current_streak = 0
                current_profit = 0

        return max_streak, max_streak_profit

    def _calculate_consecutive_losses(self) -> Tuple[int, float]:
        """Calculate max consecutive losses and their total loss"""
        max_streak = 0
        max_streak_loss = 0
        current_streak = 0
        current_loss = 0

        for trade in self.trades:
            if not trade.is_winner:
                current_streak += 1
                current_loss += trade.pnl  # Will be negative
                if current_streak > max_streak:
                    max_streak = current_streak
                    max_streak_loss = current_loss
            else:
                current_streak = 0
                current_loss = 0

        return max_streak, max_streak_loss

    def _calculate_avg_consecutive_wins(self) -> float:
        """Calculate average consecutive wins"""
        streaks = []
        current = 0
        for trade in self.trades:
            if trade.is_winner:
                current += 1
            else:
                if current > 0:
                    streaks.append(current)
                current = 0
        if current > 0:
            streaks.append(current)
        return sum(streaks) / len(streaks) if streaks else 0

    def _calculate_avg_consecutive_losses(self) -> float:
        """Calculate average consecutive losses"""
        streaks = []
        current = 0
        for trade in self.trades:
            if not trade.is_winner:
                current += 1
            else:
                if current > 0:
                    streaks.append(current)
                current = 0
        if current > 0:
            streaks.append(current)
        return sum(streaks) / len(streaks) if streaks else 0

    def _calculate_sharpe_ratio(self, pnls: List[float]) -> float:
        """Calculate Sharpe ratio (annualized)"""
        if len(pnls) < 2:
            return 0
        import statistics
        avg_return = statistics.mean(pnls)
        std_dev = statistics.stdev(pnls)
        if std_dev == 0:
            return 0
        # Annualize assuming ~12 trades per year for monthly options
        return (avg_return / std_dev) * (12 ** 0.5)

    def _calculate_sortino_ratio(self, pnls: List[float]) -> float:
        """Calculate Sortino ratio (only downside deviation)"""
        if len(pnls) < 2:
            return 0
        import statistics
        avg_return = statistics.mean(pnls)
        downside = [p for p in pnls if p < 0]
        if not downside:
            return float('inf')
        downside_dev = statistics.stdev(downside) if len(downside) > 1 else abs(downside[0])
        if downside_dev == 0:
            return float('inf')
        return (avg_return / downside_dev) * (12 ** 0.5)

    def _calculate_calmar_ratio(self, total_return: float, max_drawdown: float) -> float:
        """Calculate Calmar ratio (return / max drawdown)"""
        if max_drawdown == 0:
            return float('inf')
        return total_return / max_drawdown


def print_strategy_report(report: StrategyReport):
    """Print report in MT4 Strategy Tester style"""
    print("\n")
    print("=" * 80)
    print("                         STRATEGY TESTER REPORT")
    print(f"                         {report.strategy_name}")
    print("=" * 80)
    print()

    # Header
    print(f"{'Symbol':<25} {report.symbol}")
    print(f"{'Period':<25} {report.period}")
    print(f"{'Timeframe':<25} {report.timeframe}")
    print()

    # DATA QUALITY - THE CRITICAL NUMBER
    print("=" * 80)
    quality_status = "✓ RELIABLE" if report.data_quality_pct >= 80 else "⚠️ LOW QUALITY" if report.data_quality_pct >= 50 else "❌ UNRELIABLE"
    print(f"DATA QUALITY:            {report.data_quality_pct:.2f}%   {quality_status}")
    print(f"  Real Data Points:      {report.real_data_points}")
    print(f"  Estimated Points:      {report.estimated_data_points}")
    print(f"  Data Source:           {report.data_source}")
    if report.data_quality_pct < 80:
        print()
        print("  ⚠️  WARNING: Data quality below 80% means backtest results may not")
        print("      reflect real trading performance. Consider this a rough estimate.")
    print("=" * 80)
    print()

    # Performance
    print(f"{'Initial Deposit':<25} {report.initial_capital:>15,.2f}")
    print(f"{'Total Net Profit':<25} {report.total_net_profit:>15,.2f}    "
          f"{'Gross Profit':<20} {report.gross_profit:>12,.2f}")
    print(f"{'Profit Factor':<25} {report.profit_factor:>15.2f}    "
          f"{'Gross Loss':<20} {report.gross_loss:>12,.2f}")
    print(f"{'Expected Payoff':<25} {report.expected_payoff:>15.2f}")
    print()
    print(f"{'Absolute Drawdown':<25} {report.absolute_drawdown:>15,.2f}    "
          f"{'Maximal Drawdown':<20} {report.maximal_drawdown:>12,.2f} ({report.maximal_drawdown_pct:.2f}%)")
    print()

    # Trade statistics
    print(f"{'Total Trades':<25} {report.total_trades:>15}    "
          f"{'Winning Trades':<20} {report.winning_trades:>12} ({report.win_rate_pct:.2f}%)")
    print(f"{'':<25} {'':>15}    "
          f"{'Losing Trades':<20} {report.losing_trades:>12} ({100-report.win_rate_pct:.2f}%)")
    print()

    # Profit/Loss
    print(f"{'Largest':<10} {'profit trade':<15} {report.largest_profit_trade:>12,.2f}    "
          f"{'loss trade':<15} {report.largest_loss_trade:>12,.2f}")
    print(f"{'Average':<10} {'profit trade':<15} {report.average_profit_trade:>12,.2f}    "
          f"{'loss trade':<15} {report.average_loss_trade:>12,.2f}")
    print()

    # Consecutive
    print(f"{'Maximum':<10} {'consecutive wins':<25} {report.max_consecutive_wins:>8} ({report.max_consecutive_wins_profit:>12,.2f})")
    print(f"{'Maximum':<10} {'consecutive losses':<25} {report.max_consecutive_losses:>8} ({report.max_consecutive_losses_amount:>12,.2f})")
    print(f"{'Average':<10} {'consecutive wins':<25} {report.avg_consecutive_wins:>8.1f}")
    print(f"{'Average':<10} {'consecutive losses':<25} {report.avg_consecutive_losses:>8.1f}")
    print()

    # Risk metrics
    print("=" * 80)
    print("RISK METRICS")
    print("=" * 80)
    print(f"{'Sharpe Ratio':<25} {report.sharpe_ratio:>15.2f}")
    print(f"{'Sortino Ratio':<25} {report.sortino_ratio:>15.2f}")
    print(f"{'Calmar Ratio':<25} {report.calmar_ratio:>15.2f}")
    print(f"{'Avg Win/Loss Ratio':<25} {report.avg_win_loss_ratio:>15.2f}")
    print()

    # Trade timing
    print(f"{'Avg Trade Duration':<25} {report.avg_trade_duration_days:>15.1f} days")
    print(f"{'Longest Trade':<25} {report.longest_trade_days:>15} days")
    print(f"{'Shortest Trade':<25} {report.shortest_trade_days:>15} days")
    print()

    # Summary verdict
    print("=" * 80)
    print("VERDICT")
    print("=" * 80)

    issues = []
    strengths = []

    if report.data_quality_pct < 80:
        issues.append(f"Data quality only {report.data_quality_pct:.0f}% - results may not be reliable")
    else:
        strengths.append(f"Data quality {report.data_quality_pct:.0f}% - results are trustworthy")

    if report.profit_factor < 1.5:
        issues.append(f"Profit factor {report.profit_factor:.2f} is low (want > 1.5)")
    elif report.profit_factor >= 2.0:
        strengths.append(f"Excellent profit factor: {report.profit_factor:.2f}")

    if report.maximal_drawdown_pct > 25:
        issues.append(f"Max drawdown {report.maximal_drawdown_pct:.1f}% is high (want < 25%)")
    else:
        strengths.append(f"Acceptable max drawdown: {report.maximal_drawdown_pct:.1f}%")

    if report.win_rate_pct < 60:
        issues.append(f"Win rate {report.win_rate_pct:.1f}% is below target (want > 60%)")
    else:
        strengths.append(f"Strong win rate: {report.win_rate_pct:.1f}%")

    if report.max_consecutive_losses > 5:
        issues.append(f"Max {report.max_consecutive_losses} consecutive losses - expect drawdown periods")

    print("\nSTRENGTHS:")
    for s in strengths:
        print(f"  ✓ {s}")

    print("\nCONCERNS:")
    for i in issues:
        print(f"  ⚠️ {i}")

    if not issues:
        print("  None identified")

    print("\n" + "=" * 80)


def export_report_to_html(report: StrategyReport, filepath: str):
    """Export report to HTML with equity curve chart"""
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Strategy Tester Report - {report.strategy_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: 'Courier New', monospace; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; }}
        h1 {{ text-align: center; border-bottom: 2px solid #333; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
        .data-quality {{ font-size: 24px; font-weight: bold; }}
        .quality-good {{ color: green; }}
        .quality-warn {{ color: orange; }}
        .quality-bad {{ color: red; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 5px 10px; }}
        .metric-label {{ font-weight: bold; }}
        .metric-value {{ text-align: right; }}
        .chart-container {{ height: 400px; margin: 20px 0; }}
    </style>
</head>
<body>
<div class="container">
    <h1>Strategy Tester Report<br>{report.strategy_name}</h1>

    <div class="section">
        <h2>Summary</h2>
        <table>
            <tr><td class="metric-label">Symbol</td><td class="metric-value">{report.symbol}</td></tr>
            <tr><td class="metric-label">Period</td><td class="metric-value">{report.period}</td></tr>
            <tr><td class="metric-label">Initial Capital</td><td class="metric-value">${report.initial_capital:,.2f}</td></tr>
            <tr><td class="metric-label">Final Equity</td><td class="metric-value">${report.final_equity:,.2f}</td></tr>
        </table>
    </div>

    <div class="section">
        <h2>Data Quality</h2>
        <div class="data-quality {'quality-good' if report.data_quality_pct >= 80 else 'quality-warn' if report.data_quality_pct >= 50 else 'quality-bad'}">
            {report.data_quality_pct:.2f}%
        </div>
        <p>Real Data: {report.real_data_points} | Estimated: {report.estimated_data_points}</p>
        <p>{'✓ Results are reliable' if report.data_quality_pct >= 80 else '⚠️ Results may not reflect real trading' if report.data_quality_pct >= 50 else '❌ Results are unreliable - too many estimates'}</p>
    </div>

    <div class="section">
        <h2>Performance</h2>
        <table>
            <tr><td class="metric-label">Total Net Profit</td><td class="metric-value">${report.total_net_profit:,.2f}</td></tr>
            <tr><td class="metric-label">Profit Factor</td><td class="metric-value">{report.profit_factor:.2f}</td></tr>
            <tr><td class="metric-label">Expected Payoff</td><td class="metric-value">${report.expected_payoff:,.2f}</td></tr>
            <tr><td class="metric-label">Max Drawdown</td><td class="metric-value">${report.maximal_drawdown:,.2f} ({report.maximal_drawdown_pct:.2f}%)</td></tr>
        </table>
    </div>

    <div class="section">
        <h2>Trade Statistics</h2>
        <table>
            <tr><td class="metric-label">Total Trades</td><td class="metric-value">{report.total_trades}</td></tr>
            <tr><td class="metric-label">Win Rate</td><td class="metric-value">{report.win_rate_pct:.2f}%</td></tr>
            <tr><td class="metric-label">Max Consecutive Wins</td><td class="metric-value">{report.max_consecutive_wins}</td></tr>
            <tr><td class="metric-label">Max Consecutive Losses</td><td class="metric-value">{report.max_consecutive_losses}</td></tr>
        </table>
    </div>

    <div class="section">
        <h2>Equity Curve</h2>
        <div class="chart-container">
            <canvas id="equityChart"></canvas>
        </div>
    </div>
</div>

<script>
const ctx = document.getElementById('equityChart').getContext('2d');
const equityData = {json.dumps(report.equity_curve)};

new Chart(ctx, {{
    type: 'line',
    data: {{
        labels: equityData.map(d => d.date),
        datasets: [{{
            label: 'Equity',
            data: equityData.map(d => d.equity),
            borderColor: 'rgb(75, 192, 75)',
            backgroundColor: 'rgba(75, 192, 75, 0.1)',
            fill: true
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        scales: {{
            y: {{
                beginAtZero: false
            }}
        }}
    }}
}});
</script>
</body>
</html>
"""
    with open(filepath, 'w') as f:
        f.write(html)
    print(f"Report exported to: {filepath}")


if __name__ == "__main__":
    # Demo with sample data
    gen = StrategyReportGenerator(
        strategy_name="SPX Cash-Secured Puts",
        symbol="SPX",
        initial_capital=1000000,
        start_date="2022-01-01",
        end_date="2024-12-01"
    )

    # Add sample trades
    import random
    for i in range(50):
        pnl = random.gauss(1500, 3000)  # Avg $1500 profit, $3000 std dev
        gen.add_trade(
            trade_id=i+1,
            entry_date=f"2022-{(i%12)+1:02d}-15",
            exit_date=f"2022-{(i%12)+1:02d}-28",
            direction="SHORT_PUT",
            entry_price=15.50,
            exit_price=0 if pnl > 0 else 25.00,
            contracts=1,
            pnl=pnl,
            price_source="POLYGON_HISTORICAL" if random.random() > 0.2 else "ESTIMATED"
        )

    report = gen.generate()
    print_strategy_report(report)
