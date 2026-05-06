import pytest
from backtest.directional_1dte.config import BOT_CONFIGS, BotConfig


@pytest.fixture
def solomon():
    return BOT_CONFIGS["solomon"]


@pytest.fixture
def gideon():
    return BOT_CONFIGS["gideon"]
