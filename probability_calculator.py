"""
AlphaGEX Probability Calculator

Combines GEX, volatility, psychology, and historical data to predict:
1. EOD (End of Day) probability - where price will close today
2. Next Day probability - where price will close next trading day

Self-learning system that calibrates based on actual outcomes.
"""

import sqlite3
import requests
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
from dataclasses import dataclass


@dataclass
class ProbabilityWeights:
    """Configurable weights for probability calculation - can be adjusted via calibration"""
    gex_wall_strength: float = 0.35  # How much GEX walls influence probability
    volatility_impact: float = 0.25  # How much VIX/IV affects ranges
    psychology_signal: float = 0.20  # How much FOMO/Fear affects prediction
    mm_positioning: float = 0.15     # How much MM state matters
    historical_pattern: float = 0.05  # How much historical data confirms

    def to_dict(self):
        return {
            'gex_wall_strength': self.gex_wall_strength,
            'volatility_impact': self.volatility_impact,
            'psychology_signal': self.psychology_signal,
            'mm_positioning': self.mm_positioning,
            'historical_pattern': self.historical_pattern
        }


class ProbabilityCalculator:
    def __init__(self, db_path: str = "gex_copilot.db", tradingvol_api_key: str = None):
        self.db_path = db_path
        self.tradingvol_api_key = tradingvol_api_key or os.getenv('TRADINGVOL_API_KEY', 'I-RWFNBLR2S1DP')
        self.tradingvol_endpoint = 'https://stocks.tradingvolatility.net/api'
        self.weights = self._load_weights()
        self._init_database()

    def _init_database(self):
        """Initialize database tables for predictions, outcomes, and weights"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Predictions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS probability_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                prediction_type TEXT NOT NULL,  -- 'EOD' or 'NEXT_DAY'
                target_date DATE NOT NULL,
                current_price REAL,

                -- Probability ranges
                range_low REAL,
                range_high REAL,
                prob_in_range REAL,
                prob_above REAL,
                prob_below REAL,
                confidence_level TEXT,  -- 'HIGH', 'MEDIUM', 'LOW'

                -- Input data (for debugging/analysis)
                net_gex REAL,
                flip_point REAL,
                call_wall REAL,
                put_wall REAL,
                vix_level REAL,
                implied_vol REAL,
                psychology_state TEXT,
                fomo_level REAL,
                fear_level REAL,
                mm_state TEXT,

                -- Outcome (filled later)
                actual_close_price REAL,
                prediction_correct BOOLEAN,
                recorded_at DATETIME
            )
        ''')

        # Outcomes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS probability_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id INTEGER,
                actual_close_price REAL,
                prediction_correct BOOLEAN,
                error_pct REAL,
                recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prediction_id) REFERENCES probability_predictions(id)
            )
        ''')

        # Weights table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS probability_weights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                gex_wall_strength REAL,
                volatility_impact REAL,
                psychology_signal REAL,
                mm_positioning REAL,
                historical_pattern REAL,
                accuracy_score REAL,  -- Overall accuracy with these weights
                active BOOLEAN DEFAULT 1
            )
        ''')

        # Calibration history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS calibration_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                predictions_analyzed INTEGER,
                overall_accuracy REAL,
                eod_accuracy REAL,
                next_day_accuracy REAL,
                high_conf_accuracy REAL,
                medium_conf_accuracy REAL,
                low_conf_accuracy REAL,
                adjustments_made TEXT  -- JSON of weight changes
            )
        ''')

        conn.commit()
        conn.close()

    def _load_weights(self) -> ProbabilityWeights:
        """Load active weights from database or use defaults"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT gex_wall_strength, volatility_impact, psychology_signal,
                       mm_positioning, historical_pattern
                FROM probability_weights
                WHERE active = 1
                ORDER BY timestamp DESC
                LIMIT 1
            ''')

            result = cursor.fetchone()
            conn.close()

            if result:
                return ProbabilityWeights(*result)
        except:
            pass

        # Return defaults if no weights in DB
        return ProbabilityWeights()

    def _fetch_tradingvol_data(self, symbol: str, endpoint: str, params: dict = None) -> Optional[dict]:
        """Fetch data from TradingVolatility API"""
        try:
            if params is None:
                params = {}
            params['username'] = self.tradingvol_api_key
            params['ticker'] = symbol
            params['format'] = 'json'

            response = requests.get(
                f"{self.tradingvol_endpoint}/{endpoint}",
                params=params,
                headers={'Accept': 'application/json'},
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching {endpoint} for {symbol}: {e}")

        return None

    def _get_historical_gex_patterns(self, symbol: str, days: int = 30) -> List[dict]:
        """Get historical GEX data for pattern matching"""
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        data = self._fetch_tradingvol_data(
            symbol,
            'gex/history',
            {'start': start_date, 'end': end_date}
        )

        if data and symbol in data:
            return data[symbol]
        return []

    def _calculate_gex_probability(self, gex_data: dict, current_price: float) -> Tuple[float, float, float]:
        """
        Calculate probability based on GEX walls
        Returns: (prob_in_range, prob_above, prob_below)
        """
        flip_point = gex_data.get('flip_point', current_price)
        net_gex = gex_data.get('net_gex', 0)
        call_wall = gex_data.get('call_wall', current_price * 1.02)
        put_wall = gex_data.get('put_wall', current_price * 0.98)

        # Positive GEX = market pins price between walls
        # Negative GEX = market allows explosive moves

        if net_gex > 1e9:  # Strong positive GEX
            # High probability of staying in range
            prob_in_range = 0.75
            prob_above = 0.15
            prob_below = 0.10
        elif net_gex > 0:  # Moderate positive GEX
            prob_in_range = 0.65
            prob_above = 0.20
            prob_below = 0.15
        elif net_gex > -1e9:  # Slight negative GEX
            prob_in_range = 0.50
            prob_above = 0.25
            prob_below = 0.25
        else:  # Strong negative GEX
            # Higher probability of breakout
            prob_in_range = 0.35
            prob_above = 0.35
            prob_below = 0.30

        # Adjust based on distance from flip point
        distance_from_flip = abs(current_price - flip_point) / current_price
        if distance_from_flip > 0.02:  # More than 2% from flip
            # Less certainty
            prob_in_range *= 0.9
            prob_above += 0.05
            prob_below += 0.05

        return (prob_in_range, prob_above, prob_below)

    def _calculate_volatility_adjustment(self, vix: float, implied_vol: float) -> float:
        """
        Calculate volatility adjustment factor
        High volatility = wider ranges, lower confidence
        """
        # VIX thresholds
        if vix < 15:  # Low volatility
            return 1.2  # Increases confidence in range
        elif vix < 20:  # Normal volatility
            return 1.0
        elif vix < 30:  # Elevated volatility
            return 0.8  # Decreases confidence
        else:  # High volatility
            return 0.6  # Much less confidence

    def _calculate_psychology_adjustment(self, psychology_data: dict) -> Tuple[float, str]:
        """
        Calculate psychology adjustment
        Returns: (adjustment_factor, insight)
        """
        fomo_level = psychology_data.get('fomo_level', 50)
        fear_level = psychology_data.get('fear_level', 50)

        # Extreme FOMO = reversal likely
        if fomo_level > 80:
            return (0.7, "⚠️ Extreme FOMO - reversal risk high")

        # Extreme Fear = bounce likely
        if fear_level > 80:
            return (0.75, "⚠️ Extreme Fear - bounce potential")

        # Balanced psychology = trend continuation
        if 40 < fomo_level < 60 and 40 < fear_level < 60:
            return (1.1, "✓ Balanced psychology - sustainable move")

        return (1.0, "Neutral psychology")

    def _calculate_mm_state_impact(self, mm_state: str) -> Tuple[float, str]:
        """Calculate market maker state impact on probability"""
        state_impacts = {
            'DEFENDING': (1.15, "✓ MM Defending - dampened volatility expected"),
            'NEUTRAL': (1.0, "Neutral MM positioning"),
            'SQUEEZING': (0.8, "⚠️ MM Squeezing - explosive move possible"),
            'PANICKING': (0.6, "🚨 MM Panicking - high volatility expected"),
            'BREAKDOWN': (0.7, "⚠️ Breakdown mode - volatility elevated")
        }

        return state_impacts.get(mm_state, (1.0, "Unknown MM state"))

    def _find_similar_historical_setups(self, symbol: str, current_gex: float, current_vix: float) -> dict:
        """Find similar historical setups and calculate their outcomes"""
        historical = self._get_historical_gex_patterns(symbol, days=60)

        if not historical:
            return {'confidence': 0, 'pattern_matches': 0}

        similar_setups = []

        for record in historical:
            hist_gex = float(record.get('skew_adjusted_gex', 0))
            hist_price = float(record.get('price', 0))
            hist_flip = float(record.get('gex_flip_price', hist_price))

            # Check if GEX is similar (within 30%)
            if abs(hist_gex - current_gex) / abs(current_gex + 1) < 0.3:
                similar_setups.append(record)

        if len(similar_setups) > 5:
            return {
                'confidence': 0.8,
                'pattern_matches': len(similar_setups),
                'insight': f"✓ {len(similar_setups)} similar setups in past 60 days"
            }
        elif len(similar_setups) > 2:
            return {
                'confidence': 0.6,
                'pattern_matches': len(similar_setups),
                'insight': f"~ {len(similar_setups)} similar setups found"
            }
        else:
            return {
                'confidence': 0.3,
                'pattern_matches': len(similar_setups),
                'insight': "⚠️ Limited historical precedent"
            }

    def calculate_probability(
        self,
        symbol: str,
        current_price: float,
        gex_data: dict,
        psychology_data: dict,
        prediction_type: str = 'EOD'
    ) -> dict:
        """
        Calculate probability combining all signals

        Args:
            symbol: Ticker symbol
            current_price: Current price
            gex_data: GEX data (flip_point, net_gex, call_wall, put_wall, vix, iv)
            psychology_data: Psychology data (fomo_level, fear_level, state)
            prediction_type: 'EOD' or 'NEXT_DAY'

        Returns:
            Dictionary with probability ranges, confidence, supporting factors, trading insights
        """

        # Extract data
        net_gex = gex_data.get('net_gex', 0)
        flip_point = gex_data.get('flip_point', current_price)
        call_wall = gex_data.get('call_wall', current_price * 1.02)
        put_wall = gex_data.get('put_wall', current_price * 0.98)
        vix = gex_data.get('vix', 18)
        implied_vol = gex_data.get('implied_vol', 0.3)
        mm_state = gex_data.get('mm_state', 'NEUTRAL')

        # 1. GEX-based probability
        base_prob_in, base_prob_above, base_prob_below = self._calculate_gex_probability(gex_data, current_price)

        # 2. Volatility adjustment
        vol_adj = self._calculate_volatility_adjustment(vix, implied_vol)

        # 3. Psychology adjustment
        psych_adj, psych_insight = self._calculate_psychology_adjustment(psychology_data)

        # 4. MM state impact
        mm_adj, mm_insight = self._calculate_mm_state_impact(mm_state)

        # 5. Historical pattern matching
        historical = self._find_similar_historical_setups(symbol, net_gex, vix)
        hist_adj = historical.get('confidence', 0.5)

        # Combine with weights
        final_in_range = base_prob_in * (
            self.weights.gex_wall_strength * 1.0 +
            self.weights.volatility_impact * vol_adj +
            self.weights.psychology_signal * psych_adj +
            self.weights.mm_positioning * mm_adj +
            self.weights.historical_pattern * hist_adj
        )

        # Normalize to ensure probabilities sum to 1.0
        total_weight = sum([
            self.weights.gex_wall_strength,
            self.weights.volatility_impact * vol_adj,
            self.weights.psychology_signal * psych_adj,
            self.weights.mm_positioning * mm_adj,
            self.weights.historical_pattern * hist_adj
        ])

        final_in_range = min(0.95, max(0.10, final_in_range / total_weight))
        final_above = base_prob_above * (1.0 - final_in_range) / (base_prob_above + base_prob_below)
        final_below = 1.0 - final_in_range - final_above

        # Determine confidence level
        if final_in_range > 0.70 and vix < 20:
            confidence = "HIGH"
        elif final_in_range > 0.55 and vix < 25:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Generate supporting factors
        supporting_factors = []

        if net_gex > 1e9:
            supporting_factors.append(f"✓ Strong positive GEX ({net_gex/1e9:.1f}B) = pinning expected")
        elif net_gex < -1e9:
            supporting_factors.append(f"⚠️ Strong negative GEX ({net_gex/1e9:.1f}B) = explosive moves possible")

        if call_wall and call_wall > current_price:
            supporting_factors.append(f"✓ Call wall at ${call_wall:.2f} = resistance")

        if put_wall and put_wall < current_price:
            supporting_factors.append(f"✓ Put wall at ${put_wall:.2f} = support")

        supporting_factors.append(f"VIX: {vix:.1f} - {vol_adj_to_text(vol_adj)}")
        supporting_factors.append(psych_insight)
        supporting_factors.append(mm_insight)

        if historical.get('pattern_matches', 0) > 0:
            supporting_factors.append(historical.get('insight', ''))

        # Generate trading insights
        trading_insights = self._generate_trading_insights(
            final_in_range,
            final_above,
            final_below,
            confidence,
            put_wall,
            call_wall,
            current_price,
            vix
        )

        # Save prediction to database
        prediction_id = self._save_prediction(
            symbol=symbol,
            prediction_type=prediction_type,
            current_price=current_price,
            range_low=put_wall,
            range_high=call_wall,
            prob_in_range=final_in_range,
            prob_above=final_above,
            prob_below=final_below,
            confidence_level=confidence,
            gex_data=gex_data,
            psychology_data=psychology_data
        )

        return {
            'symbol': symbol,
            'prediction_type': prediction_type,
            'prediction_id': prediction_id,
            'confidence': confidence,
            'current_price': current_price,
            'ranges': [
                {
                    'range': f"${put_wall:.2f} - ${call_wall:.2f}",
                    'probability': round(final_in_range * 100, 1)
                },
                {
                    'range': f"Above ${call_wall:.2f}",
                    'probability': round(final_above * 100, 1)
                },
                {
                    'range': f"Below ${put_wall:.2f}",
                    'probability': round(final_below * 100, 1)
                }
            ],
            'supporting_factors': supporting_factors,
            'trading_insights': trading_insights
        }

    def _generate_trading_insights(
        self,
        prob_in_range: float,
        prob_above: float,
        prob_below: float,
        confidence: str,
        put_wall: float,
        call_wall: float,
        current_price: float,
        vix: float
    ) -> List[dict]:
        """Generate actionable trading insights"""
        insights = []

        # High probability range-bound setup
        if prob_in_range > 0.65:
            insights.append({
                'setup': f'HIGH PROBABILITY ({prob_in_range*100:.0f}%): Price stays ${put_wall:.2f}-${call_wall:.2f}',
                'action': 'Sell iron condor or credit spreads at range edges',
                'why': f'Strong GEX walls + {confidence} confidence = range-bound',
                'risk': 'Low' if confidence == 'HIGH' else 'Medium',
                'expected': 'High win rate, consistent small gains',
                'color': 'success'
            })

        # Breakout setup
        if prob_above > 0.30:
            insights.append({
                'setup': f'MODERATE PROBABILITY ({prob_above*100:.0f}%): Breakout above ${call_wall:.2f}',
                'action': 'Small size calls or spreads IF breakout confirmed' if prob_above > 0.35 else 'SKIP - Low probability',
                'why': f'Fighting call wall - MM will defend' if prob_above < 0.35 else 'Potential gamma squeeze',
                'risk': 'High' if prob_above < 0.35 else 'Medium',
                'expected': 'Lower win rate, but asymmetric gains if right',
                'color': 'warning' if prob_above > 0.35 else 'danger'
            })

        # Breakdown setup
        if prob_below > 0.30:
            insights.append({
                'setup': f'MODERATE PROBABILITY ({prob_below*100:.0f}%): Breakdown below ${put_wall:.2f}',
                'action': 'Small size puts or spreads IF breakdown confirmed' if prob_below > 0.35 else 'SKIP - Low probability',
                'why': f'Put wall support strong' if prob_below < 0.35 else 'Support breaking',
                'risk': 'High' if prob_below < 0.35 else 'Medium',
                'expected': 'Lower win rate, asymmetric downside',
                'color': 'warning' if prob_below > 0.35 else 'danger'
            })

        # High volatility warning
        if vix > 25:
            insights.append({
                'setup': f'⚠️ HIGH VOLATILITY WARNING (VIX: {vix:.1f})',
                'action': 'Reduce position size by 50% or wait',
                'why': 'Elevated VIX = unpredictable moves',
                'risk': 'Very High',
                'expected': 'Wider ranges, lower accuracy',
                'color': 'danger'
            })

        return insights

    def _save_prediction(self, **kwargs) -> int:
        """Save prediction to database and return prediction_id"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        gex_data = kwargs.get('gex_data', {})
        psychology_data = kwargs.get('psychology_data', {})

        # Calculate target date
        target_date = datetime.now()
        if kwargs.get('prediction_type') == 'NEXT_DAY':
            target_date += timedelta(days=1)
            # Skip weekends
            while target_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                target_date += timedelta(days=1)

        cursor.execute('''
            INSERT INTO probability_predictions (
                symbol, prediction_type, target_date, current_price,
                range_low, range_high, prob_in_range, prob_above, prob_below,
                confidence_level, net_gex, flip_point, call_wall, put_wall,
                vix_level, implied_vol, psychology_state, fomo_level, fear_level, mm_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            kwargs.get('symbol'),
            kwargs.get('prediction_type'),
            target_date.strftime('%Y-%m-%d'),
            kwargs.get('current_price'),
            kwargs.get('range_low'),
            kwargs.get('range_high'),
            kwargs.get('prob_in_range'),
            kwargs.get('prob_above'),
            kwargs.get('prob_below'),
            kwargs.get('confidence_level'),
            gex_data.get('net_gex'),
            gex_data.get('flip_point'),
            gex_data.get('call_wall'),
            gex_data.get('put_wall'),
            gex_data.get('vix'),
            gex_data.get('implied_vol'),
            psychology_data.get('state'),
            psychology_data.get('fomo_level'),
            psychology_data.get('fear_level'),
            gex_data.get('mm_state')
        ))

        prediction_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return prediction_id

    def record_outcome(self, prediction_id: int, actual_close_price: float):
        """Record actual outcome for a prediction"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get prediction
        cursor.execute('''
            SELECT range_low, range_high, prob_in_range
            FROM probability_predictions
            WHERE id = ?
        ''', (prediction_id,))

        result = cursor.fetchone()
        if not result:
            conn.close()
            return

        range_low, range_high, prob_in_range = result

        # Determine if prediction was correct
        prediction_correct = range_low <= actual_close_price <= range_high

        # Calculate error percentage
        midpoint = (range_low + range_high) / 2
        error_pct = abs(actual_close_price - midpoint) / midpoint * 100

        # Update prediction
        cursor.execute('''
            UPDATE probability_predictions
            SET actual_close_price = ?, prediction_correct = ?, recorded_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (actual_close_price, prediction_correct, prediction_id))

        # Insert outcome
        cursor.execute('''
            INSERT INTO probability_outcomes (prediction_id, actual_close_price, prediction_correct, error_pct)
            VALUES (?, ?, ?, ?)
        ''', (prediction_id, actual_close_price, prediction_correct, error_pct))

        conn.commit()
        conn.close()

    def get_accuracy_metrics(self, days: int = 30) -> dict:
        """Get accuracy metrics for past predictions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Overall accuracy
        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN prediction_correct = 1 THEN 1 ELSE 0 END) as correct,
                AVG(CASE WHEN prediction_correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy
            FROM probability_predictions
            WHERE recorded_at IS NOT NULL
            AND target_date >= ?
        ''', (cutoff_date,))

        overall = cursor.fetchone()

        # By prediction type
        cursor.execute('''
            SELECT
                prediction_type,
                COUNT(*) as total,
                AVG(CASE WHEN prediction_correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy
            FROM probability_predictions
            WHERE recorded_at IS NOT NULL
            AND target_date >= ?
            GROUP BY prediction_type
        ''', (cutoff_date,))

        by_type = {row[0]: {'total': row[1], 'accuracy': row[2]} for row in cursor.fetchall()}

        # By confidence level
        cursor.execute('''
            SELECT
                confidence_level,
                COUNT(*) as total,
                AVG(CASE WHEN prediction_correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy
            FROM probability_predictions
            WHERE recorded_at IS NOT NULL
            AND target_date >= ?
            GROUP BY confidence_level
        ''', (cutoff_date,))

        by_confidence = {row[0]: {'total': row[1], 'accuracy': row[2]} for row in cursor.fetchall()}

        conn.close()

        return {
            'overall': {
                'total_predictions': overall[0],
                'correct_predictions': overall[1],
                'accuracy_pct': round((overall[2] or 0) * 100, 1)
            },
            'by_type': by_type,
            'by_confidence': by_confidence,
            'period_days': days
        }

    def calibrate(self, min_predictions: int = 50) -> dict:
        """
        Calibrate weights based on prediction accuracy

        This is Phase 2 self-learning: adjust weights to improve accuracy
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all predictions with outcomes
        cursor.execute('''
            SELECT
                id, confidence_level, prediction_correct,
                net_gex, vix_level, fomo_level, mm_state
            FROM probability_predictions
            WHERE recorded_at IS NOT NULL
        ''')

        predictions = cursor.fetchall()

        if len(predictions) < min_predictions:
            conn.close()
            return {
                'success': False,
                'message': f'Need at least {min_predictions} predictions with outcomes. Currently have {len(predictions)}.'
            }

        # Calculate current accuracy
        correct = sum(1 for p in predictions if p[2])
        current_accuracy = correct / len(predictions)

        # Analyze which signals are working
        high_conf_correct = sum(1 for p in predictions if p[1] == 'HIGH' and p[2])
        high_conf_total = sum(1 for p in predictions if p[1] == 'HIGH')
        high_conf_accuracy = high_conf_correct / high_conf_total if high_conf_total > 0 else 0

        # Simple calibration: if high confidence accuracy is low, reduce confidence threshold
        adjustments = {}

        if high_conf_accuracy < 0.70:  # High confidence should be > 70% accurate
            # Increase GEX wall weight (more conservative)
            adjustments['gex_wall_strength'] = min(0.45, self.weights.gex_wall_strength * 1.1)
            # Decrease psychology weight (may be noisy)
            adjustments['psychology_signal'] = max(0.10, self.weights.psychology_signal * 0.9)

        if current_accuracy > 0.75:  # System is working well, fine-tune
            # Slightly increase historical pattern weight
            adjustments['historical_pattern'] = min(0.10, self.weights.historical_pattern * 1.2)

        # Apply adjustments
        if adjustments:
            new_weights = ProbabilityWeights(
                gex_wall_strength=adjustments.get('gex_wall_strength', self.weights.gex_wall_strength),
                volatility_impact=adjustments.get('volatility_impact', self.weights.volatility_impact),
                psychology_signal=adjustments.get('psychology_signal', self.weights.psychology_signal),
                mm_positioning=adjustments.get('mm_positioning', self.weights.mm_positioning),
                historical_pattern=adjustments.get('historical_pattern', self.weights.historical_pattern)
            )

            # Deactivate old weights
            cursor.execute('UPDATE probability_weights SET active = 0')

            # Save new weights
            cursor.execute('''
                INSERT INTO probability_weights (
                    gex_wall_strength, volatility_impact, psychology_signal,
                    mm_positioning, historical_pattern, accuracy_score
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                new_weights.gex_wall_strength,
                new_weights.volatility_impact,
                new_weights.psychology_signal,
                new_weights.mm_positioning,
                new_weights.historical_pattern,
                current_accuracy
            ))

            # Log calibration
            cursor.execute('''
                INSERT INTO calibration_history (
                    predictions_analyzed, overall_accuracy, high_conf_accuracy, adjustments_made
                ) VALUES (?, ?, ?, ?)
            ''', (
                len(predictions),
                current_accuracy,
                high_conf_accuracy,
                json.dumps(adjustments)
            ))

            conn.commit()
            self.weights = new_weights

        conn.close()

        return {
            'success': True,
            'predictions_analyzed': len(predictions),
            'current_accuracy': round(current_accuracy * 100, 1),
            'high_confidence_accuracy': round(high_conf_accuracy * 100, 1),
            'adjustments_made': adjustments,
            'new_weights': self.weights.to_dict() if adjustments else None
        }


def vol_adj_to_text(vol_adj: float) -> str:
    """Convert volatility adjustment to text"""
    if vol_adj > 1.1:
        return "Low volatility (tighter ranges)"
    elif vol_adj > 0.9:
        return "Normal volatility"
    elif vol_adj > 0.7:
        return "Elevated volatility (wider ranges)"
    else:
        return "High volatility (unpredictable)"


# Example usage
if __name__ == "__main__":
    calc = ProbabilityCalculator()

    # Example data
    gex_data = {
        'net_gex': -2500000000,
        'flip_point': 568.50,
        'call_wall': 572.00,
        'put_wall': 565.00,
        'vix': 18.5,
        'implied_vol': 0.25,
        'mm_state': 'SQUEEZING'
    }

    psychology_data = {
        'fomo_level': 62,
        'fear_level': 38,
        'state': 'MODERATE_FOMO'
    }

    result = calc.calculate_probability(
        symbol='SPY',
        current_price=570.25,
        gex_data=gex_data,
        psychology_data=psychology_data,
        prediction_type='EOD'
    )

    print(json.dumps(result, indent=2))
