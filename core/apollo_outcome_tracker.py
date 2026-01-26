#!/usr/bin/env python3
"""
Apollo Automated Outcome Tracker

This module automatically tracks the outcomes of Apollo predictions by:
1. Finding predictions older than 24 hours without recorded outcomes
2. Fetching historical price data to determine actual movement
3. Calculating direction correctness (bullish/bearish/neutral)
4. Calculating magnitude correctness (small/medium/large)
5. Recording outcomes in the apollo_outcomes table

This enables the Apollo performance metrics to actually show data!

CREATED: January 2026
FIX: Apollo Model performance 30 days wasn't showing data because
     outcomes were never being tracked automatically.
"""

import os
import sys
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

logger = logging.getLogger(__name__)

# Texas Central Time
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Magnitude thresholds (percent move)
MAGNITUDE_SMALL_THRESHOLD = 1.0   # < 1% = small
MAGNITUDE_MEDIUM_THRESHOLD = 3.0  # 1-3% = medium, > 3% = large


def get_tradier_client():
    """Get Tradier client for fetching price data"""
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        from unified_config import APIConfig

        api_key = APIConfig.TRADIER_SANDBOX_API_KEY or APIConfig.TRADIER_API_KEY
        account_id = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

        if api_key and account_id:
            return TradierDataFetcher(api_key=api_key, account_id=account_id, sandbox=True)
    except Exception as e:
        logger.error(f"Failed to initialize Tradier: {e}")
    return None


