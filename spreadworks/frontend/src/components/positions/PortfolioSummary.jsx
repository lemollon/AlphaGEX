const s = {
  strip: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
    gap: 8,
    marginBottom: 14,
  },
  card: {
    background: '#0d0d18',
    border: '1px solid #1a1a2e',
    borderRadius: 6,
    padding: '10px 12px',
    fontFamily: "'Courier New', monospace",
    textAlign: 'center',
  },
  label: {
    fontSize: 9,
    color: '#555',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    marginBottom: 4,
  },
  value: (color) => ({
    fontSize: 16,
    fontWeight: 700,
    color: color || '#fff',
  }),
};

export default function PortfolioSummary({ summary }) {
  if (!summary) return null;

  const unrealColor = summary.total_unrealized >= 0 ? '#00e676' : '#ff5252';
  const realColor = summary.total_realized >= 0 ? '#00e676' : '#ff5252';

  return (
    <div style={s.strip}>
      <div style={s.card}>
        <div style={s.label}>Slots</div>
        <div style={s.value('#448aff')}>
          {summary.slots_used}/{summary.slots_total}
        </div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Total Credit</div>
        <div style={s.value('#00e676')}>+${summary.total_credit?.toFixed(2)}</div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Unrealized</div>
        <div style={s.value(unrealColor)}>
          {summary.total_unrealized >= 0 ? '+' : ''}${summary.total_unrealized?.toFixed(2)}
        </div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Realized</div>
        <div style={s.value(realColor)}>
          {summary.total_realized >= 0 ? '+' : ''}${summary.total_realized?.toFixed(2)}
        </div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Open</div>
        <div style={s.value()}>{summary.open_count}</div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Closed</div>
        <div style={s.value('#888')}>{summary.closed_count}</div>
      </div>
    </div>
  );
}
