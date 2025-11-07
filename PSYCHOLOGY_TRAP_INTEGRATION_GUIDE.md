# Psychology Trap Detection System - Integration Guide

## Current Architecture & Integration Points

### 1. EXISTING PSYCHOLOGY DETECTION (Foundation)

**File**: `intelligence_and_strategies.py` (Line 312)
**Class**: `PsychologicalCoach`

Current detection (5 red flags):
1. **OVERTRADING** - Too many requests in short time
2. **REVENGE TRADING** - Loss → Immediate new trade
3. **IGNORING ADVICE** - AI warns risky, user pushes anyway
4. **AFTER HOURS** - Trading emotionally outside market hours
5. **TIMING VIOLATION** - Wed 3PM+ or Thu/Fri directional entry

### 2. KEY INTEGRATION LAYERS

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACE                        │
│              (Next.js Frontend - React)                  │
├─────────────────────────────────────────────────────────┤
│  ✅ Dashboard          ✅ Gamma          ✅ Trader       │
│  ❌ Psychology (NEW)   ✅ Alerts         ✅ AI Chat      │
│                                                          │
│  New Component: PsychologyDashboard                      │
│  ├─ Current Psychology State (visual gauge)             │
│  ├─ Active Traps (list with severity)                   │
│  ├─ Historical Patterns (chart)                         │
│  ├─ Behavioral Score (0-100)                            │
│  └─ Personalized Recommendations                        │
└─────────────────────────────────────────────────────────┘
           │
           │ Axios HTTP Calls
           ▼
┌─────────────────────────────────────────────────────────┐
│                  BACKEND API (FastAPI)                  │
│                  backend/main.py                        │
├─────────────────────────────────────────────────────────┤
│  ✅ GET /api/gex/{symbol}                              │
│  ✅ GET /api/gamma/{symbol}/intelligence               │
│  ✅ POST /api/ai/analyze                               │
│  ❌ POST /api/psychology/analyze (NEW)                 │
│  ❌ GET /api/psychology/score (NEW)                    │
│  ❌ GET /api/psychology/history (NEW)                  │
│                                                          │
│  New Endpoints Process:                                 │
│  1. Receive: User conversation, market data, trades    │
│  2. Extract: Behavioral patterns & signals             │
│  3. Detect: Trap type & severity                       │
│  4. Call: Claude AI for deep analysis                  │
│  5. Return: JSON with trap info + recommendations      │
└─────────────────────────────────────────────────────────┘
           │
           │ Direct Python Calls + SQLite
           ▼
┌─────────────────────────────────────────────────────────┐
│              ANALYSIS LAYER (Python)                    │
│                                                          │
│  intelligence_and_strategies.py                         │
│  ├─ PsychologicalCoach (EXTEND existing)               │
│  │  ├─ analyze_behavior() (5 flags → 20+ traps)       │
│  │  ├─ detect_overtrading()                            │
│  │  ├─ detect_revenge_trading()                        │
│  │  ├─ detect_overconfidence()                         │
│  │  ├─ detect_fear_paralysis()                         │
│  │  ├─ detect_fomo()                                   │
│  │  ├─ calculate_behavioral_score()                    │
│  │  └─ get_recommendations()                           │
│  │                                                      │
│  ├─ ClaudeIntelligence (EXISTING)                      │
│  │  ├─ Call Claude for trap analysis                   │
│  │  └─ Generate personalized coaching                 │
│  │                                                      │
│  └─ New Class: PsychologyTrapDetector                  │
│     ├─ Trap definitions & thresholds                   │
│     ├─ Pattern matching logic                          │
│     └─ Severity scoring                                │
│                                                          │
│  config_and_database.py (EXTEND)                       │
│  └─ PSYCHOLOGY_TRAPS dictionary                        │
│     ├─ Trap definitions                                │
│     ├─ Severity levels                                 │
│     ├─ Detection rules                                 │
│     └─ Coaching recommendations                        │
└─────────────────────────────────────────────────────────┘
           │
           │ SQL Reads/Writes
           ▼
