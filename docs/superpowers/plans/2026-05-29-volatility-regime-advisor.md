# Volatility Regime Advisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a SPY/VIX volatility-regime advisor that gives a directional options read (puts/calls/neutral/bounce), a data-derived timing & expiration estimate, backtest hit-rates, and a self-scoring forward track record — surfaced on a dedicated IronForge `/volatility` page and a daily-brief line.

**Architecture:** The "brain" (signal engine, recommendation, timing, evidence) lives in the AlphaGEX FastAPI backend next to the CBOE feed and the backtest. It is exposed via two endpoints. A daily collector job snapshots each day's recommendation and later scores it. IronForge (separate Next.js app in the same repo) renders a page that proxies those endpoints and adds a brief line — mirroring how the existing `/gex` page proxies AlphaGEX.

**Tech Stack:** Python 3.11, FastAPI, pandas, `requests`, `schedule`, psycopg2 via `database_adapter`; pytest. Frontend: Next.js 14 (app router), React 18, recharts 2.13, vitest.

---

## PHASE 3–4 REVISION (post-discovery, Task 10 findings — these OVERRIDE the Phase 3/4 task code below)

Discovery of the real IronForge conventions changed the frontend approach. Build Phase 3/4 with these, not the original Task 11–17 assumptions:

- **AlphaGEX access = same-origin proxy route.** Client never calls AlphaGEX directly. Create `ironforge/webapp/src/app/api/volatility/route.ts` with `export const dynamic = 'force-dynamic'`, a 5s `AbortController`, fetching `${(process.env.ALPHAGEX_API_BASE || 'https://alphagex-api.onrender.com').replace(/\/$/,'')}/api/vix/regime-advisor`, returning `NextResponse.json(...)` (502 on error). Add a second proxy `src/app/api/volatility/history/route.ts` → `/api/vix/regime-advisor/history?days=...`. (Pattern mirrors `src/app/api/blaze/gex-context/route.ts`.)
- **Page = `'use client'` + SWR**, not a server component. `src/app/volatility/page.tsx` fetches `/api/volatility` (+ `/api/volatility/history`) via SWR with the shared `@/lib/fetcher`. (Reference: `src/app/blaze/page.tsx` + `BlazeDirectionalChart.tsx` SWR usage.)
- **Styling = `forge-*` tokens** (`bg-forge-card/80`, `border-forge-border`, `text-forge-muted`, `bg-forge-bg`), accents via Tailwind (`text-emerald-400`/`text-red-400`/`text-violet-400`). Card chrome: `rounded-xl border border-forge-border bg-forge-card/80 px-4 py-3`. Replace all `neutral-*` classes in the Phase 3 component code with these.
- **Charts = recharts inline**, copy idiom from `src/components/EquityChart.tsx`. Colors: axis stroke `#44403c`, tick text `#a8a29e`, tooltip bg `#1c1917` border `#292524`; series emerald `#10b981`/red `#ef4444`/blue `#3b82f6`/violet `#a78bfa`; target line `#f59e0b`.
- **Tests = pure-logic only** (vitest `environment: 'node'`, no jsdom/ResizeObserver). Do NOT use `@testing-library/react` `render()`. Extract display/format/classify helpers (e.g. stance label, regime label, pct formatting, DTE text) into plain functions and unit-test those (`src/.../*.test.ts`). Verify JSX via `npx tsc --noEmit` + `npm run build`.
- **Nav** = append one object to the `links` array in `src/components/Nav.tsx`.
- **Daily brief line** = add a `lines.push(...)` in `src/lib/market-brief.ts` `formatInputsForPrompt()` MARKET STATE block (~L355-360). That file already fetches the VIX family (`QUOTE_SYMBOLS=['SPY','VIX','VVIX','VIX9D','VIX3M','VIX6M']`) and computes a term-structure label — fetch the advisor (`${ALPHAGEX_API_BASE}/api/vix/regime-advisor`) for the regime+stance+DTE, with graceful fallback to a locally-derived contango/backwardation label if the fetch fails. `BriefingMacroRibbon.tsx` is prop-driven (optional second surface, not required).

Revised frontend task grouping (executed by controller): **3A** proxy routes + types + working `'use client'` page shell (SWR); **3B** components + charts (forge-styled) wired into the page; **3C** nav link + brief line. The component CODE in Tasks 11–14 below is a starting point — reuse the structure, apply the overrides above.

---

## Conventions to follow (from the existing codebase)

- **DB access (Python):** `from database_adapter import get_connection` → `conn.cursor()`, `%s` params, `conn.commit()`, `conn.close()`. Postgres.
- **Table creation:** add a `CREATE TABLE IF NOT EXISTS` block in `db/config_and_database.py` (see `vix_term_structure` at ~line 1210).
- **Live VIX/VVIX (on origin/main):** `from data.vix_fetcher import get_vix_with_source, get_vvix_with_source` — each returns `(price, source)`. Term structure (VIX9D/VIX3M/VIX6M) is NOT in the repo; the advisor fetches it from CBOE delayed-quotes (`cdn.cboe.com/api/global/delayed_quotes/quotes/_<SYM>.json`).
- **CBOE history:** daily CSVs at `https://cdn.cboe.com/api/global/us_indices/daily_prices/<SYM>_History.csv` (columns `DATE,...,CLOSE`; VVIX is `DATE,VVIX`).
- **Routes:** add to `backend/api/routes/vix_routes.py` (FastAPI `APIRouter(prefix="/api/vix")`). Never raise to the client — return a fallback dict (see `get_vix_current`).
- **Collector worker:** `data/automated_data_collector.py` — define `run_*()` guarded by `is_after_market_close()`, register in `setup_schedule()`; log via `log_collection(job, table, success, error, tb)`.
- **Backtest harness:** `backtest/vvix_vix_analysis/` (already has `analyze.py` + `data/` with `VIX/VVIX/VIX3M/VIX9D.csv` and `SPY_raw.json`).
- **Frontend:** IronForge app at `ironforge/webapp/` (on `origin/main`). App-router pages under `src/app/`, components under `src/components/`, charts via recharts, tests via vitest. Match `BriefingCard`/dashboard styling; custom SVG glyphs, no emojis (per `feedback_no_cheap_visuals`).

## Pre-flight (DONE by controller — for reference)

The feature branch `claude/vol-regime-advisor` was created from `origin/main` (which already contains IronForge at `ironforge/webapp/src/...` AND a `data/vix_fetcher.py` with live `get_vix_with_source()` / `get_vvix_with_source()`). The spec + plan docs are committed on this branch. The harness `backtest/vvix_vix_analysis/` (analyze.py + data CSVs/JSON) is present (untracked).

**Key integration decision (revised):** Do NOT cherry-pick the earlier VVIX-feed PR. `origin/main` already provides live VIX + VVIX via `data/vix_fetcher.py`. It does NOT provide the VIX9D/VIX3M/VIX6M term structure — the advisor brings its own CBOE fetch for that (it needs CBOE history for z-scores anyway). So the advisor sources:
- **VIX, VVIX (live):** `from data.vix_fetcher import get_vix_with_source, get_vvix_with_source` (each returns `(price, source)`).
- **VIX9D / VIX3M / VIX6M (live, ~15-min delayed):** CBOE delayed-quotes JSON `https://cdn.cboe.com/api/global/delayed_quotes/quotes/_<SYM>.json` (numeric field `data.current_price`).
- **Trailing history (z-scores/percentiles):** CBOE daily history CSVs `https://cdn.cboe.com/api/global/us_indices/daily_prices/<SYM>_History.csv`.

The engine imports **nothing** from `data/unified_data_provider.py`.

---

## PHASE 1 — Backend brain (engine + evidence + timing + endpoint)

### Task 1: Backtest evidence + timing generator

**Files:**
- Create: `backtest/vvix_vix_analysis/build_evidence.py`
- Create: `backtest/vvix_vix_analysis/evidence.json` (generated output, committed)
- Test: `backtest/vvix_vix_analysis/test_build_evidence.py`

- [ ] **Step 1: Write the failing test**

```python
# backtest/vvix_vix_analysis/test_build_evidence.py
import json, os, subprocess, sys

HERE = os.path.dirname(__file__)

def test_evidence_json_shape():
    # regenerate then validate
    subprocess.run([sys.executable, os.path.join(HERE, "build_evidence.py")], check=True)
    with open(os.path.join(HERE, "evidence.json")) as f:
        ev = json.load(f)
    assert "signals" in ev and "as_of" in ev
    for key in ("backwardation", "ts_flattening", "exhaustion", "double_floor", "divergence"):
        s = ev["signals"][key]
        for field in ("n", "hit_rate", "fwd_vix_5", "fwd_spy_5", "t_fwd_spy_5",
                      "timing_median", "timing_p25", "timing_p75", "timing_cdf", "suggested_dte"):
            assert field in s, f"{key} missing {field}"
        assert 0.0 <= s["hit_rate"] <= 1.0
        cdf = s["timing_cdf"]
        assert len(cdf) == 21
        assert all(0.0 <= x <= 1.0 for x in cdf)
        assert all(cdf[i] <= cdf[i+1] + 1e-9 for i in range(len(cdf)-1)), "CDF must be monotonic"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest backtest/vvix_vix_analysis/test_build_evidence.py -v`
