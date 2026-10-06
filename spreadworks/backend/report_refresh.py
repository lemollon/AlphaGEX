"""Refresh before publication; preserve verified observations on provider failure.

An attempted request is never a new exchange clock. Independent producers have
bounded deadlines and one retry. This path serves both morning and intraday.
"""
import asyncio
from datetime import datetime, timezone

UTC = timezone.utc


def verified(row):
    from .report_policy import parse_clock, finite_tree
    return (isinstance(row, dict) and row.get('confidence', 'MEDIUM') in ('HIGH', 'MEDIUM')
            and 'tradier' in str(row.get('source', '')).lower()
            and 'thetadata' not in str(row.get('source', '')).lower()
            and parse_clock(row.get('source_timestamp') or row.get('chain_timestamp'))
            and finite_tree(row))


async def bounded_refresh(name, collect, *, timeout=25):
    attempts = []
    for attempt in (1, 2):
        started = datetime.now(UTC)
        try:
            value = await asyncio.wait_for(asyncio.to_thread(collect), timeout if attempt == 1 else min(timeout, 8))
            reason = value.get('reason') if isinstance(value, dict) else 'Malformed producer response'
            attempts.append(dict(attempt=attempt, requested_at=started.isoformat(),
                                 completed_at=datetime.now(UTC).isoformat(), reason=reason))
            if isinstance(value, dict) and not reason:
                return value, dict(producer=name, attempts=attempts, outcome='updated')
        except Exception as exc:
            attempts.append(dict(attempt=attempt, requested_at=started.isoformat(),
                                 completed_at=datetime.now(UTC).isoformat(), reason=type(exc).__name__))
    return None, dict(producer=name, attempts=attempts, outcome='last_known_or_unavailable')


async def refresh_context(now, plan):
    from . import full_options_report as report
    from .report_producers import collect_breadth, collect_profile, collect_macro
    symbols = ['SPY', 'QQQ', *(plan.get('symbols') or [])]
    async def breadth():
        attempts=[]
        for attempt in (1, 2):
            try:
                value=await asyncio.wait_for(collect_breadth(datetime.now(UTC), symbols), 25 if attempt==1 else 8)
                attempts.append(dict(attempt=attempt, reason=value.get('reason')))
                if value.get('source_timestamp'):
                    await asyncio.to_thread(report.save_evidence,'breadth',value,datetime.now(UTC))
                    break
            except Exception as exc:attempts.append(dict(attempt=attempt, reason=type(exc).__name__))
        return dict(producer='breadth', attempts=attempts)
    async def one(name, fn):
        value, audit = await bounded_refresh(name, fn)
        if value:
            await asyncio.to_thread(report.save_evidence, name, value, datetime.now(UTC))
        return audit
    previous={s:await asyncio.to_thread(report.load_evidence,'profile_'+s) for s in ('SPY','QQQ')}
    return await asyncio.gather(breadth(),one('macro',lambda:collect_macro(datetime.now(UTC))),
        *(one('profile_'+s,lambda s=s:collect_profile(s,datetime.now(UTC),previous[s])) for s in ('SPY','QQQ')))


async def refresh_core(core):
    from . import market_structure as ms
    audit=[]
    async def one(group, symbol, collect, persist):
        value, record=await bounded_refresh(group+'_'+symbol, collect)
        audit.append(record)
        if value and verified(value):
            # Do not overwrite a newer verified exchange observation with an older response.
            from .report_policy import parse_clock
            stamp=parse_clock(value.get('source_timestamp') or value.get('chain_timestamp'))
            value=dict(value, source_timestamp=stamp.isoformat())
            old=core.get(group,{}).get(symbol) or {}
            old_stamp=parse_clock(old.get('source_timestamp'))
            if group=='surface' and verified(old):
                # A partial successful refresh must not erase a previously observed
                # RV/skew/bucket. Each carried metric keeps its own older clock.
                clocks=dict(value.get('field_timestamps') or {})
                for key in ('atm_iv','skew_25d','iv_0dte','iv_1_5dte','iv_6_20dte','iv_21_365dte',
                            'realized_vol_60m','iv_minus_realized_vol','realized_vol_source_timestamp',
                            'realized_vol_method','realized_vol_bars','smile','surface_read','iv_rv_comparison'):
                    current=value.get(key)
                    absent=current is None or (isinstance(current,dict) and (current.get('available') is False or (key=='iv_rv_comparison' and current.get('realized_vol_60m') is None)))
                    if absent and old.get(key) is not None:
                        value[key]=old[key]
                        clocks[key]=(old.get('field_timestamps') or {}).get(key) or old.get('source_timestamp')
                value['field_timestamps']=clocks
            if not verified(old) or not old_stamp or stamp>=old_stamp:
                core.setdefault(group,{})[symbol]=value
            try:await asyncio.to_thread(persist,value)
            except Exception as exc:record['persistence_error']=type(exc).__name__
        else:
            core.setdefault(group,{}).setdefault(symbol,{})['last_refresh_attempt']=record
    await asyncio.gather(*(one(group,symbol,collect,persist)
        for symbol in ('SPY','QQQ') for group,collect,persist in (
            ('surface',lambda s=symbol:ms.build_volatility_surface(s,datetime.now(UTC)),ms.persist_surface),
            ('gamma',lambda s=symbol:ms.build_gamma_snapshot(s,datetime.now(UTC),max_dte=ms.GAMMA_MAX_DTE,strike_range=ms.GAMMA_STRIKE_RANGE),ms.persist_snapshot))))
    # These faster producers run last, rather than aging while chains are loading.
    for group, collect, persist in (
        ('volatility',lambda:ms.fetch_vol_indices(datetime.now(UTC)),ms.persist_vol),
        ('cross_asset',lambda:ms.fetch_cross_asset(datetime.now(UTC)),ms.persist_cross_asset)):
        value,record=await bounded_refresh(group,collect,timeout=10);audit.append(record)
        if value and (value.get('indices') or value.get('assets')):
            old=core.get(group) or {}; key='indices' if group=='volatility' else 'assets'
            merged=dict(old.get(key) or {})
            for symbol,row in value.get(key,{}).items():
                if row.get('price') is not None and row.get('source_timestamp'):merged[symbol]=row
            core[group]=dict(value,**{key:merged})
            try:await asyncio.to_thread(persist,value)
            except Exception as exc:record['persistence_error']=type(exc).__name__
    return core,audit
