"""Per-event historical patterns and intelligence.

Maps known economic event names to:
- pre-event lean (typical drift direction into the print)
- reversal risk (probability the release flips the prevailing trend)
- historical avg move (1-line stat)
- emoji + short tag for embed display

These are based on widely-published post-2008 historical studies of
SPY reactions to scheduled US macro events. Numbers are approximate
averages — they describe TYPICAL behavior, not predictions.

Used by spreadworks/backend/__init__.py in the daily 30-day outlook.
"""

from typing import Optional


# ----------------------------------------------------------------------
# Pattern table — keyed by substring match against event["name"]
# ----------------------------------------------------------------------
# Order matters: most-specific first. First match wins.
_EVENT_PATTERNS = [
    # ===== FOMC RATE DECISION =====
    {
        "match": "FOMC Rate Decision",
        "lean": "Drift higher into print",
        "lean_emoji": "📈",
        "reversal": "HIGH",
        "avg_move": "±1.5% on release, ±2.5% on hawkish surprise",
        "playbook": (
            "Pre-Fed drift is well-documented (Cieslak/Vissing-Jorgensen 2019). "
            "Sell premium 2-3 days before, close pre-print. Skip overnight. "
            "Powell presser at 1:30 CT is where the real move happens, not the 1:00 release."
        ),
    },
    # ===== CPI =====
    {
        "match": "CPI Report",
        "lean": "Cautious / range-bound",
        "lean_emoji": "↔️",
        "reversal": "HIGH",
        "avg_move": "±1.2% avg, ±3% on >0.2% miss",
        "playbook": (
            "Single biggest market mover post-COVID. ATM straddle prices in ~1.5%, "
            "actual delivers ±1.2% mean. Skip new IC entries day-of. "
            "If positioned long vol pre-print, close in first 30 min — IV crushes fast."
        ),
    },
    # ===== NFP =====
    {
        "match": "Non-Farm Payrolls",
        "lean": "Vol expansion 7:30 CT",
        "lean_emoji": "💥",
        "reversal": "MEDIUM",
        "avg_move": "±0.8% avg, ±2% on >100k surprise",
        "playbook": (
            "First-Friday vol spike. Move usually fades by 10:00 CT (mean-revert). "
            "Strong-jobs print = bond-yield spike = growth-stock fade. "
            "Wage inflation matters more than headline jobs for Fed reaction."
        ),
    },
    # ===== PCE =====
    {
        "match": "PCE Price Index",
        "lean": "Light pre-print",
        "lean_emoji": "→",
        "reversal": "MEDIUM",
        "avg_move": "±0.6% avg, higher near FOMC",
        "playbook": (
            "Fed's preferred inflation gauge. Reaction is muted unless it diverges from CPI. "
            "PCE print 1-2 weeks before FOMC carries 2x the typical reaction."
        ),
    },
    # ===== PPI =====
    {
        "match": "PPI Report",
        "lean": "Light",
        "lean_emoji": "→",
        "reversal": "LOW",
        "avg_move": "±0.4%",
        "playbook": (
            "Wholesale inflation — usually already telegraphed by CPI a day earlier. "
            "Trade reaction to CPI, not to PPI."
        ),
    },
    # ===== GDP =====
    {
        "match": "GDP Q",
        "lean": "Light",
        "lean_emoji": "→",
        "reversal": "LOW",
        "avg_move": "±0.5% (advance), <±0.2% (prelim/final)",
        "playbook": (
            "Advance estimate moves the tape; preliminary and final rarely do — "
            "the market has already absorbed the data through monthly indicators."
        ),
    },
    # ===== Retail Sales =====
    {
        "match": "Retail Sales",
        "lean": "Light",
        "lean_emoji": "→",
        "reversal": "MEDIUM",
        "avg_move": "±0.6%, ±1.2% on big miss",
        "playbook": (
            "Consumer-spending bellwether. Holiday-season prints (Dec/Jan) "
            "carry 2x weight. Watch ex-autos for cleaner read."
        ),
    },
    # ===== JOLTS =====
    {
        "match": "JOLTS",
        "lean": "Light",
        "lean_emoji": "→",
        "reversal": "LOW",
        "avg_move": "±0.3%",
        "playbook": (
            "Labor-market gauge. Quits-rate is the leading indicator the Fed actually watches. "
            "Rarely a primary catalyst."
        ),
    },
    # ===== ISM Services =====
    {
        "match": "ISM Services PMI",
        "lean": "Light",
        "lean_emoji": "→",
        "reversal": "MEDIUM",
        "avg_move": "±0.5%, expansion/contraction crossover = bigger move",
        "playbook": (
            "Services = 70%+ of the US economy. Above-50 is expansion, below-50 is contraction. "
            "Crossover prints (49→51 or 51→49) double the typical reaction."
        ),
    },
    # ===== ISM Manufacturing =====
    {
        "match": "ISM Manufacturing PMI",
        "lean": "Light",
        "lean_emoji": "→",
        "reversal": "MEDIUM",
        "avg_move": "±0.5%, expansion/contraction crossover = bigger move",
        "playbook": (
            "Manufacturing = ~10% of GDP but high beta to industrials/materials sectors. "
            "Same crossover dynamic as Services PMI."
        ),
    },
    # ===== Earnings Season =====
    {
        "match": "Earnings Season Begins",
        "lean": "IV expansion all week",
        "lean_emoji": "📊",
        "reversal": "MEDIUM",
        "avg_move": "Single-stock ±5-10%, SPY ±0.8%",
        "playbook": (
            "Banks (JPM, GS, MS) set the tone. Wide bid-ask in single-name options — "
            "stick to indices unless you want the IV crush trade."
        ),
    },
    # ===== Big-tech earnings (FAAMG + TSLA + NVDA) — these single-name prints can move SPY =====
    {
        "match": "NVDA Earnings",
        "lean": "Vol expansion · room holds breath",
        "lean_emoji": "💥",
        "reversal": "HIGH",
        "avg_move": "NVDA ±8-10%, SPY ±0.5-1.5%",
        "playbook": (
            "The single biggest single-name SPY mover post-2023. Skip new SPY/SPX positions "
            "the afternoon of the print. AI-capex commentary on the call is what actually "
            "moves the tape, not the headline number."
        ),
    },
    {
        "match": "AAPL Earnings",
        "lean": "Range-bound pre-print",
        "lean_emoji": "↔️",
        "reversal": "MEDIUM",
        "avg_move": "AAPL ±4-6%, SPY ±0.3%",
        "playbook": (
            "iPhone units + China + services growth. Largest weight in QQQ/SPY by market cap, "
            "so a >5% AAPL move drags index materially. Watch services margin trend."
        ),
    },
    {
        "match": "MSFT Earnings",
        "lean": "Cautious pre-print",
        "lean_emoji": "↔️",
        "reversal": "MEDIUM",
        "avg_move": "MSFT ±5-7%, SPY ±0.3%",
        "playbook": (
            "Azure growth rate is the swing factor. Decel below ~28% YoY = sell-off; reaccel = "
            "rally. AI Copilot run-rate increasingly matters."
        ),
    },
    {
        "match": "GOOGL Earnings",
        "lean": "Range-bound pre-print",
        "lean_emoji": "↔️",
        "reversal": "MEDIUM",
        "avg_move": "GOOGL ±5-7%, SPY ±0.2%",
        "playbook": (
            "Search ad revenue + YouTube + cloud growth. AI competitive narrative drives "
            "post-print direction more than the numbers themselves."
        ),
    },
    {
        "match": "META Earnings",
        "lean": "Vol expansion",
        "lean_emoji": "💥",
        "reversal": "HIGH",
        "avg_move": "META ±8-12%, SPY ±0.3%",
        "playbook": (
            "Reality Labs losses + capex guide are the two levers. Capex guide that comes in "
            "above expectations = sell-off (dilutive); below = rally."
        ),
    },
    {
        "match": "AMZN Earnings",
        "lean": "Cautious pre-print",
        "lean_emoji": "↔️",
        "reversal": "MEDIUM",
        "avg_move": "AMZN ±5-8%, SPY ±0.3%",
        "playbook": (
            "AWS growth + retail operating margin. AWS deceleration triggers sharp sell-offs; "
            "retail margin expansion fuels rallies."
        ),
    },
    {
        "match": "TSLA Earnings",
        "lean": "Vol expansion",
        "lean_emoji": "💥",
        "reversal": "HIGH",
        "avg_move": "TSLA ±10-15%, SPY ±0.2%",
        "playbook": (
            "Most volatile single-name on the megacap list. Q2 deliveries pre-announced — "
            "focus shifts to gross margins + FSD/Robotaxi commentary."
        ),
    },
    {
        "match": "NFLX Earnings",
        "lean": "Range-bound pre-print",
        "lean_emoji": "↔️",
        "reversal": "MEDIUM",
        "avg_move": "NFLX ±6-10%, SPY ±0.1%",
        "playbook": (
            "First FAANG to report — sets sector tone. Subscriber net adds + ad-tier revenue "
            "are the primary swing factors."
        ),
    },
    {
        "match": "JPM Earnings",
        "lean": "Vol expansion",
        "lean_emoji": "💥",
        "reversal": "MEDIUM",
        "avg_move": "JPM ±3-5%, SPY ±0.3%",
        "playbook": (
            "Kicks off bank earnings + sets the financials sector tone for the week. "
            "NII guide + loan loss provisions drive the move. Watch IB fees recovery."
        ),
    },
    {
        "match": "GS Earnings",
        "lean": "Light",
        "lean_emoji": "→",
        "reversal": "LOW",
        "avg_move": "GS ±3-5%, SPY ±0.1%",
        "playbook": (
            "Trading + IB fees. Less broad market read than JPM, but tells you about "
            "capital-markets activity health."
        ),
    },
    {
        "match": "WMT Earnings",
        "lean": "Light",
        "lean_emoji": "→",
        "reversal": "LOW",
        "avg_move": "WMT ±3-5%, SPY ±0.1%",
        "playbook": (
            "Best read on low-end / value-conscious consumer. Comp sales + traffic split "
            "matters; trade-down from premium retailers shows up here first."
        ),
    },
]


def get_event_intel(event_name: str) -> Optional[dict]:
    """Return pattern dict for an event name, or None if no match."""
    if not event_name:
        return None
    for pat in _EVENT_PATTERNS:
        if pat["match"] in event_name:
            return pat
    return None


def reversal_emoji(level: str) -> str:
    """Map reversal-risk level to a single emoji."""
    return {
        "HIGH": "⚡",
        "MEDIUM": "⚠️",
        "LOW": "·",
    }.get(level, "·")


def short_tag(event_name: str) -> str:
    """Compact one-line tag for inline event display.

    Example: '📈 drift up · ⚡ HIGH reversal'
             '↔️ range-bound · ⚡ HIGH reversal'
             '→ light · · LOW reversal'
    """
    intel = get_event_intel(event_name)
    if not intel:
        return ""
    return (
        f"{intel['lean_emoji']} {intel['lean'].lower()} "
        f"· {reversal_emoji(intel['reversal'])} {intel['reversal']} reversal"
    )
