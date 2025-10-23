"""
config_and_database.py - Configuration, Constants, and Database Functions
"""

import sqlite3
from pathlib import Path
import streamlit as st

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# API Configuration
TRADINGVOLATILITY_BASE = "https://stocks.tradingvolatility.net/api"
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"

# Database Path
DB_PATH = Path("gex_copilot.db")

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
    'NEGATIVE_GEX_SQUEEZE': {
        'conditions': {
            'net_gex_threshold': -1e9,
            'distance_to_flip': 1.5,
            'min_put_wall_distance': 1.0
        },
        'win_rate': 0.68,
        'risk_reward': 3.0,
        'typical_move': '2-3% in direction',
        'best_days': ['Monday', 'Tuesday'],
        'entry': 'Break above flip point',
        'exit': 'Call wall or 100% profit'
    },
    'POSITIVE_GEX_BREAKDOWN': {
        'conditions': {
            'net_gex_threshold': 2e9,
            'proximity_to_flip': 0.3,
            'call_wall_rejection': True
        },
        'win_rate': 0.62,
        'risk_reward': 2.5,
        'typical_move': '1-2% down',
        'best_days': ['Wednesday', 'Thursday'],
        'entry': 'Break below flip point',
        'exit': 'Put wall or 75% profit'
    },
    'IRON_CONDOR': {
        'conditions': {
            'net_gex_threshold': 1e9,
            'min_wall_distance': 3.0,
            'iv_rank_below': 50
        },
        'win_rate': 0.72,
        'risk_reward': 0.3,
        'typical_move': 'Range bound',
        'best_days': ['Any with 5-10 DTE'],
        'entry': 'Short strikes at walls',
        'exit': '50% profit or breach'
    },
    'PREMIUM_SELLING': {
        'conditions': {
            'wall_strength': 500e6,
            'distance_from_wall': 1.0,
            'positive_gex': True
        },
        'win_rate': 0.65,
        'risk_reward': 0.5,
        'typical_move': 'Rejection at levels',
        'best_days': ['Any 0-2 DTE'],
        'entry': 'At wall approach',
        'exit': '50% profit or time'
    }
}

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_database():
    """Initialize comprehensive database schema"""
    conn = sqlite3.connect(DB_PATH)
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
    
    # Migrate existing databases to add new columns
    _migrate_positions_table(c)

    conn.commit()
    conn.close()


def _migrate_positions_table(cursor):
    """Add new columns to existing positions table if they don't exist"""

    # Get existing columns
    cursor.execute("PRAGMA table_info(positions)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # Define new columns to add
    new_columns = {
        'quantity': 'INTEGER',
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
            except sqlite3.OperationalError:
                # Column might already exist or table doesn't exist yet
                pass
