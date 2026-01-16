"""
Comprehensive integration tests for Solomon Feedback Loop Intelligence System.

Tests cover:
1. API endpoint wiring
2. Database schema and operations
3. Core feedback loop logic
4. Proposal validation flow
5. Frontend-backend contract

Run with: pytest tests/test_solomon_feedback_loop.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db_connection():
    """Mock database connection"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


@pytest.fixture
def sample_proposal():
    """Sample proposal for testing"""
    return {
        'proposal_id': 'PROP-TEST-001',
        'bot_name': 'ARES',
        'proposal_type': 'PARAMETER_CHANGE',
        'title': 'Increase wing width',
        'description': 'Increase iron condor wing width from 50 to 60 points',
        'current_value': {'wing_width': 50},
        'proposed_value': {'wing_width': 60},
        'status': 'PENDING',
        'created_at': datetime.now(CENTRAL_TZ).isoformat(),
        'expires_at': (datetime.now(CENTRAL_TZ) + timedelta(days=7)).isoformat(),
    }


@pytest.fixture
def sample_validation():
    """Sample validation for testing"""
    return {
        'validation_id': 'VAL-TEST-001',
        'proposal_id': 'PROP-TEST-001',
        'bot_name': 'ARES',
        'method': 'AB_TEST',
        'started_at': datetime.now(CENTRAL_TZ).isoformat(),
        'status': 'RUNNING',
        'current_config': {'wing_width': 50},
        'proposed_config': {'wing_width': 60},
        'current_performance': {'trades': 0, 'wins': 0, 'pnl': 0, 'win_rate': 0},
        'proposed_performance': {'trades': 0, 'wins': 0, 'pnl': 0, 'win_rate': 0},
    }


# =============================================================================
# 1. IMPORT TESTS - Verify all Solomon modules can be imported
# =============================================================================

class TestSolomonImports:
    """Test that all Solomon modules import correctly"""

    def test_import_solomon_feedback_loop(self):
        """Test main feedback loop module imports"""
        from quant.solomon_feedback_loop import (
            SolomonFeedbackLoop,
            ActionType,
            ProposalType,
            ProposalStatus,
        )
        assert SolomonFeedbackLoop is not None
        assert ActionType is not None
        assert ProposalType is not None
        assert ProposalStatus is not None

    def test_import_solomon_enhancements(self):
        """Test enhancements module imports"""
        from quant.solomon_enhancements import (
            SolomonEnhanced,
            ProposalValidator,
            ValidationResult,
            ProposalReasoning,
        )
        assert SolomonEnhanced is not None
        assert ProposalValidator is not None
        assert ValidationResult is not None
        assert ProposalReasoning is not None

    def test_import_action_type_enum_values(self):
        """Test ActionType enum has expected values"""
        from quant.solomon_feedback_loop import ActionType

        # Verify key enum values exist
        assert hasattr(ActionType, 'PROPOSAL_CREATED')
        assert hasattr(ActionType, 'PROPOSAL_APPROVED')
        assert hasattr(ActionType, 'PROPOSAL_REJECTED')
        assert hasattr(ActionType, 'PROPOSAL_EXPIRED')
        assert hasattr(ActionType, 'KILL_SWITCH_ACTIVATED')

        # Verify PROPOSAL_APPLIED does NOT exist (this was a bug we fixed)
        assert not hasattr(ActionType, 'PROPOSAL_APPLIED')

    def test_import_proposal_type_enum_values(self):
        """Test ProposalType enum has expected values"""
        from quant.solomon_feedback_loop import ProposalType

        assert hasattr(ProposalType, 'MODEL_RETRAIN')
        assert hasattr(ProposalType, 'PARAMETER_CHANGE')


# =============================================================================
# 2. DATABASE SCHEMA TESTS
# =============================================================================

