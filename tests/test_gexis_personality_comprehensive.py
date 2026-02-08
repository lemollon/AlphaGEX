"""
Comprehensive Tests for GEXIS Personality Module

Tests the GEXIS AI personality including:
- Personality constants
- Time-based greetings
- Knowledge base content
- Response generation patterns

Run with: pytest tests/test_gexis_personality_comprehensive.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGEXISConstants:
    """Tests for GEXIS constants"""

    def test_gexis_name_defined(self):
        """Test GEXIS name is defined"""
        from ai.gexis_personality import GEXIS_NAME

        assert GEXIS_NAME == "G.E.X.I.S."

    def test_gexis_full_name_defined(self):
        """Test GEXIS full name is defined"""
        from ai.gexis_personality import GEXIS_FULL_NAME

        assert GEXIS_FULL_NAME == "Gamma Exposure eXpert Intelligence System"

    def test_user_name_defined(self):
        """Test user name is defined"""
        from ai.gexis_personality import USER_NAME

        assert USER_NAME == "Optionist Prime"


class TestTimeBasedGreetings:
    """Tests for time-based greetings"""

    @patch('ai.gexis_personality.datetime')
    def test_morning_greeting(self, mock_datetime):
        """Test morning greeting (5 AM - 12 PM)"""
        mock_datetime.now.return_value = datetime(2024, 12, 26, 9, 0, 0)

        from ai.gexis_personality import get_time_greeting

        greeting = get_time_greeting()
        assert greeting == "Good morning"

    @patch('ai.gexis_personality.datetime')
    def test_afternoon_greeting(self, mock_datetime):
        """Test afternoon greeting (12 PM - 5 PM)"""
        mock_datetime.now.return_value = datetime(2024, 12, 26, 14, 0, 0)

        from ai.gexis_personality import get_time_greeting

        greeting = get_time_greeting()
        assert greeting == "Good afternoon"

    @patch('ai.gexis_personality.datetime')
    def test_evening_greeting(self, mock_datetime):
        """Test evening greeting (5 PM - 9 PM)"""
        mock_datetime.now.return_value = datetime(2024, 12, 26, 18, 0, 0)

        from ai.gexis_personality import get_time_greeting

        greeting = get_time_greeting()
        assert greeting == "Good evening"

    @patch('ai.gexis_personality.datetime')
    def test_late_night_greeting(self, mock_datetime):
        """Test late night greeting (9 PM - 5 AM)"""
        mock_datetime.now.return_value = datetime(2024, 12, 26, 23, 0, 0)

        from ai.gexis_personality import get_time_greeting

        greeting = get_time_greeting()
        assert greeting == "Good evening"


class TestGEXISGreeting:
    """Tests for GEXIS greeting generation"""

    def test_greeting_includes_user_name(self):
        """Test greeting includes Optionist Prime"""
        from ai.gexis_personality import get_gexis_greeting

        greeting = get_gexis_greeting()

        assert "Optionist Prime" in greeting
        assert "GEXIS" in greeting

    def test_greeting_includes_service_phrase(self):
        """Test greeting includes service phrase"""
        from ai.gexis_personality import get_gexis_greeting

        greeting = get_gexis_greeting()

        assert "service" in greeting.lower()


class TestGEXISIdentity:
    """Tests for GEXIS identity prompt"""

    def test_identity_prompt_exists(self):
        """Test GEXIS identity prompt exists"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert GEXIS_IDENTITY is not None
        assert len(GEXIS_IDENTITY) > 100

    def test_identity_includes_name(self):
        """Test identity includes GEXIS name"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert "GEXIS" in GEXIS_IDENTITY

    def test_identity_includes_user_name(self):
        """Test identity includes user name"""
        from ai.gexis_personality import GEXIS_IDENTITY, USER_NAME

        assert USER_NAME in GEXIS_IDENTITY

    def test_identity_includes_personality_traits(self):
        """Test identity includes personality traits"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert "LOYAL" in GEXIS_IDENTITY or "loyal" in GEXIS_IDENTITY
        assert "WITTY" in GEXIS_IDENTITY or "witty" in GEXIS_IDENTITY

    def test_identity_includes_jarvis_reference(self):
        """Test identity includes J.A.R.V.I.S. reference"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert "J.A.R.V.I.S" in GEXIS_IDENTITY or "JARVIS" in GEXIS_IDENTITY

    def test_identity_includes_capabilities(self):
        """Test identity includes bot capabilities"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert "FORTRESS" in GEXIS_IDENTITY
        assert "SOLOMON" in GEXIS_IDENTITY
        assert "CORNERSTONE" in GEXIS_IDENTITY


