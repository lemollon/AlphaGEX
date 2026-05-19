import { useEffect, useState } from 'react';
import { Snowflake, Waves, Compass } from 'lucide-react';
import { botApi } from '../lib/botApi';

const TAPE_BOTS = [
  { key: 'breeze', code: 'BRZ', Icon: Snowflake },
  { key: 'tide',   code: 'TID', Icon: Waves },
  { key: 'drift',  code: 'DRF', Icon: Compass },
];

const REFRESH_MS = 15_000;

function formatPnl(pnl) {
  if (pnl == null || Math.abs(pnl) < 0.005) {
    return { text: '—', cls: 'text-text-muted' };
  }
  const sign = pnl > 0 ? '+' : '-';
  return {
    text: `${sign}$${Math.abs(pnl).toFixed(2)}`,
    cls: pnl > 0 ? 'sw-pnl-positive' : 'sw-pnl-negative',
  };
}

export default function LivePnlTape() {
  const [data, setData] = useState({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await botApi.listAll();
        if (cancelled) return;
        const byKey = {};
        for (const b of r.bots || []) {
          if (b && b.bot) byKey[b.bot] = b;
        }
        setData(byKey);
        setLoaded(true);
      } catch {
        if (!cancelled) setLoaded(true);
      }
    }
    load();
    const h = setInterval(load, REFRESH_MS);
    return () => { cancelled = true; clearInterval(h); };
  }, []);

  return (
    <div
      className="hidden lg:flex items-center gap-3 px-3 py-1.5 rounded-full sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <span className="inline-flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-sw-green animate-pulse-dot" />
        Live
      </span>
      {TAPE_BOTS.map(({ key, code, Icon }) => {
        const bot = data[key];
        const pnl = bot && bot.equity != null && bot.starting_capital != null
          ? Number(bot.equity) - Number(bot.starting_capital)
          : null;
        const { text, cls } = loaded ? formatPnl(pnl) : { text: '...', cls: 'text-text-muted' };
        return (
          <div key={key} className="flex items-center gap-1.5">
            <Icon size={11} className="text-text-tertiary" />
            <span className="text-[11px] font-semibold text-text-secondary tracking-wide">{code}</span>
            <span className={`text-[12px] sw-mono font-semibold ${cls}`}>{text}</span>
          </div>
        );
      })}
    </div>
  );
}
