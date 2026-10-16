// REFLEX promotional card — renders through the literal shared BotCard
// component (see BotCard.jsx), not a second hand-built copy of its JSX. The
// override props below are the ONLY thing that makes this card look
// different from any other bot's: everything else — layout, spacing,
// typography, hover lift — is BotCard's, so this card can never drift from
// the rest of the fleet again.
//
// REFLEX is a standalone Robinhood stock bot (dev/meltup/ember/run_reflex.py,
// outside this repo) with zero trades so far. Per Leron 2026-10-16, it's
// tracked here the same way every other bot on this page is: a declared
// $600 PAPER starting balance (same role as monarch_a's $10,000 or cinder's
// $500 in registry.py — a configured paper bankroll, not evidence of a
// funded brokerage account) — not REFLEX's real, separate, near-empty
// Robinhood account, which this card never shows or touches.
//
// Headline/footer below reproduce BotCard's own "zero-trade bot, market
// closed" shape (see Cinder/Monarch-a on the same page) with REFLEX's own
// numbers, instead of computing it live — REFLEX has no live scan/account
// feed wired into this backend, so there's nothing for BotCard's default
// isOpen/today_pnl logic to read. The backtest credential (2,702 trades,
// 605 symbols, 3.5y, +95.18u real-NBBO-fill total — see
// backend/squeeze_reactive_alerts.py's module docstring) sits in the
// headline sub-line and the Total column's tooltip, since the Total/Equity
// numbers themselves now show REFLEX's $600 paper allocation, matching what
// "Total"/"Equity" mean on every other card.
import BotCard, { GREEN, MUTED } from './BotCard';

const ROW = { bot: 'reflex' };

// Real: reflex_state.json has zero positions ever (see file header) — this
// is what lets BotCard's TradesLine render the exact "no closed trades yet"
// line every other zero-trade card on the page shows, instead of silently
// skipping that slot (which would leave a gap "no closed trades yet" cards
// don't have).
const BOT_STATS = { trades: { n: 0 } };

export default function ReflexSpotlightCard() {
  return (
    <BotCard
      row={ROW}
      botStats={BOT_STATS}
      linkTo="/reflex"
      statusOverride={{ label: 'Backtest', color: '#06b6d4' }}
      accountOverride={{ label: 'Free', color: GREEN }}
      headline={{
        label: 'Last session (2026-10-15)',
        value: '$0',
        color: MUTED,
        sub: '2,702 trades · 605 symbols · 3.5y backtest',
      }}
      footer={[
        {
          label: 'Total',
          value: '$0',
          color: MUTED,
          title: 'No paper trades logged yet. Backtested total return: '
            + '+95.18u over 2,702 trades, real NBBO bid/ask fills (still '
            + '+75.13u with the single best trade removed) — not live P&L.',
        },
        {
          label: 'Equity',
          value: '$600',
          color: '#e2e8f0',
          title: '$600 declared paper starting balance (set 2026-10-16) — '
            + 'same convention as every other bot\'s starting_capital.',
        },
        { label: 'Open', value: 0, color: '#64748b' },
      ]}
      atRiskText="At risk —"
      scanText="backtest only — no live scan feed"
    />
  );
}
