/**
 * GEX Profile — Gamma Exposure Visualization (ported from AlphaGEX)
 *
 * Three chart views:
 *   1. Net GEX      — Horizontal bars by strike
 *   2. Call vs Put   — Bidirectional call/put gamma by strike (Recharts)
 *   3. Intraday 5m   — Candlestick + GEX overlay (Plotly)
 *
 * Plus: price-to-wall gauge, flow diagnostics, skew measures, market interpretation.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import Plotly from 'plotly.js-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

const Plot = createPlotlyComponent(Plotly);

const API_URL = import.meta.env.VITE_API_URL || '';

// ── Helpers ─────────────────────────────────────────────────────

const COMMON_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'GLD', 'DIA', 'AAPL', 'TSLA', 'NVDA', 'AMD'];

function isMarketOpen() {
  const now = new Date();
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes();
  const month = now.getUTCMonth();
  const isDST = month >= 2 && month <= 9;
  const etMin = utcMin - (isDST ? 4 : 5) * 60;
  return etMin >= 570 && etMin < 975;
}

function formatGex(num, decimals = 2) {
  const abs = Math.abs(num);
  if (abs >= 1e9) return `${(num / 1e9).toFixed(decimals)}B`;
  if (abs >= 1e6) return `${(num / 1e6).toFixed(decimals)}M`;
  if (abs >= 1e3) return `${(num / 1e3).toFixed(decimals)}K`;
  return num.toFixed(decimals);
}

function formatDollar(num) {
  return `$${num.toFixed(2)}`;
}

function tickTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', {
    timeZone: 'America/Chicago',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

function toCentralPlotly(iso) {
  const d = new Date(iso);
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Chicago',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  }).formatToParts(d);
  const get = (t) => parts.find(p => p.type === t)?.value ?? '00';
  return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}:${get('second')}`;
}

// ── Styles ──────────────────────────────────────────────────────

const s = {
  page: {
    minHeight: '100vh',
    background: 'var(--bg-base)',
    padding: '20px 24px',
    fontFamily: 'var(--font-ui)',
  },
  title: {
    display: 'flex', alignItems: 'center', gap: 10,
    fontSize: 22, fontWeight: 800, color: '#fff',
    letterSpacing: '-0.3px', marginBottom: 4,
  },
  titleIcon: {
    width: 28, height: 28, color: 'var(--accent)',
  },
  subtitle: {
    color: 'var(--text-muted)', fontSize: 13, marginBottom: 20,
  },
  card: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-lg)',
    padding: '16px 18px',
    marginBottom: 16,
  },
  controlsRow: {
    display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 14,
  },
  searchBox: {
    display: 'flex', alignItems: 'center', gap: 8,
    background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)', padding: '6px 12px',
  },
  searchInput: {
    background: 'transparent', border: 'none', outline: 'none',
    color: '#fff', fontSize: 13, fontFamily: 'var(--font-ui)', width: 80,
  },
  searchBtn: {
    background: 'none', border: 'none', color: 'var(--accent)',
    cursor: 'pointer', padding: 0, fontSize: 14,
  },
  symbolLabel: {
    fontSize: 22, fontWeight: 800, color: '#fff',
    fontFamily: 'var(--font-mono)',
  },
  quickSymbol: {
    padding: '2px 8px', fontSize: 11, borderRadius: 'var(--radius-sm)',
    background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
    color: 'var(--text-tertiary)', cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  autoBtn: (on) => ({
    fontSize: 11, padding: '4px 10px', borderRadius: 'var(--radius-sm)',
    border: `1px solid ${on ? 'rgba(0,230,118,0.3)' : 'var(--border-default)'}`,
    background: on ? 'var(--green-dim)' : 'var(--bg-elevated)',
    color: on ? 'var(--green)' : 'var(--text-muted)',
    cursor: 'pointer', fontWeight: 600,
  }),
  refreshBtn: {
    background: 'none', border: 'none', color: 'var(--text-muted)',
    cursor: 'pointer', fontSize: 16, padding: 4,
  },
  timestamp: {
    fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)',
  },
  errorBox: {
    background: 'var(--red-dim)', border: '1px solid rgba(255,82,82,0.3)',
    borderRadius: 'var(--radius-lg)', padding: '12px 16px',
    display: 'flex', alignItems: 'center', gap: 10,
    marginBottom: 16, color: 'var(--red)', fontSize: 13,
  },
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
    gap: 10, marginBottom: 16,
  },
  metricCard: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-lg)',
    padding: '10px 14px',
  },
  metricLabel: {
    fontSize: 10, fontWeight: 600, color: 'var(--text-muted)',
    textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4,
  },
  metricValue: (color) => ({
    fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-mono)',
    color: color || '#fff', display: 'flex', alignItems: 'center', gap: 6,
  }),
  metricSub: {
    fontSize: 10, color: 'var(--text-muted)', marginTop: 2,
  },
  badge: (bg, fg) => ({
    fontSize: 10, padding: '1px 6px', borderRadius: 'var(--radius-sm)',
    background: bg, color: fg, fontWeight: 600,
  }),
  chartTabs: {
    display: 'flex', alignItems: 'center', gap: 2,
    background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)',
    padding: 2, border: '1px solid var(--border-subtle)',
  },
  chartTab: (active) => ({
    padding: '5px 14px', borderRadius: 'var(--radius-sm)',
    fontSize: 12, fontWeight: 600, cursor: 'pointer',
    background: active ? 'rgba(68,138,255,0.15)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-muted)',
    border: 'none', transition: 'all var(--transition-fast)',
  }),
  chartHeader: {
    display: 'flex', flexWrap: 'wrap', alignItems: 'center',
    justifyContent: 'space-between', gap: 10, marginBottom: 14,
  },
  chartTitle: {
    fontSize: 13, fontWeight: 600, color: '#fff',
    display: 'flex', alignItems: 'center', gap: 8,
  },
  liveBadge: {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    fontSize: 11, color: 'var(--green)',
  },
  liveDot: {
    width: 7, height: 7, borderRadius: '50%', background: 'var(--green)',
    animation: 'sw-pulse 2s ease-in-out infinite',
  },
  closedBadge: {
    fontSize: 11, color: 'var(--text-muted)',
  },
  countdownBadge: {
    fontSize: 11, fontFamily: 'var(--font-mono)',
    background: 'var(--bg-elevated)', border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-sm)', padding: '2px 8px',
    color: 'var(--accent)',
  },
  legend: {
    display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 10,
    fontSize: 11, alignItems: 'center',
  },
  legendSep: { color: 'var(--border-subtle)' },
  legendItem: (color) => ({
    display: 'flex', alignItems: 'center', gap: 5, color: 'var(--text-muted)',
  }),
  legendDot: (color, small) => ({
    width: small ? 8 : 10, height: small ? 8 : 10, borderRadius: 2,
    background: color, flexShrink: 0,
  }),
  legendLine: (color) => ({
    width: 16, height: 0, borderTop: `2px solid ${color}`, flexShrink: 0,
  }),
  noData: {
    textAlign: 'center', padding: '48px 0', color: 'var(--yellow)',
    fontSize: 13,
  },
  loading: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    height: '60vh', color: 'var(--text-muted)', gap: 10, fontSize: 14,
  },
  // Gauge
  gaugeBar: {
    position: 'relative', height: 28, borderRadius: 20,
    overflow: 'hidden', background: 'var(--bg-elevated)',
    border: '1px solid var(--border-default)',
  },
  gaugeZone: (color, left, width) => ({
    position: 'absolute', top: 0, height: '100%',
    background: color, left: `${left}%`, width: `${width}%`,
  }),
  gaugeLine: (left) => ({
    position: 'absolute', top: 0, height: '100%', width: 2,
    background: 'rgba(255,214,0,0.7)', left: `${left}%`,
  }),
  gaugeMarker: (left) => ({
    position: 'absolute', top: 2, width: 14, height: 24,
    borderRadius: 3, background: 'var(--accent)',
    border: '1px solid #82b1ff', boxShadow: '0 2px 8px rgba(68,138,255,0.35)',
    left: `calc(${left}% - 7px)`,
  }),
  gaugeLabels: {
    display: 'flex', justifyContent: 'space-between', marginTop: 8,
    fontSize: 10,
  },
  // Flow / skew / stats sub-cards
  diagGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
    gap: 10,
  },
  diagCard: (borderColor) => ({
    borderRadius: 'var(--radius-md)',
    padding: '10px 12px',
    border: `1px solid ${borderColor || 'var(--border-subtle)'}`,
    background: 'var(--bg-card)',
  }),
  diagLabel: {
    fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4,
  },
  diagValue: {
    fontSize: 16, fontWeight: 700, color: '#fff',
    fontFamily: 'var(--font-mono)',
  },
  diagDesc: {
    fontSize: 10, color: 'var(--text-muted)', marginTop: 4,
  },
  sectionTitle: {
    fontSize: 13, fontWeight: 600, color: '#fff',
    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
  },
  sectionIcon: { color: 'var(--accent)', fontSize: 14 },
  interpretLine: {
    fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6,
    marginBottom: 6,
  },
  // Net GEX bar rows
  barRow: (refBg) => ({
    display: 'flex', alignItems: 'center', position: 'relative',
    background: refBg || 'transparent',
  }),
  barRefLabel: {
    width: 96, flexShrink: 0, textAlign: 'right', paddingRight: 8,
    fontSize: 9, fontWeight: 600,
  },
  barArea: {
    flex: 1, display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
    height: '100%', borderRight: '1px solid var(--border-default)',
  },
  barFill: (color, pct, h, isMagnet, isDanger) => ({
    width: `${Math.max(pct, 0.5)}%`,
    height: Math.min(Math.max(h - 4, 6), 18),
    borderRadius: '2px 0 0 2px',
    background: color,
    opacity: isMagnet ? 1 : isDanger ? 0.9 : 0.75,
    boxShadow: isMagnet ? '0 0 4px rgba(255,214,0,0.4)' : 'none',
  }),
  barStrike: (color) => ({
    width: 48, textAlign: 'right', fontSize: 10,
    fontFamily: 'var(--font-mono)', paddingLeft: 6,
    flexShrink: 0, color: color || 'var(--text-muted)',
    fontWeight: color ? 700 : 400,
  }),
  barTooltip: {
    position: 'absolute', right: 56, top: 0, zIndex: 50,
    background: 'rgba(10,10,20,0.95)', border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)', padding: '8px 12px',
    boxShadow: 'var(--shadow-lg)', fontSize: 11, minWidth: 200,
    pointerEvents: 'none', animation: 'sw-fadeIn 0.15s ease',
  },
};

// ── Page Component ──────────────────────────────────────────────

export default function GexProfilePage() {
  const [symbol, setSymbol] = useState('SPY');
  const [searchInput, setSearchInput] = useState('');
  const [data, setData] = useState(null);
  const [intradayTicks, setIntradayTicks] = useState([]);
  const [intradayBars, setIntradayBars] = useState([]);
  const [loading, setLoading] = useState(true);
  const [intradayLoading, setIntradayLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [chartView, setChartView] = useState('intraday');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [nextCandleCountdown, setNextCandleCountdown] = useState('');
  const [dataSource, setDataSource] = useState('tradier_live');
  const [isLive, setIsLive] = useState(false);
  const [sessionDate, setSessionDate] = useState(null);
  const [hoveredStrike, setHoveredStrike] = useState(null);

  // ── Fetch ─────────────────────────────────────────────────
  const fetchGexData = useCallback(async (sym, clearFirst = false) => {
    try {
      if (clearFirst) { setData(null); setLoading(true); }
      setError(null);
      const res = await fetch(`${API_URL}/api/spreadworks/gex-analysis?symbol=${sym}`);
      const result = await res.json();
      if (result?.success) {
        setData(result.data);
        setDataSource(result.source || 'tradier_live');
        setLastUpdated(new Date());
      } else if (result?.data_unavailable) {
        setError(result.message || 'Data unavailable — market may be closed');
      } else {
        setError('Failed to fetch GEX data');
      }
    } catch (err) {
      setError(err?.message || 'Failed to connect');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchIntradayTicks = useCallback(async (sym, clearFirst = false, useFallback = false) => {
    try {
      if (clearFirst) { setIntradayTicks([]); setIntradayBars([]); }
      setIntradayLoading(true);
      const fb = useFallback ? '&fallback=true' : '';
      const [ticksRes, barsRes] = await Promise.all([
        fetch(`${API_URL}/api/spreadworks/intraday-ticks?symbol=${sym}&interval=5${fb}`).then(r => r.json()),
        fetch(`${API_URL}/api/spreadworks/intraday-bars?symbol=${sym}&interval=5min${fb}`).then(r => r.json()),
      ]);
      if (ticksRes?.success && ticksRes?.data?.ticks) setIntradayTicks(ticksRes.data.ticks);
      if (barsRes?.success && barsRes?.data?.bars) {
        setIntradayBars(barsRes.data.bars);
        if (barsRes.data.session_date) setSessionDate(barsRes.data.session_date);
      }
    } catch (err) {
      console.error('Intraday ticks error:', err);
    } finally {
      setIntradayLoading(false);
    }
  }, []);

  const refreshBars = useCallback(async (sym) => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/intraday-bars?symbol=${sym}&interval=5min`);
      const json = await res.json();
      if (json?.success && json?.data?.bars) setIntradayBars(json.data.bars);
    } catch { /* silent */ }
  }, []);

  // Initial load + symbol change
  useEffect(() => {
    fetchGexData(symbol, true);
    fetchIntradayTicks(symbol, true, true);
  }, [symbol, fetchGexData, fetchIntradayTicks]);

  // Auto-refresh: bars every 10s, full GEX every 30s
  useEffect(() => {
    if (!autoRefresh) return;
    setIsLive(isMarketOpen());
    let tick = 0;
    const id = setInterval(() => {
      const open = isMarketOpen();
      setIsLive(open);
      if (!open) return;
      tick++;
      refreshBars(symbol);
      if (tick % 3 === 0) {
        fetchGexData(symbol, false);
        fetchIntradayTicks(symbol, false);
      }
    }, 10_000);
    return () => clearInterval(id);
  }, [autoRefresh, symbol, fetchGexData, fetchIntradayTicks, refreshBars]);

  // 5-minute candle countdown
  useEffect(() => {
    const calc = () => {
      const now = new Date();
      const secsIntoBar = (now.getMinutes() % 5) * 60 + now.getSeconds();
      const secsLeft = 5 * 60 - secsIntoBar;
      const m = Math.floor(secsLeft / 60);
      const sec = secsLeft % 60;
      setNextCandleCountdown(`${m}:${sec.toString().padStart(2, '0')}`);
    };
    calc();
    const id = setInterval(calc, 1000);
    return () => clearInterval(id);
  }, []);

  const handleSymbolSearch = () => {
    const sym = searchInput.trim().toUpperCase();
    if (sym && sym !== symbol) { setSymbol(sym); setSearchInput(''); }
  };

  // ── Derived data ──────────────────────────────────────────

  const latestTick = useMemo(() => {
    const valid = intradayTicks.filter(t => t.spot_price !== null);
    return valid.length > 0 ? valid[valid.length - 1] : null;
  }, [intradayTicks]);

  const interpretation = useMemo(() => {
    if (!data) return [];
    const { gamma_form, rating, gex_flip, price } = data.header;
    const { call_wall, put_wall } = data.levels;
    const lines = [];

    if (gamma_form === 'POSITIVE') {
      lines.push('Positive gamma regime — dealers are long gamma. Price tends to mean-revert. Favor selling premium (Iron Condors).');
    } else if (gamma_form === 'NEGATIVE') {
      lines.push('Negative gamma regime — dealers are short gamma. Price accelerates. Favor directional plays.');
    } else {
      lines.push('Neutral gamma regime — no strong dealer positioning.');
    }

    const aboveFlip = gex_flip ? price > gex_flip : null;
    if (aboveFlip === true) {
      lines.push(`Price above flip ($${gex_flip?.toFixed(0)}) — positive gamma territory, upside stability.`);
    } else if (aboveFlip === false) {
      lines.push(`Price below flip ($${gex_flip?.toFixed(0)}) — negative gamma territory, vulnerable to downside.`);
    }

    if (call_wall && price) {
      const d = ((call_wall - price) / price) * 100;
      if (d > 0 && d < 0.5) lines.push(`Call wall at $${call_wall.toFixed(0)} only ${d.toFixed(1)}% away — strong resistance.`);
    }
    if (put_wall && price) {
      const d = ((price - put_wall) / price) * 100;
      if (d > 0 && d < 0.5) lines.push(`Put wall at $${put_wall.toFixed(0)} only ${d.toFixed(1)}% away — strong support.`);
    }

    if (rating === 'BULLISH' && gamma_form === 'NEGATIVE') {
      lines.push('Divergence: bullish flow in negative gamma — explosive if momentum continues.');
    } else if (rating === 'BEARISH' && gamma_form === 'POSITIVE') {
      lines.push('Divergence: bearish flow in positive gamma — dealers may dampen the move.');
    }

    return lines;
  }, [data]);

  const barsByLabel = useMemo(() => {
    const map = {};
    for (const bar of intradayBars) {
      if (!bar.time) continue;
      map[tickTime(bar.time)] = bar;
    }
    return map;
  }, [intradayBars]);

  const intradayChartData = useMemo(() => {
    return intradayTicks
      .filter(t => t.spot_price !== null)
      .map((t, idx, arr) => {
        const label = t.time ? tickTime(t.time) : '';
        const bar = barsByLabel[label];
        return {
          ...t, label,
          net_gamma_display: t.net_gamma ?? 0,
          isLast: idx === arr.length - 1,
          open: bar?.open ?? null, high: bar?.high ?? null,
          low: bar?.low ?? null, close: bar?.close ?? null,
          bar_volume: bar?.volume ?? null,
        };
      });
  }, [intradayTicks, barsByLabel]);

  const sortedStrikes = useMemo(() => {
    if (!data?.gex_chart?.strikes) return [];
    const price = data.header.price || 0;
    return [...data.gex_chart.strikes]
      .filter(ss => Math.abs(ss.net_gamma) > 0.00001 || Math.abs(ss.call_gamma) > 0.000001)
      .sort((a, b) => Math.abs(a.strike - price) - Math.abs(b.strike - price))
      .slice(0, 40)
      .sort((a, b) => b.strike - a.strike)
      .map(ss => ({
        ...ss,
        abs_net_gamma: Math.abs(ss.net_gamma),
        put_gamma_display: -(ss.put_gamma || 0),
        gex_label: formatGex(ss.net_gamma, 2),
      }));
  }, [data]);

  // ── Render ────────────────────────────────────────────────

  if (loading && !data) {
    return (
      <div style={s.page}>
        <div style={s.loading}>
          <span style={{ animation: 'sw-spin 1s linear infinite', display: 'inline-block' }}>&#8635;</span>
          Loading GEX data...
        </div>
      </div>
    );
  }

  return (
    <div style={s.page}>
      {/* Title */}
      <div style={s.title}>
        <span style={{ color: 'var(--accent)' }}>&#9632;</span>
        GEX Profile
        {dataSource === 'trading_volatility' && (
          <span style={s.badge('rgba(168,85,247,0.15)', '#a855f7')}>Next-Day Profile</span>
        )}
      </div>
      <div style={s.subtitle}>
        {dataSource === 'trading_volatility'
          ? 'After-hours next-day gamma positioning — switches to live data at market open'
          : 'Gamma exposure by strike, intraday dynamics, and options flow'}
      </div>

      {/* Controls */}
      <div style={s.card}>
        <div style={s.controlsRow}>
          <div style={s.searchBox}>
            <span style={{ color: 'var(--text-muted)' }}>&#128269;</span>
            <input
              type="text"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && handleSymbolSearch()}
              placeholder="Symbol..."
              style={s.searchInput}
            />
            <button onClick={handleSymbolSearch} style={s.searchBtn}>&#8599;</button>
          </div>

          <span style={s.symbolLabel}>{symbol}</span>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {COMMON_SYMBOLS.filter(sym => sym !== symbol).slice(0, 6).map(sym => (
              <button key={sym} onClick={() => setSymbol(sym)} style={s.quickSymbol}>{sym}</button>
            ))}
          </div>

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setAutoRefresh(!autoRefresh)} style={s.autoBtn(autoRefresh)}>
              {autoRefresh ? 'Auto ON' : 'Auto OFF'}
            </button>
            <button
              onClick={() => { fetchGexData(symbol); fetchIntradayTicks(symbol); }}
              style={s.refreshBtn}
              disabled={loading}
            >
              <span style={loading ? { animation: 'sw-spin 1s linear infinite', display: 'inline-block' } : {}}>&#8635;</span>
            </button>
            {lastUpdated && (
              <span style={s.timestamp}>
                {lastUpdated.toLocaleTimeString('en-US', {
                  timeZone: 'America/Chicago',
                  hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true,
                })} CT
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={s.errorBox}>
          <span>&#9888;</span>
          <span>{error}</span>
        </div>
      )}

      {data && (
        <>
          {/* Header Metrics */}
          <div style={s.metricsGrid}>
            <MetricCard label="Price" value={formatDollar(data.header.price)} color="var(--accent)" />
            <MetricCard
              label="Net GEX" value={formatGex(data.header.net_gex)}
              color={data.header.net_gex >= 0 ? 'var(--green)' : 'var(--red)'}
              badge={data.header.gamma_form}
              badgeBg={data.header.gamma_form === 'POSITIVE' ? 'var(--green-dim)' : data.header.gamma_form === 'NEGATIVE' ? 'var(--red-dim)' : 'var(--bg-elevated)'}
              badgeFg={data.header.gamma_form === 'POSITIVE' ? 'var(--green)' : data.header.gamma_form === 'NEGATIVE' ? 'var(--red)' : 'var(--text-muted)'}
            />
            <MetricCard
              label="Flip Point"
              value={data.levels.gex_flip ? formatDollar(data.levels.gex_flip) : '—'}
              color="var(--yellow)"
              sub={data.levels.gex_flip ? `${((data.header.price - data.levels.gex_flip) / data.header.price * 100).toFixed(1)}% from price` : undefined}
            />
            <MetricCard
              label="Call Wall"
              value={data.levels.call_wall ? formatDollar(data.levels.call_wall) : '—'}
              color="#06b6d4"
              sub={data.levels.call_wall ? `+${((data.levels.call_wall - data.header.price) / data.header.price * 100).toFixed(1)}% away` : undefined}
            />
            <MetricCard
              label="Put Wall"
              value={data.levels.put_wall ? formatDollar(data.levels.put_wall) : '—'}
              color="#a855f7"
              sub={data.levels.put_wall ? `-${((data.header.price - data.levels.put_wall) / data.header.price * 100).toFixed(1)}% away` : undefined}
            />
            <MetricCard
              label="Rating" value={data.header.rating}
              color={data.header.rating === 'BULLISH' ? 'var(--green)' : data.header.rating === 'BEARISH' ? 'var(--red)' : 'var(--text-muted)'}
              sub={data.header['30_day_vol'] ? `VIX ${data.header['30_day_vol'].toFixed(1)}` : undefined}
            />
          </div>

          {/* Chart Section */}
          <div style={s.card}>
            <div style={s.chartHeader}>
              <div style={s.chartTitle}>
                <span style={{ color: 'var(--accent)' }}>&#9632;</span>
                {chartView === 'intraday'
                  ? `${symbol} Intraday 5m — Price + Net Gamma`
                  : `${symbol} ${chartView === 'net' ? 'Net' : 'Call vs Put'} GEX by Strike — ${data.expiration}`}
                {chartView === 'intraday' && isLive && (
                  <span style={s.liveBadge}><span style={s.liveDot} />LIVE</span>
                )}
                {chartView === 'intraday' && !isLive && intradayBars.length > 0 && (
                  <span style={s.closedBadge}>
                    Market Closed{sessionDate && ` · Showing ${sessionDate} session`}
                  </span>
                )}
                {chartView === 'intraday' && nextCandleCountdown && (
                  <span style={s.countdownBadge}>Next candle: {nextCandleCountdown}</span>
                )}
              </div>
              <div style={s.chartTabs}>
                {['net', 'split', 'intraday'].map(view => (
                  <button key={view} onClick={() => setChartView(view)} style={s.chartTab(chartView === view)}>
                    {view === 'net' ? 'Net GEX' : view === 'split' ? 'Call vs Put' : 'Intraday 5m'}
                  </button>
                ))}
              </div>
            </div>

            {/* INTRADAY 5M — Candlestick + GEX overlay (Plotly) */}
            {chartView === 'intraday' && (
              intradayBars.length === 0 && intradayChartData.length === 0 ? (
                <div style={s.noData}>
                  {intradayLoading
                    ? 'Loading intraday data...'
                    : 'No intraday data yet — ticks accumulate during market hours.'}
                </div>
              ) : (
                <IntradayChart
                  intradayBars={intradayBars}
                  intradayChartData={intradayChartData}
                  sortedStrikes={sortedStrikes}
                  data={data}
                  isLive={isLive}
                  sessionDate={sessionDate}
                />
              )
            )}

            {/* NET GEX BY STRIKE */}
            {chartView === 'net' && (
              sortedStrikes.length === 0 ? (
                <div style={s.noData}>Real-time data not available outside market hours (8:30 AM – 3:00 PM CT)</div>
              ) : (
                <NetGexView
                  sortedStrikes={sortedStrikes}
                  data={data}
                  hoveredStrike={hoveredStrike}
                  setHoveredStrike={setHoveredStrike}
                />
              )
            )}

            {/* CALL VS PUT */}
            {chartView === 'split' && (
              sortedStrikes.length === 0 ? (
                <div style={s.noData}>Real-time data not available outside market hours (8:30 AM – 3:00 PM CT)</div>
              ) : (
                <CallVsPutView sortedStrikes={sortedStrikes} data={data} />
              )
            )}
          </div>

          {/* Price Position Gauge */}
          <PriceGauge
            price={latestTick?.spot_price ?? data.header.price}
            flipPoint={latestTick?.flip_point ?? data.levels.gex_flip ?? 0}
            callWall={latestTick?.call_wall ?? data.levels.call_wall ?? 0}
            putWall={latestTick?.put_wall ?? data.levels.put_wall ?? 0}
          />

          {/* Market Interpretation */}
          {interpretation.length > 0 && (
            <div style={s.card}>
              <div style={s.sectionTitle}>
                <span style={s.sectionIcon}>&#9432;</span>
                Market Interpretation
              </div>
              {interpretation.map((line, i) => (
                <p key={i} style={s.interpretLine}>{line}</p>
              ))}
            </div>
          )}

          {/* Flow Diagnostics */}
          {data.flow_diagnostics?.cards?.length > 0 && (
            <div style={s.card}>
              <div style={s.sectionTitle}>
                <span style={s.sectionIcon}>&#9875;</span>
                Options Flow Diagnostics
              </div>
              <div style={s.diagGrid}>
                {data.flow_diagnostics.cards.map(card => (
                  <div key={card.id} style={s.diagCard(getCardBorder(card))}>
                    <div style={s.diagLabel}>{card.label}</div>
                    <div style={s.diagValue}>{card.metric_value}</div>
                    <div style={s.diagDesc}>{card.description}</div>
                  </div>
                ))}
              </div>
              {data.flow_diagnostics.note && (
                <p style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 8 }}>{data.flow_diagnostics.note}</p>
              )}
            </div>
          )}

          {/* Skew Measures */}
          {data.skew_measures && (
            <div style={s.card}>
              <div style={s.sectionTitle}>
                <span style={s.sectionIcon}>&#8593;</span>
                Skew Measures
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
                <SkewCard label="Skew Ratio" value={data.skew_measures.skew_ratio.toFixed(3)} desc={data.skew_measures.skew_ratio_description} />
                <SkewCard label="Call Skew" value={data.skew_measures.call_skew.toFixed(3)} desc={data.skew_measures.call_skew_description} />
                <SkewCard
                  label="ATM IV"
                  value={`C: ${data.skew_measures.atm_call_iv?.toFixed(1) ?? '—'}% / P: ${data.skew_measures.atm_put_iv?.toFixed(1) ?? '—'}%`}
                  desc="At-the-money implied volatility"
                />
                <SkewCard
                  label="OTM Avg IV"
                  value={`C: ${data.skew_measures.avg_otm_call_iv?.toFixed(1) ?? '—'}% / P: ${data.skew_measures.avg_otm_put_iv?.toFixed(1) ?? '—'}%`}
                  desc="Out-of-the-money average IV"
                />
              </div>
            </div>
          )}

          {/* Summary Stats */}
          {data.summary && (
            <div style={s.card}>
              <div style={s.sectionTitle}>
                <span style={s.sectionIcon}>&#9632;</span>
                Volume & Open Interest
              </div>
              <div style={s.diagGrid}>
                <StatCard label="Total Volume" value={data.summary.total_volume.toLocaleString()} />
                <StatCard label="Call Volume" value={data.summary.total_call_volume.toLocaleString()} color="var(--green)" />
                <StatCard label="Put Volume" value={data.summary.total_put_volume.toLocaleString()} color="var(--red)" />
                <StatCard label="Total OI" value={(data.summary.total_call_oi + data.summary.total_put_oi).toLocaleString()} />
                <StatCard
                  label="P/C Ratio" value={data.summary.put_call_ratio.toFixed(2)}
                  color={data.summary.put_call_ratio > 1 ? 'var(--red)' : 'var(--green)'}
                />
                <StatCard
                  label="Net GEX" value={formatGex(data.summary.net_gex)}
                  color={data.summary.net_gex >= 0 ? 'var(--green)' : 'var(--red)'}
                />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Sub-Components ──────────────────────────────────────────────

function MetricCard({ label, value, color, badge, badgeBg, badgeFg, sub }) {
  return (
    <div style={s.metricCard}>
      <div style={s.metricLabel}>{label}</div>
      <div style={s.metricValue(color)}>
        {value}
        {badge && <span style={s.badge(badgeBg, badgeFg)}>{badge}</span>}
      </div>
      {sub && <div style={s.metricSub}>{sub}</div>}
    </div>
  );
}

function PriceGauge({ price, flipPoint, callWall, putWall }) {
  if (!price || !callWall || !putWall || callWall <= putWall) return null;

  const range = callWall - putWall;
  const pricePos = Math.max(0, Math.min(100, ((price - putWall) / range) * 100));
  const flipPos = Math.max(0, Math.min(100, ((flipPoint - putWall) / range) * 100));
  const aboveFlip = price > flipPoint;
  const distToCall = ((callWall - price) / price * 100).toFixed(1);
  const distToPut = ((price - putWall) / price * 100).toFixed(1);

  return (
    <div style={s.card}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'center' }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          Price Position in GEX Structure
        </span>
        <span style={{ fontSize: 11, fontWeight: 700, color: aboveFlip ? 'var(--green)' : 'var(--red)' }}>
          {aboveFlip ? 'POSITIVE GAMMA ZONE' : 'NEGATIVE GAMMA ZONE'}
        </span>
      </div>
      <div style={s.gaugeBar}>
        <div style={s.gaugeZone('rgba(255,82,82,0.1)', 0, flipPos)} />
        <div style={s.gaugeZone('rgba(0,230,118,0.1)', flipPos, 100 - flipPos)} />
        <div style={s.gaugeLine(flipPos)} />
        <div style={s.gaugeMarker(pricePos)} />
      </div>
      <div style={s.gaugeLabels}>
        <span style={{ color: '#a855f7' }}>
          Put Wall ${putWall.toFixed(0)} <span style={{ color: 'var(--text-muted)' }}>({distToPut}% away)</span>
        </span>
        <span style={{ color: 'var(--yellow)' }}>Flip ${flipPoint.toFixed(0)}</span>
        <span style={{ color: '#06b6d4' }}>
          <span style={{ color: 'var(--text-muted)' }}>({distToCall}% away)</span> Call Wall ${callWall.toFixed(0)}
        </span>
      </div>
    </div>
  );
}

function IntradayChart({ intradayBars, intradayChartData, sortedStrikes, data, isLive, sessionDate }) {
  const plotData = useMemo(() => {
    const candleTimes = intradayBars.map(b => toCentralPlotly(b.time));
    const hasCandleData = intradayBars.length > 0;
    const spotTimes = intradayChartData.map(d => toCentralPlotly(d.time));
    const spotPrices = intradayChartData.map(d => d.spot_price);

    const priceValues = hasCandleData
      ? [...intradayBars.map(b => b.high), ...intradayBars.map(b => b.low)]
      : spotPrices.filter(p => p !== null);
    const priceMin = priceValues.length > 0 ? Math.min(...priceValues) : 0;
    const priceMax = priceValues.length > 0 ? Math.max(...priceValues) : 0;
    const priceRange = priceMax - priceMin || 1;
    const visibleStrikes = sortedStrikes.filter(ss =>
      ss.strike >= priceMin - priceRange * 1.5 && ss.strike <= priceMax + priceRange * 1.5
    );

    const maxGamma = visibleStrikes.length > 0
      ? Math.max(...visibleStrikes.map(ss => ss.abs_net_gamma), 0.001) : 1;
    const barMaxWidth = 0.35;
    const strikeSpacing = visibleStrikes.length > 1
      ? Math.abs(visibleStrikes[0].strike - visibleStrikes[1].strike) * 0.35 : 0.5;

    const gexShapes = visibleStrikes.map(ss => {
      const pct = (ss.abs_net_gamma / maxGamma) * barMaxWidth;
      const color = ss.net_gamma >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)';
      const borderColor = ss.net_gamma >= 0 ? 'rgba(34,197,94,0.9)' : 'rgba(239,68,68,0.9)';
      return {
        type: 'rect', xref: 'paper', yref: 'y',
        x0: 1, x1: 1 - pct,
        y0: ss.strike - strikeSpacing, y1: ss.strike + strikeSpacing,
        fillcolor: color, line: { color: borderColor, width: 1 }, layer: 'above',
      };
    });

    const gexAnnotations = visibleStrikes
      .filter(ss => ss.abs_net_gamma / maxGamma > 0.08)
      .map(ss => ({
        xref: 'paper', yref: 'y',
        x: 1 - (ss.abs_net_gamma / maxGamma) * barMaxWidth - 0.005,
        y: ss.strike,
        text: `${formatGex(ss.net_gamma, 1)} [$${ss.strike}]`,
        showarrow: false,
        font: { color: ss.net_gamma >= 0 ? '#22c55e' : '#ef4444', size: 9, family: 'monospace' },
        xanchor: 'right', yanchor: 'middle',
      }));

    const refLines = [];
    const { gex_flip: flip, call_wall: cw, put_wall: pw, upper_1sd, lower_1sd, expected_move } = data.levels;
    if (flip) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: flip, y1: flip, line: { color: '#eab308', width: 2.5, dash: 'dash' } });
    if (cw) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: cw, y1: cw, line: { color: '#06b6d4', width: 2.5, dash: 'dot' } });
    if (pw) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: pw, y1: pw, line: { color: '#a855f7', width: 2.5, dash: 'dot' } });
    if (upper_1sd) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: upper_1sd, y1: upper_1sd, line: { color: '#f97316', width: 1.5, dash: 'dashdot' } });
    if (lower_1sd) refLines.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: lower_1sd, y1: lower_1sd, line: { color: '#f97316', width: 1.5, dash: 'dashdot' } });
    if (upper_1sd && lower_1sd) refLines.push({
      type: 'rect', xref: 'paper', yref: 'y',
      x0: 0, x1: 1, y0: lower_1sd, y1: upper_1sd,
      fillcolor: 'rgba(249,115,22,0.06)', line: { width: 0 }, layer: 'below',
    });

    const yPoints = [...priceValues];
    if (flip) yPoints.push(flip);
    if (cw) yPoints.push(cw);
    if (pw) yPoints.push(pw);
    if (upper_1sd) yPoints.push(upper_1sd);
    if (lower_1sd) yPoints.push(lower_1sd);
    const yMin = yPoints.length > 0 ? Math.min(...yPoints) : 0;
    const yMax = yPoints.length > 0 ? Math.max(...yPoints) : 0;
    const yPad = (yMax - yMin) * 0.35 || 4;
    const yRange = [yMin - yPad, yMax + yPad];

    const refAnnotations = [];
    if (flip) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.01, y: flip, text: `FLIP $${flip.toFixed(0)}`, showarrow: false, font: { color: '#eab308', size: 10 }, xanchor: 'left', yanchor: 'bottom', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });
    if (cw) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.01, y: cw, text: `CALL WALL $${cw.toFixed(0)}`, showarrow: false, font: { color: '#06b6d4', size: 10 }, xanchor: 'left', yanchor: 'bottom', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });
    if (pw) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.01, y: pw, text: `PUT WALL $${pw.toFixed(0)}`, showarrow: false, font: { color: '#a855f7', size: 10 }, xanchor: 'left', yanchor: 'top', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });
    if (upper_1sd) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.99, y: upper_1sd, text: `+1σ $${upper_1sd.toFixed(0)}${expected_move ? ` (EM $${expected_move.toFixed(1)})` : ''}`, showarrow: false, font: { color: '#f97316', size: 9 }, xanchor: 'right', yanchor: 'bottom', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });
    if (lower_1sd) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.99, y: lower_1sd, text: `-1σ $${lower_1sd.toFixed(0)}`, showarrow: false, font: { color: '#f97316', size: 9 }, xanchor: 'right', yanchor: 'top', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });

    const traces = [];
    if (hasCandleData) {
      traces.push({
        x: candleTimes,
        open: intradayBars.map(b => b.open), high: intradayBars.map(b => b.high),
        low: intradayBars.map(b => b.low), close: intradayBars.map(b => b.close),
        type: 'candlestick',
        increasing: { line: { color: '#22c55e' }, fillcolor: 'rgba(34,197,94,0.3)' },
        decreasing: { line: { color: '#ef4444' }, fillcolor: 'rgba(239,68,68,0.8)' },
        name: 'Price', hoverinfo: 'x+text',
        text: intradayBars.map(b =>
          `O:${b.open.toFixed(2)} H:${b.high.toFixed(2)} L:${b.low.toFixed(2)} C:${b.close.toFixed(2)}<br>Vol:${b.volume.toLocaleString()}`
        ),
      });
    } else {
      traces.push({
        x: spotTimes, y: spotPrices,
        type: 'scatter', mode: 'lines',
        line: { color: '#3b82f6', width: 2.5 }, name: 'Price',
      });
    }

    return { traces, shapes: [...gexShapes, ...refLines], annotations: [...gexAnnotations, ...refAnnotations], yRange, hasCandleData };
  }, [intradayBars, intradayChartData, sortedStrikes, data]);

  return (
    <>
      <div style={{ height: 550 }}>
        <Plot
          data={plotData.traces}
          layout={{
            height: 550,
            paper_bgcolor: '#0a0a14',
            plot_bgcolor: '#0f0f1e',
            font: { color: '#9ca3af', family: 'Inter, Arial, sans-serif', size: 11 },
            xaxis: {
              type: 'date', gridcolor: '#1a1a2e', showgrid: true,
              rangeslider: { visible: false },
              hoverformat: '%I:%M %p CT', tickformat: '%I:%M %p',
            },
            yaxis: {
              title: { text: 'Price', font: { size: 11, color: '#6b7280' } },
              gridcolor: '#1a1a2e', showgrid: true, side: 'right',
              tickformat: '$,.0f', range: plotData.yRange, autorange: false,
            },
            shapes: plotData.shapes,
            annotations: plotData.annotations,
            margin: { t: 10, b: 40, l: 10, r: 60 },
            hovermode: 'x unified',
            showlegend: false,
            transition: { duration: 300, easing: 'cubic-in-out' },
          }}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: '100%', height: '100%' }}
        />
      </div>
      <div style={s.legend}>
        {plotData.hasCandleData ? (
          <>
            <LegendItem color="#22c55e" label="Bullish" />
            <LegendItem color="#ef4444" label="Bearish" />
          </>
        ) : (
          <LegendItem color="#3b82f6" label="Price" line />
        )}
        <span style={s.legendSep}>|</span>
        <span style={{ color: '#22c55e', fontWeight: 600 }}>&#9632; +GEX Bar</span>
        <span style={{ color: '#ef4444', fontWeight: 600 }}>&#9632; -GEX Bar</span>
        <span style={s.legendSep}>|</span>
        <span style={{ color: '#eab308' }}>--- Flip</span>
        <span style={{ color: '#06b6d4' }}>... Call Wall</span>
        <span style={{ color: '#a855f7' }}>... Put Wall</span>
        <span style={{ color: '#f97316' }}>-.- ±1σ</span>
        <span style={s.legendSep}>|</span>
        {isLive
          ? <span style={s.liveBadge}><span style={s.liveDot} />LIVE</span>
          : <span style={{ color: 'var(--text-muted)' }}>Market Closed</span>}
        <span style={s.legendSep}>|</span>
        <span style={{ color: 'var(--text-muted)' }}>
          {intradayBars.length} bars{sessionDate ? ` · ${sessionDate}` : ''}
        </span>
      </div>
    </>
  );
}

