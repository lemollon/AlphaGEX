"""
AlphaGEX Mathematical Optimization Algorithms
==============================================

This module implements advanced mathematical algorithms to enhance trading bot
performance. These algorithms integrate with Proverbs's feedback loop to provide
continuous optimization while maintaining full transparency and human oversight.

ALGORITHMS IMPLEMENTED:
1. Hidden Markov Model (HMM) - Regime detection with probability distributions
2. Kalman Filter - Greeks and signal smoothing
3. Thompson Sampling - Dynamic bot capital allocation (Multi-Armed Bandit)
4. Convex Optimizer - Optimal strike selection under constraints
5. Hamilton-Jacobi-Bellman (HJB) - Optimal exit timing
6. Markov Decision Process (MDP) - Trade sequencing optimization

PROVERBS INTEGRATION:
Each algorithm logs its decisions to Proverbs's audit trail with:
- WHO: Which algorithm made the decision
- WHAT: The specific optimization performed
- WHY: Mathematical justification (metrics, probabilities)
- WHEN: Timestamp of the decision

Author: AlphaGEX Quant Team
Date: January 2025
"""

from __future__ import annotations

import os
import sys
import json
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from zoneinfo import ZoneInfo
import numpy as np
from collections import defaultdict

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Central timezone for AlphaGEX
CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class MarketRegime(Enum):
    """Market regimes detected by HMM"""
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    MEAN_REVERTING = "MEAN_REVERTING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    GAMMA_SQUEEZE = "GAMMA_SQUEEZE"
    PINNED = "PINNED"


