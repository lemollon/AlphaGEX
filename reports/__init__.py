"""
Reports Module

Generates investor-grade reports from backtest results.
"""

from reports.investor_report_generator import (
    InvestorReportGenerator,
    generate_investor_report_markdown,
)

__all__ = [
    'InvestorReportGenerator',
    'generate_investor_report_markdown',
]
