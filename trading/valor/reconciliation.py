"""Validate single-leg broker fills before changing Valor's position ledger."""
from decimal import Decimal, InvalidOperation

TERMINAL = {'Filled', 'Cancelled', 'Canceled', 'Rejected', 'Expired'}


def summarize_order(order, symbol, requested, action):
    """Return cumulative executions only when leg identity and quantities agree."""
    legs = order.get('legs') or []
    if len(legs) != 1:
        raise ValueError('Expected one futures leg')
    leg = legs[0]
    if leg.get('symbol') != symbol or leg.get('action') != action or leg.get('instrument-type') != 'Future':
        raise ValueError('Broker leg does not match persisted intent')
    try:
        quantity = Decimal(str(leg['quantity']))
        remaining = Decimal(str(leg['remaining-quantity']))
        if not quantity.is_finite() or not remaining.is_finite() or quantity != requested or not 0 <= remaining <= quantity:
            raise ValueError('Invalid broker quantities')
        executed = quantity - remaining
        fills = leg.get('fills') or []
        fill_qty = Decimal(0)
        notional = Decimal(0)
        for fill in fills:
            qty, price = Decimal(str(fill['quantity'])), Decimal(str(fill['fill-price']))
            if not qty.is_finite() or not price.is_finite() or qty <= 0 or price <= 0:
                raise ValueError('Invalid execution')
            fill_qty += qty
            notional += qty * price
        if fill_qty != executed:
            raise ValueError('Execution history is incomplete')
        if executed != int(executed):
            raise ValueError('Fractional futures execution')
        status = order.get('status')
        if status == 'Filled' and remaining != 0:
            raise ValueError('Filled status has remaining contracts')
        return {'quantity': int(executed), 'price': float(notional / executed) if executed else 0,
                'terminal': status in TERMINAL, 'status': status, 'order_id': str(order['id']),
                'filled_at': order.get('terminal-at') or order.get('updated-at')}
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise ValueError('Malformed broker execution') from exc
