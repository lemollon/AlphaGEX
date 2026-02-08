#!/usr/bin/env python3
"""
Apply Performance Indexes Migration (012)

This script safely applies database indexes to improve query performance.
All indexes use IF NOT EXISTS, so it's safe to run multiple times.

Usage:
    python scripts/apply_performance_indexes.py
    python scripts/apply_performance_indexes.py --verify-only
"""

import os
import sys
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_connection():
    """Get database connection."""
    try:
        from database_adapter import get_connection as db_get_connection
        return db_get_connection()
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)


def get_existing_indexes(conn):
    """Get list of existing indexes."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT indexname, tablename
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname LIKE 'idx_%'
        ORDER BY tablename, indexname
    """)
    return {row[0]: row[1] for row in cursor.fetchall()}


def apply_migration(conn, dry_run=False):
    """Apply the performance indexes migration."""
    migration_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'db', 'migrations', '012_performance_indexes.sql'
    )

    if not os.path.exists(migration_path):
        print(f"❌ Migration file not found: {migration_path}")
        return False

    with open(migration_path, 'r') as f:
        migration_sql = f.read()

    # Extract individual CREATE INDEX statements
    statements = []
    for line in migration_sql.split('\n'):
        line = line.strip()
        if line.startswith('CREATE INDEX IF NOT EXISTS'):
            # Find the full statement (may span multiple lines)
            statements.append(line)

    # Also handle multi-line statements
    current_statement = []
    in_statement = False
    for line in migration_sql.split('\n'):
        stripped = line.strip()
        if stripped.startswith('CREATE INDEX IF NOT EXISTS'):
            in_statement = True
            current_statement = [stripped]
        elif in_statement:
            current_statement.append(stripped)
            if ';' in stripped:
                statements.append(' '.join(current_statement))
                current_statement = []
                in_statement = False

    # Deduplicate
    seen = set()
    unique_statements = []
    for stmt in statements:
        if stmt not in seen and 'CREATE INDEX' in stmt:
            seen.add(stmt)
            unique_statements.append(stmt)

    if dry_run:
        print("\n📋 DRY RUN - Would execute the following statements:\n")
        for stmt in unique_statements:
            print(f"  {stmt[:80]}...")
        return True

    cursor = conn.cursor()
    success_count = 0
    skip_count = 0
    error_count = 0

    print("\n🔧 Applying performance indexes...\n")

    for stmt in unique_statements:
        # Extract index name for reporting
        try:
            idx_name = stmt.split('idx_')[1].split()[0]
            idx_name = f"idx_{idx_name}"
        except:
            idx_name = "unknown"

        try:
            cursor.execute(stmt)
            conn.commit()
            print(f"  ✅ Created: {idx_name}")
            success_count += 1
        except Exception as e:
            if 'already exists' in str(e).lower():
                print(f"  ⏭️  Exists:  {idx_name}")
                skip_count += 1
                conn.rollback()
            else:
                print(f"  ❌ Failed:  {idx_name} - {e}")
                error_count += 1
                conn.rollback()

    print(f"\n📊 Summary: {success_count} created, {skip_count} already existed, {error_count} errors")
    return error_count == 0


def verify_indexes(conn):
    """Verify all expected indexes exist."""
    expected_indexes = [
        # FORTRESS
        ('idx_fortress_positions_status', 'fortress_positions'),
        ('idx_fortress_positions_open_time', 'fortress_positions'),
        ('idx_fortress_positions_status_open_time', 'fortress_positions'),
        ('idx_fortress_positions_expiration', 'fortress_positions'),
        # SOLOMON
        ('idx_solomon_positions_status', 'solomon_positions'),
        ('idx_solomon_positions_open_time', 'solomon_positions'),
        ('idx_solomon_positions_status_open_time', 'solomon_positions'),
        ('idx_solomon_positions_expiration', 'solomon_positions'),
        # PEGASUS
        ('idx_pegasus_positions_status', 'pegasus_positions'),
        ('idx_pegasus_positions_open_time', 'pegasus_positions'),
        ('idx_pegasus_positions_status_open_time', 'pegasus_positions'),
        # GEX_HISTORY
        ('idx_gex_history_symbol_timestamp', 'gex_history'),
        ('idx_gex_history_timestamp', 'gex_history'),
        # AUTONOMOUS_CLOSED_TRADES
        ('idx_autonomous_closed_trades_created_at', 'autonomous_closed_trades'),
        ('idx_autonomous_closed_trades_exit_date', 'autonomous_closed_trades'),
        ('idx_autonomous_closed_trades_strategy', 'autonomous_closed_trades'),
        # AUTONOMOUS_POSITIONS
        ('idx_autonomous_positions_status', 'autonomous_positions'),
        ('idx_autonomous_positions_created_at', 'autonomous_positions'),
        ('idx_autonomous_positions_status_created', 'autonomous_positions'),
    ]

    existing = get_existing_indexes(conn)

    print("\n📋 Index Verification:\n")

    missing = []
    for idx_name, table_name in expected_indexes:
        if idx_name in existing:
            print(f"  ✅ {idx_name} on {table_name}")
        else:
            print(f"  ❌ {idx_name} on {table_name} - MISSING")
            missing.append((idx_name, table_name))

    if missing:
        print(f"\n⚠️  {len(missing)} indexes are missing!")
        return False
    else:
        print(f"\n✅ All {len(expected_indexes)} indexes verified!")
        return True


def main():
    parser = argparse.ArgumentParser(description='Apply performance indexes migration')
    parser.add_argument('--verify-only', action='store_true', help='Only verify indexes exist')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')
    args = parser.parse_args()

    print("=" * 60)
    print("AlphaGEX Performance Indexes Migration (012)")
    print("=" * 60)

    conn = get_connection()

    # Show existing indexes first
    existing = get_existing_indexes(conn)
    print(f"\n📊 Found {len(existing)} existing indexes")

    if args.verify_only:
        success = verify_indexes(conn)
    elif args.dry_run:
        success = apply_migration(conn, dry_run=True)
    else:
        success = apply_migration(conn)
        if success:
            verify_indexes(conn)

    conn.close()

    print("\n" + "=" * 60)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
