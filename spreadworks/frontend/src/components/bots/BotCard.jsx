import { Link } from 'react-router-dom';
import { useBotStatus } from '../../hooks/useBotStatus';
import { BOT_REGISTRY, STRATEGY_LABEL, BOT_THEME } from '../../lib/botRegistry';

export default function BotCard({ bot }) {
  const { data, error } = useBotStatus(bot, 5000);
  const meta = BOT_REGISTRY[bot];
  const theme = BOT_THEME[bot];
  if (error) return <div className="bot-card error">Failed to load {bot}</div>;
  if (!data) return <div className="bot-card loading">Loading {bot}…</div>;
  return (
    <Link to={`/bots/${bot}`} className="bot-card"
          style={{ borderLeft: `4px solid ${theme.accent}` }}>
      <div className="bot-card-header">
        <div className="bot-name">{meta.display}</div>
        <div className="bot-strategy">{STRATEGY_LABEL[meta.strategy]}</div>
      </div>
      <div className="bot-card-row">
        <div>Enabled</div>
        <div>{data.enabled ? 'Yes' : 'No'}</div>
      </div>
      <div className="bot-card-row">
        <div>Open positions</div>
        <div>{data.open_positions}</div>
      </div>
      <div className="bot-card-row">
        <div>Equity</div>
        <div>${data.equity.toFixed(2)}</div>
      </div>
      <div className="bot-card-row muted">
        <div>Last scan</div>
        <div>{data.last_scan_at || '—'}</div>
      </div>
    </Link>
  );
}
