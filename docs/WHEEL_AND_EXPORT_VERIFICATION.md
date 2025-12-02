# Wheel Strategy & Export Features - Verification Guide

## Quick Verification

Run the automated verification script:

```bash
python scripts/verify_wheel_and_export.py
```

This will check:
- Database tables exist
- Wheel strategy logic works
- Export service is functional
- API routes are registered
- Frontend components exist
- Unit tests pass

## Manual Verification Steps

### 1. Verify Backend API Endpoints

Start the backend server:
```bash
cd /home/user/AlphaGEX
uvicorn backend.main:app --reload --port 8000
```

Test these endpoints with curl or browser:

#### Wheel Strategy Endpoints

```bash
# Get wheel phases info
curl http://localhost:8000/api/wheel/phases

# Get active wheel cycles
curl http://localhost:8000/api/wheel/active

# Get wheel summary stats
curl http://localhost:8000/api/wheel/summary
```

#### Export Endpoints

```bash
# Check export status
curl http://localhost:8000/api/export/status

# Download trade history (opens Excel file)
curl -O http://localhost:8000/api/export/trades?symbol=SPY

# Download P&L attribution
curl -O http://localhost:8000/api/export/pnl-attribution?symbol=SPY

# Download decision logs
curl -O http://localhost:8000/api/export/decision-logs?symbol=SPY

# Download full audit package
curl -O http://localhost:8000/api/export/full-audit?symbol=SPY
```

### 2. Verify Frontend UI

Start the frontend:
```bash
cd /home/user/AlphaGEX/frontend
npm run dev
```

#### Check Wheel Strategy Page
1. Go to http://localhost:3000/wheel
2. Verify you see:
   - Wheel Strategy header with RotateCcw icon
   - "Start New Wheel" button
   - How The Wheel Works diagram (4 phases)
   - Active Wheel Cycles section (may be empty)
   - Export to Excel dropdown

#### Check Trader Page Export Buttons
1. Go to http://localhost:3000/trader
2. Look for "Export to Excel" dropdown button in the header
3. Click it and verify dropdown shows:
   - Trade History
   - P&L Attribution
   - Decision Logs
   - Wheel Cycles
   - Full Audit Package

#### Check Navigation
1. Click the navigation menu
2. Under "Automation" category, verify "Wheel Strategy" link exists
3. Click it and verify it navigates to /wheel

### 3. Test Wheel Strategy Flow

#### Start a New Wheel (if you have trading data)
1. Go to /wheel
2. Click "Start New Wheel"
3. Fill in the form:
   - Symbol: SPY
   - Strike: (pick a strike below current price)
   - Expiration: (pick a date 30-45 days out)
   - Contracts: 1
   - Premium: 2.50 (example)
   - Current Price: (current SPY price)
4. Click "Start Wheel (Sell CSP)"
5. Verify success message appears
6. Refresh and verify cycle appears in Active Cycles

### 4. Test Export Downloads

1. Go to /trader
2. Click "Export to Excel"
3. Click "Trade History"
4. Verify Excel file downloads
5. Open the file and verify:
   - "Closed Trades" sheet exists
   - "Open Positions" sheet exists
   - "Summary" sheet exists with stats
6. Repeat for other export types

### 5. Database Verification

Connect to PostgreSQL and verify tables:

```sql
-- Check wheel tables exist
SELECT table_name FROM information_schema.tables
WHERE table_name LIKE 'wheel_%';

-- Should see:
-- wheel_cycles
-- wheel_legs
-- wheel_activity_log

-- Check table structure
\d wheel_cycles
\d wheel_legs
\d wheel_activity_log
```

### 6. Run Tests

```bash
# Run all tests
cd /home/user/AlphaGEX
pytest tests/ -v

# Run only wheel/export tests
pytest tests/test_wheel_strategy.py tests/test_export_endpoints.py -v
```

## Expected Results

### All Checks Pass If:
- [ ] Backend starts without import errors
- [ ] All /api/wheel/* endpoints return 200
- [ ] All /api/export/* endpoints return 200 or valid Excel files
- [ ] Frontend /wheel page renders without errors
- [ ] Export dropdown appears on /trader page
- [ ] Navigation includes Wheel Strategy link
- [ ] All unit tests pass
- [ ] Database tables exist

### Common Issues

#### openpyxl not installed
```bash
pip install openpyxl
```

#### Database connection fails
- Check DATABASE_URL environment variable
- Ensure PostgreSQL is running

#### Frontend components not found
- Run `npm install` in frontend directory
- Check for TypeScript errors with `npm run build`

## Files Added/Modified

### New Files
- `trading/wheel_strategy.py` - Wheel strategy implementation
- `trading/export_service.py` - Export service
- `backend/api/routes/wheel_routes.py` - Wheel API routes
- `backend/api/routes/export_routes.py` - Export API routes
- `frontend/src/components/trader/WheelDashboard.tsx`
- `frontend/src/components/trader/ExportButtons.tsx`
- `frontend/src/app/wheel/page.tsx`
- `tests/test_wheel_strategy.py`
- `tests/test_export_endpoints.py`
- `scripts/verify_wheel_and_export.py`

### Modified Files
- `backend/main.py` - Added route imports and registration
- `frontend/src/components/Navigation.tsx` - Added wheel link
- `frontend/src/app/trader/page.tsx` - Added ExportButtons

## Support

If verification fails, check:
1. Console/terminal for error messages
2. Browser developer console for frontend errors
3. Backend logs for API errors
4. Database connection and permissions
