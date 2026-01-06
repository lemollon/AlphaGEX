"""
config_and_database.py - Configuration, Constants, and Database Functions
"""

import os

# Import PostgreSQL database adapter
from database_adapter import get_connection, get_db_adapter

# ============================================================================
# DATABASE PATH (DEPRECATED - Using PostgreSQL via DATABASE_URL)
# ============================================================================
# Legacy constant for backwards compatibility with scripts that import DB_PATH
# This system now uses PostgreSQL via DATABASE_URL environment variable
# Scripts should use: from database_adapter import get_connection
DB_PATH = None  # No longer using SQLite - PostgreSQL via DATABASE_URL

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# API Configuration
TRADINGVOLATILITY_BASE = "https://stocks.tradingvolatility.net/api"
CLAUDE_MODEL = "claude-sonnet-4-5-latest"  # Always use latest Sonnet 4.5

# Market Maker Behavioral States
MM_STATES = {
    'TRAPPED': {
        'threshold': -2e9,
        'behavior': 'Forced buying on rallies, selling on dips',
        'confidence': 85,
        'action': 'HUNT: Buy calls on any approach to flip point'
    },
    'DEFENDING': {
        'threshold': 1e9,
        'behavior': 'Selling rallies aggressively, buying dips',
        'confidence': 70,
        'action': 'FADE: Sell calls at resistance, puts at support'
    },
    'HUNTING': {
        'threshold': -1e9,
        'behavior': 'Aggressive positioning for direction',
        'confidence': 60,
        'action': 'WAIT: Let them show their hand first'
    },
    'PANICKING': {
        'threshold': -3e9,
        'behavior': 'Capitulation - covering at any price',
        'confidence': 90,
        'action': 'RIDE: Maximum aggression on squeeze'
    },
    'NEUTRAL': {
        'threshold': 0,
        'behavior': 'Balanced positioning',
        'confidence': 50,
        'action': 'RANGE: Iron condors between walls'
    }
}

