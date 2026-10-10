# /api/webhooks/ghl-translate

GHL workflow webhook. When a Spanish-speaking lead submits the design-intake
survey in GoHighLevel, this endpoint pulls the free-text custom-field answers
off the contact, translates them to English with Claude Haiku, and writes the
translation back to GHL — a `notes_en` custom field plus a contact note — so
the (English-only) team can read the survey without leaving GHL.

## What it does

1. Checks the `x-vibe-secret` header against `VIBE_WEBHOOK_SECRET`.
2. Reads the contact id from the webhook body (`contact_id`, `contactId`, or `id`).
3. Fetches the contact from GHL, and resolves the location's custom-field
   keys to ids (cached in memory for the life of the process).
4. Collects whichever of these Spanish free-text fields have content:
   `customers`, `success_metric`, `competitors`, `sites_liked`,
   `sites_liked_why`, `current_site_dislikes`, `brand_colors`,
   `brand_fonts`, `tagline`, `template_name`, `keywords`,
   `deadline_reason`, `domain_name`, `notes`.
   If none have content, it returns `{skipped:"no free text"}` and does not
   call Claude.
5. Sends the labeled Spanish lines to Claude Haiku (`claude-haiku-4-5`)
   for a factual, line-by-line English translation.
6. Writes the translated block back to the contact's `notes_en` custom field
   (if that field doesn't exist yet in the GHL location, this step is skipped
   and logged — it does not fail the request) and adds a contact note
   ("English translation (auto): ..."). The note is best-effort: a failure
   there is logged but never fails the webhook.
7. Returns `{ ok: true, contactId, fieldsTranslated: <count> }`.

On any upstream failure (GHL or Claude), the route returns that upstream's
status code with a short error message.

## Env vars

| Var | Purpose |
|---|---|
| `VIBE_WEBHOOK_SECRET` | Shared secret this route requires in the `x-vibe-secret` header. If unset, the route returns 503 (fails closed, never open). |
| `GHL_PIT_TOKEN` | GoHighLevel Private Integration Token — sent as `Authorization: Bearer <token>` on every GHL call. |
| `GHL_LOCATION_ID` | GHL sub-account (location) id, used to look up the custom-field id map. |
| `ANTHROPIC_API_KEY` | Anthropic API key for the Claude Haiku translation call. |

Set these in the Render environment for the `ironforge-dashboard` service
(and in `.env.local` for local dev — see `.env.local.example`).

## GHL workflow setup

In the GHL workflow that fires on survey submission, add a **Custom Webhook**
action:

- Method: `POST`
- URL: `https://<render-host>/api/webhooks/ghl-translate` (e.g.
  `https://ironforge-dashboard.onrender.com/api/webhooks/ghl-translate`)
- Headers: `x-vibe-secret: <value of VIBE_WEBHOOK_SECRET>`
- Body: JSON containing the contact id, e.g. `{ "contact_id": "{{contact.id}}" }`

The location also needs a `notes_en` custom field (text/long-text) for the
translated block to be written to — if it doesn't exist, the field write is
skipped (logged) but the contact note still gets added.

## Testing with curl

```bash
curl -i -X POST "https://ironforge-dashboard.onrender.com/api/webhooks/ghl-translate" \
  -H "x-vibe-secret: $VIBE_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"contact_id": "REPLACE_WITH_A_REAL_GHL_CONTACT_ID"}'
```

Expected responses:
- `200 { "ok": true, "contactId": "...", "fieldsTranslated": 3 }` — success.
- `200 { "skipped": "no free text" }` — contact has no Spanish free-text answers.
- `401 { "error": "unauthorized" }` — missing/wrong `x-vibe-secret`.
- `503 { "error": "VIBE_WEBHOOK_SECRET is not configured" }` — env var unset on the server.
- `400 { "error": "..." }` — bad/missing body or contact id.
- Any other status — passed through from GHL or Claude, with a short error message.
