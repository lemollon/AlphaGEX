# SpreadWorks Builder — visual-direction port to React app

**Date:** 2026-05-17
**Branch:** `claude/builder-mockup-port`
**Owner:** Leron Mollon

## Why

The `SpreadWorks Design System/ui_kits/builder/index.html` mockup is the canonical visual target for the Builder page. The live React app at `https://spreadworks-backend.onrender.com/` shares the design tokens but does not yet adopt the mockup's spacing, typography, sidebar styling, metrics row, chart-header chrome, sliders, or output-panel layout. This spec ports the **visual direction** of the mockup into the existing React components without breaking backend wiring or removing React-only features.

A prior PR (`c523af97 spreadworks: realign frontend to canonical Design System`) handled color-token cleanup. This work picks up where that left off and brings the layout/typography/spacing to mockup parity.

## Scope

### In scope
- Restyle every visible Builder element to match the mockup's vocabulary: top nav, sidebar (all 9 sections), chart header, chart-area frame, sliders, timeframe tabs, output panel (metrics + Greeks + legend), buttons, inputs, status pills.
- Match mockup spacing, typography (Inter for UI + JetBrains Mono with `tabular-nums` for numbers), border weights, radii, hover/focus states.
- Bring tokens to exact mockup parity: `--color-bg-base: #07090f → #050810`; confirm the rest of the palette already matches.
- Keep React extras and restyle them in the same vocabulary: sidebar collapse toggle, LegBreakdown row, PnL Table view, PayoffDiagram overlay, sticky alerts.

### Out of scope
- No backend changes. No new API calls. No data refactor.
- No swap of chart library — keep Lightweight Charts / Recharts as currently wired.
- Positions and GEX Profile pages stay untouched.
- No removal of features that exist in current React but not in the mockup. Restyle, don't delete.

## Files touched

| File | Purpose |
|---|---|
| `spreadworks/frontend/src/index.css` | Token parity (`bg-base` bump); confirm semantic vars |
| `spreadworks/frontend/index.html` | Add Inter + JetBrains Mono Google Fonts link if missing |
| `spreadworks/frontend/src/App.jsx` | NavBar restyle (lines ~83–135), Builder layout class touch-ups |
| `spreadworks/frontend/src/components/StrategyPanel.jsx` | Sidebar sections styling |
| `spreadworks/frontend/src/components/ControlsBar.jsx` | Slider track/thumb, timeframe tabs, status pills |
| `spreadworks/frontend/src/components/MetricsBar.jsx` | 6+4 grid (metrics + Greeks), mono values |
| `spreadworks/frontend/src/components/Legend.jsx` | Line-style swatches matching legend vocabulary |
| `spreadworks/frontend/src/components/LegBreakdown.jsx` | Restyle to sit under metrics without competing |
| `spreadworks/frontend/src/components/ChartArea.jsx` | Chart header (15M label, zoom, live spot tag) |
| `spreadworks/frontend/src/components/CandleChart.jsx` | Gridline subtlety, level-line label style |
| `spreadworks/frontend/src/components/SymbolSelector.jsx` | Collapsed inline-text presentation, keep dropdown affordance |
| `spreadworks/frontend/src/components/Skeleton.jsx` | Flat skeletons, no gradient shimmer |

No new files. No deletions.

## Section-by-section spec

### 1. Tokens (`src/index.css`)

- `--color-bg-base: #050810` (from `#07090f`)
- Confirm and lock:
  - `--color-bg-card: #11151f`
  - `--color-bg-hover: #1a1f2e`
  - `--color-accent: #3b82f6`
  - `--color-sw-green: #22c55e`
  - `--color-sw-red: #ef4444`
  - `--color-sw-yellow: #eab308`
  - `--color-text-primary: #f3f4f6`
  - `--color-text-secondary: #9ca3af`
  - `--color-text-muted: #4b5563`
- Add Inter + JetBrains Mono via Google Fonts in `index.html` head if not already loaded. Wire `--font-ui: 'Inter', system-ui, sans-serif` and `--font-mono: 'JetBrains Mono', ui-monospace, monospace`.

### 2. NavBar (`App.jsx` lines ~83–135)

- 56px height, flat `bg-bg-base`, 1px `border-b border-white/5`.
- Logo mark: 28px rounded-md `bg-accent` with white "S". Wordmark: `Spread` white + `Works` `text-accent` (Inter Black, tracking-tight).
- 3 route tabs as pills (Builder / Positions / GEX Profile). Outline icon ~13px before label. Inactive = subtle hover bg; active = filled `bg-accent` with white text.
- Right side: red-pulsing `EOD Mark in 2h 29m` pill + flat red `Sat May 16` date pill. Both ALL-CAPS 11px, letter-spaced.

### 3. Sidebar — `StrategyPanel.jsx`

- 312px fixed width, scrollable, flat `bg-bg-base` (not card), 1px right border.
- Section headers uppercase 11px `text-text-secondary`, letter-spaced, 16px top padding.
- **Strategy grid:** 5 chips, 2 columns, 8px radius, ~64px tall. Active = filled `bg-accent` + white; inactive = `bg-bg-card` + secondary text, no border.
- **Input Mode:** segmented chip control, active = filled blue.
- **Symbol/Spot:** inline SymbolSelector (still a dropdown affordance) with mono spot price and `±2.2%` range tag in muted gray.
- **PUT SIDE** label colored `text-sw-green`. **CALL SIDE** label colored `text-sw-red`. Inputs themselves stay neutral (`bg-bg-card`, no colored border). Mono digits with `tabular-nums`.
- **Expirations:** DTE chip row (mono integers, calendar icon prefix) + 2 native date inputs styled to match `bg-bg-card`.
- **Contracts:** single numeric `bg-bg-card` input with up/down chevrons.
- **Calculate:** full-width 44px, `bg-accent`, white text, Lucide `Zap` icon. Hover `#2563eb`. Press `translateY(1px)`.
- **Price Alerts:** 3-cell grid (Above/Below dropdown · numeric input · `+` button), all flat.

