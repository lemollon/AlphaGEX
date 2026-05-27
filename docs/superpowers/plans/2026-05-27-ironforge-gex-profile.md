# IronForge GEX Profile Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Trading-Volatility-style GEX profile page to IronForge, defaulting to SPY 0DTE, reusing AlphaGEX's existing `/api/watchtower/gex-analysis` over HTTP, plus new backend metrics (positioning pressure, structure balance) and a full-board all-expirations aggregate.

**Architecture:** Backend extends AlphaGEX (Python/FastAPI) with a focused pure-function module `core/gex_profile_metrics.py` and a new lazy `/gex-analysis/all` route. IronForge (Next.js 14) adds read-only proxy routes to AlphaGEX, a themed `/gex` page, and split components. The fast single-expiration view renders immediately; the expensive full-board aggregate loads lazily into the right-hand chart.

**Tech Stack:** Python 3.11, FastAPI, pytest (backend); Next.js 14 App Router, React 18, TypeScript, recharts, Tailwind (forge theme), vitest (IronForge). No lucide-react in IronForge — use inline SVG / text.

---

## Reference facts (verified against the codebase)

- **Endpoint reused:** `GET /api/watchtower/gex-analysis?symbol=&expiration=` → `backend/api/routes/watchtower_routes.py:2440`. Response shape: `data.header`, `data.levels` (`price, upper_1sd, lower_1sd, gex_flip, call_wall, put_wall, expected_move`), `data.gex_chart.strikes[]`, `data.flow_diagnostics.cards[]`, `data.skew_measures`, `data.rating` (`rating, confidence, bullish_score, bearish_score, net_score`), `data.summary` (`net_gex, put_call_ratio, total_*`).
- **Strike shape** (`data.gex_chart.strikes[i]`): `strike, net_gamma, call_gamma, put_gamma, call_volume, put_volume, total_volume, call_iv, put_iv, call_oi, put_oi, is_magnet, magnet_rank, is_pin, is_danger, danger_type`.
- **Volume pressure** (`= call-vs-put pressure`, −1..+1) is `data.flow_diagnostics.cards[id=='volume_pressure'].raw_value`. **Net GEX** is `data.summary.net_gex`. **Skew ratio** is `data.skew_measures.skew_ratio`.
- **Engine internals:** `engine.process_options_chain(raw_data, spot_price, vix, expiration)` → `GammaSnapshot` with `.strikes: List[StrikeData]`, `.spot_price`, `.expected_move`, `.total_net_gamma`. `StrikeData` has `.strike`, `.net_gamma`. `fetch_gamma_data(symbol, expiration)` (async) → raw dict with `spot_price`, `vix`, `strikes`, and `data_unavailable` flag.
- **Expirations:** `TradierDataFetcher(api_key, sandbox=False).get_option_expirations(symbol)` → `List['YYYY-MM-DD']`. Pattern used in `watchtower_routes.py:5422-5425`.
- **Cache helpers:** `get_cached(key, ttl_seconds)` / `set_cached(key, value)` already exist in `watchtower_routes.py` (used by `fetch_gamma_data`).
- **IronForge AlphaGEX base:** `process.env.ALPHAGEX_API_BASE || 'https://alphagex-api.onrender.com'` (see `ironforge/webapp/src/lib/blaze/gex-client.ts:7`). Reuse this exact env name. No new env var required.
- **IronForge Nav:** static `links` array in `ironforge/webapp/src/components/Nav.tsx:28`.
- **IronForge theme:** `forge-bg`, `forge-card`, `fire-divider` in `ironforge/webapp/src/app/globals.css`. Pages are `'use client'`, App Router.

---

## File Structure

**AlphaGEX backend (Python)**
- Create: `core/gex_profile_metrics.py` — pure functions: `calculate_positioning_pressure`, `calculate_structure_balance`, `aggregate_net_gamma_by_strike`. One responsibility: derived GEX-profile metrics. No FastAPI/Tradier imports.
- Create: `tests/test_gex_profile_metrics.py` — unit tests for the three pure functions.
- Modify: `backend/api/routes/watchtower_routes.py` — (a) add `positioning` block to `get_gex_analysis` response; (b) add new route `GET /api/watchtower/gex-analysis/all`.

**IronForge webapp (Next.js/TS)**
- Create: `ironforge/webapp/src/lib/gex/proxy.ts` — shared upstream fetch helper (timeout + 1 retry).
- Create: `ironforge/webapp/src/lib/gex/types.ts` — TS types for the analysis payloads.
- Create: `ironforge/webapp/src/lib/gex/derive.ts` — pure helpers: `topStrikesByGamma`, `buildReactionFramework`.
- Create: `ironforge/webapp/src/lib/gex/derive.test.ts` — vitest unit tests for `derive.ts`.
- Create: `ironforge/webapp/src/app/api/gex/analysis/route.ts`
- Create: `ironforge/webapp/src/app/api/gex/analysis-all/route.ts`
- Create: `ironforge/webapp/src/components/gex/HeaderMetrics.tsx`
- Create: `ironforge/webapp/src/components/gex/KeyGammaLevels.tsx`
- Create: `ironforge/webapp/src/components/gex/NetGexChart.tsx`
- Create: `ironforge/webapp/src/components/gex/ReactionFramework.tsx`
- Create: `ironforge/webapp/src/components/gex/PositioningRegime.tsx`
- Create: `ironforge/webapp/src/components/gex/StructureBalance.tsx`
- Create: `ironforge/webapp/src/components/gex/FlowDiagnostics.tsx`
- Create: `ironforge/webapp/src/components/gex/SkewMeasures.tsx`
- Create: `ironforge/webapp/src/app/gex/page.tsx`
- Modify: `ironforge/webapp/src/components/Nav.tsx` — add GEX Profile link.

---

## PHASE A — AlphaGEX backend

### Task 1: `calculate_positioning_pressure` (pure function + test)

**Files:**
- Create: `core/gex_profile_metrics.py`
- Test: `tests/test_gex_profile_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gex_profile_metrics.py
from core.gex_profile_metrics import calculate_positioning_pressure


def test_positioning_pressure_neutral_when_all_zero():
    out = calculate_positioning_pressure(
        volume_pressure=0.0, net_gex=0.0, skew_ratio=1.0, net_score=0
    )
    assert out["regime_label"] == "Neutral"
    assert out["pressure_score"] == 0
    assert out["call_vs_put_pressure"] == 0.0


def test_positioning_pressure_bullish_and_bounded():
    out = calculate_positioning_pressure(
        volume_pressure=0.5, net_gex=5e9, skew_ratio=1.4, net_score=3
    )
    assert out["regime_label"] == "Bullish"
    assert 0 <= out["pressure_score"] <= 100
    assert out["pressure_score"] > 0


def test_positioning_pressure_bearish_sign_from_net_score():
    out = calculate_positioning_pressure(
        volume_pressure=-0.4, net_gex=-2e9, skew_ratio=0.8, net_score=-2
    )
    assert out["regime_label"] == "Bearish"


def test_positioning_pressure_score_caps_at_100():
    out = calculate_positioning_pressure(
        volume_pressure=1.0, net_gex=1e12, skew_ratio=5.0, net_score=10
    )
    assert out["pressure_score"] == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gex_profile_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.gex_profile_metrics'`

- [ ] **Step 3: Write minimal implementation**