function NetGexView({ sortedStrikes, data, hoveredStrike, setHoveredStrike }) {
  const maxGamma = Math.max(...sortedStrikes.map(ss => ss.abs_net_gamma), 0.001);
  const { price, gex_flip: flip, call_wall: cw, put_wall: pw } = data.levels;
  const rowH = Math.max(Math.floor(540 / sortedStrikes.length), 12);

  const nearest = (target) => {
    if (!target || !sortedStrikes.length) return -1;
    let best = 0, bestD = Infinity;
    sortedStrikes.forEach((ss, i) => { const d = Math.abs(ss.strike - target); if (d < bestD) { bestD = d; best = i; } });
    return best;
  };
  const priceIdx = nearest(price);
  const flipIdx = nearest(flip);
  const cwIdx = nearest(cw);
  const pwIdx = nearest(pw);

  return (
    <>
      <div style={{ height: 550, overflowY: 'auto' }}>
        {sortedStrikes.map((entry, i) => {
          const pct = (entry.abs_net_gamma / maxGamma) * 100;
          const pos = entry.net_gamma >= 0;
          const atPrice = i === priceIdx;
          const atFlip = i === flipIdx && flipIdx !== priceIdx;
          const atCW = i === cwIdx && cwIdx !== priceIdx;
          const atPW = i === pwIdx && pwIdx !== priceIdx;

          const refBg = atPrice ? 'rgba(68,138,255,0.08)'
            : atFlip ? 'rgba(234,179,8,0.06)'
            : atCW ? 'rgba(6,182,212,0.06)'
            : atPW ? 'rgba(168,85,247,0.06)' : undefined;

          const borderTop = atPrice ? '2px solid rgba(68,138,255,0.5)'
            : atFlip ? '2px solid rgba(234,179,8,0.4)'
            : atCW ? '2px solid rgba(6,182,212,0.4)'
            : atPW ? '2px solid rgba(168,85,247,0.4)' : undefined;

          const strikeColor = atPrice ? '#448aff'
            : atFlip ? '#eab308'
            : atCW ? '#06b6d4'
            : atPW ? '#a855f7' : undefined;

          const isHovered = hoveredStrike === entry.strike;

          return (
            <div
              key={entry.strike}
              style={{ ...s.barRow(refBg), height: rowH, borderTop, borderBottom: borderTop }}
              onMouseEnter={() => setHoveredStrike(entry.strike)}
              onMouseLeave={() => setHoveredStrike(null)}
            >
              <div style={s.barRefLabel}>
                {atPrice && <span style={{ color: '#448aff' }}>PRICE ${price?.toFixed(0)}</span>}
                {atFlip && <span style={{ color: '#eab308' }}>FLIP ${flip?.toFixed(0)}</span>}
                {atCW && <span style={{ color: '#06b6d4' }}>CALL WALL</span>}
                {atPW && <span style={{ color: '#a855f7' }}>PUT WALL</span>}
              </div>
              <div style={s.barArea}>
                <div style={s.barFill(pos ? '#22c55e' : '#ef4444', pct, rowH, entry.is_magnet, entry.is_danger)} />
              </div>
              <div style={s.barStrike(strikeColor)}>
                {entry.strike}
              </div>
              {isHovered && (
                <div style={s.barTooltip}>
                  <div style={{ fontWeight: 700, color: '#fff', marginBottom: 4 }}>${entry.strike}</div>
                  <div style={{ fontWeight: 600, color: pos ? '#22c55e' : '#ef4444', marginBottom: 4 }}>
                    Net GEX: {entry.gex_label}
                  </div>
                  <div style={{ color: 'var(--text-muted)', lineHeight: 1.8 }}>
                    <div>Call GEX: <span style={{ color: '#22c55e' }}>{formatGex(entry.call_gamma, 2)}</span></div>
                    <div>Put GEX: <span style={{ color: '#ef4444' }}>{formatGex(entry.put_gamma, 2)}</span></div>
                    {entry.call_iv && <div>Call IV: {(entry.call_iv * 100).toFixed(1)}%</div>}
                    {entry.put_iv && <div>Put IV: {(entry.put_iv * 100).toFixed(1)}%</div>}
                    <div>Volume: {entry.total_volume?.toLocaleString()}</div>
                  </div>
                  {entry.is_magnet && <div style={{ color: '#eab308', fontWeight: 600, marginTop: 4 }}>Magnet Strike</div>}
                  {entry.is_pin && <div style={{ color: '#a855f7', fontWeight: 600, marginTop: 4 }}>Pin Strike</div>}
                  {entry.is_danger && <div style={{ color: '#ef4444', fontWeight: 600, marginTop: 4 }}>{entry.danger_type}</div>}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div style={s.legend}>
        <LegendItem color="#22c55e" label="Positive Gamma" />
        <LegendItem color="#ef4444" label="Negative Gamma" />
        <span style={s.legendSep}>|</span>
        <span style={{ color: '#448aff' }}>— Price</span>
        <span style={{ color: '#eab308' }}>--- Flip</span>
        <span style={{ color: '#06b6d4' }}>--- Call Wall</span>
        <span style={{ color: '#a855f7' }}>--- Put Wall</span>
      </div>
    </>
  );
}

function CallVsPutView({ sortedStrikes, data }) {
  return (
    <>
      <div style={{ height: 550 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={sortedStrikes} layout="vertical" margin={{ top: 5, right: 90, left: 60, bottom: 5 }}>
            <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={v => formatGex(v, 4)} axisLine={{ stroke: '#1a1a2e' }} />
            <YAxis type="category" dataKey="strike" tick={{ fill: '#9ca3af', fontSize: 10 }} width={50} axisLine={{ stroke: '#1a1a2e' }} />
            <Tooltip content={<StrikeTooltip />} />
            {data.levels.gex_flip && (
              <ReferenceLine y={data.levels.gex_flip} stroke="#eab308" strokeDasharray="5 3"
                label={{ value: `Flip ${data.levels.gex_flip}`, fill: '#eab308', fontSize: 9, position: 'right' }} />
            )}
            <ReferenceLine y={data.levels.price} stroke="#3b82f6" strokeWidth={2}
              label={{ value: `Price ${data.levels.price}`, fill: '#3b82f6', fontSize: 9, position: 'right' }} />
            {data.levels.call_wall && (
              <ReferenceLine y={data.levels.call_wall} stroke="#06b6d4" strokeDasharray="3 3"
                label={{ value: 'Call Wall', fill: '#06b6d4', fontSize: 9, position: 'right' }} />
            )}
            {data.levels.put_wall && (
              <ReferenceLine y={data.levels.put_wall} stroke="#a855f7" strokeDasharray="3 3"
                label={{ value: 'Put Wall', fill: '#a855f7', fontSize: 9, position: 'right' }} />
            )}
            <Bar dataKey="call_gamma" name="Call Gamma" fill="#22c55e" fillOpacity={0.75} />
            <Bar dataKey="put_gamma_display" name="Put Gamma" fill="#ef4444" fillOpacity={0.75} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div style={s.legend}>
        <LegendItem color="#22c55e" label="Call Gamma" />
        <LegendItem color="#ef4444" label="Put Gamma" />
      </div>
    </>
  );
}

function StrikeTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div style={{
      background: 'rgba(10,10,20,0.95)', border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)', padding: '10px 14px',
      boxShadow: 'var(--shadow-lg)', fontSize: 11, minWidth: 220,
    }}>
      <div style={{ fontWeight: 700, color: '#fff', fontSize: 13, marginBottom: 6 }}>
        Strike: ${label}
        {d.is_magnet && <span style={s.badge('rgba(234,179,8,0.15)', '#eab308')}> MAGNET{d.magnet_rank ? ` #${d.magnet_rank}` : ''}</span>}
        {d.is_pin && <span style={s.badge('rgba(168,85,247,0.15)', '#a855f7')}> PIN</span>}
        {d.is_danger && <span style={s.badge('rgba(239,68,68,0.15)', '#ef4444')}> {d.danger_type}</span>}
      </div>
      <TipRow label="Net Gamma" value={formatGex(d.net_gamma, 4)} color={d.net_gamma >= 0 ? '#22c55e' : '#ef4444'} bold />
      <TipRow label="Call Gamma" value={d.call_gamma?.toFixed(6)} color="#22c55e" />
      <TipRow label="Put Gamma" value={d.put_gamma?.toFixed(6)} color="#ef4444" />
      <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: 4, marginTop: 4 }}>
        <TipRow label="Call Vol / Put Vol" value={`${(d.call_volume || 0).toLocaleString()} / ${(d.put_volume || 0).toLocaleString()}`} color="#fff" />
        <TipRow label="Call OI / Put OI" value={`${(d.call_oi || 0).toLocaleString()} / ${(d.put_oi || 0).toLocaleString()}`} color="#fff" />
      </div>
      {(d.call_iv || d.put_iv) && (
        <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: 4, marginTop: 4 }}>
          <TipRow label="Call IV / Put IV" value={`${d.call_iv ? `${d.call_iv}%` : 'N/A'} / ${d.put_iv ? `${d.put_iv}%` : 'N/A'}`} color="#fff" />
        </div>
      )}
    </div>
  );
}

function TipRow({ label, value, color, bold }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}:</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: bold ? 700 : 400, color }}>{value}</span>
    </div>
  );
}

