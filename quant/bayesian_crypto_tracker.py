"""
Bayesian Crypto Performance Tracker - Statistical edge validation for crypto strategies.

The core question: "Can you still make money in a choppy market?"
Answer: Yes, IF your edge is real. This tracker uses Bayesian inference to
separate genuine alpha from noise in high-frequency crypto trading.

Concept:
  - Starting capital (e.g., $10) making small gains (e.g., $0.05/5min)
  - Tracks whether the observed win rate is statistically significant
  - Uses Beta-Binomial conjugate priors for real-time probability updating
  - Regime-aware: tracks performance across funding rate regimes,
    leverage regimes, and market volatility states
  - Answers: "Is this edge real, or am I just lucky?"

Statistical Foundation:
  - Prior: Beta(alpha=1, beta=1) = Uniform (no prior belief)
  - Posterior after n trades: Beta(alpha + wins, beta + losses)
  - Credible interval: 95% HDI of the posterior distribution
  - Edge detection: P(win_rate > breakeven) from posterior CDF
  - Kelly fraction: optimal bet sizing from Bayesian estimate

Integration:
  - Consumed by AGAPE (ETH Micro Futures) and AGAPE-SPOT (Coinbase Spot)
  - Fed by closed trade outcomes from any crypto bot
  - Provides real-time confidence that a strategy has genuine edge
"""

import math
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CryptoRegime(Enum):
    """Market regime derived from crypto microstructure signals."""
    EXTREME_LONG = "EXTREME_LONG"
    OVERLEVERAGED_LONG = "OVERLEVERAGED_LONG"
    MILD_LONG_BIAS = "MILD_LONG_BIAS"
    BALANCED = "BALANCED"
    MILD_SHORT_BIAS = "MILD_SHORT_BIAS"
    OVERLEVERAGED_SHORT = "OVERLEVERAGED_SHORT"
    EXTREME_SHORT = "EXTREME_SHORT"
    UNKNOWN = "UNKNOWN"


class VolatilityState(Enum):
    """Volatility regime for crypto markets."""
    LOW = "LOW"              # Tight range, small moves
    NORMAL = "NORMAL"        # Average volatility
    ELEVATED = "ELEVATED"    # Above average, wider swings
    HIGH = "HIGH"            # Significant volatility
    EXTREME = "EXTREME"      # Crisis-level moves


class EdgeVerdict(Enum):
    """Statistical verdict on whether a strategy has real edge."""
    CONFIRMED_EDGE = "CONFIRMED_EDGE"          # >95% probability edge is real
    PROBABLE_EDGE = "PROBABLE_EDGE"            # 80-95% probability
    INCONCLUSIVE = "INCONCLUSIVE"              # 50-80% probability
    PROBABLY_NO_EDGE = "PROBABLY_NO_EDGE"      # 20-50% probability
    NO_EDGE = "NO_EDGE"                        # <20% probability


class TimeWindow(Enum):
    """Time windows for performance aggregation."""
    LAST_HOUR = "1h"
    LAST_4_HOURS = "4h"
    LAST_24_HOURS = "24h"
    LAST_7_DAYS = "7d"
    ALL_TIME = "all"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class TradeOutcome:
    """A single trade result fed into the Bayesian tracker."""
    trade_id: str
    symbol: str
    side: str                          # "long" or "short"
    entry_price: float
    exit_price: float
    pnl: float                         # Realized P&L in USD
    contracts: int
    entry_time: datetime
    exit_time: datetime
    hold_duration_minutes: float

    # Market context at trade time
    funding_regime: str = "UNKNOWN"
    leverage_regime: str = "UNKNOWN"
    volatility_state: str = "NORMAL"
    ls_bias: str = "NEUTRAL"

    # Was it a win?
    @property
    def is_win(self) -> bool:
        return self.pnl > 0

    @property
    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        direction = 1 if self.side == "long" else -1
        return ((self.exit_price - self.entry_price) / self.entry_price) * 100 * direction


