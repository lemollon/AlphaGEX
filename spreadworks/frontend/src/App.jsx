import { useState, useEffect, useCallback, useRef } from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Layers, BarChart3, Activity, Clock, Menu, X } from 'lucide-react';
import StrategyPanel from './components/StrategyPanel';
import ChartArea from './components/ChartArea';
import ControlsBar from './components/ControlsBar';
import PnLTable from './components/PnLTable';
import LegBreakdown from './components/LegBreakdown';
import MetricsBar from './components/MetricsBar';
import Legend from './components/Legend';
import PositionsPage from './pages/PositionsPage';
import GexProfilePage from './pages/GexProfilePage';
import useCandles from './hooks/useCandles';
import useGex from './hooks/useGex';
import useCalculate from './hooks/useCalculate';
import useMarketHours from './hooks/useMarketHours';
import SymbolSelector from './components/SymbolSelector';
import { MetricsBarSkeleton, CalcOverlay } from './components/Skeleton';
import { API_URL } from './lib/api';

const CHART_HEIGHT = 500;

function MarketStatusBadge() {
  const { isOpen, statusText } = useMarketHours();
  return (
    <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-all duration-150 ${
      isOpen
        ? 'bg-sw-green-dim border-sw-green/20 text-sw-green'
        : 'bg-sw-red-dim border-sw-red/15 text-sw-red'
    }`}>
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${
        isOpen
          ? 'bg-sw-green animate-pulse-dot shadow-[0_0_6px_rgba(34,197,94,0.5)]'
          : 'bg-sw-red'
      }`} />
      {isOpen ? 'Market Open' : statusText}
    </div>
  );
}

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
    const iv = setInterval(update, 30000);
    return () => clearInterval(iv);
  }, []);

  if (!text) return null;
  return (
    <span className="flex items-center gap-1.5 text-text-muted text-[11px] font-medium font-[var(--font-ui)]">
      <Clock size={12} className="opacity-60" />
      {text}
    </span>
  );
}

function NavBar() {
  return (
    <nav className="flex items-center h-[48px] px-5 border-b border-border-subtle shadow-lg font-[var(--font-ui)] text-[13px]"
      style={{ background: 'linear-gradient(180deg, #0e0e28 0%, #0a0a1e 100%)' }}>
      {/* Logo */}
      <div className="flex items-center gap-2 pr-6 mr-4 border-r border-border-subtle/50 h-full">
        <div className="inline-flex items-center justify-center w-[26px] h-[26px] rounded-md text-xs text-white font-extrabold"
          style={{
            background: 'linear-gradient(135deg, var(--color-accent) 0%, #2962ff 100%)',
            boxShadow: '0 3px 12px rgba(68, 138, 255, 0.35)',
          }}>
          S
        </div>
        <span className="font-extrabold text-[15px] text-white tracking-tight">
          Spread<span className="text-accent">Works</span>
        </span>
      </div>

      {/* Nav Links */}
      <div className="flex items-center gap-1.5 h-full">
        <NavLink to="/" end className={({ isActive }) =>
          `flex items-center gap-1.5 px-4 py-1.5 text-[12px] font-semibold tracking-wide transition-all duration-200 no-underline rounded-md ${
            isActive
              ? 'text-white bg-accent/15 border border-accent/40'
              : 'text-text-secondary border border-transparent hover:text-white hover:bg-white/[0.06] hover:border-border-subtle'
          }`
        }>
          <Layers size={13} />
          Builder
        </NavLink>
        <NavLink to="/positions" className={({ isActive }) =>
          `flex items-center gap-1.5 px-4 py-1.5 text-[12px] font-semibold tracking-wide transition-all duration-200 no-underline rounded-md ${
            isActive
              ? 'text-white bg-accent/15 border border-accent/40'
              : 'text-text-secondary border border-transparent hover:text-white hover:bg-white/[0.06] hover:border-border-subtle'
          }`
        }>
          <BarChart3 size={13} />
          Positions
        </NavLink>
        <NavLink to="/gex-profile" className={({ isActive }) =>
          `flex items-center gap-1.5 px-4 py-1.5 text-[12px] font-semibold tracking-wide transition-all duration-200 no-underline rounded-md ${
            isActive
              ? 'text-white bg-accent/15 border border-accent/40'
              : 'text-text-secondary border border-transparent hover:text-white hover:bg-white/[0.06] hover:border-border-subtle'
          }`
        }>
          <Activity size={13} />
          GEX Profile
        </NavLink>
      </div>

      <div className="ml-auto flex items-center gap-4">
        <NextPostCountdown />
        <MarketStatusBadge />
      </div>
    </nav>
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
      <div className="flex-1 flex flex-col min-w-0 overflow-auto">
        {/* Chart Header */}
        <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border-subtle font-[var(--font-ui)] text-[13px]"
          style={{ background: 'linear-gradient(90deg, rgba(12, 12, 34, 0.95) 0%, rgba(10, 10, 26, 0.95) 100%)' }}>
          <SymbolSelector value={symbol} onChange={handleSymbolChange} />
          <span className="text-text-muted text-xs font-medium">
            {interval === '15min' ? '15M' : interval === '1h' ? '1H' : '4H'}
          </span>
          <span className="text-text-muted">&middot;</span>
          <span className="text-text-secondary font-medium">Price + Spread Payoff</span>
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
              fetchError={candlesError} />
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
      <div className="flex flex-col h-screen w-full bg-bg-base overflow-hidden">
        <NavBar />
        <Routes>
          <Route path="/" element={<BuilderPage />} />
          <Route path="/positions" element={<PositionsPage />} />
          <Route path="/gex-profile" element={<GexProfilePage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
