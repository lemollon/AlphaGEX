"""
Example: Integrating Flexible Data Sources into backend/main.py

This shows how to replace yfinance calls with the flexible data fetcher.

BEFORE: Fragile, breaks when Yahoo changes API
AFTER: Resilient, automatically tries 4 different sources
"""

# ============================================================================
# EXAMPLE 1: Simple Replacement
# ============================================================================

# BEFORE (backend/main.py line ~306):
import yfinance as yf

try:
    ticker = yf.Ticker(symbol)
    df_1d = ticker.history(period="90d", interval="1d")
    rsi_1d = calculate_rsi(df_1d)
    if rsi_1d is not None:
        rsi_data['1d'] = round(float(rsi_1d), 1)
except:
    rsi_data['1d'] = None


# AFTER:
from flexible_price_data import get_price_history

try:
    df_1d = get_price_history(symbol, period="90d", interval="1d")
    if df_1d is not None and not df_1d.empty:
        rsi_1d = calculate_rsi(df_1d)
        if rsi_1d is not None:
            rsi_data['1d'] = round(float(rsi_1d), 1)
    else:
        rsi_data['1d'] = None
except Exception as e:
    print(f"❌ RSI 1d calculation failed: {type(e).__name__}: {e}")
    rsi_data['1d'] = None


# ============================================================================
# EXAMPLE 2: VIX Fetching (backend/main.py line ~403)
# ============================================================================

# BEFORE:
try:
    vix_ticker = yf.Ticker('VIX')
    vix_data = vix_ticker.history(period="1d")
    if not vix_data.empty:
        vix_level = vix_data['Close'].iloc[-1]
except:
    pass


# AFTER:
from flexible_price_data import get_price_history

try:
    vix_data = get_price_history('VIX', period="1d")
    if vix_data is not None and not vix_data.empty:
        vix_level = float(vix_data['Close'].iloc[-1])
    else:
        print("⚠️ Could not fetch VIX, using default")
        vix_level = 18.0
except Exception as e:
    print(f"⚠️ VIX fetch error: {e}")
    vix_level = 18.0


# ============================================================================
# EXAMPLE 3: Add Health Check Endpoint
# ============================================================================

# Add to backend/main.py:

from flexible_price_data import get_health_status

@app.get("/api/data-sources/health")
async def check_data_source_health():
    """
    Check health status of all data sources

    Returns health metrics for:
    - yfinance (Yahoo Finance)
    - alpha_vantage
    - polygon
    - twelve_data
    - cache statistics
    """
    try:
        health = get_health_status()

        # Calculate overall health score
        sources = health.get('sources', {})
        if not sources:
            overall_health = 'unknown'
            healthy_sources = 0
        else:
            total_sources = len(sources)
            healthy_sources = sum(
                1 for s in sources.values()
                if s.get('consecutive_failures', 99) < 3
            )

            if healthy_sources == 0:
                overall_health = 'critical'
            elif healthy_sources < total_sources / 2:
                overall_health = 'degraded'
            else:
                overall_health = 'healthy'

        return {
            "success": True,
            "overall_health": overall_health,
            "healthy_sources": healthy_sources,
            "total_sources": len(sources),
            "data": health
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "overall_health": "unknown"
        }


# ============================================================================
# EXAMPLE 4: Price History Endpoint (with cache optimization)
# ============================================================================

# Replace /api/price-history/{symbol} endpoint in backend/main.py:

from flexible_price_data import get_price_history

