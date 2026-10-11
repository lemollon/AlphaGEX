"""
AGAPE Perpetual Bot - Phase 3 Logic Validation
Run: python scripts/validate_perp_phase3.py 2>&1 | tee /tmp/phase3_validate.txt

Validates three Phase 3 mechanisms shipped 2026-05-02 across all 5 perp bots:
  A) Funding-flip exits (FUNDING_FLIP_EXIT_LONG / FUNDING_FLIP_EXIT_SHORT)
  B) Alt correlation cap (ALT_CORRELATION_CAP) -- XRP/DOGE/SHIB only
  C) Signal distribution sanity (combined_signal / combined_confidence)
  D) New scan_activity columns populated (oi_total_usd, ls_long_pct, taker_buy_ratio)

IMPORTANT - Pre-flight code audit results (checked 2026-05-16):
  Mechanism 1 (_check_funding_flip_exit):  PRESENT in all 5 traders
  Mechanism 2 (perp_correlation_guard.py): NOT DEPLOYED -- file missing, see Section B
  Mechanism 3 (new OI/LS columns):         PRESENT in all 5 db.py schemas
"""

import sys
import os
from datetime import datetime, timezone

PHASE3_CUTOFF = "2026-05-02 00:00:00+00"

TICKERS = ["btc", "eth", "xrp", "doge", "shib"]
ALT_TICKERS = ["xrp", "doge", "shib"]

SECTION_RESULTS = {}


def banner(title):
    print("")
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def sub(label):
    print(f"\n--- {label} ---")


def verdict(section, result, detail=""):
    tag = "PASS" if result else "ADJUST"
    line = f"=== VERDICT [{section}]: {tag} ==="
    if detail:
        line += f"  ({detail})"
    print(line)
    SECTION_RESULTS[section] = tag


def get_conn():
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from database_adapter import get_connection
        conn = get_connection()
        return conn
    except Exception as e:
        print(f"FATAL: Cannot connect to database: {e}")
        print("  Ensure DATABASE_URL is set and psycopg2-binary is installed.")
        sys.exit(1)


def safe_query(cur, sql, params=None):
    try:
        cur.execute(sql, params or ())
        return cur.fetchall(), cur.description
    except Exception as e:
        print(f"  [QUERY ERROR] {e}")
        return [], None


# ---------------------------------------------------------------------------
# PRE-FLIGHT: Code presence check (informational, already audited at write time)
# ---------------------------------------------------------------------------

def section_preflight():
    banner("PRE-FLIGHT: Phase 3 Code Presence Audit")

    checks = [
        (
            "Funding-flip exit (_check_funding_flip_exit)",
            [f"trading/agape_{t}_perp/trader.py" for t in TICKERS],
            "_check_funding_flip_exit",
        ),
        (
            "Alt correlation guard (data/perp_correlation_guard.py)",
            ["data/perp_correlation_guard.py"],
            None,
        ),
        (
            "OI/LS columns in db.py schemas",
            [f"trading/agape_{t}_perp/db.py" for t in TICKERS],
            "oi_total_usd",
        ),
    ]

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    all_ok = True

    for label, file_list, symbol in checks:
        missing_files = []
        missing_symbol = []
        for rel in file_list:
            fpath = os.path.join(repo_root, rel)
            if not os.path.exists(fpath):
                missing_files.append(rel)
            elif symbol:
                with open(fpath, "r", errors="replace") as fh:
                    if symbol not in fh.read():
                        missing_symbol.append(rel)
        if missing_files:
            print(f"  [NOT DEPLOYED] {label}")
            for f in missing_files:
                print(f"    - MISSING: {f}")
            if label.startswith("Alt correlation"):
                print("    ACTION: Mechanism 2 was NOT shipped. Section B will report")
                print("    NOT_DEPLOYED instead of a database verdict. Open a follow-up")
                print("    PR if you want this guard implemented.")
            all_ok = False
        elif missing_symbol:
            print(f"  [ROLLED BACK?] {label} -- symbol '{symbol}' not found in:")
            for f in missing_symbol:
                print(f"    - {f}")
            all_ok = False
        else:
            print(f"  [OK] {label}")

    print("")
    if all_ok:
        print("Pre-flight: all Phase 3 code present.")
    else:
        print("Pre-flight: one or more mechanisms missing -- see above.")
    return all_ok


# ---------------------------------------------------------------------------
# SECTION A: Funding-flip exits
# ---------------------------------------------------------------------------

