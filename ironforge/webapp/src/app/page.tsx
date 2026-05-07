'use client'

import Link from 'next/link'
import dynamic from 'next/dynamic'

const SandboxKillSwitch = dynamic(() => import('@/components/SandboxKillSwitch'), {
  ssr: false,
})

const LaunchCountdown = dynamic(() => import('@/components/LaunchCountdown'), {
  ssr: false,
  loading: () => (
    <div className="rounded-xl border border-amber-500/20 bg-forge-card/80 p-6">
      <div className="h-20 animate-pulse rounded bg-forge-border/30" />
    </div>
  ),
})

const botIcons: Record<string, React.ReactNode> = {
  FLAME: <img src="/icon-flame.svg" alt="" className="h-5 w-5 inline-block mr-1.5 align-[-3px]" />,
  SPARK: <img src="/icon-spark.svg" alt="" className="h-5 w-5 inline-block mr-1.5 align-[-3px]" />,
  INFERNO: <img src="/inferno-icon.svg" alt="" className="h-5 w-5 inline-block mr-1.5 align-[-3px]" />,
}

const botGlow: Record<string, string> = {
  FLAME: 'glow-flame',
  SPARK: 'glow-spark',
  INFERNO: 'glow-inferno',
}

/* ── Strategy Configuration (from BotConfig) ───────────────────────── */

const sharedConfig = {
  ticker: 'SPY',
  startingCapital: '$10,000',
  riskPerTrade: '15%',
  spreadWidth: '$5.00',
  sdMultiplier: '1.2x',
  profitTarget: '30%',
  stopLoss: '200%',
  maxContracts: 10,
  maxTradesPerDay: 1,
  vixSkipThreshold: 32,
  minCredit: '$0.05',
  buyingPowerUsage: '85%',
  pdtLimit: '4 / 5 rolling days',
  eodCutoff: '2:50 PM CT',
  entryWindow: '8:30 AM – 2:00 PM CT',
  scanFrequency: 'Every 1 min',
  mtmFailLimit: 10,
}

const configRows: Array<{ label: string; value: string; hint?: string }> = [
  { label: 'Ticker', value: sharedConfig.ticker },
  { label: 'Starting Capital', value: sharedConfig.startingCapital, hint: 'Paper account' },
  { label: 'Risk Per Trade', value: sharedConfig.riskPerTrade, hint: 'Of account' },
  { label: 'Spread Width', value: sharedConfig.spreadWidth, hint: 'Per leg' },
  { label: 'Strike SD', value: sharedConfig.sdMultiplier, hint: 'Expected move multiplier' },
  { label: 'Profit Target', value: '50/30/20%', hint: 'Sliding (time-based)' },
  { label: 'Stop Loss', value: sharedConfig.stopLoss, hint: 'Cost ≥ 2x entry credit' },
  { label: 'Max Contracts', value: String(sharedConfig.maxContracts), hint: 'Per trade' },
  { label: 'Max Trades/Day', value: String(sharedConfig.maxTradesPerDay) },
  { label: 'VIX Skip', value: `> ${sharedConfig.vixSkipThreshold}`, hint: 'No entry' },
  { label: 'Min Credit', value: sharedConfig.minCredit, hint: 'Per spread' },
  { label: 'Buying Power Use', value: sharedConfig.buyingPowerUsage },
  { label: 'PDT Limit', value: sharedConfig.pdtLimit, hint: 'Rolling window' },
]

const scheduleRows: Array<{ label: string; value: string }> = [
  { label: 'Entry Window', value: sharedConfig.entryWindow },
  { label: 'EOD Cutoff', value: sharedConfig.eodCutoff },
  { label: 'Scan Frequency', value: sharedConfig.scanFrequency },
  { label: 'MTM Fail Limit', value: `${sharedConfig.mtmFailLimit} consecutive` },
]

/* ── Bots ───────────────────────────────────────────────────────────── */

