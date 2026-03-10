const s = {
  slot: {
    background: 'var(--bg-surface)',
    border: '1px dashed #1a1a2e',
    borderRadius: 6,
    padding: 24,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#2a2a3a',
    fontSize: 11,
    fontFamily: "'Courier New', monospace",
    minHeight: 120,
  },
};

export default function EmptySlot({ number, total }) {
  return (
    <div style={s.slot}>
      Empty Slot {number}/{total}
    </div>
  );
}
