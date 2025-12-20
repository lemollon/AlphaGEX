"""
Daily Manna API routes - Economic news with faith-based devotionals.

Fetches REAL financial/economic news headlines and uses Claude AI to create
Bible studies and morning prayers that connect current events to scripture.
"""

import os
import json
import hashlib
import feedparser
import requests
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/daily-manna", tags=["Daily Manna"])

# Cache for daily content (one generation per day)
_daily_cache: Dict[str, Any] = {}
_cache_date: Optional[date] = None

# News cache (refresh every 2 hours)
_news_cache: List[Dict[str, Any]] = []
_news_cache_time: Optional[datetime] = None
NEWS_CACHE_MINUTES = 120


def get_cache_key() -> str:
    """Generate cache key for today's content."""
    return datetime.now().strftime("%Y-%m-%d")


def get_cached_content() -> Optional[Dict[str, Any]]:
    """Get cached content if it's from today."""
    global _daily_cache, _cache_date
    today = date.today()
    if _cache_date == today and _daily_cache:
        return _daily_cache
    return None


def set_cached_content(content: Dict[str, Any]) -> None:
    """Cache content for today."""
    global _daily_cache, _cache_date
    _daily_cache = content
    _cache_date = date.today()


def get_daily_scriptures() -> List[Dict[str, str]]:
    """
    Get a rotating set of scriptures for economic/provision themes.
    Returns different verses based on day of year.
    """
    scriptures = [
        {
            "reference": "Philippians 4:19",
            "text": "And my God will meet all your needs according to the riches of his glory in Christ Jesus.",
            "theme": "God's Provision"
        },
        {
            "reference": "Proverbs 3:9-10",
            "text": "Honor the Lord with your wealth, with the firstfruits of all your crops; then your barns will be filled to overflowing.",
            "theme": "Honoring God with Wealth"
        },
        {
            "reference": "Matthew 6:33",
            "text": "But seek first his kingdom and his righteousness, and all these things will be given to you as well.",
            "theme": "Kingdom Priorities"
        },
        {
            "reference": "Deuteronomy 8:18",
            "text": "But remember the Lord your God, for it is he who gives you the ability to produce wealth.",
            "theme": "Source of Prosperity"
        },
        {
            "reference": "Proverbs 21:5",
            "text": "The plans of the diligent lead to profit as surely as haste leads to poverty.",
            "theme": "Diligent Planning"
        },
        {
            "reference": "Ecclesiastes 11:2",
            "text": "Invest in seven ventures, yes, in eight; you do not know what disaster may come upon the land.",
            "theme": "Diversification"
        },
        {
            "reference": "Luke 16:10",
            "text": "Whoever can be trusted with very little can also be trusted with much.",
            "theme": "Faithful Stewardship"
        },
        {
            "reference": "Proverbs 22:7",
            "text": "The rich rule over the poor, and the borrower is slave to the lender.",
            "theme": "Wisdom with Debt"
        },
        {
            "reference": "1 Timothy 6:10",
            "text": "For the love of money is a root of all kinds of evil.",
            "theme": "Heart Posture"
        },
        {
            "reference": "Malachi 3:10",
            "text": "Bring the whole tithe into the storehouse... and see if I will not throw open the floodgates of heaven.",
            "theme": "Generosity"
        },
        {
            "reference": "Proverbs 13:11",
            "text": "Dishonest money dwindles away, but whoever gathers money little by little makes it grow.",
            "theme": "Patient Accumulation"
        },
        {
            "reference": "Matthew 25:21",
            "text": "Well done, good and faithful servant! You have been faithful with a few things; I will put you in charge of many things.",
            "theme": "Faithful Investment"
        },
        {
            "reference": "James 1:5",
            "text": "If any of you lacks wisdom, you should ask God, who gives generously to all without finding fault.",
            "theme": "Divine Wisdom"
        },
        {
            "reference": "Psalm 37:25",
            "text": "I was young and now I am old, yet I have never seen the righteous forsaken or their children begging bread.",
            "theme": "God's Faithfulness"
        },
        {
            "reference": "Proverbs 11:24-25",
            "text": "One person gives freely, yet gains even more; another withholds unduly, but comes to poverty. A generous person will prosper.",
            "theme": "Generous Living"
        },
        {
            "reference": "Romans 13:8",
            "text": "Let no debt remain outstanding, except the continuing debt to love one another.",
            "theme": "Financial Freedom"
        },
        {
            "reference": "Hebrews 13:5",
            "text": "Keep your lives free from the love of money and be content with what you have, because God has said, 'Never will I leave you; never will I forsake you.'",
            "theme": "Contentment"
        },
        {
            "reference": "Proverbs 27:23-24",
            "text": "Be sure you know the condition of your flocks, give careful attention to your herds; for riches do not endure forever.",
            "theme": "Diligent Oversight"
        },
        {
            "reference": "2 Corinthians 9:8",
            "text": "And God is able to bless you abundantly, so that in all things at all times, having all that you need, you will abound in every good work.",
            "theme": "Abundant Blessing"
        },
        {
            "reference": "Matthew 6:19-21",
            "text": "Do not store up for yourselves treasures on earth... But store up for yourselves treasures in heaven... For where your treasure is, there your heart will be also.",
            "theme": "Eternal Perspective"
        },
    ]

    # Rotate based on day of year
    day_of_year = datetime.now().timetuple().tm_yday
    index = day_of_year % len(scriptures)

    # Return today's scripture plus two related ones
    return [
        scriptures[index],
        scriptures[(index + 7) % len(scriptures)],
        scriptures[(index + 13) % len(scriptures)],
    ]


