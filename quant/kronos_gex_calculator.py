"""
KRONOS GEX Calculator - Calculate Historical GEX from ORAT Options Data
========================================================================

PURPOSE:
Calculate Gamma Exposure (GEX) from ORAT historical options data used by KRONOS.
This enables:
1. Historical GEX analysis for backtesting
2. GEX as ML feature for ARES advisor
3. Understanding how GEX correlates with Iron Condor outcomes

GEX FORMULA:
    GEX_strike = gamma × open_interest × 100 × spot_price²

    Net GEX = Σ(Call_GEX) - Σ(Put_GEX)

    Positive GEX = Market makers long gamma = Mean reversion = Good for Iron Condors
    Negative GEX = Market makers short gamma = Trending = Bad for Iron Condors

ORAT DATA STRUCTURE:
    - gamma: Per-strike gamma value
    - call_oi: Call open interest
    - put_oi: Put open interest
    - strike: Strike price
    - underlying_price: Spot price

Author: AlphaGEX Quant
Date: 2025-12-10
"""
from __future__ import annotations

import os
import sys
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, field

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


@dataclass
class GEXData:
    """GEX calculation result for a single day"""
    trade_date: str
    symbol: str
    spot_price: float

    # Core GEX metrics
    net_gex: float              # Net gamma exposure (call - put)
    call_gex: float             # Total call gamma exposure
    put_gex: float              # Total put gamma exposure (negative)

    # Key levels
    call_wall: float            # Strike with highest call GEX (resistance)
    put_wall: float             # Strike with highest put GEX (support)
    flip_point: float           # Where GEX crosses zero

    # Normalized metrics for ML
    gex_normalized: float       # GEX / spot_price^2 (scale-independent)
    gex_regime: str             # 'POSITIVE', 'NEGATIVE', 'NEUTRAL'
    distance_to_flip_pct: float # (spot - flip) / spot * 100

    # Position relative to walls
    above_call_wall: bool
    below_put_wall: bool
    between_walls: bool

    # Per-strike breakdown (optional)
    strikes_data: List[Dict] = field(default_factory=list)


@dataclass
class GEXTimeSeries:
    """Collection of GEX data over time"""
    symbol: str
    start_date: str
    end_date: str
    data: List[GEXData]

    # Summary statistics
    avg_net_gex: float = 0
    pct_positive_gex: float = 0
    pct_negative_gex: float = 0

    def __post_init__(self):
        if self.data:
            self.avg_net_gex = sum(d.net_gex for d in self.data) / len(self.data)
            self.pct_positive_gex = sum(1 for d in self.data if d.net_gex > 0) / len(self.data) * 100
            self.pct_negative_gex = sum(1 for d in self.data if d.net_gex < 0) / len(self.data) * 100


