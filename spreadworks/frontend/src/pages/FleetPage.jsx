import { useState, useMemo } from 'react';
import { Search, AlertTriangle, RefreshCw } from 'lucide-react';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip,
} from 'recharts';
import ReflexSpotlightCard from '../components/bots/ReflexSpotlightCard';
import BotCard, {
  GREEN, RED, AMBER, MUTED, STALE_MS, LABEL_STYLE,
  money, signedMoney, pnlColor, relativeTime, parseTs,
} from '../components/bots/BotCard';
import { BOT_REGISTRY } from '../lib/botRegistry';
import useFleet from '../hooks/useFleet';
import useFleetStats from '../hooks/useFleetStats';
import useMarketHours from '../hooks/useMarketHours';

/* ── NOTE ON SPACING ──────────────────────────────────────────────────
   Padding and margin are set INLINE here rather than with Tailwind spacing
   classes. index.css declares an UNLAYERED reset:

       *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0 }

   Tailwind v4 emits its utilities inside `@layer utilities`, and an unlayered
   rule always beats a layered one no matter the specificity — so every p-*,
   px-*, m-*, mb-* class in this app silently computes to 0 (verified in the
   browser: `px-4` → padding-left 0px, on this page AND on PositionsPage).
   gap-* and grid-cols-* are unaffected, which is why those stay as classes.
   Inline styles outrank the reset, so they're what actually holds here.
   ──────────────────────────────────────────────────────────────────── */

// Cyan brand accent (--color-accent in index.css) — used for the fleet
// equity curve so it reads as "the same app", not a bolted-on chart lib.
const ACCENT = '#22d3ee';

/* ── fleet summary tile ──────────────────────────────────────────── */

