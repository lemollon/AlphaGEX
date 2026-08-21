// The Money — am I up or down, and what is actually carrying it.
//
// 🚨 NO SURFACE ANSWERED THIS. There were per-bot views and a fleet page, and
// nothing summed them. On 2026-08-20 the honest month-to-date answer was
// −$2,940 across 19 bots with 17 of them losing, and finding that out required
// writing SQL by hand. A book you cannot see the total of is a book you are
// managing blind.
//
// ⛔ IT LEADS WITH THE VERDICT. "Here is a table of bots" is the same defect
// this app has been fixing all week one card at a time: information where a
// decision belongs. The first thing on the page is whether you are up or down
// and what would change that answer.
//
// 🚨 AND CONCENTRATION IS THE HEADLINE, NOT A FOOTNOTE. A book earning its
// result across many trades and a book resting on one fill are different
// objects with the same total. This one is the second kind: a single +$5,319
// trade on 2026-08-18 against a −$2,940 month, i.e. the trade is larger than
// the result. This repo has already produced two phantom-profit bugs — the
// force-close $0 mark and the credit-settlement clamp — so an outsized single
// fill is a prompt to reconcile against the broker, not a reason to relax.
import { useEffect, useState } from 'react';
import { Wallet, AlertTriangle } from 'lucide-react';
import { API_URL } from '../lib/api';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', DIM = '#8b93a7';

