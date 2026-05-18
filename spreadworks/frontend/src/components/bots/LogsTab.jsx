import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

export default function LogsTab({ bot }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    botApi.scanActivity(bot, 200).then(d => setRows(d.rows || [])).catch(()=>{});
  }, [bot]);
  return (
    <table className="logs-table">
      <thead><tr><th>Time</th><th>Outcome</th><th>Reason</th><th>Position</th></tr></thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.id}>
            <td>{r.scan_time}</td>
            <td>{r.outcome}</td>
            <td>{r.reason || ''}</td>
            <td>{r.position_id || ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