### 4. Chart header + Chart area (`ChartArea.jsx`, `CandleChart.jsx`)

- Header row: sidebar-collapse toggle (preserved), `15M · Price + Spread Payoff` mono label, magnifier zoom `+/−` buttons, right-aligned live spot price tag (mono, blue if up / red if down).
- Chart frame: no card border, just `bg-bg-base`. Subtle gridlines `white/4`.
- Level-line labels inline: `$742` in yellow on a translucent yellow pill sitting on the line.
- Volume bars at the bottom: green/red 50% opacity.

### 5. ControlsBar (`ControlsBar.jsx`)

- Three sliders stacked: DATE (timeline), RANGE (±%), IV MULT (×1 → ×3). Uppercase labels, mono value to the right.
- Track 3px, gradient `bg-bg-hover → bg-accent` to thumb position. Thumb 14px blue dot with white inner.
- Right side: timeframe segmented tabs (`1m 5m 15m 30m 1h 4h 1d`), active filled blue.
- Below row: market status pill (`Market Closed · Sat May 16`) right-aligned.

### 6. Output panel — `MetricsBar.jsx` + `LegBreakdown.jsx` + `Legend.jsx`

- Top tabs: `Graph / Table`, `P&L $ / %`. Active = filled blue.
- **Metrics grid:** 6 cells in a row — `NET DEBIT · MAX PROFIT · MAX LOSS · CHANCE OF PROFIT · BREAKEVENS · IMPLIED VOL`. Each cell: uppercase 10px label, 18px mono value, sign-explicit (`+1.42%`). `--` placeholder in `text-text-muted` when not yet calculated.
- **Greeks grid:** 4 cells — `Δ DELTA · Γ GAMMA · Θ THETA · N VEGA`. Greek glyph + name on label row, mono value below.
- **LegBreakdown** row beneath: subdued styling, same monospaced columns, doesn't visually compete with the metrics row.
- **Legend** at bottom — line-style swatches per `README.md` canonical legend:
  - Green dashed = Long Strike
  - Red dashed = Short Strike
  - Yellow dashed = GEX Flip
  - Cyan dotted = Call Wall
  - Magenta dotted = Put Wall
  - Orange dash-dot = ±1σ

### 7. Skeleton / loading (`Skeleton.jsx`)

- Flat `bg-bg-hover` blocks. No gradient shimmer (consistent with no-glassmorphism rule).

## Workflow

- Branch: `claude/builder-mockup-port` (already created off `main`).
- Commits: one per section above (tokens → NavBar → Sidebar → Chart → Controls → Output → Skeleton). History stays readable; PR ships them together.
- Each push includes a rebuilt `spreadworks/frontend/dist/` (Render's `buildCommand` is still pip-only as of 2026-05-17; the dist-untrack cleanup blocked on that save). Run `npm install && npm run build` before commit.
- Single PR `#TBD` at the end against `main`. PR body links this spec.

## Verification

After each section ships locally:
1. `npm run build` succeeds with no warnings (other than the existing 500 kB chunk-size hint).
2. `npm run dev` renders the Builder with no console errors.
3. Sidebar inputs accept input and propagate to `useCalculate`.
4. Calculate fills metrics + Greeks + LegBreakdown with real values.

After the whole port lands on Render:
5. `curl -s https://spreadworks-backend.onrender.com | grep -o 'index-[A-Za-z0-9_-]*\.css'` returns a new hash.
6. Browser hard-refresh against the mockup file (`file:///C:/Users/lemol/OneDrive/Desktop/Spreadworks/SpreadWorks Design System/ui_kits/builder/index.html`) — visual parity for nav, sidebar, chart header, metrics row, legend.
7. End-to-end smoke: pick SPY, set strikes, click Calculate, confirm metrics populate and chart overlays payoff.
8. Sidebar collapse toggle still works (React-only feature preserved).
9. PnL Table view toggle still works.

## Non-goals (explicit)

- No new tests. Visual changes only; existing Jest/Playwright tests should still pass — verify with `npm test` after final commit.
- No pixel-perfect typography match (the mockup uses inline browser-default font rendering; React uses Tailwind utilities — small kerning differences are acceptable).
- No mockup-only features removed from React. LegBreakdown, sidebar collapse, table view all stay.
- No Render config changes in this PR. The pending `buildCommand` save fix is tracked separately.

## Risks

- **Backend wiring regression** — careful to not touch `useCandles`, `useGex`, `useCalculate`, `useMarketHours`, or the alerts fetch in App.jsx. Edits are className-only on these touchpoints.
- **Chart library rendering** — restyling chart container or gridlines could disturb Lightweight Charts internal layout. Restyle the WRAPPER first; only touch chart-internal class if necessary.
- **Tailwind v4 @theme** — `@theme` block changes require restarting Vite dev server to take effect. Document this in PR if a contributor stalls.

## Related

- Prior PR: `c523af97` (token alignment) — this work continues from there.
- Memory: [[project-spreadworks-dist-drift-2026-05-17]] — `dist/` must be committed until Render `buildCommand` is fixed.
- Design source: `C:\Users\lemol\OneDrive\Desktop\Spreadworks\SpreadWorks Design System\ui_kits\builder\index.html`
- Brand spec: same folder, `README.md`
