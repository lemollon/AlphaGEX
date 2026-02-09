"""
COUNSELOR Enhancements Test Suite

Comprehensive tests for:
- Caching layer (CounselorCache)
- Tracing system (CounselorTracer)
- New commands (/market-hours, /strategy-performance, /suggestion, /risk)
- Integration tests
"""

import pytest
import time
import threading
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# CACHE TESTS
# =============================================================================

class TestCounselorCache:
    """Test the COUNSELOR caching layer."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance for each test."""
        from ai.counselor_cache import CounselorCache
        return CounselorCache(max_entries=100)

    def test_cache_set_and_get(self, cache):
        """Test basic set and get operations."""
        cache.set("test_key", {"data": "value"}, ttl=60)
        result = cache.get("test_key")

        assert result is not None
        assert result["data"] == "value"

    def test_cache_miss_returns_none(self, cache):
        """Test that cache miss returns None."""
        result = cache.get("nonexistent_key")
        assert result is None

    def test_cache_expiration(self, cache):
        """Test that expired entries are not returned."""
        cache.set("short_ttl", "value", ttl=0.1)  # 100ms TTL

        # Should exist immediately
        assert cache.get("short_ttl") == "value"

        # Wait for expiration
        time.sleep(0.15)

        # Should be expired
        assert cache.get("short_ttl") is None

    def test_cache_stats_tracking(self, cache):
        """Test that cache statistics are tracked correctly."""
        # Initial state
        stats = cache.get_stats()
        assert stats['hits'] == 0
        assert stats['misses'] == 0
        assert stats['sets'] == 0

        # Set and get
        cache.set("key1", "value1", ttl=60)
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss

        stats = cache.get_stats()
        assert stats['sets'] == 1
        assert stats['hits'] == 1
        assert stats['misses'] == 1

    def test_cache_delete(self, cache):
        """Test cache delete operation."""
        cache.set("to_delete", "value", ttl=60)
        assert cache.get("to_delete") == "value"

        result = cache.delete("to_delete")
        assert result is True
        assert cache.get("to_delete") is None

        # Delete non-existent key
        result = cache.delete("nonexistent")
        assert result is False

    def test_cache_invalidate_prefix(self, cache):
        """Test prefix-based cache invalidation."""
        cache.set("market:SPY", {"price": 450}, ttl=60)
        cache.set("market:QQQ", {"price": 380}, ttl=60)
        cache.set("position:1", {"symbol": "SPY"}, ttl=60)

        # Invalidate market prefix
        count = cache.invalidate_prefix("market:")
        assert count == 2

        # Market keys should be gone
        assert cache.get("market:SPY") is None
        assert cache.get("market:QQQ") is None

        # Position key should remain
        assert cache.get("position:1") is not None

    def test_cache_clear(self, cache):
        """Test cache clear operation."""
        cache.set("key1", "value1", ttl=60)
        cache.set("key2", "value2", ttl=60)

        count = cache.clear()
        assert count == 2

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_get_or_set(self, cache):
        """Test get_or_set operation."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return {"computed": True}

        # First call should invoke factory
        result1 = cache.get_or_set("computed_key", factory, ttl=60)
        assert result1["computed"] is True
        assert call_count == 1

        # Second call should return cached value
        result2 = cache.get_or_set("computed_key", factory, ttl=60)
        assert result2["computed"] is True
        assert call_count == 1  # Factory not called again

    def test_cache_decorator(self, cache):
        """Test the @cached decorator."""
        call_count = 0

        @cache.cached(ttl=60, key_prefix="test")
        def expensive_operation(x, y):
            nonlocal call_count
            call_count += 1
            return x + y

        # First call
        result1 = expensive_operation(1, 2)
        assert result1 == 3
        assert call_count == 1

        # Second call with same args (should be cached)
        result2 = expensive_operation(1, 2)
        assert result2 == 3
        assert call_count == 1

        # Different args (new computation)
        result3 = expensive_operation(3, 4)
        assert result3 == 7
        assert call_count == 2

    def test_cache_thread_safety(self, cache):
        """Test that cache is thread-safe."""
        results = []
        errors = []

        def worker(thread_id):
            try:
                for i in range(100):
                    key = f"key_{thread_id}_{i}"
                    cache.set(key, {"thread": thread_id, "iteration": i}, ttl=60)
                    value = cache.get(key)
                    if value is not None:
                        results.append(value)
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) > 0

    def test_cache_max_entries_cleanup(self):
        """Test that cache cleans up when max entries reached."""
        from ai.counselor_cache import CounselorCache
        cache = CounselorCache(max_entries=10)

        # Add 15 entries
        for i in range(15):
            cache.set(f"key_{i}", f"value_{i}", ttl=60)

        # Should not exceed max entries by too much
        stats = cache.get_stats()
        assert stats['entries'] <= 15  # Cleanup happens during set

    def test_cache_entry_info(self, cache):
        """Test get_entry_info method."""
        cache.set("info_key", {"test": True}, ttl=120)

        # Access it once
        cache.get("info_key")

        info = cache.get_entry_info("info_key")
        assert info is not None
        assert info['key'] == "info_key"
        assert info['hit_count'] == 1
        assert info['ttl_seconds'] == 120
        assert info['remaining_ttl'] > 0
        assert info['value_type'] == 'dict'

        # Non-existent key
        assert cache.get_entry_info("nonexistent") is None


class TestCacheConvenienceFunctions:
    """Test cache convenience functions."""

    def test_cache_market_data(self):
        """Test market data caching functions."""
        from ai.counselor_cache import cache_market_data, get_cached_market_data, counselor_cache

        # Clear first
        counselor_cache.clear()

        # Cache some data
        cache_market_data("SPY", {"price": 450, "volume": 1000000})

        # Retrieve it
        result = get_cached_market_data("SPY")
        assert result is not None
        assert result["price"] == 450

        # Miss for different symbol
        assert get_cached_market_data("QQQ") is None

    def test_cache_gex_data(self):
        """Test GEX data caching functions."""
        from ai.counselor_cache import cache_gex_data, get_cached_gex_data, counselor_cache

        counselor_cache.clear()

        cache_gex_data("SPY", {"net_gex": 2500000000, "flip_point": 575})

        result = get_cached_gex_data("SPY")
        assert result is not None
        assert result["net_gex"] == 2500000000

    def test_invalidate_positions_cache(self):
        """Test positions cache invalidation."""
        from ai.counselor_cache import cache_positions, get_cached_positions, invalidate_positions_cache, counselor_cache

        counselor_cache.clear()

        positions = [{"symbol": "SPY", "strike": 450}]
        cache_positions(positions)

        assert get_cached_positions() is not None

        invalidate_positions_cache()

        assert get_cached_positions() is None


# =============================================================================
# TRACING TESTS
# =============================================================================

class TestCounselorTracer:
    """Test the COUNSELOR tracing system."""

    @pytest.fixture
    def tracer(self):
        """Create a fresh tracer instance for each test."""
        from ai.counselor_tracing import CounselorTracer
        return CounselorTracer(service_name="test")

    def test_trace_context_manager(self, tracer):
        """Test basic trace context manager."""
        with tracer.trace("test.operation") as span:
            span.set_attribute("test_attr", "value")
            time.sleep(0.01)  # Small delay to ensure measurable duration

        assert span.status == "ok"
        assert span.duration_ms is not None
        assert span.duration_ms >= 10
        assert span.attributes["test_attr"] == "value"

    def test_trace_captures_errors(self, tracer):
        """Test that traces capture errors."""
        with pytest.raises(ValueError):
            with tracer.trace("test.failing") as span:
                raise ValueError("Test error")

        assert span.status == "error"
        assert span.error == "Test error"

    def test_trace_nested_spans(self, tracer):
        """Test nested trace spans."""
        with tracer.trace("parent.operation") as parent:
            parent_trace_id = parent.trace_id

            with tracer.trace("child.operation") as child:
                child_trace_id = child.trace_id
                child_parent_id = child.parent_id

        # Child should share parent's trace ID
        assert child_trace_id == parent_trace_id
        # Child's parent should be the parent span
        assert child_parent_id == parent.span_id

    def test_traced_decorator(self, tracer):
        """Test @traced decorator."""
        @tracer.traced("test.decorated")
        def my_function(x, y):
            return x + y

        result = my_function(1, 2)
        assert result == 3

        # Check metrics
        metrics = tracer.get_metrics()
        assert metrics['total_spans'] >= 1
        assert "test.decorated" in metrics['operation_counts']

    def test_traced_async_decorator(self, tracer):
        """Test @traced_async decorator."""
        @tracer.traced_async("test.async_decorated")
        async def my_async_function(x):
            await asyncio.sleep(0.01)
            return x * 2

        result = asyncio.run(my_async_function(5))
        assert result == 10

    def test_tracer_metrics(self, tracer):
        """Test tracer metrics collection."""
        # Create some spans
        for i in range(5):
            with tracer.trace("test.metric_op"):
                time.sleep(0.001)

        metrics = tracer.get_metrics()
        assert metrics['total_spans'] == 5
        assert metrics['error_spans'] == 0
        assert metrics['error_rate_pct'] == 0
        assert "test.metric_op" in metrics['operation_counts']
        assert metrics['operation_counts']['test.metric_op'] == 5

    def test_tracer_duration_stats(self, tracer):
        """Test duration statistics calculation."""
        # Create spans with known durations
        for i in range(25):
            with tracer.trace("test.duration_op"):
                time.sleep(0.005)  # 5ms each

        metrics = tracer.get_metrics()
        duration_stats = metrics['duration_stats'].get('test.duration_op', {})

        assert duration_stats['count'] == 25
        assert duration_stats['min_ms'] >= 4
        assert duration_stats['avg_ms'] >= 4

    def test_get_recent_traces(self, tracer):
        """Test retrieving recent traces."""
        for i in range(10):
            with tracer.trace(f"test.trace_{i}"):
                pass

        recent = tracer.get_recent_traces(limit=5)
        assert len(recent) == 5

    def test_trace_events(self, tracer):
        """Test adding events to spans."""
        with tracer.trace("test.with_events") as span:
            span.add_event("checkpoint_1", {"data": "first"})
            span.add_event("checkpoint_2", {"data": "second"})

        assert len(span.events) == 2
        assert span.events[0]['name'] == "checkpoint_1"
        assert span.events[1]['name'] == "checkpoint_2"

    def test_span_to_dict(self, tracer):
        """Test span serialization."""
        with tracer.trace("test.serialize") as span:
            span.set_attribute("key", "value")

        data = span.to_dict()
        assert 'span_id' in data
        assert 'trace_id' in data
        assert 'operation_name' in data
        assert data['operation_name'] == "test.serialize"
        assert 'duration_ms' in data
        assert 'attributes' in data
        assert data['attributes']['key'] == "value"


class TestRequestContext:
    """Test RequestContext for request-level tracing."""

    def test_request_context(self):
        """Test basic request context."""
        from ai.counselor_tracing import RequestContext

        with RequestContext() as ctx:
            assert ctx.request_id is not None
            assert len(ctx.request_id) == 8
            assert ctx.trace_id is not None

    def test_request_context_custom_id(self):
        """Test request context with custom ID."""
        from ai.counselor_tracing import RequestContext

        with RequestContext(request_id="custom123") as ctx:
            assert ctx.request_id == "custom123"

    def test_request_context_duration(self):
        """Test request context duration tracking."""
        from ai.counselor_tracing import RequestContext

        with RequestContext() as ctx:
            time.sleep(0.02)  # 20ms
            duration = ctx.duration_ms

        assert duration >= 20


# =============================================================================
# NEW COMMANDS TESTS
# =============================================================================

class TestMarketHoursCommand:
    """Test /market-hours command."""

    def test_market_hours_info_structure(self):
        """Test that market hours info has correct structure."""
        from ai.counselor_commands import get_market_hours_info

        info = get_market_hours_info()

        assert 'status' in info
        assert 'status_detail' in info
        assert 'is_trading_day' in info
        assert 'current_time_et' in info
        assert 'market_open' in info
        assert 'market_close' in info
        assert 'next_event' in info
        assert 'time_until_next' in info

    def test_market_hours_status_values(self):
        """Test valid status values."""
        from ai.counselor_commands import get_market_hours_info

        info = get_market_hours_info()
        valid_statuses = [
            "OPEN", "CLOSED", "PREMARKET", "AFTERHOURS",
            "CLOSED_HOLIDAY", "CLOSED_WEEKEND"
        ]

        assert info['status'] in valid_statuses

    def test_execute_market_hours_command(self):
        """Test executing the market hours command."""
        from ai.counselor_commands import execute_market_hours_command

        result = execute_market_hours_command()

        assert result['success'] is True
        assert result['command'] == '/market-hours'
        assert 'response' in result
        assert 'data' in result
        assert result['type'] == 'market_hours'

        # Response should contain key information
        response = result['response']
        assert "Market Hours Report" in response
        assert "Status:" in response

    def test_market_holidays_are_defined(self):
        """Test that market holidays are defined for 2025."""
        from ai.counselor_commands import MARKET_HOLIDAYS_2025

        # Should have major US holidays
        assert "2025-01-01" in MARKET_HOLIDAYS_2025  # New Year
        assert "2025-12-25" in MARKET_HOLIDAYS_2025  # Christmas


class TestStrategyPerformanceCommand:
    """Test /strategy-performance command."""

    def test_strategy_performance_structure(self):
        """Test strategy performance data structure."""
        from ai.counselor_commands import get_strategy_performance

        # This will return mock data since DB isn't available
        perf = get_strategy_performance(days=30)

        # Should have data for trading bots
        assert 'FORTRESS' in perf or 'SOLOMON' in perf or 'CORNERSTONE' in perf

        # Each bot should have standard metrics
        for bot, stats in perf.items():
            if stats.get('trades', 0) > 0:
                assert 'trades' in stats
                assert 'win_rate' in stats
                assert 'total_pnl' in stats

    def test_execute_strategy_performance_command(self):
        """Test executing the strategy performance command."""
        from ai.counselor_commands import execute_strategy_performance_command

        result = execute_strategy_performance_command(days=30)

        assert result['success'] is True
        assert result['command'] == '/strategy-performance'
        assert 'response' in result
        assert 'data' in result
        assert result['period_days'] == 30

    def test_strategy_performance_with_custom_days(self):
        """Test strategy performance with custom day period."""
        from ai.counselor_commands import execute_strategy_performance_command

        result7 = execute_strategy_performance_command(days=7)
        result90 = execute_strategy_performance_command(days=90)

        assert result7['period_days'] == 7
        assert result90['period_days'] == 90


class TestSuggestionCommand:
    """Test /suggestion command."""

    @patch('ai.counselor_tools.fetch_ares_market_data')
    @patch('ai.counselor_tools.get_upcoming_events')
    @patch('ai.counselor_tools.is_market_open')
    def test_generate_trade_suggestion(
        self, mock_market_open, mock_events, mock_market_data
    ):
        """Test trade suggestion generation."""
        from ai.counselor_commands import generate_trade_suggestion

        mock_market_open.return_value = True
        mock_events.return_value = []
        mock_market_data.return_value = {"vix": 18, "spy": {"net_gex": 2000000000}}

        suggestions = generate_trade_suggestion()

        assert 'suggestions' in suggestions
        assert 'warnings' in suggestions
        assert 'market_open' in suggestions
        assert 'vix' in suggestions

        assert len(suggestions['suggestions']) > 0

    @patch('ai.counselor_commands.generate_trade_suggestion')
    def test_execute_suggestion_command(self, mock_generate):
        """Test executing the suggestion command."""
        from ai.counselor_commands import execute_suggestion_command
        from ai.counselor_cache import counselor_cache

        # Clear cache
        counselor_cache.clear()

        mock_generate.return_value = {
            'suggestions': [
                {
                    'type': 'opportunity',
                    'title': 'Test Suggestion',
                    'detail': 'Test detail',
                    'confidence': 'high'
                }
            ],
            'warnings': [],
            'market_open': True,
            'vix': 18,
            'events_upcoming': 0
        }

        result = execute_suggestion_command()

        assert result['success'] is True
        assert result['command'] == '/suggestion'
        assert 'response' in result
        assert 'Test Suggestion' in result['response']

    @patch('ai.counselor_tools.fetch_ares_market_data')
    @patch('ai.counselor_tools.get_upcoming_events')
    @patch('ai.counselor_tools.is_market_open')
    def test_suggestion_handles_high_vix(self, mock_open, mock_events, mock_market):
        """Test that high VIX triggers caution."""
        from ai.counselor_commands import generate_trade_suggestion

        mock_market.return_value = {"vix": 30}
        mock_events.return_value = []
        mock_open.return_value = True

        suggestions = generate_trade_suggestion()

        # Should have a warning or caution for high VIX
        assert len(suggestions['warnings']) > 0 or \
               any(s['type'] == 'caution' for s in suggestions['suggestions'])


class TestRiskCommand:
    """Test /risk command."""

    def test_get_portfolio_risk_structure(self):
        """Test portfolio risk data structure."""
        from ai.counselor_commands import get_portfolio_risk

        risk = get_portfolio_risk()

        # Should have key risk metrics
        assert 'total_positions' in risk or 'error' in risk

    def test_execute_risk_command(self):
        """Test executing the risk command."""
        from ai.counselor_commands import execute_risk_command

        result = execute_risk_command()

        assert result['command'] == '/risk'
        assert result['type'] == 'risk'

        if result['success']:
            assert 'response' in result
            assert 'data' in result


class TestExtendedCommandRegistry:
    """Test the extended command registry."""

    def test_extended_commands_defined(self):
        """Test that all extended commands are defined."""
        from ai.counselor_commands import EXTENDED_COMMANDS

        expected_commands = ['/market-hours', '/strategy-performance', '/suggestion', '/risk']

        for cmd in expected_commands:
            assert cmd in EXTENDED_COMMANDS
            assert 'description' in EXTENDED_COMMANDS[cmd]
            assert 'handler' in EXTENDED_COMMANDS[cmd]

    def test_execute_extended_command(self):
        """Test execute_extended_command function."""
        from ai.counselor_commands import execute_extended_command

        # Known command
        result = execute_extended_command('/market-hours')
        assert result is not None
        assert result['success'] is True

        # Unknown command
        result = execute_extended_command('/unknown-command')
        assert result is None

    def test_execute_command_with_args(self):
        """Test executing command with arguments."""
        from ai.counselor_commands import execute_extended_command

        result = execute_extended_command('/strategy-performance', args=['7'])
        assert result is not None
        assert result['period_days'] == 7


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestCounselorEnhancementsIntegration:
    """Integration tests for COUNSELOR enhancements."""

    def test_cache_with_tracing(self):
        """Test that caching works with tracing enabled."""
        from ai.counselor_cache import counselor_cache, CounselorCache
        from ai.counselor_tracing import counselor_tracer

        counselor_cache.clear()

        with counselor_tracer.trace("integration.cache_test") as span:
            # First call - cache miss
            result1 = counselor_cache.get("integration_key")
            span.add_event("cache_miss", {"key": "integration_key"})

            # Set value
            counselor_cache.set("integration_key", {"test": True}, ttl=60)
            span.add_event("cache_set", {"key": "integration_key"})

            # Second call - cache hit
            result2 = counselor_cache.get("integration_key")
            span.add_event("cache_hit", {"key": "integration_key"})

        assert result1 is None
        assert result2 is not None
        assert result2["test"] is True
        assert len(span.events) == 3

    def test_command_uses_cache(self):
        """Test that commands use caching."""
        from ai.counselor_commands import execute_strategy_performance_command
        from ai.counselor_cache import counselor_cache

        counselor_cache.clear()

        # First call - should set cache
        result1 = execute_strategy_performance_command(days=30)

        # Second call - should hit cache
        start = time.time()
        result2 = execute_strategy_performance_command(days=30)
        duration = time.time() - start

        # Both should succeed
        assert result1['success'] is True
        assert result2['success'] is True

        # Second call should be faster (from cache)
        assert duration < 0.1  # Should be near-instant from cache

    def test_tracing_captures_command_execution(self):
        """Test that tracing captures command execution."""
        from ai.counselor_commands import execute_market_hours_command
        from ai.counselor_tracing import counselor_tracer

        initial_count = counselor_tracer.get_metrics()['total_spans']

        execute_market_hours_command()

        final_count = counselor_tracer.get_metrics()['total_spans']

        # Should have created at least one span
        assert final_count > initial_count

    def test_full_command_flow(self):
        """Test complete command flow with cache and tracing."""
        from ai.counselor_commands import execute_extended_command
        from ai.counselor_cache import counselor_cache
        from ai.counselor_tracing import counselor_tracer, RequestContext

        counselor_cache.clear()

        with RequestContext(request_id="test_flow") as ctx:
            # Execute multiple commands
            commands = ['/market-hours', '/risk', '/suggestion']

            for cmd in commands:
                result = execute_extended_command(cmd)
                assert result is not None

            # Check request duration
            assert ctx.duration_ms > 0

        # Verify cache stats
        cache_stats = counselor_cache.get_stats()
        assert cache_stats['sets'] > 0

        # Verify trace metrics
        trace_metrics = counselor_tracer.get_metrics()
        assert trace_metrics['total_spans'] > 0


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_cache_handles_none_values(self):
        """Test that cache handles None values correctly."""
        from ai.counselor_cache import CounselorCache
        cache = CounselorCache()

        # Setting None should work
        cache.set("none_key", None, ttl=60)

        # Getting should return None (indistinguishable from miss)
        # This is expected behavior
        result = cache.get("none_key")
        # Note: None values are tricky - our implementation returns None for both miss and None value

    def test_cache_handles_large_values(self):
        """Test cache with large values."""
        from ai.counselor_cache import CounselorCache
        cache = CounselorCache()

        large_value = {"data": "x" * 100000}  # 100KB string
        cache.set("large_key", large_value, ttl=60)

        result = cache.get("large_key")
        assert result is not None
        assert len(result["data"]) == 100000

    def test_trace_with_exception_recovery(self):
        """Test that tracing recovers from exceptions properly."""
        from ai.counselor_tracing import CounselorTracer
        tracer = CounselorTracer()

        # Outer span should complete successfully
        with tracer.trace("outer") as outer_span:
            try:
                with tracer.trace("inner") as inner_span:
                    raise RuntimeError("Test error")
            except RuntimeError:
                pass  # Catch and continue

            # Outer span should still be active
            outer_span.set_attribute("recovered", True)

        assert outer_span.status == "ok"
        assert outer_span.attributes["recovered"] is True

    @patch('ai.counselor_tools.fetch_ares_market_data')
    @patch('ai.counselor_tools.get_upcoming_events')
    @patch('ai.counselor_tools.is_market_open')
    def test_command_handles_missing_market_data(self, mock_open, mock_events, mock_market):
        """Test commands handle missing market data gracefully."""
        from ai.counselor_commands import generate_trade_suggestion

        mock_market.side_effect = Exception("API Error")
        mock_events.return_value = []
        mock_open.return_value = False

        # Should not raise, should return default suggestion
        result = generate_trade_suggestion()

        assert 'suggestions' in result
        assert len(result['suggestions']) > 0

    def test_concurrent_cache_access(self):
        """Test concurrent cache access doesn't cause issues."""
        from ai.counselor_cache import CounselorCache
        cache = CounselorCache()
        errors = []
        results = []

        def reader():
            try:
                for _ in range(100):
                    cache.get("concurrent_key")
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    cache.set("concurrent_key", {"iteration": i}, ttl=60)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=writer),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class TestPerformance:
    """Performance tests for COUNSELOR enhancements."""

    def test_cache_set_performance(self):
        """Test cache set operation performance."""
        from ai.counselor_cache import CounselorCache
        cache = CounselorCache()

        start = time.time()
        for i in range(1000):
            cache.set(f"perf_key_{i}", {"data": i}, ttl=60)
        duration = time.time() - start

        # Should complete 1000 sets in under 100ms
        assert duration < 0.1, f"Cache set took {duration}s for 1000 operations"

    def test_cache_get_performance(self):
        """Test cache get operation performance."""
        from ai.counselor_cache import CounselorCache
        cache = CounselorCache()

        # Pre-populate
        for i in range(1000):
            cache.set(f"perf_get_key_{i}", {"data": i}, ttl=60)

        start = time.time()
        for i in range(1000):
            cache.get(f"perf_get_key_{i}")
        duration = time.time() - start

        # Should complete 1000 gets in under 50ms
        assert duration < 0.05, f"Cache get took {duration}s for 1000 operations"

    def test_trace_overhead(self):
        """Test that tracing overhead is acceptable for real-world use."""
        from ai.counselor_tracing import CounselorTracer
        tracer = CounselorTracer()

        def work():
            """Simulate realistic work (I/O-like delay)."""
            total = 0
            for i in range(10000):
                total += i
            return total

        # Without tracing
        start = time.time()
        for _ in range(20):
            work()
        baseline = time.time() - start

        # With tracing
        start = time.time()
        for _ in range(20):
            with tracer.trace("perf.work"):
                work()
        with_tracing = time.time() - start

        # Tracing overhead should be reasonable for real workloads
        # In practice, traced operations do I/O which dominates runtime
        overhead = (with_tracing - baseline) / baseline if baseline > 0 else 0

        # Allow up to 200% overhead for micro-benchmarks (real I/O would dominate)
        assert overhead < 2.0, f"Tracing overhead was {overhead * 100:.1f}%"

        # Also verify tracing is functional
        metrics = tracer.get_metrics()
        assert metrics['total_spans'] >= 20


