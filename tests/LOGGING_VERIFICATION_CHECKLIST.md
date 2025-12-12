# Logging System Verification Checklist

Generated: 2025-12-12
Status: **IN PROGRESS - NOT ALL ITEMS VERIFIED**

## How To Verify Each Item

For each item below, run the verification command. If it passes, check it off.
If it fails, the work is NOT complete.

---

## SECTION 1: Database Schema (50+ fields)

### Verification Command:
```bash
PYTHONPATH=/home/user/AlphaGEX python -c "
from database_adapter import get_connection
conn = get_connection()
c = conn.cursor()
c.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name = 'bot_decision_logs' ORDER BY ordinal_position\")
columns = [row[0] for row in c.fetchall()]
print(f'Total columns: {len(columns)}')
for col in columns:
    print(f'  - {col}')
conn.close()
"
```

### Required Columns (check each exists):
- [ ] decision_id
- [ ] bot_name
- [ ] session_id
- [ ] scan_cycle
- [ ] decision_sequence
- [ ] timestamp
- [ ] decision_type
- [ ] action
- [ ] symbol
- [ ] strategy
- [ ] strike
- [ ] expiration
- [ ] option_type
- [ ] contracts
- [ ] spot_price
- [ ] vix
- [ ] net_gex
- [ ] gex_regime
- [ ] flip_point
- [ ] call_wall
- [ ] put_wall
- [ ] trend
- [ ] claude_prompt
- [ ] claude_response
- [ ] claude_model
- [ ] claude_tokens_used
- [ ] claude_response_time_ms
- [ ] langchain_chain
- [ ] ai_confidence
- [ ] ai_warnings
- [ ] entry_reasoning
- [ ] strike_reasoning
- [ ] size_reasoning
- [ ] exit_reasoning
- [ ] alternatives_considered
- [ ] rejection_reasons
- [ ] other_strategies_considered
- [ ] psychology_pattern
- [ ] liberation_setup
- [ ] false_floor_detected
- [ ] forward_magnets
- [ ] kelly_pct
- [ ] position_size_dollars
- [ ] max_risk_dollars
- [ ] backtest_win_rate
- [ ] backtest_expectancy
- [ ] backtest_sharpe
- [ ] risk_checks_performed
- [ ] passed_all_checks
- [ ] blocked_reason
- [ ] order_submitted_at
- [ ] order_filled_at
- [ ] broker_order_id
- [ ] expected_fill_price
- [ ] actual_fill_price
- [ ] slippage_pct
- [ ] broker_status
- [ ] execution_notes
- [ ] actual_pnl
- [ ] exit_triggered_by
- [ ] exit_timestamp
- [ ] exit_price
- [ ] exit_slippage_pct
- [ ] outcome_correct
- [ ] outcome_notes
- [ ] api_calls_made
- [ ] errors_encountered
- [ ] processing_time_ms
- [ ] full_decision

---

## SECTION 2: Data Population Verification

