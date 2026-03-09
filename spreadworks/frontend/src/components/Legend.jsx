const font = "'Courier New', monospace";

const st = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    padding: '5px 12px',
    background: '#0a0a12',
    borderTop: '1px solid #1a1a2e',
    fontFamily: font,
    fontSize: 10,
    color: '#555',
    flexWrap: 'wrap',
  },
  swatch: (color) => ({
    display: 'inline-block',
    width: 10,
    height: 10,
    borderRadius: 2,
    background: color,
    marginRight: 4,
    verticalAlign: 'middle',
  }),
  line: (color, dash) => ({
    display: 'inline-block',
    width: 16,
    height: 0,
    borderTop: `2px ${dash ? 'dashed' : 'solid'} ${color}`,
    marginRight: 4,
    verticalAlign: 'middle',
  }),
};

export default function Legend({ interval = '15min', barCount = 80 }) {
  return (
    <div style={st.bar}>
      <span><span style={st.swatch('#26a69a')} />Bullish</span>
      <span><span style={st.swatch('#ef5350')} />Bearish</span>
      <span><span style={st.line('#00e676', true)} />Long Strike</span>
      <span><span style={st.line('#ff5252', true)} />Short Strike</span>
      <span><span style={st.line('#ffd600', true)} />GEX Flip</span>
      <span><span style={st.swatch('#00e67633')} />Profit</span>
      <span><span style={st.swatch('#ff174433')} />Loss</span>
      <span style={{ marginLeft: 'auto', color: '#444' }}>
        {interval === '15min' ? '15M' : interval === '1h' ? '1H' : '4H'} &middot; {barCount} bars
      </span>
    </div>
  );
}