```python
# core/gex_profile_metrics.py
"""
GEX Profile derived metrics (Trading-Volatility-style).

Pure functions — no FastAPI, no Tradier, no engine state — so they are
trivially unit-testable. Consumed by backend/api/routes/watchtower_routes.py.

NOTE: positioning pressure and structure balance are OUR transparent
approximations of TradingVolatility's proprietary scores, not 1:1 copies.
"""
from typing import Dict, List

# Scale at which |net_gex| is treated as a "full" 1.0 contribution.
# SPY net GEX commonly runs in the low billions; ~6e9 maps a strong day to ~1.0.
NET_GEX_SCALE = 6e9


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calculate_positioning_pressure(
    volume_pressure: float,
    net_gex: float,
    skew_ratio: float,
    net_score: int,
) -> Dict:
    """
    Positioning regime intensity, 0..100, plus a Bullish/Neutral/Bearish label.

    pressure_score = 100 * clamp(
        0.5*|volume_pressure| + 0.3*|net_gex_norm| + 0.2*|skew_norm|, 0, 1)
      where net_gex_norm = clamp(net_gex / NET_GEX_SCALE, -1, 1)
            skew_norm    = clamp(skew_ratio - 1.0, -1, 1)   # 1.0 == symmetric
    Label comes from the sign of net_score (the flow rating's net score).
    """
    net_gex_norm = _clamp(net_gex / NET_GEX_SCALE, -1.0, 1.0)
    skew_norm = _clamp(skew_ratio - 1.0, -1.0, 1.0)
    intensity = (
        0.5 * abs(volume_pressure)
        + 0.3 * abs(net_gex_norm)
        + 0.2 * abs(skew_norm)
    )
    pressure_score = int(round(100 * _clamp(intensity, 0.0, 1.0)))

    if net_score > 0:
        regime_label = "Bullish"
    elif net_score < 0:
        regime_label = "Bearish"
    else:
        regime_label = "Neutral"

    return {
        "regime_label": regime_label,
        "pressure_score": pressure_score,
        "call_vs_put_pressure": round(volume_pressure, 3),
        "summary": (
            f"{regime_label} • pressure {pressure_score}/100 "
            f"(call-vs-put {volume_pressure:+.3f})"
        ),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gex_profile_metrics.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add core/gex_profile_metrics.py tests/test_gex_profile_metrics.py
git commit -m "feat(gex): add positioning-pressure metric (pure fn + tests)"
```

---

### Task 2: `calculate_structure_balance` (pure function + test)

**Files:**
- Modify: `core/gex_profile_metrics.py`
- Test: `tests/test_gex_profile_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gex_profile_metrics.py
from core.gex_profile_metrics import calculate_structure_balance


def test_structure_balance_balanced_when_symmetric():
    # equal gamma above and below spot within band -> ~0
    strikes = [
        {"strike": 95.0, "net_gamma": -10.0},
        {"strike": 105.0, "net_gamma": 10.0},
    ]
    out = calculate_structure_balance(strikes, spot_price=100.0, expected_move=10.0)
    assert out["label"] == "Balanced"
    assert abs(out["balance"]) < 0.15
    assert out["horizon_days"] == 7


def test_structure_balance_resistance_heavy():
    strikes = [
        {"strike": 95.0, "net_gamma": -1.0},
        {"strike": 105.0, "net_gamma": 30.0},
    ]
    out = calculate_structure_balance(strikes, spot_price=100.0, expected_move=10.0)
    assert out["balance"] > 0.15
    assert out["label"] == "Resistance-heavy"


def test_structure_balance_support_heavy():
    strikes = [
        {"strike": 95.0, "net_gamma": -30.0},
        {"strike": 105.0, "net_gamma": 1.0},
    ]
    out = calculate_structure_balance(strikes, spot_price=100.0, expected_move=10.0)
    assert out["balance"] < -0.15
    assert out["label"] == "Support-heavy"


def test_structure_balance_empty_is_balanced_zero():
    out = calculate_structure_balance([], spot_price=100.0, expected_move=10.0)
    assert out["balance"] == 0.0
    assert out["label"] == "Balanced"


def test_structure_balance_ignores_strikes_outside_band():
    # strike far above the +1sigma band is excluded
    strikes = [
        {"strike": 105.0, "net_gamma": 5.0},
        {"strike": 200.0, "net_gamma": 999.0},
        {"strike": 95.0, "net_gamma": -5.0},
    ]
    out = calculate_structure_balance(strikes, spot_price=100.0, expected_move=10.0)
    assert abs(out["balance"]) < 0.15  # the 200 strike is ignored
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gex_profile_metrics.py -v`
Expected: FAIL — `ImportError: cannot import name 'calculate_structure_balance'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/gex_profile_metrics.py
def calculate_structure_balance(
    strikes: List[Dict],
    spot_price: float,
    expected_move: float,
    horizon_days: int = 7,
) -> Dict:
    """
    Compare resistance gamma (above spot) vs support gamma (below spot) within
    the ±1σ expected-move band.

      resist  = Σ |net_gamma| for spot < strike <= spot + expected_move
      support = Σ |net_gamma| for spot - expected_move <= strike < spot
      balance = (resist - support) / (resist + support)   # -1..+1, ~0 balanced

    `strikes` is a list of dicts with at least 'strike' and 'net_gamma'.
    When expected_move <= 0, fall back to a ±2% band around spot.
    """
    band = expected_move if expected_move and expected_move > 0 else spot_price * 0.02
    upper = spot_price + band
    lower = spot_price - band

    resist = 0.0
    support = 0.0
    for s in strikes:
        strike = s.get("strike")
        ng = s.get("net_gamma", 0.0) or 0.0
        if strike is None:
            continue
        if spot_price < strike <= upper:
            resist += abs(ng)
        elif lower <= strike < spot_price:
            support += abs(ng)

    denom = resist + support
    balance = round((resist - support) / denom, 4) if denom > 0 else 0.0

    if balance > 0.15:
        label = "Resistance-heavy"
    elif balance < -0.15:
        label = "Support-heavy"
    else:
        label = "Balanced"

    return {
        "balance": balance,
        "label": label,
        "resist_gamma": round(resist, 4),
        "support_gamma": round(support, 4),
        "horizon_days": horizon_days,
        "summary": (
            f"{label} ({balance:+.3f}) — support and resistance gamma "
            f"within the {horizon_days}-day expected range."
        ),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gex_profile_metrics.py -v`
Expected: PASS (9 passed total)

- [ ] **Step 5: Commit**

```bash
git add core/gex_profile_metrics.py tests/test_gex_profile_metrics.py
git commit -m "feat(gex): add structure-balance metric (pure fn + tests)"
```

---

### Task 3: `aggregate_net_gamma_by_strike` (pure function + test)

