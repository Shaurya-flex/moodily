# 03 — Lead form architecture, WhatsApp, payments, analytics & funnel

Covers deliverable **G** and sections 14–16, 23.

## G. Form architecture

**Location:** `/contact/` (component `@lead-form` in `build.py`). Service is preselected from `?service=<id>` (service ids only — never personal data in URLs).

| Field (`name`) | Type | Required |
|---|---|---|
| `name` | text | ✔ |
| `whatsapp` | tel, 10–15 digits | ✔ |
| `email` | email | ✔ |
| `city` | text (City/Country) | ✔ |
| `role` | Business, Medical Store, Clinic, School, Coaching Institute, Professional, Creator, Startup, Student, Other | ✔ |
| `language` | Hindi / English / Hinglish | ✔ |
| `service` | free-digital-audit, every service id, linkedin-payg, store-product, not-sure | ✔ |
| `budget` | ₹2K–₹5K, ₹5K–₹15K, ₹15K–₹50K, ₹50K+, Need recommendation | ✔ |
| `deadline` | Flexible / 1 week / 2–4 weeks / 1–3 months | |
| `link` | url (existing website/social) | |
| `goal` | text | ✔ |
| `message` | textarea | |
| `attachment_link` | url — **link, not upload** (static hosting; and keeps prescriptions/IDs out) | |
| `consent` | checkbox | ✔ |
| `company_hp` | honeypot (hidden, dropped) | |
| `page`, `submitted_at` | added by JS | |

**Flow**
1. First input → `form_start`.
2. Submit → native validation with `aria-invalid` + error summary.
3. Lead summary stored in `sessionStorage` (not URL).
4. If `site.json → form.endpoint` is set: `fetch(POST, no-cors)` → `/contact/thanks/?s=sent`.
   If empty or network fails: `/contact/thanks/?s=whatsapp` — page asks the user to send the prefilled WhatsApp (lead not lost).
5. `form_submit` fires with `label=service`, `budget`, `role`, `delivery=sent|whatsapp`.
6. Thanks page builds the WhatsApp message from sessionStorage and offers email fallback. Thanks page is `noindex` and disallowed in robots.

### Connect Google Sheets (15 minutes, no backend)

1. Create a Google Sheet "Moodily Leads". Extensions → Apps Script. Paste:

```js
const SHEET = 'Leads';
const FIELDS = ['submitted_at','name','whatsapp','email','city','role','language','service','budget',
  'deadline','link','goal','message','attachment_link','consent','page'];

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.tryLock(10000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sh = ss.getSheetByName(SHEET) || ss.insertSheet(SHEET);
    if (sh.getLastRow() === 0) sh.appendRow(FIELDS);
    const p = e.parameter || {};
    // Prefix values that Sheets would treat as formulas (=,+,-,@) to prevent formula injection.
    const row = FIELDS.map(f => {
      const v = String(p[f] || '').slice(0, 2000);
      return /^[=+\-@]/.test(v) ? "'" + v : v;
    });
    sh.appendRow(row);
    // Optional alert:
    // MailApp.sendEmail('hello@moodily.in', 'New lead: ' + p.service + ' / ' + p.budget, row.join('\n'));
    return ContentService.createTextOutput('ok');
  } finally {
    lock.releaseLock();
  }
}
```

2. Deploy → New deployment → Web app → Execute as **Me**, Who has access **Anyone** → copy the `/exec` URL.
3. Put it in `src/site.json → form.endpoint`, run `python3 build.py`, commit.
4. Test one submission; confirm the row appears. The URL is public by nature — the honeypot, length caps and formula-escaping limit abuse; add reCAPTCHA/Turnstile later if spam appears.

### Later: CRM / n8n
Replace `form.endpoint` with an n8n Webhook node URL (POST, `application/x-www-form-urlencoded`). Field names stay identical, so the site needs no other change. Suggested n8n flow: Webhook → dedupe by WhatsApp → Google Sheet/CRM → WhatsApp/Email alert → create follow-up task (24h SLA). Switch `mode: 'no-cors'` to a normal CORS request once the endpoint returns `Access-Control-Allow-Origin: https://moodily.in`, so failures can be detected.

