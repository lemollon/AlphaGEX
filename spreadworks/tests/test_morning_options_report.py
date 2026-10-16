from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend import morning_options_report as report

UTC = timezone.utc

@pytest.fixture(autouse=True)
def isolate_live_collectors(monkeypatch):
    from backend import market_structure as ms
    from backend import tradier_report_source as src
    from backend import report_refresh
    # Morning-plan unit tests do not make unrelated live macro/flow requests.
    # Actual refresh, full assembly and flow integration have dedicated suites.
    async def context(*args):return []
    async def core(value):return value, []
    monkeypatch.setattr(report_refresh, 'refresh_context', context)
    monkeypatch.setattr(report_refresh, 'refresh_core', core)
    monkeypatch.setattr(ms,'fetch_spot',lambda *a,**k: {'fresh':False,'reason':'No live quote in unit test'})
    monkeypatch.setattr(src,'get',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('No live requests in unit test')))



def _evidence(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "price": 101.5,
        "source": "Tradier production consolidated feed",
        "session": "premarket",
        "exchange_timestamp": "2026-09-22T12:00:00+00:00",
        "retrieval_timestamp": "2026-09-22T12:00:05+00:00",
        "quote_age_seconds": 5.0,
        "newest_completed_bar_timestamp": "2026-09-22T11:59:00+00:00",
        "newest_completed_bar_age_seconds": 65.0,
        "session_low": 99.0,
        "session_high": 102.0,
        "usable_for_actionable_levels": True,
    }


def _research() -> dict:
    return {
        "market_regime": "selective",
        "confidence": "medium",
        "spy_bias": "conditional bullish",
        "qqq_bias": "conditional bullish",
        "vix_regime": "unavailable",
        "gamma_regime": "positive",
        "overnight_change": "mixed",
        "flow_and_iv": "unavailable before the options open",
        "best_setup": "AMD call debit spread after confirmation",
        "what_changes_my_mind": ["A completed bar closes below the session low."],
        "recommendations": [{
            "symbol": "AMD", "rank": 1, "status": "actionable",
            "strategy": "call_debit_spread", "thesis": "bullish",
            "thesis_reason": "Current catalyst and relative strength align.",
            "catalyst": "Current company news.",
            "expiration_preference": "7-14 DTE",
            "profit_taking_framework": "Take partial gains near 50%.",
            "main_risks": "Gap and liquidity risk.",
        }],
        "watch_only": [],
        "news_sources": [{"title": "Current source", "url": "https://example.com/current"}],
    }


def test_extract_json_accepts_fenced_object():
    assert report._extract_json('```json\n{"recommendations": []}\n```') == {
        "recommendations": []
    }


def test_normalize_plan_binds_model_choice_to_fresh_tradier_levels():
    now = datetime(2026, 9, 22, 12, 0, 5, tzinfo=UTC)
    symbols, setups, rejected = report._normalize_plan(
        _research(), {"AMD": _evidence("AMD")}, now.date(), now,
    )
    assert symbols == ["AMD"]
    assert rejected == []
    assert setups[0]["entry"] == {
        "type": "opening_range_breakout",
        "range_high": 102.0,
        "confirmation_bars": 2,
    }
    assert setups[0]["invalidation"] == {"type": "close_below", "level": 99.0}
    assert setups[0]["source_metadata"]["underlying_source"].startswith("Tradier")


def test_normalize_plan_rejects_actionable_idea_without_fresh_levels():
    now = datetime(2026, 9, 22, 12, 0, 5, tzinfo=UTC)
    stale = _evidence("AMD")
    stale["usable_for_actionable_levels"] = False
    symbols, setups, rejected = report._normalize_plan(
        _research(), {"AMD": stale}, now.date(), now,
    )
    assert symbols == []
    assert setups == []
    assert rejected == ["AMD: fresh quote/bar evidence unavailable"]


