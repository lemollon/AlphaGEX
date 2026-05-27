# IronForge GEX Profile Page — Design Spec

**Date:** 2026-05-27
**Author:** Claude (with operator)
**Status:** Approved scope (both phases), pending spec review

## Goal

Produce a Trading-Volatility-style **GEX (gamma exposure) profile page inside IronForge**, defaulting to **SPY 0DTE**, matching the reference at `stocks.tradingvolatility.net/gexCharts` (operator's screenshot). The page visualizes net gamma by strike, key gamma levels (flip / call wall / put wall / ±1σ), a positioning/reaction narrative, and supporting flow & skew diagnostics.

## Key Context (why this is a port, not a build)

- The AlphaGEX **main frontend already has a working Trading-Volatility clone** at `frontend/src/app/gex-charts/GexChartsContent.tsx` (~1,770 lines). It renders header metrics, per-strike Net GEX / Call-vs-Put / Intraday-5m charts, flow diagnostics, skew, and a "WHAT IT MEANS" interpretation panel.
- It is powered by a **single backend endpoint**: `GET /api/watchtower/gex-analysis?symbol=&expiration=` (`backend/api/routes/watchtower_routes.py:2440`), which:
  - uses the **live Tradier options chain** during market hours (per-strike gamma, OI, IV, volume),
  - **falls back to the TradingVolatility API after hours** (`fetch_gex_from_trading_volatility`) for the next-day profile,
  - defaults to the **0DTE expiration** for SPY.
- IronForge **already depends on AlphaGEX for GEX** via `ironforge/webapp/src/lib/blaze/gex-client.ts` (env `ALPHAGEX_API_BASE`, default `https://alphagex-api.onrender.com`). So reusing that backend is an established precedent, not a new dependency.

**Data-access conclusion:** No operator credentials, no scraping, no new data source. We reuse the existing endpoint over HTTP.

## Architecture

Two repos-within-the-monorepo are touched:

```
AlphaGEX backend (Python / FastAPI, Render: alphagex-api)
  └─ watchtower_routes.py  → extend /gex-analysis (Phase 2 fields + ?expiration=ALL aggregate)
  └─ watchtower_engine.py  → add positioning-pressure + structure-balance computation

IronForge webapp (Next.js 14 / Render: ironforge-webapp)
  └─ src/app/api/gex/*           → thin proxy routes to AlphaGEX
  └─ src/app/gex/page.tsx        → the themed GEX Profile page (ported + restyled)
  └─ src/components/gex/*         → chart + panel components
  └─ src/components/Nav.tsx       → add "GEX Profile" nav item
```

**Plumbing decision — thin HTTP proxy (chosen).** IronForge adds server-side API routes that forward to AlphaGEX. This reuses all gamma math (no TS re-implementation), inherits the after-hours TradingVolatility fallback, and is an HTTP call — not a code import — so it respects IronForge's "standalone / no AlphaGEX code imports" rule.

IronForge proxy routes (all read-only GET):
- `GET /api/gex/analysis?symbol=SPY&expiration=YYYY-MM-DD|ALL` → `${ALPHAGEX_API_BASE}/api/watchtower/gex-analysis`
- `GET /api/gex/expirations?symbol=SPY` → `${ALPHAGEX_API_BASE}/api/watchtower/symbol-expirations`
- `GET /api/gex/intraday?symbol=SPY` → `${ALPHAGEX_API_BASE}/api/watchtower/intraday-ticks`

Each wraps the upstream fetch in a timeout + single retry (mirror `gex-client.ts` `fetchWithRetry`), returns upstream JSON verbatim, and 502s on upstream failure. `ALPHAGEX_API_BASE` already defaults to the public URL, so **no new env var is required** (but document it).

## Phase 1 — Themed 0DTE GEX Profile (frontend-only, reuses today's backend)

New route `/gex` in the IronForge webapp, added to `Nav.tsx`. Default symbol **SPY**, default expiration **nearest (0DTE)**. Restyled to the IronForge forge dark theme (`forge-bg`, `forge-card`, `fire-divider`), using **recharts** (already an IronForge dependency). Per the operator's "no cheap visuals" rule, drop the lucide icon clutter from the source page; use clean typography and minimal custom glyphs.

Components (ported/adapted from `GexChartsContent.tsx`):

1. **Header metrics bar** — Price, GEX Flip, 30-Day Vol, Call Structure, Net GEX, GEX @ expiry, Rating, Gamma Form. (`data.header`)
2. **Key Gamma Levels box** (matches Image #1's "Resist / Support" block) — top-N strikes by `abs(net_gamma)` above price (resistance) and below price (support), with their gamma magnitudes. Derived client-side from `data.gex_chart.strikes` + `data.levels.price`. *No backend change.*
3. **Net GEX profile chart** — horizontal bar of `net_gamma` per strike with reference lines for Price, GEX Flip, and ±1σ (`data.levels.upper_1sd` / `lower_1sd`). Toggles: **Net GEX**, **Call vs Put**, **Intraday 5m** (the existing three views).
4. **Reaction Framework panel** — restructured from the existing `getMarketInterpretation`: a **Base Case** line + an **Invalidated if** line, derived from gamma regime + price-vs-flip + wall proximity + ±1σ. (Rule-based text, computed client-side; see Reaction Framework rules below.)
5. **Options Flow Diagnostics** (6 cards) and **Skew Measures** — rendered from `data.flow_diagnostics` / `data.skew_measures` as-is.
6. **States** — loading, error, market-closed ("data as of last close"), and empty-strikes guards (per common-mistakes #16: test with no/one/full data).

Auto-refresh: 30s during market hours only (reuse the source page's `isMarketOpen()` gate). All times Central.

## Phase 2 — New backend computation + side-by-side charts

### 2a. Positioning Regime "pressure XX/100"
Add to the `/gex-analysis` response under a new `positioning` block. Computed in `watchtower_engine` from values already available:

- `call_vs_put_pressure` = existing `volume_pressure` (−1..+1).
- `pressure_score` (0..100) = a transparent composite intensity, **explicitly our approximation (not TV's proprietary formula)**:
  `pressure_score = round(100 * clamp(0.5*|volume_pressure| + 0.3*|net_gex_norm| + 0.2*|skew_norm|, 0, 1))`
  where `net_gex_norm` = `clamp(net_gex / NET_GEX_SCALE, -1, 1)` (pick `NET_GEX_SCALE` so typical SPY values land in range; document the constant) and `skew_norm` = `clamp(skew_ratio-derived value, -1, 1)`.
- `regime_label` ∈ {Bullish, Neutral, Bearish} from the sign of the net bullish/bearish score (reuse `rating.net_score`).
- Response shape: `positioning: { regime_label, pressure_score, call_vs_put_pressure, summary }`.
- The spec documents that this is a **named approximation**; it is not represented as TV-identical.

### 2b. Structure Balance (7-Day Horizon)
Add `structure_balance` to the response, computed from the **all-expirations aggregate** (2c) restricted to DTE ≤ 7:

- `resist_gamma` = Σ `abs(net_gamma)` for aggregated strikes **above** spot within +1σ.
- `support_gamma` = Σ `abs(net_gamma)` for aggregated strikes **below** spot within −1σ.
- `balance = (resist_gamma − support_gamma) / (resist_gamma + support_gamma)` (−1..+1; ~0 = Balanced).
- `label` from thresholds (e.g. |balance| < 0.15 → "Balanced", else "Resistance-heavy"/"Support-heavy").
- Response shape: `structure_balance: { balance, label, resist_gamma, support_gamma, horizon_days: 7, summary }`.

### 2c. All-Expirations aggregate (`?expiration=ALL`)
Extend `/gex-analysis` so `expiration=ALL` returns an **aggregate `gex_chart`** summing `net_gamma` per strike across multiple expirations, in addition to the single-expiration chart for the side-by-side view in Image #1.

- **Bounded for cost/latency:** aggregate only the next **N≈8 expirations** (or all with DTE ≤ 14), not the full board — one Tradier chain fetch per expiration is expensive. Document the bound.
- **Short server-side cache** (e.g. 60s TTL keyed by symbol) so repeated/auto-refresh calls don't re-fetch N chains every 30s. This must not interfere with the single-expiration live path.
- Response: when `expiration=ALL`, include `gex_chart_all: { strikes: [...aggregated...], expirations_included: [...], total_net_gamma }` alongside the normal single-expiration `gex_chart` (for SPY's nearest).

### 2d. Frontend wiring
- Render **two charts side-by-side** (Image #1 layout): left = single-expiration (0DTE) Net GEX; right = All-Expirations aggregate. On narrow viewports stack vertically.
- Render the **Positioning Regime** gauge (pressure XX/100 + Bullish/Neutral/Bearish + call-vs-put pressure) and the **Structure Balance** card (balance value + label + horizon).

## Reaction Framework rules (Base Case / Invalidated-if)

Derived from `gamma_form` (regime), price-vs-flip, structure balance, and ±1σ width:

- **POSITIVE regime + price above flip + balanced structure** → Base: "Chop / pin until catalyst — favor premium selling within the ±1σ band." Invalidated if: "Vol shock or strong flow pushes cleanly through the call/put wall."
- **NEGATIVE regime** → Base: "Trend / acceleration risk — favor directional, expect wider range." Invalidated if: "Price reclaims the flip and gamma turns positive."
- **Price below flip** → bias the Base toward downside-acceleration caution.
- Wall proximity (< 0.5%) adds a "watch for rejection/bounce at $X" line.

This is a deterministic mapping (no LLM); text lives client-side so it stays trivially adjustable.

## Files (anticipated)

**AlphaGEX backend**
- `core/watchtower_engine.py` — add `calculate_positioning_pressure(...)`, `calculate_structure_balance(...)`, and the all-expirations aggregation helper.
- `backend/api/routes/watchtower_routes.py` — extend `get_gex_analysis` to populate `positioning`, `structure_balance`, and handle `expiration=ALL` (+ cache).

**IronForge webapp**
- `src/app/api/gex/analysis/route.ts`, `src/app/api/gex/expirations/route.ts`, `src/app/api/gex/intraday/route.ts` — proxies.
- `src/app/gex/page.tsx` — page.
- `src/components/gex/` — `HeaderMetrics.tsx`, `KeyGammaLevels.tsx`, `NetGexChart.tsx`, `ReactionFramework.tsx`, `PositioningRegime.tsx`, `StructureBalance.tsx`, `FlowDiagnostics.tsx`, `SkewMeasures.tsx` (split for isolation/testability).
- `src/components/Nav.tsx` — add "GEX Profile".
- `src/lib/gex/types.ts` — TS types for the analysis payload (port the interfaces from `GexChartsContent.tsx`).

## Testing / Verification

- Backend: unit-test `calculate_positioning_pressure` and `calculate_structure_balance` on synthetic strike sets (balanced, resist-heavy, support-heavy, empty). Verify `expiration=ALL` returns aggregated strikes and respects the bound + cache. `pytest -k "positioning or structure" -v`.
- Frontend: `npx next build` must be green (per IronForge rule: build is the default verification). Manually load `/gex` against the live AlphaGEX endpoint and confirm SPY 0DTE renders header, levels, profile chart, and both Phase-2 panels. Test no-data / market-closed states.
- Guardrails: null-guard every API field (common-mistakes #6), CT timestamps (#5), solid chart backgrounds + y-range covering all data (#16).

## Deployment

- Two services auto-deploy from `main` on Render: `alphagex-api` (backend) and the IronForge webapp. Per the monorepo merge policy and the `ironforge/`-in-scope auto-merge default, merge `claude/ironforge-gex-profile` to `main` once `next build` is green and the page is verified. Backend `/gex-analysis` changes are **additive** (new fields + new `ALL` mode) — no breaking change to existing `/gex-charts` consumers.

## Out of scope / deferred

- Exact 1:1 replication of TradingVolatility's proprietary pressure/structure formulas (we ship documented approximations).
- Full-board (all listed expirations) aggregate — we bound to near-dated for cost; can widen later.
- Persisting IronForge-side GEX history (we read live from AlphaGEX).

## Open risks

- **All-expirations latency**: N Tradier chain fetches per call. Mitigated by the ≤8-expiration bound + 60s cache. If still slow, make the aggregate lazy (only fetch when the right-hand chart is in view).
- **After-hours data shape**: the TradingVolatility fallback path returns a different object than the Tradier path; the Phase-2 fields must degrade gracefully (omit `positioning`/`structure_balance`/`gex_chart_all` when the upstream fallback can't supply them) so the page never crashes after close.
