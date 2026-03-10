import { useMemo } from 'react';

const font = "'Courier New', monospace";

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
      return cell.pnl >= 0 ? `+$${cell.pnl.toFixed(0)}` : `-$${Math.abs(cell.pnl).toFixed(0)}`;
    case VIEW_MODES.PNL_PCT:
    case VIEW_MODES.MAX_RISK_PCT:
      return cell.pnl_pct >= 0 ? `+${cell.pnl_pct.toFixed(1)}%` : `${cell.pnl_pct.toFixed(1)}%`;
    case VIEW_MODES.CONTRACT_VALUE:
      return `$${cell.contract_value.toFixed(0)}`;
    default:
      return `$${cell.pnl.toFixed(0)}`;
  }
}

const s = {
  wrapper: {
    flex: 1,
    overflow: 'auto',
    background: '#080810',
    fontFamily: font,
    fontSize: 11,
  },
  table: {
    borderCollapse: 'collapse',
    width: '100%',
    minWidth: 400,
  },
  th: (isExpiry) => ({
    padding: '6px 8px',
    background: '#0d0d18',
    color: isExpiry ? '#ffd600' : '#888',
    fontWeight: isExpiry ? 700 : 600,
    fontSize: 10,
    textAlign: 'center',
    borderBottom: '1px solid #1a1a2e',
    borderRight: isExpiry ? '2px solid #ffd60066' : '1px solid #1a1a2e',
    position: 'sticky',
    top: 0,
    zIndex: 2,
    whiteSpace: 'nowrap',
  }),
  priceCell: (isSpot) => ({
    padding: '4px 8px',
    background: isSpot ? '#448aff22' : '#0d0d18',
    color: isSpot ? '#448aff' : '#aaa',
    fontWeight: isSpot ? 700 : 600,
    fontSize: 11,
    textAlign: 'right',
    borderRight: '1px solid #1a1a2e',
    borderBottom: '1px solid #1a1a2e',
    position: 'sticky',
    left: 0,
    zIndex: 1,
    whiteSpace: 'nowrap',
  }),
  dataCell: (bgColor, isSpotRow, isExpiry) => ({
    padding: '4px 6px',
    textAlign: 'center',
    color: '#fff',
    fontSize: 10,
    fontWeight: 500,
    background: bgColor,
    borderBottom: isSpotRow ? '2px solid #448aff66' : '1px solid #0a0a14',
    borderRight: isExpiry ? '2px solid #ffd60066' : '1px solid #0a0a14',
    whiteSpace: 'nowrap',
  }),
  empty: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    color: '#555',
    fontFamily: font,
    fontSize: 12,
    padding: 40,
  },
};

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
    return <div style={s.empty}>Run Calculate to generate the P&amp;L table</div>;
  }

  if (!grid.rows || grid.rows.length === 0) {
    return <div style={s.empty}>No grid data available</div>;
  }

  const { time_slices, price_levels, rows, max_profit, max_loss } = grid;

  return (
    <div style={s.wrapper}>
      <table style={s.table}>
        <thead>
          <tr>
            <th style={{ ...s.th(false), position: 'sticky', left: 0, zIndex: 3 }}>Price</th>
            {time_slices.map((ts, ci) => (
              <th key={ci} style={s.th(ts.is_expiry)}>{ts.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => {
            const isSpot = ri === spotIdx;
            return (
              <tr key={ri}>
                <td style={s.priceCell(isSpot)}>
                  ${price_levels[ri].toFixed(0)}
                  {isSpot && <span style={{ color: '#448aff', fontSize: 9, marginLeft: 3 }}>&#9668;</span>}
                </td>
                {row.map((cell, ci) => {
                  const bg = cellColor(cell.pnl, max_profit, max_loss);
                  return (
                    <td key={ci} style={s.dataCell(bg, isSpot, time_slices[ci]?.is_expiry)}>
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
