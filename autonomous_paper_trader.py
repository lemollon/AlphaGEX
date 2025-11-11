"""
Autonomous Paper Trader - Fully Automated SPY Trading
Finds and executes trades automatically with ZERO manual intervention
Starting capital: $5,000
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Tuple
from config_and_database import DB_PATH
import yfinance as yf
import time
import os


def get_real_option_price(symbol: str, strike: float, option_type: str, expiration_date: str) -> Dict:
    """Get REAL option price from Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        options = ticker.option_chain(expiration_date)

        if option_type.lower() == 'call':
            chain = options.calls
        else:
            chain = options.puts

        # Find exact strike or closest
        option_data = chain[chain['strike'] == strike]

        if option_data.empty:
            chain['strike_diff'] = abs(chain['strike'] - strike)
            closest = chain.nsmallest(1, 'strike_diff')
            if not closest.empty:
                option_data = closest

        if option_data.empty:
            return {'error': 'No option data found'}

        row = option_data.iloc[0]

        return {
            'bid': float(row.get('bid', 0)),
            'ask': float(row.get('ask', 0)),
            'last': float(row.get('lastPrice', 0)),
            'mid': (float(row.get('bid', 0)) + float(row.get('ask', 0))) / 2,
            'volume': int(row.get('volume', 0)),
            'open_interest': int(row.get('openInterest', 0)),
            'implied_volatility': float(row.get('impliedVolatility', 0)),
            'strike': float(row['strike']),
            'contract_symbol': row.get('contractSymbol', '')
        }

    except Exception as e:
        print(f"Error fetching option price: {e}")
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
            """, (datetime.now().isoformat(),))

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

        next_check = (datetime.now() + timedelta(hours=1)).isoformat()

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
        """, (datetime.now().isoformat(), status, action, analysis, next_check, decision))

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

        now = datetime.now()
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
        """Check if we should find a new trade today"""
        today = datetime.now().strftime('%Y-%m-%d')
        last_trade_date = self.get_config('last_trade_date')

        # Trade once per day
        if last_trade_date == today:
            return False

        # Check if market is open (simple check - Monday-Friday)
        if datetime.now().weekday() >= 5:  # Saturday or Sunday
            return False

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
                # Log why directional trade was not suitable
                if not trade:
                    reason = "No directional setup detected. GEX structure unclear or conflicting signals."
                else:
                    reason = f"Confidence too low ({trade.get('confidence', 0)}% < 70% minimum threshold). Setup not strong enough for directional trade."

                self.log_action(
                    'FALLBACK_DECISION',
                    f"{reason}\n\n"
                    f"FALLBACK STRATEGY: Using Iron Condor for premium collection. "
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
        """Execute directional call/put trade"""
        try:
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

            # For $5K account: use max 25% per trade = $1,250
            max_position = min(available * 0.25, 1250)
            cost_per_contract = entry_price * 100

            if cost_per_contract == 0:
                self.log_action('ERROR', 'Invalid option price (zero)', success=False)
                return None

            contracts = max(1, int(max_position / cost_per_contract))
            contracts = min(contracts, 10)  # Max 10 contracts for $5K account

            total_cost = contracts * cost_per_contract

            # Execute trade automatically
            position_id = self._execute_trade(
                trade, option_price_data, contracts, entry_price,
                exp_date, gex_data
            )

            if position_id:
                # Update last trade date
                self.set_config('last_trade_date', datetime.now().strftime('%Y-%m-%d'))

                # Update live status with successful trade
                self.update_live_status(
                    status='TRADE_EXECUTED',
                    action=f"✅ Successfully opened {trade['strategy']}",
                    analysis=f"{contracts} contracts @ ${entry_price:.2f} (Total: ${total_cost:.2f})",
                    decision=f"Position #{position_id} is now active. Next check in 1 hour."
                )

                self.log_action(
                    'EXECUTE',
                    f"Opened {trade['strategy']}: {contracts} contracts @ ${entry_price:.2f} (${total_cost:.2f} total)",
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
        """Get current VIX level for volatility regime - REAL-TIME"""
        try:
            import yfinance as yf
            # Force fresh data - don't use cache
            vix_ticker = yf.Ticker('^VIX')
            # Try latest quote first (most current)
            vix_info = vix_ticker.info
            if vix_info and 'regularMarketPrice' in vix_info:
                vix_price = float(vix_info['regularMarketPrice'])
                if vix_price > 0:
                    print(f"✅ VIX fetched: {vix_price:.2f}")
                    return vix_price

            # Fallback to history if info doesn't work
            vix_data = vix_ticker.history(period='1d', interval='1m')
            if not vix_data.empty:
                vix_price = float(vix_data['Close'].iloc[-1])
                print(f"✅ VIX fetched (history): {vix_price:.2f}")
                return vix_price

            print(f"⚠️ VIX data empty - using default 20.0")
            return 20.0  # Default neutral VIX
        except Exception as e:
            print(f"❌ Failed to fetch VIX: {e}")
            import traceback
            traceback.print_exc()
            return 20.0

    def _get_momentum(self) -> Dict:
        """Calculate recent momentum (1h, 4h price change)"""
        try:
            import yfinance as yf
            spy = yf.Ticker('SPY')
            # Get intraday data
            data = spy.history(period='5d', interval='1h')
            if len(data) < 5:
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
            print(f"Failed to calculate momentum: {e}")
            return {'1h': 0, '4h': 0, 'trend': 'neutral'}

    def _get_time_context(self) -> Dict:
        """Get time of day context for trading"""
        now = datetime.now()
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
        """Analyze market and return best trade with enhanced multi-factor scoring"""

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

        # Determine strategy based on GEX regime
        # REGIME 1: Negative GEX below flip = SQUEEZE
        if net_gex < -1e9 and spot < flip:
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

            # Calculate net credit
            credit = (call_sell['mid'] - call_buy['mid']) + (put_sell['mid'] - put_buy['mid'])

            if credit <= 0:
                self.log_action('ERROR', 'Iron Condor has no credit', success=False)
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

            # Execute as multi-leg position
            position_id = self._execute_trade(
                trade,
                {'mid': credit, 'bid': credit, 'ask': credit, 'contract_symbol': 'IRON_CONDOR'},
                contracts,
                credit,
                exp_date,
                gex_data
            )

            if position_id:
                self.set_config('last_trade_date', datetime.now().strftime('%Y-%m-%d'))
                self.log_action(
                    'EXECUTE',
                    f"Opened Iron Condor: ${net_credit:.0f} credit ({contracts} contracts)",
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
                call_price = {'mid': estimated_premium, 'bid': estimated_premium * 0.95, 'ask': estimated_premium * 1.05, 'contract_symbol': f'SPY{datetime.now().strftime("%y%m%d")}C{strike}'}
                put_price = {'mid': estimated_premium, 'bid': estimated_premium * 0.95, 'ask': estimated_premium * 1.05, 'contract_symbol': f'SPY{datetime.now().strftime("%y%m%d")}P{strike}'}

            total_cost = (call_price['mid'] + put_price['mid']) * 100  # Cost per straddle
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

            # Execute the straddle
            position_id = self._execute_trade(
                trade,
                {'mid': call_price['mid'] + put_price['mid'], 'bid': total_debit / (contracts * 100), 'ask': total_debit / (contracts * 100), 'contract_symbol': 'STRADDLE_FALLBACK'},
                contracts,
                -(call_price['mid'] + put_price['mid']),  # Negative because we're buying (debit)
                exp_date,
                {'net_gex': 0, 'flip_point': strike}  # Minimal GEX data
            )

            if position_id:
                self.set_config('last_trade_date', datetime.now().strftime('%Y-%m-%d'))
                self.log_action(
                    'EXECUTE',
                    f"GUARANTEED TRADE: ATM Straddle @ ${strike} ({contracts} contracts) - MINIMUM one trade per day fulfilled",
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
        today = datetime.now()

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
        today = datetime.now()
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
                       entry_price: float, exp_date: str, gex_data: Dict) -> Optional[int]:
        """Execute the trade"""

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        now = datetime.now()

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

        return position_id

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
                        f"Closed {pos['strategy']}: P&L ${unrealized_pnl:+.2f} ({pnl_pct:+.1f}%) - {reason}",
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
        dte = (exp_date - datetime.now()).days
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

        now = datetime.now()

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
