"""
Daily Manna API routes - Economic news with faith-based devotionals.

Fetches REAL financial/economic news headlines and uses Claude AI to create
Bible studies and morning prayers that connect current events to scripture.
"""

import os
import json
import hashlib
import re
import requests
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from xml.etree import ElementTree

from fastapi import APIRouter, HTTPException
import psycopg2.extras

from backend.api.database import get_database_pool, fetch_all, fetch_one, execute_query

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
    """Fetch news from an RSS feed using requests and XML parsing."""
    news_items = []
    try:
        response = requests.get(feed_url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; AlphaGEX/1.0)'
        })
        response.raise_for_status()

        # Parse XML
        root = ElementTree.fromstring(response.content)

        # Handle different RSS formats (RSS 2.0 and Atom)
        # RSS 2.0: channel/item
        items = root.findall('.//item')

        # If no items, try Atom format: entry
        if not items:
            # Try with namespace for Atom
            namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
            items = root.findall('.//atom:entry', namespaces)
            if not items:
                items = root.findall('.//entry')

        for item in items[:max_items]:
            # Get title
            title_elem = item.find('title')
            if title_elem is None:
                title_elem = item.find('{http://www.w3.org/2005/Atom}title')
            title = title_elem.text if title_elem is not None else "No title"

            # Get link
            link_elem = item.find('link')
            if link_elem is None:
                link_elem = item.find('{http://www.w3.org/2005/Atom}link')
            if link_elem is not None:
                link = link_elem.get('href') or link_elem.text
            else:
                link = None

            # Get description/summary
            desc_elem = item.find('description')
            if desc_elem is None:
                desc_elem = item.find('summary')
            if desc_elem is None:
                desc_elem = item.find('{http://www.w3.org/2005/Atom}summary')

            summary = ""
            if desc_elem is not None and desc_elem.text:
                summary = desc_elem.text
                # Remove HTML tags
                summary = re.sub(r'<[^>]+>', '', summary)
                # Remove extra whitespace
                summary = ' '.join(summary.split())
                # Truncate if too long
                if len(summary) > 300:
                    summary = summary[:297] + "..."

            # Get publication date
            pub_date_elem = item.find('pubDate')
            if pub_date_elem is None:
                pub_date_elem = item.find('published')
            if pub_date_elem is None:
                pub_date_elem = item.find('{http://www.w3.org/2005/Atom}published')

            pub_date = datetime.now().isoformat()
            if pub_date_elem is not None and pub_date_elem.text:
                try:
                    from email.utils import parsedate_to_datetime
                    pub_date = parsedate_to_datetime(pub_date_elem.text).isoformat()
                except:
                    pub_date = datetime.now().isoformat()

            news_items.append({
                "headline": title.strip() if title else "No title",
                "summary": summary,
                "source": source_name,
                "url": link,
                "timestamp": pub_date,
                "category": "Financial News"
            })

    except requests.exceptions.RequestException as e:
        print(f"Network error fetching RSS from {source_name}: {e}")
    except ElementTree.ParseError as e:
        print(f"XML parse error from {source_name}: {e}")
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

        # Auto-archive for historical access
        save_to_archive(content)

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

        # Auto-archive for historical access
        save_to_archive(content)

        return {
            "success": True,
            "data": content,
            "cached": False,
            "message": "Fresh manna prepared from today's headlines! May it nourish your soul."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_daily_greeting() -> str:
    """Get a contextual greeting based on time of day in Central Time (Texas)."""
    try:
        from zoneinfo import ZoneInfo
        central = ZoneInfo("America/Chicago")
        hour = datetime.now(central).hour
    except ImportError:
        # Fallback for older Python versions
        import pytz
        central = pytz.timezone("America/Chicago")
        hour = datetime.now(central).hour

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


# ============================================================================
# ARCHIVE, COMMENTS, REFLECTIONS & PRAYER TRACKER
# Persistent storage using PostgreSQL
# ============================================================================


def save_to_archive(content: Dict[str, Any]) -> None:
    """Save devotional to database archive."""
    try:
        pool = get_database_pool()
        if not pool.is_available:
            print("Database not available - skipping archive save")
            return

        date_key = datetime.now().strftime("%Y-%m-%d")
        devotional = content.get("devotional", {})
        scriptures = content.get("scriptures", [])
        news = content.get("news", [])
        greeting = content.get("greeting", "")
        news_sources = content.get("news_sources", [])
        generated_at = content.get("timestamp", datetime.now().isoformat())

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_manna_archive
                    (date, devotional, scriptures, news, greeting, news_sources, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    devotional = EXCLUDED.devotional,
                    scriptures = EXCLUDED.scriptures,
                    news = EXCLUDED.news,
                    greeting = EXCLUDED.greeting,
                    news_sources = EXCLUDED.news_sources,
                    generated_at = EXCLUDED.generated_at,
                    archived_at = NOW()
            """, (
                date_key,
                json.dumps(devotional),
                json.dumps(scriptures),
                json.dumps(news),
                greeting,
                news_sources,
                generated_at
            ))
            print(f"Archived Daily Manna for {date_key}")

    except Exception as e:
        print(f"Error saving to archive: {e}")


@router.get("/archive")
async def get_devotional_archive(limit: int = 30):
    """
    Get archived devotionals from past days.

    Returns a list of past devotionals for review.
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            return {
                "success": True,
                "data": {"archive": [], "total": 0},
                "message": "Database not available"
            }

        with pool.get_connection() as conn:
            cursor = conn.cursor()

            # Get archive list
            cursor.execute("""
                SELECT
                    date,
                    devotional->>'theme' as theme,
                    devotional->>'key_insight' as key_insight,
                    scriptures,
                    jsonb_array_length(news) as news_count,
                    archived_at
                FROM daily_manna_archive
                ORDER BY date DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()

            # Get total count
            cursor.execute("SELECT COUNT(*) as count FROM daily_manna_archive")
            total_row = cursor.fetchone()
            total = total_row['count'] if total_row else 0

            archive_list = []
            for row in rows:
                scriptures = row.get('scriptures', [])
                if isinstance(scriptures, str):
                    scriptures = json.loads(scriptures)
                archive_list.append({
                    "date": str(row['date']),
                    "theme": row.get('theme', 'Unknown'),
                    "key_insight": row.get('key_insight', ''),
                    "scriptures": [s.get("reference") for s in scriptures] if scriptures else [],
                    "news_count": row.get('news_count', 0),
                    "archived_at": row['archived_at'].isoformat() if row.get('archived_at') else None
                })

            return {
                "success": True,
                "data": {
                    "archive": archive_list,
                    "total": total
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/{date}")
async def get_archived_devotional(date: str):
    """
    Get a specific archived devotional by date.

    Date format: YYYY-MM-DD
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            raise HTTPException(status_code=503, detail="Database not available")

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM daily_manna_archive WHERE date = %s
            """, (date,))
            row = cursor.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail=f"No devotional found for {date}")

            # Parse JSONB fields
            devotional = row.get('devotional', {})
            scriptures = row.get('scriptures', [])
            news = row.get('news', [])

            return {
                "success": True,
                "data": {
                    "date": str(row['date']),
                    "devotional": devotional,
                    "scriptures": scriptures,
                    "news": news,
                    "greeting": row.get('greeting'),
                    "news_sources": row.get('news_sources', []),
                    "timestamp": row.get('generated_at').isoformat() if row.get('generated_at') else None,
                    "archived_at": row.get('archived_at').isoformat() if row.get('archived_at') else None
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMMUNITY COMMENTS
# ============================================================================

@router.post("/comments")
async def add_comment(request: dict):
    """
    Add a comment to today's devotional.

    Request body:
    {
        "user_name": "John",
        "user_id": "user123",  # Optional, for tracking
        "comment": "This really spoke to me today...",
        "date": "2024-12-20"  # Optional, defaults to today
    }
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            raise HTTPException(status_code=503, detail="Database not available")

        user_name = request.get("user_name", "Anonymous")
        user_id = request.get("user_id", "anonymous")
        comment_text = request.get("comment", "").strip()
        comment_date = request.get("date", datetime.now().strftime("%Y-%m-%d"))

        if not comment_text:
            raise HTTPException(status_code=400, detail="Comment cannot be empty")

        if len(comment_text) > 2000:
            raise HTTPException(status_code=400, detail="Comment too long (max 2000 characters)")

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_manna_comments (user_id, user_name, comment, date)
                VALUES (%s, %s, %s, %s)
                RETURNING id, user_id, user_name, comment, date, likes, created_at
            """, (user_id, user_name[:50], comment_text, comment_date))
            row = cursor.fetchone()

            comment = {
                "id": row['id'],
                "user_name": row['user_name'],
                "user_id": row['user_id'],
                "comment": row['comment'],
                "date": str(row['date']),
                "created_at": row['created_at'].isoformat(),
                "likes": row['likes']
            }

            return {
                "success": True,
                "data": comment,
                "message": "Comment added successfully"
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments")
async def get_comments(date: str = None, limit: int = 50):
    """
    Get comments for a devotional.

    If date is not specified, returns comments for today.
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            return {
                "success": True,
                "data": {"comments": [], "total": 0, "date": date or datetime.now().strftime("%Y-%m-%d")}
            }

        target_date = date or datetime.now().strftime("%Y-%m-%d")

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, user_name, comment, date, likes, created_at
                FROM daily_manna_comments
                WHERE date = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (target_date, limit))
            rows = cursor.fetchall()

            # Get total count
            cursor.execute("""
                SELECT COUNT(*) as count FROM daily_manna_comments WHERE date = %s
            """, (target_date,))
            total_row = cursor.fetchone()
            total = total_row['count'] if total_row else 0

            comments = [{
                "id": row['id'],
                "user_name": row['user_name'],
                "user_id": row['user_id'],
                "comment": row['comment'],
                "date": str(row['date']),
                "created_at": row['created_at'].isoformat(),
                "likes": row['likes']
            } for row in rows]

            return {
                "success": True,
                "data": {
                    "comments": comments,
                    "total": total,
                    "date": target_date
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comments/{comment_id}/like")
async def like_comment(comment_id: int):
    """Like a comment."""
    try:
        pool = get_database_pool()
        if not pool.is_available:
            raise HTTPException(status_code=503, detail="Database not available")

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE daily_manna_comments
                SET likes = likes + 1
                WHERE id = %s
                RETURNING likes
            """, (comment_id,))
            row = cursor.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Comment not found")

            return {
                "success": True,
                "data": {"likes": row['likes']}
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PERSONAL REFLECTIONS/NOTES
# ============================================================================

@router.post("/reflections")
async def save_reflection(request: dict):
    """
    Save a personal reflection/note for a devotional.

    Request body:
    {
        "user_id": "user123",
        "date": "2024-12-20",  # Optional, defaults to today
        "reflection": "My thoughts on today's devotional...",
        "prayer_answered": false,  # Optional
        "favorite": false  # Optional - mark as favorite
    }
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            raise HTTPException(status_code=503, detail="Database not available")

        user_id = request.get("user_id", "default_user")
        reflection_date = request.get("date", datetime.now().strftime("%Y-%m-%d"))
        reflection_text = request.get("reflection", "").strip()
        prayer_answered = request.get("prayer_answered", False)
        favorite = request.get("favorite", False)

        if not reflection_text:
            raise HTTPException(status_code=400, detail="Reflection cannot be empty")

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_manna_reflections
                    (user_id, date, reflection, prayer_answered, favorite)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, user_id, date, reflection, prayer_answered, favorite, created_at, updated_at
            """, (user_id, reflection_date, reflection_text, prayer_answered, favorite))
            row = cursor.fetchone()

            reflection = {
                "id": row['id'],
                "user_id": row['user_id'],
                "date": str(row['date']),
                "reflection": row['reflection'],
                "prayer_answered": row['prayer_answered'],
                "favorite": row['favorite'],
                "created_at": row['created_at'].isoformat(),
                "updated_at": row['updated_at'].isoformat()
            }

            return {
                "success": True,
                "data": reflection,
                "message": "Reflection saved successfully"
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reflections")
async def get_reflections(user_id: str = "default_user", limit: int = 100):
    """
    Get all reflections for a user.
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            return {
                "success": True,
                "data": {"reflections": [], "total": 0, "favorites": 0}
            }

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, date, reflection, prayer_answered, favorite, created_at, updated_at
                FROM daily_manna_reflections
                WHERE user_id = %s
                ORDER BY date DESC
                LIMIT %s
            """, (user_id, limit))
            rows = cursor.fetchall()

            # Get counts
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN favorite THEN 1 END) as favorites
                FROM daily_manna_reflections
                WHERE user_id = %s
            """, (user_id,))
            counts = cursor.fetchone()

            reflections = [{
                "id": row['id'],
                "user_id": row['user_id'],
                "date": str(row['date']),
                "reflection": row['reflection'],
                "prayer_answered": row['prayer_answered'],
                "favorite": row['favorite'],
                "created_at": row['created_at'].isoformat(),
                "updated_at": row['updated_at'].isoformat()
            } for row in rows]

            return {
                "success": True,
                "data": {
                    "reflections": reflections,
                    "total": counts['total'] if counts else 0,
                    "favorites": counts['favorites'] if counts else 0
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reflections/{date}")
async def get_reflection_for_date(date: str, user_id: str = "default_user"):
    """
    Get reflection for a specific date.
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            return {
                "success": True,
                "data": {"reflections": [], "date": date}
            }

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, date, reflection, prayer_answered, favorite, created_at, updated_at
                FROM daily_manna_reflections
                WHERE user_id = %s AND date = %s
                ORDER BY created_at DESC
            """, (user_id, date))
            rows = cursor.fetchall()

            reflections = [{
                "id": row['id'],
                "user_id": row['user_id'],
                "date": str(row['date']),
                "reflection": row['reflection'],
                "prayer_answered": row['prayer_answered'],
                "favorite": row['favorite'],
                "created_at": row['created_at'].isoformat(),
                "updated_at": row['updated_at'].isoformat()
            } for row in rows]

            return {
                "success": True,
                "data": {
                    "reflections": reflections,
                    "date": date
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/reflections/{reflection_id}")
async def update_reflection(reflection_id: int, request: dict):
    """
    Update an existing reflection.
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            raise HTTPException(status_code=503, detail="Database not available")

        user_id = request.get("user_id", "default_user")

        with pool.get_connection() as conn:
            cursor = conn.cursor()

            # Build update query dynamically
            updates = []
            params = []
            if "reflection" in request:
                updates.append("reflection = %s")
                params.append(request["reflection"])
            if "prayer_answered" in request:
                updates.append("prayer_answered = %s")
                params.append(request["prayer_answered"])
            if "favorite" in request:
                updates.append("favorite = %s")
                params.append(request["favorite"])

            if not updates:
                raise HTTPException(status_code=400, detail="No fields to update")

            updates.append("updated_at = NOW()")
            params.extend([reflection_id, user_id])

            cursor.execute(f"""
                UPDATE daily_manna_reflections
                SET {', '.join(updates)}
                WHERE id = %s AND user_id = %s
                RETURNING id, user_id, date, reflection, prayer_answered, favorite, created_at, updated_at
            """, tuple(params))
            row = cursor.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Reflection not found")

            reflection = {
                "id": row['id'],
                "user_id": row['user_id'],
                "date": str(row['date']),
                "reflection": row['reflection'],
                "prayer_answered": row['prayer_answered'],
                "favorite": row['favorite'],
                "created_at": row['created_at'].isoformat(),
                "updated_at": row['updated_at'].isoformat()
            }

            return {
                "success": True,
                "data": reflection,
                "message": "Reflection updated"
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PRAYER TRACKER
# ============================================================================

def calculate_prayer_streak(user_id: str, conn) -> tuple:
    """Calculate current and longest prayer streaks for a user."""
    cursor = conn.cursor()

    # Get all prayer dates for user, ordered descending
    cursor.execute("""
        SELECT date FROM daily_manna_prayer_tracker
        WHERE user_id = %s
        ORDER BY date DESC
    """, (user_id,))
    rows = cursor.fetchall()

    if not rows:
        return 0, 0

    dates = [row['date'] for row in rows]
    today = date.today()

    # Calculate current streak
    current_streak = 0
    check_date = today
    for d in dates:
        if d == check_date:
            current_streak += 1
            check_date = check_date - timedelta(days=1)
        elif d == check_date - timedelta(days=1):
            # Allow for checking from yesterday if not prayed today
            check_date = d
            current_streak += 1
            check_date = check_date - timedelta(days=1)
        else:
            break

    # Calculate longest streak
    longest_streak = 1
    streak = 1
    sorted_dates = sorted(dates)
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i-1] == timedelta(days=1):
            streak += 1
            longest_streak = max(longest_streak, streak)
        else:
            streak = 1

    return current_streak, longest_streak


@router.post("/prayer/today")
async def mark_prayed_today(request: dict):
    """
    Mark that user prayed today.

    Request body:
    {
        "user_id": "user123"
    }
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            raise HTTPException(status_code=503, detail="Database not available")

        user_id = request.get("user_id", "default_user")
        today = datetime.now().strftime("%Y-%m-%d")

        with pool.get_connection() as conn:
            cursor = conn.cursor()

            # Insert prayer record (ignore if already exists)
            cursor.execute("""
                INSERT INTO daily_manna_prayer_tracker (user_id, date)
                VALUES (%s, %s)
                ON CONFLICT (user_id, date) DO NOTHING
            """, (user_id, today))

            # Get total days
            cursor.execute("""
                SELECT COUNT(*) as total FROM daily_manna_prayer_tracker
                WHERE user_id = %s
            """, (user_id,))
            total_row = cursor.fetchone()
            total_days = total_row['total'] if total_row else 0

            # Calculate streaks
            current_streak, longest_streak = calculate_prayer_streak(user_id, conn)

            return {
                "success": True,
                "data": {
                    "prayed_today": True,
                    "current_streak": current_streak,
                    "longest_streak": longest_streak,
                    "total_days": total_days
                },
                "message": f"Prayer logged! You're on a {current_streak}-day streak!"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prayer/stats")
async def get_prayer_stats(user_id: str = "default_user"):
    """
    Get prayer statistics for a user.
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            return {
                "success": True,
                "data": {
                    "prayed_today": False,
                    "current_streak": 0,
                    "longest_streak": 0,
                    "total_days": 0,
                    "recent_days": []
                }
            }

        today = datetime.now().strftime("%Y-%m-%d")

        with pool.get_connection() as conn:
            cursor = conn.cursor()

            # Check if prayed today
            cursor.execute("""
                SELECT 1 FROM daily_manna_prayer_tracker
                WHERE user_id = %s AND date = %s
            """, (user_id, today))
            prayed_today = cursor.fetchone() is not None

            # Get total days
            cursor.execute("""
                SELECT COUNT(*) as total FROM daily_manna_prayer_tracker
                WHERE user_id = %s
            """, (user_id,))
            total_row = cursor.fetchone()
            total_days = total_row['total'] if total_row else 0

            # Get last 7 days of prayer activity
            cursor.execute("""
                SELECT date FROM daily_manna_prayer_tracker
                WHERE user_id = %s AND date >= %s
                ORDER BY date DESC
            """, (user_id, (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")))
            prayer_dates = {row['date'] for row in cursor.fetchall()}

            recent_days = []
            for i in range(7):
                day = (datetime.now() - timedelta(days=i)).date()
                recent_days.append({
                    "date": str(day),
                    "prayed": day in prayer_dates
                })

            # Calculate streaks
            current_streak, longest_streak = calculate_prayer_streak(user_id, conn)

            return {
                "success": True,
                "data": {
                    "prayed_today": prayed_today,
                    "current_streak": current_streak,
                    "longest_streak": longest_streak,
                    "total_days": total_days,
                    "recent_days": recent_days
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SUMMARY WIDGET (for Dashboard)
# ============================================================================

@router.get("/widget")
async def get_daily_manna_widget():
    """
    Get a summary for the Dashboard widget.

    Returns minimal data for displaying in a small card on the dashboard.
    """
    try:
        cached = get_cached_content()

        if cached:
            devotional = cached.get("devotional", {})
            return {
                "success": True,
                "data": {
                    "date": cached.get("date"),
                    "theme": devotional.get("theme", "Daily Wisdom"),
                    "key_insight": devotional.get("key_insight", "Seek first His kingdom."),
                    "scripture": cached.get("scriptures", [{}])[0].get("reference", ""),
                    "has_content": True
                }
            }
        else:
            # Return placeholder if no content generated yet
            scriptures = get_daily_scriptures()
            return {
                "success": True,
                "data": {
                    "date": datetime.now().strftime("%A, %B %d, %Y"),
                    "theme": "Fresh Manna Awaits",
                    "key_insight": "Click to receive today's devotional",
                    "scripture": scriptures[0]["reference"] if scriptures else "",
                    "has_content": False
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BACKFILL & ADMIN ENDPOINTS
# ============================================================================

@router.post("/backfill")
async def backfill_devotionals(request: dict):
    """
    Generate and archive devotionals for past dates.

    This endpoint allows backfilling historical devotionals for dates
    that were missed or before the archive system was implemented.

    Request body:
    {
        "start_date": "2024-12-01",  # Start date (YYYY-MM-DD)
        "end_date": "2024-12-15",    # End date (YYYY-MM-DD), defaults to yesterday
        "skip_existing": true        # Skip dates that already have archives
    }

    Note: This is a slow operation as it generates AI content for each day.
    Consider running for small date ranges.
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            raise HTTPException(status_code=503, detail="Database not available")

        start_date_str = request.get("start_date")
        end_date_str = request.get("end_date", (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))
        skip_existing = request.get("skip_existing", True)

        if not start_date_str:
            raise HTTPException(status_code=400, detail="start_date is required")

        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        if start_date > end_date:
            raise HTTPException(status_code=400, detail="start_date must be before end_date")

        if end_date >= date.today():
            end_date = date.today() - timedelta(days=1)

        # Get existing archive dates if skipping
        existing_dates = set()
        if skip_existing:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT date FROM daily_manna_archive
                    WHERE date >= %s AND date <= %s
                """, (start_date, end_date))
                existing_dates = {row['date'] for row in cursor.fetchall()}

        # Generate devotionals for each missing date
        results = {
            "generated": [],
            "skipped": [],
            "failed": []
        }

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")

            if current_date in existing_dates:
                results["skipped"].append(date_str)
                current_date += timedelta(days=1)
                continue

            try:
                # Generate content for this date
                # Note: News will be current (can't fetch historical RSS)
                # but scriptures rotate based on day of year
                news_items = fetch_economic_news()
                scriptures = get_daily_scriptures()
                devotional = await generate_devotional_with_claude(news_items, scriptures)

                content = {
                    "devotional": devotional,
                    "scriptures": scriptures,
                    "news": news_items,
                    "date": current_date.strftime("%A, %B %d, %Y"),
                    "timestamp": datetime.now().isoformat(),
                    "greeting": "Backfilled devotional",
                    "news_sources": list(set(item.get('source', 'Unknown') for item in news_items)),
                    "backfilled": True
                }

                # Save to database
                with pool.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO daily_manna_archive
                            (date, devotional, scriptures, news, greeting, news_sources, generated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (date) DO UPDATE SET
                            devotional = EXCLUDED.devotional,
                            scriptures = EXCLUDED.scriptures,
                            news = EXCLUDED.news,
                            greeting = EXCLUDED.greeting,
                            news_sources = EXCLUDED.news_sources,
                            generated_at = EXCLUDED.generated_at,
                            archived_at = NOW()
                    """, (
                        date_str,
                        json.dumps(devotional),
                        json.dumps(scriptures),
                        json.dumps(news_items),
                        "Backfilled devotional",
                        content["news_sources"],
                        datetime.now().isoformat()
                    ))

                results["generated"].append(date_str)
                print(f"Backfilled Daily Manna for {date_str}")

            except Exception as e:
                results["failed"].append({"date": date_str, "error": str(e)})
                print(f"Failed to backfill {date_str}: {e}")

            current_date += timedelta(days=1)

        return {
            "success": True,
            "data": {
                "generated": len(results["generated"]),
                "skipped": len(results["skipped"]),
                "failed": len(results["failed"]),
                "details": results
            },
            "message": f"Backfill complete: {len(results['generated'])} generated, {len(results['skipped'])} skipped, {len(results['failed'])} failed"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/archive/stats")
async def get_archive_stats():
    """
    Get statistics about the archive.
    """
    try:
        pool = get_database_pool()
        if not pool.is_available:
            return {
                "success": True,
                "data": {"total": 0, "oldest": None, "newest": None}
            }

        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    MIN(date) as oldest,
                    MAX(date) as newest
                FROM daily_manna_archive
            """)
            row = cursor.fetchone()

            return {
                "success": True,
                "data": {
                    "total": row['total'] if row else 0,
                    "oldest": str(row['oldest']) if row and row['oldest'] else None,
                    "newest": str(row['newest']) if row and row['newest'] else None
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
