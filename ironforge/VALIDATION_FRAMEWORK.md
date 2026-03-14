# IronForge System Validation & Accountability Framework

**PURPOSE**: This document defines what "working" means for IronForge, how to prove it, and how to hold Claude Code accountable for its claims. Every future session involving IronForge changes must reference this document.

---

## SECTION 1: SYSTEM CONTRACT — What Must Be True At All Times

These are the invariants. If ANY of these are violated, the system is broken. Period.

### Money Invariants

- **INV-1**: `paper_account.current_balance = starting_capital + SUM(realized_pnl FROM all closed positions for this bot)`
- **INV-2**: `paper_account.collateral_in_use = SUM(collateral_required FROM all open positions for this bot)` — exact match, not approximate
- **INV-3**: `paper_account.buying_power = current_balance - collateral_in_use`
- **INV-4**: No position can have `status='closed'` AND still contribute to `collateral_in_use`
- **INV-5**: No position can have `status='open'` with a `created_at` date older than today (no overnight positions for any bot)
- **INV-6**: `SUM(all realized_pnl)` must equal the net of all `entry_credit` and `exit_debit` values across closed positions

### Execution Invariants

- **INV-7**: Every position that opens in the DB must have a corresponding sandbox position (for FLAME) or paper record
- **INV-8**: Every position that closes in the DB must close its corresponding sandbox position (for FLAME)
- **INV-9**: If a sandbox close fails, the system must retry (cascade) and log the failure visibly — never silently skip
- **INV-10**: Closing a position and releasing its collateral must be atomic — if one fails, both fail (or reconciliation catches it within 1 scan cycle)

### Data Freshness Invariants

- **INV-11**: The dashboard must show data no older than 15 seconds for balance, collateral, and position status
- **INV-12**: The dashboard must NEVER show $0 for any financial value when the real value is non-zero (error state must show "—" or "unavailable", not $0)
- **INV-13**: The "Scanning..." badge must reflect actual scanner state — if the scanner hasn't sent a heartbeat in >120 seconds, the badge must show a warning state
- **INV-14**: Every API route serving financial data must use `dynamic = 'force-dynamic'` and `cache: 'no-store'`

### Safety Invariants

- **INV-15**: `max_contracts` must be enforced — no position can exceed the configured cap
- **INV-16**: No trade should open when oracle WP < 0.50 (weak signal gate)
- **INV-17**: The kill switch must be accessible from the dashboard at all times — one click to close everything
- **INV-18**: Every error from Tradier API (400, 401, 403, 500) must be logged with the status code, endpoint, and context — never swallowed silently

---

## SECTION 2: DEEP VALIDATION TESTS

These go beyond "does the code look right" and test the actual scenarios that broke on March 13.

### Category A: Database Layer (Run in Databricks Notebook)

#### A1. db_execute() rows_affected — Basic

```python
# Setup
spark.sql("CREATE TABLE IF NOT EXISTS alpha_prime.ironforge.test_validation (id INT, status STRING, pnl FLOAT)")
spark.sql("INSERT INTO alpha_prime.ironforge.test_validation VALUES (1, 'open', 0.0)")

# Test: UPDATE match → expect 1
r1 = spark.sql("UPDATE alpha_prime.ironforge.test_validation SET status='closed', pnl=50.0 WHERE id=1 AND status='open'")
assert r1.collect()[0][0] == 1, f"FAIL: expected 1, got {r1.collect()[0][0]}"

# Test: UPDATE no-match (already closed) → expect 0
r2 = spark.sql("UPDATE alpha_prime.ironforge.test_validation SET status='closed', pnl=50.0 WHERE id=1 AND status='open'")
assert r2.collect()[0][0] == 0, f"FAIL: expected 0, got {r2.collect()[0][0]}"

# Cleanup
spark.sql("DROP TABLE alpha_prime.ironforge.test_validation")
print("A1: PASS")
```

**What this proves**: The foundation of the double-counting guard works.
**Invariants tested**: INV-1, INV-4, INV-10

