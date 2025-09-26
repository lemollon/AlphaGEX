"""
GammaHunter Configuration
========================
Central configuration file for all system constants and settings.
"""

# App Configuration
APP_TITLE = "GammaHunter - Market Maker Co-Pilot"
APP_ICON = "🎯"

# Trading Symbols Configuration - 200+ Current Symbols with Highest Options Volume
HIGH_PRIORITY_SYMBOLS = [
    # Major ETFs (Highest Options Volume)
    'SPY', 'QQQ', 'IWM', 'DIA', 'VIX', 'UVXY', 'SQQQ', 'TQQQ', 'SPXU', 'SPXL',
    'SOXL', 'SOXS', 'TNA', 'TZA', 'FAS', 'FAZ', 'UPRO', 'SPXS', 'XLF', 'XLE',
    
    # Mega Cap Tech (Most Active Options)
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX',
    'AMD', 'INTC', 'ORCL', 'CRM', 'ADBE', 'NOW', 'SNOW', 'ZM', 'UBER',
    'LYFT', 'ABNB', 'COIN', 'BLOCK', 'PLTR', 'RBLX', 'ROKU', 'PINS',
    'SNAP', 'HOOD', 'SOFI', 'AFRM', 'UPST', 'PATH', 'DASH',
    
    # High Volume Financial/Fintech
    'PYPL', 'V', 'MA', 'JPM', 'BAC', 'GS', 'MS', 'WFC', 'C',
    'AXP', 'DFS', 'COF', 'BLK', 'SCHW',
    
    # Crypto & Blockchain (Active Options)
    'MSTR', 'RIOT', 'MARA', 'CLSK', 'HIVE', 'BITF', 'BTBT', 'CAN',
    
    # Chinese Tech ADRs (High Options Activity)
    'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI', 'BILI',
    'DIDI', 'TME', 'VIPS', 'BEKE',
    
    # High Beta/Meme Stocks (Active Options)
    'GME', 'AMC', 'CLOV', 'SPCE', 'NKLA', 'LCID', 'RIVN', 'F', 'GM'
]

MEDIUM_PRIORITY_SYMBOLS = [
    # Sector ETFs with Options Activity
    'XLK', 'XLV', 'XLI', 'XLU', 'XLP', 'XLRE', 'XLY', 'XLB', 'XBI', 'IBB',
    'XHB', 'XRT', 'XME', 'XOP', 'KRE', 'SMH', 'SOXX', 'ARKK', 'ARKQ', 'ARKG',
    
    # International & Commodity ETFs
    'GLD', 'SLV', 'GDX', 'GDXJ', 'USO', 'UNG', 'TLT', 'IEF', 'HYG', 'LQD',
    'EEM', 'FXI', 'EWJ', 'EWZ', 'EWY', 'EWG', 'EWU', 'INDA', 'ASHR', 'MCHI',
    
    # Healthcare (Active Options)
    'JNJ', 'PFE', 'UNH', 'ABBV', 'MRK', 'BMY', 'LLY', 'TMO', 'ABT', 'DHR',
    'SYK', 'BSX', 'MDT', 'ISRG', 'VRTX', 'GILD', 'REGN', 'AMGN', 'BIIB', 'MRNA',
    'BNTX', 'JNJ', 'CVS', 'CNC', 'HUM', 'ANTM', 'CI',
    
    # Energy (High Options Volume)
    'XOM', 'CVX', 'COP', 'EOG', 'PXD', 'SLB', 'MPC', 'VLO', 'PSX', 'KMI',
    'OKE', 'WMB', 'EPD', 'HAL', 'BKR', 'DVN', 'FANG', 'MRO', 'APA',
    
    # Consumer Discretionary/Staples
    'WMT', 'TGT', 'COST', 'HD', 'LOW', 'NKE', 'SBUX', 'MCD', 'KO', 'PEP',
    'PG', 'CL', 'AMZN', 'DIS', 'NFLX', 'CMCSA', 'T', 'VZ', 'TMUS',
    
    # Industrials with Options Activity  
    'BA', 'CAT', 'MMM', 'GE', 'HON', 'UPS', 'FDX', 'LMT', 'RTX', 'NOC',
    'GD', 'DE', 'EMR', 'ETN', 'PH', 'ROK', 'DOV', 'ITW', 'WM', 'RSG',
    
    # Software/Cloud (High IV)
    'CRM', 'ORCL', 'ADBE', 'NOW', 'SNOW', 'DDOG', 'CRWD', 'ZS', 'NET',
    'OKTA', 'TWLO', 'SHOP', 'SPOT', 'DOCU', 'TEAM', 'WDAY', 'VEEV',
    'SPLK', 'PANW', 'FTNT', 'CYBR', 'ESTC', 'MDB', 'FSLY', 'CFLT',
    
    # Communication/Media
    'GOOGL', 'META', 'NFLX', 'DIS', 'CMCSA', 'T', 'VZ', 'CHTR', 'TMUS',
    'PARA', 'WBD', 'FOX', 'FOXA', 'DISH', 'SIRI',
    
    # REITs with Options
    'AMT', 'PLD', 'CCI', 'EQIX', 'SPG', 'O', 'WELL', 'AVB', 'EXR', 'PSA',
    'VTR', 'ARE', 'DLR', 'BXP', 'HST', 'SLG', 'VNO',
    
    # Utilities
    'NEE', 'DUK', 'SO', 'D', 'AEP', 'EXC', 'XEL', 'WEC', 'ED', 'ES',
    'AWK', 'ATO', 'CMS', 'DTE', 'ETR', 'FE', 'NI', 'PCG', 'PEG', 'PPL',
    
    # Biotech/Pharma with High IV
    'GILD', 'VRTX', 'REGN', 'AMGN', 'BIIB', 'MRNA', 'BNTX', 'NVAX', 'SGEN',
    'ALNY', 'BMRN', 'ILMN', 'INCY', 'JAZZ', 'RARE', 'SRPT', 'TECH', 'VCEL'
]

