"""Regression test for the VALOR "equity from wrong starting capital" bug.

Production symptom: VALOR's futures page showed "Account equity $596,484
from $100,000" next to a return of -0.59% and realized -$3,516. The equity
and return were correct (computed off the bot's real $600,000 multi-instrument
paper account: $600,000 - $3,516 = $596,484, -3516/600000 = -0.59%), but the
"from $100,000" starting-capital figure came from a different, generic
endpoint (/api/metrics/valor/summary -> BotMetricsService.get_capital_config)
that hardcodes DEFAULT_CAPITAL[VALOR] = 100000 - a stale single-instrument
value left over from before VALOR traded multiple futures tickers.

get_capital_config() must fall back to VALOR's own valor_paper_account table
(the real source of truth) before reaching for that stale default.
"""

from unittest.mock import MagicMock

from backend.services.bot_metrics_service import BotMetricsService, BotName


def _make_get_connection(autonomous_config_row=None, valor_account_row=(600000.0,)):
    """Each call to _get_connection() in the real code opens a fresh
    connection for one query. Hand back the next queued row in call order:
    call #1 -> autonomous_config lookup, call #2 -> valor_paper_account
    lookup (VALOR only)."""
    responses = [autonomous_config_row, valor_account_row]
    calls = {"n": 0}

    def _get_connection():
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        idx = calls["n"]
        calls["n"] += 1
        cursor.fetchone.return_value = responses[idx] if idx < len(responses) else None
        return conn

    _get_connection.calls = calls
    return _get_connection


def test_valor_capital_falls_back_to_real_paper_account_not_stale_default(monkeypatch):
    service = BotMetricsService()
    monkeypatch.setattr(service, "_get_connection", _make_get_connection())
    monkeypatch.setattr(service, "_get_tradier_balance", lambda sandbox=False: None)

    config = service.get_capital_config(BotName.VALOR, force_refresh=True)

    assert config.starting_capital == 600000.0
    assert config.capital_source == "valor_paper_account"
    # Must NOT be the stale single-instrument default.
    assert config.starting_capital != BotMetricsService.DEFAULT_CAPITAL[BotName.VALOR]


def test_valor_explicit_db_override_still_wins_over_paper_account(monkeypatch):
    """An explicit operator override in autonomous_config must still take
    priority over the paper-account fallback."""
    service = BotMetricsService()
    monkeypatch.setattr(
        service, "_get_connection", _make_get_connection(autonomous_config_row=("750000",))
    )
    monkeypatch.setattr(service, "_get_tradier_balance", lambda sandbox=False: None)

    config = service.get_capital_config(BotName.VALOR, force_refresh=True)

    assert config.starting_capital == 750000.0
    assert config.capital_source == "database"


def test_valor_falls_back_to_stale_default_only_if_no_data_available(monkeypatch):
    """If neither an override nor a paper account row exists, the hardcoded
    default is the last resort (unchanged behavior)."""
    service = BotMetricsService()
    monkeypatch.setattr(
        service, "_get_connection", _make_get_connection(valor_account_row=None)
    )
    monkeypatch.setattr(service, "_get_tradier_balance", lambda sandbox=False: None)

    config = service.get_capital_config(BotName.VALOR, force_refresh=True)

    assert config.starting_capital == BotMetricsService.DEFAULT_CAPITAL[BotName.VALOR]
    assert config.capital_source == "default"


def test_other_bots_are_unaffected_by_the_valor_fallback(monkeypatch):
    """FORTRESS (and every non-VALOR bot) must not attempt the VALOR-specific
    paper-account lookup at all."""
    service = BotMetricsService()
    get_conn = _make_get_connection()
    monkeypatch.setattr(service, "_get_connection", get_conn)
    monkeypatch.setattr(service, "_get_tradier_balance", lambda sandbox=False: None)

    config = service.get_capital_config(BotName.FORTRESS, force_refresh=True)

    assert config.starting_capital == BotMetricsService.DEFAULT_CAPITAL[BotName.FORTRESS]
    # Only the generic autonomous_config lookup should have run - never the
    # VALOR-specific paper-account fallback query.
    assert get_conn.calls["n"] == 1