#### A2. db_execute() rows_affected — Delta Lake Specifics

```python
# Delta Lake UPDATE behavior can differ from standard SQL
# Test with the EXACT same WHERE clause pattern used in close_position()
spark.sql("""
    CREATE TABLE IF NOT EXISTS alpha_prime.ironforge.test_close_pattern (
        position_id STRING, status STRING, dte_mode STRING,
        realized_pnl FLOAT, exit_price FLOAT, exit_time TIMESTAMP, close_reason STRING
    )
""")
spark.sql("""
    INSERT INTO alpha_prime.ironforge.test_close_pattern
    VALUES ('TEST-001', 'open', '1dte', 0.0, 0.0, NULL, NULL)
""")

# Simulate close_position() UPDATE pattern
r = spark.sql("""
    UPDATE alpha_prime.ironforge.test_close_pattern
    SET status = 'closed',
        realized_pnl = 50.0,
        exit_price = 1.50,
        exit_time = current_timestamp(),
        close_reason = 'test_validation'
    WHERE position_id = 'TEST-001'
      AND status = 'open'
      AND dte_mode = '1dte'
""")
rows = r.collect()[0][0]
assert rows == 1, f"FAIL: close pattern returned {rows}"

# Simulate DUPLICATE close (race condition scenario)
r2 = spark.sql("""
    UPDATE alpha_prime.ironforge.test_close_pattern
    SET status = 'closed',
        realized_pnl = 50.0,
        exit_price = 1.50,
        exit_time = current_timestamp(),
        close_reason = 'test_validation_duplicate'
    WHERE position_id = 'TEST-001'
      AND status = 'open'
      AND dte_mode = '1dte'
""")
rows2 = r2.collect()[0][0]
assert rows2 == 0, f"FAIL: duplicate close returned {rows2} (should be 0)"

spark.sql("DROP TABLE alpha_prime.ironforge.test_close_pattern")
print("A2: PASS — Delta Lake UPDATE returns correct rows_affected for exact close_position() pattern")
```

**What this proves**: The guard works with the EXACT SQL pattern used in production, not just a simplified version.
**Invariants tested**: INV-1, INV-4, INV-10

#### A3. Collateral Drift — Current State

```sql
-- Check all invariants at once
WITH live_stats AS (
    SELECT
        bot_name,
        SUM(CASE WHEN status = 'closed' THEN realized_pnl ELSE 0 END) as sum_realized_pnl,
        SUM(CASE WHEN status = 'open' THEN collateral_required ELSE 0 END) as sum_open_collateral,
        COUNT(CASE WHEN status = 'open' THEN 1 END) as open_count,
        COUNT(CASE WHEN status = 'open' AND CAST(created_at AS DATE) < CURRENT_DATE() THEN 1 END) as stale_open_count
    FROM alpha_prime.ironforge.positions
    GROUP BY bot_name
),
accounts AS (
    SELECT bot_name, current_balance, collateral_in_use, cumulative_pnl, buying_power, starting_capital
    FROM alpha_prime.ironforge.paper_accounts
    WHERE is_active = TRUE
)
SELECT
    a.bot_name,
    -- INV-1: balance = starting_capital + sum(realized_pnl)
    a.current_balance as stored_balance,
    a.starting_capital + COALESCE(ls.sum_realized_pnl, 0) as calculated_balance,
    a.current_balance - (a.starting_capital + COALESCE(ls.sum_realized_pnl, 0)) as balance_drift,

    -- INV-2: collateral_in_use = sum(open collateral)
    a.collateral_in_use as stored_collateral,
    COALESCE(ls.sum_open_collateral, 0) as calculated_collateral,
    a.collateral_in_use - COALESCE(ls.sum_open_collateral, 0) as collateral_drift,

    -- INV-3: buying_power = balance - collateral
    a.buying_power as stored_bp,
    a.current_balance - a.collateral_in_use as calculated_bp,
    a.buying_power - (a.current_balance - a.collateral_in_use) as bp_drift,

    -- INV-5: no stale open positions
    COALESCE(ls.open_count, 0) as open_positions,
    COALESCE(ls.stale_open_count, 0) as stale_positions,

    -- Verdict
    CASE
        WHEN ABS(a.current_balance - (a.starting_capital + COALESCE(ls.sum_realized_pnl, 0))) > 0.01 THEN 'FAIL: INV-1 balance drift'
        WHEN ABS(a.collateral_in_use - COALESCE(ls.sum_open_collateral, 0)) > 0.01 THEN 'FAIL: INV-2 collateral drift'
        WHEN ABS(a.buying_power - (a.current_balance - a.collateral_in_use)) > 0.01 THEN 'FAIL: INV-3 buying power drift'
        WHEN COALESCE(ls.stale_open_count, 0) > 0 THEN 'FAIL: INV-5 stale open positions'
        ELSE 'PASS: all invariants hold'
    END as verdict
FROM accounts a
LEFT JOIN live_stats ls ON a.bot_name = ls.bot_name
ORDER BY a.bot_name;
```

