"""
FORTRESS 25-Stat Profitability Scorecard
=========================================
Reusable scorecard computation module that can be called from:
  - CLI (fortress_full_backtest.py Phase 8)
  - API endpoints (fortress_routes.py)
  - Scheduled jobs

Extracts the compute + verdict logic into structured data suitable for
JSON API responses and database persistence.
"""

import math
import logging
from datetime import date, datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

logger = logging.getLogger(__name__)


# ============================================================================
# SCORECARD DATA CLASSES
# ============================================================================

@dataclass
class ScorecardCheck:
    """A single pass/fail check in the scorecard."""
    number: int
    name: str
    category: str
    target: str
    result_display: str
    result_value: float
    passed: bool


@dataclass
class VixRegimeBucket:
    """Performance stats for a VIX regime bucket."""
    label: str
    trade_count: int
    win_rate: float
    profit_factor: float
    total_pnl: float
    max_dd_pct: float


@dataclass
class ScorecardResult:
    """Complete 25-stat scorecard result."""
    # Metadata
    run_id: str = ''
    run_timestamp: str = ''
    config_summary: str = ''

    # Verdict
    total_checks: int = 0
    passed_checks: int = 0
    verdict: str = ''  # GO_LIVE, CONDITIONAL_GO, PAPER_TRADE, NO_GO
    verdict_detail: str = ''
    recommended_size_pct: int = 100

    # All checks
    checks: List[Dict[str, Any]] = field(default_factory=list)

    # Category 1: Does It Make Money?
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    median_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expected_value: float = 0.0
    annualized_return: float = 0.0

    # Category 2: Is The Edge Real?
    total_trades: int = 0
    t_statistic: float = 0.0
    p_value: float = 1.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0

    # Category 3: Survive Bad Times?
    max_drawdown_dollar: float = 0.0
    max_drawdown_pct: float = 0.0
    max_dd_duration_trades: int = 0
    max_consecutive_losses: int = 0
    largest_single_loss: float = 0.0
    calmar_ratio: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0

    # Category 4: Robustness
    vix_regimes: List[Dict[str, Any]] = field(default_factory=list)
    worst_month: str = ''
    worst_month_pnl: float = 0.0
    worst_month_pct: float = 0.0
    worst_month_passed: bool = False

    # Extras
    initial_capital: float = 0.0
    ending_equity: float = 0.0
    return_on_capital: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    # Equity curve (for charting)
    equity_curve: List[float] = field(default_factory=list)
    trade_dates: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# ============================================================================
# SCORECARD THRESHOLDS
# ============================================================================

# These define the pass/fail criteria for each of the 25 stats
SCORECARD_THRESHOLDS = {
    # Category 1: Does It Make Money?
    'total_pnl': {'target': '> $0', 'threshold': 0, 'op': '>'},
    'avg_pnl': {'target': '> $5', 'threshold': 5, 'op': '>'},
    'median_pnl': {'target': '> $0', 'threshold': 0, 'op': '>'},
    'win_rate': {'target': '> 55%', 'threshold': 0.55, 'op': '>'},
    'profit_factor': {'target': '> 1.3', 'threshold': 1.3, 'op': '>'},
    'expected_value': {'target': '> $3', 'threshold': 3, 'op': '>'},
    'annualized_return': {'target': '> 15%', 'threshold': 0.15, 'op': '>'},

    # Category 2: Is The Edge Real?
    'sample_size': {'target': '> 200', 'threshold': 200, 'op': '>'},
    't_statistic': {'target': '> 2.0', 'threshold': 2.0, 'op': '>'},
    'sharpe': {'target': '> 1.0', 'threshold': 1.0, 'op': '>'},
    'sortino': {'target': '> 1.5', 'threshold': 1.5, 'op': '>'},
    'skewness': {'target': '> -0.5', 'threshold': -0.5, 'op': '>'},

    # Category 3: Survive Bad Times?
    'max_dd_pct': {'target': '< 20%', 'threshold': 0.20, 'op': '<'},
    'max_dd_duration': {'target': '< 60', 'threshold': 60, 'op': '<'},
    'max_consec_losses': {'target': '< 8', 'threshold': 8, 'op': '<'},
    'largest_loss_pct': {'target': '< 3% cap', 'threshold': 0.03, 'op': '<'},  # % of capital
    'calmar': {'target': '> 1.0', 'threshold': 1.0, 'op': '>'},
    'var_95_pct': {'target': '< 2% cap', 'threshold': 0.02, 'op': '<'},  # % of capital

    # Category 4: Worst month
    'worst_month': {'target': '> -8%', 'threshold': -8.0, 'op': '>'},
}


