import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { BOT_REGISTRY, STRATEGY_LABEL } from '../lib/botRegistry';
import { botApi } from '../lib/botApi';
import { useBotStatus } from '../hooks/useBotStatus';
import EquityTab from '../components/bots/EquityTab';
import PerformanceTab from '../components/bots/PerformanceTab';
import PositionsTab from '../components/bots/PositionsTab';
import TradesTab from '../components/bots/TradesTab';
import LogsTab from '../components/bots/LogsTab';
import ConfigTab from '../components/bots/ConfigTab';

const TABS = ['Equity', 'Performance', 'Positions', 'Trades', 'Logs', 'Config'];

export default function BotDashboard() {
  const { bot } = useParams();
  const meta = BOT_REGISTRY[bot];
  const { data: status } = useBotStatus(bot, 5000);
  const [tab, setTab] = useState('Equity');

  if (!meta) return <div className="page-error">Unknown bot: {bot}</div>;

  async function onToggle() { await botApi.toggle(bot); }
  async function onForceTrade() { await botApi.forceTrade(bot); }

  return (
    <div className="bot-dashboard">
      <header>
        <Link to="/bots" className="back">← Bots</Link>
        <h1>{meta.display}</h1>
        <div className="bot-strategy-sub">{STRATEGY_LABEL[meta.strategy]} · {meta.ticker}</div>
        <div className="bot-toolbar">
          <button onClick={onToggle}>
            {status?.enabled ? 'Disable' : 'Enable'}
          </button>
          <button onClick={onForceTrade}>Force Trade</button>
          <div className="equity">Equity: ${status?.equity?.toFixed(2) ?? '—'}</div>
        </div>
      </header>
      <nav className="tabs">
        {TABS.map(t => (
          <button key={t} className={t === tab ? 'active' : ''}
                  onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>
      <section className="tab-body">
        {tab === 'Equity' && <EquityTab bot={bot} />}
        {tab === 'Performance' && <PerformanceTab bot={bot} />}
        {tab === 'Positions' && <PositionsTab bot={bot} />}
        {tab === 'Trades' && <TradesTab bot={bot} />}
        {tab === 'Logs' && <LogsTab bot={bot} />}
        {tab === 'Config' && <ConfigTab bot={bot} />}
      </section>
    </div>
  );
}