function LegendItem({ color, label, line, small }) {
  return (
    <div style={s.legendItem(color)}>
      {line ? (
        <div style={s.legendLine(color)} />
      ) : (
        <div style={s.legendDot(color, small)} />
      )}
      <span>{label}</span>
    </div>
  );
}

function SkewCard({ label, value, desc }) {
  return (
    <div style={s.diagCard('var(--border-subtle)')}>
      <div style={s.diagLabel}>{label}</div>
      <div style={s.diagValue}>{value}</div>
      <div style={s.diagDesc}>{desc}</div>
    </div>
  );
}

function StatCard({ label, value, color = '#fff' }) {
  return (
    <div style={s.diagCard('var(--border-subtle)')}>
      <div style={s.diagLabel}>{label}</div>
      <div style={{ ...s.diagValue, color }}>{value}</div>
    </div>
  );
}

function getCardBorder(card) {
  if (card.id === 'volume_pressure' && card.raw_value > 0.1) return 'rgba(6,182,212,0.4)';
  if (card.id === 'call_share' && card.raw_value > 55) return 'rgba(6,182,212,0.4)';
  if (card.id === 'short_dte_share' && card.raw_value > 50) return 'rgba(6,182,212,0.4)';
  if (card.id === 'volume_pressure' && card.raw_value < -0.1) return 'rgba(239,68,68,0.4)';
  if (card.id === 'lotto_turnover' && card.raw_value > 0.3) return 'rgba(234,179,8,0.4)';
  return 'var(--border-subtle)';
}