def fetch_rss_news(feed_url: str, source_name: str, max_items: int = 5) -> List[Dict[str, Any]]:
    """Fetch news from an RSS feed."""
    news_items = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:max_items]:
            # Get publication date
            pub_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6]).isoformat()
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_date = datetime(*entry.updated_parsed[:6]).isoformat()
            else:
                pub_date = datetime.now().isoformat()

            # Clean up summary
            summary = ""
            if hasattr(entry, 'summary'):
                summary = entry.summary
                # Remove HTML tags
                import re
                summary = re.sub(r'<[^>]+>', '', summary)
                # Truncate if too long
                if len(summary) > 300:
                    summary = summary[:297] + "..."

            news_items.append({
                "headline": entry.title,
                "summary": summary,
                "source": source_name,
                "url": entry.link if hasattr(entry, 'link') else None,
                "timestamp": pub_date,
                "category": "Financial News"
            })
    except Exception as e:
        print(f"Error fetching RSS from {source_name}: {e}")

    return news_items


def fetch_economic_news() -> List[Dict[str, Any]]:
    """
    Fetch today's REAL economic/financial news headlines from multiple sources.
    Uses RSS feeds from major financial news outlets.
    """
    global _news_cache, _news_cache_time

    # Check cache first (refresh every 2 hours)
    if _news_cache and _news_cache_time:
        cache_age = (datetime.now() - _news_cache_time).total_seconds() / 60
        if cache_age < NEWS_CACHE_MINUTES:
            return _news_cache

    all_news = []

    # Financial news RSS feeds (free, no API key required)
    rss_feeds = [
        # Major financial news
        ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US", "Yahoo Finance"),
        ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC"),
        ("https://feeds.marketwatch.com/marketwatch/topstories/", "MarketWatch"),
        ("https://feeds.bloomberg.com/markets/news.rss", "Bloomberg"),
        # Economic/Fed focused
        ("https://www.federalreserve.gov/feeds/press_all.xml", "Federal Reserve"),
        ("https://feeds.reuters.com/reuters/businessNews", "Reuters"),
    ]

    for feed_url, source_name in rss_feeds:
        try:
            items = fetch_rss_news(feed_url, source_name, max_items=3)
            all_news.extend(items)
        except Exception as e:
            print(f"Failed to fetch from {source_name}: {e}")
            continue

    # If RSS feeds fail, try Alpha Vantage News API (if key available)
    if not all_news:
        alpha_vantage_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if alpha_vantage_key:
            try:
                url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&topics=economy_fiscal,economy_monetary,finance&apikey={alpha_vantage_key}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get('feed', [])[:10]:
                        all_news.append({
                            "headline": item.get('title', ''),
                            "summary": item.get('summary', '')[:300],
                            "source": item.get('source', 'Alpha Vantage'),
                            "url": item.get('url'),
                            "timestamp": item.get('time_published', datetime.now().isoformat()),
                            "category": "Financial News"
                        })
            except Exception as e:
                print(f"Alpha Vantage news fetch failed: {e}")

    # Deduplicate by headline similarity
    seen_headlines = set()
    unique_news = []
    for item in all_news:
        # Create a simplified key from headline
        headline_key = item['headline'].lower()[:50]
        if headline_key not in seen_headlines:
            seen_headlines.add(headline_key)
            unique_news.append(item)

    # Sort by timestamp (newest first) and limit
    unique_news.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    unique_news = unique_news[:8]  # Top 8 headlines

    # Add category/impact classification based on keywords
    for item in unique_news:
        headline_lower = item['headline'].lower()

        # Categorize
        if any(word in headline_lower for word in ['fed', 'federal reserve', 'rate', 'inflation', 'cpi', 'pce']):
            item['category'] = 'Federal Reserve & Monetary Policy'
            item['impact'] = 'high'
        elif any(word in headline_lower for word in ['jobs', 'employment', 'unemployment', 'labor', 'payroll']):
            item['category'] = 'Employment & Labor'
            item['impact'] = 'high'
        elif any(word in headline_lower for word in ['gdp', 'economy', 'recession', 'growth']):
            item['category'] = 'Economic Growth'
            item['impact'] = 'high'
        elif any(word in headline_lower for word in ['earnings', 'profit', 'revenue', 'quarterly']):
            item['category'] = 'Corporate Earnings'
            item['impact'] = 'medium'
        elif any(word in headline_lower for word in ['oil', 'energy', 'gas', 'opec']):
            item['category'] = 'Energy & Commodities'
            item['impact'] = 'medium'
        elif any(word in headline_lower for word in ['tech', 'ai', 'nvidia', 'apple', 'microsoft', 'google']):
            item['category'] = 'Technology'
            item['impact'] = 'medium'
        elif any(word in headline_lower for word in ['bank', 'credit', 'lending', 'mortgage']):
            item['category'] = 'Banking & Finance'
            item['impact'] = 'medium'
        elif any(word in headline_lower for word in ['china', 'tariff', 'trade', 'global']):
            item['category'] = 'Global Trade'
            item['impact'] = 'medium'
        elif any(word in headline_lower for word in ['s&p', 'dow', 'nasdaq', 'market', 'stocks', 'rally', 'drop']):
            item['category'] = 'Market Movement'
            item['impact'] = 'medium'
        else:
            item['category'] = 'Financial News'
            item['impact'] = 'low'

    # Cache the results
    if unique_news:
        _news_cache = unique_news
        _news_cache_time = datetime.now()

    # Fallback if no news fetched
    if not unique_news:
        unique_news = [{
            "headline": "Markets Active - Check Major Financial News Sources",
            "summary": "Unable to fetch live news. Please check CNBC, Bloomberg, or Reuters for the latest financial headlines.",
            "source": "System",
            "category": "Notice",
            "timestamp": datetime.now().isoformat(),
            "impact": "low"
        }]

    return unique_news


