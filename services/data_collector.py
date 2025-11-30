#!/usr/bin/env python3
"""
DATA COLLECTION SERVICE

This service ensures ALL data that flows through AlphaGEX is stored in the database.
It provides hooks that should be called whenever data is fetched from external APIs.

USAGE:
    from services.data_collector import DataCollector

    # When fetching GEX data
    gex_data = fetch_from_trading_volatility()
    DataCollector.store_gex(gex_data)

    # When fetching price data
    prices = fetch_from_polygon()
    DataCollector.store_prices(prices)
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import traceback

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except:
    DB_AVAILABLE = False
    print("⚠️  Database not available - data will not be stored")


class DataCollector:
    """
    Central data collection service.
    Call these methods whenever external data is fetched to ensure it's stored.
    """

    @staticmethod
    def _log_collection(collection_type: str, source: str, records: int, success: bool, error: str = None):
        """Log a data collection event"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("""
                INSERT INTO data_collection_log
                (collection_type, source, symbol, records_collected, success, error_message)
                VALUES (%s, %s, 'SPY', %s, %s, %s)
            """, (collection_type, source, records, success, error))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Could not log collection: {e}")

    @staticmethod
    def store_gex(gex_data: Dict[str, Any], source: str = 'tradingvolatility') -> bool:
        """
        Store GEX data snapshot.
        Call this whenever GEX data is fetched from any source.
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            c = conn.cursor()

            # Store in gex_history
            c.execute("""
                INSERT INTO gex_history
                (symbol, net_gex, flip_point, call_wall, put_wall, spot_price, mm_state, regime, data_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                gex_data.get('symbol', 'SPY'),
                gex_data.get('net_gex'),
                gex_data.get('flip_point'),
                gex_data.get('call_wall'),
                gex_data.get('put_wall'),
                gex_data.get('spot_price'),
                gex_data.get('mm_state'),
                gex_data.get('regime'),
                source
            ))

            conn.commit()
            conn.close()

            DataCollector._log_collection('gex', source, 1, True)
            return True

        except Exception as e:
            DataCollector._log_collection('gex', source, 0, False, str(e))
            print(f"❌ Failed to store GEX data: {e}")
            return False

    @staticmethod
    def store_prices(prices: List[Dict], symbol: str = 'SPY', timeframe: str = '1min',
                     source: str = 'polygon') -> int:
        """
        Store historical price data (OHLCV bars).
        Call this whenever price data is fetched from Polygon or other sources.
        Returns number of records stored.
        """
        if not DB_AVAILABLE or not prices:
            return 0

        try:
            conn = get_connection()
            c = conn.cursor()

            count = 0
            for bar in prices:
                try:
                    c.execute("""
                        INSERT INTO price_history
                        (timestamp, symbol, timeframe, open, high, low, close, volume, vwap, data_source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING
                    """, (
                        bar.get('timestamp') or bar.get('t'),
                        symbol,
                        timeframe,
                        bar.get('open') or bar.get('o'),
                        bar.get('high') or bar.get('h'),
                        bar.get('low') or bar.get('l'),
                        bar.get('close') or bar.get('c'),
                        bar.get('volume') or bar.get('v'),
                        bar.get('vwap') or bar.get('vw'),
                        source
                    ))
                    count += 1
                except Exception as e:
                    pass  # Skip duplicates

            conn.commit()
            conn.close()

            DataCollector._log_collection('price', source, count, True)
            return count

        except Exception as e:
            DataCollector._log_collection('price', source, 0, False, str(e))
            print(f"❌ Failed to store price data: {e}")
            return 0

    @staticmethod
    def store_greeks(greeks_data: Dict[str, Any], context: str = 'api_fetch') -> bool:
        """
        Store Greeks snapshot.
        Call this whenever Greeks are calculated for an option.
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO greeks_snapshots
                (symbol, strike, option_type, expiration_date, dte,
                 delta, gamma, theta, vega, implied_volatility,
                 underlying_price, option_price, bid, ask,
                 volume, open_interest, data_source, context)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                greeks_data.get('symbol', 'SPY'),
                greeks_data.get('strike'),
                greeks_data.get('option_type'),
                greeks_data.get('expiration'),
                greeks_data.get('dte'),
                greeks_data.get('delta'),
                greeks_data.get('gamma'),
                greeks_data.get('theta'),
                greeks_data.get('vega'),
                greeks_data.get('iv') or greeks_data.get('implied_volatility'),
                greeks_data.get('underlying_price') or greeks_data.get('spot_price'),
                greeks_data.get('price') or greeks_data.get('option_price'),
                greeks_data.get('bid'),
                greeks_data.get('ask'),
                greeks_data.get('volume'),
                greeks_data.get('open_interest') or greeks_data.get('oi'),
                greeks_data.get('source', 'unknown'),
                context
            ))

            conn.commit()
            conn.close()

            DataCollector._log_collection('greeks', greeks_data.get('source', 'unknown'), 1, True)
            return True

        except Exception as e:
            DataCollector._log_collection('greeks', 'unknown', 0, False, str(e))
            print(f"❌ Failed to store Greeks: {e}")
            return False

    @staticmethod
    def store_vix_term_structure(vix_data: Dict[str, Any], source: str = 'cboe') -> bool:
        """
        Store VIX term structure snapshot.
        Call this whenever VIX data is fetched.
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO vix_term_structure
                (vix_spot, vix_9d, vix_3m, vix_6m,
                 vx_front_month, vx_second_month, vx_third_month, vx_fourth_month,
                 contango_pct, term_structure_slope, inversion_detected,
                 vvix, skew_index, put_call_ratio,
                 spy_price, regime, data_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                vix_data.get('vix') or vix_data.get('vix_spot'),
                vix_data.get('vix_9d'),
                vix_data.get('vix_3m') or vix_data.get('vxv'),
                vix_data.get('vix_6m'),
                vix_data.get('vx_front') or vix_data.get('vx1'),
                vix_data.get('vx_second') or vix_data.get('vx2'),
                vix_data.get('vx_third') or vix_data.get('vx3'),
                vix_data.get('vx_fourth') or vix_data.get('vx4'),
                vix_data.get('contango_pct'),
                vix_data.get('term_slope'),
                vix_data.get('inverted', False),
                vix_data.get('vvix'),
                vix_data.get('skew'),
                vix_data.get('put_call_ratio'),
                vix_data.get('spy_price'),
                vix_data.get('regime'),
                source
            ))

            conn.commit()
            conn.close()

            DataCollector._log_collection('vix', source, 1, True)
            return True

        except Exception as e:
            DataCollector._log_collection('vix', source, 0, False, str(e))
            print(f"❌ Failed to store VIX term structure: {e}")
            return False

    @staticmethod
    def store_options_flow(flow_data: Dict[str, Any], source: str = 'tradier') -> bool:
        """
        Store options flow/volume snapshot.
        Call this whenever options chain data is processed.
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO options_flow
                (symbol, total_call_volume, total_put_volume, put_call_ratio,
                 unusual_call_volume, unusual_put_volume, unusual_strikes,
                 call_oi_change, put_oi_change, largest_oi_strike, largest_oi_type,
                 net_call_premium, net_put_premium,
                 zero_dte_volume, weekly_volume, monthly_volume,
                 spot_price, vix_level, data_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                flow_data.get('symbol', 'SPY'),
                flow_data.get('call_volume'),
                flow_data.get('put_volume'),
                flow_data.get('put_call_ratio'),
                flow_data.get('unusual_call_volume'),
                flow_data.get('unusual_put_volume'),
                json.dumps(flow_data.get('unusual_strikes', [])),
                flow_data.get('call_oi_change'),
                flow_data.get('put_oi_change'),
                flow_data.get('largest_oi_strike'),
                flow_data.get('largest_oi_type'),
                flow_data.get('net_call_premium'),
                flow_data.get('net_put_premium'),
                flow_data.get('zero_dte_volume'),
                flow_data.get('weekly_volume'),
                flow_data.get('monthly_volume'),
                flow_data.get('spot_price'),
                flow_data.get('vix'),
                source
            ))

            conn.commit()
            conn.close()

            DataCollector._log_collection('options_flow', source, 1, True)
            return True

        except Exception as e:
            DataCollector._log_collection('options_flow', source, 0, False, str(e))
            print(f"❌ Failed to store options flow: {e}")
            return False

    @staticmethod
    def store_ai_analysis(analysis_type: str, prompt: str, response: str,
                          context: Dict = None, model: str = 'claude') -> bool:
        """
        Store AI analysis for learning.
        Call this whenever Claude or other AI generates analysis.
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO ai_analysis_history
                (analysis_type, symbol, input_prompt, market_context, ai_response,
                 model_used, outcome_tracked)
                VALUES (%s, %s, %s, %s, %s, %s, FALSE)
            """, (
                analysis_type,
                context.get('symbol', 'SPY') if context else 'SPY',
                prompt[:2000] if prompt else None,  # Truncate long prompts
                json.dumps(context) if context else None,
                response[:10000] if response else None,  # Truncate long responses
                model
            ))

            conn.commit()
            conn.close()

            DataCollector._log_collection('ai_analysis', model, 1, True)
            return True

        except Exception as e:
            DataCollector._log_collection('ai_analysis', model, 0, False, str(e))
            print(f"❌ Failed to store AI analysis: {e}")
            return False

    @staticmethod
    def store_market_snapshot(snapshot: Dict[str, Any]) -> bool:
        """
        Store comprehensive market snapshot (for ML feature engineering).
        This should be called every minute during market hours.
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO market_snapshots
                (symbol, price, bid, ask, volume_1min,
                 net_gex, call_wall, put_wall, flip_point,
                 distance_to_call_wall_pct, distance_to_put_wall_pct, distance_to_flip_pct,
                 vix_spot, vix_change_1d_pct,
                 rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d,
                 gex_regime, psychology_regime, volatility_regime,
                 liberation_setup, false_floor, trap_detected,
                 market_session, minutes_to_close, day_of_week)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                snapshot.get('symbol', 'SPY'),
                snapshot.get('price'),
                snapshot.get('bid'),
                snapshot.get('ask'),
                snapshot.get('volume'),
                snapshot.get('net_gex'),
                snapshot.get('call_wall'),
                snapshot.get('put_wall'),
                snapshot.get('flip_point'),
                snapshot.get('distance_to_call_wall'),
                snapshot.get('distance_to_put_wall'),
                snapshot.get('distance_to_flip'),
                snapshot.get('vix'),
                snapshot.get('vix_change'),
                snapshot.get('rsi_5m'),
                snapshot.get('rsi_15m'),
                snapshot.get('rsi_1h'),
                snapshot.get('rsi_4h'),
                snapshot.get('rsi_1d'),
                snapshot.get('gex_regime'),
                snapshot.get('psychology_regime'),
                snapshot.get('volatility_regime'),
                snapshot.get('liberation_setup', False),
                snapshot.get('false_floor', False),
                snapshot.get('trap_detected'),
                snapshot.get('market_session'),
                snapshot.get('minutes_to_close'),
                snapshot.get('day_of_week')
            ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"❌ Failed to store market snapshot: {e}")
            return False

    @staticmethod
    def store_position_sizing(sizing: Dict[str, Any]) -> bool:
        """
        Store position sizing calculation for optimization learning.
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO position_sizing_history
                (symbol, account_value, win_rate, avg_win, avg_loss, current_drawdown_pct,
                 kelly_full, kelly_half, kelly_quarter, recommended_size, max_risk_dollars,
                 var_95, expected_value, risk_of_ruin, vix_level, regime, sizing_rationale)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                sizing.get('symbol', 'SPY'),
                sizing.get('account_value'),
                sizing.get('win_rate'),
                sizing.get('avg_win'),
                sizing.get('avg_loss'),
                sizing.get('drawdown_pct'),
                sizing.get('kelly_full'),
                sizing.get('kelly_half'),
                sizing.get('kelly_quarter'),
                sizing.get('recommended_size'),
                sizing.get('max_risk'),
                sizing.get('var_95'),
                sizing.get('expected_value'),
                sizing.get('risk_of_ruin'),
                sizing.get('vix'),
                sizing.get('regime'),
                sizing.get('rationale')
            ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"❌ Failed to store position sizing: {e}")
            return False

    @staticmethod
    def store_backtest_trade(run_id: str, trade: Dict[str, Any], trade_num: int) -> bool:
        """
        Store individual backtest trade for verification.
        This is what allows you to audit and verify backtest results!
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO backtest_trades
                (backtest_run_id, strategy_name, trade_number, symbol,
                 entry_date, entry_time, entry_price, entry_strike, entry_option_type,
                 entry_expiration, entry_dte, entry_spot_price,
                 entry_net_gex, entry_flip_point, entry_vix, entry_regime, entry_pattern,
                 entry_signal_confidence, entry_reasoning,
                 exit_date, exit_time, exit_price, exit_spot_price, exit_reason,
                 pnl_dollars, pnl_percent, win, hold_time_hours,
                 entry_delta, entry_gamma, entry_theta, entry_iv)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                run_id,
                trade.get('strategy'),
                trade_num,
                trade.get('symbol', 'SPY'),
                trade.get('entry_date'),
                trade.get('entry_time'),
                trade.get('entry_price'),
                trade.get('strike'),
                trade.get('option_type'),
                trade.get('expiration'),
                trade.get('dte'),
                trade.get('entry_spot'),
                trade.get('entry_gex'),
                trade.get('entry_flip'),
                trade.get('entry_vix'),
                trade.get('regime'),
                trade.get('pattern'),
                trade.get('confidence'),
                trade.get('reasoning'),
                trade.get('exit_date'),
                trade.get('exit_time'),
                trade.get('exit_price'),
                trade.get('exit_spot'),
                trade.get('exit_reason'),
                trade.get('pnl_dollars'),
                trade.get('pnl_percent'),
                trade.get('win'),
                trade.get('hold_hours'),
                trade.get('delta'),
                trade.get('gamma'),
                trade.get('theta'),
                trade.get('iv')
            ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"❌ Failed to store backtest trade: {e}")
            return False


# Convenience function for testing
def test_data_collector():
    """Test that the data collector can store data"""
    print("Testing Data Collector...")

    # Test GEX storage
    test_gex = {
        'symbol': 'SPY',
        'net_gex': -1500000000,
        'flip_point': 598.5,
        'call_wall': 605.0,
        'put_wall': 590.0,
        'spot_price': 597.25,
        'regime': 'negative'
    }

    if DataCollector.store_gex(test_gex, source='test'):
        print("✅ GEX storage working")
    else:
        print("❌ GEX storage failed")


if __name__ == "__main__":
    test_data_collector()
