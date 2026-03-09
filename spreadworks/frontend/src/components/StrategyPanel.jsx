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

const API_URL = import.meta.env.VITE_API_URL || '';

const s = {
  panel: {
    width: 260,
    minWidth: 260,
    background: '#0d0d18',
    borderRight: '1px solid #1a1a2e',
    padding: '12px 14px',
    overflowY: 'auto',
    fontFamily: "'Courier New', monospace",
    fontSize: 12,
    color: '#ccc',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    height: '100%',
  },
  logo: {
    display: 'flex',
    alignItems: 'baseline',
    gap: 0,
    marginBottom: 2,
  },
  logoWhite: { color: '#fff', fontWeight: 700, fontSize: 16, letterSpacing: -0.5 },
  logoBlue: { color: '#448aff', fontWeight: 700, fontSize: 16, letterSpacing: -0.5 },
  subtitle: { color: '#555', fontSize: 10, marginBottom: 4 },
  sectionLabel: {
    color: '#555',
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    marginBottom: 2,
    marginTop: 6,
  },
  toggleRow: {
    display: 'flex',
    gap: 4,
    marginBottom: 4,
  },
  toggleBtn: (active) => ({
    flex: 1,
    padding: '5px 4px',
    border: `1px solid ${active ? '#448aff' : '#1a1a2e'}`,
    borderRadius: 4,
    background: active ? '#448aff' : 'transparent',
    color: active ? '#fff' : '#666',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: "'Courier New', monospace",
    textAlign: 'center',
    transition: 'all 0.15s',
  }),
  spotRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '4px 6px',
    background: '#080810',
    borderRadius: 4,
    fontSize: 11,
  },
  spotLabel: { color: '#555' },
  spotValue: { color: '#fff', fontWeight: 600 },
  sideLabel: (color) => ({
    color: color,
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    borderBottom: `1px solid ${color}33`,
    paddingBottom: 2,
    marginTop: 6,
    marginBottom: 4,
  }),
  fieldRow: {
    display: 'flex',
    gap: 6,
    marginBottom: 4,
  },
  fieldCol: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  fieldLabel: (color) => ({
    fontSize: 9,
    color: color || '#555',
    textTransform: 'uppercase',
  }),
  input: (borderColor) => ({
    width: '100%',
    padding: '4px 6px',
    border: `1px solid ${borderColor || '#1a1a2e'}`,
    borderRadius: 3,
    background: '#080810',
    color: '#e0e0e0',
    fontSize: 12,
    fontFamily: "'Courier New', monospace",
    outline: 'none',
    boxSizing: 'border-box',
  }),
  select: (borderColor) => ({
    width: '100%',
    padding: '4px 6px',
    border: `1px solid ${borderColor || '#1a1a2e'}`,
    borderRadius: 3,
    background: '#080810',
    color: '#e0e0e0',
    fontSize: 12,
    fontFamily: "'Courier New', monospace",
    outline: 'none',
    boxSizing: 'border-box',
  }),
  calcBtn: {
    width: '100%',
    padding: '8px',
    border: '1px solid #448aff',
    borderRadius: 4,
    background: '#448aff22',
    color: '#448aff',
    fontWeight: 700,
    fontSize: 13,
    fontFamily: "'Courier New', monospace",
    cursor: 'pointer',
    transition: 'all 0.15s',
    marginTop: 4,
  },
  calcBtnDisabled: {
    opacity: 0.4,
    cursor: 'not-allowed',
  },
  alertSection: {
    marginTop: 4,
  },
  alertRow: {
    display: 'flex',
    gap: 4,
    marginTop: 4,
  },
  alertSelect: {
    width: 60,
    padding: '3px 4px',
    border: '1px solid #1a1a2e',
    borderRadius: 3,
    background: '#080810',
    color: '#ccc',
    fontSize: 11,
    fontFamily: "'Courier New', monospace",
  },
  alertInput: {
    flex: 1,
    padding: '3px 6px',
    border: '1px solid #1a1a2e',
    borderRadius: 3,
    background: '#080810',
    color: '#ccc',
    fontSize: 11,
    fontFamily: "'Courier New', monospace",
    minWidth: 0,
  },
  alertAddBtn: {
    padding: '3px 8px',
    border: '1px solid #448aff',
    borderRadius: 3,
    background: '#448aff',
    color: '#fff',
    fontSize: 11,
    fontFamily: "'Courier New', monospace",
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  alertList: {
    listStyle: 'none',
    padding: 0,
    margin: '4px 0 0 0',
  },
  alertItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '3px 0',
    borderBottom: '1px solid #1a1a2e',
    fontSize: 11,
  },
  alertDel: {
    background: 'transparent',
    border: 'none',
    color: '#555',
    cursor: 'pointer',
    fontSize: 14,
    padding: '0 2px',
  },
  gexBanner: {
    background: '#0d1a2e',
    border: '1px solid #448aff33',
    borderRadius: 4,
    padding: '6px 8px',
    fontSize: 10,
    color: '#448aff',
    marginBottom: 4,
  },
  error: {
    background: '#1a0a0a',
    border: '1px solid #ff1744',
    borderRadius: 4,
    padding: '4px 8px',
    fontSize: 10,
    color: '#ff5252',
  },
};

