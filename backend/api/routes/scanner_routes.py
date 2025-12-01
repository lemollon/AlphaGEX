"""
Scanner API routes - Multi-symbol market scanning.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import api_client, get_connection


def get_last_trading_day():
    """Get the last trading day date"""
    now = datetime.now()
    if now.weekday() == 5:  # Saturday
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    elif now.weekday() == 6:  # Sunday
        return (now - timedelta(days=2)).strftime('%Y-%m-%d')
    elif now.hour < 9 or (now.hour == 9 and now.minute < 30):
        # Before market open
        if now.weekday() == 0:  # Monday
            return (now - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')

router = APIRouter(prefix="/api/scanner", tags=["Scanner"])


@router.post("/scan")
async def scan_market(request: dict):
    """
    Scan multiple symbols for trading opportunities
    """
    try:
        symbols = request.get('symbols', ['SPY', 'QQQ', 'IWM'])
        results = []

        for symbol in symbols:
            try:
                gex_data = api_client.get_net_gamma(symbol)
                net_gex = gex_data.get('net_gex', 0)
                spot_price = gex_data.get('spot_price', 0)
                flip_point = gex_data.get('flip_point', 0)

                signal = 'NEUTRAL'
                if net_gex < -1e9 and spot_price < flip_point:
                    signal = 'BULLISH'
                elif net_gex > 1e9 and spot_price > flip_point:
                    signal = 'BEARISH'

                results.append({
                    'symbol': symbol,
                    'spot_price': spot_price,
                    'net_gex': net_gex,
                    'flip_point': flip_point,
                    'signal': signal,
                    'data_date': gex_data.get('collection_date') or get_last_trading_day(),
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                results.append({'symbol': symbol, 'error': str(e)})

        # Save scan to database
        try:
            conn = get_connection()
            c = conn.cursor()
            import json
            c.execute("""
                INSERT INTO scanner_history (symbols_scanned, results, scan_type)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (json.dumps(symbols), json.dumps(results), 'multi_symbol'))
            scan_id = c.fetchone()[0]
            conn.commit()
            conn.close()
        except Exception:
            scan_id = None  # Database operation failed, continue without scan_id

        return {
            "success": True,
            "scan_id": scan_id,
            "results": results,
            "data_date": get_last_trading_day(),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_scanner_history(limit: int = 20):
    """Get recent scan history"""
    try:
        import pandas as pd
        import json as json_module

        conn = get_connection()
        history = pd.read_sql_query("""
            SELECT id, timestamp, symbols_scanned, results, scan_type, duration_ms
            FROM scanner_history
            ORDER BY timestamp DESC
            LIMIT %s
        """, conn, params=(int(limit),))
        conn.close()

        # Transform to match frontend expectations
        formatted_history = []
        for _, row in history.iterrows():
            # Parse symbols and results for computed fields
            symbols = row['symbols_scanned']
            results = row['results']

            # Handle JSON parsing
            if isinstance(symbols, str):
                try:
                    symbols_list = json_module.loads(symbols)
                except (json_module.JSONDecodeError, TypeError):
                    symbols_list = [symbols] if symbols else []
            else:
                symbols_list = symbols if symbols else []

            if isinstance(results, str):
                try:
                    results_list = json_module.loads(results)
                except (json_module.JSONDecodeError, TypeError):
                    results_list = []
            else:
                results_list = results if results else []

            # Count opportunities (results without errors)
            opportunities = len([r for r in results_list if isinstance(r, dict) and 'error' not in r])

            formatted_history.append({
                'id': str(row['id']),
                'timestamp': str(row['timestamp']) if row['timestamp'] else None,
                'symbols_scanned': ', '.join(symbols_list) if isinstance(symbols_list, list) else str(symbols_list),
                'total_symbols': len(symbols_list) if isinstance(symbols_list, list) else 1,
                'opportunities_found': opportunities,
                'scan_duration_seconds': (row['duration_ms'] / 1000) if row['duration_ms'] else 0
            })

        return {"success": True, "data": formatted_history}

    except Exception as e:
        # Return empty data on error (table may not exist)
        return {"success": True, "data": [], "message": "Scanner history not available"}


@router.get("/results/{scan_id}")
async def get_scan_results(scan_id: int):
    """Get results of a specific scan"""
    try:
        import json as json_module

        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT id, timestamp, symbols_scanned, results, scan_type
            FROM scanner_history WHERE id = %s
        """, (scan_id,))
        row = c.fetchone()
        conn.close()

        if row:
            # Parse results JSON to return as list for frontend
            results = row[3]
            if isinstance(results, str):
                try:
                    results = json_module.loads(results)
                except (json_module.JSONDecodeError, TypeError):
                    results = []

            # Return data (the results list) for frontend compatibility
            return {"success": True, "data": results if isinstance(results, list) else []}
        else:
            return {"success": False, "error": "Scan not found", "data": []}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