**What this proves**: All money invariants hold right now.
**Invariants tested**: INV-1, INV-2, INV-3, INV-5

#### A4. P&L Integrity Check

```sql
-- INV-6: Sum of realized_pnl should equal net of entry/exit prices
SELECT
    bot_name,
    SUM(realized_pnl) as sum_pnl,
    SUM((entry_price - exit_price) * contracts * 100) as calculated_pnl_from_prices,
    SUM(realized_pnl) - SUM((entry_price - exit_price) * contracts * 100) as pnl_discrepancy
FROM alpha_prime.ironforge.positions
WHERE status = 'closed'
  AND exit_price IS NOT NULL
  AND contracts IS NOT NULL
GROUP BY bot_name
HAVING ABS(SUM(realized_pnl) - SUM((entry_price - exit_price) * contracts * 100)) > 1.0;
-- If this returns ANY rows, realized_pnl doesn't match the actual trade math
```

**What this proves**: P&L values stored in the DB are mathematically correct, not just internally consistent.
**Invariants tested**: INV-6

#### A5. INFERNO Config Override Check

```sql
-- Check what the ACTUAL effective max_contracts is
SELECT * FROM alpha_prime.ironforge.inferno_config;

-- Also check SPARK and FLAME configs
SELECT * FROM alpha_prime.ironforge.spark_config;
SELECT * FROM alpha_prime.ironforge.flame_config;
```

**What this proves**: Whether the BOT_CONFIG defaults are being overridden by DB values.
**Invariants tested**: INV-15

#### A6. Position-to-Sandbox Reconciliation (FLAME only)

```sql
-- All FLAME positions from last 7 days
-- Cross-reference: does every closed FLAME position have a close_reason?
-- Any position without a close_reason might have been closed incompletely
SELECT
    position_id,
    status,
    close_reason,
    entry_time,
    exit_time,
    collateral_required,
    realized_pnl,
    CASE
        WHEN status = 'closed' AND close_reason IS NULL THEN 'WARNING: closed without reason'
        WHEN status = 'closed' AND exit_time IS NULL THEN 'WARNING: closed without exit_time'
        WHEN status = 'open' THEN 'OPEN — should not exist on weekend'
        ELSE 'OK'
    END as health
FROM alpha_prime.ironforge.positions
WHERE bot_name = 'FLAME'
  AND created_at >= DATEADD(DAY, -7, CURRENT_DATE())
ORDER BY created_at DESC;
```

**Invariants tested**: INV-7, INV-8

---

### Category B: API Layer (Run via curl or browser)

#### B1. Status Endpoint — All Three Bots

```bash
for BOT in SPARK FLAME INFERNO; do
    echo "=== $BOT ==="
    curl -s "https://ironforge-pi.vercel.app/api/$BOT/status" | python3 -m json.tool
    echo ""
done
```

