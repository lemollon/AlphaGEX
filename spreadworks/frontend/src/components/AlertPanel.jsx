import { useState } from 'react';

import { API_URL } from '../lib/api';

export default function AlertPanel({ alerts, onRefresh }) {
  const [price, setPrice] = useState('');
  const [condition, setCondition] = useState('above');
  const [label, setLabel] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!price) return;
    setCreating(true);
    try {
      await fetch(`${API_URL}/api/spreadworks/alerts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ price: parseFloat(price), condition, label }),
      });
      setPrice('');
      setLabel('');
      if (onRefresh) onRefresh();
    } catch (err) {
      console.error('Create alert failed:', err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await fetch(`${API_URL}/api/spreadworks/alerts/${id}`, { method: 'DELETE' });
      if (onRefresh) onRefresh();
    } catch (err) {
      console.error('Delete alert failed:', err);
    }
  };

  return (
    <div className="panel alert-panel">
      <h3>Price Alerts</h3>

      <form className="alert-form" onSubmit={handleCreate}>
        <div className="alert-form-row">
          <select value={condition} onChange={(e) => setCondition(e.target.value)}>
            <option value="above">Above</option>
            <option value="below">Below</option>
          </select>
          <input
            type="number"
            step="0.01"
            placeholder="Price"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
          <input
            type="text"
            placeholder="Label (optional)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <button type="submit" disabled={creating || !price}>
            {creating ? '...' : 'Add'}
          </button>
        </div>
      </form>

      {alerts && alerts.length > 0 ? (
        <ul className="alert-list">
          {alerts.map((a) => (
            <li key={a.id} className={a.triggered ? 'triggered' : ''}>
              <span className="alert-label">{a.label || 'Alert'}</span>
              <span className="alert-detail">
                {a.condition} ${a.price}
                {a.triggered && <span className="alert-badge">TRIGGERED</span>}
              </span>
              <button className="alert-delete" onClick={() => handleDelete(a.id)}>
                &times;
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="placeholder-text">No alerts set.</p>
      )}
    </div>
  );
}
