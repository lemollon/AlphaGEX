"""
APOLLO API Routes - AI-Powered Live Options Scanner

Endpoints:
- POST /api/apollo/scan - Scan symbols with ML predictions
- GET /api/apollo/scan/{scan_id} - Get scan results
- GET /api/apollo/history - Get scan history
- POST /api/apollo/feedback - Record outcome for learning
- GET /api/apollo/performance - Get model performance stats
- GET /api/apollo/live-quote/{symbol} - Get live Tradier quote
- GET /api/apollo/options-chain/{symbol} - Get live options chain
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/apollo", tags=["APOLLO"])


# ============================================================================
# TRADIER CLIENT HELPER
# ============================================================================

_apollo_tradier_instance = None


def get_tradier():
    """
    Get Tradier data fetcher instance with proper credentials.
    Uses same pattern as FORTRESS - explicitly gets credentials from APIConfig.
    """
    global _apollo_tradier_instance

    if _apollo_tradier_instance is not None:
        return _apollo_tradier_instance

    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        from unified_config import APIConfig

        # Try sandbox credentials first (for market data)
        api_key = APIConfig.TRADIER_SANDBOX_API_KEY or APIConfig.TRADIER_API_KEY
        account_id = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

        if api_key and account_id:
            _apollo_tradier_instance = TradierDataFetcher(
                api_key=api_key,
                account_id=account_id,
                sandbox=True
            )
            logger.info("APOLLO: Tradier initialized with credentials")
            return _apollo_tradier_instance

        logger.error("APOLLO: No Tradier credentials configured")
        return None
    except Exception as e:
        logger.error(f"APOLLO: Failed to initialize Tradier: {e}")
        return None


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ScanRequest(BaseModel):
    symbols: List[str]
    include_chains: bool = True  # Include live options chains


class FeedbackRequest(BaseModel):
    scan_id: str
    symbol: str
    actual_direction: str  # bullish, bearish, neutral
    actual_magnitude: str  # small, medium, large
    actual_return_pct: float
    strategy_used: Optional[str] = None
    strategy_pnl: Optional[float] = None
    notes: Optional[str] = None


# ============================================================================
# DATA STORAGE (using existing database)
# ============================================================================

def get_db_connection():
    """Get database connection"""
    try:
        from database_adapter import get_connection
        return get_connection()
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None


def ensure_apollo_tables():
    """Create APOLLO tables if they don't exist"""
    conn = get_db_connection()
    if not conn:
        return

    try:
        c = conn.cursor()

        # APOLLO Scans table
        c.execute('''
            CREATE TABLE IF NOT EXISTS apollo_scans (
                id SERIAL PRIMARY KEY,
                scan_id VARCHAR(50) UNIQUE NOT NULL,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                symbols TEXT NOT NULL,
                results JSONB,
                market_regime VARCHAR(50),
                vix_at_scan REAL,
                scan_duration_ms INTEGER
            )
        ''')

        # APOLLO Predictions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS apollo_predictions (
                id SERIAL PRIMARY KEY,
                prediction_id VARCHAR(50) UNIQUE NOT NULL,
                scan_id VARCHAR(50) REFERENCES apollo_scans(scan_id),
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                symbol VARCHAR(20) NOT NULL,
                direction_pred VARCHAR(20),
                direction_confidence REAL,
                magnitude_pred VARCHAR(20),
                magnitude_confidence REAL,
                timing_pred VARCHAR(20),
                timing_confidence REAL,
                ensemble_confidence REAL,
                features JSONB,
                strategies JSONB,
                model_version VARCHAR(20),
                is_ml_prediction BOOLEAN DEFAULT FALSE
            )
        ''')

        # APOLLO Outcomes table (for learning)
        c.execute('''
            CREATE TABLE IF NOT EXISTS apollo_outcomes (
                id SERIAL PRIMARY KEY,
                outcome_id VARCHAR(50) UNIQUE NOT NULL,
                prediction_id VARCHAR(50),
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                symbol VARCHAR(20) NOT NULL,
                predicted_direction VARCHAR(20),
                actual_direction VARCHAR(20),
                predicted_magnitude VARCHAR(20),
                actual_magnitude VARCHAR(20),
                actual_return_pct REAL,
                direction_correct BOOLEAN,
                magnitude_correct BOOLEAN,
                strategy_used VARCHAR(50),
                strategy_pnl REAL,
                notes TEXT
            )
        ''')

        # APOLLO Model Performance table
        c.execute('''
            CREATE TABLE IF NOT EXISTS apollo_model_performance (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                model_version VARCHAR(20),
                direction_accuracy_7d REAL,
                direction_accuracy_30d REAL,
                magnitude_accuracy_7d REAL,
                magnitude_accuracy_30d REAL,
                total_predictions INTEGER,
                total_outcomes INTEGER,
                sharpe_ratio REAL,
                win_rate REAL
            )
        ''')

        # APOLLO Live Quotes cache
        c.execute('''
            CREATE TABLE IF NOT EXISTS apollo_live_quotes (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                bid REAL,
                ask REAL,
                last REAL,
                volume BIGINT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                change_pct REAL,
                source VARCHAR(50)
            )
        ''')

        # APOLLO Pin Risk History table
        c.execute('''
            CREATE TABLE IF NOT EXISTS apollo_pin_risk_history (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                spot_price REAL,
                pin_risk_score INTEGER,
                pin_risk_level VARCHAR(20),
                gamma_regime VARCHAR(20),
                max_pain REAL,
                call_wall REAL,
                put_wall REAL,
                flip_point REAL,
                net_gex REAL,
                distance_to_max_pain_pct REAL,
                distance_to_flip_pct REAL,
                long_call_outlook VARCHAR(20),
                days_to_expiry INTEGER,
                is_expiration_day BOOLEAN,
                expected_range_low REAL,
                expected_range_high REAL,
                expected_range_pct REAL,
                pin_factors JSONB,
                trading_implications JSONB,
                pin_breakers JSONB,
                summary TEXT
            )
        ''')

        # Indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_apollo_scans_timestamp ON apollo_scans(timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_apollo_predictions_symbol ON apollo_predictions(symbol)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_apollo_pin_risk_symbol ON apollo_pin_risk_history(symbol)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_apollo_pin_risk_timestamp ON apollo_pin_risk_history(timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_apollo_predictions_scan ON apollo_predictions(scan_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_apollo_outcomes_symbol ON apollo_outcomes(symbol)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_apollo_outcomes_prediction ON apollo_outcomes(prediction_id)")

        conn.commit()
        logger.info("✅ APOLLO tables created/verified")

    except Exception as e:
        logger.error(f"Failed to create APOLLO tables: {e}")
    finally:
        conn.close()


# Initialize tables on import
ensure_apollo_tables()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def save_scan_result(scan_id: str, symbols: List[str], results: List[Dict], vix: float, duration_ms: int):
    """Save scan results to database"""
    conn = get_db_connection()
    if not conn:
        return

    try:
        c = conn.cursor()

        # Determine market regime from VIX
        if vix < 15:
            regime = 'low_vol'
        elif vix < 20:
            regime = 'normal'
        elif vix < 25:
            regime = 'elevated'
        elif vix < 30:
            regime = 'high_vol'
        else:
            regime = 'extreme'

        c.execute('''
            INSERT INTO apollo_scans (scan_id, symbols, results, market_regime, vix_at_scan, scan_duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (scan_id) DO UPDATE SET
                results = EXCLUDED.results,
                market_regime = EXCLUDED.market_regime,
                vix_at_scan = EXCLUDED.vix_at_scan
        ''', (
            scan_id,
            json.dumps(symbols),
            json.dumps(results),
            regime,
            vix,
            duration_ms
        ))

        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save scan: {e}")
    finally:
        conn.close()


def save_pin_risk_analysis(analysis_data: Dict):
    """Save pin risk analysis to database"""
    conn = get_db_connection()
    if not conn:
        return

    try:
        c = conn.cursor()

        c.execute('''
            INSERT INTO apollo_pin_risk_history (
                symbol, spot_price, pin_risk_score, pin_risk_level, gamma_regime,
                max_pain, call_wall, put_wall, flip_point, net_gex,
                distance_to_max_pain_pct, distance_to_flip_pct, long_call_outlook,
                days_to_expiry, is_expiration_day, expected_range_low, expected_range_high,
                expected_range_pct, pin_factors, trading_implications, pin_breakers, summary
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        ''', (
            analysis_data.get('symbol'),
            analysis_data.get('spot_price'),
            analysis_data.get('pin_risk_score'),
            analysis_data.get('pin_risk_level'),
            analysis_data.get('gamma_regime'),
            analysis_data.get('gamma_levels', {}).get('max_pain'),
            analysis_data.get('gamma_levels', {}).get('call_wall'),
            analysis_data.get('gamma_levels', {}).get('put_wall'),
            analysis_data.get('gamma_levels', {}).get('flip_point'),
            analysis_data.get('gamma_levels', {}).get('net_gex'),
            analysis_data.get('distance_to_max_pain_pct'),
            analysis_data.get('distance_to_flip_pct'),
            analysis_data.get('long_call_outlook'),
            analysis_data.get('days_to_weekly_expiry'),
            analysis_data.get('is_expiration_day'),
            analysis_data.get('expected_range_low'),
            analysis_data.get('expected_range_high'),
            analysis_data.get('expected_range_pct'),
            json.dumps(analysis_data.get('pin_factors', [])),
            json.dumps(analysis_data.get('trading_implications', [])),
            json.dumps(analysis_data.get('pin_breakers', [])),
            analysis_data.get('summary')
        ))

        conn.commit()
        logger.info(f"✅ Saved pin risk analysis for {analysis_data.get('symbol')}")

    except Exception as e:
        logger.error(f"Failed to save pin risk analysis: {e}")
    finally:
        conn.close()


def save_prediction(prediction_data: Dict, scan_id: str):
    """Save individual prediction to database"""
    conn = get_db_connection()
    if not conn:
        return

    try:
        import uuid
        c = conn.cursor()

        prediction_id = str(uuid.uuid4())[:12]

        c.execute('''
            INSERT INTO apollo_predictions (
                prediction_id, scan_id, symbol, direction_pred, direction_confidence,
                magnitude_pred, magnitude_confidence, timing_pred, timing_confidence,
                ensemble_confidence, features, strategies, model_version, is_ml_prediction
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            prediction_id,
            scan_id,
            prediction_data.get('symbol'),
            prediction_data.get('prediction', {}).get('direction'),
            prediction_data.get('prediction', {}).get('direction_confidence'),
            prediction_data.get('prediction', {}).get('magnitude'),
            prediction_data.get('prediction', {}).get('magnitude_confidence'),
            prediction_data.get('prediction', {}).get('timing'),
            prediction_data.get('prediction', {}).get('timing_confidence'),
            prediction_data.get('prediction', {}).get('ensemble_confidence'),
            json.dumps(prediction_data.get('features', {})),
            json.dumps(prediction_data.get('strategies', [])),
            prediction_data.get('prediction', {}).get('model_version', '1.0.0'),
            prediction_data.get('prediction', {}).get('is_ml_prediction', False)
        ))

        conn.commit()
        return prediction_id

    except Exception as e:
        logger.error(f"Failed to save prediction: {e}")
        return None
    finally:
        conn.close()


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/scan")
async def apollo_scan(request: ScanRequest):
    """
    Perform APOLLO scan on symbols.

    Returns ML predictions, strategy recommendations, and live data.
    """
    import time
    start_time = time.time()

    try:
        from core.apollo_ml_engine import get_apollo_engine

        engine = get_apollo_engine()
        results = []
        vix_at_scan = 18.0

        for symbol in request.symbols[:5]:  # Limit to 5 symbols
            try:
                scan_result = engine.scan(symbol.upper())
                result_dict = scan_result.to_dict()
                results.append(result_dict)

                # Track VIX
                if scan_result.features and scan_result.features.vix > 0:
                    vix_at_scan = scan_result.features.vix

            except Exception as e:
                logger.error(f"Scan failed for {symbol}: {e}")
                results.append({
                    'symbol': symbol,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })

        duration_ms = int((time.time() - start_time) * 1000)

        # Generate scan ID
        import uuid
        scan_id = str(uuid.uuid4())[:8]

        # Save to database
        save_scan_result(scan_id, request.symbols, results, vix_at_scan, duration_ms)

        # Save individual predictions
        for result in results:
            if 'error' not in result:
                save_prediction(result, scan_id)

        return {
            "success": True,
            "scan_id": scan_id,
            "timestamp": datetime.now().isoformat(),
            "symbols_scanned": len(request.symbols),
            "results": results,
            "vix_at_scan": vix_at_scan,
            "duration_ms": duration_ms,
            "model_version": "1.0.0"
        }

    except ImportError as e:
        logger.error(f"APOLLO engine not available: {e}")
        raise HTTPException(status_code=500, detail="APOLLO ML engine not available")
    except Exception as e:
        logger.error(f"Scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/{scan_id}")
async def get_scan_results(scan_id: str):
    """Get results for a specific scan"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database unavailable")

    try:
        c = conn.cursor()
        c.execute('''
            SELECT scan_id, timestamp, symbols, results, market_regime, vix_at_scan, scan_duration_ms
            FROM apollo_scans WHERE scan_id = %s
        ''', (scan_id,))

        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Scan not found")

        return {
            "success": True,
            "data": {
                "scan_id": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "symbols": json.loads(row[2]) if row[2] else [],
                "results": json.loads(row[3]) if row[3] else [],
                "market_regime": row[4],
                "vix_at_scan": row[5],
                "duration_ms": row[6]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/history")
async def get_scan_history(
    limit: int = Query(default=20, le=100),
    symbol: Optional[str] = None
):
    """Get scan history"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database unavailable")

    try:
        c = conn.cursor()

        if symbol:
            c.execute('''
                SELECT scan_id, timestamp, symbols, market_regime, vix_at_scan, scan_duration_ms
                FROM apollo_scans
                WHERE symbols LIKE %s
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (f'%{symbol}%', limit))
        else:
            c.execute('''
                SELECT scan_id, timestamp, symbols, market_regime, vix_at_scan, scan_duration_ms
                FROM apollo_scans
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (limit,))

        rows = c.fetchall()

        history = []
        for row in rows:
            symbols = json.loads(row[2]) if row[2] else []
            history.append({
                "scan_id": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "symbols": symbols,
                "symbols_count": len(symbols),
                "market_regime": row[3],
                "vix_at_scan": row[4],
                "duration_ms": row[5]
            })

        return {
            "success": True,
            "data": history,
            "count": len(history)
        }

    except Exception as e:
        logger.error(f"Failed to get history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/feedback")
