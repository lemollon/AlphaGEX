import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Layers, BarChart3, Activity, PanelLeftClose, PanelLeftOpen, ZoomIn, ZoomOut, Cpu, ChevronDown, Plus } from 'lucide-react';
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
import { MetricsBarSkeleton, CalcOverlay } from './components/Skeleton';
import { API_URL } from './lib/api';

const CHART_HEIGHT = 500;

// ── Market chip ─────────────────────────────────────────────────────
// Single glass capsule: "HH:MM ET | • Market open / After hours".
// ── Clock — ET time + ●Market open|After hours. Inline styles only (per
// the design spec — every padding / gap / border-radius value matters).
function Clock() {
  const { isOpen } = useMarketHours();
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const fmt = now.toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
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
        ET
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

// ── BotMenu — 260px dropdown panel with all bots + status + today P&L.
function BotMenu({ activeBotId, onSelect }) {
  const statusMap = useBotStatusMap();
  const bots = Object.entries(BOT_REGISTRY).map(([id, meta]) => ({ id, ...meta }));
  return (
    <div
      style={{
        position: 'absolute', top: 'calc(100% + 8px)', right: 0,
        width: 260, padding: 6, borderRadius: 12, zIndex: 50,
        background: 'rgba(13,28,46,0.92)',
        backdropFilter: 'blur(16px) saturate(140%)',
        WebkitBackdropFilter: 'blur(16px) saturate(140%)',
        boxShadow:
          'inset 0 0 0 1px rgba(125,211,252,0.12), inset 0 1px 0 rgba(255,255,255,0.05), 0 12px 40px -8px rgba(0,0,0,0.4)',
      }}
    >
      {bots.map(b => {
        const t = BOT_THEME[b.id];
        const active = b.id === activeBotId;
        const status = statusMap[b.id] || {};
        const enabled = !!status.enabled;
        const pnl = typeof status.today_pnl === 'number' ? status.today_pnl : 0;
        return (
          <button
            key={b.id}
            onClick={() => onSelect(b.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              width: '100%', padding: '8px 10px', borderRadius: 8,
              background: active ? t.primarySoft : 'transparent',
              boxShadow: active ? `inset 0 0 0 1px ${t.primaryRing}` : 'none',
              border: 'none', cursor: 'pointer', textAlign: 'left',
              transition: 'background-color 150ms',
            }}
            onMouseEnter={(e) => {
              if (!active) e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
            }}
            onMouseLeave={(e) => {
              if (!active) e.currentTarget.style.background = 'transparent';
            }}
          >
            <div style={{
              width: 28, height: 28, borderRadius: 6,
              display: 'grid', placeItems: 'center',
              background: `${t.primary}1f`, color: t.primary, flexShrink: 0,
            }}>
              <BotGlyph kind={t.glyph} size={14} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: active ? t.primary : '#e2e8f0' }}>
                {capitalize(b.display)}
              </div>
              <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: '#64748b', marginTop: 2 }}>
                {STRATEGY_LABEL[b.strategy] || b.strategy}
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
              <span style={{
                width: 6, height: 6, borderRadius: 9999,
                background: enabled ? '#34d399' : '#475569',
              }} />
              <span style={{
                fontFamily: 'JetBrains Mono', fontSize: 11, fontWeight: 600,
                color: pnl > 0 ? '#34d399' : pnl < 0 ? '#fb7185' : '#64748b',
              }}>
                {pnl === 0 ? '—' : (pnl > 0 ? '+' : '−') + '$' + Math.abs(pnl).toFixed(0)}
              </span>
            </div>
          </button>
        );
      })}
      <div style={{
        marginTop: 6, paddingTop: 6,
        borderTop: '1px solid rgba(125,211,252,0.08)',
      }}>
        <button
          disabled
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            width: '100%', padding: '6px 10px', borderRadius: 8,
            background: 'transparent', border: 'none', cursor: 'not-allowed',
            fontSize: 12.5, fontWeight: 500, color: '#94a3b8',
            textAlign: 'left', opacity: 0.6,
          }}
          title="Coming soon"
        >
          <Plus size={12} /> New bot
        </button>
      </div>
    </div>
  );
}

function capitalize(s) {
  return s.charAt(0) + s.slice(1).toLowerCase();
}

// ── TopBar (exported as NavBar to keep the existing import name in App).
// 3-card layout per the design spec. LEFT card holds brand + divider +
// inline-styled RouteBtns. CENTER pill is absolute, mathematically centered.
// RIGHT card wraps a themed dropdown chip that opens BotMenu below.
// Persisted "currently active bot" — survives page nav and reloads so the
// chip on the Builder / Positions / GEX pages reflects the last pick, not
// just the URL. URL still wins when the user is actually on /bots/<id>.
const ACTIVE_BOT_KEY = 'spreadworks.activeBot';

function readStoredBot() {
  try {
    const v = localStorage.getItem(ACTIVE_BOT_KEY);
    if (v && BOT_REGISTRY[v]) return v;
  } catch { /* SSR / quota — fall through */ }
  return null;
}

function NavBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const match = location.pathname.match(/^\/bots\/([^/]+)/);
  const urlBotId = match && BOT_REGISTRY[match[1]] ? match[1] : null;
  const firstBotId = Object.keys(BOT_REGISTRY)[0];

  // When URL is on /bots/<id>, that's authoritative. Otherwise fall back to
  // the last picked bot from localStorage so the chip stays meaningful on
  // Builder / Positions / GEX without forcing the user to renavigate.
  const [storedBotId, setStoredBotId] = useState(() => readStoredBot());
  const activeBotId = urlBotId || storedBotId || firstBotId;
  const activeBot = BOT_REGISTRY[activeBotId];
  const theme = BOT_THEME[activeBotId];

  // Keep storage in sync when URL drives the bot (e.g. user followed a
  // link straight to /bots/tide).
  useEffect(() => {
    if (urlBotId && urlBotId !== storedBotId) {
      try { localStorage.setItem(ACTIVE_BOT_KEY, urlBotId); } catch { /* ignore */ }
      setStoredBotId(urlBotId);
    }
  }, [urlBotId, storedBotId]);

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  useEffect(() => {
    function onDoc(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    }
    function onKey(e) { if (e.key === 'Escape') setMenuOpen(false); }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, []);

  return (
    <header
      className="relative flex items-center justify-between"
      style={{
        paddingLeft: 28,
        paddingRight: 28,
        paddingTop: 12,
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
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingLeft: 12, paddingRight: 12 }}>
          <div
            style={{
              width: 36, height: 36, borderRadius: 12,
              display: 'grid', placeItems: 'center',
              fontWeight: 900, color: '#fff', fontSize: 16,
              background: 'linear-gradient(135deg, rgba(125,211,252,0.4), rgba(45,212,191,0.2))',
              boxShadow:
                'inset 0 1px 0 rgba(255,255,255,0.4), inset 0 0 0 1px rgba(255,255,255,0.10)',
            }}
          >
            S
          </div>
          <span style={{ fontWeight: 800, fontSize: 19, letterSpacing: '-0.02em', color: '#fff' }}>
            Spread<span style={{ color: '#22d3ee' }}>Works</span>
          </span>
        </div>

        {/* Divider between brand and nav */}
        <span
          style={{
            width: 1, height: 28, marginLeft: 8, marginRight: 8,
            background: 'rgba(125,211,252,0.10)',
          }}
        />

        {/* Routes */}
        <nav style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <RouteBtn to="/"            end icon={<Layers size={14} />}    label="Builder" />
          <RouteBtn to="/positions"       icon={<BarChart3 size={14} />} label="Positions" />
          <RouteBtn to="/gex-profile"     icon={<Activity size={14} />}  label="GEX Profile" />
          <RouteBtn to={`/bots/${activeBotId}`} icon={<Cpu size={14} />}  label="Bots" />
        </nav>
      </div>

      {/* ═══════════ CENTER · CLOCK ═══════════ */}
      <div
        style={{
          position: 'absolute',
          left: '50%',
          transform: 'translateX(-50%)',
          display: 'flex',
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

      {/* ═══════════ RIGHT CARD · BOT DROPDOWN ═══════════ */}
      <div
        ref={menuRef}
        style={{ position: 'relative', display: 'flex', alignItems: 'center' }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            paddingLeft: 12,
            paddingRight: 12,
            paddingTop: 8,
            paddingBottom: 8,
            borderRadius: 12,
            background: 'rgba(7,16,28,0.55)',
            boxShadow:
              'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)',
          }}
        >
          <button
            onClick={() => setMenuOpen(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              paddingLeft: 12, paddingRight: 12,
              paddingTop: 8, paddingBottom: 8,
              borderRadius: 8,
              background: theme.primarySoft,
              boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
              cursor: 'pointer',
              border: 'none',
              transition: 'background-color 150ms',
            }}
          >
            <div
              style={{
                width: 24, height: 24, borderRadius: 6,
                display: 'grid', placeItems: 'center',
                background: `${theme.primary}1f`,
                color: theme.primary,
              }}
            >
              <BotGlyph kind={theme.glyph} size={13} />
            </div>
            <span style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Bot
            </span>
            <span style={{ fontSize: 13, fontWeight: 700, color: theme.primary }}>
              {capitalize(activeBot.display)}
            </span>
            <ChevronDown size={12} style={{ color: theme.primary, opacity: 0.6 }} />
          </button>
        </div>

        {menuOpen && (
          <BotMenu
            activeBotId={activeBotId}
            onSelect={(id) => {
              // Always persist so the chip survives across pages and reloads.
              try { localStorage.setItem(ACTIVE_BOT_KEY, id); } catch { /* ignore */ }
              setStoredBotId(id);
              setMenuOpen(false);
              // Only navigate when the user is already viewing a bot dashboard.
              // From Builder / Positions / GEX we just re-theme — switching to
              // another page would be an unwelcome surprise.
              if (urlBotId && urlBotId !== id) {
                navigate(`/bots/${id}`);
              } else if (!urlBotId) {
                // Stay on the current non-bot route; chip updates via state.
              }
            }}
          />
        )}
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
