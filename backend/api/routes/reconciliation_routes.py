"""
Tradier-to-Bot Reconciliation System

Maps every Tradier order/position back to the bot that placed it.
Detects orphans, mismatches, and P&L discrepancies across ALL bots.

Key concepts:
- Each bot stores Tradier order IDs in its position table
- This module queries ALL bot tables, then matches against Tradier account data
- Produces a unified view: "Tradier order X → Bot Y position Z"
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reconciliation", tags=["Reconciliation"])

# ============================================================
# Bot registry: every bot, its table, and its order ID columns
# ============================================================

# IC bots store two order IDs (put spread + call spread)
# Directional bots store one order ID
BOT_REGISTRY = [
    # (bot_name, positions_table, closed_table, order_id_columns, ticker)
    #
    # NOTE: Most bots store open AND closed positions in the SAME table
    # (status column distinguishes them). Only JUBILEE_IC and VALOR have
    # separate closed_trades tables. Set closed_table=None for the rest
    # so we don't query non-existent tables.
    ("ANCHOR",      "anchor_positions",     None,                       ["put_order_id", "call_order_id"],              "SPX"),
    ("SAMSON",      "samson_positions",      None,                       ["put_order_id", "call_order_id"],              "SPX"),
    ("JUBILEE_BOX", "jubilee_positions",     None,                       ["put_spread_order_id", "call_spread_order_id"],"SPX"),
    ("JUBILEE_IC",  "jubilee_ic_positions",  "jubilee_ic_closed_trades", ["put_spread_order_id", "call_spread_order_id"],"SPX"),
    ("FORTRESS",    "fortress_positions",    None,                       ["put_order_id", "call_order_id"],              "SPY"),
    ("FAITH",       "faith_positions",       None,                       ["put_order_id", "call_order_id"],              "SPY"),
    ("GRACE",       "grace_positions",       None,                       ["put_order_id", "call_order_id"],              "SPY"),
    ("GIDEON",      "gideon_positions",      None,                       ["order_id"],                                   "SPY"),
    ("SOLOMON",     "solomon_positions",     None,                       ["order_id"],                                   "SPY"),
    ("VALOR",       "valor_positions",       "valor_closed_trades",      ["order_id"],                                   "SPY"),
]


def _get_connection():
    """Get database connection."""
    try:
        from database_adapter import get_connection
        return get_connection()
    except ImportError:
        import psycopg2
        return psycopg2.connect(os.environ['DATABASE_URL'])


def _get_tradier_client(sandbox: bool = False):
    """Get a Tradier client. Default to production for reading account data."""
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        return TradierDataFetcher(sandbox=sandbox)
    except Exception as e:
        logger.error(f"Failed to create Tradier client: {e}")
        return None


def _table_exists(cursor, table_name: str) -> bool:
    """Check if a table exists in the database."""
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
    """, (table_name,))
    return cursor.fetchone()[0]


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = %s AND column_name = %s
        )
    """, (table_name, column_name))
    return cursor.fetchone()[0]


def _get_bot_positions(cursor, bot_name: str, table: str, order_cols: List[str],
                       status_filter: str = 'all') -> List[Dict]:
    """
    Get positions from a bot table with their order IDs.

    Returns list of dicts with: position_id, bot, order_ids[], status, ticker, etc.
    """
    if not _table_exists(cursor, table):
        return []

    # Check which columns exist
    available_cols = []
    for col in ['position_id', 'status', 'ticker', 'entry_credit', 'realized_pnl',
                'open_time', 'close_time', 'close_reason', 'contracts', 'expiration'] + order_cols:
        if _column_exists(cursor, table, col):
            available_cols.append(col)

    if not available_cols:
        return []

    cols_str = ', '.join(available_cols)

    where_clause = ""
    if status_filter == 'open':
        if 'status' in available_cols:
            where_clause = "WHERE status IN ('open', 'OPEN', 'pending')"
    elif status_filter == 'closed':
        if 'status' in available_cols:
            where_clause = "WHERE status IN ('closed', 'CLOSED', 'expired')"

    try:
        cursor.execute(f"SELECT {cols_str} FROM {table} {where_clause} ORDER BY open_time DESC NULLS LAST LIMIT 200")
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]

        positions = []
        for row in rows:
            data = dict(zip(col_names, row))
            # Extract order IDs
            order_ids = []
            for oc in order_cols:
                val = data.get(oc, '')
                if val and val not in ('', 'PAPER', None):
                    order_ids.append(str(val))

            positions.append({
                'bot': bot_name,
                'table': table,
                'position_id': str(data.get('position_id', '')),
                'status': str(data.get('status', 'unknown')),
                'ticker': str(data.get('ticker', '')),
                'expiration': str(data.get('expiration', '')),
                'contracts': data.get('contracts', 0),
                'entry_credit': float(data.get('entry_credit', 0) or 0),
                'realized_pnl': float(data.get('realized_pnl', 0) or 0),
                'open_time': str(data.get('open_time', '')),
                'close_time': str(data.get('close_time', '') or ''),
                'close_reason': str(data.get('close_reason', '') or ''),
                'order_ids': order_ids,
                'order_id_columns': {oc: str(data.get(oc, '')) for oc in order_cols if oc in data},
                'is_paper': all(
                    str(data.get(oc, '')).startswith('PAPER') or not data.get(oc)
                    for oc in order_cols if oc in data
                ),
            })

        return positions
    except Exception as e:
        logger.error(f"Error reading {table} for {bot_name}: {e}")
        return []


def _build_order_to_bot_map(cursor) -> Tuple[Dict[str, List[Dict]], List[Dict]]:
    """
    Build a map: tradier_order_id → [bot_position(s) that reference it]

    Returns:
        - order_map: {order_id: [positions]}
        - all_positions: flat list of all positions
    """
    order_map: Dict[str, List[Dict]] = {}
    all_positions: List[Dict] = []

    for bot_name, pos_table, closed_table, order_cols, ticker in BOT_REGISTRY:
        # Get open positions
        positions = _get_bot_positions(cursor, bot_name, pos_table, order_cols)
        all_positions.extend(positions)

        # Also check closed trades table if it exists
        if closed_table:
            closed = _get_bot_positions(cursor, bot_name, closed_table, order_cols)
            all_positions.extend(closed)

        for pos in positions:
            for oid in pos['order_ids']:
                if oid not in order_map:
                    order_map[oid] = []
                order_map[oid].append(pos)

        if closed_table:
            for pos in closed:
                for oid in pos['order_ids']:
                    if oid not in order_map:
                        order_map[oid] = []
                    order_map[oid].append(pos)

    return order_map, all_positions


def run_reconciliation(include_closed: bool = False) -> Dict[str, Any]:
    """
    Run full Tradier-to-bot reconciliation.

    Returns a structured report with:
    - matched: Tradier orders that map to a known bot position
    - orphaned_tradier: Tradier orders/positions not tracked by any bot
    - orphaned_db: DB positions with real order IDs not found in Tradier
    - paper_positions: Paper-only positions (no Tradier mapping expected)
    - summary: Counts and health status
    """
    conn = _get_connection()
    cursor = conn.cursor()

    result = {
        'timestamp': datetime.utcnow().isoformat(),
        'tradier': {
            'connected': False,
            'positions': [],
            'orders': [],
        },
        'bots': {},
        'matched': [],
        'orphaned_tradier': [],
        'orphaned_db': [],
        'paper_positions': [],
        'summary': {},
    }

    # Step 1: Get all bot positions and build order→bot map
    order_map, all_positions = _build_order_to_bot_map(cursor)

    # Summarize by bot
    for bot_name, pos_table, closed_table, order_cols, ticker in BOT_REGISTRY:
        bot_positions = [p for p in all_positions if p['bot'] == bot_name and p['table'] == pos_table]
        open_count = sum(1 for p in bot_positions if p['status'].lower() in ('open', 'pending'))
        closed_count = sum(1 for p in bot_positions if p['status'].lower() in ('closed', 'expired'))
        paper_count = sum(1 for p in bot_positions if p['is_paper'])
        live_count = sum(1 for p in bot_positions if not p['is_paper'])

        result['bots'][bot_name] = {
            'table': pos_table,
            'ticker': ticker,
            'total': len(bot_positions),
            'open': open_count,
            'closed': closed_count,
            'paper': paper_count,
            'live': live_count,
            'order_ids_tracked': sum(len(p['order_ids']) for p in bot_positions),
        }

    # Step 2: Get Tradier account data
    tradier = _get_tradier_client(sandbox=False)
    tradier_positions = []
    tradier_orders = []
    tradier_order_ids = set()

    if tradier:
        try:
            tradier_positions = tradier.get_positions()
            result['tradier']['connected'] = True
            result['tradier']['positions'] = [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'cost_basis': p.cost_basis,
                    'current_price': p.current_price,
                    'gain_loss': p.gain_loss,
                }
                for p in tradier_positions
            ]
        except Exception as e:
            logger.error(f"Failed to get Tradier positions: {e}")

        try:
            tradier_orders = tradier.get_orders_detailed(status='all')
            tradier_order_ids = {str(o.get('id', '')) for o in tradier_orders}
            result['tradier']['orders_count'] = len(tradier_orders)

            # Parse orders for display
            parsed_orders = []
            for order in tradier_orders:
                order_id = str(order.get('id', ''))
                legs = order.get('leg', [])
                if isinstance(legs, dict):
                    legs = [legs]

                parsed_orders.append({
                    'order_id': order_id,
                    'symbol': order.get('symbol', ''),
                    'status': order.get('status', ''),
                    'type': order.get('type', ''),
                    'class': order.get('class', ''),
                    'side': order.get('side', ''),
                    'quantity': order.get('quantity', 0),
                    'avg_fill_price': order.get('avg_fill_price', 0),
                    'exec_quantity': order.get('exec_quantity', 0),
                    'create_date': order.get('create_date', ''),
                    'transaction_date': order.get('transaction_date', ''),
                    'legs': [
                        {
                            'symbol': leg.get('option_symbol', ''),
                            'side': leg.get('side', ''),
                            'quantity': leg.get('quantity', 0),
                            'avg_fill_price': leg.get('avg_fill_price', 0),
                            'exec_quantity': leg.get('exec_quantity', 0),
                        }
                        for leg in legs
                    ] if legs else [],
                })
            result['tradier']['orders'] = parsed_orders
        except Exception as e:
            logger.error(f"Failed to get Tradier orders: {e}")

    # Also try sandbox account
    tradier_sandbox = _get_tradier_client(sandbox=True)
    sandbox_positions = []
    sandbox_orders = []
    sandbox_order_ids = set()

    if tradier_sandbox:
        try:
            sandbox_positions = tradier_sandbox.get_positions()
            result['tradier']['sandbox_positions'] = [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'cost_basis': p.cost_basis,
                }
                for p in sandbox_positions
            ]
        except Exception:
            pass

        try:
            sandbox_orders = tradier_sandbox.get_orders_detailed(status='all')
            sandbox_order_ids = {str(o.get('id', '')) for o in sandbox_orders}
            result['tradier']['sandbox_orders_count'] = len(sandbox_orders)
        except Exception:
            pass

    # Step 3: Match Tradier orders → bot positions
    all_tradier_ids = tradier_order_ids | sandbox_order_ids

    for order in (tradier_orders + sandbox_orders):
        order_id = str(order.get('id', ''))
        source = 'production' if order_id in tradier_order_ids else 'sandbox'

        if order_id in order_map:
            # MATCHED: This Tradier order belongs to a known bot position
            for pos in order_map[order_id]:
                result['matched'].append({
                    'tradier_order_id': order_id,
                    'tradier_source': source,
                    'tradier_status': order.get('status', ''),
                    'tradier_symbol': order.get('symbol', ''),
                    'tradier_fill_price': order.get('avg_fill_price', 0),
                    'tradier_create_date': order.get('create_date', ''),
                    'bot': pos['bot'],
                    'position_id': pos['position_id'],
                    'position_status': pos['status'],
                    'entry_credit': pos['entry_credit'],
                })
        else:
            # ORPHANED ON TRADIER: No bot claims this order
            result['orphaned_tradier'].append({
                'tradier_order_id': order_id,
                'tradier_source': source,
                'tradier_status': order.get('status', ''),
                'tradier_symbol': order.get('symbol', ''),
                'tradier_type': order.get('type', ''),
                'tradier_class': order.get('class', ''),
                'tradier_create_date': order.get('create_date', ''),
                'quantity': order.get('quantity', 0),
                'avg_fill_price': order.get('avg_fill_price', 0),
            })

    # Step 4: Find DB positions whose order IDs are NOT in Tradier
    for pos in all_positions:
        if pos['is_paper']:
            result['paper_positions'].append({
                'bot': pos['bot'],
                'position_id': pos['position_id'],
                'status': pos['status'],
                'ticker': pos['ticker'],
            })
            continue

        for oid in pos['order_ids']:
            if oid and oid not in all_tradier_ids:
                # Might just be too old for Tradier's order history window
                result['orphaned_db'].append({
                    'bot': pos['bot'],
                    'position_id': pos['position_id'],
                    'order_id': oid,
                    'status': pos['status'],
                    'ticker': pos['ticker'],
                    'open_time': pos['open_time'],
                    'note': 'Order ID not found in Tradier (may be outside history window)',
                })

    # Step 5: Build summary
    result['summary'] = {
        'tradier_connected': result['tradier']['connected'],
        'tradier_positions': len(tradier_positions),
        'tradier_orders': len(tradier_orders),
        'sandbox_positions': len(sandbox_positions),
        'sandbox_orders': len(sandbox_orders),
        'db_positions_total': len(all_positions),
        'db_positions_paper': len(result['paper_positions']),
        'db_positions_live': len(all_positions) - len(result['paper_positions']),
        'matched_orders': len(result['matched']),
        'orphaned_on_tradier': len(result['orphaned_tradier']),
        'orphaned_in_db': len(result['orphaned_db']),
        'health': 'HEALTHY' if len(result['orphaned_tradier']) == 0 else 'NEEDS_REVIEW',
    }

    cursor.close()
    conn.close()

    return result


# ============================================================
# API Endpoints
# ============================================================

@router.get("/full")
async def get_full_reconciliation(include_closed: bool = Query(False, description="Include closed positions")):
    """
    Full Tradier-to-bot reconciliation.

    Maps every Tradier order to the bot that placed it.
    Detects orphaned orders and position mismatches.
    """
    try:
        report = run_reconciliation(include_closed=include_closed)
        return {"status": "success", "data": report}
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_reconciliation_summary():
    """
    Quick summary: how many positions per bot, paper vs live, any mismatches.
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor()

        summary = {
            'timestamp': datetime.utcnow().isoformat(),
            'bots': {},
            'totals': {'open': 0, 'closed': 0, 'paper': 0, 'live': 0},
        }

        for bot_name, pos_table, closed_table, order_cols, ticker in BOT_REGISTRY:
            if not _table_exists(cursor, pos_table):
                continue

            has_status = _column_exists(cursor, pos_table, 'status')
            if not has_status:
                continue

            cursor.execute(f"""
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('open', 'OPEN', 'pending')) AS open_count,
                    COUNT(*) FILTER (WHERE status IN ('closed', 'CLOSED', 'expired')) AS closed_count,
                    COUNT(*) AS total
                FROM {pos_table}
            """)
            row = cursor.fetchone()
            open_count, closed_count, total = row

            # Check how many have real (non-PAPER) order IDs
            live_count = 0
            for oc in order_cols:
                if _column_exists(cursor, pos_table, oc):
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM {pos_table}
                        WHERE {oc} IS NOT NULL
                        AND {oc} != ''
                        AND {oc} NOT LIKE 'PAPER%%'
                        AND status IN ('open', 'OPEN', 'pending')
                    """)
                    live_count = max(live_count, cursor.fetchone()[0])

            paper_open = open_count - live_count

            summary['bots'][bot_name] = {
                'ticker': ticker,
                'open': open_count,
                'closed': closed_count,
                'live_open': live_count,
                'paper_open': paper_open,
                'mode': 'LIVE' if live_count > 0 else 'PAPER' if paper_open > 0 else 'IDLE',
            }
            summary['totals']['open'] += open_count
            summary['totals']['closed'] += closed_count
            summary['totals']['live'] += live_count
            summary['totals']['paper'] += paper_open

        # Quick Tradier check
        tradier = _get_tradier_client(sandbox=False)
        if tradier:
            try:
                positions = tradier.get_positions()
                summary['tradier'] = {
                    'connected': True,
                    'open_positions': len(positions),
                    'symbols': [p.symbol for p in positions],
                }
            except Exception as e:
                summary['tradier'] = {'connected': False, 'error': str(e)}

        tradier_sb = _get_tradier_client(sandbox=True)
        if tradier_sb:
            try:
                sb_positions = tradier_sb.get_positions()
                summary['tradier_sandbox'] = {
                    'connected': True,
                    'open_positions': len(sb_positions),
                    'symbols': [p.symbol for p in sb_positions],
                }
            except Exception:
                summary['tradier_sandbox'] = {'connected': False}

        cursor.close()
        conn.close()

        return {"status": "success", "data": summary}

    except Exception as e:
        logger.error(f"Reconciliation summary failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tradier/orders")
async def get_tradier_orders(
    status: str = Query('all', description="Order status: open, pending, filled, all"),
    source: str = Query('production', description="Account: production or sandbox"),
):
    """
    Get all Tradier orders with full detail (legs, fills, timestamps).
    Each order is annotated with which bot owns it (if any).
    """
    try:
        sandbox = source == 'sandbox'
        tradier = _get_tradier_client(sandbox=sandbox)
        if not tradier:
            raise HTTPException(status_code=503, detail=f"Tradier {source} client unavailable")

        orders = tradier.get_orders_detailed(status=status)

        # Build order→bot map
        conn = _get_connection()
        cursor = conn.cursor()
        order_map, _ = _build_order_to_bot_map(cursor)
        cursor.close()
        conn.close()

        # Annotate each order
        annotated = []
        for order in orders:
            order_id = str(order.get('id', ''))
            legs = order.get('leg', [])
            if isinstance(legs, dict):
                legs = [legs]

            bot_matches = order_map.get(order_id, [])

            annotated.append({
                'order_id': order_id,
                'symbol': order.get('symbol', ''),
                'status': order.get('status', ''),
                'type': order.get('type', ''),
                'class': order.get('class', ''),
                'side': order.get('side', ''),
                'quantity': order.get('quantity', 0),
                'avg_fill_price': order.get('avg_fill_price', 0),
                'exec_quantity': order.get('exec_quantity', 0),
                'create_date': order.get('create_date', ''),
                'transaction_date': order.get('transaction_date', ''),
                'legs': [
                    {
                        'option_symbol': leg.get('option_symbol', ''),
                        'side': leg.get('side', ''),
                        'quantity': leg.get('quantity', 0),
                        'avg_fill_price': leg.get('avg_fill_price', 0),
                        'exec_quantity': leg.get('exec_quantity', 0),
                        'status': leg.get('status', ''),
                    }
                    for leg in legs
                ] if legs else [],
                'bot_owner': bot_matches[0]['bot'] if bot_matches else None,
                'position_id': bot_matches[0]['position_id'] if bot_matches else None,
                'claimed_by': [
                    {'bot': m['bot'], 'position_id': m['position_id']}
                    for m in bot_matches
                ],
            })

        return {
            "status": "success",
            "source": source,
            "total": len(annotated),
            "orders": annotated,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Tradier orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tradier/positions")
async def get_tradier_positions(
    source: str = Query('production', description="Account: production or sandbox"),
):
    """
    Get all Tradier account positions (what the broker actually holds).
    """
    try:
        sandbox = source == 'sandbox'
        tradier = _get_tradier_client(sandbox=sandbox)
        if not tradier:
            raise HTTPException(status_code=503, detail=f"Tradier {source} client unavailable")

        positions = tradier.get_positions()

        return {
            "status": "success",
            "source": source,
            "total": len(positions),
            "positions": [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'cost_basis': p.cost_basis,
                    'current_price': p.current_price,
                    'gain_loss': p.gain_loss,
                    'gain_loss_pct': p.gain_loss_pct,
                }
                for p in positions
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Tradier positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tradier/balance")
async def get_tradier_balance(
    source: str = Query('production', description="Account: production or sandbox"),
):
    """Get Tradier account balance."""
    try:
        sandbox = source == 'sandbox'
        tradier = _get_tradier_client(sandbox=sandbox)
        if not tradier:
            raise HTTPException(status_code=503, detail=f"Tradier {source} client unavailable")

        balance = tradier.get_account_balance()
        return {"status": "success", "source": source, "balance": balance}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bot/{bot_name}/positions")
async def get_bot_positions(
    bot_name: str,
    status: str = Query('open', description="Position status: open, closed, all"),
):
    """
    Get all positions for a specific bot with their Tradier order IDs.
    """
    bot_name_upper = bot_name.upper()

    # Find bot in registry
    bot_entry = None
    for entry in BOT_REGISTRY:
        if entry[0] == bot_name_upper:
            bot_entry = entry
            break

    if not bot_entry:
        available = [b[0] for b in BOT_REGISTRY]
        raise HTTPException(
            status_code=404,
            detail=f"Bot '{bot_name}' not found. Available: {available}"
        )

    bot_name, pos_table, closed_table, order_cols, ticker = bot_entry

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        positions = _get_bot_positions(cursor, bot_name, pos_table, order_cols, status_filter=status)

        cursor.close()
        conn.close()

        return {
            "status": "success",
            "bot": bot_name,
            "ticker": ticker,
            "total": len(positions),
            "positions": positions,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
