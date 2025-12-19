'use client'

import { useState } from 'react'
import {
  MessageSquare,
  Terminal,
  Activity,
  TrendingUp,
  Calendar,
  Bot,
  Zap,
  Target,
  AlertTriangle,
  Brain,
  Copy,
  Check,
  Search
} from 'lucide-react'

interface Command {
  command: string
  description: string
  example?: string
  category: string
}

const commands: Command[] = [
  // Information Commands
  { command: '/help', description: 'Show all available commands', category: 'Information' },
  { command: '/status', description: 'Full system status (bots, positions, P&L)', category: 'Information' },
  { command: '/briefing', description: 'Morning market briefing with all data', category: 'Information' },
  { command: '/calendar', description: 'Upcoming economic events (7 days)', category: 'Information' },

  // Market Data Commands
  { command: '/gex [SYMBOL]', description: 'GEX data for symbol (default: SPY)', example: '/gex SPX', category: 'Market Data' },
  { command: '/vix', description: 'Current VIX data and term structure', category: 'Market Data' },
  { command: '/market', description: 'SPX, SPY, VIX prices with expected moves', category: 'Market Data' },
  { command: '/regime', description: 'Current market regime classification', category: 'Market Data' },

  // Position Commands
  { command: '/positions', description: 'All open positions with Greeks', category: 'Positions' },
  { command: '/pnl', description: 'P&L summary across all strategies', category: 'Positions' },
  { command: '/history [N]', description: 'Last N trades (default: 10)', example: '/history 20', category: 'Positions' },

  // Analysis Commands
  { command: '/analyze [SYM]', description: 'Full trade opportunity analysis', example: '/analyze SPY', category: 'Analysis' },
  { command: '/risk', description: 'Current portfolio risk assessment', category: 'Analysis' },
  { command: '/weights', description: 'Probability system weights', category: 'Analysis' },
  { command: '/backtest', description: 'Recent backtest performance', category: 'Analysis' },

  // Bot Control Commands
  { command: '/start ares', description: 'Start ARES bot (requires confirmation)', category: 'Bot Control' },
  { command: '/stop ares', description: 'Stop ARES bot (requires confirmation)', category: 'Bot Control' },
  { command: '/cycle athena', description: 'Run one ATHENA trading cycle', category: 'Bot Control' },
  { command: '/calibrate', description: 'Recalibrate probability weights', category: 'Bot Control' },

  // Learning Commands
  { command: '/accuracy', description: 'AI prediction accuracy stats', category: 'Learning' },
  { command: '/patterns', description: 'Pattern recognition insights', category: 'Learning' },
  { command: '/improve', description: 'Suggested improvements from trade journal', category: 'Learning' },
]

const naturalQueries = [
  "What's the GEX looking like today?",
  "Should I trade today?",
  "Explain my last trade",
  "What economic events are coming up?",
  "How is ARES performing?",
  "What's my win rate this month?",
  "Give me a market briefing",
  "What's the call wall on SPY?",
  "Is VIX elevated?",
  "What regime are we in?",
]

const economicEvents = [
  { event: 'FOMC', description: 'Federal Reserve Interest Rate Decision', impact: 'HIGH', advice: 'AVOID Iron Condors - can move SPX 50-100 points' },
  { event: 'CPI', description: 'Consumer Price Index', impact: 'HIGH', advice: 'Wait 30-60 min after release before trading' },
  { event: 'NFP', description: 'Non-Farm Payrolls (First Friday)', impact: 'HIGH', advice: 'Skip morning 0DTE trades' },
  { event: 'PCE', description: 'Personal Consumption Expenditures', impact: 'MEDIUM', advice: 'Fed\'s preferred inflation measure - be cautious' },
  { event: 'PPI', description: 'Producer Price Index', impact: 'MEDIUM', advice: 'Leading indicator for CPI - reduce position size' },
  { event: 'OPEX', description: 'Monthly Options Expiration (3rd Friday)', impact: 'MEDIUM', advice: 'Increased gamma effects, pin risk around strikes' },
  { event: 'Quad Witching', description: 'Mar/Jun/Sep/Dec Expiration', impact: 'HIGH', advice: 'Consider closing positions Thursday' },
]

const categoryIcons: Record<string, React.ReactNode> = {
  'Information': <Terminal className="w-5 h-5" />,
  'Market Data': <TrendingUp className="w-5 h-5" />,
  'Positions': <Target className="w-5 h-5" />,
  'Analysis': <Brain className="w-5 h-5" />,
  'Bot Control': <Bot className="w-5 h-5" />,
  'Learning': <Zap className="w-5 h-5" />,
}