const bots = [
  {
    name: 'SPARK',
    href: '/spark',
    dte: '1DTE',
    desc: 'Shorter-duration Iron Condors with 1 day to expiration. Trades on Tradier sandbox and production (Iron Viper) accounts.',
    border: 'border-blue-500/30 hover:border-blue-400/60',
    heading: 'text-blue-400',
    btn: 'border-blue-500/60 text-blue-400 hover:bg-blue-500/10',
    glow: 'shadow-blue-500/5',
    badge: 'bg-blue-500/15 text-blue-400',
    mode: 'ACCOUNT TRADING' as const,
    modeCls: 'bg-green-500/15 text-green-400 border-green-500/30',
  },
  {
    name: 'FLAME',
    href: '/flame',
    dte: '2DTE',
    desc: 'Tasty-style Bull Put Credit Spreads at 1.0 SD OTM with $5 wings. VIX > 18 gate, 10% account risk per trade.',
    border: 'border-amber-500/30 hover:border-amber-400/60',
    heading: 'text-amber-400',
    btn: 'border-amber-500/60 text-amber-400 hover:bg-amber-500/10',
    glow: 'shadow-amber-500/5',
    badge: 'bg-amber-500/15 text-amber-400',
    mode: 'PAPER ONLY' as const,
    modeCls: 'bg-gray-500/15 text-gray-400 border-gray-600/30',
  },
  {
    name: 'INFERNO',
    href: '/inferno',
    dte: '0DTE',
    desc: 'FORTRESS-style 0DTE Iron Condors. Up to 3 trades per day with multiple simultaneous positions.',
    border: 'border-red-500/30 hover:border-red-400/60',
    heading: 'text-red-400',
    btn: 'border-red-500/60 text-red-400 hover:bg-red-500/10',
    glow: 'shadow-red-500/5',
    badge: 'bg-red-500/15 text-red-400',
    mode: 'PAPER ONLY' as const,
    modeCls: 'bg-gray-500/15 text-gray-400 border-gray-600/30',
  },
  {
    name: 'Compare',
    href: '/compare',
    dte: 'Head to Head',
    desc: 'Side-by-side comparison of FLAME, SPARK & INFERNO. Equity curves, win rates, P&L, and all metrics.',
    border: 'border-stone-600/30 hover:border-stone-500/60',
    heading: 'text-white',
    btn: 'border-stone-500/60 text-gray-300 hover:bg-stone-700/30',
    glow: '',
    badge: 'bg-stone-500/15 text-stone-300',
    mode: null,
    modeCls: '',
  },
]

/* ── Exit Logic ─────────────────────────────────────────────────────── */

const exitRules = [
  { trigger: 'PT (Morning)', condition: '50%  8:30–10:29 AM CT', color: 'text-emerald-400' },
  { trigger: 'PT (Midday)', condition: '30%  10:30 AM–12:59 PM CT', color: 'text-yellow-400' },
  { trigger: 'PT (Afternoon)', condition: '20%  1:00–2:50 PM CT', color: 'text-orange-400' },
  { trigger: 'PT (INFERNO)', condition: '20% → 30% → 50% (reversed slide)', color: 'text-red-400' },
  { trigger: 'Stop Loss', condition: '200%  Cost ≥ 2x entry credit', color: 'text-red-400' },
  { trigger: 'EOD Cutoff', condition: '2:50 PM CT', color: 'text-amber-400' },
  { trigger: 'Stale/Expired', condition: 'Position from prior day', color: 'text-amber-400' },
  { trigger: 'Data Failure', condition: '10 MTM failures', color: 'text-red-400' },
]

/* ── Page ────────────────────────────────────────────────────────────── */

