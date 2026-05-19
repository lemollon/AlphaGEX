import { useEffect, useState } from 'react';
import { ScrollText, Download } from 'lucide-react';
import { botApi } from '../../lib/botApi';

const LEVEL_COLORS = {
  info: '#94a3b8',   // slate-400
  win:  '#34d399',   // emerald-400
  warn: '#fcd34d',   // amber-300
  err:  '#fb7185',   // rose-400
};

// scan_activity.outcome → log level
function outcomeLevel(outcome) {
  if (!outcome) return 'info';
  if (outcome === 'TRADE') return 'win';
  if (outcome.startsWith('ERR')) return 'err';
  if (outcome.startsWith('BLOCKED') || outcome === 'HALTED' || outcome.startsWith('SKIP')) {
    return 'warn';
  }
  return 'info';
}

function fmtTime(ts) {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return String(ts);
  }
}

function buildMessage(row) {
  const parts = [];
  if (row.outcome) parts.push(row.outcome);
  if (row.reason) parts.push(row.reason);
  if (row.position_id) parts.push(`(${row.position_id})`);
  return parts.join(' · ') || '—';
}

function downloadCsv(bot, rows) {
  const header = 'time,outcome,reason,position_id\n';
  const body = rows.map(r =>
    [
      r.scan_time || '',
      r.outcome || '',
      (r.reason || '').replace(/[",\n]/g, ' '),
      r.position_id || '',
    ].map(v => `"${v}"`).join(',')
  ).join('\n');
  const blob = new Blob([header + body], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const stamp = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `bot-${bot}-logs-${stamp}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
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

  // Session range — first vs last visible row.
  const last = rows[0]?.scan_time;
  const first = rows[rows.length - 1]?.scan_time;
  const sessionRange = first && last
    ? `${fmtTime(first)} – ${fmtTime(last)} CT`
    : '';

  return (
    <div className="px-1 py-2 max-h-[400px] overflow-y-auto">
      <div className="font-mono space-y-0">
        {rows.map(r => {
          const level = outcomeLevel(r.outcome);
          const color = LEVEL_COLORS[level];
          return (
            <div
              key={r.id}
              className="grid grid-cols-[112px_56px_1fr] gap-3 px-4 py-1.5 text-[11.5px] hover:bg-[rgba(125,211,252,0.03)]"
            >
              <span className="sw-mono text-text-muted">{fmtTime(r.scan_time)}</span>
              <span
                className="text-[9.5px] font-bold uppercase tracking-wider text-center px-1.5 py-0.5 rounded self-center"
                style={{ color, background: `${color}1f` }}
              >
                {level}
              </span>
              <span className="text-text-secondary leading-relaxed">{buildMessage(r)}</span>
            </div>
          );
        })}
      </div>
      <div
        className="px-4 py-2 mt-2 text-[11px] text-text-muted flex items-center justify-between"
        style={{ borderTop: '1px solid rgba(125,211,252,0.08)' }}
      >
        <span>{rows.length} entries{sessionRange ? ` · session ${sessionRange}` : ''}</span>
        <button
          onClick={() => downloadCsv(bot, rows)}
          className="font-medium inline-flex items-center gap-1 hover:brightness-110"
          style={{ color: '#7dd3fc' }}
        >
          <Download size={11} /> Export
        </button>
      </div>
    </div>
  );
}
