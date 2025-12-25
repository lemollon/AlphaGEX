"""
Shared test fixtures for AlphaGEX test suite.

Provides common mocks for:
- Market data (spot prices, VIX, options chains)
- Database connections
- API clients
- Trading strategies

Run tests with: pytest -v
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# MARKET DATA FIXTURES
# =============================================================================

@pytest.fixture
def mock_spot_price():
    """Current SPY spot price"""
    return 585.50


@pytest.fixture
def mock_spx_spot_price():
    """Current SPX spot price"""
    return 5855.00


@pytest.fixture
def mock_vix():
    """Current VIX value"""
    return 15.5


@pytest.fixture
def mock_market_data(mock_spot_price, mock_vix):
    """Complete market data snapshot"""
    return {
        "symbol": "SPY",
        "spot_price": mock_spot_price,
        "vix": mock_vix,
        "iv_rank": 45.0,
        "iv_percentile": 52.0,
        "gamma_exposure": 1_500_000_000,
        "net_gex": 1.5,  # billions
        "call_wall": 590.0,
        "put_wall": 580.0,
        "gamma_flip": 583.0,
        "timestamp": datetime.now(CENTRAL_TZ),
    }


@pytest.fixture
def mock_spx_market_data(mock_spx_spot_price, mock_vix):
    """SPX market data snapshot"""
    return {
        "symbol": "SPX",
        "spot_price": mock_spx_spot_price,
        "vix": mock_vix,
        "iv_rank": 45.0,
        "iv_percentile": 52.0,
        "gamma_exposure": 15_000_000_000,
        "net_gex": 15.0,
        "call_wall": 5900.0,
        "put_wall": 5800.0,
        "gamma_flip": 5830.0,
        "timestamp": datetime.now(CENTRAL_TZ),
    }


# =============================================================================
# OPTIONS CHAIN FIXTURES
# =============================================================================

@pytest.fixture
def mock_option_chain():
    """Mock options chain data with Greeks"""
    base_strike = 580.0
    chains = []

    for i in range(-10, 11):
        strike = base_strike + (i * 5)
        # Simulate realistic gamma distribution
        distance_from_atm = abs(i)
        gamma = max(0.001, 0.08 - (distance_from_atm * 0.007))

        # Call option
        chains.append({
            "symbol": f"SPY{strike:.0f}C",
            "strike": strike,
            "option_type": "call",
            "expiration": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "bid": 2.50 + (5 - i) * 0.5,
            "ask": 2.60 + (5 - i) * 0.5,
            "last": 2.55 + (5 - i) * 0.5,
            "volume": 1000 + abs(i) * 100,
            "open_interest": 5000 + abs(i) * 500,
            "gamma": gamma,
            "delta": 0.5 - (i * 0.05),
            "theta": -0.05,
            "vega": 0.15,
            "iv": 0.18 + abs(i) * 0.01,
        })

        # Put option
        chains.append({
            "symbol": f"SPY{strike:.0f}P",
            "strike": strike,
            "option_type": "put",
            "expiration": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "bid": 2.50 + (i + 5) * 0.5,
            "ask": 2.60 + (i + 5) * 0.5,
            "last": 2.55 + (i + 5) * 0.5,
            "volume": 800 + abs(i) * 80,
            "open_interest": 4000 + abs(i) * 400,
            "gamma": gamma,
            "delta": -0.5 + (i * 0.05),
            "theta": -0.05,
            "vega": 0.15,
            "iv": 0.18 + abs(i) * 0.01,
        })

    return chains


@pytest.fixture
def mock_spx_option_chain():
    """Mock SPX options chain data"""
    base_strike = 5850.0
    chains = []

    for i in range(-10, 11):
        strike = base_strike + (i * 25)
        distance_from_atm = abs(i)
        gamma = max(0.0001, 0.008 - (distance_from_atm * 0.0007))

        chains.append({
            "symbol": f"SPX{strike:.0f}C",
            "strike": strike,
            "option_type": "call",
            "expiration": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "bid": 25.0 + (5 - i) * 5,
            "ask": 26.0 + (5 - i) * 5,
            "open_interest": 10000 + abs(i) * 1000,
            "gamma": gamma,
            "delta": 0.5 - (i * 0.05),
            "iv": 0.15,
        })

        chains.append({
            "symbol": f"SPX{strike:.0f}P",
            "strike": strike,
            "option_type": "put",
            "expiration": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "bid": 25.0 + (i + 5) * 5,
            "ask": 26.0 + (i + 5) * 5,
            "open_interest": 8000 + abs(i) * 800,
            "gamma": gamma,
            "delta": -0.5 + (i * 0.05),
            "iv": 0.15,
        })

    return chains


# =============================================================================
# GEX FIXTURES
# =============================================================================

@pytest.fixture
def mock_gex_data():
    """Mock GEX calculation result"""
    return {
        "symbol": "SPY",
        "spot_price": 585.50,
        "net_gex": 1_500_000_000,
        "call_gex": 2_000_000_000,
        "put_gex": -500_000_000,
        "call_wall": 590.0,
        "put_wall": 580.0,
        "gamma_flip": 583.0,
        "max_pain": 585.0,
        "data_source": "calculated",
        "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
    }


@pytest.fixture
def mock_gex_levels():
    """Mock GEX levels by strike"""
    return [
        {"strike": 575.0, "net_gamma": -200_000_000, "call_gamma": 50_000_000, "put_gamma": -250_000_000},
        {"strike": 580.0, "net_gamma": 100_000_000, "call_gamma": 300_000_000, "put_gamma": -200_000_000},
        {"strike": 585.0, "net_gamma": 500_000_000, "call_gamma": 600_000_000, "put_gamma": -100_000_000},
        {"strike": 590.0, "net_gamma": 800_000_000, "call_gamma": 850_000_000, "put_gamma": -50_000_000},
        {"strike": 595.0, "net_gamma": 300_000_000, "call_gamma": 350_000_000, "put_gamma": -50_000_000},
    ]


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

@pytest.fixture
def mock_db_connection():
    """Mock database connection"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    return mock_conn


