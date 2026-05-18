import BotCard from '../components/bots/BotCard';

export default function BotsOverview() {
  return (
    <div className="bots-overview">
      <h1>Bots</h1>
      <p className="hint">
        Automated paper-trading bots running inside SpreadWorks.
        Toggle a bot on from its dashboard.
      </p>
      <div className="bots-grid">
        {['breeze', 'tide', 'drift'].map(b => <BotCard key={b} bot={b} />)}
      </div>
    </div>
  );
}