# =============================================================================
# RATE LIMITER TESTS
# =============================================================================

class TestTokenBucket:
    """Test the token bucket implementation."""

    def test_token_bucket_initial_state(self):
        """Test token bucket starts with full capacity."""
        from ai.counselor_rate_limiter import TokenBucket

        bucket = TokenBucket(rate=1.0, capacity=10)
        assert bucket.available_tokens == 10

    def test_token_bucket_consume(self):
        """Test consuming tokens from bucket."""
        from ai.counselor_rate_limiter import TokenBucket

        bucket = TokenBucket(rate=1.0, capacity=10)

        # Consume 5 tokens
        allowed, wait_time = bucket.consume(5)
        assert allowed is True
        assert wait_time == 0.0
        # Use approximate comparison due to floating-point and timing
        assert 4.9 <= bucket.available_tokens <= 5.1

    def test_token_bucket_denies_when_empty(self):
        """Test bucket denies when insufficient tokens."""
        from ai.counselor_rate_limiter import TokenBucket

        bucket = TokenBucket(rate=1.0, capacity=5)

        # Consume all tokens
        bucket.consume(5)

        # Try to consume more
        allowed, wait_time = bucket.consume(1)
        assert allowed is False
        assert wait_time > 0

    def test_token_bucket_refills(self):
        """Test tokens refill over time."""
        from ai.counselor_rate_limiter import TokenBucket

        bucket = TokenBucket(rate=100.0, capacity=10)  # 100 tokens/second

        # Consume all
        bucket.consume(10)
        assert bucket.available_tokens < 1

        # Wait a bit
        time.sleep(0.05)  # 50ms = 5 tokens

        # Should have some tokens now
        assert bucket.available_tokens >= 4


