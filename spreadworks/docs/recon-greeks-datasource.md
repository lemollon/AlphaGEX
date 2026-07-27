# Recon — options data source & Greeks path (SpreadWorks)

**Date:** 2026-07-26
**Scope:** read-only reconnaissance ahead of adding skew-aware Greeks (vanna,
volga, charm, SABR/Bartlett skew-adjusted delta) and a historical vol-surface
store.
**Analysed ref:** `origin/main` @ `47ed1316` (2026-07-25).

> **Method note — read this first.** SpreadWorks is not a standalone repo; it
> lives in the AlphaGEX monorepo at `spreadworks/`. The local working tree was
> on branch `feat/ripple-ab-bot` @ `daedfa2c`, **129 commits behind
> `origin/main`**, with an unresolved merge conflict
> (`UU ironforge/webapp/src/lib/flare/scanner.ts`). Analysing the checked-out
> files would have described stale code, so every finding below was read from
> `origin/main` via `git show` / `git grep` without checking anything out. All
> line numbers refer to `origin/main`. **Verify the branch before acting on
> this report.**

---

## 1. Executive summary

- **Vendor is Tradier** (`https://api.tradier.com/v1`), Bearer auth, env
  `TRADIER_TOKEN` (with `TRADIER_API_KEY` fallback in one client). A second
  vendor, **TradingVolatility v2**, is used for exactly one metric — IV rank.
  No Polygon / ORATS / ThetaData / Schwab / IBKR / Alpaca / Finnhub / Intrinio.
- **Greeks are BOTH vendor-supplied and locally computed, in three separate
  code paths that do not share an implementation.** Tradier is called with
  `greeks=true` and its delta/gamma/theta/vega/IV are passed through by
  `/api/spreadworks/chain`; a hand-rolled Black-Scholes `_bs_greeks()` at
  `spreadworks/backend/routes.py:1408` computes them independently for
  `/calculate`; and a third partial BS lives in the frontend at
  `spreadworks/frontend/src/utils/blackScholes.js`.
- **The chain-normalisation layer discards most Greeks.** Two independent
  normalisers keep only a subset of Tradier's `greeks` block — this is the
  single biggest obstacle to adding new Greeks (see §2 and the debt register).
- **No historical options persistence exists.** `chain_cache` is a
  single-row-per-`(symbol, expiration)` **overwrite** cache
  (`spreadworks/backend/models.py:58`), not a time series. There is no
  vol-surface store and **no migration tool of any kind** — tables come from
  `Base.metadata.create_all`.
- **Adding response fields is low-risk.** There are **no FastAPI
  `response_model=` declarations anywhere** in the backend, so responses are
  plain dicts, and the frontend is **JSX with no TypeScript types**. New keys
  are additive and will not fail validation on either side.

---

## 2. Findings

### 2.1 Options data source

**Vendor: Tradier.** Three separate call sites, each with its own HTTP client:

| Call site | Client | Base URL |
|---|---|---|
| `spreadworks/backend/routes.py:60` | shared `httpx` on `app.state.http` | `https://api.tradier.com/v1` |
| `spreadworks/backend/bots/routes_helpers.py:17` | own `httpx.Client(timeout=10.0)` (`:35`) | `https://api.tradier.com/v1` |
| `spreadworks/backend/bots/tsunami/data/tradier_client.py:24` | `requests`, `_TIMEOUT = 30` (`:25`) | `https://api.tradier.com/v1` |

**Auth pattern — Bearer header.** `routes.py:87-88`:

```python
def _tradier_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
```

Env var names: `TRADIER_TOKEN` (`routes_helpers.py:18`, `render.yaml:53`).
`tradier_client.py:28-32` accepts `TRADIER_TOKEN` **or** `TRADIER_API_KEY`.
`TRADIER_ACCOUNT_ID` is declared in `render.yaml:55` and `.env.example:19`.

**Endpoints called:**

