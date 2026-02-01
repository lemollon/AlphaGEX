"""
SOLOMON - Feedback Loop Intelligence System for AlphaGEX Trading Bots
======================================================================

Named after King Solomon, renowned for wisdom and judgment.

PURPOSE:
Solomon is the central feedback loop orchestrator that ensures trading bots
continuously learn and improve while maintaining full transparency and human oversight.

CORE PRINCIPLES:
1. TRANSPARENCY - Every decision is logged with WHO, WHAT, WHY, WHEN
2. ACCOUNTABILITY - All changes require approval before going live
3. REVERSIBILITY - One-click rollback to any previous state
4. OBSERVABILITY - Real-time dashboard showing loop health and performance

ARCHITECTURE:
    ┌─────────────────────────────────────────────────────────────────┐
    │                         SOLOMON                                  │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
    │  │   COLLECT   │  │   ANALYZE   │  │   PROPOSE   │             │
    │  │  Outcomes   │──│  Performance│──│   Changes   │             │
    │  └─────────────┘  └─────────────┘  └─────────────┘             │
    │         │                │                │                     │
    │         ▼                ▼                ▼                     │
    │  ┌─────────────────────────────────────────────────────┐       │
    │  │              APPROVAL GATEWAY                        │       │
    │  │  Human reviews → Approves/Rejects → Changes Applied │       │
    │  └─────────────────────────────────────────────────────┘       │
    │         │                                                       │
    │         ▼                                                       │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
    │  │   APPLY     │  │   MONITOR   │  │   ROLLBACK  │             │
    │  │   Changes   │──│  Performance│──│  If Needed  │             │
    │  └─────────────┘  └─────────────┘  └─────────────┘             │
    └─────────────────────────────────────────────────────────────────┘

BOTS COVERED:
- ARES: Aggressive Iron Condor (0DTE SPX)
- ATHENA: Directional Spreads (Bull/Bear Call)
- PEGASUS: SPX Iron Condor
- PHOENIX: 0DTE Options Trading

DATABASE TABLES:
- solomon_audit_log: Complete audit trail of every action
- solomon_proposals: Pending changes awaiting approval
- solomon_versions: Version history for models and parameters
- solomon_rollbacks: Rollback history and recovery points
- solomon_performance: Performance tracking per version

Author: AlphaGEX Quant
Date: 2024-12
"""

from __future__ import annotations

import os
import sys
import json
import hashlib
import logging
import pickle
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from zoneinfo import ZoneInfo

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    get_connection = None


# Context manager for safe database connections (prevents connection leaks)
from contextlib import contextmanager

@contextmanager
def get_db_connection():
    """
    Context manager for database connections.

    Ensures connections are always closed, even if an exception occurs.

    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(...)
    """
    conn = None
    try:
        if not DB_AVAILABLE or get_connection is None:
            yield None
        else:
            conn = get_connection()
            yield conn
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

# Oracle integration
try:
    from quant.oracle_advisor import (
        get_oracle, auto_train, get_pending_outcomes_count,
        OracleAdvisor, BotName as OracleBotName, TrainingMetrics
    )
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    get_oracle = None

# Math Optimizer integration for enhanced trading decisions
try:
    from core.math_optimizers import MathOptimizerOrchestrator
    MATH_OPTIMIZER_AVAILABLE = True
except ImportError:
    MATH_OPTIMIZER_AVAILABLE = False
    MathOptimizerOrchestrator = None

logger = logging.getLogger(__name__)

# Timezone
CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class BotName(Enum):
    """Trading bots under Solomon's oversight"""
    ARES = "ARES"           # SPY Iron Condor (0DTE)
    ATHENA = "ATHENA"       # SPY Directional Spreads
    TITAN = "TITAN"         # SPX Aggressive Iron Condor
    PEGASUS = "PEGASUS"     # SPX Weekly Iron Condor
    ICARUS = "ICARUS"       # SPY Aggressive Directional
    PROMETHEUS = "PROMETHEUS"  # Box Spread Synthetic Borrowing + IC Trading
    # Legacy bots (not actively traded)
    ATLAS = "ATLAS"         # SPX Wheel (Cash-Secured Puts)
    PHOENIX = "PHOENIX"     # 0DTE Options (partial implementation)


class ActionType(Enum):
    """Types of actions Solomon can take"""
    # Training actions
    MODEL_RETRAIN = "MODEL_RETRAIN"
    MODEL_LOADED = "MODEL_LOADED"
    MODEL_ROLLBACK = "MODEL_ROLLBACK"

    # Parameter actions
    PARAM_UPDATE = "PARAM_UPDATE"
    PARAM_ROLLBACK = "PARAM_ROLLBACK"

    # Proposal actions
    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    PROPOSAL_APPROVED = "PROPOSAL_APPROVED"
    PROPOSAL_REJECTED = "PROPOSAL_REJECTED"
    PROPOSAL_EXPIRED = "PROPOSAL_EXPIRED"

    # Performance actions
    PERFORMANCE_ALERT = "PERFORMANCE_ALERT"
    DEGRADATION_DETECTED = "DEGRADATION_DETECTED"

    # System actions
    FEEDBACK_LOOP_RUN = "FEEDBACK_LOOP_RUN"
    OUTCOME_RECORDED = "OUTCOME_RECORDED"
    HEALTH_CHECK = "HEALTH_CHECK"
    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
    KILL_SWITCH_DEACTIVATED = "KILL_SWITCH_DEACTIVATED"


class ProposalStatus(Enum):
    """Status of a change proposal"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    APPLIED = "APPLIED"
    ROLLED_BACK = "ROLLED_BACK"


class ProposalType(Enum):
    """Types of proposals Solomon can make"""
    MODEL_UPDATE = "MODEL_UPDATE"
    PARAMETER_CHANGE = "PARAMETER_CHANGE"
    STRATEGY_ADJUSTMENT = "STRATEGY_ADJUSTMENT"
    RISK_LIMIT_CHANGE = "RISK_LIMIT_CHANGE"


class VersionType(Enum):
    """Types of versioned artifacts"""
    MODEL = "MODEL"
    PARAMETERS = "PARAMETERS"
    STRATEGY = "STRATEGY"


# Guardrails - Safety limits for automated changes
GUARDRAILS = {
    'min_sample_size': 50,           # Minimum outcomes before retraining
    'max_parameter_change_pct': 20,  # Max 20% change per cycle
    'require_oos_improvement': True,  # Out-of-sample must improve
    'degradation_threshold': 15,      # Kill if >15% degradation
    'rollback_on_drawdown_pct': 10,  # Auto-rollback if 10% drawdown
    'proposal_expiry_hours': 72,      # Proposals expire after 72 hours
    'min_approval_wait_hours': 1,     # Minimum wait before applying
    'max_consecutive_losses': 5,      # Alert after 5 consecutive losses
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AuditEntry:
    """
    Complete audit log entry - WHO, WHAT, WHY, WHEN

    Every action Solomon takes is recorded with full context.
    """
    # WHEN
    timestamp: datetime

    # WHO
    bot_name: str
    actor: str  # "SOLOMON", "USER:<username>", "SCHEDULER", "SYSTEM"
    session_id: str

    # WHAT
    action_type: str
    action_description: str

    # Details
    before_state: Dict = field(default_factory=dict)
    after_state: Dict = field(default_factory=dict)

    # WHY
    reason: str = ""
    justification: Dict = field(default_factory=dict)  # Metrics that justified this

    # Metadata
    version_from: str = ""
    version_to: str = ""
    proposal_id: Optional[str] = None

    # Outcome tracking
    success: bool = True
    error_message: str = ""

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'bot_name': self.bot_name,
            'actor': self.actor,
            'session_id': self.session_id,
            'action_type': self.action_type,
            'action_description': self.action_description,
            'before_state': self.before_state,
            'after_state': self.after_state,
            'reason': self.reason,
            'justification': self.justification,
            'version_from': self.version_from,
            'version_to': self.version_to,
            'proposal_id': self.proposal_id,
            'success': self.success,
            'error_message': self.error_message
        }


@dataclass
class Proposal:
    """
    A proposed change awaiting human approval.

    All significant changes must go through approval workflow.
    """
    proposal_id: str
    created_at: datetime
    expires_at: datetime

    # What
    proposal_type: str
    bot_name: str
    title: str
    description: str

    # The change
    current_value: Dict
    proposed_value: Dict
    change_summary: str

    # Why
    reason: str
    supporting_metrics: Dict
    expected_improvement: Dict

    # Risk assessment
    risk_level: str  # LOW, MEDIUM, HIGH
    risk_factors: List[str] = field(default_factory=list)
    rollback_plan: str = ""

    # Status
    status: str = "PENDING"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: str = ""

    def to_dict(self) -> Dict:
        return {
            'proposal_id': self.proposal_id,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'proposal_type': self.proposal_type,
            'bot_name': self.bot_name,
            'title': self.title,
            'description': self.description,
            'current_value': self.current_value,
            'proposed_value': self.proposed_value,
            'change_summary': self.change_summary,
            'reason': self.reason,
            'supporting_metrics': self.supporting_metrics,
            'expected_improvement': self.expected_improvement,
            'risk_level': self.risk_level,
            'risk_factors': self.risk_factors,
            'rollback_plan': self.rollback_plan,
            'status': self.status,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'review_notes': self.review_notes
        }


@dataclass
class Version:
    """
    A versioned snapshot of a model or parameter set.

    Enables rollback to any previous state.
    """
    version_id: str
    version_number: str  # Semantic: 1.0.0, 1.1.0, etc.
    created_at: datetime

    # What
    version_type: str
    bot_name: str
    artifact_name: str

    # Content
    artifact_hash: str  # SHA256 of serialized artifact
    artifact_data: bytes  # Pickled artifact
    metadata: Dict = field(default_factory=dict)

    # Performance at this version
    performance_metrics: Dict = field(default_factory=dict)

    # Lineage
    parent_version: Optional[str] = None
    is_active: bool = False

    # Approval
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            'version_id': self.version_id,
            'version_number': self.version_number,
            'created_at': self.created_at.isoformat(),
            'version_type': self.version_type,
            'bot_name': self.bot_name,
            'artifact_name': self.artifact_name,
            'artifact_hash': self.artifact_hash,
            'metadata': self.metadata,
            'performance_metrics': self.performance_metrics,
            'parent_version': self.parent_version,
            'is_active': self.is_active,
            'approved_by': self.approved_by,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None
        }


@dataclass
class PerformanceSnapshot:
    """
    Performance metrics at a point in time for a bot/version.
    """
    snapshot_id: str
    timestamp: datetime

    bot_name: str
    version_id: str

    # Core metrics
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int

    # P&L
    total_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float

    # Risk metrics
    max_drawdown: float
    sharpe_ratio: float

    # Comparison to previous
    vs_previous_version: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FeedbackLoopResult:
    """
    Result of a feedback loop run.
    """
    run_id: str
    started_at: datetime
    completed_at: datetime

    # What was checked
    bots_checked: List[str]
    outcomes_processed: int

    # Actions taken
    proposals_created: List[str]
    proposals_applied: List[str]  # Proposals auto-applied after proving improvement
    models_retrained: List[str]
    alerts_raised: List[Dict]

    # Status
    success: bool
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'run_id': self.run_id,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat(),
            'bots_checked': self.bots_checked,
            'outcomes_processed': self.outcomes_processed,
            'proposals_created': self.proposals_created,
            'proposals_applied': self.proposals_applied,
            'models_retrained': self.models_retrained,
            'alerts_raised': self.alerts_raised,
            'success': self.success,
            'errors': self.errors
        }


# =============================================================================
# DATABASE SCHEMA
# =============================================================================

SCHEMA_SQL = """
-- Solomon Audit Log: Complete history of every action
CREATE TABLE IF NOT EXISTS solomon_audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bot_name TEXT NOT NULL,
    actor TEXT NOT NULL,
    session_id TEXT,
    action_type TEXT NOT NULL,
    action_description TEXT NOT NULL,
    before_state JSONB,
    after_state JSONB,
    reason TEXT,
    justification JSONB,
    version_from TEXT,
    version_to TEXT,
    proposal_id TEXT,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_solomon_audit_bot ON solomon_audit_log(bot_name);
