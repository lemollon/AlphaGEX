// TALON promotional card — renders through the shared BotCard component
// (see BotCard.jsx and ReflexSpotlightCard.jsx, the sibling this is modeled
// on), not a second hand-built copy of its JSX.
//
// TALON is a standalone PAPER-ONLY $500 small-cap squeeze stock bot
// (research/talon_paper_trader.py in the squeeze repo, mirrored into this
// app's Postgres by backend/routes_talon.py — see that file's docstring).
// Unlike REFLEX (no live account, so it uses BotCard's `statsLine` prop),
// TALON has a real live API with real numbers — /status and /equity-curve.
// This card feeds those into a real `botStats` shape so it renders through
// BotCard's DEFAULT Sparkline+TradesLine+footer path, identically to any
// other live bot, instead of a hand-rolled approximation of it.
import { useEffect, useState } from 'react';
import BotCard, { signedMoney, money, pnlColor, relativeTime } from './BotCard';
import { API_URL } from '../../lib/api';

export default function TalonSpotlightCard() {
  const [status, setStatus] = useState(null);
  const [curve, setCurve] = useState(null);
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
    // Best-effort — the sparkline just stays empty (same as any brand-new
    // bot with <2 snapshots) if this one fails; it never blocks the card.
    fetch(`${API_URL}/api/spreadworks/talon/equity-curve`)
      .then(res => (res.ok ? res.json() : { curve: [] }))
      .then(data => { if (!cancelled) setCurve(Array.isArray(data.curve) ? data.curve : []); })
      .catch(() => { if (!cancelled) setCurve([]); });
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
        statsLine="…"
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

  // Real botStats shape — same fields BotCard's default (non-overridden)
  // path already reads off any live bot, so the Sparkline/TradesLine/At-risk
  // slots render pixel-identically to every other card instead of drifting.
  const botStats = {
    account: 'paper',
    trades: {
      n: status.closed_trades,
      win_rate: status.win_rate,
      // TALON's /status doesn't break P&L into 7d/30d buckets — TradesLine
      // renders these as "—" (unknown), never a fabricated number.
      pnl_7d: null,
      pnl_30d: null,
    },
    equity_series: curve && curve.length >= 2 ? curve.map(p => ({ equity: p.equity })) : undefined,
    risk: null,
    drawdown_pct: null,
  };

  return (
    <BotCard
      row={{
        bot: 'talon',
        enabled: true,
        starting_capital: status.starting_balance,
        equity_mtm: status.current_balance,
        open_positions: status.open_positions ?? 0,
      }}
      botStats={botStats}
      linkTo="/talon"
      headline={{
        label: 'Total P&L',
        value: signedMoney(status.total_pnl),
        color: pnlColor(status.total_pnl),
        sub: `since ${money(status.starting_balance)} paper start`,
      }}
      scanText={status.updated_at ? `updated ${relativeTime(status.updated_at)}` : 'no sync yet'}
    />
  );
}
