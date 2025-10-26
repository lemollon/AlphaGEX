"""
Multi-Symbol Scanner with Smart Caching
Scans multiple symbols for trading opportunities while respecting API limits
"""

import streamlit as st
from typing import List, Dict
import pandas as pd
from datetime import datetime, timedelta
import time


class SmartCache:
    """Intelligent caching system to minimize API calls"""

    def __init__(self, cache_duration_minutes=5):
        """
        Initialize cache with configurable duration

        Args:
            cache_duration_minutes: How long to cache data before refresh
        """
        if 'symbol_cache' not in st.session_state:
            st.session_state.symbol_cache = {}
        if 'cache_timestamps' not in st.session_state:
            st.session_state.cache_timestamps = {}

        self.cache_duration = timedelta(minutes=cache_duration_minutes)

    def get(self, symbol: str) -> Dict:
        """Get cached data for symbol if still valid"""
        if symbol not in st.session_state.symbol_cache:
            return None

        timestamp = st.session_state.cache_timestamps.get(symbol)
        if not timestamp:
            return None

        # Check if cache is still valid
        if datetime.now() - timestamp < self.cache_duration:
            return st.session_state.symbol_cache[symbol]

        return None

    def set(self, symbol: str, data: Dict):
        """Cache data for symbol"""
        st.session_state.symbol_cache[symbol] = data
        st.session_state.cache_timestamps[symbol] = datetime.now()

    def get_cache_age(self, symbol: str) -> str:
        """Get human-readable cache age"""
        timestamp = st.session_state.cache_timestamps.get(symbol)
        if not timestamp:
            return "Never"

        age = datetime.now() - timestamp
        if age.seconds < 60:
            return f"{age.seconds}s ago"
        elif age.seconds < 3600:
            return f"{age.seconds // 60}m ago"
        else:
            return f"{age.seconds // 3600}h ago"

    def clear(self, symbol: str = None):
        """Clear cache for specific symbol or all symbols"""
        if symbol:
            st.session_state.symbol_cache.pop(symbol, None)
            st.session_state.cache_timestamps.pop(symbol, None)
        else:
            st.session_state.symbol_cache = {}
            st.session_state.cache_timestamps = {}


def scan_symbols(symbols: List[str], api_client, force_refresh: bool = False) -> pd.DataFrame:
    """
    Scan multiple symbols for trading opportunities

    Args:
        symbols: List of ticker symbols to scan
        api_client: Trading Volatility API client
        force_refresh: Bypass cache and fetch fresh data

    Returns:
        DataFrame with scan results
    """

    cache = SmartCache(cache_duration_minutes=5)
    results = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, symbol in enumerate(symbols):
        status_text.text(f"Scanning {symbol}... ({idx + 1}/{len(symbols)})")

        # Try to get from cache first
        cached_data = None if force_refresh else cache.get(symbol)

        if cached_data:
            # Use cached data
            scan_result = cached_data
            scan_result['cache_status'] = f"Cached ({cache.get_cache_age(symbol)})"
        else:
            # Fetch fresh data
            try:
                # ONLY fetch GEX data - skip skew_data to reduce API calls
                gex_data = api_client.get_net_gamma(symbol)

                # Import here to avoid circular dependency
                from visualization_and_plans import StrategyEngine

                strategy_engine = StrategyEngine()
                setups = strategy_engine.detect_setups(gex_data)

                # Get best setup (highest confidence)
                best_setup = max(setups, key=lambda x: x.get('confidence', 0)) if setups else None

                scan_result = {
                    'symbol': symbol,
                    'spot_price': gex_data.get('spot_price', 0),
                    'net_gex': gex_data.get('net_gex', 0) / 1e9,  # In billions
                    'flip_point': gex_data.get('flip_point', 0),
                    'distance_to_flip': ((gex_data.get('flip_point', 0) - gex_data.get('spot_price', 0)) /
                                         gex_data.get('spot_price', 1) * 100) if gex_data.get('spot_price') else 0,
                    'setup_type': best_setup.get('strategy', 'N/A') if best_setup else 'N/A',
                    'confidence': best_setup.get('confidence', 0) if best_setup else 0,
                    'action': best_setup.get('action', 'N/A') if best_setup else 'N/A',
                    'cache_status': 'Fresh',
                    'timestamp': datetime.now()
                }

                # Cache the result
                cache.set(symbol, scan_result)

                # NOTE: Removed redundant sleep here - the API client already handles
                # rate limiting with its built-in 15-second minimum interval and circuit breaker.
                # Double throttling was causing circuit breaker activation due to timing misalignment.

            except Exception as e:
                st.warning(f"⚠️ Error scanning {symbol}: {str(e)}")
                scan_result = {
                    'symbol': symbol,
                    'spot_price': 0,
                    'net_gex': 0,
                    'flip_point': 0,
                    'distance_to_flip': 0,
                    'setup_type': 'Error',
                    'confidence': 0,
                    'action': 'N/A',
                    'cache_status': f'Error',
                    'timestamp': datetime.now()
                }

        results.append(scan_result)
        progress_bar.progress((idx + 1) / len(symbols))

    status_text.empty()
    progress_bar.empty()

    # Convert to DataFrame
    df = pd.DataFrame(results)

    return df


