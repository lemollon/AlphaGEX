# AlphaGEX

AlphaGEX is now intentionally focused on two trading systems:

- **VALOR** — multi-instrument micro-futures trading
- **Crypto Perpetuals** — BTC, ETH, SOL, AVAX, XRP, and DOGE perpetual strategies

The active web API, scheduler, and frontend are scoped to those systems and the
shared infrastructure they require (database access, market data, margin/risk,
execution, logging, and retained research/backtesting utilities).

## Protected sibling projects

The repository also contains independent projects that are **not part of this
AlphaGEX cleanup**:

- `spreadworks/`
- `ironforge/`

Do not delete, move, or refactor those directories as part of AlphaGEX pruning.

## Runtime

- `alphagex-api`: FastAPI routes for VALOR and active perpetuals
- `alphagex-trader`: VALOR + perpetual scheduling/execution
- PostgreSQL: shared AlphaGEX trading state
- SpreadWorks retains its existing Render service definition
- IronForge retains its separate deployment configuration

## Local start

```bash
pip install -r requirements.txt
./start.sh
```

The frontend home route redirects to `/valor`; the navigation exposes VALOR,
the aggregate crypto perpetual dashboard, and each active perpetual bot.