Expected: FAIL (build_evidence.py does not exist).

- [ ] **Step 3: Write the generator**

```python
# backtest/vvix_vix_analysis/build_evidence.py
"""Generate evidence.json: per-signal backtest hit-rates + timing distributions.
Reuses the loaders/feature logic from analyze.py. Pure historical stats; no look-ahead."""
import json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")

def _load_cboe(name, col):
    df = pd.read_csv(os.path.join(DATA, f"{name}.csv"))
    df.columns = [c.strip().upper() for c in df.columns]
    d = df.columns[0]
    df[d] = pd.to_datetime(df[d])
    return df[[d, df.columns[-1]]].rename(columns={d: "date", df.columns[-1]: col}).set_index("date")[col]

def _load_spy():
    with open(os.path.join(DATA, "SPY_raw.json")) as f:
        j = json.load(f)
    r = j["chart"]["result"][0]
    ts = pd.to_datetime(r["timestamp"], unit="s").normalize()
    s = pd.Series(r["indicators"]["adjclose"][0]["adjclose"], index=ts, name="spy").dropna()
    return s[~s.index.duplicated(keep="last")]

def _z(s, w=60):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()

def build():
    vix = _load_cboe("VIX", "vix"); vvix = _load_cboe("VVIX", "vvix")
    vix3m = _load_cboe("VIX3M", "vix3m"); vix9d = _load_cboe("VIX9D", "vix9d")
    spy = _load_spy()
    df = pd.concat([vix, vvix, vix3m, vix9d, spy], axis=1)
    df = df[df.index >= "2006-03-06"].copy()
    df["spy"] = df["spy"].ffill()
    df = df.dropna(subset=["vix", "vvix"])

    df["vix_z"] = _z(df.vix); df["vvix_z"] = _z(df.vvix)
    df["ts_3m"] = df.vix / df.vix3m
    df["vix_pct"] = df.vix.rolling(252).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    df["vix_hi10"] = df.vix >= df.vix.rolling(10).max()
    df["vvix_hi10"] = df.vvix >= df.vvix.rolling(10).max()
    for k in (1, 3, 5, 10):
        df[f"vix_fwd{k}"] = df.vix.shift(-k) / df.vix - 1.0
        df[f"vix_fwdmax{k}"] = df.vix.shift(-1).rolling(k).max().shift(-(k-1)) / df.vix - 1.0
        df[f"spy_fwd{k}"] = df.spy.shift(-k) / df.spy - 1.0

    signals = {
        "backwardation": df.ts_3m > 1.0,
        "ts_flattening": (df.ts_3m > 0.95) & (df.ts_3m.shift(20) < 0.90),
        "exhaustion": df.vix_hi10 & (~df.vvix_hi10) & (df.vix_pct > 0.80),
        "double_floor": (df.vvix < 85) & (df.vix < 14),
        "divergence": (df.vvix_z > 1.0) & (df.vix_z < 0.0),
    }
    # canonical "correct" call per signal
    correct = {
        "backwardation": df.spy_fwd5 > 0,
        "ts_flattening": df.vix_fwdmax5 >= 0.20,
        "exhaustion": df.spy_fwd3 > 0,
        "double_floor": df.vix_fwd10 > 0,
        "divergence": df.vix_fwdmax5 >= 0.20,
    }
    # timing: trading-days until the signal's event (capped at 21)
    def days_to_event(mask, kind):
        out = []
        idx = df.index
        for i in np.where(mask.fillna(False).values)[0]:
            base_vix = df.vix.values[i]; base_spy = df.spy.values[i]
            landed = None
            for k in range(1, 22):
                if i + k >= len(df): break
                v = df.vix.values[i+k]; p = df.spy.values[i+k]
                if kind == "vol_down" and v <= base_vix * 0.90: landed = k; break
                if kind == "spy_up" and p >= base_spy * 1.005: landed = k; break
                if kind == "vix_spike" and v >= base_vix * 1.20: landed = k; break
                if kind == "vix_up" and v > base_vix: landed = k; break
            out.append(landed)
        return [x for x in out if x is not None], len(out)
    kind = {"backwardation": "spy_up", "ts_flattening": "vix_spike",
            "exhaustion": "vol_down", "double_floor": "vix_up", "divergence": "vix_spike"}

    base_spy5_up = (df.spy_fwd5 > 0).mean()
    out = {"as_of": str(df.index.max().date()),
           "sample_start": str(df.index.min().date()),
           "n_days": int(len(df)), "signals": {}}
    for key, mask in signals.items():
        m = mask.fillna(False)
        n = int(m.sum())
        sel = df[m]
        landed_days, total = days_to_event(mask, kind[key])
        arr = np.array(landed_days) if landed_days else np.array([21])
        cdf = [float((arr <= k).mean()) for k in range(1, 22)]
        p75 = int(np.percentile(arr, 75))
        suggested_dte = int(np.ceil(p75 * 7 / 5 * 1.3) + 2)  # trading->calendar, +30% buffer, +2d
        def tstat(col):
            s_on = sel[col].dropna(); s_all = df[col].dropna()
            if len(s_on) < 5: return 0.0
            se = np.sqrt(s_on.var()/len(s_on) + s_all.var()/len(s_all))
            return float((s_on.mean() - s_all.mean())/se) if se else 0.0
        out["signals"][key] = {
            "n": n,
            "hit_rate": float(correct[key][m].mean()) if n else 0.0,
            "fwd_vix_1": float(sel.vix_fwd1.mean()), "fwd_vix_3": float(sel.vix_fwd3.mean()),
            "fwd_vix_5": float(sel.vix_fwd5.mean()), "fwd_vix_10": float(sel.vix_fwd10.mean()),
            "fwd_spy_3": float(sel.spy_fwd3.mean()), "fwd_spy_5": float(sel.spy_fwd5.mean()),
            "t_fwd_spy_5": tstat("spy_fwd5"), "t_fwd_vix_5": tstat("vix_fwd5"),
            "timing_median": int(np.median(arr)), "timing_p25": int(np.percentile(arr, 25)),
            "timing_p75": p75, "timing_cdf": cdf, "suggested_dte": suggested_dte,
            "event_landed_rate": float(len(landed_days)/total) if total else 0.0,
        }
    with open(os.path.join(HERE, "evidence.json"), "w") as f:
        json.dump(out, f, indent=2)
    return out

if __name__ == "__main__":
    build()
    print("evidence.json written")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest backtest/vvix_vix_analysis/test_build_evidence.py -v`
Expected: PASS.

- [ ] **Step 5: Add a `.gitignore` for transient data, commit generator + evidence.json**

```bash
printf 'data/SPY_raw.json\ndata/*.csv\n' > backtest/vvix_vix_analysis/.gitignore
git add backtest/vvix_vix_analysis/build_evidence.py backtest/vvix_vix_analysis/evidence.json backtest/vvix_vix_analysis/test_build_evidence.py backtest/vvix_vix_analysis/.gitignore backtest/vvix_vix_analysis/analyze.py
git commit -m "feat(vol-advisor): backtest evidence + timing generator (evidence.json)"
```

---

### Task 2: Signal computation (pure)

**Files:**
- Create: `core/vol_regime_advisor.py`
- Test: `tests/test_vol_regime_advisor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vol_regime_advisor.py
import pandas as pd
from core.vol_regime_advisor import compute_signals

def _history(vix_last, vix3m_last, n=300):
    # flat history then set the last row; enough rows for rolling(252)/rolling(20)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame(index=idx)
    df["vix"] = 15.0; df["vvix"] = 90.0; df["vix3m"] = 18.0; df["vix9d"] = 13.0
    df.loc[df.index[-21], "vix"] = vix3m_last  # 20 days ago for flattening test default
    df.iloc[-1, df.columns.get_loc("vix")] = vix_last
    df.iloc[-1, df.columns.get_loc("vix3m")] = vix3m_last
    return df

def test_backwardation_fires_when_vix_above_vix3m():
    df = _history(vix_last=25.0, vix3m_last=20.0)
    sigs = compute_signals(df)
    assert sigs["backwardation"]["active"] is True

def test_backwardation_off_in_contango():
    df = _history(vix_last=15.0, vix3m_last=18.0)
    sigs = compute_signals(df)
    assert sigs["backwardation"]["active"] is False

def test_divergence_flagged_low_confidence():
    df = _history(vix_last=15.0, vix3m_last=18.0)
    sigs = compute_signals(df)
    assert sigs["divergence"]["confidence"] == "low"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vol_regime_advisor.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write `compute_signals`**

```python
# core/vol_regime_advisor.py
"""Volatility regime advisor — signal engine, recommendation, timing.

Pure functions operate on an injected history DataFrame (columns: vix, vvix,
vix3m, vix9d) whose LAST row is "today". Live wrapper fetches CBOE data.
Backtest evidence (hit-rates + timing) is loaded from evidence.json.
"""
import json, os
from typing import Dict, Optional
import numpy as np
import pandas as pd
import requests

CBOE_HISTORY_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
EVIDENCE_PATH = os.path.join(os.path.dirname(__file__), "..", "backtest",
                             "vvix_vix_analysis", "evidence.json")

