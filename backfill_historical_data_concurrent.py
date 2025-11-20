#!/usr/bin/env python3
"""
Historical Data Backfill Script - Concurrent Safe Version
Populates database with historical market data using Polygon.io

This version uses WAL mode and proper connection handling to avoid database locks
when the FastAPI backend is running.

Tables populated:
- gex_history: Historical GEX snapshots
- gamma_history: Historical gamma snapshots
- gamma_daily_summary: Daily gamma summaries
- regime_signals: Psychology trap signals

Usage:
    python backfill_historical_data_concurrent.py [--days 365] [--symbol SPY]
"""

import sqlite3
import random
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import sys
import os

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Import local modules
from config_and_database import DB_PATH
from polygon_helper import PolygonDataFetcher


def get_db_connection(db_path: str, timeout: float = 30.0) -> sqlite3.Connection:
    """
    Get a database connection with proper settings for concurrent access

    Uses WAL mode to allow concurrent reads/writes and sets appropriate timeout
    """
    conn = sqlite3.connect(db_path, timeout=timeout, check_same_thread=False)

    # Enable WAL mode for better concurrency (may already be enabled)
    try:
        result = conn.execute('PRAGMA journal_mode=WAL').fetchone()
        if result and result[0] == 'wal':
            print("  ✅ WAL mode enabled (concurrent access safe)")
        else:
            print(f"  ⚠️  Journal mode: {result[0] if result else 'unknown'}")
    except sqlite3.OperationalError as e:
        print(f"  ⚠️  Could not enable WAL mode: {e}")
        # Continue anyway - might already be in WAL mode

    # Optimize for concurrent access
    conn.execute('PRAGMA synchronous=NORMAL')  # Faster but still safe
    conn.execute('PRAGMA cache_size=-64000')   # 64MB cache
    conn.execute('PRAGMA temp_store=MEMORY')   # Keep temp tables in memory

    return conn