async def record_feedback(request: FeedbackRequest):
    """
    Record actual outcome for a prediction.

    This data is used for model retraining and performance tracking.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database unavailable")

    try:
        import uuid
        c = conn.cursor()

        # Get the original prediction
        c.execute('''
            SELECT prediction_id, direction_pred, magnitude_pred
            FROM apollo_predictions
            WHERE scan_id = %s AND symbol = %s
            ORDER BY timestamp DESC LIMIT 1
        ''', (request.scan_id, request.symbol))

        pred_row = c.fetchone()
        prediction_id = pred_row[0] if pred_row else None
        predicted_direction = pred_row[1] if pred_row else None
        predicted_magnitude = pred_row[2] if pred_row else None

        # Calculate correctness
        direction_correct = (predicted_direction == request.actual_direction) if predicted_direction else None
        magnitude_correct = (predicted_magnitude == request.actual_magnitude) if predicted_magnitude else None

        outcome_id = str(uuid.uuid4())[:12]

        c.execute('''
            INSERT INTO apollo_outcomes (
                outcome_id, prediction_id, symbol, predicted_direction, actual_direction,
                predicted_magnitude, actual_magnitude, actual_return_pct,
                direction_correct, magnitude_correct, strategy_used, strategy_pnl, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            outcome_id,
            prediction_id,
            request.symbol,
            predicted_direction,
            request.actual_direction,
            predicted_magnitude,
            request.actual_magnitude,
            request.actual_return_pct,
            direction_correct,
            magnitude_correct,
            request.strategy_used,
            request.strategy_pnl,
            request.notes
        ))

        conn.commit()

        return {
            "success": True,
            "outcome_id": outcome_id,
            "direction_correct": direction_correct,
            "magnitude_correct": magnitude_correct,
            "message": "Feedback recorded for model learning"
        }

    except Exception as e:
        logger.error(f"Failed to record feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/performance")
async def get_model_performance():
    """Get APOLLO model performance statistics"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database unavailable")

    try:
        c = conn.cursor()

        # Get recent predictions count
        c.execute("SELECT COUNT(*) FROM apollo_predictions WHERE timestamp > NOW() - INTERVAL '30 days'")
        total_predictions = c.fetchone()[0]

        # Get outcomes count
        c.execute("SELECT COUNT(*) FROM apollo_outcomes WHERE timestamp > NOW() - INTERVAL '30 days'")
        total_outcomes = c.fetchone()[0]

        # Calculate direction accuracy (7 days)
        c.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN direction_correct THEN 1 ELSE 0 END) as correct
            FROM apollo_outcomes
            WHERE timestamp > NOW() - INTERVAL '7 days'
        ''')
        row = c.fetchone()
        direction_accuracy_7d = (row[1] / row[0] * 100) if row[0] > 0 else 0

        # Calculate direction accuracy (30 days)
        c.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN direction_correct THEN 1 ELSE 0 END) as correct
            FROM apollo_outcomes
            WHERE timestamp > NOW() - INTERVAL '30 days'
        ''')
        row = c.fetchone()
        direction_accuracy_30d = (row[1] / row[0] * 100) if row[0] > 0 else 0

        # Calculate magnitude accuracy
        c.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN magnitude_correct THEN 1 ELSE 0 END) as correct
            FROM apollo_outcomes
            WHERE timestamp > NOW() - INTERVAL '30 days'
        ''')
        row = c.fetchone()
        magnitude_accuracy_30d = (row[1] / row[0] * 100) if row[0] > 0 else 0

        # Calculate strategy win rate
        c.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN strategy_pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM apollo_outcomes
            WHERE strategy_pnl IS NOT NULL AND timestamp > NOW() - INTERVAL '30 days'
        ''')
        row = c.fetchone()
        strategy_win_rate = (row[1] / row[0] * 100) if row[0] > 0 else 0

        # Get ML engine info
        try:
            from core.apollo_ml_engine import get_apollo_engine
            engine = get_apollo_engine()
            models_loaded = engine.models_loaded
            last_trained = engine.model_performance.get('last_trained')
        except:
            models_loaded = False
            last_trained = None

        return {
            "success": True,
            "data": {
                "total_predictions_30d": total_predictions,
                "total_outcomes_30d": total_outcomes,
                "direction_accuracy_7d": round(direction_accuracy_7d, 1),
                "direction_accuracy_30d": round(direction_accuracy_30d, 1),
                "magnitude_accuracy_30d": round(magnitude_accuracy_30d, 1),
                "strategy_win_rate": round(strategy_win_rate, 1),
                "models_loaded": models_loaded,
                "last_trained": last_trained,
                "model_version": "1.0.0"
            }
        }

    except Exception as e:
        logger.error(f"Failed to get performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/live-quote/{symbol}")
