"""
EMBER - TradingVolatility 2:1 risk/reward scanner bot. Leron's 2:1 floor on TV's OWN levels.
Two independent strategies share the candidate list and per-name fetches below: the original
geometry scanner (strategy="rr" in every row/ledger line, unchanged) and BOUNCE (strategy=
"bounce", section F). Both are gated by the LIQUIDITY GATE in section E.

A. CANDIDATE SOURCES (all TV lists, not just /top-setups). Universe widened 2026-09-16 (Leron):
   PRICE_MAX=300 (was 80) -- liquidity lives above $80, so cost control moved from the
   candidate filter to the structure choice (section D/F: defined-width spreads, never a bare
   long, above $80).
   1. /top-setups?limit=50&price_min=15&price_max=300          source tag "idea"
   2. /top-setups/screener/{name}?limit=50&price_min=15&price_max=300 for the 7 named presets
      (bottoming_reversal, capitulation_reversal, highvol_breakdown, momentum_breakout,
      range_premium_seller, topping_reversal, trend_pullback) -- source tag = preset name.
      Same item schema as /top-setups. EXPENSIVE (5/min) -- paced with CURVE_PACE_S like the
      GEX curve; 429 -> sleep 20 and retry (tv_get's existing behaviour). A 404/error preset
      logs one line and is skipped, never fails the run.
   3. /income-setups?limit=50   source tag "income". Filtered client-side to 15<=price<=300
      (the endpoint has no price params). Income items carry NO direction: direction="long"
      only if the ticker's /tickers payload shows price above its gamma flip (positive-gamma
      regime); otherwise the name is skipped with reason "income: below flip" (CSP/CC at $500
      are dead on collateral -- the name may still be a directional option/spread candidate).
      Income items are also the only source carrying an earnings field (`earnings_date`,
      `earnings_time`) -- used as a context column by BOUNCE (section F), not a gate.
   Dedup by ticker: keep the highest (opportunity_score, else income_score)-scored item's
   direction/price. source = "|"-joined list of every list the ticker appeared on; n_sources
   = its length. Both are on every printed table and every ledger row. When the directed
   sources (idea + presets) disagree on direction, prefer /top-setups' recommended_direction
   and set dir_conflict=True.

B. PER-NAME TTL CACHE (so a tick stays inside 30 min even with ~150 unique names). Under
   --live, /tickers/{t}, /tickers/{t}/curves/gex_by_strike, and /tickers/{t}/series (BOUNCE's
   RSI source) are cached per NAME on the daily key (TODAY_ticker_T / TODAY_gex_T /
   TODAY_series_T) with a 60-minute TTL checked off the cache file's mtime -- a name looked at
   twice inside one hour reuses the payload instead of refetching. List endpoints (A1-A3) and
   /options/volume always fetch fresh each tick (they keep the per-run HHMM cache key).
   --cached replays everything from disk with no network regardless of TTL.
   Wall-clock guard: once the run passes 22 minutes, no new names are evaluated -- whatever
   hasn't been scored yet is dropped, one line prints "TRUNCATED: N names not evaluated", and
   the tables/ledger/notify still run for what was done. Candidates are evaluated in
   opportunity_score-desc order first, so truncation drops the weakest names.

For each candidate: pull /tickers/{t} (implied move by horizon: 1d/1w/30d, gamma flip,
max-gamma strike, positioning, IV rank, speculative-flow score) and
/tickers/{t}/curves/gex_by_strike (put wall / call wall = largest negative / positive GEX
strikes near spot). Levels are TV's, not ours:

  LONG  (dashboard direction long):  entry = price
        stop   = just beyond the nearer of {put wall, price - 1d implied move}   (adverse)
        target = the nearer of {call wall, price + 1w implied move}               (favorable)
  SHORT: mirror.
  Regime context printed, not gated: below gamma flip = negative gamma (momentum regime).
  A pure "1w band target / 1d band stop" would pass 2:1 for every name by the sqrt-time law
  (1w ~ sqrt(5) x 1d); the walls are what make the geometry name-specific.

R:R = |target-entry| / |entry-stop|. >= 2.0 setup; 1.0-2.0 MARGINAL; < 1.0 hidden.

C. GEX and PCR VIEWS (context only, never gate/re-sort setup vs marginal vs hidden): computed
   per name straight off the /tickers payload (the site's GEX/PCR dashboards have no API of
   their own). Every row carries regime, flip (gamma.flip.price), dist_to_flip_pct =
   (price-flip)/price*100, pcr_vol/pcr_oi/pcr_oi_d30 (positioning.put_call's pcr_volume,
   pcr_oi, pcr_oi_change.d30), spec_score
   (call_flow.speculative_interest_score), iv_rank (the candidate list item's iv_rank, else
   underlying.iv.iv_rank), rsi14 (section F's RSI, added to every row of either strategy) --
   all via .get chains, None if absent. Two extra tables print after MARGINAL: "GEX VIEW"
   (setups+marginal+illiquid sorted by |dist_to_flip_pct| ascending) and "PCR VIEW" (sorted by
   spec_score descending).

D. VOL SURFACE -> STRUCTURE CHOICE. For every >=2:1 setup, BOTH structures are priced off one
   ThetaData Terminal snapshot (same session-date fill convention as before: the prior
   session's 15:59 close when run before 16:00, else today's):
     single   = existing ATM long call/put at the ASK (unchanged math).
     vertical = long the ATM strike at the ASK, short the strike nearest the target at the
                BID (call spread for long, put spread for short); debit = ask_long-bid_short,
                max_gain = width-debit, opt_rr_floor = max_gain/debit, cost_usd = debit*100.
   structure = "vertical" if iv_rank is not None and iv_rank > 50 else "single" for names
   priced <=$80. Above $80 (Leron 2026-09-16 -- liquidity lives above $80; spreads keep cost
   <= cap): structure is FORCED to "vertical" regardless of iv_rank, and the short strike is
   picked by width instead of by nearest-to-target -- the largest listed strike (in the
   direction away from the long leg, same side as before) whose width*100 <= MAX_CONTRACT*100
   (vert_width records it). If no listed strike above $80 fits under the cap, structure=None
   (no bare "single" fallback above $80 -- note explains why). Both prices are always recorded
   for <=$80 names (single_debit, single_rr, vert_debit, vert_rr, vert_short_strike, vert_width,
   iv_rank); contract/debit/cost_usd/opt_rr_floor/opt_rr_7d reflect the CHOSEN structure only
   (opt_rr_7d is only computed for single -- None for vertical). The $200 cap note applies to
   the chosen structure's cost. Below $80, if the short leg has no bid, structure falls back to
   single and structure_note="no bid on short". skew_px = ask(put ~5% OTM) / ask(call ~5% OTM)
   at the same expiry/snapshot -- a cheap skew proxy, column only, not gated.
   Fill convention throughout: long legs at the ASK, short legs at the BID, one Terminal NBBO
   snapshot per name/expiry (no re-quoting between single and vertical pricing).
   Option leg for setups: expiry 25-45 DTE (closest to 35). Contract cap default = $200 (40%
   of $500; Leron 2026-09-16 -- raised from $150 so a stop-out risks ~$100-140 and a 4-loss
   streak is survivable; --cap 5.0 = whole account; pct_of_500 shows size). Credit spreads
   cannot meet a 2:1 floor on max-loss terms by construction, so TV's own spread suggestions
   are still priced as the long leg (tv_structure column, context only).

CONTEXT ONLY, does not gate or re-sort rows: flow_exp = the option-leg expiry (25-45 DTE for
RR, the chosen BOUNCE structure's expiry for BOUNCE) used for the strike-by-strike
options-volume pull (/tickers/{t}/options/volume?exp=...). flow_with = summed volume between
entry and target in the trade's favor (LONG: call volume in (price, target]; SHORT: put
volume in [target, price)). flow_against = summed volume between entry and stop working
against the trade (LONG: put volume in [stop, price); SHORT: call volume in (price, stop]).
flow_tilt = flow_with / max(flow_against, 1), rounded 2dp -- >1 means more strikes traded
toward target than toward stop, nothing more. flow_note carries "no volume yet" (empty
points), "not cached" (--cached run, no cached payload), or an error string when the pull
fails; flow fields never raise and never change setup/marginal/hidden membership. Pulled only
for >=1:1 rows (setups + marginal, both strategies), capped near 30 calls/run.
Every setup/marginal row (RR and BOUNCE alike, plus rows that fail the liquidity gate below)
-> tools/ember_ledger.jsonl (scored by tools/ember_score.py, grouped by strategy).
Rate limits: 60 calls/min, 5 expensive/min (screener presets + the GEX curve are expensive)
-> paced; volume calls paced 1.1s apart when not served from cache.

E. LIQUIDITY GATE (Leron 2026-09-16 -- so a setup can actually be entered/exited at a decent
   spread; applies to BOTH strategies, >=2:1 setups only): every leg of the chosen structure
   (single/vertical for RR; call/pcs for BOUNCE) gets spread_pct = (ask-bid)/((ask+bid)/2)*100
   off the same Terminal snapshot already pulled for pricing. A structure is liquid only if
   EVERY leg's spread_pct <= LIQ_SPREAD_MAX (15.0); spread_pct on the row = the max across the
   chosen structure's legs. Name-level, from positioning.put_call (same /tickers payload):
   opt_oi = call_oi+put_oi, opt_vol = call_vol+put_vol -- columns on every row, both
   strategies, all tiers. Soft floors LIQ_OI_MIN=5000, LIQ_VOL_MIN=500: below either sets
   liq_note="thin OI"/"thin vol" and fails the gate regardless of spread. A chosen structure
   with no two-sided quote at all is illiquid with liq_note="no quote". `liquid` (bool) and
   `spread_pct` are on every RR/BOUNCE row that reaches option pricing (marginal rows carry
   the columns for information only -- not gated). A >=2:1 setup that fails the gate is NOT
   presented as tradeable: it moves to "ILLIQUID (>=2:1 but spread/OI fail)" /
   "BOUNCE ILLIQUID (>=2:1 but spread/OI fail)" instead of SETUPS/BOUNCE, is still written to
   the ledger with liquid=False (so the scorer can compare later), but is excluded from NEW
   SINCE LAST SCAN and from notify.

F. BOUNCE STRATEGY (strategy="bounce"; RR above is unchanged and always strategy="rr").
   Oversold-at-support long, evaluated for EVERY unique candidate (independent of RR's
   direction/side) right after the shared per-name /tickers + curve fetch.
   Signal: rsi14 < 30 AND put_wall is not None AND put_wall*0.97 <= price <= put_wall*1.03
   (within 3% of support, including a name that has already broken slightly through it).
   Direction is always long.
   rsi14 = Wilder's RSI(14) on daily closes. Source: /tickers/{t}/series (schema tv.series.v2:
   {"data": {"points": [{"date": "YYYY-MM-DD", "price": <close>, "iv_rank":.., "gex_flip":..,
   "pc_25d_ratio":..}, ...]}}, points ascending by date, ~124 points on the default 180d
   window; "price" is the daily close), cached per-name like /tickers (section B). Falls back
   to data/stock_eod/{t}.parquet's Close column if the series has fewer than 30 closes; None
   if neither has >=15 closes. Added to every row of BOTH strategies -- a useful column on RR
   too, never a gate there.
   Geometry (same 2:1 gate as RR: >=2.0 setup, 1.0-2.0 marginal, <1.0 hidden, never priced):
   stop = put_wall*(1-BUF), or price*(1-1%) if price is already through the wall; target =
   min(call_wall, price + 1w implied move).
   Expiry (Leron 2026-09-16 amendment -- dropped the original earnings-first-expiry rule so
   BOUNCE stays nimble): only expiries with 21<=DTE<=45 are considered (max 3, nearest DTE
   first). One Terminal 15:59 snapshot per candidate expiry prices the ATM straddle; metric =
   atm_straddle_ask / sqrt(DTE). The `call` structure uses the expiry with the LOWEST metric
   (cheapest vol per unit time); the `pcs` structure uses the HIGHEST (richest vol per unit
   time -- sell where it's rich, buy where it's cheap). term_slope = metric at the longest DTE
   / metric at the shortest (None with fewer than 2 expiries in the window; if only one is
   listed, call_exp == pcs_exp). earnings_date/days_to_earnings/earnings_inside_exp are
   context columns only, never a gate: earnings_date comes from the candidate's income-setups
   item if it appeared there (the only source that carries one); earnings_inside_exp = the
   earnings date falls before the CHOSEN structure's expiry.
   Both structures are always priced and recorded (fill convention identical to RR: long legs
   at the ask, short legs at the bid, one snapshot per name/expiry):
     call = long ATM call at the ask, same floor/7d math as RR's single leg (call_debit,
            call_cost_usd, call_rr_floor, call_rr_7d).
     pcs  = put credit spread: short the highest listed strike <= put_wall; long the strike
            `width` below where width is the largest listed increment <= $2.50 (collateral =
            width*100 <= $250); credit = bid(short)-ask(long) (pcs_credit, pcs_width,
            pcs_short, pcs_max_loss = width*100-credit*100). pcs_rr_stop = credit /
            max(loss_at_stop, 0.01), loss_at_stop = the spread's BS value at the stop price
            (T-5 days, IV solved off the short leg's ask) minus the credit collected. Any
            missing leg quote -> pcs fields None, pcs_note="no quote".
   structure (chosen) = "pcs" if iv_rank is not None and iv_rank>=40 and pcs priced, else
   "call" for names priced <=$80. Above $80 (liquidity lives above $80; spreads keep cost <=
   cap): structure is FORCED to "pcs" regardless of iv_rank whenever pcs priced -- no fallback
   to a bare "call" above $80; if pcs can't be priced there, structure=None. `exp` = the chosen
   structure's expiry. Printed in "== BOUNCE (RSI<30 at put support) ==" (setup+marginal, tier
   column; "== BOUNCE == none" if empty).
   NEW SINCE LAST SCAN / ledger dedupe key is now (ticker, scan_date, dir, strategy) so RR and
   BOUNCE new-setup detection can't collide on the same ticker/day.
   TODO: peer-oversold confirmation (e.g. RCL for CCL) -- TV has no peer list; not built.

Usage: python tools/ember.py [--cached] [--live] [--cap N]
       --cached = reuse last lists and any cached per-ticker payloads from today (cache key
       TODAY_name.json for everything, including per-name TTL entries); a list with nothing
       cached yet is treated as empty (one line printed), never a failure. --live = intended
       for the every-30-min scheduled run during market hours: list-endpoint cache keys become
       TODAY_HHMM_name.json (HHMM = this run's start time, computed once at startup) so every
       --live tick fetches fresh lists, while per-name /tickers + curve + series calls stay on
       the daily key with the 60-minute TTL described in section B above. Without --live, cache
       behaviour is unchanged (TODAY_name.json); --cached always reads the daily key regardless
       of --live. --cached never writes tools/ember_ledger.jsonl or tools/ember_runs.log (a
       --cached replay would otherwise duplicate the live tick's rows) -- it prints
       "--cached: ledger/runs log not written" in their place. Notify is still skipped entirely
       under --cached (unchanged).

NEW SINCE LAST SCAN: before appending to the ledger, the existing ledger is loaded and
keyed on (ticker, scan_date, dir, strategy) for today's scan_date; the >=2:1 LIQUID setups
whose key is not already present are printed under "== NEW SINCE LAST SCAN ==" (RR) and
"== NEW BOUNCE SINCE LAST SCAN ==" (BOUNCE) (or "... == none"). Illiquid setups never appear
here (section E). The SETUPS/MARGINAL/BOUNCE tables are unchanged (full picture); the ledger
append is unchanged (appends every setup+marginal+illiquid row every run; tools/ember_score.py
dedupes on scan_date).

Notify: if tools/../.env defines KVB_NOTIFY_TOKEN and NEW SINCE LAST SCAN is non-empty for
either strategy, POSTs a summary to https://kalshi-volarb.onrender.com/api/notify (header
X-KVB-Notify) with a second section "Bounce (oversold at support)" when there are new bounce
setups; subject count = total new across both. Best-effort: failures print one line and never
fail the run. Skipped entirely under --cached, and skipped with a one-line notice if
KVB_NOTIFY_TOKEN is not set.

Every non---cached run appends one line to tools/ember_runs.log (see the --cached note above):
  <scan_time> live=<bool> setups=<n> marginal=<n> new=<n> bounce_setups=<n> bounce_marginal=<n>
  bounce_new=<n> notified=<bool>
"""
import atexit, json, os, sys, csv, io, time, math, datetime as dt, urllib.request, urllib.error, urllib.parse
from pathlib import Path
import pandas as pd
from . import ember_lock

