"""get_performance must stay JSON-serializable when there are wins and no losses.

float("inf") profit factor made /api/agape-eth-perp/performance return a
bare 500 (Starlette refuses non-finite floats) after ETH's first winning trade.
"""
import importlib
import json
from types import SimpleNamespace

import pytest

COINS = ["btc", "eth", "xrp", "sol", "doge", "avax", "shib"]


@pytest.mark.parametrize("coin", COINS)
def test_performance_json_safe_with_only_wins(coin):
    trader_mod = importlib.import_module(f"trading.agape_{coin}_perp.trader")
    cls = next(v for k, v in vars(trader_mod).items()
               if isinstance(v, type) and k.endswith("Trader") and hasattr(v, "get_performance"))
    t = cls.__new__(cls)
    win = {"realized_pnl": 51.03, "funding_regime_at_entry": "MILD_LONG_BIAS",
           "close_time": "2026-09-28T00:50:08+00:00", "pnl_pct": 0.5}
    t.db = SimpleNamespace(get_closed_trades=lambda **_: [win], get_open_positions=lambda: [])
    t.executor = SimpleNamespace(get_current_price=lambda: 100.0)
    t.config = SimpleNamespace(starting_capital=10000.0, default_quantity=1.0)
    perf = t.get_performance()
    json.dumps(perf, allow_nan=False)
    assert perf["profit_factor"] is None