**Files:**
- Modify: `core/gex_profile_metrics.py`
- Test: `tests/test_gex_profile_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gex_profile_metrics.py
from core.gex_profile_metrics import aggregate_net_gamma_by_strike


def test_aggregate_sums_net_gamma_across_expirations():
    exp_a = [{"strike": 100.0, "net_gamma": 5.0}, {"strike": 101.0, "net_gamma": -2.0}]
    exp_b = [{"strike": 100.0, "net_gamma": 3.0}, {"strike": 102.0, "net_gamma": 7.0}]
    out = aggregate_net_gamma_by_strike([exp_a, exp_b])
    by_strike = {row["strike"]: row["net_gamma"] for row in out}
    assert by_strike[100.0] == 8.0
    assert by_strike[101.0] == -2.0
    assert by_strike[102.0] == 7.0


def test_aggregate_sorted_by_strike():
    out = aggregate_net_gamma_by_strike([
        [{"strike": 102.0, "net_gamma": 1.0}, {"strike": 100.0, "net_gamma": 1.0}],
    ])
    assert [r["strike"] for r in out] == [100.0, 102.0]


def test_aggregate_empty_returns_empty():
    assert aggregate_net_gamma_by_strike([]) == []
    assert aggregate_net_gamma_by_strike([[]]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gex_profile_metrics.py -v`
Expected: FAIL — `ImportError: cannot import name 'aggregate_net_gamma_by_strike'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to core/gex_profile_metrics.py
def aggregate_net_gamma_by_strike(strike_lists: List[List[Dict]]) -> List[Dict]:
    """
    Sum net_gamma per strike across multiple expirations' strike lists.

    Returns a list of {'strike', 'net_gamma'} dicts sorted ascending by strike.
    """
    totals: Dict[float, float] = {}
    for strikes in strike_lists:
        for s in strikes:
            strike = s.get("strike")
            if strike is None:
                continue
            totals[strike] = totals.get(strike, 0.0) + (s.get("net_gamma", 0.0) or 0.0)
    return [
        {"strike": k, "net_gamma": round(v, 4)}
        for k, v in sorted(totals.items())
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gex_profile_metrics.py -v`
Expected: PASS (12 passed total)

- [ ] **Step 5: Commit**

```bash
git add core/gex_profile_metrics.py tests/test_gex_profile_metrics.py
git commit -m "feat(gex): add net-gamma aggregation helper (pure fn + tests)"
```

---

### Task 4: Wire `positioning` block into `/gex-analysis` response

**Files:**
- Modify: `backend/api/routes/watchtower_routes.py` (the `get_gex_analysis` response builder around line 2586-2645)

- [ ] **Step 1: Add the import at the top of the route module**

Find the existing imports block near the top of `backend/api/routes/watchtower_routes.py` and add:

```python
from core.gex_profile_metrics import (
    calculate_positioning_pressure,
    calculate_structure_balance,
    aggregate_net_gamma_by_strike,
)
```

- [ ] **Step 2: Compute and insert the `positioning` block**

In `get_gex_analysis`, after `diagnostics = engine.calculate_options_flow_diagnostics(...)` (≈line 2522) and before building `response`, add:

```python
        # Positioning regime (our TV-style approximation)
        _vol_pressure = 0.0
        for _card in diagnostics.get('diagnostics', []):
            if _card.get('id') == 'volume_pressure':
                _vol_pressure = _card.get('raw_value', 0.0) or 0.0
                break
        positioning = calculate_positioning_pressure(
            volume_pressure=_vol_pressure,
            net_gex=diagnostics['summary'].get('net_gex', 0.0) or 0.0,
            skew_ratio=diagnostics['skew_measures'].get('skew_ratio', 1.0) or 1.0,
            net_score=diagnostics['rating'].get('net_score', 0) or 0,
        )
```

- [ ] **Step 3: Add `positioning` to the `response["data"]` dict**

In the `response = { ... "data": { ... } }` block, add a key alongside `"rating"`:

```python
                # Positioning regime (Trading-Volatility-style approximation)
                "positioning": positioning,
```

- [ ] **Step 4: Verify the route imports and the app starts**

Run: `python -c "import backend.api.routes.watchtower_routes"`
Expected: no ImportError (exit 0). If the module has heavy import side-effects, instead run `pytest tests/test_gex_profile_metrics.py -v` (already green) and rely on Task 9's manual check.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/watchtower_routes.py
git commit -m "feat(gex): add positioning block to /gex-analysis response"
```

---

### Task 5: New `GET /api/watchtower/gex-analysis/all` route (full board)

**Files:**
- Modify: `backend/api/routes/watchtower_routes.py` (add a new route; place it directly after `get_gex_analysis`, before `get_gamma_history` at ≈line 2676)

- [ ] **Step 1: Add the route**

```python
@router.get("/gex-analysis/all")
async def get_gex_analysis_all(
    symbol: str = Query("SPY", description="Symbol (SPY, SPX, QQQ, ...)"),
):
    """
    Full-board GEX aggregate: net gamma summed per strike across ALL listed
    expirations for the symbol, plus a 7-day-horizon structure-balance score.

    Lazy/expensive (one Tradier chain per expiration). Cached 120s per symbol.
    Tolerates per-expiration fetch failures (skips + reports them).
    """
    import asyncio
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

    cache_key = f"gex_all_{symbol.upper()}"
    cached = get_cached(cache_key, 120)
    if cached:
        return cached

    try:
        import os
        api_key = os.environ.get('TRADIER_API_KEY')
        if not (TRADIER_AVAILABLE and TradierDataFetcher and api_key):
            raise HTTPException(status_code=503, detail="Tradier not available")

        fetcher = TradierDataFetcher(api_key=api_key, sandbox=False)
        all_exps = fetcher.get_option_expirations(symbol.upper()) or []
        today = date.today()
        future_exps = []
        for e in all_exps:
            try:
                d = datetime.strptime(e, '%Y-%m-%d').date()
                if d >= today:
                    future_exps.append((e, (d - today).days))
            except ValueError:
                continue
        future_exps.sort(key=lambda x: x[1])

        if not future_exps:
            return {"success": False, "message": f"No expirations for {symbol}"}

        # Fetch all chains concurrently (fetch_gamma_data caches per-exp internally)
        exp_dates = [e for e, _ in future_exps]
        raw_results = await asyncio.gather(
            *[fetch_gamma_data(symbol, e) for e in exp_dates],
            return_exceptions=True,
        )

        per_exp_strikes = []          # for full-board aggregate
        seven_day_strikes = []        # for structure balance (DTE <= 7)
        included, failed = [], []
        spot_price, expected_move = 0.0, 0.0

        for (exp, dte), raw in zip(future_exps, raw_results):
            if isinstance(raw, Exception) or not raw or raw.get('data_unavailable'):
                failed.append(exp)
                continue
            sp = raw.get('spot_price', 0) or 0
            vix = raw.get('vix', 0) or 0
            if sp <= 0:
                failed.append(exp)
                continue
            snapshot = engine.process_options_chain(raw, sp, vix, exp)
            strikes = [{"strike": s.strike, "net_gamma": s.net_gamma} for s in snapshot.strikes]
            per_exp_strikes.append(strikes)
            included.append(exp)
            spot_price = sp
            expected_move = snapshot.expected_move or expected_move
            if dte <= 7:
                seven_day_strikes.extend(strikes)

        aggregated = aggregate_net_gamma_by_strike(per_exp_strikes)
        structure_balance = calculate_structure_balance(
            seven_day_strikes, spot_price, expected_move, horizon_days=7
        )
        total_net_gamma = round(sum(r["net_gamma"] for r in aggregated), 4)

        result = {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "timestamp": format_central_timestamp(),
                "spot_price": round(spot_price, 2),
                "gex_chart_all": {
                    "strikes": aggregated,
                    "expirations_included": included,
                    "expirations_failed": failed,
                    "total_net_gamma": total_net_gamma,
                },
                "structure_balance": structure_balance,
            },
        }
        set_cached(cache_key, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting full-board GEX for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 2: Confirm symbols/helpers are in scope**

Verify `date`, `datetime`, `TradierDataFetcher`, `TRADIER_AVAILABLE`, `get_cached`, `set_cached`, `fetch_gamma_data`, `get_engine`, `format_central_timestamp`, `logger` are already imported/defined in `watchtower_routes.py` (they are used by neighbouring routes — `get_symbol_expirations` at :5393 uses `TradierDataFetcher`/`date`/`datetime`; `fetch_gamma_data` at :913 uses `get_cached`/`set_cached`). No new imports beyond Task 4's.

- [ ] **Step 3: Verify module imports**

Run: `python -c "import backend.api.routes.watchtower_routes"`
Expected: exit 0, no ImportError.

- [ ] **Step 4: Manual smoke (optional, needs Tradier key + market data)**

Run (locally with backend running): `curl -s "http://localhost:8000/api/watchtower/gex-analysis/all?symbol=SPY" | python -m json.tool | head -40`
Expected: JSON with `data.gex_chart_all.strikes` (non-empty during/after a session) and `data.structure_balance`.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/watchtower_routes.py
git commit -m "feat(gex): add full-board /gex-analysis/all route (aggregate + structure balance)"
```

---

## PHASE B — IronForge proxy routes

### Task 6: Shared proxy helper

**Files:**
- Create: `ironforge/webapp/src/lib/gex/proxy.ts`

- [ ] **Step 1: Write the helper**

```typescript
// ironforge/webapp/src/lib/gex/proxy.ts
// Server-side proxy to the AlphaGEX backend for GEX data.
// Mirrors the fetch+retry pattern in src/lib/blaze/gex-client.ts.

const ALPHAGEX_BASE = process.env.ALPHAGEX_API_BASE || 'https://alphagex-api.onrender.com'

async function fetchOnce(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { signal: controller.signal, cache: 'no-store' })
  } finally {
    clearTimeout(timeout)
  }
}