CODE_DIR = Path(__file__).resolve().parent
ROOT = Path(os.getenv("EMBER_TVSCAN_DATA_DIR", str(CODE_DIR))).expanduser().resolve()
ROOT.mkdir(parents=True, exist_ok=True)
STOCK_EOD = ROOT / "data" / "stock_eod"
TOOLS = ROOT / "tools"; CACHE_DIR = TOOLS / "ember_cache"; CACHE_DIR.mkdir(parents=True, exist_ok=True)
LEDGER = ROOT / "ember_ledger.jsonl"
THETA = os.getenv("THETADATA_BASE_URL", "http://127.0.0.1:25503").rstrip("/")
BUF, CURVE_PACE_S = 0.005, 13.0     # 13s between expensive calls = <5/min
LIQ_SPREAD_MAX = 15.0               # max per-leg (ask-bid)/mid*100 for a structure to be "liquid" (Leron 2026-09-16)
LIQ_OI_MIN, LIQ_VOL_MIN = 5000, 500 # soft floor on name-level combined call+put OI / volume; below either = not liquid
MAX_CONTRACT = float(sys.argv[sys.argv.index("--cap") + 1]) if "--cap" in sys.argv else 2.00   # $/share; 2.00 = $200 = 40% of $500 (Leron 2026-09-16: cap raised from $150; --cap 5.0 = whole account)
PRICE_MAX = 300   # Leron 2026-09-16: universe widened from 80; liquidity lives above $80, cost control moved to structure choice (defined-width verticals/pcs above $80)
_ENV_TEXT = (ROOT / ".env").read_text() if (ROOT / ".env").exists() else ""
KEY = os.getenv("TV_API_KEY") or os.getenv("TRADING_VOLATILITY_API_KEY") or next(
    (l.split("=", 1)[1].strip() for l in _ENV_TEXT.splitlines() if l.startswith("TV_API_KEY=")), None
)
NOTIFY_TOKEN = os.getenv("KVB_NOTIFY_TOKEN") or next(
    (l.split("=", 1)[1].strip() for l in _ENV_TEXT.splitlines() if l.startswith("KVB_NOTIFY_TOKEN=")), None
)
TODAY = str(dt.date.today())
LIVE = "--live" in sys.argv
SCAN_START = dt.datetime.now()          # computed once at startup (local time)
RUN_HHMM = SCAN_START.strftime("%H%M")
SCAN_TIME_ISO = SCAN_START.isoformat()
RUNS_LOG = ROOT / "ember_runs.log"

