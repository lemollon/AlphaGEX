"""Targeted tests for fixed, metadata-only VALOR research routes."""
from types import SimpleNamespace
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import valor_research_routes as routes


@pytest.fixture(autouse=True)
def clear_metadata_cache():
    routes._estimate_mes_microdata_cost.cache_clear()
    yield
    routes._estimate_mes_microdata_cost.cache_clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_mes_microdata_cost_uses_fixed_metadata_calls_and_cache(
        client, monkeypatch):
    cost_calls = []
    size_calls = []
    costs = {'trades': 12.25, 'mbp-1': 34.75}
    sizes = {'trades': 1_250, 'mbp-1': 8_750}

    class FakeMetadata:
        def get_cost(self, **kwargs):
            cost_calls.append(kwargs)
            return costs[kwargs['schema']]

        def get_billable_size(self, **kwargs):
            size_calls.append(kwargs)
            return sizes[kwargs['schema']]

    class FakeHistorical:
        def __init__(self, key):
            assert key == 'server-secret'
            self.metadata = FakeMetadata()

    monkeypatch.setenv('DATABENTO_API_KEY', 'server-secret')
    monkeypatch.setitem(sys.modules, 'databento', SimpleNamespace(Historical=FakeHistorical))

    url = ('/api/valor/research/databento/mes-microdata-cost'
           '?schema=ohlcv-1m&symbol=USER_CONTROLLED&start=2026-01-01')
    first = client.get(url)
    second = client.get(url)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    expected_calls = [
        {
            'dataset': 'GLBX.MDP3', 'symbols': 'MES.FUT', 'stype_in': 'parent',
            'schema': schema, 'start': '2023-01-01', 'end': '2026-01-01',
        }
        for schema in ('trades', 'mbp-1')
    ]
    assert cost_calls == expected_calls
    assert size_calls == expected_calls

    payload = first.json()
    assert payload['endpoint'] == '/api/valor/research/databento/mes-microdata-cost'
    assert payload['provider_methods'] == [
        'metadata.get_cost', 'metadata.get_billable_size',
    ]
    assert payload['parameters'] == {
        'dataset': 'GLBX.MDP3', 'symbol': 'MES.FUT', 'stype_in': 'parent',
        'start': '2023-01-01', 'end_exclusive': '2026-01-01',
        'schemas': ['trades', 'mbp-1'],
    }
    assert payload['estimates'] == [
        {'schema': 'trades', 'estimated_cost_usd': 12.25,
         'billable_size_bytes': 1_250},
        {'schema': 'mbp-1', 'estimated_cost_usd': 34.75,
         'billable_size_bytes': 8_750},
    ]
    assert payload['total_estimate_usd'] == 47.0
    assert payload['total_billable_size_bytes'] == 10_000
    assert payload['metadata_only'] is True
    assert payload['downloads_started'] is False
    assert payload['spend_authorized'] is False
    assert payload['research_only'] is True
    assert 'actual billed bytes' in payload['provider_note']
    assert 'server-secret' not in first.text


def test_mes_microdata_cost_missing_key_is_sanitized_502(client, monkeypatch):
    monkeypatch.delenv('DATABENTO_API_KEY', raising=False)
    monkeypatch.setitem(
        sys.modules, 'databento',
        SimpleNamespace(Historical=lambda key: pytest.fail('client must not initialize')),
    )

    response = client.get('/api/valor/research/databento/mes-microdata-cost')
    assert response.status_code == 502
    assert response.json() == {
        'detail': 'Cost metadata unavailable; no download started.'
    }
    assert 'DATABENTO_API_KEY' not in response.text


def test_mes_microdata_cost_provider_error_is_sanitized_502(client, monkeypatch):
    class FailingMetadata:
        def get_cost(self, **kwargs):
            raise RuntimeError('account=private key=do-not-echo')

        def get_billable_size(self, **kwargs):
            pytest.fail('size call must not follow failed cost metadata')

    class FakeHistorical:
        def __init__(self, key):
            self.metadata = FailingMetadata()

    monkeypatch.setenv('DATABENTO_API_KEY', 'do-not-echo')
    monkeypatch.setitem(sys.modules, 'databento', SimpleNamespace(Historical=FakeHistorical))

    response = client.get('/api/valor/research/databento/mes-microdata-cost')
    assert response.status_code == 502
    assert response.json() == {
        'detail': 'Cost metadata unavailable; no download started.'
    }
    assert 'private' not in response.text
    assert 'do-not-echo' not in response.text
