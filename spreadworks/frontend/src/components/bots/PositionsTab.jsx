import { Inbox } from 'lucide-react';
import { useBotPositions } from '../../hooks/useBotPositions';
import { botApi } from '../../lib/botApi';
import { BOT_THEME, BOT_REGISTRY, STRATEGY_LABEL } from '../../lib/botRegistry';

function LegBadges({ legs }) {
  if (!legs || legs.length === 0) return <span className="text-text-muted text-[11px]">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {legs.map((l, i) => {
        const side = (l.side || '').toLowerCase();
        const type = (l.type || '').toLowerCase();
        const isCall = type.startsWith('c');
        const isShort = side.startsWith('s') || side === '-1' || side === 'short';
        const variant = isCall
          ? (isShort ? 'sw-strike-badge--call-short' : 'sw-strike-badge--call-long')
          : (isShort ? 'sw-strike-badge--put-short'  : 'sw-strike-badge--put-long');
        const label = `${isShort ? 'S' : 'L'}${isCall ? 'C' : 'P'}`;
        return (
          <span key={i} className={`sw-strike-badge ${variant}`}>
            {label} <span className="strike-value">{l.strike}</span>
          </span>
        );
      })}
    </div>
  );
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

export default function PositionsTab({ bot }) {
  const { positions } = useBotPositions(bot, 5000);
  const theme = BOT_THEME[bot];
  const meta = BOT_REGISTRY[bot];

  async function onClose(pid) {
    if (!confirm('Force-close this position?')) return;
    await botApi.forceClose(bot, pid);
  }

  if (positions.length === 0) {
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
            <span className="w-1.5 h-1.5 rounded-full bg-sw-green animate-pulse" />
            Scanning
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
        // P&L as percent of the structure's notional (entry × contracts × 100).
        const pnlPct = pnl != null && entry && contracts
          ? pnl / (Math.abs(entry) * contracts * 100)
          : null;

        return (
          <div
            key={p.position_id}
            className="rounded-md ring-1 ring-white/5 px-5 py-4"
            style={{ background: '#070b14' }}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                  <span className="sw-mono text-[12px] font-bold text-white">{p.ticker}</span>
                  <span className="w-1 h-1 rounded-full bg-text-muted" />
                  <span className="text-[12px] text-text-secondary font-medium">
                    {STRATEGY_LABEL[p.strategy] || p.strategy}
                  </span>
                  <span className="sw-mono text-[10.5px] uppercase tracking-wider font-bold px-2 py-0.5 rounded text-blue-300 bg-blue-500/10 ring-1 ring-blue-500/20 whitespace-nowrap">
                    {contracts}×
                  </span>
                </div>
                <LegBadges legs={p.legs} />
                <div className="sw-mono text-[10.5px] text-text-muted mt-2">
                  Opened {formatOpened(p.entry_time)}
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <div
                  className="sw-mono text-[18px] font-bold"
                  style={{ color: pos ? '#22c55e' : '#ef4444' }}
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
              <div className="text-right">
                <button
                  onClick={() => onClose(p.position_id)}
                  className="px-2.5 py-1 rounded-md text-[11px] font-semibold text-text-secondary hover:text-white ring-1 ring-white/5 transition-colors"
                  style={{ background: '#11151f' }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