# Fix 3: overlap guard. run-hidden.vbs does not wait for the previous scheduled run to exit, so
# Task Scheduler's single-instance policy is not real without this. Only under --live (the
# scheduled every-30-min tick) -- a manual --cached/foreground run never takes the lock. This
# script has no __main__ guard (it is flat top-level code, always has been), so atexit stands in
# for a try/finally wrapping the whole program -- it fires on a normal exit, sys.exit(), and an
# uncaught exception alike, which is the same guarantee a finally around main() would give.
EMBER_LOCK = TOOLS / "ember.lock"
if LIVE and "--cached" not in sys.argv:
    if not ember_lock.acquire_lock(EMBER_LOCK):
        sys.exit(0)
    atexit.register(ember_lock.release_lock, EMBER_LOCK)

PRESETS = ["bottoming_reversal", "capitulation_reversal", "highvol_breakdown", "momentum_breakout",
           "range_premium_seller", "topping_reversal", "trend_pullback"]
TRUNCATE_S = 22 * 60     # wall-clock guard: stop evaluating new names past 22 min into the run
TICKER_TTL_S = 3600      # per-name /tickers + curve + series cache TTL under --live

def cache_key(cache_name, force_daily=False):
    """TODAY_name for --cached/non-live runs and for force_daily callers (per-name /tickers +
    curve + series calls force this so the TTL check in tv_get applies); TODAY_HHMM_name under
    --live for list endpoints (fresh every scheduled tick, per-run cache only)."""
    if force_daily or "--cached" in sys.argv or not LIVE: return f"{TODAY}_{cache_name}"
    return f"{TODAY}_{RUN_HHMM}_{cache_name}"

def tv_get(path, cache_name, expensive=False, ttl_s=None, force_daily=False):
    p = CACHE_DIR / f"{cache_key(cache_name, force_daily)}.json"
    if p.exists():
        fresh = True
        if ttl_s is not None and LIVE and "--cached" not in sys.argv:
            fresh = (time.time() - p.stat().st_mtime) < ttl_s
        if fresh: return json.loads(p.read_text())
    if "--cached" in sys.argv: return None
    for attempt in range(6):
        try:
            req = urllib.request.Request(f"https://stocks.tradingvolatility.net/api/v2{path}", headers={"Authorization": f"Bearer {KEY}"})
            with urllib.request.urlopen(req, timeout=30) as r: d = json.load(r)
            if "error" in d and d["error"].get("code") == "rate_limited": time.sleep(20); continue
            p.write_text(json.dumps(d))
            if expensive: time.sleep(CURVE_PACE_S)
            return d
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(20); continue
            return json.loads(p.read_text()) if p.exists() else None
        except Exception: time.sleep(3)
    return json.loads(p.read_text()) if p.exists() else None

def walls_from_curve(d, price):
    """put wall = strike with the most negative net GEX below spot; call wall = most positive above.
    Payload shape is adapted from TV's gex_by_strike (arrays of strikes and net gex)."""
    data = d.get("data", d) if d else None
    if not data: return None, None
    pts = data.get("points") or []          # TV shape: [{strike, call, put, net}], net = dealer GEX at that strike
    try: strikes = [float(x["strike"]) for x in pts]; gex = [float(x.get("net", 0)) for x in pts]
    except Exception: return None, None
    if not strikes: return None, None
    below = [(k, g) for k, g in zip(strikes, gex) if k < price and abs(k - price) / price <= 0.15]
    above = [(k, g) for k, g in zip(strikes, gex) if k > price and abs(k - price) / price <= 0.15]
    put_wall = min(below, key=lambda x: x[1])[0] if below else None     # most negative
    call_wall = max(above, key=lambda x: x[1])[0] if above else None    # most positive
    return put_wall, call_wall

def _tradier_json(path, params):
    """Fetch current executable option NBBO from Render's Tradier market-data token."""
    token = os.getenv("TRADIER_TOKEN", "").strip()
    if not token:
        return None
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"https://api.tradier.com/v1{path}?{query}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _tradier_rows(theta_url):
    """Translate the two ThetaData calls used by EMBER into Tradier responses.

    The live cloud scanner deliberately uses current executable NBBO instead
    of a local Terminal's prior-close mark.  Longs remain priced at ask and
    shorts at bid, so this is the conservative fill convention required by
    the live executor.
    """
    parsed = urllib.parse.urlparse(theta_url)
    params = urllib.parse.parse_qs(parsed.query)
    symbol = (params.get("symbol") or [""])[0].upper()
    if not symbol:
        return []
    if parsed.path.endswith("/option/list/expirations"):
        payload = _tradier_json(
            "/markets/options/expirations",
            {"symbol": symbol, "includeAllRoots": "true", "strikes": "false"},
        ) or {}
        dates = (payload.get("expirations") or {}).get("date") or []
        if isinstance(dates, str):
            dates = [dates]
        return [{"expiration": str(value)} for value in dates]
    if parsed.path.endswith("/option/history/quote"):
        raw_expiry = (params.get("expiration") or [""])[0]
        if len(raw_expiry) == 8 and raw_expiry.isdigit():
            expiry = f"{raw_expiry[:4]}-{raw_expiry[4:6]}-{raw_expiry[6:]}"
        else:
            expiry = raw_expiry
        payload = _tradier_json(
            "/markets/options/chains",
            {"symbol": symbol, "expiration": expiry, "greeks": "false"},
        ) or {}
        options = (payload.get("options") or {}).get("option") or []
        if isinstance(options, dict):
            options = [options]
        return [
            {
                "right": str(row.get("option_type") or "").upper(),
                "strike": row.get("strike"),
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "bid_size": row.get("bidsize"),
                "ask_size": row.get("asksize"),
            }
            for row in options
            if row.get("strike") is not None
        ]
    return []


def theta_csv(url):
    source = os.getenv("EMBER_OPTION_QUOTE_SOURCE", "").strip().lower()
    if source == "tradier" or os.getenv("RENDER", "").strip().lower() == "true":
        return _tradier_rows(url)
    try:
        with urllib.request.urlopen(url, timeout=30) as r: return list(csv.DictReader(io.StringIO(r.read().decode())))
    except Exception: return []

def theta_probe():
    """Fix 2: single connectivity check for the local ThetaData v3 Terminal at scan start,
    same endpoint convention as ingest/pull_stock_eod_theta.py's _request(). An HTTPError means
    the Terminal answered (even a 'no data' code) -- reachable. Any other exception (connection
    refused, timeout) means the Terminal is down. Never raises."""
    source = os.getenv("EMBER_OPTION_QUOTE_SOURCE", "").strip().lower()
    if source == "tradier" or os.getenv("RENDER", "").strip().lower() == "true":
        payload = _tradier_json("/markets/clock", {})
        return bool(payload and payload.get("clock"))
    today_str = dt.date.today().strftime("%Y%m%d")
    url = f"{THETA}/v3/stock/history/eod?symbol=SPY&start_date={today_str}&end_date={today_str}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r: r.read()
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False

def leg_spread_pct(bid, ask):
    """(ask-bid)/mid*100 for one option leg. None if either side of the market is missing."""
    bid, ask = float(bid or 0), float(ask or 0)
    if bid <= 0 or ask <= 0: return None
    mid = (ask + bid) / 2.0
    return round((ask - bid) / mid * 100, 2) if mid else None

def structure_liquidity(legs):
    """legs = [(bid, ask), ...] for every leg of a chosen structure. Returns (spread_pct,
    liquid) -- spread_pct = max per-leg spread; liquid requires every leg two-sided AND
    spread_pct <= LIQ_SPREAD_MAX. (None, False) if any leg has no two-sided quote."""
    pcts = []
    for bid, ask in legs:
        p = leg_spread_pct(bid, ask)
        if p is None: return None, False
        pcts.append(p)
    if not pcts: return None, False
    spread_pct = max(pcts)
    return spread_pct, spread_pct <= LIQ_SPREAD_MAX

def _Phi(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
def bs_price(S, K, T, sigma, right, r=0.04):
    if T <= 0 or sigma <= 0: return max(S - K, 0) if right == "CALL" else max(K - S, 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T)); d2 = d1 - sigma * math.sqrt(T)
    return S * _Phi(d1) - K * math.exp(-r * T) * _Phi(d2) if right == "CALL" else K * math.exp(-r * T) * _Phi(-d2) - S * _Phi(-d1)