class KronosGEXCalculator:
    """
    Calculate GEX from ORAT options data used by KRONOS.

    Uses the same database as KRONOS backtester but focuses on
    extracting GEX metrics for ML features.
    """

    # GEX regime thresholds (normalized)
    POSITIVE_THRESHOLD = 0.5e9    # Above this = strong positive GEX
    NEGATIVE_THRESHOLD = -0.5e9   # Below this = strong negative GEX

    def __init__(self, ticker: str = "SPX"):
        self.ticker = ticker
        self.conn = None

    def get_connection(self):
        """Get database connection for ORAT options data"""
        import psycopg2
        from urllib.parse import urlparse

        database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')

        if not database_url:
            raise ValueError("DATABASE_URL not set")

        result = urlparse(database_url)
        conn = psycopg2.connect(
            host=result.hostname,
            port=result.port or 5432,
            user=result.username,
            password=result.password,
            database=result.path[1:],
            connect_timeout=30
        )
        return conn

    def get_most_recent_date(self) -> Optional[str]:
        """
        Get the most recent date with ORAT data for this ticker.

        Returns:
            Date string in YYYY-MM-DD format, or None if no data
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT MAX(trade_date)
                FROM orat_options_eod
                WHERE ticker = %s
                  AND gamma IS NOT NULL
                  AND gamma > 0
                  AND (call_oi > 0 OR put_oi > 0)
            """, (self.ticker,))

            row = cursor.fetchone()
            conn.close()

            if row and row[0]:
                return row[0].strftime('%Y-%m-%d')
            return None
        except Exception as e:
            logger.error(f"Error getting most recent ORAT date: {e}")
            return None

    def get_gex_for_today_or_recent(self, dte_max: int = 7) -> Tuple[Optional['GEXData'], str]:
        """
        Get GEX data for today, or fall back to most recent available date.

        ORAT data is end-of-day, so today's date won't have data until after market close.
        This method handles that by falling back to the most recent available date.

        Args:
            dte_max: Maximum days to expiration to include

        Returns:
            Tuple of (GEXData or None, source description string)
        """
        from datetime import datetime

        today = datetime.now().strftime('%Y-%m-%d')

        # Try today first
        gex = self.calculate_gex_for_date(today, dte_max)
        if gex:
            return gex, f'kronos_live_{today}'

        # Fall back to most recent available date
        recent_date = self.get_most_recent_date()
        if recent_date:
            logger.info(f"No ORAT data for today ({today}), using most recent: {recent_date}")
            gex = self.calculate_gex_for_date(recent_date, dte_max)
            if gex:
                return gex, f'kronos_historical_{recent_date}'

        return None, 'no_data'

    def calculate_gex_for_date(
        self,
        trade_date: str,
        dte_max: int = 7,
        include_strikes_data: bool = False
    ) -> Optional[GEXData]:
        """
        Calculate GEX for a specific trading date.

        Args:
            trade_date: Date in YYYY-MM-DD format
            dte_max: Maximum days to expiration to include (default 7 for weekly)
            include_strikes_data: Whether to include per-strike breakdown

        Returns:
            GEXData with all GEX metrics, or None if no data
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Query ORAT data for this date
            # We need gamma, call_oi, put_oi, strike, underlying_price
            cursor.execute("""
                SELECT
                    strike,
                    gamma,
                    call_oi,
                    put_oi,
                    underlying_price,
                    dte
                FROM orat_options_eod
                WHERE ticker = %s
                  AND trade_date = %s
                  AND dte <= %s
                  AND gamma IS NOT NULL
                  AND gamma > 0
                  AND (call_oi > 0 OR put_oi > 0)
                ORDER BY strike
            """, (self.ticker, trade_date, dte_max))

            rows = cursor.fetchall()

            if not rows:
                # Run diagnostic query to understand WHY no data
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_rows,
                        COUNT(CASE WHEN gamma IS NOT NULL THEN 1 END) as gamma_not_null,
                        COUNT(CASE WHEN gamma > 0 THEN 1 END) as gamma_positive,
                        COUNT(CASE WHEN call_oi > 0 OR put_oi > 0 THEN 1 END) as has_oi,
                        COUNT(CASE WHEN dte <= %s THEN 1 END) as dte_eligible
                    FROM orat_options_eod
                    WHERE ticker = %s AND trade_date = %s
                """, (dte_max, self.ticker, trade_date))
                diag = cursor.fetchone()
                conn.close()

                if diag and diag[0] > 0:
                    logger.warning(
                        f"GEX FAIL for {trade_date}: {diag[0]} rows exist but "
                        f"gamma_not_null={diag[1]}, gamma>0={diag[2]}, has_oi={diag[3]}, dte<={dte_max}={diag[4]}"
                    )
                else:
                    logger.debug(f"No ORAT data for {trade_date} - no rows in database")
                return None

            conn.close()

            # Get spot price from first row
            spot_price = float(rows[0][4])  # underlying_price

            if spot_price <= 0:
                logger.warning(f"Invalid spot price for {trade_date}")
                return None

            # Calculate GEX by strike
            strikes_gex = {}
            total_call_gex = 0
            total_put_gex = 0

            # Track walls - we want MEANINGFUL support/resistance levels
            # Not just the nearest ATM strikes (which always have highest gamma)
            max_call_gex = 0
            max_put_gex = 0

            # Minimum distance for walls to be meaningful (0.5% from spot)
            # This ensures walls represent actual support/resistance, not just ATM strikes
            min_wall_distance = spot_price * 0.005  # 0.5%

            # Default walls to None - will find meaningful ones
            call_wall = None
            put_wall = None

            for row in rows:
                strike = float(row[0])
                gamma = float(row[1]) if row[1] else 0
                call_oi = int(row[2]) if row[2] else 0
                put_oi = int(row[3]) if row[3] else 0

                if strike <= 0 or gamma <= 0:
                    continue

                # GEX = gamma × OI × 100 × spot²
                # Contract multiplier is 100 for standard options
                call_gex_strike = gamma * call_oi * 100 * (spot_price ** 2) if call_oi > 0 else 0
                put_gex_strike = gamma * put_oi * 100 * (spot_price ** 2) if put_oi > 0 else 0

                # Calls are positive GEX, puts are negative GEX
                net_gex_strike = call_gex_strike - put_gex_strike

                strikes_gex[strike] = {
                    'call_gex': call_gex_strike,
                    'put_gex': -put_gex_strike,  # Store as negative
                    'net_gex': net_gex_strike,
                    'call_oi': call_oi,
                    'put_oi': put_oi,
                    'gamma': gamma
                }

                total_call_gex += call_gex_strike
                total_put_gex += put_gex_strike

                # Call wall (RESISTANCE) = highest call GEX that is meaningfully ABOVE spot
                # Must be at least 0.5% above spot to be a real resistance level
                if strike >= spot_price + min_wall_distance and call_gex_strike > max_call_gex:
                    max_call_gex = call_gex_strike
                    call_wall = strike

                # Put wall (SUPPORT) = highest put GEX that is meaningfully BELOW spot
                # Must be at least 0.5% below spot to be a real support level
                if strike <= spot_price - min_wall_distance and put_gex_strike > max_put_gex:
                    max_put_gex = put_gex_strike
                    put_wall = strike

            # If no meaningful walls found, use a wider search (1% minimum OI threshold)
            # This handles cases where GEX is too concentrated at ATM
            if call_wall is None or put_wall is None:
                # Sort strikes by OI for fallback
                for strike, data in sorted(strikes_gex.items(), key=lambda x: x[1]['call_oi'], reverse=True):
                    if call_wall is None and strike > spot_price and data['call_oi'] > 1000:
                        call_wall = strike
                        break

                for strike, data in sorted(strikes_gex.items(), key=lambda x: x[1]['put_oi'], reverse=True):
                    if put_wall is None and strike < spot_price and data['put_oi'] > 1000:
                        put_wall = strike
                        break

            # Final fallback - use spot price if still no walls (shouldn't happen with good data)
            if call_wall is None:
                call_wall = spot_price * 1.01  # 1% above spot
            if put_wall is None:
                put_wall = spot_price * 0.99  # 1% below spot

            # Net GEX
            net_gex = total_call_gex - total_put_gex

            # Find flip point (where GEX crosses zero)
            flip_point = self._find_flip_point(strikes_gex, spot_price)

            # Normalized GEX (scale-independent)
            gex_normalized = net_gex / (spot_price ** 2) if spot_price > 0 else 0

            # GEX regime
            if net_gex > self.POSITIVE_THRESHOLD:
                gex_regime = 'POSITIVE'
            elif net_gex < self.NEGATIVE_THRESHOLD:
                gex_regime = 'NEGATIVE'
            else:
                gex_regime = 'NEUTRAL'

            # Distance to flip as percentage
            distance_to_flip_pct = (spot_price - flip_point) / spot_price * 100 if spot_price > 0 else 0

            # Position relative to walls
            above_call_wall = spot_price > call_wall
            below_put_wall = spot_price < put_wall
            between_walls = put_wall <= spot_price <= call_wall

            # Prepare strikes data if requested
            strikes_data = []
            if include_strikes_data:
                for strike in sorted(strikes_gex.keys()):
                    strikes_data.append({
                        'strike': strike,
                        **strikes_gex[strike]
                    })

            return GEXData(
                trade_date=trade_date,
                symbol=self.ticker,
                spot_price=spot_price,
                net_gex=net_gex,
                call_gex=total_call_gex,
                put_gex=-total_put_gex,
                call_wall=call_wall,
                put_wall=put_wall,
                flip_point=flip_point,
                gex_normalized=gex_normalized,
                gex_regime=gex_regime,
                distance_to_flip_pct=distance_to_flip_pct,
                above_call_wall=above_call_wall,
                below_put_wall=below_put_wall,
                between_walls=between_walls,
                strikes_data=strikes_data
            )

        except Exception as e:
            logger.error(f"Error calculating GEX for {trade_date}: {e}")
            return None

    def _find_flip_point(self, strikes_gex: Dict, spot_price: float) -> float:
        """
        Find the strike where net GEX crosses from negative to positive.
        Uses linear interpolation between strikes.
        """
        if not strikes_gex:
            return spot_price

        sorted_strikes = sorted(strikes_gex.keys())

        prev_strike = None
        prev_net = None

        for strike in sorted_strikes:
            net = strikes_gex[strike]['net_gex']

            if prev_net is not None:
                # Check for sign change
                if (prev_net < 0 and net >= 0) or (prev_net <= 0 and net > 0):
                    # Linear interpolation
                    if net != prev_net:
                        flip = prev_strike + (strike - prev_strike) * (-prev_net) / (net - prev_net)
                        return flip
                    else:
                        return strike

            prev_strike = strike
            prev_net = net

        # No zero crossing found - return based on overall GEX
        total_net = sum(s['net_gex'] for s in strikes_gex.values())
        if total_net > 0:
            return min(sorted_strikes)  # Positive GEX, flip below range
        else:
            return max(sorted_strikes)  # Negative GEX, flip above range

    def calculate_gex_time_series(
        self,
        start_date: str,
        end_date: str,
        dte_max: int = 7
    ) -> GEXTimeSeries:
        """
        Calculate GEX for a date range.

        Args:
            start_date: Start date YYYY-MM-DD
            end_date: End date YYYY-MM-DD
            dte_max: Max DTE to include

        Returns:
            GEXTimeSeries with all daily GEX data
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Get all trading dates in range
            cursor.execute("""
                SELECT DISTINCT trade_date
                FROM orat_options_eod
                WHERE ticker = %s
                  AND trade_date >= %s
                  AND trade_date <= %s
                ORDER BY trade_date
            """, (self.ticker, start_date, end_date))

            dates = [row[0].strftime('%Y-%m-%d') for row in cursor.fetchall()]
            conn.close()

            logger.info(f"Calculating GEX for {len(dates)} trading days")

            # Calculate GEX for each date
            data = []
            for i, trade_date in enumerate(dates):
                gex = self.calculate_gex_for_date(trade_date, dte_max)
                if gex:
                    data.append(gex)

                if (i + 1) % 100 == 0:
                    logger.info(f"  Processed {i + 1}/{len(dates)} dates")

            logger.info(f"Calculated GEX for {len(data)}/{len(dates)} dates")

            return GEXTimeSeries(
                symbol=self.ticker,
                start_date=start_date,
                end_date=end_date,
                data=data
            )

        except Exception as e:
            logger.error(f"Error calculating GEX time series: {e}")
            return GEXTimeSeries(
                symbol=self.ticker,
                start_date=start_date,
                end_date=end_date,
                data=[]
            )

    def enrich_backtest_with_gex(
        self,
        backtest_results: Dict[str, Any],
        dte_max: int = 7
    ) -> Dict[str, Any]:
        """
        Add GEX data to existing KRONOS backtest results.

        This enables using GEX as an ML feature alongside other trade data.

        Args:
            backtest_results: Results from HybridFixedBacktester.run()
            dte_max: Max DTE for GEX calculation

        Returns:
            backtest_results with GEX data added to each trade
        """
        trades = backtest_results.get('all_trades', [])
        if not trades:
            logger.warning("No trades to enrich with GEX")
            return backtest_results

        logger.info(f"Enriching {len(trades)} trades with GEX data")

        # Cache GEX by date to avoid recalculating
        gex_cache = {}
        enriched_count = 0

        for trade in trades:
            trade_date = trade.get('trade_date')
            if not trade_date:
                continue

            # Get or calculate GEX for this date
            if trade_date not in gex_cache:
                gex_cache[trade_date] = self.calculate_gex_for_date(trade_date, dte_max)

            gex = gex_cache[trade_date]

            if gex:
                # Add GEX fields to trade
                trade['gex_net'] = gex.net_gex
                trade['gex_normalized'] = gex.gex_normalized
                trade['gex_regime'] = gex.gex_regime
                trade['gex_flip_point'] = gex.flip_point
                trade['gex_call_wall'] = gex.call_wall
                trade['gex_put_wall'] = gex.put_wall
                trade['gex_distance_to_flip_pct'] = gex.distance_to_flip_pct
                trade['gex_between_walls'] = gex.between_walls
                enriched_count += 1
            else:
                # No GEX data - set defaults
                trade['gex_net'] = 0
                trade['gex_normalized'] = 0
                trade['gex_regime'] = 'UNKNOWN'
                trade['gex_flip_point'] = trade.get('open_price', 0)
                trade['gex_call_wall'] = trade.get('open_price', 0)
                trade['gex_put_wall'] = trade.get('open_price', 0)
                trade['gex_distance_to_flip_pct'] = 0
                trade['gex_between_walls'] = True

        logger.info(f"Enriched {enriched_count}/{len(trades)} trades with GEX data")

        # Add GEX summary to results
        if enriched_count > 0:
            gex_values = [t['gex_net'] for t in trades if t.get('gex_net', 0) != 0]
            backtest_results['gex_summary'] = {
                'trades_with_gex': enriched_count,
                'avg_net_gex': sum(gex_values) / len(gex_values) if gex_values else 0,
                'pct_positive_gex': sum(1 for g in gex_values if g > 0) / len(gex_values) * 100 if gex_values else 0,
                'pct_negative_gex': sum(1 for g in gex_values if g < 0) / len(gex_values) * 100 if gex_values else 0,
            }

        return backtest_results

    def store_gex_to_database(self, gex: GEXData) -> bool:
        """
        Store calculated GEX data to gex_daily table for ML training.

        This ensures GEX data is persisted and can be used for:
        - ML model training
        - Historical analysis
        - Cross-referencing with trade outcomes

        Args:
            gex: GEXData object to store

        Returns:
            True if stored successfully, False otherwise
        """
        if not gex:
            return False

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gex_daily (
                    id SERIAL PRIMARY KEY,
                    trade_date DATE NOT NULL,
                    symbol VARCHAR(10) NOT NULL DEFAULT 'SPX',
                    spot_price FLOAT NOT NULL,
                    net_gex FLOAT NOT NULL,
                    call_gex FLOAT,
                    put_gex FLOAT,
                    call_wall FLOAT,
                    put_wall FLOAT,
                    flip_point FLOAT,
                    gex_normalized FLOAT,
                    gex_regime VARCHAR(10),
                    distance_to_flip_pct FLOAT,
                    above_call_wall BOOLEAN,
                    below_put_wall BOOLEAN,
                    between_walls BOOLEAN,
                    dte_max_used INTEGER DEFAULT 7,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_gex_daily UNIQUE (trade_date, symbol)
                )
            """)

            # Insert or update
            cursor.execute("""
                INSERT INTO gex_daily (
                    trade_date, symbol, spot_price, net_gex, call_gex, put_gex,
                    call_wall, put_wall, flip_point, gex_normalized, gex_regime,
                    distance_to_flip_pct, above_call_wall, below_put_wall, between_walls
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_date, symbol) DO UPDATE SET
                    spot_price = EXCLUDED.spot_price,
                    net_gex = EXCLUDED.net_gex,
                    call_gex = EXCLUDED.call_gex,
                    put_gex = EXCLUDED.put_gex,
                    call_wall = EXCLUDED.call_wall,
                    put_wall = EXCLUDED.put_wall,
                    flip_point = EXCLUDED.flip_point,
                    gex_normalized = EXCLUDED.gex_normalized,
                    gex_regime = EXCLUDED.gex_regime,
                    distance_to_flip_pct = EXCLUDED.distance_to_flip_pct
            """, (
                gex.trade_date,
                gex.symbol,
                gex.spot_price,
                gex.net_gex,
                gex.call_gex,
                gex.put_gex,
                gex.call_wall,
                gex.put_wall,
                gex.flip_point,
                gex.gex_normalized,
                gex.gex_regime,
                gex.distance_to_flip_pct,
                gex.above_call_wall,
                gex.below_put_wall,
                gex.between_walls
            ))

            conn.commit()
            conn.close()
            logger.info(f"Stored GEX data for {gex.trade_date} to database")
            return True

        except Exception as e:
            logger.error(f"Failed to store GEX data: {e}")
            return False

    def calculate_and_store_gex(self, trade_date: str, dte_max: int = 7) -> Optional[GEXData]:
        """
        Calculate GEX for a date and store it to database.

        This combines calculation and storage for convenience.

        Args:
            trade_date: Date to calculate GEX for
            dte_max: Max DTE to include

        Returns:
            GEXData if successful, None otherwise
        """
        gex = self.calculate_gex_for_date(trade_date, dte_max)
        if gex:
            self.store_gex_to_database(gex)
        return gex


