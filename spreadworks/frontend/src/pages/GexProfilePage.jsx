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
import { Activity, Search, RefreshCw, ArrowUpRight, AlertTriangle, Info, Anchor, BarChart3, TrendingUp, Send } from 'lucide-react';

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
  const [discordMsg, setDiscordMsg] = useState('');
  const [discordPushing, setDiscordPushing] = useState(false);

  const pushToDiscord = useCallback(async (view) => {
    const endpointMap = {
      net: 'push-gex-net',
      split: 'push-gex-callput',
      intraday: 'push-gex-intraday',
    };
    const endpoint = endpointMap[view];
    if (!endpoint) return;
    try {
      setDiscordPushing(true);
      setDiscordMsg('');
      const res = await fetch(`${API_URL}/api/spreadworks/discord/${endpoint}?symbol=${symbol}`, {
        method: 'POST',
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Failed to post');
      setDiscordMsg('Posted!');
    } catch (err) {
      setDiscordMsg(err.message);
    } finally {
      setDiscordPushing(false);
      setTimeout(() => setDiscordMsg(''), 3000);
    }
  }, [symbol]);

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
      <div className="min-h-screen bg-bg-base px-6 py-5 font-[var(--font-ui)]">
        <div className="flex items-center justify-center h-[60vh] text-text-muted gap-2.5 text-sm">
          <span className="inline-block animate-[sw-spin_1s_linear_infinite]">&#8635;</span>
          Loading GEX data...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-base px-6 py-5 font-[var(--font-ui)]">
      {/* Title */}
      <div className="flex items-center gap-2.5 text-[22px] font-extrabold text-white tracking-tight mb-1">
        <Activity size={28} className="text-accent" />
        GEX Profile
        {dataSource === 'trading_volatility' && (
          <span className="text-[10px] font-semibold px-1.5 py-px rounded-[var(--radius-sm)] bg-[rgba(168,85,247,0.15)] text-[#a855f7]">Next-Day Profile</span>
        )}
      </div>
      <div className="text-text-muted text-[13px] mb-5">
        {dataSource === 'trading_volatility'
          ? 'After-hours next-day gamma positioning — switches to live data at market open'
          : 'Gamma exposure by strike, intraday dynamics, and options flow'}
      </div>

      {/* Controls */}
      <div className="sw-card p-4 mb-4">
        <div className="flex flex-wrap items-center gap-3.5">
          <div className="flex items-center gap-2 bg-bg-elevated rounded-[var(--radius-md)] border border-border-default px-3 py-1.5">
            <Search size={14} className="text-text-muted" />
            <input
              type="text"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && handleSymbolSearch()}
              placeholder="Symbol..."
              className="bg-transparent border-none outline-none text-white text-[13px] font-[var(--font-ui)] w-20"
            />
            <button onClick={handleSymbolSearch} className="bg-transparent border-none text-accent cursor-pointer p-0 text-sm">
              <ArrowUpRight size={14} />
            </button>
          </div>

          <span className="text-[22px] font-extrabold text-white font-[var(--font-mono)]">{symbol}</span>

          <div className="flex flex-wrap gap-1">
            {COMMON_SYMBOLS.filter(sym => sym !== symbol).slice(0, 6).map(sym => (
              <button
                key={sym}
                onClick={() => setSymbol(sym)}
                className="px-2 py-0.5 text-[11px] rounded-[var(--radius-sm)] bg-bg-elevated border border-border-subtle text-text-tertiary cursor-pointer transition-all duration-150 hover:border-border-default hover:text-text-secondary"
              >
                {sym}
              </button>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-2.5">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`text-[11px] px-2.5 py-1 rounded-[var(--radius-sm)] font-semibold cursor-pointer transition-all duration-150 ${
                autoRefresh
                  ? 'border border-[rgba(34,197,94,0.3)] bg-sw-green-dim text-sw-green'
                  : 'border border-border-default bg-bg-elevated text-text-muted'
              }`}
            >
              {autoRefresh ? 'Auto ON' : 'Auto OFF'}
            </button>
            <button
              onClick={() => { fetchGexData(symbol); fetchIntradayTicks(symbol); }}
              className="bg-transparent border-none text-text-muted cursor-pointer text-base p-1"
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? 'animate-[sw-spin_1s_linear_infinite]' : ''} />
            </button>
            {lastUpdated && (
              <span className="text-[10px] text-text-muted font-[var(--font-mono)]">
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
        <div className="bg-sw-red-dim border border-[rgba(239,68,68,0.3)] rounded-[var(--radius-lg)] px-4 py-3 flex items-center gap-2.5 mb-4 text-sw-red text-[13px]">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {data && (
        <>
          {/* Header Metrics */}
          <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-2.5 mb-4">
            <MetricCard label="Price" value={formatDollar(data.header.price)} color="var(--color-accent)" />
            <MetricCard
              label="Net GEX" value={formatGex(data.header.net_gex)}
              color={data.header.net_gex >= 0 ? 'var(--color-sw-green)' : 'var(--color-sw-red)'}
              badge={data.header.gamma_form}
              badgeBg={data.header.gamma_form === 'POSITIVE' ? 'var(--color-sw-green-dim)' : data.header.gamma_form === 'NEGATIVE' ? 'var(--color-sw-red-dim)' : 'var(--color-bg-elevated)'}
              badgeFg={data.header.gamma_form === 'POSITIVE' ? 'var(--color-sw-green)' : data.header.gamma_form === 'NEGATIVE' ? 'var(--color-sw-red)' : 'var(--color-text-muted)'}
            />
            <MetricCard
              label="Flip Point"
              value={data.levels.gex_flip ? formatDollar(data.levels.gex_flip) : '—'}
              color="var(--color-sw-yellow)"
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
              color={data.header.rating === 'BULLISH' ? 'var(--color-sw-green)' : data.header.rating === 'BEARISH' ? 'var(--color-sw-red)' : 'var(--color-text-muted)'}
              sub={data.header['30_day_vol'] ? `VIX ${data.header['30_day_vol'].toFixed(1)}` : undefined}
            />
          </div>

          {/* Chart Section */}
          <div className="sw-card p-4 mb-4">
            <div className="flex flex-wrap items-center justify-between gap-2.5 mb-3.5">
              <div className="flex items-center gap-2 text-[13px] font-semibold text-white">
                <Activity size={14} className="text-accent" />
                {chartView === 'intraday'
                  ? `${symbol} Intraday 5m — Price + Net Gamma`
                  : `${symbol} ${chartView === 'net' ? 'Net' : 'Call vs Put'} GEX by Strike — ${data.expiration}`}
                {chartView === 'intraday' && isLive && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-sw-green">
                    <span className="w-[7px] h-[7px] rounded-full bg-sw-green animate-[sw-pulse_2s_ease-in-out_infinite]" />
                    LIVE
                  </span>
                )}
                {chartView === 'intraday' && !isLive && intradayBars.length > 0 && (
                  <span className="text-[11px] text-text-muted">
                    Market Closed{sessionDate && ` · Showing ${sessionDate} session`}
                  </span>
                )}
                {chartView === 'intraday' && nextCandleCountdown && (
                  <span className="text-[11px] font-[var(--font-mono)] bg-bg-elevated border border-border-default rounded-[var(--radius-sm)] px-2 py-0.5 text-accent">
                    Next candle: {nextCandleCountdown}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2.5">
                <div className="sw-toggle-group">
                  {['net', 'split', 'intraday'].map(view => (
                    <button
                      key={view}
                      onClick={() => setChartView(view)}
                      className={`sw-toggle-btn ${chartView === view ? 'active' : ''}`}
                    >
                      {view === 'net' ? 'Net GEX' : view === 'split' ? 'Call vs Put' : 'Intraday 5m'}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => pushToDiscord(chartView)}
                  disabled={discordPushing}
                  className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-semibold rounded-[var(--radius-sm)] border border-[rgba(88,101,242,0.3)] bg-[rgba(88,101,242,0.1)] text-[#7289da] cursor-pointer transition-all duration-150 hover:bg-[rgba(88,101,242,0.2)] hover:border-[rgba(88,101,242,0.5)] disabled:opacity-50"
                  title="Share to Discord"
                >
                  <Send size={12} />
                  {discordPushing ? 'Sending...' : 'Discord'}
                </button>
                {discordMsg && (
                  <span className={`text-[11px] font-semibold ${discordMsg === 'Posted!' ? 'text-sw-green' : 'text-sw-red'}`}>
                    {discordMsg}
                  </span>
                )}
              </div>
            </div>

            {/* INTRADAY 5M — Candlestick + GEX overlay (Plotly) */}
            {chartView === 'intraday' && (
              intradayBars.length === 0 && intradayChartData.length === 0 ? (
                <div className="text-center py-12 text-sw-yellow text-[13px]">
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
                <div className="text-center py-12 text-sw-yellow text-[13px]">Real-time data not available outside market hours (8:30 AM – 3:00 PM CT)</div>
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
                <div className="text-center py-12 text-sw-yellow text-[13px]">Real-time data not available outside market hours (8:30 AM – 3:00 PM CT)</div>
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
            <div className="sw-card p-4 mb-4">
              <div className="flex items-center gap-2 text-[13px] font-semibold text-white mb-3">
                <Info size={14} className="text-accent" />
                Market Interpretation
              </div>
              {interpretation.map((line, i) => (
                <p key={i} className="text-[13px] text-text-secondary leading-relaxed mb-1.5">{line}</p>
              ))}
            </div>
          )}

          {/* Flow Diagnostics */}
          {data.flow_diagnostics?.cards?.length > 0 && (
            <div className="sw-card p-4 mb-4">
              <div className="flex items-center gap-2 text-[13px] font-semibold text-white mb-3">
                <Anchor size={14} className="text-accent" />
                Options Flow Diagnostics
              </div>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-2.5">
                {data.flow_diagnostics.cards.map(card => (
                  <DiagCard key={card.id} borderColor={getCardBorder(card)}>
                    <div className="text-[10px] text-text-muted uppercase mb-1">{card.label}</div>
                    <div className="text-base font-bold text-white font-[var(--font-mono)]">{card.metric_value}</div>
                    <div className="text-[10px] text-text-muted mt-1">{card.description}</div>
                  </DiagCard>
                ))}
              </div>
              {data.flow_diagnostics.note && (
                <p className="text-[10px] text-text-muted mt-2">{data.flow_diagnostics.note}</p>
              )}
            </div>
          )}

          {/* Skew Measures */}
          {data.skew_measures && (
            <div className="sw-card p-4 mb-4">
              <div className="flex items-center gap-2 text-[13px] font-semibold text-white mb-3">
                <TrendingUp size={14} className="text-accent" />
                Skew Measures
              </div>
              <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-2.5">
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
            <div className="sw-card p-4 mb-4">
              <div className="flex items-center gap-2 text-[13px] font-semibold text-white mb-3">
                <BarChart3 size={14} className="text-accent" />
                Volume & Open Interest
              </div>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-2.5">
                <StatCard label="Total Volume" value={data.summary.total_volume.toLocaleString()} />
                <StatCard label="Call Volume" value={data.summary.total_call_volume.toLocaleString()} color="var(--color-sw-green)" />
                <StatCard label="Put Volume" value={data.summary.total_put_volume.toLocaleString()} color="var(--color-sw-red)" />
                <StatCard label="Total OI" value={(data.summary.total_call_oi + data.summary.total_put_oi).toLocaleString()} />
                <StatCard
                  label="P/C Ratio" value={data.summary.put_call_ratio.toFixed(2)}
                  color={data.summary.put_call_ratio > 1 ? 'var(--color-sw-red)' : 'var(--color-sw-green)'}
                />
                <StatCard
                  label="Net GEX" value={formatGex(data.summary.net_gex)}
                  color={data.summary.net_gex >= 0 ? 'var(--color-sw-green)' : 'var(--color-sw-red)'}
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
    <div className="bg-bg-card border border-border-subtle rounded-[var(--radius-lg)] px-3.5 py-2.5">
      <div className="text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-1">{label}</div>
      <div className="flex items-center gap-1.5 text-lg font-bold font-[var(--font-mono)]" style={{ color: color || '#fff' }}>
        {value}
        {badge && (
          <span className="text-[10px] px-1.5 py-px rounded-[var(--radius-sm)] font-semibold" style={{ background: badgeBg, color: badgeFg }}>{badge}</span>
        )}
      </div>
      {sub && <div className="text-[10px] text-text-muted mt-0.5">{sub}</div>}
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
    <div className="sw-card p-4 mb-4">
      <div className="flex justify-between mb-2 items-center">
        <span className="text-[10px] text-text-muted font-semibold uppercase tracking-widest">
          Price Position in GEX Structure
        </span>
        <span className={`text-[11px] font-bold ${aboveFlip ? 'text-sw-green' : 'text-sw-red'}`}>
          {aboveFlip ? 'POSITIVE GAMMA ZONE' : 'NEGATIVE GAMMA ZONE'}
        </span>
      </div>
      <div className="relative h-7 rounded-[20px] overflow-hidden bg-bg-elevated border border-border-default">
        <div className="absolute top-0 h-full" style={{ background: 'rgba(239,68,68,0.1)', left: '0%', width: `${flipPos}%` }} />
        <div className="absolute top-0 h-full" style={{ background: 'rgba(34,197,94,0.1)', left: `${flipPos}%`, width: `${100 - flipPos}%` }} />
        <div className="absolute top-0 h-full w-0.5" style={{ background: 'rgba(255,214,0,0.7)', left: `${flipPos}%` }} />
        <div
          className="absolute top-0.5 w-3.5 h-6 rounded-[3px] bg-accent border border-accent-bright"
          style={{ boxShadow: '0 2px 8px rgba(245,158,11,0.35)', left: `calc(${pricePos}% - 7px)` }}
        />
      </div>
      <div className="flex justify-between mt-2 text-[10px]">
        <span className="text-[#a855f7]">
          Put Wall ${putWall.toFixed(0)} <span className="text-text-muted">({distToPut}% away)</span>
        </span>
        <span className="text-sw-yellow">Flip ${flipPoint.toFixed(0)}</span>
        <span className="text-[#06b6d4]">
          <span className="text-text-muted">({distToCall}% away)</span> Call Wall ${callWall.toFixed(0)}
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
    // Layout: candles [0-0.78] | gap | GEX bars [0.82-0.98] | price axis in margin (r:70)
    const barLeft = 0.82;   // bars start here (paper coords)
    const barRight = 0.98;  // bars end here (leave room for price axis)
    const barMaxWidth = barRight - barLeft; // 0.16
    const strikeSpacing = visibleStrikes.length > 1
      ? Math.abs(visibleStrikes[0].strike - visibleStrikes[1].strike) * 0.35 : 0.5;

    const gexShapes = visibleStrikes.map(ss => {
      const pct = (ss.abs_net_gamma / maxGamma) * barMaxWidth;
      const color = ss.net_gamma >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)';
      const borderColor = ss.net_gamma >= 0 ? 'rgba(34,197,94,0.9)' : 'rgba(239,68,68,0.9)';
      return {
        type: 'rect', xref: 'paper', yref: 'y',
        x0: barRight, x1: barRight - pct,
        y0: ss.strike - strikeSpacing, y1: ss.strike + strikeSpacing,
        fillcolor: color, line: { color: borderColor, width: 1 }, layer: 'above',
      };
    });

    const gexAnnotations = visibleStrikes
      .filter(ss => ss.abs_net_gamma / maxGamma > 0.15)
      .map(ss => ({
        xref: 'paper', yref: 'y',
        x: barRight - (ss.abs_net_gamma / maxGamma) * barMaxWidth - 0.005,
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
    if (upper_1sd) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.77, y: upper_1sd, text: `+1σ $${upper_1sd.toFixed(0)}${expected_move ? ` (EM $${expected_move.toFixed(1)})` : ''}`, showarrow: false, font: { color: '#f97316', size: 9 }, xanchor: 'right', yanchor: 'bottom', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });
    if (lower_1sd) refAnnotations.push({ xref: 'paper', yref: 'y', x: 0.77, y: lower_1sd, text: `-1σ $${lower_1sd.toFixed(0)}`, showarrow: false, font: { color: '#f97316', size: 9 }, xanchor: 'right', yanchor: 'top', bgcolor: 'rgba(0,0,0,0.7)', borderpad: 2 });

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
      <div className="h-[550px]">
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
              domain: [0, 0.78],
            },
            yaxis: {
              gridcolor: '#1a1a2e', showgrid: true, side: 'right',
              tickformat: '$,.0f', range: plotData.yRange, autorange: false,
            },
            shapes: plotData.shapes,
            annotations: plotData.annotations,
            margin: { t: 10, b: 40, l: 10, r: 70 },
            hovermode: 'x unified',
            showlegend: false,
            transition: { duration: 300, easing: 'cubic-in-out' },
          }}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: '100%', height: '100%' }}
        />
      </div>
      <div className="flex flex-wrap gap-3.5 mt-2.5 text-[11px] items-center">
        {plotData.hasCandleData ? (
          <>
            <LegendItem color="#22c55e" label="Bullish" />
            <LegendItem color="#ef4444" label="Bearish" />
          </>
        ) : (
          <LegendItem color="#3b82f6" label="Price" line />
        )}
        <span className="text-border-subtle">|</span>
        <span className="text-[#22c55e] font-semibold">&#9632; +GEX Bar</span>
        <span className="text-[#ef4444] font-semibold">&#9632; -GEX Bar</span>
        <span className="text-border-subtle">|</span>
        <span className="text-[#eab308]">--- Flip</span>
        <span className="text-[#06b6d4]">... Call Wall</span>
        <span className="text-[#a855f7]">... Put Wall</span>
        <span className="text-[#f97316]">-.- ±1σ</span>
        <span className="text-border-subtle">|</span>
        {isLive
          ? <span className="inline-flex items-center gap-1 text-[11px] text-sw-green"><span className="w-[7px] h-[7px] rounded-full bg-sw-green animate-[sw-pulse_2s_ease-in-out_infinite]" />LIVE</span>
          : <span className="text-text-muted">Market Closed</span>}
        <span className="text-border-subtle">|</span>
        <span className="text-text-muted">
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
      <div className="h-[550px] overflow-y-auto">
        {sortedStrikes.map((entry, i) => {
          const pct = (entry.abs_net_gamma / maxGamma) * 100;
          const pos = entry.net_gamma >= 0;
          const atPrice = i === priceIdx;
          const atFlip = i === flipIdx && flipIdx !== priceIdx;
          const atCW = i === cwIdx && cwIdx !== priceIdx;
          const atPW = i === pwIdx && pwIdx !== priceIdx;

          const refBg = atPrice ? 'rgba(245,158,11,0.08)'
            : atFlip ? 'rgba(234,179,8,0.06)'
            : atCW ? 'rgba(6,182,212,0.06)'
            : atPW ? 'rgba(168,85,247,0.06)' : undefined;

          const borderTop = atPrice ? '2px solid rgba(245,158,11,0.5)'
            : atFlip ? '2px solid rgba(234,179,8,0.4)'
            : atCW ? '2px solid rgba(6,182,212,0.4)'
            : atPW ? '2px solid rgba(168,85,247,0.4)' : undefined;

          const strikeColor = atPrice ? 'var(--color-accent)'
            : atFlip ? '#eab308'
            : atCW ? '#06b6d4'
            : atPW ? '#a855f7' : undefined;

          const isHovered = hoveredStrike === entry.strike;

          return (
            <div
              key={entry.strike}
              className="flex items-center relative"
              style={{ background: refBg || 'transparent', height: rowH, borderTop, borderBottom: borderTop }}
              onMouseEnter={() => setHoveredStrike(entry.strike)}
              onMouseLeave={() => setHoveredStrike(null)}
            >
              <div className="w-24 shrink-0 text-right pr-2 text-[9px] font-semibold">
                {atPrice && <span className="text-accent">PRICE ${price?.toFixed(0)}</span>}
                {atFlip && <span className="text-[#eab308]">FLIP ${flip?.toFixed(0)}</span>}
                {atCW && <span className="text-[#06b6d4]">CALL WALL</span>}
                {atPW && <span className="text-[#a855f7]">PUT WALL</span>}
              </div>
              <div className="flex-1 flex justify-end items-center h-full border-r border-border-default">
                <div
                  style={{
                    width: `${Math.max(pct, 0.5)}%`,
                    height: Math.min(Math.max(rowH - 4, 6), 18),
                    borderRadius: '2px 0 0 2px',
                    background: pos ? '#22c55e' : '#ef4444',
                    opacity: entry.is_magnet ? 1 : entry.is_danger ? 0.9 : 0.75,
                    boxShadow: entry.is_magnet ? '0 0 4px rgba(255,214,0,0.4)' : 'none',
                  }}
                />
              </div>
              <div
                className="w-12 text-right text-[10px] font-[var(--font-mono)] pl-1.5 shrink-0"
                style={{ color: strikeColor || 'var(--color-text-muted)', fontWeight: strikeColor ? 700 : 400 }}
              >
                {entry.strike}
              </div>
              {isHovered && (
                <div className="absolute right-14 top-0 z-50 bg-[rgba(10,10,20,0.95)] border border-border-default rounded-[var(--radius-md)] px-3 py-2 shadow-lg text-[11px] min-w-[200px] pointer-events-none animate-[sw-fadeIn_0.15s_ease]">
                  <div className="font-bold text-white mb-1">${entry.strike}</div>
                  <div className={`font-semibold mb-1 ${pos ? 'text-[#22c55e]' : 'text-[#ef4444]'}`}>
                    Net GEX: {entry.gex_label}
                  </div>
                  <div className="text-text-muted leading-[1.8]">
                    <div>Call GEX: <span className="text-[#22c55e]">{formatGex(entry.call_gamma, 2)}</span></div>
                    <div>Put GEX: <span className="text-[#ef4444]">{formatGex(entry.put_gamma, 2)}</span></div>
                    {entry.call_iv && <div>Call IV: {(entry.call_iv * 100).toFixed(1)}%</div>}
                    {entry.put_iv && <div>Put IV: {(entry.put_iv * 100).toFixed(1)}%</div>}
                    <div>Volume: {entry.total_volume?.toLocaleString()}</div>
                  </div>
                  {entry.is_magnet && <div className="text-[#eab308] font-semibold mt-1">Magnet Strike</div>}
                  {entry.is_pin && <div className="text-[#a855f7] font-semibold mt-1">Pin Strike</div>}
                  {entry.is_danger && <div className="text-[#ef4444] font-semibold mt-1">{entry.danger_type}</div>}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-3.5 mt-2.5 text-[11px] items-center">
        <LegendItem color="#22c55e" label="Positive Gamma" />
        <LegendItem color="#ef4444" label="Negative Gamma" />
        <span className="text-border-subtle">|</span>
        <span className="text-accent">— Price</span>
        <span className="text-[#eab308]">--- Flip</span>
        <span className="text-[#06b6d4]">--- Call Wall</span>
        <span className="text-[#a855f7]">--- Put Wall</span>
      </div>
    </>
  );
}

function CallVsPutView({ sortedStrikes, data }) {
  return (
    <>
      <div className="h-[550px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={sortedStrikes} layout="vertical" margin={{ top: 5, right: 90, left: 60, bottom: 5 }}>
            <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={v => formatGex(v, 4)} axisLine={{ stroke: '#1a1a2e' }} />
            <YAxis type="category" dataKey="strike" tick={{ fill: '#9ca3af', fontSize: 10 }} width={50} axisLine={{ stroke: '#1a1a2e' }} />
            <Tooltip content={<StrikeTooltip />} />
            {data.levels.gex_flip && (
              <ReferenceLine y={data.levels.gex_flip} stroke="#eab308" strokeDasharray="5 3"
                label={{ value: `Flip ${data.levels.gex_flip}`, fill: '#eab308', fontSize: 9, position: 'right' }} />
            )}
            <ReferenceLine y={data.levels.price} stroke="#448aff" strokeWidth={2}
              label={{ value: `Price ${data.levels.price}`, fill: '#448aff', fontSize: 9, position: 'right' }} />
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
      <div className="flex flex-wrap gap-3.5 mt-2.5 text-[11px] items-center">
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
    <div className="bg-[rgba(10,10,20,0.95)] border border-border-default rounded-[var(--radius-md)] px-3.5 py-2.5 shadow-lg text-[11px] min-w-[220px]">
      <div className="font-bold text-white text-[13px] mb-1.5">
        Strike: ${label}
        {d.is_magnet && <span className="text-[10px] px-1.5 py-px rounded-[var(--radius-sm)] font-semibold bg-[rgba(234,179,8,0.15)] text-[#eab308]"> MAGNET{d.magnet_rank ? ` #${d.magnet_rank}` : ''}</span>}
        {d.is_pin && <span className="text-[10px] px-1.5 py-px rounded-[var(--radius-sm)] font-semibold bg-[rgba(168,85,247,0.15)] text-[#a855f7]"> PIN</span>}
        {d.is_danger && <span className="text-[10px] px-1.5 py-px rounded-[var(--radius-sm)] font-semibold bg-[rgba(239,68,68,0.15)] text-[#ef4444]"> {d.danger_type}</span>}
      </div>
      <TipRow label="Net Gamma" value={formatGex(d.net_gamma, 4)} color={d.net_gamma >= 0 ? '#22c55e' : '#ef4444'} bold />
      <TipRow label="Call Gamma" value={d.call_gamma?.toFixed(6)} color="#22c55e" />
      <TipRow label="Put Gamma" value={d.put_gamma?.toFixed(6)} color="#ef4444" />
      <div className="border-t border-border-subtle pt-1 mt-1">
        <TipRow label="Call Vol / Put Vol" value={`${(d.call_volume || 0).toLocaleString()} / ${(d.put_volume || 0).toLocaleString()}`} color="#fff" />
        <TipRow label="Call OI / Put OI" value={`${(d.call_oi || 0).toLocaleString()} / ${(d.put_oi || 0).toLocaleString()}`} color="#fff" />
      </div>
      {(d.call_iv || d.put_iv) && (
        <div className="border-t border-border-subtle pt-1 mt-1">
          <TipRow label="Call IV / Put IV" value={`${d.call_iv ? `${d.call_iv}%` : 'N/A'} / ${d.put_iv ? `${d.put_iv}%` : 'N/A'}`} color="#fff" />
        </div>
      )}
    </div>
  );
}

function TipRow({ label, value, color, bold }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-text-muted">{label}:</span>
      <span className="font-[var(--font-mono)]" style={{ fontWeight: bold ? 700 : 400, color }}>{value}</span>
    </div>
  );
}