function SummaryTile({ label, value, sub, color }) {
  return (
    <div className="rounded-lg sw-glass min-w-0" style={{ padding: '12px 16px' }}>
      <div style={{ ...LABEL_STYLE, fontSize: 10, letterSpacing: '0.10em' }}>{label}</div>
      <div
        className="truncate"
        style={{
          fontFamily: 'JetBrains Mono', fontSize: 22, fontWeight: 700,
          marginTop: 4, color: color || '#e2e8f0',
        }}
      >
        {value}
      </div>
      {sub && (
        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: MUTED, marginTop: 2 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

/* ── skeleton while the first poll lands ─────────────────────────── */

function CardSkeleton() {
  return (
    <div className="sw-glass rounded-xl animate-pulse" style={{ padding: 16, height: 210 }}>
      <div className="flex items-center gap-3">
        <div style={{ width: 34, height: 34, borderRadius: 8, background: 'rgba(148,163,184,0.12)' }} />
        <div className="flex-1">
          <div style={{ height: 11, width: '45%', borderRadius: 4, background: 'rgba(148,163,184,0.14)' }} />
          <div style={{ height: 8, width: '70%', borderRadius: 4, background: 'rgba(148,163,184,0.08)', marginTop: 7 }} />
        </div>
      </div>
      <div style={{ height: 26, width: '50%', borderRadius: 6, background: 'rgba(148,163,184,0.12)', marginTop: 22 }} />
      <div style={{ height: 40, borderRadius: 6, background: 'rgba(148,163,184,0.06)', marginTop: 22 }} />
    </div>
  );
}

/* ── page ────────────────────────────────────────────────────────── */

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'live', label: 'Live' },
  { id: 'paused', label: 'Paused' },
  { id: 'holding', label: 'Holding' },
  { id: 'attention', label: 'Needs attention' },
];

const SORTS = [
  { id: 'today', label: "Today's P&L" },
  { id: 'total', label: 'Total P&L' },
  { id: 'open', label: 'Open positions' },
  { id: 'risk', label: 'At risk' },
  { id: 'dd', label: 'Drawdown' },
  { id: 'name', label: 'Name' },
];

export default function FleetPage() {
  const { bots, loading, error, updatedAt, refetch } = useFleet();
  const { stats, riskState } = useFleetStats();
  const { isOpen } = useMarketHours();
  const [filter, setFilter] = useState('all');
  const [tickerFilter, setTickerFilter] = useState('all');
  const [sort, setSort] = useState('today');
  const [query, setQuery] = useState('');

  // Derived per-bot numbers, computed once so the cards, the sort and the
  // fleet totals can never disagree about what a bot made today.
  const rows = useMemo(() => bots.map(b => {
    const unreal = typeof b.unrealized_pnl === 'number' ? b.unrealized_pnl : 0;
    const realized = typeof b.today_pnl === 'number' ? b.today_pnl : null;
    const start = typeof b.starting_capital === 'number' ? b.starting_capital : null;
    const mtm = typeof b.equity_mtm === 'number'
      ? b.equity_mtm
      : typeof b.equity === 'number' ? b.equity + unreal : null;
    const botStats = stats?.bots?.[b.bot] || null;
    const statsOk = botStats && !botStats.error ? botStats : null;
    const scanAt = b.last_scan_at ? parseTs(b.last_scan_at) : null;
    const scanAgeMs = scanAt && !Number.isNaN(scanAt.getTime()) ? Date.now() - scanAt.getTime() : null;
    return {
      ...b,
      _today: realized == null ? null : realized + unreal,
      _total: start != null && mtm != null ? mtm - start : null,
      _mtm: mtm,
      _name: String(b.display || BOT_REGISTRY[b.bot]?.display || b.bot || ''),
      _stats: botStats,
      _risk: statsOk?.risk?.open_max_loss ?? null,
      _dd: statsOk?.drawdown_pct ?? null,
      _stale: isOpen && scanAgeMs != null && scanAgeMs > STALE_MS,
    };
  }), [bots, stats, isOpen]);

  // Totals cover every bot the API returned, including ones filtered out of
  // view — the header is the book, not the current search.
  const totals = useMemo(() => {
    const ok = rows.filter(r => !r.error);
    const sum = (k) => ok.reduce((a, r) => a + (typeof r[k] === 'number' ? r[k] : 0), 0);
    return {
      today: sum('_today'),
      total: sum('_total'),
      equity: sum('_mtm'),
      open: ok.reduce((a, r) => a + (r.open_positions || 0), 0),
      live: ok.filter(r => r.enabled).length,
      count: rows.length,
      failed: rows.length - ok.length,
    };
  }, [rows]);

  // Every ticker any bot is holding, plus the registry's static answer for the
  // flat ones — the option list for the filter.
  const tickersOf = (r) => {
    const live = stats?.bots?.[r.bot]?.tickers || [];
    if (live.length) return live;
    const reg = BOT_REGISTRY[r.bot]?.ticker;
    return reg && reg !== 'multi' ? [reg] : [];
  };
  const allTickers = useMemo(() => {
    const set = new Set();
    rows.forEach(r => tickersOf(r).forEach(t => set.add(t)));
    return [...set].sort();
  }, [rows, stats]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out = rows.filter(r => {
      if (tickerFilter !== 'all' && !tickersOf(r).includes(tickerFilter)) return false;
      if (filter === 'live' && !r.enabled) return false;
      if (filter === 'paused' && r.enabled) return false;
      if (filter === 'holding' && !(r.open_positions > 0)) return false;
      if (filter === 'attention' && !(r.error || r._stale)) return false;
      if (q) {
        const hay = `${r.bot} ${r._name} ${r.strategy || ''} ${BOT_REGISTRY[r.bot]?.ticker || ''} ${tickersOf(r).join(' ')}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : -Infinity);
    const numZero = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
    return [...out].sort((a, b) => {
      if (sort === 'name') return a._name.localeCompare(b._name);
      if (sort === 'open') return (b.open_positions || 0) - (a.open_positions || 0);
      if (sort === 'total') return num(b._total) - num(a._total);
      if (sort === 'risk') return numZero(b._risk) - numZero(a._risk);
      if (sort === 'dd') return numZero(b._dd) - numZero(a._dd);
      return num(b._today) - num(a._today);
    });
  }, [rows, filter, tickerFilter, sort, query, stats]);

  const riskHeadline = riskState?.headline;
  const riskOff = riskHeadline?.startsWith('RISK-OFF');
  const calmFloor = riskHeadline?.startsWith('CALM FLOOR');

  const fleetEquityCurve = stats?.fleet?.equity_curve || [];
  const concentration = stats?.fleet?.concentration || [];
  const totalConcRisk = concentration.reduce((a, c) => a + (c.open_max_loss || 0), 0);
  const allPaper = stats?.fleet ? stats.fleet.all_paper !== false : true;

  return (
    <div
      className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary bg-bg-base"
      style={{ padding: '20px clamp(16px, 2vw, 24px)' }}
    >
      {/* ── header ── */}
      <div className="flex items-end justify-between gap-3 flex-wrap" style={{ marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.01em', color: '#fff' }}>
            Bot Fleet
          </h1>
          <div style={{ fontSize: 12, color: MUTED, marginTop: 2 }}>
            {loading && !rows.length
              ? 'Loading…'
              : `${totals.count} bots · ${totals.live} live · ${totals.open} open position${totals.open === 1 ? '' : 's'}`}
            {totals.failed > 0 && <span style={{ color: RED }}> · {totals.failed} unavailable</span>}
            {' · '}
            <span style={{ color: allPaper ? MUTED : RED }}>
              {allPaper ? 'all paper accounts — no real money at risk' : 'MIXED — some bots live'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {updatedAt && (
            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED }}>
              updated {relativeTime(updatedAt)}
            </span>
          )}
          <button
            onClick={refetch}
            className="sw-btn-ghost flex items-center gap-1.5"
            style={{ fontSize: 12, padding: '6px 12px' }}
            title="Refresh now"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div
          className="flex items-center gap-2 rounded-lg"
          style={{
            padding: '8px 12px', marginBottom: 16,
            background: 'rgba(251,113,133,0.08)',
            boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.22)',
            fontSize: 12, color: '#fda4af',
          }}
        >
          <AlertTriangle size={14} style={{ flexShrink: 0 }} />
          Couldn't refresh the fleet ({error}). Showing the last good data.
        </div>
      )}

      {/* ── risk banner — only when the market is NOT normal. Display-only:
          the Risk Advisor page it used to link to was removed (stale data,
          Leron's call); riskState itself is live, from useFleetStats(), so
          the banner stays — it just no longer promises a "playbook" page. ── */}
      {riskHeadline && (riskOff || calmFloor) && (
        <div
          className="rounded-lg"
          style={{
            padding: '10px 14px', marginBottom: 16,
            background: riskOff ? 'rgba(251,113,133,0.08)' : 'rgba(52,211,153,0.08)',
            boxShadow: `inset 0 0 0 1px ${riskOff ? 'rgba(251,113,133,0.28)' : 'rgba(52,211,153,0.28)'}`,
            fontSize: 12.5, fontWeight: 600,
            color: riskOff ? '#fda4af' : '#6ee7b7',
          }}
        >
          {riskHeadline}
        </div>
      )}

      {/* ── fleet totals ── */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4" style={{ marginBottom: 16 }}>
        <SummaryTile
          label="Today's P&L"
          value={signedMoney(totals.today)}
          sub="realized + open marks"
          color={pnlColor(totals.today)}
        />
        <SummaryTile
          label="Total P&L"
          value={signedMoney(totals.total)}
          sub="vs starting capital"
          color={pnlColor(totals.total)}
        />
        <SummaryTile label="Fleet equity" value={money(totals.equity)} sub="mark-to-market" />
        <SummaryTile
          label="Live bots"
          value={`${totals.live} / ${totals.count}`}
          sub={`${totals.open} open position${totals.open === 1 ? '' : 's'}`}
        />
      </div>

      {/* ── cross-bot concentration ── */}
      {concentration.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap" style={{ marginBottom: 16 }}>
          {concentration.map(c => {
            const concentrated = totalConcRisk > 0 && (c.open_max_loss / totalConcRisk) > 0.6;
            return (
              <span
                key={c.ticker}
                title={(c.strategies || []).join(', ')}
                style={{
                  fontFamily: 'JetBrains Mono', fontSize: 11, padding: '4px 10px', borderRadius: 9999,
                  color: concentrated ? '#fda4af' : '#c6cbd8',
                  background: concentrated ? 'rgba(251,113,133,0.08)' : 'rgba(148,163,184,0.06)',
                  boxShadow: `inset 0 0 0 1px ${concentrated ? 'rgba(251,113,133,0.35)' : 'rgba(148,163,184,0.15)'}`,
                }}
              >
                {c.ticker} · {c.n_positions} pos · {money(c.open_max_loss)} at risk
                {concentrated ? ' · concentrated' : ''}
              </span>
            );
          })}
        </div>
      )}

      {/* ── fleet equity curve ── */}
      {fleetEquityCurve.length >= 2 && (
        <div className="sw-glass rounded-xl" style={{ padding: 16, marginBottom: 16 }}>
          <div style={{ ...LABEL_STYLE, fontSize: 11, letterSpacing: '0.08em', marginBottom: 8 }}>
            Fleet equity — 30 days
          </div>
          <div style={{ width: '100%', height: 160 }}>
            <ResponsiveContainer>
              <AreaChart data={fleetEquityCurve} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="fleetEquityFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={ACCENT} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="d"
                  tickFormatter={d => d.slice(5)}
                  tick={{ fontSize: 10, fill: MUTED }}
                  interval="preserveStartEnd"
                  minTickGap={40}
                />
                <YAxis
                  tickFormatter={v => '$' + (v / 1000).toFixed(0) + 'k'}
                  tick={{ fontSize: 10, fill: MUTED }}
                  width={44}
                />
                <Tooltip
                  contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 12 }}
                  formatter={v => ['$' + Math.round(v).toLocaleString('en-US'), 'Equity']}
                />
                <Area type="monotone" dataKey="equity" stroke={ACCENT} strokeWidth={1.8} fill="url(#fleetEquityFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── controls ── */}
      <div className="flex items-center gap-2 flex-wrap" style={{ marginBottom: 16 }}>
        <div
          className="flex items-center gap-1 rounded-lg"
          style={{ padding: 4, background: 'rgba(7,16,28,0.55)' }}
        >
          {FILTERS.map(f => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              style={{
                padding: '5px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
                fontSize: 12, fontWeight: 600,
                color: filter === f.id ? '#fff' : '#94a3b8',
                background: filter === f.id ? 'rgba(255,255,255,0.08)' : 'transparent',
                transition: 'all 150ms',
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Ticker filter — "which bots trade SPX" was a 25-card read. */}
        {allTickers.length > 1 && (
          <div
            className="flex items-center gap-1 rounded-lg"
            style={{ padding: 4, background: 'rgba(7,16,28,0.55)' }}
          >
            {['all', ...allTickers].map(t => (
              <button
                key={t}
                onClick={() => setTickerFilter(t)}
                style={{
                  padding: '5px 10px', borderRadius: 6, border: 'none', cursor: 'pointer',
                  fontFamily: 'JetBrains Mono', fontSize: 11, fontWeight: 700,
                  color: tickerFilter === t ? '#fff' : '#94a3b8',
                  background: tickerFilter === t ? 'rgba(255,255,255,0.08)' : 'transparent',
                  transition: 'all 150ms',
                }}
              >
                {t === 'all' ? 'All tickers' : t}
              </button>
            ))}
          </div>
        )}

        <div className="relative">
          <Search
            size={13}
            style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: MUTED }}
          />
          {/* .sw-input / .sw-select are width:100% — pin a width inline or they
              eat the whole flex row. */}
          <input
            className="sw-input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search bots…"
            style={{ padding: '6px 10px 6px 28px', fontSize: 12, width: 180 }}
          />
        </div>

        <select
          className="sw-select"
          value={sort}
          onChange={e => setSort(e.target.value)}
          style={{ fontSize: 12, padding: '6px 10px', width: 'auto', marginLeft: 'auto' }}
          aria-label="Sort bots"
        >
          {SORTS.map(s => (
            <option key={s.id} value={s.id}>Sort: {s.label}</option>
          ))}
        </select>
      </div>

      {/* ── featured — REFLEX is new, has no row/stats data, and isn't
          subject to the filter/sort controls above, so it renders once,
          outside the grid, rather than inside visible.map(...). ── */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" style={{ marginBottom: 16 }}>
        <ReflexSpotlightCard />
      </div>

      {/* ── grid ── */}
      {loading && !rows.length ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      ) : visible.length === 0 ? (
        <div
          className="sw-glass rounded-xl text-center"
          style={{ padding: '56px 16px', fontSize: 13, color: MUTED }}
        >
          {rows.length === 0 ? 'No bots reported by the API.' : 'No bots match this filter.'}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visible.map(row => (
            <BotCard key={row.bot} row={row} botStats={row._stats} isOpen={isOpen} />
          ))}
        </div>
      )}
    </div>
  );
}
