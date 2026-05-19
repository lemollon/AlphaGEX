import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Layers, BarChart3, Activity, PanelLeftClose, PanelLeftOpen, ZoomIn, ZoomOut } from 'lucide-react';
import StrategyPanel from './components/StrategyPanel';
import BotGlyph from './components/bots/BotGlyph';
import { BOT_REGISTRY, BOT_THEME, STRATEGY_LABEL } from './lib/botRegistry';
import ChartArea from './components/ChartArea';
import ControlsBar from './components/ControlsBar';
import PnLTable from './components/PnLTable';
import LegBreakdown from './components/LegBreakdown';
import MetricsBar from './components/MetricsBar';
import Legend from './components/Legend';
import PositionsPage from './pages/PositionsPage';
// Lazy-load heavy chart pages so Plotly + Recharts don't drag the main bundle.
const GexProfilePage = lazy(() => import('./pages/GexProfilePage'));
const BotDashboard = lazy(() => import('./pages/BotDashboard'));
import useCandles from './hooks/useCandles';
import useGex from './hooks/useGex';
import useCalculate from './hooks/useCalculate';
import useMarketHours from './hooks/useMarketHours';
import SymbolSelector from './components/SymbolSelector';
import LivePnlTape from './components/LivePnlTape';
import { MetricsBarSkeleton, CalcOverlay } from './components/Skeleton';
import { API_URL } from './lib/api';

const CHART_HEIGHT = 500;

// ── Market chip ─────────────────────────────────────────────────────
// Single glass capsule: "HH:MM ET | • Market open / After hours".
// Replaces the red MarketStatusBadge + red DatePill + red NextPostCountdown
// trio. Amber dot when closed (atmospheric, not alarmed); emerald when open.
function MarketChip() {
  const { isOpen, statusText } = useMarketHours();
  const [time, setTime] = useState(() => formatEt());
  useEffect(() => {
    const iv = setInterval(() => setTime(formatEt()), 30_000);
    return () => clearInterval(iv);
  }, []);

  const dot = isOpen ? '#34d399' : '#fcd34d';
  const label = isOpen ? 'Market open' : (statusText || 'After hours');

  return (
    <div
      className="inline-flex items-center gap-2.5 px-3 py-1.5 rounded-full sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <span className="sw-mono text-[12px] font-semibold text-[#e2e8f0]">{time.hhmm}</span>
      <span className="text-[10px] uppercase tracking-wider text-text-secondary">ET</span>
      <span className="h-3.5 w-px" style={{ background: 'rgba(255,255,255,0.08)' }} />
      <span className="inline-flex items-center gap-1.5">
        <span
          className={`inline-block w-1.5 h-1.5 rounded-full ${isOpen ? 'animate-pulse-dot' : ''}`}
          style={{ background: dot }}
        />
        <span className="text-[10.5px] uppercase tracking-[0.12em] font-semibold text-text-secondary">
          {label}
        </span>
      </span>
    </div>
  );
}

function formatEt() {
  const now = new Date();
  const hhmm = now.toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  return { hhmm };
}

// Bot-cycle countdown ("Open Post in 1h 5m") — kept but restyled to slate +
// amber, no longer red.
function NextPostCountdown() {
  const [text, setText] = useState('');

  useEffect(() => {
    const update = () => {
      const now = new Date();
      const targets = [
        { h: 8, m: 25, label: 'Open Post' },
        { h: 15, m: 0, label: 'EOD Mark' },
        { h: 15, m: 5, label: 'EOD Post' },
      ];
      const ct = new Date(now.toLocaleString('en-US', { timeZone: 'America/Chicago' }));
      const ctMins = ct.getHours() * 60 + ct.getMinutes();
      let next = null;
      for (const t of targets) {
        const tMins = t.h * 60 + t.m;
        if (tMins > ctMins) {
          const diff = tMins - ctMins;
          const hrs = Math.floor(diff / 60);
          const mins = diff % 60;
          next = `${t.label} in ${hrs > 0 ? hrs + 'h ' : ''}${mins}m`;
          break;
        }
      }
      setText(next || '');
    };
    update();
    const iv = setInterval(update, 30_000);
    return () => clearInterval(iv);
  }, []);

  if (!text) return null;
  return (
    <div
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full sw-glass text-[10.5px] font-semibold uppercase tracking-[0.12em]"
      style={{
        color: '#cbd5e1',
        boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)',
      }}
    >
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#fcd34d] animate-pulse-dot" />
      {text}
    </div>
  );
}

