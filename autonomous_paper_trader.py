"""
Autonomous Paper Trader - Fully Automated SPY Trading
Finds and executes trades automatically with ZERO manual intervention
Starting capital: $5,000

CRITICAL INTEGRATION: Uses full Psychology Trap Detection System
- Multi-timeframe RSI analysis (5m, 15m, 1h, 4h, 1d)
- Gamma expiration timeline
- Liberation setups
- False floor detection
- Forward GEX magnets
- All psychology trap patterns
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from config_and_database import DB_PATH
from polygon_data_fetcher import polygon_fetcher
import time
import os

# Central Time timezone for all timestamps
CENTRAL_TZ = ZoneInfo("America/Chicago")

# CRITICAL: Import Psychology Trap Detector
try:
    from psychology_trap_detector import analyze_current_market_complete, save_regime_signal_to_db
    from gamma_expiration_builder import build_gamma_with_expirations
    from polygon_helper import PolygonDataFetcher as PolygonHelper
    PSYCHOLOGY_AVAILABLE = True
    print("✅ Psychology Trap Detector integrated with Autonomous Trader")
except ImportError as e:
    PSYCHOLOGY_AVAILABLE = False
    print(f"⚠️ Psychology Trap Detector not available: {e}")
    print("   Falling back to basic GEX analysis")

# CRITICAL: Import AI Reasoning Engine (LangChain + Claude)
try:
    from autonomous_ai_reasoning import get_ai_reasoning
    ai_reasoning = get_ai_reasoning()
    AI_REASONING_AVAILABLE = ai_reasoning.llm is not None
    if AI_REASONING_AVAILABLE:
        print("✅ AI Reasoning Engine (LangChain + Claude) ready")
except ImportError as e:
    AI_REASONING_AVAILABLE = False
    ai_reasoning = None
    print(f"⚠️ AI Reasoning not available: {e}")

# CRITICAL: Import Database Logger
try:
    from autonomous_database_logger import get_database_logger
    DATABASE_LOGGER_AVAILABLE = True
    print("✅ Database Logger ready for comprehensive logging")
except ImportError as e:
    DATABASE_LOGGER_AVAILABLE = False
    print(f"⚠️ Database Logger not available: {e}")


def get_real_option_price(symbol: str, strike: float, option_type: str, expiration_date: str) -> Dict:
    """Get REAL option price from Polygon.io"""
    try:
        # Use Polygon.io to get option quote
        quote = polygon_fetcher.get_option_quote(
            symbol=symbol,
            strike=strike,
            expiration=expiration_date,
            option_type=option_type
        )

        if quote is None:
            return {'error': 'No option data found from Polygon.io'}

        return quote

    except Exception as e:
        print(f"Error fetching option price from Polygon.io: {e}")
        return {'error': str(e)}


class AutonomousPaperTrader:
    """
    Fully autonomous paper trader - NO manual intervention required
    Finds and executes trades automatically every market day
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.starting_capital = 5000  # $5,000 starting capital
        self._ensure_tables()

        # CRITICAL: Initialize all components
        if DATABASE_LOGGER_AVAILABLE:
            self.db_logger = get_database_logger('autonomous_trader')
            print("✅ Database logger initialized")
        else:
            self.db_logger = None

        if AI_REASONING_AVAILABLE:
            self.ai_reasoning = ai_reasoning
            print("✅ AI reasoning engine ready")
        else:
            self.ai_reasoning = None

        # Initialize risk manager
        try:
            from autonomous_risk_manager import get_risk_manager
            self.risk_manager = get_risk_manager()
            print("✅ Risk manager initialized")
        except ImportError:
            self.risk_manager = None
            print("⚠️ Risk manager not available")

        # Initialize ML pattern learner
        try:
            from autonomous_ml_pattern_learner import get_pattern_learner
            self.ml_learner = get_pattern_learner()
            print("✅ ML pattern learner initialized")
        except ImportError:
            self.ml_learner = None
            print("⚠️ ML pattern learner not available")

        # Initialize strategy competition
        try:
            from autonomous_strategy_competition import get_competition
            self.competition = get_competition()
            print("✅ Strategy competition initialized")
        except ImportError:
            self.competition = None
            print("⚠️ Strategy competition not available")

        # Initialize if first run
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT value FROM autonomous_config WHERE key = 'initialized'")
        result = c.fetchone()

        if not result:
            # First time setup
            c.execute("INSERT INTO autonomous_config (key, value) VALUES ('capital', ?)", (str(self.starting_capital),))
            c.execute("INSERT INTO autonomous_config (key, value) VALUES ('initialized', 'true')")
            c.execute("INSERT INTO autonomous_config (key, value) VALUES ('auto_execute', 'true')")
            c.execute("INSERT INTO autonomous_config (key, value) VALUES ('last_trade_date', '')")
            c.execute("INSERT INTO autonomous_config (key, value) VALUES ('mode', 'paper')")
            conn.commit()

        conn.close()

    def _ensure_tables(self):
        """Create database tables for autonomous trading"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Positions table
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                action TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                strike REAL NOT NULL,
                option_type TEXT NOT NULL,
                expiration_date TEXT NOT NULL,
                contracts INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                entry_bid REAL,
                entry_ask REAL,
                entry_spot_price REAL,
                current_price REAL,
                current_spot_price REAL,
                unrealized_pnl REAL,
                status TEXT DEFAULT 'OPEN',
                closed_date TEXT,
                closed_time TEXT,
                exit_price REAL,
                realized_pnl REAL,
                exit_reason TEXT,
                confidence INTEGER,
                gex_regime TEXT,
                entry_net_gex REAL,
                entry_flip_point REAL,
                trade_reasoning TEXT,
                contract_symbol TEXT
            )
        """)

        # Trade log (daily summaries)
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                position_id INTEGER,
                success INTEGER DEFAULT 1
            )
        """)

        # Config table
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Live status table - what the trader is thinking RIGHT NOW
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_live_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                current_action TEXT,
                market_analysis TEXT,
                next_check_time TEXT,
                last_decision TEXT,
                is_working INTEGER DEFAULT 1
            )
        """)

        # Initialize live status if not exists
        c.execute("SELECT COUNT(*) FROM autonomous_live_status WHERE id = 1")
        if c.fetchone()[0] == 0:
            c.execute("""
                INSERT INTO autonomous_live_status (id, timestamp, status, current_action, is_working)
                VALUES (1, ?, 'INITIALIZING', 'System starting up...', 1)
            """, (datetime.now(CENTRAL_TZ).isoformat(),))

        conn.commit()
        conn.close()

    def get_config(self, key: str) -> str:
        """Get configuration value"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT value FROM autonomous_config WHERE key = ?", (key,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else "0"

    def set_config(self, key: str, value: str):
        """Set configuration value"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO autonomous_config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

    def update_live_status(self, status: str, action: str, analysis: str = None, decision: str = None):
        """
        Update live status - THINKING OUT LOUD
        This is what lets you see what the trader is doing in real-time
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        now_ct = datetime.now(CENTRAL_TZ)
        next_check = (now_ct + timedelta(minutes=5)).isoformat()

        c.execute("""
            UPDATE autonomous_live_status
            SET timestamp = ?,
                status = ?,
                current_action = ?,
                market_analysis = ?,
                next_check_time = ?,
                last_decision = ?,
                is_working = 1
            WHERE id = 1
        """, (now_ct.isoformat(), status, action, analysis, next_check, decision))

        conn.commit()
        conn.close()

        # Also print to console for logs
        print(f"\n{'='*80}")
        print(f"🤖 TRADER STATUS: {status}")
        print(f"📋 ACTION: {action}")
        if analysis:
            print(f"📊 ANALYSIS: {analysis}")
        if decision:
            print(f"🎯 DECISION: {decision}")
        print(f"{'='*80}\n")

    def get_live_status(self) -> Dict:
        """Get current live status"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM autonomous_live_status WHERE id = 1")
        row = c.fetchone()
        conn.close()

        if not row:
            return {
                'status': 'UNKNOWN',
                'current_action': 'System not initialized',
                'is_working': False
            }

        return {
            'timestamp': row[1],
            'status': row[2],
            'current_action': row[3],
            'market_analysis': row[4],
            'next_check_time': row[5],
            'last_decision': row[6],
            'is_working': bool(row[7])
        }

    def log_action(self, action: str, details: str, position_id: int = None, success: bool = True):
        """Log trading actions"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        now = datetime.now(CENTRAL_TZ)
        c.execute("""
            INSERT INTO autonomous_trade_log (date, time, action, details, position_id, success)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            now.strftime('%Y-%m-%d'),
            now.strftime('%H:%M:%S'),
            action,
            details,
            position_id,
            1 if success else 0
        ))

        conn.commit()
        conn.close()

    def should_trade_today(self) -> bool:
        """Check if we should find a new trade - allows multiple trades per day within risk limits"""
        now = datetime.now(CENTRAL_TZ)

        # Check if market is open (simple check - Monday-Friday)
        if now.weekday() >= 5:  # Saturday or Sunday
            return False

        # Check risk limits instead of arbitrary daily trade count
        # Risk Manager will block trades if:
        # - Daily loss limit exceeded
        # - Max position size exceeded
        # - Max drawdown exceeded
        # - Too many open positions

        # Get today's P&L and check daily loss limit
        today = now.strftime('%Y-%m-%d')
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Count open positions - respect max open positions limit
        c.execute("SELECT COUNT(*) FROM autonomous_positions WHERE status = 'OPEN'")
        open_positions = c.fetchone()[0]
        max_positions = 10  # Configurable limit

        if open_positions >= max_positions:
            conn.close()
            return False  # Too many open positions

        # Check today's P&L - respect daily loss limit
        c.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0) + COALESCE(SUM(unrealized_pnl), 0) as total_pnl
            FROM autonomous_positions
            WHERE entry_date = ?
        """, (today,))
        today_pnl = c.fetchone()[0]
        conn.close()

        # Get starting capital
        capital = float(self.get_config('capital'))
        daily_loss_limit_pct = 5.0  # 5% daily loss limit
        daily_loss_limit = capital * (daily_loss_limit_pct / 100)

        if today_pnl < -daily_loss_limit:
            return False  # Daily loss limit exceeded

        # All risk checks passed - can trade
        return True

    def get_available_capital(self) -> float:
        """Calculate available capital"""
        total_capital = float(self.get_config('capital'))

        # Get current open positions value
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT SUM(ABS(entry_price * contracts * 100)) as used
            FROM autonomous_positions
            WHERE status = 'OPEN'
        """
        result = pd.read_sql_query(query, conn)
        conn.close()

        used = result.iloc[0]['used'] if not pd.isna(result.iloc[0]['used']) else 0
        return total_capital - used

    def find_and_execute_daily_trade(self, api_client) -> Optional[int]:
        """
        AUTONOMOUS: Find and execute today's best trade automatically

        MINIMUM ONE TRADE PER DAY GUARANTEE:
        This method implements a multi-level fallback system to ensure AT LEAST one trade
        executes every single day during market hours:

        1. PRIMARY: High-confidence directional trade (calls/puts) if GEX setup exists
        2. FALLBACK L1: Iron Condor for premium collection if no directional setup
        3. FALLBACK L2: ATM Straddle as final guarantee (simple, minimal failure points)

        Returns position ID if successful (should ALWAYS return a position ID)
        """

        # CRITICAL: Log scan start with database logger
        if self.db_logger:
            spot_price = 0
            try:
                gex_preview = api_client.get_net_gamma('SPY')
                spot_price = gex_preview.get('spot_price', 0) if gex_preview else 0
            except:
                pass

            self.db_logger.log_scan_start(
                symbol='SPY',
                spot_price=spot_price,
                market_context={'scan_type': 'daily_trade_search'}
            )

        # Update status: Starting trade search
        self.update_live_status(
            status='SEARCHING',
            action='Starting daily trade search...',
            analysis='Checking if we should trade today'
        )

        # Check if we should trade today
        if not self.should_trade_today():
            self.update_live_status(
                status='IDLE',
                action='Waiting for next trading opportunity',
                decision='Already traded today or market closed'
            )
            self.log_action('SKIP', 'Already traded today or market closed', success=True)
            return None

        self.log_action('START', 'Beginning daily trade search')
        self.update_live_status(
            status='ANALYZING',
            action='Fetching market data and analyzing GEX regime...',
            analysis='Connecting to Trading Volatility API for SPY data'
        )

        try:
            # Step 1: Get SPY GEX data + Enhanced market data
            gex_data = api_client.get_net_gamma('SPY')
            skew_data = api_client.get_skew_data('SPY')

            if not gex_data or gex_data.get('error'):
                self.update_live_status(
                    status='ERROR',
                    action='Failed to fetch market data',
                    decision='Will retry on next cycle'
                )
                self.log_action('ERROR', 'Failed to get GEX data', success=False)
                return None

            spot_price = gex_data.get('spot_price', 0)
            net_gex = gex_data.get('net_gex', 0)
            flip_point = gex_data.get('flip_point', 0)

            # Step 1b: Get VIX, momentum, and market context
            vix = self._get_vix()
            momentum = self._get_momentum()
            time_context = self._get_time_context()
            put_call_ratio = skew_data.get('put_call_ratio', 1.0) if skew_data else 1.0

            if spot_price == 0:
                self.update_live_status(
                    status='ERROR',
                    action='Invalid market data received',
                    decision='Will retry on next cycle'
                )
                self.log_action('ERROR', 'Invalid spot price', success=False)
                return None

            # Update with market analysis
            market_summary = f"SPY ${spot_price:.2f} | GEX: ${net_gex/1e9:.2f}B | Flip: ${flip_point:.2f} | VIX: {vix:.1f} | Momentum: {momentum.get('trend', 'neutral')} ({momentum.get('4h', 0):+.1f}%)"
            self.update_live_status(
                status='ANALYZING',
                action='Analyzing GEX regime and finding optimal trade setup...',
                analysis=market_summary
            )

            # Step 2: Try to find high-confidence directional trade (with enhanced data)
            trade = self._analyze_and_find_trade(gex_data, skew_data, spot_price, vix, momentum, time_context, put_call_ratio)

            # CRITICAL LOGGING: Log what strategy analysis returned
            if trade:
                self.log_action(
                    'STRATEGY_FOUND',
                    f"✅ Strategy analysis found: {trade.get('strategy', 'Unknown')} "
                    f"(Action: {trade.get('action')}, Confidence: {trade.get('confidence', 0)}%, "
                    f"Strike: ${trade.get('strike', 0):.0f})",
                    success=True
                )
            else:
                self.log_action(
                    'NO_STRATEGY',
                    f"❌ Strategy analysis returned None. "
                    f"GEX: ${net_gex/1e9:.2f}B, Spot: ${spot_price:.2f}, "
                    f"Flip: ${flip_point:.2f}, VIX: {vix:.1f}",
                    success=False
                )

            # Log detailed analysis of what was evaluated
            if trade:
                confidence = trade.get('confidence', 0)
                analysis_details = (
                    f"MARKET ANALYSIS:\n"
                    f"• SPY Price: ${spot_price:.2f}\n"
                    f"• Net GEX: ${net_gex/1e9:.2f}B {'(SHORT GAMMA - Amplification)' if net_gex < 0 else '(LONG GAMMA - Dampening)'}\n"
                    f"• Flip Point: ${flip_point:.2f} ({((flip_point-spot_price)/spot_price*100):+.1f}% from spot)\n"
                    f"• VIX: {vix:.1f} {'(Elevated)' if vix > 20 else '(Normal)' if vix > 15 else '(Low)'}\n"
                    f"• Momentum: {momentum.get('trend', 'neutral')} ({momentum.get('4h', 0):+.1f}% 4h move)\n"
                    f"• Put/Call Ratio: {put_call_ratio:.2f}\n\n"
                    f"SETUP FOUND:\n"
                    f"• Strategy: {trade.get('strategy', 'Unknown')}\n"
                    f"• Action: {trade.get('action', 'Unknown')}\n"
                    f"• Strike: ${trade.get('strike', 0):.0f}\n"
                    f"• Confidence: {confidence}%\n\n"
                    f"DECISION: {'✅ EXECUTING (meets 70%+ threshold)' if confidence >= 70 else '❌ SKIPPING (below 70% threshold)'}"
                )
                self.log_action(
                    'ANALYSIS',
                    analysis_details,
                    success=True
                )

            # GUARANTEED TRADE - MINIMUM ONE PER DAY: Multi-level fallback system
            if not trade or trade.get('confidence', 0) < 70:
                # CRITICAL LOGGING: Explain EXACTLY why we're falling back
                if not trade:
                    reason = "❌ NO STRATEGY FOUND - _analyze_and_find_trade() returned None"
                    self.log_action(
                        'FALLBACK_REASON',
                        f"{reason}\n"
                        f"Market Data:\n"
                        f"• GEX: ${net_gex/1e9:.2f}B\n"
                        f"• Spot: ${spot_price:.2f}\n"
                        f"• Flip: ${flip_point:.2f}\n"
                        f"• VIX: {vix:.1f}\n"
                        f"• Momentum: {momentum.get('trend', 'N/A')} ({momentum.get('4h', 0):+.1f}%)\n"
                        f"This suggests strategy analysis logic has a bug.",
                        success=False
                    )
                else:
                    reason = f"⚠️ CONFIDENCE TOO LOW: {trade.get('confidence', 0)}% < 70% threshold"
                    self.log_action(
                        'FALLBACK_REASON',
                        f"{reason}\n"
                        f"Strategy Found: {trade.get('strategy')}\n"
                        f"Action: {trade.get('action')}\n"
                        f"Strike: ${trade.get('strike', 0):.0f}\n"
                        f"Reasoning: {trade.get('reasoning', 'N/A')[:200]}...\n\n"
                        f"Consider lowering confidence threshold OR improving confidence scoring.",
                        success=True
                    )

                self.log_action(
                    'FALLBACK_DECISION',
                    f"FALLBACK STRATEGY: Trying Iron Condor for premium collection. "
                    f"IC provides positive expectancy in neutral/uncertain market conditions.",
                    success=True
                )

                self.update_live_status(
                    status='EXECUTING',
                    action='No high-confidence directional setup found',
                    analysis=market_summary,
                    decision='Falling back to Iron Condor for premium collection'
                )
                self.log_action('FALLBACK_L1', 'No high-confidence directional setup - trying Iron Condor')

                # Level 1 Fallback: Iron Condor
                position_id = self._execute_iron_condor(spot_price, gex_data, api_client)

                if position_id:
                    return position_id

                # Level 2 Fallback: If Iron Condor fails, execute simple ATM straddle
                self.log_action('FALLBACK_L2', 'Iron Condor failed - executing ATM Straddle as final guarantee')
                self.update_live_status(
                    status='EXECUTING',
                    action='Executing guaranteed daily trade',
                    decision='ATM Straddle fallback (MINIMUM one trade per day guarantee)'
                )
                return self._execute_atm_straddle_fallback(spot_price, api_client)

            # Step 3: Execute directional trade (calls/puts)
            self.update_live_status(
                status='EXECUTING',
                action=f'Found {trade["strategy"]} setup (confidence: {trade["confidence"]}%)',
                analysis=market_summary,
                decision=f'Executing {trade["action"]} at ${trade["strike"]:.0f}'
            )
            position_id = self._execute_directional_trade(trade, gex_data, api_client)

            # GUARANTEE CHECK: If directional trade failed, ensure we still get a trade
            if not position_id:
                self.log_action('FALLBACK_L1', 'Directional trade execution failed - trying Iron Condor')
                position_id = self._execute_iron_condor(spot_price, gex_data, api_client)

                if not position_id:
                    self.log_action('FALLBACK_L2', 'Iron Condor failed - executing ATM Straddle as final guarantee')
                    position_id = self._execute_atm_straddle_fallback(spot_price, api_client)

            return position_id

        except Exception as e:
            self.update_live_status(
                status='ERROR',
                action='System error during trade execution',
                decision=f'Error: {str(e)[:100]}'
            )
            self.log_action('ERROR', f'Exception in trade execution: {str(e)}', success=False)
            import traceback
            traceback.print_exc()
            return None

    def _execute_directional_trade(self, trade: Dict, gex_data: Dict, api_client) -> Optional[int]:
        """Execute directional call/put trade with AI reasoning and risk checks"""
        try:
            spot_price = gex_data.get('spot_price', 0)

            # CRITICAL: Use AI reasoning for strike selection
            if self.ai_reasoning:
                try:
                    # Get alternative strikes to consider
                    base_strike = trade['strike']
                    alternative_strikes = [
                        base_strike - 10,
                        base_strike - 5,
                        base_strike,
                        base_strike + 5,
                        base_strike + 10
                    ]

                    strike_analysis = self.ai_reasoning.analyze_strike_selection(
                        regime=trade.get('regime', {}),
                        spot_price=spot_price,
                        alternative_strikes=alternative_strikes
                    )

                    if strike_analysis and strike_analysis.get('recommended_strike'):
                        # Use AI-recommended strike
                        ai_strike = strike_analysis['recommended_strike']
                        if ai_strike in alternative_strikes:
                            trade['strike'] = ai_strike

                        # Log AI strike selection reasoning
                        if self.db_logger:
                            self.db_logger.log_strike_selection(
                                symbol='SPY',
                                strike_analysis=strike_analysis,
                                spot_price=spot_price
                            )

                        ai_strike_log = f"""
🎯 AI STRIKE SELECTION:
• Recommended Strike: ${strike_analysis['recommended_strike']:.0f}
• Confidence: {strike_analysis.get('confidence', 'N/A')}
• Reasoning: {strike_analysis.get('reasoning', 'See analysis')}
"""
                        self.log_action('AI_STRIKE', ai_strike_log, success=True)

                except Exception as e:
                    self.log_action('AI_ERROR', f'AI strike selection failed: {e}', success=False)

            # Get REAL option price
            exp_date = self._get_expiration_string(trade['dte'])
            option_price_data = get_real_option_price(
                'SPY',
                trade['strike'],
                trade['option_type'],
                exp_date
            )

            if option_price_data.get('error'):
                self.log_action('ERROR', f"Failed to get option price: {option_price_data.get('error')}", success=False)
                return None

            # Calculate position size for $5K account
            entry_price = option_price_data['mid']
            if entry_price == 0:
                entry_price = option_price_data.get('last', 1.0)

            available = self.get_available_capital()

            # CRITICAL: Validate entry_price before any calculations to prevent division by zero
            cost_per_contract = entry_price * 100
            if cost_per_contract == 0:
                self.log_action('ERROR', 'Invalid option price (zero)', success=False)
                return None

            # CRITICAL: Use AI reasoning for position sizing
            contracts = 1  # Default
            if self.ai_reasoning:
                try:
                    # Get historical win rate from performance
                    perf = self.get_performance()
                    win_rate = perf.get('win_rate', 60) / 100  # Convert to decimal

                    # Estimate risk/reward
                    target = trade.get('target', trade['strike'] * 1.02)
                    risk_reward = abs(target - spot_price) / abs(trade['strike'] - spot_price) if abs(trade['strike'] - spot_price) > 0 else 1.5

                    sizing_analysis = self.ai_reasoning.analyze_position_sizing(
                        account_size=available,
                        win_rate=win_rate,
                        risk_reward=risk_reward,
                        trade_confidence=trade.get('confidence', 70) / 100,
                        regime=trade.get('regime', {})
                    )

                    if sizing_analysis and sizing_analysis.get('recommended_contracts'):
                        contracts = sizing_analysis['recommended_contracts']

                        # Log AI position sizing
                        if self.db_logger:
                            self.db_logger.log_position_sizing(
                                symbol='SPY',
                                sizing_analysis=sizing_analysis,
                                contracts=contracts
                            )

                        ai_sizing_log = f"""
💰 AI POSITION SIZING:
• Kelly %: {sizing_analysis.get('kelly_pct', 0):.1f}%
• Recommended Contracts: {contracts}
• Rationale: {sizing_analysis.get('sizing_rationale', 'See analysis')}
"""
                        self.log_action('AI_SIZING', ai_sizing_log, success=True)

                except Exception as e:
                    self.log_action('AI_ERROR', f'AI position sizing failed: {e}', success=False)
                    # Fall back to basic sizing (already validated cost_per_contract above)
                    max_position = min(available * 0.25, 1250)
                    contracts = max(1, int(max_position / cost_per_contract))
            else:
                # Basic position sizing if AI not available (already validated cost_per_contract above)
                max_position = min(available * 0.25, 1250)
                contracts = max(1, int(max_position / cost_per_contract))

            contracts = min(contracts, 10)  # Max 10 contracts for $5K account
            total_cost = contracts * entry_price * 100

            # CRITICAL: Check risk manager limits before executing
            if self.risk_manager:
                try:
                    current_value = available + total_cost  # Approximate account value
                    proposed_trade = {
                        'symbol': 'SPY',
                        'cost': total_cost
                    }

                    can_trade, risk_reason = self.risk_manager.check_all_limits(current_value, proposed_trade)

                    if not can_trade:
                        self.log_action('RISK_BLOCK', f'Trade blocked by risk manager: {risk_reason}', success=False)
                        if self.db_logger:
                            self.db_logger.log_trade_decision(
                                symbol='SPY',
                                action='BLOCKED',
                                strategy=trade.get('strategy', 'Unknown'),
                                reasoning=risk_reason,
                                confidence=0
                            )
                        return None

                    self.log_action('RISK_CHECK', f'✅ Risk checks passed: {risk_reason}', success=True)

                except Exception as e:
                    self.log_action('RISK_ERROR', f'Risk manager check failed: {e}', success=False)

            # Execute trade automatically
            # Get VIX for strike/Greeks logging
            vix = self._get_vix()
            position_id = self._execute_trade(
                trade, option_price_data, contracts, entry_price,
                exp_date, gex_data, vix, trade.get('regime')
            )

            if position_id:
                # Update last trade date
                self.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))

                # Update live status with successful trade
                self.update_live_status(
                    status='TRADE_EXECUTED',
                    action=f"✅ Successfully opened {trade['strategy']}",
                    analysis=f"{contracts} contracts @ ${entry_price:.2f} (Total: ${total_cost:.2f})",
                    decision=f"Position #{position_id} is now active. Next check in 1 hour."
                )

                self.log_action(
                    'EXECUTE',
                    f"Opened {trade['strategy']}: {contracts} contracts @ ${entry_price:.2f} (${total_cost:.2f} total) | Expiration: {exp_date}",
                    position_id=position_id,
                    success=True
                )

                return position_id
            else:
                self.log_action('ERROR', 'Failed to execute trade', success=False)
                return None

        except Exception as e:
            self.log_action('ERROR', f'Directional trade failed: {str(e)}', success=False)
            return None

    def _get_vix(self) -> float:
        """Get current VIX level for volatility regime - REAL-TIME from Polygon.io"""
        try:
            # Get current VIX price from Polygon.io
            vix_price = polygon_fetcher.get_current_price('^VIX')

            if vix_price and vix_price > 0:
                print(f"✅ VIX fetched from Polygon.io: {vix_price:.2f}")
                return vix_price

            print(f"⚠️ VIX data unavailable from Polygon.io - using default 20.0")
            return 20.0  # Default neutral VIX
        except Exception as e:
            print(f"❌ Failed to fetch VIX from Polygon.io: {e}")
            return 20.0

    def _get_momentum(self) -> Dict:
        """Calculate recent momentum (1h, 4h price change) from Polygon.io"""
        try:
            # Get hourly data from Polygon.io (5 days to ensure enough data)
            data = polygon_fetcher.get_price_history('SPY', days=5, timeframe='hour', multiplier=1)

            if data is None or len(data) < 5:
                return {'1h': 0, '4h': 0, 'trend': 'neutral'}

            current_price = float(data['Close'].iloc[-1])
            price_1h_ago = float(data['Close'].iloc[-2]) if len(data) >= 2 else current_price
            price_4h_ago = float(data['Close'].iloc[-5]) if len(data) >= 5 else current_price

            change_1h = ((current_price - price_1h_ago) / price_1h_ago * 100)
            change_4h = ((current_price - price_4h_ago) / price_4h_ago * 100)

            # Determine trend
            if change_4h > 0.5:
                trend = 'strong_bullish'
            elif change_4h > 0.2:
                trend = 'bullish'
            elif change_4h < -0.5:
                trend = 'strong_bearish'
            elif change_4h < -0.2:
                trend = 'bearish'
            else:
                trend = 'neutral'

            return {
                '1h': round(change_1h, 2),
                '4h': round(change_4h, 2),
                'trend': trend
            }
        except Exception as e:
            print(f"Failed to calculate momentum from Polygon.io: {e}")
            return {'1h': 0, '4h': 0, 'trend': 'neutral'}

    def _get_time_context(self) -> Dict:
        """Get time of day context for trading"""
        now = datetime.now(CENTRAL_TZ)
        hour = now.hour
        minute = now.minute

        # Market hours context (Eastern Time approximation)
        if 9 <= hour < 10:
            session = 'opening'  # High volatility, momentum plays
            volatility_factor = 1.2
        elif 10 <= hour < 11:
            session = 'morning'  # Best for new positions
            volatility_factor = 1.0
        elif 11 <= hour < 14:
            session = 'midday'  # Lower volume, chop
            volatility_factor = 0.8
        elif 14 <= hour < 15:
            session = 'afternoon'  # Building to close
            volatility_factor = 0.9
        elif 15 <= hour < 16:
            session = 'power_hour'  # High volume, reversals
            volatility_factor = 1.3
        else:
            session = 'closed'
            volatility_factor = 0.0

        return {
            'session': session,
            'volatility_factor': volatility_factor,
            'day_of_week': now.strftime('%A')
        }

    def _analyze_and_find_trade(self, gex_data: Dict, skew_data: Dict, spot: float,
                                  vix: float = 20, momentum: Dict = None,
                                  time_context: Dict = None, put_call_ratio: float = 1.0) -> Optional[Dict]:
        """
        Analyze market using FULL Psychology Trap Detection System

        Uses ALL 5 layers:
        1. Multi-timeframe RSI analysis
        2. Current gamma walls
        3. Gamma expiration timeline (liberation/false floor)
        4. Forward GEX magnets
        5. Complete regime detection
        """

        if momentum is None:
            momentum = {'1h': 0, '4h': 0, 'trend': 'neutral'}
        if time_context is None:
            time_context = {'session': 'morning', 'volatility_factor': 1.0, 'day_of_week': 'Monday'}

        net_gex = gex_data.get('net_gex', 0)
        flip = gex_data.get('flip_point', spot)
        call_wall = gex_data.get('call_wall', 0)
        put_wall = gex_data.get('put_wall', 0)

        distance_to_flip = ((flip - spot) / spot * 100) if spot else 0

        # Enhanced scoring factors
        vix_regime = 'high' if vix > 25 else 'low' if vix < 15 else 'normal'
        momentum_trend = momentum.get('trend', 'neutral')
        momentum_4h = momentum.get('4h', 0)
        session = time_context.get('session', 'morning')
        vol_factor = time_context.get('volatility_factor', 1.0)

        # ============================================================
        # CRITICAL: USE PSYCHOLOGY TRAP DETECTOR
        # ============================================================
        if PSYCHOLOGY_AVAILABLE:
            try:
                self.log_action('PSYCHOLOGY_SCAN', '🧠 Running full psychology trap analysis...')

                # Build gamma data with expiration timeline
                gamma_data = build_gamma_with_expirations('SPY', use_tv_api=True)

                # Fetch multi-timeframe price data
                polygon_helper = PolygonHelper()
                price_data = polygon_helper.get_multi_timeframe_data('SPY', spot)

                # Calculate volume ratio from daily data
                if len(price_data.get('1d', [])) >= 20:
                    recent_vol = price_data['1d'][-1]['volume']
                    avg_vol = sum(bar['volume'] for bar in price_data['1d'][-20:]) / 20
                    volume_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
                else:
                    volume_ratio = 1.0

                # Run complete regime detection with CORRECT function
                regime_result = analyze_current_market_complete(
                    current_price=spot,
                    price_data=price_data,
                    gamma_data=gamma_data,
                    volume_ratio=volume_ratio
                )

                if regime_result and regime_result.get('regime'):
                    regime = regime_result['regime']

                    # Extract key psychology trap signals
                    pattern = regime.get('primary_regime_type', 'UNKNOWN')
                    confidence = regime.get('confidence_score', 0)
                    trade_direction = regime.get('trade_direction', 'NEUTRAL')
                    risk_level = regime.get('risk_level', 'MEDIUM')
                    description = regime.get('description', '')
                    psychology_trap = regime.get('psychology_trap', '')

                    # Liberation setup detection
                    liberation_detected = regime.get('liberation_setup_detected', False)
                    liberation_strike = regime.get('liberation_target_strike')
                    liberation_expiry = regime.get('liberation_expiry_date')

                    # False floor detection
                    false_floor_detected = regime.get('false_floor_detected', False)
                    false_floor_strike = regime.get('false_floor_strike')
                    false_floor_expiry = regime.get('false_floor_expiry_date')

                    # Forward GEX magnets
                    forward_magnet_above = regime.get('monthly_magnet_above')
                    forward_magnet_below = regime.get('monthly_magnet_below')
                    polr = regime.get('path_of_least_resistance', 'NEUTRAL')

                    # Multi-timeframe RSI
                    rsi_aligned_overbought = regime.get('rsi_aligned_overbought', False)
                    rsi_aligned_oversold = regime.get('rsi_aligned_oversold', False)
                    rsi_coiling = regime.get('rsi_coiling', False)

                    # Log comprehensive analysis
                    analysis_log = f"""
🧠 PSYCHOLOGY TRAP ANALYSIS COMPLETE:

PATTERN: {pattern}
Confidence: {confidence:.0f}%
Risk Level: {risk_level}
Trade Direction: {trade_direction}

DESCRIPTION: {description}

PSYCHOLOGY TRAP: {psychology_trap}

GAMMA DYNAMICS:
• Liberation Setup: {'YES' if liberation_detected else 'NO'}
  {f'Strike ${liberation_strike:.0f} expires {liberation_expiry}' if liberation_detected else ''}
• False Floor: {'YES - AVOID PUTS!' if false_floor_detected else 'NO'}
  {f'Strike ${false_floor_strike:.0f} expires {false_floor_expiry}' if false_floor_detected else ''}

FORWARD GEX MAGNETS:
• Above: ${forward_magnet_above:.0f} (monthly OPEX positioning)
• Below: ${forward_magnet_below:.0f}
• Path of Least Resistance: {polr}

MULTI-TIMEFRAME RSI:
• Aligned Overbought: {'YES ⚠️' if rsi_aligned_overbought else 'NO'}
• Aligned Oversold: {'YES 📈' if rsi_aligned_oversold else 'NO'}
• Coiling: {'YES 💥' if rsi_coiling else 'NO'}
"""
                    self.log_action('PSYCHOLOGY_RESULT', analysis_log, success=True)

                    # CRITICAL: Log psychology analysis to database
                    if self.db_logger:
                        self.db_logger.log_psychology_analysis(
                            regime=regime,
                            symbol='SPY',
                            spot_price=spot
                        )

                    # CRITICAL: Save regime signal to database for backtest analysis
                    try:
                        signal_id = save_regime_signal_to_db(regime_result)
                        self.log_action(
                            'REGIME_SIGNAL',
                            f"✅ Saved regime signal to database for backtest (ID: {signal_id}): {pattern}",
                            success=True
                        )
                    except Exception as e:
                        self.log_action(
                            'REGIME_SIGNAL_ERROR',
                            f"⚠️ Failed to save regime signal: {str(e)}",
                            success=False
                        )

                    # CRITICAL: Use ML to predict pattern success and adjust confidence
                    if self.ml_learner and self.ml_learner.model is not None:
                        try:
                            ml_prediction = self.ml_learner.predict_pattern_success(regime)

                            # Log ML prediction
                            if ml_prediction:
                                original_conf = regime.get('confidence_score', 0)
                                ml_adjusted = ml_prediction.get('adjusted_confidence', original_conf)
                                ml_prob = ml_prediction.get('success_probability', 0.5)

                                ml_log = f"""
🤖 ML PATTERN PREDICTION:
• Original Confidence: {original_conf:.0f}%
• ML Success Probability: {ml_prob:.1%}
• ML-Adjusted Confidence: {ml_adjusted:.0f}%
• ML Recommendation: {ml_prediction.get('recommendation', 'TRADE')}
• ML Confidence Level: {ml_prediction.get('ml_confidence', 'UNKNOWN')}
"""
                                self.log_action('ML_PREDICTION', ml_log, success=True)

                                # Adjust regime confidence with ML prediction
                                regime['confidence_score'] = ml_adjusted
                                regime['ml_prediction'] = ml_prediction
                        except Exception as e:
                            self.log_action('ML_ERROR', f'ML prediction failed: {e}', success=False)

                    # Convert psychology signals to trade setup
                    return self._convert_psychology_to_trade(
                        regime=regime,
                        spot=spot,
                        gex_data=gex_data,
                        vix=vix,
                        momentum=momentum,
                        time_context=time_context
                    )

            except Exception as e:
                self.log_action('PSYCHOLOGY_ERROR', f'Psychology trap detector failed: {e}', success=False)
                print(f"⚠️ Psychology detector error: {e}")
                import traceback
                traceback.print_exc()
                # Fall back to basic analysis

        # ============================================================
        # FALLBACK: Basic GEX Analysis (if psychology unavailable)
        # ============================================================
        self.log_action(
            'BASIC_ANALYSIS',
            f"📊 Using Basic GEX Regime Analysis (Psychology Detector unavailable)\n"
            f"Market Conditions:\n"
            f"• Net GEX: ${net_gex/1e9:.2f}B\n"
            f"• Spot Price: ${spot:.2f}\n"
            f"• Flip Point: ${flip:.2f}\n"
            f"• Distance to Flip: {distance_to_flip:+.2f}%\n"
            f"• VIX: {vix:.1f} ({vix_regime})\n"
            f"• Momentum: {momentum_trend} ({momentum_4h:+.1f}% 4h)\n"
            f"• Session: {session}\n"
            f"• P/C Ratio: {put_call_ratio:.2f}\n\n"
            f"Evaluating regime...",
            success=True
        )

        # Determine strategy based on GEX regime
        # REGIME 1: Negative GEX below flip = SQUEEZE
        if net_gex < -1e9 and spot < flip:
            self.log_action(
                'REGIME_DETECTED',
                f"✅ REGIME 1: Negative GEX Squeeze (GEX < -$1B and spot < flip)",
                success=True
            )
            strike = round(flip / 5) * 5

            # Enhanced confidence scoring
            base_confidence = 70 + abs(distance_to_flip) * 3

            # Boost confidence if momentum aligns (bullish momentum for call)
            if momentum_trend in ['bullish', 'strong_bullish']:
                base_confidence += 5
            elif momentum_trend in ['bearish', 'strong_bearish']:
                base_confidence -= 10  # Momentum against us

            # VIX factor: High VIX = more explosive moves with negative GEX
            if vix_regime == 'high':
                base_confidence += 5

            # Time factor: Morning = best for new positions
            if session in ['morning', 'opening']:
                base_confidence += 3

            # Put/Call ratio: High P/C (>1.2) = bearish sentiment, squeeze more likely
            if put_call_ratio > 1.2:
                base_confidence += 5

            confidence = min(95, int(base_confidence))

            reasoning = f"""SQUEEZE SETUP (Confidence: {confidence}%):
GEX: ${net_gex/1e9:.2f}B (NEGATIVE) - Dealers SHORT gamma
Price: ${spot:.2f} is {abs(distance_to_flip):.2f}% below flip ${flip:.2f}
→ Rally forces dealers to BUY → accelerates move

ENHANCED FACTORS:
• VIX: {vix:.1f} ({vix_regime}) - {'Higher vol = stronger moves' if vix_regime == 'high' else 'Normal regime'}
• Momentum: {momentum_trend} ({momentum_4h:+.1f}% 4h) - {'Aligned!' if momentum_4h > 0 else 'Against us' if momentum_4h < -0.2 else 'Neutral'}
• Session: {session} - {'Prime time' if session in ['morning', 'opening'] else 'Standard'}
• P/C Ratio: {put_call_ratio:.2f} - {'Bearish sentiment, squeeze likely' if put_call_ratio > 1.2 else 'Neutral'}"""

            return {
                'symbol': 'SPY',
                'strategy': 'Negative GEX Squeeze',
                'action': 'BUY_CALL',
                'option_type': 'call',
                'strike': strike,
                'dte': 5,
                'confidence': confidence,
                'target': flip,
                'stop': spot * 0.985,
                'reasoning': reasoning
            }

        # REGIME 2: Negative GEX above flip = BREAKDOWN
        elif net_gex < -1e9 and spot >= flip:
            strike = round(flip / 5) * 5

            # Enhanced confidence
            base_confidence = 65 + abs(distance_to_flip) * 3
            if momentum_trend in ['bearish', 'strong_bearish']:
                base_confidence += 5  # Momentum aligned
            elif momentum_trend in ['bullish', 'strong_bullish']:
                base_confidence -= 10
            if vix_regime == 'high':
                base_confidence += 5
            if session in ['morning', 'opening']:
                base_confidence += 3
            if put_call_ratio < 0.8:  # Low P/C = complacency, breakdown more likely
                base_confidence += 5

            confidence = min(90, int(base_confidence))

            return {
                'symbol': 'SPY',
                'strategy': 'Negative GEX Breakdown',
                'action': 'BUY_PUT',
                'option_type': 'put',
                'strike': strike,
                'dte': 5,
                'confidence': confidence,
                'target': flip,
                'stop': spot * 1.015,
                'reasoning': f"BREAKDOWN: GEX ${net_gex/1e9:.2f}B. Price ${spot:.2f} above flip ${flip:.2f}. VIX: {vix:.1f}. Momentum: {momentum_trend} ({momentum_4h:+.1f}%). Any selling forces dealers to SELL → accelerates decline."
            }

        # REGIME 3: High positive GEX = SHORT PREMIUM (but for $5K, just directional)
        elif net_gex > 1e9:
            # For small account, trade directional based on position vs flip
            base_confidence = 65
            if momentum_trend in ['bullish', 'strong_bullish'] and spot < flip:
                base_confidence += 5
            elif momentum_trend in ['bearish', 'strong_bearish'] and spot >= flip:
                base_confidence += 5
            if vix_regime == 'low':
                base_confidence += 3  # Low VIX good for range trades
            if session in ['morning']:
                base_confidence += 2

            if spot < flip:
                strike = round(spot / 5) * 5
                return {
                    'symbol': 'SPY',
                    'strategy': 'Range-Bound Bullish',
                    'action': 'BUY_CALL',
                    'option_type': 'call',
                    'strike': strike,
                    'dte': 7,
                    'confidence': min(80, int(base_confidence)),
                    'target': flip,
                    'stop': spot * 0.98,
                    'reasoning': f"RANGE: GEX ${net_gex/1e9:.2f}B (positive). Dealers fade moves. Below flip. VIX: {vix:.1f}. Momentum: {momentum_trend}."
                }
            else:
                strike = round(spot / 5) * 5
                return {
                    'symbol': 'SPY',
                    'strategy': 'Range-Bound Bearish',
                    'action': 'BUY_PUT',
                    'option_type': 'put',
                    'strike': strike,
                    'dte': 7,
                    'confidence': min(80, int(base_confidence)),
                    'target': flip,
                    'stop': spot * 1.02,
                    'reasoning': f"RANGE: GEX ${net_gex/1e9:.2f}B (positive). Dealers fade moves. Above flip. VIX: {vix:.1f}. Momentum: {momentum_trend}."
                }

        # REGIME 4: Neutral - trade toward flip
        else:
            base_confidence = 60
            if momentum_trend in ['bullish', 'strong_bullish'] and spot < flip:
                base_confidence += 5
            elif momentum_trend in ['bearish', 'strong_bearish'] and spot >= flip:
                base_confidence += 5
            if session in ['morning']:
                base_confidence += 2

            if spot < flip:
                strike = round(spot / 5) * 5
                return {
                    'symbol': 'SPY',
                    'strategy': 'Neutral Bullish',
                    'action': 'BUY_CALL',
                    'option_type': 'call',
                    'strike': strike,
                    'dte': 7,
                    'confidence': min(75, int(base_confidence)),
                    'target': flip,
                    'stop': spot * 0.98,
                    'reasoning': f"NEUTRAL: GEX ${net_gex/1e9:.2f}B. Below flip. VIX: {vix:.1f}. Momentum: {momentum_trend} ({momentum_4h:+.1f}%). Lean bullish."
                }
            else:
                strike = round(spot / 5) * 5
                return {
                    'symbol': 'SPY',
                    'strategy': 'Neutral Bearish',
                    'action': 'BUY_PUT',
                    'option_type': 'put',
                    'strike': strike,
                    'dte': 7,
                    'confidence': min(75, int(base_confidence)),
                    'target': flip,
                    'stop': spot * 1.02,
                    'reasoning': f"NEUTRAL: GEX ${net_gex/1e9:.2f}B. Above flip. VIX: {vix:.1f}. Momentum: {momentum_trend} ({momentum_4h:+.1f}%). Lean bearish."
                }

    def _convert_psychology_to_trade(self, regime: Dict, spot: float, gex_data: Dict,
                                       vix: float, momentum: Dict, time_context: Dict) -> Optional[Dict]:
        """
        Convert psychology trap detector signals into actionable trade

        Priority order:
        1. Liberation setups (highest priority - wall expiring soon)
        2. Avoid false floors (don't buy puts on temporary support)
        3. Follow forward GEX magnets
        4. Use primary regime pattern
        5. Confirm with multi-timeframe RSI
        """

        pattern = regime.get('primary_regime_type', 'UNKNOWN')
        confidence = regime.get('confidence_score', 0)
        trade_direction = regime.get('trade_direction', 'NEUTRAL')
        risk_level = regime.get('risk_level', 'MEDIUM')

        # Extract key signals
        liberation_detected = regime.get('liberation_setup_detected', False)
        liberation_strike = regime.get('liberation_target_strike')
        false_floor_detected = regime.get('false_floor_detected', False)
        false_floor_strike = regime.get('false_floor_strike')
        forward_magnet_above = regime.get('monthly_magnet_above')
        forward_magnet_below = regime.get('monthly_magnet_below')
        polr = regime.get('path_of_least_resistance', 'NEUTRAL')
        rsi_aligned_overbought = regime.get('rsi_aligned_overbought', False)
        rsi_aligned_oversold = regime.get('rsi_aligned_oversold', False)

        # ====== PRIORITY 1: LIBERATION SETUP ======
        if liberation_detected and liberation_strike and confidence >= 75:
            dte = regime.get('liberation_dte', 3)

            if liberation_strike > spot:
                # Call wall expiring - price can break upward
                strike = round(liberation_strike / 5) * 5
                reasoning = f"""🔓 LIBERATION SETUP (Confidence: {confidence:.0f}%):
CALL WALL at ${liberation_strike:.0f} EXPIRING in {dte} days
Current Price: ${spot:.2f}
→ Gamma wall disappearing, price can run to ${forward_magnet_above:.0f}

Pattern: {pattern}
Psychology Trap: {regime.get('psychology_trap', 'N/A')}

THESIS: Dealers currently pinning price at ${liberation_strike:.0f}. When options expire, resistance disappears.
Upside target: {forward_magnet_above:.0f} (monthly OPEX magnet)"""

                return {
                    'symbol': 'SPY',
                    'strategy': 'Liberation Trade - Bullish',
                    'action': 'BUY_CALL',
                    'option_type': 'call',
                    'strike': strike,
                    'dte': max(7, dte + 5),  # Give time for liberation to play out
                    'confidence': min(95, int(confidence)),
                    'target': forward_magnet_above if forward_magnet_above else liberation_strike * 1.02,
                    'stop': spot * 0.985,
                    'reasoning': reasoning,
                    'regime': regime  # CRITICAL: Pass regime for AI and competition
                }
            else:
                # Put wall expiring - price can break downward
                strike = round(liberation_strike / 5) * 5
                reasoning = f"""🔓 LIBERATION SETUP (Confidence: {confidence:.0f}%):
PUT WALL at ${liberation_strike:.0f} EXPIRING in {dte} days
Current Price: ${spot:.2f}
→ Gamma wall disappearing, price can fall to ${forward_magnet_below:.0f}

Pattern: {pattern}
Psychology Trap: {regime.get('psychology_trap', 'N/A')}

THESIS: Dealers currently supporting price at ${liberation_strike:.0f}. When options expire, support disappears.
Downside target: {forward_magnet_below:.0f} (monthly OPEX magnet)"""

                return {
                    'symbol': 'SPY',
                    'strategy': 'Liberation Trade - Bearish',
                    'action': 'BUY_PUT',
                    'option_type': 'put',
                    'strike': strike,
                    'dte': max(7, dte + 5),
                    'confidence': min(95, int(confidence)),
                    'target': forward_magnet_below if forward_magnet_below else liberation_strike * 0.98,
                    'stop': spot * 1.015,
                    'reasoning': reasoning,
                    'regime': regime  # CRITICAL: Pass regime for AI and competition
                }

        # ====== PRIORITY 2: AVOID FALSE FLOORS ======
        if false_floor_detected and false_floor_strike:
            if trade_direction == 'BEARISH' and spot > false_floor_strike * 0.98:
                # Don't buy puts if we're near a false floor
                self.log_action('FALSE_FLOOR_WARNING',
                    f'⚠️ FALSE FLOOR at ${false_floor_strike:.0f} - AVOIDING PUT TRADE\n'
                    f'Temporary support will trap put buyers. Waiting for better setup.',
                    success=True)
                return None  # Skip this trade

        # ====== PRIORITY 3: USE PATTERN + FORWARD MAGNETS ======
        if confidence >= 70:
            # High-conviction patterns with psychology confirmation
            if trade_direction == 'BULLISH':
                # Target forward magnet above
                target_strike = forward_magnet_above if forward_magnet_above and forward_magnet_above > spot else spot * 1.02
                strike = round((spot + target_strike) / 2 / 5) * 5  # ATM to slightly OTM

                # Boost confidence if RSI aligned
                adj_confidence = confidence
                if rsi_aligned_oversold:
                    adj_confidence = min(95, confidence + 5)

                reasoning = f"""📈 BULLISH {pattern} (Confidence: {adj_confidence:.0f}%):
{regime.get('description', '')}

FORWARD GEX MAGNET: ${forward_magnet_above:.0f} (monthly OPEX)
Path of Least Resistance: {polr}

Multi-timeframe RSI: {'Aligned Oversold ✅' if rsi_aligned_oversold else 'Confirming'}

Psychology Trap: {regime.get('psychology_trap', 'N/A')}

THESIS: {regime.get('detailed_explanation', 'See pattern analysis')}"""

                return {
                    'symbol': 'SPY',
                    'strategy': f'{pattern} - Psychology Confirmed',
                    'action': 'BUY_CALL',
                    'option_type': 'call',
                    'strike': strike,
                    'dte': 7,
                    'confidence': int(adj_confidence),
                    'target': target_strike,
                    'stop': spot * 0.985,
                    'reasoning': reasoning,
                    'regime': regime  # CRITICAL: Pass regime for AI and competition
                }

            elif trade_direction == 'BEARISH':
                # Target forward magnet below
                target_strike = forward_magnet_below if forward_magnet_below and forward_magnet_below < spot else spot * 0.98
                strike = round((spot + target_strike) / 2 / 5) * 5

                # Boost confidence if RSI aligned
                adj_confidence = confidence
                if rsi_aligned_overbought:
                    adj_confidence = min(95, confidence + 5)

                reasoning = f"""📉 BEARISH {pattern} (Confidence: {adj_confidence:.0f}%):
{regime.get('description', '')}

FORWARD GEX MAGNET: ${forward_magnet_below:.0f} (monthly OPEX)
Path of Least Resistance: {polr}

Multi-timeframe RSI: {'Aligned Overbought ✅' if rsi_aligned_overbought else 'Confirming'}

Psychology Trap: {regime.get('psychology_trap', 'N/A')}

THESIS: {regime.get('detailed_explanation', 'See pattern analysis')}"""

                return {
                    'symbol': 'SPY',
                    'strategy': f'{pattern} - Psychology Confirmed',
                    'action': 'BUY_PUT',
                    'option_type': 'put',
                    'strike': strike,
                    'dte': 7,
                    'confidence': int(adj_confidence),
                    'target': target_strike,
                    'stop': spot * 1.015,
                    'reasoning': reasoning,
                    'regime': regime  # CRITICAL: Pass regime for AI and competition
                }

        # ====== PRIORITY 4: LOWER CONFIDENCE / NEUTRAL ======
        if confidence >= 60 and polr != 'NEUTRAL':
            # Use path of least resistance
            if polr == 'UPWARD':
                strike = round(spot / 5) * 5
                return {
                    'symbol': 'SPY',
                    'strategy': f'Psychology {pattern} - Moderate',
                    'action': 'BUY_CALL',
                    'option_type': 'call',
                    'strike': strike,
                    'dte': 7,
                    'confidence': int(confidence),
                    'target': forward_magnet_above if forward_magnet_above else spot * 1.02,
                    'stop': spot * 0.985,
                    'reasoning': f"{pattern} with {confidence:.0f}% confidence. POLR: {polr}. Forward magnet: ${forward_magnet_above:.0f}",
                    'regime': regime  # CRITICAL: Pass regime for AI and competition
                }
            elif polr == 'DOWNWARD':
                strike = round(spot / 5) * 5
                return {
                    'symbol': 'SPY',
                    'strategy': f'Psychology {pattern} - Moderate',
                    'action': 'BUY_PUT',
                    'option_type': 'put',
                    'strike': strike,
                    'dte': 7,
                    'confidence': int(confidence),
                    'target': forward_magnet_below if forward_magnet_below else spot * 0.98,
                    'stop': spot * 1.015,
                    'reasoning': f"{pattern} with {confidence:.0f}% confidence. POLR: {polr}. Forward magnet: ${forward_magnet_below:.0f}",
                    'regime': regime  # CRITICAL: Pass regime for AI and competition
                }

        # No high-confidence setup from psychology detector
        return None

    def _execute_iron_condor(self, spot: float, gex_data: Dict, api_client) -> Optional[int]:
        """
        Execute Iron Condor - collect premium in range-bound market
        Used when no clear directional setup exists
        """
        try:
            # Iron Condor parameters for $5K account
            # Use 30-45 DTE for better theta decay
            dte = 35  # ~5 weeks out
            exp_date = self._get_expiration_string_monthly(dte)

            # Set strikes: ±5-7% from spot for safety
            # SPY at $500: Sell 475/525, Buy 470/530 (10-point wings)
            wing_width = 5  # $5 wings
            range_width = spot * 0.06  # 6% from spot

            # Round to nearest $5
            call_sell_strike = round((spot + range_width) / 5) * 5
            call_buy_strike = call_sell_strike + wing_width
            put_sell_strike = round((spot - range_width) / 5) * 5
            put_buy_strike = put_sell_strike - wing_width

            # Get option prices for all 4 legs
            call_sell = get_real_option_price('SPY', call_sell_strike, 'call', exp_date)
            call_buy = get_real_option_price('SPY', call_buy_strike, 'call', exp_date)
            put_sell = get_real_option_price('SPY', put_sell_strike, 'put', exp_date)
            put_buy = get_real_option_price('SPY', put_buy_strike, 'put', exp_date)

            # Check for errors
            if any(opt.get('error') for opt in [call_sell, call_buy, put_sell, put_buy]):
                self.log_action('ERROR', 'Failed to get Iron Condor option prices', success=False)
                return None

            # CRITICAL: Validate all prices are > 0 to prevent invalid calculations
            if (call_sell.get('mid', 0) <= 0 or call_buy.get('mid', 0) <= 0 or
                put_sell.get('mid', 0) <= 0 or put_buy.get('mid', 0) <= 0):
                self.log_action('ERROR',
                    f'Iron Condor: Invalid option prices (zero or negative) - '
                    f'Call Sell: ${call_sell.get("mid", 0):.2f}, Call Buy: ${call_buy.get("mid", 0):.2f}, '
                    f'Put Sell: ${put_sell.get("mid", 0):.2f}, Put Buy: ${put_buy.get("mid", 0):.2f}',
                    success=False)
                return None

            # Calculate net credit
            credit = (call_sell['mid'] - call_buy['mid']) + (put_sell['mid'] - put_buy['mid'])

            if credit <= 0:
                call_spread = call_sell['mid'] - call_buy['mid']
                put_spread = put_sell['mid'] - put_buy['mid']
                self.log_action('ERROR',
                    f'Iron Condor has no credit (total=${credit:.2f}). '
                    f'Call spread: ${call_spread:.2f}, Put spread: ${put_spread:.2f}. '
                    f'Strikes: {put_buy_strike}/{put_sell_strike}/{call_sell_strike}/{call_buy_strike}',
                    success=False)
                return None

            # Position sizing: use conservative 20% of capital for spreads
            available = self.get_available_capital()
            max_risk = wing_width * 100  # $5 wing = $500 risk per spread
            max_position = available * 0.20  # 20% for Iron Condor
            contracts = max(1, int(max_position / max_risk))
            contracts = min(contracts, 5)  # Max 5 Iron Condors for $5K account

            net_credit = credit * contracts * 100

            # Build trade dict
            trade = {
                'symbol': 'SPY',
                'strategy': f'Iron Condor (Collect ${net_credit:.0f} premium)',
                'action': 'IRON_CONDOR',
                'option_type': 'iron_condor',
                'strike': spot,  # Use spot as reference
                'dte': dte,
                'confidence': 85,  # High confidence for premium collection
                'reasoning': f"""IRON CONDOR: No clear directional GEX setup. Market range-bound.

STRATEGY: Collect premium betting SPY stays between ${put_sell_strike:.0f} - ${call_sell_strike:.0f}
- Sell {call_sell_strike} Call @ ${call_sell['mid']:.2f}
- Buy {call_buy_strike} Call @ ${call_buy['mid']:.2f}
- Sell {put_sell_strike} Put @ ${put_sell['mid']:.2f}
- Buy {put_buy_strike} Put @ ${put_buy['mid']:.2f}

NET CREDIT: ${credit:.2f} per spread × {contracts} contracts = ${net_credit:.0f}
MAX RISK: ${max_risk * contracts:,.0f}
EXPIRATION: {dte} DTE (monthly) for theta decay
RANGE: ±6% from ${spot:.2f} (conservative for $5K account)"""
            }

            # Execute as multi-leg position with REAL bid/ask from options chain
            ic_bid = (call_sell.get('bid', 0) - call_buy.get('ask', 0)) + (put_sell.get('bid', 0) - put_buy.get('ask', 0))
            ic_ask = (call_sell.get('ask', 0) - call_buy.get('bid', 0)) + (put_sell.get('ask', 0) - put_buy.get('bid', 0))
            # Get VIX for strike/Greeks logging
            vix = self._get_vix()
            position_id = self._execute_trade(
                trade,
                {'mid': credit, 'bid': ic_bid, 'ask': ic_ask, 'contract_symbol': 'IRON_CONDOR'},
                contracts,
                credit,
                exp_date,
                gex_data,
                vix
            )

            if position_id:
                self.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))
                self.log_action(
                    'EXECUTE',
                    f"Opened Iron Condor: ${net_credit:.0f} credit ({contracts} contracts) | Expiration: {exp_date} ({dte} DTE)",
                    position_id=position_id,
                    success=True
                )
                return position_id

            return None

        except Exception as e:
            self.log_action('ERROR', f'Iron Condor execution failed: {str(e)}', success=False)
            import traceback
            traceback.print_exc()
            return None

    def _execute_atm_straddle_fallback(self, spot: float, api_client) -> Optional[int]:
        """
        FINAL FALLBACK - GUARANTEED TRADE
        Execute simple ATM straddle to ensure MINIMUM one trade per day
        This is intentionally simple with minimal failure points
        """
        try:
            self.log_action('GUARANTEE', 'Executing GUARANTEED daily trade - ATM Straddle')

            # Simple parameters - minimize failure points
            strike = round(spot)  # Round to nearest dollar (ATM)
            dte = 7  # One week
            exp_date = self._get_expiration_string(dte)

            # Get ATM call and put prices
            call_price = get_real_option_price('SPY', strike, 'call', exp_date)
            put_price = get_real_option_price('SPY', strike, 'put', exp_date)

            # If we can't get prices, use estimated prices based on typical ATM options
            if call_price.get('error') or put_price.get('error'):
                self.log_action('WARNING', 'Could not fetch real prices - using estimated prices for guaranteed trade')
                # Typical ATM weekly option is ~1-2% of spot price
                estimated_premium = spot * 0.015  # 1.5% estimate
                call_price = {'mid': estimated_premium, 'bid': estimated_premium * 0.95, 'ask': estimated_premium * 1.05, 'contract_symbol': f'SPY{datetime.now(CENTRAL_TZ).strftime("%y%m%d")}C{strike}'}
                put_price = {'mid': estimated_premium, 'bid': estimated_premium * 0.95, 'ask': estimated_premium * 1.05, 'contract_symbol': f'SPY{datetime.now(CENTRAL_TZ).strftime("%y%m%d")}P{strike}'}

            total_cost = (call_price['mid'] + put_price['mid']) * 100  # Cost per straddle

            # CRITICAL: Validate total_cost before division to prevent ZeroDivisionError
            if total_cost <= 0:
                self.log_action('ERROR', f'ATM Straddle: Invalid option prices (total cost = ${total_cost:.2f})', success=False)
                # Try estimating based on spot price and volatility as last resort
                estimated_cost = spot * 0.02 * 100  # 2% of spot as fallback estimate
                if estimated_cost > 0:
                    total_cost = estimated_cost
                    self.log_action('WARNING', f'Using estimated straddle cost: ${estimated_cost:.2f}')
                else:
                    self.log_action('CRITICAL', 'Cannot estimate straddle cost - spot price may be zero', success=False)
                    return None

            available = self.get_available_capital()

            # Use 15% of capital for guaranteed trade
            max_position = available * 0.15
            contracts = max(1, int(max_position / total_cost))  # At least 1 contract
            contracts = min(contracts, 3)  # Max 3 for safety

            total_debit = (call_price['mid'] + put_price['mid']) * contracts * 100

            trade = {
                'symbol': 'SPY',
                'strategy': f'ATM Straddle (GUARANTEED Daily Trade)',
                'action': 'LONG_STRADDLE',
                'option_type': 'straddle',
                'strike': strike,
                'dte': dte,
                'confidence': 100,  # This is our guarantee - always execute
                'reasoning': f"""ATM STRADDLE - GUARANTEED MINIMUM ONE TRADE PER DAY

STRATEGY: Buy ATM Call + Put to ensure daily trade execution
- Buy {strike} Call @ ${call_price['mid']:.2f}
- Buy {strike} Put @ ${put_price['mid']:.2f}

TOTAL COST: ${total_debit:.0f} for {contracts} straddle(s)
EXPIRATION: {dte} DTE
RATIONALE: Failsafe execution to guarantee MINIMUM one trade per day
This trade ensures we're always active in the market"""
            }

            # Execute the straddle with REAL bid/ask from options chain
            straddle_bid = call_price.get('bid', 0) + put_price.get('bid', 0)
            straddle_ask = call_price.get('ask', 0) + put_price.get('ask', 0)
            straddle_mid = call_price['mid'] + put_price['mid']
            # Get VIX for strike/Greeks logging
            vix = self._get_vix()
            position_id = self._execute_trade(
                trade,
                {'mid': straddle_mid, 'bid': straddle_bid, 'ask': straddle_ask, 'contract_symbol': 'STRADDLE_FALLBACK'},
                contracts,
                -straddle_mid,  # Negative because we're buying (debit)
                exp_date,
                {'net_gex': 0, 'flip_point': strike, 'spot_price': spot},  # Include spot price for logging
                vix
            )

            if position_id:
                self.set_config('last_trade_date', datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'))
                self.log_action(
                    'EXECUTE',
                    f"GUARANTEED TRADE: ATM Straddle @ ${strike} ({contracts} contracts) | Expiration: {exp_date} ({dte} DTE) - MINIMUM one trade per day fulfilled",
                    position_id=position_id,
                    success=True
                )
                self.update_live_status(
                    status='ACTIVE',
                    action=f'Executed guaranteed daily trade',
                    decision=f'ATM Straddle @ ${strike} - MINIMUM one trade requirement met'
                )
                return position_id

            # If even this fails, log critical error but still return position (we tried our best)
            self.log_action('CRITICAL', 'Guaranteed trade execution failed - this should never happen', success=False)
            return None

        except Exception as e:
            self.log_action('CRITICAL', f'GUARANTEED TRADE FAILED: {str(e)} - This violates minimum one trade per day', success=False)
            import traceback
            traceback.print_exc()
            return None

    def _get_expiration_string(self, dte: int) -> str:
        """Get expiration date string for options (weekly)"""
        today = datetime.now(CENTRAL_TZ)

        if dte <= 7:
            days_until_friday = (4 - today.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7
            exp_date = today + timedelta(days=days_until_friday)
        else:
            days_until_friday = (4 - today.weekday()) % 7
            exp_date = today + timedelta(days=days_until_friday + 7)

        return exp_date.strftime('%Y-%m-%d')

    def _get_expiration_string_monthly(self, dte: int) -> str:
        """Get monthly expiration date (3rd Friday of month)"""
        today = datetime.now(CENTRAL_TZ)
        target_date = today + timedelta(days=dte)

        # Find 3rd Friday of target month
        year = target_date.year
        month = target_date.month

        # First day of month
        first_day = datetime(year, month, 1)
        # Find first Friday
        days_until_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_until_friday)
        # Third Friday
        third_friday = first_friday + timedelta(days=14)

        return third_friday.strftime('%Y-%m-%d')

    def _execute_trade(self, trade: Dict, option_data: Dict, contracts: int,
                       entry_price: float, exp_date: str, gex_data: Dict,
                       vix_current: float = 18.0, regime_result: Dict = None) -> Optional[int]:
        """Execute the trade and send push notification"""

        # CRITICAL: Log trade decision to database
        if self.db_logger:
            self.db_logger.log_trade_decision(
                symbol=trade['symbol'],
                action=trade['action'],
                strategy=trade['strategy'],
                reasoning=trade.get('reasoning', 'See trade details'),
                confidence=trade.get('confidence', 0)
            )

        # Log strike and Greeks performance data for optimizer intelligence
        self._log_strike_and_greeks_performance(
            trade, option_data, gex_data, exp_date, vix_current, regime_result
        )

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        now = datetime.now(CENTRAL_TZ)

        c.execute("""
            INSERT INTO autonomous_positions (
                symbol, strategy, action, entry_date, entry_time, strike, option_type,
                expiration_date, contracts, entry_price, entry_bid, entry_ask,
                entry_spot_price, current_price, current_spot_price, unrealized_pnl,
                status, confidence, gex_regime, entry_net_gex, entry_flip_point,
                trade_reasoning, contract_symbol
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade['symbol'],
            trade['strategy'],
            trade['action'],
            now.strftime('%Y-%m-%d'),
            now.strftime('%H:%M:%S'),
            trade['strike'],
            trade['option_type'],
            exp_date,
            contracts,
            entry_price,
            option_data.get('bid', 0),
            option_data.get('ask', 0),
            gex_data.get('spot_price', 0),
            entry_price,
            gex_data.get('spot_price', 0),
            0.0,
            'OPEN',
            trade['confidence'],
            f"GEX: ${gex_data.get('net_gex', 0)/1e9:.2f}B",
            gex_data.get('net_gex', 0),
            gex_data.get('flip_point', 0),
            trade['reasoning'],
            option_data.get('contract_symbol', '')
        ))

        position_id = c.lastrowid
        conn.commit()
        conn.close()

        # CRITICAL: Record trade in strategy competition
        if self.competition:
            try:
                # Check which strategies would have taken this trade
                regime = trade.get('regime', {})
                if regime:
                    for strategy_id in self.competition.strategies.keys():
                        should_trade = self.competition.should_trade_for_strategy(strategy_id, regime)

                        if should_trade:
                            # Record that this strategy participated in the trade
                            self.log_action(
                                'COMPETITION',
                                f'Strategy {strategy_id} participating in trade',
                                success=True
                            )
                            # Note: Actual P&L will be recorded when position closes

            except Exception as e:
                self.log_action('COMPETITION_ERROR', f'Failed to record competition trade: {e}', success=False)

        # CRITICAL: Send push notification for high-confidence trades
        if trade['confidence'] >= 80:
            self._send_trade_notification(trade, contracts, entry_price, position_id)

        return position_id

    def _send_trade_notification(self, trade: Dict, contracts: int, entry_price: float, position_id: int):
        """Send push notification when autonomous trader executes trade"""
        try:
            # Import push notification service
            import sys
            from pathlib import Path
            backend_dir = Path(__file__).parent / 'backend'
            if backend_dir.exists():
                sys.path.insert(0, str(backend_dir))

            from backend.push_notification_service import get_push_service
            push_service = get_push_service()

            # Determine alert level based on confidence
            alert_level = 'CRITICAL' if trade['confidence'] >= 90 else 'HIGH'

            # Determine alert type
            alert_type = None
            if 'liberation' in trade['strategy'].lower():
                alert_type = 'liberation'
            elif 'false floor' in trade.get('reasoning', '').lower():
                alert_type = 'false_floor'

            # Create notification title and body
            action_emoji = '📈' if 'CALL' in trade['action'] else '📉'
            title = f"{action_emoji} Autonomous Trade Executed"

            cost = abs(entry_price) * contracts * 100
            body = f"{trade['strategy']}: {trade['action']} ${trade['strike']:.0f} ({contracts}x) - Confidence: {trade['confidence']}% - Cost: ${cost:.0f}"

            # Send broadcast notification
            stats = push_service.broadcast_notification(
                title=title,
                body=body,
                alert_level=alert_level,
                alert_type=alert_type,
                data={
                    'symbol': trade['symbol'],
                    'strategy': trade['strategy'],
                    'strike': trade['strike'],
                    'confidence': trade['confidence'],
                    'position_id': position_id,
                    'type': 'autonomous_trade'
                }
            )

            print(f"📢 Push notification sent: {stats['sent']} delivered, {stats['failed']} failed")

        except Exception as e:
            # Don't fail trade execution if notification fails
            print(f"⚠️ Push notification failed: {e}")
            pass

    def _log_strike_and_greeks_performance(self, trade: Dict, option_data: Dict, gex_data: Dict,
                                          exp_date: str, vix_current: float, regime_result: Dict = None):
        """
        Log detailed strike and Greeks performance data for optimizer intelligence
        """
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            now = datetime.now(CENTRAL_TZ)

            spot_price = gex_data.get('spot_price', 0)
            strike = trade['strike']

            # Calculate strike distance percentage
            strike_distance_pct = ((strike - spot_price) / spot_price) * 100

            # Determine moneyness
            option_type = trade['option_type']
            if option_type == 'CALL':
                if abs(strike - spot_price) / spot_price < 0.005:  # Within 0.5%
                    moneyness = 'ATM'
                elif strike > spot_price:
                    moneyness = 'OTM'
                else:
                    moneyness = 'ITM'
            else:  # PUT
                if abs(strike - spot_price) / spot_price < 0.005:
                    moneyness = 'ATM'
                elif strike < spot_price:
                    moneyness = 'OTM'
                else:
                    moneyness = 'ITM'

            # Calculate DTE
            try:
                exp_datetime = datetime.strptime(exp_date, '%Y-%m-%d')
                dte = (exp_datetime - now.replace(tzinfo=None)).days
            except:
                dte = 0

            # Determine VIX regime
            if vix_current < 15:
                vix_regime = 'low'
            elif vix_current < 25:
                vix_regime = 'normal'
            else:
                vix_regime = 'high'

            # Get Greeks from option_data (if available)
            delta = option_data.get('delta', option_data.get('greeks', {}).get('delta', 0))
            gamma = option_data.get('gamma', option_data.get('greeks', {}).get('gamma', 0))
            theta = option_data.get('theta', option_data.get('greeks', {}).get('theta', 0))
            vega = option_data.get('vega', option_data.get('greeks', {}).get('vega', 0))

            # Get pattern type from regime or trade
            pattern_type = 'NONE'
            if regime_result:
                pattern_type = regime_result.get('pattern_type', 'NONE')
            elif 'liberation' in trade.get('strategy', '').lower():
                pattern_type = 'LIBERATION'
            elif 'false floor' in trade.get('reasoning', '').lower():
                pattern_type = 'FALSE_FLOOR'

            # Get gamma regime
            net_gex = gex_data.get('net_gex', 0)
            if net_gex > 0:
                gamma_regime = 'positive'
            elif net_gex < 0:
                gamma_regime = 'negative'
            else:
                gamma_regime = 'neutral'

            # Log strike performance
            c.execute("""
                INSERT INTO strike_performance (
                    timestamp, strategy_name, strike_distance_pct, strike_absolute,
                    spot_price, strike_type, moneyness, delta, gamma, theta, vega,
                    dte, vix_current, vix_regime, net_gex, gamma_regime,
                    pnl_pct, win, pattern_type, confidence_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.strftime('%Y-%m-%d %H:%M:%S'),
                trade['strategy'],
                strike_distance_pct,
                strike,
                spot_price,
                option_type,
                moneyness,
                delta,
                gamma,
                theta,
                vega,
                dte,
                vix_current,
                vix_regime,
                net_gex,
                gamma_regime,
                0.0,  # P&L will be updated on exit
                0,    # Win will be updated on exit
                pattern_type,
                trade.get('confidence', 0)
            ))

            # Log Greeks performance
            c.execute("""
                INSERT INTO greeks_performance (
                    timestamp, strategy_name, pattern_type, vix_regime,
                    entry_delta, entry_gamma, entry_theta, entry_vega,
                    exit_delta, exit_gamma, exit_theta, exit_vega,
                    delta_pnl, gamma_pnl, theta_pnl, vega_pnl,
                    total_pnl_pct, win, dte, net_gex
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.strftime('%Y-%m-%d %H:%M:%S'),
                trade['strategy'],
                pattern_type,
                vix_regime,
                delta,
                gamma,
                theta,
                vega,
                0.0,  # Exit Greeks will be updated on exit
                0.0,
                0.0,
                0.0,
                0.0,  # Greek contributions will be calculated on exit
                0.0,
                0.0,
                0.0,
                0.0,  # Total P&L will be updated on exit
                0,    # Win will be updated on exit
                dte,
                net_gex
            ))

            # Determine DTE bucket
            if dte <= 3:
                dte_bucket = '0-3'
            elif dte <= 7:
                dte_bucket = '4-7'
            elif dte <= 14:
                dte_bucket = '8-14'
            elif dte <= 30:
                dte_bucket = '15-30'
            else:
                dte_bucket = '30+'

            # Log DTE performance
            c.execute("""
                INSERT INTO dte_performance (
                    timestamp, strategy_name, pattern_type, dte, dte_bucket,
                    vix_regime, entry_price, exit_price, pnl_pct, win,
                    entry_theta, exit_theta, theta_decay_efficiency,
                    entry_time, exit_time, holding_hours
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.strftime('%Y-%m-%d %H:%M:%S'),
                trade['strategy'],
                pattern_type,
                dte,
                dte_bucket,
                vix_regime,
                option_data.get('ask', 0),  # Entry price
                0.0,  # Exit price will be updated on exit
                0.0,  # P&L will be updated on exit
                0,    # Win will be updated on exit
                theta,
                0.0,  # Exit theta will be updated on exit
                0.0,  # Theta efficiency will be calculated on exit
                now.strftime('%Y-%m-%d %H:%M:%S'),
                None,  # Exit time will be updated on exit
                0.0    # Holding hours will be calculated on exit
            ))

            conn.commit()
            conn.close()

            print(f"✅ Strike & Greeks performance logged: {moneyness} {strike_distance_pct:.1f}% strike, Δ={delta:.3f}, DTE={dte}")

        except Exception as e:
            print(f"⚠️ Failed to log strike/Greeks performance: {e}")
            # Don't fail trade execution if logging fails

    def auto_manage_positions(self, api_client):
        """
        AUTONOMOUS: Automatically manage and close positions based on conditions
        Runs every time the system checks
        """

        conn = sqlite3.connect(self.db_path)
        positions = pd.read_sql_query("""
            SELECT * FROM autonomous_positions WHERE status = 'OPEN'
        """, conn)
        conn.close()

        if positions.empty:
            return []

        actions_taken = []

        for _, pos in positions.iterrows():
            try:
                # Get current SPY price
                gex_data = api_client.get_net_gamma('SPY')
                if not gex_data or gex_data.get('error'):
                    continue

                current_spot = gex_data.get('spot_price', 0)

                # Get current option price
                option_data = get_real_option_price(
                    pos['symbol'],
                    pos['strike'],
                    pos['option_type'],
                    pos['expiration_date']
                )

                if option_data.get('error'):
                    continue

                current_price = option_data['mid']
                if current_price == 0:
                    current_price = option_data.get('last', pos['entry_price'])

                # Calculate P&L
                entry_value = pos['entry_price'] * pos['contracts'] * 100
                current_value = current_price * pos['contracts'] * 100
                unrealized_pnl = current_value - entry_value
                pnl_pct = (unrealized_pnl / entry_value * 100) if entry_value > 0 else 0

                # Update position
                self._update_position(pos['id'], current_price, current_spot, unrealized_pnl)

                # Check exit conditions
                should_exit, reason = self._check_exit_conditions(
                    pos, pnl_pct, current_price, current_spot, gex_data
                )

                if should_exit:
                    self._close_position(pos['id'], current_price, unrealized_pnl, reason)

                    actions_taken.append({
                        'position_id': pos['id'],
                        'strategy': pos['strategy'],
                        'action': 'CLOSE',
                        'reason': reason,
                        'pnl': unrealized_pnl,
                        'pnl_pct': pnl_pct
                    })

                    self.log_action(
                        'CLOSE',
                        f"Closed {pos['strategy']}: P&L ${unrealized_pnl:+.2f} ({pnl_pct:+.1f}%) | Expiration: {pos['expiration_date']} - {reason}",
                        position_id=pos['id'],
                        success=True
                    )

            except Exception as e:
                print(f"Error managing position {pos['id']}: {e}")
                continue

        return actions_taken

    def _update_position(self, position_id: int, current_price: float, current_spot: float, unrealized_pnl: float):
        """Update position with current values"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            UPDATE autonomous_positions
            SET current_price = ?, current_spot_price = ?, unrealized_pnl = ?
            WHERE id = ?
        """, (current_price, current_spot, unrealized_pnl, position_id))

        conn.commit()
        conn.close()

    def _check_exit_conditions(self, pos: Dict, pnl_pct: float, current_price: float,
                                current_spot: float, gex_data: Dict) -> Tuple[bool, str]:
        """
        AI-POWERED EXIT STRATEGY: Flexible intelligent decision making
        Uses Claude AI to analyze market conditions, not rigid rules
        """

        # HARD STOP: -50% loss (protect capital)
        if pnl_pct <= -50:
            return True, f"🚨 HARD STOP: {pnl_pct:.1f}% loss - protecting capital"

        # EXPIRATION SAFETY: Close on expiration day
        exp_date = datetime.strptime(pos['expiration_date'], '%Y-%m-%d')
        dte = (exp_date - datetime.now(CENTRAL_TZ)).days
        if dte <= 0:
            return True, f"⏰ EXPIRATION: {dte} DTE - closing to avoid assignment"

        # AI DECISION: Everything else goes to Claude
        try:
            ai_decision = self._ai_should_close_position(pos, pnl_pct, current_price, current_spot, gex_data, dte)

            if ai_decision['should_close']:
                return True, f"🤖 AI: {ai_decision['reason']}"

            # AI says HOLD
            return False, ""

        except Exception as e:
            # If AI fails, fall back to simple rules
            print(f"AI decision failed: {e}, using fallback rules")
            return self._fallback_exit_rules(pos, pnl_pct, dte, gex_data)

    def _ai_should_close_position(self, pos: Dict, pnl_pct: float, current_price: float,
                                   current_spot: float, gex_data: Dict, dte: int) -> Dict:
        """
        AI-POWERED DECISION: Ask Claude whether to close position
        Returns: {'should_close': bool, 'reason': str}
        """
        # Check if Claude API is available from environment variables
        claude_api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")

        if not claude_api_key:
            # No AI available, use fallback
            return {'should_close': False, 'reason': 'AI unavailable'}

        # Build context for Claude
        entry_gex = pos['entry_net_gex']
        current_gex = gex_data.get('net_gex', 0)
        entry_flip = pos['entry_flip_point']
        current_flip = gex_data.get('flip_point', 0)

        prompt = f"""You are an expert options trader managing a position. Analyze this position and decide: HOLD or CLOSE?

POSITION DETAILS:
- Strategy: {pos['strategy']}
- Action: {pos['action']}
- Strike: ${pos['strike']:.0f} {pos['option_type'].upper()}
- Entry: ${pos['entry_price']:.2f} | Current: ${current_price:.2f}
- P&L: {pnl_pct:+.1f}%
- Days to Expiration: {dte} DTE
- Contracts: {pos['contracts']}

MARKET CONDITIONS (THEN vs NOW):
Entry GEX: ${entry_gex/1e9:.2f}B | Current GEX: ${current_gex/1e9:.2f}B
Entry Flip: ${entry_flip:.2f} | Current Flip: ${current_flip:.2f}
SPY Entry: ${pos['entry_spot_price']:.2f} | Current SPY: ${current_spot:.2f}

TRADE THESIS:
{pos['trade_reasoning']}

THINK LIKE A PROFESSIONAL TRADER:
- Is the original thesis still valid?
- Has GEX regime changed significantly?
- Is this a good profit to take given time left?
- Could we let it run more?
- Is risk/reward still favorable?

RESPOND WITH EXACTLY:
DECISION: HOLD or CLOSE
REASON: [one concise sentence explaining why]

Examples:
"DECISION: CLOSE
REASON: GEX flipped from -$8B to +$2B - thesis invalidated, take +15% profit now"

"DECISION: HOLD
REASON: Thesis intact, only 2 DTE left but still 20% from profit target, let theta work"

"DECISION: CLOSE
REASON: Up +35% with 15 DTE, great profit - take it and redeploy capital"

Now analyze this position:"""

        try:
            # Call Claude API using the ClaudeIntelligence class
            from intelligence_and_strategies import ClaudeIntelligence
            claude = ClaudeIntelligence()

            # Get Claude's response
            response = claude._call_claude_api(
                prompt,
                max_tokens=150,
                temperature=0.3  # Lower temperature for consistent decisions
            )

            # Parse response
            if 'DECISION: CLOSE' in response.upper():
                # Extract reason
                reason_start = response.upper().find('REASON:') + 7
                reason = response[reason_start:].strip()
                # Clean up
                reason = reason.split('\n')[0].strip()
                if len(reason) > 100:
                    reason = reason[:100] + "..."

                return {'should_close': True, 'reason': reason}
            else:
                return {'should_close': False, 'reason': 'AI recommends holding'}

        except Exception as e:
            print(f"Claude API error: {e}")
            return {'should_close': False, 'reason': f'AI error: {str(e)}'}

    def _fallback_exit_rules(self, pos: Dict, pnl_pct: float, dte: int, gex_data: Dict) -> Tuple[bool, str]:
        """Fallback rules if AI is unavailable"""

        # Big profit
        if pnl_pct >= 40:
            return True, f"💰 PROFIT: +{pnl_pct:.1f}% (fallback rule)"

        # Stop loss
        if pnl_pct <= -30:
            return True, f"🛑 STOP: {pnl_pct:.1f}% (fallback rule)"

        # Expiration
        if dte <= 1:
            return True, f"⏰ EXPIRING: {dte} DTE (fallback rule)"

        # GEX flip
        entry_gex = pos['entry_net_gex']
        current_gex = gex_data.get('net_gex', 0)
        if (entry_gex > 0 and current_gex < 0) or (entry_gex < 0 and current_gex > 0):
            return True, "📊 GEX FLIP: Thesis changed (fallback rule)"

        return False, ""

    def _close_position(self, position_id: int, exit_price: float, realized_pnl: float, reason: str):
        """Close a position"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        now = datetime.now(CENTRAL_TZ)

        c.execute("""
            UPDATE autonomous_positions
            SET status = 'CLOSED',
                closed_date = ?,
                closed_time = ?,
                exit_price = ?,
                realized_pnl = ?,
                exit_reason = ?
            WHERE id = ?
        """, (
            now.strftime('%Y-%m-%d'),
            now.strftime('%H:%M:%S'),
            exit_price,
            realized_pnl,
            reason,
            position_id
        ))

        conn.commit()
        conn.close()

    def get_performance(self) -> Dict:
        """Get trading performance stats"""
        conn = sqlite3.connect(self.db_path)

        closed = pd.read_sql_query("""
            SELECT * FROM autonomous_positions WHERE status = 'CLOSED'
        """, conn)

        open_pos = pd.read_sql_query("""
            SELECT * FROM autonomous_positions WHERE status = 'OPEN'
        """, conn)

        conn.close()

        capital = float(self.get_config('capital'))
        total_realized = closed['realized_pnl'].sum() if not closed.empty else 0
        total_unrealized = open_pos['unrealized_pnl'].sum() if not open_pos.empty else 0
        total_pnl = total_realized + total_unrealized
        current_value = capital + total_pnl

        win_rate = 0
        if not closed.empty:
            winners = closed[closed['realized_pnl'] > 0]
            win_rate = (len(winners) / len(closed) * 100)

        return {
            'starting_capital': capital,
            'current_value': current_value,
            'total_pnl': total_pnl,
            'realized_pnl': total_realized,
            'unrealized_pnl': total_unrealized,
            'return_pct': (total_pnl / capital * 100),
            'total_trades': len(closed),
            'open_positions': len(open_pos),
            'win_rate': win_rate
        }
