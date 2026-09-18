# 14 — 50% deposit checkout: owner SOP

**Status:** built and tested on branch `feature/deposit-checkout`, with **payments OFF on the public site**.
The pay buttons appear only when `payments.mode` is `"live"` **and** `payments.api_base` points to a deployed backend.

## How it works

```
Service page → "₹X देकर Order Confirm करें" → /checkout/?service=ID   (noindex)
  summary (total · 50% now · balance · timeline · revisions)
  name + WhatsApp + email + Terms/Refund/Privacy checkbox
→ POST /api/payment/create-order {service_id, customer}
     the server looks the price up in checkout-prices.json → deposits (a browser amount is ignored)
     creates a Razorpay order: amount = deposit, receipt = MDLY-YYYYMMDD-XXXXXX, notes = service + split + customer
→ Razorpay Checkout (UPI/card/netbanking, prefilled)
→ POST /api/payment/verify   HMAC-SHA256(order_id|payment_id, KEY_SECRET), constant-time compare
→ /order-confirmed/?order=order_…   (noindex)
     same tab: details come from sessionStorage; later visits ask GET /api/payment/status/:order_id (no personal data returned)
     "Project Brief भरें →" opens the Google Form prefilled with category, service, Order ID and the advance line
Razorpay → POST /api/payment/webhook   (X-Razorpay-Signature over the raw body, RAZORPAY_WEBHOOK_SECRET)
```

- **Who is eligible:** `price_mode: "exact"`, or `"starts_at"` **plus** `"fixed_scope": true` set by you in `src/data/services.json`. Monthly, free and custom-quote services never get a pay button. Today 6 services are eligible (see the table below).
- **Split:** deposit = half the price, rounded **up** to the rupee; balance = total − deposit. Example: ₹499 → ₹250 now, ₹249 later.
- **Balance:** it is **never auto-charged.** Before final delivery, send the customer a Razorpay Payment Link for the balance from the Dashboard, and put the MDLY Order ID in its description.
- **Refunds:** follow the published /refund/ page. The advance is refundable before work starts, minus approved third-party costs. Do not call it non-refundable unless you change that policy.

## Go-live checklist (owner)

1. `cd worker && npx wrangler login` (one-time Cloudflare login).
2. Store the secrets **in Cloudflare, not in any file:**
   - `npx wrangler secret put RAZORPAY_KEY_ID`
   - `npx wrangler secret put RAZORPAY_KEY_SECRET`
   - `npx wrangler secret put RAZORPAY_WEBHOOK_SECRET`
3. In `worker/wrangler.toml`, set `PAYMENT_MODE = "live"` for live keys. The Worker refuses to run if the key prefix and the mode disagree. Then run `npx wrangler deploy`.
4. Open `https://<worker-url>/api/payment/health`. It should show `key_mode` = your mode, `mode_matches_key: true`, all three `*_configured: true`, `catalogue_reachable: true` and `deposit_services: 6`.
5. In the Razorpay Dashboard, go to **Settings → Webhooks → Add**:
   - URL: `https://<worker-url>/api/payment/webhook`
   - Secret: the same RAZORPAY_WEBHOOK_SECRET
   - Events: `payment.captured`, `payment.failed`, `order.paid`
6. In `src/site.json`, set `payments.api_base` to the Worker URL and `payments.mode` to `"live"`. Then rebuild, commit and deploy.
7. Do **one test in test mode first:** use test keys with `PAYMENT_MODE = "test"`, a Razorpay test card or UPI `success@razorpay`, and check /order-confirmed/ and the Form prefill. Only then switch to live keys.
8. A real ₹ live payment test needs your explicit decision. Refund it from the Dashboard afterwards.

## Local testing (never uses .env live keys)

1. Create a file **outside the repo** containing:
   - `RAZORPAY_KEY_ID=rzp_test_…`
   - `RAZORPAY_KEY_SECRET=…`
   - `RAZORPAY_WEBHOOK_SECRET=any-string`
   - `PAYMENT_MODE=test`
2. Start the preview:

```
MOODILY_SHOW_TEST_PAYMENTS=1 MOODILY_CHECKOUT_API=/ python3 build.py
MOODILY_ENV_FILE=/path/to/test.env python3 scripts/dev_server.py
```

3. Open `http://localhost:8124/checkout/?service=digital-visiting-card`.
4. Afterwards, run `python3 build.py` (no flags) before committing. CI fails a build that still has test-mode buttons.

The dev server refuses live keys unless `MOODILY_ALLOW_LIVE_LOCAL=1` is set, so a local test never charges a real card by accident.

## Daily operations — matching a payment to a brief

