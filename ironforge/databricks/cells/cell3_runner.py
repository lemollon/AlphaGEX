# Cell 3: Run the scanner

# Reset sandbox cache so new keys/account IDs are picked up
_sandbox_accounts = None
_account_id_cache.clear()


# ---------------------------------------------------------------------------
#  Sandbox Orphan Cleanup
# ---------------------------------------------------------------------------


def _run_sandbox_orphan_cleanup() -> None:
    """Close stranded sandbox positions that weren't closed with the paper position.

    Run via: SCANNER_MODE=cleanup python ironforge_scanner.py
    Or call directly from a Databricks notebook cell.

    Queries each sandbox account for open option positions, then closes them
    with market orders.
    """
    print("=" * 60)
    print("  SANDBOX ORPHAN CLEANUP")
    print("=" * 60)

    accounts = _get_sandbox_accounts()
    if not accounts:
        print("  No sandbox accounts configured")
        return

    for acct in accounts:
        acct_id = _get_account_id_for_key(acct["api_key"])
        if not acct_id:
            print(f"  [{acct['name']}] SKIP — no account_id resolved")
            continue

        print(f"\n  [{acct['name']}] Account: {acct_id}")

        # Query open positions from Tradier sandbox
        data = _sandbox_get(f"/accounts/{acct_id}/positions", None, acct["api_key"])
        if not data:
            print(f"  [{acct['name']}] No position data returned")
            continue

        positions = data.get("positions", {})
        if positions == "null" or not positions:
            print(f"  [{acct['name']}] No open positions — clean")
            continue

        pos_list = positions.get("position", [])
        if isinstance(pos_list, dict):
            pos_list = [pos_list]

        if not pos_list:
            print(f"  [{acct['name']}] No open positions — clean")
            continue

        print(f"  [{acct['name']}] Found {len(pos_list)} open position(s):")
        for p in pos_list:
            symbol = p.get("symbol", "?")
            qty = p.get("quantity", 0)
            cost_basis = p.get("cost_basis", 0)
            print(f"    {symbol} qty={qty} cost_basis={cost_basis}")

        # Close each position with a market order
        for p in pos_list:
            symbol = p.get("symbol", "")
            qty = p.get("quantity", 0)
            if not symbol or qty == 0:
                continue

            # Determine close side: positive qty = long (sell_to_close),
            # negative qty = short (buy_to_close)
            if qty > 0:
                side = "sell_to_close"
                close_qty = qty
            else:
                side = "buy_to_close"
                close_qty = abs(qty)

            close_body = {
                "class": "option",
                "symbol": symbol.split(" ")[0] if " " in symbol else "SPY",
                "option_symbol": symbol,
                "side": side,
                "quantity": str(close_qty),
                "type": "market",
                "duration": "day",
            }

            result = _sandbox_post(
                f"/accounts/{acct_id}/orders", close_body, acct["api_key"],
            )
            order_id = result.get("order", {}).get("id") if result else None
            if order_id:
                print(f"    CLOSED: {symbol} {side} x{close_qty} → order_id={order_id}")
            else:
                print(f"    FAILED: {symbol} {side} x{close_qty} — check logs for HTTP error")

    print(f"\n{'=' * 60}")
    print("  Cleanup complete")
    print("=" * 60)


_pdt_tables_ready = False


