"""
ML Pattern Recognition and Learning System
Learns from historical patterns to improve detection accuracy over time

Uses scikit-learn for:
- Pattern classification
- Feature importance analysis
- Confidence calibration
- Pattern similarity detection

Improves:
- Pattern detection accuracy
- Confidence score accuracy
- Trade timing
- Exit timing
"""

from database_adapter import get_connection
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

# Try to import scikit-learn
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    from sklearn.preprocessing import StandardScaler
    import pickle
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️ scikit-learn not available. Install with: pip install scikit-learn")


class PatternLearner:
    """ML-powered pattern recognition and learning"""

    def __init__(self):
        self.model = None
        self.scaler = None
        self.feature_importance = {}

        if ML_AVAILABLE:
            print("✅ ML Pattern Learner initialized")
        else:
            print("⚠️ ML Pattern Learner disabled (scikit-learn not installed)")

    def train_pattern_classifier(self, lookback_days: int = 180) -> Dict:
        """
        Train ML model to classify pattern success/failure

        Features used:
        - RSI values (5m, 15m, 1h, 4h, 1d)
        - Net GEX
        - Distance to gamma walls
        - VIX level
        - Liberation setup presence
        - False floor presence
        - Forward GEX magnets
        - Confidence score
        - Pattern type (one-hot encoded)

        Returns:
            Training metrics and feature importance
        """
        if not ML_AVAILABLE:
            return {'error': 'ML not available'}

        # Load training data
        X, y, feature_names = self._load_training_data(lookback_days)

        if len(X) < 50:
            return {'error': 'Insufficient training data (need at least 50 samples)'}

        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Train Random Forest
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            class_weight='balanced'  # Handle imbalanced classes
        )

        self.model.fit(X_train_scaled, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test_scaled)

        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)

        # Feature importance
        importance = self.model.feature_importances_
        self.feature_importance = dict(zip(feature_names, importance))

        # Sort by importance
        sorted_features = sorted(
            self.feature_importance.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return {
            'trained': True,
            'samples': len(X),
            'test_samples': len(X_test),
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'top_features': sorted_features[:10],
            'all_features': sorted_features
        }

    def predict_pattern_success(self, regime: Dict) -> Dict:
        """
        Use trained ML model to predict if pattern will succeed

        Returns:
            {
                'success_probability': float (0-1),
                'ml_confidence': str ('HIGH'/'MEDIUM'/'LOW'),
                'adjusted_confidence': float (original confidence * ml_probability),
                'recommendation': str ('TRADE'/'SKIP'/'CAUTION')
            }
        """
        if not ML_AVAILABLE or self.model is None:
            return {
                'success_probability': 0.5,
                'ml_confidence': 'UNKNOWN',
                'adjusted_confidence': regime.get('confidence_score', 50),
                'recommendation': 'TRADE',
                'note': 'ML model not trained'
            }

        # Extract features from regime
        features = self._extract_features_from_regime(regime)

        if features is None:
            return {
                'success_probability': 0.5,
                'ml_confidence': 'UNKNOWN',
                'adjusted_confidence': regime.get('confidence_score', 50),
                'recommendation': 'TRADE',
                'note': 'Could not extract features'
            }

        # Scale features
        features_scaled = self.scaler.transform([features])

        # Predict probability
        prob = self.model.predict_proba(features_scaled)[0][1]  # Probability of success

        # Determine ML confidence
        if prob >= 0.7:
            ml_confidence = 'HIGH'
            recommendation = 'TRADE'
        elif prob >= 0.5:
            ml_confidence = 'MEDIUM'
            recommendation = 'TRADE'
        elif prob >= 0.3:
            ml_confidence = 'LOW'
            recommendation = 'CAUTION'
        else:
            ml_confidence = 'VERY_LOW'
            recommendation = 'SKIP'

        # Adjust original confidence score
        original_confidence = regime.get('confidence_score', 50)
        adjusted_confidence = original_confidence * prob

        return {
            'success_probability': prob,
            'ml_confidence': ml_confidence,
            'adjusted_confidence': adjusted_confidence,
            'recommendation': recommendation,
            'original_confidence': original_confidence,
            'ml_boost': prob - 0.5  # How much ML adjusts from baseline
        }

    def analyze_pattern_similarity(self, current_regime: Dict, top_n: int = 5) -> List[Dict]:
        """
        Find similar historical patterns and their outcomes

        Uses cosine similarity on feature vectors

        Returns:
            List of similar patterns with their outcomes
        """
        # Load historical patterns
        historical = self._load_historical_patterns(lookback_days=90)

        if not historical:
            return []

        # Extract features from current regime
        current_features = self._extract_features_from_regime(current_regime)

        if current_features is None:
            return []

        # Calculate similarity scores
        similarities = []
        for hist in historical:
            hist_features = hist['features']

            # Cosine similarity
            similarity = self._cosine_similarity(current_features, hist_features)

            similarities.append({
                'similarity_score': similarity,
                'pattern': hist['pattern'],
                'confidence': hist['confidence'],
                'outcome': hist['outcome'],
                'price_change': hist['price_change'],
                'timestamp': hist['timestamp']
            })

        # Sort by similarity
        similarities.sort(key=lambda x: x['similarity_score'], reverse=True)

        return similarities[:top_n]

    def save_model(self, filepath: str = 'autonomous_ml_model.pkl'):
        """Save trained model to file"""
        if not ML_AVAILABLE or self.model is None:
            return False

        try:
            with open(filepath, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'scaler': self.scaler,
                    'feature_importance': self.feature_importance
                }, f)

            print(f"✅ ML model saved to {filepath}")
            return True

        except Exception as e:
            print(f"❌ Error saving model: {e}")
            return False

    def load_model(self, filepath: str = 'autonomous_ml_model.pkl'):
        """Load trained model from file"""
        if not ML_AVAILABLE:
            return False

        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)

            self.model = data['model']
            self.scaler = data['scaler']
            self.feature_importance = data['feature_importance']

            print(f"✅ ML model loaded from {filepath}")
            return True

        except Exception as e:
            print(f"❌ Error loading model: {e}")
            return False

    # Helper methods
    def _load_training_data(self, lookback_days: int) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Load training data from database"""
        conn = get_connection()
        c = conn.cursor()

        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        c.execute("""
            SELECT
                rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d,
                net_gamma, call_wall_distance_pct, put_wall_distance_pct,
                vix_current, liberation_setup_detected, false_floor_detected,
                monthly_magnet_above, monthly_magnet_below, confidence_score,
                primary_regime_type, signal_correct
            FROM regime_signals
            WHERE timestamp >= ?
            AND signal_correct IS NOT NULL
        """, (start_date,))

        rows = c.fetchall()
        conn.close()

        if not rows:
            return np.array([]), np.array([]), []

        # Extract features and labels
        X = []
        y = []

        for row in rows:
            features = list(row[:14])  # All numeric features
            label = row[15]  # signal_correct

            # Handle None values
            features = [f if f is not None else 0 for f in features]

            X.append(features)
            y.append(1 if label == 1 else 0)

        feature_names = [
            'rsi_5m', 'rsi_15m', 'rsi_1h', 'rsi_4h', 'rsi_1d',
            'net_gamma', 'call_wall_distance_pct', 'put_wall_distance_pct',
            'vix_current', 'liberation_setup', 'false_floor',
            'magnet_above', 'magnet_below', 'confidence_score'
        ]

        return np.array(X), np.array(y), feature_names

    def _extract_features_from_regime(self, regime: Dict) -> Optional[List[float]]:
        """Extract feature vector from regime dict"""
        try:
            features = [
                regime.get('rsi_5m', 0),
                regime.get('rsi_15m', 0),
                regime.get('rsi_1h', 0),
                regime.get('rsi_4h', 0),
                regime.get('rsi_1d', 0),
                regime.get('net_gamma', 0),
                regime.get('call_wall_distance_pct', 0),
                regime.get('put_wall_distance_pct', 0),
                regime.get('vix_current', 15),
                1 if regime.get('liberation_setup_detected') else 0,
                1 if regime.get('false_floor_detected') else 0,
                regime.get('monthly_magnet_above', 0),
                regime.get('monthly_magnet_below', 0),
                regime.get('confidence_score', 50)
            ]

            return features

        except Exception as e:
            print(f"Error extracting features: {e}")
            return None

    def _load_historical_patterns(self, lookback_days: int) -> List[Dict]:
        """Load historical patterns with features"""
        conn = get_connection()
        c = conn.cursor()

        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        c.execute("""
            SELECT
                timestamp, primary_regime_type, confidence_score,
                signal_correct, price_change_5d,
                rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d,
                net_gamma, call_wall_distance_pct, put_wall_distance_pct,
                vix_current, liberation_setup_detected, false_floor_detected,
                monthly_magnet_above, monthly_magnet_below
            FROM regime_signals
            WHERE timestamp >= ?
            AND signal_correct IS NOT NULL
        """, (start_date,))

        patterns = []
        for row in c.fetchall():
            features = [f if f is not None else 0 for f in row[5:]]

            patterns.append({
                'timestamp': row[0],
                'pattern': row[1],
                'confidence': row[2],
                'outcome': 'WIN' if row[3] == 1 else 'LOSS',
                'price_change': row[4],
                'features': features
            })

        conn.close()

        return patterns

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two feature vectors"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)

        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


# Singleton instance
_pattern_learner = None

def get_pattern_learner() -> PatternLearner:
    """Get singleton pattern learner"""
    global _pattern_learner
    if _pattern_learner is None:
        _pattern_learner = PatternLearner()
    return _pattern_learner
