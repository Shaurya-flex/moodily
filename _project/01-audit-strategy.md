# 01 — Current-site audit, IA, conversion strategy, pricing presentation

Branch: `feature/moodily-umbrella-platform` · Audit date: 2026-09-13 · Covers deliverables **A, B, C, D, E, F**.
Folder `_project/` is excluded from the public site by Jekyll (leading underscore).

## A. Current-site audit (before this branch)

| Area | Finding | Severity | Action taken |
|---|---|---|---|
| Stack | One hand-written `index.html` (774 lines, inline CSS/JS). No build, no framework. | — | Kept static. Added a stdlib-only Python generator (`build.py`) so ~25 pages share one layout. |
| Hosting | GitHub Pages, legacy Jekyll build from `main:/`, CNAME `moodily.in`, HTTPS enforced, cert valid to 2026-11-24. | — | **Unchanged.** Output is still plain HTML at repo root. `_config.yml` excludes source/docs. |
| Automation | `weekly-tip.yml` rewrote an AUTO-GENERATED block in `index.html` every Monday. | — | Preserved. Block moved to `src/pages/learn.html`; workflow now runs rebuild → build → checks. |
| Analytics | GTM `GTM-MRNHLVC9` in head; no `<noscript>` iframe; **zero custom events**. | High | GTM kept, noscript added, 11 dataLayer events implemented (see 03). |
| WhatsApp | Every WhatsApp CTA pointed to `wa.me/91XXXXXXXXXX` — **broken in production**. Real number `919354123255` was committed by owner in `1a11158` then overwritten. | **Critical** | Restored from history in `src/site.json` — **owner must confirm**. |
| Payments | Razorpay SDK loaded on every page with placeholder key `rzp_live_XXXX`; "Book & Pay" always failed. | **Critical** | Removed SDK and fake checkout. CTAs → enquiry form / WhatsApp. Provider-agnostic payment-link architecture (see 03). |
| Auth | "Sign In / Register" modal collected email+password and sent them nowhere. | High (trust/security) | Removed. |
| Intake form | Only opened WhatsApp; no storage, no tracking, no qualification fields. | High | Replaced with full qualification form (see 03). |
| Claims | "★★★★★ 4.8 · 1,200+ learners", "Official Certs", "IIT Madras + Govt of India certificates", "Bharat Sarkar Pramaanpatra" on 3rd-party courses, ticker of provider logos implying partnership, "Earn from your first project in 90 days", "Unlimited revisions" (×2). | **Critical** (consumer-protection / trust) | All removed. Curation disclaimer added site-wide. `tests/check_site.py` fails the build if they return. |
| Schema | Organization with Offer prices; FAQPage claiming "certified courses from Google, IIT Madras, IBM and Government of India". | High | Rebuilt: Organization (+disambiguation), WebSite, BreadcrumbList, Service, FAQPage, Article; Product only for purchasable items. |
| SEO | `<link rel=sitemap>` to non-existent `sitemap.xml`; no robots.txt; meta keywords; no og:image; one URL for everything; breadcrumb links to `#`. | High | Generated sitemap/robots, unique titles/descriptions, canonicals, OG image, 24 indexable URLs. |
| Performance | Font Awesome full CSS (~100 KB), 3 Google font families incl. unused Poppins, Razorpay SDK, reveal animations hiding content until JS. | Medium | Removed FA + Razorpay + Poppins; inline SVG icon; content visible without JS; one CSS + one small deferred JS. |
| Accessibility | Clickable `<div>`s, no labels on auth inputs, icon buttons without names, stars as `<i onclick>`. | Medium | Native `<details>`, `<button>`, labelled form controls, skip link, focus styles, 44px targets. |
| Tools | Affiliate cards linking to `#` or a Coursera search for "AI Writing Assistant". | Medium | Tools page with what/why/use-case/pros/limits/alternatives/tutorial; plain official links until real affiliate URLs exist. |

**Preserved:** brand tokens (violet/saffron/teal, dark default + light toggle), "AI Seekho. Kamai Karo." line (now on /learn/), full 5-stage curriculum with private star ratings, Hindi/English toggle (on bilingual pages), all existing prices (AI workflows 7.5k/18k/35k, LinkedIn 15k/28k/50k, PAYG 5k/12k/20k), weekly tip automation, old `#anchors` (redirected client-side to new pages).

## B. Information architecture