def get_polygon_client():
    """Fallback: Get Polygon client for price data"""
    try:
        from data.polygon_data_fetcher import PolygonDataFetcher
        from unified_config import APIConfig

        if APIConfig.POLYGON_API_KEY:
            return PolygonDataFetcher(api_key=APIConfig.POLYGON_API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Polygon: {e}")
    return None


def get_price_at_time(symbol: str, target_time: datetime) -> Optional[float]:
    """
    Get the price for a symbol at approximately the given time.
    Uses Tradier for recent data, Polygon for historical.
    """
    now = datetime.now(CENTRAL_TZ)
    hours_ago = (now - target_time).total_seconds() / 3600

    # For recent data (< 24 hours), use Tradier live quote
    if hours_ago < 24:
        tradier = get_tradier_client()
        if tradier:
            try:
                quote = tradier.get_quote(symbol)
                if quote:
                    return quote.get('last') or quote.get('close')
            except Exception as e:
                logger.warning(f"Tradier quote failed for {symbol}: {e}")

    # For historical data, use Polygon
    polygon = get_polygon_client()
    if polygon:
        try:
            # Get historical bars around the target time
            bars = polygon.get_historical_bars(
                symbol,
                start_date=target_time.strftime('%Y-%m-%d'),
                end_date=target_time.strftime('%Y-%m-%d'),
                timespan='hour'
            )
            if bars and len(bars) > 0:
                # Find the bar closest to target_time
                target_hour = target_time.hour
                for bar in bars:
                    bar_time = bar.get('timestamp') or bar.get('t')
                    if bar_time:
                        # Return close price of matching hour
                        return bar.get('close') or bar.get('c')
                # If no exact match, return the last bar's close
                return bars[-1].get('close') or bars[-1].get('c')
        except Exception as e:
            logger.warning(f"Polygon historical data failed for {symbol}: {e}")

    # Last resort: Try Tradier live quote
    tradier = get_tradier_client()
    if tradier:
        try:
            quote = tradier.get_quote(symbol)
            if quote:
                return quote.get('last') or quote.get('close')
        except Exception as e:
            logger.warning(f"Fallback Tradier quote failed: {e}")

    return None


def calculate_direction(price_at_prediction: float, price_now: float) -> str:
    """Determine actual direction based on price movement"""
    if price_at_prediction <= 0 or price_now <= 0:
        return "neutral"

    pct_change = ((price_now - price_at_prediction) / price_at_prediction) * 100

    if pct_change > 0.5:
        return "bullish"
    elif pct_change < -0.5:
        return "bearish"
    else:
        return "neutral"


def calculate_magnitude(price_at_prediction: float, price_now: float) -> str:
    """Determine actual magnitude based on absolute price movement"""
    if price_at_prediction <= 0 or price_now <= 0:
        return "small"

    pct_change = abs((price_now - price_at_prediction) / price_at_prediction) * 100

    if pct_change < MAGNITUDE_SMALL_THRESHOLD:
        return "small"
    elif pct_change < MAGNITUDE_MEDIUM_THRESHOLD:
        return "medium"
    else:
        return "large"


def get_untracked_predictions(min_age_hours: int = 24, max_age_days: int = 7) -> List[Dict]:
    """
    Find predictions that are old enough to evaluate but don't have outcomes yet.

    Args:
        min_age_hours: Minimum age in hours before evaluating (default 24)
        max_age_days: Maximum age in days to consider (default 7)

    Returns:
        List of prediction records
    """
    conn = get_connection()
    if not conn:
        return []

    try:
        c = conn.cursor()

        # Find predictions that:
        # 1. Are older than min_age_hours
        # 2. Are newer than max_age_days
        # 3. Don't have a matching outcome
        c.execute('''
            SELECT
                p.prediction_id,
                p.scan_id,
                p.timestamp,
                p.symbol,
                p.direction_pred,
                p.direction_confidence,
                p.magnitude_pred,
                p.magnitude_confidence,
                p.features
            FROM apollo_predictions p
            LEFT JOIN apollo_outcomes o ON p.prediction_id = o.prediction_id
            WHERE o.id IS NULL
              AND p.timestamp < NOW() - INTERVAL '%s hours'
              AND p.timestamp > NOW() - INTERVAL '%s days'
            ORDER BY p.timestamp ASC
            LIMIT 100
        ''', (min_age_hours, max_age_days))

        predictions = []
        for row in c.fetchall():
            predictions.append({
                'prediction_id': row[0],
                'scan_id': row[1],
                'timestamp': row[2],
                'symbol': row[3],
                'direction_pred': row[4],
                'direction_confidence': row[5],
                'magnitude_pred': row[6],
                'magnitude_confidence': row[7],
                'features': row[8]
            })

        return predictions

    except Exception as e:
        logger.error(f"Failed to get untracked predictions: {e}")
        return []
    finally:
        conn.close()


def record_outcome(
    prediction_id: str,
    symbol: str,
    predicted_direction: str,
    actual_direction: str,
    predicted_magnitude: str,
    actual_magnitude: str,
    actual_return_pct: float
) -> bool:
    """Record an outcome for a prediction"""
    conn = get_connection()
    if not conn:
        return False

    try:
        c = conn.cursor()

        outcome_id = str(uuid.uuid4())[:12]
        direction_correct = predicted_direction.lower() == actual_direction.lower()
        magnitude_correct = predicted_magnitude.lower() == actual_magnitude.lower()

        c.execute('''
            INSERT INTO apollo_outcomes (
                outcome_id, prediction_id, symbol, predicted_direction, actual_direction,
                predicted_magnitude, actual_magnitude, actual_return_pct,
                direction_correct, magnitude_correct, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            outcome_id,
            prediction_id,
            symbol,
            predicted_direction,
            actual_direction,
            predicted_magnitude,
            actual_magnitude,
            actual_return_pct,
            direction_correct,
            magnitude_correct,
            'Auto-tracked by apollo_outcome_tracker'
        ))

        conn.commit()
        logger.info(f"Recorded outcome for {symbol}: direction={direction_correct}, magnitude={magnitude_correct}")
        return True

    except Exception as e:
        logger.error(f"Failed to record outcome: {e}")
        return False
    finally:
        conn.close()


def track_apollo_outcomes(min_age_hours: int = 24, max_age_days: int = 7) -> Dict:
    """
    Main function to track outcomes for all untracked predictions.

    Args:
        min_age_hours: Minimum age before evaluating predictions
        max_age_days: Maximum age to consider

    Returns:
        Summary of tracking results
    """
    logger.info("=" * 60)
    logger.info("APOLLO OUTCOME TRACKER - Starting")
    logger.info("=" * 60)

    results = {
        'predictions_found': 0,
        'outcomes_recorded': 0,
        'errors': 0,
        'symbols_processed': set(),
        'direction_correct': 0,
        'magnitude_correct': 0,
        'details': []
    }

    # Get untracked predictions
    predictions = get_untracked_predictions(min_age_hours, max_age_days)
    results['predictions_found'] = len(predictions)

    if not predictions:
        logger.info("No untracked predictions found")
        return results

    logger.info(f"Found {len(predictions)} predictions to evaluate")

    for pred in predictions:
        symbol = pred['symbol']
        prediction_id = pred['prediction_id']
        pred_time = pred['timestamp']
        predicted_direction = pred['direction_pred'] or 'neutral'
        predicted_magnitude = pred['magnitude_pred'] or 'small'

        try:
            # Extract price at prediction time from features
            features = pred.get('features') or {}
            price_at_prediction = features.get('spot_price', 0)

            if price_at_prediction <= 0:
                # Try to estimate from symbol (would need historical lookup)
                logger.warning(f"No price at prediction for {prediction_id}")
                results['errors'] += 1
                continue

            # Get current/recent price
            price_now = get_price_at_time(symbol, datetime.now(CENTRAL_TZ))

            if price_now is None or price_now <= 0:
                logger.warning(f"Could not get current price for {symbol}")
                results['errors'] += 1
                continue

            # Calculate actual direction and magnitude
            actual_direction = calculate_direction(price_at_prediction, price_now)
            actual_magnitude = calculate_magnitude(price_at_prediction, price_now)
            actual_return_pct = ((price_now - price_at_prediction) / price_at_prediction) * 100

            # Record the outcome
            success = record_outcome(
                prediction_id=prediction_id,
                symbol=symbol,
                predicted_direction=predicted_direction,
                actual_direction=actual_direction,
                predicted_magnitude=predicted_magnitude,
                actual_magnitude=actual_magnitude,
                actual_return_pct=actual_return_pct
            )

            if success:
                results['outcomes_recorded'] += 1
                results['symbols_processed'].add(symbol)

                direction_correct = predicted_direction.lower() == actual_direction.lower()
                magnitude_correct = predicted_magnitude.lower() == actual_magnitude.lower()

                if direction_correct:
                    results['direction_correct'] += 1
                if magnitude_correct:
                    results['magnitude_correct'] += 1

                results['details'].append({
                    'prediction_id': prediction_id,
                    'symbol': symbol,
                    'predicted_direction': predicted_direction,
                    'actual_direction': actual_direction,
                    'direction_correct': direction_correct,
                    'predicted_magnitude': predicted_magnitude,
                    'actual_magnitude': actual_magnitude,
                    'magnitude_correct': magnitude_correct,
                    'return_pct': round(actual_return_pct, 2)
                })

        except Exception as e:
            logger.error(f"Error processing prediction {prediction_id}: {e}")
            results['errors'] += 1

    # Convert set to list for JSON serialization
    results['symbols_processed'] = list(results['symbols_processed'])

    # Calculate accuracy rates
    if results['outcomes_recorded'] > 0:
        results['direction_accuracy'] = round(
            (results['direction_correct'] / results['outcomes_recorded']) * 100, 1
        )
        results['magnitude_accuracy'] = round(
            (results['magnitude_correct'] / results['outcomes_recorded']) * 100, 1
        )
    else:
        results['direction_accuracy'] = 0
        results['magnitude_accuracy'] = 0

    logger.info("=" * 60)
    logger.info(f"APOLLO OUTCOME TRACKER - Complete")
    logger.info(f"  Predictions found: {results['predictions_found']}")
    logger.info(f"  Outcomes recorded: {results['outcomes_recorded']}")
    logger.info(f"  Direction accuracy: {results['direction_accuracy']}%")
    logger.info(f"  Magnitude accuracy: {results['magnitude_accuracy']}%")
    logger.info(f"  Errors: {results['errors']}")
    logger.info("=" * 60)

    return results


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    print("=" * 60)
    print("APOLLO OUTCOME TRACKER - Manual Run")
    print("=" * 60)

    results = track_apollo_outcomes()

    print(f"\nResults:")
    print(f"  Predictions found: {results['predictions_found']}")
    print(f"  Outcomes recorded: {results['outcomes_recorded']}")
    print(f"  Direction accuracy: {results.get('direction_accuracy', 0)}%")
    print(f"  Magnitude accuracy: {results.get('magnitude_accuracy', 0)}%")
    print(f"  Errors: {results['errors']}")

    print("\n" + "=" * 60)
    print("Complete")
    print("=" * 60)
