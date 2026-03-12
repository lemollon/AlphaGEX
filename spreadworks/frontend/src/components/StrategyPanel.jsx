import { useState, useEffect, useCallback, useRef } from 'react';

const STRATEGY_TYPES = {
  DOUBLE_DIAGONAL: 'double_diagonal',
  DOUBLE_CALENDAR: 'double_calendar',
  IRON_CONDOR: 'iron_condor',
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
  [STRATEGY_TYPES.IRON_CONDOR]: {
    longPutStrike: '',
    shortPutStrike: '',
    shortCallStrike: '',
    longCallStrike: '',
    expiration: '',
  },
};

const API_URL = import.meta.env.VITE_API_URL || '';

/* ── Design Tokens ── */
const s = {
  panel: {
    width: 280,
    minWidth: 280,
    background: 'var(--bg-surface)',
    borderRight: '1px solid var(--border-subtle)',
    padding: '16px',
    overflowY: 'auto',
    fontFamily: 'var(--font-ui)',
    fontSize: 13,
    color: 'var(--text-primary)',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    height: '100%',
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: 2,
    marginBottom: 0,
  },
  logoIcon: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 28,
    height: 28,
    borderRadius: 'var(--radius-md)',
    background: 'linear-gradient(135deg, var(--accent) 0%, #7c4dff 100%)',
    marginRight: 8,
    fontSize: 14,
    color: '#fff',
    fontWeight: 800,
    boxShadow: '0 2px 8px rgba(68, 138, 255, 0.3)',
  },
  logoText: {
    fontSize: 18,
    fontWeight: 800,
    letterSpacing: '-0.5px',
    color: '#fff',
  },
  logoAccent: {
    color: 'var(--accent)',
  },
  subtitle: {
    color: 'var(--text-tertiary)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '0.02em',
  },
  card: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px',
  },
  sectionLabel: {
    color: 'var(--text-tertiary)',
    fontSize: 10,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    marginBottom: 8,
  },
  toggleRow: {
    display: 'flex',
    gap: 4,
    background: 'var(--bg-elevated)',
    borderRadius: 'var(--radius-md)',
    padding: 3,
  },
  toggleBtn: (active) => ({
    flex: 1,
    padding: '7px 6px',
    border: 'none',
    borderRadius: 'var(--radius-sm)',
    background: active
      ? 'linear-gradient(135deg, var(--accent) 0%, #5c9bff 100%)'
      : 'transparent',
    color: active ? '#fff' : 'var(--text-tertiary)',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: 'var(--font-ui)',
    fontWeight: active ? 600 : 500,
    textAlign: 'center',
    transition: 'all var(--transition-fast)',
    boxShadow: active ? '0 2px 8px rgba(68, 138, 255, 0.25)' : 'none',
  }),
  spotRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 12px',
    background: 'var(--bg-elevated)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-subtle)',
  },
  spotLabel: {
    color: 'var(--text-tertiary)',
    fontSize: 11,
    fontWeight: 500,
  },
  spotSymbol: {
    color: '#fff',
    fontWeight: 700,
    fontSize: 14,
    fontFamily: 'var(--font-mono)',
  },
  spotDot: {
    width: 4,
    height: 4,
    borderRadius: '50%',
    background: 'var(--text-muted)',
  },
  spotValue: {
    color: 'var(--accent)',
    fontWeight: 700,
    fontSize: 14,
    fontFamily: 'var(--font-mono)',
  },
  sideLabel: (color) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    color: color,
    fontSize: 10,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    marginTop: 4,
    marginBottom: 6,
  }),
  sideLine: (color) => ({
    flex: 1,
    height: 1,
    background: `${color}22`,
  }),
  fieldRow: {
    display: 'flex',
    gap: 8,
    marginBottom: 6,
  },
  fieldCol: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  fieldLabel: (color) => ({
    fontSize: 10,
    color: color || 'var(--text-tertiary)',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  }),
  input: (borderColor) => ({
    width: '100%',
    padding: '8px 10px',
    border: `1px solid ${borderColor || 'var(--border-subtle)'}`,
    borderRadius: 'var(--radius-sm)',
    background: 'var(--bg-elevated)',
    color: 'var(--text-primary)',
    fontSize: 13,
    fontFamily: 'var(--font-mono)',
    fontWeight: 500,
    outline: 'none',
    boxSizing: 'border-box',
    transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast)',
  }),
  select: (borderColor) => ({
    width: '100%',
    padding: '8px 10px',
    border: `1px solid ${borderColor || 'var(--border-subtle)'}`,
    borderRadius: 'var(--radius-sm)',
    background: 'var(--bg-elevated)',
    color: 'var(--text-primary)',
    fontSize: 13,
    fontFamily: 'var(--font-mono)',
    fontWeight: 500,
    outline: 'none',
    boxSizing: 'border-box',
    transition: 'border-color var(--transition-fast)',
  }),
  calcBtn: {
    width: '100%',
    padding: '10px 12px',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    background: 'linear-gradient(135deg, var(--accent) 0%, #5c9bff 100%)',
    color: '#fff',
    fontWeight: 700,
    fontSize: 13,
    fontFamily: 'var(--font-ui)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
    boxShadow: '0 2px 12px rgba(68, 138, 255, 0.3)',
    letterSpacing: '0.03em',
  },
  calcBtnDisabled: {
    opacity: 0.35,
    cursor: 'not-allowed',
    boxShadow: 'none',
  },
  actionBtn: (bg, color, borderColor) => ({
    width: '100%',
    padding: '9px 12px',
    border: `1px solid ${borderColor}`,
    borderRadius: 'var(--radius-md)',
    background: bg,
    color: color,
    fontWeight: 600,
    fontSize: 12,
    fontFamily: 'var(--font-ui)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
    letterSpacing: '0.02em',
  }),
  alertSection: {
    marginTop: 4,
  },
  alertRow: {
    display: 'flex',
    gap: 6,
    marginTop: 6,
  },
  alertSelect: {
    width: 68,
    padding: '6px 8px',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--bg-elevated)',
    color: 'var(--text-secondary)',
    fontSize: 12,
    fontFamily: 'var(--font-ui)',
    fontWeight: 500,
  },
  alertInput: {
    flex: 1,
    padding: '6px 10px',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--bg-elevated)',
    color: 'var(--text-primary)',
    fontSize: 12,
    fontFamily: 'var(--font-mono)',
    fontWeight: 500,
    minWidth: 0,
  },
  alertAddBtn: {
    padding: '6px 12px',
    border: 'none',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--accent)',
    color: '#fff',
    fontSize: 12,
    fontFamily: 'var(--font-ui)',
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  alertList: {
    listStyle: 'none',
    padding: 0,
    margin: '6px 0 0 0',
  },
  alertItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 8px',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--bg-elevated)',
    fontSize: 12,
    fontFamily: 'var(--font-mono)',
    marginBottom: 4,
  },
  alertDel: {
    background: 'transparent',
    border: 'none',
    color: 'var(--text-tertiary)',
    cursor: 'pointer',
    fontSize: 16,
    padding: '0 4px',
    lineHeight: 1,
  },
  gexBanner: {
    background: 'linear-gradient(135deg, rgba(68, 138, 255, 0.08) 0%, rgba(124, 77, 255, 0.06) 100%)',
    border: '1px solid var(--border-accent)',
    borderRadius: 'var(--radius-md)',
    padding: '10px 12px',
    fontSize: 11,
    color: 'var(--accent)',
    animation: 'sw-fadeIn 0.3s ease',
  },
  error: {
    background: 'var(--red-dim)',
    border: '1px solid rgba(255, 82, 82, 0.3)',
    borderRadius: 'var(--radius-md)',
    padding: '8px 12px',
    fontSize: 11,
    color: 'var(--red)',
    fontWeight: 500,
  },
};

