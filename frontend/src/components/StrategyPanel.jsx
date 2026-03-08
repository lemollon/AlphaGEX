import { useState, useEffect, useCallback } from 'react';

const STRATEGY_TYPES = {
  DOUBLE_DIAGONAL: 'double_diagonal',
  DOUBLE_CALENDAR: 'double_calendar',
};

const INPUT_MODES = {
  LIVE_CHAIN: 'live_chain',
  MANUAL: 'manual',
  GEX_SUGGEST: 'gex_suggest',
};

const DEFAULT_LEGS = {
  [STRATEGY_TYPES.DOUBLE_DIAGONAL]: {
    longPutStrike: '',
    shortPutStrike: '',
    shortCallStrike: '',
    longCallStrike: '',
    longExpiration: '',
    shortExpiration: '',
  },
  [STRATEGY_TYPES.DOUBLE_CALENDAR]: {
    putStrike: '',
    callStrike: '',
    frontExpiration: '',
    backExpiration: '',
  },
};

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function StrategyPanel({ symbol = 'SPY', spotPrice, gexData, onCalculate }) {
  const [strategy, setStrategy] = useState(STRATEGY_TYPES.DOUBLE_DIAGONAL);
  const [inputMode, setInputMode] = useState(INPUT_MODES.MANUAL);
  const [legs, setLegs] = useState(DEFAULT_LEGS[STRATEGY_TYPES.DOUBLE_DIAGONAL]);
  const [contracts, setContracts] = useState(1);
  const [expirations, setExpirations] = useState([]);
  const [chainStrikes, setChainStrikes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [gexSuggestion, setGexSuggestion] = useState(null);

  // Reset legs when strategy type changes
  useEffect(() => {
    setLegs(DEFAULT_LEGS[strategy]);
    setGexSuggestion(null);
  }, [strategy]);

  // Fetch expirations when in Live Chain mode
  useEffect(() => {
    if (inputMode !== INPUT_MODES.LIVE_CHAIN) return;

    async function fetchExpirations() {
      try {
        const res = await fetch(`${API_URL}/api/spreadworks/expirations?symbol=${symbol}`);
        if (!res.ok) throw new Error('Failed to fetch expirations');
        const data = await res.json();
        setExpirations(data.expirations || []);
      } catch (err) {
        setError(`Expirations: ${err.message}`);
      }
    }
    fetchExpirations();
  }, [inputMode, symbol]);

  // Fetch strikes for a given expiration
  const fetchStrikes = useCallback(async (expiration) => {
    if (!expiration) return;
    try {
      const res = await fetch(
        `${API_URL}/api/spreadworks/chain?symbol=${symbol}&expiration=${expiration}`
      );
      if (!res.ok) throw new Error('Failed to fetch chain');
      const data = await res.json();
      setChainStrikes(data.strikes || []);
    } catch (err) {
      setError(`Chain: ${err.message}`);
    }
  }, [symbol]);

  // Fetch GEX-suggested strikes
  const fetchGexSuggestion = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/spreadworks/gex-suggest?symbol=${symbol}&strategy=${strategy}`
      );
      if (!res.ok) throw new Error('Failed to fetch GEX suggestion');
      const data = await res.json();
      setGexSuggestion(data);

      // Auto-fill legs from suggestion
      if (strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL && data.legs) {
        setLegs({
          longPutStrike: data.legs.long_put_strike ?? '',
          shortPutStrike: data.legs.short_put_strike ?? '',
          shortCallStrike: data.legs.short_call_strike ?? '',
          longCallStrike: data.legs.long_call_strike ?? '',
          longExpiration: data.legs.long_expiration ?? '',
          shortExpiration: data.legs.short_expiration ?? '',
        });
      } else if (strategy === STRATEGY_TYPES.DOUBLE_CALENDAR && data.legs) {
        setLegs({
          putStrike: data.legs.put_strike ?? '',
          callStrike: data.legs.call_strike ?? '',
          frontExpiration: data.legs.front_expiration ?? '',
          backExpiration: data.legs.back_expiration ?? '',
        });
      }
    } catch (err) {
      setError(`GEX Suggest: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [symbol, strategy]);

  // Switch to GEX Suggest mode triggers fetch
  useEffect(() => {
    if (inputMode === INPUT_MODES.GEX_SUGGEST) {
      fetchGexSuggestion();
    }
  }, [inputMode, fetchGexSuggestion]);

  const updateLeg = (field, value) => {
    setLegs((prev) => ({ ...prev, [field]: value }));
  };

  const handleCalculate = () => {
    if (!onCalculate) return;

    const payload = {
      symbol,
      strategy,
      contracts,
      legs,
      spot_price: spotPrice,
      input_mode: inputMode,
    };
    onCalculate(payload);
  };

  const isFormValid = () => {
    if (strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL) {
      return (
        legs.longPutStrike &&
        legs.shortPutStrike &&
        legs.shortCallStrike &&
        legs.longCallStrike &&
        legs.longExpiration &&
        legs.shortExpiration
      );
    }
    return (
      legs.putStrike &&
      legs.callStrike &&
      legs.frontExpiration &&
      legs.backExpiration
    );
  };

  // Strike selector: dropdown in Live Chain mode, text input in Manual
  const StrikeInput = ({ label, field, value }) => {
    if (inputMode === INPUT_MODES.LIVE_CHAIN && chainStrikes.length > 0) {
      return (
        <div className="field">
          <label>{label}</label>
          <select value={value} onChange={(e) => updateLeg(field, e.target.value)}>
            <option value="">Select strike</option>
            {chainStrikes.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      );
    }
    return (
      <div className="field">
        <label>{label}</label>
        <input
          type="number"
          step="0.5"
          placeholder={label}
          value={value}
          onChange={(e) => updateLeg(field, e.target.value)}
          disabled={inputMode === INPUT_MODES.GEX_SUGGEST}
        />
      </div>
    );
  };

  const ExpirationInput = ({ label, field, value }) => {
    if (inputMode === INPUT_MODES.LIVE_CHAIN && expirations.length > 0) {
      return (
        <div className="field">
          <label>{label}</label>
          <select
            value={value}
            onChange={(e) => {
              updateLeg(field, e.target.value);
              fetchStrikes(e.target.value);
            }}
          >
            <option value="">Select expiration</option>
            {expirations.map((exp) => (
              <option key={exp} value={exp}>
                {exp}
              </option>
            ))}
          </select>
        </div>
      );
    }
    return (
      <div className="field">
        <label>{label}</label>
        <input
          type="date"
          value={value}
          onChange={(e) => updateLeg(field, e.target.value)}
          disabled={inputMode === INPUT_MODES.GEX_SUGGEST}
        />
      </div>
    );
  };

  return (
    <div className="strategy-panel">
      <h2>Strategy Builder</h2>

      {/* Strategy Type Selector */}
      <div className="strategy-type-selector">
        <button
          className={strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL ? 'active' : ''}
          onClick={() => setStrategy(STRATEGY_TYPES.DOUBLE_DIAGONAL)}
        >
          Double Diagonal
        </button>
        <button
          className={strategy === STRATEGY_TYPES.DOUBLE_CALENDAR ? 'active' : ''}
          onClick={() => setStrategy(STRATEGY_TYPES.DOUBLE_CALENDAR)}
        >
          Double Calendar
        </button>
      </div>

      {/* Input Mode Tabs */}
      <div className="input-mode-tabs">
        {Object.entries(INPUT_MODES).map(([key, mode]) => (
          <button
            key={mode}
            className={inputMode === mode ? 'active' : ''}
            onClick={() => setInputMode(mode)}
          >
            {key === 'LIVE_CHAIN' ? 'Live Chain' : key === 'MANUAL' ? 'Manual' : 'GEX Suggest'}
          </button>
        ))}
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* GEX Suggestion Banner */}
      {inputMode === INPUT_MODES.GEX_SUGGEST && gexSuggestion && (
        <div className="gex-suggestion-banner">
          <strong>GEX-Based Suggestion</strong>
          {gexSuggestion.rationale && <p>{gexSuggestion.rationale}</p>}
          {gexSuggestion.flip_point && (
            <span className="tag">Flip: ${gexSuggestion.flip_point.toFixed(2)}</span>
          )}
          {gexSuggestion.gamma_regime && (
            <span className="tag">{gexSuggestion.gamma_regime}</span>
          )}
        </div>
      )}

      {/* Spot Price Display */}
      <div className="spot-display">
        <span className="label">Spot</span>
        <span className="value">{spotPrice ? `$${spotPrice.toFixed(2)}` : '--'}</span>
        <span className="label">Symbol</span>
        <span className="value">{symbol}</span>
      </div>

      {/* Leg Inputs */}
      <div className="legs-form">
        {strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL ? (
          <>
            <fieldset>
              <legend>Put Side</legend>
              <StrikeInput label="Long Put Strike" field="longPutStrike" value={legs.longPutStrike} />
              <StrikeInput label="Short Put Strike" field="shortPutStrike" value={legs.shortPutStrike} />
            </fieldset>
            <fieldset>
              <legend>Call Side</legend>
              <StrikeInput label="Short Call Strike" field="shortCallStrike" value={legs.shortCallStrike} />
              <StrikeInput label="Long Call Strike" field="longCallStrike" value={legs.longCallStrike} />
            </fieldset>
            <fieldset>
              <legend>Expirations</legend>
              <ExpirationInput label="Short Expiration (front)" field="shortExpiration" value={legs.shortExpiration} />
              <ExpirationInput label="Long Expiration (back)" field="longExpiration" value={legs.longExpiration} />
            </fieldset>
          </>
        ) : (
          <>
            <fieldset>
              <legend>Strikes</legend>
              <StrikeInput label="Put Strike" field="putStrike" value={legs.putStrike} />
              <StrikeInput label="Call Strike" field="callStrike" value={legs.callStrike} />
            </fieldset>
            <fieldset>
              <legend>Expirations</legend>
              <ExpirationInput label="Front Expiration" field="frontExpiration" value={legs.frontExpiration} />
              <ExpirationInput label="Back Expiration" field="backExpiration" value={legs.backExpiration} />
            </fieldset>
          </>
        )}
      </div>

      {/* Contracts */}
      <div className="field contracts-field">
        <label>Contracts</label>
        <input
          type="number"
          min={1}
          max={100}
          value={contracts}
          onChange={(e) => setContracts(Math.max(1, parseInt(e.target.value, 10) || 1))}
        />
      </div>

      {/* Calculate Button */}
      <button
        className="calculate-btn"
        onClick={handleCalculate}
        disabled={!isFormValid() || loading}
      >
        {loading ? 'Loading...' : 'Calculate'}
      </button>
    </div>
  );
}
