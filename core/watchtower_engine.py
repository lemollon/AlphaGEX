"""
WATCHTOWER Engine - 0DTE Gamma Live Analysis
=========================================

Named after Watchtower Panoptes, the "all-seeing" giant with 100 eyes from Greek mythology.
Real-time visualization of net gamma by strike with ML-powered probability predictions.

Features:
- Net gamma calculation per strike
- Gamma flip detection (positive ↔ negative)
- Hybrid probability calculation (ML + gamma-weighted distance)
- Rate of change indicators (1-min and 5-min)
- Magnet, pin, and danger zone detection

Author: AlphaGEX Team
"""

import os
import sys
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import math
import json

import numpy as np
import pandas as pd

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


class GammaRegime(Enum):
    """Overall gamma regime classification"""
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class FlipDirection(Enum):
    """Direction of gamma flip"""
    POS_TO_NEG = "POS_TO_NEG"
    NEG_TO_POS = "NEG_TO_POS"


class DangerType(Enum):
    """Type of danger zone"""
    BUILDING = "BUILDING"      # Gamma accumulating rapidly (>+25% in 5 min)
    COLLAPSING = "COLLAPSING"  # Gamma evaporating (<-25% in 5 min)
    SPIKE = "SPIKE"            # Sudden gamma surge (>+15% in 1 min)


class AlertType(Enum):
    """Types of alerts"""
    GAMMA_FLIP = "GAMMA_FLIP"
    REGIME_CHANGE = "REGIME_CHANGE"
    GAMMA_SPIKE = "GAMMA_SPIKE"
    MAGNET_SHIFT = "MAGNET_SHIFT"
    PIN_ZONE_ENTRY = "PIN_ZONE_ENTRY"
    DANGER_ZONE = "DANGER_ZONE"
    GAMMA_COLLAPSE = "GAMMA_COLLAPSE"
    PATTERN_MATCH = "PATTERN_MATCH"