const S = {
  wrap: { maxWidth: 1100, margin: '0 auto', padding: '24px 16px 96px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: DIM, fontSize: 13, margin: '0 0 20px' },
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

// Dollars first, percent second — a percentage of an unstated base is not an
// amount of money.
const usd = (x) => (x == null ? '—'
  : `${x < 0 ? '−' : ''}$${Math.abs(x).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
const usd2 = (x) => (x == null ? '—'
  : `${x < 0 ? '−' : ''}$${Math.abs(x).toFixed(2)}`);

const WINDOWS = [['day', 'Today'], ['week', 'This week'],
                 ['month', 'This month'], ['all', 'All time']];

export default function MoneyPage() {
  const [win, setWin] = useState('month');
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    setD(null); setErr(null);
    fetch(`${API_URL}/api/spreadworks/book-risk/money?window=${win}`)
      .then((r) => r.json())
      .then((x) => { if (live) setD(x); })
      .catch((e) => { if (live) setErr(String(e)); });
    return () => { live = false; };
  }, [win]);

  const picker = (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {WINDOWS.map(([k, label]) => (
        <button key={k} onClick={() => setWin(k)} style={{
          padding: '5px 11px', borderRadius: 999, fontSize: 12, cursor: 'pointer',
          background: win === k ? '#1e2740' : 'transparent',
          border: `1px solid ${win === k ? '#3b4a6b' : '#232a3d'}`,
          color: win === k ? '#e6e9f0' : DIM,
        }}>{label}</button>
      ))}
    </div>
  );

  const body = () => {
    if (err) return <div style={S.card}>Couldn’t load the book: {err}</div>;
    if (!d) return <div style={S.card}>Loading…</div>;
    if (d.status === 'unavailable') return <div style={S.card}>No database.</div>;
    if (!d.bots || !d.bots.length) {
      return <div style={S.card}>No closed trades in this window.</div>;
    }

    const up = d.book_total > 0;
    const tone = up ? GREEN : RED;
    // ⛔ The verdict is not "you are up". It is up-or-down AND whether that
    // survives removing the one thing carrying it.
    const carried = d.sign_flips_without_biggest
      || (up && d.without_top_bot != null && d.without_top_bot < 0);

    return (
      <>
        <div style={{
          ...S.card, borderColor: `${tone}55`, background: `${tone}0d`,
        }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
            <Wallet size={16} color={tone} />
            <span style={{ ...S.mono, fontSize: 30, fontWeight: 700, color: tone }}>
              {usd(d.book_total)}
            </span>
            <span style={{ fontSize: 13, color: DIM }}>
              across {d.bots_total} bots · {d.book_trades} closed trades
              {d.start ? ` · since ${d.start}` : ''}
            </span>
          </div>
          <div style={{ fontSize: 13.5, fontWeight: 700, color: tone, marginTop: 8 }}>
            {up ? 'THE BOOK IS UP' : 'THE BOOK IS DOWN'}
            {d.bots_losing > d.bots_total / 2
              && ` — AND ${d.bots_losing} OF ${d.bots_total} BOTS ARE LOSING`}
          </div>
          {carried && (
            <div style={{ ...S.caption, marginTop: 4, color: '#e6e9f0' }}>
              {d.sign_flips_without_biggest
                ? <>One trade decides the sign. Remove it and the book is{' '}
                    <b style={{ color: RED }}>{usd(d.without_biggest_trade)}</b>.</>
                : <>It is carried by <b>{d.top_bot}</b>. Without it the book is{' '}
                    <b style={{ color: RED }}>{usd(d.without_top_bot)}</b>.</>}
            </div>
          )}
        </div>

        {/* ── WHAT WOULD CHANGE THE ANSWER ─────────────────────────────── */}
        <div style={S.card}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>
            What is holding this number up
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {[
              ['without the top bot', d.without_top_bot,
               d.top_bot ? `remove ${d.top_bot} entirely` : null],
              ['without the single biggest trade', d.without_biggest_trade,
               d.biggest_trade
                 ? `${d.biggest_trade.bot} ${usd2(d.biggest_trade.pnl)} on ${d.biggest_trade.date}`
                 : null],
            ].map(([label, val, note]) => (
              <div key={label} style={{
                flex: '1 1 240px', padding: '10px 12px', borderRadius: 8,
                background: '#0e1220',
                border: `1px solid ${(val ?? 0) < 0 ? `${RED}44` : '#1c2233'}`,
              }}>
                <div style={S.small}>{label}</div>
                <div style={{
                  ...S.mono, fontSize: 19, fontWeight: 700,
                  color: (val ?? 0) < 0 ? RED : GREEN,
                }}>{usd(val)}</div>
                {note && <div style={{ ...S.small, marginTop: 2 }}>{note}</div>}
              </div>
            ))}
          </div>

          {d.concentrated && d.biggest_trade && (
            <div style={{
              marginTop: 10, padding: '10px 12px', borderRadius: 8,
              background: `${AMBER}12`, border: `1px solid ${AMBER}55`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertTriangle size={14} color={AMBER} />
                <span style={{ fontSize: 13, fontWeight: 700, color: AMBER }}>
                  RECONCILE THIS TRADE AGAINST THE BROKER
                </span>
              </div>
              <div style={{ ...S.caption, marginTop: 4 }}>
                <b style={{ color: '#e6e9f0' }}>{d.biggest_trade.bot} {usd2(d.biggest_trade.pnl)}</b>{' '}
                on {d.biggest_trade.date} is{' '}
                <b style={{ color: '#e6e9f0' }}>{d.concentration_ratio}×</b> the size of the
                whole book’s result. This app has already produced two
                phantom-profit bugs — a force-close at a $0 mark and a credit
                settlement clamped to max profit — so a single fill this large is
                a prompt to check it against a real broker confirmation. The
                database cannot tell you whether a fill happened.
              </div>
            </div>
          )}
        </div>

        {/* ── PER BOT ───────────────────────────────────────────────────── */}
        <div style={S.card}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
            Every bot that traded in this window
          </div>
          <div style={{ ...S.small, marginBottom: 8 }}>
            Sorted by dollars. A high win rate next to a negative total means it
            wins small and loses big.
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 620 }}>
              <thead>
                <tr>
                  <th style={S.th}>bot</th>
                  <th style={{ ...S.th, textAlign: 'right' }}>total</th>
                  <th style={{ ...S.th, textAlign: 'right' }}>per trade</th>
                  <th style={{ ...S.th, textAlign: 'right' }}>trades</th>
                  <th style={{ ...S.th, textAlign: 'right' }}>win %</th>
                  <th style={{ ...S.th, textAlign: 'right' }}>worst</th>
                  <th style={{ ...S.th, textAlign: 'right' }}>% of capital</th>
                </tr>
              </thead>
              <tbody>
                {d.bots.map((b) => (
                  <tr key={b.bot}>
                    <td style={{ ...S.td, fontWeight: 600 }}>{b.bot}</td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right', fontWeight: 700,
                                 color: b.total < 0 ? RED : GREEN }}>{usd2(b.total)}</td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right',
                                 color: b.per_trade < 0 ? RED : GREEN }}>{usd2(b.per_trade)}</td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right' }}>{b.n}</td>
                    {/* ⛔ Win rate is NOT coloured. A 100% win rate on a losing
                        bot is the trap this whole book keeps re-learning; making
                        it green would advertise the trap. */}
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right', color: DIM }}>
                      {b.win_pct}%
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right', color: RED }}>
                      {usd2(b.worst)}
                    </td>
                    <td style={{ ...S.td, ...S.mono, textAlign: 'right', color: DIM }}>
                      {b.pct_of_capital == null ? '—' : `${b.pct_of_capital}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ ...S.caption }}>
          Realized P&amp;L only — closed trades, grouped on the CT session date.
          Open positions are not counted, so this is money booked rather than
          money marked. Paper and live bots are summed together; the page tells
          you what the ledger says, and the ledger does not know which account a
          fill went to.
        </div>
      </>
    );
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div style={S.wrap}>
        <h1 style={S.h1}>The Money</h1>
        <p style={S.sub}>
          Whether the book is up or down, and what is actually holding that number up.
        </p>
        <div style={{ marginBottom: 14 }}>{picker}</div>
        {body()}
      </div>
    </div>
  );
}
