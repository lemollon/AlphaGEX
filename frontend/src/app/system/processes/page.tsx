'use client';

import { useState, useEffect, useCallback } from 'react';
import Navigation from '@/components/Navigation';

// Types for our process data
interface ProcessNode {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'inactive' | 'error' | 'unknown';
  lastRun?: string;
  codeFile?: string;
  category: string;
}

interface BotStatus {
  name: string;
  status: 'running' | 'stopped' | 'error';
  lastHeartbeat?: string;
  tradesExecuted?: number;
}

// Tab definitions
const TABS = [
  { id: 'overview', label: 'Overview', icon: '🏠' },
  { id: 'data', label: 'Data Layer', icon: '📊' },
  { id: 'decisions', label: 'Decision Engines', icon: '🧠' },
  { id: 'execution', label: 'Execution', icon: '⚡' },
  { id: 'bots', label: 'Autonomous Bots', icon: '🤖' },
  { id: 'ai', label: 'AI/ML Systems', icon: '🔮' },
  { id: 'analysis', label: 'Analysis', icon: '📈' },
  { id: 'strategy', label: 'Strategies', icon: '♟️' },
  { id: 'operations', label: 'Operations', icon: '⚙️' },
  { id: 'timeline', label: 'Timeline', icon: '⏰' },
];

// Color coding for different node types
const NODE_COLORS = {
  data: { bg: 'bg-blue-900/30', border: 'border-blue-500', text: 'text-blue-400' },
  decision: { bg: 'bg-green-900/30', border: 'border-green-500', text: 'text-green-400' },
  process: { bg: 'bg-yellow-900/30', border: 'border-yellow-500', text: 'text-yellow-400' },
  ai: { bg: 'bg-purple-900/30', border: 'border-purple-500', text: 'text-purple-400' },
  bot: { bg: 'bg-pink-900/30', border: 'border-pink-500', text: 'text-pink-400' },
  risk: { bg: 'bg-red-900/30', border: 'border-red-500', text: 'text-red-400' },
  output: { bg: 'bg-cyan-900/30', border: 'border-cyan-500', text: 'text-cyan-400' },
};

