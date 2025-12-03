"""
REAL SPX Wheel ML System

This ML system is designed SPECIFICALLY for SPX cash-secured put selling.
NOT copied from SPY pattern detection - built from scratch for premium selling.

WHAT MAKES PREMIUM SELLING PROFITABLE:
1. Selling high IV (overpriced options) - IV Rank matters
2. Avoiding catastrophic losses - VIX spikes, market crashes
3. Selling into support (put walls) - GEX positioning matters
4. Time decay works in your favor - Theta is your friend

FEATURES THAT ACTUALLY MATTER:
- IV Rank: Is implied volatility high relative to history? (sell high IV)
- VIX Level: Market fear gauge (high VIX = high premium but more risk)
- VIX Term Structure: Contango (normal) vs Backwardation (fear)
- Put Wall Distance: How far is the nearest put wall support?
- Recent Drawdown: Has SPX dropped recently? (mean reversion opportunity)
- Days to Expiration: Theta decay accelerates near expiration

WHAT THIS ML LEARNS:
- Which market conditions lead to profitable put sales
- When to avoid selling (crash conditions)
- Optimal strike selection based on conditions

TRANSPARENCY:
- Every prediction is logged with reasoning
- Outcome tracking updates after each trade closes
- Accuracy metrics show if ML actually helps
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Try to import ML libraries
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report
    import pickle
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logger.warning("scikit-learn not available. Install with: pip install scikit-learn")


@dataclass
class SPXWheelFeatures:
    """
    Features that ACTUALLY matter for SPX put selling.

    Each feature has a clear reason for inclusion.
    """
    # Trade parameters
    trade_date: str
    strike: float
    underlying_price: float
    dte: int  # Days to expiration
    delta: float  # Option delta (probability of ITM)
    premium: float  # Premium received per contract

    # Volatility features - CRITICAL for premium selling
    iv: float  # Implied volatility of the option
    iv_rank: float  # IV percentile over last year (0-100)
    vix: float  # VIX level
    vix_percentile: float  # VIX percentile over last year
    vix_term_structure: float  # VIX - VIX3M (positive = backwardation = fear)

    # GEX/Positioning features - Support levels
    put_wall_distance_pct: float  # Distance to nearest put wall (support)
    call_wall_distance_pct: float  # Distance to nearest call wall (resistance)
    net_gex: float  # Net gamma exposure (positive = dealers buy dips)

    # Market regime features
    spx_20d_return: float  # 20-day SPX return (momentum)
    spx_5d_return: float  # 5-day SPX return (recent move)
    spx_distance_from_high: float  # % below 52-week high

    # Premium quality
    premium_to_strike_pct: float  # Premium as % of strike (yield)
    annualized_return: float  # Annualized return if trade wins

    def to_array(self) -> np.ndarray:
        """Convert to numpy array for ML model"""
        return np.array([
            self.dte,
            self.delta,
            self.iv,
            self.iv_rank,
            self.vix,
            self.vix_percentile,
            self.vix_term_structure,
            self.put_wall_distance_pct,
            self.call_wall_distance_pct,
            self.net_gex / 1e9,  # Scale to billions
            self.spx_20d_return,
            self.spx_5d_return,
            self.spx_distance_from_high,
            self.premium_to_strike_pct,
            self.annualized_return
        ])

    @staticmethod
    def feature_names() -> List[str]:
        return [
            'dte',
            'delta',
            'iv',
            'iv_rank',
            'vix',
            'vix_percentile',
            'vix_term_structure',
            'put_wall_distance_pct',
            'call_wall_distance_pct',
            'net_gex_billions',
            'spx_20d_return',
            'spx_5d_return',
            'spx_distance_from_high',
            'premium_to_strike_pct',
            'annualized_return'
        ]


@dataclass
class SPXWheelOutcome:
    """
    Actual outcome of a trade - used for training.
    """
    trade_id: str
    features: SPXWheelFeatures

    # Outcome (filled after trade closes)
    outcome: str  # 'WIN' (expired OTM) or 'LOSS' (ITM/assigned)
    pnl: float  # Actual P&L
    max_drawdown: float  # Worst unrealized P&L during trade
    settlement_price: float  # SPX price at expiration

    def is_win(self) -> bool:
        return self.outcome == 'WIN'


class SPXWheelMLTrainer:
    """
    REAL ML trainer for SPX wheel strategy.

    Trains on actual trade outcomes, not theoretical patterns.
    """

    def __init__(self, model_path: str = None):
        self.model = None
        self.scaler = None
        self.feature_importance = {}
        self.training_metrics = {}
        self.model_path = model_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'models',
            'spx_wheel_ml.pkl'
        )

        # Try to load existing model
        if os.path.exists(self.model_path):
            self.load_model()

    def train(self, outcomes: List[SPXWheelOutcome], min_samples: int = 30) -> Dict:
        """
        Train ML model on actual trade outcomes.

        Returns training metrics and feature importance.
        """
        if not ML_AVAILABLE:
            return {'error': 'scikit-learn not installed'}

        if len(outcomes) < min_samples:
            return {
                'error': f'Need at least {min_samples} trades to train. Have {len(outcomes)}.',
                'trades_available': len(outcomes),
                'trades_needed': min_samples
            }

        # Extract features and labels
        X = np.array([o.features.to_array() for o in outcomes])
        y = np.array([1 if o.is_win() else 0 for o in outcomes])

        # Check class balance
        win_rate = y.mean()
        if win_rate < 0.1 or win_rate > 0.9:
            logger.warning(f"Imbalanced classes: {win_rate:.1%} win rate")

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Train Random Forest (good for this problem)
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=6,  # Prevent overfitting
            min_samples_leaf=5,
            class_weight='balanced',  # Handle imbalanced classes
            random_state=42,
            n_jobs=-1
        )

        self.model.fit(X_train_scaled, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        y_prob = self.model.predict_proba(X_test_scaled)[:, 1]

        # Cross-validation for more robust estimate
        cv_scores = cross_val_score(self.model, X_train_scaled, y_train, cv=5)

        # Feature importance
        importance = self.model.feature_importances_
        feature_names = SPXWheelFeatures.feature_names()
        self.feature_importance = dict(zip(feature_names, importance))
        sorted_features = sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)

        # Store metrics
        self.training_metrics = {
            'trained_at': datetime.now().isoformat(),
            'total_samples': len(outcomes),
            'training_samples': len(X_train),
            'test_samples': len(X_test),
            'baseline_win_rate': float(win_rate),
            'test_accuracy': float(accuracy_score(y_test, y_pred)),
            'test_precision': float(precision_score(y_test, y_pred, zero_division=0)),
            'test_recall': float(recall_score(y_test, y_pred, zero_division=0)),
            'cv_accuracy_mean': float(cv_scores.mean()),
            'cv_accuracy_std': float(cv_scores.std()),
            'feature_importance': sorted_features
        }

        # Save model
        self.save_model()

        return {
            'success': True,
            'metrics': self.training_metrics,
            'interpretation': self._interpret_results()
        }

    def _interpret_results(self) -> Dict:
        """
        Provide human-readable interpretation of training results.

        THIS IS THE TRANSPARENCY - explaining what the model learned.
        """
        if not self.training_metrics:
            return {'message': 'No training metrics available'}

        baseline = self.training_metrics['baseline_win_rate']
        accuracy = self.training_metrics['test_accuracy']
        top_features = self.training_metrics['feature_importance'][:5]

        # Is ML actually helping?
        improvement = accuracy - baseline

        interpretation = {
            'baseline_explanation': f"Without ML, just selling puts randomly has {baseline:.1%} win rate",
            'ml_accuracy': f"ML correctly predicts {accuracy:.1%} of trades",
            'ml_value_add': f"ML {'improves' if improvement > 0.02 else 'does not significantly improve'} on baseline by {improvement:.1%}",
            'top_factors': [
                f"{f[0]}: {f[1]:.1%} importance" for f in top_features
            ],
            'recommendation': self._get_recommendation(improvement, accuracy)
        }

        return interpretation

    def _get_recommendation(self, improvement: float, accuracy: float) -> str:
        """Honest recommendation about whether to use ML"""
        if improvement > 0.05 and accuracy > 0.6:
            return "ML is adding significant value. Use ML scoring for trade selection."
        elif improvement > 0.02:
            return "ML shows modest improvement. Consider using as secondary filter."
        elif accuracy > 0.55:
            return "ML is marginally better than random. May help avoid worst trades."
        else:
            return "ML is NOT adding value. Stick to mechanical strategy rules."

    def predict(self, features: SPXWheelFeatures) -> Dict:
        """
        Predict trade outcome.

        Returns probability and clear reasoning.
        """
        if not ML_AVAILABLE or self.model is None:
            return {
                'ml_available': False,
                'win_probability': None,
                'recommendation': 'USE_MECHANICAL_RULES',
                'reasoning': 'ML model not trained. Use mechanical strategy rules.'
            }

        # Scale features
        X = features.to_array().reshape(1, -1)
        X_scaled = self.scaler.transform(X)

        # Predict
        prob = self.model.predict_proba(X_scaled)[0][1]

        # Get feature contributions (which features drove this prediction)
        feature_values = dict(zip(SPXWheelFeatures.feature_names(), features.to_array()))

        # Identify key factors
        key_factors = self._identify_key_factors(features)

        # Recommendation
        if prob >= 0.70:
            recommendation = 'STRONG_TRADE'
            reasoning = f"High win probability ({prob:.1%}). {key_factors['positive']}"
        elif prob >= 0.55:
            recommendation = 'TRADE'
            reasoning = f"Favorable conditions ({prob:.1%}). {key_factors['positive']}"
        elif prob >= 0.45:
            recommendation = 'NEUTRAL'
            reasoning = f"Mixed signals ({prob:.1%}). {key_factors['mixed']}"
        elif prob >= 0.30:
            recommendation = 'CAUTION'
            reasoning = f"Elevated risk ({prob:.1%}). {key_factors['negative']}"
        else:
            recommendation = 'SKIP'
            reasoning = f"High loss probability ({1-prob:.1%}). {key_factors['negative']}"

        return {
            'ml_available': True,
            'win_probability': float(prob),
            'recommendation': recommendation,
            'reasoning': reasoning,
            'key_factors': key_factors,
            'feature_values': feature_values
        }

    def _identify_key_factors(self, features: SPXWheelFeatures) -> Dict:
        """Identify which factors are driving the prediction"""
        positive = []
        negative = []

        # IV Rank analysis
        if features.iv_rank > 50:
            positive.append(f"IV Rank {features.iv_rank:.0f}% (selling expensive options)")
        elif features.iv_rank < 20:
            negative.append(f"IV Rank {features.iv_rank:.0f}% (cheap options, low premium)")

        # VIX analysis
        if features.vix > 25:
            positive.append(f"VIX {features.vix:.1f} (high premium environment)")
            if features.vix > 35:
                negative.append("Extreme VIX (crash risk)")
        elif features.vix < 15:
            negative.append(f"VIX {features.vix:.1f} (low premium, complacency)")

        # VIX term structure
        if features.vix_term_structure > 2:
            negative.append("VIX backwardation (market stress)")
        elif features.vix_term_structure < -2:
            positive.append("VIX contango (normal conditions)")

        # Put wall support
        if features.put_wall_distance_pct < 3:
            positive.append(f"Strong put wall support {features.put_wall_distance_pct:.1f}% below")
        elif features.put_wall_distance_pct > 8:
            negative.append("No nearby put wall support")

        # Recent performance
        if features.spx_5d_return < -3:
            positive.append(f"SPX down {abs(features.spx_5d_return):.1f}% (mean reversion)")
        elif features.spx_5d_return > 3:
            negative.append(f"SPX up {features.spx_5d_return:.1f}% (extended)")

        # Premium quality
        if features.annualized_return > 20:
            positive.append(f"Strong premium ({features.annualized_return:.0f}% annualized)")
        elif features.annualized_return < 8:
            negative.append(f"Weak premium ({features.annualized_return:.0f}% annualized)")

        return {
            'positive': ' '.join(positive) if positive else 'No strong positive factors',
            'negative': ' '.join(negative) if negative else 'No significant risks identified',
            'mixed': f"{len(positive)} positive, {len(negative)} negative factors"
        }

    def save_model(self):
        """Save trained model"""
        if self.model is None:
            return False

        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

        with open(self.model_path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'scaler': self.scaler,
                'feature_importance': self.feature_importance,
                'training_metrics': self.training_metrics
            }, f)

        logger.info(f"Model saved to {self.model_path}")
        return True

    def load_model(self) -> bool:
        """Load trained model"""
        if not os.path.exists(self.model_path):
            return False

        try:
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)

            self.model = data['model']
            self.scaler = data['scaler']
            self.feature_importance = data['feature_importance']
            self.training_metrics = data.get('training_metrics', {})

            logger.info(f"Model loaded from {self.model_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False


class SPXWheelOutcomeTracker:
    """
    Tracks trade outcomes for ML training.

    THIS IS CRITICAL - without outcome tracking, ML can't learn.
    """

    def __init__(self):
        self.pending_trades: Dict[str, SPXWheelFeatures] = {}

    def record_trade_entry(self, trade_id: str, features: SPXWheelFeatures):
        """Record a new trade for outcome tracking"""
        self.pending_trades[trade_id] = features
        self._save_to_db(trade_id, features, outcome=None, pnl=None)
        logger.info(f"Recorded trade {trade_id} for outcome tracking")

    def record_trade_outcome(
        self,
        trade_id: str,
        outcome: str,
        pnl: float,
        settlement_price: float,
        max_drawdown: float = 0
    ) -> SPXWheelOutcome:
        """Record trade outcome - CRITICAL for ML learning"""

        if trade_id in self.pending_trades:
            features = self.pending_trades.pop(trade_id)
        else:
            features = self._load_from_db(trade_id)

        if features is None:
            logger.error(f"No features found for trade {trade_id}")
            return None

        outcome_obj = SPXWheelOutcome(
            trade_id=trade_id,
            features=features,
            outcome=outcome,
            pnl=pnl,
            max_drawdown=max_drawdown,
            settlement_price=settlement_price
        )

        self._update_outcome_in_db(trade_id, outcome, pnl, settlement_price, max_drawdown)
        logger.info(f"Recorded outcome for trade {trade_id}: {outcome}, P&L: ${pnl:,.2f}")

        return outcome_obj

    def get_all_outcomes(self) -> List[SPXWheelOutcome]:
        """Get all completed trade outcomes for training"""
        return self._load_all_outcomes_from_db()

    def _save_to_db(self, trade_id: str, features: SPXWheelFeatures, outcome: str, pnl: float):
        """Save to database"""
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # NOTE: Table 'spx_wheel_ml_outcomes' is defined in db/config_and_database.py (single source of truth)

            cursor.execute('''
                INSERT INTO spx_wheel_ml_outcomes (
                    trade_id, trade_date, strike, underlying_price, dte, delta, premium,
                    iv, iv_rank, vix, vix_percentile, vix_term_structure,
                    put_wall_distance_pct, call_wall_distance_pct, net_gex,
                    spx_20d_return, spx_5d_return, spx_distance_from_high,
                    premium_to_strike_pct, annualized_return, outcome, pnl
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_id) DO NOTHING
            ''', (
                trade_id, features.trade_date, features.strike, features.underlying_price,
                features.dte, features.delta, features.premium, features.iv, features.iv_rank,
                features.vix, features.vix_percentile, features.vix_term_structure,
                features.put_wall_distance_pct, features.call_wall_distance_pct, features.net_gex,
                features.spx_20d_return, features.spx_5d_return, features.spx_distance_from_high,
                features.premium_to_strike_pct, features.annualized_return, outcome, pnl
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save to DB: {e}")

    def _update_outcome_in_db(self, trade_id: str, outcome: str, pnl: float, settlement_price: float, max_drawdown: float):
        """Update outcome in database"""
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE spx_wheel_ml_outcomes
                SET outcome = %s, pnl = %s, settlement_price = %s, max_drawdown = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE trade_id = %s
            ''', (outcome, pnl, settlement_price, max_drawdown, trade_id))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to update outcome in DB: {e}")

    def _load_from_db(self, trade_id: str) -> Optional[SPXWheelFeatures]:
        """Load features from database"""
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT trade_date, strike, underlying_price, dte, delta, premium,
                       iv, iv_rank, vix, vix_percentile, vix_term_structure,
                       put_wall_distance_pct, call_wall_distance_pct, net_gex,
                       spx_20d_return, spx_5d_return, spx_distance_from_high,
                       premium_to_strike_pct, annualized_return
                FROM spx_wheel_ml_outcomes
                WHERE trade_id = %s
            ''', (trade_id,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return SPXWheelFeatures(
                    trade_date=row[0], strike=float(row[1]), underlying_price=float(row[2]),
                    dte=int(row[3]), delta=float(row[4]), premium=float(row[5]),
                    iv=float(row[6]), iv_rank=float(row[7]), vix=float(row[8]),
                    vix_percentile=float(row[9]), vix_term_structure=float(row[10]),
                    put_wall_distance_pct=float(row[11]), call_wall_distance_pct=float(row[12]),
                    net_gex=float(row[13]), spx_20d_return=float(row[14]),
                    spx_5d_return=float(row[15]), spx_distance_from_high=float(row[16]),
                    premium_to_strike_pct=float(row[17]), annualized_return=float(row[18])
                )
            return None
        except Exception as e:
            logger.error(f"Failed to load from DB: {e}")
            return None

    def _load_all_outcomes_from_db(self) -> List[SPXWheelOutcome]:
        """Load all completed outcomes from database"""
        outcomes = []
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT trade_id, trade_date, strike, underlying_price, dte, delta, premium,
                       iv, iv_rank, vix, vix_percentile, vix_term_structure,
                       put_wall_distance_pct, call_wall_distance_pct, net_gex,
                       spx_20d_return, spx_5d_return, spx_distance_from_high,
                       premium_to_strike_pct, annualized_return, outcome, pnl,
                       max_drawdown, settlement_price
                FROM spx_wheel_ml_outcomes
                WHERE outcome IS NOT NULL
            ''')

            for row in cursor.fetchall():
                features = SPXWheelFeatures(
                    trade_date=row[1], strike=float(row[2]), underlying_price=float(row[3]),
                    dte=int(row[4]), delta=float(row[5]), premium=float(row[6]),
                    iv=float(row[7]), iv_rank=float(row[8]), vix=float(row[9]),
                    vix_percentile=float(row[10]), vix_term_structure=float(row[11]),
                    put_wall_distance_pct=float(row[12]), call_wall_distance_pct=float(row[13]),
                    net_gex=float(row[14]), spx_20d_return=float(row[15]),
                    spx_5d_return=float(row[16]), spx_distance_from_high=float(row[17]),
                    premium_to_strike_pct=float(row[18]), annualized_return=float(row[19])
                )
                outcomes.append(SPXWheelOutcome(
                    trade_id=row[0],
                    features=features,
                    outcome=row[20],
                    pnl=float(row[21]) if row[21] else 0,
                    max_drawdown=float(row[22]) if row[22] else 0,
                    settlement_price=float(row[23]) if row[23] else 0
                ))

            conn.close()
        except Exception as e:
            logger.error(f"Failed to load outcomes from DB: {e}")

        return outcomes


# Singleton instances
_ml_trainer = None
_outcome_tracker = None

def get_spx_wheel_ml_trainer() -> SPXWheelMLTrainer:
    """Get singleton ML trainer"""
    global _ml_trainer
    if _ml_trainer is None:
        _ml_trainer = SPXWheelMLTrainer()
    return _ml_trainer

def get_outcome_tracker() -> SPXWheelOutcomeTracker:
    """Get singleton outcome tracker"""
    global _outcome_tracker
    if _outcome_tracker is None:
        _outcome_tracker = SPXWheelOutcomeTracker()
    return _outcome_tracker


# =============================================================================
# WHY THIS STRATEGY CAN MAKE MONEY - HONEST EXPLANATION
# =============================================================================
"""
THE HONEST TRUTH ABOUT SPX PUT SELLING:

