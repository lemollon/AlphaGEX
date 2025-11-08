#!/usr/bin/env python3
"""
AlphaGEX Deployment Monitor
Tracks which deployment is consuming Trading Volatility API quota
"""

import time
import requests
import json
from datetime import datetime
from collections import defaultdict

class DeploymentMonitor:
    def __init__(self):
        self.deployments = {
            'local': 'http://localhost:8000',
            'vercel': 'https://alphagex.vercel.app',
            'streamlit': None,  # Add your Streamlit URL if different
        }
        self.api_call_history = defaultdict(list)

    def check_deployment_health(self, name, url):
        """Check if a deployment is online and get its API usage stats"""
        if not url:
            return None

        try:
            # Try rate limit status endpoint
            response = requests.get(f"{url}/api/rate-limit-status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return {
                    'online': True,
                    'calls_this_minute': data.get('calls_this_minute', 0),
                    'remaining': data.get('remaining', 0),
                    'circuit_breaker_active': data.get('circuit_breaker_active', False),
                    'cache_size': data.get('cache_size', 0),
                    'total_calls_lifetime': data.get('total_calls_lifetime', 0),
                    'status': data.get('status', 'unknown'),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                # Try basic health check
                response = requests.get(f"{url}/api/time", timeout=5)
                return {
                    'online': response.status_code == 200,
                    'calls_this_minute': '?',
                    'remaining': '?',
                    'circuit_breaker_active': False,
                    'status': 'no_rate_limit_endpoint',
                    'timestamp': datetime.now().isoformat()
                }
        except requests.exceptions.RequestException as e:
            return {
                'online': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    def monitor_all(self, duration_minutes=5, interval_seconds=30):
        """Monitor all deployments for a period of time"""
        print("=" * 80)
        print("🔍 AlphaGEX Deployment Monitor")
        print("=" * 80)
        print(f"\nMonitoring for {duration_minutes} minutes (checking every {interval_seconds}s)")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        iterations = int((duration_minutes * 60) / interval_seconds)

        for i in range(iterations):
            print(f"\n{'─' * 80}")
            print(f"Check #{i+1}/{iterations} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'─' * 80}")

            for name, url in self.deployments.items():
                if not url:
                    continue

                status = self.check_deployment_health(name, url)

                if status and status['online']:
                    # Track API call history
                    if isinstance(status.get('calls_this_minute'), int):
                        self.api_call_history[name].append({
                            'timestamp': status['timestamp'],
                            'calls': status['calls_this_minute']
                        })

                    print(f"\n{name.upper():>10}: ✅ ONLINE")
                    print(f"           Calls/min: {status.get('calls_this_minute', '?')}/20")
                    print(f"           Remaining: {status.get('remaining', '?')}")
                    print(f"           Circuit Breaker: {'🚨 ACTIVE' if status.get('circuit_breaker_active') else '✅ Inactive'}")
                    print(f"           Cache Size: {status.get('cache_size', '?')}")
                    print(f"           Total Calls: {status.get('total_calls_lifetime', '?')}")
                    print(f"           Status: {status.get('status', 'unknown')}")
                else:
                    print(f"\n{name.upper():>10}: ❌ OFFLINE")
                    if status and 'error' in status:
                        print(f"           Error: {status['error']}")

            if i < iterations - 1:
                print(f"\n⏱️  Waiting {interval_seconds} seconds...")
                time.sleep(interval_seconds)

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print summary of API usage by deployment"""
        print("\n" + "=" * 80)
        print("📊 MONITORING SUMMARY")
        print("=" * 80)

        for name, history in self.api_call_history.items():
            if not history:
                continue

            print(f"\n{name.upper()}:")
            print(f"  Checks: {len(history)}")

            calls = [h['calls'] for h in history if isinstance(h['calls'], int)]
            if calls:
                print(f"  Avg calls/min: {sum(calls) / len(calls):.1f}")
                print(f"  Max calls/min: {max(calls)}")
                print(f"  Min calls/min: {min(calls)}")

                # Detect if actively consuming quota
                if sum(calls) / len(calls) > 2:
                    print(f"  ⚠️  HIGH USAGE - This deployment is actively consuming quota!")

    def quick_check(self):
        """Quick check of all deployments (single snapshot)"""
        print("=" * 80)
        print("🔍 AlphaGEX Deployment Quick Check")
        print("=" * 80)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        total_calls = 0

        for name, url in self.deployments.items():
            if not url:
                continue

            status = self.check_deployment_health(name, url)

            if status and status['online']:
                calls = status.get('calls_this_minute')
                if isinstance(calls, int):
                    total_calls += calls

                print(f"{name.upper():>10}: ✅ {calls}/20 calls/min | "
                      f"{'🚨 Circuit Breaker' if status.get('circuit_breaker_active') else '✅ OK'} | "
                      f"Cache: {status.get('cache_size', 0)}")
            else:
                print(f"{name.upper():>10}: ❌ OFFLINE")

        print(f"\n{'─' * 80}")
        print(f"TOTAL API CALLS/MIN: {total_calls}/20 ({'⚠️ NEAR LIMIT' if total_calls > 15 else '✅ OK'})")
        print(f"{'─' * 80}\n")

        return total_calls


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Monitor AlphaGEX deployments')
    parser.add_argument('--mode', choices=['quick', 'monitor'], default='quick',
                        help='Quick check or continuous monitoring')
    parser.add_argument('--duration', type=int, default=5,
                        help='Monitoring duration in minutes (default: 5)')
    parser.add_argument('--interval', type=int, default=30,
                        help='Check interval in seconds (default: 30)')
    parser.add_argument('--streamlit-url', type=str,
                        help='Streamlit deployment URL (if available)')

    args = parser.parse_args()

    monitor = DeploymentMonitor()

    # Add Streamlit URL if provided
    if args.streamlit_url:
        monitor.deployments['streamlit'] = args.streamlit_url

    if args.mode == 'quick':
        total_calls = monitor.quick_check()

        # Provide recommendations
        if total_calls > 15:
            print("\n⚠️  RECOMMENDATION: You're using >75% of API quota")
            print("   Consider stopping non-essential deployments or implementing caching fixes\n")
        elif total_calls > 10:
            print("\n💡 RECOMMENDATION: Moderate usage detected")
            print("   Apply intelligent caching to reduce API calls\n")
        else:
            print("\n✅ RECOMMENDATION: API usage is healthy")
            print("   Current load is sustainable\n")

    else:
        monitor.monitor_all(duration_minutes=args.duration, interval_seconds=args.interval)


if __name__ == '__main__':
    main()