function StrikeInput({ label, value, color, inputMode, chainStrikes, chainOptions, onChange, disabled }) {
  const borderColor = color === '#00e676' ? '#00e67644' : '#ff525244';
  const optionType = label.toLowerCase().includes('put') ? 'put' : 'call';
  // Live Chain mode: dropdown with delta info
  if (inputMode === INPUT_MODES.LIVE_CHAIN && chainStrikes.length > 0) {
    return (
      <div style={s.fieldCol}>
        <span style={s.fieldLabel(color)}>{label}</span>
        <select
          style={s.select(borderColor)}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">--</option>
          {chainStrikes.map((sk) => {
            const opt = chainOptions[sk]?.[optionType];
            const delta = opt?.delta;
            const displayDelta = delta != null ? ` (\u0394${Math.abs(delta).toFixed(2)})` : '';
            return (
              <option key={sk} value={sk}>${sk}{displayDelta}</option>
            );
          })}
        </select>
      </div>
    );
  }
  // Manual and GEX Suggest: plain text input (no spinners)
  return (
    <div style={s.fieldCol}>
      <span style={s.fieldLabel(color)}>{label}</span>
      <input
        type="text"
        inputMode="numeric"
        pattern="[0-9.]*"
        placeholder={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        style={{
          width: '100%',
          background: '#111120',
          border: `1px solid ${borderColor || '#1e1e32'}`,
          color: '#ccc',
          padding: '6px 8px',
          fontSize: '11px',
          borderRadius: '3px',
          fontFamily: 'inherit',
          outline: 'none',
          boxSizing: 'border-box',
        }}
      />
    </div>
  );
}

function ExpirationInput({ label, value, inputMode, expirations, onChange, onFetchStrikes, disabled }) {
  if (inputMode === INPUT_MODES.LIVE_CHAIN && expirations.length > 0) {
    return (
      <div style={s.fieldCol}>
        <span style={s.fieldLabel()}>{label}</span>
        <select
          style={s.select()}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            if (onFetchStrikes) onFetchStrikes(e.target.value);
          }}
        >
          <option value="">--</option>
          {expirations.map((exp) => (
            <option key={exp} value={exp}>{exp}</option>
          ))}
        </select>
      </div>
    );
  }
  return (
    <div style={s.fieldCol}>
      <span style={s.fieldLabel()}>{label}</span>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        style={s.input()}
      />
    </div>
  );
}