SIGNAL_CONFIDENCE = {
    "backwardation": "high", "ts_flattening": "medium", "exhaustion": "medium",
    "double_floor": "low", "divergence": "low",
}
SIGNAL_BLURB = {
    "backwardation": "VIX above VIX3M — stress is here. Vol historically mean-reverts down and SPY tends to recover; fade the spike.",
    "ts_flattening": "Term structure flattening from contango — an early warning that a vol spike may be building.",
    "exhaustion": "VIX made a new high but VVIX won't confirm — vol tends to fade and SPY bounces.",
    "double_floor": "VIX and VVIX both at the floor — complacent; vol drifts up slowly. Owning optionality is cheap.",
    "divergence": "VVIX elevated while VIX calm. NOTE: 20-yr study shows this is statistically noise — low confidence.",
}

def _z(s, w=60):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()

def compute_signals(history: pd.DataFrame) -> Dict[str, dict]:
    """history: DataFrame indexed by date with columns vix,vvix,vix3m,vix9d; last row = today."""
    df = history.copy()
    df["vix_z"] = _z(df["vix"]); df["vvix_z"] = _z(df["vvix"])
    df["ts_3m"] = df["vix"] / df["vix3m"]
    df["vix_pct"] = df["vix"].rolling(252).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    df["vix_hi10"] = df["vix"] >= df["vix"].rolling(10).max()
    df["vvix_hi10"] = df["vvix"] >= df["vvix"].rolling(10).max()
    r = df.iloc[-1]
    ts20 = df["ts_3m"].iloc[-21] if len(df) > 21 else float("nan")

    raw = {
        "backwardation": bool(r["ts_3m"] > 1.0),
        "ts_flattening": bool(r["ts_3m"] > 0.95 and ts20 < 0.90),
        "exhaustion": bool(r["vix_hi10"] and not r["vvix_hi10"] and (r["vix_pct"] or 0) > 0.80),
        "double_floor": bool(r["vvix"] < 85 and r["vix"] < 14),
        "divergence": bool((r["vvix_z"] or 0) > 1.0 and (r["vix_z"] or 0) < 0.0),
    }
    values = {
        "backwardation": float(r["ts_3m"]), "ts_flattening": float(r["ts_3m"]),
        "exhaustion": float(r["vix_pct"] or 0), "double_floor": float(r["vvix"]),
        "divergence": float(r["vvix_z"] or 0),
    }
    return {
        key: {"active": raw[key], "value": round(values[key], 4),
              "confidence": SIGNAL_CONFIDENCE[key], "blurb": SIGNAL_BLURB[key]}
        for key in raw
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vol_regime_advisor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/vol_regime_advisor.py tests/test_vol_regime_advisor.py
git commit -m "feat(vol-advisor): signal computation engine"
```

---

### Task 3: Recommendation + report assembly (pure)

**Files:**
- Modify: `core/vol_regime_advisor.py`
- Test: `tests/test_vol_regime_advisor.py`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/test_vol_regime_advisor.py
from core.vol_regime_advisor import build_recommendation, compute_report

def _sigs(active):
    base = {k: {"active": False, "value": 0.0, "confidence": "low", "blurb": ""}
            for k in ("backwardation","ts_flattening","exhaustion","double_floor","divergence")}
    for k in active: base[k]["active"] = True
    return base

def test_backwardation_takes_precedence_as_bounce():
    rec = build_recommendation(_sigs(["backwardation", "exhaustion"]))
    assert rec["stance"] == "buy_the_bounce"

def test_flattening_leans_puts():
    rec = build_recommendation(_sigs(["ts_flattening"]))
    assert rec["stance"] == "lean_puts"

def test_neutral_when_nothing_active():
    rec = build_recommendation(_sigs([]))
    assert rec["stance"] == "neutral"

def test_report_has_required_keys():
    rep = compute_report(_sigs(["exhaustion"]),
                         curve={"vix":30,"vvix":110,"vix9d":28,"vix3m":26,"vix6m":25},
                         evidence={"signals":{"exhaustion":{"hit_rate":0.6,"timing_median":5,
                            "timing_p25":3,"timing_p75":8,"suggested_dte":13,"timing_cdf":[0.1]*21,
                            "fwd_spy_5":0.009,"fwd_vix_5":-0.07,"n":91}}})
    for k in ("regime_label","recommendation","outlook","timing","signals","inputs"):
        assert k in rep
    assert rep["timing"]["suggested_dte"] == 13
```

- [ ] **Step 2: Run to verify fail**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vol_regime_advisor.py -v`
Expected: FAIL (build_recommendation/compute_report undefined).

- [ ] **Step 3: Implement**

```python
# append to core/vol_regime_advisor.py

def build_recommendation(signals: Dict[str, dict]) -> dict:
    """Deterministic precedence -> stance + conviction + rationale."""
    def on(k): return signals[k]["active"]
    if on("backwardation"):
        return {"stance": "buy_the_bounce", "conviction": "high",
                "rationale": "Backwardation: spike is present but historically fades (VIX -8%/5d) "
                             "and SPY recovers (+0.9%/5d). Stress is real — size carefully."}
    if on("exhaustion"):
        return {"stance": "buy_the_bounce", "conviction": "medium",
                "rationale": "Exhaustion: VIX high but VVIX won't confirm — vol fades, SPY bounces."}
    if on("ts_flattening"):
        return {"stance": "lean_puts", "conviction": "medium",
                "rationale": "Term structure flattening — rising-vol warning; favor downside/puts."}
    if on("double_floor"):
        return {"stance": "neutral", "conviction": "low",
                "rationale": "Floor/complacent — vol is cheap and drifts up slowly; favor owning optionality."}
    return {"stance": "neutral", "conviction": "low",
            "rationale": "No high-confidence signal active."}

def _regime_label(signals: Dict[str, dict]) -> str:
    if signals["backwardation"]["active"]: return "backwardation_stressed"
    if signals["exhaustion"]["active"]: return "exhaustion"
    if signals["double_floor"]["active"]: return "floor_complacent"
    if signals["ts_flattening"]["active"]: return "contango_flattening"
    return "contango_calm"

def _primary_signal(signals: Dict[str, dict]) -> Optional[str]:
    for k in ("backwardation", "exhaustion", "ts_flattening", "double_floor"):
        if signals[k]["active"]: return k
    return None

def compute_report(signals: Dict[str, dict], curve: dict, evidence: dict) -> dict:
    rec = build_recommendation(signals)
    primary = _primary_signal(signals)
    ev_sig = (evidence.get("signals", {}) or {}).get(primary, {}) if primary else {}
    timing = {
        "primary_signal": primary,
        "median_days": ev_sig.get("timing_median"),
        "p25_days": ev_sig.get("timing_p25"),
        "p75_days": ev_sig.get("timing_p75"),
        "suggested_dte": ev_sig.get("suggested_dte"),
        "cdf": ev_sig.get("timing_cdf"),
        "structure_note": _structure_note(rec["stance"], curve.get("vix")),
    }
    outlook = {
        "fwd_spy_5_pct": ev_sig.get("fwd_spy_5"),
        "fwd_vix_5_pct": ev_sig.get("fwd_vix_5"),
        "hit_rate": ev_sig.get("hit_rate"),
        "sample_n": ev_sig.get("n"),
    }
    # attach per-signal hit_rate for the signals panel
    for k, s in signals.items():
        s["hit_rate"] = (evidence.get("signals", {}) or {}).get(k, {}).get("hit_rate")
    return {
        "regime_label": _regime_label(signals),
        "recommendation": rec,
        "outlook": outlook,
        "timing": timing,
        "signals": signals,
        "inputs": curve,
    }

def _structure_note(stance: str, vix: Optional[float]) -> str:
    if stance in ("buy_the_bounce", "lean_calls") and vix and vix >= 22:
        return "VIX is elevated — long single calls face IV crush; a call debit spread or shorter DTE fits better."
    if stance == "lean_puts" and vix and vix < 16:
        return "VIX is low — long puts are relatively cheap; single long puts are reasonable."
    return "Standard long premium is reasonable in this IV regime; mind theta near the suggested DTE."
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vol_regime_advisor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/vol_regime_advisor.py tests/test_vol_regime_advisor.py
git commit -m "feat(vol-advisor): recommendation precedence + report assembly + timing"
```

---

### Task 4: Live wrapper (`get_regime_report`) with CBOE fetch + evidence load

**Files:**
- Modify: `core/vol_regime_advisor.py`
- Test: `tests/test_vol_regime_advisor.py`

- [ ] **Step 1: Add failing test (monkeypatched, no network)**

```python
# append to tests/test_vol_regime_advisor.py
import core.vol_regime_advisor as adv

def test_get_regime_report_uses_injected_history(monkeypatch):
    import pandas as pd
    idx = pd.date_range("2024-01-01", periods=300, freq="B")
    hist = pd.DataFrame({"vix":15.0,"vvix":90.0,"vix3m":18.0,"vix9d":13.0}, index=idx)
    hist.iloc[-1, hist.columns.get_loc("vix")] = 26.0
    hist.iloc[-1, hist.columns.get_loc("vix3m")] = 20.0
    monkeypatch.setattr(adv, "fetch_cboe_history", lambda: hist)
    monkeypatch.setattr(adv, "_live_curve", lambda: {"vix":26.0,"vvix":110.0,"vix9d":24.0,"vix3m":20.0,"vix6m":19.0})
    rep = adv.get_regime_report()
    assert rep["regime_label"] == "backwardation_stressed"
    assert rep["recommendation"]["stance"] == "buy_the_bounce"
```

- [ ] **Step 2: Run to verify fail**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vol_regime_advisor.py::test_get_regime_report_uses_injected_history -v`
Expected: FAIL (fetch_cboe_history/get_regime_report undefined).

- [ ] **Step 3: Implement live wrapper**

```python
# append to core/vol_regime_advisor.py
import logging
logger = logging.getLogger(__name__)
_HISTORY_CACHE = {"date": None, "df": None}

def _read_cboe_csv(sym: str, col: str) -> pd.Series:
    import io
    txt = requests.get(CBOE_HISTORY_URL.format(sym=sym), timeout=10).text
    df = pd.read_csv(io.StringIO(txt))
    df.columns = [c.strip().upper() for c in df.columns]
    d = df.columns[0]
    df[d] = pd.to_datetime(df[d])
    return df[[d, df.columns[-1]]].rename(columns={d: "date", df.columns[-1]: col}).set_index("date")[col]

def fetch_cboe_history() -> pd.DataFrame:
    """Daily VIX/VVIX/VIX3M/VIX9D history from CBOE, cached once per UTC date in-process."""
    today = pd.Timestamp.utcnow().normalize()
    if _HISTORY_CACHE["date"] == today and _HISTORY_CACHE["df"] is not None:
        return _HISTORY_CACHE["df"]
    df = pd.concat([
        _read_cboe_csv("VIX", "vix"), _read_cboe_csv("VVIX", "vvix"),
        _read_cboe_csv("VIX3M", "vix3m"), _read_cboe_csv("VIX9D", "vix9d"),
    ], axis=1).dropna(subset=["vix", "vvix"])
    _HISTORY_CACHE.update(date=today, df=df)
    return df

CBOE_QUOTE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_{sym}.json"

def _cboe_quote(sym: str) -> Optional[float]:
    """Latest value for a CBOE index from the delayed-quotes CDN (~15-min)."""
    try:
        data = (requests.get(CBOE_QUOTE_URL.format(sym=sym), timeout=8).json() or {}).get("data", {})
        for k in ("current_price", "price", "last", "close"):
            v = data.get(k)
            if v is not None and float(v) > 0:
                return float(v)
    except Exception as e:
        logger.debug(f"CBOE quote {sym} failed: {e}")
    return None

def _live_curve() -> dict:
    """Live curve: VIX/VVIX from origin/main's vix_fetcher; 9D/3M/6M from CBOE delayed quotes."""
    from data.vix_fetcher import get_vix_with_source, get_vvix_with_source
    vix, _ = get_vix_with_source()
    vvix, _ = get_vvix_with_source()
    return {"vix": vix, "vvix": vvix,
            "vix9d": _cboe_quote("VIX9D"), "vix3m": _cboe_quote("VIX3M"), "vix6m": _cboe_quote("VIX6M")}

def _load_evidence() -> dict:
    try:
        with open(os.path.normpath(EVIDENCE_PATH)) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"evidence.json unavailable: {e}")
        return {"signals": {}}

def get_regime_report() -> dict:
    """Live report. Never raises; degrades to neutral if data is missing."""
    try:
        hist = fetch_cboe_history()
        curve = _live_curve()
        # ensure today's live curve is the last row so signals reflect intraday-latest
        last = hist.iloc[-1].copy()
        for c in ("vix", "vvix", "vix3m", "vix9d"):
            v = curve.get(c if c != "vix9d" else "vix9d")
            if v: last[c] = v
        hist = pd.concat([hist.iloc[:-1], pd.DataFrame([last], index=[hist.index[-1]])])
        signals = compute_signals(hist)
        rep = compute_report(signals, curve, _load_evidence())
        rep["as_of"] = str(hist.index[-1].date())
        rep["ok"] = True
        return rep
    except Exception as e:
        logger.error(f"get_regime_report failed: {e}")
        return {"ok": False, "regime_label": "unknown",
                "recommendation": {"stance": "neutral", "conviction": "low",
                                   "rationale": "Volatility data temporarily unavailable."},
                "outlook": {}, "timing": {}, "signals": {}, "inputs": {}}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vol_regime_advisor.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add core/vol_regime_advisor.py tests/test_vol_regime_advisor.py
git commit -m "feat(vol-advisor): live get_regime_report (CBOE fetch + evidence load)"
```

---

### Task 5: `GET /api/vix/regime-advisor` endpoint

**Files:**
- Modify: `backend/api/routes/vix_routes.py`
- Test: `tests/test_vix_routes_advisor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_vix_routes_advisor.py
from fastapi.testclient import TestClient
import backend.api.routes.vix_routes as vr

def _app():
    from fastapi import FastAPI
    app = FastAPI(); app.include_router(vr.router); return app

def test_regime_advisor_returns_report(monkeypatch):
    monkeypatch.setattr(vr, "_advisor_report", lambda: {"ok": True, "regime_label": "exhaustion",
        "recommendation": {"stance": "buy_the_bounce"}, "timing": {"suggested_dte": 13},
        "outlook": {}, "signals": {}, "inputs": {}})
    monkeypatch.setattr(vr, "_advisor_live_record", lambda: {"overall_accuracy": None, "n_scored": 0})
    c = TestClient(_app())
    r = c.get("/api/vix/regime-advisor")
    assert r.status_code == 200
    body = r.json()
    assert body["report"]["regime_label"] == "exhaustion"
    assert "evidence" in body and "live_record" in body
```

- [ ] **Step 2: Run to verify fail**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vix_routes_advisor.py -v`
Expected: FAIL (route 404 / helpers undefined).

- [ ] **Step 3: Implement route + helpers**

```python
# add near the other imports in backend/api/routes/vix_routes.py
import json as _json, os as _os

def _advisor_report():
    from core.vol_regime_advisor import get_regime_report
    return get_regime_report()

def _advisor_evidence():
    try:
        p = _os.path.join(_os.path.dirname(__file__), "..", "..", "..",
                          "backtest", "vvix_vix_analysis", "evidence.json")
        with open(_os.path.normpath(p)) as f:
            return _json.load(f)
    except Exception:
        return {"signals": {}}

def _advisor_live_record():
    """Aggregate accuracy from vol_advisor_log. Returns nulls if unavailable."""
    try:
        from database_adapter import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""SELECT COUNT(*) FILTER (WHERE correct IS NOT NULL),
                            AVG(CASE WHEN correct THEN 1.0 ELSE 0.0 END) FILTER (WHERE correct IS NOT NULL),
                            AVG(CASE WHEN in_window THEN 1.0 ELSE 0.0 END) FILTER (WHERE in_window IS NOT NULL)
                     FROM vol_advisor_log""")
        row = c.fetchone(); conn.close()
        return {"n_scored": int(row[0] or 0),
                "overall_accuracy": float(row[1]) if row[1] is not None else None,
                "in_window_rate": float(row[2]) if row[2] is not None else None}
    except Exception:
        return {"n_scored": 0, "overall_accuracy": None, "in_window_rate": None}

@router.get("/regime-advisor")
async def get_regime_advisor():
    return {"report": _advisor_report(),
            "evidence": _advisor_evidence(),
            "live_record": _advisor_live_record()}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vix_routes_advisor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/vix_routes.py tests/test_vix_routes_advisor.py
git commit -m "feat(vol-advisor): GET /api/vix/regime-advisor"
```

---

## PHASE 2 — Forward tracking + scorer

### Task 6: `vol_advisor_log` table

**Files:**
- Modify: `db/config_and_database.py` (add CREATE TABLE near the `vix_term_structure` block)

- [ ] **Step 1: Add the table DDL**

```python
# in db/config_and_database.py, inside the same init function that creates vix_term_structure
    c.execute('''
        CREATE TABLE IF NOT EXISTS vol_advisor_log (
            id SERIAL PRIMARY KEY,
            log_date DATE UNIQUE NOT NULL,
            vix REAL, vvix REAL, vix9d REAL, vix3m REAL, vix6m REAL,
            regime_label TEXT,
            stance TEXT,
            conviction TEXT,
            active_signals JSONB,
            predicted_dir TEXT,
            horizon_days INT,
            window_p75_days INT,
            realized_vix_chg REAL,
            realized_spy_ret REAL,
            event_landed_day INT,
            correct BOOLEAN,
            in_window BOOLEAN,
            scored_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    ''')
```

- [ ] **Step 2: Verify it applies (idempotent)**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -c "from db.config_and_database import *; print('ddl import ok')"`
Expected: prints `ddl import ok` (the function runs at app startup; this just confirms the file imports).

- [ ] **Step 3: Commit**

```bash
git add db/config_and_database.py
git commit -m "feat(vol-advisor): vol_advisor_log table"
```

---

### Task 7: Scorer logic (pure) + tracker module

**Files:**
- Create: `services/vol_advisor_tracker.py`
- Test: `tests/test_vol_advisor_tracker.py`

- [ ] **Step 1: Write failing test (pure scorer)**

```python
# tests/test_vol_advisor_tracker.py
import pandas as pd
from services.vol_advisor_tracker import score_row

def _fwd(vix_path, spy_path):
    idx = pd.date_range("2024-02-01", periods=len(vix_path), freq="B")
    return pd.DataFrame({"vix": vix_path, "spy": spy_path}, index=idx)

def test_buy_the_bounce_correct_when_spy_up_in_window():
    row = {"stance": "buy_the_bounce", "predicted_dir": "spy_up",
           "horizon_days": 5, "window_p75_days": 8, "vix": 30.0, "spy": 500.0}
    fwd = _fwd([30,29,28,27,26,25,24,23], [500,501,503,505,506,507,508,509])
    res = score_row(row, fwd)
    assert res["correct"] is True
    assert res["in_window"] is True
    assert res["event_landed_day"] is not None

def test_lean_puts_incorrect_when_spy_rises():
    row = {"stance": "lean_puts", "predicted_dir": "spy_down",
           "horizon_days": 5, "window_p75_days": 8, "vix": 14.0, "spy": 500.0}
    fwd = _fwd([14,14,14,14,15,15,15,15], [500,502,504,506,508,510,512,514])
    res = score_row(row, fwd)
    assert res["correct"] is False
```

- [ ] **Step 2: Run to verify fail**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vol_advisor_tracker.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement tracker (pure scorer + DB wrappers)**

```python
# services/vol_advisor_tracker.py
"""Forward tracking for the vol regime advisor: snapshot today's call, score matured calls."""
import json
import logging
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)