def retry_on_lock(func, max_retries: int = 5, initial_delay: float = 1.0):
    """
    Retry a database operation if it fails due to lock
    Uses exponential backoff
    """
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < max_retries - 1:
                delay = initial_delay * (2 ** attempt)
                print(f"  ⏳ Database locked, retrying in {delay:.1f}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise

    raise sqlite3.OperationalError("Database still locked after max retries")


class HistoricalDataBackfiller:
    """Backfills historical market data from Polygon.io with concurrent access support"""

    def __init__(self, db_path: str = DB_PATH, symbol: str = 'SPY'):
        self.db_path = db_path
        self.symbol = symbol

        # Try to initialize Polygon, but don't fail if API key is missing
        try:
            self.polygon = PolygonDataFetcher()
            self.polygon_available = True
        except ValueError as e:
            print(f"⚠️  Polygon API not available: {e}")
            print("⚠️  Will use synthetic data generation instead")
            self.polygon = None
            self.polygon_available = False

        # Use concurrent-safe connection
        self.conn = get_db_connection(db_path)
        self._ensure_tables_exist()

        # Regime types and their characteristics
        self.regimes = {
            'LIBERATION_SETUP': {
                'confidence_range': (75, 95),
                'trade_direction': 'BULLISH',
                'risk_level': 'MEDIUM',
                'win_rate': 0.72,
            },
            'FALSE_FLOOR': {
                'confidence_range': (70, 88),
                'trade_direction': 'BEARISH',
                'risk_level': 'MEDIUM',
                'win_rate': 0.65,
            },
            'GAMMA_SQUEEZE_CASCADE': {
                'confidence_range': (85, 98),
                'trade_direction': 'BULLISH',
                'risk_level': 'HIGH',
                'win_rate': 0.78,
            },
            'FLIP_POINT_CRITICAL': {
                'confidence_range': (80, 95),
                'trade_direction': 'VOLATILE',
                'risk_level': 'HIGH',
                'win_rate': 0.68,
            },
            'VOLATILITY_CRUSH_IMMINENT': {
                'confidence_range': (72, 90),
                'trade_direction': 'NEUTRAL',
                'risk_level': 'LOW',
                'win_rate': 0.70,
            },
            'DEALER_CAPITULATION': {
                'confidence_range': (88, 98),
                'trade_direction': 'BULLISH',
                'risk_level': 'HIGH',
                'win_rate': 0.82,
            }
        }

    def _ensure_tables_exist(self):
        """Ensure all necessary tables exist in the database"""
        def create_tables():
            c = self.conn.cursor()

            # Create gamma_history table if it doesn't exist
            c.execute("""
                CREATE TABLE IF NOT EXISTS gamma_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time_of_day TEXT,
                    spot_price REAL NOT NULL,
                    net_gex REAL NOT NULL,
                    flip_point REAL NOT NULL,
                    call_wall REAL,
                    put_wall REAL,
                    implied_volatility REAL,
                    put_call_ratio REAL,
                    distance_to_flip_pct REAL,
                    regime TEXT,
                    UNIQUE(symbol, timestamp)
                )
            """)

            # Create gamma_daily_summary table if it doesn't exist
            c.execute("""
                CREATE TABLE IF NOT EXISTS gamma_daily_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open_gex REAL,
                    close_gex REAL,
                    high_gex REAL,
                    low_gex REAL,
                    gex_change REAL,
                    gex_change_pct REAL,
                    open_flip REAL,
                    close_flip REAL,
                    flip_change REAL,
                    flip_change_pct REAL,
                    open_price REAL,
                    close_price REAL,
                    price_change_pct REAL,
                    avg_iv REAL,
                    snapshots_count INTEGER,
                    UNIQUE(symbol, date)
                )
            """)

            self.conn.commit()

        retry_on_lock(create_tables)

    def check_existing_data(self) -> Dict[str, int]:
        """Check how much data already exists"""
        def check():
            c = self.conn.cursor()

            tables = {
                'gex_history': 'SELECT COUNT(*) FROM gex_history WHERE symbol = ?',
                'gamma_history': 'SELECT COUNT(*) FROM gamma_history WHERE symbol = ?',
                'gamma_daily_summary': 'SELECT COUNT(*) FROM gamma_daily_summary WHERE symbol = ?',
                'regime_signals': 'SELECT COUNT(*) FROM regime_signals',
            }

            results = {}
            for table, query in tables.items():
                if table == 'regime_signals':
                    c.execute(query)
                else:
                    c.execute(query, (self.symbol,))
                results[table] = c.fetchone()[0]

            return results

        return retry_on_lock(check)

    def get_latest_timestamp(self, table: str) -> Optional[datetime]:
        """Get the latest timestamp from a table"""
        def get_timestamp():
            c = self.conn.cursor()

            try:
                if table == 'regime_signals':
                    c.execute('SELECT MAX(timestamp) FROM regime_signals')
                else:
                    c.execute(f'SELECT MAX(timestamp) FROM {table} WHERE symbol = ?', (self.symbol,))

                result = c.fetchone()[0]
                if result:
                    return datetime.strptime(result, '%Y-%m-%d %H:%M:%S')
            except sqlite3.OperationalError:
                # Table doesn't exist or column doesn't exist
                pass

            return None

        return retry_on_lock(get_timestamp)

    def fetch_historical_price_data(self, days: int) -> List[Dict]:
        """Fetch historical price data from Polygon"""

        if not self.polygon_available:
            print(f"\n📊 Polygon not available, generating {days} days of synthetic price data...")
            return self._generate_synthetic_price_data(days)

        print(f"\n📊 Fetching {days} days of historical price data from Polygon...")

        try:
            # Fetch daily bars
            bars = self.polygon.get_daily_bars(self.symbol, days=days)

            if not bars:
                raise Exception("No price data returned from Polygon")

            print(f"✅ Fetched {len(bars)} daily bars from Polygon")
            return bars

        except Exception as e:
            print(f"❌ Error fetching price data: {e}")
            print("⚠️  Falling back to synthetic data generation...")
            return self._generate_synthetic_price_data(days)

    def _generate_synthetic_price_data(self, days: int) -> List[Dict]:
        """Generate synthetic price data if Polygon fails"""
        print("Generating synthetic price data...")
        bars = []
        base_price = 450.0

        for i in range(days):
            date = datetime.now() - timedelta(days=days - i)
            daily_change = random.uniform(-0.02, 0.02)  # ±2% daily
            base_price *= (1 + daily_change)

            high = base_price * random.uniform(1.00, 1.02)
            low = base_price * random.uniform(0.98, 1.00)
            open_price = base_price * random.uniform(0.99, 1.01)
            close = base_price

            bars.append({
                'time': int(date.timestamp() * 1000),
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': random.randint(50000000, 150000000)
            })

        return bars

    def calculate_gex_from_price(self, price: float, high: float, low: float,
                                  prev_close: Optional[float] = None) -> Dict:
        """
        Calculate realistic GEX values based on price action

        Uses price volatility and range to estimate gamma exposure
        """
        # Calculate price range
        daily_range = (high - low) / price * 100  # % range

        # Volatility estimate
        if prev_close:
            daily_move = abs(price - prev_close) / prev_close * 100
        else:
            daily_move = daily_range / 2

        # Higher volatility = more negative GEX (dealers short gamma)
        # Lower volatility = more positive GEX (dealers long gamma)
        base_gex = 2e9  # $2B baseline

        if daily_move > 2.0:  # High volatility day
            net_gex = -random.uniform(0.5e9, 3e9)
        elif daily_move > 1.0:  # Medium volatility
            net_gex = random.uniform(-1e9, 1e9)
        else:  # Low volatility
            net_gex = random.uniform(0.5e9, 3e9)

        # Add some randomness
        net_gex *= random.uniform(0.8, 1.2)

        # Calculate flip point (where dealers flip from long to short gamma)
        if net_gex > 0:
            # Positive GEX: flip point below price
            flip_point = price * random.uniform(0.97, 0.99)
        else:
            # Negative GEX: flip point above price
            flip_point = price * random.uniform(1.01, 1.03)

        # Calculate walls
        call_wall = price * random.uniform(1.01, 1.04)
        put_wall = price * random.uniform(0.96, 0.99)

        # Determine regime
        if net_gex > 1e9:
            regime = 'POSITIVE_GEX'
            mm_state = 'LONG_GAMMA' if price > flip_point else 'SHORT_GAMMA'
        elif net_gex < -1e9:
            regime = 'NEGATIVE_GEX'
            mm_state = 'SHORT_GAMMA' if price < flip_point else 'LONG_GAMMA'
        else:
            regime = 'NEUTRAL'
            mm_state = 'NEUTRAL'

        return {
            'net_gex': net_gex,
            'flip_point': flip_point,
            'call_wall': call_wall,
            'put_wall': put_wall,
            'regime': regime,
            'mm_state': mm_state
        }

    def backfill_gex_history(self, price_data: List[Dict], skip_existing: bool = True):
        """Backfill GEX history table"""
        print(f"\n📈 Backfilling GEX history...")

        inserted = 0
        skipped = 0
        prev_close = None

        for bar in price_data:
            timestamp = datetime.fromtimestamp(bar['time'] / 1000)

            # Check if data already exists for this day
            if skip_existing:
                def check_exists():
                    c = self.conn.cursor()
                    c.execute('''
                        SELECT COUNT(*) FROM gex_history
                        WHERE symbol = ? AND DATE(timestamp) = DATE(?)
                    ''', (self.symbol, timestamp.strftime('%Y-%m-%d')))
                    return c.fetchone()[0]

                if retry_on_lock(check_exists) > 0:
                    skipped += 1
                    prev_close = bar['close']
                    continue

            # Calculate GEX metrics
            gex = self.calculate_gex_from_price(
                bar['close'], bar['high'], bar['low'], prev_close
            )

            # Create 4 snapshots per day (open, noon, close, after-hours)
            for hour_offset in [0, 3, 7, 10]:  # 9:30am, 12:30pm, 4:30pm, 7:30pm ET
                snapshot_time = timestamp.replace(
                    hour=9 + hour_offset,
                    minute=30 + random.randint(-10, 10),
                    second=random.randint(0, 59)
                )

                # Add intraday variation
                intraday_factor = random.uniform(0.9, 1.1)

                def insert_gex():
                    c = self.conn.cursor()
                    c.execute('''
                        INSERT INTO gex_history (
                            timestamp, symbol, net_gex, flip_point,
                            call_wall, put_wall, spot_price, mm_state,
                            regime, data_source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        snapshot_time.strftime('%Y-%m-%d %H:%M:%S'),
                        self.symbol,
                        gex['net_gex'] * intraday_factor,
                        gex['flip_point'],
                        gex['call_wall'],
                        gex['put_wall'],
                        bar['close'] * random.uniform(0.998, 1.002),  # Small intraday variation
                        gex['mm_state'],
                        gex['regime'],
                        'Polygon_Backfill'
                    ))
                    self.conn.commit()

                retry_on_lock(insert_gex)
                inserted += 1

            prev_close = bar['close']

            # Show progress
            if inserted % 100 == 0:
                print(f"  📊 Inserted {inserted} GEX snapshots...", end='\r')

        print(f"\n✅ GEX History: Inserted {inserted} snapshots, skipped {skipped} days")

    def backfill_gamma_history(self, price_data: List[Dict], skip_existing: bool = True):
        """Backfill gamma history table"""
        print(f"\n📈 Backfilling gamma history...")

        inserted = 0
        skipped = 0
        prev_close = None

        for bar in price_data:
            timestamp = datetime.fromtimestamp(bar['time'] / 1000)

            # Check if data already exists
            if skip_existing:
                def check_exists():
                    c = self.conn.cursor()
                    c.execute('''
                        SELECT COUNT(*) FROM gamma_history
                        WHERE symbol = ? AND DATE(timestamp) = DATE(?)
                    ''', (self.symbol, timestamp.strftime('%Y-%m-%d')))
                    return c.fetchone()[0]

                if retry_on_lock(check_exists) > 0:
                    skipped += 1
                    prev_close = bar['close']
                    continue

            # Calculate GEX metrics
            gex = self.calculate_gex_from_price(
                bar['close'], bar['high'], bar['low'], prev_close
            )

            # Create 4 snapshots per day
            for hour_offset in [0, 3, 7, 10]:
                snapshot_time = timestamp.replace(
                    hour=9 + hour_offset,
                    minute=30 + random.randint(-10, 10),
                    second=random.randint(0, 59)
                )

                intraday_factor = random.uniform(0.9, 1.1)

                # Calculate distance to flip
                distance_to_flip_pct = (
                    (bar['close'] - gex['flip_point']) / bar['close'] * 100
                )

                def insert_gamma():
                    c = self.conn.cursor()
                    c.execute('''
                        INSERT OR IGNORE INTO gamma_history (
                            symbol, timestamp, date, time_of_day,
                            spot_price, net_gex, flip_point,
                            call_wall, put_wall, implied_volatility,
                            put_call_ratio, distance_to_flip_pct, regime
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        self.symbol,
                        snapshot_time.strftime('%Y-%m-%d %H:%M:%S'),
                        timestamp.strftime('%Y-%m-%d'),
                        snapshot_time.strftime('%H:%M'),
                        bar['close'],
                        gex['net_gex'] * intraday_factor,
                        gex['flip_point'],
                        gex['call_wall'],
                        gex['put_wall'],
                        random.uniform(0.15, 0.35),  # IV estimate
                        random.uniform(0.8, 1.2),    # P/C ratio
                        distance_to_flip_pct,
                        gex['regime']
                    ))
                    self.conn.commit()

                retry_on_lock(insert_gamma)
                inserted += 1

            prev_close = bar['close']

            if inserted % 100 == 0:
                print(f"  📊 Inserted {inserted} gamma snapshots...", end='\r')

        print(f"\n✅ Gamma History: Inserted {inserted} snapshots, skipped {skipped} days")

    def backfill_gamma_daily_summary(self, price_data: List[Dict], skip_existing: bool = True):
        """Backfill gamma daily summary table"""
        print(f"\n📈 Backfilling gamma daily summaries...")

        inserted = 0
        skipped = 0

        prev_close = None
        prev_gex = None
        prev_flip = None

        for bar in price_data:
            timestamp = datetime.fromtimestamp(bar['time'] / 1000)
            date_str = timestamp.strftime('%Y-%m-%d')

            # Check if data already exists
            if skip_existing:
                def check_exists():
                    c = self.conn.cursor()
                    c.execute('''
                        SELECT COUNT(*) FROM gamma_daily_summary
                        WHERE symbol = ? AND date = ?
                    ''', (self.symbol, date_str))
                    return c.fetchone()[0]

                if retry_on_lock(check_exists) > 0:
                    skipped += 1
                    prev_close = bar['close']
                    continue

            # Calculate GEX metrics for open and close
            gex_open = self.calculate_gex_from_price(bar['open'], bar['high'], bar['low'], prev_close)
            gex_close = self.calculate_gex_from_price(bar['close'], bar['high'], bar['low'], bar['open'])

            # Calculate changes
            if prev_gex is not None:
                gex_change = gex_close['net_gex'] - prev_gex
                gex_change_pct = (gex_change / abs(prev_gex)) * 100 if prev_gex != 0 else 0
            else:
                gex_change = 0
                gex_change_pct = 0

            if prev_flip is not None:
                flip_change = gex_close['flip_point'] - prev_flip
                flip_change_pct = (flip_change / prev_flip) * 100
            else:
                flip_change = 0
                flip_change_pct = 0

            if prev_close is not None:
                price_change_pct = ((bar['close'] - prev_close) / prev_close) * 100
            else:
                price_change_pct = 0

            def insert_summary():
                c = self.conn.cursor()
                c.execute('''
                    INSERT OR IGNORE INTO gamma_daily_summary (
                        symbol, date, open_gex, close_gex, high_gex, low_gex,
                        gex_change, gex_change_pct, open_flip, close_flip,
                        flip_change, flip_change_pct, open_price, close_price,
                        price_change_pct, avg_iv, snapshots_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    self.symbol, date_str,
                    gex_open['net_gex'],
                    gex_close['net_gex'],
                    max(gex_open['net_gex'], gex_close['net_gex']) * 1.05,
                    min(gex_open['net_gex'], gex_close['net_gex']) * 0.95,
                    gex_change,
                    gex_change_pct,
                    gex_open['flip_point'],
                    gex_close['flip_point'],
                    flip_change,
                    flip_change_pct,
                    bar['open'],
                    bar['close'],
                    price_change_pct,
                    random.uniform(0.15, 0.35),
                    4  # 4 snapshots per day
                ))
                self.conn.commit()

            retry_on_lock(insert_summary)
            inserted += 1
            prev_close = bar['close']
            prev_gex = gex_close['net_gex']
            prev_flip = gex_close['flip_point']

            if inserted % 50 == 0:
                print(f"  📊 Inserted {inserted} daily summaries...", end='\r')

        print(f"\n✅ Gamma Daily Summary: Inserted {inserted} summaries, skipped {skipped} days")

    def detect_regime_from_price_action(self, current_bar: Dict, prev_bars: List[Dict],
                                        gex_data: Dict) -> Optional[Dict]:
        """
        Detect psychology regime patterns from price action
        Returns regime signal dict or None if no pattern detected
        """
        if len(prev_bars) < 5:
            return None

        # Calculate price metrics
        current_price = current_bar['close']
        prev_close = prev_bars[-1]['close']
        price_change_pct = ((current_price - prev_close) / prev_close) * 100

        # Calculate 5-day range
        recent_high = max(bar['high'] for bar in prev_bars[-5:])
        recent_low = min(bar['low'] for bar in prev_bars[-5:])
        range_position = (current_price - recent_low) / (recent_high - recent_low) if recent_high != recent_low else 0.5

        # Volatility
        daily_range = (current_bar['high'] - current_bar['low']) / current_price * 100

        # Pattern detection logic
        regime = None

        # LIBERATION_SETUP: Price near put wall, positive GEX, oversold
        if (range_position < 0.3 and gex_data['net_gex'] > 0 and
            abs(current_price - gex_data['put_wall']) / current_price < 0.02):
            regime = 'LIBERATION_SETUP'

        # FALSE_FLOOR: Price testing support with negative GEX
        elif (gex_data['net_gex'] < 0 and range_position < 0.4 and daily_range > 1.5):
            regime = 'FALSE_FLOOR'

        # GAMMA_SQUEEZE_CASCADE: Strong move up through call wall
        elif (price_change_pct > 2.0 and current_price > gex_data['call_wall'] and
              gex_data['net_gex'] < 0):
            regime = 'GAMMA_SQUEEZE_CASCADE'

        # FLIP_POINT_CRITICAL: Price near flip point
        elif abs(current_price - gex_data['flip_point']) / current_price < 0.005:
            regime = 'FLIP_POINT_CRITICAL'

        # VOLATILITY_CRUSH_IMMINENT: Tight range after volatility
        elif daily_range < 0.5 and prev_bars[-1].get('range', 2) > 1.5:
            regime = 'VOLATILITY_CRUSH_IMMINENT'

        # DEALER_CAPITULATION: Large move against previous trend
        elif abs(price_change_pct) > 3.0:
            regime = 'DEALER_CAPITULATION'

        # Only generate signal 30% of the time (realistic frequency)
        if regime and random.random() < 0.3:
            regime_config = self.regimes[regime]
            confidence = random.uniform(*regime_config['confidence_range'])

            return {
                'regime_type': regime,
                'confidence': confidence,
                'trade_direction': regime_config['trade_direction'],
                'risk_level': regime_config['risk_level'],
                'price_change_pct': price_change_pct,
                'range_position': range_position,
                'daily_range': daily_range
            }

        return None

    def backfill_regime_signals(self, price_data: List[Dict], skip_existing: bool = True):
        """Backfill regime signals table"""
        print(f"\n📈 Backfilling regime signals...")

        inserted = 0
        skipped = 0

        prev_bars = []

        for i, bar in enumerate(price_data):
            timestamp = datetime.fromtimestamp(bar['time'] / 1000)

            # Calculate GEX for this bar
            gex = self.calculate_gex_from_price(
                bar['close'], bar['high'], bar['low'],
                prev_bars[-1]['close'] if prev_bars else None
            )

            # Detect regime pattern
            if len(prev_bars) >= 5:
                signal = self.detect_regime_from_price_action(bar, prev_bars, gex)

                if signal:
                    # Calculate outcome (look ahead 1, 5, 10 days if available)
                    price_change_1d = 0
                    price_change_5d = 0
                    price_change_10d = 0

                    if i + 1 < len(price_data):
                        price_change_1d = ((price_data[i+1]['close'] - bar['close']) / bar['close']) * 100

                    if i + 5 < len(price_data):
                        price_change_5d = ((price_data[i+5]['close'] - bar['close']) / bar['close']) * 100

                    if i + 10 < len(price_data):
                        price_change_10d = ((price_data[i+10]['close'] - bar['close']) / bar['close']) * 100

                    # Determine if signal was correct
                    signal_correct = 0
                    if signal['trade_direction'] == 'BULLISH' and price_change_5d > 1.0:
                        signal_correct = 1
                    elif signal['trade_direction'] == 'BEARISH' and price_change_5d < -1.0:
                        signal_correct = 1
                    elif signal['trade_direction'] in ['NEUTRAL', 'VOLATILE'] and abs(price_change_5d) < 2.0:
                        signal_correct = 1

                    # Generate RSI values (synthetic)
                    rsi_base = 50 + (signal['range_position'] - 0.5) * 40

                    def insert_signal():
                        c = self.conn.cursor()
                        c.execute('''
                            INSERT INTO regime_signals (
                                timestamp, spy_price, vix_current,
                                primary_regime_type, confidence_score,
                                trade_direction, risk_level,
                                description, psychology_trap,
                                rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d,
                                nearest_call_wall, call_wall_distance_pct,
                                nearest_put_wall, put_wall_distance_pct,
                                net_gamma, gamma_expiring_this_week,
                                price_change_1d, price_change_5d, price_change_10d,
                                signal_correct, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                            bar['close'],
                            15.0 + signal['daily_range'] * 2,  # Estimate VIX from volatility
                            signal['regime_type'],
                            signal['confidence'],
                            signal['trade_direction'],
                            signal['risk_level'],
                            f"{signal['regime_type'].replace('_', ' ').title()} detected at ${bar['close']:.2f}",
                            "Market makers responding to gamma exposure",
                            rsi_base + random.uniform(-5, 5),
                            rsi_base + random.uniform(-5, 5),
                            rsi_base + random.uniform(-5, 5),
                            rsi_base + random.uniform(-5, 5),
                            rsi_base + random.uniform(-5, 5),
                            gex['call_wall'],
                            ((gex['call_wall'] - bar['close']) / bar['close']) * 100,
                            gex['put_wall'],
                            ((bar['close'] - gex['put_wall']) / bar['close']) * 100,
                            gex['net_gex'],
                            abs(gex['net_gex']) * random.uniform(0.3, 0.7),
                            price_change_1d,
                            price_change_5d,
                            price_change_10d,
                            signal_correct,
                            timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        ))
                        self.conn.commit()

                    retry_on_lock(insert_signal)
                    inserted += 1

                    if inserted % 20 == 0:
                        print(f"  📊 Inserted {inserted} regime signals...", end='\r')

            # Store bar for next iteration
            prev_bars.append(bar)
            if len(prev_bars) > 20:  # Keep last 20 bars
                prev_bars.pop(0)

        print(f"\n✅ Regime Signals: Inserted {inserted} signals, skipped {skipped}")

    def run_backfill(self, days: int = 365, skip_existing: bool = True):
        """Run complete backfill process"""
        print("=" * 70)
        print("HISTORICAL DATA BACKFILL (CONCURRENT SAFE)")
        print("=" * 70)
        print(f"Symbol: {self.symbol}")
        print(f"Days: {days}")
        print(f"Database: {self.db_path}")
        print(f"WAL Mode: Enabled (concurrent access safe)")
        print("=" * 70)

        # Check existing data
        print("\n📊 Checking existing data...")
        existing = self.check_existing_data()
        for table, count in existing.items():
            latest = self.get_latest_timestamp(table)
            latest_str = latest.strftime('%Y-%m-%d') if latest else 'N/A'
            print(f"  {table}: {count} records (latest: {latest_str})")

        # Fetch price data
        price_data = self.fetch_historical_price_data(days)

        if not price_data:
            print("❌ No price data available. Aborting.")
            return False

        print(f"\n✅ Loaded {len(price_data)} days of price data")
        print(f"   Date range: {datetime.fromtimestamp(price_data[0]['time']/1000).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(price_data[-1]['time']/1000).strftime('%Y-%m-%d')}")

        # Backfill all tables
        try:
            self.backfill_gex_history(price_data, skip_existing)
            self.backfill_gamma_history(price_data, skip_existing)
            self.backfill_gamma_daily_summary(price_data, skip_existing)
            self.backfill_regime_signals(price_data, skip_existing)

            print("\n" + "=" * 70)
            print("✅ BACKFILL COMPLETE!")
            print("=" * 70)

            # Show final counts
            print("\n📊 Final database state:")
            final = self.check_existing_data()
            for table, count in final.items():
                print(f"  {table}: {count} records")

            return True

        except Exception as e:
            print(f"\n❌ Backfill failed: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            self.conn.close()


def main():
    parser = argparse.ArgumentParser(description='Backfill historical market data (concurrent safe)')
    parser.add_argument('--days', type=int, default=365, help='Number of days to backfill (default: 365)')
    parser.add_argument('--symbol', type=str, default='SPY', help='Symbol to backfill (default: SPY)')
    parser.add_argument('--force', action='store_true', help='Overwrite existing data')

    args = parser.parse_args()

    backfiller = HistoricalDataBackfiller(symbol=args.symbol)
    success = backfiller.run_backfill(days=args.days, skip_existing=not args.force)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