export default function StrategyPanel({
  symbol = 'SPY',
  spotPrice,
  gexData,
  onCalculate,
  calcLoading,
  calcError,
  calcResult,
  alerts,
  onRefreshAlerts,
}) {
  const [strategy, setStrategy] = useState(STRATEGY_TYPES.DOUBLE_DIAGONAL);
  const [inputMode, setInputMode] = useState(INPUT_MODES.MANUAL);
  const [legs, setLegs] = useState(DEFAULT_LEGS[STRATEGY_TYPES.DOUBLE_DIAGONAL]);
  const [contracts, setContracts] = useState(1);
  const [expirations, setExpirations] = useState([]);
  const [chainStrikes, setChainStrikes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [gexSuggestion, setGexSuggestion] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  // Alert form state
  const [alertPrice, setAlertPrice] = useState('');
  const [alertCondition, setAlertCondition] = useState('above');
  const [alertCreating, setAlertCreating] = useState(false);

  const handleSavePosition = async () => {
    if (!calcResult || !spotPrice) return;
    setSaving(true);
    setSaveMsg('');
    try {
      // Map legs to individual strike fields based on strategy
      let long_put, short_put, short_call, long_call, short_exp, long_exp;
      if (strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL) {
        long_put = parseFloat(legs.longPutStrike) || 0;
        short_put = parseFloat(legs.shortPutStrike) || 0;
        short_call = parseFloat(legs.shortCallStrike) || 0;
        long_call = parseFloat(legs.longCallStrike) || 0;
        short_exp = legs.shortExpiration;
        long_exp = legs.longExpiration;
      } else {
        long_put = parseFloat(legs.putStrike) || 0;
        short_put = parseFloat(legs.putStrike) || 0;
        short_call = parseFloat(legs.callStrike) || 0;
        long_call = parseFloat(legs.callStrike) || 0;
        short_exp = legs.frontExpiration;
        long_exp = legs.backExpiration;
      }

      // entry_credit is the absolute value of net_debit (credit received)
      const entryCredit = Math.abs(calcResult.net_debit);
      const entryPrice = entryCredit / (contracts * 100);

      const res = await fetch(`${API_URL}/api/spreadworks/positions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          strategy,
          contracts,
          long_put,
          short_put,
          short_call,
          long_call,
          short_exp,
          long_exp,
          entry_credit: entryCredit,
          entry_price: entryPrice,
          entry_spot: spotPrice,
          max_profit: calcResult.max_profit || null,
          max_loss: calcResult.max_loss || null,
          breakeven_low: calcResult.lower_breakeven || null,
          breakeven_high: calcResult.upper_breakeven || null,
          notes: '',
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save');
      }
      setSaveMsg('Saved!');
      setTimeout(() => setSaveMsg(''), 3000);
    } catch (err) {
      setSaveMsg(err.message);
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    setLegs(DEFAULT_LEGS[strategy]);
    setGexSuggestion(null);
  }, [strategy]);

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

  const [chainOptions, setChainOptions] = useState({});

  const fetchStrikes = useCallback(async (expiration) => {
    if (!expiration) return;
    try {
      const res = await fetch(
        `${API_URL}/api/spreadworks/chain?symbol=${symbol}&expiration=${expiration}`
      );
      if (!res.ok) throw new Error('Failed to fetch chain');
      const data = await res.json();
      setChainStrikes(data.strikes || []);
      setChainOptions(data.options || {});
    } catch (err) {
      setError(`Chain: ${err.message}`);
    }
  }, [symbol]);

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
    onCalculate({
      symbol,
      strategy,
      contracts,
      legs,
      spot_price: spotPrice,
      input_mode: inputMode,
    });
  };

  const isFormValid = () => {
    if (strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL) {
      return legs.longPutStrike && legs.shortPutStrike && legs.shortCallStrike && legs.longCallStrike && legs.longExpiration && legs.shortExpiration;
    }
    return legs.putStrike && legs.callStrike && legs.frontExpiration && legs.backExpiration;
  };

  const handleAddAlert = async (e) => {
    e.preventDefault();
    if (!alertPrice) return;
    setAlertCreating(true);
    try {
      await fetch(`${API_URL}/api/spreadworks/alerts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ price: parseFloat(alertPrice), condition: alertCondition, label: '' }),
      });
      setAlertPrice('');
      if (onRefreshAlerts) onRefreshAlerts();
    } catch {
      // silent
    } finally {
      setAlertCreating(false);
    }
  };

  const handleDeleteAlert = async (id) => {
    try {
      await fetch(`${API_URL}/api/spreadworks/alerts/${id}`, { method: 'DELETE' });
      if (onRefreshAlerts) onRefreshAlerts();
    } catch {
      // silent
    }
  };

  return (
    <div style={s.panel}>
      {/* Logo */}
      <div>
        <div style={s.logo}>
          <span style={s.logoWhite}>Spread</span>
          <span style={s.logoBlue}>Works</span>
        </div>
        <div style={s.subtitle}>DD & Calendar Analyzer</div>
      </div>

      {/* Strategy toggle */}
      <div>
        <div style={s.sectionLabel}>STRATEGY</div>
        <div style={s.toggleRow}>
          <button
            style={s.toggleBtn(strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL)}
            onClick={() => setStrategy(STRATEGY_TYPES.DOUBLE_DIAGONAL)}
          >Dbl Diagonal</button>
          <button
            style={s.toggleBtn(strategy === STRATEGY_TYPES.DOUBLE_CALENDAR)}
            onClick={() => setStrategy(STRATEGY_TYPES.DOUBLE_CALENDAR)}
          >Dbl Calendar</button>
        </div>
      </div>

      {/* Input mode toggle */}
      <div>
        <div style={s.sectionLabel}>INPUT MODE</div>
        <div style={s.toggleRow}>
          <button style={s.toggleBtn(inputMode === INPUT_MODES.LIVE_CHAIN)} onClick={() => setInputMode(INPUT_MODES.LIVE_CHAIN)}>Live Chain</button>
          <button style={s.toggleBtn(inputMode === INPUT_MODES.MANUAL)} onClick={() => setInputMode(INPUT_MODES.MANUAL)}>Manual</button>
          <button style={s.toggleBtn(inputMode === INPUT_MODES.GEX_SUGGEST)} onClick={() => setInputMode(INPUT_MODES.GEX_SUGGEST)}>GEX Suggest</button>
        </div>
      </div>

      {(error || calcError) && <div style={s.error}>{error || calcError}</div>}

      {/* GEX Suggestion */}
      {inputMode === INPUT_MODES.GEX_SUGGEST && gexSuggestion && (
        <div style={s.gexBanner}>
          <strong>GEX Suggestion</strong>
          {gexSuggestion.rationale && <div style={{ color: '#888', marginTop: 2 }}>{gexSuggestion.rationale}</div>}
        </div>
      )}

      {/* Spot */}
      <div style={s.spotRow}>
        <span style={s.spotLabel}>Symbol</span>
        <span style={{ ...s.spotValue, marginRight: 4 }}>{symbol}</span>
        <span style={{ color: '#333' }}>&middot;</span>
        <span style={{ ...s.spotLabel, marginLeft: 4 }}>Spot:</span>
        <span style={s.spotValue}>{spotPrice ? `$${spotPrice.toFixed(2)}` : '--'}</span>
      </div>

      {/* Legs */}
      {strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL ? (
        <>
          <div style={s.sideLabel('#00e676')}>-- PUT SIDE --</div>
          <div style={s.fieldRow}>
            <StrikeInput label="Long Put" value={legs.longPutStrike} color="#00e676" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            <StrikeInput label="Short Put" value={legs.shortPutStrike} color="#ff5252" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
          </div>
          <div style={s.sideLabel('#ff5252')}>-- CALL SIDE --</div>
          <div style={s.fieldRow}>
            <StrikeInput label="Short Call" value={legs.shortCallStrike} color="#ff5252" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            <StrikeInput label="Long Call" value={legs.longCallStrike} color="#00e676" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
          </div>
          <div style={s.fieldRow}>
            <ExpirationInput label="Short Exp" value={legs.shortExpiration} inputMode={inputMode} expirations={expirations} onChange={(v) => updateLeg('shortExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            <ExpirationInput label="Long Exp" value={legs.longExpiration} inputMode={inputMode} expirations={expirations} onChange={(v) => updateLeg('longExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
          </div>
        </>
      ) : (
        <>
          <div style={s.sideLabel('#448aff')}>-- STRIKES --</div>
          <div style={s.fieldRow}>
            <StrikeInput label="Put Strike" value={legs.putStrike} color="#ff5252" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('putStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            <StrikeInput label="Call Strike" value={legs.callStrike} color="#00e676" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('callStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
          </div>
          <div style={s.fieldRow}>
            <ExpirationInput label="Front Exp" value={legs.frontExpiration} inputMode={inputMode} expirations={expirations} onChange={(v) => updateLeg('frontExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            <ExpirationInput label="Back Exp" value={legs.backExpiration} inputMode={inputMode} expirations={expirations} onChange={(v) => updateLeg('backExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
          </div>
        </>
      )}

      {/* Contracts */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={s.fieldLabel()}>Contracts</span>
        <input
          type="number"
          min={1}
          max={100}
          value={contracts}
          onChange={(e) => setContracts(Math.max(1, parseInt(e.target.value, 10) || 1))}
          style={{ ...s.input(), width: 50 }}
        />
      </div>

      {/* Calculate */}
      <button
        style={{ ...s.calcBtn, ...((!isFormValid() || calcLoading || loading) ? s.calcBtnDisabled : {}) }}
        onClick={handleCalculate}
        disabled={!isFormValid() || calcLoading || loading}
      >
        {calcLoading || loading ? 'Loading...' : '\u26A1 CALCULATE'}
      </button>

      {/* Save Position — only visible after calculate */}
      {calcResult && (
        <button
          style={{
            ...s.calcBtn,
            background: '#00e67622',
            color: '#00e676',
            border: '1px solid #00e676',
            marginTop: 2,
            ...(saving ? s.calcBtnDisabled : {}),
          }}
          onClick={handleSavePosition}
          disabled={saving}
        >
          {saving ? 'Saving...' : '\uD83D\uDCBE SAVE POSITION'}
        </button>
      )}
      {saveMsg && (
        <div style={{
          fontSize: 10,
          color: saveMsg === 'Saved!' ? '#00e676' : '#ff5252',
          textAlign: 'center',
          marginTop: 2,
        }}>
          {saveMsg}
        </div>
      )}

      {/* Price Alerts */}
      <div style={s.alertSection}>
        <div style={s.sectionLabel}>PRICE ALERTS</div>
        <form onSubmit={handleAddAlert}>
          <div style={s.alertRow}>
            <select style={s.alertSelect} value={alertCondition} onChange={(e) => setAlertCondition(e.target.value)}>
              <option value="above">Above</option>
              <option value="below">Below</option>
            </select>
            <input
              type="number"
              step="0.01"
              placeholder="Price"
              value={alertPrice}
              onChange={(e) => setAlertPrice(e.target.value)}
              style={s.alertInput}
            />
            <button type="submit" disabled={alertCreating || !alertPrice} style={s.alertAddBtn}>+Add</button>
          </div>
        </form>
        {alerts && alerts.length > 0 && (
          <ul style={s.alertList}>
            {alerts.map((a) => (
              <li key={a.id} style={{ ...s.alertItem, opacity: a.triggered ? 0.5 : 1 }}>
                <span>{a.condition} ${a.price}{a.triggered ? ' \u26A1' : ''}</span>
                <button style={s.alertDel} onClick={() => handleDeleteAlert(a.id)}>&times;</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
