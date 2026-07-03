# TSUNAMI

TSUNAMI is the LETF earnings-week options bot, ported into SpreadWorks from
the AlphaGEX research lab on 2026-07-03 (formerly GOLIATH, `trading/goliath`).
Paper trading only; live unlock requires explicit sign-off.

## Universe

MSTR, TSLA, NVDA, COIN, AMD (5 underlyings, each with a paired LETF).
Instance names: `TSUNAMI-<LETF>`.

## Structure

Per-instance 3-leg structure (short put + long put + long call) entered
around earnings weeks, gated by G02-G10 pre-entry gates (gates/) and managed
by T1-T8 triggers (management/triggers/). Kill switches per instance +
platform (kill_switch/). Append-only audit (audit/, table `tsunami_trade_audit`).

## Runtime (SpreadWorks)

- Runs on spreadworks-backend via the shared APScheduler:
  entry cycle Mon-Fri 10:30 CT, management every 15 min during market hours.
  Wiring: `backend/bots/tsunami/scheduler_hook.py`, called from
  `backend/__init__.py`.
- Tables: `tsunami_gate_failures`, `tsunami_news_flags`, `tsunami_kill_state`,
  `tsunami_trade_audit`, `tsunami_paper_positions`, `tsunami_equity_snapshots`
  (created by `init_db.ensure_tables()`), plus shared `bot_heartbeats`.
  Database is the shared alphagex-db.
- Data: Tradier (`TRADIER_TOKEN`) for chains/quotes/underlying GEX;
  yfinance for underlying spot/MA/vol/earnings; TV v2
  (`TRADING_VOLATILITY_API_TOKEN`) for LETF IV rank — without the TV token,
  gate G05 fails closed (INSUFFICIENT_HISTORY) and no trades open.
- Discord alerts via the platform-standard `DISCORD_WEBHOOK_URL`.

## Rules

**Paper-only is config-locked.** `configs/global_config.py` `paper_only=True`.
Do not flip without explicit user sign-off.

**Spec defaults are sticky.** Wall threshold 2.0x, fudge factor 0.1, vol
window 30d stay at spec values until Leron explicitly approves changes.

**Data-outage vs market verdict.** G03 has an explicit spot/strikes guard —
keep feed failures distinguishable from real gate rejections in
`tsunami_gate_failures.failure_reason`.

**Universe failure rule.** If any underlying fails coverage, escalate to
Leron with the failure data. Do not work around it.