def get_gex_for_date(trade_date: str, ticker: str = "SPX") -> Optional[GEXData]:
    """
    Convenience function to get GEX for a specific date.

    Example:
        gex = get_gex_for_date('2024-01-15')
        print(f"Net GEX: {gex.net_gex:,.0f}")
        print(f"Regime: {gex.gex_regime}")
    """
    calc = KronosGEXCalculator(ticker)
    return calc.calculate_gex_for_date(trade_date)


def enrich_trades_with_gex(backtest_results: Dict[str, Any], ticker: str = "SPX") -> Dict[str, Any]:
    """
    Convenience function to add GEX to backtest results.

    Example:
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester
        from quant.kronos_gex_calculator import enrich_trades_with_gex

        backtester = HybridFixedBacktester(start_date='2024-01-01')
        results = backtester.run()
        results = enrich_trades_with_gex(results)

        # Now each trade has gex_net, gex_regime, etc.
    """
    calc = KronosGEXCalculator(ticker)
    return calc.enrich_backtest_with_gex(backtest_results)


if __name__ == "__main__":
    # Demo usage
    import argparse

    parser = argparse.ArgumentParser(description='Calculate GEX from ORAT data')
    parser.add_argument('--date', type=str, help='Single date to calculate')
    parser.add_argument('--start', type=str, help='Start date for time series')
    parser.add_argument('--end', type=str, help='End date for time series')
    parser.add_argument('--ticker', type=str, default='SPX', help='Ticker symbol')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    calc = KronosGEXCalculator(args.ticker)

    if args.date:
        print(f"\nCalculating GEX for {args.date}...")
        gex = calc.calculate_gex_for_date(args.date, include_strikes_data=True)

        if gex:
            print(f"\n{'='*60}")
            print(f"GEX Results for {gex.trade_date}")
            print(f"{'='*60}")
            print(f"Spot Price:      ${gex.spot_price:,.2f}")
            print(f"Net GEX:         ${gex.net_gex:,.0f}")
            print(f"  Call GEX:      ${gex.call_gex:,.0f}")
            print(f"  Put GEX:       ${gex.put_gex:,.0f}")
            print(f"GEX Regime:      {gex.gex_regime}")
            print(f"Flip Point:      ${gex.flip_point:,.2f}")
            print(f"Call Wall:       ${gex.call_wall:,.2f}")
            print(f"Put Wall:        ${gex.put_wall:,.2f}")
            print(f"Distance to Flip: {gex.distance_to_flip_pct:+.2f}%")
            print(f"Between Walls:   {gex.between_walls}")
        else:
            print("No data available")

    elif args.start and args.end:
        print(f"\nCalculating GEX time series from {args.start} to {args.end}...")
        ts = calc.calculate_gex_time_series(args.start, args.end)

        print(f"\n{'='*60}")
        print(f"GEX Time Series Summary")
        print(f"{'='*60}")
        print(f"Period:          {ts.start_date} to {ts.end_date}")
        print(f"Data Points:     {len(ts.data)}")
        print(f"Avg Net GEX:     ${ts.avg_net_gex:,.0f}")
        print(f"% Positive GEX:  {ts.pct_positive_gex:.1f}%")
        print(f"% Negative GEX:  {ts.pct_negative_gex:.1f}%")

    else:
        print("Usage:")
        print("  Single date:   python kronos_gex_calculator.py --date 2024-01-15")
        print("  Time series:   python kronos_gex_calculator.py --start 2024-01-01 --end 2024-12-01")
