import { useBotPositions } from '../../hooks/useBotPositions';
import { botApi } from '../../lib/botApi';

export default function PositionsTab({ bot }) {
  const { positions } = useBotPositions(bot, 5000);
  async function onClose(pid) { await botApi.forceClose(bot, pid); }
  if (positions.length === 0) return <div className="empty">No open positions.</div>;
  return (
    <table className="positions-table">
      <thead><tr>
        <th>ID</th><th>Strategy</th><th>Legs</th><th>Entry</th>
        <th>MTM Value</th><th>MTM P&amp;L</th><th>PT / SL</th><th></th>
      </tr></thead>
      <tbody>
        {positions.map(p => (
          <tr key={p.position_id}>
            <td>{p.position_id}</td>
            <td>{p.strategy}</td>
            <td>{(p.legs||[]).map(l => `${l.side[0]}${l.type[0]} ${l.strike}`).join(' / ')}</td>
            <td>{Number(p.entry_price).toFixed(2)}</td>
            <td>{p.mtm_value ? Number(p.mtm_value).toFixed(2) : '—'}</td>
            <td>{p.mtm_pnl ? `$${Number(p.mtm_pnl).toFixed(2)}` : '—'}</td>
            <td>${Number(p.pt_target_pnl).toFixed(0)} / ${Number(p.sl_target_pnl).toFixed(0)}</td>
            <td><button onClick={() => onClose(p.position_id)}>Close</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
