const st = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    padding: '6px 16px',
    background: 'var(--bg-surface)',
    borderTop: '1px solid var(--border-subtle)',
    fontFamily: 'var(--font-ui)',
    fontSize: 11,
    color: 'var(--text-tertiary)',
    flexWrap: 'wrap',
  },
  item: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
  },
  swatch: (color) => ({
    display: 'inline-block',
    width: 10,
    height: 10,
    borderRadius: 2,
    background: color,
  }),
  line: (color, dash) => ({
    display: 'inline-block',
    width: 16,
    height: 0,
    borderTop: `2px ${dash ? 'dashed' : 'solid'} ${color}`,
  }),
};

export default function Legend({ interval = '15min', barCount = 80 }) {
  return (
    <div style={st.bar}>
      <span style={st.item}><span style={st.swatch('#26a69a')} />Bullish</span>
      <span style={st.item}><span style={st.swatch('#ef5350')} />Bearish</span>
      <span style={st.item}><span style={st.line('#00e676', true)} />Long Strike</span>
      <span style={st.item}><span style={st.line('#ff5252', true)} />Short Strike</span>
      <span style={st.item}><span style={st.line('#ffd600', true)} />GEX Flip</span>
      <span style={st.item}><span style={st.swatch('rgba(0, 230, 118, 0.2)')} />Profit</span>
      <span style={st.item}><span style={st.swatch('rgba(255, 23, 68, 0.2)')} />Loss</span>
      <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
        {interval === '15min' ? '15M' : interval === '1h' ? '1H' : '4H'} &middot; {barCount} bars
      </span>
    </div>
  );
}