class TestSolomonDatabaseSchema:
    """Test database schema definitions"""

    def test_proposals_table_sql_valid(self):
        """Test that proposals table SQL is valid"""
        from quant.solomon_feedback_loop import SCHEMA_SQL

        assert 'CREATE TABLE IF NOT EXISTS solomon_proposals' in SCHEMA_SQL
        assert 'proposal_id TEXT' in SCHEMA_SQL
        assert 'bot_name TEXT' in SCHEMA_SQL
        assert 'status TEXT' in SCHEMA_SQL
        assert 'created_at TIMESTAMPTZ' in SCHEMA_SQL

    def test_validations_table_sql_valid(self):
        """Test that validations table SQL is valid"""
        from quant.solomon_feedback_loop import SCHEMA_SQL

        assert 'CREATE TABLE IF NOT EXISTS solomon_validations' in SCHEMA_SQL
        assert 'validation_id TEXT' in SCHEMA_SQL
        assert 'proposal_id TEXT' in SCHEMA_SQL
        assert 'improvement_proven BOOLEAN' in SCHEMA_SQL
        assert 'can_apply BOOLEAN' in SCHEMA_SQL
        # Check for the updated_at column we rely on
        assert 'updated_at TIMESTAMPTZ' in SCHEMA_SQL


# =============================================================================
# 3. CORE LOGIC TESTS - ProposalValidator
# =============================================================================

class TestProposalValidator:
    """Test ProposalValidator logic"""

    def test_win_rate_calculation_on_loss(self):
        """Test that win rate updates correctly on losses (BUG #3 fix)"""
        from quant.solomon_enhancements import ProposalValidator

        with patch('quant.solomon_enhancements.get_connection') as mock_get_conn:
            mock_get_conn.return_value = MagicMock()

            validator = ProposalValidator.__new__(ProposalValidator)
            validator._pending_validations = {}
            validator._save_to_database = MagicMock()

            # Manually set up a validation
            val_id = 'VAL-TEST-001'
            validator._pending_validations[val_id] = {
                'validation_id': val_id,
                'current_performance': {'trades': 0, 'wins': 0, 'pnl': 0, 'win_rate': 0},
                'proposed_performance': {'trades': 0, 'wins': 0, 'pnl': 0, 'win_rate': 0},
            }

            # Record a win
            validator.record_validation_trade(val_id, is_proposed=True, pnl=100)
            assert validator._pending_validations[val_id]['proposed_performance']['trades'] == 1
            assert validator._pending_validations[val_id]['proposed_performance']['wins'] == 1
            assert validator._pending_validations[val_id]['proposed_performance']['win_rate'] == 100.0

            # Record a loss - win rate should update to 50%
            validator.record_validation_trade(val_id, is_proposed=True, pnl=-50)
            assert validator._pending_validations[val_id]['proposed_performance']['trades'] == 2
            assert validator._pending_validations[val_id]['proposed_performance']['wins'] == 1
            assert validator._pending_validations[val_id]['proposed_performance']['win_rate'] == 50.0

    def test_validation_minimum_requirements(self):
        """Test validation requires minimum trades and days"""
        from quant.solomon_enhancements import ProposalValidator, ValidationResult

        with patch('quant.solomon_enhancements.get_connection') as mock_get_conn:
            mock_get_conn.return_value = MagicMock()

            validator = ProposalValidator.__new__(ProposalValidator)
            validator._pending_validations = {}

            # Set up validation with insufficient data
            val_id = 'VAL-TEST-002'
            validator._pending_validations[val_id] = {
                'validation_id': val_id,
                'method': 'AB_TEST',
                'started_at': datetime.now(CENTRAL_TZ).isoformat(),  # Just started
                'current_performance': {'trades': 5, 'wins': 3, 'pnl': 100, 'win_rate': 60},
                'proposed_performance': {'trades': 5, 'wins': 4, 'pnl': 200, 'win_rate': 80},
                'reasoning': {},
            }

            result = validator.evaluate_validation(val_id)

            # Should fail - not enough trades (needs 20) and not enough days (needs 7)
            assert isinstance(result, ValidationResult)
            assert result.can_apply == False
            assert len(result.rejection_reasons) > 0


# =============================================================================
# 4. CAN_APPLY_PROPOSAL TESTS
# =============================================================================

