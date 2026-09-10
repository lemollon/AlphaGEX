# LLC Formation Guide — AlphaGEX · SpreadWorks · IronForge

> **Not legal or tax advice.** This is a practical planning guide written by an
> engineer, not an attorney or CPA. Fees, thresholds, and rules change and vary
> by situation. Before filing, spend one hour with a Texas business attorney
> and/or a CPA who knows trader taxation. The cost of that hour is trivial next
> to getting the structure wrong. Figures below were current as of **May 2026**.

---

## 0. TL;DR — The Recommended Plan

For a solo (or small-team) founder living in **Texas**, running three
**software/trading** products:

1. **Form ONE LLC in Texas.** Not Delaware, not Wyoming (see §2 for why).
2. **Run all three products as brands (DBAs / "assumed names") under that one
   LLC** — do *not* form three separate LLCs to start (see §3).
3. Name the LLC something **umbrella / neutral** (e.g. a holding-style name),
   then file **assumed name certificates** for `AlphaGEX`, `SpreadWorks`, and
   `IronForge` as needed (see §4 for name ideas).
4. After formation: get an **EIN**, open a **business bank account**, sign an
   **operating agreement**, and **assign the IP** (the code) from you personally
   into the LLC (see §5–6).
5. **Before you take a single dollar from anyone else** — for signals, a SaaS
   subscription, or managed money — read §7. This is the part that can actually
   get you in trouble, far more than the entity paperwork.

Total realistic first-year cost in Texas: **~$300–$700** if you DIY the filing,
or **~$600–$1,200** if you use a registered-agent service. (§8 has the table.)

---

## 1. What We're Putting Under the Entity

Three products that currently live in one monorepo:

| Product | What it is | Lives in |
|---|---|---|
| **AlphaGEX** | GEX (gamma exposure) options-trading platform + bots | repo root |
| **SpreadWorks** | Double-diagonal / calendar spread analyzer + Discord bot | `spreadworks/` |
| **IronForge** | Trading system | `ironforge/` |

The thing of value the LLC will *own* is: the **code/IP**, the **brand names**,
any **trading accounts** opened in the LLC's name, and the **revenue** (if any)
these products generate. The point of the LLC is to (a) hold that IP in one
place, (b) separate business liability from your personal assets, and (c) give
you a clean entity for banking, taxes, and any future partners/investors.

---

## 2. Which State? (Texas — almost certainly)

The internet pushes Delaware and Wyoming hard. For your situation, **form in
Texas**. Here's the honest breakdown.

### The "foreign qualification" trap
If you live and work in Texas and form your LLC in Delaware or Wyoming, you
don't escape Texas. The moment you "do business" in Texas (which you are — you
live and operate here), you must **register the out-of-state LLC as a "foreign"
LLC in Texas anyway**. Result: you pay **two** sets of fees, **two** registered
agents, and file in **two** states — for essentially zero benefit at your scale.

### When Delaware actually makes sense
- You're raising **venture capital** and the VCs demand a Delaware **C-corp**
  (note: a corp, not an LLC).
- You expect **many outside investors** and want Delaware's well-developed
  corporate case law.
- Neither applies to a solo trading-software shop today. You can always
  **convert/redomesticate later** if you raise money.