def implied_vol(price, S, K, T, right):
    lo, hi = 0.01, 5.0
    if price <= bs_price(S, K, T, 0.01, right): return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, mid, right) > price: hi = mid
        else: lo = mid
    return 0.5 * (lo + hi)

def pick_expiry(t, sess):
    """25-45 DTE expiry closest to 35 DTE, from the live ThetaData Terminal. Shared by
    option_structures and volume_flow so both price/size and the volume context use the same
    contract month."""
    exps = [dt.date.fromisoformat(r["expiration"]) for r in theta_csv(f"{THETA}/v3/option/list/expirations?symbol={t}")]
    cands = [e for e in exps if 25 <= (e - sess).days <= 45]
    if not cands: return None
    return min(cands, key=lambda x: abs((x - sess).days - 35))

def option_structures(t, side, entry, target, stop, sess, exp, iv_rank):
    """Price both structures off one ThetaData Terminal NBBO snapshot (long legs at the ask,
    short legs at the bid; snapshot = sess's 15:59 close per the fill-convention docstring):
      single   = ATM long call/put at the ask (unchanged math from the original scanner).
      vertical = ATM long (ask) / target-strike short (bid), same right as single.
    Picks structure="vertical" if iv_rank>50 and a priceable short leg exists, else "single" --
    for names priced <=$80. Above $80 (Leron 2026-09-16), structure is FORCED to "vertical"
    regardless of iv_rank and the short strike is chosen by width, not by nearest-to-target:
    the largest listed strike (same side as before) whose width*100 <= MAX_CONTRACT*100
    (vert_width records the width); no bare "single" above $80 -- structure=None if no listed
    strike fits under the cap. Always records both prices; contract/debit/cost_usd/
    opt_rr_floor/opt_rr_7d reflect the chosen structure only. spread_pct/struct_liquid = the
    chosen structure's per-leg spread (section E's liquidity gate; combined with the row's
    name-level OI/vol check by the caller). Never raises -- returns a None-shaped dict with
    `note` on failure."""
    none_shaped = dict(structure=None, iv_rank=iv_rank, single_debit=None, single_rr=None,
                        vert_debit=None, vert_rr=None, vert_short_strike=None, vert_width=None, contract=None,
                        debit=None, cost_usd=None, pct_of_500=None, opt_rr_floor=None, opt_rr_7d=None,
                        structure_note=None, skew_px=None, note=None, spread_pct=None, struct_liquid=False)
    if exp is None:
        r = dict(none_shaped); r["note"] = "no 25-45 DTE expiry / Terminal down"; return r
    rows = theta_csv(f"{THETA}/v3/option/history/quote?symbol={t}&expiration={exp:%Y%m%d}&strike=*&start_date={sess:%Y%m%d}&end_date={sess:%Y%m%d}&interval=1m&start_time=15:59:00&end_time=15:59:00")
    right = "CALL" if side == "long" else "PUT"
    same = [r for r in rows if r.get("right") == right]
    ask_rows = [r for r in same if float(r.get("ask", 0) or 0) > 0]
    if not ask_rows:
        r = dict(none_shaped); r["note"] = "no quote"; return r
    atm = min(ask_rows, key=lambda r: abs(float(r["strike"]) - entry)); K, ask = float(atm["strike"]), float(atm["ask"])
    bid_atm = float(atm.get("bid", 0) or 0)

    iv_t = max(target - K, 0) if side == "long" else max(K - target, 0)
    iv_s = max(stop - K, 0) if side == "long" else max(K - stop, 0)
    T0 = (exp - sess).days / 365.0; T1 = max((exp - sess).days - 10, 1) / 365.0
    sig = implied_vol(ask, entry, K, T0, right)
    v_t = bs_price(target, K, T1, sig, right) if sig else iv_t; v_s = bs_price(stop, K, T1, sig, right) if sig else iv_s
    single_debit = round(ask, 2)
    single_rr = round((iv_t - ask) / (ask - iv_s), 2) if ask - iv_s > 0 else None
    single_opt_rr_7d = round((v_t - ask) / (ask - v_s), 2) if ask - v_s > 0 else None

    width_forced = entry > 80   # Leron 2026-09-16: liquidity lives above $80, cost control moves to structure
    bid_rows = [r for r in same if float(r.get("bid", 0) or 0) > 0 and float(r["strike"]) != K]
    vert_debit = vert_rr = vert_short_strike = vert_width = ask2 = bid2 = None
    structure_note = None
    if bid_rows:
        if width_forced:
            dir_rows = [r for r in bid_rows if (float(r["strike"]) > K if right == "CALL" else float(r["strike"]) < K)]
            cap_rows = [r for r in dir_rows if abs(float(r["strike"]) - K) * 100 <= MAX_CONTRACT * 100 + 1e-6]
            short = max(cap_rows, key=lambda r: abs(float(r["strike"]) - K)) if cap_rows else None
        else:
            short = min(bid_rows, key=lambda r: abs(float(r["strike"]) - target))
        if short is not None:
            K2, bid2 = float(short["strike"]), float(short["bid"])
            ask2 = float(short.get("ask", 0) or 0)
            width, debit = abs(K2 - K), round(ask - bid2, 2)
            if debit > 0:
                vert_short_strike, vert_debit, vert_width = K2, debit, width
                vert_rr = round((width - debit) / debit, 2)
            else: structure_note = "no bid on short"
        else: structure_note = "no width <= cap above $80" if width_forced else "no bid on short"
    else: structure_note = "no bid on short"

    if width_forced:
        structure = "vertical" if vert_debit is not None else None
    else:
        structure = "vertical" if (iv_rank is not None and iv_rank > 50 and vert_debit is not None) else "single"
    right_c = "C" if right == "CALL" else "P"
    if structure == "vertical":
        contract = f"{t} {exp:%Y-%m-%d} {K:g}/{vert_short_strike:g}{right_c}"
        debit, cost_usd, opt_rr_floor, opt_rr_7d = vert_debit, round(vert_debit * 100), vert_rr, None
        spread_pct, struct_liquid = structure_liquidity([(bid_atm, ask), (bid2, ask2)])
    elif structure == "single":
        contract = f"{t} {exp:%Y-%m-%d} {K:g}{right_c}"
        debit, cost_usd, opt_rr_floor, opt_rr_7d = single_debit, round(single_debit * 100), single_rr, single_opt_rr_7d
        spread_pct, struct_liquid = structure_liquidity([(bid_atm, ask)])
    else:   # width_forced (>$80) and no listed strike fits under the cap -- no bare single above $80
        contract = debit = cost_usd = opt_rr_floor = opt_rr_7d = None
        spread_pct, struct_liquid = None, False
    if cost_usd is not None and cost_usd > MAX_CONTRACT * 100:
        note = f"{contract} @ {debit:.2f} = ${cost_usd} > ${MAX_CONTRACT*100:.0f} account"
    elif structure is None and width_forced:
        note = "no vertical width <= cap for $80+ name (liquidity lives above $80; spreads keep cost <= cap)"
    else:
        note = None

    calls = [r for r in rows if r.get("right") == "CALL" and float(r.get("ask", 0) or 0) > 0]
    puts = [r for r in rows if r.get("right") == "PUT" and float(r.get("ask", 0) or 0) > 0]
    skew_px = None
    if calls and puts:
        c5 = min(calls, key=lambda r: abs(float(r["strike"]) - entry * 1.05))
        p5 = min(puts, key=lambda r: abs(float(r["strike"]) - entry * 0.95))
        c_ask, p_ask = float(c5["ask"]), float(p5["ask"])
        skew_px = round(p_ask / c_ask, 3) if c_ask else None

    return dict(structure=structure, iv_rank=iv_rank, single_debit=single_debit, single_rr=single_rr,
                vert_debit=vert_debit, vert_rr=vert_rr, vert_short_strike=vert_short_strike, vert_width=vert_width,
                contract=contract, debit=debit, cost_usd=cost_usd, pct_of_500=(round(cost_usd / 5.0) if cost_usd is not None else None),
                opt_rr_floor=opt_rr_floor, opt_rr_7d=opt_rr_7d, structure_note=structure_note,
                skew_px=skew_px, note=note, spread_pct=spread_pct, struct_liquid=struct_liquid)

