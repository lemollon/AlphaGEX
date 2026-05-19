export default function Legend({ interval = '15min', barCount = 80 }) {
  const items = [
    { type: 'swatch', color: '#26a69a', label: 'Bullish' },
    { type: 'swatch', color: '#ef5350', label: 'Bearish' },
    { type: 'line', color: '#34d399', dash: true, label: 'Long Strike' },
    { type: 'line', color: '#fb7185', dash: true, label: 'Short Strike' },
    { type: 'line', color: '#fcd34d', dash: true, label: 'GEX Flip' },
    { type: 'swatch', color: 'rgba(34, 197, 94, 0.25)', label: 'Profit' },
    { type: 'swatch', color: 'rgba(239, 68, 68, 0.25)', label: 'Loss' },
  ];

  return (
    <div className="flex items-center gap-4 px-4 py-2 border-t border-white/5 bg-bg-base font-[var(--font-ui)] text-[11px] text-text-tertiary flex-wrap">
      {items.map(({ type, color, dash, label }, i) => (
        <span key={i} className="inline-flex items-center gap-1.5">
          {type === 'swatch' ? (
            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
          ) : (
            <span className="inline-block w-[18px] h-0" style={{ borderTop: `2px ${dash ? 'dashed' : 'solid'} ${color}` }} />
          )}
          {label}
        </span>
      ))}
      <span className="ml-auto text-text-muted font-[var(--font-mono)] text-[10px] font-medium">
        {interval === '15min' ? '15M' : interval === '1h' ? '1H' : '4H'} &middot; {barCount} bars
      </span>
    </div>
  );
}