### When Wyoming actually makes sense
- You want **maximum owner privacy** (Wyoming doesn't list members publicly) and
  you have **no physical nexus** anywhere — e.g. a pure online business with no
  home state. You have a home state: Texas.

### Why Texas is the right call for you
- **No state personal income tax**, and the franchise tax has a **"no tax due"
  threshold of ~$2.65M** annualized revenue for 2026–2027 reports — you almost
  certainly owe **$0** in franchise tax for years.
- Strong, modern LLC statute (Texas Business Organizations Code).
- You're already here — **one** filing, **one** agent, **one** state.
- Filing fee is **$300** (one-time, see §8).

> ⚠️ Even at $0 tax owed, Texas still requires a **Public Information Report
> (PIR)** every year by **May 15**. The PIR has **no fee**, but **missing it can
> forfeit your LLC's right to do business**. Calendar it.

---

## 3. Which Structure? (One LLC + DBAs to start)

You have three options for "three products, one company." Ranked for your stage:

### ✅ Option A — Single LLC + Assumed Names (DBAs) — **START HERE**
One LLC owns everything. You file an **assumed name certificate** for each brand
you want to operate/bill under (`AlphaGEX`, `SpreadWorks`, `IronForge`).

- **Pros:** Cheapest, simplest, one tax return, one bank account, one set of
  filings. Brands can still have distinct logos/sites/Stripe products.
- **Cons:** **No liability separation between the three brands.** If IronForge
  gets sued, AlphaGEX's assets (inside the same LLC) are exposed. At pre-revenue
  / early-revenue stage this risk is low and not worth the overhead of splitting.
- **Best when:** You're one person, products share code, and none is yet a
  material independent revenue stream.

### ⚖️ Option B — Texas Series LLC
One "parent" LLC that creates internal **series** (e.g. Series A = AlphaGEX,
Series B = SpreadWorks, Series C = IronForge). Texas is one of the few states
that allows this.

- **Pros:** Internal **liability separation between series** at lower cost than
  three full LLCs; one state filing.
- **Cons:** Operationally fiddly — each series must keep **separate books and
  records** or you lose the liability shield ("piercing"). Banks, brokers, and
  other states don't always understand series; out-of-state recognition is
  uneven. Overkill until each product is its own real business.
- **Best when:** Two or three of the products become independent revenue streams
  and you want them walled off, but don't yet want three separate tax returns.

### 🏢 Option C — Holding Company + Subsidiary LLCs
A parent "HoldCo" LLC that owns three child LLCs (AlphaGEX LLC, SpreadWorks LLC,
IronForge LLC).

- **Pros:** Strongest liability separation; cleanest for selling **one** product
  or taking an investor into **one** product; each child is a normal LLC every
  bank/broker understands.
- **Cons:** Most expensive and most paperwork — **4 entities**, potentially 4
  filings, multiple bank accounts, more accounting.
- **Best when:** A product is generating real money, you're hiring around it, or
  you're courting a buyer/investor for a specific product.

### Recommendation
**Start with Option A.** Re-evaluate when any single product clears meaningful
recurring revenue or takes on outside risk (real customers, managed money) —
then graduate that product to **Option C** (spin it into its own subsidiary).
You don't need to decide the end-state today; the migration path is clean.

---

## 4. Naming the LLC

Two layers:

1. **Legal entity name** — appears on the Certificate of Formation, bank
   account, tax returns. Make it **neutral/umbrella** so it isn't tied to one of
   the three products. Must end with `LLC`, `L.L.C.`, or `Limited Liability
   Company`.
2. **Brand / DBA names** — `AlphaGEX`, `SpreadWorks`, `IronForge` stay as
   customer-facing brands, filed as assumed names under the entity.

### Name ideas for the umbrella entity
Themes pulled from the products: gamma/convexity (AlphaGEX), spreads/options
(SpreadWorks), forge/anvil/iron (IronForge), plus generic quant/markets.

| Name | Why it fits |
|---|---|
| **Convexity Labs LLC** | "Convexity" = gamma in options-speak; ties to AlphaGEX's core; "Labs" signals a portfolio of products. Neutral, professional. |
| **Gamma Forge Capital LLC** | Bridges AlphaGEX (gamma) + IronForge (forge). "Capital" reads like a trading firm. |
| **Strike Forge LLC** | Options "strike" + IronForge's "forge." Short, brandable. |
| **Anvil Quant LLC** | Forge → anvil; "Quant" signals systematic trading. Clean and memorable. |
| **Three Greeks Capital LLC** | Options Greeks + the three products. Slightly playful. |
| **Lattice Trading Systems LLC** | Neutral, technical (binomial lattice / options pricing), umbrellas all three. |
| **Theta Forge LLC** | Theta (options decay) + forge. Distinctive. |

My pick for a clean, neutral umbrella: **Convexity Labs LLC** or **Gamma Forge
Capital LLC**. Avoid putting "Capital," "Partners," or "Fund" in the name *if*
you'll never manage outside money — those words can imply you're a regulated
financial firm. "Labs," "Systems," "Technologies," or "Software" are safer for a
software shop. (See §7.)

### Before you commit to a name — check availability
1. **Texas SOSDirect / Comptroller "Taxable Entity Search"** — is the entity
   name already taken in Texas? (Names must be "distinguishable.")
2. **USPTO trademark search** (`tmsearch.uspto.gov`) — make sure the name (and
   ideally `AlphaGEX`/`SpreadWorks`/`IronForge`) isn't trademarked by someone
   else in a related class.
3. **Domain + social handles** — is the `.com` available?
4. Optional but smart: reserve the entity name with the Texas SOS (Form 501,
   small fee) if you're not filing immediately.

---

## 5. Step-by-Step: Forming the Texas LLC

> Do these in order. Items marked **(DIY-able)** you can do yourself online;
> none strictly require a lawyer, but §6 IP assignment and the operating
> agreement are worth a professional review.

1. **Pick the entity name** and confirm availability (§4). **(DIY-able)**

2. **Choose a registered agent.** Texas requires a registered agent with a
   physical Texas street address (no PO boxes) available during business hours.
   Options:
   - **Yourself / your home address** — free, but your address becomes public
     record and you must be available during business hours.
   - **A commercial registered-agent service** (~$100–$150/yr) — keeps your home
     address off public filings; they forward legal mail. Recommended if privacy
     matters. **(DIY-able)**

3. **File the Certificate of Formation (Form 205)** with the Texas Secretary of
   State via **SOSDirect** (online) or by mail. Fee: **$300**.
   - Choose **member-managed** (you run it) vs **manager-managed** (a manager
     runs it) — solo founders almost always pick **member-managed**.
   - If you ever want a **Series LLC** (Option B), the special series language
     goes in the **Supplemental Text** section here. **(DIY-able)**

4. **Get an EIN from the IRS** (free, ~10 minutes online at irs.gov). This is the
   business's tax ID; you'll need it for banking and taxes. Do **not** pay a
   third party for this — it's free directly from the IRS. **(DIY-able)**

5. **Adopt an Operating Agreement.** Texas doesn't *require* filing one, but you
   should *have* one — it's what actually proves the LLC is a separate entity
   (critical for the liability shield) and governs ownership %, contributions,
   distributions, and what happens if a member leaves. For a single-member LLC a
   template is usually fine; for multi-member, get it reviewed. **(lawyer worth it
   for multi-member)**

6. **File Assumed Name Certificates (DBAs)** for any brand operating under a name
   other than the legal entity name — i.e. `AlphaGEX`, `SpreadWorks`,
   `IronForge`. Filed with the **Texas SOS** (and historically also at the county
   level — confirm current requirement). Small fee per name. **(DIY-able)**

7. **Open a business bank account** in the LLC's name using the EIN + a copy of
   the Certificate of Formation. **Never commingle** personal and business money
   — commingling is the #1 way solo owners accidentally void their own liability
   protection.

8. **Calendar the annual Public Information Report (PIR)**, due **May 15** every
   year (no fee, but mandatory). Set a recurring reminder now.

---

## 6. Moving the Three Products Into the LLC (IP Assignment)

This step is skipped constantly and it matters. Right now **you personally** own
the code you've written (or it's ambiguous). To have the LLC actually own
AlphaGEX, SpreadWorks, and IronForge:

1. **Sign an IP Assignment Agreement** transferring all code, trademarks, brand
   names, domains, and related IP from **you personally → the LLC**. One short
   document, dated after the LLC exists. (A lawyer can paper this in 30 minutes;
   templates exist.)
2. **Transfer domains and accounts** (GitHub org, Render, Vercel, Stripe,
   Discord, data-vendor API contracts) into the business's name/ownership where
   practical.
3. **Add a LICENSE / copyright notice** to each product's repo reflecting the LLC
   as owner once the name is final (e.g. `Copyright © 2026 <LLC Name>. All rights
   reserved.`). *(I can do this part in the codebase for you once you pick the
   name — just say the word.)*
4. Keep a simple **cap table / ownership record** even as a solo owner (you own
   100% of the membership units).

---

## 7. ⚠️ The Part That Actually Carries Risk: Securities / Trading Regulation

The LLC paperwork is the easy, low-risk part. **How you use these products
determines whether you trip financial-regulation tripwires** — this is where you
genuinely need a securities/CFTC attorney *if* you go beyond trading your own
money. Read this carefully:

- **Trading only your own capital through the LLC** → generally fine. The LLC is
  just a vehicle for your own account. (Talk to a CPA about **"trader tax
  status,"** mark-to-market elections, and whether an LLC helps or hurts your
  taxes — it's situation-specific.)

- **Selling subscriptions to trade *signals* / a SaaS that tells people what to
  trade** (e.g. AlphaGEX or SpreadWorks alerts, the Discord `/spread` bot's
  recommendations) → this can make you an **"investment adviser"** under federal
  and Texas state law. There's a **"publisher's exclusion"** for *bona fide,
  general, impersonal* market commentary, but **personalized** advice for
  compensation generally requires **registration** (state RIA, or SEC if large
  enough). The line is fact-specific. **Get advice before charging for advice.**

- **Managing other people's money / pooling capital** (an actual fund) →
  **heavily regulated** (Investment Advisers Act, possibly Investment Company
  Act, Texas State Securities Board, blue-sky laws). Do **not** do this without a
  securities attorney. The LLC alone does not make this legal.

- **Anything touching futures/commodities or crypto derivatives** (IronForge or
  AGAPE perps, futures) sold/advised to others → may implicate **CFTC/NFA**
  (CTA/CPO registration). Again: own-account trading is the safe lane.

- **Naming caution:** words like *Capital*, *Partners*, *Advisors*, *Fund*,
  *Asset Management* in your entity/brand names can **imply** you're a regulated
  financial firm even if you aren't. If you'll only ever trade your own money and
  sell software, lean toward *Labs / Systems / Technologies / Software*.

**Bottom line:** Form the LLC freely. But **before monetizing advice or
touching outside money, get one consultation with a securities attorney.** This
section is the real risk, not the $300 filing.

---

## 8. Cost Summary (Texas, 2026)

| Item | Cost | Frequency | Notes |
|---|---|---|---|
| Certificate of Formation (Form 205) | **$300** | One-time | Texas SOS filing fee |
| Registered agent (commercial) | **$0–$150** | Annual | $0 if you self-serve as agent |
| EIN | **$0** | One-time | Free from IRS — never pay for this |
| Operating agreement | **$0–$500** | One-time | $0 template (solo) → lawyer (multi-member) |
| Assumed name (DBA) per brand | **~$25 each** | One-time* | For AlphaGEX / SpreadWorks / IronForge |
| Public Information Report (PIR) | **$0** | Annual (May 15) | Mandatory even at $0 tax |
| Franchise tax | **$0** | Annual | Until ~$2.65M revenue (2026–2027) |
| Business bank account | **$0** | — | Many free business checking options |
| **Realistic Year 1 total (DIY)** | **~$300–$475** | | + ~$75 if you file 3 DBAs |
| **Realistic Year 1 total (assisted)** | **~$600–$1,200** | | With agent + lawyer-reviewed docs |

\* DBA/assumed name renewal periods vary; confirm current term at filing.

---

## 9. Your Next Actions

1. **Decide the entity name** (§4) — I lean **Convexity Labs LLC** or **Gamma
   Forge Capital LLC**; run it through the Texas entity search + USPTO + domain
   check.
2. **Confirm Texas** as the state (§2) — it's the right answer unless you're
   about to raise VC.
3. **Decide structure** — start with **Option A** (one LLC + DBAs) (§3).
4. **File Form 205 + get EIN + open bank account** (§5).
5. **Sign the IP assignment** to move the three products into the LLC (§6).
6. **Book one hour with (a) a Texas business attorney** for the operating
   agreement + IP assignment, **and (b) a CPA** for trader-tax-status questions.
7. **Before charging for advice or touching outside money → securities attorney**
   (§7).

---

### When you've picked a name, I can:
- Add `LICENSE` files and copyright headers/UI footers across AlphaGEX,
  SpreadWorks, and IronForge naming the LLC as owner.
- Draft a top-level monorepo README presenting the three products as one
  company's portfolio.
- Draft (non-legal) template stubs: operating agreement outline, IP assignment
  outline, and a formation checklist you can hand to your attorney.

Just tell me the name and which of those you want.

---

#### Sources (fees/rules current as of May 2026)
- [Texas SOS — Business Filings & Trademarks Fee Schedule (Form 806)](https://www.sos.texas.gov/corp/forms/806_boc.pdf)
- [Texas SOS — Selecting a Business Structure](https://www.sos.state.tx.us/corp/businessstructure.shtml)
- [Texas SOS — Name Filings FAQs](https://www.sos.texas.gov/corp/namefilingsfaqs.shtml)
- [LLC University — Texas LLC Costs (2026)](https://www.llcuniversity.com/texas-llc/costs/)
- [Texas LLC Taxes & Fees / PIR due May 15 (2026)](https://www.statebusinesscompliance.com/blog/texas-llc-taxes-fees-2026)
- [LLC University — Multiple businesses under one LLC (2026)](https://www.llcuniversity.com/multiple-businesses-under-one-llc/)
- [BusinessAnywhere — Series LLC Rules by State (2026)](https://businessanywhere.io/series-llc-rules-by-state/)
