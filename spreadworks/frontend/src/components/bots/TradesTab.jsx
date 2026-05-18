import { useEffect, useState } from 'react';
import { Clock } from 'lucide-react';
import { botApi } from '../../lib/botApi';

const REASON_STYLE = {
  PT:          'bg-sw-green/10 text-sw-green border border-sw-green/25',
  SL:          'bg-sw-red/10 text-sw-red border border-sw-red/25',
  EOD:         'bg-sw-yellow/10 text-sw-yellow border border-sw-yellow/25',
  FORCE:       'bg-sw-purple/10 text-sw-purple border border-sw-purple/25',
  EVENT_HALT:  'bg-sw-red/10 text-sw-red border border-sw-red/25',
};

function ReasonBadge({ reason }) {
  const style = REASON_STYLE[reason] || 'bg-bg-hover text-text-tertiary border border-border-subtle';
  return (
    <span className={`sw-badge ${style}`}>{reason || '—'}</span>
  );
}

export default function TradesTab({ bot }) {
  const [trades, setTrades] = useState([]);
  useEffect(() => {
    botApi.trades(bot, 100).then(d => setTrades(d.trades || [])).catch(() => {});
  }, [bot]);

  if (trades.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <Clock size={24} className="text-text-muted" />
        <span className="text-text-tertiary text-[13px]">No closed trades yet.</span>
      </div>
    );
  }

  return (
    <div className="sw-card p-0 overflow-hidden">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle">
            {['CLOSED', 'REASON', 'P&L', 'ENTRY', 'CLOSE', 'CONTRACTS'].map(h => (
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
          {trades.map(t => {
            const pnl = Number(t.realized_pnl);
            return (
              <tr key={t.position_id} className="border-b border-border-subtle hover:bg-bg-hover transition-colors">
                <td className="px-3 py-2.5 sw-mono text-text-secondary text-[11px]">{t.close_time || '—'}</td>
                <td className="px-3 py-2.5"><ReasonBadge reason={t.close_reason} /></td>
                <td className="px-3 py-2.5 sw-mono font-semibold">
                  <span className={pnl >= 0 ? 'sw-pnl-positive' : 'sw-pnl-negative'}>
                    {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                  </span>
                </td>
                <td className="px-3 py-2.5 sw-mono">{Number(t.entry_price).toFixed(2)}</td>
                <td className="px-3 py-2.5 sw-mono">{Number(t.close_price).toFixed(2)}</td>
                <td className="px-3 py-2.5 sw-mono text-text-secondary">{t.contracts}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