| Endpoint | Cited at |
|---|---|
| `/markets/quotes` | `routes.py:106`, `tradier_client.py:47`, `routes_helpers.py:135` |
| `/markets/options/chains` | `routes.py:702`, `routes_helpers.py:44`, `tradier_client.py:129` |
| `/markets/options/expirations` | `tradier_client.py:97` |
| `/markets/history` (daily OHLC) | `tradier_client.py:72` |

**Does the response include Greeks and IV? YES — Tradier is asked for them.**
All three chain calls pass `"greeks": "true"` (`routes.py:703`,
`routes_helpers.py:45`, `tradier_client.py:130`).

**Critical: two of the three normalisers throw most of them away.**

`routes.py:736-748` (the `/chain` route) — keeps five Greeks:

```python
greeks = o.get("greeks", {}) or {}
entry = {
    "bid": o.get("bid"), "ask": o.get("ask"),
    ...
    "iv": greeks.get("mid_iv") or greeks.get("smv_vol"),
    "delta": greeks.get("delta"),
    "gamma": greeks.get("gamma"),
    "theta": greeks.get("theta"),
    "vega": greeks.get("vega"),
}
```

`routes_helpers.py:70-74` (the **production scanner** provider) — keeps
**none**:

```python
"options": [
    {"strike": o["strike"], "type": o["option_type"],
     "bid": o.get("bid") or 0, "ask": o.get("ask") or 0}
    for o in data
],
```

`tradier_client.py:143-151` (TSUNAMI) — keeps **gamma only**:

```python
greeks = c.get("greeks") or {}
out.append({
    "strike": float(c["strike"]),
    "bid": float(c.get("bid") or 0),
    "ask": float(c.get("ask") or 0),
    "open_interest": int(c.get("open_interest") or 0),
    "option_type": str(c.get("option_type") or "").lower(),
    "gamma": float(greeks.get("gamma") or 0),
})
```

**Second vendor: TradingVolatility v2**, IV rank only.
`spreadworks/backend/bots/tsunami/data/tv_client.py:52` calls
`{base}/tickers/{symbol}/series?metrics=iv_rank&window=5d`, Bearer auth
(`:54`). Base URL from `TRADING_VOLATILITY_V2_BASE_URL`, defaulting to
`https://stocks.tradingvolatility.net/api/v2` (`:31-35`). Token from
`TRADING_VOLATILITY_API_TOKEN` or `TRADING_VOLATILITY_API_KEY` (`:40-43`).
Note the docstring warning at `:12-16` that the fallback name historically
held a v1 *username* in AlphaGEX.

**Internal (non-vendor) dependency:** `routes_helpers.py:90` fetches
`{ALPHAGEX_BASE_URL}/api/watchtower/gamma` for per-expiration GEX structure.
`ALPHAGEX_BASE_URL` defaults to `http://localhost:8000` (`routes_helpers.py:21`,
`routes.py:61`).

**Historical vs live:** options data is **live/current chains only**. The one
time-series call is equity daily OHLC (`tradier_client.py:64-89`). There is no
historical options endpoint in use anywhere.

**Rate limiting / retry / backoff: NONE FOUND.** `_tradier_get`
(`routes.py:91-101`) is a bare GET that raises `HTTPException(502)` on
non-200 — no retry, no backoff, no rate-limit accounting. Same for the other
two clients, which return `None`/`[]` on failure. **Caching** exists and is
DB-backed — see §2.4.

### 2.2 Greeks computation

**Three independent implementations. No shared module.**

**(a) Vendor pass-through** — `routes.py:744-748`, quoted above. Which Greeks:
`delta`, `gamma`, `theta`, `vega`, plus `iv`. No rho, no second-order Greeks.

**(b) Local Black-Scholes, backend** — `routes.py:1408-1427`, full body:

```python
def _bs_greeks(
    S: float, K: float, T: float, r: float, sigma: float, is_call: bool
) -> dict:
    if T <= 0 or sigma <= 0:
        intrinsic = max(0, S - K) if is_call else max(0, K - S)
        return {"delta": (1.0 if intrinsic > 0 else 0.0) * (1 if is_call else -1),
                "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    nd1 = _norm_pdf(d1)

    delta = _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1.0
    gamma = nd1 / (S * sigma * sqrtT)
    theta = (-(S * nd1 * sigma) / (2 * sqrtT)
             - r * K * math.exp(-r * T) * _norm_cdf(d2 if is_call else -d2)
             * (1 if is_call else -1)) / 365.0
    vega = S * nd1 * sqrtT / 100.0

    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}
```

- **Library: none.** Hand-rolled. `_norm_cdf` uses `math.erf`
  (`routes.py:1387-1388`); `_norm_pdf` at `:1391-1392`. No `py_vollib`, no
  `QuantLib`, no `mibian`, **no `scipy`** (absent from `requirements.txt`).
- **Model: Black-Scholes, European, no dividend yield term.** There is no
  `q`/dividend parameter anywhere in the signature or the math. Not Black-76;
  no binomial; no American exercise handling. Note SPX is traded
  (`routes_helpers.py:52-60`) — European is correct for SPX, questionable for
  SPY (American, and SPY pays dividends).
- Greeks produced: `delta`, `gamma`, `theta`, `vega`. **No rho, no vanna, no
  volga, no charm.** Confirmed by grep: `vanna|volga|charm` returns zero hits
  across `spreadworks/**/*.py`.
- Companion pricer `_bs_price` at `routes.py:1395-1405`.
- Called from `/calculate` at `routes.py:1893-1896`, `1940-1943`, `1985+`;
  results embedded per leg at `routes.py:1913-1916` and `1959-1962` under a
  `"greeks"` key.

**(c) Local Black-Scholes, frontend** —
`spreadworks/frontend/src/utils/blackScholes.js`. Prices only
(`bsCallPrice:20`, `bsPutPrice:27`); **no Greeks**. Uses an
Abramowitz-Stegun `normCdf` polynomial approximation (`:6-18`), not `erf` —
so it does not numerically match the backend. Purpose per docstring (`:1-4`):
"instant DTE slider interpolation… approximate payoff recalculation".

**Risk-free rate:** `routes.py:62`

```python
RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.05"))
```

Configurable by env, default 5%, **not fetched** from any curve. Read into
local `r` at `routes.py:974`. Note `RISK_FREE_RATE` is **not** declared in
`render.yaml` or `.env.example`, so production runs on the hardcoded 0.05
default. The frontend has its own independent default: `r = 0.05` as a
function parameter at `blackScholes.js:40`.

**Dividend yield: NOT MODELLED ANYWHERE.** Grep for `dividend|div_yield`
across `spreadworks/backend/*.py` returns nothing.

**Implied volatility: vendor-supplied. Never inverted locally.** No solver
exists — grep found no Newton/bisection/Brent IV routine. Resolution ladder at
`routes_helpers.py:230-268`, keys tried in order:

```python
def _read(o: dict | None) -> float:
    if not o: return 0.0
    g = o.get("greeks") or {}
    for k in ("mid_iv", "smv_vol", "ask_iv", "bid_iv"):
        v = g.get(k)
        if v: return float(v)
    return 0.0
```

Strike search walks outward from ATM ±5 strikes (`:245-251`), call then put
(`:266`), returning `0.0` if nothing found (`:268`). `/chain` uses a narrower
two-key version: `greeks.get("mid_iv") or greeks.get("smv_vol")`
(`routes.py:744`).

### 2.3 Data model for chains and expiries

**No chain or smile abstraction. Plain dicts throughout.**

- `LiveTradierChainProvider.get_chain()` (`routes_helpers.py:37-80`) returns an
  untyped `dict | None` with keys `spot`, `vix`, `atm_straddle_mid`, `iv_atm`,
  `expiration`, `ticker`, `options`, `gex`. `options` is a **flat list** of
  `{strike, type, bid, ask}` — not grouped by expiry, no per-expiry smile
  object.
- `/chain` (`routes.py:755-760`) returns a different shape:
  `{symbol, expiration, strikes, options}` where `options` is
  `dict[strike][option_type] -> entry`.