/**
 * Proxy a GET to the AlphaGEX backend. Single retry with 1s backoff.
 * Returns a Next.js Response with the upstream JSON, or a 502 on failure.
 */
export async function proxyGet(path: string, timeoutMs = 20000): Promise<Response> {
  const url = `${ALPHAGEX_BASE.replace(/\/$/, '')}${path}`
  let resp: Response
  try {
    resp = await fetchOnce(url, timeoutMs)
  } catch {
    await new Promise((r) => setTimeout(r, 1000))
    try {
      resp = await fetchOnce(url, timeoutMs)
    } catch (err) {
      return Response.json(
        { success: false, error: `AlphaGEX proxy error: ${(err as Error).message}` },
        { status: 502 },
      )
    }
  }
  const text = await resp.text()
  return new Response(text, {
    status: resp.status,
    headers: { 'content-type': resp.headers.get('content-type') || 'application/json' },
  })
}
```

- [ ] **Step 2: Commit**

```bash
git add ironforge/webapp/src/lib/gex/proxy.ts
git commit -m "feat(gex): add IronForge AlphaGEX proxy helper"
```

---

### Task 7: Proxy routes (analysis, analysis-all)

> Scope: only the two proxies the SPY/0DTE page actually consumes. (See the YAGNI trim note in File Structure — `expirations`/`intraday` proxies are omitted.)

**Files:**
- Create: `ironforge/webapp/src/app/api/gex/analysis/route.ts`
- Create: `ironforge/webapp/src/app/api/gex/analysis-all/route.ts`

- [ ] **Step 1: `analysis/route.ts`**

```typescript
// ironforge/webapp/src/app/api/gex/analysis/route.ts
import { NextRequest } from 'next/server'
import { proxyGet } from '@/lib/gex/proxy'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams
  const symbol = sp.get('symbol') || 'SPY'
  const expiration = sp.get('expiration')
  const qs = new URLSearchParams({ symbol })
  if (expiration) qs.set('expiration', expiration)
  return proxyGet(`/api/watchtower/gex-analysis?${qs.toString()}`)
}
```

- [ ] **Step 2: `analysis-all/route.ts`**

```typescript
// ironforge/webapp/src/app/api/gex/analysis-all/route.ts
import { NextRequest } from 'next/server'
import { proxyGet } from '@/lib/gex/proxy'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get('symbol') || 'SPY'
  // Full board can be slow on a cold cache; allow a longer timeout.
  return proxyGet(`/api/watchtower/gex-analysis/all?symbol=${encodeURIComponent(symbol)}`, 60000)
}
```

- [ ] **Step 3: Commit**

```bash
git add ironforge/webapp/src/app/api/gex
git commit -m "feat(gex): add IronForge GEX proxy routes (analysis, analysis-all)"
```

---

## PHASE C — IronForge types, derive helpers, components, page

### Task 8: TS types

**Files:**
- Create: `ironforge/webapp/src/lib/gex/types.ts`

- [ ] **Step 1: Write the types** (ported from `frontend/src/app/gex-charts/GexChartsContent.tsx:43-180`, plus Phase-2 additions)

```typescript
// ironforge/webapp/src/lib/gex/types.ts
export interface StrikeGex {
  strike: number
  net_gamma: number
  call_gamma: number
  put_gamma: number
  call_volume: number
  put_volume: number
  total_volume: number
  call_iv: number | null
  put_iv: number | null
  call_oi: number
  put_oi: number
  is_magnet: boolean
  magnet_rank: number | null
  is_pin: boolean
  is_danger: boolean
  danger_type: string | null
}

export interface DiagnosticCard {
  id: string
  label: string
  metric_name: string
  metric_value: string
  description: string
  raw_value: number
}

export interface SkewMeasures {
  skew_ratio: number
  skew_ratio_description: string
  call_skew: number
  call_skew_description: string
  atm_call_iv: number | null
  atm_put_iv: number | null
  avg_otm_call_iv: number | null
  avg_otm_put_iv: number | null
}

export interface Positioning {
  regime_label: 'Bullish' | 'Neutral' | 'Bearish' | string
  pressure_score: number
  call_vs_put_pressure: number
  summary: string
}

export interface StructureBalance {
  balance: number
  label: string
  resist_gamma: number
  support_gamma: number
  horizon_days: number
  summary: string
}

export interface GexAnalysisData {
  symbol: string
  timestamp: string
  expiration: string
  header: {
    price: number
    gex_flip: number | null
    '30_day_vol': number | null
    call_structure: string
    gex_at_expiration: number
    net_gex: number
    rating: string
    gamma_form: string
    previous_regime: string | null
    regime_flipped: boolean
  }
  flow_diagnostics: { cards: DiagnosticCard[]; note: string }
  skew_measures: SkewMeasures
  rating: { rating: string; confidence: string; bullish_score: number; bearish_score: number; net_score: number }
  positioning?: Positioning
  levels: {
    price: number
    upper_1sd: number | null
    lower_1sd: number | null
    gex_flip: number | null
    call_wall: number | null
    put_wall: number | null
    expected_move: number | null
  }
  gex_chart: { expiration: string; strikes: StrikeGex[]; total_net_gamma: number; gamma_regime: string }
  summary: {
    total_call_volume: number
    total_put_volume: number
    total_volume: number
    total_call_oi: number
    total_put_oi: number
    put_call_ratio: number
    net_gex: number
  }
}

