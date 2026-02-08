"""
GEX Probability Models - 5 ML Models for Gamma-Based Trading
=============================================================

Trains 5 probability models using pre-computed GEX structure data:
1. Direction Probability - UP/DOWN/FLAT based on gamma regime
2. Flip Gravity - Probability price gravitates toward flip point
3. Magnet Attraction - Probability price reaches nearest magnet
4. Volatility Estimate - Expected price range based on gamma
5. Pin Zone Behavior - Probability of staying between magnets

Key Design Principles:
- NO BIAS: Store raw data, let ML discover patterns
- Walk-forward validation to prevent look-ahead bias
- Feature engineering based on validated hypotheses
- Combined signal output for trading decisions

Author: AlphaGEX Quant
"""

import os
import sys
import logging
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import statistics

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score,
    mean_squared_error, mean_absolute_error, r2_score
)
from sklearn.preprocessing import StandardScaler, LabelEncoder
import joblib

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')


class Direction(Enum):
    """Market direction classification"""
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


@dataclass
class ModelPrediction:
    """Unified prediction result"""
    model_name: str
    prediction: Any
    confidence: float
    probabilities: Optional[Dict[str, float]] = None
    raw_value: Optional[float] = None


@dataclass
class CombinedSignal:
    """Combined output from all 5 models"""
    direction_prediction: str
    direction_confidence: float
    flip_gravity_prob: float
    magnet_attraction_prob: float
    expected_volatility_pct: float
    pin_zone_prob: float
    overall_conviction: float  # 0-1 combined score
    trade_recommendation: str  # LONG/SHORT/STAY_OUT

    def to_dict(self) -> Dict:
        return {
            'direction': self.direction_prediction,
            'direction_confidence': self.direction_confidence,
            'flip_gravity': self.flip_gravity_prob,
            'magnet_attraction': self.magnet_attraction_prob,
            'expected_volatility_pct': self.expected_volatility_pct,
            'pin_zone_prob': self.pin_zone_prob,
            'conviction': self.overall_conviction,
            'recommendation': self.trade_recommendation
        }


def get_connection():
    """Get PostgreSQL connection"""
    import psycopg2
    from urllib.parse import urlparse

    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL or ORAT_DATABASE_URL environment variable not set")

    result = urlparse(database_url)
    return psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )


def load_gex_from_history_fallback(
    symbols: List[str] = ['SPX', 'SPY'],
    start_date: str = '2020-01-01',
    end_date: str = None
) -> pd.DataFrame:
    """
    Fallback: Load and aggregate GEX data from gex_history table.

    Used when gex_structure_daily is empty but gex_history has real-time snapshots.
    Aggregates intraday snapshots into daily structure for ML training.
    """
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    conn = get_connection()

    # Check if gex_history has data
    check_query = """
        SELECT COUNT(*) FROM gex_history
        WHERE symbol = ANY(%s)
        AND DATE(timestamp) >= %s
        AND DATE(timestamp) <= %s
    """
    cursor = conn.cursor()
    cursor.execute(check_query, (symbols, start_date, end_date))
    count = cursor.fetchone()[0]

    if count == 0:
        logger.warning("No data in gex_history table either")
        conn.close()
        return pd.DataFrame()

    logger.info(f"Loading {count} records from gex_history (fallback mode)")

    # Aggregate gex_history to daily structure
    query = """
        SELECT
            DATE(h.timestamp) as trade_date,
            h.symbol,
            -- Use first and last of day for OHLC approximation
            FIRST_VALUE(h.spot_price) OVER (PARTITION BY DATE(h.timestamp), h.symbol ORDER BY h.timestamp) as spot_open,
            MAX(h.spot_price) OVER (PARTITION BY DATE(h.timestamp), h.symbol) as spot_high,
            MIN(h.spot_price) OVER (PARTITION BY DATE(h.timestamp), h.symbol) as spot_low,
            LAST_VALUE(h.spot_price) OVER (PARTITION BY DATE(h.timestamp), h.symbol ORDER BY h.timestamp
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as spot_close,
            -- Average gamma for the day
            AVG(h.net_gex) as net_gamma,
            -- Walls from last snapshot of day
            LAST_VALUE(h.flip_point) OVER (PARTITION BY DATE(h.timestamp), h.symbol ORDER BY h.timestamp
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as flip_point,
            LAST_VALUE(h.call_wall) OVER (PARTITION BY DATE(h.timestamp), h.symbol ORDER BY h.timestamp
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as call_wall,
            LAST_VALUE(h.put_wall) OVER (PARTITION BY DATE(h.timestamp), h.symbol ORDER BY h.timestamp
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as put_wall,
            -- VIX from vix_daily if available
            v.vix_open,
            v.vix_close
        FROM gex_history h
        LEFT JOIN vix_daily v ON DATE(h.timestamp) = v.trade_date
        WHERE h.symbol = ANY(%s)
          AND DATE(h.timestamp) >= %s
          AND DATE(h.timestamp) <= %s
        ORDER BY trade_date, symbol
    """

    # Use a simpler aggregation query that works better
    simple_query = """
        WITH daily_agg AS (
            SELECT
                DATE(timestamp) as trade_date,
                symbol,
                MIN(spot_price) as spot_low,
                MAX(spot_price) as spot_high,
                AVG(net_gex) as net_gamma,
                AVG(flip_point) as flip_point,
                AVG(call_wall) as call_wall,
                AVG(put_wall) as put_wall,
                COUNT(*) as snapshot_count
            FROM gex_history
            WHERE symbol = ANY(%s)
              AND DATE(timestamp) >= %s
              AND DATE(timestamp) <= %s
            GROUP BY DATE(timestamp), symbol
        ),
        first_last AS (
            SELECT DISTINCT ON (DATE(timestamp), symbol)
                DATE(timestamp) as trade_date,
                symbol,
                FIRST_VALUE(spot_price) OVER w as spot_open,
                LAST_VALUE(spot_price) OVER w as spot_close
            FROM gex_history
            WHERE symbol = ANY(%s)
              AND DATE(timestamp) >= %s
              AND DATE(timestamp) <= %s
            WINDOW w AS (PARTITION BY DATE(timestamp), symbol ORDER BY timestamp
                         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        )
        SELECT
            d.trade_date,
            d.symbol,
            f.spot_open,
            d.spot_high,
            d.spot_low,
            f.spot_close,
            d.net_gamma,
            d.net_gamma * 0.6 as total_call_gamma,  -- Approximation
            d.net_gamma * 0.4 as total_put_gamma,   -- Approximation
            d.flip_point,
            d.call_wall as magnet_1_strike,  -- Use call wall as magnet 1
            d.net_gamma as magnet_1_gamma,
            d.put_wall as magnet_2_strike,   -- Use put wall as magnet 2
            d.net_gamma * 0.5 as magnet_2_gamma,
            NULL as magnet_3_strike,
            NULL as magnet_3_gamma,
            d.call_wall,
            d.put_wall,
            CASE WHEN d.net_gamma > 0 THEN d.net_gamma ELSE 0 END as gamma_above_spot,
            CASE WHEN d.net_gamma < 0 THEN ABS(d.net_gamma) ELSE 0 END as gamma_below_spot,
            CASE WHEN d.net_gamma != 0
                 THEN (d.net_gamma / ABS(d.net_gamma)) * 100
                 ELSE 0 END as gamma_imbalance_pct,
            1 as num_magnets_above,
            1 as num_magnets_below,
            d.call_wall as nearest_magnet_strike,
            CASE WHEN f.spot_open > 0
                 THEN ABS(d.call_wall - f.spot_open) / f.spot_open * 100
                 ELSE 0 END as nearest_magnet_distance_pct,
            CASE WHEN f.spot_open > 0 AND d.flip_point > 0
                 THEN ABS(f.spot_open - d.flip_point) / f.spot_open * 100
                 ELSE 0 END as open_to_flip_distance_pct,
            FALSE as open_in_pin_zone,
            CASE WHEN f.spot_open > 0
                 THEN (f.spot_close - f.spot_open) / f.spot_open * 100
                 ELSE 0 END as price_change_pct,
            CASE WHEN f.spot_open > 0
                 THEN (d.spot_high - d.spot_low) / f.spot_open * 100
                 ELSE 0 END as price_range_pct,
            CASE WHEN f.spot_close > 0 AND d.flip_point > 0
                 THEN ABS(f.spot_close - d.flip_point) / f.spot_close * 100
                 ELSE 0 END as close_distance_to_flip_pct,
            CASE WHEN f.spot_close > 0 AND d.call_wall > 0
                 THEN ABS(f.spot_close - d.call_wall) / f.spot_close * 100
                 ELSE 0 END as close_distance_to_magnet1_pct,
            CASE WHEN f.spot_close > 0 AND d.put_wall > 0
                 THEN ABS(f.spot_close - d.put_wall) / f.spot_close * 100
                 ELSE 0 END as close_distance_to_magnet2_pct,
            v.vix_open,
            v.vix_close
        FROM daily_agg d
        JOIN first_last f ON d.trade_date = f.trade_date AND d.symbol = f.symbol
        LEFT JOIN vix_daily v ON d.trade_date = v.trade_date
        ORDER BY d.trade_date, d.symbol
    """

    df = pd.read_sql(simple_query, conn, params=(
        symbols, start_date, end_date,
        symbols, start_date, end_date
    ))
    conn.close()

    # Convert decimals to float
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = df[col].astype(float)
            except (ValueError, TypeError):
                pass

    logger.info(f"Aggregated {len(df)} daily records from gex_history")
    return df


