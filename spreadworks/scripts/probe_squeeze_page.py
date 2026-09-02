"""Load the /squeeze page, measure layout + readability, save screenshots.

Usage: python scripts/probe_squeeze_page.py [url]
Writes to %TEMP%\\squeeze_probe\\ : desktop.png, mobile.png, report.json

What it checks (the four-section contract from 2026-09-02):
  * section order: status row -> THE CALL -> the gamma line -> ONE fold
  * the fold "How this signal has done" is collapsed on a fresh load, stays
    open across a reload once opened, and collapses again when localStorage
    is cleared
  * zero forbidden words above the fold: NO TRADE TODAY / n= / sigma / Stage / z=
  * every scroll container actually scrolls to its bottom
  * prose font floor 13px (SVG 11px)
  * no console errors
"""
import json
import os
import sys
import tempfile

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://spreadworks-backend.onrender.com/squeeze"
OUT = os.path.join(tempfile.gettempdir(), "squeeze_probe")
os.makedirs(OUT, exist_ok=True)

FOLD_TITLE = "How this signal has done"
FOLD_KEY = "sw_squeeze_history_fold_open"
FORBIDDEN = ["NO TRADE TODAY", "n=", "σ", "Stage ", "z="]

MEASURE_JS = """
(args) => {
  const [FOLD_TITLE, FORBIDDEN] = args;
  const out = {};
  out.viewport = {w: window.innerWidth, h: window.innerHeight};
  const scrollers = [];
  for (const el of document.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 2) {
      scrollers.push({tag: el.tagName, cls: (el.className||'').toString().slice(0,80),
                      scrollH: el.scrollHeight, clientH: el.clientHeight});
    }
  }
  out.scrollers = scrollers;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const sizes = {}; const small = []; let words = 0; let n;
  while ((n = walker.nextNode())) {
    const t = n.textContent.replace(/\\s+/g,' ').trim();
    if (!t) continue;
    const el = n.parentElement; if (!el) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    words += t.split(' ').length;
    const fs = parseFloat(cs.fontSize);
    sizes[fs.toFixed(1)] = (sizes[fs.toFixed(1)]||0) + 1;
    const inSvg = !!el.closest('svg');
    if (fs < (inSvg ? 11 : 13)) small.push({fs, text: t.slice(0,70), tag: el.tagName, svg: inSvg});
  }
  out.sizes = sizes; out.small = small.slice(0,40); out.smallCount = small.length; out.words = words;

  // Section order — the first card carrying each marker, by vertical position.
  const main = document.querySelector('h1')?.closest('div');
  const cards = main ? [...main.children].filter(e => e.tagName === 'DIV') : [];
  out.cards = cards.map(c => ({top: Math.round(c.getBoundingClientRect().top),
                               text: c.innerText.replace(/\\s+/g,' ').trim().slice(0,90)}));
  const findTop = (re) => { const c = cards.find(c => re.test(c.innerText||'')); return c ? Math.round(c.getBoundingClientRect().top) : null; };
  out.top_status = findTop(/next reading|page loaded|CURRENT|BEHIND|MIXED SOURCES|CAPTURE FAILED|NOT ARMED|FRESHNESS UNKNOWN/);
  out.top_call   = findTop(/SELL THE PUT SPREAD|STAND DOWN FROM SELLING|SKIP THE PUT SPREAD|NO USABLE READING|NOTHING TO ACT ON HERE/);
  out.top_chart  = findTop(/Net dealer gamma — last/);
  out.top_fold   = findTop(new RegExp(FOLD_TITLE));
  out.card_count = cards.length;

  const foldBtn = [...document.querySelectorAll('button')].find(b => (b.textContent||'').includes(FOLD_TITLE));
  out.fold_present = !!foldBtn;
  out.fold_open = foldBtn ? foldBtn.getAttribute('aria-expanded') === 'true' : null;

  const body = document.body.innerText;
  out.forbidden = {};
  for (const w of FORBIDDEN) out.forbidden[w] = (body.split(w).length - 1);
  out.headline = document.querySelector('h1')?.textContent || null;
  const call = cards.find(c => /SELL THE PUT SPREAD|STAND DOWN FROM SELLING|SKIP THE PUT SPREAD|NO USABLE READING|NOTHING TO ACT ON HERE/.test(c.innerText||''));
  out.call_card = call ? call.innerText.replace(/\\s+/g,' ').trim().slice(0,500) : null;
  out.title = document.title;
  return out;
}
"""

