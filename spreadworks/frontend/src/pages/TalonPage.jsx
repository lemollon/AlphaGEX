// TALON — PAPER-ONLY $500 small-cap squeeze stock bot.
//
// Reads a standalone research warehouse (DuckDB, squeeze repo) via
// /api/spreadworks/talon/* — same one-way-mirror pattern as /squeeze-hunt.
// This page NEVER shows or implies a real order: TALON only ever trades
// on paper, and that is said more than once below, on purpose, matching
// the honesty convention every other research page on this site uses.
//
// Visual shape matches BotDashboard.jsx (/bots/{id}, e.g. /bots/flow) on
// purpose — same nameplate (BotNameplate, imported, not copied), same KPI
// tile (KpiTile, imported), same page padding/borders, same tab-bar look —
// per Leron 2026-10-16. The one real difference: TALON has no toggle/
// force-trade/logs/config API (it's a read-only mirror, not a registry
// bot), and it trades many symbols per day rather than one fixed ticker,
// so Positions/Trade History show a Symbol column instead of the single-
// ticker framing /bots/flow uses.
//
// Strategy (frozen 2026-10-06, see research/OPEN_ENTRY_NO_PRICE_CAP_RESULT.md):
// $1-$5 band, entry = real NBBO ask 09:30-09:34:59 ET, filter = no >=5%
// pullback off the running high in the first 2 minutes, exit = first real
// NBBO bid >= entry x 1.50, or the EOD closing bid if the target is never
// hit. UNCONFIRMED / IN-SAMPLE — found and scored on spent history,
// holdout not yet run. That is exactly why this is paper, not live capital.
import { useEffect, useState } from 'react';
import { AlertTriangle, Inbox, List } from 'lucide-react';
import { API_URL as API_BASE } from '../lib/api';
import { BOT_REGISTRY, BOT_THEME } from '../lib/botRegistry';
import { BotNameplate, KpiTile, money as moneyDec, pct, formatHM } from './BotDashboard';

const meta = BOT_REGISTRY.talon;
const theme = BOT_THEME.talon;

/* ── formatting (TALON-specific: 4-decimal share prices, not $X.XX) ── */

function money4(v) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v < 0 ? '−' : '';
  return `${sign}$${Math.abs(v).toFixed(4)}`;
}

