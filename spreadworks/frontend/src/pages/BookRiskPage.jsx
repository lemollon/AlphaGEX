// Book Risk — portfolio-level exposure, drawdown, concentration and config
// drift across the whole fleet. Distinct from the Risk Advisor, which grades
// market regime and says nothing about the book.
// All spacing inline (Tailwind p-*/m-* are zeroed app-wide).
import { useEffect, useState } from 'react';
import { ShieldAlert, PieChart } from 'lucide-react';
import { API_URL } from '../lib/api';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', BLUE = '#60a5fa', DIM = '#8b93a7';
const S = {
  wrap: { maxWidth: 1100, margin: '0 auto', padding: '24px 16px 96px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: DIM, fontSize: 13, margin: '0 0 20px' },
  card: { background: '#141824', border: '1px solid #232a3d', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardTitle: { fontSize: 13, fontWeight: 700, marginBottom: 10 },
  th: { textAlign: 'left', color: DIM, fontSize: 12, padding: '6px 10px' },
  td: { padding: '6px 10px', fontSize: 13, borderTop: '1px solid #1c2233' },
  small: { fontSize: 11, color: DIM },
  big: { fontSize: 20, fontWeight: 700 },
};

function InfoTip({ text }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: 'relative', display: 'inline-block', marginLeft: 6 }}
          onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <span style={{ cursor: 'help', color: DIM, fontSize: 11, border: `1px solid ${DIM}66`,
                     borderRadius: '50%', width: 14, height: 14, display: 'inline-flex',
                     alignItems: 'center', justifyContent: 'center', verticalAlign: 'middle' }}>i</span>
      {open && (
        <span style={{ position: 'absolute', zIndex: 30, top: 18, left: -8, width: 290,
                       background: '#0e1220', border: '1px solid #2a3145', borderRadius: 8,
                       padding: '10px 12px', fontSize: 12, lineHeight: 1.55, color: '#c6cbd8',
                       fontWeight: 400, boxShadow: '0 6px 20px rgba(0,0,0,.5)' }}>{text}</span>
      )}
    </span>
  );
}

// money(x) -> "$1,234" (no cents above $1,000, 2dp below), "-$1,234" for
// negatives, "—" for null. Never date math — this is pure number formatting.
function money(x) {
  if (x == null || Number.isNaN(x)) return '—';
  const neg = x < 0;
  const abs = Math.abs(x);
  const body = abs >= 1000
    ? abs.toLocaleString('en-US', { maximumFractionDigits: 0 })
    : abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return (neg ? '-$' : '$') + body;
}

function pct(x, d = 1) { return x == null ? '—' : (100 * x).toFixed(d) + '%'; }

