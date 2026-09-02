/*
 * CallHistory — every call this surface made, and what SPY did next.
 *
 * 🚨 THESE ARE RECORDED CALLS, NOT RECOMPUTED ONES. The old
 * /risk-advisor/history re-derived past verdicts from today's code, so a
 * threshold change silently rewrote the past and a decaying signal could never
 * appear. Everything here comes out of an append-only table.
 *
 * 🚨 A HIT RATE WITHOUT A BASE RATE IS A LIE, so the scorecard never shows one
 * without the unconditional rate over the same days and an n beside it. A 55%
 * hit rate in a market that rises 55% of the time is worth nothing, and on its
 * own it reads like a win.
 */
import { useEffect, useState } from 'react';
import { API_URL } from '../lib/api';

const DIM = '#8b93a7';
const GREEN = '#38d39f';
const RED = '#ff5c7a';
const AMBER = '#f5b942';
const LINE = '#1c2233';
const ACTIVE = '#2b3750';

const RANGES = [
  { key: 'week', label: 'Week' },
  { key: 'month', label: 'Month' },
  { key: 'year', label: 'Year' },
];

// Colour a verdict by what it tells you to DO, not by which page it came from.
const TONE = {
  SELL_PREMIUM: GREEN, normal: GREEN, 'NOT ARMED': DIM,
  NEUTRAL: DIM, UNKNOWN: DIM, 'WAITING FOR THE 10:00 SNAPSHOT': DIM,
  SQUEEZE_WATCH: AMBER, skip_entry: AMBER, 'ARMED — WAITING FOR A SIDE': AMBER,
  NO_SELL: RED, stand_down: RED, 'DOWN CONFIRMED': RED, 'UP CONFIRMED': GREEN,
};