┌─────────────────────────────────────────────────────────┐
│               DATABASE (SQLite)                         │
│               gex_copilot.db                            │
├─────────────────────────────────────────────────────────┤
│  ✅ gamma_history                                       │
│  ✅ autonomous_positions                               │
│  ✅ autonomous_trade_log                               │
│  ❌ psychology_history (NEW TABLE)                      │
│  ❌ psychology_scores (NEW TABLE)                       │
│  ❌ psychology_recommendations (NEW TABLE)              │
│                                                          │
│  New Tables Schema:                                     │
│                                                          │
│  psychology_history:                                    │
│  ├─ id (PRIMARY KEY)                                    │
│  ├─ timestamp (DATETIME)                               │
│  ├─ trap_type (VARCHAR)  -- "REVENGE", "FOMO", etc.   │
│  ├─ severity (VARCHAR)   -- "LOW", "MEDIUM", "HIGH"    │
│  ├─ description (TEXT)                                 │
│  ├─ trigger_event (TEXT)                               │
│  ├─ user_action (TEXT)   -- What user did next         │
│  ├─ recommendation (TEXT)                              │
│  └─ outcome (VARCHAR)    -- "Avoided", "Triggered"     │
│                                                          │
│  psychology_scores:                                     │
│  ├─ id (PRIMARY KEY)                                    │
│  ├─ date (DATE)                                         │
│  ├─ behavioral_score (INT)  -- 0-100                   │
│  ├─ emotional_state (VARCHAR) -- "Rational", "Anxious" │
│  ├─ trap_vulnerability (INT) -- 0-100                  │
│  └─ recovery_trend (REAL)                              │
└─────────────────────────────────────────────────────────┘
```

### 3. DETAILED INTEGRATION STEPS

#### Step 1: Extend PsychologicalCoach Class

**File**: `intelligence_and_strategies.py` (Line 312)

```python
class PsychologicalCoach:
    """Detect and analyze trader psychology traps"""
    
    def __init__(self):
        self.session_trade_count = 0
        self.last_loss_time = None
        self.ignored_warnings = []
        
        # NEW: Load trap definitions
        self.traps = self._load_trap_definitions()
        
    def analyze_behavior(self, conversation_history, current_request):
        """Analyze ALL 20+ psychology traps (extend from 5)"""
        red_flags = []
        
        # Existing 5 detections
        red_flags.extend(self._detect_overtrading(conversation_history))
        red_flags.extend(self._detect_revenge_trading(conversation_history))
        red_flags.extend(self._detect_ignoring_advice(conversation_history))
        red_flags.extend(self._detect_after_hours_trading(conversation_history))
        red_flags.extend(self._detect_timing_violations())
        
        # NEW: 15+ additional trap detections
        red_flags.extend(self._detect_overconfidence(conversation_history))
        red_flags.extend(self._detect_fear_paralysis(conversation_history))
        red_flags.extend(self._detect_fomo(conversation_history))
        red_flags.extend(self._detect_loss_aversion(conversation_history))
        red_flags.extend(self._detect_anchoring_bias(conversation_history))
        red_flags.extend(self._detect_confirmation_bias(conversation_history))
        red_flags.extend(self._detect_averaging_down(conversation_history))
        red_flags.extend(self._detect_gambler_fallacy(conversation_history))
        # ... more traps
        
        return {
            'traps_detected': red_flags,
            'trap_count': len(red_flags),
            'severity': self._calculate_severity(red_flags),
            'behavioral_score': self.calculate_behavioral_score(red_flags),
            'recommendations': self._get_personalized_recommendations(red_flags),
            'primary_concern': red_flags[0] if red_flags else None
        }
    
    def calculate_behavioral_score(self, traps: List[Dict]) -> int:
        """Calculate 0-100 behavioral health score"""
        # Start with 100 (perfect)
        score = 100
        
        for trap in traps:
            if trap['severity'] == 'CRITICAL':
                score -= 20
            elif trap['severity'] == 'HIGH':
                score -= 10
            elif trap['severity'] == 'MEDIUM':
                score -= 5
            elif trap['severity'] == 'LOW':
                score -= 2
        
        return max(0, min(100, score))  # Clamp 0-100
    
    def _get_personalized_recommendations(self, traps):
        """Generate actionable coaching for each trap"""
        recommendations = []
        
        for trap in traps:
            # NEW: Custom coaching message per trap
            coaching = self.traps[trap['type']].get('coaching')
            
            recommendations.append({
                'trap_type': trap['type'],
                'action': coaching.get('immediate_action'),
                'prevention': coaching.get('prevention_strategy'),
                'affirmation': coaching.get('positive_affirmation'),
                'resource': coaching.get('educational_link')
            })
        
        return recommendations