- `tradier_client.get_chain_contracts()` returns a third shape:
  `list[dict[str, Any]]` (`tradier_client.py:118`).
- **Pydantic models exist only for REQUEST bodies**, never for chains or
  responses: `CalcRequest` (`routes.py:1812`), `AlertCreate` (`:2161`),
  `PositionCreate` (`:2331`), `PositionUpdate` (`:2352`),
  `PositionCloseBody` (`:2358`), `DiscordPushSpread` (`:3003`),
  `ConfigUpdate` (`routes_bots.py:210`), `AdjustBody` (`:292`).
- **UNKNOWN:** whether any dataclass/TypedDict chain model exists in
  `spreadworks/backend/bots/tsunami/models.py` — file was listed but not read
  in full (see §5).

**Expiry keying and time-to-expiry:** expiries are **plain `YYYY-MM-DD`
strings** (`routes_helpers.py:40`, `tradier_client.py:92-112`,
`models.py:64` `expiration = Column(String(12))`).

TTE is **calendar days / 365**, computed in at least five places:

```python
# routes.py:1443-1445
def _tte(d: str) -> float:
    exp = datetime.strptime(d, "%Y-%m-%d").date()
    return max((exp - today_date).days, 0) / 365.0
```

Also `routes.py:1848`, `:2624`, `:1669`, and theta divided by `365.0` at
`:1424`. Floors of `1/365.0` at `:1452`, `:1493`, `:1500`. TSUNAMI has
`_DEFAULT_DTE_YEARS = 7.0 / 365.0` at `tradier_snapshot.py:37` and
`engine.py:37`. Frontend uses `dte / 365` (`blackScholes.js:47-48`).

**No market-calendar dependency.** `requirements.txt` has no
`pandas_market_calendars` / `exchange_calendars`. The only trading-day logic is
a local `_is_trading_day()` helper at `spreadworks/backend/__init__.py:219`,
used for Discord scheduling — **not** in any pricing path.

### 2.4 Persistence

**Postgres via SQLAlchemy 2.x**, shared with AlphaGEX
(`render.yaml:65-68` binds `DATABASE_URL` from database `alphagex-db`;
`requirements.txt:5-6` = `sqlalchemy>=2.0.0`, `psycopg2-binary>=2.9.0`).

Tables in `spreadworks/backend/models.py`:

| Model | Table | Line | Nature |
|---|---|---|---|
| `QuoteCache` | `quote_cache` | `:17` | latest-only, PK `symbol` (`:21`) |
| `CandleCache` | `candle_cache` | `:29` | JSON blob `candles_json` (`:36`) |
| `GexCache` | `gex_cache` | `:43` | latest-only, PK `symbol` (`:47`) |
| `ChainCache` | `chain_cache` | `:58` | JSON blob `chain_json` (`:65`) |
| `GexSnapshot` | `gex_snapshots` | `:71` | append-only history |

**`chain_cache` is an overwrite cache, not a history.** `routes.py:201-216`:

```python
stmt = insert(ChainCache).values(
    symbol=symbol, expiration=expiration,
    chain_json=json.dumps(chain_data),
    fetched_at=datetime.now(timezone.utc),
).on_conflict_do_update(
    index_elements=["symbol", "expiration"],
    set_=dict(chain_json=..., fetched_at=...),
)
```

Every fetch replaces the prior row for that `(symbol, expiration)`. **No
option chain, IV, or Greek is retained historically.** `GexSnapshot`
(`models.py:71`) is the only append-only table, and it stores aggregate GEX
levels, not a surface.

Cache TTLs are constants at `routes.py:69-80` (GEX 15 min open / 20 h closed;
candles 10 min / 20 h; `GEX_SPOT_DRIFT_THRESHOLD = 0.02`). Reads at
`routes.py:296` (`_read_cached_chain`), fallback path `routes.py:769-770`.

