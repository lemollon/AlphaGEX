// REFLEX promotional card — renders through the literal shared BotCard
// component (see BotCard.jsx), not a second hand-built copy of its JSX. The
// override props below are the ONLY thing that makes this card look
// different from any other bot's: everything else — layout, spacing,
// typography, hover lift — is BotCard's, so this card can never drift from
// the rest of the fleet again.
//
// REFLEX is a standalone Robinhood stock bot (dev/meltup/ember/run_reflex.py,
// outside this repo). It was armed for live trading but has ZERO live trades
// — real account state, confirmed 2026-10-16 from its own
// reflex_state.json (positions: []) and reflex-capital-check-output.log
// (TOTAL_VALUE=1.26, last checked 2026-10-15 15:00 CT) — the account sits at
// $1.26, below the $500 REFLEX_MIN_ACCOUNT_VALUE floor, so it has never
// placed a real order. That means Total P&L / Last session are REAL
// numbers, not placeholders: $0 realized (nothing has ever traded), $1
// equity (the real, if tiny, account balance).
//
// Headline/footer below reproduce BotCard's own "zero-trade bot, market
// closed" shape (see Cinder/Monarch-a on the same page) with those real
// numbers, instead of computing it live — REFLEX has no live scan/account
// feed wired into this backend, so there's nothing for BotCard's default
// isOpen/today_pnl logic to read. The backtest credential (2,702 trades,
// 605 symbols, 3.5y, +95.18u real-NBBO-fill total — see
// backend/squeeze_reactive_alerts.py's module docstring) moves to the
// headline sub-line and the Total column's tooltip, since the Total/Equity
// numbers themselves now show REFLEX's real (if dormant) live account, not
// the backtest, matching what "Total"/"Equity" mean on every other card.
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
          title: 'No live trades yet — $1 Robinhood account balance, armed and '
            + 'waiting on the $500 capital floor. Backtested total return: '
            + '+95.18u over 2,702 trades, real NBBO bid/ask fills (still '
            + '+75.13u with the single best trade removed) — not live P&L.',
        },
        {
          label: 'Equity',
          value: '$1',
          color: '#e2e8f0',
          title: 'Real Robinhood account balance, last checked 2026-10-15.',
        },
        { label: 'Open', value: 0, color: '#64748b' },
      ]}
      atRiskText="At risk —"
      scanText="backtest only — no live scan feed"
    />
  );
}
