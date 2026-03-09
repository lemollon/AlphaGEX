/**
 * Build SVG path data from a pnl_curve array for the payoff panel.
 *
 * Payoff panel is oriented sideways:
 *   Y-axis = price (shared with candle chart)
 *   X-axis = P&L magnitude
 *   Zero line at X=220 (right edge, touching candle chart divider)
 *   Profit grows LEFT from X=220
 *   Loss grows RIGHT from X=220
 */

/**
 * Convert pnl_curve [{price, pnl}] to SVG points for the payoff panel.
 * @param {Array} pnlCurve - sorted by price ascending
 * @param {Function} priceToYFn - (price) => y coordinate
 * @param {number} maxAbsPnl - max absolute P&L for scaling
 * @param {number} viewWidth - viewBox width (280)
 * @param {number} zeroX - x position of the zero line (220)
 * @returns {Array} [{x, y, pnl}, ...]
 */
export function pnlCurveToPoints(pnlCurve, priceToYFn, maxAbsPnl, viewWidth = 280, zeroX = 220) {
  if (!pnlCurve || pnlCurve.length === 0) return [];
  const scale = maxAbsPnl > 0 ? 160 / maxAbsPnl : 1;

  return pnlCurve.map(({ price, pnl }) => {
    const y = priceToYFn(price);
    let x;
    if (pnl >= 0) {
      x = zeroX - pnl * scale; // profit grows left
      x = Math.max(x, 20);
    } else {
      x = zeroX + Math.abs(pnl) * scale; // loss grows right
      x = Math.min(x, viewWidth - 5);
    }
    return { x, y, pnl };
  });
}

/**
 * Build a smooth SVG path from points using Catmull-Rom → cubic bezier.
 * Returns the `d` attribute for an SVG <path>.
 */
export function buildSmoothPath(points) {
  if (points.length < 2) return '';
  if (points.length === 2) {
    return `M${points[0].x.toFixed(1)},${points[0].y.toFixed(1)} L${points[1].x.toFixed(1)},${points[1].y.toFixed(1)}`;
  }

  let d = `M${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}`;

  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(i - 1, 0)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(i + 2, points.length - 1)];

    const tension = 0.3;
    const cp1x = p1.x + (p2.x - p0.x) * tension;
    const cp1y = p1.y + (p2.y - p0.y) * tension;
    const cp2x = p2.x - (p3.x - p1.x) * tension;
    const cp2y = p2.y - (p3.y - p1.y) * tension;

    d += ` C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
  }

  return d;
}

/**
 * Build a closed fill path (for area fill) from points back to the zero line.
 */
export function buildFillPath(points, zeroX = 220) {
  if (points.length < 2) return '';
  const first = points[0];
  const last = points[points.length - 1];
  const curvePart = buildSmoothPath(points);
  return `${curvePart} L${zeroX},${last.y.toFixed(1)} L${zeroX},${first.y.toFixed(1)} Z`;
}

/**
 * Split points into profit segments and loss segments for separate fills.
 */
export function splitProfitLoss(points, zeroX = 220) {
  const profitPoints = [];
  const lossPoints = [];

  for (const pt of points) {
    if (pt.pnl >= 0) {
      profitPoints.push(pt);
    } else {
      lossPoints.push(pt);
    }
  }

  return { profitPoints, lossPoints };
}