// Formats an integer second count from the backend into a human label. NEVER
// do date math in the browser on these API timestamps — the backend already
// computed the age; this function only formats the number it gave us.
function ago(seconds) {
  if (seconds == null) return '—';
  // A timestamp ahead of the server clock is a timezone fault, not freshness.
  // Formatting it as "just now" is how a dead bot ends up looking alive.
  if (seconds < -60) return 'TIMESTAMP AHEAD OF CLOCK';
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m ago`;
  }
  return `${Math.floor(seconds / 86400)}d ago`;
}

function until(seconds) {
  if (seconds == null) return '—';
  if (seconds <= 0) return 'now';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

// Colour scale shared by drawdown-limit-used and correlation r.
function ddColor(used) {
  if (used == null) return DIM;
  return used > 0.8 ? RED : used > 0.5 ? AMBER : GREEN;
}
function corrColor(r) {
  if (r == null) return DIM;
  const a = Math.abs(r);
  return a >= 0.5 ? RED : a >= 0.25 ? AMBER : GREEN;
}

function ArmedChip({ enabled }) {
  return (
    <span style={{ fontSize: 10, fontWeight: 700, color: enabled ? GREEN : DIM,
                   border: `1px solid ${enabled ? GREEN : DIM}55`, borderRadius: 4,
                   padding: '1px 6px' }}>
      {enabled ? 'ARMED' : 'paused'}
    </span>
  );
}

// Freshness chip rendered in every block's card header — the single place
// staleness surfaces, so the reader never has to infer it from a stuck number.
function Fresh({ f }) {
  if (!f) return null;
  if (f.as_of_ct == null) {
    return <span style={{ ...S.small, float: 'right' }}>no data yet</span>;
  }
  const label = f.next_update_ct ?? f.cadence;
  const bad = f.stale || f.clock_mismatch;
  return (
    <span style={{ float: 'right', fontSize: 11, color: bad ? RED : DIM, fontWeight: bad ? 700 : 400 }}>
      {f.clock_mismatch ? '⚠ CLOCK MISMATCH · ' : f.stale ? 'STALE · ' : ''}
      as of {f.as_of_ct} CT · {ago(f.age_seconds)} · next {label}
      <InfoTip text={`source: ${f.source} · cadence: ${f.cadence}`} />
    </span>
  );
}

export default function BookRiskPage() {
  const [payload, setPayload] = useState(null);
  const [err, setErr] = useState(null);
  const [tick, setTick] = useState(0); // 10s re-render so countdowns move between 30s polls

  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const res = await fetch(`${API_URL}/api/spreadworks/book-risk`);
        const data = await res.json();
        if (live) setPayload(data);
      } catch (e) { if (live) setErr(String(e)); }
    };
    load();
    const t = setInterval(load, 30 * 1000);
    const t2 = setInterval(() => setTick(x => x + 1), 10 * 1000);
    return () => { live = false; clearInterval(t); clearInterval(t2); };
  }, []);

  if (err) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Book Risk unavailable: {err}</div></div></div>;
  if (!payload) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Loading…</div></div></div>;

  void tick; // forces the countdown re-render; the value itself is unused

  const { clock, exposure, drawdown, concentration, config_audit, unavailable } = payload;

  const expBots = [...(exposure?.bots || [])].sort((a, b) => (b.defined_risk ?? 0) - (a.defined_risk ?? 0));
  const ddBots = [...(drawdown?.bots || [])].sort((a, b) => (b.limit_used_pct ?? -1) - (a.limit_used_pct ?? -1));
  const totals = exposure?.totals || {};
  const fleet = drawdown?.fleet || {};

  return (
    <div className="flex-1 overflow-y-auto">
      <div style={S.wrap}>
        <h1 style={S.h1}>Book Risk</h1>
        <p style={S.sub}>
          Portfolio-level exposure, drawdown, concentration and config drift across the whole fleet.
          Distinct from the Risk Advisor, which grades market regime and says nothing about the book.
        </p>

        {/* 0 ─ GLOBAL FRESHNESS BANNER */}
        {clock && (
          <div style={{ ...S.card, borderColor: (clock.frozen ? AMBER : GREEN) + '88',
                        borderWidth: 2, display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <ShieldAlert size={26} color={clock.frozen ? AMBER : GREEN} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <div style={{ fontSize: 17, fontWeight: 700, color: clock.frozen ? AMBER : GREEN }}>
                {clock.frozen ? 'FROZEN — nothing on this page is moving.' : 'LIVE — scan loop running'}
              </div>
              {clock.frozen ? (
                <div style={{ fontSize: 13.5, marginTop: 6, color: '#c6cbd8' }}>
                  {clock.frozen_note}
                  <div style={{ marginTop: 4 }}>
                    Next scan: {clock.next_scan_ct} CT (in {until(clock.next_scan_in_seconds)})
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: 13.5, marginTop: 6, color: '#c6cbd8' }}>
                  next scan in {until(clock.next_scan_in_seconds)}
                  <div style={{ ...S.small, marginTop: 4 }}>
                    scan window {clock.scan_window_ct} · settle window {clock.settle_window_ct}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 1 ─ BOOK EXPOSURE NOW */}
        <div style={S.card}>
          <div style={S.cardTitle}>
            Book exposure now
            <Fresh f={exposure?.fresh} />
          </div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 14 }}>
            {[
              ['Defined risk', money(totals.defined_risk), totals.over_budget ? RED : undefined,
                'Sum of every open position\'s structural max loss, in dollars. positions.max_loss is already the total for the whole position, not per contract.'],
              ['Remaining downside', money(totals.remaining_downside), undefined,
                'What you can still lose from TODAY\'S mark down to the structural floor — not from entry. A position already down $80 of a $400 floor has $320 left to give.'],
              ['One-day budget', money(totals.one_day_budget), undefined, null],
              ['Book equity', money(totals.equity_mtm), undefined, null],
              ['Armed', `${totals.bots_armed ?? '—'}/${totals.bots_total ?? '—'}`, undefined, null],
              ['Open positions', totals.open_positions ?? '—', undefined, null],
            ].map(([label, val, color, tip]) => (
              <div key={label} style={{ minWidth: 130 }}>
                <div style={S.small}>{label}{tip && <InfoTip text={tip} />}</div>
                <div style={{ ...S.big, color }}>{val}</div>
              </div>
            ))}
          </div>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>
              <th style={S.th}>bot</th><th style={S.th}>armed</th><th style={S.th}>ticker</th>
              <th style={S.th}>open pos</th><th style={S.th}>contracts</th>
              <th style={S.th}>defined risk</th><th style={S.th}>unrealized P&amp;L</th>
              <th style={S.th}>remaining downside</th><th style={S.th}>% of capital</th>
              <th style={S.th}>1-day budget</th><th style={S.th}>mark age</th>
            </tr></thead>
            <tbody>
              {expBots.map(b => {
                const markAge = b.oldest_mark_age_seconds;
                return (
                  <tr key={b.bot} style={{ background: b.over_budget ? AMBER + '18' : undefined }}>
                    <td style={{ ...S.td, fontWeight: 600 }}>{b.display}</td>
                    <td style={S.td}><ArmedChip enabled={b.enabled} /></td>
                    <td style={S.td}>{b.ticker || '—'}</td>
                    <td style={S.td}>{b.open_positions}</td>
                    <td style={S.td}>{b.contracts}</td>
                    <td style={{ ...S.td, color: b.over_budget ? RED : undefined, fontWeight: 600 }}>{money(b.defined_risk)}</td>
                    <td style={{ ...S.td, color: (b.unrealized_pnl ?? 0) >= 0 ? GREEN : RED }}>{money(b.unrealized_pnl)}</td>
                    <td style={S.td}>{money(b.remaining_downside)}</td>
                    <td style={S.td}>{pct(b.risk_pct_of_capital)}</td>
                    <td style={S.td}>{money(b.one_day_budget)}</td>
                    <td style={{ ...S.td, color: markAge != null && markAge > 300 ? RED : undefined }}>{ago(markAge)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* 2 ─ DRAWDOWN + KILL LINE */}
        <div style={S.card}>
          <div style={S.cardTitle}>
            Drawdown + kill line
            <Fresh f={drawdown?.fresh} />
          </div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10 }}>
            <div style={{ minWidth: 130 }}>
              <div style={S.small}>Current DD</div>
              <div style={{ ...S.big, color: (fleet.current_dd ?? 0) < 0 ? RED : undefined }}>
                {money(fleet.current_dd)} <span style={{ fontSize: 13 }}>({pct(fleet.current_dd_pct)})</span>
              </div>
            </div>
            <div style={{ minWidth: 130 }}>
              <div style={S.small}>Peak</div>
              <div style={S.big}>{money(fleet.peak)}</div>
              <div style={S.small}>{fleet.peak_date || '—'}</div>
            </div>
            <div style={{ minWidth: 130 }}>
              <div style={S.small}>Days since high water</div>
              <div style={S.big}>{fleet.days_since_high_water ?? '—'}</div>
            </div>
            <div style={{ minWidth: 130 }}>
              <div style={S.small}>Worst-ever DD</div>
              <div style={{ ...S.big, color: RED }}>{money(fleet.max_dd)} <span style={{ fontSize: 13 }}>({pct(fleet.max_dd_pct)})</span></div>
              <div style={S.small}>{fleet.max_dd_date || '—'}</div>
            </div>
          </div>
          {drawdown?.note && <div style={{ ...S.small, marginBottom: 12 }}>{drawdown.note}</div>}

          <div style={{ ...S.small, marginBottom: 4 }}>
            Fleet limit used (not enforced) — {pct(fleet.limit_used_pct)} of {pct(drawdown?.limit?.pct)}
          </div>
          <div style={{ background: '#1a2030', borderRadius: 6, height: 10, overflow: 'hidden' }}>
            <div style={{ width: Math.min(100, 100 * (fleet.limit_used_pct ?? 0)) + '%', height: '100%',
                          background: ddColor(fleet.limit_used_pct) }} />
          </div>
          {drawdown?.limit?.note && (
            <div style={{ fontSize: 12, color: AMBER, fontWeight: 600, marginTop: 8 }}>
              {drawdown.limit.note}
            </div>
          )}

          <table style={{ borderCollapse: 'collapse', width: '100%', marginTop: 14 }}>
            <thead><tr>
              <th style={S.th}>bot</th><th style={S.th}>armed</th>
              <th style={S.th}>current DD $</th><th style={S.th}>current DD %</th>
              <th style={S.th}>days since HW</th><th style={S.th}>worst DD</th>
              <th style={S.th}>limit used %</th>
            </tr></thead>
            <tbody>
              {ddBots.map(b => (
                <tr key={b.bot}>
                  <td style={{ ...S.td, fontWeight: 600 }}>{b.display}</td>
                  <td style={S.td}><ArmedChip enabled={b.enabled} /></td>
                  <td style={{ ...S.td, color: (b.current_dd ?? 0) < 0 ? RED : undefined }}>{money(b.current_dd)}</td>
                  <td style={S.td}>{pct(b.current_dd_pct)}</td>
                  <td style={S.td}>{b.days_since_high_water ?? '—'}</td>
                  <td style={S.td}>{money(b.max_dd)} ({pct(b.max_dd_pct)})</td>
                  <td style={{ ...S.td, color: ddColor(b.limit_used_pct), fontWeight: 700 }}>{pct(b.limit_used_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* 3 ─ CORRELATION + CONCENTRATION */}
        <div style={S.card}>
          <div style={S.cardTitle}>
            <PieChart size={13} style={{ verticalAlign: -2 }} /> Correlation + concentration
            <InfoTip text="Two bots on SPY and XSP are not diversified just because the tickers differ — they are one bet. Correlation is measured on daily realized P&L, paired only on days both bots actually closed a trade." />
            <Fresh f={concentration?.fresh} />
          </div>

          {concentration?.worst_book_day && (
            <div style={{ ...S.card, background: '#1a1420', border: `1px solid ${RED}44`, marginBottom: 14 }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: RED }}>
                Worst day the book has had (actually happened): {concentration.worst_book_day.date}, {money(concentration.worst_book_day.pnl)}
              </div>
              <div style={{ ...S.small, marginTop: 6 }}>
                {(concentration.worst_book_day.by_bot || []).map(x => `${x.bot} ${money(x.pnl)}`).join(' · ')}
              </div>
            </div>
          )}

          {/* Only pairs that actually carry a number get a row. With 25 bots
              the full list is ~300 entries and on a young fleet nearly all of
              them read "need 20, have 1" — rendering them all buried the
              measured pairs and pushed the concentration bars off screen.
              The rest collapse into the one line below. */}
          {(() => {
            const c = concentration?.correlation || {};
            const measured = (c.pairs || []).filter(p => !p.underpowered);
            return (<>
              {measured.length > 0 ? (
                <table style={{ borderCollapse: 'collapse', width: '100%', marginBottom: 8 }}>
                  <thead><tr>
                    <th style={S.th}>bot A</th><th style={S.th}>bot B</th>
                    <th style={S.th}>shared days</th><th style={S.th}>r</th>
                  </tr></thead>
                  <tbody>
                    {measured.map((p, i) => (
                      <tr key={i}>
                        <td style={S.td}>{p.a}</td>
                        <td style={S.td}>{p.b}</td>
                        <td style={S.td}>{p.n_days}</td>
                        <td style={{ ...S.td, color: corrColor(p.r), fontWeight: 700 }}>
                          {p.r != null ? p.r.toFixed(2) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div style={{ fontSize: 13, color: AMBER, fontWeight: 600, marginBottom: 8 }}>
                  No pair has enough shared history to measure correlation yet —
                  so this book's diversification is currently UNKNOWN, not proven.
                </div>
              )}
              {c.underpowered_pairs > 0 && (
                <div style={{ ...S.small, marginBottom: 8 }}>
                  {c.underpowered_pairs} of {c.total_pairs} pairs skipped —
                  under {c.min_paired_days} shared trading days. The closest pair has{' '}
                  {c.max_shared_days_among_underpowered}. They reappear here as they age.
                </div>
              )}
            </>);
          })()}
          {concentration?.correlation?.note && <div style={{ ...S.small, marginBottom: 16 }}>{concentration.correlation.note}</div>}

          {[['By cluster', concentration?.by_cluster], ['By ticker', concentration?.by_ticker], ['By strategy', concentration?.by_strategy]].map(([title, rows]) => {
            const arr = rows || [];
            const maxShare = arr.length ? arr[0].share : 0;
            return (
              <div key={title} style={{ marginBottom: 14 }}>
                <div style={{ ...S.small, marginBottom: 6, fontWeight: 600, color: '#c6cbd8' }}>{title}</div>
                {arr.map(r => (
                  <div key={r.key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ width: 110, fontSize: 12 }}>{r.key}</span>
                    <div style={{ flex: 1, background: '#1a2030', borderRadius: 6, height: 10, overflow: 'hidden' }}>
                      <div style={{
                        width: Math.min(100, 100 * (r.share ?? 0)) + '%', height: '100%',
                        background: (r.share === maxShare && r.share > 0.6) ? RED : BLUE,
                      }} />
                    </div>
                    <span style={{ width: 60, fontSize: 12, textAlign: 'right' }}>{pct(r.share)}</span>
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        {/* 4 ─ CONFIG AUDIT */}
        <div style={S.card}>
          <div style={S.cardTitle}>
            Config audit
            <Fresh f={config_audit?.fresh} />
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10,
                        color: config_audit?.drifted > 0 ? RED : GREEN }}>
            {config_audit?.drifted ?? 0} of {(config_audit?.bots || []).length} bots have drifted from their validated config
          </div>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>
              <th style={S.th}>bot</th><th style={S.th}>armed</th><th style={S.th}>updated</th>
              <th style={S.th}>max contracts</th><th style={S.th}>max concurrent</th>
              <th style={S.th}>SL %</th><th style={S.th}>PT %</th><th style={S.th}>EOD close</th>
              <th style={S.th}>drift</th>
            </tr></thead>
            <tbody>
              {(config_audit?.bots || []).map(b => (
                <tr key={b.bot}>
                  <td style={{ ...S.td, fontWeight: 600 }}>{b.display}</td>
                  <td style={S.td}><ArmedChip enabled={b.enabled} /></td>
                  <td style={S.td}>{b.updated_at_ct || '—'}</td>
                  <td style={S.td}>{b.max_contracts}</td>
                  <td style={S.td}>{b.max_concurrent_positions}</td>
                  <td style={S.td}>{pct(b.sl_pct)}</td>
                  <td style={S.td}>{pct(b.pt_pct)}</td>
                  <td style={S.td}>{b.eod_close_ct}</td>
                  <td style={S.td}>
                    {b.clean ? (
                      <span style={{ color: GREEN, fontWeight: 600 }}>matches validated cell</span>
                    ) : (
                      (b.drift || []).map((d, i) => (
                        <div key={i} style={{ marginBottom: 2 }}>
                          {d.key}: <span style={{ color: RED, fontWeight: 600 }}>{String(d.live)}</span>
                          {' → '}<span style={{ color: DIM }}>{String(d.validated)}</span>
                        </div>
                      ))
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {config_audit?.validated_source && <div style={{ ...S.small, marginTop: 8 }}>{config_audit.validated_source}</div>}
        </div>

        {/* 5 ─ UNAVAILABLE */}
        {unavailable && unavailable.length > 0 && (
          <div style={{ ...S.card, border: `1px solid ${RED}55` }}>
            <div style={{ ...S.cardTitle, color: RED }}>
              Bots that could not be read — their risk is NOT included in the totals above
            </div>
            {unavailable.map((u, i) => (
              <div key={i} style={{ fontSize: 13, marginBottom: 4 }}>
                <b>{u.bot}</b>: {u.reason}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
