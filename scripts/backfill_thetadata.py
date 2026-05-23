"""
HELIOS — one-shot ThetaData → Postgres backfill of SPY 1-min option bars.

Pulls per (trade_date, expiration, strike, right) the 1-min OHLC + bid/ask
quote bars from a locally-running ThetaData Terminal (port 25510) and writes
them into the `helios_options_intraday` table on the AlphaGEX prod Postgres.

Designed to run on the operator's Windows box — ThetaData credentials never
leave their machine because the Terminal handles ThetaData auth itself; this
script just talks to `http://127.0.0.1:25510` with no auth headers.

Idempotent (`ON CONFLICT DO NOTHING`) and resumable (`--resume` reads
`max(trade_date)` from the table and continues from the next trading day).

CLI:
    python scripts/backfill_thetadata.py --smoke --start 2024-03-15
    python scripts/backfill_thetadata.py --start 2020-01-02 --end 2025-12-05
    python scripts/backfill_thetadata.py --resume

Environment:
    THETADATA_USERNAME  — for log messages only (defaults to
                          shairan2016@gmail.com if unset). Auth is handled by
                          Theta Terminal, NOT by this script.
    DATABASE_URL        — Render Postgres connection string.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

import psycopg2
import psycopg2.extras
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_THETADATA_USERNAME = "shairan2016@gmail.com"
THETADATA_BASE_URL = "http://127.0.0.1:25510"

DEFAULT_START = dt.date(2020, 1, 2)
DEFAULT_END = dt.date(2025, 12, 5)

DEFAULT_HALF_WIDTH = 10           # ATM ± $10 (21 integer strikes)
DEFAULT_BAR_INTERVAL_MS = 60_000  # 1-minute bars
ROOT = "SPY"


# ---------------------------------------------------------------------------
# NYSE holiday calendar 2020-2025 (full-day closures)
#
# Sourced from NYSE published holiday schedules + special closure notices.
# Half-day closures (1pm ET on day-after-Thanksgiving, Christmas Eve when on a
# weekday with market open, July 3 when on a weekday and July 4 is on a
# weekday) are NOT in this set — the script will still pull data for those
# half-sessions, which is correct (data exists, just shorter).
# ---------------------------------------------------------------------------

US_MARKET_HOLIDAYS = frozenset({
    # 2020
    dt.date(2020, 1, 1),    # New Year's Day
    dt.date(2020, 1, 20),   # MLK Day
    dt.date(2020, 2, 17),   # Presidents Day
    dt.date(2020, 4, 10),   # Good Friday
    dt.date(2020, 5, 25),   # Memorial Day
    dt.date(2020, 7, 3),    # Independence Day observed (Jul 4 was Sat)
    dt.date(2020, 9, 7),    # Labor Day
    dt.date(2020, 11, 26),  # Thanksgiving
    dt.date(2020, 12, 25),  # Christmas
    # 2021
    dt.date(2021, 1, 1),    # New Year's Day
    dt.date(2021, 1, 18),   # MLK Day
    dt.date(2021, 2, 15),   # Presidents Day
    dt.date(2021, 4, 2),    # Good Friday
    dt.date(2021, 5, 31),   # Memorial Day
    dt.date(2021, 7, 5),    # Independence Day observed (Jul 4 was Sun)
    dt.date(2021, 9, 6),    # Labor Day
    dt.date(2021, 11, 25),  # Thanksgiving
    dt.date(2021, 12, 24),  # Christmas observed (Dec 25 was Sat)
    # 2022
    dt.date(2022, 1, 17),   # MLK Day  (Jan 1 was Sat — no NYE makeup)
    dt.date(2022, 2, 21),   # Presidents Day
    dt.date(2022, 4, 15),   # Good Friday
    dt.date(2022, 5, 30),   # Memorial Day
    dt.date(2022, 6, 20),   # Juneteenth observed (Jun 19 was Sun)
    dt.date(2022, 7, 4),    # Independence Day
    dt.date(2022, 9, 5),    # Labor Day
    dt.date(2022, 11, 24),  # Thanksgiving
    dt.date(2022, 12, 26),  # Christmas observed (Dec 25 was Sun)
    # 2023
    dt.date(2023, 1, 2),    # New Year's Day observed (Jan 1 was Sun)
    dt.date(2023, 1, 16),   # MLK Day
    dt.date(2023, 2, 20),   # Presidents Day
    dt.date(2023, 4, 7),    # Good Friday
    dt.date(2023, 5, 29),   # Memorial Day
    dt.date(2023, 6, 19),   # Juneteenth
    dt.date(2023, 7, 4),    # Independence Day
    dt.date(2023, 9, 4),    # Labor Day
    dt.date(2023, 11, 23),  # Thanksgiving
    dt.date(2023, 12, 25),  # Christmas
    # 2024
    dt.date(2024, 1, 1),    # New Year's Day
    dt.date(2024, 1, 15),   # MLK Day
    dt.date(2024, 2, 19),   # Presidents Day
    dt.date(2024, 3, 29),   # Good Friday
    dt.date(2024, 5, 27),   # Memorial Day
    dt.date(2024, 6, 19),   # Juneteenth
    dt.date(2024, 7, 4),    # Independence Day
    dt.date(2024, 9, 2),    # Labor Day
    dt.date(2024, 11, 28),  # Thanksgiving
    dt.date(2024, 12, 25),  # Christmas
    # 2025
    dt.date(2025, 1, 1),    # New Year's Day
    dt.date(2025, 1, 9),    # State funeral for President Carter (NYSE closed)
    dt.date(2025, 1, 20),   # MLK Day
    dt.date(2025, 2, 17),   # Presidents Day
    dt.date(2025, 4, 18),   # Good Friday
    dt.date(2025, 5, 26),   # Memorial Day
    dt.date(2025, 6, 19),   # Juneteenth
    dt.date(2025, 7, 4),    # Independence Day
    dt.date(2025, 9, 1),    # Labor Day
    dt.date(2025, 11, 27),  # Thanksgiving
    dt.date(2025, 12, 25),  # Christmas
})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Pull:
    """A single ThetaData request specification."""

    trade_date: dt.date
    expiration_date: dt.date
    strike: int          # whole-dollar strike (integer)
    right: str           # 'C' or 'P'


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------

def _is_trading_day(d: dt.date) -> bool:
    """Mon-Fri and not on the holiday list."""
    return d.weekday() < 5 and d not in US_MARKET_HOLIDAYS


def next_trading_day(d: dt.date) -> dt.date:
    """Return the next trading day strictly after `d`, skipping weekends + holidays."""
    candidate = d + dt.timedelta(days=1)
    while not _is_trading_day(candidate):
        candidate += dt.timedelta(days=1)
    return candidate


def strike_window(spot: float, half_width: int) -> List[int]:
    """
    Return integer strikes from floor(spot)-half_width to floor(spot)+half_width, inclusive.

    21 strikes for half_width=10. ATM is `int(spot)`.
    """
    atm = int(spot)
    return list(range(atm - half_width, atm + half_width + 1))


def plan_pulls(
    trade_date: dt.date,
    spot: float,
    half_width: int = DEFAULT_HALF_WIDTH,
) -> List[Pull]:
    """
    Build the list of (date, exp, strike, right) requests for one trade day.

    - expiration = next trading day after trade_date (matches HELIOS 1DTE design)
    - strikes    = ATM ± half_width
    - rights     = ['C', 'P']
    """
    exp = next_trading_day(trade_date)
    strikes = strike_window(spot, half_width)
    pulls: List[Pull] = []
    for k in strikes:
        for right in ("C", "P"):
            pulls.append(Pull(
                trade_date=trade_date,
                expiration_date=exp,
                strike=k,
                right=right,
            ))
    return pulls


def trading_days_in_range(start: dt.date, end: dt.date) -> List[dt.date]:
    """Inclusive list of trading days between start and end."""
    out: List[dt.date] = []
    d = start
    while d <= end:
        if _is_trading_day(d):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# Side-effecting functions
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    """HTTP session with retries + backoff. ThetaData Terminal needs no auth header."""
    sess = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2.0,            # 0s, 2s, 4s, 8s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    return sess


def _strike_to_thetadata(strike_dollars: int) -> int:
    """ThetaData encodes strikes as 1/1000 of a dollar (i.e. 1/10 of a cent)."""
    return strike_dollars * 1000


def _date_to_thetadata(d: dt.date) -> str:
    """ThetaData wants YYYYMMDD."""
    return d.strftime("%Y%m%d")


def _bar_time_for(trade_date: dt.date, ms_of_day: int) -> dt.datetime:
    """ThetaData ms_of_day is in ET; build a tz-naive UTC datetime by interpreting
    the trade_date as ET wall time. We store TIMESTAMPTZ in Postgres so any tz is
    fine as long as it round-trips correctly. We keep ET semantics by emitting an
    ISO string with -05:00 / -04:00 offset based on a simple DST rule.

    For backfill purposes a simple UTC offset isn't necessary — Postgres TIMESTAMPTZ
    will normalize. We emit a timezone-aware datetime in UTC, computed from
    (trade_date midnight ET + ms_of_day milliseconds), where ET is treated as
    America/New_York with whatever offset is in effect that day.
    """
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    midnight_et = dt.datetime(trade_date.year, trade_date.month, trade_date.day, tzinfo=et)
    return midnight_et + dt.timedelta(milliseconds=ms_of_day)


def fetch_quote(
    session: requests.Session,
    pull: Pull,
    bar_interval_ms: int = DEFAULT_BAR_INTERVAL_MS,
    timeout: float = 60.0,
) -> List[List]:
    """
    GET /v2/hist/option/quote → response array of
        [ms_of_day, bid_size, bid_exch, bid, bid_cond, ask_size, ask_exch, ask, ask_cond, date]
    """
    url = f"{THETADATA_BASE_URL}/v2/hist/option/quote"
    params = {
        "root": ROOT,
        "exp": _date_to_thetadata(pull.expiration_date),
        "strike": str(_strike_to_thetadata(pull.strike)),
        "right": pull.right,
        "start_date": _date_to_thetadata(pull.trade_date),
        "end_date": _date_to_thetadata(pull.trade_date),
        "ivl": str(bar_interval_ms),
    }
    resp = session.get(url, params=params, timeout=timeout)
    if resp.status_code in (472, 474):
        # Empty result for this contract on this day. Treat as soft-empty so
        # the day-level skip recovers gracefully without losing the rest of
        # the chain. Same semantics as fetch_ohlc.
        return []
    resp.raise_for_status()
    payload = resp.json()
    # Theta returns {"header": {...}, "response": [[...]]}
    return payload.get("response", []) or []


def fetch_ohlc(
    session: requests.Session,
    pull: Pull,
    bar_interval_ms: int = DEFAULT_BAR_INTERVAL_MS,
    timeout: float = 60.0,
) -> List[List]:
    """
    GET /v2/hist/option/ohlc → response array of
        [ms_of_day, open, high, low, close, volume, count, date]

    ThetaData returns HTTP 472 ("No data for the specified timeframe & contract")
    for strikes that traded zero contracts on that day. The companion quote
    endpoint usually still has bid/ask for those strikes, so we treat 472 as a
    soft-empty (return []) rather than raising — merge_quote_and_ohlc will
    write rows with NULL OHLC but populated bid/ask.
    """
    url = f"{THETADATA_BASE_URL}/v2/hist/option/ohlc"
    params = {
        "root": ROOT,
        "exp": _date_to_thetadata(pull.expiration_date),
        "strike": str(_strike_to_thetadata(pull.strike)),
        "right": pull.right,
        "start_date": _date_to_thetadata(pull.trade_date),
        "end_date": _date_to_thetadata(pull.trade_date),
        "ivl": str(bar_interval_ms),
    }
    resp = session.get(url, params=params, timeout=timeout)
    if resp.status_code in (472, 474):
        return []
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("response", []) or []


_SPY_OPEN_CACHE: dict = {}


def _load_spy_open_history(start: dt.date, end: dt.date) -> dict:
    """One-shot pull of SPY daily OHLC from yfinance, returns {date: open_price}.

    Used in place of ThetaData's stock EOD endpoint, which on the OPTION.STANDARD
    bundle has a "first access date" of 2023-06-01 — too recent for our 2020+
    backtest window. yfinance has SPY back to inception; one HTTP call covers
    the full 6-year span and is then cached in-memory for the run.
    """
    import yfinance as yf
    pad_start = start - dt.timedelta(days=7)
    pad_end = end + dt.timedelta(days=2)
    df = yf.Ticker("SPY").history(
        start=pad_start.isoformat(),
        end=pad_end.isoformat(),
        auto_adjust=False,
    )
    cache: dict = {}
    for ts, row in df.iterrows():
        cache[ts.date()] = float(row["Open"])
    return cache


def fetch_spy_open_price(session: requests.Session, trade_date: dt.date) -> Optional[float]:
    """Look up SPY's open price on `trade_date`.

    Reads from the module-level _SPY_OPEN_CACHE populated by main() at startup
    (yfinance one-shot). Returns None if the date is missing (weekend/holiday
    or out of range). The `session` arg is unused but preserved for signature
    compatibility with earlier ThetaData-based versions.
    """
    return _SPY_OPEN_CACHE.get(trade_date)


def merge_quote_and_ohlc(
    pull: Pull,
    quote_rows: Iterable[List],
    ohlc_rows: Iterable[List],
) -> List[tuple]:
    """
    Join quote bars and OHLC bars by ms_of_day and shape into the row tuple
    expected by `INSERT INTO helios_options_intraday`.

    Tuple order: (trade_date, expiration_date, strike, right, bar_time,
                  open, high, low, close, volume, bid, ask)
    """
    ohlc_by_ms = {row[0]: row for row in ohlc_rows if row}
    quote_by_ms = {row[0]: row for row in quote_rows if row}
    all_ms = sorted(set(ohlc_by_ms.keys()) | set(quote_by_ms.keys()))

    out: List[tuple] = []
    for ms in all_ms:
        bar_time = _bar_time_for(pull.trade_date, ms)
        o_row = ohlc_by_ms.get(ms)
        q_row = quote_by_ms.get(ms)
        # OHLC: [ms, open, high, low, close, volume, count, date]
        open_ = o_row[1] if o_row else None
        high = o_row[2] if o_row else None
        low = o_row[3] if o_row else None
        close = o_row[4] if o_row else None
        volume = int(o_row[5]) if o_row and o_row[5] is not None else None
        # Quote: [ms, bid_size, bid_exch, bid, bid_cond, ask_size, ask_exch, ask, ask_cond, date]
        bid = q_row[3] if q_row else None
        ask = q_row[7] if q_row else None
        out.append((
            pull.trade_date,
            pull.expiration_date,
            pull.strike,
            pull.right,
            bar_time,
            open_,
            high,
            low,
            close,
            volume,
            bid,
            ask,
        ))
    return out


INSERT_SQL = """
    INSERT INTO helios_options_intraday
        (trade_date, expiration_date, strike, "right", bar_time,
         open, high, low, close, volume, bid, ask)
    VALUES %s
    ON CONFLICT (trade_date, expiration_date, strike, "right", bar_time)
        DO NOTHING
