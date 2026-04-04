import { useState, useEffect, useCallback, useRef } from 'react';
import { Zap, Save, Send, Bell, Plus, X, Sparkles, AlertTriangle, Calendar } from 'lucide-react';

const STRATEGY_TYPES = {
  DOUBLE_DIAGONAL: 'double_diagonal',
  DOUBLE_CALENDAR: 'double_calendar',
  IRON_CONDOR: 'iron_condor',
  BUTTERFLY: 'butterfly',
  IRON_BUTTERFLY: 'iron_butterfly',
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
  [STRATEGY_TYPES.BUTTERFLY]: {
    lowerStrike: '',
    middleStrike: '',
    upperStrike: '',
    optionType: 'call',
    expiration: '',
  },
  [STRATEGY_TYPES.IRON_BUTTERFLY]: {
    longPutStrike: '',
    shortStrike: '',
    longCallStrike: '',
    expiration: '',
  },
};

import { API_URL } from '../lib/api';

function StrikeInput({ label, value, color, inputMode, chainStrikes, chainOptions, onChange, disabled }) {
  const isGreen = color === '#00e676' || color === '#22c55e';
  const borderCls = isGreen ? 'border-sw-green/25 focus:border-sw-green' : 'border-sw-red/25 focus:border-sw-red';
  const labelCls = isGreen ? 'text-sw-green' : 'text-sw-red';
  const optionType = label.toLowerCase().includes('put') ? 'put' : 'call';

  if (inputMode === INPUT_MODES.LIVE_CHAIN && chainStrikes.length > 0) {
    return (
      <div className="flex-1 flex flex-col gap-1">
        <span className={`sw-label ${labelCls}`}>{label}</span>
        <select
          className={`sw-select ${borderCls}`}
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
    <div className="flex-1 flex flex-col gap-1">
      <span className={`sw-label ${labelCls}`}>{label}</span>
      <input
        type="text"
        inputMode="numeric"
        pattern="[0-9.]*"
        placeholder={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={`sw-input ${borderCls}`}
      />
    </div>
  );
}

function ExpirationInput({ label, value, inputMode, expirations, expirationsWithDte, onChange, onFetchStrikes, disabled }) {
  if (inputMode === INPUT_MODES.LIVE_CHAIN && expirations.length > 0) {
    // Build a DTE lookup map from annotated data
    const dteMap = {};
    if (expirationsWithDte) {
      for (const item of expirationsWithDte) {
        dteMap[item.date] = item.dte;
      }
    }
    return (
      <div className="flex-1 flex flex-col gap-1">
        <span className="sw-label">{label}</span>
        <select
          className="sw-select"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            if (onFetchStrikes) onFetchStrikes(e.target.value);
          }}
        >
          <option value="">--</option>
          {expirations.map((exp) => {
            const dte = dteMap[exp];
            const dteLabel = dte === 0 ? '0DTE' : dte != null ? `${dte}DTE` : '';
            return (
              <option key={exp} value={exp}>
                {exp}{dteLabel ? ` (${dteLabel})` : ''}
              </option>
            );
          })}
        </select>
      </div>
    );
  }
  return (
    <div className="flex-1 flex flex-col gap-1">
      <span className="sw-label">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="sw-input"
      />
    </div>
  );
}

/** Return YYYY-MM-DD for today + dte trading days (skips weekends). */
function dteToDate(dte) {
  const d = new Date();
  // Use CT date
  const ct = new Date(d.toLocaleString('en-US', { timeZone: 'America/Chicago' }));
  let remaining = dte;
  const result = new Date(ct.getFullYear(), ct.getMonth(), ct.getDate());
  while (remaining > 0) {
    result.setDate(result.getDate() + 1);
    const day = result.getDay();
    if (day !== 0 && day !== 6) remaining--;
  }
  return result.toISOString().split('T')[0];
}

const DTE_OPTIONS = [0, 1, 2, 3, 4, 5, 14, 30];

