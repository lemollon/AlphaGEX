'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import Navigation from '@/components/Navigation';

// ============================================================================
// TYPES & INTERFACES
// ============================================================================

interface ProcessNode {
  id: string;
  name: string;
  label: string;
  description: string;
  status: 'active' | 'inactive' | 'error' | 'unknown';
  lastRun?: string;
  codeFile?: string;
  category: string;
  type: NodeType;
  dependencies?: string[];
  executionHistory?: { timestamp: string; success: boolean; duration: number }[];
}

interface BotStatus {
  name: string;
  status: 'running' | 'stopped' | 'error';
  lastHeartbeat?: string;
  tradesExecuted?: number;
}

type NodeType = 'data' | 'decision' | 'process' | 'ai' | 'bot' | 'risk' | 'output';

interface FlowChartProps {
  id: string;
  title: string;
  nodes: { id: string; label: string; type: NodeType; dependencies?: string[] }[];
  description?: string;
  codeRef?: string;
  searchQuery?: string;
  onNodeClick?: (nodeId: string) => void;
  selectedNode?: string | null;
  showAnimations?: boolean;
  theme?: 'dark' | 'light';
}

// ============================================================================
// CONSTANTS
// ============================================================================

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
  { id: 'comparison', label: 'Comparison', icon: '⚖️' },
];

const NODE_COLORS = {
  dark: {
    data: { bg: 'bg-blue-900/30', border: 'border-blue-500', text: 'text-blue-400', glow: 'shadow-blue-500/50' },
    decision: { bg: 'bg-green-900/30', border: 'border-green-500', text: 'text-green-400', glow: 'shadow-green-500/50' },
    process: { bg: 'bg-yellow-900/30', border: 'border-yellow-500', text: 'text-yellow-400', glow: 'shadow-yellow-500/50' },
    ai: { bg: 'bg-purple-900/30', border: 'border-purple-500', text: 'text-purple-400', glow: 'shadow-purple-500/50' },
    bot: { bg: 'bg-pink-900/30', border: 'border-pink-500', text: 'text-pink-400', glow: 'shadow-pink-500/50' },
    risk: { bg: 'bg-red-900/30', border: 'border-red-500', text: 'text-red-400', glow: 'shadow-red-500/50' },
    output: { bg: 'bg-cyan-900/30', border: 'border-cyan-500', text: 'text-cyan-400', glow: 'shadow-cyan-500/50' },
  },
  light: {
    data: { bg: 'bg-blue-100', border: 'border-blue-600', text: 'text-blue-700', glow: 'shadow-blue-300/50' },
    decision: { bg: 'bg-green-100', border: 'border-green-600', text: 'text-green-700', glow: 'shadow-green-300/50' },
    process: { bg: 'bg-yellow-100', border: 'border-yellow-600', text: 'text-yellow-700', glow: 'shadow-yellow-300/50' },
    ai: { bg: 'bg-purple-100', border: 'border-purple-600', text: 'text-purple-700', glow: 'shadow-purple-300/50' },
    bot: { bg: 'bg-pink-100', border: 'border-pink-600', text: 'text-pink-700', glow: 'shadow-pink-300/50' },
    risk: { bg: 'bg-red-100', border: 'border-red-600', text: 'text-red-700', glow: 'shadow-red-300/50' },
    output: { bg: 'bg-cyan-100', border: 'border-cyan-600', text: 'text-cyan-700', glow: 'shadow-cyan-300/50' },
  },
};

