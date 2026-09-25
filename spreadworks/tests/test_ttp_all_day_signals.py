"""Signal continuity and Discord delivery tests without network calls."""
import asyncio
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


class FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeApp:
    def __init__(self, *args, **kwargs):
        pass

    def on_event(self, *args):
        return lambda fn: fn

    def get(self, *args):
        return lambda fn: fn


sys.modules.setdefault("httpx", types.SimpleNamespace(AsyncClient=FakeClient))
sys.modules.setdefault("fastapi", types.SimpleNamespace(FastAPI=FakeApp))
BACKEND = Path(__file__).resolve().parents[1] / "backend"


def load(name):
    spec = importlib.util.spec_from_file_location(name, BACKEND / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SignalContinuityTests(unittest.TestCase):
    def test_more_than_three_and_cooldown_allows_new_setup(self):
        scanner = load("ttp_multi_engine")
        now = datetime.now(ZoneInfo("America/New_York")).replace(second=0, microsecond=0)
        symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
        clock = [now]

        async def tv(_):
            return []

        async def fetch(_, symbol):
            return symbol, None

        def propose(symbol, _bars, _prev, _now):
            return scanner.Proposal(symbol, "BUY", "ORB", 8, 10, 9.9, 10.1,
                                    10.2, 100, 10, 1000, clock[0].isoformat(), 1, 2)

        with patch.object(scanner, "STATIC_UNIVERSE", symbols), \
             patch.object(scanner, "_window_open", return_value=True), \
             patch.object(scanner, "_fetch_tv_symbols", tv), \
             patch.object(scanner, "_fetch_symbol", fetch), \
             patch.object(scanner, "_proposal", propose):
            asyncio.run(scanner._cycle())
            self.assertEqual(len(scanner._STATE["proposals_today"]), 5)
            asyncio.run(scanner._cycle())
            self.assertEqual(len(scanner._STATE["proposals_today"]), 5)
            clock[0] += timedelta(minutes=31)
            asyncio.run(scanner._cycle())
            self.assertEqual(len(scanner._STATE["proposals_today"]), 10)

    def test_relay_retries_failed_delivery_and_ignores_old_signal(self):
        relay = load("ttp_discord_relay")
        signal = {"symbol": "AAA", "engine": "ORB", "bar_time": datetime.now(timezone.utc).isoformat(),
                  "shares": 10, "entry": 10, "stop": 9, "target1": 11, "target2": 12,
                  "risk_dollars": 10, "position_value": 100}

        class Response:
            def __init__(self, fail):
                self.fail = fail

            def raise_for_status(self):
                if self.fail:
                    raise RuntimeError("Discord unavailable")

        class Client:
            def __init__(self):
                self.fail = True
                self.calls = 0

            async def post(self, *args, **kwargs):
                self.calls += 1
                return Response(self.fail)

        client = Client()
        with patch.object(relay, "WEBHOOK", "https://example.invalid/webhook"):
            with self.assertRaises(RuntimeError):
                asyncio.run(relay.post_signal(client, signal))
            self.assertFalse(relay.seen)
            client.fail = False
            asyncio.run(relay.post_signal(client, signal))
            asyncio.run(relay.post_signal(client, signal))
            self.assertEqual(client.calls, 2)
            signal["bar_time"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            asyncio.run(relay.post_signal(client, signal))
            self.assertEqual(client.calls, 2)


if __name__ == "__main__":
    unittest.main()
