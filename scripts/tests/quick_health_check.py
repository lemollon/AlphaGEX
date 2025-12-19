#!/usr/bin/env python3
"""
Quick Health Check - Fast system status check
Run in Render shell: python scripts/tests/quick_health_check.py

A lightweight script for quick deployment verification.
"""

import os
import sys
from datetime import datetime

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def check_env_vars():
    """Check critical environment variables"""
    print("\n📋 Environment Variables:")
    critical_vars = {
        'DATABASE_URL': os.environ.get('DATABASE_URL'),
        'CLAUDE_API_KEY': os.environ.get('CLAUDE_API_KEY'),
    }

    all_set = True
    for var, value in critical_vars.items():
        status = "✓ Set" if value else "✗ NOT SET"
        print(f"   {var}: {status}")
        if not value:
            all_set = False

    return all_set


def check_database():
    """Check database connection"""
    print("\n🗄️  Database Connection:")
    try:
        from database_adapter import get_connection, is_database_available

        if not is_database_available():
            print("   ✗ Database not available")
            return False

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        print("   ✓ Connected successfully")
        return True
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        return False


def check_tables():
    """Check essential tables exist"""
    print("\n📊 Essential Tables:")
    essential_tables = [
        'gex_snapshots',
        'decision_logs',
        'oracle_predictions',
        'probability_weights',
        'wheel_cycles'
    ]

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        all_exist = True
        for table in essential_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))
            exists = cursor.fetchone()[0]
            status = "✓" if exists else "✗"
            print(f"   {status} {table}")
            if not exists:
                all_exist = False

        conn.close()
        return all_exist
    except Exception as e:
        print(f"   ✗ Error checking tables: {e}")
        return False


def check_api():
    """Check API health endpoint"""
    print("\n🌐 API Health:")
    import json
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    # Auto-detect Render URL
    if os.environ.get('API_BASE_URL'):
        api_url = os.environ.get('API_BASE_URL')
    elif os.environ.get('RENDER'):
        service_name = os.environ.get('RENDER_SERVICE_NAME', 'alphagex-backend')
        api_url = f"https://{service_name}.onrender.com"
    else:
        api_url = 'http://localhost:8000'

    try:
        req = Request(f"{api_url}/health")
        response = urlopen(req, timeout=10)
        data = json.loads(response.read().decode('utf-8'))

        if data.get('status') == 'healthy':
            print(f"   ✓ API healthy at {api_url}")
            return True
        else:
            print(f"   ⚠️  API responded but not healthy")
            return False
    except URLError as e:
        print(f"   ✗ API not reachable: {e.reason}")
        return False
    except Exception as e:
        print(f"   ✗ API check failed: {e}")
        return False


def check_claude():
    """Check Claude API availability"""
    print("\n🤖 Claude AI:")
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("   ⚠️  ANTHROPIC_API_KEY not set")
        return False

    # Just check key is present and formatted correctly
    if api_key.startswith('sk-ant-'):
        print("   ✓ API key format valid")
        return True
    else:
        print("   ⚠️  API key format unexpected (may still work)")
        return True


def main():
    """Run quick health check"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║            ALPHAGEX QUICK HEALTH CHECK                    ║
╚═══════════════════════════════════════════════════════════╝
""")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        'Environment': check_env_vars(),
        'Database': check_database(),
        'Tables': check_tables(),
        'Claude AI': check_claude(),
    }

    # Try API check (may fail if server not running locally)
    try:
        results['API'] = check_api()
    except:
        results['API'] = None  # Skip if not available

    # Summary
    print("\n" + "="*50)
    print("SUMMARY:")
    print("="*50)

    all_passed = True
    for check, result in results.items():
        if result is None:
            status = "⏭️  SKIPPED"
        elif result:
            status = "✓ PASS"
        else:
            status = "✗ FAIL"
            all_passed = False
        print(f"   [{status}] {check}")

    print("="*50)

    if all_passed:
        print("\n   ✅ System appears healthy!")
        return 0
    else:
        print("\n   ⚠️  Some checks failed - review above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