@pytest.mark.asyncio
async def test_cloud_run_persists_one_atomic_plan_and_posts_digest(monkeypatch):
    now = datetime(2026, 9, 22, 12, 0, 5, tzinfo=UTC)
    stored: dict = {}
    delivered: dict = {}

    monkeypatch.setattr(report, "is_market_holiday", lambda _day: False)
    monkeypatch.setattr(report, "_latest_plan_payload", lambda _day: None)
    monkeypatch.setattr(report, "_load_trading_volatility_context", lambda _now: {
        "available": True,
        "source": "TradingVolatility v2 API",
        "top_setups": [{"ticker": "AMD", "rank": 1}],
        "universe_count": 1,
        "retrieval_timestamp": now.isoformat(),
    })

    async def collect(_app, symbols, _now):
        return {symbol: _evidence(symbol) for symbol in symbols}

    async def generate(_now, _tv, _evidence_by_symbol):
        return _research()

    def store(trading_date, symbols, setups, payload, *, ingested_at):
        stored.update(
            trading_date=trading_date, symbols=symbols, setups=setups,
            payload=payload, ingested_at=ingested_at,
        )
        return {
            "trading_date": trading_date.isoformat(),
            "persisted": True,
            "registered_symbol_count": len(symbols),
            "registered_setup_count": len(setups),
            "registered_total_symbol_count": 4 + len(symbols),
            "plan_hash": "a" * 64,
            "ingested_at": ingested_at.isoformat(),
            "parity": {"valid": True},
        }

    monkeypatch.setattr(report, "_collect_market_evidence", collect)
    monkeypatch.setattr(report, "_generate_research", generate)
    monkeypatch.setattr(report, "store_morning_plan_atomic", store)
    monkeypatch.setattr(report, "_send_discord", lambda payload: payload["run_status"] == "SUCCESS")
    monkeypatch.setattr(
        report, "_update_delivery",
        lambda trading_date, *, posted, attempted_at: delivered.update(
            trading_date=trading_date, posted=posted, attempted_at=attempted_at,
        ),
    )

    result = await report.run_morning_options_report(SimpleNamespace(), now=now)

    assert result["run_status"] == "SUCCESS"
    assert result["symbols"] == ["AMD"]
    assert len(result["setups"]) == 1
    assert stored["payload"]["generated_by"] == report.GENERATOR_ID
    assert delivered["posted"] is True


@pytest.mark.asyncio
async def test_generation_error_publishes_deterministic_fallback_plan(monkeypatch):
    now = datetime(2026, 9, 22, 12, 0, 5, tzinfo=UTC)
    stored: dict = {}

    monkeypatch.setattr(report, "is_market_holiday", lambda _day: False)
    monkeypatch.setattr(report, "_latest_plan_payload", lambda _day: None)
    monkeypatch.setattr(report, "_load_trading_volatility_context", lambda _now: {
        "available": False, "top_setups": [],
    })

    async def collect(_app, symbols, _now):
        return {symbol: _evidence(symbol) for symbol in symbols}

    async def fail(*_args):
        raise RuntimeError("provider unavailable")

    def store(trading_date, symbols, setups, payload, *, ingested_at):
        stored.update(symbols=symbols, setups=setups, payload=payload)
        return {
            "trading_date": trading_date.isoformat(), "persisted": True,
            "registered_symbol_count": 0, "registered_setup_count": 0,
            "registered_total_symbol_count": 4, "plan_hash": "b" * 64,
            "ingested_at": ingested_at.isoformat(), "parity": {"valid": True},
        }

    monkeypatch.setattr(report, "_collect_market_evidence", collect)
    monkeypatch.setattr(report, "_generate_research", fail)
    monkeypatch.setattr(report, "store_morning_plan_atomic", store)
    monkeypatch.setattr(report, "_send_discord", lambda _payload: False)
    monkeypatch.setattr(report, "_update_delivery", lambda *_args, **_kwargs: None)

    result = await report.run_morning_options_report(SimpleNamespace(), now=now)

    # Since #3068 a model failure publishes a fresh-data-only plan with no
    # actionable setups instead of failing closed.
    assert result["run_status"] == "SUCCESS"
    assert stored["payload"]["generation_mode"] == "deterministic_fresh_data"
    assert stored["setups"] == []
    assert "provider unavailable" not in stored["payload"]["reason"]