SCROLL_JS = """() => {
  const els = [...document.querySelectorAll('*')].filter(e => {
    const cs = getComputedStyle(e); return (cs.overflowY==='auto'||cs.overflowY==='scroll') && e.scrollHeight>e.clientHeight+2;});
  const r = [];
  for (const e of els) { const b = e.scrollTop; e.scrollTop = e.scrollHeight; r.push({before:b, after:e.scrollTop, max:e.scrollHeight-e.clientHeight}); }
  return r; }"""

report = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    for name, vp in (("desktop", {"width": 1440, "height": 900}), ("mobile", {"width": 390, "height": 844})):
        ctx = browser.new_context(viewport=vp, device_scale_factor=1)
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2500)
        m = page.evaluate(MEASURE_JS, [FOLD_TITLE, FORBIDDEN])
        m["scroll_test"] = page.evaluate(SCROLL_JS)
        page.evaluate("() => { for (const e of document.querySelectorAll('*')) { e.scrollTop = 0; } }")
        page.screenshot(path=os.path.join(OUT, f"{name}.png"), full_page=False)

        # Fold persistence: open it, reload, it must still be open; clear, reload, closed.
        if name == "desktop" and m.get("fold_present"):
            page.get_by_role("button", name=FOLD_TITLE).click()
            page.wait_for_timeout(800)
            m["fold_open_after_click"] = page.evaluate(
                f"() => [...document.querySelectorAll('button')].find(b => b.textContent.includes('{FOLD_TITLE}'))?.getAttribute('aria-expanded') === 'true'")
            m["fold_saved"] = page.evaluate(f"() => localStorage.getItem('{FOLD_KEY}')")
            m["words_with_fold_open"] = page.evaluate("() => document.body.innerText.split(/\\s+/).length")
            page.screenshot(path=os.path.join(OUT, f"{name}_fold_open_full.png"), full_page=True)
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(2000)
            m["fold_open_after_reload"] = page.evaluate(
                f"() => [...document.querySelectorAll('button')].find(b => b.textContent.includes('{FOLD_TITLE}'))?.getAttribute('aria-expanded') === 'true'")
            page.evaluate("() => localStorage.clear()")
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(2000)
            m["fold_open_after_clear"] = page.evaluate(
                f"() => [...document.querySelectorAll('button')].find(b => b.textContent.includes('{FOLD_TITLE}'))?.getAttribute('aria-expanded') === 'true'")
        m["console_errors"] = errors[:10]
        report[name] = m
        ctx.close()
    browser.close()

with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, indent=1)

ok = True
for name, m in report.items():
    print(f"== {name} viewport {m['viewport']}")
    print(f"   cards on page: {m['card_count']}  order tops: status={m['top_status']} call={m['top_call']} chart={m['top_chart']} fold={m['top_fold']}")
    order_ok = (m['top_status'] is not None and m['top_call'] is not None and m['top_chart'] is not None
                and m['top_fold'] is not None and m['top_status'] < m['top_call'] < m['top_chart'] < m['top_fold'])
    print(f"   section order status->call->chart->fold: {'OK' if order_ok else 'FAIL'}")
    print(f"   fold present {m['fold_present']} · collapsed on fresh load: {'OK' if m['fold_open'] is False else 'FAIL'}")
    if 'fold_open_after_click' in m:
        print(f"   fold opens on click {m['fold_open_after_click']} · saved={m['fold_saved']} · open after reload {m['fold_open_after_reload']} · closed after clear {m['fold_open_after_clear'] is False}")
        print(f"   words with fold open: {m['words_with_fold_open']}")
    print(f"   words visible (fold closed): {m['words']}")
    print(f"   scrollers: {m['scrollers']}")
    print(f"   scroll_test: {m['scroll_test']}")
    print(f"   below floor (prose<13px, svg<11px): {m['smallCount']}")
    for s in m["small"][:20]:
        print(f"     {s['fs']:>5}px {'svg' if s['svg'] else 'html':<4} {s['tag']:<5} {s['text']}")
    print(f"   forbidden words: {m['forbidden']}")
    print(f"   console errors: {m['console_errors']}")
    print(f"   call card: {m['call_card']}")
    ok = ok and order_ok and m['fold_open'] is False and not any(m['forbidden'].values()) and not m['console_errors']
print("OUT:", OUT)
print("VERDICT:", "PASS" if ok else "FAIL")
