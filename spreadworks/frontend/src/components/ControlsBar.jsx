import { useState, useCallback, useRef } from 'react';

const st = {
  container: {
    background: 'var(--bg-surface)',
    borderTop: '1px solid var(--border-subtle)',
    padding: '8px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    fontFamily: 'var(--font-ui)',
    fontSize: 12,
    color: 'var(--text-secondary)',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    flexWrap: 'wrap',
  },
  label: {
    color: 'var(--text-tertiary)',
    fontSize: 10,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    whiteSpace: 'nowrap',
  },
  slider: {
    flex: 1,
    minWidth: 80,
    maxWidth: 300,
    accentColor: 'var(--accent)',
    height: 3,
  },
  value: {
    color: 'var(--text-primary)',
    fontWeight: 600,
    fontSize: 12,
    fontFamily: 'var(--font-mono)',
    minWidth: 50,
  },
  liveBadge: (isOpen) => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    padding: '3px 10px',
    borderRadius: 20,
    background: isOpen ? 'var(--green-dim)' : 'rgba(80, 80, 100, 0.15)',
    border: `1px solid ${isOpen ? 'rgba(0, 230, 118, 0.2)' : 'var(--border-subtle)'}`,
    color: isOpen ? 'var(--green)' : 'var(--text-tertiary)',
    fontSize: 10,
    fontWeight: 600,
    marginLeft: 'auto',
  }),
  dot: (isOpen) => ({
    width: 5,
    height: 5,
    borderRadius: '50%',
    background: isOpen ? 'var(--green)' : 'var(--text-tertiary)',
    boxShadow: isOpen ? '0 0 6px rgba(0, 230, 118, 0.4)' : 'none',
  }),
  toggleBtn: (active) => ({
    padding: '4px 12px',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border-subtle)'}`,
    borderRadius: 'var(--radius-sm)',
    background: active ? 'rgba(68, 138, 255, 0.12)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-tertiary)',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: 'var(--font-ui)',
    fontWeight: active ? 600 : 500,
    transition: 'all var(--transition-fast)',
  }),
  tfBtn: (active) => ({
    padding: '4px 12px',
    border: active ? 'none' : '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-sm)',
    background: active
      ? 'linear-gradient(135deg, var(--accent) 0%, #5c9bff 100%)'
      : 'transparent',
    color: active ? '#fff' : 'var(--text-tertiary)',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: 'var(--font-ui)',
    fontWeight: active ? 600 : 500,
    boxShadow: active ? '0 1px 6px rgba(68, 138, 255, 0.2)' : 'none',
    transition: 'all var(--transition-fast)',
  }),
  refreshBtn: {
    background: 'transparent',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--text-tertiary)',
    cursor: 'pointer',
    padding: '3px 8px',
    fontSize: 13,
    fontFamily: 'var(--font-ui)',
    transition: 'all var(--transition-fast)',
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
  dataAsOf,
  interval,
  onIntervalChange,
  onRefreshIv,
  viewMode,
  onViewModeChange,
  tableViewMode,
  onTableViewModeChange,
}) {
  const debounceRef = useRef(null);

  const handleDteSlider = useCallback((e) => {
    const val = Number(e.target.value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (onDteChange) onDteChange(val);
    }, 300);
    e.target.style.setProperty('--val', val);
  }, [onDteChange]);

  const dteLabel = dteSlider === 100 ? 'At expiration'
    : dteSlider === 0 ? 'Current date'
    : `${100 - dteSlider}% DTE remaining`;

  return (
    <div style={st.container}>
      {/* Row 1: Date slider + Live badge + Timeframe buttons */}
      <div style={st.row}>
        <span style={st.label}>Date:</span>
        <span style={st.value}>{dteLabel}</span>
        <input
          type="range"
          min={0}
          max={100}
          defaultValue={dteSlider}
          onChange={handleDteSlider}
          style={st.slider}
        />
        <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>(At expiration)</span>

        <div style={st.liveBadge(isMarketOpen)}>
          <span style={st.dot(isMarketOpen)} />
          {isMarketOpen ? 'LIVE' : 'CLOSED'}
        </div>
        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
          {isMarketOpen
            ? `Updated ${secondsAgo}s ago`
            : dataAsOf
              ? `Cached data \u00b7 ${statusText}`
              : `Market Closed \u00b7 ${statusText}`}
        </span>

        {/* Timeframe buttons */}
        <div style={{ display: 'flex', gap: 3 }}>
          {['15min', '1h', '4h'].map(tf => (
            <button key={tf} style={st.tfBtn(interval === tf)} onClick={() => onIntervalChange(tf)}>
              {tf === '15min' ? '15M' : tf === '1h' ? '1H' : '4H'}
            </button>
          ))}
        </div>
      </div>

      {/* Row 2: Range + IV */}
      <div style={st.row}>
        <span style={st.label}>Range: &plusmn;{rangePct.toFixed(1)}%</span>
        <input
          type="range"
          min={10}
          max={100}
          value={rangePct * 10}
          onChange={(e) => onRangeChange(Number(e.target.value) / 10)}
          style={{ ...st.slider, maxWidth: 120 }}
        />
        <button style={st.refreshBtn} onClick={onRefreshIv} title="Refresh IV">&orarr;</button>
        <span style={{ ...st.label, marginLeft: 8 }}>Implied Volatility:</span>
        <span style={st.value}>&times;{ivMultiplier.toFixed(1)}</span>
        <input
          type="range"
          min={10}
          max={30}
          value={ivMultiplier * 10}
          onChange={(e) => onIvMultiplierChange(Number(e.target.value) / 10)}
          style={{ ...st.slider, maxWidth: 150 }}
        />
        <span style={{ color: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>&times;1</span>
        <span style={{ color: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>&times;2</span>
        <span style={{ color: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>&times;3</span>
      </div>

      {/* Row 3: View toggles */}
      <div style={st.row}>
        <button style={st.toggleBtn(viewMode === 'table')} onClick={() => onViewModeChange('table')}>
          &#8862; Table {viewMode === 'table' ? '\u2713' : ''}
        </button>
        <button style={st.toggleBtn(viewMode === 'graph')} onClick={() => onViewModeChange('graph')}>
          &#128200; Graph {viewMode === 'graph' ? '\u2713' : ''}
        </button>
        <span style={{ color: 'var(--border-subtle)', margin: '0 2px' }}>|</span>
        <button
          style={st.toggleBtn(tableViewMode === 'pnl_dollar')}
          onClick={() => onTableViewModeChange('pnl_dollar')}
        >
          Profit/Loss $ {tableViewMode === 'pnl_dollar' ? '\u2713' : ''}
        </button>
        <button
          style={st.toggleBtn(tableViewMode === 'pnl_pct')}
          onClick={() => onTableViewModeChange('pnl_pct')}
        >
          Profit/Loss % {tableViewMode === 'pnl_pct' ? '\u2713' : ''}
        </button>
        <button
          style={st.toggleBtn(tableViewMode === 'contract_value')}
          onClick={() => onTableViewModeChange('contract_value')}
        >
          Contract Value {tableViewMode === 'contract_value' ? '\u2713' : ''}
        </button>
        <button
          style={st.toggleBtn(tableViewMode === 'max_risk_pct')}
          onClick={() => onTableViewModeChange('max_risk_pct')}
        >
          % of Max Risk {tableViewMode === 'max_risk_pct' ? '\u2713' : ''}
        </button>
      </div>
    </div>
  );
}