def _ensure_pdt_tables() -> None:
    """Create shared ironforge_pdt_config and ironforge_pdt_log tables if they don't exist.

    Runs once per scanner process. Safe to call repeatedly.
    """
    global _pdt_tables_ready
    if _pdt_tables_ready:
        return
    try:
        pdt_config_tbl = shared_table('ironforge_pdt_config')
        pdt_log_tbl = shared_table('ironforge_pdt_log')

        db_execute(f"""
            CREATE TABLE IF NOT EXISTS {pdt_config_tbl} (
                bot_name STRING NOT NULL,
                pdt_enabled BOOLEAN,
                day_trade_count INT,
                max_day_trades INT,
                window_days INT,
                max_trades_per_day INT,
                last_reset_at TIMESTAMP,
                last_reset_by STRING,
                updated_at TIMESTAMP,
                created_at TIMESTAMP
            ) USING DELTA
        """)
        db_execute(f"""
            CREATE TABLE IF NOT EXISTS {pdt_log_tbl} (
                log_id STRING NOT NULL,
                bot_name STRING NOT NULL,
                action STRING NOT NULL,
                old_value STRING,
                new_value STRING,
                reason STRING,
                performed_by STRING,
                created_at TIMESTAMP
            ) USING DELTA
        """)

        # Seed PDT config for each bot if missing
        for bot in BOTS:
            bot_upper = bot["name"].upper()
            cfg = BOT_CONFIG.get(bot["name"], BOT_CONFIG["flame"])
            max_tpd = cfg["max_trades"]
            # INFERNO: no PDT enforcement, unlimited trades per day
            pdt_on = "FALSE" if bot["name"] == "inferno" else "TRUE"
            pdt_max = 0 if bot["name"] == "inferno" else 3  # 0 = disabled, 3 = broker-safe limit
            existing = db_query(f"""
                SELECT bot_name FROM {pdt_config_tbl}
                WHERE bot_name = '{bot_upper}' LIMIT 1
            """)
            if not existing:
                db_execute(f"""
                    INSERT INTO {pdt_config_tbl}
                        (bot_name, pdt_enabled, day_trade_count, max_day_trades,
                         window_days, max_trades_per_day, created_at, updated_at)
                    VALUES ('{bot_upper}', {pdt_on}, 0, {pdt_max}, 5, {max_tpd},
                            CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
                """)
                log.info(f"Seeded ironforge_pdt_config for {bot_upper} (pdt_enabled={pdt_on}, max_trades_per_day={max_tpd})")
        _pdt_tables_ready = True
        log.info("PDT tables verified/created (ironforge_pdt_config, ironforge_pdt_log)")
    except Exception as e:
        log.warning(f"PDT table auto-creation failed (non-fatal): {e}")


# ---------------------------------------------------------------------------
#  Pending Orders — Fill-Only Listener
# ---------------------------------------------------------------------------
# Instead of blocking 45s for a Tradier sandbox fill, we save a pending order
# and check for fills asynchronously on the next scan cycle.
#
# The listener ONLY looks for "filled" status. Rejected, canceled, expired
# orders are ignored — they sit in the table until the day ends, costing nothing.
# Orders from prior days are never checked (WHERE created_date = CURRENT_DATE()).
# ---------------------------------------------------------------------------


def _ensure_pending_orders_table() -> None:
    """Create {bot}_pending_orders table for each bot if it doesn't exist.

    Runs once per scanner process. Safe to call repeatedly.
    """
    global _pending_orders_table_ready
    if _pending_orders_table_ready:
        return
    try:
        for bot in BOTS:
            tbl = bot_table(bot["name"], "pending_orders")
            db_execute(f"""
                CREATE TABLE IF NOT EXISTS {tbl} (
                    pending_id STRING NOT NULL,
                    position_id STRING NOT NULL,
                    bot_name STRING NOT NULL,
                    dte_mode STRING NOT NULL,
                    order_type STRING NOT NULL,
                    sandbox_account STRING NOT NULL,
                    sandbox_api_key STRING,
                    sandbox_account_id STRING,
                    tradier_order_id BIGINT NOT NULL,
                    sandbox_contracts INT,
                    ticker STRING,
                    expiration STRING,
                    put_short DOUBLE,
                    put_long DOUBLE,
                    call_short DOUBLE,
                    call_long DOUBLE,
                    paper_contracts INT,
                    total_credit DOUBLE,
                    spread_width DOUBLE,
                    collateral_per DOUBLE,
                    max_profit DOUBLE,
                    max_loss DOUBLE,
                    spot_price DOUBLE,
                    vix DOUBLE,
                    expected_move DOUBLE,
                    advisor_json STRING,
                    sandbox_order_ids_json STRING,
                    status STRING NOT NULL,
                    fill_price DOUBLE,
                    resolved_at TIMESTAMP,
                    created_at TIMESTAMP,
                    created_date DATE
                ) USING DELTA
            """)
        _pending_orders_table_ready = True
        log.info("Pending orders tables verified/created")
    except Exception as e:
        log.warning(f"Pending orders table auto-creation failed (non-fatal): {e}")