def score_row(row: dict, fwd: pd.DataFrame) -> dict:
    """Grade one logged recommendation against forward VIX/SPY.
    fwd: rows AFTER the log date (index ascending), columns vix, spy.
    Returns realized_vix_chg, realized_spy_ret, event_landed_day, correct, in_window."""
    horizon = int(row.get("horizon_days") or 5)
    window = int(row.get("window_p75_days") or horizon)
    base_vix = float(row["vix"]); base_spy = float(row["spy"])
    pred = row.get("predicted_dir") or _dir_from_stance(row.get("stance"))

    fwd = fwd.head(max(horizon, window, 21))
    if fwd.empty:
        return {"realized_vix_chg": None, "realized_spy_ret": None,
                "event_landed_day": None, "correct": None, "in_window": None}

    h = min(horizon, len(fwd))
    realized_vix_chg = float(fwd["vix"].iloc[h-1] / base_vix - 1.0)
    realized_spy_ret = float(fwd["spy"].iloc[h-1] / base_spy - 1.0)

    landed = None
    for k in range(1, len(fwd) + 1):
        v = fwd["vix"].iloc[k-1]; p = fwd["spy"].iloc[k-1]
        if pred == "spy_up" and p >= base_spy * 1.005: landed = k; break
        if pred == "spy_down" and p <= base_spy * 0.995: landed = k; break
        if pred == "vol_down" and v <= base_vix * 0.90: landed = k; break
        if pred == "vol_up" and v >= base_vix * 1.20: landed = k; break

    if pred == "spy_up": correct = realized_spy_ret > 0
    elif pred == "spy_down": correct = realized_spy_ret < 0
    elif pred == "vol_down": correct = realized_vix_chg < 0
    elif pred == "vol_up": correct = realized_vix_chg > 0
    else: correct = None

    in_window = (landed is not None and landed <= window)
    return {"realized_vix_chg": realized_vix_chg, "realized_spy_ret": realized_spy_ret,
            "event_landed_day": landed, "correct": bool(correct) if correct is not None else None,
            "in_window": bool(in_window)}

