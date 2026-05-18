import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
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

  if (!meta) {
    return (
      <div className="flex-1 px-6 py-5 bg-bg-base text-text-secondary text-[13px]">
        Unknown bot: {bot}
      </div>
    );
  }

  async function onToggle() { await botApi.toggle(bot); }
  async function onForceTrade() { await botApi.forceTrade(bot); }

  const equity = typeof status?.equity === 'number' ? status.equity : null;
  const isEnabled = !!status?.enabled;

  return (
    <div className="flex-1 px-6 py-5 overflow-y-auto font-[var(--font-ui)] text-text-primary bg-bg-base">
      {/* Back link */}
      <Link
        to="/bots"
        className="inline-flex items-center gap-1 text-text-tertiary text-[12px] hover:text-text-secondary mb-4 no-underline"
      >
        <ChevronLeft size={13} />
        Bots
      </Link>

      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <h1 className="text-white text-xl font-extrabold tracking-tight">{meta.display}</h1>
          <p className="text-text-tertiary text-[13px] mt-0.5">
            {STRATEGY_LABEL[meta.strategy]} · {meta.ticker}
          </p>
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-2">
          <button className="sw-btn-secondary !py-1.5 !text-[12px]" onClick={onToggle}>
            {isEnabled ? 'Disable' : 'Enable'}
          </button>
          <button className="sw-btn-ghost !text-[12px]" onClick={onForceTrade}>
            Force Trade
          </button>
          <div className="sw-mono text-[13px] text-text-secondary ml-2">
            {equity != null ? (
              <>
                <span className="sw-label mr-1.5">Equity</span>
                <span className={equity >= 0 ? 'sw-pnl-positive' : 'sw-pnl-negative'}>
                  ${equity.toFixed(2)}
                </span>
              </>
            ) : null}
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="sw-toggle-group !gap-0.5 w-fit mb-0">
        {TABS.map(t => (
          <button
            key={t}
            className={`sw-toggle-btn !px-4 !py-1.5 ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="mt-4">
        {tab === 'Equity' && <EquityTab bot={bot} />}
        {tab === 'Performance' && <PerformanceTab bot={bot} />}
        {tab === 'Positions' && <PositionsTab bot={bot} />}
        {tab === 'Trades' && <TradesTab bot={bot} />}
        {tab === 'Logs' && <LogsTab bot={bot} />}
        {tab === 'Config' && <ConfigTab bot={bot} />}
      </div>
    </div>
  );
}
