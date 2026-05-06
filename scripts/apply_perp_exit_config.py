#!/usr/bin/env python3
"""
APPLY PERP EXIT-RULE CONFIG

Writes one or more exit-rule rows to `autonomous_config` for a perp/futures
bot. Exactly the same semantics as `POST /api/admin/perp-exit-optimizer/apply`
but skips the HTTP layer so the operator doesn't need curl, JSON escaping, or
the RENDER_API_BASE URL — just a worker shell with DATABASE_URL.

Whitelisted keys (mirrors backend/api/routes/perp_exit_optimizer_routes.py):
  no_loss_activation_pct
  no_loss_trail_distance_pct
  no_loss_profit_target_pct
  max_unrealized_loss_pct
  no_loss_emergency_stop_pct
  max_hold_hours
  use_sar
  sar_trigger_pct
  sar_mfe_threshold_pct
  use_no_loss_trailing
  use_regime_aware_exits
  exit_profile_chop_json
  exit_profile_trend_json

Bot labels (case-insensitive):
  BTC, ETH, SOL, AVAX, XRP, DOGE
  SHIB              -> AGAPE_SHIB_FUTURES (the active 1000SHIB-FUT bot;
                       the legacy SHIB perp is retired)
  SHIB_PERP         -> AGAPE_SHIB_PERP (retired; explicit if you really want it)
  LINK, LTC, BCH    -> AGAPE_<X>_FUTURES

Usage:
    # Apply BTC chop-tightening from the regime-aware backtest grid
    python scripts/apply_perp_exit_config.py BTC \\
        no_loss_activation_pct=0.2 \\
        no_loss_trail_distance_pct=0.25 \\
        no_loss_profit_target_pct=1.0 \\
        max_unrealized_loss_pct=1.5 \\
        max_hold_hours=6

    # Flip the regime-aware feature flag for one bot (and stamp profile JSON)
    python scripts/apply_perp_exit_config.py SOL \\
        use_regime_aware_exits=true \\
        'exit_profile_chop_json={"activation_pct":0.3,...}'

    # Dry-run: show the upserts without writing
    python scripts/apply_perp_exit_config.py BTC max_hold_hours=6 --dry-run
"""

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Bot label -> autonomous_config key prefix.
# Keep in sync with _BOT_KEY_PREFIX in backend/api/routes/perp_exit_optimizer_routes.py.
_PREFIX = {
    "BTC":           "agape_btc_perp_",
    "ETH":           "agape_eth_perp_",
    "SOL":           "agape_sol_perp_",
    "AVAX":          "agape_avax_perp_",
    "XRP":           "agape_xrp_perp_",
    "DOGE":          "agape_doge_perp_",
    # SHIB bare label routes to the active futures bot, NOT retired SHIB-PERP.
    "SHIB":          "agape_shib_futures_",
    "SHIB_FUTURES":  "agape_shib_futures_",
    "SHIB_PERP":     "agape_shib_perp_",        # retired; explicit only
    "LINK":          "agape_link_futures_",
    "LINK_FUTURES":  "agape_link_futures_",
    "LTC":           "agape_ltc_futures_",
    "LTC_FUTURES":   "agape_ltc_futures_",
    "BCH":           "agape_bch_futures_",
    "BCH_FUTURES":   "agape_bch_futures_",
}

# Mirror of _ALLOWED_KEYS in backend/api/routes/perp_exit_optimizer_routes.py.
_ALLOWED_KEYS = {
    "no_loss_activation_pct",
    "no_loss_trail_distance_pct",
    "no_loss_profit_target_pct",
    "max_unrealized_loss_pct",
    "no_loss_emergency_stop_pct",
    "max_hold_hours",
    "use_sar",
    "sar_trigger_pct",
    "sar_mfe_threshold_pct",
    "use_no_loss_trailing",
    "use_regime_aware_exits",
    "exit_profile_chop_json",
    "exit_profile_trend_json",
}


def _parse_kv(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise SystemExit(f"bad arg '{raw}' — expected key=value")
    k, v = raw.split("=", 1)
    return k.strip(), v.strip()


def _resolve_bot(label: str) -> tuple[str, str]:
    s = label.upper()
    if s in _PREFIX:
        return s, _PREFIX[s]
    raise SystemExit(
        f"unknown bot '{label}'.\n"
        f"  Bare tickers: {', '.join(k for k in _PREFIX if '_' not in k)}\n"
        f"  Suffixed:     {', '.join(k for k in _PREFIX if '_' in k)}"
    )


def _validate_keys(items: dict[str, str]) -> None:
    bad = [k for k in items if k not in _ALLOWED_KEYS]
    if bad:
        raise SystemExit(
            f"keys not in whitelist: {bad}\n"
            f"allowed: {sorted(_ALLOWED_KEYS)}"
        )


def _get_connection():
    try:
        from database_adapter import get_connection as _get
        conn = _get()
    except Exception as e:
        raise SystemExit(f"db connect failed: {e}")
    if conn is None:
        raise SystemExit("db connect returned None — DATABASE_URL likely unset")
    return conn


def _read_existing(cursor, prefix: str) -> dict[str, str]:
    cursor.execute(
        "SELECT key, value FROM autonomous_config WHERE key LIKE %s ORDER BY key",
        (f"{prefix}%",),
    )
    return {r[0]: r[1] for r in cursor.fetchall()}


def _upsert(cursor, full_key: str, value: str) -> None:
    cursor.execute(
        """
        INSERT INTO autonomous_config (key, value)
        VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
        (full_key, value),
    )


def main():
    p = argparse.ArgumentParser(
        description=__doc__.strip().split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("bot", help="bot label, e.g. BTC, SOL, SHIB, LINK_FUTURES")
    p.add_argument("kv", nargs="+", metavar="key=value",
                   help="one or more whitelist key=value pairs")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would change without writing")
    args = p.parse_args()

    bot_label, prefix = _resolve_bot(args.bot)
    items = dict(_parse_kv(s) for s in args.kv)
    _validate_keys(items)

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        existing = _read_existing(cursor, prefix)

        ts = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d %H:%M:%S CT")
        print(f"[{ts}] target: {bot_label}  (prefix={prefix})")
        print(f"  whitelist passed: {len(items)} keys")

        diff_lines = []
        for k, v in items.items():
            full_key = f"{prefix}{k}"
            old = existing.get(full_key)
            if old == v:
                diff_lines.append(f"  {k:<32} = {v}  (unchanged)")
            elif old is None:
                diff_lines.append(f"  {k:<32} = {v}  (NEW)")
            else:
                diff_lines.append(f"  {k:<32} = {v}  (was: {old})")
        for line in diff_lines:
            print(line)

        if args.dry_run:
            print("\n[dry-run] no changes written.")
            return

        for k, v in items.items():
            _upsert(cursor, f"{prefix}{k}", v)
        conn.commit()
        cursor.close()
        print(f"\nApplied {len(items)} key(s). Restart alphagex-trader (auto-deploy")
        print("on the next push handles this; otherwise click Restart on Render).")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
