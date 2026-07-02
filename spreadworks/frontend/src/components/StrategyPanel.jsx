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
  const isGreen = color === '#34d399' || color === '#34d399';
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

/* ── GEX Suggest panel ─────────────────────────────────────────── */

function fmtUsd(v, decimals = 2) {
  if (v == null || Number.isNaN(v)) return '—';
  const abs = Math.abs(v);
  const sign = v < 0 ? '−' : '';
  return `${sign}$${abs.toFixed(decimals)}`;
}

function fmtPct(v, decimals = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(decimals)}%`;
}

function fmtTimestamp(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    }) + ' CT';
  } catch { return ''; }
}

function ContextStrip({ ctx }) {
  if (!ctx) return null;
  const items = [
    { label: 'Spot', value: fmtUsd(ctx.spot), color: '#fff' },
    { label: 'Flip', value: fmtUsd(ctx.flip_point), color: '#cbd5e1' },
    { label: 'Put Wall', value: fmtUsd(ctx.put_wall), color: '#fb7185' },
    { label: 'Call Wall', value: fmtUsd(ctx.call_wall), color: '#34d399' },
    { label: 'VIX', value: ctx.vix != null ? ctx.vix.toFixed(1) : '—', color: '#fcd34d' },
    { label: 'Regime', value: ctx.gamma_regime || '—', color: '#7dd3fc' },
    { label: 'ATM Strad', value: ctx.atm_straddle_mid != null ? fmtUsd(ctx.atm_straddle_mid) : '—', color: '#cbd5e1' },
    { label: 'Δ Flip', value: fmtUsd(ctx.flip_distance), color: ctx.flip_distance < 1.0 ? '#fcd34d' : '#cbd5e1' },
  ];
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(72px,1fr))',
        gap: 6,
        padding: '8px 10px',
        background: 'rgba(7,16,28,0.55)',
        boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08)',
        borderRadius: 6,
        marginBottom: 8,
      }}
    >
      {items.map((it, i) => (
        <div key={i} style={{ minWidth: 0 }}>
          <div style={{
            fontSize: 8.5, fontWeight: 700, color: '#64748b',
            textTransform: 'uppercase', letterSpacing: '0.10em',
            marginBottom: 1,
          }}>{it.label}</div>
          <div style={{
            fontFamily: 'JetBrains Mono', fontSize: 11, fontWeight: 700,
            color: it.color, overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>{it.value}</div>
        </div>
      ))}
    </div>
  );
}

function WarningBanner({ warnings }) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <div
      style={{
        padding: '6px 10px',
        marginBottom: 8,
        borderRadius: 6,
        background: 'rgba(252,211,77,0.08)',
        boxShadow: 'inset 0 0 0 1px rgba(252,211,77,0.25)',
      }}
    >
      {warnings.map((w, i) => (
        <div key={i} style={{
          fontSize: 10.5, color: '#fcd34d', fontWeight: 600,
          lineHeight: 1.5,
        }}>
          ⚠ {w}
        </div>
      ))}
    </div>
  );
}

function VariantCard({ variant, onApply, isActive }) {
  const p = variant.preview;
  const hasMetrics = p && p.max_profit != null && p.max_loss != null;
  const positiveCredit = p && p.credit_estimate != null && p.credit_estimate > 0;
  return (
    <div
      style={{
        padding: '10px 12px',
        borderRadius: 8,
        background: isActive ? 'rgba(125,211,252,0.10)' : 'rgba(7,16,28,0.55)',
        boxShadow: isActive
          ? 'inset 0 0 0 1px rgba(125,211,252,0.35)'
          : 'inset 0 0 0 1px rgba(125,211,252,0.08)',
        marginBottom: 6,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: '#e2e8f0' }}>
          {variant.name}
        </span>
        <button
          onClick={() => onApply(variant)}
          style={{
            padding: '3px 10px', borderRadius: 4, border: 'none',
            fontSize: 10.5, fontWeight: 700, cursor: 'pointer',
            color: isActive ? '#06121f' : '#22d3ee',
            background: isActive ? '#22d3ee' : 'rgba(34,211,238,0.10)',
            boxShadow: isActive ? 'none' : 'inset 0 0 0 1px rgba(34,211,238,0.30)',
          }}
        >
          {isActive ? 'Applied' : 'Use'}
        </button>
      </div>
      <div style={{
        fontSize: 10, color: '#94a3b8', marginBottom: 6, lineHeight: 1.4,
      }}>
        {variant.description}
      </div>
      {hasMetrics ? (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(64px,1fr))', gap: 4,
          fontFamily: 'JetBrains Mono', fontSize: 10,
        }}>
          <Metric label={positiveCredit ? 'Credit' : 'Debit'} value={fmtUsd(Math.abs(p.credit_estimate))} color={positiveCredit ? '#34d399' : '#fcd34d'} />
          <Metric label="Max P" value={fmtUsd(p.max_profit, 0)} color="#34d399" />
          <Metric label="Max L" value={fmtUsd(p.max_loss, 0)} color="#fb7185" />
          <Metric label="POP"   value={fmtPct(p.pop_estimate)} color="#fcd34d" />
        </div>
      ) : p && p.credit_estimate != null ? (
        <div style={{ fontSize: 10, color: '#fb7185', fontStyle: 'italic' }}>
          {positiveCredit ? 'Net credit too small to evaluate' : `Negative credit at these strikes (${fmtUsd(p.credit_estimate)}) — bot would skip`}
        </div>
      ) : (
        <div style={{ fontSize: 10, color: '#64748b', fontStyle: 'italic' }}>
          Pricing unavailable — chain may be missing a leg.
        </div>
      )}
      {p && p.breakevens && (p.breakevens.lower != null || p.breakevens.upper != null) && (
        <div style={{
          fontFamily: 'JetBrains Mono', fontSize: 9.5, color: '#94a3b8',
          marginTop: 4,
        }}>
          BE: {p.breakevens.lower != null ? `$${p.breakevens.lower.toFixed(2)}` : '—'} · {p.breakevens.upper != null ? `$${p.breakevens.upper.toFixed(2)}` : '—'}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, color }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 8.5, fontWeight: 700, color: '#64748b',
        textTransform: 'uppercase', letterSpacing: '0.10em' }}>{label}</div>
      <div style={{ color, fontWeight: 700, overflow: 'hidden',
        textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</div>
    </div>
  );
}

function GexSuggestPanel({ suggestion, loading, onApplyVariant, onRefresh, onDismiss }) {
  const variants = suggestion?.variants || [];
  const context = suggestion?.context;
  const warnings = suggestion?.warnings || [];
  // Track which variant was last applied so the "Use"/"Applied" buttons
  // reflect the active selection. Default to Standard on first render.
  const [appliedName, setAppliedName] = useState(() => {
    const std = variants.find(v => v.name === 'Standard');
    return std?.name || variants[0]?.name || null;
  });
  return (
    <div
      style={{
        padding: 10,
        borderRadius: 8,
        background: 'rgba(13,28,46,0.55)',
        boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.12)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Sparkles size={12} style={{ color: '#22d3ee' }} />
          <span style={{ fontSize: 11, fontWeight: 700, color: '#22d3ee',
            textTransform: 'uppercase', letterSpacing: '0.10em' }}>GEX Suggest</span>
          {loading && <span style={{ fontSize: 9.5, color: '#64748b' }}>refreshing…</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {suggestion?.as_of && (
            <span style={{ fontSize: 9, color: '#64748b', fontFamily: 'JetBrains Mono' }}>
              {fmtTimestamp(suggestion.as_of)}
            </span>
          )}
          <button
            onClick={onRefresh}
            style={{
              fontSize: 9.5, fontWeight: 700, color: '#94a3b8',
              padding: '2px 8px', borderRadius: 4, border: 'none',
              background: 'rgba(255,255,255,0.04)', cursor: 'pointer',
              textTransform: 'uppercase', letterSpacing: '0.10em',
            }}
            title="Re-fetch GEX walls + chain"
          >Refresh</button>
          <button
            onClick={onDismiss}
            style={{
              fontSize: 14, color: '#fb7185',
              padding: '2px 4px', border: 'none', background: 'transparent',
              cursor: 'pointer', lineHeight: 1,
            }}
            title="Dismiss suggestion and switch to Manual"
          >
            <X size={12} />
          </button>
        </div>
      </div>

      <ContextStrip ctx={context} />
      <WarningBanner warnings={warnings} />

      {variants.length === 0 && (
        <div style={{ fontSize: 11, color: '#94a3b8', padding: 8, fontStyle: 'italic' }}>
          No variants available — strike chain may be missing or strategy unsupported.
        </div>
      )}

      {variants.map((v) => (
        <VariantCard
          key={v.name}
          variant={v}
          isActive={appliedName === v.name}
          onApply={(variant) => { setAppliedName(variant.name); onApplyVariant(variant); }}
        />
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
  // Most-recently-clicked DTE quick button. Drives the gex-suggest URL so
  // changing the picker actually changes the suggested strikes/expirations.
  // `null` = use the backend default (next Friday).
  const [selectedDte, setSelectedDte] = useState(null);
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
      setLegs(strategy ? DEFAULT_LEGS[strategy] : {});
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
        const detail = data.detail;
        const msg = typeof detail === 'string' ? detail : JSON.stringify(detail) || 'Failed to save';
        throw new Error(msg);
      }
      setSaveMsg('Saved!');
      setTimeout(() => setSaveMsg(''), 3000);
    } catch (err) {
      setSaveMsg(typeof err?.message === 'string' ? err.message : String(err));
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
      if (!res.ok) {
        const detail = data.detail;
        const msg = typeof detail === 'string' ? detail : JSON.stringify(detail) || 'Failed to post';
        throw new Error(msg);
      }
      setPushMsg('Posted!');
      setTimeout(() => setPushMsg(''), 3000);
    } catch (err) {
      setPushMsg(typeof err?.message === 'string' ? err.message : String(err));
    } finally {
      setPushing(false);
    }
  };

  useEffect(() => {
    // When strategy is cleared (null), wipe everything strategy-shaped so
    // the panel returns to a clean empty state. When a strategy IS picked,
    // hydrate legs from that strategy's defaults.
    setLegs(strategy ? DEFAULT_LEGS[strategy] : {});
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

  // Apply a single variant's legs onto local state — used both by the
  // initial fetch (auto-loads Standard) and by clicking another variant
  // in the GexSuggestPanel.
  const applyVariantLegs = useCallback((variantLegs) => {
    if (!variantLegs) return;
    if (strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL) {
      setLegs({
        longPutStrike: variantLegs.long_put_strike ?? '',
        shortPutStrike: variantLegs.short_put_strike ?? '',
        shortCallStrike: variantLegs.short_call_strike ?? '',
        longCallStrike: variantLegs.long_call_strike ?? '',
        longExpiration: variantLegs.long_expiration ?? '',
        shortExpiration: variantLegs.short_expiration ?? '',
      });
    } else if (strategy === STRATEGY_TYPES.IRON_CONDOR) {
      setLegs({
        longPutStrike: variantLegs.long_put_strike ?? '',
        shortPutStrike: variantLegs.short_put_strike ?? '',
        shortCallStrike: variantLegs.short_call_strike ?? '',
        longCallStrike: variantLegs.long_call_strike ?? '',
        expiration: variantLegs.expiration ?? '',
      });
    } else if (strategy === STRATEGY_TYPES.DOUBLE_CALENDAR) {
      setLegs({
        putStrike: variantLegs.put_strike ?? '',
        callStrike: variantLegs.call_strike ?? '',
        frontExpiration: variantLegs.front_expiration ?? '',
        backExpiration: variantLegs.back_expiration ?? '',
      });
    } else if (strategy === STRATEGY_TYPES.BUTTERFLY) {
      setLegs({
        lowerStrike: variantLegs.lower_strike ?? '',
        middleStrike: variantLegs.middle_strike ?? '',
        upperStrike: variantLegs.upper_strike ?? '',
        optionType: variantLegs.option_type ?? 'call',
        expiration: variantLegs.expiration ?? '',
      });
    } else if (strategy === STRATEGY_TYPES.IRON_BUTTERFLY) {
      setLegs({
        longPutStrike: variantLegs.long_put_strike ?? '',
        shortStrike: variantLegs.short_strike ?? '',
        longCallStrike: variantLegs.long_call_strike ?? '',
        expiration: variantLegs.expiration ?? '',
      });
    }
  }, [strategy]);

  const fetchGexSuggestion = useCallback(async () => {
    if (!strategy) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ symbol, strategy });
      if (selectedDte != null) params.set('dte', String(selectedDte));
      const res = await fetch(`${API_URL}/api/spreadworks/gex-suggest?${params}`);
      if (!res.ok) throw new Error('Failed to fetch GEX suggestion');
      const data = await res.json();
      setGexSuggestion(data);
      // Default-apply the Standard variant so the user gets immediate legs
      // (matches the prior "auto-fill on mode switch" behavior). Falls back
      // to the top-level legs payload if variants[] is missing (very old API).
      const standard = (data.variants || []).find(v => v.name === 'Standard');
      applyVariantLegs(standard?.legs || data.legs);
    } catch (err) {
      setError(`GEX Suggest: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [symbol, strategy, selectedDte, applyVariantLegs]);

  useEffect(() => {
    if (inputMode === INPUT_MODES.GEX_SUGGEST) {
      fetchGexSuggestion();
    }
  }, [inputMode, fetchGexSuggestion]);

  // Auto-refresh every 60s while the user has GEX Suggest open — walls move
  // intraday so a stale suggestion will silently rot otherwise.
  useEffect(() => {
    if (inputMode !== INPUT_MODES.GEX_SUGGEST) return;
    const iv = setInterval(() => { fetchGexSuggestion(); }, 60_000);
    return () => clearInterval(iv);
  }, [inputMode, fetchGexSuggestion]);

  const updateLeg = (field, value) => {
    setLegs((prev) => ({ ...prev, [field]: value }));
  };

  const handleDteSelect = (dte) => {
    // Always remember the pick so GEX Suggest can pass it to the backend
    // and refetch — without this the suggestion stays anchored to "next
    // Friday" no matter which DTE button the user presses.
    setSelectedDte(dte);

    // In Live Chain + GEX Suggest modes we'd be overwriting the API-driven
    // legs.expiration, so let the fetch loop populate dates instead. In
    // Manual mode we set them directly here for the immediate UI feedback.
    if (inputMode !== INPUT_MODES.MANUAL) return;

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
    <div
      className="w-full md:w-[312px] md:min-w-[312px] px-4 py-5 overflow-visible md:overflow-y-auto font-[var(--font-ui)] text-[13px] text-text-primary flex flex-col gap-4 h-auto md:h-full border-b border-white/[0.06] md:border-b-0"
      style={{
        background: 'rgba(13,28,46,0.45)',
        backdropFilter: 'blur(16px) saturate(140%)',
        WebkitBackdropFilter: 'blur(16px) saturate(140%)',
        borderRight: '1px solid rgba(125,211,252,0.08)',
      }}
    >

      {/* Strategy */}
      <div className="sw-sidebar-section">
        <div className="flex items-center justify-between mb-2.5">
          <div className="sw-label">Strategy</div>
          {strategy && (
            <button
              type="button"
              onClick={() => setStrategy(null)}
              className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider transition-colors"
              style={{ color: '#94a3b8' }}
              onMouseEnter={(e) => { e.currentTarget.style.color = '#f1f5f9'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; }}
              title="Clear strategy and start over"
            >
              <X size={11} />
              Clear
            </button>
          )}
        </div>
        <div className="sw-strategy-grid">
          <button className={`sw-strategy-btn ${strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL ? 'active' : ''}`}
            onClick={() => setStrategy(s => s === STRATEGY_TYPES.DOUBLE_DIAGONAL ? null : STRATEGY_TYPES.DOUBLE_DIAGONAL)}>Dbl Diagonal</button>
          <button className={`sw-strategy-btn ${strategy === STRATEGY_TYPES.DOUBLE_CALENDAR ? 'active' : ''}`}
            onClick={() => setStrategy(s => s === STRATEGY_TYPES.DOUBLE_CALENDAR ? null : STRATEGY_TYPES.DOUBLE_CALENDAR)}>Dbl Calendar</button>
          <button className={`sw-strategy-btn ${strategy === STRATEGY_TYPES.IRON_CONDOR ? 'active' : ''}`}
            onClick={() => setStrategy(s => s === STRATEGY_TYPES.IRON_CONDOR ? null : STRATEGY_TYPES.IRON_CONDOR)}>Iron Condor</button>
          <button className={`sw-strategy-btn ${strategy === STRATEGY_TYPES.BUTTERFLY ? 'active' : ''}`}
            onClick={() => setStrategy(s => s === STRATEGY_TYPES.BUTTERFLY ? null : STRATEGY_TYPES.BUTTERFLY)}>Butterfly</button>
          <button className={`sw-strategy-btn ${strategy === STRATEGY_TYPES.IRON_BUTTERFLY ? 'active' : ''} col-span-2`}
            onClick={() => setStrategy(s => s === STRATEGY_TYPES.IRON_BUTTERFLY ? null : STRATEGY_TYPES.IRON_BUTTERFLY)}>Iron Fly</button>
        </div>
        {!strategy && (
          <div
            className="text-[12px] mt-2.5 italic"
            style={{ color: '#64748b' }}
          >
            Pick a strategy to start building.
          </div>
        )}
      </div>

      {/* Input Mode */}
      <div className="sw-sidebar-section">
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

      {/* GEX staleness warning (shown whenever GEX data is flagged stale,
          independent of input mode — helps users notice that the walls the
          chart is drawing may no longer reflect current market structure). */}
      {gexData && (gexData.stale || gexData.error) && (
        <div className="bg-sw-yellow-dim border border-sw-yellow/30 rounded-lg px-3 py-2 text-[11px] text-sw-yellow font-medium flex items-start gap-1.5 animate-fade-in">
          <AlertTriangle size={14} className="shrink-0 mt-[1px]" />
          <div className="leading-relaxed">
            <div className="font-bold">GEX data may be stale</div>
            <div className="text-text-secondary mt-0.5">
              {gexData.stale_reason || gexData.detail || 'Upstream GEX unavailable'}
              {gexData.fetched_at && (
                <span> &middot; last update {new Date(gexData.fetched_at).toLocaleString('en-US', {
                  timeZone: 'America/Chicago',
                  month: 'short',
                  day: 'numeric',
                  hour: 'numeric',
                  minute: '2-digit',
                  hour12: true,
                })} CT</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* GEX Suggest panel — variants + context + warnings */}
      {inputMode === INPUT_MODES.GEX_SUGGEST && gexSuggestion && (
        <GexSuggestPanel
          suggestion={gexSuggestion}
          loading={loading}
          onApplyVariant={(variant) => applyVariantLegs(variant.legs)}
          onRefresh={fetchGexSuggestion}
          onDismiss={() => {
            setGexSuggestion(null);
            setLegs(DEFAULT_LEGS[strategy] || {});
            setInputMode(INPUT_MODES.MANUAL);
          }}
        />
      )}

      {/* Spot Price */}
      <div className="flex items-center gap-2.5 px-3.5 py-3 rounded-md border border-white/5 bg-bg-card">
        <span className="text-text-tertiary text-[11px] font-semibold">Symbol</span>
        <span className="text-white font-bold text-[14px] font-[var(--font-mono)]">{symbol}</span>
        <span className="w-1 h-1 rounded-full bg-border-default" />
        <span className="text-text-tertiary text-[11px] font-semibold">Spot</span>
        {spotPrice ? (
          <span className="text-accent font-bold text-[14px] font-[var(--font-mono)]">
            ${spotPrice.toFixed(2)}
          </span>
        ) : (
          <input
            type="number"
            step="0.01"
            placeholder="Enter spot"
            className="sw-input w-[90px] text-center text-accent font-bold text-[13px]"
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
      <div className="sw-sidebar-section">
        {strategy === STRATEGY_TYPES.DOUBLE_DIAGONAL ? (
          <>
            <div className="sw-section-divider text-sw-green">
              <span>Put Side</span>
              <div className="line bg-sw-green/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Long Put" value={legs.longPutStrike} color="#34d399" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Short Put" value={legs.shortPutStrike} color="#fb7185" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="sw-section-divider text-sw-red">
              <span>Call Side</span>
              <div className="line bg-sw-red/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Short Call" value={legs.shortCallStrike} color="#fb7185" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Long Call" value={legs.longCallStrike} color="#34d399" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
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
              <StrikeInput label="Lower (Buy)" value={legs.lowerStrike} color="#34d399" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('lowerStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Middle (Sell 2x)" value={legs.middleStrike} color="#fb7185" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('middleStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Upper (Buy)" value={legs.upperStrike} color="#34d399" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('upperStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
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
              <StrikeInput label="Long Put" value={legs.longPutStrike} color="#34d399" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Long Call" value={legs.longCallStrike} color="#34d399" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="sw-section-divider text-sw-red">
              <span>Body ATM (Sell)</span>
              <div className="line bg-sw-red/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Short Strike (ATM)" value={legs.shortStrike} color="#fb7185" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
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
              <StrikeInput label="Long Put" value={legs.longPutStrike} color="#34d399" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Short Put" value={legs.shortPutStrike} color="#fb7185" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortPutStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="sw-section-divider text-sw-red">
              <span>Call Side</span>
              <div className="line bg-sw-red/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Short Call" value={legs.shortCallStrike} color="#fb7185" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('shortCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
              <StrikeInput label="Long Call" value={legs.longCallStrike} color="#34d399" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('longCallStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
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
              <StrikeInput label="Put Strike" value={legs.putStrike} color="#fb7185" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('putStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
            </div>
            <div className="text-[10px] text-text-tertiary mb-1 -mt-0.5">
              Sell @ Front Exp &middot; Buy @ Back Exp
            </div>
            <div className="sw-section-divider text-sw-green">
              <span>Call Calendar</span>
              <div className="line bg-sw-green/15" />
            </div>
            <div className="flex gap-2 mb-1.5">
              <StrikeInput label="Call Strike" value={legs.callStrike} color="#34d399" inputMode={inputMode} chainStrikes={chainStrikes} chainOptions={chainOptions} onChange={(v) => updateLeg('callStrike', v)} disabled={inputMode === INPUT_MODES.GEX_SUGGEST} />
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
          className="sw-btn-primary-tall w-full"
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
      <div className="sw-sidebar-section">
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
