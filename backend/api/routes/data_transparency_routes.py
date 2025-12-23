"""
Data Transparency Routes

Exposes ALL collected data that is not displayed in the main UI.
This provides complete visibility into:
- Regime signals (80+ columns)
- VIX term structure (full data)
- AI/ML model internals
- Position sizing rationale
- Strike selection logic
- Psychology pattern analysis
- Volatility surface data
- Performance analytics
- Options flow data
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging

router = APIRouter(prefix="/api/data-transparency", tags=["Data Transparency"])
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection"""
    try:
        from db.config_and_database import get_db_connection as db_conn
        return db_conn()
    except Exception as e:
        logger.error(f"Failed to get DB connection: {e}")
        return None


@router.get("/summary")
async def get_transparency_summary():
    """Get summary of all hidden data available"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        categories = {
            "regime_signals": {
                "table": "regime_signals",
                "display_name": "Regime Signals (80+ columns)",
                "hidden_fields": [
                    "rsi_5m", "rsi_15m", "rsi_1h", "rsi_4h", "rsi_1d",
                    "rsi_aligned", "rsi_oversold", "rsi_overbought", "rsi_coiling",
                    "liberation_setup", "liberation_strike", "liberation_expiry",
                    "false_floor", "false_floor_strike", "false_floor_expiry",
                    "monthly_magnet_above", "monthly_magnet_below", "magnet_strength",
                    "path_of_least_resistance", "polr_confidence",
                    "psychology_trap", "trap_probability", "at_flip_point",
                    "gamma_persistence_ratio", "dealer_positioning"
                ]
            },
            "vix_term_structure": {
                "table": "vix_term_structure",
                "display_name": "VIX Term Structure (Full)",
                "hidden_fields": [
                    "vix_9d", "vix_3m", "vix_6m",
                    "vx_front", "vx_second", "vx_third",
                    "term_slope", "inversion_detected",
                    "vvix", "skew_index", "put_call_ratio",
                    "iv_percentile", "iv_rank", "realized_vol_20d"
                ]
            },
            "ai_analysis_history": {
                "table": "ai_analysis_history",
                "display_name": "AI Analysis History",
                "hidden_fields": [
                    "input_prompt", "output_response", "confidence_score",
                    "model_used", "tokens_used", "response_time_ms",
                    "recommendations", "warnings", "outcome_tracked",
                    "outcome_correct", "feedback_notes"
                ]
            },
            "position_sizing_history": {
                "table": "position_sizing_history",
                "display_name": "Position Sizing Rationale",
                "hidden_fields": [
                    "kelly_full", "kelly_half", "kelly_quarter",
                    "var_95", "expected_value", "risk_of_ruin",
                    "sizing_rationale", "win_rate_used", "avg_win", "avg_loss"
                ]
            },
            "autonomous_trader_logs": {
                "table": "autonomous_trader_logs",
                "display_name": "Trading Decision Details (62+ fields)",
                "hidden_fields": [
                    "rsi_5m_value", "rsi_15m_value", "rsi_1h_value", "rsi_4h_value", "rsi_1d_value",
                    "strike_selection_reasoning", "alternative_strikes",
                    "why_not_alternatives", "ai_thought_process", "ai_confidence",
                    "ai_warnings", "langchain_chain_used", "kelly_pct",
                    "sizing_rationale", "full_reasoning", "liberation_detected",
                    "false_floor_detected", "psychology_pattern"
                ]
            },
            "strike_performance": {
                "table": "strike_performance",
                "display_name": "Strike Performance Analytics",
                "hidden_fields": [
                    "strike_distance_pct", "moneyness", "delta_at_entry",
                    "gamma_at_entry", "theta_at_entry", "vega_at_entry",
                    "win_rate_at_strike", "avg_pnl_at_strike",
                    "max_profit_pct", "max_loss_pct"
                ]
            },
            "options_flow": {
                "table": "options_flow",
                "display_name": "Options Flow Analysis",
                "hidden_fields": [
                    "total_call_volume", "total_put_volume", "put_call_ratio",
                    "unusual_activity_detected", "oi_changes", "premium_flow",
                    "zero_dte_volume", "weekly_volume", "monthly_volume",
                    "largest_oi_strike", "net_call_premium", "net_put_premium"
                ]
            },
            "greeks_performance": {
                "table": "greeks_performance",
                "display_name": "Greeks Efficiency Analysis",
                "hidden_fields": [
                    "delta_pnl_ratio", "theta_pnl_ratio", "gamma_scalp_efficiency",
                    "vega_contribution", "entry_greeks_optimal"
                ]
            },
            "dte_performance": {
                "table": "dte_performance",
                "display_name": "DTE Performance Analysis",
                "hidden_fields": [
                    "dte_bucket", "avg_hold_time", "optimal_exit_dte",
                    "theta_decay_rate", "theta_pnl_contribution",
                    "days_before_expiration_closed"
                ]
            },
            "sucker_statistics": {
                "table": "sucker_statistics",
                "display_name": "Psychology Pattern Statistics",
                "hidden_fields": [
                    "scenario_type", "total_occurrences", "failure_rate",
                    "avg_price_change_when_failed"
                ]
            },
            "liberation_outcomes": {
                "table": "liberation_outcomes",
                "display_name": "Liberation Setup Outcomes",
                "hidden_fields": [
                    "signal_date", "strike", "expiry_ratio",
                    "price_at_signal", "price_at_liberation",
                    "price_1d_later", "price_5d_later",
                    "breakout_occurred", "max_move_pct"
                ]
            }
        }

        summary = {}
        for key, info in categories.items():
            try:
                cur.execute(f"SELECT COUNT(*) FROM {info['table']}")
                count = cur.fetchone()[0]

                cur.execute(f"""
                    SELECT MAX(created_at) FROM {info['table']}
                    WHERE created_at IS NOT NULL
                """)
                latest = cur.fetchone()[0]

                summary[key] = {
                    "display_name": info["display_name"],
                    "table": info["table"],
                    "total_records": count,
                    "latest_entry": latest.isoformat() if latest else None,
                    "hidden_fields": info["hidden_fields"],
                    "hidden_field_count": len(info["hidden_fields"])
                }
            except Exception as e:
                summary[key] = {
                    "display_name": info["display_name"],
                    "table": info["table"],
                    "error": str(e),
                    "total_records": 0
                }

        return {
            "success": True,
            "data": summary,
            "total_categories": len(summary),
            "generated_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting transparency summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/regime-signals")
async def get_regime_signals(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get full regime signals with all 80+ columns"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        # Get all columns
        cur.execute("""
            SELECT * FROM regime_signals
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        # Get total count
        cur.execute("SELECT COUNT(*) FROM regime_signals")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "column_count": len(columns),
                "total_records": total,
                "limit": limit,
                "offset": offset
            }
        }

    except Exception as e:
        logger.error(f"Error getting regime signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/vix-term-structure")