@dataclass
class BayesianEstimate:
    """Bayesian posterior estimate of win probability."""
    alpha: float                       # Beta distribution alpha (wins + prior)
    beta_param: float                  # Beta distribution beta (losses + prior)
    mean: float                        # Posterior mean = alpha / (alpha + beta)
    median: float                      # Posterior median approximation
    mode: float                        # Posterior mode (most likely value)
    ci_lower: float                    # 95% credible interval lower bound
    ci_upper: float                    # 95% credible interval upper bound
    total_trades: int
    edge_probability: float            # P(win_rate > breakeven)
    verdict: EdgeVerdict
    kelly_fraction: float              # Optimal bet fraction

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alpha": round(self.alpha, 3),
            "beta": round(self.beta_param, 3),
            "mean_win_rate": round(self.mean, 4),
            "median_win_rate": round(self.median, 4),
            "mode_win_rate": round(self.mode, 4),
            "ci_95_lower": round(self.ci_lower, 4),
            "ci_95_upper": round(self.ci_upper, 4),
            "total_trades": self.total_trades,
            "edge_probability": round(self.edge_probability, 4),
            "verdict": self.verdict.value,
            "kelly_fraction": round(self.kelly_fraction, 4),
        }


@dataclass
class RegimePerformance:
    """Performance statistics for a specific market regime."""
    regime: str
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0

    @property
    def total_trades(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.wins / self.total_trades

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime,
            "wins": self.wins,
            "losses": self.losses,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "total_pnl": round(self.total_pnl, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "best_trade": round(self.best_trade, 2),
            "worst_trade": round(self.worst_trade, 2),
        }


@dataclass
class StreakAnalysis:
    """Tracks winning and losing streaks for psychological insight."""
    current_streak: int = 0            # Positive = wins, negative = losses
    max_win_streak: int = 0
    max_loss_streak: int = 0
    streak_history: List[int] = field(default_factory=list)

    def update(self, won: bool):
        if won:
            if self.current_streak > 0:
                self.current_streak += 1
            else:
                self.current_streak = 1
            self.max_win_streak = max(self.max_win_streak, self.current_streak)
        else:
            if self.current_streak < 0:
                self.current_streak -= 1
            else:
                self.current_streak = -1
            self.max_loss_streak = max(self.max_loss_streak, abs(self.current_streak))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_streak": self.current_streak,
            "max_win_streak": self.max_win_streak,
            "max_loss_streak": self.max_loss_streak,
        }


@dataclass
class ChoppyMarketMetrics:
    """Metrics specifically for choppy/sideways market performance.

    The core premise: small, consistent gains ($0.05 per 5-min interval)
    can compound into significant returns IF the edge is genuine.
    """
    intervals_tracked: int = 0         # Number of 5-min intervals observed
    profitable_intervals: int = 0
    avg_gain_per_interval: float = 0.0
    avg_loss_per_interval: float = 0.0
    cumulative_pnl: float = 0.0
    starting_capital: float = 0.0

    # Projected returns (based on observed data)
    projected_hourly: float = 0.0
    projected_daily: float = 0.0
    projected_weekly: float = 0.0

    # Reality check
    annualized_return_pct: float = 0.0
    sharpe_ratio: float = 0.0          # Risk-adjusted return
    max_drawdown: float = 0.0
    drawdown_duration_minutes: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intervals_tracked": self.intervals_tracked,
            "profitable_intervals": self.profitable_intervals,
            "interval_win_rate": round(
                self.profitable_intervals / max(1, self.intervals_tracked), 4
            ),
            "avg_gain_per_interval": round(self.avg_gain_per_interval, 4),
            "avg_loss_per_interval": round(self.avg_loss_per_interval, 4),
            "cumulative_pnl": round(self.cumulative_pnl, 2),
            "starting_capital": round(self.starting_capital, 2),
            "return_pct": round(
                (self.cumulative_pnl / max(1, self.starting_capital)) * 100, 2
            ),
            "projected_hourly": round(self.projected_hourly, 4),
            "projected_daily": round(self.projected_daily, 2),
            "projected_weekly": round(self.projected_weekly, 2),
            "annualized_return_pct": round(self.annualized_return_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "max_drawdown": round(self.max_drawdown, 2),
            "drawdown_duration_minutes": round(self.drawdown_duration_minutes, 1),
        }


# ---------------------------------------------------------------------------
# Core Bayesian Engine
# ---------------------------------------------------------------------------