function DteQuickButtons({ onSelect }) {
  return (
    <div className="flex flex-wrap gap-1 mt-1.5 mb-1">
      <span className="text-text-muted text-[10px] font-semibold mr-1 flex items-center gap-1">
        <Calendar size={10} />DTE
      </span>
      {DTE_OPTIONS.map((dte) => (
        <button
          key={dte}
          type="button"
          onClick={() => onSelect(dte)}
          className="px-2 py-0.5 text-[10px] font-semibold rounded-md border border-border-subtle text-text-secondary hover:text-accent hover:border-accent/40 hover:bg-accent/5 transition-all duration-150"
        >
          {dte}
        </button>
      ))}
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
  apiError,
  onManualSpotChange,
}) {
  const [strategy, setStrategy] = useState(STRATEGY_TYPES.DOUBLE_DIAGONAL);
  const [inputMode, setInputMode] = useState(INPUT_MODES.MANUAL);
  const [legs, setLegs] = useState(DEFAULT_LEGS[STRATEGY_TYPES.DOUBLE_DIAGONAL]);
  const [contracts, setContracts] = useState(1);
  const [expirations, setExpirations] = useState([]);
  const [expirationsWithDte, setExpirationsWithDte] = useState([]);
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
      } else if (strategy === STRATEGY_TYPES.BUTTERFLY) {
        long_put = parseFloat(legs.lowerStrike) || 0;
        short_put = parseFloat(legs.middleStrike) || 0;
        short_call = parseFloat(legs.middleStrike) || 0;
        long_call = parseFloat(legs.upperStrike) || 0;
        short_exp = legs.expiration;
        long_exp = null;
      } else if (strategy === STRATEGY_TYPES.IRON_BUTTERFLY) {
        long_put = parseFloat(legs.longPutStrike) || 0;
        short_put = parseFloat(legs.shortStrike) || 0;
        short_call = parseFloat(legs.shortStrike) || 0;
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
      } else if (strategy === STRATEGY_TYPES.BUTTERFLY) {
        legPayload = {
          long_put: parseFloat(legs.lowerStrike) || 0,
          short_put: parseFloat(legs.middleStrike) || 0,
          short_call: parseFloat(legs.middleStrike) || 0,
          long_call: parseFloat(legs.upperStrike) || 0,
        };
        shortExp = legs.expiration;
        longExp = null;
      } else if (strategy === STRATEGY_TYPES.IRON_BUTTERFLY) {
        legPayload = {
          long_put: parseFloat(legs.longPutStrike) || 0,
          short_put: parseFloat(legs.shortStrike) || 0,
          short_call: parseFloat(legs.shortStrike) || 0,
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
        [STRATEGY_TYPES.BUTTERFLY]: 'Butterfly',
        [STRATEGY_TYPES.IRON_BUTTERFLY]: 'Iron Butterfly',
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
        setExpirationsWithDte(data.expirations_with_dte || []);
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
      } else if (strategy === STRATEGY_TYPES.BUTTERFLY && data.legs) {
        setLegs({
          lowerStrike: data.legs.lower_strike ?? '',
          middleStrike: data.legs.middle_strike ?? '',
          upperStrike: data.legs.upper_strike ?? '',
          optionType: data.legs.option_type ?? 'call',
          expiration: data.legs.expiration ?? '',
        });
      } else if (strategy === STRATEGY_TYPES.IRON_BUTTERFLY && data.legs) {
        setLegs({
          longPutStrike: data.legs.long_put_strike ?? '',
          shortStrike: data.legs.short_strike ?? '',
          longCallStrike: data.legs.long_call_strike ?? '',
          expiration: data.legs.expiration ?? '',
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

  const handleDteSelect = (dte) => {
    const expDate = dteToDate(dte);
    if (strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL) {
      const longDate = dteToDate(dte + 7);
      setLegs((prev) => ({ ...prev, shortExpiration: expDate, longExpiration: longDate }));
    } else if (strategy === STRATEGY_TYPES.DOUBLE_CALENDAR) {
      const backDate = dteToDate(dte + 7);
      setLegs((prev) => ({ ...prev, frontExpiration: expDate, backExpiration: backDate }));
    } else if (strategy === STRATEGY_TYPES.IRON_CONDOR || strategy === STRATEGY_TYPES.BUTTERFLY || strategy === STRATEGY_TYPES.IRON_BUTTERFLY) {
      setLegs((prev) => ({ ...prev, expiration: expDate }));
    }
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
    if (strategy === STRATEGY_TYPES.BUTTERFLY) {
      return legs.lowerStrike && legs.middleStrike && legs.upperStrike && legs.expiration;
    }
    if (strategy === STRATEGY_TYPES.IRON_BUTTERFLY) {
      return legs.longPutStrike && legs.shortStrike && legs.longCallStrike && legs.expiration;
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
    <div className="w-[300px] min-w-[300px] border-r border-border-subtle px-4 py-5 overflow-y-auto font-[var(--font-ui)] text-[13px] text-text-primary flex flex-col gap-3.5 h-full"
      style={{ background: 'linear-gradient(180deg, #0c0c22 0%, #080818 100%)', boxShadow: 'var(--shadow-panel)' }}>

      {/* Strategy */}
      <div className="sw-card p-3.5">
        <div className="sw-label mb-2.5">Strategy</div>
        <div className="sw-toggle-group flex-wrap">
          <button className={`sw-toggle-btn ${strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL ? 'active' : ''}`}
            onClick={() => setStrategy(STRATEGY_TYPES.DOUBLE_DIAGONAL)}>Dbl Diagonal</button>
          <button className={`sw-toggle-btn ${strategy === STRATEGY_TYPES.DOUBLE_CALENDAR ? 'active' : ''}`}
            onClick={() => setStrategy(STRATEGY_TYPES.DOUBLE_CALENDAR)}>Dbl Calendar</button>
          <button className={`sw-toggle-btn ${strategy === STRATEGY_TYPES.IRON_CONDOR ? 'active' : ''}`}
            onClick={() => setStrategy(STRATEGY_TYPES.IRON_CONDOR)}>Iron Condor</button>
          <button className={`sw-toggle-btn ${strategy === STRATEGY_TYPES.BUTTERFLY ? 'active' : ''}`}
            onClick={() => setStrategy(STRATEGY_TYPES.BUTTERFLY)}>Butterfly</button>
          <button className={`sw-toggle-btn ${strategy === STRATEGY_TYPES.IRON_BUTTERFLY ? 'active' : ''}`}
            onClick={() => setStrategy(STRATEGY_TYPES.IRON_BUTTERFLY)}>Iron Fly</button>
        </div>
      </div>

      {/* Input Mode */}
      <div className="sw-card p-3.5">
        <div className="sw-label mb-2.5">Input Mode</div>
        <div className="sw-toggle-group">
          <button className={`sw-toggle-btn ${inputMode === INPUT_MODES.LIVE_CHAIN ? 'active' : ''}`}
            onClick={() => setInputMode(INPUT_MODES.LIVE_CHAIN)}>Live Chain</button>
          <button className={`sw-toggle-btn ${inputMode === INPUT_MODES.MANUAL ? 'active' : ''}`}
            onClick={() => setInputMode(INPUT_MODES.MANUAL)}>Manual</button>
          <button className={`sw-toggle-btn ${inputMode === INPUT_MODES.GEX_SUGGEST ? 'active' : ''}`}
            onClick={() => setInputMode(INPUT_MODES.GEX_SUGGEST)}>GEX Suggest</button>
        </div>
      </div>

      {/* Error */}
      {(error || calcError) && (
        <div className="flex items-center gap-2 bg-sw-red-dim border border-sw-red/30 rounded-lg px-3 py-2 text-[11px] text-sw-red font-medium animate-fade-in">
          <AlertTriangle size={14} className="shrink-0" />
          {error || calcError}
        </div>
      )}

      {/* GEX Suggestion */}
      {inputMode === INPUT_MODES.GEX_SUGGEST && gexSuggestion && (
        <div className="bg-accent-dim border border-accent/20 rounded-lg px-3 py-2.5 text-[11px] text-accent animate-fade-in">
          <div className="flex justify-between items-center">
            <span className="font-bold text-xs flex items-center gap-1.5">
              <Sparkles size={12} />
              GEX Suggestion
            </span>
            <button
              onClick={() => {
                setGexSuggestion(null);
                setLegs(DEFAULT_LEGS[strategy]);
                setInputMode(INPUT_MODES.MANUAL);
              }}
              className="sw-btn-ghost p-0 text-sw-red hover:text-sw-red text-base leading-none"
              title="Dismiss suggestion and switch to Manual"
            ><X size={14} /></button>
          </div>
          {gexSuggestion.rationale && (
            <div className="text-text-secondary mt-1 text-[11px] leading-relaxed">
              {gexSuggestion.rationale}
            </div>
          )}
        </div>
      )}

      {/* Spot Price */}
      <div className="flex items-center gap-2.5 px-3.5 py-3 rounded-xl border border-border-subtle"
        style={{ background: 'linear-gradient(135deg, rgba(16, 16, 42, 0.8) 0%, rgba(13, 13, 35, 0.6) 100%)', boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)' }}>
        <span className="text-text-tertiary text-[11px] font-semibold">Symbol</span>
        <span className="text-white font-extrabold text-[15px] font-[var(--font-mono)]">{symbol}</span>
        <span className="w-1 h-1 rounded-full bg-border-default" />
        <span className="text-text-tertiary text-[11px] font-semibold">Spot</span>
        {spotPrice ? (
          <span className="text-accent-bright font-bold text-[15px] font-[var(--font-mono)]" style={{ textShadow: '0 0 20px rgba(68, 138, 255, 0.3)' }}>
            ${spotPrice.toFixed(2)}
          </span>
        ) : (
          <input
            type="number"
            step="0.01"
            placeholder="Enter spot"
            className="sw-input w-[90px] text-center text-accent-bright font-bold text-[13px]"
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              if (onManualSpotChange && !isNaN(val) && val > 0) onManualSpotChange(val);
            }}
          />
        )}
      </div>
      {apiError && (
        <div className="px-3 py-2 rounded-lg border border-sw-red/20 bg-sw-red-dim text-[11px] text-sw-red font-medium">
          API offline — enter spot price manually to calculate spreads
        </div>
      )}

      {/* Strike Inputs */}
      <div className="sw-card p-3.5">
        {strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL ? (
          <>
            <div className="sw-section-divider text-sw-green">
              <span>Put Side</span>
              <div className="line bg-sw-green/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Long Put" value={legs.longPutStrike} color="#22c55e" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Short Put" value={legs.shortPutStrike} color="#ef4444" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="sw-section-divider text-sw-red">
              <span>Call Side</span>
              <div className="line bg-sw-red/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Short Call" value={legs.shortCallStrike} color="#ef4444" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Long Call" value={legs.longCallStrike} color="#22c55e" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="sw-section-divider text-text-tertiary mt-2">
              <span>Expirations</span>
              <div className="line bg-text-tertiary/20" />
            </div>
            <DteQuickButtons onSelect={handleDteSelect} />
            <div className="flex gap-2 mb-1.5">
              <ExpirationInput label="Short Exp" value={legs.shortExpiration} inputMode={inputMode} expirations={expirations} expirationsWithDte={expirationsWithDte} onChange={(v) => updateLeg('shortExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <ExpirationInput label="Long Exp" value={legs.longExpiration} inputMode={inputMode} expirations={expirations} expirationsWithDte={expirationsWithDte} onChange={(v) => updateLeg('longExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
          </>
        ) : strategy === STRATEGY_TYPES.BUTTERFLY ? (
          <>
            <div className="sw-section-divider text-accent">
              <span>Butterfly Strikes</span>
              <div className="line bg-accent/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Lower (Buy)" value={legs.lowerStrike} color="#22c55e" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('lowerStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Middle (Sell 2x)" value={legs.middleStrike} color="#ef4444" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('middleStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Upper (Buy)" value={legs.upperStrike} color="#22c55e" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('upperStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="sw-section-divider text-text-tertiary mt-2">
              <span>Type &amp; Expiration</span>
              <div className="line bg-text-tertiary/20" />
            </div>
            <DteQuickButtons onSelect={handleDteSelect} />
            <div className="flex gap-2 mb-1.5">
              <div className="flex-1 flex flex-col gap-1">
                <span className="sw-label">Option Type</span>
                <select className="sw-select" value={legs.optionType} onChange={(e) => updateLeg('optionType', e.target.value)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST}>
                  <option value="call">Calls</option>
                  <option value="put">Puts</option>
                </select>
              </div>
              <ExpirationInput label="Expiration" value={legs.expiration} inputMode={inputMode} expirations={expirations} expirationsWithDte={expirationsWithDte} onChange={(v) => updateLeg('expiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
          </>
        ) : strategy === STRATEGY_TYPES.IRON_BUTTERFLY ? (
          <>
            <div className="sw-section-divider text-sw-green">
              <span>Wings (Buy)</span>
              <div className="line bg-sw-green/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Long Put" value={legs.longPutStrike} color="#22c55e" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Long Call" value={legs.longCallStrike} color="#22c55e" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="sw-section-divider text-sw-red">
              <span>Body ATM (Sell)</span>
              <div className="line bg-sw-red/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Short Strike (ATM)" value={legs.shortStrike} color="#ef4444" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="text-[10px] text-text-tertiary mb-1 -mt-0.5">
              Sell 1 Put + 1 Call at same strike (ATM)
            </div>
            <div className="sw-section-divider text-text-tertiary mt-2">
              <span>Expiration</span>
              <div className="line bg-text-tertiary/20" />
            </div>
            <DteQuickButtons onSelect={handleDteSelect} />
            <div className="flex gap-2 mb-1.5">
              <ExpirationInput label="Expiration" value={legs.expiration} inputMode={inputMode} expirations={expirations} expirationsWithDte={expirationsWithDte} onChange={(v) => updateLeg('expiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
          </>
        ) : strategy === STRATEGY_TYPES.IRON_CONDOR ? (
          <>
            <div className="sw-section-divider text-sw-green">
              <span>Put Side</span>
              <div className="line bg-sw-green/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Long Put" value={legs.longPutStrike} color="#22c55e" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Short Put" value={legs.shortPutStrike} color="#ef4444" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="sw-section-divider text-sw-red">
              <span>Call Side</span>
              <div className="line bg-sw-red/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Short Call" value={legs.shortCallStrike} color="#ef4444" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Long Call" value={legs.longCallStrike} color="#22c55e" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="sw-section-divider text-text-tertiary mt-2">
              <span>Expiration</span>
              <div className="line bg-text-tertiary/20" />
            </div>
            <DteQuickButtons onSelect={handleDteSelect} />
            <div className="flex gap-2 mb-1.5">
              <ExpirationInput label="Expiration" value={legs.expiration} inputMode={inputMode} expirations={expirations} expirationsWithDte={expirationsWithDte} onChange={(v) => updateLeg('expiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
          </>
        ) : (
          <>
            <div className="sw-section-divider text-sw-red">
              <span>Put Calendar</span>
              <div className="line bg-sw-red/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Put Strike" value={legs.putStrike} color="#ef4444" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('putStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="text-[10px] text-text-tertiary mb-1 -mt-0.5">
              Sell @ Front Exp &middot; Buy @ Back Exp
            </div>
            <div className="sw-section-divider text-sw-green">
              <span>Call Calendar</span>
              <div className="line bg-sw-green/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Call Strike" value={legs.callStrike} color="#22c55e" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('callStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="text-[10px] text-text-tertiary mb-1 -mt-0.5">
              Sell @ Front Exp &middot; Buy @ Back Exp
            </div>
            <div className="sw-section-divider text-accent mt-2">
              <span>Expirations</span>
              <div className="line bg-accent/15" />
            </div>
            <DteQuickButtons onSelect={handleDteSelect} />
            <div className="flex gap-2 mb-1.5">
              <ExpirationInput label="Front (Sell)" value={legs.frontExpiration} inputMode={inputMode} expirations={expirations} expirationsWithDte={expirationsWithDte} onChange={(v) => updateLeg('frontExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <ExpirationInput label="Back (Buy)" value={legs.backExpiration} inputMode={inputMode} expirations={expirations} expirationsWithDte={expirationsWithDte} onChange={(v) => updateLeg('backExpiration', v)} onFetchStrikes={fetchStrikes} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            {legs.putStrike && legs.callStrike && legs.frontExpiration && legs.backExpiration && (
              <div className="bg-bg-elevated rounded-md px-2.5 py-2 text-[10px] text-text-secondary mt-1 font-[var(--font-mono)]">
                <div className="text-text-tertiary mb-1 font-semibold font-[var(--font-ui)] uppercase tracking-wider">4 Legs:</div>
                <div>1. Sell Put ${legs.putStrike} ({legs.frontExpiration})</div>
                <div>2. Buy Put ${legs.putStrike} ({legs.backExpiration})</div>
                <div>3. Sell Call ${legs.callStrike} ({legs.frontExpiration})</div>
                <div>4. Buy Call ${legs.callStrike} ({legs.backExpiration})</div>
              </div>
            )}
          </>
        )}

        {/* Contracts */}
        <div className="flex items-center gap-2.5 mt-2">
          <span className="sw-label">Contracts</span>
          <input
            type="number"
            min={1}
            max={100}
            value={contracts}
            onChange={(e) => setContracts(Math.max(1, parseInt(e.target.value, 10) || 1))}
            className="sw-input w-[60px]"
          />
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col gap-1.5">
        <button
          className="sw-btn-primary w-full flex items-center justify-center gap-2"
          onClick={handleCalculate}
          disabled={!isFormValid() || calcLoading || loading}
        >
          <Zap size={14} />
          {calcLoading || loading ? 'Calculating...' : 'Calculate'}
        </button>

        {calcResult && (
          <>
            <button
              className="sw-btn-secondary w-full flex items-center justify-center gap-2 !border-sw-green/25 !text-sw-green hover:!bg-sw-green-dim"
              onClick={handleSavePosition}
              disabled={saving}
              style={saving ? { opacity: 0.35 } : {}}
            >
              <Save size={14} />
              {saving ? 'Saving...' : 'Save Position'}
            </button>
            <button
              className="sw-btn-secondary w-full flex items-center justify-center gap-2 !border-sw-purple/25 !text-sw-purple hover:!bg-sw-purple-dim"
              onClick={handlePushDiscord}
              disabled={pushing}
              style={pushing ? { opacity: 0.35 } : {}}
            >
              <Send size={14} />
              {pushing ? 'Posting...' : 'Push to Discord'}
            </button>
          </>
        )}
        {saveMsg && (
          <div className={`text-[11px] text-center font-medium ${saveMsg === 'Saved!' ? 'text-sw-green' : 'text-sw-red'}`}>
            {saveMsg}
          </div>
        )}
        {pushMsg && (
          <div className={`text-[11px] text-center font-medium ${pushMsg === 'Posted!' ? 'text-sw-purple' : 'text-sw-red'}`}>
            {pushMsg}
          </div>
        )}
      </div>

      {/* Price Alerts */}
      <div className="sw-card p-3.5">
        <div className="sw-label mb-2.5 flex items-center gap-1.5">
          <Bell size={12} />
          Price Alerts
        </div>
        <form onSubmit={handleAddAlert}>
          <div className="flex gap-1.5 mt-1.5">
            <select className="sw-select !w-[68px] !text-xs" value={alertCondition} onChange={(e) => setAlertCondition(e.target.value)}>
              <option value="above">Above</option>
              <option value="below">Below</option>
            </select>
            <input
              type="number"
              step="0.01"
              placeholder="Price"
              value={alertPrice}
              onChange={(e) => setAlertPrice(e.target.value)}
              className="sw-input !text-xs flex-1 min-w-0"
            />
            <button type="submit" disabled={alertCreating || !alertPrice}
              className="sw-btn-primary !px-3 !py-1.5 text-xs flex items-center gap-1">
              <Plus size={12} />Add
            </button>
          </div>
        </form>
        {alerts && alerts.length > 0 && (
          <ul className="list-none p-0 mt-1.5 space-y-1">
            {alerts.map((a) => (
              <li key={a.id} className="flex items-center justify-between px-2 py-1.5 rounded-md bg-bg-elevated text-xs font-[var(--font-mono)] transition-all duration-150 hover:bg-bg-hover"
                style={{ opacity: a.triggered ? 0.5 : 1 }}>
                <span className="text-text-secondary">{a.condition} ${a.price}{a.triggered ? ' \u26A1' : ''}</span>
                <button className="sw-btn-ghost !p-0 text-text-tertiary hover:text-sw-red text-base leading-none"
                  onClick={() => handleDeleteAlert(a.id)}><X size={14} /></button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
