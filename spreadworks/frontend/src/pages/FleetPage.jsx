import { useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, AlertTriangle, RefreshCw } from 'lucide-react';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip,
} from 'recharts';
import BotGlyph from '../components/bots/BotGlyph';
import { BOT_REGISTRY, BOT_THEME, STRATEGY_LABEL } from '../lib/botRegistry';
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

const GREEN = '#34d399';
const RED = '#fb7185';
const AMBER = '#fbbf24';
const MUTED = '#64748b';
// Cyan brand accent (--color-accent in index.css) — used for the fleet
// equity curve so it reads as "the same app", not a bolted-on chart lib.
const ACCENT = '#22d3ee';

// A bot's last scan is STALE if it's older than this AND the market is open
// (last_scan_at naturally trails while the market is closed — that's not a
// problem, so the alarm is gated on isOpen).
const STALE_MS = 20 * 60 * 1000;

function money(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return '$' + Math.round(Math.abs(n)).toLocaleString('en-US');
}

// Signed money with a true unicode minus, matching the bot dropdown's format.
function signedMoney(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  if (Math.round(n) === 0) return '$0';
  return (n > 0 ? '+' : '−') + money(n);
}

function signedPct(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return null;
  return (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(1) + '%';
}

function pnlColor(n) {
  if (typeof n !== 'number' || !Number.isFinite(n) || Math.round(n) === 0) return MUTED;
  return n > 0 ? GREEN : RED;
}

// The API returns NAIVE timestamps that are actually UTC ("2026-08-07
// 20:10:00.000947" while the server clock reads 20:10Z). `new Date(str)` on a
// naive string parses it as BROWSER-LOCAL, so in CT that reads 5h in the
// future, the diff goes negative, and the caller prints "just now" — forever,
// no matter how long ago the bot really scanned. That defeats the entire point
// of showing it on a fleet page, where a frozen scan clock is the main symptom
// of a dead bot. Pin the string to UTC before parsing.
//
// NOTE: relativeTime() in BotDashboard.jsx and PositionsTab.jsx still has the
// uncorrected version, so their "scanned …" labels understate staleness.
function parseTs(ts) {
  if (ts instanceof Date || typeof ts === 'number') return new Date(ts);
  const s = String(ts).trim();
  // Already carries a zone (…Z / +00:00) — trust it. Otherwise mark it UTC.
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/.test(s);
  return new Date(zoned ? s : s.replace(' ', 'T') + 'Z');
}

function relativeTime(ts) {
  if (!ts) return '—';
  const at = parseTs(ts);
  if (Number.isNaN(at.getTime())) return '—';
  const diff = Math.floor((Date.now() - at.getTime()) / 1000);
  if (diff < 0) return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function capitalize(s) {
  return String(s || '').charAt(0) + String(s || '').slice(1).toLowerCase();
}

// A bot the API knows about but the frontend registry doesn't (backend shipped
// first) still gets a readable card instead of crashing on BOT_THEME[id].glyph.
const FALLBACK_THEME = {
  glyph: 'wave',
  primary: '#94a3b8',
  primarySoft: 'rgba(148,163,184,0.10)',
  primaryRing: 'rgba(148,163,184,0.30)',
  glow: 'rgba(148,163,184,0.18)',
};

const LABEL_STYLE = {
  fontSize: 9, fontWeight: 600, letterSpacing: '0.08em',
  textTransform: 'uppercase', color: MUTED,
};

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

/* ── fleet-stats micro-widgets (sparkline / trades / drawdown / account) ── */

// Plain inline SVG, no recharts — 23 of these on one page is 23 chart-lib
// instances too many. viewBox + preserveAspectRatio="none" stretches to
// whatever box the caller gives it.
function Sparkline({ series }) {
  if (!Array.isArray(series) || series.length < 2) return null;
  const w = 100, h = 28;
  const vals = series.map(p => p.equity);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const step = w / (vals.length - 1);
  const points = vals
    .map((v, i) => `${(i * step).toFixed(2)},${(h - ((v - min) / range) * h).toFixed(2)}`)
    .join(' ');
  const color = vals[vals.length - 1] >= vals[0] ? GREEN : RED;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      style={{ width: '100%', height: h, display: 'block' }}
    >
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function TradesLine({ trades }) {
  if (!trades) return null;
  const style = { fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 4 };
  if (trades.n === 0) return <div style={style}>no closed trades yet</div>;
  const wr = trades.win_rate != null ? Math.round(trades.win_rate * 100) + '%' : '—';
  return (
    <div style={style}>
      {wr} win · {trades.n} trade{trades.n === 1 ? '' : 's'} · 7d {signedMoney(trades.pnl_7d)} · 30d {signedMoney(trades.pnl_30d)}
    </div>
  );
}

function DrawdownChip({ pct }) {
  if (typeof pct !== 'number' || !Number.isFinite(pct) || pct < 0.03) return null;
  const severe = pct >= 0.10;
  const color = severe ? RED : AMBER;
  return (
    <span
      style={{
        marginLeft: 6, fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 9999,
        color, background: severe ? 'rgba(251,113,133,0.12)' : 'rgba(251,191,36,0.12)',
        boxShadow: `inset 0 0 0 1px ${color}55`,
      }}
    >
      DD -{Math.round(pct * 100)}%
    </span>
  );
}

function AccountChip({ account }) {
  const isPaper = !account || account === 'paper';
  return (
    <span
      style={{
        flexShrink: 0, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
        textTransform: 'uppercase', padding: '2px 7px', borderRadius: 9999,
        color: isPaper ? AMBER : RED,
        background: isPaper ? 'transparent' : 'rgba(251,113,133,0.10)',
        boxShadow: `inset 0 0 0 1px ${isPaper ? AMBER : RED}55`,
      }}
    >
      {isPaper ? 'PAPER' : 'LIVE $'}
    </span>
  );
}

/* ── one bot card ────────────────────────────────────────────────── */

function BotCard({ row, botStats, isOpen }) {
  const id = row.bot;
  const meta = BOT_REGISTRY[id] || {};
  const theme = BOT_THEME[id] || FALLBACK_THEME;
  const [hover, setHover] = useState(false);

  const display = capitalize(row.display || meta.display || id);
  const strategy = row.strategy || meta.strategy;
  const failed = !!row.error;

  // Live day P&L = realized closes + mark-to-market on the open book. Realized
  // alone sits at $0 until something actually closes, which reads as a dead bot
  // while it's holding — same reasoning as the nav dropdown's rows.
  const realized = typeof row.today_pnl === 'number' ? row.today_pnl : null;
  const unreal = typeof row.unrealized_pnl === 'number' ? row.unrealized_pnl : 0;
  const today = realized == null ? null : realized + unreal;

  // Total P&L is measured against starting_capital using the MARK-TO-MARKET
  // equity, so an open position shows up here too. equity_mtm is what the bot's
  // own dashboard tile reads; `equity` is realized-only (the scanner sizes off
  // it and must not lever up on unrealized marks).
  const start = typeof row.starting_capital === 'number' ? row.starting_capital : null;
  const mtm = typeof row.equity_mtm === 'number'
    ? row.equity_mtm
    : typeof row.equity === 'number' ? row.equity + unreal : null;
  const total = start != null && mtm != null ? mtm - start : null;
  const retPct = total != null && start ? (total / start) * 100 : null;

  const openPos = typeof row.open_positions === 'number' ? row.open_positions : null;
  const enabled = !!row.enabled;

  const account = botStats && !botStats.error ? botStats.account : 'paper';

  // After-hours framing: the market is closed and today's number is a flat
  // $0 (nothing realized, nothing open to mark) — that reads as a dead bot
  // when what actually happened was yesterday's session. Swap the headline
  // to the last completed session instead, when we have one.
  const lastSession = botStats && !botStats.error ? botStats.last_session : null;
  const showLastSession = !isOpen && today != null && Math.round(today) === 0 && !!lastSession;
  const headlineLabel = showLastSession ? `Last session (${lastSession.d})` : 'Today';
  const headlineValue = showLastSession ? lastSession.pnl : today;

  // Scan-staleness alarm — only meaningful while the market is open; a
  // last_scan_at from yesterday afternoon is expected once the bell rings.
  const scanAt = row.last_scan_at ? parseTs(row.last_scan_at) : null;
  const scanAgeMs = scanAt && !Number.isNaN(scanAt.getTime()) ? Date.now() - scanAt.getTime() : null;
  const stale = isOpen && scanAgeMs != null && scanAgeMs > STALE_MS;

  return (
    <Link
      to={`/bots/${id}`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="sw-glass rounded-xl flex flex-col gap-3"
      style={{
        padding: 16,
        color: 'inherit',
        textDecoration: 'none',
        transition: 'transform 150ms, box-shadow 150ms',
        transform: hover ? 'translateY(-2px)' : 'none',
        boxShadow: hover
          ? `inset 0 0 0 1px ${theme.primaryRing}, 0 10px 30px -12px ${theme.glow || 'rgba(0,0,0,0.4)'}`
          : 'inset 0 0 0 1px rgba(125,211,252,0.08)',
      }}
    >
      {/* header — glyph, name, strategy, live/paused */}
      <div className="flex items-center gap-3 min-w-0">
        <div
          style={{
            width: 34, height: 34, borderRadius: 8, flexShrink: 0,
            display: 'grid', placeItems: 'center',
            background: theme.primarySoft, color: theme.primary,
            boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
          }}
        >
          <BotGlyph kind={theme.glyph} size={16} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="truncate" style={{ fontSize: 15, fontWeight: 700, color: theme.primary }}>
            {display}
          </div>
          <div
            className="truncate"
            style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 2 }}
          >
            {STRATEGY_LABEL[strategy] || strategy || '—'}
          </div>
        </div>

        <span
          className="flex items-center gap-1.5"
          style={{
            flexShrink: 0,
            fontSize: 9.5, fontWeight: 700, letterSpacing: '0.10em',
            textTransform: 'uppercase',
            padding: '3px 8px', borderRadius: 9999,
            color: enabled ? GREEN : MUTED,
            background: enabled ? 'rgba(52,211,153,0.10)' : 'rgba(148,163,184,0.08)',
            boxShadow: `inset 0 0 0 1px ${enabled ? 'rgba(52,211,153,0.25)' : 'rgba(148,163,184,0.18)'}`,
          }}
        >
          <span
            style={{ width: 5, height: 5, borderRadius: 9999, background: enabled ? GREEN : '#475569' }}
          />
          {enabled ? 'Live' : 'Paused'}
        </span>

        <AccountChip account={account} />
      </div>

      {failed ? (
        <div
          className="flex items-start gap-2 rounded-lg"
          style={{
            padding: '8px 12px',
            background: 'rgba(251,113,133,0.08)',
            boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.22)',
          }}
        >
          <AlertTriangle size={13} style={{ color: RED, flexShrink: 0, marginTop: 1 }} />
          <div style={{ fontSize: 11, color: '#fda4af', wordBreak: 'break-word' }}>{row.error}</div>
        </div>
      ) : (
        <>
          {/* today's P&L — the headline number */}
          <div>
            <div style={{ ...LABEL_STYLE, fontSize: 9.5, letterSpacing: '0.10em' }}>{headlineLabel}</div>
            <div
              style={{
                fontFamily: 'JetBrains Mono', fontSize: 26, fontWeight: 700,
                lineHeight: 1.15, marginTop: 2, color: pnlColor(headlineValue),
              }}
            >
              {headlineValue == null ? '—' : signedMoney(headlineValue)}
            </div>
            {!showLastSession && unreal !== 0 && (
              <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 2 }}>
                {signedMoney(realized)} realized · {signedMoney(unreal)} open
              </div>
            )}
          </div>

          {botStats && !botStats.error && (
            <>
              <Sparkline series={botStats.equity_series} />
              <TradesLine trades={botStats.trades} />
            </>
          )}

          {/* total / equity / open */}
          <div
            className="grid grid-cols-3 gap-2"
            style={{ paddingTop: 12, borderTop: '1px solid rgba(125,211,252,0.08)' }}
          >
            <div className="min-w-0">
              <div style={LABEL_STYLE}>Total</div>
              <div
                className="truncate"
                style={{
                  fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700,
                  marginTop: 2, color: pnlColor(total),
                }}
              >
                {total == null ? '—' : signedMoney(total)}
              </div>
              {retPct != null && (
                <div style={{ fontFamily: 'JetBrains Mono', fontSize: 9.5, color: MUTED }}>
                  {signedPct(retPct)}
                </div>
              )}
            </div>

            <div className="min-w-0">
              <div style={LABEL_STYLE}>Equity</div>
              <div
                className="truncate flex items-center"
                style={{
                  fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700,
                  marginTop: 2, color: '#e2e8f0',
                }}
              >
                {money(mtm)}
                {botStats && !botStats.error && <DrawdownChip pct={botStats.drawdown_pct} />}
              </div>
            </div>

            <div className="min-w-0">
              <div style={LABEL_STYLE}>Open</div>
              <div
                style={{
                  fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700,
                  marginTop: 2, color: openPos ? theme.primary : MUTED,
                }}
              >
                {openPos == null ? '—' : openPos}
              </div>
            </div>
          </div>

          {botStats && !botStats.error && (
            <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED }}>
              {botStats.risk?.open_max_loss != null
                ? `At risk ${money(botStats.risk.open_max_loss)}`
                : 'At risk —'}
              {botStats.risk?.nearest_dte != null && ` · nearest exp ${botStats.risk.nearest_dte} DTE`}
            </div>
          )}
        </>
      )}

      {/* footer — ticker · version · last scan */}
      <div
        className="flex items-center justify-between gap-2"
        style={{
          marginTop: 'auto', paddingTop: 8,
          borderTop: '1px solid rgba(125,211,252,0.06)',
          fontFamily: 'JetBrains Mono', fontSize: 9.5, color: MUTED,
        }}
      >
        <span className="truncate">
          {meta.ticker || '—'}{meta.version ? ` · ${meta.version}` : ''}
        </span>
        <span className="truncate" style={{ flexShrink: 0, color: stale ? RED : MUTED }}>
          {stale ? '⚠ STALE · ' : ''}scanned {relativeTime(row.last_scan_at)}
        </span>
      </div>
    </Link>
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
  const navigate = useNavigate();
  const [filter, setFilter] = useState('all');
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

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out = rows.filter(r => {
      if (filter === 'live' && !r.enabled) return false;
      if (filter === 'paused' && r.enabled) return false;
      if (filter === 'holding' && !(r.open_positions > 0)) return false;
      if (filter === 'attention' && !(r.error || r._stale)) return false;
      if (q) {
        const hay = `${r.bot} ${r._name} ${r.strategy || ''} ${BOT_REGISTRY[r.bot]?.ticker || ''}`.toLowerCase();
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
  }, [rows, filter, sort, query]);

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

      {/* ── risk advisor banner — only when the market is NOT normal ── */}
      {riskHeadline && (riskOff || calmFloor) && (
        <div
          role="button"
          tabIndex={0}
          onClick={() => navigate('/risk')}
          onKeyDown={e => { if (e.key === 'Enter') navigate('/risk'); }}
          className="rounded-lg"
          style={{
            padding: '10px 14px', marginBottom: 16, cursor: 'pointer',
            background: riskOff ? 'rgba(251,113,133,0.08)' : 'rgba(52,211,153,0.08)',
            boxShadow: `inset 0 0 0 1px ${riskOff ? 'rgba(251,113,133,0.28)' : 'rgba(52,211,153,0.28)'}`,
            fontSize: 12.5, fontWeight: 600,
            color: riskOff ? '#fda4af' : '#6ee7b7',
          }}
        >
          {riskOff ? `${riskHeadline} — see Risk page for the playbook` : riskHeadline}
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