def _dir_from_stance(stance: Optional[str]) -> str:
    return {"buy_the_bounce": "spy_up", "lean_calls": "spy_up",
            "lean_puts": "spy_down"}.get(stance or "", "vol_down")

# ---- DB wrappers (thin; depend on database_adapter + core engine) ----

def snapshot_today(report: dict) -> bool:
    """Insert today's advisor call into vol_advisor_log (idempotent on log_date)."""
    try:
        from database_adapter import get_connection
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        d = datetime.now(ET).date()
        rec = report.get("recommendation", {})
        timing = report.get("timing", {})
        inputs = report.get("inputs", {})
        active = {k: v for k, v in (report.get("signals") or {}).items() if v.get("active")}
        conn = get_connection(); c = conn.cursor()
        c.execute("""
            INSERT INTO vol_advisor_log
              (log_date, vix, vvix, vix9d, vix3m, vix6m, regime_label, stance, conviction,
               active_signals, predicted_dir, horizon_days, window_p75_days)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (log_date) DO NOTHING
        """, (d, inputs.get("vix"), inputs.get("vvix"), inputs.get("vix9d"),
              inputs.get("vix3m"), inputs.get("vix6m"), report.get("regime_label"),
              rec.get("stance"), rec.get("conviction"), json.dumps(active),
              _dir_from_stance(rec.get("stance")), timing.get("median_days"),
              timing.get("p75_days")))
        conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.error(f"snapshot_today failed: {e}")
        return False

def score_matured() -> int:
    """Score all unscored rows whose horizon has fully elapsed. Returns # scored."""
    try:
        from database_adapter import get_connection
        from core.vol_regime_advisor import fetch_cboe_history
        from data.unified_data_provider import get_data_provider
        hist = fetch_cboe_history()
        spy = _spy_history()
        conn = get_connection(); c = conn.cursor()
        c.execute("""SELECT id, log_date, vix, spy_close, stance, predicted_dir,
                            horizon_days, window_p75_days FROM (
                       SELECT l.*, NULL::real AS spy_close FROM vol_advisor_log l
                     ) q WHERE scored_at IS NULL ORDER BY log_date""")
        # NOTE: spy close is taken from spy history by date below
        rows = c.fetchall()
        scored = 0
        for r in rows:
            rid, log_date = r[0], r[1]
            base_vix = r[2]
            if log_date not in spy.index: 
                continue
            base_spy = float(spy.loc[log_date])
            fwd_idx = hist.index[hist.index > pd.Timestamp(log_date)]
            if len(fwd_idx) < (r[6] or 5):
                continue  # not matured yet
            fwd = pd.DataFrame({
                "vix": hist.loc[fwd_idx, "vix"].values,
                "spy": [float(spy.loc[d]) if d in spy.index else float("nan") for d in fwd_idx],
            }, index=fwd_idx).dropna()
            res = score_row({"stance": r[4], "predicted_dir": r[5], "horizon_days": r[6],
                             "window_p75_days": r[7], "vix": base_vix, "spy": base_spy}, fwd)
            c.execute("""UPDATE vol_advisor_log SET realized_vix_chg=%s, realized_spy_ret=%s,
                         event_landed_day=%s, correct=%s, in_window=%s, scored_at=NOW()
                         WHERE id=%s""",
                      (res["realized_vix_chg"], res["realized_spy_ret"], res["event_landed_day"],
                       res["correct"], res["in_window"], rid))
            scored += 1
        conn.commit(); conn.close()
        return scored
    except Exception as e:
        logger.error(f"score_matured failed: {e}")
        return 0

def _spy_history() -> pd.Series:
    """Daily SPY closes for scoring, from Yahoo chart API (keyless)."""
    import requests
    j = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/SPY"
                     "?period1=1136073600&period2=9999999999&interval=1d",
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
    r = j["chart"]["result"][0]
    ts = pd.to_datetime(r["timestamp"], unit="s").normalize()
    s = pd.Series(r["indicators"]["adjclose"][0]["adjclose"], index=ts).dropna()
    s.index = s.index.date
    return s[~pd.Index(s.index).duplicated(keep="last")]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vol_advisor_tracker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/vol_advisor_tracker.py tests/test_vol_advisor_tracker.py
git commit -m "feat(vol-advisor): forward tracker — pure scorer + snapshot/score DB wrappers"
```

---

### Task 8: Collector job (daily snapshot + score)

**Files:**
- Modify: `data/automated_data_collector.py`

- [ ] **Step 1: Add the run function (after `run_gamma_daily_summary`)**

```python
# data/automated_data_collector.py
def run_vol_advisor():
    """Snapshot today's vol-regime recommendation and score matured ones -> vol_advisor_log"""
    if not is_after_market_close():
        return
    print(f"🌪️ Vol Regime Advisor - {datetime.now(CENTRAL_TZ).strftime('%H:%M:%S')}")
    try:
        from core.vol_regime_advisor import get_regime_report
        from services.vol_advisor_tracker import snapshot_today, score_matured
        report = get_regime_report()
        snapped = snapshot_today(report)
        scored = score_matured()
        print(f"  ✅ vol_advisor_log (snapshot={'ok' if snapped else 'skip'}, scored={scored})")
        log_collection('vol_advisor', 'vol_advisor_log', True)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ❌ vol_advisor failed: {e}\n{tb}")
        log_collection('vol_advisor', 'vol_advisor_log', False, str(e), tb)
```

- [ ] **Step 2: Register it in `setup_schedule()` (END OF DAY block)**

```python
    schedule.every(5).minutes.do(run_vol_advisor)          # vol_advisor_log (NEW)
