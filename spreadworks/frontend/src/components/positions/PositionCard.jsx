import { useState, useEffect, useMemo } from 'react';
import { X, RotateCcw, Send, BarChart3 } from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || '';

const STRAT_LABELS = {
  double_diagonal: 'DD',
  double_calendar: 'DC',
  iron_condor: 'IC',
  butterfly: 'BF',
  iron_butterfly: 'IBF',
};

const CREDIT_STRATEGIES = new Set(['iron_condor', 'iron_butterfly']);

export default function PositionCard({ position, onClose, onDelete }) {
  const [pnl, setPnl] = useState(null);
  const [discordPushing, setDiscordPushing] = useState(false);
  const [discordDone, setDiscordDone] = useState(false);
  const [showChart, setShowChart] = useState(false);
  const [payoff, setPayoff] = useState(null);
  const [payoffLoading, setPayoffLoading] = useState(false);

  const isOpen = position.status === 'open';
  const strat = STRAT_LABELS[position.strategy] || position.strategy;

  useEffect(() => {
    if (!isOpen) return;
    const fetchPnl = async () => {
      try {
        const res = await fetch(`${API_URL}/api/spreadworks/positions/${position.id}/pnl`);
        if (res.ok) setPnl(await res.json());
      } catch { /* silent */ }
    };
    fetchPnl();
    const iv = setInterval(fetchPnl, 60000);
    return () => clearInterval(iv);
  }, [position.id, isOpen]);

  const pushToDiscord = async () => {
    setDiscordPushing(true);
    try {
      const res = await fetch(`${API_URL}/api/spreadworks/discord/push-position/${position.id}`, { method: 'POST' });
      if (res.ok) {
        setDiscordDone(true);
        setTimeout(() => setDiscordDone(false), 3000);
      }
    } catch { /* silent */ }
    setDiscordPushing(false);
  };

  const toggleChart = async () => {
    if (showChart) {
      setShowChart(false);
      return;
    }
    setShowChart(true);
    if (!payoff) {
      setPayoffLoading(true);
      try {
        const res = await fetch(`${API_URL}/api/spreadworks/positions/${position.id}/payoff`);
        if (res.ok) setPayoff(await res.json());
      } catch { /* silent */ }
      setPayoffLoading(false);
    }
  };

  const unrealized = pnl?.unrealized_pnl ?? 0;
  const currentValue = pnl?.current_value;
  const pnlPct = pnl?.pnl_pct ?? 0;
  const displayPnl = isOpen ? unrealized : (position.realized_pnl || 0);

  const borderColor = position.status === 'closed'
    ? 'border-border-subtle'
    : displayPnl > 0 ? 'border-sw-green/15' : displayPnl < 0 ? 'border-sw-red/15' : 'border-border-subtle';

  return (
    <div className={`sw-card p-4 ${borderColor} ${position.status === 'closed' ? 'opacity-65' : ''}`}>
      {/* Header */}
      <div className="flex justify-between items-center mb-3">
        <div>
          <span className="text-white font-bold text-sm">{position.label || `#${position.id}`}</span>
          <span className="text-text-tertiary text-[11px] ml-2 font-medium">{strat}</span>
        </div>
        <div className="flex gap-1.5 items-center">
          {position.dte != null && (
            <span className="sw-badge">{position.dte}DTE</span>
          )}
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider ${
            isOpen ? 'bg-sw-green/10 text-sw-green border border-sw-green/20' : 'bg-bg-elevated/30 text-text-tertiary border border-border-subtle'
          }`}>
            {isOpen ? 'OPEN' : 'CLOSED'}
          </span>
        </div>
      </div>

      {/* Strike Chips */}
      <div className="flex gap-1.5 mb-2.5 flex-wrap">
        <span className="text-[11px] px-2.5 py-0.5 rounded-md font-semibold font-[var(--font-mono)] bg-sw-green-dim border border-sw-green/20 text-sw-green">LP {position.long_put}</span>
        <span className="text-[11px] px-2.5 py-0.5 rounded-md font-semibold font-[var(--font-mono)] bg-sw-red-dim border border-sw-red/20 text-sw-red">SP {position.short_put}</span>
        <span className="text-[11px] px-2.5 py-0.5 rounded-md font-semibold font-[var(--font-mono)] bg-sw-red-dim border border-sw-red/20 text-sw-red">SC {position.short_call}</span>
        <span className="text-[11px] px-2.5 py-0.5 rounded-md font-semibold font-[var(--font-mono)] bg-sw-green-dim border border-sw-green/20 text-sw-green">LC {position.long_call}</span>
      </div>

      {/* Expirations */}
      <div className="text-[11px] text-text-tertiary mb-2.5 font-medium">
        Short: {position.short_exp}
        {position.long_exp && ` | Long: ${position.long_exp}`}
      </div>

      {/* 7 Metrics */}
      <div className="grid grid-cols-2 gap-x-5 gap-y-1 mb-3">
        <div className="flex justify-between py-1 text-xs">
          <span className="text-text-tertiary font-medium">
            {CREDIT_STRATEGIES.has(position.strategy) ? 'Entry Credit' : 'Entry Debit'}
          </span>
          <span className={`font-semibold font-[var(--font-mono)] ${CREDIT_STRATEGIES.has(position.strategy) ? 'text-sw-green' : 'text-sw-red'}`}>
            {CREDIT_STRATEGIES.has(position.strategy) ? '+' : '-'}${position.entry_credit?.toFixed(2)}
          </span>
        </div>
        <div className="flex justify-between py-1 text-xs">
          <span className="text-text-tertiary font-medium">Current Value</span>
          <span className="font-[var(--font-mono)]">{currentValue != null ? `$${currentValue.toFixed(4)}` : '\u2014'}</span>
        </div>
        <div className="flex justify-between py-1 text-xs">
          <span className="text-text-tertiary font-medium">P&L $</span>
          {isOpen ? (
            <span className={`font-bold font-[var(--font-mono)] ${unrealized >= 0 ? 'text-sw-green' : 'text-sw-red'}`}>
              ${unrealized >= 0 ? '+' : ''}{unrealized.toFixed(2)}
            </span>
          ) : (
            <span className={`font-bold font-[var(--font-mono)] ${(position.realized_pnl || 0) >= 0 ? 'text-sw-green' : 'text-sw-red'}`}>
              ${(position.realized_pnl || 0) >= 0 ? '+' : ''}{(position.realized_pnl || 0).toFixed(2)}
            </span>
          )}
        </div>
        <div className="flex justify-between py-1 text-xs">
          <span className="text-text-tertiary font-medium">P&L %</span>
          <span className={`font-bold font-[var(--font-mono)] ${displayPnl >= 0 ? 'text-sw-green' : 'text-sw-red'}`}>
            {isOpen
              ? `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%`
              : position.max_profit
                ? `${((position.realized_pnl || 0) / Math.abs(position.max_profit) * 100).toFixed(1)}%`
                : '\u2014'
            }
          </span>
        </div>
        <div className="flex justify-between py-1 text-xs">
          <span className="text-text-tertiary font-medium">Max Profit</span>
          <span className="font-[var(--font-mono)]">${position.max_profit != null ? position.max_profit.toFixed(2) : '\u2014'}</span>
        </div>
        <div className="flex justify-between py-1 text-xs">
          <span className="text-text-tertiary font-medium">Max Loss</span>
          <span className="text-sw-red font-[var(--font-mono)]">
            ${position.max_loss != null ? position.max_loss.toFixed(2) : '\u2014'}
          </span>
        </div>
        <div className="flex justify-between py-1 text-xs">
          <span className="text-text-tertiary font-medium">Contracts</span>
          <span className="font-[var(--font-mono)]">{position.contracts}</span>
        </div>
      </div>

      {/* Pricing source */}
      {isOpen && pnl?.pricing_source && (
        <div className="text-[10px] mb-2 flex items-center gap-1.5 font-medium"
          style={{ color: pnl.pricing_source === 'live_quotes' ? 'var(--color-sw-green)' : 'var(--color-text-secondary)' }}>
          <span className="w-1.5 h-1.5 rounded-full inline-block"
            style={{
              background: pnl.pricing_source === 'live_quotes' ? 'var(--color-sw-green)'
                : pnl.pricing_source === 'black_scholes_live_iv' ? '#ffb300'
                : 'var(--color-sw-red)',
            }} />
          {pnl.pricing_source === 'live_quotes'
            ? 'P&L from live Tradier bid/ask'
            : pnl.pricing_source === 'black_scholes_live_iv'
              ? 'P&L estimated (BS + live IV)'
              : 'P&L estimated (BS model — market closed)'}
        </div>
      )}

      {/* Notes */}
      {position.notes && (
        <div className="text-[11px] text-text-tertiary italic mb-2">
          {position.notes}
        </div>
      )}

      {/* Date info */}
      <div className="text-[11px] text-text-muted font-medium">
        Opened {position.entry_date || '\u2014'}
        {position.close_date && ` \u2022 Closed ${position.close_date}`}
      </div>

      {/* Actions */}
      <div className="flex gap-1.5 mt-3 border-t border-border-subtle pt-2.5">
        {isOpen && (
          <>
            <button className="sw-btn-danger !px-3 !py-1.5 !text-[11px] flex items-center gap-1" onClick={() => onClose(position)}>
              <X size={11} /> Close
            </button>
            <button className="sw-btn-ghost !px-3 !py-1.5 !text-[11px]" onClick={() => onDelete(position.id)}>
              Delete
            </button>
            <button className="sw-btn-ghost !px-3 !py-1.5 !text-[11px] opacity-30 cursor-not-allowed" disabled title="Coming soon">
              <RotateCcw size={11} /> Roll
            </button>
          </>
        )}
        <button
          className="sw-btn-ghost !px-3 !py-1.5 !text-[11px] text-sw-purple flex items-center gap-1"
          onClick={pushToDiscord}
          disabled={discordPushing}
          title="Push to Discord"
        >
          {discordDone ? '\u2713 Sent' : discordPushing ? '...' : <><Send size={11} /> Discord</>}
        </button>
        <button
          className="sw-btn-ghost !px-3 !py-1.5 !text-[11px] text-accent flex items-center gap-1"
          onClick={toggleChart}
          title="View payoff chart"
        >
          {showChart ? <><X size={11} /> Chart</> : <><BarChart3 size={11} /> Chart</>}
        </button>
      </div>

      {/* Payoff Chart — SVG visualization untouched */}
      {showChart && (
        <div className="mt-2.5 border-t border-border-subtle pt-2.5 animate-fade-in">
          {payoffLoading ? (
            <div className="text-text-muted text-[11px] text-center py-4">
              Loading payoff...
            </div>
          ) : payoff?.pnl_curve ? (
            <MiniPayoff
              curve={payoff.pnl_curve}
              spotPrice={payoff.spot_price}
              breakevens={payoff.breakevens}
              maxProfit={payoff.max_profit}
              maxLoss={payoff.max_loss}
            />
          ) : (
            <div className="text-text-muted text-[11px] text-center py-4">
              Unable to load payoff data
            </div>
          )}
        </div>
      )}
    </div>
  );
}


/** Inline mini payoff chart rendered as SVG — visualization logic untouched. */
function MiniPayoff({ curve, spotPrice, breakevens, maxProfit, maxLoss }) {
  const svg = useMemo(() => {
    if (!curve || curve.length === 0) return null;

    const W = 320;
    const H = 160;
    const pad = { top: 14, right: 12, bottom: 24, left: 46 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    const prices = curve.map((p) => p.price);
    const pnls = curve.map((p) => p.pnl);
    const minP = Math.min(...prices);
    const maxP = Math.max(...prices);
    const minPnl = Math.min(...pnls, 0);
    const maxPnl = Math.max(...pnls, 0);
    const pnlRange = maxPnl - minPnl || 1;

    const xScale = (p) => pad.left + ((p - minP) / (maxP - minP)) * plotW;
    const yScale = (v) => pad.top + plotH - ((v - minPnl) / pnlRange) * plotH;

    const points = curve.map((p) => `${xScale(p.price).toFixed(1)},${yScale(p.pnl).toFixed(1)}`);
    const linePath = `M${points.join('L')}`;
    const zeroY = yScale(0);

    const profitPts = [];
    const lossPts = [];
    for (const p of curve) {
      const x = xScale(p.price);
      const y = yScale(p.pnl);
      if (p.pnl >= 0) profitPts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
      if (p.pnl <= 0) lossPts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }

    return { W, H, pad, plotW, plotH, linePath, zeroY, xScale, yScale, profitPts, lossPts, minP, maxP, minPnl, maxPnl };
  }, [curve]);

  if (!svg) return null;

  const profitFill = svg.profitPts.length > 1
    ? `M${svg.xScale(curve.find((p) => p.pnl >= 0)?.price ?? 0).toFixed(1)},${svg.zeroY} ${svg.profitPts.join(' ')} ${svg.xScale(curve.filter((p) => p.pnl >= 0).pop()?.price ?? 0).toFixed(1)},${svg.zeroY} Z`
    : null;

  const lossFill = svg.lossPts.length > 1
    ? `M${svg.xScale(curve.find((p) => p.pnl <= 0)?.price ?? 0).toFixed(1)},${svg.zeroY} ${svg.lossPts.join(' ')} ${svg.xScale(curve.filter((p) => p.pnl <= 0).pop()?.price ?? 0).toFixed(1)},${svg.zeroY} Z`
    : null;

  const xTicks = [];
  const xStep = (svg.maxP - svg.minP) / 4;
  for (let i = 0; i <= 4; i++) {
    const val = svg.minP + xStep * i;
    xTicks.push({ val, x: svg.xScale(val) });
  }

  const yTicks = [];
  const yStep = (svg.maxPnl - svg.minPnl) / 3;
  for (let i = 0; i <= 3; i++) {
    const val = svg.minPnl + yStep * i;
    yTicks.push({ val, y: svg.yScale(val) });
  }

  return (
    <svg viewBox={`0 0 ${svg.W} ${svg.H}`} style={{ width: '100%', maxHeight: 160 }}>
      {/* Zero line */}
      <line x1={svg.pad.left} y1={svg.zeroY} x2={svg.pad.left + svg.plotW} y2={svg.zeroY}
        stroke="#475569" strokeWidth="0.5" strokeDasharray="3,2" />

      {/* Fills */}
      {profitFill && <path d={profitFill} fill="rgba(34, 197, 94, 0.12)" />}
      {lossFill && <path d={lossFill} fill="rgba(239, 68, 68, 0.10)" />}

      {/* P&L line */}
      <path d={svg.linePath} fill="none" stroke="#448aff" strokeWidth="1.5" />

      {/* Spot price */}
      {spotPrice && spotPrice >= svg.minP && spotPrice <= svg.maxP && (
        <>
          <line x1={svg.xScale(spotPrice)} y1={svg.pad.top} x2={svg.xScale(spotPrice)} y2={svg.pad.top + svg.plotH}
            stroke="#facc15" strokeWidth="0.8" strokeDasharray="2,2" />
          <text x={svg.xScale(spotPrice)} y={svg.pad.top - 3} textAnchor="middle" fill="#facc15" fontSize="8"
            fontFamily="'JetBrains Mono', monospace">Spot</text>
        </>
      )}

      {/* Breakevens */}
      {breakevens?.lower && (
        <line x1={svg.xScale(breakevens.lower)} y1={svg.zeroY - 4} x2={svg.xScale(breakevens.lower)} y2={svg.zeroY + 4}
          stroke="#a78bfa" strokeWidth="1.5" />
      )}
      {breakevens?.upper && (
        <line x1={svg.xScale(breakevens.upper)} y1={svg.zeroY - 4} x2={svg.xScale(breakevens.upper)} y2={svg.zeroY + 4}
          stroke="#a78bfa" strokeWidth="1.5" />
      )}

      {/* Y-axis */}
      {yTicks.map((t, i) => (
        <g key={i}>
          <line x1={svg.pad.left - 3} y1={t.y} x2={svg.pad.left} y2={t.y} stroke="#444" />
          <text x={svg.pad.left - 5} y={t.y + 3} textAnchor="end" fill="#555" fontSize="8"
            fontFamily="'JetBrains Mono', monospace">${t.val.toFixed(0)}</text>
        </g>
      ))}

      {/* X-axis */}
      {xTicks.map((t, i) => (
        <g key={i}>
          <line x1={t.x} y1={svg.pad.top + svg.plotH} x2={t.x} y2={svg.pad.top + svg.plotH + 3} stroke="#444" />
          <text x={t.x} y={svg.pad.top + svg.plotH + 14} textAnchor="middle" fill="#555" fontSize="8"
            fontFamily="'JetBrains Mono', monospace">${t.val.toFixed(0)}</text>
        </g>
      ))}

      {/* Max profit / loss labels */}
      {maxProfit != null && (
        <text x={svg.pad.left + svg.plotW - 2} y={svg.pad.top + 10} textAnchor="end" fill="#22c55e" fontSize="8"
          fontFamily="'JetBrains Mono', monospace">Max +${maxProfit.toFixed(0)}</text>
      )}
      {maxLoss != null && (
        <text x={svg.pad.left + svg.plotW - 2} y={svg.pad.top + svg.plotH - 3} textAnchor="end" fill="#ef4444" fontSize="8"
          fontFamily="'JetBrains Mono', monospace">Max ${maxLoss.toFixed(0)}</text>
      )}

      {/* Border */}
      <rect x={svg.pad.left} y={svg.pad.top} width={svg.plotW} height={svg.plotH}
        fill="none" stroke="var(--color-border-subtle)" />
    </svg>
  );
}
