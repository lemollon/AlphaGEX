# Bot Development Standards

## Production-Ready Implementation
When implementing features, **always deliver production-ready, end-to-end implementations**:

1. **Don't just write scaffolding** - Wire it up to actually run in production
2. **Complete the full loop**: Database schema → Backend logic → API endpoint → Frontend display
3. **If adding data fields**, integrate them into the code that populates them
4. **If adding UI components**, ensure the backend sends the data they need
5. **If adding new analysis systems**, integrate them into the bots that use them

**Example**: If asked to "add ML analysis to scan activity":
- BAD: Add database columns and UI components, but leave bots unchanged
- GOOD: Add columns, update bots to call ML systems, pass data to logger, display in UI

### Trigger Phrases
When the user says any of these, ensure full end-to-end implementation:
- "make it production-ready"
- "implement end-to-end"
- "wire it up"
- "make it actually work"
- "activate it"

---

## Bot Completeness Requirements

**CRITICAL: Each trading bot is an independent system.** When fixing issues or adding features to ANY bot, treat it as a complete web application that must work end-to-end:

**Each bot (FORTRESS, SAMSON, ANCHOR, SOLOMON, GIDEON, VALOR, FAITH, GRACE) MUST have:**

1. **Historical Equity Curve** (`/equity-curve`)
   - Query ALL closed trades (no date filter on SQL - filter output only)
   - Cumulative P&L = running sum of all realized_pnl
   - Equity = starting_capital + cumulative_pnl
   - starting_capital from config table (NOT hardcoded)

2. **Intraday Equity Curve** (`/equity-curve/intraday`)
   - Read from `{bot}_equity_snapshots` table
   - Include unrealized P&L from open positions
   - Market open equity = starting_capital + previous_day_cumulative_pnl

3. **Position Management**
   - `close_position()` must set: `close_time = NOW()`, `realized_pnl`
   - `expire_position()` must exist and set same fields
   - All position status changes must update `close_time`

4. **Data Consistency**
   - Same starting_capital lookup in ALL endpoints (config table)
   - Same P&L formula everywhere: `(close_price - entry_price) * contracts * 100`
   - Timezone handling: `::timestamptz AT TIME ZONE 'America/Chicago'`

**When fixing ONE bot, check ALL bots for the same issue.** Don't fix FORTRESS and leave SAMSON broken.

**Common Bot Endpoints to Verify:**
| Endpoint | Purpose | Key Checks |
|----------|---------|------------|
| `/status` | Bot health | Config loaded, positions counted |
| `/positions` | Open positions | All fields populated |
| `/equity-curve` | Historical P&L | Cumulative math correct |
| `/equity-curve/intraday` | Today's P&L | Snapshots being saved |
| `/performance` | Statistics | Win rate, total P&L accurate |
| `/logs` | Activity log | Actions being logged |
| `/scan-activity` | Scan history | Scans recorded |
