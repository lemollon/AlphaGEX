# AlphaGEX React Rebuild - Project Plan

**Date:** 2025-10-29
**Objective:** Transform AlphaGEX from Streamlit POC to Professional React/FastAPI Platform
**Timeline:** 8 weeks
**Status:** Planning Phase

---

## 🎯 Project Goals

### Primary Objectives
1. ✅ **Keep ALL Python backend logic intact** - Zero changes to calculations, AI, or intelligence
2. ✅ **Modern React frontend** - Professional, clean UI like the version user saw previously
3. ✅ **Upgrade to PostgreSQL** - Replace SQLite for better performance and scalability
4. ✅ **Real-time updates** - WebSocket for live data during market hours
5. ✅ **Auto-refresh** - Automatic data updates without manual intervention
6. ✅ **Live charts** - Charts update as market moves
7. ✅ **100% feature parity** - Everything that works in Streamlit works in React

### What Changes
- **Frontend:** Streamlit → React/Next.js
- **Database:** SQLite → PostgreSQL
- **Architecture:** Monolith → FastAPI backend + React frontend
- **Hosting:** Render (backend) + Vercel (frontend)
- **Real-time:** Polling → WebSocket

### What Stays EXACTLY the Same
- ✅ All GEX calculations
- ✅ All AI intelligence and Claude integration
- ✅ All gamma analysis logic (3 views)
- ✅ Trading algorithms and auto trader logic
- ✅ Position tracking and management
- ✅ Trade journal functionality
- ✅ All business logic in Python

---

## 📐 Architecture

### Current Architecture (Streamlit)
```
┌─────────────────────────────────────┐
│      Streamlit Monolith             │
│  ┌────────────────────────────┐     │
│  │   UI (Streamlit widgets)   │     │
│  └────────────────────────────┘     │
│  ┌────────────────────────────┐     │
│  │   Python Logic             │     │
│  │   - GEX Calculations       │     │
│  │   - AI Intelligence        │     │
│  │   - Trading Logic          │     │
│  └────────────────────────────┘     │
│  ┌────────────────────────────┐     │
│  │   SQLite Database          │     │
│  └────────────────────────────┘     │
└─────────────────────────────────────┘
         ↓ Render (render.com)
```

### New Architecture (FastAPI + React)
```
┌──────────────────────────────────────────────────────────┐
│                    FRONTEND (Vercel)                     │
│  ┌────────────────────────────────────────────────┐     │
│  │   React/Next.js                                │     │
│  │   - Modern UI Components                       │     │
│  │   - Live Charts (Recharts/TradingView)        │     │
│  │   - Real-time WebSocket Client                 │     │
│  │   - State Management (Zustand/React Query)     │     │
│  └────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────┘
                            ↕ HTTPS + WebSocket
┌──────────────────────────────────────────────────────────┐
│                   BACKEND (Render)                       │
│  ┌────────────────────────────────────────────────┐     │
│  │   FastAPI Server                               │     │
│  │   - REST API Endpoints                         │     │
│  │   - WebSocket Server                           │     │
│  │   - CORS Configuration                         │     │
│  └────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────┐     │
│  │   Python Business Logic (UNCHANGED)            │     │
│  │   - TradingVolatilityAPI                       │     │
│  │   - ClaudeIntelligence                         │     │
│  │   - GammaCorrelationTracker                    │     │
│  │   - AutonomousPaperTrader                      │     │
│  │   - All existing logic preserved               │     │
│  └────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────┐     │
│  │   PostgreSQL (Render PostgreSQL)               │     │
│  │   - All tables migrated from SQLite            │     │
│  │   - Same schema, better performance            │     │
│  └────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────┘
```

---

## 🗂️ Pages/Features to Migrate

All 11 sections must be rebuilt in React:

### 1. **Main Dashboard**
- Top 5 status boxes (System Status, Active Positions, Today's P&L, Market Time, Trading Day)
- GEX overview metrics
- Quick charts
- Recent activity

### 2. **GEX Daily Analysis** ⚠️ CRITICAL
- **ALL CODE AND LOGIC MUST REMAIN UNTOUCHED**
- Only update the frontend presentation
- Preserve all calculations, intelligence, and data structures
- 3 gamma views must work identically

### 3. **Gamma Expiration Intelligence**
- View 1: Daily Impact (Today → Tomorrow)
- View 2: Weekly Evolution (Monday → Friday)
- View 3: Volatility Potential (Risk Calendar)
- All money-making strategies preserved

### 4. **AI Copilot**
- Claude AI integration
- Chat interface
- Strategy recommendations
- Context-aware suggestions

### 5. **Position Tracking**
- Active positions table
- P&L calculations
- Position management (open/close)
- Position history

### 6. **Trade Journal**
- Journal entries
- Trade notes
- Performance tracking
- Trade analysis

### 7. **Auto Trader Dashboard**
- Scheduler controls (start/stop)
- Current status
- Trade history
- Performance metrics
- Timing display (10AM-3PM ET)

### 8. **Paper Trading**
- Paper positions
- Virtual P&L
- Trade execution
- Performance tracking

### 9. **Multi-Symbol Scanner**
- Symbol search
- Watchlist management
- Scanner controls
- Results table

### 10. **Alerts System**
- Alert configuration
- Active alerts
- Alert history
- Notification settings

### 11. **Position Sizing Calculator**
- Kelly Criterion calculator
- Risk calculator
- Position size recommendations
- Portfolio management

---

## 🗄️ Database Migration: SQLite → PostgreSQL

### Tables to Migrate

**Core Tables:**
- `positions` - Active trading positions
- `trade_journal` - Journal entries
- `alerts` - Alert configurations
- `autonomous_positions` - Auto trader positions
- `autonomous_config` - Auto trader settings
- `autonomous_logs` - Auto trader activity logs
- `scheduler_state` - Scheduler persistence

**New Tables (for real-time features):**
- `market_data_cache` - Cached GEX data
- `websocket_subscriptions` - Active WebSocket connections
- `user_preferences` - UI settings (show/hide sections, theme, etc.)

### Migration Strategy
1. **Create PostgreSQL database on Render**
2. **Schema conversion:** SQLite → PostgreSQL DDL
3. **Data migration script:** Export SQLite → Import PostgreSQL
4. **Validation:** Verify all data migrated correctly
5. **Update connection strings** in Python code
6. **Test all queries** work with PostgreSQL

### Connection Details
```python
# SQLite (OLD)
DB_PATH = "alphagex.db"
conn = sqlite3.connect(DB_PATH)

# PostgreSQL (NEW)
DATABASE_URL = os.getenv("DATABASE_URL")  # From Render
conn = psycopg2.connect(DATABASE_URL)
# Or use SQLAlchemy for ORM
```

---

## 🔌 API Endpoints Design

### Base URL
- **Development:** `http://localhost:8000`
- **Production:** `https://alphagex-api.onrender.com`

### Authentication
- **Phase 1:** No auth (single user - you)
- **Future:** JWT tokens if adding users

### Endpoint Structure

#### **GEX Data Endpoints**
```
GET  /api/gex/{symbol}                    # Get GEX data for symbol
GET  /api/gex/{symbol}/levels             # Get GEX support/resistance levels
GET  /api/gex/{symbol}/history?days=30    # Historical GEX data
```

#### **Gamma Intelligence Endpoints**
```
GET  /api/gamma/{symbol}/intelligence     # Get 3-view gamma intelligence
GET  /api/gamma/{symbol}/weekly           # Weekly evolution view
GET  /api/gamma/{symbol}/daily            # Daily impact view
GET  /api/gamma/{symbol}/volatility       # Volatility potential view
```

#### **AI Copilot Endpoints**
```
POST /api/ai/analyze                      # Send query, get Claude response
POST /api/ai/trade-recommendation         # Get specific trade recommendation
GET  /api/ai/context/{symbol}             # Get AI context for symbol
```

#### **Position Management Endpoints**
```
GET    /api/positions                     # List all positions
POST   /api/positions                     # Open new position
GET    /api/positions/{id}                # Get position details
PUT    /api/positions/{id}                # Update position
DELETE /api/positions/{id}                # Close position
GET    /api/positions/pnl                 # Get P&L summary
```

#### **Trade Journal Endpoints**
```
GET    /api/journal                       # List journal entries
POST   /api/journal                       # Create entry
GET    /api/journal/{id}                  # Get entry
PUT    /api/journal/{id}                  # Update entry
DELETE /api/journal/{id}                  # Delete entry
```

#### **Auto Trader Endpoints**
```
GET  /api/autotrader/status               # Get current status
POST /api/autotrader/start                # Start scheduler
POST /api/autotrader/stop                 # Stop scheduler
GET  /api/autotrader/positions            # Get autonomous positions
GET  /api/autotrader/logs                 # Get execution logs
PUT  /api/autotrader/config               # Update config
```

#### **Scanner Endpoints**
```
POST /api/scanner/scan                    # Run scanner with params
GET  /api/scanner/symbols                 # Get available symbols
GET  /api/scanner/watchlist               # Get watchlist
POST /api/scanner/watchlist               # Add to watchlist
```

#### **Alerts Endpoints**
```
GET    /api/alerts                        # List all alerts
POST   /api/alerts                        # Create alert
GET    /api/alerts/{id}                   # Get alert
PUT    /api/alerts/{id}                   # Update alert
DELETE /api/alerts/{id}                   # Delete alert
GET    /api/alerts/history                # Alert history
```

#### **Position Sizing Endpoints**
```
POST /api/sizing/calculate                # Calculate position size
POST /api/sizing/kelly                    # Kelly Criterion calculation
GET  /api/sizing/recommendations          # Get recommendations
```

#### **WebSocket Endpoints**
```
WS   /ws/market-data                      # Real-time market data stream
WS   /ws/positions                        # Real-time position updates
WS   /ws/notifications                    # Real-time alerts/notifications
```

---

## 🎨 Frontend Tech Stack

### Core Framework
- **Next.js 14** (React 18 with App Router)
- **TypeScript** for type safety
- **Tailwind CSS** for styling

### UI Components
- **shadcn/ui** - Beautiful, accessible components
- **Radix UI** - Headless UI primitives
- **Lucide Icons** - Clean, consistent icons

### Charts & Visualizations
- **Recharts** - React charting library
- **TradingView Lightweight Charts** - Professional trading charts (if needed)

### State Management
- **Zustand** - Lightweight state management
- **React Query (TanStack Query)** - Server state & caching

### Real-Time
- **Socket.io Client** - WebSocket client
- **SWR** - Stale-while-revalidate for real-time data

### Forms & Validation
- **React Hook Form** - Form management
- **Zod** - Schema validation

### Utilities
- **date-fns** - Date manipulation
- **numeral** - Number formatting

---

## 🐍 Backend Tech Stack

### Core Framework
- **FastAPI** - Modern Python web framework
- **Uvicorn** - ASGI server
- **Pydantic** - Data validation

### Database
- **PostgreSQL** - Production database (Render PostgreSQL)
- **SQLAlchemy** - ORM
- **Alembic** - Database migrations
- **psycopg2** - PostgreSQL adapter

### Real-Time
- **FastAPI WebSockets** - WebSocket support
- **Redis** (optional) - Pub/sub for multi-instance deployments

### Existing Logic (Keep As-Is)
- ✅ `core_classes_and_engines.py`
- ✅ `intelligence_and_strategies.py`
- ✅ `visualization_and_plans.py`
- ✅ `autonomous_paper_trader.py`
- ✅ All other existing Python files

### New Files to Create
- `main.py` - FastAPI application entry point
- `api/` - API route handlers
  - `api/gex.py`
  - `api/gamma.py`
  - `api/ai.py`
  - `api/positions.py`
  - `api/journal.py`
  - `api/autotrader.py`
  - `api/scanner.py`
  - `api/alerts.py`
  - `api/sizing.py`
- `websockets/` - WebSocket handlers
  - `websockets/market_data.py`
  - `websockets/positions.py`
  - `websockets/notifications.py`
- `database/` - Database models and migrations
  - `database/models.py`
  - `database/connection.py`
  - `database/migrations/`
- `schemas/` - Pydantic schemas for request/response
  - `schemas/gex.py`
  - `schemas/positions.py`
  - etc.

---

## 📅 8-Week Timeline

### **Week 1: Planning & Setup** (CURRENT)
**Goals:**
- ✅ Architecture decisions made
- ✅ Todo list created
- 🔲 Set up project structure
- 🔲 Initialize FastAPI backend
- 🔲 Initialize React frontend
- 🔲 Set up PostgreSQL on Render

**Deliverables:**
- Project plan document (this file)
- Backend project structure
- Frontend project structure
- PostgreSQL database created
- Development environment configured

---

### **Week 2: Database Migration**
**Goals:**
- Migrate SQLite schema to PostgreSQL
- Create migration scripts
- Test data integrity
- Update Python code to use PostgreSQL

**Tasks:**
- Create PostgreSQL DDL from SQLite schema
- Write migration script (SQLite → PostgreSQL)
- Run migration on test data
- Update all database connections in Python code
- Update ORM/raw SQL queries for PostgreSQL compatibility
- Test all database operations

**Deliverables:**
- PostgreSQL database with all tables
- Migration script tested and documented
- All Python code using PostgreSQL
- Data integrity verified

---

### **Week 3: FastAPI Backend Core**
**Goals:**
- Build core FastAPI application
- Implement GEX data endpoints
- Implement gamma intelligence endpoints
- Set up WebSocket server

**Tasks:**
- Create FastAPI main.py
- Set up CORS for frontend
- Build GEX endpoints (wrap existing `TradingVolatilityAPI`)
- Build gamma intelligence endpoints (wrap `get_current_week_gamma_intelligence`)
- Set up WebSocket server for real-time data
- Add logging and error handling
- Create API documentation (automatic with FastAPI)

**Deliverables:**
- Working FastAPI server
- GEX endpoints functional
- Gamma endpoints functional
- WebSocket server running
- API docs at `/docs`

---

### **Week 4: FastAPI Backend Features**
**Goals:**
- Build remaining API endpoints
- AI Copilot endpoint
- Position management endpoints
- Auto trader endpoints

**Tasks:**
- Build AI Copilot endpoint (wrap `ClaudeIntelligence`)
- Build positions CRUD endpoints
- Build trade journal endpoints
- Build auto trader control endpoints
- Build scanner endpoints
- Build alerts endpoints
- Build position sizing endpoints
- Add request validation (Pydantic schemas)
- Add response models

**Deliverables:**
- All API endpoints functional
- Full API documentation
- Backend ready for frontend integration

---

### **Week 5: React Frontend Foundation**
**Goals:**
- Set up React project
- Build design system
- Create layout and navigation
- Build main dashboard

**Tasks:**
- Initialize Next.js project with TypeScript
- Set up Tailwind CSS
- Install and configure UI libraries (shadcn/ui)
- Create design system (colors, typography, spacing)
- Build layout components (Header, Sidebar, Navigation)
- Build routing structure
- Build top 5 status boxes
- Build main dashboard page
- Set up API client (Axios/Fetch with React Query)

**Deliverables:**
- React app running
- Design system implemented
- Navigation working
- Main dashboard displaying data from API

---

### **Week 6: React Feature Pages Part 1**
**Goals:**
- Build GEX Daily Analysis page
- Build Gamma Intelligence views
- Build AI Copilot interface

**Tasks:**
- **GEX Daily Analysis page** ⚠️
  - Preserve ALL logic from backend
  - Build UI to display gamma intelligence 3 views
  - Ensure calculations match Streamlit version exactly
- Build interactive gamma intelligence visualizations
- Build AI Copilot chat interface
- Add loading states and skeletons
- Add error handling

**Deliverables:**
- GEX Daily Analysis page complete (logic preserved)
- Gamma Intelligence 3 views functional
- AI Copilot working

---

### **Week 7: React Feature Pages Part 2**
**Goals:**
- Build remaining feature pages
- Position tracking
- Trade journal
- Auto trader dashboard

**Tasks:**
- Build position tracking page (table, P&L, actions)
- Build trade journal page (entries, notes, analysis)
- Build auto trader dashboard (controls, status, logs)
- Build paper trading page
- Build scanner page
- Build alerts page
- Build position sizing calculator
- Implement WebSocket client in React
- Connect real-time data to charts

**Deliverables:**
- All 11 pages functional
- WebSocket integration working
- Real-time updates working

---

### **Week 8: Polish, Test, Deploy**
**Goals:**
- Polish UI/UX
- Optimize performance
- End-to-end testing
- Deploy to production

**Tasks:**
- Add smooth animations and transitions
- Optimize mobile responsive layout
- Add loading states everywhere
- Add toast notifications for actions
- Performance optimization (lazy loading, code splitting)
- End-to-end testing (all features)
- Fix bugs
- Deploy backend to Render
- Deploy frontend to Vercel
- Migrate production data
- Update DNS (if needed)
- Monitor for issues

**Deliverables:**
- Professional, polished UI
- All features working
- Production deployment live
- No critical bugs

---

## 🎨 Design System

### Color Palette (Based on Current Dark Theme)
```css
/* Primary Colors */
--primary-blue: #00D4FF;      /* Main brand color */
--primary-green: #00FF88;     /* Success, profit */
--primary-red: #FF4444;       /* Error, loss */
--primary-yellow: #FFB800;    /* Warning, caution */
--primary-purple: #8A2BE2;    /* Accent */

/* Background Colors */
--bg-dark: #0a0e17;           /* Main background */
--bg-card: #141821;           /* Card background */
--bg-hover: #1a1f2e;          /* Hover state */

/* Text Colors */
--text-primary: #ffffff;      /* Main text */
--text-secondary: #8b92a7;    /* Secondary text */
--text-muted: rgba(255,255,255,0.6);  /* Muted text */

/* Border Colors */
--border-subtle: rgba(255,255,255,0.1);
--border-medium: rgba(255,255,255,0.2);
```

### Typography
```css
/* Headings */
--font-heading: 'Inter', -apple-system, sans-serif;
--heading-1: 48px / 900;      /* Page titles */
--heading-2: 32px / 800;      /* Section titles */
--heading-3: 24px / 700;      /* Subsections */
--heading-4: 18px / 700;      /* Card titles */

/* Body Text */
--font-body: 'Inter', -apple-system, sans-serif;
--body-large: 16px / 400;
--body-medium: 14px / 400;
--body-small: 12px / 400;

/* Monospace (for numbers) */
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;
```

### Spacing Scale
```
4px, 8px, 12px, 16px, 20px, 24px, 32px, 40px, 48px, 64px
```

### Component Styles

**Status Box:**
```tsx
<div className="
  bg-gradient-to-br from-blue-500/10 to-blue-600/5
  border-2 border-blue-500/40
  rounded-2xl p-6
  min-h-[120px] h-[120px] max-h-[120px]
  flex flex-col justify-between
  shadow-xl
  hover:scale-102 transition-transform
">
  <div className="text-white/60 text-sm">Label</div>
  <div className="text-white text-2xl font-semibold">Value</div>
  <div className="text-sm">Detail</div>
</div>
```

**Card:**
```tsx
<div className="
  bg-gray-800/50
  border border-white/10
  rounded-xl p-6
  backdrop-blur-sm
">
  {/* Content */}
</div>
```

---

## 🔄 Real-Time Features

### WebSocket Implementation

**Backend (FastAPI):**
```python
# websockets/market_data.py
from fastapi import WebSocket

@app.websocket("/ws/market-data")
async def market_data_websocket(websocket: WebSocket):
    await websocket.accept()

    while True:
        # Fetch latest GEX data
        gex_data = api_client.get_net_gamma('SPY')

        # Send to client
        await websocket.send_json({
            "type": "gex_update",
            "data": gex_data,
            "timestamp": datetime.now().isoformat()
        })

        # Wait 30 seconds
        await asyncio.sleep(30)
```

**Frontend (React):**
```typescript
// hooks/useMarketData.ts
import { useEffect, useState } from 'react';

export function useMarketData(symbol: string) {
  const [data, setData] = useState(null);

  useEffect(() => {
    const ws = new WebSocket('wss://alphagex-api.onrender.com/ws/market-data');

    ws.onmessage = (event) => {
      const update = JSON.parse(event.data);
      setData(update.data);
    };

    return () => ws.close();
  }, [symbol]);

  return data;
}
```

### Auto-Refresh Strategy
- **Market hours (9:30 AM - 4:00 PM ET):** WebSocket updates every 30 seconds
- **After hours:** Polling every 5 minutes (to save resources)
- **Positions:** Real-time updates via WebSocket
- **Charts:** Live updates during market hours

---

## 🚀 Deployment Strategy

### Backend Deployment (Render)
```yaml
# render.yaml
services:
  - type: web
    name: alphagex-api
    env: python
    plan: standard
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: alphagex-db
          property: connectionString
      - key: CLAUDE_API_KEY
        sync: false
      - key: TRADING_VOLATILITY_API_KEY
        sync: false

databases:
  - name: alphagex-db
    plan: starter
    databaseName: alphagex
    user: alphagex
```

### Frontend Deployment (Vercel)
```json
// vercel.json
{
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "devCommand": "npm run dev",
  "installCommand": "npm install",
  "framework": "nextjs",
  "env": {
    "NEXT_PUBLIC_API_URL": "https://alphagex-api.onrender.com"
  }
}
```

### DNS Configuration
- **Option 1:** Keep `alphagex.onrender.com`, point to Vercel frontend
- **Option 2:** Use custom domain (e.g., `alphagex.com`)
  - Frontend: `alphagex.com` → Vercel
  - Backend: `api.alphagex.com` → Render

---

## ✅ Testing Strategy

### Backend Testing
- **Unit tests** for each endpoint
- **Integration tests** for database operations
- **Load testing** for WebSocket connections
- **Test coverage:** Aim for 80%+

### Frontend Testing
- **Component tests** (React Testing Library)
- **E2E tests** (Playwright) for critical flows
- **Visual regression** testing
- **Performance testing** (Lighthouse)

### Critical Test Cases
1. **GEX data fetching** - Must match Streamlit calculations exactly
2. **Gamma intelligence** - All 3 views must preserve logic
3. **AI Copilot** - Claude integration works
4. **Position management** - Open/close positions correctly
5. **Auto trader** - Scheduler works, trades execute
6. **WebSocket** - Real-time updates work
7. **Database** - All CRUD operations work

---

## 🎯 Success Criteria

### Must Have (Launch Blockers)
- ✅ All 11 pages functional
- ✅ GEX Daily Analysis preserves ALL logic
- ✅ AI Copilot works
- ✅ Position tracking works
- ✅ Auto trader works (scheduler, trades, logs)
- ✅ Real-time updates work
- ✅ Mobile responsive
- ✅ No critical bugs
- ✅ Performance: Page load < 2 seconds

### Nice to Have (Post-Launch)
- Dark mode toggle
- Customizable dashboard (drag-and-drop widgets)
- Keyboard shortcuts
- Export data to CSV
- Historical trade analysis charts
- Multiple themes

---

## 📊 Progress Tracking

Progress will be tracked in the Todo list (visible via `/todos` command).

**Weekly Check-ins:**
- Review completed tasks
- Discuss blockers
- Adjust timeline if needed
- Demo progress

---

## 🔐 Environment Variables

### Backend (.env)
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/alphagex

# APIs
CLAUDE_API_KEY=sk-...
TRADING_VOLATILITY_API_KEY=...

# CORS
ALLOWED_ORIGINS=https://alphagex.vercel.app,http://localhost:3000

# Environment
ENVIRONMENT=production
```

### Frontend (.env.local)
```bash
NEXT_PUBLIC_API_URL=https://alphagex-api.onrender.com
NEXT_PUBLIC_WS_URL=wss://alphagex-api.onrender.com
```

---

## 📝 File Structure

### Backend Structure
```
backend/
├── main.py                      # FastAPI app entry point
├── requirements.txt             # Python dependencies
├── alembic.ini                  # Database migrations config
├── api/
│   ├── __init__.py
│   ├── gex.py                   # GEX endpoints
│   ├── gamma.py                 # Gamma intelligence endpoints
│   ├── ai.py                    # AI Copilot endpoints
│   ├── positions.py             # Position management
│   ├── journal.py               # Trade journal
│   ├── autotrader.py            # Auto trader
│   ├── scanner.py               # Scanner
│   ├── alerts.py                # Alerts
│   └── sizing.py                # Position sizing
├── websockets/
│   ├── __init__.py
│   ├── market_data.py           # Market data WebSocket
│   ├── positions.py             # Position updates WebSocket
│   └── notifications.py         # Notifications WebSocket
├── database/
│   ├── __init__.py
│   ├── models.py                # SQLAlchemy models
│   ├── connection.py            # Database connection
│   └── migrations/              # Alembic migrations
├── schemas/
│   ├── __init__.py
│   ├── gex.py                   # GEX Pydantic schemas
│   ├── positions.py             # Position schemas
│   └── ...
├── existing_logic/               # EXISTING FILES - DO NOT MODIFY
│   ├── core_classes_and_engines.py
│   ├── intelligence_and_strategies.py
│   ├── visualization_and_plans.py
│   ├── autonomous_paper_trader.py
│   ├── gamma_correlation_tracker.py
│   ├── gamma_alerts.py
│   └── ... (all other existing .py files)
└── utils/
    ├── __init__.py
    └── helpers.py
```

### Frontend Structure
```
frontend/
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.js
├── app/
│   ├── layout.tsx               # Root layout
│   ├── page.tsx                 # Home/Dashboard
│   ├── dashboard/
│   │   └── page.tsx             # Main dashboard
│   ├── gex-analysis/
│   │   └── page.tsx             # GEX Daily Analysis
│   ├── gamma-intelligence/
│   │   └── page.tsx             # Gamma 3 views
│   ├── ai-copilot/
│   │   └── page.tsx             # AI Copilot
│   ├── positions/
│   │   └── page.tsx             # Position tracking
│   ├── journal/
│   │   └── page.tsx             # Trade journal
│   ├── autotrader/
│   │   └── page.tsx             # Auto trader
│   ├── scanner/
│   │   └── page.tsx             # Multi-symbol scanner
│   ├── alerts/
│   │   └── page.tsx             # Alerts
│   └── sizing/
│       └── page.tsx             # Position sizing
├── components/
│   ├── ui/                      # shadcn/ui components
│   ├── layout/
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   └── Navigation.tsx
│   ├── dashboard/
│   │   ├── StatusBox.tsx
│   │   └── MetricsCard.tsx
│   ├── charts/
│   │   ├── GEXChart.tsx
│   │   ├── GammaChart.tsx
│   │   └── LiveChart.tsx
│   └── ...
├── lib/
│   ├── api.ts                   # API client
│   ├── websocket.ts             # WebSocket client
│   └── utils.ts                 # Utilities
├── hooks/
│   ├── useMarketData.ts
│   ├── usePositions.ts
│   ├── useWebSocket.ts
│   └── ...
├── store/
│   ├── marketStore.ts           # Zustand store
│   └── uiStore.ts
└── types/
    ├── gex.ts
    ├── positions.ts
    └── ...
```

---

## 🚨 Risk Mitigation

### Risks & Mitigation Strategies

**Risk 1: Data loss during migration**
- **Mitigation:**
  - Backup SQLite database before migration
  - Test migration on copy first
  - Verify data integrity after migration
  - Keep SQLite backup for 30 days

**Risk 2: Breaking existing Python logic**
- **Mitigation:**
  - DO NOT modify existing Python files
  - Only create new wrapper functions
  - Comprehensive testing of all calculations
  - Compare outputs with Streamlit version

**Risk 3: WebSocket performance issues**
- **Mitigation:**
  - Start with 30-second intervals
  - Monitor server load
  - Implement connection pooling
  - Add Redis if needed for scaling

**Risk 4: Auto trader stops working**
- **Mitigation:**
  - Test thoroughly in paper trading first
  - Keep detailed logs
  - Add health checks
  - Alert if scheduler stops

**Risk 5: Frontend/backend version mismatch**
- **Mitigation:**
  - API versioning (v1, v2)
  - Backward compatibility
  - Graceful degradation
  - Clear deployment process

**Risk 6: Timeline slippage**
- **Mitigation:**
  - Weekly check-ins
  - Identify blockers early
  - Prioritize must-have features
  - Have fallback plan (keep Streamlit running in parallel)

---

## 📚 Documentation

### Documentation to Create
1. **API Documentation** (auto-generated by FastAPI)
2. **Database Schema Documentation**
3. **WebSocket Protocol Documentation**
4. **Frontend Component Library** (Storybook optional)
5. **Deployment Guide**
6. **Troubleshooting Guide**

---

## 🎉 Post-Launch

### Future Enhancements (Not in initial 8 weeks)
- Mobile app (React Native)
- Multiple user support with authentication
- Customizable dashboards
- Advanced charting (TradingView integration)
- Backtesting framework
- Strategy builder UI
- Social features (share trades/strategies)
- White-label for selling platform

---

## 📞 Communication

### Status Updates
- **Weekly:** Progress report (tasks completed, blockers, next week plan)
- **Daily:** Quick status update (what's done, what's in progress)
- **Ad-hoc:** Questions, blockers, design decisions

### Decision Log
All major decisions will be documented:
- Date
- Decision made
- Rationale
- Alternatives considered

---

## ✅ Next Steps (Week 1)

1. **Review this plan** - Make sure everything looks good
2. **Set up project repositories:**
   - Create `backend/` directory
   - Create `frontend/` directory
3. **Initialize FastAPI backend:**
   - Create virtual environment
   - Install FastAPI, Uvicorn, SQLAlchemy, psycopg2
   - Create basic `main.py`
4. **Initialize React frontend:**
   - Run `npx create-next-app@latest`
   - Install Tailwind, shadcn/ui
   - Set up basic routing
5. **Set up PostgreSQL on Render:**
   - Create database instance
   - Get connection string
   - Test connection from local machine

**Let's start with Week 1 tasks!** 🚀

---

**End of Project Plan**
