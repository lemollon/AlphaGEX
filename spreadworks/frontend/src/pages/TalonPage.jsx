// TALON — PAPER-ONLY $500 small-cap squeeze stock bot.
//
// Reads a standalone research warehouse (DuckDB, squeeze repo) via
// /api/spreadworks/talon/* — same one-way-mirror pattern as /squeeze-hunt.
// This page NEVER shows or implies a real order: TALON only ever trades
// on paper, and that is said more than once below, on purpose, matching
// the honesty convention every other research page on this site uses.
//
// Strategy (frozen 2026-10-06, see research/OPEN_ENTRY_NO_PRICE_CAP_RESULT.md):
// $1-$5 band, entry = real NBBO ask 09:30-09:34:59 ET, filter = no >=5%
// pullback off the running high in the first 2 minutes, exit = first real
// NBBO bid >= entry x 1.50, or the EOD closing bid if the target is never
// hit. UNCONFIRMED / IN-SAMPLE — found and scored on spent history,
// holdout not yet run. That is exactly why this is paper, not live capital.
import { useEffect, useState } from 'react';
import { Crosshair, AlertTriangle } from 'lucide-react';
import { API_URL as API_BASE } from '../lib/api';

const THEME = {
  primary: '#38bdf8',
  primaryRing: 'rgba(56,189,248,0.30)',
  glow: 'rgba(56,189,248,0.18)',
  green: '#4ade80',
  amber: '#facc15',
  red: '#fb7185',
  dim: '#64748b',
};

/* ── formatting ──────────────────────────────────────────────────── */

function money(v, decimals = 2) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v < 0 ? '−' : '';
  return `${sign}$${Math.abs(v).toFixed(decimals)}`;
}

