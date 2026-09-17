# 13 — Google Form lead capture (V1)

**Decision: a standard Google Form wired to a Google Sheet. No Apps Script.**
Google Forms already stores every response and populates its linked Sheet. Apps Script stays on the
shelf for later (notifications, lead scoring, CRM sync) — it is not needed to capture a lead.

## Status: LIVE

The Form is published, open to anyone with the link, requires no sign-in, and writes to its linked
Sheet. `src/data/intake.json` carries the public `/viewform` URL and all four verified entry IDs.

**Only the public Form URL is committed.** The Form-edit URL and the Sheet URL are owner-only
operational links; `validate_form_prefill()` fails the build if either ever appears in the config.

### The dropdown trap, and the guard against it

`Service Category` (entry.732529302) is a **dropdown**. Google silently discards any prefill value
that is not an exact option string. Moodily's own category labels did **not** match — 7 of 14 would
have been dropped (`Business Design`, `Social Media`, `Creator Content`, `Educational Material`,
`Research`, `Website / Google Business`, `Print-ready Design`).

`intake.json` now stores the Form's 16 real options plus three mappings (by intake category, by
service category, by service id), and `validate_form_prefill()` fails the build if any mapping — or
any active service — resolves to something the Form does not offer. All 49 active services resolve
to a real option.

## Original setup notes (kept for reference)

### 1. Build the Form
Fields, in this order. `*` = mark Required in the Form.

| # | Question | Type | Req |
|---|---|---|---|
| 1 | नाम / Name | Short answer | * |
| 2 | WhatsApp number | Short answer | * |
| 3 | Email | Short answer | |
| 4 | City / Country | Short answer | |
| 5 | Role / Customer type | Dropdown | |
| 6 | Selected Service | Short answer *(prefilled)* | * |
| 7 | Selected Sample | Short answer *(prefilled)* | |
| 8 | Primary Goal | Paragraph | * |
| 9 | Budget | Dropdown | * |
| 10 | Deadline | Short answer / Date | * |
| 11 | Preferred Language | Dropdown (Hindi / English / दोनों) | |
| 12 | Detailed Requirement | Paragraph | |
| 13 | Reference / Source link | Short answer | |
| 14 | Consent | Checkbox | * |

**No file upload in V1** — it forces a Google sign-in and loses people. Ask for a
Drive / Dropbox / Canva / website link in field 13 instead.

### 2. Link it to a Sheet
Form → **Responses** → **Link to Sheets**. Responses land there automatically, forever.

### 3. Paste the URL
`src/data/intake.json` → `"form_url"` — the Form's `.../viewform` share link.
**That one line is what unblocks launch.**

### 4. (Recommended) Prefill IDs
Form ⋮ → **Get pre-filled link** → answer questions 5, 6, 7 → Copy link. The link contains
`entry.123456789=...`. Put those numbers in `src/data/intake.json` → `entry_ids`:

| Key | Prefills | Comes from |
|---|---|---|
| `service_category` | the Form's category question | Q5 |
| `sub_service` | the exact service name | Q6 |
| `sample_or_estimate` | the sample title, or a website estimate range | Q7 |
| `offer_code` | the Founding-10 code, when that offer is live | a hidden/short question |

Leave any of them empty and the Form still opens — the visitor just answers that one themselves.
**Never guess an entry ID: a wrong number silently drops the answer.**

## Recommended Sheet columns

Form writes columns A–O; the owner keeps P–Y by hand. That is the V1 CRM — no custom CRM yet.

**From the Form:** Timestamp · Name · WhatsApp · Email · Location · Role · Service · Sample ·
Goal · Budget · Deadline · Language · Message · Reference Link · Consent

**Owner-managed:** Status · Priority · Quoted Price · Quote Date · Follow-up Date · Won/Lost ·
Payment Status · Delivery Date · Revenue · Notes

## How it behaves, by configuration

| `form_url` | What `/contact/` shows | Where the lead goes |
|---|---|---|
| **set** | "Requirement form भरें" → opens the Form prefilled, in a new tab | Google Form → linked Sheet. Permanent. |
| **empty** *(today)* | the built-in form, submit button reads **"WhatsApp पर भेजें →"** | Opens WhatsApp with every field filled in, one tap. |

In the fallback the page says plainly: *"यह form WhatsApp पर भेजा जाएगा … तब तक Moodily तक कुछ नहीं
पहुँचता."* Moodily never claims to have received an enquiry it has not received.

## The lead-loss fix

Before: an empty endpoint meant submit wrote to `sessionStorage`, redirected to a thank-you page, and
hoped the visitor then tapped WhatsApp. Close the tab at that point and the lead was gone.

Now: submit **opens WhatsApp directly with the filled enquiry**. One action, not two. The thank-you
page remains as a backstop if the popup is blocked. `?s=sent` (a real server submission) and
`?s=whatsapp` (hand-off) show different copy, so the confirmation is never a lie.

## Testing once the URL is pasted

1. `python3 build.py`
2. Open `/samples/digital-invitation/` → **इसे मेरे लिए बनाइए**
3. `/contact/?service=invitation-digital&sample=digital-invitation` should name the sample and show ₹799
4. **Continue Requirement Form →** opens the Form with Service and Sample already answered
5. Submit → the row appears in the linked Sheet
6. Repeat on a phone, in dark mode, and check the browser Back button returns cleanly