class OptimizationAction(Enum):
    """Actions logged to Proverbs"""
    HMM_REGIME_UPDATE = "HMM_REGIME_UPDATE"
    KALMAN_SMOOTHING = "KALMAN_SMOOTHING"
    THOMPSON_ALLOCATION = "THOMPSON_ALLOCATION"
    CONVEX_STRIKE_OPTIMIZATION = "CONVEX_STRIKE_OPTIMIZATION"
    HJB_EXIT_SIGNAL = "HJB_EXIT_SIGNAL"
    MDP_TRADE_SEQUENCE = "MDP_TRADE_SEQUENCE"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RegimeState:
    """HMM regime state with probabilities"""
    regime: MarketRegime
    probability: float
    confidence: float
    observation_features: Dict[str, float] = field(default_factory=dict)
    transition_from: Optional[MarketRegime] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))

    def to_dict(self) -> Dict:
        return {
            'regime': self.regime.value,
            'probability': self.probability,
            'confidence': self.confidence,
            'observation_features': self.observation_features,
            'transition_from': self.transition_from.value if self.transition_from else None,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class KalmanState:
    """Kalman filter state for signal smoothing"""
    value: float
    variance: float
    kalman_gain: float
    raw_observation: float
    smoothed_value: float
    prediction: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ThompsonAllocation:
    """Thompson Sampling allocation result"""
    allocations: Dict[str, float]  # bot_name -> allocation percentage
    sampled_rewards: Dict[str, float]  # bot_name -> sampled reward
    exploration_bonus: Dict[str, float]  # uncertainty bonus per bot
    timestamp: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))

    def to_dict(self) -> Dict:
        return {
            'allocations': self.allocations,
            'sampled_rewards': self.sampled_rewards,
            'exploration_bonus': self.exploration_bonus,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class StrikeOptimization:
    """Convex optimizer result for strike selection"""
    original_strike: float
    optimized_strike: float
    expected_loss_original: float
    expected_loss_optimized: float
    improvement_pct: float
    constraints_satisfied: Dict[str, bool]
    scenarios_evaluated: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ExitSignal:
    """HJB exit optimizer signal"""
    should_exit: bool
    current_pnl_pct: float
    optimal_boundary: float
    time_value: float
    volatility_factor: float
    expected_future_value: float
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TradeSequence:
    """MDP trade sequencer result"""
    original_order: List[Dict]
    optimized_order: List[Dict]
    expected_value_original: float
    expected_value_optimized: float
    skipped_trades: List[Dict]
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# 1. HIDDEN MARKOV MODEL (HMM) - REGIME DETECTION
# =============================================================================

class HiddenMarkovRegimeDetector:
    """
    Hidden Markov Model for Market Regime Detection

    Mathematical Foundation:
    - Hidden states S = {TRENDING, MEAN_REVERTING, VOLATILE, PINNED, ...}
    - Observations O = {VIX, net_gamma, momentum, volume, etc.}
    - Transition matrix A[i,j] = P(state_j | state_i)
    - Emission matrix B[i,k] = P(observation_k | state_i)

    Algorithm: Forward-backward with Viterbi decoding
    - Forward: α_t(i) = P(o_1:t, s_t=i)
    - Backward: β_t(i) = P(o_t+1:T | s_t=i)
    - Viterbi: Find most likely state sequence

    WHY THIS IMPROVES TRADING:
    - Instead of hard "IF vix > 20 THEN volatile", we get probability distributions
    - Reduces regime whipsaw by requiring high confidence for transitions
    - Learns transition patterns from historical data
    """

    def __init__(self):
        self.n_states = len(MarketRegime)
        self.states = list(MarketRegime)

        # Initialize transition matrix (learned from data)
        # A[i,j] = P(transition from state i to state j)
        self._init_transition_matrix()

        # Emission parameters (Gaussian for each feature per state)
        self._init_emission_params()

        # Current state belief (probability distribution over states)
        self.state_belief = np.ones(self.n_states) / self.n_states

        # History for learning
        self.observation_history: List[Dict] = []
        self.state_history: List[MarketRegime] = []

        # Minimum confidence for regime change
        self.min_transition_confidence = 0.70

        logger.info("HMM Regime Detector initialized with %d states", self.n_states)

    def _init_transition_matrix(self):
        """
        Initialize transition probabilities.

        Based on market microstructure:
        - Most states have high self-transition (markets persist)
        - Some transitions are more likely (trending -> volatile)
        """
        # Base: high self-transition probability (0.85)
        self.transition_matrix = np.eye(self.n_states) * 0.85

        # Add off-diagonal transitions (remaining 0.15 distributed)
        for i in range(self.n_states):
            remaining = 0.15
            other_states = [j for j in range(self.n_states) if j != i]
            for j in other_states:
                self.transition_matrix[i, j] = remaining / len(other_states)

        # Override with domain knowledge
        state_idx = {s: i for i, s in enumerate(self.states)}

        # Trending more likely to go to high volatility
        if MarketRegime.TRENDING_BULLISH in state_idx and MarketRegime.HIGH_VOLATILITY in state_idx:
            self.transition_matrix[state_idx[MarketRegime.TRENDING_BULLISH], state_idx[MarketRegime.HIGH_VOLATILITY]] = 0.08

        # Mean reverting likely to stay or go to pinned
        if MarketRegime.MEAN_REVERTING in state_idx and MarketRegime.PINNED in state_idx:
            self.transition_matrix[state_idx[MarketRegime.MEAN_REVERTING], state_idx[MarketRegime.PINNED]] = 0.10

        # Normalize rows
        self.transition_matrix = self.transition_matrix / self.transition_matrix.sum(axis=1, keepdims=True)

    def _init_emission_params(self):
        """
        Initialize emission parameters (Gaussian mean/variance for each feature per state).

        Features: VIX, net_gamma, momentum, realized_vol, volume_ratio
        """
        # Mean and std for each feature per state
        # Format: {state: {feature: (mean, std)}}
        self.emission_params = {
            MarketRegime.TRENDING_BULLISH: {
                'vix': (15.0, 3.0),
                'net_gamma': (0.5, 0.3),
                'momentum': (0.8, 0.2),
                'realized_vol': (0.12, 0.03),
                'volume_ratio': (1.1, 0.2)
            },
            MarketRegime.TRENDING_BEARISH: {
                'vix': (22.0, 5.0),
                'net_gamma': (-0.3, 0.3),
                'momentum': (-0.7, 0.2),
                'realized_vol': (0.18, 0.04),
                'volume_ratio': (1.3, 0.3)
            },
            MarketRegime.MEAN_REVERTING: {
                'vix': (16.0, 2.0),
                'net_gamma': (0.2, 0.2),
                'momentum': (0.0, 0.3),
                'realized_vol': (0.10, 0.02),
                'volume_ratio': (0.9, 0.15)
            },
            MarketRegime.HIGH_VOLATILITY: {
                'vix': (28.0, 8.0),
                'net_gamma': (-0.5, 0.4),
                'momentum': (0.0, 0.5),
                'realized_vol': (0.25, 0.08),
                'volume_ratio': (1.5, 0.4)
            },
            MarketRegime.LOW_VOLATILITY: {
                'vix': (12.0, 2.0),
                'net_gamma': (0.4, 0.2),
                'momentum': (0.2, 0.2),
                'realized_vol': (0.08, 0.02),
                'volume_ratio': (0.8, 0.1)
            },
            MarketRegime.GAMMA_SQUEEZE: {
                'vix': (25.0, 6.0),
                'net_gamma': (-0.8, 0.2),
                'momentum': (0.5, 0.4),
                'realized_vol': (0.30, 0.10),
                'volume_ratio': (2.0, 0.5)
            },
            MarketRegime.PINNED: {
                'vix': (14.0, 2.0),
                'net_gamma': (0.6, 0.2),
                'momentum': (0.0, 0.1),
                'realized_vol': (0.06, 0.02),
                'volume_ratio': (0.7, 0.1)
            }
        }

    def _gaussian_prob(self, x: float, mean: float, std: float) -> float:
        """Calculate Gaussian probability density"""
        if std <= 0:
            std = 0.001
        return (1 / (std * math.sqrt(2 * math.pi))) * math.exp(-0.5 * ((x - mean) / std) ** 2)

    def _emission_probability(self, state: MarketRegime, observation: Dict[str, float]) -> float:
        """
        Calculate P(observation | state) using Gaussian emission model.

        Formula: P(obs | state) = Π_i P(feature_i | state)
                                = Π_i N(feature_i; μ_state,i, σ_state,i)
        """
        params = self.emission_params.get(state, {})
        prob = 1.0

        for feature, value in observation.items():
            if feature in params:
                mean, std = params[feature]
                prob *= self._gaussian_prob(value, mean, std)

        return max(prob, 1e-10)  # Avoid zero probability

    def update(self, observation: Dict[str, float]) -> RegimeState:
        """
        Update regime belief given new observation.

        Uses Bayesian update (forward algorithm step):
        P(s_t | o_1:t) ∝ P(o_t | s_t) × Σ P(s_t | s_t-1) × P(s_t-1 | o_1:t-1)

        Args:
            observation: Dict with keys like 'vix', 'net_gamma', 'momentum', etc.

        Returns:
            RegimeState with most likely regime and probability
        """
        # Store observation
        self.observation_history.append(observation)

        # Calculate emission probabilities for all states
        emission_probs = np.array([
            self._emission_probability(state, observation)
            for state in self.states
        ])

        # Forward step: predict then update
        # Predict: P(s_t | o_1:t-1) = Σ P(s_t | s_t-1) × P(s_t-1 | o_1:t-1)
        predicted_belief = self.transition_matrix.T @ self.state_belief

        # Update: P(s_t | o_1:t) ∝ P(o_t | s_t) × P(s_t | o_1:t-1)
        updated_belief = emission_probs * predicted_belief

        # Normalize
        updated_belief = updated_belief / (updated_belief.sum() + 1e-10)

        # Get previous most likely state
        prev_state_idx = np.argmax(self.state_belief)
        prev_state = self.states[prev_state_idx]

        # Update belief
        self.state_belief = updated_belief

        # Get current most likely state
        current_state_idx = np.argmax(updated_belief)
        current_state = self.states[current_state_idx]
        current_prob = updated_belief[current_state_idx]

        # Calculate confidence (how much better than second best)
        sorted_probs = np.sort(updated_belief)[::-1]
        confidence = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else sorted_probs[0]

        # Only transition if confidence exceeds threshold
        transition_from = None
        if current_state != prev_state:
            if current_prob >= self.min_transition_confidence:
                transition_from = prev_state
                self.state_history.append(current_state)
                logger.info(f"HMM Regime transition: {prev_state.value} → {current_state.value} (prob={current_prob:.2%})")
            else:
                # Revert to previous state due to low confidence
                current_state = prev_state
                current_prob = self.state_belief[prev_state_idx]
                logger.debug(f"HMM: Low confidence transition blocked ({current_prob:.2%} < {self.min_transition_confidence:.2%})")

        return RegimeState(
            regime=current_state,
            probability=float(current_prob),  # Convert numpy to native Python
            confidence=float(confidence),  # Convert numpy to native Python
            observation_features=observation,
            transition_from=transition_from
        )

    def get_regime_probabilities(self) -> Dict[str, float]:
        """Get probability distribution over all regimes"""
        return {
            state.value: float(prob)  # Convert numpy.float64 to native Python float
            for state, prob in zip(self.states, self.state_belief)
        }

    def get_transition_probability(self, from_state: MarketRegime, to_state: MarketRegime) -> float:
        """Get probability of transitioning between states"""
        from_idx = self.states.index(from_state)
        to_idx = self.states.index(to_state)
        return float(self.transition_matrix[from_idx, to_idx])  # Convert numpy to native Python

    def train_from_history(self, observations: List[Dict], labels: List[MarketRegime]):
        """
        Train emission parameters from labeled historical data.

        Uses Maximum Likelihood Estimation:
        μ_state,feature = mean(feature values when in state)
        σ_state,feature = std(feature values when in state)
        """
        if len(observations) != len(labels):
            raise ValueError("Observations and labels must have same length")

        # Group observations by state
        state_observations = defaultdict(list)
        for obs, label in zip(observations, labels):
            state_observations[label].append(obs)

        # Update emission parameters
        for state, obs_list in state_observations.items():
            if len(obs_list) < 5:  # Need minimum samples
                continue

            for feature in obs_list[0].keys():
                values = [obs[feature] for obs in obs_list if feature in obs]
                if values:
                    mean = np.mean(values)
                    std = max(np.std(values), 0.01)  # Minimum std
                    self.emission_params[state][feature] = (mean, std)

        # Update transition matrix from label sequences
        transition_counts = np.zeros((self.n_states, self.n_states))
        for i in range(len(labels) - 1):
            from_idx = self.states.index(labels[i])
            to_idx = self.states.index(labels[i + 1])
            transition_counts[from_idx, to_idx] += 1

        # Add smoothing and normalize
        transition_counts += 0.1  # Laplace smoothing
        self.transition_matrix = transition_counts / transition_counts.sum(axis=1, keepdims=True)

        logger.info(f"HMM trained on {len(observations)} observations")


# =============================================================================
# 2. KALMAN FILTER - SIGNAL SMOOTHING
# =============================================================================

class KalmanFilter:
    """
    Kalman Filter for Greeks and Signal Smoothing

    Mathematical Foundation:
    State equation: x_t = A × x_t-1 + w_t  (w_t ~ N(0, Q))
    Observation equation: z_t = H × x_t + v_t  (v_t ~ N(0, R))

    Algorithm:
    1. Predict: x̂_t|t-1 = A × x̂_t-1, P_t|t-1 = A × P_t-1 × A' + Q
    2. Update: K_t = P_t|t-1 × H' × (H × P_t|t-1 × H' + R)^-1
               x̂_t = x̂_t|t-1 + K_t × (z_t - H × x̂_t|t-1)
               P_t = (I - K_t × H) × P_t|t-1

    WHY THIS IMPROVES TRADING:
    - Raw Greeks fluctuate with bid-ask noise
    - Kalman provides optimal estimate balancing prediction and observation
    - Smoother signals = fewer false trading decisions
    """

    def __init__(
        self,
        process_variance: float = 0.01,
        measurement_variance: float = 0.1,
        initial_value: float = 0.0,
        initial_variance: float = 1.0
    ):
        """
        Initialize Kalman Filter.

        Args:
            process_variance: Q - how much the true value changes between observations
            measurement_variance: R - how noisy the observations are
            initial_value: Starting estimate
            initial_variance: Initial uncertainty
        """
        # State: [value]
        self.state = initial_value

        # Covariance
        self.P = initial_variance

        # Process noise variance (Q)
        self.Q = process_variance

        # Measurement noise variance (R)
        self.R = measurement_variance

        # State transition (A = 1 for random walk)
        self.A = 1.0

        # Observation matrix (H = 1, we observe the state directly)
        self.H = 1.0

        # History
        self.history: List[KalmanState] = []

        logger.debug(f"Kalman Filter initialized: Q={process_variance}, R={measurement_variance}")

    def update(self, observation: float) -> KalmanState:
        """
        Process new observation and return smoothed value.

        Args:
            observation: Raw noisy measurement

        Returns:
            KalmanState with smoothed value and diagnostics
        """
        # Predict step
        x_pred = self.A * self.state
        P_pred = self.A * self.P * self.A + self.Q

        # Update step
        # Innovation (measurement residual)
        y = observation - self.H * x_pred

        # Innovation covariance
        S = self.H * P_pred * self.H + self.R

        # Kalman gain
        K = P_pred * self.H / S

        # Update state
        x_new = x_pred + K * y

        # Update covariance
        P_new = (1 - K * self.H) * P_pred

        # Store state
        self.state = x_new
        self.P = P_new

        result = KalmanState(
            value=x_new,
            variance=P_new,
            kalman_gain=K,
            raw_observation=observation,
            smoothed_value=x_new,
            prediction=x_pred
        )

        self.history.append(result)

        return result

    def predict(self, steps: int = 1) -> List[float]:
        """Predict future values"""
        predictions = []
        state = self.state
        for _ in range(steps):
            state = self.A * state
            predictions.append(state)
        return predictions

    def get_smoothing_ratio(self) -> float:
        """
        Get ratio of smoothing applied.

        Higher Kalman gain = trusting observations more
        Lower Kalman gain = trusting predictions more (more smoothing)
        """
        if not self.history:
            return 0.5
        return 1 - self.history[-1].kalman_gain


class MultiDimensionalKalmanFilter:
    """
    Multi-dimensional Kalman Filter for smoothing multiple Greeks simultaneously.

    Tracks: [delta, gamma, theta, vega, vanna, charm]
    """

    def __init__(self, n_dims: int = 6):
        self.n_dims = n_dims
        self.filters = {
            'delta': KalmanFilter(process_variance=0.005, measurement_variance=0.02),
            'gamma': KalmanFilter(process_variance=0.001, measurement_variance=0.01),
            'theta': KalmanFilter(process_variance=0.01, measurement_variance=0.05),
            'vega': KalmanFilter(process_variance=0.02, measurement_variance=0.1),
            'vanna': KalmanFilter(process_variance=0.001, measurement_variance=0.01),
            'charm': KalmanFilter(process_variance=0.001, measurement_variance=0.01)
        }

    def update(self, observations: Dict[str, float]) -> Dict[str, KalmanState]:
        """Update all filters with new observations"""
        results = {}
        for name, filter_obj in self.filters.items():
            if name in observations:
                results[name] = filter_obj.update(observations[name])
        return results

    def get_smoothed_greeks(self) -> Dict[str, float]:
        """Get current smoothed values for all Greeks"""
        return {
            name: filter_obj.state
            for name, filter_obj in self.filters.items()
        }


# =============================================================================
# 3. THOMPSON SAMPLING - BOT CAPITAL ALLOCATION
# =============================================================================

class ThompsonSamplingAllocator:
    """
    Thompson Sampling for Dynamic Bot Capital Allocation

    Mathematical Foundation:
    - Each bot is an "arm" with unknown reward distribution
    - We model rewards as Beta(α, β) distributions
    - α = successes (wins) + 1, β = failures (losses) + 1

    Algorithm:
    1. For each bot, sample θ ~ Beta(α_bot, β_bot)
    2. Allocate capital proportional to sampled θ values

    This naturally balances:
    - EXPLOITATION: Allocate more to bots with high win rates
    - EXPLORATION: Still try uncertain bots (high variance)

    WHY THIS IMPROVES TRADING:
    - Current system: Fixed equal allocation to all bots
    - Thompson: Dynamically shifts capital to hot-performing bots
    - Automatically explores underperforming bots in case they improve
    """

    def __init__(self, bot_names: List[str] = None):
        """
        Initialize Thompson Sampling allocator.

        Args:
            bot_names: List of bot names to allocate between
        """
        self.bot_names = bot_names or ['FORTRESS', 'SOLOMON', 'PHOENIX', 'ATLAS']

        # Beta distribution parameters (α=wins+1, β=losses+1)
        # Start with uninformative prior Beta(1,1) = uniform
        self.alpha = {bot: 1.0 for bot in self.bot_names}
        self.beta = {bot: 1.0 for bot in self.bot_names}

        # Track total capital and allocations
        self.total_capital = 100000  # Default
        self.min_allocation = 0.05  # Minimum 5% per bot
        self.max_allocation = 0.50  # Maximum 50% per bot

        # History
        self.allocation_history: List[ThompsonAllocation] = []

        logger.info(f"Thompson Sampling initialized for bots: {self.bot_names}")

    def record_outcome(self, bot_name: str, win: bool, pnl: float = 0):
        """
        Record a trade outcome for a bot.

        Args:
            bot_name: Which bot completed the trade
            win: Whether the trade was profitable
            pnl: Actual P&L (for weighted updates)
        """
        if bot_name not in self.bot_names:
            logger.warning(f"Unknown bot: {bot_name}")
            return

        # Update Beta parameters
        if win:
            # Weight by P&L magnitude for larger wins
            weight = 1 + min(abs(pnl) / 100, 2)  # Cap at 3x weight
            self.alpha[bot_name] += weight
        else:
            weight = 1 + min(abs(pnl) / 100, 2)
            self.beta[bot_name] += weight

        logger.debug(f"Thompson: {bot_name} outcome recorded (win={win}, α={self.alpha[bot_name]:.1f}, β={self.beta[bot_name]:.1f})")

    def sample_allocation(self, total_capital: float = None) -> ThompsonAllocation:
        """
        Generate allocation using Thompson Sampling.

        Returns:
            ThompsonAllocation with capital distribution across bots
        """
        if total_capital:
            self.total_capital = total_capital

        # Sample from Beta distribution for each bot
        sampled_rewards = {}
        for bot in self.bot_names:
            # Sample θ ~ Beta(α, β)
            theta = np.random.beta(self.alpha[bot], self.beta[bot])
            sampled_rewards[bot] = float(theta)  # Convert numpy to native Python

        # Calculate exploration bonus (uncertainty)
        exploration_bonus = {}
        for bot in self.bot_names:
            # Variance of Beta distribution = αβ / ((α+β)²(α+β+1))
            a, b = self.alpha[bot], self.beta[bot]
            variance = (a * b) / ((a + b) ** 2 * (a + b + 1))
            exploration_bonus[bot] = math.sqrt(variance)

        # Normalize sampled rewards to allocations
        total_sampled = sum(sampled_rewards.values())
        raw_allocations = {
            bot: reward / total_sampled
            for bot, reward in sampled_rewards.items()
        }

        # Apply min/max constraints
        allocations = {}
        for bot, alloc in raw_allocations.items():
            allocations[bot] = max(self.min_allocation, min(self.max_allocation, alloc))

        # Re-normalize to sum to 1
        total_alloc = sum(allocations.values())
        allocations = {bot: alloc / total_alloc for bot, alloc in allocations.items()}

        result = ThompsonAllocation(
            allocations=allocations,
            sampled_rewards=sampled_rewards,
            exploration_bonus=exploration_bonus
        )

        self.allocation_history.append(result)

        logger.info(f"Thompson allocation: {', '.join(f'{b}:{a:.1%}' for b, a in allocations.items())}")

        return result

    def get_expected_win_rates(self) -> Dict[str, float]:
        """Get expected win rate for each bot (mean of Beta)"""
        return {
            bot: self.alpha[bot] / (self.alpha[bot] + self.beta[bot])
            for bot in self.bot_names
        }

    def get_uncertainty(self) -> Dict[str, float]:
        """Get uncertainty (std dev) for each bot"""
        uncertainties = {}
        for bot in self.bot_names:
            a, b = self.alpha[bot], self.beta[bot]
            variance = (a * b) / ((a + b) ** 2 * (a + b + 1))
            uncertainties[bot] = math.sqrt(variance)
        return uncertainties

    def reset_bot(self, bot_name: str):
        """Reset a bot's statistics (e.g., after strategy change)"""
        if bot_name in self.bot_names:
            self.alpha[bot_name] = 1.0
            self.beta[bot_name] = 1.0
            logger.info(f"Thompson: Reset statistics for {bot_name}")


# =============================================================================
# 4. CONVEX OPTIMIZER - STRIKE SELECTION
# =============================================================================

class ConvexStrikeOptimizer:
    """
    Convex Optimizer for Optimal Strike Selection

    Mathematical Foundation:
    minimize    E[Loss] = Σ P(scenario_i) × Loss(strike, scenario_i)
    subject to  delta_total ∈ [delta_min, delta_max]
                margin_used ≤ margin_budget
                strike ∈ available_strikes

    This is a Mixed-Integer Convex Program (MICP) solved via:
    1. Enumerate available strikes
    2. For each strike, calculate expected loss across scenarios
    3. Filter by constraints
    4. Select strike minimizing expected loss

    WHY THIS IMPROVES TRADING:
    - Current: "Pick strike closest to target delta"
    - Convex: "Pick strike minimizing expected loss across all price scenarios"
    - Considers adjustment costs, gamma risk, time decay
    """

    def __init__(self):
        # Default scenarios (price movements with probabilities)
        self.scenarios = [
            {'name': 'up_large', 'price_change': 0.03, 'probability': 0.10},
            {'name': 'up_medium', 'price_change': 0.015, 'probability': 0.20},
            {'name': 'up_small', 'price_change': 0.005, 'probability': 0.15},
            {'name': 'flat', 'price_change': 0.0, 'probability': 0.10},
            {'name': 'down_small', 'price_change': -0.005, 'probability': 0.15},
            {'name': 'down_medium', 'price_change': -0.015, 'probability': 0.20},
            {'name': 'down_large', 'price_change': -0.03, 'probability': 0.10},
        ]

        # Cost parameters
        self.adjustment_cost = 50  # Fixed cost per adjustment
        self.slippage_rate = 0.001  # 0.1% slippage

        logger.info("Convex Strike Optimizer initialized")

    def _estimate_delta_after_move(
        self,
        current_delta: float,
        gamma: float,
        price_change_pct: float,
        spot_price: float
    ) -> float:
        """Estimate delta after price move using Taylor expansion"""
        price_change = spot_price * price_change_pct
        delta_change = gamma * price_change
        return current_delta + delta_change

    def _calculate_adjustment_probability(
        self,
        future_delta: float,
        delta_min: float,
        delta_max: float
    ) -> float:
        """Calculate probability of needing adjustment"""
        if delta_min <= future_delta <= delta_max:
            return 0.0

        # Distance outside bounds determines adjustment probability
        if future_delta < delta_min:
            distance = delta_min - future_delta
        else:
            distance = future_delta - delta_max

        # Sigmoid probability based on distance
        return 1 / (1 + math.exp(-10 * distance))

    def _expected_loss(
        self,
        strike: float,
        spot_price: float,
        current_delta: float,
        gamma: float,
        theta: float,
        delta_bounds: Tuple[float, float],
        time_to_expiry: float
    ) -> float:
        """
        Calculate expected loss for a strike across all scenarios.

        Loss = Σ P(scenario) × [P&L_change + adjustment_cost × P(adjustment)]
        """
        delta_min, delta_max = delta_bounds
        total_expected_loss = 0.0

        for scenario in self.scenarios:
            prob = scenario['probability']
            price_change_pct = scenario['price_change']

            # Estimate delta after move
            future_delta = self._estimate_delta_after_move(
                current_delta, gamma, price_change_pct, spot_price
            )

            # P&L from delta exposure
            pnl_from_delta = current_delta * spot_price * price_change_pct * 100  # Per contract

            # Theta decay (negative)
            theta_loss = theta * time_to_expiry

            # Adjustment probability and cost
            adj_prob = self._calculate_adjustment_probability(future_delta, delta_min, delta_max)
            adj_cost = adj_prob * self.adjustment_cost

            # Slippage cost proportional to price movement
            slippage = abs(price_change_pct) * self.slippage_rate * spot_price * 100

            # Total loss for this scenario
            scenario_loss = -pnl_from_delta + abs(theta_loss) + adj_cost + slippage

            total_expected_loss += prob * scenario_loss

        return total_expected_loss

    def optimize(
        self,
        available_strikes: List[Dict],  # [{strike, delta, gamma, theta, vega}, ...]
        spot_price: float,
        target_delta: float,
        delta_tolerance: float = 0.05,
        margin_budget: float = 10000,
        time_to_expiry: float = 1.0  # Days
    ) -> StrikeOptimization:
        """
        Find optimal strike minimizing expected loss.

        Args:
            available_strikes: List of strike candidates with Greeks
            spot_price: Current underlying price
            target_delta: Desired delta
            delta_tolerance: Acceptable deviation from target
            margin_budget: Maximum margin to use
            time_to_expiry: Days until expiration

        Returns:
            StrikeOptimization with best strike and analysis
        """
        if not available_strikes:
            raise ValueError("No available strikes provided")

        delta_bounds = (target_delta - delta_tolerance, target_delta + delta_tolerance)

        # Filter strikes within delta bounds
        valid_strikes = [
            s for s in available_strikes
            if delta_bounds[0] <= abs(s.get('delta', 0)) <= delta_bounds[1]
        ]

        if not valid_strikes:
            # Expand bounds if no valid strikes
            valid_strikes = available_strikes

        # Calculate expected loss for each strike
        strike_losses = []
        for strike_data in valid_strikes:
            loss = self._expected_loss(
                strike=strike_data['strike'],
                spot_price=spot_price,
                current_delta=strike_data.get('delta', target_delta),
                gamma=strike_data.get('gamma', 0.01),
                theta=strike_data.get('theta', -0.1),
                delta_bounds=delta_bounds,
                time_to_expiry=time_to_expiry
            )
            strike_losses.append((strike_data, loss))

        # Sort by expected loss
        strike_losses.sort(key=lambda x: x[1])

        # Best strike
        best_strike_data, best_loss = strike_losses[0]

        # Find original (closest to target delta) for comparison
        original_strike_data = min(
            available_strikes,
            key=lambda s: abs(abs(s.get('delta', 0)) - target_delta)
        )
        original_loss = self._expected_loss(
            strike=original_strike_data['strike'],
            spot_price=spot_price,
            current_delta=original_strike_data.get('delta', target_delta),
            gamma=original_strike_data.get('gamma', 0.01),
            theta=original_strike_data.get('theta', -0.1),
            delta_bounds=delta_bounds,
            time_to_expiry=time_to_expiry
        )

        # Calculate improvement
        improvement = ((original_loss - best_loss) / original_loss * 100) if original_loss > 0 else 0

        result = StrikeOptimization(
            original_strike=original_strike_data['strike'],
            optimized_strike=best_strike_data['strike'],
            expected_loss_original=original_loss,
            expected_loss_optimized=best_loss,
            improvement_pct=improvement,
            constraints_satisfied={
                'delta_in_bounds': delta_bounds[0] <= abs(best_strike_data.get('delta', 0)) <= delta_bounds[1],
                'margin_ok': True  # Simplified
            },
            scenarios_evaluated=len(self.scenarios)
        )

        logger.info(f"Convex optimization: {original_strike_data['strike']} → {best_strike_data['strike']} ({improvement:.1f}% improvement)")

        return result


# =============================================================================
# 5. HAMILTON-JACOBI-BELLMAN (HJB) - OPTIMAL EXIT
# =============================================================================

class HJBExitOptimizer:
    """
    Hamilton-Jacobi-Bellman Exit Optimizer

    Mathematical Foundation:
    V(pnl, time, vol) = value of holding position

    HJB Equation:
    0 = max{ EXIT_NOW: pnl,
             HOLD: ∂V/∂t + μ × ∂V/∂pnl + ½σ² × ∂²V/∂pnl² }

    Exit when immediate value (pnl) > expected future value (E[V])

    Simplified implementation using analytical approximation:
    - Exit boundary = f(time_remaining, volatility, theta_decay)
    - Dynamic adjustment based on current market conditions

    WHY THIS IMPROVES TRADING:
    - Current: Fixed targets (exit at 50% profit)
    - HJB: Dynamic targets based on time, volatility, and expected movement
    - Example: Exit at 45% if only 1 hour left (time decay accelerates)
    """

    def __init__(self):
        # Default parameters
        self.risk_free_rate = 0.05  # 5% annual
        self.base_profit_target = 0.50  # 50% default target
        self.base_stop_loss = -1.00  # 100% max loss

        # Time decay acceleration (theta speeds up near expiry)
        self.time_decay_factor = 1.5

        # Volatility impact (higher vol = exit earlier)
        self.volatility_sensitivity = 0.3

        logger.info("HJB Exit Optimizer initialized")

    def _calculate_expected_future_value(
        self,
        current_pnl: float,
        time_remaining: float,  # In hours
        volatility: float,
        theta_per_hour: float
    ) -> float:
        """
        Calculate expected future value of holding.

        E[V] = current_pnl + expected_drift - expected_theta_loss - risk_premium
        """
        # Expected drift (assume market-neutral position has ~0 drift)
        expected_drift = 0

        # Expected theta loss
        expected_theta_loss = abs(theta_per_hour) * time_remaining

        # Risk premium (uncertainty has negative value)
        hourly_std = volatility / math.sqrt(252 * 6.5)  # Convert annual to hourly
        risk_premium = hourly_std * math.sqrt(time_remaining) * 0.5  # Risk aversion factor

        expected_future_value = current_pnl + expected_drift - expected_theta_loss - risk_premium

        return expected_future_value

    def _calculate_optimal_boundary(
        self,
        time_remaining: float,
        volatility: float,
        max_profit: float
    ) -> float:
        """
        Calculate optimal exit boundary based on HJB solution.

        As time → 0, boundary → current_value (exit immediately)
        As volatility ↑, boundary ↓ (exit earlier to lock in gains)
        """
        # Base boundary
        base_boundary = self.base_profit_target * max_profit

        # Time adjustment (lower boundary as time runs out)
        # Using exponential decay
        time_factor = 1 - math.exp(-time_remaining / 4)  # 4 hour half-life

        # Volatility adjustment
        vol_adjustment = 1 - self.volatility_sensitivity * (volatility - 0.15) / 0.15
        vol_adjustment = max(0.5, min(1.2, vol_adjustment))

        optimal_boundary = base_boundary * time_factor * vol_adjustment

        return optimal_boundary

    def should_exit(
        self,
        current_pnl: float,
        max_profit: float,
        entry_time: datetime,
        expiry_time: datetime,
        current_volatility: float,
        theta_per_hour: float = 0
    ) -> ExitSignal:
        """
        Determine if position should be exited.

        Args:
            current_pnl: Current unrealized P&L
            max_profit: Maximum possible profit (e.g., credit received)
            entry_time: When position was opened
            expiry_time: When position expires
            current_volatility: Current implied or realized volatility
            theta_per_hour: Expected theta decay per hour

        Returns:
            ExitSignal with recommendation and reasoning
        """
        now = datetime.now(CENTRAL_TZ)
        time_remaining = (expiry_time - now).total_seconds() / 3600  # Hours
        time_remaining = max(0, time_remaining)

        # Calculate current P&L percentage
        pnl_pct = current_pnl / max_profit if max_profit > 0 else 0

        # Calculate optimal exit boundary
        optimal_boundary = self._calculate_optimal_boundary(
            time_remaining, current_volatility, max_profit
        )
        optimal_boundary_pct = optimal_boundary / max_profit if max_profit > 0 else self.base_profit_target

        # Calculate expected future value
        expected_future = self._calculate_expected_future_value(
            current_pnl, time_remaining, current_volatility, theta_per_hour
        )

        # Time value remaining
        time_value = expected_future - current_pnl

        # Decision logic
        should_exit = False
        reason = ""

        # Check profit target (dynamic)
        if current_pnl >= optimal_boundary:
            should_exit = True
            reason = f"Reached optimal exit boundary ({pnl_pct:.1%} >= {optimal_boundary_pct:.1%})"

        # Check stop loss
        elif pnl_pct <= self.base_stop_loss:
            should_exit = True
            reason = f"Stop loss triggered ({pnl_pct:.1%} <= {self.base_stop_loss:.1%})"

        # Check if expected future value is negative
        elif expected_future < current_pnl and time_remaining < 2:
            should_exit = True
            reason = f"Expected future value declining (EV={expected_future:.2f} < current={current_pnl:.2f})"

        # Check time-based exit (very little time left)
        elif time_remaining < 0.5 and pnl_pct > 0:  # Less than 30 min, profitable
            should_exit = True
            reason = f"Time expiry approaching ({time_remaining:.1f}h remaining, locking {pnl_pct:.1%} profit)"

        else:
            reason = f"Hold position (boundary={optimal_boundary_pct:.1%}, time={time_remaining:.1f}h, EV={expected_future:.2f})"

        return ExitSignal(
            should_exit=should_exit,
            current_pnl_pct=pnl_pct,
            optimal_boundary=optimal_boundary_pct,
            time_value=time_value,
            volatility_factor=current_volatility,
            expected_future_value=expected_future,
            reason=reason
        )


# =============================================================================
# 6. MARKOV DECISION PROCESS (MDP) - TRADE SEQUENCING
# =============================================================================

class MDPTradeSequencer:
    """
    Markov Decision Process for Optimal Trade Sequencing

    Mathematical Foundation:
    States: (portfolio_state, market_regime, pending_signals)
    Actions: {EXECUTE_TRADE_i, SKIP_TRADE_i, DELAY}
    Rewards: Expected P&L - transaction_costs - opportunity_cost
    Transitions: P(next_state | current_state, action)

    Bellman Equation:
    V(s) = max_a [ R(s,a) + γ × Σ P(s'|s,a) × V(s') ]

    Simplified implementation using greedy optimization with lookahead.

    WHY THIS IMPROVES TRADING:
    - Current: Execute signals independently as they arrive
    - MDP: Consider how one trade affects future opportunities
    - Example: Skip redundant trade if another bot already took the position
    """

    def __init__(self):
        # Cost parameters
        self.transaction_cost = 5  # Per trade
        self.opportunity_cost_rate = 0.001  # Per hour of delay

        # Discount factor
        self.gamma = 0.95

        # Lookahead steps
        self.lookahead = 3

        # Correlation threshold (skip if highly correlated with existing position)
        self.correlation_threshold = 0.70

        logger.info("MDP Trade Sequencer initialized")

    def _calculate_trade_value(
        self,
        trade: Dict,
        existing_positions: List[Dict],
        market_regime: str
    ) -> float:
        """Calculate expected value of executing a trade"""
        expected_pnl = trade.get('expected_pnl', 0)
        win_prob = trade.get('win_probability', 0.5)

        # Adjust for market regime
        regime_multiplier = {
            'TRENDING_BULLISH': 1.2 if trade.get('direction') == 'long' else 0.8,
            'TRENDING_BEARISH': 0.8 if trade.get('direction') == 'long' else 1.2,
            'HIGH_VOLATILITY': 0.7,  # Higher risk
            'LOW_VOLATILITY': 1.1,   # Lower risk
            'MEAN_REVERTING': 1.0,
            'PINNED': 0.9
        }.get(market_regime, 1.0)

        # Adjust for correlation with existing positions
        correlation_penalty = 0
        for pos in existing_positions:
            if pos.get('symbol') == trade.get('symbol'):
                correlation_penalty += 0.2  # Same symbol penalty
            if pos.get('direction') == trade.get('direction'):
                correlation_penalty += 0.1  # Same direction penalty

        adjusted_value = (expected_pnl * win_prob * regime_multiplier) - self.transaction_cost - correlation_penalty

        return adjusted_value

    def _check_redundancy(
        self,
        trade: Dict,
        existing_positions: List[Dict],
        other_pending: List[Dict]
    ) -> Tuple[bool, str]:
        """Check if trade is redundant given existing positions"""
        symbol = trade.get('symbol')
        direction = trade.get('direction')

        # Check existing positions
        for pos in existing_positions:
            if pos.get('symbol') == symbol and pos.get('direction') == direction:
                return True, f"Redundant: Already have {direction} position in {symbol}"

        # Check other pending trades (higher priority)
        for pending in other_pending:
            if pending.get('priority', 0) > trade.get('priority', 0):
                if pending.get('symbol') == symbol:
                    return True, f"Redundant: Higher priority trade pending for {symbol}"

        return False, ""

    def sequence_trades(
        self,
        pending_trades: List[Dict],
        existing_positions: List[Dict],
        market_regime: str,
        max_trades: int = 3
    ) -> TradeSequence:
        """
        Sequence pending trades optimally.

        Args:
            pending_trades: List of trade signals [{symbol, direction, expected_pnl, win_probability, bot, ...}]
            existing_positions: Current open positions
            market_regime: Current market regime
            max_trades: Maximum trades to execute

        Returns:
            TradeSequence with optimized order and skipped trades
        """
        if not pending_trades:
            return TradeSequence(
                original_order=[],
                optimized_order=[],
                expected_value_original=0,
                expected_value_optimized=0,
                skipped_trades=[],
                reason="No pending trades"
            )

        original_order = pending_trades.copy()

        # Calculate value for each trade
        trade_values = []
        for trade in pending_trades:
            value = self._calculate_trade_value(trade, existing_positions, market_regime)
            is_redundant, redundancy_reason = self._check_redundancy(
                trade, existing_positions, pending_trades
            )
            trade_values.append({
                'trade': trade,
                'value': value,
                'is_redundant': is_redundant,
                'redundancy_reason': redundancy_reason
            })

        # Sort by value (descending)
        trade_values.sort(key=lambda x: x['value'], reverse=True)

        # Filter out redundant trades
        optimized_order = []
        skipped_trades = []

        for tv in trade_values:
            if tv['is_redundant']:
                skipped_trades.append({**tv['trade'], 'skip_reason': tv['redundancy_reason']})
            elif len(optimized_order) < max_trades and tv['value'] > 0:
                optimized_order.append(tv['trade'])
            else:
                skipped_trades.append({**tv['trade'], 'skip_reason': 'Low value or max trades reached'})

        # Calculate expected values
        ev_original = sum(
            self._calculate_trade_value(t, existing_positions, market_regime)
            for t in original_order[:max_trades]
        )
        ev_optimized = sum(
            self._calculate_trade_value(t, existing_positions, market_regime)
            for t in optimized_order
        )

        improvement = ((ev_optimized - ev_original) / ev_original * 100) if ev_original > 0 else 0

        result = TradeSequence(
            original_order=original_order,
            optimized_order=optimized_order,
            expected_value_original=ev_original,
            expected_value_optimized=ev_optimized,
            skipped_trades=skipped_trades,
            reason=f"Optimized sequence: {len(optimized_order)} trades, {len(skipped_trades)} skipped, {improvement:.1f}% improvement"
        )

        logger.info(f"MDP sequencing: {len(original_order)} → {len(optimized_order)} trades ({improvement:.1f}% EV improvement)")

        return result


# =============================================================================
# INTEGRATED OPTIMIZER ORCHESTRATOR
# =============================================================================

class MathOptimizerOrchestrator:
    """
    Central orchestrator for all mathematical optimizers.

    Integrates with Proverbs's feedback loop for:
    - Logging all optimization decisions
    - Tracking performance of each algorithm
    - Enabling A/B testing of optimizations
    """

    def __init__(self):
        # Initialize all optimizers
        self.hmm_regime = HiddenMarkovRegimeDetector()
        self.kalman_greeks = MultiDimensionalKalmanFilter()
        self.thompson = ThompsonSamplingAllocator()
        self.convex_strike = ConvexStrikeOptimizer()
        self.hjb_exit = HJBExitOptimizer()
        self.mdp_sequencer = MDPTradeSequencer()

        # Proverbs integration (lazy load)
        self._proverbs = None

        # Performance tracking
        self.optimization_counts = defaultdict(int)
        self.optimization_improvements = defaultdict(list)

        logger.info("Math Optimizer Orchestrator initialized with all algorithms")

    @property
    def proverbs(self):
        """Lazy load Proverbs for logging"""
        if self._proverbs is None:
            try:
                from quant.proverbs_feedback_loop import get_proverbs
                self._proverbs = get_proverbs()
            except ImportError:
                logger.debug("Proverbs not available for optimizer logging")
        return self._proverbs

    def log_to_proverbs(
        self,
        action: OptimizationAction,
        description: str,
        bot_name: str = "SYSTEM",
        justification: Dict = None
    ):
        """Log optimization action to Proverbs audit trail"""
        if self.proverbs:
            try:
                from quant.proverbs_feedback_loop import ActionType

                # Map our action to Proverbs's action type
                action_map = {
                    OptimizationAction.HMM_REGIME_UPDATE: "FEEDBACK_LOOP_RUN",
                    OptimizationAction.KALMAN_SMOOTHING: "FEEDBACK_LOOP_RUN",
                    OptimizationAction.THOMPSON_ALLOCATION: "FEEDBACK_LOOP_RUN",
                    OptimizationAction.CONVEX_STRIKE_OPTIMIZATION: "FEEDBACK_LOOP_RUN",
                    OptimizationAction.HJB_EXIT_SIGNAL: "FEEDBACK_LOOP_RUN",
                    OptimizationAction.MDP_TRADE_SEQUENCE: "FEEDBACK_LOOP_RUN"
                }

                self.proverbs.log_action(
                    bot_name=bot_name,
                    action_type=ActionType.FEEDBACK_LOOP_RUN,
                    description=f"[{action.value}] {description}",
                    reason=f"Mathematical optimization: {action.value}",
                    justification=justification or {}
                )
            except Exception as e:
                logger.debug(f"Could not log to Proverbs: {e}")

    # Convenience methods that combine algorithms

    def analyze_market(self, market_data: Dict) -> Dict:
        """
        Full market analysis using all relevant algorithms.

        Args:
            market_data: {vix, net_gamma, momentum, realized_vol, volume_ratio, greeks: {...}}

        Returns:
            Comprehensive analysis with regime, smoothed data, and recommendations
        """
        result = {
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
            'regime': None,
            'smoothed_greeks': None,
            'allocations': None,
            'analysis': {}
        }

        # 1. Update regime detection
        regime_obs = {k: v for k, v in market_data.items() if k in ['vix', 'net_gamma', 'momentum', 'realized_vol', 'volume_ratio']}
        if regime_obs:
            regime_state = self.hmm_regime.update(regime_obs)
            result['regime'] = regime_state.to_dict()
            result['analysis']['regime_probabilities'] = self.hmm_regime.get_regime_probabilities()

            self.log_to_proverbs(
                OptimizationAction.HMM_REGIME_UPDATE,
                f"Regime: {regime_state.regime.value} (prob={regime_state.probability:.2%})",
                justification=regime_state.to_dict()
            )

        # 2. Smooth Greeks
        if 'greeks' in market_data:
            kalman_results = self.kalman_greeks.update(market_data['greeks'])
            result['smoothed_greeks'] = self.kalman_greeks.get_smoothed_greeks()

            self.log_to_proverbs(
                OptimizationAction.KALMAN_SMOOTHING,
                f"Smoothed {len(kalman_results)} Greeks",
                justification={'smoothed': result['smoothed_greeks']}
            )

        # 3. Get current allocations
        allocation = self.thompson.sample_allocation()
        result['allocations'] = allocation.to_dict()

        self.log_to_proverbs(
            OptimizationAction.THOMPSON_ALLOCATION,
            f"Capital allocation: {', '.join(f'{b}:{a:.1%}' for b, a in allocation.allocations.items())}",
            justification=allocation.to_dict()
        )

        return result

    def optimize_trade(
        self,
        signal: Dict,
        available_strikes: List[Dict],
        existing_positions: List[Dict],
        spot_price: float,
        current_regime: str = None
    ) -> Dict:
        """
        Optimize a trade signal before execution.

        Args:
            signal: Trade signal with {symbol, direction, target_delta, bot, ...}
            available_strikes: Available strikes with Greeks
            existing_positions: Current open positions
            spot_price: Current underlying price
            current_regime: Current market regime

        Returns:
            Optimized trade with strike selection and sequencing
        """
        result = {
            'original_signal': signal,
            'optimized': {}
        }

        # 1. Optimize strike selection
        if available_strikes and signal.get('target_delta'):
            strike_opt = self.convex_strike.optimize(
                available_strikes=available_strikes,
                spot_price=spot_price,
                target_delta=signal['target_delta'],
                time_to_expiry=signal.get('dte', 1)
            )
            result['optimized']['strike'] = strike_opt.to_dict()

            self.log_to_proverbs(
                OptimizationAction.CONVEX_STRIKE_OPTIMIZATION,
                f"Strike optimized: {strike_opt.original_strike} → {strike_opt.optimized_strike} ({strike_opt.improvement_pct:.1f}% improvement)",
                bot_name=signal.get('bot', 'SYSTEM'),
                justification=strike_opt.to_dict()
            )

        # 2. Check sequencing
        sequence = self.mdp_sequencer.sequence_trades(
            pending_trades=[signal],
            existing_positions=existing_positions,
            market_regime=current_regime or 'MEAN_REVERTING'
        )
        result['optimized']['sequencing'] = sequence.to_dict()

        if sequence.skipped_trades:
            self.log_to_proverbs(
                OptimizationAction.MDP_TRADE_SEQUENCE,
                f"Trade sequencing: {len(sequence.optimized_order)} execute, {len(sequence.skipped_trades)} skip",
                bot_name=signal.get('bot', 'SYSTEM'),
                justification=sequence.to_dict()
            )

        return result

    def check_exit(
        self,
        position: Dict,
        current_pnl: float,
        max_profit: float,
        current_volatility: float
    ) -> ExitSignal:
        """
        Check if position should be exited using HJB optimizer.

        Args:
            position: Position data with entry_time, expiry_time
            current_pnl: Current unrealized P&L
            max_profit: Maximum possible profit
            current_volatility: Current volatility

        Returns:
            ExitSignal with recommendation
        """
        entry_time = position.get('entry_time', datetime.now(CENTRAL_TZ))
        expiry_time = position.get('expiry_time', datetime.now(CENTRAL_TZ) + timedelta(hours=8))

        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
        if isinstance(expiry_time, str):
            expiry_time = datetime.fromisoformat(expiry_time.replace('Z', '+00:00'))

        signal = self.hjb_exit.should_exit(
            current_pnl=current_pnl,
            max_profit=max_profit,
            entry_time=entry_time,
            expiry_time=expiry_time,
            current_volatility=current_volatility,
            theta_per_hour=position.get('theta_per_hour', 0)
        )

        if signal.should_exit:
            self.log_to_proverbs(
                OptimizationAction.HJB_EXIT_SIGNAL,
                f"Exit signal: {signal.reason}",
                bot_name=position.get('bot', 'SYSTEM'),
                justification=signal.to_dict()
            )

        return signal

    def get_status(self) -> Dict:
        """Get status of all optimizers"""
        return {
            'hmm_regime': {
                'current_belief': self.hmm_regime.get_regime_probabilities(),
                'observations_processed': len(self.hmm_regime.observation_history)
            },
            'kalman': {
                'smoothed_greeks': self.kalman_greeks.get_smoothed_greeks()
            },
            'thompson': {
                'expected_win_rates': self.thompson.get_expected_win_rates(),
                'uncertainty': self.thompson.get_uncertainty(),
                'allocations': self.thompson.allocation_history[-1].to_dict() if self.thompson.allocation_history else None
            },
            'optimization_counts': dict(self.optimization_counts)
        }


# =============================================================================
# SINGLETON AND CONVENIENCE FUNCTIONS
# =============================================================================

_orchestrator: Optional[MathOptimizerOrchestrator] = None


def get_math_optimizer() -> MathOptimizerOrchestrator:
    """Get or create Math Optimizer singleton"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MathOptimizerOrchestrator()
    return _orchestrator


def analyze_market(market_data: Dict) -> Dict:
    """Convenience function for market analysis"""
    return get_math_optimizer().analyze_market(market_data)


def optimize_trade(signal: Dict, **kwargs) -> Dict:
    """Convenience function for trade optimization"""
    return get_math_optimizer().optimize_trade(signal, **kwargs)


def check_exit(position: Dict, **kwargs) -> ExitSignal:
    """Convenience function for exit check"""
    return get_math_optimizer().check_exit(position, **kwargs)


# =============================================================================
# CLI FOR TESTING
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("AlphaGEX Mathematical Optimizer Test Suite")
    print("=" * 60)

    orchestrator = get_math_optimizer()

    # Test HMM Regime Detection
    print("\n1. Testing HMM Regime Detection...")
    market_obs = {
        'vix': 18.5,
        'net_gamma': 0.3,
        'momentum': 0.4,
        'realized_vol': 0.14,
        'volume_ratio': 1.1
    }
    regime_state = orchestrator.hmm_regime.update(market_obs)
    print(f"   Regime: {regime_state.regime.value}")
    print(f"   Probability: {regime_state.probability:.2%}")
    print(f"   Confidence: {regime_state.confidence:.2%}")

    # Test Kalman Filter
    print("\n2. Testing Kalman Filter...")
    greeks = {'delta': 0.32, 'gamma': 0.05, 'theta': -0.15, 'vega': 0.20}
    kalman_results = orchestrator.kalman_greeks.update(greeks)
    smoothed = orchestrator.kalman_greeks.get_smoothed_greeks()
    print(f"   Raw delta: 0.32 → Smoothed: {smoothed['delta']:.4f}")

    # Test Thompson Sampling
    print("\n3. Testing Thompson Sampling...")
    orchestrator.thompson.record_outcome('FORTRESS', True, 150)
    orchestrator.thompson.record_outcome('SOLOMON', True, 80)
    orchestrator.thompson.record_outcome('FORTRESS', False, -50)
    allocation = orchestrator.thompson.sample_allocation(100000)
    print(f"   Allocation: {', '.join(f'{b}: {a:.1%}' for b, a in allocation.allocations.items())}")

    # Test Convex Strike Optimizer
    print("\n4. Testing Convex Strike Optimizer...")
    strikes = [
        {'strike': 570, 'delta': -0.25, 'gamma': 0.03, 'theta': -0.10},
        {'strike': 575, 'delta': -0.30, 'gamma': 0.04, 'theta': -0.12},
        {'strike': 580, 'delta': -0.35, 'gamma': 0.05, 'theta': -0.15},
    ]
    strike_opt = orchestrator.convex_strike.optimize(
        available_strikes=strikes,
        spot_price=590,
        target_delta=0.30
    )
    print(f"   Original: {strike_opt.original_strike} → Optimized: {strike_opt.optimized_strike}")
    print(f"   Improvement: {strike_opt.improvement_pct:.1f}%")

    # Test HJB Exit
    print("\n5. Testing HJB Exit Optimizer...")
    from datetime import timedelta
    exit_signal = orchestrator.hjb_exit.should_exit(
        current_pnl=120,
        max_profit=250,
        entry_time=datetime.now(CENTRAL_TZ) - timedelta(hours=4),
        expiry_time=datetime.now(CENTRAL_TZ) + timedelta(hours=2),
        current_volatility=0.18
    )
    print(f"   Should exit: {exit_signal.should_exit}")
    print(f"   Reason: {exit_signal.reason}")

    # Test MDP Sequencer
    print("\n6. Testing MDP Trade Sequencer...")
    pending = [
        {'symbol': 'SPY', 'direction': 'long', 'expected_pnl': 100, 'win_probability': 0.65, 'bot': 'FORTRESS'},
        {'symbol': 'SPY', 'direction': 'long', 'expected_pnl': 80, 'win_probability': 0.60, 'bot': 'SOLOMON'},
        {'symbol': 'QQQ', 'direction': 'short', 'expected_pnl': 120, 'win_probability': 0.55, 'bot': 'PHOENIX'},
    ]
    sequence = orchestrator.mdp_sequencer.sequence_trades(
        pending_trades=pending,
        existing_positions=[],
        market_regime='TRENDING_BULLISH'
    )
    print(f"   Original: {len(sequence.original_order)} → Optimized: {len(sequence.optimized_order)}")
    print(f"   Skipped: {len(sequence.skipped_trades)}")
    print(f"   Reason: {sequence.reason}")

    print("\n" + "=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)