export default function GexisCommandsPage() {
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedCommand(text)
    setTimeout(() => setCopiedCommand(null), 2000)
  }

  const filteredCommands = commands.filter(cmd =>
    cmd.command.toLowerCase().includes(searchTerm.toLowerCase()) ||
    cmd.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
    cmd.category.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const groupedCommands = filteredCommands.reduce((acc, cmd) => {
    if (!acc[cmd.category]) acc[cmd.category] = []
    acc[cmd.category].push(cmd)
    return acc
  }, {} as Record<string, Command[]>)

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center space-x-3 mb-2">
            <MessageSquare className="w-8 h-8 text-primary" />
            <h1 className="text-3xl font-bold text-text-primary">GEXIS Commands Reference</h1>
          </div>
          <p className="text-text-secondary">
            Quick reference for all GEXIS slash commands and natural language queries.
            Use these in the floating chat or AI Copilot page.
          </p>
        </div>

        {/* Search */}
        <div className="mb-6">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-text-muted" />
            <input
              type="text"
              placeholder="Search commands..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-background-card border border-gray-700 rounded-lg pl-10 pr-4 py-3 text-text-primary placeholder-text-muted focus:border-primary focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
        </div>

        {/* Commands Grid */}
        <div className="grid gap-6 mb-8">
          {Object.entries(groupedCommands).map(([category, cmds]) => (
            <div key={category} className="bg-background-card rounded-xl border border-gray-800 p-6">
              <div className="flex items-center space-x-2 mb-4">
                <span className="text-primary">{categoryIcons[category]}</span>
                <h2 className="text-xl font-semibold text-text-primary">{category}</h2>
              </div>
              <div className="grid gap-3">
                {cmds.map((cmd) => (
                  <div
                    key={cmd.command}
                    className="flex items-start justify-between p-3 bg-background-hover rounded-lg hover:bg-gray-800/50 transition-colors group"
                  >
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <code className="text-primary font-mono font-semibold">{cmd.command}</code>
                        <button
                          onClick={() => copyToClipboard(cmd.command.split(' ')[0])}
                          className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-gray-700 rounded"
                          title="Copy command"
                        >
                          {copiedCommand === cmd.command.split(' ')[0] ? (
                            <Check className="w-4 h-4 text-success" />
                          ) : (
                            <Copy className="w-4 h-4 text-text-muted" />
                          )}
                        </button>
                      </div>
                      <p className="text-text-secondary text-sm mt-1">{cmd.description}</p>
                      {cmd.example && (
                        <p className="text-text-muted text-xs mt-1">
                          Example: <code className="text-blue-400">{cmd.example}</code>
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Natural Language Queries */}
        <div className="bg-background-card rounded-xl border border-gray-800 p-6 mb-8">
          <div className="flex items-center space-x-2 mb-4">
            <MessageSquare className="w-5 h-5 text-primary" />
            <h2 className="text-xl font-semibold text-text-primary">Natural Language Queries</h2>
          </div>
          <p className="text-text-secondary mb-4">
            GEXIS understands natural language. Try asking these questions:
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {naturalQueries.map((query) => (
              <div
                key={query}
                onClick={() => copyToClipboard(query)}
                className="flex items-center justify-between p-3 bg-background-hover rounded-lg hover:bg-gray-800/50 transition-colors cursor-pointer group"
              >
                <span className="text-text-primary text-sm">"{query}"</span>
                <button className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-gray-700 rounded">
                  {copiedCommand === query ? (
                    <Check className="w-4 h-4 text-success" />
                  ) : (
                    <Copy className="w-4 h-4 text-text-muted" />
                  )}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Economic Calendar Awareness */}
        <div className="bg-background-card rounded-xl border border-gray-800 p-6">
          <div className="flex items-center space-x-2 mb-4">
            <Calendar className="w-5 h-5 text-primary" />
            <h2 className="text-xl font-semibold text-text-primary">Economic Calendar Awareness</h2>
          </div>
          <p className="text-text-secondary mb-4">
            GEXIS knows about these market-moving events and will advise accordingly:
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left py-3 px-4 text-text-muted font-medium">Event</th>
                  <th className="text-left py-3 px-4 text-text-muted font-medium">Description</th>
                  <th className="text-center py-3 px-4 text-text-muted font-medium">Impact</th>
                  <th className="text-left py-3 px-4 text-text-muted font-medium">Trading Advice</th>
                </tr>
              </thead>
              <tbody>
                {economicEvents.map((event) => (
                  <tr key={event.event} className="border-b border-gray-800 hover:bg-background-hover">
                    <td className="py-3 px-4 font-semibold text-text-primary">{event.event}</td>
                    <td className="py-3 px-4 text-text-secondary">{event.description}</td>
                    <td className="py-3 px-4 text-center">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        event.impact === 'HIGH'
                          ? 'bg-danger/20 text-danger'
                          : 'bg-warning/20 text-warning'
                      }`}>
                        {event.impact}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-text-secondary text-xs">{event.advice}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 p-4 bg-warning/10 border border-warning/30 rounded-lg">
            <div className="flex items-start space-x-2">
              <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-warning font-medium">GEXIS Calendar Guidance</p>
                <p className="text-text-secondary text-sm mt-1">
                  Ask GEXIS "/calendar" or "What events are coming up?" to get a tailored trading
                  advisory based on the economic calendar. GEXIS will proactively warn you about
                  high-impact events that could affect your 0DTE Iron Condor strategy.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Tips */}
        <div className="mt-8 p-4 bg-primary/10 border border-primary/30 rounded-lg">
          <div className="flex items-start space-x-2">
            <Zap className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-primary font-medium">Pro Tip</p>
              <p className="text-text-secondary text-sm mt-1">
                GEXIS knows you as "Optionist Prime" and will address you personally.
                The more context you give, the better GEXIS can help. Try: "GEXIS, I'm thinking
                about opening an Iron Condor today. What does the GEX data suggest?"
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