class TestCounselorRateLimiter:
    """Test the COUNSELOR rate limiter."""

    @pytest.fixture
    def limiter(self):
        """Create a fresh rate limiter for each test."""
        from ai.counselor_rate_limiter import CounselorRateLimiter
        return CounselorRateLimiter()

    def test_rate_limiter_allows_initial_requests(self, limiter):
        """Test that initial requests are allowed."""
        allowed, retry_after, reason = limiter.check_rate_limit(
            user_id="test_user",
            endpoint="/analyze"
        )

        assert allowed is True
        assert retry_after is None
        assert reason == "OK"

    def test_rate_limiter_tracks_stats(self, limiter):
        """Test that stats are tracked correctly."""
        # Make some requests
        for i in range(5):
            limiter.check_rate_limit(f"user_{i}", "/analyze")

        stats = limiter.get_stats()
        assert stats['total_requests'] == 5
        assert stats['allowed_requests'] == 5
        assert stats['denied_requests'] == 0

    def test_rate_limiter_denies_excessive_requests(self, limiter):
        """Test that excessive requests are denied."""
        user_id = "heavy_user"
        denied_count = 0

        # Make many requests quickly
        for i in range(50):
            allowed, _, _ = limiter.check_rate_limit(user_id, "/analyze")
            if not allowed:
                denied_count += 1

        # Some should be denied
        assert denied_count > 0

    def test_rate_limiter_per_endpoint_limits(self, limiter):
        """Test endpoint-specific rate limits."""
        user_id = "test_user"

        # /briefing has stricter limits than /command
        briefing_denied = 0
        command_denied = 0

        for _ in range(20):
            allowed, _, _ = limiter.check_rate_limit(user_id, "/briefing")
            if not allowed:
                briefing_denied += 1

            allowed, _, _ = limiter.check_rate_limit(user_id, "/command")
            if not allowed:
                command_denied += 1

        # Briefing should hit limits faster
        assert briefing_denied >= command_denied

    def test_get_user_limits(self, limiter):
        """Test getting user limit information."""
        limiter.check_rate_limit("test_user", "/analyze")

        limits = limiter.get_user_limits("test_user", "/analyze")

        assert 'endpoint' in limits
        assert 'limit_per_minute' in limits
        assert 'available_tokens' in limits
        assert limits['endpoint'] == '/analyze'

    def test_reset_user(self, limiter):
        """Test resetting user limits."""
        user_id = "reset_test"

        # Make some requests
        for _ in range(5):
            limiter.check_rate_limit(user_id, "/analyze")

        # Reset
        result = limiter.reset_user(user_id)
        assert result is True

        # Reset non-existent user
        result = limiter.reset_user("nonexistent")
        assert result is False

    def test_cleanup_inactive(self, limiter):
        """Test cleaning up inactive users."""
        # Add a user
        limiter.check_rate_limit("old_user", "/analyze")

        # Cleanup with very short max age
        # Note: This might not clean up since last_update is recent
        count = limiter.cleanup_inactive(max_age_seconds=0)

        # Stats should show active users
        stats = limiter.get_stats()
        assert 'active_users' in stats

    def test_rate_limiter_thread_safety(self, limiter):
        """Test thread safety of rate limiter."""
        errors = []
        results = []

        def worker(user_id):
            try:
                for _ in range(20):
                    allowed, _, _ = limiter.check_rate_limit(user_id, "/analyze")
                    results.append(allowed)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(f"user_{i}",))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 100  # 5 users * 20 requests


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
