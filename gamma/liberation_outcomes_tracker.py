"""
Liberation Outcomes Tracker
Validates if psychology trap predictions actually worked by tracking outcomes
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
from zoneinfo import ZoneInfo
from db.config_and_database import DB_PATH
from database_adapter import get_connection
import pandas as pd

CENTRAL_TZ = ZoneInfo("America/Chicago")


def check_liberation_outcomes():
    """
    Check liberation signals from regime_signals table and validate outcomes

    For each signal that's 1-4 hours old:
    1. Get the original prediction (direction, target, confidence)
    2. Check current price movement
    3. Determine if prediction was correct
    4. Log outcome to liberation_outcomes table
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get regime signals from last 24 hours that haven't been checked yet
        c.execute("""
            SELECT rs.id, rs.timestamp, rs.signal_type, rs.predicted_direction,
                   rs.target_price, rs.confidence, rs.current_price, rs.stop_loss,
                   rs.reasoning, rs.gex_regime
            FROM regime_signals rs
            LEFT JOIN liberation_outcomes lo ON rs.id = lo.regime_signal_id
            WHERE rs.timestamp >= NOW() - INTERVAL '24 hours'
              AND rs.timestamp <= NOW() - INTERVAL '1 hour'
              AND lo.id IS NULL
              AND rs.signal_type IN ('LIBERATION', 'FALSE_FLOOR', 'GAMMA_SQUEEZE')
            ORDER BY rs.timestamp DESC
        """)

        signals = c.fetchall()

        if not signals:
            print("✅ No new signals to check for outcomes")
            conn.close()
            return

        print(f"📊 Checking outcomes for {len(signals)} signals...")

        for signal in signals:
            (signal_id, timestamp, signal_type, predicted_direction, target_price,
             confidence, entry_price, stop_loss, reasoning, gex_regime) = signal

            # Get current SPY price (use latest available data)
            current_price = get_current_spy_price(c)

            if not current_price:
                continue

            # Calculate time since signal
            signal_dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            now = datetime.now(CENTRAL_TZ).replace(tzinfo=None)
            hours_elapsed = (now - signal_dt).total_seconds() / 3600

            # Determine if prediction was correct
            outcome = evaluate_prediction(
                predicted_direction,
                entry_price,
                current_price,
                target_price,
                stop_loss,
                hours_elapsed
            )

            # Calculate actual move
            price_change = current_price - entry_price
            price_change_pct = (price_change / entry_price) * 100

            # Log outcome
            c.execute("""
                INSERT INTO liberation_outcomes (
                    timestamp, regime_signal_id, signal_type, predicted_direction,
                    entry_price, target_price, actual_price, hours_elapsed,
                    outcome, price_change_pct, confidence_score,
                    prediction_correct, gex_regime_at_signal
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                now.strftime('%Y-%m-%d %H:%M:%S'),
                signal_id,
                signal_type,
                predicted_direction,
                entry_price,
                target_price,
                current_price,
                hours_elapsed,
                outcome['status'],
                price_change_pct,
                confidence,
                outcome['correct'],
                gex_regime
            ))

            status_emoji = "✅" if outcome['correct'] else "❌"
            print(f"{status_emoji} Signal #{signal_id} ({signal_type}): "
                  f"{predicted_direction} from ${entry_price:.2f} → ${current_price:.2f} "
                  f"({price_change_pct:+.2f}%) - {outcome['status']}")

        conn.commit()
        print(f"✅ Logged {len(signals)} liberation outcomes")

        # Print summary stats
        c.execute("""
            SELECT
                signal_type,
                COUNT(*) as total,
                SUM(CASE WHEN prediction_correct = TRUE THEN 1 ELSE 0 END) as correct,
                AVG(price_change_pct) as avg_move
            FROM liberation_outcomes
            WHERE timestamp >= NOW() - INTERVAL '7 days'
            GROUP BY signal_type
        """)

        summary = c.fetchall()
        if summary:
            print("\n📈 7-Day Liberation Performance:")
            for signal_type, total, correct, avg_move in summary:
                accuracy = (correct / total * 100) if total > 0 else 0
                print(f"  {signal_type}: {accuracy:.1f}% accuracy ({correct}/{total}) | "
                      f"Avg move: {avg_move:+.2f}%")

        conn.close()

    except Exception as e:
        print(f"❌ Error checking liberation outcomes: {e}")
        import traceback
        traceback.print_exc()


def evaluate_prediction(predicted_direction: str, entry_price: float,
                       current_price: float, target_price: Optional[float],
                       stop_loss: Optional[float], hours_elapsed: float) -> Dict:
    """
    Determine if a prediction was correct based on price movement

    Returns dict with 'correct' (bool) and 'status' (str)
    """
    price_change_pct = ((current_price - entry_price) / entry_price) * 100

    # Define thresholds
    PROFIT_THRESHOLD = 0.3  # 0.3% move in predicted direction = correct
    LOSS_THRESHOLD = -0.5   # -0.5% move against = wrong

    if predicted_direction == 'BULLISH':
        # Check if hit target
        if target_price and current_price >= target_price:
            return {'correct': True, 'status': 'TARGET_HIT'}

        # Check if hit stop
        if stop_loss and current_price <= stop_loss:
            return {'correct': False, 'status': 'STOP_HIT'}

        # Check move size
        if price_change_pct >= PROFIT_THRESHOLD:
            return {'correct': True, 'status': 'MOVING_CORRECTLY'}
        elif price_change_pct <= LOSS_THRESHOLD:
            return {'correct': False, 'status': 'MOVING_WRONG_DIRECTION'}
        else:
            # Too early or inconclusive
            if hours_elapsed < 2:
                return {'correct': None, 'status': 'PENDING'}
            else:
                return {'correct': False, 'status': 'INSUFFICIENT_MOVE'}

    elif predicted_direction == 'BEARISH':
        # Check if hit target
        if target_price and current_price <= target_price:
            return {'correct': True, 'status': 'TARGET_HIT'}

        # Check if hit stop
        if stop_loss and current_price >= stop_loss:
            return {'correct': False, 'status': 'STOP_HIT'}

        # Check move size
        if price_change_pct <= -PROFIT_THRESHOLD:
            return {'correct': True, 'status': 'MOVING_CORRECTLY'}
        elif price_change_pct >= -LOSS_THRESHOLD:
            return {'correct': False, 'status': 'MOVING_WRONG_DIRECTION'}
        else:
            if hours_elapsed < 2:
                return {'correct': None, 'status': 'PENDING'}
            else:
                return {'correct': False, 'status': 'INSUFFICIENT_MOVE'}

    else:  # NEUTRAL
        # For neutral predictions, check if stayed within range
        if abs(price_change_pct) <= 0.5:
            return {'correct': True, 'status': 'STAYED_NEUTRAL'}
        else:
            return {'correct': False, 'status': 'BROKE_OUT_OF_RANGE'}


def get_current_spy_price(cursor) -> Optional[float]:
    """Get latest SPY price from any available source in database"""

    # Try regime_signals (most recent)
    cursor.execute("""
        SELECT current_price
        FROM regime_signals
        WHERE current_price > 0
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    result = cursor.fetchone()
    if result:
        return result[0]

    # Try autonomous_positions
    cursor.execute("""
        SELECT current_spot_price
        FROM autonomous_positions
        WHERE current_spot_price > 0
        ORDER BY entry_date DESC, entry_time DESC
        LIMIT 1
    """)
    result = cursor.fetchone()
    if result:
        return result[0]

    return None


if __name__ == '__main__':
    print("🔍 Liberation Outcomes Tracker - Validating Psychology Trap Predictions\n")
    check_liberation_outcomes()