// Flowchart component for rendering diagrams
function FlowChart({ title, nodes, description, codeRef }: {
  title: string;
  nodes: { id: string; label: string; type: keyof typeof NODE_COLORS; children?: string[] }[];
  description?: string;
  codeRef?: string;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700 mb-4">
      <div
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-700/30"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">{expanded ? '▼' : '▶'}</span>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
        </div>
        {codeRef && (
          <span className="text-xs text-gray-500 font-mono">{codeRef}</span>
        )}
      </div>

      {expanded && (
        <div className="p-4 pt-0">
          {description && (
            <p className="text-gray-400 text-sm mb-4">{description}</p>
          )}
          <div className="flex flex-wrap gap-3 items-start justify-center">
            {nodes.map((node, idx) => (
              <div key={node.id} className="flex items-center gap-2">
                <div
                  className={`px-4 py-2 rounded-lg border-2 ${NODE_COLORS[node.type].bg} ${NODE_COLORS[node.type].border} ${NODE_COLORS[node.type].text} font-medium text-sm`}
                  title={node.label}
                >
                  {node.label}
                </div>
                {idx < nodes.length - 1 && (
                  <span className="text-gray-500 text-xl">→</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Decision Tree component
function DecisionTree({ title, tree, description, codeRef }: {
  title: string;
  tree: { condition: string; yes: string; no: string; yesType?: keyof typeof NODE_COLORS; noType?: keyof typeof NODE_COLORS }[];
  description?: string;
  codeRef?: string;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700 mb-4">
      <div
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-700/30"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">{expanded ? '▼' : '▶'}</span>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
        </div>
        {codeRef && (
          <span className="text-xs text-gray-500 font-mono">{codeRef}</span>
        )}
      </div>

      {expanded && (
        <div className="p-4 pt-0">
          {description && (
            <p className="text-gray-400 text-sm mb-4">{description}</p>
          )}
          <div className="space-y-4">
            {tree.map((node, idx) => (
              <div key={idx} className="flex items-center gap-4 flex-wrap">
                <div className="px-4 py-2 rounded-lg bg-yellow-900/30 border-2 border-yellow-500 text-yellow-400 font-medium">
                  ◇ {node.condition}
                </div>
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-green-500 text-sm">YES →</span>
                    <div className={`px-3 py-1 rounded border ${NODE_COLORS[node.yesType || 'process'].bg} ${NODE_COLORS[node.yesType || 'process'].border} ${NODE_COLORS[node.yesType || 'process'].text} text-sm`}>
                      {node.yes}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-red-500 text-sm">NO →</span>
                    <div className={`px-3 py-1 rounded border ${NODE_COLORS[node.noType || 'process'].bg} ${NODE_COLORS[node.noType || 'process'].border} ${NODE_COLORS[node.noType || 'process'].text} text-sm`}>
                      {node.no}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Bot Status Card
function BotCard({ bot }: { bot: { name: string; icon: string; description: string; status: string; features: string[]; codeRef: string } }) {
  const [expanded, setExpanded] = useState(false);

  const statusColors = {
    running: 'bg-green-500',
    stopped: 'bg-gray-500',
    error: 'bg-red-500',
  };

  return (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{bot.icon}</span>
          <div>
            <h4 className="text-white font-semibold">{bot.name}</h4>
            <p className="text-gray-400 text-xs">{bot.description}</p>
          </div>
        </div>
        <div className={`w-3 h-3 rounded-full ${statusColors[bot.status as keyof typeof statusColors] || 'bg-gray-500'} animate-pulse`} />
      </div>

      <button
        className="text-blue-400 text-sm hover:underline"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? 'Hide details' : 'Show details'}
      </button>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-700">
          <p className="text-xs text-gray-500 font-mono mb-2">{bot.codeRef}</p>
          <ul className="text-sm text-gray-300 space-y-1">
            {bot.features.map((f, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className="text-green-500">✓</span> {f}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Process Metrics component
function ProcessMetrics({ metrics }: { metrics: { label: string; value: string | number; trend?: 'up' | 'down' | 'neutral' }[] }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {metrics.map((m, i) => (
        <div key={i} className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
          <p className="text-gray-400 text-sm">{m.label}</p>
          <p className="text-2xl font-bold text-white">{m.value}</p>
          {m.trend && (
            <span className={m.trend === 'up' ? 'text-green-500' : m.trend === 'down' ? 'text-red-500' : 'text-gray-500'}>
              {m.trend === 'up' ? '↑' : m.trend === 'down' ? '↓' : '–'}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

// Legend component
function Legend() {
  return (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-6">
      <h4 className="text-white font-semibold mb-3">Color Legend</h4>
      <div className="flex flex-wrap gap-4">
        {Object.entries(NODE_COLORS).map(([type, colors]) => (
          <div key={type} className="flex items-center gap-2">
            <div className={`w-4 h-4 rounded ${colors.bg} border ${colors.border}`} />
            <span className="text-gray-300 text-sm capitalize">{type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SystemProcessesPage() {
  const [activeTab, setActiveTab] = useState('overview');
  const [searchQuery, setSearchQuery] = useState('');
  const [botStatuses, setBotStatuses] = useState<Record<string, string>>({});

  // Fetch bot statuses
  useEffect(() => {
    const fetchBotStatuses = async () => {
      try {
        const response = await fetch('/api/bots/status');
        if (response.ok) {
          const data = await response.json();
          setBotStatuses(data);
        }
      } catch (error) {
        console.error('Failed to fetch bot statuses:', error);
      }
    };

    fetchBotStatuses();
    const interval = setInterval(fetchBotStatuses, 30000);
    return () => clearInterval(interval);
  }, []);

  // Bot definitions
  const bots = [
    {
      name: 'ARES',
      icon: '⚔️',
      description: '0DTE Iron Condor Trading Bot',
      status: botStatuses['ares'] || 'stopped',
      features: [
        'Automated 0DTE Iron Condor trades on SPX',
        'VIX-based position sizing (12-35 range)',
        'Dynamic wing width adjustment',
        'Profit target: 50%, Stop loss: 100%',
        'Market regime awareness',
        'Kelly criterion position sizing',
      ],
      codeRef: 'backend/trading/ares_iron_condor.py',
    },
    {
      name: 'ATHENA',
      icon: '🦉',
      description: 'Directional Spreads Bot',
      status: botStatuses['athena'] || 'stopped',
      features: [
        'Bull/Bear put/call spreads',
        'Trend-following strategies',
        'Multi-timeframe analysis',
        'Volatility surface integration',
      ],
      codeRef: 'backend/trading/athena_directional.py',
    },
    {
      name: 'APOLLO',
      icon: '☀️',
      description: 'AI Scanner Bot',
      status: botStatuses['apollo'] || 'stopped',
      features: [
        'Claude AI integration for analysis',
        'Pattern recognition scanning',
        'Setup detection across symbols',
        'Opportunity scoring system',
      ],
      codeRef: 'backend/trading/apollo_scanner.py',
    },
    {
      name: 'ARGUS',
      icon: '👁️',
      description: '0DTE Gamma Live Monitor',
      status: botStatuses['argus'] || 'stopped',
      features: [
        'Real-time GEX monitoring',
        'Flip point detection',
        'Gamma exposure alerts',
        'Position risk tracking',
      ],
      codeRef: 'backend/trading/argus_monitor.py',
    },
    {
      name: 'ORACLE',
      icon: '🔮',
      description: 'ML Prediction Advisor',
      status: botStatuses['oracle'] || 'stopped',
      features: [
        'RandomForest predictions',
        'Pattern learning from history',
        'Probability estimations',
        'Confidence scoring',
      ],
      codeRef: 'backend/ml/oracle_predictions.py',
    },
    {
      name: 'PROMETHEUS',
      icon: '🔥',
      description: 'ML Training System',
      status: botStatuses['prometheus'] || 'stopped',
      features: [
        'Continuous model training',
        'Feature engineering',
        'Model evaluation & selection',
        'Hyperparameter optimization',
      ],
      codeRef: 'backend/ml/prometheus_training.py',
    },
    {
      name: 'PHOENIX',
      icon: '🦅',
      description: 'Recovery Bot',
      status: botStatuses['phoenix'] || 'stopped',
      features: [
        'Loss recovery strategies',
        'Position adjustment automation',
        'Risk reduction protocols',
        'Account protection rules',
      ],
      codeRef: 'backend/trading/phoenix_recovery.py',
    },
    {
      name: 'HERMES',
      icon: '📨',
      description: 'Data Flow Orchestrator',
      status: botStatuses['hermes'] || 'stopped',
      features: [
        'Data pipeline management',
        'API rate limit handling',
        'Cache invalidation',
        'Data consistency checks',
      ],
      codeRef: 'backend/data/hermes_flow.py',
    },
    {
      name: 'ATLAS',
      icon: '🗺️',
      description: 'Portfolio Manager',
      status: botStatuses['atlas'] || 'stopped',
      features: [
        'Multi-position tracking',
        'Portfolio-level Greeks',
        'Correlation analysis',
        'Rebalancing automation',
      ],
      codeRef: 'backend/trading/atlas_portfolio.py',
    },
  ];

  // Render tab content
  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">AlphaGEX System Overview</h2>
            <p className="text-gray-400 mb-6">
              Complete visualization of all processes, decision trees, and data flows in the AlphaGEX trading system.
            </p>

            <ProcessMetrics metrics={[
              { label: 'Active Processes', value: 47, trend: 'neutral' },
              { label: 'Bots Running', value: Object.values(botStatuses).filter(s => s === 'running').length, trend: 'up' },
              { label: 'Data Sources', value: 6, trend: 'neutral' },
              { label: 'Decision Paths', value: '61+', trend: 'neutral' },
            ]} />

            <Legend />

            {/* Master System Flow */}
            <FlowChart
              title="Master System Flow"
              description="High-level overview of how data flows through AlphaGEX from input to trade execution"
              nodes={[
                { id: '1', label: 'Market Data APIs', type: 'data' },
                { id: '2', label: 'Data Layer', type: 'data' },
                { id: '3', label: 'Analysis Engine', type: 'process' },
                { id: '4', label: 'AI/ML Systems', type: 'ai' },
                { id: '5', label: 'Decision Engine', type: 'decision' },
                { id: '6', label: 'Risk Validation', type: 'risk' },
                { id: '7', label: 'Trade Execution', type: 'output' },
              ]}
            />

            {/* Trading Loop */}
            <FlowChart
              title="Autonomous Trading Loop"
              description="The continuous cycle of analysis, decision-making, and execution"
              codeRef="backend/trading/trading_loop.py"
              nodes={[
                { id: '1', label: 'Market Open Check', type: 'decision' },
                { id: '2', label: 'Fetch Market Data', type: 'data' },
                { id: '3', label: 'Calculate GEX/Greeks', type: 'process' },
                { id: '4', label: 'Classify Regime', type: 'ai' },
                { id: '5', label: 'Select Strategy', type: 'decision' },
                { id: '6', label: 'Size Position', type: 'process' },
                { id: '7', label: 'Validate Risk', type: 'risk' },
                { id: '8', label: 'Execute Trade', type: 'output' },
              ]}
            />

            {/* Category Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
              {TABS.slice(1).map(tab => (
                <div
                  key={tab.id}
                  className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 cursor-pointer hover:border-blue-500 transition-colors"
                  onClick={() => setActiveTab(tab.id)}
                >
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-2xl">{tab.icon}</span>
                    <h3 className="text-white font-semibold">{tab.label}</h3>
                  </div>
                  <p className="text-gray-400 text-sm">
                    Click to explore {tab.label.toLowerCase()} processes and flows
                  </p>
                </div>
              ))}
            </div>
          </div>
        );

      case 'data':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">Data Layer</h2>
            <p className="text-gray-400 mb-6">
              All data pipelines, sources, caching strategies, and error handling flows.
            </p>

            <Legend />

            {/* Data Pipeline Flow */}
            <FlowChart
              title="Data Pipeline Flow"
              description="How market data flows from external APIs through processing to the database"
              codeRef="backend/data/unified_data_provider.py"
              nodes={[
                { id: '1', label: 'Tradier API', type: 'data' },
                { id: '2', label: 'Polygon API', type: 'data' },
                { id: '3', label: 'Trading Volatility', type: 'data' },
                { id: '4', label: 'FRED API', type: 'data' },
                { id: '5', label: 'Yahoo Finance', type: 'data' },
                { id: '6', label: 'Unified Provider', type: 'process' },
                { id: '7', label: 'Cache Layer', type: 'process' },
                { id: '8', label: 'Database', type: 'output' },
              ]}
            />

            {/* Data Priority Hierarchy */}
            <DecisionTree
              title="Data Priority & Fallback Hierarchy"
              description="When a data source fails, the system falls back to alternatives"
              codeRef="backend/data/data_priority.py"
              tree={[
                { condition: 'Tradier Available?', yes: 'Use Tradier (Primary)', no: 'Try Polygon', yesType: 'data', noType: 'decision' },
                { condition: 'Polygon Available?', yes: 'Use Polygon (Secondary)', no: 'Try Yahoo', yesType: 'data', noType: 'decision' },
                { condition: 'Yahoo Available?', yes: 'Use Yahoo (Tertiary)', no: 'Use Cached Data', yesType: 'data', noType: 'risk' },
              ]}
            />

            {/* Caching Strategies */}
            <FlowChart
              title="Caching Strategies"
              description="Multi-tier caching for performance optimization"
              codeRef="backend/data/cache_manager.py"
              nodes={[
                { id: '1', label: 'Request', type: 'data' },
                { id: '2', label: 'In-Memory Cache', type: 'process' },
                { id: '3', label: 'Database Cache', type: 'process' },
                { id: '4', label: 'API Call', type: 'data' },
                { id: '5', label: 'Update Caches', type: 'process' },
                { id: '6', label: 'Return Data', type: 'output' },
              ]}
            />

            {/* Rate Limiting */}
            <DecisionTree
              title="Rate Limiting & Throttling"
              description="Prevents API rate limit violations"
              codeRef="backend/data/rate_limiter.py"
              tree={[
                { condition: 'Under Rate Limit?', yes: 'Make API Call', no: 'Queue Request', yesType: 'output', noType: 'process' },
                { condition: 'Queue Full?', yes: 'Return Cached', no: 'Wait & Retry', yesType: 'data', noType: 'process' },
              ]}
            />

            {/* Error Handling */}
            <FlowChart
              title="Error Handling & Recovery"
              description="Graceful degradation when data sources fail"
              codeRef="backend/data/error_handler.py"
              nodes={[
                { id: '1', label: 'API Error', type: 'risk' },
                { id: '2', label: 'Retry (3x)', type: 'process' },
                { id: '3', label: 'Exponential Backoff', type: 'process' },
                { id: '4', label: 'Fallback Source', type: 'decision' },
                { id: '5', label: 'Use Stale Cache', type: 'data' },
                { id: '6', label: 'Alert & Log', type: 'output' },
              ]}
            />

            {/* Data Transparency */}
            <FlowChart
              title="Data Transparency & Audit Trail"
              description="Complete logging of all data operations for debugging and compliance"
              codeRef="backend/data/audit_logger.py"
              nodes={[
                { id: '1', label: 'Data Request', type: 'data' },
                { id: '2', label: 'Log Request', type: 'process' },
                { id: '3', label: 'Process Data', type: 'process' },
                { id: '4', label: 'Log Response', type: 'process' },
                { id: '5', label: 'Store Audit', type: 'output' },
              ]}
            />
          </div>
        );

      case 'decisions':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">Decision Engines</h2>
            <p className="text-gray-400 mb-6">
              All decision-making logic including market regime classification, strategy selection, and position sizing.
            </p>

            <Legend />

            {/* Market Regime Classification */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">Market Regime Classification (5 MM States)</h3>
              <p className="text-gray-400 text-sm mb-4">Based on GEX levels and market maker positioning</p>
              <p className="text-xs text-gray-500 font-mono mb-4">backend/analysis/regime_classifier.py</p>

              <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                <div className="bg-red-900/30 border border-red-500 rounded-lg p-3 text-center">
                  <h4 className="text-red-400 font-bold">PANICKING</h4>
                  <p className="text-gray-300 text-sm">GEX &lt; -$3B</p>
                  <p className="text-green-400 text-xs mt-2">→ Buy ATM Calls</p>
                </div>
                <div className="bg-orange-900/30 border border-orange-500 rounded-lg p-3 text-center">
                  <h4 className="text-orange-400 font-bold">TRAPPED</h4>
                  <p className="text-gray-300 text-sm">-$3B to $1B</p>
                  <p className="text-green-400 text-xs mt-2">→ Buy Calls on Dips</p>
                </div>
                <div className="bg-yellow-900/30 border border-yellow-500 rounded-lg p-3 text-center">
                  <h4 className="text-yellow-400 font-bold">HUNTING</h4>
                  <p className="text-gray-300 text-sm">Directional Bias</p>
                  <p className="text-green-400 text-xs mt-2">→ Follow Momentum</p>
                </div>
                <div className="bg-blue-900/30 border border-blue-500 rounded-lg p-3 text-center">
                  <h4 className="text-blue-400 font-bold">DEFENDING</h4>
                  <p className="text-gray-300 text-sm">GEX &gt; $1B</p>
                  <p className="text-green-400 text-xs mt-2">→ Sell Premium</p>
                </div>
                <div className="bg-gray-700/30 border border-gray-500 rounded-lg p-3 text-center">
                  <h4 className="text-gray-400 font-bold">NEUTRAL</h4>
                  <p className="text-gray-300 text-sm">No Clear Signal</p>
                  <p className="text-yellow-400 text-xs mt-2">→ Stay Flat</p>
                </div>
              </div>
            </div>

            {/* Strategy Selection Matrix */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">Strategy Selection Matrix (61+ Decision Paths)</h3>
              <p className="text-gray-400 text-sm mb-4">Multi-factor decision tree for strategy selection</p>
              <p className="text-xs text-gray-500 font-mono mb-4">backend/trading/strategy_selector.py</p>

              <div className="space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="px-3 py-1 rounded bg-blue-900/30 border border-blue-500 text-blue-400 text-sm">Regime</div>
                  <span className="text-gray-500">→</span>
                  <div className="px-3 py-1 rounded bg-purple-900/30 border border-purple-500 text-purple-400 text-sm">IV Rank</div>
                  <span className="text-gray-500">→</span>
                  <div className="px-3 py-1 rounded bg-green-900/30 border border-green-500 text-green-400 text-sm">Trend</div>
                  <span className="text-gray-500">→</span>
                  <div className="px-3 py-1 rounded bg-yellow-900/30 border border-yellow-500 text-yellow-400 text-sm">VIX Level</div>
                  <span className="text-gray-500">→</span>
                  <div className="px-3 py-1 rounded bg-cyan-900/30 border border-cyan-500 text-cyan-400 text-sm">Strategy</div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-4">
                  <div className="bg-gray-700/50 rounded p-2 text-center">
                    <p className="text-white text-sm font-medium">Iron Condor</p>
                    <p className="text-gray-400 text-xs">High IV + Neutral</p>
                  </div>
                  <div className="bg-gray-700/50 rounded p-2 text-center">
                    <p className="text-white text-sm font-medium">Bull Put Spread</p>
                    <p className="text-gray-400 text-xs">Bullish + Support</p>
                  </div>
                  <div className="bg-gray-700/50 rounded p-2 text-center">
                    <p className="text-white text-sm font-medium">Bear Call Spread</p>
                    <p className="text-gray-400 text-xs">Bearish + Resistance</p>
                  </div>
                  <div className="bg-gray-700/50 rounded p-2 text-center">
                    <p className="text-white text-sm font-medium">Long Calls</p>
                    <p className="text-gray-400 text-xs">Strong Bull + Low IV</p>
                  </div>
                  <div className="bg-gray-700/50 rounded p-2 text-center">
                    <p className="text-white text-sm font-medium">Long Puts</p>
                    <p className="text-gray-400 text-xs">Strong Bear + Low IV</p>
                  </div>
                  <div className="bg-gray-700/50 rounded p-2 text-center">
                    <p className="text-white text-sm font-medium">SPX Wheel</p>
                    <p className="text-gray-400 text-xs">Range-bound + High IV</p>
                  </div>
                  <div className="bg-gray-700/50 rounded p-2 text-center">
                    <p className="text-white text-sm font-medium">Straddle</p>
                    <p className="text-gray-400 text-xs">High Vol Expected</p>
                  </div>
                  <div className="bg-gray-700/50 rounded p-2 text-center">
                    <p className="text-white text-sm font-medium">No Trade</p>
                    <p className="text-gray-400 text-xs">Uncertain Conditions</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Position Sizing (Kelly Criterion) */}
            <FlowChart
              title="Position Sizing (Kelly Criterion)"
              description="Optimal position sizing based on edge and risk tolerance"
              codeRef="backend/trading/position_sizer.py"
              nodes={[
                { id: '1', label: 'Win Rate', type: 'data' },
                { id: '2', label: 'Avg Win/Loss', type: 'data' },
                { id: '3', label: 'Kelly Formula', type: 'process' },
                { id: '4', label: 'VIX Adjustment', type: 'decision' },
                { id: '5', label: 'Account Cap', type: 'risk' },
                { id: '6', label: 'Max Contracts', type: 'risk' },
                { id: '7', label: 'Final Size', type: 'output' },
              ]}
            />

            {/* Exit Condition Checker */}
            <DecisionTree
              title="Exit Condition Checker"
              description="When to close positions"
              codeRef="backend/trading/exit_manager.py"
              tree={[
                { condition: 'Profit > 50%?', yes: 'CLOSE (Take Profit)', no: 'Check Stop', yesType: 'output', noType: 'decision' },
                { condition: 'Loss > 30%?', yes: 'CLOSE (Stop Loss)', no: 'Check DTE', yesType: 'risk', noType: 'decision' },
                { condition: 'DTE = 1?', yes: 'CLOSE (Expiry Risk)', no: 'Check Regime', yesType: 'risk', noType: 'decision' },
                { condition: 'Regime Flipped?', yes: 'Re-evaluate Position', no: 'HOLD', yesType: 'ai', noType: 'output' },
              ]}
            />

            {/* Roll vs Close Decision */}
            <DecisionTree
              title="Roll vs Close Decision Tree"
              description="Whether to roll a position or close it outright"
              codeRef="backend/trading/roll_manager.py"
              tree={[
                { condition: 'Position Profitable?', yes: 'Consider Rolling', no: 'Evaluate Close', yesType: 'decision', noType: 'decision' },
                { condition: 'Good Premium Available?', yes: 'ROLL to Next Expiry', no: 'CLOSE Position', yesType: 'output', noType: 'output' },
                { condition: 'Regime Still Valid?', yes: 'ROLL with Adjustment', no: 'CLOSE & Reassess', yesType: 'output', noType: 'risk' },
              ]}
            />

            {/* VIX Gating Logic */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">VIX Gating Logic</h3>
              <p className="text-gray-400 text-sm mb-4">VIX-based trading restrictions and adjustments</p>
              <p className="text-xs text-gray-500 font-mono mb-4">backend/trading/vix_gate.py</p>

              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div className="bg-green-900/30 border border-green-500 rounded-lg p-3 text-center flex-1 min-w-[150px]">
                  <p className="text-green-400 font-bold">VIX 12-20</p>
                  <p className="text-gray-300 text-sm">Normal Trading</p>
                  <p className="text-gray-400 text-xs">Full size allowed</p>
                </div>
                <div className="bg-yellow-900/30 border border-yellow-500 rounded-lg p-3 text-center flex-1 min-w-[150px]">
                  <p className="text-yellow-400 font-bold">VIX 20-25</p>
                  <p className="text-gray-300 text-sm">Cautious Trading</p>
                  <p className="text-gray-400 text-xs">Reduce size 25%</p>
                </div>
                <div className="bg-orange-900/30 border border-orange-500 rounded-lg p-3 text-center flex-1 min-w-[150px]">
                  <p className="text-orange-400 font-bold">VIX 25-35</p>
                  <p className="text-gray-300 text-sm">Elevated Risk</p>
                  <p className="text-gray-400 text-xs">Reduce size 50%</p>
                </div>
                <div className="bg-red-900/30 border border-red-500 rounded-lg p-3 text-center flex-1 min-w-[150px]">
                  <p className="text-red-400 font-bold">VIX &gt; 35</p>
                  <p className="text-gray-300 text-sm">High Volatility</p>
                  <p className="text-gray-400 text-xs">No new trades</p>
                </div>
              </div>
            </div>

            {/* Strike Selection Algorithm */}
            <FlowChart
              title="Strike Selection Algorithm"
              description="How optimal strikes are selected for options trades"
              codeRef="backend/trading/strike_selector.py"
              nodes={[
                { id: '1', label: 'Current Price', type: 'data' },
                { id: '2', label: 'Delta Target', type: 'process' },
                { id: '3', label: 'Liquidity Check', type: 'decision' },
                { id: '4', label: 'Spread Width', type: 'process' },
                { id: '5', label: 'Premium Calc', type: 'process' },
                { id: '6', label: 'Risk/Reward', type: 'risk' },
                { id: '7', label: 'Final Strikes', type: 'output' },
              ]}
            />
          </div>
        );

      case 'execution':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">Execution Layer</h2>
            <p className="text-gray-400 mb-6">
              Trade entry, order management, and position tracking flows.
            </p>

            <Legend />

            {/* Trade Entry Pipeline */}
            <FlowChart
              title="Trade Entry Pipeline (10 Steps)"
              description="Complete flow from trade signal to executed order"
              codeRef="backend/trading/trade_executor.py"
              nodes={[
                { id: '1', label: '1. Signal Generated', type: 'ai' },
                { id: '2', label: '2. Validate Setup', type: 'decision' },
                { id: '3', label: '3. Check Greeks', type: 'process' },
                { id: '4', label: '4. Select Strikes', type: 'process' },
                { id: '5', label: '5. Check Liquidity', type: 'decision' },
                { id: '6', label: '6. Size Position', type: 'process' },
                { id: '7', label: '7. Psychology Check', type: 'ai' },
                { id: '8', label: '8. Risk Validation', type: 'risk' },
                { id: '9', label: '9. Submit Order', type: 'output' },
                { id: '10', label: '10. Log & Monitor', type: 'output' },
              ]}
            />

            {/* Multi-Leg Spread Execution */}
            <FlowChart
              title="Multi-Leg Spread Execution"
              description="How complex multi-leg orders are built and executed"
              codeRef="backend/trading/spread_executor.py"
              nodes={[
                { id: '1', label: 'Strategy Type', type: 'decision' },
                { id: '2', label: 'Build Leg 1', type: 'process' },
                { id: '3', label: 'Build Leg 2', type: 'process' },
                { id: '4', label: 'Build Leg 3+', type: 'process' },
                { id: '5', label: 'Calculate Net', type: 'process' },
                { id: '6', label: 'Submit Spread', type: 'output' },
              ]}
            />

            {/* Paper vs Live Mode */}
            <DecisionTree
              title="Paper vs Live Mode Switching"
              description="Controls whether trades are simulated or real"
              codeRef="backend/trading/mode_manager.py"
              tree={[
                { condition: 'Paper Mode Enabled?', yes: 'Simulate Trade', no: 'Check Account', yesType: 'process', noType: 'decision' },
                { condition: 'Account Has Funds?', yes: 'Execute Live Trade', no: 'Block & Alert', yesType: 'output', noType: 'risk' },
              ]}
            />

            {/* Order Management */}
            <FlowChart
              title="Order Management & Fills"
              description="Order lifecycle from submission to fill"
              codeRef="backend/trading/order_manager.py"
              nodes={[
                { id: '1', label: 'Create Order', type: 'process' },
                { id: '2', label: 'Submit to Broker', type: 'output' },
                { id: '3', label: 'Monitor Status', type: 'process' },
                { id: '4', label: 'Handle Partial', type: 'decision' },
                { id: '5', label: 'Confirm Fill', type: 'output' },
                { id: '6', label: 'Update Position', type: 'data' },
              ]}
            />

            {/* Position Tracking */}
            <FlowChart
              title="Position Tracking & Cost Basis"
              description="Maintaining accurate position and P&L data"
              codeRef="backend/trading/position_tracker.py"
              nodes={[
                { id: '1', label: 'Trade Executed', type: 'data' },
                { id: '2', label: 'Update Positions', type: 'process' },
                { id: '3', label: 'Calc Cost Basis', type: 'process' },
                { id: '4', label: 'Track Greeks', type: 'process' },
                { id: '5', label: 'Calc P&L', type: 'process' },
                { id: '6', label: 'Store History', type: 'output' },
              ]}
            />
          </div>
        );

      case 'bots':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">Autonomous Bots</h2>
            <p className="text-gray-400 mb-6">
              All autonomous trading and monitoring bots in the AlphaGEX system.
            </p>

            <ProcessMetrics metrics={[
              { label: 'Total Bots', value: 9, trend: 'neutral' },
              { label: 'Running', value: Object.values(botStatuses).filter(s => s === 'running').length, trend: 'up' },
              { label: 'Stopped', value: Object.values(botStatuses).filter(s => s === 'stopped').length, trend: 'neutral' },
              { label: 'Errors', value: Object.values(botStatuses).filter(s => s === 'error').length, trend: 'down' },
            ]} />

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {bots.map(bot => (
                <BotCard key={bot.name} bot={bot} />
              ))}
            </div>

            {/* Bot Orchestration Flow */}
            <div className="mt-6">
              <FlowChart
                title="Bot Orchestration Flow"
                description="How bots coordinate and communicate"
                codeRef="backend/bots/orchestrator.py"
                nodes={[
                  { id: '1', label: 'Scheduler', type: 'process' },
                  { id: '2', label: 'Health Check', type: 'decision' },
                  { id: '3', label: 'Start Bots', type: 'bot' },
                  { id: '4', label: 'Monitor Heartbeats', type: 'process' },
                  { id: '5', label: 'Handle Failures', type: 'risk' },
                  { id: '6', label: 'Log Activity', type: 'output' },
                ]}
              />
            </div>
          </div>
        );

      case 'ai':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">AI/ML Systems</h2>
            <p className="text-gray-400 mb-6">
              Artificial intelligence and machine learning systems powering AlphaGEX decisions.
            </p>

            <Legend />

            {/* Claude AI Intelligence */}
            <FlowChart
              title="Claude AI Intelligence (GEXIS)"
              description="How Claude AI analyzes market conditions and provides insights"
              codeRef="backend/ai/claude_analyzer.py"
              nodes={[
                { id: '1', label: 'Market Data', type: 'data' },
                { id: '2', label: 'Build Prompt', type: 'process' },
                { id: '3', label: 'Claude API', type: 'ai' },
                { id: '4', label: 'Parse Response', type: 'process' },
                { id: '5', label: 'Extract Signals', type: 'ai' },
                { id: '6', label: 'Confidence Score', type: 'output' },
              ]}
            />

            {/* ML Pattern Learning */}
            <FlowChart
              title="ML Pattern Learning (RandomForest)"
              description="Machine learning model for pattern recognition"
              codeRef="backend/ml/pattern_learner.py"
              nodes={[
                { id: '1', label: 'Historical Data', type: 'data' },
                { id: '2', label: 'Feature Extraction', type: 'process' },
                { id: '3', label: 'Train Model', type: 'ai' },
                { id: '4', label: 'Validate', type: 'decision' },
                { id: '5', label: 'Deploy Model', type: 'output' },
                { id: '6', label: 'Real-time Predict', type: 'ai' },
              ]}
            />

            {/* Psychology Trap Detector */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">Psychology Trap Detector (15 Trap Types)</h3>
              <p className="text-gray-400 text-sm mb-4">AI-powered detection of psychological trading traps</p>
              <p className="text-xs text-gray-500 font-mono mb-4">backend/ai/psychology_detector.py</p>

              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                {[
                  'Revenge Trading', 'FOMO', 'Overconfidence', 'Loss Aversion', 'Anchoring',
                  'Confirmation Bias', 'Gambler\'s Fallacy', 'Recency Bias', 'Herd Mentality', 'Sunk Cost',
                  'Overtrading', 'Analysis Paralysis', 'Hope Trading', 'Fear of Missing Out', 'Tilt'
                ].map(trap => (
                  <div key={trap} className="bg-red-900/20 border border-red-800 rounded p-2 text-center">
                    <p className="text-red-400 text-xs">{trap}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Trading RAG System */}
            <FlowChart
              title="Trading RAG System"
              description="Retrieval-Augmented Generation for trading knowledge"
              codeRef="backend/ai/trading_rag.py"
              nodes={[
                { id: '1', label: 'Query', type: 'data' },
                { id: '2', label: 'Embed Query', type: 'process' },
                { id: '3', label: 'Vector Search', type: 'ai' },
                { id: '4', label: 'Retrieve Context', type: 'data' },
                { id: '5', label: 'Augment Prompt', type: 'process' },
                { id: '6', label: 'Generate Response', type: 'ai' },
              ]}
            />

            {/* AI Recommendations Engine */}
            <FlowChart
              title="AI Recommendations Engine"
              description="Generates actionable trading recommendations"
              codeRef="backend/ai/recommendation_engine.py"
              nodes={[
                { id: '1', label: 'Current State', type: 'data' },
                { id: '2', label: 'ML Predictions', type: 'ai' },
                { id: '3', label: 'Claude Analysis', type: 'ai' },
                { id: '4', label: 'Combine Signals', type: 'process' },
                { id: '5', label: 'Rank Options', type: 'decision' },
                { id: '6', label: 'Top Recommendations', type: 'output' },
              ]}
            />
          </div>
        );

      case 'analysis':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">Analysis Systems</h2>
            <p className="text-gray-400 mb-6">
              Technical analysis, Greeks calculation, and market scanning systems.
            </p>

            <Legend />

            {/* Greeks Calculator */}
            <FlowChart
              title="Greeks Calculator"
              description="Real-time options Greeks calculation"
              codeRef="backend/analysis/greeks_calculator.py"
              nodes={[
                { id: '1', label: 'Option Data', type: 'data' },
                { id: '2', label: 'Spot Price', type: 'data' },
                { id: '3', label: 'Black-Scholes', type: 'process' },
                { id: '4', label: 'Delta/Gamma', type: 'output' },
                { id: '5', label: 'Theta/Vega', type: 'output' },
                { id: '6', label: 'Portfolio Greeks', type: 'output' },
              ]}
            />

            {/* Probability Analysis */}
            <FlowChart
              title="Probability Analysis (Monte Carlo)"
              description="Statistical probability calculations for trade outcomes"
              codeRef="backend/analysis/probability_engine.py"
              nodes={[
                { id: '1', label: 'Current Price', type: 'data' },
                { id: '2', label: 'Volatility', type: 'data' },
                { id: '3', label: 'Run Simulations', type: 'process' },
                { id: '4', label: '10,000 Paths', type: 'process' },
                { id: '5', label: 'Calc Probabilities', type: 'process' },
                { id: '6', label: 'POP/POL', type: 'output' },
              ]}
            />

            {/* Volatility Surface Analysis */}
            <FlowChart
              title="Volatility Surface Analysis"
              description="IV, Skew, and Term Structure analysis"
              codeRef="backend/analysis/volatility_surface.py"
              nodes={[
                { id: '1', label: 'Options Chain', type: 'data' },
                { id: '2', label: 'Extract IVs', type: 'process' },
                { id: '3', label: 'Build Surface', type: 'process' },
                { id: '4', label: 'Calc Skew', type: 'process' },
                { id: '5', label: 'Term Structure', type: 'process' },
                { id: '6', label: 'Anomaly Detection', type: 'ai' },
              ]}
            />

            {/* GEX Analyzer */}
            <FlowChart
              title="GEX Analyzer & Profiler"
              description="Gamma Exposure analysis and key level detection"
              codeRef="backend/analysis/gex_analyzer.py"
              nodes={[
                { id: '1', label: 'Open Interest', type: 'data' },
                { id: '2', label: 'Calc GEX/Strike', type: 'process' },
                { id: '3', label: 'Sum Total GEX', type: 'process' },
                { id: '4', label: 'Find Flip Point', type: 'decision' },
                { id: '5', label: 'Key Levels', type: 'output' },
                { id: '6', label: 'MM Positioning', type: 'output' },
              ]}
            />

            {/* Multi-Symbol Scanner */}
            <FlowChart
              title="Multi-Symbol Scanner"
              description="Scans multiple symbols for trading opportunities"
              codeRef="backend/analysis/multi_scanner.py"
              nodes={[
                { id: '1', label: 'Symbol List', type: 'data' },
                { id: '2', label: 'Fetch All Data', type: 'data' },
                { id: '3', label: 'Apply Filters', type: 'decision' },
                { id: '4', label: 'Score Setups', type: 'process' },
                { id: '5', label: 'Rank Results', type: 'process' },
                { id: '6', label: 'Top Opportunities', type: 'output' },
              ]}
            />

            {/* Setups Detection Engine */}
            <FlowChart
              title="Setups Detection Engine"
              description="Identifies specific trading setups and patterns"
              codeRef="backend/analysis/setup_detector.py"
              nodes={[
                { id: '1', label: 'Price Action', type: 'data' },
                { id: '2', label: 'Pattern Match', type: 'ai' },
                { id: '3', label: 'Volume Confirm', type: 'decision' },
                { id: '4', label: 'Greeks Confirm', type: 'decision' },
                { id: '5', label: 'Setup Score', type: 'process' },
                { id: '6', label: 'Alert/Trade', type: 'output' },
              ]}
            />
          </div>
        );

      case 'strategy':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">Strategy Systems</h2>
            <p className="text-gray-400 mb-6">
              Trading strategy implementations and optimization systems.
            </p>

            <Legend />

            {/* Wheel Strategy Workflow */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">Wheel Strategy Workflow (4 Phases)</h3>
              <p className="text-gray-400 text-sm mb-4">Complete wheel strategy lifecycle</p>
              <p className="text-xs text-gray-500 font-mono mb-4">backend/trading/wheel_strategy.py</p>

              <div className="flex flex-wrap items-center justify-center gap-4">
                <div className="bg-blue-900/30 border-2 border-blue-500 rounded-lg p-4 text-center min-w-[150px]">
                  <p className="text-blue-400 font-bold">Phase 1</p>
                  <p className="text-white">Sell CSP</p>
                  <p className="text-gray-400 text-xs">Cash-Secured Put</p>
                </div>
                <span className="text-gray-500 text-2xl">→</span>
                <div className="bg-yellow-900/30 border-2 border-yellow-500 rounded-lg p-4 text-center min-w-[150px]">
                  <p className="text-yellow-400 font-bold">Phase 2</p>
                  <p className="text-white">Assignment</p>
                  <p className="text-gray-400 text-xs">Take Stock Delivery</p>
                </div>
                <span className="text-gray-500 text-2xl">→</span>
                <div className="bg-green-900/30 border-2 border-green-500 rounded-lg p-4 text-center min-w-[150px]">
                  <p className="text-green-400 font-bold">Phase 3</p>
                  <p className="text-white">Sell CC</p>
                  <p className="text-gray-400 text-xs">Covered Call</p>
                </div>
                <span className="text-gray-500 text-2xl">→</span>
                <div className="bg-purple-900/30 border-2 border-purple-500 rounded-lg p-4 text-center min-w-[150px]">
                  <p className="text-purple-400 font-bold">Phase 4</p>
                  <p className="text-white">Resolution</p>
                  <p className="text-gray-400 text-xs">Called Away / Roll</p>
                </div>
              </div>
            </div>

            {/* 0DTE Specific Logic */}
            <FlowChart
              title="0DTE Specific Logic"
              description="Special handling for same-day expiration trades"
              codeRef="backend/trading/zero_dte.py"
              nodes={[
                { id: '1', label: 'Market Open', type: 'decision' },
                { id: '2', label: 'Check Gamma', type: 'process' },
                { id: '3', label: 'Wide Strikes', type: 'process' },
                { id: '4', label: 'Small Size', type: 'risk' },
                { id: '5', label: 'Tight Stops', type: 'risk' },
                { id: '6', label: 'Close by 3PM', type: 'output' },
              ]}
            />

            {/* Backtesting Engines */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">Backtesting Engines (6 Engines)</h3>
              <p className="text-gray-400 text-sm mb-4">Different backtesting approaches for various strategies</p>
              <p className="text-xs text-gray-500 font-mono mb-4">backend/backtesting/</p>

              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <div className="bg-gray-700/50 rounded p-3">
                  <p className="text-white font-medium">Simple Backtest</p>
                  <p className="text-gray-400 text-xs">Basic historical replay</p>
                </div>
                <div className="bg-gray-700/50 rounded p-3">
                  <p className="text-white font-medium">Options Backtest</p>
                  <p className="text-gray-400 text-xs">Greeks-aware simulation</p>
                </div>
                <div className="bg-gray-700/50 rounded p-3">
                  <p className="text-white font-medium">Walk-Forward</p>
                  <p className="text-gray-400 text-xs">Rolling optimization</p>
                </div>
                <div className="bg-gray-700/50 rounded p-3">
                  <p className="text-white font-medium">Monte Carlo</p>
                  <p className="text-gray-400 text-xs">Randomized paths</p>
                </div>
                <div className="bg-gray-700/50 rounded p-3">
                  <p className="text-white font-medium">Regime-Based</p>
                  <p className="text-gray-400 text-xs">Per-regime analysis</p>
                </div>
                <div className="bg-gray-700/50 rounded p-3">
                  <p className="text-white font-medium">Live Replay</p>
                  <p className="text-gray-400 text-xs">Tick-by-tick simulation</p>
                </div>
              </div>
            </div>

            {/* Walk-Forward Optimization */}
            <FlowChart
              title="Walk-Forward Optimization"
              description="Continuous strategy optimization loop"
              codeRef="backend/backtesting/walk_forward.py"
              nodes={[
                { id: '1', label: 'Historical Window', type: 'data' },
                { id: '2', label: 'Optimize Params', type: 'ai' },
                { id: '3', label: 'Validate OOS', type: 'decision' },
                { id: '4', label: 'Deploy Params', type: 'output' },
                { id: '5', label: 'Trade Live', type: 'output' },
                { id: '6', label: 'Collect Results', type: 'data' },
                { id: '7', label: 'Slide Window', type: 'process' },
              ]}
            />
          </div>
        );

      case 'operations':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">Operational Systems</h2>
            <p className="text-gray-400 mb-6">
              Alerts, notifications, scheduling, logging, and database operations.
            </p>

            <Legend />

            {/* Alert/Notification System */}
            <FlowChart
              title="Alert/Notification System"
              description="Real-time alerts for price, GEX, and trading events"
              codeRef="backend/notifications/alert_manager.py"
              nodes={[
                { id: '1', label: 'Event Trigger', type: 'data' },
                { id: '2', label: 'Check Conditions', type: 'decision' },
                { id: '3', label: 'Build Message', type: 'process' },
                { id: '4', label: 'Select Channel', type: 'decision' },
                { id: '5', label: 'Send Alert', type: 'output' },
                { id: '6', label: 'Log Alert', type: 'output' },
              ]}
            />

            {/* Push Notification Service */}
            <FlowChart
              title="Push Notification Service"
              description="Mobile and web push notifications"
              codeRef="backend/notifications/push_service.py"
              nodes={[
                { id: '1', label: 'Alert Created', type: 'data' },
                { id: '2', label: 'Get Subscriptions', type: 'data' },
                { id: '3', label: 'Format Payload', type: 'process' },
                { id: '4', label: 'Send to Service', type: 'output' },
                { id: '5', label: 'Track Delivery', type: 'process' },
              ]}
            />

            {/* Background Job Queue */}
            <FlowChart
              title="Background Job Queue"
              description="Async job processing system"
              codeRef="backend/jobs/job_queue.py"
              nodes={[
                { id: '1', label: 'Create Job', type: 'process' },
                { id: '2', label: 'Queue Job', type: 'data' },
                { id: '3', label: 'Worker Picks Up', type: 'process' },
                { id: '4', label: 'Execute Task', type: 'process' },
                { id: '5', label: 'Handle Result', type: 'decision' },
                { id: '6', label: 'Update Status', type: 'output' },
              ]}
            />

            {/* Scheduler System */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">Scheduler System</h3>
              <p className="text-gray-400 text-sm mb-4">Scheduled job execution intervals</p>
              <p className="text-xs text-gray-500 font-mono mb-4">backend/jobs/scheduler.py</p>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div className="bg-purple-900/30 border border-purple-500 rounded p-3 text-center">
                  <p className="text-purple-400 font-bold">Every 15 Min</p>
                  <p className="text-gray-300 text-xs">GEX Updates</p>
                </div>
                <div className="bg-blue-900/30 border border-blue-500 rounded p-3 text-center">
                  <p className="text-blue-400 font-bold">Hourly</p>
                  <p className="text-gray-300 text-xs">Position Check</p>
                </div>
                <div className="bg-green-900/30 border border-green-500 rounded p-3 text-center">
                  <p className="text-green-400 font-bold">Daily</p>
                  <p className="text-gray-300 text-xs">EOD Summary</p>
                </div>
                <div className="bg-yellow-900/30 border border-yellow-500 rounded p-3 text-center">
                  <p className="text-yellow-400 font-bold">Weekly</p>
                  <p className="text-gray-300 text-xs">Performance Report</p>
                </div>
                <div className="bg-orange-900/30 border border-orange-500 rounded p-3 text-center">
                  <p className="text-orange-400 font-bold">Monthly</p>
                  <p className="text-gray-300 text-xs">Model Retrain</p>
                </div>
              </div>
            </div>

            {/* Health Checks */}
            <FlowChart
              title="Health Checks & Bot Heartbeats"
              description="System health monitoring and bot status tracking"
              codeRef="backend/monitoring/health_checker.py"
              nodes={[
                { id: '1', label: 'Heartbeat Received', type: 'data' },
                { id: '2', label: 'Update Timestamp', type: 'process' },
                { id: '3', label: 'Check Stale Bots', type: 'decision' },
                { id: '4', label: 'Alert if Down', type: 'risk' },
                { id: '5', label: 'Auto-Restart', type: 'process' },
              ]}
            />

            {/* Logging System */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">Logging System (17+ Log Tables)</h3>
              <p className="text-gray-400 text-sm mb-4">Comprehensive logging for all system activities</p>
              <p className="text-xs text-gray-500 font-mono mb-4">backend/logging/</p>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {[
                  'trade_logs', 'decision_logs', 'error_logs', 'api_logs',
                  'bot_logs', 'alert_logs', 'gex_logs', 'order_logs',
                  'position_logs', 'pnl_logs', 'regime_logs', 'signal_logs',
                  'backtest_logs', 'ml_logs', 'audit_logs', 'user_logs', 'system_logs'
                ].map(log => (
                  <div key={log} className="bg-gray-700/50 rounded p-2 text-center">
                    <p className="text-cyan-400 text-xs font-mono">{log}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Database Operations */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">Database Operations (30+ Tables)</h3>
              <p className="text-gray-400 text-sm mb-4">Core database tables and relationships</p>
              <p className="text-xs text-gray-500 font-mono mb-4">backend/database/</p>

              <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                {[
                  'trades', 'positions', 'orders', 'accounts', 'users', 'settings',
                  'options_chains', 'gex_data', 'regimes', 'signals', 'alerts', 'bots',
                  'strategies', 'backtests', 'ml_models', 'predictions', 'features', 'metrics',
                  'daily_summary', 'pnl_history', 'equity_curve', 'drawdowns', 'sessions', 'api_keys',
                  'notifications', 'subscriptions', 'jobs', 'schedules', 'health', 'audit'
                ].map(table => (
                  <div key={table} className="bg-gray-700/50 rounded p-1 text-center">
                    <p className="text-gray-300 text-xs font-mono">{table}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* User-Facing Systems */}
            <h3 className="text-xl font-bold text-white mb-4 mt-8">User-Facing Systems</h3>

            <FlowChart
              title="Daily Manna System"
              description="Faith-based devotional with RSS and Claude AI"
              codeRef="backend/features/daily_manna.py"
              nodes={[
                { id: '1', label: 'Fetch RSS Feed', type: 'data' },
                { id: '2', label: 'Parse Content', type: 'process' },
                { id: '3', label: 'Claude Enhancement', type: 'ai' },
                { id: '4', label: 'Format Display', type: 'process' },
                { id: '5', label: 'Cache Result', type: 'output' },
              ]}
            />

            <FlowChart
              title="Settings & Configuration"
              description="User and system settings management"
              codeRef="backend/settings/config_manager.py"
              nodes={[
                { id: '1', label: 'Load Defaults', type: 'data' },
                { id: '2', label: 'User Overrides', type: 'data' },
                { id: '3', label: 'Merge Config', type: 'process' },
                { id: '4', label: 'Validate', type: 'decision' },
                { id: '5', label: 'Apply Settings', type: 'output' },
              ]}
            />

            <FlowChart
              title="Feature Flags & Toggles"
              description="Dynamic feature control"
              codeRef="backend/features/feature_flags.py"
              nodes={[
                { id: '1', label: 'Check Flag', type: 'decision' },
                { id: '2', label: 'Enabled?', type: 'decision' },
                { id: '3', label: 'Run Feature', type: 'output' },
                { id: '4', label: 'Skip Feature', type: 'process' },
              ]}
            />

            <FlowChart
              title="Account Management"
              description="Balance, positions, and equity tracking"
              codeRef="backend/accounts/account_manager.py"
              nodes={[
                { id: '1', label: 'Fetch Balance', type: 'data' },
                { id: '2', label: 'Get Positions', type: 'data' },
                { id: '3', label: 'Calc Equity', type: 'process' },
                { id: '4', label: 'Update Curve', type: 'process' },
                { id: '5', label: 'Store History', type: 'output' },
              ]}
            />
          </div>
        );

      case 'timeline':
        return (
          <div>
            <h2 className="text-2xl font-bold text-white mb-4">Timeline & Workflows</h2>
            <p className="text-gray-400 mb-6">
              Time-based trading workflows throughout the trading day.
            </p>

            <Legend />

            {/* Daily Timeline */}
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="text-lg font-semibold text-white mb-4">Trading Day Timeline</h3>
              <p className="text-gray-400 text-sm mb-4">Complete flow of a trading day</p>

              <div className="relative">
                <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-700"></div>

                {[
                  { time: '4:00 AM', event: 'Pre-Market Data Fetch', type: 'data' as keyof typeof NODE_COLORS },
                  { time: '6:00 AM', event: 'GEX Analysis Begins', type: 'process' as keyof typeof NODE_COLORS },
                  { time: '9:00 AM', event: 'Market Regime Classification', type: 'ai' as keyof typeof NODE_COLORS },
                  { time: '9:30 AM', event: 'Market Open - Trading Begins', type: 'output' as keyof typeof NODE_COLORS },
                  { time: '10:00 AM', event: 'First Hour Analysis', type: 'process' as keyof typeof NODE_COLORS },
                  { time: '11:00 AM', event: 'Position Check', type: 'decision' as keyof typeof NODE_COLORS },
                  { time: '12:00 PM', event: 'Mid-Day Review', type: 'process' as keyof typeof NODE_COLORS },
                  { time: '2:00 PM', event: 'Final Hour Prep', type: 'decision' as keyof typeof NODE_COLORS },
                  { time: '3:00 PM', event: '0DTE Close Window', type: 'risk' as keyof typeof NODE_COLORS },
                  { time: '3:45 PM', event: 'EOD Position Close', type: 'output' as keyof typeof NODE_COLORS },
                  { time: '4:00 PM', event: 'Market Close', type: 'output' as keyof typeof NODE_COLORS },
                  { time: '4:30 PM', event: 'Daily Summary Generation', type: 'process' as keyof typeof NODE_COLORS },
                  { time: '5:00 PM', event: 'Model Recalibration', type: 'ai' as keyof typeof NODE_COLORS },
                ].map((item, idx) => (
                  <div key={idx} className="flex items-center gap-4 mb-4 relative">
                    <div className="w-8 h-8 rounded-full bg-gray-800 border-2 border-gray-600 flex items-center justify-center z-10">
                      <div className={`w-3 h-3 rounded-full ${NODE_COLORS[item.type].border.replace('border-', 'bg-')}`}></div>
                    </div>
                    <div className="flex-1 flex items-center gap-4">
                      <span className="text-gray-500 font-mono text-sm w-20">{item.time}</span>
                      <div className={`px-3 py-1 rounded ${NODE_COLORS[item.type].bg} ${NODE_COLORS[item.type].border} ${NODE_COLORS[item.type].text} text-sm border`}>
                        {item.event}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Pre-Market Flow */}
            <FlowChart
              title="Pre-Market Opening Flow"
              description="Preparations before market open"
              codeRef="backend/workflows/pre_market.py"
              nodes={[
                { id: '1', label: 'Fetch Overnight Data', type: 'data' },
                { id: '2', label: 'Analyze Futures', type: 'process' },
                { id: '3', label: 'Check News/Events', type: 'data' },
                { id: '4', label: 'Pre-calculate GEX', type: 'process' },
                { id: '5', label: 'Set Day Bias', type: 'ai' },
                { id: '6', label: 'Prepare Strategies', type: 'decision' },
              ]}
            />

            {/* Market Hours Loop */}
            <FlowChart
              title="Market Hours Trading Loop"
              description="Continuous loop during market hours"
              codeRef="backend/workflows/market_hours.py"
              nodes={[
                { id: '1', label: 'Poll Market Data', type: 'data' },
                { id: '2', label: 'Update GEX', type: 'process' },
                { id: '3', label: 'Check Signals', type: 'ai' },
                { id: '4', label: 'Evaluate Trades', type: 'decision' },
                { id: '5', label: 'Execute if Valid', type: 'output' },
                { id: '6', label: 'Manage Positions', type: 'process' },
                { id: '7', label: 'Loop (15 min)', type: 'process' },
              ]}
            />

            {/* Intraday Position Management */}
            <FlowChart
              title="Intraday Position Management"
              description="How positions are monitored and managed during the day"
              codeRef="backend/workflows/intraday_management.py"
              nodes={[
                { id: '1', label: 'Get Open Positions', type: 'data' },
                { id: '2', label: 'Calc Current P&L', type: 'process' },
                { id: '3', label: 'Check Exit Rules', type: 'decision' },
                { id: '4', label: 'Adjust Stops', type: 'risk' },
                { id: '5', label: 'Roll Decision', type: 'decision' },
                { id: '6', label: 'Execute Changes', type: 'output' },
              ]}
            />

            {/* Post-Market Flow */}
            <FlowChart
              title="Post-Market / EOD Flow"
              description="End of day reconciliation and reporting"
              codeRef="backend/workflows/post_market.py"
              nodes={[
                { id: '1', label: 'Close Positions', type: 'output' },
                { id: '2', label: 'Reconcile Trades', type: 'process' },
                { id: '3', label: 'Calculate Day P&L', type: 'process' },
                { id: '4', label: 'Update Equity Curve', type: 'data' },
                { id: '5', label: 'Generate Report', type: 'output' },
                { id: '6', label: 'Send Notifications', type: 'output' },
                { id: '7', label: 'Archive Logs', type: 'data' },
              ]}
            />
          </div>
        );

      default:
        return <div>Select a tab</div>;
    }
  };

  return (
    <div className="min-h-screen bg-gray-900">
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">System Processes & Flows</h1>
          <p className="text-gray-400">
            Complete visualization of all AlphaGEX processes, decision trees, and data flows
          </p>
        </div>

        {/* Search Bar */}
        <div className="mb-6">
          <input
            type="text"
            placeholder="Search processes, bots, or flows..."
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Tab Navigation */}
        <div className="flex flex-wrap gap-2 mb-6 border-b border-gray-700 pb-4">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-colors ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="min-h-[600px]">
          {renderTabContent()}
        </div>

        {/* Footer */}
        <div className="mt-8 pt-8 border-t border-gray-700">
          <div className="flex flex-wrap justify-between items-center gap-4">
            <div className="text-gray-500 text-sm">
              Last updated: {new Date().toLocaleString()}
            </div>
            <div className="flex gap-4">
              <button className="px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 text-sm">
                Export to PDF
              </button>
              <button className="px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 text-sm">
                Export to PNG
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