```

- [ ] **Step 3: Verify import + scheduler builds**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -c "import data.automated_data_collector as a; a.setup_schedule(); print('schedule ok')"`
Expected: prints the schedule banner then `schedule ok` (no exceptions).

- [ ] **Step 4: Commit**

```bash
git add data/automated_data_collector.py
git commit -m "feat(vol-advisor): daily collector snapshot + scorer job"
```

---

### Task 9: `GET /api/vix/regime-advisor/history` + wire live_record

**Files:**
- Modify: `backend/api/routes/vix_routes.py`
- Test: `tests/test_vix_routes_advisor.py`

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_vix_routes_advisor.py
def test_regime_advisor_history(monkeypatch):
    monkeypatch.setattr(vr, "_advisor_history", lambda days: [
        {"log_date": "2026-05-20", "stance": "buy_the_bounce", "correct": True, "in_window": True}])
    c = TestClient(_app())
    r = c.get("/api/vix/regime-advisor/history?days=30")
    assert r.status_code == 200
    assert r.json()["rows"][0]["correct"] is True
```

- [ ] **Step 2: Run to verify fail**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vix_routes_advisor.py::test_regime_advisor_history -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# add to backend/api/routes/vix_routes.py
def _advisor_history(days: int):
    try:
        from database_adapter import get_connection
        conn = get_connection(); c = conn.cursor()
        c.execute("""SELECT log_date, vix, vvix, regime_label, stance, conviction,
                            predicted_dir, horizon_days, window_p75_days,
                            realized_vix_chg, realized_spy_ret, event_landed_day, correct, in_window
                     FROM vol_advisor_log
                     WHERE log_date >= (CURRENT_DATE - %s::int)
                     ORDER BY log_date DESC""", (days,))
        cols = [d[0] for d in c.description]
        rows = [dict(zip(cols, r)) for r in c.fetchall()]
        for r in rows:
            r["log_date"] = str(r["log_date"])
        conn.close()
        return rows
    except Exception:
        return []

@router.get("/regime-advisor/history")
async def get_regime_advisor_history(days: int = 180):
    return {"rows": _advisor_history(days)}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest tests/test_vix_routes_advisor.py -v`
Expected: PASS (all advisor route tests).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/vix_routes.py tests/test_vix_routes_advisor.py
git commit -m "feat(vol-advisor): GET /api/vix/regime-advisor/history"
```

---

## PHASE 3 — IronForge `/volatility` page

> Frontend lives in `ironforge/webapp/`. Run all frontend commands from there.

### Task 10: Discovery — mirror the `/gex` proxy + chart conventions

**Files:** (read-only)

- [ ] **Step 1: Read the exact wiring of the existing `/gex` page and record it**

```bash
cd /c/Users/lemol/Documents/AlphaGEX
sed -n '1,120p' ironforge/webapp/src/app/gex/page.tsx          # how it fetches AlphaGEX
grep -rn "ALPHAGEX\|API_BASE\|process.env\|fetch(" ironforge/webapp/src/app/gex/ | head
ls ironforge/webapp/src/components | grep -iE "chart|brief|card"
sed -n '1,80p' ironforge/webapp/src/components/BriefingCard.tsx  # styling tokens to match
```
Record into a scratch note: (a) the AlphaGEX base-URL mechanism (env var name or server proxy route), (b) whether the page is a server component using `fetch(..., {cache:'no-store'})` or a client component, (c) the recharts wrapper/colors used. **Use these in Tasks 11-15 in place of `<<API_BASE>>` and to match styling.**

- [ ] **Step 2: Confirm dev/test run**

```bash
cd ironforge/webapp && npm run test -- --run 2>&1 | tail -5
```
Expected: vitest runs (some suite passes/exists). If deps missing: `npm install` first.

---

### Task 11: Data fetch helper + types

**Files:**
- Create: `ironforge/webapp/src/lib/volAdvisor.ts`
- Test: `ironforge/webapp/src/lib/volAdvisor.test.ts`

- [ ] **Step 1: Write failing test**

```ts
// ironforge/webapp/src/lib/volAdvisor.test.ts
import { describe, it, expect, vi } from "vitest";
import { fetchAdvisor } from "./volAdvisor";

describe("fetchAdvisor", () => {
  it("parses report + evidence + live_record", async () => {
    const payload = { report: { regime_label: "exhaustion", recommendation: { stance: "buy_the_bounce" },
      timing: { suggested_dte: 13 }, outlook: {}, signals: {}, inputs: {} },
      evidence: { signals: {} }, live_record: { overall_accuracy: 0.6, n_scored: 10 } };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => payload }) as any;
    const out = await fetchAdvisor();
    expect(out.report.regime_label).toBe("exhaustion");
    expect(out.live_record.n_scored).toBe(10);
  });
});
```

- [ ] **Step 2: Run to verify fail**

```bash
cd ironforge/webapp && npx vitest run src/lib/volAdvisor.test.ts
```
Expected: FAIL (module not found).

- [ ] **Step 3: Implement (use the API base mechanism recorded in Task 10 for `<<API_BASE>>`)**

```ts
// ironforge/webapp/src/lib/volAdvisor.ts
export type Stance = "lean_puts" | "lean_calls" | "neutral" | "buy_the_bounce";

export interface AdvisorSignal { active: boolean; value: number; confidence: string; blurb: string; hit_rate: number | null; }
export interface AdvisorReport {
  regime_label: string;
  recommendation: { stance: Stance; conviction: string; rationale: string };
  outlook: { fwd_spy_5_pct?: number; fwd_vix_5_pct?: number; hit_rate?: number; sample_n?: number };
  timing: { primary_signal?: string | null; median_days?: number; p25_days?: number; p75_days?: number;
            suggested_dte?: number; cdf?: number[]; structure_note?: string };
  signals: Record<string, AdvisorSignal>;
  inputs: { vix?: number; vvix?: number; vix9d?: number; vix3m?: number; vix6m?: number };
  as_of?: string; ok?: boolean;
}
export interface AdvisorEvidence { signals: Record<string, any>; as_of?: string; }
export interface AdvisorLiveRecord { overall_accuracy: number | null; n_scored: number; in_window_rate?: number | null; }
export interface AdvisorPayload { report: AdvisorReport; evidence: AdvisorEvidence; live_record: AdvisorLiveRecord; }

// <<API_BASE>>: replace with the env var / proxy mechanism the /gex page uses (recorded in Task 10).
const API_BASE = process.env.NEXT_PUBLIC_ALPHAGEX_API ?? "";

