"""Load the live /session page, measure layout + readability, save screenshots.

Usage: python scripts/probe_session_page.py [url]
Writes to %TEMP%\\session_probe\\ : desktop.png, mobile.png, report.json
"""
import json
import os
import sys
import tempfile

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://spreadworks-backend.onrender.com/session"
OUT = os.path.join(tempfile.gettempdir(), "session_probe")
os.makedirs(OUT, exist_ok=True)

MEASURE_JS = """
() => {
  const out = {};
  out.viewport = {w: window.innerWidth, h: window.innerHeight};
  out.doc = {scrollH: document.documentElement.scrollHeight, clientH: document.documentElement.clientHeight};
  // scroll containers
  const scrollers = [];
  for (const el of document.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 2) {
      scrollers.push({tag: el.tagName, cls: (el.className||'').toString().slice(0,80),
                      scrollH: el.scrollHeight, clientH: el.clientHeight});
    }
  }
  out.scrollers = scrollers;
  // text nodes: font size + color + opacity
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const sizes = {};
  const small = [];
  const dim = [];
  let words = 0;
  let n;
  while ((n = walker.nextNode())) {
    const t = n.textContent.replace(/\\s+/g,' ').trim();
    if (!t) continue;
    const el = n.parentElement;
    if (!el) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    words += t.split(' ').length;
    const fs = parseFloat(cs.fontSize);
    const key = fs.toFixed(1);
    sizes[key] = (sizes[key]||0) + 1;
    // effective opacity up the tree
    let op = 1, p = el;
    while (p && p !== document.body) { op *= parseFloat(getComputedStyle(p).opacity || '1'); p = p.parentElement; }
    const inSvg = !!el.closest('svg');
    const floor = inSvg ? 11 : 13;
    if (fs < floor) small.push({fs, text: t.slice(0,70), tag: el.tagName, svg: inSvg});
    if (op < 0.9) dim.push({op: +op.toFixed(2), fs, color: cs.color, text: t.slice(0,60)});
  }
  out.sizes = sizes; out.small = small.slice(0,60); out.smallCount = small.length;
  out.dim = dim.slice(0,40); out.dimCount = dim.length; out.words = words;
  out.headline = (document.querySelector('h1,h2')||{}).textContent || null;
  // THE CALL card = first card after the freshness banner; grab its text for the record
  const cards = [...document.querySelectorAll('div')].filter(e => /NOTHING TO ACT|NO TRADE|STAND BY|TAKE IT/.test(e.textContent||'') && e.children.length < 6);
  out.call_card = cards.length ? cards[cards.length-1].textContent.replace(/\\s+/g,' ').trim().slice(0,400) : null;
  out.no_trade_today_count = (document.body.innerText.match(/NO TRADE TODAY/g)||[]).length;
  out.sigma_count = (document.body.innerText.match(/σ/g)||[]).length;
  out.title = document.title;
  return out;
}
"""

report = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    for name, vp in (("desktop", {"width": 1440, "height": 900}), ("mobile", {"width": 390, "height": 844})):
        page = browser.new_page(viewport=vp, device_scale_factor=1)
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2500)
        m = page.evaluate(MEASURE_JS)
        # scroll the main scroller to the bottom and confirm it moves
        moved = page.evaluate("""() => {
          const els = [...document.querySelectorAll('*')].filter(e => {
            const cs = getComputedStyle(e); return (cs.overflowY==='auto'||cs.overflowY==='scroll') && e.scrollHeight>e.clientHeight+2;});
          const r = [];
          for (const e of els) { const b = e.scrollTop; e.scrollTop = e.scrollHeight; r.push({before:b, after:e.scrollTop, max:e.scrollHeight-e.clientHeight}); }
          return r; }""")
        m["scroll_test"] = moved
        page.evaluate("() => { for (const e of document.querySelectorAll('*')) { e.scrollTop = 0; } }")
        page.screenshot(path=os.path.join(OUT, f"{name}.png"), full_page=False)
        # full-page capture of the scroller content: expand by screenshotting the scroller element
        sc = page.query_selector("main") or page.query_selector("body")
        try:
            page.screenshot(path=os.path.join(OUT, f"{name}_full.png"), full_page=True)
        except Exception as e:  # noqa: BLE001
            m["full_err"] = str(e)
        report[name] = m
        page.close()
    browser.close()

with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, indent=1)

for name, m in report.items():
    print(f"== {name} viewport {m['viewport']} doc {m['doc']}")
    print(f"   scrollers: {m['scrollers']}")
    print(f"   scroll_test: {m['scroll_test']}")
    print(f"   words visible: {m['words']}  sizes(px:count): {dict(sorted(m['sizes'].items(), key=lambda kv: float(kv[0])))}")
    print(f"   below floor (prose<13px, svg<11px): {m['smallCount']}   dimmed(<0.9 opacity): {m['dimCount']}")
    for s in m["small"][:25]:
        print(f"     {s['fs']:>5}px {'svg' if s['svg'] else 'html':<4} {s['tag']:<5} {s['text']}")
    print(f"   'NO TRADE TODAY' occurrences: {m['no_trade_today_count']}   sigma symbols: {m['sigma_count']}")
    print(f"   call card: {m['call_card']}")
    for s in m["dim"][:10]:
        print(f"     dim op={s['op']} {s['fs']}px {s['color']} {s['text']}")
    print(f"   headline: {m['headline']}")
print("OUT:", OUT)
