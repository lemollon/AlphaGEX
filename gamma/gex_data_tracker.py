"""
gex_data_tracker.py - Comprehensive GEX Data Tracking System

Tracks what's currently MISSING:
1. GEX by expiration (0DTE, weekly, monthly) - NOT just bucketed
2. GEX change rate (how fast is positioning shifting?)
3. Strike-level gamma (where are the walls building?)
4. GEX levels (GEX_0 through GEX_4)
5. Historical patterns for regime detection

This data feeds into the unified classifier for better decisions.

Author: AlphaGEX
Date: 2025-11-26
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from database_adapter import get_connection
from zoneinfo import ZoneInfo
import json

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Import API client
try:
    from core_classes_and_engines import TradingVolatilityAPI
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False


@dataclass
class GEXSnapshot:
    """Complete GEX snapshot with all expiration data"""
    timestamp: datetime
    symbol: str

    # Total GEX
    net_gex: float
    flip_point: float
    spot_price: float

    # GEX by expiration (what's currently MISSING)
    gex_0dte: float          # Same-day expiration gamma
    gex_weekly: float        # This week's expiration
    gex_monthly: float       # Monthly OPEX gamma
    gex_quarterly: float     # Quarterly expiration

    # GEX levels (support/resistance - currently NOT stored)
    gex_level_0: float       # GEX_0 price level
    gex_level_1: float       # GEX_1
    gex_level_2: float       # GEX_2
    gex_level_3: float       # GEX_3
    gex_level_4: float       # GEX_4
    std_1d_upper: float      # +1 STD (1-day)
    std_1d_lower: float      # -1 STD (1-day)

    # Top strikes by gamma (currently thrown away)
    top_call_strikes: List[Dict]  # [{strike, gamma, oi}, ...]
    top_put_strikes: List[Dict]

    # Change metrics (currently NOT tracked)
    gex_change_1h: float     # GEX change in last hour
    gex_change_4h: float     # GEX change in last 4 hours
    gex_change_rate: float   # GEX change per hour (velocity)

    # Volatility data
    iv: float
    vix: float
    put_call_ratio: float


class GEXDataTracker:
    """
    Comprehensive GEX tracking that captures what you're currently missing.

    TRACKS:
    - GEX by expiration (0DTE, weekly, monthly, quarterly)
    - GEX change velocity (how fast is it moving?)
    - Strike-level gamma (where are walls building?)
    - GEX support/resistance levels
    - Historical patterns for better regime detection
    """

    def __init__(self, symbol: str = "SPY"):
        self.symbol = symbol
        self.api_client = TradingVolatilityAPI() if API_AVAILABLE else None
        self._ensure_tables()

        # In-memory cache for change calculations
        self.recent_snapshots: List[GEXSnapshot] = []
        self.max_cache_size = 100  # Keep last 100 snapshots in memory

    def _ensure_tables(self):
        """Create comprehensive GEX tracking tables"""
        conn = get_connection()
        c = conn.cursor()

        # Main GEX snapshots with expiration breakdown
        c.execute("""
            CREATE TABLE IF NOT EXISTS gex_snapshots_detailed (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                symbol VARCHAR(10) NOT NULL,

                -- Total GEX
                net_gex DECIMAL(15,2),
                flip_point DECIMAL(10,2),
                spot_price DECIMAL(10,2),

                -- GEX by expiration (THE MISSING DATA)
                gex_0dte DECIMAL(15,2),
                gex_weekly DECIMAL(15,2),
                gex_monthly DECIMAL(15,2),
                gex_quarterly DECIMAL(15,2),

                -- GEX levels (support/resistance)
                gex_level_0 DECIMAL(10,2),
                gex_level_1 DECIMAL(10,2),
                gex_level_2 DECIMAL(10,2),
                gex_level_3 DECIMAL(10,2),
                gex_level_4 DECIMAL(10,2),
                std_1d_upper DECIMAL(10,2),
                std_1d_lower DECIMAL(10,2),

                -- Change velocity
                gex_change_1h DECIMAL(15,2),
                gex_change_4h DECIMAL(15,2),
                gex_change_rate DECIMAL(15,4),

                -- Volatility
                iv DECIMAL(8,4),
                vix DECIMAL(8,2),
                put_call_ratio DECIMAL(8,4),

                -- Top strikes (JSON)
                top_call_strikes JSONB,
                top_put_strikes JSONB,

                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, timestamp)
            )
        """)

        # Index for fast lookups
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_gex_snapshots_symbol_time
            ON gex_snapshots_detailed(symbol, timestamp DESC)
        """)

        # GEX change tracking (for velocity calculation)
        c.execute("""
            CREATE TABLE IF NOT EXISTS gex_change_log (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                net_gex DECIMAL(15,2),
                gex_change DECIMAL(15,2),
                change_pct DECIMAL(8,4),
                time_period_minutes INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Strike-level gamma history (the data you're throwing away)
        c.execute("""
            CREATE TABLE IF NOT EXISTS gamma_strike_history (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                strike DECIMAL(10,2) NOT NULL,
                call_gamma DECIMAL(15,2),
                put_gamma DECIMAL(15,2),
                net_gamma DECIMAL(15,2),
                call_oi INTEGER,
                put_oi INTEGER,
                distance_from_spot_pct DECIMAL(8,4),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_gamma_strike_symbol_time
            ON gamma_strike_history(symbol, timestamp DESC)
        """)

        conn.commit()
        conn.close()
        print(f"✅ GEX Data Tracker tables ready for {self.symbol}")

    def fetch_complete_gex_data(self) -> Optional[GEXSnapshot]:
        """
        Fetch ALL GEX data including what's currently missing.

        This is the COMPREHENSIVE fetch that gets:
        - Net GEX
        - GEX by expiration
        - GEX levels
        - Strike-level gamma
        - Change metrics
        """
        if not self.api_client:
            print("❌ API client not available")
            return None

        try:
            now = datetime.now(CENTRAL_TZ)

            # 1. Get basic GEX data
            gex_data = self.api_client.get_net_gamma(self.symbol)
            if not gex_data or gex_data.get('error'):
                return None

            net_gex = gex_data.get('net_gex', 0)
            flip_point = gex_data.get('flip_point', 0)
            spot_price = gex_data.get('spot_price', 0)
            iv = gex_data.get('implied_volatility', 0)
            pcr = gex_data.get('put_call_ratio', 1.0)

            # 2. Get GEX levels (currently NOT stored)
            gex_levels = self.api_client.get_gex_levels(self.symbol)
            gex_level_0 = 0
            gex_level_1 = 0
            gex_level_2 = 0
            gex_level_3 = 0
            gex_level_4 = 0
            std_1d_upper = 0
            std_1d_lower = 0

            if gex_levels and not gex_levels.get('error'):
                levels = gex_levels.get('levels', {})
                gex_level_0 = levels.get('gex_0', 0)
                gex_level_1 = levels.get('gex_1', 0)
                gex_level_2 = levels.get('gex_2', 0)
                gex_level_3 = levels.get('gex_3', 0)
                gex_level_4 = levels.get('gex_4', 0)
                std_1d_upper = levels.get('+1STD (1-day)', 0)
                std_1d_lower = levels.get('-1STD (1-day)', 0)

            # 3. Get GEX by expiration (THE MISSING DATA)
            # Fetch for different expirations
            gex_0dte = self._fetch_gex_for_expiration('1')  # Nearest (0DTE if available)
            gex_weekly = self._fetch_gex_for_expiration('0') - gex_0dte  # Total minus 0DTE
            gex_monthly = self._fetch_gex_for_expiration('2')  # Monthly
            gex_quarterly = 0  # Would need separate fetch

            # 4. Get strike-level gamma (currently thrown away)
            top_call_strikes, top_put_strikes = self._fetch_top_strikes()

            # 5. Calculate change metrics
            gex_change_1h, gex_change_4h, gex_change_rate = self._calculate_change_metrics(net_gex)

            # 6. Get VIX
            try:
                from polygon_data_fetcher import polygon_fetcher
                vix = polygon_fetcher.get_current_price('^VIX') or 17.0
            except (ImportError, Exception):
                vix = 17.0  # Default VIX when unavailable

            snapshot = GEXSnapshot(
                timestamp=now,
                symbol=self.symbol,
                net_gex=net_gex,
                flip_point=flip_point,
                spot_price=spot_price,
                gex_0dte=gex_0dte,
                gex_weekly=gex_weekly,
                gex_monthly=gex_monthly,
                gex_quarterly=gex_quarterly,
                gex_level_0=gex_level_0,
                gex_level_1=gex_level_1,
                gex_level_2=gex_level_2,
                gex_level_3=gex_level_3,
                gex_level_4=gex_level_4,
                std_1d_upper=std_1d_upper,
                std_1d_lower=std_1d_lower,
                top_call_strikes=top_call_strikes,
                top_put_strikes=top_put_strikes,
                gex_change_1h=gex_change_1h,
                gex_change_4h=gex_change_4h,
                gex_change_rate=gex_change_rate,
                iv=iv,
                vix=vix,
                put_call_ratio=pcr
            )

            # Add to cache
            self.recent_snapshots.append(snapshot)
            if len(self.recent_snapshots) > self.max_cache_size:
                self.recent_snapshots = self.recent_snapshots[-self.max_cache_size:]

            return snapshot

        except Exception as e:
            print(f"❌ GEX fetch error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _fetch_gex_for_expiration(self, expiration_code: str) -> float:
        """Fetch GEX for specific expiration"""
        try:
            data = self.api_client.get_gamma_by_expiration(self.symbol, expiration_code)
            if data and not data.get('error'):
                return data.get('net_gex', 0)
            return 0
        except Exception:
            return 0  # Return default on API failure

    def _fetch_top_strikes(self, top_n: int = 10) -> Tuple[List[Dict], List[Dict]]:
        """Fetch top strikes by gamma (currently thrown away)"""
        try:
            # This data comes from gamma_array in the API response
            # Currently only used for display, not stored
            gex_data = self.api_client.get_net_gamma(self.symbol)
            if not gex_data:
                return [], []

            gamma_array = gex_data.get('gamma_array', [])
            if not gamma_array:
                return [], []

            # Sort by gamma magnitude
            calls = sorted(
                [g for g in gamma_array if g.get('call_gamma', 0) > 0],
                key=lambda x: abs(x.get('call_gamma', 0)),
                reverse=True
            )[:top_n]

            puts = sorted(
                [g for g in gamma_array if g.get('put_gamma', 0) < 0],
                key=lambda x: abs(x.get('put_gamma', 0)),
                reverse=True
            )[:top_n]

            return (
                [{'strike': c['strike'], 'gamma': c['call_gamma']} for c in calls],
                [{'strike': p['strike'], 'gamma': p['put_gamma']} for p in puts]
            )
        except Exception:
            return [], []  # Return empty on API failure

    def _calculate_change_metrics(self, current_gex: float) -> Tuple[float, float, float]:
        """Calculate GEX change velocity"""
        if not self.recent_snapshots:
            return 0, 0, 0

        now = datetime.now(CENTRAL_TZ)

        # Find snapshot from 1 hour ago
        gex_1h_ago = current_gex
        gex_4h_ago = current_gex
        time_1h_ago = now - timedelta(hours=1)
        time_4h_ago = now - timedelta(hours=4)

        for snap in reversed(self.recent_snapshots):
            if snap.timestamp <= time_1h_ago and gex_1h_ago == current_gex:
                gex_1h_ago = snap.net_gex
            if snap.timestamp <= time_4h_ago and gex_4h_ago == current_gex:
                gex_4h_ago = snap.net_gex
                break

        change_1h = current_gex - gex_1h_ago
        change_4h = current_gex - gex_4h_ago

        # Change rate = change per hour
        if len(self.recent_snapshots) >= 2:
            oldest = self.recent_snapshots[0]
            hours_elapsed = (now - oldest.timestamp).total_seconds() / 3600
            if hours_elapsed > 0:
                total_change = current_gex - oldest.net_gex
                change_rate = total_change / hours_elapsed
            else:
                change_rate = 0
        else:
            change_rate = 0

        return change_1h, change_4h, change_rate

    def store_snapshot(self, snapshot: GEXSnapshot):
        """Store snapshot to database"""
        conn = get_connection()
        c = conn.cursor()

        try:
            c.execute("""
                INSERT INTO gex_snapshots_detailed (
                    timestamp, symbol, net_gex, flip_point, spot_price,
                    gex_0dte, gex_weekly, gex_monthly, gex_quarterly,
                    gex_level_0, gex_level_1, gex_level_2, gex_level_3, gex_level_4,
                    std_1d_upper, std_1d_lower,
                    gex_change_1h, gex_change_4h, gex_change_rate,
                    iv, vix, put_call_ratio,
                    top_call_strikes, top_put_strikes
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (symbol, timestamp) DO UPDATE SET
                    net_gex = EXCLUDED.net_gex,
                    gex_change_rate = EXCLUDED.gex_change_rate
            """, (
                snapshot.timestamp, snapshot.symbol,
                snapshot.net_gex, snapshot.flip_point, snapshot.spot_price,
                snapshot.gex_0dte, snapshot.gex_weekly, snapshot.gex_monthly, snapshot.gex_quarterly,
                snapshot.gex_level_0, snapshot.gex_level_1, snapshot.gex_level_2,
                snapshot.gex_level_3, snapshot.gex_level_4,
                snapshot.std_1d_upper, snapshot.std_1d_lower,
                snapshot.gex_change_1h, snapshot.gex_change_4h, snapshot.gex_change_rate,
                snapshot.iv, snapshot.vix, snapshot.put_call_ratio,
                json.dumps(snapshot.top_call_strikes),
                json.dumps(snapshot.top_put_strikes)
            ))

            conn.commit()
        except Exception as e:
            print(f"❌ Store snapshot error: {e}")
        finally:
            conn.close()

    def store_strike_history(self, snapshot: GEXSnapshot):
        """Store strike-level gamma history"""
        conn = get_connection()
        c = conn.cursor()

        try:
            # Store top call strikes
            for strike_data in snapshot.top_call_strikes:
                distance_pct = (strike_data['strike'] - snapshot.spot_price) / snapshot.spot_price * 100
                c.execute("""
                    INSERT INTO gamma_strike_history
                    (timestamp, symbol, strike, call_gamma, put_gamma, net_gamma, distance_from_spot_pct)
                    VALUES (%s, %s, %s, %s, 0, %s, %s)
                """, (
                    snapshot.timestamp, snapshot.symbol,
                    strike_data['strike'], strike_data['gamma'], strike_data['gamma'],
                    distance_pct
                ))

            # Store top put strikes
            for strike_data in snapshot.top_put_strikes:
                distance_pct = (strike_data['strike'] - snapshot.spot_price) / snapshot.spot_price * 100
                c.execute("""
                    INSERT INTO gamma_strike_history
                    (timestamp, symbol, strike, call_gamma, put_gamma, net_gamma, distance_from_spot_pct)
                    VALUES (%s, %s, %s, 0, %s, %s, %s)
                """, (
                    snapshot.timestamp, snapshot.symbol,
                    strike_data['strike'], strike_data['gamma'], strike_data['gamma'],
                    distance_pct
                ))

            conn.commit()
        except Exception as e:
            print(f"⚠️ Store strike history error: {e}")
        finally:
            conn.close()

    def collect_and_store(self) -> Optional[GEXSnapshot]:
        """Main collection method - fetch and store everything"""
        snapshot = self.fetch_complete_gex_data()
        if snapshot:
            self.store_snapshot(snapshot)
            self.store_strike_history(snapshot)
            print(f"✅ Stored GEX snapshot: Net ${snapshot.net_gex/1e9:.2f}B, "
                  f"0DTE ${snapshot.gex_0dte/1e9:.2f}B, "
                  f"Change Rate ${snapshot.gex_change_rate/1e9:.4f}B/hr")
        return snapshot

    def get_gex_development(self, hours: int = 24) -> pd.DataFrame:
        """
        Get GEX development over time - THIS IS WHAT YOU ASKED FOR.

        Returns DataFrame showing how GEX is developing across expirations.
        """
        conn = get_connection()

        query = """
            SELECT
                timestamp,
                net_gex,
                gex_0dte,
                gex_weekly,
                gex_monthly,
                gex_change_rate,
                flip_point,
                spot_price,
                vix
            FROM gex_snapshots_detailed
            WHERE symbol = %s
            AND timestamp > NOW() - INTERVAL '%s hours'
            ORDER BY timestamp
        """

        df = pd.read_sql_query(query, conn.raw_connection, params=(self.symbol, hours))
        conn.close()

        return df

    def analyze_gex_momentum(self) -> Dict:
        """
        Analyze GEX momentum - is positioning building or unwinding?

        This tells you:
        - Is GEX accelerating or decelerating?
        - Which expirations are driving the move?
        - Is this a slow grind or fast shift?
        """
        df = self.get_gex_development(hours=8)  # Last 8 hours

        if df.empty or len(df) < 3:
            return {
                'momentum': 'unknown',
                'direction': 'unknown',
                'driver': 'unknown',
                'confidence': 0
            }

        # Safety check for required columns
        if 'net_gex' not in df.columns or 'gex_change_rate' not in df.columns:
            return {
                'momentum': 'unknown',
                'direction': 'unknown',
                'driver': 'unknown',
                'confidence': 0
            }

        # Calculate GEX momentum (with safe access)
        try:
            gex_change = df['net_gex'].iloc[-1] - df['net_gex'].iloc[0]
            gex_acceleration = df['gex_change_rate'].diff().mean()
        except (IndexError, KeyError):
            gex_change = 0
            gex_acceleration = 0

        # Which expiration is driving?
        driver = 'unknown'
        if 'gex_0dte' in df.columns and 'gex_weekly' in df.columns and 'gex_monthly' in df.columns:
            try:
                dte_change = df['gex_0dte'].iloc[-1] - df['gex_0dte'].iloc[0]
                weekly_change = df['gex_weekly'].iloc[-1] - df['gex_weekly'].iloc[0]
                monthly_change = df['gex_monthly'].iloc[-1] - df['gex_monthly'].iloc[0]

                max_change = max(abs(dte_change), abs(weekly_change), abs(monthly_change))
                if max_change == abs(dte_change):
                    driver = '0DTE'
                elif max_change == abs(weekly_change):
                    driver = 'WEEKLY'
                else:
                    driver = 'MONTHLY'
            except (IndexError, KeyError):
                driver = 'unknown'

        # Determine momentum
        if gex_acceleration > 0 and gex_change > 0:
            momentum = 'ACCELERATING_POSITIVE'
        elif gex_acceleration > 0 and gex_change < 0:
            momentum = 'ACCELERATING_NEGATIVE'
        elif gex_acceleration < 0 and gex_change > 0:
            momentum = 'DECELERATING_POSITIVE'
        elif gex_acceleration < 0 and gex_change < 0:
            momentum = 'DECELERATING_NEGATIVE'
        else:
            momentum = 'STABLE'

        return {
            'momentum': momentum,
            'direction': 'POSITIVE' if gex_change > 0 else 'NEGATIVE',
            'driver': driver,
            'gex_change_8h': gex_change,
            'acceleration': gex_acceleration,
            'confidence': min(100, abs(gex_change) / 1e9 * 20)  # Higher change = higher confidence
        }


# Singleton instance
_tracker = None

def get_gex_tracker(symbol: str = "SPY") -> GEXDataTracker:
    """Get GEX tracker singleton"""
    global _tracker
    if _tracker is None or _tracker.symbol != symbol:
        _tracker = GEXDataTracker(symbol)
    return _tracker


if __name__ == "__main__":
    # Test the tracker
    tracker = get_gex_tracker("SPY")

    print("\nCollecting GEX snapshot...")
    snapshot = tracker.collect_and_store()

    if snapshot:
        print(f"\n{'='*60}")
        print("GEX SNAPSHOT SUMMARY")
        print(f"{'='*60}")
        print(f"Net GEX: ${snapshot.net_gex/1e9:.2f}B")
        print(f"0DTE GEX: ${snapshot.gex_0dte/1e9:.2f}B")
        print(f"Weekly GEX: ${snapshot.gex_weekly/1e9:.2f}B")
        print(f"Monthly GEX: ${snapshot.gex_monthly/1e9:.2f}B")
        print(f"")
        print(f"GEX Change (1h): ${snapshot.gex_change_1h/1e9:.2f}B")
        print(f"GEX Change Rate: ${snapshot.gex_change_rate/1e9:.4f}B/hr")
        print(f"")
        print(f"GEX Levels:")
        print(f"  GEX_0: ${snapshot.gex_level_0:.2f}")
        print(f"  GEX_1: ${snapshot.gex_level_1:.2f}")
        print(f"  GEX_2: ${snapshot.gex_level_2:.2f}")
        print(f"")
        print(f"Top Call Strikes: {snapshot.top_call_strikes[:3]}")
        print(f"Top Put Strikes: {snapshot.top_put_strikes[:3]}")
