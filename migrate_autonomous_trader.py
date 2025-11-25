#!/usr/bin/env python3
"""
Autonomous Trader Database Migration
=====================================
This script:
1. Backs up existing data (for reference)
2. Creates new proper tables for autonomous trading
3. Resets corrupted data and starts fresh

New Schema:
- autonomous_open_positions: Currently active trades
- autonomous_closed_trades: Historical trades with real P&L
- autonomous_equity_snapshots: Time series data for P&L graphing
- autonomous_trade_activity: All trader actions/decisions
"""

import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_adapter import get_connection


def run_migration():
    """Run the full migration"""
    print("\n" + "="*70)
    print("AUTONOMOUS TRADER DATABASE MIGRATION")
    print("="*70)

    conn = get_connection()
    c = conn.cursor()

    try:
        # Step 1: Backup existing data count (for reference)
        print("\n[1/6] Checking existing data...")
        try:
            c.execute("SELECT COUNT(*) FROM autonomous_positions")
            old_count = c.fetchone()[0]
            print(f"   Found {old_count} existing positions (will be archived)")
        except:
            old_count = 0
            print("   No existing positions table")

        # Step 2: Archive old tables (rename, don't delete)
        print("\n[2/6] Archiving old tables...")
        archive_tables = [
            'autonomous_positions',
            'autonomous_trade_log',
            'autonomous_config',
            'autonomous_live_status'
        ]

        for table in archive_tables:
            try:
                archive_name = f"{table}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                c.execute(f"ALTER TABLE {table} RENAME TO {archive_name}")
                print(f"   Archived: {table} -> {archive_name}")
            except Exception as e:
                print(f"   Skipped: {table} (may not exist)")

        conn.commit()

        # Step 3: Create new OPEN POSITIONS table
        print("\n[3/6] Creating autonomous_open_positions table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_open_positions (
                id SERIAL PRIMARY KEY,

                -- Trade identification
                symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
                strategy VARCHAR(100) NOT NULL,
                action VARCHAR(50) NOT NULL,

                -- Option details
                strike DECIMAL(10,2) NOT NULL,
                option_type VARCHAR(20) NOT NULL,
                expiration_date DATE NOT NULL,
                contracts INTEGER NOT NULL DEFAULT 1,
                contract_symbol VARCHAR(50),

                -- Entry details (CRITICAL - must be non-zero)
                entry_date DATE NOT NULL,
                entry_time TIME NOT NULL,
                entry_price DECIMAL(10,4) NOT NULL CHECK (entry_price > 0),
                entry_bid DECIMAL(10,4),
                entry_ask DECIMAL(10,4),
                entry_spot_price DECIMAL(10,2),
                entry_iv DECIMAL(6,4),
                entry_delta DECIMAL(6,4),

                -- Current values (updated in real-time)
                current_price DECIMAL(10,4),
                current_spot_price DECIMAL(10,2),
                current_iv DECIMAL(6,4),
                current_delta DECIMAL(6,4),
                last_updated TIMESTAMP DEFAULT NOW(),

                -- P&L tracking
                unrealized_pnl DECIMAL(12,2) DEFAULT 0,
                unrealized_pnl_pct DECIMAL(8,4) DEFAULT 0,

                -- Trade context
                confidence INTEGER CHECK (confidence >= 0 AND confidence <= 100),
                gex_regime VARCHAR(100),
                entry_net_gex DECIMAL(15,2),
                entry_flip_point DECIMAL(10,2),
                trade_reasoning TEXT,

                -- Timestamps
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("   Created autonomous_open_positions")

        # Step 4: Create CLOSED TRADES table
        print("\n[4/6] Creating autonomous_closed_trades table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_closed_trades (
                id SERIAL PRIMARY KEY,

                -- Trade identification
                symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
                strategy VARCHAR(100) NOT NULL,
                action VARCHAR(50) NOT NULL,

                -- Option details
                strike DECIMAL(10,2) NOT NULL,
                option_type VARCHAR(20) NOT NULL,
                expiration_date DATE NOT NULL,
                contracts INTEGER NOT NULL DEFAULT 1,
                contract_symbol VARCHAR(50),

                -- Entry details
                entry_date DATE NOT NULL,
                entry_time TIME NOT NULL,
                entry_price DECIMAL(10,4) NOT NULL,
                entry_bid DECIMAL(10,4),
                entry_ask DECIMAL(10,4),
                entry_spot_price DECIMAL(10,2),
                entry_iv DECIMAL(6,4),
                entry_delta DECIMAL(6,4),

                -- Exit details
                exit_date DATE NOT NULL,
                exit_time TIME NOT NULL,
                exit_price DECIMAL(10,4) NOT NULL,
                exit_spot_price DECIMAL(10,2),
                exit_reason VARCHAR(100),

                -- P&L (the real numbers!)
                realized_pnl DECIMAL(12,2) NOT NULL,
                realized_pnl_pct DECIMAL(8,4) NOT NULL,

                -- Trade context
                confidence INTEGER,
                gex_regime VARCHAR(100),
                entry_net_gex DECIMAL(15,2),
                entry_flip_point DECIMAL(10,2),
                trade_reasoning TEXT,

                -- Duration
                hold_duration_minutes INTEGER,

                -- Timestamps
                created_at TIMESTAMP DEFAULT NOW(),

                -- For performance analysis
                is_winner BOOLEAN GENERATED ALWAYS AS (realized_pnl > 0) STORED
            )
        """)
        print("   Created autonomous_closed_trades")

        # Step 5: Create EQUITY SNAPSHOTS table (for P&L time series graphing)
        print("\n[5/6] Creating autonomous_equity_snapshots table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_equity_snapshots (
                id SERIAL PRIMARY KEY,

                -- Timestamp
                snapshot_date DATE NOT NULL,
                snapshot_time TIME NOT NULL,
                snapshot_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

                -- Account values
                starting_capital DECIMAL(12,2) NOT NULL DEFAULT 5000,
                total_realized_pnl DECIMAL(12,2) NOT NULL DEFAULT 0,
                total_unrealized_pnl DECIMAL(12,2) NOT NULL DEFAULT 0,
                account_value DECIMAL(12,2) NOT NULL,

                -- Daily metrics
                daily_pnl DECIMAL(12,2) DEFAULT 0,
                daily_return_pct DECIMAL(8,4) DEFAULT 0,

                -- Performance metrics (calculated)
                total_return_pct DECIMAL(8,4) DEFAULT 0,
                max_drawdown_pct DECIMAL(8,4) DEFAULT 0,
                sharpe_ratio DECIMAL(8,4) DEFAULT 0,

                -- Position summary
                open_positions_count INTEGER DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                win_rate DECIMAL(6,4) DEFAULT 0,

                -- Unique constraint to prevent duplicate snapshots
                UNIQUE(snapshot_date, snapshot_time)
            )
        """)
        print("   Created autonomous_equity_snapshots")

        # Step 6: Create TRADE ACTIVITY table
        print("\n[6/6] Creating autonomous_trade_activity table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_trade_activity (
                id SERIAL PRIMARY KEY,

                -- Timestamp
                activity_date DATE NOT NULL,
                activity_time TIME NOT NULL,
                activity_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

                -- Activity type
                action_type VARCHAR(50) NOT NULL,
                -- Types: SCAN, ANALYSIS, ENTRY, EXIT, ERROR, WARNING, RISK_CHECK, SKIP

                -- Details
                symbol VARCHAR(10) DEFAULT 'SPY',
                details TEXT,

                -- Associated position (if any)
                position_id INTEGER,

                -- P&L impact (if any)
                pnl_impact DECIMAL(12,2),

                -- Status
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT
            )
        """)
        print("   Created autonomous_trade_activity")

        # Create indexes for performance
        print("\n[+] Creating indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_open_positions_status ON autonomous_open_positions(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_closed_trades_date ON autonomous_closed_trades(exit_date)",
            "CREATE INDEX IF NOT EXISTS idx_closed_trades_strategy ON autonomous_closed_trades(strategy)",
            "CREATE INDEX IF NOT EXISTS idx_equity_snapshots_date ON autonomous_equity_snapshots(snapshot_date)",
            "CREATE INDEX IF NOT EXISTS idx_trade_activity_date ON autonomous_trade_activity(activity_date)",
            "CREATE INDEX IF NOT EXISTS idx_trade_activity_type ON autonomous_trade_activity(action_type)"
        ]

        for idx in indexes:
            try:
                c.execute(idx)
            except Exception as e:
                pass  # Index may already exist

        # Create config table fresh
        print("\n[+] Creating config table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_config (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Initialize config with starting values
        c.execute("""
            INSERT INTO autonomous_config (key, value) VALUES
            ('capital', '5000'),
            ('starting_capital', '5000'),
            ('initialized', 'true'),
            ('mode', 'paper'),
            ('auto_execute', 'true'),
            ('last_reset_date', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (datetime.now().strftime('%Y-%m-%d'),))

        # Create live status table
        print("\n[+] Creating live status table...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_live_status (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                timestamp TIMESTAMP DEFAULT NOW(),
                status VARCHAR(50) DEFAULT 'IDLE',
                current_action TEXT,
                market_analysis TEXT,
                next_check_time TIMESTAMP,
                last_decision TEXT,
                is_working BOOLEAN DEFAULT FALSE
            )
        """)

        # Insert initial live status
        c.execute("""
            INSERT INTO autonomous_live_status (id, status, current_action, last_decision)
            VALUES (1, 'READY', 'System reset - ready for trading', 'Fresh start with corrected data capture')
            ON CONFLICT (id) DO UPDATE SET
                status = 'READY',
                current_action = 'System reset - ready for trading',
                last_decision = 'Fresh start with corrected data capture',
                timestamp = NOW()
        """)

        # Create initial equity snapshot
        print("\n[+] Creating initial equity snapshot...")
        c.execute("""
            INSERT INTO autonomous_equity_snapshots (
                snapshot_date, snapshot_time, snapshot_timestamp,
                starting_capital, total_realized_pnl, total_unrealized_pnl,
                account_value, daily_pnl, total_return_pct,
                open_positions_count, total_trades, win_rate
            ) VALUES (
                CURRENT_DATE, CURRENT_TIME, NOW(),
                5000, 0, 0,
                5000, 0, 0,
                0, 0, 0
            )
        """)

        conn.commit()

        print("\n" + "="*70)
        print("MIGRATION COMPLETE!")
        print("="*70)
        print(f"""
Summary:
- Archived {old_count} old positions (data preserved in backup tables)
- Created 4 new tables:
  1. autonomous_open_positions  - Active trades with validated entry prices
  2. autonomous_closed_trades   - Completed trades with real P&L
  3. autonomous_equity_snapshots - Time series for P&L graphing
  4. autonomous_trade_activity  - All trader actions/decisions
- Initialized with $5,000 starting capital
- Ready for fresh trading with proper data capture

Next Steps:
1. Restart the autonomous trader
2. New trades will have proper entry prices
3. P&L will be calculated correctly
""")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: Migration failed - {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