async def get_live_quote(symbol: str):
    """Get live quote from Tradier"""
    try:
        tradier = get_tradier()
        if not tradier:
            raise HTTPException(status_code=503, detail="Tradier not available - check credentials")

        quote = tradier.get_quote(symbol.upper())

        if not quote:
            raise HTTPException(status_code=404, detail=f"No quote found for {symbol}")

        return {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "bid": quote.get('bid'),
                "ask": quote.get('ask'),
                "last": quote.get('last'),
                "open": quote.get('open'),
                "high": quote.get('high'),
                "low": quote.get('low'),
                "close": quote.get('close'),
                "volume": quote.get('volume'),
                "average_volume": quote.get('average_volume'),
                "change": quote.get('change'),
                "change_pct": quote.get('change_percentage'),
                "timestamp": datetime.now().isoformat(),
                "source": "tradier"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batch-quotes")
async def get_batch_quotes(symbols: str = "SPY,QQQ,AAPL,NVDA,TSLA,AMZN,META,GOOGL,MSFT,AMD"):
    """
    Get live quotes for multiple symbols in a single request.

    Args:
        symbols: Comma-separated list of stock symbols

    Returns:
        List of quotes with price and change data
    """
    try:
        tradier = get_tradier()
        if not tradier:
            raise HTTPException(status_code=503, detail="Tradier not available - check credentials")

        # Make single API call with all symbols
        response = tradier._make_request('GET', 'markets/quotes', params={'symbols': symbols.upper()})
        quotes_data = response.get('quotes', {})

        quotes = []
        quote_list = quotes_data.get('quote', [])

        # Handle single quote vs multiple
        if isinstance(quote_list, dict):
            quote_list = [quote_list]

        for quote in quote_list:
            if quote:
                quotes.append({
                    "symbol": quote.get('symbol'),
                    "price": quote.get('last') or quote.get('close'),
                    "change": quote.get('change', 0),
                    "change_pct": quote.get('change_percentage', 0),
                    "bid": quote.get('bid'),
                    "ask": quote.get('ask'),
                    "volume": quote.get('volume'),
                    "open": quote.get('open'),
                    "high": quote.get('high'),
                    "low": quote.get('low'),
                })

        return {
            "success": True,
            "data": quotes,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get batch quotes: {e}")
        # Return fallback data if API fails
        symbol_list = symbols.upper().split(',')
        fallback = [{"symbol": s.strip(), "price": 0, "change": 0, "change_pct": 0} for s in symbol_list]
        return {
            "success": False,
            "data": fallback,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/options-chain/{symbol}")
async def get_options_chain(
    symbol: str,
    expiration: Optional[str] = None
):
    """Get live options chain from Tradier"""
    try:
        tradier = get_tradier()
        if not tradier:
            raise HTTPException(status_code=503, detail="Tradier not available - check credentials")

        # Get expirations if not specified
        expirations = tradier.get_option_expirations(symbol.upper())
        if not expirations:
            raise HTTPException(status_code=404, detail=f"No options found for {symbol}")

        target_expiration = expiration or expirations[0]

        # Get chain
        chain = tradier.get_option_chain(symbol.upper(), target_expiration)

        if not chain:
            raise HTTPException(status_code=404, detail=f"No chain found for {symbol} {target_expiration}")

        # Format chain data
        calls = []
        puts = []

        for contract in chain:
            formatted = {
                'symbol': contract.get('symbol'),
                'strike': contract.get('strike'),
                'bid': contract.get('bid'),
                'ask': contract.get('ask'),
                'last': contract.get('last'),
                'volume': contract.get('volume'),
                'open_interest': contract.get('open_interest'),
                'greeks': contract.get('greeks', {})
            }

            if contract.get('option_type') == 'call':
                calls.append(formatted)
            else:
                puts.append(formatted)

        # Sort by strike
        calls.sort(key=lambda x: x.get('strike', 0))
        puts.sort(key=lambda x: x.get('strike', 0))

        return {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "expiration": target_expiration,
                "available_expirations": expirations[:10],
                "calls": calls,
                "puts": puts,
                "timestamp": datetime.now().isoformat(),
                "source": "tradier"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get options chain: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/features/{symbol}")
async def get_features(symbol: str):
    """Get extracted features for a symbol (for debugging/analysis)"""
    try:
        from core.apollo_ml_engine import get_apollo_engine

        engine = get_apollo_engine()
        features = engine.extract_features(symbol.upper())

        return {
            "success": True,
            "data": features.to_dict(),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get features: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pin-risk/{symbol}")
async def get_pin_risk(symbol: str):
    """
    Get comprehensive pin risk analysis for a symbol.

    Analyzes gamma exposure, max pain, and dealer positioning to assess
    the probability of price pinning.

    Returns:
        - Pin risk score (0-100)
        - Gamma regime (positive/negative/neutral)
        - Key levels (max pain, walls, flip point)
        - Trading implications for different strategies
        - What would break the pin pattern
    """
    try:
        from core.pin_risk_analyzer import get_pin_risk_analyzer

        analyzer = get_pin_risk_analyzer()
        analysis = analyzer.analyze(symbol.upper())
        analysis_dict = analysis.to_dict()

        # Save to database for historical tracking
        save_pin_risk_analysis(analysis_dict)

        return {
            "success": True,
            "data": analysis_dict,
            "timestamp": datetime.now().isoformat()
        }

    except ImportError as e:
        logger.error(f"Pin risk analyzer not available: {e}")
        raise HTTPException(status_code=500, detail="Pin risk analyzer not available")
    except Exception as e:
        logger.error(f"Pin risk analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pin-risk-batch")
async def get_pin_risk_batch(symbols: str = "SPY,QQQ,NVDA,AAPL,TSLA"):
    """
    Get pin risk analysis for multiple symbols.

    Args:
        symbols: Comma-separated list of stock symbols

    Returns:
        List of pin risk analyses sorted by risk score (highest first)
    """
    try:
        from core.pin_risk_analyzer import get_pin_risk_analyzer

        analyzer = get_pin_risk_analyzer()
        symbol_list = [s.strip().upper() for s in symbols.split(',')][:10]  # Limit to 10

        results = []
        for sym in symbol_list:
            try:
                analysis = analyzer.analyze(sym)
                results.append({
                    'symbol': sym,
                    'pin_risk_score': analysis.pin_risk_score,
                    'pin_risk_level': analysis.pin_risk_level.value,
                    'gamma_regime': analysis.gamma_regime.value,
                    'spot_price': analysis.spot_price,
                    'max_pain': analysis.gamma_levels.max_pain,
                    'long_call_outlook': analysis.long_call_outlook,
                    'summary': analysis.summary
                })
            except Exception as e:
                logger.error(f"Pin risk failed for {sym}: {e}")
                results.append({
                    'symbol': sym,
                    'error': str(e)
                })

        # Sort by pin risk score (highest first)
        results.sort(key=lambda x: x.get('pin_risk_score', 0), reverse=True)

        return {
            "success": True,
            "data": results,
            "count": len(results),
            "timestamp": datetime.now().isoformat()
        }

    except ImportError as e:
        logger.error(f"Pin risk analyzer not available: {e}")
        raise HTTPException(status_code=500, detail="Pin risk analyzer not available")
    except Exception as e:
        logger.error(f"Batch pin risk analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pin-risk-history/{symbol}")
async def get_pin_risk_history(
    symbol: str,
    limit: int = Query(default=50, le=200),
    days: int = Query(default=7, le=30)
):
    """
    Get historical pin risk data for a symbol.

    Args:
        symbol: Stock symbol
        limit: Maximum number of records (default 50)
        days: Number of days to look back (default 7)

    Returns:
        Historical pin risk scores and levels
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database unavailable")

    try:
        c = conn.cursor()
        c.execute('''
            SELECT
                timestamp, spot_price, pin_risk_score, pin_risk_level,
                gamma_regime, max_pain, call_wall, put_wall, flip_point,
                long_call_outlook, days_to_expiry, expected_range_pct, summary
            FROM apollo_pin_risk_history
            WHERE symbol = %s
            AND timestamp > NOW() - INTERVAL '%s days'
            ORDER BY timestamp DESC
            LIMIT %s
        ''', (symbol.upper(), days, limit))

        rows = c.fetchall()

        history = []
        for row in rows:
            history.append({
                "timestamp": row[0].isoformat() if row[0] else None,
                "spot_price": row[1],
                "pin_risk_score": row[2],
                "pin_risk_level": row[3],
                "gamma_regime": row[4],
                "max_pain": row[5],
                "call_wall": row[6],
                "put_wall": row[7],
                "flip_point": row[8],
                "long_call_outlook": row[9],
                "days_to_expiry": row[10],
                "expected_range_pct": row[11],
                "summary": row[12]
            })

        return {
            "success": True,
            "symbol": symbol.upper(),
            "data": history,
            "count": len(history),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get pin risk history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/train")
async def trigger_training():
    """
    Trigger model retraining using recent outcome data.

    This should be called periodically (e.g., weekly) to update models.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database unavailable")

    try:
        import pandas as pd
        from core.apollo_ml_engine import get_apollo_engine

        c = conn.cursor()

        # Get training data (predictions with outcomes)
        c.execute('''
            SELECT
                p.features,
                o.actual_direction,
                o.actual_magnitude,
                CASE
                    WHEN ABS(o.actual_return_pct) < 0.5 THEN 'immediate'
                    WHEN ABS(o.actual_return_pct) < 1.5 THEN '1_day'
                    ELSE '3_day'
                END as actual_timing
            FROM apollo_predictions p
            JOIN apollo_outcomes o ON p.prediction_id = o.prediction_id
            WHERE o.actual_direction IS NOT NULL
            AND o.actual_magnitude IS NOT NULL
        ''')

        rows = c.fetchall()

        if len(rows) < 100:
            return {
                "success": False,
                "message": f"Insufficient training data ({len(rows)} samples, need 100+)"
            }

        # Prepare training dataframe
        training_data = []
        for row in rows:
            features = json.loads(row[0]) if row[0] else {}
            features['actual_direction'] = row[1]
            features['actual_magnitude'] = row[2]
            features['actual_timing'] = row[3]
            training_data.append(features)

        df = pd.DataFrame(training_data)

        # Train models
        engine = get_apollo_engine()
        engine.train_models(df)

        return {
            "success": True,
            "message": f"Models trained on {len(rows)} samples",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/track-outcomes")
async def trigger_outcome_tracking(
    min_age_hours: int = Query(default=24, ge=1, le=168, description="Minimum age of predictions to track (hours)"),
    max_age_days: int = Query(default=7, ge=1, le=30, description="Maximum age of predictions to track (days)")
):
    """
    Manually trigger Apollo outcome tracking.

    This finds predictions older than min_age_hours that don't have outcomes yet,
    fetches the actual price data, and records whether predictions were correct.

    This endpoint was added to fix the issue where Apollo performance 30-day
    metrics weren't showing any data because outcomes were never tracked.
    """
    try:
        from core.apollo_outcome_tracker import track_apollo_outcomes

        results = track_apollo_outcomes(
            min_age_hours=min_age_hours,
            max_age_days=max_age_days
        )

        return {
            "success": True,
            "data": {
                "predictions_found": results.get('predictions_found', 0),
                "outcomes_recorded": results.get('outcomes_recorded', 0),
                "direction_accuracy": results.get('direction_accuracy', 0),
                "magnitude_accuracy": results.get('magnitude_accuracy', 0),
                "symbols_processed": results.get('symbols_processed', []),
                "errors": results.get('errors', 0)
            },
            "message": f"Tracked {results.get('outcomes_recorded', 0)} outcomes",
            "timestamp": datetime.now().isoformat()
        }

    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Outcome tracking module not available: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Outcome tracking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tracking-status")
async def get_tracking_status():
    """
    Get Apollo outcome tracking status.

    Shows how many predictions have been tracked and overall accuracy.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database unavailable")

    try:
        c = conn.cursor()

        # Total predictions
        c.execute("SELECT COUNT(*) FROM apollo_predictions")
        total_predictions = c.fetchone()[0]

        # Predictions with outcomes
        c.execute("""
            SELECT COUNT(DISTINCT p.prediction_id)
            FROM apollo_predictions p
            JOIN apollo_outcomes o ON p.prediction_id = o.prediction_id
        """)
        predictions_with_outcomes = c.fetchone()[0]

        # Predictions awaiting tracking (>24h old without outcome)
        c.execute("""
            SELECT COUNT(*)
            FROM apollo_predictions p
            LEFT JOIN apollo_outcomes o ON p.prediction_id = o.prediction_id
            WHERE o.id IS NULL
              AND p.timestamp < NOW() - INTERVAL '24 hours'
              AND p.timestamp > NOW() - INTERVAL '7 days'
        """)
        awaiting_tracking = c.fetchone()[0]

        # Recent outcomes (last 30 days)
        c.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN direction_correct THEN 1 ELSE 0 END) as direction_correct,
                SUM(CASE WHEN magnitude_correct THEN 1 ELSE 0 END) as magnitude_correct
            FROM apollo_outcomes
            WHERE timestamp > NOW() - INTERVAL '30 days'
        """)
        row = c.fetchone()
        recent_outcomes = row[0] or 0
        direction_correct = row[1] or 0
        magnitude_correct = row[2] or 0

        return {
            "success": True,
            "data": {
                "total_predictions": total_predictions,
                "predictions_with_outcomes": predictions_with_outcomes,
                "tracking_rate": round((predictions_with_outcomes / total_predictions * 100), 1) if total_predictions > 0 else 0,
                "awaiting_tracking": awaiting_tracking,
                "recent_outcomes_30d": recent_outcomes,
                "direction_accuracy_30d": round((direction_correct / recent_outcomes * 100), 1) if recent_outcomes > 0 else 0,
                "magnitude_accuracy_30d": round((magnitude_correct / recent_outcomes * 100), 1) if recent_outcomes > 0 else 0,
                "needs_attention": awaiting_tracking > 0
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get tracking status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
