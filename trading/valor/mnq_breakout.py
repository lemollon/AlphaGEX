"""MNQ rolling-30-minute breakout specification, version 1 (PAPER ONLY).

Completed trade candles form the signal; current bid/ask forms the paper fill.
No synthetic ETF candles, no calibrated win-probability claim, no protective stop.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

CT = ZoneInfo('America/Chicago')
UTC = timezone.utc
SOURCE = 'MNQ_BREAKOUT_30M'
VERSION = 'mnq-30m-240m-cash-paper-v1'
MAX_ENTRY_DELAY_SECONDS = 45
HOLD_MINUTES = 240
TICK = 0.25
HOLIDAYS = {
    2023: '01-02 01-16 02-20 04-07 05-29 06-19 07-04 09-04 11-23 12-25',
    2024: '01-01 01-15 02-19 03-29 05-27 06-19 07-04 09-02 11-28 12-25',
    2025: '01-01 01-09 01-20 02-17 04-18 05-26 06-19 07-04 09-01 11-27 12-25',
    2026: '01-01 01-19 02-16 04-03 05-25 06-19 07-03 09-07 11-26 12-25',
}
EARLY = {2023: '07-03 11-24', 2024: '07-03 11-29 12-24',
         2025: '07-03 11-28 12-24', 2026: '11-27 12-24'}


class InvalidMarketData(ValueError):
    """Missing, stale or ambiguous market data must never create an entry."""


def aware(value: Any) -> datetime:
    t = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if t.tzinfo is None or t.utcoffset() is None:
        raise InvalidMarketData('Timezone-aware timestamp required')
    return t.astimezone(UTC)


def contract_ok(symbol: str) -> bool:
    return isinstance(symbol, str) and re.fullmatch(r'/MNQ[HMUZ]\d', symbol) is not None


def cash_session(day: date):
    if day.year not in HOLIDAYS:
        raise InvalidMarketData('Cash calendar requires review for this year')
    if day.weekday() >= 5 or day.strftime('%m-%d') in HOLIDAYS[day.year].split():
        return None
    opening = datetime(day.year, day.month, day.day, 8, 30, tzinfo=CT)
    early = day.strftime('%m-%d') in EARLY[day.year].split()
    closing = opening.replace(hour=12 if early else 15, minute=0)
    return opening, closing - timedelta(minutes=5)


def entry_window(now: datetime) -> bool:
    now = aware(now)
    session = cash_session(now.astimezone(CT).date())
    return bool(session and session[0] <= now < session[1])


def numeric(value: Any) -> float:
    if isinstance(value, bool):
        raise InvalidMarketData('Boolean is not a price')
    x = float(value)
    if not math.isfinite(x):
        raise InvalidMarketData('Nonfinite candle')
    return x


@dataclass(frozen=True)
class Decision:
    contract: str
    side: int
    signal_start: datetime
    decision_at: datetime
    deadline: datetime
    reference: float
    prior_high: float
    prior_low: float
    bars_sha256: str

    @property
    def key(self) -> str:
        text = f'{VERSION}:{self.contract}:{self.decision_at.isoformat()}'
        return 'MNQB1-' + hashlib.sha256(text.encode()).hexdigest()[:24]

    def metadata(self) -> dict:
        return dict(strategy=SOURCE, version=VERSION, paper_only=True,
                    contract=self.contract, signal_start=self.signal_start.isoformat(),
                    planned_entry=self.decision_at.isoformat(), scheduled_exit=self.deadline.isoformat(),
                    reference=self.reference, prior_high=self.prior_high, prior_low=self.prior_low,
                    input_sha256=self.bars_sha256, protective_stop=None, gex_used=False)


def decide(bars: Iterable[Mapping[str, Any]], symbol: str, now: datetime) -> Decision | None:
    now = aware(now)
    if not contract_ok(symbol):
        raise InvalidMarketData('Exact MNQ quarterly contract required')
    if not entry_window(now):
        return None
    boundary = now.replace(second=0, microsecond=0)
    if (now - boundary).total_seconds() > MAX_ENTRY_DELAY_SECONDS:
        return None
    items = []
    seen = set()
    for row in bars:
        t = aware(row['timestamp'])
        if t >= boundary:
            continue
        if t < boundary - timedelta(minutes=31):
            continue
        if t.second or t.microsecond or t in seen:
            raise InvalidMarketData('Duplicate or non-minute candle')
        seen.add(t)
        if row.get('contract_symbol') != symbol:
            raise InvalidMarketData('Mixed contract candles')
        o, h, l, c = (numeric(row[k]) for k in ('open', 'high', 'low', 'close'))
        if l <= 0 or not l <= min(o, c) <= max(o, c) <= h:
            raise InvalidMarketData('Invalid candle geometry')
        if any(abs(x / TICK - round(x / TICK)) > 1e-5 for x in (o, h, l, c)):
            raise InvalidMarketData('Off-tick candle')
        items.append((t, o, h, l, c))
    items.sort()
    expected = [boundary - timedelta(minutes=n) for n in range(31, 0, -1)]
    if [x[0] for x in items] != expected:
        raise InvalidMarketData('Need 31 contiguous completed one-minute candles')
    prior_high, prior_low = max(x[2] for x in items[:-1]), min(x[3] for x in items[:-1])
    close = items[-1][4]
    side = 1 if close > prior_high else -1 if close < prior_low else 0
    if side == 0:
        return None
    session = cash_session(now.astimezone(CT).date())
    assert session is not None
    deadline = min(boundary + timedelta(minutes=HOLD_MINUTES), aware(session[1]))
    evidence = [(t.isoformat(), o, h, l, c) for t, o, h, l, c in items]
    checksum = hashlib.sha256(json.dumps(evidence, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return Decision(symbol, side, items[-1][0], boundary, deadline, close, prior_high, prior_low, checksum)


def metadata(reasoning: str, symbol: str) -> dict:
    m = json.loads(reasoning)
    if m.get('strategy') != SOURCE or m.get('version') != VERSION or m.get('paper_only') is not True:
        raise InvalidMarketData('Unknown breakout position identity')
    if m.get('contract') != symbol or not contract_ok(symbol):
        raise InvalidMarketData('Position/metadata contract mismatch')
    planned, deadline = aware(m['planned_entry']), aware(m['scheduled_exit'])
    session = cash_session(planned.astimezone(CT).date())
    if not session or not session[0] <= planned < session[1]:
        raise InvalidMarketData('Entry outside audited cash session')
    if deadline != min(planned + timedelta(minutes=HOLD_MINUTES), aware(session[1])):
        raise InvalidMarketData('Invalid scheduled exit')
    return m


def paper_order_valid(signal, mode: Any, now: datetime) -> bool:
    """Independent guard used by the trader and the executor."""
    try:
        if getattr(mode, 'value', mode) != 'paper' or signal.ticker != 'MNQ':
            return False
        if getattr(signal.source, 'value', signal.source) != SOURCE or isinstance(signal.contracts, bool) or signal.contracts != 1:
            return False
        if signal.stop_price != 0 or signal.target_price != 0 or signal.stop_type != 'TIME_ONLY_PAPER':
            return False
        if not math.isfinite(float(signal.entry_price)) or signal.entry_price <= 0:
            return False
        m = metadata(signal.reasoning, signal.contract_symbol)
        delay = (aware(now) - aware(m['planned_entry'])).total_seconds()
        return entry_window(now) and 0 <= delay <= MAX_ENTRY_DELAY_SECONDS
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


async def collect_candles(executor, symbol: str, now: datetime) -> list[dict]:
    """Read-only DXLink snapshot of actual contract trade candles (no paid download)."""
    import asyncio
    from tastytrade import Session, DXLinkStreamer
    from tastytrade.dxfeed import Candle
    from tastytrade.instruments import Future

    if not contract_ok(symbol) or executor.auth_method != 'OAUTH':
        raise InvalidMarketData('Verified OAuth futures data required')
    now = aware(now)
    boundary = now.replace(second=0, microsecond=0)
    expected = {boundary - timedelta(minutes=n) for n in range(1, 32)}
    session = Session(executor.client_secret, executor.refresh_token)
    future = await asyncio.wait_for(Future.get(session, symbol), timeout=3)
    if future.symbol != symbol or not future.streamer_symbol or aware(future.stops_trading_at) <= now:
        raise InvalidMarketData('Contract unavailable or expired')
    events = {}
    async with DXLinkStreamer(session) as stream:
        await stream.subscribe_candle([future.streamer_symbol], '1m',
                                     boundary - timedelta(minutes=35), extended_trading_hours=True)
        until = asyncio.get_running_loop().time() + 6
        while True:
            remaining = until - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise InvalidMarketData('Candle snapshot timed out')
            event = await asyncio.wait_for(stream.get_event(Candle), timeout=remaining)
            if event.event_symbol.split('{', 1)[0] != future.streamer_symbol:
                continue
            t = datetime.fromtimestamp(int(event.time) / 1000, UTC)
            if t not in expected:
                continue
            flags = int(getattr(event, 'event_flags', 0))
            if flags & 2:
                events.pop(t, None)
                continue
            events[t] = dict(timestamp=t.isoformat(), contract_symbol=symbol,
                             open=float(event.open), high=float(event.high),
                             low=float(event.low), close=float(event.close))
            if expected.issubset(events) and not flags & 1:
                return [events[t] for t in sorted(expected)]


def get_candles(executor, symbol: str, now: datetime) -> list[dict]:
    import asyncio
    return executor._run_async_sync(lambda: asyncio.wait_for(collect_candles(executor, symbol, now), timeout=11))
