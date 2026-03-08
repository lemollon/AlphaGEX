# SpreadWorks

Double Diagonal & Calendar Spread Analyzer powered by AlphaGEX GEX data.

## Architecture

```
frontend/          Vite + React (StrategyPanel, App)
backend/           FastAPI (spread calc, GEX proxy, alerts)
bot/               Discord.js bot (/spread command)
```

Three Render services: `spreadworks-frontend` (static), `spreadworks-backend` (Python), `spreadworks-bot` (Node worker).

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Tradier API token (for live chain data)
- AlphaGEX backend running (for GEX data)

### Setup

```bash
# 1. Copy environment file
cp .env.example .env
# Fill in: TRADIER_TOKEN, TRADIER_ACCOUNT_ID, ALPHAGEX_BASE_URL,
#          DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_GUILD_ID,
#          DISCORD_WEBHOOK_URL, VITE_API_URL, FRONTEND_URL

# 2. Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173

# 4. Discord Bot (separate terminal, optional)
cd bot
npm install
node src/index.js
```

### Key Environment Variables

| Variable | Required By | Description |
|----------|-------------|-------------|
| `TRADIER_TOKEN` | Backend | Tradier API token for options chain |
| `TRADIER_ACCOUNT_ID` | Backend | Tradier account ID |
| `ALPHAGEX_BASE_URL` | Backend | AlphaGEX backend URL for GEX data |
| `DISCORD_TOKEN` | Bot | Discord bot token |
| `DISCORD_CLIENT_ID` | Bot | Discord application client ID |
| `DISCORD_GUILD_ID` | Bot | Discord server ID for slash commands |
| `DISCORD_WEBHOOK_URL` | Bot | Webhook for alert notifications |
| `VITE_API_URL` | Frontend | SpreadWorks backend URL |
| `FRONTEND_URL` | Backend | Frontend URL for CORS |

## Render Deploy

1. Connect your repo to Render
2. Use `render-spreadworks.yaml` as the blueprint
3. Set all env vars listed above in the Render dashboard
4. Deploy - Render builds all 3 services automatically

```bash
# Manual deploy (push to main triggers auto-deploy)
git push origin main
```

## Features

### Strategy Panel (`StrategyPanel.jsx`)

- **Double Diagonal**: 4 strikes (long put, short put, short call, long call) + 2 expirations
- **Double Calendar**: 2 strikes (put, call) + 2 expirations (front, back)
- **Input Modes**:
  - **Live Chain** - Fetches real expirations/strikes from Tradier
  - **Manual** - Type in strikes and dates directly
  - **GEX Suggest** - Auto-fills strikes based on AlphaGEX GEX levels (flip point, walls, regime)

### App (`App.jsx`)

- Two-column layout: Strategy Builder (left), Results + Market Data (right)
- Loads candle data with 1-minute refresh
- Polls price alerts every 15 seconds with toast notifications
- Displays GEX levels (flip point, call/put walls, gamma regime)
- Shows spread analysis results (max profit/loss, breakevens, Greeks, P(profit))

### Discord Bot (`/spread` command)

- `/spread` - Default SPY Double Diagonal suggestion
- `/spread symbol:QQQ strategy:double_calendar` - Custom symbol + strategy
- Returns Discord embed with GEX levels, suggested strikes, and rationale

## API Endpoints

```
GET  /api/spreadworks/candles?symbol=SPY         # OHLCV candle data
GET  /api/spreadworks/gex?symbol=SPY             # GEX levels from AlphaGEX
GET  /api/spreadworks/expirations?symbol=SPY     # Available expirations
GET  /api/spreadworks/chain?symbol=SPY&exp=DATE  # Option chain strikes
GET  /api/spreadworks/gex-suggest?symbol=SPY&strategy=double_diagonal
POST /api/spreadworks/calculate                   # Spread P&L calculation
GET  /api/spreadworks/alerts                      # Active price alerts
POST /api/spreadworks/alerts/:id/trigger          # Mark alert triggered
```