export async function fetchAdvisor(): Promise<AdvisorPayload> {
  const r = await fetch(`${API_BASE}/api/vix/regime-advisor`, { cache: "no-store" });
  if (!r.ok) throw new Error(`advisor fetch failed: ${r.status}`);
  return r.json();
}
export async function fetchAdvisorHistory(days = 180): Promise<{ rows: any[] }> {
  const r = await fetch(`${API_BASE}/api/vix/regime-advisor/history?days=${days}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`advisor history failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step 4: Run to verify pass**

```bash
cd ironforge/webapp && npx vitest run src/lib/volAdvisor.test.ts
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/lib/volAdvisor.ts ironforge/webapp/src/lib/volAdvisor.test.ts
git commit -m "feat(vol-advisor): IronForge advisor fetch helper + types"
```

---

### Task 12: Presentational components — RecommendationCard, SignalsPanel

**Files:**
- Create: `ironforge/webapp/src/components/vol/RecommendationCard.tsx`
- Create: `ironforge/webapp/src/components/vol/SignalsPanel.tsx`
- Test: `ironforge/webapp/src/components/vol/RecommendationCard.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// ironforge/webapp/src/components/vol/RecommendationCard.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RecommendationCard } from "./RecommendationCard";

describe("RecommendationCard", () => {
  it("renders stance and target DTE", () => {
    render(<RecommendationCard
      recommendation={{ stance: "buy_the_bounce", conviction: "medium", rationale: "x" }}
      timing={{ median_days: 5, p25_days: 3, p75_days: 8, suggested_dte: 13, structure_note: "n" }} />);
    expect(screen.getByText(/Buy the bounce/i)).toBeTruthy();
    expect(screen.getByText(/13/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify fail**

```bash
cd ironforge/webapp && npx vitest run src/components/vol/RecommendationCard.test.tsx
```
Expected: FAIL (module not found). (If `@testing-library/react` is absent, mirror whatever the repo's existing component tests use — check Task 10 output — and adjust imports.)

- [ ] **Step 3: Implement components (match BriefingCard styling tokens recorded in Task 10)**

```tsx
// ironforge/webapp/src/components/vol/RecommendationCard.tsx
import React from "react";
import type { AdvisorReport } from "../../lib/volAdvisor";

const STANCE_LABEL: Record<string, string> = {
  buy_the_bounce: "Buy the bounce", lean_calls: "Lean calls",
  lean_puts: "Lean puts", neutral: "Neutral", unknown: "—",
};

export function RecommendationCard({ recommendation, timing }:
  { recommendation: AdvisorReport["recommendation"]; timing: AdvisorReport["timing"]; }) {
  const stance = recommendation?.stance ?? "neutral";
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950 p-5">
      <div className="text-xs uppercase tracking-widest text-neutral-500">Recommendation</div>
      <div className="mt-1 text-2xl font-semibold text-neutral-100">{STANCE_LABEL[stance]}</div>
      <div className="text-sm text-neutral-400">conviction: {recommendation?.conviction ?? "—"}</div>
      <p className="mt-3 text-sm leading-relaxed text-neutral-300">{recommendation?.rationale}</p>
      {timing?.suggested_dte != null && (
        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><div className="text-neutral-500">Expected window</div>
            <div className="text-neutral-200">{timing.p25_days}–{timing.p75_days} trading days
              {timing.median_days != null ? ` (median ${timing.median_days})` : ""}</div></div>
          <div><div className="text-neutral-500">Target expiration</div>
            <div className="text-neutral-200">~{timing.suggested_dte} DTE</div></div>
        </div>
      )}
      {timing?.structure_note && <p className="mt-3 text-xs text-neutral-500">{timing.structure_note}</p>}
    </section>
  );
}
```

```tsx
// ironforge/webapp/src/components/vol/SignalsPanel.tsx
import React from "react";
import type { AdvisorSignal } from "../../lib/volAdvisor";

const NAMES: Record<string, string> = {
  backwardation: "Backwardation", ts_flattening: "TS flattening",
  exhaustion: "Exhaustion", double_floor: "Double floor", divergence: "VVIX divergence",
};

export function SignalsPanel({ signals }: { signals: Record<string, AdvisorSignal> }) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950 p-5">
      <div className="text-xs uppercase tracking-widest text-neutral-500">Signals</div>
      <ul className="mt-3 space-y-2">
        {Object.entries(signals).map(([key, s]) => (
          <li key={key} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2">
              <span className={`inline-block h-2 w-2 rounded-full ${s.active ? "bg-emerald-400" : "bg-neutral-700"}`} />
              <span className="text-neutral-200">{NAMES[key] ?? key}</span>
              {s.confidence === "low" && <span className="text-[10px] text-amber-500">low-conf</span>}
            </span>
            <span className="text-neutral-400">
              {s.hit_rate != null ? `${Math.round(s.hit_rate * 100)}% hit` : "—"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 4: Run to verify pass**

```bash
cd ironforge/webapp && npx vitest run src/components/vol/RecommendationCard.test.tsx
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/components/vol/
git commit -m "feat(vol-advisor): RecommendationCard + SignalsPanel"
```

---

### Task 13: Charts — TermStructureCurve, VixVvixOverlay, TimingChart (recharts)

**Files:**
- Create: `ironforge/webapp/src/components/vol/TermStructureCurve.tsx`
- Create: `ironforge/webapp/src/components/vol/TimingChart.tsx`
- Test: `ironforge/webapp/src/components/vol/charts.test.tsx`

- [ ] **Step 1: Write failing test (smoke render)**

```tsx
// ironforge/webapp/src/components/vol/charts.test.tsx
import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TermStructureCurve } from "./TermStructureCurve";
import { TimingChart } from "./TimingChart";

describe("vol charts", () => {
  it("term structure renders without throwing", () => {
    const { container } = render(<TermStructureCurve inputs={{ vix9d: 13, vix: 15, vix3m: 18, vix6m: 21 }} />);
    expect(container).toBeTruthy();
  });
  it("timing chart renders cdf", () => {
    const { container } = render(<TimingChart cdf={Array.from({length:21},(_,i)=>i/21)} p75={8} />);
    expect(container).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify fail**

```bash
cd ironforge/webapp && npx vitest run src/components/vol/charts.test.tsx
```
Expected: FAIL (modules not found).

- [ ] **Step 3: Implement (recharts 2.13)**

```tsx
// ironforge/webapp/src/components/vol/TermStructureCurve.tsx
import React from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import type { AdvisorReport } from "../../lib/volAdvisor";

export function TermStructureCurve({ inputs }: { inputs: AdvisorReport["inputs"] }) {
  const data = [
    { t: "9D", v: inputs.vix9d }, { t: "30D", v: inputs.vix },
    { t: "3M", v: inputs.vix3m }, { t: "6M", v: inputs.vix6m },
  ].filter(d => d.v != null);
  const backwardation = (inputs.vix ?? 0) > (inputs.vix3m ?? Infinity);
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950 p-5">
      <div className="text-xs uppercase tracking-widest text-neutral-500">
        Term structure {backwardation ? "— BACKWARDATION" : "— contango"}
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="#262626" strokeDasharray="3 3" />
            <XAxis dataKey="t" stroke="#737373" fontSize={11} />
            <YAxis stroke="#737373" fontSize={11} domain={["auto", "auto"]} />
            <Tooltip contentStyle={{ background: "#0a0a0a", border: "1px solid #404040" }} />
            <Line type="monotone" dataKey="v" stroke={backwardation ? "#f87171" : "#34d399"}
                  strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
```

```tsx
// ironforge/webapp/src/components/vol/TimingChart.tsx
import React from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, CartesianGrid } from "recharts";

export function TimingChart({ cdf, p75 }: { cdf?: number[]; p75?: number }) {
  if (!cdf || cdf.length === 0) return null;
  const data = cdf.map((p, i) => ({ day: i + 1, p: Math.round(p * 100) }));
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950 p-5">
      <div className="text-xs uppercase tracking-widest text-neutral-500">
        When the move lands — cumulative probability by trading day
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="#262626" strokeDasharray="3 3" />
            <XAxis dataKey="day" stroke="#737373" fontSize={11} />
            <YAxis stroke="#737373" fontSize={11} domain={[0, 100]} unit="%" />
            <Tooltip contentStyle={{ background: "#0a0a0a", border: "1px solid #404040" }} />
            {p75 != null && <ReferenceLine x={p75} stroke="#fbbf24" strokeDasharray="4 4"
                            label={{ value: "target", fill: "#fbbf24", fontSize: 10 }} />}
            <Area type="monotone" dataKey="p" stroke="#60a5fa" fill="#1e3a8a" fillOpacity={0.4} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run to verify pass**

```bash
cd ironforge/webapp && npx vitest run src/components/vol/charts.test.tsx
```
Expected: PASS. (If recharts needs a ResizeObserver polyfill under jsdom, add `globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} }` to the test setup — check whether the repo already has one from Task 10.)

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/components/vol/
git commit -m "feat(vol-advisor): term-structure + timing charts"
```

---

### Task 14: Historical accuracy table + live track record + page assembly

**Files:**
- Create: `ironforge/webapp/src/components/vol/EvidenceTable.tsx`
- Create: `ironforge/webapp/src/components/vol/LiveTrackRecord.tsx`
- Create: `ironforge/webapp/src/app/volatility/page.tsx`

- [ ] **Step 1: Implement EvidenceTable**

```tsx
// ironforge/webapp/src/components/vol/EvidenceTable.tsx
import React from "react";
const ROWS = ["backwardation","ts_flattening","exhaustion","double_floor","divergence"] as const;
const LABEL: Record<string,string> = { backwardation:"Backwardation", ts_flattening:"TS flattening",
  exhaustion:"Exhaustion", double_floor:"Double floor", divergence:"VVIX divergence" };
const pct = (x:number|undefined) => x==null ? "—" : `${(x*100).toFixed(1)}%`;

export function EvidenceTable({ evidence }: { evidence: { signals: Record<string, any> } }) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950 p-5 overflow-x-auto">
      <div className="text-xs uppercase tracking-widest text-neutral-500">Historical accuracy (2006–2026)</div>
      <table className="mt-3 w-full text-sm">
        <thead><tr className="text-neutral-500 text-left">
          <th className="py-1 pr-4">Signal</th><th>N</th><th>Hit rate</th>
          <th>Fwd VIX 5d</th><th>Fwd SPY 5d</th><th>Median timing</th></tr></thead>
        <tbody>
          {ROWS.map(k => { const s = evidence.signals?.[k] ?? {}; return (
            <tr key={k} className="border-t border-neutral-900 text-neutral-200">
              <td className="py-1 pr-4">{LABEL[k]}</td><td>{s.n ?? "—"}</td>
              <td>{pct(s.hit_rate)}</td><td>{pct(s.fwd_vix_5)}</td>
              <td>{pct(s.fwd_spy_5)}</td><td>{s.timing_median != null ? `${s.timing_median}d` : "—"}</td>
            </tr>); })}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-neutral-600">VVIX divergence is shown for completeness; the study found it statistically insignificant.</p>
    </section>
  );
}
```

- [ ] **Step 2: Implement LiveTrackRecord**

```tsx
// ironforge/webapp/src/components/vol/LiveTrackRecord.tsx
import React from "react";
import type { AdvisorLiveRecord } from "../../lib/volAdvisor";

export function LiveTrackRecord({ record, rows }:
  { record: AdvisorLiveRecord; rows: any[] }) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950 p-5 overflow-x-auto">
      <div className="text-xs uppercase tracking-widest text-neutral-500">Live track record (since launch)</div>
      <div className="mt-2 text-sm text-neutral-300">
        {record.n_scored > 0
          ? <>Accuracy <span className="text-neutral-100 font-semibold">
              {Math.round((record.overall_accuracy ?? 0) * 100)}%</span> over {record.n_scored} scored calls
              {record.in_window_rate != null && <> · in-window {Math.round(record.in_window_rate * 100)}%</>}</>
          : <span className="text-neutral-500">No scored calls yet — accruing daily.</span>}
      </div>
      {rows?.length > 0 && (
        <table className="mt-3 w-full text-sm">
          <thead><tr className="text-neutral-500 text-left"><th className="py-1 pr-4">Date</th>
            <th>Stance</th><th>SPY 5d</th><th>Result</th><th>In window</th></tr></thead>
          <tbody>{rows.slice(0,20).map((r,i)=>(
            <tr key={i} className="border-t border-neutral-900 text-neutral-200">
              <td className="py-1 pr-4">{r.log_date}</td><td>{r.stance}</td>
              <td>{r.realized_spy_ret!=null?`${(r.realized_spy_ret*100).toFixed(2)}%`:"—"}</td>
              <td>{r.correct==null?"pending":r.correct?"✓":"✗"}</td>
              <td>{r.in_window==null?"—":r.in_window?"✓":"✗"}</td>
            </tr>))}</tbody>
        </table>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Implement the page (server component; mirror /gex fetch pattern from Task 10)**

```tsx
// ironforge/webapp/src/app/volatility/page.tsx
import React from "react";
import { fetchAdvisor, fetchAdvisorHistory } from "../../lib/volAdvisor";
import { RecommendationCard } from "../../components/vol/RecommendationCard";
import { SignalsPanel } from "../../components/vol/SignalsPanel";
import { TermStructureCurve } from "../../components/vol/TermStructureCurve";
import { TimingChart } from "../../components/vol/TimingChart";
import { EvidenceTable } from "../../components/vol/EvidenceTable";
import { LiveTrackRecord } from "../../components/vol/LiveTrackRecord";

export const dynamic = "force-dynamic";

export default async function VolatilityPage() {
  const [payload, history] = await Promise.all([
    fetchAdvisor().catch(() => null),
    fetchAdvisorHistory(180).catch(() => ({ rows: [] })),
  ]);
  if (!payload) return <main className="p-6 text-neutral-400">Volatility data temporarily unavailable.</main>;
  const { report, evidence, live_record } = payload;
  const r = report.inputs ?? {};
  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold text-neutral-100">Volatility Regime</h1>
        <div className="text-sm text-neutral-400">
          VIX {r.vix?.toFixed?.(1) ?? "—"} · VVIX {r.vvix?.toFixed?.(0) ?? "—"}
          {report.as_of && <span className="text-neutral-600"> · {report.as_of}</span>}
        </div>
      </header>
      <RecommendationCard recommendation={report.recommendation} timing={report.timing} />
      <div className="grid gap-4 md:grid-cols-2">
        <TermStructureCurve inputs={report.inputs} />
        <TimingChart cdf={report.timing?.cdf} p75={report.timing?.p75_days} />
      </div>
      <SignalsPanel signals={report.signals} />
      <EvidenceTable evidence={evidence} />
      <LiveTrackRecord record={live_record} rows={history.rows} />
    </main>
  );
}
```

- [ ] **Step 4: Type-check / build**

```bash
cd ironforge/webapp && npx tsc --noEmit && npm run build 2>&1 | tail -15
```
Expected: tsc clean; `next build` completes (the `/volatility` route compiles).

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/components/vol/ ironforge/webapp/src/app/volatility/
git commit -m "feat(vol-advisor): IronForge /volatility page (charts, evidence, live record)"
```

---

### Task 15: Navigation link

**Files:**
- Modify: the IronForge nav component (find via Task 10 / grep)

- [ ] **Step 1: Find the nav and add a link**

```bash
cd /c/Users/lemol/Documents/AlphaGEX
grep -rln "href=\"/gex\"\|/spark\|nav" ironforge/webapp/src/components | head
```
Add an entry pointing to `/volatility` labeled "Volatility", mirroring the existing `/gex` nav item exactly (same component/styling).

- [ ] **Step 2: Build to verify**

```bash
cd ironforge/webapp && npm run build 2>&1 | tail -5
```
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add ironforge/webapp/src/components/
git commit -m "feat(vol-advisor): add /volatility to navigation"
```

---

## PHASE 4 — Daily-brief vol-regime line

### Task 16: Discovery — brief structure

**Files:** (read-only)

- [ ] **Step 1: Read the brief generator + macro ribbon**

```bash
cd /c/Users/lemol/Documents/AlphaGEX
sed -n '1,120p' ironforge/webapp/src/app/api/[bot]/briefs/generate/route.ts
sed -n '1,80p' ironforge/webapp/src/components/BriefingMacroRibbon.tsx
```
Record: where brief text/factors are assembled, and whether the macro ribbon renders server-fetched data or props. Decide the minimal insertion point for one vol-regime line.

---

### Task 17: Add the vol-regime line to the brief

**Files:**
- Modify: `ironforge/webapp/src/components/BriefingMacroRibbon.tsx` (or the brief generate route — per Task 16 finding)
- Test: `ironforge/webapp/src/components/vol/volLine.test.ts`

- [ ] **Step 1: Write failing test for the formatter**

```ts
// ironforge/webapp/src/components/vol/volLine.test.ts
import { describe, it, expect } from "vitest";
import { formatVolLine } from "./volLine";

describe("formatVolLine", () => {
  it("summarizes regime + stance + dte", () => {
    const line = formatVolLine({ regime_label: "exhaustion",
      recommendation: { stance: "buy_the_bounce", conviction: "medium", rationale: "" },
      timing: { suggested_dte: 13, p25_days: 3, p75_days: 8 }, outlook: {}, signals: {}, inputs: {} } as any);
    expect(line).toMatch(/Exhaustion/i);
    expect(line).toMatch(/13 DTE/);
  });
});
```

- [ ] **Step 2: Run to verify fail**

```bash
cd ironforge/webapp && npx vitest run src/components/vol/volLine.test.ts
```
Expected: FAIL.

- [ ] **Step 3: Implement formatter + wire into the ribbon**

```ts
// ironforge/webapp/src/components/vol/volLine.ts
import type { AdvisorReport } from "../../lib/volAdvisor";
const REGIME: Record<string,string> = { backwardation_stressed: "Backwardation (stressed)",
  exhaustion: "Exhaustion", floor_complacent: "Floor / complacent",
  contango_flattening: "Contango, flattening", contango_calm: "Contango (calm)", unknown: "Unknown" };
const STANCE: Record<string,string> = { buy_the_bounce: "lean long / buy the bounce",
  lean_calls: "lean calls", lean_puts: "lean puts", neutral: "neutral" };

export function formatVolLine(report: AdvisorReport): string {
  const regime = REGIME[report.regime_label] ?? report.regime_label;
  const stance = STANCE[report.recommendation?.stance] ?? "neutral";
  const dte = report.timing?.suggested_dte;
  const win = (report.timing?.p25_days != null && report.timing?.p75_days != null)
    ? ` over ${report.timing.p25_days}–${report.timing.p75_days} trading days` : "";
  return `Volatility: ${regime} — ${stance}${dte != null ? `, ~${dte} DTE` : ""}${win}.`;
}
```
Then in `BriefingMacroRibbon.tsx`, fetch the advisor (reuse `fetchAdvisor`) and render `formatVolLine(report)` as one line in the ribbon, styled like the other macro items (per Task 16). Degrade silently if the fetch fails.

- [ ] **Step 4: Run tests + build**

```bash
cd ironforge/webapp && npx vitest run src/components/vol/volLine.test.ts && npm run build 2>&1 | tail -5
```
Expected: test PASS; build OK.

- [ ] **Step 5: Commit**

```bash
git add ironforge/webapp/src/components/
git commit -m "feat(vol-advisor): daily-brief vol-regime line"
```

---

## Final verification

- [ ] **Backend tests green:** `cd /c/Users/lemol/Documents/AlphaGEX && PYTHONIOENCODING=utf-8 python -m pytest backtest/vvix_vix_analysis/test_build_evidence.py tests/test_vol_regime_advisor.py tests/test_vol_advisor_tracker.py tests/test_vix_routes_advisor.py -v`
- [ ] **Frontend tests green + build:** `cd ironforge/webapp && npx vitest run && npm run build`
- [ ] **Live endpoint smoke (network):** `python -c "from core.vol_regime_advisor import get_regime_report; import json; print(json.dumps(get_regime_report(), default=str)[:600])"` → prints a report with a real regime_label + recommendation.
- [ ] **Push branch + open PR:** `git push -u origin claude/vol-regime-advisor` then `gh pr create` (do not merge without sign-off — this adds a live page + a collector job).

## Spec coverage check

- Engine + signals + recommendation → Tasks 2–4 ✓
- Timing & expiration estimator → Task 1 (timing in evidence.json) + Task 3 (surfaced in report) + Task 13 (chart) ✓
- Historical evidence / hit-rate → Task 1 + Task 5 (`evidence` in response) + Task 14 (table) ✓
- Forward tracking + scorer → Tasks 6–8 ✓
- Endpoints → Tasks 5, 9 ✓
- IronForge page (8 sections) → Tasks 11–15 ✓
- Daily-brief line → Tasks 16–17 ✓
- Exhaustion indicator (item #2) → defined in Task 1 + Task 2; primary bullish signal in recommendation ✓
- Informational daily-brief gate (item #1) → Task 17, advisory only ✓
