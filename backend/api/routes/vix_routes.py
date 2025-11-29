"""
VIX Hedge Manager API routes.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/vix", tags=["VIX"])


@router.get("/hedge-signal")
async def get_vix_hedge_signal(portfolio_delta: float = 0, portfolio_value: float = 100000):
    """
    Generate a VIX-based hedge signal for portfolio protection.
    This is a SIGNAL GENERATOR only - does not auto-execute trades.
    """
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager

        manager = get_vix_hedge_manager()
        signal = manager.generate_hedge_signal(
            portfolio_delta=portfolio_delta,
            portfolio_value=portfolio_value
        )

        return {
            "success": True,
            "data": {
                "timestamp": signal.timestamp.isoformat(),
                "signal_type": signal.signal_type.value,
                "confidence": signal.confidence,
                "vol_regime": signal.vol_regime.value,
                "reasoning": signal.reasoning,
                "recommended_action": signal.recommended_action,
                "risk_warning": signal.risk_warning,
                "metrics": signal.metrics
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signal-history")
async def get_vix_signal_history(days: int = 30):
    """Get historical VIX hedge signals"""
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager

        manager = get_vix_hedge_manager()
        history = manager.get_signal_history(days)

        if history.empty:
            return {"success": True, "data": []}

        formatted_data = []
        for _, row in history.iterrows():
            try:
                date_str = str(row.get('signal_date', ''))
                time_str = str(row.get('signal_time', '00:00:00'))
                timestamp = f"{date_str}T{time_str}"
            except Exception:
                timestamp = None

            formatted_data.append({
                "timestamp": timestamp,
                "signal_type": row.get('signal_type', 'no_action'),
                "vix_level": float(row.get('vix_spot', 0)) if row.get('vix_spot') else None,
                "confidence": float(row.get('confidence', 0)) if row.get('confidence') else None,
                "action_taken": row.get('recommended_action', 'Monitored')
            })

        return {
            "success": True,
            "data": formatted_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current")
async def get_vix_current():
    """Get current VIX data and analysis with VVIX and stress indicators"""
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager

        manager = get_vix_hedge_manager()
        vix_data = manager.get_vix_data()
        vix_spot = vix_data.get('vix_spot', 18.0)

        iv_percentile = manager.calculate_iv_percentile(vix_spot)
        realized_vol = manager.calculate_realized_vol('SPY')
        vol_regime = manager.get_vol_regime(vix_spot)

        return {
            "success": True,
            "data": {
                "vix_spot": vix_spot,
                "vix_source": vix_data.get('vix_source', 'unknown'),
                "vix_m1": vix_data.get('vix_m1', 0),
                "vix_m2": vix_data.get('vix_m2', 0),
                "is_estimated": vix_data.get('is_estimated', True),
                "term_structure_pct": vix_data.get('term_structure_m1_pct', 0),
                "term_structure_m2_pct": vix_data.get('term_structure_m2_pct', 0),
                "structure_type": vix_data.get('structure_type', 'unknown'),
                "vvix": vix_data.get('vvix'),
                "vvix_source": vix_data.get('vvix_source', 'none'),
                "iv_percentile": iv_percentile,
                "realized_vol_20d": realized_vol,
                "iv_rv_spread": vix_spot - realized_vol,
                "vol_regime": vol_regime.value,
                "vix_stress_level": vix_data.get('vix_stress_level', 'unknown'),
                "position_size_multiplier": vix_data.get('position_size_multiplier', 1.0),
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug")
async def get_vix_debug():
    """VIX debugging endpoint - shows all VIX-related data and sources."""
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager

        manager = get_vix_hedge_manager()
        vix_data = manager.get_vix_data()
        vix_spot = vix_data.get('vix_spot', 18.0)

        iv_percentile = manager.calculate_iv_percentile(vix_spot)
        realized_vol = manager.calculate_realized_vol('SPY')
        vol_regime = manager.get_vol_regime(vix_spot)

        raw_sources = {}

        try:
            from data.unified_data_provider import get_vix as unified_get_vix
            raw_sources['unified_provider'] = unified_get_vix()
        except Exception as e:
            raw_sources['unified_provider'] = f"Error: {e}"

        try:
            from data.polygon_data_fetcher import polygon_fetcher
            raw_sources['polygon'] = polygon_fetcher.get_current_price('^VIX')
        except Exception as e:
            raw_sources['polygon'] = f"Error: {e}"

        return {
            "success": True,
            "data": {
                "vix_data": vix_data,
                "raw_sources": raw_sources,
                "calculated_metrics": {
                    "iv_percentile": iv_percentile,
                    "realized_vol_20d": realized_vol,
                    "iv_rv_spread": vix_spot - realized_vol,
                    "vol_regime": vol_regime.value
                },
                "trading_impact": {
                    "stress_level": vix_data.get('vix_stress_level', 'unknown'),
                    "position_size_multiplier": vix_data.get('position_size_multiplier', 1.0),
                    "should_reduce_risk": vix_data.get('vix_stress_level') in ['high', 'extreme'],
                    "vvix_available": vix_data.get('vvix') is not None
                },
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