async def generate_devotional_with_claude(
    news_items: List[Dict[str, Any]],
    scriptures: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Use Claude AI to generate a Bible study and morning prayer
    based on today's REAL economic/financial news and selected scriptures.
    """
    try:
        import anthropic

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return {
                "bible_study": "API key not configured. Please set ANTHROPIC_API_KEY.",
                "morning_prayer": "Lord, guide our steps today as we navigate the markets with wisdom and integrity. Amen.",
                "reflection_questions": ["How can I honor God with my financial decisions today?"],
                "key_insight": "Trust in the Lord with all your heart.",
                "theme": "Divine Guidance"
            }

        # Build context from REAL news headlines
        news_summary = "\n".join([
            f"- [{item.get('category', 'News')}] {item['headline']}"
            + (f"\n  Summary: {item['summary'][:200]}..." if item.get('summary') else "")
            + (f"\n  Source: {item.get('source', 'Unknown')}" if item.get('source') else "")
            for item in news_items[:6]
        ])

        scripture_text = "\n".join([
            f"- {s['reference']}: \"{s['text']}\" (Theme: {s['theme']})"
            for s in scriptures
        ])

        today = datetime.now().strftime("%A, %B %d, %Y")

        prompt = f"""You are a wise Christian financial advisor and pastor who helps believers integrate their faith with understanding of economic events and financial markets. Today is {today}.

TODAY'S TOP FINANCIAL/ECONOMIC NEWS HEADLINES:
{news_summary}

TODAY'S SCRIPTURES FOR REFLECTION:
{scripture_text}

Please create a "Daily Manna" devotional that helps believers understand current economic events through the lens of faith:

1. **Bible Study** (3-4 paragraphs):
   - Connect today's specific news headlines to the scriptures
   - Help readers understand what these economic events might mean for their lives
   - Draw spiritual lessons from the news (e.g., if Fed raises rates, discuss patience and God's timing; if job losses are reported, discuss God's provision)
   - Reference the SPECIFIC headlines when making connections
   - Be practical and encouraging, not preachy

2. **Morning Prayer** (1 paragraph):
   - Write a sincere prayer that acknowledges the current economic realities in the news
   - Ask for wisdom to navigate these specific circumstances
   - Include protection from fear and greed
   - Make it personal and heartfelt, referencing the day's economic themes

3. **Reflection Questions** (3 questions):
   - Thoughtful questions that help readers apply faith to the current economic environment
   - Connect to the specific news of the day

4. **Key Insight** (1-2 sentences):
   - A practical takeaway that bridges today's specific news to faith principles

Format your response as JSON with these keys:
- bible_study: The Bible study text (can use markdown for formatting)
- morning_prayer: The prayer text
- reflection_questions: Array of 3 questions
- key_insight: The practical takeaway
- theme: A 2-4 word theme for today's devotional based on the dominant news theme"""

        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text if message.content else "{}"

        # Parse JSON response
        try:
            # Find JSON in response (might be wrapped in markdown code blocks)
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_match = response_text.split("```")[1].split("```")[0]

            devotional = json.loads(json_match.strip())
            return devotional
        except json.JSONDecodeError:
            # If JSON parsing fails, extract content manually
            return {
                "bible_study": response_text,
                "morning_prayer": "Lord, grant us wisdom and discernment as we process today's economic news. Help us to trust in Your provision regardless of market conditions. Amen.",
                "reflection_questions": [
                    "How can I maintain peace when economic news creates uncertainty?",
                    "What is God teaching me through today's financial headlines?",
                    "How can I be a blessing to others during these economic times?"
                ],
                "key_insight": "God's economy operates on different principles than Wall Street's.",
                "theme": "Trusting God's Economy"
            }

    except Exception as e:
        return {
            "bible_study": f"Unable to generate devotional content. Error: {str(e)}",
            "morning_prayer": "Heavenly Father, even when we cannot access the news, Your wisdom remains. Guide our steps today. Amen.",
            "reflection_questions": [
                "How can I find peace in uncertain economic times?",
                "What does faithfulness look like in my financial life?",
                "How can I be a blessing to others through my resources?"
            ],
            "key_insight": "God's provision is not dependent on economic conditions.",
            "theme": "Unwavering Trust"
        }


@router.get("/news")
async def get_economic_news():
    """
    Get today's REAL economic/financial news headlines.

    Fetches from major financial news sources including:
    - Yahoo Finance
    - CNBC
    - MarketWatch
    - Bloomberg
    - Reuters
    - Federal Reserve announcements
    """
    try:
        news_items = fetch_economic_news()

        return {
            "success": True,
            "data": {
                "news": news_items,
                "date": datetime.now().strftime("%A, %B %d, %Y"),
                "timestamp": datetime.now().isoformat(),
                "sources": list(set(item.get('source', 'Unknown') for item in news_items))
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scriptures")
async def get_daily_scriptures_endpoint():
    """
    Get today's selected scriptures for reflection.

    Returns 3 rotating scriptures focused on wealth, stewardship,
    and God's provision - different each day.
    """
    try:
        scriptures = get_daily_scriptures()

        return {
            "success": True,
            "data": {
                "scriptures": scriptures,
                "date": datetime.now().strftime("%A, %B %d, %Y")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devotional")
async def get_devotional(force_refresh: bool = False):
    """
    Get today's AI-generated devotional.

    Generates a Bible study and morning prayer based on REAL
    economic/financial news headlines and daily scriptures.

    The devotional is cached for the day unless force_refresh=true.
    """
    try:
        # Check cache first
        if not force_refresh:
            cached = get_cached_content()
            if cached:
                return {
                    "success": True,
                    "data": cached,
                    "cached": True
                }

        # Generate fresh content
        news_items = fetch_economic_news()
        scriptures = get_daily_scriptures()
        devotional = await generate_devotional_with_claude(news_items, scriptures)

        # Combine all content
        content = {
            "devotional": devotional,
            "scriptures": scriptures,
            "news": news_items,
            "date": datetime.now().strftime("%A, %B %d, %Y"),
            "timestamp": datetime.now().isoformat()
        }

        # Cache for the day
        set_cached_content(content)

        return {
            "success": True,
            "data": content,
            "cached": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today")
async def get_daily_manna(force_refresh: bool = False):
    """
    Get complete Daily Manna content for today.

    This is the main endpoint that returns everything:
    - Today's REAL economic/financial news headlines
    - Selected scriptures
    - AI-generated Bible study connecting news to faith
    - Morning prayer addressing current economic realities
    - Reflection questions

    News is fetched from: Yahoo Finance, CNBC, MarketWatch, Bloomberg, Reuters, Fed
    Content is cached for the day (one generation per day).
    Use force_refresh=true to regenerate.
    """
    try:
        # Check cache first
        if not force_refresh:
            cached = get_cached_content()
            if cached:
                return {
                    "success": True,
                    "data": cached,
                    "cached": True,
                    "message": "Today's manna is ready! Fresh devotional based on today's financial news."
                }

        # Generate fresh content
        news_items = fetch_economic_news()
        scriptures = get_daily_scriptures()
        devotional = await generate_devotional_with_claude(news_items, scriptures)

        # Combine all content
        content = {
            "devotional": devotional,
            "scriptures": scriptures,
            "news": news_items,
            "date": datetime.now().strftime("%A, %B %d, %Y"),
            "timestamp": datetime.now().isoformat(),
            "greeting": get_daily_greeting(),
            "news_sources": list(set(item.get('source', 'Unknown') for item in news_items))
        }

        # Cache for the day
        set_cached_content(content)

        return {
            "success": True,
            "data": content,
            "cached": False,
            "message": "Fresh manna prepared from today's headlines! May it nourish your soul."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_daily_greeting() -> str:
    """Get a contextual greeting based on time of day."""
    hour = datetime.now().hour

    if hour < 5:
        return "Night owl or early bird? Either way, God's mercies are new every morning."
    elif hour < 12:
        return "Good morning! Let's see what's happening in the financial world and what God might be teaching us today."
    elif hour < 17:
        return "Good afternoon! Take a moment to reflect on today's economic news through the lens of faith."
    elif hour < 21:
        return "Good evening! Process today's market events with eternal perspective."
    else:
        return "Rest well tonight. Tomorrow's news will bring new opportunities to trust God."
