import { useState } from 'react';
import { Inbox, BarChart3, X } from 'lucide-react';
import { useBotPositions } from '../../hooks/useBotPositions';
import { botApi } from '../../lib/botApi';
import { BOT_THEME, BOT_REGISTRY, STRATEGY_LABEL } from '../../lib/botRegistry';
import BotPayoffChart from './BotPayoffChart';

// Format a legs array the way the design handoff wants it:
//   "+P 580 / −P 585 / −C 600 / +C 605"
function formatLegs(legs) {
  if (!legs || legs.length === 0) return '—';
  return legs.map(l => {
    const side = (l.side || '').toLowerCase();
    const type = (l.type || '').toLowerCase();
    const isCall = type.startsWith('c');
    const isShort = side.startsWith('s') || side === '-1' || side === 'short';
    const sign = isShort ? '−' : '+';
    const letter = isCall ? 'C' : 'P';
    return `${sign}${letter} ${l.strike}`;
  }).join(' / ');
}

function formatOpened(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }) + ' CT';
  } catch {
    return String(ts);
  }
}

function relativeTime(ts) {
  if (!ts) return 'just now';
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 0) return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function PositionsTab({ bot, lastScanAt, enabled = true }) {
  const { positions } = useBotPositions(bot, 5000);
  const theme = BOT_THEME[bot];
  const meta = BOT_REGISTRY[bot];
  const [openCharts, setOpenCharts] = useState(() => new Set());

  function toggleChart(pid) {
    setOpenCharts(prev => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid); else next.add(pid);
      return next;
    });
  }

  async function onClose(pid) {
    if (!confirm('Force-close this position?')) return;
    await botApi.forceClose(bot, pid);
  }

  if (positions.length === 0) {
    const scanLabel = enabled
      ? `Scanning · ${relativeTime(lastScanAt)}`
      : 'Scanner paused';
    const dotClass = enabled ? 'bg-sw-green animate-pulse' : 'bg-text-tertiary';
    return (
      <div className="px-5 py-16 flex flex-col items-center text-center">
        <div
          className="w-14 h-14 rounded-full grid place-items-center mb-4"
          style={{
            background: theme.primarySoft,
            boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
          }}
        >
          <Inbox size={22} style={{ color: theme.primary }} strokeWidth={1.5} />
        </div>
        <div className="text-[14px] font-semibold text-white mb-1">No open positions</div>
        <div className="text-[12.5px] text-text-tertiary max-w-sm leading-relaxed">
          {meta?.display || bot.toUpperCase()} is scanning for a setup. The next
          trade will appear here automatically when filters match.
        </div>
        <div className="flex items-center gap-2 mt-5 text-[11px] text-text-tertiary">
          <span className="inline-flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
            {scanLabel}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-5 space-y-3">
      {positions.map(p => {
        const pnl = p.mtm_pnl != null ? Number(p.mtm_pnl) : null;
        const pos = pnl != null && pnl >= 0;
        const entry = Number(p.entry_price) || 0;
        const current = p.mtm_value != null ? Number(p.mtm_value) : null;
        const contracts = Number(p.contracts) || 1;
        const pnlPct = pnl != null && entry && contracts
          ? pnl / (Math.abs(entry) * contracts * 100)
          : null;
        const legs = typeof p.legs === 'string'
          ? (() => { try { return JSON.parse(p.legs); } catch { return []; } })()
          : (p.legs || []);

        return (
          <div
            key={p.position_id}
            className="rounded-md sw-glass-deep px-5 py-4"
            style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                  <span className="sw-mono text-[12px] font-bold text-white">{p.ticker}</span>
                  <span className="w-1 h-1 rounded-full bg-text-muted" />
                  <span className="text-[12px] text-text-secondary font-medium">
                    {STRATEGY_LABEL[p.strategy] || p.strategy}
                  </span>
                  <span
                    className="sw-mono text-[10.5px] uppercase tracking-wider font-bold px-2 py-0.5 rounded whitespace-nowrap"
                    style={{
                      color: '#7dd3fc',
                      background: 'rgba(125,211,252,0.10)',
                      boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.30)',
                    }}
                  >
                    {contracts}×
                  </span>
                </div>
                <div className="sw-mono text-[12.5px] text-text-secondary">
                  {formatLegs(legs)}
                </div>
                <div className="sw-mono text-[10.5px] text-text-muted mt-1">
                  Opened {formatOpened(p.entry_time)}
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <div
                  className="sw-mono text-[18px] font-bold"
                  style={{ color: pos ? '#34d399' : '#fb7185' }}
                >
                  {pnl != null
                    ? `${pos ? '+' : '−'}$${Math.abs(pnl).toFixed(2)}`
                    : '—'}
                </div>
                <div className="sw-mono text-[11px] text-text-tertiary mt-0.5">
                  {pnlPct != null
                    ? `${pnlPct >= 0 ? '+' : ''}${(pnlPct * 100).toFixed(1)}% on credit`
                    : ''}
                </div>
              </div>
            </div>

            <div className="mt-3 grid grid-cols-[1fr_1fr_1fr_auto] gap-4 text-[11px] items-end">
              <div>
                <div className="text-text-tertiary uppercase tracking-wider font-semibold text-[10px] mb-1">
                  Entry credit
                </div>
                <div className="sw-mono text-text-secondary font-semibold">${entry.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-text-tertiary uppercase tracking-wider font-semibold text-[10px] mb-1">
                  Current
                </div>
                <div className="sw-mono text-white font-semibold">
                  {current != null ? `$${current.toFixed(2)}` : '—'}
                </div>
              </div>
              <div>
                <div className="text-text-tertiary uppercase tracking-wider font-semibold text-[10px] mb-1">
                  PT / SL
                </div>
                <div className="sw-mono text-text-secondary font-semibold">
                  ${Number(p.pt_target_pnl).toFixed(0)} / ${Number(p.sl_target_pnl).toFixed(0)}
                </div>
              </div>
              <div className="text-right flex gap-1.5 justify-end">
                <button
                  onClick={() => toggleChart(p.position_id)}
                  className="px-2.5 py-1 rounded-md text-[11px] font-semibold sw-glass text-text-body hover:text-text-primary transition-colors inline-flex items-center gap-1"
                  style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)' }}
                  title="Toggle payoff chart"
                >
                  {openCharts.has(p.position_id)
                    ? <><X size={10} /> Chart</>
                    : <><BarChart3 size={10} /> Chart</>}
                </button>
                <button
                  onClick={() => onClose(p.position_id)}
                  className="px-2.5 py-1 rounded-md text-[11px] font-semibold sw-glass text-text-body hover:text-text-primary transition-colors"
                  style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)' }}
                >
                  Close
                </button>
              </div>
            </div>

            {openCharts.has(p.position_id) && (
              <div className="mt-3 pt-3 border-t border-border-subtle">
                <BotPayoffChart
                  bot={bot}
                  positionId={p.position_id}
                  contracts={contracts}
                  height={190}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
