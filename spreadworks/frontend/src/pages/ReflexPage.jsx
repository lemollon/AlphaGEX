// REFLEX — REAL-MONEY $600 reactive-momentum stock bot.
//
// Reads REFLEX's actual Robinhood account via /api/spreadworks/reflex/* —
// same one-way-mirror pattern as /talon, except this account is REAL
// money, not paper (see routes_reflex.py, sync_reflex_to_postgres.py in
// the squeeze repo). REFLEX went live 2026-10-16 once Leron's $600 deposit
// cleared its $500 account-value gate; this page used to be 100% static
// copy claiming "zero trades ever" long after that stopped being true —
// see memory `feedback-recheck-contingent-claims-after-triggering-
// action.md`. Never hardcode a trade count/balance/live-status claim here
// again; it all comes from the mirror below.
//
// Visual shape matches BotDashboard.jsx (/bots/{id}) and TalonPage.jsx on
// purpose — same nameplate, KPI tile, equity chart chrome, tab bar.
import { useEffect, useState } from 'react';
import { AlertTriangle, Inbox, List } from 'lucide-react';
import { API_URL as API_BASE } from '../lib/api';
import { BOT_REGISTRY, BOT_THEME, STRATEGY_LABEL } from '../lib/botRegistry';
import { BotNameplate, KpiTile, money as moneyDec, pct, formatHM } from './BotDashboard';

const meta = BOT_REGISTRY.reflex;
const theme = BOT_THEME.reflex;

function money4(v) {
  if (v == null || Number.isNaN(v)) return '—';
  const sign = v < 0 ? '−' : '';
  return `${sign}$${Math.abs(v).toFixed(4)}`;
}