| Where | What you see |
|---|---|
| Razorpay → Orders | Receipt = **MDLY Order ID**. Notes = service, total/deposit/balance, customer name, phone and email. Status is `paid`. |
| Google Form responses | "Offer / Package Code" = **MDLY Order ID**; "Sample or estimate" = `Advance ₹X paid · balance ₹Y … · order_…` |
| WhatsApp | The customer's prefilled message includes the MDLY Order ID and Payment ID |

Order status to track in your Sheet: `DEPOSIT PAID — BRIEF PENDING` → `BRIEF RECEIVED` → `IN PROGRESS` → `PREVIEW SENT` → `BALANCE LINK SENT` → `BALANCE PAID` → `DELIVERED`.

A brief without a matching **paid** Razorpay order is just an enquiry. Always confirm "paid" in the Dashboard; a Form entry is never proof of payment.

## Recommended Google Form changes (owner, in the Form editor)

- Add a short-answer question **"Moodily Order ID"**, and send its `entry.NNNN` id so it can be prefilled. Until then, the Order ID goes into "Offer / Package Code".
- Optional: add an "Order status" column in the linked Sheet for the statuses above.

## Not done / needs you

- **Backend not deployed:** GitHub Pages cannot hold secrets. Steps 1–6 above are required before any customer can pay.
- **GSTIN / business name:** empty in `site.json`. Invoices and receipts show only what Razorpay has on file. Nothing was invented.
- **starts-at packages** (38 services) stay "Exact Quote लें" until you define a fixed scope and add `"fixed_scope": true`.
- **Founding-10 offer** buttons (full discounted price) still use the old `/api/create-order`. The offer ends on 2026-09-20.

## Security rules (enforced by code, CI and pre-commit)

- The secret key and the webhook secret exist only as Worker secrets (and in your local .env for the dev server). The browser receives only the key **id**, per order, from the server.
- `scripts/secret_scan.py` runs in CI and the pre-commit hook.
- The status and verify responses never include a customer's name, phone or email. An order id alone reveals nothing personal.
- Analytics events (`deposit_cta_click`, `checkout_start`, `razorpay_open`, `payment_success_verified`, `payment_failed`, `payment_cancelled`, `payment_verify_failed`, `brief_open`) carry only the service id.
- The server never logs secrets, signatures or customer details.

## Service audit (49 active services)