def display_scanner_dashboard(df: pd.DataFrame):
    """Display interactive scanner dashboard"""

    if df.empty:
        st.info("👆 Add symbols to your watchlist and click Scan to begin")
        return

    st.subheader("📊 Multi-Symbol Scanner Results")

    # Ensure all required columns exist (IV and PCR removed to reduce API calls by 50%)
    required_columns = ['symbol', 'spot_price', 'net_gex', 'distance_to_flip',
                       'setup_type', 'confidence', 'action', 'cache_status']
    for col in required_columns:
        if col not in df.columns:
            df[col] = 0 if col not in ['symbol', 'setup_type', 'action', 'cache_status'] else 'N/A'

    # Sort by confidence (best opportunities first)
    df_sorted = df.sort_values('confidence', ascending=False)

    # Display formatted table (IV column removed - not essential for finding setups)
    display_df = df_sorted[[
        'symbol', 'spot_price', 'net_gex', 'distance_to_flip',
        'setup_type', 'confidence', 'action', 'cache_status'
    ]].copy()

    # Keep raw confidence values for styling
    confidence_values = display_df['confidence'].copy()

    # Rename columns (IV removed - not essential for finding trade setups)
    display_df.columns = [
        'Symbol', 'Price', 'Net GEX ($B)', 'Dist to Flip (%)',
        'Setup', 'Conf %', 'Action', 'Status'
    ]

    # Format numeric columns (safely handle non-numeric values)
    def safe_format_price(x):
        try:
            return f"${float(x):.2f}" if x != 'N/A' else 'N/A'
        except (ValueError, TypeError):
            return 'N/A'

    def safe_format_gex(x):
        try:
            return f"{float(x):.2f}B" if x != 'N/A' else 'N/A'
        except (ValueError, TypeError):
            return 'N/A'

    def safe_format_percent(x):
        try:
            return f"{float(x):+.1f}%" if x != 'N/A' else 'N/A'
        except (ValueError, TypeError):
            return 'N/A'

    def safe_format_conf(x):
        try:
            return f"{int(x)}%" if x != 'N/A' else 'N/A'
        except (ValueError, TypeError):
            return 'N/A'

    display_df['Price'] = display_df['Price'].apply(safe_format_price)
    display_df['Net GEX ($B)'] = display_df['Net GEX ($B)'].apply(safe_format_gex)
    display_df['Dist to Flip (%)'] = display_df['Dist to Flip (%)'].apply(safe_format_percent)
    display_df['Conf %'] = display_df['Conf %'].apply(safe_format_conf)

    # Color coding based on raw confidence values
    def highlight_confidence(row):
        idx = row.name
        try:
            conf = float(confidence_values.iloc[idx])
            if conf >= 70:
                return ['background-color: rgba(0, 255, 0, 0.2)'] * len(row)
            elif conf >= 60:
                return ['background-color: rgba(255, 255, 0, 0.1)'] * len(row)
            else:
                return ['background-color: rgba(255, 0, 0, 0.1)'] * len(row)
        except (ValueError, TypeError, IndexError):
            return [''] * len(row)

    st.dataframe(
        display_df.style.apply(highlight_confidence, axis=1),
        use_container_width=True,
        height=400
    )

    # Quick stats
    st.subheader("🎯 Best Opportunities")

    top_3 = df_sorted.head(3)

    cols = st.columns(3)
    # Use .iloc instead of .iterrows() for better performance
    for idx in range(len(top_3)):
        row = top_3.iloc[idx]
        with cols[idx]:
            st.metric(
                f"#{idx + 1}: {row['symbol']}",
                row['setup_type'],
                f"{row['confidence']}% confidence"
            )
            st.caption(f"💡 {row['action']}")

    # Legend
    with st.expander("🎨 Color Legend"):
        st.markdown("""
        - 🟢 **Green**: High confidence (70%+) - Strong setup
        - 🟡 **Yellow**: Medium confidence (60-69%) - Moderate setup
        - 🔴 **Red**: Low confidence (<60%) - Weak setup

        **Cache Status**:
        - **Fresh**: Just fetched from API
        - **Cached (Xm ago)**: Using cached data to save API calls
        - **Error**: Failed to fetch data
        """)