export default function Home() {
  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="text-center mt-2">
        <h1 className="text-5xl font-extrabold tracking-tight mb-2 glow-amber">
          <img src="/ironforge-logo.svg" alt="" className="h-10 w-10 inline-block align-middle" />{' '}
          <span className="text-white">Iron</span>
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 via-orange-400 to-amber-500">
            Forge
          </span>
        </h1>
        <p className="text-forge-muted text-sm mb-3">
          SPY Iron Condor Paper Trading &middot; Render + Tradier
        </p>
        <p style={{
          color: '#FCD34D',
          fontStyle: 'italic',
          fontSize: '0.85rem',
          fontFamily: "Georgia, 'Times New Roman', serif",
          letterSpacing: '0.05em',
          textAlign: 'center',
          maxWidth: '400px',
          margin: '4px auto 0 auto',
          textShadow: '0 1px 3px rgba(0,0,0,0.8), 0 0 8px rgba(251,191,36,0.5)',
        }}>
          &ldquo;As iron sharpens iron, so one person sharpens another.&rdquo; &mdash; Proverbs 27:17
        </p>
      </div>

      {/* Launch Countdown */}
      <LaunchCountdown />

      {/* Sandbox Kill Switch — emergency controls */}
      <SandboxKillSwitch />

      {/* Bot Cards */}
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
        {bots.map((bot) => (
          <Link key={bot.name} href={bot.href}>
            <div
              className={`rounded-xl border bg-forge-card/80 p-6 h-full transition-all duration-200 hover:translate-y-[-2px] ${bot.border} ${bot.glow}`}
            >
              <div className="flex items-center justify-between mb-3">
                <h2 className={`text-2xl font-bold ${bot.heading} ${botGlow[bot.name] || ''}`}>
                  {botIcons[bot.name]}{bot.name}
                </h2>
                <div className="flex flex-col items-end gap-1">
                  <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${bot.badge}`}>
                    {bot.dte}
                  </span>
                  {bot.mode && (
                    <span className={`text-[9px] px-2 py-0.5 rounded-full font-semibold border tracking-wider ${bot.modeCls}`}>
                      {bot.mode}
                    </span>
                  )}
                </div>
              </div>
              <p className="text-sm text-gray-400 mb-5 leading-relaxed">{bot.desc}</p>
              <div className="text-center">
                <span className={`inline-block px-5 py-1.5 rounded-lg border text-sm font-medium transition-colors ${bot.btn}`}>
                  View Dashboard &rarr;
                </span>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Fire divider */}
      <div className="fire-divider" />

      {/* Strategy Configuration */}
      <section>
        <h2 className="text-xl font-bold mb-1">
          <span className="text-amber-400">Strategy</span> Configuration
        </h2>
        <p className="text-xs text-forge-muted mb-5">
          Shared base parameters for SPARK &amp; INFERNO Iron Condors. FLAME runs its own Bull Put Credit Spread strategy (1.0 SD, $1.50 min credit, 10% account risk).
        </p>

        <div className="grid md:grid-cols-2 gap-5">
          {/* Left: IC Parameters */}
          <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5">
            <h3 className="text-sm font-semibold text-amber-400/80 uppercase tracking-wider mb-4">
              Iron Condor Parameters
            </h3>
            <div className="space-y-2.5">
              {configRows.map((row) => (
                <div key={row.label} className="flex items-baseline justify-between">
                  <span className="text-sm text-gray-400">{row.label}</span>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium text-gray-100">{row.value}</span>
                    {row.hint && (
                      <span className="text-[10px] text-forge-muted">{row.hint}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right: Schedule + Exit Rules */}
          <div className="space-y-5">
            {/* Schedule */}
            <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5">
              <h3 className="text-sm font-semibold text-amber-400/80 uppercase tracking-wider mb-4">
                Trading Schedule
              </h3>
              <div className="space-y-2.5">
                {scheduleRows.map((row) => (
                  <div key={row.label} className="flex items-baseline justify-between">
                    <span className="text-sm text-gray-400">{row.label}</span>
                    <span className="text-sm font-medium text-gray-100">{row.value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Exit Rules */}
            <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5">
              <h3 className="text-sm font-semibold text-amber-400/80 uppercase tracking-wider mb-4">
                Exit Rules
              </h3>
              <div className="space-y-2">
                {exitRules.map((rule) => (
                  <div key={rule.trigger} className="flex items-center justify-between text-sm">
                    <span className={`font-medium ${rule.color}`}>{rule.trigger}</span>
                    <span className="text-gray-400 text-xs">{rule.condition}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Fire divider */}
      <div className="fire-divider" />

      {/* Signal Flow */}
      <section>
        <h2 className="text-xl font-bold mb-4">
          <span className="text-amber-400">Signal</span> Flow
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { step: '1', title: 'Market Data', desc: 'SPY spot + VIX from Tradier production API', icon: '&#9673;' },
            { step: '2', title: 'Filter Gates', desc: 'VIX < 32, not max trades, PDT compliant, within window', icon: '&#9670;' },
            { step: '3', title: 'Strike Calc', desc: 'SD-based strikes, $5 wings, real option chain credits', icon: '&#9651;' },
            { step: '4', title: 'Execute', desc: 'Size position, log to PostgreSQL, monitor MTM every 1 min', icon: '&#9632;' },
          ].map((s) => (
            <div key={s.step} className="rounded-xl border border-forge-border bg-forge-card/40 p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-amber-500 text-lg" dangerouslySetInnerHTML={{ __html: s.icon }} />
                <span className="text-xs text-forge-muted font-mono">STEP {s.step}</span>
              </div>
              <p className="text-sm font-semibold text-gray-100 mb-1">{s.title}</p>
              <p className="text-xs text-gray-500 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Fire divider */}
      <div className="fire-divider" />

      {/* Architecture — Bot to Account Flow */}
      <section>
        <h2 className="text-xl font-bold mb-1">
          <span className="text-amber-400">Architecture</span> — Bot to Account Flow
        </h2>
        <p className="text-xs text-forge-muted mb-5">
          How each bot connects to trading accounts
        </p>

        <div className="grid md:grid-cols-2 gap-5">
          {/* Left: Paper-Only Bots */}
          <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
              Paper-Only Bots
            </h3>
            <p className="text-xs text-gray-500 mb-4">
              Internal paper tracking only. No sandbox accounts, no broker orders.
            </p>
            <div className="space-y-3">
              <div className="flex items-center gap-3 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                <img src="/icon-flame.svg" alt="" className="h-5 w-5" />
                <div>
                  <span className="text-sm font-medium text-amber-400">FLAME</span>
                  <span className="text-xs text-gray-500 ml-2">2DTE &middot; Bull Put Credit Spread</span>
                </div>
                <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-gray-500/15 text-gray-400 border border-gray-600/30">PAPER ONLY</span>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg border border-red-500/20 bg-red-500/5">
                <img src="/inferno-icon.svg" alt="" className="h-5 w-5" />
                <div>
                  <span className="text-sm font-medium text-red-400">INFERNO</span>
                  <span className="text-xs text-gray-500 ml-2">0DTE &middot; Iron Condor</span>
                </div>
                <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-gray-500/15 text-gray-400 border border-gray-600/30">PAPER ONLY</span>
              </div>
            </div>
          </div>

          {/* Right: SPARK — Account Trading */}
          <div className="rounded-xl border border-blue-500/20 bg-forge-card/60 p-5">
            <h3 className="text-sm font-semibold text-blue-400/80 uppercase tracking-wider mb-4">
              SPARK — Account Trading
            </h3>
            <p className="text-xs text-gray-500 mb-4">
              Sole production bot. Places real orders on Tradier sandbox and production accounts.
            </p>

            {/* Sandbox accounts */}
            <div className="mb-3">
              <span className="text-[10px] text-gray-500 uppercase tracking-wider">Sandbox Account</span>
              <div className="mt-1 space-y-1.5">
                <div className="flex items-center justify-between px-3 py-2 rounded-lg border border-gray-700/50 bg-forge-bg/50">
                  <span className="text-xs text-gray-300 font-medium">User</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-400 border border-blue-500/30">SANDBOX</span>
                </div>
              </div>
            </div>

            {/* Production account */}
            <div>
              <span className="text-[10px] text-gray-500 uppercase tracking-wider">Production Account</span>
              <div className="mt-1">
                <div className="flex items-center justify-between px-3 py-2 rounded-lg border border-green-500/20 bg-green-500/5">
                  <span className="text-xs text-gray-300 font-medium">Iron Viper</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/15 text-green-400 border border-green-500/30">PRODUCTION</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Fire divider */}
      <div className="fire-divider" />

      {/* DTE Comparison */}
      <section>
        <h2 className="text-xl font-bold mb-4">
          <span className="text-amber-400">FLAME</span> vs <span className="text-blue-400">SPARK</span> vs <span className="text-red-400">INFERNO</span>
        </h2>
        <div className="rounded-xl border border-forge-border bg-forge-card/60 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-forge-border">
                <th className="text-left py-3 px-4 text-forge-muted font-medium">Parameter</th>
                <th className="text-center py-3 px-4 text-amber-400 font-semibold">FLAME</th>
                <th className="text-center py-3 px-4 text-blue-400 font-semibold">SPARK</th>
                <th className="text-center py-3 px-4 text-red-400 font-semibold">INFERNO</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-forge-border/50">
              {[
                { param: 'Strategy', flame: 'Bull Put Spread', spark: 'Iron Condor', inferno: 'Iron Condor', diff: true },
                { param: 'Mode', flame: 'Paper Only', spark: 'Sandbox + Production', inferno: 'Paper Only', diff: true },
                { param: 'Days to Expiration', flame: '2 DTE', spark: '1 DTE', inferno: '0 DTE', diff: true },
                { param: 'Legs', flame: '2 (puts only)', spark: '4', inferno: '4', diff: true },
                { param: 'Spread Width', flame: '$5.00', spark: '$5.00', inferno: '$5.00', diff: false },
                { param: 'SD Multiplier', flame: '1.0x', spark: '1.2x', inferno: '1.0x', diff: true },
                { param: 'Min Credit', flame: '$1.50', spark: '$0.05', inferno: '$0.15', diff: true },
                { param: 'VIX Gate', flame: '> 18', spark: '< 32', inferno: '< 32', diff: true },
                { param: 'Profit Target', flame: '50/30/20%', spark: '50/30/20%', inferno: '20/30/50%', diff: true },
                { param: 'Stop Loss', flame: '200%', spark: '200%', inferno: '200%', diff: false },
                { param: 'Position Sizing', flame: '10% account risk', spark: 'Kelly (BP-aware)', inferno: 'Half-Kelly', diff: true },
                { param: 'Max Trades/Day', flame: '1', spark: '1', inferno: 'Unlimited', diff: true },
                { param: 'Max Positions', flame: '1', spark: '1', inferno: '3', diff: true },
                { param: 'PDT Enforcement', flame: 'N/A (paper)', spark: 'Exempt (>$25K)', inferno: 'No', diff: true },
                { param: 'Entry Window', flame: '8:30–2:00', spark: '8:30–2:00', inferno: '8:30–2:30', diff: true },
                { param: 'Theta Decay', flame: 'Slower', spark: 'Faster', inferno: 'Fastest', diff: true },
                { param: 'Premium', flame: 'Higher', spark: 'Lower', inferno: 'Lowest', diff: true },
                { param: 'Resolution', flame: '~2 days', spark: '~1 day', inferno: 'Same day', diff: true },
              ].map((row) => (
                <tr key={row.param}>
                  <td className="py-2.5 px-4 text-gray-400">{row.param}</td>
                  <td className={`py-2.5 px-4 text-center font-medium ${row.diff ? 'text-amber-400' : 'text-gray-300'}`}>
                    {row.flame}
                  </td>
                  <td className={`py-2.5 px-4 text-center font-medium ${row.diff ? 'text-blue-400' : 'text-gray-300'}`}>
                    {row.spark}
                  </td>
                  <td className={`py-2.5 px-4 text-center font-medium ${row.diff ? 'text-red-400' : 'text-gray-300'}`}>
                    {row.inferno}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Fire divider */}
      <div className="fire-divider" />

      {/* System Footer */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm pb-4">
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Platform</p>
          <p className="font-medium">Render</p>
        </div>
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Data Source</p>
          <p className="font-medium">Tradier <span className="text-emerald-400 text-xs">(Production)</span></p>
        </div>
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Storage</p>
          <p className="font-medium">PostgreSQL</p>
        </div>
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Ticker</p>
          <p className="font-medium">SPY</p>
        </div>
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Mode</p>
          <span className="inline-block px-2 py-0.5 rounded text-xs bg-amber-500/15 text-amber-400 font-medium">
            PAPER
          </span>
        </div>
      </div>
    </div>
  )
}