**Migrations: NONE.** No Alembic, no migration directory —
`git ls-tree` over `spreadworks/` matched nothing for `alembic|migration`.
Table creation is via `Base.metadata.create_all` (see `spreadworks/backend/db.py`
— **UNKNOWN**, not read; see §5). Adding a vol-surface table means either
hand-rolled DDL or introducing Alembic to the monorepo.

### 2.5 API surface and frontend coupling

**Endpoints that return Greeks:**

| Route | Line | Greeks source |
|---|---|---|
| `GET /api/spreadworks/chain` | `routes.py:714` | vendor pass-through (`:744-748`) |
| `POST /api/spreadworks/calculate` | `routes.py:1823` | local `_bs_greeks` (`:1893-1896`, `1940-1943`) |
| `GET /api/spreadworks/bots/{bot}/positions/{id}/payoff` | `routes_bots.py:417` | **UNKNOWN** — not read |
| `GET /api/spreadworks/positions/{id}/payoff` | `routes.py:4089` | **UNKNOWN** — not read |

Routers: `routes.py:56` prefix `/api/spreadworks`; `routes_bots.py:21` prefix
`/api/spreadworks/bots`; `routes_tsunami.py:42` prefix `/api/tsunami`.

**Response models: none.** Grep for `response_model` across
`spreadworks/backend/*.py` returned **zero hits**. All endpoints return raw
dicts.

**Frontend consumption** — plain `fetch`, no client library, no generated types:

- `/chain`: `spreadworks/frontend/src/components/StrategyPanel.jsx:703`
- `/expirations`: `StrategyPanel.jsx:685`
- `/gex-suggest`: `StrategyPanel.jsx:768`
- `/positions/{id}/pnl`: `PositionTracker.jsx:24`, `positions/PositionCard.jsx:23`
- `/alerts`: `App.jsx:665`, `AlertPanel.jsx:16,33`
- `/bots`: `App.jsx:82`

Greek rendering:
- `MetricsBar.jsx:147-150` reads `g.delta`, `g.gamma`, `g.theta`, `g.vega`.
- `LegBreakdown.jsx:38-40` reads `leg.iv`, `greeks.delta`, `greeks.theta`.
- `StrategyPanel.jsx:75` reads `opt?.delta`.

**If you add new fields to a Greeks response, what breaks? Nothing.**
- Backend: no `response_model`, so no field filtering or validation error.
- Frontend: **no TypeScript** — `git ls-tree` found no `.ts`/`.tsx` under
  `spreadworks/frontend/src/`. Components destructure named keys and use
  optional chaining / null guards (`g.theta != null ? … : '--'` at
  `MetricsBar.jsx:149`), so unknown extra keys are ignored.
- **Caveat:** `chain_cache` stores a serialised blob (`routes.py:206`). Rows
  written before a schema change will lack new keys, and
  `_read_cached_chain` (`routes.py:296`) has no version field — stale rows
  will silently return `None` for new Greeks until overwritten.

### 2.6 Testing

- **Framework:** pytest. `spreadworks/pytest.ini:1-6` — `testpaths = tests`,
  `asyncio_mode = auto`. Deps: `pytest>=8.0`, `pytest-asyncio>=0.23`,
  `freezegun>=1.4` (`requirements.txt:13-15`).
- **Location:** `spreadworks/tests/`, plus `spreadworks/tests/tsunami/`
  (gates, broker, audit, strike_mapping, integration).
- **Tests for numerical/pricing code:** there are **no tests for
  `_bs_greeks` or `_bs_price`**. Grep for those symbols in
  `spreadworks/tests/` returned nothing. Existing numeric tests target
  *strategy construction* arithmetic (debit, max_profit, max_loss, PT/SL
  targets), e.g. `tests/test_long_butterfly.py:98-114`,
  `tests/test_iron_condor.py:115-116`, `tests/test_iron_butterfly.py:176-177`.
- **IV path is tested:** `tests/test_atm_iv_fallback.py` exercises the
  `_atm_iv` ladder.