@pytest.fixture
def mock_db_cursor(mock_db_connection):
    """Mock database cursor"""
    return mock_db_connection.cursor()


# =============================================================================
# TRADING FIXTURES
# =============================================================================

@pytest.fixture
def mock_position():
    """Mock trading position"""
    return {
        "id": 1,
        "symbol": "SPY",
        "strategy": "iron_condor",
        "entry_time": datetime.now(CENTRAL_TZ) - timedelta(hours=2),
        "entry_price": 2.50,
        "current_price": 2.30,
        "quantity": 10,
        "pnl": 200.0,
        "pnl_pct": 8.0,
        "status": "open",
        "legs": [
            {"strike": 575, "type": "put", "side": "sell"},
            {"strike": 570, "type": "put", "side": "buy"},
            {"strike": 595, "type": "call", "side": "sell"},
            {"strike": 600, "type": "call", "side": "buy"},
        ]
    }


@pytest.fixture
def mock_iron_condor_position():
    """Mock iron condor position"""
    return {
        "id": 1,
        "symbol": "SPX",
        "strategy": "iron_condor",
        "entry_time": datetime.now(CENTRAL_TZ) - timedelta(hours=1),
        "credit_received": 3.50,
        "max_loss": 6.50,
        "current_value": 2.80,
        "pnl": 70.0,
        "quantity": 5,
        "status": "open",
        "short_put": 5800,
        "long_put": 5790,
        "short_call": 5900,
        "long_call": 5910,
        "expiration": datetime.now().strftime("%Y-%m-%d"),
    }


