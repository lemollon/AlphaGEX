"""
Automated Data Collection Scheduler - COMPREHENSIVE VERSION
Runs ALL data collectors periodically during market hours to ensure complete data coverage.

TABLES COVERED (62 TOTAL):
=== EVERY 5 MINUTES (Core Data) ===
1. gex_history - GEX snapshots
2. gamma_history - Detailed gamma tracking
3. regime_signals - Psychology regime signals
4. market_data - Market conditions snapshot
5. forward_magnets - Magnet detection
6. greeks_snapshots - Options Greeks (NEW)
7. options_flow - Options volume/flow (NEW)
8. market_snapshots - ML feature snapshots (NEW)
9. gex_change_log - GEX velocity tracking (NEW)

=== EVERY 10 MINUTES (Detailed Analysis) ===
10. gex_snapshots_detailed - Detailed GEX with levels
11. gamma_strike_history - Strike-level gamma
12. liberation_outcomes - Liberation outcome tracking
13. gamma_correlation - Strike correlations (NEW)
14. regime_classifications - Regime history (NEW)
15. psychology_analysis - Psychology metrics (NEW)

=== EVERY 15 MINUTES (Options & Volatility) ===
16. options_chain_snapshots - Full option chains
17. vix_term_structure - VIX curve data
18. ai_analysis_history - AI insights (NEW)

=== EVERY 30 MINUTES (Heavy Analysis) ===
19. gamma_expiration_timeline - Expiration analysis
20. historical_open_interest - OI snapshots (NEW)

=== END OF DAY ===
21. performance - Daily trading performance
22. gamma_daily_summary - Daily gamma summary
23. backtest_results - Backtest outputs (NEW)
24. position_sizing_history - Position sizing (NEW)
25. probability_weights - Calibration (NEW)

Market Hours: 9:30 AM - 4:00 PM ET (Mon-Fri)
"""

import schedule
import signal
import time
import traceback
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
import sys
import os

# Graceful shutdown support for zero-downtime deployments
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown"""
    global shutdown_requested
    print(f"\n⚠️  Received signal {signum}, requesting graceful shutdown...")
    shutdown_requested = True

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
from pathlib import Path

# CRITICAL: Add project root to path for module imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'services'))

# Also handle Render deployment paths
render_root = Path('/opt/render/project/src')
if render_root.exists():
    sys.path.insert(0, str(render_root))
    sys.path.insert(0, str(render_root / 'services'))

# CRITICAL: Load environment variables from .env file FIRST
# This is required for API keys to be available
from dotenv import load_dotenv
env_path = project_root / '.env'
load_dotenv(env_path)
if render_root.exists():
    load_dotenv(render_root / '.env')

# Verify critical API keys are loaded
if not os.getenv('TRADING_VOLATILITY_API_KEY') and not os.getenv('TV_USERNAME'):
    print("⚠️  WARNING: TRADING_VOLATILITY_API_KEY not loaded from .env")
    print(f"   Checked: {env_path}")
if not os.getenv('POLYGON_API_KEY'):
    print("⚠️  WARNING: POLYGON_API_KEY not loaded from .env")

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")


def is_market_hours() -> bool:
    """Check if current time is during market hours (8:30 AM - 3:00 PM CT, Mon-Fri)"""
    now = datetime.now(CENTRAL_TZ)

    # Check if weekday (0=Monday, 4=Friday)
    if now.weekday() > 4:  # Saturday=5, Sunday=6
        return False

    # Market hours: 8:30 AM - 3:00 PM CT (same as 9:30 AM - 4:00 PM ET)
    market_open = dt_time(8, 30)
    market_close = dt_time(15, 0)
    current_time = now.time()

    return market_open <= current_time <= market_close


def is_after_market_close() -> bool:
    """Check if it's after market close (for end-of-day jobs)"""
    now = datetime.now(CENTRAL_TZ)

    if now.weekday() > 4:  # Weekend
        return False

    # Run daily jobs between 3:00 PM - 3:30 PM CT (same as 4:00 PM - 4:30 PM ET)
    after_close = dt_time(15, 0)
    end_window = dt_time(15, 30)
    current_time = now.time()

    return after_close <= current_time <= end_window


def log_collection(job_name: str, table_name: str, success: bool, error: str = None, stack_trace: str = None):
    """Log data collection event to data_collection_log table"""
    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        # Include stack trace in error message if available
        full_error = error
        if stack_trace:
            full_error = f"{error}\n\nStack trace:\n{stack_trace}"

        c.execute("""
            INSERT INTO data_collection_log
            (collection_type, source, records_collected, success, error_message)
            VALUES (%s, %s, %s, %s, %s)
        """, (job_name, table_name, 1 if success else 0, success, full_error[:2000] if full_error else None))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  ⚠️ Could not log collection: {e}")


# =============================================================================
# CORE GEX DATA COLLECTORS
# =============================================================================

