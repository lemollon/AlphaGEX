import { useMemo, useState, useCallback } from 'react';
import CandleChart from './CandleChart';
import PayoffPanel from './PayoffPanel';

/**
 * Container that renders CandleChart (Plotly) and PayoffPanel side-by-side.
 *
 * The Plotly chart computes its own Y range from intraday bars + GEX levels.
 * That range is passed to PayoffPanel via a callback so strike lines align.
 */
export default function ChartArea({
  intradayBars,
  sortedStrikes,
  levels,
  spotPrice,
  strikes,
  calcResult,
  height = 500,
  sessionDate,
}) {
  // yRange synced from CandleChart's Plotly layout
  const [yRange, setYRange] = useState(null);

  const handleYRange = useCallback((range) => {
    setYRange(range);
  }, []);

  const minPrice = yRange ? yRange[0] : (spotPrice ? spotPrice - 15 : 550);
  const maxPrice = yRange ? yRange[1] : (spotPrice ? spotPrice + 15 : 590);

  const breakevens = calcResult ? {
    lower: calcResult.lower_breakeven,
    upper: calcResult.upper_breakeven,
  } : null;

  return (
    <div className="flex flex-1 min-h-0">
      <CandleChart
        intradayBars={intradayBars}
        sortedStrikes={sortedStrikes}
        levels={levels}
        strikes={strikes}
        spotPrice={spotPrice}
        height={height}
        sessionDate={sessionDate}
        yRangeOut={handleYRange}
      />
      <PayoffPanel
        pnlCurve={calcResult?.pnl_curve}
        minPrice={minPrice}
        maxPrice={maxPrice}
        height={height}
        strikes={strikes}
        spotPrice={spotPrice}
        maxProfit={calcResult?.max_profit}
        maxLoss={calcResult?.max_loss}
        breakevens={breakevens}
      />
    </div>
  );
}
