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

            # Step 2: Analyze market and find best trade
            trade = self._analyze_and_find_trade(gex_data, skew_data, spot_price)

            if not trade:
                self.log_action('ERROR', 'No valid trade found', success=False)
                return None

            # Step 3: Get REAL option price
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

            # Step 4: Calculate position size for $5K account
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

            # Step 5: Execute trade automatically
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
            self.log_action('ERROR', f'Exception in trade execution: {str(e)}', success=False)
            import traceback
            traceback.print_exc()
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

    def _get_expiration_string(self, dte: int) -> str:
        """Get expiration date string for options"""
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
        """Check if position should be closed"""

        # Exit 1: Profit target (+50%)
        if pnl_pct >= 50:
            return True, f"Profit target hit: +{pnl_pct:.1f}%"

        # Exit 2: Stop loss (-30%)
        if pnl_pct <= -30:
            return True, f"Stop loss hit: {pnl_pct:.1f}%"

        # Exit 3: Expiration approaching (1 DTE or less)
        exp_date = datetime.strptime(pos['expiration_date'], '%Y-%m-%d')
        dte = (exp_date - datetime.now()).days
        if dte <= 1:
            return True, f"Expiration approaching: {dte} DTE"

        # Exit 4: GEX regime flip
        entry_gex = pos['entry_net_gex']
        current_gex = gex_data.get('net_gex', 0)

        if (entry_gex > 0 and current_gex < 0) or (entry_gex < 0 and current_gex > 0):
            return True, "GEX regime flip - thesis invalidated"

        # Exit 5: Early profit (+25% with 5+ DTE)
        if pnl_pct >= 25 and dte >= 5:
            return True, f"Early profit: +{pnl_pct:.1f}% with {dte} DTE"

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
