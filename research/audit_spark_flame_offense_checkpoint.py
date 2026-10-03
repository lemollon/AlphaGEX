"""Independent stored-ledger audit. Does not load or execute the replay engine."""
import argparse
import base64
import collections
import datetime as dt
import gzip
import hashlib
import json
from decimal import Decimal
from pathlib import Path


def audit(checkpoint, sessions):
    errors, result = [], []
    reasons = collections.Counter()
    state = checkpoint['state']
    if state['completed'] != 751 or state['stage'] != 'completed' or state['dataErrors']:
        errors.append('checkpoint_not_complete')
    accounts = checkpoint['accounts']
    identities = [(a['scenario']['id'], a['fillCase']) for a in accounts]
    if len(accounts) != 96 or len(set(identities)) != 96:
        errors.append('path_identity_count')
    for a in accounts:
        ident = f"{a['scenario']['id']}:{a['fillCase']}"
        rows = json.loads(gzip.decompress(base64.b64decode(a['packed']))) + a.get('history', [])
        if [r[0] for r in rows] != sessions:
            errors.append(ident + ':session_coverage')
        equity = Decimal(str(a['deposit']))
        closed = 0
        for day, before, after, pnl, status, reason in rows:
            before, after, pnl = map(lambda x: Decimal(str(x)), (before, after, pnl))
            if before != equity or after != before + pnl:
                errors.append(ident + ':cash_chain:' + day)
            if status != 'closed' and pnl != 0:
                errors.append(ident + ':nontrade_pnl:' + day)
            closed += status == 'closed'
            reasons[(status, reason)] += 1
            equity = after
        if equity != Decimal(str(a['equity'])):
            errors.append(ident + ':ending_equity')
        if closed != len(a['trades']) or a['unresolved']:
            errors.append(ident + ':trade_or_unresolved_count')
        trade_pnl = sum((Decimal(str(t['pnl'])) for t in a['trades']), Decimal(0))
        pnl = equity - Decimal(str(a['deposit']))
        if trade_pnl != pnl:
            errors.append(ident + ':trade_reconciliation')
        result.append({'id': ident, 'sessions': len(rows), 'trades': closed,
                       'pnl': float(pnl), 'netAfterExternalSubscription': float(pnl - 1800),
                       'endingEquity': float(equity)})
    return {'storedLedgerAuditPass': not errors, 'errors': errors, 'paths': result,
            'reasonCounts': [{'status': k[0], 'reason': k[1], 'accountDays': v}
                             for k, v in sorted(reasons.items())],
            'limits': ['Stored ledger/account coverage audit only; quotes and signals were not exported.',
                       'Standalone $2000 accounts; no Spark $5000 or combined host ledger.',
                       'Runner used raw VIX table/provider OHLC rather than mandated valid views.',
                       'Budget/cash/quote failures cannot be separated from saved reason labels.',
                       'Runner stopped at the first unaffordable candidate; later candidates were not tested.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('checkpoint', type=Path)
    parser.add_argument('--sessions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.checkpoint.read_bytes()
    checkpoint = json.loads(raw)
    sessions_input = json.loads(args.sessions.read_text())
    sessions = [s if isinstance(s, str) else s['day'] for s in sessions_input]
    result = audit(checkpoint, sessions)
    result['checkpointSha256'] = hashlib.sha256(raw).hexdigest()
    result['auditedAtUTC'] = dt.datetime.now(dt.timezone.utc).isoformat()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'pass': result['storedLedgerAuditPass'], 'paths': len(result['paths']),
                      'trades': sum(x['trades'] for x in result['paths']),
                      'errors': result['errors'], 'reasonCounts': result['reasonCounts']}))
    if result['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
