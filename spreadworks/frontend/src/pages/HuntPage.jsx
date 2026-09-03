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
import { Fragment, useEffect, useState } from 'react';
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

// ── SECTION 0 · THE ACTION BOX ───────────────────────────────────────────
// The single answer to "what do I do right now", computed server-side by
// routes_risk.build_action() and reused verbatim (via action_sentence) in
// the confirm Discord/ntfy alert — the page and the push can never
// disagree. Always exactly one of NO_ACTION / ACT_NOW / DONE. This trade is
// PAPER on every surface; the word appears in every ACT_NOW/DONE headline.
function ActionBox({ data, err }) {
  if (err) {
    return (
      <div style={S.card}>
        <div style={S.h2}>Action</div>
        <div style={{ marginTop: 8 }}><Chip text="unavailable — could not load /session" /></div>
      </div>
    );
  }
  if (!data) {
    return <div style={S.card}><div style={S.h2}>Action</div><div style={{ ...S.small, marginTop: 8 }}>Loading…</div></div>;
  }

  const action = data.action || {};
  const confirm = data.confirm || {};
  const state = action.state;
  const dir = confirm.fired_dir;
  const trade = action.trade;

  let color;
  if (state === 'ACT_NOW') {
    color = dir === 'UP' ? GREEN : dir === 'DOWN' ? RED : AMBER;
  } else if (state === 'DONE') {
    color = '#38bdf8';
  } else if (action.headline && action.headline.startsWith('ARMED')) {
    color = AMBER;
  } else {
    color = DIM;
  }

  return (
    <div style={{ ...S.card, border: `1px solid ${color}55` }}>
      <div style={S.h2}>Action</div>
      <div style={{ fontSize: 20, fontWeight: 800, color, marginTop: 6, lineHeight: 1.3 }}>
        {action.headline || '—'}
      </div>
      {action.detail && <div style={{ ...S.caption, marginTop: 8 }}>{action.detail}</div>}
      {action.why && <div style={{ ...S.small, marginTop: 6 }}>{action.why}</div>}
      <div style={{ ...S.small, marginTop: 10 }}>
        mode: {action.mode || 'PAPER'} · next check: {action.next_check || '—'}
      </div>

      {trade && (
        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 620 }}>
            <thead>
              <tr>
                <th style={S.th}>expiry</th>
                <th style={S.th}>long strike</th>
                <th style={S.th}>short strike</th>
                <th style={{ ...S.th, textAlign: 'right' }}>contracts</th>
                <th style={{ ...S.th, textAlign: 'right' }}>debit</th>
                <th style={S.th}>quoted at</th>
                <th style={{ ...S.th, textAlign: 'right' }}>P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ ...S.td, ...S.mono }}>{trade.expiry || '—'}</td>
                <td style={{ ...S.td, ...S.mono }}>
                  {trade.long_strike == null ? '—' : num(trade.long_strike, 0)}
                </td>
                <td style={{ ...S.td, ...S.mono }}>
                  {trade.short_strike == null ? '—' : num(trade.short_strike, 0)}
                </td>
                <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                  {trade.contracts == null ? '—' : trade.contracts}
                </td>
                <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                  {trade.debit == null ? '—' : `$${money(trade.debit)}`}
                </td>
                <td style={{ ...S.td, ...S.mono, color: DIM }}>
                  {trade.quote_at ? `${ctTime(trade.quote_at)} CT` : '—'}
                </td>
                <td style={{
                  ...S.td, ...S.mono, textAlign: 'right', fontWeight: 700,
                  color: trade.pnl == null ? DIM : trade.pnl >= 0 ? GREEN : RED,
                }}>
                  {trade.pnl == null ? '—' : `${trade.pnl >= 0 ? '+' : ''}$${money(trade.pnl)}`}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
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

