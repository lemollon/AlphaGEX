import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

export default function TradesTab({ bot }) {
  const [trades, setTrades] = useState([]);
  useEffect(() => {
    botApi.trades(bot, 100).then(d => setTrades(d.trades || [])).catch(()=>{});
  }, [bot]);
  if (trades.length === 0) return <div className="empty">No closed trades yet.</div>;
  return (
    <table className="trades-table">
      <thead><tr>
        <th>Closed</th><th>Reason</th><th>P&amp;L</th><th>Entry</th><th>Close</th><th>Contracts</th>
      </tr></thead>
      <tbody>
        {trades.map(t => (
          <tr key={t.position_id} className={Number(t.realized_pnl) >= 0 ? 'win' : 'loss'}>
            <td>{t.close_time}</td>
            <td>{t.close_reason}</td>
            <td>${Number(t.realized_pnl).toFixed(2)}</td>
            <td>{Number(t.entry_price).toFixed(2)}</td>
            <td>{Number(t.close_price).toFixed(2)}</td>
            <td>{t.contracts}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