async def get_vix_term_structure(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get full VIX term structure data"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM vix_term_structure
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM vix_term_structure")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting VIX term structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/ai-analysis-history")
async def get_ai_analysis_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get full AI analysis history with prompts, responses, and outcomes"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM ai_analysis_history
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM ai_analysis_history")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting AI analysis history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/position-sizing")
async def get_position_sizing_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get position sizing history with Kelly calculations, VaR, and rationale"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM position_sizing_history
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM position_sizing_history")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting position sizing history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/trading-decisions-full")
async def get_full_trading_decisions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    bot: Optional[str] = None
):
    """Get full trading decision logs with all 62+ fields"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        query = "SELECT * FROM autonomous_trader_logs"
        params = []

        if bot:
            query += " WHERE bot_name = %s"
            params.append(bot)

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        count_query = "SELECT COUNT(*) FROM autonomous_trader_logs"
        if bot:
            count_query += f" WHERE bot_name = '{bot}'"
        cur.execute(count_query)
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "column_count": len(columns),
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting trading decisions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/options-flow")
async def get_options_flow(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get options flow data - volume, OI, unusual activity"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM options_flow
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM options_flow")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting options flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/strike-performance")
async def get_strike_performance(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get strike performance analytics"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM strike_performance
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM strike_performance")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting strike performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/greeks-performance")
async def get_greeks_performance(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get Greeks efficiency analytics"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM greeks_performance
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM greeks_performance")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting greeks performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/dte-performance")
async def get_dte_performance(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get DTE performance analytics"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM dte_performance
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM dte_performance")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting DTE performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/psychology-patterns")
async def get_psychology_patterns(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get psychology pattern analysis and sucker statistics"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        # Get psychology analysis
        cur.execute("""
            SELECT * FROM psychology_analysis
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        psychology_records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            psychology_records.append(record)

        # Get sucker statistics
        sucker_stats = []
        try:
            cur.execute("SELECT * FROM sucker_statistics ORDER BY created_at DESC LIMIT 50")
            sucker_columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = {}
                for i, col in enumerate(sucker_columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    record[col] = val
                sucker_stats.append(record)
        except:
            pass

        # Get liberation outcomes
        liberation_outcomes = []
        try:
            cur.execute("SELECT * FROM liberation_outcomes ORDER BY created_at DESC LIMIT 50")
            lib_columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = {}
                for i, col in enumerate(lib_columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    record[col] = val
                liberation_outcomes.append(record)
        except:
            pass

        return {
            "success": True,
            "data": {
                "psychology_analysis": psychology_records,
                "sucker_statistics": sucker_stats,
                "liberation_outcomes": liberation_outcomes
            }
        }

    except Exception as e:
        logger.error(f"Error getting psychology patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/volatility-surface-history")
async def get_volatility_surface_history():
    """Get volatility surface analysis history"""
    try:
        # Try to get current volatility surface analysis
        from data.unified_data_provider import get_data_provider
        from utils.volatility_surface import VolatilitySurface
        from core.volatility_surface_integration import VolatilitySurfaceAnalyzer

        provider = get_data_provider()
        quote = provider.get_quote("SPY")
        spot_price = quote.get('last', quote.get('mid', 450)) if quote else 450

        analyzer = VolatilitySurfaceAnalyzer(spot_price=spot_price)

        # Get options chain
        chain = provider.get_options_chain("SPY", greeks=True)

        surface_data = {
            "current_analysis": None,
            "skew_data": None,
            "term_structure": None
        }

        if chain and chain.chains:
            for exp_date, contracts in sorted(chain.chains.items())[:5]:
                from datetime import datetime as dt
                exp_dt = dt.strptime(exp_date, '%Y-%m-%d')
                dte_days = (exp_dt - dt.now()).days

                if dte_days < 1 or dte_days > 90:
                    continue

                chain_data = [{
                    'strike': c.strike,
                    'iv': c.implied_volatility,
                    'delta': c.delta,
                    'volume': c.volume or 0,
                    'open_interest': c.open_interest or 0
                } for c in contracts if c.implied_volatility and c.implied_volatility > 0]

                if chain_data:
                    analyzer.add_chain_data(chain_data, dte_days)

            analysis = analyzer.get_enhanced_analysis()

            if analysis:
                surface_data["current_analysis"] = {
                    "atm_iv": analysis.atm_iv,
                    "iv_rank": analysis.iv_rank,
                    "iv_percentile": analysis.iv_percentile,
                    "skew_25d": analysis.skew_25d,
                    "risk_reversal": analysis.risk_reversal,
                    "butterfly": analysis.butterfly,
                    "skew_regime": str(analysis.skew_regime),
                    "term_slope": analysis.term_slope,
                    "term_regime": str(analysis.term_structure_regime) if hasattr(analysis, 'term_structure_regime') else str(analysis.term_regime),
                    "front_month_iv": analysis.front_month_iv,
                    "back_month_iv": analysis.back_month_iv,
                    "recommended_dte": analysis.recommended_dte,
                    "directional_bias": analysis.get_directional_bias(),
                    "should_sell_premium": analysis.should_sell_premium()[0],
                    "sell_reasoning": analysis.should_sell_premium()[1],
                    "optimal_strategy": analysis.get_optimal_strategy()
                }

        return {
            "success": True,
            "data": surface_data,
            "spot_price": spot_price,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting volatility surface: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


@router.get("/market-snapshots-full")
async def get_full_market_snapshots(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get full market snapshots with all fields"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM market_snapshots
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM market_snapshots")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting market snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/greeks-snapshots-full")
async def get_full_greeks_snapshots(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Get full Greeks snapshots with IV rank, percentile, etc."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT * FROM greeks_snapshots
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM greeks_snapshots")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting Greeks snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/backtest-trades-full")
async def get_full_backtest_trades(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    run_id: Optional[str] = None
):
    """Get full backtest trade details with entry context and Greeks"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        query = "SELECT * FROM backtest_trades"
        params = []

        if run_id:
            query += " WHERE backtest_run_id = %s"
            params.append(run_id)

        query += " ORDER BY entry_date DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)

        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if isinstance(val, datetime):
                    val = val.isoformat()
                record[col] = val
            records.append(record)

        cur.execute("SELECT COUNT(*) FROM backtest_trades")
        total = cur.fetchone()[0]

        return {
            "success": True,
            "data": {
                "records": records,
                "columns": columns,
                "total_records": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting backtest trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/ml-model-details")
async def get_ml_model_details():
    """Get ML model internals - feature importance, accuracy, calibration"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        # Get ML models
        models = []
        try:
            cur.execute("""
                SELECT * FROM ml_models
                ORDER BY created_at DESC
                LIMIT 10
            """)
            columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    elif isinstance(val, bytes):
                        val = f"<binary: {len(val)} bytes>"
                    record[col] = val
                models.append(record)
        except:
            pass

        # Get ML predictions with outcomes
        predictions = []
        try:
            cur.execute("""
                SELECT * FROM ml_predictions
                ORDER BY created_at DESC
                LIMIT 100
            """)
            columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    record[col] = val
                predictions.append(record)
        except:
            pass

        # Get calibration history
        calibration = []
        try:
            cur.execute("""
                SELECT * FROM calibration_history
                ORDER BY created_at DESC
                LIMIT 50
            """)
            columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    record[col] = val
                calibration.append(record)
        except:
            pass

        # Get Prometheus training history
        prometheus = []
        try:
            cur.execute("""
                SELECT training_id, training_date, total_samples, accuracy,
                       precision_score, recall, f1_score, auc_roc, brier_score,
                       cv_accuracy_mean, cv_accuracy_std, calibration_error,
                       feature_importance, model_type, model_version,
                       interpretation, honest_assessment, recommendation
                FROM prometheus_training_history
                ORDER BY training_date DESC
                LIMIT 20
            """)
            columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    record[col] = val
                prometheus.append(record)
        except:
            pass

        return {
            "success": True,
            "data": {
                "models": models,
                "predictions": predictions,
                "calibration_history": calibration,
                "prometheus_training": prometheus
            }
        }

    except Exception as e:
        logger.error(f"Error getting ML model details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/argus-gamma-details")
async def get_argus_gamma_details(
    limit: int = Query(50, ge=1, le=500)
):
    """Get ARGUS gamma flip details and predictions"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()

        # Get gamma flips
        flips = []
        try:
            cur.execute("""
                SELECT * FROM argus_gamma_flips
                ORDER BY flip_time DESC
                LIMIT %s
            """, (limit,))
            columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    record[col] = val
                flips.append(record)
        except:
            pass

        # Get predictions with outcomes
        predictions = []
        try:
            cur.execute("""
                SELECT p.*, o.actual_close, o.actual_pin_strike,
                       o.pin_accuracy, o.direction_correct, o.magnet_touched
                FROM argus_predictions p
                LEFT JOIN argus_outcomes o ON p.id = o.prediction_id
                ORDER BY p.prediction_time DESC
                LIMIT %s
            """, (limit,))
            columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    record[col] = val
                predictions.append(record)
        except:
            pass

        # Get accuracy metrics
        accuracy = []
        try:
            cur.execute("""
                SELECT * FROM argus_accuracy
                ORDER BY metric_date DESC
                LIMIT 30
            """)
            columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    record[col] = val
                accuracy.append(record)
        except:
            pass

        return {
            "success": True,
            "data": {
                "gamma_flips": flips,
                "predictions_with_outcomes": predictions,
                "accuracy_metrics": accuracy
            }
        }

    except Exception as e:
        logger.error(f"Error getting ARGUS details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
