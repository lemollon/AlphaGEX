import { useState } from 'react';
import { formatCurrency2, formatPct, formatGreek, formatGreekDollar } from '../utils/format';

const s = {
  wrapper: {
    background: 'linear-gradient(180deg, rgba(10, 10, 26, 0.95) 0%, rgba(8, 8, 24, 0.95) 100%)',
    borderTop: '1px solid var(--border-subtle)',
    fontFamily: 'var(--font-ui)',
    fontSize: 12,
  },
  toggleBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--text-tertiary)',
    cursor: 'pointer',
    padding: '8px 16px',
    fontSize: 11,
    fontFamily: 'var(--font-ui)',
    fontWeight: 600,
    width: '100%',
    textAlign: 'left',
    transition: 'color var(--transition-fast)',
    letterSpacing: '0.03em',
  },
  table: {
    width: '100%',
    borderCollapse: 'separate',
    borderSpacing: '0 2px',
  },
  th: {
    padding: '8px 10px',
    color: 'var(--text-tertiary)',
    fontSize: 10,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    textAlign: 'right',
    borderBottom: '1px solid rgba(30, 30, 70, 0.5)',
  },
  td: (isLong) => ({
    padding: '8px 10px',
    textAlign: 'right',
    fontSize: 12,
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-primary)',
    background: isLong ? 'rgba(0, 230, 118, 0.04)' : 'rgba(255, 82, 82, 0.04)',
    borderBottom: '1px solid rgba(16, 16, 42, 0.5)',
  }),
  legName: (isLong) => ({
    textAlign: 'left',
    color: isLong ? 'var(--green)' : 'var(--red)',
    fontWeight: 600,
    fontFamily: 'var(--font-ui)',
  }),
};

export default function LegBreakdown({ calcResult }) {
  const [open, setOpen] = useState(false);
  const legs = calcResult?.legs;

  if (!legs || legs.length === 0) return null;

  const isTheoretical = calcResult?.pricing_mode === 'black_scholes';
  const tilde = isTheoretical ? '~' : '';

  return (
    <div style={s.wrapper}>
      <button
        style={s.toggleBtn}
        onClick={() => setOpen(!open)}
        onMouseEnter={(e) => e.target.style.color = 'var(--text-secondary)'}
        onMouseLeave={(e) => e.target.style.color = 'var(--text-tertiary)'}
      >
        {open ? 'Legs \u25B4' : 'Legs \u25BE'} ({legs.length} legs)
      </button>
      {open && (
        <div style={{ padding: '0 12px 10px', animation: 'sw-fadeIn 0.2s ease' }}>
          <table style={s.table}>
            <thead>
              <tr>
                <th style={{ ...s.th, textAlign: 'left' }}>Leg</th>
                <th style={s.th}>Strike</th>
                <th style={s.th}>Exp</th>
                <th style={s.th}>Mid</th>
                <th style={s.th}>IV</th>
                <th style={s.th}>{'\u0394'}</th>
                <th style={s.th}>{'\u0398'}</th>
              </tr>
            </thead>
            <tbody>
              {legs.map((leg, i) => {
                const isLong = leg.type === 'long';
                const greeks = leg.greeks || {};
                const priceStr = leg.price != null
                  ? `${tilde}${formatCurrency2(leg.price)}`
                  : '--';
                const ivStr = leg.iv != null
                  ? formatPct(leg.iv)
                  : '--';
                const deltaStr = formatGreek(greeks.delta, 3);
                const thetaStr = formatGreekDollar(greeks.theta);

                return (
                  <tr key={i}>
                    <td style={{ ...s.td(isLong), ...s.legName(isLong) }}>{leg.leg}</td>
                    <td style={s.td(isLong)}>${leg.strike}</td>
                    <td style={s.td(isLong)}>{leg.exp}</td>
                    <td style={s.td(isLong)}>{priceStr}</td>
                    <td style={s.td(isLong)}>{ivStr}</td>
                    <td style={s.td(isLong)}>{deltaStr}</td>
                    <td style={s.td(isLong)}>{thetaStr}</td>
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