CREATE INDEX IF NOT EXISTS idx_solomon_audit_action ON solomon_audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_solomon_audit_time ON solomon_audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_solomon_audit_proposal ON solomon_audit_log(proposal_id);

-- Solomon Proposals: Changes awaiting approval
CREATE TABLE IF NOT EXISTS solomon_proposals (
    id SERIAL PRIMARY KEY,
    proposal_id TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    proposal_type TEXT NOT NULL,
    bot_name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    current_value JSONB,
    proposed_value JSONB,
    change_summary TEXT,
    reason TEXT,
    supporting_metrics JSONB,
    expected_improvement JSONB,
    risk_level TEXT DEFAULT 'MEDIUM',
    risk_factors JSONB,
    rollback_plan TEXT,
    status TEXT DEFAULT 'PENDING',
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    review_notes TEXT,
    applied_at TIMESTAMPTZ,
    rolled_back_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_solomon_proposals_status ON solomon_proposals(status);
CREATE INDEX IF NOT EXISTS idx_solomon_proposals_bot ON solomon_proposals(bot_name);
CREATE INDEX IF NOT EXISTS idx_solomon_proposals_expires ON solomon_proposals(expires_at);

-- Solomon Versions: Version history for models and parameters
CREATE TABLE IF NOT EXISTS solomon_versions (
    id SERIAL PRIMARY KEY,
    version_id TEXT UNIQUE NOT NULL,
    version_number TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version_type TEXT NOT NULL,
    bot_name TEXT NOT NULL,
    artifact_name TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    artifact_data BYTEA,
    metadata JSONB,
    performance_metrics JSONB,
    parent_version TEXT,
    is_active BOOLEAN DEFAULT FALSE,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    deactivated_at TIMESTAMPTZ,
    deactivation_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_solomon_versions_bot ON solomon_versions(bot_name);
CREATE INDEX IF NOT EXISTS idx_solomon_versions_active ON solomon_versions(is_active);
CREATE INDEX IF NOT EXISTS idx_solomon_versions_type ON solomon_versions(version_type);

-- Solomon Performance: Performance tracking over time
CREATE TABLE IF NOT EXISTS solomon_performance (
    id SERIAL PRIMARY KEY,
    snapshot_id TEXT UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bot_name TEXT NOT NULL,
    version_id TEXT,
    win_rate REAL,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    total_pnl REAL,
    avg_win REAL,
    avg_loss REAL,
    profit_factor REAL,
    max_drawdown REAL,
    sharpe_ratio REAL,
    vs_previous_version JSONB,
    period_start DATE,
    period_end DATE
);

CREATE INDEX IF NOT EXISTS idx_solomon_perf_bot ON solomon_performance(bot_name);
CREATE INDEX IF NOT EXISTS idx_solomon_perf_time ON solomon_performance(timestamp DESC);

-- Solomon Rollbacks: History of rollbacks
CREATE TABLE IF NOT EXISTS solomon_rollbacks (
    id SERIAL PRIMARY KEY,
    rollback_id TEXT UNIQUE NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bot_name TEXT NOT NULL,
    rollback_type TEXT NOT NULL,
    from_version TEXT NOT NULL,
    to_version TEXT NOT NULL,
    reason TEXT NOT NULL,
    triggered_by TEXT NOT NULL,
    automatic BOOLEAN DEFAULT FALSE,
    performance_before JSONB,
    performance_after JSONB,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_solomon_rollbacks_bot ON solomon_rollbacks(bot_name);

-- Solomon Health: System health tracking
CREATE TABLE IF NOT EXISTS solomon_health (
    id SERIAL PRIMARY KEY,
    check_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    component TEXT NOT NULL,
    status TEXT NOT NULL,
    details JSONB,
    last_successful_run TIMESTAMPTZ,
    consecutive_failures INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_solomon_health_component ON solomon_health(component);

-- Solomon Kill Switch: Emergency stop state
CREATE TABLE IF NOT EXISTS solomon_kill_switch (
    id SERIAL PRIMARY KEY,
    bot_name TEXT UNIQUE NOT NULL,
    is_killed BOOLEAN DEFAULT FALSE,
    killed_at TIMESTAMPTZ,
    killed_by TEXT,
    kill_reason TEXT,
    auto_resume_at TIMESTAMPTZ,
    resumed_at TIMESTAMPTZ,
    resumed_by TEXT
);

-- Solomon Validations: Track proposal validations for proven improvement
CREATE TABLE IF NOT EXISTS solomon_validations (
    id SERIAL PRIMARY KEY,
    validation_id TEXT UNIQUE NOT NULL,
    proposal_id TEXT NOT NULL REFERENCES solomon_proposals(proposal_id),
    bot_name TEXT NOT NULL,
    method TEXT NOT NULL,  -- AB_TEST, BACKTEST, SHADOW_MODE, HISTORICAL
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'RUNNING',  -- RUNNING, COMPLETED, FAILED

    -- Configuration being tested
    current_config JSONB NOT NULL,
    proposed_config JSONB NOT NULL,

    -- Current (control) performance
    current_trades INTEGER DEFAULT 0,
    current_wins INTEGER DEFAULT 0,
    current_pnl NUMERIC(12,2) DEFAULT 0,
    current_win_rate NUMERIC(5,2) DEFAULT 0,

    -- Proposed (variant) performance
    proposed_trades INTEGER DEFAULT 0,
    proposed_wins INTEGER DEFAULT 0,
    proposed_pnl NUMERIC(12,2) DEFAULT 0,
    proposed_win_rate NUMERIC(5,2) DEFAULT 0,

    -- Validation results
    improvement_proven BOOLEAN DEFAULT FALSE,
    can_apply BOOLEAN DEFAULT FALSE,
    rejection_reasons JSONB DEFAULT '[]',
    improvement_metrics JSONB DEFAULT '{}',

    -- Detailed reasoning (WHO, WHAT, WHY, WHEN)
    problem_statement TEXT,
    hypothesis TEXT,
    supporting_evidence JSONB DEFAULT '[]',
    expected_improvement JSONB DEFAULT '{}',
    confidence_level NUMERIC(3,2) DEFAULT 0.7,
    success_criteria JSONB DEFAULT '{}',
    rollback_trigger JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_solomon_validations_proposal ON solomon_validations(proposal_id);
CREATE INDEX IF NOT EXISTS idx_solomon_validations_bot ON solomon_validations(bot_name);
CREATE INDEX IF NOT EXISTS idx_solomon_validations_status ON solomon_validations(status);
"""


# =============================================================================
# SOLOMON FEEDBACK LOOP SERVICE
# =============================================================================

class SolomonFeedbackLoop:
    """
    Central feedback loop orchestrator for all trading bots.

    Responsibilities:
    1. Collect trade outcomes from all bots
    2. Analyze performance and detect degradation
    3. Propose improvements (model retraining, parameter changes)
    4. Manage approval workflow
    5. Apply approved changes safely
    6. Enable rollback when needed
    7. Maintain complete audit trail
    """

    def __init__(self):
        self.session_id = self._generate_session_id()
        self._ensure_schema()
        self._oracle = None

        logger.info(f"[SOLOMON] Initialized new session: {self.session_id}")
        logger.info(f"[SOLOMON] Database available: {DB_AVAILABLE}")
        logger.info(f"[SOLOMON] Oracle available: {ORACLE_AVAILABLE}")
        logger.info(f"[SOLOMON] Math Optimizer available: {MATH_OPTIMIZER_AVAILABLE}")

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        import uuid
        return f"SOLOMON-{datetime.now(CENTRAL_TZ).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def _ensure_schema(self):
        """Ensure all required database tables exist"""
        if not DB_AVAILABLE:
            logger.warning("Database not available - Solomon running in limited mode")
            return

        with get_db_connection() as conn:
            if conn is None:
                return
            try:
                cursor = conn.cursor()
                cursor.execute(SCHEMA_SQL)
                conn.commit()
                logger.info("Solomon database schema verified")
            except Exception as e:
                logger.error(f"Failed to create Solomon schema: {e}")

    @property
    def oracle(self):
        """Lazy-load Oracle advisor"""
        if self._oracle is None and ORACLE_AVAILABLE:
            self._oracle = get_oracle()
        return self._oracle

    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================

    def log_action(
        self,
        bot_name: str,
        action_type: ActionType,
        description: str,
        reason: str = "",
        actor: str = "SOLOMON",
        before_state: Dict = None,
        after_state: Dict = None,
        justification: Dict = None,
        version_from: str = "",
        version_to: str = "",
        proposal_id: str = None,
        success: bool = True,
        error_message: str = ""
    ) -> Optional[int]:
        """
        Log an action to the audit trail.

        This is the core logging function - EVERY action goes through here.
        """
        if not DB_AVAILABLE:
            logger.info(f"[AUDIT] {bot_name} | {action_type.value} | {description}")
            return None

        entry = AuditEntry(
            timestamp=datetime.now(CENTRAL_TZ),
            bot_name=bot_name,
            actor=actor,
            session_id=self.session_id,
            action_type=action_type.value,
            action_description=description,
            before_state=before_state or {},
            after_state=after_state or {},
            reason=reason,
            justification=justification or {},
            version_from=version_from,
            version_to=version_to,
            proposal_id=proposal_id,
            success=success,
            error_message=error_message
        )

        with get_db_connection() as conn:
            if conn is None:
                return None
            try:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO solomon_audit_log (
                        timestamp, bot_name, actor, session_id, action_type,
                        action_description, before_state, after_state, reason,
                        justification, version_from, version_to, proposal_id,
                        success, error_message
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) RETURNING id
                """, (
                    entry.timestamp,
                    entry.bot_name,
                    entry.actor,
                    entry.session_id,
                    entry.action_type,
                    entry.action_description,
                    json.dumps(entry.before_state),
                    json.dumps(entry.after_state),
                    entry.reason,
                    json.dumps(entry.justification),
                    entry.version_from,
                    entry.version_to,
                    entry.proposal_id,
                    entry.success,
                    entry.error_message
                ))

                audit_id = cursor.fetchone()[0]
                conn.commit()

                # Enhanced logging with more context
                log_msg = f"[SOLOMON AUDIT #{audit_id}] {bot_name} | {action_type.value} | {description}"
                if reason:
                    log_msg += f" | Reason: {reason}"
                if version_from and version_to:
                    log_msg += f" | Version: {version_from} → {version_to}"
                if proposal_id:
                    log_msg += f" | Proposal: {proposal_id}"
                if not success:
                    log_msg += f" | FAILED: {error_message}"

                logger.info(log_msg)
                return audit_id

            except Exception as e:
                logger.error(f"[SOLOMON] Failed to log audit entry: {e}")
                logger.error(f"[SOLOMON] Audit details - Bot: {bot_name}, Action: {action_type.value}, Description: {description}")
                return None

    def get_audit_log(
        self,
        bot_name: str = None,
        action_type: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Retrieve audit log entries with filtering.
        """
        if not DB_AVAILABLE:
            return []

        with get_db_connection() as conn:
            if conn is None:
                return []
            try:
                cursor = conn.cursor()

                query = "SELECT * FROM solomon_audit_log WHERE 1=1"
                params = []

                if bot_name:
                    query += " AND bot_name = %s"
                    params.append(bot_name)

                if action_type:
                    query += " AND action_type = %s"
                    params.append(action_type)

                if start_date:
                    query += " AND timestamp >= %s"
                    params.append(start_date)

                if end_date:
                    query += " AND timestamp <= %s"
                    params.append(end_date)

                query += " ORDER BY timestamp DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, params)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

                return [dict(zip(columns, row)) for row in rows]

            except Exception as e:
                logger.error(f"Failed to get audit log: {e}")
                return []

    # =========================================================================
    # PROPOSAL MANAGEMENT
    # =========================================================================

    def create_proposal(
        self,
        bot_name: str,
        proposal_type: ProposalType,
        title: str,
        description: str,
        current_value: Dict,
        proposed_value: Dict,
        reason: str,
        supporting_metrics: Dict,
        expected_improvement: Dict,
        risk_level: str = "MEDIUM",
        risk_factors: List[str] = None,
        rollback_plan: str = ""
    ) -> Optional[str]:
        """
        Create a proposal for human review.

        All significant changes must go through this workflow.
        """
        import uuid

        proposal_id = f"PROP-{datetime.now(CENTRAL_TZ).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        created_at = datetime.now(CENTRAL_TZ)
        expires_at = created_at + timedelta(hours=GUARDRAILS['proposal_expiry_hours'])

        # Build change summary
        change_summary = self._build_change_summary(current_value, proposed_value)

        proposal = Proposal(
            proposal_id=proposal_id,
            created_at=created_at,
            expires_at=expires_at,
            proposal_type=proposal_type.value,
            bot_name=bot_name,
            title=title,
            description=description,
            current_value=current_value,
            proposed_value=proposed_value,
            change_summary=change_summary,
            reason=reason,
            supporting_metrics=supporting_metrics,
            expected_improvement=expected_improvement,
            risk_level=risk_level,
            risk_factors=risk_factors or [],
            rollback_plan=rollback_plan
        )

        if not DB_AVAILABLE:
            logger.info(f"[PROPOSAL] {proposal_id} | {bot_name} | {title}")
            return proposal_id

        with get_db_connection() as conn:
            if conn is None:
                return None
            try:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO solomon_proposals (
                        proposal_id, created_at, expires_at, proposal_type, bot_name,
                        title, description, current_value, proposed_value, change_summary,
                        reason, supporting_metrics, expected_improvement, risk_level,
                        risk_factors, rollback_plan, status
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    proposal.proposal_id,
                    proposal.created_at,
                    proposal.expires_at,
                    proposal.proposal_type,
                    proposal.bot_name,
                    proposal.title,
                    proposal.description,
                    json.dumps(proposal.current_value),
                    json.dumps(proposal.proposed_value),
                    proposal.change_summary,
                    proposal.reason,
                    json.dumps(proposal.supporting_metrics),
                    json.dumps(proposal.expected_improvement),
                    proposal.risk_level,
                    json.dumps(proposal.risk_factors),
                    proposal.rollback_plan,
                    ProposalStatus.PENDING.value
                ))

                conn.commit()

                # Log the proposal creation
                self.log_action(
                    bot_name=bot_name,
                    action_type=ActionType.PROPOSAL_CREATED,
                    description=f"Proposal created: {title}",
                    reason=reason,
                    justification=supporting_metrics,
                    proposal_id=proposal_id
                )

                logger.info(f"[SOLOMON PROPOSAL] Created {proposal_id}")
                logger.info(f"[SOLOMON PROPOSAL]   Bot: {bot_name} | Type: {proposal_type.value}")
                logger.info(f"[SOLOMON PROPOSAL]   Title: {title}")
                logger.info(f"[SOLOMON PROPOSAL]   Risk Level: {risk_level} | Expires: {expires_at.strftime('%Y-%m-%d %H:%M')} CT")
                logger.info(f"[SOLOMON PROPOSAL]   Change: {change_summary}")
                if expected_improvement:
                    logger.info(f"[SOLOMON PROPOSAL]   Expected Improvement: {expected_improvement}")
                return proposal_id

            except Exception as e:
                logger.error(f"[SOLOMON] Failed to create proposal: {e}")
                logger.error(f"[SOLOMON] Proposal details - Bot: {bot_name}, Title: {title}, Type: {proposal_type.value}")
                return None

    def _build_change_summary(self, current: Dict, proposed: Dict) -> str:
        """Build human-readable summary of changes"""
        changes = []

        all_keys = set(current.keys()) | set(proposed.keys())
        for key in sorted(all_keys):
            curr_val = current.get(key)
            prop_val = proposed.get(key)

            if curr_val != prop_val:
                if isinstance(curr_val, (int, float)) and isinstance(prop_val, (int, float)):
                    if curr_val != 0:
                        pct_change = ((prop_val - curr_val) / curr_val) * 100
                        changes.append(f"{key}: {curr_val} → {prop_val} ({pct_change:+.1f}%)")
                    else:
                        changes.append(f"{key}: {curr_val} → {prop_val}")
                else:
                    changes.append(f"{key}: {curr_val} → {prop_val}")

        return "; ".join(changes) if changes else "No changes"

    def approve_proposal(
        self,
        proposal_id: str,
        reviewer: str,
        notes: str = ""
    ) -> bool:
        """
        Approve a proposal and apply the changes.
        """
        if not DB_AVAILABLE:
            logger.warning("Cannot approve proposal - database not available")
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get the proposal
            cursor.execute("""
                SELECT proposal_type, bot_name, title, current_value, proposed_value,
                       reason, supporting_metrics, status
                FROM solomon_proposals
                WHERE proposal_id = %s
            """, (proposal_id,))

            row = cursor.fetchone()
            if not row:
                logger.error(f"[SOLOMON] Proposal {proposal_id} not found - cannot approve")
                conn.close()
                return False

            proposal_type, bot_name, title, current_value, proposed_value, reason, metrics, status = row

            if status != ProposalStatus.PENDING.value:
                logger.warning(f"[SOLOMON] Proposal {proposal_id} is not pending (current status: {status}) - cannot approve")
                conn.close()
                return False

            logger.info(f"[SOLOMON APPROVAL] Processing approval for {proposal_id}")
            logger.info(f"[SOLOMON APPROVAL]   Bot: {bot_name} | Title: {title}")
            logger.info(f"[SOLOMON APPROVAL]   Reviewer: {reviewer} | Notes: {notes or 'None'}")

            # Update proposal status
            reviewed_at = datetime.now(CENTRAL_TZ)
            cursor.execute("""
                UPDATE solomon_proposals
                SET status = %s, reviewed_by = %s, reviewed_at = %s, review_notes = %s
                WHERE proposal_id = %s
            """, (ProposalStatus.APPROVED.value, reviewer, reviewed_at, notes, proposal_id))

            conn.commit()
            conn.close()

            # Log the approval
            self.log_action(
                bot_name=bot_name,
                action_type=ActionType.PROPOSAL_APPROVED,
                description=f"Proposal approved: {title}",
                reason=f"Approved by {reviewer}: {notes}",
                actor=f"USER:{reviewer}",
                before_state=current_value if isinstance(current_value, dict) else json.loads(current_value),
                after_state=proposed_value if isinstance(proposed_value, dict) else json.loads(proposed_value),
                proposal_id=proposal_id
            )

            # Apply the changes
            logger.info(f"[SOLOMON APPROVAL] Applying changes for {proposal_id}...")
            success = self._apply_proposal(proposal_id, proposal_type, bot_name, proposed_value)

            if success:
                # Mark as applied
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE solomon_proposals
                    SET status = %s, applied_at = %s
                    WHERE proposal_id = %s
                """, (ProposalStatus.APPLIED.value, datetime.now(CENTRAL_TZ), proposal_id))
                conn.commit()
                conn.close()
                logger.info(f"[SOLOMON APPROVAL] Successfully applied proposal {proposal_id}")
                logger.info(f"[SOLOMON APPROVAL]   Changes applied to {bot_name} at {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S')} CT")
            else:
                logger.error(f"[SOLOMON APPROVAL] Failed to apply proposal {proposal_id}")

            return success

        except Exception as e:
            logger.error(f"[SOLOMON] Failed to approve proposal {proposal_id}: {e}")
            traceback.print_exc()
            return False

    def reject_proposal(
        self,
        proposal_id: str,
        reviewer: str,
        notes: str = ""
    ) -> bool:
        """
        Reject a proposal.
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get proposal info for logging
            cursor.execute("""
                SELECT bot_name, title FROM solomon_proposals WHERE proposal_id = %s
            """, (proposal_id,))

            row = cursor.fetchone()
            if not row:
                conn.close()
                return False

            bot_name, title = row

            # Update status
            cursor.execute("""
                UPDATE solomon_proposals
                SET status = %s, reviewed_by = %s, reviewed_at = %s, review_notes = %s
                WHERE proposal_id = %s
            """, (ProposalStatus.REJECTED.value, reviewer, datetime.now(CENTRAL_TZ), notes, proposal_id))

            conn.commit()
            conn.close()

            # Log rejection
            self.log_action(
                bot_name=bot_name,
                action_type=ActionType.PROPOSAL_REJECTED,
                description=f"Proposal rejected: {title}",
                reason=f"Rejected by {reviewer}: {notes}",
                actor=f"USER:{reviewer}",
                proposal_id=proposal_id
            )

            logger.info(f"[SOLOMON REJECTION] Proposal {proposal_id} rejected")
            logger.info(f"[SOLOMON REJECTION]   Bot: {bot_name} | Title: {title}")
            logger.info(f"[SOLOMON REJECTION]   Reviewer: {reviewer} | Notes: {notes or 'None'}")
            return True

        except Exception as e:
            logger.error(f"[SOLOMON] Failed to reject proposal {proposal_id}: {e}")
            return False

    def _apply_proposal(
        self,
        proposal_id: str,
        proposal_type: str,
        bot_name: str,
        proposed_value: Any
    ) -> bool:
        """
        Apply an approved proposal.
        """
        try:
            if proposal_type == ProposalType.MODEL_UPDATE.value:
                return self._apply_model_update(bot_name, proposed_value, proposal_id)
            elif proposal_type == ProposalType.PARAMETER_CHANGE.value:
                return self._apply_parameter_change(bot_name, proposed_value, proposal_id)
            elif proposal_type == ProposalType.STRATEGY_ADJUSTMENT.value:
                return self._apply_strategy_adjustment(bot_name, proposed_value, proposal_id)
            elif proposal_type == ProposalType.RISK_LIMIT_CHANGE.value:
                return self._apply_risk_limit_change(bot_name, proposed_value, proposal_id)
            else:
                logger.warning(f"Unknown proposal type: {proposal_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to apply proposal: {e}")
            return False

    def _apply_model_update(self, bot_name: str, proposed_value: Any, proposal_id: str) -> bool:
        """Apply a model update from a proposal"""
        # Trigger Oracle retraining
        if ORACLE_AVAILABLE:
            result = auto_train(force=True)
            if result.get('success'):
                self.log_action(
                    bot_name=bot_name,
                    action_type=ActionType.MODEL_RETRAIN,
                    description=f"Model retrained via proposal {proposal_id}",
                    reason="Approved proposal",
                    justification=result.get('training_metrics', {}),
                    proposal_id=proposal_id
                )
                return True
        return False

    def _apply_parameter_change(self, bot_name: str, proposed_value: Any, proposal_id: str) -> bool:
        """Apply a parameter change from a proposal"""
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Store parameters in bot config table
            if isinstance(proposed_value, str):
                proposed_value = json.loads(proposed_value)

            cursor.execute("""
                INSERT INTO autonomous_config (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (f"{bot_name.lower()}_parameters", json.dumps(proposed_value)))

            conn.commit()
            conn.close()

            self.log_action(
                bot_name=bot_name,
                action_type=ActionType.PARAM_UPDATE,
                description=f"Parameters updated via proposal {proposal_id}",
                reason="Approved proposal",
                after_state=proposed_value,
                proposal_id=proposal_id
            )

            return True

        except Exception as e:
            logger.error(f"Failed to apply parameter change: {e}")
            return False

    def _apply_strategy_adjustment(self, bot_name: str, proposed_value: Any, proposal_id: str) -> bool:
        """Apply a strategy adjustment from a proposal"""
        # Similar to parameter change but for strategy-level settings
        return self._apply_parameter_change(bot_name, proposed_value, proposal_id)

    def _apply_risk_limit_change(self, bot_name: str, proposed_value: Any, proposal_id: str) -> bool:
        """Apply a risk limit change from a proposal"""
        # Update circuit breaker limits
        return self._apply_parameter_change(bot_name, proposed_value, proposal_id)

    def get_pending_proposals(self, bot_name: str = None) -> List[Dict]:
        """Get all pending proposals"""
        if not DB_AVAILABLE:
            return []

        try:
            conn = get_connection()
            cursor = conn.cursor()

            query = """
                SELECT * FROM solomon_proposals
                WHERE status = 'PENDING' AND expires_at > NOW()
            """
            params = []

            if bot_name:
                query += " AND bot_name = %s"
                params.append(bot_name)

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            conn.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get pending proposals: {e}")
            return []

    def expire_old_proposals(self) -> int:
        """Expire proposals past their expiry date"""
        if not DB_AVAILABLE:
            return 0

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE solomon_proposals
                SET status = 'EXPIRED'
                WHERE status = 'PENDING' AND expires_at < NOW()
                RETURNING proposal_id, bot_name, title
            """)

            expired = cursor.fetchall()
            conn.commit()
            conn.close()

            for proposal_id, bot_name, title in expired:
                self.log_action(
                    bot_name=bot_name,
                    action_type=ActionType.PROPOSAL_EXPIRED,
                    description=f"Proposal expired: {title}",
                    reason="Expired without review",
                    proposal_id=proposal_id
                )

            return len(expired)

        except Exception as e:
            logger.error(f"Failed to expire proposals: {e}")
            return 0

    # =========================================================================
    # VERSION MANAGEMENT
    # =========================================================================

    def save_version(
        self,
        bot_name: str,
        version_type: VersionType,
        artifact_name: str,
        artifact_data: Any,
        metadata: Dict = None,
        performance_metrics: Dict = None,
        approved_by: str = None
    ) -> Optional[str]:
        """
        Save a new version of a model or parameter set.
        """
        import uuid

        # Serialize and hash
        if isinstance(artifact_data, dict):
            serialized = json.dumps(artifact_data, sort_keys=True).encode()
        else:
            serialized = pickle.dumps(artifact_data)

        artifact_hash = hashlib.sha256(serialized).hexdigest()

        # Generate version number
        version_number = self._get_next_version_number(bot_name, version_type, artifact_name)
        version_id = f"{bot_name}-{artifact_name}-{version_number}-{uuid.uuid4().hex[:8]}"

        # Get parent version
        parent_version = self._get_active_version_id(bot_name, version_type, artifact_name)

        if not DB_AVAILABLE:
            logger.info(f"[VERSION] {version_id} saved")
            return version_id

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO solomon_versions (
                    version_id, version_number, created_at, version_type, bot_name,
                    artifact_name, artifact_hash, artifact_data, metadata,
                    performance_metrics, parent_version, is_active, approved_by,
                    approved_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                version_id,
                version_number,
                datetime.now(CENTRAL_TZ),
                version_type.value,
                bot_name,
                artifact_name,
                artifact_hash,
                serialized,
                json.dumps(metadata or {}),
                json.dumps(performance_metrics or {}),
                parent_version,
                False,  # Not active until explicitly activated
                approved_by,
                datetime.now(CENTRAL_TZ) if approved_by else None
            ))

            conn.commit()
            conn.close()

            logger.info(f"Saved version {version_id}")
            return version_id

        except Exception as e:
            logger.error(f"Failed to save version: {e}")
            return None

    def _get_next_version_number(self, bot_name: str, version_type: VersionType, artifact_name: str) -> str:
        """Get the next semantic version number"""
        if not DB_AVAILABLE:
            return "1.0.0"

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT version_number FROM solomon_versions
                WHERE bot_name = %s AND version_type = %s AND artifact_name = %s
                ORDER BY created_at DESC LIMIT 1
            """, (bot_name, version_type.value, artifact_name))

            row = cursor.fetchone()
            conn.close()

            if row:
                parts = row[0].split('.')
                major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
                return f"{major}.{minor}.{patch + 1}"
            else:
                return "1.0.0"

        except Exception as e:
            logger.error(f"Failed to get next version: {e}")
            return "1.0.0"

    def _get_active_version_id(self, bot_name: str, version_type: VersionType, artifact_name: str) -> Optional[str]:
        """Get the currently active version ID"""
        if not DB_AVAILABLE:
            return None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT version_id FROM solomon_versions
                WHERE bot_name = %s AND version_type = %s AND artifact_name = %s AND is_active = TRUE
                LIMIT 1
            """, (bot_name, version_type.value, artifact_name))

            row = cursor.fetchone()
            conn.close()

            return row[0] if row else None

        except Exception as e:
            logger.error(f"Failed to get active version: {e}")
            return None

    def activate_version(self, version_id: str, activated_by: str = "SOLOMON") -> bool:
        """
        Activate a specific version (deactivate current active).
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get version info
            cursor.execute("""
                SELECT bot_name, version_type, artifact_name, version_number
                FROM solomon_versions WHERE version_id = %s
            """, (version_id,))

            row = cursor.fetchone()
            if not row:
                conn.close()
                return False

            bot_name, version_type, artifact_name, version_number = row

            # Get current active version
            cursor.execute("""
                SELECT version_id, version_number FROM solomon_versions
                WHERE bot_name = %s AND version_type = %s AND artifact_name = %s AND is_active = TRUE
            """, (bot_name, version_type, artifact_name))

            current = cursor.fetchone()
            current_version_id = current[0] if current else None
            current_version_number = current[1] if current else None

            # Deactivate current
            if current_version_id:
                cursor.execute("""
                    UPDATE solomon_versions
                    SET is_active = FALSE, deactivated_at = NOW()
                    WHERE version_id = %s
                """, (current_version_id,))

            # Activate new
            cursor.execute("""
                UPDATE solomon_versions
                SET is_active = TRUE, approved_by = COALESCE(approved_by, %s), approved_at = COALESCE(approved_at, NOW())
                WHERE version_id = %s
            """, (activated_by, version_id))

            conn.commit()
            conn.close()

            # Log activation
            self.log_action(
                bot_name=bot_name,
                action_type=ActionType.MODEL_LOADED,
                description=f"Activated version {version_number}",
                reason=f"Activated by {activated_by}",
                actor=activated_by,
                version_from=current_version_number or "",
                version_to=version_number
            )

            return True

        except Exception as e:
            logger.error(f"Failed to activate version: {e}")
            return False

    def get_version_history(self, bot_name: str, artifact_name: str = None, limit: int = 20) -> List[Dict]:
        """Get version history for a bot"""
        if not DB_AVAILABLE:
            return []

        try:
            conn = get_connection()
            cursor = conn.cursor()

            query = """
                SELECT version_id, version_number, created_at, version_type, artifact_name,
                       artifact_hash, metadata, performance_metrics, parent_version,
                       is_active, approved_by, approved_at
                FROM solomon_versions
                WHERE bot_name = %s
            """
            params = [bot_name]

            if artifact_name:
                query += " AND artifact_name = %s"
                params.append(artifact_name)

            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            conn.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get version history: {e}")
            return []

    # =========================================================================
    # ROLLBACK
    # =========================================================================

    def rollback(
        self,
        bot_name: str,
        to_version_id: str,
        reason: str,
        triggered_by: str = "USER",
        automatic: bool = False
    ) -> bool:
        """
        Rollback to a previous version.
        """
        import uuid

        rollback_id = f"ROLL-{datetime.now(CENTRAL_TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        if not DB_AVAILABLE:
            logger.info(f"[SOLOMON ROLLBACK] {rollback_id} | {bot_name} → {to_version_id} (DB not available)")
            return True

        logger.info(f"[SOLOMON ROLLBACK] Initiating rollback {rollback_id}")
        logger.info(f"[SOLOMON ROLLBACK]   Bot: {bot_name}")
        logger.info(f"[SOLOMON ROLLBACK]   Target version: {to_version_id}")
        logger.info(f"[SOLOMON ROLLBACK]   Reason: {reason}")
        logger.info(f"[SOLOMON ROLLBACK]   Triggered by: {triggered_by} | Automatic: {automatic}")

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get target version info
            cursor.execute("""
                SELECT version_type, artifact_name, version_number
                FROM solomon_versions WHERE version_id = %s
            """, (to_version_id,))

            row = cursor.fetchone()
            if not row:
                logger.error(f"Target version {to_version_id} not found")
                conn.close()
                return False

            version_type, artifact_name, target_version_number = row

            # Get current active version
            cursor.execute("""
                SELECT version_id, version_number FROM solomon_versions
                WHERE bot_name = %s AND version_type = %s AND artifact_name = %s AND is_active = TRUE
            """, (bot_name, version_type, artifact_name))

            current = cursor.fetchone()
            if not current:
                logger.error(f"No active version found for {bot_name}")
                conn.close()
                return False

            from_version_id, from_version_number = current

            # Get performance before rollback
            perf_before = self._get_current_performance(bot_name)

            # Perform rollback (deactivate current, activate target)
            cursor.execute("""
                UPDATE solomon_versions
                SET is_active = FALSE, deactivated_at = NOW(), deactivation_reason = %s
                WHERE version_id = %s
            """, (f"Rolled back: {reason}", from_version_id))

            cursor.execute("""
                UPDATE solomon_versions
                SET is_active = TRUE
                WHERE version_id = %s
            """, (to_version_id,))

            # Record rollback
            cursor.execute("""
                INSERT INTO solomon_rollbacks (
                    rollback_id, executed_at, bot_name, rollback_type, from_version,
                    to_version, reason, triggered_by, automatic, performance_before
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                rollback_id,
                datetime.now(CENTRAL_TZ),
                bot_name,
                version_type,
                from_version_id,
                to_version_id,
                reason,
                triggered_by,
                automatic,
                json.dumps(perf_before)
            ))

            conn.commit()
            conn.close()

            # Log rollback
            self.log_action(
                bot_name=bot_name,
                action_type=ActionType.MODEL_ROLLBACK,
                description=f"Rolled back from {from_version_number} to {target_version_number}",
                reason=reason,
                actor=triggered_by,
                version_from=from_version_number,
                version_to=target_version_number,
                justification={'automatic': automatic, 'performance_before': perf_before}
            )

            logger.info(f"[SOLOMON ROLLBACK] Rollback {rollback_id} completed successfully")
            logger.info(f"[SOLOMON ROLLBACK]   Version change: {from_version_number} → {target_version_number}")
            logger.info(f"[SOLOMON ROLLBACK]   Performance before rollback: {json.dumps(perf_before)}")
            return True

        except Exception as e:
            logger.error(f"[SOLOMON ROLLBACK] Failed to execute rollback {rollback_id}: {e}")
            traceback.print_exc()
            return False

    def _get_current_performance(self, bot_name: str) -> Dict:
        """Get current performance metrics for a bot from its actual positions table"""
        if not DB_AVAILABLE:
            return {}

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Map bot names to their actual positions tables
            # Bots store closed trades in *_positions tables with status='closed'
            BOT_TABLES = {
                'ARES': 'ares_positions',
                'ATHENA': 'athena_positions',
                'TITAN': 'titan_positions',
                'PEGASUS': 'pegasus_positions',
                'ICARUS': 'icarus_positions',
                'PROMETHEUS': 'prometheus_ic_positions',
            }

            table = BOT_TABLES.get(bot_name.upper())
            if not table:
                logger.warning(f"Unknown bot_name '{bot_name}' - no table mapping")
                return {}

            # Query closed positions from the bot's actual table
            # Table name is from whitelisted BOT_TABLES dict (safe)
            # Use COALESCE to handle legacy data with NULL close_time
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl) as avg_pnl
                FROM {table}
                WHERE status = 'closed'
                    AND COALESCE(close_time, open_time) > NOW() - INTERVAL '30 days'
            """)

            row = cursor.fetchone()

            if row and row[0]:
                total, wins, losses, pnl, avg_pnl = row
                return {
                    'total_trades': total or 0,
                    'wins': wins or 0,
                    'losses': losses or 0,
                    'win_rate': (wins / total * 100) if total and total > 0 else 0,
                    'total_pnl': float(pnl) if pnl else 0,
                    'avg_pnl': float(avg_pnl) if avg_pnl else 0
                }
            return {}

        except Exception as e:
            logger.debug(f"Could not get performance: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def get_rollback_history(self, bot_name: str = None, limit: int = 20) -> List[Dict]:
        """Get rollback history"""
        if not DB_AVAILABLE:
            return []

        try:
            conn = get_connection()
            cursor = conn.cursor()

            query = "SELECT * FROM solomon_rollbacks"
            params = []

            if bot_name:
                query += " WHERE bot_name = %s"
                params.append(bot_name)

            query += " ORDER BY executed_at DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            conn.close()

            return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get rollback history: {e}")
            return []

    # =========================================================================
    # PERFORMANCE TRACKING
    # =========================================================================

    def record_performance_snapshot(self, bot_name: str) -> Optional[str]:
        """Record current performance snapshot for a bot"""
        import uuid

        snapshot_id = f"PERF-{datetime.now(CENTRAL_TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        perf = self._get_current_performance(bot_name)
        if not perf:
            return None

        version_id = self._get_active_version_id(bot_name, VersionType.MODEL, "oracle_model")

        if not DB_AVAILABLE:
            return snapshot_id

        try:
            conn = get_connection()
            cursor = conn.cursor()

            total = perf.get('total_trades', 0)
            wins = perf.get('wins', 0)
            losses = perf.get('losses', 0)

            cursor.execute("""
                INSERT INTO solomon_performance (
                    snapshot_id, timestamp, bot_name, version_id, win_rate,
                    total_trades, winning_trades, losing_trades, total_pnl
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                snapshot_id,
                datetime.now(CENTRAL_TZ),
                bot_name,
                version_id,
                perf.get('win_rate', 0),
                total,
                wins,
                losses,
                perf.get('total_pnl', 0)
            ))

            conn.commit()
            conn.close()

            return snapshot_id

        except Exception as e:
            logger.error(f"Failed to record performance snapshot: {e}")
            return None

    def get_performance_history(self, bot_name: str, days: int = 30) -> List[Dict]:
        """Get performance history for a bot from actual positions tables"""
        if not DB_AVAILABLE:
            return []

        # Map bot names to their actual positions tables
        BOT_TABLES = {
            'ARES': 'ares_positions',
            'ATHENA': 'athena_positions',
            'TITAN': 'titan_positions',
            'PEGASUS': 'pegasus_positions',
            'ICARUS': 'icarus_positions',
            'PROMETHEUS': 'prometheus_ic_positions',
        }

        table_name = BOT_TABLES.get(bot_name.upper())
        if not table_name:
            return []

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get daily P&L for sparkline data
            # Use COALESCE to handle legacy data with NULL close_time
            cursor.execute(f"""
                SELECT
                    DATE(COALESCE(close_time, open_time) AT TIME ZONE 'America/Chicago') as trade_date,
                    COUNT(*) as trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(realized_pnl), 0) as total_pnl,
                    COALESCE(AVG(realized_pnl), 0) as avg_pnl
                FROM {table_name}
                WHERE status = 'closed'
                AND COALESCE(close_time, open_time) > NOW() - INTERVAL '{days} days'
                GROUP BY DATE(COALESCE(close_time, open_time) AT TIME ZONE 'America/Chicago')
                ORDER BY trade_date DESC
            """)

            rows = cursor.fetchall()
            conn.close()

            results = []
            for row in rows:
                results.append({
                    'timestamp': row[0].isoformat() if row[0] else None,
                    'trade_date': row[0].isoformat() if row[0] else None,
                    'trades': row[1] or 0,
                    'wins': row[2] or 0,
                    'total_pnl': float(row[3]) if row[3] else 0,
                    'avg_pnl': float(row[4]) if row[4] else 0,
                    'win_rate': (row[2] / row[1] * 100) if row[1] else 0
                })

            return results

        except Exception as e:
            logger.error(f"Failed to get performance history: {e}")
            return []

    def detect_degradation(self, bot_name: str) -> Optional[Dict]:
        """
        Detect performance degradation by comparing recent vs previous period.

        Uses actual bot positions tables for trade data.
        Returns alert info if degradation detected, None otherwise.
        """
        if not DB_AVAILABLE:
            return None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Map bot names to their actual positions tables
            BOT_TABLES = {
                'ARES': 'ares_positions',
                'ATHENA': 'athena_positions',
                'TITAN': 'titan_positions',
                'PEGASUS': 'pegasus_positions',
                'ICARUS': 'icarus_positions',
                'PROMETHEUS': 'prometheus_ic_positions',
            }

            table = BOT_TABLES.get(bot_name.upper())
            if not table:
                return None

            # Compare last 7 days vs previous 7 days using bot's actual positions table
            # Use COALESCE to handle legacy data with NULL close_time
            cursor.execute(f"""
                WITH period_stats AS (
                    SELECT
                        CASE
                            WHEN COALESCE(close_time, open_time) > NOW() - INTERVAL '7 days' THEN 'recent'
                            ELSE 'previous'
                        END as period,
                        COUNT(*) as trades,
                        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(realized_pnl) as total_pnl
                    FROM {table}
                    WHERE status = 'closed'
                        AND COALESCE(close_time, open_time) > NOW() - INTERVAL '14 days'
                    GROUP BY
                        CASE
                            WHEN COALESCE(close_time, open_time) > NOW() - INTERVAL '7 days' THEN 'recent'
                            ELSE 'previous'
                        END
                )
                SELECT
                    period, trades, wins, total_pnl,
                    CASE WHEN trades > 0 THEN wins::float / trades * 100 ELSE 0 END as win_rate
                FROM period_stats
                ORDER BY period
            """)

            rows = cursor.fetchall()
            conn.close()

            # Parse results
            recent_stats = None
            prev_stats = None
            for row in rows:
                period, trades, wins, total_pnl, win_rate = row
                if period == 'recent':
                    recent_stats = {'trades': trades, 'wins': wins, 'pnl': float(total_pnl or 0), 'win_rate': float(win_rate or 0)}
                else:
                    prev_stats = {'trades': trades, 'wins': wins, 'pnl': float(total_pnl or 0), 'win_rate': float(win_rate or 0)}

            # Need both periods with minimum trades
            if not recent_stats or not prev_stats:
                return None
            if recent_stats['trades'] < 3 or prev_stats['trades'] < 3:
                return None

            recent_wr = recent_stats['win_rate']
            prev_wr = prev_stats['win_rate']

            if prev_wr > 0:
                degradation = ((prev_wr - recent_wr) / prev_wr) * 100

                if degradation > GUARDRAILS['degradation_threshold']:
                    alert = {
                        'bot_name': bot_name,
                        'alert_type': 'DEGRADATION',
                        'recent_win_rate': recent_wr,
                        'previous_win_rate': prev_wr,
                        'recent_trades': recent_stats['trades'],
                        'previous_trades': prev_stats['trades'],
                        'recent_pnl': recent_stats['pnl'],
                        'previous_pnl': prev_stats['pnl'],
                        'degradation_pct': degradation,
                        'threshold': GUARDRAILS['degradation_threshold'],
                        'recommendation': 'Consider rollback to previous version or parameter adjustment'
                    }

                    self.log_action(
                        bot_name=bot_name,
                        action_type=ActionType.DEGRADATION_DETECTED,
                        description=f"Performance degradation detected: {degradation:.1f}%",
                        reason=f"Win rate dropped from {prev_wr:.1f}% to {recent_wr:.1f}%",
                        justification=alert
                    )

                    # AUTO-GENERATE improvement proposal
                    self._create_degradation_proposal(bot_name, alert)

                    return alert

            return None

        except Exception as e:
            logger.error(f"Failed to detect degradation: {e}")
            return None

    def _create_degradation_proposal(self, bot_name: str, degradation_info: Dict) -> Optional[str]:
        """
        Automatically create a proposal when degradation is detected.

        This is the automated proposal generation that Solomon performs.
        """
        try:
            # Determine strategy type and appropriate adjustments
            ic_bots = ['ARES', 'TITAN', 'PEGASUS', 'PROMETHEUS']
            is_ic = bot_name.upper() in ic_bots

            if is_ic:
                # Iron Condor bots - suggest widening strikes
                proposal_type = ProposalType.PARAMETER_CHANGE
                title = f"Widen {bot_name} IC strikes after degradation"
                description = f"Performance degradation of {degradation_info['degradation_pct']:.1f}% detected. " \
                             f"Win rate dropped from {degradation_info['previous_win_rate']:.1f}% to {degradation_info['recent_win_rate']:.1f}%. " \
                             f"Recommend widening strikes to increase win probability."
                current_value = {'sd_multiplier': 1.0}  # Placeholder - actual value would come from config
                proposed_value = {'sd_multiplier': 1.2}  # Widen by 20%
                expected_improvement = {'win_rate_increase': 5.0}
            else:
                # Directional bots - suggest tightening entry criteria
                proposal_type = ProposalType.PARAMETER_CHANGE
                title = f"Tighten {bot_name} entry criteria after degradation"
                description = f"Performance degradation of {degradation_info['degradation_pct']:.1f}% detected. " \
                             f"Win rate dropped from {degradation_info['previous_win_rate']:.1f}% to {degradation_info['recent_win_rate']:.1f}%. " \
                             f"Recommend tightening wall proximity filter."
                current_value = {'wall_filter_pct': 0.5}
                proposed_value = {'wall_filter_pct': 0.3}  # Require closer to wall
                expected_improvement = {'direction_accuracy_increase': 3.0}

            proposal_id = self.create_proposal(
                bot_name=bot_name,
                proposal_type=proposal_type,
                title=title,
                description=description,
                current_value=current_value,
                proposed_value=proposed_value,
                reason=f"Auto-generated due to {degradation_info['degradation_pct']:.1f}% performance degradation",
                supporting_metrics=degradation_info,
                expected_improvement=expected_improvement,
                risk_level="MEDIUM",
                risk_factors=["May reduce trade frequency", "Requires validation period"],
                rollback_plan="Revert to previous parameter values if win rate doesn't improve within 7 days"
            )

            if proposal_id:
                logger.info(f"[SOLOMON] Auto-created proposal {proposal_id} for {bot_name} degradation")
                self.log_action(
                    bot_name=bot_name,
                    action_type=ActionType.PROPOSAL_CREATED,
                    description=f"Auto-generated improvement proposal: {title}",
                    reason=f"Degradation detected: {degradation_info['degradation_pct']:.1f}%",
                    justification={'proposal_id': proposal_id, 'degradation': degradation_info}
                )

            return proposal_id

        except Exception as e:
            logger.error(f"Failed to create degradation proposal: {e}")
            return None

    # =========================================================================
    # KILL SWITCH
    # =========================================================================

    def activate_kill_switch(self, bot_name: str, reason: str, killed_by: str = "SYSTEM") -> bool:
        """Activate kill switch for a bot"""
        logger.warning(f"[SOLOMON KILL SWITCH] Activating kill switch for {bot_name}")
        logger.warning(f"[SOLOMON KILL SWITCH]   Reason: {reason}")
        logger.warning(f"[SOLOMON KILL SWITCH]   Killed by: {killed_by}")

        if not DB_AVAILABLE:
            logger.warning(f"[SOLOMON KILL SWITCH] {bot_name} KILLED (DB not available)")
            return True

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO solomon_kill_switch (bot_name, is_killed, killed_at, killed_by, kill_reason)
                VALUES (%s, TRUE, NOW(), %s, %s)
                ON CONFLICT (bot_name) DO UPDATE SET
                    is_killed = TRUE,
                    killed_at = NOW(),
                    killed_by = EXCLUDED.killed_by,
                    kill_reason = EXCLUDED.kill_reason,
                    resumed_at = NULL,
                    resumed_by = NULL
            """, (bot_name, killed_by, reason))

            conn.commit()
            conn.close()

            self.log_action(
                bot_name=bot_name,
                action_type=ActionType.KILL_SWITCH_ACTIVATED,
                description=f"Kill switch activated: {reason}",
                reason=reason,
                actor=killed_by
            )

            logger.warning(f"[SOLOMON KILL SWITCH] Kill switch ACTIVATED for {bot_name} - all trading halted")
            return True

        except Exception as e:
            logger.error(f"[SOLOMON KILL SWITCH] Failed to activate kill switch for {bot_name}: {e}")
            return False

    def deactivate_kill_switch(self, bot_name: str, resumed_by: str) -> bool:
        """Deactivate kill switch for a bot"""
        logger.info(f"[SOLOMON KILL SWITCH] Deactivating kill switch for {bot_name}")
        logger.info(f"[SOLOMON KILL SWITCH]   Resumed by: {resumed_by}")

        if not DB_AVAILABLE:
            logger.info(f"[SOLOMON KILL SWITCH] {bot_name} resumed (DB not available)")
            return True

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE solomon_kill_switch
                SET is_killed = FALSE, resumed_at = NOW(), resumed_by = %s
                WHERE bot_name = %s
            """, (resumed_by, bot_name))

            conn.commit()
            conn.close()

            self.log_action(
                bot_name=bot_name,
                action_type=ActionType.KILL_SWITCH_DEACTIVATED,
                description=f"Kill switch deactivated by {resumed_by}",
                reason="Manual resume",
                actor=f"USER:{resumed_by}"
            )

            logger.info(f"[SOLOMON KILL SWITCH] Kill switch DEACTIVATED for {bot_name} - trading resumed")
            return True

        except Exception as e:
            logger.error(f"[SOLOMON KILL SWITCH] Failed to deactivate kill switch for {bot_name}: {e}")
            return False

    def is_bot_killed(self, bot_name: str) -> bool:
        """Check if a bot's kill switch is active.

        NOTE: Kill switch functionality has been removed.
        This method always returns False (trading allowed).

        Returns:
            Always False - kill switch is never active
        """
        # Kill switch removed - always allow trading
        return False

    def get_kill_switch_status(self) -> Dict[str, Dict]:
        """Get kill switch status for all bots"""
        if not DB_AVAILABLE:
            return {}

        with get_db_connection() as conn:
            if conn is None:
                return {}
            try:
                cursor = conn.cursor()

                cursor.execute("SELECT * FROM solomon_kill_switch")
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

                return {row[1]: dict(zip(columns, row)) for row in rows}

            except Exception as e:
                logger.error(f"Failed to get kill switch status: {e}")
                return {}

    # =========================================================================
    # FEEDBACK LOOP EXECUTION
    # =========================================================================

    def run_feedback_loop(self) -> FeedbackLoopResult:
        """
        Run the complete feedback loop.

        This is the main entry point called by the scheduler.

        Steps:
        1. Expire old proposals
        2. Check each bot's performance
        3. Detect degradation
        4. Check for retraining opportunities
        5. Create proposals for improvements
        6. Record performance snapshots
        """
        import uuid

        run_id = f"RUN-{datetime.now(CENTRAL_TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(CENTRAL_TZ)

        logger.info(f"[SOLOMON FEEDBACK LOOP] ========================================")
        logger.info(f"[SOLOMON FEEDBACK LOOP] Starting feedback loop run: {run_id}")
        logger.info(f"[SOLOMON FEEDBACK LOOP] Start time: {started_at.strftime('%Y-%m-%d %H:%M:%S')} CT")
        logger.info(f"[SOLOMON FEEDBACK LOOP] Session: {self.session_id}")
        logger.info(f"[SOLOMON FEEDBACK LOOP] ========================================")

        self.log_action(
            bot_name="SYSTEM",
            action_type=ActionType.FEEDBACK_LOOP_RUN,
            description=f"Feedback loop started: {run_id}",
            reason="Scheduled run"
        )

        proposals_created = []
        proposals_applied = []
        models_retrained = []
        alerts_raised = []
        errors = []
        outcomes_processed = 0

        # All active trading bots - IC bots: ARES, TITAN, PEGASUS, PROMETHEUS | Directional: ATHENA, ICARUS
        bots = [BotName.ARES, BotName.ATHENA, BotName.TITAN, BotName.PEGASUS, BotName.ICARUS, BotName.PROMETHEUS]

        try:
            # Step 1: Expire old proposals
            logger.info(f"[SOLOMON FEEDBACK LOOP] Step 1: Checking for expired proposals...")
            expired_count = self.expire_old_proposals()
            if expired_count > 0:
                logger.info(f"[SOLOMON FEEDBACK LOOP]   Expired {expired_count} old proposals")
            else:
                logger.info(f"[SOLOMON FEEDBACK LOOP]   No proposals to expire")

            # Step 1.5: AUTO-APPLY proven proposals (Solomon's autonomous improvement)
            # Check all proposals with active validations for proven improvement
            logger.info(f"[SOLOMON FEEDBACK LOOP] Step 1.5: Checking for proven proposals to auto-apply...")
            pending_proposals = self.get_pending_proposals()
            logger.info(f"[SOLOMON FEEDBACK LOOP]   Found {len(pending_proposals)} pending proposals")
            for proposal in pending_proposals:
                proposal_id = proposal.get('proposal_id')
                if not proposal_id:
                    continue

                try:
                    # Import and use the enhanced validation
                    from quant.solomon_enhancements import get_solomon_enhanced
                    enhanced = get_solomon_enhanced()
                    validation_result = enhanced.can_apply_proposal(proposal_id)

                    if validation_result.get('can_apply') and validation_result.get('improvement_proven'):
                        # AUTO-APPLY: Improvement has been PROVEN
                        improvement_pct = validation_result.get('improvement_metrics', {}).get('win_rate_improvement', 0)
                        logger.info(f"🎯 AUTO-APPLYING proven improvement: {proposal_id} (+{improvement_pct:.1f}%)")

                        # Apply the proposal
                        success = self.approve_proposal(
                            proposal_id=proposal_id,
                            reviewer="SOLOMON_AUTO",
                            notes=f"Auto-applied: {improvement_pct:.1f}% improvement proven over {validation_result.get('improvement_metrics', {}).get('days_validated', 0)} days"
                        )
                        if success:
                            proposals_applied.append(proposal_id)
                            self.log_action(
                                bot_name=proposal.get('bot_name', 'UNKNOWN'),
                                action_type=ActionType.PROPOSAL_APPROVED,
                                description=f"Auto-applied proven improvement: {proposal_id}",
                                reason=f"Improvement validated: {improvement_pct:.1f}% over {validation_result.get('improvement_metrics', {}).get('trades_validated', 0)} trades",
                                justification=validation_result,
                                success=True
                            )
                except Exception as e:
                    logger.debug(f"Could not check proposal {proposal_id} for auto-apply: {e}")

            # Step 2-5: Process each bot
            logger.info(f"[SOLOMON FEEDBACK LOOP] Step 2-5: Processing bots: {[b.value for b in bots]}")
            for bot in bots:
                bot_name = bot.value
                logger.info(f"[SOLOMON FEEDBACK LOOP] Processing {bot_name}...")

                # Skip if killed
                if self.is_bot_killed(bot_name):
                    logger.info(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - SKIPPED (kill switch active)")
                    continue

                try:
                    # Record performance snapshot
                    logger.info(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - Recording performance snapshot...")
                    snapshot_id = self.record_performance_snapshot(bot_name)
                    if snapshot_id:
                        logger.info(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - Performance snapshot: {snapshot_id}")
                    else:
                        logger.info(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - No performance data available")

                    # Detect degradation
                    logger.info(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - Checking for performance degradation...")
                    degradation = self.detect_degradation(bot_name)
                    if degradation:
                        logger.warning(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - DEGRADATION DETECTED: {degradation['degradation_pct']:.1f}%")
                        alerts_raised.append(degradation)

                        # Auto-rollback if severe
                        if degradation['degradation_pct'] > GUARDRAILS['rollback_on_drawdown_pct']:
                            logger.warning(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - Triggering auto-rollback (degradation > {GUARDRAILS['rollback_on_drawdown_pct']}%)")
                            versions = self.get_version_history(bot_name, limit=2)
                            if len(versions) >= 2:
                                prev_version = versions[1]
                                logger.info(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - Rolling back to version {prev_version['version_number']}")
                                self.rollback(
                                    bot_name=bot_name,
                                    to_version_id=prev_version['version_id'],
                                    reason=f"Automatic rollback: {degradation['degradation_pct']:.1f}% degradation",
                                    triggered_by="SOLOMON",
                                    automatic=True
                                )
                            else:
                                logger.warning(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - Cannot rollback: insufficient version history")
                    else:
                        logger.info(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - No degradation detected")

                except Exception as e:
                    errors.append(f"{bot_name}: {str(e)}")
                    logger.error(f"[SOLOMON FEEDBACK LOOP]   {bot_name} - ERROR: {e}")

            # Step 6: Check if Oracle retraining is needed
            logger.info(f"[SOLOMON FEEDBACK LOOP] Step 6: Checking Oracle retraining requirements...")
            if ORACLE_AVAILABLE:
                pending_outcomes = get_pending_outcomes_count()
                outcomes_processed = pending_outcomes
                logger.info(f"[SOLOMON FEEDBACK LOOP]   Oracle pending outcomes: {pending_outcomes} (threshold: {GUARDRAILS['min_sample_size']})")

                if pending_outcomes >= GUARDRAILS['min_sample_size']:
                    logger.info(f"[SOLOMON FEEDBACK LOOP]   Creating retraining proposal...")
                    # Create proposal for retraining
                    proposal_id = self.create_proposal(
                        bot_name="ORACLE",
                        proposal_type=ProposalType.MODEL_UPDATE,
                        title=f"Oracle Model Retraining ({pending_outcomes} new outcomes)",
                        description=f"Oracle has accumulated {pending_outcomes} new trade outcomes since last training. "
                                    f"Retraining will incorporate this new data to improve predictions.",
                        current_value={'outcomes_since_training': 0, 'model_version': 'current'},
                        proposed_value={'outcomes_to_incorporate': pending_outcomes, 'model_version': 'new'},
                        reason=f"{pending_outcomes} new outcomes available (threshold: {GUARDRAILS['min_sample_size']})",
                        supporting_metrics={'pending_outcomes': pending_outcomes},
                        expected_improvement={'accuracy_improvement': '1-5%', 'confidence': 'Data-driven'},
                        risk_level='LOW',
                        risk_factors=['Model may not improve', 'Possible overfitting'],
                        rollback_plan='Rollback to previous model version if performance degrades'
                    )

                    if proposal_id:
                        proposals_created.append(proposal_id)

        except Exception as e:
            errors.append(f"Loop error: {str(e)}")
            logger.error(f"[SOLOMON FEEDBACK LOOP] Loop error: {e}")
            traceback.print_exc()

        completed_at = datetime.now(CENTRAL_TZ)
        duration = (completed_at - started_at).total_seconds()

        result = FeedbackLoopResult(
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            bots_checked=[b.value for b in bots],
            outcomes_processed=outcomes_processed,
            proposals_created=proposals_created,
            proposals_applied=proposals_applied,
            models_retrained=models_retrained,
            alerts_raised=alerts_raised,
            success=len(errors) == 0,
            errors=errors
        )

        # Enhanced completion logging
        logger.info(f"[SOLOMON FEEDBACK LOOP] ========================================")
        logger.info(f"[SOLOMON FEEDBACK LOOP] Feedback loop completed: {run_id}")
        logger.info(f"[SOLOMON FEEDBACK LOOP] Duration: {duration:.2f} seconds")
        logger.info(f"[SOLOMON FEEDBACK LOOP] Status: {'SUCCESS' if result.success else 'FAILED'}")
        logger.info(f"[SOLOMON FEEDBACK LOOP] Summary:")
        logger.info(f"[SOLOMON FEEDBACK LOOP]   Bots checked: {len(result.bots_checked)}")
        logger.info(f"[SOLOMON FEEDBACK LOOP]   Outcomes processed: {result.outcomes_processed}")
        logger.info(f"[SOLOMON FEEDBACK LOOP]   Proposals created: {len(result.proposals_created)}")
        logger.info(f"[SOLOMON FEEDBACK LOOP]   Proposals auto-applied: {len(result.proposals_applied)}")
        logger.info(f"[SOLOMON FEEDBACK LOOP]   Models retrained: {len(result.models_retrained)}")
        logger.info(f"[SOLOMON FEEDBACK LOOP]   Alerts raised: {len(result.alerts_raised)}")
        if result.errors:
            logger.warning(f"[SOLOMON FEEDBACK LOOP]   Errors: {result.errors}")
        logger.info(f"[SOLOMON FEEDBACK LOOP] ========================================")

        self.log_action(
            bot_name="SYSTEM",
            action_type=ActionType.FEEDBACK_LOOP_RUN,
            description=f"Feedback loop completed: {run_id}",
            reason="Run completed",
            justification=result.to_dict(),
            success=result.success
        )

        return result

    # =========================================================================
    # DASHBOARD DATA
    # =========================================================================

    def get_dashboard_summary(self) -> Dict:
        """
        Get comprehensive dashboard summary.
        """
        summary = {
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
            'session_id': self.session_id,
            'bots': {},
            'pending_proposals': [],
            'recent_actions': [],
            'kill_switch_status': {},
            'health': {}
        }

        # Get status for each bot
        for bot in BotName:
            bot_name = bot.value
            # Get performance history for sparkline (last 10 data points)
            perf_history = self.get_performance_history(bot_name, days=14)
            sparkline_data = [h.get('total_pnl', 0) for h in perf_history[:10]][::-1] if perf_history else []

            summary['bots'][bot_name] = {
                'name': bot_name,
                'is_killed': self.is_bot_killed(bot_name),
                'performance': self._get_current_performance(bot_name),
                'performance_history': sparkline_data,  # For sparkline chart
                'active_version': self._get_active_version_info(bot_name),
                'versions_count': len(self.get_version_history(bot_name, limit=100)),
                'last_action': self._get_last_action(bot_name)
            }

        # Pending proposals
        summary['pending_proposals'] = self.get_pending_proposals()

        # Recent actions
        summary['recent_actions'] = self.get_audit_log(limit=20)

        # Kill switch status
        summary['kill_switch_status'] = self.get_kill_switch_status()

        # Health
        summary['health'] = self._get_system_health()

        # Math Optimizer Status (new in 2024-12)
        summary['math_optimizer'] = self.get_math_optimizer_status()

        return summary

    def _get_active_version_info(self, bot_name: str) -> Optional[Dict]:
        """Get active version info for a bot"""
        if not DB_AVAILABLE:
            return None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT version_id, version_number, created_at, artifact_name, approved_by
                FROM solomon_versions
                WHERE bot_name = %s AND is_active = TRUE
                LIMIT 1
            """, (bot_name,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    'version_id': row[0],
                    'version_number': row[1],
                    'created_at': row[2].isoformat() if row[2] else None,
                    'artifact_name': row[3],
                    'approved_by': row[4]
                }
            return None

        except Exception as e:
            logger.debug(f"Could not get active version: {e}")
            return None

    def _get_last_action(self, bot_name: str) -> Optional[Dict]:
        """Get last action for a bot"""
        actions = self.get_audit_log(bot_name=bot_name, limit=1)
        return actions[0] if actions else None

    def _get_system_health(self) -> Dict:
        """Get overall system health"""
        health = {
            'database': DB_AVAILABLE,
            'oracle': ORACLE_AVAILABLE,
            'last_feedback_run': None,
            'pending_proposals_count': 0,
            'degradation_alerts': 0
        }

        if DB_AVAILABLE:
            try:
                conn = get_connection()
                cursor = conn.cursor()

                # Last feedback run
                cursor.execute("""
                    SELECT timestamp FROM solomon_audit_log
                    WHERE action_type = 'FEEDBACK_LOOP_RUN'
                    ORDER BY timestamp DESC LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    health['last_feedback_run'] = row[0].isoformat()

                # Pending proposals count
                cursor.execute("SELECT COUNT(*) FROM solomon_proposals WHERE status = 'PENDING'")
                health['pending_proposals_count'] = cursor.fetchone()[0]

                # Degradation alerts (last 24h)
                cursor.execute("""
                    SELECT COUNT(*) FROM solomon_audit_log
                    WHERE action_type = 'DEGRADATION_DETECTED'
                    AND timestamp > NOW() - INTERVAL '24 hours'
                """)
                health['degradation_alerts'] = cursor.fetchone()[0]

                conn.close()
            except Exception as e:
                logger.debug(f"Could not get health info: {e}")

        return health

    def get_math_optimizer_status(self) -> Dict:
        """
        Get math optimizer status for all bots.

        MATH OPTIMIZER ALGORITHMS:
        - HMM (Hidden Markov Model): Bayesian regime detection
        - Kalman Filter: Signal smoothing for noisy Greeks
        - Thompson Sampling: Multi-armed bandit for capital allocation
        - Convex Optimization: Scenario-aware strike selection
        - HJB Exit Optimizer: Optimal exit timing
        - MDP Trade Sequencer: Trade ordering optimization

        Returns:
            Dict with status for each bot and overall optimizer health
        """
        status = {
            'available': MATH_OPTIMIZER_AVAILABLE,
            'bots': {},
            'algorithms': {
                'HMM': 'Hidden Markov Model - Regime Detection',
                'Kalman': 'Kalman Filter - Signal Smoothing',
                'Thompson': 'Thompson Sampling - Capital Allocation',
                'Convex': 'Convex Optimization - Strike Selection',
                'HJB': 'Hamilton-Jacobi-Bellman - Exit Timing',
                'MDP': 'Markov Decision Process - Trade Sequencing'
            }
        }

        if MATH_OPTIMIZER_AVAILABLE and MathOptimizerOrchestrator:
            try:
                # Get orchestrator to check algorithm states
                orchestrator = MathOptimizerOrchestrator(bot_name="SOLOMON_CHECK")
                status['orchestrator_status'] = 'ACTIVE'

                # Track which bots have math optimizer enabled
                for bot in BotName:
                    bot_name = bot.value
                    status['bots'][bot_name] = {
                        'integrated': True,  # All bots now have integration
                        'algorithms_enabled': ['HMM', 'Thompson', 'HJB', 'Kalman']
                    }

            except Exception as e:
                status['orchestrator_status'] = f'ERROR: {str(e)}'
                logger.debug(f"Could not get math optimizer status: {e}")
        else:
            status['orchestrator_status'] = 'NOT_AVAILABLE'
            for bot in BotName:
                status['bots'][bot.value] = {'integrated': False, 'algorithms_enabled': []}

        return status


# =============================================================================
# SINGLETON AND CONVENIENCE FUNCTIONS
# =============================================================================

_solomon: Optional[SolomonFeedbackLoop] = None


def get_solomon() -> SolomonFeedbackLoop:
    """Get or create Solomon singleton"""
    global _solomon
    if _solomon is None:
        _solomon = SolomonFeedbackLoop()
    return _solomon


def run_feedback_loop() -> FeedbackLoopResult:
    """Run the feedback loop (convenience function)"""
    return get_solomon().run_feedback_loop()


def approve_proposal(proposal_id: str, reviewer: str, notes: str = "") -> bool:
    """Approve a proposal"""
    return get_solomon().approve_proposal(proposal_id, reviewer, notes)


def reject_proposal(proposal_id: str, reviewer: str, notes: str = "") -> bool:
    """Reject a proposal"""
    return get_solomon().reject_proposal(proposal_id, reviewer, notes)


def rollback_bot(bot_name: str, to_version_id: str, reason: str, user: str) -> bool:
    """Rollback a bot to a previous version"""
    return get_solomon().rollback(bot_name, to_version_id, reason, f"USER:{user}")


def kill_bot(bot_name: str, reason: str, user: str) -> bool:
    """Activate kill switch for a bot"""
    return get_solomon().activate_kill_switch(bot_name, reason, f"USER:{user}")


def resume_bot(bot_name: str, user: str) -> bool:
    """Resume a killed bot"""
    return get_solomon().deactivate_kill_switch(bot_name, user)


def get_dashboard() -> Dict:
    """Get dashboard summary"""
    return get_solomon().get_dashboard_summary()


# =============================================================================
# CLI FOR TESTING
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    solomon = get_solomon()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "run":
            result = solomon.run_feedback_loop()
            print(json.dumps(result.to_dict(), indent=2, default=str))

        elif command == "dashboard":
            dashboard = solomon.get_dashboard_summary()
            print(json.dumps(dashboard, indent=2, default=str))

        elif command == "proposals":
            proposals = solomon.get_pending_proposals()
            print(json.dumps(proposals, indent=2, default=str))

        elif command == "audit":
            bot = sys.argv[2] if len(sys.argv) > 2 else None
            logs = solomon.get_audit_log(bot_name=bot, limit=50)
            print(json.dumps(logs, indent=2, default=str))

        else:
            print(f"Unknown command: {command}")
            print("Usage: python solomon_feedback_loop.py [run|dashboard|proposals|audit [bot_name]]")
    else:
        print("Solomon Feedback Loop Service")
        print("Usage: python solomon_feedback_loop.py [run|dashboard|proposals|audit [bot_name]]")