WHY IT WORKS (historically):
1. VOLATILITY RISK PREMIUM: Implied volatility > realized volatility ~80% of the time
   - Options are systematically overpriced because people pay for insurance
   - Selling options captures this premium

2. THETA DECAY: Time works in your favor
   - Every day that passes, you keep more premium
   - This is a mathematical certainty, not a prediction

3. PROBABILITY: 20-delta puts have ~80% chance of expiring worthless
   - You win more often than you lose
   - BUT the losses can be large (asymmetric)

WHY IT CAN FAIL:
1. TAIL RISK: The 20% losses can wipe out many wins
   - March 2020: SPX dropped 34% - catastrophic for put sellers
   - 2008: Similar devastation

2. DRAWDOWNS: Even without tail events, you can have extended losing streaks

3. CAPITAL REQUIREMENTS: Need substantial capital for SPX

WHAT ML CAN ACTUALLY DO:
1. Identify HIGH IV environments (better premium)
2. Avoid EXTREME STRESS conditions (potential crashes)
3. Find SUPPORT levels (put walls) for safer strikes
4. Time entries after pullbacks (mean reversion)

WHAT ML CANNOT DO:
1. Predict black swan events
2. Guarantee profits
3. Eliminate drawdowns
4. Turn a losing strategy into a winning one

THE KEY INSIGHT:
ML can improve a strategy that already has an edge.
It cannot create an edge where none exists.
The SPX wheel has a statistical edge (volatility risk premium).
ML helps you capture that edge more efficiently.
"""