# ============================================================================
# CORE COMPUTATION
# ============================================================================

def _check_passes(value: float, threshold: float, op: str) -> bool:
    """Evaluate a pass/fail check."""
    if op == '>':
        return value > threshold
    elif op == '>=':
        return value >= threshold
    elif op == '<':
        return value < threshold
    elif op == '<=':
        return value <= threshold
    return False


def compute_scorecard(
    trade_pnls: List[float],
    trade_dates: List[str],
    trade_vix_values: List[float],
    initial_capital: float,
    config_summary: str = '',
    run_id: str = '',
) -> ScorecardResult:
    """
    Compute the full 25-stat profitability scorecard.

    Args:
        trade_pnls: List of realized P&L per trade (after costs)
        trade_dates: List of entry dates as ISO strings (YYYY-MM-DD)
        trade_vix_values: List of VIX at entry for each trade
        initial_capital: Starting capital
        config_summary: Human-readable config description
        run_id: Unique identifier for this scorecard run

    Returns:
        ScorecardResult with all stats, checks, and verdict
    """
    if not HAS_NUMPY:
        raise ImportError("numpy is required for scorecard computation")

    result = ScorecardResult(
        run_id=run_id,
        run_timestamp=datetime.utcnow().isoformat(),
        config_summary=config_summary,
        initial_capital=initial_capital,
    )

    if not trade_pnls:
        result.verdict = 'NO_GO'
        result.verdict_detail = 'No trades to evaluate'
        return result

    pnls = np.array(trade_pnls)
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    total_trades = len(pnls)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / total_trades if total_trades else 0
    total_pnl = float(pnls.sum())
    avg_pnl = float(pnls.mean())
    median_pnl = float(np.median(pnls))
    avg_win = float(wins.mean()) if len(wins) else 0
    avg_loss = float(np.abs(losses).mean()) if len(losses) else 0
    gross_profit = float(wins.sum()) if len(wins) else 0
    gross_loss = float(np.abs(losses.sum())) if len(losses) else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    if profit_factor == float('inf'):
        profit_factor = 999.0
    expected_value = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    # Equity curve
    equity = np.zeros(total_trades + 1)
    equity[0] = initial_capital
    for i in range(total_trades):
        equity[i + 1] = equity[i] + pnls[i]

    # Drawdown
    rolling_max = np.maximum.accumulate(equity)
    drawdown = equity - rolling_max
    max_dd_dollar = float(np.abs(drawdown).max())
    dd_pct = drawdown / np.where(rolling_max > 0, rolling_max, 1)
    max_dd_pct = float(np.abs(dd_pct).max())

    # Max drawdown duration (in trades)
    in_dd = drawdown < 0
    max_dd_duration = 0
    current_dd_len = 0
    for v in in_dd:
        if v:
            current_dd_len += 1
            max_dd_duration = max(max_dd_duration, current_dd_len)
        else:
            current_dd_len = 0

    # Consecutive losses
    max_consec_losses = 0
    current_streak = 0
    for p in pnls:
        if p <= 0:
            current_streak += 1
            max_consec_losses = max(max_consec_losses, current_streak)
        else:
            current_streak = 0

    # Largest single loss
    largest_loss = float(pnls.min()) if len(pnls) else 0

    # Annualized returns
    if total_trades >= 2 and len(trade_dates) >= 2:
        try:
            first_date = date.fromisoformat(trade_dates[0])
            last_date = date.fromisoformat(trade_dates[-1])
            days_span = (last_date - first_date).days
            years = days_span / 365.25 if days_span > 0 else 1
        except (ValueError, TypeError):
            years = 1
        ending_equity = equity[-1]
        annualized_return = (ending_equity / initial_capital) ** (1 / years) - 1 if years > 0 else 0
    else:
        annualized_return = 0
        years = 1

    # Sharpe Ratio
    trade_returns = pnls / initial_capital
    ann_vol = float(trade_returns.std() * np.sqrt(252 / max(1, total_trades / max(1, years))))
    risk_free = 0.05
    sharpe = (annualized_return - risk_free) / ann_vol if ann_vol > 0 else 0

    # Sortino Ratio
    downside = trade_returns[trade_returns < 0]
    downside_vol = float(downside.std() * np.sqrt(252 / max(1, total_trades / max(1, years)))) if len(downside) > 0 else 0.001
    sortino = (annualized_return - risk_free) / downside_vol if downside_vol > 0 else 0

    # Calmar Ratio
    calmar = annualized_return / max_dd_pct if max_dd_pct > 0 else 0

    # Statistical significance
    t_stat = 0.0
    p_value = 1.0
    if HAS_SCIPY and total_trades >= 5:
        t_stat, p_value = scipy_stats.ttest_1samp(pnls, 0)
        t_stat = float(t_stat)
        p_value = float(p_value)

    # Skewness & kurtosis
    skewness = float(scipy_stats.skew(pnls)) if HAS_SCIPY else 0
    kurtosis = float(scipy_stats.kurtosis(pnls)) if HAS_SCIPY else 0

    # VaR
    var_95 = float(np.percentile(pnls, 5))
    var_mask = pnls <= var_95
    cvar_95 = float(pnls[var_mask].mean()) if var_mask.any() else var_95

    # Return on capital
    return_on_capital = total_pnl / initial_capital

    # ---- Populate result ----
    result.total_pnl = round(total_pnl, 2)
    result.avg_pnl = round(avg_pnl, 2)
    result.median_pnl = round(median_pnl, 2)
    result.win_rate = round(win_rate, 4)
    result.profit_factor = round(min(profit_factor, 999.0), 2)
    result.expected_value = round(expected_value, 2)
    result.annualized_return = round(annualized_return, 4)

    result.total_trades = total_trades
    result.t_statistic = round(t_stat, 2)
    result.p_value = round(p_value, 6)
    result.sharpe_ratio = round(sharpe, 2)
    result.sortino_ratio = round(sortino, 2)
    result.skewness = round(skewness, 2)
    result.kurtosis = round(kurtosis, 2)

    result.max_drawdown_dollar = round(max_dd_dollar, 2)
    result.max_drawdown_pct = round(max_dd_pct, 4)
    result.max_dd_duration_trades = max_dd_duration
    result.max_consecutive_losses = max_consec_losses
    result.largest_single_loss = round(largest_loss, 2)
    result.calmar_ratio = round(calmar, 2)
    result.var_95 = round(var_95, 2)
    result.cvar_95 = round(cvar_95, 2)

    result.initial_capital = initial_capital
    result.ending_equity = round(float(equity[-1]), 2)
    result.return_on_capital = round(return_on_capital, 4)
    result.win_count = win_count
    result.loss_count = loss_count
    result.avg_win = round(avg_win, 2)
    result.avg_loss = round(avg_loss, 2)
    result.gross_profit = round(gross_profit, 2)
    result.gross_loss = round(gross_loss, 2)

    # Equity curve for charting (downsample if > 500 points)
    eq_list = equity.tolist()
    if len(eq_list) > 500:
        step = len(eq_list) // 500
        result.equity_curve = [eq_list[i] for i in range(0, len(eq_list), step)]
        result.trade_dates = [trade_dates[i] if i < len(trade_dates) else '' for i in range(0, len(eq_list) - 1, step)]
    else:
        result.equity_curve = eq_list
        result.trade_dates = list(trade_dates)

    # ---- Build checks ----
    checks = []
    passes = 0

    # Category 1: Does It Make Money?
    cat1 = [
        (1, 'Total Net P&L', total_pnl, f'${total_pnl:,.0f}', 0, '>'),
        (2, 'Avg Trade P&L', avg_pnl, f'${avg_pnl:,.2f}', 5, '>'),
        (3, 'Median Trade P&L', median_pnl, f'${median_pnl:,.2f}', 0, '>'),
        (4, 'Win Rate', win_rate, f'{win_rate*100:.1f}%', 0.55, '>'),
        (5, 'Profit Factor', profit_factor, f'{profit_factor:.2f}', 1.3, '>'),
        (6, 'Expected Value/Trade', expected_value, f'${expected_value:,.2f}', 3, '>'),
        (7, 'Annualized Return', annualized_return, f'{annualized_return*100:.1f}%', 0.15, '>'),
    ]
    for num, name, val, display, thresh, op in cat1:
        passed = _check_passes(val, thresh, op)
        if passed:
            passes += 1
        target_str = f'> ${thresh:,.0f}' if name.startswith('Total') else \
                     f'> ${thresh}' if 'P&L' in name or 'Value' in name else \
                     f'> {thresh*100:.0f}%' if 'Rate' in name or 'Return' in name else \
                     f'> {thresh}'
        checks.append({
            'number': num, 'name': name, 'category': 'DOES IT MAKE MONEY?',
            'target': target_str, 'result_display': display,
            'result_value': round(val, 4), 'passed': passed,
        })

    # Category 2: Is The Edge Real?
    cat2 = [
        (8, 'Sample Size', total_trades, f'{total_trades}', 200, '>'),
        (9, 't-Statistic', t_stat, f'{t_stat:.2f}', 2.0, '>'),
        (10, 'Sharpe Ratio', sharpe, f'{sharpe:.2f}', 1.0, '>'),
        (11, 'Sortino Ratio', sortino, f'{sortino:.2f}', 1.5, '>'),
        (14, 'P&L Skewness', skewness, f'{skewness:.2f}', -0.5, '>'),
    ]
    for num, name, val, display, thresh, op in cat2:
        passed = _check_passes(val, thresh, op)
        if passed:
            passes += 1
        checks.append({
            'number': num, 'name': name, 'category': 'IS THE EDGE REAL?',
            'target': f'> {thresh}', 'result_display': display,
            'result_value': round(val, 4), 'passed': passed,
        })

    # Category 3: Survive Bad Times?
    cap = initial_capital
    cat3 = [
        (15, 'Max Drawdown', max_dd_pct, f'${max_dd_dollar:,.0f} ({max_dd_pct*100:.1f}%)', 0.20, '<'),
        (16, 'Max DD Duration (trades)', max_dd_duration, f'{max_dd_duration}', 60, '<'),
        (17, 'Max Consecutive Losses', max_consec_losses, f'{max_consec_losses}', 8, '<'),
        (18, 'Largest Single Loss', abs(largest_loss) / cap if cap > 0 else 0,
         f'${largest_loss:,.0f} ({abs(largest_loss)/cap*100:.1f}% cap)' if cap > 0 else f'${largest_loss:,.0f}',
         0.03, '<'),
        (19, 'Calmar Ratio', calmar, f'{calmar:.2f}', 1.0, '>'),
        (20, '95% VaR (per trade)', abs(var_95) / cap if cap > 0 else 0,
         f'${var_95:,.0f} ({abs(var_95)/cap*100:.1f}% cap)' if cap > 0 else f'${var_95:,.0f}',
         0.02, '<'),
    ]
    for num, name, val, display, thresh, op in cat3:
        passed = _check_passes(val, thresh, op)
        if passed:
            passes += 1
        target_str = f'< {thresh*100:.0f}% cap' if 'Loss' in name or 'VaR' in name else \
                     f'< {thresh*100:.0f}%' if 'Drawdown' in name else \
                     f'> {thresh}' if op == '>' else f'< {int(thresh)}'
        checks.append({
            'number': num, 'name': name, 'category': 'SURVIVE THE BAD TIMES?',
            'target': target_str, 'result_display': display,
            'result_value': round(val, 4), 'passed': passed,
        })

    total_checks = len(checks)
    result.checks = checks
    result.total_checks = total_checks
    result.passed_checks = passes

    # Verdict
    if passes >= 16:
        result.verdict = 'GO_LIVE'
        result.verdict_detail = 'Strategy passes all critical checks. Deploy at full size.'
        result.recommended_size_pct = 100
    elif passes >= 13:
        result.verdict = 'CONDITIONAL_GO'
        result.verdict_detail = 'Strategy is profitable but has risk concerns. Deploy at 50% size.'
        result.recommended_size_pct = 50
    elif passes >= 10:
        result.verdict = 'PAPER_TRADE'
        result.verdict_detail = 'Strategy needs more validation. Paper trade for 60 days.'
        result.recommended_size_pct = 0
    else:
        result.verdict = 'NO_GO'
        result.verdict_detail = 'Strategy does not meet minimum profitability requirements. Needs redesign.'
        result.recommended_size_pct = 0

    # ---- Category 4: VIX Regime Breakdown ----
    if trade_vix_values and len(trade_vix_values) == len(trade_pnls):
        vix_arr = np.array(trade_vix_values)
        pnl_arr = np.array(trade_pnls)

        buckets = {
            'VIX < 20': vix_arr < 20,
            'VIX 20-30': (vix_arr >= 20) & (vix_arr < 30),
            'VIX > 30': vix_arr >= 30,
        }

        for label, mask in buckets.items():
            bucket_pnls = pnl_arr[mask]
            if len(bucket_pnls) == 0:
                continue

            b_wins = bucket_pnls[bucket_pnls > 0]
            b_losses = bucket_pnls[bucket_pnls <= 0]
            b_wr = len(b_wins) / len(bucket_pnls)
            b_gp = float(b_wins.sum()) if len(b_wins) else 0
            b_gl = float(np.abs(b_losses.sum())) if len(b_losses) else 0
            b_pf = b_gp / b_gl if b_gl > 0 else 999.0

            # Bucket drawdown
            b_eq = np.zeros(len(bucket_pnls) + 1)
            b_eq[0] = initial_capital
            for i in range(len(bucket_pnls)):
                b_eq[i + 1] = b_eq[i] + bucket_pnls[i]
            b_peak = np.maximum.accumulate(b_eq)
            b_dd = b_eq - b_peak
            b_dd_pct_arr = b_dd / np.where(b_peak > 0, b_peak, 1)
            b_max_dd = float(np.abs(b_dd_pct_arr).max())

            result.vix_regimes.append({
                'label': label,
                'trade_count': int(mask.sum()),
                'win_rate': round(b_wr, 4),
                'profit_factor': round(min(b_pf, 999.0), 2),
                'total_pnl': round(float(bucket_pnls.sum()), 2),
                'max_dd_pct': round(b_max_dd, 4),
            })

    # Worst month
    monthly = defaultdict(float)
    for i, d in enumerate(trade_dates):
        try:
            key = d[:7]  # YYYY-MM
            monthly[key] += trade_pnls[i]
        except (IndexError, TypeError):
            pass

    if monthly:
        worst_key = min(monthly, key=monthly.get)
        worst_val = monthly[worst_key]
        worst_pct = worst_val / initial_capital * 100
        result.worst_month = worst_key
        result.worst_month_pnl = round(worst_val, 2)
        result.worst_month_pct = round(worst_pct, 2)
        result.worst_month_passed = worst_pct > -8

    return result


def compute_scorecard_from_trades(
    trades: List[Any],
    initial_capital: float,
    config_summary: str = '',
    run_id: str = '',
) -> ScorecardResult:
    """
    Convenience wrapper that accepts Trade dataclass objects
    (from fortress_full_backtest.py) and extracts the needed fields.
    """
    trade_pnls = [t.realized_pnl for t in trades]
    trade_dates = [t.entry_date.isoformat() if isinstance(t.entry_date, date) else str(t.entry_date)
                   for t in trades]
    trade_vix = [t.vix_at_entry for t in trades]

    return compute_scorecard(
        trade_pnls=trade_pnls,
        trade_dates=trade_dates,
        trade_vix_values=trade_vix,
        initial_capital=initial_capital,
        config_summary=config_summary,
        run_id=run_id,
    )
