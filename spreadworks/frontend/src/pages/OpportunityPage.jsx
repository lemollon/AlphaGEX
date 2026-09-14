// Opportunity Scanner — concrete trades from strategies that passed a real
// test. Three sections, three different maturity levels, and each one says
// so plainly:
//   1. Dividend raise (idea #69) — armed by Leron at $100/pos, max 3.
//   2. Same-day SPY 0DTE put spread — passed the honest engine, VIX-gated.
//   3. Insider buying & SEC filings (FilingSense) — live since 9/10, still
//      inside its own verdict window.
// No account-size language anywhere — every economics line is a per-unit
// number, never a dollar target scaled to a balance. Nothing here places a
// trade; this is read-only, same discipline as /hunt and /wall-scanner.
import { useCallback, useEffect, useState } from 'react';
import { Target, Calendar, TrendingDown, Eye, AlertTriangle } from 'lucide-react';
import { API_URL } from '../lib/api';

// Snapshot is now built entirely on Leron's laptop (ThetaData is a local
// terminal, unreachable from Render) and pushed here — this page only reads
// GET /api/spreadworks/opportunity. There is no /refresh anymore: nothing
// left on this side computes.
const STALE_HOURS = 6;

const GREEN = 'text-sw-green', AMBER = 'text-sw-yellow', RED = 'text-sw-red', DIM = 'text-text-tertiary';
const GREEN_BG = 'bg-sw-green-dim', AMBER_BG = 'bg-sw-yellow-dim', RED_BG = 'bg-sw-red-dim';

function fmtCT(iso, opts = {}) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-US', {
    timeZone: 'America/Chicago', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', ...opts,
  }) + ' CT';
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function money(x, d = 2) {
  if (x == null || Number.isNaN(x)) return '—';
  const sign = x < 0 ? '−' : '';
  return `${sign}$${Math.abs(x).toFixed(d)}`;
}