# API Configuration
TRADINGVOLATILITY_BASE_URL = "https://stocks.tradingvolatility.net/api"

# Rate Limiting (calls per minute)
API_LIMITS = {
    'weekday_non_realtime': 20,
    'weekday_realtime': 2,
    'weekend_options_volume': 1,
    'weekend_other': 2
}

# GEX Analysis Configuration
GEX_THRESHOLDS = {
    'spy_negative_gex': -1_000_000_000,  # -1B
    'spy_positive_gex': 2_000_000_000,   # 2B
    'qqq_negative_gex': -500_000_000,    # -500M
    'qqq_positive_gex': 1_000_000_000,   # 1B
    'wall_strength_min': 500_000_000,    # 500M
    'gamma_flip_threshold': 0.003        # 0.3%
}

# Risk Management
RISK_LIMITS = {
    'max_squeeze_allocation': 0.03,      # 3% of capital
    'max_premium_sell_allocation': 0.05,  # 5% of capital
    'max_condor_loss': 0.02,             # 2% portfolio loss
    'stop_loss_percentage': 0.50,        # 50% loss
    'profit_target_long': 1.00,          # 100% gain
    'profit_target_short': 0.50          # 50% gain
}

# Database Configuration
DATABASE_CONFIG = {
    'redis_host': 'localhost',
    'redis_port': 6379,
    'redis_db': 0,
    'cache_expiry': 300  # 5 minutes
}

# Alert Configuration
ALERT_TYPES = {
    'high_priority': ['squeeze_setup', 'gamma_flip_breach', 'wall_breach'],
    'medium_priority': ['new_walls', 'regime_change', 'condor_threat'],
    'low_priority': ['concentration_risk', 'charm_decay']
}

# Streamlit Configuration
STREAMLIT_CONFIG = {
    'page_title': APP_TITLE,
    'page_icon': APP_ICON,
    'layout': 'wide',
    'initial_sidebar_state': 'expanded'
}

# Color Scheme
COLORS = {
    'bullish': '#00ff00',
    'bearish': '#ff0000',
    'neutral': '#888888',
    'call_wall': '#ff6b6b',
    'put_wall': '#4ecdc4',
    'gamma_flip': '#ffd93d',
    'background': '#0e1117',
    'sidebar': '#262730'
}
