// AUTO-GENERATED from ~/Downloads/landing.html by _split_landing.mjs — do not hand-edit.
// Body markup of the IronForge landing page (all <style>/<script> stripped; anvil img path
// rewritten assets/anvil-iso.png -> /anvil-iso.png; design-tool Tweaks panel removed and its
// eyebrow text baked in). Rendered via dangerouslySetInnerHTML.
export const LANDING_MARKUP = `<div class="topbar" id="topbar" style="display:none"></div>

<!-- TITLE BLOCK -->
<header class="titleblock">
  <div class="tb-cell">
    <div class="brand">
      <span class="brand-mark">IF</span>
      <div class="brand-text">
        <span class="brand-name">IRONFORGE</span>
        <span class="brand-sub">// AUTONOMOUS · TRADIER NATIVE</span>
      </div>
    </div>
  </div>
  <div class="tb-cell" style="padding:0">
    <nav class="nav">
      <a href="#" class="curr">SHEET 01 / FORGE</a>
      <a href="#bots">02 / BOTS</a>
      <a href="#flow">03 / HOW IT WORKS</a>
      <a href="#mech">04 / MECHANICS</a>
    </nav>
  </div>
  <div class="tb-cell tb-actions">
    <button class="btn" onclick="document.getElementById('proof').scrollIntoView({behavior:'smooth'})">EARLY ACCESS</button>
    <button class="btn primary" onclick="document.getElementById('proof').scrollIntoView({behavior:'smooth'})">▸ JOIN WAITLIST</button>
  </div>
</header>

<!-- SHEET RULE -->
<div class="sheet-rule">
  <span class="sh">DRAWING · IF-001 / SHEET 01 OF 04</span>
  <div class="ln"></div>
  <span>SCALE 1:1 · DTE 14 · SPY 528.41 ▴</span>
  <span class="stamp"><span class="live"></span> LIVE · REV B</span>
</div>

<!-- HERO / SHEET 01 -->
<section class="hero">
  <div class="hero-l">
    <div class="hero-eyebrow"><span class="dot"></span> THE FORGE IS LIT</div>
    <div class="hero-meta">
      <span>SHEET <b>01 / 04</b></span>
      <span>FORGE / SPY / SET-AND-FORGET</span>
      <span>REV <b>B</b></span>
    </div>
    <h1>Forge <em>Discipline.</em><br/>Execute <em>Precision.</em></h1>
    <p class="plain">Connect your brokerage. Pick a risk level. <b>Five vetted bots</b> run defined-risk options trades on SPY for you — every position has a <b>capped max loss</b>, gets sized automatically, and exits by rule.</p>
    <p class="lede">
      For people who want disciplined exposure to options without becoming
      a full-time trader. Your cash stays in <b>your Tradier account</b>. We never hold it.
      Discipline scales. Emotion doesn't.
    </p>
    <div class="hero-cta">
      <button class="btn primary lg" onclick="document.getElementById('proof').scrollIntoView({behavior:'smooth'})">▸ JOIN THE WAITLIST</button>
      <button class="btn lg" onclick="document.getElementById('mech').scrollIntoView({behavior:'smooth'})">↓ HOW IT WORKS</button>
    </div>
    <div class="keys-list">
      <div class="k"><div class="lbl">AUTOPILOT</div><div class="val">Bots trade <em>// you don't lift a finger</em></div></div>
      <div class="k"><div class="lbl">CAPPED LOSS</div><div class="val">Every trade <em>// fixed max risk</em></div></div>
      <div class="k"><div class="lbl">YOUR MONEY</div><div class="val">Stays at Tradier <em>// we never hold it</em></div></div>
      <div class="k"><div class="lbl">CHECK-IN</div><div class="val">~5 min / mo <em>// if you feel like it</em></div></div>
    </div>
  </div>

  <!-- Iron condor schematic (with live readout) -->
  <div class="hero-r">
  <div class="schematic">
    <span class="sch-corner tl"></span><span class="sch-corner tr"></span>
    <span class="sch-corner bl"></span><span class="sch-corner br"></span>
    <div class="sch-stamp">FIG. 01 · <span id="sch-strat-name">IRON CONDOR</span> / <em>SPY 14DTE</em> · ORTHOGRAPHIC</div>
    <div class="sch-readout"><span class="pulse-dot"></span>LIVE · OPEN <b>02</b> · NET <b id="net-val" style="color:var(--pos)">+47%</b></div>
    <div class="strat-chips" role="tablist" aria-label="Strategy">
      <button class="chip on" data-strat="condor">CONDOR</button>
      <button class="chip" data-strat="spread">SPREAD</button>
    </div>
    <div class="scrub-readout" id="scrub-readout"></div>
    <svg viewBox="0 0 720 460" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <pattern id="dotgrid" width="20" height="20" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="0.6" fill="#1a1612"/>
        </pattern>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="#ff6b35"/>
        </marker>
        <linearGradient id="zoneFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ff6b35" stop-opacity="0.18"/>
          <stop offset="100%" stop-color="#ff6b35" stop-opacity="0.02"/>
        </linearGradient>
      </defs>
      <rect width="720" height="460" fill="url(#dotgrid)"/>

      <line x1="40" y1="320" x2="680" y2="320" stroke="#3a342b" stroke-width="1"/>
      <text x="40" y="340" font-size="9" letter-spacing="1.5">PRICE →</text>
      <text x="660" y="340" font-size="9" letter-spacing="1.5">$</text>

      <rect id="profit-zone" x="240" y="180" width="240" height="140" fill="url(#zoneFill)"/>
      <line id="zone-top" x1="240" y1="180" x2="480" y2="180" stroke="#ff6b35" stroke-width="1.5"/>

      <polyline id="payoff-curve" points="40,360 200,360 240,180 360,180 480,180 520,360 680,360"
                fill="none" stroke="#e8e2d4" stroke-width="1.5"/>

      <circle id="sput-dot" cx="240" cy="180" r="4" fill="#ff6b35">
        <animate attributeName="r" values="4;6;4" dur="2.4s" repeatCount="indefinite"/>
      </circle>
      <circle id="scall-dot" cx="480" cy="180" r="4" fill="#ff6b35">
        <animate attributeName="r" values="4;6;4" dur="2.4s" repeatCount="indefinite" begin="1.2s"/>
      </circle>
      <circle id="lput-dot"  cx="200" cy="360" r="3.5" fill="none" stroke="#7a7468" stroke-width="1.5"/>
      <circle id="lcall-dot" cx="520" cy="360" r="3.5" fill="none" stroke="#7a7468" stroke-width="1.5"/>

      <line id="price-line" x1="360" y1="60" x2="360" y2="380" stroke="#3a342b" stroke-dasharray="2,4"/>
      <circle id="price-grip" cx="360" cy="60" r="5" fill="#ff6b35" stroke="#1a0a02" stroke-width="1.5"/>
      <text id="spy-label" x="364" y="54" fill="#ff6b35" font-size="10" font-weight="500">SPY · 528.41</text>
      <rect id="drag-area" x="40" y="40" width="640" height="380" fill="transparent" style="cursor:ew-resize"/>

      <line x1="200" y1="395" x2="240" y2="395" stroke="#ff6b35" stroke-width="0.8" marker-start="url(#arr)" marker-end="url(#arr)"/>
      <text x="220" y="410" fill="#ff6b35" font-size="9" text-anchor="middle">5.0</text>
      <line x1="480" y1="395" x2="520" y2="395" stroke="#ff6b35" stroke-width="0.8" marker-start="url(#arr)" marker-end="url(#arr)"/>
      <text x="500" y="410" fill="#ff6b35" font-size="9" text-anchor="middle">5.0</text>
      <line x1="240" y1="425" x2="480" y2="425" stroke="#a8a092" stroke-width="0.8" marker-start="url(#arr)" marker-end="url(#arr)"/>
      <text x="360" y="440" fill="#a8a092" font-size="9" text-anchor="middle">PROFIT ZONE · 24.0</text>

      <line x1="240" y1="180" x2="120" y2="120" stroke="#ff6b35" stroke-width="0.7"/>
      <circle cx="120" cy="120" r="2" fill="#ff6b35"/>
      <text x="60" y="108" fill="#ff6b35" font-size="9">SHORT PUT</text>
      <text x="60" y="120" fill="#a8a092" font-size="8">523 · Δ 0.16</text>

      <line x1="200" y1="360" x2="80" y2="220" stroke="#7a7468" stroke-width="0.7"/>
      <circle cx="80" cy="220" r="2" fill="#7a7468"/>
      <text x="48" y="208" fill="#a8a092" font-size="9">LONG PUT</text>
      <text x="48" y="220" fill="#5a5447" font-size="8">518 · WING</text>

      <line x1="480" y1="180" x2="610" y2="120" stroke="#ff6b35" stroke-width="0.7"/>
      <circle cx="610" cy="120" r="2" fill="#ff6b35"/>
      <text x="610" y="108" fill="#ff6b35" font-size="9" text-anchor="end">SHORT CALL</text>
      <text x="610" y="120" fill="#a8a092" font-size="8" text-anchor="end">533 · Δ 0.16</text>

      <line x1="520" y1="360" x2="650" y2="220" stroke="#7a7468" stroke-width="0.7"/>
      <circle cx="650" cy="220" r="2" fill="#7a7468"/>
      <text x="675" y="208" fill="#a8a092" font-size="9" text-anchor="end">LONG CALL</text>
      <text x="675" y="220" fill="#5a5447" font-size="8" text-anchor="end">538 · WING</text>

      <text id="lbl-max-profit" x="360" y="170" fill="#e8e2d4" font-size="10" text-anchor="middle">MAX PROFIT · +100% credit · $150</text>
      <text id="lbl-max-loss-l" x="40" y="378" fill="#5a5447" font-size="8">MAX LOSS · -233% · -$350</text>
      <text id="lbl-max-loss-r" x="680" y="378" fill="#5a5447" font-size="8" text-anchor="end">MAX LOSS · -233% · -$350</text>
    </svg>
    <div class="pl-bar">
      <div class="lbl">CURRENT P/L · % CREDIT</div>
      <div class="v" id="pl-val">+47%</div>
    </div>
    <div class="legend">
      <span><b>━━</b>  SHORT STRIKE</span>
      <span><b>○</b>  LONG STRIKE / WING</span>
      <span><b>▒▒</b>  PROFIT ZONE</span>
    </div>
    <div class="hint show persistent" id="drag-hint">↔ drag the price line</div>
  </div>

  <!-- CONTROLS / interactive strip — fills gap between schematic and bench -->
  <div class="ctrls">
    <span class="sch-corner tl"></span><span class="sch-corner tr"></span>
    <span class="sch-corner bl"></span><span class="sch-corner br"></span>
    <div class="ctrls-row">
      <div class="ctrl-group">
        <span class="cg-lbl">DTE</span>
        <div class="cg-chips" id="ctrl-dte">
          <button class="cchip" data-dte="0">0D</button>
          <button class="cchip" data-dte="7">7D</button>
          <button class="cchip on" data-dte="14">14D</button>
          <button class="cchip" data-dte="30">30D</button>
          <button class="cchip" data-dte="45">45D</button>
        </div>
      </div>
      <div class="ctrl-group">
        <span class="cg-lbl">WIDTH</span>
        <div class="cg-stepper">
          <button class="cstep" id="w-dn" aria-label="decrease">−</button>
          <span class="cval"><b id="w-val">5</b><em>pts</em></span>
          <button class="cstep" id="w-up" aria-label="increase">+</button>
        </div>
      </div>
      <div class="ctrl-group">
        <span class="cg-lbl">DELTA</span>
        <div class="cg-track" id="d-track" role="slider" aria-valuemin="5" aria-valuemax="35" aria-valuenow="16">
          <div class="cg-fill" id="d-fill"></div>
          <div class="cg-thumb" id="d-thumb"></div>
        </div>
        <span class="cval mini"><b id="d-val">.16</b></span>
      </div>
      <div class="ctrl-readout">
        <div class="cr-row"><span>POP</span><b id="pop-val">84%</b></div>
        <div class="cr-row"><span>R:R</span><b id="rr-val">1 : 2.3</b></div>
        <div class="cr-row"><span>CREDIT</span><b id="cr-val" style="color:var(--pos)">$1.50</b></div>
      </div>
    </div>
  </div>

  <!-- BENCH / live bot states — fills space below schematic -->
  <div class="bench">
    <span class="sch-corner tl"></span><span class="sch-corner tr"></span>
    <span class="sch-corner bl"></span><span class="sch-corner br"></span>
    <div class="bench-head">
      <span class="bh-label"><span class="pulse-dot"></span>BENCH · LIVE STATES</span>
      <span class="bh-meta">FIG. 01.2 · 5 UNITS · SPY 14DTE</span>
    </div>
    <div class="bench-grid">
      <div class="bp" data-bot="spark" style="--c:#3b82f6">
        <div class="bp-h"><span class="bp-glyph">◆</span><span class="bp-n">SPARK</span><span class="bp-dte">1D</span></div>
        <div class="bp-state" data-state></div>
        <div class="bp-foot">IC · 528/533 · NEUTRAL</div>
      </div>
      <div class="bp" data-bot="flame" style="--c:#FF5500">
        <div class="bp-h"><span class="bp-glyph">▲</span><span class="bp-n">FLAME</span><span class="bp-dte">2D</span></div>
        <div class="bp-state" data-state></div>
        <div class="bp-foot">BPS · 1σ ENTRIES</div>
      </div>
      <div class="bp" data-bot="inferno" style="--c:#ef4444">
        <div class="bp-h"><span class="bp-glyph">◊</span><span class="bp-n">INFERNO</span><span class="bp-dte">0D</span></div>
        <div class="bp-state" data-state></div>
        <div class="bp-foot">0DTE IC · INTRADAY</div>
      </div>
      <div class="bp" data-bot="flare" style="--c:#f5a623">
        <div class="bp-h"><span class="bp-glyph">◈</span><span class="bp-n">FLARE</span><span class="bp-dte">0D</span></div>
        <div class="bp-state" data-state></div>
        <div class="bp-foot">DEBIT · DIRECTIONAL</div>
      </div>
      <div class="bp" data-bot="blaze" style="--c:#06b6d4">
        <div class="bp-h"><span class="bp-glyph">➤</span><span class="bp-n">BLAZE</span><span class="bp-dte">1D</span></div>
        <div class="bp-state" data-state></div>
        <div class="bp-foot">DEBIT · NEXT-DAY</div>
      </div>
    </div>
    <div class="bench-foot">
      <span>AGGREGATE · OPEN <b>02</b></span><span class="sep">│</span>
      <span>NET P/L <b class="pos">+$159</b></span><span class="sep">│</span>
      <span>BPU <b>23%</b> / 25%</span><span class="sep">│</span>
      <span>DAILY LIMIT <b>$0 / $500</b></span><span class="sep">│</span>
      <span>NEXT WINDOW <b style="color:var(--accent)">10:30 ET</b></span>
    </div>
  </div>
  </div>
</section>

<!-- LIVE TAPE -->
<section class="tape-sheet">
  <div class="tape-label"><span class="dot"></span>FORGE TAPE · LIVE</div>
  <div class="tape-track" id="tape-track"></div>
</section>

<!-- ============ BUILT AROUND CONTROL — safeguards strip ============ -->

<section class="safeguards">
  <div class="safeguards-head">
    <div class="kicker">// 02.5 · BUILT AROUND CONTROL</div>
    <h3>Six safeguards. <em>Always armed.</em></h3>
  </div>
  <div class="sg-grid">
    <div class="sg-cell"><div class="sg-ico">⊘</div><div class="sg-lbl">No withdrawal<br/>permissions</div></div>
    <div class="sg-cell"><div class="sg-ico">⊞</div><div class="sg-lbl">User-authorized<br/>deployment only</div></div>
    <div class="sg-cell"><div class="sg-ico">⟨/⟩</div><div class="sg-lbl">Encrypted API<br/>sessions</div></div>
    <div class="sg-cell"><div class="sg-ico">✓</div><div class="sg-lbl">Risk engine<br/>safeguards</div></div>
    <div class="sg-cell"><div class="sg-ico">▢</div><div class="sg-lbl">Paper deployment<br/>supported</div></div>
    <div class="sg-cell"><div class="sg-ico">≡</div><div class="sg-lbl">Audit logging<br/>enabled</div></div>
  </div>
</section>

<!-- BOTS / SHEET 02 -->
<div class="sheet-rule" id="bots">
  <span class="sh">DRAWING · IF-002 / SHEET 02 OF 04</span>
  <div class="ln"></div>
  <span>BOT LINEUP · EXPLODED VIEW</span>
  <span class="stamp"><span class="live"></span> 5 UNITS · ARMED</span>
</div>
<section class="bots-sheet">
  <div class="bots-grid">
    <a href="/spark" class="bot-art" style="--c:#3b82f6">
      <div class="b-meta"><span>FIG. 02-A · <em>SPARK</em></span><span>1 DTE · <b style="color:#3b82f6">MODERATE</b></span></div>
      <div class="b-name">Spark</div>
      <div class="b-tag">STRUCTURED INCOME · START HERE</div>
      <div class="b-recom">Short-duration iron condors. Daily premium collection, defined risk, lowest touch — the bot to learn the engine on.</div>
      <div class="b-pulse"><span class="dot"></span>STATE · <span class="state">PATIENT</span> · NEXT WIN <span style="color:var(--ink);margin-left:auto">~3D</span></div>
      <div class="b-diag">
        <svg viewBox="0 0 280 160" width="100%" height="100%">
          <line x1="20" y1="120" x2="260" y2="120" stroke="#3a342b"/>
          <polyline points="20,140 80,140 110,70 170,70 200,140 260,140" fill="none" stroke="#3b82f6" stroke-width="1.5"/>
          <circle cx="110" cy="70" r="3" fill="#3b82f6"/>
          <circle cx="170" cy="70" r="3" fill="#3b82f6"/>
          <circle cx="80" cy="140" r="2.5" fill="none" stroke="#7a7468"/>
          <circle cx="200" cy="140" r="2.5" fill="none" stroke="#7a7468"/>
          <line x1="80" y1="148" x2="110" y2="148" stroke="#3b82f6" stroke-width="0.6"/>
          <line x1="170" y1="148" x2="200" y2="148" stroke="#3b82f6" stroke-width="0.6"/>
          <text x="95" y="158" fill="#3b82f6" font-size="7" text-anchor="middle">5w</text>
          <text x="185" y="158" fill="#3b82f6" font-size="7" text-anchor="middle">5w</text>
          <text x="140" y="60" fill="#a8a092" font-size="8" text-anchor="middle">PROFIT</text>
        </svg>
      </div>
      <div class="b-spec">
        <div class="row"><span>STRUCT</span><b>IRON CONDOR</b></div>
        <div class="row"><span>DTE</span><b>1 DAY</b></div>
        <div class="row"><span>BIAS</span><b>NEUTRAL</b></div>
        <div class="row"><span>TARGET</span><b>+50%</b></div>
        <div class="row"><span>STOP</span><b>-200%</b></div>
        <div class="row"><span>FREQ</span><b>DAILY</b></div>
      </div>
    </a>
    <a href="/flame" class="bot-art" style="--c:#FF5500">
      <div class="b-meta"><span>FIG. 02-B · <em>FLAME</em></span><span>2 DTE · <b style="color:#FF5500">MODERATE</b></span></div>
      <div class="b-name">Flame</div>
      <div class="b-tag">PREMIUM SELLING · TACTICAL</div>
      <div class="b-recom">Bull put credit spreads with statistical edge. Captures premium when skew is favorable.</div>
      <div class="b-pulse"><span class="dot"></span>STATE · <span class="state">SCANNING</span> · GATE <span style="color:var(--ink);margin-left:auto">2/3 OK</span></div>
      <div class="b-diag">
        <svg viewBox="0 0 280 160" width="100%" height="100%">
          <line x1="20" y1="120" x2="260" y2="120" stroke="#3a342b"/>
          <polyline points="20,140 100,140 140,70 260,70" fill="none" stroke="#FF5500" stroke-width="1.5"/>
          <circle cx="140" cy="70" r="3" fill="#FF5500"/>
          <circle cx="100" cy="140" r="2.5" fill="none" stroke="#7a7468"/>
          <line x1="100" y1="148" x2="140" y2="148" stroke="#FF5500" stroke-width="0.6"/>
          <text x="120" y="158" fill="#FF5500" font-size="7" text-anchor="middle">5w</text>
          <text x="200" y="62" fill="#a8a092" font-size="8" text-anchor="middle">PROFIT (1-SIDED)</text>
        </svg>
      </div>
      <div class="b-spec">
        <div class="row"><span>STRUCT</span><b>BULL PUT</b></div>
        <div class="row"><span>DTE</span><b>2 DAYS</b></div>
        <div class="row"><span>BIAS</span><b>BULLISH</b></div>
        <div class="row"><span>TARGET</span><b>+60%</b></div>
        <div class="row"><span>STOP</span><b>STRIKE</b></div>
        <div class="row"><span>FREQ</span><b>1–2/DAY</b></div>
      </div>
    </a>
    <a href="/inferno" class="bot-art" style="--c:#ef4444">
      <div class="b-meta"><span>FIG. 02-C · <em>INFERNO</em></span><span>0 DTE · <b style="color:#ef4444">HIGH</b></span></div>
      <div class="b-name">Inferno</div>
      <div class="b-tag">INTRADAY VOLATILITY · EXPERIENCED</div>
      <div class="b-recom">High-frequency 0DTE iron condors for intraday edges. Multiple positions, tight risk controls, fast exits.</div>
      <div class="b-pulse"><span class="dot"></span>STATE · <span class="state">ARMED</span> · WINDOW <span style="color:var(--ink);margin-left:auto">10:30—14:30</span></div>
      <div class="b-diag">
        <svg viewBox="0 0 280 160" width="100%" height="100%">
          <line x1="20" y1="120" x2="260" y2="120" stroke="#3a342b"/>
          <polyline points="20,140 100,140 122,80 158,80 180,140 260,140" fill="none" stroke="#ef4444" stroke-width="1.5"/>
          <circle cx="122" cy="80" r="3" fill="#ef4444"/>
          <circle cx="158" cy="80" r="3" fill="#ef4444"/>
          <circle cx="100" cy="140" r="2.5" fill="none" stroke="#7a7468"/>
          <circle cx="180" cy="140" r="2.5" fill="none" stroke="#7a7468"/>
          <text x="140" y="70" fill="#a8a092" font-size="8" text-anchor="middle">TIGHT</text>
        </svg>
      </div>
      <div class="b-spec">
        <div class="row"><span>STRUCT</span><b>IRON CONDOR</b></div>
        <div class="row"><span>DTE</span><b>0 DAYS</b></div>
        <div class="row"><span>BIAS</span><b>NEUTRAL</b></div>
        <div class="row"><span>TARGET</span><b>+25%</b></div>
        <div class="row"><span>STOP</span><b>-100%</b></div>
        <div class="row"><span>FREQ</span><b>MULTI/DAY</b></div>
      </div>
    </a>
    <a href="/flare" class="bot-art" style="--c:#f5a623">
      <div class="b-meta"><span>FIG. 02-D · <em>FLARE</em></span><span>0 DTE · <b style="color:#f5a623">HIGH</b></span></div>
      <div class="b-name">Flare</div>
      <div class="b-tag">DIRECTIONAL · DEFINED-RISK DEBIT</div>
      <div class="b-recom">Same-day debit spreads. Pay-to-play directional bets with capped risk and asymmetric payoff on intraday momentum.</div>
      <div class="b-pulse"><span class="dot"></span>STATE · <span class="state">SCANNING SETUPS</span> <span style="color:var(--ink);margin-left:auto">1–3 / DAY</span></div>
      <div class="b-diag">
        <svg viewBox="0 0 280 160" width="100%" height="100%">
          <line x1="20" y1="120" x2="260" y2="120" stroke="#3a342b"/>
          <polyline points="20,140 120,140 160,40 260,40" fill="none" stroke="#f5a623" stroke-width="1.5"/>
          <circle cx="120" cy="140" r="2.5" fill="none" stroke="#7a7468"/>
          <circle cx="160" cy="40" r="3" fill="#f5a623"/>
          <text x="200" y="32" fill="#a8a092" font-size="8" text-anchor="middle">CAPPED MAX</text>
          <text x="60" y="112" fill="#a8a092" font-size="8" text-anchor="middle">CAPPED LOSS</text>
        </svg>
      </div>
      <div class="b-spec">
        <div class="row"><span>STRUCT</span><b>DEBIT SPREAD</b></div>
        <div class="row"><span>DTE</span><b>0 DAYS</b></div>
        <div class="row"><span>BIAS</span><b>DIRECTIONAL</b></div>
        <div class="row"><span>TARGET</span><b>+100%</b></div>
        <div class="row"><span>STOP</span><b>-50%</b></div>
        <div class="row"><span>FREQ</span><b>1–3/DAY</b></div>
      </div>
    </a>
    <a href="/blaze" class="bot-art" style="--c:#06b6d4">
      <div class="b-meta"><span>FIG. 02-E · <em>BLAZE</em></span><span>1 DTE · <b style="color:#06b6d4">MODERATE+</b></span></div>
      <div class="b-name">Blaze</div>
      <div class="b-tag">OVERNIGHT DIRECTIONAL · DEBIT</div>
      <div class="b-recom">Next-day debit spreads. Carries a directional thesis into the following session with defined risk and a longer runway than Flare.</div>
      <div class="b-pulse"><span class="dot"></span>STATE · <span class="state">STAGING SETUP</span> <span style="color:var(--ink);margin-left:auto">1–2 / DAY</span></div>
      <div class="b-diag">
        <svg viewBox="0 0 280 160" width="100%" height="100%">
          <line x1="20" y1="120" x2="260" y2="120" stroke="#3a342b"/>
          <polyline points="20,140 110,140 150,40 260,40" fill="none" stroke="#06b6d4" stroke-width="1.5"/>
          <circle cx="110" cy="140" r="2.5" fill="none" stroke="#7a7468"/>
          <circle cx="150" cy="40" r="3" fill="#06b6d4"/>
          <text x="200" y="32" fill="#a8a092" font-size="8" text-anchor="middle">CAPPED MAX</text>
          <text x="60" y="112" fill="#a8a092" font-size="8" text-anchor="middle">CAPPED LOSS</text>
        </svg>
      </div>
      <div class="b-spec">
        <div class="row"><span>STRUCT</span><b>DEBIT SPREAD</b></div>
        <div class="row"><span>DTE</span><b>1 DAY</b></div>
        <div class="row"><span>BIAS</span><b>DIRECTIONAL</b></div>
        <div class="row"><span>TARGET</span><b>+75%</b></div>
        <div class="row"><span>STOP</span><b>-50%</b></div>
        <div class="row"><span>FREQ</span><b>1–2/DAY</b></div>
      </div>
    </a>
  </div>
</section>

<!-- ============ STRATEGY COMPARISON TABLE ============ -->

<section class="cmp-sheet">
  <div class="cmp-head">
    <div class="kicker">// 02.7 · STRATEGY COMPARISON</div>
    <h3>Four engines. <em>One discipline.</em></h3>
  </div>
  <div class="cmp-wrap">
    <table class="cmp">
      <thead>
        <tr><th>Feature</th><th class="bot-h c-spk">SPARK</th><th class="bot-h c-flm">FLAME</th><th class="bot-h c-inf">INFERNO</th><th class="bot-h c-flr">FLARE</th><th class="bot-h c-blz">BLAZE</th></tr>
      </thead>
      <tbody>
        <tr><td>Strategy Type</td><td>Iron Condor</td><td>Bull Put Spread</td><td>Iron Condor</td><td>Debit Spread</td><td>Debit Spread</td></tr>
        <tr><td>DTE</td><td>1 Day</td><td>2 Days</td><td>0 Day</td><td>0 Day</td><td>1 Day</td></tr>
        <tr><td>Bias</td><td>Neutral / Range</td><td>Bullish Lean</td><td>Neutral</td><td>Directional</td><td>Directional</td></tr>
        <tr><td>Market Conditions</td><td>Normal IV / Range</td><td>Elevated IV / Pullback</td><td>High IV / Volatile</td><td>Intraday Momentum</td><td>Overnight Setup</td></tr>
        <tr><td>Trade Frequency</td><td>Daily</td><td>1–2 / Day</td><td>Multi / Day</td><td>1–3 / Day</td><td>1–2 / Day</td></tr>
        <tr><td>Hold Time</td><td>Intraday</td><td>Hours – 2 Days</td><td>Minutes – Hours</td><td>Intraday</td><td>Overnight – 1 Day</td></tr>
        <tr><td>Risk Profile</td><td class="c-spk">Moderate</td><td class="c-flm">Moderate+</td><td class="c-inf">High</td><td class="c-flr">High</td><td class="c-blz">Moderate+</td></tr>
        <tr><td>Automation</td><td>High</td><td>High</td><td>High</td><td>High</td><td>High</td></tr>
      </tbody>
    </table>
  </div>
</section>

<!-- ============ ANVIL HERO — chapter break / brand moment ============ -->

<section class="anvil-hero" aria-label="Discipline">
  <div class="anvil-stage">
    <div class="anvil-img" aria-hidden="true"><img src="/anvil-iso.png" alt="" loading="lazy"/></div>
    <div class="light-shaft" aria-hidden="true"></div>
    <div class="light-shaft s2" aria-hidden="true"></div>
    <div class="forge-edge">
      <div class="forge-line"></div>
      <div class="forge-cinders" id="cinders-hero"></div>
    </div>
    <span class="corner tl"></span><span class="corner tr"></span>
    <span class="corner bl"></span><span class="corner br"></span>
    <span class="scale l" aria-hidden="true"></span><span class="scale r" aria-hidden="true"></span>
    <div class="rail l" aria-hidden="true">
      <div class="tick"><span><b>JOB 23:10</b> · <em>"forth as gold"</em></span></div>
      <div class="tick"><span><b>MAL. 3:3</b> · <em>"refiner of silver"</em></span></div>
      <div class="tick"><span><b>1 PET. 1:7</b> · <em>"tested by fire"</em></span></div>
      <div class="tick"><span><b>ISA. 48:10</b> · <em>"furnace of affliction"</em></span></div>
      <div class="tick"><span><b>ZECH. 13:9</b> · <em>"refine like silver"</em></span></div>
    </div>
    <div class="rail r" aria-hidden="true">
      <div class="tick"><span><em>"produces righteousness"</em> · <b>HEB. 12:11</b></span></div>
      <div class="tick"><span><em>"remove the dross"</em> · <b>PROV. 25:4</b></span></div>
      <div class="tick"><span><em>"testing produces"</em> · <b>JAMES 1:3</b></span></div>
      <div class="tick"><span><em>"better than mighty"</em> · <b>PROV. 16:32</b></span></div>
      <div class="tick"><span><em>"perseverance, character"</em> · <b>ROM. 5:4</b></span></div>
    </div>
    <div class="plate-tag"><span class="dot"></span>FIG. 02.6 · <em>THE FORGE</em> · ORTHOGRAPHIC</div>
    <div class="coords">
      <span>X · <b>0.000</b></span>
      <span>Y · <b>0.000</b></span>
      <span>Z · <b>0.000</b></span>
      <span>TEMP · <b style="color:var(--accent)">1,538°C</b></span>
      <span>STATE · <b style="color:var(--accent)">FORGING</b></span>
    </div>

    <div class="anvil-overlay">
      <h2>Pressure. Heat. <em>Refinement.</em></h2>
      <p class="quote">"As iron sharpens iron, so one person sharpens another."</p>
      <p class="quote-attr">— Proverbs <em>27:17</em></p>
    </div>
  </div>
</section>

<!-- ANVIL — animated counters + forge edge -->
<section class="anvil">
  <div class="forge-edge">
    <div class="forge-line"></div>
    <div class="forge-cinders" id="cinders"></div>
  </div>
  <div class="anvil-inner">
    <div class="anvil-meta"><span class="anvil-meta-dot"></span>FIG. 02.5 · STRESS REPORT · 18-MO BACKTEST</div>
    <h2>Discipline <em>scales.</em><br/>Emotion <em>doesn't.</em></h2>
    <p class="anvil-sub">IronForge was built around structured execution, defined risk, and continuous refinement. <b style="color:var(--ink)">No hype. No gambling culture. No reckless deployment.</b> Just systems, process, and precision.</p>
    <div class="anvil-stats">
      <div class="ac">
        <div class="ac-num">FIG. <em>2.5-A</em> · WIN RATE</div>
        <div class="ac-val" data-target="78">0<sup>%</sup></div>
        <div class="ac-label">Closed at target</div>
        <div class="ac-foot">2,847 trades · 18 mo</div>
      </div>
      <div class="ac">
        <div class="ac-num">FIG. <em>2.5-B</em> · MAX DD</div>
        <div class="ac-val" data-target="6.2">0<sup>%</sup></div>
        <div class="ac-label">Worst drawdown</div>
        <div class="ac-foot">Single-month, 2024-08</div>
      </div>
      <div class="ac">
        <div class="ac-num">FIG. <em>2.5-C</em> · SHARPE</div>
        <div class="ac-val" data-target="1.84">0</div>
        <div class="ac-label">Risk-adjusted return</div>
        <div class="ac-foot">Net of slippage &amp; fees</div>
      </div>
    </div>
  </div>
</section>

<!-- ============ HOW IT WORKS — 5-STEP FLOW ============ -->

<section class="flow-sheet" id="flow">
  <div class="flow-head">
    <div class="kicker">// 03 · HOW IT WORKS</div>
    <h2>From signup to <em>live deployment</em><br/>in five disciplined steps.</h2>
    <p>No spreadsheets, no chart-reading, no guesswork. The system runs itself — you set the rules of engagement.</p>
  </div>
  <div class="flow-grid">
    <div class="flow-step"><div class="flow-num">1</div><h4>Create Environment</h4><p>Sign up &amp; configure your operational setup</p></div>
    <div class="flow-step"><div class="flow-num">2</div><h4>Select Frameworks</h4><p>Choose Spark / Flame / Inferno / Flare / Blaze</p></div>
    <div class="flow-step"><div class="flow-num">3</div><h4>Configure Safeguards</h4><p>Daily max loss, position size, kill switch</p></div>
    <div class="flow-step"><div class="flow-num">4</div><h4>Validate Deployment</h4><p>Paper mode first, system checks</p></div>
    <div class="flow-step"><div class="flow-num">5</div><h4>Enter the Forge</h4><p>Launch your command center</p></div>
  </div>
</section>

<!-- ============ BROKERAGE CONNECT — Tradier live / Tastytrade soon ============ -->

<section class="brk-sheet">
  <div class="brk-head">
    <div class="kicker">// 03.5 · BROKERAGE CONNECT</div>
    <h2>Your account. <em>Your keys.</em><br/>Your money never leaves your broker.</h2>
  </div>
  <div class="brk-grid">
    <div class="brk-card live">
      <span class="brk-badge">● LIVE</span>
      <h3>Tradier</h3>
      <div class="brk-tag">PRIMARY · RECOMMENDED</div>
      <p>Direct API integration with sandbox + production environments. Connect via OAuth 2.0 in 60 seconds. Recommended for all new operators.</p>
      <ul class="brk-list">
        <li>API-enabled, options-focused</li>
        <li>Paper (sandbox) + live trading</li>
        <li>No withdrawal permissions</li>
        <li>Revoke access anytime</li>
      </ul>
    </div>
    <div class="brk-card soon">
      <span class="brk-badge">SOON</span>
      <h3>Tastytrade</h3>
      <div class="brk-tag">COMING SOON · JOIN WAITLIST</div>
      <p>Integration in progress. Join the brokerage waitlist below and we'll notify you the day Tastytrade goes live in IronForge.</p>
      <ul class="brk-list">
        <li>Options-focused workflows</li>
        <li>Active-trader friendly</li>
        <li>Advanced order management</li>
        <li>Real-time market data</li>
      </ul>
    </div>
  </div>
</section>
<div class="sheet-rule" id="mech">
  <span class="sh">DRAWING · IF-003 / SHEET 03 OF 04</span>
  <div class="ln"></div>
  <span>RISK GATE · BLOCK DIAGRAM</span>
  <span class="stamp"><span class="live"></span> 6 GATES · ARMED</span>
</div>
<section class="mech-sheet">
  <div class="mech-grid">
    <div class="mech-text">
      <h2>Every order<br/>passes the <em>gates.</em></h2>
      <p>The forge is an engine, not an oracle. Each candidate trade flows through a fixed sequence of binary checks before a single contract is submitted to Tradier.</p>
      <p>One <b>fail</b>, no trade. Read the log, not the chart.</p>
      <div class="mech-callouts">
        <div class="c"><span class="n">01</span><span><b>IV RANK</b> · 20 ≤ rank ≤ 80 — no dead-vol, no extremes</span><span class="gate">✓ OK</span></div>
        <div class="c"><span class="n">02</span><span><b>VIX REGIME</b> · 10 ≤ vix ≤ 30 — outside band, halt</span><span class="gate">✓ OK</span></div>
        <div class="c"><span class="n">03</span><span><b>CALENDAR</b> — earnings ±2d, FOMC, CPI all blocked</span><span class="gate">✓ OK</span></div>
        <div class="c"><span class="n">04</span><span><b>CONCURRENCY</b> — max 3 open, one per bot, one per DTE</span><span class="gate">✓ OK</span></div>
        <div class="c"><span class="n">05</span><span><b>SIZING</b> — bot risk × NAV, never exceeds drawdown cap</span><span class="gate">✓ OK</span></div>
        <div class="c"><span class="n">06</span><span><b>FILL</b> — limit-only at mid, ladder ±$0.05 for 30s</span><span class="gate">✓ OK</span></div>
      </div>
    </div>
    <div class="mech-art">
      <svg viewBox="0 0 480 480">
        <defs>
          <pattern id="dotgrid2" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.6" fill="#1a1612"/>
          </pattern>
          <marker id="arr2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="#ff6b35"/>
          </marker>
        </defs>
        <rect width="480" height="480" fill="url(#dotgrid2)"/>

        <rect x="60" y="40" width="360" height="50" fill="none" stroke="#a8a092" stroke-width="1"/>
        <text x="240" y="62" fill="#e8e2d4" font-size="11" text-anchor="middle" letter-spacing="2">SCAN · CHAIN</text>
        <text x="240" y="78" fill="#5a5447" font-size="9" text-anchor="middle">candidates from option chain</text>

        <line x1="240" y1="90" x2="240" y2="110" stroke="#ff6b35" marker-end="url(#arr2)">
          <animate attributeName="stroke-opacity" values="0.3;1;0.3" dur="1.8s" repeatCount="indefinite"/>
        </line>

        <g>
          <rect class="gate-rect" data-gate="0" x="60" y="120" width="170" height="36" fill="none" stroke="#a8a092"/>
          <text x="145" y="142" fill="#e8e2d4" font-size="10" text-anchor="middle" letter-spacing="1">IV RANK · 20–80</text>
          <rect class="gate-rect" data-gate="1" x="250" y="120" width="170" height="36" fill="none" stroke="#a8a092"/>
          <text x="335" y="142" fill="#e8e2d4" font-size="10" text-anchor="middle" letter-spacing="1">VIX · 10–30</text>
          <rect class="gate-rect" data-gate="2" x="60" y="170" width="170" height="36" fill="none" stroke="#a8a092"/>
          <text x="145" y="192" fill="#e8e2d4" font-size="10" text-anchor="middle" letter-spacing="1">CALENDAR · CLEAR</text>
          <rect class="gate-rect" data-gate="3" x="250" y="170" width="170" height="36" fill="none" stroke="#a8a092"/>
          <text x="335" y="192" fill="#e8e2d4" font-size="10" text-anchor="middle" letter-spacing="1">CONCURRENCY · OK</text>
          <rect class="gate-rect" data-gate="4" x="60" y="220" width="170" height="36" fill="none" stroke="#a8a092"/>
          <text x="145" y="242" fill="#e8e2d4" font-size="10" text-anchor="middle" letter-spacing="1">SIZING · ≤ NAV%</text>
          <rect class="gate-rect" data-gate="5" x="250" y="220" width="170" height="36" fill="none" stroke="#a8a092"/>
          <text x="335" y="242" fill="#e8e2d4" font-size="10" text-anchor="middle" letter-spacing="1">SHORT Δ · 0.16</text>
        </g>

        <line x1="240" y1="270" x2="240" y2="300" stroke="#ff6b35" marker-end="url(#arr2)"/>

        <rect x="160" y="310" width="160" height="44" fill="rgba(255,107,53,.06)" stroke="#ff6b35"/>
        <text x="240" y="336" fill="#ff6b35" font-size="11" text-anchor="middle" letter-spacing="3">AND</text>

        <line x1="240" y1="356" x2="240" y2="386" stroke="#ff6b35" marker-end="url(#arr2)"/>

        <rect x="100" y="396" width="280" height="48" fill="rgba(255,107,53,.10)" stroke="#ff6b35" stroke-width="1.5"/>
        <text x="240" y="420" fill="#ff6b35" font-size="12" text-anchor="middle" letter-spacing="3">SUBMIT TO TRADIER</text>
        <text x="240" y="434" fill="#a8a092" font-size="9" text-anchor="middle">limit · mid · 30s ladder</text>

        <text x="20" y="20" font-size="9" fill="#5a5447">FIG. 03</text>
        <text x="460" y="20" font-size="9" fill="#5a5447" text-anchor="end">REV B</text>
      </svg>
    </div>
  </div>
</section>

<!-- AUTH / CHANGE REQUEST -->
<div class="sheet-rule" id="proof">
  <span class="sh">DRAWING · IF-004 / SHEET 04 OF 04</span>
  <div class="ln"></div>
  <span>OPERATOR ENROLLMENT · CHANGE REQUEST</span>
  <span class="stamp">REV B · ACCEPTING</span>
</div>
<section class="auth-sheet">
  <div class="auth-grid">
    <div class="auth-l">
      <div class="stamp"><span style="width:6px;height:6px;background:var(--accent);border-radius:50%;box-shadow:0 0 8px var(--accent)"></span> EARLY ACCESS · WAITLIST OPEN</div>
      <h3>The forge isn't lit <em>yet.</em></h3>
      <p><b>IronForge is software you operate</b>, not a fund. You'll bring the brokerage account, we'll bring the engine — but we're not quite open yet.</p>
      <p>Drop your email below and we'll send you a personal invite the day the bots go live. No drip campaigns, no spam — just one note when the forge is ready.</p>
      <div class="checks">
        <div>NO CHARGE · NO COMMITMENT</div>
        <div>YOUR ACCOUNT · YOUR KEYS · YOUR RULES</div>
        <div>FIRST 100 OPERATORS GET LIFETIME EARLY-ADOPTER PRICING</div>
        <div>UNSUBSCRIBE IN ONE CLICK · NO LOCK-IN</div>
      </div>
    </div>
    <div class="auth-r">
      <form class="auth-form" id="waitlist-form" action="mailto:hello@ironforge.example?subject=IronForge%20waitlist%20signup" method="post" enctype="text/plain">
        <div>
          <span class="label">YOUR EMAIL</span>
          <input type="email" name="email" placeholder="you@gmail.com" required/>
        </div>
        <div>
          <span class="label">EXPERIENCE LEVEL <em style="color:var(--ink-3);font-style:normal">// optional</em></span>
          <select name="experience" style="width:100%;background:var(--bg);border:1px solid var(--line-2);color:var(--ink);padding:12px 14px;font-family:'IBM Plex Mono',monospace;font-size:14px;outline:none">
            <option>Never traded options</option>
            <option>Dabbled a few times</option>
            <option>I trade actively</option>
            <option>Prefer not to say</option>
          </select>
        </div>
        <label class="check">
          <input type="checkbox" required/>
          <span>I understand IronForge is pre-launch software and that options trading carries substantial risk of loss when it goes live.</span>
        </label>
        <button class="submit" type="submit">
          <span>▸ GET MY INVITE</span>
          <span style="font-family:'IBM Plex Sans';font-weight:300;font-size:18px;letter-spacing:0">→</span>
        </button>
        <div class="alt" id="waitlist-thanks" style="display:none">✓ You're on the list. We'll be in touch.</div>
        <div class="alt">No spam. One email when the bots go live.</div>
      </form>
    </div>
  </div>
</section>

<!-- ============ OUR FOUNDATION — values strip ============ -->

<section class="found-sheet">
  <div class="found-head">
    <div class="kicker">// 04.5 · OUR FOUNDATION</div>
    <h3>Grounded in <em>discipline.</em> Built for the long arc.</h3>
    <p class="verse">"As iron sharpens iron, so one person sharpens another."</p>
    <span class="verse-attr">— Proverbs 27:17</span>
  </div>
  <div class="values-strip">
    <div class="val-cell"><div class="val-ico">▣</div><div class="val-lbl">Discipline</div><div class="val-sub">Rules over feel</div></div>
    <div class="val-cell"><div class="val-ico">◐</div><div class="val-lbl">Patience</div><div class="val-sub">Slow compounding</div></div>
    <div class="val-cell"><div class="val-ico">♡</div><div class="val-lbl">Stewardship</div><div class="val-sub">Your capital first</div></div>
    <div class="val-cell"><div class="val-ico">△</div><div class="val-lbl">Humility</div><div class="val-sub">The market is teacher</div></div>
    <div class="val-cell"><div class="val-ico">↻</div><div class="val-lbl">Continuous Refinement</div><div class="val-sub">Always learning</div></div>
  </div>
</section>

<!-- TITLEBLOCK FOOT -->
<div class="titleblock-foot">
  <div class="tb-cell"><div class="tb-lbl">DWG TITLE</div><div class="tb-val mono">IRONFORGE / LANDING</div></div>
  <div class="tb-cell"><div class="tb-lbl">SHEET</div><div class="tb-val mono">04 OF 04</div></div>
  <div class="tb-cell"><div class="tb-lbl">REV</div><div class="tb-val mono">B · 2026-05</div></div>
  <div class="tb-cell"><div class="tb-lbl">APPROVED</div><div class="tb-val mono">— forge eng</div></div>
  <div class="tb-cell"><div class="tb-lbl">FILE</div><div class="tb-val mono">if-001-b.dwg</div></div>
</div>

<div class="risk">
  <b>RISK ▸</b> Options trading involves substantial risk of loss and is not suitable for every investor. Defined-risk does not mean low-risk; max loss can equal wing width minus credit on every contract. IronForge is software you operate; you are the trader of record. Past simulation results do not guarantee future returns.
</div>

<!-- ─── INTERACTIVE BEHAVIORS ─────────────────────── -->

<!-- ─── PROGRESSIVE FEATURES (chips, scrubber, sparklines, quiz) ─── -->

<!-- ─── WAITLIST MODAL ─── -->

<div class="waitlist-modal" id="waitlist-modal" role="dialog" aria-modal="true" aria-label="Join waitlist">
  <div class="waitlist-card">
    <span class="wlc tl"></span><span class="wlc tr"></span><span class="wlc bl"></span><span class="wlc br"></span>
    <button class="waitlist-x" id="waitlist-close" aria-label="Close">×</button>
    <div id="waitlist-form-wrap">
      <div class="waitlist-eyebrow">▸ EARLY ACCESS · BATCH 01</div>
      <h3>We'll email you when the <em>forge is lit.</em></h3>
      <p>Drop your email. You'll be first in when the bots go live — no newsletter, no spam, just the invite.</p>
      <form class="waitlist-form" id="waitlist-form">
        <input type="email" required placeholder="you@yours.com" id="waitlist-email" autocomplete="email"/>
        <button type="submit">▸ NOTIFY ME</button>
      </form>
      <div class="waitlist-fine">~ 2 WEEKS · 60 SPOTS · BATCH 01</div>
    </div>
    <div class="waitlist-success" id="waitlist-success">
      <b>✓ ON THE LIST</b>
      You'll hear from us before the open.<br/>Welcome to batch 01.
    </div>
  </div>
</div>`
