/* AUTO-GENERATED from ~/Downloads/landing.html — verbatim design JS (Tweaks panel removed).
   Injected once by src/app/page.tsx after the markup mounts. */
(function(){
try {
(() => {
    const tb = document.getElementById('topbar');
    tb.style.display = 'flex';
    tb.innerHTML = `
      <span><span class="pulse"></span><b style="color:var(--pos);letter-spacing:.18em">MARKET OPEN</b></span>
      <span class="sep">│</span>
      <span class="tk"><span class="k">SPY</span><b>528.41</b><span class="up">▴ 0.27%</span></span>
      <span class="tk"><span class="k">VIX</span><b>13.42</b><span class="dn">▾ 1.13%</span></span>
      <span class="tk"><span class="k">IVR</span><b>25.7</b></span>
      <span class="tk"><span class="k">DTE</span><b style="color:var(--accent)">SHORT</b></span>
      <span class="sep">│</span>
      <span class="tk"><span class="k">VOL REGIME</span><b style="color:var(--pos)">NORMAL</b></span>
      <span class="right">· MARKET PULSE ·</span>
    `;
  })();
} catch (e) { console.error('[landing block 1]', e); }

/* ═══════════════════════════════════════════ */

try {
(() => {
  // ═══ 1. Hero schematic: draw-on-scroll ═══════════════
  const heroSvg = document.querySelector('.schematic svg');
  if (heroSvg) {
    const curve = heroSvg.querySelector('#payoff-curve');
    const zone  = heroSvg.querySelector('#profit-zone');
    if (curve) {
      try {
        const len = curve.getTotalLength();
        curve.style.strokeDasharray  = len;
        curve.style.strokeDashoffset = len;
      } catch(_) {}
    }
    const triggerDraw = () => {
      if (curve) { curve.classList.add('drawn'); curve.style.strokeDashoffset = '0'; }
      if (zone)  { zone.classList.add('drawn');  zone.style.opacity = '1'; }
    };
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) { triggerDraw(); obs.unobserve(e.target); }
      });
    }, { threshold: 0.25 });
    obs.observe(heroSvg);
    // Fallback: if IO doesn't fire (some embed contexts), trigger after a beat
    setTimeout(triggerDraw, 1200);
  }

  // ═══ 2. Draggable SPY price line + live P/L ══════════
  const sch = document.querySelector('.schematic');
  const grip = document.getElementById('price-grip');
  const line = document.getElementById('price-line');
  const lbl  = document.getElementById('spy-label');
  const drag = document.getElementById('drag-area');
  const hint = document.getElementById('drag-hint');
  const plEl = document.getElementById('pl-val');
  const netEl = document.getElementById('net-val');

  const X_MIN = 60, X_MAX = 660;

  const strats = {
    condor: {
      pts: [[40,360],[200,360],[240,180],[360,180],[480,180],[520,360],[680,360]],
      zone: {x:240, y:180, w:240, h:140},
      maxProfit: 100, maxLoss: -233,
      maxProfitTxt: 'MAX PROFIT · +100% credit · $150',
      maxLossTxt:   'MAX LOSS · -233% · -$350',
      name: 'IRON CONDOR'
    },
    spread: {
      pts: [[40,360],[120,360],[200,360],[240,180],[460,180],[570,180],[680,180]],
      zone: {x:240, y:180, w:440, h:140},
      maxProfit: 100, maxLoss: -233,
      maxProfitTxt: 'MAX PROFIT · +100% credit · $148',
      maxLossTxt:   'MAX LOSS · -233% · -$352',
      name: 'PUT CREDIT SPREAD'
    },
    fly: {
      pts: [[40,360],[200,360],[280,360],[360,140],[440,360],[540,360],[680,360]],
      zone: {x:355, y:140, w:10, h:220},
      maxProfit: 260, maxLoss: -100,
      maxProfitTxt: 'MAX PROFIT · +260% · pin 528 · $390',
      maxLossTxt:   'MAX LOSS · -100% · -$150',
      name: 'IRON BUTTERFLY'
    }
  };
  let currentStrat = 'condor';

  const payoffPct = (x) => {
    const s = strats[currentStrat];
    const pts = s.pts;
    let y = pts[pts.length-1][1];
    if (x <= pts[0][0]) y = pts[0][1];
    else if (x >= pts[pts.length-1][0]) y = pts[pts.length-1][1];
    else for (let i=0; i<pts.length-1; i++) {
      const [x1,y1] = pts[i], [x2,y2] = pts[i+1];
      if (x >= x1 && x <= x2) {
        const t = x2===x1 ? 0 : (x-x1)/(x2-x1);
        y = y1 + t*(y2-y1); break;
      }
    }
    const ys = pts.map(p=>p[1]);
    const yMin = Math.min(...ys), yMax = Math.max(...ys);
    const t = yMax === yMin ? 0 : (yMax - y) / (yMax - yMin);
    return s.maxLoss + t * (s.maxProfit - s.maxLoss);
  };

  // Expose for chip switcher + scrubber
  window.__payoffPct = payoffPct;
  window.__isDragging = () => dragging;
  window.__setStrategy = (name) => {
    if (!strats[name] || name === currentStrat) return;
    const fromS = strats[currentStrat];
    const toS = strats[name];
    currentStrat = name;
    const curveEl = document.getElementById('payoff-curve');
    const zoneEl  = document.getElementById('profit-zone');
    const lblMP   = document.getElementById('lbl-max-profit');
    const lblMLL  = document.getElementById('lbl-max-loss-l');
    const lblMLR  = document.getElementById('lbl-max-loss-r');
    const stratNameEl = document.getElementById('sch-strat-name');
    if (curveEl) { curveEl.style.strokeDasharray='none'; curveEl.style.strokeDashoffset='0'; }
    const t0 = performance.now(), dur = 600, ease = t => 1 - Math.pow(1-t, 3);
    const step = (now) => {
      const tt = Math.min(1, (now - t0) / dur), e = ease(tt);
      const pts = fromS.pts.map((p,i) => {
        const q = toS.pts[i];
        return [p[0]+(q[0]-p[0])*e, p[1]+(q[1]-p[1])*e];
      });
      if (curveEl) curveEl.setAttribute('points', pts.map(p=>p.join(',')).join(' '));
      if (zoneEl) {
        zoneEl.setAttribute('x', fromS.zone.x + (toS.zone.x - fromS.zone.x) * e);
        zoneEl.setAttribute('y', fromS.zone.y + (toS.zone.y - fromS.zone.y) * e);
        zoneEl.setAttribute('width',  fromS.zone.w + (toS.zone.w - fromS.zone.w) * e);
        zoneEl.setAttribute('height', fromS.zone.h + (toS.zone.h - fromS.zone.h) * e);
      }
      if (tt < 1) requestAnimationFrame(step);
      else {
        if (lblMP)  lblMP.textContent = toS.maxProfitTxt;
        if (lblMLL) lblMLL.textContent = toS.maxLossTxt;
        if (lblMLR) lblMLR.textContent = toS.maxLossTxt;
        if (stratNameEl) stratNameEl.textContent = toS.name;
        // Refresh current X-position P/L using new strategy
        if (line) {
          const cx = parseFloat(line.getAttribute('x1')) || 360;
          setX(cx);
        }
      }
    };
    requestAnimationFrame(step);
  };
  const priceFromX = (x) => 528 + (x - 360) / 16;
  const fmtPct = (v) => (v >= 0 ? '+' : '-') + Math.abs(v).toFixed(0) + '%';

  let manual = false;
  const setX = (x, opts) => {
    x = Math.max(X_MIN, Math.min(X_MAX, x));
    if (line) { line.setAttribute('x1', x); line.setAttribute('x2', x); }
    if (grip) grip.setAttribute('cx', x);
    if (lbl)  { lbl.setAttribute('x', x + 4); lbl.textContent = 'SPY · ' + priceFromX(x).toFixed(2); }
    if (!opts || opts.pl !== false) {
      const pct = payoffPct(x);
      const txt = fmtPct(pct);
      if (plEl)  { plEl.textContent  = txt; plEl.style.color  = pct >= 0 ? 'var(--accent)' : 'var(--neg)'; }
      if (netEl) { netEl.textContent = txt; netEl.style.color = pct >= 0 ? 'var(--pos)'    : 'var(--neg)'; }
    }
  };

  const clientToSvgX = (clientX) => {
    if (!heroSvg) return 360;
    const r = heroSvg.getBoundingClientRect();
    return ((clientX - r.left) / r.width) * 720;
  };

  let dragging = false;
  const onDown = (e) => {
    dragging = true; manual = true;
    sch?.classList.add('dragging','touched');
    grip?.classList.add('dragging');
    if (window.__setPLSpeed) window.__setPLSpeed(99999999); // pause auto tick
    setX(clientToSvgX(e.clientX || e.touches?.[0]?.clientX));
    e.preventDefault();
  };
  const onMove = (e) => {
    if (!dragging) return;
    setX(clientToSvgX(e.clientX || e.touches?.[0]?.clientX));
  };
  const onUp = () => {
    if (!dragging) return;
    dragging = false;
    sch?.classList.remove('dragging');
    grip?.classList.remove('dragging');
  };
  if (drag) drag.addEventListener('mousedown', onDown);
  if (grip) grip.addEventListener('mousedown', onDown);
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
  if (drag) drag.addEventListener('touchstart', onDown, {passive:false});
  window.addEventListener('touchmove', onMove, {passive:false});
  window.addEventListener('touchend', onUp);

  // Hide hint once user actually grabs the line
  if (hint) {
    const hideHint = () => hint.classList.remove('show','persistent');
    drag?.addEventListener('mousedown',  hideHint);
    grip?.addEventListener('mousedown',  hideHint);
    drag?.addEventListener('touchstart', hideHint, {passive:true});
  }
  // Resume the independent P/L auto-tick after a drag completes
  const resumePL = () => { if (window.__setPLSpeed) window.__setPLSpeed(2200); };
  window.addEventListener('mouseup',  resumePL);
  window.addEventListener('touchend', resumePL);

  // ─── Live-market auto-walker (visual-only; P/L stays independent) ──
  let curX = 360;
  let velocity = 0;
  let releaseUntil = 0;
  const walk = () => {
    if (dragging) return;
    if (performance.now() < releaseUntil) return;
    const target = 360;
    const reversion = (target - curX) * 0.0015;
    const noise = (Math.random() - 0.5) * 2.4;
    velocity = velocity * 0.88 + reversion + noise * 0.6;
    velocity = Math.max(-6, Math.min(6, velocity));
    curX += velocity;
    if (curX < X_MIN + 8) { curX = X_MIN + 8; velocity = Math.abs(velocity) * 0.4; }
    if (curX > X_MAX - 8) { curX = X_MAX - 8; velocity = -Math.abs(velocity) * 0.4; }
    setX(curX, {pl:false});  // walker drives the line, NOT the P/L numbers
  };
  setInterval(walk, 90);

  // Sync walker's curX when user grabs / releases the line so it picks up smoothly
  const syncCurX = () => {
    if (line) curX = parseFloat(line.getAttribute('x1')) || curX;
    velocity = 0;
    releaseUntil = performance.now() + 1200;
  };
  window.addEventListener('mouseup',  syncCurX);
  window.addEventListener('touchend', syncCurX);

  // ═══ 3. Gate-flow animation (Sheet 03) ═══════════════
  const gateSvg = document.querySelector('.mech-art svg');
  if (gateSvg) {
    const gates = [...gateSvg.querySelectorAll('.gate-rect')];
    // Path: SCAN → each gate (in row order) → AND → SUBMIT
    const route = [
      {x:240,y:90,  type:'scan'},
      {x:145,y:138, type:'gate', i:0},
      {x:335,y:138, type:'gate', i:1},
      {x:145,y:188, type:'gate', i:2},
      {x:335,y:188, type:'gate', i:3},
      {x:145,y:238, type:'gate', i:4},
      {x:335,y:238, type:'gate', i:5},
      {x:240,y:332, type:'and'},
      {x:240,y:420, type:'submit'},
    ];
    const NS = 'http://www.w3.org/2000/svg';
    const dot = document.createElementNS(NS, 'circle');
    dot.setAttribute('id','gate-flow-dot');
    dot.setAttribute('r','5');
    dot.setAttribute('fill','#ff6b35');
    dot.setAttribute('cx', route[0].x);
    dot.setAttribute('cy', route[0].y);
    dot.setAttribute('opacity','0');
    gateSvg.appendChild(dot);

    const animate = (from, to, ms) => new Promise(res => {
      const t0 = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - t0) / ms);
        const e = 1 - Math.pow(1 - t, 3);
        dot.setAttribute('cx', from.x + (to.x - from.x) * e);
        dot.setAttribute('cy', from.y + (to.y - from.y) * e);
        if (t < 1) requestAnimationFrame(step); else res();
      };
      requestAnimationFrame(step);
    });

    const wait = (ms) => new Promise(r => setTimeout(r, ms));

    const runOnce = async () => {
      gates.forEach(g => g.classList.remove('lit','fail'));
      dot.setAttribute('opacity','1');
      dot.setAttribute('cx', route[0].x);
      dot.setAttribute('cy', route[0].y);

      // ~15% chance the candidate fails out at one of the first 4 gates
      const fails = Math.random() < 0.15;
      const failAt = fails ? 1 + Math.floor(Math.random() * 4) : -1;

      for (let i = 1; i < route.length; i++) {
        const prev = route[i-1], curr = route[i];
        await animate(prev, curr, curr.type === 'and' ? 420 : 320);
        if (curr.type === 'gate') {
          if (i === failAt) {
            gates[curr.i].classList.add('fail');
            // fade dot out
            for (let k = 0; k < 6; k++) {
              dot.setAttribute('opacity', String(1 - k/5));
              await wait(60);
            }
            await wait(900);
            return;
          }
          gates[curr.i].classList.add('lit');
          await wait(120);
        }
        if (curr.type === 'submit') {
          // brief flash
          dot.setAttribute('r','9');
          await wait(180);
          dot.setAttribute('r','5');
          await wait(360);
        }
      }
      dot.setAttribute('opacity','0');
    };

    let gateLoop = null;
    const startGateLoop = () => {
      if (gateLoop) return;
      const tick = async () => {
        await runOnce();
        gateLoop = setTimeout(tick, 2400 + Math.random()*1800);
      };
      tick();
    };
    // start when gate diagram is in view
    const gobs = new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) { startGateLoop(); gobs.unobserve(e.target); } });
    }, { threshold: 0.3 });
    gobs.observe(gateSvg);
  }
})();
} catch (e) { console.error('[landing block 2]', e); }