class TestCanApplyProposal:
    """Test can_apply_proposal logic including expiration checks"""

    def test_expired_proposal_cannot_be_applied(self):
        """Test that expired proposals return can_apply=False (BUG #11 fix)"""
        from quant.solomon_enhancements import SolomonEnhanced

        with patch('quant.solomon_enhancements.get_solomon') as mock_get_solomon:
            mock_solomon = MagicMock()
            mock_solomon.get_pending_proposals.return_value = [{
                'proposal_id': 'PROP-EXPIRED',
                'status': 'EXPIRED',
                'expires_at': (datetime.now(CENTRAL_TZ) - timedelta(days=1)).isoformat(),
            }]
            mock_get_solomon.return_value = mock_solomon

            enhancements = SolomonEnhanced.__new__(SolomonEnhanced)
            enhancements.solomon = mock_solomon
            enhancements.proposal_validator = MagicMock()

            result = enhancements.can_apply_proposal('PROP-EXPIRED')

            assert result['can_apply'] == False
            assert result['improvement_proven'] == False
            assert 'expired' in result['message'].lower()

    def test_missing_proposal_returns_correct_response(self):
        """Test response includes improvement_proven when proposal not found (BUG #2 fix)"""
        from quant.solomon_enhancements import SolomonEnhanced

        with patch('quant.solomon_enhancements.get_solomon') as mock_get_solomon:
            mock_solomon = MagicMock()
            mock_solomon.get_pending_proposals.return_value = []  # No proposals
            mock_get_solomon.return_value = mock_solomon

            enhancements = SolomonEnhanced.__new__(SolomonEnhanced)
            enhancements.solomon = mock_solomon
            enhancements.proposal_validator = MagicMock()

            result = enhancements.can_apply_proposal('PROP-NONEXISTENT')

            # Must have improvement_proven field (BUG #2 fix)
            assert 'improvement_proven' in result
            assert result['improvement_proven'] == False
            assert result['can_apply'] == False


# =============================================================================
# 5. API ROUTES TESTS
# =============================================================================

class TestSolomonAPIRoutes:
    """Test that API routes are properly defined"""

    def test_routes_module_imports(self):
        """Test routes module imports without error"""
        from backend.api.routes import solomon_routes
        assert solomon_routes.router is not None

    def test_route_definitions_exist(self):
        """Test key routes are defined"""
        from backend.api.routes.solomon_routes import router

        routes = [r.path for r in router.routes]

        # Check critical routes exist
        assert '/health' in routes
        assert '/dashboard' in routes
        assert '/proposals' in routes
        assert '/proposals/{proposal_id}/approve' in routes
        assert '/proposals/{proposal_id}/reject' in routes
        assert '/killswitch/{bot_name}/activate' in routes
        assert '/killswitch/{bot_name}/deactivate' in routes
        assert '/rollback/{bot_name}' in routes
        assert '/versions/{bot_name}' in routes
        assert '/validation/can-apply/{proposal_id}' in routes
        assert '/validation/status' in routes

    def test_request_models_have_correct_fields(self):
        """Test Pydantic request models have expected fields"""
        from backend.api.routes.solomon_routes import (
            ApprovalRequest,
            RejectionRequest,
            RollbackRequest,
            KillSwitchRequest,
        )

        # Test RejectionRequest expects 'notes' not 'reason'
        rejection = RejectionRequest(reviewer='test', notes='test reason')
        assert rejection.notes == 'test reason'

        # Test RollbackRequest expects 'to_version_id' not 'version_id'
        rollback = RollbackRequest(to_version_id='v1', reason='test', user='test')
        assert rollback.to_version_id == 'v1'


# =============================================================================
# 6. FRONTEND-BACKEND CONTRACT TESTS
# =============================================================================

class TestFrontendBackendContract:
    """Test that frontend expectations match backend responses"""

    def test_validation_status_response_structure(self):
        """Test validation status has all required fields for frontend"""
        from quant.solomon_enhancements import SolomonEnhanced, ValidationResult

        with patch('quant.solomon_enhancements.get_solomon') as mock_get_solomon:
            mock_solomon = MagicMock()
            mock_solomon.get_pending_proposals.return_value = [{
                'proposal_id': 'PROP-TEST',
                'status': 'PENDING',
                'expires_at': (datetime.now(CENTRAL_TZ) + timedelta(days=7)).isoformat(),
            }]
            mock_get_solomon.return_value = mock_solomon

            mock_validator = MagicMock()
            mock_validator.get_pending_validations.return_value = [{
                'proposal_id': 'PROP-TEST',
                'validation_id': 'VAL-TEST',
            }]
            mock_validator.evaluate_validation.return_value = ValidationResult(
                is_valid=True,
                can_apply=True,
                validation_method='AB_TEST',
                improvement_proven=True,
                improvement_metrics={'win_rate_improvement': 10.5},
                rejection_reasons=[],
                detailed_reasoning={'summary': 'Test passed'},
            )

            enhancements = SolomonEnhanced.__new__(SolomonEnhanced)
            enhancements.solomon = mock_solomon
            enhancements.proposal_validator = mock_validator

            result = enhancements.can_apply_proposal('PROP-TEST')

            # Frontend ValidationStatus interface expects these fields
            assert 'can_apply' in result
            assert 'improvement_proven' in result
            assert isinstance(result['can_apply'], bool)
            assert isinstance(result['improvement_proven'], bool)