function LegendItem({ color, label, line, small }) {
  return (
    <div className="flex items-center gap-1.5 text-text-muted">
      {line ? (
        <div className="w-4 h-0 shrink-0" style={{ borderTop: `2px solid ${color}` }} />
      ) : (
        <div className="rounded-sm shrink-0" style={{ width: small ? 8 : 10, height: small ? 8 : 10, background: color }} />
      )}
      <span>{label}</span>
    </div>
  );
}

function DiagCard({ borderColor, children }) {
  return (
    <div
      className="rounded-[var(--radius-md)] px-3 py-2.5 bg-bg-card"
      style={{ border: `1px solid ${borderColor || 'var(--color-border-subtle)'}` }}
    >
      {children}
    </div>
  );
}

function SkewCard({ label, value, desc }) {
  return (
    <DiagCard borderColor="var(--color-border-subtle)">
      <div className="text-[10px] text-text-muted uppercase mb-1">{label}</div>
      <div className="text-base font-bold text-white font-[var(--font-mono)]">{value}</div>
      <div className="text-[10px] text-text-muted mt-1">{desc}</div>
    </DiagCard>
  );
}

function StatCard({ label, value, color = '#fff' }) {
  return (
    <DiagCard borderColor="var(--color-border-subtle)">
      <div className="text-[10px] text-text-muted uppercase mb-1">{label}</div>
      <div className="text-base font-bold font-[var(--font-mono)]" style={{ color }}>{value}</div>
    </DiagCard>
  );
}

function getCardBorder(card) {
  if (card.id === 'volume_pressure' && card.raw_value > 0.1) return 'rgba(6,182,212,0.4)';
  if (card.id === 'call_share' && card.raw_value > 55) return 'rgba(6,182,212,0.4)';
  if (card.id === 'short_dte_share' && card.raw_value > 50) return 'rgba(6,182,212,0.4)';
  if (card.id === 'volume_pressure' && card.raw_value < -0.1) return 'rgba(239,68,68,0.4)';
  if (card.id === 'lotto_turnover' && card.raw_value > 0.3) return 'rgba(234,179,8,0.4)';
  return 'var(--color-border-subtle)';
}
