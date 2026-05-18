import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Activity,
  Snowflake,
  Waves,
  Wind,
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { BOT_REGISTRY, STRATEGY_LABEL, BOT_THEME } from '../lib/botRegistry';
import { botApi } from '../lib/botApi';
import { useBotStatus } from '../hooks/useBotStatus';
import { useBotEquity } from '../hooks/useBotEquity';
import PositionsTab from '../components/bots/PositionsTab';
import TradesTab from '../components/bots/TradesTab';
import LogsTab from '../components/bots/LogsTab';
import ConfigTab from '../components/bots/ConfigTab';

/* ── Constants ──────────────────────────────────────────────────── */

const STATUS_REFRESH  = 15_000;
const POSITION_REFRESH = 10_000;
const TABLE_REFRESH   = 30_000;
const INTRADAY_REFRESH = 10_000;

const GLYPH_MAP = {
  snowflake: Snowflake,
  wave:      Waves,
  current:   Wind,
};

const EQUITY_PERIODS = [
  { label: 'Intraday', value: 'intraday' },
  { label: '1D',       value: '1d' },
  { label: '1W',       value: '1w' },
  { label: '1M',       value: '1m' },
  { label: '3M',       value: '3m' },
  { label: 'All',      value: 'all' },
];

const SUB_TABS = ['Positions', 'Trade History', 'Logs', 'Config'];

/* ── Helpers ─────────────────────────────────────────────────────── */

function formatCT(ts) {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'America/Chicago',
      hour12: false,
    });
  } catch {
    return String(ts);
  }
}

