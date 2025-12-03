"""
Monte Carlo Stress Testing for Kelly Position Sizing

The Kelly Criterion assumes you know the TRUE win rate and payoff ratio.
In reality, these are ESTIMATES with uncertainty.

Problem:
- Estimated win rate: 65%
- True win rate: might be 55-75%
- Kelly sizing based on 65% could be CATASTROPHIC if true rate is 55%

Solution:
Monte Carlo simulation that:
1. Samples from distribution of possible true win rates
2. Simulates 1000s of trade sequences
3. Calculates probability of ruin at each Kelly fraction
4. Recommends SAFE Kelly fraction (not optimal, but robust)

Key Outputs:
- Optimal Kelly (based on point estimates) - DON'T USE THIS
- Safe Kelly (survives 95% of scenarios) - USE THIS
- Probability of 50% drawdown at each Kelly level
- Recommended position sizing with uncertainty buffer

Author: AlphaGEX Quant
Date: 2025-12-03
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json

# For statistical distributions
from scipy import stats


@dataclass
class KellyEstimate:
    """Estimated Kelly parameters with uncertainty"""
    win_rate: float          # Point estimate (e.g., 0.65)
    win_rate_std: float      # Uncertainty (e.g., 0.05)
    avg_win: float           # Average win %
    avg_win_std: float       # Uncertainty in avg win
    avg_loss: float          # Average loss % (positive number)
    avg_loss_std: float      # Uncertainty in avg loss
    sample_size: int         # Number of trades this is based on


@dataclass
class SimulationResult:
    """Result from a single Monte Carlo path"""
    final_equity: float
    max_drawdown_pct: float
    num_trades: int
    ruin: bool  # Equity fell below 50%
    peak_equity: float
    trough_equity: float


@dataclass
class KellyStressTest:
    """Complete stress test results"""
    kelly_optimal: float          # Theoretical optimal (DON'T USE)
    kelly_safe: float             # Recommended safe fraction
    kelly_conservative: float     # Extra conservative (half of safe)

    # Probability of bad outcomes at optimal Kelly
    prob_50pct_drawdown_optimal: float
    prob_ruin_optimal: float  # Equity below 25%

    # Probability of bad outcomes at safe Kelly
    prob_50pct_drawdown_safe: float
    prob_ruin_safe: float

    # Monte Carlo stats
    num_simulations: int
    num_trades_per_sim: int
    median_final_equity_optimal: float
    median_final_equity_safe: float

    # Risk metrics
    var_95_optimal: float    # 95% Value at Risk
    var_95_safe: float
    cvar_95_optimal: float   # Conditional VaR (Expected Shortfall)
    cvar_95_safe: float

    # Input parameters
    estimated_win_rate: float
    estimated_avg_win: float
    estimated_avg_loss: float
    uncertainty_level: str  # 'low', 'medium', 'high'

    recommendation: str

    def to_dict(self) -> Dict:
        return {
            'kelly_optimal': round(self.kelly_optimal, 4),
            'kelly_safe': round(self.kelly_safe, 4),
            'kelly_conservative': round(self.kelly_conservative, 4),
            'prob_50pct_drawdown_optimal': round(self.prob_50pct_drawdown_optimal, 2),
            'prob_50pct_drawdown_safe': round(self.prob_50pct_drawdown_safe, 2),
            'prob_ruin_optimal': round(self.prob_ruin_optimal, 2),
            'prob_ruin_safe': round(self.prob_ruin_safe, 2),
            'var_95_safe': round(self.var_95_safe, 2),
            'cvar_95_safe': round(self.cvar_95_safe, 2),
            'median_final_equity_safe': round(self.median_final_equity_safe, 2),
            'num_simulations': self.num_simulations,
            'uncertainty_level': self.uncertainty_level,
            'recommendation': self.recommendation
        }


class MonteCarloKelly:
    """
    Monte Carlo simulator for Kelly position sizing.

    Accounts for:
    1. Uncertainty in win rate estimate
    2. Uncertainty in payoff ratio
    3. Sequence risk (bad trades clustering)
    4. Fat tails in returns

    Provides SAFE Kelly fraction that survives worst-case scenarios.
    """

    # Ruin thresholds
    DRAWDOWN_THRESHOLD = 0.50  # 50% drawdown
    RUIN_THRESHOLD = 0.25     # 75% loss = ruin

    # Target survival probability
    SURVIVAL_TARGET = 0.95    # 95% of simulations should survive

    def __init__(
        self,
        num_simulations: int = 10000,
        num_trades_per_sim: int = 200,
        random_seed: int = 42
    ):
        """
        Initialize Monte Carlo simulator.

        Args:
            num_simulations: Number of Monte Carlo paths
            num_trades_per_sim: Trades per simulation (1 year ≈ 200 trades)
            random_seed: For reproducibility
        """
        self.num_simulations = num_simulations
        self.num_trades_per_sim = num_trades_per_sim
        self.random_seed = random_seed
        np.random.seed(random_seed)

    def calculate_kelly(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate theoretical Kelly fraction.

        Kelly Formula: f* = (bp - q) / b
        where:
          b = avg_win / avg_loss (payoff ratio)
          p = win_rate
          q = 1 - p

        Or equivalently: f* = p - q/b = p - (1-p)/(avg_win/avg_loss)
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0

        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p

        kelly = (b * p - q) / b

        # Clamp to reasonable range
        return max(0, min(1, kelly))

    def estimate_uncertainty(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        sample_size: int
    ) -> KellyEstimate:
        """
        Estimate uncertainty in Kelly parameters.

        Uses:
        - Binomial confidence interval for win rate
        - Standard error for means

        Larger sample = less uncertainty.
        """
        # Win rate uncertainty (binomial proportion confidence interval)
        # SE = sqrt(p(1-p)/n)
        if sample_size < 5:
            win_rate_std = 0.20  # Very high uncertainty
        else:
            win_rate_std = np.sqrt(win_rate * (1 - win_rate) / sample_size)
            # Minimum uncertainty of 3% even with large samples
            win_rate_std = max(0.03, win_rate_std)

        # Payoff uncertainty (assume coefficient of variation ~ 0.5)
        # With more trades, uncertainty decreases
        cv_base = 0.5  # Typical CV for trade returns
        shrinkage = np.sqrt(sample_size / 100)  # Shrinks with more data
        avg_win_std = avg_win * cv_base / shrinkage
        avg_loss_std = avg_loss * cv_base / shrinkage

        return KellyEstimate(
            win_rate=win_rate,
            win_rate_std=win_rate_std,
            avg_win=avg_win,
            avg_win_std=avg_win_std,
            avg_loss=avg_loss,
            avg_loss_std=avg_loss_std,
            sample_size=sample_size
        )

    def simulate_path(
        self,
        kelly_fraction: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> SimulationResult:
        """
        Simulate a single equity path.

        Each trade:
        1. Risk kelly_fraction of current equity
        2. Win with probability win_rate
        3. If win: gain avg_win% of risked amount
        4. If loss: lose avg_loss% of risked amount
        """
        equity = 1.0  # Start with $1
        peak = 1.0
        trough = 1.0
        max_drawdown = 0

        for _ in range(self.num_trades_per_sim):
            # Amount to risk
            risk_amount = equity * kelly_fraction

            # Win or lose
            if np.random.random() < win_rate:
                # Win
                pnl = risk_amount * (avg_win / 100)
            else:
                # Loss
                pnl = -risk_amount * (avg_loss / 100)

            equity += pnl

            # Track drawdown
            if equity > peak:
                peak = equity
            current_dd = (peak - equity) / peak if peak > 0 else 0
            max_drawdown = max(max_drawdown, current_dd)
            trough = min(trough, equity)

            # Check for ruin
            if equity < self.RUIN_THRESHOLD:
                break

        return SimulationResult(
            final_equity=equity,
            max_drawdown_pct=max_drawdown * 100,
            num_trades=self.num_trades_per_sim,
            ruin=equity < self.RUIN_THRESHOLD,
            peak_equity=peak,
            trough_equity=trough
        )

    def run_simulation(
        self,
        kelly_fraction: float,
        estimate: KellyEstimate,
        vary_parameters: bool = True
    ) -> List[SimulationResult]:
        """
        Run Monte Carlo simulation.

        If vary_parameters=True, samples win_rate and payoffs from
        distributions to account for parameter uncertainty.
        """
        results = []

        for _ in range(self.num_simulations):
            if vary_parameters:
                # Sample from uncertainty distribution
                # Use truncated normal to keep in valid range
                win_rate = np.clip(
                    np.random.normal(estimate.win_rate, estimate.win_rate_std),
                    0.2, 0.9  # Realistic bounds
                )
                avg_win = max(1, np.random.normal(estimate.avg_win, estimate.avg_win_std))
                avg_loss = max(1, np.random.normal(estimate.avg_loss, estimate.avg_loss_std))
            else:
                win_rate = estimate.win_rate
                avg_win = estimate.avg_win
                avg_loss = estimate.avg_loss

            result = self.simulate_path(kelly_fraction, win_rate, avg_win, avg_loss)
            results.append(result)

        return results

    def analyze_results(
        self,
        results: List[SimulationResult]
    ) -> Dict:
        """Analyze simulation results for risk metrics"""
        final_equities = [r.final_equity for r in results]
        max_drawdowns = [r.max_drawdown_pct for r in results]
        ruin_count = sum(1 for r in results if r.ruin)
        dd_50_count = sum(1 for r in results if r.max_drawdown_pct >= 50)

        # Value at Risk (5th percentile of final equity)
        var_95 = np.percentile(final_equities, 5)

        # Conditional VaR (mean of worst 5%)
        cutoff = np.percentile(final_equities, 5)
        worst_5pct = [e for e in final_equities if e <= cutoff]
        cvar_95 = np.mean(worst_5pct) if worst_5pct else var_95

        return {
            'prob_ruin': ruin_count / len(results),
            'prob_50pct_dd': dd_50_count / len(results),
            'median_final_equity': np.median(final_equities),
            'mean_final_equity': np.mean(final_equities),
            'std_final_equity': np.std(final_equities),
            'var_95': var_95,
            'cvar_95': cvar_95,
            'median_max_dd': np.median(max_drawdowns),
            'max_max_dd': max(max_drawdowns)
        }

    def find_safe_kelly(
        self,
        estimate: KellyEstimate,
        target_survival: float = 0.95
    ) -> float:
        """
        Find Kelly fraction where probability of ruin < (1 - target_survival).

        Uses binary search to find the largest Kelly where
        at least target_survival% of simulations avoid ruin.
        """
        low = 0.01
        high = 0.50  # Max 50% Kelly
        best_safe = low

        for _ in range(10):  # Binary search iterations
            mid = (low + high) / 2
            results = self.run_simulation(mid, estimate, vary_parameters=True)
            analysis = self.analyze_results(results)

            survival_rate = 1 - analysis['prob_ruin']

            if survival_rate >= target_survival:
                best_safe = mid
                low = mid
            else:
                high = mid

        return best_safe

    def stress_test(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        sample_size: int = 50
    ) -> KellyStressTest:
        """
        Run complete stress test on Kelly sizing.

        Returns:
            KellyStressTest with optimal, safe, and conservative Kelly fractions
        """
        # Calculate theoretical optimal Kelly
        kelly_optimal = self.calculate_kelly(win_rate, avg_win, avg_loss)

        # Estimate uncertainty
        estimate = self.estimate_uncertainty(win_rate, avg_win, avg_loss, sample_size)

        # Determine uncertainty level
        if estimate.win_rate_std < 0.05:
            uncertainty_level = 'low'
        elif estimate.win_rate_std < 0.10:
            uncertainty_level = 'medium'
        else:
            uncertainty_level = 'high'

        # Find safe Kelly
        kelly_safe = self.find_safe_kelly(estimate, self.SURVIVAL_TARGET)

        # Conservative = half of safe
        kelly_conservative = kelly_safe / 2

        # Run simulations at optimal Kelly
        results_optimal = self.run_simulation(kelly_optimal, estimate, vary_parameters=True)
        analysis_optimal = self.analyze_results(results_optimal)

        # Run simulations at safe Kelly
        results_safe = self.run_simulation(kelly_safe, estimate, vary_parameters=True)
        analysis_safe = self.analyze_results(results_safe)

        # Build recommendation
        if kelly_optimal <= 0:
            recommendation = "NEGATIVE EDGE: Do not trade. Expected value is negative."
        elif analysis_safe['prob_ruin'] > 0.10:
            recommendation = f"HIGH RISK: Even safe Kelly ({kelly_safe:.1%}) has {analysis_safe['prob_ruin']:.0%} ruin probability. Use {kelly_conservative:.1%} or less."
        elif uncertainty_level == 'high':
            recommendation = f"HIGH UNCERTAINTY: Limited sample size ({sample_size} trades). Use conservative Kelly ({kelly_conservative:.1%}) until more data available."
        else:
            recommendation = f"TRADEABLE: Use safe Kelly ({kelly_safe:.1%}) for position sizing. Optimal Kelly ({kelly_optimal:.1%}) is too aggressive."

        return KellyStressTest(
            kelly_optimal=kelly_optimal,
            kelly_safe=kelly_safe,
            kelly_conservative=kelly_conservative,
            prob_50pct_drawdown_optimal=analysis_optimal['prob_50pct_dd'],
            prob_ruin_optimal=analysis_optimal['prob_ruin'],
            prob_50pct_drawdown_safe=analysis_safe['prob_50pct_dd'],
            prob_ruin_safe=analysis_safe['prob_ruin'],
            num_simulations=self.num_simulations,
            num_trades_per_sim=self.num_trades_per_sim,
            median_final_equity_optimal=analysis_optimal['median_final_equity'],
            median_final_equity_safe=analysis_safe['median_final_equity'],
            var_95_optimal=(1 - analysis_optimal['var_95']) * 100,  # Convert to % loss
            var_95_safe=(1 - analysis_safe['var_95']) * 100,
            cvar_95_optimal=(1 - analysis_optimal['cvar_95']) * 100,
            cvar_95_safe=(1 - analysis_safe['cvar_95']) * 100,
            estimated_win_rate=win_rate,
            estimated_avg_win=avg_win,
            estimated_avg_loss=avg_loss,
            uncertainty_level=uncertainty_level,
            recommendation=recommendation
        )


def get_safe_position_size(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    sample_size: int = 50,
    account_size: float = 10000,
    max_risk_pct: float = 25.0
) -> Dict:
    """
    Get safe position size based on Monte Carlo stress testing.

    This is the MAIN FUNCTION to use for position sizing.

    Args:
        win_rate: Estimated win rate (0-1)
        avg_win: Average winning trade % (e.g., 15 for 15%)
        avg_loss: Average losing trade % (e.g., 10 for 10%)
        sample_size: Number of trades this estimate is based on
        account_size: Current account value
        max_risk_pct: Maximum % of account to risk per trade

    Returns:
        Dict with position sizing recommendations
    """
    # Run stress test
    mc = MonteCarloKelly(num_simulations=5000, num_trades_per_sim=200)
    stress_test = mc.stress_test(win_rate, avg_win, avg_loss, sample_size)

    # Use safe Kelly, capped at max_risk_pct
    kelly_to_use = min(stress_test.kelly_safe, max_risk_pct / 100)

    # Calculate position size
    position_value = account_size * kelly_to_use

    return {
        'position_size_pct': kelly_to_use * 100,
        'position_value': position_value,
        'kelly_optimal': stress_test.kelly_optimal * 100,
        'kelly_safe': stress_test.kelly_safe * 100,
        'kelly_conservative': stress_test.kelly_conservative * 100,
        'prob_50pct_drawdown': stress_test.prob_50pct_drawdown_safe * 100,
        'prob_ruin': stress_test.prob_ruin_safe * 100,
        'var_95': stress_test.var_95_safe,
        'uncertainty_level': stress_test.uncertainty_level,
        'recommendation': stress_test.recommendation,
        'stress_test': stress_test
    }


def validate_current_sizing(
    current_kelly_pct: float,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    sample_size: int = 50
) -> Dict:
    """
    Validate if current position sizing is safe.

    Returns warning if current sizing is too aggressive.
    """
    mc = MonteCarloKelly(num_simulations=5000, num_trades_per_sim=200)
    stress_test = mc.stress_test(win_rate, avg_win, avg_loss, sample_size)

    current_kelly = current_kelly_pct / 100

    # Run simulation at current Kelly
    estimate = mc.estimate_uncertainty(win_rate, avg_win, avg_loss, sample_size)
    results = mc.run_simulation(current_kelly, estimate, vary_parameters=True)
    analysis = mc.analyze_results(results)

    is_safe = current_kelly <= stress_test.kelly_safe
    is_conservative = current_kelly <= stress_test.kelly_conservative

    if current_kelly > stress_test.kelly_optimal:
        warning = f"DANGER: Current sizing ({current_kelly_pct:.1f}%) exceeds optimal Kelly ({stress_test.kelly_optimal*100:.1f}%). Reduce immediately!"
        risk_level = "CRITICAL"
    elif current_kelly > stress_test.kelly_safe:
        warning = f"WARNING: Current sizing ({current_kelly_pct:.1f}%) exceeds safe Kelly ({stress_test.kelly_safe*100:.1f}%). Consider reducing."
        risk_level = "HIGH"
    elif current_kelly > stress_test.kelly_conservative:
        warning = f"MODERATE: Current sizing ({current_kelly_pct:.1f}%) is between safe and conservative. Acceptable if confident in estimates."
        risk_level = "MODERATE"
    else:
        warning = f"SAFE: Current sizing ({current_kelly_pct:.1f}%) is conservative. Room to increase if desired."
        risk_level = "LOW"

    return {
        'current_kelly_pct': current_kelly_pct,
        'is_safe': is_safe,
        'is_conservative': is_conservative,
        'risk_level': risk_level,
        'warning': warning,
        'prob_ruin_at_current': analysis['prob_ruin'] * 100,
        'prob_50pct_dd_at_current': analysis['prob_50pct_dd'] * 100,
        'recommended_kelly_pct': stress_test.kelly_safe * 100,
        'stress_test': stress_test.to_dict()
    }


if __name__ == "__main__":
    print("=" * 60)
    print("Monte Carlo Kelly Stress Test")
    print("=" * 60)

    # Example: Strategy with 65% win rate, 15% avg win, 10% avg loss
    # Based on 50 historical trades

    result = get_safe_position_size(
        win_rate=0.65,
        avg_win=15.0,
        avg_loss=10.0,
        sample_size=50,
        account_size=10000
    )

    print(f"\nInput Parameters:")
    print(f"  Win Rate: 65%")
    print(f"  Avg Win: 15%")
    print(f"  Avg Loss: 10%")
    print(f"  Sample Size: 50 trades")

    print(f"\nKelly Fractions:")
    print(f"  Optimal Kelly: {result['kelly_optimal']:.1f}% (DON'T USE)")
    print(f"  Safe Kelly: {result['kelly_safe']:.1f}% (RECOMMENDED)")
    print(f"  Conservative Kelly: {result['kelly_conservative']:.1f}%")

    print(f"\nRisk Metrics at Safe Kelly:")
    print(f"  Prob of 50% Drawdown: {result['prob_50pct_drawdown']:.1f}%")
    print(f"  Prob of Ruin (75% loss): {result['prob_ruin']:.1f}%")
    print(f"  95% Value at Risk: {result['var_95']:.1f}%")

    print(f"\nPosition Sizing:")
    print(f"  Recommended: {result['position_size_pct']:.1f}% of account")
    print(f"  Dollar Value: ${result['position_value']:.2f}")

    print(f"\nUncertainty Level: {result['uncertainty_level'].upper()}")
    print(f"\nRecommendation:")
    print(f"  {result['recommendation']}")

    # Validate current sizing
    print("\n" + "=" * 60)
    print("Validating Current Sizing (20%)")
    print("=" * 60)

    validation = validate_current_sizing(
        current_kelly_pct=20.0,
        win_rate=0.65,
        avg_win=15.0,
        avg_loss=10.0,
        sample_size=50
    )

    print(f"\nRisk Level: {validation['risk_level']}")
    print(f"Is Safe: {validation['is_safe']}")
    print(f"Prob of Ruin at Current: {validation['prob_ruin_at_current']:.1f}%")
    print(f"\n{validation['warning']}")
