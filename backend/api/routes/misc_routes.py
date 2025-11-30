"""
Miscellaneous API routes - OI trends, recommendations, and other small endpoints.
"""

from fastapi import APIRouter

from database_adapter import get_connection

router = APIRouter(tags=["Miscellaneous"])


# ============================================================================
# Open Interest Trends APIs
# ============================================================================

@router.get("/api/oi/trends")
async def get_oi_trends(symbol: str = "SPY", days: int = 30):
    """Get historical open interest trends"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                snapshot_date,
                strike,
                expiration,
                call_oi,
                put_oi,
                total_oi,
                call_volume,
                put_volume,
                put_call_ratio
            FROM historical_open_interest
            WHERE symbol = %s
            AND snapshot_date >= CURRENT_DATE - INTERVAL '1 day' * %s
            ORDER BY snapshot_date DESC, total_oi DESC
        ''', (symbol, days))

        trends = []
        for row in c.fetchall():
            trends.append({
                'snapshot_date': row[0],
                'strike': row[1],
                'expiration': row[2],
                'call_oi': row[3],
                'put_oi': row[4],
                'total_oi': row[5],
                'call_volume': row[6],
                'put_volume': row[7],
                'put_call_ratio': row[8]
            })

        conn.close()

        return {
            "success": True,
            "trends": trends,
            "symbol": symbol
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/oi/unusual-activity")
async def get_unusual_oi_activity(symbol: str = "SPY", days: int = 7):
    """Detect unusual open interest changes"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                h1.snapshot_date,
                h1.strike,
                h1.expiration,
                h1.total_oi,
                h2.total_oi as prev_oi,
                ((h1.total_oi - h2.total_oi) * 100.0 / h2.total_oi) as oi_change_pct
            FROM historical_open_interest h1
            LEFT JOIN historical_open_interest h2
                ON h1.strike = h2.strike
                AND h1.expiration = h2.expiration
                AND h2.snapshot_date = h1.snapshot_date - INTERVAL '1 day'
            WHERE h1.symbol = %s
            AND h1.snapshot_date >= CURRENT_DATE - INTERVAL '1 day' * %s
            AND h2.total_oi IS NOT NULL
            AND abs((h1.total_oi - h2.total_oi) * 100.0 / h2.total_oi) > 20
            ORDER BY abs((h1.total_oi - h2.total_oi) * 100.0 / h2.total_oi) DESC
            LIMIT 50
        ''', (symbol, days))

        unusual = []
        for row in c.fetchall():
            unusual.append({
                'date': row[0],
                'strike': row[1],
                'expiration': row[2],
                'current_oi': row[3],
                'previous_oi': row[4],
                'change_pct': row[5]
            })

        conn.close()

        return {
            "success": True,
            "unusual_activity": unusual
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


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
                direction,
                confidence,
                reasoning,
                strike,
                expiration,
                entry_price,
                target_price,
                stop_loss,
                status,
                actual_outcome
            FROM recommendations
            WHERE timestamp >= NOW() - INTERVAL '1 day' * %s
            ORDER BY timestamp DESC
        ''', (days,))

        recommendations = []
        for row in c.fetchall():
            recommendations.append({
                'id': row[0],
                'timestamp': row[1],
                'symbol': row[2],
                'strategy': row[3],
                'direction': row[4],
                'confidence': row[5],
                'reasoning': row[6],
                'strike': row[7],
                'expiration': row[8],
                'entry_price': row[9],
                'target_price': row[10],
                'stop_loss': row[11],
                'status': row[12],
                'actual_outcome': row[13]
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
                actual_outcome,
                CASE WHEN actual_outcome = 'WIN' THEN 1 ELSE 0 END as won
            FROM recommendations
            WHERE status = 'CLOSED'
            AND actual_outcome IS NOT NULL
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

        # Calculate win rates
        performance = {}
        for bucket, data in confidence_buckets.items():
            if data['total'] > 0:
                performance[bucket] = {
                    'total_trades': data['total'],
                    'wins': data['wins'],
                    'win_rate': round(data['wins'] / data['total'] * 100, 1)
                }
            else:
                performance[bucket] = {
                    'total_trades': 0,
                    'wins': 0,
                    'win_rate': 0
                }

        overall_win_rate = round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0

        return {
            "success": True,
            "overall": {
                "total_trades": total_trades,
                "wins": total_wins,
                "win_rate": overall_win_rate
            },
            "by_confidence": performance
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