@pytest.mark.asyncio
async def test_completed_plan_retries_a_failed_discord_delivery(monkeypatch):
    now = datetime(2026, 9, 22, 12, 10, 5, tzinfo=UTC)
    existing = {
        "generated_by": report.GENERATOR_ID,
        "run_status": "SUCCESS",
        "generation_mode": "model_enriched",
        "symbols": ["AMD"], "setups": [], "plan_hash": "c" * 64,
        "discord_delivery": {"posted": False, "attempt_count": 1},
    }
    updated: dict = {}
    monkeypatch.setenv("INTRADAY_ALERTS_ENABLED", "true")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    monkeypatch.setattr(report, "_latest_plan_payload", lambda _day: existing)
    monkeypatch.setattr(report, "_send_discord", lambda payload: payload is existing)
    monkeypatch.setattr(
        report, "_update_delivery",
        lambda trading_date, *, posted, attempted_at: updated.update(
            trading_date=trading_date, posted=posted, attempted_at=attempted_at,
        ),
    )

    result = await report.run_morning_options_report(SimpleNamespace(), now=now)

    assert result["skipped"] is True
    assert result["discord_posted"] is True
    assert updated["posted"] is True


def test_register_arms_exact_central_time_schedule(monkeypatch):
    calls = []

    class Scheduler:
        def add_job(self, fn, trigger, **kwargs):
            calls.append((fn, trigger, kwargs))

        def get_job(self, _job_id):
            return None

    monkeypatch.setenv("MORNING_OPTIONS_CLOUD_ENABLED", "true")
    monkeypatch.setattr(report, "_latest_plan_payload", lambda _day: {
        "generated_by": report.GENERATOR_ID, "run_status": "SUCCESS",
    })
    assert report.register(Scheduler(), SimpleNamespace()) is True
    cron = next(item for item in calls if item[2].get("id") == report.JOB_ID)
    assert cron[1] == "cron"
    assert cron[2]["hour"] == 7
    assert cron[2]["minute"] == "35,45,55"
    assert cron[2]["day_of_week"] == "mon-fri"
    assert cron[2]["max_instances"] == 1


# ---- model-call hardening -------------------------------------------------

class _Block(SimpleNamespace):
    pass


class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def get_final_message(self):
        if isinstance(self._message, Exception):
            raise self._message
        return self._message


class _FakeClient:
    def __init__(self, responses, calls, init_kwargs=None):
        self._responses = responses
        self.calls = calls
        self.init_kwargs = init_kwargs or {}
        self.messages = self

    def with_options(self, **kwargs):
        self.calls.append(("options", kwargs))
        return self

    def stream(self, **kwargs):
        self.calls.append(("stream", kwargs))
        return _FakeStream(self._responses.pop(0))


def _install_fake_anthropic(monkeypatch, responses):
    import sys
    calls: list = []
    holder: dict = {}

    def factory(**kwargs):
        holder["client"] = _FakeClient(responses, calls, kwargs)
        return holder["client"]

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=factory))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    return calls, holder


def _msg(stop_reason, *texts):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[_Block(type="text", text=t) for t in texts],
    )


def test_claude_request_streams_with_retries_and_long_timeout(monkeypatch):
    calls, holder = _install_fake_anthropic(monkeypatch, [_msg("end_turn", '{"confidence": 60}')])
    monkeypatch.delenv("MORNING_OPTIONS_MODEL_TIMEOUT_SECONDS", raising=False)

    assert report._claude_request("p") == {"confidence": 60}
    assert holder["client"].init_kwargs["max_retries"] == 2
    assert holder["client"].init_kwargs["timeout"] >= 240
    stream_kwargs = [c[1] for c in calls if c[0] == "stream"][0]
    assert stream_kwargs["tools"][0]["name"] == "web_search"


