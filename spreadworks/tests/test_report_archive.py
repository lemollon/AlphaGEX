import json
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from backend.report_archive import load_archive

@pytest.fixture
def archive_db():
    engine=create_engine('sqlite://')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE sw_full_reports (report_id TEXT, generated_at TIMESTAMP, kind TEXT, payload_json TEXT)'))
        for id,stamp,kind,raw in [('a'*24,'2026-10-06 04:59:00','intraday','{}'),
                                ('b'*24,'2026-10-06 05:00:00','morning',json.dumps({'report_completeness':'INCOMPLETE'})),
                                ('c'*24,'2026-10-06 06:00:00','verification','{}'),
                                ('d'*24,'2026-10-06 12:40:00','morning','broken')]:
            c.execute(text('INSERT INTO sw_full_reports VALUES (:id,:stamp,:kind,:raw)'),dict(id=id,stamp=stamp,kind=kind,raw=raw))
    return engine

def test_archive_excludes_verification_and_pages_stably(archive_db):
    page=load_archive(archive_db,1,0)
    assert page['total']==3 and page['next_offset']==1
    assert page['reports'][0]['report_id']=='d'*24
    assert not page['reports'][0]['readable']
    assert load_archive(archive_db,1,1)['reports'][0]['report_id']=='b'*24

def test_date_uses_central_midnight_and_preserves_original_clock(archive_db):
    page=load_archive(archive_db,24,0,'morning','2026-10-06')
    assert page['total']==2
    row=page['reports'][1]
    assert row['generated_at']=='2026-10-06T05:00:00+00:00' and row['time_ct']=='00:00'
    assert 'LIVE' not in str(row)
    assert load_archive(archive_db,24,0,None,'2026-10-05')['total']==1

@pytest.mark.parametrize('kwargs',[{'kind':'verification'},{'kind':"morning' OR 1=1"},{'trading_date':'2026-02-30'},{'limit':101},{'offset':-1}])
def test_archive_rejects_invalid_filters(archive_db,kwargs):
    with pytest.raises(HTTPException):load_archive(archive_db,**kwargs)