def load_gex_structure_data(
    symbols: List[str] = ['SPX', 'SPY'],
    start_date: str = '2020-01-01',
    end_date: str = None
) -> pd.DataFrame:
    """
    Load pre-computed GEX structure data from database.

    Returns DataFrame with all features needed for ML training.
    Falls back to gex_history table if gex_structure_daily is empty.
    """
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    conn = get_connection()

    query = """
        SELECT
            g.trade_date,
            g.symbol,
            g.spot_open,
            g.spot_close,
            g.spot_high,
            g.spot_low,
            g.net_gamma,
            g.total_call_gamma,
            g.total_put_gamma,
            g.flip_point,
            g.magnet_1_strike,
            g.magnet_1_gamma,
            g.magnet_2_strike,
            g.magnet_2_gamma,
            g.magnet_3_strike,
            g.magnet_3_gamma,
            g.call_wall,
            g.put_wall,
            g.gamma_above_spot,
            g.gamma_below_spot,
            g.gamma_imbalance_pct,
            g.num_magnets_above,
            g.num_magnets_below,
            g.nearest_magnet_strike,
            g.nearest_magnet_distance_pct,
            g.open_to_flip_distance_pct,
            g.open_in_pin_zone,
            g.price_change_pct,
            g.price_range_pct,
            g.close_distance_to_flip_pct,
            g.close_distance_to_magnet1_pct,
            g.close_distance_to_magnet2_pct,
            v.vix_open,
            v.vix_close
        FROM gex_structure_daily g
        LEFT JOIN vix_daily v ON g.trade_date = v.trade_date
        WHERE g.symbol = ANY(%s)
          AND g.trade_date >= %s
          AND g.trade_date <= %s
        ORDER BY g.trade_date, g.symbol
    """

    df = pd.read_sql(query, conn, params=(symbols, start_date, end_date))
    conn.close()

    # If gex_structure_daily is empty, try gex_history fallback
    if len(df) == 0:
        logger.info("gex_structure_daily is empty, trying gex_history fallback...")
        df = load_gex_from_history_fallback(symbols, start_date, end_date)
        if len(df) > 0:
            logger.info(f"Successfully loaded {len(df)} records from gex_history fallback")
        else:
            logger.warning("No data found in either gex_structure_daily or gex_history")
        return df

    # Convert decimals to float
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = df[col].astype(float)
            except (ValueError, TypeError):
                pass

    logger.info(f"Loaded {len(df)} records for {symbols}")
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer ML features from raw GEX structure data.

    Creates features based on validated hypotheses:
    - H1: Positive gamma = smaller range
    - H2: Negative gamma = larger moves
    - H3: Pin zone = closes between magnets
    - H5: Multi-magnet oscillation
    """
    df = df.copy()
    df = df.sort_values(['symbol', 'trade_date']).reset_index(drop=True)

    # === Gamma Regime Features ===
    df['gamma_regime'] = np.where(df['net_gamma'] > 0, 'POSITIVE', 'NEGATIVE')
    df['gamma_regime_positive'] = (df['gamma_regime'] == 'POSITIVE').astype(int)
    df['gamma_regime_negative'] = (df['gamma_regime'] == 'NEGATIVE').astype(int)

    # Normalized gamma (scale-independent)
    df['net_gamma_normalized'] = df.groupby('symbol')['net_gamma'].transform(
        lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0
    )

    # === Gamma Imbalance Features ===
    # Call/Put gamma ratio
    df['gamma_ratio'] = df.apply(
        lambda r: abs(r['total_call_gamma']) / abs(r['total_put_gamma'])
        if r['total_put_gamma'] != 0 else 10.0,
        axis=1
    ).clip(0.1, 10.0)
    df['gamma_ratio_log'] = np.log(df['gamma_ratio'])

    # Gamma concentration (how much is in top magnets)
    df['top_magnet_concentration'] = df.apply(
        lambda r: (abs(r['magnet_1_gamma'] or 0) + abs(r['magnet_2_gamma'] or 0)) /
        (abs(r['total_call_gamma'] or 1) + abs(r['total_put_gamma'] or 1)),
        axis=1
    ).clip(0, 1)

    # === Distance Features ===
    # Normalized distances
    df['flip_distance_normalized'] = df['open_to_flip_distance_pct'].abs()
    df['near_flip'] = (df['flip_distance_normalized'] < 0.5).astype(int)

    # Magnet distance features
    df['magnet_distance_normalized'] = df['nearest_magnet_distance_pct'].abs()
    df['near_magnet'] = (df['magnet_distance_normalized'] < 0.3).astype(int)

    # Position relative to walls
    df['wall_spread_pct'] = df.apply(
        lambda r: (r['call_wall'] - r['put_wall']) / r['spot_open'] * 100
        if r['spot_open'] > 0 else 0,
        axis=1
    ).abs()

    # === VIX Features ===
    df['vix_level'] = df['vix_close'].fillna(df['vix_open']).fillna(20)
    df['vix_regime_low'] = (df['vix_level'] < 15).astype(int)
    df['vix_regime_mid'] = ((df['vix_level'] >= 15) & (df['vix_level'] <= 25)).astype(int)
    df['vix_regime_high'] = (df['vix_level'] > 25).astype(int)

    # Rolling VIX percentile
    df['vix_percentile'] = df.groupby('symbol')['vix_level'].transform(
        lambda x: x.rolling(30, min_periods=5).apply(
            lambda w: (w.iloc[-1] - w.min()) / (w.max() - w.min() + 0.01)
        )
    ).fillna(0.5)

    # === Momentum Features ===
    # Previous day's outcomes (for learning patterns)
    df['prev_price_change_pct'] = df.groupby('symbol')['price_change_pct'].shift(1)
    df['prev_price_range_pct'] = df.groupby('symbol')['price_range_pct'].shift(1)
    df['prev_gamma_regime'] = df.groupby('symbol')['gamma_regime'].shift(1)
    df['gamma_regime_changed'] = (df['gamma_regime'] != df['prev_gamma_regime']).astype(int)

    # Gamma momentum
    df['gamma_change_1d'] = df.groupby('symbol')['net_gamma_normalized'].diff()
    df['gamma_change_3d'] = df.groupby('symbol')['net_gamma_normalized'].transform(
        lambda x: x.rolling(3, min_periods=1).mean().diff()
    )

    # === Calendar Features ===
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['day_of_week'] = df['trade_date'].dt.dayofweek
    df['is_monday'] = (df['day_of_week'] == 0).astype(int)
    df['is_friday'] = (df['day_of_week'] == 4).astype(int)
    df['day_of_month'] = df['trade_date'].dt.day
    df['is_opex_week'] = ((df['day_of_month'] >= 15) & (df['day_of_month'] <= 21)).astype(int)
    df['is_month_end'] = (df['day_of_month'] >= 25).astype(int)

    # === Pin Zone Features ===
    df['pin_zone_width_pct'] = df.apply(
        lambda r: abs(r['magnet_1_strike'] - r['magnet_2_strike']) / r['spot_open'] * 100
        if r['magnet_1_strike'] and r['magnet_2_strike'] and r['spot_open'] > 0 else 0,
        axis=1
    )

    # Fill NaN
    df = df.fillna(0)

    return df


# ==============================================================================
# MODEL 1: DIRECTION PROBABILITY
# ==============================================================================

class DirectionModel:
    """
    Predicts market direction (UP/DOWN/FLAT) based on GEX structure.

    Based on validated hypotheses:
    - Positive gamma = mean-reverting (smaller moves)
    - Negative gamma = trending (larger moves)
    """

    FEATURE_COLUMNS = [
        'gamma_regime_positive', 'gamma_regime_negative',
        'net_gamma_normalized', 'gamma_ratio_log',
        'gamma_imbalance_pct', 'top_magnet_concentration',
        'flip_distance_normalized', 'near_flip',
        'num_magnets_above', 'num_magnets_below',
        'vix_level', 'vix_regime_low', 'vix_regime_mid', 'vix_regime_high',
        'gamma_change_1d', 'gamma_regime_changed',
        'prev_price_change_pct',
        'day_of_week', 'is_monday', 'is_friday', 'is_opex_week'
    ]

    # Thresholds for direction classification
    UP_THRESHOLD = 0.30
    DOWN_THRESHOLD = -0.30

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.is_trained = False
        self.feature_names = []

    def _classify_direction(self, price_change_pct: float) -> str:
        if price_change_pct >= self.UP_THRESHOLD:
            return Direction.UP.value
        elif price_change_pct <= self.DOWN_THRESHOLD:
            return Direction.DOWN.value
        return Direction.FLAT.value

    def train(self, df: pd.DataFrame, n_splits: int = 5) -> Dict:
        """Train direction prediction model"""
        print("\n" + "=" * 70)
        print("MODEL 1: DIRECTION PROBABILITY")
        print("=" * 70)

        # Create target
        df = df.copy()
        df['direction'] = df['price_change_pct'].apply(self._classify_direction)

        # Select features
        available = [c for c in self.FEATURE_COLUMNS if c in df.columns]
        self.feature_names = available

        X = df[available].values
        y = df['direction'].values

        # Handle NaN
        X = np.nan_to_num(X, nan=0.0)

        # Encode labels
        y_encoded = self.label_encoder.fit_transform(y)

        # Walk-forward validation
        tscv = TimeSeriesSplit(n_splits=n_splits)
        fold_accuracies = []
        all_y_true, all_y_pred = [], []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y_encoded[train_idx], y_encoded[test_idx]

            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            if HAS_XGBOOST:
                model = xgb.XGBClassifier(
                    n_estimators=100, max_depth=4, learning_rate=0.1,
                    min_child_weight=10, subsample=0.8, random_state=42, verbosity=0
                )
            else:
                model = GradientBoostingClassifier(
                    n_estimators=100, max_depth=4, learning_rate=0.1,
                    min_samples_leaf=10, random_state=42
                )

            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)

            fold_acc = accuracy_score(y_test, y_pred)
            fold_accuracies.append(fold_acc)
            all_y_true.extend(y_test)
            all_y_pred.extend(y_pred)

            print(f"  Fold {fold + 1}: {fold_acc:.1%}")

        # Final model on all data
        X_scaled = self.scaler.fit_transform(X)
        if HAS_XGBOOST:
            self.model = xgb.XGBClassifier(
                n_estimators=150, max_depth=4, learning_rate=0.1,
                min_child_weight=10, subsample=0.8, random_state=42, verbosity=0
            )
        else:
            self.model = GradientBoostingClassifier(
                n_estimators=150, max_depth=4, learning_rate=0.1,
                min_samples_leaf=10, random_state=42
            )
        self.model.fit(X_scaled, y_encoded)
        self.is_trained = True

        overall_acc = accuracy_score(all_y_true, all_y_pred)

        print(f"\n  Overall Accuracy: {overall_acc:.1%}")
        print(f"  Mean CV: {np.mean(fold_accuracies):.1%} (+/- {np.std(fold_accuracies):.1%})")
        print(f"  Classes: {list(self.label_encoder.classes_)}")

        return {
            'accuracy': overall_acc,
            'cv_mean': np.mean(fold_accuracies),
            'cv_std': np.std(fold_accuracies),
            'samples': len(df)
        }

    def predict(self, features: Dict) -> ModelPrediction:
        if not self.is_trained:
            raise ValueError("Model not trained")

        X = np.array([[features.get(f, 0) for f in self.feature_names]])
        X_scaled = self.scaler.transform(X)

        proba = self.model.predict_proba(X_scaled)[0]
        pred_idx = np.argmax(proba)
        pred_label = self.label_encoder.inverse_transform([pred_idx])[0]

        return ModelPrediction(
            model_name='direction',
            prediction=pred_label,
            confidence=float(proba[pred_idx]),
            probabilities={c: float(proba[i]) for i, c in enumerate(self.label_encoder.classes_)}
        )


# ==============================================================================
# MODEL 2: FLIP GRAVITY
# ==============================================================================

class FlipGravityModel:
    """
    Predicts probability that price moves toward the flip point.

    Note: Hypothesis H4 was NOT confirmed (44.4%), so this model
    may have limited predictive power. We train it anyway to
    let the model find any conditional patterns.
    """

    FEATURE_COLUMNS = [
        'gamma_regime_positive', 'gamma_regime_negative',
        'flip_distance_normalized', 'near_flip',
        'gamma_imbalance_pct', 'net_gamma_normalized',
        'vix_level', 'vix_regime_high',
        'gamma_change_1d', 'is_opex_week'
    ]

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_names = []

    def train(self, df: pd.DataFrame, n_splits: int = 5) -> Dict:
        """Train flip gravity model"""
        print("\n" + "=" * 70)
        print("MODEL 2: FLIP GRAVITY PROBABILITY")
        print("=" * 70)

        df = df.copy()

        # Target: Did price move toward flip?
        # Distance to flip decreased from open to close
        def moved_toward_flip(row):
            if row['flip_point'] is None or row['flip_point'] == 0:
                return 0
            dist_open = abs(row['spot_open'] - row['flip_point'])
            dist_close = abs(row['spot_close'] - row['flip_point'])
            return 1 if dist_close < dist_open else 0

        df['moved_toward_flip'] = df.apply(moved_toward_flip, axis=1)

        available = [c for c in self.FEATURE_COLUMNS if c in df.columns]
        self.feature_names = available

        X = np.nan_to_num(df[available].values, nan=0.0)
        y = df['moved_toward_flip'].values

        # Walk-forward validation
        tscv = TimeSeriesSplit(n_splits=n_splits)
        fold_accuracies = []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            if HAS_XGBOOST:
                model = xgb.XGBClassifier(
                    n_estimators=100, max_depth=3, learning_rate=0.1,
                    min_child_weight=20, random_state=42, verbosity=0
                )
            else:
                model = GradientBoostingClassifier(
                    n_estimators=100, max_depth=3, learning_rate=0.1,
                    min_samples_leaf=20, random_state=42
                )

            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)

            fold_acc = accuracy_score(y_test, y_pred)
            fold_accuracies.append(fold_acc)
            print(f"  Fold {fold + 1}: {fold_acc:.1%}")

        # Final model
        X_scaled = self.scaler.fit_transform(X)
        if HAS_XGBOOST:
            self.model = xgb.XGBClassifier(
                n_estimators=100, max_depth=3, learning_rate=0.1,
                min_child_weight=20, random_state=42, verbosity=0
            )
        else:
            self.model = GradientBoostingClassifier(
                n_estimators=100, max_depth=3, learning_rate=0.1,
                min_samples_leaf=20, random_state=42
            )
        self.model.fit(X_scaled, y)
        self.is_trained = True

        base_rate = y.mean()
        print(f"\n  Base Rate (moved toward flip): {base_rate:.1%}")
        print(f"  Mean CV Accuracy: {np.mean(fold_accuracies):.1%}")

        return {
            'base_rate': float(base_rate),
            'cv_mean': np.mean(fold_accuracies),
            'samples': len(df)
        }

    def predict(self, features: Dict) -> ModelPrediction:
        if not self.is_trained:
            raise ValueError("Model not trained")

        X = np.array([[features.get(f, 0) for f in self.feature_names]])
        X_scaled = self.scaler.transform(X)

        proba = self.model.predict_proba(X_scaled)[0]
        # Probability of moving toward flip (class 1)
        flip_prob = float(proba[1]) if len(proba) > 1 else float(proba[0])

        return ModelPrediction(
            model_name='flip_gravity',
            prediction='TOWARD' if flip_prob > 0.5 else 'AWAY',
            confidence=flip_prob,
            raw_value=flip_prob
        )


# ==============================================================================
# MODEL 3: MAGNET ATTRACTION
# ==============================================================================

class MagnetAttractionModel:
    """
    Predicts probability that price reaches/touches the nearest magnet.

    Based on H5 (89% interact with magnets in pin zones).
    """

    FEATURE_COLUMNS = [
        'open_in_pin_zone', 'pin_zone_width_pct',
        'near_magnet', 'magnet_distance_normalized',
        'top_magnet_concentration',
        'gamma_regime_positive', 'gamma_regime_negative',
        'vix_level', 'vix_regime_high',
        'is_opex_week'
    ]

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_names = []

    def train(self, df: pd.DataFrame, n_splits: int = 5) -> Dict:
        """Train magnet attraction model"""
        print("\n" + "=" * 70)
        print("MODEL 3: MAGNET ATTRACTION PROBABILITY")
        print("=" * 70)

        df = df.copy()

        # Target: Did price touch nearest magnet?
        # High or Low was within 0.1% of nearest magnet
        def touched_magnet(row):
            if row['nearest_magnet_strike'] is None or row['nearest_magnet_strike'] == 0:
                return 0
            magnet = row['nearest_magnet_strike']
            tolerance = row['spot_open'] * 0.001  # 0.1%
            return 1 if (row['spot_low'] <= magnet + tolerance and
                        row['spot_high'] >= magnet - tolerance) else 0

        df['touched_magnet'] = df.apply(touched_magnet, axis=1)

        available = [c for c in self.FEATURE_COLUMNS if c in df.columns]
        self.feature_names = available

        X = np.nan_to_num(df[available].values, nan=0.0)
        y = df['touched_magnet'].values

        # Walk-forward validation
        tscv = TimeSeriesSplit(n_splits=n_splits)
        fold_accuracies = []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            if HAS_XGBOOST:
                model = xgb.XGBClassifier(
                    n_estimators=100, max_depth=3, learning_rate=0.1,
                    min_child_weight=15, random_state=42, verbosity=0
                )
            else:
                model = GradientBoostingClassifier(
                    n_estimators=100, max_depth=3, learning_rate=0.1,
                    min_samples_leaf=15, random_state=42
                )

            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)

            fold_acc = accuracy_score(y_test, y_pred)
            fold_accuracies.append(fold_acc)
            print(f"  Fold {fold + 1}: {fold_acc:.1%}")

        # Final model
        X_scaled = self.scaler.fit_transform(X)
        if HAS_XGBOOST:
            self.model = xgb.XGBClassifier(
                n_estimators=100, max_depth=3, learning_rate=0.1,
                min_child_weight=15, random_state=42, verbosity=0
            )
        else:
            self.model = GradientBoostingClassifier(
                n_estimators=100, max_depth=3, learning_rate=0.1,
                min_samples_leaf=15, random_state=42
            )
        self.model.fit(X_scaled, y)
        self.is_trained = True

        base_rate = y.mean()
        print(f"\n  Base Rate (touched magnet): {base_rate:.1%}")
        print(f"  Mean CV Accuracy: {np.mean(fold_accuracies):.1%}")

        return {
            'base_rate': float(base_rate),
            'cv_mean': np.mean(fold_accuracies),
            'samples': len(df)
        }

    def predict(self, features: Dict) -> ModelPrediction:
        if not self.is_trained:
            raise ValueError("Model not trained")

        X = np.array([[features.get(f, 0) for f in self.feature_names]])
        X_scaled = self.scaler.transform(X)

        proba = self.model.predict_proba(X_scaled)[0]
        attract_prob = float(proba[1]) if len(proba) > 1 else float(proba[0])

        return ModelPrediction(
            model_name='magnet_attraction',
            prediction='ATTRACT' if attract_prob > 0.5 else 'MISS',
            confidence=attract_prob,
            raw_value=attract_prob
        )


# ==============================================================================
# MODEL 4: VOLATILITY ESTIMATE
# ==============================================================================

class VolatilityModel:
    """
    Predicts expected price range (volatility) for the day.

    Based on H1 (positive gamma = smaller range) and H2 (negative gamma = larger moves).
    This is a regression model, not classification.
    """

    FEATURE_COLUMNS = [
        'gamma_regime_positive', 'gamma_regime_negative',
        'net_gamma_normalized', 'gamma_imbalance_pct',
        'vix_level', 'vix_percentile', 'vix_regime_high',
        'prev_price_range_pct',
        'wall_spread_pct', 'pin_zone_width_pct',
        'day_of_week', 'is_opex_week', 'is_month_end'
    ]

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_names = []

    def train(self, df: pd.DataFrame, n_splits: int = 5) -> Dict:
        """Train volatility prediction model"""
        print("\n" + "=" * 70)
        print("MODEL 4: VOLATILITY ESTIMATE (Expected Range %)")
        print("=" * 70)

        df = df.copy()

        # Filter out bad data
        df = df[df['price_range_pct'] > 0].copy()

        available = [c for c in self.FEATURE_COLUMNS if c in df.columns]
        self.feature_names = available

        X = np.nan_to_num(df[available].values, nan=0.0)
        y = df['price_range_pct'].values

        # Walk-forward validation
        tscv = TimeSeriesSplit(n_splits=n_splits)
        fold_maes = []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            if HAS_XGBOOST:
                model = xgb.XGBRegressor(
                    n_estimators=100, max_depth=4, learning_rate=0.1,
                    min_child_weight=10, random_state=42, verbosity=0
                )
            else:
                model = GradientBoostingRegressor(
                    n_estimators=100, max_depth=4, learning_rate=0.1,
                    min_samples_leaf=10, random_state=42
                )

            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)

            mae = mean_absolute_error(y_test, y_pred)
            fold_maes.append(mae)
            print(f"  Fold {fold + 1}: MAE = {mae:.3f}%")

        # Final model
        X_scaled = self.scaler.fit_transform(X)
        if HAS_XGBOOST:
            self.model = xgb.XGBRegressor(
                n_estimators=150, max_depth=4, learning_rate=0.1,
                min_child_weight=10, random_state=42, verbosity=0
            )
        else:
            self.model = GradientBoostingRegressor(
                n_estimators=150, max_depth=4, learning_rate=0.1,
                min_samples_leaf=10, random_state=42
            )
        self.model.fit(X_scaled, y)
        self.is_trained = True

        avg_range = y.mean()
        print(f"\n  Average Historical Range: {avg_range:.2f}%")
        print(f"  Mean CV MAE: {np.mean(fold_maes):.3f}%")

        return {
            'avg_range': float(avg_range),
            'cv_mae': np.mean(fold_maes),
            'samples': len(df)
        }

    def predict(self, features: Dict) -> ModelPrediction:
        if not self.is_trained:
            raise ValueError("Model not trained")

        X = np.array([[features.get(f, 0) for f in self.feature_names]])
        X_scaled = self.scaler.transform(X)

        predicted_range = float(self.model.predict(X_scaled)[0])
        predicted_range = max(0.1, predicted_range)  # Minimum range

        return ModelPrediction(
            model_name='volatility',
            prediction=f"{predicted_range:.2f}%",
            confidence=1.0,  # Regression doesn't have confidence
            raw_value=predicted_range
        )


# ==============================================================================
# MODEL 5: PIN ZONE BEHAVIOR
# ==============================================================================

class PinZoneModel:
    """
    Predicts probability that price closes between magnets (pin zone behavior).

    Based on H3 (55.2% close between magnets) and H5 (89% interact with magnets).
    """

    FEATURE_COLUMNS = [
        'open_in_pin_zone', 'pin_zone_width_pct',
        'gamma_regime_positive', 'gamma_regime_negative',
        'top_magnet_concentration',
        'vix_level', 'vix_regime_low', 'vix_regime_mid',
        'gamma_change_1d', 'is_opex_week'
    ]

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_names = []

    def train(self, df: pd.DataFrame, n_splits: int = 5) -> Dict:
        """Train pin zone model"""
        print("\n" + "=" * 70)
        print("MODEL 5: PIN ZONE BEHAVIOR")
        print("=" * 70)

        df = df.copy()

        # Target: Did price close between the two largest magnets?
        def closed_in_zone(row):
            m1, m2 = row['magnet_1_strike'], row['magnet_2_strike']
            if not m1 or not m2:
                return 0
            low_mag, high_mag = min(m1, m2), max(m1, m2)
            return 1 if low_mag <= row['spot_close'] <= high_mag else 0

        df['closed_in_pin_zone'] = df.apply(closed_in_zone, axis=1)

        available = [c for c in self.FEATURE_COLUMNS if c in df.columns]
        self.feature_names = available

        X = np.nan_to_num(df[available].values, nan=0.0)
        y = df['closed_in_pin_zone'].values

        # Walk-forward validation
        tscv = TimeSeriesSplit(n_splits=n_splits)
        fold_accuracies = []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            if HAS_XGBOOST:
                model = xgb.XGBClassifier(
                    n_estimators=100, max_depth=3, learning_rate=0.1,
                    min_child_weight=15, random_state=42, verbosity=0
                )
            else:
                model = GradientBoostingClassifier(
                    n_estimators=100, max_depth=3, learning_rate=0.1,
                    min_samples_leaf=15, random_state=42
                )

            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)

            fold_acc = accuracy_score(y_test, y_pred)
            fold_accuracies.append(fold_acc)
            print(f"  Fold {fold + 1}: {fold_acc:.1%}")

        # Final model
        X_scaled = self.scaler.fit_transform(X)
        if HAS_XGBOOST:
            self.model = xgb.XGBClassifier(
                n_estimators=100, max_depth=3, learning_rate=0.1,
                min_child_weight=15, random_state=42, verbosity=0
            )
        else:
            self.model = GradientBoostingClassifier(
                n_estimators=100, max_depth=3, learning_rate=0.1,
                min_samples_leaf=15, random_state=42
            )
        self.model.fit(X_scaled, y)
        self.is_trained = True

        base_rate = y.mean()
        print(f"\n  Base Rate (closed in pin zone): {base_rate:.1%}")
        print(f"  Mean CV Accuracy: {np.mean(fold_accuracies):.1%}")

        return {
            'base_rate': float(base_rate),
            'cv_mean': np.mean(fold_accuracies),
            'samples': len(df)
        }

    def predict(self, features: Dict) -> ModelPrediction:
        if not self.is_trained:
            raise ValueError("Model not trained")

        X = np.array([[features.get(f, 0) for f in self.feature_names]])
        X_scaled = self.scaler.transform(X)

        proba = self.model.predict_proba(X_scaled)[0]
        pin_prob = float(proba[1]) if len(proba) > 1 else float(proba[0])

        return ModelPrediction(
            model_name='pin_zone',
            prediction='PIN' if pin_prob > 0.5 else 'BREAK',
            confidence=pin_prob,
            raw_value=pin_prob
        )


# ==============================================================================
# COMBINED SIGNAL GENERATOR
# ==============================================================================

class GEXSignalGenerator:
    """
    Combines all 5 models into trading signals.

    Uses probability outputs from each model to generate:
    - Trade direction (LONG/SHORT)
    - Conviction score (0-1)
    - Expected outcome targets
    """

    def __init__(self):
        self.direction_model = DirectionModel()
        self.flip_gravity_model = FlipGravityModel()
        self.magnet_attraction_model = MagnetAttractionModel()
        self.volatility_model = VolatilityModel()
        self.pin_zone_model = PinZoneModel()
        self.is_trained = False

    def train(
        self,
        symbols: List[str] = ['SPX', 'SPY'],
        start_date: str = '2020-01-01',
        end_date: str = None
    ) -> Dict:
        """Train all 5 models"""
        print("=" * 70)
        print("GEX SIGNAL GENERATOR - TRAINING ALL 5 MODELS")
        print("=" * 70)
        print(f"Symbols: {symbols}")
        print(f"Date range: {start_date} to {end_date or 'present'}")

        # Load data
        df = load_gex_structure_data(symbols, start_date, end_date)
        print(f"\nLoaded {len(df)} total records")

        # Engineer features
        df = engineer_features(df)

        # Train each model
        results = {}
        results['direction'] = self.direction_model.train(df)
        results['flip_gravity'] = self.flip_gravity_model.train(df)
        results['magnet_attraction'] = self.magnet_attraction_model.train(df)
        results['volatility'] = self.volatility_model.train(df)
        results['pin_zone'] = self.pin_zone_model.train(df)

        self.is_trained = True

        # Summary
        print("\n" + "=" * 70)
        print("TRAINING SUMMARY")
        print("=" * 70)
        for name, res in results.items():
            if 'accuracy' in res:
                print(f"  {name}: Accuracy={res.get('accuracy', res.get('cv_mean', 0)):.1%}")
            elif 'cv_mae' in res:
                print(f"  {name}: MAE={res['cv_mae']:.3f}%")
            else:
                print(f"  {name}: CV={res.get('cv_mean', 0):.1%}")

        return results

    def predict(self, features: Dict) -> CombinedSignal:
        """
        Generate combined trading signal from all 5 models.

        Args:
            features: Dict of feature values for prediction

        Returns:
            CombinedSignal with all predictions and recommendation
        """
        if not self.is_trained:
            raise ValueError("Models not trained")

        # Get predictions from each model
        direction = self.direction_model.predict(features)
        flip_gravity = self.flip_gravity_model.predict(features)
        magnet_attraction = self.magnet_attraction_model.predict(features)
        volatility = self.volatility_model.predict(features)
        pin_zone = self.pin_zone_model.predict(features)

        # Calculate conviction score
        # Higher when models agree and have high confidence
        conviction_factors = []

        # Direction confidence
        conviction_factors.append(direction.confidence)

        # If in pin zone with high probability, reduce conviction (choppy)
        if pin_zone.raw_value > 0.7:
            conviction_factors.append(0.5)  # Reduce conviction in strong pin zones
        else:
            conviction_factors.append(0.8)

        # Magnet attraction - if high, price has target
        if magnet_attraction.raw_value > 0.7:
            conviction_factors.append(0.9)
        else:
            conviction_factors.append(0.6)

        # FlipGravity - measures pull toward GEX flip point
        # High gravity = strong directional pull, good for directional trades
        # Low gravity = price may stay flat, reduce conviction
        flip_gravity_score = flip_gravity.raw_value
        if flip_gravity_score > 0.7:
            conviction_factors.append(0.9)  # Strong pull toward flip - high conviction
        elif flip_gravity_score > 0.4:
            conviction_factors.append(0.7)  # Moderate pull - decent conviction
        else:
            conviction_factors.append(0.5)  # Weak gravity - lower conviction

        # Volatility-based adjustment
        exp_vol = volatility.raw_value
        if exp_vol < 0.5:  # Very low expected vol
            conviction_factors.append(0.5)  # Low conviction in quiet markets
        elif exp_vol > 2.0:  # High vol
            conviction_factors.append(0.7)  # Moderate conviction in volatile markets
        else:
            conviction_factors.append(0.8)

        overall_conviction = np.mean(conviction_factors)

        # Determine trade recommendation
        # Use probability-based approach instead of hard classification
        # This generates more signals when there's directional edge

        # Get raw probabilities from direction model
        dir_probs = direction.probabilities or {}
        up_prob = dir_probs.get('UP', 0.33)
        down_prob = dir_probs.get('DOWN', 0.33)
        flat_prob = dir_probs.get('FLAT', 0.34)

        # Directional edge = difference between UP and DOWN
        directional_edge = abs(up_prob - down_prob)

        # Signal thresholds (tunable)
        MIN_DIRECTIONAL_PROB = 0.35  # Min probability for direction
        MIN_EDGE = 0.10              # Min edge over opposite direction
        MIN_CONVICTION = 0.55        # Min overall conviction

        if up_prob >= MIN_DIRECTIONAL_PROB and up_prob > down_prob + MIN_EDGE:
            if overall_conviction >= MIN_CONVICTION:
                recommendation = 'LONG'
            else:
                recommendation = 'STAY_OUT'
        elif down_prob >= MIN_DIRECTIONAL_PROB and down_prob > up_prob + MIN_EDGE:
            if overall_conviction >= MIN_CONVICTION:
                recommendation = 'SHORT'
            else:
                recommendation = 'STAY_OUT'
        elif direction.prediction == Direction.UP.value and direction.confidence > 0.6:
            # Fallback to high-confidence predictions
            recommendation = 'LONG' if overall_conviction >= MIN_CONVICTION else 'STAY_OUT'
        elif direction.prediction == Direction.DOWN.value and direction.confidence > 0.6:
            recommendation = 'SHORT' if overall_conviction >= MIN_CONVICTION else 'STAY_OUT'
        else:
            recommendation = 'STAY_OUT'

        return CombinedSignal(
            direction_prediction=direction.prediction,
            direction_confidence=direction.confidence,
            flip_gravity_prob=flip_gravity.raw_value,
            magnet_attraction_prob=magnet_attraction.raw_value,
            expected_volatility_pct=volatility.raw_value,
            pin_zone_prob=pin_zone.raw_value,
            overall_conviction=overall_conviction,
            trade_recommendation=recommendation
        )

    def save(self, filepath: str = 'models/gex_signal_generator.joblib'):
        """Save all models to disk"""
        if not self.is_trained:
            raise ValueError("Models not trained")

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        model_data = {
            'direction_model': {
                'model': self.direction_model.model,
                'scaler': self.direction_model.scaler,
                'label_encoder': self.direction_model.label_encoder,
                'feature_names': self.direction_model.feature_names
            },
            'flip_gravity_model': {
                'model': self.flip_gravity_model.model,
                'scaler': self.flip_gravity_model.scaler,
                'feature_names': self.flip_gravity_model.feature_names
            },
            'magnet_attraction_model': {
                'model': self.magnet_attraction_model.model,
                'scaler': self.magnet_attraction_model.scaler,
                'feature_names': self.magnet_attraction_model.feature_names
            },
            'volatility_model': {
                'model': self.volatility_model.model,
                'scaler': self.volatility_model.scaler,
                'feature_names': self.volatility_model.feature_names
            },
            'pin_zone_model': {
                'model': self.pin_zone_model.model,
                'scaler': self.pin_zone_model.scaler,
                'feature_names': self.pin_zone_model.feature_names
            }
        }

        joblib.dump(model_data, filepath)
        print(f"\nModels saved to {filepath}")

    def load(self, filepath: str = 'models/gex_signal_generator.joblib'):
        """Load all models from disk"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Model file not found: {filepath}")

        model_data = joblib.load(filepath)

        # Load direction model
        self.direction_model.model = model_data['direction_model']['model']
        self.direction_model.scaler = model_data['direction_model']['scaler']
        self.direction_model.label_encoder = model_data['direction_model']['label_encoder']
        self.direction_model.feature_names = model_data['direction_model']['feature_names']
        self.direction_model.is_trained = True

        # Load flip gravity model
        self.flip_gravity_model.model = model_data['flip_gravity_model']['model']
        self.flip_gravity_model.scaler = model_data['flip_gravity_model']['scaler']
        self.flip_gravity_model.feature_names = model_data['flip_gravity_model']['feature_names']
        self.flip_gravity_model.is_trained = True

        # Load magnet attraction model
        self.magnet_attraction_model.model = model_data['magnet_attraction_model']['model']
        self.magnet_attraction_model.scaler = model_data['magnet_attraction_model']['scaler']
        self.magnet_attraction_model.feature_names = model_data['magnet_attraction_model']['feature_names']
        self.magnet_attraction_model.is_trained = True

        # Load volatility model
        self.volatility_model.model = model_data['volatility_model']['model']
        self.volatility_model.scaler = model_data['volatility_model']['scaler']
        self.volatility_model.feature_names = model_data['volatility_model']['feature_names']
        self.volatility_model.is_trained = True

        # Load pin zone model
        self.pin_zone_model.model = model_data['pin_zone_model']['model']
        self.pin_zone_model.scaler = model_data['pin_zone_model']['scaler']
        self.pin_zone_model.feature_names = model_data['pin_zone_model']['feature_names']
        self.pin_zone_model.is_trained = True

        self.is_trained = True
        print(f"Models loaded from {filepath}")

    def save_to_db(self, metrics: dict = None, training_records: int = None):
        """Save models to PostgreSQL database for persistence across Render deploys"""
        if not self.is_trained:
            raise ValueError("Models not trained")

        try:
            from quant.model_persistence import save_model_to_db, MODEL_GEX_PROBABILITY

            model_data = {
                'direction_model': {
                    'model': self.direction_model.model,
                    'scaler': self.direction_model.scaler,
                    'label_encoder': self.direction_model.label_encoder,
                    'feature_names': self.direction_model.feature_names
                },
                'flip_gravity_model': {
                    'model': self.flip_gravity_model.model,
                    'scaler': self.flip_gravity_model.scaler,
                    'feature_names': self.flip_gravity_model.feature_names
                },
                'magnet_attraction_model': {
                    'model': self.magnet_attraction_model.model,
                    'scaler': self.magnet_attraction_model.scaler,
                    'feature_names': self.magnet_attraction_model.feature_names
                },
                'volatility_model': {
                    'model': self.volatility_model.model,
                    'scaler': self.volatility_model.scaler,
                    'feature_names': self.volatility_model.feature_names
                },
                'pin_zone_model': {
                    'model': self.pin_zone_model.model,
                    'scaler': self.pin_zone_model.scaler,
                    'feature_names': self.pin_zone_model.feature_names
                }
            }

            return save_model_to_db(
                MODEL_GEX_PROBABILITY,
                model_data,
                metrics=metrics,
                training_records=training_records
            )
        except Exception as e:
            print(f"Error saving to database: {e}")
            return False

    def load_from_db(self) -> bool:
        """Load models from PostgreSQL database"""
        try:
            from quant.model_persistence import load_model_from_db, MODEL_GEX_PROBABILITY

            model_data = load_model_from_db(MODEL_GEX_PROBABILITY)
            if model_data is None:
                return False

            # Load direction model
            self.direction_model.model = model_data['direction_model']['model']
            self.direction_model.scaler = model_data['direction_model']['scaler']
            self.direction_model.label_encoder = model_data['direction_model']['label_encoder']
            self.direction_model.feature_names = model_data['direction_model']['feature_names']
            self.direction_model.is_trained = True

            # Load flip gravity model
            self.flip_gravity_model.model = model_data['flip_gravity_model']['model']
            self.flip_gravity_model.scaler = model_data['flip_gravity_model']['scaler']
            self.flip_gravity_model.feature_names = model_data['flip_gravity_model']['feature_names']
            self.flip_gravity_model.is_trained = True

            # Load magnet attraction model
            self.magnet_attraction_model.model = model_data['magnet_attraction_model']['model']
            self.magnet_attraction_model.scaler = model_data['magnet_attraction_model']['scaler']
            self.magnet_attraction_model.feature_names = model_data['magnet_attraction_model']['feature_names']
            self.magnet_attraction_model.is_trained = True

            # Load volatility model
            self.volatility_model.model = model_data['volatility_model']['model']
            self.volatility_model.scaler = model_data['volatility_model']['scaler']
            self.volatility_model.feature_names = model_data['volatility_model']['feature_names']
            self.volatility_model.is_trained = True

            # Load pin zone model
            self.pin_zone_model.model = model_data['pin_zone_model']['model']
            self.pin_zone_model.scaler = model_data['pin_zone_model']['scaler']
            self.pin_zone_model.feature_names = model_data['pin_zone_model']['feature_names']
            self.pin_zone_model.is_trained = True

            self.is_trained = True
            return True

        except Exception as e:
            print(f"Error loading from database: {e}")
            return False