"""


def _reconnect_with_backoff(conn, db_url: str, max_attempts: int = 8):
    """Close the dead connection and re-connect with exponential backoff.

    Survives transient DNS/network outages (cap ~5 minutes total wait).
    """
    try:
        conn.close()
    except Exception:
        pass
    delay = 5.0
    for attempt in range(1, max_attempts + 1):
        try:
            new = psycopg2.connect(db_url)
            new.autocommit = False
            logging.info("DB reconnected (attempt %d).", attempt)
            return new
        except psycopg2.OperationalError as e:
            logging.warning("Reconnect attempt %d failed: %s -- sleeping %.1fs",
                            attempt, e, delay)
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    raise RuntimeError(f"Failed to reconnect to Postgres after {max_attempts} attempts")


def insert_bars(conn, rows: List[tuple]) -> int:
    """Bulk-insert with ON CONFLICT DO NOTHING. Returns rows attempted."""
    if not rows:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, INSERT_SQL, rows, page_size=500)
    return len(rows)


def get_resume_point(conn) -> Optional[dt.date]:
    """Return max(trade_date) already in the table, or None if empty."""
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(trade_date) FROM helios_options_intraday")
        row = cur.fetchone()
    return row[0] if row and row[0] else None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill SPY 1-min option bars from ThetaData Terminal into Postgres.",
    )
    p.add_argument(
        "--start",
        type=lambda s: dt.date.fromisoformat(s),
        default=DEFAULT_START,
        help="Start trade_date (YYYY-MM-DD). Default: 2020-01-02.",
    )
    p.add_argument(
        "--end",
        type=lambda s: dt.date.fromisoformat(s),
        default=DEFAULT_END,
        help="End trade_date inclusive (YYYY-MM-DD). Default: 2025-12-05.",
    )
    p.add_argument(
        "--smoke",
        action="store_true",
        help="One-day pull only (uses --start as the single trade_date).",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="Pick up from max(trade_date)+1 in helios_options_intraday.",
    )
    return p.parse_args(argv)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def main(argv: Optional[List[str]] = None) -> int:
    setup_logging()
    args = parse_args(argv)

    username = os.environ.get("THETADATA_USERNAME", DEFAULT_THETADATA_USERNAME)
    # Password is never required for the local Terminal request path; if the
    # user has set THETADATA_PASSWORD we deliberately do not log it nor send it.
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logging.error("DATABASE_URL not set; aborting.")
        return 2

    logging.info("HELIOS backfill starting (ThetaData user: %s)", username)
    logging.info("Terminal endpoint: %s (no auth — Terminal handles ThetaData login)",
                 THETADATA_BASE_URL)

    session = make_session()

    # Quick liveness check on Terminal
    try:
        r = session.get(f"{THETADATA_BASE_URL}/v2/system/mdds/status", timeout=10)
        logging.info("Terminal reachable (mdds/status HTTP %s).", r.status_code)
    except Exception as e:
        logging.warning("Terminal liveness check failed: %s — proceeding anyway.", e)

    conn = psycopg2.connect(db_url)
    conn.autocommit = False

    try:
        # Resolve the date range
        if args.smoke:
            target_dates = [args.start]
            logging.info("SMOKE mode: pulling exactly %s", args.start)
        else:
            start = args.start
            if args.resume:
                last = get_resume_point(conn)
                if last is not None:
                    start = max(start, next_trading_day(last))
                    logging.info("RESUME: last completed trade_date in DB = %s; "
                                 "continuing from %s", last, start)
                else:
                    logging.info("RESUME: table empty; starting at %s", start)
            target_dates = trading_days_in_range(start, args.end)
            logging.info("Plan: %d trading days from %s to %s",
                         len(target_dates),
                         target_dates[0] if target_dates else "(none)",
                         target_dates[-1] if target_dates else "(none)")

        if target_dates:
            global _SPY_OPEN_CACHE
            logging.info("Loading SPY EOD history from yfinance (%s -> %s)...",
                         target_dates[0], target_dates[-1])
            _SPY_OPEN_CACHE = _load_spy_open_history(target_dates[0], target_dates[-1])
            logging.info("Cached %d SPY EOD rows.", len(_SPY_OPEN_CACHE))

        total_rows = 0
        last_known_spot: Optional[float] = None

        for trade_date in target_dates:
            day_rows = 0
            day_failures = 0

            spot = fetch_spy_open_price(session, trade_date)
            if spot is None:
                if last_known_spot is None:
                    logging.warning("[%s] No SPY open price and no prior spot; "
                                    "skipping day.", trade_date)
                    continue
                spot = last_known_spot
                logging.info("[%s] Spot lookup failed; reusing last_known_spot=%.2f",
                             trade_date, spot)
            last_known_spot = spot

            pulls = plan_pulls(trade_date, spot, half_width=DEFAULT_HALF_WIDTH)

            for pull in pulls:
                try:
                    quote_rows = fetch_quote(session, pull)
                    ohlc_rows = fetch_ohlc(session, pull)
                except requests.RequestException as e:
                    day_failures += 1
                    logging.warning("[%s exp=%s K=%d %s] FAIL: %s",
                                    trade_date, pull.expiration_date,
                                    pull.strike, pull.right, e)
                    continue

                merged = merge_quote_and_ohlc(pull, quote_rows, ohlc_rows)
                if merged:
                    inserted = 0
                    for insert_attempt in range(1, 6):
                        try:
                            inserted = insert_bars(conn, merged)
                            break
                        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                            logging.warning(
                                "DB drop during insert (attempt %d/5): %s", insert_attempt, e,
                            )
                            try:
                                conn = _reconnect_with_backoff(conn, db_url)
                            except Exception as recon_err:
                                logging.error("Reconnect failed: %s", recon_err)
                                if insert_attempt == 5:
                                    raise
                    day_rows += inserted

            for commit_attempt in range(1, 6):
                try:
                    conn.commit()
                    break
                except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                    logging.warning(
                        "DB drop during commit (attempt %d/5): %s", commit_attempt, e,
                    )
                    try:
                        conn = _reconnect_with_backoff(conn, db_url)
                    except Exception as recon_err:
                        logging.error("Reconnect failed: %s", recon_err)
                        if commit_attempt == 5:
                            raise
                    # Day's data was rolled back when the connection dropped; --resume
                    # on next run will redo this date (insert_bars is idempotent via
                    # ON CONFLICT DO NOTHING).
            total_rows += day_rows
            logging.info(
                "[%s] done — pulls=%d rows=%d failures=%d running_total=%d",
                trade_date, len(pulls), day_rows, day_failures, total_rows,
            )

        logging.info("Backfill complete. Rows inserted (attempted): %d", total_rows)
        return 0

    except KeyboardInterrupt:
        logging.warning("Interrupted by user — committing partial day and exiting.")
        try:
            conn.commit()
        except Exception:
            conn.rollback()
        return 130
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
