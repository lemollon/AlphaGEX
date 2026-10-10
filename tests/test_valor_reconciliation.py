from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from trading.valor.reconciliation import summarize_order
from trading.valor.trader import ValorTrader
from trading.valor.models import TradingMode, PositionStatus


def order(quantity=3,remaining=0,status='Filled'):
    fills=[] if quantity==remaining else [{'quantity':str(quantity-remaining),'fill-price':'100'}]
    return {'id':'123','status':status,'external-identifier':'intent',
            'legs':[{'instrument-type':'Future','symbol':'/MESZ6','action':'Sell to Close',
                     'quantity':str(quantity),'remaining-quantity':str(remaining),'fills':fills}]}


def test_weighted_average_fill():
    data=order();data['legs'][0]['fills']=[{'quantity':'1','fill-price':'100'},{'quantity':'2','fill-price':'103'}]
    result=summarize_order(data,'/MESZ6',3,'Sell to Close')
    assert result['price']==102 and result['quantity']==3 and result['terminal']


@pytest.mark.parametrize('field,value',[('symbol','/MNQZ6'),('action','Buy to Open'),('quantity','4'),
                                       ('remaining-quantity','-1'),('instrument-type','Equity')])
def test_mismatched_order_fails_closed(field,value):
    data=order();data['legs'][0][field]=value
    with pytest.raises(ValueError): summarize_order(data,'/MESZ6',3,'Sell to Close')


@pytest.mark.parametrize('fills', [[],[{'quantity':'3','fill-price':'NaN'}],
    [{'quantity':'2','fill-price':'100'}],[{'quantity':'3','fill-price':'-5'}]])
def test_incomplete_or_invalid_execution_history_rejected(fills):
    data=order();data['legs'][0]['fills']=fills
    with pytest.raises(ValueError): summarize_order(data,'/MESZ6',3,'Sell to Close')


def test_terminal_partial_is_distinct_from_full_fill():
    result=summarize_order(order(3,2,'Cancelled'),'/MESZ6',3,'Sell to Close')
    assert result['quantity']==1 and result['terminal']


def trader_with_intent(data):
    t=ValorTrader.__new__(ValorTrader);t.config=SimpleNamespace(mode=TradingMode.LIVE)
    t.db=MagicMock();t.executor=MagicMock();t._close_position=MagicMock()
    context={'kind':'close','position_id':'p','symbol':'/MESZ6','contracts':3,'action':'Sell to Close',
             'status':PositionStatus.CLOSED.value,'reason':'STOP'}
    t.db.get_pending_order_intents.return_value=[{'intent_id':'intent','ticker':'MES','context':context,'broker_order_id':'123'}]
    t.db.get_position_by_id.return_value=SimpleNamespace(position_id='p',contracts=3,status=PositionStatus.OPEN)
    t.executor.find_order.return_value=data
    return t


def test_delayed_full_close_reconciles_without_resubmission():
    t=trader_with_intent(order())
    ValorTrader.reconcile_pending_orders.__wrapped__(t)
    assert t._close_position.call_args.kwargs['reconciled_fill']==100
    t.executor.close_position_order.assert_not_called()


def test_unknown_submission_stays_pending_and_is_never_retried():
    t=trader_with_intent(None)
    ValorTrader.reconcile_pending_orders.__wrapped__(t)
    t.db.complete_order_intent.assert_not_called()
    t.executor.close_position_order.assert_not_called()


def test_partial_working_order_cancels_remainder_before_accounting():
    t=trader_with_intent(order(3,2,'Live'))
    ValorTrader.reconcile_pending_orders.__wrapped__(t)
    t.executor.cancel_order.assert_called_once_with('123')
    t.db.close_position.assert_not_called()
    t._close_position.assert_not_called()


def test_terminal_partial_close_uses_atomic_partial_ledger_path():
    t=trader_with_intent(order(3,2,'Cancelled'))
    t.db.close_position.return_value=(True,10)
    ValorTrader.reconcile_pending_orders.__wrapped__(t)
    assert t.db.close_position.call_args.kwargs['contracts_closed']==1
    assert t.db.close_position.call_args.kwargs['execution_id']=='intent'
    t.executor.close_position_order.assert_not_called()


def test_cancelled_unfilled_order_releases_intent():
    t=trader_with_intent(order(3,3,'Cancelled'))
    ValorTrader.reconcile_pending_orders.__wrapped__(t)
    t.db.complete_order_intent.assert_called_once_with('intent')


def test_already_accounted_close_completes_crash_recovery():
    t=trader_with_intent(order())
    t.db.get_position_by_id.return_value.status=PositionStatus.CLOSED
    ValorTrader.reconcile_pending_orders.__wrapped__(t)
    t.db.complete_order_intent.assert_called_once_with('intent')
    t.executor.find_order.assert_not_called()