### Test: Insert a test decision and verify ALL fields populated
```bash
PYTHONPATH=/home/user/AlphaGEX python -c "
from trading.bot_logger import *
from datetime import datetime

# Create decision with ALL fields
decision = BotDecision(
    bot_name='TEST',
    decision_type='ENTRY',
    action='BUY',
    symbol='SPY',
    strategy='test_strategy',
    strike=590.0,
    expiration='2025-12-13',
    option_type='CALL',
    contracts=5,
    session_id='2025-12-12-TEST',
    scan_cycle=1,
    decision_sequence=1,
    market_context=MarketContext(
        spot_price=590.50,
        vix=15.5,
        net_gex=1500000000,
        gex_regime='LONG_GAMMA',
        flip_point=588.0,
        call_wall=595.0,
        put_wall=580.0,
        trend='BULLISH'
    ),
    claude_context=ClaudeContext(
        prompt='REAL PROMPT HERE',
        response='REAL RESPONSE HERE',
        model='claude-sonnet-4-5-latest',
        tokens_used=1500,
        response_time_ms=2500,
        chain_name='trade_advisor_chain',
        confidence='HIGH',
        warnings=['Near resistance level']
    ),
    entry_reasoning='REAL entry reasoning',
    strike_reasoning='REAL strike reasoning',
    size_reasoning='REAL size reasoning',
    alternatives_considered=[
        Alternative(strike=595.0, strategy='Higher strike', reason_rejected='REAL reason'),
        Alternative(strike=585.0, strategy='Lower strike', reason_rejected='REAL reason'),
    ],
    other_strategies_considered=['Put spread', 'Iron condor'],
    psychology_pattern='Liberation setup',
    liberation_setup=True,
    false_floor_detected=False,
    kelly_pct=5.0,
    position_size_dollars=2500.0,
    max_risk_dollars=2500.0,
    backtest_win_rate=65.5,
    backtest_expectancy=1.25,
    risk_checks=[
        RiskCheck(check_name='VIX', passed=True, current_value=15.5, limit_value=30.0, message='OK'),
        RiskCheck(check_name='POSITION_SIZE', passed=True, current_value=2500, limit_value=5000, message='OK'),
    ],
    passed_all_checks=True,
    execution=ExecutionTimeline(
        order_submitted_at=datetime.now(),
        order_filled_at=datetime.now(),
        broker_order_id='TEST-12345',
        expected_fill_price=2.50,
        actual_fill_price=2.52,
        broker_status='FILLED',
        execution_notes='Filled at ask'
    ),
    api_calls=[
        ApiCall(api_name='tradier', endpoint='quotes', time_ms=150, success=True),
        ApiCall(api_name='polygon', endpoint='options', time_ms=200, success=True),
    ],
    errors_encountered=[],
    processing_time_ms=500
)

decision_id = log_bot_decision(decision)
print(f'Logged test decision: {decision_id}')

# Now verify it was stored correctly
from database_adapter import get_connection
conn = get_connection()
c = conn.cursor()
c.execute('SELECT * FROM bot_decision_logs WHERE decision_id = %s', (decision_id,))
row = c.fetchone()
if row:
    print('SUCCESS: Decision stored')
    # Check specific fields
    c.execute('SELECT claude_prompt, claude_tokens_used, scan_cycle, actual_fill_price FROM bot_decision_logs WHERE decision_id = %s', (decision_id,))
    data = c.fetchone()
    print(f'  claude_prompt: {data[0][:50] if data[0] else \"EMPTY\"}...')
    print(f'  claude_tokens_used: {data[1]}')
    print(f'  scan_cycle: {data[2]}')
    print(f'  actual_fill_price: {data[3]}')
else:
    print('FAILED: Decision not found')

# Cleanup
c.execute('DELETE FROM bot_decision_logs WHERE decision_id = %s', (decision_id,))
conn.commit()
conn.close()
"
```

### Checklist - Data NOT Fake:
- [ ] claude_prompt contains REAL prompt (not "Oracle advice for...")
- [ ] claude_response contains REAL response (not Oracle reasoning)
- [ ] claude_tokens_used > 0
- [ ] claude_response_time_ms > 0
- [ ] scan_cycle > 0
- [ ] decision_sequence > 0
- [ ] alternatives_considered has REAL alternatives (not "Higher strike", "Lower strike")
- [ ] actual_fill_price populated (not always 0)
- [ ] order_filled_at populated (not NULL)
- [ ] api_calls_made populated (not empty array)
- [ ] processing_time_ms > 0

---

## SECTION 3: Bot Wiring Verification

### ARES - Check it logs REAL data
```bash
grep -n "log_bot_decision" /home/user/AlphaGEX/trading/ares_iron_condor.py | head -10
```
- [ ] ARES calls log_bot_decision() for SKIP decisions
- [ ] ARES calls log_bot_decision() for ENTRY decisions
- [ ] ARES passes scan_cycle (NOT always 0)
- [ ] ARES passes REAL alternatives (NOT hardcoded)

### PHOENIX/ATLAS/HERMES (DecisionBridge)
```bash
grep -n "log_bot_decision" /home/user/AlphaGEX/trading/autonomous_decision_bridge.py | head -10
```
- [ ] DecisionBridge calls log_bot_decision() for ENTRY
- [ ] DecisionBridge calls log_bot_decision() for SKIP
- [ ] DecisionBridge calls log_bot_decision() for EXIT
- [ ] DecisionBridge passes REAL alternatives (NOT hardcoded)

### SPX Wheel (ATLAS)
```bash
grep -n "log_bot_decision" /home/user/AlphaGEX/trading/spx_wheel_system.py | head -10
```
- [ ] SPX Wheel calls log_bot_decision()
- [ ] SPX Wheel passes REAL data

### Oracle
```bash
grep -n "log_bot_decision" /home/user/AlphaGEX/quant/oracle_advisor.py | head -10
```
- [ ] Oracle calls log_bot_decision()

---

## SECTION 4: API Endpoints Verification

### Test each endpoint returns data:
```bash
# Start the API server first, then run:
curl -s http://localhost:8000/api/logs/bot-decisions?limit=5 | python -m json.tool | head -30
curl -s http://localhost:8000/api/logs/bot-decisions/ARES?limit=5 | python -m json.tool | head -30
curl -s http://localhost:8000/api/logs/bot-decisions/stats | python -m json.tool
curl -s "http://localhost:8000/api/logs/bot-decisions/export?format=csv&limit=5"
```

