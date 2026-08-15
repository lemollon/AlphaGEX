import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { ShieldAlert, Layers, BarChart3, Activity, PanelLeftClose, PanelLeftOpen, ZoomIn, ZoomOut, Cpu, PieChart, Zap } from 'lucide-react';
import StrategyPanel from './components/StrategyPanel';
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
const FleetPage = lazy(() => import('./pages/FleetPage'));
const RiskAdvisorPage = lazy(() => import('./pages/RiskAdvisorPage'));
const SqueezePage = lazy(() => import('./pages/SqueezePage'));
const BookRiskPage = lazy(() => import('./pages/BookRiskPage'));
const TsunamiPage = lazy(() => import('./pages/TsunamiPage'));

import useCandles from './hooks/useCandles';
import useGex from './hooks/useGex';
import useCalculate from './hooks/useCalculate';
import useMarketHours from './hooks/useMarketHours';
import SymbolSelector from './components/SymbolSelector';
import { MetricsBarSkeleton, CalcOverlay } from './components/Skeleton';
import { API_URL } from './lib/api';

const CHART_HEIGHT = 500;

// ── Market chip ─────────────────────────────────────────────────────
// Single glass capsule: "HH:MM CT | • Market open / After hours".
// ── Clock — CT time + ●Market open|After hours. Inline styles only (per
// the design spec — every padding / gap / border-radius value matters).
function Clock() {
  const { isOpen } = useMarketHours();
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const fmt = now.toLocaleTimeString('en-US', {
    timeZone: 'America/Chicago',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  return (
    <>
      <span style={{ fontFamily: 'JetBrains Mono', fontSize: 12.5, fontWeight: 600, color: '#e2e8f0' }}>
        {fmt}
      </span>
      <span style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        CT
      </span>
      <span style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.10)' }} />
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        fontSize: 10.5, fontWeight: 600,
        textTransform: 'uppercase', letterSpacing: '0.12em',
        color: isOpen ? '#34d399' : '#fcd34d',
      }}>
        <span style={{
          width: 6, height: 6, borderRadius: 9999,
          background: isOpen ? '#34d399' : '#fcd34d',
          animation: isOpen ? 'pulse 2s infinite' : 'none',
        }} />
        {isOpen ? 'Market open' : 'After hours'}
      </span>
    </>
  );
}

// ── RouteBtn — inline-styled nav button per spec. Active state is derived
// from the current URL via react-router so the URL stays source of truth.
function RouteBtn({ icon, label, to, end = false }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [hover, setHover] = useState(false);
  const active = end
    ? location.pathname === to
    : location.pathname === to || location.pathname.startsWith(to + '/');
  return (
    <button
      onClick={() => navigate(to)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        paddingLeft: 12,
        paddingRight: 12,
        paddingTop: 6,
        paddingBottom: 6,
        borderRadius: 6,
        fontSize: 13,
        fontWeight: 500,
        color: active ? '#fff' : hover ? '#fff' : '#94a3b8',
        background: active ? 'rgba(255,255,255,0.06)' : hover ? 'rgba(255,255,255,0.03)' : 'transparent',
        border: 'none',
        cursor: 'pointer',
        transition: 'all 150ms',
      }}
    >
      {icon}
      {label}
    </button>
  );
}

