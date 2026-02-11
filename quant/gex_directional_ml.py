"""
GEX Directional ML Model - Predict Market Direction from Gamma Structure
=========================================================================

PURPOSE:
Train an ML model that predicts daily market direction (BULLISH/BEARISH/FLAT)
based on GEX structure at market open.

USE CASE:
- A directional trading bot that uses GEX patterns to determine:
  * When to go long (bullish GEX pattern)
  * When to go short (bearish GEX pattern)
  * When to stay flat (neutral GEX pattern)

FEATURES USED (V2 - 25 features):
- GEX regime (positive/negative/neutral)
- Net GEX normalized (scale-independent)
- Distance to flip point (%)
- Distance to call wall / put wall (%)
- Price position between walls
- Magnet Theory: GEX ratio, log ratio, asymmetry, wall proximity
- VIX level + regime indicators
- Volatility Risk Premium (V2: expected_move - realized_vol)
- Cyclical day encoding (V2: sin/cos, replaces integer day_of_week)
- Opening gap (spot vs prev close)
- Calendar: is_monday, is_friday, is_opex_week

V2 CHANGES:
- REMOVED: vix_percentile (data leakage - hardcoded 0.5 at inference)
- REMOVED: gex_change_1d, gex_regime_changed (always 0 at inference)
- REMOVED: integer day_of_week (Friday-Monday discontinuity)
- ADDED: volatility_risk_premium (strongest edge signal for options)
- ADDED: cyclical day encoding (sin/cos, matches WISDOM/Prophet/ORION)
- ADDED: sample_weight for 3-class imbalance handling
- ADDED: isotonic calibration for reliable confidence values
- ADDED: Brier score evaluation on held-out CV folds

LABELS:
- BULLISH: close > open by threshold (e.g., +0.3%)
- BEARISH: close < open by threshold (e.g., -0.3%)
- FLAT: close ≈ open (within threshold)

Author: AlphaGEX Quant
"""

import os
import sys
import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import Counter
import warnings

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, brier_score_loss
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.calibration import CalibratedClassifierCV
import joblib

# XGBoost for all ML in AlphaGEX
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    print("Warning: XGBoost not installed. Using sklearn GradientBoosting as fallback.")

# Fallback to sklearn GradientBoosting
from sklearn.ensemble import GradientBoostingClassifier

# Add parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')


class Direction(Enum):
    """Market direction classification"""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    FLAT = "FLAT"


@dataclass
class DirectionalPrediction:
    """Prediction result from the model"""
    direction: Direction
    confidence: float  # 0-1 probability
    probabilities: Dict[str, float]  # Per-class probabilities
    features_used: Dict[str, float]  # Feature values that led to prediction


@dataclass
class TrainingResult:
    """Results from model training"""
    accuracy: float
    precision_by_class: Dict[str, float]
    recall_by_class: Dict[str, float]
    feature_importance: Dict[str, float]
    confusion_matrix: np.ndarray
    training_samples: int
    test_samples: int
    brier_score: float = 0.0  # V2: multiclass Brier on held-out CV folds
    feature_version: str = 'V2'  # V2: track which feature set was used


