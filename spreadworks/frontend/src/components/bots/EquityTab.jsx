import { useState } from 'react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { useBotEquity } from '../../hooks/useBotEquity';

export default function EquityTab({ bot }) {
  const [mode, setMode] = useState('intraday');
  const { curve } = useBotEquity(bot, mode, 15000);
  return (
    <div>
      <div className="mode-toggle">
        <button className={mode==='intraday'?'active':''} onClick={() => setMode('intraday')}>Intraday</button>
        <button className={mode==='historical'?'active':''} onClick={() => setMode('historical')}>Historical</button>
      </div>
      {curve.length < 2 ? (
        <div className="empty">No equity points yet. Bot will write one per scan cycle.</div>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={curve}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" tickFormatter={t => new Date(t).toLocaleTimeString()} />
            <YAxis dataKey="equity" domain={['dataMin - 50', 'dataMax + 50']} />
            <Tooltip />
            <Line type="monotone" dataKey="equity" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