Then compare each response field to the Databricks results from A3.

| Bot | Field | DB Value (A3) | API Value (B1) | Match? |
|-----|-------|--------------|----------------|--------|
| SPARK | balance | | | |
| SPARK | collateral_in_use | | | |
| SPARK | buying_power | | | |
| SPARK | cumulative_pnl | | | |
| FLAME | balance | | | |
| FLAME | collateral_in_use | | | |
| FLAME | buying_power | | | |
| FLAME | cumulative_pnl | | | |
| INFERNO | balance | | | |
| INFERNO | collateral_in_use | | | |
| INFERNO | buying_power | | | |
| INFERNO | cumulative_pnl | | | |

**Invariants tested**: INV-11, INV-12

#### B2. Status Endpoint — Null Handling

```bash
curl -s "https://ironforge-pi.vercel.app/api/SPARK/status" | python3 -c "
import sys, json
data = json.load(sys.stdin)
urpnl = data.get('account', {}).get('unrealized_pnl')
print(f'unrealized_pnl value: {urpnl}')
print(f'unrealized_pnl type: {type(urpnl).__name__}')
if urpnl is None:
    print('PASS: returns null (frontend should show —)')
elif urpnl == 0:
    print('WARNING: returns 0 — is this real zero or masked error?')
else:
    print(f'INFO: returns {urpnl}')
"
```

**Invariants tested**: INV-12

#### B3. Kill Switch Diagnostic

```bash
curl -s "https://ironforge-pi.vercel.app/api/sandbox/emergency-close" | python3 -m json.tool
```

**Invariants tested**: INV-17

#### B4. Cache Busting Verification

```bash
T1=$(curl -s "https://ironforge-pi.vercel.app/api/SPARK/status" | python3 -c "import sys,json; print(json.load(sys.stdin).get('timestamp','none'))")
sleep 2
T2=$(curl -s "https://ironforge-pi.vercel.app/api/SPARK/status" | python3 -c "import sys,json; print(json.load(sys.stdin).get('timestamp','none'))")
echo "Response 1 timestamp: $T1"
echo "Response 2 timestamp: $T2"
if [ "$T1" != "$T2" ]; then
    echo "PASS: Different timestamps — not cached"
else
    echo "FAIL or INCONCLUSIVE: Same timestamp — could be cached or just fast"
fi
```

**Invariants tested**: INV-11, INV-14

#### B5. API Route Headers Check

```bash
for BOT in SPARK FLAME INFERNO; do
    echo "=== $BOT status headers ==="
    curl -sI "https://ironforge-pi.vercel.app/api/$BOT/status" | grep -i "cache-control\|x-vercel-cache\|age:"
done
```

**Invariants tested**: INV-14

---

### Category C: Tradier Sandbox (Run via curl)

#### C1. Account Balances and Positions

```bash
SANDBOX_KEY="YOUR_KEY_HERE"

for ACCT in VA39284047 VA68498498 VA71498282; do
    echo "=== Account: $ACCT ==="

    echo "Balances:"
    curl -s -H "Authorization: Bearer $SANDBOX_KEY" \
        "https://sandbox.tradier.com/v1/accounts/$ACCT/balances" | python3 -c "
import sys, json
data = json.load(sys.stdin)
bal = data.get('balances', {})
print(f'  option_buying_power: {bal.get(\"option_buying_power\", \"N/A\")}')
print(f'  stock_buying_power: {bal.get(\"stock_buying_power\", \"N/A\")}')
print(f'  total_equity: {bal.get(\"total_equity\", \"N/A\")}')
if float(bal.get('option_buying_power', 0)) < 0:
    print('  NEGATIVE BP — FLAME will be blocked')
else:
    print('  BP is positive')
"

    echo "Positions:"
    curl -s -H "Authorization: Bearer $SANDBOX_KEY" \
        "https://sandbox.tradier.com/v1/accounts/$ACCT/positions" | python3 -c "
import sys, json
data = json.load(sys.stdin)
positions = data.get('positions', {})
if positions == 'null' or positions is None or positions == {}:
    print('  No open positions')
else:
    pos_list = positions.get('position', [])
    if not isinstance(pos_list, list):
        pos_list = [pos_list]
    print(f'  {len(pos_list)} positions open')
    for p in pos_list:
        print(f'    {p.get(\"symbol\", \"?\")} qty={p.get(\"quantity\", \"?\")} cost={p.get(\"cost_basis\", \"?\")}')
"
    echo ""
done
```