class GEXDirectionalPredictor:
    """
    ML model that predicts market direction from GEX structure.

    Uses historical GEX patterns and their associated price outcomes
    to predict whether the market will be bullish, bearish, or flat.
    """

    # Direction thresholds (percentage price change)
    BULLISH_THRESHOLD = 0.30  # +0.3% or more = bullish
    BEARISH_THRESHOLD = -0.30  # -0.3% or more = bearish

    # Feature version tracking (V1 = original 26, V2 = fixed 25)
    FEATURE_VERSION = 'V2'

    # V2 Changes:
    #   REMOVED: vix_percentile (data leakage - hardcoded 0.5 at inference)
    #   REMOVED: gex_change_1d (always 0 at inference - no prior-day context)
    #   REMOVED: gex_regime_changed (always 0 at inference - no prior-day context)
    #   REMOVED: day_of_week (integer creates Friday-Monday discontinuity)
    #   ADDED: day_of_week_sin, day_of_week_cos (cyclical encoding, matches WISDOM/Prophet/ORION)
    #   ADDED: volatility_risk_premium (VRP = expected_move - realized_vol, strongest edge signal)

    # Feature columns used for prediction
    FEATURE_COLUMNS = [
        # Core GEX features
        'gex_normalized',
        'gex_regime_positive',
        'gex_regime_negative',
        'distance_to_flip_pct',
        'distance_to_call_wall_pct',
        'distance_to_put_wall_pct',
        'between_walls',
        'above_call_wall',
        'below_put_wall',

        # MAGNET THEORY features (key for directional prediction)
        'gex_ratio',              # put_gex / call_gex - primary signal
        'gex_ratio_log',          # log(gex_ratio) for better scaling
        'near_put_wall',          # within proximity of put wall
        'near_call_wall',         # within proximity of call wall
        'gex_asymmetry_strong',   # ratio > 1.5 or < 0.67

        # Market context
        'vix_level',
        'volatility_risk_premium',  # V2: VRP = expected_move - realized_vol
        'vix_regime_low',         # VIX < 15 (low vol, trending)
        'vix_regime_mid',         # VIX 15-25 (best risk-adjusted)
        'vix_regime_high',        # VIX > 25 (high vol, mean-revert)

        # Momentum features (V2: removed gex_change_1d, gex_regime_changed)
        'spot_vs_prev_close_pct',

        # Calendar features (V2: cyclical encoding)
        'day_of_week_sin',        # V2: sin(2*pi*dow/5) - cyclical
        'day_of_week_cos',        # V2: cos(2*pi*dow/5) - cyclical
        'is_monday',
        'is_friday',
        'is_opex_week',
    ]

    def __init__(self, ticker: str = 'SPY'):
        """
        Initialize the predictor.

        Args:
            ticker: Symbol to predict (SPY or SPX)
        """
        self.ticker = ticker
        self.model = None
        self.calibrated_model = None  # V2: isotonic calibration wrapper
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.feature_importance = {}
        self.is_trained = False

    def get_connection(self):
        """Get database connection"""
        import psycopg2
        database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL not set")
        return psycopg2.connect(database_url)

    def load_training_data(
        self,
        start_date: str = '2022-01-01',
        end_date: str = None
    ) -> pd.DataFrame:
        """
        Load and prepare training data from database.

        Joins GEX data with price data and VIX to create training dataset.

        Returns:
            DataFrame with features and direction labels
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        conn = self.get_connection()

        # Load GEX data
        gex_query = """
            SELECT
                trade_date,
                symbol,
                spot_price,
                net_gex,
                call_gex,
                put_gex,
                call_wall,
                put_wall,
                flip_point,
                gex_normalized,
                gex_regime,
                distance_to_flip_pct,
                above_call_wall,
                below_put_wall,
                between_walls
            FROM gex_daily
            WHERE symbol = %s
              AND trade_date >= %s
              AND trade_date <= %s
            ORDER BY trade_date
        """

        try:
            gex_df = pd.read_sql(gex_query, conn, params=(self.ticker, start_date, end_date))
        except Exception as e:
            logger.warning(f"gex_daily table not found, will calculate from ORAT: {e}")
            gex_df = self._calculate_gex_from_orat(conn, start_date, end_date)

        # Load price data
        price_query = """
            SELECT
                trade_date,
                symbol,
                open,
                high,
                low,
                close,
                volume
            FROM underlying_prices
            WHERE symbol = %s
              AND trade_date >= %s
              AND trade_date <= %s
            ORDER BY trade_date
        """
        price_df = pd.read_sql(price_query, conn, params=(self.ticker, start_date, end_date))

        # Load VIX data
        vix_query = """
            SELECT
                trade_date,
                close as vix_close,
                open as vix_open
            FROM vix_history
            WHERE trade_date >= %s
              AND trade_date <= %s
            ORDER BY trade_date
        """
        vix_df = pd.read_sql(vix_query, conn, params=(start_date, end_date))

        conn.close()

        # Merge datasets
        df = gex_df.merge(price_df, on=['trade_date', 'symbol'], how='inner')
        df = df.merge(vix_df, on='trade_date', how='left')

        if len(df) == 0:
            raise ValueError(f"No data found for {self.ticker} between {start_date} and {end_date}")

        logger.info(f"Loaded {len(df)} trading days of data")

        return df

    def _calculate_gex_from_orat(
        self,
        conn,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Calculate GEX directly from ORAT options data if gex_daily doesn't exist.
        """
        from quant.chronicles_gex_calculator import ChroniclesGEXCalculator

        calc = ChroniclesGEXCalculator(self.ticker)

        # Get list of trading dates
        dates_query = """
            SELECT DISTINCT trade_date
            FROM orat_options_eod
            WHERE ticker = %s
              AND trade_date >= %s
              AND trade_date <= %s
            ORDER BY trade_date
        """
        dates_df = pd.read_sql(dates_query, conn, params=(self.ticker, start_date, end_date))

        gex_records = []
        for trade_date in dates_df['trade_date']:
            gex = calc.calculate_gex_for_date(str(trade_date), dte_max=7)
            if gex:
                gex_records.append({
                    'trade_date': trade_date,
                    'symbol': self.ticker,
                    'spot_price': gex.spot_price,
                    'net_gex': gex.net_gex,
                    'call_gex': gex.call_gex,
                    'put_gex': gex.put_gex,
                    'call_wall': gex.call_wall,
                    'put_wall': gex.put_wall,
                    'flip_point': gex.flip_point,
                    'gex_normalized': gex.gex_normalized,
                    'gex_regime': gex.gex_regime,
                    'distance_to_flip_pct': gex.distance_to_flip_pct,
                    'above_call_wall': gex.above_call_wall,
                    'below_put_wall': gex.below_put_wall,
                    'between_walls': gex.between_walls,
                })

        return pd.DataFrame(gex_records)

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Engineer features for ML training.

        Creates derived features from raw GEX and price data.
        """
        df = df.copy()
        df = df.sort_values('trade_date').reset_index(drop=True)

        # === Direction Label (TARGET) ===
        df['price_change_pct'] = (df['close'] - df['open']) / df['open'] * 100
        df['direction'] = df['price_change_pct'].apply(self._classify_direction)

        # === GEX Regime Features ===
        df['gex_regime_positive'] = (df['gex_regime'] == 'POSITIVE').astype(int)
        df['gex_regime_negative'] = (df['gex_regime'] == 'NEGATIVE').astype(int)

        # === Distance Features ===
        # Distance to call wall (resistance)
        df['distance_to_call_wall_pct'] = (
            (df['call_wall'] - df['spot_price']) / df['spot_price'] * 100
        ).fillna(0)

        # Distance to put wall (support)
        df['distance_to_put_wall_pct'] = (
            (df['spot_price'] - df['put_wall']) / df['spot_price'] * 100
        ).fillna(0)

        # === MAGNET THEORY Features (KEY for directional prediction) ===
        # GEX Ratio: |put_gex| / |call_gex| using ABSOLUTE VALUES
        # (put_gex is typically negative in the database)
        # Higher ratio = stronger put side = price pulled DOWN (BEARISH)
        # Lower ratio = stronger call side = price pulled UP (BULLISH)
        df['gex_ratio'] = df.apply(
            lambda row: abs(row['put_gex']) / abs(row['call_gex']) if row['call_gex'] != 0 else (10.0 if row['put_gex'] != 0 else 1.0),
            axis=1
        ).fillna(1.0)

        # Log of ratio for better ML scaling (centered around 0)
        df['gex_ratio_log'] = np.log(df['gex_ratio'].clip(0.1, 10.0))

        # Near wall indicators (within 3% of wall)
        WALL_PROXIMITY_PCT = 3.0
        df['near_put_wall'] = (df['distance_to_put_wall_pct'].abs() <= WALL_PROXIMITY_PCT).astype(int)
        df['near_call_wall'] = (df['distance_to_call_wall_pct'].abs() <= WALL_PROXIMITY_PCT).astype(int)

        # Strong asymmetry indicator (ratio > 1.5 or < 0.67)
        df['gex_asymmetry_strong'] = ((df['gex_ratio'] >= 1.5) | (df['gex_ratio'] <= 0.67)).astype(int)

        # === VIX Features ===
        df['vix_level'] = df['vix_close'].fillna(20)

        # VIX regime indicators (15-25 has best risk-adjusted returns)
        df['vix_regime_low'] = (df['vix_level'] < 15).astype(int)
        df['vix_regime_mid'] = ((df['vix_level'] >= 15) & (df['vix_level'] <= 25)).astype(int)
        df['vix_regime_high'] = (df['vix_level'] > 25).astype(int)

        # === V2: Volatility Risk Premium (VRP) ===
        # VRP = expected_move (IV proxy) - realized_vol
        # Strongest edge signal for options strategies
        daily_expected_move_pct = df['vix_level'] / (252 ** 0.5)  # VIX annualized -> daily %
        price_changes_pct = df['close'].pct_change().abs() * 100
        realized_vol_5d = price_changes_pct.rolling(5, min_periods=2).std().fillna(
            daily_expected_move_pct * 0.8  # Conservative fallback
        )
        df['volatility_risk_premium'] = daily_expected_move_pct - realized_vol_5d

        # === Momentum Features ===
        # V2: Removed gex_change_1d and gex_regime_changed (always 0 at inference)

        # Opening gap (spot vs previous close)
        df['prev_close'] = df['close'].shift(1)
        df['spot_vs_prev_close_pct'] = (
            (df['open'] - df['prev_close']) / df['prev_close'] * 100
        ).fillna(0)

        # === Calendar Features (V2: cyclical encoding) ===
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['day_of_week'] = df['trade_date'].dt.dayofweek
        # V2: Cyclical encoding (matches WISDOM/Prophet/ORION pattern)
        df['day_of_week_sin'] = df['day_of_week'].apply(lambda d: math.sin(2 * math.pi * d / 5))
        df['day_of_week_cos'] = df['day_of_week'].apply(lambda d: math.cos(2 * math.pi * d / 5))
        df['is_monday'] = (df['day_of_week'] == 0).astype(int)
        df['is_friday'] = (df['day_of_week'] == 4).astype(int)

        # OPEX week (3rd Friday of month)
        df['day_of_month'] = df['trade_date'].dt.day
        df['is_opex_week'] = (
            (df['day_of_month'] >= 15) &
            (df['day_of_month'] <= 21)
        ).astype(int)

        # === Boolean to Int ===
        for col in ['between_walls', 'above_call_wall', 'below_put_wall']:
            if col in df.columns:
                df[col] = df[col].astype(int)

        # Drop rows with missing essential data
        df = df.dropna(subset=['direction', 'gex_normalized'])

        logger.info(f"Engineered features for {len(df)} samples")
        logger.info(f"Direction distribution:\n{df['direction'].value_counts()}")

        return df

    def _classify_direction(self, price_change_pct: float) -> str:
        """Classify price change into direction label"""
        if price_change_pct >= self.BULLISH_THRESHOLD:
            return Direction.BULLISH.value
        elif price_change_pct <= self.BEARISH_THRESHOLD:
            return Direction.BEARISH.value
        else:
            return Direction.FLAT.value

    def prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare feature matrix X and target vector y.

        Returns:
            X: Feature matrix (n_samples, n_features)
            y: Target vector (n_samples,)
        """
        # Select feature columns that exist
        available_features = [col for col in self.FEATURE_COLUMNS if col in df.columns]

        if len(available_features) < 5:
            raise ValueError(f"Not enough features available. Found: {available_features}")

        logger.info(f"Using {len(available_features)} features: {available_features}")

        X = df[available_features].values
        y = df['direction'].values

        # Handle any remaining NaN
        X = np.nan_to_num(X, nan=0.0)

        return X, y, available_features

    def train(
        self,
        start_date: str = '2022-01-01',
        end_date: str = None,
        n_splits: int = 5
    ) -> TrainingResult:
        """
        Train the directional prediction model.

        Uses walk-forward validation to prevent look-ahead bias.

        Args:
            start_date: Training data start date
            end_date: Training data end date
            n_splits: Number of time series splits for validation

        Returns:
            TrainingResult with metrics and feature importance
        """
        logger.info(f"Training GEX Directional Model for {self.ticker}")
        logger.info(f"Date range: {start_date} to {end_date or 'present'}")

        # Load and prepare data
        df = self.load_training_data(start_date, end_date)
        df = self.engineer_features(df)

        X, y, feature_names = self.prepare_features(df)

        # Encode labels
        y_encoded = self.label_encoder.fit_transform(y)

        # Time series split for validation
        tscv = TimeSeriesSplit(n_splits=n_splits)

        # V2: Compute sample weights for 3-class imbalance
        # (scale_pos_weight is binary-only; sample_weight works for multiclass)
        class_counts = Counter(y_encoded)
        n_samples = len(y_encoded)
        n_classes = len(class_counts)
        class_weights = {
            cls: n_samples / (n_classes * count)
            for cls, count in class_counts.items()
        }
        sample_weights_all = np.array([class_weights[y] for y in y_encoded])

        logger.info(f"V2 class balance: {dict(class_counts)}")
        logger.info(f"V2 class weights: { {self.label_encoder.inverse_transform([k])[0]: f'{v:.2f}' for k, v in class_weights.items()} }")

        # Track metrics across folds
        fold_accuracies = []
        fold_briers = []  # V2: Brier score per fold
        all_y_true = []
        all_y_pred = []
        all_y_proba = []  # V2: for multiclass Brier

        print("\n" + "=" * 60)
        print("WALK-FORWARD VALIDATION (V2)")
        print("=" * 60)

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y_encoded[train_idx], y_encoded[test_idx]
            sw_train = sample_weights_all[train_idx]  # V2: per-fold sample weights

            # Scale features (fit on train fold only — no leakage)
            scaler_fold = StandardScaler()
            X_train_scaled = scaler_fold.fit_transform(X_train)
            X_test_scaled = scaler_fold.transform(X_test)

            # Train model (XGBoost if available, else sklearn GradientBoosting)
            if HAS_XGBOOST:
                model = xgb.XGBClassifier(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    min_child_weight=10,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.1,
                    reg_lambda=1.0,
                    random_state=42,
                    verbosity=0
                )
            else:
                model = GradientBoostingClassifier(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    min_samples_leaf=10,
                    subsample=0.8,
                    random_state=42
                )
            model.fit(X_train_scaled, y_train, sample_weight=sw_train)  # V2: weighted

            # Predict
            y_pred = model.predict(X_test_scaled)
            y_proba = model.predict_proba(X_test_scaled)

            # V2: Multiclass Brier score = mean of one-vs-rest Brier scores
            fold_brier = 0.0
            for cls_idx in range(n_classes):
                y_binary = (y_test == cls_idx).astype(int)
                fold_brier += brier_score_loss(y_binary, y_proba[:, cls_idx])
            fold_brier /= n_classes
            fold_briers.append(fold_brier)

            # Track
            fold_acc = accuracy_score(y_test, y_pred)
            fold_accuracies.append(fold_acc)
            all_y_true.extend(y_test)
            all_y_pred.extend(y_pred)
            all_y_proba.extend(y_proba.tolist())

            print(f"Fold {fold + 1}: Accuracy = {fold_acc:.1%}, Brier = {fold_brier:.4f} (train={len(train_idx)}, test={len(test_idx)})")

        # Final training on all data
        print("\n" + "-" * 60)
        model_type = "XGBoost" if HAS_XGBOOST else "sklearn GradientBoosting"
        print(f"Final training on all data with {model_type}...")

        X_scaled = self.scaler.fit_transform(X)

        # Final model with optimized hyperparameters
        if HAS_XGBOOST:
            self.model = xgb.XGBClassifier(
                n_estimators=150,
                max_depth=4,
                learning_rate=0.1,
                min_child_weight=10,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                verbosity=0
            )
        else:
            self.model = GradientBoostingClassifier(
                n_estimators=150,
                max_depth=4,
                learning_rate=0.1,
                min_samples_leaf=10,
                subsample=0.8,
                random_state=42
            )
        self.model.fit(X_scaled, y_encoded, sample_weight=sample_weights_all)  # V2: weighted

        # V2: Isotonic calibration for reliable confidence values
        try:
            self.calibrated_model = CalibratedClassifierCV(
                self.model, method='isotonic', cv=3
            )
            self.calibrated_model.fit(X_scaled, y_encoded, sample_weight=sample_weights_all)
            print("V2: Isotonic calibration applied successfully")
        except Exception as e:
            logger.warning(f"V2: Calibration failed, using raw model: {e}")
            self.calibrated_model = None

        # Store feature names for later use
        self.feature_names = feature_names

        # Get feature importance from XGBoost model
        self.feature_importance = dict(zip(
            feature_names,
            self.model.feature_importances_
        ))

        self.is_trained = True

        # Calculate final metrics
        overall_accuracy = accuracy_score(all_y_true, all_y_pred)
        cm = confusion_matrix(all_y_true, all_y_pred)

        # Per-class metrics
        class_names = self.label_encoder.classes_
        report = classification_report(all_y_true, all_y_pred, target_names=class_names, output_dict=True)

        precision_by_class = {cls: report[cls]['precision'] for cls in class_names}
        recall_by_class = {cls: report[cls]['recall'] for cls in class_names}

        # V2: Compute mean Brier score across CV folds
        mean_brier = np.mean(fold_briers) if fold_briers else 0.0

        # Print results
        print("\n" + "=" * 60)
        print("TRAINING RESULTS (V2)")
        print("=" * 60)
        print(f"\nOverall Accuracy: {overall_accuracy:.1%}")
        print(f"Mean CV Accuracy: {np.mean(fold_accuracies):.1%} (+/- {np.std(fold_accuracies):.1%})")
        print(f"Mean CV Brier Score: {mean_brier:.4f} (lower is better, 0=perfect)")
        print(f"Calibrated Model: {'YES' if self.calibrated_model else 'NO'}")
        print(f"Feature Version: {self.FEATURE_VERSION}")
        print(f"Features: {len(feature_names)} (was 26 in V1)")

        print("\nV2 Class Weights Applied:")
        for cls_idx, cls_name in enumerate(class_names):
            weight = class_weights.get(cls_idx, 1.0)
            count = class_counts.get(cls_idx, 0)
            print(f"  {cls_name}: count={count}, weight={weight:.2f}")

        print("\nPer-Class Performance:")
        print("-" * 40)
        for cls in class_names:
            print(f"  {cls}: Precision={precision_by_class[cls]:.1%}, Recall={recall_by_class[cls]:.1%}")

        print("\nConfusion Matrix:")
        print(f"  Columns: {list(class_names)}")
        print(cm)

        print("\nFeature Importance (Top 10):")
        print("-" * 40)
        sorted_importance = sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)
        for feat, imp in sorted_importance[:10]:
            print(f"  {feat}: {imp:.3f}")

        return TrainingResult(
            accuracy=overall_accuracy,
            precision_by_class=precision_by_class,
            recall_by_class=recall_by_class,
            feature_importance=self.feature_importance,
            confusion_matrix=cm,
            training_samples=len(X),
            test_samples=len(all_y_true),
            brier_score=mean_brier,
            feature_version=self.FEATURE_VERSION,
        )

    def predict(
        self,
        gex_data: Dict[str, Any],
        vix: float = 20.0,
        prev_close: float = None
    ) -> DirectionalPrediction:
        """
        Predict market direction from current GEX structure.

        Args:
            gex_data: Dict with GEX features (from ChroniclesGEXCalculator)
                - spot_price, net_gex, gex_normalized, gex_regime
                - call_wall, put_wall, flip_point
                - distance_to_flip_pct, between_walls, etc.
            vix: Current VIX level
            prev_close: Previous day's close (for gap analysis)

        Returns:
            DirectionalPrediction with direction, confidence, and probabilities
        """
        if not self.is_trained:
            raise ValueError("Model not trained. Call train() first.")

        # Build feature vector
        features = self._build_feature_vector(gex_data, vix, prev_close)

        # Scale
        X = np.array([list(features.values())])
        X_scaled = self.scaler.transform(X)

        # Predict (V2: prefer calibrated model for reliable confidence)
        predict_model = self.calibrated_model if self.calibrated_model else self.model
        proba = predict_model.predict_proba(X_scaled)[0]
        pred_idx = np.argmax(proba)
        pred_label = self.label_encoder.inverse_transform([pred_idx])[0]

        # Build probability dict
        probabilities = {
            cls: proba[i] for i, cls in enumerate(self.label_encoder.classes_)
        }

        return DirectionalPrediction(
            direction=Direction(pred_label),
            confidence=proba[pred_idx],
            probabilities=probabilities,
            features_used=features
        )

    def _build_feature_vector(
        self,
        gex_data: Dict[str, Any],
        vix: float,
        prev_close: float = None
    ) -> Dict[str, float]:
        """Build feature vector from GEX data"""
        spot = gex_data.get('spot_price', 0)

        features = {}

        # Core GEX features
        features['gex_normalized'] = gex_data.get('gex_normalized', 0)
        features['gex_regime_positive'] = 1 if gex_data.get('gex_regime') == 'POSITIVE' else 0
        features['gex_regime_negative'] = 1 if gex_data.get('gex_regime') == 'NEGATIVE' else 0
        features['distance_to_flip_pct'] = gex_data.get('distance_to_flip_pct', 0)

        # Distance to walls
        call_wall = gex_data.get('call_wall', spot)
        put_wall = gex_data.get('put_wall', spot)
        distance_to_call_wall_pct = (call_wall - spot) / spot * 100 if spot > 0 else 0
        distance_to_put_wall_pct = (spot - put_wall) / spot * 100 if spot > 0 else 0
        features['distance_to_call_wall_pct'] = distance_to_call_wall_pct
        features['distance_to_put_wall_pct'] = distance_to_put_wall_pct

        # Position features
        features['between_walls'] = int(gex_data.get('between_walls', True))
        features['above_call_wall'] = int(gex_data.get('above_call_wall', False))
        features['below_put_wall'] = int(gex_data.get('below_put_wall', False))

        # === MAGNET THEORY Features (KEY for directional prediction) ===
        # Get put/call GEX values
        put_gex = gex_data.get('put_gex', gex_data.get('total_put_gex', 0))
        call_gex = gex_data.get('call_gex', gex_data.get('total_call_gex', 0))

        # GEX Ratio: |put_gex| / |call_gex| using ABSOLUTE VALUES
        # (put_gex is typically negative in the database)
        abs_put_gex = abs(put_gex)
        abs_call_gex = abs(call_gex)

        if abs_call_gex > 0:
            gex_ratio = abs_put_gex / abs_call_gex
        else:
            gex_ratio = 10.0 if abs_put_gex > 0 else 1.0
        features['gex_ratio'] = gex_ratio

        # Log ratio for better scaling
        features['gex_ratio_log'] = np.log(max(0.1, min(10.0, gex_ratio)))

        # Near wall indicators (within 3% proximity)
        WALL_PROXIMITY_PCT = 3.0
        features['near_put_wall'] = 1 if abs(distance_to_put_wall_pct) <= WALL_PROXIMITY_PCT else 0
        features['near_call_wall'] = 1 if abs(distance_to_call_wall_pct) <= WALL_PROXIMITY_PCT else 0

        # Strong GEX asymmetry (ratio > 1.5 or < 0.67)
        features['gex_asymmetry_strong'] = 1 if (gex_ratio >= 1.5 or gex_ratio <= 0.67) else 0

        # === VIX Features ===
        features['vix_level'] = vix

        # V2: VRP inference proxy (matches Prophet V3 approach)
        # Expected daily move from VIX, realized from opening gap
        daily_expected_move = vix / (252 ** 0.5)
        # Use opening gap as realized vol proxy when available
        spot_gap_pct = abs((spot - prev_close) / prev_close * 100) if prev_close and prev_close > 0 else daily_expected_move * 0.8
        features['volatility_risk_premium'] = daily_expected_move - spot_gap_pct

        # VIX regime indicators
        features['vix_regime_low'] = 1 if vix < 15 else 0
        features['vix_regime_mid'] = 1 if 15 <= vix <= 25 else 0
        features['vix_regime_high'] = 1 if vix > 25 else 0

        # Momentum (V2: removed gex_change_1d, gex_regime_changed — were always 0)
        features['spot_vs_prev_close_pct'] = (
            (spot - prev_close) / prev_close * 100 if prev_close and prev_close > 0 else 0
        )

        # Calendar (V2: cyclical encoding)
        today = datetime.now()
        dow = today.weekday()
        features['day_of_week_sin'] = math.sin(2 * math.pi * dow / 5)
        features['day_of_week_cos'] = math.cos(2 * math.pi * dow / 5)
        features['is_monday'] = 1 if dow == 0 else 0
        features['is_friday'] = 1 if dow == 4 else 0
        features['is_opex_week'] = 1 if 15 <= today.day <= 21 else 0

        # Only return features the model was trained on
        return {k: features.get(k, 0) for k in self.feature_names}

    def save_model(self, filepath: str = 'models/gex_directional_model.joblib'):
        """Save trained model to disk"""
        if not self.is_trained:
            raise ValueError("Model not trained")

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        model_data = {
            'model': self.model,
            'calibrated_model': self.calibrated_model,  # V2
            'scaler': self.scaler,
            'label_encoder': self.label_encoder,
            'feature_names': self.feature_names,
            'feature_importance': self.feature_importance,
            'ticker': self.ticker,
            'feature_version': self.FEATURE_VERSION,  # V2
            'thresholds': {
                'bullish': self.BULLISH_THRESHOLD,
                'bearish': self.BEARISH_THRESHOLD
            }
        }

        joblib.dump(model_data, filepath)
        logger.info(f"Model saved to {filepath}")

    def save_to_db(self, metrics: dict = None, training_records: int = None) -> bool:
        """Save model to database for Render persistence"""
        if not self.is_trained:
            raise ValueError("Model not trained")

        try:
            from quant.model_persistence import save_model_to_db, MODEL_GEX_DIRECTIONAL

            model_data = {
                'model': self.model,
                'calibrated_model': self.calibrated_model,  # V2
                'scaler': self.scaler,
                'label_encoder': self.label_encoder,
                'feature_names': self.feature_names,
                'feature_importance': self.feature_importance,
                'ticker': self.ticker,
                'feature_version': self.FEATURE_VERSION,  # V2
                'thresholds': {
                    'bullish': self.BULLISH_THRESHOLD,
                    'bearish': self.BEARISH_THRESHOLD
                }
            }

            return save_model_to_db(
                MODEL_GEX_DIRECTIONAL,
                model_data,
                metrics=metrics,
                training_records=training_records
            )
        except Exception as e:
            logger.error(f"Error saving to database: {e}")
            return False

    def load_from_db(self) -> bool:
        """Load model from database"""
        try:
            from quant.model_persistence import load_model_from_db, MODEL_GEX_DIRECTIONAL

            model_data = load_model_from_db(MODEL_GEX_DIRECTIONAL)
            if model_data is None:
                return False

            self.model = model_data['model']
            self.calibrated_model = model_data.get('calibrated_model')  # V2 (None for V1 models)
            self.scaler = model_data['scaler']
            self.label_encoder = model_data['label_encoder']
            self.feature_names = model_data['feature_names']
            self.feature_importance = model_data['feature_importance']
            self.ticker = model_data['ticker']
            self.is_trained = True

            loaded_version = model_data.get('feature_version', 'V1')
            logger.info(f"Model loaded from database (feature_version={loaded_version})")
            return True

        except Exception as e:
            logger.error(f"Error loading from database: {e}")
            return False

    def load_model(self, filepath: str = 'models/gex_directional_model.joblib'):
        """Load trained model from disk"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Model file not found: {filepath}")

        model_data = joblib.load(filepath)

        self.model = model_data['model']
        self.calibrated_model = model_data.get('calibrated_model')  # V2 (None for V1 models)
        self.scaler = model_data['scaler']
        self.label_encoder = model_data['label_encoder']
        self.feature_names = model_data['feature_names']
        self.feature_importance = model_data['feature_importance']
        self.ticker = model_data['ticker']
        self.is_trained = True

        loaded_version = model_data.get('feature_version', 'V1')
        logger.info(f"Model loaded from {filepath} (feature_version={loaded_version})")


def main():
    """Train and evaluate the GEX directional model"""
    import argparse

    parser = argparse.ArgumentParser(description='Train GEX Directional ML Model')
    parser.add_argument('--ticker', type=str, default='SPY', help='Ticker to train on')
    parser.add_argument('--start', type=str, default='2022-01-01', help='Start date')
    parser.add_argument('--end', type=str, default=None, help='End date')
    parser.add_argument('--save', type=str, default='models/gex_directional_model.joblib',
                        help='Path to save model')
    args = parser.parse_args()

    print("=" * 70)
    print("GEX DIRECTIONAL ML MODEL TRAINER")
    print("=" * 70)
    print(f"\nTicker: {args.ticker}")
    print(f"Date range: {args.start} to {args.end or 'present'}")

    # Initialize predictor
    predictor = GEXDirectionalPredictor(ticker=args.ticker)

    # Train model
    try:
        result = predictor.train(
            start_date=args.start,
            end_date=args.end,
            n_splits=5
        )

        # Save model
        predictor.save_model(args.save)
        print(f"\nModel saved to: {args.save}")

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Training samples: {result.training_samples}")
        print(f"Overall accuracy: {result.accuracy:.1%}")
        print(f"\nModel ready for directional predictions!")
        print("\nUsage:")
        print("  from quant.gex_directional_ml import GEXDirectionalPredictor")
        print("  predictor = GEXDirectionalPredictor()")
        print("  predictor.load_model()")
        print("  prediction = predictor.predict(gex_data, vix=20)")
        print(f"  print(prediction.direction, prediction.confidence)")

    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise


if __name__ == '__main__':
    main()