/* ═══════════════════════════════════════════ */

try {
(() => {
  // ─── Live tape (looped prints) ───────────────────────
  const prints = [
    {bot:'SPK', c:'#5b8fd9', sym:'SPY', strikes:'515P/510P · 540C/545C', credit:'+$1.48', pnl:'+52%',  cls:'pos'},
    {bot:'INF', c:'#e74c3c', sym:'SPY', strikes:'523P/518P · 533C/538C', credit:'+$1.62', pnl:'+24%',  cls:'pos'},
    {bot:'FLM', c:'#f5a623', sym:'SPY', strikes:'521P/516P',             credit:'+$0.87', pnl:'+58%',  cls:'pos'},
    {bot:'INF', c:'#e74c3c', sym:'SPY', strikes:'525P/520P · 531C/536C', credit:'+$1.18', pnl:'+41%',  cls:'pos'},
    {bot:'SPK', c:'#5b8fd9', sym:'SPY', strikes:'513P/508P · 538C/543C', credit:'+$1.34', pnl:'+50%',  cls:'pos'},
    {bot:'INF', c:'#e74c3c', sym:'SPY', strikes:'526P/521P · 531C/536C', credit:'+$0.92', pnl:'+38%',  cls:'pos'},
    {bot:'FLM', c:'#f5a623', sym:'SPY', strikes:'519C/524C',             credit:'+$0.74', pnl:'+62%',  cls:'pos'},
    {bot:'SPK', c:'#5b8fd9', sym:'SPY', strikes:'517P/512P · 539C/544C', credit:'+$1.55', pnl:'+45%',  cls:'pos'},
  ];
  const track = document.getElementById('tape-track');
  const renderPrint = p => `
    <div class="tape-print">
      <span class="tape-bot" style="color:${p.c}">${p.bot}</span>
      <span style="color:${p.c}">▸</span>
      <span class="sym">${p.sym}</span>
      <span class="strikes">${p.strikes}</span>
      <span class="credit">CREDIT ${p.credit}</span>
      <span class="pnl ${p.cls}">${p.pnl}</span>
    </div>`;
  // duplicate for seamless loop
  track.innerHTML = [...prints, ...prints].map(renderPrint).join('');

  // ─── Cinders + Flares (forge edge) ────────────────────────────
  const populateCinders = (cinders) => {
    if (!cinders) return;
    const N = 12;
    for (let i = 0; i < N; i++) {
      const c = document.createElement('div');
      c.className = 'cinder';
      const left = 8 + (i * 84 / N) + (Math.random()*8 - 4);
      const drift = (Math.random()*80 - 40) + 'px';
      const dur = (3.6 + Math.random()*3).toFixed(2) + 's';
      const delay = (i * 0.35 + Math.random()*0.6).toFixed(2) + 's';
      c.style.left = left + '%';
      c.style.setProperty('--drift', drift);
      c.style.animationDuration = dur;
      c.style.animationDelay = delay;
      cinders.appendChild(c);
    }
    // Brighter "flares" — fewer but more dramatic
    const F = 4;
    for (let i = 0; i < F; i++) {
      const f = document.createElement('div');
      f.className = 'flare';
      f.style.left = (20 + i*20 + Math.random()*8) + '%';
      f.style.setProperty('--drift', (Math.random()*60 - 30) + 'px');
      f.style.animationDuration = (5.5 + Math.random()*2.5).toFixed(2) + 's';
      f.style.animationDelay = (i * 1.6 + Math.random()*1.2).toFixed(2) + 's';
      cinders.appendChild(f);
    }
  };
  populateCinders(document.getElementById('cinders'));
  populateCinders(document.getElementById('cinders-hero'));

  // ─── Hero CONTROLS strip (DTE / Width / Delta → POP / R:R / Credit) ──
  (() => {
    const state = { dte: 14, width: 5, delta: 16 };
    const dteChips = document.querySelectorAll('#ctrl-dte .cchip');
    const wVal = document.getElementById('w-val');
    const wDn  = document.getElementById('w-dn');
    const wUp  = document.getElementById('w-up');
    const dTrack = document.getElementById('d-track');
    const dFill  = document.getElementById('d-fill');
    const dThumb = document.getElementById('d-thumb');
    const dVal   = document.getElementById('d-val');
    const popEl  = document.getElementById('pop-val');
    const rrEl   = document.getElementById('rr-val');
    const crEl   = document.getElementById('cr-val');

    const recompute = () => {
      // POP ≈ 100 - 2*delta
      const pop = Math.max(35, Math.min(96, Math.round(100 - state.delta * 2 - (14 - state.dte) * 0.2)));
      // Credit scales with delta and width and dte
      const credit = Math.max(0.05, ((state.delta / 16) * (state.width / 5) * (Math.max(1, state.dte) / 14) * 1.50));
      // Max loss = width - credit (per share, x100 = per contract)
      const maxLoss = Math.max(0.1, state.width - credit);
      const rr = (credit / maxLoss);

      popEl.textContent = pop + '%';
      crEl.textContent = '$' + credit.toFixed(2);
      rrEl.textContent = '1 : ' + (1 / Math.max(0.05, rr)).toFixed(1);

      // ─── Update schematic chart geometry ───
      const centerPx = 360;
      // Short-strike distance from center: larger delta → closer to center
      const shortOffsetPx = Math.max(40, Math.min(180, 120 + (16 - state.delta) * 5));
      // Wing distance (long from short): scales with width
      const wingOffsetPx = Math.max(10, Math.min(120, state.width * 8));

      const sputX  = centerPx - shortOffsetPx;
      const scallX = centerPx + shortOffsetPx;
      const lputX  = sputX  - wingOffsetPx;
      const lcallX = scallX + wingOffsetPx;

      const set = (id, attr, val) => {
        const el = document.getElementById(id);
        if (el) el.setAttribute(attr, val);
      };
      set('sput-dot',   'cx', sputX);
      set('scall-dot',  'cx', scallX);
      set('lput-dot',   'cx', lputX);
      set('lcall-dot',  'cx', lcallX);
      set('profit-zone','x',  sputX);
      set('profit-zone','width', scallX - sputX);
      set('zone-top',   'x1', sputX);
      set('zone-top',   'x2', scallX);

      // Update payoff curve polyline
      const curve = document.getElementById('payoff-curve');
      if (curve) {
        const pts = [
          [40, 360], [lputX, 360], [sputX, 180],
          [centerPx, 180], [scallX, 180], [lcallX, 360], [680, 360]
        ].map(p => p.join(',')).join(' ');
        curve.setAttribute('points', pts);
      }

      // Update DTE in the schematic stamp
      const stamp = document.querySelector('.sch-stamp em');
      if (stamp) stamp.textContent = 'SPY ' + state.dte + 'DTE';
    };

    // DTE chips
    dteChips.forEach(c => c.addEventListener('click', () => {
      dteChips.forEach(x => x.classList.remove('on'));
      c.classList.add('on');
      state.dte = parseInt(c.dataset.dte, 10);
      recompute();
    }));

    // Width stepper
    const setW = (v) => {
      state.width = Math.max(1, Math.min(20, v));
      wVal.textContent = state.width;
      recompute();
    };
    wDn?.addEventListener('click', () => setW(state.width - 1));
    wUp?.addEventListener('click', () => setW(state.width + 1));

    // Delta slider
    const setD = (pct) => {
      const clamped = Math.max(0, Math.min(1, pct));
      state.delta = Math.round(5 + clamped * 30); // 5..35
      dFill.style.width = (clamped * 100) + '%';
      dThumb.style.left = (clamped * 100) + '%';
      dVal.textContent = '.' + String(state.delta).padStart(2, '0');
      recompute();
    };
    let dragging = false;
    const onMove = (clientX) => {
      const r = dTrack.getBoundingClientRect();
      setD((clientX - r.left) / r.width);
    };
    dTrack?.addEventListener('mousedown', e => { dragging = true; onMove(e.clientX); e.preventDefault(); });
    window.addEventListener('mousemove', e => { if (dragging) onMove(e.clientX); });
    window.addEventListener('mouseup', () => dragging = false);
    dTrack?.addEventListener('touchstart', e => { dragging = true; onMove(e.touches[0].clientX); }, {passive:true});
    dTrack?.addEventListener('touchmove', e => { if (dragging) onMove(e.touches[0].clientX); }, {passive:true});
    dTrack?.addEventListener('touchend', () => dragging = false);

    // initial: thumb at 36% to match CSS default
    setD(0.36);
  })();

  // ─── BENCH: live bot state cycling ────────────────────────────
  (() => {
    const cycles = {
      spark:   ['<span class="sdot live"></span>OPEN · <b class="pos">+47%</b>',
                '<span class="sdot live"></span>OPEN · <b class="pos">+52%</b>',
                '<span class="sdot live"></span>OPEN · <b class="pos">+58%</b>',
                '<span class="sdot live"></span>CLOSING · <b class="pos">+50%</b>',
                '<span class="sdot stand"></span>CLOSED · <b class="pos">+50% ✓</b>',
                '<span class="sdot scan"></span>SCANNING · <b>NEXT FILL</b>'],
      flame:   ['<span class="sdot scan"></span>SCANNING · <b>GATE 2/3</b>',
                '<span class="sdot scan"></span>SCANNING · <b>GATE 3/3</b>',
                '<span class="sdot live"></span>FILLED · <b class="pos">+$0.18</b>',
                '<span class="sdot live"></span>OPEN · <b class="pos">+12%</b>',
                '<span class="sdot live"></span>OPEN · <b class="pos">+24%</b>'],
      inferno: ['<span class="sdot armed"></span>ARMED · <b>10:30–14:30</b>',
                '<span class="sdot scan"></span>SETUP · <b>VIX 13.4</b>',
                '<span class="sdot live"></span>OPEN · <b class="pos">+18%</b>',
                '<span class="sdot live"></span>OPEN · <b class="pos">+12%</b>',
                '<span class="sdot armed"></span>HOLDING · <b>14:08</b>'],
      flare:   ['<span class="sdot scan"></span>STAGING · <b>1–3/DAY</b>',
                '<span class="sdot armed"></span>SIGNAL · <b>SPY ↗</b>',
                '<span class="sdot live"></span>OPEN · <b class="pos">+34%</b>',
                '<span class="sdot live"></span>OPEN · <b class="pos">+71%</b>',
                '<span class="sdot stand"></span>CLOSED · <b class="pos">+75% ✓</b>'],
      blaze:   ['<span class="sdot stand"></span>STANDBY · <b>OVERNIGHT</b>',
                '<span class="sdot scan"></span>STAGING · <b>SETUP CHK</b>',
                '<span class="sdot armed"></span>QUEUED · <b>15:55 ET</b>',
                '<span class="sdot live"></span>OPEN · <b class="pos">+8%</b>'],
    };
    const idx = { spark:0, flame:0, inferno:0, flare:0, blaze:0 };
    const tick = (bot) => {
      const el = document.querySelector(`.bp[data-bot="${bot}"] [data-state]`);
      if (!el) return;
      el.innerHTML = cycles[bot][idx[bot] % cycles[bot].length];
      // Soft flash on update
      el.style.transition = 'opacity .25s';
      el.style.opacity = '.35';
      requestAnimationFrame(() => requestAnimationFrame(() => { el.style.opacity = '1'; }));
      idx[bot]++;
    };
    // Initial render
    Object.keys(cycles).forEach(tick);
    // Stagger updates so they don't all tick at once
    const stagger = { spark: 2800, flame: 3600, inferno: 4400, flare: 5200, blaze: 6000 };
    Object.keys(cycles).forEach(bot => {
      setTimeout(() => {
        tick(bot);
        setInterval(() => tick(bot), 4500 + Math.random() * 2500);
      }, stagger[bot]);
    });
  })();

  // ─── Animated counters (anvil stats) ─────────────────
  const easeOutCubic = t => 1 - Math.pow(1 - t, 3);
  const animateCounter = (el) => {
    const target = parseFloat(el.dataset.target);
    const isFloat = !Number.isInteger(target);
    const dur = 1400;
    const start = performance.now();
    const sup = el.querySelector('sup');
    const supHTML = sup ? sup.outerHTML : '';
    const tick = (now) => {
      const t = Math.min(1, (now - start) / dur);
      const v = target * easeOutCubic(t);
      const display = isFloat ? v.toFixed(target < 10 ? 2 : 1) : Math.round(v);
      el.innerHTML = display + supHTML;
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };
  const counters = document.querySelectorAll('.ac-val[data-target]');
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        animateCounter(e.target);
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.4 });
  counters.forEach(c => obs.observe(c));

  // ─── Live P/L tick (% of credit) ───────────────────────
  const plEl  = document.getElementById('pl-val');
  const netEl = document.getElementById('net-val');
  let pl = 47; // % of credit collected
  const tickPL = () => {
    pl += (Math.random() - 0.45) * 4;
    if (pl < 10)  pl = 10;
    if (pl > 75)  pl = 75;
    const sign = pl >= 0 ? '+' : '-';
    const txt = sign + Math.abs(pl).toFixed(0) + '%';
    plEl.textContent = txt;
    plEl.style.color = pl >= 0 ? 'var(--accent)' : 'var(--neg)';
    if (netEl) {
      netEl.textContent = txt;
      netEl.style.color = pl >= 0 ? 'var(--pos)' : 'var(--neg)';
    }
  };
  let plTimer = setInterval(tickPL, 2200);
  window.__setPLSpeed = (ms) => { clearInterval(plTimer); plTimer = setInterval(tickPL, ms); };
})();
} catch (e) { console.error('[landing block 3]', e); }

