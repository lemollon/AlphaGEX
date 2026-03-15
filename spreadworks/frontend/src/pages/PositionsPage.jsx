import { useState } from 'react';
import { Send } from 'lucide-react';
import usePositions from '../hooks/usePositions';
import PositionCard from '../components/positions/PositionCard';
import PortfolioSummary from '../components/positions/PortfolioSummary';
import ClosePositionModal from '../components/positions/ClosePositionModal';
import EmptySlot from '../components/positions/EmptySlot';

export default function PositionsPage() {
  const [filter, setFilter] = useState('open');
  const [closingPos, setClosingPos] = useState(null);
  const {
    positions, summary, loading, error,
    closePosition, deletePosition, refetch,
    postDiscordOpen, postDiscordEod,
  } = usePositions(filter);

  const emptySlots = filter === 'open' && summary
    ? Math.max(0, summary.slots_total - (summary.slots_used || 0))
    : 0;

  const handleClose = async (id, closePrice) => {
    try {
      await closePosition(id, closePrice);
      setClosingPos(null);
    } catch { /* silent */ }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this position permanently?')) return;
    try { await deletePosition(id); } catch { /* silent */ }
  };

  return (
    <div className="flex-1 px-6 py-5 overflow-y-auto font-[var(--font-ui)] text-text-primary bg-bg-base">
      <div className="flex justify-between items-center mb-4">
        <span className="text-white text-xl font-extrabold tracking-tight">Positions</span>
        <div className="flex gap-2 items-center">
          <button
            className="sw-btn-ghost !text-[11px] text-sw-purple flex items-center gap-1"
            onClick={postDiscordOpen}
            title="Post open summary to Discord"
          >
            <Send size={11} /> Post Open
          </button>
          <button
            className="sw-btn-ghost !text-[11px] text-sw-purple flex items-center gap-1"
            onClick={postDiscordEod}
            title="Post EOD summary to Discord"
          >
            <Send size={11} /> Post EOD
          </button>
          <div className="sw-toggle-group !gap-0.5">
            {['open', 'closed', 'all'].map((f) => (
              <button key={f} className={`sw-toggle-btn !px-3.5 !py-1 ${filter === f ? 'active' : ''}`} onClick={() => setFilter(f)}>
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-sw-red-dim border border-sw-red/30 rounded-lg px-4 py-2.5 text-[13px] text-sw-red font-medium mb-3.5">
          Unable to connect to database. Check that DATABASE_URL is set in Render environment variables.
        </div>
      )}
      <PortfolioSummary summary={summary} />

      {loading ? (
        <div className="text-center py-12 text-text-tertiary text-[15px] font-medium">Loading positions...</div>
      ) : positions.length === 0 && emptySlots === 0 ? (
        <div className="text-center py-12 text-text-tertiary text-[15px] font-medium">
          No open positions yet.
          <br />
          <span className="text-[13px] text-text-muted mt-2 inline-block">
            Build a spread in the Builder tab and hit Save to track it here.
          </span>
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(380px,1fr))] gap-4">
          {positions.map((pos) => (
            <PositionCard
              key={pos.id}
              position={pos}
              onClose={(p) => setClosingPos(p)}
              onDelete={handleDelete}
            />
          ))}
          {Array.from({ length: emptySlots }).map((_, i) => (
            <EmptySlot
              key={`empty-${i}`}
              number={(summary?.slots_used || 0) + i + 1}
              total={summary?.slots_total || 10}
            />
          ))}
        </div>
      )}

      {closingPos && (
        <ClosePositionModal
          position={closingPos}
          onConfirm={handleClose}
          onCancel={() => setClosingPos(null)}
        />
      )}
    </div>
  );
}
