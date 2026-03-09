import { useState, useEffect, useCallback, useRef } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import StrategyPanel from './components/StrategyPanel';
import ChartArea from './components/ChartArea';
import ControlsBar from './components/ControlsBar';
import MetricsBar from './components/MetricsBar';
import Legend from './components/Legend';
import PositionsPage from './components/PositionsPage';
import useCandles from './hooks/useCandles';
import useGex from './hooks/useGex';
import useCalculate from './hooks/useCalculate';
import useMarketHours from './hooks/useMarketHours';

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
    </nav>
  );
}

function BuilderPage() {
  const [symbol] = useState('SPY');
  const [interval, setInterval_] = useState('15min');
  const [alerts, setAlerts] = useState([]);
  const [dteSlider, setDteSlider] = useState(0);
  const [rangePct, setRangePct] = useState(2.2);
  const [ivMultiplier, setIvMultiplier] = useState(1.0);
  const [viewMode, setViewMode] = useState('graph');
  const [lastPayload, setLastPayload] = useState(null);

  const API_URL = import.meta.env.VITE_API_URL || '';

  const { candles, spotPrice, loading: candlesLoading, refetch: refetchCandles } = useCandles(symbol, interval);
  const { gexData, refetch: refetchGex } = useGex(symbol);
  const { calcResult, calcLoading, calcError, calculate } = useCalculate();
  const { isOpen, secondsAgo, markRefreshed, statusText } = useMarketHours();

  const strikes = lastPayload?.legs || null;

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/alerts`);
      if (!res.ok) return;
      const data = await res.json();
      setAlerts(data.alerts || []);
    } catch {
      // silent
    }
  }, [API_URL]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

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

  const handleIntervalChange = (newInterval) => {
    setInterval_(newInterval);
  };

  const headerStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '6px 12px',
    background: '#0d0d18',
    borderBottom: '1px solid #1a1a2e',
    fontFamily: "'Courier New', monospace",
    fontSize: 12,
  };

  return (
    <div style={{
      display: 'flex',
      flex: 1,
      overflow: 'hidden',
    }}>
      {/* LEFT PANEL */}
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

      {/* RIGHT PANEL */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        overflow: 'hidden',
      }}>
        <div style={headerStyle}>
          <span style={{ color: '#fff', fontWeight: 700 }}>{symbol}</span>
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
          <div style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}>
            <span style={{
              display: 'inline-block',
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: isOpen ? '#00e676' : '#ef5350',
            }} />
            <span style={{ color: isOpen ? '#00e676' : '#ef5350', fontSize: 10 }}>
              {isOpen ? 'Market Open' : `Market Closed \u00b7 ${statusText}`}
            </span>
          </div>
        </div>

        <div style={{ flex: 1, minHeight: 0 }}>
          <ChartArea
            candles={candles}
            spotPrice={spotPrice}
            gexData={gexData}
            strikes={strikes}
            calcResult={calcResult}
            height={CHART_HEIGHT}
            rangePct={rangePct}
          />
        </div>

        <ControlsBar
          dteSlider={dteSlider}
          onDteChange={setDteSlider}
          rangePct={rangePct}
          onRangeChange={setRangePct}
          ivMultiplier={ivMultiplier}
          onIvMultiplierChange={setIvMultiplier}
          isMarketOpen={isOpen}
          secondsAgo={secondsAgo}
          statusText={statusText}
          interval={interval}
          onIntervalChange={handleIntervalChange}
          onRefreshIv={refetchGex}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
        />

        <MetricsBar calcResult={calcResult} />
        <Legend interval={interval} barCount={Math.min(candles.length, 80)} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        width: '100%',
        background: '#080810',
        overflow: 'hidden',
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
