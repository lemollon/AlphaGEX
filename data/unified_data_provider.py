"""
Unified Data Provider - Single source for all market data

Priority order:
1. Tradier - Live quotes, options chains, Greeks (PRIMARY)
2. Trading Volatility - GEX, gamma exposure, flip points
3. Polygon - Historical data fallback only

This replaces scattered Polygon usage across the app.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Import data sources
TRADIER_AVAILABLE = False
POLYGON_AVAILABLE = False
TRADING_VOL_AVAILABLE = False

try:
    from data.tradier_data_fetcher import TradierDataFetcher, OptionContract, OptionChain
    TRADIER_AVAILABLE = True
except ImportError:
    logger.warning("Tradier not available - install tradier_data_fetcher")
    # Define fallback types for type hints
    OptionContract = None
    OptionChain = None

try:
    from data.polygon_data_fetcher import PolygonDataFetcher as PolygonHelper
    POLYGON_AVAILABLE = True
except ImportError:
    logger.warning("Polygon not available - some historical features may be limited")

try:
    from core_classes_and_engines import TradingVolatilityAPI
    TRADING_VOL_AVAILABLE = True
except ImportError:
    logger.warning("Trading Volatility API not available - GEX data will be unavailable")


@dataclass
class Quote:
    """Unified quote structure"""
    symbol: str
    price: float
    bid: float
    ask: float
    volume: int
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "unknown"


@dataclass
class HistoricalBar:
    """Single OHLCV bar"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class GEXData:
    """Gamma exposure data"""
    symbol: str
    net_gex: float
    flip_point: float
    call_gex: float
    put_gex: float
    timestamp: datetime = field(default_factory=datetime.now)