export interface GexAllData {
  symbol: string
  timestamp: string
  spot_price: number
  gex_chart_all: {
    strikes: { strike: number; net_gamma: number }[]
    expirations_included: string[]
    expirations_failed: string[]
    total_net_gamma: number
  }
  structure_balance: StructureBalance
}

export interface ExpirationInfo {
  date: string
  dte: number
  day: string
  category: string
  is_opex: boolean
  is_today: boolean
}

export interface SymbolExpirations {
  symbol: string
  expiration_type: string
  nearest: ExpirationInfo | null
  next_opex: string | null
  weekly: string[]
  all_expirations: ExpirationInfo[]
  total_available: number
}
```

- [ ] **Step 2: Commit**

```bash
git add ironforge/webapp/src/lib/gex/types.ts
git commit -m "feat(gex): add IronForge GEX TS types"
```

---

### Task 9: Derive helpers (`topStrikesByGamma`, `buildReactionFramework`) + tests

**Files:**
- Create: `ironforge/webapp/src/lib/gex/derive.ts`
- Test: `ironforge/webapp/src/lib/gex/derive.test.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
// ironforge/webapp/src/lib/gex/derive.test.ts
import { describe, it, expect } from 'vitest'
import { topStrikesByGamma, buildReactionFramework } from './derive'

describe('topStrikesByGamma', () => {
  const strikes = [
    { strike: 95, net_gamma: -30 },
    { strike: 97, net_gamma: -10 },
    { strike: 105, net_gamma: 20 },
    { strike: 110, net_gamma: 5 },
  ]
  it('returns top resistance strikes above price by |gamma|', () => {
    const { resistance } = topStrikesByGamma(strikes as any, 100, 2)
    expect(resistance.map((s) => s.strike)).toEqual([105, 110])
  })
  it('returns top support strikes below price by |gamma|', () => {
    const { support } = topStrikesByGamma(strikes as any, 100, 2)
    expect(support.map((s) => s.strike)).toEqual([95, 97])
  })
  it('handles empty input', () => {
    const out = topStrikesByGamma([], 100, 2)
    expect(out.resistance).toEqual([])
    expect(out.support).toEqual([])
  })
})