function pctPlain(v, decimals = 0) {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(decimals)}%`;
}

// Wall-clock from an ISO timestamp WITHOUT Date() — Date() re-interprets a
// naive timestamp as UTC and can shift the hour in a negative-offset
// browser, same reasoning as SqueezeHuntPage's clock()/shortDate().
function dateTimeShort(iso) {
  if (typeof iso !== 'string' || iso.length < 16) return '—';
  const [datePart, timePart] = iso.split('T');
  const [, m, d] = datePart.split('-');
  const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mi = parseInt(m, 10) - 1;
  const mon = MONTH_ABBR[mi] || m;
  return `${mon} ${parseInt(d, 10)} ${timePart.slice(0, 5)}`;
}

const EXIT_REASON_LABEL = {
  target: { label: 'TARGET HIT (+50%)', color: '#4ade80' },
  eod: { label: 'EOD CLOSE', color: '#facc15' },
};

function ExitPill({ reason }) {
  const r = EXIT_REASON_LABEL[reason] || { label: reason || '—', color: '#64748b' };
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider whitespace-nowrap"
      style={{ background: `${r.color}22`, color: r.color }}
    >
      {r.label}
    </span>
  );
}

function PaperOnlyBanner() {
  return (
    <div
      className="px-5 py-3 rounded-lg mb-5 flex items-start gap-3"
      style={{ background: 'rgba(251,191,36,0.08)', boxShadow: 'inset 0 0 0 1px rgba(251,191,36,0.30)' }}
    >
      <AlertTriangle size={16} color="#facc15" className="shrink-0 mt-0.5" />
      <div className="text-[12.5px] leading-relaxed" style={{ color: '#fde68a' }}>
        <strong>PAPER TRADING — unconfirmed, in-sample strategy, not live capital.</strong>{' '}
        This $500 account is simulated. The entry/exit rule was found and scored on spent
        history today (OPEN_ENTRY_NO_PRICE_CAP_RESULT.md) and has NOT been holdout-confirmed.
        No real broker order, no real money, at any point on this page.
      </div>
    </div>
  );
}

/* ── Equity curve — same card chrome as BotDashboard's EquityCurveCard,
   but TALON's own step-function chart: it only marks equity at trade
   entry/exit checkpoints, never continuously, so flat segments between
   steps are real, not a rendering gap (unlike /bots/flow's intraday-polled
   curve). No period selector -- TALON's API has no date-range param. ── */

function EquityChart({ curve }) {
  const W = 900;
  const H = 260;
  const padL = 60;
  const padR = 18;
  const padT = 18;
  const padB = 30;

  if (!curve || curve.length < 2) {
    return (
      <div className="flex items-center justify-center text-text-tertiary text-[13px] h-[260px]">
        No equity snapshots yet. The entry/exit checks write one per run.
      </div>
    );
  }

  const values = curve.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.15 || 1;
  const yMin = min - pad;
  const yMax = max + pad;
  const range = yMax - yMin || 1;
  const stepX = (W - padL - padR) / (curve.length - 1);
  const yFor = (v) => padT + (H - padT - padB) * (1 - (v - yMin) / range);

  const points = curve.map((p, i) => [padL + i * stepX, yFor(p.equity)]);
  const linePts = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const areaPts = `${padL},${(H - padB).toFixed(1)} ${linePts} ${(padL + (curve.length - 1) * stepX).toFixed(1)},${(H - padB).toFixed(1)}`;

  const last = curve[curve.length - 1];
  const first = curve[0];
  const up = last.equity >= first.equity;
  const lineColor = up ? '#34d399' : '#fb7185';
  const delta = last.equity - first.equity;
  const deltaPct = first.equity ? delta / first.equity : 0;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none">
      <line x1={padL} y1={yFor(first.equity)} x2={W - padR} y2={yFor(first.equity)}
            stroke="rgba(148,163,184,0.18)" strokeDasharray="4 4" strokeWidth={1} />
      <text x={padL - 8} y={yFor(first.equity) + 3} textAnchor="end" fontSize={10.5}
            fontFamily="JetBrains Mono" fill="#475569">
        {moneyDec(first.equity, { decimals: 0 })}
      </text>
      <polygon points={areaPts} fill={lineColor} opacity={0.12} />
      <polyline points={linePts} fill="none" stroke={lineColor} strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r={4.5} fill={lineColor} stroke="#0a1726" strokeWidth={2.5} />

      {/* last-value pill — same convention as BotDashboard's EquityChart */}
      <g transform={`translate(${Math.min(points[points.length - 1][0] + 10, W - padR - 100)}, ${points[points.length - 1][1] - 14})`}>
        <rect x="0" y="0" width="96" height="28" rx="4" fill={lineColor} />
        <text x="48" y="18" fill="#0a1726" fontSize="12" fontFamily="JetBrains Mono" fontWeight="700" textAnchor="middle">
          {moneyDec(last.equity, { decimals: 2 })}
        </text>
      </g>

      {/* session delta */}
      <g transform={`translate(${padL + 4}, ${padT + 2})`}>
        <text x="0" y="10" fill="#64748b" fontSize="10.5" fontFamily="Inter" fontWeight="600" letterSpacing="0.14em" style={{ textTransform: 'uppercase' }}>
          Since start
        </text>
        <text x="0" y="28" fill={up ? '#34d399' : '#fb7185'} fontSize="14" fontFamily="JetBrains Mono" fontWeight="700">
          {up ? '+' : '−'}${Math.abs(delta).toFixed(2)} · {up ? '+' : '−'}{Math.abs(deltaPct * 100).toFixed(2)}%
        </text>
      </g>
    </svg>
  );
}

function EquityCurveCard({ curve, loading, error }) {
  return (
    <div
      className="rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <div
        className="px-5 py-4 flex items-center justify-between"
        style={{ borderBottom: '1px solid rgba(125,211,252,0.08)' }}
      >
        <h3 className="text-[14px] font-semibold text-text-primary">Equity Curve</h3>
        <span className="text-[11.5px] text-text-tertiary">
          {curve.length} snapshot{curve.length === 1 ? '' : 's'} · marks at entry/exit, not continuous
        </span>
      </div>
      <div className="px-3 pt-3 pb-3">
        {loading ? (
          <div className="flex items-center justify-center h-[260px] text-text-tertiary text-[13px]">Loading…</div>
        ) : error ? (
          <div className="flex items-center justify-center h-[260px] text-[13px] text-sw-red">{error}</div>
        ) : (
          <EquityChart curve={curve} />
        )}
      </div>
    </div>
  );
}

/* ── Positions / Trade History tables ───────────────────────────── */

const COL_HEAD = 'px-3 py-2 text-[10px] uppercase tracking-[0.1em] font-semibold text-text-tertiary';

function PositionsTable({ rows }) {
  return (
    <table className="w-full min-w-[640px] table-fixed">
      <thead>
        <tr className="border-b border-white/5">
          <th className={`${COL_HEAD} text-left`}>Symbol</th>
          <th className={`${COL_HEAD} text-left`}>Entry</th>
          <th className={`${COL_HEAD} text-right`}>Entry ask</th>
          <th className={`${COL_HEAD} text-right`}>Shares</th>
          <th className={`${COL_HEAD} text-right`}>Size</th>
          <th className={`${COL_HEAD} text-center`}>Target</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.position_id} className="border-t border-white/5 hover:bg-white/[0.03]">
            <td className="px-3 py-2.5">
              <span className="font-bold text-[13px] text-text-primary sw-mono">{p.symbol}</span>
            </td>
            <td className="px-3 py-2.5 text-text-secondary sw-mono text-[12.5px]">{dateTimeShort(p.entry_ts)}</td>
            <td className="px-3 py-2.5 text-right sw-mono text-[13px] text-text-primary">{money4(p.entry_ask)}</td>
            <td className="px-3 py-2.5 text-right sw-mono text-[12.5px] text-text-secondary">
              {p.shares != null ? p.shares.toFixed(2) : '—'}
            </td>
            <td className="px-3 py-2.5 text-right sw-mono text-[12.5px] text-text-secondary">{moneyDec(p.position_size_usd, { decimals: 0 })}</td>
            <td className="px-3 py-2.5 text-center sw-mono text-[12.5px]" style={{ color: theme.primary }}>
              {p.entry_ask != null ? money4(p.entry_ask * 1.5) : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TradesTable({ rows }) {
  return (
    <table className="w-full min-w-[760px] table-fixed">
      <thead>
        <tr className="border-b border-white/5">
          <th className={`${COL_HEAD} text-left`}>Symbol</th>
          <th className={`${COL_HEAD} text-left`}>Entry</th>
          <th className={`${COL_HEAD} text-right`}>Entry ask</th>
          <th className={`${COL_HEAD} text-left`}>Exit</th>
          <th className={`${COL_HEAD} text-right`}>Exit bid</th>
          <th className={`${COL_HEAD} text-center`}>Reason</th>
          <th className={`${COL_HEAD} text-right`}>P&amp;L</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t) => {
          const pnlColor = (t.realized_pnl || 0) >= 0 ? '#34d399' : '#fb7185';
          return (
            <tr key={t.position_id} className="border-t border-white/5 hover:bg-white/[0.03]">
              <td className="px-3 py-2.5">
                <span className="font-bold text-[13px] text-text-primary sw-mono">{t.symbol}</span>
              </td>
              <td className="px-3 py-2.5 text-text-secondary sw-mono text-[12.5px]">{dateTimeShort(t.entry_ts)}</td>
              <td className="px-3 py-2.5 text-right sw-mono text-[13px] text-text-primary">{money4(t.entry_ask)}</td>
              <td className="px-3 py-2.5 text-text-secondary sw-mono text-[12.5px]">{dateTimeShort(t.exit_ts)}</td>
              <td className="px-3 py-2.5 text-right sw-mono text-[13px] text-text-primary">{money4(t.exit_price)}</td>
              <td className="px-3 py-2.5 text-center"><ExitPill reason={t.exit_reason} /></td>
              <td className="px-3 py-2.5 text-right sw-mono text-[13px] font-semibold" style={{ color: pnlColor }}>
                {moneyDec(t.realized_pnl, { signed: true })}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/* ── Activity tabs — same tab-bar look as BotDashboard's ActivityTabs,
   just two tabs: TALON has no /logs or /config endpoint to show. ── */

function ActivityTabs({ positions, positionsLoading, positionsError, trades, tradesLoading, tradesError }) {
  const [tab, setTab] = useState('positions');
  const tabs = [
    { id: 'positions', label: 'Positions', Icon: Inbox, count: positions.length },
    { id: 'history', label: 'Trade History', Icon: List, count: trades.length },
  ];
  return (
    <div
      className="rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <div
        className="flex items-center gap-1 px-3 pt-3 overflow-x-auto whitespace-nowrap"
        style={{ borderBottom: '1px solid rgba(125,211,252,0.08)' }}
      >
        {tabs.map(t => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="relative shrink-0 inline-flex items-center gap-2 px-3.5 py-2.5 text-[12.5px] font-semibold transition-colors"
              style={{ color: active ? theme.primary : 'var(--color-text-secondary)' }}
            >
              <t.Icon size={13} />
              {t.label}
              {t.count > 0 && (
                <span
                  className="sw-mono text-[10px] font-bold px-1.5 py-0.5 rounded-full"
                  style={active
                    ? { background: theme.primarySoft, color: theme.primary, boxShadow: `inset 0 0 0 1px ${theme.primaryRing}` }
                    : { background: 'rgba(255,255,255,0.05)', color: 'var(--color-text-secondary)' }}
                >
                  {t.count}
                </span>
              )}
              {active && <span className="absolute left-2.5 right-2.5 -bottom-px h-[2px]" style={{ background: theme.primary }} />}
            </button>
          );
        })}
      </div>
      <div className="min-h-[280px] overflow-x-auto">
        {tab === 'positions' && (
          positionsLoading ? <div className="px-5 py-8 text-center text-text-tertiary text-[13px]">Loading…</div>
          : positionsError ? <div className="px-5 py-8 text-center text-[13px] text-sw-red">{positionsError}</div>
          : !positions.length ? <div className="px-5 py-8 text-center text-text-tertiary text-[13px]">No open positions.</div>
          : <PositionsTable rows={positions} />
        )}
        {tab === 'history' && (
          tradesLoading ? <div className="px-5 py-8 text-center text-text-tertiary text-[13px]">Loading…</div>
          : tradesError ? <div className="px-5 py-8 text-center text-[13px] text-sw-red">{tradesError}</div>
          : !trades.length ? <div className="px-5 py-8 text-center text-text-tertiary text-[13px]">No closed trades yet.</div>
          : <TradesTable rows={trades} />
        )}
      </div>
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────────────── */

export default function TalonPage() {
  const [status, setStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);

  const [positions, setPositions] = useState([]);
  const [positionsLoading, setPositionsLoading] = useState(true);
  const [positionsError, setPositionsError] = useState(null);

  const [trades, setTrades] = useState([]);
  const [tradesLoading, setTradesLoading] = useState(true);
  const [tradesError, setTradesError] = useState(null);

  const [curve, setCurve] = useState([]);
  const [curveLoading, setCurveLoading] = useState(true);
  const [curveError, setCurveError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/talon/status`);
        if (!res.ok) throw new Error(`status ${res.status}`);
        const data = await res.json();
        if (!cancelled) setStatus(data);
      } catch { /* keep last good status */ }
      finally { if (!cancelled) setStatusLoading(false); }

      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/talon/positions`);
        if (!res.ok) throw new Error(`positions ${res.status}`);
        const data = await res.json();
        if (!cancelled) { setPositions(data.positions || []); setPositionsError(null); }
      } catch (e) { if (!cancelled) setPositionsError(e.message || 'load failed'); }
      finally { if (!cancelled) setPositionsLoading(false); }

      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/talon/trades`);
        if (!res.ok) throw new Error(`trades ${res.status}`);
        const data = await res.json();
        if (!cancelled) { setTrades(data.trades || []); setTradesError(null); }
      } catch (e) { if (!cancelled) setTradesError(e.message || 'load failed'); }
      finally { if (!cancelled) setTradesLoading(false); }

      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/talon/equity-curve`);
        if (!res.ok) throw new Error(`equity-curve ${res.status}`);
        const data = await res.json();
        if (!cancelled) { setCurve(data.curve || []); setCurveError(null); }
      } catch (e) { if (!cancelled) setCurveError(e.message || 'load failed'); }
      finally { if (!cancelled) setCurveLoading(false); }
    }
    load();
    const iv = setInterval(load, 60_000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  const s = status || {};
  const pnlColor = (s.total_pnl || 0) >= 0 ? '#34d399' : '#fb7185';

  return (
    <div className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary">
      <div className="px-4 md:px-8 pt-7 pb-6" style={{ borderBottom: '1px solid rgba(125,211,252,0.18)' }}>
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <BotNameplate
            bot="talon"
            meta={meta}
            theme={theme}
            right={
              <span className="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider" style={{ background: 'rgba(251,191,36,0.16)', color: '#facc15' }}>
                Paper
              </span>
            }
            note="Many symbols at once, $1-$5 squeeze stocks — not a single fixed ticker like most of the fleet."
          />
        </div>
      </div>

      <div className="px-4 md:px-8 py-6 space-y-5">
        <PaperOnlyBanner />

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiTile
            label="Account Equity"
            value={statusLoading ? '…' : moneyDec(s.current_balance, { decimals: 2 })}
            sub={`Started ${moneyDec(s.starting_balance, { decimals: 0 })}`}
          />
          <KpiTile
            label="Total P&L"
            value={statusLoading ? '…' : moneyDec(s.total_pnl, { signed: true })}
            accent={!statusLoading ? pnlColor : undefined}
            sub={s.total_pnl_pct != null ? `${pct(s.total_pnl_pct)} since start` : undefined}
          />
          <KpiTile
            label="Open Positions"
            value={statusLoading ? '…' : String(s.open_positions ?? 0)}
            accent={s.open_positions > 0 ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)'}
            sub={s.open_positions > 0 ? 'Auto-managed' : 'Awaiting setup'}
          />
          <KpiTile
            label="Win Rate"
            value={statusLoading || !s.closed_trades ? <span className="text-text-muted">—</span> : pctPlain(s.win_rate)}
            accent={s.closed_trades > 0 && s.win_rate != null ? (s.win_rate >= 0.5 ? 'var(--color-sw-green)' : 'var(--color-sw-red)') : undefined}
            sub={`${s.closed_trades ?? 0} closed trade${s.closed_trades === 1 ? '' : 's'}`}
          />
        </div>

        <EquityCurveCard curve={curve} loading={curveLoading} error={curveError} />

        <ActivityTabs
          positions={positions} positionsLoading={positionsLoading} positionsError={positionsError}
          trades={trades} tradesLoading={tradesLoading} tradesError={tradesError}
        />

        <p className="text-[11px] text-text-tertiary leading-relaxed max-w-[900px]">
          Entry: real NBBO ask, 09:30:00-09:34:59 ET, $1-$5 band, no &ge;5% pullback off the
          running high in the first 2 minutes. Exit: first real NBBO bid &ge; entry &times;
          1.50, or the EOD closing bid if the target is never hit. Position size 20% of
          current paper equity. Source: <code>research/talon_paper_trader.py</code> in the
          squeeze repo, via a one-way Postgres mirror — same pattern as Squeeze Hunt.
          {s.updated_at && <> Last synced {formatHM(s.updated_at)}.</>}
        </p>
      </div>
    </div>
  );
}
