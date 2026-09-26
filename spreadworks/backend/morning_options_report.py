"""Cloud-owned 07:00 CT morning options plan generator.

The Render web service owns research and plan registration.  The dedicated
``qqq-retest-worker`` remains the only intraday evaluator.  This module never
imports broker order code and never places, routes, changes, or cancels orders.

Safety boundaries:

* current Tradier quotes and completed one-minute bars are the only source of
  machine-actionable price levels;
* Trading Volatility is discovery/context only;
* Claude may rank structures and summarize current news, but it cannot invent
  trigger prices, quotes, Greeks, or option premiums;
* missing/stale evidence or an invalid model response publishes a durable empty
  technical-failure plan, so the watcher fails closed instead of reusing an old
  plan.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .db import SessionLocal
from .economic_events import is_market_holiday
from .intraday_watch import (
    CORE_SYMBOLS,
    STRATEGIES,
    fetch_symbol_market,
    store_morning_plan_atomic,
    validate_plan_parity,
    validate_setup,
    validate_watchlist,
)
from .models import IntradayTradePlan, QQQWatchRuntimeStatus

logger = logging.getLogger(__name__)
UTC = timezone.utc
CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")

GENERATOR_ID = "render-cloud-morning-options-v1"
JOB_ID = "cloud_morning_options_0700_ct"
FALLBACK_UNIVERSE = ("AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD", "NFLX")
_SCHEDULER: dict[str, Any] = {"ref": None}
_LAST_RUN: dict[str, Any] = {
    "started_at": None,
    "finished_at": None,
    "trading_date": None,
    "run_status": "NEVER_RUN",
    "reason": None,
    "plan_hash": None,
    "registered_symbol_count": 0,
    "registered_setup_count": 0,
    "discord_posted": None,
}


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _age_seconds(now: datetime, then: datetime | None) -> float | None:
    if then is None:
        return None
    return max(0.0, (now.astimezone(UTC) - then.astimezone(UTC)).total_seconds())


def _latest_plan_payload(trading_date: date) -> dict[str, Any] | None:
    if SessionLocal is None:
        return None
    db = SessionLocal()
    try:
        row = db.get(IntradayTradePlan, trading_date)
        return json.loads(row.payload_json) if row else None
    except (json.JSONDecodeError, TypeError):
        return None
    finally:
        db.close()


def _load_trading_volatility_context(now: datetime) -> dict[str, Any]:
    """Read the worker's current vendor context without calling it a signal."""
    unavailable = {
        "available": False,
        "source": "TradingVolatility v2 API",
        "symbols": [],
        "top_setups": [],
        "reason": "worker context is unavailable",
    }
    if SessionLocal is None:
        return {**unavailable, "reason": "database is not configured"}
    db = SessionLocal()
    try:
        row = db.get(QQQWatchRuntimeStatus, "qqq-retest")
        if row is None:
            return unavailable
        heartbeat = row.heartbeat_at
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=UTC)
        heartbeat_age = _age_seconds(now, heartbeat)
        payload = json.loads(row.payload_json)
        tv = dict(payload.get("trading_volatility") or {})
        accepted = bool(tv.get("available")) and heartbeat_age is not None and heartbeat_age <= 120
        if not accepted:
            reason = tv.get("last_error") or (
                f"worker heartbeat is {heartbeat_age:.1f}s old" if heartbeat_age is not None
                else "worker heartbeat is unavailable"
            )
            return {
                **unavailable,
                "configured": tv.get("configured"),
                "retrieval_timestamp": tv.get("retrieval_timestamp"),
                "worker_heartbeat_at": _iso(heartbeat),
                "worker_heartbeat_age_seconds": heartbeat_age,
                "reason": reason,
            }
        tv.update(
            accepted_for_discovery=True,
            worker_heartbeat_at=_iso(heartbeat),
            worker_heartbeat_age_seconds=round(float(heartbeat_age), 1),
        )
        return tv
    except (json.JSONDecodeError, TypeError) as exc:
        return {**unavailable, "reason": f"worker context was unreadable: {type(exc).__name__}"}
    finally:
        db.close()


def _candidate_symbols(tv: dict[str, Any]) -> tuple[list[str], str]:
    limit = max(5, min(20, int(os.getenv("MORNING_OPTIONS_CANDIDATE_LIMIT", "12"))))
    ranked: list[str] = []
    if tv.get("available"):
        for item in tv.get("top_setups") or []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("ticker") or "").strip().upper()
            if symbol and symbol not in ranked and symbol not in {"VIX", *CORE_SYMBOLS}:
                ranked.append(symbol)
            if len(ranked) >= limit:
                break
    if ranked:
        return ranked, "TradingVolatility v2 liquid-options roster"
    return list(FALLBACK_UNIVERSE[:limit]), "liquid-ticker fallback; Trading Volatility unavailable"