- **Float comparison:** mostly `pytest.approx` with default tolerance
  (`test_long_butterfly.py:98`, `test_iron_condor.py:115`,
  `test_pin_drift_combo.py:46-49`). One hand-rolled absolute tolerance:
  `tests/test_executor.py:83` — `assert abs(mtm_pnl - expected) < 0.01`. No
  custom tolerance helper, no explicit `rel=`/`abs=` arguments found.
- **Fixtures are real captured market data:** `tests/fixtures/` contains
  `spy_0dte_chain.json`, `spy_1dte_chain.json`, `spy_6dte_chain.json`,
  `spy_9dte_chain.json`, `spy_14dte_chain.json`. Whether these include the
  Tradier `greeks` sub-object is **UNKNOWN** — file contents not read.
- Per `routes_helpers.py:3-4`: "Tests use a FakeChainProvider injected
  directly, never this module."

### 2.7 Deployment

`spreadworks/render.yaml` — three services:

| Service | Runtime | Build / start |
|---|---|---|
| `spreadworks-frontend` (`:14`) | static | `:18` build, publish `spreadworks/frontend/dist` (`:19`) |
| `spreadworks-backend` (`:39`) | python, starter, oregon (`:40-42`) | build `:45`, start `:46` `uvicorn backend.main:app` |
| `spreadworks-bot` (`:72`) | node worker | `:78-79` |

**⚠ render.yaml is explicitly NOT the source of truth for the live backend.**
`render.yaml:5-9`:

> "spreadworks-backend (srv-d6mv30f5gffc73bog9a0) was created from this
> blueprint then its live Build Command drifted in the dashboard. As of
> 2026-05-18 the live command is pip-only and does NOT match the SERVICE 2
> buildCommand below. Source of truth for the LIVE service is the dashboard,
> not this file."

**Python version pinned to 3.11.0** (`render.yaml:51-52`).
**Node version: UNKNOWN** — no `engines` field checked in
`spreadworks/frontend/package.json` (not read).

**Env vars the app expects, by name:**
`TZ` (`:49`, `America/Chicago`), `PYTHON_VERSION` (`:51`), `TRADIER_TOKEN`
(`:53`), `TRADIER_ACCOUNT_ID` (`:55`), `ALPHAGEX_BASE_URL` (`:57`),
`FRONTEND_URL` (`:59`), `ANTHROPIC_API_KEY` (`:61`), `DISCORD_WEBHOOK_URL`
(`:63`), `DATABASE_URL` (`:65`), `VITE_API_URL` (`:29`, `:89`),
`DISCORD_TOKEN` (`:81`), `DISCORD_CLIENT_ID` (`:83`), `DISCORD_GUILD_ID`
(`:85`).

Referenced in code but **absent from render.yaml** — will fall back to
defaults in production: `RISK_FREE_RATE` (`routes.py:62`),
`TRADIER_API_KEY` (`tradier_client.py:31`),
`TRADING_VOLATILITY_API_TOKEN` / `TRADING_VOLATILITY_API_KEY`
(`tv_client.py:41-42`), `TRADING_VOLATILITY_V2_BASE_URL` (`tv_client.py:33`).

**Constraints on adding `scipy` / `py_vollib`:** `requirements.txt` already
has `numpy>=1.26` (`:10`) and `matplotlib>=3.8.0` (`:11`), so a compiled
scientific stack is already being built on Render's `starter` plan. **No
version ceilings** are declared anywhere — every pin is `>=`. Python 3.11
supports current `scipy` and `py_vollib`. No blocker found; note only that
`render.yaml:45` and the *actual live* build command differ, so a dependency
added to `requirements.txt` will be picked up only if the live pip-only
command installs from it.

### 2.8 Tech debt in the numerical path

See the register in §3.

---

## 3. Tech debt register

