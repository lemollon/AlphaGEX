// REFLEX promotional card — renders through the literal shared BotCard
// component (see BotCard.jsx), not a second hand-built copy of its JSX. The
// override props below are the ONLY thing that makes this card look
// different from any other bot's: everything else — layout, spacing,
// typography, hover lift — is BotCard's, so this card can never drift from
// the rest of the fleet again.
//
// REFLEX is a standalone Robinhood stock bot (dev/meltup/ember/run_reflex.py,
// outside this repo). It was armed today for live trading but has ZERO live
// trades — it's waiting on the account to clear a $500 capital floor — and
// there is no live P&L API for it anywhere in this backend. Every value
// mapped in here is either a real backtest number (2,702 trades, 605
// symbols, 3.5y, +95.18u total / +75.13u with the best trade removed) or a
// plainly-labeled "no live data" fact. None of it is fabricated, and nothing
// here is presented as live P&L.
import BotCard, { GREEN } from './BotCard';

const ROW = { bot: 'reflex' };

export default function ReflexSpotlightCard() {
  return (
    <BotCard
      row={ROW}
      botStats={null}
      linkTo="/reflex"
      statusOverride={{ label: 'Backtest', color: '#06b6d4' }}
      accountOverride={{ label: 'Free', color: GREEN }}
      headline={{
        label: 'Backtest avg/trade',
        value: '+3.52%',
        color: GREEN,
        sub: '2,702 trades · 605 symbols · 3.5y backtest',
      }}
      footer={[
        {
          label: 'Total',
          value: '+95.18u',
          color: GREEN,
          title: 'Backtested total return, real NBBO bid/ask fills — not live P&L. '
            + 'Still +75.13u with the single best trade removed.',
        },
        {
          label: 'Equity',
          value: 'N/A',
          color: '#64748b',
          title: 'No live equity account — REFLEX trades via a separate Robinhood '
            + 'script outside this platform.',
        },
        { label: 'Open', value: 0, color: '#64748b' },
      ]}
      atRiskText="At risk $0 — no live positions"
      scanText="backtest only — no live scan feed"
    />
  );
}
