import { useState } from 'react';
import { formatCurrency2, formatPct, formatGreek, formatGreekDollar } from '../utils/format';

const font = "'Courier New', monospace";

const s = {
  wrapper: {
    background: 'var(--bg-surface)',
    borderTop: '1px solid #1a1a2e',
    fontFamily: font,
    fontSize: 11,
  },
  toggleBtn: {
    background: 'transparent',
    border: 'none',
    color: '#555',
    cursor: 'pointer',
    padding: '4px 12px',
    fontSize: 10,
    fontFamily: font,
    fontWeight: 600,
    width: '100%',
    textAlign: 'left',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  th: {
    padding: '4px 8px',
    color: '#555',
    fontSize: 9,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
    textAlign: 'right',
    borderBottom: '1px solid #1a1a2e',
    fontWeight: 600,
  },
  td: (isLong) => ({
    padding: '4px 8px',
    textAlign: 'right',
    fontSize: 11,
    color: '#ccc',
    borderBottom: '1px solid #0a0a14',
    background: isLong ? '#00e67608' : '#ff525208',
  }),
  legName: (isLong) => ({
    textAlign: 'left',
    color: isLong ? '#00e676' : '#ff5252',
    fontWeight: 600,
  }),
  noData: {
    color: '#444',
    fontStyle: 'italic',
    fontSize: 10,
  },
};

export default function LegBreakdown({ calcResult }) {
  const [open, setOpen] = useState(false);
  const legs = calcResult?.legs;

  if (!legs || legs.length === 0) return null;

  const isTheoretical = calcResult?.pricing_mode === 'black_scholes';
  const tilde = isTheoretical ? '~' : '';

  return (
    <div style={s.wrapper}>
      <button style={s.toggleBtn} onClick={() => setOpen(!open)}>
        {open ? 'Legs \u25B4' : 'Legs \u25BE'} ({legs.length} legs)
      </button>
      {open && (
        <div style={{ padding: '0 8px 8px' }}>
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
