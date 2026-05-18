import { useEffect, useState } from 'react';
import { ScrollText } from 'lucide-react';
import { botApi } from '../../lib/botApi';

function outcomeStyle(outcome) {
  if (!outcome) return 'text-text-muted';
  if (outcome === 'TRADE') return 'text-accent font-semibold';
  if (outcome === 'MONITOR') return 'text-text-secondary';
  if (outcome.startsWith('BLOCKED')) return 'text-text-tertiary';
  return 'text-text-secondary';
}

export default function LogsTab({ bot }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    botApi.scanActivity(bot, 200).then(d => setRows(d.rows || [])).catch(() => {});
  }, [bot]);

  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <ScrollText size={24} className="text-text-muted" />
        <span className="text-text-tertiary text-[13px]">No scan activity yet.</span>
      </div>
    );
  }

  return (
    <div className="sw-card p-0 overflow-hidden">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle">
            {['TIME', 'OUTCOME', 'REASON', 'POSITION'].map(h => (
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
          {rows.map(r => (
            <tr key={r.id} className="border-b border-border-subtle hover:bg-bg-hover transition-colors">
              <td className="px-3 py-2.5 sw-mono text-text-secondary text-[11px]">{r.scan_time || '—'}</td>
              <td className={`px-3 py-2.5 sw-mono text-[11px] uppercase tracking-wide ${outcomeStyle(r.outcome)}`}>
                {r.outcome || '—'}
              </td>
              <td className="px-3 py-2.5 text-text-tertiary text-[11px]">{r.reason || ''}</td>
              <td className="px-3 py-2.5 sw-mono text-text-muted text-[11px]">{r.position_id || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