**Invariants tested**: INV-7, INV-8, INV-9

---

### Category D: Frontend (Manual Browser Tests)

#### D1. Dashboard vs API Comparison

1. Open FLAME dashboard in browser
2. Open DevTools → Network tab → filter by "status"
3. Find the `/api/FLAME/status` request
4. Click on it → Response tab
5. Compare EVERY number:

| Dashboard Label | Dashboard Shows | API Response Field | API Value | Match? |
|----------------|----------------|-------------------|-----------|--------|
| Balance | | account.balance | | |
| Realized PnL | | account.cumulative_pnl | | |
| Unrealized PnL | | account.unrealized_pnl | | |
| Total PnL | | (computed: realized + unrealized) | | |
| Open | | account.open_positions | | |
| Total Trades | | account.total_trades | | |
| Collateral | | account.collateral_in_use | | |
| Buying Power | | account.buying_power | | |

Repeat for SPARK and INFERNO.

#### D2. Scanning Badge Test
#### D3. Null Display Test
#### D4. Kill Switch Button Visibility
#### D5. Force Close Accessibility

---

### Category E: End-to-End Wiring Tests

#### E1. Full Trade Lifecycle — Open to Close

Run Monday morning with first real trade. Steps 1 and 5 can be run now as baseline.

| Checkpoint | DB Value | API Value | Dashboard Value | All Match? |
|-----------|----------|-----------|-----------------|------------|
| BEFORE: balance | | | | |
| BEFORE: collateral | | | | |
| BEFORE: buying_power | | | | |
| BEFORE: open_count | | | | |
| AFTER OPEN: balance | | | | |
| AFTER OPEN: collateral | | | | |
| AFTER OPEN: buying_power | | | | |
| AFTER OPEN: open_count | | | | |
| AFTER CLOSE: balance | | | | |
| AFTER CLOSE: collateral | | | | |
| AFTER CLOSE: buying_power | | | | |
| AFTER CLOSE: open_count | | | | |
| AFTER CLOSE: realized_pnl | | | | |

#### E2. Double-Close Race Condition Simulation

```python
# Setup
spark.sql("""
    INSERT INTO alpha_prime.ironforge.test_close_pattern
    VALUES ('RACE-TEST-001', 'open', '1dte', 0.0, 0.0, NULL, NULL)
""")

# Process A (scanner) closes first
r_a = spark.sql("""
    UPDATE alpha_prime.ironforge.test_close_pattern
    SET status='closed', realized_pnl=50.0, close_reason='scanner_eod'
    WHERE position_id='RACE-TEST-001' AND status='open' AND dte_mode='1dte'
""")
rows_a = r_a.collect()[0][0]

# Process B (position_monitor) tries same position
r_b = spark.sql("""
    UPDATE alpha_prime.ironforge.test_close_pattern
    SET status='closed', realized_pnl=50.0, close_reason='monitor_stop_loss'
    WHERE position_id='RACE-TEST-001' AND status='open' AND dte_mode='1dte'
""")
rows_b = r_b.collect()[0][0]

# VERDICT:
# A=1, B=0: PASS — guard works
# A=1, B=1: FAIL — Delta Lake concurrent UPDATE is NOT atomic
# Both=0: FAIL — neither updates

spark.sql("DELETE FROM alpha_prime.ironforge.test_close_pattern WHERE position_id='RACE-TEST-001'")
```

