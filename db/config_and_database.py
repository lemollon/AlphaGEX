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
CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # Haiku 4.5 (Oct 2025) - Fast, cheap, great for analysis

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

    # ===== BACKTEST RESULTS TABLES =====

    # Backtest results for all strategies
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
    # These indexes significantly speed up queries by symbol, date, and status
    c.execute("CREATE INDEX IF NOT EXISTS idx_gex_history_symbol ON gex_history(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_gex_history_timestamp ON gex_history(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_recommendations_symbol ON recommendations(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_recommendations_timestamp ON recommendations(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_positions_closed_at ON positions(closed_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_performance_date ON performance(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp)")

    # Psychology trap detection indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_regime_signals_timestamp ON regime_signals(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_regime_signals_type ON regime_signals(primary_regime_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_regime_signals_liberation ON regime_signals(liberation_setup_detected, liberation_expiry_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_regime_signals_false_floor ON regime_signals(false_floor_detected, false_floor_expiry_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_gamma_expiration_timeline_expiration ON gamma_expiration_timeline(expiration_date, strike)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_gamma_expiration_timeline_snapshot ON gamma_expiration_timeline(snapshot_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_historical_oi_date_strike ON historical_open_interest(date, strike, expiration_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_forward_magnets_snapshot_strike ON forward_magnets(snapshot_date, strike)")

    # Backtest indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy ON backtest_results(strategy_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_backtest_results_timestamp ON backtest_results(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_backtest_results_symbol ON backtest_results(symbol)")

    # Strategy Optimizer indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_strike_performance_strategy ON strike_performance(strategy_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_strike_performance_timestamp ON strike_performance(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_strike_performance_dte ON strike_performance(dte)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_strike_performance_moneyness ON strike_performance(moneyness)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_strike_performance_vix_regime ON strike_performance(vix_regime)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_strike_performance_win ON strike_performance(win)")

    c.execute("CREATE INDEX IF NOT EXISTS idx_spread_width_strategy ON spread_width_performance(strategy_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_spread_width_timestamp ON spread_width_performance(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_spread_width_type ON spread_width_performance(spread_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_spread_width_win ON spread_width_performance(win)")

    c.execute("CREATE INDEX IF NOT EXISTS idx_greeks_performance_strategy ON greeks_performance(strategy_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_greeks_performance_timestamp ON greeks_performance(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_greeks_performance_delta_target ON greeks_performance(delta_target)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_greeks_performance_win ON greeks_performance(win)")

    c.execute("CREATE INDEX IF NOT EXISTS idx_dte_performance_strategy ON dte_performance(strategy_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dte_performance_timestamp ON dte_performance(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dte_performance_bucket ON dte_performance(dte_bucket)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dte_performance_pattern ON dte_performance(pattern_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dte_performance_win ON dte_performance(win)")

    # Push notification indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_push_subscriptions_endpoint ON push_subscriptions(endpoint)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_push_subscriptions_created_at ON push_subscriptions(created_at)")

    # Autonomous trader logs indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_timestamp ON autonomous_trader_logs(timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_type ON autonomous_trader_logs(log_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_symbol ON autonomous_trader_logs(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_position ON autonomous_trader_logs(position_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_session ON autonomous_trader_logs(session_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_logs_pattern ON autonomous_trader_logs(pattern_detected)")

    # Autonomous positions indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_positions_status ON autonomous_positions(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_positions_symbol ON autonomous_positions(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_positions_entry_date ON autonomous_positions(entry_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_positions_strategy ON autonomous_positions(strategy)")

    # Autonomous trade log indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_trade_log_date ON autonomous_trade_log(date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_trade_log_action ON autonomous_trade_log(action)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_autonomous_trade_log_position_id ON autonomous_trade_log(position_id)")

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
        from strategy_stats import get_mm_states
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
        from strategy_stats import get_strategy_stats
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
    from strategy_stats import get_recent_changes
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
