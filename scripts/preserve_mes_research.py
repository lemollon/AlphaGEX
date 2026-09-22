#!/usr/bin/env python3
"""Preserve existing instance-local research in Postgres before a Render restart.

Only creates/inserts an archival table. Does not reset trading or change settings.
"""
import hashlib
import io
import os
import tarfile
from pathlib import Path
import psycopg2


def main():
    root = Path('/tmp/mes_research_c18cootu')
    if not root.is_dir():
        raise ValueError('Research directory missing; do not deploy until its location is resolved')
    files = sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink())
    if not files or sum(p.stat().st_size for p in files) > 100_000_000:
        raise ValueError('Archive is empty or exceeds 100 MB')
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for path in files:
            archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
    data = buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    with psycopg2.connect(os.environ['DATABASE_URL'],connect_timeout=15) as conn:
        with conn.cursor() as c:
            c.execute("SET LOCAL statement_timeout='60s'")
            c.execute('''CREATE TABLE IF NOT EXISTS valor_research_archives (
                sha256 TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                filename TEXT NOT NULL, file_count INTEGER NOT NULL, archive_bytes BYTEA NOT NULL)''')
            c.execute('''INSERT INTO valor_research_archives(sha256,filename,file_count,archive_bytes)
                VALUES (%s,%s,%s,%s) ON CONFLICT(sha256) DO NOTHING''',
                (digest,root.name+'.tar.gz',len(files),psycopg2.Binary(data)))
            c.execute('SELECT archive_bytes FROM valor_research_archives WHERE sha256=%s',(digest,))
            if hashlib.sha256(bytes(c.fetchone()[0])).hexdigest()!=digest:
                raise ValueError('Archive verification failed')
    print('RESEARCH PRESERVED:',len(files),'files;',len(data),'bytes; SHA256:',digest)
    print('Trading has not been reset. No orders or settings changed.')


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print('BACKUP FAILED:',type(exc).__name__)
        raise SystemExit(1)