// All searchable content for filtering
const ALL_PROCESSES = [
  { id: 'data-pipeline', title: 'Data Pipeline Flow', category: 'data', keywords: ['tradier', 'polygon', 'api', 'data', 'pipeline'] },
  { id: 'data-fallback', title: 'Data Priority & Fallback', category: 'data', keywords: ['fallback', 'priority', 'cache'] },
  { id: 'caching', title: 'Caching Strategies', category: 'data', keywords: ['cache', 'memory', 'database'] },
  { id: 'rate-limit', title: 'Rate Limiting', category: 'data', keywords: ['rate', 'limit', 'throttle'] },
  { id: 'error-handling', title: 'Error Handling', category: 'data', keywords: ['error', 'retry', 'recovery'] },
  { id: 'audit-trail', title: 'Audit Trail', category: 'data', keywords: ['audit', 'log', 'transparency'] },
  { id: 'regime', title: 'Market Regime Classification', category: 'decisions', keywords: ['regime', 'gex', 'market', 'panicking', 'trapped', 'hunting', 'defending'] },
  { id: 'strategy-selection', title: 'Strategy Selection Matrix', category: 'decisions', keywords: ['strategy', 'iron condor', 'spread', 'selection'] },
  { id: 'position-sizing', title: 'Position Sizing (Kelly)', category: 'decisions', keywords: ['kelly', 'position', 'size', 'risk'] },
  { id: 'exit-conditions', title: 'Exit Condition Checker', category: 'decisions', keywords: ['exit', 'profit', 'stop', 'loss'] },
  { id: 'roll-close', title: 'Roll vs Close Decision', category: 'decisions', keywords: ['roll', 'close', 'expiry'] },
  { id: 'vix-gate', title: 'VIX Gating Logic', category: 'decisions', keywords: ['vix', 'volatility', 'gate'] },
  { id: 'strike-selection', title: 'Strike Selection', category: 'decisions', keywords: ['strike', 'delta', 'premium'] },
  { id: 'trade-entry', title: 'Trade Entry Pipeline', category: 'execution', keywords: ['trade', 'entry', 'execute', 'order'] },
  { id: 'spread-exec', title: 'Multi-Leg Spread Execution', category: 'execution', keywords: ['spread', 'leg', 'iron condor'] },
  { id: 'paper-live', title: 'Paper vs Live Mode', category: 'execution', keywords: ['paper', 'live', 'simulate'] },
  { id: 'order-mgmt', title: 'Order Management', category: 'execution', keywords: ['order', 'fill', 'partial'] },
  { id: 'position-tracking', title: 'Position Tracking', category: 'execution', keywords: ['position', 'pnl', 'cost basis'] },
  { id: 'ares', title: 'ARES Bot', category: 'bots', keywords: ['ares', 'iron condor', '0dte', 'spx'] },
  { id: 'athena', title: 'ATHENA Bot', category: 'bots', keywords: ['athena', 'directional', 'spread'] },
  { id: 'apollo', title: 'APOLLO Bot', category: 'bots', keywords: ['apollo', 'scanner', 'ai'] },
  { id: 'argus', title: 'ARGUS Bot', category: 'bots', keywords: ['argus', 'gamma', 'monitor'] },
  { id: 'oracle', title: 'ORACLE Bot', category: 'bots', keywords: ['oracle', 'ml', 'prediction'] },
  { id: 'prometheus', title: 'PROMETHEUS Bot', category: 'bots', keywords: ['prometheus', 'training', 'ml'] },
  { id: 'phoenix', title: 'PHOENIX Bot', category: 'bots', keywords: ['phoenix', 'recovery'] },
  { id: 'hermes', title: 'HERMES Bot', category: 'bots', keywords: ['hermes', 'data', 'flow'] },
  { id: 'atlas', title: 'ATLAS Bot', category: 'bots', keywords: ['atlas', 'portfolio'] },
  { id: 'claude-ai', title: 'Claude AI Intelligence', category: 'ai', keywords: ['claude', 'gexis', 'ai', 'analysis'] },
  { id: 'ml-pattern', title: 'ML Pattern Learning', category: 'ai', keywords: ['ml', 'pattern', 'randomforest'] },
  { id: 'psychology', title: 'Psychology Trap Detector', category: 'ai', keywords: ['psychology', 'trap', 'fomo', 'revenge'] },
  { id: 'rag', title: 'Trading RAG System', category: 'ai', keywords: ['rag', 'retrieval', 'knowledge'] },
  { id: 'recommendations', title: 'AI Recommendations', category: 'ai', keywords: ['recommendation', 'suggest'] },
];

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

