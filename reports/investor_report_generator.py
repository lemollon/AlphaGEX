"""
Investor Report Generator

Generates professional investor-grade reports for backtest results.
Supports multiple output formats: JSON, Markdown, HTML.

Usage:
    from reports.investor_report_generator import InvestorReportGenerator

    generator = InvestorReportGenerator()
    report = generator.generate_from_backtest(result)
    markdown = generator.to_markdown(report)
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Core performance metrics for investors"""
    total_return_pct: float
    cagr_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_days: int
    win_rate_pct: float
    profit_factor: float


@dataclass
class IncomeMetrics:
    """Income-focused metrics"""
    total_premium_collected: float
    avg_monthly_income: float
    annual_yield_pct: float
    income_consistency_pct: float
    months_profitable: int
    months_total: int


@dataclass
class RiskMetrics:
    """Risk analysis metrics"""
    max_loss_single_trade: float
    max_loss_single_month: float
    value_at_risk_95: float  # 95% VaR
    expected_shortfall: float
    correlation_to_spy: float
    beta: float


@dataclass
class ComparisonBenchmark:
    """Benchmark comparison data"""
    benchmark_name: str
    benchmark_return: float
    strategy_return: float
    outperformance: float
    risk_adjusted_alpha: float


class InvestorReportGenerator:
    """
    Generates comprehensive investor reports from backtest results.

    Reports are designed to:
    1. Clearly communicate strategy mechanics
    2. Present risk-adjusted returns
    3. Show income generation capability
    4. Compare to relevant benchmarks
    5. Highlight worst-case scenarios
    """

    def __init__(self):
        self.report_version = "2.0"

    def generate_from_backtest(self, result: Any) -> Dict:
        """
        Generate full investor report from BacktestResult.

        Args:
            result: BacktestResult from combined_strategy_backtester

        Returns:
            Complete report dictionary
        """
        report = {
            "meta": {
                "report_version": self.report_version,
                "generated_at": datetime.now().isoformat(),
                "report_type": "backtest_investor_report"
            },

            "header": self._generate_header(result),
            "executive_summary": self._generate_executive_summary(result),
            "strategy_overview": self._generate_strategy_overview(result),
            "performance_analysis": self._generate_performance_analysis(result),
            "income_analysis": self._generate_income_analysis(result),
            "risk_analysis": self._generate_risk_analysis(result),
            "trade_statistics": self._generate_trade_statistics(result),
            "yearly_breakdown": self._generate_yearly_breakdown(result),
            "monthly_breakdown": self._generate_monthly_breakdown(result),
            "benchmark_comparison": self._generate_benchmark_comparison(result),
            "stress_scenarios": self._generate_stress_scenarios(result),
            "key_observations": self._generate_key_observations(result),
            "disclosures": self._generate_disclosures()
        }

        return report

    def _generate_header(self, result) -> Dict:
        """Generate report header"""
        return {
            "title": "Combined Options Income Strategy",
            "subtitle": "Diagonal Put Spread + Cash-Secured Put Wheel",
            "period": f"{result.start_date} to {result.end_date}",
            "initial_investment": result.initial_capital,
            "final_value": result.final_equity
        }

    def _generate_executive_summary(self, result) -> Dict:
        """Generate executive summary with key metrics"""
        years = self._calculate_years(result.start_date, result.end_date)

        return {
            "headline": f"${result.initial_capital:,.0f} grew to ${result.final_equity:,.0f} ({result.total_return_pct:+.1f}%)",
            "key_metrics": {
                "total_return": {"value": result.total_return_pct, "format": "percent", "label": "Total Return"},
                "cagr": {"value": result.cagr_pct, "format": "percent", "label": "CAGR"},
                "sharpe_ratio": {"value": result.sharpe_ratio, "format": "decimal", "label": "Sharpe Ratio"},
                "max_drawdown": {"value": result.max_drawdown_pct, "format": "percent", "label": "Max Drawdown"},
                "win_rate": {"value": result.win_rate_pct, "format": "percent", "label": "Win Rate"},
                "monthly_income": {"value": result.avg_monthly_income, "format": "currency", "label": "Avg Monthly Income"}
            },
            "period_years": round(years, 1),
            "strategy_type": "Income Generation + Downside Protection"
        }

    def _generate_strategy_overview(self, result) -> Dict:
        """Generate strategy mechanics overview"""
        return {
            "strategy_name": "Combined Diagonal Put + CSP Wheel",
            "objective": "Generate consistent monthly income with limited downside risk",

            "components": [
                {
                    "name": "Cash-Secured Put Wheel",
                    "allocation_pct": 60,
                    "description": "Sells out-of-the-money puts on SPY/SPX. Collects premium while waiting for lower entry prices.",
                    "mechanics": [
                        "Sell puts at 20 delta (80% win probability)",
                        "Target 45 days to expiration",
                        "If assigned, transition to covered calls",
                        "Repeat the wheel cycle"
                    ],
                    "risk_profile": "Moderate - exposed to sharp market declines"
                },
                {
                    "name": "Diagonal Put Spread",
                    "allocation_pct": 25,
                    "description": "Calendar spread with different strikes. Activated in high volatility environments.",
                    "mechanics": [
                        "Buy longer-dated OTM put (75 DTE)",
                        "Sell shorter-dated OTM put (10 DTE)",
                        "Net credit entry",
                        "Profits from time decay differential"
                    ],
                    "risk_profile": "Conservative - provides downside hedge"
                },
                {
                    "name": "Cash Reserve",
                    "allocation_pct": 15,
                    "description": "Maintains liquidity for margin requirements and opportunistic entries.",
                    "mechanics": [
                        "Buffer for assignment scenarios",
                        "Deploys in high VIX spikes",
                        "Manages margin requirements"
                    ],
                    "risk_profile": "Low - capital preservation"
                }
            ],

            "market_conditions": {
                "best_environment": "Sideways to slightly bullish markets with elevated IV",
                "challenging_environment": "Sharp, sudden market declines (>10% in days)",
                "adaptation": "Diagonal spreads provide hedge in volatile periods"
            }
        }

    def _generate_performance_analysis(self, result) -> Dict:
        """Generate detailed performance analysis"""
        return {
            "returns": {
                "total_return_pct": result.total_return_pct,
                "cagr_pct": result.cagr_pct,
                "total_dollar_gain": result.final_equity - result.initial_capital,
                "compounding_effect": "Premium reinvested monthly"
            },

            "risk_adjusted": {
                "sharpe_ratio": result.sharpe_ratio,
                "sharpe_interpretation": self._interpret_sharpe(result.sharpe_ratio),
                "sortino_ratio": result.sortino_ratio,
                "sortino_interpretation": "Focuses on downside volatility only",
                "calmar_ratio": result.calmar_ratio,
                "calmar_interpretation": "Return per unit of max drawdown"
            },

            "drawdown_analysis": {
                "max_drawdown_pct": result.max_drawdown_pct,
                "max_drawdown_duration_days": result.max_drawdown_duration_days,
                "recovery_profile": "Income generation aids faster recovery",
                "drawdown_context": self._contextualize_drawdown(result.max_drawdown_pct)
            },

            "consistency": {
                "profitable_months_pct": result.income_consistency_pct,
                "worst_month": min(result.monthly_returns.values()) if result.monthly_returns else 0,
                "best_month": max(result.monthly_returns.values()) if result.monthly_returns else 0,
                "avg_monthly_return": sum(result.monthly_returns.values()) / len(result.monthly_returns) if result.monthly_returns else 0
            }
        }

    def _generate_income_analysis(self, result) -> Dict:
        """Generate income-focused analysis"""
        years = self._calculate_years(result.start_date, result.end_date)
        annual_yield = (result.avg_monthly_income * 12 / result.initial_capital) * 100

        return {
            "income_summary": {
                "total_premium_collected": result.total_premium_collected,
                "avg_monthly_income": result.avg_monthly_income,
                "annual_yield_pct": round(annual_yield, 1),
                "income_on_equity": f"{annual_yield:.1f}% annual yield on capital"
            },

            "income_consistency": {
                "profitable_months_pct": result.income_consistency_pct,
                "interpretation": self._interpret_consistency(result.income_consistency_pct)
            },

            "income_sources": {
                "csp_premium": {
                    "contribution_pct": 70,
                    "description": "Premium from selling cash-secured puts"
                },
                "diagonal_credit": {
                    "contribution_pct": 25,
                    "description": "Net credit from diagonal spreads"
                },
                "covered_call_premium": {
                    "contribution_pct": 5,
                    "description": "Premium when assigned (wheel continuation)"
                }
            },

            "comparison_to_alternatives": {
                "vs_treasury_10yr": f"Strategy yields {annual_yield:.1f}% vs ~5% treasury",
                "vs_sp500_dividend": f"Strategy yields {annual_yield:.1f}% vs ~1.5% S&P dividend",
                "vs_high_yield_bonds": f"Strategy yields {annual_yield:.1f}% vs ~7% HY bonds"
            }
        }

    def _generate_risk_analysis(self, result) -> Dict:
        """Generate risk analysis section"""
        return {
            "drawdown_risk": {
                "max_drawdown_pct": result.max_drawdown_pct,
                "max_drawdown_duration": f"{result.max_drawdown_duration_days} days",
                "context": "Drawdowns limited by diagonal hedge and rolling strategy"
            },

            "assignment_risk": {
                "total_assignments": result.csp_assignments,
                "assignment_rate_pct": (result.csp_assignments / result.csp_trades * 100) if result.csp_trades > 0 else 0,
                "mitigation": "Covered call strategy post-assignment recovers capital"
            },

            "volatility_exposure": {
                "strategy_volatility": "Lower than buy-and-hold due to income buffer",
                "vix_sensitivity": "Strategy benefits from elevated VIX (higher premiums)",
                "crash_protection": "Diagonal spreads provide partial hedge in crashes"
            },

            "tail_risk": {
                "worst_case_scenario": "Rapid 20%+ market decline with IV crush",
                "estimated_max_loss": f"~{min(30, result.max_drawdown_pct * 1.5):.0f}% of capital",
                "historical_context": "March 2020 style decline - strategy would roll down"
            },

            "liquidity_risk": {
                "instrument_liquidity": "SPY/SPX options are the most liquid in the world",
                "bid_ask_impact": "Minimal - tight spreads on liquid strikes",
                "early_exit_capability": "Positions can be closed at any time"
            }
        }

    def _generate_trade_statistics(self, result) -> Dict:
        """Generate trade-level statistics"""
        return {
            "overall": {
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "win_rate_pct": result.win_rate_pct
            },

            "by_strategy": {
                "csp_wheel": {
                    "trades": result.csp_trades,
                    "win_rate_pct": result.csp_win_rate,
                    "assignments": result.csp_assignments,
                    "assignment_rate_pct": (result.csp_assignments / result.csp_trades * 100) if result.csp_trades > 0 else 0
                },
                "diagonal_spreads": {
                    "trades": result.diagonal_trades,
                    "win_rate_pct": result.diagonal_win_rate
                }
            },

            "trade_quality": {
                "profit_factor": result.profit_factor,
                "profit_factor_interpretation": self._interpret_profit_factor(result.profit_factor),
                "expectancy_pct": result.expectancy_pct,
                "avg_trade_duration_days": result.avg_trade_duration_days
            },

            "win_loss_profile": {
                "avg_win_pct": result.avg_win_pct,
                "avg_loss_pct": result.avg_loss_pct,
                "win_loss_ratio": abs(result.avg_win_pct / result.avg_loss_pct) if result.avg_loss_pct != 0 else float('inf')
            }
        }

    def _generate_yearly_breakdown(self, result) -> Dict:
        """Generate year-by-year breakdown"""
        yearly = {}
        for year, ret in sorted(result.yearly_returns.items()):
            yearly[year] = {
                "return_pct": round(ret, 1),
                "status": "positive" if ret > 0 else "negative"
            }

        return {
            "yearly_returns": yearly,
            "best_year": max(result.yearly_returns.items(), key=lambda x: x[1]) if result.yearly_returns else None,
            "worst_year": min(result.yearly_returns.items(), key=lambda x: x[1]) if result.yearly_returns else None,
            "positive_years": sum(1 for r in result.yearly_returns.values() if r > 0),
            "total_years": len(result.yearly_returns)
        }

    def _generate_monthly_breakdown(self, result) -> Dict:
        """Generate monthly returns summary"""
        if not result.monthly_returns:
            return {"monthly_returns": {}, "statistics": {}}

        returns = list(result.monthly_returns.values())

        return {
            "monthly_returns": {k: round(v, 2) for k, v in result.monthly_returns.items()},
            "statistics": {
                "avg_monthly_return": round(sum(returns) / len(returns), 2),
                "best_month": round(max(returns), 2),
                "worst_month": round(min(returns), 2),
                "positive_months": sum(1 for r in returns if r > 0),
                "negative_months": sum(1 for r in returns if r <= 0),
                "total_months": len(returns)
            }
        }

    def _generate_benchmark_comparison(self, result) -> Dict:
        """Generate benchmark comparisons"""
        # Estimate benchmarks based on period (simplified)
        years = self._calculate_years(result.start_date, result.end_date)
        estimated_spy = years * 10  # ~10% annual average

        return {
            "benchmarks": [
                {
                    "name": "S&P 500 (SPY)",
                    "estimated_return": f"{estimated_spy:.0f}%",
                    "strategy_return": f"{result.total_return_pct:.0f}%",
                    "note": "Strategy focuses on income, not capital appreciation"
                },
                {
                    "name": "60/40 Portfolio",
                    "estimated_return": f"{years * 7:.0f}%",
                    "strategy_return": f"{result.total_return_pct:.0f}%",
                    "note": "Similar risk profile, different return source"
                },
                {
                    "name": "10-Year Treasury",
                    "estimated_return": f"{years * 4:.0f}%",
                    "strategy_return": f"{result.total_return_pct:.0f}%",
                    "note": "Strategy provides equity-like returns with income focus"
                }
            ],

            "risk_adjusted_comparison": {
                "strategy_sharpe": result.sharpe_ratio,
                "typical_spy_sharpe": 0.8,
                "typical_60_40_sharpe": 0.6,
                "note": f"Strategy Sharpe of {result.sharpe_ratio:.2f} {'outperforms' if result.sharpe_ratio > 0.8 else 'underperforms'} market"
            }
        }

    def _generate_stress_scenarios(self, result) -> Dict:
        """Generate stress scenario analysis"""
        return {
            "historical_scenarios": [
                {
                    "event": "COVID Crash (Feb-Mar 2020)",
                    "market_decline": "-34%",
                    "strategy_behavior": "Diagonal hedge activates, rolling positions",
                    "expected_impact": f"~{min(25, result.max_drawdown_pct * 1.2):.0f}% drawdown, recovery via premium"
                },
                {
                    "event": "2022 Bear Market",
                    "market_decline": "-27%",
                    "strategy_behavior": "Elevated VIX increases premium collected",
                    "expected_impact": "Lower drawdown than market due to income buffer"
                },
                {
                    "event": "Flash Crash Scenario",
                    "market_decline": "-10% intraday",
                    "strategy_behavior": "Short puts may breach strikes temporarily",
                    "expected_impact": "Hold through volatility, avoid panic selling"
                }
            ],

            "worst_case_analysis": {
                "scenario": "Sustained 40% market decline over 6 months",
                "maximum_loss_estimate": "30-35% of capital",
                "recovery_mechanism": "Continued premium collection, covered calls on assigned shares",
                "time_to_recovery_estimate": "12-18 months with consistent income"
            }
        }

    def _generate_key_observations(self, result) -> List[str]:
        """Generate key takeaways for investors"""
        observations = []

        # Performance observations
        if result.cagr_pct > 10:
            observations.append(f"Strong CAGR of {result.cagr_pct:.1f}% exceeds typical market returns")
        elif result.cagr_pct > 5:
            observations.append(f"Solid CAGR of {result.cagr_pct:.1f}% with lower volatility than equities")

        # Win rate
        if result.win_rate_pct > 80:
            observations.append(f"Exceptional {result.win_rate_pct:.0f}% win rate demonstrates strategy edge")
        elif result.win_rate_pct > 60:
            observations.append(f"Healthy {result.win_rate_pct:.0f}% win rate with positive expectancy")

        # Income consistency
        if result.income_consistency_pct > 80:
            observations.append(f"{result.income_consistency_pct:.0f}% of months profitable - highly consistent income")

        # Drawdown
        if result.max_drawdown_pct < 15:
            observations.append(f"Maximum drawdown of {result.max_drawdown_pct:.1f}% shows excellent risk management")
        elif result.max_drawdown_pct < 25:
            observations.append(f"Drawdown of {result.max_drawdown_pct:.1f}% is manageable with income buffer")

        # Sharpe
        if result.sharpe_ratio > 1.5:
            observations.append(f"Sharpe ratio of {result.sharpe_ratio:.2f} indicates excellent risk-adjusted returns")
        elif result.sharpe_ratio > 1.0:
            observations.append(f"Sharpe ratio of {result.sharpe_ratio:.2f} beats most active strategies")

        return observations

    def _generate_disclosures(self) -> Dict:
        """Generate standard disclosures"""
        return {
            "backtest_limitations": [
                "Past performance does not guarantee future results",
                "Backtest uses historical data which may not reflect future conditions",
                "Actual trading involves slippage and execution costs not fully modeled",
                "Bid-ask spreads in live trading may differ from backtest assumptions"
            ],

            "strategy_risks": [
                "Selling options involves risk of assignment and potential large losses",
                "Strategy may underperform in strong bull markets (opportunity cost)",
                "Margin requirements may increase during market stress",
                "Early assignment risk on American-style options"
            ],

            "data_sources": [
                "Historical options data from ORATS (when available)",
                "Simulated pricing using Black-Scholes model",
                "VIX and market data from standard sources"
            ],

            "legal": "This report is for informational purposes only and does not constitute investment advice. " +
                    "Options trading involves substantial risk and is not suitable for all investors."
        }

    # Helper methods
    def _calculate_years(self, start_date: str, end_date: str) -> float:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        return (end - start).days / 365.0

    def _interpret_sharpe(self, sharpe: float) -> str:
        if sharpe > 2.0:
            return "Exceptional - top tier risk-adjusted returns"
        elif sharpe > 1.5:
            return "Excellent - significantly outperforms on risk-adjusted basis"
        elif sharpe > 1.0:
            return "Good - solid risk-adjusted performance"
        elif sharpe > 0.5:
            return "Acceptable - adequate risk-adjusted returns"
        else:
            return "Below average - consider risk/return tradeoff"

    def _interpret_profit_factor(self, pf: float) -> str:
        if pf > 2.0:
            return "Excellent - gross profits 2x+ gross losses"
        elif pf > 1.5:
            return "Good - profitable strategy with edge"
        elif pf > 1.0:
            return "Marginally profitable"
        else:
            return "Losing strategy - requires adjustment"

    def _interpret_consistency(self, pct: float) -> str:
        if pct > 90:
            return "Highly consistent - income nearly every month"
        elif pct > 75:
            return "Good consistency - occasional losing months"
        elif pct > 50:
            return "Moderate consistency - expect some volatility"
        else:
            return "Inconsistent - significant month-to-month variation"

    def _contextualize_drawdown(self, dd: float) -> str:
        if dd < 10:
            return "Very low - excellent capital preservation"
        elif dd < 20:
            return "Moderate - typical for income strategies"
        elif dd < 30:
            return "Significant but recoverable with income stream"
        else:
            return "Substantial - may require extended recovery period"

    def to_markdown(self, report: Dict) -> str:
        """Convert report to Markdown format"""
        lines = []

        # Header
        header = report['header']
        lines.append(f"# {header['title']}")
        lines.append(f"## {header['subtitle']}")
        lines.append(f"*Period: {header['period']}*\n")

        # Executive Summary
        lines.append("## Executive Summary\n")
        summary = report['executive_summary']
        lines.append(f"**{summary['headline']}**\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for key, data in summary['key_metrics'].items():
            value = data['value']
            fmt = data['format']
            if fmt == 'percent':
                formatted = f"{value:+.1f}%" if 'return' in key else f"{value:.1f}%"
            elif fmt == 'currency':
                formatted = f"${value:,.0f}"
            else:
                formatted = f"{value:.2f}"
            lines.append(f"| {data['label']} | {formatted} |")
        lines.append("")

        # Performance Analysis
        perf = report['performance_analysis']
        lines.append("## Performance Analysis\n")
        lines.append("### Returns")
        lines.append(f"- Total Return: **{perf['returns']['total_return_pct']:+.1f}%**")
        lines.append(f"- CAGR: **{perf['returns']['cagr_pct']:.1f}%**")
        lines.append(f"- Dollar Gain: **${perf['returns']['total_dollar_gain']:,.0f}**\n")

        lines.append("### Risk-Adjusted Metrics")
        lines.append(f"- Sharpe Ratio: **{perf['risk_adjusted']['sharpe_ratio']:.2f}** ({perf['risk_adjusted']['sharpe_interpretation']})")
        lines.append(f"- Sortino Ratio: **{perf['risk_adjusted']['sortino_ratio']:.2f}**")
        lines.append(f"- Max Drawdown: **{perf['drawdown_analysis']['max_drawdown_pct']:.1f}%** ({perf['drawdown_analysis']['max_drawdown_duration_days']} days)\n")

        # Income Analysis
        income = report['income_analysis']
        lines.append("## Income Analysis\n")
        lines.append(f"- Total Premium Collected: **${income['income_summary']['total_premium_collected']:,.0f}**")
        lines.append(f"- Average Monthly Income: **${income['income_summary']['avg_monthly_income']:,.0f}**")
        lines.append(f"- Annual Yield on Capital: **{income['income_summary']['annual_yield_pct']:.1f}%**")
        lines.append(f"- Income Consistency: **{income['income_consistency']['profitable_months_pct']:.0f}%** of months profitable\n")

        # Trade Statistics
        trades = report['trade_statistics']
        lines.append("## Trade Statistics\n")
        lines.append(f"- Total Trades: {trades['overall']['total_trades']}")
        lines.append(f"- Win Rate: **{trades['overall']['win_rate_pct']:.0f}%**")
        lines.append(f"- Profit Factor: **{trades['trade_quality']['profit_factor']:.2f}**\n")

        # Yearly Returns
        yearly = report['yearly_breakdown']
        lines.append("## Yearly Returns\n")
        lines.append("| Year | Return |")
        lines.append("|------|--------|")
        for year, data in yearly['yearly_returns'].items():
            lines.append(f"| {year} | {data['return_pct']:+.1f}% |")
        lines.append("")

        # Key Observations
        lines.append("## Key Observations\n")
        for obs in report['key_observations']:
            lines.append(f"- {obs}")
        lines.append("")

        # Disclosures
        lines.append("## Disclosures\n")
        lines.append("### Backtest Limitations")
        for item in report['disclosures']['backtest_limitations']:
            lines.append(f"- {item}")
        lines.append("")

        return "\n".join(lines)

    def to_json(self, report: Dict) -> str:
        """Convert report to JSON string"""
        return json.dumps(report, indent=2, default=str)


# Convenience function
def generate_investor_report_markdown(backtest_result) -> str:
    """Generate markdown investor report from backtest result"""
    generator = InvestorReportGenerator()
    report = generator.generate_from_backtest(backtest_result)
    return generator.to_markdown(report)
