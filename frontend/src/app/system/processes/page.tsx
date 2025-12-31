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
  executionHistory?: ExecutionRecord[];
  metrics?: ProcessMetrics;
}

interface ExecutionRecord {
  timestamp: string;
  success: boolean;
  duration: number;
}

interface ProcessMetrics {
  avgDuration: number;
  successRate: number;
  executionCount: number;
  lastError?: string;
}

interface BotStatus {
  name: string;
  status: 'running' | 'stopped' | 'error';
  lastHeartbeat?: string;
  tradesExecuted?: number;
  pnlToday?: number;
}

type NodeType = 'data' | 'decision' | 'process' | 'ai' | 'bot' | 'risk' | 'output';
type LayoutType = 'horizontal' | 'vertical' | 'tree' | 'radial';
type StatusFilter = 'all' | 'active' | 'inactive' | 'error' | 'ai' | 'bots';

interface Comment {
  id: string;
  nodeId: string;
  text: string;
  author: string;
  timestamp: string;
}

// ============================================================================
// CONSTANTS
// ============================================================================

const TABS = [
  { id: 'overview', label: 'Overview', icon: '🏠', shortcut: '1' },
  { id: 'data', label: 'Data Layer', icon: '📊', shortcut: '2' },
  { id: 'decisions', label: 'Decision Engines', icon: '🧠', shortcut: '3' },
  { id: 'execution', label: 'Execution', icon: '⚡', shortcut: '4' },
  { id: 'bots', label: 'Autonomous Bots', icon: '🤖', shortcut: '5' },
  { id: 'ai', label: 'AI/ML Systems', icon: '🔮', shortcut: '6' },
  { id: 'analysis', label: 'Analysis', icon: '📈', shortcut: '7' },
  { id: 'strategy', label: 'Strategies', icon: '♟️', shortcut: '8' },
  { id: 'operations', label: 'Operations', icon: '⚙️', shortcut: '9' },
  { id: 'timeline', label: 'Timeline', icon: '⏰', shortcut: '0' },
  { id: 'comparison', label: 'Comparison', icon: '⚖️', shortcut: '' },
];

const NODE_COLORS = {
  dark: {
    data: { bg: 'bg-blue-900/30', border: 'border-blue-500', text: 'text-blue-400', glow: 'shadow-blue-500/50', hex: '#3b82f6' },
    decision: { bg: 'bg-green-900/30', border: 'border-green-500', text: 'text-green-400', glow: 'shadow-green-500/50', hex: '#22c55e' },
    process: { bg: 'bg-yellow-900/30', border: 'border-yellow-500', text: 'text-yellow-400', glow: 'shadow-yellow-500/50', hex: '#eab308' },
    ai: { bg: 'bg-purple-900/30', border: 'border-purple-500', text: 'text-purple-400', glow: 'shadow-purple-500/50', hex: '#a855f7' },
    bot: { bg: 'bg-pink-900/30', border: 'border-pink-500', text: 'text-pink-400', glow: 'shadow-pink-500/50', hex: '#ec4899' },
    risk: { bg: 'bg-red-900/30', border: 'border-red-500', text: 'text-red-400', glow: 'shadow-red-500/50', hex: '#ef4444' },
    output: { bg: 'bg-cyan-900/30', border: 'border-cyan-500', text: 'text-cyan-400', glow: 'shadow-cyan-500/50', hex: '#06b6d4' },
  },
  light: {
    data: { bg: 'bg-blue-100', border: 'border-blue-600', text: 'text-blue-700', glow: 'shadow-blue-300/50', hex: '#2563eb' },
    decision: { bg: 'bg-green-100', border: 'border-green-600', text: 'text-green-700', glow: 'shadow-green-300/50', hex: '#16a34a' },
    process: { bg: 'bg-yellow-100', border: 'border-yellow-600', text: 'text-yellow-700', glow: 'shadow-yellow-300/50', hex: '#ca8a04' },
    ai: { bg: 'bg-purple-100', border: 'border-purple-600', text: 'text-purple-700', glow: 'shadow-purple-300/50', hex: '#9333ea' },
    bot: { bg: 'bg-pink-100', border: 'border-pink-600', text: 'text-pink-700', glow: 'shadow-pink-300/50', hex: '#db2777' },
    risk: { bg: 'bg-red-100', border: 'border-red-600', text: 'text-red-700', glow: 'shadow-red-300/50', hex: '#dc2626' },
    output: { bg: 'bg-cyan-100', border: 'border-cyan-600', text: 'text-cyan-700', glow: 'shadow-cyan-300/50', hex: '#0891b2' },
  },
};

