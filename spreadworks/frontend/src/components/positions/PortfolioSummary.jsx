export default function PortfolioSummary({ summary }) {
  if (!summary) return null;

  const unrealColor = summary.total_unrealized >= 0 ? 'text-sw-green' : 'text-sw-red';
  const realColor = summary.total_realized >= 0 ? 'text-sw-green' : 'text-sw-red';

  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-2.5 mb-4">
      <div className="sw-card text-center">
        <div className="sw-label mb-1.5">Slots</div>
        <div className="text-lg font-bold font-[var(--font-mono)] text-accent-bright">
          {summary.slots_used}/{summary.slots_total}
        </div>
      </div>
      <div className="sw-card text-center">
        <div className="sw-label mb-1.5">Total Credit</div>
        <div className="text-lg font-bold font-[var(--font-mono)] text-sw-green">+${summary.total_credit?.toFixed(2)}</div>
      </div>
      <div className="sw-card text-center">
        <div className="sw-label mb-1.5">Unrealized</div>
        <div className={`text-lg font-bold font-[var(--font-mono)] ${unrealColor}`}>
          {summary.total_unrealized >= 0 ? '+' : ''}${summary.total_unrealized?.toFixed(2)}
        </div>
      </div>
      <div className="sw-card text-center">
        <div className="sw-label mb-1.5">Realized</div>
        <div className={`text-lg font-bold font-[var(--font-mono)] ${realColor}`}>
          {summary.total_realized >= 0 ? '+' : ''}${summary.total_realized?.toFixed(2)}
        </div>
      </div>
      <div className="sw-card text-center">
        <div className="sw-label mb-1.5">Open</div>
        <div className="text-lg font-bold font-[var(--font-mono)] text-text-primary">{summary.open_count}</div>
      </div>
      <div className="sw-card text-center">
        <div className="sw-label mb-1.5">Closed</div>
        <div className="text-lg font-bold font-[var(--font-mono)] text-text-secondary">{summary.closed_count}</div>
      </div>
    </div>
  );
}