class BayesianCryptoTracker:
    """
    Bayesian performance tracker for crypto trading strategies.

    Uses Beta-Binomial conjugate model for real-time win probability updating.
    Tracks performance across market regimes (funding, leverage, volatility).
    Provides statistical edge detection with credible intervals.

    Key Methods:
      - record_trade(): Feed a trade outcome
      - get_estimate(): Current Bayesian win probability estimate
      - get_regime_breakdown(): Performance by market regime
      - get_choppy_market_metrics(): Small-gain strategy analysis
      - get_edge_verdict(): Is the edge statistically real?
    """

    def __init__(
        self,
        strategy_name: str = "crypto_default",
        starting_capital: float = 10.0,
        breakeven_win_rate: float = 0.50,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
    ):
        self.strategy_name = strategy_name
        self.starting_capital = starting_capital
        self.breakeven_win_rate = breakeven_win_rate

        # Bayesian state
        self.alpha = prior_alpha
        self.beta_param = prior_beta
        self.total_wins = 0
        self.total_losses = 0

        # Regime tracking
        self.regime_stats: Dict[str, RegimePerformance] = {}
        self.volatility_stats: Dict[str, RegimePerformance] = {}

        # Streak tracking
        self.streaks = StreakAnalysis()

        # Trade history (in-memory, limited to recent trades)
        self.recent_trades: List[TradeOutcome] = []
        self.max_recent_trades = 500

        # P&L tracking
        self.cumulative_pnl = 0.0
        self.equity_high_water_mark = starting_capital
        self.max_drawdown = 0.0
        self.drawdown_start: Optional[datetime] = None
        self.max_drawdown_duration = timedelta(0)

        # Interval tracking for choppy market analysis
        self.interval_pnls: List[float] = []

        # Timestamps
        self.created_at = datetime.now(CENTRAL_TZ)
        self.last_updated: Optional[datetime] = None

    def record_trade(self, outcome: TradeOutcome) -> BayesianEstimate:
        """
        Record a trade outcome and update Bayesian estimates.

        Returns the updated posterior estimate.
        """
        # Update Bayesian parameters
        if outcome.is_win:
            self.alpha += 1
            self.total_wins += 1
        else:
            self.beta_param += 1
            self.total_losses += 1

        # Update P&L tracking
        self.cumulative_pnl += outcome.pnl
        current_equity = self.starting_capital + self.cumulative_pnl

        # Drawdown tracking
        if current_equity > self.equity_high_water_mark:
            self.equity_high_water_mark = current_equity
            self.drawdown_start = None
        else:
            drawdown = self.equity_high_water_mark - current_equity
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
            if self.drawdown_start is None:
                self.drawdown_start = outcome.exit_time
            else:
                dd_duration = outcome.exit_time - self.drawdown_start
                if dd_duration > self.max_drawdown_duration:
                    self.max_drawdown_duration = dd_duration

        # Update regime stats
        self._update_regime_stats(outcome)

        # Update streaks
        self.streaks.update(outcome.is_win)

        # Track interval P&L
        self.interval_pnls.append(outcome.pnl)

        # Store recent trade
        self.recent_trades.append(outcome)
        if len(self.recent_trades) > self.max_recent_trades:
            self.recent_trades = self.recent_trades[-self.max_recent_trades:]

        self.last_updated = datetime.now(CENTRAL_TZ)

        return self.get_estimate()

    def get_estimate(self) -> BayesianEstimate:
        """
        Calculate current Bayesian posterior estimate.

        Uses the Beta distribution:
          - Mean = alpha / (alpha + beta)
          - Mode = (alpha - 1) / (alpha + beta - 2) when alpha, beta > 1
          - 95% CI from Beta quantiles
        """
        a = self.alpha
        b = self.beta_param
        total = self.total_wins + self.total_losses

        # Posterior mean
        mean = a / (a + b)

        # Posterior median (approximation for Beta distribution)
        median = (a - 1/3) / (a + b - 2/3) if (a + b) > 1 else 0.5

        # Posterior mode
        if a > 1 and b > 1:
            mode = (a - 1) / (a + b - 2)
        else:
            mode = mean  # Fallback when mode is at boundary

        # 95% credible interval using normal approximation
        # For Beta(a,b): variance = ab / ((a+b)^2 * (a+b+1))
        variance = (a * b) / ((a + b) ** 2 * (a + b + 1))
        std = math.sqrt(variance)
        ci_lower = max(0, mean - 1.96 * std)
        ci_upper = min(1, mean + 1.96 * std)

        # Edge probability: P(win_rate > breakeven) using normal approx
        if std > 0:
            z = (mean - self.breakeven_win_rate) / std
            edge_prob = _normal_cdf(z)
        else:
            edge_prob = 1.0 if mean > self.breakeven_win_rate else 0.0

        # Verdict
        verdict = self._classify_edge(edge_prob, total)

        # Kelly fraction: f* = (p*b - q) / b
        # Where p=win_rate, q=1-p, b=avg_win/avg_loss
        kelly = self._calculate_kelly(mean)

        return BayesianEstimate(
            alpha=a,
            beta_param=b,
            mean=mean,
            median=median,
            mode=mode,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            total_trades=total,
            edge_probability=edge_prob,
            verdict=verdict,
            kelly_fraction=kelly,
        )

    def get_regime_breakdown(self) -> Dict[str, Dict[str, Any]]:
        """Get performance breakdown by funding regime."""
        result = {}
        for regime_name, stats in self.regime_stats.items():
            if stats.total_trades > 0:
                # Calculate Bayesian estimate for this regime
                a = stats.wins + 1
                b = stats.losses + 1
                regime_mean = a / (a + b)
                var = (a * b) / ((a + b) ** 2 * (a + b + 1))
                std = math.sqrt(var)

                result[regime_name] = {
                    **stats.to_dict(),
                    "bayesian_win_rate": round(regime_mean, 4),
                    "ci_lower": round(max(0, regime_mean - 1.96 * std), 4),
                    "ci_upper": round(min(1, regime_mean + 1.96 * std), 4),
                }
        return result

    def get_volatility_breakdown(self) -> Dict[str, Dict[str, Any]]:
        """Get performance breakdown by volatility state."""
        result = {}
        for vol_name, stats in self.volatility_stats.items():
            if stats.total_trades > 0:
                a = stats.wins + 1
                b = stats.losses + 1
                vol_mean = a / (a + b)
                result[vol_name] = {
                    **stats.to_dict(),
                    "bayesian_win_rate": round(vol_mean, 4),
                }
        return result

    def get_choppy_market_metrics(self) -> ChoppyMarketMetrics:
        """
        Analyze performance for the choppy-market small-gain strategy.

        Maps to the user's scenario:
          Starting with $10, making $0.05 every 5 minutes, 24/7.
          Reality: how does actual performance compare?
        """
        metrics = ChoppyMarketMetrics(
            starting_capital=self.starting_capital,
            cumulative_pnl=self.cumulative_pnl,
        )

        if not self.interval_pnls:
            return metrics

        gains = [p for p in self.interval_pnls if p > 0]
        losses = [p for p in self.interval_pnls if p <= 0]

        metrics.intervals_tracked = len(self.interval_pnls)
        metrics.profitable_intervals = len(gains)

        if gains:
            metrics.avg_gain_per_interval = sum(gains) / len(gains)
        if losses:
            metrics.avg_loss_per_interval = sum(losses) / len(losses)

        # Project returns based on observed average per interval
        avg_per_interval = sum(self.interval_pnls) / len(self.interval_pnls)
        metrics.projected_hourly = avg_per_interval * 12       # 12 intervals/hour
        metrics.projected_daily = avg_per_interval * 288       # 288 intervals/day
        metrics.projected_weekly = avg_per_interval * 2016     # 2016 intervals/week

        # Annualized return
        if self.starting_capital > 0 and metrics.projected_weekly != 0:
            weekly_return = metrics.projected_weekly / self.starting_capital
            metrics.annualized_return_pct = weekly_return * 52 * 100

        # Sharpe ratio (annualized, using interval returns)
        if len(self.interval_pnls) > 1:
            import statistics
            returns = [p / max(1, self.starting_capital) for p in self.interval_pnls]
            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)
            if std_return > 0:
                # Annualize: multiply by sqrt(intervals_per_year)
                intervals_per_year = 288 * 365
                metrics.sharpe_ratio = (mean_return / std_return) * math.sqrt(intervals_per_year)

        metrics.max_drawdown = self.max_drawdown
        metrics.drawdown_duration_minutes = self.max_drawdown_duration.total_seconds() / 60

        return metrics

    def get_time_window_stats(self, window: TimeWindow) -> Dict[str, Any]:
        """Get stats for a specific time window."""
        now = datetime.now(CENTRAL_TZ)

        if window == TimeWindow.LAST_HOUR:
            cutoff = now - timedelta(hours=1)
        elif window == TimeWindow.LAST_4_HOURS:
            cutoff = now - timedelta(hours=4)
        elif window == TimeWindow.LAST_24_HOURS:
            cutoff = now - timedelta(hours=24)
        elif window == TimeWindow.LAST_7_DAYS:
            cutoff = now - timedelta(days=7)
        else:
            cutoff = datetime.min.replace(tzinfo=CENTRAL_TZ)

        filtered = [t for t in self.recent_trades if t.exit_time >= cutoff]
        if not filtered:
            return {
                "window": window.value,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
            }

        wins = sum(1 for t in filtered if t.is_win)
        losses = len(filtered) - wins
        total_pnl = sum(t.pnl for t in filtered)

        return {
            "window": window.value,
            "trades": len(filtered),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(filtered), 4),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(filtered), 4),
        }

    def get_full_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        estimate = self.get_estimate()

        return {
            "strategy_name": self.strategy_name,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "starting_capital": self.starting_capital,
            "current_equity": round(self.starting_capital + self.cumulative_pnl, 2),
            "cumulative_pnl": round(self.cumulative_pnl, 2),
            "total_return_pct": round(
                (self.cumulative_pnl / max(1, self.starting_capital)) * 100, 2
            ),
            "bayesian_estimate": estimate.to_dict(),
            "regime_breakdown": self.get_regime_breakdown(),
            "volatility_breakdown": self.get_volatility_breakdown(),
            "streaks": self.streaks.to_dict(),
            "choppy_market_metrics": self.get_choppy_market_metrics().to_dict(),
            "time_windows": {
                w.value: self.get_time_window_stats(w)
                for w in TimeWindow
            },
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _update_regime_stats(self, outcome: TradeOutcome):
        """Update per-regime performance stats."""
        # Funding regime
        regime = outcome.funding_regime
        if regime not in self.regime_stats:
            self.regime_stats[regime] = RegimePerformance(regime=regime)
        stats = self.regime_stats[regime]
        self._apply_outcome_to_stats(stats, outcome)

        # Volatility state
        vol = outcome.volatility_state
        if vol not in self.volatility_stats:
            self.volatility_stats[vol] = RegimePerformance(regime=vol)
        vstats = self.volatility_stats[vol]
        self._apply_outcome_to_stats(vstats, outcome)

    @staticmethod
    def _apply_outcome_to_stats(stats: RegimePerformance, outcome: TradeOutcome):
        """Apply a trade outcome to a RegimePerformance object."""
        if outcome.is_win:
            stats.wins += 1
            stats.avg_win = (
                (stats.avg_win * (stats.wins - 1) + outcome.pnl) / stats.wins
            )
            if outcome.pnl > stats.best_trade:
                stats.best_trade = outcome.pnl
        else:
            stats.losses += 1
            n = stats.losses
            stats.avg_loss = (
                (stats.avg_loss * (n - 1) + outcome.pnl) / n
            )
            if outcome.pnl < stats.worst_trade:
                stats.worst_trade = outcome.pnl
        stats.total_pnl += outcome.pnl

    def _classify_edge(self, edge_prob: float, total_trades: int) -> EdgeVerdict:
        """Classify the edge verdict based on probability and sample size."""
        # Need minimum trades for any verdict beyond inconclusive
        if total_trades < 5:
            return EdgeVerdict.INCONCLUSIVE

        if edge_prob >= 0.95:
            return EdgeVerdict.CONFIRMED_EDGE
        elif edge_prob >= 0.80:
            return EdgeVerdict.PROBABLE_EDGE
        elif edge_prob >= 0.50:
            return EdgeVerdict.INCONCLUSIVE
        elif edge_prob >= 0.20:
            return EdgeVerdict.PROBABLY_NO_EDGE
        else:
            return EdgeVerdict.NO_EDGE

    def _calculate_kelly(self, win_rate: float) -> float:
        """Calculate Kelly criterion fraction for optimal bet sizing."""
        if not self.recent_trades:
            return 0.0

        wins = [t for t in self.recent_trades if t.is_win]
        losses = [t for t in self.recent_trades if not t.is_win]

        if not wins or not losses:
            return 0.0

        avg_win = sum(t.pnl for t in wins) / len(wins)
        avg_loss = abs(sum(t.pnl for t in losses) / len(losses))

        if avg_loss == 0:
            return 0.0

        # Kelly: f* = (p * b - q) / b where b = avg_win / avg_loss
        b = avg_win / avg_loss
        q = 1 - win_rate
        kelly = (win_rate * b - q) / b

        # Cap at half-Kelly for safety
        return max(0.0, min(kelly * 0.5, 0.25))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize tracker state for database persistence."""
        return {
            "strategy_name": self.strategy_name,
            "starting_capital": self.starting_capital,
            "breakeven_win_rate": self.breakeven_win_rate,
            "alpha": self.alpha,
            "beta": self.beta_param,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "cumulative_pnl": self.cumulative_pnl,
            "equity_high_water_mark": self.equity_high_water_mark,
            "max_drawdown": self.max_drawdown,
            "max_win_streak": self.streaks.max_win_streak,
            "max_loss_streak": self.streaks.max_loss_streak,
            "current_streak": self.streaks.current_streak,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BayesianCryptoTracker":
        """Restore tracker state from database."""
        tracker = cls(
            strategy_name=data.get("strategy_name", "crypto_default"),
            starting_capital=data.get("starting_capital", 10.0),
            breakeven_win_rate=data.get("breakeven_win_rate", 0.50),
            prior_alpha=data.get("alpha", 1.0),
            prior_beta=data.get("beta", 1.0),
        )
        tracker.total_wins = data.get("total_wins", 0)
        tracker.total_losses = data.get("total_losses", 0)
        tracker.cumulative_pnl = data.get("cumulative_pnl", 0.0)
        tracker.equity_high_water_mark = data.get("equity_high_water_mark", tracker.starting_capital)
        tracker.max_drawdown = data.get("max_drawdown", 0.0)
        tracker.streaks.max_win_streak = data.get("max_win_streak", 0)
        tracker.streaks.max_loss_streak = data.get("max_loss_streak", 0)
        tracker.streaks.current_streak = data.get("current_streak", 0)

        created = data.get("created_at")
        if created and isinstance(created, str):
            try:
                tracker.created_at = datetime.fromisoformat(created)
            except (ValueError, TypeError):
                pass

        updated = data.get("last_updated")
        if updated and isinstance(updated, str):
            try:
                tracker.last_updated = datetime.fromisoformat(updated)
            except (ValueError, TypeError):
                pass

        return tracker


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _normal_cdf(z: float) -> float:
    """
    Standard normal CDF approximation (Abramowitz & Stegun).
    Avoids scipy dependency.
    """
    if z > 6:
        return 1.0
    if z < -6:
        return 0.0

    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429
    p = 0.2316419

    t = 1.0 / (1.0 + p * abs(z))
    pdf = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z * z)
    poly = ((((b5 * t + b4) * t + b3) * t + b2) * t + b1) * t
    cdf = 1.0 - pdf * poly

    if z < 0:
        cdf = 1.0 - cdf

    return cdf


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_trackers: Dict[str, BayesianCryptoTracker] = {}
_trackers_lock = None

try:
    import threading
    _trackers_lock = threading.Lock()
except ImportError:
    pass


def get_tracker(strategy_name: str = "crypto_default", **kwargs) -> BayesianCryptoTracker:
    """Get or create a Bayesian tracker for a strategy."""
    if _trackers_lock:
        with _trackers_lock:
            if strategy_name not in _trackers:
                _trackers[strategy_name] = BayesianCryptoTracker(
                    strategy_name=strategy_name, **kwargs
                )
            return _trackers[strategy_name]
    else:
        if strategy_name not in _trackers:
            _trackers[strategy_name] = BayesianCryptoTracker(
                strategy_name=strategy_name, **kwargs
            )
        return _trackers[strategy_name]


def list_trackers() -> List[str]:
    """List all active tracker names."""
    return list(_trackers.keys())