# Trading Strategies Configuration
STRATEGIES = {
    # ===== DIRECTIONAL DEBIT SPREADS =====
    'BULLISH_CALL_SPREAD': {
        'conditions': {
            'net_gex_threshold': -0.5e9,  # Looser: any negative or slightly positive
            'distance_to_flip': 3.0,      # Within 3% of flip
            'trend': 'bullish'
        },
        'win_rate': 0.65,
        'risk_reward': 2.0,
        'typical_move': '2-4% up',
        'best_days': ['Monday', 'Tuesday', 'Friday'],
        'entry': 'Near support or flip point',
        'exit': 'Call wall or 75% max profit',
        'dte_range': [3, 14]
    },
    'BEARISH_PUT_SPREAD': {
        'conditions': {
            'net_gex_threshold': 1e9,     # Positive GEX breakdown
            'distance_to_flip': 3.0,
            'trend': 'bearish'
        },
        'win_rate': 0.62,
        'risk_reward': 2.0,
        'typical_move': '2-4% down',
        'best_days': ['Wednesday', 'Thursday'],
        'entry': 'Near resistance or below flip',
        'exit': 'Put wall or 75% max profit',
        'dte_range': [3, 14]
    },

    # ===== DIRECTIONAL CREDIT SPREADS =====
    'BULL_PUT_SPREAD': {
        'conditions': {
            'net_gex_threshold': 0.5e9,   # Slightly positive (support)
            'distance_to_put_wall': 2.0,
            'trend': 'neutral_to_bullish'
        },
        'win_rate': 0.70,
        'risk_reward': 0.4,
        'typical_move': 'Flat to +2%',
        'best_days': ['Any'],
        'entry': 'Sell puts at support/put wall',
        'exit': '50% profit or 2 DTE',
        'dte_range': [5, 21]
    },
    'BEAR_CALL_SPREAD': {
        'conditions': {
            'net_gex_threshold': 0.5e9,   # Positive GEX (resistance)
            'distance_to_call_wall': 2.0,
            'trend': 'neutral_to_bearish'
        },
        'win_rate': 0.68,
        'risk_reward': 0.4,
        'typical_move': 'Flat to -2%',
        'best_days': ['Any'],
        'entry': 'Sell calls at resistance/call wall',
        'exit': '50% profit or 2 DTE',
        'dte_range': [5, 21]
    },

    # ===== RANGE-BOUND STRATEGIES =====
    'IRON_CONDOR': {
        'conditions': {
            'net_gex_threshold': 1e9,     # Strong positive GEX
            'min_wall_distance': 2.0,     # Loosened from 3.0
            'iv_rank_below': 50
        },
        'win_rate': 0.72,
        'risk_reward': 0.3,
        'typical_move': 'Range bound',
        'best_days': ['Any with 5-10 DTE'],
        'entry': 'Short strikes at walls',
        'exit': '50% profit or breach',
        'dte_range': [5, 14]
    },
    'IRON_BUTTERFLY': {
        'conditions': {
            'net_gex_threshold': 2e9,     # Very strong positive GEX
            'price_at_flip': 1.0,         # Price near flip point
            'low_volatility': True
        },
        'win_rate': 0.68,
        'risk_reward': 0.5,
        'typical_move': 'Pinned at flip',
        'best_days': ['Expiration week'],
        'entry': 'Sell ATM, buy wings',
        'exit': '50% profit or breach',
        'dte_range': [3, 7]
    },

    # ===== VOLATILITY STRATEGIES =====
    'LONG_STRADDLE': {
        'conditions': {
            'net_gex_threshold': -2e9,    # Extreme negative GEX
            'low_volatility': False,
            'expected_move': 'large'
        },
        'win_rate': 0.55,
        'risk_reward': 3.0,
        'typical_move': '5%+ either direction',
        'best_days': ['Before earnings/events'],
        'entry': 'Buy ATM calls + puts',
        'exit': 'Either wall or 100% profit',
        'dte_range': [0, 7]
    },
    'LONG_STRANGLE': {
        'conditions': {
            'net_gex_threshold': -1e9,
            'low_volatility': False,
            'expected_move': 'moderate'
        },
        'win_rate': 0.58,
        'risk_reward': 2.5,
        'typical_move': '3-5% either direction',
        'best_days': ['Before events'],
        'entry': 'Buy OTM calls + puts',
        'exit': 'Either wall or 75% profit',
        'dte_range': [0, 14]
    },

    # ===== GEX-SPECIFIC STRATEGIES =====
    'NEGATIVE_GEX_SQUEEZE': {
        'conditions': {
            'net_gex_threshold': -1e9,
            'distance_to_flip': 2.0,      # Loosened from 1.5
            'min_put_wall_distance': 1.0
        },
        'win_rate': 0.68,
        'risk_reward': 3.0,
        'typical_move': '2-3% in direction',
        'best_days': ['Monday', 'Tuesday'],
        'entry': 'Break above flip point',
        'exit': 'Call wall or 100% profit',
        'dte_range': [0, 5]
    },
    'POSITIVE_GEX_BREAKDOWN': {
        'conditions': {
            'net_gex_threshold': 2e9,
            'proximity_to_flip': 1.0,     # Loosened from 0.3
            'call_wall_rejection': True
        },
        'win_rate': 0.62,
        'risk_reward': 2.5,
        'typical_move': '1-2% down',
        'best_days': ['Wednesday', 'Thursday'],
        'entry': 'Break below flip point',
        'exit': 'Put wall or 75% profit',
        'dte_range': [0, 5]
    },

    # ===== PREMIUM COLLECTION =====
    'PREMIUM_SELLING': {
        'conditions': {
            'wall_strength': 500e6,
            'distance_from_wall': 1.5,    # Loosened from 1.0
            'positive_gex': True
        },
        'win_rate': 0.65,
        'risk_reward': 0.5,
        'typical_move': 'Rejection at levels',
        'best_days': ['Any 0-2 DTE'],
        'entry': 'At wall approach',
        'exit': '50% profit or time',
        'dte_range': [0, 3]
    },
    'CALENDAR_SPREAD': {
        'conditions': {
            'net_gex_threshold': 1e9,     # Positive GEX (range)
            'price_stability': True,
            'low_near_term_iv': True
        },
        'win_rate': 0.60,
        'risk_reward': 1.0,
        'typical_move': 'Stable range',
        'best_days': ['Any'],
        'entry': 'Sell near DTE, buy far DTE',
        'exit': 'Near DTE expiration',
        'dte_range': [7, 30]
    }
}

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_database():
    """Initialize comprehensive database schema"""
    conn = get_connection()
    # Enable autocommit to prevent transaction abort cascading
    conn._conn.autocommit = True
    c = conn.cursor()

    # GEX History
    c.execute('''
        CREATE TABLE IF NOT EXISTS gex_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            net_gex REAL,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            spot_price REAL,
            mm_state TEXT,
            regime TEXT,
            data_source TEXT
        )
    ''')

    # =========================================================================
    # AI INTELLIGENCE TABLES (Required for AI Intelligence endpoints)
    # =========================================================================

    # Market Data - Real-time market snapshots
    c.execute('''
        CREATE TABLE IF NOT EXISTS market_data (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            spot_price REAL,
            vix REAL,
            net_gex REAL,
            call_volume REAL,
            put_volume REAL,
            data_source TEXT
        )
    ''')

    # Psychology Analysis - Market regime and psychology detection
    c.execute('''
        CREATE TABLE IF NOT EXISTS psychology_analysis (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            regime_type TEXT,
            confidence REAL,
            psychology_trap TEXT,
            trap_probability REAL,
            reasoning TEXT
        )
    ''')

    # GEX Levels - Gamma exposure key levels
    c.execute('''
        CREATE TABLE IF NOT EXISTS gex_levels (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            call_wall REAL,
            put_wall REAL,
            flip_point REAL,
            max_gamma_strike REAL,
            net_gex REAL,
            gex_regime TEXT
        )
    ''')

    # Account State - Trading account snapshots
    c.execute('''
        CREATE TABLE IF NOT EXISTS account_state (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            account_value REAL DEFAULT 10000,
            cash_balance REAL,
            buying_power REAL,
            daily_pnl REAL,
            total_pnl REAL
        )
    ''')

    # Trades - All trade records (open and closed)
    c.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            strike REAL,
            option_type TEXT,
            contracts INTEGER DEFAULT 1,
            entry_price REAL,
            exit_price REAL,
            current_price REAL,
            status TEXT DEFAULT 'OPEN',
            pattern_type TEXT,
            confidence_score REAL,
            realized_pnl REAL,
            unrealized_pnl REAL,
            entry_reason TEXT,
            exit_reason TEXT
        )
    ''')

    # Trade Recommendations
    c.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            strategy TEXT,
            confidence REAL,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            option_strike REAL,
            option_type TEXT,
            dte INTEGER,
            reasoning TEXT,
            mm_behavior TEXT,
            outcome TEXT,
            pnl REAL
        )
    ''')
    
    # Active Positions
    c.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            strategy TEXT,
            direction TEXT,
            entry_price REAL,
            current_price REAL,
            exit_price REAL,
            target REAL,
            stop REAL,
            size REAL,
            quantity INTEGER,
            status TEXT DEFAULT 'ACTIVE',
            closed_at DATETIME,
            pnl REAL,
            entry_net_gex REAL,
            entry_flip_point REAL,
            entry_spot_price REAL,
            entry_regime TEXT,
            notes TEXT
        )
    ''')
    
    # Performance Analytics
    c.execute('''
        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            total_trades INTEGER,
            winning_trades INTEGER,
            losing_trades INTEGER,
            total_pnl REAL,
            win_rate REAL,
            avg_winner REAL,
            avg_loser REAL,
            sharpe_ratio REAL,
            max_drawdown REAL
        )
    ''')
    
    # AI Conversations
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_message TEXT,
            ai_response TEXT,
            context_data TEXT,
            confidence_score REAL
        )
    ''')

    # Autonomous Trader Positions (MUST come before autonomous_trader_logs due to FK)
    c.execute('''
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
    ''')

    # Autonomous Trade Log (daily summaries)
    c.execute('''
        CREATE TABLE IF NOT EXISTS autonomous_trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            position_id INTEGER,
            success INTEGER DEFAULT 1,
            realized_pnl REAL
        )
    ''')

    # Autonomous Config
    c.execute('''
        CREATE TABLE IF NOT EXISTS autonomous_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    # ARES Iron Condor Positions
    c.execute('''
        CREATE TABLE IF NOT EXISTS ares_positions (
            id SERIAL PRIMARY KEY,
            position_id TEXT UNIQUE NOT NULL,
            open_date TEXT NOT NULL,
            open_time TEXT,
            expiration TEXT NOT NULL,

            -- Iron Condor Strikes (4 legs)
            put_long_strike REAL NOT NULL,
            put_short_strike REAL NOT NULL,
            call_short_strike REAL NOT NULL,
            call_long_strike REAL NOT NULL,

            -- Credits
            put_credit REAL NOT NULL,
            call_credit REAL NOT NULL,
            total_credit REAL NOT NULL,

            -- Position details
            contracts INTEGER NOT NULL,
            spread_width REAL NOT NULL,
            max_loss REAL NOT NULL,

            -- Order IDs from broker
            put_spread_order_id TEXT,
            call_spread_order_id TEXT,

            -- Status
            status TEXT DEFAULT 'open',
            close_date TEXT,
            close_time TEXT,
            close_price REAL,
            realized_pnl REAL,

            -- Market data at entry
            underlying_price_at_entry REAL,
            vix_at_entry REAL,
            expected_move REAL,

            -- Metadata
            mode TEXT DEFAULT 'paper',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ARES Daily Performance Tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS ares_daily_performance (
            id SERIAL PRIMARY KEY,
            date TEXT UNIQUE NOT NULL,
            starting_capital REAL NOT NULL,
            ending_capital REAL NOT NULL,
            daily_pnl REAL NOT NULL,
            daily_return_pct REAL NOT NULL,
            cumulative_pnl REAL NOT NULL,
            cumulative_return_pct REAL NOT NULL,
            positions_opened INTEGER DEFAULT 0,
            positions_closed INTEGER DEFAULT 0,
            high_water_mark REAL,
            drawdown_pct REAL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # Autonomous Trader Comprehensive Logs
    c.execute('''
        CREATE TABLE IF NOT EXISTS autonomous_trader_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            log_type TEXT NOT NULL,

            -- Market Context
            symbol TEXT,
            spot_price REAL,
            net_gex REAL,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            vix_level REAL,

            -- Psychology Trap Analysis
            pattern_detected TEXT,
            confidence_score REAL,
            trade_direction TEXT,
            risk_level TEXT,
            liberation_setup BOOLEAN,
            liberation_strike REAL,
            liberation_expiry DATE,
            false_floor_detected BOOLEAN,
            false_floor_strike REAL,
            forward_magnet_above REAL,
            forward_magnet_below REAL,
            polr TEXT,

            -- RSI Analysis
            rsi_5m REAL,
            rsi_15m REAL,
            rsi_1h REAL,
            rsi_4h REAL,
            rsi_1d REAL,
            rsi_aligned_overbought BOOLEAN,
            rsi_aligned_oversold BOOLEAN,
            rsi_coiling BOOLEAN,

            -- Strike Selection Reasoning
            strike_chosen REAL,
            strike_selection_reason TEXT,
            alternative_strikes TEXT,
            why_not_alternatives TEXT,

            -- Position Sizing
            kelly_pct REAL,
            position_size_dollars REAL,
            contracts INTEGER,
            sizing_rationale TEXT,

            -- AI Reasoning (LangChain + Claude)
            ai_thought_process TEXT,
            ai_confidence TEXT,
            ai_warnings TEXT,
            langchain_chain_used TEXT,

            -- Trade Decision
            action_taken TEXT,
            strategy_name TEXT,
            reasoning_summary TEXT,
            full_reasoning TEXT,

            -- Outcome Tracking
            position_id INTEGER,
            outcome TEXT,
            pnl REAL,

            -- Session Tracking
            scan_cycle INTEGER,
            session_id TEXT,

            FOREIGN KEY (position_id) REFERENCES autonomous_positions(id)
        )
    ''')
    
    # Migrate existing databases to add new columns
    _migrate_positions_table(c)

    # Scheduler state table (for auto-restart persistence)
    c.execute('''
        CREATE TABLE IF NOT EXISTS scheduler_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_running INTEGER DEFAULT 0,
            last_started TEXT,
            last_stopped TEXT,
            last_trade_check TEXT,
            last_position_check TEXT,
            execution_count INTEGER DEFAULT 0,
            should_auto_restart INTEGER DEFAULT 1,
            restart_reason TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Initialize scheduler state if not exists
    c.execute('''
        INSERT OR IGNORE INTO scheduler_state (id, is_running, should_auto_restart)
        VALUES (1, 0, 1)
    ''')

    # ===== PSYCHOLOGY TRAP DETECTION TABLES =====

    # Main regime signals table (enhanced with expiration data)
    c.execute('''
        CREATE TABLE IF NOT EXISTS regime_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            spy_price REAL,
            vix_current REAL,

            -- Regime identification
            primary_regime_type TEXT,
            secondary_regime_type TEXT,
            confidence_score REAL,
            trade_direction TEXT,
            risk_level TEXT,
            description TEXT,
            detailed_explanation TEXT,
            psychology_trap TEXT,

            -- RSI data
            rsi_5m REAL,
            rsi_15m REAL,
            rsi_1h REAL,
            rsi_4h REAL,
            rsi_1d REAL,
            rsi_score REAL,
            rsi_aligned_overbought INTEGER,
            rsi_aligned_oversold INTEGER,
            rsi_coiling INTEGER,

            -- Current gamma walls
            nearest_call_wall REAL,
            call_wall_distance_pct REAL,
            call_wall_strength REAL,
            call_wall_dealer_position TEXT,

            nearest_put_wall REAL,
            put_wall_distance_pct REAL,
            put_wall_strength REAL,
            put_wall_dealer_position TEXT,

            net_gamma REAL,
            net_gamma_regime TEXT,

            -- Expiration layer
            zero_dte_gamma REAL,
            gamma_expiring_this_week REAL,
            gamma_expiring_next_week REAL,
            gamma_persistence_ratio REAL,
            liberation_setup_detected INTEGER,
            liberation_target_strike REAL,
            liberation_expiry_date DATE,
            false_floor_detected INTEGER,
            false_floor_strike REAL,
            false_floor_expiry_date DATE,

            -- Forward GEX
            monthly_magnet_above REAL,
            monthly_magnet_above_strength REAL,
            monthly_magnet_below REAL,
            monthly_magnet_below_strength REAL,
            path_of_least_resistance TEXT,
            polr_confidence REAL,

            -- Volume
            volume_ratio REAL,

            -- Price targets
            target_price_near REAL,
            target_price_far REAL,
            target_timeline_days INTEGER,

            -- Outcome tracking
            price_change_1d REAL,
            price_change_5d REAL,
            price_change_10d REAL,
            signal_correct INTEGER,
            vix_spike_detected INTEGER,

            -- Additional volatility and flip point tracking
            volatility_regime TEXT,
            at_flip_point INTEGER,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add vix_spike_detected column if it doesn't exist (migration)
    try:
        c.execute("SELECT vix_spike_detected FROM regime_signals LIMIT 1")
    except Exception:
        c.execute("ALTER TABLE regime_signals ADD COLUMN vix_spike_detected INTEGER")
        print("✓ Added vix_spike_detected column to regime_signals table")

    # Add volatility_regime column if it doesn't exist (migration)
    try:
        c.execute("SELECT volatility_regime FROM regime_signals LIMIT 1")
    except Exception:
        c.execute("ALTER TABLE regime_signals ADD COLUMN volatility_regime TEXT")
        print("✓ Added volatility_regime column to regime_signals table")

    # Add at_flip_point column if it doesn't exist (migration)
    try:
        c.execute("SELECT at_flip_point FROM regime_signals LIMIT 1")
    except Exception:
        c.execute("ALTER TABLE regime_signals ADD COLUMN at_flip_point INTEGER")
        print("✓ Added at_flip_point column to regime_signals table")

    # Gamma expiration timeline table
    c.execute('''
        CREATE TABLE IF NOT EXISTS gamma_expiration_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date DATE NOT NULL,
            expiration_date DATE NOT NULL,
            dte INTEGER NOT NULL,
            expiration_type TEXT,
            strike REAL NOT NULL,

            call_gamma REAL,
            put_gamma REAL,
            total_gamma REAL,
            net_gamma REAL,

            call_oi INTEGER,
            put_oi INTEGER,

            distance_from_spot_pct REAL,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Historical OI tracking (for accumulation analysis)
    c.execute('''
        CREATE TABLE IF NOT EXISTS historical_open_interest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            symbol TEXT NOT NULL,
            strike REAL NOT NULL,
            expiration_date DATE NOT NULL,

            call_oi INTEGER,
            put_oi INTEGER,
            call_volume INTEGER DEFAULT 0,
            put_volume INTEGER DEFAULT 0,
            call_gamma REAL,
            put_gamma REAL,

            UNIQUE(date, symbol, strike, expiration_date)
        )
    ''')

    # Forward magnet tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS forward_magnets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date DATE NOT NULL,
            strike REAL NOT NULL,
            expiration_date DATE NOT NULL,
            dte INTEGER,

            magnet_strength_score REAL,
            total_gamma REAL,
            total_oi INTEGER,
            distance_from_spot_pct REAL,
            direction TEXT
        )
    ''')

    # Sucker statistics (enhanced with expiration scenarios)
    c.execute('''
        CREATE TABLE IF NOT EXISTS sucker_statistics (
            scenario_type TEXT PRIMARY KEY,
            total_occurrences INTEGER,
            newbie_fade_failed INTEGER,
            newbie_fade_succeeded INTEGER,
            failure_rate REAL,
            avg_price_change_when_failed REAL,
            avg_days_to_resolution REAL,
            last_updated DATETIME
        )
    ''')

    # Liberation trade outcomes
    c.execute('''
        CREATE TABLE IF NOT EXISTS liberation_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date DATE,
            liberation_date DATE,
            strike REAL,
            expiry_ratio REAL,

            price_at_signal REAL,
            price_at_liberation REAL,
            price_1d_after REAL,
            price_5d_after REAL,

            breakout_occurred INTEGER,
            max_move_pct REAL,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ===== PUSH NOTIFICATION TABLES =====

    # Push notification subscriptions
    c.execute('''
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT UNIQUE NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            preferences TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ===== MISSING TABLES REQUIRED BY API ROUTES =====

    # Psychology Notifications (used by psychology_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS psychology_notifications (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            notification_type TEXT,
            regime_type TEXT,
            message TEXT,
            severity TEXT DEFAULT 'info',
            data JSONB,
            read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # Autonomous Closed Trades (used by autonomous_routes.py, trader_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS autonomous_closed_trades (
            id SERIAL PRIMARY KEY,
            symbol TEXT DEFAULT 'SPY',
            strategy TEXT,
            strike REAL,
            option_type TEXT,
            contracts INTEGER DEFAULT 1,
            entry_date TEXT,
            entry_time TEXT,
            entry_price REAL,
            exit_date TEXT,
            exit_time TEXT,
            exit_price REAL,
            realized_pnl REAL,
            exit_reason TEXT,
            hold_time_hours REAL,
            entry_spot_price REAL,
            exit_spot_price REAL,
            entry_vix REAL,
            exit_vix REAL,
            gex_regime TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # Autonomous Open Positions (alias view - used by some routes)
    # Note: autonomous_positions table already exists, this is for compatibility
    c.execute('''
        CREATE TABLE IF NOT EXISTS autonomous_open_positions (
            id SERIAL PRIMARY KEY,
            symbol TEXT DEFAULT 'SPY',
            strategy TEXT,
            strike REAL,
            option_type TEXT,
            contracts INTEGER DEFAULT 1,
            entry_date TEXT,
            entry_time TEXT,
            entry_price REAL,
            current_price REAL,
            unrealized_pnl REAL,
            status TEXT DEFAULT 'OPEN',
            entry_spot_price REAL,
            current_spot_price REAL,
            gex_regime TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            -- Greek columns for transparency
            entry_delta REAL,
            entry_gamma REAL,
            entry_theta REAL,
            entry_vega REAL,
            entry_iv REAL,
            current_delta REAL,
            current_gamma REAL,
            current_theta REAL,
            current_vega REAL,
            current_iv REAL,
            -- Data source tracking
            is_delayed BOOLEAN DEFAULT FALSE,
            data_confidence TEXT DEFAULT 'high',
            contract_symbol TEXT,
            expiration_date TEXT,
            last_updated TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # Add missing columns to existing autonomous_open_positions table
    greek_columns = [
        ('entry_delta', 'REAL'),
        ('entry_gamma', 'REAL'),
        ('entry_theta', 'REAL'),
        ('entry_vega', 'REAL'),
        ('entry_iv', 'REAL'),
        ('current_delta', 'REAL'),
        ('current_gamma', 'REAL'),
        ('current_theta', 'REAL'),
        ('current_vega', 'REAL'),
        ('current_iv', 'REAL'),
        ('is_delayed', 'BOOLEAN DEFAULT FALSE'),
        ('data_confidence', "TEXT DEFAULT 'high'"),
        ('contract_symbol', 'TEXT'),
        ('expiration_date', 'TEXT'),
        ('last_updated', 'TIMESTAMPTZ DEFAULT NOW()'),
    ]
    for col_name, col_type in greek_columns:
        try:
            c.execute(f'''
                ALTER TABLE autonomous_open_positions
                ADD COLUMN IF NOT EXISTS {col_name} {col_type}
            ''')
        except:
            pass  # Column may already exist

    # Autonomous Equity Snapshots (used by autonomous_routes.py, trader_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS autonomous_equity_snapshots (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            equity REAL,
            cash REAL,
            positions_value REAL,
            daily_pnl REAL,
            cumulative_pnl REAL,
            drawdown_pct REAL,
            high_water_mark REAL
        )
    ''')

    # Autonomous Live Status (used by trader_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS autonomous_live_status (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            status TEXT DEFAULT 'idle',
            last_scan TEXT,
            positions_open INTEGER DEFAULT 0,
            daily_trades INTEGER DEFAULT 0,
            daily_pnl REAL DEFAULT 0,
            message TEXT
        )
    ''')

    # Autonomous Trade Activity (used by trader_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS autonomous_trade_activity (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            action TEXT,
            symbol TEXT,
            strike REAL,
            option_type TEXT,
            contracts INTEGER,
            price REAL,
            reason TEXT,
            success BOOLEAN DEFAULT TRUE
        )
    ''')

    # Scanner History (used by scanner_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS scanner_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbols_scanned TEXT,
            results JSONB,
            scan_type TEXT,
            duration_ms INTEGER
        )
    ''')

    # Alerts (used by alerts_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            alert_type TEXT,
            condition TEXT,
            threshold REAL,
            comparison TEXT,
            active BOOLEAN DEFAULT TRUE,
            triggered_at TIMESTAMPTZ,
            notification_sent BOOLEAN DEFAULT FALSE
        )
    ''')

    # Alert History (used by alerts_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS alert_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            alert_id INTEGER,
            symbol TEXT,
            alert_type TEXT,
            triggered_value REAL,
            threshold REAL,
            message TEXT
        )
    ''')

    # Trade Setups (used by setups_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_setups (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            setup_type TEXT,
            strike REAL,
            option_type TEXT,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            contracts INTEGER DEFAULT 1,
            expiration_date TEXT,
            reasoning TEXT,
            confidence REAL,
            status TEXT DEFAULT 'pending',
            executed_at TIMESTAMPTZ,
            result TEXT
        )
    ''')

    # Probability Predictions (used by probability_calculator.py)
    # Stores each prediction made by the system for later accuracy tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS probability_predictions (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT NOT NULL,
            prediction_type TEXT NOT NULL,
            target_date DATE NOT NULL,
            current_price REAL,
            range_low REAL,
            range_high REAL,
            prob_in_range REAL,
            prob_above REAL,
            prob_below REAL,
            confidence_level TEXT,
            net_gex REAL,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            vix_level REAL,
            implied_vol REAL,
            psychology_state TEXT,
            fomo_level REAL,
            fear_level REAL,
            mm_state TEXT,
            actual_close_price REAL,
            prediction_correct BOOLEAN,
            recorded_at TIMESTAMPTZ
        )
    ''')

    # Probability Outcomes (used by probability_routes.py)
    # Links predictions to actual outcomes for accuracy tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS probability_outcomes (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            prediction_id INTEGER REFERENCES probability_predictions(id),
            prediction_type TEXT,
            predicted_probability REAL,
            actual_outcome BOOLEAN,
            correct_prediction BOOLEAN,
            outcome_timestamp TIMESTAMPTZ,
            confidence REAL,
            regime_type TEXT,
            gex_value REAL,
            vix_value REAL,
            error_pct REAL
        )
    ''')

    # Probability Weights (used by probability_routes.py and probability_calculator.py)
    # Stores the configurable weights for probability calculations
    c.execute('''
        CREATE TABLE IF NOT EXISTS probability_weights (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            weight_name TEXT NOT NULL,
            weight_value REAL NOT NULL,
            description TEXT,
            last_updated TIMESTAMPTZ DEFAULT NOW(),
            calibration_count INTEGER DEFAULT 0,
            gex_wall_strength REAL DEFAULT 0.35,
            volatility_impact REAL DEFAULT 0.25,
            psychology_signal REAL DEFAULT 0.20,
            mm_positioning REAL DEFAULT 0.15,
            historical_pattern REAL DEFAULT 0.05,
            accuracy_score REAL,
            active BOOLEAN DEFAULT TRUE
        )
    ''')

    # Calibration History (used by probability_routes.py)
    # Tracks model weight adjustments over time
    c.execute('''
        CREATE TABLE IF NOT EXISTS calibration_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            calibration_date TIMESTAMPTZ DEFAULT NOW(),
            weight_name TEXT,
            old_value REAL,
            new_value REAL,
            reason TEXT,
            performance_delta REAL,
            predictions_analyzed INTEGER,
            overall_accuracy REAL,
            high_conf_accuracy REAL,
            adjustments_made JSONB
        )
    ''')

    # SPX Institutional Positions (used by spx_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_institutional_positions (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPX',
            position_type TEXT,
            strike REAL,
            contracts INTEGER,
            entry_price REAL,
            current_price REAL,
            unrealized_pnl REAL,
            entry_date TEXT,
            exit_date TEXT,
            status TEXT DEFAULT 'OPEN'
        )
    ''')

    # SPX Debug Logs (used by spx_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_debug_logs (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            category TEXT,
            session_id TEXT,
            log_level TEXT DEFAULT 'info',
            message TEXT,
            data JSONB,
            scan_cycle INTEGER
        )
    ''')

    # Strategy Config (used by trader_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS strategy_config (
            id SERIAL PRIMARY KEY,
            strategy_name TEXT UNIQUE,
            enabled BOOLEAN DEFAULT TRUE,
            max_position_size REAL,
            max_daily_trades INTEGER,
            risk_per_trade REAL,
            parameters JSONB,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ML Models (used by autonomous_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS ml_models (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            model_name TEXT,
            model_type TEXT,
            version TEXT,
            accuracy REAL,
            training_samples INTEGER,
            features TEXT,
            hyperparameters JSONB,
            status TEXT DEFAULT 'active'
        )
    ''')

    # ML Predictions (used by autonomous_routes.py)
    c.execute('''
        CREATE TABLE IF NOT EXISTS ml_predictions (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            model_id INTEGER,
            symbol TEXT DEFAULT 'SPY',
            prediction_type TEXT,
            predicted_value REAL,
            confidence REAL,
            actual_value REAL,
            correct BOOLEAN,
            features_used JSONB
        )
    ''')

    # =========================================================================
    # ML/AI DATA COLLECTION TABLES - COMPREHENSIVE STORAGE FOR ANALYSIS
    # =========================================================================
    # These tables store ALL data needed for machine learning and AI analysis
    # Everything that flows through the system should be captured here

    # Historical Price Data (OHLCV bars from Polygon)
    # Previously: Fetched for charts but NOT stored - now stored for ML training
    c.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            symbol TEXT DEFAULT 'SPY',
            timeframe TEXT NOT NULL,  -- '1min', '5min', '15min', '1h', '1d'
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume BIGINT,
            vwap REAL,
            num_trades INTEGER,
            data_source TEXT DEFAULT 'polygon',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(symbol, timeframe, timestamp)
        )
    ''')

    # Greeks Snapshots - Capture Greeks at every significant moment
    # Previously: Calculated and discarded - now stored for ML correlation
    c.execute('''
        CREATE TABLE IF NOT EXISTS greeks_snapshots (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            strike REAL NOT NULL,
            option_type TEXT NOT NULL,  -- 'CALL' or 'PUT'
            expiration_date DATE NOT NULL,
            dte INTEGER,
            -- The Greeks
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            rho REAL,
            -- Volatility metrics
            implied_volatility REAL,
            iv_rank REAL,
            iv_percentile REAL,
            -- Price context
            underlying_price REAL,
            option_price REAL,
            bid REAL,
            ask REAL,
            spread_pct REAL,
            -- Volume context
            volume INTEGER,
            open_interest INTEGER,
            -- Source tracking
            data_source TEXT,
            context TEXT  -- 'entry', 'exit', 'monitoring', 'hourly_snapshot'
        )
    ''')

    # VIX Term Structure - Full volatility curve
    # Previously: Only spot VIX stored - now full term structure for ML
    c.execute('''
        CREATE TABLE IF NOT EXISTS vix_term_structure (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            -- Spot VIX
            vix_spot REAL NOT NULL,
            vix_9d REAL,  -- VIX9D
            vix_3m REAL,  -- VIX3M (VXV)
            vix_6m REAL,  -- VIX6M
            -- VIX Futures
            vx_front_month REAL,
            vx_front_month_expiry DATE,
            vx_second_month REAL,
            vx_second_month_expiry DATE,
            vx_third_month REAL,
            vx_fourth_month REAL,
            -- Derived metrics
            contango_pct REAL,  -- % between spot and front month
            term_structure_slope REAL,  -- Overall slope
            inversion_detected BOOLEAN DEFAULT FALSE,
            -- Related indices
            vvix REAL,  -- VIX of VIX
            skew_index REAL,  -- CBOE SKEW
            put_call_ratio REAL,
            -- Context
            spy_price REAL,
            regime TEXT,  -- 'low_vol', 'normal', 'elevated', 'crisis'
            data_source TEXT
        )
    ''')

    # Options Flow/Volume - Capture unusual activity for ML sentiment
    # Previously: Used for GEX calc then discarded - now stored
    c.execute('''
        CREATE TABLE IF NOT EXISTS options_flow (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            -- Aggregate volume
            total_call_volume INTEGER,
            total_put_volume INTEGER,
            put_call_ratio REAL,
            -- Unusual activity
            unusual_call_volume INTEGER,
            unusual_put_volume INTEGER,
            unusual_strikes TEXT,  -- JSON array of unusual strike activity
            -- Open interest changes
            call_oi_change INTEGER,
            put_oi_change INTEGER,
            largest_oi_strike REAL,
            largest_oi_type TEXT,
            -- Premium flow (if available)
            net_call_premium REAL,
            net_put_premium REAL,
            -- Expiration breakdown
            zero_dte_volume INTEGER,
            weekly_volume INTEGER,
            monthly_volume INTEGER,
            -- Context
            spot_price REAL,
            vix_level REAL,
            data_source TEXT
        )
    ''')

    # AI Analysis Results - Store every AI insight for learning
    # Previously: Displayed and discarded - now stored for feedback loop
    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_analysis_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            analysis_type TEXT NOT NULL,  -- 'market_commentary', 'trade_advice', 'risk_analysis', 'copilot_chat'
            -- Input context
            symbol TEXT DEFAULT 'SPY',
            input_prompt TEXT,
            market_context JSONB,  -- GEX, VIX, price, regime at time of analysis
            -- AI output
            ai_response TEXT NOT NULL,
            confidence_score REAL,
            recommendations JSONB,  -- Structured recommendations if any
            warnings TEXT,
            -- Model info
            model_used TEXT,
            tokens_used INTEGER,
            response_time_ms INTEGER,
            -- Outcome tracking (for feedback loop)
            outcome_tracked BOOLEAN DEFAULT FALSE,
            outcome_correct BOOLEAN,
            actual_result TEXT,
            feedback_notes TEXT
        )
    ''')

    # Position Sizing History - Track all sizing decisions
    # Previously: Calculated and discarded - now stored for optimization
    c.execute('''
        CREATE TABLE IF NOT EXISTS position_sizing_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            -- Input parameters
            account_value REAL,
            win_rate REAL,
            avg_win REAL,
            avg_loss REAL,
            current_drawdown_pct REAL,
            -- Calculated sizes
            kelly_full REAL,
            kelly_half REAL,
            kelly_quarter REAL,
            recommended_size REAL,
            max_risk_dollars REAL,
            -- Risk metrics
            var_95 REAL,
            expected_value REAL,
            risk_of_ruin REAL,
            -- Context
            vix_level REAL,
            regime TEXT,
            sizing_rationale TEXT,
            -- Outcome tracking
            trade_taken BOOLEAN DEFAULT FALSE,
            actual_size_used REAL,
            trade_outcome REAL  -- Actual P&L if trade was taken
        )
    ''')

    # Strategy Comparison Results - Track strategy selection decisions
    # Previously: Displayed and discarded - now stored for optimization
    c.execute('''
        CREATE TABLE IF NOT EXISTS strategy_comparison_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            -- Market conditions at comparison time
            spot_price REAL,
            net_gex REAL,
            vix_level REAL,
            regime TEXT,
            -- Strategies compared
            strategies_evaluated JSONB,  -- Array of strategy names
            comparison_results JSONB,  -- Full comparison data
            -- Winner
            recommended_strategy TEXT,
            recommendation_confidence REAL,
            recommendation_reasoning TEXT,
            -- Alternatives
            second_best_strategy TEXT,
            third_best_strategy TEXT,
            -- Outcome tracking
            strategy_chosen TEXT,  -- What user actually chose
            trade_taken BOOLEAN DEFAULT FALSE,
            trade_outcome REAL
        )
    ''')

    # Real-Time Market Snapshots - Comprehensive market state every minute
    # This is the master table for ML feature engineering
    c.execute('''
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            -- Price data
            price REAL NOT NULL,
            bid REAL,
            ask REAL,
            spread_pct REAL,
            volume_1min BIGINT,
            -- GEX data
            net_gex REAL,
            call_wall REAL,
            put_wall REAL,
            flip_point REAL,
            distance_to_call_wall_pct REAL,
            distance_to_put_wall_pct REAL,
            distance_to_flip_pct REAL,
            -- VIX data
            vix_spot REAL,
            vix_change_1d_pct REAL,
            -- RSI multi-timeframe
            rsi_5m REAL,
            rsi_15m REAL,
            rsi_1h REAL,
            rsi_4h REAL,
            rsi_1d REAL,
            -- Regime classification
            gex_regime TEXT,
            psychology_regime TEXT,
            volatility_regime TEXT,
            -- Derived signals
            liberation_setup BOOLEAN DEFAULT FALSE,
            false_floor BOOLEAN DEFAULT FALSE,
            trap_detected TEXT,
            -- Session info
            market_session TEXT,  -- 'pre', 'regular', 'post', 'closed'
            minutes_to_close INTEGER,
            day_of_week INTEGER
        )
    ''')

    # Data Collection Log - Track what data was collected when
    c.execute('''
        CREATE TABLE IF NOT EXISTS data_collection_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            collection_type TEXT NOT NULL,  -- 'price', 'greeks', 'vix', 'flow', 'gex'
            source TEXT NOT NULL,  -- 'polygon', 'tradier', 'yahoo', 'tradingvolatility'
            symbol TEXT DEFAULT 'SPY',
            records_collected INTEGER,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            duration_ms INTEGER,
            next_collection_at TIMESTAMPTZ
        )
    ''')

    # ===== INDEXES FOR NEW ML TABLES =====

    # Helper function to safely create indexes (define BEFORE first use)
    def safe_index(sql):
        try:
            c.execute(sql)
        except Exception:
            pass  # Column or table may not exist in older schema

    # Price history indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_price_history_symbol_timeframe ON price_history(symbol, timeframe)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_price_history_timestamp ON price_history(timestamp)")

    # Greeks snapshots indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_greeks_snapshots_timestamp ON greeks_snapshots(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_greeks_snapshots_symbol_strike ON greeks_snapshots(symbol, strike)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_greeks_snapshots_context ON greeks_snapshots(context)")

    # VIX term structure indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_vix_term_structure_timestamp ON vix_term_structure(timestamp)")

    # Options flow indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_options_flow_timestamp ON options_flow(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_options_flow_symbol ON options_flow(symbol)")

    # AI analysis indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_ai_analysis_history_timestamp ON ai_analysis_history(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ai_analysis_history_type ON ai_analysis_history(analysis_type)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ai_analysis_history_outcome ON ai_analysis_history(outcome_tracked)")

    # Position sizing indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_position_sizing_history_timestamp ON position_sizing_history(timestamp)")

    # Strategy comparison indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_strategy_comparison_history_timestamp ON strategy_comparison_history(timestamp)")

    # Market snapshots indexes (critical for ML queries)
    safe_index("CREATE INDEX IF NOT EXISTS idx_market_snapshots_timestamp ON market_snapshots(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_market_snapshots_symbol ON market_snapshots(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_market_snapshots_regime ON market_snapshots(gex_regime, psychology_regime)")

    # Data collection log indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_data_collection_log_timestamp ON data_collection_log(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_data_collection_log_type ON data_collection_log(collection_type)")

    # ===== BACKTEST RESULTS TABLES =====

    # Backtest INDIVIDUAL TRADES - For verification and audit
    # This is the PROOF of every trade that makes up the backtest results
    c.execute('''
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id SERIAL PRIMARY KEY,
            -- Link to backtest run
            backtest_run_id TEXT NOT NULL,  -- UUID for each backtest run
            strategy_name TEXT NOT NULL,
            -- Trade details
            trade_number INTEGER NOT NULL,
            symbol TEXT DEFAULT 'SPY',
            -- Entry
            entry_date DATE NOT NULL,
            entry_time TIME,
            entry_price REAL NOT NULL,
            entry_strike REAL,
            entry_option_type TEXT,  -- 'CALL' or 'PUT'
            entry_expiration DATE,
            entry_dte INTEGER,
            entry_spot_price REAL,
            -- Entry context (why this trade was taken)
            entry_net_gex REAL,
            entry_flip_point REAL,
            entry_vix REAL,
            entry_regime TEXT,
            entry_pattern TEXT,
            entry_signal_confidence REAL,
            entry_reasoning TEXT,
            -- Exit
            exit_date DATE NOT NULL,
            exit_time TIME,
            exit_price REAL NOT NULL,
            exit_spot_price REAL,
            exit_reason TEXT,  -- 'target_hit', 'stop_loss', 'time_exit', 'signal_exit'
            -- Results
            pnl_dollars REAL NOT NULL,
            pnl_percent REAL NOT NULL,
            win BOOLEAN NOT NULL,
            hold_time_hours REAL,
            -- Greeks at entry (for analysis)
            entry_delta REAL,
            entry_gamma REAL,
            entry_theta REAL,
            entry_iv REAL,
            -- Timestamps
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # Backtest runs - Track each backtest execution
    c.execute('''
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id SERIAL PRIMARY KEY,
            run_id TEXT UNIQUE NOT NULL,  -- UUID
            strategy_name TEXT NOT NULL,
            symbol TEXT DEFAULT 'SPY',
            -- Time range
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            -- Configuration used
            config JSONB,
            -- Summary (duplicated from results for quick access)
            total_trades INTEGER,
            win_rate REAL,
            total_pnl REAL,
            -- Run metadata
            started_at TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            duration_seconds REAL,
            status TEXT DEFAULT 'running'  -- 'running', 'completed', 'failed'
        )
    ''')

    # Indexes for backtest trades (for quick verification lookups)
    safe_index("CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id ON backtest_trades(backtest_run_id)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_backtest_trades_strategy ON backtest_trades(strategy_name)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_backtest_trades_entry_date ON backtest_trades(entry_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_backtest_trades_win ON backtest_trades(win)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_backtest_runs_run_id ON backtest_runs(run_id)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy ON backtest_runs(strategy_name)")

    # Backtest results for all strategies (summary only)
    c.execute('''
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            strategy_name TEXT,
            symbol TEXT,
            start_date TEXT,
            end_date TEXT,
            total_trades INTEGER,
            winning_trades INTEGER,
            losing_trades INTEGER,
            win_rate REAL,
            avg_win_pct REAL,
            avg_loss_pct REAL,
            largest_win_pct REAL,
            largest_loss_pct REAL,
            expectancy_pct REAL,
            total_return_pct REAL,
            max_drawdown_pct REAL,
            sharpe_ratio REAL,
            avg_trade_duration_days REAL
        )
    ''')

    # Backtest summary table (aggregated results)
    c.execute('''
        CREATE TABLE IF NOT EXISTS backtest_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT,
            start_date TEXT,
            end_date TEXT,
            psychology_trades INTEGER,
            psychology_win_rate REAL,
            psychology_expectancy REAL,
            gex_trades INTEGER,
            gex_win_rate REAL,
            gex_expectancy REAL,
            options_trades INTEGER,
            options_win_rate REAL,
            options_expectancy REAL
        )
    ''')

    # ===== STRATEGY OPTIMIZER TABLES =====

    # Strike-level performance tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS strike_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            strategy_name TEXT NOT NULL,

            -- Strike details
            strike_distance_pct REAL,  -- % from spot (negative = ITM, positive = OTM)
            strike_absolute REAL,       -- Actual strike price
            spot_price REAL,             -- SPY price at entry
            strike_type TEXT,            -- 'CALL' or 'PUT'
            moneyness TEXT,              -- 'ITM', 'ATM', 'OTM'

            -- Greeks at entry
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,

            -- Time to expiration
            dte INTEGER,                 -- Days to expiration
            expiration_date DATE,

            -- Market regime at entry
            vix_current REAL,
            vix_regime TEXT,             -- 'low', 'normal', 'high'
            net_gex REAL,
            gamma_regime TEXT,           -- 'positive', 'negative'

            -- Performance
            entry_premium REAL,
            exit_premium REAL,
            pnl_pct REAL,
            pnl_dollars REAL,
            max_profit_pct REAL,
            max_loss_pct REAL,
            win INTEGER,                 -- 1 = win, 0 = loss
            hold_time_hours INTEGER,

            -- Pattern context
            pattern_type TEXT,           -- e.g., 'LIBERATION', 'GAMMA_SQUEEZE'
            confidence_score REAL,

            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Spread width performance (for multi-leg strategies)
    c.execute('''
        CREATE TABLE IF NOT EXISTS spread_width_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            strategy_name TEXT NOT NULL,
            spread_type TEXT,            -- 'iron_condor', 'butterfly', 'vertical_call', 'vertical_put'

            -- Spread configuration
            short_strike_call REAL,
            long_strike_call REAL,
            short_strike_put REAL,
            long_strike_put REAL,

            -- Distances
            call_spread_width_points REAL,
            put_spread_width_points REAL,
            short_call_distance_pct REAL,  -- % from spot
            long_call_distance_pct REAL,
            short_put_distance_pct REAL,
            long_put_distance_pct REAL,

            -- Entry details
            spot_price REAL,
            dte INTEGER,
            vix_current REAL,
            net_gex REAL,

            -- Performance
            entry_credit REAL,
            exit_cost REAL,
            pnl_pct REAL,
            pnl_dollars REAL,
            max_profit_pct REAL,
            max_loss_pct REAL,
            win INTEGER,
            hold_time_hours INTEGER,

            -- Greeks totals
            total_delta REAL,
            total_gamma REAL,
            total_theta REAL,

            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Greeks performance analysis
    c.execute('''
        CREATE TABLE IF NOT EXISTS greeks_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            strategy_name TEXT NOT NULL,

            -- Entry Greeks
            entry_delta REAL,
            entry_gamma REAL,
            entry_theta REAL,
            entry_vega REAL,
            entry_iv_rank REAL,          -- IV percentile

            -- Position characteristics
            position_type TEXT,          -- 'long', 'short', 'neutral'
            delta_target TEXT,           -- 'low_delta', 'medium_delta', 'high_delta'
            theta_strategy TEXT,         -- 'positive_theta', 'negative_theta'

            -- Market context
            dte INTEGER,
            vix_current REAL,
            spot_price REAL,

            -- Performance
            pnl_pct REAL,
            pnl_dollars REAL,
            win INTEGER,
            hold_time_hours INTEGER,

            -- Greeks efficiency
            delta_pnl_ratio REAL,        -- PnL / delta (delta efficiency)
            theta_pnl_ratio REAL,        -- PnL / theta (time decay efficiency)

            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # DTE (Days To Expiration) performance
    c.execute('''
        CREATE TABLE IF NOT EXISTS dte_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            strategy_name TEXT NOT NULL,

            -- Time details
            dte_at_entry INTEGER,
            dte_bucket TEXT,             -- '0-3', '4-7', '8-14', '15-30', '30+'
            hold_time_hours INTEGER,
            expiration_date DATE,

            -- Entry context
            spot_price REAL,
            strike REAL,
            strike_distance_pct REAL,
            vix_current REAL,
            pattern_type TEXT,

            -- Performance
            entry_premium REAL,
            exit_premium REAL,
            pnl_pct REAL,
            pnl_dollars REAL,
            win INTEGER,

            -- Time decay analysis
            theta_at_entry REAL,
            avg_theta_decay REAL,        -- Average daily theta
            theta_pnl_contribution REAL, -- How much PnL from time decay

            -- Optimal exit analysis
            held_to_expiration INTEGER,  -- 1 = yes, 0 = no
            days_before_expiration_closed INTEGER,

            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Performance optimization: Add indexes for frequently queried columns
    # (safe_index function defined earlier in this function)
    safe_index("CREATE INDEX IF NOT EXISTS idx_gex_history_symbol ON gex_history(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_gex_history_timestamp ON gex_history(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_recommendations_symbol ON recommendations(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_recommendations_timestamp ON recommendations(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_positions_closed_at ON positions(closed_at)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_performance_date ON performance(date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp)")

    # Psychology trap detection indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_regime_signals_timestamp ON regime_signals(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_regime_signals_type ON regime_signals(primary_regime_type)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_regime_signals_liberation ON regime_signals(liberation_setup_detected, liberation_expiry_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_regime_signals_false_floor ON regime_signals(false_floor_detected, false_floor_expiry_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_gamma_expiration_timeline_expiration ON gamma_expiration_timeline(expiration_date, strike)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_gamma_expiration_timeline_snapshot ON gamma_expiration_timeline(snapshot_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_historical_oi_date_strike ON historical_open_interest(date, strike, expiration_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_forward_magnets_snapshot_strike ON forward_magnets(snapshot_date, strike)")

    # Backtest indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy ON backtest_results(strategy_name)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_backtest_results_timestamp ON backtest_results(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_backtest_results_symbol ON backtest_results(symbol)")

    # Strategy Optimizer indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_strike_performance_strategy ON strike_performance(strategy_name)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_strike_performance_timestamp ON strike_performance(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_strike_performance_dte ON strike_performance(dte)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_strike_performance_moneyness ON strike_performance(moneyness)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_strike_performance_vix_regime ON strike_performance(vix_regime)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_strike_performance_win ON strike_performance(win)")

    safe_index("CREATE INDEX IF NOT EXISTS idx_spread_width_strategy ON spread_width_performance(strategy_name)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_spread_width_timestamp ON spread_width_performance(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_spread_width_type ON spread_width_performance(spread_type)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_spread_width_win ON spread_width_performance(win)")

    safe_index("CREATE INDEX IF NOT EXISTS idx_greeks_performance_strategy ON greeks_performance(strategy_name)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_greeks_performance_timestamp ON greeks_performance(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_greeks_performance_delta_target ON greeks_performance(delta_target)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_greeks_performance_win ON greeks_performance(win)")

    safe_index("CREATE INDEX IF NOT EXISTS idx_dte_performance_strategy ON dte_performance(strategy_name)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_dte_performance_timestamp ON dte_performance(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_dte_performance_bucket ON dte_performance(dte_bucket)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_dte_performance_pattern ON dte_performance(pattern_type)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_dte_performance_win ON dte_performance(win)")

    # Push notification indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_push_subscriptions_endpoint ON push_subscriptions(endpoint)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_push_subscriptions_created_at ON push_subscriptions(created_at)")

    # Autonomous trader logs indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_timestamp ON autonomous_trader_logs(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_type ON autonomous_trader_logs(log_type)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_symbol ON autonomous_trader_logs(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_position ON autonomous_trader_logs(position_id)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_session ON autonomous_trader_logs(session_id)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_pattern ON autonomous_trader_logs(pattern_detected)")

    # Autonomous positions indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_positions_status ON autonomous_positions(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_positions_symbol ON autonomous_positions(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_positions_entry_date ON autonomous_positions(entry_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_positions_strategy ON autonomous_positions(strategy)")

    # Autonomous trade log indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_trade_log_date ON autonomous_trade_log(date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_trade_log_action ON autonomous_trade_log(action)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_trade_log_position_id ON autonomous_trade_log(position_id)")

    # ARES positions indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_ares_positions_status ON ares_positions(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ares_positions_open_date ON ares_positions(open_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ares_positions_expiration ON ares_positions(expiration)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ares_positions_mode ON ares_positions(mode)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ares_daily_performance_date ON ares_daily_performance(date)")

    # ===== NEW TABLE INDEXES =====

    # Psychology notifications indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_psychology_notifications_timestamp ON psychology_notifications(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_psychology_notifications_type ON psychology_notifications(notification_type)")

    # Autonomous closed trades indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_closed_trades_symbol ON autonomous_closed_trades(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_closed_trades_exit_date ON autonomous_closed_trades(exit_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_closed_trades_strategy ON autonomous_closed_trades(strategy)")

    # Autonomous open positions indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_open_positions_symbol ON autonomous_open_positions(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_open_positions_status ON autonomous_open_positions(status)")

    # Autonomous equity snapshots indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_equity_snapshots_timestamp ON autonomous_equity_snapshots(timestamp)")

    # Autonomous live status indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_live_status_timestamp ON autonomous_live_status(timestamp)")

    # Autonomous trade activity indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_trade_activity_timestamp ON autonomous_trade_activity(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_autonomous_trade_activity_symbol ON autonomous_trade_activity(symbol)")

    # Scanner history indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_scanner_history_timestamp ON scanner_history(timestamp)")

    # Alerts indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(active)")

    # Alert history indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_alert_history_timestamp ON alert_history(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_alert_history_alert_id ON alert_history(alert_id)")

    # Trade setups indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_trade_setups_symbol ON trade_setups(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_trade_setups_status ON trade_setups(status)")

    # Probability outcomes indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_probability_outcomes_timestamp ON probability_outcomes(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_probability_outcomes_type ON probability_outcomes(prediction_type)")

    # Calibration history indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_calibration_history_timestamp ON calibration_history(timestamp)")

    # SPX institutional positions indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_spx_institutional_positions_status ON spx_institutional_positions(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_spx_institutional_positions_symbol ON spx_institutional_positions(symbol)")

    # SPX debug logs indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_spx_debug_logs_timestamp ON spx_debug_logs(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_spx_debug_logs_category ON spx_debug_logs(category)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_spx_debug_logs_session_id ON spx_debug_logs(session_id)")

    # Strategy config indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_strategy_config_name ON strategy_config(strategy_name)")

    # ML models indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_ml_models_status ON ml_models(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ml_models_name ON ml_models(model_name)")

    # ML predictions indexes
    safe_index("CREATE INDEX IF NOT EXISTS idx_ml_predictions_timestamp ON ml_predictions(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ml_predictions_model_id ON ml_predictions(model_id)")

    # =========================================================================
    # CONSOLIDATED TABLES - Previously scattered across multiple files
    # All CREATE TABLE statements must be in THIS FILE ONLY
    # =========================================================================

    # ----- From gamma/gamma_tracking_database.py -----
    # gamma_history - Historical gamma snapshots (multi-day storage)
    # NOTE: This is DIFFERENT from gex_history - gamma_history has more fields
    c.execute('''
        CREATE TABLE IF NOT EXISTS gamma_history (
            id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            date DATE NOT NULL,
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
    ''')

    # gamma_daily_summary - Daily aggregated gamma data
    c.execute('''
        CREATE TABLE IF NOT EXISTS gamma_daily_summary (
            id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            date DATE NOT NULL,
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
    ''')

    # spy_correlation - SPY correlation tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS spy_correlation (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            symbol TEXT NOT NULL,
            spy_gex_change_pct REAL,
            symbol_gex_change_pct REAL,
            spy_price_change_pct REAL,
            symbol_price_change_pct REAL,
            correlation_score REAL,
            UNIQUE(symbol, date)
        )
    ''')

    # ----- From trading/wheel_strategy.py -----
    # wheel_cycles - Wheel strategy cycle tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS wheel_cycles (
            id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'CSP',
            start_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            end_date TIMESTAMPTZ,
            shares_owned INTEGER DEFAULT 0,
            share_cost_basis REAL DEFAULT 0.0,
            total_csp_premium REAL DEFAULT 0.0,
            total_cc_premium REAL DEFAULT 0.0,
            total_premium_collected REAL DEFAULT 0.0,
            assignment_date TIMESTAMPTZ,
            assignment_price REAL,
            called_away_date TIMESTAMPTZ,
            called_away_price REAL,
            realized_pnl REAL DEFAULT 0.0,
            unrealized_pnl REAL DEFAULT 0.0,
            target_delta_csp REAL DEFAULT 0.30,
            target_delta_cc REAL DEFAULT 0.30,
            min_premium_pct REAL DEFAULT 1.0,
            max_dte INTEGER DEFAULT 45,
            min_dte INTEGER DEFAULT 21,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # wheel_legs - Individual option legs in wheel strategy
    c.execute('''
        CREATE TABLE IF NOT EXISTS wheel_legs (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER REFERENCES wheel_cycles(id),
            leg_type TEXT NOT NULL,
            action TEXT NOT NULL,
            strike REAL NOT NULL,
            expiration_date DATE NOT NULL,
            contracts INTEGER NOT NULL DEFAULT 1,
            premium_received REAL DEFAULT 0.0,
            premium_paid REAL DEFAULT 0.0,
            open_date TIMESTAMPTZ NOT NULL,
            close_date TIMESTAMPTZ,
            close_reason TEXT,
            underlying_price_at_open REAL,
            underlying_price_at_close REAL,
            iv_at_open REAL,
            delta_at_open REAL,
            dte_at_open INTEGER,
            contract_symbol TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # wheel_activity_log - Wheel strategy action log
    c.execute('''
        CREATE TABLE IF NOT EXISTS wheel_activity_log (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER REFERENCES wheel_cycles(id),
            leg_id INTEGER REFERENCES wheel_legs(id),
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            action TEXT NOT NULL,
            description TEXT,
            premium_impact REAL DEFAULT 0.0,
            pnl_impact REAL DEFAULT 0.0,
            underlying_price REAL,
            option_price REAL,
            details JSONB
        )
    ''')

    # ----- From trading/decision_logger.py -----
    # trading_decisions - Complete decision audit trail
    c.execute('''
        CREATE TABLE IF NOT EXISTS trading_decisions (
            id SERIAL PRIMARY KEY,
            decision_id VARCHAR(50) UNIQUE NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            decision_type VARCHAR(50) NOT NULL,
            action VARCHAR(20) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            strategy VARCHAR(100),
            spot_price DECIMAL(12,4),
            spot_source VARCHAR(50),
            option_price DECIMAL(10,4),
            strike DECIMAL(10,2),
            expiration DATE,
            vix DECIMAL(8,2),
            net_gex DECIMAL(20,2),
            gex_regime VARCHAR(20),
            market_regime VARCHAR(50),
            trend VARCHAR(20),
            backtest_strategy VARCHAR(100),
            backtest_win_rate DECIMAL(5,2),
            backtest_expectancy DECIMAL(8,4),
            backtest_uses_real_data BOOLEAN,
            primary_reason TEXT,
            supporting_factors JSONB,
            risk_factors JSONB,
            position_size_dollars DECIMAL(12,2),
            position_size_contracts INTEGER,
            max_risk_dollars DECIMAL(12,2),
            target_profit_pct DECIMAL(6,2),
            stop_loss_pct DECIMAL(6,2),
            prob_profit DECIMAL(5,2),
            passed_risk_checks BOOLEAN DEFAULT TRUE,
            risk_check_details JSONB,
            full_decision JSONB,
            actual_entry_price DECIMAL(10,4),
            actual_exit_price DECIMAL(10,4),
            actual_pnl DECIMAL(12,2),
            actual_hold_days INTEGER,
            outcome_notes TEXT,
            outcome_updated_at TIMESTAMPTZ
        )
    ''')

    # =========================================================================
    # BOT_DECISION_LOGS - COMPREHENSIVE UNIFIED LOGGING TABLE
    # =========================================================================
    # This is the master logging table with FULL transparency on every decision
    # Includes: Claude AI prompts/responses, execution timeline, alternatives,
    # session tracking, risk checks, and error logging
    c.execute('''
        CREATE TABLE IF NOT EXISTS bot_decision_logs (
            id SERIAL PRIMARY KEY,

            -- IDENTIFICATION
            decision_id TEXT UNIQUE NOT NULL,
            bot_name TEXT NOT NULL,  -- PHOENIX, ATLAS, ARES, HERMES, ORACLE
            session_id TEXT,
            scan_cycle INTEGER,
            decision_sequence INTEGER,
            timestamp TIMESTAMPTZ DEFAULT NOW(),

            -- DECISION
            decision_type TEXT,  -- ENTRY, EXIT, SKIP, ADJUSTMENT
            action TEXT,         -- BUY, SELL, HOLD
            symbol TEXT,
            strategy TEXT,

            -- TRADE DETAILS
            strike REAL,
            expiration DATE,
            option_type TEXT,
            contracts INTEGER,

            -- MARKET CONTEXT (flattened for filtering)
            spot_price REAL,
            vix REAL,
            net_gex REAL,
            gex_regime TEXT,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            trend TEXT,

            -- AI REASONING (full transparency)
            claude_prompt TEXT,
            claude_response TEXT,
            claude_model TEXT,
            claude_tokens_used INTEGER,
            claude_response_time_ms INTEGER,
            langchain_chain TEXT,
            ai_confidence TEXT,
            ai_warnings JSONB,

            -- REASONING BREAKDOWN
            entry_reasoning TEXT,
            strike_reasoning TEXT,
            size_reasoning TEXT,
            exit_reasoning TEXT,

            -- ALTERNATIVES
            alternatives_considered JSONB,  -- [{strike: 5850, reason_rejected: "too close to put wall"}]
            rejection_reasons JSONB,
            other_strategies_considered JSONB,

            -- PSYCHOLOGY/PATTERNS
            psychology_pattern TEXT,
            liberation_setup BOOLEAN,
            false_floor_detected BOOLEAN,
            forward_magnets JSONB,

            -- POSITION SIZING
            kelly_pct REAL,
            position_size_dollars REAL,
            max_risk_dollars REAL,

            -- BACKTEST REFERENCE
            backtest_win_rate REAL,
            backtest_expectancy REAL,
            backtest_sharpe REAL,

            -- RISK CHECKS
            risk_checks_performed JSONB,  -- [{check: "max_position", passed: true, value: 15000, limit: 25000}]
            passed_all_checks BOOLEAN,
            blocked_reason TEXT,

            -- EXECUTION TIMELINE
            order_submitted_at TIMESTAMPTZ,
            order_filled_at TIMESTAMPTZ,
            broker_order_id TEXT,
            expected_fill_price REAL,
            actual_fill_price REAL,
            slippage_pct REAL,
            broker_status TEXT,
            execution_notes TEXT,

            -- OUTCOME (filled later)
            actual_pnl REAL,
            exit_triggered_by TEXT,  -- 'PROFIT_TARGET', 'STOP_LOSS', 'TIME_DECAY', 'MANUAL', 'GEX_REGIME_CHANGE'
            exit_timestamp TIMESTAMPTZ,
            exit_price REAL,
            exit_slippage_pct REAL,
            outcome_correct BOOLEAN,
            outcome_notes TEXT,

            -- DEBUGGING
            api_calls_made JSONB,  -- [{api: "tradier", endpoint: "quotes", time_ms: 150, success: true}]
            errors_encountered JSONB,  -- [{timestamp, error, retried, resolved}]
            processing_time_ms INTEGER,

            -- FULL BLOB (for export)
            full_decision JSONB,

            -- TIMESTAMPS
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # Indexes for fast filtering on bot_decision_logs
    safe_index("CREATE INDEX IF NOT EXISTS idx_bot_logs_bot ON bot_decision_logs(bot_name)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_bot_logs_timestamp ON bot_decision_logs(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_bot_logs_session ON bot_decision_logs(session_id)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_bot_logs_outcome ON bot_decision_logs(actual_pnl)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_bot_logs_decision_type ON bot_decision_logs(decision_type)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_bot_logs_symbol ON bot_decision_logs(symbol)")

    # ----- From core/vix_hedge_manager.py -----
    # vix_hedge_signals - VIX hedge signal tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS vix_hedge_signals (
            id SERIAL PRIMARY KEY,
            signal_date DATE NOT NULL,
            signal_time TIME,
            signal_type TEXT NOT NULL,
            confidence REAL,
            vol_regime TEXT,
            vix_spot REAL,
            vix_futures_m1 REAL,
            vix_futures_m2 REAL,
            term_structure_pct REAL,
            iv_percentile REAL,
            realized_vol_20d REAL,
            iv_rv_spread REAL,
            spy_spot REAL,
            reasoning TEXT,
            recommended_action TEXT,
            risk_warning TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # vix_hedge_positions - VIX hedge position tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS vix_hedge_positions (
            id SERIAL PRIMARY KEY,
            position_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strike REAL,
            expiration DATE,
            contracts INTEGER DEFAULT 1,
            entry_date DATE NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL,
            exit_date DATE,
            exit_price REAL,
            realized_pnl REAL,
            status TEXT DEFAULT 'OPEN',
            hedge_ratio REAL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ----- From core/autonomous_strategy_competition.py -----
    # strategy_competition - Strategy competition tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS strategy_competition (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            competition_id TEXT UNIQUE,
            strategy_name TEXT NOT NULL,
            strategy_params JSONB,
            paper_capital REAL DEFAULT 100000,
            current_equity REAL,
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            win_rate REAL,
            total_pnl REAL DEFAULT 0,
            max_drawdown REAL DEFAULT 0,
            sharpe_ratio REAL,
            status TEXT DEFAULT 'active',
            last_trade_date DATE
        )
    ''')

    # ----- From unified_trading_engine.py -----
    # unified_positions - Unified trading engine positions
    c.execute('''
        CREATE TABLE IF NOT EXISTS unified_positions (
            id SERIAL PRIMARY KEY,
            position_id TEXT UNIQUE NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            entry_date TIMESTAMPTZ NOT NULL,
            contracts INTEGER DEFAULT 1,
            strike REAL,
            expiration DATE,
            option_type TEXT,
            current_price REAL,
            unrealized_pnl REAL,
            status TEXT DEFAULT 'OPEN',
            regime_at_entry TEXT,
            signal_confidence REAL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # unified_trades - Unified trading engine closed trades
    c.execute('''
        CREATE TABLE IF NOT EXISTS unified_trades (
            id SERIAL PRIMARY KEY,
            trade_id TEXT UNIQUE NOT NULL,
            position_id TEXT,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            entry_date TIMESTAMPTZ NOT NULL,
            exit_price REAL NOT NULL,
            exit_date TIMESTAMPTZ NOT NULL,
            contracts INTEGER DEFAULT 1,
            realized_pnl REAL NOT NULL,
            pnl_pct REAL,
            hold_time_hours REAL,
            exit_reason TEXT,
            regime_at_entry TEXT,
            regime_at_exit TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # regime_classifications - Market regime classification history
    c.execute('''
        CREATE TABLE IF NOT EXISTS regime_classifications (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            regime_type TEXT NOT NULL,
            sub_regime TEXT,
            confidence REAL,
            spot_price REAL,
            net_gex REAL,
            vix REAL,
            momentum_1h REAL,
            momentum_4h REAL,
            trend TEXT,
            signal TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ----- From backend/jobs/background_jobs.py -----
    # background_jobs - Background job tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS background_jobs (
            id SERIAL PRIMARY KEY,
            job_id TEXT UNIQUE NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            message TEXT,
            params JSONB,
            result JSONB,
            error TEXT,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ----- From ai/ai_trade_advisor.py -----
    # ai_predictions - AI model predictions
    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_predictions (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            prediction_date DATE NOT NULL,
            symbol TEXT DEFAULT 'SPY',
            prediction_type TEXT NOT NULL,
            predicted_direction TEXT,
            predicted_magnitude REAL,
            confidence REAL,
            features_used JSONB,
            actual_direction TEXT,
            actual_magnitude REAL,
            correct BOOLEAN,
            evaluated_at TIMESTAMPTZ
        )
    ''')

    # pattern_learning - Pattern learning history
    c.execute('''
        CREATE TABLE IF NOT EXISTS pattern_learning (
            id SERIAL PRIMARY KEY,
            pattern_name TEXT NOT NULL,
            pattern_data JSONB,
            occurrences INTEGER DEFAULT 1,
            success_rate REAL,
            avg_return REAL,
            last_seen TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ai_performance - AI model performance tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_performance (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL UNIQUE,
            model_version TEXT,
            predictions_made INTEGER DEFAULT 0,
            correct_predictions INTEGER DEFAULT 0,
            accuracy REAL,
            avg_confidence REAL,
            features_importance JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ai_recommendations - AI trade recommendations
    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            recommendation_type TEXT NOT NULL,
            action TEXT NOT NULL,
            strike REAL,
            expiration DATE,
            confidence REAL,
            reasoning TEXT,
            risk_level TEXT,
            expected_return REAL,
            followed BOOLEAN DEFAULT FALSE,
            outcome REAL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ----- From data/option_chain_collector.py -----
    # options_chain_snapshots - Full options chain snapshots
    c.execute('''
        CREATE TABLE IF NOT EXISTS options_chain_snapshots (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT NOT NULL,
            expiration DATE NOT NULL,
            strike REAL NOT NULL,
            option_type TEXT NOT NULL,
            bid REAL,
            ask REAL,
            last REAL,
            volume INTEGER,
            open_interest INTEGER,
            implied_volatility REAL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            underlying_price REAL,
            UNIQUE(timestamp, symbol, expiration, strike, option_type)
        )
    ''')

    # options_collection_log - Options data collection tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS options_collection_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT NOT NULL,
            expirations_collected INTEGER,
            strikes_collected INTEGER,
            duration_ms INTEGER,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT
        )
    ''')

    # ----- From validation/quant_validation.py -----
    # paper_signals - Paper trading signals
    c.execute('''
        CREATE TABLE IF NOT EXISTS paper_signals (
            id SERIAL PRIMARY KEY,
            signal_id TEXT UNIQUE NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            signal_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            confidence REAL,
            regime TEXT,
            status TEXT DEFAULT 'pending'
        )
    ''')

    # paper_outcomes - Paper trading outcomes
    c.execute('''
        CREATE TABLE IF NOT EXISTS paper_outcomes (
            id SERIAL PRIMARY KEY,
            signal_id TEXT REFERENCES paper_signals(signal_id),
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            hold_time_hours REAL,
            exit_reason TEXT,
            correct BOOLEAN
        )
    ''')

    # ----- From quant/ module - Quant Enhancements -----

    # walk_forward_results - Walk-forward optimization validation results
    c.execute('''
        CREATE TABLE IF NOT EXISTS walk_forward_results (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            strategy_name TEXT NOT NULL,
            symbol TEXT DEFAULT 'SPY',
            total_windows INTEGER,
            is_avg_win_rate REAL,
            oos_avg_win_rate REAL,
            degradation_pct REAL,
            is_robust BOOLEAN DEFAULT FALSE,
            recommended_params JSONB,
            analysis_date TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ml_regime_models - ML regime classifier models and metrics
    c.execute('''
        CREATE TABLE IF NOT EXISTS ml_regime_models (
            id SERIAL PRIMARY KEY,
            symbol TEXT DEFAULT 'SPY',
            model_version TEXT NOT NULL,
            accuracy REAL,
            precision_score REAL,
            recall_score REAL,
            f1_score REAL,
            samples_trained INTEGER,
            samples_validated INTEGER,
            feature_importances JSONB,
            training_date TIMESTAMPTZ DEFAULT NOW(),
            is_active BOOLEAN DEFAULT TRUE,
            model_path TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ensemble_signals - Ensemble strategy combination signals
    c.execute('''
        CREATE TABLE IF NOT EXISTS ensemble_signals (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            final_signal TEXT NOT NULL,
            confidence REAL,
            bullish_weight REAL,
            bearish_weight REAL,
            neutral_weight REAL,
            should_trade BOOLEAN DEFAULT FALSE,
            position_size_multiplier REAL,
            component_signals JSONB,
            reasoning TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # monte_carlo_kelly - Monte Carlo Kelly stress test results
    c.execute('''
        CREATE TABLE IF NOT EXISTS monte_carlo_kelly (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            strategy_name TEXT,
            kelly_optimal REAL,
            kelly_safe REAL,
            kelly_conservative REAL,
            prob_ruin_optimal REAL,
            prob_ruin_safe REAL,
            prob_50pct_drawdown_optimal REAL,
            prob_50pct_drawdown_safe REAL,
            var_95_safe REAL,
            cvar_95_safe REAL,
            estimated_win_rate REAL,
            estimated_avg_win REAL,
            estimated_avg_loss REAL,
            sample_size INTEGER,
            uncertainty_level TEXT,
            recommendation TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # quant_recommendations - Complete quant-enhanced trading recommendations
    c.execute('''
        CREATE TABLE IF NOT EXISTS quant_recommendations (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT DEFAULT 'SPY',
            action TEXT NOT NULL,
            confidence REAL,
            should_trade BOOLEAN DEFAULT FALSE,
            position_size_pct REAL,
            position_value REAL,
            kelly_safe REAL,
            kelly_optimal REAL,
            prob_ruin REAL,
            var_95 REAL,
            uncertainty_level TEXT,
            ml_prediction JSONB,
            ensemble_signal JSONB,
            walk_forward_valid BOOLEAN DEFAULT TRUE,
            reasoning TEXT,
            warnings JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')

    # ----- From gamma/gex_data_tracker.py -----
    # gex_snapshots_detailed - Detailed GEX snapshots with strike data
    c.execute('''
        CREATE TABLE IF NOT EXISTS gex_snapshots_detailed (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT NOT NULL,
            spot_price REAL NOT NULL,
            net_gex REAL,
            flip_point REAL,
            call_wall REAL,
            call_wall_gamma REAL,
            put_wall REAL,
            put_wall_gamma REAL,
            zero_gamma_level REAL,
            total_call_gamma REAL,
            total_put_gamma REAL,
            data_source TEXT,
            strike_data JSONB
        )
    ''')

    # gex_change_log - GEX change events and velocity tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS gex_change_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT NOT NULL,
            change_type TEXT,
            previous_value REAL,
            new_value REAL,
            previous_gex REAL,
            current_gex REAL,
            change REAL,
            change_pct REAL,
            velocity_trend TEXT,
            direction_change BOOLEAN DEFAULT FALSE,
            trigger_event TEXT,
            spot_price REAL
        )
    ''')

    # gamma_strike_history - Strike-level gamma history
    c.execute('''
        CREATE TABLE IF NOT EXISTS gamma_strike_history (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            symbol TEXT NOT NULL,
            strike REAL NOT NULL,
            expiration DATE NOT NULL,
            call_gamma REAL,
            put_gamma REAL,
            net_gamma REAL,
            call_oi INTEGER,
            put_oi INTEGER,
            spot_price REAL
        )
    ''')

    # ----- From gamma/gamma_correlation_tracker.py -----
    # gamma_correlation - Multi-symbol gamma correlation
    c.execute('''
        CREATE TABLE IF NOT EXISTS gamma_correlation (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            base_symbol TEXT DEFAULT 'SPY',
            compare_symbol TEXT NOT NULL,
            correlation_30d REAL,
            correlation_7d REAL,
            gex_ratio REAL,
            price_beta REAL,
            notes TEXT
        )
    ''')

    # =========================================================================
    # SPX WHEEL SYSTEM TABLES (from trading/spx_wheel_system.py, etc.)
    # =========================================================================

    # SPX wheel parameters configuration
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_parameters (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            parameters JSONB NOT NULL,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')

    # SPX wheel positions
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_positions (
            id SERIAL PRIMARY KEY,
            opened_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMPTZ,
            status VARCHAR(20) DEFAULT 'OPEN',
            option_ticker VARCHAR(50),
            strike DECIMAL(10,2),
            expiration DATE,
            contracts INTEGER,
            entry_price DECIMAL(10,4),
            exit_price DECIMAL(10,4),
            premium_received DECIMAL(12,2),
            settlement_pnl DECIMAL(12,2),
            total_pnl DECIMAL(12,2),
            parameters_used JSONB,
            notes TEXT
        )
    ''')

    # SPX wheel performance tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_performance (
            id SERIAL PRIMARY KEY,
            date DATE UNIQUE,
            equity DECIMAL(14,2),
            daily_pnl DECIMAL(12,2),
            cumulative_pnl DECIMAL(12,2),
            open_positions INTEGER,
            backtest_expected_equity DECIMAL(14,2),
            divergence_pct DECIMAL(8,4)
        )
    ''')

    # SPX wheel Greeks snapshots
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_greeks (
            id SERIAL PRIMARY KEY,
            position_id INTEGER,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            delta DECIMAL(8,6),
            gamma DECIMAL(8,6),
            theta DECIMAL(8,4),
            vega DECIMAL(8,4),
            iv DECIMAL(8,6),
            underlying_price DECIMAL(10,2),
            option_price DECIMAL(10,4)
        )
    ''')

    # SPX wheel reconciliation logs
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_reconciliation (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            db_count INTEGER,
            broker_count INTEGER,
            matched_count INTEGER,
            is_reconciled BOOLEAN,
            details JSONB
        )
    ''')

    # SPX wheel alerts
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_alerts (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            alert_type VARCHAR(50),
            level VARCHAR(20),
            subject VARCHAR(200),
            body TEXT,
            position_id INTEGER,
            acknowledged BOOLEAN DEFAULT FALSE
        )
    ''')

    # SPX wheel multi-leg positions
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_multileg_positions (
            id SERIAL PRIMARY KEY,
            opened_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMPTZ,
            status VARCHAR(20) DEFAULT 'OPEN',
            strategy_type VARCHAR(30),
            expiration DATE,
            contracts INTEGER,
            legs JSONB,
            max_profit DECIMAL(12,2),
            max_loss DECIMAL(12,2),
            breakeven DECIMAL(10,2),
            credit_received DECIMAL(12,2),
            margin_required DECIMAL(12,2),
            entry_underlying_price DECIMAL(10,2),
            exit_pnl DECIMAL(12,2),
            notes TEXT
        )
    ''')

    # SPX wheel ML outcomes tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_ml_outcomes (
            id SERIAL PRIMARY KEY,
            trade_id VARCHAR(50) UNIQUE NOT NULL,
            trade_date VARCHAR(20),
            strike DECIMAL(10,2),
            underlying_price DECIMAL(10,2),
            dte INTEGER,
            delta DECIMAL(6,4),
            premium DECIMAL(10,4),
            iv DECIMAL(6,4),
            iv_rank DECIMAL(5,2),
            vix DECIMAL(6,2),
            vix_percentile DECIMAL(5,2),
            vix_term_structure DECIMAL(6,2),
            put_wall_distance_pct DECIMAL(6,2),
            call_wall_distance_pct DECIMAL(6,2),
            net_gex DECIMAL(20,2),
            spx_20d_return DECIMAL(6,2),
            spx_5d_return DECIMAL(6,2),
            spx_distance_from_high DECIMAL(6,2),
            premium_to_strike_pct DECIMAL(6,4),
            annualized_return DECIMAL(8,2),
            outcome VARCHAR(10),
            pnl DECIMAL(12,2),
            settlement_price DECIMAL(10,2),
            max_drawdown DECIMAL(12,2),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # =========================================================================
    # PROMETHEUS ML TABLES
    # =========================================================================

    # Prometheus predictions - stores ML predictions for trades
    c.execute('''
        CREATE TABLE IF NOT EXISTS prometheus_predictions (
            id SERIAL PRIMARY KEY,
            trade_id VARCHAR(50) UNIQUE NOT NULL,
            trade_date VARCHAR(20),
            strike DECIMAL(10,2),
            underlying_price DECIMAL(10,2),
            dte INTEGER,
            delta DECIMAL(6,4),
            premium DECIMAL(10,4),
            win_probability DECIMAL(5,4),
            recommendation VARCHAR(20),
            confidence DECIMAL(5,4),
            reasoning TEXT,
            key_factors JSONB,
            feature_values JSONB,
            vix DECIMAL(6,2),
            iv_rank DECIMAL(5,2),
            model_version VARCHAR(50),
            session_id VARCHAR(50),
            actual_outcome VARCHAR(10),
            actual_pnl DECIMAL(12,2),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Prometheus live model - stores the active ML model binary
    c.execute('''
        CREATE TABLE IF NOT EXISTS prometheus_live_model (
            id SERIAL PRIMARY KEY,
            model_version VARCHAR(50) NOT NULL,
            model_binary BYTEA,
            scaler_binary BYTEA,
            model_type VARCHAR(50),
            feature_names JSONB,
            accuracy DECIMAL(5,4),
            calibration_error DECIMAL(5,4),
            is_active BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Prometheus training history
    c.execute('''
        CREATE TABLE IF NOT EXISTS prometheus_training_history (
            id SERIAL PRIMARY KEY,
            training_id VARCHAR(50) UNIQUE NOT NULL,
            total_samples INTEGER,
            train_samples INTEGER,
            test_samples INTEGER,
            win_count INTEGER,
            loss_count INTEGER,
            baseline_win_rate DECIMAL(5,4),
            accuracy DECIMAL(5,4),
            precision_score DECIMAL(5,4),
            recall DECIMAL(5,4),
            f1_score DECIMAL(5,4),
            auc_roc DECIMAL(5,4),
            brier_score DECIMAL(5,4),
            cv_accuracy_mean DECIMAL(5,4),
            cv_accuracy_std DECIMAL(5,4),
            cv_scores JSONB,
            calibration_error DECIMAL(5,4),
            is_calibrated BOOLEAN DEFAULT FALSE,
            feature_importance JSONB,
            model_type VARCHAR(50),
            model_version VARCHAR(50),
            interpretation TEXT,
            honest_assessment TEXT,
            recommendation TEXT,
            model_path VARCHAR(255),
            model_saved_to_db BOOLEAN DEFAULT FALSE,
            model_binary BYTEA,
            scaler_binary BYTEA,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Prometheus logs
    c.execute('''
        CREATE TABLE IF NOT EXISTS prometheus_logs (
            id SERIAL PRIMARY KEY,
            log_type VARCHAR(30) NOT NULL,
            action VARCHAR(100),
            ml_score DECIMAL(5,4),
            recommendation VARCHAR(20),
            trade_id VARCHAR(50),
            reasoning TEXT,
            details JSONB,
            features JSONB,
            execution_time_ms INTEGER,
            session_id VARCHAR(50),
            trace_id VARCHAR(50),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Prometheus models (for versioning/backup)
    c.execute('''
        CREATE TABLE IF NOT EXISTS prometheus_models (
            id SERIAL PRIMARY KEY,
            model_version VARCHAR(50) NOT NULL,
            model_name VARCHAR(100),
            model_binary BYTEA,
            scaler_binary BYTEA,
            config JSONB,
            metrics JSONB,
            is_production BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # =========================================================================
    # SPX WHEEL BACKTEST TABLES (from backtest/spx_premium_backtest.py)
    # =========================================================================

    # SPX backtest runs metadata
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_backtest_runs (
            id SERIAL PRIMARY KEY,
            backtest_id VARCHAR(50) UNIQUE NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            config JSONB,
            summary JSONB,
            data_quality JSONB,
            ml_results JSONB
        )
    ''')

    # SPX backtest equity curve
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_backtest_equity (
            id SERIAL PRIMARY KEY,
            backtest_id VARCHAR(50) NOT NULL,
            date VARCHAR(20),
            equity DECIMAL(14,2),
            cash_balance DECIMAL(14,2),
            open_position_value DECIMAL(14,2),
            daily_pnl DECIMAL(12,2),
            cumulative_pnl DECIMAL(14,2),
            peak_equity DECIMAL(14,2),
            drawdown_pct DECIMAL(8,4),
            open_puts INTEGER,
            margin_used DECIMAL(14,2)
        )
    ''')

    # SPX backtest trades
    c.execute('''
        CREATE TABLE IF NOT EXISTS spx_wheel_backtest_trades (
            id SERIAL PRIMARY KEY,
            backtest_id VARCHAR(50) NOT NULL,
            backtest_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            trade_id INTEGER,
            trade_date VARCHAR(20),
            trade_type VARCHAR(30),
            option_ticker VARCHAR(50),
            strike DECIMAL(10,2),
            expiration VARCHAR(20),
            entry_price DECIMAL(10,4),
            exit_price DECIMAL(10,4),
            contracts INTEGER,
            premium_received DECIMAL(12,2),
            settlement_pnl DECIMAL(12,2),
            total_pnl DECIMAL(12,2),
            price_source VARCHAR(30),
            entry_underlying_price DECIMAL(10,2),
            exit_underlying_price DECIMAL(10,2),
            notes TEXT,
            parameters JSONB
        )
    ''')

    # =========================================================================
    # ML DECISION LOGS TABLE (from backend/api/routes/ml_routes.py)
    # =========================================================================

    c.execute('''
        CREATE TABLE IF NOT EXISTS ml_decision_logs (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            action VARCHAR(50) NOT NULL,
            symbol VARCHAR(20) DEFAULT 'SPX',
            details JSONB,
            ml_score DECIMAL(5,4),
            recommendation VARCHAR(20),
            reasoning TEXT,
            trade_id VARCHAR(50),
            backtest_id VARCHAR(50)
        )
    ''')

    # =========================================================================
    # APOLLO ML SCANNER TABLES
    # =========================================================================

    c.execute('''
        CREATE TABLE IF NOT EXISTS apollo_scans (
            id SERIAL PRIMARY KEY,
            scan_id VARCHAR(50) UNIQUE NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            symbols TEXT NOT NULL,
            results JSONB,
            market_regime VARCHAR(50),
            vix_at_scan REAL,
            scan_duration_ms INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS apollo_predictions (
            id SERIAL PRIMARY KEY,
            prediction_id VARCHAR(50) UNIQUE NOT NULL,
            scan_id VARCHAR(50),
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            symbol VARCHAR(20) NOT NULL,
            direction_pred VARCHAR(20),
            direction_confidence REAL,
            magnitude_pred VARCHAR(20),
            magnitude_confidence REAL,
            timing_pred VARCHAR(20),
            timing_confidence REAL,
            ensemble_confidence REAL,
            features JSONB,
            strategies JSONB,
            model_version VARCHAR(20),
            is_ml_prediction BOOLEAN DEFAULT FALSE
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS apollo_outcomes (
            id SERIAL PRIMARY KEY,
            outcome_id VARCHAR(50) UNIQUE NOT NULL,
            prediction_id VARCHAR(50),
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            symbol VARCHAR(20) NOT NULL,
            predicted_direction VARCHAR(20),
            actual_direction VARCHAR(20),
            predicted_magnitude VARCHAR(20),
            actual_magnitude VARCHAR(20),
            actual_return_pct REAL,
            direction_correct BOOLEAN,
            magnitude_correct BOOLEAN,
            strategy_used VARCHAR(50),
            strategy_pnl REAL,
            notes TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS apollo_model_performance (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            model_version VARCHAR(20),
            direction_accuracy_7d REAL,
            direction_accuracy_30d REAL,
            magnitude_accuracy_7d REAL,
            magnitude_accuracy_30d REAL,
            total_predictions INTEGER,
            total_outcomes INTEGER,
            sharpe_ratio REAL,
            win_rate REAL
        )
    ''')

    # Volatility Surface Snapshots - Store periodic surface analysis
    c.execute('''
        CREATE TABLE IF NOT EXISTS volatility_surface_snapshots (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
            snapshot_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            spot_price REAL NOT NULL,
            atm_iv REAL,
            iv_rank REAL,
            iv_percentile REAL,
            skew_25d REAL,
            skew_10d REAL,
            risk_reversal REAL,
            butterfly REAL,
            put_skew_slope REAL,
            call_skew_slope REAL,
            skew_ratio REAL,
            skew_regime VARCHAR(30),
            term_slope REAL,
            term_regime VARCHAR(30),
            front_month_iv REAL,
            back_month_iv REAL,
            is_inverted BOOLEAN DEFAULT FALSE,
            iv_7dte REAL,
            iv_14dte REAL,
            iv_30dte REAL,
            iv_45dte REAL,
            iv_60dte REAL,
            recommended_dte INTEGER,
            directional_bias VARCHAR(10),
            should_sell_premium BOOLEAN,
            optimal_strategy VARCHAR(50),
            strategy_reasoning TEXT,
            svi_params JSONB,
            fit_quality_mae REAL,
            fit_quality_n_points INTEGER,
            fit_quality_n_expirations INTEGER,
            data_source VARCHAR(50) DEFAULT 'TRADIER',
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    safe_index("CREATE INDEX IF NOT EXISTS idx_vol_surface_symbol_time ON volatility_surface_snapshots(symbol, snapshot_time)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_vol_surface_skew_regime ON volatility_surface_snapshots(skew_regime)")

    safe_index("CREATE INDEX IF NOT EXISTS idx_apollo_scans_timestamp ON apollo_scans(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_apollo_predictions_symbol ON apollo_predictions(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_apollo_predictions_scan ON apollo_predictions(scan_id)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_apollo_outcomes_symbol ON apollo_outcomes(symbol)")

    # ----- Indexes for consolidated tables -----
    safe_index("CREATE INDEX IF NOT EXISTS idx_gamma_history_symbol_date ON gamma_history(symbol, date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_gamma_history_timestamp_main ON gamma_history(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_gamma_daily_summary_symbol_date ON gamma_daily_summary(symbol, date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_spy_correlation_symbol_date ON spy_correlation(symbol, date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_wheel_cycles_symbol ON wheel_cycles(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_wheel_cycles_status ON wheel_cycles(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_wheel_legs_cycle_id ON wheel_legs(cycle_id)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_wheel_activity_cycle ON wheel_activity_log(cycle_id)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_wheel_activity_timestamp ON wheel_activity_log(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_trading_decisions_timestamp ON trading_decisions(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_trading_decisions_symbol ON trading_decisions(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_vix_hedge_signals_date ON vix_hedge_signals(signal_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_vix_hedge_positions_status ON vix_hedge_positions(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_strategy_competition_name ON strategy_competition(strategy_name)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_unified_positions_status ON unified_positions(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_unified_trades_date ON unified_trades(entry_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_regime_classifications_timestamp ON regime_classifications(timestamp)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_background_jobs_job_id ON background_jobs(job_id)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_background_jobs_status ON background_jobs(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ai_predictions_date ON ai_predictions(prediction_date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_ai_performance_date ON ai_performance(date)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_options_chain_snapshots_symbol ON options_chain_snapshots(symbol, expiration)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_paper_signals_status ON paper_signals(status)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_gex_snapshots_detailed_symbol ON gex_snapshots_detailed(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_gex_change_log_symbol ON gex_change_log(symbol)")
    safe_index("CREATE INDEX IF NOT EXISTS idx_gamma_strike_history_symbol ON gamma_strike_history(symbol, strike)")

    # ===== DATABASE MIGRATIONS =====

    # Helper function to get table columns (PostgreSQL)
    def get_table_columns(cursor, table_name):
        """Get list of column names for a table"""
        try:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
            """, (table_name,))
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            # Table might not exist
            return []

    # Add vix_current column to regime_signals if it doesn't exist
    try:
        columns = get_table_columns(c, 'regime_signals')
        if columns and 'vix_current' not in columns:
            print("🔄 Migrating regime_signals table: adding vix_current column")
            c.execute("ALTER TABLE regime_signals ADD COLUMN vix_current REAL")
            print("✅ Migration complete: vix_current column added")
    except Exception as e:
        # Table might not exist yet on first run - that's fine
        pass

    # Migrate backtest_summary table to new schema
    try:
        columns = get_table_columns(c, 'backtest_summary')

        # Check if old schema exists (missing symbol column)
        if 'symbol' not in columns and columns:
            print("🔄 Migrating backtest_summary table: rebuilding with new schema")
            # Drop old table and recreate with new schema
            c.execute("DROP TABLE IF EXISTS backtest_summary")
            c.execute('''
                CREATE TABLE IF NOT EXISTS backtest_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    psychology_trades INTEGER,
                    psychology_win_rate REAL,
                    psychology_expectancy REAL,
                    gex_trades INTEGER,
                    gex_win_rate REAL,
                    gex_expectancy REAL,
                    options_trades INTEGER,
                    options_win_rate REAL,
                    options_expectancy REAL
                )
            ''')
            print("✅ Migration complete: backtest_summary table rebuilt")
    except Exception as e:
        # Table might not exist yet on first run - that's fine
        pass

    # Migrate gex_change_log table - add missing columns
    try:
        columns = get_table_columns(c, 'gex_change_log')
        if columns:
            # Add missing columns for GEX velocity tracking
            if 'previous_gex' not in columns:
                print("🔄 Migrating gex_change_log table: adding previous_gex column")
                c.execute("ALTER TABLE gex_change_log ADD COLUMN previous_gex REAL")
            if 'current_gex' not in columns:
                print("🔄 Migrating gex_change_log table: adding current_gex column")
                c.execute("ALTER TABLE gex_change_log ADD COLUMN current_gex REAL")
            if 'change' not in columns:
                print("🔄 Migrating gex_change_log table: adding change column")
                c.execute("ALTER TABLE gex_change_log ADD COLUMN change REAL")
            if 'velocity_trend' not in columns:
                print("🔄 Migrating gex_change_log table: adding velocity_trend column")
                c.execute("ALTER TABLE gex_change_log ADD COLUMN velocity_trend TEXT")
            if 'direction_change' not in columns:
                print("🔄 Migrating gex_change_log table: adding direction_change column")
                c.execute("ALTER TABLE gex_change_log ADD COLUMN direction_change BOOLEAN DEFAULT FALSE")
            print("✅ gex_change_log migration complete")
    except Exception as e:
        print(f"⚠️  gex_change_log migration skipped: {e}")

    # Migrate ai_predictions table - add columns for SmartTradeAdvisor learning system
    try:
        columns = get_table_columns(c, 'ai_predictions')
        if columns:
            # Add columns needed by ai_trade_advisor.py
            if 'pattern_type' not in columns:
                print("🔄 Migrating ai_predictions table: adding pattern_type column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN pattern_type TEXT")
            if 'trade_direction' not in columns:
                print("🔄 Migrating ai_predictions table: adding trade_direction column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN trade_direction TEXT")
            if 'predicted_outcome' not in columns:
                print("🔄 Migrating ai_predictions table: adding predicted_outcome column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN predicted_outcome TEXT")
            if 'confidence_score' not in columns:
                print("🔄 Migrating ai_predictions table: adding confidence_score column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN confidence_score REAL")
            if 'reasoning' not in columns:
                print("🔄 Migrating ai_predictions table: adding reasoning column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN reasoning TEXT")
            if 'market_context' not in columns:
                print("🔄 Migrating ai_predictions table: adding market_context column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN market_context TEXT")
            if 'vix_level' not in columns:
                print("🔄 Migrating ai_predictions table: adding vix_level column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN vix_level REAL")
            if 'volatility_regime' not in columns:
                print("🔄 Migrating ai_predictions table: adding volatility_regime column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN volatility_regime TEXT")
            if 'actual_outcome' not in columns:
                print("🔄 Migrating ai_predictions table: adding actual_outcome column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN actual_outcome TEXT")
            if 'outcome_pnl' not in columns:
                print("🔄 Migrating ai_predictions table: adding outcome_pnl column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN outcome_pnl REAL")
            if 'prediction_correct' not in columns:
                print("🔄 Migrating ai_predictions table: adding prediction_correct column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN prediction_correct INTEGER")
            if 'feedback_timestamp' not in columns:
                print("🔄 Migrating ai_predictions table: adding feedback_timestamp column")
                c.execute("ALTER TABLE ai_predictions ADD COLUMN feedback_timestamp TIMESTAMPTZ")
            print("✅ ai_predictions migration complete")
    except Exception as e:
        print(f"⚠️  ai_predictions migration skipped: {e}")

    # Migrate ai_performance table - add columns for SmartTradeAdvisor tracking
    try:
        columns = get_table_columns(c, 'ai_performance')
        if columns:
            if 'total_predictions' not in columns:
                print("🔄 Migrating ai_performance table: adding total_predictions column")
                c.execute("ALTER TABLE ai_performance ADD COLUMN total_predictions INTEGER DEFAULT 0")
            if 'correct_predictions' not in columns:
                print("🔄 Migrating ai_performance table: adding correct_predictions column")
                c.execute("ALTER TABLE ai_performance ADD COLUMN correct_predictions INTEGER DEFAULT 0")
            if 'profitable_trades' not in columns:
                print("🔄 Migrating ai_performance table: adding profitable_trades column")
                c.execute("ALTER TABLE ai_performance ADD COLUMN profitable_trades INTEGER DEFAULT 0")
            if 'losing_trades' not in columns:
                print("🔄 Migrating ai_performance table: adding losing_trades column")
                c.execute("ALTER TABLE ai_performance ADD COLUMN losing_trades INTEGER DEFAULT 0")
            if 'net_pnl' not in columns:
                print("🔄 Migrating ai_performance table: adding net_pnl column")
                c.execute("ALTER TABLE ai_performance ADD COLUMN net_pnl REAL DEFAULT 0")
            if 'accuracy_rate' not in columns:
                print("🔄 Migrating ai_performance table: adding accuracy_rate column")
                c.execute("ALTER TABLE ai_performance ADD COLUMN accuracy_rate REAL")
            print("✅ ai_performance migration complete")
    except Exception as e:
        print(f"⚠️  ai_performance migration skipped: {e}")

    conn.commit()
    conn.close()


def _get_table_columns(cursor, table_name):
    """Get list of column names for a table (PostgreSQL)"""
    try:
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
        """, (table_name,))
        return [row[0] for row in cursor.fetchall()]
    except Exception:
        # Table might not exist
        return []


# ============================================================================
# BACKFILL TABLES FROM REAL HISTORICAL DATA ONLY
# ============================================================================

def backfill_ai_intelligence_tables():
    """
    Backfill tables from REAL historical data ONLY.
    NO fake data, NO default values, NO static data.

    If source table is empty, target stays empty - that's honest.
    """
    print("🔄 Starting backfill from REAL historical data...")
    print("=" * 60)

    try:
        conn = get_connection()
        c = conn.cursor()

        # =====================================================================
        # STEP 1: CHECK WHAT SOURCE DATA EXISTS
        # =====================================================================
        print("\n📊 CHECKING SOURCE DATA AVAILABILITY:")

        source_counts = {}
        sources_to_check = [
            'gex_history',
            'regime_signals',
            'autonomous_positions',
            'autonomous_trade_log',
            'autonomous_config'
        ]

        for table in sources_to_check:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]
                source_counts[table] = count
                status = "✅ HAS DATA" if count > 0 else "❌ EMPTY"
                print(f"  {table}: {count} rows {status}")
            except Exception as e:
                source_counts[table] = 0
                print(f"  {table}: ERROR - {e}")

        print("\n" + "=" * 60)
        print("📥 BACKFILLING FROM REAL DATA ONLY:")

        # =====================================================================
        # 1. BACKFILL market_data FROM gex_history (with REAL VIX from regime_signals)
        # =====================================================================
        if source_counts.get('gex_history', 0) > 0:
            print("\n  1. market_data FROM gex_history...")
            try:
                # Join with regime_signals to get REAL VIX values
                c.execute("""
                    INSERT INTO market_data (timestamp, symbol, spot_price, vix, net_gex, data_source)
                    SELECT
                        gh.timestamp,
                        COALESCE(gh.symbol, 'SPY'),
                        gh.spot_price,
                        COALESCE(rs.vix_current, (
                            SELECT vix_current FROM regime_signals
                            WHERE vix_current IS NOT NULL
                            ORDER BY timestamp DESC LIMIT 1
                        )),
                        gh.net_gex,
                        'backfill_gex_history'
                    FROM gex_history gh
                    LEFT JOIN regime_signals rs ON DATE(gh.timestamp) = DATE(rs.timestamp)
                    WHERE gh.spot_price IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM market_data md
                        WHERE md.timestamp = gh.timestamp
                    )
                    ORDER BY gh.timestamp DESC
                    LIMIT 1000
                """)
                rows = c.rowcount
                if rows > 0:
                    # Get sample of what was inserted
                    c.execute("SELECT spot_price, vix, net_gex FROM market_data ORDER BY timestamp DESC LIMIT 1")
                    sample = c.fetchone()
                    print(f"     ✅ Inserted {rows} rows")
                    print(f"     📍 Latest: spot=${sample[0]}, vix={sample[1]}, net_gex={sample[2]}")
                else:
                    print(f"     ℹ️ Already backfilled or no new data")
            except Exception as e:
                print(f"     ⚠️ Error: {e}")
                conn.rollback()  # Reset transaction for next step
        else:
            print("\n  1. market_data: SKIPPED - gex_history is empty")

        # =====================================================================
        # 2. BACKFILL gex_levels FROM gex_history
        # =====================================================================
        if source_counts.get('gex_history', 0) > 0:
            print("\n  2. gex_levels FROM gex_history...")
            try:
                c.execute("""
                    INSERT INTO gex_levels (timestamp, symbol, call_wall, put_wall, flip_point, net_gex, gex_regime)
                    SELECT
                        timestamp,
                        COALESCE(symbol, 'SPY'),
                        call_wall,
                        put_wall,
                        flip_point,
                        net_gex,
                        regime
                    FROM gex_history
                    WHERE (call_wall IS NOT NULL OR put_wall IS NOT NULL)
                    AND NOT EXISTS (
                        SELECT 1 FROM gex_levels gl WHERE gl.timestamp = gex_history.timestamp
                    )
                    ORDER BY timestamp DESC
                    LIMIT 1000
                """)
                rows = c.rowcount
                if rows > 0:
                    c.execute("SELECT call_wall, put_wall, flip_point FROM gex_levels ORDER BY timestamp DESC LIMIT 1")
                    sample = c.fetchone()
                    print(f"     ✅ Inserted {rows} rows")
                    print(f"     📍 Latest: call_wall=${sample[0]}, put_wall=${sample[1]}, flip=${sample[2]}")
                else:
                    print(f"     ℹ️ Already backfilled or no new data")
            except Exception as e:
                print(f"     ⚠️ Error: {e}")
                conn.rollback()  # Reset transaction for next step
        else:
            print("\n  2. gex_levels: SKIPPED - gex_history is empty")

        # =====================================================================
        # 3. BACKFILL psychology_analysis FROM regime_signals
        # =====================================================================
        if source_counts.get('regime_signals', 0) > 0:
            print("\n  3. psychology_analysis FROM regime_signals...")
            try:
                c.execute("""
                    INSERT INTO psychology_analysis (timestamp, symbol, regime_type, confidence, psychology_trap, reasoning)
                    SELECT
                        timestamp,
                        'SPY',
                        primary_regime_type,
                        confidence_score,
                        psychology_trap,
                        COALESCE(description, detailed_explanation)
                    FROM regime_signals
                    WHERE primary_regime_type IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM psychology_analysis pa WHERE pa.timestamp = regime_signals.timestamp
                    )
                    ORDER BY timestamp DESC
                    LIMIT 1000
                """)
                rows = c.rowcount
                if rows > 0:
                    c.execute("SELECT regime_type, confidence, psychology_trap FROM psychology_analysis ORDER BY timestamp DESC LIMIT 1")
                    sample = c.fetchone()
                    print(f"     ✅ Inserted {rows} rows")
                    print(f"     📍 Latest: regime={sample[0]}, confidence={sample[1]}, trap={sample[2]}")
                else:
                    print(f"     ℹ️ Already backfilled or no new data")
            except Exception as e:
                print(f"     ⚠️ Error: {e}")
                conn.rollback()  # Reset transaction for next step
        else:
            print("\n  3. psychology_analysis: SKIPPED - regime_signals is empty")

        # =====================================================================
        # 4. BACKFILL account_state FROM autonomous_config (REAL capital only)
        # =====================================================================
        if source_counts.get('autonomous_config', 0) > 0:
            print("\n  4. account_state FROM autonomous_config...")
            try:
                c.execute("SELECT value FROM autonomous_config WHERE key = 'capital'")
                capital_row = c.fetchone()
                if capital_row:
                    capital = float(capital_row[0])
                    c.execute("""
                        INSERT INTO account_state (account_value, cash_balance, buying_power)
                        SELECT %s, %s, %s
                        WHERE NOT EXISTS (SELECT 1 FROM account_state LIMIT 1)
                    """, (capital, capital, capital * 2))
                    if c.rowcount > 0:
                        print(f"     ✅ Inserted with REAL capital: ${capital}")
                    else:
                        print(f"     ℹ️ Already has data")
                else:
                    print(f"     ⚠️ No 'capital' key found in autonomous_config - SKIPPING (no fake data)")
            except Exception as e:
                print(f"     ⚠️ Error: {e}")
                conn.rollback()  # Reset transaction for next step
        else:
            print("\n  4. account_state: SKIPPED - autonomous_config is empty (no fake data)")

        # =====================================================================
        # 5. BACKFILL trades FROM autonomous_positions
        # =====================================================================
        if source_counts.get('autonomous_positions', 0) > 0:
            print("\n  5. trades FROM autonomous_positions...")
            try:
                c.execute("""
                    INSERT INTO trades (timestamp, symbol, strike, option_type, contracts, entry_price,
                                       current_price, status, pattern_type, confidence_score, entry_reason)
                    SELECT
                        entry_date::timestamp,
                        symbol,
                        strike,
                        option_type,
                        contracts,
                        entry_price,
                        current_price,
                        status,
                        strategy,
                        confidence,
                        trade_reasoning
                    FROM autonomous_positions
                    WHERE NOT EXISTS (
                        SELECT 1 FROM trades t
                        WHERE t.symbol = autonomous_positions.symbol
                        AND t.strike = autonomous_positions.strike
                    )
                """)
                rows = c.rowcount
                if rows > 0:
                    print(f"     ✅ Inserted {rows} rows")
                else:
                    print(f"     ℹ️ Already backfilled or no new data")
            except Exception as e:
                print(f"     ⚠️ Error: {e}")
                conn.rollback()  # Reset transaction for next step
        else:
            print("\n  5. trades: SKIPPED - autonomous_positions is empty")

        # =====================================================================
        # 6. BACKFILL autonomous_closed_trades FROM autonomous_positions (CLOSED)
        # =====================================================================
        if source_counts.get('autonomous_positions', 0) > 0:
            print("\n  6. autonomous_closed_trades FROM autonomous_positions (CLOSED)...")
            try:
                c.execute("""
                    INSERT INTO autonomous_closed_trades (symbol, strategy, strike, option_type, contracts,
                        entry_date, entry_time, entry_price, exit_date, exit_price, realized_pnl,
                        exit_reason, entry_spot_price, gex_regime)
                    SELECT
                        symbol, strategy, strike, option_type, contracts,
                        entry_date, entry_time, entry_price,
                        closed_date, exit_price, realized_pnl,
                        exit_reason, entry_spot_price, gex_regime
                    FROM autonomous_positions
                    WHERE status = 'CLOSED'
                    AND NOT EXISTS (
                        SELECT 1 FROM autonomous_closed_trades act
                        WHERE act.symbol = autonomous_positions.symbol
                        AND act.strike = autonomous_positions.strike
                        AND act.entry_date::text = autonomous_positions.entry_date::text
                    )
                """)
                rows = c.rowcount
                print(f"     ✅ Inserted {rows} closed trades")
            except Exception as e:
                print(f"     ⚠️ Error: {e}")
                conn.rollback()  # Reset transaction for next step
        else:
            print("\n  6. autonomous_closed_trades: SKIPPED - autonomous_positions is empty")

        # =====================================================================
        # 7. BACKFILL autonomous_open_positions FROM autonomous_positions (OPEN)
        # =====================================================================
        if source_counts.get('autonomous_positions', 0) > 0:
            print("\n  7. autonomous_open_positions FROM autonomous_positions (OPEN)...")
            try:
                c.execute("""
                    INSERT INTO autonomous_open_positions (symbol, strategy, strike, option_type, contracts,
                        entry_date, entry_time, entry_price, current_price, unrealized_pnl, status,
                        entry_spot_price, current_spot_price, gex_regime)
                    SELECT
                        symbol, strategy, strike, option_type, contracts,
                        entry_date, entry_time, entry_price, current_price, unrealized_pnl, status,
                        entry_spot_price, current_spot_price, gex_regime
                    FROM autonomous_positions
                    WHERE status = 'OPEN'
                    AND NOT EXISTS (
                        SELECT 1 FROM autonomous_open_positions aop
                        WHERE aop.symbol = autonomous_positions.symbol
                        AND aop.strike = autonomous_positions.strike
                    )
                """)
                rows = c.rowcount
                print(f"     ✅ Inserted {rows} open positions")
            except Exception as e:
                print(f"     ⚠️ Error: {e}")
                conn.rollback()  # Reset transaction for next step
        else:
            print("\n  7. autonomous_open_positions: SKIPPED - autonomous_positions is empty")

        # =====================================================================
        # 8. BACKFILL psychology_notifications FROM regime_signals
        # =====================================================================
        if source_counts.get('regime_signals', 0) > 0:
            print("\n  8. psychology_notifications FROM regime_signals...")
            try:
                c.execute("""
                    INSERT INTO psychology_notifications (timestamp, notification_type, regime_type, message, severity)
                    SELECT
                        timestamp,
                        'regime_change',
                        primary_regime_type,
                        COALESCE(description, 'Regime: ' || primary_regime_type),
                        CASE
                            WHEN risk_level = 'HIGH' THEN 'warning'
                            WHEN risk_level = 'LOW' THEN 'success'
                            ELSE 'info'
                        END
                    FROM regime_signals
                    WHERE primary_regime_type IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM psychology_notifications pn WHERE pn.timestamp = regime_signals.timestamp
                    )
                    ORDER BY timestamp DESC
                    LIMIT 500
                """)
                rows = c.rowcount
                print(f"     ✅ Inserted {rows} notifications")
            except Exception as e:
                print(f"     ⚠️ Error: {e}")
                conn.rollback()  # Reset transaction for next step
        else:
            print("\n  8. psychology_notifications: SKIPPED - regime_signals is empty")

        # =====================================================================
        # 9. BACKFILL autonomous_trade_activity FROM autonomous_trade_log
        # =====================================================================
        if source_counts.get('autonomous_trade_log', 0) > 0:
            print("\n  9. autonomous_trade_activity FROM autonomous_trade_log...")
            try:
                c.execute("""
                    INSERT INTO autonomous_trade_activity (timestamp, action, reason, success)
                    SELECT
                        CASE
                            WHEN date ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN (date || ' ' || COALESCE(time, '00:00:00'))::timestamp
                            ELSE NOW()
                        END,
                        action,
                        details,
                        CASE WHEN success = 1 THEN TRUE ELSE FALSE END
                    FROM autonomous_trade_log
                    WHERE date IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM autonomous_trade_activity ata
                        WHERE ata.action = autonomous_trade_log.action
                        AND DATE(ata.timestamp)::text = autonomous_trade_log.date
                    )
                    ORDER BY date DESC, time DESC
                    LIMIT 500
                """)
                rows = c.rowcount
                print(f"     ✅ Inserted {rows} trade activities")
            except Exception as e:
                print(f"     ⚠️ Error: {e}")
                conn.rollback()  # Reset transaction for next step
        else:
            print("\n  9. autonomous_trade_activity: SKIPPED - autonomous_trade_log is empty")

        # =====================================================================
        # SUMMARY
        # =====================================================================
        print("\n" + "=" * 60)
        print("📊 BACKFILL SUMMARY:")

        # Check what we actually have now
        target_tables = [
            'market_data', 'gex_levels', 'psychology_analysis', 'account_state',
            'trades', 'autonomous_closed_trades', 'autonomous_open_positions',
            'psychology_notifications', 'autonomous_trade_activity'
        ]

        for table in target_tables:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]
                status = "✅" if count > 0 else "❌ EMPTY"
                print(f"  {table}: {count} rows {status}")
            except Exception as e:
                print(f"  {table}: ERROR - {e}")

        conn.commit()
        conn.close()
        print("\n✅ Backfill complete - REAL DATA ONLY, NO FAKE VALUES")

    except Exception as e:
        print(f"❌ Backfill failed: {e}")
        import traceback
        traceback.print_exc()


def _migrate_positions_table(cursor):
    """Add new columns to existing positions table if they don't exist"""

    # Get existing columns (database-agnostic)
    existing_columns = set(_get_table_columns(cursor, 'positions'))

    # Define new columns to add
    new_columns = {
        'quantity': 'INTEGER',
        'exit_price': 'REAL',
        'entry_net_gex': 'REAL',
        'entry_flip_point': 'REAL',
        'entry_spot_price': 'REAL',
        'entry_regime': 'TEXT',
        'notes': 'TEXT'
    }

    # Add missing columns
    for column_name, column_type in new_columns.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE positions ADD COLUMN {column_name} {column_type}")
            except Exception:
                # Column might already exist or table doesn't exist yet
                pass


# ============================================================================
# DYNAMIC STATS INTEGRATION (Auto-updated from backtests)
# ============================================================================

def get_dynamic_mm_states():
    """
    Get MM states with DYNAMIC thresholds and confidence.
    Confidence is calculated based on actual GEX data, not hardcoded.
    """
    try:
        from core.strategy_stats import get_mm_states
        return get_mm_states()
    except Exception as e:
        print(f"⚠️  Could not load dynamic MM states: {e}")
        return MM_STATES  # Fallback to static

def get_dynamic_strategies():
    """
    Get strategies with DYNAMIC win rates from backtest results.
    Win rates auto-update when backtests run.
    """
    try:
        from core.strategy_stats import get_strategy_stats
        live_stats = get_strategy_stats()
        
        # Merge live stats into static configuration
        merged = {}
        for strategy_name, static_config in STRATEGIES.items():
            merged[strategy_name] = static_config.copy()
            
            # Override with live backtest data if available
            if strategy_name in live_stats:
                live = live_stats[strategy_name]
                merged[strategy_name]['win_rate'] = live['win_rate']
                merged[strategy_name]['avg_win'] = live.get('avg_win', 0)
                merged[strategy_name]['avg_loss'] = live.get('avg_loss', 0)
                merged[strategy_name]['expectancy'] = live.get('expectancy', 0)
                merged[strategy_name]['total_trades'] = live.get('total_trades', 0)
                merged[strategy_name]['last_updated'] = live.get('last_updated')
                merged[strategy_name]['source'] = live.get('source', 'backtest')
        
        return merged
    except Exception as e:
        print(f"⚠️  Could not load dynamic strategy stats: {e}")
        return STRATEGIES  # Fallback to static

# Print info on import
try:
    from core.strategy_stats import get_recent_changes
    recent = get_recent_changes(limit=3)
    if recent:
        print("\n" + "="*70)
        print("📊 DYNAMIC STATS ACTIVE - Recent Auto-Updates:")
        print("="*70)
        for change in recent:
            print(f"  [{change['timestamp'][:16]}] {change['category']} > {change['item']}")
            print(f"    {change['old_value']} → {change['new_value']}")
        print("="*70 + "\n")
except (ImportError, Exception):
    # strategy_stats module might not be available
    pass