const ALL_PROCESSES = [
  { id: 'data-pipeline', title: 'Data Pipeline Flow', category: 'data', keywords: ['tradier', 'polygon', 'api', 'data', 'pipeline'], type: 'data' as NodeType },
  { id: 'data-fallback', title: 'Data Priority & Fallback', category: 'data', keywords: ['fallback', 'priority', 'cache'], type: 'data' as NodeType },
  { id: 'caching', title: 'Caching Strategies', category: 'data', keywords: ['cache', 'memory', 'database'], type: 'process' as NodeType },
  { id: 'rate-limit', title: 'Rate Limiting', category: 'data', keywords: ['rate', 'limit', 'throttle'], type: 'process' as NodeType },
  { id: 'error-handling', title: 'Error Handling', category: 'data', keywords: ['error', 'retry', 'recovery'], type: 'risk' as NodeType },
  { id: 'audit-trail', title: 'Audit Trail', category: 'data', keywords: ['audit', 'log', 'transparency'], type: 'output' as NodeType },
  { id: 'regime', title: 'Market Regime Classification', category: 'decisions', keywords: ['regime', 'gex', 'market'], type: 'ai' as NodeType },
  { id: 'strategy-selection', title: 'Strategy Selection Matrix', category: 'decisions', keywords: ['strategy', 'iron condor'], type: 'decision' as NodeType },
  { id: 'position-sizing', title: 'Position Sizing (Kelly)', category: 'decisions', keywords: ['kelly', 'position', 'size'], type: 'decision' as NodeType },
  { id: 'exit-conditions', title: 'Exit Condition Checker', category: 'decisions', keywords: ['exit', 'profit', 'stop'], type: 'decision' as NodeType },
  { id: 'vix-gate', title: 'VIX Gating Logic', category: 'decisions', keywords: ['vix', 'volatility'], type: 'risk' as NodeType },
  { id: 'trade-entry', title: 'Trade Entry Pipeline', category: 'execution', keywords: ['trade', 'entry', 'execute'], type: 'output' as NodeType },
  { id: 'ares', title: 'ARES Bot', category: 'bots', keywords: ['ares', 'iron condor', '0dte'], type: 'bot' as NodeType },
  { id: 'athena', title: 'ATHENA Bot', category: 'bots', keywords: ['athena', 'directional'], type: 'bot' as NodeType },
  { id: 'apollo', title: 'APOLLO Bot', category: 'bots', keywords: ['apollo', 'scanner'], type: 'bot' as NodeType },
  { id: 'argus', title: 'ARGUS Bot', category: 'bots', keywords: ['argus', 'gamma'], type: 'bot' as NodeType },
  { id: 'oracle', title: 'ORACLE Bot', category: 'bots', keywords: ['oracle', 'ml'], type: 'bot' as NodeType },
  { id: 'prometheus', title: 'PROMETHEUS Bot', category: 'bots', keywords: ['prometheus', 'training'], type: 'bot' as NodeType },
  { id: 'phoenix', title: 'PHOENIX Bot', category: 'bots', keywords: ['phoenix', 'recovery'], type: 'bot' as NodeType },
  { id: 'hermes', title: 'HERMES Bot', category: 'bots', keywords: ['hermes', 'data'], type: 'bot' as NodeType },
  { id: 'atlas', title: 'ATLAS Bot', category: 'bots', keywords: ['atlas', 'portfolio'], type: 'bot' as NodeType },
  { id: 'solomon', title: 'SOLOMON Bot', category: 'bots', keywords: ['solomon', 'feedback', 'loop', 'optimization', 'self-improving'], type: 'bot' as NodeType },
  { id: 'claude-ai', title: 'Claude AI Intelligence', category: 'ai', keywords: ['claude', 'gexis'], type: 'ai' as NodeType },
  { id: 'ml-pattern', title: 'ML Pattern Learning', category: 'ai', keywords: ['ml', 'pattern'], type: 'ai' as NodeType },
  { id: 'psychology', title: 'Psychology Trap Detector', category: 'ai', keywords: ['psychology', 'trap'], type: 'ai' as NodeType },
];

const KEYBOARD_SHORTCUTS = [
  { key: '/', description: 'Focus search' },
  { key: '1-9', description: 'Switch tabs' },
  { key: 'Esc', description: 'Clear selection' },
  { key: '+/-', description: 'Zoom in/out' },
  { key: 'r', description: 'Reset view' },
  { key: 't', description: 'Toggle theme' },
  { key: 'a', description: 'Toggle animations' },
  { key: 'f', description: 'Toggle favorites' },
  { key: '?', description: 'Show shortcuts' },
];

// ============================================================================
// HOOKS
// ============================================================================

// Custom hook for WebSocket connection
function useWebSocket(url: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setIsConnected(true);
      ws.onclose = () => setIsConnected(false);
      ws.onmessage = (event) => {
        try {
          setLastMessage(JSON.parse(event.data));
        } catch {
          setLastMessage(event.data);
        }
      };

      return () => ws.close();
    } catch {
      // WebSocket not available, fallback to polling
      setIsConnected(false);
    }
  }, [url]);

  return { isConnected, lastMessage };
}

// Custom hook for localStorage persistence
function useLocalStorage<T>(key: string, initialValue: T): [T, (value: T) => void] {
  const [storedValue, setStoredValue] = useState<T>(initialValue);

  useEffect(() => {
    try {
      const item = window.localStorage.getItem(key);
      if (item) setStoredValue(JSON.parse(item));
    } catch {}
  }, [key]);

  const setValue = (value: T) => {
    setStoredValue(value);
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {}
  };

  return [storedValue, setValue];
}

// Custom hook for keyboard shortcuts
function useKeyboardShortcuts(handlers: Record<string, () => void>) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        if (e.key === 'Escape') {
          (e.target as HTMLElement).blur();
        }
        return;
      }

      const key = e.key.toLowerCase();
      if (handlers[key]) {
        e.preventDefault();
        handlers[key]();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handlers]);
}

// Custom hook for touch gestures
function useTouchGestures(ref: React.RefObject<HTMLElement>, handlers: {
  onPinch?: (scale: number) => void;
  onPan?: (dx: number, dy: number) => void;
  onSwipe?: (direction: 'left' | 'right') => void;
}) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let startDistance = 0;
    let startX = 0;
    let startY = 0;

    const handleTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        startDistance = Math.sqrt(dx * dx + dy * dy);
      } else if (e.touches.length === 1) {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
      }
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (e.touches.length === 2 && handlers.onPinch) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const distance = Math.sqrt(dx * dx + dy * dy);
        handlers.onPinch(distance / startDistance);
        startDistance = distance;
      } else if (e.touches.length === 1 && handlers.onPan) {
        const dx = e.touches[0].clientX - startX;
        const dy = e.touches[0].clientY - startY;
        handlers.onPan(dx, dy);
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
      }
    };

    const handleTouchEnd = (e: TouchEvent) => {
      if (handlers.onSwipe && e.changedTouches.length === 1) {
        const dx = e.changedTouches[0].clientX - startX;
        if (Math.abs(dx) > 50) {
          handlers.onSwipe(dx > 0 ? 'right' : 'left');
        }
      }
    };

    el.addEventListener('touchstart', handleTouchStart);
    el.addEventListener('touchmove', handleTouchMove);
    el.addEventListener('touchend', handleTouchEnd);

    return () => {
      el.removeEventListener('touchstart', handleTouchStart);
      el.removeEventListener('touchmove', handleTouchMove);
      el.removeEventListener('touchend', handleTouchEnd);
    };
  }, [ref, handlers]);
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