```

#### Step 2: Define Trap Types in Configuration

**File**: `config_and_database.py` (NEW section)

```python
# Psychology Traps Taxonomy
PSYCHOLOGY_TRAPS = {
    # Category 1: Overtrading
    'OVERTRADING': {
        'definition': 'Making too many trades in short period',
        'severity': 'HIGH',
        'indicators': [
            'trade_request_count >= 4 in 24 hours',
            'trading_on_breakeven_days',
            'multiple_same_strategy_trades'
        ],
        'threshold': 4,  # Trades per 24 hours
        'coaching': {
            'immediate_action': 'Step away from trading for 30 minutes',
            'prevention_strategy': 'Max 2 trades per day rule',
            'positive_affirmation': 'Quality over quantity - patience is a virtue',
            'educational_link': '/resources/emotional-trading'
        }
    },
    
    # Category 2: Loss/Win Chasing
    'REVENGE_TRADING': {
        'definition': 'Opening new trade immediately after loss',
        'severity': 'CRITICAL',
        'indicators': [
            'loss_mentioned && trade_requested_within_30min',
            'position_loss_pct > 20 && new_position_opened'
        ],
        'cooling_period': 60,  # minutes
        'coaching': {
            'immediate_action': 'STOP. Walk away for 1 hour minimum',
            'prevention_strategy': '15-minute rule: Never trade within 15 min of loss',
            'positive_affirmation': 'Losses are learning opportunities, not targets',
            'educational_link': '/resources/revenge-trading'
        }
    },
    
    # Category 3: Overconfidence
    'OVERCONFIDENCE': {
        'definition': 'Excessive confidence after wins; ignoring risk',
        'severity': 'HIGH',
        'indicators': [
            'consecutive_wins >= 3',
            'larger_size_after_wins',
            'ignored_stop_loss_warnings',
            'expressing_certainty_about_move'
        ],
        'consecutive_win_threshold': 3,
        'coaching': {
            'immediate_action': 'Reduce position size by 50%',
            'prevention_strategy': 'Cap win streak size at 75% of normal',
            'positive_affirmation': 'Consistent winners are humble winners',
            'educational_link': '/resources/overconfidence-bias'
        }
    },
    
    # Category 4: Fear
    'FEAR_PARALYSIS': {
        'definition': 'Unable to take profits; watching winner become loser',
        'severity': 'MEDIUM',
        'indicators': [
            'position_profitable_for_30min && not_closed',
            'loss_after_being_positive >= 3x_in_week',
            'trailing_stop_never_triggered'
        ],
        'profit_hold_minutes': 30,  # Profitable but not taking
        'coaching': {
            'immediate_action': 'Set and forget - use auto-close at +50%',
            'prevention_strategy': 'Never hold a profitable position overnight',
            'positive_affirmation': 'Take profits early and often',
            'educational_link': '/resources/fear-paralysis'
        }
    },
    
    # Category 5: FOMO
    'FOMO': {
        'definition': 'Fear of Missing Out - chasing moved breakouts',
        'severity': 'HIGH',
        'indicators': [
            'entering_after_>5%_move',
            'chasing_stops_multiple_times',
            'wider_stops_after_breakout'
        ],
        'move_threshold': 5,  # Percent
        'coaching': {
            'immediate_action': 'Let this one go - next setup is coming',
            'prevention_strategy': 'Only trade first 30 min and last hour',
            'positive_affirmation': 'The best trade is the one you don\'t take',
            'educational_link': '/resources/fomo-trading'
        }
    },
    
    # Category 6: Bias
    'CONFIRMATION_BIAS': {
        'definition': 'Only looking for information confirming your view',
        'severity': 'MEDIUM',
        'indicators': [
            'ignoring_opposing_signals',
            'only_reading_bullish/bearish_news',
            'dismissing_contrary_advice'
        ],
        'coaching': {
            'immediate_action': 'List 3 reasons why you could be WRONG',
            'prevention_strategy': 'Always play devil\'s advocate before entry',
            'positive_affirmation': 'The market is always right; adjust your view',
            'educational_link': '/resources/confirmation-bias'
        }
    },
    
    # ... 14+ more traps
}
```

#### Step 3: Create Backend Endpoints

**File**: `backend/main.py`

```python
from intelligence_and_strategies import PsychologicalCoach

