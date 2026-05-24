# Social Media Knowledge Base — Iron Forge & Spreadworks

This folder is the **content brain** for two social-media "avatars" of the founder:
one for **Iron Forge** and one for **Spreadworks**. Drop these documents into Claude
Projects (as Project Knowledge) and the avatar will generate on-brand, accurate,
compliant content without you re-explaining the products every time.

> An "avatar" here is **one real person — you — wearing two product hats.** People
> follow people, not logos. The avatar is your transparent builder-in-public voice,
> scoped to one product per project so the content stays focused.

---

## How to set up the two Claude Projects

**Recommended structure: two brand projects + one shared library.**

### Project A — "Iron Forge — Social"
Upload as Project Knowledge:
- Everything in `shared/` (5 files)
- Everything in `ironforge/` (4 files)

Paste `ironforge/04_project_instructions.md` into the Project's **custom instructions**.

### Project B — "Spreadworks — Social"
Upload as Project Knowledge:
- Everything in `shared/` (5 files)
- Everything in `spreadworks/` (4 files)

Paste `spreadworks/04_project_instructions.md` into the Project's **custom instructions**.

> **Why two projects, not one?** The two products tell different stories to different
> audiences. Iron Forge is a *watch-the-bots-trade* build-in-public story. Spreadworks
> is a *tool + community* story. One combined project blurs the voices. The only cost
> is that the 5 `shared/` files live in both projects — when a shared fact changes,
> update it in both. That folder is deliberately small to keep that cheap.

---

## Folder map

```
social/
├── README.md                        ← you are here
├── shared/                          ← paste into BOTH projects
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