/* ═══════════════════════════════════════════ */

try {
(() => {
  // ═══ STRATEGY CHIPS ═══════════════════════════════════
  document.querySelectorAll('.strat-chips .chip').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.strat-chips .chip').forEach(b => b.classList.remove('on'));
      btn.classList.add('on');
      if (window.__setStrategy) window.__setStrategy(btn.dataset.strat);
    });
  });

  // ═══ HOVER SCRUBBER ══════════════════════════════════
  const heroSvg = document.querySelector('.schematic svg');
  const dragArea = document.getElementById('drag-area');
  const sch = document.querySelector('.schematic');
  const readout = document.getElementById('scrub-readout');
  if (heroSvg && dragArea && readout) {
    const NS = 'http://www.w3.org/2000/svg';
    const reticle = document.createElementNS(NS,'line');
    reticle.setAttribute('y1','60'); reticle.setAttribute('y2','380');
    reticle.setAttribute('stroke','rgba(255,107,53,0.55)');
    reticle.setAttribute('stroke-width','1');
    reticle.setAttribute('stroke-dasharray','3,3');
    reticle.setAttribute('opacity','0');
    reticle.setAttribute('pointer-events','none');
    heroSvg.appendChild(reticle);

    const showAt = (clientX, clientY) => {
      if (window.__isDragging && window.__isDragging()) return;
      const r = heroSvg.getBoundingClientRect();
      const x = ((clientX - r.left) / r.width) * 720;
      if (x < 40 || x > 680) { hide(); return; }
      reticle.setAttribute('x1', x); reticle.setAttribute('x2', x);
      reticle.setAttribute('opacity','1');
      const pct = window.__payoffPct ? window.__payoffPct(x) : 0;
      const price = 528 + (x - 360) / 16;
      const sign = pct >= 0 ? '+' : '−';
      readout.innerHTML = `<div class="pct ${pct<0?'neg':''}">${sign}${Math.abs(pct).toFixed(0)}%</div><div class="sub">If SPY closes ${price.toFixed(2)}</div>`;
      const schR = sch.getBoundingClientRect();
      readout.style.left = (clientX - schR.left) + 'px';
      readout.style.top  = (clientY - schR.top)  + 'px';
      readout.classList.add('show');
    };
    const hide = () => {
      reticle.setAttribute('opacity','0');
      readout.classList.remove('show');
    };
    sch.addEventListener('mousemove', e => {
      const svgR = heroSvg.getBoundingClientRect();
      if (e.clientX < svgR.left || e.clientX > svgR.right || e.clientY < svgR.top || e.clientY > svgR.bottom) { hide(); return; }
      showAt(e.clientX, e.clientY);
    });
    sch.addEventListener('mouseleave', hide);
  }

  // ═══ BOT SPARKLINES (injected) ═══════════════════════
  const sparkPaths = {
    spark:   'M0,30 L20,28 L40,29 L60,26 L80,24 L100,22 L120,21 L140,18 L160,15 L180,14 L200,11 L220,8 L240,6',
    flame:   'M0,30 L18,25 L36,28 L54,21 L72,24 L90,18 L108,22 L126,15 L144,19 L162,12 L180,16 L198,9 L216,13 L240,6',
    inferno: 'M0,30 L15,27 L30,33 L45,22 L60,28 L75,18 L90,24 L105,12 L120,20 L135,8 L150,18 L165,4 L180,16 L195,2 L210,14 L225,3 L240,8'
  };
  const sparkStats = { spark:'78% WIN', flame:'71% WIN', inferno:'62% WIN' };
  document.querySelectorAll('.bot-art').forEach(card => {
    const name = (card.querySelector('.b-name')?.textContent || '').trim().toLowerCase();
    const d = sparkPaths[name] || sparkPaths.spark;
    const stat = sparkStats[name] || '—';
    const html = `<div class="b-spark"><svg viewBox="0 0 240 36" preserveAspectRatio="none"><path class="curve" d="${d}"/></svg><div class="b-spark-foot"><span>30-DAY EQUITY</span><b>${stat}</b></div></div>`;
    const pulse = card.querySelector('.b-pulse');
    if (pulse) pulse.insertAdjacentHTML('afterend', html);
  });

  // ═══ FIND-MY-BOT QUIZ ════════════════════════════════
  const botsSheet = document.querySelector('.bots-sheet');
  const grid = botsSheet?.querySelector('.bots-grid');
  if (botsSheet && grid) {
    grid.insertAdjacentHTML('beforebegin', `
      <div class="bots-prebar">
        <span>NOT SURE WHICH BOT? <em>Calibrate in 30 seconds.</em></span>
        <button class="quiz-cta" id="quiz-cta">▸ FIND MY BOT</button>
      </div>
      <section class="quiz" id="quiz" aria-label="Bot calibration">
        <div class="quiz-head">
          <div class="quiz-eyebrow">CALIBRATION · 30 SECONDS · ANONYMOUS</div>
          <button class="quiz-x" id="quiz-x" aria-label="Close">×</button>
        </div>
        <h3>Find your bot.</h3>
        <p class="quiz-sub">Three quick choices. We'll point you at the closest match.</p>
        <div class="quiz-q" data-q="style">
          <div class="quiz-lbl">PRIMARY GOAL</div>
          <div class="quiz-opts">
            <button data-v="income">Income / theta</button>
            <button data-v="balanced">Balanced</button>
            <button data-v="growth">Faster compounding</button>
          </div>
        </div>
        <div class="quiz-q" data-q="hold">
          <div class="quiz-lbl">PREFERRED HOLD</div>
          <div class="quiz-opts">
            <button data-v="month">Weeks</button>
            <button data-v="week">A few days</button>
            <button data-v="day">Intraday</button>
          </div>
        </div>
        <div class="quiz-q" data-q="risk">
          <div class="quiz-lbl">RISK PER TRADE</div>
          <div class="quiz-opts">
            <button data-v="low">≤ 0.5% NAV</button>
            <button data-v="med">~ 1% NAV</button>
            <button data-v="high">~ 2% NAV</button>
          </div>
        </div>
        <div class="quiz-result" id="quiz-result"></div>
      </section>
    `);

    const quiz = document.getElementById('quiz');
    document.getElementById('quiz-cta').addEventListener('click', () => quiz.classList.toggle('open'));
    document.getElementById('quiz-x').addEventListener('click', () => quiz.classList.remove('open'));

    const scoreMap = {
      style:{income:{spark:2,flame:1,inferno:0}, balanced:{spark:1,flame:2,inferno:1}, growth:{spark:0,flame:1,inferno:2}},
      hold: {month:{spark:2,flame:1,inferno:0},  week:{spark:1,flame:2,inferno:1},     day:{spark:0,flame:1,inferno:2}},
      risk: {low:{spark:2,flame:1,inferno:0},    med:{spark:1,flame:2,inferno:1},      high:{spark:0,flame:1,inferno:2}}
    };
    const answers = {};
    quiz.querySelectorAll('.quiz-q').forEach(qEl => {
      const q = qEl.dataset.q;
      qEl.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', () => {
          qEl.querySelectorAll('button').forEach(b => b.classList.remove('on'));
          btn.classList.add('on');
          answers[q] = btn.dataset.v;
          if (Object.keys(answers).length === 3) computeMatch();
        });
      });
    });

    const labels = { spark:'Spark', flame:'Flame', inferno:'Inferno' };
    const blurbs = {
      spark:'Patient theta. Wide wings, low touch — the bot to learn the engine on.',
      flame:'Tactical short-term spreads. For traders who already trade theta.',
      inferno:'0DTE iron condors with tight bands. Experienced operators only.'
    };
    function computeMatch() {
      const totals = {spark:0, flame:0, inferno:0};
      Object.keys(answers).forEach(q => {
        const m = scoreMap[q]?.[answers[q]];
        if (m) Object.keys(m).forEach(k => totals[k] += m[k]);
      });
      const ranked = Object.entries(totals).sort((a,b) => b[1]-a[1]).map(e => e[0]);
      // Reorder bot cards via flex/grid order
      grid.querySelectorAll('.bot-art').forEach(card => {
        const n = (card.querySelector('.b-name')?.textContent || '').trim().toLowerCase();
        const idx = ranked.indexOf(n);
        card.style.order = idx >= 0 ? idx : 9;
        card.classList.toggle('match', idx === 0);
      });
      const top = ranked[0];
      const result = document.getElementById('quiz-result');
      result.innerHTML = `<div>Best match: <b>${labels[top].toUpperCase()}</b></div><div style="margin-top:6px;color:var(--ink-3)">${blurbs[top]}</div>`;
      result.classList.add('show');
    }
  }
})();
} catch (e) { console.error('[landing block 4]', e); }

/* ═══════════════════════════════════════════ */

try {
(() => {
  // Forge-edge embers for #cinders (preserves the 7-ember look the removed
  // Tweaks panel produced on load; runs just after the base populateCinders).
  const apply = () => {
    const root = document.getElementById('cinders');
    if (!root) return;
    root.innerHTML = '';
    const N = 7;
    for (let i = 0; i < N; i++) {
      const c = document.createElement('div');
      c.className = 'cinder';
      c.style.left = (12 + (i * 76 / N) + (Math.random()*6 - 3)) + '%';
      c.style.setProperty('--drift', (Math.random()*60 - 30) + 'px');
      c.style.animationDuration = (4 + Math.random()*3).toFixed(2) + 's';
      c.style.animationDelay = (i * 0.6 + Math.random()*0.5).toFixed(2) + 's';
      root.appendChild(c);
    }
  };
  setTimeout(apply, 80);
})();
} catch (e) { console.error('[landing block 5]', e); }
})();
