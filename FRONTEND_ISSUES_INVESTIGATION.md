# Frontend Issues Investigation & Fixes

## Issues Identified

### 1. ⏰ 0DTE Data Shows Stale Week (Nov 3-7, but today is Nov 10)

**Location**: `/home/user/AlphaGEX/frontend/src/app/gamma/0dte/page.tsx:167`

**Problem**:
```tsx
<span>Week of 2025-11-03 to 2025-11-07</span>
```
Hardcoded date range - doesn't update with current week.

**Root Cause**: Static text instead of dynamic calculation.

**Fix**: Calculate current week dynamically in JavaScript
```tsx
// Add helper function at top of component:
const getCurrentWeekRange = () => {
  const today = new Date()
  const dayOfWeek = today.getDay() // 0 = Sunday, 1 = Monday, etc.

  // Calculate Monday of current week
  const monday = new Date(today)
  monday.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))

  // Calculate Friday of current week
  const friday = new Date(monday)
  friday.setDate(monday.getDate() + 4)

  const formatDate = (date: Date) => {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  return `${formatDate(monday)} to ${formatDate(friday)}`
}

// Then replace line 167 with:
<span>Week of {getCurrentWeekRange()}</span>
```

---

### 2. 📊 GEX Profile Chart Doesn't Load on Daily Analysis Page

**Location**: `/home/user/AlphaGEX/frontend/src/app/gex/page.tsx:515-520`

**Problem**: Chart is rendered but hidden by default because `expandedTickers` starts as empty Set.

**Root Cause**:
- Line 91: `const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set())`
- Chart only renders when ticker is expanded
- No clear indication to users they need to expand to see chart

**The Chart Code (works fine when expanded)**:
```tsx
{isExpanded && gexLevels[ticker] && (
  <div className="mt-6">
    <h3 className="text-lg font-semibold text-text-primary mb-4 flex items-center gap-2">
      <BarChart3 className="w-5 h-5" />
      GEX Profile by Strike
    </h3>
    <GEXProfileChart
      data={gexLevels[ticker]}
      spotPrice={data.spot_price}
      flipPoint={data.flip_point}
      callWall={data.call_wall}
      putWall={data.put_wall}
    />
  </div>
)}
```

**Fix Options**:

**Option A: Auto-expand SPY on load** (Recommended)
```tsx
// Change line 91 from:
const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set())

// To:
const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set(['SPY']))
```

**Option B: Make expand button more prominent**
```tsx
// Add visual cue next to ticker name:
<button
  onClick={() => toggleExpanded(ticker)}
  className="flex items-center gap-2 text-primary hover:text-primary/80 transition-all"
>
  {isExpanded ? (
    <>
      <ChevronUp className="w-5 h-5" />
      <span className="text-sm font-medium">Hide GEX Chart</span>
    </>
  ) : (
    <>
      <ChevronDown className="w-5 h-5" />
      <span className="text-sm font-medium">Show GEX Chart ⬇️</span>
    </>
  )}
</button>
```

**Option C: Add "Expand All" button**
```tsx
// Add button near header:
<button
  onClick={() => setExpandedTickers(new Set(tickers))}
  className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/80"
>
  Show All GEX Charts
</button>
```

**Recommended**: Combine Option A (SPY auto-expands) + Option B (clearer expand button)

---

### 3. 🎀 Navigation Ribbon Overlays Page Titles

**Location**: Multiple pages

**Problem**:
- Navigation bar is fixed at top with `z-50` and `h-16` (64px height)
- GEX page has correct padding: `pt-16` (line 321)
- Psychology page is MISSING padding: starts with `container mx-auto` without `pt-16` (line 235)
- Result: Page title gets hidden under navigation bar

**Files Affected**:
- ✅ `/frontend/src/app/gex/page.tsx:321` - HAS `pt-16` (works)
- ❌ `/frontend/src/app/psychology/page.tsx:235` - MISSING `pt-16` (broken)
- Need to check: All other pages

**Fix for Psychology Page**:
```tsx
// Line 235, change from:
<div className="container mx-auto px-4 py-8 space-y-6">

// To:
<div className="pt-16 transition-all duration-300">
  <div className="container mx-auto px-4 py-8 space-y-6">
```

**Pattern to Apply to ALL Pages**:
```tsx
<div className="min-h-screen">
  <Navigation />

  <main className="pt-16 transition-all duration-300">  {/* <-- CRITICAL */}
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Page content */}
    </div>
  </main>
</div>
```

**Pages to Check/Fix**:
1. ❌ `/app/psychology/page.tsx` - NEEDS FIX
2. ✅ `/app/gex/page.tsx` - Already correct
3. ? `/app/gamma/page.tsx` - CHECK
4. ? `/app/gamma/0dte/page.tsx` - CHECK
5. ? `/app/strategies/page.tsx` - CHECK
6. ? `/app/scanner/page.tsx` - CHECK
7. ? All other pages - CHECK

---

### 4. 📅 Market Psychology Page Has No Date/Recency

**Location**: `/home/user/AlphaGEX/frontend/src/app/psychology/page.tsx`

**Problem**:
- API returns `timestamp` in `analysis.timestamp` (line 50)
- But timestamp is never displayed to user
- Users don't know if data is fresh or stale

