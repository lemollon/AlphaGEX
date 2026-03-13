import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { formatCurrency2, formatPct, formatGreek, formatGreekDollar } from '../utils/format';

export default function LegBreakdown({ calcResult }) {
  const [open, setOpen] = useState(false);
  const legs = calcResult?.legs;

  if (!legs || legs.length === 0) return null;

  const isTheoretical = calcResult?.pricing_mode === 'black_scholes';
  const tilde = isTheoretical ? '~' : '';

  return (
    <div className="border-t border-border-subtle font-[var(--font-ui)] text-xs"
      style={{ background: 'linear-gradient(180deg, rgba(10, 10, 26, 0.95) 0%, rgba(8, 8, 24, 0.95) 100%)' }}>
      <button
        className="sw-btn-ghost w-full text-left px-4 py-2 text-[11px] font-semibold tracking-wider text-text-tertiary hover:text-text-secondary flex items-center gap-1.5"
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        Legs ({legs.length} legs)
      </button>
      {open && (
        <div className="px-3 pb-2.5 animate-fade-in">
          <table className="w-full" style={{ borderCollapse: 'separate', borderSpacing: '0 2px' }}>
            <thead>
              <tr>
                {['Leg', 'Strike', 'Exp', 'Mid', 'IV', '\u0394', '\u0398'].map((h, i) => (
                  <th key={i} className={`sw-label px-2.5 py-2 border-b border-border-subtle/50 ${i === 0 ? 'text-left' : 'text-right'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {legs.map((leg, i) => {
                const isLong = leg.type === 'long';
                const greeks = leg.greeks || {};
                const priceStr = leg.price != null ? `${tilde}${formatCurrency2(leg.price)}` : '--';
                const ivStr = leg.iv != null ? formatPct(leg.iv) : '--';
                const deltaStr = formatGreek(greeks.delta, 3);
                const thetaStr = formatGreekDollar(greeks.theta);
                const rowBg = isLong ? 'bg-sw-green/[0.04]' : 'bg-sw-red/[0.04]';

                return (
                  <tr key={i}>
                    <td className={`px-2.5 py-2 text-left font-semibold font-[var(--font-ui)] border-b border-bg-elevated/50 ${rowBg} ${isLong ? 'text-sw-green' : 'text-sw-red'}`}>{leg.leg}</td>
                    <td className={`px-2.5 py-2 text-right font-[var(--font-mono)] text-text-primary border-b border-bg-elevated/50 ${rowBg}`}>${leg.strike}</td>
                    <td className={`px-2.5 py-2 text-right font-[var(--font-mono)] text-text-primary border-b border-bg-elevated/50 ${rowBg}`}>{leg.exp}</td>
                    <td className={`px-2.5 py-2 text-right font-[var(--font-mono)] text-text-primary border-b border-bg-elevated/50 ${rowBg}`}>{priceStr}</td>
                    <td className={`px-2.5 py-2 text-right font-[var(--font-mono)] text-text-primary border-b border-bg-elevated/50 ${rowBg}`}>{ivStr}</td>
                    <td className={`px-2.5 py-2 text-right font-[var(--font-mono)] text-text-primary border-b border-bg-elevated/50 ${rowBg}`}>{deltaStr}</td>
                    <td className={`px-2.5 py-2 text-right font-[var(--font-mono)] text-text-primary border-b border-bg-elevated/50 ${rowBg}`}>{thetaStr}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