def check_pending_fills(bot: dict) -> Optional[str]:
    """Check for filled pending orders and create paper positions.

    Runs every scan cycle BEFORE signal generation. Only looks for fills —
    rejected/canceled/expired orders are invisible to this function.

    Returns:
        "filled:{position_id}" if a pending order was filled and position created.
        None if no pending fills found (or no pending orders at all).
    """
    tbl = bot_table(bot["name"], "pending_orders")

    # Expire stale pending orders from prior days (market closed, options expired)
    try:
        db_execute(f"""
            UPDATE {tbl}
            SET status = 'expired', resolved_at = CURRENT_TIMESTAMP()
            WHERE status = 'pending'
              AND created_date < CURRENT_DATE()
        """)
    except Exception:
        pass  # Non-fatal — cleanup only

    try:
        pending_rows = db_query(f"""
            SELECT *
            FROM {tbl}
            WHERE status = 'pending'
              AND order_type = 'open'
              AND created_date = CURRENT_DATE()
              AND bot_name = '{bot["name"].upper()}'
              AND dte_mode = '{bot["dte"]}'
            ORDER BY created_at ASC
        """)
    except Exception as e:
        log.warning(f"{bot['name'].upper()} check_pending_fills query failed: {e}")
        return None

    if not pending_rows:
        return None

    for row in pending_rows:
        pending_id = row["pending_id"]
        tradier_order_id = to_int(row["tradier_order_id"])
        sandbox_api_key = row.get("sandbox_api_key", "")
        sandbox_account_id = row.get("sandbox_account_id", "")
        position_id = row["position_id"]

        if not sandbox_api_key or not sandbox_account_id or tradier_order_id <= 0:
            log.warning(
                f"Pending order {pending_id} has missing sandbox credentials, skipping"
            )
            continue

        # Query Tradier — single non-blocking call (no wait/retry)
        try:
            data = _sandbox_get(
                f"/accounts/{sandbox_account_id}/orders/{tradier_order_id}",
                None,
                sandbox_api_key,
            )
        except Exception as e:
            log.warning(f"Pending order {pending_id}: Tradier query failed: {e}")
            continue

        if not data:
            continue

        order = data.get("order", {})
        status = order.get("status", "")

        # Only care about fills. Everything else: ignore and check next cycle.
        if status != "filled":
            continue

        # ── ORDER FILLED — guard against duplicate position creation ──
        # If a prior cycle already created this position (but the pending UPDATE
        # failed), skip it to avoid duplicates.
        existing_pos = db_query(f"""
            SELECT position_id FROM {bot_table(bot['name'], 'positions')}
            WHERE position_id = '{position_id}' AND dte_mode = '{bot["dte"]}'
            LIMIT 1
        """)
        if existing_pos:
            log.info(
                f"Pending order {pending_id}: position {position_id} already exists, "
                f"marking as filled (recovery from partial update)"
            )
            try:
                db_execute(f"""
                    UPDATE {tbl}
                    SET status = 'filled', resolved_at = CURRENT_TIMESTAMP()
                    WHERE pending_id = '{pending_id}'
                """)
            except Exception:
                pass
            continue

        # ── Extract fill price ──
        fill_price = None
        avg_fill = order.get("avg_fill_price")
        if avg_fill is not None:
            fill_price = abs(float(avg_fill))
        else:
            # Fallback: calculate from leg fills
            legs = order.get("leg", [])
            if isinstance(legs, dict):
                legs = [legs]
            if legs:
                total = 0.0
                for leg in legs:
                    side = leg.get("side", "")
                    lfill = float(leg.get("avg_fill_price") or 0)
                    if "sell" in side:
                        total += lfill
                    else:
                        total -= lfill
                if total != 0:
                    fill_price = abs(total)

        if fill_price is None or fill_price <= 0:
            log.warning(
                f"Pending order {pending_id}: filled but no fill price extracted, skipping"
            )
            continue

        log.info(
            f"PENDING FILL DETECTED: {position_id} order_id={tradier_order_id} "
            f"fill=${fill_price:.4f}"
        )

        # ── Create the paper position ──
        try:
            _create_position_from_pending(bot, row, fill_price)
        except Exception as e:
            log.error(f"Failed to create position from pending fill {pending_id}: {e}")
            import traceback as _tb
            _tb.print_exc()
            continue

        # ── Mark pending order as resolved ──
        try:
            db_execute(f"""
                UPDATE {tbl}
                SET status = 'filled',
                    fill_price = {fill_price},
                    resolved_at = CURRENT_TIMESTAMP()
                WHERE pending_id = '{pending_id}'
            """)
        except Exception as e:
            log.warning(f"Failed to mark pending {pending_id} as filled: {e}")

        # ── Now place Matt/Logan orders (best-effort, non-blocking) ──
        try:
            _place_secondary_sandbox_orders(bot, row, position_id, fill_price)
        except Exception as e:
            log.warning(f"Secondary sandbox orders failed for {position_id}: {e}")

        return f"filled:{position_id}"

    return None


