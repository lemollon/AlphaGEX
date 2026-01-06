"""
PROMETHEUS Outcome Tracker
===========================

Tracks trade outcomes for Prometheus ML learning.

STANDALONE OPERATION:
This module works independently without requiring ATLAS, HERMES, or any other
trading bot. Use the API endpoints or these classes directly:

Via API (recommended):
- POST /api/prometheus/record-entry - Record a new trade
- POST /api/prometheus/record-outcome - Record trade result
- POST /api/prometheus/quick-predict - Get prediction + optionally record entry

Via Python:
```python
from trading.prometheus_outcome_tracker import (
    get_prometheus_outcome_tracker,
    record_spx_wheel_entry,
    record_spx_wheel_outcome
)

# Record a trade entry
record_spx_wheel_entry(
    trade_id="my-trade-001",
    strike=5800.0,
    underlying_price=5850.0,
    dte=7,
    delta=-0.15,
    premium=5.50
)

# Later, record the outcome
record_spx_wheel_outcome(
    trade_id="my-trade-001",
    is_win=True,
    pnl=550.0,
    settlement_price=5870.0
)
```

This module provides:
1. Trade entry recording when positions are opened
2. Outcome recording when positions are closed
3. Optional integration with trading bots (ATLAS, HERMES, etc.)
4. Automatic feature extraction from market data

Author: AlphaGEX Quant
"""

import os
import sys
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")

logger = logging.getLogger(__name__)

# Prometheus imports
try:
    from trading.prometheus_ml import (
        PrometheusFeatures,
        PrometheusOutcome,
        get_prometheus_trainer,
        get_prometheus_logger,
        LogType,
        DB_AVAILABLE
    )
    PROMETHEUS_AVAILABLE = True
except ImportError as e:
    PROMETHEUS_AVAILABLE = False
    logger.warning(f"Prometheus not available: {e}")

# Database
try:
    from database_adapter import get_connection
except ImportError:
    get_connection = None


