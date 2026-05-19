import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Layers, BarChart3, Activity, PanelLeftClose, PanelLeftOpen, ZoomIn, ZoomOut, Cpu, ChevronDown } from 'lucide-react';
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

const CARD_CHROME = {
  background: 'rgba(7,16,28,0.55)',
  boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)',
};
import useCandles from './hooks/useCandles';
import useGex from './hooks/useGex';
import useCalculate from './hooks/useCalculate';
import useMarketHours from './hooks/useMarketHours';
import SymbolSelector from './components/SymbolSelector';
import { MetricsBarSkeleton, CalcOverlay } from './components/Skeleton';
import { API_URL } from './lib/api';

const CHART_HEIGHT = 500;

// ── Market chip ─────────────────────────────────────────────────────
// Single glass capsule: "HH:MM ET | • Market open / After hours".
// ── Center clock — lives in an absolutely-centered pill inside the header.
// Matches the side cards' chrome (translucent + inset ring) so it reads as
// the third card in the row. NEVER uses red — emerald when market is open,
// amber when after-hours.
function CenterClock() {
  const { isOpen, statusText } = useMarketHours();
  const [time, setTime] = useState(() => formatEt());
  useEffect(() => {
    const iv = setInterval(() => setTime(formatEt()), 30_000);
    return () => clearInterval(iv);
  }, []);

  const dotColor = isOpen ? '#34d399' : '#fcd34d';
  const label = isOpen ? 'Market open' : (statusText || 'After hours');
  const labelColor = isOpen ? '#34d399' : '#fcd34d';

  return (
    <>
      <span className="font-mono font-semibold text-[12.5px]" style={{ color: '#e2e8f0' }}>
        {time.hhmm}
      </span>
      <span className="font-mono text-[10px] uppercase tracking-wider" style={{ color: '#64748b' }}>
        ET
      </span>
      <span className="w-px h-3.5" style={{ background: 'rgba(255,255,255,0.10)' }} />
      <span className="inline-flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.12em] font-semibold" style={{ color: labelColor }}>
        <span
          className={`w-1.5 h-1.5 rounded-full ${isOpen ? 'animate-pulse-dot' : ''}`}
          style={{ background: dotColor }}
        />
        {label}
      </span>
    </>
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

// ── useBotStatusMap — polls /api/spreadworks/bots every 15s and returns a
// keyed map { breeze: {enabled, today_pnl, ...}, tide: {...} } used by the
// dropdown's per-bot status dots and today-P&L numbers.
function useBotStatusMap() {
  const [statusMap, setStatusMap] = useState({});
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
  return statusMap;
}

// ── Bot dropdown — the RIGHT card. Chip shows the active bot tinted to its
// theme. Clicking opens a 260px menu below with all bots, their status dot,
// and today's P&L. Navigates via react-router (the existing route pattern);
// no URL-hash routing — the page tree is already wired to /bots/:bot.
function BotDropdown() {
  const navigate = useNavigate();
  const location = useLocation();
  const statusMap = useBotStatusMap();
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  const match = location.pathname.match(/^\/bots\/([^/]+)/);
  const activeBotId = match ? match[1] : null;

  // If not on a /bots/* route, fall back to the first bot in the registry so
  // the chip still shows something meaningful.
  const firstBotId = Object.keys(BOT_REGISTRY)[0];
  const chipBotId = activeBotId || firstBotId;
  const chipBot = BOT_REGISTRY[chipBotId];
  const chipTheme = BOT_THEME[chipBotId];

  // Close menu on outside click or Esc.
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const onPick = (id) => {
    navigate(`/bots/${id}`);
    setOpen(false);
  };

  const bots = Object.entries(BOT_REGISTRY).map(([id, meta]) => ({ id, ...meta }));

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors"
        style={{
          background: chipTheme.primarySoft,
          boxShadow: `inset 0 0 0 1px ${chipTheme.primaryRing}`,
        }}
      >
        <div
          className="w-6 h-6 rounded-md grid place-items-center flex-shrink-0"
          style={{ background: `${chipTheme.primary}1f`, color: chipTheme.primary }}
        >
          <BotGlyph kind={chipTheme.glyph} size={13} />
        </div>
        <span className="text-[10px] uppercase tracking-wider font-bold" style={{ color: '#64748b' }}>
          Bot
        </span>
        <span className="text-[13px] font-bold" style={{ color: chipTheme.primary }}>
          {chipBot.display}
        </span>
        <ChevronDown size={12} style={{ color: chipTheme.primary, opacity: 0.6 }} />
      </button>

      {open && (
        <div
          className="absolute right-0 mt-2 p-1.5 z-50"
          style={{
            width: 260,
            background: 'rgba(13,28,46,0.92)',
            backdropFilter: 'blur(16px) saturate(140%)',
            WebkitBackdropFilter: 'blur(16px) saturate(140%)',
            borderRadius: 12,
            boxShadow:
              'inset 0 0 0 1px rgba(125,211,252,0.12), inset 0 1px 0 rgba(255,255,255,0.05), 0 12px 40px -8px rgba(0,0,0,0.4)',
          }}
        >
          {bots.map(b => {
            const theme = BOT_THEME[b.id];
            const active = activeBotId === b.id;
            const status = statusMap[b.id] || {};
            const enabled = !!status.enabled;
            const todayPnl = typeof status.today_pnl === 'number' ? status.today_pnl : null;

            return (
              <button
                key={b.id}
                type="button"
                onClick={() => onPick(b.id)}
                className="flex items-center gap-3 w-full px-2.5 py-2 rounded-lg transition-colors text-left"
                style={
                  active
                    ? {
                        background: theme.primarySoft,
                        boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
                      }
                    : undefined
                }
                onMouseEnter={(e) => {
                  if (!active) e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                }}
                onMouseLeave={(e) => {
                  if (!active) e.currentTarget.style.background = '';
                }}
              >
                <div
                  className="w-7 h-7 rounded-md grid place-items-center flex-shrink-0"
                  style={{ background: `${theme.primary}1f`, color: theme.primary }}
                >
                  <BotGlyph kind={theme.glyph} size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <div
                    className="text-[13px] font-bold"
                    style={{ color: active ? theme.primary : '#e2e8f0' }}
                  >
                    {b.display}
                  </div>
                  <div className="sw-mono text-[10px]" style={{ color: '#64748b' }}>
                    {STRATEGY_LABEL[b.strategy] || b.strategy}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ background: enabled ? '#34d399' : '#475569' }}
                  />
                  <span
                    className="sw-mono text-[11px] font-semibold"
                    style={{
                      color:
                        todayPnl == null || todayPnl === 0 ? '#64748b' :
                        todayPnl > 0 ? '#34d399' : '#fb7185',
                    }}
                  >
                    {todayPnl == null || todayPnl === 0
                      ? '—'
                      : `${todayPnl > 0 ? '+' : '−'}$${Math.abs(todayPnl).toFixed(2)}`}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}
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

// ── Brand block (left card head). Tile + wordmark, untouched palette.
function Brand() {
  return (
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
  );
}

// ── NavBar — 3-card layout: LEFT card (brand + nav), CENTER pill (market
// clock, absolute positioned so it stays mathematically centered), RIGHT
// card (bot dropdown). All three share the same chrome: rgba(7,16,28,0.55)
// background with an inset cyan ring + subtle top highlight.
function NavBar() {
  return (
    <header
      className="relative px-7 py-3 flex items-center justify-between gap-4 font-[var(--font-ui)] text-[13px]"
      style={{
        backdropFilter: 'blur(20px) saturate(140%)',
        WebkitBackdropFilter: 'blur(20px) saturate(140%)',
        borderBottom: '1px solid rgba(125,211,252,0.10)',
      }}
    >
      {/* LEFT CARD — brand + primary routes */}
      <div
        className="flex items-center gap-1 px-2 py-1.5 rounded-xl"
        style={CARD_CHROME}
      >
        <div className="px-3"><Brand /></div>
        <span className="w-px h-7 mx-2" style={{ background: 'rgba(125,211,252,0.10)' }} />
        <nav className="flex items-center gap-0.5">
          <NavTabLink to="/"            end Icon={Layers}    label="Builder" />
          <NavTabLink to="/positions"       Icon={BarChart3} label="Positions" />
          <NavTabLink to="/gex-profile"     Icon={Activity}  label="GEX" />
          <NavTabLink to="/bots/breeze"     Icon={Cpu}       label="Bots" />
        </nav>
      </div>

      {/* CENTER — market clock, absolute-positioned dead-center */}
      <div
        className="absolute left-1/2 -translate-x-1/2 flex items-center gap-3 px-4 py-2 rounded-full"
        style={{
          ...CARD_CHROME,
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
        }}
      >
        <CenterClock />
      </div>

      {/* RIGHT CARD — bot dropdown */}
      <div
        className="flex items-center px-3 py-2 rounded-xl"
        style={CARD_CHROME}
      >
        <BotDropdown />
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
