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
import GexProfilePage from './pages/GexProfilePage';
import useCandles from './hooks/useCandles';
import useGex from './hooks/useGex';
import useCalculate from './hooks/useCalculate';
import useMarketHours from './hooks/useMarketHours';
import SymbolSelector from './components/SymbolSelector';
import { MetricsBarSkeleton, CalcOverlay } from './components/Skeleton';

const CHART_HEIGHT = 500;

function MarketStatusBadge() {
  const { isOpen, statusText } = useMarketHours();
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '4px 10px',
      borderRadius: 20,
      background: isOpen ? 'var(--green-dim)' : 'rgba(255, 82, 82, 0.08)',
      border: `1px solid ${isOpen ? 'rgba(0, 230, 118, 0.2)' : 'rgba(255, 82, 82, 0.15)'}`,
    }}>
      <span style={{
        display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
        background: isOpen ? 'var(--green)' : 'var(--red)',
        boxShadow: isOpen ? '0 0 6px rgba(0, 230, 118, 0.5)' : 'none',
        animation: isOpen ? 'sw-pulse 2s ease-in-out infinite' : 'none',
      }} />
      <span style={{
        color: isOpen ? 'var(--green)' : 'var(--red)',
        fontSize: 11,
        fontWeight: 600,
        fontFamily: 'var(--font-ui)',
      }}>
        {isOpen ? 'Market Open' : statusText}
      </span>
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
    <span style={{
      color: 'var(--text-muted)',
      fontSize: 11,
      fontFamily: 'var(--font-ui)',
      fontWeight: 500,
    }}>
      {text}
    </span>
  );
}

function NavBar() {
  const navLinkStyle = ({ isActive }) => ({
    padding: '0 18px',
    height: '100%',
    display: 'flex',
    alignItems: 'center',
    color: isActive ? '#fff' : 'var(--text-tertiary)',
    background: isActive ? 'rgba(68, 138, 255, 0.08)' : 'transparent',
    borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent',
    textDecoration: 'none',
    fontWeight: isActive ? 700 : 500,
    fontSize: 13,
    letterSpacing: '0.01em',
    transition: 'all 0.2s ease',
  });

  return (
    <nav style={{
      display: 'flex',
      alignItems: 'center',
      gap: 0,
      background: 'linear-gradient(180deg, #0e0e28 0%, #0a0a1e 100%)',
      borderBottom: '1px solid var(--border-subtle)',
      fontFamily: 'var(--font-ui)',
      fontSize: 13,
      padding: '0 16px',
      height: 52,
      boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)',
    }}>
      {/* Logo */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '0 20px 0 0',
        marginRight: 8,
        borderRight: '1px solid rgba(30, 30, 70, 0.5)',
        height: '100%',
      }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 30,
          height: 30,
          borderRadius: 8,
          background: 'linear-gradient(135deg, var(--accent) 0%, #7c4dff 100%)',
          fontSize: 14,
          color: '#fff',
          fontWeight: 800,
          boxShadow: '0 4px 16px rgba(68, 138, 255, 0.4), 0 0 30px rgba(68, 138, 255, 0.15)',
        }}>S</div>
        <span style={{ fontWeight: 800, fontSize: 17, color: '#fff', letterSpacing: '-0.5px' }}>
          Spread<span style={{ color: 'var(--accent-bright)' }}>Works</span>
        </span>
      </div>

      {/* Nav Links */}
      <NavLink to="/" end style={navLinkStyle}>Builder</NavLink>
      <NavLink to="/positions" style={navLinkStyle}>Positions</NavLink>
      <NavLink to="/gex-profile" style={navLinkStyle}>GEX Profile</NavLink>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 14 }}>
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
        {/* Chart Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 16px',
          background: 'linear-gradient(90deg, rgba(12, 12, 34, 0.95) 0%, rgba(10, 10, 26, 0.95) 100%)',
          borderBottom: '1px solid var(--border-subtle)',
          fontFamily: 'var(--font-ui)',
          fontSize: 13,
        }}>
          <SymbolSelector value={symbol} onChange={handleSymbolChange} />
          <span style={{ color: 'var(--text-muted)', fontSize: 12, fontWeight: 500 }}>
            {interval === '15min' ? '15M' : interval === '1h' ? '1H' : '4H'}
          </span>
          <span style={{ color: 'var(--text-muted)' }}>&middot;</span>
          <span style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>Price + Spread Payoff</span>
          {spotPrice && (
            <span style={{
              color: 'var(--accent)',
              fontWeight: 700,
              fontSize: 14,
              fontFamily: 'var(--font-mono)',
              marginLeft: 4,
            }}>
              ${spotPrice.toFixed(2)}
            </span>
          )}
          {!isOpen && dataAsOf && (
            <span style={{
              marginLeft: 'auto',
              padding: '3px 10px',
              background: 'var(--yellow-dim)',
              border: '1px solid rgba(255, 214, 0, 0.2)',
              borderRadius: 20,
              color: 'var(--yellow)',
              fontSize: 11,
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

        {/* Chart Area — UNTOUCHED */}
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
        background: 'var(--bg-base)', overflow: 'hidden',
      }}>
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
