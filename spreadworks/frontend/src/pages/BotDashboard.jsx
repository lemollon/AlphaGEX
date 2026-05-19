import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Power, Zap, Play, Inbox, List, Terminal, Sliders } from 'lucide-react';
import { BOT_REGISTRY, STRATEGY_LABEL, BOT_THEME } from '../lib/botRegistry';
import { botApi } from '../lib/botApi';
import { useBotStatus } from '../hooks/useBotStatus';
import { useBotEquity } from '../hooks/useBotEquity';
import BotGlyph from '../components/bots/BotGlyph';
import PositionsTab from '../components/bots/PositionsTab';
import TradesTab from '../components/bots/TradesTab';
import LogsTab from '../components/bots/LogsTab';
import ConfigTab from '../components/bots/ConfigTab';

/* ── Constants ──────────────────────────────────────────────────── */

const STATUS_REFRESH   = 15_000;
const TABLE_REFRESH    = 30_000;
const INTRADAY_REFRESH = 10_000;

const EQUITY_PERIODS = [
  { label: 'Intraday', value: 'intraday' },
  { label: '1D',       value: '1d' },
  { label: '1W',       value: '1w' },
  { label: '1M',       value: '1m' },
  { label: '3M',       value: '3m' },
  { label: 'All',      value: 'all' },
];

/* ── Helpers ─────────────────────────────────────────────────────── */

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

function formatHM(ts) {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }) + ' CT';
  } catch {
    return String(ts);
  }
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

/* ── KPI tile ────────────────────────────────────────────────────── */

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

/* ── Bot nameplate header ───────────────────────────────────────── */