psychology_coach = PsychologicalCoach()

@app.post("/api/psychology/analyze")
async def analyze_psychology(request: dict):
    """
    Analyze trader psychology and detect traps
    
    Request body:
    {
        'conversation_history': [...],  # Chat messages
        'recent_trades': [...],          # Last N trades
        'market_data': {...},            # Current GEX, etc
        'account_status': {...}          # P&L, positions
    }
    """
    try:
        # Extract data
        history = request.get('conversation_history', [])
        current_request = request.get('latest_message', '')
        
        # Analyze psychology
        analysis = psychology_coach.analyze_behavior(history, current_request)
        
        # Get Claude's perspective
        if analysis['traps_detected']:
            claude_coaching = await claude_ai.get_psychology_coaching(
                analysis,
                request.get('market_data'),
                request.get('recent_trades')
            )
            analysis['claude_perspective'] = claude_coaching
        
        # Store in database
        store_psychology_record(analysis)
        
        return {
            'success': True,
            'analysis': analysis,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.get("/api/psychology/score")
async def get_psychology_score():
    """Get current behavioral health score (0-100)"""
    # Pull recent data
    # Calculate behavioral score
    # Return with trend analysis
    pass

@app.get("/api/psychology/history")
async def get_psychology_history(days: int = 7):
    """Get psychology history for past N days"""
    # Query psychology_history table
    # Return trends, patterns, insights
    pass

@app.post("/api/psychology/coaching")
async def get_psychology_coaching(request: dict):
    """Get personalized coaching for detected traps"""
    # Uses Claude AI + trap definitions
    # Returns: Immediate action, prevention strategy, affirmation
    pass
```

#### Step 4: Create Database Tables

**File**: `gamma_tracking_database.py` (or new file)

```python
def _ensure_psychology_tables(self):
    """Create psychology tracking tables"""
    conn = sqlite3.connect(self.db_path)
    c = conn.cursor()
    
    # Historical trap detection
    c.execute("""
        CREATE TABLE IF NOT EXISTS psychology_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            trap_type TEXT NOT NULL,
            severity TEXT,
            description TEXT,
            trigger_event TEXT,
            user_action TEXT,
            recommendation TEXT,
            outcome TEXT,
            resolved BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Daily behavioral scores
    c.execute("""
        CREATE TABLE IF NOT EXISTS psychology_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            behavioral_score INTEGER,
            emotional_state TEXT,
            trap_vulnerability INTEGER,
            win_rate INTEGER,
            trade_count INTEGER,
            avg_hold_time REAL,
            recovery_trend REAL,
            confidence_score INTEGER,
            UNIQUE(date)
        )
    """)
    
    # Recommendations & outcomes
    c.execute("""
        CREATE TABLE IF NOT EXISTS psychology_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            trap_type TEXT NOT NULL,
            recommendation TEXT,
            followed BOOLEAN,
            outcome TEXT,
            profit_impact REAL,
            effectiveness_score REAL
        )
    """)
    
    conn.commit()
    conn.close()
```

#### Step 5: Create Frontend Dashboard

**File**: `frontend/src/app/psychology/page.tsx` (NEW)

```tsx
'use client'

import { useState, useEffect } from 'react'
import Navigation from '@/components/Navigation'
import { apiClient } from '@/lib/api'
import {
  TrendingUp,
  AlertCircle,
  Activity,
  Zap,
  Heart,
  Brain
} from 'lucide-react'

interface PsychologyAnalysis {
  traps_detected: Array<{
    type: string
    severity: string
    message: string
  }>
  behavioral_score: number
  recommendations: Array<{
    trap_type: string
    action: string
    prevention: string
  }>
  primary_concern: string | null
}

export default function PsychologyDashboard() {
  const [analysis, setAnalysis] = useState<PsychologyAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const fetchPsychologyAnalysis = async () => {
    try {
      setLoading(true)
      
      // Get latest data
      const [traderStatus, positionsRes, tradeLogRes] = await Promise.all([
        apiClient.getTraderLiveStatus(),
        apiClient.getOpenPositions(),
        apiClient.getTradeLog()
      ])
      
      // Analyze psychology
      const response = await apiClient.analyzePsychology({
        recent_trades: tradeLogRes.data.data,
        account_status: traderStatus.data.data,
        positions: positionsRes.data.data
      })
      
      setAnalysis(response.data.analysis)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  useEffect(() => {
    fetchPsychologyAnalysis()
    // Refresh every 5 minutes
    const interval = setInterval(fetchPsychologyAnalysis, 300000)
    return () => clearInterval(interval)
  }, [])
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800">
      <Navigation />
      
      <div className="p-8">
        <h1 className="text-4xl font-bold text-white mb-8">
          <Brain className="inline mr-3" />
          Psychology & Behavioral Analysis
        </h1>
        
        {/* Behavioral Score Gauge */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-slate-700 rounded-lg p-6">
            <div className="text-sm text-slate-300 mb-2">Behavioral Score</div>
            <div className="text-5xl font-bold text-blue-400">
              {analysis?.behavioral_score ?? 0}
            </div>
            <div className="text-xs text-slate-400 mt-2">out of 100</div>
          </div>
          
          {/* Trap Count */}
          <div className="bg-slate-700 rounded-lg p-6">
            <div className="text-sm text-slate-300 mb-2">Active Traps</div>
            <div className="text-5xl font-bold text-red-400">
              {analysis?.traps_detected?.length ?? 0}
            </div>
            <div className="text-xs text-slate-400 mt-2">detected</div>
          </div>
        </div>
        
        {/* Detected Traps */}
        {analysis?.traps_detected && analysis.traps_detected.length > 0 && (
          <div className="bg-slate-700 rounded-lg p-6 mb-8">
            <h2 className="text-xl font-bold text-white mb-4 flex items-center">
              <AlertCircle className="mr-2 text-red-400" />
              Detected Psychological Traps
            </h2>
            
            {analysis.traps_detected.map((trap, idx) => (
              <div key={idx} className="mb-4 p-4 bg-slate-800 rounded border-l-4 border-red-500">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-bold text-white">{trap.type}</h3>
                    <p className="text-sm text-slate-300 mt-2">{trap.message}</p>
                  </div>
                  <span className="px-3 py-1 bg-red-900 text-red-200 rounded text-xs font-bold">
                    {trap.severity}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
        
        {/* Recommendations */}
        {analysis?.recommendations && (
          <div className="bg-slate-700 rounded-lg p-6 mb-8">
            <h2 className="text-xl font-bold text-white mb-4 flex items-center">
              <Zap className="mr-2 text-yellow-400" />
              Personalized Recommendations
            </h2>
            
            {analysis.recommendations.map((rec, idx) => (
              <div key={idx} className="mb-6 p-4 bg-slate-800 rounded border-l-4 border-yellow-500">
                <h3 className="font-bold text-white mb-2">{rec.trap_type}</h3>
                <div className="space-y-2 text-sm text-slate-300">
                  <p>
                    <span className="font-semibold text-yellow-300">Immediate Action:</span> {rec.action}
                  </p>
                  <p>
                    <span className="font-semibold text-green-300">Prevention:</span> {rec.prevention}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
```

#### Step 6: Update Frontend API Client

**File**: `frontend/src/lib/api.ts`

```typescript
// Add to apiClient object:
analyzePsychology: (data: {
  recent_trades?: any[]
  account_status?: any
  positions?: any
}) => api.post('/api/psychology/analyze', data),

getPsychologyScore: () => api.get('/api/psychology/score'),

getPsychologyHistory: (days: number = 7) =>
  api.get('/api/psychology/history', { params: { days } }),

getPsychologyCoaching: (trapType: string) =>
  api.post('/api/psychology/coaching', { trap_type: trapType }),
```

### 4. PSYCHOLOGY TRAP DEFINITIONS (20+ Traps to Detect)

Based on trader behavior research, these traps should be detected:

**Emotional Traps:**
1. Revenge Trading - Trading too soon after loss
2. FOMO (Fear of Missing Out) - Chasing moved breakouts
3. Fear Paralysis - Can't take profits
4. Overconfidence - Too much faith after wins
5. Loss Aversion - Taking losses differently than wins

**Cognitive Biases:**
6. Confirmation Bias - Only looking for confirming info
7. Anchoring Bias - Stuck on wrong entry price
8. Gambler's Fallacy - "Due for a win after losses"
9. Availability Bias - Overweighting recent events
10. Recency Bias - Trading like market always continues up/down

**Behavioral Patterns:**
11. Overtrading - Too many trades per day/week
12. Average Down - Doubling down on losing positions
13. Ignoring Stops - Moving stops after being stopped out
14. Correlation Bias - Thinking patterns mean causation
15. Size Creep - Gradually increasing position sizes

**Timing Errors:**
16. Theta Trap - Holding directional into weekend/expiration
17. IV Crush - Buying premium before earnings
18. Trend Following Late - Chasing after big move
19. News Trading - Overtrading around announcements
20. Time of Day - Trading outside best hours

**Institutional Traps:**
21. Forced Liquidation - Margin calls
22. Liquidity Trap - Entry is easy, exit is hard
23. Slippage Death - Not accounting for bid/ask
24. Correlation Collapse - Positions move together

### 5. EXPECTED BENEFITS

Once implemented, the Psychology Trap Detection System will:

1. **Real-time Detection** - Catch emotional trades before execution
2. **Personalized Coaching** - Tailored advice per trap type
3. **Pattern Learning** - Track which traps affect YOUR trading most
4. **Behavioral Trending** - Show improvement over time (like equity curve)
5. **Preventive Alerts** - Warn you about vulnerability to traps
6. **Community Learning** - Learn from historical trap data
7. **AI Coaching** - Claude provides deep psychological insights

### 6. IMPLEMENTATION TIMELINE

**Phase 1 (Week 1):**
- Extend PsychologicalCoach class with 20+ trap detections
- Define PSYCHOLOGY_TRAPS in config_and_database.py
- Create SQLite tables for psychology history

**Phase 2 (Week 2):**
- Add backend endpoints: /api/psychology/*
- Integrate with ClaudeIntelligence for coaching
- Connect to database

**Phase 3 (Week 3):**
- Create frontend PsychologyDashboard page
- Add components for visualization
- Connect frontend API client

**Phase 4 (Week 4):**
- Testing and refinement
- Historical data analysis
- Documentation & deployment

---

**END OF PSYCHOLOGY TRAP INTEGRATION GUIDE**