// ── SECTION 1.5 · LIVE FLOW TAPE (descriptive only) ──────────────────────
// /session's flow_tape — SPY chain volume captured every 10 minutes from
// 08:40 CT by the standalone risk_flow_capture job (backend/risk_alerts.py
// run_flow_capture), which exists to fill the gap confirm_check's 10:10
// start leaves (the 2026-09-03 blind spot: SPY ran +1% before the first
// reading of the day ever landed). NEVER a call — every label carries
// "unvalidated — descriptive" and none says buy/sell/call/put/direction.
// The confirm signal in SignalState above is the only thing on this page
// allowed to make one.
function FlowTape({ data, err }) {
  if (err) {
    return (
      <div style={S.card}>
        <div style={S.h2}>Live flow tape (from 08:40 CT)</div>
        <div style={{ marginTop: 8 }}><Chip text="unavailable — could not load /session" /></div>
      </div>
    );
  }
  if (!data) {
    return (
      <div style={S.card}>
        <div style={S.h2}>Live flow tape (from 08:40 CT)</div>
        <div style={{ ...S.small, marginTop: 8 }}>Loading…</div>
      </div>
    );
  }

  const tape = data.flow_tape || [];
  const meta = data.flow_tape_meta || {};
  const isBurst = typeof meta.latest_read === 'string' && meta.latest_read.includes('burst');

  return (
    <div style={S.card}>
      <div style={S.h2}>Live flow tape (from 08:40 CT)</div>

      {meta.latest_read && (
        <div style={{ marginTop: 8 }}>
          <Chip text={meta.latest_read} tone={isBurst ? AMBER : DIM} />
        </div>
      )}

      <div style={{ ...S.small, marginTop: 8 }}>
        {meta.first_capture && meta.last_capture
          ? `first capture ${meta.first_capture} · last capture ${meta.last_capture} · ${meta.n_slots} slot${meta.n_slots === 1 ? '' : 's'}`
          : 'no capture yet today'}
      </div>
      <div style={{ ...S.caption, marginTop: 4, color: AMBER }}>
        Descriptive only — unvalidated. The only thing on this page allowed
        to make a call is the confirm signal above.
      </div>

      {tape.length === 0 ? (
        <div style={{ marginTop: 12 }}>
          <Chip text="no flow captured yet today — capture runs every 10 min from 08:40 CT" tone={DIM} />
        </div>
      ) : (
        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 960 }}>
            <thead>
              <tr>
                <th style={S.th}>time</th>
                <th style={{ ...S.th, textAlign: 'right' }}>spot</th>
                <th style={{ ...S.th, textAlign: 'right' }}>0DTE calls (vol, Δ)</th>
                <th style={{ ...S.th, textAlign: 'right' }}>0DTE puts (vol, Δ)</th>
                <th style={{ ...S.th, textAlign: 'right' }}>0DTE call-buy %</th>
                <th style={{ ...S.th, textAlign: 'right' }}>0DTE put-buy %</th>
                <th style={{ ...S.th, textAlign: 'right' }}>1-5d call-buy %</th>
                <th style={{ ...S.th, textAlign: 'right' }}>1-5d put-buy %</th>
                <th style={S.th}>read</th>
              </tr>
            </thead>
            <tbody>
              {tape.map((row) => {
                const t0 = (row.tenors && row.tenors['0dte']) || {};
                const t15 = (row.tenors && row.tenors['1_5d']) || {};
                const readColor = row.read === 'bullish burst' ? GREEN
                  : row.read === 'bearish burst' ? RED : DIM;
                return (
                  <tr key={row.minute_ct}>
                    <td style={{ ...S.td, ...S.mono }}>{row.time} CT</td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>{money(row.spot)}</td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                      {t0.call_vol == null ? '—' : t0.call_vol.toLocaleString()}
                      {t0.call_vol_delta != null && (
                        <span style={{ color: DIM }}>
                          {' '}({t0.call_vol_delta >= 0 ? '+' : ''}{t0.call_vol_delta.toLocaleString()})
                        </span>
                      )}
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                      {t0.put_vol == null ? '—' : t0.put_vol.toLocaleString()}
                      {t0.put_vol_delta != null && (
                        <span style={{ color: DIM }}>
                          {' '}({t0.put_vol_delta >= 0 ? '+' : ''}{t0.put_vol_delta.toLocaleString()})
                        </span>
                      )}
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                      {t0.call_buy_share == null ? '—' : `${(t0.call_buy_share * 100).toFixed(0)}%`}
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                      {t0.put_buy_share == null ? '—' : `${(t0.put_buy_share * 100).toFixed(0)}%`}
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                      {t15.call_buy_share == null ? '—' : `${(t15.call_buy_share * 100).toFixed(0)}%`}
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                      {t15.put_buy_share == null ? '—' : `${(t15.put_buy_share * 100).toFixed(0)}%`}
                    </td>
                    <td style={{ ...S.td, fontWeight: 700, color: readColor }}>{row.read}</td>
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

// ── SECTION 2 · THE PLAYBOOK ─────────────────────────────────────────────
// Static, and must stay honest: what is tested, what is not, and what this
// signal is actually allowed to do today.
function pipelineRows(bookStart) {
  return [
    { n: 1, label: 'Found', rated: 'not rated',
      note: 'A pattern noticed in the data. Nothing has been measured against it yet.' },
    { n: 2, label: 'Proving the signal', rated: 'prediction quality, no dollars',
      note: 'Does it predict anything better than chance? hedge-dump, cascade and squeeze live here. The flow-confirm signal itself is here too — 63% continuation, tested, no money attached.' },
    { n: 3, label: 'Trade designed', rated: 'dollars/trade vs frozen bars',
      note: 'A specific ticket (strikes, size, entry/exit) is backtested against historical prices.' },
    { n: 4, label: 'Paper book', rated: 'starting + running balance',
      note: `The designed trade runs live on paper money with a real ledger. EBB and EBB-PM run here — and now the flow-confirm trade too: passed 8/31; paper book live since ${bookStart || '—'}.` },
    { n: 5, label: 'Live', rated: 'real P&L vs paper shadow',
      note: 'Real capital, checked continuously against its own paper shadow to catch drift.' },
  ];
}

function Playbook({ bookStart }) {
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

      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: GREEN }}>
          The tested recipe — passed its registered test 8/31, now earning
          paper status
        </div>
        <div style={{ ...S.caption, marginTop: 6 }}>
          When the confirm fires: buy a $2-wide same-day (0DTE) SPY debit
          vertical in the fired direction — long strike nearest{' '}
          <span style={S.mono}>round(spot at fire)</span>, short strike $2
          further out. Entered crossing the spread (~$79 average cost, risk
          capped at the debit paid). Held to the close. No exit.
        </div>
        <ul style={{ ...S.caption, marginTop: 8, paddingLeft: 18 }}>
          <li>78 historical firings, total <b style={{ color: '#e6e9f0' }}>+$2,283</b></li>
          <li>
            Median <b style={{ color: '#e6e9f0' }}>+$39</b> per firing — median
            above mean, so this isn't one lucky tail carrying the book
          </li>
          <li>58% win rate, worst single firing −$102</li>
          <li>
            Still +$1,867 after removing the 3 best firings (top-3 share 18%
            of the total)
          </li>
          <li>
            Positive every year — 2023 $583 / 2024 $628 / 2025 $267 / 2026
            $805 — and in both directions
          </li>
          <li>Roughly $570/yr per contract at ~20 fires/yr</li>
        </ul>
      </div>

      <div style={{
        marginTop: 12, padding: '10px 12px', borderRadius: 8,
        background: `${AMBER}12`, border: `1px solid ${AMBER}55`,
      }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: AMBER }}>
          Stage 4 of 5: paper only. The signal was discovered on this same
          history, so the final gate is a paper book scored on firings the
          search never saw. No real dollars until that passes and Leron
          signs off.
        </div>
      </div>

      <div style={{ ...S.small, marginTop: 8 }}>
        Proof days: full firing list at{' '}
        <span style={S.mono}>dev\meltup\confirm_trade_fires_2026_08_31.csv</span>,
        chart overlay at <span style={S.mono}>Desktop\tv_confirm_fires.pine</span>.
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
          today: stage 2, proven; stage 4, paper accrual running on the trade
          design that passed 8/31.
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
              {pipelineRows(bookStart).map((p) => (
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

// ── SECTION 2.5 · PAPER BOOK (stage 4) ───────────────────────────────────
// The forward-only ledger for the flow-confirm trade design. Nothing here
// places a trade — it reads /paper-book, which reads what the confirm-check
// job wrote when it fired. Same card/table/mono conventions as FiringHistory.
const FLOW_TENOR_COLUMNS = [
  ['0dte', '0DTE'], ['1_5d', '1-5D'], ['6_20d', '6-20D'], ['far', 'FAR'],
];

function StatTile({ label, value, tone }) {
  return (
    <div style={{
      flex: '1 1 150px', padding: '8px 10px', borderRadius: 8,
      background: '#0e1220', border: '1px solid #1c2233',
    }}>
      <div style={S.small}>{label}</div>
      <div style={{ ...S.mono, fontSize: 15, fontWeight: 700, color: tone || '#e6e9f0', marginTop: 2 }}>
        {value}
      </div>
    </div>
  );
}

function PaperBook({ data, err }) {
  if (err) {
    return (
      <div style={S.card}>
        <div style={S.h2}>Paper book — stage 4</div>
        <div style={{ marginTop: 8 }}><Chip text="unavailable — could not load /paper-book" /></div>
      </div>
    );
  }
  if (!data) {
    return <div style={S.card}><div style={S.h2}>Paper book — stage 4</div><div style={{ ...S.small, marginTop: 8 }}>Loading…</div></div>;
  }

  const rows = data.rows || [];
  const flowRows = data.flow_at_fire || [];
  const pnlTone = data.pnl_total > 0 ? GREEN : data.pnl_total < 0 ? RED : DIM;

  return (
    <div style={S.card}>
      <div style={S.h2}>Paper book — stage 4</div>
      <div style={{ ...S.small, marginBottom: 12 }}>
        Forward-only. Row 1 is the first fire after {data.book_start}. The
        8/18 and 8/20 fires are not in this book — the search saw them.
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <StatTile label="Starting balance" value={`$${money(data.start_balance)}`} />
        <StatTile label="Running balance" value={`$${money(data.running_balance)}`} tone={pnlTone} />
        <StatTile
          label="P&L ($ / %)"
          value={`${data.pnl_total >= 0 ? '+' : ''}$${money(data.pnl_total)} (${pct(data.pnl_pct)})`}
          tone={pnlTone}
        />
        <StatTile label="Fires (settled / skipped)" value={`${data.fires} (${data.settled} / ${data.skipped})`} />
        <StatTile
          label="Win rate"
          value={data.win_rate == null ? '—' : `${(data.win_rate * 100).toFixed(0)}%`}
        />
        <StatTile
          label="Median / fire"
          value={data.median_pnl == null ? '—' : `${data.median_pnl >= 0 ? '+' : ''}$${money(data.median_pnl)}`}
          tone={data.median_pnl == null ? undefined : (data.median_pnl >= 0 ? GREEN : RED)}
        />
        <StatTile
          label="Worst fire"
          value={data.worst_pnl == null ? '—' : `$${money(data.worst_pnl)}`}
          tone={data.worst_pnl == null ? undefined : RED}
        />
        <StatTile
          label="Best fire"
          value={data.best_pnl == null ? '—' : `+$${money(data.best_pnl)}`}
          tone={data.best_pnl == null ? undefined : GREEN}
        />
      </div>

      <div style={{
        padding: '10px 12px', borderRadius: 8, marginBottom: 12,
        background: `${AMBER}12`, border: `1px solid ${AMBER}55`,
      }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: AMBER }}>
          {data.gate?.text}
        </div>
      </div>

      {rows.length === 0 ? (
        <div style={{ ...S.small }}>No fires since the book opened.</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 760 }}>
            <thead>
              <tr>
                <th style={S.th}>date</th>
                <th style={S.th}>dir</th>
                <th style={S.th}>fire time</th>
                <th style={S.th}>strikes</th>
                <th style={{ ...S.th, textAlign: 'right' }}>debit</th>
                <th style={{ ...S.th, textAlign: 'right' }}>settle</th>
                <th style={{ ...S.th, textAlign: 'right' }}>P&L</th>
                <th style={{ ...S.th, textAlign: 'right' }}>balance</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const dirColor = r.fired_dir === 'UP' ? GREEN : r.fired_dir === 'DOWN' ? RED : DIM;
                return (
                  <tr key={`${r.date}-${r.fired_at || i}`}>
                    <td style={{ ...S.td, ...S.mono }}>{r.date}</td>
                    <td style={{ ...S.td, fontWeight: 700, color: dirColor }}>{r.fired_dir}</td>
                    <td style={{ ...S.td, ...S.mono, color: DIM }}>
                      {r.fired_at ? `${ctTime(r.fired_at)} CT` : '—'}
                    </td>
                    <td style={{ ...S.td, ...S.mono }}>{r.strikes || '—'}</td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                      {r.debit == null ? '—' : money(r.debit)}
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                      {r.settle_value == null ? '—' : money(r.settle_value)}
                    </td>
                    <td style={{
                      ...S.td, ...S.mono, textAlign: 'right', fontWeight: 700,
                      color: r.skipped_reason ? DIM : (r.pnl == null ? DIM : r.pnl >= 0 ? GREEN : RED),
                    }}>
                      {r.skipped_reason
                        ? r.skipped_reason
                        : (r.pnl == null ? '—' : `${r.pnl >= 0 ? '+' : ''}$${money(r.pnl)}`)}
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>${money(r.running_balance)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {flowRows.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 700 }}>Flow at the fire</div>
          <div style={{ ...S.small, marginBottom: 8 }}>
            Chain snapshots every 10 minutes by tenor; buy/sell inferred from
            the last print vs the quote. A proxy — no signed tape exists live.
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 900 }}>
              <thead>
                <tr>
                  <th style={S.th}>date</th>
                  <th style={S.th}>dir</th>
                  <th style={{ ...S.th, textAlign: 'right' }}>flow-mix z</th>
                  {FLOW_TENOR_COLUMNS.map(([, label]) => (
                    <th key={label} style={{ ...S.th, textAlign: 'right' }} colSpan={2}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {flowRows.map((r, i) => {
                  const dirColor = r.fired_dir === 'UP' ? GREEN : r.fired_dir === 'DOWN' ? RED : DIM;
                  const side = r.fired_dir === 'UP' ? 'call' : 'put';
                  return (
                    <tr key={`${r.date}-${r.fired_at || i}`}>
                      <td style={{ ...S.td, ...S.mono }}>{r.date}</td>
                      <td style={{ ...S.td, fontWeight: 700, color: dirColor }}>{r.fired_dir}</td>
                      <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                        {r.flow_mix_z == null ? '—' : `${num(r.flow_mix_z, 2)}σ`}
                      </td>
                      {FLOW_TENOR_COLUMNS.map(([key]) => {
                        const t = (r.tenors && r.tenors[key]) || {};
                        const buyShare = side === 'call' ? t.call_buy_share : t.put_buy_share;
                        const notionalD = side === 'call' ? t.call_notional_d : t.put_notional_d;
                        return (
                          <Fragment key={key}>
                            <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                              {buyShare == null ? '—' : `${(buyShare * 100).toFixed(0)}%`}
                            </td>
                            <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>
                              {notionalD == null ? '—' : `${notionalD >= 0 ? '+' : ''}$${Math.round(notionalD).toLocaleString()}`}
                            </td>
                          </Fragment>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
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
  const [paperBook, setPaperBook] = useState(null);
  const [paperBookErr, setPaperBookErr] = useState(null);

  useEffect(() => {
    let live = true;
    // Polled every 60s (not fetch-once) — the flow tape now changes through
    // the whole session, not just at load, since capture runs every 10 min
    // from 08:40 CT. Skipped while the tab is hidden to avoid burning polls
    // nobody is looking at.
    const load = () => {
      fetch(`${API_URL}/api/spreadworks/risk-advisor/session`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((d) => { if (live) { setSession(d); setSessionErr(null); } })
        .catch((e) => { if (live) setSessionErr(String(e)); });
    };
    load();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, 60000);
    return () => { live = false; clearInterval(id); };
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

  useEffect(() => {
    let live = true;
    fetch(`${API_URL}/api/spreadworks/risk-advisor/paper-book`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (live) setPaperBook(d); })
      .catch((e) => { if (live) setPaperBookErr(String(e)); });
    return () => { live = false; };
  }, []);

  return (
    <div className="flex-1 overflow-y-auto">
      <div style={S.wrap}>
        <h1 style={S.h1}>
          <Crosshair size={18} style={{ verticalAlign: -3, marginRight: 6 }} />
          Hunt
        </h1>
        <ActionBox data={session} err={sessionErr} />

        <p style={S.sub}>
          The permanent reference for the SPY flow-confirmation signal: what
          it says right now, what it has proven, every day it has fired, and
          where its alerts land. Read-only — nothing here places a trade.
        </p>

        <SignalState data={session} err={sessionErr} />
        <FlowTape data={session} err={sessionErr} />
        <Playbook bookStart={paperBook?.book_start} />
        <PaperBook data={paperBook} err={paperBookErr} />
        <FiringHistory rows={history} err={historyErr} />
        <AlertDirectory />
      </div>
    </div>
  );
}
