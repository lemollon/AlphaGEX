const s = {
  strip: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
    gap: 10,
    marginBottom: 16,
  },
  card: {
    background: 'var(--bg-card)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 14px',
    fontFamily: 'var(--font-ui)',
    textAlign: 'center',
    transition: 'border-color var(--transition-default)',
  },
  label: {
    fontSize: 10,
    fontWeight: 600,
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    marginBottom: 6,
  },
  value: (color) => ({
    fontSize: 18,
    fontWeight: 700,
    fontFamily: 'var(--font-mono)',
    color: color || '#fff',
  }),
};

export default function PortfolioSummary({ summary }) {
  if (!summary) return null;

  const unrealColor = summary.total_unrealized >= 0 ? 'var(--green)' : 'var(--red)';
  const realColor = summary.total_realized >= 0 ? 'var(--green)' : 'var(--red)';

  return (
    <div style={s.strip}>
      <div style={s.card}>
        <div style={s.label}>Slots</div>
        <div style={s.value('var(--accent)')}>
          {summary.slots_used}/{summary.slots_total}
        </div>
      </div>
      <div style={s.card}>
        <div style={s.label}>Total Credit</div>
        <div style={s.value('var(--green)')}>+${summary.total_credit?.toFixed(2)}</div>
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
        <div style={s.value('var(--text-secondary)')}>{summary.closed_count}</div>
      </div>
    </div>
  );
}
