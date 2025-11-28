#!/usr/bin/env python3
"""
Free API Keys Setup Script
Get your FREE API keys for multiple data sources to replace yfinance dependency
"""

print("=" * 80)
print("🔑 FREE API KEYS SETUP GUIDE")
print("=" * 80)
print()
print("Your flexible_price_data.py supports 4 FREE data sources:")
print()

# 1. Yahoo Finance (yfinance)
print("1️⃣  Yahoo Finance (yfinance) - ALREADY WORKING ✅")
print("   • FREE: Unlimited requests")
print("   • NO API KEY NEEDED")
print("   • Status: ✅ Working right now")
print("   • Priority: #1 (tries first)")
print()

# 2. Alpha Vantage
print("2️⃣  Alpha Vantage - FREE TIER (500 calls/day)")
print("   • Status: ⚠️  API key has 403 error (needs activation)")
print("   • Current key: IW5CSY60VSCU8TUJ")
print()
print("   🔧 HOW TO FIX:")
print("   1. Get a NEW free key: https://www.alphavantage.co/support/#api-key")
print("   2. Fill out form (takes 20 seconds):")
print("      - Email: your_email@example.com")
print("      - Organization: Personal Trading")
print("      - Use case: Stock market analysis")
print("   3. Check your email for the key")
print("   4. Click activation link if provided")
print("   5. Test your key:")
print("      https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey=YOUR_KEY")
print("   6. Update .env file:")
print("      ALPHA_VANTAGE_API_KEY=your_new_key_here")
print()

# 3. IEX Cloud
print("3️⃣  IEX Cloud - FREE TIER (50,000 calls/month)")
print("   • Status: ⚠️  Not configured yet")
print()
print("   🔧 HOW TO GET:")
print("   1. Sign up: https://iexcloud.io/cloud-login#/register")
print("   2. Verify email")
print("   3. Go to Console → API Tokens")
print("   4. Copy your \"Publishable Token\" (starts with pk_)")
print("   5. Add to .env file:")
print("      IEXCLOUD_API_KEY=pk_your_key_here")
print()
print("   💡 TIP: IEXCloud has excellent data quality and generous free tier!")
print()

# 4. Polygon.io
print("4️⃣  Polygon.io - FREE TIER (5 calls/minute)")
print("   • Status: ⚠️  Not configured yet")
print()
print("   🔧 HOW TO GET:")
print("   1. Sign up: https://polygon.io/")
print("   2. Verify email")
print("   3. Go to Dashboard → API Keys")
print("   4. Copy your API key")
print("   5. Add to .env file:")
print("      POLYGON_API_KEY=your_key_here")
print()
print("   ⚠️  NOTE: Free tier is limited to 5 calls/min")
print()

# 5. Twelve Data
print("5️⃣  Twelve Data - FREE TIER (800 calls/day)")
print("   • Status: ⚠️  Not configured yet")
print()
print("   🔧 HOW TO GET:")
print("   1. Sign up: https://twelvedata.com/")
print("   2. Verify email")
print("   3. Go to Dashboard → API Key")
print("   4. Copy your API key")
print("   5. Add to .env file:")
print("      TWELVE_DATA_API_KEY=your_key_here")
print()

# Summary
print("=" * 80)
print("📊 RECOMMENDATION")
print("=" * 80)
print()
print("✅ BEST FREE SETUP (3 sources):")
print()
print("   1. Yahoo Finance (yfinance) - Already working!")
print("   2. IEX Cloud - 50,000 calls/month (excellent data)")
print("   3. Alpha Vantage - 500 calls/day (fix your key)")
print()
print("   With these 3, you'll have:")
print("   • Redundancy if one source fails")
print("   • More than enough free API calls")
print("   • Excellent data quality")
print()

# Current .env file
print("=" * 80)
print("📝 YOUR .env FILE")
print("=" * 80)
print()
print("Create or update /home/user/AlphaGEX/.env:")
print()
print("""# Alpha Vantage (500 calls/day)
ALPHA_VANTAGE_API_KEY=your_new_key_here

# IEX Cloud (50,000 calls/month) - RECOMMENDED
IEXCLOUD_API_KEY=pk_your_key_here

# Polygon.io (5 calls/min) - Optional
POLYGON_API_KEY=your_key_here

# Twelve Data (800 calls/day) - Optional
TWELVE_DATA_API_KEY=your_key_here
""")
print()

# Testing
print("=" * 80)
print("🧪 TESTING YOUR SETUP")
print("=" * 80)
print()
print("After adding your API keys, test them:")
print()
print("   python3 flexible_price_data.py")
print()
print("This will:")
print("   • Test each data source")
print("   • Show which ones are working")
print("   • Display health status")
print()

# Priority order
print("=" * 80)
print("📌 AUTO-FALLBACK PRIORITY")
print("=" * 80)
print()
print("Your system tries sources in this order:")
print()
print("   1. yfinance (Yahoo Finance) - Fastest, unlimited")
print("   2. alpha_vantage - If yfinance fails")
print("   3. iexcloud - If alpha_vantage fails")
print("   4. polygon - If iexcloud fails")
print("   5. twelve_data - Last resort")
print()
print("✅ This means you're COVERED even if one or two sources fail!")
print()

print("=" * 80)
print("🚀 NEXT STEPS")
print("=" * 80)
print()
print("1. Get at least ONE new API key (IEX Cloud recommended)")
print("2. Add it to your .env file")
print("3. Test with: python3 flexible_price_data.py")
print("4. Deploy your backend to Render (will auto-read .env)")
print()
print("That's it! Your site will automatically use the best available source.")
print()