| Issue | Location | Severity | Why it matters |
|---|---|---|---|
| Production scanner chain provider discards the entire `greeks` block | `backend/bots/routes_helpers.py:70-74` | **Critical** | Tradier is billed/queried with `greeks=true` (`:45`) and the result is thrown away. Any new Greek must widen this normaliser or the scanner will never see it. |
| TSUNAMI normaliser keeps `gamma` only | `backend/bots/tsunami/data/tradier_client.py:143-151` | **Critical** | Same problem, second code path. Vanna/volga/charm work would need changes in three places. |
| Three unshared pricing implementations | `backend/routes.py:1395-1427`; `frontend/src/utils/blackScholes.js:20-32`; vendor pass-through `routes.py:744-748` | **High** | Backend uses `math.erf`, frontend uses an Abramowitz-Stegun polynomial — they do not agree numerically. Adding a Greek means implementing it up to 3× or unifying first. |
| No tests whatsoever for `_bs_greeks` / `_bs_price` | `backend/routes.py:1395`, `:1408`; searched all of `spreadworks/tests/` | **High** | The only pricing math in the repo is unverified. There is no regression net for a skew-aware refactor. |
| Dividend yield not modelled | `_bs_greeks` signature `routes.py:1408-1410` (no `q` term) | **High** | SPY pays dividends; omitting `q` biases delta and every derived Greek. Matters more for vanna/charm than for price. |
| `RISK_FREE_RATE` hardcoded default, not deployed | `routes.py:62`; absent from `render.yaml` env list | Medium | Production silently runs at 5% regardless of the actual curve. Frontend independently defaults to `r = 0.05` (`blackScholes.js:40`). |
| Calendar-day `/365` day count, duplicated ≥5× | `routes.py:1424`, `:1443-1445`, `:1848`, `:2624`, `:1669`; `blackScholes.js:47-48`; `tradier_snapshot.py:37`; `engine.py:37` | Medium | No trading-day convention and no market calendar. 0DTE and holiday-adjacent expiries are mispriced, and charm (∂delta/∂t) is highly sensitive to the convention. |
| `T <= 0 or sigma <= 0` collapses to intrinsic with delta forced to ±1/0 | `routes.py:1411-1414` | Medium | Handled, but crudely — gamma/theta/vega return exactly `0.0`. A skew-adjusted delta needs a defined behaviour here rather than a hard branch. |
| Division by `sigma * sqrtT` with no guard beyond the `<= 0` branch | `routes.py:1416` (d1), `:1421` (gamma), `:1422` (theta) | Medium | A very small non-zero `sigma` (a real occurrence in deep-OTM vendor IV) yields `d1 → ±inf` and `gamma → inf` rather than raising. |
| `_atm_iv` returns `0.0` on total failure | `backend/bots/routes_helpers.py:268` | Medium | A sentinel `0.0` IV flows into `sigma`, which then hits the `sigma <= 0` branch and silently zeroes all Greeks. Docstring at `:233-236` confirms this previously blocked entries for hours. |
| Mid computed without checking both sides | `routes.py:740` — `round((o.get("bid", 0) + o.get("ask", 0)) / 2, 4) if o.get("bid") is not None` | Medium | Guards `bid` but not `ask`; a present bid with `ask=None` raises `TypeError`. Zero-bid contracts produce a mid of `ask/2`. |
| `atm_straddle_mid` returns `0.0` when either leg missing | `routes_helpers.py:225` | Low | Sentinel zero rather than `None`; indistinguishable from a genuinely free straddle downstream. |
| Silent exception swallowing, pervasive | 43 `except Exception` in `routes.py` alone; 23 in `backend/__init__.py`; bare `except Exception: pass` at `routes.py:133-134`; `routes.py:723-724` swallows the entire chain fetch | **High** | A pricing or normalisation bug surfaces as empty/zero data, not an error. `routes.py:723` in particular hides every `/chain` upstream failure. |
| No retry / backoff / rate-limit handling on any vendor call | `routes.py:91-101`; `routes_helpers.py:43`; `tradier_client.py:46,71,96,128` | Medium | A vol-surface backfill would hammer Tradier with no throttle and no 429 handling. |
| `chain_cache` overwrites in place; blob has no schema version | `models.py:58-66`; `routes.py:201-216` | **High** for this project | There is no historical options store to build on, and cached blobs written pre-change silently lack new Greek keys. |
| No migration tooling | searched `spreadworks/` for `alembic|migration` — none | **High** for this project | A vol-surface table needs schema management that does not currently exist in this subtree. |
| `render.yaml` does not match the live service | `render.yaml:5-9` (self-documented) | Medium | Dependency or build changes verified against `render.yaml` may not reflect production. |

