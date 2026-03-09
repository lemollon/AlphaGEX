import { useState, useCallback, useRef } from 'react';

const font = "'Courier New', monospace";

const st = {
  container: {
    background: '#0d0d18',
    borderTop: '1px solid #1a1a2e',
    padding: '6px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 5,
    fontFamily: font,
    fontSize: 11,
    color: '#888',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap',
  },
  label: {
    color: '#555',
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    whiteSpace: 'nowrap',
  },
  slider: {
    flex: 1,
    minWidth: 80,
    maxWidth: 300,
    accentColor: '#448aff',
    height: 4,
  },
  value: {
    color: '#ccc',
    fontWeight: 600,
    fontSize: 11,
    minWidth: 50,
  },
  liveBadge: (isOpen) => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '2px 8px',
    borderRadius: 3,
    background: isOpen ? '#00e67622' : '#33333344',
    border: `1px solid ${isOpen ? '#00e676' : '#333'}`,
    color: isOpen ? '#00e676' : '#666',
    fontSize: 10,
    fontWeight: 600,
    marginLeft: 'auto',
  }),
  dot: (isOpen) => ({
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: isOpen ? '#00e676' : '#666',
  }),
  toggleBtn: (active) => ({
    padding: '3px 10px',
    border: `1px solid ${active ? '#448aff' : '#1a1a2e'}`,
    borderRadius: 3,
    background: active ? '#448aff33' : 'transparent',
    color: active ? '#448aff' : '#555',
    cursor: 'pointer',
    fontSize: 10,
    fontFamily: font,
  }),
  tfBtn: (active) => ({
    padding: '3px 10px',
    border: `1px solid ${active ? '#448aff' : '#1a1a2e'}`,
    borderRadius: 3,
    background: active ? '#448aff' : 'transparent',
    color: active ? '#fff' : '#555',
    cursor: 'pointer',
    fontSize: 10,
    fontFamily: font,
    fontWeight: active ? 600 : 400,
  }),
  refreshBtn: {
    background: 'transparent',
    border: '1px solid #1a1a2e',
    borderRadius: 3,
    color: '#555',
    cursor: 'pointer',
    padding: '2px 6px',
    fontSize: 12,
    fontFamily: font,
  },
};

export default function ControlsBar({
  dteSlider,
  onDteChange,
  rangePct,
  onRangeChange,
  ivMultiplier,
  onIvMultiplierChange,
  isMarketOpen,
  secondsAgo,
  statusText,
  interval,
  onIntervalChange,
  onRefreshIv,
  viewMode,
  onViewModeChange,
}) {
  const debounceRef = useRef(null);

  const handleDteSlider = useCallback((e) => {
    const val = Number(e.target.value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (onDteChange) onDteChange(val);
    }, 300);
    // Immediate visual update
    e.target.style.setProperty('--val', val);
  }, [onDteChange]);

  const dteLabel = dteSlider === 100 ? 'At expiration'
    : dteSlider === 0 ? 'Current date'
    : `${100 - dteSlider}% DTE remaining`;

  return (
    <div style={st.container}>
      {/* Row 1: Date slider + Live badge + Timeframe buttons */}
      <div style={st.row}>
        <span style={st.label}>DATE:</span>
        <span style={st.value}>{dteLabel}</span>
        <input
          type="range"
          min={0}
          max={100}
          defaultValue={dteSlider}
          onChange={handleDteSlider}
          style={st.slider}
        />
        <span style={{ color: '#555', fontSize: 10 }}>(At expiration)</span>

        <div style={st.liveBadge(isMarketOpen)}>
          <span style={st.dot(isMarketOpen)} />
          {isMarketOpen ? 'LIVE' : 'CLOSED'}
        </div>
        <span style={{ color: '#444', fontSize: 10 }}>
          {isMarketOpen ? `Updated ${secondsAgo}s ago` : `Market Closed \u00b7 ${statusText}`}
        </span>

        {/* Timeframe buttons */}
        <div style={{ display: 'flex', gap: 2, marginLeft: 8 }}>
          {['15min', '1h', '4h'].map(tf => (
            <button key={tf} style={st.tfBtn(interval === tf)} onClick={() => onIntervalChange(tf)}>
              {tf === '15min' ? '15M' : tf === '1h' ? '1H' : '4H'}
            </button>
          ))}
        </div>
      </div>

      {/* Row 2: Range + IV */}
      <div style={st.row}>
        <span style={st.label}>RANGE: &plusmn;{rangePct.toFixed(1)}%</span>
        <input
          type="range"
          min={10}
          max={100}
          value={rangePct * 10}
          onChange={(e) => onRangeChange(Number(e.target.value) / 10)}
          style={{ ...st.slider, maxWidth: 120 }}
        />
        <button style={st.refreshBtn} onClick={onRefreshIv} title="Refresh IV">&orarr;</button>
        <span style={{ ...st.label, marginLeft: 8 }}>IMPLIED VOLATILITY:</span>
        <span style={st.value}>&times;{ivMultiplier.toFixed(1)}</span>
        <input
          type="range"
          min={10}
          max={30}
          value={ivMultiplier * 10}
          onChange={(e) => onIvMultiplierChange(Number(e.target.value) / 10)}
          style={{ ...st.slider, maxWidth: 150 }}
        />
        <span style={{ color: '#444', fontSize: 9 }}>&times;1</span>
        <span style={{ color: '#444', fontSize: 9 }}>&times;2</span>
        <span style={{ color: '#444', fontSize: 9 }}>&times;3</span>
      </div>

      {/* Row 3: View toggles */}
      <div style={st.row}>
        <button style={st.toggleBtn(viewMode === 'table')} onClick={() => onViewModeChange('table')}>
          &#8862; Table
        </button>
        <button style={st.toggleBtn(viewMode === 'graph')} onClick={() => onViewModeChange('graph')}>
          &#128200; Graph {viewMode === 'graph' ? '\u2713' : ''}
        </button>
        <button style={st.toggleBtn(false)}>Profit/Loss $</button>
        <button style={st.toggleBtn(true)}>Profit/Loss % \u2713</button>
        <button style={st.toggleBtn(false)}>Contract Value</button>
        <button style={st.toggleBtn(false)}>% of Max Risk</button>
        <button style={{ ...st.toggleBtn(false), color: '#444' }}>&or; More</button>
      </div>
    </div>
  );
}