// Export to PNG using html2canvas
const exportToPNG = async (elementId: string, filename: string) => {
  try {
    const element = document.getElementById(elementId);
    if (!element) return;

    // Dynamic import of html2canvas
    const html2canvas = (await import('html2canvas')).default;
    const canvas = await html2canvas(element, {
      backgroundColor: '#1a1a2e',
      scale: 2,
    });

    const link = document.createElement('a');
    link.download = `${filename}-${new Date().toISOString().split('T')[0]}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  } catch (error) {
    console.error('Failed to export PNG:', error);
    alert('Export failed. Please try again.');
  }
};

// Export to PDF
const exportToPDF = async (elementId: string, filename: string) => {
  try {
    const element = document.getElementById(elementId);
    if (!element) return;

    const html2canvas = (await import('html2canvas')).default;
    const { jsPDF } = await import('jspdf');

    const canvas = await html2canvas(element, {
      backgroundColor: '#1a1a2e',
      scale: 2,
    });

    const imgData = canvas.toDataURL('image/png');
    const pdf = new jsPDF({
      orientation: canvas.width > canvas.height ? 'landscape' : 'portrait',
      unit: 'px',
      format: [canvas.width, canvas.height],
    });

    pdf.addImage(imgData, 'PNG', 0, 0, canvas.width, canvas.height);
    pdf.save(`${filename}-${new Date().toISOString().split('T')[0]}.pdf`);
  } catch (error) {
    console.error('Failed to export PDF:', error);
    alert('Export failed. Please try again.');
  }
};

// ============================================================================
// COMPONENTS
// ============================================================================

// Animated Flow Line Component
function AnimatedFlowLine({ active }: { active: boolean }) {
  if (!active) return <span className="text-gray-500 text-xl mx-1">→</span>;

  return (
    <div className="relative mx-1 w-8 h-6 flex items-center justify-center overflow-hidden">
      <div className="absolute inset-0 flex items-center">
        <div className="h-0.5 w-full bg-gray-600 relative overflow-hidden">
          <div className="absolute h-full w-3 bg-gradient-to-r from-transparent via-cyan-400 to-transparent animate-flow" />
        </div>
      </div>
      <span className="text-cyan-400 text-xl z-10">→</span>
    </div>
  );
}

// Enhanced FlowChart with Zoom, Pan, Dependency Highlighting, Animations
function FlowChart({
  id,
  title,
  nodes,
  description,
  codeRef,
  searchQuery = '',
  onNodeClick,
  selectedNode,
  showAnimations = false,
  theme = 'dark'
}: FlowChartProps) {
  const [expanded, setExpanded] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [nodeNotes, setNodeNotes] = useState<Record<string, string>>({});
  const [editingNote, setEditingNote] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const colors = NODE_COLORS[theme];

  // Check if this flowchart matches search
  const matchesSearch = searchQuery === '' ||
    title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    nodes.some(n => n.label.toLowerCase().includes(searchQuery.toLowerCase()));

  if (!matchesSearch) return null;

  // Find dependencies for highlighting
  const highlightedNodes = useMemo(() => {
    if (!selectedNode) return new Set<string>();
    const highlighted = new Set<string>([selectedNode]);

    // Find nodes that depend on selected
    nodes.forEach(node => {
      if (node.dependencies?.includes(selectedNode)) {
        highlighted.add(node.id);
      }
    });

    // Find nodes that selected depends on
    const selected = nodes.find(n => n.id === selectedNode);
    selected?.dependencies?.forEach(dep => highlighted.add(dep));

    return highlighted;
  }, [selectedNode, nodes]);

  // Mouse handlers for pan
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
    }
  };

  const handleMouseUp = () => setIsDragging(false);

  // Wheel handler for zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(z => Math.min(Math.max(z * delta, 0.5), 3));
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  return (
    <div className={`rounded-lg border mb-4 ${theme === 'dark' ? 'bg-gray-800/50 border-gray-700' : 'bg-white border-gray-300'}`}>
      <div
        className={`flex items-center justify-between p-4 cursor-pointer ${theme === 'dark' ? 'hover:bg-gray-700/30' : 'hover:bg-gray-100'}`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">{expanded ? '▼' : '▶'}</span>
          <h3 className={`text-lg font-semibold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{title}</h3>
        </div>
        <div className="flex items-center gap-2">
          {codeRef && (
            <span className="text-xs text-gray-500 font-mono">{codeRef}</span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="p-4 pt-0">
          {description && (
            <p className={`text-sm mb-4 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>{description}</p>
          )}

          {/* Zoom Controls */}
          <div className="flex items-center gap-2 mb-3">
            <button
              onClick={() => setZoom(z => Math.min(z * 1.2, 3))}
              className="px-2 py-1 bg-gray-700 text-white rounded text-sm hover:bg-gray-600"
            >
              🔍+
            </button>
            <button
              onClick={() => setZoom(z => Math.max(z * 0.8, 0.5))}
              className="px-2 py-1 bg-gray-700 text-white rounded text-sm hover:bg-gray-600"
            >
              🔍-
            </button>
            <button
              onClick={resetView}
              className="px-2 py-1 bg-gray-700 text-white rounded text-sm hover:bg-gray-600"
            >
              Reset
            </button>
            <span className="text-gray-500 text-sm ml-2">{Math.round(zoom * 100)}%</span>
          </div>

          {/* Diagram Container with Pan/Zoom */}
          <div
            ref={containerRef}
            className="overflow-hidden rounded-lg border border-gray-600 cursor-grab active:cursor-grabbing"
            style={{ minHeight: '120px' }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onWheel={handleWheel}
          >
            <div
              className="flex flex-wrap gap-3 items-center justify-center p-4 transition-transform"
              style={{
                transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
                transformOrigin: 'center center'
              }}
            >
              {nodes.map((node, idx) => {
                const isHighlighted = highlightedNodes.has(node.id);
                const isHovered = hoveredNode === node.id;
                const nodeColors = colors[node.type];

                return (
                  <div key={node.id} className="flex items-center gap-2">
                    <div
                      className={`
                        px-4 py-2 rounded-lg border-2 font-medium text-sm cursor-pointer
                        transition-all duration-200 relative
                        ${nodeColors.bg} ${nodeColors.border} ${nodeColors.text}
                        ${isHighlighted ? `shadow-lg ${nodeColors.glow}` : ''}
                        ${isHovered ? 'scale-110' : ''}
                        ${selectedNode === node.id ? 'ring-2 ring-white ring-offset-2 ring-offset-gray-800' : ''}
                      `}
                      title={node.label}
                      onClick={(e) => {
                        e.stopPropagation();
                        onNodeClick?.(node.id);
                      }}
                      onMouseEnter={() => setHoveredNode(node.id)}
                      onMouseLeave={() => setHoveredNode(null)}
                    >
                      {node.label}

                      {/* Execution indicator */}
                      <div className={`absolute -top-1 -right-1 w-2 h-2 rounded-full ${
                        Math.random() > 0.5 ? 'bg-green-500 animate-pulse' : 'bg-gray-500'
                      }`} />
                    </div>

                    {idx < nodes.length - 1 && (
                      <AnimatedFlowLine active={showAnimations} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Node Editor (when node is selected) */}
          {selectedNode && (
            <div className="mt-4 p-3 bg-gray-700/50 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-white font-medium">
                  Node: {nodes.find(n => n.id === selectedNode)?.label}
                </span>
                <button
                  onClick={() => onNodeClick?.(selectedNode)}
                  className="text-gray-400 hover:text-white"
                >
                  ✕
                </button>
              </div>
              <textarea
                className="w-full p-2 bg-gray-800 text-white rounded border border-gray-600 text-sm"
                placeholder="Add notes about this node..."
                value={nodeNotes[selectedNode] || ''}
                onChange={(e) => setNodeNotes({ ...nodeNotes, [selectedNode]: e.target.value })}
                rows={2}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Decision Tree component with enhancements
function DecisionTree({ title, tree, description, codeRef, theme = 'dark' as 'dark' | 'light', searchQuery = '' }: {
  title: string;
  tree: { condition: string; yes: string; no: string; yesType?: NodeType; noType?: NodeType }[];
  description?: string;
  codeRef?: string;
  theme?: 'dark' | 'light';
  searchQuery?: string;
}) {
  const [expanded, setExpanded] = useState(true);
  const colors = NODE_COLORS[theme];

  const matchesSearch = searchQuery === '' ||
    title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    tree.some(t =>
      t.condition.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.yes.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.no.toLowerCase().includes(searchQuery.toLowerCase())
    );

  if (!matchesSearch) return null;

  return (
    <div className={`rounded-lg border mb-4 ${theme === 'dark' ? 'bg-gray-800/50 border-gray-700' : 'bg-white border-gray-300'}`}>
      <div
        className={`flex items-center justify-between p-4 cursor-pointer ${theme === 'dark' ? 'hover:bg-gray-700/30' : 'hover:bg-gray-100'}`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">{expanded ? '▼' : '▶'}</span>
          <h3 className={`text-lg font-semibold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{title}</h3>
        </div>
        {codeRef && (
          <span className="text-xs text-gray-500 font-mono">{codeRef}</span>
        )}
      </div>

      {expanded && (
        <div className="p-4 pt-0">
          {description && (
            <p className={`text-sm mb-4 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>{description}</p>
          )}
          <div className="space-y-4">
            {tree.map((node, idx) => {
              const yesColors = colors[node.yesType || 'process'];
              const noColors = colors[node.noType || 'process'];

              return (
                <div key={idx} className="flex items-center gap-4 flex-wrap">
                  <div className={`px-4 py-2 rounded-lg border-2 font-medium ${colors.decision.bg} ${colors.decision.border} ${colors.decision.text}`}>
                    ◇ {node.condition}
                  </div>
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-green-500 text-sm font-bold">YES →</span>
                      <div className={`px-3 py-1 rounded border ${yesColors.bg} ${yesColors.border} ${yesColors.text} text-sm`}>
                        {node.yes}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-red-500 text-sm font-bold">NO →</span>
                      <div className={`px-3 py-1 rounded border ${noColors.bg} ${noColors.border} ${noColors.text} text-sm`}>
                        {node.no}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// Bot Status Card with Execution History
function BotCard({ bot, theme = 'dark' as 'dark' | 'light' }: {
  bot: {
    name: string;
    icon: string;
    description: string;
    status: string;
    features: string[];
    codeRef: string;
    executionHistory?: { timestamp: string; success: boolean; duration: number }[];
  };
  theme?: 'dark' | 'light';
}) {
  const [expanded, setExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const statusColors = {
    running: 'bg-green-500',
    stopped: 'bg-gray-500',
    error: 'bg-red-500',
  };

  // Mock execution history
  const history = bot.executionHistory || [
    { timestamp: new Date(Date.now() - 1000 * 60 * 5).toISOString(), success: true, duration: 234 },
    { timestamp: new Date(Date.now() - 1000 * 60 * 20).toISOString(), success: true, duration: 189 },
    { timestamp: new Date(Date.now() - 1000 * 60 * 35).toISOString(), success: false, duration: 45 },
    { timestamp: new Date(Date.now() - 1000 * 60 * 50).toISOString(), success: true, duration: 312 },
    { timestamp: new Date(Date.now() - 1000 * 60 * 65).toISOString(), success: true, duration: 198 },
  ];

  return (
    <div className={`rounded-lg border p-4 ${theme === 'dark' ? 'bg-gray-800/50 border-gray-700' : 'bg-white border-gray-300'}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{bot.icon}</span>
          <div>
            <h4 className={`font-semibold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{bot.name}</h4>
            <p className={`text-xs ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>{bot.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${statusColors[bot.status as keyof typeof statusColors] || 'bg-gray-500'} animate-pulse`} />
          <span className={`text-xs capitalize ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>{bot.status}</span>
        </div>
      </div>

      <div className="flex gap-2 mt-2">
        <button
          className="text-blue-400 text-sm hover:underline"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'Hide details' : 'Show details'}
        </button>
        <button
          className="text-purple-400 text-sm hover:underline"
          onClick={() => setShowHistory(!showHistory)}
        >
          {showHistory ? 'Hide history' : 'Execution history'}
        </button>
      </div>

      {expanded && (
        <div className={`mt-3 pt-3 border-t ${theme === 'dark' ? 'border-gray-700' : 'border-gray-300'}`}>
          <p className="text-xs text-gray-500 font-mono mb-2">{bot.codeRef}</p>
          <ul className={`text-sm space-y-1 ${theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}`}>
            {bot.features.map((f, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className="text-green-500">✓</span> {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {showHistory && (
        <div className={`mt-3 pt-3 border-t ${theme === 'dark' ? 'border-gray-700' : 'border-gray-300'}`}>
          <h5 className={`text-sm font-medium mb-2 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>Last 5 Executions</h5>
          <div className="space-y-1">
            {history.map((h, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className={theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}>
                  {new Date(h.timestamp).toLocaleTimeString()}
                </span>
                <span className={h.success ? 'text-green-400' : 'text-red-400'}>
                  {h.success ? '✓' : '✗'} {h.duration}ms
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Process Metrics component with live status
function ProcessMetrics({ metrics, theme = 'dark' as 'dark' | 'light' }: {
  metrics: { label: string; value: string | number; trend?: 'up' | 'down' | 'neutral'; live?: boolean }[];
  theme?: 'dark' | 'light';
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {metrics.map((m, i) => (
        <div key={i} className={`rounded-lg border p-4 ${theme === 'dark' ? 'bg-gray-800/50 border-gray-700' : 'bg-white border-gray-300'}`}>
          <div className="flex items-center justify-between">
            <p className={`text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>{m.label}</p>
            {m.live && <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />}
          </div>
          <p className={`text-2xl font-bold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{m.value}</p>
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
function Legend({ theme = 'dark' as 'dark' | 'light' }: { theme?: 'dark' | 'light' }) {
  const colors = NODE_COLORS[theme];

  return (
    <div className={`rounded-lg border p-4 mb-6 ${theme === 'dark' ? 'bg-gray-800/50 border-gray-700' : 'bg-white border-gray-300'}`}>
      <h4 className={`font-semibold mb-3 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>Color Legend</h4>
      <div className="flex flex-wrap gap-4">
        {Object.entries(colors).map(([type, c]) => (
          <div key={type} className="flex items-center gap-2">
            <div className={`w-4 h-4 rounded ${c.bg} border ${c.border}`} />
            <span className={`text-sm capitalize ${theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}`}>{type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Comparison View Component
function ComparisonView({ theme = 'dark' as 'dark' | 'light' }: { theme?: 'dark' | 'light' }) {
  const [mode, setMode] = useState<'paper' | 'live'>('paper');

  const paperFlow = [
    { id: '1', label: 'Signal Generated', type: 'ai' as NodeType },
    { id: '2', label: 'Validate Setup', type: 'decision' as NodeType },
    { id: '3', label: 'Paper Portfolio Check', type: 'process' as NodeType },
    { id: '4', label: 'Simulate Execution', type: 'process' as NodeType },
    { id: '5', label: 'Update Paper P&L', type: 'output' as NodeType },
  ];

  const liveFlow = [
    { id: '1', label: 'Signal Generated', type: 'ai' as NodeType },
    { id: '2', label: 'Validate Setup', type: 'decision' as NodeType },
    { id: '3', label: 'Account Balance Check', type: 'risk' as NodeType },
    { id: '4', label: 'Broker API Call', type: 'data' as NodeType },
    { id: '5', label: 'Order Submission', type: 'output' as NodeType },
    { id: '6', label: 'Fill Confirmation', type: 'output' as NodeType },
    { id: '7', label: 'Position Update', type: 'data' as NodeType },
  ];

  return (
    <div>
      <h2 className={`text-2xl font-bold mb-4 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
        Paper vs Live Comparison
      </h2>
      <p className={`mb-6 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
        Compare the execution flow between paper trading and live trading modes.
      </p>

      <div className="flex gap-4 mb-6">
        <button
          onClick={() => setMode('paper')}
          className={`px-4 py-2 rounded-lg ${mode === 'paper' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300'}`}
        >
          Paper Mode
        </button>
        <button
          onClick={() => setMode('live')}
          className={`px-4 py-2 rounded-lg ${mode === 'live' ? 'bg-red-600 text-white' : 'bg-gray-700 text-gray-300'}`}
        >
          Live Mode
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className={`p-4 rounded-lg border ${mode === 'paper' ? 'border-blue-500 ring-2 ring-blue-500/50' : 'border-gray-700 opacity-50'}`}>
          <h3 className="text-lg font-semibold text-blue-400 mb-4">Paper Trading Flow</h3>
          <FlowChart
            id="paper-flow"
            title="Paper Execution"
            nodes={paperFlow}
            description="Simulated trading without real money"
            theme={theme}
          />
          <div className="mt-4 space-y-2 text-sm text-gray-400">
            <p>✓ No real money at risk</p>
            <p>✓ Instant simulated fills</p>
            <p>✓ No broker API calls</p>
            <p>✓ Simplified flow</p>
          </div>
        </div>

        <div className={`p-4 rounded-lg border ${mode === 'live' ? 'border-red-500 ring-2 ring-red-500/50' : 'border-gray-700 opacity-50'}`}>
          <h3 className="text-lg font-semibold text-red-400 mb-4">Live Trading Flow</h3>
          <FlowChart
            id="live-flow"
            title="Live Execution"
            nodes={liveFlow}
            description="Real trading with actual capital"
            theme={theme}
          />
          <div className="mt-4 space-y-2 text-sm text-gray-400">
            <p>⚠️ Real money at risk</p>
            <p>⚠️ Market fills (may slip)</p>
            <p>⚠️ Broker API integration</p>
            <p>⚠️ Additional validation steps</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// Print Optimized View Component
function PrintView({ onClose, theme }: { onClose: () => void; theme: 'dark' | 'light' }) {
  return (
    <div className="fixed inset-0 bg-white z-50 overflow-auto print:relative">
      <div className="max-w-4xl mx-auto p-8">
        <div className="flex justify-between items-center mb-8 print:hidden">
          <h1 className="text-2xl font-bold text-gray-900">AlphaGEX System Documentation</h1>
          <div className="flex gap-4">
            <button
              onClick={() => window.print()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg"
            >
              Print
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg"
            >
              Close
            </button>
          </div>
        </div>

        <div className="prose max-w-none">
          <h1 className="text-3xl font-bold mb-4">AlphaGEX Trading System</h1>
          <p className="text-gray-600 mb-8">Complete system architecture and process documentation</p>

          <h2 className="text-xl font-bold mt-8 mb-4">1. Data Layer</h2>
          <ul className="list-disc pl-6 text-gray-700">
            <li>Tradier API (Primary data source)</li>
            <li>Polygon API (Secondary)</li>
            <li>Trading Volatility (GEX data)</li>
            <li>FRED API (Economic data)</li>
            <li>Yahoo Finance (Backup)</li>
          </ul>

          <h2 className="text-xl font-bold mt-8 mb-4">2. Decision Engines</h2>
          <ul className="list-disc pl-6 text-gray-700">
            <li>Market Regime Classification (5 states)</li>
            <li>Strategy Selection Matrix (61+ paths)</li>
            <li>Position Sizing (Kelly Criterion)</li>
            <li>Exit Condition Checker</li>
            <li>VIX Gating Logic</li>
          </ul>

          <h2 className="text-xl font-bold mt-8 mb-4">3. Autonomous Bots</h2>
          <ul className="list-disc pl-6 text-gray-700">
            <li>ARES - 0DTE Iron Condor</li>
            <li>ATHENA - Directional Spreads</li>
            <li>APOLLO - AI Scanner</li>
            <li>ARGUS - Gamma Monitor</li>
            <li>ORACLE - ML Predictions</li>
            <li>PROMETHEUS - ML Training</li>
            <li>PHOENIX - Recovery</li>
            <li>HERMES - Data Flow</li>
            <li>ATLAS - Portfolio Manager</li>
          </ul>

          <div className="mt-8 pt-4 border-t text-sm text-gray-500">
            Generated: {new Date().toLocaleString()}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// MAIN PAGE COMPONENT
// ============================================================================

export default function SystemProcessesPage() {
  const [activeTab, setActiveTab] = useState('overview');
  const [searchQuery, setSearchQuery] = useState('');
  const [botStatuses, setBotStatuses] = useState<Record<string, string>>({});
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [showAnimations, setShowAnimations] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [showPrintView, setShowPrintView] = useState(false);
  const [processStatuses, setProcessStatuses] = useState<Record<string, 'active' | 'inactive' | 'error'>>({});
  const contentRef = useRef<HTMLDivElement>(null);

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

  // Simulate live process statuses
  useEffect(() => {
    const updateStatuses = () => {
      const statuses: Record<string, 'active' | 'inactive' | 'error'> = {};
      ALL_PROCESSES.forEach(p => {
        const rand = Math.random();
        statuses[p.id] = rand > 0.7 ? 'active' : rand > 0.1 ? 'inactive' : 'error';
      });
      setProcessStatuses(statuses);
    };

    updateStatuses();
    const interval = setInterval(updateStatuses, 10000);
    return () => clearInterval(interval);
  }, []);

  // Filter processes based on search
  const filteredProcesses = useMemo(() => {
    if (!searchQuery) return ALL_PROCESSES;
    const query = searchQuery.toLowerCase();
    return ALL_PROCESSES.filter(p =>
      p.title.toLowerCase().includes(query) ||
      p.keywords.some(k => k.includes(query))
    );
  }, [searchQuery]);

  // Handle node click for dependency mapping
  const handleNodeClick = useCallback((nodeId: string) => {
    setSelectedNode(prev => prev === nodeId ? null : nodeId);
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
            <h2 className={`text-2xl font-bold mb-4 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
              AlphaGEX System Overview
            </h2>
            <p className={`mb-6 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
              Complete visualization of all processes, decision trees, and data flows in the AlphaGEX trading system.
            </p>

            <ProcessMetrics
              theme={theme}
              metrics={[
                { label: 'Active Processes', value: Object.values(processStatuses).filter(s => s === 'active').length, trend: 'neutral', live: true },
                { label: 'Bots Running', value: Object.values(botStatuses).filter(s => s === 'running').length, trend: 'up', live: true },
                { label: 'Data Sources', value: 6, trend: 'neutral' },
                { label: 'Decision Paths', value: '61+', trend: 'neutral' },
              ]}
            />

            <Legend theme={theme} />

            {/* Master System Flow */}
            <FlowChart
              id="master-flow"
              title="Master System Flow"
              description="High-level overview of how data flows through AlphaGEX from input to trade execution"
              theme={theme}
              showAnimations={showAnimations}
              selectedNode={selectedNode}
              onNodeClick={handleNodeClick}
              nodes={[
                { id: 'api', label: 'Market Data APIs', type: 'data' },
                { id: 'data-layer', label: 'Data Layer', type: 'data', dependencies: ['api'] },
                { id: 'analysis', label: 'Analysis Engine', type: 'process', dependencies: ['data-layer'] },
                { id: 'ai-ml', label: 'AI/ML Systems', type: 'ai', dependencies: ['analysis'] },
                { id: 'decision', label: 'Decision Engine', type: 'decision', dependencies: ['ai-ml'] },
                { id: 'risk', label: 'Risk Validation', type: 'risk', dependencies: ['decision'] },
                { id: 'execute', label: 'Trade Execution', type: 'output', dependencies: ['risk'] },
              ]}
            />

            {/* Trading Loop */}
            <FlowChart
              id="trading-loop"
              title="Autonomous Trading Loop"
              description="The continuous cycle of analysis, decision-making, and execution"
              codeRef="backend/trading/trading_loop.py"
              theme={theme}
              showAnimations={showAnimations}
              selectedNode={selectedNode}
              onNodeClick={handleNodeClick}
              nodes={[
                { id: 't1', label: 'Market Open Check', type: 'decision' },
                { id: 't2', label: 'Fetch Market Data', type: 'data', dependencies: ['t1'] },
                { id: 't3', label: 'Calculate GEX/Greeks', type: 'process', dependencies: ['t2'] },
                { id: 't4', label: 'Classify Regime', type: 'ai', dependencies: ['t3'] },
                { id: 't5', label: 'Select Strategy', type: 'decision', dependencies: ['t4'] },
                { id: 't6', label: 'Size Position', type: 'process', dependencies: ['t5'] },
                { id: 't7', label: 'Validate Risk', type: 'risk', dependencies: ['t6'] },
                { id: 't8', label: 'Execute Trade', type: 'output', dependencies: ['t7'] },
              ]}
            />

            {/* Category Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
              {TABS.slice(1, -1).map(tab => (
                <div
                  key={tab.id}
                  className={`rounded-lg border p-4 cursor-pointer transition-colors ${
                    theme === 'dark'
                      ? 'bg-gray-800/50 border-gray-700 hover:border-blue-500'
                      : 'bg-white border-gray-300 hover:border-blue-500'
                  }`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-2xl">{tab.icon}</span>
                    <h3 className={`font-semibold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{tab.label}</h3>
                  </div>
                  <p className={`text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
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
            <h2 className={`text-2xl font-bold mb-4 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>Data Layer</h2>
            <p className={`mb-6 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
              All data pipelines, sources, caching strategies, and error handling flows.
            </p>

            <Legend theme={theme} />

            <FlowChart
              id="data-pipeline"
              title="Data Pipeline Flow"
              description="How market data flows from external APIs through processing to the database"
              codeRef="backend/data/unified_data_provider.py"
              searchQuery={searchQuery}
              theme={theme}
              showAnimations={showAnimations}
              selectedNode={selectedNode}
              onNodeClick={handleNodeClick}
              nodes={[
                { id: 'd1', label: 'Tradier API', type: 'data' },
                { id: 'd2', label: 'Polygon API', type: 'data' },
                { id: 'd3', label: 'Trading Volatility', type: 'data' },
                { id: 'd4', label: 'FRED API', type: 'data' },
                { id: 'd5', label: 'Yahoo Finance', type: 'data' },
                { id: 'd6', label: 'Unified Provider', type: 'process', dependencies: ['d1', 'd2', 'd3', 'd4', 'd5'] },
                { id: 'd7', label: 'Cache Layer', type: 'process', dependencies: ['d6'] },
                { id: 'd8', label: 'Database', type: 'output', dependencies: ['d7'] },
              ]}
            />

            <DecisionTree
              title="Data Priority & Fallback Hierarchy"
              description="When a data source fails, the system falls back to alternatives"
              codeRef="backend/data/data_priority.py"
              theme={theme}
              searchQuery={searchQuery}
              tree={[
                { condition: 'Tradier Available?', yes: 'Use Tradier (Primary)', no: 'Try Polygon', yesType: 'data', noType: 'decision' },
                { condition: 'Polygon Available?', yes: 'Use Polygon (Secondary)', no: 'Try Yahoo', yesType: 'data', noType: 'decision' },
                { condition: 'Yahoo Available?', yes: 'Use Yahoo (Tertiary)', no: 'Use Cached Data', yesType: 'data', noType: 'risk' },
              ]}
            />

            <FlowChart
              id="caching"
              title="Caching Strategies"
              description="Multi-tier caching for performance optimization"
              codeRef="backend/data/cache_manager.py"
              searchQuery={searchQuery}
              theme={theme}
              showAnimations={showAnimations}
              nodes={[
                { id: 'c1', label: 'Request', type: 'data' },
                { id: 'c2', label: 'In-Memory Cache', type: 'process' },
                { id: 'c3', label: 'Database Cache', type: 'process' },
                { id: 'c4', label: 'API Call', type: 'data' },
                { id: 'c5', label: 'Update Caches', type: 'process' },
                { id: 'c6', label: 'Return Data', type: 'output' },
              ]}
            />

            <DecisionTree
              title="Rate Limiting & Throttling"
              description="Prevents API rate limit violations"
              codeRef="backend/data/rate_limiter.py"
              theme={theme}
              searchQuery={searchQuery}
              tree={[
                { condition: 'Under Rate Limit?', yes: 'Make API Call', no: 'Queue Request', yesType: 'output', noType: 'process' },
                { condition: 'Queue Full?', yes: 'Return Cached', no: 'Wait & Retry', yesType: 'data', noType: 'process' },
              ]}
            />

            <FlowChart
              id="error-handling"
              title="Error Handling & Recovery"
              description="Graceful degradation when data sources fail"
              codeRef="backend/data/error_handler.py"
              searchQuery={searchQuery}
              theme={theme}
              showAnimations={showAnimations}
              nodes={[
                { id: 'e1', label: 'API Error', type: 'risk' },
                { id: 'e2', label: 'Retry (3x)', type: 'process' },
                { id: 'e3', label: 'Exponential Backoff', type: 'process' },
                { id: 'e4', label: 'Fallback Source', type: 'decision' },
                { id: 'e5', label: 'Use Stale Cache', type: 'data' },
                { id: 'e6', label: 'Alert & Log', type: 'output' },
              ]}
            />
          </div>
        );

      case 'bots':
        return (
          <div>
            <h2 className={`text-2xl font-bold mb-4 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
              Autonomous Bots
            </h2>
            <p className={`mb-6 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
              All autonomous trading and monitoring bots in the AlphaGEX system.
            </p>

            <ProcessMetrics
              theme={theme}
              metrics={[
                { label: 'Total Bots', value: 9, trend: 'neutral' },
                { label: 'Running', value: Object.values(botStatuses).filter(s => s === 'running').length, trend: 'up', live: true },
                { label: 'Stopped', value: Object.values(botStatuses).filter(s => s === 'stopped').length, trend: 'neutral' },
                { label: 'Errors', value: Object.values(botStatuses).filter(s => s === 'error').length, trend: 'down' },
              ]}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {bots.map(bot => (
                <BotCard key={bot.name} bot={bot} theme={theme} />
              ))}
            </div>

            <div className="mt-6">
              <FlowChart
                id="bot-orchestration"
                title="Bot Orchestration Flow"
                description="How bots coordinate and communicate"
                codeRef="backend/bots/orchestrator.py"
                theme={theme}
                showAnimations={showAnimations}
                nodes={[
                  { id: 'b1', label: 'Scheduler', type: 'process' },
                  { id: 'b2', label: 'Health Check', type: 'decision' },
                  { id: 'b3', label: 'Start Bots', type: 'bot' },
                  { id: 'b4', label: 'Monitor Heartbeats', type: 'process' },
                  { id: 'b5', label: 'Handle Failures', type: 'risk' },
                  { id: 'b6', label: 'Log Activity', type: 'output' },
                ]}
              />
            </div>
          </div>
        );

      case 'comparison':
        return <ComparisonView theme={theme} />;

      default:
        return (
          <div className={`text-center py-12 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
            <p className="text-xl">Select a tab to view processes</p>
            <p className="text-sm mt-2">This section is under development</p>
          </div>
        );
    }
  };

  // Show print view
  if (showPrintView) {
    return <PrintView onClose={() => setShowPrintView(false)} theme={theme} />;
  }

  return (
    <div className={`min-h-screen ${theme === 'dark' ? 'bg-gray-900' : 'bg-gray-100'}`}>
      <Navigation />

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <h1 className={`text-3xl font-bold mb-2 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
                System Processes & Flows
              </h1>
              <p className={theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}>
                Complete visualization of all AlphaGEX processes, decision trees, and data flows
              </p>
            </div>

            {/* Theme & Animation Controls */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
                className={`px-3 py-2 rounded-lg text-sm ${
                  theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white text-gray-900 border border-gray-300'
                }`}
              >
                {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
              </button>
              <button
                onClick={() => setShowAnimations(!showAnimations)}
                className={`px-3 py-2 rounded-lg text-sm ${
                  showAnimations
                    ? 'bg-cyan-600 text-white'
                    : theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white text-gray-900 border border-gray-300'
                }`}
              >
                {showAnimations ? '⚡ Animated' : '⏸️ Static'}
              </button>
              <button
                onClick={() => setShowPrintView(true)}
                className={`px-3 py-2 rounded-lg text-sm ${
                  theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white text-gray-900 border border-gray-300'
                }`}
              >
                🖨️ Print View
              </button>
            </div>
          </div>
        </div>

        {/* Search Bar with live filtering */}
        <div className="mb-6">
          <div className="relative">
            <input
              type="text"
              placeholder="Search processes, bots, or flows... (try: 'ares', 'gex', 'iron condor')"
              className={`w-full px-4 py-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                theme === 'dark'
                  ? 'bg-gray-800 border border-gray-700 text-white placeholder-gray-500'
                  : 'bg-white border border-gray-300 text-gray-900 placeholder-gray-400'
              }`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <div className={`absolute right-3 top-1/2 -translate-y-1/2 text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
                {filteredProcesses.length} results
              </div>
            )}
          </div>

          {/* Search Results Preview */}
          {searchQuery && filteredProcesses.length > 0 && (
            <div className={`mt-2 p-3 rounded-lg ${theme === 'dark' ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-300'}`}>
              <p className={`text-xs mb-2 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>Found in:</p>
              <div className="flex flex-wrap gap-2">
                {filteredProcesses.slice(0, 8).map(p => (
                  <span
                    key={p.id}
                    className={`px-2 py-1 rounded text-xs cursor-pointer ${
                      theme === 'dark' ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                    onClick={() => setActiveTab(p.category)}
                  >
                    {p.title}
                  </span>
                ))}
                {filteredProcesses.length > 8 && (
                  <span className={`text-xs ${theme === 'dark' ? 'text-gray-500' : 'text-gray-400'}`}>
                    +{filteredProcesses.length - 8} more
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Tab Navigation */}
        <div className={`flex flex-wrap gap-2 mb-6 border-b pb-4 ${theme === 'dark' ? 'border-gray-700' : 'border-gray-300'}`}>
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-colors ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : theme === 'dark'
                    ? 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-300'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div id="content-area" ref={contentRef} className="min-h-[600px]">
          {renderTabContent()}
        </div>

        {/* Footer */}
        <div className={`mt-8 pt-8 border-t ${theme === 'dark' ? 'border-gray-700' : 'border-gray-300'}`}>
          <div className="flex flex-wrap justify-between items-center gap-4">
            <div className={`text-sm ${theme === 'dark' ? 'text-gray-500' : 'text-gray-400'}`}>
              Last updated: {new Date().toLocaleString()}
              {selectedNode && (
                <span className="ml-4">
                  Selected: <span className="text-blue-400">{selectedNode}</span>
                </span>
              )}
            </div>
            <div className="flex gap-4">
              <button
                onClick={() => exportToPDF('content-area', 'alphagex-system')}
                className={`px-4 py-2 rounded-lg text-sm ${
                  theme === 'dark' ? 'bg-gray-800 text-gray-300 hover:bg-gray-700' : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-300'
                }`}
              >
                📄 Export PDF
              </button>
              <button
                onClick={() => exportToPNG('content-area', 'alphagex-system')}
                className={`px-4 py-2 rounded-lg text-sm ${
                  theme === 'dark' ? 'bg-gray-800 text-gray-300 hover:bg-gray-700' : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-300'
                }`}
              >
                🖼️ Export PNG
              </button>
            </div>
          </div>
        </div>
      </main>

      {/* CSS for animations */}
      <style jsx global>{`
        @keyframes flow {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
        .animate-flow {
          animation: flow 1.5s linear infinite;
        }

        @media print {
          .print\\:hidden { display: none !important; }
          .print\\:relative { position: relative !important; }
        }
      `}</style>
    </div>
  );
}