---

## 4. Security findings

**No credential values were found committed to source control.**

- `spreadworks/.env.example` contains **placeholder assignments only** — the
  variable names are listed in §2.7. Values were not printed and were not
  real.
- `render.yaml` uses `sync: false` for every secret (`:33`, `:54`, `:56`,
  `:58`, `:60`, `:62`, `:64`, `:82`, `:84`, `:86`, `:88`, `:90`), meaning
  values live in the Render dashboard, not the repo.
- All tokens are read from `os.getenv` / `os.environ` at runtime
  (`routes.py:62`, `routes_helpers.py:18`, `tradier_client.py:28-32`,
  `tv_client.py:33,41-42`).
- `.env.example:4-13` documents a correct rotation runbook and confirms
  `.env` / `.env.local` are gitignored.

**One informational note, not a leak:** `tv_client.py:11-16` records in a
docstring which env var a credential "lives under in this environment" and
attributes it to a named person and date. That is a naming hint, not a secret,
but it is the kind of operational detail worth keeping out of source.

**Not verified:** whether a real `.env` exists untracked in the working tree,
and whether git *history* contains a previously committed secret. Neither was
checked — see §5.

---

## 5. UNKNOWNS

| Unknown | Paths / refs searched |
|---|---|
| Whether `backend/bots/tsunami/models.py` defines a typed chain/smile/contract model | file listed via `git ls-tree origin/main -- spreadworks/`; **contents not read** |
| How DB tables are actually created (`create_all` vs raw DDL) | `spreadworks/backend/db.py` — listed, **not read** |
| Greeks source for the two payoff endpoints | `routes.py:4089`, `routes_bots.py:417` — decorators found, **bodies not read** |
| Whether `tests/fixtures/spy_*dte_chain.json` include Tradier's `greeks` sub-object | files listed; **contents not read** |
| Node version / `engines` constraint | `spreadworks/frontend/package.json` — **not read** |
| Whether `scipy`/`py_vollib` are already present transitively | only `spreadworks/requirements.txt` read; no lockfile exists for Python; `frontend/package-lock.json` not relevant |
| Exact Tradier rate limits and whether any are being hit | no limits documented in code; no logs or metrics inspected (out of scope — no runtime) |
| Whether an untracked real `.env` exists, and whether git history ever contained a secret | only `origin/main:spreadworks/.env.example` read; **no history scan, no working-tree `.env` inspection** |
| Whether `RISK_FREE_RATE` is set in the Render dashboard | `render.yaml` read; dashboard not accessible from static analysis |
| The live backend build command | `render.yaml:5-9` states it differs; dashboard not inspected |
| Whether `/api/watchtower/gamma` (AlphaGEX side) exposes per-strike Greeks usable for a surface | `routes_helpers.py:82-100` read (consumer side only); **AlphaGEX provider not traced** |

---

## 6. Repo map

Source directories only, depth 3, excluding `node_modules`, `.venv`, `dist`,
`build`, `__pycache__`, `.pytest_cache`.

```
spreadworks
├── backend
│   └── bots
│       ├── strategies
│       └── tsunami
│           ├── audit  broker  configs  data  gates
│           ├── kill_switch  management  monitoring
│           ├── sizing  strike_mapping
├── bot
│   └── src
├── frontend
│   ├── public
│   └── src
│       ├── components
│       │   ├── bots
│       │   └── positions
│       ├── pages
│       └── utils
├── scripts
└── tests
    ├── fixtures
    └── tsunami
        ├── audit  broker  gates  integration  strike_mapping
```

Top-level files: `.env.example`, `pytest.ini`, `README.md`, `render.yaml`,
`requirements.txt`.
