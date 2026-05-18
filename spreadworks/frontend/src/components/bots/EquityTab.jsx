import { useState } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';
import { Activity } from 'lucide-react';
import { useBotEquity } from '../../hooks/useBotEquity';

function formatCT(ts) {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago', hour12: false,
    });
  } catch {
    return ts;
  }
}

function formatEquity(v) {
  if (v == null) return '—';
  return `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="sw-card p-2.5 text-[11px] shadow-md">
      <div className="sw-label mb-1">{formatCT(label)}</div>
      <div className="sw-mono text-text-primary font-semibold">{formatEquity(payload[0]?.value)}</div>
    </div>
  );
};

export default function EquityTab({ bot }) {
  const [mode, setMode] = useState('intraday');
  const { curve } = useBotEquity(bot, mode, 15000);

  return (
    <div>
      {/* Mode toggle */}
      <div className="sw-toggle-group !gap-0.5 w-fit mb-4">
        {['intraday', 'historical'].map(m => (
          <button
            key={m}
            className={`sw-toggle-btn !px-4 !py-1 ${mode === m ? 'active' : ''}`}
            onClick={() => setMode(m)}
          >
            {m === 'intraday' ? 'Intraday' : 'Historical'}
          </button>
        ))}
      </div>

      <div className="sw-card p-4">
        {curve.length < 2 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-2">
            <Activity size={24} className="text-text-muted" />
            <span className="text-text-tertiary text-[13px]">
              No equity points yet. Bot will write one per scan cycle.
            </span>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={curve} margin={{ top: 8, right: 16, left: 16, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-subtle)" />
              <XAxis
                dataKey="time"
                tickFormatter={formatCT}
                tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)' }}
                axisLine={{ stroke: 'var(--color-border-subtle)' }}
                tickLine={false}
              />
              <YAxis
                dataKey="equity"
                domain={['dataMin - 50', 'dataMax + 50']}
                tickFormatter={v => `$${Number(v).toLocaleString()}`}
                tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)', fontFamily: 'var(--font-mono)' }}
                axisLine={{ stroke: 'var(--color-border-subtle)' }}
                tickLine={false}
                width={80}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="equity"
                dot={false}
                strokeWidth={2}
                stroke="var(--color-accent)"
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
