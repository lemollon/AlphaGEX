from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import valor_mes_dxlink_candle_probe as probe


UTC = timezone.utc
START = datetime(2023, 9, 18, tzinfo=UTC)


def spec(interval="1m"):
    return probe.ProbeSpec("/MESZ3", "/MESZ23:XCME", interval, START)


def continuous_spec(interval="1h"):
    return probe.ProbeSpec("/MES", "/MES:XCME", interval, START)


def es_continuous_spec(interval="1h"):
    return probe.ProbeSpec("/ES", "/ES:XCME", interval, START)


def event(**overrides):
    values = dict(
        event_symbol="/MESZ23:XCME{=1m}",
        time=int(datetime(2023, 12, 1, tzinfo=UTC).timestamp() * 1000),
        open=4500.00, high=4501.25, low=4499.75, close=4501.00,
        volume=120, vwap=4500.5, bid_volume=50, ask_volume=70,
        count=44, index=123, sequence=2, event_flags=0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_valid_exact_contract_candle_is_preserved():
    row = probe.candle_to_row(event(), spec())
    assert row["contract_symbol"] == "/MESZ3"
    assert row["event_time"].tzinfo is UTC
    assert row["bid_volume"] == 50
    assert row["ask_volume"] == 70
    assert row["source"] == "TASTYTRADE_DXLINK_CANDLE"


def test_removal_tombstone_identity_does_not_require_ohlc():
    tombstone = event(open=0, high=0, low=0, close=0, event_flags=2)
    event_time, flags = probe.candle_identity(tombstone, spec())
    assert event_time == datetime(2023, 12, 1, tzinfo=UTC)
    assert flags & 2


@pytest.mark.parametrize("event_symbol", [
    "/MESZ23:XCME{=1m}",
    "/MESZ23:XCME{=m}",
])
def test_one_minute_identity_accepts_dxfeed_period_normalization(event_symbol):
    row = probe.candle_to_row(event(event_symbol=event_symbol), spec())
    assert row["interval"] == "1m"


@pytest.mark.parametrize("event_symbol", [
    "/MES:XCME{=1h}",
    "/MES:XCME{=h}",
])
def test_hourly_continuous_identity_accepts_dxfeed_normalization(event_symbol):
    row = probe.candle_to_row(
        event(event_symbol=event_symbol), continuous_spec()
    )
    assert row["contract_symbol"] == "/MES"
    assert row["streamer_symbol"] == "/MES:XCME"
    assert row["interval"] == "1h"


@pytest.mark.parametrize("event_symbol", [
    "/ES:XCME{=1h}",
    "/ES:XCME{=h}",
])
def test_hourly_es_leader_identity_accepts_only_exact_continuous_pair(event_symbol):
    row = probe.candle_to_row(
        event(event_symbol=event_symbol), es_continuous_spec()
    )
    assert row["contract_symbol"] == "/ES"
    assert row["streamer_symbol"] == "/ES:XCME"
    assert row["interval"] == "1h"


@pytest.mark.parametrize(("contract", "streamer"), [
    ("/MES", "/MESZ23:XCME"),
    ("/MESZ3", "/MES:XCME"),
    ("/ES", "/MES:XCME"),
    ("/MES", "/ES:XCME"),
    ("/ESZ3", "/ESZ23:XCME"),
    ("/NQ", "/NQ:XCME"),
])
def test_continuous_symbol_validation_rejects_mixed_or_wrong_products(
    contract, streamer
):
    with pytest.raises(probe.InvalidProbeConfiguration):
        probe.ProbeSpec(contract, streamer, "1h", START)


def test_identity_rejects_a_different_candle_period():
    with pytest.raises(ValueError, match="unexpected candle symbol"):
        probe.candle_to_row(event(event_symbol="/MESZ23:XCME{=5m}"), spec())


@pytest.mark.parametrize("bad", [
    {"event_symbol": "/ESZ23:XCME{=1m}"},
    {"close": 4501.10},
    {"high": 4499.00},
    {"bid_volume": -1},
])
def test_invalid_provider_candles_fail_closed(bad):
    with pytest.raises(ValueError):
        probe.candle_to_row(event(**bad), spec())


def test_snapshot_classification_detects_provider_cap():
    rows = []
    for minute in range(7_900):
        item = probe.candle_to_row(event(
            time=int((datetime(2023, 11, 1, tzinfo=UTC).timestamp() + minute * 60) * 1000)
        ), spec())
        rows.append(item)
    result = probe.classify_snapshot(spec(), rows, 0, False)
    assert result["state"] == "CAP_TRUNCATED"
    assert result["cap_suspected"] is True
    assert result["reached_start"] is False


def test_snapshot_complete_only_when_requested_start_is_reached():
    row = probe.candle_to_row(event(time=int(START.timestamp() * 1000)), spec())
    result = probe.classify_snapshot(spec(), [row], 0, False)
    assert result["state"] == "COMPLETE"
    assert result["reached_start"] is True


def test_launcher_is_off_by_default(monkeypatch):
    monkeypatch.delenv("VALOR_MES_DXLINK_CANDLE_PROBE_AUTORUN", raising=False)
    assert probe.launch_if_enabled() is False


def test_module_has_no_order_or_account_imports():
    source = Path(probe.__file__).read_text(encoding="utf-8")
    assert "tastytrade.account" not in source
    assert "tastytrade.order" not in source
    assert "trading.valor.executor" not in source
    assert "CHECK (interval IN ('1m','5m','15m','1h'))" in source