def display_watchlist_manager():
    """Watchlist management UI"""

    st.subheader("📋 Watchlist Manager")

    # API Protection: Max watchlist size
    MAX_WATCHLIST_SIZE = 20

    # Initialize watchlist in session state
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = ['SPY', 'QQQ', 'IWM', 'DIA', 'TSLA']

    # Add symbol
    col1, col2 = st.columns([3, 1])
    with col1:
        new_symbol = st.text_input(
            "Add Symbol",
            placeholder="Enter ticker (e.g., AAPL)",
            key="new_symbol_input"
        ).upper()
    with col2:
        if st.button("➕ Add", use_container_width=True):
            # Check watchlist size limit
            if len(st.session_state.watchlist) >= MAX_WATCHLIST_SIZE:
                st.error(f"❌ Watchlist limit reached ({MAX_WATCHLIST_SIZE} symbols max)")
                st.warning("💡 Remove symbols to add new ones. This limit protects against excessive API usage.")
            elif new_symbol and new_symbol not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_symbol)
                st.success(f"✅ Added {new_symbol}")
                st.rerun()
            elif new_symbol in st.session_state.watchlist:
                st.warning(f"⚠️ {new_symbol} already in watchlist")

    # Display current watchlist with limit indicator
    remaining = MAX_WATCHLIST_SIZE - len(st.session_state.watchlist)
    color = "🟢" if remaining > 5 else "🟡" if remaining > 0 else "🔴"
    st.write(f"**Current Watchlist** ({len(st.session_state.watchlist)}/{MAX_WATCHLIST_SIZE} symbols) {color}")

    # Show watchlist with remove buttons
    for symbol in st.session_state.watchlist:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.text(f"📊 {symbol}")
        with col2:
            if st.button("🗑️", key=f"remove_{symbol}", help=f"Remove {symbol}"):
                st.session_state.watchlist.remove(symbol)
                st.rerun()

    # Quick add popular symbols
    with st.expander("➕ Quick Add Popular Symbols"):
        popular = ['AAPL', 'MSFT', 'NVDA', 'AMD', 'AMZN', 'META', 'GOOGL', 'NFLX']
        cols = st.columns(4)
        for idx, sym in enumerate(popular):
            with cols[idx % 4]:
                if st.button(sym, key=f"quick_{sym}", use_container_width=True):
                    if len(st.session_state.watchlist) >= MAX_WATCHLIST_SIZE:
                        st.error(f"Watchlist limit reached ({MAX_WATCHLIST_SIZE} max)")
                    elif sym not in st.session_state.watchlist:
                        st.session_state.watchlist.append(sym)
                        st.rerun()

    return st.session_state.watchlist


def display_scanner_controls():
    """Scanner settings and controls"""

    st.sidebar.subheader("🔍 Scanner Settings")

    # Cache duration
    cache_mins = st.sidebar.slider(
        "Cache Duration (minutes)",
        min_value=1,
        max_value=15,
        value=5,
        help="How long to cache data before refreshing"
    )

    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox(
        "Auto-refresh",
        value=False,
        help="Automatically refresh scanner every X minutes"
    )

    if auto_refresh:
        refresh_interval = st.sidebar.slider(
            "Refresh interval (minutes)",
            min_value=5,
            max_value=30,
            value=10
        )
    else:
        refresh_interval = None

    # API call budget info
    st.sidebar.info(f"""
    💡 **API Management**:
    - Cache: {cache_mins} mins
    - Calls per symbol: ~3
    - Watchlist size: {len(st.session_state.get('watchlist', []))} symbols
    - Est. calls/scan: ~{len(st.session_state.get('watchlist', [])) * 3}
    """)

    return {
        'cache_duration': cache_mins,
        'auto_refresh': auto_refresh,
        'refresh_interval': refresh_interval
    }
