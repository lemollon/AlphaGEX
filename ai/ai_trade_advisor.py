"""
AlphaGEX Smart Trade Advisor
Powered by Claude + LangChain with Learning System

This system:
1. Explains WHY you should (or shouldn't) take a trade
2. Provides context-aware analysis (VIX, market regime, pattern history)
3. LEARNS from past predictions to get smarter over time
4. Tracks its own accuracy and adjusts confidence accordingly

The Goal: Give you intelligent, profitable trade recommendations that improve with every trade.
"""

import os
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import psycopg2.extras

from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage

from database_adapter import get_connection

# Note: Using PostgreSQL via database_adapter - no SQLite needed


class SmartTradeAdvisor:
    """
    AI-powered trade advisor that learns from outcomes

    Features:
    - Context-aware trade analysis
    - Historical pattern matching
    - Self-learning from prediction accuracy
    - Transparent reasoning for every recommendation
    """

    def __init__(self, anthropic_api_key: str = None):
        """Initialize the Smart Trade Advisor"""

        self.api_key = anthropic_api_key or os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY or CLAUDE_API_KEY must be set")

        self.llm = ChatAnthropic(
            model="claude-sonnet-4-5-latest",  # Always use latest Sonnet 4.5
            anthropic_api_key=self.api_key,
            temperature=0.2,  # Slightly higher for nuanced trade analysis
            max_tokens=2048
        )

        # Initialize learning database
        self._init_learning_database()

    def _init_learning_database(self):
        """
        Verify AI learning tables exist.
        NOTE: Tables are now defined in db/config_and_database.py (single source of truth).
        Tables expected: ai_predictions, pattern_learning, ai_performance
        """
        # Tables created by main schema - no action needed
        pass

    def get_similar_historical_trades(self, current_pattern: str, current_vix: float,
                                      current_regime: str) -> List[Dict]:
        """Find similar historical trades for pattern matching"""
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Find trades with similar conditions
        vix_range = 3.0  # +/- 3 points
        cursor.execute("""
            SELECT
                timestamp,
                primary_regime_type,
                confidence_score,
                trade_direction,
                vix_current,
                volatility_regime,
                signal_correct,
                price_change_1d,
                price_change_5d
            FROM regime_signals
            WHERE primary_regime_type = %s
              AND vix_current BETWEEN %s AND %s
              AND volatility_regime = %s
              AND signal_correct IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 20
        """, (current_pattern, current_vix - vix_range, current_vix + vix_range, current_regime))

        similar_trades = []
        for row in cursor.fetchall():
            similar_trades.append({
                'date': row['timestamp'],
                'pattern': row['primary_regime_type'],
                'direction': row['trade_direction'],
                'vix': row['vix_current'],
                'regime': row['volatility_regime'],
                'correct': bool(row['signal_correct']),
                'pnl_1d': row['price_change_1d'],
                'pnl_5d': row['price_change_5d']
            })

        conn.close()
        return similar_trades

    def get_ai_track_record(self, days: int = 30) -> Dict:
        """Get AI's recent prediction accuracy"""
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN prediction_correct = 1 THEN 1 ELSE 0 END) as correct,
                AVG(confidence_score) as avg_confidence,
                AVG(CASE WHEN prediction_correct = 1 THEN confidence_score END) as avg_confidence_correct,
                AVG(CASE WHEN prediction_correct = 0 THEN confidence_score END) as avg_confidence_wrong
            FROM ai_predictions
            WHERE timestamp > %s
              AND prediction_correct IS NOT NULL
        """, (cutoff_date,))

        row = cursor.fetchone()
        conn.close()

        if row['total'] == 0:
            return {
                'total_predictions': 0,
                'accuracy': 0,
                'avg_confidence': 0,
                'calibration': 'No data yet'
            }

        accuracy = (row['correct'] / row['total'] * 100) if row['total'] > 0 else 0

        return {
            'total_predictions': row['total'],
            'correct_predictions': row['correct'],
            'accuracy': round(accuracy, 1),
            'avg_confidence': round(row['avg_confidence'], 1),
            'avg_confidence_when_correct': round(row['avg_confidence_correct'] or 0, 1),
            'avg_confidence_when_wrong': round(row['avg_confidence_wrong'] or 0, 1),
            'calibration': 'Well calibrated' if abs(accuracy - row['avg_confidence']) < 10 else 'Needs calibration'
        }

    def analyze_trade(self, signal_data: Dict) -> Dict:
        """
        Analyze a trade signal and provide intelligent recommendation

        Args:
            signal_data: Dict containing:
                - pattern: e.g. 'GAMMA_SQUEEZE_CASCADE'
                - price: current SPY price
                - direction: 'Bullish' or 'Bearish'
                - confidence: signal confidence
                - vix: current VIX
                - volatility_regime: e.g. 'EXPLOSIVE_VOLATILITY'
                - description: pattern description

        Returns:
            Dict with recommendation, reasoning, confidence, and learning data
        """

        # Get similar historical trades
        similar_trades = self.get_similar_historical_trades(
            signal_data.get('pattern'),
            signal_data.get('vix', 15.0),
            signal_data.get('volatility_regime', 'UNKNOWN')
        )

        # Calculate win rate for similar conditions
        if similar_trades:
            wins = sum(1 for t in similar_trades if t['correct'])
            win_rate = (wins / len(similar_trades)) * 100
        else:
            win_rate = None

        # Get AI's own track record
        ai_track_record = self.get_ai_track_record(days=30)

        # Build context for Claude
        context = f"""
