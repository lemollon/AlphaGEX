"""Concurrent API/scheduler access must construct one trader per process."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock
import trading.valor.trader as module


def test_simultaneous_requests_share_initialized_trader(monkeypatch):
    started, release = Event(), Event()
    instance = object()
    def initialize():
        started.set()
        assert release.wait(timeout=5)
        return instance
    constructor = Mock(side_effect=initialize)
    monkeypatch.setattr(module, '_trader_instance', None)
    monkeypatch.setattr(module, 'ValorTrader', constructor)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(module.get_valor_trader)
        assert started.wait(timeout=5)
        others = [pool.submit(module.get_valor_trader) for _ in range(2)]
        release.set()
        assert all(f.result(timeout=5) is instance for f in [first, *others])
    constructor.assert_called_once()
