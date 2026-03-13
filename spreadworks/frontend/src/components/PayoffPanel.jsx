import { useMemo } from 'react';
import { priceToY } from '../utils/priceScale';
import { pnlCurveToPoints, buildSmoothPath, buildFillPath, splitProfitLoss } from '../utils/payoffShape';
import { formatDollarPnl, formatSignedPct } from '../utils/format';

const VIEW_WIDTH = 280;
const ZERO_X = 220;

/**
 * Sideways payoff diagram panel.
 * Y-axis = price (shared with candle chart)
 * X-axis = P&L (zero line at X=220, profit grows left, loss grows right)
 */
export default function PayoffPanel({
  pnlCurve,
  minPrice,
  maxPrice,
  height,
  strikes,
  spotPrice,
  maxProfit,
  maxLoss,
  breakevens,
}) {
  const plotH = height - 10 - 28; // match candle chart top/bottom padding
  const topPad = 10;

  const pToY = (p) => topPad + priceToY(p, minPrice, maxPrice, plotH);

  const paths = useMemo(() => {
    if (!pnlCurve || pnlCurve.length === 0) return null;

    const maxAbsPnl = Math.max(
      Math.abs(maxProfit || 0),
      Math.abs(maxLoss || 0),
      Math.max(...pnlCurve.map(p => Math.abs(p.pnl)), 1)
    );

    const points = pnlCurveToPoints(pnlCurve, pToY, maxAbsPnl, VIEW_WIDTH, ZERO_X);
    if (points.length < 2) return null;

    const { profitPoints, lossPoints } = splitProfitLoss(points, ZERO_X);
    const mainPath = buildSmoothPath(points);
    const profitFill = profitPoints.length >= 2 ? buildFillPath(profitPoints, ZERO_X) : '';
    const lossFill = lossPoints.length >= 2 ? buildFillPath(lossPoints, ZERO_X) : '';

    return { mainPath, profitFill, lossFill, points };
  }, [pnlCurve, minPrice, maxPrice, height, maxProfit, maxLoss]);

  // Strike lines that continue from candle chart
  const strikeLines = useMemo(() => {
    const lines = [];
    if (!strikes) return lines;
    const longPrices = [strikes.longPutStrike, strikes.longCallStrike].filter(Boolean).map(Number);
    const shortPrices = [strikes.shortPutStrike, strikes.shortCallStrike].filter(Boolean).map(Number);
    longPrices.forEach(p => {
      if (p >= minPrice && p <= maxPrice) {
        lines.push({ y: pToY(p), color: '#22c55e', dash: '5,4', label: `$${p}` });
      }
    });
    shortPrices.forEach(p => {
      if (p >= minPrice && p <= maxPrice) {
        lines.push({ y: pToY(p), color: '#ef4444', dash: '5,4' });
      }
    });
    return lines;
  }, [strikes, minPrice, maxPrice, height]);

  const spotY = spotPrice ? pToY(spotPrice) : null;

  // Price axis ticks (same as candle chart)
  const range = maxPrice - minPrice;
  const step = range > 30 ? 5 : range > 15 ? 2 : 1;
  const startP = Math.ceil(minPrice / step) * step;
  const priceTicks = [];
  for (let p = startP; p <= maxPrice; p += step) {
    priceTicks.push({ price: p, y: pToY(p) });
  }

  return (
    <div className="w-[220px] min-w-[220px] bg-bg-base border-l border-border-subtle relative">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${VIEW_WIDTH} ${height}`}
        preserveAspectRatio="none"
        style={{ display: 'block' }}
      >
        <defs>
          <linearGradient id="profitGrad" x1="1" y1="0" x2="0" y2="0">
            <stop offset="0%" stopColor="#22c55e" stopOpacity="0" />
            <stop offset="100%" stopColor="#22c55e" stopOpacity="0.5" />
          </linearGradient>
          <linearGradient id="lossGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#ef4444" stopOpacity="0" />
            <stop offset="100%" stopColor="#ef4444" stopOpacity="0.5" />
          </linearGradient>
        </defs>

        {/* Grid lines matching candle chart */}
        {priceTicks.map((t, i) => (
          <line key={i} x1={0} y1={t.y} x2={VIEW_WIDTH} y2={t.y} stroke="#1a1a2e" strokeWidth="0.5" />
        ))}

        {/* Zero line */}
        <line x1={ZERO_X} y1={topPad} x2={ZERO_X} y2={height - 28} stroke="#1a1a2e" strokeWidth="1" />

        {/* Strike lines continue */}
        {strikeLines.map((sl, i) => (
          <line key={i} x1={0} y1={sl.y} x2={VIEW_WIDTH} y2={sl.y} stroke={sl.color} strokeWidth="1" strokeDasharray={sl.dash} opacity="0.4" />
        ))}

        {/* Payoff shape */}
        {paths && (
          <>
            {paths.profitFill && (
              <path d={paths.profitFill} fill="url(#profitGrad)" />
            )}
            {paths.lossFill && (
              <path d={paths.lossFill} fill="url(#lossGrad)" />
            )}
            <path d={paths.mainPath} fill="none" stroke="#22c55e" strokeWidth="2.5" />
          </>
        )}

        {/* Spot price horizontal line */}
        {spotY != null && (
          <>
            <line x1={0} y1={spotY} x2={VIEW_WIDTH} y2={spotY} stroke="#f59e0b" strokeWidth="1" strokeDasharray="3,3" opacity="0.5" />
            <rect x={VIEW_WIDTH - 48} y={spotY - 8} width={46} height={16} rx={3} fill="rgba(245, 158, 11, 0.13)" stroke="#f59e0b" strokeWidth="0.5" />
            <text x={VIEW_WIDTH - 25} y={spotY + 3} textAnchor="middle" fill="#f59e0b" fontSize="8" fontFamily="'Courier New', monospace">
              ${spotPrice?.toFixed(0)}
            </text>
          </>
        )}

        {/* Breakeven markers */}
        {breakevens && breakevens.lower && (
          <g>
            <line x1={ZERO_X - 10} y1={pToY(breakevens.lower)} x2={ZERO_X + 10} y2={pToY(breakevens.lower)} stroke="#ffd600" strokeWidth="2" />
            <text x={ZERO_X - 14} y={pToY(breakevens.lower) + 3} textAnchor="end" fill="#ffd600" fontSize="8" fontFamily="'Courier New', monospace">BE</text>
          </g>
        )}
        {breakevens && breakevens.upper && (
          <g>
            <line x1={ZERO_X - 10} y1={pToY(breakevens.upper)} x2={ZERO_X + 10} y2={pToY(breakevens.upper)} stroke="#ffd600" strokeWidth="2" />
            <text x={ZERO_X - 14} y={pToY(breakevens.upper) + 3} textAnchor="end" fill="#ffd600" fontSize="8" fontFamily="'Courier New', monospace">BE</text>
          </g>
        )}

        {/* Current P&L badge at spot price */}
        {paths && spotY != null && spotPrice && pnlCurve && pnlCurve.length > 0 && (() => {
          let pnlAtSpot = null;
          for (let i = 0; i < pnlCurve.length - 1; i++) {
            const a = pnlCurve[i], b = pnlCurve[i + 1];
            if ((a.price <= spotPrice && b.price >= spotPrice) || (a.price >= spotPrice && b.price <= spotPrice)) {
              const t = (spotPrice - a.price) / (b.price - a.price || 1);
              pnlAtSpot = a.pnl + t * (b.pnl - a.pnl);
              break;
            }
          }
          if (pnlAtSpot == null) return null;

          const maxRisk = Math.abs(maxLoss || 1);
          const pctOfRisk = maxRisk > 0 ? (pnlAtSpot / maxRisk) * 100 : 0;
          const isProfit = pnlAtSpot > 0;
          const nearBreakeven = Math.abs(pctOfRisk) < 10;
          const badgeColor = nearBreakeven ? '#ffd600' : isProfit ? '#22c55e' : '#ef4444';
          const bgColor = nearBreakeven ? '#ffd60022' : isProfit ? '#22c55e22' : '#ef444422';

          const label = `Now: ${formatDollarPnl(pnlAtSpot)} (${formatSignedPct(pctOfRisk)})`;

          const badgeW = 140;
          const badgeH = 18;
          const rawX = 4;
          let badgeY = spotY - badgeH / 2;
          badgeY = Math.max(10, Math.min(badgeY, height - 28 - badgeH));

          return (
            <g>
              <rect x={rawX} y={badgeY} width={badgeW} height={badgeH} rx={3}
                fill={bgColor} stroke={badgeColor} strokeWidth="0.8" />
              <text x={rawX + badgeW / 2} y={badgeY + 12} textAnchor="middle"
                fill={badgeColor} fontSize="9" fontWeight="700" fontFamily="'Courier New', monospace">
                {label}
              </text>
            </g>
          );
        })()}

        {/* No data placeholder */}
        {!paths && (
          <text x={VIEW_WIDTH / 2} y={height / 2} textAnchor="middle" fill="#333" fontSize="11" fontFamily="'Courier New', monospace">
            Calculate to see payoff
          </text>
        )}

        {/* Strike labels on right edge */}
        {strikeLines.map((sl, i) => (
          <text key={`label-${i}`} x={VIEW_WIDTH - 4} y={sl.y + 3} textAnchor="end" fill={sl.color} fontSize="8" fontFamily="'Courier New', monospace" opacity="0.8">
            {sl.label}
          </text>
        ))}
      </svg>
    </div>
  );
}