def test_claude_request_resumes_pause_turn(monkeypatch):
    paused = _msg("pause_turn", "searching...")
    calls, _ = _install_fake_anthropic(monkeypatch, [paused, _msg("end_turn", '{"confidence": 70}')])

    assert report._claude_request("p") == {"confidence": 70}
    streams = [c[1] for c in calls if c[0] == "stream"]
    assert len(streams) == 2
    assert streams[1]["messages"][1] == {"role": "assistant", "content": paused.content}


def test_claude_request_falls_back_to_plain_request(monkeypatch):
    calls, _ = _install_fake_anthropic(
        monkeypatch, [RuntimeError("tool rejected"), _msg("end_turn", '{"confidence": 55}')],
    )
    assert report._claude_request("p") == {"confidence": 55}
    streams = [c[1] for c in calls if c[0] == "stream"]
    assert "tools" in streams[0] and "tools" not in streams[1]


def test_claude_request_stops_at_deadline(monkeypatch):
    calls, _ = _install_fake_anthropic(monkeypatch, [])
    monkeypatch.setenv("MORNING_OPTIONS_MODEL_DEADLINE_SECONDS", "0")
    with pytest.raises(RuntimeError, match="TimeoutError"):
        report._claude_request("p")
    assert not [c for c in calls if c[0] == "stream"]


def _patch_run(monkeypatch, existing, research):
    stored: dict = {}
    posted: list = []
    monkeypatch.setattr(report, "is_market_holiday", lambda _day: False)
    monkeypatch.setattr(report, "_latest_plan_payload", lambda _day: existing)
    monkeypatch.setattr(report, "_load_trading_volatility_context", lambda _now: {
        "available": False, "top_setups": [],
    })

    async def collect(_app, symbols, _now):
        return {symbol: _evidence(symbol) for symbol in symbols}

    def store(trading_date, symbols, setups, payload, *, ingested_at):
        stored.update(symbols=symbols, setups=setups, payload=payload)
        return {
            "trading_date": trading_date.isoformat(), "persisted": True,
            "registered_symbol_count": 0, "registered_setup_count": 0,
            "registered_total_symbol_count": 4, "plan_hash": "c" * 64,
            "ingested_at": ingested_at.isoformat(), "parity": {"valid": True},
        }

    monkeypatch.setattr(report, "_collect_market_evidence", collect)
    monkeypatch.setattr(report, "_generate_research", research)
    monkeypatch.setattr(report, "store_morning_plan_atomic", store)
    monkeypatch.setattr(report, "_send_discord", lambda payload: posted.append(payload) or False)
    monkeypatch.setattr(report, "_update_delivery", lambda *_args, **_kwargs: None)
    return stored, posted


_FALLBACK_PLAN = {
    "generated_by": report.GENERATOR_ID, "run_status": "SUCCESS",
    "generation_mode": "deterministic_fresh_data", "attempt": 1,
    "symbols": [], "setups": [], "plan_hash": "a" * 64,
}


async def test_retry_tick_upgrades_fallback_plan_when_model_answers(monkeypatch):
    now = datetime(2026, 9, 22, 12, 10, 5, tzinfo=timezone.utc)

    async def ok(*_args):
        return report._deterministic_research({"available": False}, {}, "")

    stored, _ = _patch_run(monkeypatch, dict(_FALLBACK_PLAN), ok)
    result = await report.run_morning_options_report(SimpleNamespace(), now=now)

    assert not result.get("skipped")
    assert stored["payload"]["generation_mode"] == "model_enriched"
    assert stored["payload"]["attempt"] == 2


async def test_retry_tick_keeps_fallback_plan_when_model_fails_again(monkeypatch):
    now = datetime(2026, 9, 22, 12, 10, 5, tzinfo=timezone.utc)

    async def fail(*_args):
        raise RuntimeError("still down")

    stored, posted = _patch_run(monkeypatch, dict(_FALLBACK_PLAN), fail)
    result = await report.run_morning_options_report(SimpleNamespace(), now=now)

    assert result["skipped"] is True
    assert stored == {} and posted == []


