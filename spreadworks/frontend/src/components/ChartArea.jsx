import { useMemo } from 'react';
import CandleChart from './CandleChart';
import PayoffPanel from './PayoffPanel';
import { computePriceRange } from '../utils/priceScale';

/**
 * Container that renders CandleChart and PayoffPanel side-by-side
 * with a shared price scale (minPrice/maxPrice).
 */
export default function ChartArea({
  candles,
  spotPrice,
  gexData,
  strikes,
  calcResult,
  height = 500,
  rangePct = 2.2,
}) {
  // Compute shared price range from candles + strikes + GEX
  const { minPrice, maxPrice } = useMemo(() => {
    const base = computePriceRange(candles, strikes, gexData, 0.005);

    // If user set a range %, override based on spot price
    if (spotPrice && rangePct) {
      const rangeAmt = spotPrice * (rangePct / 100);
      const rMin = spotPrice - rangeAmt;
      const rMax = spotPrice + rangeAmt;
      return {
        minPrice: Math.min(base.minPrice, rMin),
        maxPrice: Math.max(base.maxPrice, rMax),
      };
    }

    return base;
  }, [candles, strikes, gexData, spotPrice, rangePct]);

  const breakevens = calcResult ? {
    lower: calcResult.lower_breakeven,
    upper: calcResult.upper_breakeven,
  } : null;

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <CandleChart
        candles={candles}
        minPrice={minPrice}
        maxPrice={maxPrice}
        height={height}
        strikes={strikes}
        gexData={gexData}
        spotPrice={spotPrice}
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
