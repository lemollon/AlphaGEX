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
                date,
                strike,
                expiration_date,
                call_oi,
                put_oi,
                COALESCE(call_oi, 0) + COALESCE(put_oi, 0) as total_oi,
                call_volume,
                put_volume,
                CASE WHEN call_oi > 0 THEN ROUND(put_oi::numeric / call_oi::numeric, 2) ELSE 0 END as put_call_ratio
            FROM historical_open_interest
            WHERE symbol = %s
            AND date >= CURRENT_DATE - INTERVAL '1 day' * %s
            ORDER BY date DESC, (COALESCE(call_oi, 0) + COALESCE(put_oi, 0)) DESC
        ''', (symbol, days))

        trends = []
        for row in c.fetchall():
            trends.append({
                'date': row[0],
                'strike': row[1],
                'expiration_date': row[2],
                'call_oi': row[3],
                'put_oi': row[4],
                'total_oi': row[5],
                'call_volume': row[6],
                'put_volume': row[7],
                'put_call_ratio': float(row[8]) if row[8] else 0
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
                h1.date,
                h1.strike,
                h1.expiration_date,
                (COALESCE(h1.call_oi, 0) + COALESCE(h1.put_oi, 0)) as total_oi,
                (COALESCE(h2.call_oi, 0) + COALESCE(h2.put_oi, 0)) as prev_oi,
                ROUND((((COALESCE(h1.call_oi, 0) + COALESCE(h1.put_oi, 0)) - (COALESCE(h2.call_oi, 0) + COALESCE(h2.put_oi, 0))) * 100.0 / NULLIF(COALESCE(h2.call_oi, 0) + COALESCE(h2.put_oi, 0), 0))::numeric, 2) as oi_change_pct
            FROM historical_open_interest h1
            LEFT JOIN historical_open_interest h2
                ON h1.strike = h2.strike
                AND h1.expiration_date = h2.expiration_date
                AND h1.symbol = h2.symbol
                AND h2.date = h1.date - INTERVAL '1 day'
            WHERE h1.symbol = %s
            AND h1.date >= CURRENT_DATE - INTERVAL '1 day' * %s
            AND (COALESCE(h2.call_oi, 0) + COALESCE(h2.put_oi, 0)) > 0
            AND abs(((COALESCE(h1.call_oi, 0) + COALESCE(h1.put_oi, 0)) - (COALESCE(h2.call_oi, 0) + COALESCE(h2.put_oi, 0))) * 100.0 / (COALESCE(h2.call_oi, 0) + COALESCE(h2.put_oi, 0))) > 20
            ORDER BY abs(((COALESCE(h1.call_oi, 0) + COALESCE(h1.put_oi, 0)) - (COALESCE(h2.call_oi, 0) + COALESCE(h2.put_oi, 0))) * 100.0 / (COALESCE(h2.call_oi, 0) + COALESCE(h2.put_oi, 0))) DESC
            LIMIT 50
        ''', (symbol, days))

        unusual = []
        for row in c.fetchall():
            unusual.append({
                'date': row[0],
                'strike': row[1],
                'expiration_date': row[2],
                'current_oi': row[3],
                'previous_oi': row[4],
                'change_pct': float(row[5]) if row[5] else 0
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
            recommendations.append({
                'id': row[0],
                'timestamp': row[1],
                'symbol': row[2],
                'strategy': row[3],
                'confidence': row[4],
                'reasoning': row[5],
                'option_strike': row[6],
                'option_type': row[7],
                'dte': row[8],
                'entry_price': row[9],
                'target_price': row[10],
                'stop_price': row[11],
                'outcome': row[12],
                'pnl': row[13]
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