@pytest.fixture
def mock_directional_spread():
    """Mock directional spread position"""
    return {
        "id": 2,
        "symbol": "SPX",
        "strategy": "bull_call_spread",
        "direction": "bullish",
        "entry_time": datetime.now(CENTRAL_TZ) - timedelta(hours=1),
        "debit_paid": 5.00,
        "max_profit": 5.00,
        "current_value": 6.50,
        "pnl": 150.0,
        "quantity": 3,
        "status": "open",
        "long_strike": 5850,
        "short_strike": 5860,
        "expiration": datetime.now().strftime("%Y-%m-%d"),
    }


@pytest.fixture
def mock_wheel_position():
    """Mock wheel strategy position"""
    return {
        "id": 3,
        "symbol": "SPY",
        "strategy": "wheel",
        "phase": "cash_secured_put",
        "entry_time": datetime.now(CENTRAL_TZ) - timedelta(days=5),
        "strike": 580.0,
        "premium_collected": 2.50,
        "expiration": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "status": "open",
        "quantity": 1,
    }


# =============================================================================
# PERFORMANCE FIXTURES
# =============================================================================

@pytest.fixture
def mock_performance_metrics():
    """Mock trading performance metrics"""
    return {
        "total_pnl": 15000.0,
        "total_trades": 150,
        "winning_trades": 105,
        "losing_trades": 45,
        "win_rate": 70.0,
        "avg_win": 250.0,
        "avg_loss": -150.0,
        "profit_factor": 2.33,
        "sharpe_ratio": 1.85,
        "sortino_ratio": 2.45,
        "max_drawdown": -5.2,
        "max_drawdown_duration_days": 12,
        "current_streak": 3,
        "best_trade": 1500.0,
        "worst_trade": -800.0,
    }


@pytest.fixture
def mock_equity_curve():
    """Mock equity curve data"""
    base_value = 100000
    curve = []

    for i in range(30):
        date = datetime.now(CENTRAL_TZ) - timedelta(days=29-i)
        # Simulate gradual growth with some volatility
        value = base_value * (1 + 0.002 * i + 0.01 * (i % 3 - 1))
        curve.append({
            "date": date.strftime("%Y-%m-%d"),
            "equity": value,
            "daily_pnl": value * 0.002 if i > 0 else 0,
            "drawdown": -abs((i % 5) * 0.5),
        })

    return curve


# =============================================================================
# REGIME FIXTURES
# =============================================================================

@pytest.fixture
def mock_regime_classification():
    """Mock market regime classification"""
    return {
        "volatility_regime": "LOW",
        "gamma_regime": "POSITIVE",
        "trend_regime": "BULLISH",
        "iv_rank": 35.0,
        "iv_percentile": 40.0,
        "vix": 14.5,
        "recommended_action": "SELL_PREMIUM",
        "confidence": 0.85,
        "strategies": ["iron_condor", "cash_secured_put", "covered_call"],
    }


# =============================================================================
# AI/LLM FIXTURES
# =============================================================================

@pytest.fixture
def mock_llm_response():
    """Mock LLM response"""
    return {
        "content": "Based on current market conditions with positive gamma and low VIX, "
                   "I recommend selling premium through iron condors. "
                   "The put wall at 580 provides strong support.",
        "model": "gpt-4",
        "tokens_used": 150,
    }


@pytest.fixture
def mock_ai_recommendation():
    """Mock AI trade recommendation"""
    return {
        "action": "SELL_IRON_CONDOR",
        "confidence": 0.82,
        "reasoning": "Positive gamma regime with low IV rank suggests mean reversion.",
        "entry": {
            "short_put": 5800,
            "long_put": 5790,
            "short_call": 5900,
            "long_call": 5910,
        },
        "risk_reward": 1.5,
        "probability_of_profit": 0.72,
    }


# =============================================================================
# HEARTBEAT FIXTURES
# =============================================================================

@pytest.fixture
def mock_bot_heartbeat():
    """Mock bot heartbeat data"""
    return {
        "last_scan": datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT'),
        "last_scan_iso": datetime.now(CENTRAL_TZ).isoformat(),
        "status": "RUNNING",
        "scan_count_today": 42,
        "details": {
            "last_trade": None,
            "positions_open": 2,
            "daily_pnl": 350.0,
        }
    }


