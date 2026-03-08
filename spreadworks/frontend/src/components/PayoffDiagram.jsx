import { useMemo } from 'react';

export default function PayoffDiagram({ pnlCurve, spotPrice, breakevens, height = 240 }) {
  const svg = useMemo(() => {
    if (!pnlCurve || pnlCurve.length === 0) return null;

    const W = 600;
    const H = height;
    const pad = { top: 20, right: 20, bottom: 30, left: 55 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    const prices = pnlCurve.map((p) => p.price);
    const pnls = pnlCurve.map((p) => p.pnl);
    const minP = Math.min(...prices);
    const maxP = Math.max(...prices);
    const minPnl = Math.min(...pnls, 0);
    const maxPnl = Math.max(...pnls, 0);
    const pnlRange = maxPnl - minPnl || 1;

    const xScale = (p) => pad.left + ((p - minP) / (maxP - minP)) * plotW;
    const yScale = (v) => pad.top + plotH - ((v - minPnl) / pnlRange) * plotH;

    // Build path
    const points = pnlCurve.map((p) => `${xScale(p.price).toFixed(1)},${yScale(p.pnl).toFixed(1)}`);
    const linePath = `M${points.join('L')}`;

    // Fill area: profit green, loss red
    const zeroY = yScale(0);
    const profitPath = [];
    const lossPath = [];

    for (let i = 0; i < pnlCurve.length; i++) {
      const x = xScale(pnlCurve[i].price);
      const y = yScale(pnlCurve[i].pnl);
      if (pnlCurve[i].pnl >= 0) {
        profitPath.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      }
      if (pnlCurve[i].pnl <= 0) {
        lossPath.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      }
    }

    // Y-axis ticks
    const yTicks = [];
    const step = pnlRange / 4;
    for (let i = 0; i <= 4; i++) {
      const val = minPnl + step * i;
      yTicks.push({ val, y: yScale(val) });
    }

    // X-axis ticks
    const xTicks = [];
    const xStep = (maxP - minP) / 5;
    for (let i = 0; i <= 5; i++) {
      const val = minP + xStep * i;
      xTicks.push({ val, x: xScale(val) });
    }

    return { W, H, pad, plotW, plotH, linePath, zeroY, yTicks, xTicks, xScale, yScale, profitPath, lossPath };
  }, [pnlCurve, height]);

  if (!svg) {
    return <p className="placeholder-text">Calculate a spread to see the payoff diagram.</p>;
  }

  return (
    <svg viewBox={`0 0 ${svg.W} ${svg.H}`} style={{ width: '100%', maxHeight: height }}>
      {/* Zero line */}
      <line
        x1={svg.pad.left}
        y1={svg.zeroY}
        x2={svg.pad.left + svg.plotW}
        y2={svg.zeroY}
        stroke="#475569"
        strokeWidth="1"
        strokeDasharray="4,3"
      />

      {/* Profit fill */}
      {svg.profitPath.length > 1 && (
        <polygon
          points={`${svg.xScale(pnlCurve.find((p) => p.pnl >= 0)?.price ?? 0).toFixed(1)},${svg.zeroY} ${svg.profitPath.join(' ')} ${svg.xScale(pnlCurve.filter((p) => p.pnl >= 0).pop()?.price ?? 0).toFixed(1)},${svg.zeroY}`}
          fill="rgba(34,197,94,0.15)"
        />
      )}

      {/* Loss fill */}
      {svg.lossPath.length > 1 && (
        <polygon
          points={`${svg.xScale(pnlCurve.find((p) => p.pnl <= 0)?.price ?? 0).toFixed(1)},${svg.zeroY} ${svg.lossPath.join(' ')} ${svg.xScale(pnlCurve.filter((p) => p.pnl <= 0).pop()?.price ?? 0).toFixed(1)},${svg.zeroY}`}
          fill="rgba(239,68,68,0.12)"
        />
      )}

      {/* P&L line */}
      <path d={svg.linePath} fill="none" stroke="#3b82f6" strokeWidth="2" />

      {/* Spot price vertical line */}
      {spotPrice && (
        <>
          <line
            x1={svg.xScale(spotPrice)}
            y1={svg.pad.top}
            x2={svg.xScale(spotPrice)}
            y2={svg.pad.top + svg.plotH}
            stroke="#facc15"
            strokeWidth="1"
            strokeDasharray="3,3"
          />
          <text
            x={svg.xScale(spotPrice)}
            y={svg.pad.top - 4}
            textAnchor="middle"
            fill="#facc15"
            fontSize="10"
          >
            Spot
          </text>
        </>
      )}

      {/* Breakeven markers */}
      {breakevens &&
        [breakevens.lower, breakevens.upper].filter(Boolean).map((be, i) => (
          <g key={i}>
            <line
              x1={svg.xScale(be)}
              y1={svg.zeroY - 6}
              x2={svg.xScale(be)}
              y2={svg.zeroY + 6}
              stroke="#a78bfa"
              strokeWidth="2"
            />
            <text
              x={svg.xScale(be)}
              y={svg.zeroY + 18}
              textAnchor="middle"
              fill="#a78bfa"
              fontSize="9"
            >
              BE {be}
            </text>
          </g>
        ))}

      {/* Y-axis */}
      {svg.yTicks.map((t, i) => (
        <g key={i}>
          <line
            x1={svg.pad.left - 4}
            y1={t.y}
            x2={svg.pad.left}
            y2={t.y}
            stroke="#64748b"
          />
          <text
            x={svg.pad.left - 8}
            y={t.y + 3}
            textAnchor="end"
            fill="#64748b"
            fontSize="9"
          >
            ${t.val.toFixed(0)}
          </text>
        </g>
      ))}

      {/* X-axis */}
      {svg.xTicks.map((t, i) => (
        <g key={i}>
          <line
            x1={t.x}
            y1={svg.pad.top + svg.plotH}
            x2={t.x}
            y2={svg.pad.top + svg.plotH + 4}
            stroke="#64748b"
          />
          <text
            x={t.x}
            y={svg.pad.top + svg.plotH + 16}
            textAnchor="middle"
            fill="#64748b"
            fontSize="9"
          >
            ${t.val.toFixed(0)}
          </text>
        </g>
      ))}

      {/* Border */}
      <rect
        x={svg.pad.left}
        y={svg.pad.top}
        width={svg.plotW}
        height={svg.plotH}
        fill="none"
        stroke="#334155"
      />
    </svg>
  );
}