function pct(v, decimals = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v * 100).toFixed(decimals)}%`;
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
  target: { label: 'TARGET HIT (+50%)', color: THEME.green },
  eod: { label: 'EOD CLOSE', color: THEME.amber },
};

function ExitPill({ reason }) {
  const r = EXIT_REASON_LABEL[reason] || { label: reason || '—', color: THEME.dim };
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider whitespace-nowrap"
      style={{ background: `${r.color}22`, color: r.color }}
    >
      {r.label}
    </span>
  );
}

/* ── Paper-only banner — never below the fold, never ambiguous ────── */

function PaperOnlyBanner() {
  return (
    <div
      className="px-5 py-3 rounded-lg mb-5 flex items-start gap-3"
      style={{ background: 'rgba(251,191,36,0.08)', boxShadow: 'inset 0 0 0 1px rgba(251,191,36,0.30)' }}
    >
      <AlertTriangle size={16} color={THEME.amber} className="shrink-0 mt-0.5" />
      <div className="text-[12.5px] leading-relaxed" style={{ color: '#fde68a' }}>
        <strong>PAPER TRADING — unconfirmed, in-sample strategy, not live capital.</strong>{' '}
        This $500 account is simulated. The entry/exit rule was found and scored on spent
        history today (OPEN_ENTRY_NO_PRICE_CAP_RESULT.md) and has NOT been holdout-confirmed.
        No real broker order, no real money, at any point on this page.
      </div>
    </div>
  );
}

/* ── Status cards ───────────────────────────────────────────────── */

function StatCard({ label, value, valueColor, sub }) {
  return (
    <div
      className="px-4 py-3 rounded-md sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(148,163,184,0.10)' }}
    >
      <div className="text-[10px] uppercase tracking-[0.14em] text-text-tertiary mb-1.5">{label}</div>
      <div className="text-[19px] font-bold sw-mono" style={{ color: valueColor || 'var(--color-text-primary)' }}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-text-secondary sw-mono mt-1">{sub}</div>}
    </div>
  );
}

function StatusCards({ status, loading, error }) {
  if (loading) {
    return <div className="px-5 py-8 text-center text-text-tertiary text-[13px]">Loading…</div>;
  }
  if (error) {
    return <div className="px-5 py-8 text-center text-[13px]" style={{ color: THEME.red }}>{error}</div>;
  }
  const pnlColor = (status.total_pnl || 0) >= 0 ? THEME.green : THEME.red;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3 mb-6">
      <StatCard label="Starting balance" value={money(status.starting_balance, 0)} />
      <StatCard
        label="Current balance"
        value={money(status.current_balance, 2)}
        valueColor={pnlColor}
      />
      <StatCard
        label="Total P&amp;L"
        value={`${money(status.total_pnl, 2)} (${pct(status.total_pnl_pct)})`}
        valueColor={pnlColor}
        sub={status.updated_at ? `as of ${dateTimeShort(status.updated_at)}` : undefined}
      />
      <StatCard
        label="Win rate"
        value={status.win_rate != null ? pctPlain(status.win_rate) : '—'}
        sub={`${status.closed_trades} closed trade${status.closed_trades === 1 ? '' : 's'}`}
      />
      <StatCard
        label="Open positions"
        value={String(status.open_positions)}
        valueColor={status.open_positions > 0 ? THEME.primary : undefined}
      />
    </div>
  );
}

/* ── Equity curve — plain inline SVG, same house style as the other
   hand-drawn charts on this site (BotDashboard's EquityChart, SqueezeHunt's
   PaceSpark). A step function, not a smooth line — TALON only marks equity
   at entry/exit checkpoints, never continuously, so the flat segments
   between steps are real, not a rendering gap. ──────────────────────── */

function EquityChart({ curve }) {
  const W = 900;
  const H = 220;
  const padL = 56;
  const padR = 16;
  const padT = 16;
  const padB = 24;

  if (!curve || curve.length < 2) {
    return (
      <div className="flex items-center justify-center text-text-tertiary text-[13px] h-[220px]">
        No equity snapshots yet. The entry/exit checks write one per run.
      </div>
    );
  }

  const values = curve.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.12 || 1;
  const yMin = min - pad;
  const yMax = max + pad;
  const range = yMax - yMin || 1;
  const stepX = (W - padL - padR) / (curve.length - 1);
  const yFor = (v) => padT + (H - padT - padB) * (1 - (v - yMin) / range);

  const points = curve.map((p, i) => [padL + i * stepX, yFor(p.equity)]);
  const linePts = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const areaPts = `${padL},${(H - padB).toFixed(1)} ${linePts} ${(padL + (curve.length - 1) * stepX).toFixed(1)},${(H - padB).toFixed(1)}`;

  const last = curve[curve.length - 1];
  const up = last.equity >= curve[0].equity;
  const lineColor = up ? THEME.green : THEME.red;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none">
      <line x1={padL} y1={yFor(curve[0].equity)} x2={W - padR} y2={yFor(curve[0].equity)}
            stroke="rgba(148,163,184,0.18)" strokeDasharray="4 4" strokeWidth={1} />
      <text x={padL - 6} y={yFor(curve[0].equity) + 3} textAnchor="end" fontSize={10}
            fill="var(--color-text-tertiary)">
        {money(curve[0].equity, 0)}
      </text>
      <polygon points={areaPts} fill={lineColor} opacity={0.08} />
      <polyline points={linePts} fill="none" stroke={lineColor} strokeWidth={1.75} />
      <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r={3} fill={lineColor} />
      <text x={W - padR} y={yFor(last.equity) - 8} textAnchor="end" fontSize={11} fontWeight={700}
            fill={lineColor}>
        {money(last.equity, 2)}
      </text>
    </svg>
  );
}

function EquityCurveCard({ curve, loading, error }) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2.5">
        <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary">
          Equity curve
        </h2>
        <span className="text-[12px] text-text-tertiary sw-mono">
          {curve.length} snapshot{curve.length === 1 ? '' : 's'}
        </span>
      </div>
      <div
        className="rounded-lg sw-glass px-4 py-3"
        style={{ boxShadow: 'inset 0 0 0 1px rgba(148,163,184,0.10)' }}
      >
        {loading ? (
          <div className="flex items-center justify-center h-[220px] text-text-tertiary text-[13px]">Loading…</div>
        ) : error ? (
          <div className="flex items-center justify-center h-[220px] text-[13px]" style={{ color: THEME.red }}>{error}</div>
        ) : (
          <EquityChart curve={curve} />
        )}
      </div>
    </div>
  );
}

/* ── Open positions ─────────────────────────────────────────────── */

const COL_HEAD = 'px-3 py-2 text-[10px] uppercase tracking-[0.1em] font-semibold text-text-tertiary';

function PositionsTable({ rows }) {
  return (
    <table className="w-full min-w-[640px] table-fixed">
      <colgroup>
        <col style={{ width: '16%' }} />
        <col style={{ width: '22%' }} />
        <col style={{ width: '16%' }} />
        <col style={{ width: '16%' }} />
        <col style={{ width: '16%' }} />
        <col style={{ width: '14%' }} />
      </colgroup>
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
            <td className="px-3 py-2.5 text-text-secondary sw-mono text-[12.5px]">
              {dateTimeShort(p.entry_ts)}
            </td>
            <td className="px-3 py-2.5 text-right sw-mono text-[13px] text-text-primary">
              {money(p.entry_ask, 4)}
            </td>
            <td className="px-3 py-2.5 text-right sw-mono text-[12.5px] text-text-secondary">
              {p.shares != null ? p.shares.toFixed(2) : '—'}
            </td>
            <td className="px-3 py-2.5 text-right sw-mono text-[12.5px] text-text-secondary">
              {money(p.position_size_usd, 0)}
            </td>
            <td className="px-3 py-2.5 text-center sw-mono text-[12.5px]" style={{ color: THEME.primary }}>
              {p.entry_ask != null ? money(p.entry_ask * 1.5, 4) : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function OpenPositions({ rows, loading, error }) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2.5">
        <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary">
          Open positions
        </h2>
        <span className="text-[12px] text-text-tertiary sw-mono">{rows.length}</span>
      </div>
      <div
        className="rounded-lg sw-glass overflow-x-auto"
        style={{ boxShadow: 'inset 0 0 0 1px rgba(148,163,184,0.10)' }}
      >
        {loading ? (
          <div className="px-5 py-8 text-center text-text-tertiary text-[13px]">Loading…</div>
        ) : error ? (
          <div className="px-5 py-8 text-center text-[13px]" style={{ color: THEME.red }}>{error}</div>
        ) : !rows.length ? (
          <div className="px-5 py-8 text-center text-text-tertiary text-[13px]">No open positions.</div>
        ) : (
          <PositionsTable rows={rows} />
        )}
      </div>
    </div>
  );
}

/* ── Closed trades ──────────────────────────────────────────────── */

function TradesTable({ rows }) {
  return (
    <table className="w-full min-w-[760px] table-fixed">
      <colgroup>
        <col style={{ width: '12%' }} />
        <col style={{ width: '16%' }} />
        <col style={{ width: '12%' }} />
        <col style={{ width: '16%' }} />
        <col style={{ width: '12%' }} />
        <col style={{ width: '16%' }} />
        <col style={{ width: '16%' }} />
      </colgroup>
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
          const pnlColor = (t.realized_pnl || 0) >= 0 ? THEME.green : THEME.red;
          return (
            <tr key={t.position_id} className="border-t border-white/5 hover:bg-white/[0.03]">
              <td className="px-3 py-2.5">
                <span className="font-bold text-[13px] text-text-primary sw-mono">{t.symbol}</span>
              </td>
              <td className="px-3 py-2.5 text-text-secondary sw-mono text-[12.5px]">
                {dateTimeShort(t.entry_ts)}
              </td>
              <td className="px-3 py-2.5 text-right sw-mono text-[13px] text-text-primary">
                {money(t.entry_ask, 4)}
              </td>
              <td className="px-3 py-2.5 text-text-secondary sw-mono text-[12.5px]">
                {dateTimeShort(t.exit_ts)}
              </td>
              <td className="px-3 py-2.5 text-right sw-mono text-[13px] text-text-primary">
                {money(t.exit_price, 4)}
              </td>
              <td className="px-3 py-2.5 text-center">
                <ExitPill reason={t.exit_reason} />
              </td>
              <td className="px-3 py-2.5 text-right sw-mono text-[13px] font-semibold" style={{ color: pnlColor }}>
                {money(t.realized_pnl, 2)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ClosedTrades({ rows, loading, error }) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2.5">
        <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary">
          Closed trades
        </h2>
        <span className="text-[12px] text-text-tertiary sw-mono">{rows.length}</span>
      </div>
      <div
        className="rounded-lg sw-glass overflow-x-auto"
        style={{ boxShadow: 'inset 0 0 0 1px rgba(148,163,184,0.10)' }}
      >
        {loading ? (
          <div className="px-5 py-8 text-center text-text-tertiary text-[13px]">Loading…</div>
        ) : error ? (
          <div className="px-5 py-8 text-center text-[13px]" style={{ color: THEME.red }}>{error}</div>
        ) : !rows.length ? (
          <div className="px-5 py-8 text-center text-text-tertiary text-[13px]">No closed trades yet.</div>
        ) : (
          <TradesTable rows={rows} />
        )}
      </div>
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────────────── */

export default function TalonPage() {
  const [status, setStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState(null);

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
        if (!cancelled) {
          setStatus(data);
          setStatusError(null);
        }
      } catch (e) {
        if (!cancelled) setStatusError(e.message || 'load failed');
      } finally {
        if (!cancelled) setStatusLoading(false);
      }

      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/talon/positions`);
        if (!res.ok) throw new Error(`positions ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setPositions(data.positions || []);
          setPositionsError(null);
        }
      } catch (e) {
        if (!cancelled) setPositionsError(e.message || 'load failed');
      } finally {
        if (!cancelled) setPositionsLoading(false);
      }

      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/talon/trades`);
        if (!res.ok) throw new Error(`trades ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setTrades(data.trades || []);
          setTradesError(null);
        }
      } catch (e) {
        if (!cancelled) setTradesError(e.message || 'load failed');
      } finally {
        if (!cancelled) setTradesLoading(false);
      }

      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/talon/equity-curve`);
        if (!res.ok) throw new Error(`equity-curve ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setCurve(data.curve || []);
          setCurveError(null);
        }
      } catch (e) {
        if (!cancelled) setCurveError(e.message || 'load failed');
      } finally {
        if (!cancelled) setCurveLoading(false);
      }
    }
    load();
    const iv = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(iv);
    };
  }, []);

  return (
    <div className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary">
      <div className="px-4 md:px-8 pt-6 pb-5" style={{ borderBottom: '1px solid rgba(56,189,248,0.18)' }}>
        <div className="max-w-[1400px] mx-auto flex items-center gap-4">
          <div
            className="w-11 h-11 rounded-xl grid place-items-center flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg, rgba(56,189,248,0.22) 0%, rgba(56,189,248,0.03) 100%)',
              boxShadow: `inset 0 0 0 1px ${THEME.primaryRing}, 0 0 32px -8px ${THEME.glow}`,
              color: THEME.primary,
            }}
          >
            <Crosshair size={22} strokeWidth={1.8} />
          </div>
          <div>
            <h1
              className="font-black tracking-[0.04em] leading-none text-[22px] md:text-[28px]"
              style={{ color: THEME.primary }}
            >
              TALON
            </h1>
            <p className="text-[12px] text-text-tertiary mt-1.5">
              $500 paper account &middot; $1-$5 squeeze stocks, +50% target, same-day exit
            </p>
          </div>
        </div>
      </div>

      <div className="px-4 md:px-8 py-6">
        <div className="max-w-[1400px] mx-auto">
          <PaperOnlyBanner />

          <StatusCards status={status || {}} loading={statusLoading} error={statusError} />

          <EquityCurveCard curve={curve} loading={curveLoading} error={curveError} />

          <OpenPositions rows={positions} loading={positionsLoading} error={positionsError} />

          <ClosedTrades rows={trades} loading={tradesLoading} error={tradesError} />

          <p className="mt-2.5 mb-6 text-[11px] text-text-tertiary leading-relaxed max-w-[900px]">
            Entry: real NBBO ask, 09:30:00-09:34:59 ET, $1-$5 band, no &ge;5% pullback off the
            running high in the first 2 minutes. Exit: first real NBBO bid &ge; entry &times;
            1.50, or the EOD closing bid if the target is never hit. Position size 20% of
            current paper equity. Source: <code>research/talon_paper_trader.py</code> in the
            squeeze repo, via a one-way Postgres mirror — same pattern as Squeeze Hunt.
          </p>
        </div>
      </div>
    </div>
  );
}