def volume_flow(t, side, price, target, stop, exp, cached):
    """Strike-by-strike options volume toward target vs toward stop (/tickers/{t}/options/volume),
    at the same expiry option_structures (RR) or the chosen structure (BOUNCE) uses. CONTEXT
    ONLY -- never raises, never changes which rows are setups/marginal/hidden."""
    none_row = dict(flow_exp=None, flow_with=0, flow_against=0, flow_tilt=None, flow_note="no expiry")
    if exp is None: return none_row
    exp_str = f"{exp:%Y-%m-%d}"
    try:
        cache_name = f"vol_{t}_{exp_str}"
        p = CACHE_DIR / f"{cache_key(cache_name)}.json"
        was_cached = p.exists()
        if cached and not was_cached:
            return dict(flow_exp=exp_str, flow_with=0, flow_against=0, flow_tilt=None, flow_note="not cached")
        d = tv_get(f"/tickers/{t}/options/volume?exp={exp_str}", cache_name, expensive=False)
        if not was_cached: time.sleep(1.1)
        if not d or "error" in d: return dict(flow_exp=exp_str, flow_with=0, flow_against=0, flow_tilt=None, flow_note="no volume data")
        data = d.get("data", d)
        pts = data.get("points") or []
        if not pts: return dict(flow_exp=exp_str, flow_with=0, flow_against=0, flow_tilt=None, flow_note="no volume yet")
        rows = [(float(x["strike"]), int(x.get("call_volume", 0) or 0), int(x.get("put_volume", 0) or 0)) for x in pts]
        if side == "long":
            with_v = sum(cv for k, cv, pv in rows if price < k <= target)
            against_v = sum(pv for k, cv, pv in rows if stop <= k < price)
        else:
            with_v = sum(pv for k, cv, pv in rows if target <= k < price)
            against_v = sum(cv for k, cv, pv in rows if price < k <= stop)
        return dict(flow_exp=exp_str, flow_with=with_v, flow_against=against_v, flow_tilt=round(with_v / max(against_v, 1), 2), flow_note=None)
    except Exception as e:
        return dict(flow_exp=exp_str, flow_with=0, flow_against=0, flow_tilt=None, flow_note=f"flow error: {e}")

# ---- F. BOUNCE helpers ----
def rsi14_wilder(closes):
    """Wilder's RSI(14) off an ascending list of closes. None with fewer than 15 points (14
    deltas needed to seed the first average)."""
    if not closes or len(closes) < 15: return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(x, 0.0) for x in deltas]; losses = [max(-x, 0.0) for x in deltas]
    avg_gain, avg_loss = sum(gains[:14]) / 14, sum(losses[:14]) / 14
    for g, l in zip(gains[14:], losses[14:]):
        avg_gain = (avg_gain * 13 + g) / 14
        avg_loss = (avg_loss * 13 + l) / 14
    if avg_loss == 0: return 100.0
    return round(100 - 100 / (1 + avg_gain / avg_loss), 2)

def fetch_rsi14(t):
    """Daily-close RSI(14), the BOUNCE signal. Source: /tickers/{t}/series, cached per-name on
    the daily key like /tickers (60-min TTL under --live). Payload shape (tv.series.v2):
    {"data": {"points": [{"date": "YYYY-MM-DD", "price": <close>, "iv_rank":.., "gex_flip":..,
    "pc_25d_ratio":..}, ...]}}, points ascending by date, ~124 points on the default 180d
    window. Falls back to data/stock_eod/{t}.parquet's Close column if the series has fewer
    than 30 closes (or the endpoint has no data); None if neither has enough history. Never
    raises."""
    closes = None
    d = tv_get(f"/tickers/{t}/series", f"series_{t}", ttl_s=TICKER_TTL_S, force_daily=True)
    if d and "error" not in d:
        pts = (d.get("data", d) or {}).get("points") or []
        cl = [float(p["price"]) for p in pts if p.get("price") is not None]
        if len(cl) >= 30: closes = cl
    if closes is None:
        p = STOCK_EOD / f"{t}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                col = "Close" if "Close" in df.columns else "close"
                cl = df[col].dropna().astype(float).tolist()
                if len(cl) >= 15: closes = cl
            except Exception: pass
    return rsi14_wilder(closes) if closes else None

def bounce_term_structure(t, price, sess):
    """Up to 3 listed expiries with 21<=DTE<=45 (nearest-first), one ThetaData Terminal 15:59
    snapshot per expiry (same quote pull as option_structures). metric = atm_straddle_ask /
    sqrt(DTE): the `call` leg picks the cheapest (lowest) vol-per-time expiry, the `pcs` leg
    picks the richest (highest) -- sell premium where it's rich, buy where it's cheap. Returns
    a list of dicts (exp, dte, metric, call_strike, call_ask, call_bid, rows) sorted by DTE
    ascending; [] if the Terminal has no listed expiries in the window or no priceable ATM
    straddle. Never raises."""
    exps = [dt.date.fromisoformat(r["expiration"]) for r in theta_csv(f"{THETA}/v3/option/list/expirations?symbol={t}")]
    cands = sorted([e for e in exps if 21 <= (e - sess).days <= 45], key=lambda e: (e - sess).days)[:3]
    out = []
    for exp in cands:
        dte = (exp - sess).days
        rows = theta_csv(f"{THETA}/v3/option/history/quote?symbol={t}&expiration={exp:%Y%m%d}&strike=*&start_date={sess:%Y%m%d}&end_date={sess:%Y%m%d}&interval=1m&start_time=15:59:00&end_time=15:59:00")
        calls = [r for r in rows if r.get("right") == "CALL" and float(r.get("ask", 0) or 0) > 0]
        puts = [r for r in rows if r.get("right") == "PUT" and float(r.get("ask", 0) or 0) > 0]
        if not calls or not puts: continue
        c_atm = min(calls, key=lambda r: abs(float(r["strike"]) - price))
        p_atm = min(puts, key=lambda r: abs(float(r["strike"]) - price))
        metric = round((float(c_atm["ask"]) + float(p_atm["ask"])) / math.sqrt(dte), 4)
        out.append(dict(exp=exp, dte=dte, metric=metric, call_strike=float(c_atm["strike"]),
                         call_ask=float(c_atm["ask"]), call_bid=float(c_atm.get("bid", 0) or 0), rows=rows))
    return out

def price_bounce_call(entry, target, stop, call_leg):
    """Long ATM call at the ask, priced off bounce_term_structure's cheapest-vol-per-time
    expiry. Same floor/7d math as option_structures' single leg. call_spread_pct/
    call_struct_liquid = section E's liquidity check on this one leg. None-shaped on no leg /
    no quote."""
    none_shaped = dict(call_debit=None, call_cost_usd=None, call_rr_floor=None, call_rr_7d=None,
                        call_note=None, call_spread_pct=None, call_struct_liquid=False)
    if call_leg is None: return none_shaped
    K, ask, bid, dte = call_leg["call_strike"], call_leg["call_ask"], call_leg["call_bid"], call_leg["dte"]
    iv_t, iv_s = max(target - K, 0), max(stop - K, 0)
    T0, T1 = dte / 365.0, max(dte - 10, 1) / 365.0
    sig = implied_vol(ask, entry, K, T0, "CALL")
    v_t = bs_price(target, K, T1, sig, "CALL") if sig else iv_t
    v_s = bs_price(stop, K, T1, sig, "CALL") if sig else iv_s
    debit = round(ask, 2)
    rr_floor = round((iv_t - debit) / (debit - iv_s), 2) if debit - iv_s > 0 else None
    rr_7d = round((v_t - debit) / (debit - v_s), 2) if debit - v_s > 0 else None
    cost_usd = round(debit * 100)
    note = f"{K:g}C ${cost_usd} > ${MAX_CONTRACT*100:.0f} account" if cost_usd > MAX_CONTRACT * 100 else None
    spread_pct, struct_liquid = structure_liquidity([(bid, ask)])
    return dict(call_debit=debit, call_cost_usd=cost_usd, call_rr_floor=rr_floor, call_rr_7d=rr_7d,
                call_note=note, call_spread_pct=spread_pct, call_struct_liquid=struct_liquid)

def price_bounce_pcs(entry, put_wall, pcs_leg, stop):
    """Put credit spread: short the highest listed strike <= put_wall, long the strike `width`
    below where width is the largest listed increment <= $2.50 (collateral cap). credit =
    bid(short) - ask(long); pcs_rr_stop = credit / max(loss_at_stop, 0.01), loss_at_stop = the
    spread's BS value at the stop price (T-5 days, short leg's ask IV) minus the credit
    collected. pcs_spread_pct/pcs_struct_liquid = section E's liquidity check across both legs
    (needs a two-sided market on each). None-shaped (with pcs_note) on any missing strike/quote."""
    none_shaped = dict(pcs_credit=None, pcs_width=None, pcs_short=None, pcs_max_loss=None,
                        pcs_rr_stop=None, pcs_note=None, pcs_spread_pct=None, pcs_struct_liquid=False)
    if pcs_leg is None: return none_shaped
    rows, dte = pcs_leg["rows"], pcs_leg["dte"]
    puts = [r for r in rows if r.get("right") == "PUT"]
    strikes = sorted(set(float(r["strike"]) for r in puts))
    below_eq = [k for k in strikes if k <= put_wall]
    if not below_eq:
        r = dict(none_shaped); r["pcs_note"] = "no strike <= put wall"; return r
    short_strike = max(below_eq)
    width_cands = [k for k in strikes if k < short_strike and short_strike - k <= 2.50]
    if not width_cands:
        r = dict(none_shaped); r["pcs_short"] = short_strike; r["pcs_note"] = "no width <= $2.50 cap"; return r
    long_strike = min(width_cands)
    width = round(short_strike - long_strike, 2)
    short_row = next((r for r in puts if float(r["strike"]) == short_strike), None)
    long_row = next((r for r in puts if float(r["strike"]) == long_strike), None)
    bid_short = float((short_row or {}).get("bid", 0) or 0)
    ask_short = float((short_row or {}).get("ask", 0) or 0)
    ask_long = float((long_row or {}).get("ask", 0) or 0)
    bid_long = float((long_row or {}).get("bid", 0) or 0)
    if bid_short <= 0 or ask_long <= 0 or ask_short <= 0 or bid_long <= 0:
        r = dict(none_shaped); r["pcs_short"] = short_strike; r["pcs_width"] = width; r["pcs_note"] = "no quote"; return r
    credit = round(bid_short - ask_long, 2)
    max_loss = round(width * 100 - credit * 100, 2)
    T0, T1 = dte / 365.0, max(dte - 5, 1) / 365.0
    sig = implied_vol(ask_short, entry, short_strike, T0, "PUT")
    if sig:
        short_val = bs_price(stop, short_strike, T1, sig, "PUT"); long_val = bs_price(stop, long_strike, T1, sig, "PUT")
    else:
        short_val = max(short_strike - stop, 0); long_val = max(long_strike - stop, 0)
    loss_at_stop = (short_val - long_val) - credit
    pcs_rr_stop = round(credit / max(loss_at_stop, 0.01), 2)
    cap_note = f"collateral ${width*100:.0f} > ${MAX_CONTRACT*100:.0f} account" if width * 100 > MAX_CONTRACT * 100 else None
    spread_pct, struct_liquid = structure_liquidity([(bid_short, ask_short), (bid_long, ask_long)])
    return dict(pcs_credit=credit, pcs_width=width, pcs_short=short_strike, pcs_max_loss=max_loss,
                pcs_rr_stop=pcs_rr_stop, pcs_note=cap_note, pcs_spread_pct=spread_pct, pcs_struct_liquid=struct_liquid)