const exportToPNG = async (elementId: string, filename: string) => {
  try {
    const element = document.getElementById(elementId);
    if (!element) return;
    const html2canvas = (await import('html2canvas')).default;
    const canvas = await html2canvas(element, { backgroundColor: '#1a1a2e', scale: 2 });
    const link = document.createElement('a');
    link.download = `${filename}-${new Date().toISOString().split('T')[0]}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  } catch (error) {
    console.error('Export failed:', error);
  }
};

const exportToPDF = async (elementId: string, filename: string) => {
  try {
    const element = document.getElementById(elementId);
    if (!element) return;
    const html2canvas = (await import('html2canvas')).default;
    const { jsPDF } = await import('jspdf');
    const canvas = await html2canvas(element, { backgroundColor: '#1a1a2e', scale: 2 });
    const imgData = canvas.toDataURL('image/png');
    const pdf = new jsPDF({
      orientation: canvas.width > canvas.height ? 'landscape' : 'portrait',
      unit: 'px',
      format: [canvas.width, canvas.height],
    });
    pdf.addImage(imgData, 'PNG', 0, 0, canvas.width, canvas.height);
    pdf.save(`${filename}-${new Date().toISOString().split('T')[0]}.pdf`);
  } catch (error) {
    console.error('Export failed:', error);
  }
};

const generateShareableLink = (nodeId: string, tab: string) => {
  const url = new URL(window.location.href);
  url.searchParams.set('tab', tab);
  url.searchParams.set('node', nodeId);
  return url.toString();
};

const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};

// ============================================================================
// COMPONENTS
// ============================================================================

// Keyboard Shortcuts Modal
function ShortcutsModal({ isOpen, onClose, theme }: { isOpen: boolean; onClose: () => void; theme: 'dark' | 'light' }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center" onClick={onClose}>
      <div
        className={`p-6 rounded-lg max-w-md w-full mx-4 ${theme === 'dark' ? 'bg-gray-800' : 'bg-white'}`}
        onClick={e => e.stopPropagation()}
      >
        <h3 className={`text-xl font-bold mb-4 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
          Keyboard Shortcuts
        </h3>
        <div className="space-y-2">
          {KEYBOARD_SHORTCUTS.map(s => (
            <div key={s.key} className="flex justify-between">
              <kbd className={`px-2 py-1 rounded text-sm font-mono ${theme === 'dark' ? 'bg-gray-700 text-gray-300' : 'bg-gray-200 text-gray-700'}`}>
                {s.key}
              </kbd>
              <span className={theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}>{s.description}</span>
            </div>
          ))}
        </div>
        <button
          onClick={onClose}
          className="mt-4 w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Close
        </button>
      </div>
    </div>
  );
}

// Mini-Map Component
function MiniMap({ nodes, viewport, onNavigate, theme }: {
  nodes: { id: string; x: number; y: number; type: NodeType }[];
  viewport: { x: number; y: number; width: number; height: number };
  onNavigate: (x: number, y: number) => void;
  theme: 'dark' | 'light';
}) {
  const colors = NODE_COLORS[theme];
  const mapWidth = 150;
  const mapHeight = 100;
  const scale = 0.1;

  return (
    <div
      className={`absolute bottom-4 right-4 rounded-lg border overflow-hidden cursor-pointer ${
        theme === 'dark' ? 'bg-gray-800/80 border-gray-600' : 'bg-white/80 border-gray-300'
      }`}
      style={{ width: mapWidth, height: mapHeight }}
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const x = (e.clientX - rect.left) / scale;
        const y = (e.clientY - rect.top) / scale;
        onNavigate(x, y);
      }}
    >
      {/* Viewport indicator */}
      <div
        className="absolute border-2 border-blue-500 bg-blue-500/20"
        style={{
          left: viewport.x * scale,
          top: viewport.y * scale,
          width: viewport.width * scale,
          height: viewport.height * scale,
        }}
      />
      {/* Nodes */}
      {nodes.map(node => (
        <div
          key={node.id}
          className={`absolute w-2 h-2 rounded-full`}
          style={{
            left: node.x * scale,
            top: node.y * scale,
            backgroundColor: colors[node.type].hex,
          }}
        />
      ))}
    </div>
  );
}