async def test_model_enriched_plan_still_blocks_retry_ticks(monkeypatch):
    now = datetime(2026, 9, 22, 12, 10, 5, tzinfo=timezone.utc)
    existing = dict(_FALLBACK_PLAN, generation_mode="model_enriched")

    async def never(*_args):
        raise AssertionError("should not regenerate")

    stored, _ = _patch_run(monkeypatch, existing, never)
    result = await report.run_morning_options_report(SimpleNamespace(), now=now)
    assert result["skipped"] is True and stored == {}


async def test_a_losing_tick_claim_skips_generation_entirely(monkeypatch):
    """Leron, 2026-10-16: "im getting duplicate reports" -- confirmed real, 3 full
    kind="morning" reports archived within 10 seconds of each other. Root cause: if more
    than one worker process executes the SAME cron tick concurrently, each one reads
    "not yet complete" before any of them writes back, and each generates and sends its
    own full report. claim_delivery_tick() (minute-granularity, not the hourly
    claim_delivery() used by intraday/market_open, which would block the legitimate
    07:35->07:45->07:55 sequential retry this job is designed to do) should let only one
    caller per exact tick actually run the generation. True concurrent-thread races
    can't be exercised reliably against this test suite's sqlite-in-memory engine --
    SingletonThreadPool gives each OS thread its own disconnected `:memory:` database,
    so two genuinely concurrent asyncio.to_thread() callers never see each other's claim
    row at all (a sqlite test-harness limitation; production is Postgres, where the
    UPDATE ... WHERE's row lock inside one transaction does serialize real concurrent
    callers). This instead claims the tick directly first (same thread, deterministic),
    then verifies the wrapper correctly treats that as "another worker already has it"
    and skips the generation -- the exact behavior a losing concurrent caller must have."""
    now = datetime(2026, 9, 22, 12, 10, 5, tzinfo=timezone.utc)

    async def never(*_args):
        raise AssertionError("a losing claim must never reach generation")

    stored, _ = _patch_run(monkeypatch, None, never)

    # The real code path dispatches claim_delivery_tick/finish_delivery via
    # asyncio.to_thread so DB calls never block the event loop. This suite's sqlite
    # :memory: engine uses SingletonThreadPool (one disconnected database PER THREAD),
    # so this test's own pre-claim (on the main test thread) and the wrapper's claim
    # (on a to_thread worker) would never see the same row unless both run on the same
    # thread -- a sqlite test-harness limitation, not a production concern (production
    # is Postgres, a real shared database regardless of thread). Make to_thread run
    # synchronously on the calling thread for this test only.
    import asyncio
    async def same_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)
    monkeypatch.setattr(asyncio, "to_thread", same_thread)

    from backend.full_options_report import claim_delivery_tick
    pre_claimed = claim_delivery_tick("morning", now)
    assert pre_claimed is not None  # sanity: this test's own claim succeeded

    result = await report.run_morning_options_report(SimpleNamespace(), now=now)

    assert result == {"skipped": True, "reason": "another worker already claimed this tick"}
    assert stored == {}


async def test_different_tick_calls_each_proceed_independently(monkeypatch):
    """A second call one minute later (a legitimate 07:35 -> 07:45 retry, or simply a
    different tick) must NOT be blocked by the first tick's lease -- only the exact same
    tick is deduplicated."""
    now1 = datetime(2026, 9, 22, 12, 10, 5, tzinfo=timezone.utc)
    now2 = datetime(2026, 9, 22, 12, 11, 5, tzinfo=timezone.utc)
    run_count = {"n": 0}

    async def ok(*_args):
        run_count["n"] += 1
        return report._deterministic_research({"available": False}, {}, "")

    stored, _ = _patch_run(monkeypatch, None, ok)

    result1 = await report.run_morning_options_report(SimpleNamespace(), now=now1)
    result2 = await report.run_morning_options_report(SimpleNamespace(), now=now2)

    assert not result1.get("skipped") and not result2.get("skipped")
    assert run_count["n"] == 2
