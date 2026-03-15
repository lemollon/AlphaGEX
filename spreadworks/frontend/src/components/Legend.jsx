export default function Legend({ barCount = 0, sessionDate = null }) {
  const items = [
    { type: 'swatch', color: '#22c55e', label: 'Bullish' },
    { type: 'swatch', color: '#ef4444', label: 'Bearish' },
    { type: 'separator' },
    { type: 'swatch', color: 'rgba(34,197,94,0.6)', label: '+GEX Bar' },
    { type: 'swatch', color: 'rgba(239,68,68,0.6)', label: '-GEX Bar' },
    { type: 'separator' },
    { type: 'line', color: '#eab308', dash: true, label: 'Flip' },
    { type: 'line', color: '#06b6d4', dash: true, label: 'Call Wall' },
    { type: 'line', color: '#a855f7', dash: true, label: 'Put Wall' },
    { type: 'line', color: '#f97316', dash: true, label: '±1σ' },
    { type: 'separator' },
    { type: 'line', color: '#22c55e', dash: true, label: 'Long Strike' },
    { type: 'line', color: '#ef4444', dash: true, label: 'Short Strike' },
    { type: 'separator' },
    { type: 'swatch', color: 'rgba(34, 197, 94, 0.25)', label: 'Profit' },
    { type: 'swatch', color: 'rgba(239, 68, 68, 0.25)', label: 'Loss' },
  ];

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-t border-border-subtle font-[var(--font-ui)] text-[11px] text-text-tertiary flex-wrap"
      style={{ background: 'linear-gradient(180deg, rgba(8, 8, 24, 0.95) 0%, rgba(5, 5, 16, 0.95) 100%)' }}>
      {items.map((item, i) => {
        if (item.type === 'separator') {
          return <span key={i} className="text-border-subtle">|</span>;
        }
        return (
          <span key={i} className="inline-flex items-center gap-1.5">
            {item.type === 'swatch' ? (
              <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: item.color, boxShadow: `0 0 6px ${item.color}44` }} />
            ) : (
              <span className="inline-block w-[18px] h-0" style={{ borderTop: `2px ${item.dash ? 'dashed' : 'solid'} ${item.color}` }} />
            )}
            {item.label}
          </span>
        );
      })}
      <span className="ml-auto text-text-muted font-[var(--font-mono)] text-[10px] font-medium">
        5M &middot; {barCount} bars{sessionDate ? ` · ${sessionDate}` : ''}
      </span>
    </div>
  );
}
