# Social Media Knowledge Base — Iron Forge & Spreadworks

This folder is the **content brain** for **one brand with two systems**:

- **Brand:** AlphaGEX — the GEX-trading brand, and *you* (the founder) are its face.
- **System 1:** **Iron Forge** — autonomous SPY Iron Condor paper bots.
- **System 2:** **Spreadworks** — a GEX spread lab + paper bots + community.

You run **one founder voice ("the avatar")** across **one shared Discord, one X account,
and one Instagram** — all under the AlphaGEX brand. Drop these documents into a Claude
Project (as Project Knowledge) and the avatar generates on-brand, accurate, compliant
content for either system without you re-explaining anything.

> One brand, one human, two systems. People follow people, not logos. Iron Forge and
> Spreadworks are *what you ship*; AlphaGEX + you is *who's shipping it.*
>
> (If "AlphaGEX" isn't the public brand name you want, swap it everywhere — the model
> is the same: one umbrella brand over the two systems.)

---

## How to set up the Claude Project

**Decided channel strategy:** one personal founder brand across a **shared Discord**,
**X/Twitter**, and **Instagram**, promoting **both** products. Because the channels are
shared, the recommended setup is **one combined Claude Project.**

### Recommended — One combined project ("GEX Social" or your name)
Upload as Project Knowledge: **everything in `social/`** — all of `shared/`,
`ironforge/`, and `spreadworks/`.

Paste `combined_project_instructions.md` into the Project's **custom instructions**.

This matches the unified distribution: one feed per channel, mixing Iron Forge content,
Spreadworks content, and brand-neutral GEX education. The avatar decides which product
lens a given post needs (see `shared/05_website_and_funnel.md` for the cross-brand
calendar).

### Alternative — Two brand projects (only if you later split into separate handles)
If you ever run separate per-product accounts, split into two projects instead:
- **Project A — Iron Forge:** upload `shared/` + `ironforge/`; paste
  `ironforge/04_project_instructions.md` as custom instructions.
- **Project B — Spreadworks:** upload `shared/` + `spreadworks/`; paste
  `spreadworks/04_project_instructions.md` as custom instructions.
- Cost: the `shared/` files live in both projects — update shared facts in both.

---

## Folder map

```
social/
├── README.md                        ← you are here
├── combined_project_instructions.md ← paste into the ONE combined project (recommended)
├── shared/                          ← always uploaded
│   ├── 01_GEX_explained.md          Gamma Exposure, plain-English → technical
│   ├── 02_glossary.md               Options + GEX terms the avatar must use correctly
│   ├── 03_compliance_and_disclaimers.md   Hard rules. Non-negotiable.
│   ├── 04_creator_story_and_brand_voice.md  Who you are, how you sound
│   └── 05_website_and_funnel.md     The website as the conversion hub + CTA rules
├── ironforge/
│   ├── 01_product_knowledge.md      What Iron Forge is; FLAME / SPARK / INFERNO
│   ├── 02_avatar_persona.md         The Iron Forge avatar spec
│   ├── 03_content_playbook.md       Pillars, formats, hooks, cadence, platforms
│   └── 04_project_instructions.md   ← paste into Project A custom instructions
└── spreadworks/
    ├── 01_product_knowledge.md      What Spreadworks is; BREEZE / TIDE / DRIFT / FLOW + analyzer + Discord
    ├── 02_avatar_persona.md         The Spreadworks avatar spec
    ├── 03_content_playbook.md       Pillars, formats, hooks, cadence, platforms
    └── 04_project_instructions.md   ← paste into Project B custom instructions
```

---

## How to talk to the avatar (prompt patterns)

Once a project is set up, you can ask things like:

- "Write 5 X/Twitter posts about this week's Iron Forge results. Here's the equity
  screenshot data: [paste]."
- "Draft a LinkedIn post explaining the GEX flip point to a beginner, in my voice."
- "Spreadworks: write a Discord daily brief for tomorrow — verse, one tip, one
  engagement prompt, and a DRIFT setup idea for SPY."
- "Turn this INFERNO 0DTE losing day into an honest build-in-public thread. No
  spin, real lesson."
- "Give me 10 hooks for short-form video about trading WITH market makers."

The avatar already knows the products, the voice, and the compliance rules — so your
prompts can be short.

---

## Maintenance

- **Source of truth for product facts:** the codebase (`ironforge/CLAUDE.md`,
  `spreadworks/README.md`, `spreadworks/backend/bots/registry.py`). If you change a
  bot's parameters, update the matching `01_product_knowledge.md` so the avatar never
  posts stale numbers.
- **Fill in the placeholders:** anything in `<ANGLE_BRACKETS>` (URLs, handles, Discord
  invite, current phase) needs your real value before the avatar uses it.
- **Phase awareness:** the compliance doc tracks whether you're in paper-trading or
  live mode. Update it when that changes — it controls how the avatar is allowed to
  talk about results.
