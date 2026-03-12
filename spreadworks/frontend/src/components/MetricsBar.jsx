import { useState } from 'react';
import { formatCurrency, formatPct, formatGreek, formatGreekDollar } from '../utils/format';

const currFmt = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
  minimumFractionDigits: 0,
});

const st = {
  bar: {
    display: 'flex',
    background: 'var(--bg-surface)',
    borderTop: '1px solid var(--border-subtle)',
    fontFamily: 'var(--font-ui)',
    fontSize: 12,
  },
  cell: {
    flex: 1,
    padding: '10px 14px',
    borderRight: '1px solid var(--border-subtle)',
    display: 'flex',
    flexDirection: 'column',
    gap: 3,
  },
  label: {
    color: 'var(--text-tertiary)',
    fontSize: 10,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  value: (color) => ({
    color: color || 'var(--text-primary)',
    fontWeight: 700,
    fontSize: 15,
    fontFamily: 'var(--font-mono)',
  }),
  greekValue: (color) => ({
    color: color || 'var(--text-primary)',
    fontWeight: 600,
    fontSize: 14,
    fontFamily: 'var(--font-mono)',
  }),
  tooltip: {
    position: 'absolute',
    bottom: '100%',
    left: '50%',
    transform: 'translateX(-50%)',
    marginBottom: 8,
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    padding: '8px 12px',
    color: 'var(--text-secondary)',
    fontSize: 11,
    lineHeight: 1.4,
    fontFamily: 'var(--font-ui)',
    whiteSpace: 'nowrap',
    zIndex: 10,
    pointerEvents: 'none',
    boxShadow: 'var(--shadow-lg)',
    animation: 'sw-fadeIn 0.15s ease',
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
  if (val == null) return 'var(--text-tertiary)';
  if (Math.abs(val) < 0.05) return 'var(--text-secondary)';
  return val > 0 ? 'var(--green)' : 'var(--red)';
}

function thetaColor(val) {
  if (val == null) return 'var(--text-tertiary)';
  return val >= 0 ? 'var(--green)' : 'var(--red)';
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

  const isCredit = r.net_debit != null && r.net_debit < 0;
  const displayAmount = Math.abs(r.net_debit ?? 0);
  const creditLabel = isCredit ? 'NET CREDIT' : 'NET DEBIT';
  const creditColor = isCredit ? 'var(--green)' : 'var(--red)';
  const isTheoretical = r.pricing_mode === 'black_scholes';
  const tilde = isTheoretical ? '~' : '';

  let creditVal, maxProfitStr, maxLossStr;
  if (isPct && maxRisk && maxRisk > 0) {
    const costPct = displayAmount > 0 ? (displayAmount / maxRisk * 100).toFixed(1) : null;
    creditVal = costPct != null ? `${tilde}${isCredit ? '+' : '-'}${costPct}%` : '--';
    maxProfitStr = r.max_profit != null ? `${tilde}+${(r.max_profit / maxRisk * 100).toFixed(1)}%` : '--';
    maxLossStr = '--100.0%';
  } else {
    creditVal = displayAmount > 0
      ? `${tilde}${isCredit ? '+' : '-'}$${currFmt.format(displayAmount)}`
      : '--';
    maxProfitStr = r.max_profit != null
      ? `${tilde}+$${currFmt.format(Math.round(r.max_profit))}`
      : '--';
    maxLossStr = r.max_loss != null
      ? `${tilde}-$${currFmt.format(Math.abs(Math.round(r.max_loss)))}`
      : '--';
  }

  const cop = r.probability_of_profit != null
    ? formatPct(r.probability_of_profit)
    : r.chance_of_profit != null
      ? formatPct(r.chance_of_profit)
      : '--';

  const beLower = r.lower_breakeven != null ? r.lower_breakeven.toFixed(2) : '--';
  const beUpper = r.upper_breakeven != null ? r.upper_breakeven.toFixed(2) : '--';
  const iv = r.implied_vol != null
    ? formatPct(r.implied_vol)
    : '--';

  const unitBtnStyle = (active) => ({
    padding: '2px 6px',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border-subtle)'}`,
    borderRadius: 3,
    background: active ? 'rgba(68, 138, 255, 0.15)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-muted)',
    cursor: 'pointer',
    fontSize: 10,
    fontFamily: 'var(--font-mono)',
    fontWeight: 600,
    lineHeight: 1,
  });

  return (
    <div>
      {/* Row 1: P&L Metrics */}
      <div style={st.bar}>
        <div style={st.cell}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={st.label}>{creditLabel}</span>
            <button style={unitBtnStyle(!isPct)} onClick={toggleUnit}>$</button>
            <button style={unitBtnStyle(isPct)} onClick={toggleUnit}>%</button>
          </div>
          <span style={st.value(creditColor)}>{creditVal}</span>
        </div>
        <div style={st.cell}>
          <span style={st.label}>Max Profit</span>
          <span style={st.value('var(--green)')}>{maxProfitStr}</span>
        </div>
        <div style={st.cell}>
          <span style={st.label}>Max Loss</span>
          <span style={st.value('var(--red)')}>{maxLossStr}</span>
        </div>
        <div style={st.cell}>
          <span style={st.label}>Chance of Profit</span>
          <span style={st.value('var(--accent)')}>{cop}</span>
        </div>
        <div style={st.cell}>
          <span style={st.label}>Breakevens</span>
          <span style={st.value()}>${beLower} &mdash; ${beUpper}</span>
        </div>
        <div style={{ ...st.cell, borderRight: 'none' }}>
          <span style={st.label}>Implied Vol</span>
          <span style={st.value()}>{iv}</span>
        </div>
      </div>
      {/* Row 2: Greeks */}
      <div style={{ ...st.bar, borderTop: 'none' }}>
        <GreekCell
          label="Delta" symbol={'\u0394'}
          value={formatGreek(g.delta)}
          color={deltaColor(g.delta)}
          tooltip={GREEK_TOOLTIPS.delta}
        />
        <GreekCell
          label="Gamma" symbol={'\u0393'}
          value={formatGreek(g.gamma, 5)}
          color="var(--text-secondary)"
          tooltip={GREEK_TOOLTIPS.gamma}
        />
        <GreekCell
          label="Theta" symbol={'\u0398'}
          value={g.theta != null ? `${formatGreekDollar(g.theta)}/day` : '--'}
          color={thetaColor(g.theta)}
          tooltip={GREEK_TOOLTIPS.theta}
        />
        <GreekCell
          label="Vega" symbol={'\u03BD'}
          value={formatGreekDollar(g.vega)}
          color="var(--text-secondary)"
          tooltip={GREEK_TOOLTIPS.vega}
        />
        <div style={{ ...st.cell, flex: 2, borderRight: 'none' }} />
      </div>
    </div>
  );
}
