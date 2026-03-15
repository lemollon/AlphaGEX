import { useState } from 'react';
import { formatCurrency, formatPct, formatGreek, formatGreekDollar } from '../utils/format';

const currFmt = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
  minimumFractionDigits: 0,
});

const GREEK_TOOLTIPS = {
  delta: 'How much the position value changes per $1 move in the underlying',
  gamma: 'Rate of change of delta \u2014 how fast your directional risk shifts',
  theta: 'Daily time decay \u2014 positive means you earn from time passing',
  vega: 'Sensitivity to a 1% change in implied volatility',
};

function GreekCell({ label, symbol, value, color, tooltip }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      className={`flex-1 flex flex-col gap-1 px-3.5 py-2.5 rounded-lg border transition-all duration-150 relative cursor-default backdrop-blur-sm ${
        hovered ? 'border-accent/20 bg-bg-card-hover' : 'border-border-subtle/40 bg-bg-card/60'
      }`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span className="sw-label">{symbol} {label}</span>
      <span className="font-semibold text-sm font-[var(--font-mono)]" style={{ color: color || 'var(--color-text-primary)' }}>{value}</span>
      {hovered && tooltip && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 rounded-lg text-[11px] leading-snug text-text-secondary whitespace-nowrap z-10 pointer-events-none animate-fade-in backdrop-blur-xl"
          style={{ background: 'rgba(16, 16, 42, 0.95)', border: '1px solid var(--color-border-default)', boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6)' }}>
          {tooltip}
        </div>
      )}
    </div>
  );
}

function deltaColor(val) {
  if (val == null) return 'var(--color-text-tertiary)';
  if (Math.abs(val) < 0.05) return 'var(--color-text-secondary)';
  return val > 0 ? 'var(--color-sw-green)' : 'var(--color-sw-red)';
}

function thetaColor(val) {
  if (val == null) return 'var(--color-text-tertiary)';
  return val >= 0 ? 'var(--color-sw-green)' : 'var(--color-sw-red)';
}

function getInitialUnit() {
  try { return localStorage.getItem('sw_metrics_unit') || 'dollar'; } catch { return 'dollar'; }
}

export default function MetricsBar({ calcResult }) {
  const [unit, setUnit] = useState(getInitialUnit);
  const [hoveredIdx, setHoveredIdx] = useState(-1);
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
  const creditColor = isCredit ? 'var(--color-sw-green)' : 'var(--color-sw-red)';
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
  const iv = r.implied_vol != null ? formatPct(r.implied_vol) : '--';

  const cellCls = (idx) => `flex-1 flex flex-col gap-1 px-3.5 py-2.5 rounded-lg border transition-all duration-150 backdrop-blur-sm ${
    hoveredIdx === idx ? 'border-accent/20 bg-bg-card-hover' : 'border-border-subtle/40 bg-bg-card/60'
  }`;

  return (
    <div>
      {/* Row 1: P&L Metrics */}
      <div className="flex gap-0.5 px-2.5 py-1.5 border-t border-border-subtle font-[var(--font-ui)] text-xs"
        style={{ background: 'linear-gradient(180deg, rgba(10, 10, 26, 0.95) 0%, rgba(8, 8, 24, 0.95) 100%)' }}>
        <div className={cellCls(0)} onMouseEnter={() => setHoveredIdx(0)} onMouseLeave={() => setHoveredIdx(-1)}>
          <div className="flex items-center gap-1.5">
            <span className="sw-label">{creditLabel}</span>
            <button className={`px-1.5 py-0.5 rounded text-[10px] font-semibold font-[var(--font-mono)] transition-all duration-150 border cursor-pointer ${
              !isPct ? 'border-accent bg-accent/20 text-accent-bright' : 'border-border-subtle/60 bg-transparent text-text-muted'
            }`} onClick={toggleUnit}>$</button>
            <button className={`px-1.5 py-0.5 rounded text-[10px] font-semibold font-[var(--font-mono)] transition-all duration-150 border cursor-pointer ${
              isPct ? 'border-accent bg-accent/20 text-accent-bright' : 'border-border-subtle/60 bg-transparent text-text-muted'
            }`} onClick={toggleUnit}>%</button>
          </div>
          <span className="font-bold text-[15px] font-[var(--font-mono)]" style={{ color: creditColor, textShadow: `0 0 12px ${creditColor}33` }}>{creditVal}</span>
        </div>
        <div className={cellCls(1)} onMouseEnter={() => setHoveredIdx(1)} onMouseLeave={() => setHoveredIdx(-1)}>
          <span className="sw-label">Max Profit</span>
          <span className="font-bold text-[15px] font-[var(--font-mono)] text-sw-green" style={{ textShadow: '0 0 12px rgba(34,197,94,0.3)' }}>{maxProfitStr}</span>
        </div>
        <div className={cellCls(2)} onMouseEnter={() => setHoveredIdx(2)} onMouseLeave={() => setHoveredIdx(-1)}>
          <span className="sw-label">Max Loss</span>
          <span className="font-bold text-[15px] font-[var(--font-mono)] text-sw-red" style={{ textShadow: '0 0 12px rgba(239,68,68,0.3)' }}>{maxLossStr}</span>
        </div>
        <div className={cellCls(3)} onMouseEnter={() => setHoveredIdx(3)} onMouseLeave={() => setHoveredIdx(-1)}>
          <span className="sw-label">Chance of Profit</span>
          <span className="font-bold text-[15px] font-[var(--font-mono)] text-accent-bright" style={{ textShadow: '0 0 12px rgba(245,158,11,0.3)' }}>{cop}</span>
        </div>
        <div className={cellCls(4)} onMouseEnter={() => setHoveredIdx(4)} onMouseLeave={() => setHoveredIdx(-1)}>
          <span className="sw-label">Breakevens</span>
          <span className="font-bold text-[15px] font-[var(--font-mono)] text-text-primary">${beLower} &mdash; ${beUpper}</span>
        </div>
        <div className={cellCls(5)} onMouseEnter={() => setHoveredIdx(5)} onMouseLeave={() => setHoveredIdx(-1)}>
          <span className="sw-label">Implied Vol</span>
          <span className="font-bold text-[15px] font-[var(--font-mono)] text-text-primary">{iv}</span>
        </div>
      </div>
      {/* Row 2: Greeks */}
      <div className="flex gap-0.5 px-2.5 py-1.5 font-[var(--font-ui)] text-xs"
        style={{ background: 'linear-gradient(180deg, rgba(10, 10, 26, 0.95) 0%, rgba(8, 8, 24, 0.95) 100%)' }}>
        <GreekCell label="Delta" symbol={'\u0394'} value={formatGreek(g.delta)} color={deltaColor(g.delta)} tooltip={GREEK_TOOLTIPS.delta} />
        <GreekCell label="Gamma" symbol={'\u0393'} value={formatGreek(g.gamma, 5)} color="var(--color-text-secondary)" tooltip={GREEK_TOOLTIPS.gamma} />
        <GreekCell label="Theta" symbol={'\u0398'} value={g.theta != null ? `${formatGreekDollar(g.theta)}/day` : '--'} color={thetaColor(g.theta)} tooltip={GREEK_TOOLTIPS.theta} />
        <GreekCell label="Vega" symbol={'\u03BD'} value={formatGreekDollar(g.vega)} color="var(--color-text-secondary)" tooltip={GREEK_TOOLTIPS.vega} />
        <div className="flex-[2] opacity-0" />
      </div>
    </div>
  );
}
