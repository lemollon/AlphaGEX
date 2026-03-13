import { useMemo } from 'react';
import { formatDollarPnl, formatSignedPct, formatCurrency } from '../utils/format';

const VIEW_MODES = {
  PNL_DOLLAR: 'pnl_dollar',
  PNL_PCT: 'pnl_pct',
  MAX_RISK_PCT: 'max_risk_pct',
  CONTRACT_VALUE: 'contract_value',
};

function cellColor(pnl, maxProfit, maxLoss) {
  if (pnl === 0) return 'transparent';
  if (pnl > 0) {
    const intensity = maxProfit > 0 ? Math.min(pnl / maxProfit, 1) : 0;
    const alpha = Math.round(intensity * 180);
    return `rgba(0, 230, 118, ${alpha / 255})`;
  }
  const intensity = maxLoss < 0 ? Math.min(Math.abs(pnl / maxLoss), 1) : 0;
  const alpha = Math.round(intensity * 180);
  return `rgba(255, 82, 82, ${alpha / 255})`;
}

function formatCell(cell, viewMode) {
  switch (viewMode) {
    case VIEW_MODES.PNL_DOLLAR:
      return formatDollarPnl(cell.pnl);
    case VIEW_MODES.PNL_PCT:
    case VIEW_MODES.MAX_RISK_PCT:
      return formatSignedPct(cell.pnl_pct);
    case VIEW_MODES.CONTRACT_VALUE:
      return formatCurrency(cell.contract_value);
    default:
      return formatDollarPnl(cell.pnl);
  }
}

export default function PnLTable({ calcResult, viewMode: tableViewMode }) {
  const grid = calcResult?.pnl_grid;

  const activeView = tableViewMode || VIEW_MODES.PNL_DOLLAR;

  const spotIdx = useMemo(() => {
    if (!grid) return -1;
    const spot = grid.spot_price;
    let closest = 0;
    let minDist = Infinity;
    grid.price_levels.forEach((px, i) => {
      const d = Math.abs(px - spot);
      if (d < minDist) { minDist = d; closest = i; }
    });
    return closest;
  }, [grid]);

  if (!grid) {
    return (
      <div className="flex flex-1 items-center justify-center text-text-muted font-[var(--font-mono)] text-xs p-10">
        Run Calculate to generate the P&amp;L table
      </div>
    );
  }

  if (!grid.rows || grid.rows.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-text-muted font-[var(--font-mono)] text-xs p-10">
        No grid data available
      </div>
    );
  }

  const { time_slices, price_levels, rows, max_profit, max_loss } = grid;

  return (
    <div className="flex-1 overflow-auto bg-bg-base font-[var(--font-mono)] text-[11px]">
      <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 400 }}>
        <thead>
          <tr>
            <th className="px-2 py-1.5 bg-bg-surface text-text-muted font-semibold text-[10px] text-center whitespace-nowrap sticky top-0 left-0 z-[3]"
              style={{ borderBottom: '1px solid #1a1a2e', borderRight: '1px solid #1a1a2e' }}>
              Price
            </th>
            {time_slices.map((ts, ci) => (
              <th key={ci}
                className={`px-2 py-1.5 bg-bg-surface font-semibold text-[10px] text-center whitespace-nowrap sticky top-0 z-[2] ${
                  ts.is_expiry ? 'text-accent-bright font-bold' : 'text-text-muted'
                }`}
                style={{
                  borderBottom: '1px solid #1a1a2e',
                  borderRight: ts.is_expiry ? '2px solid rgba(245, 158, 11, 0.4)' : '1px solid #1a1a2e',
                }}>
                {ts.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => {
            const isSpot = ri === spotIdx;
            return (
              <tr key={ri}>
                <td
                  className={`px-2 py-1 text-right font-semibold text-[11px] whitespace-nowrap sticky left-0 z-[1] ${
                    isSpot ? 'bg-accent/[0.13] text-accent font-bold' : 'bg-bg-surface text-text-secondary'
                  }`}
                  style={{ borderRight: '1px solid #1a1a2e', borderBottom: '1px solid #1a1a2e' }}>
                  ${price_levels[ri].toFixed(0)}
                  {isSpot && <span className="text-accent text-[9px] ml-0.5">&#9668;</span>}
                </td>
                {row.map((cell, ci) => {
                  const bg = cellColor(cell.pnl, max_profit, max_loss);
                  return (
                    <td key={ci}
                      className="px-1.5 py-1 text-center text-white text-[10px] font-medium whitespace-nowrap"
                      style={{
                        background: bg,
                        borderBottom: isSpot ? '2px solid rgba(245, 158, 11, 0.4)' : '1px solid #0a0a14',
                        borderRight: time_slices[ci]?.is_expiry ? '2px solid rgba(245, 158, 11, 0.4)' : '1px solid #0a0a14',
                      }}>
                      {formatCell(cell, activeView)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export { VIEW_MODES };
