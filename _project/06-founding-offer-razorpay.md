# 06 — Founding 10 offer & Razorpay setup

## Decision: where the 70% discount applies

**Only 3 entry packages, sharing one pool of 10 slots:**

| Package | Regular starting price | Founding price (70% off) |
|---|---|---|
| Digital Business Starter | ₹4,999 | ₹1,499 |
| Medical Store Digital Desk | ₹9,999 | ₹2,999 |
| Professional Authority Pack | ₹14,999 | ₹4,499 |

Why these three (validated against Indian market rates, see `07-india-market-rates.md`):
- **Digital Business Starter:** the highest-demand, easiest-to-explain problem for Hindi-first SMBs (Google Maps + WhatsApp). Template-driven delivery in 5–7 days, and GBP before/after data makes a clear case study.
- **Medical Store Digital Desk:** a clear niche. The SOP and message templates are reusable for every chemist.
- **Professional Authority Pack:** writing-only (no tool costs), and the client's LinkedIn profile is a public showcase that attracts other professionals.
- All three are sold as one-time packages at or within market range, so the struck-through price is credible. Customers can upgrade to Business Growth Launch, Digital Saathi Monthly or LinkedIn retainers.

**AI Automation Starter was considered and excluded.** Its ₹7,500 is already well below Indian market rates (₹15k+ per workflow), so 70% off would attract the wrong buyers.

Excluded, and why:
- **Monthly retainers** (Digital Saathi Monthly, LinkedIn): the discount would repeat every month or anchor a price the client expects to keep.
- **High-ticket projects** (Growth Launch, Research, Knowledge-to-Product, Content Engine): the absolute loss is too large, and those buyers are less price-driven.
- **Education**: custom quote.

## Urgency that is legal and honest

The Consumer Protection Act 2019, the CCPA misleading-advertisement guidelines (2022) and the CCPA dark-patterns guidelines (2023, which list "false urgency") mean the offer must follow these rules:

- **Real deadline.** `offer.ends_at` in `src/site.json` is one fixed moment for everyone. The countdown never resets per visitor.
- **Real scarcity.** `slots_total` / `slots_taken` must be true. Update `slots_taken` after every confirmed paid booking.
- **Genuine reference price.** The struck-through price is the regular starting price already published on the site. Don't raise regular prices just before or during the offer.
- **Same scope.** Founding customers get exactly the regular deliverables.
- **No review-for-discount.** Incentivised Google reviews break Google's policy. Case-study use needs written permission and is not a condition of the discount.

This is not legal advice; confirm with your advisor if unsure.

## How the site behaves (automatic)

| State | What visitors see |
|---|---|
| Active, inside window, slots left | Offer section on home. Slim banner on all pages except legal, thanks, 404 and the offer page. Struck price + founding price on the 3 packages. Live countdown and "X/10 slots बाकी". `/offers/founding-10/` terms page (noindex). |
| Deadline passes (visitor already on page) | JS hides all offer UI and shows regular prices instantly. |
| Next build after deadline, or `slots_taken == slots_total` | Offer markup is not generated at all. The weekly Monday workflow rebuilds automatically. |

Analytics events: `offer_view`, `offer_cta_click` and `checkout_click` (label = offer-service). Enquiries arriving through the offer carry `offer=founding-10` in the form data and the WhatsApp message.

## Razorpay: where the keys go

**Short answer: no key goes into this repository. It is public on GitHub, so anyone can read it.**

| Credential | Needed now? | Where it goes |
|---|---|---|
| Key ID (`rzp_test_…` / `rzp_live_…`) | No, Payment Pages don't need it | Later, only if we build custom Checkout: `src/site.json → payments.razorpay_key_id` (public by design) |
| **Key Secret** | No | **Never** in the repo, chat, email or WhatsApp. Only in a server-side secret store (Google Apps Script Script Properties, Cloudflare Worker secret, Vercel/Netlify env var) when a backend that creates orders and verifies signatures exists. |
| Webhook secret | No | Same as Key Secret |

If a secret has been pasted anywhere public, regenerate it: Razorpay Dashboard → Account & Settings → API Keys.

### Recommended now: Razorpay Payment Pages (no code, no keys on the site)

1. Razorpay Dashboard → switch to **Test Mode**.
2. **Payment Pages → Create**, one page per package:
   - Title: e.g. "Founding 10 — Digital Business Starter"
   - Fixed amount: ₹1,499 / ₹2,999 / ₹2,250
   - Customer fields: Name, Phone, Email, Business name, City
   - Description: copy the package deliverables and link to `https://moodily.in/offers/founding-10/`
   - Success message: "Payment मिल गया — 1 working day में WhatsApp पर onboarding शुरू होगी।"
   - If Razorpay offers an expiry or stock limit for the page, set it to the offer deadline / 10.
3. Copy each page URL into `src/site.json → offer.payment_links` for the matching service id.
4. Preview locally with the buttons visible (do **not** commit this build):
   ```bash
   MOODILY_SHOW_TEST_PAYMENTS=1 python3 build.py
   python3 -m http.server 8123
   ```
   Pay with Razorpay test cards/UPI and confirm the success flow.
5. Rebuild normally (`python3 build.py`) before committing. While `payments.mode` is `"test"`, the production build never shows Razorpay buttons (the test suite enforces it). Visitors see "₹X वाला slot पाएँ", which opens the enquiry form tagged with the offer.
6. **Go live:** complete Razorpay KYC and activation, recreate the 3 pages in **Live Mode**, replace the URLs, set `payments.mode` to `"live"`, then build, test and push.

### After every paid booking (2 minutes)
1. Confirm the payment in Razorpay Dashboard → Payments.
2. `src/site.json → offer.slots_taken` += 1.
3. `python3 build.py && python3 tests/check_site.py`, then commit and push.
4. If two payments race past slot 10, refund the extra one within 7 working days (promised in the terms).

### Later (optional): custom Checkout with Orders API
Needed only for an in-page popup, automatic slot counting or instant confirmations. Add a small backend (Apps Script or Cloudflare Worker) that holds the Key Secret, creates orders, verifies `razorpay_signature` and receives the `payment.captured` webhook to increment slots in a Google Sheet. The site then needs only the Key ID.

## Ending or reusing the offer
- **End early:** set `offer.active` to `false`, then build and push.
- **New campaign:** change `id`, `name`, dates, `services`, `payment_links`, and reset `slots_taken` to 0.