## WhatsApp (section 16)

- Number: `src/site.json → whatsapp.number` (**confirm**). If emptied, all WhatsApp CTAs fall back to `/contact/`.
- Prefilled template (server-rendered, works without JS):
  ```
  Namaste Moodily,
  Main [role] hoon.
  Mujhe [service] chahiye.
  Mera business/profession [type] hai.
  City [city] hai.
  Budget approx [budget] hai.
  Current website/social link [URL] hai.
  ```
  Service pages substitute role + service; the thanks page substitutes everything the user typed.
- Placements: floating button (all pages), hero, every package card, final CTA, footer, contact, thanks. All tracked as `whatsapp_click` with a placement `label`.

## Payments (section 14)

No provider is approved, so **none is hard-coded**. Architecture:
- `site.json → payments.provider` documents the decision.
- Each product in `products.json` has `status`, `price`, `checkout_url`. When `status: available` **and** price **and** `checkout_url` exist, the card shows "Buy" linking to the hosted payment page and emits `Product` schema; otherwise it shows a waitlist WhatsApp CTA.
- Works with any hosted link: Razorpay Payment Pages/Links, Cashfree Payment Forms, PhonePe, Instamojo (India); Stripe Payment Links, Lemon Squeezy, Gumroad, Paddle (international). Delivery of files is handled by the provider or by an n8n webhook on payment success.
- Services stay quote-first (enquiry → proposal → payment link sent on WhatsApp/email).

## 23. Analytics events

All events push to `window.dataLayer` with `event`, `label`, `page_path` (+ `link_url` for clicks).

| Event | Trigger | Key params |
|---|---|---|
| `hero_cta_click` | Primary CTAs (hero, nav "Free Audit", final CTA, guide CTAs) | label = placement |
| `whatsapp_click` | Any WhatsApp link | label = placement / service id |
| `form_start` | First input in lead form | label = preselected service |
| `form_submit` | Valid submit | label = service, budget, role, delivery |
| `service_view` | Page load of a service page | label = category |
| `price_click` | "Details"/"Enquire" on a package | label = service id |
| `case_study_open` | Case study link / case page view | label = slug |
| `product_view` | Product card ≥50% visible (once) | label = slug |
| `checkout_click` | Buy / waitlist button | label = slug |
| `tool_affiliate_click` | Outbound tool link | label = tool slug |
| `language_switch` | हिं/EN toggle | label = hi/en |
| `audience_select` | Router card (extra) | label = audience |

### GTM setup (owner, ~30 min)
1. Data Layer Variables: `label`, `page_path`, `link_url`, `budget`, `role`, `delivery`.
2. Trigger: Custom Event, regex `^(hero_cta_click|whatsapp_click|form_start|form_submit|service_view|price_click|case_study_open|product_view|checkout_click|tool_affiliate_click|language_switch|audience_select)$`.
3. Tag: GA4 Event, Event Name `{{Event}}`, parameters above. (Requires a GA4 Configuration/Google tag with the Measurement ID — **TODO: add GA4 ID inside GTM**.)
4. GA4 → Admin → Key events: mark `form_submit` and `whatsapp_click`.
5. Preview mode: click each CTA, submit a test form, confirm events.

### Conversion funnel

```
Landing (organic/social/WhatsApp share)
  → service_view / audience_select
    → price_click
      → form_start → form_submit            (primary conversion)
      → whatsapp_click                      (primary conversion)
        → qualified (owner marks in Sheet: budget ≥ ₹5K & fit)
          → proposal sent → paid            (tracked in Sheet/CRM, not GA)
```
Weekly review: sessions → service_view rate; price_click → form/WhatsApp rate by service; submissions by budget band; qualified % ; first-response time.
