import { useState, useEffect, useCallback, useRef } from 'react';
import StrategyPanel from './components/StrategyPanel';
import ChartArea from './components/ChartArea';
import ControlsBar from './components/ControlsBar';
import MetricsBar from './components/MetricsBar';
import Legend from './components/Legend';
import useCandles from './hooks/useCandles';
import useGex from './hooks/useGex';
import useCalculate from './hooks/useCalculate';
import useMarketHours from './hooks/useMarketHours';

const API_URL = import.meta.env.VITE_API_URL || '';
const CHART_HEIGHT = 500;

export default function App() {
  const [symbol] = useState('SPY');
  const [interval, setInterval_] = useState('15min');
  const [alerts, setAlerts] = useState([]);
  const [dteSlider, setDteSlider] = useState(0);
  const [rangePct, setRangePct] = useState(2.2);
  const [ivMultiplier, setIvMultiplier] = useState(1.0);
  const [viewMode, setViewMode] = useState('graph');
  const [lastPayload, setLastPayload] = useState(null);

  // Hooks
  const { candles, spotPrice, loading: candlesLoading, refetch: refetchCandles } = useCandles(symbol, interval);
  const { gexData, refetch: refetchGex } = useGex(symbol);
  const { calcResult, calcLoading, calcError, calculate } = useCalculate();
  const { isOpen, secondsAgo, markRefreshed, statusText } = useMarketHours();

  // Extract strikes from last payload for chart overlay
  const strikes = lastPayload?.legs || null;

  // Fetch alerts
  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/alerts`);
      if (!res.ok) return;
      const data = await res.json();
      setAlerts(data.alerts || []);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Live refresh timer — mark refreshed when candles update
  const prevCandlesLen = useRef(0);
  useEffect(() => {
    if (candles.length !== prevCandlesLen.current) {
      prevCandlesLen.current = candles.length;
      markRefreshed();
    }
  }, [candles, markRefreshed]);

  // Handle calculate
  const handleCalculate = async (payload) => {
    setLastPayload(payload);
    await calculate(payload);
  };

  // Interval change
  const handleIntervalChange = (newInterval) => {
    setInterval_(newInterval);
  };

  // Header bar
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
      height: '100vh',
      width: '100%',
      background: '#080810',
      overflow: 'hidden',
    }}>
      {/* LEFT PANEL — Strategy Builder (260px fixed) */}
      <StrategyPanel
        symbol={symbol}
        spotPrice={spotPrice}
        gexData={gexData}
        onCalculate={handleCalculate}
        calcLoading={calcLoading}
        calcError={calcError}
        alerts={alerts}
        onRefreshAlerts={fetchAlerts}
      />

      {/* RIGHT PANEL — Chart + Controls + Metrics */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        overflow: 'hidden',
      }}>
        {/* Header bar */}
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

          {/* Market status */}
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

        {/* Chart area — candles + payoff side by side */}
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

        {/* Controls bar */}
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

        {/* Metrics bar */}
        <MetricsBar calcResult={calcResult} />

        {/* Legend */}
        <Legend interval={interval} barCount={Math.min(candles.length, 80)} />
      </div>
    </div>
  );
}
