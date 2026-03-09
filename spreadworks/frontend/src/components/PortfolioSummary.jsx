const s = {
  container: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
    gap: 8,
    marginBottom: 12,
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

  const unrealColor = summary.total_unrealised >= 0 ? '#00e676' : '#ff5252';
  const realizedColor = summary.total_realized >= 0 ? '#00e676' : '#ff5252';

  return (
    <div style={s.container}>
      <div style={s.card}>
        <div style={s.label}>Slots Used</div>
        <div style={s.value('#448aff')}>
          {summary.slots_used}/{summary.slots_total}
        </div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Invested</div>
        <div style={s.value()}>${summary.total_invested?.toFixed(2)}</div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Unrealised</div>
        <div style={s.value(unrealColor)}>
          ${summary.total_unrealised >= 0 ? '+' : ''}{summary.total_unrealised?.toFixed(2)}
        </div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Realized</div>
        <div style={s.value(realizedColor)}>
          ${summary.total_realized >= 0 ? '+' : ''}{summary.total_realized?.toFixed(2)}
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