// ── Bot cards row (second nav row, only on /bots/* routes) ─────────
// Replaces the previous centered pillbox. Each card = glass surface with
// glyph + name + strategy + status dot + today P&L. Active card is themed
// with primarySoft gradient + glow.
function BotCardsRow() {
  const navigate = useNavigate();
  const location = useLocation();
  const [statusMap, setStatusMap] = useState({});

  const match = location.pathname.match(/^\/bots\/([^/]+)/);
  const activeBotId = match ? match[1] : null;

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const res = await fetch(`${API_URL}/api/spreadworks/bots`);
        if (!res.ok) return;
        const data = await res.json();
        const next = {};
        for (const b of (data?.bots || data || [])) {
          const id = b?.bot || b?.id;
          if (id) next[id] = b;
        }
        if (!cancelled) setStatusMap(next);
      } catch { /* silent */ }
    }
    poll();
    const iv = setInterval(poll, 15_000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  const bots = Object.entries(BOT_REGISTRY).map(([id, meta]) => ({ id, ...meta }));

  return (
    <div className="px-7 pt-4 pb-5 flex items-center gap-3">
      {bots.map(b => {
        const theme = BOT_THEME[b.id];
        const active = activeBotId === b.id;
        const status = statusMap[b.id] || {};
        const enabled = !!status.enabled;
        const todayPnl = typeof status.today_pnl === 'number' ? status.today_pnl : null;

        const cardStyle = active
          ? {
              background: `linear-gradient(135deg, ${theme.primarySoft}, rgba(255,255,255,0.02))`,
              boxShadow: `inset 0 0 0 1px ${theme.primaryRing}, inset 0 1px 0 rgba(255,255,255,0.06), 0 8px 32px -16px ${theme.glow}`,
            }
          : {
              background: 'rgba(255,255,255,0.025)',
              boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.05), inset 0 1px 0 rgba(255,255,255,0.04)',
            };

        return (
          <button
            key={b.id}
            onClick={() => navigate(`/bots/${b.id}`)}
            className="flex-1 flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all text-left"
            style={{
              ...cardStyle,
              backdropFilter: 'blur(8px) saturate(140%)',
              WebkitBackdropFilter: 'blur(8px) saturate(140%)',
            }}
          >
            {/* Glyph tile */}
            <div
              className="w-9 h-9 rounded-lg grid place-items-center flex-shrink-0"
              style={
                active
                  ? { background: theme.primarySoft, color: theme.primary }
                  : { background: 'rgba(255,255,255,0.03)', color: '#94a3b8' }
              }
            >
              <BotGlyph kind={theme.glyph} size={17} />
            </div>

            {/* Name + strategy */}
            <div className="min-w-0 flex-1">
              <div
                className="text-[14px] font-bold tracking-wide"
                style={
                  active
                    ? { color: theme.primary, textShadow: `0 0 12px ${theme.glow}` }
                    : { color: '#e2e8f0' }
                }
              >
                {b.display}
              </div>
              <div className="sw-mono text-[10px] text-text-tertiary mt-0.5">
                {STRATEGY_LABEL[b.strategy] || b.strategy}
              </div>
            </div>

            {/* Status + today P&L */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: enabled ? '#34d399' : '#475569' }}
              />
              {todayPnl != null && (
                <span
                  className="sw-mono text-[11.5px] font-semibold"
                  style={{
                    color:
                      todayPnl > 0 ? '#34d399' :
                      todayPnl < 0 ? '#fb7185' :
                      '#64748b',
                  }}
                >
                  {todayPnl === 0
                    ? '—'
                    : `${todayPnl > 0 ? '+' : '−'}$${Math.abs(todayPnl).toFixed(2)}`}
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function NavTabLink({ to, end, Icon, label }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium transition-colors duration-150 no-underline rounded-md ${
          isActive
            ? 'text-text-primary'
            : 'text-text-secondary hover:text-text-primary'
        }`
      }
      style={({ isActive }) =>
        isActive ? { background: 'rgba(255,255,255,0.06)' } : undefined
      }
    >
      <Icon size={13} />
      {label}
    </NavLink>
  );
}

function NavBar() {
  return (
    <nav
      className="relative flex items-center h-16 px-7 font-[var(--font-ui)] text-[13px]"
      style={{
        background: 'linear-gradient(180deg, rgba(255,255,255,0.025), rgba(255,255,255,0))',
        backdropFilter: 'blur(20px) saturate(140%)',
        WebkitBackdropFilter: 'blur(20px) saturate(140%)',
        borderBottom: '1px solid rgba(125,211,252,0.08)',
      }}
    >
      {/* LEFT: brand + primary routes */}
      <div className="flex items-center gap-8 h-full">
        <div className="flex items-center gap-2.5">
          <div
            className="inline-flex items-center justify-center w-9 h-9 rounded-xl text-base text-white font-black"
            style={{
              background: 'linear-gradient(135deg, rgba(125,211,252,0.4), rgba(45,212,191,0.2))',
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.4), inset 0 0 0 1px rgba(255,255,255,0.10)',
            }}
          >
            S
          </div>
          <span className="font-extrabold text-[19px] text-text-primary tracking-tight">
            Spread<span style={{ color: '#22d3ee' }}>Works</span>
          </span>
        </div>

        <div className="flex items-center gap-1">
          <NavTabLink to="/"            end Icon={Layers}    label="Builder" />
          <NavTabLink to="/positions"       Icon={BarChart3} label="Positions" />
          <NavTabLink to="/gex-profile"     Icon={Activity}  label="GEX Profile" />
          <NavTabLink to="/bots/breeze"     Icon={Layers}    label="Bots" />
        </div>
      </div>

      {/* RIGHT: live tape + countdown + market chip */}
      <div className="ml-auto flex items-center gap-3">
        <LivePnlTape />
        <NextPostCountdown />
        <MarketChip />
      </div>
    </nav>
  );
}

// Renders BotCardsRow only when the URL is on a bot page.
function BotCardsRowGate() {
  const location = useLocation();
  if (!location.pathname.startsWith('/bots')) return null;
  return <BotCardsRow />;
}

function BuilderPage() {
  const [symbol, setSymbol] = useState('SPY');
  const [interval, setInterval_] = useState('15min');
  const [alerts, setAlerts] = useState([]);
  const [dteSlider, setDteSlider] = useState(0);
  const [rangePct, setRangePct] = useState(2.2);
  const [ivMultiplier, setIvMultiplier] = useState(1.0);
  const [viewMode, setViewMode] = useState('graph');
  const [tableViewMode, setTableViewMode] = useState('pnl_dollar');
  const [lastPayload, setLastPayload] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [candleSpacing, setCandleSpacing] = useState(9);

  const zoomIn = () => setCandleSpacing((s) => Math.min(s + 3, 30));
  const zoomOut = () => setCandleSpacing((s) => Math.max(s - 3, 3));

  const { candles, spotPrice, loading: candlesLoading, error: candlesError, dataAsOf, refetch: refetchCandles } = useCandles(symbol, interval);
  const [manualSpot, setManualSpot] = useState(null);
  const { gexData, refetch: refetchGex } = useGex(symbol);
  const { calcResult, calcLoading, calcError, calculate, clearResult } = useCalculate();

  const handleSymbolChange = useCallback((newSymbol) => {
    setSymbol(newSymbol);
    setLastPayload(null);
    clearResult();
  }, [clearResult]);
  const { isOpen, secondsAgo, markRefreshed, statusText } = useMarketHours();

  const strikes = lastPayload?.legs || null;
  const effectiveSpot = spotPrice || manualSpot;

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/alerts`);
      if (!res.ok) return;
      const data = await res.json();
      setAlerts(data.alerts || []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const prevCandlesLen = useRef(0);
  useEffect(() => {
    if (candles.length !== prevCandlesLen.current) {
      prevCandlesLen.current = candles.length;
      markRefreshed();
    }
  }, [candles, markRefreshed]);

  const handleCalculate = async (payload) => {
    setLastPayload(payload);
    await calculate(payload);
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      {sidebarOpen && (
        <StrategyPanel
          symbol={symbol}
          spotPrice={effectiveSpot}
          gexData={gexData}
          onCalculate={handleCalculate}
          calcLoading={calcLoading}
          calcError={calcError}
          calcResult={calcResult}
          alerts={alerts}
          onRefreshAlerts={fetchAlerts}
          apiError={candlesError}
          onManualSpotChange={setManualSpot}
        />
      )}
      <div className="flex-1 flex flex-col min-w-0 overflow-auto">
        {/* Chart Header */}
        <div className="flex items-center gap-3 px-4 py-2.5 border-b border-white/5 bg-bg-base font-[var(--font-ui)] text-[13px]">
          <button
            className="p-1.5 rounded-md text-text-secondary hover:text-white hover:bg-white/[0.06] transition-all duration-150 border border-transparent hover:border-border-subtle"
            onClick={() => setSidebarOpen((v) => !v)}
            title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
          </button>
          <SymbolSelector value={symbol} onChange={handleSymbolChange} />
          <span className="text-text-muted text-xs font-medium">
            {interval === '15min' ? '15M' : interval === '1h' ? '1H' : '4H'}
          </span>
          <span className="text-text-muted">&middot;</span>
          <span className="text-text-secondary font-medium">Price + Spread Payoff</span>
          <div className="flex items-center gap-0.5 ml-2">
            <button
              className="p-1 rounded text-text-secondary hover:text-white hover:bg-white/[0.06] transition-all duration-150"
              onClick={zoomOut}
              title="Zoom out (more bars)"
            >
              <ZoomOut size={14} />
            </button>
            <button
              className="p-1 rounded text-text-secondary hover:text-white hover:bg-white/[0.06] transition-all duration-150"
              onClick={zoomIn}
              title="Zoom in (fewer bars)"
            >
              <ZoomIn size={14} />
            </button>
          </div>
          {effectiveSpot && (
            <span className="text-accent font-bold text-sm font-[var(--font-mono)] ml-1">
              ${effectiveSpot.toFixed(2)}
            </span>
          )}
          {!isOpen && dataAsOf && (
            <span className="ml-auto px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-sw-yellow-dim border border-sw-yellow/20 text-sw-yellow">
              Market Closed &middot; Data as of {new Date(dataAsOf).toLocaleString('en-US', {
                timeZone: 'America/New_York',
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                hour12: true,
              })} ET
            </span>
          )}
        </div>

        {/* Chart Area */}
        <div className="min-h-[500px] flex relative">
          {calcLoading && <CalcOverlay />}
          {viewMode === 'table' ? (
            <PnLTable calcResult={calcResult} viewMode={tableViewMode} />
          ) : (
            <ChartArea candles={candles} spotPrice={effectiveSpot} gexData={gexData}
              strikes={strikes} calcResult={calcResult} height={CHART_HEIGHT} rangePct={rangePct}
              fetchError={candlesError} candleSpacing={candleSpacing} />
          )}
        </div>

        <ControlsBar dteSlider={dteSlider} onDteChange={setDteSlider}
          rangePct={rangePct} onRangeChange={setRangePct}
          ivMultiplier={ivMultiplier} onIvMultiplierChange={setIvMultiplier}
          isMarketOpen={isOpen} secondsAgo={secondsAgo} statusText={statusText}
          dataAsOf={dataAsOf}
          interval={interval} onIntervalChange={setInterval_}
          onRefreshIv={refetchGex} viewMode={viewMode} onViewModeChange={setViewMode}
          tableViewMode={tableViewMode} onTableViewModeChange={setTableViewMode} />
        {calcLoading ? <MetricsBarSkeleton /> : <MetricsBar calcResult={calcResult} />}
        <LegBreakdown calcResult={calcResult} />
        <Legend interval={interval} barCount={Math.min(candles.length, 80)} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex flex-col h-screen w-full overflow-hidden">
        <NavBar />
        <BotCardsRowGate />
        <Suspense fallback={
          <div className="flex-1 flex items-center justify-center text-text-tertiary text-sm">
            Loading…
          </div>
        }>
          <Routes>
            <Route path="/" element={<BuilderPage />} />
            <Route path="/positions" element={<PositionsPage />} />
            <Route path="/gex-profile" element={<GexProfilePage />} />
            <Route path="/bots" element={<Navigate to="/bots/breeze" replace />} />
            <Route path="/bots/:bot" element={<BotDashboard />} />
          </Routes>
        </Suspense>
      </div>
    </BrowserRouter>
  );
}