function StrikeInput({ label, value, color, inputMode, chainStrikes, chainOptions, onChange, disabled }) {
  const borderColor = color === '#00e676' ? 'rgba(0, 230, 118, 0.25)' : 'rgba(255, 82, 82, 0.25)';
  const optionType = label.toLowerCase().includes('put') ? 'put' : 'call';
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
        style={s.input(borderColor)}
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
  const [pushing, setPushing] = useState(false);
  const [pushMsg, setPushMsg] = useState('');

  const [alertPrice, setAlertPrice] = useState('');
  const [alertCondition, setAlertCondition] = useState('above');
  const [alertCreating, setAlertCreating] = useState(false);

  const prevSymbolRef = useRef(symbol);
  useEffect(() => {
    if (prevSymbolRef.current !== symbol) {
      prevSymbolRef.current = symbol;
      setLegs(DEFAULT_LEGS[strategy]);
      setContracts(1);
      setExpirations([]);
      setChainStrikes([]);
      setGexSuggestion(null);
      setError(null);
      setSaveMsg('');
      setPushMsg('');
    }
  }, [symbol, strategy]);

  const handleSavePosition = async () => {
    if (!calcResult || !spotPrice) return;
    setSaving(true);
    setSaveMsg('');
    try {
      let long_put, short_put, short_call, long_call, short_exp, long_exp;
      if (strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL) {
        long_put = parseFloat(legs.longPutStrike) || 0;
        short_put = parseFloat(legs.shortPutStrike) || 0;
        short_call = parseFloat(legs.shortCallStrike) || 0;
        long_call = parseFloat(legs.longCallStrike) || 0;
        short_exp = legs.shortExpiration;
        long_exp = legs.longExpiration;
      } else if (strategy === STRATEGY_TYPES.IRON_CONDOR) {
        long_put = parseFloat(legs.longPutStrike) || 0;
        short_put = parseFloat(legs.shortPutStrike) || 0;
        short_call = parseFloat(legs.shortCallStrike) || 0;
        long_call = parseFloat(legs.longCallStrike) || 0;
        short_exp = legs.expiration;
        long_exp = null;
      } else {
        long_put = parseFloat(legs.putStrike) || 0;
        short_put = parseFloat(legs.putStrike) || 0;
        short_call = parseFloat(legs.callStrike) || 0;
        long_call = parseFloat(legs.callStrike) || 0;
        short_exp = legs.frontExpiration;
        long_exp = legs.backExpiration;
      }

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

  const handlePushDiscord = async () => {
    if (!calcResult || !spotPrice) return;
    setPushing(true);
    setPushMsg('');
    try {
      let legPayload, shortExp, longExp;
      if (strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL) {
        legPayload = {
          long_put: parseFloat(legs.longPutStrike) || 0,
          short_put: parseFloat(legs.shortPutStrike) || 0,
          short_call: parseFloat(legs.shortCallStrike) || 0,
          long_call: parseFloat(legs.longCallStrike) || 0,
        };
        shortExp = legs.shortExpiration;
        longExp = legs.longExpiration;
      } else if (strategy === STRATEGY_TYPES.IRON_CONDOR) {
        legPayload = {
          long_put: parseFloat(legs.longPutStrike) || 0,
          short_put: parseFloat(legs.shortPutStrike) || 0,
          short_call: parseFloat(legs.shortCallStrike) || 0,
          long_call: parseFloat(legs.longCallStrike) || 0,
        };
        shortExp = legs.expiration;
        longExp = null;
      } else {
        legPayload = {
          long_put: parseFloat(legs.putStrike) || 0,
          short_put: parseFloat(legs.putStrike) || 0,
          short_call: parseFloat(legs.callStrike) || 0,
          long_call: parseFloat(legs.callStrike) || 0,
        };
        shortExp = legs.frontExpiration;
        longExp = legs.backExpiration;
      }

      const strategyLabels = {
        [STRATEGY_TYPES.DOUBLE_DIAGONAL]: 'Dbl Diagonal',
        [STRATEGY_TYPES.DOUBLE_CALENDAR]: 'Dbl Calendar',
        [STRATEGY_TYPES.IRON_CONDOR]: 'Iron Condor',
      };

      const res = await fetch(`${API_URL}/api/spreadworks/discord/push-spread`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          strategy: strategyLabels[strategy] || strategy,
          spot: spotPrice,
          legs: legPayload,
          short_exp: shortExp,
          long_exp: longExp,
          net_credit: calcResult.net_debit ? -calcResult.net_debit : null,
          max_profit: calcResult.max_profit || null,
          max_loss: calcResult.max_loss || null,
          breakevens: [calcResult.lower_breakeven, calcResult.upper_breakeven].filter(Boolean),
          chance_of_profit: calcResult.probability_of_profit != null
            ? calcResult.probability_of_profit * 100
            : calcResult.chance_of_profit != null
              ? calcResult.chance_of_profit * 100
              : null,
          implied_vol: calcResult.implied_vol != null ? calcResult.implied_vol * 100 : null,
          contracts,
          gex_suggestion: gexSuggestion?.rationale || '',
          pricing_mode: calcResult.pricing_mode || '',
          pnl_curve: calcResult.pnl_curve || [],
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Failed to post');
      setPushMsg('Posted!');
      setTimeout(() => setPushMsg(''), 3000);
    } catch (err) {
      setPushMsg(err.message);
    } finally {
      setPushing(false);
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
      } else if (strategy === STRATEGY_TYPES.IRON_CONDOR && data.legs) {
        setLegs({
          longPutStrike: data.legs.long_put_strike ?? '',
          shortPutStrike: data.legs.short_put_strike ?? '',
          shortCallStrike: data.legs.short_call_strike ?? '',
          longCallStrike: data.legs.long_call_strike ?? '',
          expiration: data.legs.expiration ?? '',
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
    if (strategy === STRATEGY_TYPES.IRON_CONDOR) {
      return legs.longPutStrike && legs.shortPutStrike && legs.shortCallStrike && legs.longCallStrike && legs.expiration;
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
          <div style={s.logoIcon}>S</div>
          <span style={s.logoText}>
            Spread<span style={s.logoAccent}>Works</span>
          </span>
        </div>
        <div style={{ ...s.subtitle, marginTop: 2, marginLeft: 36 }}>Options Spread Analyzer</div>
      </div>

      {/* Strategy */}
      <div style={s.card}>
        <div style={s.sectionLabel}>Strategy</div>
        <div style={s.toggleRow}>
          <button
            style={s.toggleBtn(strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL)}
            onClick={() => setStrategy(STRATEGY_TYPES.DOUBLE_DIAGONAL)}
          >Dbl Diagonal</button>
          <button
            style={s.toggleBtn(strategy === STRATEGY_TYPES.DOUBLE_CALENDAR)}
            onClick={() => setStrategy(STRATEGY_TYPES.DOUBLE_CALENDAR)}
          >Dbl Calendar</button>
          <button
            style={s.toggleBtn(strategy === STRATEGY_TYPES.IRON_CONDOR)}
            onClick={() => setStrategy(STRATEGY_TYPES.IRON_CONDOR)}
          >Iron Condor</button>
        </div>
      </div>

      {/* Input Mode */}
      <div style={s.card}>
        <div style={s.sectionLabel}>Input Mode</div>
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 700, fontSize: 12 }}>GEX Suggestion</span>
            <button
              onClick={() => {
                setGexSuggestion(null);
                setLegs(DEFAULT_LEGS[strategy]);
                setInputMode(INPUT_MODES.MANUAL);
              }}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--red)',
                cursor: 'pointer',
                fontSize: 16,
                fontFamily: 'var(--font-ui)',
                padding: '0 2px',
                lineHeight: 1,
              }}
              title="Dismiss suggestion and switch to Manual"
            >&times;</button>
          </div>
          {gexSuggestion.rationale && (
            <div style={{ color: 'var(--text-secondary)', marginTop: 4, fontSize: 11, lineHeight: 1.5 }}>
              {gexSuggestion.rationale}
            </div>
          )}
        </div>
      )}

      {/* Spot Price */}
      <div style={s.spotRow}>
        <span style={s.spotLabel}>Symbol</span>
        <span style={s.spotSymbol}>{symbol}</span>
        <span style={s.spotDot} />
        <span style={s.spotLabel}>Spot</span>
        <span style={s.spotValue}>{spotPrice ? `$${spotPrice.toFixed(2)}` : '--'}</span>
      </div>

      {/* Strike Inputs */}
      <div style={s.card}>
        {strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL ? (
          <>
            <div style={s.sideLabel('var(--green)')}>
              <span>Put Side</span>
              <div style={s.sideLine('var(--green)')} />
            </div>
            <div style={s.fieldRow}>
              <StrikeInput label="Long Put" value={legs.longPutStrike} color="#00e676" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Short Put" value={legs.shortPutStrike} color="#ff5252" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div style={s.sideLabel('var(--red)')}>
              <span>Call Side</span>
              <div style={s.sideLine('var(--red)')} />
            </div>
            <div style={s.fieldRow}>
              <StrikeInput label="Short Call" value={legs.shortCallStrike} color="#ff5252" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Long Call" value={legs.longCallStrike} color="#00e676" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div style={{ ...s.sideLabel('var(--text-tertiary)'), marginTop: 8 }}>
              <span>Expirations</span>
              <div style={s.sideLine('var(--text-tertiary)')} />
            </div>
            <div style={s.fieldRow}>
              <ExpirationInput label="Short Exp" value={legs.shortExpiration} inputMode={inputMode} expirations={expirations} onChange={(v) => updateLeg('shortExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <ExpirationInput label="Long Exp" value={legs.longExpiration} inputMode={inputMode} expirations={expirations} onChange={(v) => updateLeg('longExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
          </>
        ) : strategy === STRATEGY_TYPES.IRON_CONDOR ? (
          <>
            <div style={s.sideLabel('var(--green)')}>
              <span>Put Side</span>
              <div style={s.sideLine('var(--green)')} />
            </div>
            <div style={s.fieldRow}>
              <StrikeInput label="Long Put" value={legs.longPutStrike} color="#00e676" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Short Put" value={legs.shortPutStrike} color="#ff5252" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div style={s.sideLabel('var(--red)')}>
              <span>Call Side</span>
              <div style={s.sideLine('var(--red)')} />
            </div>
            <div style={s.fieldRow}>
              <StrikeInput label="Short Call" value={legs.shortCallStrike} color="#ff5252" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Long Call" value={legs.longCallStrike} color="#00e676" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div style={{ ...s.sideLabel('var(--text-tertiary)'), marginTop: 8 }}>
              <span>Expiration</span>
              <div style={s.sideLine('var(--text-tertiary)')} />
            </div>
            <div style={s.fieldRow}>
              <ExpirationInput label="Expiration" value={legs.expiration} inputMode={inputMode} expirations={expirations} onChange={(v) => updateLeg('expiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
          </>
        ) : (
          <>
            <div style={s.sideLabel('var(--red)')}>
              <span>Put Calendar</span>
              <div style={s.sideLine('var(--red)')} />
            </div>
            <div style={s.fieldRow}>
              <StrikeInput label="Put Strike" value={legs.putStrike} color="#ff5252" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('putStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 4, marginTop: -2 }}>
              Sell @ Front Exp &middot; Buy @ Back Exp
            </div>
            <div style={s.sideLabel('var(--green)')}>
              <span>Call Calendar</span>
              <div style={s.sideLine('var(--green)')} />
            </div>
            <div style={s.fieldRow}>
              <StrikeInput label="Call Strike" value={legs.callStrike} color="#00e676" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('callStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 4, marginTop: -2 }}>
              Sell @ Front Exp &middot; Buy @ Back Exp
            </div>
            <div style={{ ...s.sideLabel('var(--accent)'), marginTop: 8 }}>
              <span>Expirations</span>
              <div style={s.sideLine('var(--accent)')} />
            </div>
            <div style={s.fieldRow}>
              <ExpirationInput label="Front (Sell)" value={legs.frontExpiration} inputMode={inputMode} expirations={expirations} onChange={(v) => updateLeg('frontExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <ExpirationInput label="Back (Buy)" value={legs.backExpiration} inputMode={inputMode} expirations={expirations} onChange={(v) => updateLeg('backExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            {legs.putStrike && legs.callStrike && legs.frontExpiration && legs.backExpiration && (
              <div style={{
                background: 'var(--bg-elevated)',
                borderRadius: 'var(--radius-sm)',
                padding: '8px 10px',
                fontSize: 10,
                color: 'var(--text-secondary)',
                marginTop: 4,
                fontFamily: 'var(--font-mono)',
              }}>
                <div style={{ color: 'var(--text-tertiary)', marginBottom: 4, fontWeight: 600, fontFamily: 'var(--font-ui)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>4 Legs:</div>
                <div>1. Sell Put ${legs.putStrike} ({legs.frontExpiration})</div>
                <div>2. Buy Put ${legs.putStrike} ({legs.backExpiration})</div>
                <div>3. Sell Call ${legs.callStrike} ({legs.frontExpiration})</div>
                <div>4. Buy Call ${legs.callStrike} ({legs.backExpiration})</div>
              </div>
            )}
          </>
        )}

        {/* Contracts */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
          <span style={s.fieldLabel()}>Contracts</span>
          <input
            type="number"
            min={1}
            max={100}
            value={contracts}
            onChange={(e) => setContracts(Math.max(1, parseInt(e.target.value, 10) || 1))}
            style={{ ...s.input(), width: 60 }}
          />
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button
          style={{ ...s.calcBtn, ...((!isFormValid() || calcLoading || loading) ? s.calcBtnDisabled : {}) }}
          onClick={handleCalculate}
          disabled={!isFormValid() || calcLoading || loading}
        >
          {calcLoading || loading ? 'Calculating...' : '\u26A1 Calculate'}
        </button>

        {calcResult && (
          <>
            <button
              style={{
                ...s.actionBtn('var(--green-dim)', 'var(--green)', 'rgba(0, 230, 118, 0.25)'),
                ...(saving ? s.calcBtnDisabled : {}),
              }}
              onClick={handleSavePosition}
              disabled={saving}
            >
              {saving ? 'Saving...' : '\uD83D\uDCBE Save Position'}
            </button>
            <button
              style={{
                ...s.actionBtn('var(--purple-dim)', 'var(--purple)', 'rgba(124, 77, 255, 0.25)'),
                ...(pushing ? s.calcBtnDisabled : {}),
              }}
              onClick={handlePushDiscord}
              disabled={pushing}
            >
              {pushing ? 'Posting...' : '\uD83D\uDCE3 Push to Discord'}
            </button>
          </>
        )}
        {saveMsg && (
          <div style={{
            fontSize: 11,
            color: saveMsg === 'Saved!' ? 'var(--green)' : 'var(--red)',
            textAlign: 'center',
            fontWeight: 500,
          }}>
            {saveMsg}
          </div>
        )}
        {pushMsg && (
          <div style={{
            fontSize: 11,
            color: pushMsg === 'Posted!' ? 'var(--purple)' : 'var(--red)',
            textAlign: 'center',
            fontWeight: 500,
          }}>
            {pushMsg}
          </div>
        )}
      </div>

      {/* Price Alerts */}
      <div style={s.card}>
        <div style={s.sectionLabel}>Price Alerts</div>
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
                <span style={{ color: 'var(--text-secondary)' }}>{a.condition} ${a.price}{a.triggered ? ' \u26A1' : ''}</span>
                <button style={s.alertDel} onClick={() => handleDeleteAlert(a.id)}>&times;</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
