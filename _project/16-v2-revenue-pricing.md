# 16 — v2 revenue architecture (pricing v1-2026)

**Single source of truth:** `src/data/pricing.json`. `build.py` fails the build if:
- a price disagrees with `services.json`;
- a checkout link is not an `https://rzp.io/rzp/…` Payment Link;
- a quote or onboarding product gets a checkout link;
- a checkout product isn't `price_mode: exact`.

`tests/check_site.py` fails if any rendered Razorpay link is not in `pricing.json`, or if a button's product or amount doesn't match its link.

| Product | Price | Checkout | Reference |
|---|---|---|---|
| Free Digital Audit | ₹0 | /contact/?service=free-digital-audit | — |
| Digital Action Blueprint | ₹499 | rzp.io/rzp/KzW5JJ4C | MOOD-BLUEPRINT-499 |
| WhatsApp Business Basic | ₹1,499 | rzp.io/rzp/DncsbZ0 | MOOD-WA-1499 |
| Google Business Quick Fix | ₹1,999 | rzp.io/rzp/32F3Jh5 | MOOD-GBP-1999 |
| Founding 10 — Google + WhatsApp Starter | ₹1,499 | rzp.io/rzp/M9nG1WO | MOOD-FOUNDING10-1499 |
| Digital Starter — advance | ₹2,500 (+ ₹2,499 before handover) | rzp.io/rzp/HSbE7we | MOOD-STARTER-ADV-2500 |
| Digital Starter — full | ₹4,999 | rzp.io/rzp/fm6B5Jn | MOOD-STARTER-4999 |
| Local Business Growth | from ₹12,999 | written quote → 50% / 50% | — |
| Digital Saathi Monthly | ₹9,999/month | WhatsApp → onboarding; plan_TdqCrbIKGzjq2d is infrastructure only, never a button | MOOD-SAATHI-9999M |

**Founding 10:**
- The scope is exactly WhatsApp Business Basic plus Google Business Quick Fix. That's why "individually ₹3,498, you save ₹1,999" is true.
- There's no deadline and no countdown.
- A remaining-slot count is shown only when `founding.slots_confirmed` is true.
- Customers are tracked as F01…F10 in the private MOODILY-OS folder, not in this repo.

**Blueprint credit:** ₹499 is adjusted manually into a qualifying ₹4,999+ implementation taken within 14 days. It is not a Razorpay discount. The terms are on /terms/#pricing-terms.

**Analytics (GTM dataLayer, no personal data):**
- Clicks: `*_checkout_clicked` plus `payment_outbound_clicked {product, amount}`.
- Views: `*_viewed`, fired once per page when a card is 50% visible.
- Other events: `free_audit_started`, `free_audit_completed` (on-site form only; count Google Form completions from the response sheet), `growth_quote_requested`, `digital_saathi_contact_clicked`, `whatsapp_contact_clicked` (alias of `whatsapp_click`).

**Deliberately not built:**
- Login or dashboard.
- Self-serve subscriptions.
- Live slot inventory.
- Automatic credits.
- A second payment backend (the 50% Worker flow is still PR #13).
