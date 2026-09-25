"""Read-only research metadata. Public requests cannot initiate paid downloads.

Legacy aggregate results remain preserved in Postgres, but are provisional:
clock buckets were not true position limits and MNG's multiplier was wrong.
"""
import os
from datetime import date
from functools import lru_cache
from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix='/api/valor/research/databento', tags=['valor-research'])

MES_MICRODATA_DATASET = 'GLBX.MDP3'
MES_MICRODATA_SYMBOL = 'MES.FUT'
MES_MICRODATA_STYPE_IN = 'parent'
MES_MICRODATA_START = '2023-01-01'
MES_MICRODATA_END = '2026-01-01'
MES_MICRODATA_SCHEMAS = ('trades', 'mbp-1')


@router.get('/status')
async def databento_status():
    return {'configured': bool(os.getenv('DATABENTO_API_KEY')),
            'key_authenticated': 'not_checked_by_status',
            'engine': 'valor-contract-v2-20260923',
            'research_only': True, 'gex_used': False,
            'legacy_results': 'provisional_not_live_validation',
            'public_paid_downloads_enabled': False}


@lru_cache(maxsize=4)
def _estimate(start: str, end: str):
    import databento as db
    from scripts.valor_contract_research_v2 import PRODUCTS
    key = os.environ['DATABENTO_API_KEY']
    client = db.Historical(key)
    rows = []
    for ticker, cfg in PRODUCTS.items():
        cost = float(client.metadata.get_cost(dataset='GLBX.MDP3',schema='ohlcv-1m',
                     symbols=cfg[0],stype_in='continuous',start=start,end=end))
        rows.append({'ticker':ticker,'symbol':cfg[0],'estimated_cost_usd':cost})
    return {'requests':rows,'total_estimate_usd':sum(r['estimated_cost_usd'] for r in rows),
            'start':start,'end_exclusive':end,'credit_balance_verified':False,
            'downloads_started':False}


@lru_cache(maxsize=1)
def _estimate_mes_microdata_cost():
    """Fetch fixed provider metadata without initiating a data request."""
    import databento as db

    client = db.Historical(os.environ['DATABENTO_API_KEY'])
    estimates = []
    for schema in MES_MICRODATA_SCHEMAS:
        parameters = {
            'dataset': MES_MICRODATA_DATASET,
            'symbols': MES_MICRODATA_SYMBOL,
            'stype_in': MES_MICRODATA_STYPE_IN,
            'schema': schema,
            'start': MES_MICRODATA_START,
            'end': MES_MICRODATA_END,
        }
        cost = float(client.metadata.get_cost(**parameters))
        billable_size = int(client.metadata.get_billable_size(**parameters))
        estimates.append({
            'schema': schema,
            'estimated_cost_usd': cost,
            'billable_size_bytes': billable_size,
        })
    return {
        'endpoint': '/api/valor/research/databento/mes-microdata-cost',
        'provider_methods': ['metadata.get_cost', 'metadata.get_billable_size'],
        'metadata_only': True,
        'downloads_started': False,
        'spend_authorized': False,
        'research_only': True,
        'parameters': {
            'dataset': MES_MICRODATA_DATASET,
            'symbol': MES_MICRODATA_SYMBOL,
            'stype_in': MES_MICRODATA_STYPE_IN,
            'start': MES_MICRODATA_START,
            'end_exclusive': MES_MICRODATA_END,
            'schemas': list(MES_MICRODATA_SCHEMAS),
        },
        'estimates': estimates,
        'total_estimate_usd': sum(row['estimated_cost_usd'] for row in estimates),
        'total_billable_size_bytes': sum(row['billable_size_bytes'] for row in estimates),
        'provider_note': (
            'The estimate respects provider plan discounts; actual billed bytes '
            'govern any future separately approved request.'
        ),
    }


@router.get('/cost')
async def databento_cost(start: str='2023-01-01', end: str='2026-01-01'):
    try:
        first,last=date.fromisoformat(start),date.fromisoformat(end)
        if not date(2023,1,1)<=first<last<=date(2026,1,1):
            raise ValueError('Outside fixed research window')
    except ValueError as exc:
        raise HTTPException(400,'Use dates within 2023-01-01 to 2026-01-01 exclusive.') from exc
    try:
        return await run_in_threadpool(_estimate,start,end)
    except Exception as exc:
        # Do not echo provider credentials or account details to a public route.
        raise HTTPException(502,'Cost metadata unavailable; no download started.') from exc


@router.get('/mes-microdata-cost')
async def mes_microdata_cost():
    try:
        return await run_in_threadpool(_estimate_mes_microdata_cost)
    except Exception as exc:
        # Do not echo provider credentials or account details to a public route.
        raise HTTPException(502,'Cost metadata unavailable; no download started.') from exc


@router.get('/run-year')
async def databento_run_year(ticker: str, year: int):
    raise HTTPException(410,'Legacy public paid-download route disabled. Use the locked, budgeted research worker.')


def launch_autorun_if_enabled():
    return False


def launch_contract_search_if_enabled():
    return False
