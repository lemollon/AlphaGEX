const s = {
  slot: {
    background: 'var(--bg-card)',
    border: '1px dashed var(--border-subtle)',
    borderRadius: 'var(--radius-lg)',
    padding: 28,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'var(--text-muted)',
    fontSize: 12,
    fontFamily: 'var(--font-ui)',
    fontWeight: 500,
    minHeight: 120,
    transition: 'border-color var(--transition-default)',
  },
};

export default function EmptySlot({ number, total }) {
  return (
    <div style={s.slot}>
      Empty Slot {number}/{total}
    </div>
  );
}
