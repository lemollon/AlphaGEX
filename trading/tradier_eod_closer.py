"""
Tradier Sandbox EOD Position Closer
====================================

Bulletproof end-of-day close mechanism for Tradier sandbox accounts.

Tradier sandbox accounts do NOT honor natural option expiration or carry
positions overnight. All positions must be explicitly closed before market
close via API orders. This module provides a centralized, reliable mechanism
to close all positions in all sandbox accounts before EOD.

Design:
1. Query actual Tradier sandbox account for ALL open positions
2. Cancel all open/pending orders (prevent interference with close orders)
3. Send MARKET orders to close every position (guarantees fill)
4. Verify each order fills with polling and retry
5. Log everything for audit trail

Usage:
    closer = TradierEODCloser()
    result = closer.close_all_positions()
    # or
    result = closer.close_all_positions(account_label="secondary")
"""

import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")
EASTERN_TZ = ZoneInfo("America/New_York")

# Maximum time to wait for order fill verification (seconds)
MAX_FILL_WAIT = 30
FILL_POLL_INTERVAL = 5
MAX_CLOSE_RETRIES = 3


class TradierEODCloser:
    """
    Centralized EOD position closer for Tradier sandbox accounts.

    Queries the ACTUAL Tradier sandbox account (not the bot database)
    and closes every position with MARKET orders.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        account_id: Optional[str] = None,
        sandbox: bool = True,
    ):
        """
        Initialize with Tradier sandbox credentials.

        Args:
            api_key: Sandbox API key (falls back to env/config)
            account_id: Sandbox account ID (falls back to env/config)
            sandbox: Must be True for sandbox accounts
        """
        self.sandbox = sandbox

        # Load credentials
        try:
            from unified_config import APIConfig
            if sandbox:
                self.api_key = api_key or APIConfig.TRADIER_SANDBOX_API_KEY or os.getenv('TRADIER_SANDBOX_API_KEY')
                self.account_id = account_id or APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or os.getenv('TRADIER_SANDBOX_ACCOUNT_ID')
            else:
                self.api_key = api_key or APIConfig.TRADIER_API_KEY or os.getenv('TRADIER_API_KEY')
                self.account_id = account_id or APIConfig.TRADIER_ACCOUNT_ID or os.getenv('TRADIER_ACCOUNT_ID')
        except ImportError:
            if sandbox:
                self.api_key = api_key or os.getenv('TRADIER_SANDBOX_API_KEY') or os.getenv('TRADIER_API_KEY')
                self.account_id = account_id or os.getenv('TRADIER_SANDBOX_ACCOUNT_ID') or os.getenv('TRADIER_ACCOUNT_ID')
            else:
                self.api_key = api_key or os.getenv('TRADIER_API_KEY')
                self.account_id = account_id or os.getenv('TRADIER_ACCOUNT_ID')

        self.base_url = "https://sandbox.tradier.com/v1" if sandbox else "https://api.tradier.com/v1"
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json'
        }

        if not self.api_key or not self.account_id:
            logger.warning(
                "TradierEODCloser: Missing API key or account ID. "
                "EOD close will be skipped for this account."
            )

    def _api_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make a Tradier API request with error handling."""
        import requests

        url = f"{self.base_url}/{endpoint}"

        try:
            if method == 'GET':
                resp = requests.get(url, headers=self.headers, params=data, timeout=15)
            elif method == 'POST':
                resp = requests.post(url, headers=self.headers, data=data, timeout=15)
            elif method == 'DELETE':
                resp = requests.delete(url, headers=self.headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")

            resp.raise_for_status()
            return resp.json()

        except Exception as e:
            logger.error(f"TradierEODCloser API error ({method} {endpoint}): {e}")
            return {}

    def health_check(self) -> bool:
        """Verify the Tradier sandbox API is reachable before attempting closes."""
        if not self.api_key or not self.account_id:
            logger.error("TradierEODCloser: No credentials configured")
            return False

        try:
            result = self._api_request('GET', f'accounts/{self.account_id}/balances')
            if result and 'balances' in result:
                logger.info("TradierEODCloser: API health check passed")
                return True
            else:
                logger.error(f"TradierEODCloser: Unexpected API response: {result}")
                return False
        except Exception as e:
            logger.error(f"TradierEODCloser: Health check failed: {e}")
            return False

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """
        Query Tradier sandbox for ALL open positions.

        Returns list of position dicts with symbol, quantity, cost_basis, etc.
        Handles Tradier's different response formats for 0, 1, or N positions.
        """
        result = self._api_request('GET', f'accounts/{self.account_id}/positions')
        positions_data = result.get('positions', {})

        if not positions_data or positions_data == 'null':
            return []

        position_list = positions_data.get('position', [])

        # Tradier wraps single position in dict, not list
        if isinstance(position_list, dict):
            position_list = [position_list]

        positions = []
        for pos in position_list:
            quantity = int(pos.get('quantity', 0))
            if quantity == 0:
                continue  # Skip zero-quantity positions

            positions.append({
                'symbol': pos.get('symbol', ''),
                'quantity': quantity,
                'cost_basis': float(pos.get('cost_basis', 0) or 0),
                'date_acquired': pos.get('date_acquired', ''),
                'id': pos.get('id', ''),
            })

        return positions

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get all open/pending orders from Tradier sandbox."""
        result = self._api_request('GET', f'accounts/{self.account_id}/orders')
        orders_data = result.get('orders', {})

        if not orders_data or orders_data == 'null':
            return []

        order_list = orders_data.get('order', [])
        if isinstance(order_list, dict):
            order_list = [order_list]

        open_orders = []
        for order in order_list:
            status = order.get('status', '')
            if status in ('open', 'pending', 'partially_filled'):
                open_orders.append({
                    'id': str(order.get('id', '')),
                    'symbol': order.get('symbol', ''),
                    'side': order.get('side', ''),
                    'quantity': int(order.get('quantity', 0)),
                    'type': order.get('type', ''),
                    'status': status,
                })

        return open_orders

    def cancel_all_open_orders(self) -> Dict[str, Any]:
        """
        Cancel all open/pending orders to prevent interference with close orders.

        Returns summary of cancellation results.
        """
        open_orders = self.get_open_orders()

        if not open_orders:
            logger.info("TradierEODCloser: No open orders to cancel")
            return {'cancelled': 0, 'failed': 0, 'orders': []}

        cancelled = 0
        failed = 0
        details = []

        for order in open_orders:
            order_id = order['id']
            try:
                result = self._api_request('DELETE', f'accounts/{self.account_id}/orders/{order_id}')
                logger.info(f"TradierEODCloser: Cancelled order {order_id} ({order['symbol']})")
                cancelled += 1
                details.append({'order_id': order_id, 'status': 'cancelled'})
            except Exception as e:
                logger.error(f"TradierEODCloser: Failed to cancel order {order_id}: {e}")
                failed += 1
                details.append({'order_id': order_id, 'status': 'failed', 'error': str(e)})

        logger.info(f"TradierEODCloser: Cancelled {cancelled} orders, {failed} failures")
        return {'cancelled': cancelled, 'failed': failed, 'orders': details}

    def _close_single_position(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """
        Close a single position with a MARKET order.

        Determines correct closing side based on position quantity:
        - Long (quantity > 0) → sell_to_close
        - Short (quantity < 0) → buy_to_close

        Returns result dict with order status.
        """
        symbol = position['symbol']
        quantity = position['quantity']

        if quantity > 0:
            side = 'sell_to_close'
            close_qty = quantity
        else:
            side = 'buy_to_close'
            close_qty = abs(quantity)

        # Determine if this is an option or equity
        # Options have OCC format: ROOT + 6-digit date + C/P + 8-digit strike
        is_option = len(symbol) > 10 and any(c in symbol for c in ('C', 'P'))

        order_data = {
            'class': 'option' if is_option else 'equity',
            'symbol': symbol[:6].rstrip('0123456789') if is_option else symbol,  # Extract underlying
            'side': side,
            'quantity': str(close_qty),
            'type': 'market',
            'duration': 'day',
        }

        if is_option:
            order_data['option_symbol'] = symbol

        logger.info(
            f"TradierEODCloser: Closing {symbol} — "
            f"{side} {close_qty} @ MARKET"
        )

        result = {
            'symbol': symbol,
            'quantity': quantity,
            'side': side,
            'order_id': None,
            'fill_status': 'not_sent',
            'error': None,
        }

        for attempt in range(MAX_CLOSE_RETRIES):
            try:
                response = self._api_request(
                    'POST',
                    f'accounts/{self.account_id}/orders',
                    data=order_data
                )

                order_info = response.get('order', {})
                order_id = order_info.get('id')
                order_status = order_info.get('status', 'unknown')

                if order_id:
                    result['order_id'] = str(order_id)
                    result['fill_status'] = order_status
                    logger.info(
                        f"TradierEODCloser: Order placed for {symbol} — "
                        f"ID: {order_id}, Status: {order_status}"
                    )

                    # Verify fill
                    if order_status != 'filled':
                        filled = self._wait_for_fill(str(order_id))
                        result['fill_status'] = 'filled' if filled else 'unfilled'

                    return result
                else:
                    # Check for error in response
                    errors = response.get('errors', {})
                    error_msg = errors.get('error', []) if isinstance(errors, dict) else str(errors)
                    result['error'] = str(error_msg) if error_msg else f"No order ID returned: {response}"
                    logger.warning(
                        f"TradierEODCloser: No order ID for {symbol} on attempt "
                        f"{attempt + 1}/{MAX_CLOSE_RETRIES}: {result['error']}"
                    )

            except Exception as e:
                result['error'] = str(e)
                logger.error(
                    f"TradierEODCloser: Close attempt {attempt + 1}/{MAX_CLOSE_RETRIES} "
                    f"failed for {symbol}: {e}"
                )

            if attempt < MAX_CLOSE_RETRIES - 1:
                delay = 2 ** (attempt + 1)  # 2s, 4s
                logger.info(f"TradierEODCloser: Retrying in {delay}s...")
                time.sleep(delay)

        result['fill_status'] = 'failed'
        logger.error(
            f"TradierEODCloser: CRITICAL — Failed to close {symbol} "
            f"after {MAX_CLOSE_RETRIES} attempts: {result['error']}"
        )
        return result

    def _wait_for_fill(self, order_id: str) -> bool:
        """
        Poll order status until filled or timeout.

        Returns True if filled, False otherwise.
        """
        elapsed = 0
        while elapsed < MAX_FILL_WAIT:
            time.sleep(FILL_POLL_INTERVAL)
            elapsed += FILL_POLL_INTERVAL

            try:
                result = self._api_request(
                    'GET',
                    f'accounts/{self.account_id}/orders/{order_id}'
                )

                order = result.get('order', {})
                status = order.get('status', 'unknown')

                logger.info(
                    f"TradierEODCloser: Order {order_id} status: {status} "
                    f"({elapsed}s / {MAX_FILL_WAIT}s)"
                )

                if status == 'filled':
                    return True
                elif status in ('canceled', 'rejected', 'expired'):
                    logger.warning(
                        f"TradierEODCloser: Order {order_id} is {status} — not fillable"
                    )
                    return False

            except Exception as e:
                logger.warning(f"TradierEODCloser: Fill check error: {e}")

        logger.warning(
            f"TradierEODCloser: Order {order_id} not filled after {MAX_FILL_WAIT}s"
        )
        return False

    def close_all_positions(self) -> Dict[str, Any]:
        """
        Close ALL positions in the Tradier sandbox account.

        This is the main entry point. Steps:
        1. Health check — verify API is reachable
        2. Cancel all open orders — prevent interference
        3. Query all positions — from actual Tradier account
        4. Send MARKET close orders for each position
        5. Verify fills
        6. Return comprehensive result

        Returns:
            Dict with full audit trail of what happened
        """
        now = datetime.now(CENTRAL_TZ)

        result = {
            'timestamp': now.isoformat(),
            'account_id': self.account_id,
            'sandbox': self.sandbox,
            'health_check': False,
            'orders_cancelled': 0,
            'positions_found': 0,
            'positions_closed': 0,
            'positions_failed': 0,
            'position_details': [],
            'errors': [],
        }

        logger.info(f"{'=' * 60}")
        logger.info(
            f"TradierEODCloser: Starting EOD close for account "
            f"{self.account_id} at {now.strftime('%I:%M:%S %p CT')}"
        )

        # Step 1: Health check
        if not self.health_check():
            result['errors'].append("API health check failed — cannot close positions")
            logger.error("TradierEODCloser: CRITICAL — API unreachable, positions may remain open!")
            return result

        result['health_check'] = True

        # Step 2: Cancel all open orders
        cancel_result = self.cancel_all_open_orders()
        result['orders_cancelled'] = cancel_result['cancelled']

        # Brief pause after cancellations to let them settle
        if cancel_result['cancelled'] > 0:
            time.sleep(1)

        # Step 3: Query all positions
        positions = self.get_all_positions()
        result['positions_found'] = len(positions)

        if not positions:
            logger.info("TradierEODCloser: No open positions found — account is flat")
            logger.info(f"{'=' * 60}")
            return result

        logger.info(f"TradierEODCloser: Found {len(positions)} position(s) to close:")
        for pos in positions:
            logger.info(f"  {pos['symbol']}: qty={pos['quantity']}")

        # Step 4: Close each position with MARKET orders
        for pos in positions:
            close_result = self._close_single_position(pos)
            result['position_details'].append(close_result)

            if close_result['fill_status'] in ('filled', 'open'):
                # 'open' means order was accepted; sandbox often fills market orders instantly
                result['positions_closed'] += 1
            else:
                result['positions_failed'] += 1
                result['errors'].append(
                    f"Failed to close {pos['symbol']}: {close_result.get('error', 'unknown')}"
                )

        # Step 5: Final verification — re-check account positions
        time.sleep(2)
        remaining = self.get_all_positions()
        if remaining:
            logger.error(
                f"TradierEODCloser: CRITICAL — {len(remaining)} position(s) "
                f"still open after close attempt!"
            )
            for pos in remaining:
                logger.error(f"  STILL OPEN: {pos['symbol']} qty={pos['quantity']}")
                result['errors'].append(f"STILL OPEN: {pos['symbol']} qty={pos['quantity']}")
        else:
            logger.info("TradierEODCloser: VERIFIED — All positions closed successfully")

        # Summary
        logger.info(
            f"TradierEODCloser: EOD close complete — "
            f"Found: {result['positions_found']}, "
            f"Closed: {result['positions_closed']}, "
            f"Failed: {result['positions_failed']}"
        )
        logger.info(f"{'=' * 60}")

        return result


def get_all_sandbox_accounts() -> List[Dict[str, str]]:
    """
    Get all configured Tradier sandbox accounts.

    Returns list of dicts with 'api_key', 'account_id', 'label'.
    Supports the primary sandbox plus any additional accounts.
    """
    accounts = []

    # Primary sandbox account
    try:
        from unified_config import APIConfig
        primary_key = APIConfig.TRADIER_SANDBOX_API_KEY or os.getenv('TRADIER_SANDBOX_API_KEY')
        primary_id = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or os.getenv('TRADIER_SANDBOX_ACCOUNT_ID')
    except ImportError:
        primary_key = os.getenv('TRADIER_SANDBOX_API_KEY')
        primary_id = os.getenv('TRADIER_SANDBOX_ACCOUNT_ID')

    if primary_key and primary_id:
        accounts.append({
            'api_key': primary_key,
            'account_id': primary_id,
            'label': 'primary',
        })

    # Second sandbox account (FORTRESS mirrors to this)
    second_key = os.getenv('TRADIER_SANDBOX_API_KEY_2')
    second_id = os.getenv('TRADIER_SANDBOX_ACCOUNT_ID_2')
    if second_key and second_id:
        accounts.append({
            'api_key': second_key,
            'account_id': second_id,
            'label': 'secondary',
        })

    # Third sandbox account
    third_key = os.getenv('TRADIER_SANDBOX_API_KEY_3')
    third_id = os.getenv('TRADIER_SANDBOX_ACCOUNT_ID_3')
    if third_key and third_id:
        accounts.append({
            'api_key': third_key,
            'account_id': third_id,
            'label': 'tertiary',
        })

    return accounts


def close_all_sandbox_accounts() -> Dict[str, Any]:
    """
    Close all positions across ALL configured Tradier sandbox accounts.

    This is the top-level function called by the scheduler.

    Returns combined results from all accounts.
    """
    accounts = get_all_sandbox_accounts()

    if not accounts:
        logger.warning("TradierEODCloser: No sandbox accounts configured")
        return {'accounts_processed': 0, 'error': 'No sandbox accounts configured'}

    logger.info(f"TradierEODCloser: Closing positions across {len(accounts)} sandbox account(s)")

    combined = {
        'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
        'accounts_processed': len(accounts),
        'total_positions_found': 0,
        'total_positions_closed': 0,
        'total_positions_failed': 0,
        'account_results': [],
    }

    for account in accounts:
        logger.info(f"TradierEODCloser: Processing account '{account['label']}' ({account['account_id']})")

        closer = TradierEODCloser(
            api_key=account['api_key'],
            account_id=account['account_id'],
            sandbox=True,
        )

        result = closer.close_all_positions()
        result['label'] = account['label']

        combined['total_positions_found'] += result['positions_found']
        combined['total_positions_closed'] += result['positions_closed']
        combined['total_positions_failed'] += result['positions_failed']
        combined['account_results'].append(result)

    logger.info(
        f"TradierEODCloser: All accounts processed — "
        f"Total found: {combined['total_positions_found']}, "
        f"Total closed: {combined['total_positions_closed']}, "
        f"Total failed: {combined['total_positions_failed']}"
    )

    return combined
