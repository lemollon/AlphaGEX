#!/usr/bin/env python3
"""
Database Query Helper for AlphaGEX PostgreSQL Database

Usage:
    python query_database.py                    # Show all tables and counts
    python query_database.py --table regime_signals   # Show specific table
    python query_database.py --schema regime_signals  # Show table structure
    python query_database.py --query "SELECT * FROM regime_signals LIMIT 5"  # Custom query
"""

import sys
import argparse
import json
from database_adapter import get_connection


def show_all_tables():
    """Show all tables with row counts"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = cursor.fetchall()

    print("=" * 100)
    print("DATABASE: PostgreSQL via DATABASE_URL")
    print(f"TOTAL TABLES: {len(tables)}")
    print("=" * 100)
    print(f"{'STATUS':<15} {'TABLE NAME':<40} {'ROWS':<15}")
    print("-" * 100)

    total_rows = 0
    populated_count = 0

    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        total_rows += count

        if count > 0:
            status = "O POPULATED"
            populated_count += 1
        else:
            status = "X EMPTY"

        print(f"{status:<15} {table_name:<40} {count:>10,}")

    print("-" * 100)
    print(f"Populated: {populated_count}/{len(tables)} tables | Total Rows: {total_rows:,}")
    print("=" * 100)

    conn.close()


def show_table_schema(table_name):
    """Show table schema"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT ordinal_position, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        columns = cursor.fetchall()

        if not columns:
            print(f"❌ Table '{table_name}' not found")
            conn.close()
            return

        print("=" * 100)
        print(f"TABLE: {table_name}")
        print(f"COLUMNS: {len(columns)}")
        print("=" * 100)
        print(f"{'#':<5} {'COLUMN NAME':<30} {'TYPE':<20} {'NULLABLE':<10} {'DEFAULT':<15}")
        print("-" * 100)

        for col in columns:
            col_id, name, col_type, nullable, default_val = col
            nullable_str = "YES" if nullable == 'YES' else "NO"
            default_str = str(default_val)[:15] if default_val else ""
            print(f"{col_id:<5} {name:<30} {col_type:<20} {nullable_str:<10} {default_str:<15}")

        print("=" * 100)

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()


def show_table_data(table_name, limit=10):
    """Show table data"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = cursor.fetchone()[0]

        if total_rows == 0:
            print(f"⚠️  Table '{table_name}' is empty (0 rows)")
            return

        # Get column names
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        columns = [col[0] for col in cursor.fetchall()]

        # Get data
        cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
        rows = cursor.fetchall()

        print("=" * 100)
        print(f"TABLE: {table_name}")
        print(f"TOTAL ROWS: {total_rows:,} | SHOWING: {len(rows)} rows")
        print("=" * 100)

        # Print as JSON for readability
        for idx, row in enumerate(rows, 1):
            row_dict = dict(zip(columns, row))
            print(f"\n--- Row {idx} ---")
            for key, value in row_dict.items():
                # Truncate long values
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                print(f"  {key}: {value}")

        print("=" * 100)

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()


def run_custom_query(query):
    """Run custom SQL query"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(query)

        if query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()

            # Get column names from cursor description
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            print("=" * 100)
            print(f"QUERY: {query}")
            print(f"RESULTS: {len(rows)} rows")
            print("=" * 100)

            if len(rows) == 0:
                print("No results")
            else:
                # Print header
                header = " | ".join(f"{col:<20}" for col in columns)
                print(header)
                print("-" * len(header))

                # Print rows
                for row in rows:
                    row_str = " | ".join(f"{str(val)[:20]:<20}" for val in row)
                    print(row_str)

            print("=" * 100)
        else:
            conn.commit()
            print(f"✅ Query executed successfully (affected {cursor.rowcount} rows)")

    except Exception as e:
        print(f"❌ SQL Error: {e}")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="AlphaGEX Database Query Helper")
    parser.add_argument('--table', '-t', help='Show data from specific table')
    parser.add_argument('--schema', '-s', help='Show schema for specific table')
    parser.add_argument('--query', '-q', help='Run custom SQL query')
    parser.add_argument('--limit', '-l', type=int, default=10, help='Limit rows (default: 10)')

    args = parser.parse_args()

    if args.schema:
        show_table_schema(args.schema)
    elif args.table:
        show_table_data(args.table, args.limit)
    elif args.query:
        run_custom_query(args.query)
    else:
        show_all_tables()


if __name__ == "__main__":
    main()
