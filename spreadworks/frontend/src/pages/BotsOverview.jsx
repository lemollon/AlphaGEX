import BotCard from '../components/bots/BotCard';

export default function BotsOverview() {
  return (
    <div className="flex-1 px-6 py-5 overflow-y-auto font-[var(--font-ui)] text-text-primary bg-bg-base">
      <div className="flex justify-between items-center mb-4">
        <span className="text-white text-xl font-extrabold tracking-tight">Auto Bots</span>
        <span className="text-text-tertiary text-[12px]">3 bots · SPY · paper</span>
      </div>
      <p className="text-text-secondary text-[13px] mb-4">
        Automated paper-trading bots running inside SpreadWorks. Toggle one on from its dashboard.
      </p>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-4">
        {['breeze', 'tide', 'drift'].map(b => <BotCard key={b} bot={b} />)}
      </div>
    </div>
  );
}
