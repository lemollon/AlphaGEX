import { useState, useEffect, useCallback, useRef } from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import StrategyPanel from './components/StrategyPanel';
import ChartArea from './components/ChartArea';
import ControlsBar from './components/ControlsBar';
import PnLTable from './components/PnLTable';
import LegBreakdown from './components/LegBreakdown';
import MetricsBar from './components/MetricsBar';
import Legend from './components/Legend';
import PositionsPage from './pages/PositionsPage';
import useCandles from './hooks/useCandles';
import useGex from './hooks/useGex';
import useCalculate from './hooks/useCalculate';
import useMarketHours from './hooks/useMarketHours';
import SymbolSelector from './components/SymbolSelector';
import { MetricsBarSkeleton, CalcOverlay } from './components/Skeleton';

const CHART_HEIGHT = 500;

const navStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 0,
  background: '#080810',
  borderBottom: '1px solid #1a1a2e',
  fontFamily: "'Courier New', monospace",
  fontSize: 12,
  padding: '0 12px',
};

const navLinkStyle = (isActive) => ({
  padding: '8px 16px',
  color: isActive ? '#448aff' : '#555',
  borderBottom: isActive ? '2px solid #448aff' : '2px solid transparent',
  textDecoration: 'none',
  fontWeight: isActive ? 700 : 400,
  fontSize: 12,
  fontFamily: "'Courier New', monospace",
  transition: 'all 0.15s',
});

const logoStyle = {
  display: 'flex',
  alignItems: 'baseline',
  gap: 0,
  padding: '8px 12px 8px 0',
  marginRight: 12,
  borderRight: '1px solid #1a1a2e',
};

function MarketStatusBadge() {
  const { isOpen, statusText } = useMarketHours();
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <span style={{
        display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
        background: isOpen ? '#00e676' : '#ef5350',
      }} />
      <span style={{ color: isOpen ? '#00e676' : '#ef5350', fontSize: 10 }}>
        {isOpen ? 'Open' : statusText}
      </span>
    </div>
  );
}

function NextPostCountdown() {
  const [text, setText] = useState('');

  useEffect(() => {
    const update = () => {
      const now = new Date();
      // Next scheduled posts: 8:25 CT open, 15:00 CT mark, 15:05 CT EOD
      const targets = [
        { h: 8, m: 25, label: 'Open Post' },
        { h: 15, m: 0, label: 'EOD Mark' },
        { h: 15, m: 5, label: 'EOD Post' },
      ];

      // Get current CT time
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
    <span style={{ color: '#444', fontSize: 10, fontFamily: "'Courier New', monospace" }}>
      {text}
    </span>
  );
}

function NavBar() {
  return (
    <nav style={navStyle}>
      <div style={logoStyle}>
        <span style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>Spread</span>
        <span style={{ color: '#448aff', fontWeight: 700, fontSize: 14 }}>Works</span>
      </div>
      <NavLink to="/" style={({ isActive }) => navLinkStyle(isActive)} end>
        Builder
      </NavLink>
      <NavLink to="/positions" style={({ isActive }) => navLinkStyle(isActive)}>
        Positions
      </NavLink>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
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

  const API_URL = import.meta.env.VITE_API_URL || '';

  const { candles, spotPrice, loading: candlesLoading, dataAsOf, refetch: refetchCandles } = useCandles(symbol, interval);
  const { gexData, refetch: refetchGex } = useGex(symbol);
  const { calcResult, calcLoading, calcError, calculate, clearResult } = useCalculate();

  const handleSymbolChange = useCallback((newSymbol) => {
    setSymbol(newSymbol);
    setLastPayload(null);
    clearResult();
  }, [clearResult]);
  const { isOpen, secondsAgo, markRefreshed, statusText } = useMarketHours();

  const strikes = lastPayload?.legs || null;

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/alerts`);
      if (!res.ok) return;
      const data = await res.json();
      setAlerts(data.alerts || []);
    } catch { /* silent */ }
  }, [API_URL]);

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

  const headerStyle = {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '6px 12px', background: '#0d0d18',
    borderBottom: '1px solid #1a1a2e',
    fontFamily: "'Courier New', monospace", fontSize: 12,
  };

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
      <StrategyPanel
        symbol={symbol}
        spotPrice={spotPrice}
        gexData={gexData}
        onCalculate={handleCalculate}
        calcLoading={calcLoading}
        calcError={calcError}
        calcResult={calcResult}
        alerts={alerts}
        onRefreshAlerts={fetchAlerts}
      />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        <div style={headerStyle}>
          <SymbolSelector value={symbol} onChange={handleSymbolChange} />
          <span style={{ color: '#555' }}>
            {interval === '15min' ? '15M' : interval === '1h' ? '1H' : '4H'}
          </span>
          <span style={{ color: '#555' }}>&middot;</span>
          <span style={{ color: '#888' }}>Price + Spread Payoff</span>
          {spotPrice && (
            <span style={{ color: '#448aff', fontWeight: 600, marginLeft: 8 }}>
              ${spotPrice.toFixed(2)}
            </span>
          )}
          {!isOpen && dataAsOf && (
            <span style={{
              marginLeft: 'auto',
              padding: '2px 8px',
              background: '#ffd60022',
              border: '1px solid #ffd60044',
              borderRadius: 3,
              color: '#ffd600',
              fontSize: 10,
              fontWeight: 600,
            }}>
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
        <div style={{ flex: 1, minHeight: 0, display: 'flex', position: 'relative' }}>
          {calcLoading && <CalcOverlay />}
          {viewMode === 'table' ? (
            <PnLTable calcResult={calcResult} viewMode={tableViewMode} />
          ) : (
            <ChartArea candles={candles} spotPrice={spotPrice} gexData={gexData}
              strikes={strikes} calcResult={calcResult} height={CHART_HEIGHT} rangePct={rangePct} />
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
      <div style={{
        display: 'flex', flexDirection: 'column',
        height: '100vh', width: '100%',
        background: '#080810', overflow: 'hidden',
      }}>
        <NavBar />
        <Routes>
          <Route path="/" element={<BuilderPage />} />
          <Route path="/positions" element={<PositionsPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
