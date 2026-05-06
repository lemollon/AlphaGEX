# Agape Derivatives — Full Trade History + Normalized Performance Chart

**Date:** 2026-05-06
**Scope:** `frontend/src/app/perpetuals-crypto` (the "all" page) and the 10 per-bot pages under `frontend/src/app/agape-{coin}-{perp|futures}`. New backend route under `backend/api/routes/`.
**Goal:** (1) replace today's hardcoded 50-row / 10-row trade tables with paginated, date-filtered "full" trade history on every Agape Derivatives surface; (2) add a normalized multi-bot performance comparison chart to the all page.

---

## Active bots in scope (10)

Source: `ACTIVE_COINS` in `frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx`.

| Bot id | Display | Endpoint slug |
|--------|---------|---------------|
| `eth` | ETH-PERP | `/api/agape-eth-perp` |
| `sol` | SOL-PERP | `/api/agape-sol-perp` |
| `avax` | AVAX-PERP | `/api/agape-avax-perp` |
| `btc` | BTC-PERP | `/api/agape-btc-perp` |
| `xrp` | XRP-PERP | `/api/agape-xrp-perp` |
| `doge` | DOGE-PERP | `/api/agape-doge-perp` |
| `shib_futures` | SHIB-FUT | `/api/agape-shib-futures` |
| `link_futures` | LINK-FUT | `/api/agape-link-futures` |
| `ltc_futures` | LTC-FUT | `/api/agape-ltc-futures` |
| `bch_futures` | BCH-FUT | `/api/agape-bch-futures` |

A central registry mapping `bot_id` → trader/db handle lives alongside the new aggregator route.

---

## Decisions (from brainstorming)

- **Trade history pagination:** default last 30 days + `Load more` cursor pagination + a date-range selector (`7d / 30d / 90d / All / Custom`).
- **Chart normalization (headline):** indexed-to-100 over a window (`7d / 30d / 90d / All`), with a toggle to "% from inception".
- **All-page layout:** keep both surfaces — the cross-bot "Recent Trades" feed AND the per-coin History tab. Both upgrade in place to use the new shared component.
- **Backend approach:** single new aggregator endpoint (`/api/agape-perpetuals/trades`); old per-bot `closed-trades` routes are left untouched at their 50-default for any legacy callers.
- **Chart implementation:** client-side normalization on top of existing per-bot `/equity-curve` endpoints. No new backend route for the chart.

---

## 1. Backend — `/api/agape-perpetuals/trades`

**File:** new `backend/api/routes/agape_perpetuals_trades_routes.py`, registered under the existing `/api/agape-perpetuals` blueprint/router.

**Bot registry:** small dict mapping `bot_id` → existing per-bot trader/db accessor (the same `get_*_trader()` helpers each per-bot route already uses). New bots register here on creation. Reading goes through each bot's `db.get_closed_trades(...)`, NOT direct SQL — preserves per-bot encapsulation.

### Query parameters

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `bots` | csv string | required | e.g. `btc,eth,sol`. `*` = all 10 active. Unknown ids return 400. |
| `since` | ISO-8601 | `now − 30d` if no `before` cursor and not `*=all-time` | Lower bound on `close_time`. |
| `until` | ISO-8601 | none | Upper bound on `close_time`. |
| `before` | opaque base64 cursor | none | Keyset cursor `{close_time, bot_id, position_id}`. When present, overrides `since` for the page boundary; `since` still bounds the overall window. |
| `limit` | int | 100 | Max 500. |

### Response

```json
{
  "trades": [
    {
      "bot_id": "btc",
      "bot_label": "BTC-PERP",
      "position_id": "...",
      "side": "long" | "short",
      "qty": 0.0,
      "entry_price": 0.0,
      "close_price": 0.0,
      "realized_pnl": 0.0,
      "realized_pnl_pct": 0.0,
      "entry_time": "2026-05-01T...Z",
      "close_time": "2026-05-02T...Z",
      "close_reason": "tp" | "sl" | "expiry" | "manual" | ...,
      "max_risk_usd": 0.0
    }
  ],
  "next_cursor": "<opaque>" | null,
  "has_more": true | false,
  "window": { "since": "...", "until": "..." }
}
```

`realized_pnl_pct` = `realized_pnl / max_risk_usd × 100` when `max_risk_usd > 0`, else `realized_pnl / (entry_price × qty) × 100`. Computed server-side so every consumer agrees.