# =============================================================================
# 7. INTEGRATION TESTS - Full Flow
# =============================================================================

class TestSolomonFullFlow:
    """Test complete proposal -> validation -> apply flow"""

    def test_proposal_validation_apply_flow(self):
        """Test the full flow from proposal creation to application"""
        from quant.solomon_enhancements import SolomonEnhanced, ProposalValidator

        with patch('quant.solomon_enhancements.get_solomon') as mock_get_solomon, \
             patch('quant.solomon_enhancements.get_connection') as mock_get_conn:

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_get_conn.return_value = mock_conn

            mock_solomon = MagicMock()
            mock_solomon.get_pending_proposals.return_value = [{
                'proposal_id': 'PROP-FLOW-TEST',
                'bot_name': 'ARES',
                'status': 'PENDING',
                'expires_at': (datetime.now(CENTRAL_TZ) + timedelta(days=7)).isoformat(),
            }]
            mock_solomon.approve_proposal.return_value = True
            mock_solomon.log_action = MagicMock()
            mock_get_solomon.return_value = mock_solomon

            # Create validator with mocked save
            validator = ProposalValidator.__new__(ProposalValidator)
            validator._pending_validations = {}
            validator._save_to_database = MagicMock()

            # Start validation
            val_id = validator.start_validation(
                proposal_id='PROP-FLOW-TEST',
                bot_name='ARES',
                method='AB_TEST',
                current_config={'param': 1},
                proposed_config={'param': 2},
                reasoning={'hypothesis': 'test'},
            )

            assert val_id is not None
            assert val_id in validator._pending_validations

            # Simulate enough trades to prove improvement
            # Record 25 trades with 80% win rate for proposed
            for i in range(25):
                if i < 20:  # 20 wins
                    validator.record_validation_trade(val_id, is_proposed=True, pnl=100)
                else:  # 5 losses
                    validator.record_validation_trade(val_id, is_proposed=True, pnl=-50)

            # Record 25 trades with 60% win rate for current (control)
            for i in range(25):
                if i < 15:  # 15 wins
                    validator.record_validation_trade(val_id, is_proposed=False, pnl=100)
                else:  # 10 losses
                    validator.record_validation_trade(val_id, is_proposed=False, pnl=-50)

            # Check the performance was recorded correctly
            val = validator._pending_validations[val_id]
            assert val['proposed_performance']['trades'] == 25
            assert val['proposed_performance']['win_rate'] == 80.0
            assert val['current_performance']['trades'] == 25
            assert val['current_performance']['win_rate'] == 60.0


# =============================================================================
# 8. EDGE CASE TESTS
# =============================================================================

class TestSolomonEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_proposal_id(self):
        """Test handling of empty proposal ID"""
        from quant.solomon_enhancements import SolomonEnhanced

        with patch('quant.solomon_enhancements.get_solomon') as mock_get_solomon:
            mock_solomon = MagicMock()
            mock_solomon.get_pending_proposals.return_value = []
            mock_get_solomon.return_value = mock_solomon

            enhancements = SolomonEnhanced.__new__(SolomonEnhanced)
            enhancements.solomon = mock_solomon
            enhancements.proposal_validator = MagicMock()

            result = enhancements.can_apply_proposal('')

            assert result['can_apply'] == False

    def test_invalid_validation_id(self):
        """Test handling of non-existent validation ID"""
        from quant.solomon_enhancements import ProposalValidator, ValidationResult

        with patch('quant.solomon_enhancements.get_connection') as mock_get_conn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []  # No validations in DB
            mock_conn.cursor.return_value = mock_cursor
            mock_get_conn.return_value = mock_conn

            validator = ProposalValidator.__new__(ProposalValidator)
            validator._pending_validations = {}

            result = validator.evaluate_validation('NONEXISTENT')

            assert isinstance(result, ValidationResult)
            assert result.can_apply == False
            assert 'not found' in str(result.rejection_reasons).lower()

    def test_timezone_handling(self):
        """Test that timezone-aware datetimes are handled correctly"""
        from quant.solomon_enhancements import SolomonEnhanced

        with patch('quant.solomon_enhancements.get_solomon') as mock_get_solomon:
            mock_solomon = MagicMock()

            # Test with ISO format with Z suffix
            mock_solomon.get_pending_proposals.return_value = [{
                'proposal_id': 'PROP-TZ-TEST',
                'status': 'PENDING',
                'expires_at': '2099-12-31T23:59:59Z',  # Far future
            }]
            mock_get_solomon.return_value = mock_solomon

            enhancements = SolomonEnhanced.__new__(SolomonEnhanced)
            enhancements.solomon = mock_solomon
            enhancements.proposal_validator = MagicMock()
            enhancements.proposal_validator.get_pending_validations.return_value = []

            result = enhancements.can_apply_proposal('PROP-TZ-TEST')

            # Should not crash on timezone parsing
            assert 'can_apply' in result


# =============================================================================
# 9. PERFORMANCE TESTS
# =============================================================================

class TestSolomonPerformance:
    """Test performance-related concerns"""

    def test_validation_trade_recording_efficiency(self):
        """Test that recording many trades doesn't accumulate errors"""
        from quant.solomon_enhancements import ProposalValidator

        with patch('quant.solomon_enhancements.get_connection') as mock_get_conn:
            mock_get_conn.return_value = MagicMock()

            validator = ProposalValidator.__new__(ProposalValidator)
            validator._pending_validations = {}
            validator._save_to_database = MagicMock()

            val_id = 'VAL-PERF-TEST'
            validator._pending_validations[val_id] = {
                'validation_id': val_id,
                'current_performance': {'trades': 0, 'wins': 0, 'pnl': 0, 'win_rate': 0},
                'proposed_performance': {'trades': 0, 'wins': 0, 'pnl': 0, 'win_rate': 0},
            }

            # Record 1000 trades
            for i in range(1000):
                pnl = 100 if i % 3 != 0 else -50  # ~66% win rate
                validator.record_validation_trade(val_id, is_proposed=True, pnl=pnl)

            perf = validator._pending_validations[val_id]['proposed_performance']
            assert perf['trades'] == 1000
            # Win rate should be approximately 66.7%
            assert 66 <= perf['win_rate'] <= 67


# =============================================================================
# 10. MIGRATION 023 TESTS - Strategy Analysis & Oracle Accuracy
# =============================================================================

