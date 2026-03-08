import { useState, useEffect, useCallback, useRef } from 'react';
import StrategyPanel from './components/StrategyPanel';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const ALERT_POLL_INTERVAL = 15_000; // 15 seconds
const CANDLE_REFRESH_INTERVAL = 60_000; // 1 minute

export default function App() {
  const [symbol] = useState('SPY');
  const [spotPrice, setSpotPrice] = useState(null);
  const [candles, setCandles] = useState([]);
  const [gexData, setGexData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [triggeredAlerts, setTriggeredAlerts] = useState([]);
  const [calcResult, setCalcResult] = useState(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const [error, setError] = useState(null);
  const alertTimerRef = useRef(null);
  const candleTimerRef = useRef(null);

  // --- Data Loaders ---

  const fetchCandles = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/candles?symbol=${symbol}`);
      if (!res.ok) throw new Error('Failed to fetch candles');
      const data = await res.json();
      setCandles(data.candles || []);
      if (data.last_price) setSpotPrice(data.last_price);
    } catch (err) {
      console.error('Candle fetch error:', err.message);
    }
  }, [symbol]);

  const fetchGexData = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/gex?symbol=${symbol}`);
      if (!res.ok) throw new Error('Failed to fetch GEX data');
      const data = await res.json();
      setGexData(data);
    } catch (err) {
      console.error('GEX fetch error:', err.message);
    }
  }, [symbol]);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/alerts`);
      if (!res.ok) return;
      const data = await res.json();
      setAlerts(data.alerts || []);
    } catch {
      // Silent fail for alert polling
    }
  }, []);

  const pollAlerts = useCallback(async () => {
    if (!spotPrice || alerts.length === 0) return;

    const newlyTriggered = alerts.filter((alert) => {
      if (alert.triggered) return false;
      if (alert.condition === 'above' && spotPrice >= alert.price) return true;
      if (alert.condition === 'below' && spotPrice <= alert.price) return true;
      return false;
    });

    if (newlyTriggered.length > 0) {
      setTriggeredAlerts((prev) => [...prev, ...newlyTriggered]);
      // Notify backend
      for (const alert of newlyTriggered) {
        try {
          await fetch(`${API_URL}/api/spreadworks/alerts/${alert.id}/trigger`, {
            method: 'POST',
          });
        } catch {
          // Best-effort notification
        }
      }
    }
  }, [spotPrice, alerts]);

  // --- Initial Load ---

  useEffect(() => {
    fetchCandles();
    fetchGexData();
    fetchAlerts();
  }, [fetchCandles, fetchGexData, fetchAlerts]);

  // --- Polling ---

  useEffect(() => {
    candleTimerRef.current = setInterval(fetchCandles, CANDLE_REFRESH_INTERVAL);
    return () => clearInterval(candleTimerRef.current);
  }, [fetchCandles]);

  useEffect(() => {
    alertTimerRef.current = setInterval(() => {
      fetchAlerts();
      pollAlerts();
    }, ALERT_POLL_INTERVAL);
    return () => clearInterval(alertTimerRef.current);
  }, [fetchAlerts, pollAlerts]);

  // --- Calculate Handler ---

  const handleCalculate = async (payload) => {
    setCalcLoading(true);
    setCalcResult(null);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/calculate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Calculation failed');
      }
      const data = await res.json();
      setCalcResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setCalcLoading(false);
    }
  };

  // --- Dismiss Alert ---

  const dismissAlert = (id) => {
    setTriggeredAlerts((prev) => prev.filter((a) => a.id !== id));
  };

  // --- Render ---

  return (
    <div className="app">
      <header className="app-header">
        <h1>SpreadWorks</h1>
        <span className="subtitle">Double Diagonal &amp; Calendar Spread Analyzer</span>
        {spotPrice && (
          <span className="spot-badge">
            {symbol} ${spotPrice.toFixed(2)}
          </span>
        )}
      </header>

      {/* Triggered Alert Toasts */}
      {triggeredAlerts.length > 0 && (
        <div className="alert-toasts">
          {triggeredAlerts.map((alert) => (
            <div key={alert.id} className="alert-toast">
              <span>
                {alert.label || 'Alert'}: {symbol} {alert.condition} ${alert.price}
              </span>
              <button onClick={() => dismissAlert(alert.id)}>Dismiss</button>
            </div>
          ))}
        </div>
      )}

      <main className="two-column-grid">
        {/* Left Column: Strategy Builder */}
        <section className="column left-column">
          <StrategyPanel
            symbol={symbol}
            spotPrice={spotPrice}
            gexData={gexData}
            onCalculate={handleCalculate}
          />
        </section>

        {/* Right Column: Results & Market Data */}
        <section className="column right-column">
          {/* Candle Chart Placeholder */}
          <div className="panel candle-panel">
            <h3>Price Chart</h3>
            {candles.length > 0 ? (
              <div className="candle-summary">
                <span>Candles loaded: {candles.length}</span>
                <span>
                  Range: ${Math.min(...candles.map((c) => c.low)).toFixed(2)} &ndash; $
                  {Math.max(...candles.map((c) => c.high)).toFixed(2)}
                </span>
              </div>
            ) : (
              <p className="placeholder-text">Loading candle data...</p>
            )}
          </div>

          {/* GEX Summary */}
          <div className="panel gex-panel">
            <h3>GEX Levels</h3>
            {gexData ? (
              <div className="gex-summary">
                {gexData.flip_point && (
                  <div className="gex-row">
                    <span className="label">Flip Point</span>
                    <span className="value">${gexData.flip_point.toFixed(2)}</span>
                  </div>
                )}
                {gexData.call_wall && (
                  <div className="gex-row">
                    <span className="label">Call Wall</span>
                    <span className="value">${gexData.call_wall.toFixed(2)}</span>
                  </div>
                )}
                {gexData.put_wall && (
                  <div className="gex-row">
                    <span className="label">Put Wall</span>
                    <span className="value">${gexData.put_wall.toFixed(2)}</span>
                  </div>
                )}
                {gexData.gamma_regime && (
                  <div className="gex-row">
                    <span className="label">Regime</span>
                    <span className={`value regime-${gexData.gamma_regime.toLowerCase()}`}>
                      {gexData.gamma_regime}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <p className="placeholder-text">Loading GEX data...</p>
            )}
          </div>

          {/* Calculation Result */}
          <div className="panel result-panel">
            <h3>Spread Analysis</h3>
            {calcLoading && <p className="placeholder-text">Calculating...</p>}
            {error && <div className="error-banner">{error}</div>}
            {calcResult && (
              <div className="calc-result">
                <div className="result-row">
                  <span className="label">Max Profit</span>
                  <span className="value positive">
                    ${calcResult.max_profit?.toFixed(2) ?? '--'}
                  </span>
                </div>
                <div className="result-row">
                  <span className="label">Max Loss</span>
                  <span className="value negative">
                    ${calcResult.max_loss?.toFixed(2) ?? '--'}
                  </span>
                </div>
                <div className="result-row">
                  <span className="label">Net Debit</span>
                  <span className="value">
                    ${calcResult.net_debit?.toFixed(2) ?? '--'}
                  </span>
                </div>
                <div className="result-row">
                  <span className="label">Breakevens</span>
                  <span className="value">
                    {calcResult.lower_breakeven?.toFixed(2) ?? '--'} / {calcResult.upper_breakeven?.toFixed(2) ?? '--'}
                  </span>
                </div>
                {calcResult.probability_of_profit != null && (
                  <div className="result-row">
                    <span className="label">P(Profit)</span>
                    <span className="value">
                      {(calcResult.probability_of_profit * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
                {calcResult.greeks && (
                  <div className="greeks-grid">
                    <span>Delta: {calcResult.greeks.delta?.toFixed(3) ?? '--'}</span>
                    <span>Gamma: {calcResult.greeks.gamma?.toFixed(4) ?? '--'}</span>
                    <span>Theta: {calcResult.greeks.theta?.toFixed(3) ?? '--'}</span>
                    <span>Vega: {calcResult.greeks.vega?.toFixed(3) ?? '--'}</span>
                  </div>
                )}
              </div>
            )}
            {!calcResult && !calcLoading && !error && (
              <p className="placeholder-text">
                Configure a spread and click Calculate to see results.
              </p>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
