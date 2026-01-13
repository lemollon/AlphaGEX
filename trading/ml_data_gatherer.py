"""
ML Data Gatherer - Centralized Collection of All ML Analyses for Scan Activity
===============================================================================

This module collects data from all ML systems in a single call, making it easy
for bots (ARES, ATHENA, etc.) to log comprehensive ML context with each scan.

Systems Gathered:
- Quant ML Advisor (ARES-specific ML feedback loop)
- ML Regime Classifier (market regime prediction)
- GEX Directional ML (direction prediction from GEX)
- Ensemble Strategy (weighted combination of signals)
- Volatility Regime (from psychology trap detector)
- Psychology Patterns (Liberation, False Floor, Forward Magnets)
- Monte Carlo Kelly (position sizing)
- ARGUS Pattern Analysis (pattern similarity)
- IV Context (IV rank, percentile, ratios)
- Time Context (day of week, OPEX timing, economic events)
- Recent Performance (win rates, streaks, P&L)
- ML Consensus & Conflict Detection

Author: AlphaGEX
Date: 2025-01
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Import ML systems with fallbacks
try:
    from quant.ares_ml_advisor import AresMLAdvisor, TradingAdvice
    ARES_ML_AVAILABLE = True
except ImportError as e:
    ARES_ML_AVAILABLE = False
    logger.debug(f"AresMLAdvisor not available: {e}")

try:
    from quant.ml_regime_classifier import get_ml_classifier, MLRegimeAction
    ML_REGIME_AVAILABLE = True
except ImportError as e:
    ML_REGIME_AVAILABLE = False
    logger.debug(f"MLRegimeClassifier not available: {e}")

try:
    from quant.gex_directional_ml import GEXDirectionalPredictor
    GEX_ML_AVAILABLE = True
except ImportError as e:
    GEX_ML_AVAILABLE = False
    GEXDirectionalPredictor = None
    logger.debug(f"GEXDirectionalPredictor not available: {e}")

try:
    from quant.ensemble_strategy import get_ensemble_signal
    ENSEMBLE_AVAILABLE = True
except ImportError as e:
    ENSEMBLE_AVAILABLE = False
    logger.debug(f"EnsembleStrategy not available: {e}")

try:
    from quant.monte_carlo_kelly import MonteCarloKelly
    KELLY_AVAILABLE = True
except ImportError as e:
    KELLY_AVAILABLE = False
    logger.debug(f"MonteCarloKelly not available: {e}")

try:
    from core.psychology_trap_detector import PsychologyTrapDetector
    PSYCHOLOGY_AVAILABLE = True
except ImportError as e:
    PSYCHOLOGY_AVAILABLE = False
    logger.debug(f"PsychologyTrapDetector not available: {e}")

try:
    from gamma.argus_pattern_similarity import get_argus_analyzer
    ARGUS_AVAILABLE = True
except ImportError as e:
    ARGUS_AVAILABLE = False
    logger.debug(f"ARGUS not available: {e}")

try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


@dataclass
class MLDataBundle:
    """
    Complete bundle of ML data for scan activity logging.
    All fields match the scan_activity_logger parameters.
    """
    # Quant ML Advisor
    quant_ml_advice: str = ""
    quant_ml_win_probability: float = 0
    quant_ml_confidence: float = 0
    quant_ml_suggested_risk_pct: float = 0
    quant_ml_suggested_sd_multiplier: float = 0
    quant_ml_top_factors: Optional[List[Dict]] = None
    quant_ml_model_version: str = ""

    # ML Regime Classifier
    regime_predicted_action: str = ""
    regime_confidence: float = 0
    regime_probabilities: Optional[Dict] = None
    regime_feature_importance: Optional[Dict] = None
    regime_model_version: str = ""

    # GEX Directional ML
    gex_ml_direction: str = ""
    gex_ml_confidence: float = 0
    gex_ml_probabilities: Optional[Dict] = None
    gex_ml_features_used: Optional[Dict] = None

    # Ensemble Strategy
    ensemble_signal: str = ""
    ensemble_confidence: float = 0
    ensemble_bullish_weight: float = 0
    ensemble_bearish_weight: float = 0
    ensemble_neutral_weight: float = 0
    ensemble_should_trade: bool = False
    ensemble_position_size_multiplier: float = 0
    ensemble_component_signals: Optional[List[Dict]] = None
    ensemble_reasoning: str = ""

    # Volatility Regime
    volatility_regime: str = ""
    volatility_risk_level: str = ""
    volatility_description: str = ""
    at_flip_point: bool = False
    flip_point: float = 0
    flip_point_distance_pct: float = 0

    # Psychology Patterns
    psychology_pattern: str = ""
    liberation_setup: bool = False
    false_floor_detected: bool = False
    forward_magnets: Optional[List[Dict]] = None

    # Monte Carlo Kelly
    kelly_optimal: float = 0
    kelly_safe: float = 0
    kelly_conservative: float = 0
    kelly_prob_ruin: float = 0
    kelly_recommendation: str = ""

    # ARGUS Pattern Analysis
    argus_pattern_match: str = ""
    argus_similarity_score: float = 0
    argus_historical_outcome: str = ""
    argus_roc_value: float = 0
    argus_roc_signal: str = ""

    # IV Context
    iv_rank: float = 0
    iv_percentile: float = 0
    iv_hv_ratio: float = 0
    iv_30d: float = 0
    hv_30d: float = 0

    # Time Context
    day_of_week: str = ""
    day_of_week_num: int = 0
    time_of_day: str = ""
    hour_ct: int = 0
    minute_ct: int = 0
    days_to_monthly_opex: int = 0
    days_to_weekly_opex: int = 0
    is_opex_week: bool = False
    is_fomc_day: bool = False
    is_cpi_day: bool = False

    # Recent Performance Context
    similar_setup_win_rate: float = 0
    similar_setup_count: int = 0
    similar_setup_avg_pnl: float = 0
    current_streak: int = 0
    streak_type: str = ""
    last_5_trades_win_rate: float = 0
    last_10_trades_win_rate: float = 0
    daily_pnl: float = 0
    weekly_pnl: float = 0

    # ML Consensus & Conflict Detection
    ml_consensus: str = ""
    ml_consensus_score: float = 0
    ml_systems_agree: int = 0
    ml_systems_total: int = 0
    ml_conflicts: Optional[List[Dict]] = None
    ml_conflict_severity: str = ""
    ml_highest_confidence_system: str = ""
    ml_highest_confidence_value: float = 0

    def to_kwargs(self) -> Dict[str, Any]:
        """Convert to kwargs dict for log_scan_activity()"""
        def convert_numpy_types(obj):
            """Recursively convert numpy types to Python native types"""
            import numpy as np
            if isinstance(obj, dict):
                return {k: convert_numpy_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            elif isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        return convert_numpy_types(asdict(self))


class MLDataGatherer:
    """
    Gathers all ML data for scan activity logging.

    Usage:
        gatherer = MLDataGatherer()
        ml_data = gatherer.gather_all(
            symbol="SPY",
            spot_price=585.50,
            vix=15.5,
            gex_data={'net_gex': 1.5e9, ...},
            bot_name="ARES"
        )
        # ml_data.to_kwargs() returns all fields ready for log_scan_activity()
    """

    def __init__(self):
        self._ares_advisor = None
        self._regime_classifier = None
        self._gex_ml = None
        self._kelly_calculator = None
        self._psychology_detector = None
        self._argus_analyzer = None

    def gather_all(
        self,
        symbol: str = "SPY",
        spot_price: float = 0,
        vix: float = 0,
        gex_data: Optional[Dict] = None,
        market_data: Optional[Dict] = None,
        bot_name: str = "ARES",
        win_rate: float = 0.70,
        avg_win: float = 150,
        avg_loss: float = 350,
    ) -> MLDataBundle:
        """
        Gather all ML data in a single call.

        Args:
            symbol: Trading symbol (SPY, SPX, etc.)
            spot_price: Current underlying price
            vix: Current VIX value
            gex_data: GEX data dict with net_gex, call_wall, put_wall, flip_point, etc.
            market_data: Additional market data for ML features
            bot_name: Name of the calling bot (for performance lookup)
            win_rate: Historical win rate for Kelly calculation
            avg_win: Average winning trade P&L
            avg_loss: Average losing trade P&L

        Returns:
            MLDataBundle with all ML analyses populated
        """
        bundle = MLDataBundle()
        gex_data = gex_data or {}
        market_data = market_data or {}

        # Gather each component (catch exceptions individually)
        self._gather_quant_ml(bundle, symbol, spot_price, vix, gex_data)
        self._gather_regime_classifier(bundle, symbol, spot_price, vix, gex_data)
        self._gather_gex_ml(bundle, symbol, spot_price, vix, gex_data)
        self._gather_ensemble(bundle, symbol, spot_price, vix, gex_data)
        self._gather_volatility_regime(bundle, spot_price, vix, gex_data)
        self._gather_psychology(bundle, symbol, spot_price, gex_data)
        self._gather_kelly(bundle, win_rate, avg_win, avg_loss)
        self._gather_argus(bundle, symbol, spot_price, gex_data)
        self._gather_iv_context(bundle, vix, market_data)
        self._gather_time_context(bundle)
        self._gather_recent_performance(bundle, bot_name)
        self._compute_consensus(bundle)

        return bundle

    def _gather_quant_ml(
        self,
        bundle: MLDataBundle,
        symbol: str,
        spot_price: float,
        vix: float,
        gex_data: Dict
    ):
        """Gather Quant ML Advisor data"""
        if not ARES_ML_AVAILABLE:
            return

        try:
            if self._ares_advisor is None:
                self._ares_advisor = AresMLAdvisor(symbol=symbol)

            # Build features for prediction
            features = {
                'vix': vix,
                'spot_price': spot_price,
                'net_gex': gex_data.get('net_gex', 0),
                'call_wall': gex_data.get('call_wall', 0),
                'put_wall': gex_data.get('put_wall', 0),
            }

            result = self._ares_advisor.predict(features)
            if result:
                bundle.quant_ml_advice = result.advice.value if hasattr(result.advice, 'value') else str(result.advice)
                bundle.quant_ml_win_probability = getattr(result, 'win_probability', 0)
                bundle.quant_ml_confidence = getattr(result, 'confidence', 0)
                bundle.quant_ml_suggested_risk_pct = getattr(result, 'suggested_risk_pct', 0)
                bundle.quant_ml_suggested_sd_multiplier = getattr(result, 'suggested_sd_multiplier', 0)
                bundle.quant_ml_top_factors = getattr(result, 'top_factors', None)
                bundle.quant_ml_model_version = getattr(result, 'model_version', '')
        except Exception as e:
            logger.debug(f"Quant ML gather failed: {e}")

    def _gather_regime_classifier(
        self,
        bundle: MLDataBundle,
        symbol: str,
        spot_price: float,
        vix: float,
        gex_data: Dict
    ):
        """Gather ML Regime Classifier data"""
        if not ML_REGIME_AVAILABLE:
            return

        try:
            classifier = get_ml_classifier(symbol)

            # Build features
            features = {
                'vix': vix,
                'spot_price': spot_price,
                'net_gex': gex_data.get('net_gex', 0),
                'call_wall': gex_data.get('call_wall', 0),
                'put_wall': gex_data.get('put_wall', 0),
                'flip_point': gex_data.get('flip_point', 0),
            }

            result = classifier.predict(features)
            if result:
                bundle.regime_predicted_action = result.predicted_action.value if hasattr(result.predicted_action, 'value') else str(result.predicted_action)
                bundle.regime_confidence = result.confidence
                bundle.regime_probabilities = result.probabilities
                bundle.regime_feature_importance = result.feature_importance
                bundle.regime_model_version = result.model_version
        except Exception as e:
            logger.debug(f"Regime classifier gather failed: {e}")

    def _gather_gex_ml(
        self,
        bundle: MLDataBundle,
        symbol: str,
        spot_price: float,
        vix: float,
        gex_data: Dict
    ):
        """Gather GEX Directional ML data"""
        if not GEX_ML_AVAILABLE or GEXDirectionalPredictor is None:
            return

        try:
            if self._gex_ml is None:
                self._gex_ml = GEXDirectionalPredictor(ticker=symbol)
                # Try to load from database (trained model persisted across deploys)
                if hasattr(self._gex_ml, 'load_from_db'):
                    try:
                        if self._gex_ml.load_from_db():
                            logger.debug("MLDataGatherer: GEX Directional ML loaded from database")
                        else:
                            logger.debug("MLDataGatherer: GEX Directional ML not found in database")
                            return  # No model to predict with
                    except Exception as load_err:
                        logger.debug(f"MLDataGatherer: Failed to load GEX ML from DB: {load_err}")
                        return

            # Check if model is trained
            if not getattr(self._gex_ml, 'is_trained', False) and self._gex_ml.model is None:
                return  # No trained model

            features = {
                'vix': vix,
                'spot_price': spot_price,
                'net_gex': gex_data.get('net_gex', 0),
                'call_wall': gex_data.get('call_wall', 0),
                'put_wall': gex_data.get('put_wall', 0),
                'flip_point': gex_data.get('flip_point', 0),
            }

            result = self._gex_ml.predict(features)
            if result:
                bundle.gex_ml_direction = getattr(result, 'direction', '') or getattr(result, 'predicted_direction', '')
                if hasattr(bundle.gex_ml_direction, 'value'):
                    bundle.gex_ml_direction = bundle.gex_ml_direction.value
                bundle.gex_ml_confidence = getattr(result, 'confidence', 0)
                bundle.gex_ml_probabilities = getattr(result, 'probabilities', None)
                bundle.gex_ml_features_used = getattr(result, 'feature_importance', None) or getattr(result, 'features_used', None)
        except Exception as e:
            logger.debug(f"GEX ML gather failed: {e}")

    def _gather_ensemble(
        self,
        bundle: MLDataBundle,
        symbol: str,
        spot_price: float,
        vix: float,
        gex_data: Dict
    ):
        """Gather Ensemble Strategy data"""
        if not ENSEMBLE_AVAILABLE:
            return

        try:
            result = get_ensemble_signal(
                symbol=symbol,
                spot_price=spot_price,
                vix=vix,
                net_gex=gex_data.get('net_gex', 0),
                call_wall=gex_data.get('call_wall', 0),
                put_wall=gex_data.get('put_wall', 0),
            )
            if result:
                bundle.ensemble_signal = getattr(result, 'signal', '') or getattr(result, 'final_signal', '')
                if hasattr(bundle.ensemble_signal, 'value'):
                    bundle.ensemble_signal = bundle.ensemble_signal.value
                bundle.ensemble_confidence = getattr(result, 'confidence', 0)
                bundle.ensemble_bullish_weight = getattr(result, 'bullish_weight', 0)
                bundle.ensemble_bearish_weight = getattr(result, 'bearish_weight', 0)
                bundle.ensemble_neutral_weight = getattr(result, 'neutral_weight', 0)
                bundle.ensemble_should_trade = getattr(result, 'should_trade', False)
                bundle.ensemble_position_size_multiplier = getattr(result, 'position_size_multiplier', 1.0)
                bundle.ensemble_component_signals = getattr(result, 'component_signals', None)
                bundle.ensemble_reasoning = getattr(result, 'reasoning', '')
        except Exception as e:
            logger.debug(f"Ensemble gather failed: {e}")

    def _gather_volatility_regime(
        self,
        bundle: MLDataBundle,
        spot_price: float,
        vix: float,
        gex_data: Dict
    ):
        """Gather volatility regime data"""
        try:
            # Determine volatility regime from VIX and GEX
            net_gex = gex_data.get('net_gex', 0)
            flip_point = gex_data.get('flip_point', 0)

            # Calculate flip point distance
            if flip_point and spot_price:
                bundle.flip_point = flip_point
                bundle.flip_point_distance_pct = ((spot_price - flip_point) / flip_point) * 100 if flip_point else 0
                bundle.at_flip_point = abs(bundle.flip_point_distance_pct) < 0.5  # Within 0.5%

            # Determine regime based on VIX and GEX
            if vix > 30:
                bundle.volatility_regime = "EXTREME_VOLATILITY"
                bundle.volatility_risk_level = "extreme"
                bundle.volatility_description = f"VIX at {vix:.1f} - extreme volatility conditions"
            elif vix > 25:
                bundle.volatility_regime = "HIGH_VOLATILITY"
                bundle.volatility_risk_level = "high"
                bundle.volatility_description = f"VIX at {vix:.1f} - elevated volatility"
            elif net_gex and net_gex < -1e9:
                bundle.volatility_regime = "NEGATIVE_GAMMA_RISK"
                bundle.volatility_risk_level = "high"
                bundle.volatility_description = f"Negative GEX ({net_gex/1e9:.2f}B) - expect amplified moves"
            elif net_gex and net_gex > 2e9:
                bundle.volatility_regime = "POSITIVE_GAMMA_SUPPORT"
                bundle.volatility_risk_level = "low"
                bundle.volatility_description = f"Strong positive GEX ({net_gex/1e9:.2f}B) - dealer support"
            elif vix < 15:
                bundle.volatility_regime = "LOW_VOLATILITY"
                bundle.volatility_risk_level = "low"
                bundle.volatility_description = f"VIX at {vix:.1f} - calm market conditions"
            else:
                bundle.volatility_regime = "NORMAL"
                bundle.volatility_risk_level = "medium"
                bundle.volatility_description = f"VIX at {vix:.1f} - normal conditions"
        except Exception as e:
            logger.debug(f"Volatility regime gather failed: {e}")

    def _gather_psychology(
        self,
        bundle: MLDataBundle,
        symbol: str,
        spot_price: float,
        gex_data: Dict
    ):
        """Gather psychology pattern data"""
        if not PSYCHOLOGY_AVAILABLE:
            return

        try:
            if self._psychology_detector is None:
                self._psychology_detector = PsychologyTrapDetector()

            result = self._psychology_detector.analyze(
                symbol=symbol,
                spot_price=spot_price,
                gex_data=gex_data
            )
            if result:
                bundle.liberation_setup = getattr(result, 'liberation_setup_detected', False)
                bundle.false_floor_detected = getattr(result, 'false_floor_detected', False)
                bundle.forward_magnets = getattr(result, 'forward_magnets', None)

                # Build pattern description
                patterns = []
                if bundle.liberation_setup:
                    patterns.append("Liberation Setup")
                if bundle.false_floor_detected:
                    patterns.append("False Floor")
                if bundle.forward_magnets:
                    patterns.append(f"Forward Magnets ({len(bundle.forward_magnets)})")
                bundle.psychology_pattern = ", ".join(patterns) if patterns else "None"
        except Exception as e:
            logger.debug(f"Psychology gather failed: {e}")

    def _gather_kelly(
        self,
        bundle: MLDataBundle,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ):
        """Gather Monte Carlo Kelly data"""
        if not KELLY_AVAILABLE:
            return

        try:
            if self._kelly_calculator is None:
                self._kelly_calculator = MonteCarloKelly()

            result = self._kelly_calculator.calculate_kelly(
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss
            )
            if result:
                bundle.kelly_optimal = getattr(result, 'kelly_optimal', 0) or getattr(result, 'optimal_kelly', 0)
                bundle.kelly_safe = getattr(result, 'kelly_safe', 0) or getattr(result, 'half_kelly', 0)
                bundle.kelly_conservative = getattr(result, 'kelly_conservative', 0) or getattr(result, 'quarter_kelly', 0)
                bundle.kelly_prob_ruin = getattr(result, 'prob_ruin', 0) or getattr(result, 'probability_of_ruin', 0)
                bundle.kelly_recommendation = getattr(result, 'recommendation', '')
        except Exception as e:
            logger.debug(f"Kelly gather failed: {e}")

    def _gather_argus(
        self,
        bundle: MLDataBundle,
        symbol: str,
        spot_price: float,
        gex_data: Dict
    ):
        """Gather ARGUS pattern analysis data"""
        if not ARGUS_AVAILABLE:
            return

        try:
            if self._argus_analyzer is None:
                self._argus_analyzer = get_argus_analyzer()

            result = self._argus_analyzer.find_similar_patterns(
                symbol=symbol,
                spot_price=spot_price,
                gex_data=gex_data
            )
            if result:
                bundle.argus_pattern_match = getattr(result, 'pattern_name', '') or getattr(result, 'best_match', '')
                bundle.argus_similarity_score = getattr(result, 'similarity_score', 0) or getattr(result, 'score', 0)
                bundle.argus_historical_outcome = getattr(result, 'historical_outcome', '')
                bundle.argus_roc_value = getattr(result, 'roc_value', 0)
                bundle.argus_roc_signal = getattr(result, 'roc_signal', '')
        except Exception as e:
            logger.debug(f"ARGUS gather failed: {e}")

    def _gather_iv_context(
        self,
        bundle: MLDataBundle,
        vix: float,
        market_data: Dict
    ):
        """Gather IV context data"""
        try:
            # Use VIX as proxy for IV if not provided
            bundle.iv_30d = market_data.get('iv_30d', vix)
            bundle.hv_30d = market_data.get('hv_30d', 0)

            # Calculate IV rank and percentile from market_data or estimate from VIX
            bundle.iv_rank = market_data.get('iv_rank', 0)
            bundle.iv_percentile = market_data.get('iv_percentile', 0)

            # If not provided, estimate from VIX
            if bundle.iv_rank == 0 and vix > 0:
                # Rough estimate: VIX 12-35 range maps to 0-100 rank
                bundle.iv_rank = min(100, max(0, ((vix - 12) / 23) * 100))
                bundle.iv_percentile = bundle.iv_rank

            # Calculate IV/HV ratio if we have both
            if bundle.iv_30d and bundle.hv_30d:
                bundle.iv_hv_ratio = bundle.iv_30d / bundle.hv_30d
            elif vix > 0:
                # Use VIX as proxy, typical HV around 15
                bundle.iv_hv_ratio = vix / 15.0
        except Exception as e:
            logger.debug(f"IV context gather failed: {e}")

    def _gather_time_context(self, bundle: MLDataBundle):
        """Gather time context data"""
        try:
            import pytz
            ct = pytz.timezone('America/Chicago')
            now = datetime.now(ct)

            bundle.day_of_week = now.strftime('%A')
            bundle.day_of_week_num = now.weekday()
            bundle.hour_ct = now.hour
            bundle.minute_ct = now.minute

            # Time of day classification
            if now.hour < 10:
                bundle.time_of_day = "morning"
            elif now.hour < 13:
                bundle.time_of_day = "midday"
            else:
                bundle.time_of_day = "afternoon"

            # Calculate days to OPEX
            # Monthly OPEX is 3rd Friday of the month
            bundle.days_to_monthly_opex = self._days_to_monthly_opex(now)
            bundle.days_to_weekly_opex = self._days_to_weekly_opex(now)
            bundle.is_opex_week = bundle.days_to_monthly_opex <= 5

            # Check for economic events (simplified)
            bundle.is_fomc_day = self._is_fomc_day(now)
            bundle.is_cpi_day = self._is_cpi_day(now)
        except Exception as e:
            logger.debug(f"Time context gather failed: {e}")

    def _days_to_monthly_opex(self, now: datetime) -> int:
        """Calculate days until monthly options expiration (3rd Friday)"""
        try:
            year, month = now.year, now.month

            # Find 3rd Friday of current month
            first_day = datetime(year, month, 1, tzinfo=now.tzinfo)
            first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
            third_friday = first_friday + timedelta(weeks=2)

            # If past this month's OPEX, calculate next month's
            if now.date() > third_friday.date():
                if month == 12:
                    year += 1
                    month = 1
                else:
                    month += 1
                first_day = datetime(year, month, 1, tzinfo=now.tzinfo)
                first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
                third_friday = first_friday + timedelta(weeks=2)

            return (third_friday.date() - now.date()).days
        except Exception:
            return 0

    def _days_to_weekly_opex(self, now: datetime) -> int:
        """Calculate days until weekly expiration (Friday)"""
        try:
            days_until_friday = (4 - now.weekday()) % 7
            return days_until_friday if days_until_friday > 0 else 7
        except Exception:
            return 0

    def _is_fomc_day(self, now: datetime) -> bool:
        """Check if today is an FOMC announcement day (simplified)"""
        # FOMC meets 8 times per year, announcements at 2pm ET on Wednesdays
        # This is a simplified check - in production, use a calendar API
        return now.weekday() == 2  # Wednesday - very rough approximation

    def _is_cpi_day(self, now: datetime) -> bool:
        """Check if today is a CPI release day (simplified)"""
        # CPI typically released around 10th-15th of month at 8:30am ET
        return 10 <= now.day <= 15 and now.hour < 10

    def _gather_recent_performance(self, bundle: MLDataBundle, bot_name: str):
        """Gather recent performance context from trade history.

        CRITICAL: Uses finally block to prevent connection leaks.
        This function is called on EVERY scan, so leaks here cause
        pool exhaustion over time (the 6:05 AM stoppage root cause).
        """
        if not DB_AVAILABLE:
            return

        conn = None  # Initialize to prevent NameError in finally block
        try:
            conn = get_connection()
            c = conn.cursor()

            # Get recent closed trades for this bot
            c.execute("""
                SELECT pnl, closed_at
                FROM autonomous_closed_trades
                WHERE bot_name = %s
                AND closed_at > NOW() - INTERVAL '30 days'
                ORDER BY closed_at DESC
                LIMIT 20
            """, (bot_name,))

            trades = c.fetchall()

            if trades:
                pnls = [float(t[0]) for t in trades if t[0] is not None]

                if pnls:
                    # Calculate win rates
                    wins = sum(1 for p in pnls if p > 0)
                    bundle.last_5_trades_win_rate = sum(1 for p in pnls[:5] if p > 0) / min(5, len(pnls))
                    bundle.last_10_trades_win_rate = sum(1 for p in pnls[:10] if p > 0) / min(10, len(pnls))

                    # Calculate streak
                    streak = 0
                    if pnls:
                        current_sign = pnls[0] > 0
                        for p in pnls:
                            if (p > 0) == current_sign:
                                streak += 1
                            else:
                                break
                        bundle.current_streak = streak if current_sign else -streak
                        bundle.streak_type = "WIN" if current_sign else "LOSS"

            # Get daily and weekly P&L
            c.execute("""
                SELECT COALESCE(SUM(pnl), 0)
                FROM autonomous_closed_trades
                WHERE bot_name = %s
                AND DATE(closed_at) = CURRENT_DATE
            """, (bot_name,))
            result = c.fetchone()
            bundle.daily_pnl = float(result[0]) if result and result[0] else 0

            c.execute("""
                SELECT COALESCE(SUM(pnl), 0)
                FROM autonomous_closed_trades
                WHERE bot_name = %s
                AND closed_at > NOW() - INTERVAL '7 days'
            """, (bot_name,))
            result = c.fetchone()
            bundle.weekly_pnl = float(result[0]) if result and result[0] else 0

        except Exception as e:
            logger.debug(f"Recent performance gather failed: {e}")
        finally:
            # CRITICAL: Always close connection to prevent pool exhaustion
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    def _compute_consensus(self, bundle: MLDataBundle):
        """Compute ML consensus and detect conflicts"""
        try:
            signals = []

            # Map each ML system's output to bullish/bearish/neutral
            if bundle.quant_ml_advice:
                if bundle.quant_ml_advice in ['TRADE_FULL', 'TRADE_REDUCED']:
                    signals.append({
                        'system': 'Quant ML',
                        'signal': 'BULLISH',  # Trading = bullish on strategy
                        'confidence': bundle.quant_ml_confidence
                    })
                else:
                    signals.append({
                        'system': 'Quant ML',
                        'signal': 'NEUTRAL',
                        'confidence': bundle.quant_ml_confidence
                    })

            if bundle.regime_predicted_action:
                signal_map = {
                    'SELL_PREMIUM': 'NEUTRAL',  # Premium selling is neutral/range
                    'BUY_CALLS': 'BULLISH',
                    'BUY_PUTS': 'BEARISH',
                    'STAY_FLAT': 'NEUTRAL'
                }
                signals.append({
                    'system': 'Regime Classifier',
                    'signal': signal_map.get(bundle.regime_predicted_action, 'NEUTRAL'),
                    'confidence': bundle.regime_confidence
                })

            if bundle.gex_ml_direction:
                signals.append({
                    'system': 'GEX ML',
                    'signal': bundle.gex_ml_direction.upper(),
                    'confidence': bundle.gex_ml_confidence
                })

            if bundle.ensemble_signal:
                signal_map = {
                    'STRONG_BUY': 'BULLISH',
                    'BUY': 'BULLISH',
                    'NEUTRAL': 'NEUTRAL',
                    'SELL': 'BEARISH',
                    'STRONG_SELL': 'BEARISH'
                }
                signals.append({
                    'system': 'Ensemble',
                    'signal': signal_map.get(bundle.ensemble_signal.upper(), 'NEUTRAL'),
                    'confidence': bundle.ensemble_confidence
                })

            if not signals:
                bundle.ml_consensus = "NO_DATA"
                bundle.ml_conflict_severity = "none"
                return

            bundle.ml_systems_total = len(signals)

            # Count directional signals
            bullish = sum(1 for s in signals if s['signal'] == 'BULLISH')
            bearish = sum(1 for s in signals if s['signal'] == 'BEARISH')
            neutral = sum(1 for s in signals if s['signal'] in ['NEUTRAL', 'FLAT'])

            # Calculate weighted score (-1 to +1)
            total_weight = sum(s['confidence'] for s in signals) or 1
            score = sum(
                s['confidence'] * (1 if s['signal'] == 'BULLISH' else -1 if s['signal'] == 'BEARISH' else 0)
                for s in signals
            ) / total_weight
            bundle.ml_consensus_score = score

            # Determine consensus
            if score > 0.5:
                bundle.ml_consensus = "STRONG_BULLISH"
            elif score > 0.2:
                bundle.ml_consensus = "BULLISH"
            elif score < -0.5:
                bundle.ml_consensus = "STRONG_BEARISH"
            elif score < -0.2:
                bundle.ml_consensus = "BEARISH"
            else:
                bundle.ml_consensus = "MIXED"

            # Count agreeing systems
            if bundle.ml_consensus in ['STRONG_BULLISH', 'BULLISH']:
                bundle.ml_systems_agree = bullish
            elif bundle.ml_consensus in ['STRONG_BEARISH', 'BEARISH']:
                bundle.ml_systems_agree = bearish
            else:
                bundle.ml_systems_agree = max(bullish, bearish, neutral)

            # Detect conflicts
            conflicts = []
            if bullish > 0 and bearish > 0:
                bullish_systems = [s['system'] for s in signals if s['signal'] == 'BULLISH']
                bearish_systems = [s['system'] for s in signals if s['signal'] == 'BEARISH']
                conflicts.append({
                    'type': 'DIRECTIONAL_CONFLICT',
                    'bullish_systems': bullish_systems,
                    'bearish_systems': bearish_systems,
                    'description': f"{', '.join(bullish_systems)} say BULLISH but {', '.join(bearish_systems)} say BEARISH"
                })

            bundle.ml_conflicts = conflicts if conflicts else None

            # Determine conflict severity
            if not conflicts:
                bundle.ml_conflict_severity = "none"
            elif bullish >= 2 and bearish >= 2:
                bundle.ml_conflict_severity = "high"
            elif bullish > 0 and bearish > 0:
                bundle.ml_conflict_severity = "medium"
            else:
                bundle.ml_conflict_severity = "low"

            # Find highest confidence system
            if signals:
                highest = max(signals, key=lambda s: s['confidence'])
                bundle.ml_highest_confidence_system = highest['system']
                bundle.ml_highest_confidence_value = highest['confidence']

        except Exception as e:
            logger.debug(f"Consensus computation failed: {e}")


# Singleton instance
_gatherer: Optional[MLDataGatherer] = None


def get_ml_data_gatherer() -> MLDataGatherer:
    """Get singleton MLDataGatherer instance"""
    global _gatherer
    if _gatherer is None:
        _gatherer = MLDataGatherer()
    return _gatherer


def gather_ml_data(
    symbol: str = "SPY",
    spot_price: float = 0,
    vix: float = 0,
    gex_data: Optional[Dict] = None,
    market_data: Optional[Dict] = None,
    bot_name: str = "ARES",
    **kwargs
) -> Dict[str, Any]:
    """
    Convenience function to gather all ML data and return as kwargs dict.

    This is the main entry point for bots to get ML data for logging.

    Usage:
        ml_kwargs = gather_ml_data(
            symbol="SPY",
            spot_price=585.50,
            vix=15.5,
            gex_data={'net_gex': 1.5e9, ...},
            bot_name="ARES"
        )
        log_ares_scan(..., **ml_kwargs)
    """
    gatherer = get_ml_data_gatherer()
    bundle = gatherer.gather_all(
        symbol=symbol,
        spot_price=spot_price,
        vix=vix,
        gex_data=gex_data,
        market_data=market_data,
        bot_name=bot_name,
        **kwargs
    )
    return bundle.to_kwargs()
