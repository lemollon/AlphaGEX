import { useBotPositions } from '../../hooks/useBotPositions';
import { botApi } from '../../lib/botApi';

function LegBadges({ legs }) {
  if (!legs || legs.length === 0) return <span className="text-text-muted text-[11px]">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {legs.map((l, i) => {
        const side = (l.side || '').toLowerCase();
        const type = (l.type || '').toLowerCase();
        // short call = call-short (red), long call = call-long (green)
        // short put = put-short (red), long put = put-long (green)
        const isCall = type.startsWith('c');
        const isShort = side.startsWith('s') || side === '-1' || side === 'short';
        let variant;
        if (isCall) {
          variant = isShort ? 'sw-strike-badge--call-short' : 'sw-strike-badge--call-long';
        } else {
          variant = isShort ? 'sw-strike-badge--put-short' : 'sw-strike-badge--put-long';
        }
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

export default function PositionsTab({ bot }) {
  const { positions } = useBotPositions(bot, 5000);

  async function onClose(pid) {
    if (!confirm('Force-close this position?')) return;
    await botApi.forceClose(bot, pid);
  }

  if (positions.length === 0) {
    return (
      <div className="text-text-tertiary text-[13px] py-8 text-center">No open positions.</div>
    );
  }

  return (
    <div className="sw-card p-0 overflow-hidden">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle">
            {['POS ID', 'STRATEGY', 'LEGS', 'ENTRY', 'MTM', 'P&L', 'PT / SL', ''].map(h => (
              <th
                key={h}
                className="text-left text-[10px] uppercase tracking-wider text-text-tertiary px-3 py-2.5 font-semibold"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map(p => {
            const pnl = p.mtm_pnl != null ? Number(p.mtm_pnl) : null;
            return (
              <tr key={p.position_id} className="border-b border-border-subtle hover:bg-bg-hover transition-colors">
                <td className="px-3 py-2.5 sw-mono text-text-secondary">{p.position_id}</td>
                <td className="px-3 py-2.5 text-text-secondary">{p.strategy}</td>
                <td className="px-3 py-2.5"><LegBadges legs={p.legs} /></td>
                <td className="px-3 py-2.5 sw-mono">{Number(p.entry_price).toFixed(2)}</td>
                <td className="px-3 py-2.5 sw-mono">
                  {p.mtm_value != null ? Number(p.mtm_value).toFixed(2) : '—'}
                </td>
                <td className="px-3 py-2.5 sw-mono font-semibold">
                  {pnl != null ? (
                    <span className={pnl >= 0 ? 'sw-pnl-positive' : 'sw-pnl-negative'}>
                      {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                    </span>
                  ) : '—'}
                </td>
                <td className="px-3 py-2.5 sw-mono text-text-secondary">
                  ${Number(p.pt_target_pnl).toFixed(0)} / ${Number(p.sl_target_pnl).toFixed(0)}
                </td>
                <td className="px-3 py-2.5">
                  <button
                    className="sw-btn-danger !py-1 !text-[11px]"
                    onClick={() => onClose(p.position_id)}
                  >
                    Close
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