@app.get("/api/price-history/{symbol}")
async def get_price_history_endpoint(
    symbol: str,
    period: str = "1mo",
    interval: str = "1d"
):
    """
    Get historical price data using flexible multi-source fetcher

    Automatically tries:
    1. yfinance (Yahoo Finance)
    2. Alpha Vantage (if yfinance fails)
    3. Polygon.io (if Alpha Vantage fails)
    4. Twelve Data (if Polygon fails)

    Uses 1-hour cache to reduce API calls
    """
    try:
        data = get_price_history(symbol, period=period, interval=interval)

        if data is None or data.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No price data available for {symbol}"
            )

        # Convert to JSON-friendly format
        records = []
        for idx, row in data.iterrows():
            records.append({
                'date': idx.isoformat(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume'])
            })

        return {
            "success": True,
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "count": len(records),
            "data": records
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching price history for {symbol}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch price data: {str(e)}"
        )


# ============================================================================
# EXAMPLE 5: Batch Price Data (for scanner)
# ============================================================================

from flexible_price_data import price_data_fetcher
from concurrent.futures import ThreadPoolExecutor, as_completed

@app.post("/api/scanner/batch-prices")
async def get_batch_prices(request: dict):
    """
    Fetch prices for multiple symbols efficiently

    Uses:
    - Parallel fetching (ThreadPoolExecutor)
    - Shared cache across all symbols
    - Automatic fallback per symbol
    """
    symbols = request.get('symbols', [])
    period = request.get('period', '5d')

    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols provided")

    results = {}
    errors = {}

    # Fetch in parallel (max 10 concurrent)
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_symbol = {
            executor.submit(get_price_history, symbol, period): symbol
            for symbol in symbols
        }

        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                data = future.result(timeout=10)
                if data is not None and not data.empty:
                    results[symbol] = {
                        'latest_close': float(data['Close'].iloc[-1]),
                        'latest_volume': int(data['Volume'].iloc[-1]),
                        'count': len(data)
                    }
                else:
                    errors[symbol] = "No data available"
            except Exception as e:
                errors[symbol] = str(e)

    return {
        "success": True,
        "requested": len(symbols),
        "successful": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors if errors else None
    }


# ============================================================================
# EXAMPLE 6: Startup Health Check
# ============================================================================

# Add to backend startup in main.py:

from flexible_price_data import get_price_history

@app.on_event("startup")
async def startup_check_data_sources():
    """Check data sources on startup"""
    print("\n" + "=" * 80)
    print("Checking Data Source Health...")
    print("=" * 80)

    # Test with SPY
    test_symbol = "SPY"
    try:
        data = get_price_history(test_symbol, period="5d")
        if data is not None and not data.empty:
            latest_close = data['Close'].iloc[-1]
            print(f"✅ Data sources working! {test_symbol} latest: ${latest_close:.2f}")
        else:
            print("⚠️ Warning: Could not fetch price data")
            print("   Application will work but price features may be limited")
    except Exception as e:
        print(f"⚠️ Warning: Data source check failed: {e}")
        print("   Application will start but price features may be limited")

    # Show health status
    health = get_health_status()
    sources = health.get('sources', {})
    if sources:
        print("\nData Source Status:")
        for source, stats in sources.items():
            total = stats['success_count'] + stats['failure_count']
            if total > 0:
                success_rate = (stats['success_count'] / total) * 100
                status = "✅" if success_rate > 50 else "⚠️"
                print(f"  {status} {source}: {success_rate:.0f}% success")

    print("=" * 80 + "\n")


# ============================================================================
# DEPLOYMENT CHECKLIST
# ============================================================================

"""
1. Add flexible_price_data.py to your project
2. Sign up for free API keys:
   - Alpha Vantage: https://www.alphavantage.co/support/#api-key
   - Polygon: https://polygon.io/dashboard/signup
   - Twelve Data: https://twelvedata.com/account/api-key

3. Add to Render environment variables:
   ALPHA_VANTAGE_API_KEY=your_key
   POLYGON_API_KEY=your_key
   TWELVE_DATA_API_KEY=your_key

4. Update backend/main.py:
   - Replace yfinance imports with flexible_price_data
   - Add health check endpoint
   - Add startup check

5. Deploy and test:
   curl https://your-api.onrender.com/api/data-sources/health

6. Monitor health dashboard regularly
"""


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("Run this in your backend to test:")
    print()
    print("from flexible_price_data import get_price_history, get_health_status")
    print()
    print("# Test data fetch")
    print("data = get_price_history('SPY', period='5d')")
    print("print(data)")
    print()
    print("# Check health")
    print("health = get_health_status()")
    print("print(health)")
