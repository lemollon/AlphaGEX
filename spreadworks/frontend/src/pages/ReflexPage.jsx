// REFLEX — marketing page for the reactive-momentum stock bot.
//
// This page is 100% static copy, unlike every other page in src/pages/,
// which all poll a live API. REFLEX was armed for live Robinhood trading
// (dev/meltup/ember/run_reflex.py, outside this repo) but has ZERO live
// trades ever — there is no live P&L API for REFLEX anywhere in this
// backend, so every number here is either a labeled BACKTEST result or
// REFLEX's own declared $600 paper balance (same convention as every other
// bot's starting_capital — see ReflexSpotlightCard.jsx), never presented
// as live performance. Do not wire this into useFleet()/useFleetStats().
//
// Visual shape matches BotDashboard.jsx (/bots/{id}, e.g. /bots/flow) on
// purpose — same nameplate (BotNameplate, imported, not copied), same KPI
// tile (KpiTile, imported), same page padding/borders — per Leron
// 2026-10-16. The real difference: REFLEX has no live positions, trade
// history, logs or config to show (zero trades, ever), so there's no
// activity-tabs section here — that's an honest "nothing to show", not a
// missing feature.
import { BOT_REGISTRY, BOT_THEME, STRATEGY_LABEL } from '../lib/botRegistry';
import { BotNameplate, KpiTile } from './BotDashboard';

const meta = BOT_REGISTRY.reflex;
const theme = BOT_THEME.reflex;

function HowItWorksItem({ children }) {
  return (
    <li className="flex items-start gap-2.5 text-[13.5px] text-text-secondary leading-relaxed">
      <span className="mt-[7px] w-1.5 h-1.5 rounded-full shrink-0" style={{ background: theme.primary }} />
      {children}
    </li>
  );
}

export default function ReflexPage() {
  return (
    <div className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary">
      <div className="px-4 md:px-8 pt-7 pb-6" style={{ borderBottom: '1px solid rgba(125,211,252,0.18)' }}>
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <BotNameplate
            bot="reflex"
            meta={meta}
            theme={theme}
            right={
              <span className="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider" style={{ background: 'rgba(74,222,128,0.16)', color: '#4ade80' }}>
                Free
              </span>
            }
            note="Many symbols at once, any mover 10%+ on the day — not a single fixed ticker like most of the fleet."
          />
        </div>
      </div>

      <div className="px-4 md:px-8 py-6 space-y-5">
        <div
          className="px-4 py-2.5 rounded-md text-[13px] leading-relaxed"
          style={{ background: 'rgba(251,191,36,0.08)', boxShadow: 'inset 0 0 0 1px rgba(251,191,36,0.25)', color: '#fde68a' }}
        >
          <strong>BACKTESTED — not live P&amp;L.</strong> REFLEX has zero live trades ever; the
          numbers below are REFLEX's own backtest (real NBBO bid/ask fills) and its declared
          $600 paper balance, never a live result.
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiTile label="Last Session" value="$0" sub="No trades yet" />
          <KpiTile label="Total P&L" value="$0" sub="No trades yet" />
          <KpiTile label="Account Equity" value="$600" sub="Declared paper balance" />
          <KpiTile label="Open Positions" value="0" accent="var(--color-text-tertiary)" sub="Awaiting setup" />
        </div>

        <p className="text-[14px] text-text-secondary leading-relaxed max-w-[820px]">
          Most momentum bots try to guess which stocks will run before they run — chasing premarket gaps,
          news, or chart patterns. REFLEX does the opposite: it waits until a stock is already moving — up
          10%+ on the day with real buying pressure accelerating — and only then gets in. No prediction, no
          guesswork, just confirmed momentum.
        </p>

        <div>
          <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary mb-3">
            How it works
          </h2>
          <ul className="flex flex-col gap-2.5 max-w-[820px]">
            <HowItWorksItem>Scans the market in real time during regular trading hours</HowItWorksItem>
            <HowItWorksItem>
              Enters only when a stock is up 10%+ from the prior close <em>and</em> money flow is
              accelerating (not just one green candle)
            </HowItWorksItem>
            <HowItWorksItem>
              Holds through the close — exits at the real market-on-close price, never an early flinch on
              noise
            </HowItWorksItem>
            <HowItWorksItem>
              Built-in safety floor: won&rsquo;t place a single trade until the account reaches $500,
              checked fresh every few minutes
            </HowItWorksItem>
          </ul>
        </div>

        <div>
          <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary mb-3">
            The backtest
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <KpiTile
              label="Trades · symbols"
              value="2,702 trades"
              sub="605 symbols · 3.5+ years (2023-01-03 to 2026-08-28)"
            />
            <KpiTile
              label="Average return per trade"
              value="+3.52%"
              sub="+95.18 total units, real NBBO bid/ask fills"
            />
            <KpiTile
              label="Robustness"
              value="+75.13 units"
              sub="still profitable with the single best trade removed"
            />
          </div>
        </div>

        <p className="text-[13px] text-text-secondary leading-relaxed max-w-[820px]">
          Position sizing is capped at 5% per trade, max 5 positions at once — no single stock can sink the
          account.
        </p>

        <p className="text-[12px] text-text-tertiary leading-relaxed max-w-[820px]">
          {STRATEGY_LABEL[meta.strategy]} &middot; Included free with your account.
        </p>
      </div>
    </div>
  );
}
