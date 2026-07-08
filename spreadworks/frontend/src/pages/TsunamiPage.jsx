// TSUNAMI — LETF trend bot page.
// Same data + behavior as before (status, comparison chart, book, fills);
// the LOOK now matches the other bot dashboards: themed glyph nameplate,
// sw-glass KPI tiles, branded card chrome. TSUNAMI is stock-only (buys and
// sells shares), so instead of payoff/positions tabs it keeps its own
// centerpiece: the indexed comparison chart plus the share book and fills.
import { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, CartesianGrid,
} from 'recharts';
import { Inbox, LayoutGrid, List, Terminal } from 'lucide-react';
import { API_URL as API_BASE } from '../lib/api';
import BotGlyph from '../components/bots/BotGlyph';

// Page theme — mirrors the BOT_THEME shape in lib/botRegistry.js. TSUNAMI
// isn't a registry bot (own engine + routes) so its theme lives here.
// sky-300 to match the nav menu's pinned TSUNAMI row.
const THEME = {
  glyph:       'wave',
  primary:     '#7dd3fc',
  primarySoft: 'rgba(125,211,252,0.10)',
  primaryRing: 'rgba(125,211,252,0.30)',
  glow:        'rgba(125,211,252,0.18)',
  accentBg:    'linear-gradient(135deg, rgba(125,211,252,0.22) 0%, rgba(125,211,252,0.03) 100%)',
};

// Fixed categorical order — hue follows the ticker, never its rank.
const SERIES_COLOR = {
  TSUNAMI: '#f8fafc', // the system line — near-white, bold
  TSLL: '#22d3ee',
  AMDL: '#f97316',
  NVDL: '#4ade80',
  CONL: '#a78bfa',
  MSTU: '#facc15',
  BITX: '#fb7185',
  ETHU: '#38bdf8',
  IONX: '#c084fc',
  UXRP: '#2dd4bf',
  SPXL: '#60a5fa',
  TQQQ: '#f472b6',
  SBIT: '#fb7185',  // inverses share their asset hue but render dashed
  ETHD: '#38bdf8',
  SMST: '#facc15',
  SPXS: '#60a5fa',
  SQQQ: '#f472b6',
};
const INVERSE = new Set(['SBIT', 'ETHD', 'SMST', 'SPXS', 'SQQQ']);
// Default view: system + the 7 core longs. Everything togglable.
const DEFAULT_ON = new Set(['TSUNAMI', 'TSLL', 'AMDL', 'NVDL', 'CONL', 'MSTU', 'SPXL', 'TQQQ']);

function money(v, { signed = false, decimals = 2 } = {}) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v > 0 ? '+' : v < 0 ? '−' : '';
  const abs = Math.abs(v);
  const str = abs.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  if (signed) return `${sign}$${str}`;
  return v < 0 ? `−$${str}` : `$${str}`;
}