class TestMigration023StrategyAnalysis:
    """Test Migration 023: Strategy-level analysis features"""

    def test_bot_strategy_configs_exist(self):
        """Test that BOT_STRATEGY_CONFIGS has all 5 bots"""
        from quant.solomon_enhancements import SolomonEnhanced

        configs = SolomonEnhanced.BOT_STRATEGY_CONFIGS

        # Verify all 5 bots are configured
        assert 'ARES' in configs
        assert 'TITAN' in configs
        assert 'PEGASUS' in configs
        assert 'ATHENA' in configs
        assert 'ICARUS' in configs

    def test_bot_strategy_types_correct(self):
        """Test that bots have correct strategy types"""
        from quant.solomon_enhancements import SolomonEnhanced

        configs = SolomonEnhanced.BOT_STRATEGY_CONFIGS

        # Iron Condor bots
        assert configs['ARES']['strategy_type'] == 'IRON_CONDOR'
        assert configs['TITAN']['strategy_type'] == 'IRON_CONDOR'
        assert configs['PEGASUS']['strategy_type'] == 'IRON_CONDOR'

        # Directional bots
        assert configs['ATHENA']['strategy_type'] == 'DIRECTIONAL'
        assert configs['ICARUS']['strategy_type'] == 'DIRECTIONAL'

    def test_get_bot_strategy_config(self):
        """Test get_bot_strategy_config method"""
        from quant.solomon_enhancements import SolomonEnhanced

        # Create SolomonEnhanced without calling __init__
        enhanced = SolomonEnhanced.__new__(SolomonEnhanced)
        enhanced.solomon = MagicMock()
        enhanced.proposal_validator = MagicMock()

        config = enhanced.get_bot_strategy_config('ARES')
        assert config['strategy_type'] == 'IRON_CONDOR'
        assert config['goal'] == 'stability'

        config = enhanced.get_bot_strategy_config('ATHENA')
        assert config['strategy_type'] == 'DIRECTIONAL'
        assert config['goal'] == 'movement'

        # Unknown bot
        config = enhanced.get_bot_strategy_config('UNKNOWN_BOT')
        assert config['strategy_type'] == 'UNKNOWN'

    def test_get_strategy_analysis_structure(self):
        """Test get_strategy_analysis returns correct structure"""
        from quant.solomon_enhancements import SolomonEnhanced
        import quant.solomon_enhancements as se_module

        with patch.object(se_module, 'get_connection') as mock_get_conn, \
             patch.object(se_module, 'DB_AVAILABLE', True):

            mock_conn = MagicMock()
            mock_cursor = MagicMock()

            # Mock Iron Condor results: (trades, wins, total_pnl, avg_pnl)
            # Mock Directional results: (trades, wins, total_pnl, avg_pnl, direction_correct)
            mock_cursor.fetchone.side_effect = [
                (10, 7, 500.0, 50.0),  # IC results
                (8, 5, 300.0, 37.5, 4)  # Directional results
            ]
            mock_conn.cursor.return_value = mock_cursor
            mock_get_conn.return_value = mock_conn

            enhanced = SolomonEnhanced.__new__(SolomonEnhanced)
            enhanced.solomon = MagicMock()
            enhanced.proposal_validator = MagicMock()

            result = enhanced.get_strategy_analysis(days=30)

            assert result['status'] == 'analyzed'
            assert result['period_days'] == 30
            assert 'iron_condor' in result
            assert 'directional' in result
            assert 'recommendation' in result

            # Check IC metrics
            assert result['iron_condor']['trades'] == 10
            assert result['iron_condor']['wins'] == 7
            assert result['iron_condor']['win_rate'] == 70.0
            assert 'ARES' in result['iron_condor']['bots']

            # Check Directional metrics
            assert result['directional']['trades'] == 8
            assert result['directional']['wins'] == 5
            assert 'direction_accuracy' in result['directional']
            assert 'ATHENA' in result['directional']['bots']

    def test_get_oracle_accuracy_structure(self):
        """Test get_oracle_accuracy returns correct structure"""
        from quant.solomon_enhancements import SolomonEnhanced
        import quant.solomon_enhancements as se_module

        with patch.object(se_module, 'get_connection') as mock_get_conn, \
             patch.object(se_module, 'DB_AVAILABLE', True):

            mock_conn = MagicMock()
            mock_cursor = MagicMock()

            # Mock results: (oracle_advice, strategy_type, trades, wins, avg_pnl)
            mock_cursor.fetchall.return_value = [
                ('TRADE_FULL', 'IRON_CONDOR', 15, 10, 45.0),
                ('TRADE_FULL', 'DIRECTIONAL', 12, 8, 35.0),
                ('TRADE_REDUCED', 'IRON_CONDOR', 5, 3, 20.0),
            ]
            mock_conn.cursor.return_value = mock_cursor
            mock_get_conn.return_value = mock_conn

            enhanced = SolomonEnhanced.__new__(SolomonEnhanced)
            enhanced.solomon = MagicMock()
            enhanced.proposal_validator = MagicMock()

            result = enhanced.get_oracle_accuracy(days=30)

            assert result['status'] == 'analyzed'
            assert result['period_days'] == 30
            assert 'by_advice' in result
            assert 'by_advice_detailed' in result
            assert 'by_strategy' in result
            assert 'summary' in result
            assert 'summary_data' in result

            # Check flattened by_advice for UI (aggregate across strategies)
            assert 'TRADE_FULL' in result['by_advice']
            assert 'count' in result['by_advice']['TRADE_FULL']
            assert 'accuracy' in result['by_advice']['TRADE_FULL']
            assert result['by_advice']['TRADE_FULL']['count'] == 27  # 15 + 12

            # Check detailed by_advice (nested structure)
            assert 'TRADE_FULL' in result['by_advice_detailed']
            assert 'IRON_CONDOR' in result['by_advice_detailed']['TRADE_FULL']
            assert result['by_advice_detailed']['TRADE_FULL']['IRON_CONDOR']['trades'] == 15

            # Check by_strategy aggregation
            assert 'IRON_CONDOR' in result['by_strategy']
            assert result['by_strategy']['IRON_CONDOR']['count'] == 20  # 15 + 5
            assert 'DIRECTIONAL' in result['by_strategy']
            assert result['by_strategy']['DIRECTIONAL']['count'] == 12

    def test_strategy_recommendation_ic_outperforming(self):
        """Test recommendation when Iron Condor is outperforming"""
        from quant.solomon_enhancements import SolomonEnhanced

        enhanced = SolomonEnhanced.__new__(SolomonEnhanced)

        # IC: 80% win rate, $60 avg PnL
        ic_row = (10, 8, 600.0, 60.0)
        # Directional: 50% win rate, $30 avg PnL
        dir_row = (10, 5, 300.0, 30.0, 3)

        recommendation = enhanced._generate_strategy_recommendation(
            ic_row, dir_row, ic_trades=10, dir_trades=10
        )

        assert 'Iron Condor' in recommendation
        assert 'outperforming' in recommendation

    def test_strategy_recommendation_directional_outperforming(self):
        """Test recommendation when Directional is outperforming"""
        from quant.solomon_enhancements import SolomonEnhanced

        enhanced = SolomonEnhanced.__new__(SolomonEnhanced)

        # IC: 45% win rate, $20 avg PnL
        ic_row = (10, 4, 200.0, 20.0)
        # Directional: 75% win rate, $50 avg PnL
        dir_row = (10, 7, 500.0, 50.0, 6)

        recommendation = enhanced._generate_strategy_recommendation(
            ic_row, dir_row, ic_trades=10, dir_trades=10
        )

        assert 'Directional' in recommendation
        assert 'outperforming' in recommendation or 'trending' in recommendation

    def test_strategy_recommendation_insufficient_data(self):
        """Test recommendation with insufficient data"""
        from quant.solomon_enhancements import SolomonEnhanced

        enhanced = SolomonEnhanced.__new__(SolomonEnhanced)

        ic_row = (3, 2, 100.0, 33.0)
        dir_row = (2, 1, 50.0, 25.0, 1)

        recommendation = enhanced._generate_strategy_recommendation(
            ic_row, dir_row, ic_trades=3, dir_trades=2
        )

        assert 'Insufficient data' in recommendation