class PrometheusOutcomeTracker:
    """
    Tracks trade outcomes for Prometheus ML training.

    Provides automatic integration with trading systems to record:
    - Trade entries with market features
    - Trade outcomes (win/loss/P&L)
    - Feature extraction from current market data
    """

    def __init__(self):
        self._pending_trades: Dict[str, PrometheusFeatures] = {}
        self._logger = get_prometheus_logger() if PROMETHEUS_AVAILABLE else None

    def record_trade_entry(
        self,
        trade_id: str,
        strike: float,
        underlying_price: float,
        dte: int,
        delta: float,
        premium: float,
        market_data: Dict = None
    ) -> bool:
        """
        Record a new trade entry for outcome tracking.

        Args:
            trade_id: Unique trade identifier
            strike: Put strike price
            underlying_price: Current SPX price
            dte: Days to expiration
            delta: Option delta
            premium: Premium received per contract
            market_data: Optional dict with VIX, GEX, etc.

        Returns:
            True if recorded successfully
        """
        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus not available for trade recording")
            return False

        try:
            # Extract or default market features
            market_data = market_data or {}

            features = PrometheusFeatures(
                trade_date=datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'),
                strike=strike,
                underlying_price=underlying_price,
                dte=dte,
                delta=delta,
                premium=premium,
                iv=market_data.get('iv', 0.18),
                iv_rank=market_data.get('iv_rank', 50.0),
                vix=market_data.get('vix', 18.0),
                vix_percentile=market_data.get('vix_percentile', 50.0),
                vix_term_structure=market_data.get('vix_term_structure', -1.0),
                put_wall_distance_pct=market_data.get('put_wall_distance_pct', 3.0),
                call_wall_distance_pct=market_data.get('call_wall_distance_pct', 3.0),
                net_gex=market_data.get('net_gex', 5e9),
                spx_20d_return=market_data.get('spx_20d_return', 0.0),
                spx_5d_return=market_data.get('spx_5d_return', 0.0),
                spx_distance_from_high=market_data.get('spx_distance_from_high', 1.0),
                premium_to_strike_pct=(premium / strike) * 100 if strike > 0 else 0,
                annualized_return=self._calculate_annualized_return(premium, strike, dte)
            )

            self._pending_trades[trade_id] = features
            self._save_entry_to_db(trade_id, features)

            if self._logger:
                self._logger.log(
                    LogType.INFO,
                    "TRADE_ENTRY_RECORDED",
                    f"Trade {trade_id} recorded for outcome tracking",
                    trade_id=trade_id,
                    details={
                        'strike': strike,
                        'underlying': underlying_price,
                        'dte': dte,
                        'premium': premium
                    }
                )

            logger.info(f"Trade entry recorded: {trade_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to record trade entry: {e}")
            return False

    def record_trade_outcome(
        self,
        trade_id: str,
        outcome: str,  # 'WIN' or 'LOSS'
        pnl: float,
        settlement_price: float = None,
        max_drawdown: float = 0
    ) -> Optional[PrometheusOutcome]:
        """
        Record the outcome of a trade.

        Args:
            trade_id: Trade identifier
            outcome: 'WIN' (expired OTM) or 'LOSS' (ITM/assigned)
            pnl: Actual P&L in dollars
            settlement_price: SPX price at expiration
            max_drawdown: Worst unrealized P&L during trade

        Returns:
            PrometheusOutcome if successful, None otherwise
        """
        if not PROMETHEUS_AVAILABLE:
            return None

        try:
            # Get features from memory or database
            if trade_id in self._pending_trades:
                features = self._pending_trades.pop(trade_id)
            else:
                features = self._load_entry_from_db(trade_id)

            if features is None:
                logger.warning(f"No features found for trade {trade_id}")
                return None

            outcome_obj = PrometheusOutcome(
                trade_id=trade_id,
                features=features,
                outcome=outcome,
                pnl=pnl,
                max_drawdown=max_drawdown,
                settlement_price=settlement_price or features.underlying_price
            )

            # Update in database
            self._update_outcome_in_db(trade_id, outcome, pnl, settlement_price, max_drawdown)

            if self._logger:
                self._logger.log(
                    LogType.OUTCOME,
                    "TRADE_OUTCOME_RECORDED",
                    f"Trade {trade_id}: {outcome}, P&L: ${pnl:,.2f}",
                    trade_id=trade_id,
                    details={
                        'outcome': outcome,
                        'pnl': pnl,
                        'settlement_price': settlement_price
                    }
                )

            logger.info(f"Trade outcome recorded: {trade_id} - {outcome} (${pnl:,.2f})")
            return outcome_obj

        except Exception as e:
            logger.error(f"Failed to record trade outcome: {e}")
            return None

    def get_current_market_features(self) -> Dict:
        """
        Get current market features for trade entry.

        Fetches VIX, GEX, and other market data from the system.

        Returns:
            Dict of current market features
        """
        features = {
            'vix': 18.0,
            'vix_percentile': 50.0,
            'vix_term_structure': -1.0,
            'iv_rank': 50.0,
            'iv': 0.18,
            'net_gex': 5e9,
            'put_wall_distance_pct': 3.0,
            'call_wall_distance_pct': 3.0,
            'spx_20d_return': 0.0,
            'spx_5d_return': 0.0,
            'spx_distance_from_high': 1.0
        }

        # Try to get live data
        try:
            from core_classes_and_engines import TradingVolatilityAPI
            api = TradingVolatilityAPI()

            # Get VIX
            try:
                vix_data = api.get_vix_current()
                if vix_data:
                    features['vix'] = vix_data.get('vix_spot', 18.0)
                    features['vix_percentile'] = vix_data.get('percentile', 50.0)
                    features['vix_term_structure'] = vix_data.get('term_structure', -1.0)
            except:
                pass

            # Get GEX data
            try:
                gex_data = api.get_gex_analysis('SPX')
                if gex_data and 'data' in gex_data:
                    data = gex_data['data']
                    features['net_gex'] = data.get('total_gex', 5e9)
                    features['put_wall_distance_pct'] = data.get('put_wall_distance_pct', 3.0)
                    features['call_wall_distance_pct'] = data.get('call_wall_distance_pct', 3.0)
            except:
                pass

        except ImportError:
            pass

        return features

    def _calculate_annualized_return(self, premium: float, strike: float, dte: int) -> float:
        """Calculate annualized return from premium"""
        if strike <= 0 or dte <= 0:
            return 0.0
        pct_return = (premium / strike) * 100
        annualized = pct_return * (365 / max(dte, 0.5))
        return min(annualized, 500.0)  # Cap at 500%

    def _save_entry_to_db(self, trade_id: str, features: PrometheusFeatures):
        """Save trade entry to database"""
        if not DB_AVAILABLE or get_connection is None:
            return

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO spx_wheel_ml_outcomes (
                    trade_id, trade_date, strike, underlying_price, dte, delta, premium,
                    iv, iv_rank, vix, vix_percentile, vix_term_structure,
                    put_wall_distance_pct, call_wall_distance_pct, net_gex,
                    spx_20d_return, spx_5d_return, spx_distance_from_high,
                    premium_to_strike_pct, annualized_return
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_id) DO NOTHING
            ''', (
                trade_id, features.trade_date, features.strike, features.underlying_price,
                features.dte, features.delta, features.premium, features.iv, features.iv_rank,
                features.vix, features.vix_percentile, features.vix_term_structure,
                features.put_wall_distance_pct, features.call_wall_distance_pct, features.net_gex,
                features.spx_20d_return, features.spx_5d_return, features.spx_distance_from_high,
                features.premium_to_strike_pct, features.annualized_return
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save entry to DB: {e}")

    def _load_entry_from_db(self, trade_id: str) -> Optional[PrometheusFeatures]:
        """Load trade entry from database"""
        if not DB_AVAILABLE or get_connection is None:
            return None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT trade_date, strike, underlying_price, dte, delta, premium,
                       iv, iv_rank, vix, vix_percentile, vix_term_structure,
                       put_wall_distance_pct, call_wall_distance_pct, net_gex,
                       spx_20d_return, spx_5d_return, spx_distance_from_high,
                       premium_to_strike_pct, annualized_return
                FROM spx_wheel_ml_outcomes
                WHERE trade_id = %s
            ''', (trade_id,))

            row = cursor.fetchone()
            conn.close()

            if row:
                # Helper to safely convert values with defaults
                def safe_float(val, default=0.0):
                    return float(val) if val is not None else default

                def safe_int(val, default=0):
                    return int(val) if val is not None else default

                return PrometheusFeatures(
                    trade_date=str(row[0]) if row[0] else datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'),
                    strike=safe_float(row[1]),
                    underlying_price=safe_float(row[2]),
                    dte=safe_int(row[3]),
                    delta=safe_float(row[4]),
                    premium=safe_float(row[5]),
                    iv=safe_float(row[6], 0.18),
                    iv_rank=safe_float(row[7], 50.0),
                    vix=safe_float(row[8], 18.0),
                    vix_percentile=safe_float(row[9], 50.0),
                    vix_term_structure=safe_float(row[10], -1.0),
                    put_wall_distance_pct=safe_float(row[11], 3.0),
                    call_wall_distance_pct=safe_float(row[12], 3.0),
                    net_gex=safe_float(row[13], 5e9),
                    spx_20d_return=safe_float(row[14]),
                    spx_5d_return=safe_float(row[15]),
                    spx_distance_from_high=safe_float(row[16], 1.0),
                    premium_to_strike_pct=safe_float(row[17]),
                    annualized_return=safe_float(row[18])
                )
            return None
        except Exception as e:
            logger.error(f"Failed to load entry from DB: {e}")
            return None

    def _update_outcome_in_db(
        self,
        trade_id: str,
        outcome: str,
        pnl: float,
        settlement_price: float,
        max_drawdown: float
    ):
        """Update trade outcome in database"""
        if not DB_AVAILABLE or get_connection is None:
            return

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE spx_wheel_ml_outcomes
                SET outcome = %s,
                    pnl = %s,
                    settlement_price = %s,
                    max_drawdown = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE trade_id = %s
            ''', (outcome, pnl, settlement_price, max_drawdown, trade_id))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to update outcome in DB: {e}")

    def get_pending_trades(self) -> Dict[str, PrometheusFeatures]:
        """Get all pending trades awaiting outcome"""
        return self._pending_trades.copy()

    def get_training_data_count(self) -> int:
        """Get count of completed trades available for training"""
        if not DB_AVAILABLE or get_connection is None:
            return 0

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT COUNT(*) FROM spx_wheel_ml_outcomes
                WHERE outcome IS NOT NULL
            ''')

            count = cursor.fetchone()[0]
            conn.close()
            return count or 0
        except Exception as e:
            logger.error(f"Failed to get training data count: {e}")
            return 0


