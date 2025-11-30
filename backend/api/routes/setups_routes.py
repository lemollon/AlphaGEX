"""
Trade Setups API routes - Generate and manage trade setups.
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

router = APIRouter(prefix="/api/setups", tags=["Trade Setups"])


@router.post("/generate")
async def generate_trade_setups(request: dict):
    """
    Generate AI-powered trade setups based on current market conditions
    """
    try:
        symbols = request.get('symbols', ['SPY'])
        account_size = request.get('account_size', 50000)
        risk_pct = request.get('risk_pct', 2.0)
        max_risk = account_size * (risk_pct / 100)

        from core.intelligence_and_strategies import RealOptionsChainFetcher
        from db.config_and_database import STRATEGIES

        options_fetcher = RealOptionsChainFetcher()
        setups = []

        for symbol in symbols:
            gex_data = api_client.get_net_gamma(symbol)
            net_gex = gex_data.get('net_gex', 0)
            spot_price = gex_data.get('spot_price', 0)
            flip_point = gex_data.get('flip_point', 0)
            call_wall = gex_data.get('call_wall', 0)
            put_wall = gex_data.get('put_wall', 0)

            matched_strategy = None
            strategy_config = None

            neg_gex_threshold = STRATEGIES.get('NEGATIVE_GEX_SQUEEZE', {}).get('conditions', {}).get('net_gex_threshold', -500)
            if net_gex < neg_gex_threshold:
                if spot_price < flip_point:
                    matched_strategy = 'NEGATIVE_GEX_SQUEEZE'
                    strategy_config = STRATEGIES.get('NEGATIVE_GEX_SQUEEZE', {})
                    entry_price = spot_price
                    target_price = call_wall if call_wall else spot_price * 1.03
                    stop_price = put_wall if put_wall else spot_price * 0.98
                    catalyst = f"Negative GEX regime creates MM buy pressure"

            if matched_strategy is None and net_gex > STRATEGIES.get('IRON_CONDOR', {}).get('conditions', {}).get('net_gex_threshold', 0):
                matched_strategy = 'IRON_CONDOR'
                strategy_config = STRATEGIES.get('IRON_CONDOR', {})
                entry_price = spot_price
                target_price = spot_price * 1.01
                stop_price = call_wall if call_wall else spot_price * 1.03
                catalyst = "Positive GEX creates range-bound environment"

            if matched_strategy is None:
                matched_strategy = 'PREMIUM_SELLING'
                strategy_config = STRATEGIES.get('PREMIUM_SELLING', {'win_rate': 60, 'risk_reward': 1.5})
                entry_price = spot_price
                target_price = spot_price * 1.01
                stop_price = flip_point if flip_point else spot_price * 0.98
                catalyst = "Neutral GEX allows for premium collection"

            confidence = strategy_config.get('win_rate', 60)
            risk_reward = strategy_config.get('risk_reward', 1.5)

            setups.append({
                'symbol': symbol,
                'setup_type': matched_strategy,
                'confidence': confidence,
                'entry_price': round(entry_price, 2) if entry_price else None,
                'target_price': round(target_price, 2) if target_price else None,
                'stop_price': round(stop_price, 2) if stop_price else None,
                'risk_reward': round(risk_reward, 2),
                'max_risk_dollars': round(max_risk, 2),
                'catalyst': catalyst,
                'data_date': gex_data.get('collection_date') or get_last_trading_day(),
                'timestamp': datetime.now().isoformat()
            })

        return {
            "success": True,
            "setups": setups,
            "data_date": get_last_trading_day(),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def save_trade_setup(request: dict):
    """Save a trade setup to database for tracking"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            INSERT INTO trade_setups (
                symbol, setup_type, confidence, entry_price, target_price,
                stop_price, risk_reward, position_size, max_risk_dollars,
                time_horizon, catalyst, money_making_plan
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            request['symbol'],
            request['setup_type'],
            request['confidence'],
            request['entry_price'],
            request['target_price'],
            request['stop_price'],
            request['risk_reward'],
            request.get('position_size', 1),
            request['max_risk_dollars'],
            request.get('time_horizon', '1 day'),
            request['catalyst'],
            request.get('money_making_plan', '')
        ))

        setup_id = c.fetchone()[0]
        conn.commit()
        conn.close()

        return {"success": True, "setup_id": setup_id, "message": "Trade setup saved"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_trade_setups(limit: int = 20, status: str = 'active'):
    """Get saved trade setups"""
    try:
        import pandas as pd

        conn = get_connection()
        setups = pd.read_sql_query("""
            SELECT * FROM trade_setups
            WHERE status = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, conn, params=(status, limit))
        conn.close()

        return {"success": True, "data": setups.to_dict('records') if not setups.empty else []}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{setup_id}")
async def update_trade_setup(setup_id: int, request: dict):
    """Update a trade setup"""
    try:
        conn = get_connection()
        c = conn.cursor()

        update_fields = []
        values = []

        for field in ['status', 'actual_entry', 'actual_exit', 'actual_pnl', 'notes']:
            if field in request:
                update_fields.append(f'{field} = %s')
                values.append(request[field])

        if not update_fields:
            return {"success": False, "message": "No fields to update"}

        values.append(setup_id)
        c.execute(f"UPDATE trade_setups SET {', '.join(update_fields)} WHERE id = %s", values)
        conn.commit()
        conn.close()

        return {"success": True, "message": "Setup updated"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
