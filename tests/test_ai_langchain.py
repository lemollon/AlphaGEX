"""
LangChain Integration Tests

Tests for LangChain AI integration modules.

Run with: pytest tests/test_ai_langchain.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLangChainModelsInitialization:
    """Tests for LangChain models initialization"""

    def test_import_langchain_models(self):
        """Test that LangChain models can be imported"""
        try:
            from ai.langchain_models import get_llm, get_chat_model
            assert get_llm is not None or get_chat_model is not None
        except ImportError:
            pytest.skip("LangChain models not available")

    @patch('ai.langchain_models.ChatOpenAI')
    def test_get_chat_model(self, mock_chat):
        """Test chat model creation"""
        try:
            from ai.langchain_models import get_chat_model
            mock_chat.return_value = MagicMock()
            model = get_chat_model()
            assert model is not None
        except ImportError:
            pytest.skip("LangChain models not available")


class TestLangChainPrompts:
    """Tests for LangChain prompts"""

    def test_import_prompts(self):
        """Test that prompts can be imported"""
        try:
            from ai.langchain_prompts import (
                get_trading_analysis_prompt,
                get_market_commentary_prompt
            )
            assert get_trading_analysis_prompt is not None
        except ImportError:
            # Try alternative import
            try:
                from ai.langchain_prompts import TRADING_PROMPTS
                assert TRADING_PROMPTS is not None
            except ImportError:
                pytest.skip("LangChain prompts not available")

    def test_prompt_templates(self):
        """Test prompt template structure"""
        try:
            from ai.langchain_prompts import get_trading_analysis_prompt
            prompt = get_trading_analysis_prompt()
            assert prompt is not None
            # Prompts should be strings or PromptTemplate objects
        except ImportError:
            pytest.skip("LangChain prompts not available")


class TestLangChainTools:
    """Tests for LangChain tools"""

    def test_import_tools(self):
        """Test that tools can be imported"""
        try:
            from ai.langchain_tools import get_trading_tools
            tools = get_trading_tools()
            assert isinstance(tools, list)
        except ImportError:
            pytest.skip("LangChain tools not available")

    def test_tool_definitions(self):
        """Test tool definitions are valid"""
        try:
            from ai.langchain_tools import get_trading_tools
            tools = get_trading_tools()

            for tool in tools:
                # Tools should have name and description
                assert hasattr(tool, 'name') or hasattr(tool, '__name__')
        except ImportError:
            pytest.skip("LangChain tools not available")


class TestLangChainIntelligence:
    """Tests for LangChain intelligence module"""

    def test_import_intelligence(self):
        """Test that intelligence module can be imported"""
        try:
            from ai.langchain_intelligence import LangChainIntelligence
            assert LangChainIntelligence is not None
        except ImportError:
            pytest.skip("LangChain intelligence not available")

    @patch('ai.langchain_intelligence.ChatOpenAI')
    def test_intelligence_initialization(self, mock_chat):
        """Test intelligence initialization"""
        try:
            from ai.langchain_intelligence import LangChainIntelligence
            mock_chat.return_value = MagicMock()
            intel = LangChainIntelligence()
            assert intel is not None
        except ImportError:
            pytest.skip("LangChain intelligence not available")


class TestLangChainChains:
    """Tests for LangChain chains"""

    def test_analysis_chain(self):
        """Test analysis chain creation"""
        try:
            from ai.langchain_intelligence import LangChainIntelligence

            with patch('ai.langchain_intelligence.ChatOpenAI'):
                intel = LangChainIntelligence()
                if hasattr(intel, 'create_analysis_chain'):
                    chain = intel.create_analysis_chain()
                    assert chain is not None
        except ImportError:
            pytest.skip("LangChain intelligence not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