| # | Service | Price type | Price | Page | Primary action |
|---|---|---|---|---|---|
| 1 | Google + WhatsApp Starter (`digital-business-starter`) | starts_at | ₹4,999 | /services/local-business-digitalization/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 2 | Local Business Growth (`business-growth-launch`) | starts_at | ₹12,999 | /services/local-business-digitalization/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 3 | Digital Saathi Monthly (`digital-saathi-monthly`) | starts_at | ₹9,999/month | /services/local-business-digitalization/ | Exact Quote लें (monthly retainer) |
| 4 | Medical Store Digital Desk (`medical-store-digital-desk`) | starts_at | ₹9,999 | /services/medical-store/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 5 | Professional Authority Pack (`professional-authority-pack`) | starts_at | ₹14,999 | /services/professionals/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 6 | LinkedIn Writing — Essential (`linkedin-essential`) | starts_at | ₹15,000/month | /services/professionals/ | Exact Quote लें (monthly retainer) |
| 7 | LinkedIn Writing — Growth (`linkedin-growth`) | starts_at | ₹28,000/month | /services/professionals/ | Exact Quote लें (monthly retainer) |
| 8 | LinkedIn Writing — Authority (`linkedin-authority`) | starts_at | ₹50,000/month | /services/professionals/ | Exact Quote लें (monthly retainer) |
| 9 | Creator Content Sprint (`creator-content-sprint`) | starts_at | ₹9,999 | /services/creators/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 10 | Research Intelligence Brief (`research-intelligence-sprint`) | starts_at | ₹9,999 | /services/research-intelligence/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 11 | Knowledge-to-Product (`knowledge-to-product`) | custom_quote | — | /services/knowledge-to-product/ | Exact Quote लें → /contact/ |
| 12 | Study Material Bundle (`education-content-pack`) | starts_at | ₹9,999 | /services/education-content/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 13 | AI Automation Starter (`ai-automation-starter`) | starts_at | ₹7,500 | /services/ai-workflows/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 14 | Workflow (`ai-workflow-package`) | starts_at | ₹18,000 | /services/ai-workflows/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 15 | Content Engine (`ai-content-engine`) | starts_at | ₹35,000 | /services/ai-workflows/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 16 | PPT Formatting / Design (`presentation-design-only`) | starts_at | ₹1,999 | /services/presentation-design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 17 | Content + Presentation (`presentation-content-design`) | starts_at | ₹9,999 | /services/presentation-design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 18 | Research + Strategy Presentation (`presentation-research-content-design`) | starts_at | ₹14,999 | /services/presentation-design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 19 | Static Invitation (`invitation-digital`) | exact | ₹799 | /services/digital-invitation/ | Pay 50% ₹400 → /checkout/ (balance ₹399) |
| 20 | Animated / Video Invitation (`invitation-animated`) | exact | ₹1,999 | /services/digital-invitation/ | Pay 50% ₹1,000 → /checkout/ (balance ₹999) |
| 21 | Business Document Template (`business-document-template`) | starts_at | ₹799 | /services/design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 22 | Starter Brand Kit (`business-identity-kit`) | starts_at | ₹9,999 | /services/design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 23 | Poster / Flyer Design (`print-design-single`) | exact | ₹799 | /services/design/ | Pay 50% ₹400 → /checkout/ (balance ₹399) |
| 24 | Social Media Post Pack (`social-post-pack`) | starts_at | ₹2,499 | /services/social-media-design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 25 | Carousels & Thumbnails Pack (`social-carousel-thumbnail-pack`) | starts_at | ₹3,499 | /services/social-media-design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 26 | Social Campaign Kit (`social-campaign-kit`) | starts_at | ₹6,999 | /services/social-media-design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 27 | मुफ़्त Digital Audit (`free-digital-audit`) | free | — | /services/google-business-profile/ | Free — Digital Audit / WhatsApp |
| 28 | Google Business Profile Optimization (`google-business-fix`) | starts_at | ₹1,999 | /services/google-business-profile/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 29 | WhatsApp Business Basic Setup (`whatsapp-business-setup`) | exact | ₹1,499 | /services/whatsapp-business/ | Pay 50% ₹750 → /checkout/ (balance ₹749) |
| 30 | Local Business Digital Starter (`local-business-digital-starter`) | starts_at | ₹6,999 | /services/local-business-digitalization/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 31 | Local Business Complete (`local-business-complete`) | starts_at | ₹24,999 | /services/local-business-digitalization/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 32 | Landing Page (`landing-page`) | starts_at | ₹7,999 | /services/business-website/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 33 | Business Website (`business-website`) | starts_at | ₹19,999 | /services/business-website/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 34 | Advanced Booking Website (`lead-booking-website`) | custom_quote | — | /services/business-website/ | Exact Quote लें → /contact/ |
| 35 | Business Brochure (`business-brochure`) | starts_at | ₹2,999 | /services/design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 36 | Catalogue (`product-catalogue`) | starts_at | ₹7,999 | /services/design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 37 | Digital Visiting Card (`digital-visiting-card`) | exact | ₹499 | /services/design/ | Pay 50% ₹250 → /checkout/ (balance ₹249) |
| 38 | Social Creative (`social-creative-single`) | exact | ₹599 | /services/social-media-design/ | Pay 50% ₹300 → /checkout/ (balance ₹299) |
| 39 | Logo Design (`logo-starter`) | starts_at | ₹4,999 | /services/design/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 40 | Wedding Digital Suite (`wedding-digital-suite`) | starts_at | ₹4,999 | /services/digital-invitation/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 41 | Educational PDF / Module (`educational-pdf-module`) | starts_at | ₹4,999 | /services/education-content/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 42 | Competitive Intelligence (`competitive-intelligence`) | starts_at | ₹24,999 | /services/research-intelligence/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 43 | Research Dossier (`research-dossier`) | custom_quote | — | /services/research-intelligence/ | Exact Quote लें → /contact/ |
| 44 | B2B Digital Sales Kit (`b2b-digital-sales-kit`) | starts_at | ₹24,999 | /services/b2b-digital-sales/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 45 | Monthly Social Content (`content-growth-retainer`) | starts_at | ₹9,999/month | /services/social-media-design/ | Exact Quote लें (monthly retainer) |
| 46 | Coaching Digital Starter (`coaching-digital-starter`) | starts_at | ₹6,999 | /services/coaching-digital-services/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 47 | Coaching Growth (`coaching-growth`) | starts_at | ₹14,999 | /services/coaching-digital-services/ | Exact Quote लें → /contact/ (starts-at; needs fixed_scope to be payable) |
| 48 | Monthly Digital Saathi (Coaching) (`coaching-monthly-saathi`) | starts_at | ₹4,999/month | /services/coaching-digital-services/ | Exact Quote लें (monthly retainer) |
| 49 | Pitch Deck (`pitch-deck`) | custom_quote | — | /services/presentation-design/ | Exact Quote लें → /contact/ |

Totals: {'starts_at': 38, 'custom_quote': 4, 'exact': 6, 'free': 1} · deposit-eligible: 6
