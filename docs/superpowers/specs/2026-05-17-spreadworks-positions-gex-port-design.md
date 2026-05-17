# SpreadWorks Positions + GEX Profile — visual-direction port

**Date:** 2026-05-17
**Branch:** `claude/positions-gex-mockup-port`
**Continues:** PR #2334 (Builder port). Same approach, two more pages.

## Why

Builder page was ported to canonical mockup vocabulary in PR #2334. Positions and GEX Profile pages still wear the old visual language. This spec brings both to mockup parity in a single PR.

## Scope

### In scope
- Restyle `pages/PositionsPage.jsx`, `components/positions/*` to match `ui_kits/positions/index.html`.
- Restyle `pages/GexProfilePage.jsx` to match `ui_kits/gex-profile/index.html`.
- Add 5 shared utility classes to `index.css` (`.sw-stat-card`, `.sw-stat-value`, `.sw-chart-header`, `.sw-strike-badge`, `.sw-empty-card`, `.sw-chart-legend`).
- Keep all React features. No backend changes.

### Out of scope
- No backend / hook / fetch changes.
- No chart library swap (keep Plotly + Recharts).
- Builder page not touched (already done).

## Section-by-section

1. **Tokens / utilities** — add the 5 new utility classes to `index.css`.
2. **Positions — PortfolioSummary.jsx** — wrap stat cells in `.sw-stat-card` with `.sw-stat-value` for the big mono numbers.
3. **Positions — PositionCard.jsx** — bigger uppercase strike badges (LP/SP/SC/LC) via `.sw-strike-badge`; flatter card with subtle border; action button row visually grouped.
4. **Positions — EmptySlot.jsx** — use `.sw-empty-card` for the prominent "Empty Slot N/10" placeholder.
5. **GEX Profile — page header + symbol bar** — title + subtitle + "Next-Day Profile" badge; symbol bar becomes a separate control strip with search + quick-picks + auto-toggle + refresh + timestamp.
6. **GEX Profile — stat strip** — 6 cards (Price, Net GEX, Flip, Call Wall, Put Wall, Rating) using `.sw-stat-card` + `.sw-stat-value`, with sub-labels under each value (e.g., `$742.51 (+1.42%)`).
7. **GEX Profile — chart headers + legends** — `.sw-chart-header` for the view-toggle row, `.sw-chart-legend` for the inline legend beneath each chart.

## Workflow
- Branch: `claude/positions-gex-mockup-port` (already created).
- One PR. Section-per-commit. Build dist + commit, push, merge.

## Verification
- After deploy, `https://spreadworks-backend.onrender.com/positions` renders with new stat strip + position card vocabulary; existing filter / close / Discord / delete still work.
- `/gex-profile` renders with new header + symbol bar + stat strip + chart legends; symbol switching, auto-refresh, and Discord push still work.
- Builder page (already ported) untouched.
