// Hunt — the permanent reference for the SPY flow-confirmation signal: what
// it is saying right now, what it has actually proven, every day it has
// fired, and where its alerts land.
//
// ⛔ READ-ONLY. This page places no trade and gates nothing. It renders what
// /session and risk_confirm_state already record — see routes_risk.py's
// `_pc_z` and `confirm_step()` docstrings for the underlying math. The one
// new backend query it adds is /confirm-history, a plain SELECT over
// risk_confirm_state with no write path.
//
// 🚨 EVERY SECTION DEGRADES TO A CHIP, NEVER A CRASH. A missing table or a
// slow DB must not blank the page — each block renders its own "unavailable"
// state and the rest of the page keeps going, same discipline as /money and
// /book-risk.
import { useEffect, useState } from 'react';
import { Crosshair, AlertTriangle, ExternalLink } from 'lucide-react';
import { API_URL } from '../lib/api';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', DIM = '#8b93a7';

const S = {
  wrap: { maxWidth: 1100, margin: '0 auto', padding: '24px 16px 96px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: DIM, fontSize: 13, margin: '0 0 20px' },
  h2: { fontSize: 14, fontWeight: 700, margin: '0 0 4px' },
  card: {
    background: '#141824', border: '1px solid #232a3d', borderRadius: 12,
    padding: 16, marginBottom: 16,
  },
  small: { fontSize: 11, color: DIM },
  caption: { fontSize: 13, color: '#a8afc0', lineHeight: 1.75 },
  mono: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    fontVariantNumeric: 'tabular-nums',
  },
  th: {
    textAlign: 'left', color: DIM, fontSize: 11, padding: '8px 10px',
    letterSpacing: '.05em', textTransform: 'uppercase', whiteSpace: 'nowrap',
  },
  td: { padding: '8px 10px', fontSize: 13, borderTop: '1px solid #1c2233' },
};

const num = (x, d = 2) => (x == null || Number.isNaN(x) ? '—' : Number(x).toFixed(d));
const pct = (x, d = 3) =>
  x == null || Number.isNaN(x) ? '—' : `${x >= 0 ? '+' : ''}${Number(x).toFixed(d)}%`;
const money = (x) => (x == null ? '—' : Number(x).toFixed(2));
const ctTime = (iso) => (iso && iso.includes('T') ? iso.split('T')[1].slice(0, 5) : '—');

function Chip({ text, tone = AMBER }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 9px', borderRadius: 999, fontSize: 11, fontWeight: 700,
      color: tone, background: `${tone}18`, border: `1px solid ${tone}55`,
    }}>
      <AlertTriangle size={11} /> {text}
    </span>
  );
}

