export default function PortfolioSummary({ summary }) {
  if (!summary) return null;

  const netPremium = summary.net_premium ?? summary.total_credit ?? 0;
  const premiumColor = netPremium >= 0 ? 'text-sw-green' : 'text-sw-red';
  const unrealColor = summary.total_unrealized >= 0 ? 'text-sw-green' : 'text-sw-red';
  const realColor = summary.total_realized >= 0 ? 'text-sw-green' : 'text-sw-red';

  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-3 mb-5">
      <div className="sw-card px-4 py-3 text-center">
        <div className="sw-label mb-2">Slots</div>
        <div className="text-lg font-bold font-[var(--font-mono)] text-accent-bright">
          {summary.slots_used}/{summary.slots_total}
        </div>
      </div>
      <div className="sw-card px-4 py-3 text-center">
        <div className="sw-label mb-2">Net Premium</div>
        <div className={`text-lg font-bold font-[var(--font-mono)] ${premiumColor}`}>
          {netPremium >= 0 ? '+' : '-'}${Math.abs(netPremium).toFixed(2)}
        </div>
      </div>
      <div className="sw-card px-4 py-3 text-center">
        <div className="sw-label mb-2">Collateral</div>
        <div className="text-lg font-bold font-[var(--font-mono)] text-text-primary">
          ${(summary.total_collateral ?? 0).toFixed(2)}
        </div>
      </div>
      <div className="sw-card px-4 py-3 text-center">
        <div className="sw-label mb-2">Unrealized</div>
        <div className={`text-lg font-bold font-[var(--font-mono)] ${unrealColor}`}>
          {summary.total_unrealized >= 0 ? '+' : ''}${summary.total_unrealized?.toFixed(2)}
        </div>
      </div>
      <div className="sw-card px-4 py-3 text-center">
        <div className="sw-label mb-2">Realized</div>
        <div className={`text-lg font-bold font-[var(--font-mono)] ${realColor}`}>
          {summary.total_realized >= 0 ? '+' : ''}${summary.total_realized?.toFixed(2)}
        </div>
      </div>
      <div className="sw-card px-4 py-3 text-center">
        <div className="sw-label mb-2">Open</div>
        <div className="text-lg font-bold font-[var(--font-mono)] text-text-primary">{summary.open_count}</div>
      </div>
      <div className="sw-card px-4 py-3 text-center">
        <div className="sw-label mb-2">Closed</div>
        <div className="text-lg font-bold font-[var(--font-mono)] text-text-secondary">{summary.closed_count}</div>
      </div>
    </div>
  );
}