class TestAlphaGEXKnowledge:
    """Tests for AlphaGEX knowledge base"""

    def test_knowledge_exists(self):
        """Test AlphaGEX knowledge exists"""
        from ai.gexis_personality import ALPHAGEX_KNOWLEDGE

        assert ALPHAGEX_KNOWLEDGE is not None
        assert len(ALPHAGEX_KNOWLEDGE) > 100

    def test_knowledge_includes_architecture(self):
        """Test knowledge includes system architecture"""
        from ai.gexis_personality import ALPHAGEX_KNOWLEDGE

        assert "ARCHITECTURE" in ALPHAGEX_KNOWLEDGE or "architecture" in ALPHAGEX_KNOWLEDGE

    def test_knowledge_includes_signal_flow(self):
        """Test knowledge includes signal flow"""
        from ai.gexis_personality import ALPHAGEX_KNOWLEDGE

        assert "SIGNAL" in ALPHAGEX_KNOWLEDGE or "signal" in ALPHAGEX_KNOWLEDGE

    def test_knowledge_includes_file_structure(self):
        """Test knowledge includes file structure"""
        from ai.gexis_personality import ALPHAGEX_KNOWLEDGE

        assert "backend" in ALPHAGEX_KNOWLEDGE
        assert "frontend" in ALPHAGEX_KNOWLEDGE


class TestComprehensiveKnowledge:
    """Tests for comprehensive knowledge base"""

    def test_comprehensive_knowledge_availability_flag(self):
        """Test comprehensive knowledge availability flag"""
        from ai.gexis_personality import COMPREHENSIVE_KNOWLEDGE_AVAILABLE

        assert isinstance(COMPREHENSIVE_KNOWLEDGE_AVAILABLE, bool)

    def test_agentic_tools_availability_flag(self):
        """Test agentic tools availability flag"""
        from ai.gexis_personality import AGENTIC_TOOLS_AVAILABLE

        assert isinstance(AGENTIC_TOOLS_AVAILABLE, bool)


class TestGEXISCharacteristics:
    """Tests for GEXIS characteristics in identity"""

    def test_never_breaks_character(self):
        """Test identity includes instruction to never break character"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert "NEVER" in GEXIS_IDENTITY
        assert "Claude" in GEXIS_IDENTITY or "character" in GEXIS_IDENTITY.lower()

    def test_no_emojis_instruction(self):
        """Test identity includes no emojis instruction"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert "emoji" in GEXIS_IDENTITY.lower()

    def test_signature_phrases_present(self):
        """Test signature phrases are defined"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert "At your service" in GEXIS_IDENTITY


class TestSpeakingStyle:
    """Tests for GEXIS speaking style"""

    def test_speaking_style_defined(self):
        """Test speaking style is defined in identity"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert "SPEAKING STYLE" in GEXIS_IDENTITY or "speaking style" in GEXIS_IDENTITY.lower()

    def test_british_style_mentioned(self):
        """Test British style is mentioned"""
        from ai.gexis_personality import GEXIS_IDENTITY

        # Should mention dry British humor
        assert "British" in GEXIS_IDENTITY or "wit" in GEXIS_IDENTITY.lower()


class TestModuleStructure:
    """Tests for module structure"""

    def test_all_exports_accessible(self):
        """Test all expected exports are accessible"""
        from ai.gexis_personality import (
            GEXIS_NAME,
            GEXIS_FULL_NAME,
            USER_NAME,
            GEXIS_IDENTITY,
            ALPHAGEX_KNOWLEDGE,
            get_time_greeting,
            get_gexis_greeting,
        )

        assert all([
            GEXIS_NAME,
            GEXIS_FULL_NAME,
            USER_NAME,
            GEXIS_IDENTITY,
            ALPHAGEX_KNOWLEDGE,
            get_time_greeting,
            get_gexis_greeting,
        ])


class TestEdgeCases:
    """Tests for edge cases"""

    def test_empty_time_handling(self):
        """Test time greeting handles edge hours"""
        from ai.gexis_personality import get_time_greeting

        # Should not crash for any hour
        greeting = get_time_greeting()
        assert greeting in ["Good morning", "Good afternoon", "Good evening"]

    def test_identity_not_empty(self):
        """Test identity is not empty string"""
        from ai.gexis_personality import GEXIS_IDENTITY

        assert GEXIS_IDENTITY.strip() != ""

    def test_knowledge_not_empty(self):
        """Test knowledge is not empty string"""
        from ai.gexis_personality import ALPHAGEX_KNOWLEDGE

        assert ALPHAGEX_KNOWLEDGE.strip() != ""