function BotHeader({ meta, theme, status, enabled, toggling, forcing, onToggle, onForceTrade }) {
  return (
    <div
      className="px-8 pt-7 pb-6"
      style={{ borderBottom: '1px solid rgba(125,211,252,0.18)' }}
    >
      <div className="flex items-start justify-between gap-6">
        <div className="flex items-center gap-5 min-w-0">
          {/* Glyph tile */}
          <div
            className="w-16 h-16 rounded-2xl grid place-items-center flex-shrink-0"
            style={{
              background: theme.accentBg,
              boxShadow: `inset 0 0 0 1px ${theme.primaryRing}, 0 0 32px -8px ${theme.glow}`,
              color: theme.primary,
            }}
          >
            <BotGlyph kind={theme.glyph} size={32} strokeWidth={1.6} />
          </div>

          {/* Nameplate */}
          <div className="min-w-0">
            <h1
              className="font-black tracking-[0.04em] leading-none"
              style={{
                fontSize: 44,
                color: theme.primary,
                textShadow: `0 0 24px ${theme.glow}`,
              }}
            >
              {meta.display}
            </h1>
            <div className="flex items-center gap-2 mt-2 text-[13.5px] text-text-secondary">
              <span className="font-medium">{STRATEGY_LABEL[meta.strategy] || meta.strategy}</span>
              <span className="w-1 h-1 rounded-full bg-text-muted" />
              <span className="sw-mono font-semibold text-white">{meta.ticker}</span>
              <span className="w-1 h-1 rounded-full bg-text-muted" />
              <span className="sw-mono text-text-tertiary">
                {String(meta.display).toLowerCase()} · {meta.version || 'v1.0'}
              </span>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {enabled ? (
            <>
              <button
                onClick={onToggle}
                disabled={toggling}
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-md text-[13px] font-semibold sw-glass hover:brightness-110 transition disabled:opacity-60"
                style={{
                  color: '#7dd3fc',
                  boxShadow: `inset 0 0 0 1px ${theme.primaryRing}, inset 0 1px 0 rgba(255,255,255,0.04)`,
                }}
              >
                <Power size={13} /> {toggling ? 'Working…' : 'Disable'}
              </button>
              <button
                onClick={onForceTrade}
                disabled={forcing}
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-md text-[13px] font-semibold sw-glass text-text-body hover:text-text-primary transition-colors disabled:opacity-60"
                style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)' }}
              >
                <Zap size={13} /> {forcing ? 'Sending…' : 'Force Trade'}
              </button>
              <span className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-[11.5px] font-bold tracking-wider uppercase text-sw-green bg-sw-green-dim ring-1 ring-sw-green/30">
                <span className="relative inline-flex w-1.5 h-1.5">
                  <span className="absolute inset-0 rounded-full animate-ping opacity-60 bg-sw-green" />
                  <span className="relative inline-block w-1.5 h-1.5 rounded-full bg-sw-green" />
                </span>
                Enabled
              </span>
            </>
          ) : (
            <>
              <button
                onClick={onToggle}
                disabled={toggling}
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-md text-[13px] font-semibold text-white bg-sw-green hover:brightness-110 transition disabled:opacity-60"
              >
                <Play size={13} /> {toggling ? 'Working…' : 'Enable'}
              </button>
              <button
                disabled
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-md text-[13px] font-semibold sw-glass text-text-tertiary cursor-not-allowed opacity-60"
                style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)' }}
              >
                <Zap size={13} /> Force Trade
              </button>
              <span className="inline-flex items-center gap-2 px-3 py-2 rounded-md text-[11.5px] font-bold tracking-wider uppercase text-text-secondary bg-white/[0.04] ring-1 ring-white/10">
                <span className="w-1.5 h-1.5 rounded-full bg-text-tertiary" />
                Disabled
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── KPI Grid (4×2) ─────────────────────────────────────────────── */

function KpiGrid({ bot, status, perf, theme }) {
  const equity = status && typeof status.equity === 'number' ? status.equity : null;
  const startingCapital = status?.starting_capital ?? null;

  // The backend doesn't yet expose `today_pnl`/`unrealized_pnl`; derive what we
  // can from the data we have, otherwise show em-dash.
  const todayPnl = status && typeof status.today_pnl === 'number' ? status.today_pnl : null;
  const openPos = status?.open_positions ?? 0;
  const lastScanAt = status?.last_scan_at ?? null;

  const todayPos = todayPnl != null && todayPnl > 0;
  const todayNeg = todayPnl != null && todayPnl < 0;

  const tradeCount = perf?.trades ?? null;
  const winRate    = perf?.win_rate ?? null;       // 0..1
  const totalPnl   = perf?.total_pnl ?? null;
  const avgWin     = perf?.avg_win ?? null;
  const avgLoss    = perf?.avg_loss ?? null;
  const totalPos   = totalPnl != null && totalPnl >= 0;

  const equityBase = equity ?? startingCapital ?? null;

  const expectancy =
    winRate != null && avgWin != null && avgLoss != null
      ? winRate * avgWin + (1 - winRate) * avgLoss
      : null;

  return (
    <div className="grid grid-cols-4 gap-4">
      <KpiTile
        label="Account Equity"
        value={equity != null ? money(equity, { decimals: 2 }) : '…'}
        sub={`Allocated · ${bot.toUpperCase()}`}
      />
      <KpiTile
        label="Today P&L"
        value={
          todayPnl == null
            ? <span className="text-text-muted">—</span>
            : todayPnl === 0
              ? <span className="text-text-muted">—</span>
              : money(todayPnl, { signed: true })
        }
        accent={todayPos ? 'var(--color-sw-green)' : todayNeg ? 'var(--color-sw-red)' : undefined}
        sub={
          todayPnl != null && todayPnl !== 0 && equityBase
            ? `${pct(todayPnl / equityBase, 2)} on equity`
            : 'No fills today'
        }
      />
      <KpiTile
        label="Open Positions"
        value={String(openPos)}
        accent={openPos > 0 ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)'}
        sub={openPos > 0 ? 'Auto-managed' : 'Awaiting setup'}
      />
      <KpiTile
        label="Last Scan"
        value={
          <span className="text-sw-green">
            {lastScanAt ? relativeTime(lastScanAt) : '—'}
          </span>
        }
        mono={false}
        sub={lastScanAt ? formatHM(lastScanAt) : undefined}
      />

      <KpiTile
        label="Trades"
        value={tradeCount != null ? String(tradeCount) : '—'}
        sub="Since deploy"
      />
      <KpiTile
        label="Win Rate"
        value={
          tradeCount > 0 && winRate != null
            ? `${(winRate * 100).toFixed(1)}%`
            : <span className="text-text-muted">—</span>
        }
        accent={
          tradeCount > 0 && winRate != null
            ? (winRate >= 0.5 ? 'var(--color-sw-green)' : 'var(--color-sw-red)')
            : undefined
        }
        sub={
          tradeCount != null && winRate != null
            ? `${Math.round(tradeCount * winRate)} W · ${tradeCount - Math.round(tradeCount * winRate)} L`
            : undefined
        }
      />
      <KpiTile
        label="Total P&L"
        value={
          totalPnl != null
            ? money(totalPnl, { signed: true })
            : <span className="text-text-muted">—</span>
        }
        accent={
          totalPnl != null
            ? (totalPos ? 'var(--color-sw-green)' : 'var(--color-sw-red)')
            : undefined
        }
        sub={
          totalPnl != null && equityBase
            ? `${pct(totalPnl / equityBase, 2)} since deploy`
            : undefined
        }
      />
      <KpiTile
        label="Avg Win / Loss"
        value={
          avgWin != null && avgLoss != null
            ? (
                <span>
                  <span className="text-sw-green">+${Math.abs(avgWin).toFixed(0)}</span>
                  <span className="text-text-muted mx-1">/</span>
                  <span className="text-sw-red">−${Math.abs(avgLoss).toFixed(0)}</span>
                </span>
              )
            : <span className="text-text-muted">—</span>
        }
        sub={
          expectancy != null
            ? `Expectancy ${money(expectancy, { signed: true, decimals: 0 })}`
            : undefined
        }
      />
    </div>
  );
}

/* ── Equity Curve (themed, hand-drawn SVG) ──────────────────────── */

function EquityCurveCard({ bot, theme, period, onPeriodChange, curve }) {
  return (
    <div
      className="rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <div
        className="px-5 py-4 flex items-center justify-between"
        style={{ borderBottom: '1px solid rgba(125,211,252,0.08)' }}
      >
        <div className="flex items-center gap-3">
          <h3 className="text-[14px] font-semibold text-text-primary">Equity Curve</h3>
          <span className="text-[11.5px] text-text-tertiary">Account equity over time</span>
        </div>
        <div className="flex items-center gap-1 rounded-md p-0.5" style={{ background: 'rgba(7,16,28,0.4)' }}>
          {EQUITY_PERIODS.map(p => {
            const active = period === p.value;
            return (
              <button
                key={p.value}
                onClick={() => onPeriodChange(p.value)}
                className="sw-mono px-3 py-1 text-[11px] font-medium rounded transition-all"
                style={
                  active
                    ? { background: theme.primary, color: '#0a1726' }
                    : { color: 'var(--color-text-secondary)' }
                }
              >
                {p.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="px-3 pt-3 pb-3">
        <EquityChart bot={bot} theme={theme} data={curve} />
      </div>
    </div>
  );
}

function EquityChart({ bot, theme, data }) {
  const W = 1200;
  const H = 260;
  const padL = 64;
  const padR = 18;
  const padT = 18;
  const padB = 30;

  if (!data || data.length < 2) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2 h-[260px]">
        <span className="text-text-tertiary text-[13px]">
          No equity points yet. Bot will write one per scan cycle.
        </span>
      </div>
    );
  }

  const values = data.map(d => d.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.15 || 1;
  const yMin = min - pad;
  const yMax = max + pad;
  const range = yMax - yMin || 1;
  const stepX = (W - padL - padR) / (data.length - 1);

  const points = data.map((d, i) => {
    const x = padL + i * stepX;
    const y = padT + (H - padT - padB) * (1 - (d.equity - yMin) / range);
    return [x, y, d];
  });
  const linePts = points.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');

  const lastX = points[points.length - 1][0];
  const lastY = points[points.length - 1][1];
  const lastV = data[data.length - 1].equity;
  const firstV = data[0].equity;
  const delta = lastV - firstV;
  const deltaPos = delta >= 0;
  const deltaPct = firstV ? delta / firstV : 0;

  // Y ticks (5)
  const yTicks = [];
  for (let i = 0; i < 5; i++) {
    const v = yMin + (range * i) / 4;
    const y = padT + (H - padT - padB) * (1 - (v - yMin) / range);
    yTicks.push({ y, v });
  }

  // X ticks (6 evenly spaced, formatted as HH:MM CT)
  const xTicks = [];
  const fmtTime = ts => {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleTimeString('en-US', {
        timeZone: 'America/Chicago',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
    } catch {
      return '';
    }
  };
  for (let i = 0; i < 6; i++) {
    const idx = Math.round((i / 5) * (data.length - 1));
    const x = padL + idx * stepX;
    xTicks.push({ x, label: fmtTime(data[idx]?.time) });
  }

  const gradId = `eqgrad-${bot}`;
  const glowId = `eqglow-${bot}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[260px]">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={theme.primary} stopOpacity="0.35" />
          <stop offset="100%" stopColor={theme.primary} stopOpacity="0" />
        </linearGradient>
        <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* y grid + tick labels */}
      {yTicks.map((t, i) => (
        <g key={`y-${i}`}>
          <line
            x1={padL}
            y1={t.y}
            x2={W - padR}
            y2={t.y}
            stroke="rgba(125,211,252,0.06)"
            strokeWidth="1"
            strokeDasharray={i === 0 || i === 4 ? '0' : '3 6'}
          />
          <text
            x={padL - 8}
            y={t.y + 3}
            fill="#475569"
            fontSize="10.5"
            fontFamily="JetBrains Mono"
            textAnchor="end"
          >
            ${t.v.toLocaleString('en-US', { maximumFractionDigits: 0 })}
          </text>
        </g>
      ))}

      {/* x tick labels */}
      {xTicks.map((x, i) => (
        <text
          key={`x-${i}`}
          x={x.x}
          y={H - 10}
          fill="#475569"
          fontSize="10.5"
          fontFamily="JetBrains Mono"
          textAnchor="middle"
        >
          {x.label}
        </text>
      ))}

      {/* fill */}
      <path
        d={`M ${padL},${H - padB} L ${linePts.split(' ').join(' L ')} L ${W - padR},${H - padB} Z`}
        fill={`url(#${gradId})`}
      />

      {/* line */}
      <polyline
        fill="none"
        stroke={theme.primary}
        strokeWidth="2.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={linePts}
        filter={`url(#${glowId})`}
      />

      {/* last-point marker + dashed guideline */}
      <circle cx={lastX} cy={lastY} r="4.5" fill={theme.primary} stroke="#0a1726" strokeWidth="2.5" />
      <line
        x1={lastX}
        y1={padT}
        x2={lastX}
        y2={H - padB}
        stroke={theme.primary}
        strokeWidth="1"
        strokeDasharray="2 4"
        opacity="0.35"
      />

      {/* last-value pill */}
      <g transform={`translate(${Math.min(lastX + 10, W - padR - 100)}, ${lastY - 14})`}>
        <rect x="0" y="0" width="96" height="28" rx="4" fill={theme.primary} />
        <text
          x="48"
          y="18"
          fill="#0a1726"
          fontSize="12"
          fontFamily="JetBrains Mono"
          fontWeight="700"
          textAnchor="middle"
        >
          ${lastV.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </text>
      </g>

      {/* session delta */}
      <g transform={`translate(${padL + 4}, ${padT + 2})`}>
        <text
          x="0"
          y="10"
          fill="#64748b"
          fontSize="10.5"
          fontFamily="Inter"
          fontWeight="600"
          letterSpacing="0.14em"
          style={{ textTransform: 'uppercase' }}
        >
          Session
        </text>
        <text
          x="0"
          y="28"
          fill={deltaPos ? '#34d399' : '#fb7185'}
          fontSize="14"
          fontFamily="JetBrains Mono"
          fontWeight="700"
        >
          {deltaPos ? '+' : '−'}$
          {Math.abs(delta).toFixed(2)} · {deltaPos ? '+' : '−'}
          {Math.abs(deltaPct * 100).toFixed(2)}%
        </text>
      </g>
    </svg>
  );
}

/* ── Activity Tabs (themed) ─────────────────────────────────────── */

function ActivityTabs({ bot, theme, openCount, tradeCount, lastScanAt, enabled }) {
  const [tab, setTab] = useState('positions');

  const tabs = [
    { id: 'positions', label: 'Positions',     Icon: Inbox,    count: openCount },
    { id: 'history',   label: 'Trade History', Icon: List,     count: tradeCount },
    { id: 'logs',      label: 'Logs',          Icon: Terminal, count: null },
    { id: 'config',    label: 'Config',        Icon: Sliders,  count: null },
  ];

  return (
    <div
      className="rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      {/* Tab bar */}
      <div
        className="flex items-center gap-1 px-3 pt-3"
        style={{ borderBottom: '1px solid rgba(125,211,252,0.08)' }}
      >
        {tabs.map(t => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="relative inline-flex items-center gap-2 px-3.5 py-2.5 text-[12.5px] font-semibold transition-colors"
              style={{ color: active ? theme.primary : 'var(--color-text-secondary)' }}
            >
              <t.Icon size={13} />
              {t.label}
              {t.count != null && t.count > 0 && (
                <span
                  className="sw-mono text-[10px] font-bold px-1.5 py-0.5 rounded-full"
                  style={
                    active
                      ? {
                          background: theme.primarySoft,
                          color: theme.primary,
                          boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
                        }
                      : { background: 'rgba(255,255,255,0.05)', color: 'var(--color-text-secondary)' }
                  }
                >
                  {t.count}
                </span>
              )}
              {active && (
                <span
                  className="absolute left-2.5 right-2.5 -bottom-px h-[2px]"
                  style={{ background: theme.primary }}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="min-h-[280px]">
        {tab === 'positions' && <PositionsTab bot={bot} lastScanAt={lastScanAt} enabled={enabled} />}
        {tab === 'history'   && <TradesTab    bot={bot} />}
        {tab === 'logs'      && <LogsTab      bot={bot} />}
        {tab === 'config'    && <ConfigTab    bot={bot} />}
      </div>
    </div>
  );
}

/* ── Main page ───────────────────────────────────────────────────── */

export default function BotDashboard() {
  const { bot } = useParams();
  const meta  = BOT_REGISTRY[bot];
  const theme = BOT_THEME[bot];

  const [equityPeriod, setEquityPeriod] = useState('intraday');
  const [perf,    setPerf]    = useState(null);
  const [toggling, setToggling] = useState(false);
  const [forcing,  setForcing]  = useState(false);

  const { data: status, error: statusErr } = useBotStatus(bot, STATUS_REFRESH);

  const equityMode     = equityPeriod === 'intraday' ? 'intraday' : 'historical';
  const equityInterval = equityPeriod === 'intraday' ? INTRADAY_REFRESH : TABLE_REFRESH;
  const { curve: equityCurve } = useBotEquity(bot, equityMode, equityInterval);

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

  if (!meta || !theme) {
    return (
      <div className="flex-1 px-6 py-5 bg-bg-base text-text-secondary text-[13px]">
        Unknown bot: {bot}
      </div>
    );
  }

  if (statusErr && !status) {
    return (
      <div className="flex-1 px-6 py-5 bg-bg-base">
        <div className="sw-card p-4 border-sw-red/30 bg-sw-red-dim text-sw-red text-[13px]">
          Failed to load {bot.toUpperCase()} status: {statusErr.message}
        </div>
      </div>
    );
  }

  const enabled = !!status?.enabled;
  const openCount = status?.open_positions ?? 0;
  const tradeCount = perf?.trades ?? 0;

  return (
    <div className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary">
      <BotHeader
        meta={meta}
        theme={theme}
        status={status}
        enabled={enabled}
        toggling={toggling}
        forcing={forcing}
        onToggle={onToggle}
        onForceTrade={onForceTrade}
      />

      <div className="px-8 py-6 space-y-5">
        <KpiGrid bot={bot} status={status} perf={perf} theme={theme} />

        <EquityCurveCard
          bot={bot}
          theme={theme}
          period={equityPeriod}
          onPeriodChange={setEquityPeriod}
          curve={equityCurve}
        />

        <ActivityTabs
          bot={bot}
          theme={theme}
          openCount={openCount}
          tradeCount={tradeCount}
          lastScanAt={status?.last_scan_at}
          enabled={enabled}
        />
      </div>
    </div>
  );
}