function pct(v, decimals = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v * 100).toFixed(decimals)}%`;
}

/* ── KPI tile — same chrome as BotDashboard's KpiTile ───────────────── */

function KpiTile({ label, value, sub, mono = true, accent }) {
  return (
    <div
      className="px-5 py-4 rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <div
        className={`leading-none ${mono ? 'sw-mono' : ''}`}
        style={{ fontSize: 28, fontWeight: 700, color: accent || 'var(--color-text-primary)' }}
      >
        {value}
      </div>
      <div className="text-[10.5px] uppercase tracking-[0.16em] font-semibold text-text-tertiary mt-3">
        {label}
      </div>
      {sub && (
        <div className="text-[11px] text-text-tertiary mt-1.5 sw-mono">{sub}</div>
      )}
    </div>
  );
}

/* ── Series chip — brand pill, same interaction as before ───────────── */

function Chip({ id, on, held, onClick }) {
  const c = SERIES_COLOR[id] || '#94a3b8';
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full cursor-pointer text-[12px] font-semibold sw-mono transition-all"
      style={{
        color: on ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
        background: on ? 'rgba(148,163,184,0.10)' : 'transparent',
        boxShadow: `inset 0 0 0 1px ${on ? c : 'rgba(100,116,139,0.35)'}`,
        opacity: on ? 1 : 0.7,
      }}
    >
      <span style={{
        width: 14, height: 0, borderTop: `2px ${INVERSE.has(id) ? 'dashed' : 'solid'} ${c}`,
      }} />
      {id}
      {INVERSE.has(id) && (
        <span className="text-[9px] font-bold tracking-wider text-text-secondary">SHORT</span>
      )}
      {held && (
        <span className="text-[9px] font-bold tracking-wider text-sw-green">● HELD</span>
      )}
    </button>
  );
}

/* ── Nameplate header — mirrors BotHeader in BotDashboard ───────────── */

function TsunamiHeader() {
  return (
    <div
      className="px-4 md:px-8 pt-7 pb-6"
      style={{ borderBottom: '1px solid rgba(125,211,252,0.18)' }}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex items-center gap-5 min-w-0">
          {/* Glyph tile */}
          <div
            className="w-16 h-16 rounded-2xl grid place-items-center flex-shrink-0"
            style={{
              background: THEME.accentBg,
              boxShadow: `inset 0 0 0 1px ${THEME.primaryRing}, 0 0 32px -8px ${THEME.glow}`,
              color: THEME.primary,
            }}
          >
            <BotGlyph kind={THEME.glyph} size={32} strokeWidth={1.6} />
          </div>

          {/* Nameplate */}
          <div className="min-w-0">
            <h1
              className="font-black tracking-[0.04em] leading-none text-[28px] md:text-[44px]"
              style={{ color: THEME.primary, textShadow: `0 0 24px ${THEME.glow}` }}
            >
              TSUNAMI
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-2 text-[13.5px] text-text-secondary">
              <span className="font-medium">LETF Trend Engine</span>
              <span className="w-1 h-1 rounded-full bg-text-muted" />
              <span className="sw-mono font-semibold text-white">16 instruments</span>
              <span className="w-1 h-1 rounded-full bg-text-muted" />
              <span className="sw-mono text-text-tertiary">
                stocks only · daily rebalance 14:45 CT
              </span>
            </div>
          </div>
        </div>

        {/* Status badges — no toggle/force-trade: TSUNAMI trades shares on a
            fixed daily rebalance, not on-demand option structures. */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-[11.5px] font-bold tracking-wider uppercase text-sw-yellow bg-sw-yellow-dim ring-1 ring-sw-yellow/30">
            Paper
          </span>
          <span className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-[11.5px] font-bold tracking-wider uppercase text-sw-green bg-sw-green-dim ring-1 ring-sw-green/30">
            <span className="relative inline-flex w-1.5 h-1.5">
              <span className="absolute inset-0 rounded-full animate-ping opacity-60 bg-sw-green" />
              <span className="relative inline-block w-1.5 h-1.5 rounded-full bg-sw-green" />
            </span>
            Enabled
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Card shell — matches the sw-glass card chrome on bot pages ─────── */

function Card({ title, subtitle, children, headerRight }) {
  return (
    <div
      className="rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <div
        className="px-5 py-4 flex flex-wrap items-center justify-between gap-2"
        style={{ borderBottom: '1px solid rgba(125,211,252,0.08)' }}
      >
        <div className="flex flex-wrap items-baseline gap-3">
          <h3 className="text-[14px] font-semibold text-text-primary">{title}</h3>
          {subtitle && <span className="text-[11.5px] text-text-tertiary">{subtitle}</span>}
        </div>
        {headerRight}
      </div>
      {children}
    </div>
  );
}

/* Timeframe windows for BOTH charts (days back from the newest point; ALL = everything).
   INTRADAY is a calendar-day filter (not a day-count) -- it's what shows the intraday marks
   the equity chart now gets every 15 min, on top of the once-daily rebalance point. Matches
   the "Intraday" view the other bot dashboards expose. */
const TIMEFRAMES = [
  { id: 'INTRADAY' },
  { id: '1W', days: 7 },
  { id: '1M', days: 31 },
  { id: '3M', days: 93 },
  { id: 'ALL', days: 0 },
];

function windowPoints(points, tf) {
  if (!points.length) return points;
  if (tf === 'INTRADAY') {
    const lastDay = String(points[points.length - 1].date || points[points.length - 1].ts).slice(0, 10);
    return points.filter(p => String(p.date || p.ts).slice(0, 10) === lastDay);
  }
  const days = TIMEFRAMES.find(t => t.id === tf)?.days || 0;
  if (!days) return points;
  const last = new Date(points[points.length - 1].date || points[points.length - 1].ts);
  const cutoff = new Date(last.getTime() - days * 86400 * 1000);
  return points.filter(p => new Date(p.date || p.ts) >= cutoff);
}

/* Pill-button group — chart view toggle + timeframe filter (same chrome as the chips). */
function PillGroup({ options, value, onChange }) {
  return (
    <div className="inline-flex gap-1 p-0.5 rounded-full" style={{ background: 'rgba(148,163,184,0.08)' }}>
      {options.map(o => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className="px-2.5 py-1 rounded-full text-[11px] font-bold sw-mono cursor-pointer transition-all"
          style={value === o
            ? { color: '#0b1220', background: THEME.primary }
            : { color: 'var(--color-text-tertiary)', background: 'transparent' }}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

/* ── Activity tabs — Positions / Universe / Trade History / Logs ─────
   Mirrors BotDashboard's ActivityTabs pattern. TSUNAMI previously only
   showed currently-HELD names (the Book card); there was no view of the
   full 16-instrument universe, no reason why a name wasn't bought, no
   full trade history (capped at 12 inline), and no logs at all. Backed
   by tsunami_trend_signals (one row per instrument per rebalance cycle,
   added 2026-07-08) via /trend/universe and /trend/logs, plus the
   already-existing /trend/trades for full history. */

function fmtCT(ts, opts = {}) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago', hour: '2-digit', minute: '2-digit',
      hour12: false, ...opts,
    });
  } catch {
    return String(ts);
  }
}

function actionBadgeStyle(action) {
  if (action === 'BUY') {
    return { color: 'var(--color-sw-green)', background: 'var(--color-sw-green-dim)', boxShadow: 'inset 0 0 0 1px rgba(52,211,153,0.30)' };
  }
  if (action === 'SELL') {
    return { color: 'var(--color-sw-red)', background: 'var(--color-sw-red-dim)', boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.30)' };
  }
  if (action === 'NO_SIGNAL' || action === 'NO_QUOTE') {
    return { color: 'var(--color-sw-yellow)', background: 'var(--color-sw-yellow-dim)' };
  }
  return { color: 'var(--color-text-tertiary)', background: 'rgba(148,163,184,0.10)' }; // HOLD / FLAT / null
}

function EmptyState({ children }) {
  return <div className="py-8 text-center text-[12.5px] text-text-tertiary">{children}</div>;
}

function PositionsTabContent({ book }) {
  return (
    <div className="px-5 py-3">
      {book.length === 0 && (
        <EmptyState>All cash — no instrument above its 50-day MA (or first rebalance pending).</EmptyState>
      )}
      {book.map(b => (
        <div
          key={b.letf}
          className="flex items-center justify-between py-2.5 text-[13px] text-text-body"
          style={{ borderBottom: '1px solid rgba(125,211,252,0.06)' }}
        >
          <span className="inline-flex items-center gap-2 font-bold sw-mono"
                style={{ color: SERIES_COLOR[b.letf] || 'var(--color-text-primary)' }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: SERIES_COLOR[b.letf] || '#94a3b8' }} />
            {b.letf}
          </span>
          <span className="sw-mono text-right">
            <span className="block">
              {b.shares} sh <span className="text-text-tertiary">@</span> ${Number(b.avg_cost).toFixed(2)}
            </span>
            {b.unrealized_pnl != null && (
              <span
                className="block text-[11px]"
                style={{ color: b.unrealized_pnl >= 0 ? 'var(--color-sw-green)' : 'var(--color-sw-red)' }}
              >
                {money(b.unrealized_pnl, { signed: true })} unrealized
                {b.last != null && <span className="text-text-tertiary"> · last ${Number(b.last).toFixed(2)}</span>}
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}

function UniverseTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let dead = false;
    fetch(`${API_BASE}/api/tsunami/trend/universe`).then(r => r.json())
      .then(d => { if (!dead) setData(d); })
      .catch(e => { if (!dead) setErr(String(e)); });
    return () => { dead = true; };
  }, []);
  const instruments = data?.instruments || [];

  return (
    <div className="px-5 py-3">
      {err && <div className="text-sw-red text-[12px] mb-2">{err}</div>}
      {!data && !err && <EmptyState>Loading universe…</EmptyState>}
      {data && instruments.length === 0 && <EmptyState>No universe data yet.</EmptyState>}
      {instruments.map(row => (
        <div
          key={row.letf}
          className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5 text-[12.5px] text-text-body sw-mono"
          style={{ borderBottom: '1px solid rgba(125,211,252,0.06)' }}
        >
          <span className="inline-flex items-center gap-2 font-bold" style={{ minWidth: 68, color: SERIES_COLOR[row.letf] || 'var(--color-text-primary)' }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: SERIES_COLOR[row.letf] || '#94a3b8' }} />
            {row.letf}
          </span>
          <span className="text-text-tertiary" style={{ minWidth: 130 }}>
            {row.price != null ? `$${row.price.toFixed(2)}` : '—'}
            {row.ma50 != null && <span className="text-[10.5px]"> · MA50 ${row.ma50.toFixed(2)}</span>}
          </span>
          <span
            className="text-[10.5px] font-bold tracking-wider px-1.5 py-0.5 rounded"
            style={
              row.trending === true
                ? { color: 'var(--color-sw-green)', background: 'var(--color-sw-green-dim)', boxShadow: 'inset 0 0 0 1px rgba(52,211,153,0.30)' }
                : row.trending === false
                ? { color: 'var(--color-text-tertiary)', background: 'rgba(148,163,184,0.10)' }
                : { color: 'var(--color-sw-yellow)', background: 'var(--color-sw-yellow-dim)' }
            }
          >
            {row.trending === true ? 'TRENDING' : row.trending === false ? 'FLAT' : 'NO DATA'}
          </span>
          <span className="text-[10.5px] font-bold tracking-wider px-1.5 py-0.5 rounded" style={actionBadgeStyle(row.action)}>
            {row.action || '—'}
          </span>
          <span className="text-text-tertiary" style={{ minWidth: 90 }}>
            {row.held_shares ?? 0} held
            {row.target_shares != null && row.target_shares !== row.held_shares ? ` → ${row.target_shares} tgt` : ''}
          </span>
          <span className="flex-1 min-w-[160px] text-text-tertiary text-[11.5px]">{row.reason || '—'}</span>
          <span className="text-text-tertiary text-[10.5px]">{row.ts ? fmtCT(row.ts) + ' CT' : ''}</span>
        </div>
      ))}
    </div>
  );
}

function TradeHistoryTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let dead = false;
    fetch(`${API_BASE}/api/tsunami/trend/trades?limit=200`).then(r => r.json())
      .then(d => { if (!dead) setData(d); })
      .catch(e => { if (!dead) setErr(String(e)); });
    return () => { dead = true; };
  }, []);
  const trades = data?.trades || [];

  return (
    <div className="px-5 py-3 max-h-[480px] overflow-y-auto">
      {err && <div className="text-sw-red text-[12px] mb-2">{err}</div>}
      {!data && !err && <EmptyState>Loading trade history…</EmptyState>}
      {data && trades.length === 0 && (
        <EmptyState>No fills yet — first rebalance runs the next trading day at 14:45 CT.</EmptyState>
      )}
      {trades.map((t, i) => (
        <div
          key={i}
          className="flex items-center gap-3 justify-between py-2.5 text-[12.5px] text-text-body sw-mono"
          style={{ borderBottom: '1px solid rgba(125,211,252,0.06)' }}
        >
          <span
            className="text-[10.5px] font-bold tracking-wider px-1.5 py-0.5 rounded"
            style={actionBadgeStyle(t.side)}
          >
            {t.side}
          </span>
          <span className="font-semibold" style={{ color: SERIES_COLOR[t.letf] || 'var(--color-text-primary)' }}>
            {t.letf}
          </span>
          <span>{t.shares} @ ${Number(t.price).toFixed(2)}</span>
          <span className="flex-1 min-w-[120px] text-text-tertiary text-[11.5px]">{t.reason}</span>
          <span className="text-text-tertiary">{String(t.ts).slice(0, 10)}</span>
          <span style={{
            color: t.realized_pnl > 0 ? 'var(--color-sw-green)'
                 : t.realized_pnl < 0 ? 'var(--color-sw-red)'
                 : 'var(--color-text-tertiary)',
          }}>
            {t.realized_pnl != null ? money(t.realized_pnl, { signed: true }) : ''}
          </span>
        </div>
      ))}
    </div>
  );
}

function TsunamiLogsTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let dead = false;
    fetch(`${API_BASE}/api/tsunami/trend/logs?limit=300`).then(r => r.json())
      .then(d => { if (!dead) setData(d); })
      .catch(e => { if (!dead) setErr(String(e)); });
    return () => { dead = true; };
  }, []);
  const logs = data?.logs || [];

  return (
    <div className="px-5 py-3 max-h-[480px] overflow-y-auto">
      {err && <div className="text-sw-red text-[12px] mb-2">{err}</div>}
      {!data && !err && <EmptyState>Loading logs…</EmptyState>}
      {data && logs.length === 0 && <EmptyState>No cycles logged yet.</EmptyState>}
      {logs.map((l, i) => (
        <div
          key={i}
          className="flex items-center gap-3 py-2 text-[12px] sw-mono"
          style={{ borderBottom: '1px solid rgba(125,211,252,0.05)' }}
        >
          <span className="text-text-tertiary" style={{ minWidth: 130 }}>
            {String(l.ts).slice(0, 10)} {fmtCT(l.ts, { second: '2-digit' })}
          </span>
          <span className="font-bold" style={{ minWidth: 60, color: SERIES_COLOR[l.letf] || 'var(--color-text-primary)' }}>
            {l.letf}
          </span>
          <span className="text-[10.5px] font-bold tracking-wider px-1.5 py-0.5 rounded" style={actionBadgeStyle(l.action)}>
            {l.action}
          </span>
          <span className="flex-1 text-text-tertiary">{l.reason}</span>
        </div>
      ))}
    </div>
  );
}

const TSUNAMI_TABS = [
  { id: 'positions', label: 'Positions',     Icon: Inbox },
  { id: 'universe',  label: 'Universe',      Icon: LayoutGrid },
  { id: 'history',   label: 'Trade History', Icon: List },
  { id: 'logs',      label: 'Logs',          Icon: Terminal },
];

function TsunamiTabs({ book, heldCount }) {
  const [tab, setTab] = useState('positions');
  return (
    <div className="rounded-lg sw-glass" style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}>
      <div className="flex items-center gap-1 px-3 pt-3 overflow-x-auto whitespace-nowrap" style={{ borderBottom: '1px solid rgba(125,211,252,0.08)' }}>
        {TSUNAMI_TABS.map(t => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="relative shrink-0 inline-flex items-center gap-2 px-3.5 py-2.5 text-[12.5px] font-semibold transition-colors cursor-pointer"
              style={{ color: active ? THEME.primary : 'var(--color-text-secondary)' }}
            >
              <t.Icon size={13} />
              {t.label}
              {t.id === 'positions' && heldCount > 0 && (
                <span
                  className="sw-mono text-[10px] font-bold px-1.5 py-0.5 rounded-full"
                  style={
                    active
                      ? { background: THEME.primarySoft, color: THEME.primary, boxShadow: `inset 0 0 0 1px ${THEME.primaryRing}` }
                      : { background: 'rgba(255,255,255,0.05)', color: 'var(--color-text-secondary)' }
                  }
                >
                  {heldCount}
                </span>
              )}
              {active && (
                <span className="absolute left-2.5 right-2.5 -bottom-px h-[2px]" style={{ background: THEME.primary }} />
              )}
            </button>
          );
        })}
      </div>
      <div className="min-h-[240px]">
        {tab === 'positions' && <PositionsTabContent book={book} />}
        {tab === 'universe'  && <UniverseTab />}
        {tab === 'history'   && <TradeHistoryTab />}
        {tab === 'logs'      && <TsunamiLogsTab />}
      </div>
    </div>
  );
}

export default function TsunamiPage() {
  const [status, setStatus] = useState(null);
  const [cmp, setCmp] = useState(null);
  const [eq, setEq] = useState(null);
  const [err, setErr] = useState(null);
  const [on, setOn] = useState(DEFAULT_ON);
  const [view, setView] = useState('EQUITY');    // EQUITY | COMPARE
  const [tf, setTf] = useState('ALL');           // INTRADAY | 1W | 1M | 3M | ALL

  useEffect(() => {
    let dead = false;
    (async () => {
      try {
        const [s, c, e] = await Promise.all([
          fetch(`${API_BASE}/api/tsunami/trend/status`).then(r => r.json()),
          fetch(`${API_BASE}/api/tsunami/trend/comparison`).then(r => r.json()),
          fetch(`${API_BASE}/api/tsunami/trend/equity-curve`).then(r => r.json()).catch(() => null),
        ]);
        if (!dead) { setStatus(s); setCmp(c); setEq(e); }
      } catch (e2) {
        if (!dead) setErr(String(e2));
      }
    })();
    return () => { dead = true; };
  }, []);

  const held = useMemo(() => new Set(cmp?.held || []), [cmp]);
  const tickers = useMemo(() => ['TSUNAMI', ...(cmp?.tickers || [])], [cmp]);
  const points = useMemo(
    () => windowPoints(cmp?.points || [], tf), [cmp, tf]);
  const eqPoints = useMemo(
    () => windowPoints(eq?.points || [], tf), [eq, tf]);
  const startCash = eq?.start_cash ?? 500;

  const toggle = (id) => setOn(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const equity = status?.equity ?? null;
  const cash = status?.cash ?? null;
  const startingCapital = status?.starting_capital ?? null;
  const todayPnl = status?.today_pnl ?? null;
  const unrealizedPnl = status?.unrealized_pnl ?? null;
  const realizedPnl = status?.realized_pnl ?? null;
  const book = status?.book || [];
  const trades = status?.recent_trades || [];
  const heldCount = book.filter(b => b.shares > 0).length;
  const lastFill = trades.length ? String(trades[0].ts).slice(0, 10) : null;
  const returnPct = equity != null && startingCapital ? (equity - startingCapital) / startingCapital : null;

  return (
    <div className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary">
      <TsunamiHeader />

      <div className="px-4 md:px-8 py-6 space-y-5">
        {/* KPI strip — stock-bot stats: equity / P&L (today, unrealized, realized) / positions */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiTile
            label="Account Equity"
            value={equity != null ? money(equity) : '…'}
            accent={returnPct != null ? (returnPct >= 0 ? 'var(--color-sw-green)' : 'var(--color-sw-red)') : undefined}
            sub={returnPct != null ? `${pct(returnPct, 1)} since deploy` : 'Allocated · TSUNAMI'}
          />
          <KpiTile
            label="Today P&L"
            value={todayPnl != null ? money(todayPnl, { signed: true }) : '…'}
            accent={todayPnl != null ? (todayPnl >= 0 ? 'var(--color-sw-green)' : 'var(--color-sw-red)') : undefined}
            sub="Realized · closed today"
          />
          <KpiTile
            label="Unrealized P&L"
            value={unrealizedPnl != null ? money(unrealizedPnl, { signed: true }) : '…'}
            accent={unrealizedPnl != null ? (unrealizedPnl >= 0 ? 'var(--color-sw-green)' : 'var(--color-sw-red)') : undefined}
            sub={heldCount > 0 ? `Mark-to-market · ${heldCount} held` : 'All cash'}
          />
          <KpiTile
            label="Total Realized P&L"
            value={realizedPnl != null ? money(realizedPnl, { signed: true }) : '…'}
            accent={realizedPnl != null ? (realizedPnl >= 0 ? 'var(--color-sw-green)' : 'var(--color-sw-red)') : undefined}
            sub="Since deploy · closed trades"
          />
          <KpiTile
            label="Cash"
            value={cash != null ? money(cash) : '…'}
            sub={
              equity != null && cash != null && equity > 0
                ? `${((cash / equity) * 100).toFixed(0)}% of equity uninvested`
                : undefined
            }
          />
          <KpiTile
            label="Positions"
            value={String(heldCount)}
            accent={heldCount > 0 ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)'}
            sub={heldCount > 0 ? 'Names held · shares' : 'All cash'}
          />
          <KpiTile
            label="Last Fill"
            value={
              lastFill
                ? <span className="text-sw-green text-[20px]">{lastFill}</span>
                : <span className="text-text-muted">—</span>
            }
            sub={lastFill ? `${trades.length} recent fills` : 'Awaiting first rebalance'}
          />
        </div>

        {/* Centerpiece — toggle between the EQUITY curve ($500 sleeve over time) and the
            indexed COMPARISON vs its universe. Timeframe filter applies to both; instrument
            chips filter the comparison view. */}
        <Card
          title={view === 'EQUITY' ? 'TSUNAMI equity' : 'TSUNAMI vs. its instruments'}
          subtitle={view === 'EQUITY'
            ? `$${startCash.toFixed(0)} sleeve · daily rebalance + 15-min intraday marks`
            : 'Indexed to 100 at the left edge · dashed = inverse (short-side) products'}
          headerRight={
            <div className="flex flex-wrap items-center gap-2">
              <PillGroup options={['EQUITY', 'COMPARE']} value={view} onChange={setView} />
              <PillGroup options={TIMEFRAMES.map(t => t.id)} value={tf} onChange={setTf} />
            </div>
          }
        >
          <div className="px-5 pt-4 pb-5">
            {view === 'COMPARE' && (
              <div className="flex flex-wrap gap-1.5 mb-4">
                {tickers.map(t => (
                  <Chip key={t} id={t} on={on.has(t)} held={held.has(t)} onClick={() => toggle(t)} />
                ))}
              </div>
            )}
            {err && <div className="text-sw-red text-[12px] mb-2">{err}</div>}
            {view === 'EQUITY' && eqPoints.length === 0 && (
              <div className="py-16 text-center text-[12.5px] text-text-tertiary">
                No equity history yet — points land every 15 min during market hours,
                plus the daily rebalance (14:45 CT).
              </div>
            )}
            {(view === 'COMPARE' || eqPoints.length > 0) && (
            <div className="w-full h-[380px]">
              <ResponsiveContainer>
                {view === 'EQUITY' ? (
                  <LineChart data={eqPoints} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
                    <CartesianGrid stroke="rgba(125,211,252,0.06)" vertical={false} />
                    <XAxis dataKey={tf === 'INTRADAY' ? 'ts' : 'date'}
                           tickFormatter={tf === 'INTRADAY' ? (v) => String(v).slice(11, 16) : undefined}
                           tick={{ fill: '#475569', fontSize: 10.5, fontFamily: 'JetBrains Mono' }}
                           minTickGap={48} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#475569', fontSize: 10.5, fontFamily: 'JetBrains Mono' }} axisLine={false}
                           tickLine={false} domain={['auto', 'auto']} width={54}
                           tickFormatter={(v) => `$${Number(v).toFixed(0)}`} />
                    <Tooltip
                      contentStyle={{
                        background: 'rgba(13,28,46,0.95)',
                        border: '1px solid rgba(125,211,252,0.25)',
                        borderRadius: 10, fontSize: 12, fontFamily: 'JetBrains Mono',
                      }}
                      labelStyle={{ color: '#94a3b8' }}
                      labelFormatter={tf === 'INTRADAY' ? (v) => String(v).slice(0, 16).replace('T', ' ') : undefined}
                      formatter={(v) => [money(Number(v)), 'equity']}
                    />
                    <ReferenceLine y={startCash} stroke="rgba(148,163,184,0.35)" strokeDasharray="2 4" />
                    <Line type="monotone" dataKey="equity" dot={false} connectNulls
                          stroke={THEME.primary} strokeWidth={2.4} />
                  </LineChart>
                ) : (
                  <LineChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
                    <CartesianGrid stroke="rgba(125,211,252,0.06)" vertical={false} />
                    <XAxis dataKey="date" tick={{ fill: '#475569', fontSize: 10.5, fontFamily: 'JetBrains Mono' }}
                           minTickGap={48} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#475569', fontSize: 10.5, fontFamily: 'JetBrains Mono' }} axisLine={false}
                           tickLine={false} domain={['auto', 'auto']} width={44} />
                    <Tooltip
                      contentStyle={{
                        background: 'rgba(13,28,46,0.95)',
                        border: '1px solid rgba(125,211,252,0.25)',
                        borderRadius: 10, fontSize: 12, fontFamily: 'JetBrains Mono',
                      }}
                      labelStyle={{ color: '#94a3b8' }}
                      formatter={(v, name) => [Number(v).toFixed(1), name]}
                    />
                    <ReferenceLine y={100} stroke="rgba(148,163,184,0.35)" strokeDasharray="2 4" />
                    {tickers.filter(t => on.has(t)).map(t => (
                      <Line key={t} type="monotone" dataKey={t} dot={false} connectNulls
                            stroke={SERIES_COLOR[t] || '#94a3b8'}
                            strokeWidth={t === 'TSUNAMI' ? 2.6 : 1.4}
                            strokeDasharray={INVERSE.has(t) ? '5 4' : undefined} />
                    ))}
                  </LineChart>
                )}
              </ResponsiveContainer>
            </div>
            )}
          </div>
        </Card>

        {/* Positions / Universe (all 16, incl. why not bought) / Trade History / Logs */}
        <TsunamiTabs book={book} heldCount={heldCount} />
      </div>
    </div>
  );
}