# ---- A. candidate sources ----
def item_score(it):
    v = it.get("opportunity_score", it.get("income_score"))
    return float(v) if v is not None else 0.0

def normalize_items(d, source_tag):
    """Pull items[] out of a TV list payload and tag each with its source list. None = no
    usable payload (missing/error/404) so the caller can log one line and move on."""
    if not d or "error" in d: return None
    items = ((d.get("data") or {}).get("items")) or []
    out = []
    for it in items:
        if not it.get("ticker"): continue
        it["_source"] = source_tag; out.append(it)
    return out

def fetch_idea():
    d = tv_get(f"/top-setups?limit=50&price_min=15&price_max={PRICE_MAX}", "top_setups")
    items = normalize_items(d, "idea")
    if items is None: print("  source idea: no /top-setups data"); return [], ""
    return items, ((d or {}).get("meta") or {}).get("asof", "")

def fetch_presets():
    out = []
    for name in PRESETS:
        d = tv_get(f"/top-setups/screener/{name}?limit=50&price_min=15&price_max={PRICE_MAX}", f"screener_{name}", expensive=True)
        items = normalize_items(d, name)
        if items is None: print(f"  source {name}: no data (404/error/empty)"); continue
        out += items
    return out

def fetch_income():
    d = tv_get("/income-setups?limit=50", "income_setups")
    items = normalize_items(d, "income")
    if items is None: print("  source income: no /income-setups data"); return []
    keep = []
    for it in items:
        try:
            if 15 <= float(it.get("price")) <= PRICE_MAX: keep.append(it)
        except (TypeError, ValueError): pass
    return keep

idea_items, asof = fetch_idea()
preset_items = fetch_presets()
income_items = fetch_income()

by_ticker = {}
for it in idea_items + preset_items + income_items: by_ticker.setdefault(it["ticker"], []).append(it)

candidates = []
for t, group in by_ticker.items():
    sources = []
    for it in group:
        if it["_source"] not in sources: sources.append(it["_source"])
    directed = [it for it in group if it.get("recommended_direction") in ("long", "short")]
    has_income = any(it["_source"] == "income" for it in group)
    dir_conflict, direction = False, None
    if directed:
        dirs = {it["recommended_direction"] for it in directed}
        if len(dirs) > 1:
            dir_conflict = True
            idea_it = next((it for it in directed if it["_source"] == "idea"), None)
            direction = idea_it["recommended_direction"] if idea_it else max(directed, key=item_score)["recommended_direction"]
        else: direction = dirs.pop()
    best = max(group, key=item_score)
    candidates.append(dict(ticker=t, direction=direction, has_income=has_income, score=item_score(best),
                            source="|".join(sources), n_sources=len(sources), dir_conflict=dir_conflict, best_item=best))
candidates.sort(key=lambda r: -r["score"])   # opportunity_score desc so truncation drops the weakest

# ---- run ----
sess = dt.date.today()
cloud_quotes = os.getenv("EMBER_OPTION_QUOTE_SOURCE", "").strip().lower() == "tradier" or \
    os.getenv("RENDER", "").strip().lower() == "true"
if not cloud_quotes:
    if dt.datetime.now().hour < 16: sess -= dt.timedelta(days=1)
    while sess.weekday() >= 5: sess -= dt.timedelta(days=1)

# Fix 2: ThetaData must be loud, not a fake "0 setups" -- probe once before pricing any legs.
if not theta_probe():
    print(f"THETADATA UNREACHABLE ({THETA.replace('http://', '')}) -- option legs cannot be priced; ledger NOT written this scan")
    if "--cached" not in sys.argv:
        with open(RUNS_LOG, "a") as f:
            f.write(f"{SCAN_TIME_ISO} live={LIVE} theta_down=True setups=NA\n")
    sys.exit(3)