| Route | Division | Language | Purpose |
|---|---|---|---|
| `/` | Umbrella | hi | Router: सीखें / बनवाएँ / खरीदें → audience router → services → samples → store → quality workflow → FAQ → CTA |
| `/learn/` | Learn | en + hi toggle | Free AI path (migrated) |
| `/guides/` + 3 articles | Learn | hi | AEO answers (Maps, GBP cost, WhatsApp orders) |
| `/digital-saathi/` | Digital Saathi | hi | Primary Hindi services page |
| `/services/` | All | hi | Full price table + all cards |
| `/services/local-business/` | Digital Saathi | hi | Starter ₹4,999 · Growth Launch ₹12,999 · Monthly ₹4,999/mo |
| `/services/medical-store/` | Digital Saathi | hi | 12-step human-approval workflow · ₹9,999 |
| `/services/ai-workflows/` | Digital Saathi | hi | 7,500 / 18,000 / 35,000 |
| `/services/professionals/` | Studio | hi | Authority Pack ₹14,999 · LinkedIn tiers · PAYG (`#linkedin`) |
| `/services/education/` | Studio | hi | B2B + B2C, custom quote |
| `/services/creators/` | Studio | hi | Content Sprint ₹9,999 |
| `/services/research/` | Studio | en | Research Sprint ₹14,999 |
| `/services/knowledge-to-product/` | Studio | en (international) | ₹19,999 |
| `/case-studies/` (+ `/case-studies/<slug>/` when published) | All | hi/en | Portfolio hub + template |
| `/store/` | Store | hi | 7 categories, waitlist |
| `/tools/` | Learn | hi | Tool guides + disclosure |
| `/about/`, `/contact/`, `/contact/thanks/` (noindex) | — | hi | Entity, intake, confirmation |
| `/privacy/`, `/terms/`, `/refund/` | — | hi | Legal (drafts — lawyer review) |

**Locale decision:** the old site did not use locale routes (one URL + CSS toggle), so per the brief no `/hi` `/en` split was created. Each URL has one primary language set in `<html lang>`; no hreflang needed. This avoids duplicating ~25 pages of thin translations. Revisit only if English-market pages (e.g. knowledge-to-product) need Hindi twins.

## C. Conversion strategy

**Objective:** qualified enquiries → first paying customers, without disrupting the learning audience.

1. **One lead magnet: मुफ़्त Digital Audit.** Low-friction, specific promise (3 fixes in 2 working days), qualifies by service/budget. Every page's primary CTA.
2. **WhatsApp as the default channel** for Hindi-first SMB owners: sticky floating button, prefilled structured message (role/service/type/city/budget/URL), plus WhatsApp hand-off after the form.
3. **Router before catalogue:** "आप कौन हैं?" cards reduce choice overload; each lands on a page with only the relevant packages.
4. **Trust through specificity, not metrics:** exact deliverables, "क्या शामिल नहीं", defined revisions, owner-controlled accounts, quality workflow, "no ranking guarantee". No numbers we cannot prove.
5. **Learning audience protected:** `/learn/` keeps its content and CTA hierarchy; services appear there only as a secondary "no time to learn?" card.
6. **Samples honesty:** drafts shown as real project titles; full case studies publish only with evidence — first 30-day priority.

Funnel and events: see `03-forms-payments-analytics.md`.

## D & E. Homepage and service-page copy

Exact, production copy lives in the source files (single source of truth — do not duplicate here):
- Homepage: `src/pages/index.html`
- Digital Saathi: `src/pages/digital-saathi.html`
- Service pages: `src/pages/services/*.html`
- Package cards (who/problem/deliverables/timeline/not included/revisions/support/case study): `src/data/services.json`

## F. Pricing presentation

- Always "शुरुआत ₹X से" / "Starts at ₹X" + "Final quote scope देखकर लिखित में".
- Monthly plans show "/महीना"; education shows "Scope के अनुसार quote" (**owner to set a starting price**).
- Every card: who it's for, problem, deliverables, timeline, revisions & support, not included (collapsed), related sample, two CTAs (enquiry with service preselected; WhatsApp with service prefilled).
- One comparison table on `/services/` — the "price shopper" page.
- **Deliverable scopes for the new launch offers are drafts written for owner approval** (quantities chosen to be deliverable at the price). Adjust in `services.json`; the build rejects any "unlimited".
