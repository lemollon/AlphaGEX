"""Rotating daily engagement prompts for the EOD Discord brief.

Pulled into the evening market brief — one prompt per day, rotated
deterministically by day-of-year so the room sees variety but the choice
is reproducible (no DB lookup, no random seed).
"""

# Each item is (emoji, question). Keep questions punchy — Discord embeds
# truncate field values around 1024 chars and you want the question to
# stand out, not get buried.
ENGAGEMENT_PROMPTS = [
    ("🎯", "What's your highest-conviction setup for tomorrow? Drop your thesis below 👇"),
    ("🧭", "If you had to pick ONE catalyst this week, which one and why?"),
    ("⚖️", "Iron Condor or Double Diagonal for this week's range — defend your pick."),
    ("🎲", "What's the smallest size you'd open a NEW position at right now?"),
    ("🔥", "Last 5 trades — share your win rate, no judgment. Let's normalize transparency."),
    ("🚫", "Drop your favorite 'no-fly zone' — a setup you've sworn off forever and why."),
    ("📊", "Which expiry is winning your portfolio this month — 0DTE, weeklies, monthlies?"),
    ("🎤", "Hot take time: what does the room have wrong about the current tape?"),
    ("🛠️", "What's the ONE indicator you'd never trade without — and what does it tell you?"),
    ("🎵", "What's your trading playlist this week? Drop a track. 🎧"),
    ("📚", "Best book / video / podcast on options you've consumed this year?"),
    ("🪞", "Biggest mental mistake you made this week. Naming it kills its power."),
    ("🧨", "If SPY closes above [today_high+2] tomorrow, what does it confirm for you?"),
    ("⏳", "Roll, close, or let it ride — your stuck position needs a verdict. What's yours?"),
    ("🧊", "Which sector are you AVOIDING this week and why?"),
    ("🎯", "Drop your 80%-confidence price target for SPY by Friday close."),
    ("💬", "What question do you wish you could ask Powell at the next presser?"),
    ("🪙", "Coin flip: 0DTE Iron Condor on SPX or hold cash? Defend your call."),
    ("⚡", "What's the FASTEST you've ever closed a winner? Tell the story."),
    ("🌗", "Which trader on Twitter/YT actually moves your P&L (good or bad)?"),
    ("🔮", "Predict tomorrow's SPY range. Closest answer wins ETERNAL bragging rights."),
]


def get_daily_prompt(day_of_year: int) -> tuple[str, str]:
    """Return (emoji, question) for the given day-of-year (1-366)."""
    idx = (day_of_year - 1) % len(ENGAGEMENT_PROMPTS)
    return ENGAGEMENT_PROMPTS[idx]