setups, marginal, hidden, nodata, illiquid = [], [], [], [], []
bounce_rows, bounce_hidden, bounce_illiquid = [], [], []
bounce_signal_n = 0
deadline = SCAN_START + dt.timedelta(seconds=TRUNCATE_S)
truncated_n = 0
vol_reported_n, vol_zero_n = 0, 0     # Fix 1: names with a reported call_vol+put_vol field, and how many are 0
theta_priced_n, theta_missing_n = 0, 0  # Fix 2: names where an option-leg price was attempted via ThetaData, and how many came back quote_missing
for i, cand in enumerate(candidates):
    if dt.datetime.now() >= deadline: truncated_n = len(candidates) - i; break
    t = cand["ticker"]
    st = tv_get(f"/tickers/{t}", f"ticker_{t}", ttl_s=TICKER_TTL_S, force_daily=True)
    if not st or "error" in st: nodata.append((t, "no /tickers payload")); continue
    d = st.get("data", st); price = float(d["underlying"]["price"])
    flip = (d.get("gamma", {}).get("flip") or {}).get("price")
    em = d["expected_move"]; m1d, m1w = price * em["expected_move_pct_1d"] / 100, price * em["expected_move_pct_1w"] / 100
    maxg = (d.get("gamma", {}).get("structure") or {}).get("max_gamma_strike")
    curve = tv_get(f"/tickers/{t}/curves/gex_by_strike?exp=combined", f"gex_{t}", expensive=True, ttl_s=TICKER_TTL_S, force_daily=True)
    pw, cw = walls_from_curve(curve, price)
    if pw is None and maxg and maxg < price: pw = maxg
    if cw is None and maxg and maxg > price: cw = maxg

    dist_to_flip_pct = round((price - flip) / price * 100, 2) if flip else None
    put_call = (d.get("positioning") or {}).get("put_call") or {}
    pcr_vol, pcr_oi = put_call.get("pcr_volume"), put_call.get("pcr_oi")
    pcr_oi_d30 = (put_call.get("pcr_oi_change") or {}).get("d30")
    spec_raw = (d.get("call_flow") or {}).get("speculative_interest_score")
    spec_score = round(spec_raw, 3) if spec_raw is not None else None
    iv_rank = cand["best_item"].get("iv_rank")
    if iv_rank is None: iv_rank = (d.get("underlying", {}).get("iv") or {}).get("iv_rank")
    rsi14 = fetch_rsi14(t)

    # name-level liquidity (section E): combined OI/volume from the same /tickers payload
    call_oi, put_oi = put_call.get("call_oi"), put_call.get("put_oi")
    call_vol, put_vol = put_call.get("call_vol"), put_call.get("put_vol")
    opt_oi = (call_oi or 0) + (put_oi or 0) if (call_oi is not None or put_oi is not None) else None
    opt_vol_reported = (call_vol or 0) + (put_vol or 0) if (call_vol is not None or put_vol is not None) else None
    # Fix 1: TV's intraday put_call.pcr_volume is 0 for every name -- a reported 0 is UNKNOWN,
    # not "thin"; the LIQ_VOL_MIN floor applies only when opt_vol is a positive number.
    vol_unknown = opt_vol_reported is not None and opt_vol_reported == 0
    if opt_vol_reported is not None: vol_reported_n += 1
    if vol_unknown: vol_zero_n += 1
    opt_vol = None if vol_unknown else opt_vol_reported
    liq_note_name = "thin OI" if (opt_oi is not None and opt_oi < LIQ_OI_MIN) else \
                     ("thin vol" if (opt_vol is not None and opt_vol < LIQ_VOL_MIN) else
                      ("vol unknown" if vol_unknown else None))
    liq_gate_fail_name = liq_note_name in ("thin OI", "thin vol")   # "vol unknown" is informational only, never gates

    # ---- RR (geometry) strategy, strategy="rr" ----
    side = cand["direction"]
    if side is None:
        if cand["has_income"] and flip is not None and price > flip: side = "long"
        elif cand["has_income"]: nodata.append((t, "income: below flip"))
        else: nodata.append((t, "no direction"))

    if side is not None:
        if side == "long":
            stop_c = [x for x in (pw, price - m1d) if x]; targ_c = [x for x in (cw, price + m1w) if x]
            stop = max(stop_c) * (1 - BUF); target = min(targ_c)
            stop_src = "put wall" if pw and max(stop_c) == pw else "1d band"; targ_src = "call wall" if cw and min(targ_c) == cw else "1w band"
        else:
            stop_c = [x for x in (cw, price + m1d) if x]; targ_c = [x for x in (pw, price - m1w) if x]
            stop = min(stop_c) * (1 + BUF); target = max(targ_c)
            stop_src = "call wall" if cw and min(stop_c) == cw else "1d band"; targ_src = "put wall" if pw and max(targ_c) == pw else "1w band"
        risk, reward = abs(price - stop), abs(target - price)
        if risk <= 0 or reward <= 0:
            nodata.append((t, "degenerate levels"))
        else:
            rr = reward / risk
            row = dict(ticker=t, schema_version=2, score=cand["score"], dir=side, source=cand["source"], n_sources=cand["n_sources"],
                       dir_conflict=cand["dir_conflict"], type=cand["best_item"].get("recommended_trade_type") or cand["best_item"].get("strategy"),
                       price=round(price, 2), stop=round(stop, 2), stop_src=stop_src, target=round(target, 2), target_src=targ_src, stock_rr=round(rr, 2),
                       flip=flip, regime=("neg-gamma" if flip and price < flip else "pos-gamma" if flip else "?"), dist_to_flip_pct=dist_to_flip_pct,
                       put_wall=pw, call_wall=cw, em_1d_pct=round(em["expected_move_pct_1d"], 2), em_1w_pct=round(em["expected_move_pct_1w"], 2),
                       iv_rank=iv_rank, pcr_vol=pcr_vol, pcr_oi=pcr_oi, pcr_oi_d30=pcr_oi_d30, spec_score=spec_score, rsi14=rsi14,
                       strategy="rr", opt_oi=opt_oi, opt_vol=opt_vol,
                       tv_structure=",".join((cand["best_item"].get("trade_setup") or {}).get("structures", [])),
                       tv_asof=asof, scan_date=str(sess), scan_time=SCAN_TIME_ISO)
            if rr >= 2.0:
                e = pick_expiry(t, sess)
                row.update(option_structures(t, side, price, target, stop, sess, e, iv_rank))
                row.update(volume_flow(t, side, price, target, stop, e, "--cached" in sys.argv))
                quote_missing = row.get("structure") is None
                theta_priced_n += 1
                if quote_missing: theta_missing_n += 1
                row["liquid"] = bool(row.get("struct_liquid")) and not liq_gate_fail_name and not quote_missing
                row["liq_note"] = liq_note_name if liq_note_name else ("no quote" if quote_missing or row.get("spread_pct") is None else None)
                (setups if row["liquid"] else illiquid).append(row)
            elif rr >= 1.0:
                e = pick_expiry(t, sess)
                row.update(volume_flow(t, side, price, target, stop, e, "--cached" in sys.argv))
                row["spread_pct"], row["liquid"], row["liq_note"] = None, None, liq_note_name
                marginal.append(row)
            else:
                row["spread_pct"], row["liquid"], row["liq_note"] = None, None, liq_note_name
                hidden.append(row)

    # ---- BOUNCE strategy, strategy="bounce" ----
    bounce_hit = rsi14 is not None and rsi14 < 30 and pw is not None and pw * 0.97 <= price <= pw * 1.03
    if bounce_hit:
        bounce_signal_n += 1
        b_stop = price * (1 - 0.01) if price < pw else pw * (1 - BUF)
        b_targ_c = [x for x in (cw, price + m1w) if x]
        b_target = min(b_targ_c) if b_targ_c else None
        if b_target is not None and (price - b_stop) > 0 and (b_target - price) > 0:
            b_rr = round((b_target - price) / (price - b_stop), 2)
            earnings_date = next((it.get("earnings_date") for it in by_ticker.get(t, []) if it.get("earnings_date")), None)
            days_to_earnings, ed_date = None, None
            if earnings_date:
                try:
                    ed_date = dt.date.fromisoformat(earnings_date)
                    days_to_earnings = (ed_date - dt.date.today()).days
                except Exception: pass
            b_row = dict(ticker=t, schema_version=2, dir="long", source=cand["source"], price=round(price, 2), rsi14=rsi14,
                         put_wall=pw, dist_to_wall_pct=round((price - pw) / price * 100, 2),
                         stop=round(b_stop, 2), target=round(b_target, 2), stock_rr=b_rr,
                         earnings_date=earnings_date, days_to_earnings=days_to_earnings,
                         iv_rank=iv_rank, pcr_vol=pcr_vol, strategy="bounce",
                         opt_oi=opt_oi, opt_vol=opt_vol, scan_date=str(sess), scan_time=SCAN_TIME_ISO)
            if b_rr >= 1.0:
                term = bounce_term_structure(t, price, sess)
                if term:
                    cheapest = min(term, key=lambda x: x["metric"]); richest = max(term, key=lambda x: x["metric"])
                    by_dte = sorted(term, key=lambda x: x["dte"])
                    term_slope = round(by_dte[-1]["metric"] / by_dte[0]["metric"], 3) if len(by_dte) > 1 and by_dte[0]["metric"] else None
                else:
                    cheapest = richest = None; term_slope = None
                b_row["term_slope"] = term_slope
                b_row["call_exp"] = cheapest["exp"] if cheapest else None
                b_row["pcs_exp"] = richest["exp"] if richest else None
                b_row.update(price_bounce_call(price, b_target, b_stop, cheapest))
                b_row.update(price_bounce_pcs(price, pw, richest, b_stop))

                # Leron 2026-09-16: liquidity lives above $80 -- above $80, force pcs (defined-width) regardless of iv_rank, never a bare "call"
                if price > 80:
                    structure = "pcs" if b_row.get("pcs_credit") is not None else None
                else:
                    structure = "pcs" if (iv_rank is not None and iv_rank >= 40 and b_row.get("pcs_credit") is not None) else "call"
                b_row["structure"] = structure
                if structure == "pcs": exp_chosen = b_row["pcs_exp"]
                elif structure == "call": exp_chosen = b_row["call_exp"]
                else: exp_chosen = b_row["pcs_exp"] or b_row["call_exp"]
                b_row["exp"] = exp_chosen
                b_row["earnings_inside_exp"] = bool(ed_date and exp_chosen and ed_date < exp_chosen)
                b_row.update(volume_flow(t, "long", price, b_target, b_stop, exp_chosen, "--cached" in sys.argv))

                if structure == "pcs":
                    spread_pct, struct_liquid, quote_missing = b_row.get("pcs_spread_pct"), b_row.get("pcs_struct_liquid"), b_row.get("pcs_credit") is None
                elif structure == "call":
                    spread_pct, struct_liquid, quote_missing = b_row.get("call_spread_pct"), b_row.get("call_struct_liquid"), b_row.get("call_debit") is None
                else:
                    spread_pct, struct_liquid, quote_missing = None, False, True
                theta_priced_n += 1
                if quote_missing: theta_missing_n += 1
                b_row["spread_pct"] = spread_pct
                b_row["liquid"] = bool(struct_liquid) and not liq_gate_fail_name and not quote_missing
                b_row["liq_note"] = liq_note_name if liq_note_name else ("no quote" if quote_missing or spread_pct is None else None)
                b_row["tier"] = "setup" if b_rr >= 2.0 else "marginal"
                if b_row["tier"] == "setup" and not b_row["liquid"]:
                    bounce_illiquid.append(b_row)
                else:
                    bounce_rows.append(b_row)
            else:
                b_row.update(term_slope=None, call_exp=None, pcs_exp=None, exp=None, structure=None,
                             earnings_inside_exp=None, pcs_credit=None, pcs_width=None, pcs_short=None,
                             pcs_max_loss=None, pcs_rr_stop=None, pcs_note=None, call_debit=None,
                             call_cost_usd=None, call_rr_floor=None, call_rr_7d=None, call_note=None,
                             flow_exp=None, flow_with=0, flow_against=0, flow_tilt=None, flow_note=None,
                             spread_pct=None, liquid=None, liq_note=liq_note_name, tier="hidden")
                bounce_hidden.append(b_row)

def show(rows, title, cols, key=None):
    if rows:
        df = pd.DataFrame(sorted(rows, key=key or (lambda r: -r["stock_rr"])))
        print(f"\n== {title} ==\n" + df[[c for c in cols if c in df.columns]].to_string(index=False))

if truncated_n: print(f"TRUNCATED: {truncated_n} names not evaluated")
print(f"TV candidates as of {asof} | {len(candidates)} unique tickers (idea={len(idea_items)} preset={len(preset_items)} income={len(income_items)}) | "
      f"setups >=2:1: {len(setups)} (illiquid: {len(illiquid)}) | marginal: {len(marginal)} | <1:1 hidden: {len(hidden)} | no data: {len(nodata)}")