- [ ] GET /api/logs/bot-decisions returns data
- [ ] GET /api/logs/bot-decisions/{bot} filters correctly
- [ ] GET /api/logs/bot-decisions/session/{id} groups by session
- [ ] GET /api/logs/bot-decisions/stats returns aggregated stats
- [ ] GET /api/logs/bot-decisions/export returns CSV
- [ ] GET /api/logs/bot-decisions/export?format=json returns JSON
- [ ] GET /api/logs/bot-decisions/export?format=excel returns Excel

---

## SECTION 5: UI Pages Verification

### Check files exist and have content:
```bash
ls -la /home/user/AlphaGEX/frontend/src/app/*/logs/page.tsx
ls -la /home/user/AlphaGEX/frontend/src/components/logs/
```

- [ ] /ares/logs/page.tsx exists and imports BotLogsPage
- [ ] /atlas/logs/page.tsx exists and imports BotLogsPage
- [ ] /phoenix/logs/page.tsx exists and imports BotLogsPage
- [ ] /hermes/logs/page.tsx exists and imports BotLogsPage
- [ ] /oracle/logs/page.tsx exists and imports BotLogsPage
- [ ] BotLogsPage.tsx is complete
- [ ] ClaudeConversationViewer.tsx is complete
- [ ] ExecutionTimeline.tsx is complete
- [ ] DecisionFilterPanel.tsx is complete

### UI Functional Test (manual):
```bash
cd /home/user/AlphaGEX/frontend && npm run dev
# Then open http://localhost:3000/ares/logs
```

- [ ] Page loads without errors
- [ ] Filter panel works
- [ ] Export buttons work
- [ ] Decision cards expand/collapse
- [ ] Claude viewer shows content
- [ ] Execution timeline renders

---

## SECTION 6: Session Grouping Verification

- [ ] Session grouping UI component exists
- [ ] Decisions can be filtered by session_id
- [ ] scan_cycle is populated for each decision
- [ ] decision_sequence increments within a session

---

## SECTION 7: Real Claude Integration

### Check Claude/LangChain calls are intercepted:
```bash
grep -rn "claude_prompt\|claude_response\|tokens_used" /home/user/AlphaGEX/ai/ | head -20
```

- [ ] AI advisor code captures actual prompt before sending
- [ ] AI advisor code captures actual response after receiving
- [ ] Token count is captured from API response
- [ ] Response time is measured

---

## FINAL VERIFICATION

Run this command to get a summary:
```bash
PYTHONPATH=/home/user/AlphaGEX python -c "
from database_adapter import get_connection
conn = get_connection()
c = conn.cursor()

# Count records
c.execute('SELECT COUNT(*) FROM bot_decision_logs')
total = c.fetchone()[0]

# Count by bot
c.execute('SELECT bot_name, COUNT(*) FROM bot_decision_logs GROUP BY bot_name')
by_bot = c.fetchall()

# Check for fake data
c.execute(\"SELECT COUNT(*) FROM bot_decision_logs WHERE claude_prompt LIKE '%Oracle advice%'\")
fake_prompts = c.fetchone()[0]

c.execute('SELECT COUNT(*) FROM bot_decision_logs WHERE scan_cycle = 0 OR scan_cycle IS NULL')
missing_scan_cycle = c.fetchone()[0]

c.execute('SELECT COUNT(*) FROM bot_decision_logs WHERE claude_tokens_used = 0 OR claude_tokens_used IS NULL')
missing_tokens = c.fetchone()[0]

print(f'Total records: {total}')
print(f'By bot: {by_bot}')
print(f'')
print(f'FAKE DATA CHECKS:')
print(f'  Records with fake claude_prompt: {fake_prompts} (should be 0)')
print(f'  Records with missing scan_cycle: {missing_scan_cycle} (should be 0)')
print(f'  Records with missing claude_tokens: {missing_tokens} (should be 0 for AI decisions)')
conn.close()
"
```

**ALL CHECKS MUST PASS FOR WORK TO BE CONSIDERED COMPLETE**

---

## Sign-off

| Item | Claude Claims Done | User Verified | Date |
|------|-------------------|---------------|------|
| Schema complete | YES | [ ] | |
| Data not fake | NO | [ ] | |
| All bots wired | YES (partial) | [ ] | |
| API working | NOT TESTED | [ ] | |
| UI working | NOT TESTED | [ ] | |
| Session grouping | NO | [ ] | |
| Real Claude capture | NO | [ ] | |