// ── TopBar (exported as NavBar to keep the existing import name in App).
// LEFT card holds brand + divider + inline-styled RouteBtns. CENTER pill is
// absolute, mathematically centered. (The right-card bot dropdown was removed
// 2026-08-13 per operator request — the Bots route + fleet page replaced it.)
function NavBar() {
  const navigate = useNavigate();

  return (
    <header
      className="relative flex items-center justify-between flex-wrap gap-y-2"
      style={{
        // Respect the top safe-area (notch / status bar) so the brand + nav
        // clear it under viewport-fit=cover; falls back to 12px off-device.
        paddingLeft: 'calc(28px + env(safe-area-inset-left, 0px))',
        paddingRight: 'calc(28px + env(safe-area-inset-right, 0px))',
        paddingTop: 'calc(12px + env(safe-area-inset-top, 0px))',
        paddingBottom: 12,
        backdropFilter: 'blur(20px) saturate(140%)',
        WebkitBackdropFilter: 'blur(20px) saturate(140%)',
        borderBottom: '1px solid rgba(125,211,252,0.10)',
      }}
    >
      {/* ═══════════ LEFT CARD ═══════════ */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 4,
          paddingLeft: 8,
          paddingRight: 8,
          paddingTop: 6,
          paddingBottom: 6,
          borderRadius: 12,
          background: 'rgba(7,16,28,0.55)',
          boxShadow:
            'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)',
        }}
      >
        {/* Brand — clicking the logo/wordmark returns to the Builder (home). */}
        <button
          onClick={() => navigate('/')}
          aria-label="SpreadWorks home"
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            paddingLeft: 12, paddingRight: 12,
            background: 'transparent', border: 'none', cursor: 'pointer',
          }}
        >
          <img
            src="/logo.png"
            alt="SpreadWorks"
            width={36}
            height={36}
            style={{
              width: 36, height: 36, borderRadius: 12, display: 'block', flexShrink: 0,
              // Glowing cyan ring — box-shadow (not border) so the 36px box
              // doesn't shift. Gentle pulse via the sw-logo-glow keyframe.
              animation: 'sw-logo-glow 2.4s ease-in-out infinite',
            }}
          />
          <span style={{ fontWeight: 800, fontSize: 19, letterSpacing: '-0.02em', color: '#fff' }}>
            Spread<span style={{ color: '#22d3ee' }}>Works</span>
          </span>
        </button>

        {/* Divider between brand and nav */}
        <span
          style={{
            width: 1, height: 28, marginLeft: 8, marginRight: 8,
            background: 'rgba(125,211,252,0.10)',
          }}
        />

        {/* Routes */}
        <nav style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
          <RouteBtn to="/"            end icon={<Layers size={14} />}    label="Builder" />
          <RouteBtn to="/positions"       icon={<BarChart3 size={14} />} label="Positions" />
          <RouteBtn to="/gex-profile"     icon={<Activity size={14} />}  label="GEX Profile" />
          {/* Lands on the fleet overview; deep links to /bots/<id> keep it
              highlighted too. */}
          <RouteBtn to="/bots"            icon={<Cpu size={14} />}  label="Bots" />
          <RouteBtn to="/risk"            icon={<ShieldAlert size={14} />} label="Risk" />
          <RouteBtn to="/squeeze"         icon={<Zap size={14} />} label="Squeeze" />
          <RouteBtn to="/book-risk"       icon={<PieChart size={14} />} label="Book Risk" />
        </nav>
      </div>

      {/* ═══════════ CENTER · CLOCK ═══════════ */}
      {/* Absolute-centered pill. Two safeguards keep it from blocking the nav:
          1. pointerEvents: 'none' — the clock is display-only, so even if it
             visually overlaps the "Bots" / nav buttons on a narrower window,
             clicks pass straight through to the buttons beneath it. (Without
             this it was painting on top of the left nav card and swallowing
             clicks on the Bots button.)
          2. hidden 2xl:flex — only render it once the viewport is wide enough
             (≥1536px) that a 50%-centered pill clears the left nav card; below
             that it would slide left over the nav, so we simply hide it (market
             status is still shown in the Builder's controls bar).
          Display is class-controlled so the Tailwind `2xl:flex` wins over an
          inline display value. */}
      <div
        className="hidden 2xl:flex"
        style={{
          position: 'absolute',
          left: '50%',
          transform: 'translateX(-50%)',
          pointerEvents: 'none',
          alignItems: 'center',
          gap: 12,
          paddingLeft: 16,
          paddingRight: 16,
          paddingTop: 8,
          paddingBottom: 8,
          borderRadius: 9999,
          background: 'rgba(7,16,28,0.55)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          boxShadow:
            'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)',
        }}
      >
        <Clock />
      </div>

    </header>
  );
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
  // Default the strategy panel OPEN on desktop but COLLAPSED on phones, so a
  // mobile user sees the chart + controls first instead of scrolling past the
  // whole panel. The toggle button in the chart header opens it on demand.
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    if (typeof window !== 'undefined') return window.innerWidth >= 768;
    return true;
  });
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
    <div className="flex flex-col md:flex-row flex-1 overflow-y-auto md:overflow-hidden">
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
      <div className="flex-1 flex flex-col min-w-0 overflow-visible md:overflow-auto">
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
                timeZone: 'America/Chicago',
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                hour12: true,
              })} CT
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
      <div className="flex flex-col h-dvh w-full overflow-hidden">
        <NavBar />
        <Suspense fallback={
          <div className="flex-1 flex items-center justify-center text-text-tertiary text-sm">
            Loading…
          </div>
        }>
          <Routes>
            <Route path="/" element={<BuilderPage />} />
            <Route path="/positions" element={<PositionsPage />} />
            <Route path="/risk" element={<RiskAdvisorPage />} />
            <Route path="/squeeze" element={<SqueezePage />} />
            <Route path="/book-risk" element={<BookRiskPage />} />
            <Route path="/gex-profile" element={<GexProfilePage />} />
            {/* /bots is the fleet overview — every bot as its own card. It used
                to redirect straight to /bots/surge, which meant there was no
                way to see the whole book at once. Deep links to a single bot
                are unchanged. */}
            <Route path="/bots" element={<FleetPage />} />
            <Route path="/bots/:bot" element={<BotDashboard />} />
            <Route path="/tsunami" element={<TsunamiPage />} />
          </Routes>
        </Suspense>
      </div>
    </BrowserRouter>
  );
}