### Implementation

- **Fan-out:** parallel calls to each requested bot's `db.get_closed_trades(since=..., until=..., before=..., limit=limit+1)`. Async via `asyncio.gather` if the bot db layer is async; otherwise `concurrent.futures.ThreadPoolExecutor` with a small pool (10 workers — one per bot).
- **Per-bot db change:** extend each existing `db.get_closed_trades()` with optional `since`, `until`, `before` kwargs. If a per-bot `db` does not accept them yet, the new route's adapter falls back to fetching `limit*2` and filtering in Python — but the spec calls for adding the kwargs to the `db.get_closed_trades` of all 10 bots so the SQL does the work.
- **Merge:** combine per-bot results, sort by `(close_time DESC, bot_id ASC, position_id ASC)` for determinism. Take the first `limit` for the page; if there are more elements available, build `next_cursor` from element `limit` (the next one to be returned) and set `has_more=true`.
- **Cursor format:** base64(JSON `{close_time_iso, bot_id, position_id}`). Stable because each bot's `position_id` is unique within that bot.

### Tests (backend)

- Unknown bot id → 400.
- `bots=btc,eth` returns trades only from those bots, correctly merged, count ≤ limit.
- Cursor round-trip: page 1 + page 2 = page 1+2 in one call (no overlaps, no gaps).
- `since` / `until` bounds respected.
- `bots=*` expands to all 10 active.
- Empty bot results don't crash the merge.

---

## 2. Frontend — shared `<TradeHistoryTable>`

**Files:**
- `frontend/src/components/perpetuals/TradeHistoryTable.tsx`
- `frontend/src/lib/hooks/useAgapePerpTrades.ts` (SWR)

### Hook contract

```ts
useAgapePerpTrades({
  bots: string[],            // ["btc"] or ACTIVE_COINS
  range: '7d' | '30d' | '90d' | 'all' | { since: Date, until: Date },
  pageSize?: number,         // default 100
}) => {
  trades: Trade[];           // accumulated across pages
  hasMore: boolean;
  loadMore: () => void;
  isLoading: boolean;
  isLoadingMore: boolean;
  error?: Error;
  reset: () => void;
}
```

- Internally maintains an array of pages keyed by `(bots, range)`. Range change → discard + refetch from page 1.
- Page 1 has `refreshInterval: 60_000`; subsequent pages do not auto-refresh.
- `reset()` is exposed so the table can recover from an error.

### Component props

```ts
{
  bots: string[];
  showBotColumn?: boolean;          // default = bots.length > 1
  defaultRange?: '7d'|'30d'|'90d'|'all'; // default '30d'
  pageSize?: number;                // default 100
  title?: string;                   // optional section heading
}
```

### UI

- **Top bar:** range chips `7d / 30d / 90d / All / Custom`. `Custom` reveals two date inputs; applying triggers a page-1 refetch.
- **Table columns** (in order):
  `Close Time` · `Bot` (only if `showBotColumn`) · `Side` · `Qty` · `Entry` · `Close` · `PnL ($)` · `PnL (%)` · `Reason`.
  Server-side sort by `close_time DESC` only. Sticky header on scroll.
- **Bottom:** `Load more` button when `hasMore`; shows `Showing N trades` count next to it.
- **States:** loading skeleton on first page; spinner inside button on `Load more`; empty state with a hint to widen the date range; error state with a retry button calling `reset()`.

### Tests (frontend)

- Renders rows from mocked endpoint; asserts column count toggles with `showBotColumn`.
- Clicking `Load more` advances cursor and appends rows without duplicating.
- Range change resets accumulated rows and refetches.
- Custom range submits `since`/`until`.

---

## 3. Wiring on existing pages

### Per-bot pages — 10 files

Each `frontend/src/app/agape-{coin}-{perp|futures}/page.tsx` History tab:

- **Remove** the `useAGAPE{Coin}{Perp|Futures}ClosedTrades(50, ...)` call and its inline 50-row table block.
- **Render** `<TradeHistoryTable bots={['{coin}']} showBotColumn={false} defaultRange="30d" />`.

The bot's per-bot `/closed-trades` route stays in place (other consumers, dashboard summary cards). No backend deletion in this spec.

### All page — `perpetuals-crypto/PerpetualsCryptoContent.tsx`

Two replacements:

1. **Cross-bot "Recent Trades" section** (`AllCoinsRecentTrades`, lines 576–611) →
   `<TradeHistoryTable bots={ACTIVE_COINS} showBotColumn defaultRange="30d" title="Recent Trades — All Bots" />`.
   Drop the per-bot 10-cap fan-out logic; the new aggregator handles it.

2. **Per-coin History tab** (`HistoryTab`, lines 1755–1831) →
   `<TradeHistoryTable bots={[coin]} showBotColumn={false} defaultRange="30d" />`.
   Drop `usePerpClosedTrades(coin, 50)` and the inline table.

`COIN_META`'s endpoint slugs are no longer needed for trade history (still used by equity curve + market charts). Leave them.

---

## 4. Multi-bot performance chart on the all page

**File:** new `frontend/src/components/perpetuals/MultiBotPerpEquityChart.tsx`. Placed in the all-page header area, above the `Recent Trades — All Bots` section and below the portfolio summary card.

### Data source

Per-bot SWR fan-out to existing endpoints — no backend change:

```
/api/agape-{coin}-{perp|futures}/equity-curve?days={window_days}
```

for each of the 10 ACTIVE_COINS. SWR `refreshInterval: 60_000`. `dedupingInterval: 30_000`.

Endpoint already returns:
```
{ equity_curve: [{date, equity}, ...], starting_capital, current_equity, total_pnl, total_return_pct }
```

`days` for `'all'` = 3650 (10 years — effectively unbounded for current data).

### Controls

- **Window selector:** `7d / 30d / 90d / All`. Drives the `days` param sent to each bot.
- **Mode toggle:** `Indexed (100)` (default) ↔ `% from inception`.
- **Bot legend:** click-to-toggle visibility per bot. Persisted in `localStorage` under `agape-perp-chart-hidden-bots`.

### Normalization (client-side)

Given each bot's `equity_curve` filtered to the visible window:

- **Indexed (100):** for each bot, let `base = first equity point inside the window`. If `base <= 0` or no point exists, hide that bot from the chart. Render `equity / base × 100`. All visible lines start at 100.
- **% from inception:** render `(equity − starting_capital) / starting_capital × 100`. Same formula `MultiBotEquityCurveImpl` uses today.

**Date axis:** union of all bots' dates inside the window. Bots that started later than a given date render `null` for those dates — no fake interpolation, the line just begins where the data begins.

### Visual

- Recharts `LineChart` (consistent with existing equity views).
- One color per bot; reuse the brand color map already in `lib/botDisplayNames.ts` if a `agape-{coin}` entry exists, else assign deterministically by index.
- Tooltip shows: date, all visible bots' values at that date sorted descending, and an "outperformer" badge on the top line.
- Header strip below the chart with each bot's small stat: current value (indexed or %), and rank within the visible set.

### Why a new component (not extending `MultiBotEquityCurveImpl`)

`MultiBotEquityCurveImpl` is the platform-wide 21-bot view. The all-page comparison wants:
- A focused 10-bot list driven by `ACTIVE_COINS`, not the platform list.
- An `Indexed (100)` mode the existing component does not support.
- A perpetuals-specific window selector.

Diverging now is cheaper than retrofitting two opinions into one component. If both components grow in parallel, lift shared bits later.

### Tests (frontend)

- Indexed mode: every visible bot's first point in the window equals 100.
- % mode: matches the formula and existing component on overlapping data.
- Window switch refetches with new `days`.
- Legend toggle hides/shows bots and persists across reload.
- Bots with no data inside the window are excluded from the legend (or shown disabled).

---

## Out of scope (explicitly)

- No DB schema changes. No new tables or views.
- No removal/deprecation of per-bot `/closed-trades` routes.
- No PnL recomputation or trade-data backfill — we render whatever each bot's db already stores.
- No risk-adjusted (Sharpe) chart and no "% return per unit of risk" chart for v1. Easy to add later.
- No CSV export. Easy to add later.

---

## Rollout

Single PR (or two — backend + frontend) on a branch off `main`. Verification:

1. Backend tests for the new aggregator pass.
2. Hit `/api/agape-perpetuals/trades?bots=*&limit=100` against a Render preview and confirm shape, cursor round-trip, date filter.
3. Open the all page on the preview and the 10 per-bot pages; check both surfaces show the new component, default 30d, and `Load more` works.
4. Open the new chart, switch modes and windows, and confirm normalization math against a hand-computed bot.