// ── SECTION 1 · TODAY'S SIGNAL STATE ─────────────────────────────────────
function SignalState({ data, err }) {
  if (err) {
    return (
      <div style={S.card}>
        <div style={S.h2}>Today's signal state</div>
        <div style={{ marginTop: 8 }}><Chip text="unavailable — could not load /session" /></div>
      </div>
    );
  }
  if (!data) {
    return <div style={S.card}><div style={S.h2}>Today's signal state</div><div style={{ ...S.small, marginTop: 8 }}>Loading…</div></div>;
  }

  const clock10 = (data.clocks || []).find((c) => c.clock === '10:00');
  const confirm = data.confirm || {};
  const flagged = clock10?.flagged;
  const captured = clock10?.captured;

  let flagTone, flagText;
  if (!captured) {
    flagTone = DIM;
    flagText = "Not captured yet — the 10:00 CT snapshot hasn't landed";
  } else if (flagged) {
    flagTone = AMBER;
    flagText = 'FLAGGED — watching for a confirmed break until 14:00 CT';
  } else {
    flagTone = GREEN;
    flagText = 'No flag today — no directional information, silence is correct';
  }

  const fired = confirm.fired_dir;
  const dirColor = fired === 'UP' ? GREEN : fired === 'DOWN' ? RED : DIM;

  return (
    <div style={S.card}>
      <div style={S.h2}>Today's signal state</div>
      <div style={{ ...S.small, marginBottom: 12 }}>All times CT.</div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {/* 10:00 CT flow-mix flag */}
        <div style={{
          flex: '1 1 320px', padding: '10px 12px', borderRadius: 8,
          background: '#0e1220', border: `1px solid ${flagTone}44`,
        }}>
          <div style={S.small}>10:00 CT flow-mix flag</div>
          <div style={{ ...S.mono, fontSize: 20, fontWeight: 700, color: flagTone, marginTop: 2 }}>
            {clock10?.putcall_z == null ? '—' : `${num(clock10.putcall_z, 2)}σ`}
          </div>
          <div style={{ fontSize: 13, fontWeight: 700, color: flagTone, marginTop: 4 }}>
            {flagText}
          </div>
        </div>

        {/* confirm state */}
        <div style={{
          flex: '1 1 320px', padding: '10px 12px', borderRadius: 8,
          background: '#0e1220', border: `1px solid ${dirColor}44`,
        }}>
          <div style={S.small}>Confirmation watcher (risk_confirm_state)</div>
          {fired ? (
            <>
              <div style={{ ...S.mono, fontSize: 20, fontWeight: 700, color: dirColor, marginTop: 2 }}>
                {fired} CONFIRMED
              </div>
              <div style={{ ...S.caption, marginTop: 4 }}>
                Fired at <b style={{ color: '#e6e9f0' }}>{ctTime(confirm.fired_at)} CT</b>,
                {' '}reference <b style={{ color: '#e6e9f0' }}>{money(confirm.ref_spot)}</b>,
                {' '}fired price <b style={{ color: '#e6e9f0' }}>{money(confirm.fired_spot)}</b>.
              </div>
            </>
          ) : (
            <div style={{ fontSize: 15, fontWeight: 700, color: DIM, marginTop: 6 }}>
              no confirm
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── SECTION 2 · THE PLAYBOOK ─────────────────────────────────────────────
// Static, and must stay honest: what is tested, what is not, and what this
// signal is actually allowed to do today.
const PIPELINE = [
  { n: 1, label: 'Found', rated: 'not rated',
    note: 'A pattern noticed in the data. Nothing has been measured against it yet.' },
  { n: 2, label: 'Proving the signal', rated: 'prediction quality, no dollars',
    note: 'Does it predict anything better than chance? hedge-dump, cascade and squeeze live here. The flow-confirm signal itself is here too — 63% continuation, tested, no money attached.' },
  { n: 3, label: 'Trade designed', rated: 'dollars/trade vs frozen bars',
    note: 'A specific ticket (strikes, size, entry/exit) is backtested against historical prices. The flow-confirm TRADE is the next pre-registered test — this stage has not run yet.' },
  { n: 4, label: 'Paper book', rated: 'starting + running balance',
    note: 'The designed trade runs live on paper money with a real ledger. EBB and EBB-PM are the only signals here today.' },
  { n: 5, label: 'Live', rated: 'real P&L vs paper shadow',
    note: 'Real capital, checked continuously against its own paper shadow to catch drift.' },
];

function Playbook() {
  return (
    <div style={S.card}>
      <div style={S.h2}>The playbook</div>

      <div style={{ ...S.caption, marginTop: 8 }}>
        When a confirmation fires, this is what has actually been tested (904
        sessions, 2023-01-03 → 2026-08-11, pooling UP and DOWN breaks):
      </div>
      <ul style={{ ...S.caption, marginTop: 6, paddingLeft: 18 }}>
        <li>~63% continuation in the fired direction (63.2%, z = +2.61)</li>
        <li>Winners run roughly 3x the give-back on losers</li>
        <li>Median ~0.2% of the move is still ahead at the moment it fires</li>
        <li>Symmetric — down breaks and up breaks perform alike, on disjoint samples</li>
        <li>Positive in all 4 years tested</li>
      </ul>

      <div style={{
        marginTop: 12, padding: '10px 12px', borderRadius: 8,
        background: `${AMBER}12`, border: `1px solid ${AMBER}55`,
      }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: AMBER }}>
          No sized SPY trade is sanctioned on this signal yet — the standalone
          money expression has never been tested. It is the next
          pre-registered test. Until it passes, this alert is context and
          direction, not an entry ticket.
        </div>
      </div>

      <div style={{ ...S.caption, marginTop: 10 }}>
        <b style={{ color: '#e6e9f0' }}>What IS sanctioned:</b> EBB's pivot
        consumes this signal automatically — its one validated use. A
        confirmation that fires against an open EBB position is the one
        thing that buys it back early.
      </div>

      {/* ── Addendum: how a signal becomes money ─────────────────────── */}
      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 2 }}>
          How a signal becomes money
        </div>
        <div style={{ ...S.small, marginBottom: 8 }}>
          Success is rated differently at every stage, and the balance only
          exists from stage 4 on. This is where the flow-confirm signal sits
          today: stage 2, proven; stage 3, not yet built.
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 560 }}>
            <thead>
              <tr>
                <th style={S.th}>stage</th>
                <th style={S.th}>rated by</th>
                <th style={S.th}>what it means here</th>
              </tr>
            </thead>
            <tbody>
              {PIPELINE.map((p) => (
                <tr key={p.n}>
                  <td style={{ ...S.td, fontWeight: 700, whiteSpace: 'nowrap' }}>
                    {p.n}. {p.label}
                  </td>
                  <td style={{ ...S.td, color: DIM, whiteSpace: 'nowrap' }}>{p.rated}</td>
                  <td style={{ ...S.td, color: '#a8afc0' }}>{p.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── SECTION 3 · FIRING HISTORY ───────────────────────────────────────────
function FiringHistory({ rows, err }) {
  if (err) {
    return (
      <div style={S.card}>
        <div style={S.h2}>Firing history</div>
        <div style={{ marginTop: 8 }}><Chip text="unavailable — could not load confirm-history" /></div>
      </div>
    );
  }
  return (
    <div style={S.card}>
      <div style={S.h2}>Firing history</div>
      <div style={{ ...S.small, marginBottom: 8 }}>
        Every recorded day of the watcher (risk_confirm_state), newest first.
        Times are CT. Outcome is the move from the fired price to the close,
        signed so positive means it kept going the fired way.
      </div>
      {!rows ? (
        <div style={{ ...S.small }}>Loading…</div>
      ) : rows.length === 0 ? (
        <div style={{ ...S.small }}>No recorded sessions yet.</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 640 }}>
            <thead>
              <tr>
                <th style={S.th}>date</th>
                <th style={S.th}>direction</th>
                <th style={S.th}>fire time</th>
                <th style={{ ...S.th, textAlign: 'right' }}>reference</th>
                <th style={{ ...S.th, textAlign: 'right' }}>close</th>
                <th style={{ ...S.th, textAlign: 'right' }}>outcome</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const dirColor = r.fired_dir === 'UP' ? GREEN
                  : r.fired_dir === 'DOWN' ? RED : DIM;
                return (
                  <tr key={r.d}>
                    <td style={{ ...S.td, ...S.mono }}>{r.d}</td>
                    <td style={{ ...S.td, fontWeight: 700, color: dirColor }}>
                      {r.fired_dir || 'no confirm'}
                    </td>
                    <td style={{ ...S.td, ...S.mono, color: DIM }}>
                      {r.fired_at ? `${ctTime(r.fired_at)} CT` : '—'}
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>{money(r.ref_spot)}</td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>{money(r.close_spot)}</td>
                    <td style={{
                      ...S.td, ...S.mono, textAlign: 'right', fontWeight: 700,
                      color: r.outcome_pct == null ? DIM : r.outcome_pct >= 0 ? GREEN : RED,
                    }}>
                      {pct(r.outcome_pct)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── SECTION 4 · ALERT DIRECTORY ──────────────────────────────────────────
function AlertDirectory() {
  const rows = [
    {
      name: 'Flow-confirm Discord (phone ping)',
      when: 'Event-driven, 10:10–14:00 CT',
      silence: 'Silence = no qualified confirm today',
    },
    {
      name: 'Nightly research-ledger pings',
      when: '~20:30 / 20:40 CT + intraday squeeze scans',
      silence: 'Silence at those times = the scheduled task did not fire — investigate',
    },
    {
      name: 'EBB verdict email',
      when: 'On change, to leron@ironforge.trade',
      silence: 'Silence = held',
    },
  ];
  return (
    <div style={S.card}>
      <div style={S.h2}>Alert directory</div>
      <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
        {rows.map((r) => (
          <div key={r.name} style={{
            padding: '10px 12px', borderRadius: 8, background: '#0e1220',
            border: '1px solid #1c2233',
          }}>
            <div style={{ fontSize: 13, fontWeight: 700 }}>{r.name}</div>
            <div style={{ ...S.small, marginTop: 2 }}>{r.when}</div>
            <div style={{ fontSize: 12, color: '#c6cbd8', marginTop: 2 }}>{r.silence}</div>
          </div>
        ))}
      </div>
      <div style={{ ...S.caption, marginTop: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
        <ExternalLink size={13} color={DIM} />
        Full research state:{' '}
        <a
          href="https://claude.ai/code/artifact/9094cc52-b306-4513-b300-2a1bb791249d"
          target="_blank" rel="noreferrer"
          style={{ color: '#22d3ee' }}
        >
          The SPY Hunt Console artifact
        </a>
      </div>
    </div>
  );
}

export default function HuntPage() {
  const [session, setSession] = useState(null);
  const [sessionErr, setSessionErr] = useState(null);
  const [history, setHistory] = useState(null);
  const [historyErr, setHistoryErr] = useState(null);

  useEffect(() => {
    let live = true;
    fetch(`${API_URL}/api/spreadworks/risk-advisor/session`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (live) setSession(d); })
      .catch((e) => { if (live) setSessionErr(String(e)); });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    let live = true;
    fetch(`${API_URL}/api/spreadworks/risk-advisor/confirm-history?limit=90`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => {
        if (!live) return;
        if (d.status === 'unavailable') { setHistoryErr('unavailable'); return; }
        setHistory(d.rows || []);
      })
      .catch((e) => { if (live) setHistoryErr(String(e)); });
    return () => { live = false; };
  }, []);

  return (
    <div className="flex-1 overflow-y-auto">
      <div style={S.wrap}>
        <h1 style={S.h1}>
          <Crosshair size={18} style={{ verticalAlign: -3, marginRight: 6 }} />
          Hunt
        </h1>
        <p style={S.sub}>
          The permanent reference for the SPY flow-confirmation signal: what
          it says right now, what it has proven, every day it has fired, and
          where its alerts land. Read-only — nothing here places a trade.
        </p>

        <SignalState data={session} err={sessionErr} />
        <Playbook />
        <FiringHistory rows={history} err={historyErr} />
        <AlertDirectory />
      </div>
    </div>
  );
}