# Singleton instance
_outcome_tracker = None


def get_prometheus_outcome_tracker() -> PrometheusOutcomeTracker:
    """Get singleton outcome tracker"""
    global _outcome_tracker
    if _outcome_tracker is None:
        _outcome_tracker = PrometheusOutcomeTracker()
    return _outcome_tracker


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def record_spx_wheel_entry(
    trade_id: str,
    strike: float,
    underlying_price: float,
    dte: int,
    delta: float,
    premium: float
) -> bool:
    """
    Convenience function to record SPX Wheel trade entry.

    Call this when opening a new SPX put selling position.
    """
    tracker = get_prometheus_outcome_tracker()
    market_data = tracker.get_current_market_features()
    return tracker.record_trade_entry(
        trade_id=trade_id,
        strike=strike,
        underlying_price=underlying_price,
        dte=dte,
        delta=delta,
        premium=premium,
        market_data=market_data
    )


def record_spx_wheel_outcome(
    trade_id: str,
    is_win: bool,
    pnl: float,
    settlement_price: float = None
) -> bool:
    """
    Convenience function to record SPX Wheel trade outcome.

    Call this when closing a position (expiration or assignment).
    """
    tracker = get_prometheus_outcome_tracker()
    outcome = "WIN" if is_win else "LOSS"
    result = tracker.record_trade_outcome(
        trade_id=trade_id,
        outcome=outcome,
        pnl=pnl,
        settlement_price=settlement_price
    )
    return result is not None


def trigger_retraining_if_ready(min_new_outcomes: int = 10) -> Dict:
    """
    Check if we have enough new data to retrain and trigger if ready.

    Args:
        min_new_outcomes: Minimum new outcomes before retraining

    Returns:
        Training result or status dict
    """
    if not PROMETHEUS_AVAILABLE:
        return {'error': 'Prometheus not available'}

    tracker = get_prometheus_outcome_tracker()
    count = tracker.get_training_data_count()

    if count < 30:
        return {
            'status': 'waiting',
            'message': f'Need at least 30 outcomes, have {count}'
        }

    # Get trainer and check last training
    trainer = get_prometheus_trainer()

    if trainer.training_metrics:
        last_samples = trainer.training_metrics.total_samples
        if count - last_samples < min_new_outcomes:
            return {
                'status': 'waiting',
                'message': f'Need {min_new_outcomes} new outcomes, have {count - last_samples}'
            }

    # Trigger training
    logger.info(f"Auto-triggering Prometheus training with {count} outcomes")
    # Training would be done via API call or background task
    return {
        'status': 'ready',
        'message': f'Ready to train with {count} outcomes',
        'training_data_count': count
    }