function formatEquity(v) {
  if (v == null) return '—';
  return `$${Number(v).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function relativeTime(ts) {
  if (!ts) return '—';
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 0) return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

/* ── Equity chart tooltip ────────────────────────────────────────── */

function EquityTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="sw-card p-2.5 text-[11px] shadow-md">
      <div className="sw-label mb-1">{formatCT(label)}</div>
      <div className="sw-mono text-text-primary font-semibold">
        {formatEquity(payload[0]?.value)}
      </div>
    </div>
  );
}

/* ── Stat card (used in status row) ─────────────────────────────── */

function StatCard({ label, value, sub, valueClass = '' }) {
  return (
    <div className="sw-card p-4 flex flex-col gap-1.5">
      <div className={`sw-stat-value ${valueClass}`}>{value}</div>
      <div className="sw-label">{label}</div>
      {sub && <div className="sw-stat-sublabel">{sub}</div>}
    </div>
  );
}

/* ── Main component ──────────────────────────────────────────────── */

export default function BotDashboard() {
  const { bot } = useParams();
  const meta  = BOT_REGISTRY[bot];
  const theme = BOT_THEME[bot];

  const [subTab, setSubTab]         = useState('Positions');
  const [equityPeriod, setEquityPeriod] = useState('intraday');
  const [perf, setPerf]             = useState(null);
  const [toggling, setToggling]     = useState(false);
  const [forcing, setForcing]       = useState(false);

  /* Status (always polled) */
  const { data: status, error: statusErr } = useBotStatus(bot, STATUS_REFRESH);

  /* Equity curve — period switches between intraday and historical */
  const equityMode  = equityPeriod === 'intraday' ? 'intraday' : 'historical';
  const equityInterval = equityPeriod === 'intraday' ? INTRADAY_REFRESH : TABLE_REFRESH;
  const { curve: equityCurve } = useBotEquity(bot, equityMode, equityInterval);

  /* Performance (always fetched, slow refresh) */
  useEffect(() => {
    let cancelled = false;
    async function fetchPerf() {
      try {
        const d = await botApi.performance(bot);
        if (!cancelled) setPerf(d);
      } catch { /* silent */ }
    }
    fetchPerf();
    const h = setInterval(fetchPerf, TABLE_REFRESH);
    return () => { cancelled = true; clearInterval(h); };
  }, [bot]);

  const onToggle = useCallback(async () => {
    setToggling(true);
    try { await botApi.toggle(bot); } catch { /* silent */ }
    finally { setToggling(false); }
  }, [bot]);

  const onForceTrade = useCallback(async () => {
    setForcing(true);
    try { await botApi.forceTrade(bot); } catch { /* silent */ }
    finally { setForcing(false); }
  }, [bot]);

  /* Unknown bot */
  if (!meta) {
    return (
      <div className="flex-1 px-6 py-5 bg-bg-base text-text-secondary text-[13px]">
        Unknown bot: {bot}
      </div>
    );
  }

  const GlyphIcon = GLYPH_MAP[theme?.glyph] || Wind;
  const accentColor = theme?.accent || 'var(--color-accent)';
  const isEnabled = !!status?.enabled;

  /* Derived metrics */
  const equity      = typeof status?.equity === 'number' ? status.equity : null;
  const todayPnl    = typeof status?.today_pnl === 'number' ? status.today_pnl : null;
  const openPos     = status?.open_positions ?? 0;
  const unrealPnl   = typeof status?.unrealized_pnl === 'number' ? status.unrealized_pnl : null;
  const lastScanAt  = status?.last_scan_at ?? null;
  const scannerOn   = !!status?.scanner_active;

  const winRate   = perf ? (perf.win_rate ?? 0) * 100 : null;
  const totalPnl  = perf?.total_pnl ?? null;
  const avgWin    = perf?.avg_win ?? null;
  const avgLoss   = perf?.avg_loss ?? null;
  const tradeCount = perf?.trades ?? null;

  /* Loading / error */
  if (statusErr) {
    return (
      <div className="flex-1 px-6 py-5 bg-bg-base">
        <div className="sw-card p-4 border-sw-red/30 bg-sw-red-dim text-sw-red text-[13px]">
          Failed to load {bot.toUpperCase()} status: {statusErr.message}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 px-6 py-5 overflow-y-auto font-[var(--font-ui)] text-text-primary bg-bg-base space-y-5">

      {/* ── Section A: Bot header bar ────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <GlyphIcon size={20} style={{ color: accentColor }} />
          <div>
            <h1
              className="text-2xl font-extrabold tracking-tight leading-none"
              style={{ color: accentColor }}
            >
              {meta.display}
            </h1>
            <p className="text-text-secondary text-[13px] mt-0.5">
              {STRATEGY_LABEL[meta.strategy]} &middot; {meta.ticker}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="sw-btn-secondary !py-1.5 !text-[12px]"
            onClick={onToggle}
            disabled={toggling}
          >
            {toggling ? 'Working...' : isEnabled ? 'Disable' : 'Enable'}
          </button>
          <button
            className="sw-btn-ghost !text-[12px]"
            onClick={onForceTrade}
            disabled={forcing}
          >
            {forcing ? 'Sending...' : 'Force Trade'}
          </button>
          <span
            className={`sw-badge ml-1 ${
              isEnabled
                ? 'bg-sw-green/10 text-sw-green border border-sw-green/25'
                : 'bg-bg-hover text-text-muted border border-border-subtle'
            }`}
          >
            {isEnabled ? 'ENABLED' : 'DISABLED'}
          </span>
        </div>
      </div>

      {/* ── Section B: Status row ────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="ACCOUNT EQUITY"
          value={status ? formatEquity(equity) : '...'}
          valueClass="sw-mono"
        />
        <StatCard
          label="TODAY P&L"
          value={
            todayPnl != null
              ? `${todayPnl >= 0 ? '+' : ''}$${Math.abs(todayPnl).toFixed(2)}`
              : status ? '—' : '...'
          }
          valueClass={`sw-mono ${todayPnl != null ? (todayPnl >= 0 ? 'sw-pnl-positive' : 'sw-pnl-negative') : ''}`}
        />
        <StatCard
          label="OPEN POSITIONS"
          value={status ? String(openPos) : '...'}
          valueClass="sw-mono"
          sub={
            unrealPnl != null
              ? `${unrealPnl >= 0 ? '+' : ''}$${unrealPnl.toFixed(2)} unrealized`
              : undefined
          }
        />
        <StatCard
          label="LAST SCAN"
          value={status ? relativeTime(lastScanAt) : '...'}
          valueClass="sw-mono text-[16px]"
          sub={
            lastScanAt
              ? new Date(lastScanAt).toLocaleTimeString('en-US', {
                  timeZone: 'America/Chicago',
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                  hour12: false,
                }) + ' CT'
              : undefined
          }
        />
      </div>

      {/* ── Section C: Performance summary row ───────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="sw-stat-card">
          <div className="sw-stat-value sw-mono">
            {tradeCount != null ? String(tradeCount) : '—'}
          </div>
          <div className="sw-stat-sublabel">TRADES</div>
        </div>
        <div className="sw-stat-card">
          <div className={`sw-stat-value sw-mono ${tradeCount > 0 && winRate != null ? (winRate >= 50 ? 'sw-pnl-positive' : 'sw-pnl-negative') : 'text-text-muted'}`}>
            {tradeCount > 0 && winRate != null ? `${winRate.toFixed(1)}%` : '—'}
          </div>
          <div className="sw-stat-sublabel">WIN RATE</div>
        </div>
        <div className="sw-stat-card">
          <div className={`sw-stat-value sw-mono ${tradeCount > 0 && totalPnl != null ? (totalPnl >= 0 ? 'sw-pnl-positive' : 'sw-pnl-negative') : 'text-text-muted'}`}>
            {tradeCount > 0 && totalPnl != null ? `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}` : '—'}
          </div>
          <div className="sw-stat-sublabel">TOTAL P&L</div>
        </div>
        <div className="sw-stat-card">
          <div className="sw-stat-value sw-mono text-text-secondary">
            {tradeCount > 0 && avgWin != null && avgLoss != null
              ? `+$${avgWin.toFixed(0)} / -$${Math.abs(avgLoss).toFixed(0)}`
              : '—'}
          </div>
          <div className="sw-stat-sublabel">AVG WIN / LOSS</div>
        </div>
      </div>

      {/* ── Section D: Equity chart (always visible) ─────────────── */}
      <div className="sw-card p-4">
        {/* Chart header */}
        <div className="flex items-center justify-between mb-4">
          <span className="text-text-primary text-[13px] font-semibold">Equity Curve</span>
          <div className="sw-toggle-group !gap-0.5">
            {EQUITY_PERIODS.map(p => (
              <button
                key={p.value}
                className={`sw-toggle-btn !px-3 !py-1 ${equityPeriod === p.value ? 'active' : ''}`}
                onClick={() => setEquityPeriod(p.value)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Chart body */}
        {equityCurve.length < 2 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-2">
            <Activity size={24} className="text-text-muted" />
            <span className="text-text-tertiary text-[13px]">
              No equity points yet. Bot will write one per scan cycle.
            </span>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart
              data={equityCurve}
              margin={{ top: 8, right: 16, left: 16, bottom: 4 }}
            >
              <defs>
                <linearGradient id={`grad-${bot}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-accent)" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="var(--color-accent)" stopOpacity={0.01} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--color-border-subtle)"
                vertical={false}
              />
              <XAxis
                dataKey="time"
                tickFormatter={formatCT}
                tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)' }}
                axisLine={{ stroke: 'var(--color-border-subtle)' }}
                tickLine={false}
              />
              <YAxis
                dataKey="equity"
                domain={['dataMin - 50', 'dataMax + 50']}
                tickFormatter={v => `$${Number(v).toLocaleString()}`}
                tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)' }}
                axisLine={{ stroke: 'var(--color-border-subtle)' }}
                tickLine={false}
                width={80}
              />
              <Tooltip content={<EquityTooltip />} />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="var(--color-accent)"
                strokeWidth={2}
                fill={`url(#grad-${bot})`}
                dot={false}
                activeDot={{ r: 4, fill: 'var(--color-accent)', strokeWidth: 0 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Section E: Sub-tabs ───────────────────────────────────── */}
      <div>
        <div className="sw-toggle-group !gap-0.5 w-fit mb-4">
          {SUB_TABS.map(t => (
            <button
              key={t}
              className={`sw-toggle-btn !px-4 !py-1.5 ${subTab === t ? 'active' : ''}`}
              onClick={() => setSubTab(t)}
            >
              {t}
            </button>
          ))}
        </div>

        <div>
          {subTab === 'Positions'     && <PositionsTab bot={bot} />}
          {subTab === 'Trade History' && <TradesTab    bot={bot} />}
          {subTab === 'Logs'          && <LogsTab      bot={bot} />}
          {subTab === 'Config'        && <ConfigTab    bot={bot} />}
        </div>
      </div>

    </div>
  );
}