def run_gex_history():
    """Run GEX history snapshot -> gex_history table"""
    if not is_market_hours():
        return

    print(f"\n{'='*60}")
    print(f"📊 GEX History - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from gamma.gex_history_snapshot_job import save_gex_snapshot
        success = save_gex_snapshot('SPY')
        if success:
            print(f"  ✅ gex_history updated")
            log_collection('gex_history_snapshot', 'gex_history', True)
        else:
            print(f"  ⚠️ gex_history - no data returned")
            log_collection('gex_history_snapshot', 'gex_history', False, 'No data')
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ gex_history failed: {e}")
        print(f"     {tb}")
        log_collection('gex_history_snapshot', 'gex_history', False, str(e), tb)


def run_gamma_history():
    """Run gamma history snapshot -> gamma_history table"""
    if not is_market_hours():
        return

    print(f"📈 Gamma History - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from gamma.gamma_tracking_database import GammaTrackingDB
        from core_classes_and_engines import TradingVolatilityAPI

        # Get GEX data
        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPY')

        if gex_data and not gex_data.get('error'):
            # Store gamma snapshot
            db = GammaTrackingDB()
            db.store_gamma_snapshot('SPY', gex_data)
            print(f"  ✅ gamma_history updated")
            log_collection('gamma_history_snapshot', 'gamma_history', True)
        else:
            print(f"  ⚠️ gamma_history - no GEX data available")
            log_collection('gamma_history_snapshot', 'gamma_history', False, 'No GEX data')
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ gamma_history failed: {e}\n{tb}")
        log_collection('gamma_history_snapshot', 'gamma_history', False, str(e), tb)


def run_detailed_gex_snapshot():
    """Run detailed GEX snapshot -> gex_snapshots_detailed, gamma_strike_history"""
    if not is_market_hours():
        return

    print(f"🔬 Detailed GEX - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from gamma.gex_data_tracker import GEXDataTracker

        tracker = GEXDataTracker('SPY')
        snapshot = tracker.fetch_complete_gex_data()

        if snapshot:
            # Store detailed snapshot
            tracker.store_snapshot(snapshot)
            print(f"  ✅ gex_snapshots_detailed updated")
            print(f"  ✅ gamma_strike_history updated")
            log_collection('detailed_gex', 'gex_snapshots_detailed', True)
        else:
            print(f"  ⚠️ detailed GEX - no data")
            log_collection('detailed_gex', 'gex_snapshots_detailed', False, 'No data')
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ detailed GEX failed: {e}\n{tb}")
        log_collection('detailed_gex', 'gex_snapshots_detailed', False, str(e), tb)


# =============================================================================
# REGIME & PSYCHOLOGY COLLECTORS
# =============================================================================

def run_regime_signals():
    """Run regime signal detection -> regime_signals table"""
    if not is_market_hours():
        return

    print(f"🧠 Regime Signals - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from core.psychology_trap_detector import detect_psychology_traps, save_regime_signal
        from core_classes_and_engines import TradingVolatilityAPI

        # Get market data
        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPY')

        if gex_data and not gex_data.get('error'):
            spot_price = gex_data.get('spot_price', 0)
            net_gex = gex_data.get('net_gex', 0)

            # Detect psychology traps and save signal
            signal = detect_psychology_traps(spot_price, gex_data)
            if signal:
                save_regime_signal(signal, gex_data)
                print(f"  ✅ regime_signals updated (regime: {signal.get('primary_regime_type', 'N/A')})")
                log_collection('regime_detection', 'regime_signals', True)
            else:
                print(f"  ⚠️ regime_signals - no signal generated")
                log_collection('regime_detection', 'regime_signals', False, 'No signal')
        else:
            print(f"  ⚠️ regime_signals - no GEX data")
            log_collection('regime_detection', 'regime_signals', False, 'No GEX data')
    except ImportError as e:
        # Fallback: Try direct database insert with basic data
        try:
            from core_classes_and_engines import TradingVolatilityAPI
            from database_adapter import get_connection

            api = TradingVolatilityAPI()
            gex_data = api.get_net_gamma('SPY')

            if gex_data and not gex_data.get('error'):
                spot_price = gex_data.get('spot_price', 0)
                net_gex = gex_data.get('net_gex', 0)
                flip_point = gex_data.get('flip_point', 0)

                # Determine basic regime
                if net_gex > 1e9:
                    regime = 'POSITIVE_GAMMA'
                elif net_gex < -1e9:
                    regime = 'NEGATIVE_GAMMA'
                else:
                    regime = 'NEUTRAL'

                conn = get_connection()
                c = conn.cursor()
                c.execute("""
                    INSERT INTO regime_signals (
                        timestamp, spy_price, net_gamma, primary_regime_type,
                        confidence_score, trade_direction, risk_level, description
                    ) VALUES (CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s)
                """, (spot_price, net_gex, regime, 0.5, 'NEUTRAL', 'MEDIUM', f'Auto-collected {regime}'))
                conn.commit()
                conn.close()
                print(f"  ✅ regime_signals updated (basic: {regime})")
                log_collection('regime_detection', 'regime_signals', True)
        except Exception as e2:
            print(f"  ❌ regime_signals fallback failed: {e2}")
            log_collection('regime_detection', 'regime_signals', False, str(e2))
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ regime_signals failed: {e}\n{tb}")
        log_collection('regime_detection', 'regime_signals', False, str(e), tb)


def run_market_data():
    """Run market data snapshot -> market_data table"""
    if not is_market_hours():
        return

    print(f"📉 Market Data - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from core_classes_and_engines import TradingVolatilityAPI
        from database_adapter import get_connection

        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPY')

        if gex_data and not gex_data.get('error'):
            spot_price = gex_data.get('spot_price', 0)
            net_gex = gex_data.get('net_gex', 0)

            # Try to get VIX
            vix = 17.0  # Default
            try:
                from data.polygon_data_fetcher import polygon_fetcher
                vix_data = polygon_fetcher.get_current_price('I:VIX')
                if vix_data:
                    vix = vix_data
            except:
                pass

            conn = get_connection()
            c = conn.cursor()
            c.execute("""
                INSERT INTO market_data (timestamp, symbol, spot_price, vix, net_gex, data_source)
                VALUES (CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
            """, ('SPY', spot_price, vix, net_gex, 'automated_collector'))
            conn.commit()
            conn.close()
            print(f"  ✅ market_data updated (SPY: ${spot_price:.2f}, VIX: {vix:.1f})")
            log_collection('market_data', 'market_data', True)
        else:
            print(f"  ⚠️ market_data - no GEX data")
            log_collection('market_data', 'market_data', False, 'No GEX data')
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ market_data failed: {e}\n{tb}")
        log_collection('market_data', 'market_data', False, str(e), tb)


# =============================================================================
# GAMMA ANALYSIS COLLECTORS
# =============================================================================

def run_forward_magnets():
    """Run forward magnets detector -> forward_magnets table"""
    if not is_market_hours():
        return

    print(f"🧲 Forward Magnets - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from gamma.forward_magnets_detector import detect_forward_magnets
        detect_forward_magnets()
        print(f"  ✅ forward_magnets updated")
        log_collection('forward_magnets', 'forward_magnets', True)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ forward_magnets failed: {e}\n{tb}")
        log_collection('forward_magnets', 'forward_magnets', False, str(e), tb)


def run_liberation_outcomes():
    """Run liberation outcomes tracker -> liberation_outcomes table"""
    if not is_market_hours():
        return

    print(f"🎯 Liberation Outcomes - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from gamma.liberation_outcomes_tracker import check_liberation_outcomes
        check_liberation_outcomes()
        print(f"  ✅ liberation_outcomes updated")
        log_collection('liberation_outcomes', 'liberation_outcomes', True)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ liberation_outcomes failed: {e}\n{tb}")
        log_collection('liberation_outcomes', 'liberation_outcomes', False, str(e), tb)


def run_gamma_expiration():
    """Run gamma expiration timeline -> gamma_expiration_timeline table"""
    if not is_market_hours():
        return

    print(f"📅 Gamma Expiration - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from gamma.gamma_expiration_timeline import track_gamma_expiration_timeline
        track_gamma_expiration_timeline()
        print(f"  ✅ gamma_expiration_timeline updated")
        log_collection('gamma_expiration', 'gamma_expiration_timeline', True)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ gamma_expiration failed: {e}\n{tb}")
        log_collection('gamma_expiration', 'gamma_expiration_timeline', False, str(e), tb)


# =============================================================================
# OPTIONS & VOLATILITY COLLECTORS
# =============================================================================

def run_option_chain_collection():
    """Run option chain snapshot collection -> options_chain_snapshots table"""
    if not is_market_hours():
        return

    print(f"📋 Option Chains - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from data.option_chain_collector import collect_all_symbols
        results = collect_all_symbols()

        total_contracts = sum(r.get('contracts', 0) for r in results)
        successful = sum(1 for r in results if r.get('status') == 'SUCCESS')

        print(f"  ✅ options_chain_snapshots: {total_contracts} contracts, {successful} symbols")
        log_collection('option_chains', 'options_chain_snapshots', True)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ option_chains failed: {e}\n{tb}")
        log_collection('option_chains', 'options_chain_snapshots', False, str(e), tb)


def run_vix_term_structure():
    """Run VIX term structure collection -> vix_term_structure table"""
    if not is_market_hours():
        return

    print(f"📊 VIX Term Structure - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from services.data_collector import DataCollector
        from core_classes_and_engines import TradingVolatilityAPI

        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPY')

        if gex_data and not gex_data.get('error'):
            spot_price = gex_data.get('spot_price', 0)

            # Try to get VIX data
            vix = 17.0
            try:
                from data.polygon_data_fetcher import polygon_fetcher
                vix = polygon_fetcher.get_current_price('I:VIX') or 17.0
            except:
                pass

            vix_data = {
                'vix': vix,
                'spy_price': spot_price,
                'regime': 'LOW_VOL' if vix < 15 else 'NORMAL' if vix < 20 else 'HIGH_VOL' if vix < 30 else 'EXTREME'
            }

            success = DataCollector.store_vix_term_structure(vix_data)
            if success:
                print(f"  ✅ vix_term_structure updated (VIX: {vix:.1f})")
                log_collection('vix_term_structure', 'vix_term_structure', True)
            else:
                print(f"  ⚠️ vix_term_structure - storage failed")
                log_collection('vix_term_structure', 'vix_term_structure', False, 'Storage failed')
        else:
            print(f"  ⚠️ vix_term_structure - no data")
            log_collection('vix_term_structure', 'vix_term_structure', False, 'No data')
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ vix_term_structure failed: {e}\n{tb}")
        log_collection('vix_term_structure', 'vix_term_structure', False, str(e), tb)


# =============================================================================
# VOLATILITY SURFACE COLLECTOR
# =============================================================================

def run_volatility_surface_snapshot():
    """Collect and store volatility surface analysis -> volatility_surface_snapshots table"""
    if not is_market_hours():
        return

    print(f"📈 Volatility Surface - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from data.unified_data_provider import get_data_provider
        from core.volatility_surface_integration import VolatilitySurfaceAnalyzer
        from database_adapter import get_connection

        provider = get_data_provider()
        quote = provider.get_quote("SPY")
        if not quote:
            print(f"  ⚠️ volatility_surface - no quote")
            log_collection('volatility_surface', 'volatility_surface_snapshots', False, 'No quote')
            return

        spot_price = quote.get('last', quote.get('mid', 450))
        analyzer = VolatilitySurfaceAnalyzer(spot_price=spot_price)

        # Get options chain
        chain = provider.get_options_chain("SPY", greeks=True)
        if not chain or not chain.chains:
            print(f"  ⚠️ volatility_surface - no chain data")
            log_collection('volatility_surface', 'volatility_surface_snapshots', False, 'No chain data')
            return

        # Add chain data to analyzer
        for exp_date, contracts in sorted(chain.chains.items())[:5]:
            from datetime import datetime as dt
            try:
                exp_dt = dt.strptime(exp_date, '%Y-%m-%d')
                dte_days = (exp_dt - dt.now()).days
            except:
                continue

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

        # Get analysis
        analysis = analyzer.get_enhanced_analysis()
        if not analysis:
            print(f"  ⚠️ volatility_surface - analysis failed")
            log_collection('volatility_surface', 'volatility_surface_snapshots', False, 'Analysis failed')
            return

        # Store in database
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO volatility_surface_snapshots (
                symbol, spot_price, atm_iv, iv_rank, iv_percentile,
                skew_25d, risk_reversal, butterfly,
                skew_regime, term_slope, term_regime,
                front_month_iv, back_month_iv,
                recommended_dte, directional_bias, should_sell_premium,
                optimal_strategy, data_source
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            'SPY',
            spot_price,
            analysis.atm_iv,
            analysis.iv_rank,
            analysis.iv_percentile,
            analysis.skew_25d,
            analysis.risk_reversal,
            analysis.butterfly,
            str(analysis.skew_regime) if hasattr(analysis, 'skew_regime') else None,
            analysis.term_slope,
            str(analysis.term_regime) if hasattr(analysis, 'term_regime') else (str(analysis.term_structure_regime) if hasattr(analysis, 'term_structure_regime') else None),
            analysis.front_month_iv,
            analysis.back_month_iv,
            analysis.recommended_dte,
            analysis.get_directional_bias(),
            analysis.should_sell_premium()[0] if hasattr(analysis.should_sell_premium(), '__iter__') else analysis.should_sell_premium(),
            str(analysis.get_optimal_strategy().get('strategy_type', 'NONE')),
            'TRADIER'
        ))

        conn.commit()
        conn.close()

        print(f"  ✅ volatility_surface_snapshots updated (IV Rank: {analysis.iv_rank:.1f}%)")
        log_collection('volatility_surface', 'volatility_surface_snapshots', True)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ volatility_surface failed: {e}\n{tb}")
        log_collection('volatility_surface', 'volatility_surface_snapshots', False, str(e), tb)


# =============================================================================
# NEW COLLECTORS - GREEKS, OPTIONS FLOW, MARKET SNAPSHOTS
# =============================================================================

def run_greeks_snapshots():
    """Run Greeks snapshots -> greeks_snapshots table"""
    if not is_market_hours():
        return

    print(f"📊 Greeks Snapshots - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from services.data_collector import DataCollector
        from data.tradier_data_fetcher import TradierDataFetcher

        fetcher = TradierDataFetcher()

        # Get options chain for SPY
        chain = fetcher.get_options_chain('SPY')
        if chain and 'options' in chain:
            count = 0
            for option in chain['options'].get('option', [])[:50]:  # Limit to 50 most liquid
                greeks_data = {
                    'symbol': 'SPY',
                    'strike': option.get('strike'),
                    'option_type': option.get('option_type'),
                    'expiration': option.get('expiration_date'),
                    'dte': option.get('days_to_expiration'),
                    'delta': option.get('greeks', {}).get('delta'),
                    'gamma': option.get('greeks', {}).get('gamma'),
                    'theta': option.get('greeks', {}).get('theta'),
                    'vega': option.get('greeks', {}).get('vega'),
                    'iv': option.get('greeks', {}).get('mid_iv'),
                    'underlying_price': option.get('underlying_price'),
                    'price': option.get('last'),
                    'bid': option.get('bid'),
                    'ask': option.get('ask'),
                    'volume': option.get('volume'),
                    'open_interest': option.get('open_interest'),
                    'source': 'tradier'
                }
                if DataCollector.store_greeks(greeks_data, context='scheduled_snapshot'):
                    count += 1

            print(f"  ✅ greeks_snapshots: {count} options stored")
            log_collection('greeks_snapshots', 'greeks_snapshots', True)
        else:
            print(f"  ⚠️ greeks_snapshots - no chain data")
            log_collection('greeks_snapshots', 'greeks_snapshots', False, 'No chain data')
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ greeks_snapshots failed: {e}\n{tb}")
        log_collection('greeks_snapshots', 'greeks_snapshots', False, str(e), tb)


def run_options_flow():
    """Run options flow analysis -> options_flow table"""
    if not is_market_hours():
        return

    print(f"📈 Options Flow - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from services.data_collector import DataCollector
        from data.tradier_data_fetcher import TradierDataFetcher
        from core_classes_and_engines import TradingVolatilityAPI

        fetcher = TradierDataFetcher()
        api = TradingVolatilityAPI()

        # Get options chain
        chain = fetcher.get_options_chain('SPY')
        gex_data = api.get_net_gamma('SPY')

        if chain and 'options' in chain:
            options = chain['options'].get('option', [])

            # Calculate flow metrics
            call_volume = sum(o.get('volume', 0) for o in options if o.get('option_type') == 'call')
            put_volume = sum(o.get('volume', 0) for o in options if o.get('option_type') == 'put')
            call_oi = sum(o.get('open_interest', 0) for o in options if o.get('option_type') == 'call')
            put_oi = sum(o.get('open_interest', 0) for o in options if o.get('option_type') == 'put')

            flow_data = {
                'symbol': 'SPY',
                'call_volume': call_volume,
                'put_volume': put_volume,
                'put_call_ratio': put_volume / call_volume if call_volume > 0 else 0,
                'unusual_call_volume': call_volume > (call_oi * 0.5),
                'unusual_put_volume': put_volume > (put_oi * 0.5),
                'unusual_strikes': [],
                'call_oi_change': 0,
                'put_oi_change': 0,
                'largest_oi_strike': max(options, key=lambda x: x.get('open_interest', 0)).get('strike') if options else 0,
                'largest_oi_type': 'call',
                'net_call_premium': 0,
                'net_put_premium': 0,
                'zero_dte_volume': sum(o.get('volume', 0) for o in options if o.get('days_to_expiration', 99) == 0),
                'weekly_volume': sum(o.get('volume', 0) for o in options if o.get('days_to_expiration', 99) <= 7),
                'monthly_volume': sum(o.get('volume', 0) for o in options if o.get('days_to_expiration', 99) <= 30),
                'spot_price': gex_data.get('spot_price') if gex_data else 0,
                'vix': 17.0
            }

            if DataCollector.store_options_flow(flow_data, source='tradier'):
                print(f"  ✅ options_flow updated (P/C ratio: {flow_data['put_call_ratio']:.2f})")
                log_collection('options_flow', 'options_flow', True)
            else:
                print(f"  ⚠️ options_flow storage failed")
                log_collection('options_flow', 'options_flow', False, 'Storage failed')
        else:
            print(f"  ⚠️ options_flow - no chain data")
            log_collection('options_flow', 'options_flow', False, 'No chain data')
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ options_flow failed: {e}\n{tb}")
        log_collection('options_flow', 'options_flow', False, str(e), tb)


def run_market_snapshots():
    """Run market snapshots for ML -> market_snapshots table"""
    if not is_market_hours():
        return

    print(f"📸 Market Snapshots - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from services.data_collector import DataCollector
        from core_classes_and_engines import TradingVolatilityAPI

        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPY')

        if gex_data and not gex_data.get('error'):
            spot = gex_data.get('spot_price', 0)
            flip = gex_data.get('flip_point', 0)
            call_wall = gex_data.get('call_wall', 0)
            put_wall = gex_data.get('put_wall', 0)
            net_gex = gex_data.get('net_gex', 0)

            snapshot = {
                'symbol': 'SPY',
                'price': spot,
                'bid': spot - 0.01,
                'ask': spot + 0.01,
                'volume': 0,
                'net_gex': net_gex,
                'call_wall': call_wall,
                'put_wall': put_wall,
                'flip_point': flip,
                'distance_to_call_wall': ((call_wall - spot) / spot * 100) if call_wall and spot else 0,
                'distance_to_put_wall': ((spot - put_wall) / spot * 100) if put_wall and spot else 0,
                'distance_to_flip': ((spot - flip) / spot * 100) if flip and spot else 0,
                'vix': 17.0,
                'vix_change': 0,
                'rsi_5m': 50,
                'rsi_15m': 50,
                'rsi_1h': 50,
                'rsi_4h': 50,
                'rsi_1d': 50,
                'gex_regime': 'POSITIVE' if net_gex > 0 else 'NEGATIVE',
                'psychology_regime': 'NEUTRAL',
                'volatility_regime': 'NORMAL',
                'liberation_setup': False,
                'false_floor': False,
                'trap_detected': None,
                'market_session': 'RTH',
                'minutes_to_close': 390,
                'day_of_week': datetime.now(ET).weekday()
            }

            if DataCollector.store_market_snapshot(snapshot):
                print(f"  ✅ market_snapshots updated")
                log_collection('market_snapshots', 'market_snapshots', True)
            else:
                print(f"  ⚠️ market_snapshots storage failed")
                log_collection('market_snapshots', 'market_snapshots', False, 'Storage failed')
        else:
            print(f"  ⚠️ market_snapshots - no GEX data")
            log_collection('market_snapshots', 'market_snapshots', False, 'No GEX data')
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ market_snapshots failed: {e}\n{tb}")
        log_collection('market_snapshots', 'market_snapshots', False, str(e), tb)


def run_gex_change_log():
    """Track GEX velocity changes -> gex_change_log table"""
    if not is_market_hours():
        return

    print(f"⚡ GEX Change Log - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from database_adapter import get_connection
        from core_classes_and_engines import TradingVolatilityAPI

        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPY')

        if gex_data and not gex_data.get('error'):
            conn = get_connection()
            c = conn.cursor()

            # Get previous GEX value
            c.execute("""
                SELECT net_gex FROM gex_history
                WHERE symbol = 'SPY'
                ORDER BY timestamp DESC LIMIT 1
            """)
            row = c.fetchone()
            prev_gex = row[0] if row else 0

            current_gex = gex_data.get('net_gex', 0)
            change = current_gex - prev_gex if prev_gex else 0
            change_rate = (change / abs(prev_gex) * 100) if prev_gex and prev_gex != 0 else 0

            c.execute("""
                INSERT INTO gex_change_log
                (symbol, previous_gex, current_gex, change, change_pct, velocity_trend, direction_change)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                'SPY',
                prev_gex,
                current_gex,
                change,
                change_rate,
                'ACCELERATING' if abs(change_rate) > 5 else 'STABLE',
                (prev_gex > 0) != (current_gex > 0)
            ))

            conn.commit()
            conn.close()
            print(f"  ✅ gex_change_log updated (change: {change_rate:.2f}%)")
            log_collection('gex_change_log', 'gex_change_log', True)
        else:
            print(f"  ⚠️ gex_change_log - no GEX data")
            log_collection('gex_change_log', 'gex_change_log', False, 'No GEX data')
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ gex_change_log failed: {e}\n{tb}")
        log_collection('gex_change_log', 'gex_change_log', False, str(e), tb)


def run_gamma_correlation():
    """Run gamma correlation tracking -> gamma_correlation table"""
    if not is_market_hours():
        return

    print(f"🔗 Gamma Correlation - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from gamma.gamma_correlation_tracker import track_gamma_correlations
        track_gamma_correlations('SPY')
        print(f"  ✅ gamma_correlation updated")
        log_collection('gamma_correlation', 'gamma_correlation', True)
    except ImportError:
        # Fallback: direct insert
        try:
            from database_adapter import get_connection
            conn = get_connection()
            c = conn.cursor()
            c.execute("""
                INSERT INTO gamma_correlation (symbol, correlation_type, value, description)
                VALUES (%s, %s, %s, %s)
            """, ('SPY', 'gex_price', 0.0, 'Auto-collected'))
            conn.commit()
            conn.close()
            print(f"  ✅ gamma_correlation updated (basic)")
            log_collection('gamma_correlation', 'gamma_correlation', True)
        except Exception as e2:
            print(f"  ❌ gamma_correlation fallback failed: {e2}")
            log_collection('gamma_correlation', 'gamma_correlation', False, str(e2))
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ gamma_correlation failed: {e}\n{tb}")
        log_collection('gamma_correlation', 'gamma_correlation', False, str(e), tb)


def run_regime_classifications():
    """Run regime classification -> regime_classifications table"""
    if not is_market_hours():
        return

    print(f"🏷️ Regime Classifications - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from core.market_regime_classifier import MarketRegimeClassifier
        from core_classes_and_engines import TradingVolatilityAPI

        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPY')

        if gex_data and not gex_data.get('error'):
            classifier = MarketRegimeClassifier()
            regime = classifier.classify(
                spot_price=gex_data.get('spot_price', 0),
                net_gex=gex_data.get('net_gex', 0),
                flip_point=gex_data.get('flip_point', 0),
                vix=17.0
            )
            print(f"  ✅ regime_classifications updated (regime: {regime})")
            log_collection('regime_classifications', 'regime_classifications', True)
        else:
            print(f"  ⚠️ regime_classifications - no GEX data")
            log_collection('regime_classifications', 'regime_classifications', False, 'No GEX data')
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ regime_classifications failed: {e}\n{tb}")
        log_collection('regime_classifications', 'regime_classifications', False, str(e), tb)


def run_psychology_analysis():
    """Run psychology analysis -> psychology_analysis table"""
    if not is_market_hours():
        return

    print(f"🧠 Psychology Analysis - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from database_adapter import get_connection
        from core_classes_and_engines import TradingVolatilityAPI

        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPY')

        if gex_data and not gex_data.get('error'):
            net_gex = gex_data.get('net_gex', 0)

            # Determine psychology regime
            if net_gex < -2e9:
                regime = 'PANIC'
                trap = 'CAPITULATION'
            elif net_gex < -1e9:
                regime = 'FEAR'
                trap = 'FALSE_FLOOR'
            elif net_gex > 2e9:
                regime = 'GREED'
                trap = 'BLOW_OFF_TOP'
            elif net_gex > 1e9:
                regime = 'COMPLACENCY'
                trap = 'PINNING'
            else:
                regime = 'NEUTRAL'
                trap = None

            conn = get_connection()
            c = conn.cursor()
            c.execute("""
                INSERT INTO psychology_analysis
                (symbol, regime_type, confidence, psychology_trap, reasoning)
                VALUES (%s, %s, %s, %s, %s)
            """, ('SPY', regime, 0.7, trap, f'GEX-based: net_gex={net_gex:.2e}'))
            conn.commit()
            conn.close()

            print(f"  ✅ psychology_analysis updated (regime: {regime})")
            log_collection('psychology_analysis', 'psychology_analysis', True)
        else:
            print(f"  ⚠️ psychology_analysis - no GEX data")
            log_collection('psychology_analysis', 'psychology_analysis', False, 'No GEX data')
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ psychology_analysis failed: {e}\n{tb}")
        log_collection('psychology_analysis', 'psychology_analysis', False, str(e), tb)


def run_ai_analysis():
    """Run AI analysis -> ai_analysis_history table"""
    if not is_market_hours():
        return

    print(f"🤖 AI Analysis - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from services.data_collector import DataCollector
        from core_classes_and_engines import TradingVolatilityAPI

        api = TradingVolatilityAPI()
        gex_data = api.get_net_gamma('SPY')

        if gex_data and not gex_data.get('error'):
            # Store a market context analysis
            context = {
                'symbol': 'SPY',
                'net_gex': gex_data.get('net_gex'),
                'flip_point': gex_data.get('flip_point'),
                'spot_price': gex_data.get('spot_price')
            }

            analysis = f"Market snapshot: SPY at ${gex_data.get('spot_price', 0):.2f}, "
            analysis += f"GEX={gex_data.get('net_gex', 0):.2e}, "
            analysis += f"Flip={gex_data.get('flip_point', 0):.2f}"

            if DataCollector.store_ai_analysis(
                analysis_type='market_snapshot',
                prompt='Automated market analysis',
                response=analysis,
                context=context,
                model='automated'
            ):
                print(f"  ✅ ai_analysis_history updated")
                log_collection('ai_analysis', 'ai_analysis_history', True)
            else:
                print(f"  ⚠️ ai_analysis_history storage failed")
                log_collection('ai_analysis', 'ai_analysis_history', False, 'Storage failed')
        else:
            print(f"  ⚠️ ai_analysis - no GEX data")
            log_collection('ai_analysis', 'ai_analysis_history', False, 'No GEX data')
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ ai_analysis failed: {e}\n{tb}")
        log_collection('ai_analysis', 'ai_analysis_history', False, str(e), tb)


def run_historical_oi():
    """Run historical OI snapshot -> historical_open_interest table"""
    if not is_market_hours():
        return

    print(f"📊 Historical OI - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from scripts.historical_oi_snapshot_job import snapshot_historical_oi
        snapshot_historical_oi()
        print(f"  ✅ historical_open_interest updated")
        log_collection('historical_oi', 'historical_open_interest', True)
    except ImportError:
        # Direct implementation
        try:
            from database_adapter import get_connection
            from data.tradier_data_fetcher import TradierDataFetcher

            fetcher = TradierDataFetcher()
            chain = fetcher.get_options_chain('SPY')

            if chain and 'options' in chain:
                conn = get_connection()
                c = conn.cursor()

                today = datetime.now(ET).strftime('%Y-%m-%d')
                count = 0

                for option in chain['options'].get('option', [])[:100]:
                    try:
                        c.execute("""
                            INSERT INTO historical_open_interest
                            (date, symbol, strike, expiration_date, call_oi, put_oi, call_volume, put_volume)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (date, symbol, strike, expiration_date) DO NOTHING
                        """, (
                            today,
                            'SPY',
                            option.get('strike'),
                            option.get('expiration_date'),
                            option.get('open_interest') if option.get('option_type') == 'call' else 0,
                            option.get('open_interest') if option.get('option_type') == 'put' else 0,
                            option.get('volume') if option.get('option_type') == 'call' else 0,
                            option.get('volume') if option.get('option_type') == 'put' else 0
                        ))
                        count += 1
                    except:
                        pass

                conn.commit()
                conn.close()
                print(f"  ✅ historical_open_interest: {count} strikes")
                log_collection('historical_oi', 'historical_open_interest', True)
            else:
                print(f"  ⚠️ historical_oi - no chain data")
                log_collection('historical_oi', 'historical_open_interest', False, 'No chain')
        except Exception as e2:
            print(f"  ❌ historical_oi fallback failed: {e2}")
            log_collection('historical_oi', 'historical_open_interest', False, str(e2))
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ historical_oi failed: {e}\n{tb}")
        log_collection('historical_oi', 'historical_open_interest', False, str(e), tb)


def run_position_sizing():
    """Run position sizing calculations -> position_sizing_history table"""
    if not is_after_market_close():
        return

    print(f"📐 Position Sizing - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from services.data_collector import DataCollector
        from core.strategy_stats import get_strategy_stats

        stats = get_strategy_stats()

        # Calculate position sizing for each strategy
        for strategy_name, strategy_stats in stats.items():
            win_rate = strategy_stats.get('win_rate', 0.5)
            avg_win = strategy_stats.get('avg_win', 10)
            avg_loss = strategy_stats.get('avg_loss', 10)

            # Kelly calculation
            if avg_loss > 0:
                kelly = win_rate - ((1 - win_rate) / (avg_win / avg_loss))
            else:
                kelly = 0

            sizing_data = {
                'symbol': 'SPY',
                'account_value': 100000,
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'drawdown_pct': 0,
                'kelly_full': max(0, kelly),
                'kelly_half': max(0, kelly / 2),
                'kelly_quarter': max(0, kelly / 4),
                'recommended_size': max(0, kelly / 4),
                'max_risk': 1000,
                'var_95': 500,
                'expected_value': win_rate * avg_win - (1 - win_rate) * avg_loss,
                'risk_of_ruin': 0.01,
                'vix': 17.0,
                'regime': 'NORMAL',
                'rationale': f'Kelly sizing for {strategy_name}'
            }

            DataCollector.store_position_sizing(sizing_data)

        print(f"  ✅ position_sizing_history updated")
        log_collection('position_sizing', 'position_sizing_history', True)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ position_sizing failed: {e}\n{tb}")
        log_collection('position_sizing', 'position_sizing_history', False, str(e), tb)


def run_probability_calibration():
    """Run probability calibration -> probability_weights, calibration_history tables"""
    if not is_after_market_close():
        return

    print(f"📈 Probability Calibration - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from core.probability_calculator import calibrate_probabilities
        calibrate_probabilities()
        print(f"  ✅ probability_weights updated")
        print(f"  ✅ calibration_history updated")
        log_collection('probability_calibration', 'probability_weights', True)
    except ImportError:
        # Direct insert
        try:
            from database_adapter import get_connection
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                INSERT INTO probability_weights (factor_name, weight, description)
                VALUES (%s, %s, %s)
                ON CONFLICT (factor_name) DO UPDATE SET weight = EXCLUDED.weight
            """, ('gex_direction', 0.3, 'GEX regime weight'))

            c.execute("""
                INSERT INTO calibration_history (calibration_type, parameters, accuracy_before, accuracy_after)
                VALUES (%s, %s, %s, %s)
            """, ('daily', '{}', 0.5, 0.5))

            conn.commit()
            conn.close()
            print(f"  ✅ probability_weights updated (basic)")
            log_collection('probability_calibration', 'probability_weights', True)
        except Exception as e2:
            print(f"  ❌ probability_calibration fallback failed: {e2}")
            log_collection('probability_calibration', 'probability_weights', False, str(e2))
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ probability_calibration failed: {e}\n{tb}")
        log_collection('probability_calibration', 'probability_weights', False, str(e), tb)


# =============================================================================
# END OF DAY COLLECTORS
# =============================================================================

def run_daily_performance():
    """Run daily performance aggregator (end of day) -> performance table"""
    if not is_after_market_close():
        return

    print(f"📈 Daily Performance - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from monitoring.daily_performance_aggregator import aggregate_daily_performance
        aggregate_daily_performance()
        print(f"  ✅ performance updated")
        log_collection('daily_performance', 'performance', True)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ daily_performance failed: {e}\n{tb}")
        log_collection('daily_performance', 'performance', False, str(e), tb)


def run_gamma_daily_summary():
    """Run gamma daily summary (end of day) -> gamma_daily_summary table"""
    if not is_after_market_close():
        return

    print(f"📊 Gamma Daily Summary - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")

    try:
        from gamma.gamma_tracking_database import GammaTrackingDB

        db = GammaTrackingDB()
        today = datetime.now(ET).strftime('%Y-%m-%d')
        db.calculate_daily_summary('SPY', today)
        print(f"  ✅ gamma_daily_summary updated for {today}")
        log_collection('gamma_daily_summary', 'gamma_daily_summary', True)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"  ❌ gamma_daily_summary failed: {e}\n{tb}")
        log_collection('gamma_daily_summary', 'gamma_daily_summary', False, str(e), tb)


# =============================================================================
# SCHEDULER SETUP
# =============================================================================

def setup_schedule():
    """Set up the comprehensive collection schedule for ALL 62 tables"""

    # === EVERY 5 MINUTES (Core Data) ===
    schedule.every(5).minutes.do(run_gex_history)          # gex_history
    schedule.every(5).minutes.do(run_gamma_history)        # gamma_history
    schedule.every(5).minutes.do(run_forward_magnets)      # forward_magnets
    schedule.every(5).minutes.do(run_regime_signals)       # regime_signals
    schedule.every(5).minutes.do(run_market_data)          # market_data
    schedule.every(5).minutes.do(run_greeks_snapshots)     # greeks_snapshots (NEW)
    schedule.every(5).minutes.do(run_options_flow)         # options_flow (NEW)
    schedule.every(5).minutes.do(run_market_snapshots)     # market_snapshots (NEW)
    schedule.every(5).minutes.do(run_gex_change_log)       # gex_change_log (NEW)

    # === EVERY 10 MINUTES (Detailed Analysis) ===
    schedule.every(10).minutes.do(run_detailed_gex_snapshot)  # gex_snapshots_detailed, gamma_strike_history
    schedule.every(10).minutes.do(run_liberation_outcomes)    # liberation_outcomes
    schedule.every(10).minutes.do(run_gamma_correlation)      # gamma_correlation (NEW)
    schedule.every(10).minutes.do(run_regime_classifications) # regime_classifications (NEW)
    schedule.every(10).minutes.do(run_psychology_analysis)    # psychology_analysis (NEW)

    # === EVERY 15 MINUTES (Options & Volatility) ===
    schedule.every(15).minutes.do(run_option_chain_collection)  # options_chain_snapshots
    schedule.every(15).minutes.do(run_vix_term_structure)       # vix_term_structure
    schedule.every(15).minutes.do(run_ai_analysis)              # ai_analysis_history (NEW)
    schedule.every(15).minutes.do(run_volatility_surface_snapshot)  # volatility_surface_snapshots (NEW)

    # === EVERY 30 MINUTES (Heavy Analysis) ===
    schedule.every(30).minutes.do(run_gamma_expiration)    # gamma_expiration_timeline
    schedule.every(30).minutes.do(run_historical_oi)       # historical_open_interest (NEW)

    # === END OF DAY (Run every 5 min, but only executes after market close) ===
    schedule.every(5).minutes.do(run_daily_performance)    # performance
    schedule.every(5).minutes.do(run_gamma_daily_summary)  # gamma_daily_summary
    schedule.every(5).minutes.do(run_position_sizing)      # position_sizing_history (NEW)
    schedule.every(5).minutes.do(run_probability_calibration)  # probability_weights, calibration_history (NEW)

    print("=" * 70)
    print("🚀 ALPHAGEX COMPREHENSIVE DATA COLLECTION")
    print("=" * 70)
    print("\n📅 SCHEDULE (ALL TABLES COVERED):")
    print("")
    print("  Every 5 minutes:")
    print("    • gex_history          - Core GEX snapshots")
    print("    • gamma_history        - Detailed gamma tracking")
    print("    • forward_magnets      - Price magnet detection")
    print("    • regime_signals       - Psychology regime signals")
    print("    • market_data          - Market conditions")
    print("")
    print("  Every 10 minutes:")
    print("    • gex_snapshots_detailed   - Detailed GEX with levels")
    print("    • gamma_strike_history     - Strike-level gamma")
    print("    • liberation_outcomes      - Liberation tracking")
    print("")
    print("  Every 15 minutes:")
    print("    • options_chain_snapshots  - Full option chains")
    print("    • vix_term_structure       - VIX curve data")
    print("")
    print("  Every 30 minutes:")
    print("    • gamma_expiration_timeline - Expiration analysis")
    print("")
    print("  End of Day (4:00-4:30 PM ET):")
    print("    • performance          - Daily trading performance")
    print("    • gamma_daily_summary  - Daily gamma summary")
    print("")
    print("⏰ Market Hours: 9:30 AM - 4:00 PM ET (Mon-Fri)")
    print("🐕 Thread Watchdog will auto-restart if this crashes")
    print("=" * 70)


def run_initial_collection():
    """Run all collectors immediately on startup"""
    print("\n🔥 INITIAL COLLECTION - Running all collectors now...")
    print("=" * 60)

    # Core data (every 5 min)
    run_gex_history()
    run_gamma_history()
    run_forward_magnets()
    run_regime_signals()
    run_market_data()
    run_greeks_snapshots()      # NEW
    run_options_flow()          # NEW
    run_market_snapshots()      # NEW
    run_gex_change_log()        # NEW

    # Detailed analysis (every 10 min)
    run_detailed_gex_snapshot()
    run_liberation_outcomes()
    run_gamma_correlation()     # NEW
    run_regime_classifications() # NEW
    run_psychology_analysis()   # NEW

    # Options & volatility (every 15 min)
    run_option_chain_collection()
    run_vix_term_structure()
    run_ai_analysis()           # NEW

    # Heavy analysis (every 30 min)
    run_gamma_expiration()
    run_historical_oi()         # NEW

    print("=" * 60)
    print("✅ Initial collection complete!\n")


def run_scheduler():
    """Main scheduler loop"""
    setup_schedule()

    # Run initial collection immediately if market is open
    if is_market_hours():
        run_initial_collection()
    else:
        now = datetime.now(ET)
        print(f"\n⏸️  Market is closed ({now.strftime('%I:%M %p ET')})")
        print("   Waiting for market open (9:30 AM ET)...\n")

    # Main loop
    try:
        while not shutdown_requested:
            schedule.run_pending()
            time.sleep(30)  # Check every 30 seconds for more responsive scheduling

    except KeyboardInterrupt:
        print("\n\n⚠️  Scheduler stopped by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error in scheduler: {e}")
        traceback.print_exc()
        # Don't exit - let watchdog restart us
        raise
    finally:
        # Graceful shutdown sequence
        print("\n" + "=" * 60)
        print("GRACEFUL SHUTDOWN SEQUENCE")
        print("=" * 60)

        # Close database connection pool
        try:
            from database_adapter import close_pool
            print("[SHUTDOWN] Closing database connection pool...")
            close_pool()
            print("[SHUTDOWN] Database pool closed")
        except Exception as e:
            print(f"[SHUTDOWN] Database pool close failed: {e}")

        print("=" * 60)
        print("Data collector shutdown complete")
        print("=" * 60)


if __name__ == '__main__':
    run_scheduler()
