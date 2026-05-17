export default function PortfolioSummary({ summary }) {
  if (!summary) return null;

  const netPremium = summary.net_premium ?? summary.total_credit ?? 0;
  const premiumColor = netPremium >= 0 ? 'text-sw-green' : 'text-sw-red';
  const unrealColor = summary.total_unrealized >= 0 ? 'text-sw-green' : 'text-sw-red';
  const realColor = summary.total_realized >= 0 ? 'text-sw-green' : 'text-sw-red';

  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-2.5 mb-5">
      <div className="sw-stat-card">
        <div className="sw-label">Slots</div>
        <div className="sw-stat-value text-accent">
          {summary.slots_used}/{summary.slots_total}
        </div>
      </div>
      <div className="sw-stat-card">
        <div className="sw-label">Net Premium</div>
        <div className={`sw-stat-value ${premiumColor}`}>
          {netPremium >= 0 ? '+' : '-'}${Math.abs(netPremium).toFixed(2)}
        </div>
      </div>
      <div className="sw-stat-card">
        <div className="sw-label">Collateral</div>
        <div className="sw-stat-value">
          ${(summary.total_collateral ?? 0).toFixed(2)}
        </div>
      </div>
      <div className="sw-stat-card">
        <div className="sw-label">Unrealized</div>
        <div className={`sw-stat-value ${unrealColor}`}>
          {summary.total_unrealized >= 0 ? '+' : ''}${summary.total_unrealized?.toFixed(2)}
        </div>
      </div>
      <div className="sw-stat-card">
        <div className="sw-label">Realized</div>
        <div className={`sw-stat-value ${realColor}`}>
          {summary.total_realized >= 0 ? '+' : ''}${summary.total_realized?.toFixed(2)}
        </div>
      </div>
      <div className="sw-stat-card">
        <div className="sw-label">Open</div>
        <div className="sw-stat-value">{summary.open_count}</div>
      </div>
      <div className="sw-stat-card">
        <div className="sw-label">Closed</div>
        <div className="sw-stat-value text-text-secondary">{summary.closed_count}</div>
      </div>
    </div>
  );
}