Current Trade Signal:
- Pattern: {signal_data.get('pattern')}
- Direction: {signal_data.get('direction')}
- Signal Confidence: {signal_data.get('confidence')}%
- Price: ${signal_data.get('price')}
- VIX: {signal_data.get('vix')}
- Volatility Regime: {signal_data.get('volatility_regime')}
- Description: {signal_data.get('description')}

Historical Performance (Similar Conditions):
- Found {len(similar_trades)} similar trades
- Win Rate: {f"{win_rate:.1f}%" if win_rate is not None else "No data"}
- Sample trades: {json.dumps(similar_trades[:5], indent=2) if similar_trades else "None"}

AI Track Record (Last 30 Days):
- Total Predictions: {ai_track_record['total_predictions']}
- Accuracy: {ai_track_record['accuracy']}%
- Calibration: {ai_track_record['calibration']}
"""

        # Create prompt for Claude
        system_prompt = """You are an expert quantitative trading advisor with a proven track record.

Your role: Analyze trade signals and provide HONEST, DATA-DRIVEN recommendations.

Analysis Framework:
1. Pattern Quality: Is this pattern historically profitable?
2. Current Conditions: Do current market conditions favor this pattern?
3. Risk/Reward: What's the expected gain vs potential loss?
4. Timing: Is NOW the right time to enter this trade?
5. Confidence: How sure are you this will work?

Your Response Must Include:
1. RECOMMENDATION: "TAKE TRADE" or "SKIP" or "WAIT"
2. REASONING: Why? Use specific data points.
3. EXPECTED OUTCOME: Specific price target and timeframe
4. RISK ASSESSMENT: What could go wrong?
5. CONFIDENCE: 0-100% (be honest about uncertainty)
6. ACTION PLAN: Exact entry, stop, and target

Red Flags (Always mention if present):
- Win rate < 60% in similar conditions → Low probability
- VIX spike without confirmation → False signal
- Small sample size (< 10 similar trades) → Unproven
- Pattern works better in different regime → Wrong timing

Be BRUTALLY honest. If you're not confident, say SKIP. Better to miss a trade than lose money.

