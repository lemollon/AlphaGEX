"""
Probability Prediction API routes - Self-learning probability calibration.
"""

import json

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import probability_calc, get_connection

router = APIRouter(prefix="/api/probability", tags=["Probability"])


@router.post("/record-outcome")
async def record_probability_outcome(request: dict):
    """
    Record actual outcome for a prediction (for calibration/learning)

    Request body:
        {
            "prediction_id": 123,
            "actual_close_price": 570.50
        }
    """
    try:
        prediction_id = request.get('prediction_id')
        actual_close_price = request.get('actual_close_price')

        if not prediction_id or actual_close_price is None:
            raise HTTPException(
                status_code=400,
                detail="prediction_id and actual_close_price required"
            )

        probability_calc.record_outcome(prediction_id, actual_close_price)

        return {
            "success": True,
            "message": f"Outcome recorded for prediction {prediction_id}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accuracy")
async def get_probability_accuracy(days: int = 30):
    """
    Get accuracy metrics for probability predictions
    """
    try:
        metrics = probability_calc.get_accuracy_metrics(days=days)

        return {
            "success": True,
            "metrics": metrics
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calibrate")
async def calibrate_probability_model(min_predictions: int = 50):
    """
    Calibrate probability model based on actual outcomes (Phase 2 Self-Learning)
    """
    try:
        result = probability_calc.calibrate(min_predictions=min_predictions)

        return {
            "success": True,
            "calibration": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/outcomes")
async def get_probability_outcomes(days: int = 30):
    """
    Get prediction accuracy outcomes over time
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                timestamp,
                prediction_type,
                predicted_probability,
                actual_outcome,
                correct_prediction,
                outcome_timestamp
            FROM probability_outcomes
            WHERE timestamp >= NOW() - INTERVAL '1 day' * %s
            ORDER BY timestamp DESC
        ''', (days,))

        outcomes = []
        for row in c.fetchall():
            outcomes.append({
                'prediction_date': row[0],  # Frontend expects prediction_date
                'pattern_type': row[1],  # Frontend expects pattern_type
                'predicted_probability': row[2],
                'actual_outcome': row[3],
                'correct_prediction': bool(row[4]) if row[4] is not None else None,
                'outcome_timestamp': row[5]
            })

        # Calculate accuracy stats
        total = len(outcomes)
        correct = sum(1 for o in outcomes if o['correct_prediction'])
        accuracy = (correct / total * 100) if total > 0 else 0

        conn.close()

        return {
            "success": True,
            "outcomes": outcomes,
            "stats": {
                "total_predictions": total,
                "correct": correct,
                "accuracy_pct": accuracy
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/weights")
async def get_probability_weights():
    """Get current probability weighting configuration"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get the active weights row (column-based storage)
        c.execute('''
            SELECT
                gex_wall_strength,
                volatility_impact,
                psychology_signal,
                mm_positioning,
                historical_pattern,
                timestamp,
                calibration_count
            FROM probability_weights
            WHERE active = TRUE
            ORDER BY timestamp DESC
            LIMIT 1
        ''')

        row = c.fetchone()
        conn.close()

        # Transform column-based weights into row-based format for frontend
        weight_descriptions = {
            'gex_wall_strength': 'How much GEX walls influence probability',
            'volatility_impact': 'How much VIX/IV affects price ranges',
            'psychology_signal': 'How much FOMO/Fear affects prediction',
            'mm_positioning': 'How much Market Maker state matters',
            'historical_pattern': 'How much historical data confirms patterns'
        }

        weights = []
        if row:
            weight_names = ['gex_wall_strength', 'volatility_impact', 'psychology_signal',
                          'mm_positioning', 'historical_pattern']
            for i, name in enumerate(weight_names):
                weights.append({
                    'weight_name': name.replace('_', ' ').title(),
                    'weight_value': row[i] if row[i] is not None else 0.0,
                    'description': weight_descriptions.get(name, ''),
                    'last_updated': row[5],  # timestamp
                    'calibration_count': row[6] if row[6] is not None else 0
                })
        else:
            # Return defaults if no weights in DB
            defaults = [0.35, 0.25, 0.20, 0.15, 0.05]
            weight_names = ['gex_wall_strength', 'volatility_impact', 'psychology_signal',
                          'mm_positioning', 'historical_pattern']
            for i, name in enumerate(weight_names):
                weights.append({
                    'weight_name': name.replace('_', ' ').title(),
                    'weight_value': defaults[i],
                    'description': weight_descriptions.get(name, ''),
                    'last_updated': None,
                    'calibration_count': 0
                })

        return {
            "success": True,
            "weights": weights
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/calibration-history")
async def get_calibration_history(days: int = 90):
    """Get model calibration adjustment history"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get calibration events with adjustments JSON
        c.execute('''
            SELECT
                calibration_date,
                timestamp,
                predictions_analyzed,
                overall_accuracy,
                high_conf_accuracy,
                adjustments_made
            FROM calibration_history
            WHERE timestamp >= NOW() - INTERVAL '1 day' * %s
            ORDER BY timestamp DESC
        ''', (days,))

        rows = c.fetchall()
        conn.close()

        # Transform calibration records into weight-level changes for frontend
        history = []
        for row in rows:
            calibration_date = row[0] or row[1]  # Use calibration_date or timestamp
            overall_accuracy = row[3]
            adjustments = row[5]

            # Parse adjustments JSON and create a row per weight changed
            if adjustments:
                try:
                    adj_dict = adjustments if isinstance(adjustments, dict) else json.loads(adjustments)
                    for weight_name, new_value in adj_dict.items():
                        history.append({
                            'calibration_date': calibration_date,
                            'weight_name': weight_name.replace('_', ' ').title(),
                            'old_value': 0.0,  # We don't track old values currently
                            'new_value': new_value,
                            'reason': f'Accuracy: {overall_accuracy*100:.1f}%' if overall_accuracy else 'Calibration adjustment',
                            'performance_delta': 0.0  # Would need before/after comparison
                        })
                except (json.JSONDecodeError, TypeError):
                    # If JSON parsing fails, add a summary row
                    history.append({
                        'calibration_date': calibration_date,
                        'weight_name': 'Multiple Weights',
                        'old_value': 0.0,
                        'new_value': 0.0,
                        'reason': f'Analyzed {row[2]} predictions' if row[2] else 'Calibration event',
                        'performance_delta': 0.0
                    })

        return {
            "success": True,
            "calibration_history": history  # Frontend expects calibration_history
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
