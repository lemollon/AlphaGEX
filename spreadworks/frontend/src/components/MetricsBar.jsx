import { useState } from 'react';

const font = "'Courier New', monospace";

const st = {
  bar: {
    display: 'flex',
    background: '#0d0d18',
    borderTop: '1px solid #1a1a2e',
    fontFamily: font,
    fontSize: 11,
  },
  cell: {
    flex: 1,
    padding: '8px 12px',
    borderRight: '1px solid #1a1a2e',
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  label: {
    color: '#555',
    fontSize: 9,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
  value: (color) => ({
    color: color || '#ccc',
    fontWeight: 700,
    fontSize: 14,
  }),
  greekValue: (color) => ({
    color: color || '#ccc',
    fontWeight: 700,
    fontSize: 13,
  }),
  tooltip: {
    position: 'absolute',
    bottom: '100%',
    left: '50%',
    transform: 'translateX(-50%)',
    marginBottom: 6,
    background: '#1a1a2e',
    border: '1px solid #2a2a40',
    borderRadius: 4,
    padding: '6px 10px',
    color: '#aaa',
    fontSize: 10,
    lineHeight: 1.4,
    fontFamily: font,
    whiteSpace: 'nowrap',
    zIndex: 10,
    pointerEvents: 'none',
  },
};

const GREEK_TOOLTIPS = {
  delta: 'How much the position value changes per $1 move in the underlying',
  gamma: 'Rate of change of delta — how fast your directional risk shifts',
  theta: 'Daily time decay — positive means you earn from time passing',
  vega: 'Sensitivity to a 1% change in implied volatility',
};

function GreekCell({ label, symbol, value, color, tooltip }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      style={{ ...st.cell, position: 'relative', cursor: 'default' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span style={st.label}>{symbol} {label}</span>
      <span style={st.greekValue(color)}>{value}</span>
      {hovered && tooltip && <div style={st.tooltip}>{tooltip}</div>}
    </div>
  );
}

function deltaColor(val) {
  if (val == null) return '#555';
  if (Math.abs(val) < 0.05) return '#666';
  return val > 0 ? '#00e676' : '#ff5252';
}

function thetaColor(val) {
  if (val == null) return '#555';
  return val >= 0 ? '#00e676' : '#ff5252';
}

function getInitialUnit() {
  try { return localStorage.getItem('sw_metrics_unit') || 'dollar'; } catch { return 'dollar'; }
}

export default function MetricsBar({ calcResult }) {
  const [unit, setUnit] = useState(getInitialUnit);
  const r = calcResult || {};
  const g = r.greeks || {};
  const isPct = unit === 'pct';

  const toggleUnit = () => {
    const next = isPct ? 'dollar' : 'pct';
    setUnit(next);
    try { localStorage.setItem('sw_metrics_unit', next); } catch { /* noop */ }
  };

  const maxRisk = r.max_loss != null ? Math.abs(r.max_loss) : null;

  // net_debit < 0 means credit strategy (IC); net_debit > 0 means debit strategy (DC, DD)
  const isCredit = r.net_debit != null && r.net_debit < 0;
  const displayAmount = Math.abs(r.net_debit ?? 0);
  const creditLabel = isCredit ? 'NET CREDIT' : 'NET DEBIT';
  const creditColor = isCredit ? '#00e676' : '#ff5252';
  const isTheoretical = r.pricing_mode === 'black_scholes';
  const tilde = isTheoretical ? '~' : '';

  let creditVal, maxProfitStr, maxLossStr;
  if (isPct && maxRisk && maxRisk > 0) {
    const costPct = displayAmount > 0 ? (displayAmount / maxRisk * 100).toFixed(1) : null;
    creditVal = costPct != null ? `${tilde}${isCredit ? '+' : '-'}${costPct}%` : '--';
    maxProfitStr = r.max_profit != null ? `${tilde}+${(r.max_profit / maxRisk * 100).toFixed(1)}%` : '--';
    maxLossStr = '--100.0%';
  } else {
    creditVal = displayAmount > 0 ? `${tilde}${isCredit ? '+' : '-'}$${displayAmount.toFixed(0)}` : '--';
    maxProfitStr = r.max_profit != null ? `${tilde}+$${r.max_profit.toFixed(0)}` : '--';
    maxLossStr = r.max_loss != null ? `${tilde}-$${Math.abs(r.max_loss).toFixed(0)}` : '--';
  }

  const cop = r.probability_of_profit != null
    ? `${(r.probability_of_profit * 100).toFixed(1)}%`
    : r.chance_of_profit != null
      ? `${(r.chance_of_profit * 100).toFixed(1)}%`
      : '--';

  const beLower = r.lower_breakeven?.toFixed(2) ?? '--';
  const beUpper = r.upper_breakeven?.toFixed(2) ?? '--';
  const iv = r.implied_vol != null
    ? `${(r.implied_vol * 100).toFixed(1)}%`
    : '--';

  const fmtGreek = (val, decimals = 4) =>
    val != null ? (val >= 0 ? '+' : '') + val.toFixed(decimals) : '--';

  const unitBtnStyle = (active) => ({
    padding: '1px 5px',
    border: `1px solid ${active ? '#448aff' : '#1a1a2e'}`,
    borderRadius: 2,
    background: active ? '#448aff33' : 'transparent',
    color: active ? '#448aff' : '#444',
    cursor: 'pointer',
    fontSize: 9,
    fontFamily: font,
    fontWeight: 600,
    lineHeight: 1,
  });

  return (
    <div>
      {/* Row 1: P&L Metrics */}
      <div style={st.bar}>
        <div style={st.cell}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={st.label}>{creditLabel}</span>
            <button style={unitBtnStyle(!isPct)} onClick={toggleUnit}>$</button>
            <button style={unitBtnStyle(isPct)} onClick={toggleUnit}>%</button>
          </div>
          <span style={st.value(creditColor)}>{creditVal}</span>
        </div>
        <div style={st.cell}>
          <span style={st.label}>MAX PROFIT</span>
          <span style={st.value('#00e676')}>{maxProfitStr}</span>
        </div>
        <div style={st.cell}>
          <span style={st.label}>MAX LOSS</span>
          <span style={st.value('#ff5252')}>{maxLossStr}</span>
        </div>
        <div style={st.cell}>
          <span style={st.label}>CHANCE OF PROFIT</span>
          <span style={st.value('#448aff')}>{cop}</span>
        </div>
        <div style={st.cell}>
          <span style={st.label}>BREAKEVENS</span>
          <span style={st.value()}>${beLower} &mdash; ${beUpper}</span>
        </div>
        <div style={{ ...st.cell, borderRight: 'none' }}>
          <span style={st.label}>IMPLIED VOL</span>
          <span style={st.value()}>{iv}</span>
        </div>
      </div>
      {/* Row 2: Greeks */}
      <div style={{ ...st.bar, borderTop: 'none' }}>
        <GreekCell
          label="Delta" symbol={'\u0394'}
          value={fmtGreek(g.delta)}
          color={deltaColor(g.delta)}
          tooltip={GREEK_TOOLTIPS.delta}
        />
        <GreekCell
          label="Gamma" symbol={'\u0393'}
          value={fmtGreek(g.gamma, 5)}
          color="#aaa"
          tooltip={GREEK_TOOLTIPS.gamma}
        />
        <GreekCell
          label="Theta" symbol={'\u0398'}
          value={g.theta != null ? `$${(g.theta * 100).toFixed(2)}/day` : '--'}
          color={thetaColor(g.theta)}
          tooltip={GREEK_TOOLTIPS.theta}
        />
        <GreekCell
          label="Vega" symbol={'\u03BD'}
          value={g.vega != null ? `$${(g.vega * 100).toFixed(2)}` : '--'}
          color="#aaa"
          tooltip={GREEK_TOOLTIPS.vega}
        />
        <div style={{ ...st.cell, flex: 2, borderRight: 'none' }} />
      </div>
    </div>
  );
}
