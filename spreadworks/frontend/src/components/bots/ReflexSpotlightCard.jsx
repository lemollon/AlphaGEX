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
// symbols, 3.5y, +95.18u total / +75.13u with the best trade removed — see
// backend/squeeze_reactive_alerts.py's module docstring) or a plainly-labeled
// "no live data" fact. None of it is fabricated.
//
// `botStats.equity_series` below is the two REAL endpoints of that backtest
// — [0, +95.18] units, start and final total return — not a fabricated
// day-by-day curve (the per-trade series behind those numbers was never
// persisted to a table; confirmed 2026-10-16, no squeeze.duckdb table named
// in that docstring exists). Passing it as `botStats` (not the `statsLine`
// text stand-in) routes this card through BotCard's DEFAULT Sparkline +
// TradesLine path — the exact same code every live bot uses — so REFLEX is
// structurally identical to the rest of the fleet, not a lookalike.
import BotCard, { GREEN } from './BotCard';

const ROW = { bot: 'reflex' };

const BOT_STATS = {
  trades: { n: 2702, win_rate: null, pnl_7d: null, pnl_30d: null },
  equity_series: [{ equity: 0 }, { equity: 95.18 }],
};

export default function ReflexSpotlightCard() {
  return (
    <BotCard
      row={ROW}
      botStats={BOT_STATS}
      linkTo="/reflex"
      statusOverride={{ label: 'Backtest', color: '#06b6d4' }}
      accountOverride={{ label: 'Free', color: GREEN }}
      headline={{
        label: 'Backtest avg/trade',
        value: '+3.52%',
        color: GREEN,
        sub: '605 symbols · 3.5y backtest',
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