# Fix 1: scan-level zero-volume line (TV intraday put_call volume reads 0 for every name some days)
vol_floor_off = vol_reported_n > 0 and (vol_zero_n / vol_reported_n) >= 0.9
if vol_floor_off:
    print("VOL FIELD ZERO FOR ALL NAMES -- volume floor disabled this scan (TV intraday)")
print(f"  vol: {vol_zero_n}/{vol_reported_n} names reported zero call+put volume | vol_floor={'off' if vol_floor_off else 'on'}")

# Fix 2: scan-level degraded-quote line (probe passed but most names have no priceable leg)
theta_degraded = theta_priced_n > 0 and (theta_missing_n / theta_priced_n) >= 0.9
if theta_degraded:
    print(f"THETADATA QUOTES MISSING FOR {theta_missing_n}/{theta_priced_n} NAMES")

SETUP_COLS = ["ticker", "score", "dir", "source", "n_sources", "regime", "rsi14", "price", "stop", "stop_src", "target", "target_src", "stock_rr",
              "structure", "iv_rank", "contract", "debit", "cost_usd", "pct_of_500", "opt_rr_floor", "opt_rr_7d",
              "single_debit", "single_rr", "vert_debit", "vert_rr", "vert_short_strike", "vert_width", "structure_note", "skew_px",
              "flow_exp", "flow_with", "flow_against", "flow_tilt", "flow_note", "note",
              "opt_oi", "opt_vol", "spread_pct", "liquid", "liq_note"]
MARGINAL_COLS = ["ticker", "score", "dir", "source", "n_sources", "regime", "rsi14", "price", "stop", "stop_src", "target", "target_src", "stock_rr",
                  "flow_exp", "flow_with", "flow_against", "flow_tilt", "flow_note",
                  "opt_oi", "opt_vol", "spread_pct", "liquid", "liq_note"]
GEX_COLS = ["ticker", "dir", "price", "stock_rr", "source", "n_sources", "regime", "flip", "dist_to_flip_pct", "put_wall", "call_wall"]
PCR_COLS = ["ticker", "dir", "price", "stock_rr", "source", "n_sources", "spec_score", "pcr_vol", "pcr_oi", "pcr_oi_d30", "iv_rank"]
BOUNCE_COLS = ["ticker", "tier", "source", "price", "rsi14", "put_wall", "dist_to_wall_pct", "stop", "target", "stock_rr",
               "earnings_date", "days_to_earnings", "earnings_inside_exp", "exp", "structure", "call_exp", "pcs_exp", "term_slope",
               "pcs_credit", "pcs_width", "pcs_short", "pcs_max_loss", "pcs_rr_stop", "pcs_note",
               "call_debit", "call_cost_usd", "call_rr_floor", "call_rr_7d", "call_note",
               "flow_with", "pcr_vol", "iv_rank", "opt_oi", "opt_vol", "spread_pct", "liquid", "liq_note"]

show(setups, "SETUPS (>=2:1 on TV walls/bands, priced as long options)", SETUP_COLS)
show(marginal, "MARGINAL (1:1 - 2:1)", MARGINAL_COLS)
if illiquid: show(illiquid, "ILLIQUID (>=2:1 but spread/OI fail)", SETUP_COLS)
if nodata: print("\n== no geometry ==\n" + "\n".join(f"  {t}: {w}" for t, w in nodata))

print(f"\nBOUNCE candidates: RSI<30 near put wall: {bounce_signal_n} | setups >=2:1: "
      f"{sum(1 for r in bounce_rows if r['tier'] == 'setup')} (illiquid: {len(bounce_illiquid)}) | "
      f"marginal: {sum(1 for r in bounce_rows if r['tier'] == 'marginal')} | <1:1 hidden: {len(bounce_hidden)}")
if bounce_rows: show(bounce_rows, "BOUNCE (RSI<30 at put support)", BOUNCE_COLS, key=lambda r: -r["stock_rr"])
else: print("== BOUNCE == none")
if bounce_illiquid: show(bounce_illiquid, "BOUNCE ILLIQUID (>=2:1 but spread/OI fail)", BOUNCE_COLS, key=lambda r: -r["stock_rr"])

gexpcr_pool = setups + marginal + illiquid
show(gexpcr_pool, "GEX VIEW (setups+marginal sorted by |dist_to_flip_pct| asc)", GEX_COLS,
     key=lambda r: (r["dist_to_flip_pct"] is None, abs(r["dist_to_flip_pct"]) if r["dist_to_flip_pct"] is not None else 0))
show(gexpcr_pool, "PCR VIEW (sorted by spec_score desc)", PCR_COLS,
     key=lambda r: (r["spec_score"] is None, -(r["spec_score"] or 0)))

# NEW SINCE LAST SCAN: >=2:1 LIQUID setups not already in today's ledger, keyed on
# (ticker, scan_date, dir, strategy). Illiquid setups never qualify (section E).
existing_keys = set()
if LEDGER.exists():
    with open(LEDGER) as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("scan_date") == str(sess): existing_keys.add((r.get("ticker"), r.get("scan_date"), r.get("dir"), r.get("strategy", "rr")))
            except Exception: pass
new_setups = [r for r in setups if (r["ticker"], r["scan_date"], r["dir"], r["strategy"]) not in existing_keys]
new_bounce = [r for r in bounce_rows if r["tier"] == "setup" and (r["ticker"], r["scan_date"], r["dir"], r["strategy"]) not in existing_keys]
if new_setups: show(new_setups, "NEW SINCE LAST SCAN", SETUP_COLS)
else: print("\n== NEW SINCE LAST SCAN == none")
if new_bounce: show(new_bounce, "NEW BOUNCE SINCE LAST SCAN", BOUNCE_COLS)
else: print("== NEW BOUNCE SINCE LAST SCAN == none")

def send_notify(rr_rows, bounce_new_rows):
    """POST a summary of new setups (both strategies, liquid only) to the KVB notify hub.
    Best-effort: never raises, never fails the run."""
    try:
        n = len(rr_rows) + len(bounce_new_rows)
        pool = rr_rows + bounce_new_rows
        best = max(pool, key=lambda r: r["stock_rr"])

        def _cost(r):
            if r.get("cost_usd") is not None: return r["cost_usd"]
            if r.get("strategy") == "bounce" and r.get("structure") == "call": return r.get("call_cost_usd")
            return None
        fits200 = sum(1 for r in pool if (_cost(r) if _cost(r) is not None else 1e9) <= 200)

        sections = [{"title": "New setups", "rows": [
            [r["ticker"], r["dir"], f"{r['price']}  tgt {r['target']} / stop {r['stop']}", f"{r['stock_rr']}:1",
             r.get("contract") or "-", f"${r['cost_usd']}" if r.get("cost_usd") is not None else "-"]
            for r in rr_rows]}]
        if bounce_new_rows:
            sections.append({"title": "Bounce (oversold at support)", "rows": [
                [r["ticker"], r["dir"], f"{r['price']}  tgt {r['target']} / stop {r['stop']}", f"{r['stock_rr']}:1",
                 r.get("structure") or "-",
                 f"${r['call_cost_usd']}" if r.get("structure") == "call" and r.get("call_cost_usd") is not None else
                 f"${r['pcs_max_loss']}" if r.get("structure") == "pcs" and r.get("pcs_max_loss") is not None else "-"]
                for r in bounce_new_rows]})

        body = {
            "subject": f"EMBER - {n} new setups",
            "headline": f"EMBER: {n} new �2:1 setups at {RUN_HHMM[:2]}:{RUN_HHMM[2:]}",
            "tone": "info",
            "stats": [["setups", str(n)], ["best R:R", f"{best['ticker']} {best['stock_rr']}x"], ["fits $200", str(fits200)]],
            "sections": sections,
            "footer": "tools/ember_ledger.jsonl",
        }
        req = urllib.request.Request("https://kalshi-volarb.onrender.com/api/notify", data=json.dumps(body).encode(),
                                      headers={"X-KVB-Notify": NOTIFY_TOKEN, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r: r.read()
        return True
    except Exception as e:
        print(f"notify: failed ({e})"); return False

notified = False
if "--cached" not in sys.argv and (new_setups or new_bounce):
    if NOTIFY_TOKEN: notified = send_notify(new_setups, new_bounce)
    else: print("notify: KVB_NOTIFY_TOKEN not set, skipped")

if "--cached" in sys.argv:
    print("--cached: ledger/runs log not written")
else:
    with open(LEDGER, "a") as f:
        for r in setups + marginal + illiquid + bounce_rows + bounce_illiquid: f.write(json.dumps(r, default=str) + "\n")
    print(f"\nledger: {LEDGER} (+{len(setups) + len(marginal) + len(illiquid) + len(bounce_rows) + len(bounce_illiquid)} rows)")

    with open(RUNS_LOG, "a") as f:
        f.write(f"{SCAN_TIME_ISO} live={LIVE} setups={len(setups)} marginal={len(marginal)} new={len(new_setups)} "
                f"bounce_setups={sum(1 for r in bounce_rows if r['tier']=='setup')} bounce_marginal={sum(1 for r in bounce_rows if r['tier']=='marginal')} "
                f"bounce_new={len(new_bounce)} notified={notified} vol_floor={'off' if vol_floor_off else 'on'} theta_degraded={theta_degraded}\n")