class TestMigration023APIRoutes:
    """Test Migration 023 API route definitions"""

    def test_strategy_analysis_route_exists(self):
        """Test that /strategy-analysis route is defined"""
        from backend.api.routes.solomon_routes import router

        routes = [r.path for r in router.routes]
        assert '/strategy-analysis' in routes

    def test_oracle_accuracy_route_exists(self):
        """Test that /oracle-accuracy route is defined"""
        from backend.api.routes.solomon_routes import router

        routes = [r.path for r in router.routes]
        assert '/oracle-accuracy' in routes


class TestMigration023FrontendContract:
    """Test that frontend API client matches backend expectations"""

    def test_frontend_api_methods_exist(self):
        """Test that frontend api.ts has the required methods"""
        import os

        api_file_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            'frontend',
            'src',
            'lib',
            'api.ts'
        )

        if not os.path.exists(api_file_path):
            pytest.skip("Frontend api.ts not found")

        with open(api_file_path, 'r') as f:
            api_content = f.read()

        # Check Migration 023 methods exist
        assert 'getSolomonStrategyAnalysis' in api_content
        assert 'getSolomonOracleAccuracy' in api_content

        # Check they call the correct endpoints
        assert '/api/solomon/strategy-analysis' in api_content
        assert '/api/solomon/oracle-accuracy' in api_content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
