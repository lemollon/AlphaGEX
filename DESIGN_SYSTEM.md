# 🎨 AlphaGEX Design System & Wireframes

**Professional Trading Terminal UI/UX Design**

---

## Table of Contents
1. [Design Philosophy](#design-philosophy)
2. [Design System](#design-system)
3. [Information Architecture](#information-architecture)
4. [Page Wireframes](#page-wireframes)
5. [Component Library](#component-library)
6. [Interactions & Animations](#interactions--animations)
7. [Responsive Design](#responsive-design)

---

## Design Philosophy

### Vision Statement
**"Professional trading terminal that combines TradingView's chart excellence with Unusual Whales' clean interface"**

### Core Principles
1. **Data First** - Information hierarchy optimized for quick scanning
2. **Dark Mode Native** - Easy on eyes during long trading sessions
3. **Real-Time Feel** - Updates without page reload, smooth transitions
4. **Progressive Disclosure** - Show most important info first, details on demand
5. **Professional Polish** - Looks like $10k/month Bloomberg Terminal, not a POC

### Design Inspiration
- **TradingView:** Chart quality, interactive elements
- **Unusual Whales:** Card layouts, modern feel
- **Bloomberg Terminal:** Data density, seriousness
- **Robinhood:** Simplicity, smooth animations

---

## Design System

### 🎨 Color Palette

#### Primary Colors (Dark Mode)
```
Background Layers:
├─ Deep Background:  #0a0e1a  (Darkest - page background)
├─ Card Background:  #141824  (Cards, panels)
└─ Hover/Active:     #1a1f2e  (Interactive elements)

Accent Colors:
├─ Primary Blue:     #3b82f6  (Links, CTAs, focus states)
├─ Success Green:    #10b981  (Positive P&L, calls, bullish)
├─ Danger Red:       #ef4444  (Negative P&L, puts, bearish)
├─ Warning Amber:    #f59e0b  (Alerts, caution states)
└─ Info Purple:      #8b5cf6  (AI features, special states)

Text Colors:
├─ Primary Text:     #f3f4f6  (Headlines, important)
├─ Secondary Text:   #9ca3af  (Body text, labels)
├─ Muted Text:       #6b7280  (Captions, disabled)
└─ Inverted Text:    #0a0e1a  (Text on light backgrounds)

Chart Colors:
├─ Gamma Positive:   #10b981  (Positive GEX)
├─ Gamma Negative:   #ef4444  (Negative GEX)
├─ Flip Point:       #f59e0b  (Key level line)
├─ Call Wall:        #3b82f6  (Resistance)
└─ Put Wall:         #8b5cf6  (Support)
```

#### Gradients (For cards, headers, highlights)
```
Hero Gradient:       linear-gradient(135deg, #667eea 0%, #764ba2 100%)
Success Gradient:    linear-gradient(135deg, #10b981 0%, #059669 100%)
Danger Gradient:     linear-gradient(135deg, #ef4444 0%, #dc2626 100%)
Neutral Gradient:    linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)
```

### 📝 Typography

#### Font Family
```
Primary Font:        'Inter', system-ui, -apple-system, sans-serif
Monospace Font:      'JetBrains Mono', 'Fira Code', monospace (for numbers)
```

#### Font Scales
```
Display Large:       48px / 3rem    (Hero text)
Display Medium:      36px / 2.25rem (Page titles)
Heading 1:           30px / 1.875rem
Heading 2:           24px / 1.5rem
Heading 3:           20px / 1.25rem
Body Large:          18px / 1.125rem
Body:                16px / 1rem
Body Small:          14px / 0.875rem
Caption:             12px / 0.75rem
Micro:               10px / 0.625rem (Chart labels)
```

#### Font Weights
```
Light:     300  (Rarely used)
Regular:   400  (Body text)
Medium:    500  (Emphasis, labels)
Semibold:  600  (Headings, buttons)
Bold:      700  (Strong emphasis)
```

### 📏 Spacing System

#### Base Unit: 4px
```
Space Scale:
├─ xs:   4px   (0.25rem)  - Tight padding, icon spacing
├─ sm:   8px   (0.5rem)   - Small gaps
├─ md:   16px  (1rem)     - Default spacing
├─ lg:   24px  (1.5rem)   - Section spacing
├─ xl:   32px  (2rem)     - Large gaps
├─ 2xl:  48px  (3rem)     - Page section breaks
└─ 3xl:  64px  (4rem)     - Major divisions
```

### 🎯 Border Radius
```
None:    0px      (Tables, tight layouts)
Small:   4px      (Buttons, inputs)
Medium:  8px      (Cards, panels)
Large:   12px     (Modals, large cards)
XLarge:  16px     (Feature cards)
Round:   9999px   (Badges, pills)
```

### 🌫️ Shadows & Elevation
```
Level 0 (Flat):      none
Level 1 (Subtle):    0 1px 3px rgba(0,0,0,0.3)
Level 2 (Card):      0 4px 6px rgba(0,0,0,0.4)
Level 3 (Elevated):  0 10px 15px rgba(0,0,0,0.5)
Level 4 (Modal):     0 20px 25px rgba(0,0,0,0.6)
Level 5 (Peak):      0 25px 50px rgba(0,0,0,0.7)

Glow Effects (Hover states):
├─ Blue Glow:    0 0 20px rgba(59,130,246,0.3)
├─ Green Glow:   0 0 20px rgba(16,185,129,0.3)
└─ Red Glow:     0 0 20px rgba(239,68,68,0.3)
```

---

## Information Architecture

### Navigation Structure
```
Top Navigation (Horizontal Tabs)
├─── Dashboard (Home)
├─── GEX Analysis
├─── Gamma Intelligence
├─── AI Copilot
├─── Autonomous Trader
└─── More ▾
     ├─── Multi-Symbol Scanner
     ├─── Position Tracking
     ├─── Trade Journal
     ├─── Alerts System
     ├─── Position Sizer
     └─── Settings
```

### Page Hierarchy
```
Level 1: Dashboard - Most important, landing page
Level 2: Core Tools - GEX, Gamma, AI, Trader (Equal importance)
Level 3: Support Tools - Scanner, Tracking, Journal, etc.
```

---

## Page Wireframes

### 🏠 **Page 1: Dashboard (Home)**

**Purpose:** Quick overview of market + your positions

**Layout:**
```
┌────────────────────────────────────────────────────────────────────────┐
│  🎯 AlphaGEX    [Dashboard][GEX][Gamma][AI][Trader][More▾]   @username│
│                                      SPY: $580.25 ▲ | Market: 🟢 Open  │
└────────────────────────────────────────────────────────────────────────┘

┌─────────────┬─────────────┬─────────────┬─────────────┬─────────────┐
│ 📊 SPY GEX  │ 🔄 Net Gamma│ ⚡ Flip Point│ 🎯 MM State │ 📈 Win Rate │
│             │             │             │             │             │
│   -$1.2B    │   -2.1B     │   $582.50   │  SQUEEZE    │    62%      │
│   ↓ 15%     │   Negative  │   ↑ $2.50   │  Bullish    │  18 / 29    │
└─────────────┴─────────────┴─────────────┴─────────────┴─────────────┘

┌─────────────────────────────────────────┬───────────────────────────┐
│  📈 Market Overview (Big Chart)         │  💼 Active Positions (3)  │
│  ┌───────────────────────────────────┐  │  ┌─────────────────────┐  │
│  │  TradingView-style Chart         │  │  │ SPY 580C          ↗ │  │
│  │  - GEX levels overlaid           │  │  │ Entry: $4.20        │  │
│  │  - Flip point line               │  │  │ Current: $5.80      │  │
│  │  - Call/Put walls                │  │  │ P&L: +$160 (+38%)   │  │
│  │  - Real-time updates             │  │  │ [Close Position]    │  │
│  │  - Interactive zoom/pan          │  │  └─────────────────────┘  │
│  └───────────────────────────────────┘  │  ┌─────────────────────┐  │
│                                          │  │ QQQ 390P          ↘ │  │
│  Today's Recommendation (from AI):       │  │ Entry: $2.10        │  │
│  🤖 "Negative GEX squeeze setup          │  │ Current: $1.85      │  │
│      forming. Consider SPY 585C          │  │ P&L: -$25 (-12%)    │  │
│      for momentum play."                 │  │ [Close Position]    │  │
│                                          │  └─────────────────────┘  │
└─────────────────────────────────────────┴───────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│  ⚡ Quick Actions                                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 🤖 Ask AI│ │ 📊 Scan  │ │ 💰 Size  │ │ 🔔 Alerts│ │ ⚙️ Config│   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
└────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────┬──────────────────────────────────┐
│  📅 Today's Trade Log (3 trades)    │  📊 Performance (Last 30 Days)   │
│  ┌───────────────────────────────┐  │  ┌──────────────────────────────┐│
│  │ 09:45 AM - Opened SPY 580C    │  │  │ Equity Curve Chart          │││
│  │ 10:23 AM - Closed QQQ 385P    │  │  │ $5,000 → $5,420 (+8.4%)     │││
│  │ 11:02 AM - Opened AAPL 185C   │  │  │                             │││
│  └───────────────────────────────┘  │  └──────────────────────────────┘│
└─────────────────────────────────────┴──────────────────────────────────┘
```

**Components Used:**
- Status cards (5 metric boxes at top)
- Large interactive chart (main focus)
- Position cards (right panel)
- Quick action buttons
- Activity timeline
- Performance mini-chart

---

### 📊 **Page 2: GEX Analysis**

**Purpose:** Deep dive into Gamma Exposure for any symbol

**Layout:**
```
┌────────────────────────────────────────────────────────────────────────┐
│  🎯 AlphaGEX    [Dashboard][GEX][Gamma][AI][Trader][More▾]   @username│
└────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────┬──────────────────────────────────────────────┐
│  🔍 Symbol Search       │  📊 GEX Chart (Full Width)                   │
│  ┌───────────────────┐  │  ┌────────────────────────────────────────┐ │
│  │ [SPY         🔍]  │  │  │  Price: $580.25                        │ │
│  │                   │  │  │  Net GEX: -$1.2B (Negative)            │ │
│  │ Quick Select:     │  │  │  ┌──────────────────────────────────┐ │ │
│  │ • SPY             │  │  │  │ TradingView Chart with:          │ │ │
│  │ • QQQ             │  │  │  │ - Price candlesticks             │ │ │
│  │ • AAPL            │  │  │  │ - Flip point line (yellow)       │ │ │
│  │ • TSLA            │  │  │  │ - Call wall (blue)               │ │ │
│  │ • Custom...       │  │  │  │ - Put wall (purple)              │ │ │
│  └───────────────────┘  │  │  │ - GEX heatmap below             │ │ │
│                         │  │  │ - Interactive zoom/pan           │ │ │
│  📈 Key Metrics         │  │  │ - Real-time updates (30s)        │ │ │
│  ┌───────────────────┐  │  │  └──────────────────────────────────┘ │ │
│  │ Net GEX: -$1.2B  │  │  │                                          │ │
│  │ Flip: $582.50    │  │  │  Time Range: [1D][5D][1M][3M][1Y][All]  │ │
│  │ Call Wall: $590  │  │  │  Indicators: [GEX][Flip][Walls][Volume] │ │
│  │ Put Wall: $570   │  │  └────────────────────────────────────────┘ │
│  │ Spot: $580.25    │  │                                              │
│  └───────────────────┘  │  🎯 Market Maker State                      │
│                         │  ┌────────────────────────────────────────┐ │
│  🎨 GEX Distribution    │  │ Current State: SQUEEZE                 │ │
│  ┌───────────────────┐  │  │                                        │ │
│  │ [Mini Chart]      │  │  │ Dealers are SHORT gamma                │ │
│  │ Strike vs GEX     │  │  │ Price below flip = Forced buying       │ │
│  │ Bar chart         │  │  │                                        │ │
│  └───────────────────┘  │  │ Trade Idea:                            │ │
│                         │  │ "BUY CALLS on break above $582.50"    │ │
│  ⏱️ Last Updated        │  │ Target: $590 (Call Wall)               │ │
│  Just now (Live)        │  │ Stop: $575 (Risk -1.5%)                │ │
│                         │  │                                        │ │
│                         │  │ [📋 Copy Trade] [💬 Ask AI About This]│ │
│                         │  └────────────────────────────────────────┘ │
└─────────────────────────┴──────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│  📊 GEX Level Breakdown (Table)                                        │
│  ┌──────────┬────────────┬───────────┬─────────────┬────────────────┐ │
│  │ Strike   │ Call GEX   │ Put GEX   │ Net GEX     │ Open Interest  │ │
│  ├──────────┼────────────┼───────────┼─────────────┼────────────────┤ │
│  │ $590     │ +$800M  🟢 │ -$200M    │ +$600M      │ 120K           │ │
│  │ $585     │ +$600M     │ -$300M    │ +$300M      │ 95K            │ │
│  │ $582.50  │ +$200M     │ -$400M    │ -$200M ⚡   │ 80K (Flip)     │ │
│  │ $580     │ -$100M     │ -$500M 🔴 │ -$600M      │ 150K           │ │
│  │ $575     │ -$200M     │ -$900M    │ -$1.1B      │ 130K           │ │
│  │ $570     │ -$300M     │ -$1.2B    │ -$1.5B      │ 110K           │ │
│  └──────────┴────────────┴───────────┴─────────────┴────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

**Components Used:**
- Symbol search with quick select
- Large TradingView-style chart (main focus)
- Key metrics sidebar
- Market maker state card
- GEX levels data table

---

### 🔮 **Page 3: Gamma Intelligence (3 Views)**

**Purpose:** Gamma expiration analysis with 3 different perspectives

**Layout:**
```
┌────────────────────────────────────────────────────────────────────────┐
│  🎯 AlphaGEX    [Dashboard][GEX][Gamma][AI][Trader][More▾]   @username│
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│  🔮 Gamma Expiration Intelligence - SPY                                │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  [View 1: Daily Impact] [View 2: Weekly Evolution] [View 3: Risk]│  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│  📅 View 1: Daily Impact (Today → Tomorrow)                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Today (Wed)                  Tomorrow (Thu)                      │  │
│  │  ┌────────────────────┐       ┌────────────────────┐             │  │
│  │  │ Net GEX: -$1.2B   │   →   │ Net GEX: -$800M    │             │  │
│  │  │ Flip: $582.50     │       │ Flip: $584.00      │             │  │
│  │  │ Expiring: $2.1B   │       │ Removed: 35%       │             │  │
│  │  └────────────────────┘       └────────────────────┘             │  │
│  │                                                                    │  │
│  │  Impact Assessment:                                                │  │
│  │  🔴 HIGH IMPACT - 35% of gamma expires today                      │  │
│  │                                                                    │  │
│  │  What This Means:                                                  │  │
│  │  • Dealers covering $2.1B in positions                            │  │
│  │  • Volatility likely to DECREASE tomorrow                         │  │
│  │  • Range compression expected                                     │  │
│  │                                                                    │  │
│  │  Trade Implications:                                               │  │
│  │  ✅ TODAY: Momentum plays (squeeze still active)                  │  │
│  │  ⚠️ TOMORROW: Range-bound strategies (sell premium)               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│  📊 View 2: Weekly Evolution (Mon → Fri)                               │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Monday    Tuesday    Wednesday    Thursday    Friday             │  │
│  │  ┌──────┐  ┌──────┐   ┌──────┐    ┌──────┐    ┌──────┐          │  │
│  │  │-$2.5B│→ │-$1.8B│→  │-$1.2B│→   │-$800M│→   │-$200M│          │  │
│  │  │      │  │      │   │      │    │      │    │      │          │  │
│  │  │ High │  │ Med  │   │ Med  │    │ Low  │    │ Flat │          │  │
│  │  │ Vol  │  │ Vol  │   │ Vol  │    │ Vol  │    │ Vol  │          │  │
│  │  └──────┘  └──────┘   └──────┘    └──────┘    └──────┘          │  │
│  │                                                                    │  │
│  │  Weekly Pattern:                                                   │  │
│  │  • Monday: Peak negative gamma → Most volatile                    │  │
│  │  • Wed-Thu: Gradual decay as positions expire                     │  │
│  │  • Friday: Flat → OpEx cleanup, low volatility                    │  │
│  │                                                                    │  │
│  │  Best Trade Windows:                                               │  │
│  │  🎯 Monday-Tuesday: Directional trades (squeeze/breakdown)        │  │
│  │  💰 Thursday-Friday: Premium selling (range-bound)                │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│  ⚡ View 3: Volatility Potential (Risk Calendar)                       │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Next 7 Days Expiration Schedule                                  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │ Date        Expiring GEX    Impact Level    Volatility      │  │  │
│  │  ├────────────────────────────────────────────────────────────┤  │  │
│  │  │ Today (Wed)  $2.1B         🔴 HIGH         ↑ Elevated      │  │  │
│  │  │ Thu          $800M         🟡 MEDIUM       → Moderate      │  │  │
│  │  │ Fri (OpEx)   $3.5B         🔴 EXTREME      ↓ Collapse      │  │  │
│  │  │ Mon          $400M         🟢 LOW          → Calm           │  │  │
│  │  │ Tue          $300M         🟢 LOW          → Calm           │  │  │
│  │  │ Wed          $1.2B         🟡 MEDIUM       ↑ Rising         │  │  │
│  │  │ Thu          $900M         🟡 MEDIUM       → Moderate      │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │                                                                    │  │
│  │  🎯 Key Dates to Watch:                                            │  │
│  │  • Friday (OpEx): $3.5B expiring → Volatility crush expected      │  │
│  │  • Next Wednesday: $1.2B expiring → Volatility spike likely       │  │
│  │                                                                    │  │
│  │  Strategy Recommendations:                                         │  │
│  │  📅 Today-Thu: Trade momentum before Friday cleanup               │  │
│  │  📅 Friday: AVOID directional, sell premium instead               │  │
│  │  📅 Next Week Mon-Tue: Low vol → Scale into positions             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

**Components Used:**
- Tabbed interface (3 views)
- Timeline/calendar visualizations
- Impact assessment cards
- Strategy recommendation panels

---

### 🤖 **Page 4: AI Copilot**

**Purpose:** Chat with Claude about market conditions & trade ideas

**Layout:**
```
┌────────────────────────────────────────────────────────────────────────┐
│  🎯 AlphaGEX    [Dashboard][GEX][Gamma][AI][Trader][More▾]   @username│
└────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────┬─────────────────────────────────────────────┐
│  📊 Market Context       │  💬 Chat with Claude                        │
│  ┌────────────────────┐  │  ┌───────────────────────────────────────┐ │
│  │ SPY                │  │  │ 🤖 Claude                             │ │
│  │ Net GEX: -$1.2B    │  │  │                                       │ │
│  │ Flip: $582.50      │  │  │ Based on current GEX data, I see a   │ │
│  │ State: SQUEEZE     │  │  │ negative gamma squeeze forming. SPY   │ │
│  └────────────────────┘  │  │ is $2.25 below flip point. This      │ │
│                          │  │ suggests dealers will need to buy     │ │
│  💼 Your Positions (2)   │  │ on any upward move, potentially       │ │
│  ┌────────────────────┐  │  │ accelerating momentum.                │ │
│  │ SPY 580C: +$160   │  │  │                                       │ │
│  │ QQQ 390P: -$25    │  │  │ Consider: SPY 585C for 5 DTE         │ │
│  └────────────────────┘  │  │ Entry around $4.50-$4.80              │ │
│                          │  └───────────────────────────────────────┘ │
│  📅 Today                │                                             │
│  10:23 AM                │  ┌───────────────────────────────────────┐ │
│                          │  │ 👤 You                                │ │
│  🎯 Auto Trader          │  │                                       │ │
│  Status: Active          │  │ What's the best trade setup right    │ │
│  Last Trade: 9:45 AM     │  │ now given the GEX squeeze?            │ │
│  P&L Today: +$135        │  └───────────────────────────────────────┘ │
│                          │                                             │
│                          │  ┌───────────────────────────────────────┐ │
│  [📋 Export Chat]        │  │ 🤖 Claude                             │ │
│  [🗑️ Clear History]      │  │                                       │ │
└──────────────────────────┤  │ Here are 3 trade setups ranked by    │ │
                           │  │ probability and risk/reward:          │ │
📝 Suggested Prompts       │  │                                       │ │
┌────────────────────────┐ │  │ 1. Momentum Play (85% confidence)    │ │
│ "Analyze current GEX"  │ │  │    Buy SPY 585C, 5 DTE              │ │
│ "Best trade right now?"│ │  │    Entry: $4.65, Target: $8.00      │ │
│ "Review my positions"  │ │  │    Stop: $3.25, R:R = 2.1:1         │ │
│ "Explain this setup"   │ │  │                                       │ │
│ "What if VIX spikes?"  │ │  │ 2. [View More Setups...]             │ │
└────────────────────────┘ │  │                                       │ │
                           │  │ [📋 Copy Setup] [💰 Calculate Size]  │ │
                           │  └───────────────────────────────────────┘ │
                           │                                             │
                           │  ┌───────────────────────────────────────┐ │
                           │  │ [Type your message here...]       [↑]│ │
                           │  └───────────────────────────────────────┘ │
                           └─────────────────────────────────────────────┘
```

**Components Used:**
- Context panel (left sidebar)
- Chat interface (main area)
- Suggested prompts
- Quick actions in chat messages

---

### 🤖 **Page 5: Autonomous Trader Dashboard**

**Purpose:** Monitor and control the autonomous trading bot

**Layout:**
```
┌────────────────────────────────────────────────────────────────────────┐
│  🎯 AlphaGEX    [Dashboard][GEX][Gamma][AI][Trader][More▾]   @username│
└────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  🤖 Autonomous Trader                                                   │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Status: 🟢 ACTIVE   |   Last Trade: 9:45 AM   |   Next Check: 10:45 AM  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────┬───────────────────────────────────────────────┐
│  ⚙️ Controls            │  📊 Performance Overview                      │
│  ┌───────────────────┐  │  ┌─────────────────────────────────────────┐ │
│  │ [⏸️ Pause]  [▶️ Start]│ │  │  Starting Capital: $5,000.00           │ │
│  │ [🔄 Force Check Now] │ │  │  Current Value: $5,420.00              │ │
│  │                   │  │  │  Total P&L: +$420.00 (+8.4%)           │ │
│  └───────────────────┘  │  │                                         │ │
│                         │  │  ┌───────────────────────────────────┐  │ │
│  📈 Today               │  │  │ Equity Curve Chart                │  │ │
│  ┌───────────────────┐  │  │  │ (Shows growth over time)          │  │ │
│  │ Trades: 1          │  │  │  │                                   │  │ │
│  │ P&L: +$160        │  │  │  └───────────────────────────────────┘  │ │
│  │ Win Rate: 100%    │  │  └─────────────────────────────────────────┘ │
│  └───────────────────┘  │                                               │
│                         │  📊 Statistics                                │
│  📅 This Week           │  ┌─────────────────────────────────────────┐ │
│  ┌───────────────────┐  │  │  Total Trades: 29                      │ │
│  │ Trades: 5          │  │  │  Winning Trades: 18 (62%)              │ │
│  │ P&L: +$225        │  │  │  Losing Trades: 11 (38%)               │ │
│  │ Win Rate: 60%     │  │  │                                         │ │
│  └───────────────────┘  │  │  Average Winner: $45.50                │ │
│                         │  │  Average Loser: -$28.20                │ │
│  🎯 Strategy            │  │  Win/Loss Ratio: 1.61                  │ │
│  Current: Negative GEX  │  │  Expectancy: +$14.30 per trade         │ │
│  Squeeze                │  │                                         │ │
│                         │  │  Longest Win Streak: 5 trades          │ │
│  [⚙️ Settings]          │  │  Longest Loss Streak: 3 trades         │ │
│                         │  │  Max Drawdown: -$125 (-2.5%)           │ │
│                         │  └─────────────────────────────────────────┘ │
└─────────────────────────┴───────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  📜 Trade History (Last 10 Trades)                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ Date     Time    Symbol  Strategy        Entry    Exit     P&L    │  │
│  ├───────────────────────────────────────────────────────────────────┤  │
│  │ 10/30   9:45 AM  SPY 580C  Neg GEX Sq   $4.20    OPEN    +$160 ✅│  │
│  │ 10/29   10:15 AM SPY 575C  Neg GEX Sq   $5.10    $6.80   +$170 ✅│  │
│  │ 10/29   9:42 AM  SPY 572P  Pos GEX Fade $3.20    $2.85   -$35  ❌│  │
│  │ 10/28   10:00 AM SPY 570C  Neg GEX Sq   $4.50    $6.20   +$170 ✅│  │
│  │ 10/27   9:55 AM  SPY 568P  Breakdown     $2.80    $2.50   -$30  ❌│  │
│  │ 10/26   10:10 AM SPY 565C  Neg GEX Sq   $3.90    $4.80   +$90  ✅│  │
│  │ 10/25   9:50 AM  SPY 562C  Neg GEX Sq   $4.20    $3.50   -$70  ❌│  │
│  │ 10/24   10:05 AM SPY 560P  Breakdown     $3.50    $4.20   +$70  ✅│  │
│  │ ...                                                               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│  [View Full History] [Export CSV] [Analyze Patterns]                   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  🔍 Current Position Details                                            │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  SPY 580C - Opened 9:45 AM (Negative GEX Squeeze)                 │  │
│  │  ┌─────────────────┬───────────────┬───────────────┬─────────────┐ │  │
│  │  │ Entry: $4.20    │ Current: $5.80│ Target: $8.00 │ Stop: $3.00 │ │  │
│  │  │ Contracts: 2    │ Cost: $840    │ Value: $1,160 │ P&L: +$320  │ │  │
│  │  └─────────────────┴───────────────┴───────────────┴─────────────┘ │  │
│  │                                                                     │  │
│  │  Trade Reasoning:                                                   │  │
│  │  "Net GEX -$1.2B (negative). Dealers SHORT gamma. Price $580.25   │  │
│  │   is $2.25 below flip $582.50. When SPY rallies, dealers must BUY │  │
│  │   to hedge, accelerating the move upward."                         │  │
│  │                                                                     │  │
│  │  Exit Conditions:                                                   │  │
│  │  ✅ +50% profit ($6.30) - Take profit target                       │  │
│  │  ❌ -30% loss ($2.94) - Stop loss                                  │  │
│  │  ⏰ 1 DTE or less - Time-based exit                                │  │
│  │  🔄 GEX regime change - Strategy invalidation                      │  │
│  │                                                                     │  │
│  │  [🔴 Close Position Now] [⚙️ Adjust Targets]                       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Components Used:**
- Status bar with controls
- Performance overview card
- Statistics panel
- Trade history table
- Current position details card

---

## Component Library

### 🎴 Cards
```
Standard Card:
┌────────────────────────────┐
│ Card Header (Semibold)     │
├────────────────────────────┤
│ Card Body (Regular)        │
│ - Content                  │
│ - More content             │
└────────────────────────────┘

Metric Card:
┌────────────────────────────┐
│ 📊 Label (Caption)         │
│                            │
│ $1.2M                      │
│ Value (Display Medium)     │
│                            │
│ ↑ 15% (Small, Green)       │
└────────────────────────────┘

Status Card:
┌────────────────────────────┐
│ 🟢 Status: Active          │
│ Last Update: Just now      │
└────────────────────────────┘
```

### 🔘 Buttons

**Primary Button** (CTAs, main actions)
```
Background: #3b82f6 (Blue)
Hover: #2563eb (Darker blue)
Text: #ffffff (White)
Padding: 12px 24px
Border Radius: 8px
Font: Semibold, 16px
```

**Secondary Button** (Less important actions)
```
Background: Transparent
Border: 2px solid #3b82f6
Hover: Background #3b82f6, Text #ffffff
Text: #3b82f6
Padding: 12px 24px
Border Radius: 8px
```

**Danger Button** (Destructive actions)
```
Background: #ef4444 (Red)
Hover: #dc2626
Text: #ffffff
(Same size/shape as primary)
```

**Icon Button** (Quick actions)
```
Size: 40px × 40px
Background: Transparent
Hover: Background #1a1f2e
Icon: 20px, #9ca3af
Border Radius: 8px
```

### 📊 Charts

**Primary Chart Library:** TradingView Lightweight Charts
- Real-time updates
- Interactive pan/zoom
- Multiple timeframes
- Technical indicators
- Custom overlays (GEX levels, flip point, walls)

**Secondary Charts:** Recharts (for simpler charts)
- Equity curves
- Bar charts
- Performance metrics

### 📝 Forms & Inputs

**Text Input:**
```
┌────────────────────────────┐
│ Label (Small, Semibold)    │
│ ┌────────────────────────┐ │
│ │ [Placeholder text...  ]│ │
│ └────────────────────────┘ │
│ Helper text (Caption)      │
└────────────────────────────┘

Background: #1a1f2e
Border: 1px solid #374151
Focus: Border #3b82f6, glow
Padding: 12px 16px
Border Radius: 8px
```

**Select Dropdown:**
```
┌────────────────────────────┐
│ [Selected option       ▾] │
└────────────────────────────┘

Dropdown Menu:
┌────────────────────────────┐
│ Option 1                   │
│ Option 2                 ✓ │
│ Option 3                   │
└────────────────────────────┘
```

**Toggle Switch:**
```
⚫──── OFF

────⚫ ON (Blue)
```

### 📊 Tables

**Data Table:**
```
┌────────────┬────────────┬────────────┬────────────┐
│ Header 1   │ Header 2   │ Header 3   │ Actions    │
├────────────┼────────────┼────────────┼────────────┤
│ Cell 1,1   │ Cell 1,2   │ Cell 1,3   │ [Edit]     │
│ Cell 2,1   │ Cell 2,2   │ Cell 2,3   │ [Edit]     │
│ Cell 3,1   │ Cell 3,2   │ Cell 3,3   │ [Edit]     │
└────────────┴────────────┴────────────┴────────────┘

Features:
- Sortable columns
- Hover state on rows
- Alternate row backgrounds (very subtle)
- Fixed header on scroll
- Responsive (stack on mobile)
```

### 🔔 Alerts & Toasts

**Success Toast:**
```
┌────────────────────────────────────┐
│ ✅ Success!                        │
│ Position closed at $5.80 (+38%)    │
└────────────────────────────────────┘
Background: Linear gradient green
Position: Top-right corner
Duration: 4 seconds
```

**Error Toast:**
```
┌────────────────────────────────────┐
│ ❌ Error                           │
│ Failed to fetch GEX data           │
└────────────────────────────────────┘
Background: Linear gradient red
Position: Top-right corner
Duration: 5 seconds
```

**Info Toast:**
```
┌────────────────────────────────────┐
│ ℹ️ Info                            │
│ Data refreshed - 30s ago           │
└────────────────────────────────────┘
Background: Linear gradient blue
Position: Top-right corner
Duration: 3 seconds
```

---

## Interactions & Animations

### Hover States
```
Cards:
- Lift: translateY(-2px)
- Shadow: Increase elevation
- Transition: 200ms ease

Buttons:
- Background: Darken 10%
- Transform: scale(1.02)
- Transition: 150ms ease

Links:
- Color: Brighten 20%
- Underline: Fade in
```

### Loading States
```
Skeleton Loader:
- Gray boxes (#1a1f2e)
- Shimmer animation (left to right)
- Pulsing opacity

Spinner:
- Circular blue spinner
- 40px diameter
- Smooth rotation
```

### Page Transitions
```
Route Change:
- Fade out current page (200ms)
- Fade in new page (300ms)
- Slight slide up (10px)

Modal Open:
- Background fade to 60% black
- Modal scale from 0.9 to 1.0
- Duration: 250ms ease-out
```

### Real-Time Updates
```
New Data Arrives:
- Flash border of card (blue glow)
- Duration: 500ms
- Fade out

Chart Updates:
- Smooth line animation
- No jarring jumps
- Crossfade old/new data
```

---

## Responsive Design

### Breakpoints
```
Mobile:    < 640px
Tablet:    640px - 1024px
Desktop:   1024px - 1536px
XL:        > 1536px
```

### Mobile Adaptations

**Navigation:**
- Bottom tab bar (instead of top)
- Hamburger menu for "More" section

**Dashboard:**
- Status cards: 2 columns instead of 5
- Chart: Full width, taller
- Positions: Stacked cards instead of side-by-side

**Tables:**
- Stack rows into cards
- Show only essential columns
- "Expand" button for details

**Charts:**
- Touch-friendly controls
- Larger touch targets (48px min)
- Simplified overlays

---

## Next Steps

### ✅ Review Checklist

Before I start coding, please confirm:

- [ ] Overall design direction looks good
- [ ] Color scheme works for you (dark mode, blue accents)
- [ ] Navigation structure makes sense
- [ ] Page layouts organized well
- [ ] Components are what you need
- [ ] Responsive approach is appropriate

### 📝 Feedback Needed

Please review and tell me:

1. **Any pages/layouts you want changed?**
   - Different organization?
   - Missing features?
   - Too cluttered/too sparse?

2. **Color preferences?**
   - Like the dark mode + blue accent?
   - Want different colors?
   - Any specific brand colors?

3. **Priority order for building?**
   - Which page should I build first?
   - Which features are most critical?

4. **Any design inspirations to add?**
   - Screenshots of UIs you like?
   - Specific elements to emulate?

### 🚀 After Approval

Once you approve the design:
1. I'll set up the React project
2. Build design system (components)
3. Build pages in priority order
4. You test each page as it's done
5. Iterate based on feedback

**Ready for your feedback!** 🎨