Your confidence should reflect:
- Historical win rate (most important)
- Sample size (more data = higher confidence)
- Your own track record (adjust based on past accuracy)
- Current market alignment with pattern's ideal conditions
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Analyze this trade signal:\n\n{context}")
        ]

        # Get Claude's analysis
        response = self.llm.invoke(messages)
        analysis = response.content

        # Parse recommendation and confidence
        recommendation = "SKIP"  # Default to conservative
        if "TAKE TRADE" in analysis.upper():
            recommendation = "TAKE_TRADE"
        elif "WAIT" in analysis.upper():
            recommendation = "WAIT"

        # Extract confidence (look for patterns like "Confidence: 75%")
        import re
        confidence_match = re.search(r'confidence[:\s]+(\d+)%', analysis, re.IGNORECASE)
        ai_confidence = int(confidence_match.group(1)) if confidence_match else 50

        # Adjust confidence based on historical accuracy
        if ai_track_record['total_predictions'] > 10:
            # If AI has been overconfident, reduce confidence
            # If AI has been underconfident, increase confidence
            calibration_factor = ai_track_record['accuracy'] / max(ai_track_record['avg_confidence'], 1)
            ai_confidence = min(95, max(5, int(ai_confidence * calibration_factor)))

        # Save prediction for learning
        prediction_id = self._save_prediction(
            pattern_type=signal_data.get('pattern'),
            trade_direction=signal_data.get('direction'),
            predicted_outcome=recommendation,
            confidence=ai_confidence,
            reasoning=analysis,
            market_context=json.dumps({
                'vix': signal_data.get('vix'),
                'regime': signal_data.get('volatility_regime'),
                'price': signal_data.get('price')
            }),
            vix_level=signal_data.get('vix'),
            volatility_regime=signal_data.get('volatility_regime')
        )

        return {
            'recommendation': recommendation,
            'analysis': analysis,
            'confidence': ai_confidence,
            'historical_win_rate': win_rate,
            'similar_trades_count': len(similar_trades),
            'ai_accuracy_30d': ai_track_record['accuracy'],
            'prediction_id': prediction_id,
            'timestamp': datetime.now().isoformat()
        }

    def _save_prediction(self, pattern_type: str, trade_direction: str, predicted_outcome: str,
                        confidence: float, reasoning: str, market_context: str,
                        vix_level: float, volatility_regime: str) -> int:
        """Save prediction for future learning (PostgreSQL)"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ai_predictions (
                pattern_type, trade_direction, predicted_outcome, confidence_score,
                reasoning, market_context, vix_level, volatility_regime
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (pattern_type, trade_direction, predicted_outcome, confidence,
              reasoning, market_context, vix_level, volatility_regime))

        result = cursor.fetchone()
        prediction_id = result[0] if result else 0
        conn.commit()
        conn.close()

        return prediction_id

    def provide_feedback(self, prediction_id: int, actual_outcome: str,
                        outcome_pnl: float) -> Dict:
        """
        Provide feedback on a prediction to enable learning

        Args:
            prediction_id: ID from analyze_trade() call
            actual_outcome: 'WIN' or 'LOSS'
            outcome_pnl: Actual profit/loss percentage

        Returns:
            Dict with learning stats
        """
        conn = get_connection()
        cursor = conn.cursor()

        # Get original prediction
        cursor.execute("""
            SELECT predicted_outcome, confidence_score, pattern_type
            FROM ai_predictions
            WHERE id = %s
        """, (prediction_id,))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return {'error': 'Prediction not found'}

        predicted_outcome, confidence, pattern = row

        # Determine if prediction was correct
        was_correct = (
            (predicted_outcome == 'TAKE_TRADE' and actual_outcome == 'WIN') or
            (predicted_outcome == 'SKIP' and actual_outcome == 'LOSS')
        )

        # Update prediction with actual outcome
        cursor.execute("""
            UPDATE ai_predictions
            SET actual_outcome = %s,
                outcome_pnl = %s,
                prediction_correct = %s,
                feedback_timestamp = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (actual_outcome, outcome_pnl, 1 if was_correct else 0, prediction_id))

        # Update daily performance stats
        today = datetime.now().date().isoformat()
        cursor.execute("""
            INSERT INTO ai_performance (date, total_predictions, correct_predictions, profitable_trades, losing_trades, net_pnl)
            VALUES (%s, 1, %s, %s, %s, %s)
            ON CONFLICT(date) DO UPDATE SET
                total_predictions = ai_performance.total_predictions + 1,
                correct_predictions = ai_performance.correct_predictions + EXCLUDED.correct_predictions,
                profitable_trades = ai_performance.profitable_trades + EXCLUDED.profitable_trades,
                losing_trades = ai_performance.losing_trades + EXCLUDED.losing_trades,
                net_pnl = ai_performance.net_pnl + EXCLUDED.net_pnl,
                accuracy_rate = (CAST(ai_performance.correct_predictions AS REAL) / ai_performance.total_predictions * 100)
        """, (today, 1 if was_correct else 0,
              1 if actual_outcome == 'WIN' else 0,
              1 if actual_outcome == 'LOSS' else 0,
              outcome_pnl))

        conn.commit()
        conn.close()

        # Get updated accuracy
        track_record = self.get_ai_track_record(days=30)

        return {
            'prediction_id': prediction_id,
            'was_correct': was_correct,
            'confidence': confidence,
            'actual_pnl': outcome_pnl,
            'updated_accuracy': track_record['accuracy'],
            'learning_enabled': True
        }

    def get_learning_insights(self) -> Dict:
        """Get insights about what the AI has learned"""
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Overall accuracy
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(prediction_correct) as correct,
                AVG(confidence_score) as avg_confidence
            FROM ai_predictions
            WHERE prediction_correct IS NOT NULL
        """)
        overall = cursor.fetchone()

        # Accuracy by pattern
        cursor.execute("""
            SELECT
                pattern_type,
                COUNT(*) as total,
                SUM(prediction_correct) as correct,
                AVG(confidence_score) as avg_confidence,
                AVG(outcome_pnl) as avg_pnl
            FROM ai_predictions
            WHERE prediction_correct IS NOT NULL
            GROUP BY pattern_type
            ORDER BY (CAST(correct AS REAL) / total) DESC
        """)
        by_pattern = cursor.fetchall()

        # Accuracy by confidence level
        cursor.execute("""
            SELECT
                CASE
                    WHEN confidence_score >= 80 THEN 'High (80-100%)'
                    WHEN confidence_score >= 60 THEN 'Medium (60-79%)'
                    ELSE 'Low (0-59%)'
                END as confidence_level,
                COUNT(*) as total,
                SUM(prediction_correct) as correct,
                AVG(outcome_pnl) as avg_pnl
            FROM ai_predictions
            WHERE prediction_correct IS NOT NULL
            GROUP BY confidence_level
        """)
        by_confidence = cursor.fetchall()

        conn.close()

        return {
            'overall_accuracy': round((overall['correct'] / overall['total'] * 100) if overall['total'] > 0 else 0, 1),
            'total_predictions': overall['total'],
            'avg_confidence': round(overall['avg_confidence'] or 0, 1),
            'by_pattern': [dict(row) for row in by_pattern],
            'by_confidence_level': [dict(row) for row in by_confidence]
        }


# ============================================================================
# Command-Line Interface
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Smart Trade Advisor with Learning')
    parser.add_argument('--analyze', action='store_true', help='Analyze a sample trade')
    parser.add_argument('--insights', action='store_true', help='Show learning insights')
    parser.add_argument('--api-key', help='Anthropic API key')

    args = parser.parse_args()

    try:
        advisor = SmartTradeAdvisor(anthropic_api_key=args.api_key)

        if args.insights:
            print("\n📊 AI LEARNING INSIGHTS\n")
            insights = advisor.get_learning_insights()
            print(json.dumps(insights, indent=2))

        elif args.analyze:
            # Sample trade for testing
            sample_trade = {
                'pattern': 'GAMMA_SQUEEZE_CASCADE',
                'price': 570.25,
                'direction': 'Bullish',
                'confidence': 85,
                'vix': 18.5,
                'volatility_regime': 'EXPLOSIVE_VOLATILITY',
                'description': 'VIX spike + short gamma detected'
            }

            print("\n🤖 Analyzing Sample Trade...\n")
            result = advisor.analyze_trade(sample_trade)

            print("="*80)
            print(f"RECOMMENDATION: {result['recommendation']}")
            print(f"CONFIDENCE: {result['confidence']}%")
            print(f"Historical Win Rate: {result['historical_win_rate']:.1f}%" if result['historical_win_rate'] else "No historical data")
            print("="*80)
            print("\nANALYSIS:")
            print(result['analysis'])
            print("="*80)

        else:
            print("Usage:")
            print("  python ai_trade_advisor.py --analyze")
            print("  python ai_trade_advisor.py --insights")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure:")
        print("1. ANTHROPIC_API_KEY is set")
        print("2. Database exists")
        print("3. langchain-anthropic is installed: pip install langchain-anthropic")
