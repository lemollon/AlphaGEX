import { useCallback, useRef } from 'react';
import { RefreshCw } from 'lucide-react';

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
    <div className="border-t border-border-subtle px-4 py-2.5 flex flex-col gap-2 font-[var(--font-ui)] text-xs text-text-secondary"
      style={{ background: 'linear-gradient(180deg, rgba(10, 10, 26, 0.95) 0%, rgba(8, 8, 24, 0.95) 100%)' }}>
      {/* Row 1 */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-lg bg-bg-card/50 border border-border-subtle/30">
          <span className="sw-label">Date:</span>
          <span className="text-accent-bright font-semibold text-xs font-[var(--font-mono)] min-w-[50px]">{dteLabel}</span>
          <input type="range" min={0} max={100} defaultValue={dteSlider} onChange={handleDteSlider}
            className="flex-1 min-w-[80px] max-w-[300px] h-[3px]" />
        </div>

        <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold tracking-wider border transition-all duration-150 ml-auto ${
          isMarketOpen
            ? 'bg-sw-green-dim border-sw-green/25 text-sw-green shadow-[0_0_12px_rgba(34,197,94,0.1)]'
            : 'bg-bg-elevated/30 border-border-subtle text-text-tertiary'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${isMarketOpen ? 'bg-sw-green animate-pulse-dot shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-text-tertiary'}`} />
          {isMarketOpen ? 'LIVE' : 'CLOSED'}
        </div>
        <span className="text-text-muted text-[11px]">
          {isMarketOpen ? `Updated ${secondsAgo}s ago`
            : dataAsOf ? `Cached data \u00b7 ${statusText}`
            : `Market Closed \u00b7 ${statusText}`}
        </span>

        <div className="sw-toggle-group !gap-0.5">
          {['15min', '1h', '4h'].map(tf => (
            <button key={tf} className={`sw-toggle-btn !px-3 !py-1 ${interval === tf ? 'active' : ''}`}
              onClick={() => onIntervalChange(tf)}>
              {tf === '15min' ? '15M' : tf === '1h' ? '1H' : '4H'}
            </button>
          ))}
        </div>
      </div>

      {/* Row 2 */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-lg bg-bg-card/50 border border-border-subtle/30">
          <span className="sw-label">Range: &plusmn;{rangePct.toFixed(1)}%</span>
          <input type="range" min={10} max={100} value={rangePct * 10}
            onChange={(e) => onRangeChange(Number(e.target.value) / 10)}
            className="flex-1 min-w-[80px] max-w-[120px] h-[3px]" />
        </div>
        <button className="sw-btn-ghost !px-2 !py-1 flex items-center gap-1 text-text-tertiary hover:text-accent" onClick={onRefreshIv} title="Refresh IV">
          <RefreshCw size={12} />
        </button>
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-lg bg-bg-card/50 border border-border-subtle/30">
          <span className="sw-label">Implied Volatility:</span>
          <span className="text-accent-bright font-semibold text-xs font-[var(--font-mono)] min-w-[50px]">&times;{ivMultiplier.toFixed(1)}</span>
          <input type="range" min={10} max={30} value={ivMultiplier * 10}
            onChange={(e) => onIvMultiplierChange(Number(e.target.value) / 10)}
            className="flex-1 min-w-[80px] max-w-[150px] h-[3px]" />
          <span className="text-text-muted text-[10px] font-[var(--font-mono)]">&times;1</span>
          <span className="text-text-muted text-[10px] font-[var(--font-mono)]">&times;3</span>
        </div>
      </div>

      {/* Row 3 */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="sw-toggle-group !gap-0.5">
          <button className={`sw-toggle-btn !px-3 !py-1 ${viewMode === 'graph' ? 'active' : ''}`}
            onClick={() => onViewModeChange('graph')}>
            Graph {viewMode === 'graph' ? '\u2713' : ''}
          </button>
          <button className={`sw-toggle-btn !px-3 !py-1 ${viewMode === 'table' ? 'active' : ''}`}
            onClick={() => onViewModeChange('table')}>
            Table {viewMode === 'table' ? '\u2713' : ''}
          </button>
        </div>
        <div className="w-px h-5 bg-border-subtle" />
        <div className="sw-toggle-group !gap-0.5">
          {[
            { key: 'pnl_dollar', label: 'P&L $' },
            { key: 'pnl_pct', label: 'P&L %' },
            { key: 'contract_value', label: 'Value' },
            { key: 'max_risk_pct', label: '% Risk' },
          ].map(({ key, label }) => (
            <button key={key} className={`sw-toggle-btn !px-3 !py-1 ${tableViewMode === key ? 'active' : ''}`}
              onClick={() => onTableViewModeChange(key)}>
              {label} {tableViewMode === key ? '\u2713' : ''}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
