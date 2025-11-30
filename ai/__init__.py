"""AI and Machine Learning components for AlphaGEX trading system."""

# Make imports optional to prevent package-level failures
# when dependencies like langchain aren't installed

__all__ = []

try:
    from .autonomous_ai_reasoning import get_ai_reasoning
    __all__.append('get_ai_reasoning')
except ImportError:
    get_ai_reasoning = None

try:
    from .langchain_intelligence import TradingIntelligence
    __all__.append('TradingIntelligence')
except ImportError:
    TradingIntelligence = None

try:
    from .langchain_models import get_llm_model
    __all__.append('get_llm_model')
except ImportError:
    get_llm_model = None

try:
    from .langchain_prompts import TRADING_PROMPTS
    __all__.append('TRADING_PROMPTS')
except ImportError:
    TRADING_PROMPTS = None

try:
    from .langchain_tools import create_trading_tools
    __all__.append('create_trading_tools')
except ImportError:
    create_trading_tools = None