// Sparkline Component for Metrics
function Sparkline({ data, color = '#3b82f6', width = 60, height = 20 }: {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (data.length < 2) return null;

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  const points = data.map((value, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((value - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={width} height={height} className="inline-block">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
      />
    </svg>
  );
}

// Favorites Sidebar
function FavoritesSidebar({ favorites, onRemove, onSelect, isOpen, onClose, theme }: {
  favorites: string[];
  onRemove: (id: string) => void;
  onSelect: (id: string) => void;
  isOpen: boolean;
  onClose: () => void;
  theme: 'dark' | 'light';
}) {
  if (!isOpen) return null;

  const favoriteProcesses = ALL_PROCESSES.filter(p => favorites.includes(p.id));

  return (
    <div className={`fixed left-0 top-24 bottom-0 w-full sm:w-64 z-40 border-r transform transition-transform ${
      theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-300'
    }`}>
      <div className="p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className={`font-bold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
            ⭐ Favorites ({favorites.length})
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">✕</button>
        </div>
        {favoriteProcesses.length === 0 ? (
          <p className={`text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
            No favorites yet. Click ⭐ on any process to add it here.
          </p>
        ) : (
          <div className="space-y-2">
            {favoriteProcesses.map(p => (
              <div
                key={p.id}
                className={`flex items-center justify-between p-2 rounded cursor-pointer ${
                  theme === 'dark' ? 'hover:bg-gray-700' : 'hover:bg-gray-100'
                }`}
                onClick={() => onSelect(p.id)}
              >
                <span className={theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}>{p.title}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); onRemove(p.id); }}
                  className="text-red-400 hover:text-red-300"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Status Filter Bar
function StatusFilterBar({ filter, onFilterChange, theme }: {
  filter: StatusFilter;
  onFilterChange: (filter: StatusFilter) => void;
  theme: 'dark' | 'light';
}) {
  const filters: { value: StatusFilter; label: string; icon: string }[] = [
    { value: 'all', label: 'All', icon: '📋' },
    { value: 'active', label: 'Active', icon: '🟢' },
    { value: 'inactive', label: 'Inactive', icon: '⚪' },
    { value: 'error', label: 'Errors', icon: '🔴' },
    { value: 'ai', label: 'AI/ML', icon: '🤖' },
    { value: 'bots', label: 'Bots', icon: '🦾' },
  ];

  return (
    <div className="flex gap-2 mb-4 flex-wrap">
      {filters.map(f => (
        <button
          key={f.value}
          onClick={() => onFilterChange(f.value)}
          className={`px-3 py-1 rounded-full text-sm flex items-center gap-1 transition-colors ${
            filter === f.value
              ? 'bg-blue-600 text-white'
              : theme === 'dark'
                ? 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          <span>{f.icon}</span>
          <span>{f.label}</span>
        </button>
      ))}
    </div>
  );
}

// Layout Selector
function LayoutSelector({ layout, onLayoutChange, theme }: {
  layout: LayoutType;
  onLayoutChange: (layout: LayoutType) => void;
  theme: 'dark' | 'light';
}) {
  const layouts: { value: LayoutType; label: string; icon: string }[] = [
    { value: 'horizontal', label: 'Horizontal', icon: '➡️' },
    { value: 'vertical', label: 'Vertical', icon: '⬇️' },
    { value: 'tree', label: 'Tree', icon: '🌳' },
    { value: 'radial', label: 'Radial', icon: '🔄' },
  ];

  return (
    <div className="flex gap-1">
      {layouts.map(l => (
        <button
          key={l.value}
          onClick={() => onLayoutChange(l.value)}
          title={l.label}
          className={`p-2 rounded ${
            layout === l.value
              ? 'bg-blue-600 text-white'
              : theme === 'dark'
                ? 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
          }`}
        >
          {l.icon}
        </button>
      ))}
    </div>
  );
}

// Process Drill-Down Panel
function DrillDownPanel({ processId, onClose, theme }: {
  processId: string;
  onClose: () => void;
  theme: 'dark' | 'light';
}) {
  const process = ALL_PROCESSES.find(p => p.id === processId);
  if (!process) return null;

  // Mock data
  const mockLogs = [
    { time: '10:32:15', level: 'INFO', message: 'Process started' },
    { time: '10:32:16', level: 'DEBUG', message: 'Fetching data...' },
    { time: '10:32:17', level: 'INFO', message: 'Process completed in 234ms' },
  ];

  const mockMetrics = {
    avgDuration: 234,
    successRate: 98.5,
    executionCount: 1523,
    lastError: 'Timeout at 10:15:32 (2 hours ago)',
  };

  return (
    <div className={`fixed right-0 top-24 bottom-0 w-full sm:w-96 z-40 border-l overflow-y-auto ${
      theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-300'
    }`}>
      <div className="p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className={`font-bold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
            {process.title}
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">✕</button>
        </div>

        {/* Source Code Preview */}
        <div className="mb-4">
          <h4 className={`text-sm font-semibold mb-2 ${theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}`}>
            Source File
          </h4>
          <div className={`p-2 rounded font-mono text-xs ${theme === 'dark' ? 'bg-gray-900 text-green-400' : 'bg-gray-100 text-gray-800'}`}>
            backend/{process.category}/{process.id}.py
          </div>
        </div>

        {/* Metrics */}
        <div className="mb-4">
          <h4 className={`text-sm font-semibold mb-2 ${theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}`}>
            Performance Metrics
          </h4>
          <div className="grid grid-cols-2 gap-2">
            <div className={`p-2 rounded ${theme === 'dark' ? 'bg-gray-700' : 'bg-gray-100'}`}>
              <div className={`text-xs ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>Avg Duration</div>
              <div className={`font-bold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{mockMetrics.avgDuration}ms</div>
            </div>
            <div className={`p-2 rounded ${theme === 'dark' ? 'bg-gray-700' : 'bg-gray-100'}`}>
              <div className={`text-xs ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>Success Rate</div>
              <div className="font-bold text-green-500">{mockMetrics.successRate}%</div>
            </div>
            <div className={`p-2 rounded ${theme === 'dark' ? 'bg-gray-700' : 'bg-gray-100'}`}>
              <div className={`text-xs ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>Executions</div>
              <div className={`font-bold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{mockMetrics.executionCount}</div>
            </div>
            <div className={`p-2 rounded ${theme === 'dark' ? 'bg-gray-700' : 'bg-gray-100'}`}>
              <div className={`text-xs ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>Trend</div>
              <Sparkline data={[45, 52, 48, 61, 55, 67, 72, 68, 75, 82]} color="#22c55e" />
            </div>
          </div>
        </div>

        {/* Recent Logs */}
        <div className="mb-4">
          <h4 className={`text-sm font-semibold mb-2 ${theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}`}>
            Recent Logs
          </h4>
          <div className={`rounded overflow-hidden ${theme === 'dark' ? 'bg-gray-900' : 'bg-gray-100'}`}>
            {mockLogs.map((log, i) => (
              <div key={i} className={`px-2 py-1 text-xs font-mono flex gap-2 ${
                i % 2 === 0 ? (theme === 'dark' ? 'bg-gray-900' : 'bg-gray-100') : (theme === 'dark' ? 'bg-gray-800' : 'bg-gray-50')
              }`}>
                <span className="text-gray-500">{log.time}</span>
                <span className={log.level === 'ERROR' ? 'text-red-400' : log.level === 'DEBUG' ? 'text-gray-500' : 'text-blue-400'}>
                  [{log.level}]
                </span>
                <span className={theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}>{log.message}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Last Error */}
        {mockMetrics.lastError && (
          <div className="mb-4">
            <h4 className="text-sm font-semibold mb-2 text-red-400">Last Error</h4>
            <div className="p-2 rounded bg-red-900/20 border border-red-800 text-red-400 text-sm">
              {mockMetrics.lastError}
            </div>
          </div>
        )}

        {/* GitHub Link */}
        <a
          href={`https://github.com/lemollon/AlphaGEX/blob/main/backend/${process.category}/${process.id}.py`}
          target="_blank"
          rel="noopener noreferrer"
          className="block w-full py-2 text-center bg-gray-700 text-white rounded hover:bg-gray-600"
        >
          View on GitHub →
        </a>
      </div>
    </div>
  );
}

// AI Analysis Component
function AIAnalysisPanel({ processId, onClose, theme }: {
  processId: string;
  onClose: () => void;
  theme: 'dark' | 'light';
}) {
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const process = ALL_PROCESSES.find(p => p.id === processId);

  const runAnalysis = async () => {
    setLoading(true);
    // Simulate AI analysis
    await new Promise(r => setTimeout(r, 2000));
    setAnalysis(`
## Analysis of ${process?.title}

### Summary
This process is part of the ${process?.category} layer and handles ${process?.keywords.join(', ')}.

### Optimization Suggestions
1. Consider adding caching for frequently accessed data
2. Implement retry logic with exponential backoff
3. Add more granular logging for debugging

### Potential Bottlenecks
- Database queries could be batched
- Consider async processing for non-critical paths

### Risk Assessment
- Low risk of data loss
- Medium risk of timeout under high load
    `.trim());
    setLoading(false);
  };

  if (!process) return null;

  return (
    <div className={`fixed inset-0 bg-black/50 z-50 flex items-center justify-center`} onClick={onClose}>
      <div
        className={`max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto rounded-lg ${
          theme === 'dark' ? 'bg-gray-800' : 'bg-white'
        }`}
        onClick={e => e.stopPropagation()}
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className={`text-xl font-bold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
              🔮 AI Analysis: {process.title}
            </h3>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-300">✕</button>
          </div>

          {!analysis && !loading && (
            <div className="text-center py-8">
              <p className={`mb-4 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
                Run Claude AI analysis on this process to get optimization suggestions and insights.
              </p>
              <button
                onClick={runAnalysis}
                className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
              >
                🚀 Run AI Analysis
              </button>
            </div>
          )}

          {loading && (
            <div className="text-center py-8">
              <div className="animate-spin w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full mx-auto mb-4" />
              <p className={theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}>
                Analyzing with Claude AI...
              </p>
            </div>
          )}

          {analysis && (
            <div className={`prose max-w-none ${theme === 'dark' ? 'prose-invert' : ''}`}>
              <pre className={`whitespace-pre-wrap text-sm ${theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}`}>
                {analysis}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Comments Section
function CommentsSection({ nodeId, theme }: { nodeId: string; theme: 'dark' | 'light' }) {
  const [comments, setComments] = useLocalStorage<Comment[]>(`comments-${nodeId}`, []);
  const [newComment, setNewComment] = useState('');

  const addComment = () => {
    if (!newComment.trim()) return;
    const comment: Comment = {
      id: Date.now().toString(),
      nodeId,
      text: newComment,
      author: 'You',
      timestamp: new Date().toISOString(),
    };
    setComments([...comments, comment]);
    setNewComment('');
  };

  return (
    <div className={`mt-4 p-3 rounded-lg ${theme === 'dark' ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
      <h4 className={`text-sm font-semibold mb-2 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
        💬 Comments ({comments.length})
      </h4>

      <div className="space-y-2 mb-3 max-h-32 overflow-y-auto">
        {comments.map(c => (
          <div key={c.id} className={`text-sm p-2 rounded ${theme === 'dark' ? 'bg-gray-800' : 'bg-white'}`}>
            <div className="flex justify-between">
              <span className={`font-medium ${theme === 'dark' ? 'text-blue-400' : 'text-blue-600'}`}>{c.author}</span>
              <span className="text-gray-500 text-xs">{new Date(c.timestamp).toLocaleTimeString()}</span>
            </div>
            <p className={theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}>{c.text}</p>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment..."
          className={`flex-1 px-3 py-1 rounded text-sm ${
            theme === 'dark' ? 'bg-gray-800 text-white border-gray-600' : 'bg-white text-gray-900 border-gray-300'
          } border`}
          onKeyDown={(e) => e.key === 'Enter' && addComment()}
        />
        <button
          onClick={addComment}
          className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
        >
          Send
        </button>
      </div>
    </div>
  );
}

// Enhanced FlowChart with all new features
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
  theme = 'dark',
  layout = 'horizontal' as LayoutType,
  onFavorite,
  favorites = [],
  statusFilter = 'all' as StatusFilter,
}: {
  id: string;
  title: string;
  nodes: { id: string; label: string; type: NodeType; dependencies?: string[]; status?: string }[];
  description?: string;
  codeRef?: string;
  searchQuery?: string;
  onNodeClick?: (nodeId: string) => void;
  selectedNode?: string | null;
  showAnimations?: boolean;
  theme?: 'dark' | 'light';
  layout?: LayoutType;
  onFavorite?: (id: string) => void;
  favorites?: string[];
  statusFilter?: StatusFilter;
}) {
  const [expanded, setExpanded] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const colors = NODE_COLORS[theme];

  // Touch gestures
  useTouchGestures(containerRef, {
    onPinch: (scale) => setZoom(z => Math.min(Math.max(z * scale, 0.5), 3)),
    onPan: (dx, dy) => setPan(p => ({ x: p.x + dx, y: p.y + dy })),
  });

  const matchesSearch = searchQuery === '' ||
    title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    nodes.some(n => n.label.toLowerCase().includes(searchQuery.toLowerCase()));

  if (!matchesSearch) return null;

  const highlightedNodes = useMemo(() => {
    if (!selectedNode) return new Set<string>();
    const highlighted = new Set<string>([selectedNode]);
    nodes.forEach(node => {
      if (node.dependencies?.includes(selectedNode)) highlighted.add(node.id);
    });
    const selected = nodes.find(n => n.id === selectedNode);
    selected?.dependencies?.forEach(dep => highlighted.add(dep));
    return highlighted;
  }, [selectedNode, nodes]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  };

  const handleMouseUp = () => setIsDragging(false);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    setZoom(z => Math.min(Math.max(z * (e.deltaY > 0 ? 0.9 : 1.1), 0.5), 3));
  };

  const getLayoutStyle = () => {
    switch (layout) {
      case 'vertical':
        return 'flex-col';
      case 'tree':
        return 'flex-wrap justify-center';
      case 'radial':
        return 'flex-wrap justify-center items-center';
      default:
        return 'flex-wrap';
    }
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
          {onFavorite && (
            <button
              onClick={(e) => { e.stopPropagation(); onFavorite(id); }}
              className={`text-xl ${favorites.includes(id) ? 'text-yellow-400' : 'text-gray-500 hover:text-yellow-400'}`}
            >
              {favorites.includes(id) ? '⭐' : '☆'}
            </button>
          )}
        </div>
        {codeRef && <span className="text-xs text-gray-500 font-mono">{codeRef}</span>}
      </div>

      {expanded && (
        <div className="p-4 pt-0">
          {description && <p className={`text-sm mb-4 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>{description}</p>}

          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <button onClick={() => setZoom(z => Math.min(z * 1.2, 3))} className="px-2 py-1 bg-gray-700 text-white rounded text-sm">🔍+</button>
            <button onClick={() => setZoom(z => Math.max(z * 0.8, 0.5))} className="px-2 py-1 bg-gray-700 text-white rounded text-sm">🔍-</button>
            <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} className="px-2 py-1 bg-gray-700 text-white rounded text-sm">Reset</button>
            <span className="text-gray-500 text-sm">{Math.round(zoom * 100)}%</span>
          </div>

          <div
            ref={containerRef}
            className="overflow-hidden rounded-lg border border-gray-600 cursor-grab active:cursor-grabbing relative"
            style={{ minHeight: '120px' }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onWheel={handleWheel}
          >
            <div
              className={`flex gap-3 items-center justify-center p-4 transition-transform ${getLayoutStyle()}`}
              style={{ transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`, transformOrigin: 'center center' }}
            >
              {nodes.map((node, idx) => {
                const isHighlighted = highlightedNodes.has(node.id);
                const isHovered = hoveredNode === node.id;
                const nodeColors = colors[node.type];
                const nodeStatus = node.status || (Math.random() > 0.7 ? 'active' : Math.random() > 0.1 ? 'inactive' : 'error');

                // Apply status filter
                if (statusFilter !== 'all') {
                  if (statusFilter === 'active' && nodeStatus !== 'active') return null;
                  if (statusFilter === 'inactive' && nodeStatus !== 'inactive') return null;
                  if (statusFilter === 'error' && nodeStatus !== 'error') return null;
                  if (statusFilter === 'ai' && node.type !== 'ai') return null;
                  if (statusFilter === 'bots' && node.type !== 'bot') return null;
                }

                return (
                  <div key={node.id} className={`flex items-center gap-2 ${layout === 'vertical' ? 'flex-col' : ''}`}>
                    <div
                      className={`
                        px-4 py-2 rounded-lg border-2 font-medium text-sm cursor-pointer transition-all duration-200 relative
                        ${nodeColors.bg} ${nodeColors.border} ${nodeColors.text}
                        ${isHighlighted ? `shadow-lg ${nodeColors.glow}` : ''}
                        ${isHovered ? 'scale-110' : ''}
                        ${selectedNode === node.id ? 'ring-2 ring-white ring-offset-2 ring-offset-gray-800' : ''}
                      `}
                      onClick={(e) => { e.stopPropagation(); onNodeClick?.(node.id); }}
                      onMouseEnter={() => setHoveredNode(node.id)}
                      onMouseLeave={() => setHoveredNode(null)}
                    >
                      {node.label}
                      <div className={`absolute -top-1 -right-1 w-2 h-2 rounded-full ${
                        nodeStatus === 'active' ? 'bg-green-500 animate-pulse' :
                        nodeStatus === 'error' ? 'bg-red-500 animate-pulse' : 'bg-gray-500'
                      }`} />
                    </div>
                    {idx < nodes.length - 1 && (
                      <span className={`text-gray-500 text-xl ${layout === 'vertical' ? 'rotate-90' : ''}`}>
                        {showAnimations ? (
                          <span className="inline-block animate-pulse text-cyan-400">→</span>
                        ) : '→'}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {selectedNode && (
            <CommentsSection nodeId={selectedNode} theme={theme} />
          )}
        </div>
      )}
    </div>
  );
}

// Legend with glow effects
function Legend({ theme }: { theme: 'dark' | 'light' }) {
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

// Metrics component with sparklines
function ProcessMetricsDisplay({ metrics, theme }: {
  metrics: { label: string; value: string | number; trend?: 'up' | 'down' | 'neutral'; live?: boolean; sparkData?: number[] }[];
  theme: 'dark' | 'light';
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {metrics.map((m, i) => (
        <div key={i} className={`rounded-lg border p-4 ${theme === 'dark' ? 'bg-gray-800/50 border-gray-700' : 'bg-white border-gray-300'}`}>
          <div className="flex items-center justify-between">
            <p className={`text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>{m.label}</p>
            {m.live && <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />}
          </div>
          <div className="flex items-center justify-between">
            <p className={`text-2xl font-bold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{m.value}</p>
            {m.sparkData && <Sparkline data={m.sparkData} color={m.trend === 'up' ? '#22c55e' : m.trend === 'down' ? '#ef4444' : '#6b7280'} />}
          </div>
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

// ============================================================================
// MAIN PAGE COMPONENT
// ============================================================================

export default function SystemProcessesPage() {
  // State
  const [activeTab, setActiveTab] = useState('overview');
  const [searchQuery, setSearchQuery] = useState('');
  const [theme, setTheme] = useLocalStorage<'dark' | 'light'>('system-theme', 'dark');
  const [showAnimations, setShowAnimations] = useLocalStorage('show-animations', false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [favorites, setFavorites] = useLocalStorage<string[]>('process-favorites', []);
  const [layout, setLayout] = useLocalStorage<LayoutType>('diagram-layout', 'horizontal');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [showFavorites, setShowFavorites] = useState(false);
  const [drillDownProcess, setDrillDownProcess] = useState<string | null>(null);
  const [aiAnalysisProcess, setAiAnalysisProcess] = useState<string | null>(null);
  const [botStatuses, setBotStatuses] = useState<Record<string, BotStatus>>({});
  const [processStatuses, setProcessStatuses] = useState<Record<string, string>>({});

  const searchRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // WebSocket for real-time updates
  const { isConnected, lastMessage } = useWebSocket('ws://localhost:8000/ws/system');

  // Update statuses from WebSocket
  useEffect(() => {
    if (lastMessage?.type === 'bot_status') {
      setBotStatuses((prev: Record<string, BotStatus>) => ({ ...prev, [lastMessage.bot]: lastMessage.status }));
    }
    if (lastMessage?.type === 'process_status') {
      setProcessStatuses((prev: Record<string, string>) => ({ ...prev, [lastMessage.process]: lastMessage.status }));
    }
  }, [lastMessage]);

  // Fetch initial bot statuses
  useEffect(() => {
    const fetchStatuses = async () => {
      try {
        const res = await fetch('/api/bots/status');
        if (res.ok) setBotStatuses(await res.json());
      } catch {}
    };
    fetchStatuses();
    const interval = setInterval(fetchStatuses, 30000);
    return () => clearInterval(interval);
  }, []);

  // Simulate process statuses
  useEffect(() => {
    const update = () => {
      const statuses: Record<string, string> = {};
      ALL_PROCESSES.forEach(p => {
        const r = Math.random();
        statuses[p.id] = r > 0.7 ? 'active' : r > 0.1 ? 'inactive' : 'error';
      });
      setProcessStatuses(statuses);
    };
    update();
    const interval = setInterval(update, 10000);
    return () => clearInterval(interval);
  }, []);

  // Keyboard shortcuts
  const keyboardHandlers = useMemo(() => ({
    '/': () => searchRef.current?.focus(),
    'escape': () => { setSelectedNode(null); searchRef.current?.blur(); },
    '1': () => setActiveTab('overview'),
    '2': () => setActiveTab('data'),
    '3': () => setActiveTab('decisions'),
    '4': () => setActiveTab('execution'),
    '5': () => setActiveTab('bots'),
    '6': () => setActiveTab('ai'),
    '7': () => setActiveTab('analysis'),
    '8': () => setActiveTab('strategy'),
    '9': () => setActiveTab('operations'),
    '0': () => setActiveTab('timeline'),
    't': () => setTheme(theme === 'dark' ? 'light' : 'dark'),
    'a': () => setShowAnimations(!showAnimations),
    'f': () => setShowFavorites(!showFavorites),
    '?': () => setShowShortcuts(true),
    'r': () => { /* Reset zoom handled in FlowChart */ },
  }), [theme, showAnimations, showFavorites]);

  useKeyboardShortcuts(keyboardHandlers);

  // URL params for sharing
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    const node = params.get('node');
    if (tab) setActiveTab(tab);
    if (node) setSelectedNode(node);
  }, []);

  // Handlers
  const handleNodeClick = useCallback((nodeId: string) => {
    setSelectedNode((prev: string | null) => prev === nodeId ? null : nodeId);
  }, []);

  const handleFavorite = useCallback((id: string) => {
    setFavorites(favorites.includes(id) ? favorites.filter(f => f !== id) : [...favorites, id]);
  }, [favorites, setFavorites]);

  const handleShare = useCallback(async () => {
    if (selectedNode) {
      const link = generateShareableLink(selectedNode, activeTab);
      const success = await copyToClipboard(link);
      if (success) alert('Link copied to clipboard!');
    }
  }, [selectedNode, activeTab]);

  // Filtered processes
  const filteredProcesses = useMemo(() => {
    if (!searchQuery) return ALL_PROCESSES;
    const q = searchQuery.toLowerCase();
    return ALL_PROCESSES.filter(p =>
      p.title.toLowerCase().includes(q) ||
      p.keywords.some(k => k.includes(q))
    );
  }, [searchQuery]);

  // Bot data
  const bots = useMemo(() => [
    { name: 'ARES', icon: '⚔️', description: '0DTE Iron Condor', status: botStatuses['ares']?.status || 'stopped', pnl: botStatuses['ares']?.pnlToday || 0 },
    { name: 'ATHENA', icon: '🦉', description: 'Directional Spreads', status: botStatuses['athena']?.status || 'stopped', pnl: botStatuses['athena']?.pnlToday || 0 },
    { name: 'APOLLO', icon: '☀️', description: 'AI Scanner', status: botStatuses['apollo']?.status || 'stopped', pnl: 0 },
    { name: 'ARGUS', icon: '👁️', description: 'Gamma Monitor', status: botStatuses['argus']?.status || 'stopped', pnl: 0 },
    { name: 'ORACLE', icon: '🔮', description: 'ML Predictions', status: botStatuses['oracle']?.status || 'stopped', pnl: 0 },
    { name: 'PROMETHEUS', icon: '🔥', description: 'ML Training', status: botStatuses['prometheus']?.status || 'stopped', pnl: 0 },
    { name: 'PHOENIX', icon: '🦅', description: 'Recovery Bot', status: botStatuses['phoenix']?.status || 'stopped', pnl: 0 },
    { name: 'HERMES', icon: '📨', description: 'Data Flow', status: botStatuses['hermes']?.status || 'stopped', pnl: 0 },
    { name: 'ATLAS', icon: '🗺️', description: 'Portfolio Manager', status: botStatuses['atlas']?.status || 'stopped', pnl: 0 },
    { name: 'SOLOMON', icon: '📖', description: 'Feedback Loop Intelligence', status: botStatuses['solomon']?.status || 'stopped', pnl: 0 },
  ], [botStatuses]);

  return (
    <div className={`min-h-screen ${theme === 'dark' ? 'bg-gray-900' : 'bg-gray-100'}`}>
      <Navigation />

      {/* Modals and Sidebars */}
      <ShortcutsModal isOpen={showShortcuts} onClose={() => setShowShortcuts(false)} theme={theme} />
      <FavoritesSidebar
        favorites={favorites}
        onRemove={(id) => setFavorites(favorites.filter(f => f !== id))}
        onSelect={(id) => { setSelectedNode(id); setShowFavorites(false); }}
        isOpen={showFavorites}
        onClose={() => setShowFavorites(false)}
        theme={theme}
      />
      {drillDownProcess && (
        <DrillDownPanel processId={drillDownProcess} onClose={() => setDrillDownProcess(null)} theme={theme} />
      )}
      {aiAnalysisProcess && (
        <AIAnalysisPanel processId={aiAnalysisProcess} onClose={() => setAiAnalysisProcess(null)} theme={theme} />
      )}

      <main className={`max-w-7xl mx-auto px-4 pt-24 pb-8 transition-all ${showFavorites ? 'sm:ml-64' : ''} ${drillDownProcess ? 'sm:mr-96' : ''}`}>
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <h1 className={`text-3xl font-bold mb-2 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>
                System Processes & Flows
              </h1>
              <div className="flex items-center gap-2">
                <p className={theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}>
                  Complete visualization of all AlphaGEX processes
                </p>
                {isConnected && (
                  <span className="flex items-center gap-1 text-green-500 text-sm">
                    <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    Live
                  </span>
                )}
              </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-2 flex-wrap">
              <LayoutSelector layout={layout} onLayoutChange={setLayout} theme={theme} />
              <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} className={`px-3 py-2 rounded-lg text-sm ${theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white text-gray-900 border'}`}>
                {theme === 'dark' ? '☀️' : '🌙'}
              </button>
              <button onClick={() => setShowAnimations(!showAnimations)} className={`px-3 py-2 rounded-lg text-sm ${showAnimations ? 'bg-cyan-600 text-white' : theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white text-gray-900 border'}`}>
                {showAnimations ? '⚡' : '⏸️'}
              </button>
              <button onClick={() => setShowFavorites(!showFavorites)} className={`px-3 py-2 rounded-lg text-sm ${showFavorites ? 'bg-yellow-600 text-white' : theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white text-gray-900 border'}`}>
                ⭐ {favorites.length}
              </button>
              <button onClick={() => setShowShortcuts(true)} className={`px-3 py-2 rounded-lg text-sm ${theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white text-gray-900 border'}`}>
                ⌨️
              </button>
              {selectedNode && (
                <>
                  <button onClick={handleShare} className="px-3 py-2 rounded-lg text-sm bg-blue-600 text-white">🔗 Share</button>
                  <button onClick={() => setDrillDownProcess(selectedNode)} className="px-3 py-2 rounded-lg text-sm bg-purple-600 text-white">🔍 Drill Down</button>
                  <button onClick={() => setAiAnalysisProcess(selectedNode)} className="px-3 py-2 rounded-lg text-sm bg-green-600 text-white">🤖 AI Analyze</button>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="mb-4">
          <div className="relative">
            <input
              ref={searchRef}
              type="text"
              placeholder="Search processes... (Press / to focus)"
              className={`w-full px-4 py-3 rounded-lg ${theme === 'dark' ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300 text-gray-900'} border focus:ring-2 focus:ring-blue-500`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <span className={`absolute right-3 top-1/2 -translate-y-1/2 text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
                {filteredProcesses.length} results
              </span>
            )}
          </div>
        </div>

        {/* Status Filter */}
        <StatusFilterBar filter={statusFilter} onFilterChange={setStatusFilter} theme={theme} />

        {/* Tabs */}
        <div className={`flex flex-wrap gap-2 mb-6 border-b pb-4 ${theme === 'dark' ? 'border-gray-700' : 'border-gray-300'}`}>
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-colors ${
                activeTab === tab.id ? 'bg-blue-600 text-white' : theme === 'dark' ? 'bg-gray-800 text-gray-400 hover:bg-gray-700' : 'bg-white text-gray-600 hover:bg-gray-100 border'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
              {tab.shortcut && <kbd className="text-xs opacity-50">{tab.shortcut}</kbd>}
            </button>
          ))}
        </div>

        {/* Content */}
        <div id="content-area" ref={contentRef} className="min-h-[600px]">
          {activeTab === 'overview' && (
            <div>
              <h2 className={`text-2xl font-bold mb-4 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>AlphaGEX System Overview</h2>

              <ProcessMetricsDisplay
                theme={theme}
                metrics={[
                  { label: 'Active Processes', value: Object.values(processStatuses).filter(s => s === 'active').length, trend: 'up', live: true, sparkData: [12, 15, 14, 18, 22, 19, 24, 28, 25, 30] },
                  { label: 'Bots Running', value: bots.filter(b => b.status === 'running').length, trend: 'neutral', live: true, sparkData: [3, 3, 4, 3, 5, 4, 4, 5, 5, 4] },
                  { label: 'Errors', value: Object.values(processStatuses).filter(s => s === 'error').length, trend: 'down', sparkData: [5, 4, 6, 3, 2, 4, 3, 2, 1, 2] },
                  { label: 'Uptime', value: '99.9%', trend: 'up', sparkData: [98, 99, 99, 100, 99, 100, 100, 99, 100, 100] },
                ]}
              />

              <Legend theme={theme} />

              <FlowChart
                id="master-flow"
                title="Master System Flow"
                description="High-level overview of data flow through AlphaGEX"
                theme={theme}
                layout={layout}
                showAnimations={showAnimations}
                selectedNode={selectedNode}
                onNodeClick={handleNodeClick}
                onFavorite={handleFavorite}
                favorites={favorites}
                statusFilter={statusFilter}
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

              {/* Category cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
                {TABS.slice(1, -1).map(tab => (
                  <div
                    key={tab.id}
                    className={`rounded-lg border p-4 cursor-pointer transition-all hover:scale-105 ${theme === 'dark' ? 'bg-gray-800/50 border-gray-700 hover:border-blue-500' : 'bg-white border-gray-300 hover:border-blue-500'}`}
                    onClick={() => setActiveTab(tab.id)}
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-2xl">{tab.icon}</span>
                      <h3 className={`font-semibold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{tab.label}</h3>
                    </div>
                    <p className={`text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
                      Explore {tab.label.toLowerCase()} processes
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'bots' && (
            <div>
              <h2 className={`text-2xl font-bold mb-4 ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>Autonomous Bots</h2>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                {bots.map(bot => (
                  <div key={bot.name} className={`rounded-lg border p-4 ${theme === 'dark' ? 'bg-gray-800/50 border-gray-700' : 'bg-white border-gray-300'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl">{bot.icon}</span>
                        <div>
                          <h4 className={`font-semibold ${theme === 'dark' ? 'text-white' : 'text-gray-900'}`}>{bot.name}</h4>
                          <p className={`text-xs ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>{bot.description}</p>
                        </div>
                      </div>
                      <div className={`w-3 h-3 rounded-full animate-pulse ${bot.status === 'running' ? 'bg-green-500' : bot.status === 'error' ? 'bg-red-500' : 'bg-gray-500'}`} />
                    </div>
                    {bot.pnl !== 0 && (
                      <div className={`text-sm ${bot.pnl > 0 ? 'text-green-500' : 'text-red-500'}`}>
                        P&L Today: {bot.pnl > 0 ? '+' : ''}{bot.pnl.toFixed(2)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab !== 'overview' && activeTab !== 'bots' && (
            <div className={`text-center py-12 ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
              <p className="text-xl">Tab: {activeTab}</p>
              <p className="text-sm mt-2">Content for this tab would be displayed here with all diagrams and filters applied.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={`mt-8 pt-8 border-t ${theme === 'dark' ? 'border-gray-700' : 'border-gray-300'}`}>
          <div className="flex flex-wrap justify-between items-center gap-4">
            <div className={`text-sm ${theme === 'dark' ? 'text-gray-500' : 'text-gray-400'}`}>
              Last updated: {new Date().toLocaleString()}
              {selectedNode && <span className="ml-4">Selected: <span className="text-blue-400">{selectedNode}</span></span>}
            </div>
            <div className="flex gap-2">
              <button onClick={() => exportToPDF('content-area', 'alphagex-system')} className={`px-4 py-2 rounded-lg text-sm ${theme === 'dark' ? 'bg-gray-800 text-gray-300 hover:bg-gray-700' : 'bg-white text-gray-600 hover:bg-gray-100 border'}`}>
                📄 Export PDF
              </button>
              <button onClick={() => exportToPNG('content-area', 'alphagex-system')} className={`px-4 py-2 rounded-lg text-sm ${theme === 'dark' ? 'bg-gray-800 text-gray-300 hover:bg-gray-700' : 'bg-white text-gray-600 hover:bg-gray-100 border'}`}>
                🖼️ Export PNG
              </button>
            </div>
          </div>
        </div>
      </main>

      <style jsx global>{`
        @keyframes flow {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
        .animate-flow { animation: flow 1.5s linear infinite; }
      `}</style>
    </div>
  );
}