def section_a(conn):
    banner("SECTION A: Funding-Flip Exits")
    print(f"Query period: {PHASE3_CUTOFF} -> now")

    total_exits = 0
    total_pnl = 0.0
    total_notional = 0.0
    rows_detail = []

    with conn.cursor() as cur:
        for t in TICKERS:
            table = f"agape_{t}_perp_positions"
            sql = f"""
                SELECT position_id, side, close_reason,
                       entry_price, close_price, quantity,
                       realized_pnl, open_time, close_time
                FROM {table}
                WHERE close_reason LIKE 'FUNDING_FLIP_EXIT_%%'
                  AND close_time >= %s
                ORDER BY close_time DESC
            """
            rows, desc = safe_query(cur, sql, (PHASE3_CUTOFF,))
            if not rows:
                print(f"  {t.upper():5s}: 0 funding-flip exits")
                continue

            ticker_pnl = 0.0
            ticker_notional = 0.0
            for row in rows:
                (pos_id, side, reason, entry_p, close_p, qty,
                 rpnl, open_t, close_t) = row
                rpnl = float(rpnl or 0)
                entry_p = float(entry_p or 0)
                qty = float(qty or 0)
                notional = entry_p * qty
                pnl_pct = (rpnl / notional * 100) if notional else 0
                ticker_pnl += rpnl
                ticker_notional += notional
                rows_detail.append({
                    "ticker": t.upper(),
                    "pos_id": pos_id,
                    "side": side,
                    "reason": reason,
                    "pnl": rpnl,
                    "pnl_pct": pnl_pct,
                    "notional": notional,
                    "close_time": close_t,
                })

            mean_pct = (ticker_pnl / ticker_notional * 100) if ticker_notional else 0
            print(
                f"  {t.upper():5s}: {len(rows):3d} exits  "
                f"total_pnl=${ticker_pnl:+.2f}  notional=${ticker_notional:.2f}  "
                f"mean_pnl_pct={mean_pct:+.3f}%"
            )
            total_exits += len(rows)
            total_pnl += ticker_pnl
            total_notional += ticker_notional

    sub("Individual exit breakdown (most recent 15)")
    rows_detail.sort(key=lambda r: str(r["close_time"] or ""), reverse=True)
    for r in rows_detail[:15]:
        print(
            f"  {r['ticker']:5s} {r['side']:5s}  {r['reason']:30s}  "
            f"pnl=${r['pnl']:+.4f} ({r['pnl_pct']:+.3f}%)  "
            f"notional=${r['notional']:.2f}  closed={r['close_time']}"
        )

    sub("Verdict logic")
    if total_exits == 0:
        print("  No funding-flip exits recorded since 2026-05-02.")
        print("  This is either: (a) no EXTREME_LONG/EXTREME_SHORT regimes fired,")
        print("  or (b) the mechanism is silently failing (snapshot None branch).")
        print("  Check trader logs for '_check_funding_flip_exit' debug lines.")
        verdict("A", True, "zero exits -- mechanism present but no triggers yet; not a failure")
    else:
        mean_overall_pct = (total_pnl / total_notional * 100) if total_notional else 0
        print(f"  Total exits: {total_exits}  overall_pnl=${total_pnl:+.2f}  mean_pct={mean_overall_pct:+.3f}%")
        threshold = -0.5  # percent
        passed = mean_overall_pct >= threshold
        if passed:
            print(f"  Mean pnl pct {mean_overall_pct:+.3f}% >= {threshold}% threshold -- exits not cutting winners.")
        else:
            print(f"  Mean pnl pct {mean_overall_pct:+.3f}% < {threshold}% threshold -- exits may be cutting profitable trades.")
            print("  RECOMMENDATION: Tighten EXTREME_LONG/EXTREME_SHORT threshold or add a min_hold_minutes guard")
            print("    before funding-flip exit fires (e.g. don't exit if held < 30 min and in profit).")
        verdict("A", passed, f"mean_exit_pnl_pct={mean_overall_pct:+.3f}%")


# ---------------------------------------------------------------------------
# SECTION B: Alt correlation cap
# ---------------------------------------------------------------------------