def _create_position_from_pending(
    bot: dict, pending_row: dict, fill_price: float
) -> None:
    """Create a paper position from a filled pending order.

    Inserts into {bot}_positions, updates paper_account, logs signal/trade/pdt/equity.
    """
    position_id = pending_row["position_id"]
    paper_contracts = to_int(pending_row["paper_contracts"])
    spread_width = num(pending_row["spread_width"])
    calculated_credit = num(pending_row["total_credit"])
    actual_credit = fill_price
    spot = num(pending_row["spot_price"])
    vix = num(pending_row["vix"])
    expected_move = num(pending_row["expected_move"])
    expiration = pending_row["expiration"]
    put_short = num(pending_row["put_short"])
    put_long = num(pending_row["put_long"])
    call_short = num(pending_row["call_short"])
    call_long = num(pending_row["call_long"])
    sandbox_contracts = to_int(pending_row.get("sandbox_contracts", 0))
    tradier_order_id = to_int(pending_row["tradier_order_id"])

    # Parse advisor JSON
    adv = {"confidence": 0, "winProbability": 0, "advice": "IC", "reasoning": "", "topFactors": []}
    try:
        adv_str = pending_row.get("advisor_json", "")
        if adv_str:
            adv = json.loads(adv_str)
    except (json.JSONDecodeError, TypeError):
        pass

    # Recalculate financials with actual fill price
    total_collateral = max(0, (spread_width - actual_credit) * 100) * paper_contracts
    max_profit = actual_credit * 100 * paper_contracts
    max_loss = total_collateral

    # Build sandbox_order_id JSON (User account info from the fill)
    sandbox_order_ids = {}
    try:
        existing_json = pending_row.get("sandbox_order_ids_json", "")
        if existing_json:
            sandbox_order_ids = json.loads(existing_json)
    except (json.JSONDecodeError, TypeError):
        pass
    # Update User entry with fill price
    sandbox_order_ids["User"] = {
        "order_id": tradier_order_id,
        "contracts": sandbox_contracts,
        "fill_price": fill_price,
    }
    sandbox_json = json.dumps(sandbox_order_ids).replace("'", "''")

    factors_json = json.dumps(adv.get("topFactors", [])).replace("'", "''")
    reasoning_escaped = str(adv.get("reasoning", "")).replace("'", "''")
    now_ts = get_central_time().strftime("%Y-%m-%d %H:%M:%S")
    today_date = get_central_time().strftime("%Y-%m-%d")

    # Get paper account ID
    acct_rows = db_query(f"""
        SELECT id FROM {bot_table(bot['name'], 'paper_account')}
        WHERE is_active = TRUE AND dte_mode = '{bot['dte']}'
        ORDER BY id DESC LIMIT 1
    """)
    if not acct_rows:
        raise RuntimeError(f"No paper account found for {bot['name']}")
    paper_acct_id = to_int(acct_rows[0]["id"])

    # INSERT position
    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'positions')} (
            position_id, ticker, expiration,
            put_short_strike, put_long_strike, put_credit,
            call_short_strike, call_long_strike, call_credit,
            contracts, spread_width, total_credit, max_loss, max_profit,
            collateral_required,
            underlying_at_entry, vix_at_entry, expected_move,
            call_wall, put_wall, gex_regime,
            flip_point, net_gex,
            oracle_confidence, oracle_win_probability, oracle_advice,
            oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
            wings_adjusted, original_put_width, original_call_width,
            put_order_id, call_order_id,
            status, open_time, open_date, dte_mode,
            sandbox_order_id, created_at, updated_at
        ) VALUES (
            '{position_id}', 'SPY', CAST('{expiration}' AS DATE),
            {put_short}, {put_long}, 0,
            {call_short}, {call_long}, 0,
            {paper_contracts}, {spread_width}, {actual_credit}, {max_loss}, {max_profit},
            {total_collateral},
            {spot}, {vix}, {expected_move},
            0, 0, 'UNKNOWN',
            0, 0,
            {adv['confidence']}, {adv['winProbability']}, '{adv['advice']}',
            '{reasoning_escaped}', '{factors_json}', FALSE,
            FALSE, {spread_width}, {spread_width},
            'PAPER', 'PAPER',
            'open', CAST('{now_ts}' AS TIMESTAMP), CAST('{today_date}' AS DATE), '{bot['dte']}',
            '{sandbox_json}', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
        )
    """)

    # UPDATE paper account (deduct collateral)
    db_execute(f"""
        UPDATE {bot_table(bot['name'], 'paper_account')}
        SET collateral_in_use = collateral_in_use + {total_collateral},
            buying_power = buying_power - {total_collateral},
            updated_at = CURRENT_TIMESTAMP()
        WHERE id = {paper_acct_id}
    """)

    # Log signal
    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'signals')} (
            signal_time, spot_price, vix, expected_move, call_wall, put_wall,
            gex_regime, put_short, put_long, call_short, call_long,
            total_credit, confidence, was_executed, reasoning,
            wings_adjusted, dte_mode
        ) VALUES (
            CURRENT_TIMESTAMP(), {spot}, {vix}, {expected_move}, 0, 0,
            'UNKNOWN', {put_short}, {put_long},
            {call_short}, {call_long},
            {actual_credit}, {adv['confidence']}, TRUE,
            'Async fill | {reasoning_escaped}',
            FALSE, '{bot['dte']}'
        )
    """)

    # Log trade open
    trade_details = json.dumps({
        "position_id": position_id,
        "contracts": paper_contracts,
        "credit": actual_credit,
        "calculated_credit": calculated_credit,
        "credit_source": "sandbox_fill_async",
        "collateral": total_collateral,
        "source": "pending_fill_listener",
        "sandbox_order_ids": sandbox_order_ids,
    }).replace("'", "''")
    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'logs')}
            (log_time, level, message, details, dte_mode)
        VALUES (
            CURRENT_TIMESTAMP(),
            'TRADE_OPEN',
            'ASYNC FILL: {position_id} {put_long}/{put_short}P-{call_short}/{call_long}C x{paper_contracts} @ ${actual_credit:.4f}',
            '{trade_details}',
            '{bot['dte']}'
        )
    """)

    # PDT log entry
    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'pdt_log')} (
            trade_date, symbol, position_id, opened_at,
            contracts, entry_credit, dte_mode, created_at
        ) VALUES (
            CURRENT_DATE(), 'SPY', '{position_id}', CURRENT_TIMESTAMP(),
            {paper_contracts}, {actual_credit}, '{bot['dte']}',
            CURRENT_TIMESTAMP()
        )
    """)

    # Equity snapshot
    updated_acct = db_query(f"""
        SELECT current_balance, cumulative_pnl
        FROM {bot_table(bot['name'], 'paper_account')}
        WHERE id = {paper_acct_id}
    """)
    bal = num(updated_acct[0]["current_balance"]) if updated_acct else 0
    cum_pnl = num(updated_acct[0]["cumulative_pnl"]) if updated_acct else 0
    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'equity_snapshots')}
            (snapshot_time, balance, realized_pnl, unrealized_pnl,
             open_positions, note, dte_mode, created_at)
        VALUES (
            CURRENT_TIMESTAMP(), {bal}, {cum_pnl}, 0,
            1, 'async_fill:{position_id}', '{bot['dte']}',
            CURRENT_TIMESTAMP()
        )
    """)

    # Daily perf
    db_execute(f"""
        MERGE INTO {bot_table(bot['name'], 'daily_perf')} AS t
        USING (SELECT CURRENT_DATE() AS trade_date) AS s
        ON t.trade_date = s.trade_date
        WHEN MATCHED THEN UPDATE SET
            trades_executed = t.trades_executed + 1,
            updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT
            (trade_date, trades_executed, positions_closed, realized_pnl, updated_at)
        VALUES (CURRENT_DATE(), 1, 0, 0, CURRENT_TIMESTAMP())
    """)

    log.info(
        f"{bot['name'].upper()} ASYNC FILL → POSITION CREATED: {position_id} "
        f"{put_long}/{put_short}P-{call_short}/{call_long}C "
        f"x{paper_contracts} @ ${actual_credit:.4f} (sandbox_fill)"
    )


def _place_secondary_sandbox_orders(
    bot: dict, pending_row: dict, position_id: str, user_fill_price: float
) -> None:
    """Place Matt/Logan sandbox orders (best-effort) after User fills.

    Non-blocking, non-fatal. Failures are logged but don't affect the paper position.
    Updates the position's sandbox_order_id JSON with secondary account info.
    """
    accounts = _get_sandbox_accounts_lazy()
    other_accounts = [a for a in accounts if a["name"] != "User"]
    if not other_accounts:
        return

    put_short = num(pending_row["put_short"])
    put_long = num(pending_row["put_long"])
    call_short = num(pending_row["call_short"])
    call_long = num(pending_row["call_long"])
    expiration = pending_row["expiration"]
    spread_width = num(pending_row["spread_width"])
    collateral_per = num(pending_row["collateral_per"])

    _occ_ps = build_occ_symbol("SPY", expiration, put_short, "P")
    _occ_pl = build_occ_symbol("SPY", expiration, put_long, "P")
    _occ_cs = build_occ_symbol("SPY", expiration, call_short, "C")
    _occ_cl = build_occ_symbol("SPY", expiration, call_long, "C")

    sandbox_order_ids = {}
    try:
        existing_json = pending_row.get("sandbox_order_ids_json", "")
        if existing_json:
            sandbox_order_ids = json.loads(existing_json)
    except (json.JSONDecodeError, TypeError):
        pass

    for acct in other_accounts:
        try:
            acct_id = _get_account_id_for_key(acct["api_key"])
            if not acct_id:
                continue

            acct_bp = _get_sandbox_buying_power(acct["api_key"], acct_id)
            if acct_bp is None or acct_bp < collateral_per:
                log.warning(
                    f"Sandbox [{acct['name']}]: BP=${acct_bp} insufficient "
                    f"(need ${collateral_per:.2f}/contract)"
                )
                continue

            acct_usable = acct_bp * 0.85
            acct_contracts = min(200, max(1, math.floor(acct_usable / collateral_per)))

            order_body = {
                "class": "multileg",
                "symbol": "SPY",
                "type": "market",
                "duration": "day",
                "option_symbol[0]": _occ_ps, "side[0]": "sell_to_open", "quantity[0]": str(acct_contracts),
                "option_symbol[1]": _occ_pl, "side[1]": "buy_to_open", "quantity[1]": str(acct_contracts),
                "option_symbol[2]": _occ_cs, "side[2]": "sell_to_open", "quantity[2]": str(acct_contracts),
                "option_symbol[3]": _occ_cl, "side[3]": "buy_to_open", "quantity[3]": str(acct_contracts),
                "tag": position_id[:255],
            }
            result = _sandbox_post(
                f"/accounts/{acct_id}/orders", order_body, acct["api_key"]
            )
            if result and result.get("order", {}).get("id"):
                oid = result["order"]["id"]
                sandbox_order_ids[acct["name"]] = {
                    "order_id": oid,
                    "contracts": acct_contracts,
                }
                log.info(
                    f"Sandbox IC OPEN OK [{acct['name']}]: "
                    f"order_id={oid} x{acct_contracts}"
                )
            else:
                log.warning(
                    f"Sandbox IC OPEN FAILED [{acct['name']}]: no order ID returned"
                )
        except Exception as e:
            log.warning(f"Sandbox order failed [{acct['name']}]: {e}")

    # Update position's sandbox_order_id with all account info
    if sandbox_order_ids:
        sandbox_json = json.dumps(sandbox_order_ids).replace("'", "''")
        try:
            db_execute(f"""
                UPDATE {bot_table(bot['name'], 'positions')}
                SET sandbox_order_id = '{sandbox_json}',
                    updated_at = CURRENT_TIMESTAMP()
                WHERE position_id = '{position_id}' AND dte_mode = '{bot["dte"]}'
            """)
        except Exception as e:
            log.warning(f"Failed to update sandbox_order_id for {position_id}: {e}")


def main() -> None:
    """Single scan — called by Databricks Job every 1 minute.

    In Job context (SCANNER_MODE=single), runs one scan cycle and exits.
    The Databricks Job scheduler handles the 1-minute repeat.

    In notebook context (SCANNER_MODE=loop), runs in an infinite loop
    with a 1-minute sleep between cycles.
    """
    try:
        # Ensure tables exist (auto-create if 01_setup_tables.sql hasn't been re-run)
        _ensure_pdt_tables()
        _ensure_pending_orders_table()

        ct = get_central_time()
        print(f"IronForge scan starting at {ct.strftime('%Y-%m-%d %H:%M:%S')} CT")
        print(f"  Catalog: {CATALOG} | Schema: {SCHEMA} | Tradier: {'OK' if is_tradier_configured() else 'MISSING'}")
        accounts = _get_sandbox_accounts_lazy()
        print(f"  Sandbox accounts: {len(accounts)}")
        for acct in accounts:
            acct_id = acct.get("account_id") or "auto-discover"
            print(f"    {acct['name']}: key={acct['api_key'][:6]}... account={acct_id}")
        log.info(
            f"IronForge scan starting at {ct.strftime('%Y-%m-%d %H:%M:%S')} CT "
            f"| Catalog: {CATALOG} | Schema: {SCHEMA} "
            f"| Tradier: {'OK' if is_tradier_configured() else 'MISSING'}"
        )
        log.warning(
            "GEX data source NOT configured — trading without gamma context. "
            "All GEX fields (call_wall, put_wall, gex_regime, flip_point, net_gex) "
            "are hardcoded to zero/UNKNOWN. Bots use SD-based strike selection only. "
            "To integrate real GEX data, connect to AlphaGEX API and populate these fields."
        )

        if not is_market_open(ct):
            if is_in_warmup_window(ct):
                # Pre-market warm-up: wait for 8:30 so the cluster stays alive
                from zoneinfo import ZoneInfo
                market_open = ct.replace(hour=8, minute=30, second=0, microsecond=0)
                wait_secs = max(0, (market_open - ct).total_seconds())
                print(f"  Pre-market warm-up — waiting {int(wait_secs)}s for market open")
                log.info(
                    f"Pre-market warm-up window ({ct.strftime('%H:%M')} CT) — "
                    f"cluster warm, waiting {int(wait_secs)}s for market open"
                )
                if wait_secs > 0:
                    time.sleep(wait_secs)
                # Re-check time after sleeping (should now be ~8:30)
                ct = get_central_time()
                print(f"  Warm-up complete — now {ct.strftime('%H:%M:%S')} CT")
                log.info(f"Warm-up complete — now {ct.strftime('%H:%M:%S')} CT, proceeding to scan")
            else:
                print(f"  Market closed ({ct.strftime('%H:%M')} CT) — exiting")
                log.info(
                    f"Market closed ({ct.strftime('%H:%M')} CT, "
                    f"{'weekend' if ct.weekday() >= 5 else 'outside 8:30-15:00'}) — exiting"
                )
                return

        print("  Running scan cycle...")
        run_scan_cycle()
        print("  Scan complete — exiting")
        log.info("Scan complete — exiting")

    except Exception as e:
        print(f"  MAIN ERROR: {e}")
        import traceback as tb
        tb.print_exc()


# Entry point: single-scan (Job) vs loop (notebook testing)
_scanner_mode = os.environ.get("SCANNER_MODE", "single")

if _scanner_mode == "loop":
    # Notebook testing mode — infinite loop with 5-min sleep
    print("Starting in LOOP mode (notebook testing)")
    while True:
        main()
        time.sleep(SCAN_INTERVAL)
elif _scanner_mode == "cleanup":
    # Orphan cleanup mode — close stranded sandbox positions
    _run_sandbox_orphan_cleanup()
else:
    # Job mode — single scan and exit
    main()