class AlertPriority(Enum):
    """Alert priority levels"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class StrikeData:
    """Data for a single strike"""
    strike: float
    net_gamma: float
    call_gamma: float = 0.0
    put_gamma: float = 0.0
    probability: float = 0.0
    gamma_change_pct: float = 0.0
    roc_1min: float = 0.0
    roc_5min: float = 0.0
    roc_30min: float = 0.0
    roc_1hr: float = 0.0
    roc_4hr: float = 0.0
    roc_trading_day: float = 0.0  # ROC since market open (8:30 AM CT)
    volume: int = 0
    call_volume: int = 0  # Separate call volume for GEX flow analysis
    put_volume: int = 0   # Separate put volume for GEX flow analysis
    # Bid/Ask size for order flow analysis (from Tradier API)
    call_bid_size: int = 0   # Contracts waiting at call bid (buyers)
    call_ask_size: int = 0   # Contracts waiting at call ask (sellers)
    put_bid_size: int = 0    # Contracts waiting at put bid (buyers)
    put_ask_size: int = 0    # Contracts waiting at put ask (sellers)
    call_oi: int = 0     # Call open interest for GEX calculation
    put_oi: int = 0      # Put open interest for GEX calculation
    call_iv: float = 0.0
    put_iv: float = 0.0
    is_magnet: bool = False
    magnet_rank: Optional[int] = None
    is_pin: bool = False
    is_danger: bool = False
    danger_type: Optional[str] = None
    gamma_flipped: bool = False
    flip_direction: Optional[str] = None
    previous_net_gamma: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class GammaSnapshot:
    """Complete gamma snapshot at a point in time"""
    symbol: str
    expiration_date: str
    snapshot_time: datetime
    spot_price: float
    expected_move: float
    vix: float
    total_net_gamma: float
    gamma_regime: str
    previous_regime: Optional[str]
    regime_flipped: bool
    market_status: str
    strikes: List[StrikeData]
    magnets: List[Dict]
    likely_pin: float
    pin_probability: float
    danger_zones: List[Dict]
    gamma_flips: List[Dict]
    pinning_status: Dict = field(default_factory=lambda: {'is_pinning': False})
    order_flow: Dict = field(default_factory=dict)  # Order flow analysis (combined_signal, flow_confidence, etc.)

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'expiration_date': self.expiration_date,
            'snapshot_time': self.snapshot_time.isoformat(),
            'spot_price': self.spot_price,
            'expected_move': self.expected_move,
            'vix': self.vix,
            'total_net_gamma': self.total_net_gamma,
            'gamma_regime': self.gamma_regime,
            'previous_regime': self.previous_regime,
            'regime_flipped': self.regime_flipped,
            'market_status': self.market_status,
            'strikes': [s.to_dict() for s in self.strikes],
            'magnets': self.magnets,
            'likely_pin': self.likely_pin,
            'pin_probability': self.pin_probability,
            'danger_zones': self.danger_zones,
            'gamma_flips': self.gamma_flips,
            'pinning_status': self.pinning_status,
            'order_flow': self.order_flow
        }


@dataclass
class Alert:
    """Alert generated by the system"""
    alert_type: str
    strike: Optional[float]
    message: str
    priority: str
    spot_price: float
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    triggered_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            'alert_type': self.alert_type,
            'strike': self.strike,
            'message': self.message,
            'priority': self.priority,
            'spot_price': self.spot_price,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'triggered_at': self.triggered_at.isoformat()
        }


class WatchtowerEngine:
    """
    Core engine for WATCHTOWER 0DTE Gamma Live analysis.

    Responsibilities:
    - Fetch and process gamma data from Tradier
    - Calculate net gamma per strike
    - Detect gamma flips (positive ↔ negative)
    - Calculate probabilities using hybrid approach
    - Identify magnets, pins, and danger zones
    - Generate alerts for significant events
    """

    # Thresholds - keep high to only show REAL spikes
    ROC_1MIN_SPIKE_THRESHOLD = 15.0  # % for SPIKE danger type
    ROC_5MIN_BUILDING_THRESHOLD = 25.0  # % for BUILDING danger type
    ROC_5MIN_COLLAPSING_THRESHOLD = -25.0  # % for COLLAPSING danger type
    PIN_ZONE_PROXIMITY_PCT = 0.5  # % distance from likely pin
    GAMMA_SPIKE_THRESHOLD = 50.0  # % increase in 5 min for alert
    GAMMA_COLLAPSE_THRESHOLD = -20.0  # % decrease in 10 min for alert

    def __init__(self):
        """Initialize the WATCHTOWER engine"""
        self.previous_snapshot: Optional[GammaSnapshot] = None
        self.history: Dict[float, List[Tuple[datetime, float]]] = {}  # strike -> [(time, gamma)]
        self.previous_magnets: List[float] = []
        self.alerts: List[Alert] = []

        # Import ML models lazily to avoid circular imports
        self._ml_models = None

        # Expected move smoothing state
        # EMA smoothing reduces chart structure volatility by ~70-80%
        self._previous_expected_move: Optional[float] = None
        self._ema_alpha: float = 0.3  # 30% new value, 70% previous (tunable)

        # Gamma smoothing state - reduces noise from Tradier Greeks recalculations
        # Rolling window stores recent gamma values per strike for median smoothing
        self._gamma_window: Dict[float, List[float]] = {}  # strike -> [recent gamma values]
        self._gamma_window_size: int = 5  # Number of readings to average
        self._gamma_smoothing_enabled: bool = True
        self._previous_spot_price: Optional[float] = None
        self._max_gamma_change_pct: float = 50.0  # Max % change allowed without price move

        # Market open baseline - stores first 5 minutes of readings for stable baseline
        self._market_open_baselines: Dict[float, List[float]] = {}  # strike -> [opening values]
        self._baseline_locked: bool = False  # Lock baseline after 5 minutes

        # Locked GEX levels at market open (like SpotGamma does for 0DTE)
        # OI doesn't change intraday, so GEX rankings should be stable
        self._locked_gex_rankings: Dict[float, int] = {}  # strike -> rank at open
        self._locked_gex_values: Dict[float, float] = {}  # strike -> GEX value at open
        self._gex_levels_locked: bool = False
        self._major_strikes_at_open: List[float] = []  # Top 5 strikes by GEX at open

    def reset_expected_move_smoothing(self):
        """
        Reset the expected move smoothing state.

        Call this at the start of a new trading day or when you want
        the expected move to immediately reflect current option prices
        without smoothing from previous values.
        """
        self._previous_expected_move = None
        logger.debug("Expected move smoothing state reset")

    def set_ema_alpha(self, alpha: float):
        """
        Set the EMA smoothing factor for expected move.

        Args:
            alpha: Value between 0 and 1. Higher = more responsive to changes,
                   lower = more stable/smooth. Default is 0.3.
                   - 0.1 = very smooth (90% previous, 10% new)
                   - 0.3 = balanced (70% previous, 30% new) [default]
                   - 0.5 = responsive (50% previous, 50% new)
        """
        if not 0 < alpha <= 1:
            raise ValueError("Alpha must be between 0 (exclusive) and 1 (inclusive)")
        self._ema_alpha = alpha
        logger.info(f"Expected move EMA alpha set to {alpha}")

    def set_gamma_smoothing(self, enabled: bool = True, window_size: int = 5,
                            max_change_pct: float = 50.0):
        """
        Configure gamma smoothing to reduce noise from Tradier Greeks recalculations.

        Args:
            enabled: Whether to enable gamma smoothing (default True)
            window_size: Number of recent readings to use for median (default 5)
            max_change_pct: Maximum % change allowed in single reading without price move (default 50%)
        """
        self._gamma_smoothing_enabled = enabled
        self._gamma_window_size = window_size
        self._max_gamma_change_pct = max_change_pct
        logger.info(f"Gamma smoothing: enabled={enabled}, window={window_size}, max_change={max_change_pct}%")

    def reset_gamma_smoothing(self):
        """
        Reset gamma smoothing state at start of new trading day.
        Call this when market opens to clear stale data.
        """
        self._gamma_window = {}
        self._previous_spot_price = None
        self._market_open_baselines = {}
        self._baseline_locked = False
        # Reset locked GEX levels for new trading day
        self._locked_gex_rankings = {}
        self._locked_gex_values = {}
        self._gex_levels_locked = False
        self._major_strikes_at_open = []
        # Reset order flow pressure smoothing history
        self._pressure_history = []
        logger.debug("Gamma smoothing state reset for new trading day (including pressure history)")

    def lock_gex_levels_at_open(self, strikes_data: List, spot_price: float):
        """
        Lock GEX levels at market open (like SpotGamma does for 0DTE).

        Since OI doesn't change intraday, the relative GEX rankings should be stable.
        This prevents noisy gamma recalculations from changing which strikes are "major".

        Args:
            strikes_data: List of StrikeData objects with net_gamma populated
            spot_price: Current spot price
        """
        if self._gex_levels_locked:
            return  # Already locked

        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")
        now = datetime.now(CENTRAL_TZ)
        market_open = now.replace(hour=8, minute=30, second=0, microsecond=0)

        # Only lock after market open and within first 10 minutes
        if now < market_open:
            return
        if (now - market_open).total_seconds() > 600:  # 10 minute window to lock
            if not self._gex_levels_locked and self._locked_gex_values:
                self._gex_levels_locked = True
                logger.info(f"GEX levels locked with {len(self._locked_gex_values)} strikes")
            return

        # Calculate GEX for each strike and store
        for strike_data in strikes_data:
            strike = strike_data.strike
            gex = abs(strike_data.net_gamma)  # Already OI-weighted from calculate_net_gamma
            self._locked_gex_values[strike] = gex

        # Rank strikes by GEX (highest = rank 1)
        sorted_strikes = sorted(self._locked_gex_values.items(), key=lambda x: abs(x[1]), reverse=True)
        for rank, (strike, _) in enumerate(sorted_strikes, 1):
            self._locked_gex_rankings[strike] = rank

        # Store top 5 as "major strikes" - these should remain major all day
        self._major_strikes_at_open = [strike for strike, _ in sorted_strikes[:5]]
        logger.debug(f"GEX levels captured: top 5 = {self._major_strikes_at_open}")

    def get_locked_gex_rank(self, strike: float) -> Optional[int]:
        """Get the locked GEX rank for a strike (set at market open)."""
        return self._locked_gex_rankings.get(strike)

    def is_major_strike(self, strike: float) -> bool:
        """Check if strike was in top 5 GEX at market open."""
        return strike in self._major_strikes_at_open

    def get_gex_rank_change(self, strike: float, current_rank: int) -> int:
        """
        Get how much a strike's GEX rank has changed since market open.

        Returns:
            Positive = improved (moved up in ranking)
            Negative = declined (moved down in ranking)
            0 = no change or no baseline
        """
        locked_rank = self._locked_gex_rankings.get(strike)
        if locked_rank is None:
            return 0
        # Lower rank number = higher importance, so improvement = negative change
        return locked_rank - current_rank

    def _smooth_gamma_value(self, strike: float, raw_gamma: float, spot_price: float) -> float:
        """
        Apply smoothing to a raw gamma value to reduce noise.

        Uses median of recent readings (robust to outliers) and validates
        that large changes only occur when price has moved significantly.

        Args:
            strike: Strike price
            raw_gamma: Raw gamma value from Tradier
            spot_price: Current spot price

        Returns:
            Smoothed gamma value
        """
        if not self._gamma_smoothing_enabled:
            return raw_gamma

        # Initialize window for this strike if needed
        if strike not in self._gamma_window:
            self._gamma_window[strike] = []

        window = self._gamma_window[strike]

        # Check for suspicious large change without price movement
        if window and self._previous_spot_price is not None:
            last_gamma = window[-1]
            if last_gamma != 0:
                change_pct = abs((raw_gamma - last_gamma) / abs(last_gamma)) * 100
                price_change_pct = abs((spot_price - self._previous_spot_price) / self._previous_spot_price) * 100

                # If gamma changed dramatically but price didn't, dampen the change
                if change_pct > self._max_gamma_change_pct and price_change_pct < 0.1:
                    # Blend: 70% previous, 30% new (dampen noise)
                    raw_gamma = 0.7 * last_gamma + 0.3 * raw_gamma
                    logger.debug(f"Dampened gamma spike at strike {strike}: "
                                f"{change_pct:.1f}% change with {price_change_pct:.2f}% price move")

        # Add to rolling window
        window.append(raw_gamma)

        # Keep window at configured size
        if len(window) > self._gamma_window_size:
            window.pop(0)

        # Use median for robustness to outliers
        if len(window) >= 3:
            smoothed = float(np.median(window))
        else:
            # Not enough data yet, use simple average
            smoothed = sum(window) / len(window)

        return smoothed

    def _update_market_open_baseline(self, strike: float, gamma: float):
        """
        Update market open baseline for a strike.

        Collects readings for first 5 minutes after market open to establish
        a stable baseline (average of multiple readings, not just first snapshot).
        """
        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")
        now = datetime.now(CENTRAL_TZ)
        market_open = now.replace(hour=8, minute=30, second=0, microsecond=0)

        # Only collect baseline in first 5 minutes after open
        if now < market_open or (now - market_open).total_seconds() > 300:
            if not self._baseline_locked and self._market_open_baselines:
                self._baseline_locked = True
                logger.info("Market open baselines locked after 5 minutes")
            return

        # Add to baseline collection
        if strike not in self._market_open_baselines:
            self._market_open_baselines[strike] = []

        self._market_open_baselines[strike].append(gamma)

    def get_market_open_baseline(self, strike: float) -> Optional[float]:
        """
        Get the stable market open baseline for a strike.

        Returns median of first 5 minutes of readings for stability.
        """
        if strike not in self._market_open_baselines:
            return None

        baselines = self._market_open_baselines[strike]
        if not baselines:
            return None

        # Use median for robustness
        return float(np.median(baselines))

    def _get_ml_models(self):
        """Lazy load ML probability models"""
        if self._ml_models is None:
            try:
                from quant.gex_probability_models import GEXProbabilityModels
                self._ml_models = GEXProbabilityModels()
                logger.info("Loaded GEX probability models for WATCHTOWER")
            except Exception as e:
                logger.warning(f"Could not load ML models: {e}")
                self._ml_models = False
        return self._ml_models if self._ml_models else None

    def get_market_status(self) -> str:
        """Determine current market status based on time, including holidays"""
        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")
        now = datetime.now(CENTRAL_TZ)
        hour = now.hour
        minute = now.minute

        # Weekend check
        if now.weekday() >= 5:
            return 'closed'

        # Holiday check - use MarketCalendar holidays
        from trading.market_calendar import MARKET_HOLIDAYS_2024_2025
        date_str = now.strftime('%Y-%m-%d')
        if date_str in MARKET_HOLIDAYS_2024_2025:
            return 'holiday'

        time_minutes = hour * 60 + minute

        # Pre-market: 4:00am - 8:30am CT (5:00am - 9:30am ET)
        if 4 * 60 <= time_minutes < 8 * 60 + 30:
            return 'pre_market'
        # Market hours: 8:30am - 3:00pm CT (9:30am - 4:00pm ET)
        elif 8 * 60 + 30 <= time_minutes < 15 * 60:
            return 'open'
        # After hours: 3:00pm - 7:00pm CT (4:00pm - 8:00pm ET)
        elif 15 * 60 <= time_minutes < 19 * 60:
            return 'after_hours'
        else:
            return 'closed'

    def get_0dte_expiration(self, target_day: str = 'today') -> str:
        """
        Get the 0DTE expiration date.
        SPY has 0DTE every day (Mon-Fri).

        Args:
            target_day: 'today', 'mon', 'tue', 'wed', 'thu', 'fri'

        Returns:
            Expiration date string in YYYY-MM-DD format
        """
        today = date.today()

        if target_day == 'today':
            # If weekend, return next Monday
            if today.weekday() >= 5:
                days_until_monday = 7 - today.weekday()
                return (today + timedelta(days=days_until_monday)).strftime('%Y-%m-%d')
            return today.strftime('%Y-%m-%d')

        # Map day names to weekday numbers
        day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4}
        target_weekday = day_map.get(target_day.lower(), today.weekday())

        # Calculate days until target
        days_ahead = target_weekday - today.weekday()
        if days_ahead < 0:
            days_ahead += 7

        target_date = today + timedelta(days=days_ahead)
        return target_date.strftime('%Y-%m-%d')

    def calculate_expected_move(self, atm_call_price: float, atm_put_price: float,
                                  apply_smoothing: bool = True) -> float:
        """
        Calculate expected move from ATM straddle price with optional EMA smoothing.

        Smoothing reduces chart structure volatility by dampening rapid changes
        in expected move that cause strike filtering bounds to shift frequently.

        Args:
            atm_call_price: Price of ATM call
            atm_put_price: Price of ATM put
            apply_smoothing: Whether to apply EMA smoothing (default True)

        Returns:
            Expected move in dollars (smoothed if enabled)
        """
        raw_em = atm_call_price + atm_put_price

        if not apply_smoothing or raw_em <= 0:
            return raw_em

        # Apply exponential moving average smoothing
        if self._previous_expected_move is None:
            # First calculation - use raw value
            smoothed_em = raw_em
        else:
            # EMA: smoothed = alpha * new + (1 - alpha) * previous
            smoothed_em = (self._ema_alpha * raw_em +
                          (1 - self._ema_alpha) * self._previous_expected_move)

        # Update state for next calculation
        self._previous_expected_move = smoothed_em

        return smoothed_em

    def calculate_net_gamma(self, call_gamma: float, put_gamma: float,
                            call_oi: int = 0, put_oi: int = 0) -> float:
        """
        Calculate net gamma at a strike.

        Net gamma = call_gamma * call_OI * 100 + put_gamma * put_OI * 100
        (Both should be positive as they measure absolute exposure)

        For visualization, we show the sum as net gamma affects dealer hedging.
        """
        # Gamma is always positive, but we multiply by OI and contract multiplier
        call_exposure = abs(call_gamma) * call_oi * 100 if call_oi else abs(call_gamma)
        put_exposure = abs(put_gamma) * put_oi * 100 if put_oi else abs(put_gamma)

        # Net gamma is typically calls - puts for directional bias
        # Positive = calls dominate (dealers hedging by buying)
        # Negative = puts dominate (dealers hedging by selling)
        return call_exposure - put_exposure

    def detect_gamma_flip(self, current_gamma: float, previous_gamma: float) -> Tuple[bool, Optional[str]]:
        """
        Detect if gamma flipped from positive to negative or vice versa.

        Returns:
            Tuple of (flipped: bool, direction: Optional[str])
        """
        if previous_gamma is None or previous_gamma == 0:
            return False, None

        # Check for sign change
        if current_gamma > 0 and previous_gamma < 0:
            return True, FlipDirection.NEG_TO_POS.value
        elif current_gamma < 0 and previous_gamma > 0:
            return True, FlipDirection.POS_TO_NEG.value

        return False, None

    def classify_gamma_regime(self, total_net_gamma: float, spot_price: float = 0) -> str:
        """
        Classify overall gamma regime based on total net gamma.

        Args:
            total_net_gamma: Sum of net gamma across strikes (gamma × OI × 100 units)
            spot_price: Current spot price. When provided, converts gamma-exposure
                        units to GEX-dollar units (× spot²) before comparing thresholds.

        Returns:
            POSITIVE, NEGATIVE, or NEUTRAL
        """
        # Convert to GEX-dollar units if spot_price is available
        # total_net_gamma is in gamma × OI × 100 units from calculate_net_gamma
        # GEX-dollar = gamma × OI × 100 × spot² — matches market_regime_classifier scale
        if spot_price > 0:
            gex_value = total_net_gamma * (spot_price ** 2)
        else:
            gex_value = total_net_gamma

        # Threshold for neutral zone in GEX-dollar units
        neutral_threshold = 1e9  # $1B

        if gex_value > neutral_threshold:
            return GammaRegime.POSITIVE.value
        elif gex_value < -neutral_threshold:
            return GammaRegime.NEGATIVE.value
        else:
            return GammaRegime.NEUTRAL.value

    def get_ml_status(self) -> Dict:
        """Get ML model status for monitoring"""
        ml_models = self._get_ml_models()
        if not ml_models:
            return {
                'is_trained': False,
                'model_info': None,
                'needs_retraining': True,
                'staleness_hours': None,
                'status': 'NOT_LOADED'
            }

        return {
            'is_trained': ml_models.is_trained,
            'model_info': ml_models.model_info,
            'needs_retraining': ml_models.needs_retraining() if hasattr(ml_models, 'needs_retraining') else True,
            'staleness_hours': ml_models.get_model_staleness_hours() if hasattr(ml_models, 'get_model_staleness_hours') else None,
            'status': 'TRAINED' if ml_models.is_trained else 'NOT_TRAINED'
        }

    def calculate_probability_hybrid(self, strike: float, spot_price: float,
                                     net_gamma: float, total_gamma: float,
                                     expected_move: float,
                                     gamma_structure: Dict = None) -> float:
        """
        Calculate probability of price landing at a strike using hybrid approach.

        60% ML model + 40% gamma-weighted distance

        Args:
            strike: Strike price
            spot_price: Current spot price
            net_gamma: Net gamma at this strike
            total_gamma: Total absolute gamma across all strikes
            expected_move: Expected move in dollars
            gamma_structure: Optional structure for ML model

        Returns:
            Probability as percentage (0-100)
        """
        # Distance component (40% weight)
        distance_from_spot = abs(strike - spot_price)
        gamma_magnitude = abs(net_gamma)

        # Avoid division by zero
        if total_gamma == 0:
            total_gamma = 1

        # Gamma weight (higher gamma = more likely to attract)
        gamma_weight = gamma_magnitude / total_gamma

        # Distance decay (exponential decay based on expected move)
        if expected_move > 0:
            distance_decay = math.exp(-distance_from_spot / expected_move)
        else:
            distance_decay = 1.0 if distance_from_spot == 0 else 0.0

        distance_probability = gamma_weight * distance_decay * 100

        # ML component (60% weight) - try to use ML models
        ml_probability = distance_probability  # Default to distance if no ML
        ml_used = False

        ml_models = self._get_ml_models()
        if ml_models and ml_models.is_trained:
            # Build minimal gamma_structure if not provided
            if gamma_structure is None:
                gamma_structure = {
                    'net_gamma': net_gamma,
                    'total_gamma': total_gamma,
                    'flip_point': spot_price,
                    'magnets': [{'strike': strike, 'gamma': net_gamma}],
                    'vix': 20,
                    'gamma_regime': 'POSITIVE' if net_gamma > 0 else 'NEGATIVE',
                    'expected_move': expected_move
                }

            try:
                ml_result = ml_models.predict_magnet_attraction(
                    strike, spot_price, gamma_structure
                )
                if ml_result and 'probability' in ml_result:
                    ml_probability = ml_result['probability'] * 100
                    ml_used = True
            except Exception as e:
                logger.debug(f"ML prediction failed, using distance only: {e}")

        # Combined probability
        combined = (0.6 * ml_probability) + (0.4 * distance_probability)

        # Log ML usage periodically
        if not hasattr(self, '_ml_call_count'):
            self._ml_call_count = 0
        self._ml_call_count += 1
        if self._ml_call_count % 500 == 0:
            logger.info(f"WATCHTOWER ML probability: used={ml_used}, calls={self._ml_call_count}")

        return combined

    def calculate_roc(self, strike: float, current_gamma: float,
                      history: List[Tuple[datetime, float]],
                      minutes: int = 1) -> float:
        """
        Calculate rate of change for a strike over specified minutes.

        Args:
            strike: Strike price
            current_gamma: Current gamma value
            history: List of (timestamp, gamma) tuples
            minutes: Number of minutes to look back (1, 5, 30, 60, 240)

        Returns:
            Rate of change as percentage
        """
        if not history or len(history) < 2:
            return 0.0

        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")

        # Find value from X minutes ago - use timezone-aware datetime
        target_time = datetime.now(CENTRAL_TZ) - timedelta(minutes=minutes)
        old_gamma = None

        for timestamp, gamma in reversed(history):
            # Handle timezone-aware comparison
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=CENTRAL_TZ)
            if timestamp <= target_time:
                old_gamma = gamma
                break

        if old_gamma is None or old_gamma == 0:
            return 0.0

        roc = ((current_gamma - old_gamma) / abs(old_gamma)) * 100
        return round(roc, 2)

    def calculate_roc_since_open(self, current_gamma: float,
                                  history: List[Tuple[datetime, float]],
                                  strike: float = None) -> float:
        """
        Calculate rate of change since market open (8:30 AM CT).

        Uses stable baseline (median of first 5 minutes) when available,
        falls back to first recorded value otherwise.

        Args:
            current_gamma: Current gamma value
            history: List of (timestamp, gamma) tuples
            strike: Strike price (for baseline lookup)

        Returns:
            Rate of change as percentage since market open
        """
        if not history or len(history) < 1:
            return 0.0

        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")
        now = datetime.now(CENTRAL_TZ)

        # Market open is 8:30 AM CT
        market_open = now.replace(hour=8, minute=30, second=0, microsecond=0)

        # If it's before market open today, no trading day ROC available
        if now < market_open:
            return 0.0

        # Try to use stable baseline first (median of first 5 minutes)
        open_gamma = None
        if strike is not None:
            open_gamma = self.get_market_open_baseline(strike)

        # Fall back to first recorded value if no stable baseline
        if open_gamma is None:
            for timestamp, gamma in history:
                # Handle timezone-aware comparison
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=CENTRAL_TZ)
                if timestamp >= market_open:
                    open_gamma = gamma
                    break

        if open_gamma is None or open_gamma == 0:
            return 0.0

        roc = ((current_gamma - open_gamma) / abs(open_gamma)) * 100
        return round(roc, 2)

    def update_history(self, strike: float, gamma: float, timestamp: datetime = None):
        """Update gamma history for a strike"""
        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")

        if timestamp is None:
            timestamp = datetime.now(CENTRAL_TZ)

        # Ensure timestamp is timezone-aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=CENTRAL_TZ)

        if strike not in self.history:
            self.history[strike] = []

        self.history[strike].append((timestamp, gamma))

        # Keep history for full trading day (7 hours = 420 minutes to cover pre-market to close)
        cutoff = timestamp - timedelta(minutes=420)
        self.history[strike] = [
            (t, g) for t, g in self.history[strike]
            if (t.replace(tzinfo=CENTRAL_TZ) if t.tzinfo is None else t) >= cutoff
        ]

    def identify_magnets(self, strikes: List[StrikeData], top_n: int = 3) -> List[Dict]:
        """
        Identify top N gamma magnets (strikes with highest absolute gamma).

        Returns:
            List of dicts with strike and gamma info
        """
        sorted_strikes = sorted(strikes, key=lambda s: abs(s.net_gamma), reverse=True)

        magnets = []
        for i, strike_data in enumerate(sorted_strikes[:top_n]):
            magnets.append({
                'rank': i + 1,
                'strike': strike_data.strike,
                'net_gamma': strike_data.net_gamma,
                'probability': strike_data.probability
            })
            strike_data.is_magnet = True
            strike_data.magnet_rank = i + 1

        return magnets

    def identify_pin_strike(self, strikes: List[StrikeData], spot_price: float) -> Tuple[float, float]:
        """
        Identify the likely pin strike.

        Pin score = (probability * 0.4) + (gamma_rank * 0.3) + (proximity_score * 0.3)

        Returns:
            Tuple of (pin_strike, pin_probability)
        """
        if not strikes:
            return 0.0, 0.0

        best_pin = None
        best_score = -1

        # Rank strikes by gamma
        sorted_by_gamma = sorted(strikes, key=lambda s: abs(s.net_gamma), reverse=True)
        gamma_ranks = {s.strike: i + 1 for i, s in enumerate(sorted_by_gamma)}

        for strike_data in strikes:
            # Probability component (0-1, higher is better)
            prob_score = strike_data.probability / 100

            # Gamma rank component (1 is best, invert so higher is better)
            gamma_rank = gamma_ranks.get(strike_data.strike, len(strikes))
            gamma_score = 1 - (gamma_rank / len(strikes))

            # Proximity score (closer to spot is better)
            distance = abs(strike_data.strike - spot_price)
            max_distance = max(abs(s.strike - spot_price) for s in strikes) or 1
            proximity_score = 1 - (distance / max_distance)

            # Combined score
            pin_score = (prob_score * 0.4) + (gamma_score * 0.3) + (proximity_score * 0.3)

            if pin_score > best_score:
                best_score = pin_score
                best_pin = strike_data

        if best_pin:
            best_pin.is_pin = True
            return best_pin.strike, best_pin.probability

        return 0.0, 0.0

    def identify_danger_zones(self, strikes: List[StrikeData]) -> List[Dict]:
        """
        Identify danger zones - strikes with rapid gamma changes.

        Thresholds:
        - BUILDING: 5-min ROC > +25%
        - COLLAPSING: 5-min ROC < -25%
        - SPIKE: 1-min ROC > +15%
        """
        danger_zones = []

        for strike_data in strikes:
            danger_type = None

            if strike_data.roc_5min >= self.ROC_5MIN_BUILDING_THRESHOLD:
                danger_type = DangerType.BUILDING.value
            elif strike_data.roc_5min <= self.ROC_5MIN_COLLAPSING_THRESHOLD:
                danger_type = DangerType.COLLAPSING.value
            elif strike_data.roc_1min >= self.ROC_1MIN_SPIKE_THRESHOLD:
                danger_type = DangerType.SPIKE.value

            if danger_type:
                strike_data.is_danger = True
                strike_data.danger_type = danger_type
                danger_zones.append({
                    'strike': strike_data.strike,
                    'danger_type': danger_type,
                    'roc_1min': strike_data.roc_1min,
                    'roc_5min': strike_data.roc_5min
                })

        return danger_zones

    def detect_pinning_condition(
        self,
        strikes: List[StrikeData],
        spot_price: float,
        likely_pin: float,
        danger_zones: List[Dict]
    ) -> Dict:
        """
        Detect if the market is in a "pinning" condition.

        Pinning is detected when:
        1. No danger zones (gamma is stable, no significant ROC)
        2. Spot price is within 0.5% of likely pin strike
        3. Average absolute ROC is low (< 5%)

        Returns:
            Dict with pinning status and details
        """
        if not strikes or not likely_pin:
            return {'is_pinning': False}

        # Check 1: No danger zones
        has_no_danger = len(danger_zones) == 0

        # Check 2: Spot is close to pin (within 0.5%)
        distance_to_pin_pct = abs(spot_price - likely_pin) / spot_price * 100 if spot_price > 0 else 100
        is_near_pin = distance_to_pin_pct < 0.5

        # Check 3: Average ROC is low (stable gamma)
        roc_values = []
        for s in strikes:
            roc_values.extend([abs(s.roc_1min), abs(s.roc_5min)])

        avg_roc = sum(roc_values) / len(roc_values) if roc_values else 0
        is_stable = avg_roc < 5.0  # Less than 5% average movement

        # Determine pinning status
        is_pinning = has_no_danger and (is_near_pin or is_stable)

        if is_pinning:
            if is_near_pin:
                message = f"PINNING: Price is pinning near ${likely_pin} strike (within {distance_to_pin_pct:.2f}%). Gamma stable, expect tight range."
            else:
                message = f"STABLE: No gamma movement detected (avg ROC: {avg_roc:.1f}%). Price likely to gravitate toward ${likely_pin} pin."

            return {
                'is_pinning': True,
                'pin_strike': likely_pin,
                'distance_to_pin_pct': round(distance_to_pin_pct, 2),
                'avg_roc': round(avg_roc, 2),
                'message': message,
                'trade_idea': 'Iron Condor or Credit Spread around pin strike may be favorable.'
            }

        return {'is_pinning': False}

    def generate_trading_signal(self, strikes: List[StrikeData], spot_price: float,
                                 likely_pin: float, gamma_regime: str) -> Dict:
        """
        Generate actionable trading signal based on GEX structure.

        Uses OI-WEIGHTED GEX RANKINGS (stable because OI doesn't change intraday)
        instead of noisy gamma % changes. This follows SpotGamma's methodology
        of locking major levels at market open for 0DTE.

        A strike is "building" if its GEX rank improved 3+ positions since open.
        A strike is "decaying" if its GEX rank declined 3+ positions since open.
        Major strikes (top 5 at open) stay major unless they drop to rank 10+.

        Returns:
            Dict with signal, confidence, and specific trade recommendations
        """
        if not strikes:
            return {
                'signal': 'NO_DATA',
                'confidence': 'LOW',
                'action': 'Wait for market data',
                'explanation': 'Insufficient data to generate signal'
            }

        # First, lock GEX levels at open if not already locked
        self.lock_gex_levels_at_open(strikes, spot_price)

        # Calculate current GEX rankings
        sorted_by_gex = sorted(strikes, key=lambda s: abs(s.net_gamma), reverse=True)
        current_rankings = {s.strike: rank for rank, s in enumerate(sorted_by_gex, 1)}

        # Categorize strikes by GEX RANK change (stable) instead of % change (noisy)
        # Building = rank improved by 3+ positions (strike becoming more important)
        # Decaying = rank declined by 3+ positions (strike losing importance)
        building_strikes = []
        decaying_strikes = []
        stable_strikes = []

        for s in strikes:
            current_rank = current_rankings.get(s.strike, len(strikes))
            rank_change = self.get_gex_rank_change(s.strike, current_rank)

            # Mark major strikes (top 5 at open) - these are stable anchors
            is_major = self.is_major_strike(s.strike)

            if rank_change >= 3:  # Improved 3+ positions
                building_strikes.append(s)
            elif rank_change <= -3:  # Declined 3+ positions
                # Major strikes only "decay" if they drop to rank 10+
                if is_major and current_rank < 10:
                    stable_strikes.append(s)  # Major strike stays stable
                else:
                    decaying_strikes.append(s)
            else:
                stable_strikes.append(s)

        # Separate building above vs below spot
        building_above = [s for s in building_strikes if s.strike > spot_price]
        building_below = [s for s in building_strikes if s.strike < spot_price]
        decaying_above = [s for s in decaying_strikes if s.strike > spot_price]
        decaying_below = [s for s in decaying_strikes if s.strike < spot_price]

        # Count for pattern detection
        n_building_above = len(building_above)
        n_building_below = len(building_below)
        n_decaying_above = len(decaying_above)
        n_decaying_below = len(decaying_below)
        n_building = len(building_strikes)
        n_decaying = len(decaying_strikes)

        # Calculate average building strength
        avg_building_pct = (sum(s.roc_trading_day for s in building_strikes) /
                           n_building if n_building else 0)
        avg_decaying_pct = (sum(s.roc_trading_day for s in decaying_strikes) /
                           n_decaying if n_decaying else 0)

        # Calculate Net GEX Volume for intraday flow confirmation
        # OI tells us about STRUCTURE (stable), Volume tells us about FLOW (intraday momentum)
        gex_volume = self.calculate_net_gex_volume(strikes, spot_price)
        flow_direction = gex_volume['flow_direction']
        flow_strength = gex_volume['flow_strength']

        # Detect patterns and generate signals
        # Include major strikes from open for stability reference
        signal_data = {
            'building_count': n_building,
            'decaying_count': n_decaying,
            'building_above_spot': n_building_above,
            'building_below_spot': n_building_below,
            'avg_building_strength': round(avg_building_pct, 1),
            'avg_decaying_strength': round(avg_decaying_pct, 1),
            'gamma_regime': gamma_regime,
            'major_strikes': self._major_strikes_at_open,  # Top 5 GEX at open (stable anchors)
            'gex_locked': self._gex_levels_locked,
            'methodology': 'GEX_RANK',  # Using OI-weighted rank changes, not noisy % changes
            # Net GEX Volume - intraday flow data (volume weighted by gamma)
            'gex_volume': gex_volume,
            'flow_direction': flow_direction,
            'flow_strength': flow_strength
        }

        # Helper to adjust confidence based on volume flow confirmation
        def adjust_confidence_with_volume(base_confidence: str, signal_type: str) -> str:
            """
            Boost or reduce confidence based on volume flow alignment.
            BULLISH signal + BULLISH flow = boost
            BEARISH signal + BEARISH flow = boost
            SELL_PREMIUM + NEUTRAL flow = boost
            Directional signal + OPPOSITE flow = reduce
            """
            if flow_strength == 'NONE':
                return base_confidence  # No volume data, keep base confidence

            # For directional signals, check alignment
            if signal_type == 'BULLISH_BIAS':
                if flow_direction == 'BULLISH' and flow_strength in ['STRONG', 'MODERATE']:
                    return 'HIGH'  # Volume confirms bullish structure
                elif flow_direction == 'BEARISH' and flow_strength in ['STRONG', 'MODERATE']:
                    return 'LOW'  # Volume contradicts bullish structure
            elif signal_type == 'BEARISH_BIAS':
                if flow_direction == 'BEARISH' and flow_strength in ['STRONG', 'MODERATE']:
                    return 'HIGH'  # Volume confirms bearish structure
                elif flow_direction == 'BULLISH' and flow_strength in ['STRONG', 'MODERATE']:
                    return 'LOW'  # Volume contradicts bearish structure
            elif signal_type == 'SELL_PREMIUM':
                if flow_direction == 'NEUTRAL' or flow_strength == 'WEAK':
                    return 'HIGH'  # Low directional flow supports premium selling
                elif flow_strength == 'STRONG':
                    return 'MEDIUM'  # Strong directional flow - be cautious with IC
            elif signal_type == 'BREAKOUT_LIKELY':
                if flow_strength in ['STRONG', 'MODERATE']:
                    return 'HIGH'  # Strong flow suggests momentum building

            return base_confidence

        # Helper to add volume context to explanation
        def volume_context() -> str:
            if flow_strength == 'NONE':
                return ''
            direction_emoji = 'call' if flow_direction == 'BULLISH' else 'put' if flow_direction == 'BEARISH' else 'balanced'
            return f" Vol flow: {flow_strength} {flow_direction.lower()} (${gex_volume['net_gex_volume']}M net {direction_emoji} GEX)."

        # PATTERN 1: Symmetric building (premium selling opportunity)
        if n_building_above >= 2 and n_building_below >= 2:
            base_conf = 'HIGH' if gamma_regime == 'POSITIVE' else 'MEDIUM'
            final_conf = adjust_confidence_with_volume(base_conf, 'SELL_PREMIUM')
            signal_data.update({
                'signal': 'SELL_PREMIUM',
                'confidence': final_conf,
                'action': f'Iron Condor or Iron Butterfly centered at ${likely_pin}',
                'explanation': (f'GEX gaining importance above ({n_building_above} strikes) '
                               f'and below ({n_building_below} strikes) spot. '
                               f'Dealers capping both directions. Range-bound near ${likely_pin}.'
                               f'{volume_context()}'),
                'short_strike_call': building_above[0].strike if building_above else None,
                'short_strike_put': building_below[-1].strike if building_below else None,
                'volume_confirms': flow_direction == 'NEUTRAL' or flow_strength == 'WEAK'
            })

        # PATTERN 2: Building above only (bullish bias)
        elif n_building_above >= 2 and n_building_below == 0:
            target_strike = building_above[0].strike if building_above else spot_price + 2
            base_conf = 'HIGH' if gamma_regime == 'NEGATIVE' else 'MEDIUM'
            final_conf = adjust_confidence_with_volume(base_conf, 'BULLISH_BIAS')
            signal_data.update({
                'signal': 'BULLISH_BIAS',
                'confidence': final_conf,
                'action': f'Bull call spread or call debit spread targeting ${target_strike}',
                'explanation': (f'GEX concentrating above spot ({n_building_above} strikes gaining rank). '
                               f'Call wall building = resistance, but dealers must buy on breakout. '
                               f'Target: ${target_strike}.{volume_context()}'),
                'target_strike': target_strike,
                'volume_confirms': flow_direction == 'BULLISH'
            })

        # PATTERN 3: Building below only (bearish bias)
        elif n_building_below >= 2 and n_building_above == 0:
            target_strike = building_below[-1].strike if building_below else spot_price - 2
            base_conf = 'HIGH' if gamma_regime == 'NEGATIVE' else 'MEDIUM'
            final_conf = adjust_confidence_with_volume(base_conf, 'BEARISH_BIAS')
            signal_data.update({
                'signal': 'BEARISH_BIAS',
                'confidence': final_conf,
                'action': f'Bear put spread or put debit spread targeting ${target_strike}',
                'explanation': (f'GEX concentrating below spot ({n_building_below} strikes gaining rank). '
                               f'Put wall building = support, but dealers must sell on breakdown. '
                               f'Target: ${target_strike}.{volume_context()}'),
                'target_strike': target_strike,
                'volume_confirms': flow_direction == 'BEARISH'
            })

        # PATTERN 4: Widespread decay (momentum/breakout likely)
        elif n_decaying >= 4 and n_building <= 1:
            base_conf = 'HIGH' if gamma_regime == 'NEGATIVE' else 'MEDIUM'
            final_conf = adjust_confidence_with_volume(base_conf, 'BREAKOUT_LIKELY')
            # Use volume flow to determine breakout direction
            breakout_direction = ''
            if flow_direction == 'BULLISH' and flow_strength in ['STRONG', 'MODERATE']:
                breakout_direction = ' (likely UPWARD based on vol flow)'
            elif flow_direction == 'BEARISH' and flow_strength in ['STRONG', 'MODERATE']:
                breakout_direction = ' (likely DOWNWARD based on vol flow)'
            signal_data.update({
                'signal': 'BREAKOUT_LIKELY',
                'confidence': final_conf,
                'action': f'Long straddle or strangle at ATM strike{breakout_direction}',
                'explanation': (f'GEX importance declining at {n_decaying} strikes. '
                               f'Dealer hedging walls weakening - less resistance to moves. '
                               f'Expect larger range.{volume_context()}'),
                'breakout_direction': flow_direction if flow_strength != 'NONE' else 'UNKNOWN',
                'volume_confirms': flow_strength in ['STRONG', 'MODERATE']
            })

        # PATTERN 5: Building at pin, decaying elsewhere (strong pinning)
        elif n_building == 1 and abs(building_strikes[0].strike - likely_pin) <= 1:
            # Strong pin is confirmed if flow is weak/neutral
            final_conf = 'HIGH' if flow_strength in ['NONE', 'WEAK'] else 'MEDIUM'
            signal_data.update({
                'signal': 'STRONG_PIN',
                'confidence': final_conf,
                'action': f'Sell premium around ${likely_pin} pin. Tight credit spread or butterfly.',
                'explanation': (f'GEX concentrating at pin strike ${likely_pin}. '
                               f'Major strike holding rank - strong magnet. Tight range expected.'
                               f'{volume_context()}'),
                'volume_confirms': flow_strength in ['NONE', 'WEAK']
            })

        # PATTERN 6: No clear pattern but stable
        elif n_building <= 1 and n_decaying <= 1:
            # If we have strong volume flow despite stable structure, note the potential direction
            if flow_strength in ['STRONG', 'MODERATE']:
                signal_data.update({
                    'signal': 'FLOW_DRIVEN',
                    'confidence': 'MEDIUM',
                    'action': f'Follow volume flow: {"calls" if flow_direction == "BULLISH" else "puts"} favored',
                    'explanation': (f'Gamma structure stable but {flow_strength.lower()} {flow_direction.lower()} '
                                   f'volume flow detected (${gex_volume["net_gex_volume"]}M). '
                                   f'Flow may lead structure - consider directional plays aligned with flow.'),
                    'volume_confirms': True
                })
            else:
                signal_data.update({
                    'signal': 'NEUTRAL_WAIT',
                    'confidence': 'LOW',
                    'action': 'Wait for clearer pattern or trade small iron condor',
                    'explanation': f'Gamma structure stable, no strong directional signal or volume flow. Wait for setup.{volume_context()}',
                    'volume_confirms': False
                })

        # PATTERN 7: Mixed/chaotic
        else:
            signal_data.update({
                'signal': 'MIXED_SIGNALS',
                'confidence': 'LOW',
                'action': 'Reduce position size. Consider waiting.',
                'explanation': (f'Mixed gamma signals: {n_building} building, {n_decaying} decaying. '
                               f'Market structure unclear - trade small or sit out.{volume_context()}'),
                'volume_confirms': False
            })

        return signal_data

    def calculate_bid_ask_pressure(self, strikes: List[StrikeData], spot_price: float,
                                     atm_range_pct: float = 0.03, min_depth: int = 100,
                                     update_smoothing: bool = True) -> Dict:
        """
        Analyze bid/ask size imbalance to determine order flow pressure.

        NOISE REDUCTION:
        - Only uses strikes within ±3% of spot (ATM focus for liquidity)
        - Requires minimum depth threshold to avoid thin markets
        - Smooths readings using 5-period rolling average
        - Gamma-weights pressure so high-impact strikes matter more

        Args:
            strikes: List of StrikeData objects
            spot_price: Current spot price
            atm_range_pct: Percentage range from ATM to include (default 3%)
            min_depth: Minimum total contracts for valid signal (default 100)
            update_smoothing: If False, skip adding to pressure history (use for cached data)

        Bid/Ask Size Interpretation:
        - bid_size >> ask_size = Buyers stacked up = BULLISH pressure (demand > supply)
        - ask_size >> bid_size = Sellers stacked up = BEARISH pressure (supply > demand)

        This differs from volume (what traded) - bid/ask size shows what's WAITING to trade.

        For options market context:
        - Call bid_size high = Buyers want calls = BULLISH
        - Call ask_size high = Sellers offering calls = NEUTRAL/covered calls
        - Put bid_size high = Buyers want puts = BEARISH/hedging
        - Put ask_size high = Sellers offering puts = BULLISH (selling insurance)

        Args:
            strikes: List of StrikeData objects
            spot_price: Current spot price
            atm_range_pct: Percentage range from ATM to include (default 3%)
            min_depth: Minimum total contracts for valid signal (default 100)

        Returns:
            Dict with pressure metrics and per-strike breakdown
        """
        # Initialize pressure history if not exists
        if not hasattr(self, '_pressure_history'):
            self._pressure_history = []

        empty_result = {
            'net_pressure': 0.0,
            'raw_pressure': 0.0,  # Unsmoothed value (same as net when empty)
            'pressure_direction': 'NEUTRAL',
            'pressure_strength': 'NONE',
            'call_pressure': 0.0,
            'put_pressure': 0.0,
            'total_bid_size': 0,
            'total_ask_size': 0,
            'liquidity_score': 0.0,
            'strikes_used': 0,
            'smoothing_periods': 0,  # No history yet
            'is_valid': False,
            'reason': '',
            'top_pressure_strikes': []
        }

        if not strikes or spot_price <= 0:
            empty_result['reason'] = 'No strikes or invalid spot price'
            return empty_result

        # FILTER 1: Only use strikes within ±3% of spot (ATM focus)
        atm_min = spot_price * (1 - atm_range_pct)
        atm_max = spot_price * (1 + atm_range_pct)
        atm_strikes = [s for s in strikes if atm_min <= s.strike <= atm_max]

        if not atm_strikes:
            empty_result['reason'] = f'No strikes within ±{atm_range_pct*100:.0f}% of spot'
            return empty_result

        total_call_bid = 0
        total_call_ask = 0
        total_put_bid = 0
        total_put_ask = 0
        strike_pressure = []

        for s in atm_strikes:
            # Aggregate bid/ask sizes
            total_call_bid += s.call_bid_size
            total_call_ask += s.call_ask_size
            total_put_bid += s.put_bid_size
            total_put_ask += s.put_ask_size

            # Calculate per-strike pressure weighted by gamma
            # Higher gamma = more market impact = weight the pressure more
            gamma_weight = abs(s.net_gamma) + 0.0001  # Avoid division by zero

            # Call pressure: bid - ask (positive = buyers dominate)
            call_imbalance = s.call_bid_size - s.call_ask_size
            # Put pressure: ask - bid (positive = sellers dominate = bullish for market)
            put_imbalance = s.put_ask_size - s.put_bid_size

            # Net bullish pressure at this strike
            strike_net_pressure = (call_imbalance + put_imbalance) * gamma_weight

            strike_pressure.append({
                'strike': s.strike,
                'call_bid_size': s.call_bid_size,
                'call_ask_size': s.call_ask_size,
                'put_bid_size': s.put_bid_size,
                'put_ask_size': s.put_ask_size,
                'call_imbalance': call_imbalance,
                'put_imbalance': put_imbalance,
                'net_pressure': round(strike_net_pressure, 2),
                'gamma_weight': round(gamma_weight, 6)
            })

        # Calculate aggregate pressure metrics
        total_bid = total_call_bid + total_put_bid
        total_ask = total_call_ask + total_put_ask
        total_depth = total_bid + total_ask

        # FILTER 2: Minimum depth threshold
        if total_depth < min_depth:
            empty_result['total_bid_size'] = total_bid
            empty_result['total_ask_size'] = total_ask
            empty_result['strikes_used'] = len(atm_strikes)
            empty_result['reason'] = f'Insufficient depth ({total_depth} < {min_depth} contracts)'
            return empty_result

        # Call pressure: buyers vs sellers in calls
        # Positive = more call buyers = bullish
        if total_call_bid + total_call_ask > 0:
            call_pressure = (total_call_bid - total_call_ask) / (total_call_bid + total_call_ask)
        else:
            call_pressure = 0.0

        # Put pressure: sellers vs buyers in puts
        # Positive put_ask (selling puts) = bullish, positive put_bid (buying puts) = bearish
        if total_put_bid + total_put_ask > 0:
            put_pressure = (total_put_ask - total_put_bid) / (total_put_bid + total_put_ask)
        else:
            put_pressure = 0.0

        # Net pressure combines call buying pressure and put selling pressure
        # Both are bullish signals
        raw_net_pressure = (call_pressure + put_pressure) / 2

        # SMOOTHING: Add to history and compute rolling average
        # Only update history with fresh data to prevent cache corruption
        if update_smoothing:
            self._pressure_history.append(raw_net_pressure)
            # Keep only last 5 readings for smoothing
            if len(self._pressure_history) > 5:
                self._pressure_history = self._pressure_history[-5:]

        # Smoothed pressure = average of last N readings (or raw if no history)
        if self._pressure_history:
            smoothed_pressure = sum(self._pressure_history) / len(self._pressure_history)
        else:
            smoothed_pressure = raw_net_pressure

        # Determine pressure direction and strength from SMOOTHED value
        if abs(smoothed_pressure) < 0.1:
            pressure_direction = 'NEUTRAL'
            pressure_strength = 'NONE'
        elif smoothed_pressure > 0:
            pressure_direction = 'BULLISH'
            if smoothed_pressure > 0.4:
                pressure_strength = 'STRONG'
            elif smoothed_pressure > 0.2:
                pressure_strength = 'MODERATE'
            else:
                pressure_strength = 'WEAK'
        else:
            pressure_direction = 'BEARISH'
            if smoothed_pressure < -0.4:
                pressure_strength = 'STRONG'
            elif smoothed_pressure < -0.2:
                pressure_strength = 'MODERATE'
            else:
                pressure_strength = 'WEAK'

        # Liquidity score: higher = more liquid = easier execution
        # Based on total depth available in ATM zone
        liquidity_score = min(100, total_depth / 100)  # Normalize to 0-100

        # Top pressure strikes (highest absolute net pressure)
        sorted_by_pressure = sorted(strike_pressure, key=lambda x: abs(x['net_pressure']), reverse=True)[:5]

        return {
            'net_pressure': round(smoothed_pressure, 3),
            'raw_pressure': round(raw_net_pressure, 3),  # Unsmoothed for reference
            'pressure_direction': pressure_direction,
            'pressure_strength': pressure_strength,
            'call_pressure': round(call_pressure, 3),
            'put_pressure': round(put_pressure, 3),
            'total_bid_size': total_bid,
            'total_ask_size': total_ask,
            'liquidity_score': round(liquidity_score, 1),
            'strikes_used': len(atm_strikes),
            'smoothing_periods': len(self._pressure_history),
            'is_valid': True,
            'reason': 'OK',
            'top_pressure_strikes': sorted_by_pressure
        }

    def calculate_net_gex_volume(self, strikes: List[StrikeData], spot_price: float,
                                   update_smoothing: bool = True) -> Dict:
        """
        Calculate Net GEX Volume - intraday flow weighted by gamma impact.

        Unlike OI-based GEX (which is stable because OI doesn't change intraday),
        volume DOES change intraday and tells us about FLOW/MOMENTUM.

        Args:
            strikes: List of StrikeData objects
            spot_price: Current spot price
            update_smoothing: If False, skip adding to pressure history (use for cached data)

        Formula:
            Call GEX Flow = Call_Volume × |Call_Gamma| × 100 × spot²
            Put GEX Flow = Put_Volume × |Put_Gamma| × 100 × spot²
            Net GEX Volume = Call GEX Flow - Put GEX Flow

        Enhanced with bid/ask pressure for confirmation:
            - Volume shows what TRADED
            - Bid/ask size shows what's WAITING to trade
            - Combined signal is more reliable

        Positive Net GEX Volume = Bullish flow (more call gamma being traded)
        Negative Net GEX Volume = Bearish flow (more put gamma being traded)

        Returns:
            Dict with net_gex_volume, flow_direction, bid/ask pressure, and per-strike breakdown
        """
        # Empty result with properly structured bid_ask_pressure
        empty_bid_ask = {
            'net_pressure': 0.0,
            'raw_pressure': 0.0,
            'pressure_direction': 'NEUTRAL',
            'pressure_strength': 'NONE',
            'call_pressure': 0.0,
            'put_pressure': 0.0,
            'total_bid_size': 0,
            'total_ask_size': 0,
            'liquidity_score': 0.0,
            'strikes_used': 0,
            'smoothing_periods': 0,
            'is_valid': False,
            'reason': 'No data',
            'top_pressure_strikes': []
        }

        if not strikes or spot_price <= 0:
            return {
                'net_gex_volume': 0,
                'call_gex_flow': 0,
                'put_gex_flow': 0,
                'flow_direction': 'NEUTRAL',
                'flow_strength': 'NONE',
                'imbalance_ratio': 0,
                'bid_ask_pressure': empty_bid_ask,
                'combined_signal': 'NEUTRAL',
                'signal_confidence': 'LOW',
                'top_call_flow_strikes': [],
                'top_put_flow_strikes': []
            }

        # Multiplier for GEX calculation
        multiplier = 100 * spot_price * spot_price

        call_gex_flow = 0
        put_gex_flow = 0
        strike_flows = []

        for s in strikes:
            # Calculate GEX-weighted volume for this strike
            call_flow = s.call_volume * abs(s.call_gamma) * multiplier
            put_flow = s.put_volume * abs(s.put_gamma) * multiplier

            call_gex_flow += call_flow
            put_gex_flow += put_flow

            strike_flows.append({
                'strike': s.strike,
                'call_flow': round(call_flow / 1e6, 2),  # In millions
                'put_flow': round(put_flow / 1e6, 2),
                'net_flow': round((call_flow - put_flow) / 1e6, 2),
                'call_volume': s.call_volume,
                'put_volume': s.put_volume,
                # Include bid/ask size for transparency
                'call_bid_size': s.call_bid_size,
                'call_ask_size': s.call_ask_size,
                'put_bid_size': s.put_bid_size,
                'put_ask_size': s.put_ask_size
            })

        net_gex_volume = call_gex_flow - put_gex_flow

        # Normalize to millions for readability
        net_gex_volume_m = net_gex_volume / 1e6
        call_gex_flow_m = call_gex_flow / 1e6
        put_gex_flow_m = put_gex_flow / 1e6

        # Determine flow direction and strength
        # Thresholds based on typical SPY 0DTE activity
        total_flow = call_gex_flow + put_gex_flow
        if total_flow > 0:
            imbalance_ratio = abs(net_gex_volume) / total_flow
        else:
            imbalance_ratio = 0

        if abs(net_gex_volume_m) < 1:  # Less than $1M net = neutral
            flow_direction = 'NEUTRAL'
            flow_strength = 'NONE'
        elif net_gex_volume_m > 0:
            flow_direction = 'BULLISH'
            if imbalance_ratio > 0.3:  # 30%+ imbalance
                flow_strength = 'STRONG'
            elif imbalance_ratio > 0.15:
                flow_strength = 'MODERATE'
            else:
                flow_strength = 'WEAK'
        else:
            flow_direction = 'BEARISH'
            if imbalance_ratio > 0.3:
                flow_strength = 'STRONG'
            elif imbalance_ratio > 0.15:
                flow_strength = 'MODERATE'
            else:
                flow_strength = 'WEAK'

        # Calculate bid/ask pressure for confirmation
        bid_ask_pressure = self.calculate_bid_ask_pressure(strikes, spot_price, update_smoothing=update_smoothing)

        # Combine volume flow with bid/ask pressure for final signal
        # Agreement = high confidence, disagreement = caution
        combined_signal, signal_confidence = self._combine_flow_signals(
            flow_direction, flow_strength,
            bid_ask_pressure['pressure_direction'],
            bid_ask_pressure['pressure_strength']
        )

        # Get top flow strikes
        sorted_by_call = sorted(strike_flows, key=lambda x: x['call_flow'], reverse=True)[:3]
        sorted_by_put = sorted(strike_flows, key=lambda x: x['put_flow'], reverse=True)[:3]

        return {
            'net_gex_volume': round(net_gex_volume_m, 2),
            'call_gex_flow': round(call_gex_flow_m, 2),
            'put_gex_flow': round(put_gex_flow_m, 2),
            'flow_direction': flow_direction,
            'flow_strength': flow_strength,
            'imbalance_ratio': round(imbalance_ratio * 100, 1),  # As percentage
            'bid_ask_pressure': bid_ask_pressure,
            'combined_signal': combined_signal,
            'signal_confidence': signal_confidence,
            'top_call_flow_strikes': sorted_by_call,
            'top_put_flow_strikes': sorted_by_put
        }

    def _combine_flow_signals(
        self,
        volume_direction: str,
        volume_strength: str,
        pressure_direction: str,
        pressure_strength: str
    ) -> Tuple[str, str]:
        """
        Combine volume flow direction with bid/ask pressure for final signal.

        Agreement between volume and pressure = HIGH confidence
        Disagreement = LOW confidence (proceed with caution)

        Returns:
            Tuple of (combined_signal, confidence)
        """
        # Both neutral
        if volume_direction == 'NEUTRAL' and pressure_direction == 'NEUTRAL':
            return 'NEUTRAL', 'HIGH'

        # Full agreement
        if volume_direction == pressure_direction:
            # Both bullish
            if volume_direction == 'BULLISH':
                if volume_strength == 'STRONG' or pressure_strength == 'STRONG':
                    return 'STRONG_BULLISH', 'HIGH'
                elif volume_strength == 'MODERATE' or pressure_strength == 'MODERATE':
                    return 'BULLISH', 'HIGH'
                else:
                    return 'BULLISH', 'MEDIUM'
            # Both bearish
            else:
                if volume_strength == 'STRONG' or pressure_strength == 'STRONG':
                    return 'STRONG_BEARISH', 'HIGH'
                elif volume_strength == 'MODERATE' or pressure_strength == 'MODERATE':
                    return 'BEARISH', 'HIGH'
                else:
                    return 'BEARISH', 'MEDIUM'

        # One neutral, one directional - trust the directional one with medium confidence
        if volume_direction == 'NEUTRAL':
            return pressure_direction, 'MEDIUM'
        if pressure_direction == 'NEUTRAL':
            return volume_direction, 'MEDIUM'

        # Disagreement - volume says one thing, pressure says another
        # This is a DIVERGENCE - important signal of potential reversal
        # Volume = what happened, Pressure = what's building
        # If volume is bullish but pressure is bearish, bulls are exhausting
        if volume_direction == 'BULLISH' and pressure_direction == 'BEARISH':
            return 'DIVERGENCE_BEARISH', 'LOW'  # Bullish exhaustion
        else:
            return 'DIVERGENCE_BULLISH', 'LOW'  # Bearish exhaustion

    def generate_alerts(self, current: GammaSnapshot, previous: Optional[GammaSnapshot]) -> List[Alert]:
        """
        Generate alerts based on current snapshot vs previous.
        """
        alerts = []

        # 1. Gamma Flip alerts
        for flip in current.gamma_flips:
            alert = Alert(
                alert_type=AlertType.GAMMA_FLIP.value,
                strike=flip['strike'],
                message=f"Strike {flip['strike']} gamma flipped {flip['direction']}",
                priority=AlertPriority.HIGH.value,
                spot_price=current.spot_price,
                old_value=str(flip.get('gamma_before', 'N/A')),
                new_value=str(flip.get('gamma_after', 'N/A'))
            )
            alerts.append(alert)

        # 2. Regime Change alert
        if current.regime_flipped and previous:
            alert = Alert(
                alert_type=AlertType.REGIME_CHANGE.value,
                strike=None,
                message=f"Gamma regime shifted from {previous.gamma_regime} to {current.gamma_regime}",
                priority=AlertPriority.HIGH.value,
                spot_price=current.spot_price,
                old_value=previous.gamma_regime,
                new_value=current.gamma_regime
            )
            alerts.append(alert)

        # 3. Magnet Shift alert
        if previous and current.magnets:
            current_top = current.magnets[0]['strike'] if current.magnets else None
            previous_top = self.previous_magnets[0] if self.previous_magnets else None

            if current_top and previous_top and current_top != previous_top:
                alert = Alert(
                    alert_type=AlertType.MAGNET_SHIFT.value,
                    strike=current_top,
                    message=f"Top magnet shifted from {previous_top} to {current_top}",
                    priority=AlertPriority.HIGH.value,
                    spot_price=current.spot_price,
                    old_value=str(previous_top),
                    new_value=str(current_top)
                )
                alerts.append(alert)

        # 4. Danger Zone alerts
        for dz in current.danger_zones:
            alert = Alert(
                alert_type=AlertType.DANGER_ZONE.value,
                strike=dz['strike'],
                message=f"Strike {dz['strike']} entered {dz['danger_type']} zone (ROC: {dz['roc_5min']:.1f}%)",
                priority=AlertPriority.MEDIUM.value,
                spot_price=current.spot_price,
                new_value=dz['danger_type']
            )
            alerts.append(alert)

        # 5. Pin Zone Entry alert
        if current.likely_pin:
            distance_to_pin = abs(current.spot_price - current.likely_pin)
            pin_zone_threshold = current.spot_price * (self.PIN_ZONE_PROXIMITY_PCT / 100)

            if distance_to_pin <= pin_zone_threshold:
                alert = Alert(
                    alert_type=AlertType.PIN_ZONE_ENTRY.value,
                    strike=current.likely_pin,
                    message=f"SPY entered pin zone near {current.likely_pin} strike",
                    priority=AlertPriority.MEDIUM.value,
                    spot_price=current.spot_price
                )
                alerts.append(alert)

        # 6. Gamma Spike alerts
        for strike_data in current.strikes:
            if previous:
                # Find previous strike data
                prev_strike = next(
                    (s for s in previous.strikes if s.strike == strike_data.strike),
                    None
                )
                if prev_strike and prev_strike.net_gamma != 0:
                    change_pct = ((strike_data.net_gamma - prev_strike.net_gamma) /
                                  abs(prev_strike.net_gamma)) * 100
                    if change_pct >= self.GAMMA_SPIKE_THRESHOLD:
                        alert = Alert(
                            alert_type=AlertType.GAMMA_SPIKE.value,
                            strike=strike_data.strike,
                            message=f"Strike {strike_data.strike} gamma spiked +{change_pct:.0f}%",
                            priority=AlertPriority.HIGH.value,
                            spot_price=current.spot_price,
                            old_value=str(prev_strike.net_gamma),
                            new_value=str(strike_data.net_gamma)
                        )
                        alerts.append(alert)

        return alerts

    def process_options_chain(self, options_data: Dict, spot_price: float,
                               vix: float, expiration: str) -> GammaSnapshot:
        """
        Process raw options chain data into a GammaSnapshot.

        Args:
            options_data: Dict containing options chain from Tradier
            spot_price: Current spot price
            vix: Current VIX level
            expiration: Expiration date string

        Returns:
            GammaSnapshot with all calculated metrics
        """
        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")
        timestamp = datetime.now(CENTRAL_TZ)
        market_status = self.get_market_status()

        # Extract strikes and calculate metrics
        strikes_data = []
        total_gamma = 0
        total_net_gamma = 0
        gamma_flips = []

        # Get previous strike data for comparison
        previous_strikes = {}
        if self.previous_snapshot:
            for s in self.previous_snapshot.strikes:
                previous_strikes[s.strike] = s

        # Calculate expected move from ATM options
        expected_move = 0
        atm_strike = round(spot_price)  # Simplified ATM finding

        # Process each strike from options data
        for strike_info in options_data.get('strikes', []):
            strike = strike_info.get('strike', 0)
            call_gamma = strike_info.get('call_gamma', 0)
            put_gamma = strike_info.get('put_gamma', 0)
            call_oi = strike_info.get('call_oi', 0)
            put_oi = strike_info.get('put_oi', 0)

            # Calculate raw net gamma
            raw_net_gamma = self.calculate_net_gamma(call_gamma, put_gamma, call_oi, put_oi)

            # Apply smoothing to reduce noise from Tradier Greeks recalculations
            # This uses median of recent readings and dampens suspicious large swings
            net_gamma = self._smooth_gamma_value(strike, raw_net_gamma, spot_price)

            # Update market open baseline (first 5 minutes of trading)
            self._update_market_open_baseline(strike, net_gamma)

            total_gamma += abs(net_gamma)
            total_net_gamma += net_gamma

            # Check for gamma flip
            prev_strike = previous_strikes.get(strike)
            prev_gamma = prev_strike.net_gamma if prev_strike else 0
            flipped, flip_dir = self.detect_gamma_flip(net_gamma, prev_gamma)

            if flipped:
                gamma_flips.append({
                    'strike': strike,
                    'direction': flip_dir,
                    'gamma_before': prev_gamma,
                    'gamma_after': net_gamma
                })

            # Update history for ROC calculation
            self.update_history(strike, net_gamma, timestamp)

            # Calculate ROC at multiple timeframes
            history = self.history.get(strike, [])
            roc_1min = self.calculate_roc(strike, net_gamma, history, minutes=1)
            roc_5min = self.calculate_roc(strike, net_gamma, history, minutes=5)
            roc_30min = self.calculate_roc(strike, net_gamma, history, minutes=30)
            roc_1hr = self.calculate_roc(strike, net_gamma, history, minutes=60)
            roc_4hr = self.calculate_roc(strike, net_gamma, history, minutes=240)
            roc_trading_day = self.calculate_roc_since_open(net_gamma, history, strike=strike)

            # Calculate gamma change percentage
            gamma_change_pct = 0
            if prev_gamma and prev_gamma != 0:
                gamma_change_pct = ((net_gamma - prev_gamma) / abs(prev_gamma)) * 100

            strike_data = StrikeData(
                strike=strike,
                net_gamma=net_gamma,
                call_gamma=call_gamma,
                put_gamma=put_gamma,
                gamma_change_pct=round(gamma_change_pct, 2),
                roc_1min=roc_1min,
                roc_5min=roc_5min,
                roc_30min=roc_30min,
                roc_1hr=roc_1hr,
                roc_4hr=roc_4hr,
                roc_trading_day=roc_trading_day,
                volume=strike_info.get('volume', 0),
                call_volume=strike_info.get('call_volume', 0),  # Separate for GEX flow
                put_volume=strike_info.get('put_volume', 0),    # Separate for GEX flow
                call_oi=strike_info.get('call_oi', 0),          # Open interest for GEX calculation
                put_oi=strike_info.get('put_oi', 0),            # Open interest for GEX calculation
                # Bid/ask size for order flow pressure analysis
                call_bid_size=strike_info.get('call_bid_size', 0),
                call_ask_size=strike_info.get('call_ask_size', 0),
                put_bid_size=strike_info.get('put_bid_size', 0),
                put_ask_size=strike_info.get('put_ask_size', 0),
                call_iv=strike_info.get('call_iv', 0),
                put_iv=strike_info.get('put_iv', 0),
                previous_net_gamma=prev_gamma,
                gamma_flipped=flipped,
                flip_direction=flip_dir
            )
            strikes_data.append(strike_data)

            # Calculate expected move from ATM
            if strike == atm_strike:
                call_price = strike_info.get('call_price', 0)
                put_price = strike_info.get('put_price', 0)
                expected_move = self.calculate_expected_move(call_price, put_price)

        # Default expected move if not calculated
        if expected_move == 0:
            expected_move = spot_price * 0.01  # 1% default

        # Build gamma_structure for ML predictions
        # Find magnets early (top 3 by gamma magnitude)
        sorted_by_gamma = sorted(strikes_data, key=lambda s: abs(s.net_gamma), reverse=True)
        top_magnets = [{'strike': s.strike, 'gamma': s.net_gamma} for s in sorted_by_gamma[:3]]

        # Calculate flip point (weighted average of positive/negative gamma centers)
        positive_strikes = [s for s in strikes_data if s.net_gamma > 0]
        negative_strikes = [s for s in strikes_data if s.net_gamma < 0]
        if positive_strikes and negative_strikes:
            pos_center = sum(s.strike * abs(s.net_gamma) for s in positive_strikes) / sum(abs(s.net_gamma) for s in positive_strikes)
            neg_center = sum(s.strike * abs(s.net_gamma) for s in negative_strikes) / sum(abs(s.net_gamma) for s in negative_strikes)
            flip_point = (pos_center + neg_center) / 2
        else:
            flip_point = spot_price

        # Build gamma_structure for ML
        gamma_structure = {
            'net_gamma': total_net_gamma,
            'total_gamma': total_gamma,
            'flip_point': flip_point,
            'magnets': top_magnets,
            'vix': vix,
            'gamma_regime': self.classify_gamma_regime(total_net_gamma, spot_price),
            'expected_move': expected_move,
            'spot_price': spot_price
        }

        # Calculate probabilities for all strikes using gamma_structure
        for strike_data in strikes_data:
            strike_data.probability = self.calculate_probability_hybrid(
                strike_data.strike,
                spot_price,
                strike_data.net_gamma,
                total_gamma,
                expected_move,
                gamma_structure  # Pass gamma_structure for ML predictions
            )

        # Normalize probabilities to sum to 100%
        total_prob = sum(s.probability for s in strikes_data)
        if total_prob > 0:
            for s in strikes_data:
                s.probability = round((s.probability / total_prob) * 100, 1)

        # Classify overall regime
        gamma_regime = self.classify_gamma_regime(total_net_gamma, spot_price)
        previous_regime = self.previous_snapshot.gamma_regime if self.previous_snapshot else None
        regime_flipped = previous_regime is not None and gamma_regime != previous_regime

        # Lock GEX levels at market open (like SpotGamma does for 0DTE)
        # This ensures major strikes remain stable throughout the day
        self.lock_gex_levels_at_open(strikes_data, spot_price)

        # Identify magnets, pin, and danger zones
        magnets = self.identify_magnets(strikes_data)
        likely_pin, pin_probability = self.identify_pin_strike(strikes_data, spot_price)
        danger_zones = self.identify_danger_zones(strikes_data)

        # Detect pinning condition (no danger zones = stable gamma = likely pinning)
        pinning_status = self.detect_pinning_condition(strikes_data, spot_price, likely_pin, danger_zones)

        # Calculate order flow analysis (volume-weighted gamma flow + bid/ask pressure)
        # This provides signal confirmation based on intraday trading activity
        order_flow = self.calculate_net_gex_volume(strikes_data, spot_price, update_smoothing=True)

        # Create snapshot
        symbol = options_data.get('symbol', 'SPY')  # Get symbol from data, default to SPY
        snapshot = GammaSnapshot(
            symbol=symbol,
            expiration_date=expiration,
            snapshot_time=timestamp,
            spot_price=spot_price,
            expected_move=expected_move,
            vix=vix,
            total_net_gamma=total_net_gamma,
            gamma_regime=gamma_regime,
            previous_regime=previous_regime,
            regime_flipped=regime_flipped,
            market_status=market_status,
            strikes=strikes_data,
            magnets=magnets,
            likely_pin=likely_pin,
            pin_probability=pin_probability,
            danger_zones=danger_zones,
            gamma_flips=gamma_flips,
            pinning_status=pinning_status,
            order_flow=order_flow
        )

        # Generate alerts
        self.alerts = self.generate_alerts(snapshot, self.previous_snapshot)

        # Update state for next iteration
        self.previous_snapshot = snapshot
        self.previous_magnets = [m['strike'] for m in magnets]
        self._previous_spot_price = spot_price  # Track for smoothing validation

        return snapshot

    def filter_strikes_by_expected_move(self, strikes: List[StrikeData],
                                         spot_price: float,
                                         expected_move: float,
                                         extra_strikes: int = 5) -> List[StrikeData]:
        """
        Filter strikes to only include those within expected move ± extra strikes.

        Args:
            strikes: All strike data
            spot_price: Current spot price
            expected_move: Expected move in dollars
            extra_strikes: Number of strikes outside expected move to include

        Returns:
            Filtered list of strikes
        """
        lower_bound = spot_price - expected_move
        upper_bound = spot_price + expected_move

        # Sort strikes by distance from bounds
        def in_range_priority(s):
            if lower_bound <= s.strike <= upper_bound:
                return 0
            elif s.strike < lower_bound:
                return lower_bound - s.strike
            else:
                return s.strike - upper_bound

        sorted_strikes = sorted(strikes, key=in_range_priority)

        # Get strikes within expected move
        in_range = [s for s in sorted_strikes if lower_bound <= s.strike <= upper_bound]

        # Get extra strikes outside
        outside_lower = sorted([s for s in strikes if s.strike < lower_bound],
                                key=lambda x: x.strike, reverse=True)[:extra_strikes]
        outside_upper = sorted([s for s in strikes if s.strike > upper_bound],
                                key=lambda x: x.strike)[:extra_strikes]

        # Combine and sort by strike
        all_strikes = in_range + outside_lower + outside_upper
        return sorted(all_strikes, key=lambda s: s.strike)

    def get_active_alerts(self) -> List[Dict]:
        """Get list of active (unacknowledged) alerts"""
        return [a.to_dict() for a in self.alerts]

    def get_gamma_snapshot(self, symbol: str = "SPY") -> Optional[Dict]:
        """
        Get the current gamma snapshot as a dictionary.

        This returns the most recently processed snapshot from process_options_chain().
        Returns None if no snapshot has been processed yet.

        Args:
            symbol: Symbol to get snapshot for (currently ignored, uses stored snapshot)

        Returns:
            Dict with gamma data including strikes, spot_price, gamma_regime, etc.
            None if no data available.
        """
        if self.previous_snapshot is None:
            return None

        # Convert to dict and add flip_point for backwards compatibility
        snapshot_dict = self.previous_snapshot.to_dict()

        # Add flip_point if not present (computed from magnets/structure)
        if 'flip_point' not in snapshot_dict:
            # Flip point is typically near the largest gamma magnitude strike
            strikes = snapshot_dict.get('strikes', [])
            if strikes:
                # Find the strike closest to spot with highest gamma
                spot = snapshot_dict.get('spot_price', 0)
                near_strikes = [s for s in strikes if abs(s.get('strike', 0) - spot) / spot < 0.02] if spot > 0 else strikes[:5]
                if near_strikes:
                    max_gamma_strike = max(near_strikes, key=lambda s: abs(s.get('net_gamma', 0)))
                    snapshot_dict['flip_point'] = max_gamma_strike.get('strike', spot)
                else:
                    snapshot_dict['flip_point'] = spot
            else:
                snapshot_dict['flip_point'] = snapshot_dict.get('spot_price', 0)

        return snapshot_dict

    def acknowledge_alert(self, alert_index: int) -> bool:
        """Acknowledge an alert by index"""
        if 0 <= alert_index < len(self.alerts):
            # In production, this would update the database
            return True
        return False

    # ==================== OPTIONS FLOW DIAGNOSTICS ====================
    # Trading Volatility-style analysis

    def calculate_options_flow_diagnostics(
        self,
        strikes: List[StrikeData],
        spot_price: float,
        expected_move: float = 0.0
    ) -> Dict:
        """
        Calculate Trading Volatility-style Options Flow Diagnostics.

        These metrics provide insight into:
        - Volume imbalance (call vs put pressure)
        - Position structure (hedging vs speculation)
        - Far-OTM "lotto" activity
        - IV skew indicators

        Args:
            strikes: List of StrikeData objects from options chain
            spot_price: Current spot price
            expected_move: Expected move in dollars (for OTM classification)

        Returns:
            Dict with 6 diagnostic cards + skew measures + overall rating
        """
        if not strikes or spot_price <= 0:
            return self._empty_flow_diagnostics()

        # Aggregate volume and OI
        total_call_volume = 0
        total_put_volume = 0
        total_call_oi = 0
        total_put_oi = 0

        # Far-OTM tracking (lotto = low delta, far from ATM)
        # Define far-OTM as > 1.5 expected moves from spot
        otm_threshold = expected_move * 1.5 if expected_move > 0 else spot_price * 0.02
        far_otm_call_volume = 0
        far_otm_put_volume = 0
        far_otm_call_oi = 0
        far_otm_put_oi = 0

        # Near-ATM tracking (within 1 expected move)
        near_atm_call_volume = 0
        near_atm_put_volume = 0

        # Bid/ask activity for structure classification
        total_call_bid_size = 0
        total_call_ask_size = 0
        total_put_bid_size = 0
        total_put_ask_size = 0

        # IV tracking for skew
        atm_call_iv = None
        atm_put_iv = None
        otm_call_ivs = []  # For 25-delta region
        otm_put_ivs = []

        atm_distance = float('inf')

        for s in strikes:
            strike = s.strike
            call_vol = s.call_volume
            put_vol = s.put_volume

            # Estimate OI from gamma if not available (gamma proportional to OI)
            # In real data, we'd have actual OI
            call_oi = getattr(s, 'call_oi', 0) or int(abs(s.call_gamma) * 10000)
            put_oi = getattr(s, 'put_oi', 0) or int(abs(s.put_gamma) * 10000)

            total_call_volume += call_vol
            total_put_volume += put_vol
            total_call_oi += call_oi
            total_put_oi += put_oi

            # Classify by moneyness
            distance_from_spot = strike - spot_price

            # Calls: far OTM if strike >> spot
            # Puts: far OTM if strike << spot
            is_far_otm_call = distance_from_spot > otm_threshold  # Deep OTM call
            is_far_otm_put = distance_from_spot < -otm_threshold  # Deep OTM put
            is_near_atm = abs(distance_from_spot) <= (expected_move if expected_move > 0 else spot_price * 0.01)

            if is_far_otm_call:
                far_otm_call_volume += call_vol
                far_otm_call_oi += call_oi
                if s.call_iv > 0:
                    otm_call_ivs.append(s.call_iv)

            if is_far_otm_put:
                far_otm_put_volume += put_vol
                far_otm_put_oi += put_oi
                if s.put_iv > 0:
                    otm_put_ivs.append(s.put_iv)

            if is_near_atm:
                near_atm_call_volume += call_vol
                near_atm_put_volume += put_vol

            # Track ATM strike for IV reference
            if abs(distance_from_spot) < atm_distance:
                atm_distance = abs(distance_from_spot)
                atm_call_iv = s.call_iv
                atm_put_iv = s.put_iv

            # Aggregate bid/ask sizes
            total_call_bid_size += s.call_bid_size
            total_call_ask_size += s.call_ask_size
            total_put_bid_size += s.put_bid_size
            total_put_ask_size += s.put_ask_size

        # Calculate diagnostic metrics
        total_volume = total_call_volume + total_put_volume
        total_oi = total_call_oi + total_put_oi

        # 1. CALL VS PUT VOLUME PRESSURE
        # Range: -1 (all puts) to +1 (all calls)
        if total_volume > 0:
            volume_pressure = (total_call_volume - total_put_volume) / total_volume
        else:
            volume_pressure = 0.0

        # Pressure interpretation
        if volume_pressure > 0.3:
            pressure_label = "Strong call pressure"
            pressure_description = "Call volume overwhelms put volume"
        elif volume_pressure > 0.1:
            pressure_label = "Call-leaning pressure"
            pressure_description = "Call volume exceeds put volume"
        elif volume_pressure < -0.3:
            pressure_label = "Strong put pressure"
            pressure_description = "Put volume overwhelms call volume"
        elif volume_pressure < -0.1:
            pressure_label = "Put-leaning pressure"
            pressure_description = "Put volume exceeds call volume"
        else:
            pressure_label = "Balanced flow"
            pressure_description = "Call and put volume roughly equal"

        # 2. SHORT-DTE DOMINANCE (using near-ATM as proxy for 0DTE activity)
        # Since we're looking at 0DTE chain, all is short-dated
        # But we can look at ATM vs OTM distribution
        if total_call_volume > 0:
            near_atm_call_share = (near_atm_call_volume / total_call_volume) * 100
        else:
            near_atm_call_share = 0.0

        if near_atm_call_share > 60:
            dte_label = "Short-dated call dominance"
            dte_description = "Near-term options activity is strongly call-dominated"
        elif near_atm_call_share > 40:
            dte_label = "Mixed ATM/OTM activity"
            dte_description = "Activity spread across near and far strikes"
        else:
            dte_label = "Far-strike dominated"
            dte_description = "Most activity is in far-from-ATM strikes"

        # 3. CALL SHARE OF OPTIONS FLOW
        if total_volume > 0:
            call_share = (total_call_volume / total_volume) * 100
        else:
            call_share = 50.0

        if call_share > 60:
            flow_label = "Call-leaning flow"
            flow_description = "Options activity tilts toward calls"
        elif call_share < 40:
            flow_label = "Put-leaning flow"
            flow_description = "Options activity tilts toward puts"
        else:
            flow_label = "Balanced flow"
            flow_description = "Options activity balanced between calls and puts"

        # 4. LOTTO TURNOVER VS OPEN INTEREST
        # Lotto = far OTM options (cheap, low delta, lottery tickets)
        lotto_volume = far_otm_call_volume + far_otm_put_volume
        lotto_oi = far_otm_call_oi + far_otm_put_oi

        if lotto_oi > 0:
            lotto_turnover = lotto_volume / lotto_oi
        else:
            lotto_turnover = 0.0

        if lotto_turnover > 0.5:
            lotto_label = "High lotto turnover"
            lotto_description = "Today's lotto volume is high vs existing open interest"
        elif lotto_turnover > 0.2:
            lotto_label = "Moderate lotto activity"
            lotto_description = "Average lotto activity relative to open interest"
        else:
            lotto_label = "Little new lotto activity"
            lotto_description = "Today's lotto call volume is small compared to existing lotto open interest"

        # 5. FAR-OTM CALL SHARE
        if total_call_volume > 0:
            far_otm_call_share = (far_otm_call_volume / total_call_volume) * 100
        else:
            far_otm_call_share = 0.0

        if far_otm_call_share > 30:
            otm_label = "Far-OTM heavy"
            otm_description = "Significant call volume is far out-of-the-money"
        elif far_otm_call_share < 10:
            otm_label = "Mostly near-ATM / structured"
            otm_description = "Most call volume is not far out-of-the-money"
        else:
            otm_label = "Mixed moneyness"
            otm_description = "Moderate mix of near-ATM and far-OTM activity"

        # 6. LOTTO SHARE OF CALL TAPE
        if total_call_volume > 0:
            lotto_call_share = (far_otm_call_volume / total_call_volume) * 100
        else:
            lotto_call_share = 0.0

        if lotto_call_share > 30:
            tape_label = "Lotto-heavy call tape"
            tape_description = "A large share of call volume is concentrated in low-delta calls"
        elif lotto_call_share > 15:
            tape_label = "Moderate lotto activity"
            tape_description = "Some call volume in far OTM strikes"
        else:
            tape_label = "Low lotto activity"
            tape_description = "Most call volume is in higher-delta strikes"

        # ==================== CALL STRUCTURE CLASSIFICATION ====================
        call_structure = self._classify_call_structure(
            total_call_volume=total_call_volume,
            total_put_volume=total_put_volume,
            total_call_bid_size=total_call_bid_size,
            total_call_ask_size=total_call_ask_size,
            far_otm_call_volume=far_otm_call_volume,
            near_atm_call_volume=near_atm_call_volume,
            total_call_oi=total_call_oi
        )

        # ==================== SKEW MEASURES ====================
        skew_measures = self._calculate_skew_measures(
            atm_call_iv=atm_call_iv,
            atm_put_iv=atm_put_iv,
            otm_call_ivs=otm_call_ivs,
            otm_put_ivs=otm_put_ivs
        )

        # ==================== OVERALL RATING ====================
        # Compute gamma-based signals for hybrid rating
        net_gex_value = self._estimate_net_gex(strikes, spot_price)

        # Determine price vs flip point
        price_above_flip = None
        if strikes:
            sorted_strikes = sorted(strikes, key=lambda s: s.strike)
            for i in range(len(sorted_strikes) - 1):
                curr = sorted_strikes[i]
                nxt = sorted_strikes[i + 1]
                if curr.net_gamma * nxt.net_gamma < 0:
                    ratio = abs(curr.net_gamma) / (abs(curr.net_gamma) + abs(nxt.net_gamma))
                    flip = curr.strike + ratio * (nxt.strike - curr.strike)
                    price_above_flip = spot_price > flip
                    break

        rating = self._calculate_flow_rating(
            volume_pressure=volume_pressure,
            call_share=call_share,
            skew_ratio=skew_measures.get('skew_ratio', 1.0),
            net_gex=net_gex_value,
            price_above_flip=price_above_flip
        )

        return {
            'diagnostics': [
                {
                    'id': 'volume_pressure',
                    'label': pressure_label,
                    'metric_name': 'CALL VS PUT VOLUME PRESSURE',
                    'metric_value': f"{volume_pressure:+.3f}",
                    'description': pressure_description,
                    'raw_value': round(volume_pressure, 4)
                },
                {
                    'id': 'short_dte_share',
                    'label': dte_label,
                    'metric_name': 'SHORT-DTE CALL SHARE',
                    'metric_value': f"{near_atm_call_share:.0f}%",
                    'description': dte_description,
                    'raw_value': round(near_atm_call_share, 1)
                },
                {
                    'id': 'call_share',
                    'label': flow_label,
                    'metric_name': 'CALL SHARE OF OPTIONS FLOW',
                    'metric_value': f"{call_share:.0f}%",
                    'description': flow_description,
                    'raw_value': round(call_share, 1)
                },
                {
                    'id': 'lotto_turnover',
                    'label': lotto_label,
                    'metric_name': 'LOTTO TURNOVER VS OPEN INTEREST',
                    'metric_value': f"{lotto_turnover:.2f}",
                    'description': lotto_description,
                    'raw_value': round(lotto_turnover, 3)
                },
                {
                    'id': 'far_otm_share',
                    'label': otm_label,
                    'metric_name': 'FAR-OTM CALL SHARE',
                    'metric_value': f"{far_otm_call_share:.0f}%",
                    'description': otm_description,
                    'raw_value': round(far_otm_call_share, 1)
                },
                {
                    'id': 'lotto_tape_share',
                    'label': tape_label,
                    'metric_name': 'LOTTO SHARE OF CALL TAPE',
                    'metric_value': f"{lotto_call_share:.0f}%",
                    'description': tape_description,
                    'raw_value': round(lotto_call_share, 1)
                }
            ],
            'call_structure': call_structure,
            'skew_measures': skew_measures,
            'rating': rating,
            'summary': {
                'total_call_volume': total_call_volume,
                'total_put_volume': total_put_volume,
                'total_volume': total_volume,
                'total_call_oi': total_call_oi,
                'total_put_oi': total_put_oi,
                'put_call_ratio': round(total_put_volume / total_call_volume, 3) if total_call_volume > 0 else 0,
                'net_gex': net_gex_value
            }
        }

    def _classify_call_structure(
        self,
        total_call_volume: int,
        total_put_volume: int,
        total_call_bid_size: int,
        total_call_ask_size: int,
        far_otm_call_volume: int,
        near_atm_call_volume: int,
        total_call_oi: int
    ) -> Dict:
        """
        Classify the call structure as Hedging, Overwrite, or Speculation.

        - Hedging: Protective puts dominate, calls used for portfolio protection
        - Overwrite (Covered Call): Call selling dominates (ask > bid), near-ATM focus
        - Speculation: Call buying dominates (bid > ask), far-OTM focus
        """
        # Call bid vs ask imbalance
        has_bid_ask_data = (total_call_bid_size + total_call_ask_size) > 0
        if has_bid_ask_data:
            call_buying_pressure = (total_call_bid_size - total_call_ask_size) / (total_call_bid_size + total_call_ask_size)
        else:
            call_buying_pressure = 0.0

        # Determine structure
        if total_call_volume == 0 and total_put_volume == 0:
            # No volume data at all (e.g., outside market hours)
            structure = "Data Unavailable"
            structure_description = "No volume data — market may be closed"
        elif total_put_volume > total_call_volume * 1.3:
            # Puts dominate - likely hedging activity
            structure = "Hedging / Protective"
            structure_description = "Put activity exceeds calls, suggesting portfolio protection"
        elif has_bid_ask_data and call_buying_pressure < -0.2 and near_atm_call_volume > far_otm_call_volume:
            # Sellers dominating near ATM - covered call writing
            structure = "Hedging / Overwrite"
            structure_description = "Call selling near ATM suggests covered call activity"
        elif has_bid_ask_data and call_buying_pressure > 0.2 and far_otm_call_volume > near_atm_call_volume * 0.5:
            # Buyers dominating far OTM - speculation
            structure = "Speculation / Directional"
            structure_description = "Aggressive call buying in far OTM strikes"
        elif has_bid_ask_data and call_buying_pressure > 0.1:
            # Moderate buying pressure
            structure = "Bullish / Accumulation"
            structure_description = "Net call buying suggests bullish positioning"
        elif not has_bid_ask_data and total_call_volume > total_put_volume * 1.3:
            # No bid/ask data but volume available — use volume-based classification
            structure = "Bullish / Call Dominant"
            structure_description = "Call volume exceeds put volume (bid/ask data unavailable)"
        else:
            # Balanced or neutral
            structure = "Balanced / Mixed"
            structure_description = "No clear directional bias in options flow"

        return {
            'structure': structure,
            'description': structure_description,
            'call_buying_pressure': round(call_buying_pressure, 3),
            'is_hedging': 'Hedging' in structure,
            'is_overwrite': 'Overwrite' in structure,
            'is_speculation': 'Speculation' in structure
        }

    def _calculate_skew_measures(
        self,
        atm_call_iv: Optional[float],
        atm_put_iv: Optional[float],
        otm_call_ivs: List[float],
        otm_put_ivs: List[float]
    ) -> Dict:
        """
        Calculate IV skew measures similar to Trading Volatility.

        - Skew Ratio: 25-delta put IV / 25-delta call IV
          Values > 1 indicate stronger downside hedging demand
          Values < 1 indicate call-side skew (bullish)

        - Call Skew: Difference in delta between OTM calls and puts
          Positive = call-side demand
        """
        # Skew ratio: put IV / call IV
        # Using ATM as proxy if 25-delta not available
        skew_ratio = 1.0
        skew_description = "Normal skew"

        if atm_put_iv and atm_call_iv and atm_call_iv > 0:
            skew_ratio = atm_put_iv / atm_call_iv

            if skew_ratio > 1.1:
                skew_description = "Put skew (bearish hedging demand)"
            elif skew_ratio < 0.9:
                skew_description = "Call skew (bullish sentiment)"
            else:
                skew_description = "Normal skew"

        # Call Skew: Average OTM call IV - Average OTM put IV
        # Positive = calls more expensive (bullish demand)
        call_skew = 0.0
        call_skew_description = "Neutral"

        avg_otm_call_iv = sum(otm_call_ivs) / len(otm_call_ivs) if otm_call_ivs else 0
        avg_otm_put_iv = sum(otm_put_ivs) / len(otm_put_ivs) if otm_put_ivs else 0

        if avg_otm_call_iv > 0 and avg_otm_put_iv > 0:
            # Express as percentage points difference
            call_skew = (avg_otm_call_iv - avg_otm_put_iv) * 100

            if call_skew > 5:
                call_skew_description = "Strong call-side demand"
            elif call_skew > 2:
                call_skew_description = "Moderate call-side demand"
            elif call_skew < -5:
                call_skew_description = "Strong put-side demand"
            elif call_skew < -2:
                call_skew_description = "Moderate put-side demand"
            else:
                call_skew_description = "Balanced IV across strikes"

        return {
            'skew_ratio': round(skew_ratio, 3),
            'skew_ratio_description': skew_description,
            'call_skew': round(call_skew, 2),
            'call_skew_description': call_skew_description,
            'atm_call_iv': round(atm_call_iv * 100, 1) if atm_call_iv else None,
            'atm_put_iv': round(atm_put_iv * 100, 1) if atm_put_iv else None,
            'avg_otm_call_iv': round(avg_otm_call_iv * 100, 1) if avg_otm_call_iv else None,
            'avg_otm_put_iv': round(avg_otm_put_iv * 100, 1) if avg_otm_put_iv else None
        }

    def _calculate_flow_rating(
        self,
        volume_pressure: float,
        call_share: float,
        skew_ratio: float,
        net_gex: float = 0.0,
        price_above_flip: Optional[bool] = None
    ) -> Dict:
        """
        Calculate overall rating (BULLISH / BEARISH / NEUTRAL).

        Combines flow-based AND gamma-based signals:
        - Volume pressure direction
        - Call vs put share
        - IV skew bias
        - Net GEX direction (positive = bullish dealer positioning)
        - Price vs GEX flip point (above = positive gamma territory)
        """
        bullish_score = 0
        bearish_score = 0

        # Volume pressure (flow-based)
        if volume_pressure > 0.2:
            bullish_score += 2
        elif volume_pressure > 0.05:
            bullish_score += 1
        elif volume_pressure < -0.2:
            bearish_score += 2
        elif volume_pressure < -0.05:
            bearish_score += 1

        # Call share (flow-based)
        if call_share > 60:
            bullish_score += 1
        elif call_share < 40:
            bearish_score += 1

        # Skew (inverted - low skew = bullish)
        if skew_ratio < 0.95:
            bullish_score += 1
        elif skew_ratio > 1.05:
            bearish_score += 1

        # Net GEX direction (gamma-based) — positive GEX = dealers long gamma = supportive
        if net_gex > 0.5:
            bullish_score += 1
        elif net_gex < -0.5:
            bearish_score += 1

        # Price vs GEX flip (gamma-based) — above flip = positive gamma territory
        if price_above_flip is True:
            bullish_score += 1
        elif price_above_flip is False:
            bearish_score += 1

        # Determine rating
        net_score = bullish_score - bearish_score

        if net_score >= 3:
            rating = "BULLISH"
            confidence = "HIGH"
        elif net_score >= 1:
            rating = "BULLISH"
            confidence = "MODERATE"
        elif net_score <= -3:
            rating = "BEARISH"
            confidence = "HIGH"
        elif net_score <= -1:
            rating = "BEARISH"
            confidence = "MODERATE"
        else:
            rating = "NEUTRAL"
            confidence = "LOW"

        return {
            'rating': rating,
            'confidence': confidence,
            'bullish_score': bullish_score,
            'bearish_score': bearish_score,
            'net_score': net_score
        }

    def _estimate_net_gex(self, strikes: List[StrikeData], spot_price: float) -> float:
        """
        Estimate total Net GEX from all strikes.

        GEX = Gamma × OI × 100 × Spot²
        Net GEX = Call GEX - Put GEX

        Positive Net GEX = market maker long gamma = mean reversion
        Negative Net GEX = market maker short gamma = trending/volatile
        """
        total_gex = 0.0

        for s in strikes:
            # Estimate OI from gamma magnitude if not available
            call_oi = getattr(s, 'call_oi', 0) or max(1, int(abs(s.call_gamma) * 10000))
            put_oi = getattr(s, 'put_oi', 0) or max(1, int(abs(s.put_gamma) * 10000))

            # GEX formula
            call_gex = s.call_gamma * call_oi * 100 * (spot_price ** 2)
            put_gex = s.put_gamma * put_oi * 100 * (spot_price ** 2)

            # Net = Call - Put (puts have negative effect on dealer positioning)
            total_gex += (call_gex - put_gex)

        # Return in millions
        return round(total_gex / 1e6, 2)

    def _empty_flow_diagnostics(self) -> Dict:
        """Return empty diagnostics when data unavailable."""
        return {
            'diagnostics': [],
            'call_structure': {
                'structure': 'Unknown',
                'description': 'No data available',
                'call_buying_pressure': 0,
                'is_hedging': False,
                'is_overwrite': False,
                'is_speculation': False
            },
            'skew_measures': {
                'skew_ratio': 1.0,
                'skew_ratio_description': 'No data',
                'call_skew': 0.0,
                'call_skew_description': 'No data',
                'atm_call_iv': None,
                'atm_put_iv': None,
                'avg_otm_call_iv': None,
                'avg_otm_put_iv': None
            },
            'rating': {
                'rating': 'NEUTRAL',
                'confidence': 'LOW',
                'bullish_score': 0,
                'bearish_score': 0,
                'net_score': 0
            },
            'summary': {
                'total_call_volume': 0,
                'total_put_volume': 0,
                'total_volume': 0,
                'total_call_oi': 0,
                'total_put_oi': 0,
                'put_call_ratio': 0,
                'net_gex': 0
            }
        }


# Singleton instance
_watchtower_engine: Optional[WatchtowerEngine] = None


def get_watchtower_engine() -> WatchtowerEngine:
    """Get or create the singleton WATCHTOWER engine instance"""
    global _watchtower_engine
    if _watchtower_engine is None:
        _watchtower_engine = WatchtowerEngine()
    return _watchtower_engine


def initialize_watchtower_engine() -> WatchtowerEngine:
    """
    Initialize WATCHTOWER engine with eager loading of ML models.
    Call this at application startup to avoid cold-start latency.
    """
    engine = get_watchtower_engine()
    # Eagerly load ML models to avoid first-request delay
    engine._get_ml_models()
    logger.info("WATCHTOWER engine initialized with ML models pre-loaded")
    return engine