**Note**: This test is SEQUENTIAL, not truly concurrent. A true concurrent test requires two simultaneous Databricks jobs. If E2 passes sequentially but fails concurrently, the architecture needs optimistic locking (version column).

#### E3–E7: See full test procedures in source document.

---

### Category F: Architecture Verification (Code + Config Audit)

#### F1. All Close Paths Use Same Function
#### F2. Error Handling Architecture
#### F3. Data Flow Architecture Map
#### F4. Single Writer Verification
#### F5. Configuration Consistency
#### F6. Deployment Pipeline Verification

See full audit procedures in the framework source.

---

## SECTION 3: ACCOUNTABILITY FRAMEWORK FOR CLAUDE CODE

### Rule 1: No "Done" Without Evidence
Every fix must provide: WHAT (files + lines), TEST (output), INVARIANTS (preserved), RISKS (remaining).

### Rule 2: Confidence Levels Are Earned
- 90-100%: Test executed, correct results, edge cases covered
- 70-89%: Test executed, correct results, some edge cases not covered
- 50-69%: Code review only — logic traced, never executed
- 30-49%: Code written but not reviewed against real data
- 0-29%: Claimed done but no evidence

**Code review alone caps at 69%.**

### Rule 3: Build Before Push
`cd ironforge/webapp && npm run build` before every TypeScript commit.

### Rule 4: Regression Check on Every Change
Run A3 invariant query, hit status endpoint, trace close paths.

### Rule 5: Honest Status Reporting
Never say "fixed" when untested. Never round up confidence. Show FULL output.

### Rule 6: Session Handoff
Every session ends with: Completed (with evidence), Incomplete, Untested, Known Risks, Next Session priorities.

---

## SECTION 4: CONFIDENCE REPORT TEMPLATE

```
============================================================
IRONFORGE CONFIDENCE REPORT — [DATE]
============================================================

INVARIANT STATUS:
  INV-1  (balance = starting + sum_pnl):     [PASS/FAIL] — Test A3 result
  INV-2  (collateral = sum open):             [PASS/FAIL] — Test A3 result
  INV-3  (buying_power = bal - coll):         [PASS/FAIL] — Test A3 result
  INV-4  (closed pos no collateral):          [PASS/FAIL] — Test A3 result
  INV-5  (no stale open positions):           [PASS/FAIL] — Test A3 result
  INV-6  (pnl matches trade math):            [PASS/FAIL] — Test A4 result
  INV-7  (db pos → sandbox pos):              [PASS/FAIL] — Test A6/C1
  INV-8  (db close → sandbox close):          [PASS/FAIL] — Test A6/C1
  INV-9  (failed close → retry + log):        [TESTED/CODE REVIEW/NOT TESTED]
  INV-10 (atomic close + collateral):         [PASS/FAIL] — Test A1/A2
  INV-11 (data freshness < 15s):              [PASS/FAIL] — Test B4
  INV-12 (no false $0 on error):              [PASS/FAIL] — Test B2/D3
  INV-13 (scanning badge accurate):           [PASS/FAIL] — Test D2
  INV-14 (no-cache on financial routes):      [PASS/FAIL] — Test B5
  INV-15 (max_contracts enforced):            [PASS/FAIL] — Test A5
  INV-16 (WP < 0.50 gate):                   [TESTED/CODE REVIEW/NOT TESTED]
  INV-17 (kill switch accessible):            [PASS/FAIL] — Test B3/D4
  INV-18 (API errors logged):                 [TESTED/CODE REVIEW/NOT TESTED]

OVERALL CONFIDENCE: [X%]
TESTED: [Y/10]  |  CODE REVIEW ONLY: [Z/10]  |  NOT TESTED: [W/10]

GO / NO-GO: [GO / CONDITIONAL GO / NO-GO]
BLOCKERS: [List items that must be resolved before market open]
MONITORING PLAN: [What to watch during first hour of trading]
============================================================
```

---

*Created: 2026-03-14*
*Purpose: IronForge system validation and Claude Code accountability*
