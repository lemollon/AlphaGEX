import { useMemo } from 'react';
import { priceToY } from '../utils/priceScale';

/**
 * Pure SVG candlestick chart. Renders OHLCV bars, volume histogram,
 * strike lines, GEX lines, and current price marker.
 * Shares the same price scale with PayoffPanel via minPrice/maxPrice props.
 *
 * Layout constants:
 *   CHART_LEFT_MARGIN (50px) — price axis labels
 *   CHART_RIGHT_MARGIN (80px) — always empty, separates candles from payoff panel
 *   CANDLE_SPACING (9px) — center-to-center distance between candles
 *
 * If more candles than fit, older ones are clipped on the LEFT — never the right.
 * The 80px right margin zone is always clean: no candle body, wick, volume bar,
 * or date label enters it. Only the current-price dashed vertical line and
 * $XXX.XX badge sit in that zone.
 */

const CHART_LEFT_MARGIN = 50;
const CHART_RIGHT_MARGIN = 80; // always empty — separates candles from payoff panel
const CANDLE_SPACING = 9;
const BAR_WIDTH = 6;
const TOP_PAD = 10;
const BOTTOM_PAD = 28;

export default function CandleChart({
  candles,
  minPrice,
  maxPrice,
  height,
  strikes,
  gexData,
  spotPrice,
}) {
  const chartData = useMemo(() => {
    if (!candles || candles.length === 0) return null;

    // Fixed SVG width — viewBox controls scaling
    const svgWidth = 900;
    const availableWidth = svgWidth - CHART_LEFT_MARGIN - CHART_RIGHT_MARGIN;
    const maxCandles = Math.floor(availableWidth / CANDLE_SPACING);

    // Clip older candles on the left if there are more than fit
    const visibleCandles = candles.slice(-maxCandles);

    const plotH = height - TOP_PAD - BOTTOM_PAD;
    const maxVol = Math.max(...visibleCandles.map(c => c.volume || 0), 1);

    const pToY = (p) => TOP_PAD + priceToY(p, minPrice, maxPrice, plotH);

    // Last candle X — this is where the candle zone ends
    const lastCandleX = CHART_LEFT_MARGIN + (visibleCandles.length - 1) * CANDLE_SPACING;

    const bars = visibleCandles.map((c, i) => {
      const x = CHART_LEFT_MARGIN + i * CANDLE_SPACING - BAR_WIDTH / 2;
      const centerX = CHART_LEFT_MARGIN + i * CANDLE_SPACING;
      const isUp = c.close >= c.open;
      const color = isUp ? '#26a69a' : '#ef5350';
      const bodyTop = pToY(Math.max(c.open, c.close));
      const bodyBottom = pToY(Math.min(c.open, c.close));
      const bodyHeight = Math.max(bodyBottom - bodyTop, 1);
      const wickTop = pToY(c.high);
      const wickBottom = pToY(c.low);

      // Volume bar
      const volH = ((c.volume || 0) / maxVol) * 40;
      const volY = height - BOTTOM_PAD - volH;

      return {
        x, centerX, bodyTop, bodyHeight, wickTop, wickBottom,
        color, volH, volY, volColor: isUp ? '#26a69a44' : '#ef535044',
        time: c.time,
      };
    });

    // Date labels (every ~20 bars) — must not enter the right margin zone
    const dateLabels = [];
    for (let i = 0; i < visibleCandles.length; i += 20) {
      const c = visibleCandles[i];
      const labelX = CHART_LEFT_MARGIN + i * CANDLE_SPACING;
      if (c && c.time && labelX < svgWidth - CHART_RIGHT_MARGIN) {
        const d = new Date(c.time);
        const label = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        dateLabels.push({ x: labelX, label });
      }
    }

    // Price axis ticks
    const priceTicks = [];
    const range = maxPrice - minPrice;
    const step = range > 30 ? 5 : range > 15 ? 2 : 1;
    const startP = Math.ceil(minPrice / step) * step;
    for (let p = startP; p <= maxPrice; p += step) {
      priceTicks.push({ price: p, y: pToY(p) });
    }

    return { bars, svgWidth, plotH, pToY, dateLabels, priceTicks, lastCandleX };
  }, [candles, minPrice, maxPrice, height]);

  if (!chartData) {
    return (
      <div style={{
        flex: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        color: '#555', fontFamily: "'Courier New', monospace", fontSize: 12,
        background: '#080810', gap: 6,
      }}>
        <span>No candle data available</span>
        <span style={{ fontSize: 10, color: '#444' }}>
          Load SpreadWorks during market hours to populate the cache for offline use.
        </span>
      </div>
    );
  }

  const { bars, svgWidth, plotH, pToY, dateLabels, priceTicks, lastCandleX } = chartData;

  // Candle zone boundary — strike/GEX lines extend to here, not into right margin
  const candleZoneRight = svgWidth - CHART_RIGHT_MARGIN;

  // Strike overlay lines
  const strikeLines = [];
  if (strikes) {
    const longPrices = [strikes.longPutStrike, strikes.longCallStrike].filter(Boolean).map(Number);
    const shortPrices = [strikes.shortPutStrike, strikes.shortCallStrike].filter(Boolean).map(Number);
    longPrices.forEach(p => {
      if (p >= minPrice && p <= maxPrice) {
        strikeLines.push({ price: p, y: pToY(p), color: '#00e676', dash: '5,4', label: `$${p}` });
      }
    });
    shortPrices.forEach(p => {
      if (p >= minPrice && p <= maxPrice) {
        strikeLines.push({ price: p, y: pToY(p), color: '#ff5252', dash: '5,4', label: `$${p}` });
      }
    });
  }

  // GEX overlay lines
  const gexLines = [];
  if (gexData) {
    if (gexData.flip_point && gexData.flip_point >= minPrice && gexData.flip_point <= maxPrice) {
      gexLines.push({ y: pToY(gexData.flip_point), color: '#ffd600', dash: '7,5', label: `$${gexData.flip_point.toFixed(0)}` });
    }
    if (gexData.call_wall && gexData.call_wall >= minPrice && gexData.call_wall <= maxPrice) {
      gexLines.push({ y: pToY(gexData.call_wall), color: '#00bcd4', dash: '7,5', label: `$${gexData.call_wall.toFixed(0)}` });
    }
    if (gexData.put_wall && gexData.put_wall >= minPrice && gexData.put_wall <= maxPrice) {
      gexLines.push({ y: pToY(gexData.put_wall), color: '#c855ff', dash: '7,5', label: `$${gexData.put_wall.toFixed(0)}` });
    }
  }

  const spotY = spotPrice ? pToY(spotPrice) : null;

  return (
    <div style={{ flex: 3, overflow: 'hidden', background: '#080810' }}>
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${svgWidth} ${height}`}
        preserveAspectRatio="none"
        style={{ display: 'block' }}
      >
        {/* Grid lines — span full width including right margin for visual continuity */}
        {priceTicks.map((t, i) => (
          <g key={i}>
            <line x1={CHART_LEFT_MARGIN} y1={t.y} x2={svgWidth} y2={t.y} stroke="#1a1a2e" strokeWidth="0.5" />
            <text x={CHART_LEFT_MARGIN - 6} y={t.y + 3} textAnchor="end" fill="#555" fontSize="9" fontFamily="'Courier New', monospace">
              ${t.price}
            </text>
          </g>
        ))}

        {/* Strike lines — span to candle zone edge, then through right margin */}
        {strikeLines.map((sl, i) => (
          <g key={`strike-${i}`}>
            <line x1={CHART_LEFT_MARGIN} y1={sl.y} x2={svgWidth} y2={sl.y} stroke={sl.color} strokeWidth="1" strokeDasharray={sl.dash} opacity="0.7" />
            <text x={CHART_LEFT_MARGIN + 4} y={sl.y - 3} fill={sl.color} fontSize="10" fontWeight="600" fontFamily="'Courier New', monospace">
              {sl.label}
            </text>
          </g>
        ))}

        {/* GEX lines */}
        {gexLines.map((gl, i) => (
          <g key={`gex-${i}`}>
            <line x1={CHART_LEFT_MARGIN} y1={gl.y} x2={svgWidth} y2={gl.y} stroke={gl.color} strokeWidth="1" strokeDasharray={gl.dash} opacity="0.5" />
            <text x={CHART_LEFT_MARGIN + 4} y={gl.y + 12} fill={gl.color} fontSize="9" fontFamily="'Courier New', monospace" opacity="0.7">
              {gl.label}
            </text>
          </g>
        ))}

        {/* Volume bars — within candle zone only */}
        {bars.map((b, i) => (
          <rect key={`vol-${i}`} x={b.x} y={b.volY} width={BAR_WIDTH} height={b.volH} fill={b.volColor} />
        ))}

        {/* Candlestick bars — within candle zone only */}
        {bars.map((b, i) => (
          <g key={`candle-${i}`}>
            <line x1={b.centerX} y1={b.wickTop} x2={b.centerX} y2={b.wickBottom} stroke={b.color} strokeWidth="1" />
            <rect x={b.x} y={b.bodyTop} width={BAR_WIDTH} height={b.bodyHeight} fill={b.color} />
          </g>
        ))}

        {/* Current price dashed vertical line — sits at lastCandleX in the margin zone */}
        {lastCandleX != null && spotY != null && (
          <>
            <line x1={lastCandleX} y1={TOP_PAD} x2={lastCandleX} y2={height - BOTTOM_PAD} stroke="#448aff" strokeWidth="1" strokeDasharray="3,3" opacity="0.6" />
            {/* Price badge — positioned in the right margin zone */}
            <rect x={svgWidth - CHART_RIGHT_MARGIN + 8} y={spotY - 8} width={60} height={16} rx={3} fill="#448aff" />
            <text x={svgWidth - CHART_RIGHT_MARGIN + 38} y={spotY + 3} textAnchor="middle" fill="#fff" fontSize="9" fontWeight="600" fontFamily="'Courier New', monospace">
              ${spotPrice?.toFixed(2)}
            </text>
          </>
        )}

        {/* Date labels — within candle zone only */}
        {dateLabels.map((dl, i) => (
          <text key={`date-${i}`} x={dl.x} y={height - 6} fill="#555" fontSize="9" fontFamily="'Courier New', monospace">
            {dl.label}
          </text>
        ))}
      </svg>
    </div>
  );
}