class UnifiedDataProvider:
    """
    Single interface for all market data needs.

    Usage:
        provider = UnifiedDataProvider()

        # Get live quote
        quote = provider.get_quote('SPY')

        # Get options chain with Greeks
        chain = provider.get_options_chain('SPY')

        # Get GEX data
        gex = provider.get_gex('SPY')

        # Get historical bars
        bars = provider.get_historical_bars('SPY', days=30)
    """

    def __init__(self):
        self._tradier = None
        self._polygon = None
        self._trading_vol = None

        # Initialize available sources
        if TRADIER_AVAILABLE:
            try:
                self._tradier = TradierDataFetcher()
                logger.info(f"Tradier initialized - Mode: {'SANDBOX' if self._tradier.sandbox else 'LIVE'}")
            except Exception as e:
                logger.warning(f"Failed to initialize Tradier: {e}")

        if POLYGON_AVAILABLE:
            try:
                self._polygon = PolygonHelper()
                logger.info("Polygon initialized (historical fallback)")
            except Exception as e:
                logger.warning(f"Failed to initialize Polygon: {e}")

        if TRADING_VOL_AVAILABLE:
            try:
                self._trading_vol = TradingVolatilityAPI()
                logger.info("Trading Volatility API initialized (GEX data)")
            except Exception as e:
                logger.warning(f"Failed to initialize Trading Volatility: {e}")

        # Log data source status
        self._log_status()

    def _log_status(self):
        """Log which data sources are available"""
        status = []
        if self._tradier:
            status.append("Tradier (live)")
        if self._polygon:
            status.append("Polygon (historical)")
        if self._trading_vol:
            status.append("TradingVol (GEX)")

        if status:
            logger.info(f"Data sources available: {', '.join(status)}")
        else:
            logger.error("NO DATA SOURCES AVAILABLE!")

    # ==================== QUOTES ====================

    def get_quote(self, symbol: str) -> Optional[Quote]:
        """
        Get real-time quote for symbol.

        Priority: Tradier > Polygon
        """
        # Try Tradier first (preferred - real-time)
        if self._tradier:
            try:
                data = self._tradier.get_quote(symbol)
                if data:
                    return Quote(
                        symbol=symbol,
                        price=float(data.get('last', 0) or data.get('close', 0)),
                        bid=float(data.get('bid', 0) or 0),
                        ask=float(data.get('ask', 0) or 0),
                        volume=int(data.get('volume', 0) or 0),
                        timestamp=datetime.now(),
                        source='tradier'
                    )
            except Exception as e:
                logger.warning(f"Tradier quote failed for {symbol}: {e}")

        # Fallback to Polygon
        if self._polygon:
            try:
                data = self._polygon.get_latest_price(symbol)
                if data:
                    return Quote(
                        symbol=symbol,
                        price=float(data.get('close', 0) or data.get('price', 0)),
                        bid=float(data.get('bid', 0) or 0),
                        ask=float(data.get('ask', 0) or 0),
                        volume=int(data.get('volume', 0) or 0),
                        timestamp=datetime.now(),
                        source='polygon'
                    )
            except Exception as e:
                logger.warning(f"Polygon quote failed for {symbol}: {e}")

        logger.error(f"No quote available for {symbol}")
        return None

    def get_price(self, symbol: str) -> float:
        """Simple price getter - returns 0 if unavailable"""
        quote = self.get_quote(symbol)
        return quote.price if quote else 0.0

    # ==================== OPTIONS ====================

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[str] = None,
        greeks: bool = True
    ) -> Optional[OptionChain]:
        """
        Get options chain with Greeks.

        Tradier ONLY - Polygon doesn't provide Greeks.
        """
        if not self._tradier:
            logger.error("Tradier required for options chains - not available")
            return None

        try:
            return self._tradier.get_option_chain(symbol, expiration, greeks)
        except Exception as e:
            logger.error(f"Failed to get options chain for {symbol}: {e}")
            return None

    def get_option_expirations(self, symbol: str) -> List[str]:
        """Get available expiration dates"""
        if not self._tradier:
            return []

        try:
            return self._tradier.get_option_expirations(symbol)
        except Exception as e:
            logger.error(f"Failed to get expirations for {symbol}: {e}")
            return []

    def get_atm_option(
        self,
        symbol: str,
        expiration: Optional[str] = None,
        option_type: str = 'call'
    ) -> Optional[OptionContract]:
        """Get at-the-money option"""
        if not self._tradier:
            return None

        try:
            return self._tradier.find_atm_options(symbol, expiration, option_type)
        except Exception as e:
            logger.error(f"Failed to find ATM option for {symbol}: {e}")
            return None

    def get_delta_option(
        self,
        symbol: str,
        target_delta: float,
        expiration: Optional[str] = None,
        option_type: str = 'call'
    ) -> Optional[OptionContract]:
        """Find option closest to target delta"""
        if not self._tradier:
            return None

        try:
            return self._tradier.find_delta_option(symbol, target_delta, expiration, option_type)
        except Exception as e:
            logger.error(f"Failed to find delta option for {symbol}: {e}")
            return None

    def get_option_greeks(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        option_type: str
    ) -> Dict[str, float]:
        """
        Get Greeks for specific option.

        Returns dict with delta, gamma, theta, vega, iv
        """
        chain = self.get_options_chain(symbol, expiration, greeks=True)
        if not chain or expiration not in chain.chains:
            return {}

        for contract in chain.chains[expiration]:
            if contract.strike == strike and contract.option_type == option_type:
                return {
                    'delta': contract.delta,
                    'gamma': contract.gamma,
                    'theta': contract.theta,
                    'vega': contract.vega,
                    'iv': contract.implied_volatility
                }

        return {}

    # ==================== GEX DATA ====================

    def get_gex(self, symbol: str) -> Optional[GEXData]:
        """
        Get gamma exposure data.

        Trading Volatility API ONLY.
        """
        if not self._trading_vol:
            logger.warning("Trading Volatility API not available for GEX data")
            return None

        try:
            data = self._trading_vol.get_net_gamma(symbol)
            if data:
                return GEXData(
                    symbol=symbol,
                    net_gex=float(data.get('netGamma', 0) or data.get('net_gex', 0)),
                    flip_point=float(data.get('flipPoint', 0) or data.get('flip_point', 0)),
                    call_gex=float(data.get('callGamma', 0) or data.get('call_gex', 0)),
                    put_gex=float(data.get('putGamma', 0) or data.get('put_gex', 0)),
                    timestamp=datetime.now()
                )
        except Exception as e:
            logger.error(f"Failed to get GEX for {symbol}: {e}")

        return None

    def get_net_gex(self, symbol: str) -> float:
        """Simple net GEX getter"""
        gex = self.get_gex(symbol)
        return gex.net_gex if gex else 0.0

    def get_flip_point(self, symbol: str) -> float:
        """Get gamma flip point"""
        gex = self.get_gex(symbol)
        return gex.flip_point if gex else 0.0

    # ==================== HISTORICAL DATA ====================

    def get_historical_bars(
        self,
        symbol: str,
        days: int = 30,
        interval: str = 'day'
    ) -> List[HistoricalBar]:
        """
        Get historical OHLCV bars.

        Priority: Tradier > Polygon

        Args:
            symbol: Stock symbol
            days: Number of days of history
            interval: 'day', '1min', '5min', '15min'
        """
        bars = []

        # Try Tradier first
        if self._tradier:
            try:
                bars = self._get_tradier_history(symbol, days, interval)
                if bars:
                    return bars
            except Exception as e:
                logger.warning(f"Tradier history failed for {symbol}: {e}")

        # Fallback to Polygon
        if self._polygon:
            try:
                bars = self._get_polygon_history(symbol, days, interval)
                if bars:
                    return bars
            except Exception as e:
                logger.warning(f"Polygon history failed for {symbol}: {e}")

        return bars

    def _get_tradier_history(
        self,
        symbol: str,
        days: int,
        interval: str
    ) -> List[HistoricalBar]:
        """Get history from Tradier"""
        # Tradier uses different endpoint for historical data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        params = {
            'symbol': symbol,
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d')
        }

        if interval == 'day':
            params['interval'] = 'daily'
        elif interval in ['1min', '5min', '15min']:
            params['interval'] = interval

        response = self._tradier._make_request('GET', 'markets/history', params=params)
        history = response.get('history', {})

        if not history or history == 'null':
            return []

        day_data = history.get('day', [])
        if isinstance(day_data, dict):
            day_data = [day_data]

        bars = []
        for bar in day_data:
            bars.append(HistoricalBar(
                timestamp=datetime.strptime(bar['date'], '%Y-%m-%d'),
                open=float(bar.get('open', 0)),
                high=float(bar.get('high', 0)),
                low=float(bar.get('low', 0)),
                close=float(bar.get('close', 0)),
                volume=int(bar.get('volume', 0))
            ))

        return bars

    def _get_polygon_history(
        self,
        symbol: str,
        days: int,
        interval: str
    ) -> List[HistoricalBar]:
        """Get history from Polygon"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Map interval to Polygon format
        timespan = 'day'
        multiplier = 1
        if interval == '1min':
            timespan = 'minute'
        elif interval == '5min':
            timespan = 'minute'
            multiplier = 5
        elif interval == '15min':
            timespan = 'minute'
            multiplier = 15

        data = self._polygon.get_historical_bars(
            symbol,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d'),
            timespan=timespan,
            multiplier=multiplier
        )

        bars = []
        for bar in (data or []):
            bars.append(HistoricalBar(
                timestamp=datetime.fromtimestamp(bar['t'] / 1000) if 't' in bar else datetime.now(),
                open=float(bar.get('o', 0)),
                high=float(bar.get('h', 0)),
                low=float(bar.get('l', 0)),
                close=float(bar.get('c', 0)),
                volume=int(bar.get('v', 0))
            ))

        return bars

    # ==================== PRICE HISTORY ALIAS ====================

    def get_price_history(
        self,
        symbol: str,
        days: int = 30,
        interval: str = 'day',
        timeframe: str = None
    ) -> List[HistoricalBar]:
        """
        Alias for get_historical_bars() for backwards compatibility.

        Args:
            symbol: Stock symbol
            days: Number of days of history
            interval: 'day', '1min', '5min', '15min'
            timeframe: Alternative name for interval (for compatibility)

        Returns:
            List of HistoricalBar objects
        """
        # Use timeframe as alias for interval if provided
        if timeframe and not interval:
            interval = timeframe
        return self.get_historical_bars(symbol, days, interval)

    # ==================== VIX ====================

    def get_vix(self) -> float:
        """Get current VIX value from Tradier, Yahoo Finance, or Polygon"""
        # Try multiple VIX symbol formats for Tradier
        if self._tradier:
            vix_symbols = ['VIX', '$VIX.X', 'VIXW', '$VIX']
            for symbol in vix_symbols:
                try:
                    data = self._tradier.get_quote(symbol)
                    if data:
                        price = float(data.get('last', 0) or data.get('close', 0) or 0)
                        if price > 0:
                            logger.info(f"VIX from Tradier ({symbol}): {price}")
                            return price
                except Exception as e:
                    continue

        # Try Yahoo Finance (FREE - no API key needed!)
        try:
            import yfinance as yf
            vix_ticker = yf.Ticker("^VIX")

            # Method 1: Try info dict (most reliable)
            try:
                info = vix_ticker.info
                price = info.get('regularMarketPrice') or info.get('previousClose') or info.get('open', 0)
                if price and price > 0:
                    logger.info(f"VIX from Yahoo Finance (info): {price}")
                    return float(price)
            except Exception:
                pass

            # Method 2: Get from history (always works)
            hist = vix_ticker.history(period='5d')
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
                if price > 0:
                    logger.info(f"VIX from Yahoo Finance (history): {price}")
                    return price
        except ImportError:
            logger.debug("yfinance not installed")
        except Exception as e:
            logger.debug(f"Yahoo Finance VIX fetch failed: {e}")

        # Fallback to Polygon (requires API key)
        if self._polygon:
            try:
                price = self._polygon.get_current_price('I:VIX')
                if price and price > 0:
                    logger.info(f"VIX from Polygon: {price}")
                    return price
            except Exception as e:
                logger.debug(f"Polygon VIX fetch failed: {e}")

        logger.warning("VIX unavailable from all sources")
        return 0.0

    # ==================== ACCOUNT (Tradier only) ====================

    def get_account_balance(self) -> Dict:
        """Get trading account balance"""
        if not self._tradier:
            return {'error': 'Tradier not available'}

        try:
            return self._tradier.get_account_balance()
        except Exception as e:
            return {'error': str(e)}

    def get_positions(self) -> List:
        """Get current positions"""
        if not self._tradier:
            return []

        try:
            return self._tradier.get_positions()
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    # ==================== EXECUTION (Tradier only) ====================

    def buy_call(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """Buy call option"""
        if not self._tradier:
            return {'error': 'Tradier not available for trading'}

        return self._tradier.buy_call(symbol, expiration, strike, quantity, limit_price)

    def buy_put(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """Buy put option"""
        if not self._tradier:
            return {'error': 'Tradier not available for trading'}

        return self._tradier.buy_put(symbol, expiration, strike, quantity, limit_price)

    def sell_call(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """Sell call option"""
        if not self._tradier:
            return {'error': 'Tradier not available for trading'}

        return self._tradier.sell_call(symbol, expiration, strike, quantity, limit_price)

    def sell_put(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """Sell put option"""
        if not self._tradier:
            return {'error': 'Tradier not available for trading'}

        return self._tradier.sell_put(symbol, expiration, strike, quantity, limit_price)

    def place_iron_condor(
        self,
        symbol: str,
        expiration: str,
        put_long: float,
        put_short: float,
        call_short: float,
        call_long: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """Place iron condor spread"""
        if not self._tradier:
            return {'error': 'Tradier not available for trading'}

        return self._tradier.place_iron_condor(
            symbol, expiration, put_long, put_short,
            call_short, call_long, quantity, limit_price
        )


# ==================== SINGLETON INSTANCE ====================

_provider_instance: Optional[UnifiedDataProvider] = None


def get_data_provider() -> UnifiedDataProvider:
    """Get singleton data provider instance"""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = UnifiedDataProvider()
    return _provider_instance


# ==================== CONVENIENCE FUNCTIONS ====================

def get_quote(symbol: str) -> Optional[Quote]:
    """Quick quote lookup"""
    return get_data_provider().get_quote(symbol)


def get_price(symbol: str) -> float:
    """Quick price lookup"""
    return get_data_provider().get_price(symbol)


def get_options_chain(symbol: str, expiration: Optional[str] = None) -> Optional[OptionChain]:
    """Quick options chain lookup"""
    return get_data_provider().get_options_chain(symbol, expiration)


def get_gex(symbol: str) -> Optional[GEXData]:
    """Quick GEX lookup"""
    return get_data_provider().get_gex(symbol)


def get_vix() -> float:
    """Quick VIX lookup"""
    return get_data_provider().get_vix()


# ==================== TEST ====================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print("\n" + "=" * 50)
    print("UNIFIED DATA PROVIDER TEST")
    print("=" * 50)

    provider = get_data_provider()

    # Test quote
    print("\n1. SPY Quote:")
    quote = provider.get_quote('SPY')
    if quote:
        print(f"   Price: ${quote.price:.2f} | Source: {quote.source}")
    else:
        print("   FAILED")

    # Test options
    print("\n2. SPY Options Chain:")
    chain = provider.get_options_chain('SPY')
    if chain:
        print(f"   Underlying: ${chain.underlying_price:.2f}")
        print(f"   Expirations: {len(chain.chains)}")
    else:
        print("   FAILED (Tradier required)")

    # Test GEX
    print("\n3. SPY GEX Data:")
    gex = provider.get_gex('SPY')
    if gex:
        print(f"   Net GEX: ${gex.net_gex:,.0f}")
        print(f"   Flip Point: ${gex.flip_point:.2f}")
    else:
        print("   FAILED (Trading Volatility API required)")

    # Test historical
    print("\n4. SPY Historical (30 days):")
    bars = provider.get_historical_bars('SPY', days=30)
    if bars:
        print(f"   Got {len(bars)} bars")
        print(f"   Latest: {bars[-1].timestamp.date()} Close: ${bars[-1].close:.2f}")
    else:
        print("   FAILED")

    # Test VIX
    print("\n5. VIX:")
    vix = provider.get_vix()
    print(f"   VIX: {vix:.2f}")

    print("\n" + "=" * 50)