const pct = (v, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`;
const money = (v) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(2);
const clockOf = (iso) => (iso && iso.includes('T') ? iso.split('T')[1].slice(0, 5) : '—');

export default function CallHistory({ surface, title = 'Call history' }) {
  const [range, setRange] = useState('month');
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    setErr(null);
    const q = surface ? `surface=${encodeURIComponent(surface)}&` : '';
    fetch(`${API_URL}/api/spreadworks/calls?${q}range=${range}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => { if (alive) { setData(j); setBusy(false); } })
      .catch((e) => { if (alive) { setErr(e.message); setBusy(false); } });
    return () => { alive = false; };
  }, [surface, range]);

  const calls = data?.calls || [];
  const sc = data?.scorecard || {};

  return (
    <div style={{ background: '#0e1220', border: `1px solid ${LINE}`,
                  borderRadius: 10, padding: 14, marginTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10,
                    flexWrap: 'wrap', marginBottom: 4 }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>{title}</span>
        <span style={{ fontSize: 12, color: DIM }}>
          every call as it was made, including same-day changes
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          {RANGES.map((r) => (
            <button key={r.key} onClick={() => setRange(r.key)}
                    style={{
                      background: range === r.key ? '#1b2437' : 'transparent',
                      color: range === r.key ? '#e8ecf5' : DIM,
                      border: `1px solid ${range === r.key ? ACTIVE : LINE}`,
                      borderRadius: 6, padding: '3px 10px', fontSize: 12,
                      cursor: 'pointer',
                    }}>{r.label}</button>
          ))}
        </div>
      </div>

      {busy && <div style={{ fontSize: 12, color: DIM }}>loading…</div>}
      {err && <div style={{ fontSize: 12, color: RED }}>could not load: {err}</div>}

      {!busy && !err && calls.length === 0 && (
        <div style={{ fontSize: 12, color: DIM, padding: '10px 0' }}>
          No calls recorded in this window yet. The log starts filling from the
          first sample after deploy — it is not back-filled, because a
          reconstructed call is not the call that was made.
        </div>
      )}

      {/* --- the scorecard, always with the base rate beside it --- */}
      {!busy && sc.verdicts?.length > 0 && (
        <div style={{ margin: '10px 0 14px' }}>
          <div style={{ fontSize: 12, color: DIM, marginBottom: 6 }}>
            Scored over {sc.days} session{sc.days === 1 ? '' : 's'}. SPY rose on{' '}
            {sc.base_rate_up === null ? '—' : `${(sc.base_rate_up * 100).toFixed(0)}%`} of them
            {sc.big_move_cut_pct != null &&
              ` · a "big" day here is ±${sc.big_move_cut_pct.toFixed(2)}%`}.
          </div>
          <div style={{ display: 'grid', gap: 4 }}>
            {sc.verdicts.map((v) => (
              <div key={v.verdict} style={{
                display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                fontSize: 12, padding: '4px 8px', borderRadius: 6,
                background: '#0b0f1a', border: `1px solid ${LINE}`,
              }}>
                <b style={{ color: TONE[v.verdict] || DIM, minWidth: 150 }}>{v.verdict}</b>
                <span style={{ color: DIM }}>n={v.n}</span>
                {v.hit_rate === null ? (
                  <span style={{ color: DIM }}>no directional claim — not scored</span>
                ) : (
                  <>
                    <span>hit {(v.hit_rate * 100).toFixed(0)}%</span>
                    <span style={{ color: DIM }}>base {(v.base_rate * 100).toFixed(0)}%</span>
                    <span style={{ color: v.edge > 0 ? GREEN : v.edge < 0 ? RED : DIM }}>
                      edge {v.edge > 0 ? '+' : ''}{(v.edge * 100).toFixed(0)}pts
                    </span>
                  </>
                )}
                <span style={{ color: DIM }}>avg move {pct(v.avg_move_pct)}</span>
                {v.thin && (
                  <span style={{ color: AMBER }}>
                    too thin to mean anything yet
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* --- the calls themselves --- */}
      {!busy && calls.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
            <thead>
              <tr style={{ color: DIM, textAlign: 'left' }}>
                <th style={{ padding: '6px 8px' }}>Date</th>
                <th style={{ padding: '6px 8px' }}>Time CT</th>
                {!surface && <th style={{ padding: '6px 8px' }}>Page</th>}
                <th style={{ padding: '6px 8px' }}>Call</th>
                <th style={{ padding: '6px 8px', textAlign: 'right' }}>SPY that day</th>
                <th style={{ padding: '6px 8px', textAlign: 'right' }}>Close</th>
                <th style={{ padding: '6px 8px', textAlign: 'right' }}>Next open</th>
                <th style={{ padding: '6px 8px', textAlign: 'right' }}>Overnight</th>
                <th style={{ padding: '6px 8px' }} />
              </tr>
            </thead>
            <tbody style={{ fontVariantNumeric: 'tabular-nums' }}>
              {calls.map((c) => (
                <tr key={c.id} style={{ borderTop: `1px solid ${LINE}` }}>
                  <td style={{ padding: '6px 8px' }}>{c.trade_date}</td>
                  <td style={{ padding: '6px 8px', color: DIM }}>{clockOf(c.call_ts)}</td>
                  {!surface && <td style={{ padding: '6px 8px', color: DIM }}>{c.surface}</td>}
                  <td style={{ padding: '6px 8px', color: TONE[c.verdict] || '#e8ecf5',
                               fontWeight: 600 }}>{c.verdict}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right',
                               color: c.spy_day_pct > 0 ? GREEN : c.spy_day_pct < 0 ? RED : DIM }}>
                    {pct(c.spy_day_pct)}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'right' }}>{money(c.spy_close)}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right' }}>{money(c.spy_next_open)}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right',
                               color: c.spy_overnight_pct > 0 ? GREEN
                                    : c.spy_overnight_pct < 0 ? RED : DIM }}>
                    {/* 🚨 The overnight gap only belongs to the LAST call of the
                        day — that is the one that was standing at the bell.
                        Showing it on a 10am call that was later replaced would
                        credit it with a window it never held. */}
                    {c.last_of_day ? pct(c.spy_overnight_pct) : '—'}
                  </td>
                  <td style={{ padding: '6px 8px', color: DIM }}>
                    {c.superseded_by && (
                      <span title={`replaced by ${c.superseded_by}`}>
                        → {c.superseded_by}
                      </span>
                    )}
                    {c.data_age_min > 90 && !c.structural_lag && (
                      <span style={{ color: AMBER, marginLeft: 6 }}
                            title="the input was already this old when the call was made">
                        stale {Math.round(c.data_age_min / 60)}h
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* --- where the surfaces split --- */}
      {!busy && !surface && data?.disagreements?.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 12 }}>
          <div style={{ color: DIM, marginBottom: 4 }}>
            Days the pages disagreed ({data.disagreements.length}). Two signals
            that always agree add nothing by being stacked — these are the days
            the second one earned its place.
          </div>
          {data.disagreements.slice(0, 10).map((d) => (
            <div key={d.trade_date} style={{ color: '#e8ecf5' }}>
              {d.trade_date}:{' '}
              {Object.entries(d.verdicts).map(([s, v]) => `${s} ${v}`).join(' · ')}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
