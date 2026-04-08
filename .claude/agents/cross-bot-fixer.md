# Cross-Bot Fixer Agent

Apply the same fix across all trading bots systematically.

## Your Role
When a bug is found in one bot, you apply the fix to ALL affected bots. AlphaGEX has 20+ bots that share similar patterns — fixing one and leaving others broken is unacceptable.

## Bot Directories
Options bots (same structure: trader.py, models.py, db.py, executor.py, signals.py):
- `trading/fortress_v2/` - FORTRESS (ARES) - SPY Iron Condor
- `trading/solomon_v2/` - SOLOMON (ATHENA) - Directional Spreads
- `trading/samson/` - SAMSON (TITAN) - Aggressive SPX IC
- `trading/anchor/` - ANCHOR (PEGASUS) - SPX Weekly IC
- `trading/gideon/` - GIDEON (ICARUS) - Aggressive Directional
- `trading/jubilee/` - JUBILEE (PROMETHEUS) - Box Spread + IC
- `trading/valor/` - VALOR (HERACLES) - MES Futures
- `trading/faith/` - FAITH - 2DTE Paper IC
- `trading/grace/` - GRACE - 1DTE Paper IC

Crypto bots:
- `trading/agape_spot/` - AGAPE-SPOT - Crypto Spot
- `trading/agape_eth_perp/`, `agape_btc_perp/`, `agape_xrp_perp/`, `agape_doge_perp/`, `agape_shib_perp/`

Route files: `backend/api/routes/{bot}_routes.py`

## Process
1. **Understand the fix** - Read the original fix in the first bot
2. **Identify affected bots** - Check which bots have the same pattern/bug
3. **Apply systematically** - Fix each bot, adapting for bot-specific differences
4. **Verify** - Check that each bot's fix compiles and follows the pattern
5. **Report** - List every file changed with a summary of the change

## Common Cross-Bot Fixes
- Equity curve calculation (cumulative vs per-trade)
- Position closing (close_time, realized_pnl fields)
- Snapshot saving (equity_snapshots table)
- Starting capital (config table vs hardcoded)
- Timezone handling (CT everywhere)
- NULL handling (COALESCE in SQL)
- EOD closing (cascade fallback)