# ==============================================================================
# WRAPPER CLASS FOR SHARED ENGINE INTEGRATION
# ==============================================================================

class GEXProbabilityModels:
    """
    Wrapper class for WATCHTOWER/GLORY integration.

    Auto-loads trained models from database on initialization.
    Provides simplified interface for probability predictions.

    Usage:
        models = GEXProbabilityModels()  # Auto-loads from DB
        result = models.predict_magnet_attraction(strike, spot_price, gamma_structure)
    """

    _instance = None  # Singleton instance

    def __new__(cls):
        """Singleton pattern - only one instance loads models"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._generator = GEXSignalGenerator()
        self._load_attempted = False
        self._load_successful = False
        self._last_load_time = None
        self._model_info = None
        self._initialized = True

        # Attempt to load from database
        self._try_load_from_db()

    def _try_load_from_db(self) -> bool:
        """Attempt to load models from database"""
        if self._load_attempted:
            return self._load_successful

        self._load_attempted = True
        try:
            success = self._generator.load_from_db()
            if success:
                self._load_successful = True
                self._last_load_time = datetime.now()
                # Get model info
                try:
                    from quant.model_persistence import get_model_info, MODEL_GEX_PROBABILITY
                    self._model_info = get_model_info(MODEL_GEX_PROBABILITY)
                except:
                    pass
                logger.info("GEXProbabilityModels: Loaded trained models from database")
            else:
                logger.warning("GEXProbabilityModels: No trained models in database")
            return success
        except Exception as e:
            logger.warning(f"GEXProbabilityModels: Failed to load from DB: {e}")
            return False

    @property
    def is_trained(self) -> bool:
        """Check if models are trained and ready"""
        return self._generator.is_trained

    @property
    def model_info(self) -> Optional[Dict]:
        """Get model metadata"""
        return self._model_info

    def predict_magnet_attraction(
        self,
        strike: float,
        spot_price: float,
        gamma_structure: Dict
    ) -> Optional[Dict]:
        """
        Predict probability of price being attracted to a strike.

        Args:
            strike: Strike price to evaluate
            spot_price: Current spot price
            gamma_structure: Dict containing gamma data with keys:
                - net_gamma: Total net gamma
                - flip_point: Gamma flip point
                - magnets: List of magnet strikes
                - vix: Current VIX
                - gamma_regime: 'POSITIVE', 'NEGATIVE', or 'NEUTRAL'

        Returns:
            Dict with 'probability' key (0-1), or None if not trained
        """
        if not self._generator.is_trained:
            return None

        try:
            # Build features dict from gamma_structure
            features = self._build_features(strike, spot_price, gamma_structure)

            # Get magnet attraction prediction
            prediction = self._generator.magnet_attraction_model.predict(features)

            return {
                'probability': prediction.confidence,
                'prediction': prediction.prediction,
                'model': 'magnet_attraction'
            }

        except Exception as e:
            logger.debug(f"Magnet attraction prediction failed: {e}")
            return None

    def predict_combined(
        self,
        spot_price: float,
        gamma_structure: Dict
    ) -> Optional[CombinedSignal]:
        """
        Get combined signal from all 5 models.

        Args:
            spot_price: Current spot price
            gamma_structure: Dict with gamma data

        Returns:
            CombinedSignal with direction, confidence, and recommendation
        """
        if not self._generator.is_trained:
            return None

        try:
            features = self._build_features(spot_price, spot_price, gamma_structure)
            return self._generator.predict(features)
        except Exception as e:
            logger.debug(f"Combined prediction failed: {e}")
            return None

    def _build_features(
        self,
        strike: float,
        spot_price: float,
        gamma_structure: Dict
    ) -> Dict:
        """Build feature dict for model prediction"""
        net_gamma = gamma_structure.get('net_gamma', 0)
        flip_point = gamma_structure.get('flip_point', spot_price)
        vix = gamma_structure.get('vix', 20)
        gamma_regime = gamma_structure.get('gamma_regime', 'NEUTRAL')
        magnets = gamma_structure.get('magnets', [])
        total_gamma = gamma_structure.get('total_gamma', abs(net_gamma) or 1)
        expected_move = gamma_structure.get('expected_move', spot_price * 0.01)

        # Find nearest magnet
        nearest_magnet = None
        nearest_distance = float('inf')
        for m in magnets:
            mag_strike = m.get('strike', m) if isinstance(m, dict) else m
            dist = abs(mag_strike - spot_price)
            if dist < nearest_distance:
                nearest_distance = dist
                nearest_magnet = mag_strike

        # Calculate derived features
        distance_to_flip = abs(spot_price - flip_point) / spot_price if flip_point else 0
        magnet_distance = nearest_distance / spot_price if nearest_magnet else 0.1

        return {
            # Gamma features
            'gamma_regime_positive': 1 if gamma_regime == 'POSITIVE' else 0,
            'gamma_regime_negative': 1 if gamma_regime == 'NEGATIVE' else 0,
            'net_gamma_normalized': net_gamma / total_gamma if total_gamma else 0,
            'gamma_ratio_log': np.log1p(abs(net_gamma) / (total_gamma or 1)),

            # Position features
            'distance_to_flip': distance_to_flip,
            'distance_to_flip_pct': distance_to_flip * 100,
            'above_flip': 1 if spot_price > flip_point else 0,
            'near_magnet': 1 if magnet_distance < 0.005 else 0,
            'magnet_distance_normalized': magnet_distance,
            'nearest_magnet_strike': nearest_magnet or spot_price,

            # Volatility features
            'vix_level': vix,
            'vix_regime_high': 1 if vix > 25 else 0,
            'expected_move_pct': (expected_move / spot_price * 100) if spot_price else 1,

            # Pin zone features
            'open_in_pin_zone': 1 if len(magnets) >= 2 else 0,
            'pin_zone_width_pct': magnet_distance * 100,
            'top_magnet_concentration': 0.5,  # Default

            # Time features
            'is_opex_week': 0,  # Would need date calculation
            'day_of_week': datetime.now().weekday(),

            # Price features
            'spot_open': spot_price,
            'spot_price': spot_price,
            'strike': strike,
        }

    def get_model_staleness_hours(self) -> Optional[float]:
        """Get hours since model was trained"""
        if not self._model_info:
            return None
        try:
            created_at = datetime.fromisoformat(self._model_info['created_at'].replace('Z', '+00:00'))
            return (datetime.now(created_at.tzinfo) - created_at).total_seconds() / 3600
        except:
            return None

    def needs_retraining(self, max_age_hours: float = 168) -> bool:
        """Check if models need retraining (default: 7 days)"""
        staleness = self.get_model_staleness_hours()
        if staleness is None:
            return True  # No model info means needs training
        return staleness > max_age_hours


def main():
    """Train all GEX probability models"""
    import argparse

    parser = argparse.ArgumentParser(description='Train GEX Probability Models')
    parser.add_argument('--symbols', type=str, nargs='+', default=['SPX', 'SPY'],
                        help='Symbols to train on')
    parser.add_argument('--start', type=str, default='2020-01-01', help='Start date')
    parser.add_argument('--end', type=str, default=None, help='End date')
    parser.add_argument('--save', type=str, default='models/gex_signal_generator.joblib',
                        help='Path to save models')
    args = parser.parse_args()

    # Initialize generator
    generator = GEXSignalGenerator()

    # Train
    results = generator.train(
        symbols=args.symbols,
        start_date=args.start,
        end_date=args.end
    )

    # Save
    generator.save(args.save)

    # Example prediction
    print("\n" + "=" * 70)
    print("EXAMPLE PREDICTION")
    print("=" * 70)

    # Mock features for demonstration
    example_features = {
        'gamma_regime_positive': 1,
        'gamma_regime_negative': 0,
        'net_gamma_normalized': 0.5,
        'gamma_ratio_log': 0.2,
        'gamma_imbalance_pct': 20,
        'top_magnet_concentration': 0.4,
        'flip_distance_normalized': 1.2,
        'near_flip': 0,
        'num_magnets_above': 3,
        'num_magnets_below': 2,
        'vix_level': 18,
        'vix_regime_low': 0,
        'vix_regime_mid': 1,
        'vix_regime_high': 0,
        'gamma_change_1d': 0.1,
        'gamma_regime_changed': 0,
        'prev_price_change_pct': -0.2,
        'day_of_week': 2,
        'is_monday': 0,
        'is_friday': 0,
        'is_opex_week': 0,
        'open_in_pin_zone': 1,
        'pin_zone_width_pct': 1.5,
        'near_magnet': 1,
        'magnet_distance_normalized': 0.2,
        'vix_percentile': 0.4,
        'prev_price_range_pct': 1.2,
        'wall_spread_pct': 3.0,
        'is_month_end': 0
    }

    signal = generator.predict(example_features)

    print(f"\n  Direction: {signal.direction_prediction} ({signal.direction_confidence:.1%})")
    print(f"  Expected Volatility: {signal.expected_volatility_pct:.2f}%")
    print(f"  Flip Gravity Prob: {signal.flip_gravity_prob:.1%}")
    print(f"  Magnet Attraction Prob: {signal.magnet_attraction_prob:.1%}")
    print(f"  Pin Zone Prob: {signal.pin_zone_prob:.1%}")
    print(f"  Overall Conviction: {signal.overall_conviction:.1%}")
    print(f"  Recommendation: {signal.trade_recommendation}")

    return generator


if __name__ == '__main__':
    main()
