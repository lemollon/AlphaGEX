# AlphaGEX Backend (FastAPI)

Professional Options Intelligence Platform - Backend API

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
cp .env.example .env
# Edit .env with your actual values
```

### 3. Run Development Server

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Server will start at: http://localhost:8000

## 📚 API Documentation

Once the server is running:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## 🔌 Available Endpoints

### Health & Status
- `GET /` - Health check
- `GET /health` - Detailed health status
- `GET /api/time` - Current market time

### GEX Data
- `GET /api/gex/{symbol}` - Get GEX data for symbol
- `GET /api/gex/{symbol}/levels` - Get GEX support/resistance levels

### Gamma Intelligence
- `GET /api/gamma/{symbol}/intelligence` - Get 3-view gamma intelligence

### AI Copilot
- `POST /api/ai/analyze` - Get AI market analysis

### WebSocket
- `WS /ws/market-data?symbol=SPY` - Real-time market data stream

## 🗄️ Database

Currently using SQLite (transitioning to PostgreSQL in Week 2).

**PostgreSQL Setup** (Coming in Week 2):
```bash
# Create database on Render
# Update DATABASE_URL in .env
# Run migrations
alembic upgrade head
```

## 🔧 Development

### Project Structure

```
backend/
├── main.py                   # FastAPI app entry point
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (create from .env.example)
├── .env.example              # Example env file
├── api/                      # API route handlers
│   ├── __init__.py
│   ├── gex.py                # GEX endpoints (TODO)
│   ├── gamma.py              # Gamma endpoints (TODO)
│   ├── ai.py                 # AI endpoints (TODO)
│   └── ...
├── websockets/               # WebSocket handlers
│   ├── __init__.py
│   └── market_data.py        # Market data WebSocket (TODO)
├── database/                 # Database models & migrations
│   ├── __init__.py
│   ├── models.py             # SQLAlchemy models (TODO)
│   └── connection.py         # DB connection (TODO)
├── schemas/                  # Pydantic schemas
│   ├── __init__.py
│   └── ...
└── utils/                    # Utility functions
    ├── __init__.py
    └── helpers.py
```

### Adding New Endpoints

1. Create endpoint in `main.py` or separate file in `api/`
2. Import existing AlphaGEX logic (don't modify original files)
3. Wrap logic in FastAPI route
4. Add Pydantic schemas for request/response in `schemas/`
5. Document with docstring
6. Test with `/docs` Swagger UI

### Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest
```

## 🚢 Deployment

### Render Deployment

1. Create new Web Service on Render
2. Connect GitHub repository
3. Configure:
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variables**: Add from `.env`

4. Deploy!

### Environment Variables on Render

Required:
- `DATABASE_URL` - PostgreSQL connection string (from Render PostgreSQL)
- `CLAUDE_API_KEY` - Anthropic Claude API key
- `TRADING_VOLATILITY_API_KEY` - TradingVolatility.com API key
- `ALLOWED_ORIGINS` - Frontend URLs (comma-separated)
- `ENVIRONMENT` - `production`

## 🔐 Security

- CORS configured for specific origins only
- Environment variables for sensitive data
- PostgreSQL for production (SQLite for dev only)
- Input validation with Pydantic
- Rate limiting (TODO)
- API key authentication (TODO - if adding users)

## 📊 Monitoring

- Health check endpoint: `/health`
- Logs with uvicorn
- Performance monitoring (TODO)
- Error tracking (TODO - Sentry integration)

## 🐛 Troubleshooting

### Import Errors

If you get import errors for existing AlphaGEX modules:
```bash
# Make sure parent directory is in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/path/to/AlphaGEX"
```

### CORS Errors

If frontend can't connect:
1. Check `ALLOWED_ORIGINS` in `.env`
2. Make sure frontend URL is included
3. Restart backend server

### WebSocket Connection Issues

- Ensure firewall allows WebSocket connections
- Check browser console for errors
- Verify `/ws/market-data` endpoint is accessible

## 📝 Notes

### Existing Python Logic

**DO NOT MODIFY** these files - they contain all the working AlphaGEX logic:
- `core_classes_and_engines.py`
- `intelligence_and_strategies.py`
- `autonomous_paper_trader.py`
- `gamma_correlation_tracker.py`
- All other existing `.py` files in parent directory

**Instead:** Import and wrap them in FastAPI endpoints.

### Week 1 Progress

- ✅ Project structure created
- ✅ FastAPI app initialized
- ✅ Basic endpoints (health, GEX, gamma, AI)
- ✅ WebSocket server setup
- 🔲 PostgreSQL migration (Week 2)
- 🔲 Remaining endpoints (Week 3-4)

## 🤝 Contributing

When adding new features:
1. Preserve existing Python logic
2. Add comprehensive docstrings
3. Use Pydantic for validation
4. Test with `/docs` Swagger UI
5. Update this README

## 📚 Resources

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Pydantic Docs](https://docs.pydantic.dev/)
- [SQLAlchemy Docs](https://docs.sqlalchemy.org/)
- [Uvicorn Docs](https://www.uvicorn.org/)