def _completed_bar_evidence(market: dict[str, Any], now: datetime) -> dict[str, Any]:
    bars = sorted(market.get("bars") or [], key=lambda item: item.timestamp)
    current_minute = now.astimezone(UTC).replace(second=0, microsecond=0)
    completed = [bar for bar in bars if bar.timestamp.astimezone(UTC) < current_minute]
    newest = completed[-1] if completed else None
    bar_age = _age_seconds(now, newest.timestamp if newest else None)
    quote_fresh = bool(market.get("fresh"))
    bars_fresh = bar_age is not None and bar_age <= 90
    usable = quote_fresh and bars_fresh and len(completed) >= 2
    lows = [float(item.low) for item in completed]
    highs = [float(item.high) for item in completed]
    session_low = min(lows) if lows else None
    session_high = max(highs) if highs else None
    if session_low is None or session_high is None or session_low >= session_high:
        usable = False
    return {
        "symbol": market.get("symbol"),
        "price": round(float(market["price"]), 4) if market.get("price") is not None else None,
        "price_basis": market.get("price_basis"),
        "source": market.get("source"),
        "session": market.get("session"),
        "exchange_timestamp": market.get("exchange_timestamp"),
        "retrieval_timestamp": market.get("retrieval_timestamp"),
        "quote_age_seconds": market.get("age_seconds"),
        "quote_fresh": quote_fresh,
        "newest_completed_bar_timestamp": _iso(newest.timestamp) if newest else None,
        "newest_completed_bar_age_seconds": round(float(bar_age), 1) if bar_age is not None else None,
        "completed_bar_count": len(completed),
        "session_low": round(session_low, 4) if session_low is not None else None,
        "session_high": round(session_high, 4) if session_high is not None else None,
        "last_completed_close": round(float(newest.close), 4) if newest else None,
        "usable_for_actionable_levels": usable,
        "unavailable_reason": None if usable else (
            "requires a fresh quote and at least two completed one-minute bars, with the newest bar no more than 90 seconds old"
        ),
    }


async def _collect_market_evidence(app: Any, symbols: list[str], now: datetime) -> dict[str, dict[str, Any]]:
    semaphore = asyncio.Semaphore(5)

    async def one(symbol: str) -> tuple[str, dict[str, Any]]:
        async with semaphore:
            try:
                market = await fetch_symbol_market(app, symbol, now)
                return symbol, _completed_bar_evidence(market, now)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[MorningOptions] %s market evidence unavailable: %s", symbol, type(exc).__name__)
                return symbol, {
                    "symbol": symbol,
                    "usable_for_actionable_levels": False,
                    "unavailable_reason": f"market evidence unavailable ({type(exc).__name__})",
                }

    pairs = await asyncio.gather(*(one(symbol) for symbol in symbols))
    return dict(pairs)


