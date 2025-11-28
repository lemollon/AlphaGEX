"""
Scanner API routes - Multi-symbol market scanning.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import api_client, get_connection

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
                INSERT INTO scanner_history (symbols, results)
                VALUES (%s, %s)
                RETURNING id
            """, (json.dumps(symbols), json.dumps(results)))
            scan_id = c.fetchone()[0]
            conn.commit()
            conn.close()
        except:
            scan_id = None

        return {"success": True, "scan_id": scan_id, "results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_scanner_history(limit: int = 20):
    """Get recent scan history"""
    try:
        import pandas as pd

        conn = get_connection()
        history = pd.read_sql_query(f"""
            SELECT * FROM scanner_history
            ORDER BY timestamp DESC
            LIMIT {int(limit)}
        """, conn)
        conn.close()

        return {"success": True, "data": history.to_dict('records') if not history.empty else []}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{scan_id}")
async def get_scan_results(scan_id: int):
    """Get results of a specific scan"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("SELECT * FROM scanner_history WHERE id = %s", (scan_id,))
        row = c.fetchone()
        conn.close()

        if row:
            return {"success": True, "scan": dict(zip(['id', 'symbols', 'results', 'timestamp'], row))}
        else:
            return {"success": False, "error": "Scan not found"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
