"""
Miscellaneous API routes - recommendations and other small endpoints.
"""

from fastapi import APIRouter

from database_adapter import get_connection

router = APIRouter(tags=["Miscellaneous"])


# ============================================================================
# Recommendations History APIs
# ============================================================================

@router.get("/api/recommendations/history")
async def get_recommendations_history(days: int = 30):
    """Get past trade recommendations"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                id,
                timestamp,
                symbol,
                strategy,
                confidence,
                reasoning,
                option_strike,
                option_type,
                dte,
                entry_price,
                target_price,
                stop_price,
                outcome,
                pnl
            FROM recommendations
            WHERE timestamp >= NOW() - INTERVAL '1 day' * %s
            ORDER BY timestamp DESC
        ''', (days,))

        recommendations = []
        for row in c.fetchall():
            # Map to frontend-expected field names
            direction = 'BULLISH' if row[7] == 'CALL' else 'BEARISH' if row[7] == 'PUT' else 'NEUTRAL'
            recommendations.append({
                'id': row[0],
                'recommendation_date': row[1],  # Frontend expects recommendation_date
                'symbol': row[2],
                'strategy_type': row[3],  # Frontend expects strategy_type
                'confidence_pct': row[4],  # Frontend expects confidence_pct
                'reasoning': row[5],
                'entry_strike': row[6],  # Frontend expects entry_strike
                'exit_strike': row[11] or row[10],  # stop_price or target_price as exit
                'direction': direction,  # Frontend expects direction
                'recommended_entry_price': row[9] or 0,  # Frontend expects recommended_entry_price
                'actual_entry_price': row[9],  # Use entry_price as actual
                'actual_exit_price': None,  # Not tracked in current schema
                'outcome': row[12],
                'pnl': row[13],
                'outcome_date': None  # Not tracked in current schema
            })

        conn.close()

        return {
            "success": True,
            "recommendations": recommendations
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/recommendations/performance")
async def get_recommendation_performance():
    """Analyze how well past recommendations performed"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get recommendations with outcomes
        c.execute('''
            SELECT
                confidence,
                outcome,
                CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END as won
            FROM recommendations
            WHERE outcome IS NOT NULL
        ''')

        results = c.fetchall()

        # Calculate stats by confidence level
        confidence_buckets = {
            'high': {'total': 0, 'wins': 0},
            'medium': {'total': 0, 'wins': 0},
            'low': {'total': 0, 'wins': 0}
        }

        total_wins = 0
        total_trades = 0

        for conf, outcome, won in results:
            total_trades += 1
            total_wins += won

            if conf >= 80:
                bucket = 'high'
            elif conf >= 60:
                bucket = 'medium'
            else:
                bucket = 'low'

            confidence_buckets[bucket]['total'] += 1
            confidence_buckets[bucket]['wins'] += won

        conn.close()

        # Calculate win rates - format as array for frontend
        performance_buckets = []
        bucket_ranges = {
            'high': '80-100%',
            'medium': '60-79%',
            'low': '0-59%'
        }

        for bucket in ['high', 'medium', 'low']:
            data = confidence_buckets[bucket]
            win_rate = round(data['wins'] / data['total'] * 100, 1) if data['total'] > 0 else 0
            losses = data['total'] - data['wins']

            performance_buckets.append({
                'confidence_range': bucket_ranges[bucket],
                'total_recommendations': data['total'],
                'executed_trades': data['total'],  # Assume all were executed
                'winning_trades': data['wins'],
                'losing_trades': losses,
                'win_rate_pct': win_rate,
                'avg_pnl': 0,  # Not tracked in current schema
                'total_pnl': 0  # Not tracked in current schema
            })

        overall_win_rate = round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0

        return {
            "success": True,
            "overall": {
                "total_trades": total_trades,
                "wins": total_wins,
                "win_rate": overall_win_rate
            },
            "performance_buckets": performance_buckets,  # Frontend expects this
            "by_confidence": {b['confidence_range']: b for b in performance_buckets}  # Keep for backwards compat
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
