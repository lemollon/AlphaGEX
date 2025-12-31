# AlphaGEX Render Shell Commands

Quick reference for production verification in Render shell.

## Full System Check (Run This First)

```bash
bash scripts/render_full_check.sh
```

This runs all checks in order.

---

## Individual Checks

### 1. Check Python Imports
```bash
python scripts/render_check_imports.py
```
Verifies all Python modules import correctly.

### 2. Check Database
```bash
python scripts/render_check_database.py
```
Tests database connection and checks tables exist.

### 3. Check AI Features
```bash
python scripts/render_check_ai.py
```
Tests Learning Memory, Extended Thinking, GEXIS personality.

### 4. Check API Endpoints
```bash
python scripts/render_test_api.py
```
Verifies all API routes load correctly.

### 5. Test Live API
```bash
python scripts/render_test_api.py --live https://your-api.onrender.com
```
Tests actual HTTP endpoints against running API.

---

## Run Migrations

### Dry Run (Preview)
```bash
python scripts/render_run_migrations.py
```

### Apply Migrations
```bash
python scripts/render_run_migrations.py --apply
```

**This will:**
- Add extended columns to ARES positions table
- Reset all bots to fresh start (0 trades, 0 P&L)

---

## Troubleshooting

### Missing Dependencies
```bash
pip install fastapi uvicorn psycopg2-binary anthropic
```

### Check Environment Variables
```bash
echo $DATABASE_URL
echo $CLAUDE_API_KEY
echo $TRADIER_SANDBOX_API_KEY
```

### Start Backend Manually
```bash
cd backend && python main.py
# or
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## Expected Results

After running `bash scripts/render_full_check.sh`:

```
[OK] Python Imports
[OK] Database Connection
[OK] AI Features
[OK] API Endpoints
[OK] AI Init Script

ALL CHECKS PASSED - System is production ready!
```
