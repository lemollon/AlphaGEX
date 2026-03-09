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
};

export default function MetricsBar({ calcResult }) {
  const r = calcResult || {};

  const netCredit = r.net_credit ?? r.net_debit;
  const isCredit = netCredit != null && netCredit > 0;
  const creditLabel = isCredit ? 'NET CREDIT' : 'NET DEBIT';
  const creditColor = isCredit ? '#00e676' : '#ff5252';
  const creditVal = netCredit != null ? `${isCredit ? '+' : ''}$${Math.abs(netCredit).toFixed(0)}` : '--';

  const maxProfit = r.max_profit != null ? `$${r.max_profit.toFixed(0)}` : '--';
  const maxLoss = r.max_loss != null ? `-$${Math.abs(r.max_loss).toFixed(0)}` : '--';
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

  return (
    <div style={st.bar}>
      <div style={st.cell}>
        <span style={st.label}>{creditLabel}</span>
        <span style={st.value(creditColor)}>{creditVal}</span>
      </div>
      <div style={st.cell}>
        <span style={st.label}>MAX PROFIT</span>
        <span style={st.value('#00e676')}>{maxProfit}</span>
      </div>
      <div style={st.cell}>
        <span style={st.label}>MAX LOSS</span>
        <span style={st.value('#ff5252')}>{maxLoss}</span>
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
  );
}
