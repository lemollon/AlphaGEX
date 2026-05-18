import { Link } from 'react-router-dom';
import { Snowflake, Waves, Wind } from 'lucide-react';
import { useBotStatus } from '../../hooks/useBotStatus';
import { BOT_REGISTRY, STRATEGY_LABEL, BOT_THEME } from '../../lib/botRegistry';

const GLYPH_MAP = {
  snowflake: Snowflake,
  wave: Waves,
  current: Wind,
};

function relativeTime(ts) {
  if (!ts) return '—';
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function BotCard({ bot }) {
  const { data, error } = useBotStatus(bot, 5000);
  const meta = BOT_REGISTRY[bot];
  const theme = BOT_THEME[bot];
  const GlyphIcon = GLYPH_MAP[theme?.glyph] || Wind;

  if (error) {
    return (
      <div className="sw-card p-4 opacity-60">
        <span className="text-sw-red text-[13px]">Failed to load {bot}</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="sw-card p-4 animate-pulse">
        <div className="h-4 bg-bg-hover rounded w-1/3 mb-3" />
        <div className="h-3 bg-bg-hover rounded w-1/2 mb-2" />
        <div className="h-3 bg-bg-hover rounded w-2/3" />
      </div>
    );
  }

  const isEnabled = !!data.enabled;
  const equity = typeof data.equity === 'number' ? data.equity : null;
  const openPos = data.open_positions ?? 0;

  return (
    <Link
      to={`/bots/${bot}`}
      className="sw-card p-4 hover:bg-bg-card-hover block no-underline"
      style={{ borderLeft: `2px solid ${theme.accent}` }}
    >
      {/* Header row */}
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2">
          <GlyphIcon size={14} style={{ color: theme.accent }} />
          <span className="text-white font-bold text-sm tracking-tight">{meta.display}</span>
          <span className="sw-badge bg-bg-hover border border-border-subtle text-text-tertiary">
            {STRATEGY_LABEL[meta.strategy]}
          </span>
        </div>
        <span
          className={`sw-badge ${
            isEnabled
              ? 'bg-sw-green/10 text-sw-green border border-sw-green/25'
              : 'bg-bg-hover text-text-muted border border-border-subtle'
          }`}
        >
          {isEnabled ? 'ON' : 'OFF'}
        </span>
      </div>

      {/* Stat rows */}
      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between items-center py-1 border-b border-border-subtle">
          <span className="sw-label">Open Positions</span>
          <span className="sw-mono text-[13px] font-semibold text-text-primary">{openPos}</span>
        </div>
        <div className="flex justify-between items-center py-1 border-b border-border-subtle">
          <span className="sw-label">Equity</span>
          <span className={`sw-mono text-[13px] font-semibold ${equity != null && equity >= 0 ? 'sw-pnl-positive' : 'sw-pnl-negative'}`}>
            {equity != null ? `$${equity.toFixed(2)}` : '—'}
          </span>
        </div>
        <div className="flex justify-between items-center py-1">
          <span className="sw-label">Last Scan</span>
          <span className="sw-mono text-[11px] text-text-tertiary">{relativeTime(data.last_scan_at)}</span>
        </div>
      </div>
    </Link>
  );
}
