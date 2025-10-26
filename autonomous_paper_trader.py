"""
Autonomous Paper Trader - Fully Automated SPY Trading
Finds and executes trades automatically with ZERO manual intervention
Starting capital: $5,000
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Tuple
import streamlit as st
from config_and_database import DB_PATH
import yfinance as yf
import time


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
        GUARANTEED TRADE: If no directional setup, fall back to Iron Condor for premium
        Returns position ID if successful
        """

        # Check if we should trade today
        if not self.should_trade_today():
            self.log_action('SKIP', 'Already traded today or market closed', success=True)
            return None

        self.log_action('START', 'Beginning daily trade search')

        try:
            # Step 1: Get SPY GEX data
            gex_data = api_client.get_net_gamma('SPY')
            skew_data = api_client.get_skew_data('SPY')

            if not gex_data or gex_data.get('error'):
                self.log_action('ERROR', 'Failed to get GEX data', success=False)
                return None

            spot_price = gex_data.get('spot_price', 0)
            if spot_price == 0:
                self.log_action('ERROR', 'Invalid spot price', success=False)
                return None

            # Step 2: Try to find high-confidence directional trade
            trade = self._analyze_and_find_trade(gex_data, skew_data, spot_price)

            # GUARANTEED TRADE: If no high-confidence setup, do Iron Condor
            if not trade or trade.get('confidence', 0) < 70:
                self.log_action('FALLBACK', 'No high-confidence directional setup - creating Iron Condor for premium collection')
                return self._execute_iron_condor(spot_price, gex_data, api_client)

            # Step 3: Execute directional trade (calls/puts)
            return self._execute_directional_trade(trade, gex_data, api_client)

        except Exception as e:
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

    def _analyze_and_find_trade(self, gex_data: Dict, skew_data: Dict, spot: float) -> Optional[Dict]:
        """Analyze market and return best trade"""

        net_gex = gex_data.get('net_gex', 0)
        flip = gex_data.get('flip_point', spot)
        call_wall = gex_data.get('call_wall', 0)
        put_wall = gex_data.get('put_wall', 0)

        distance_to_flip = ((flip - spot) / spot * 100) if spot else 0

        # Determine strategy based on GEX regime
        # REGIME 1: Negative GEX below flip = SQUEEZE
        if net_gex < -1e9 and spot < flip:
            strike = round(flip / 5) * 5
            return {
                'symbol': 'SPY',
                'strategy': 'Negative GEX Squeeze',
                'action': 'BUY_CALL',
                'option_type': 'call',
                'strike': strike,
                'dte': 5,
                'confidence': min(85, 70 + abs(distance_to_flip) * 3),
                'target': flip,
                'stop': spot * 0.985,
                'reasoning': f"SQUEEZE: Net GEX ${net_gex/1e9:.2f}B (negative). Dealers SHORT gamma. Price ${spot:.2f} is {abs(distance_to_flip):.2f}% below flip ${flip:.2f}. When SPY rallies, dealers must BUY → accelerates move."
            }

        # REGIME 2: Negative GEX above flip = BREAKDOWN
        elif net_gex < -1e9 and spot >= flip:
            strike = round(flip / 5) * 5
            return {
                'symbol': 'SPY',
                'strategy': 'Negative GEX Breakdown',
                'action': 'BUY_PUT',
                'option_type': 'put',
                'strike': strike,
                'dte': 5,
                'confidence': min(80, 65 + abs(distance_to_flip) * 3),
                'target': flip,
                'stop': spot * 1.015,
                'reasoning': f"BREAKDOWN: Net GEX ${net_gex/1e9:.2f}B (negative). Dealers SHORT gamma. Price ${spot:.2f} is {abs(distance_to_flip):.2f}% above flip ${flip:.2f}. Any selling forces dealers to SELL → accelerates decline."
            }

        # REGIME 3: High positive GEX = SHORT PREMIUM (but for $5K, just directional)
        elif net_gex > 1e9:
            # For small account, trade directional based on position vs flip
            if spot < flip:
                strike = round(spot / 5) * 5
                return {
                    'symbol': 'SPY',
                    'strategy': 'Range-Bound Bullish',
                    'action': 'BUY_CALL',
                    'option_type': 'call',
                    'strike': strike,
                    'dte': 7,
                    'confidence': 70,
                    'target': flip,
                    'stop': spot * 0.98,
                    'reasoning': f"RANGE: Net GEX ${net_gex/1e9:.2f}B (positive). Dealers LONG gamma, will fade moves. Price below flip → lean bullish toward ${flip:.2f}."
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
                    'confidence': 70,
                    'target': flip,
                    'stop': spot * 1.02,
                    'reasoning': f"RANGE: Net GEX ${net_gex/1e9:.2f}B (positive). Dealers LONG gamma, will fade moves. Price above flip → lean bearish toward ${flip:.2f}."
                }

        # REGIME 4: Neutral - trade toward flip
        else:
            if spot < flip:
                strike = round(spot / 5) * 5
                return {
                    'symbol': 'SPY',
                    'strategy': 'Neutral Bullish',
                    'action': 'BUY_CALL',
                    'option_type': 'call',
                    'strike': strike,
                    'dte': 7,
                    'confidence': 65,
                    'target': flip,
                    'stop': spot * 0.98,
                    'reasoning': f"NEUTRAL: Net GEX ${net_gex/1e9:.2f}B. Price ${spot:.2f} below flip ${flip:.2f}. Lean bullish toward flip point."
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
                    'confidence': 65,
                    'target': flip,
                    'stop': spot * 1.02,
                    'reasoning': f"NEUTRAL: Net GEX ${net_gex/1e9:.2f}B. Price ${spot:.2f} above flip ${flip:.2f}. Lean bearish toward flip point."
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
        import streamlit as st
        import os

        # Check if Claude API is available
        # Check environment variables first (for Render), then secrets (for local)
        claude_api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("claude_api_key", "")
        if not claude_api_key:
            try:
                claude_api_key = st.secrets.get("claude_api_key", "")
            except:
                claude_api_key = ""

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
