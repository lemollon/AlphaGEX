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


@router.get('/run-year')
async def databento_run_year(ticker: str, year: int):
    raise HTTPException(410,'Legacy public paid-download route disabled. Use the locked, budgeted research worker.')


def launch_autorun_if_enabled():
    return False


def launch_contract_search_if_enabled():
    return False
