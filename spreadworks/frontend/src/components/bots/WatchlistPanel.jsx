import { useState, useEffect, useCallback } from 'react';
import { botApi } from '../../lib/botApi';

const REFRESH = 60_000; // ~60s auto-poll (8 chain fetches/poll)

function pctText(v) {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(1)}%`;
}
function num(v, d = 2) {
  if (v == null || Number.isNaN(v)) return '—';
  return Number(v).toFixed(d);
}

const STATUS_STYLE = {
  SIGNAL:   (theme) => ({ color: theme.primary, background: theme.primarySoft, ring: theme.primaryRing }),
  HELD:     ()      => ({ color: '#7dd3fc', background: 'rgba(125,211,252,0.10)', ring: 'rgba(125,211,252,0.30)' }),
  WATCHING: ()      => ({ color: '#94a3b8', background: 'rgba(148,163,184,0.08)', ring: 'rgba(148,163,184,0.22)' }),
};

function StatusBadge({ status, theme }) {
  const s = (STATUS_STYLE[status] || STATUS_STYLE.WATCHING)(theme);
  return (
    <span
      className="sw-mono text-[10.5px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
      style={{ color: s.color, background: s.background, boxShadow: `inset 0 0 0 1px ${s.ring}` }}
    >
      {status}
    </span>
  );
}

function CandidateLine({ c }) {
  if (!c) return <span className="text-text-muted">—</span>;
  const net = c.is_credit ? `cr ${num(c.net)}` : `db ${num(c.net)}`;
  const dir = c.kind.replace(/_/g, ' ');
  return (
    <span className="sw-mono text-[12px]">
      <span className="text-text-primary">{c.long_strike}</span>
      <span className="text-text-muted">/</span>
      <span className="text-text-primary">{c.short_strike}</span>
      <span className="text-text-tertiary"> · {dir} · {net} · ×{c.contracts}</span>
      <span className="text-sw-green"> +{num(c.max_profit, 0)}</span>
      <span className="text-text-muted">/</span>
      <span className="text-sw-red">−{num(c.max_loss, 0)}</span>
    </span>
  );
}

export default function WatchlistPanel({ bot, theme }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const fetchWatchlist = useCallback(async () => {
    try {
      const d = await botApi.watchlist(bot);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [bot]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => { if (!cancelled) await fetchWatchlist(); };
    run();
    const h = setInterval(run, REFRESH);
    return () => { cancelled = true; clearInterval(h); };
  }, [fetchWatchlist]);

  const rows = data?.rows || [];

  return (
    <div
      className="rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <div
        className="px-5 py-4 flex items-center justify-between"
        style={{ borderBottom: '1px solid rgba(125,211,252,0.08)' }}
      >
        <div className="flex items-center gap-3">
          <h3 className="text-[14px] font-semibold text-text-primary">Universe Watchlist</h3>
          <span className="text-[11.5px] text-text-tertiary">
            {rows.length ? `${rows.length} names · live candidate spreads` : 'Tracked names'}
          </span>
        </div>
        <button
          onClick={fetchWatchlist}
          className="sw-mono px-3 py-1 text-[11px] font-medium rounded transition-all"
          style={{ color: theme.primary, background: theme.primarySoft }}
        >
          Refresh
        </button>
      </div>

      {error && !data ? (
        <div className="px-5 py-6 text-[13px] text-sw-red">Failed to load watchlist: {error.message}</div>
      ) : !data ? (
        <div className="px-5 py-6 text-[13px] text-text-tertiary">Loading watchlist…</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-text-tertiary text-[10.5px] uppercase tracking-[0.14em]">
                <th className="text-left font-semibold px-4 py-2.5">Ticker</th>
                <th className="text-left font-semibold px-3 py-2.5">Status</th>
                <th className="text-right font-semibold px-3 py-2.5">Spot</th>
                <th className="text-right font-semibold px-3 py-2.5">Dip%</th>
                <th className="text-right font-semibold px-3 py-2.5">Rip%</th>
                <th className="text-right font-semibold px-3 py-2.5">RSI(2)</th>
                <th className="text-right font-semibold px-3 py-2.5">SMA20</th>
                <th className="text-left font-semibold px-3 py-2.5">Expiry</th>
                <th className="text-left font-semibold px-4 py-2.5">Candidate / Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker} className="border-t border-white/[0.04]">
                  <td className="px-4 py-2.5 sw-mono font-semibold text-white">{r.ticker}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={r.status} theme={theme} /></td>
                  <td className="px-3 py-2.5 text-right sw-mono">{num(r.spot)}</td>
                  <td className="px-3 py-2.5 text-right sw-mono">{pctText(r.dip_pct)}</td>
                  <td className="px-3 py-2.5 text-right sw-mono">{pctText(r.rip_pct)}</td>
                  <td className="px-3 py-2.5 text-right sw-mono">{num(r.rsi, 1)}</td>
                  <td className="px-3 py-2.5 text-right sw-mono">{num(r.sma20)}</td>
                  <td className="px-3 py-2.5 sw-mono text-text-tertiary">{r.expiration || '—'}</td>
                  <td className="px-4 py-2.5">
                    {r.status === 'SIGNAL'
                      ? <CandidateLine c={r.candidate} />
                      : <span className="text-text-tertiary">{r.reason || '—'}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