// ── Status pill — the fixed vocabulary from the spec: ACTIONABLE / MISSED n
// sessions late / GATE OPEN / GATE CLOSED / STALE. Never a new label.
function Pill({ tone, children }) {
  const cls = { green: `${GREEN} ${GREEN_BG}`, amber: `${AMBER} ${AMBER_BG}`,
    red: `${RED} ${RED_BG}`, dim: `${DIM} bg-bg-deep` }[tone] || `${DIM} bg-bg-deep`;
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${cls}`}>
      {children}
    </span>
  );
}

function StrategyChip({ children }) {
  return (
    <span className="inline-flex items-center rounded-md bg-accent-dim px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-accent">
      {children}
    </span>
  );
}

// ── Source tag — only rendered when a value did NOT come from ThetaData
// (the primary source). A silent card means "ThetaData"; anything else says
// so, since it's a disclosed fallback, not a preference.
function SourceTag({ source }) {
  if (!source || source === 'thetadata') return null;
  const label = source === 'yfinance' ? 'yfinance' : source === 'polygon' ? 'Polygon'
    : source === 'warehouse' ? 'warehouse' : source;
  return (
    <span className="inline-flex items-center rounded-md bg-bg-deep px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">
      via {label}
    </span>
  );
}

// ── One trade card. Every section reuses this shape: chip, mono
// instruction, a status pill, the per-unit economics line, small meta.
function TradeCard({ chip, instruction, pill, economics, meta, source }) {
  return (
    <div className="sw-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <StrategyChip>{chip}</StrategyChip>
        {pill}
        <SourceTag source={source} />
      </div>
      <div className="mt-2.5 font-mono text-[13.5px] leading-relaxed text-text-primary">
        {instruction}
      </div>
      {economics && (
        <div className="mt-2 text-[12px] text-text-secondary">{economics}</div>
      )}
      {meta && (
        <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-text-tertiary">
          {meta}
        </div>
      )}
    </div>
  );
}

function EmptyState({ children, tone = 'dim' }) {
  const cls = tone === 'amber' ? `${AMBER_BG} ${AMBER}` : tone === 'red' ? `${RED_BG} ${RED}` : 'bg-bg-deep text-text-tertiary';
  return (
    <div className={`rounded-lg px-4 py-3.5 text-[13px] ${cls}`}>{children}</div>
  );
}

function SectionHeader({ icon, title }) {
  return (
    <div className="mb-2.5 flex items-center gap-2">
      {icon}
      <h2 className="text-[15px] font-bold text-text-primary">{title}</h2>
    </div>
  );
}

function Footnote({ children }) {
  return <p className="mt-3 text-[11px] leading-relaxed text-text-tertiary">{children}</p>;
}

// ── SECTION 1 · DIVIDEND RAISE ────────────────────────────────────────────
function DividendSection({ status, rows, warnings }) {
  const warning = warnings.find((w) => w.startsWith('Dividend raise:'));

  return (
    <section className="mb-7">
      <SectionHeader icon={<Calendar size={16} className="text-accent" />} title="Dividend raise" />
      {status !== 'ok' ? (
        <EmptyState tone="amber">
          {warning ? warning.replace(/^Dividend raise:\s*/, '') : 'Dividend raise scan unavailable.'}
        </EmptyState>
      ) : rows.length === 0 ? (
        <EmptyState>No hike candidates in the last scan.</EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          {rows.map((r) => {
            const actionable = r.status === 'ACTIONABLE';
            const missedLabel = r.sessions_late === 1 ? '1 session late' : `${r.sessions_late} sessions late`;
            return (
              <TradeCard
                key={`${r.ticker}-${r.declaration_date}`}
                chip="Dividend raise"
                instruction={r.instruction}
                pill={<Pill tone={actionable ? 'green' : 'amber'}>{actionable ? 'ACTIONABLE' : `MISSED ${missedLabel}`}</Pill>}
                economics={r.economics}
                source={r.source}
                meta={[
                  <span key="hike">{r.amount != null ? `$${r.amount.toFixed(4)}` : '—'} vs {r.median_prior != null ? `$${r.median_prior.toFixed(4)}` : '—'} median ({r.ratio != null ? `${r.ratio.toFixed(2)}x` : '—'})</span>,
                  <span key="decl">declared {fmtDate(r.declaration_date)} · ex {fmtDate(r.ex_date)}</span>,
                  <span key="elig" className={r.eligibility === 'eligible' ? GREEN : r.eligibility === 'unknown' ? AMBER : RED}>
                    {r.eligibility}{r.eligibility_detail && r.eligibility !== 'eligible' ? ` (${r.eligibility_detail})` : ''}
                  </span>,
                  r.price != null && <span key="price">${r.price.toFixed(2)}/share</span>,
                  r.eligibility_source && r.eligibility_source !== 'thetadata' &&
                    <span key="eligsrc">eligibility via {r.eligibility_source}</span>,
                ].filter(Boolean)}
              />
            );
          })}
        </div>
      )}
      <Footnote>
        HALF2 passed all 5 clauses, HALF1 failed on missing data — armed by Leron 9/11.
      </Footnote>
    </section>
  );
}

// ── SECTION 2 · SAME-DAY SPY 0DTE PUT SPREAD ──────────────────────────────
function SameDaySection({ data }) {
  if (!data) {
    return (
      <section className="mb-7">
        <SectionHeader icon={<TrendingDown size={16} className="text-accent" />} title="Same-day SPY put spread" />
        <EmptyState>Loading…</EmptyState>
      </section>
    );
  }

  const { gate_status: gateStatus, gate_error: gateError, ratio, vix_prev: vixPrev,
    vix_20d_max: vix20dMax, vix_as_of: vixAsOf, vix_source: vixSource, live,
    live_strikes_error: liveErr, instruction, economics, note } = data;

  const gatePill = gateStatus === 'OPEN' ? <Pill tone="green">GATE OPEN</Pill>
    : gateStatus === 'CLOSED' ? <Pill tone="dim">GATE CLOSED</Pill>
    : <Pill tone="red">GATE UNKNOWN</Pill>;

  const meta = [
    ratio != null && <span key="ratio">VIX {vixPrev.toFixed(2)} / 20d high {vix20dMax.toFixed(2)} = {ratio.toFixed(2)}</span>,
    vixAsOf && <span key="asof">VIX as of {fmtDate(vixAsOf)}</span>,
    live && <span key="spot" className="font-mono">spot {money(live.spot)} → sell {live.short_strike}p / buy {live.long_strike}p, exp {live.exp}</span>,
    live && live.credit != null && <span key="credit" className="font-mono">credit {money(live.credit * 100)}/contract · max loss {money(live.max_loss)}</span>,
    live && live.source && live.source !== 'thetadata' &&
      <span key="chainsrc">chain via {live.source}</span>,
  ].filter(Boolean);

  return (
    <section className="mb-7">
      <SectionHeader icon={<TrendingDown size={16} className="text-accent" />} title="Same-day SPY put spread" />

      {gateStatus === 'UNKNOWN' ? (
        <EmptyState tone="amber">VIX gate unavailable — {gateError}</EmptyState>
      ) : gateStatus === 'CLOSED' ? (
        <EmptyState tone="amber">
          Gate closed — VIX at {ratio.toFixed(2)} of its 20-day high (ceiling 0.80). No spread today.
        </EmptyState>
      ) : (
        <TradeCard
          chip="Same-day SPY 0DTE"
          instruction={instruction}
          pill={gatePill}
          economics={economics}
          meta={meta}
          source={vixSource}
        />
      )}
      {liveErr && gateStatus === 'OPEN' && (
        <div className="mt-2 text-[11px] text-text-tertiary">Live strikes unavailable — {liveErr}</div>
      )}
      <Footnote>{note} — passed the honest engine 9/8.</Footnote>
    </section>
  );
}

// ── SECTION 3 · INSIDER BUYING & SEC FILINGS (FilingSense) ────────────────
function FilingSenseSection({ data }) {
  const rows = data?.rows || [];
  const scorecard = data?.scorecard;

  return (
    <section className="mb-2">
      <SectionHeader icon={<Eye size={16} className="text-accent" />} title="Insider buying & SEC filings" />
      {scorecard && (
        <div className="mb-3 text-[12px] text-text-secondary">
          All-time: {scorecard.all.right}/{scorecard.all.n} directionally right (
          {(scorecard.all.right / scorecard.all.n * 100).toFixed(0)}%), avg move {scorecard.all.avg >= 0 ? '+' : ''}{scorecard.all.avg.toFixed(2)}%.
        </div>
      )}
      {rows.length === 0 ? (
        <EmptyState>No FilingSense calls in the last 3 days.</EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          {rows.map((r) => (
            <TradeCard
              key={`${r.ticker}-${r.posted_ct}`}
              chip="FilingSense"
              instruction={r.instruction}
              pill={r.stale ? <Pill tone="amber">STALE</Pill> : null}
              meta={[
                <span key="posted">posted {fmtCT(r.posted_ct)}</span>,
                <span key="hit">feed hit rate: {r.hit_rate}</span>,
                r.ret_1d != null && <span key="ret" className={r.ret_1d >= 0 ? GREEN : RED}>1-day result {r.ret_1d >= 0 ? '+' : ''}{r.ret_1d.toFixed(2)}%</span>,
              ].filter(Boolean)}
            />
          ))}
        </div>
      )}
      <Footnote>Live since 9/10; verdict clock 9/17 — early numbers.</Footnote>
    </section>
  );
}

export default function OpportunityPage() {
  const [snapshot, setSnapshot] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/api/spreadworks/opportunity`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setSnapshot(d);
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    load();
    // No /refresh anymore — the laptop pushes on its own cadence. Polling
    // just picks up whatever it last pushed.
    const id = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [load]);

  const ageHours = snapshot?.age_seconds != null ? snapshot.age_seconds / 3600 : null;
  const isWeekday = new Date().getDay() >= 1 && new Date().getDay() <= 5;
  const isStale = ageHours != null && ageHours > STALE_HOURS && isWeekday;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[900px] px-4 pb-24 pt-6">
        <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
          <h1 className="flex items-center gap-2 text-[22px] font-bold text-text-primary">
            <Target size={19} className="text-accent" />
            Opportunity Scanner
          </h1>
        </div>
        <p className="mb-3 text-[13px] text-text-secondary">
          Concrete trades from strategies that passed a real test.
          {snapshot?.as_of_ct && ` As of ${fmtCT(snapshot.as_of_ct)} · updated from laptop.`}
        </p>

        {isStale && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-sw-yellow-dim px-4 py-3 text-[13px] text-sw-yellow">
            <AlertTriangle size={14} />
            Snapshot is {ageHours.toFixed(1)}h old — the laptop script may not have run today.
          </div>
        )}
        {snapshot?.fallback_data && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-sw-yellow-dim px-4 py-3 text-[13px] text-sw-yellow">
            <AlertTriangle size={14} />
            This snapshot used fallback data sources — ThetaData was unavailable for at least one field. See "via ..." tags below.
          </div>
        )}

        {err && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-sw-red-dim px-4 py-3 text-[13px] text-sw-red">
            <AlertTriangle size={14} />
            Failed to load: {err}
          </div>
        )}

        {!snapshot && !err ? (
          <div className="text-[13px] text-text-tertiary">Loading…</div>
        ) : snapshot ? (
          <>
            <DividendSection
              status={snapshot.dividend_raises_status}
              rows={snapshot.dividend_raises || []}
              warnings={snapshot.warnings || []}
            />
            <SameDaySection data={snapshot.sameday_spy} />
            <FilingSenseSection data={snapshot.filingsense} />
          </>
        ) : null}
      </div>
    </div>
  );
}