**Data Available**:
```tsx
interface RegimeAnalysis {
  timestamp: string  // <-- THIS EXISTS but not displayed
  spy_price: number
  regime: { ... }
  // ...
}
```

**Fix**: Add timestamp display to header

**Option A: Add to page header** (Recommended)
```tsx
{/* Line ~237 - Update header section */}
<div className="flex items-center justify-between">
  <div className="space-y-1">
    <div className="flex items-center gap-2">
      <Brain className="w-8 h-8 text-purple-400" />
      <h1 className="text-3xl font-bold">Psychology Trap Detection</h1>
    </div>
    <div className="flex items-center gap-3">
      <p className="text-gray-400">
        Identify when retail traders get trapped by ignoring market structure
      </p>
      {analysis?.timestamp && (
        <>
          <span className="text-gray-600">|</span>
          <div className="flex items-center gap-1 text-sm text-gray-500">
            <Clock className="w-4 h-4" />
            <span>Updated: {new Date(analysis.timestamp).toLocaleString()}</span>
          </div>
        </>
      )}
    </div>
  </div>
  {/* ... refresh button ... */}
</div>
```

**Option B: Add as status badge**
```tsx
{/* Add near top of analysis section */}
{analysis && (
  <div className="flex items-center justify-between mb-4">
    <div className="flex items-center gap-2 text-sm text-gray-400">
      <Clock className="w-4 h-4" />
      <span>Data as of: {new Date(analysis.timestamp).toLocaleString()}</span>
      <span className="text-gray-600">|</span>
      <span>SPY: ${analysis.spy_price.toFixed(2)}</span>
    </div>
  </div>
)}
```

**Option C: Add to each card** (Most visible)
```tsx
{/* Line ~299 - Inside main regime card */}
<div className="bg-gradient-to-br from-gray-900 to-gray-800 border-2 border-purple-500/30 rounded-xl p-6 space-y-4">
  <div className="flex items-center justify-between mb-2">
    <div className="text-2xl font-bold text-purple-400">
      {analysis.regime.primary_type}
    </div>
    <div className="flex items-center gap-2 text-sm text-gray-400 bg-gray-800/50 px-3 py-1 rounded-lg">
      <Clock className="w-4 h-4" />
      <span>{new Date(analysis.timestamp).toLocaleString()}</span>
    </div>
  </div>
  {/* ... rest of card ... */}
</div>
```

**Recommended**: Option C (most visible) + Option B (summary at top)

---

## Implementation Priority

### Critical (Do First):
1. ✅ Fix 0DTE hardcoded date → Users see stale week
2. ✅ Fix ribbon overlay → Page titles hidden
3. ✅ Add Psychology timestamp → Users don't know data freshness

### High (Do Soon):
4. ✅ Fix GEX chart visibility → Chart works but users can't see it

### Format for Timestamp Display

**Current Time Display**:
```tsx
new Date(analysis.timestamp).toLocaleString()
// Example: "11/10/2025, 2:15:30 PM"
```

**Better Format** (more readable):
```tsx
const formatTimestamp = (timestamp: string) => {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = Math.floor((now.getTime() - date.getTime()) / 1000) // seconds

  if (diff < 60) return `${diff} seconds ago`
  if (diff < 3600) return `${Math.floor(diff / 60)} minutes ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`

  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  })
}

// Usage:
<span>{formatTimestamp(analysis.timestamp)}</span>
// Examples:
// "45 seconds ago"
// "5 minutes ago"
// "Nov 10, 2:15 PM"
```

---

## Testing Checklist

After fixes:

**0DTE Page**:
- [ ] Week range shows current week (Nov 10-14, not Nov 3-7)
- [ ] Week range updates on Monday
- [ ] "Today" shows correct day name

**GEX Analysis Page**:
- [ ] SPY chart auto-expands on page load
- [ ] Expand/collapse button is clearly visible
- [ ] Chart renders when expanded
- [ ] Chart shows correct strike data

**Psychology Page**:
- [ ] Page title visible (not hidden under nav bar)
- [ ] Timestamp displays correctly
- [ ] Timestamp shows "X minutes ago" for recent data
- [ ] Timestamp updates after refresh

**All Pages**:
- [ ] No page titles hidden under navigation
- [ ] Consistent padding (pt-16) after nav bar
- [ ] Smooth transitions
- [ ] Mobile responsive

---

## Files to Modify

1. `/frontend/src/app/gamma/0dte/page.tsx` - Fix hardcoded date
2. `/frontend/src/app/gex/page.tsx` - Auto-expand SPY, improve button
3. `/frontend/src/app/psychology/page.tsx` - Fix padding, add timestamp
4. Check all other `/frontend/src/app/*/page.tsx` - Verify pt-16 padding

---

## Summary

| Issue | Impact | Fix Complexity | Priority |
|-------|--------|----------------|----------|
| 0DTE stale date | Users see old week | Easy (5 min) | Critical |
| GEX chart hidden | Feature invisible | Easy (2 min) | High |
| Ribbon overlay | Titles unreadable | Easy (10 min) | Critical |
| No timestamp | Unknown data age | Easy (10 min) | Critical |

**Total Time to Fix**: ~30 minutes

All fixes are simple CSS/JS changes - no API or backend changes needed.
