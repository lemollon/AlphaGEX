# Attio saved views — build sheet

Attio's REST API has **no create-view endpoint**. Objects, attributes, select options, statuses,
lists, records, notes, tasks and webhooks can all be created programmatically; views cannot. So
these seven are the one part of the CRM spec that must be clicked by hand, and AC-CRM-011 is
verified against this sheet rather than by a test.

Everything these views reference already exists — the schema was provisioned on 2026-08-02 and
verified against the live workspace.

## Status

| # | View | Base | Priority | State |
|---|---|---|---|---|
| 1 | Waitlist - All | People | P0 | **Built** — missing only the Location column (see §1) |
| 2 | Waitlist - Priority | People | P0 | **Built** |
| 3 | Enrollment Pipeline | People (Kanban) | P0 | To build |
| 4 | Active Members | People | P0 | **Built** — add the Account Health sort when there is data |
| 5 | Brokerage Issues | Brokerage Connections | P0 | **Built** — columns, Or-filter and sort all saved |
| 6 | Paused & Canceled | Memberships | P1 | **Built** |
| 7 | Founding Member Outreach | List | P1 | To build |

## How to build one (the mechanics)

- **New view:** open the object → click the view-name dropdown (top left, next to "View
  settings") → **Create new view** → pick Table or Kanban → name it → Confirm.
- **Columns:** **View settings** → **Add attribute to view** → click the attribute. The panel
  closes after each pick, so reopen it for the next one.
- **Filter:** the **Filter** button → click the attribute in the list → pick the condition → pick
  the value.
- **Sort:** the **Sort** button → choose the attribute → then click the direction dropdown
  (defaults to Ascending) and set Descending where this sheet says so.
- **⚠️ Save:** changing filters/sorts shows **Save for everyone** in the top right. Click it, or
  the change stays local to you and nobody else sees the view you just built.

### ⚠️ Multi-value filters need an ADVANCED filter (learned the hard way)

Every "is any of / is in" filter in this spec — Brokerage Issues, Paused & Canceled, Enrollment
Pipeline — **cannot be built as one condition**. Attio's status filter is single-select: clicking
a second value silently REPLACES the first. Do this instead:

1. Add the filter normally with the first value (e.g. `Connection Status is Failed`).
2. Click the **⋮** on that filter → **Convert to advanced filter**.
3. In the advanced panel, **+ Add filter**, and click the **And** joiner to flip it to **Or**.
4. Repeat for each remaining value.
5. **Delete the leftover simple chip.** Converting leaves the original condition sitting in the
   filter bar *outside* the advanced group, where it ANDs against it — leaving it there makes the
   view permanently empty. Its **⋮** → **Delete filter**.

Verify the pill reads **Advanced filter N** with nothing beside it.

### ⚠️ Reference fields (Member, Brokerage) drill in rather than attach

Clicking `Member` opens the linked *person's* attributes instead of adding a Member column. Pick
**Name** from that drilled-in list to get a `Member › Name` column, which is what you want. Same
for `Brokerage` → `Name`, and for `Primary location` → `City` / `State`.

### Three gotchas that cost me time

1. **Don't type into the attribute picker before clicking its search box.** Focus starts on the
   list, so the first keystroke selects the highlighted row (I accidentally created a Record ID
   filter this way). Click the search field first, then type.
2. **"Primary location" has sub-fields.** Clicking the parent row drills into City / State /
   Country rather than adding it. Add **Primary location → City** and **Primary location →
   State** as two separate columns — better for you anyway, since the waitlist form captures
   exactly city and state.
3. **The Attio tab freezes under sustained automation.** If a click seems to do nothing, reload
   before repeating it — otherwise you'll double-apply the previous action.

---

## 1. Waitlist - All — *built, one column outstanding*

Already has: Person · Email addresses · Phone numbers · Trading Volume · Lead Source ·
Waitlist Date · Lead Priority. Filter `Customer Lifecycle is Waitlist`. Sort `Waitlist Date`
Descending. Saved for everyone.

**Outstanding:** add **Primary location → City** and **Primary location → State** (gotcha 2).

> It reads "0 count" today and that is correct — `Customer Lifecycle` only exists from
> 2026-08-02, so people captured before then have no value for it. New waitlist submissions
> populate it within ~30 seconds.

## 2. Waitlist - Priority — *BUILT AND SAVED*

- **Base:** People · **Type:** Table
- **Columns:** Person · Email addresses · Phone numbers · Trading Volume · Lead Source ·
  Lead Priority
- **Filter:** `Customer Lifecycle is Waitlist` **AND** `Lead Priority is High`
- **Sort:** `Trading Volume` Descending, then add a second sort `Waitlist Date` Ascending
  (oldest high-value lead first — they have waited longest)

> The spec also lists a "Follow-up Task" column. Tasks are not an attribute on People, so there
> is no such column to add; open tasks show on the record itself. Skip it.

## 3. Enrollment Pipeline

- **Base:** People · **Type:** **Kanban**
- When creating, the dialog asks for **Kanban Columns → Select a status attribute**. Choose
  **Customer Lifecycle**. That is the grouping — no separate "group by" step afterwards.
- **Columns (card fields):** Person · Email addresses · Account Health
- **Filter:** `Customer Lifecycle is any of` → Invited, Enrollment Started, Billing Complete,
  Active

> The spec asks for Plan, Brokerage Status and Last Activity on the cards. Those live on
> **Memberships** and **Brokerage Connections**, not People, so they cannot be card fields on a
> People kanban. Plan and connection status are one click away on each person's record via the
> linked Membership / Brokerage Connection. Do not try to force them on.

## 4. Active Members — *BUILT AND SAVED (sort still to add)*

- **Base:** People · **Type:** Table
- **Columns:** Person · Email addresses · Account Health · Customer Lifecycle
- **Filter:** `Customer Lifecycle is Active`
- **Sort:** `Account Health` Ascending, then `Waitlist Date` Descending

> Same cross-object limit as above: the spec's Plan, Preferred Agent, Brokerage, Connection
> Status and Start Date columns belong to Memberships / Brokerage Connections. Use view 6 for
> plan and dates, and view 5 for connection state.

## 5. Brokerage Issues — *BUILT AND SAVED*

- **Base:** Brokerage Connections · **Type:** Table
- **Columns:** Member › Name · Connection Status · Last Attempt · Last Error Code ·
  Last Error Summary · Reauthorization Required · Brokerage › Name
- **Filter:** Advanced — `Connection Status is Failed` **Or** `is Disconnected` **Or**
  `is Reauthorization Required`
- **Sort:** `Last Attempt` Descending

> This is the view that most needed the backend work: three failure paths used to write nothing
> at all, so there was no data to show. They now record a normalized error code and a
> customer-safe summary — never provider text, tokens or credentials.

## 6. Paused & Canceled — *BUILT AND SAVED*

- **Base:** Memberships · **Type:** Table
- **Columns:** Member · Plan · Bot · Membership Status · Start Date · Cancellation Date ·
  Cancellation Reason
- **Filter:** `Membership Status is any of` → Paused, Canceled
- **Sort:** `Cancellation Date` Descending

## 7. Founding Member Outreach

The **list** already exists with its attributes provisioned. It needs a view over it.

- Open **Founding Member Outreach** under *Lists* in the sidebar → create a Table view
- **Columns:** Person · Outreach Owner · Outreach Status · Last Touch · Next Follow-up · Response
- **Sort:** `Next Follow-up` Ascending
- **No filter** — membership of the list is the filter. The Waitlist Agent adds High-priority
  leads to it; this is the only list Claude may modify.

---

## When you're done

Spot-check against the spec's Views & Lists sheet: each view's columns, filter, sort field and
direction. That walk-through is the evidence for **AC-CRM-011**.

Several views will legitimately read empty until data flows: lifecycle values only exist from
2026-08-02, and no memberships or brokerage connections have synced yet. Empty is not broken —
compare against the filter, not against the row count.

Also still outstanding, unrelated to views: set `ATTIO_WAITLIST_LIST=ironforge_waitlist` on
`ironforge-customer`, without which waitlist list entries are skipped (the app now logs this
explicitly rather than failing silently).
