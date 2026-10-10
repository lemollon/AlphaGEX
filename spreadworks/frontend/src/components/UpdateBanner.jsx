// "A new version shipped — reload" — because a tab never asks for new code.
//
// 🚨 THE FAILURE THIS REMOVES. Every page polls its DATA on a timer and never
// re-fetches its own CODE. A tab left open across a deploy runs the OLD UI
// against FRESH numbers forever: the clocks tick, the values update, nothing
// looks wrong. On 2026-08-19 that cost real time twice — a change that was
// shipped, deployed and verified was reported as missing, because the tab
// predated the deploy. Cache headers cannot fix it (the SPA routes already
// send no-store); the tab simply never asks again.
//
// So the app now watches for its own replacement and says so.
//
// ⛔ IT NEVER RELOADS BY ITSELF. This page is read during live trading; an
// auto-reload could wipe a scroll position or a half-read alert at exactly the
// wrong moment. It offers, and the human decides.
import { useEffect, useState } from 'react';
import { API_URL } from '../lib/api';

// The bundle this tab is actually running, read off its own script tag. Using
// the DOM rather than a build-time constant means it cannot drift from what
// was really loaded.
function currentBuild() {
  const el = [...document.querySelectorAll('script[src]')]
    .map((s) => s.src)
    .find((src) => /assets\/index-[A-Za-z0-9_-]+\.js/.test(src));
  const m = el && /(index-[A-Za-z0-9_-]+\.js)/.exec(el);
  return m ? m[1] : null;
}

export default function UpdateBanner() {
  const [stale, setStale] = useState(false);

  useEffect(() => {
    const mine = currentBuild();
    if (!mine) return;              // dev server / no hashed bundle: nothing to compare
    let alive = true;
    const check = async () => {
      try {
        const r = await fetch(`${API_URL}/api/spreadworks/version`, { cache: 'no-store' });
        const d = await r.json();
        // ⛔ Only a POSITIVE mismatch counts. A failed fetch or a null build
        // must never nag — a version checker that cries wolf on a blip is one
        // more thing to distrust on a page whose whole job is being trusted.
        if (alive && d?.build && d.build !== mine) setStale(true);
      } catch { /* offline or deploying — say nothing */ }
    };
    check();
    const t = setInterval(check, 60 * 1000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!stale) return null;
  return (
    <div style={{
      position: 'fixed', bottom: 16, right: 16, zIndex: 100,
      display: 'flex', alignItems: 'center', gap: 12,
      background: '#141824', border: '1px solid #34d39966', borderRadius: 10,
      padding: '10px 14px', boxShadow: '0 8px 24px rgba(0,0,0,.5)',
      fontSize: 13, color: '#c6cbd8', maxWidth: 'calc(100vw - 32px)',
    }}>
      <span>A newer version of this page is live — you’re seeing old code.</span>
      <button
        onClick={() => window.location.reload()}
        style={{
          all: 'unset', cursor: 'pointer', background: '#34d399', color: '#0b0e17',
          fontWeight: 700, fontSize: 12, padding: '6px 12px', borderRadius: 7,
          letterSpacing: '.03em', whiteSpace: 'nowrap',
        }}
      >RELOAD</button>
    </div>
  );
}
