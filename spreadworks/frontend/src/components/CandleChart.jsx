import { useMemo } from 'react';
import { priceToY } from '../utils/priceScale';

/**
 * Pure SVG candlestick chart. Renders OHLCV bars, volume histogram,
 * strike lines, GEX lines, and current price marker.
 * Shares the same price scale with PayoffPanel via minPrice/maxPrice props.
 */
export default function CandleChart({
  candles,
  minPrice,
  maxPrice,
  height,
  strikes,
  gexData,
  spotPrice,
}) {
  const barCount = 80;
  const barWidth = 6;
  const barGap = 3;
  const leftPad = 52;
  const rightPad = 10;
  const topPad = 10;
  const bottomPad = 28;

  const chartData = useMemo(() => {
    if (!candles || candles.length === 0) return null;

    const visibleCandles = candles.slice(-barCount);
    const plotH = height - topPad - bottomPad;
    const plotW = visibleCandles.length * (barWidth + barGap);
    const totalW = leftPad + plotW + rightPad;
    const maxVol = Math.max(...visibleCandles.map(c => c.volume || 0), 1);

    const pToY = (p) => topPad + priceToY(p, minPrice, maxPrice, plotH);

    const bars = visibleCandles.map((c, i) => {
      const x = leftPad + i * (barWidth + barGap);
      const isUp = c.close >= c.open;
      const color = isUp ? '#26a69a' : '#ef5350';
      const bodyTop = pToY(Math.max(c.open, c.close));
      const bodyBottom = pToY(Math.min(c.open, c.close));
      const bodyHeight = Math.max(bodyBottom - bodyTop, 1);
      const wickTop = pToY(c.high);
      const wickBottom = pToY(c.low);
      const wickX = x + barWidth / 2;

      // Volume bar
      const volH = ((c.volume || 0) / maxVol) * 40;
      const volY = height - bottomPad - volH;

      return {
        x, bodyTop, bodyHeight, wickTop, wickBottom, wickX,
        color, volH, volY, volColor: isUp ? '#26a69a44' : '#ef535044',
        time: c.time,
      };
    });

    // Date labels (every ~20 bars)
    const dateLabels = [];
    for (let i = 0; i < visibleCandles.length; i += 20) {
      const c = visibleCandles[i];
      if (c && c.time) {
        const d = new Date(c.time);
        const label = `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
        dateLabels.push({ x: leftPad + i * (barWidth + barGap), label });
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

    return { bars, totalW, plotH, pToY, dateLabels, priceTicks };
  }, [candles, minPrice, maxPrice, height]);

  if (!chartData) {
    return (
      <div style={{
        flex: 3, display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#555', fontFamily: "'Courier New', monospace", fontSize: 12,
        background: '#080810',
      }}>
        No candle data available
      </div>
    );
  }

  const { bars, totalW, plotH, pToY, dateLabels, priceTicks } = chartData;

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

  const lastBarX = bars.length > 0 ? bars[bars.length - 1].x + barWidth / 2 : null;
  const spotY = spotPrice ? pToY(spotPrice) : null;

  return (
    <div style={{ flex: 3, overflow: 'hidden', background: '#080810' }}>
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${totalW} ${height}`}
        preserveAspectRatio="none"
        style={{ display: 'block' }}
      >
        {/* Grid lines */}
        {priceTicks.map((t, i) => (
          <g key={i}>
            <line x1={leftPad} y1={t.y} x2={totalW} y2={t.y} stroke="#1a1a2e" strokeWidth="0.5" />
            <text x={leftPad - 6} y={t.y + 3} textAnchor="end" fill="#555" fontSize="9" fontFamily="'Courier New', monospace">
              ${t.price}
            </text>
          </g>
        ))}

        {/* Strike lines (full width, dashed) */}
        {strikeLines.map((sl, i) => (
          <g key={`strike-${i}`}>
            <line x1={leftPad} y1={sl.y} x2={totalW} y2={sl.y} stroke={sl.color} strokeWidth="1" strokeDasharray={sl.dash} opacity="0.7" />
            <text x={leftPad + 4} y={sl.y - 3} fill={sl.color} fontSize="10" fontWeight="600" fontFamily="'Courier New', monospace">
              {sl.label}
            </text>
          </g>
        ))}

        {/* GEX lines */}
        {gexLines.map((gl, i) => (
          <g key={`gex-${i}`}>
            <line x1={leftPad} y1={gl.y} x2={totalW} y2={gl.y} stroke={gl.color} strokeWidth="1" strokeDasharray={gl.dash} opacity="0.5" />
            <text x={leftPad + 4} y={gl.y + 12} fill={gl.color} fontSize="9" fontFamily="'Courier New', monospace" opacity="0.7">
              {gl.label}
            </text>
          </g>
        ))}

        {/* Volume bars */}
        {bars.map((b, i) => (
          <rect key={`vol-${i}`} x={b.x} y={b.volY} width={barWidth} height={b.volH} fill={b.volColor} />
        ))}

        {/* Candlestick bars */}
        {bars.map((b, i) => (
          <g key={`candle-${i}`}>
            <line x1={b.wickX} y1={b.wickTop} x2={b.wickX} y2={b.wickBottom} stroke={b.color} strokeWidth="1" />
            <rect x={b.x} y={b.bodyTop} width={barWidth} height={b.bodyHeight} fill={b.color} />
          </g>
        ))}

        {/* Current price vertical dashed line at last candle */}
        {lastBarX != null && spotY != null && (
          <>
            <line x1={lastBarX} y1={topPad} x2={lastBarX} y2={height - bottomPad} stroke="#448aff" strokeWidth="1" strokeDasharray="3,3" opacity="0.6" />
            <rect x={totalW - rightPad - 56} y={spotY - 8} width={54} height={16} rx={3} fill="#448aff" />
            <text x={totalW - rightPad - 54 + 27} y={spotY + 3} textAnchor="middle" fill="#fff" fontSize="9" fontWeight="600" fontFamily="'Courier New', monospace">
              ${spotPrice?.toFixed(2)}
            </text>
          </>
        )}

        {/* Date labels */}
        {dateLabels.map((dl, i) => (
          <text key={`date-${i}`} x={dl.x} y={height - 6} fill="#555" fontSize="9" fontFamily="'Courier New', monospace">
            {dl.label}
          </text>
        ))}
      </svg>
    </div>
  );
}