function pctPlain(v, decimals = 0) {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(decimals)}%`;
}

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
  target: { label: 'TARGET HIT', color: '#4ade80' },
  faded: { label: 'FADED', color: '#fb7185' },
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

function LiveMoneyBanner() {
  return (
    <div
      className="px-5 py-3 rounded-lg mb-5 flex items-start gap-3"
      style={{ background: 'rgba(251,113,133,0.08)', boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.30)' }}
    >
      <AlertTriangle size={16} color="#fb7185" className="shrink-0 mt-0.5" />
      <div className="text-[12.5px] leading-relaxed" style={{ color: '#fecaca' }}>
        <strong>LIVE — real Robinhood money, real fills.</strong>{' '}
        REFLEX went live 2026-10-16 once the account cleared its $500 minimum. Every position
        and dollar figure below is this account's real state, not a simulation.
      </div>
    </div>
  );
}

/* ── Equity curve — same card chrome as TalonPage's, step-function: one
   mark per new entry (REFLEX's local state only records account value
   when it opens a position), never a continuous intraday mark. ── */

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
        No equity snapshots yet. Each new entry writes one.
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
      <text x={padL - 8} y={yFor(first.equity) - 6} textAnchor="end" fontSize={10.5}
            fontFamily="JetBrains Mono" fill="#475569">
        {moneyDec(first.equity, { decimals: 0 })}
      </text>
      <polygon points={areaPts} fill={lineColor} opacity={0.12} />
      <polyline points={linePts} fill="none" stroke={lineColor} strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r={4.5} fill={lineColor} stroke="#0a1726" strokeWidth={2.5} />

      <g transform={`translate(${Math.min(points[points.length - 1][0] + 10, W - padR - 100)}, ${points[points.length - 1][1] - 14})`}>
        <rect x="0" y="0" width="96" height="28" rx="4" fill={lineColor} />
        <text x="48" y="18" fill="#0a1726" fontSize="12" fontFamily="JetBrains Mono" fontWeight="700" textAnchor="middle">
          {moneyDec(last.equity, { decimals: 2 })}
        </text>
      </g>

      <g transform={`translate(${padL + 4}, ${padT + 20})`}>
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
          {curve.length} snapshot{curve.length === 1 ? '' : 's'} · marks at each new entry, not continuous
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
          <th className={`${COL_HEAD} text-right`}>Qty</th>
          <th className={`${COL_HEAD} text-right`}>Cost</th>
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
              {p.qty != null ? p.qty : '—'}
            </td>
            <td className="px-3 py-2.5 text-right sw-mono text-[12.5px] text-text-secondary">{moneyDec(p.cost_usd, { decimals: 2 })}</td>
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
          <th className={`${COL_HEAD} text-right`}>Exit</th>
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

function HowItWorksItem({ children }) {
  return (
    <li className="flex items-start gap-2.5 text-[13.5px] text-text-secondary leading-relaxed">
      <span className="mt-[7px] w-1.5 h-1.5 rounded-full shrink-0" style={{ background: theme.primary }} />
      {children}
    </li>
  );
}

/* ── Page ─────────────────────────────────────────────────────────── */

export default function ReflexPage() {
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
        const res = await fetch(`${API_BASE}/api/spreadworks/reflex/status`);
        if (!res.ok) throw new Error(`status ${res.status}`);
        const data = await res.json();
        if (!cancelled) setStatus(data);
      } catch { /* keep last good status */ }
      finally { if (!cancelled) setStatusLoading(false); }

      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/reflex/positions`);
        if (!res.ok) throw new Error(`positions ${res.status}`);
        const data = await res.json();
        if (!cancelled) { setPositions(data.positions || []); setPositionsError(null); }
      } catch (e) { if (!cancelled) setPositionsError(e.message || 'load failed'); }
      finally { if (!cancelled) setPositionsLoading(false); }

      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/reflex/trades`);
        if (!res.ok) throw new Error(`trades ${res.status}`);
        const data = await res.json();
        if (!cancelled) { setTrades(data.trades || []); setTradesError(null); }
      } catch (e) { if (!cancelled) setTradesError(e.message || 'load failed'); }
      finally { if (!cancelled) setTradesLoading(false); }

      try {
        const res = await fetch(`${API_BASE}/api/spreadworks/reflex/equity-curve`);
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
            bot="reflex"
            meta={meta}
            theme={theme}
            right={
              <span className="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider" style={{ background: 'rgba(74,222,128,0.16)', color: '#4ade80' }}>
                Free
              </span>
            }
            note="Many symbols at once, any mover 10%+ on the day — not a single fixed ticker like most of the fleet."
          />
        </div>
      </div>

      <div className="px-4 md:px-8 py-6 space-y-5">
        <LiveMoneyBanner />

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

        <div>
          <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary mb-3">
            How it works
          </h2>
          <ul className="flex flex-col gap-2.5 max-w-[820px]">
            <HowItWorksItem>Scans the market in real time during regular trading hours</HowItWorksItem>
            <HowItWorksItem>
              Enters only when a stock is up 10%+ from the prior close <em>and</em> money flow is
              accelerating (not just one green candle)
            </HowItWorksItem>
            <HowItWorksItem>
              Holds through the close — exits at the real market-on-close price, never an early flinch on
              noise
            </HowItWorksItem>
            <HowItWorksItem>
              Built-in safety floor: won&rsquo;t place a single trade until the account reaches $500,
              checked fresh every few minutes
            </HowItWorksItem>
          </ul>
        </div>

        <div>
          <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary mb-3">
            The backtest
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <KpiTile
              label="Trades · symbols"
              value="2,702 trades"
              sub="605 symbols · 3.5+ years (2023-01-03 to 2026-08-28)"
            />
            <KpiTile
              label="Average return per trade"
              value="+3.52%"
              sub="+95.18 total units, real NBBO bid/ask fills"
            />
            <KpiTile
              label="Robustness"
              value="+75.13 units"
              sub="still profitable with the single best trade removed"
            />
          </div>
        </div>

        <p className="text-[13px] text-text-secondary leading-relaxed max-w-[820px]">
          Position sizing is capped at 5% per trade, max 5 positions at once — no single stock can sink the
          account.
        </p>

        <p className="text-[12px] text-text-tertiary leading-relaxed max-w-[900px]">
          {STRATEGY_LABEL[meta.strategy]} &middot; Included free with your account.
          Source: <code>run_reflex.py</code> against a real Robinhood account, via a one-way Postgres
          mirror — same pattern as Talon/Squeeze Hunt.
          {s.updated_at && <> Last synced {formatHM(s.updated_at)}.</>}
        </p>
      </div>
    </div>
  );
}