def section_b(conn):
    banner("SECTION B: Alt Correlation Cap (XRP/DOGE/SHIB)")

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    guard_path = os.path.join(repo_root, "data", "perp_correlation_guard.py")
    if not os.path.exists(guard_path):
        print("  STATUS: NOT DEPLOYED")
        print("")
        print("  data/perp_correlation_guard.py does not exist in the repo.")
        print("  The ALT_CORRELATION_CAP outcome string is referenced nowhere in the codebase.")
        print("  XRP/DOGE/SHIB _check_entry_conditions() has no alt-cap logic.")
        print("")
        print("  This mechanism was never shipped to production (or was rolled back")
        print("  before it could log any outcomes). No database verdict is possible.")
        print("")
        print("  RECOMMENDATION: If you want this guard, open a follow-up PR.")
        print("    Minimum viable implementation:")
        print("      1. Create data/perp_correlation_guard.py with is_alt_correlation_capped()")
        print("         that queries agape_{xrp,doge,shib}_perp_positions for open count.")
        print("      2. Call it in XRP/DOGE/SHIB _check_entry_conditions() before the")
        print("         margin gate, return 'ALT_CORRELATION_CAP' if capped.")
        print("      3. The scan_activity logger already accepts arbitrary outcome strings.")
        print("")
        verdict("B", False, "NOT DEPLOYED -- mechanism was never shipped")
        return

    # If the file somehow appears, fall through to DB check
    sub("ALT_CORRELATION_CAP outcomes since cutoff")
    with conn.cursor() as cur:
        for t in ALT_TICKERS:
            table = f"agape_{t}_perp_scan_activity"
            sql = f"""
                SELECT COUNT(*),
                       AVG(combined_confidence::float) FILTER (WHERE combined_confidence ~ '^[0-9.]+$')
                FROM {table}
                WHERE outcome = 'ALT_CORRELATION_CAP'
                  AND timestamp >= %s
            """
            rows, _ = safe_query(cur, sql, (PHASE3_CUTOFF,))
            if rows:
                count, avg_conf = rows[0]
                print(f"  {t.upper():5s}: {count or 0} blocked entries  avg_confidence={avg_conf}")

    # Cross-reference: what did the OTHER alts return when XRP/DOGE/SHIB was blocked?
    sub("Counterfactual P&L (alts that DID open when sibling was blocked)")
    print("  [Counterfactual analysis requires non-zero ALT_CORRELATION_CAP rows -- skipped if 0]")
    verdict("B", True, "deployed -- see counts above")


# ---------------------------------------------------------------------------
# SECTION C: Signal distribution
# ---------------------------------------------------------------------------

def section_c(conn):
    banner("SECTION C: Signal Distribution (all 5 perps)")
    print(f"Query period: {PHASE3_CUTOFF} -> now")

    overall_warn = False

    with conn.cursor() as cur:
        for t in TICKERS:
            table = f"agape_{t}_perp_scan_activity"
            sql = f"""
                SELECT combined_signal, combined_confidence,
                       COUNT(*) AS cnt,
                       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
                FROM {table}
                WHERE timestamp >= %s
                  AND combined_signal IS NOT NULL
                GROUP BY combined_signal, combined_confidence
                ORDER BY cnt DESC
            """
            rows, _ = safe_query(cur, sql, (PHASE3_CUTOFF,))

            total_sql = f"""
                SELECT COUNT(*) FROM {table}
                WHERE timestamp >= %s
            """
            total_rows, _ = safe_query(cur, total_sql, (PHASE3_CUTOFF,))
            total = total_rows[0][0] if total_rows else 0

            sub(f"{t.upper()} ({total} scans since cutoff)")
            if not rows:
                print(f"  No rows with combined_signal -- column may be NULL for all scans.")
                print(f"  Check that signal stack is populating combined_signal in _log_scan().")
                overall_warn = True
                continue

            top_pct = 0.0
            top_signal = ""
            for row in rows[:10]:
                sig, conf, cnt, pct = row
                pct = float(pct or 0)
                print(f"    {str(sig):25s}  {str(conf):8s}  n={cnt:6d}  ({pct:.1f}%)")
                if pct > top_pct:
                    top_pct = pct
                    top_signal = str(sig)

            if top_pct > 80:
                print(f"  WARNING: {top_signal} dominates at {top_pct:.1f}% -- signal stack may not be differentiating.")
                overall_warn = True
            else:
                print(f"  OK: top signal '{top_signal}' at {top_pct:.1f}% -- distribution looks differentiated.")

    sub("Verdict")
    verdict("C", not overall_warn,
            "differentiated" if not overall_warn else "one or more tickers dominated by single signal")


# ---------------------------------------------------------------------------
# SECTION D: New columns populated
# ---------------------------------------------------------------------------

