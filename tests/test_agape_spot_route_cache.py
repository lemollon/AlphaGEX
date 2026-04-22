"""
AGAPE-SPOT Route Cache — HIT/MISS Tests

Covers the _cached_with_status helper that backs the 5s response cache on
/api/agape-spot/summary and /api/agape-spot/equity-curve/intraday, plus the
X-AgapeSpot-Cache header exposed for production verification.

Run:  pytest tests/test_agape_spot_route_cache.py -v --no-cov
"""

import importlib

import pytest


@pytest.fixture
def routes_module(monkeypatch):
    """Import the routes module with a stable clock + empty cache per test."""
    mod = importlib.import_module("backend.api.routes.agape_spot_routes")
    # Reset the shared cache so tests don't leak into each other.
    mod._ROUTE_CACHE.clear()

    # Freeze time() so the TTL math is deterministic.
    t = [1_000_000.0]
    monkeypatch.setattr(mod.time, "time", lambda: t[0])
    mod._TEST_CLOCK = t  # expose to the test
    return mod


def test_first_call_is_miss(routes_module):
    calls = []

    def producer():
        calls.append(1)
        return {"value": 42}

    is_hit, value = routes_module._cached_with_status("k1", 5.0, producer)

    assert is_hit is False
    assert value == {"value": 42}
    assert calls == [1]


def test_second_call_within_ttl_is_hit(routes_module):
    calls = []

    def producer():
        calls.append(1)
        return {"value": 42}

    routes_module._cached_with_status("k1", 5.0, producer)
    # Step forward, still inside TTL.
    routes_module._TEST_CLOCK[0] += 2.0
    is_hit, value = routes_module._cached_with_status("k1", 5.0, producer)

    assert is_hit is True
    assert value == {"value": 42}
    # Producer only fired once.
    assert calls == [1]


def test_expires_after_ttl(routes_module):
    calls = []

    def producer():
        calls.append(len(calls) + 1)
        return {"n": calls[-1]}

    routes_module._cached_with_status("k1", 5.0, producer)
    # Step past TTL → refetch.
    routes_module._TEST_CLOCK[0] += 6.0
    is_hit, value = routes_module._cached_with_status("k1", 5.0, producer)

    assert is_hit is False
    assert value == {"n": 2}
    assert calls == [1, 2]


def test_keys_are_isolated(routes_module):
    a_calls: list = []
    b_calls: list = []

    def prod_a():
        a_calls.append(1)
        return "A"

    def prod_b():
        b_calls.append(1)
        return "B"

    assert routes_module._cached_with_status("a", 5.0, prod_a) == (False, "A")
    assert routes_module._cached_with_status("b", 5.0, prod_b) == (False, "B")
    # Both again → both hit.
    assert routes_module._cached_with_status("a", 5.0, prod_a) == (True, "A")
    assert routes_module._cached_with_status("b", 5.0, prod_b) == (True, "B")
    assert len(a_calls) == 1
    assert len(b_calls) == 1


def test_back_compat_cached_discards_status(routes_module):
    """The legacy _cached wrapper must still return just the value."""
    def producer():
        return [1, 2, 3]

    value = routes_module._cached("legacy", 5.0, producer)

    assert value == [1, 2, 3]


def test_cache_header_constant_matches_contract(routes_module):
    """Monitoring relies on the exact header name; guard against accidental renames."""
    assert routes_module._CACHE_HEADER == "X-AgapeSpot-Cache"
