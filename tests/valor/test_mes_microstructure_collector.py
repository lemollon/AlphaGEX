from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from trading.valor import mes_microstructure_collector as collector


UTC = timezone.utc
SYMBOL = "/MESZ26:XCME"
CONTRACT = "/MESZ6"


def quote(**changes):
    values = {
        "event_symbol": SYMBOL,
        "bid_price": 7000.00,
        "ask_price": 7000.25,
        "bid_size": 12,
        "ask_size": 8,
        "bid_time": 1_798_761_600_000,
        "ask_time": 1_798_761_600_010,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def sale(index=101, **changes):
    values = {
        "event_symbol": SYMBOL,
        "index": index,
        "sequence": index,
        "time": 1_798_761_600_020,
        "price": 7000.25,
        "size": 3,
        "aggressor_side": "BUY",
        "spread_leg": False,
        "extended_trading_hours": False,
        "valid_tick": True,
        "type": "NEW",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def aggregator(last_index=0):
    return collector.MESMinuteAggregator(
        CONTRACT, SYMBOL, "connection-1", persisted_last_sale_index=last_index
    )


def test_quote_fields_and_timestamp_provenance_are_preserved():
    agg = aggregator()
    received = datetime(2027, 1, 1, 0, 0, 1, tzinfo=UTC)

    assert agg.add_quote(quote(), received) is True
    row = agg.pop_all()[0]

    assert row["source"] == "TASTYTRADE_DXLINK"
    assert row["contract_symbol"] == CONTRACT
    assert row["streamer_symbol"] == SYMBOL
    assert row["bid_close"] == 7000.0
    assert row["ask_close"] == 7000.25
    assert row["spread_avg"] == 0.25
    assert row["quote_exchange_time_count"] == 1
    assert row["quality_complete"] is True


def test_crossed_quote_is_rejected_and_quality_is_flagged():
    agg = aggregator()
    received = datetime(2027, 1, 1, 0, 0, 1, tzinfo=UTC)

    assert agg.add_quote(quote(bid_price=7001, ask_price=7000), received) is False
    row = agg.pop_all()[0]

    assert row["valid_quote_count"] == 0
    assert row["invalid_quote_count"] == 1
    assert row["quality_complete"] is False


def test_time_and_sale_uses_real_aggressor_and_handles_correction_cancel():
    agg = aggregator()
    received = datetime(2027, 1, 1, 0, 0, 1, tzinfo=UTC)

    assert agg.add_sale(sale(), received) is True
    assert agg.add_sale(
        sale(type="CORRECTION", price=7000.50, size=4, aggressor_side="SELL"),
        received + timedelta(milliseconds=1),
    ) is True
    updated = agg.buckets[datetime(2027, 1, 1, 0, 0, tzinfo=UTC)].to_row()
    assert updated["trade_count"] == 1
    assert updated["trade_volume"] == 4
    assert updated["aggressor_sell_volume"] == 4
    assert updated["correction_count"] == 1

    assert agg.add_sale(
        sale(type="CANCEL"), received + timedelta(milliseconds=2)
    ) is True
    row = agg.pop_all()[0]
    assert row["trade_count"] == 0
    assert row["trade_volume"] == 0
    assert row["cancellation_count"] == 1
    assert row["last_sale_index"] == 101


def test_persisted_index_prevents_reconnect_replay_double_count():
    agg = aggregator(last_index=500)
    received = datetime(2027, 1, 1, 0, 0, 1, tzinfo=UTC)

    assert agg.add_sale(sale(index=500), received) is False
    assert agg.add_sale(sale(index=501), received) is True
    row = agg.pop_all()[0]

    assert row["duplicate_trade_count"] == 1
    assert row["trade_count"] == 1
    assert row["trade_volume"] == 3
    assert row["last_sale_index"] == 501


def test_completed_bucket_is_retained_for_late_in_connection_correction():
    agg = aggregator()
    received = datetime(2027, 1, 1, 0, 0, 1, tzinfo=UTC)
    agg.add_sale(sale(), received)

    first = agg.pop_completed(received + timedelta(minutes=1))[0]
    assert first["trade_close"] == 7000.25
    assert agg.add_sale(
        sale(type="CORRECTION", price=6999.75),
        received + timedelta(minutes=1, seconds=1),
    ) is True
    second = agg.pop_completed(received + timedelta(minutes=2))[0]

    assert second["trade_count"] == 1
    assert second["trade_close"] == 6999.75
    assert second["correction_count"] == 1


def test_collector_fails_closed_without_enablement_or_oauth(monkeypatch):
    monkeypatch.setattr(collector, "TASTYTRADE_STREAMING_AVAILABLE", True)
    disabled = collector.MESMicrostructureCollector(
        enabled=False, client_secret="secret", refresh_token="refresh"
    )
    missing_oauth = collector.MESMicrostructureCollector(
        enabled=True, client_secret=None, refresh_token=None
    )

    assert disabled.start() is False
    assert missing_oauth.start() is False
    assert disabled.is_alive() is False
    assert missing_oauth.is_alive() is False
    assert collector.READ_ONLY_MODE is True


def test_exact_contract_resolution_rejects_ambiguous_active_months():
    instance = collector.MESMicrostructureCollector(
        enabled=True, client_secret="secret", refresh_token="refresh"
    )
    now = datetime.now(UTC)
    valid = SimpleNamespace(
        product_code="MES", active_month=True, is_tradeable=True,
        is_closing_only=False, stops_trading_at=now + timedelta(days=10),
        symbol=CONTRACT, streamer_symbol=SYMBOL,
    )

    async def fake_get(_session, product_codes):
        assert product_codes == ["MES"]
        return [valid, valid]

    original = collector.Future
    collector.Future = SimpleNamespace(get=fake_get)
    try:
        with pytest.raises(RuntimeError, match="MESContractResolutionError"):
            import asyncio
            asyncio.run(instance._resolve_contract(object()))
    finally:
        collector.Future = original


def test_connection_subscribes_only_to_quote_and_time_and_sale(monkeypatch):
    import asyncio

    subscriptions = []

    class FakeQuote:
        pass

    class FakeTimeAndSale:
        pass

    class FakeStreamer:
        def __init__(self, _session):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def subscribe(self, event_type, symbols, refresh_interval):
            subscriptions.append((event_type, symbols, refresh_interval))

        async def listen(self, _event_type):
            while True:
                await asyncio.sleep(60)
                yield None

    class FakeStore:
        def last_sale_index(self, contract_symbol):
            assert contract_symbol == CONTRACT
            return 0

        def close_gap(self, *_args):
            return None

        def update_status(self, **_kwargs):
            return None

        def upsert_segment(self, _row):
            raise AssertionError("no fabricated rows may be stored")

    monkeypatch.setattr(collector, "Session", lambda *_args: object())
    monkeypatch.setattr(collector, "DXLinkStreamer", FakeStreamer)
    monkeypatch.setattr(collector, "Quote", FakeQuote)
    monkeypatch.setattr(collector, "TimeAndSale", FakeTimeAndSale)
    instance = collector.MESMicrostructureCollector(
        enabled=True,
        client_secret="secret",
        refresh_token="refresh",
        store=FakeStore(),
    )

    async def resolve(_session):
        return CONTRACT, SYMBOL

    async def rotate_now():
        return None

    monkeypatch.setattr(instance, "_resolve_contract", resolve)
    monkeypatch.setattr(instance, "_rotation_wait", rotate_now)

    asyncio.run(instance._connection_once("gap-1"))

    assert subscriptions == [
        (FakeQuote, [SYMBOL], 0.1),
        (FakeTimeAndSale, [SYMBOL], 0.1),
    ]
