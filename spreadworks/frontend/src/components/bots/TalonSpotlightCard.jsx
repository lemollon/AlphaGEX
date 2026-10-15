// TALON promotional card — renders through the shared BotCard component
// (see BotCard.jsx and ReflexSpotlightCard.jsx, the sibling this is modeled
// on), not a second hand-built copy of its JSX.
//
// TALON is a standalone PAPER-ONLY $500 small-cap squeeze stock bot
// (research/talon_paper_trader.py in the squeeze repo, mirrored into this
// app's Postgres by backend/routes_talon.py — see that file's docstring).
// Unlike REFLEX, TALON has a real live API (/api/spreadworks/talon/status)
// with a real paper account, so this card fetches and shows the actual
// current numbers rather than a frozen backtest snapshot.
import { useEffect, useState } from 'react';
import BotCard, { signedMoney, money, pnlColor, relativeTime } from './BotCard';
import { API_URL } from '../../lib/api';

export default function TalonSpotlightCard() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/spreadworks/talon/status`)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => { if (!cancelled) setStatus(data); })
      .catch(err => { if (!cancelled) setError(String(err?.message || err)); });
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <BotCard
        row={{ bot: 'talon', error: `Couldn't reach TALON (${error})` }}
        botStats={null}
        linkTo="/talon"
      />
    );
  }

  if (!status) {
    return (
      <BotCard
        row={{ bot: 'talon', enabled: true }}
        botStats={null}
        linkTo="/talon"
        headline={{ label: 'Total P&L', value: '…', color: '#64748b' }}
        footer={[
          { label: 'Total', value: '…' },
          { label: 'Equity', value: '…' },
          { label: 'Open', value: '…' },
        ]}
        atRiskText="loading…"
        scanText="loading…"
      />
    );
  }

  const winRate = status.win_rate != null ? `${Math.round(status.win_rate * 100)}% win` : 'no closed trades yet';
  const n = status.closed_trades || 0;

  return (
    <BotCard
      row={{ bot: 'talon', enabled: true }}
      botStats={null}
      linkTo="/talon"
      headline={{
        label: 'Total P&L',
        value: signedMoney(status.total_pnl),
        color: pnlColor(status.total_pnl),
        sub: `since ${money(status.starting_balance)} paper start`,
      }}
      footer={[
        { label: 'Total', value: signedMoney(status.total_pnl), color: pnlColor(status.total_pnl) },
        { label: 'Equity', value: money(status.current_balance) },
        { label: 'Open', value: status.open_positions ?? 0 },
      ]}
      atRiskText={`${winRate} · ${n} trade${n === 1 ? '' : 's'}`}
      scanText={status.updated_at ? `updated ${relativeTime(status.updated_at)}` : 'no sync yet'}
    />
  );
}