describe('buildReactionFramework', () => {
  it('positive regime above flip -> chop base case', () => {
    const out = buildReactionFramework({
      gammaForm: 'POSITIVE', price: 750, flip: 743, callWall: 755, putWall: 730,
      balanceLabel: 'Balanced',
    })
    expect(out.baseCase.toLowerCase()).toContain('chop')
    expect(out.invalidatedIf.length).toBeGreaterThan(0)
  })
  it('negative regime -> trend/acceleration base case', () => {
    const out = buildReactionFramework({
      gammaForm: 'NEGATIVE', price: 740, flip: 743, callWall: 755, putWall: 730,
      balanceLabel: 'Balanced',
    })
    expect(out.baseCase.toLowerCase()).toMatch(/trend|acceler/)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ironforge/webapp && npx vitest run src/lib/gex/derive.test.ts`
Expected: FAIL — cannot resolve `./derive`.

- [ ] **Step 3: Write the implementation**

```typescript
// ironforge/webapp/src/lib/gex/derive.ts
import type { StrikeGex } from './types'

type MiniStrike = Pick<StrikeGex, 'strike' | 'net_gamma'>

/** Top-N strikes above (resistance) and below (support) price, ranked by |net_gamma|. */
export function topStrikesByGamma(
  strikes: MiniStrike[],
  price: number,
  n: number,
): { resistance: MiniStrike[]; support: MiniStrike[] } {
  const above = strikes.filter((s) => s.strike > price)
  const below = strikes.filter((s) => s.strike < price)
  const byAbsGammaDesc = (a: MiniStrike, b: MiniStrike) =>
    Math.abs(b.net_gamma) - Math.abs(a.net_gamma)
  const resistance = [...above].sort(byAbsGammaDesc).slice(0, n).sort((a, b) => a.strike - b.strike)
  const support = [...below].sort(byAbsGammaDesc).slice(0, n).sort((a, b) => b.strike - a.strike)
  return { resistance, support }
}

export interface ReactionInput {
  gammaForm: string
  price: number
  flip: number | null
  callWall: number | null
  putWall: number | null
  balanceLabel: string
}

export interface ReactionFrameworkText {
  baseCase: string
  invalidatedIf: string
  notes: string[]
}

/** Deterministic Base Case / Invalidated-if narrative from regime + structure. */
export function buildReactionFramework(input: ReactionInput): ReactionFrameworkText {
  const { gammaForm, price, flip, callWall, putWall } = input
  const aboveFlip = flip != null ? price > flip : null
  const notes: string[] = []
  let baseCase: string
  let invalidatedIf: string

  if (gammaForm === 'NEGATIVE') {
    baseCase =
      'Negative gamma — dealers are short gamma. Expect trend / acceleration and wider ranges; favor directional plays.'
    invalidatedIf = 'Price reclaims the GEX flip and gamma turns positive (mean-reversion resumes).'
  } else if (gammaForm === 'POSITIVE') {
    baseCase =
      'Positive gamma — dealers are long gamma. Chop / pin until a catalyst; favor selling premium inside the expected range.'
    invalidatedIf = 'Vol shock or strong flow pushes cleanly through the call or put wall.'
  } else {
    baseCase = 'Neutral gamma — no strong dealer positioning. Rangebound unless a catalyst expands volatility.'
    invalidatedIf = 'A directional flow or vol expansion breaks the balance.'
  }

  if (aboveFlip === false) {
    notes.push(`Price is below the GEX flip${flip != null ? ` ($${flip.toFixed(0)})` : ''} — downside acceleration risk.`)
  } else if (aboveFlip === true) {
    notes.push(`Price is above the GEX flip${flip != null ? ` ($${flip.toFixed(0)})` : ''} — positive-gamma support.`)
  }
  if (callWall && price) {
    const d = ((callWall - price) / price) * 100
    if (d > 0 && d < 0.5) notes.push(`Call wall $${callWall.toFixed(0)} is ${d.toFixed(1)}% away — watch for rejection.`)
  }
  if (putWall && price) {
    const d = ((price - putWall) / price) * 100
    if (d > 0 && d < 0.5) notes.push(`Put wall $${putWall.toFixed(0)} is ${d.toFixed(1)}% away — watch for a bounce.`)
  }

  return { baseCase, invalidatedIf, notes }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ironforge/webapp && npx vitest run src/lib/gex/derive.test.ts`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/lib/gex/derive.ts ironforge/webapp/src/lib/gex/derive.test.ts
git commit -m "feat(gex): add derive helpers (top strikes, reaction framework) + tests"
```

---

### Task 10: `HeaderMetrics` + `KeyGammaLevels` components

**Files:**
- Create: `ironforge/webapp/src/components/gex/HeaderMetrics.tsx`
- Create: `ironforge/webapp/src/components/gex/KeyGammaLevels.tsx`

- [ ] **Step 1: `HeaderMetrics.tsx`**

```tsx
// ironforge/webapp/src/components/gex/HeaderMetrics.tsx
'use client'
import type { GexAnalysisData } from '@/lib/gex/types'

function fmt(n: number, d = 2): string {
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(d)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(d)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(d)}K`
  return n.toFixed(d)
}

const ratingColor = (r: string) =>
  r === 'BULLISH' ? 'text-green-400' : r === 'BEARISH' ? 'text-red-400' : 'text-gray-300'

export default function HeaderMetrics({ data }: { data: GexAnalysisData }) {
  const h = data.header
  const cells: { label: string; value: string; cls?: string }[] = [
    { label: 'Price', value: h.price.toFixed(2) },
    { label: 'GEX Flip', value: h.gex_flip != null ? h.gex_flip.toFixed(2) : 'N/A', cls: 'text-amber-300' },
    { label: '30-Day Vol', value: h['30_day_vol'] != null ? h['30_day_vol'].toFixed(1) : 'N/A' },
    { label: 'Call Structure', value: h.call_structure, cls: 'text-amber-300' },
    { label: 'Net GEX', value: fmt((h.net_gex || 0) * 1e6, 0) },
  ]
  return (
    <div className="forge-card rounded-xl p-4 flex flex-wrap items-center justify-between gap-6">
      <div className="flex flex-wrap items-center gap-6">
        {cells.map((c) => (
          <div key={c.label}>
            <div className="text-[11px] uppercase tracking-wide text-gray-500">{c.label}</div>
            <div className={`text-xl font-bold ${c.cls || 'text-white'}`}>{c.value}</div>
          </div>
        ))}
      </div>
      <div className="text-right">
        <div className="text-[11px] uppercase tracking-wide text-gray-500">Rating</div>
        <div className={`text-2xl font-bold ${ratingColor(h.rating)}`}>{h.rating}</div>
        <div className="text-[11px] text-gray-500">Gamma Form: {h.gamma_form}</div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: `KeyGammaLevels.tsx`**

```tsx
// ironforge/webapp/src/components/gex/KeyGammaLevels.tsx
'use client'
import type { GexAnalysisData } from '@/lib/gex/types'
import { topStrikesByGamma } from '@/lib/gex/derive'

// Adaptive magnitude formatter (matches HeaderMetrics/NetGexChart). Per-strike
// net-gamma scale varies, so never hard-code "M".
function gammaM(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return n.toFixed(1)
}

export default function KeyGammaLevels({ data }: { data: GexAnalysisData }) {
  const price = data.levels.price
  const { resistance, support } = topStrikesByGamma(data.gex_chart.strikes, price, 2)
  return (
    <div className="forge-card rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Key Gamma Levels ({data.expiration})</h3>
      <div className="space-y-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded bg-red-500/15 text-red-300 text-xs font-semibold">Resist</span>
          <span className="text-gray-200">
            {resistance.length
              ? resistance.map((s) => `${s.strike} (${gammaM(s.net_gamma)})`).join(', ')
              : '—'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded bg-green-500/15 text-green-300 text-xs font-semibold">Support</span>
          <span className="text-gray-200">
            {support.length
              ? support.map((s) => `${s.strike} (${gammaM(s.net_gamma)})`).join(', ')
              : '—'}
          </span>
        </div>
      </div>
      <p className="text-[11px] text-gray-500 mt-3">Largest absolute-gamma strikes around price.</p>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add ironforge/webapp/src/components/gex/HeaderMetrics.tsx ironforge/webapp/src/components/gex/KeyGammaLevels.tsx
git commit -m "feat(gex): add HeaderMetrics + KeyGammaLevels components"
```

---

### Task 11: `NetGexChart` component (recharts horizontal bars)

**Files:**
- Create: `ironforge/webapp/src/components/gex/NetGexChart.tsx`

- [ ] **Step 1: Write the chart** (fresh, themed; horizontal bars of net_gamma per strike with price/flip/±1σ reference lines)

```tsx
// ironforge/webapp/src/components/gex/NetGexChart.tsx
'use client'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'

export interface NetGexChartStrike {
  strike: number
  net_gamma: number
}

interface Props {
  title: string
  strikes: NetGexChartStrike[]
  price?: number | null
  flip?: number | null
  upper1sd?: number | null
  lower1sd?: number | null
  loading?: boolean
  emptyMessage?: string
}

function fmt(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return n.toFixed(1)
}

export default function NetGexChart({
  title, strikes, price, flip, upper1sd, lower1sd, loading, emptyMessage,
}: Props) {
  // Recharts horizontal bars: numeric Y (strike), value X (net_gamma).
  const data = [...strikes].sort((a, b) => a.strike - b.strike)
  return (
    <div className="forge-card rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
      {loading ? (
        <div className="h-[480px] flex items-center justify-center text-gray-500 text-sm">Loading…</div>
      ) : data.length === 0 ? (
        <div className="h-[480px] flex items-center justify-center text-amber-300 text-sm text-center px-6">
          {emptyMessage || 'No data (market may be closed).'}
        </div>
      ) : (
        <div className="h-[480px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart layout="vertical" data={data} margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
              <XAxis
                type="number"
                tick={{ fill: '#9ca3af', fontSize: 10 }}
                tickFormatter={(v) => fmt(v as number)}
              />
              <YAxis
                type="number"
                dataKey="strike"
                domain={['dataMin', 'dataMax']}
                tick={{ fill: '#9ca3af', fontSize: 10 }}
                width={48}
                reversed={false}
              />
              <Tooltip
                contentStyle={{ background: '#0b0b0f', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => [fmt(v), 'Net Gamma']}
                labelFormatter={(l) => `Strike ${l}`}
              />
              <ReferenceLine x={0} stroke="#4b5563" />
              {price != null && (
                <ReferenceLine y={price} stroke="#3b82f6" strokeWidth={1.5}
                  label={{ value: 'Price', fill: '#3b82f6', fontSize: 10, position: 'right' }} />
              )}
              {flip != null && (
                <ReferenceLine y={flip} stroke="#eab308" strokeDasharray="4 3"
                  label={{ value: 'Flip', fill: '#eab308', fontSize: 10, position: 'right' }} />
              )}
              {upper1sd != null && (
                <ReferenceLine y={upper1sd} stroke="#f59e0b" strokeDasharray="2 4"
                  label={{ value: '+1σ', fill: '#f59e0b', fontSize: 10, position: 'right' }} />
              )}
              {lower1sd != null && (
                <ReferenceLine y={lower1sd} stroke="#f59e0b" strokeDasharray="2 4"
                  label={{ value: '−1σ', fill: '#f59e0b', fontSize: 10, position: 'right' }} />
              )}
              <Bar dataKey="net_gamma" barSize={6}>
                {data.map((d, i) => (
                  <Cell key={i} fill={d.net_gamma >= 0 ? '#22c55e' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add ironforge/webapp/src/components/gex/NetGexChart.tsx
git commit -m "feat(gex): add NetGexChart component"
```

---

### Task 12: `ReactionFramework`, `PositioningRegime`, `StructureBalance` components

**Files:**
- Create: `ironforge/webapp/src/components/gex/ReactionFramework.tsx`
- Create: `ironforge/webapp/src/components/gex/PositioningRegime.tsx`
- Create: `ironforge/webapp/src/components/gex/StructureBalance.tsx`

- [ ] **Step 1: `ReactionFramework.tsx`**

```tsx
// ironforge/webapp/src/components/gex/ReactionFramework.tsx
'use client'
import type { GexAnalysisData } from '@/lib/gex/types'
import { buildReactionFramework } from '@/lib/gex/derive'

export default function ReactionFramework({
  data, balanceLabel,
}: { data: GexAnalysisData; balanceLabel: string }) {
  const fw = buildReactionFramework({
    gammaForm: data.header.gamma_form,
    price: data.header.price,
    flip: data.header.gex_flip,
    callWall: data.levels.call_wall,
    putWall: data.levels.put_wall,
    balanceLabel,
  })
  return (
    <div className="forge-card rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Reaction Framework</h3>
      <div className="mb-3">
        <div className="text-[11px] uppercase tracking-wide text-amber-300">Base Case</div>
        <p className="text-sm text-gray-200 mt-1">{fw.baseCase}</p>
      </div>
      <div className="mb-3">
        <div className="text-[11px] uppercase tracking-wide text-gray-500">Invalidated if</div>
        <p className="text-sm text-gray-300 mt-1">{fw.invalidatedIf}</p>
      </div>
      {fw.notes.length > 0 && (
        <ul className="space-y-1">
          {fw.notes.map((n, i) => (
            <li key={i} className="text-xs text-gray-400">• {n}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 2: `PositioningRegime.tsx`**

```tsx
// ironforge/webapp/src/components/gex/PositioningRegime.tsx
'use client'
import type { Positioning } from '@/lib/gex/types'

const labelColor = (l: string) =>
  l === 'Bullish' ? 'text-green-400' : l === 'Bearish' ? 'text-red-400' : 'text-gray-300'

export default function PositioningRegime({ positioning }: { positioning?: Positioning }) {
  if (!positioning) {
    return (
      <div className="forge-card rounded-xl p-4">
        <h3 className="text-sm font-semibold text-white mb-2">Positioning Regime</h3>
        <p className="text-xs text-gray-500">Not available (after-hours fallback).</p>
      </div>
    )
  }
  const pct = Math.max(0, Math.min(100, positioning.pressure_score))
  return (
    <div className="forge-card rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-2">Positioning Regime</h3>
      <div className="flex items-baseline gap-3">
        <span className={`text-xl font-bold ${labelColor(positioning.regime_label)}`}>
          {positioning.regime_label}
        </span>
        <span className="text-sm text-gray-400">pressure {positioning.pressure_score}/100</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-gray-800 overflow-hidden">
        <div className="h-full bg-amber-400" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-gray-500 mt-2">Call vs Put Pressure {positioning.call_vs_put_pressure.toFixed(3)}</p>
    </div>
  )
}
```

- [ ] **Step 3: `StructureBalance.tsx`**

```tsx
// ironforge/webapp/src/components/gex/StructureBalance.tsx
'use client'
import type { StructureBalance } from '@/lib/gex/types'

export default function StructureBalanceCard({
  sb, loading,
}: { sb?: StructureBalance; loading?: boolean }) {
  return (
    <div className="forge-card rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-2">
        Structure Balance <span className="text-xs text-gray-500">(7-Day Horizon)</span>
      </h3>
      {loading ? (
        <p className="text-xs text-gray-500">Loading full board…</p>
      ) : !sb ? (
        <p className="text-xs text-gray-500">Not available.</p>
      ) : (
        <>
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-bold text-amber-300">{sb.label}</span>
            <span className="text-sm text-gray-400">{sb.balance.toFixed(3)}</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">{sb.summary}</p>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add ironforge/webapp/src/components/gex/ReactionFramework.tsx ironforge/webapp/src/components/gex/PositioningRegime.tsx ironforge/webapp/src/components/gex/StructureBalance.tsx
git commit -m "feat(gex): add Reaction/Positioning/StructureBalance components"
```

---

### Task 13: `FlowDiagnostics` + `SkewMeasures` components

**Files:**
- Create: `ironforge/webapp/src/components/gex/FlowDiagnostics.tsx`
- Create: `ironforge/webapp/src/components/gex/SkewMeasures.tsx`

- [ ] **Step 1: `FlowDiagnostics.tsx`**

```tsx
// ironforge/webapp/src/components/gex/FlowDiagnostics.tsx
'use client'
import type { GexAnalysisData } from '@/lib/gex/types'

export default function FlowDiagnostics({ data }: { data: GexAnalysisData }) {
  return (
    <div className="forge-card rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-1">Options Flow Diagnostics</h3>
      <p className="text-[11px] text-gray-500 mb-3">{data.flow_diagnostics.note}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {data.flow_diagnostics.cards.map((c) => (
          <div key={c.id} className="rounded-lg border border-gray-800 bg-black/20 p-3">
            <div className="text-sm font-semibold text-white">{c.label}</div>
            <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">{c.metric_name}</div>
            <div className="text-lg font-bold text-amber-300">{c.metric_value}</div>
            <div className="text-[11px] text-gray-400 mt-1">{c.description}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: `SkewMeasures.tsx`**

```tsx
// ironforge/webapp/src/components/gex/SkewMeasures.tsx
'use client'
import type { GexAnalysisData } from '@/lib/gex/types'

const ivStr = (v: number | null) => (v != null ? `${v}%` : 'N/A')

export default function SkewMeasures({ data }: { data: GexAnalysisData }) {
  const s = data.skew_measures
  const rows: { label: string; value: string }[] = [
    { label: 'Skew Ratio', value: s.skew_ratio?.toFixed(3) ?? 'N/A' },
    { label: 'Call Skew', value: s.call_skew?.toFixed(3) ?? 'N/A' },
    { label: 'ATM Call IV', value: ivStr(s.atm_call_iv) },
    { label: 'ATM Put IV', value: ivStr(s.atm_put_iv) },
    { label: 'OTM Call IV', value: ivStr(s.avg_otm_call_iv) },
    { label: 'OTM Put IV', value: ivStr(s.avg_otm_put_iv) },
  ]
  return (
    <div className="forge-card rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Skew Measures</h3>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between">
            <span className="text-gray-400">{r.label}</span>
            <span className="text-gray-100 font-mono">{r.value}</span>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-gray-500 mt-3">{s.skew_ratio_description}</p>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add ironforge/webapp/src/components/gex/FlowDiagnostics.tsx ironforge/webapp/src/components/gex/SkewMeasures.tsx
git commit -m "feat(gex): add FlowDiagnostics + SkewMeasures components"
```

---

### Task 14: The `/gex` page (wiring + lazy full-board)

**Files:**
- Create: `ironforge/webapp/src/app/gex/page.tsx`

- [ ] **Step 1: Write the page**

```tsx
// ironforge/webapp/src/app/gex/page.tsx
'use client'
import { useCallback, useEffect, useState } from 'react'
import type { GexAnalysisData, GexAllData } from '@/lib/gex/types'
import HeaderMetrics from '@/components/gex/HeaderMetrics'
import KeyGammaLevels from '@/components/gex/KeyGammaLevels'
import NetGexChart from '@/components/gex/NetGexChart'
import ReactionFramework from '@/components/gex/ReactionFramework'
import PositioningRegime from '@/components/gex/PositioningRegime'
import StructureBalanceCard from '@/components/gex/StructureBalance'
import FlowDiagnostics from '@/components/gex/FlowDiagnostics'
import SkewMeasures from '@/components/gex/SkewMeasures'

// Market hours gate (ET) — only auto-refresh while open.
function isMarketOpen(): boolean {
  const now = new Date()
  const day = now.getUTCDay()
  if (day === 0 || day === 6) return false
  const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes()
  const month = now.getUTCMonth()
  const isDST = month >= 2 && month <= 9
  const etMin = utcMin - (isDST ? 4 : 5) * 60
  return etMin >= 570 && etMin < 975
}

export default function GexProfilePage() {
  const symbol = 'SPY'
  const [data, setData] = useState<GexAnalysisData | null>(null)
  const [allData, setAllData] = useState<GexAllData | null>(null)
  const [loading, setLoading] = useState(true)
  const [allLoading, setAllLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [updated, setUpdated] = useState<Date | null>(null)

  const fetchFast = useCallback(async () => {
    try {
      setError(null)
      const r = await fetch(`/api/gex/analysis?symbol=${symbol}`, { cache: 'no-store' })
      const j = await r.json()
      if (j?.success) {
        setData(j.data)
        setUpdated(new Date())
      } else {
        setError(j?.message || 'GEX data unavailable')
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchAll = useCallback(async () => {
    try {
      setAllLoading(true)
      const r = await fetch(`/api/gex/analysis-all?symbol=${symbol}`, { cache: 'no-store' })
      const j = await r.json()
      if (j?.success) setAllData(j.data)
    } catch {
      /* full board is best-effort */
    } finally {
      setAllLoading(false)
    }
  }, [])

  useEffect(() => { fetchFast() }, [fetchFast])
  useEffect(() => { fetchAll() }, [fetchAll])

  useEffect(() => {
    const id = setInterval(() => {
      if (isMarketOpen()) { fetchFast(); fetchAll() }
    }, 30000)
    return () => clearInterval(id)
  }, [fetchFast, fetchAll])

  const balanceLabel = allData?.structure_balance?.label || 'Balanced'

  return (
    <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">GEX Profile <span className="text-amber-400">{symbol}</span></h1>
          <p className="text-sm text-gray-500">0DTE gamma exposure — nearest expiration. Net gamma by strike, walls, flip, and ±1σ.</p>
        </div>
        <div className="text-xs text-gray-500 text-right">
          {updated && <div>Updated {updated.toLocaleTimeString()}</div>}
          {!isMarketOpen() && <div className="text-amber-300">Data as of last close</div>}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>
      )}

      {loading && !data ? (
        <div className="h-64 flex items-center justify-center text-gray-500">Loading GEX profile…</div>
      ) : data ? (
        <>
          <HeaderMetrics data={data} />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <ReactionFramework data={data} balanceLabel={balanceLabel} />
            <PositioningRegime positioning={data.positioning} />
            <div className="space-y-6">
              <KeyGammaLevels data={data} />
              <StructureBalanceCard sb={allData?.structure_balance} loading={allLoading} />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <NetGexChart
              title={`${symbol} Net GEX — ${data.expiration} (0DTE)`}
              strikes={data.gex_chart.strikes}
              price={data.levels.price}
              flip={data.levels.gex_flip}
              upper1sd={data.levels.upper_1sd}
              lower1sd={data.levels.lower_1sd}
              emptyMessage="Real-time data not available outside market hours (8:30am–3:00pm CT)."
            />
            <NetGexChart
              title={`${symbol} Net GEX — All Expirations`}
              strikes={allData?.gex_chart_all.strikes || []}
              price={allData?.spot_price ?? data.levels.price}
              flip={data.levels.gex_flip}
              loading={allLoading && !allData}
              emptyMessage="Full-board aggregate unavailable."
            />
          </div>

          <FlowDiagnostics data={data} />
          <SkewMeasures data={data} />
        </>
      ) : null}
    </main>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add ironforge/webapp/src/app/gex/page.tsx
git commit -m "feat(gex): add /gex profile page (fast view + lazy full board)"
```

---

### Task 15: Add nav link

**Files:**
- Modify: `ironforge/webapp/src/components/Nav.tsx:28-41` (the `links` array)

- [ ] **Step 1: Add the link**

Insert after the `/flare` entry in the `links` array:

```tsx
  { href: '/gex', label: 'GEX Profile', className: 'text-cyan-400 hover:text-cyan-300' },
```

- [ ] **Step 2: Commit**

```bash
git add ironforge/webapp/src/components/Nav.tsx
git commit -m "feat(gex): add GEX Profile nav link"
```

---

### Task 16: Build + verify

**Files:** none (verification only)

- [ ] **Step 1: Run frontend unit tests**

Run: `cd ironforge/webapp && npx vitest run src/lib/gex/derive.test.ts`
Expected: PASS.

- [ ] **Step 2: Build the IronForge webapp**

Run: `cd ironforge/webapp && npx next build`
Expected: "Compiled successfully" with `/gex`, `/api/gex/analysis`, and `/api/gex/analysis-all` listed in the route output. Fix any TS errors (null-guard, `catch (e: unknown)`).

- [ ] **Step 3: Run the backend metric tests once more**

Run (repo root): `pytest tests/test_gex_profile_metrics.py -v`
Expected: 12 passed.

- [ ] **Step 4: Manual page check (dev or preview)**

Start the webapp (`cd ironforge/webapp && npm run dev`) with `ALPHAGEX_API_BASE` reachable, open `http://localhost:3000/gex`, and confirm: header metrics render, Key Gamma Levels show Resist/Support, the left (0DTE) Net GEX chart renders, Positioning Regime + Reaction Framework render, and the right (All Expirations) chart + Structure Balance fill in after the lazy call. After hours, confirm the page shows last-close data and the Positioning/Structure panels degrade gracefully instead of crashing.

- [ ] **Step 5: Commit any build fixes**

```bash
git add -A
git commit -m "fix(gex): resolve build/type issues for GEX profile page"
```

---

## Final integration

- [ ] Confirm all tasks' commits are on `claude/ironforge-gex-profile`.
- [ ] Per the monorepo merge policy (`ironforge/` in auto-merge scope; backend changes are additive/non-breaking), once `npx next build` is green and `/gex` is verified, merge `claude/ironforge-gex-profile` to `main` (rebase on `origin/main` first if GitHub reports a conflict). Render auto-deploys both `alphagex-api` and the IronForge webapp.
- [ ] Post-merge: hit `https://<ironforge-host>/gex` and `https://alphagex-api.onrender.com/api/watchtower/gex-analysis/all?symbol=SPY` to confirm production.

## Self-review notes (spec coverage)

- Phase 1 (header, key levels, net-GEX profile, reaction framework, diagnostics, skew) → Tasks 8–14. ✓
- Phase 2a positioning pressure → Tasks 1, 4 (+ component Task 12). ✓
- Phase 2b structure balance → Tasks 2, 5 (+ component Task 12). ✓
- Phase 2c full-board aggregate (lazy, concurrent, cached, partial-tolerant) → Tasks 3, 5; proxy Task 7; lazy wiring Task 14. ✓
- Plumbing thin proxy → Tasks 6–7. ✓
- Theming/nav/no-lucide → Tasks 10–15. ✓
- Testing/verification → Tasks 1–3 (pytest), 9 (vitest), 16 (build + manual). ✓
- Graceful after-hours degradation (omit positioning/structure when fallback can't supply) → Task 5 (route tolerates), Task 12 (`PositioningRegime`/`StructureBalanceCard` render "not available"), Task 14 (best-effort full board). ✓
