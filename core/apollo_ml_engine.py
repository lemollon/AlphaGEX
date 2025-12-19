"""
APOLLO ML Engine - AI-Powered Live Options Scanner

APOLLO (Advanced Predictive Options Live Learning Oracle) combines:
1. Live Tradier data (quotes, options chains, Greeks)
2. GEX analysis (net gamma, flip points, walls)
3. VIX regime detection
4. Machine learning predictions (direction, magnitude, timing)
5. Adaptive learning from outcomes

This is the core ML engine that powers the APOLLO scanner.
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import pickle
import hashlib

# ML Libraries
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    import xgboost as xgb
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️  ML libraries not available - using rule-based fallback")

logger = logging.getLogger(__name__)

# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class Direction(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

class Magnitude(Enum):
    SMALL = "small"      # < 1%
    MEDIUM = "medium"    # 1-3%
    LARGE = "large"      # > 3%

class Timing(Enum):
    IMMEDIATE = "immediate"  # Same day
    ONE_DAY = "1_day"        # Within 1 day
    THREE_DAY = "3_day"      # Within 3 days

class MarketRegime(Enum):
    LOW_VOL = "low_vol"           # VIX < 15
    NORMAL = "normal"             # VIX 15-20
    ELEVATED = "elevated"         # VIX 20-25
    HIGH_VOL = "high_vol"         # VIX 25-30
    EXTREME = "extreme"           # VIX > 30

class GEXRegime(Enum):
    STRONG_POSITIVE = "strong_positive"  # > 2B
    POSITIVE = "positive"                 # 0.5B - 2B
    NEUTRAL = "neutral"                   # -0.5B to 0.5B
    NEGATIVE = "negative"                 # -2B to -0.5B
    STRONG_NEGATIVE = "strong_negative"   # < -2B


@dataclass
class ApolloFeatures:
    """Complete feature set for ML prediction"""
    symbol: str
    timestamp: datetime

    # Price Features
    spot_price: float = 0.0
    price_change_1d: float = 0.0
    price_change_5d: float = 0.0
    distance_to_flip_pct: float = 0.0
    above_flip: bool = False
    distance_to_call_wall_pct: float = 0.0
    distance_to_put_wall_pct: float = 0.0

    # GEX Features
    net_gex: float = 0.0
    net_gex_normalized: float = 0.0  # -1 to 1 scale
    gex_regime: str = "neutral"
    flip_point: float = 0.0
    call_wall: float = 0.0
    put_wall: float = 0.0

    # VIX Features
    vix: float = 18.0
    vix_percentile: float = 50.0
    vvix: Optional[float] = None
    market_regime: str = "normal"

    # Options Features (from Tradier)
    atm_iv: float = 0.0
    iv_rank: float = 50.0
    iv_hv_ratio: float = 1.0
    put_call_ratio: float = 1.0
    skew_index: float = 1.0

    # ATM Greeks
    atm_delta: float = 0.5
    atm_gamma: float = 0.0
    atm_theta: float = 0.0
    atm_vega: float = 0.0

    # Technical Features
    rsi_14: float = 50.0
    macd_signal: str = "neutral"
    bb_percentb: float = 0.5
    atr_percentile: float = 50.0

    # Volume Features
    volume_ratio: float = 1.0  # vs 20-day avg
    oi_change_pct: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_array(self) -> np.ndarray:
        """Convert to numpy array for ML model input"""
        return np.array([
            self.spot_price,
            self.price_change_1d,
            self.price_change_5d,
            self.distance_to_flip_pct,
            1.0 if self.above_flip else 0.0,
            self.distance_to_call_wall_pct,
            self.distance_to_put_wall_pct,
            self.net_gex_normalized,
            self.vix,
            self.vix_percentile,
            self.atm_iv,
            self.iv_rank,
            self.iv_hv_ratio,
            self.put_call_ratio,
            self.skew_index,
            self.atm_delta,
            self.atm_gamma,
            self.atm_theta,
            self.atm_vega,
            self.rsi_14,
            self.bb_percentb,
            self.atr_percentile,
            self.volume_ratio,
            self.oi_change_pct
        ])


@dataclass
class ApolloPrediction:
    """ML prediction output"""
    symbol: str
    timestamp: datetime

    # Direction prediction
    direction: Direction = Direction.NEUTRAL
    direction_confidence: float = 0.5
    direction_probabilities: Dict[str, float] = field(default_factory=dict)

    # Magnitude prediction
    magnitude: Magnitude = Magnitude.SMALL
    magnitude_confidence: float = 0.5
    magnitude_probabilities: Dict[str, float] = field(default_factory=dict)

    # Timing prediction
    timing: Timing = Timing.ONE_DAY
    timing_confidence: float = 0.5
    timing_probabilities: Dict[str, float] = field(default_factory=dict)

    # Ensemble confidence (0-100)
    ensemble_confidence: float = 50.0

    # Model info
    model_version: str = "1.0.0"
    is_ml_prediction: bool = False  # True if ML, False if rule-based

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'direction': self.direction.value,
            'direction_confidence': self.direction_confidence,
            'direction_probabilities': self.direction_probabilities,
            'magnitude': self.magnitude.value,
            'magnitude_confidence': self.magnitude_confidence,
            'magnitude_probabilities': self.magnitude_probabilities,
            'timing': self.timing.value,
            'timing_confidence': self.timing_confidence,
            'timing_probabilities': self.timing_probabilities,
            'ensemble_confidence': self.ensemble_confidence,
            'model_version': self.model_version,
            'is_ml_prediction': self.is_ml_prediction
        }


@dataclass
class ApolloStrategy:
    """Recommended trading strategy with live strikes"""
    strategy_type: str
    symbol: str

    # Trade details
    direction: str = "neutral"
    expiration: str = ""
    dte: int = 0

    # Strikes (populated from live chain)
    long_strike: Optional[float] = None
    short_strike: Optional[float] = None
    long_strike_2: Optional[float] = None  # For iron condors
    short_strike_2: Optional[float] = None

    # Live pricing
    entry_cost: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    breakeven: Optional[float] = None
    breakeven_upper: Optional[float] = None  # For ranges

    # Risk metrics
    risk_reward_ratio: float = 0.0
    probability_of_profit: float = 0.0
    expected_value: float = 0.0

    # Greeks at entry
    position_delta: float = 0.0
    position_gamma: float = 0.0
    position_theta: float = 0.0
    position_vega: float = 0.0

    # Confidence
    ml_confidence: float = 50.0
    rule_confidence: float = 50.0
    combined_confidence: float = 50.0

    # Reasoning
    reasoning: str = ""
    entry_trigger: str = ""
    exit_target: str = ""
    stop_loss: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ApolloScanResult:
    """Complete scan result for a symbol"""
    symbol: str
    timestamp: datetime
    scan_id: str

    # Raw data
    features: ApolloFeatures = None

    # ML prediction
    prediction: ApolloPrediction = None

    # Recommended strategies (ranked by confidence)
    strategies: List[ApolloStrategy] = field(default_factory=list)

    # Market context
    market_regime: str = "normal"
    gex_regime: str = "neutral"

    # Data quality
    data_quality_score: float = 100.0
    data_sources: List[str] = field(default_factory=list)

    # Errors/warnings
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'scan_id': self.scan_id,
            'features': self.features.to_dict() if self.features else None,
            'prediction': self.prediction.to_dict() if self.prediction else None,
            'strategies': [s.to_dict() for s in self.strategies],
            'market_regime': self.market_regime,
            'gex_regime': self.gex_regime,
            'data_quality_score': self.data_quality_score,
            'data_sources': self.data_sources,
            'warnings': self.warnings
        }


# ============================================================================
# APOLLO ML ENGINE
# ============================================================================

class ApolloMLEngine:
    """
    Core ML engine for APOLLO scanner.

    Handles:
    - Feature engineering from live data
    - ML model predictions
    - Strategy recommendations
    - Outcome tracking and learning
    """

    MODEL_VERSION = "1.0.0"

    def __init__(self):
        self.direction_model = None
        self.magnitude_model = None
        self.timing_model = None
        self.scaler = StandardScaler() if ML_AVAILABLE else None
        self.models_loaded = False
        self.model_performance = {
            'direction_accuracy_7d': 0.0,
            'direction_accuracy_30d': 0.0,
            'magnitude_accuracy_7d': 0.0,
            'magnitude_accuracy_30d': 0.0,
            'last_trained': None
        }

        # Try to load existing models
        self._load_models()

        # Initialize data providers
        self._init_data_providers()

    def _init_data_providers(self):
        """Initialize data provider connections"""
        self.tradier = None
        self.polygon = None
        self.gex_provider = None

        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            self.tradier = TradierDataFetcher()
            logger.info("✅ Tradier data provider initialized")
        except Exception as e:
            logger.warning(f"⚠️  Tradier not available: {e}")

        try:
            from data.polygon_data_fetcher import polygon_fetcher
            self.polygon = polygon_fetcher
            logger.info("✅ Polygon data provider initialized")
        except Exception as e:
            logger.warning(f"⚠️  Polygon not available: {e}")

        try:
            # Try to get the GEX provider - first from dependencies, then create directly
            try:
                from backend.api.dependencies import trading_volatility_api
                self.gex_provider = trading_volatility_api
            except ImportError:
                # Create directly if backend import fails
                from core_classes_and_engines import TradingVolatilityAPI
                self.gex_provider = TradingVolatilityAPI()
            logger.info("✅ GEX data provider initialized")
        except Exception as e:
            logger.warning(f"⚠️  GEX provider not available: {e}")

    def _load_models(self):
        """Load pre-trained models if available"""
        model_dir = os.path.join(os.path.dirname(__file__), '..', 'models', 'apollo')

        if not os.path.exists(model_dir):
            os.makedirs(model_dir, exist_ok=True)
            logger.info("📁 Created models/apollo directory")
            return

        try:
            direction_path = os.path.join(model_dir, 'direction_model.pkl')
            magnitude_path = os.path.join(model_dir, 'magnitude_model.pkl')
            timing_path = os.path.join(model_dir, 'timing_model.pkl')
            scaler_path = os.path.join(model_dir, 'scaler.pkl')

            if all(os.path.exists(p) for p in [direction_path, magnitude_path, timing_path, scaler_path]):
                with open(direction_path, 'rb') as f:
                    self.direction_model = pickle.load(f)
                with open(magnitude_path, 'rb') as f:
                    self.magnitude_model = pickle.load(f)
                with open(timing_path, 'rb') as f:
                    self.timing_model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)

                self.models_loaded = True
                logger.info("✅ APOLLO ML models loaded successfully")
            else:
                logger.info("📊 No pre-trained models found - will use rule-based predictions")
        except Exception as e:
            logger.warning(f"⚠️  Failed to load models: {e}")

    def _save_models(self):
        """Save trained models"""
        model_dir = os.path.join(os.path.dirname(__file__), '..', 'models', 'apollo')
        os.makedirs(model_dir, exist_ok=True)

        try:
            if self.direction_model:
                with open(os.path.join(model_dir, 'direction_model.pkl'), 'wb') as f:
                    pickle.dump(self.direction_model, f)
            if self.magnitude_model:
                with open(os.path.join(model_dir, 'magnitude_model.pkl'), 'wb') as f:
                    pickle.dump(self.magnitude_model, f)
            if self.timing_model:
                with open(os.path.join(model_dir, 'timing_model.pkl'), 'wb') as f:
                    pickle.dump(self.timing_model, f)
            if self.scaler:
                with open(os.path.join(model_dir, 'scaler.pkl'), 'wb') as f:
                    pickle.dump(self.scaler, f)

            logger.info("✅ APOLLO models saved")
        except Exception as e:
            logger.error(f"❌ Failed to save models: {e}")

    # ========================================================================
    # FEATURE ENGINEERING
    # ========================================================================

    def extract_features(self, symbol: str) -> ApolloFeatures:
        """
        Extract all features for a symbol using live data.

        Combines:
        - Tradier live quotes and options
        - GEX data
        - VIX/market regime
        - Technical indicators
        """
        features = ApolloFeatures(symbol=symbol, timestamp=datetime.now())
        data_sources = []

        # 1. Get live quote from Tradier
        if self.tradier:
            try:
                quote = self.tradier.get_quote(symbol)
                if quote:
                    features.spot_price = float(quote.get('last', 0) or quote.get('close', 0) or 0)
                    features.volume_ratio = self._calculate_volume_ratio(quote)
                    data_sources.append('tradier_quote')
            except Exception as e:
                logger.warning(f"Failed to get Tradier quote: {e}")

        # 2. Get GEX data
        if self.gex_provider:
            try:
                gex_data = self.gex_provider.get_net_gamma(symbol)
                if gex_data and not gex_data.get('error'):
                    features.net_gex = gex_data.get('net_gex', 0)
                    features.flip_point = gex_data.get('flip_point', features.spot_price)
                    features.call_wall = gex_data.get('call_wall', features.spot_price * 1.05)
                    features.put_wall = gex_data.get('put_wall', features.spot_price * 0.95)

                    # Normalize GEX (-1 to 1 scale based on typical range)
                    features.net_gex_normalized = np.clip(features.net_gex / 3e9, -1, 1)

                    # Calculate distances
                    if features.spot_price > 0:
                        features.distance_to_flip_pct = ((features.spot_price - features.flip_point) / features.spot_price) * 100
                        features.above_flip = features.spot_price > features.flip_point
                        features.distance_to_call_wall_pct = ((features.call_wall - features.spot_price) / features.spot_price) * 100
                        features.distance_to_put_wall_pct = ((features.spot_price - features.put_wall) / features.spot_price) * 100

                    # Classify GEX regime
                    features.gex_regime = self._classify_gex_regime(features.net_gex)

                    data_sources.append('gex_data')
            except Exception as e:
                logger.warning(f"Failed to get GEX data: {e}")

        # 3. Get VIX data
        try:
            vix_data = self._get_vix_data()
            features.vix = vix_data.get('vix', 18.0)
            features.vix_percentile = vix_data.get('percentile', 50.0)
            features.vvix = vix_data.get('vvix')
            features.market_regime = self._classify_market_regime(features.vix)
            data_sources.append('vix_data')
        except Exception as e:
            logger.warning(f"Failed to get VIX data: {e}")

        # 4. Get options chain data from Tradier
        if self.tradier:
            try:
                options_data = self._get_options_features(symbol, features.spot_price)
                features.atm_iv = options_data.get('atm_iv', 0)
                features.iv_rank = options_data.get('iv_rank', 50)
                features.iv_hv_ratio = options_data.get('iv_hv_ratio', 1.0)
                features.put_call_ratio = options_data.get('put_call_ratio', 1.0)
                features.skew_index = options_data.get('skew_index', 1.0)
                features.atm_delta = options_data.get('atm_delta', 0.5)
                features.atm_gamma = options_data.get('atm_gamma', 0)
                features.atm_theta = options_data.get('atm_theta', 0)
                features.atm_vega = options_data.get('atm_vega', 0)
                features.oi_change_pct = options_data.get('oi_change_pct', 0)
                data_sources.append('tradier_options')
            except Exception as e:
                logger.warning(f"Failed to get options data: {e}")

        # 5. Calculate technical features
        try:
            tech_data = self._calculate_technical_features(symbol)
            features.price_change_1d = tech_data.get('change_1d', 0)
            features.price_change_5d = tech_data.get('change_5d', 0)
            features.rsi_14 = tech_data.get('rsi', 50)
            features.macd_signal = tech_data.get('macd_signal', 'neutral')
            features.bb_percentb = tech_data.get('bb_percentb', 0.5)
            features.atr_percentile = tech_data.get('atr_percentile', 50)
            data_sources.append('technical')
        except Exception as e:
            logger.warning(f"Failed to calculate technicals: {e}")

        return features

    def _get_vix_data(self) -> Dict:
        """Get VIX and VVIX data"""
        result = {'vix': 18.0, 'percentile': 50.0, 'vvix': None}

        try:
            # Try unified data provider first (includes Yahoo Finance fallback)
            from data.unified_data_provider import get_vix
            vix = get_vix()
            if vix and vix > 0:
                result['vix'] = vix
        except:
            pass

        # Direct Yahoo Finance fallback (FREE - no API key!)
        if result['vix'] == 18.0:
            try:
                import yfinance as yf
                vix_ticker = yf.Ticker("^VIX")
                try:
                    price = vix_ticker.fast_info.get('lastPrice', 0)
                    if price and price > 0:
                        result['vix'] = float(price)
                except:
                    hist = vix_ticker.history(period='1d')
                    if not hist.empty:
                        result['vix'] = float(hist['Close'].iloc[-1])
            except:
                pass

        # Get VVIX from Polygon if available
        if self.polygon:
            try:
                vvix = self.polygon.get_current_price('I:VVIX')
                if vvix and vvix > 0:
                    result['vvix'] = vvix
            except:
                pass

        # Calculate VIX percentile (simplified - based on typical range)
        vix = result['vix']
        if vix < 12:
            result['percentile'] = 5
        elif vix < 15:
            result['percentile'] = 20
        elif vix < 18:
            result['percentile'] = 40
        elif vix < 22:
            result['percentile'] = 60
        elif vix < 28:
            result['percentile'] = 80
        else:
            result['percentile'] = 95

        return result

    def _get_options_features(self, symbol: str, spot_price: float) -> Dict:
        """Extract options features from Tradier chain"""
        result = {
            'atm_iv': 0,
            'iv_rank': 50,
            'iv_hv_ratio': 1.0,
            'put_call_ratio': 1.0,
            'skew_index': 1.0,
            'atm_delta': 0.5,
            'atm_gamma': 0,
            'atm_theta': 0,
            'atm_vega': 0,
            'oi_change_pct': 0
        }

        if not self.tradier or spot_price <= 0:
            return result

        try:
            # Get nearest expiration
            expirations = self.tradier.get_option_expirations(symbol)
            if not expirations:
                return result

            # Get chain for nearest expiration (usually 0DTE or next day)
            expiration = expirations[0] if expirations else None
            if not expiration:
                return result

            chain = self.tradier.get_option_chain(symbol, expiration)
            if not chain:
                return result

            # Find ATM strike
            atm_strike = round(spot_price)

            # Extract features from chain
            call_oi = 0
            put_oi = 0
            atm_call = None
            atm_put = None

            for contract in chain:
                strike = contract.get('strike', 0)
                option_type = contract.get('option_type', '')

                if option_type == 'call':
                    call_oi += contract.get('open_interest', 0)
                    if abs(strike - atm_strike) <= 1:
                        atm_call = contract
                elif option_type == 'put':
                    put_oi += contract.get('open_interest', 0)
                    if abs(strike - atm_strike) <= 1:
                        atm_put = contract

            # Put/Call ratio
            if call_oi > 0:
                result['put_call_ratio'] = put_oi / call_oi

            # ATM Greeks
            if atm_call:
                greeks = atm_call.get('greeks', {})
                result['atm_iv'] = greeks.get('mid_iv', 0) * 100  # Convert to percentage
                result['atm_delta'] = greeks.get('delta', 0.5)
                result['atm_gamma'] = greeks.get('gamma', 0)
                result['atm_theta'] = greeks.get('theta', 0)
                result['atm_vega'] = greeks.get('vega', 0)

            # Skew (put IV / call IV)
            if atm_call and atm_put:
                call_iv = atm_call.get('greeks', {}).get('mid_iv', 0.2)
                put_iv = atm_put.get('greeks', {}).get('mid_iv', 0.2)
                if call_iv > 0:
                    result['skew_index'] = put_iv / call_iv

            # IV Rank (simplified - compare to VIX)
            if result['atm_iv'] > 0:
                result['iv_rank'] = min(100, (result['atm_iv'] / 30) * 100)

        except Exception as e:
            logger.warning(f"Error extracting options features: {e}")

        return result

    def _calculate_technical_features(self, symbol: str) -> Dict:
        """Calculate technical indicators"""
        result = {
            'change_1d': 0,
            'change_5d': 0,
            'rsi': 50,
            'macd_signal': 'neutral',
            'bb_percentb': 0.5,
            'atr_percentile': 50
        }

        if not self.polygon:
            return result

        try:
            # Get price history
            df = self.polygon.get_price_history(symbol, days=30, timeframe='day')
            if df is None or len(df) < 14:
                return result

            # Price changes
            if len(df) >= 2:
                result['change_1d'] = ((df['Close'].iloc[-1] / df['Close'].iloc[-2]) - 1) * 100
            if len(df) >= 6:
                result['change_5d'] = ((df['Close'].iloc[-1] / df['Close'].iloc[-6]) - 1) * 100

            # RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            result['rsi'] = rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50

            # Bollinger Bands %B
            sma20 = df['Close'].rolling(window=20).mean()
            std20 = df['Close'].rolling(window=20).std()
            upper = sma20 + (std20 * 2)
            lower = sma20 - (std20 * 2)
            bb_range = upper - lower
            if bb_range.iloc[-1] > 0:
                result['bb_percentb'] = (df['Close'].iloc[-1] - lower.iloc[-1]) / bb_range.iloc[-1]

            # MACD Signal
            ema12 = df['Close'].ewm(span=12).mean()
            ema26 = df['Close'].ewm(span=26).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9).mean()
            if macd.iloc[-1] > signal.iloc[-1]:
                result['macd_signal'] = 'bullish'
            elif macd.iloc[-1] < signal.iloc[-1]:
                result['macd_signal'] = 'bearish'

            # ATR Percentile
            high_low = df['High'] - df['Low']
            high_close = (df['High'] - df['Close'].shift()).abs()
            low_close = (df['Low'] - df['Close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean()
            if len(atr) > 0:
                result['atr_percentile'] = (atr.iloc[-1] / atr.max()) * 100 if atr.max() > 0 else 50

        except Exception as e:
            logger.warning(f"Error calculating technicals: {e}")

        return result

    def _calculate_volume_ratio(self, quote: Dict) -> float:
        """Calculate volume vs average"""
        volume = quote.get('volume', 0)
        avg_volume = quote.get('average_volume', volume)
        if avg_volume > 0:
            return volume / avg_volume
        return 1.0

    def _classify_gex_regime(self, net_gex: float) -> str:
        """Classify GEX regime"""
        if net_gex > 2e9:
            return GEXRegime.STRONG_POSITIVE.value
        elif net_gex > 0.5e9:
            return GEXRegime.POSITIVE.value
        elif net_gex > -0.5e9:
            return GEXRegime.NEUTRAL.value
        elif net_gex > -2e9:
            return GEXRegime.NEGATIVE.value
        else:
            return GEXRegime.STRONG_NEGATIVE.value

    def _classify_market_regime(self, vix: float) -> str:
        """Classify market regime by VIX"""
        if vix < 15:
            return MarketRegime.LOW_VOL.value
        elif vix < 20:
            return MarketRegime.NORMAL.value
        elif vix < 25:
            return MarketRegime.ELEVATED.value
        elif vix < 30:
            return MarketRegime.HIGH_VOL.value
        else:
            return MarketRegime.EXTREME.value

    # ========================================================================
    # ML PREDICTION
    # ========================================================================

    def predict(self, features: ApolloFeatures) -> ApolloPrediction:
        """
        Generate ML prediction from features.

        Uses trained models if available, otherwise rule-based fallback.
        """
        prediction = ApolloPrediction(
            symbol=features.symbol,
            timestamp=datetime.now(),
            model_version=self.MODEL_VERSION
        )

        if self.models_loaded and ML_AVAILABLE:
            prediction = self._ml_predict(features, prediction)
        else:
            prediction = self._rule_based_predict(features, prediction)

        return prediction

    def _ml_predict(self, features: ApolloFeatures, prediction: ApolloPrediction) -> ApolloPrediction:
        """ML-based prediction using trained models"""
        try:
            # Convert features to array and scale
            X = features.to_array().reshape(1, -1)
            X_scaled = self.scaler.transform(X)

            # Direction prediction
            if self.direction_model:
                dir_probs = self.direction_model.predict_proba(X_scaled)[0]
                dir_classes = self.direction_model.classes_
                prediction.direction_probabilities = {
                    c: float(p) for c, p in zip(dir_classes, dir_probs)
                }
                best_dir_idx = np.argmax(dir_probs)
                prediction.direction = Direction(dir_classes[best_dir_idx])
                prediction.direction_confidence = float(dir_probs[best_dir_idx])

            # Magnitude prediction
            if self.magnitude_model:
                mag_probs = self.magnitude_model.predict_proba(X_scaled)[0]
                mag_classes = self.magnitude_model.classes_
                prediction.magnitude_probabilities = {
                    c: float(p) for c, p in zip(mag_classes, mag_probs)
                }
                best_mag_idx = np.argmax(mag_probs)
                prediction.magnitude = Magnitude(mag_classes[best_mag_idx])
                prediction.magnitude_confidence = float(mag_probs[best_mag_idx])

            # Timing prediction
            if self.timing_model:
                time_probs = self.timing_model.predict_proba(X_scaled)[0]
                time_classes = self.timing_model.classes_
                prediction.timing_probabilities = {
                    c: float(p) for c, p in zip(time_classes, time_probs)
                }
                best_time_idx = np.argmax(time_probs)
                prediction.timing = Timing(time_classes[best_time_idx])
                prediction.timing_confidence = float(time_probs[best_time_idx])

            # Calculate ensemble confidence
            prediction.ensemble_confidence = self._calculate_ensemble_confidence(
                prediction.direction_confidence,
                prediction.magnitude_confidence,
                prediction.timing_confidence,
                features
            )

            prediction.is_ml_prediction = True

        except Exception as e:
            logger.error(f"ML prediction failed: {e}")
            prediction = self._rule_based_predict(features, prediction)

        return prediction

    def _rule_based_predict(self, features: ApolloFeatures, prediction: ApolloPrediction) -> ApolloPrediction:
        """Rule-based prediction fallback (uses existing GEX logic)"""

        # Direction based on GEX and position
        if features.net_gex_normalized < -0.3 and not features.above_flip:
            # Negative GEX below flip = bullish squeeze potential
            prediction.direction = Direction.BULLISH
            prediction.direction_confidence = 0.65
        elif features.net_gex_normalized < -0.3 and features.above_flip:
            # Negative GEX above flip = bearish breakdown potential
            prediction.direction = Direction.BEARISH
            prediction.direction_confidence = 0.60
        elif features.net_gex_normalized > 0.3:
            # Strong positive GEX = mean reversion/range
            prediction.direction = Direction.NEUTRAL
            prediction.direction_confidence = 0.70
        else:
            # Weak GEX signal
            if features.rsi_14 < 30:
                prediction.direction = Direction.BULLISH
                prediction.direction_confidence = 0.55
            elif features.rsi_14 > 70:
                prediction.direction = Direction.BEARISH
                prediction.direction_confidence = 0.55
            else:
                prediction.direction = Direction.NEUTRAL
                prediction.direction_confidence = 0.50

        prediction.direction_probabilities = {
            'bullish': 0.33,
            'bearish': 0.33,
            'neutral': 0.34
        }
        prediction.direction_probabilities[prediction.direction.value] = prediction.direction_confidence

        # Magnitude based on VIX and GEX
        if features.vix > 25 or abs(features.net_gex_normalized) > 0.6:
            prediction.magnitude = Magnitude.LARGE
            prediction.magnitude_confidence = 0.60
        elif features.vix > 18 or abs(features.net_gex_normalized) > 0.3:
            prediction.magnitude = Magnitude.MEDIUM
            prediction.magnitude_confidence = 0.65
        else:
            prediction.magnitude = Magnitude.SMALL
            prediction.magnitude_confidence = 0.70

        prediction.magnitude_probabilities = {
            'small': 0.33,
            'medium': 0.34,
            'large': 0.33
        }
        prediction.magnitude_probabilities[prediction.magnitude.value] = prediction.magnitude_confidence

        # Timing based on GEX intensity
        if abs(features.net_gex_normalized) > 0.6:
            prediction.timing = Timing.IMMEDIATE
            prediction.timing_confidence = 0.55
        elif abs(features.net_gex_normalized) > 0.3:
            prediction.timing = Timing.ONE_DAY
            prediction.timing_confidence = 0.60
        else:
            prediction.timing = Timing.THREE_DAY
            prediction.timing_confidence = 0.65

        prediction.timing_probabilities = {
            'immediate': 0.33,
            '1_day': 0.34,
            '3_day': 0.33
        }
        prediction.timing_probabilities[prediction.timing.value] = prediction.timing_confidence

        # Ensemble confidence
        prediction.ensemble_confidence = self._calculate_ensemble_confidence(
            prediction.direction_confidence,
            prediction.magnitude_confidence,
            prediction.timing_confidence,
            features
        )

        prediction.is_ml_prediction = False

        return prediction

    def _calculate_ensemble_confidence(
        self,
        dir_conf: float,
        mag_conf: float,
        time_conf: float,
        features: ApolloFeatures
    ) -> float:
        """Calculate combined confidence score (0-100)"""

        # Base confidence from models
        base_conf = (dir_conf * 0.5 + mag_conf * 0.25 + time_conf * 0.25)

        # Boost for strong GEX signal
        gex_boost = min(0.1, abs(features.net_gex_normalized) * 0.15)

        # Boost for extreme VIX (clearer regime)
        vix_boost = 0
        if features.vix < 15 or features.vix > 25:
            vix_boost = 0.05

        # Penalty for conflicting signals
        penalty = 0
        if features.macd_signal == 'bearish' and dir_conf > 0.5:
            penalty = 0.05
        elif features.macd_signal == 'bullish' and dir_conf < 0.5:
            penalty = 0.05

        final_conf = base_conf + gex_boost + vix_boost - penalty

        # Scale to 0-100
        return min(100, max(0, final_conf * 100))

    # ========================================================================
    # STRATEGY RECOMMENDATION
    # ========================================================================

    def recommend_strategies(
        self,
        symbol: str,
        features: ApolloFeatures,
        prediction: ApolloPrediction
    ) -> List[ApolloStrategy]:
        """
        Generate strategy recommendations based on ML prediction and live data.

        Returns ranked list of strategies with live strikes and pricing.
        """
        strategies = []

        # Get live options chain for strike selection
        chain_data = self._get_live_chain(symbol, features.spot_price)

        # Generate strategies based on prediction
        if prediction.direction == Direction.BULLISH:
            strategies.append(self._build_bull_call_spread(symbol, features, prediction, chain_data))
            strategies.append(self._build_bull_put_spread(symbol, features, prediction, chain_data))
            if features.vix > 20:
                strategies.append(self._build_long_call(symbol, features, prediction, chain_data))

        elif prediction.direction == Direction.BEARISH:
            strategies.append(self._build_bear_put_spread(symbol, features, prediction, chain_data))
            strategies.append(self._build_bear_call_spread(symbol, features, prediction, chain_data))
            if features.vix > 20:
                strategies.append(self._build_long_put(symbol, features, prediction, chain_data))

        else:  # Neutral
            strategies.append(self._build_iron_condor(symbol, features, prediction, chain_data))
            strategies.append(self._build_iron_butterfly(symbol, features, prediction, chain_data))
            if features.vix > 25:
                strategies.append(self._build_straddle(symbol, features, prediction, chain_data))

        # Sort by combined confidence
        strategies = [s for s in strategies if s is not None]
        strategies.sort(key=lambda x: x.combined_confidence, reverse=True)

        return strategies[:5]  # Return top 5

    def _get_live_chain(self, symbol: str, spot_price: float) -> Dict:
        """Get live options chain data from Tradier"""
        result = {
            'expirations': [],
            'chains': {},
            'spot_price': spot_price
        }

        if not self.tradier:
            return result

        try:
            expirations = self.tradier.get_option_expirations(symbol)
            result['expirations'] = expirations[:5] if expirations else []  # First 5 expirations

            # Get chain for nearest useful expiration (skip 0DTE for spreads)
            for exp in result['expirations']:
                chain = self.tradier.get_option_chain(symbol, exp)
                if chain:
                    result['chains'][exp] = chain
                    break  # Just get first valid chain for now

        except Exception as e:
            logger.warning(f"Failed to get live chain: {e}")

        return result

    def _find_strike_by_delta(self, chain: List, target_delta: float, option_type: str) -> Optional[Dict]:
        """Find strike closest to target delta"""
        best_match = None
        best_diff = float('inf')

        for contract in chain:
            if contract.get('option_type') != option_type:
                continue

            delta = abs(contract.get('greeks', {}).get('delta', 0))
            diff = abs(delta - abs(target_delta))

            if diff < best_diff:
                best_diff = diff
                best_match = contract

        return best_match

    def _build_bull_call_spread(
        self,
        symbol: str,
        features: ApolloFeatures,
        prediction: ApolloPrediction,
        chain_data: Dict
    ) -> Optional[ApolloStrategy]:
        """Build bull call spread with live strikes"""

        strategy = ApolloStrategy(
            strategy_type="BULL_CALL_SPREAD",
            symbol=symbol,
            direction="bullish"
        )

        if not chain_data.get('chains'):
            # No live chain - use estimate
            strategy.long_strike = round(features.spot_price * 0.99)
            strategy.short_strike = round(features.spot_price * 1.02)
            strategy.expiration = "nearest"
            strategy.dte = 7
            strategy.entry_cost = features.spot_price * 0.015  # ~1.5% of underlying
            strategy.max_profit = (strategy.short_strike - strategy.long_strike) - strategy.entry_cost
            strategy.max_loss = strategy.entry_cost
            strategy.risk_reward_ratio = strategy.max_profit / strategy.max_loss if strategy.max_loss > 0 else 0
            strategy.probability_of_profit = 0.45
        else:
            # Use live chain
            expiration = list(chain_data['chains'].keys())[0]
            chain = chain_data['chains'][expiration]

            # Find strikes by delta
            long_contract = self._find_strike_by_delta(chain, 0.45, 'call')
            short_contract = self._find_strike_by_delta(chain, 0.25, 'call')

            if long_contract and short_contract:
                strategy.long_strike = long_contract.get('strike')
                strategy.short_strike = short_contract.get('strike')
                strategy.expiration = expiration

                # Calculate DTE
                exp_date = datetime.strptime(expiration, '%Y-%m-%d')
                strategy.dte = (exp_date - datetime.now()).days

                # Live pricing
                long_ask = long_contract.get('ask', 0)
                short_bid = short_contract.get('bid', 0)
                strategy.entry_cost = (long_ask - short_bid) * 100  # Per contract
                strategy.max_profit = ((strategy.short_strike - strategy.long_strike) * 100) - strategy.entry_cost
                strategy.max_loss = strategy.entry_cost
                strategy.risk_reward_ratio = strategy.max_profit / strategy.max_loss if strategy.max_loss > 0 else 0

                # Greeks
                strategy.position_delta = (
                    long_contract.get('greeks', {}).get('delta', 0) -
                    short_contract.get('greeks', {}).get('delta', 0)
                )
                strategy.position_gamma = (
                    long_contract.get('greeks', {}).get('gamma', 0) -
                    short_contract.get('greeks', {}).get('gamma', 0)
                )
                strategy.position_theta = (
                    long_contract.get('greeks', {}).get('theta', 0) -
                    short_contract.get('greeks', {}).get('theta', 0)
                )

                # Probability of profit (simplified)
                strategy.probability_of_profit = 0.45 + (prediction.direction_confidence - 0.5) * 0.2

        # Confidence scores
        strategy.ml_confidence = prediction.ensemble_confidence
        strategy.rule_confidence = 65 if features.net_gex_normalized < -0.2 else 55
        strategy.combined_confidence = (strategy.ml_confidence * 0.6 + strategy.rule_confidence * 0.4)

        # Reasoning
        strategy.reasoning = f"Bullish setup: {prediction.direction.value} prediction with {prediction.direction_confidence:.0%} confidence. "
        strategy.reasoning += f"GEX regime: {features.gex_regime}, VIX: {features.vix:.1f}"
        strategy.entry_trigger = f"Enter on pullback to ${features.flip_point:.2f} (flip point)"
        strategy.exit_target = f"Exit at ${features.call_wall:.2f} (call wall) or 75% profit"
        strategy.stop_loss = f"Close if {symbol} breaks below ${features.put_wall:.2f}"

        return strategy

    def _build_bear_put_spread(
        self,
        symbol: str,
        features: ApolloFeatures,
        prediction: ApolloPrediction,
        chain_data: Dict
    ) -> Optional[ApolloStrategy]:
        """Build bear put spread"""

        strategy = ApolloStrategy(
            strategy_type="BEAR_PUT_SPREAD",
            symbol=symbol,
            direction="bearish"
        )

        strategy.long_strike = round(features.spot_price * 1.01)
        strategy.short_strike = round(features.spot_price * 0.98)
        strategy.expiration = "nearest"
        strategy.dte = 7
        strategy.entry_cost = features.spot_price * 0.015
        strategy.max_profit = (strategy.long_strike - strategy.short_strike) - strategy.entry_cost
        strategy.max_loss = strategy.entry_cost
        strategy.risk_reward_ratio = strategy.max_profit / strategy.max_loss if strategy.max_loss > 0 else 0
        strategy.probability_of_profit = 0.42

        strategy.ml_confidence = prediction.ensemble_confidence
        strategy.rule_confidence = 62 if features.net_gex_normalized < -0.2 and features.above_flip else 50
        strategy.combined_confidence = (strategy.ml_confidence * 0.6 + strategy.rule_confidence * 0.4)

        strategy.reasoning = f"Bearish setup: {prediction.direction.value} prediction with {prediction.direction_confidence:.0%} confidence."
        strategy.entry_trigger = f"Enter on bounce to ${features.flip_point:.2f}"
        strategy.exit_target = f"Exit at ${features.put_wall:.2f} or 75% profit"
        strategy.stop_loss = f"Close if {symbol} breaks above ${features.call_wall:.2f}"

        return strategy

    def _build_iron_condor(
        self,
        symbol: str,
        features: ApolloFeatures,
        prediction: ApolloPrediction,
        chain_data: Dict
    ) -> Optional[ApolloStrategy]:
        """Build iron condor for neutral prediction"""

        strategy = ApolloStrategy(
            strategy_type="IRON_CONDOR",
            symbol=symbol,
            direction="neutral"
        )

        # Use walls as outer strikes
        put_wing = features.put_wall
        call_wing = features.call_wall

        # Inner strikes closer to spot
        strategy.short_strike = round(features.spot_price * 1.02)  # Short call
        strategy.long_strike = round(features.spot_price * 1.04)   # Long call (protection)
        strategy.short_strike_2 = round(features.spot_price * 0.98)  # Short put
        strategy.long_strike_2 = round(features.spot_price * 0.96)   # Long put (protection)

        strategy.expiration = "nearest"
        strategy.dte = 7

        # Credit received (simplified estimate)
        strategy.entry_cost = -features.spot_price * 0.008  # Negative = credit
        strategy.max_profit = abs(strategy.entry_cost) * 100  # Credit received
        wing_width = (strategy.long_strike - strategy.short_strike) * 100
        strategy.max_loss = wing_width - strategy.max_profit
        strategy.risk_reward_ratio = strategy.max_profit / strategy.max_loss if strategy.max_loss > 0 else 0

        strategy.breakeven = strategy.short_strike_2 - abs(strategy.entry_cost)
        strategy.breakeven_upper = strategy.short_strike + abs(strategy.entry_cost)

        strategy.probability_of_profit = 0.68  # Iron condors typically have high POP

        strategy.ml_confidence = prediction.ensemble_confidence
        strategy.rule_confidence = 75 if features.net_gex_normalized > 0.2 else 60
        strategy.combined_confidence = (strategy.ml_confidence * 0.6 + strategy.rule_confidence * 0.4)

        strategy.reasoning = f"Range-bound setup: Positive GEX ({features.net_gex/1e9:.2f}B) suggests pinning between walls."
        strategy.entry_trigger = f"Enter when {symbol} is between ${features.put_wall:.2f} and ${features.call_wall:.2f}"
        strategy.exit_target = "Close at 50% profit or 21 DTE"
        strategy.stop_loss = f"Close if {symbol} breaks ${strategy.short_strike_2:.2f} or ${strategy.short_strike:.2f}"

        return strategy

    # Stub implementations for other strategies
    def _build_bull_put_spread(self, symbol, features, prediction, chain_data):
        strategy = ApolloStrategy(strategy_type="BULL_PUT_SPREAD", symbol=symbol, direction="bullish")
        strategy.long_strike = round(features.spot_price * 0.95)
        strategy.short_strike = round(features.spot_price * 0.97)
        strategy.ml_confidence = prediction.ensemble_confidence
        strategy.rule_confidence = 60
        strategy.combined_confidence = (strategy.ml_confidence * 0.6 + strategy.rule_confidence * 0.4)
        strategy.reasoning = "Credit spread for bullish bias with defined risk"
        return strategy

    def _build_bear_call_spread(self, symbol, features, prediction, chain_data):
        strategy = ApolloStrategy(strategy_type="BEAR_CALL_SPREAD", symbol=symbol, direction="bearish")
        strategy.long_strike = round(features.spot_price * 1.05)
        strategy.short_strike = round(features.spot_price * 1.03)
        strategy.ml_confidence = prediction.ensemble_confidence
        strategy.rule_confidence = 58
        strategy.combined_confidence = (strategy.ml_confidence * 0.6 + strategy.rule_confidence * 0.4)
        strategy.reasoning = "Credit spread for bearish bias with defined risk"
        return strategy

    def _build_long_call(self, symbol, features, prediction, chain_data):
        strategy = ApolloStrategy(strategy_type="LONG_CALL", symbol=symbol, direction="bullish")
        strategy.long_strike = round(features.spot_price)
        strategy.ml_confidence = prediction.ensemble_confidence
        strategy.rule_confidence = 55
        strategy.combined_confidence = (strategy.ml_confidence * 0.6 + strategy.rule_confidence * 0.4)
        strategy.reasoning = "Directional play for high conviction bullish move"
        return strategy

    def _build_long_put(self, symbol, features, prediction, chain_data):
        strategy = ApolloStrategy(strategy_type="LONG_PUT", symbol=symbol, direction="bearish")
        strategy.long_strike = round(features.spot_price)
        strategy.ml_confidence = prediction.ensemble_confidence
        strategy.rule_confidence = 55
        strategy.combined_confidence = (strategy.ml_confidence * 0.6 + strategy.rule_confidence * 0.4)
        strategy.reasoning = "Directional play for high conviction bearish move"
        return strategy

    def _build_iron_butterfly(self, symbol, features, prediction, chain_data):
        strategy = ApolloStrategy(strategy_type="IRON_BUTTERFLY", symbol=symbol, direction="neutral")
        strategy.long_strike = round(features.spot_price * 1.03)
        strategy.short_strike = round(features.spot_price)
        strategy.long_strike_2 = round(features.spot_price * 0.97)
        strategy.short_strike_2 = round(features.spot_price)
        strategy.ml_confidence = prediction.ensemble_confidence
        strategy.rule_confidence = 65
        strategy.combined_confidence = (strategy.ml_confidence * 0.6 + strategy.rule_confidence * 0.4)
        strategy.reasoning = "Max profit at ATM for low vol, pinned price action"
        return strategy

    def _build_straddle(self, symbol, features, prediction, chain_data):
        strategy = ApolloStrategy(strategy_type="LONG_STRADDLE", symbol=symbol, direction="neutral")
        strategy.long_strike = round(features.spot_price)
        strategy.ml_confidence = prediction.ensemble_confidence
        strategy.rule_confidence = 50
        strategy.combined_confidence = (strategy.ml_confidence * 0.6 + strategy.rule_confidence * 0.4)
        strategy.reasoning = "Volatility play - profits from large move in either direction"
        return strategy

    # ========================================================================
    # FULL SCAN
    # ========================================================================

    def scan(self, symbol: str) -> ApolloScanResult:
        """
        Perform complete APOLLO scan for a symbol.

        Returns:
            ApolloScanResult with features, prediction, and strategies
        """
        import uuid

        scan_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now()

        result = ApolloScanResult(
            symbol=symbol,
            timestamp=timestamp,
            scan_id=scan_id
        )

        try:
            # 1. Extract features
            features = self.extract_features(symbol)
            result.features = features
            result.data_sources = ['gex', 'vix', 'tradier', 'technical']

            # 2. Generate prediction
            prediction = self.predict(features)
            result.prediction = prediction

            # 3. Get strategy recommendations
            strategies = self.recommend_strategies(symbol, features, prediction)
            result.strategies = strategies

            # 4. Set regimes
            result.market_regime = features.market_regime
            result.gex_regime = features.gex_regime

            # 5. Calculate data quality
            result.data_quality_score = self._calculate_data_quality(features)

        except Exception as e:
            logger.error(f"Scan failed for {symbol}: {e}")
            result.warnings.append(f"Scan error: {str(e)}")
            result.data_quality_score = 0

        return result

    def _calculate_data_quality(self, features: ApolloFeatures) -> float:
        """Calculate data quality score (0-100)"""
        score = 100

        if features.spot_price <= 0:
            score -= 30
        if features.net_gex == 0:
            score -= 20
        if features.atm_iv == 0:
            score -= 15
        if features.vix == 18.0:  # Default value
            score -= 10
        if features.rsi_14 == 50:  # Default value
            score -= 5

        return max(0, score)

    # ========================================================================
    # TRAINING & LEARNING
    # ========================================================================

    def train_models(self, training_data: pd.DataFrame):
        """
        Train ML models on historical data.

        Expected columns:
        - All feature columns
        - actual_direction: 'bullish', 'bearish', 'neutral'
        - actual_magnitude: 'small', 'medium', 'large'
        - actual_timing: 'immediate', '1_day', '3_day'
        """
        if not ML_AVAILABLE:
            logger.error("ML libraries not available - cannot train")
            return

        logger.info(f"Training APOLLO models on {len(training_data)} samples...")

        # Prepare features
        feature_cols = [
            'spot_price', 'price_change_1d', 'price_change_5d', 'distance_to_flip_pct',
            'above_flip', 'distance_to_call_wall_pct', 'distance_to_put_wall_pct',
            'net_gex_normalized', 'vix', 'vix_percentile', 'atm_iv', 'iv_rank',
            'iv_hv_ratio', 'put_call_ratio', 'skew_index', 'atm_delta', 'atm_gamma',
            'atm_theta', 'atm_vega', 'rsi_14', 'bb_percentb', 'atr_percentile',
            'volume_ratio', 'oi_change_pct'
        ]

        X = training_data[feature_cols].values

        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Train direction model
        y_dir = training_data['actual_direction'].values
        X_train, X_test, y_train, y_test = train_test_split(X_scaled, y_dir, test_size=0.2)

        self.direction_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        self.direction_model.fit(X_train, y_train)
        dir_accuracy = self.direction_model.score(X_test, y_test)
        logger.info(f"Direction model accuracy: {dir_accuracy:.2%}")

        # Train magnitude model
        y_mag = training_data['actual_magnitude'].values
        X_train, X_test, y_train, y_test = train_test_split(X_scaled, y_mag, test_size=0.2)

        self.magnitude_model = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            random_state=42
        )
        self.magnitude_model.fit(X_train, y_train)
        mag_accuracy = self.magnitude_model.score(X_test, y_test)
        logger.info(f"Magnitude model accuracy: {mag_accuracy:.2%}")

        # Train timing model
        y_time = training_data['actual_timing'].values
        X_train, X_test, y_train, y_test = train_test_split(X_scaled, y_time, test_size=0.2)

        self.timing_model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42
        )
        self.timing_model.fit(X_train, y_train)
        time_accuracy = self.timing_model.score(X_test, y_test)
        logger.info(f"Timing model accuracy: {time_accuracy:.2%}")

        self.models_loaded = True
        self.model_performance['last_trained'] = datetime.now().isoformat()

        # Save models
        self._save_models()

        logger.info("✅ APOLLO models trained and saved")


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_apollo_engine = None

def get_apollo_engine() -> ApolloMLEngine:
    """Get singleton APOLLO engine instance"""
    global _apollo_engine
    if _apollo_engine is None:
        _apollo_engine = ApolloMLEngine()
    return _apollo_engine
