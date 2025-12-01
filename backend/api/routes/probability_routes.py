"""
Probability Prediction API routes - Self-learning probability calibration.
"""

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
                'timestamp': row[0],
                'prediction_type': row[1],
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

        c.execute('''
            SELECT
                weight_name,
                weight_value,
                description,
                last_updated,
                calibration_count
            FROM probability_weights
            ORDER BY weight_name
        ''')

        weights = []
        for row in c.fetchall():
            weights.append({
                'weight_name': row[0],
                'weight_value': row[1],
                'description': row[2],
                'last_updated': row[3],
                'calibration_count': row[4]
            })

        conn.close()

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

        c.execute('''
            SELECT
                calibration_date,
                weight_name,
                old_value,
                new_value,
                reason,
                performance_delta
            FROM calibration_history
            WHERE calibration_date >= NOW() - INTERVAL '1 day' * %s
            ORDER BY calibration_date DESC
        ''', (days,))

        history = []
        for row in c.fetchall():
            history.append({
                'calibration_date': row[0],
                'weight_name': row[1],
                'old_value': row[2],
                'new_value': row[3],
                'reason': row[4],
                'performance_delta': row[5]
            })

        conn.close()

        return {
            "success": True,
            "history": history
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
