import { useEffect, useState } from 'react';
import { Clock } from 'lucide-react';
import { botApi } from '../../lib/botApi';
import { STRATEGY_LABEL } from '../../lib/botRegistry';

// close_reason → display label + color class
const REASON_ACTION = {
  PT:         { label: 'Close', cls: 'text-sw-green' },
  EOD:        { label: 'Close', cls: 'text-sw-green' },
  FORCE:      { label: 'Close', cls: 'text-sw-green' },
  SL:         { label: 'Stop',  cls: 'text-sw-red' },
  EVENT_HALT: { label: 'Stop',  cls: 'text-sw-red' },
  ROLL:       { label: 'Roll',  cls: 'text-sw-yellow' },
};

function fmtDate(ts) {
  if (!ts) return ['—', ''];
  try {
    const d = new Date(ts);
    const date = d.toLocaleDateString('en-US', {
      timeZone: 'America/Chicago',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
    const time = d.toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
    return [date, time];
  } catch {
    return [String(ts), ''];
  }
}

function shortStrategy(s) {
  // "iron_butterfly" → "IBF", "double_calendar" → "DC", "double_diagonal" → "DD"
  if (s === 'iron_butterfly')  return 'IBF';
  if (s === 'double_calendar') return 'DC';
  if (s === 'double_diagonal') return 'DD';
  return STRATEGY_LABEL[s] || s;
}

function tradeDesc(row) {
  const strat = shortStrategy(row.strategy);
  let legs = row.legs;
  if (typeof legs === 'string') {
    try { legs = JSON.parse(legs); } catch { legs = []; }
  }
  const strikes = (legs || []).map(l => l.strike).join('/');
  return `${strat} ${row.ticker} ${strikes} · ${row.contracts}×`;
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
    <div>
      <div className="grid grid-cols-[120px_64px_1fr_80px_100px_70px] gap-3 px-5 py-2.5 text-[10px] uppercase tracking-wider font-semibold text-text-tertiary border-b border-white/5">
        <div>Date</div>
        <div>Action</div>
        <div>Trade</div>
        <div className="text-right">Credit</div>
        <div className="text-right">P&amp;L</div>
        <div className="text-right">Status</div>
      </div>
      <div className="divide-y divide-white/[0.04]">
        {trades.map(t => {
          const pnl = Number(t.realized_pnl);
          const win = pnl >= 0;
          const action = REASON_ACTION[t.close_reason] || { label: 'Close', cls: 'text-sw-green' };
          const [date, time] = fmtDate(t.close_time);
          const isCreditStrat = t.strategy === 'iron_butterfly';
          const entry = Number(t.entry_price) || 0;
          const creditStr = isCreditStrat
            ? `+${entry.toFixed(2)}`
            : `−${entry.toFixed(2)}`;
          return (
            <div
              key={t.position_id}
              className="grid grid-cols-[120px_64px_1fr_80px_100px_70px] gap-3 px-5 py-3 items-center hover:bg-white/[0.02]"
            >
              <div className="sw-mono text-[11.5px] text-text-secondary">
                <div>{date}</div>
                <div className="text-text-muted text-[10.5px]">{time}</div>
              </div>
              <div className={`text-[11.5px] font-semibold ${action.cls}`}>{action.label}</div>
              <div className="sw-mono text-[12px] text-text-primary">{tradeDesc(t)}</div>
              <div className="sw-mono text-[12px] text-text-secondary text-right">{creditStr}</div>
              <div
                className="sw-mono text-[12.5px] font-bold text-right"
                style={{ color: win ? '#22c55e' : '#ef4444' }}
              >
                {win ? '+' : '−'}${Math.abs(pnl).toFixed(2)}
              </div>
              <div className="text-right">
                <span
                  className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold ${
                    win
                      ? 'bg-sw-green/15 text-sw-green'
                      : 'bg-sw-red/15 text-sw-red'
                  }`}
                >
                  {win ? '✓' : '✕'}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