# =============================================================================
# PSYCHOLOGY FIXTURES
# =============================================================================

@pytest.fixture
def mock_psychology_assessment():
    """Mock psychology/emotional assessment"""
    return {
        "emotional_state": "NEUTRAL",
        "risk_tolerance": "MODERATE",
        "traps_detected": [],
        "warnings": [],
        "recommendations": [
            "Current emotional state is conducive to trading.",
            "Stick to your position sizing rules.",
        ],
        "score": 75,
    }


@pytest.fixture
def mock_psychology_trap():
    """Mock detected psychology trap"""
    return {
        "trap_type": "REVENGE_TRADING",
        "severity": "HIGH",
        "trigger": "3 consecutive losses detected",
        "recommendation": "Take a 30-minute break before next trade",
        "detected_at": datetime.now(CENTRAL_TZ).isoformat(),
    }


# =============================================================================
# API CLIENT FIXTURES
# =============================================================================

@pytest.fixture
def mock_tradier_client():
    """Mock Tradier API client"""
    client = MagicMock()
    client.get_quotes.return_value = {"SPY": {"last": 585.50, "bid": 585.48, "ask": 585.52}}
    client.get_option_chain.return_value = []
    client.place_order.return_value = {"order_id": "12345", "status": "filled"}
    return client


@pytest.fixture
def mock_polygon_client():
    """Mock Polygon API client"""
    client = MagicMock()
    client.get_snapshot.return_value = {"ticker": "SPY", "last_trade": {"p": 585.50}}
    client.get_options_chain.return_value = []
    return client


# =============================================================================
# FASTAPI TEST CLIENT FIXTURE
# =============================================================================

@pytest.fixture
def test_client():
    """FastAPI test client"""
    from fastapi.testclient import TestClient
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
        from main import app
        return TestClient(app)
    except ImportError:
        pytest.skip("Backend not available")


# =============================================================================
# TIME FIXTURES
# =============================================================================

@pytest.fixture
def mock_market_open():
    """Mock time during market hours (10:30 AM CT)"""
    return datetime.now(CENTRAL_TZ).replace(hour=10, minute=30, second=0, microsecond=0)


@pytest.fixture
def mock_market_close():
    """Mock time at market close (3:00 PM CT)"""
    return datetime.now(CENTRAL_TZ).replace(hour=15, minute=0, second=0, microsecond=0)


@pytest.fixture
def mock_after_hours():
    """Mock time after market hours (5:00 PM CT)"""
    return datetime.now(CENTRAL_TZ).replace(hour=17, minute=0, second=0, microsecond=0)


# =============================================================================
# BACKTEST FIXTURES
# =============================================================================

@pytest.fixture
def mock_backtest_result():
    """Mock backtest result"""
    return {
        "strategy": "iron_condor",
        "start_date": "2024-01-01",
        "end_date": "2024-12-01",
        "initial_capital": 100000,
        "final_capital": 125000,
        "total_return": 25.0,
        "cagr": 27.5,
        "sharpe_ratio": 1.95,
        "sortino_ratio": 2.65,
        "max_drawdown": -8.5,
        "win_rate": 72.0,
        "total_trades": 200,
        "profit_factor": 2.1,
        "avg_trade_duration_days": 1.5,
    }


@pytest.fixture
def mock_backtest_trades():
    """Mock backtest trade history"""
    trades = []
    for i in range(10):
        trades.append({
            "id": i + 1,
            "entry_date": f"2024-{(i % 12) + 1:02d}-15",
            "exit_date": f"2024-{(i % 12) + 1:02d}-16",
            "pnl": 150 if i % 3 != 0 else -100,
            "pnl_pct": 1.5 if i % 3 != 0 else -1.0,
            "strategy": "iron_condor",
        })
    return trades