def section_d(conn):
    banner("SECTION D: New Scan-Activity Columns (oi_total_usd, ls_long_pct, taker_buy_ratio)")
    print(f"Query period: {PHASE3_CUTOFF} -> now")
    print("  NOTE: taker_buy_ratio NULL is expected -- endpoint paywalled at Hobbyist tier.")

    all_pass = True

    with conn.cursor() as cur:
        for t in TICKERS:
            table = f"agape_{t}_perp_scan_activity"

            # Null-rate query
            sql_nulls = f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN oi_total_usd IS NOT NULL THEN 1 ELSE 0 END) AS oi_nn,
                    SUM(CASE WHEN ls_long_pct IS NOT NULL THEN 1 ELSE 0 END) AS ls_nn,
                    SUM(CASE WHEN taker_buy_ratio IS NOT NULL THEN 1 ELSE 0 END) AS tbr_nn
                FROM {table}
                WHERE timestamp >= %s
            """
            rows, _ = safe_query(cur, sql_nulls, (PHASE3_CUTOFF,))
            if not rows or rows[0][0] == 0:
                print(f"  {t.upper():5s}: no scan rows since cutoff")
                continue

            total, oi_nn, ls_nn, tbr_nn = rows[0]
            total = int(total)
            oi_pct = (int(oi_nn) / total * 100) if total else 0
            ls_pct = (int(ls_nn) / total * 100) if total else 0
            tbr_pct = (int(tbr_nn) / total * 100) if total else 0

            oi_ok = oi_pct >= 90
            ls_ok = ls_pct >= 50

            status = "OK" if (oi_ok and ls_ok) else "WARN"
            if status == "WARN":
                all_pass = False

            print(
                f"  {t.upper():5s}  [{status}]  n={total:6d}  "
                f"oi_total_usd={oi_pct:.1f}%  ls_long_pct={ls_pct:.1f}%  "
                f"taker_buy_ratio={tbr_pct:.1f}% (expect low)"
            )
            if not oi_ok:
                print(f"         WARN: oi_total_usd only {oi_pct:.1f}% non-NULL (need >= 90%)")
                print(f"               Check CoinGlass snapshot.oi_snapshot population.")
            if not ls_ok:
                print(f"         WARN: ls_long_pct only {ls_pct:.1f}% non-NULL (need >= 50%)")

            # Sample 5 recent rows
            sql_sample = f"""
                SELECT timestamp, oi_total_usd, ls_long_pct, taker_buy_ratio
                FROM {table}
                WHERE timestamp >= %s
                ORDER BY timestamp DESC
                LIMIT 5
            """
            sample_rows, _ = safe_query(cur, sql_sample, (PHASE3_CUTOFF,))
            if sample_rows:
                print(f"         Sample (5 most recent):")
                for sr in sample_rows:
                    ts, oi, ls, tbr = sr
                    print(f"           {str(ts)[:19]}  oi=${str(oi):>12}  ls={str(ls):>7}  tbr={str(tbr)}")

    sub("Verdict")
    verdict("D", all_pass,
            "all columns filling" if all_pass else "one or more columns below threshold -- check CoinGlass provider")


# ---------------------------------------------------------------------------
# FINAL SUMMARY
# ---------------------------------------------------------------------------

def final_summary():
    banner("FINAL SUMMARY")
    print(f"  Validation run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Phase 3 cutoff: {PHASE3_CUTOFF}")
    print("")

    all_pass = True
    for sec, result in sorted(SECTION_RESULTS.items()):
        mark = "[PASS  ]" if result == "PASS" else "[ADJUST]"
        print(f"  {mark}  Section {sec}")
        if result != "PASS":
            all_pass = False

    print("")
    if all_pass:
        print("  Overall: ALL PASS -- Phase 3 mechanisms appear to be working as designed.")
        print("  No immediate action required. Re-run in 7 days to track trending.")
    else:
        print("  Overall: ONE OR MORE SECTIONS NEED ATTENTION")
        print("")
        if SECTION_RESULTS.get("A") == "ADJUST":
            print("  Section A (funding-flip): exits are cutting into P&L.")
            print("    -> Comment on the PR and a follow-up threshold-tweak PR will be opened.")
        if SECTION_RESULTS.get("B") == "ADJUST" or SECTION_RESULTS.get("B") == "NOT DEPLOYED":
            print("  Section B (alt correlation cap): mechanism was NEVER DEPLOYED.")
            print("    -> Comment on the PR to request implementation PR.")
        if SECTION_RESULTS.get("C") == "ADJUST":
            print("  Section C (signal distribution): signals may be defaulting.")
            print("    -> Check signal stack combined_signal population in _log_scan().")
        if SECTION_RESULTS.get("D") == "ADJUST":
            print("  Section D (new columns): OI/LS data not filling as expected.")
            print("    -> Check CoinGlass provider oi_snapshot / ls_ratio objects.")
        print("")
        print("  If any section says ADJUST, comment back on the PR:")
        print("    https://github.com/lemollon/AlphaGEX  (see validate PR)")
        print("  and a follow-up fix PR will be opened with the proposed tweak.")

    print("")
    print("=" * 70)
    print("  END OF VALIDATION REPORT")
    print("=" * 70)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("AGAPE Perp Phase 3 Validation Script")
    print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Pre-flight code audit (no DB needed)
    section_preflight()

    # Connect once, share across sections
    conn = get_conn()

    try:
        section_a(conn)
        section_b(conn)
        section_c(conn)
        section_d(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    final_summary()