def _trim_tv_context(tv: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
    wanted = set(symbols)
    return {
        "available": bool(tv.get("available")),
        "source": tv.get("source"),
        "role": tv.get("role"),
        "retrieval_timestamp": tv.get("retrieval_timestamp"),
        "worker_heartbeat_at": tv.get("worker_heartbeat_at"),
        "worker_heartbeat_age_seconds": tv.get("worker_heartbeat_age_seconds"),
        "universe_count": tv.get("universe_count"),
        "symbol_context": tv.get("symbol_context"),
        "top_setups": [
            item for item in (tv.get("top_setups") or [])
            if isinstance(item, dict) and item.get("ticker") in wanted
        ],
        "reason": tv.get("reason") or tv.get("last_error"),
    }


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model response did not contain a JSON object")
        parsed = json.loads(cleaned[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model response must be a JSON object")
    return parsed


def _claude_request(prompt: str) -> dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    import anthropic

    timeout = float(os.getenv("MORNING_OPTIONS_MODEL_TIMEOUT_SECONDS", "45"))
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)
    model = os.getenv("MORNING_OPTIONS_MODEL", "claude-sonnet-4-6")
    text = ""

    # First try the richer request with web search. Some provider/model
    # combinations reject the web-search tool schema, so fall back immediately
    # to a plain JSON request instead of failing the entire morning report.
    attempts = (
        {"tools": [{"type": "web_search_20260209", "name": "web_search"}]},
        {},
    )
    last_exc: Exception | None = None
    for extra in attempts:
        try:
            response = client.messages.create(
                model=model,
                max_tokens=5000,
                messages=[{"role": "user", "content": prompt}],
                **extra,
            )
            for block in response.content:
                if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                    text = block.text.strip()
            if text:
                return _extract_json(text)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "[MorningOptions] model enrichment attempt failed: %s",
                type(exc).__name__,
            )
    raise RuntimeError(
        f"model enrichment unavailable ({type(last_exc).__name__ if last_exc else 'empty_response'})"
    )


def _deterministic_research(tv: dict[str, Any],
                            evidence: dict[str, dict[str, Any]],
                            reason: str) -> dict[str, Any]:
    """Fresh-data-only fallback when optional model enrichment is unavailable."""
    fresh = [
        (symbol, item) for symbol, item in evidence.items()
        if item.get("usable_for_actionable_levels")
    ]
    spy = evidence.get("SPY") or {}
    qqq = evidence.get("QQQ") or {}
    watch = []
    if reason:
        watch.append(f"Model enrichment unavailable: {reason}")
    if not fresh:
        regime = "DATA UNAVAILABLE — no symbol passed the fresh quote/bar gate"
        confidence = 0
        best = "No Trade"
    else:
        regime = "Fresh market evidence available; directional conviction deferred to opening-range confirmation"
        confidence = 50
        best = "Use objective fresh session-range triggers; no model-ranked setup"
    if not tv.get("available"):
        watch.append(f"Trading Volatility unavailable: {tv.get('reason') or 'worker context unavailable'}")
    return {
        "market_regime": regime,
        "confidence": confidence,
        "spy_bias": "conditional" if spy.get("usable_for_actionable_levels") else "unavailable",
        "qqq_bias": "conditional" if qqq.get("usable_for_actionable_levels") else "unavailable",
        "vix_regime": "unavailable unless current-session VIX passed freshness validation",
        "gamma_regime": "unavailable in deterministic fallback",
        "overnight_change": "Use attached fresh Tradier market_evidence; no model inference applied.",
        "flow_and_iv": "unavailable in deterministic fallback",
        "best_setup": best,
        "what_changes_my_mind": [
            "A confirmed break/hold of the fresh premarket range with current data.",
            "Loss of quote or completed-bar freshness.",
        ],
        "recommendations": [],
        "watch_only": watch,
        "news_sources": [],
    }


async def _generate_research(now: datetime, tv: dict[str, Any],
                             evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    usable = [symbol for symbol, item in evidence.items() if item.get("usable_for_actionable_levels")]
    prompt = f"""
You are the cloud research layer for an advisory-only U.S. options alert system.
Today is {now.astimezone(CT).isoformat()} (America/Chicago). Use web_search for TODAY'S
market-moving news, scheduled macro/Fed events, rates, oil, dollar, and company catalysts.

Hard evidence rules:
- The attached Tradier evidence is the only allowed source for current prices and numeric trigger levels.
- Trading Volatility is discovery and positioning context only, never a directional trigger.
- Do not invent or infer bid, ask, IV, IV rank, Greeks, flow, option premiums, probabilities, or exact strikes.
- Options are closed at report time; exact contracts are selected later by Render only after a trigger and a fresh authorized chain.
- Recommend No Trade or Watch Only when confirmation is insufficient.
- Prefer defined-risk structures.
- Every actionable recommendation must use a symbol in usable_symbols and one supported strategy.
- Actionable non-core recommendations should normally total 5-8, but fewer or zero is correct when evidence does not justify them.

usable_symbols={json.dumps(usable)}
supported_strategies={json.dumps(sorted(STRATEGIES))}
trading_volatility={json.dumps(tv, default=str, separators=(',', ':'))}
tradier_market_evidence={json.dumps(evidence, default=str, separators=(',', ':'))}

Return ONE plain JSON object and nothing else with exactly these top-level keys:
market_regime, confidence, spy_bias, qqq_bias, vix_regime, gamma_regime,
overnight_change, flow_and_iv, best_setup, what_changes_my_mind,
recommendations, watch_only, news_sources.

recommendations is an array. Each item must contain:
symbol, rank, status (actionable or watch_only), strategy, thesis (bullish, bearish, or neutral),
thesis_reason, catalyst, expiration_preference, profit_taking_framework, main_risks.
Do not put numeric trigger prices in the response; the server deterministically binds
actionable ideas to the fresh session high/low supplied above.

watch_only is an array of concise strings. news_sources is an array of objects with
title and url. Keep every prose field concise and factual. If a requested input is not
available, literally say unavailable rather than estimating it.
""".strip()
    return await asyncio.to_thread(_claude_request, prompt)


def _compatible_strategy(strategy: str, thesis: str) -> bool:
    by_thesis = {
        "bullish": {"long_call", "call_debit_spread", "put_credit_spread"},
        "bearish": {"long_put", "put_debit_spread", "call_credit_spread"},
        "neutral": {"iron_condor", "calendar", "double_calendar"},
    }
    return strategy in by_thesis.get(thesis, set())


def _default_delta_profile(strategy: str) -> dict[str, list[float]]:
    if strategy in {"put_credit_spread", "call_credit_spread", "iron_condor"}:
        return {"short": [0.15, 0.25], "long": [0.05, 0.15]}
    if strategy in {"calendar", "double_calendar"}:
        return {"near": [0.35, 0.50], "far": [0.35, 0.50]}
    return {"long": [0.50, 0.65], "short": [0.25, 0.40]}


def _default_profit_framework(strategy: str) -> str:
    if strategy in {"put_credit_spread", "call_credit_spread", "iron_condor"}:
        return "Consider taking 50-70% of the available credit; exit on invalidation or before late-day assignment risk."
    if strategy in {"calendar", "double_calendar"}:
        return "Consider taking gains after a 20-30% increase in structure value; exit on invalidation or a volatility-regime break."
    return "Consider taking partial gains near 50%; exit the remainder on invalidation or before 15:30 ET."


def _build_setup(item: dict[str, Any], evidence: dict[str, Any],
                 trading_date: date, now: datetime) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "").strip().upper()
    strategy = str(item.get("strategy") or "").strip().lower().replace(" ", "_")
    thesis = str(item.get("thesis") or "").strip().lower()
    if strategy not in STRATEGIES or not _compatible_strategy(strategy, thesis):
        raise ValueError(f"{symbol}: strategy {strategy!r} is incompatible with thesis {thesis!r}")
    low = float(evidence["session_low"])
    high = float(evidence["session_high"])
    if thesis == "bullish":
        entry = {"type": "opening_range_breakout", "range_high": high, "confirmation_bars": 2}
        invalidation = {"type": "close_below", "level": low}
    elif thesis == "bearish":
        entry = {
            "type": "opening_range_rejection", "range_low": low,
            "range_high": high, "confirmation_bars": 2,
        }
        invalidation = {"type": "close_above", "level": high}
    else:
        entry = {
            "type": "opening_range_hold", "range_low": low,
            "range_high": high, "confirmation_bars": 10,
        }
        invalidation = {"type": "none"}
    expires = datetime.combine(trading_date, time(16, 0), ET)
    source_metadata = {
        "underlying_source": evidence.get("source"),
        "session": evidence.get("session"),
        "exchange_timestamp": evidence.get("exchange_timestamp"),
        "retrieval_timestamp": evidence.get("retrieval_timestamp"),
        "quote_age_seconds": evidence.get("quote_age_seconds"),
        "newest_completed_bar_timestamp": evidence.get("newest_completed_bar_timestamp"),
        "newest_completed_bar_age_seconds": evidence.get("newest_completed_bar_age_seconds"),
        "level_basis": "fresh completed premarket one-minute session range",
    }
    raw = {
        "setup_id": f"cloud-{symbol.lower()}-{strategy}",
        "symbol": symbol,
        "strategy": strategy,
        "thesis": thesis,
        "entry": entry,
        "invalidation": invalidation,
        "support_levels": [low],
        "resistance_levels": [high],
        "expiration_preference": str(item.get("expiration_preference") or "7-14 DTE"),
        "target_delta_profile": _default_delta_profile(strategy),
        "profit_taking_framework": str(
            item.get("profit_taking_framework") or _default_profit_framework(strategy)
        ),
        "max_risk_logic": "Defined-risk structure only; size from the fresh natural debit or spread width at review time.",
        "main_risks": str(item.get("main_risks") or "Gap risk, event risk, and option liquidity at trigger time."),
        "thesis_reason": str(item.get("thesis_reason") or "Current evidence-supported setup."),
        "catalyst": str(item.get("catalyst") or "No specific catalyst confirmed."),
        "source_metadata": source_metadata,
        "created_at": now.astimezone(UTC).isoformat(),
        "expires_at": expires.isoformat(),
        "sessions": ["regular"],
        "setup_state": "WAIT",
    }
    return validate_setup(raw, trading_date)


def _normalize_plan(research: dict[str, Any], evidence: dict[str, dict[str, Any]],
                    trading_date: date, now: datetime) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    setups: list[dict[str, Any]] = []
    rejected: list[str] = []
    seen: set[tuple[str, str]] = set()
    recommendations = research.get("recommendations")
    if not isinstance(recommendations, list):
        raise ValueError("recommendations must be an array")
    def rank(item: dict[str, Any]) -> int:
        try:
            return int(item.get("rank") or 999)
        except (TypeError, ValueError):
            return 999

    ordered = sorted(
        (item for item in recommendations if isinstance(item, dict)),
        key=rank,
    )
    for item in ordered:
        if str(item.get("status") or "").strip().lower() != "actionable":
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        market = evidence.get(symbol)
        if market is None or not market.get("usable_for_actionable_levels"):
            rejected.append(f"{symbol or 'UNKNOWN'}: fresh quote/bar evidence unavailable")
            continue
        strategy = str(item.get("strategy") or "").strip().lower().replace(" ", "_")
        identity = (symbol, strategy)
        if identity in seen:
            continue
        try:
            setup = _build_setup(item, market, trading_date, now)
        except (TypeError, ValueError) as exc:
            rejected.append(str(exc))
            continue
        setups.append(setup)
        seen.add(identity)

    non_core = []
    for setup in setups:
        if setup["symbol"] not in CORE_SYMBOLS and setup["symbol"] not in non_core:
            non_core.append(setup["symbol"])
    non_core = non_core[:8]
    setups = [item for item in setups if item["symbol"] in CORE_SYMBOLS or item["symbol"] in non_core]
    _, symbols = validate_watchlist({"trading_date": trading_date.isoformat(), "symbols": non_core})
    validate_plan_parity(symbols, setups)
    return symbols, setups, rejected


def _report_markdown(now: datetime, research: dict[str, Any], symbols: list[str],
                     setups: list[dict[str, Any]], rejected: list[str],
                     universe_source: str, tv: dict[str, Any]) -> str:
    def field(name: str, default: str = "unavailable") -> str:
        value = research.get(name)
        return str(value).strip() if value not in (None, "", []) else default

    lines = [
        f"# Morning Options Sentiment — {now.astimezone(CT).date().isoformat()}",
        "",
        "> Advisory only. Render registered objective underlying triggers; no order was routed.",
        "",
        "## 30-second dashboard",
        "",
        f"- Regime: {field('market_regime')} (confidence: {field('confidence')})",
        f"- SPY: {field('spy_bias')}",
        f"- QQQ: {field('qqq_bias')}",
        f"- VIX: {field('vix_regime')}",
        f"- Dealer gamma: {field('gamma_regime')}",
        f"- Overnight: {field('overnight_change')}",
        f"- Flow / IV: {field('flow_and_iv')}",
        f"- Best setup: {field('best_setup', 'No Trade')}",
        "",
        "## Render Live Watchlist",
        "",
        f"- Discovery source: {universe_source}",
        f"- Trading Volatility retrieval: {tv.get('retrieval_timestamp') or 'unavailable'}",
        f"- Trading Volatility universe count: {tv.get('universe_count') if tv.get('universe_count') is not None else 'unavailable'}",
        f"- Registered non-core symbols: {', '.join(symbols) if symbols else 'none'}",
        "",
        "## Registered actionable setups",
        "",
    ]
    if not setups:
        lines.append("No Trade — no recommendation passed the current-data and machine-rule gates.")
    else:
        for index, setup in enumerate(setups, 1):
            entry = setup["entry"]
            if entry["type"] == "opening_range_breakout":
                trigger = f"hold above {entry['range_high']:g} for {entry['confirmation_bars']} completed 1-minute bars"
            elif entry["type"] == "opening_range_rejection":
                trigger = (
                    f"reject {entry['range_low']:g}-{entry['range_high']:g} and close below it for "
                    f"{entry['confirmation_bars']} completed 1-minute bars"
                )
            else:
                trigger = (
                    f"hold inside {entry['range_low']:g}-{entry['range_high']:g} for "
                    f"{entry['confirmation_bars']} completed 1-minute bars"
                )
            lines.extend([
                f"{index}. **{setup['symbol']} — {setup['strategy'].replace('_', ' ').title()}**",
                f"   - Thesis: {setup['thesis']} — {setup.get('thesis_reason')}",
                f"   - Entry: {trigger}",
                f"   - Invalidation: {setup['invalidation']}",
                f"   - Expiration preference: {setup.get('expiration_preference')}",
                f"   - Profit framework: {setup.get('profit_taking_framework')}",
                f"   - Risk: {setup.get('main_risks')}",
                "   - Strikes: selected only after ENTRY_READY from a fresh authorized chain; otherwise STRIKES PENDING OPTIONS DATA.",
            ])
    changes = research.get("what_changes_my_mind")
    lines.extend(["", "## What would change my mind?", ""])
    if isinstance(changes, list) and changes:
        lines.extend(f"- {item}" for item in changes[:8])
    else:
        lines.append("- Fresh price action invalidating the registered levels or unavailable/stale market data.")
    watch = research.get("watch_only")
    lines.extend(["", "## Watch Only / rejected", ""])
    watch_items = ([str(item) for item in watch] if isinstance(watch, list) else []) + rejected
    lines.extend(f"- {item}" for item in watch_items[:12])
    if not watch_items:
        lines.append("- None.")
    sources = research.get("news_sources")
    lines.extend(["", "## Current news sources", ""])
    source_count = 0
    if isinstance(sources, list):
        for item in sources[:10]:
            if isinstance(item, dict) and item.get("title"):
                url = str(item.get("url") or "").strip()
                lines.append(f"- {item['title']}{f' — {url}' if url else ''}")
                source_count += 1
    if source_count == 0:
        lines.append("- unavailable")
    return "\n".join(lines).strip()


def _discord_embed(payload: dict[str, Any]) -> dict[str, Any]:
    setups = payload.get("setups") or []
    status = payload.get("run_status")
    if status == "SUCCESS" and setups:
        title = f"7:00 AM PLAN REGISTERED — {len(setups)} SETUP(S)"
        color = 0x34D399
    elif status == "SUCCESS":
        title = "7:00 AM PLAN REGISTERED — NO TRADE"
        color = 0xF59E0B
    else:
        title = (
            "7:00 AM PLAN FAILED CLOSED — MANUAL WATCHES PRESERVED"
            if setups else "7:00 AM PLAN FAILED CLOSED — NO ACTIVE SETUPS"
        )
        color = 0xEF4444
    setup_lines = []
    for setup in setups[:12]:
        entry = setup["entry"]
        levels = (
            entry.get("range_high") or entry.get("breakout_level")
            or f"{entry.get('range_low')}-{entry.get('range_high')}"
        )
        setup_lines.append(
            f"**{setup['symbol']}** {setup['strategy'].replace('_', ' ')} | "
            f"{setup['thesis']} | {entry['type']} {levels} | {entry['confirmation_bars']} bar(s)"
        )
    fields = [
        {"name": "Result", "value": str(payload.get("reason") or payload.get("best_setup") or "Plan stored."), "inline": False},
        {"name": "Actionable setups", "value": "\n".join(setup_lines)[:1024] if setup_lines else "None — No Trade.", "inline": False},
        {"name": "Registration", "value": (
            f"date {payload['trading_date']} | symbols {len(payload.get('symbols') or [])} | "
            f"setups {len(setups)} | hash {(payload.get('plan_hash') or 'unavailable')[:12]}"
        ), "inline": False},
        {"name": "Options", "value": (
            "Exact strikes are selected only after ENTRY_READY from fresh authorized chain/Greeks. "
            "Otherwise: ENTRY TRIGGER HIT — STRIKES PENDING OPTIONS DATA."
        ), "inline": False},
    ]
    return {
        "title": title,
        "description": "Render cloud run; advisory only; no order routing.",
        "color": color,
        "fields": fields,
        "timestamp": payload.get("generated_at"),
        "footer": {"text": "SpreadWorks Cloud Morning Options | 07:00 CT"},
    }


def _update_delivery(trading_date: date, *, posted: bool, attempted_at: datetime) -> None:
    if SessionLocal is None:
        return
    db = SessionLocal()
    try:
        row = db.get(IntradayTradePlan, trading_date)
        if row is None:
            return
        payload = json.loads(row.payload_json)
        payload["discord_delivery"] = {
            "configured": bool(
                os.getenv("INTRADAY_DISCORD_WEBHOOK_URL", "").strip()
                or os.getenv("DISCORD_WEBHOOK_URL", "").strip()
            ),
            "enabled": _truthy("INTRADAY_ALERTS_ENABLED"),
            "attempted_at": attempted_at.astimezone(UTC).isoformat(),
            "posted": posted,
        }
        row.payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[MorningOptions] could not persist Discord delivery result")
    finally:
        db.close()


def _send_discord(payload: dict[str, Any]) -> bool:
    from . import _send_intraday_webhook_sync
    return _send_intraday_webhook_sync(_discord_embed(payload))


def _failure_payload(now: datetime, reason: str, *, attempt: int) -> dict[str, Any]:
    return {
        "trading_date": now.astimezone(CT).date().isoformat(),
        "symbols": [],
        "setups": [],
        "created_at": now.astimezone(UTC).isoformat(),
        "expires_at": datetime.combine(now.astimezone(CT).date(), time(16, 0), ET).isoformat(),
        "generated_at": now.astimezone(UTC).isoformat(),
        "generated_by": GENERATOR_ID,
        "run_status": "FAILED_CLOSED",
        "attempt": attempt,
        "advisory_only": True,
        "reason": reason,
        "report_markdown": (
            f"# Morning Options Sentiment — {now.astimezone(CT).date().isoformat()}\n\n"
            f"No Trade — cloud generation failed closed: {reason}"
        ),
    }


async def run_morning_options_report(app: Any, *, now: datetime | None = None,
                                     force: bool = False) -> dict[str, Any]:
    """Generate, validate, atomically store, and notify one cloud morning plan."""
    started = (now or datetime.now(UTC)).astimezone(UTC)
    trading_date = started.astimezone(CT).date()
    _LAST_RUN.update(
        started_at=started.isoformat(), finished_at=None,
        trading_date=trading_date.isoformat(), run_status="RUNNING", reason=None,
    )
    existing = await asyncio.to_thread(_latest_plan_payload, trading_date)
    if (not force and existing and existing.get("generated_by") == GENERATOR_ID
            and existing.get("run_status") in {"SUCCESS", "SKIPPED_MARKET_CLOSED"}):
        result = {"skipped": True, "reason": "cloud morning plan already completed", **existing}
        _LAST_RUN.update(
            finished_at=datetime.now(UTC).isoformat(), run_status=existing.get("run_status"),
            reason=result["reason"], plan_hash=existing.get("plan_hash"),
            registered_symbol_count=len(existing.get("symbols") or []),
            registered_setup_count=len(existing.get("setups") or []),
            discord_posted=(existing.get("discord_delivery") or {}).get("posted"),
        )
        return result

    if started.astimezone(CT).weekday() >= 5 or is_market_holiday(trading_date):
        payload = {
            "trading_date": trading_date.isoformat(), "symbols": [], "setups": [],
            "created_at": started.isoformat(), "generated_at": started.isoformat(),
            "generated_by": GENERATOR_ID, "run_status": "SKIPPED_MARKET_CLOSED",
            "advisory_only": True, "reason": "U.S. equity market is closed; no report is due.",
            "report_markdown": "U.S. equity market is closed; no morning options report is due.",
        }
        result = await asyncio.to_thread(
            store_morning_plan_atomic, trading_date, [], [], payload, ingested_at=started,
        )
        payload.update(result)
        _LAST_RUN.update(
            finished_at=datetime.now(UTC).isoformat(), run_status=payload["run_status"],
            reason=payload["reason"], plan_hash=payload.get("plan_hash"),
            registered_symbol_count=0, registered_setup_count=0, discord_posted=None,
        )
        return payload

    previous_attempt = int(existing.get("attempt") or 0) if existing else 0
    attempt = previous_attempt + 1
    try:
        tv = await asyncio.to_thread(_load_trading_volatility_context, started)
        candidates, universe_source = _candidate_symbols(tv)
        requested = list(dict.fromkeys(["SPY", "QQQ", "IWM", "XSP", "VIX", *candidates]))
        evidence = await _collect_market_evidence(app, requested, started)
        trimmed_tv = _trim_tv_context(tv, candidates)
        try:
            research = await _generate_research(started, trimmed_tv, evidence)
            research["generation_mode"] = "model_enriched"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[MorningOptions] using deterministic fresh-data fallback: %s",
                type(exc).__name__,
            )
            research = _deterministic_research(
                trimmed_tv, evidence,
                f"{type(exc).__name__}: optional enrichment failed",
            )
            research["generation_mode"] = "deterministic_fresh_data"
        symbols, setups, rejected = _normalize_plan(research, evidence, trading_date, started)
        report = _report_markdown(
            started, research, symbols, setups, rejected, universe_source, trimmed_tv,
        )
        payload = {
            "trading_date": trading_date.isoformat(),
            "symbols": symbols,
            "setups": setups,
            "created_at": started.isoformat(),
            "expires_at": datetime.combine(trading_date, time(16, 0), ET).isoformat(),
            "generated_at": started.isoformat(),
            "generated_by": GENERATOR_ID,
            "run_status": "SUCCESS",
            "attempt": attempt,
            "advisory_only": True,
            "reason": (
                f"Registered {len(setups)} actionable setup(s)." if setups
                else "No Trade — no recommendation passed the current-data and machine-rule gates."
            ),
            "best_setup": research.get("best_setup"),
            "market_regime": research.get("market_regime"),
            "confidence": research.get("confidence"),
            "generation_mode": research.get("generation_mode"),
            "universe_source": universe_source,
            "trading_volatility": trimmed_tv,
            "market_evidence": evidence,
            "rejected_recommendations": rejected,
            "news_sources": research.get("news_sources") or [],
            "report_markdown": report,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[MorningOptions] cloud generation failed closed: %s", type(exc).__name__)
        payload = _failure_payload(
            started,
            f"{type(exc).__name__}: cloud report did not pass generation/validation",
            attempt=attempt,
        )

    result = await asyncio.to_thread(
        store_morning_plan_atomic, trading_date, payload["symbols"], payload["setups"],
        payload, ingested_at=started, preserve_manual=True,
    )
    payload["symbols"] = result.pop("stored_symbols")
    payload["setups"] = result.pop("stored_setups")
    if payload["run_status"] != "SUCCESS" and result["preserved_manual_setup_count"]:
        payload["reason"] += (
            f" {result['preserved_manual_setup_count']} manually pasted watch(es) "
            "remain active."
        )
    payload.update(result)
    posted = await asyncio.to_thread(_send_discord, payload)
    await asyncio.to_thread(_update_delivery, trading_date, posted=posted, attempted_at=datetime.now(UTC))
    finished = datetime.now(UTC)
    _LAST_RUN.update(
        finished_at=finished.isoformat(), run_status=payload["run_status"],
        reason=payload["reason"], plan_hash=payload.get("plan_hash"),
        registered_symbol_count=len(payload["symbols"]),
        registered_setup_count=len(payload["setups"]), discord_posted=posted,
    )
    logger.info(
        "[MorningOptions] completed status=%s symbols=%d setups=%d discord_posted=%s hash=%s",
        payload["run_status"], len(payload["symbols"]), len(payload["setups"]), posted,
        str(payload.get("plan_hash") or "")[:12],
    )
    return payload


def scheduled_status() -> dict[str, Any]:
    scheduler = _SCHEDULER.get("ref")
    job = scheduler.get_job(JOB_ID) if scheduler is not None else None
    latest = _latest_plan_payload(datetime.now(CT).date())
    return {
        "owner": "spreadworks-backend Render web service",
        "schedule": (
            "07:00 America/Chicago, Monday-Friday; 07:10/07:20 retry only after failure; "
            "NYSE holiday gate"
        ),
        "registered": bool(job),
        "next_run_at": _iso(job.next_run_time) if job and job.next_run_time else None,
        "generator": GENERATOR_ID,
        "advisory_only": True,
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY", "").strip()),
        "tradier_configured": bool(os.getenv("TRADIER_TOKEN", "").strip()),
        "discord_configured": bool(
            os.getenv("INTRADAY_DISCORD_WEBHOOK_URL", "").strip()
            or os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        ),
        "discord_enabled": _truthy("INTRADAY_ALERTS_ENABLED"),
        "last_run": dict(_LAST_RUN),
        "today": {
            "run_status": latest.get("run_status"),
            "generated_at": latest.get("generated_at"),
            "plan_hash": latest.get("plan_hash"),
            "registered_symbol_count": len(latest.get("symbols") or []),
            "registered_setup_count": len(latest.get("setups") or []),
            "discord_delivery": latest.get("discord_delivery"),
        } if latest else None,
    }


def register(scheduler: Any, app: Any) -> bool:
    if scheduler is None:
        logger.error("[MorningOptions] scheduler unavailable; 07:00 cloud report is not armed")
        return False
    if not _truthy("MORNING_OPTIONS_CLOUD_ENABLED", True):
        logger.warning("[MorningOptions] cloud generator disabled by MORNING_OPTIONS_CLOUD_ENABLED")
        return False

    async def tick() -> None:
        await run_morning_options_report(app)

    scheduler.add_job(
        tick, "cron", hour=7, minute="0,10,20", day_of_week="mon-fri",
        id=JOB_ID, replace_existing=True, coalesce=True, max_instances=1,
        misfire_grace_time=5400,
    )
    _SCHEDULER["ref"] = scheduler
    logger.info(
        "[MorningOptions] registered 07:00 CT weekdays with 07:10/07:20 failure retries; "
        "advisory only; no orders"
    )

    # A deploy/restart shortly after 07:00 would otherwise wait until tomorrow.
    now_ct = datetime.now(CT)
    if (now_ct.weekday() < 5 and time(7, 0) <= now_ct.time().replace(tzinfo=None) < time(8, 30)
            and not is_market_holiday(now_ct.date())):
        existing = _latest_plan_payload(now_ct.date())
        complete = bool(
            existing and existing.get("generated_by") == GENERATOR_ID
            and existing.get("run_status") in {"SUCCESS", "SKIPPED_MARKET_CLOSED"}
        )
        if not complete:
            scheduler.add_job(
                tick, "date", run_date=datetime.now(UTC),
                id=f"{JOB_ID}_catchup", replace_existing=True,
                misfire_grace_time=300,
            )
            logger.warning("[MorningOptions] scheduled immediate post-07:00 catch-up run")
    return True
