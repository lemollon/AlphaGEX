import { useEffect, useMemo, useState } from 'react';
import { botApi } from '../../lib/botApi';

/**
 * Payoff chart for a single bot position (BREEZE / TIDE / DRIFT).
 * Lazy-fetches /api/spreadworks/bots/{bot}/positions/{pid}/payoff on first mount.
 * Renders pure SVG — no Recharts / Plotly so it stays out of the heavy chunks.
 */
export default function BotPayoffChart({ bot, positionId, contracts = 1, height = 180 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    botApi.positionPayoff(bot, positionId)
      .then(d => { if (alive) setData(d); })
      .catch(e => { if (alive) setError(e.message || 'failed'); });
    return () => { alive = false; };
  }, [bot, positionId]);

  const svg = useMemo(() => {
    if (!data || !data.pnl_curve || data.pnl_curve.length === 0) return null;
    const curve = data.pnl_curve;
    const W = 560;
    const H = height;
    const pad = { top: 14, right: 14, bottom: 28, left: 56 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    const prices = curve.map(p => p.price);
    const pnls = curve.map(p => p.pnl);
    const minP = Math.min(...prices);
    const maxP = Math.max(...prices);
    // Pad P&L range a touch so the line never touches the frame.
    const rawMinPnl = Math.min(...pnls, 0);
    const rawMaxPnl = Math.max(...pnls, 0);
    const span = Math.max(Math.abs(rawMinPnl), Math.abs(rawMaxPnl), 1);
    const minPnl = rawMinPnl - span * 0.08;
    const maxPnl = rawMaxPnl + span * 0.08;
    const pnlRange = maxPnl - minPnl || 1;

    const xScale = p => pad.left + ((p - minP) / (maxP - minP || 1)) * plotW;
    const yScale = v => pad.top + plotH - ((v - minPnl) / pnlRange) * plotH;

    // Build piecewise-linear (no smoothing — payoff has real kinks at strikes).
    const points = curve.map(p => `${xScale(p.price).toFixed(1)},${yScale(p.pnl).toFixed(1)}`);
    const linePath = `M${points.join('L')}`;
    const zeroY = yScale(0);

    // Profit/loss fills: render two separate polygons clipped to the zero line.
    const profitPts = [];
    const lossPts = [];
    for (const p of curve) {
      const x = xScale(p.price);
      if (p.pnl >= 0) profitPts.push({ x, y: yScale(p.pnl) });
      if (p.pnl <= 0) lossPts.push({ x, y: yScale(p.pnl) });
    }

    const buildArea = (pts) => {
      if (pts.length < 2) return null;
      const head = `${pts[0].x.toFixed(1)},${zeroY.toFixed(1)}`;
      const body = pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
      const tail = `${pts[pts.length - 1].x.toFixed(1)},${zeroY.toFixed(1)}`;
      return `M${head} L${body} L${tail} Z`;
    };
    const profitFill = buildArea(profitPts);
    const lossFill = buildArea(lossPts);

    const xTicks = [];
    for (let i = 0; i <= 5; i++) {
      const val = minP + ((maxP - minP) / 5) * i;
      xTicks.push({ val, x: xScale(val) });
    }
    const yTicks = [];
    for (let i = 0; i <= 4; i++) {
      const val = minPnl + (pnlRange / 4) * i;
      yTicks.push({ val, y: yScale(val) });
    }

    return {
      W, H, pad, plotW, plotH,
      linePath, profitFill, lossFill, zeroY,
      xScale, yScale, xTicks, yTicks,
      minP, maxP, minPnl, maxPnl,
    };
  }, [data, height]);

  if (error) {
    return (
      <div className="text-text-muted text-[11px] text-center py-3 italic">
        Payoff unavailable ({error})
      </div>
    );
  }
  if (!data) {
    return (
      <div className="text-text-muted text-[11px] text-center py-3 italic">
        Loading payoff…
      </div>
    );
  }
  if (!svg) {
    return (
      <div className="text-text-muted text-[11px] text-center py-3 italic">
        No curve data
      </div>
    );
  }

  const { breakevens, max_profit, max_loss } = data;

  return (
    <svg
      viewBox={`0 0 ${svg.W} ${svg.H}`}
      width="100%"
      preserveAspectRatio="xMidYMid meet"
      style={{ display: 'block', maxHeight: svg.H }}
    >
      <defs>
        <linearGradient id={`pgrad-${positionId}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#34d399" stopOpacity="0.32" />
          <stop offset="100%" stopColor="#34d399" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id={`lgrad-${positionId}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#fb7185" stopOpacity="0.02" />
          <stop offset="100%" stopColor="#fb7185" stopOpacity="0.32" />
        </linearGradient>
      </defs>

      {/* Plot frame */}
      <rect
        x={svg.pad.left} y={svg.pad.top}
        width={svg.plotW} height={svg.plotH}
        fill="rgba(15,23,42,0.30)"
        stroke="rgba(125,211,252,0.10)" strokeWidth="0.5"
      />

      {/* Y-axis grid */}
      {svg.yTicks.map((t, i) => (
        <g key={`y${i}`}>
          <line
            x1={svg.pad.left} y1={t.y}
            x2={svg.pad.left + svg.plotW} y2={t.y}
            stroke="rgba(125,211,252,0.05)" strokeWidth="0.5"
          />
          <text
            x={svg.pad.left - 6} y={t.y + 3}
            textAnchor="end" fill="#64748b" fontSize="9"
            fontFamily="'JetBrains Mono', monospace"
          >
            {t.val >= 0 ? '+' : ''}${Math.round(t.val)}
          </text>
        </g>
      ))}

      {/* X-axis grid + ticks */}
      {svg.xTicks.map((t, i) => (
        <g key={`x${i}`}>
          <line
            x1={t.x} y1={svg.pad.top}
            x2={t.x} y2={svg.pad.top + svg.plotH}
            stroke="rgba(125,211,252,0.04)" strokeWidth="0.5"
          />
          <text
            x={t.x} y={svg.pad.top + svg.plotH + 14}
            textAnchor="middle" fill="#64748b" fontSize="9"
            fontFamily="'JetBrains Mono', monospace"
          >
            ${t.val.toFixed(0)}
          </text>
        </g>
      ))}

      {/* Fills */}
      {svg.profitFill && (
        <path d={svg.profitFill} fill={`url(#pgrad-${positionId})`} />
      )}
      {svg.lossFill && (
        <path d={svg.lossFill} fill={`url(#lgrad-${positionId})`} />
      )}

      {/* Zero line */}
      <line
        x1={svg.pad.left} y1={svg.zeroY}
        x2={svg.pad.left + svg.plotW} y2={svg.zeroY}
        stroke="#475569" strokeWidth="0.8" strokeDasharray="4,3"
      />

      {/* P&L curve */}
      <path d={svg.linePath} fill="none" stroke="#7dd3fc" strokeWidth="1.6" />

      {/* Breakevens */}
      {breakevens?.lower != null && breakevens.lower >= svg.minP && breakevens.lower <= svg.maxP && (
        <g>
          <line
            x1={svg.xScale(breakevens.lower)} y1={svg.pad.top}
            x2={svg.xScale(breakevens.lower)} y2={svg.pad.top + svg.plotH}
            stroke="#a78bfa" strokeWidth="0.8" strokeDasharray="3,2"
          />
          <text
            x={svg.xScale(breakevens.lower)} y={svg.pad.top - 3}
            textAnchor="middle" fill="#a78bfa" fontSize="8"
            fontFamily="'JetBrains Mono', monospace"
          >
            BE ${breakevens.lower.toFixed(0)}
          </text>
        </g>
      )}
      {breakevens?.upper != null && breakevens.upper >= svg.minP && breakevens.upper <= svg.maxP && (
        <g>
          <line
            x1={svg.xScale(breakevens.upper)} y1={svg.pad.top}
            x2={svg.xScale(breakevens.upper)} y2={svg.pad.top + svg.plotH}
            stroke="#a78bfa" strokeWidth="0.8" strokeDasharray="3,2"
          />
          <text
            x={svg.xScale(breakevens.upper)} y={svg.pad.top - 3}
            textAnchor="middle" fill="#a78bfa" fontSize="8"
            fontFamily="'JetBrains Mono', monospace"
          >
            BE ${breakevens.upper.toFixed(0)}
          </text>
        </g>
      )}

      {/* Max profit / loss corner labels */}
      {max_profit != null && (
        <text
          x={svg.pad.left + svg.plotW - 4} y={svg.pad.top + 11}
          textAnchor="end" fill="#34d399" fontSize="9"
          fontFamily="'JetBrains Mono', monospace" fontWeight="700"
        >
          Max +${Math.round(max_profit)}
        </text>
      )}
      {max_loss != null && (
        <text
          x={svg.pad.left + svg.plotW - 4} y={svg.pad.top + svg.plotH - 4}
          textAnchor="end" fill="#fb7185" fontSize="9"
          fontFamily="'JetBrains Mono', monospace" fontWeight="700"
        >
          Max ${Math.round(max_loss)}
        </text>
      )}
    </svg>
  );
}
