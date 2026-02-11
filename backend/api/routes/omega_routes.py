"""
OMEGA Orchestrator API Routes
==============================

Complete REST API for the OMEGA (Optimal Market Execution & Governance Architecture)
Orchestrator — the central coordination hub for all trading decisions.

Exposes:
- System status and health
- 4-layer decision pipeline visibility
- Bot orchestration and kill switch management
- Gap implementation monitoring (AutoRetrain, Thompson, Regime, Correlation, Equity)
- Decision history and simulation
- Real-time status for dashboard consumption

Author: AlphaGEX Quant Team
Date: February 2026
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")

router = APIRouter(prefix="/api/omega", tags=["OMEGA Orchestrator"])

# =============================================================================
# OPTIONAL DEPENDENCY IMPORTS (follow AlphaGEX try/except pattern)
# =============================================================================

OMEGA_AVAILABLE = False
get_omega_orchestrator = None
OmegaOrchestrator = None
TradingDecision = None

try:
    from core.omega_orchestrator import (
        get_omega_orchestrator,
        OmegaOrchestrator,
        TradingDecision,
        DecisionAuthority,
        RegimeTransition,
    )
    OMEGA_AVAILABLE = True
    logger.info("OMEGA Orchestrator loaded for API routes")
except ImportError as e:
    logger.warning(f"OMEGA Orchestrator not available: {e}")

PROVERBS_AVAILABLE = False
get_proverbs_enhanced = None

try:
    from quant.proverbs_enhancements import get_proverbs_enhanced
    PROVERBS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Proverbs not available: {e}")

PROVERBS_FEEDBACK_AVAILABLE = False
ProverbsFeedbackLoop = None

try:
    from quant.proverbs_feedback_loop import ProverbsFeedbackLoop
    PROVERBS_FEEDBACK_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Proverbs Feedback Loop not available: {e}")

WISDOM_AVAILABLE = False
FortressMLAdvisor = None

try:
    from quant.fortress_ml_advisor import FortressMLAdvisor
    WISDOM_AVAILABLE = True
except ImportError as e:
    logger.warning(f"WISDOM (FortressMLAdvisor) not available: {e}")

PROPHET_AVAILABLE = False
ProphetAdvisor = None

try:
    from quant.prophet_advisor import ProphetAdvisor
    PROPHET_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Prophet Advisor not available: {e}")

DB_AVAILABLE = False
get_connection = None

try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Database adapter not available: {e}")

# =============================================================================
# PYDANTIC REQUEST MODELS
# =============================================================================

class SimulationRequest(BaseModel):
    """Request model for OMEGA decision simulation"""
    bot_name: str = Field(..., description="Bot name (FORTRESS, SOLOMON, ANCHOR, LAZARUS, CORNERSTONE)")
    vix: float = Field(20.0, ge=5.0, le=100.0, description="VIX level")
    spot_price: float = Field(585.0, ge=100.0, le=1000.0, description="SPY spot price")
    net_gamma: float = Field(0.0, description="Net gamma exposure")
    gex_regime: str = Field("POSITIVE", description="GEX regime (POSITIVE/NEGATIVE/NEUTRAL)")
    price_trend: str = Field("NEUTRAL", description="Price trend (BULLISH/BEARISH/NEUTRAL)")
    day_of_week: int = Field(0, ge=0, le=4, description="Day of week (0=Monday)")
    expected_move_pct: float = Field(1.0, ge=0.0, le=10.0, description="Expected move %")
    flip_point: Optional[float] = Field(None, description="GEX flip point price")
    put_wall: Optional[float] = Field(None, description="Put wall price")
    call_wall: Optional[float] = Field(None, description="Call wall price")


class KillSwitchRequest(BaseModel):
    """Request model for manual kill switch activation"""
    reason: str = Field(..., min_length=5, max_length=500, description="Reason for kill/revive")



# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_omega():
    """Get OMEGA singleton, raise 503 if unavailable"""
    if not OMEGA_AVAILABLE or get_omega_orchestrator is None:
        raise HTTPException(status_code=503, detail="OMEGA Orchestrator not available")
    return get_omega_orchestrator()


def _get_bot_wiring_status() -> Dict[str, Any]:
    """Check which bots are wired to use OMEGA vs running independently"""
    # OMEGA is not currently wired into any bot
    bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
    return {
        bot: {
            "wired_to_omega": False,
            "uses_omega_mixin": False,
            "decision_source": "Prophet (direct call in trader.py)"
        }
        for bot in bots
    }


def _get_kill_switch_db_state(bot_name: str) -> Dict[str, Any]:
    """Read actual kill switch state from database"""
    result = {
        "db_is_killed": False,
        "db_kill_reason": None,
        "db_killed_at": None,
        "is_bot_killed_returns": False,
        "mismatch": False
    }

    if not DB_AVAILABLE:
        result["error"] = "Database not available"
        return result

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT is_killed, kill_reason, killed_at
               FROM proverbs_kill_switch
               WHERE bot_name = %s
               ORDER BY killed_at DESC NULLS LAST
               LIMIT 1""",
            [bot_name]
        )
        row = cursor.fetchone()

        if row:
            result["db_is_killed"] = bool(row[0])
            result["db_kill_reason"] = row[1]
            result["db_killed_at"] = row[2].isoformat() if row[2] else None
    except Exception as e:
        logger.warning(f"Could not read kill switch DB for {bot_name}: {e}")
        result["error"] = str(e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    # Check what is_bot_killed() actually returns (known to always be False)
    if PROVERBS_FEEDBACK_AVAILABLE:
        try:
            pfl = ProverbsFeedbackLoop()
            result["is_bot_killed_returns"] = pfl.is_bot_killed(bot_name)
        except Exception:
            pass

    # Flag mismatch
    result["mismatch"] = result["db_is_killed"] and not result["is_bot_killed_returns"]
    return result


def _get_training_schedule() -> List[Dict[str, Any]]:
    """Return the coordinated Sunday training schedule"""
    return [
        {"model": "WISDOM", "day": "Sunday", "time_ct": "4:00 PM", "file": "fortress_ml_advisor.py", "type": "XGBoost"},
        {"model": "Prophet (combined)", "day": "Sunday", "time_ct": "5:00 PM", "file": "prophet_advisor.py", "type": "GBC"},
        {"model": "Prophet (sub-models)", "day": "Sunday", "time_ct": "5:00 PM", "file": "prophet_advisor.py", "type": "GBC"},
        {"model": "ORION (5 sub-models)", "day": "Sunday", "time_ct": "6:00 PM", "file": "gex_probability_models.py", "type": "XGBoost"},
        {"model": "Auto-Validation", "day": "Sunday", "time_ct": "7:00 PM", "file": "auto_validation_system.py", "type": "Walk-forward"},
        {"model": "PROVERBS Feedback", "day": "Daily", "time_ct": "4:00 PM", "file": "proverbs_feedback_loop.py", "type": "Analysis"},
    ]


# =============================================================================
# 1. SYSTEM STATUS ENDPOINTS
# =============================================================================

@router.get("/status")
async def get_omega_status():
    """
    Get comprehensive OMEGA Orchestrator status.

    Returns overall health, layer states, gap implementation statuses,
    and critical wiring information.
    """
    omega = _get_omega()

    try:
        status = omega.get_status()
        now = datetime.now(CENTRAL_TZ)

        # Determine overall health
        health = "ACTIVE"
        health_issues = []

        # Check if any bot has a kill switch mismatch
        bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
        kill_statuses = {}
        any_mismatch = False
        for bot in bots:
            ks = _get_kill_switch_db_state(bot)
            kill_statuses[bot] = ks
            if ks.get("mismatch"):
                any_mismatch = True
                health_issues.append(f"Kill switch mismatch for {bot}")

        if any_mismatch:
            health = "DEGRADED"

        # Check wiring status
        wiring = _get_bot_wiring_status()
        all_unwired = all(not v["wired_to_omega"] for v in wiring.values())
        if all_unwired:
            health_issues.append("No bots wired to OMEGA — all decisions bypass orchestrator")

        return {
            "status": "success",
            "health": health,
            "health_issues": health_issues,
            "omega_status": status,
            "wiring": wiring,
            "wired_bot_count": sum(1 for v in wiring.values() if v["wired_to_omega"]),
            "total_bot_count": len(wiring),
            "kill_switch_statuses": kill_statuses,
            "kill_switch_bug_detected": any_mismatch,
            "layers": {
                "layer_1_proverbs": {
                    "name": "PROVERBS Safety Gate",
                    "status": "ACTIVE" if PROVERBS_AVAILABLE else "UNAVAILABLE",
                    "authority": "ABSOLUTE — can veto all trades",
                    "known_bug": "is_bot_killed() always returns False"
                },
                "layer_2_ensemble": {
                    "name": "Ensemble Context",
                    "status": "GUTTED",
                    "authority": "INFORMATIONAL — currently returns neutral",
                    "note": "Returns NEUTRAL with 50% confidence — 'Prophet is god'"
                },
                "layer_3_wisdom": {
                    "name": "WISDOM ML Decision",
                    "status": "ACTIVE" if WISDOM_AVAILABLE else "UNAVAILABLE",
                    "authority": "PRIMARY — win probability prediction"
                },
                "layer_4_prophet": {
                    "name": "Prophet Adaptation",
                    "status": "ACTIVE" if PROPHET_AVAILABLE else "UNAVAILABLE",
                    "authority": "ADAPTATION — bot-specific adjustments, no veto"
                },
            },
            "gap_implementations": {
                "gap1_auto_retrain": status.get("gaps", {}).get("gap1_auto_retrain", {}),
                "gap2_thompson_capital": status.get("gaps", {}).get("gap2_thompson", {}),
                "gap6_regime_transition": status.get("gaps", {}).get("gap6_regime", {}),
                "gap9_cross_bot_correlation": status.get("gaps", {}).get("gap9_correlation", {}),
                "gap10_equity_scaling": status.get("gaps", {}).get("gap10_equity", {}),
            },
            "training_schedule": _get_training_schedule(),
            "recent_decision_count": status.get("recent_decisions", 0),
            "timestamp": now.isoformat()
        }
    except Exception as e:
        logger.error(f"OMEGA status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_omega_health():
    """Quick health check for OMEGA Orchestrator."""
    now = datetime.now(CENTRAL_TZ)

    return {
        "status": "success",
        "omega_available": OMEGA_AVAILABLE,
        "proverbs_available": PROVERBS_AVAILABLE,
        "wisdom_available": WISDOM_AVAILABLE,
        "prophet_available": PROPHET_AVAILABLE,
        "database_available": DB_AVAILABLE,
        "timestamp": now.isoformat()
    }


# =============================================================================
# 2. DECISION PIPELINE ENDPOINTS
# =============================================================================

@router.get("/decisions/live")
async def get_live_decisions():
    """
    Get what OMEGA would decide RIGHT NOW for each bot.

    Runs the full 4-layer pipeline for each bot with current market conditions.
    Returns each layer's input/output and final recommendation.
    """
    omega = _get_omega()

    try:
        bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
        decisions = {}

        # Build current market context from available data
        gex_data = {"regime": "UNKNOWN", "net_gamma": 0, "trend": "UNKNOWN"}
        features = {"vix": 20.0}  # Minimal features - OMEGA will use what's available
        data_sources = {"vix": "DEFAULT (20.0)", "spot_price": "NOT_AVAILABLE"}

        # Try to get real market data
        try:
            from backend.api.dependencies import get_vix
            vix_val = get_vix()
            if vix_val:
                features["vix"] = float(vix_val)
                data_sources["vix"] = "LIVE"
        except Exception:
            pass

        try:
            from backend.api.dependencies import get_price
            spot = get_price("SPY")
            if spot:
                features["spot_price"] = float(spot)
                data_sources["spot_price"] = "LIVE"
        except Exception:
            pass

        for bot in bots:
            try:
                decision = omega.get_trading_decision(
                    bot_name=bot,
                    gex_data=gex_data,
                    features=features
                )
                decisions[bot] = decision.to_dict()
            except Exception as e:
                decisions[bot] = {"error": str(e)}

        return {
            "status": "success",
            "decisions": decisions,
            "market_context": {
                "vix": features.get("vix"),
                "spot_price": features.get("spot_price"),
                "gex_regime": gex_data.get("regime"),
                "data_sources": data_sources,
            },
            "note": "These are simulated decisions — OMEGA is not currently wired into trading bots",
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Live decisions failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/history")
async def get_decision_history(
    bot_name: Optional[str] = Query(None, description="Filter by bot name"),
    limit: int = Query(50, ge=1, le=500, description="Number of decisions to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    Get historical OMEGA decisions with full layer trace.

    Decisions are stored in memory on the OMEGA singleton.
    """
    omega = _get_omega()

    try:
        history = omega.decision_history

        # Filter by bot
        if bot_name:
            history = [d for d in history if d.bot_name == bot_name.upper()]

        total = len(history)

        # Sort by timestamp desc and paginate
        history_sorted = sorted(history, key=lambda d: d.timestamp, reverse=True)
        page = history_sorted[offset:offset + limit]

        return {
            "status": "success",
            "total": total,
            "offset": offset,
            "limit": limit,
            "decisions": [d.to_dict() for d in page],
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Decision history failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decisions/simulate")
async def simulate_decision(request: SimulationRequest):
    """
    Simulate what OMEGA would decide given hypothetical market conditions.

    This runs the full 4-layer pipeline with user-provided inputs.
    No actual trades are placed.
    """
    omega = _get_omega()

    try:
        import math
        day = request.day_of_week

        gex_data = {
            "regime": request.gex_regime,
            "net_gamma": request.net_gamma,
            "trend": request.price_trend,
            "put_wall": request.put_wall or (request.spot_price * 0.98),
            "call_wall": request.call_wall or (request.spot_price * 1.02),
            "flip_point": request.flip_point or request.spot_price,
        }

        features = {
            "vix": request.vix,
            "spot_price": request.spot_price,
            "expected_move_pct": request.expected_move_pct,
            "day_of_week_sin": math.sin(2 * math.pi * day / 5),
            "day_of_week_cos": math.cos(2 * math.pi * day / 5),
            "net_gex_normalized": request.net_gamma / 1e9 if abs(request.net_gamma) > 1000 else request.net_gamma,
            "vix_percentile": 50.0,
            "price_change_1d": 0.0,
            "distance_to_flip_pct": 0.0,
        }

        # Calculate distance to flip
        if request.flip_point and request.spot_price > 0:
            features["distance_to_flip_pct"] = (
                (request.spot_price - request.flip_point) / request.spot_price * 100
            )

        # Capture history length before simulation so we can remove the
        # simulated entry — get_trading_decision always appends to history.
        history_len_before = len(omega.decision_history)

        decision = omega.get_trading_decision(
            bot_name=request.bot_name.upper(),
            gex_data=gex_data,
            features=features,
            current_regime=request.gex_regime
        )

        # Remove simulated decision from history (prevent pollution)
        with omega._lock:
            if len(omega.decision_history) > history_len_before:
                omega.decision_history = omega.decision_history[:history_len_before]

        return {
            "status": "success",
            "simulation": True,
            "input": {
                "bot_name": request.bot_name.upper(),
                "market_conditions": {
                    "vix": request.vix,
                    "spot_price": request.spot_price,
                    "gex_regime": request.gex_regime,
                    "price_trend": request.price_trend,
                    "day_of_week": request.day_of_week,
                    "expected_move_pct": request.expected_move_pct,
                    "net_gamma": request.net_gamma,
                }
            },
            "decision": decision.to_dict(),
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Decision simulation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 3. LAYER STATUS ENDPOINTS
# =============================================================================

@router.get("/layers")
async def get_all_layers():
    """
    Get status of all 4 OMEGA decision layers.

    Shows enabled/disabled state, availability, and known issues.
    """
    omega = _get_omega()

    try:
        return {
            "status": "success",
            "layers": [
                {
                    "layer_number": 1,
                    "name": "PROVERBS Safety Gate",
                    "authority": "ABSOLUTE",
                    "available": PROVERBS_AVAILABLE,
                    "enabled": True,
                    "description": "Consecutive loss tracking, daily loss limits, kill switch management",
                    "known_bugs": ["is_bot_killed() always returns False — kill switch enforcement broken"],
                    "files": ["quant/proverbs_enhancements.py", "quant/proverbs_feedback_loop.py"],
                    "line_count": 5919,
                },
                {
                    "layer_number": 2,
                    "name": "Ensemble Context",
                    "authority": "INFORMATIONAL",
                    "available": True,
                    "enabled": False,
                    "description": "Market context aggregation — CURRENTLY GUTTED",
                    "known_bugs": ["Returns NEUTRAL with 50% confidence always — 'Prophet is god'"],
                    "note": "This layer was intentionally disabled. It always returns neutral.",
                    "files": ["core/omega_orchestrator.py (lines 956-976)"],
                },
                {
                    "layer_number": 3,
                    "name": "WISDOM ML Decision",
                    "authority": "PRIMARY",
                    "available": WISDOM_AVAILABLE,
                    "enabled": True,
                    "description": "XGBoost win probability prediction — primary decision maker",
                    "version": "V3",
                    "features": 13,
                    "files": ["quant/fortress_ml_advisor.py"],
                    "line_count": 3200,
                },
                {
                    "layer_number": 4,
                    "name": "Prophet Adaptation",
                    "authority": "ADAPTATION (no veto)",
                    "available": PROPHET_AVAILABLE,
                    "enabled": True,
                    "description": "Bot-specific adjustments — strike selection, risk scaling",
                    "version": "V3",
                    "files": ["quant/prophet_advisor.py"],
                    "line_count": 6269,
                },
            ],
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Layer status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/layers/{layer_number}")
async def get_layer_detail(layer_number: int):
    """Get detailed status for a specific layer (1-4)."""
    if layer_number < 1 or layer_number > 4:
        raise HTTPException(status_code=400, detail="Layer number must be 1-4")

    omega = _get_omega()

    try:
        if layer_number == 1:
            # PROVERBS layer
            bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
            proverbs_data = {}

            for bot in bots:
                ks = _get_kill_switch_db_state(bot)
                proverbs_data[bot] = {
                    "kill_switch": ks,
                    "proverbs_verdict": None
                }
                try:
                    verdict = omega._check_proverbs(bot)
                    proverbs_data[bot]["proverbs_verdict"] = verdict.to_dict()
                except Exception as e:
                    proverbs_data[bot]["proverbs_verdict"] = {"error": str(e)}

            return {
                "status": "success",
                "layer": 1,
                "name": "PROVERBS Safety Gate",
                "bots": proverbs_data,
                "known_bug": "is_bot_killed() always returns False",
                "timestamp": datetime.now(CENTRAL_TZ).isoformat()
            }

        elif layer_number == 2:
            # Ensemble layer (gutted)
            return {
                "status": "success",
                "layer": 2,
                "name": "Ensemble Context",
                "state": "GUTTED",
                "description": "Ensemble Strategy was removed — 'Prophet is god'",
                "output": {
                    "signal": "NEUTRAL",
                    "confidence": 50.0,
                    "position_size_multiplier": 1.0,
                    "note": "This layer always returns these exact values"
                },
                "timestamp": datetime.now(CENTRAL_TZ).isoformat()
            }

        elif layer_number == 3:
            # WISDOM ML layer
            advisor_status = {}
            if WISDOM_AVAILABLE:
                try:
                    advisor = FortressMLAdvisor()
                    advisor_status = {
                        "is_trained": getattr(advisor, 'is_trained', False),
                        "model_version": getattr(advisor, 'model_version', 'unknown'),
                        "feature_version": getattr(advisor, 'feature_version', 'unknown'),
                        "feature_count": len(getattr(advisor, 'FEATURE_COLS', [])),
                        "features": list(getattr(advisor, 'FEATURE_COLS', [])),
                    }
                except Exception as e:
                    advisor_status = {"error": str(e)}

            return {
                "status": "success",
                "layer": 3,
                "name": "WISDOM ML Decision",
                "available": WISDOM_AVAILABLE,
                "advisor": advisor_status,
                "timestamp": datetime.now(CENTRAL_TZ).isoformat()
            }

        else:  # layer_number == 4
            # Prophet layer
            prophet_status = {}
            if PROPHET_AVAILABLE:
                try:
                    prophet = ProphetAdvisor()
                    prophet_status = {
                        "is_trained": getattr(prophet, 'is_trained', False),
                        "model_version": getattr(prophet, 'model_version', 'unknown'),
                        "feature_version": getattr(prophet, 'feature_version', 'unknown'),
                        "has_sub_models": hasattr(prophet, '_sub_models'),
                    }
                    if hasattr(prophet, '_sub_models'):
                        prophet_status["sub_models"] = {
                            name: {
                                "is_trained": info.get("is_trained", False),
                                "version": info.get("version"),
                            }
                            for name, info in prophet._sub_models.items()
                        }
                except Exception as e:
                    prophet_status = {"error": str(e)}

            return {
                "status": "success",
                "layer": 4,
                "name": "Prophet Adaptation",
                "available": PROPHET_AVAILABLE,
                "prophet": prophet_status,
                "timestamp": datetime.now(CENTRAL_TZ).isoformat()
            }

    except Exception as e:
        logger.error(f"Layer {layer_number} detail failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 4. BOT ORCHESTRATION ENDPOINTS
# =============================================================================

@router.get("/bots")
async def get_all_bots():
    """
    Get all bots with OMEGA-assigned status, kill switch state,
    capital allocation, and correlation warnings.
    """
    omega = _get_omega()

    try:
        bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
        wiring = _get_bot_wiring_status()
        bot_data = {}

        for bot in bots:
            kill_status = _get_kill_switch_db_state(bot)

            # Get Proverbs verdict
            proverbs_verdict = None
            try:
                verdict = omega._check_proverbs(bot)
                proverbs_verdict = verdict.to_dict()
            except Exception:
                pass

            # Get recent decisions for this bot
            recent = [
                d.to_dict()
                for d in sorted(omega.decision_history, key=lambda x: x.timestamp, reverse=True)
                if d.bot_name == bot
            ][:5]

            bot_data[bot] = {
                "wiring": wiring.get(bot, {}),
                "kill_switch": kill_status,
                "proverbs_verdict": proverbs_verdict,
                "recent_decisions": recent,
                "recent_decision_count": len([d for d in omega.decision_history if d.bot_name == bot]),
            }

        # Get correlation status
        correlation_status = omega.correlation_enforcer.get_status()

        # Get capital allocations
        thompson = omega._get_thompson_allocator()
        capital_allocation = {}
        if thompson:
            try:
                alloc = thompson.sample_allocation(omega.capital)
                capital_allocation = alloc.allocations
            except Exception:
                pass

        return {
            "status": "success",
            "bots": bot_data,
            "correlation": correlation_status,
            "capital_allocation": capital_allocation,
            "total_capital": omega.capital,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Bot status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bots/{bot_name}")
async def get_bot_detail(bot_name: str):
    """Get deep detail for a specific bot's OMEGA integration."""
    omega = _get_omega()
    bot = bot_name.upper()

    valid_bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
    if bot not in valid_bots:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bot name. Must be one of: {', '.join(valid_bots)}"
        )

    try:
        kill_status = _get_kill_switch_db_state(bot)
        wiring = _get_bot_wiring_status()

        # Get Proverbs details
        proverbs_verdict = None
        try:
            verdict = omega._check_proverbs(bot)
            proverbs_verdict = verdict.to_dict()
        except Exception as e:
            proverbs_verdict = {"error": str(e)}

        # Get all decisions for this bot
        bot_decisions = [
            d.to_dict()
            for d in sorted(omega.decision_history, key=lambda x: x.timestamp, reverse=True)
            if d.bot_name == bot
        ]

        # Compute win/loss from decisions (if outcomes recorded)
        trade_decisions = [d for d in omega.decision_history if d.bot_name == bot]

        # Get correlation info
        corr_check = omega.correlation_enforcer.check_new_position(
            bot_name=bot,
            direction="NEUTRAL",
            proposed_exposure_pct=5.0
        )

        # Strategy type mapping
        strategy_map = {
            "FORTRESS": "IC (SPY 0DTE Iron Condor)",
            "ANCHOR": "IC (SPX Weekly Iron Condor)",
            "SOLOMON": "Directional (SPY Calls/Puts)",
            "LAZARUS": "Directional (SPY Call Entries)",
            "CORNERSTONE": "Directional (SPY Cash-Secured Puts)",
        }

        return {
            "status": "success",
            "bot_name": bot,
            "strategy": strategy_map.get(bot, "Unknown"),
            "wiring": wiring.get(bot, {}),
            "kill_switch": kill_status,
            "proverbs_verdict": proverbs_verdict,
            "correlation": corr_check,
            "decision_count": len(bot_decisions),
            "recent_decisions": bot_decisions[:20],
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Bot detail for {bot} failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_name}/kill")
async def kill_bot(bot_name: str, request: KillSwitchRequest):
    """
    Manually activate kill switch for a bot.

    This writes directly to the proverbs_kill_switch database table,
    bypassing the broken is_bot_killed() method.
    """
    bot = bot_name.upper()
    valid_bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
    if bot not in valid_bots:
        raise HTTPException(status_code=400, detail=f"Invalid bot. Must be one of: {', '.join(valid_bots)}")

    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(CENTRAL_TZ)

        # Upsert kill switch state
        cursor.execute("""
            INSERT INTO proverbs_kill_switch (bot_name, is_killed, kill_reason, killed_at)
            VALUES (%s, TRUE, %s, %s)
            ON CONFLICT (bot_name) DO UPDATE SET
                is_killed = TRUE,
                kill_reason = EXCLUDED.kill_reason,
                killed_at = EXCLUDED.killed_at
        """, [bot, f"MANUAL KILL via OMEGA API: {request.reason}", now])

        # Log to audit trail (schema: action_type, bot_name, actor, action_description, reason)
        cursor.execute("""
            INSERT INTO proverbs_audit_log (action_type, bot_name, actor, action_description, reason, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, [
            "MANUAL_KILL",
            bot,
            "OMEGA API",
            f"Manual kill switch activation for {bot}",
            request.reason,
            now
        ])

        conn.commit()

        logger.warning(f"OMEGA API: Manual kill activated for {bot} — reason: {request.reason}")

        return {
            "status": "success",
            "action": "KILL_ACTIVATED",
            "bot_name": bot,
            "reason": request.reason,
            "warning": "NOTE: is_bot_killed() still returns False due to known bug. "
                       "This sets the DB state but enforcement depends on the P0 fix.",
            "timestamp": now.isoformat()
        }
    except Exception as e:
        logger.error(f"Kill bot {bot} failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@router.post("/bots/{bot_name}/revive")
async def revive_bot(bot_name: str, request: KillSwitchRequest):
    """
    Revive a killed bot (deactivate kill switch).

    Requires explicit confirmation reason.
    """
    bot = bot_name.upper()
    valid_bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
    if bot not in valid_bots:
        raise HTTPException(status_code=400, detail=f"Invalid bot. Must be one of: {', '.join(valid_bots)}")

    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(CENTRAL_TZ)

        # UPSERT instead of UPDATE — handles case where bot has no row yet
        cursor.execute("""
            INSERT INTO proverbs_kill_switch (bot_name, is_killed, kill_reason, resumed_at, resumed_by)
            VALUES (%s, FALSE, %s, %s, %s)
            ON CONFLICT (bot_name) DO UPDATE SET
                is_killed = FALSE,
                kill_reason = EXCLUDED.kill_reason,
                resumed_at = EXCLUDED.resumed_at,
                resumed_by = EXCLUDED.resumed_by
        """, [bot, f"REVIVED via OMEGA API: {request.reason}", now, "OMEGA API"])

        # Log to audit trail (schema: action_type, bot_name, actor, action_description, reason)
        cursor.execute("""
            INSERT INTO proverbs_audit_log (action_type, bot_name, actor, action_description, reason, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, [
            "MANUAL_REVIVE",
            bot,
            "OMEGA API",
            f"Kill switch deactivated (bot revived) for {bot}",
            request.reason,
            now
        ])

        conn.commit()

        logger.info(f"OMEGA API: Bot {bot} revived — reason: {request.reason}")

        return {
            "status": "success",
            "action": "BOT_REVIVED",
            "bot_name": bot,
            "reason": request.reason,
            "timestamp": now.isoformat()
        }
    except Exception as e:
        logger.error(f"Revive bot {bot} failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@router.post("/bots/kill-all")
async def kill_all_bots(request: KillSwitchRequest):
    """
    Emergency kill all bots.

    This is the panic button — activates kill switch for every trading bot.
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(CENTRAL_TZ)
        bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]

        for bot in bots:
            cursor.execute("""
                INSERT INTO proverbs_kill_switch (bot_name, is_killed, kill_reason, killed_at)
                VALUES (%s, TRUE, %s, %s)
                ON CONFLICT (bot_name) DO UPDATE SET
                    is_killed = TRUE,
                    kill_reason = EXCLUDED.kill_reason,
                    killed_at = EXCLUDED.killed_at
            """, [bot, f"EMERGENCY KILL ALL via OMEGA API: {request.reason}", now])

        # Log to audit trail (schema: action_type, bot_name, actor, action_description, reason)
        cursor.execute("""
            INSERT INTO proverbs_audit_log (action_type, bot_name, actor, action_description, reason, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, [
            "EMERGENCY_KILL_ALL",
            "ALL_BOTS",
            "OMEGA API",
            f"Emergency kill all bots: {', '.join(bots)}",
            request.reason,
            now
        ])

        conn.commit()

        logger.critical(f"OMEGA API: EMERGENCY KILL ALL — reason: {request.reason}")

        return {
            "status": "success",
            "action": "ALL_BOTS_KILLED",
            "bots_killed": bots,
            "reason": request.reason,
            "warning": "NOTE: is_bot_killed() still returns False due to known bug. "
                       "DB state is set but enforcement depends on the P0 fix.",
            "timestamp": now.isoformat()
        }
    except Exception as e:
        logger.error(f"Kill all bots failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# =============================================================================
# 5. GAP IMPLEMENTATION ENDPOINTS
# =============================================================================

@router.get("/capital-allocation")
async def get_capital_allocation():
    """
    Get Thompson Sampling bandit capital allocations per bot.

    Shows exploration vs exploitation ratio, allocation percentages,
    and confidence intervals.
    """
    omega = _get_omega()

    try:
        thompson = omega._get_thompson_allocator()
        allocation_data = {
            "available": thompson is not None,
            "allocations": {},
            "total_capital": omega.capital,
        }

        if thompson:
            try:
                alloc = thompson.sample_allocation(omega.capital)
                allocation_data["allocations"] = alloc.allocations
                allocation_data["confidence"] = getattr(alloc, 'confidence', {})
            except Exception as e:
                allocation_data["error"] = str(e)
        else:
            # Default equal allocation
            bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
            allocation_data["allocations"] = {bot: 0.20 for bot in bots}
            allocation_data["note"] = "Thompson Sampling not available — using equal 20% allocation"

        return {
            "status": "success",
            "capital_allocation": allocation_data,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Capital allocation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime")
async def get_regime_status():
    """
    Get current market regime from RegimeTransitionDetector.

    Shows regime type, confidence, duration, historical transitions.
    """
    omega = _get_omega()

    try:
        regimes = omega.regime_detector.get_current_regimes()
        recent_transitions = omega.regime_detector.recent_transitions[-10:]

        return {
            "status": "success",
            "current_regimes": regimes,
            "recent_transitions": recent_transitions,
            "observation_count": {
                "gex": len(omega.regime_detector.gex_regime_history),
                "vix": len(omega.regime_detector.vix_regime_history),
                "trend": len(omega.regime_detector.trend_history),
            },
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Regime status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/correlations")
async def get_correlation_status():
    """
    Get CrossBotCorrelation matrix — pairwise correlation between all active bots.

    Shows concentration risk warnings and diversification metrics.
    """
    omega = _get_omega()

    try:
        status = omega.correlation_enforcer.get_status()

        # Check each bot pair for correlation
        bots = ["FORTRESS", "ANCHOR", "SOLOMON", "LAZARUS", "CORNERSTONE"]
        pair_checks = {}
        for i, bot_a in enumerate(bots):
            for bot_b in bots[i+1:]:
                key = f"{bot_a}:{bot_b}"
                pair_checks[key] = omega.correlation_enforcer.correlation_cache.get(key, 0.0)

        return {
            "status": "success",
            "correlation_matrix": pair_checks,
            "active_positions": status,
            "max_correlation_threshold": omega.correlation_enforcer.MAX_CORRELATION_THRESHOLD,
            "max_correlated_exposure_pct": omega.correlation_enforcer.MAX_CORRELATED_EXPOSURE_PCT,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Correlation status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-scaling")
async def get_equity_scaling():
    """
    Get EquityCompoundScaler current state.

    Shows account equity, scaling factor, drawdown status.
    """
    omega = _get_omega()

    try:
        scaler_status = omega.equity_scaler.get_status()

        # Get position multiplier for a reference risk level
        multiplier_info = omega.equity_scaler.get_position_multiplier(5.0)

        return {
            "status": "success",
            "equity_scaler": scaler_status,
            "current_multiplier": multiplier_info,
            "config": {
                "drawdown_reduction_threshold": omega.equity_scaler.DRAWDOWN_REDUCTION_THRESHOLD,
                "drawdown_reduction_factor": omega.equity_scaler.DRAWDOWN_REDUCTION_FACTOR,
                "growth_scaling_factor": omega.equity_scaler.GROWTH_SCALING_FACTOR,
                "max_position_multiplier": omega.equity_scaler.MAX_POSITION_MULTIPLIER,
                "min_position_multiplier": omega.equity_scaler.MIN_POSITION_MULTIPLIER,
            },
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Equity scaling failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/retrain-status")
async def get_retrain_status():
    """
    Get AutoRetrain state for each model.

    Shows last retrain date, performance metrics, degradation indicators,
    and the Sunday retraining schedule.
    """
    omega = _get_omega()

    try:
        retrain_status = omega.auto_retrain_monitor.get_status()

        return {
            "status": "success",
            "auto_retrain": retrain_status,
            "training_schedule": _get_training_schedule(),
            "config": {
                "win_rate_degradation_threshold": omega.auto_retrain_monitor.WIN_RATE_DEGRADATION_THRESHOLD,
                "max_model_age_days": omega.auto_retrain_monitor.MAX_MODEL_AGE_DAYS,
                "min_trades_for_evaluation": omega.auto_retrain_monitor.MIN_TRADES_FOR_EVALUATION,
                "consecutive_loss_trigger": omega.auto_retrain_monitor.CONSECUTIVE_LOSS_TRIGGER,
            },
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Retrain status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 6. AUDIT LOG ENDPOINTS
# =============================================================================

@router.get("/audit-log")
async def get_audit_log(
    bot_name: Optional[str] = Query(None, description="Filter by bot name"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(50, ge=1, le=200, description="Number of entries"),
):
    """
    Get OMEGA-related entries from the PROVERBS audit log.

    Includes manual kills, revives, layer toggles, and system events.
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = "SELECT action_type, bot_name, actor, action_description, reason, created_at FROM proverbs_audit_log"
        conditions = []
        params = []

        if bot_name:
            conditions.append("bot_name = %s")
            params.append(bot_name.upper())
        if action:
            conditions.append("action_type = %s")
            params.append(action.upper())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        entries = []
        for row in rows:
            entry = dict(zip(columns, row))
            # Convert datetime
            if entry.get("created_at"):
                entry["created_at"] = entry["created_at"].isoformat()
            entries.append(entry)

        return {
            "status": "success",
            "count": len(entries),
            "entries": entries,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Audit log failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# =============================================================================
# 7. ML SYSTEM INVENTORY
# =============================================================================

@router.get("/ml-systems")
async def get_ml_systems():
    """
    Get complete inventory of all ML/AI systems in the platform.

    Shows 18 systems with their status, line counts, and relationships.
    """
    systems = [
        {
            "name": "WISDOM",
            "file": "quant/fortress_ml_advisor.py",
            "lines": 3200,
            "type": "XGBoost classifier",
            "role": "Primary ML win probability in signals.py",
            "version": "V3",
            "status": "FIXED" if WISDOM_AVAILABLE else "UNAVAILABLE",
        },
        {
            "name": "Prophet",
            "file": "quant/prophet_advisor.py",
            "lines": 6269,
            "type": "GBC + isotonic calibration",
            "role": "Strategy recommendation + bot-specific advice in trader.py",
            "version": "V3",
            "status": "FIXED" if PROPHET_AVAILABLE else "UNAVAILABLE",
        },
        {
            "name": "ORION",
            "file": "quant/gex_probability_models.py",
            "lines": 4000,
            "type": "5 XGBoost sub-models",
            "role": "GEX probability models for WATCHTOWER/GIDEON/SOLOMON_V2",
            "version": "V2",
            "status": "FIXED",
        },
        {
            "name": "OMEGA",
            "file": "core/omega_orchestrator.py",
            "lines": 1450,
            "type": "Decision hub",
            "role": "Central 4-layer orchestrator — exists but NO bot uses it",
            "version": "V1",
            "status": "NOT_WIRED",
        },
        {
            "name": "PROVERBS",
            "file": "quant/proverbs_enhancements.py + proverbs_feedback_loop.py",
            "lines": 5919,
            "type": "Guardrails + feedback loop",
            "role": "Safety, kill switch, outcome recording, A/B testing",
            "version": "V1",
            "status": "PARTIALLY_BROKEN",
            "known_bug": "is_bot_killed() always returns False",
        },
        {
            "name": "DISCERNMENT",
            "file": "core/discernment_ml_engine.py",
            "lines": 1482,
            "type": "XGBoost + RF + GBC",
            "role": "AI options scanner with direction/magnitude/timing",
            "version": "V1",
            "status": "OPERATIONAL",
            "known_issue": "6 of 9 strategy builders are stubs",
        },
        {
            "name": "Auto Validation",
            "file": "quant/auto_validation_system.py",
            "lines": 1454,
            "type": "Walk-forward validation",
            "role": "Central model validation + auto-retraining for 11 registered models",
            "version": "V1",
            "status": "OPERATIONAL",
        },
        {
            "name": "GEX Directional",
            "file": "quant/gex_directional_ml.py",
            "lines": 900,
            "type": "XGBoost classifier",
            "role": "Market direction prediction from GEX structure",
            "version": "V1",
            "status": "OPERATIONAL",
        },
        {
            "name": "SPX Wheel ML",
            "file": "trading/spx_wheel_ml.py",
            "lines": 300,
            "type": "RF/GBC",
            "role": "ML for SPX Wheel strategy (CORNERSTONE)",
            "version": "V1",
            "status": "PARTIAL",
            "known_issue": "Not wired into CORNERSTONE trader",
        },
        {
            "name": "VALOR ML",
            "file": "trading/valor/ml.py",
            "lines": 100,
            "type": "XGBoost",
            "role": "ML for MES futures (mirrors WISDOM)",
            "version": "V1",
            "status": "DESIGNED",
        },
        {
            "name": "Pattern Learner",
            "file": "ai/autonomous_ml_pattern_learner.py",
            "lines": 150,
            "type": "RandomForest",
            "role": "Multi-timeframe RSI pattern learning",
            "version": "V1",
            "status": "OPERATIONAL",
        },
        {
            "name": "Walk-Forward Optimizer",
            "file": "quant/walk_forward_optimizer.py",
            "lines": 565,
            "type": "Validation framework",
            "role": "Walk-forward cross-validation for ML models",
            "version": "V1",
            "status": "OPERATIONAL",
        },
        {
            "name": "Model Persistence",
            "file": "quant/model_persistence.py",
            "lines": 374,
            "type": "PostgreSQL storage",
            "role": "Store/load trained models from database",
            "version": "V1",
            "status": "OPERATIONAL",
        },
        {
            "name": "Proverbs AI Analyst",
            "file": "quant/proverbs_ai_analyst.py",
            "lines": 634,
            "type": "Claude API analysis",
            "role": "AI-powered trading pattern analysis",
            "version": "V1",
            "status": "OPERATIONAL",
        },
        {
            "name": "Price Trend Tracker",
            "file": "quant/price_trend_tracker.py",
            "lines": 726,
            "type": "Rule-based trends",
            "role": "Multi-timeframe price trend detection",
            "version": "V1",
            "status": "OPERATIONAL",
        },
        {
            "name": "Strategy Competition",
            "file": "core/autonomous_strategy_competition.py",
            "lines": 100,
            "type": "Benchmark framework",
            "role": "Strategy performance comparison and ranking",
            "version": "V1",
            "status": "OPERATIONAL",
        },
        {
            "name": "Integration Layer",
            "file": "quant/integration.py",
            "lines": 639,
            "type": "Walk-forward + Kelly",
            "role": "Combines walk-forward validation with Kelly criterion sizing",
            "version": "V1",
            "status": "OPERATIONAL",
        },
    ]

    return {
        "status": "success",
        "system_count": len(systems),
        "total_lines": sum(s["lines"] for s in systems),
        "systems": systems,
        "timestamp": datetime.now(CENTRAL_TZ).isoformat()
    }
