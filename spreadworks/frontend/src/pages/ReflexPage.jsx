// REFLEX — marketing page for the reactive-momentum stock bot.
//
// This page is 100% static copy, unlike every other page in src/pages/,
// which all poll a live API. REFLEX was armed today for live Robinhood
// trading (dev/meltup/ember/run_reflex.py, outside this repo) but has ZERO
// live trades yet — it is waiting on the account to clear a $500 capital
// floor. There is no live P&L API for REFLEX anywhere in this backend, so
// every number on this page is a labeled BACKTEST result, never presented
// as live performance. Do not wire this into useFleet()/useFleetStats().
import { ActivitySquare } from 'lucide-react';
import { BOT_THEME, STRATEGY_LABEL } from '../lib/botRegistry';

const theme = BOT_THEME.reflex;

function FreeBadge() {
  return (
    <span
      className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
      style={{ background: 'rgba(74,222,128,0.16)', color: '#4ade80' }}
    >
      Free
    </span>
  );
}

function HowItWorksItem({ children }) {
  return (
    <li className="flex items-start gap-2.5 text-[13.5px] text-text-secondary leading-relaxed">
      <span
        className="mt-[7px] w-1.5 h-1.5 rounded-full shrink-0"
        style={{ background: theme.primary }}
      />
      {children}
    </li>
  );
}

function StatTile({ label, value, sub, highlight }) {
  return (
    <div
      className="px-4 py-3 rounded-md sw-glass"
      style={highlight ? { boxShadow: `inset 0 0 0 1px ${theme.primaryRing}` } : undefined}
    >
      <div className="text-[10px] uppercase tracking-[0.14em] text-text-tertiary mb-1.5">{label}</div>
      <div className="text-[19px] font-bold sw-mono" style={{ color: theme.primary }}>{value}</div>
      {sub && <div className="text-[11px] text-text-secondary sw-mono mt-1">{sub}</div>}
    </div>
  );
}

export default function ReflexPage() {
  return (
    <div className="flex-1 overflow-y-auto font-[var(--font-ui)] text-text-primary">
      {/* ── header band ── */}
      <div className="px-4 md:px-8 pt-6 pb-5" style={{ borderBottom: `1px solid ${theme.primaryRing}` }}>
        <div className="max-w-[1400px] mx-auto flex items-center gap-4">
          <div
            className="w-11 h-11 rounded-xl grid place-items-center flex-shrink-0"
            style={{
              background: theme.accentBg,
              boxShadow: `inset 0 0 0 1px ${theme.primaryRing}, 0 0 32px -8px ${theme.glow}`,
              color: theme.primary,
            }}
          >
            <ActivitySquare size={22} strokeWidth={1.8} />
          </div>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1
                className="font-black tracking-[0.04em] leading-none text-[22px] md:text-[28px]"
                style={{ color: theme.primary }}
              >
                REFLEX
              </h1>
              <FreeBadge />
            </div>
            <p className="text-[12px] text-text-tertiary mt-1.5">
              We don&rsquo;t predict the move. We confirm it, then ride it.
            </p>
          </div>
        </div>
      </div>

      {/* ── body ── */}
      <div className="px-4 md:px-8 py-6">
        <div className="max-w-[1400px] mx-auto">
          <p className="text-[14px] text-text-secondary leading-relaxed max-w-[820px] mb-7">
            Most momentum bots try to guess which stocks will run before they run — chasing premarket gaps,
            news, or chart patterns. REFLEX does the opposite: it waits until a stock is already moving — up
            10%+ on the day with real buying pressure accelerating — and only then gets in. No prediction, no
            guesswork, just confirmed momentum.
          </p>

          {/* ── how it works ── */}
          <div className="mb-7">
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

          {/* ── track record ── */}
          <div className="mb-7">
            <h2 className="text-[13px] font-bold uppercase tracking-[0.12em] text-text-secondary mb-3">
              The track record
            </h2>

            <div
              className="mb-3 px-4 py-2.5 rounded-md text-[13px] leading-relaxed max-w-[820px]"
              style={{
                background: 'rgba(251,191,36,0.08)',
                boxShadow: 'inset 0 0 0 1px rgba(251,191,36,0.25)',
                color: '#fde68a',
              }}
            >
              <strong>BACKTESTED — not live P&amp;L.</strong> REFLEX was armed today for live Robinhood
              trading and has zero live trades yet; it is waiting on the account to reach a $500 capital
              floor. Every number below is backtested on real historical bid/ask prices, not theoretical
              fills, and never presented as a live result.
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <StatTile
                label="Trades &middot; symbols"
                value="2,702 trades"
                sub="605 symbols · 3.5+ years (2023-01-03 to 2026-08-28)"
                highlight
              />
              <StatTile
                label="Average return per trade"
                value="+3.52%"
                sub="+95.18 total units, real NBBO bid/ask fills"
              />
              <StatTile
                label="Robustness"
                value="+75.13 units"
                sub="still profitable with the single best trade removed"
              />
            </div>
          </div>

          <p className="text-[13px] text-text-secondary leading-relaxed max-w-[820px] mb-7">
            Position sizing is capped at 5% per trade, max 5 positions at once — no single stock can sink the
            account.
          </p>

          <p className="text-[12px] text-text-tertiary leading-relaxed max-w-[820px]">
            {STRATEGY_LABEL.reactive_momentum} &middot; Included free with your account.
          </p>
        </div>
      </div>
    </div>
  );
}
