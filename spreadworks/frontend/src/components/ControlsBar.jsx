import { useState, useCallback, useRef } from 'react';

const st = {
  container: {
    background: 'linear-gradient(180deg, rgba(10, 10, 26, 0.95) 0%, rgba(8, 8, 24, 0.95) 100%)',
    borderTop: '1px solid var(--border-subtle)',
    padding: '10px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
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
  group: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '4px 10px',
    background: 'rgba(13, 13, 35, 0.5)',
    border: '1px solid rgba(30, 30, 70, 0.3)',
    borderRadius: 'var(--radius-md)',
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
    color: 'var(--accent-bright)',
    fontWeight: 600,
    fontSize: 12,
    fontFamily: 'var(--font-mono)',
    minWidth: 50,
  },
  liveBadge: (isOpen) => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    padding: '4px 12px',
    borderRadius: 20,
    background: isOpen
      ? 'linear-gradient(135deg, rgba(0, 230, 118, 0.12) 0%, rgba(0, 200, 100, 0.06) 100%)'
      : 'rgba(80, 80, 100, 0.15)',
    border: `1px solid ${isOpen ? 'rgba(0, 230, 118, 0.25)' : 'var(--border-subtle)'}`,
    color: isOpen ? 'var(--green)' : 'var(--text-tertiary)',
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: '0.05em',
    marginLeft: 'auto',
    boxShadow: isOpen ? '0 0 12px rgba(0, 230, 118, 0.1)' : 'none',
  }),
  dot: (isOpen) => ({
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: isOpen ? 'var(--green)' : 'var(--text-tertiary)',
    boxShadow: isOpen ? '0 0 8px rgba(0, 230, 118, 0.5)' : 'none',
    animation: isOpen ? 'sw-pulse 2s ease-in-out infinite' : 'none',
  }),
  toggleBtn: (active) => ({
    padding: '5px 14px',
    border: `1px solid ${active ? 'rgba(68, 138, 255, 0.3)' : 'rgba(30, 30, 70, 0.5)'}`,
    borderRadius: 'var(--radius-sm)',
    background: active ? 'rgba(68, 138, 255, 0.12)' : 'transparent',
    color: active ? 'var(--accent-bright)' : 'var(--text-tertiary)',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: 'var(--font-ui)',
    fontWeight: active ? 600 : 500,
    transition: 'all var(--transition-fast)',
  }),
  tfBtn: (active) => ({
    padding: '5px 14px',
    border: active ? 'none' : '1px solid rgba(30, 30, 70, 0.5)',
    borderRadius: 'var(--radius-sm)',
    background: active
      ? 'linear-gradient(135deg, var(--accent) 0%, #6366f1 100%)'
      : 'transparent',
    color: active ? '#fff' : 'var(--text-tertiary)',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: 'var(--font-ui)',
    fontWeight: active ? 700 : 500,
    boxShadow: active ? '0 2px 10px rgba(68, 138, 255, 0.3)' : 'none',
    transition: 'all var(--transition-fast)',
  }),
  refreshBtn: {
    background: 'rgba(13, 13, 35, 0.5)',
    border: '1px solid rgba(30, 30, 70, 0.5)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--text-tertiary)',
    cursor: 'pointer',
    padding: '4px 10px',
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
        <div style={st.group}>
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
        </div>

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
        <div style={{ display: 'flex', gap: 3, background: 'rgba(13, 13, 35, 0.5)', borderRadius: 'var(--radius-md)', padding: 3, border: '1px solid rgba(30, 30, 70, 0.3)' }}>
          {['15min', '1h', '4h'].map(tf => (
            <button key={tf} style={st.tfBtn(interval === tf)} onClick={() => onIntervalChange(tf)}>
              {tf === '15min' ? '15M' : tf === '1h' ? '1H' : '4H'}
            </button>
          ))}
        </div>
      </div>

      {/* Row 2: Range + IV */}
      <div style={st.row}>
        <div style={st.group}>
          <span style={st.label}>Range: &plusmn;{rangePct.toFixed(1)}%</span>
          <input
            type="range"
            min={10}
            max={100}
            value={rangePct * 10}
            onChange={(e) => onRangeChange(Number(e.target.value) / 10)}
            style={{ ...st.slider, maxWidth: 120 }}
          />
        </div>
        <button style={st.refreshBtn} onClick={onRefreshIv} title="Refresh IV">&orarr;</button>
        <div style={st.group}>
          <span style={st.label}>Implied Volatility:</span>
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
          <span style={{ color: 'var(--text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}>&times;3</span>
        </div>
      </div>

      {/* Row 3: View toggles */}
      <div style={st.row}>
        <div style={{ display: 'flex', gap: 3, background: 'rgba(13, 13, 35, 0.5)', borderRadius: 'var(--radius-md)', padding: 3, border: '1px solid rgba(30, 30, 70, 0.3)' }}>
          <button style={st.toggleBtn(viewMode === 'graph')} onClick={() => onViewModeChange('graph')}>
            Graph {viewMode === 'graph' ? '\u2713' : ''}
          </button>
          <button style={st.toggleBtn(viewMode === 'table')} onClick={() => onViewModeChange('table')}>
            Table {viewMode === 'table' ? '\u2713' : ''}
          </button>
        </div>
        <div style={{ width: 1, height: 20, background: 'var(--border-subtle)' }} />
        <div style={{ display: 'flex', gap: 3, background: 'rgba(13, 13, 35, 0.5)', borderRadius: 'var(--radius-md)', padding: 3, border: '1px solid rgba(30, 30, 70, 0.3)' }}>
          <button
            style={st.toggleBtn(tableViewMode === 'pnl_dollar')}
            onClick={() => onTableViewModeChange('pnl_dollar')}
          >
            P&amp;L $ {tableViewMode === 'pnl_dollar' ? '\u2713' : ''}
          </button>
          <button
            style={st.toggleBtn(tableViewMode === 'pnl_pct')}
            onClick={() => onTableViewModeChange('pnl_pct')}
          >
            P&amp;L % {tableViewMode === 'pnl_pct' ? '\u2713' : ''}
          </button>
          <button
            style={st.toggleBtn(tableViewMode === 'contract_value')}
            onClick={() => onTableViewModeChange('contract_value')}
          >
            Value {tableViewMode === 'contract_value' ? '\u2713' : ''}
          </button>
          <button
            style={st.toggleBtn(tableViewMode === 'max_risk_pct')}
            onClick={() => onTableViewModeChange('max_risk_pct')}
          >
            % Risk {tableViewMode === 'max_risk_pct' ? '\u2713' : ''}
          </button>
        </div>
      </div>
    </div>
  );
}
