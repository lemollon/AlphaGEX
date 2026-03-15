import { useState, useEffect, useMemo } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '';

const STRAT_LABELS = {
  double_diagonal: 'DD',
  double_calendar: 'DC',
  iron_condor: 'IC',
};

const s = {
  card: (pnl, status) => ({
    background: 'var(--bg-card)',
    border: `1px solid ${status === 'closed' ? 'var(--border-subtle)' : pnl > 0 ? 'rgba(0, 230, 118, 0.15)' : pnl < 0 ? 'rgba(255, 82, 82, 0.15)' : 'var(--border-subtle)'}`,
    borderRadius: 'var(--radius-lg)',
    padding: '16px 18px',
    fontFamily: 'var(--font-ui)',
    fontSize: 13,
    color: 'var(--text-primary)',
    opacity: status === 'closed' ? 0.65 : 1,
    transition: 'border-color var(--transition-default), box-shadow var(--transition-default)',
  }),
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  title: { color: '#fff', fontWeight: 700, fontSize: 14 },
  badge: (color) => ({
    fontSize: 10,
    padding: '3px 8px',
    borderRadius: 20,
    background: color + '18',
    color: color,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  }),
  strikesRow: {
    display: 'flex',
    gap: 5,
    marginBottom: 10,
    flexWrap: 'wrap',
  },
  chip: (type) => ({
    fontSize: 11,
    padding: '3px 10px',
    borderRadius: 'var(--radius-sm)',
    fontWeight: 600,
    fontFamily: 'var(--font-mono)',
    background: type === 'long' ? 'var(--green-dim)' : 'var(--red-dim)',
    border: `1px solid ${type === 'long' ? 'rgba(0, 230, 118, 0.2)' : 'rgba(255, 82, 82, 0.2)'}`,
    color: type === 'long' ? 'var(--green)' : 'var(--red)',
  }),
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '3px 14px',
    marginBottom: 10,
  },
  metric: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '4px 0',
    fontSize: 12,
  },
  dim: { color: 'var(--text-tertiary)', fontWeight: 500 },
  pnl: (v) => ({
    fontWeight: 700,
    fontFamily: 'var(--font-mono)',
    color: v >= 0 ? 'var(--green)' : 'var(--red)',
  }),
  actions: {
    display: 'flex',
    gap: 6,
    marginTop: 12,
    borderTop: '1px solid var(--border-subtle)',
    paddingTop: 10,
  },
  btn: (color) => ({
    padding: '5px 12px',
    border: `1px solid ${color}33`,
    borderRadius: 'var(--radius-sm)',
    background: 'transparent',
    color: color,
    fontSize: 11,
    fontFamily: 'var(--font-ui)',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  }),
  btnDisabled: {
    opacity: 0.3,
    cursor: 'not-allowed',
  },
  expRow: {
    fontSize: 11,
    color: 'var(--text-tertiary)',
    marginBottom: 10,
    fontWeight: 500,
  },
};

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

  return (
    <div style={s.card(isOpen ? unrealized : (position.realized_pnl || 0), position.status)}>
      {/* Header */}
      <div style={s.header}>
        <div>
          <span style={s.title}>{position.label || `#${position.id}`}</span>
          <span style={{ color: 'var(--text-tertiary)', fontSize: 11, marginLeft: 8, fontWeight: 500 }}>{strat}</span>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {position.dte != null && (
            <span style={s.badge('#448aff')}>{position.dte}DTE</span>
          )}
          <span style={s.badge(isOpen ? '#00e676' : '#888')}>
            {isOpen ? 'OPEN' : 'CLOSED'}
          </span>
        </div>
      </div>

      {/* Strike Chips */}
      <div style={s.strikesRow}>
        <span style={s.chip('long')}>LP {position.long_put}</span>
        <span style={s.chip('short')}>SP {position.short_put}</span>
        <span style={s.chip('short')}>SC {position.short_call}</span>
        <span style={s.chip('long')}>LC {position.long_call}</span>
      </div>

      {/* Expirations */}
      <div style={s.expRow}>
        Short: {position.short_exp}
        {position.long_exp && ` | Long: ${position.long_exp}`}
      </div>

      {/* 7 Metrics */}
      <div style={s.metricsGrid}>
        <div style={s.metric}>
          <span style={s.dim}>Entry Credit</span>
          <span style={{ color: 'var(--green)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>+${position.entry_credit?.toFixed(2)}</span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>Current Value</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>{currentValue != null ? `$${currentValue.toFixed(4)}` : '\u2014'}</span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>P&L $</span>
          {isOpen ? (
            <span style={s.pnl(unrealized)}>${unrealized >= 0 ? '+' : ''}{unrealized.toFixed(2)}</span>
          ) : (
            <span style={s.pnl(position.realized_pnl || 0)}>
              ${(position.realized_pnl || 0) >= 0 ? '+' : ''}{(position.realized_pnl || 0).toFixed(2)}
            </span>
          )}
        </div>
        <div style={s.metric}>
          <span style={s.dim}>P&L %</span>
          <span style={s.pnl(isOpen ? unrealized : (position.realized_pnl || 0))}>
            {isOpen
              ? `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%`
              : position.max_profit
                ? `${((position.realized_pnl || 0) / Math.abs(position.max_profit) * 100).toFixed(1)}%`
                : '\u2014'
            }
          </span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>Max Profit</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>${position.max_profit != null ? position.max_profit.toFixed(2) : '\u2014'}</span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>Max Loss</span>
          <span style={{ color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>
            ${position.max_loss != null ? position.max_loss.toFixed(2) : '\u2014'}
          </span>
        </div>
        <div style={s.metric}>
          <span style={s.dim}>Contracts</span>
          <span style={{ fontFamily: 'var(--font-mono)' }}>{position.contracts}</span>
        </div>
      </div>

      {/* Pricing source */}
      {isOpen && pnl?.pricing_source && (
        <div style={{
          fontSize: 10,
          color: pnl.pricing_source === 'live_quotes' ? 'var(--green)' : 'var(--text-secondary)',
          marginBottom: 8,
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          fontWeight: 500,
        }}>
          <span style={{
            width: 5, height: 5, borderRadius: '50%',
            background: pnl.pricing_source === 'live_quotes' ? 'var(--green)'
              : pnl.pricing_source === 'black_scholes_live_iv' ? '#ffb300'
              : 'var(--red)',
            display: 'inline-block',
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
        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontStyle: 'italic', marginBottom: 8 }}>
          {position.notes}
        </div>
      )}

      {/* Date info */}
      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }}>
        Opened {position.entry_date || '\u2014'}
        {position.close_date && ` \u2022 Closed ${position.close_date}`}
      </div>

      {/* Actions */}
      <div style={s.actions}>
        {isOpen && (
          <>
            <button style={s.btn('var(--red)')} onClick={() => onClose(position)}>
              \u2715 Close
            </button>
            <button style={s.btn('var(--text-tertiary)')} onClick={() => onDelete(position.id)}>
              Delete
            </button>
            <button style={{ ...s.btn('var(--text-tertiary)'), ...s.btnDisabled }} disabled title="Coming soon">
              \u21bb Roll
            </button>
          </>
        )}
        <button
          style={s.btn('var(--purple)')}
          onClick={pushToDiscord}
          disabled={discordPushing}
          title="Push to Discord"
        >
          {discordDone ? '\u2713 Sent' : discordPushing ? '...' : '\u21d2 Discord'}
        </button>
        <button
          style={s.btn('var(--accent)')}
          onClick={toggleChart}
          title="View payoff chart"
        >
          {showChart ? '\u2715 Chart' : '\u25b6 Chart'}
        </button>
      </div>

      {/* Payoff Chart — SVG visualization untouched */}
      {showChart && (
        <div style={{ marginTop: 10, borderTop: '1px solid var(--border-subtle)', paddingTop: 10, animation: 'sw-fadeIn 0.2s ease' }}>
          {payoffLoading ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 11, textAlign: 'center', padding: 16 }}>
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
            <div style={{ color: 'var(--text-muted)', fontSize: 11, textAlign: 'center', padding: 16 }}>
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
      {profitFill && <path d={profitFill} fill="rgba(0,230,118,0.12)" />}
      {lossFill && <path d={lossFill} fill="rgba(255,23,68,0.10)" />}

      {/* P&L line */}
      <path d={svg.linePath} fill="none" stroke="#3b82f6" strokeWidth="1.5" />

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
        <text x={svg.pad.left + svg.plotW - 2} y={svg.pad.top + 10} textAnchor="end" fill="#00e676" fontSize="8"
          fontFamily="'JetBrains Mono', monospace">Max +${maxProfit.toFixed(0)}</text>
      )}
      {maxLoss != null && (
        <text x={svg.pad.left + svg.plotW - 2} y={svg.pad.top + svg.plotH - 3} textAnchor="end" fill="#ff5252" fontSize="8"
          fontFamily="'JetBrains Mono', monospace">Max ${maxLoss.toFixed(0)}</text>
      )}

      {/* Border */}
      <rect x={svg.pad.left} y={svg.pad.top} width={svg.plotW} height={svg.plotH}
        fill="none" stroke="var(--border-subtle)" />
    </svg>
  );
}
