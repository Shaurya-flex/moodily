# 09 — Service commerce + Digital Saathi (2026-09-14)

Goal: a buyer lands, identifies their problem, sees a matching solution, a real sample and the starting price, and submits a qualified requirement within 2–3 minutes. The free learning section is unchanged.

## 1. Repo audit (before this change)

| Area | State found |
|---|---|
| Framework | Static site, stdlib Python generator (`build.py`) → GitHub Pages (`main:/`, moodily.in). No runtime framework. |
| Routes | 8 service pages + 4 draft landing pages (presentation-design, invitation-design, business-documents, social-media-design) + digital-saathi, services index, contact, offers, learn, guides, store, tools, legal. |
| Components | Token components in `build.py`; data in `src/data/*.json`; single CSS/JS. |
| Pricing | `services.json` single source (price tokens enforced by tests); 13 draft-priced packages from 2026-09-14 morning. |
| Contact | Branded Google Form wrapper with service/offer prefill; built-in fallback form while `intake.json form_url` is empty. |
| WhatsApp | Prefilled messages on every CTA; floating button. |
| Analytics | GTM `GTM-MRNHLVC9`, dataLayer events via `data-track`. |
| Payments | Razorpay Standard Checkout (Worker + dev server) hidden until `payments.mode = live`. |
| Assets / portfolio | No real samples published; 11 case studies in draft. |
| Language | Hindi-first single URLs, some English pages (research, knowledge-to-product). |

## 2. Routes and components affected

**New pages:** `/services/education-business/`, `/services/wedding-event/`, `/services/b2b/`, `/services/websites/`, `/services/google-whatsapp/`, `/services/design/`, `/services/estimator/`.
**Renamed (old URL → noindex redirect page, `src/data/redirects.json`):** presentation-design → `/services/presentations/`, invitation-design → `/services/invitations/`, business-documents → `/services/design/`, social-media-design → `/services/social-media/`, education → `/services/education-content/`.
**Updated:** home (need router, customer-type router, real samples, how it works), digital-saathi, services index (finder + price list), local-business (tiers), research (dossier), all service pages (samples, third-party note, how it works), case-studies (published samples).

**New components (`build.py`):**

| Token | Output |
|---|---|
| `<!--@need-router -->` | "आपको क्या करवाना है?" 8 need cards with starting price |
| `<!--@customer-router -->` | 11 customer types; first 4 on mobile, rest behind "सभी देखें" |
| `<!--@tiers ids="a,b,c" recommended="b" -->` | Starter / Growth (RECOMMENDED) / Premium cards |
| `<!--@hero-ctas service="id" audit="yes" -->` | Quote · WhatsApp · Sample · Estimate (+ free audit) |
| `<!--@samples services="a,b" ids="x" -->` | Real samples (with kind label) + linked draft case studies; honest placeholder when none |
| `<!--@before-after id="…" -->` | Concept illustration, always labelled "Concept illustration — client project नहीं" |
| `<!--@finder -->` | Package search + 9 filter chips + customer-type select |
| `<!--@estimator -->` | Client-side indicative range estimator |
| `<!--@third-party-note -->`, `<!--@how-it-works -->` | Cost disclosure; 8-step process |

Package detail cards now show what the client gets, timeline, starting price and scope note, revisions, delivery format, third-party costs, the related sample, and Quote / WhatsApp / Sample / Estimate / Free audit CTAs.

## 3. Service data schema (`src/data/services.json`)

| Brief field | JSON key | Notes |
|---|---|---|
| id / slug | `id`, `slug` | slug = id (stable anchors and offer links) |
| category | `category` | page group |
| customerTypes | `customer_types` | ids from `routers.json customer_types` (validated) |
| title | `name` | |
| shortDescription | `tagline` | |
| problemSolved | `problem` | |
| deliverables | `deliverables` | |
| startingPrice | `price_from` | `0` = FREE, `null` = custom quote |
| recommendedPrice | `recommended_price` | not displayed until the owner sets it |
| priceType | `price_unit` | `one-time` · `month` · `free` · `custom` |
| timeline | `timeline` | |
| revisionRounds | `revision_rounds` (+ `revisions` text) | integer 0–3; build rejects "unlimited" |
| editableSource | `editable_source` | shown under Delivery format |
| thirdPartyCosts | `third_party_costs` | codes → `third_party_cost_labels` |
| sampleIds | `sample_ids` | ids in `samples.json` |
| caseStudyIds | `case_study_ids` | slugs in `case_studies.json` |
| formPrefillURL | `form_prefill_url` | full Google Form prefilled URL (wins over intake.json) |
| whatsappMessage | `whatsapp_message` | optional custom prefilled text |
| featured / active | `featured`, `active` | inactive packages disappear everywhere |
| — | `tier`, `filters`, `keywords`, `formats` | tiers, finder filters/search, delivery formats |

The build validates every package: customer types, filters, third-party codes, formats, samples, case studies, tier, price type vs. price, and revision rounds.

## 4. Pricing QA — owner-approved starting prices (2026-09-14)

| Brief item | Package id | Displayed |
|---|---|---|
| Digital Audit | free-digital-audit | FREE |
| Google Business Fix / Optimization | google-business-fix | ₹2,499 |
| Google + WhatsApp Starter | digital-business-starter | ₹4,999 |
| Local Business Digital Starter | local-business-digital-starter | ₹6,999 |
| Landing Page | landing-page | ₹6,999 |
| Business Website | business-website | ₹14,999 |
| Lead / Booking Website | lead-booking-website | ₹24,999 |
| Business Brochure | business-brochure | ₹2,499 |
| Catalogue | product-catalogue | ₹4,999 |
| Digital Visiting Card | digital-visiting-card | ₹799 |
| Poster / Flyer | print-design-single | ₹799 |
| Social Creative | social-creative-single | ₹499 |
| Logo Starter | logo-starter | ₹3,499 |
| Logo + Mini Brand Kit | business-identity-kit | ₹7,999 |
| Static Invitation | invitation-digital | ₹799 |
| Animated Invitation | invitation-animated | ₹1,999 |
| Wedding Digital Suite | wedding-digital-suite | ₹4,999 |
| 10-slide PPT Design | presentation-design-only | ₹4,999 |
| PPT Content + Design | presentation-content-design | ₹8,999 |
| Research + Strategy Presentation | presentation-research-content-design | ₹14,999 |
| Educational PDF / Module | educational-pdf-module | ₹4,999 |
| Knowledge-to-Product | knowledge-to-product | ₹14,999 |
| Research Intelligence Brief | research-intelligence-sprint | ₹9,999 |
| Deep Competitive / Research Dossier | research-dossier | ₹24,999 |
| B2B Digital Sales Kit | b2b-digital-sales-kit | ₹24,999 |
| Digital Saathi Care | digital-saathi-monthly | ₹3,999/month |
| Local Growth | local-growth-monthly | ₹7,999/month |
| Content / Growth Retainer | content-growth-retainer | ₹14,999/month |
| Local Business tiers | digital-business-starter / business-growth-launch / local-business-complete | ₹4,999 / ₹12,999 / ₹24,999 |
| Coaching Digital Starter / Growth / Monthly | coaching-digital-starter / coaching-growth / coaching-monthly-saathi | ₹6,999 / ₹14,999 / ₹4,999/month |

- **Unchanged (not in the brief):**
  - Medical Store Digital Desk ₹9,999 and Professional Authority Pack ₹14,999. These are Founding 10 offer packages, so the regular reference price stays genuine.
  - LinkedIn tiers, Creator Sprint and AI workflows.
- **Still drafts** (`_todo_price`, listed in OWNER-TODO): Business Document Template ₹799, Social Post Pack ₹2,499, Carousel/Thumbnail Pack ₹3,499, Social Campaign Kit ₹6,999.
- **Retired drafts:** Print-ready Invitation Suite, Brochure/Company Profile/Catalogue ₹3,999 (replaced by Brochure + Catalogue).
- **Scope note** shown with every price (tests enforce it): "Final quote depends on scope, content readiness, integrations, timeline and revision requirements."

## 5. Quote estimator (`src/data/estimator.json`)

- **Formula:** range = starting price × scope × content readiness × turnaround × (1 + extras %), rounded to ₹500. It never goes below the starting price.
- **Rush limit:** 24–48h is disabled for packages starting above ₹9,999.
- **Monthly plans:** turnaround is hidden.
- **Excluded:** free and custom-quote packages.
- **The output is indicative only.** Quote and WhatsApp carry `?estimate=low-high` to `/contact/`, where it is shown and optionally prefilled into the Google Form (`intake.json entry_ids.estimate`). No payment is ever taken from an estimate.
- **Owner review:** the multipliers are drafts, listed in OWNER-TODO.

## 6. Samples & portfolio (`src/data/samples.json`)

- **Published samples (all self-initiated, labelled):**
  - moodily.in website (desktop and mobile)
  - the "How we breathe" NCERT-based learning PDF
  - the AI with Saurabh channel art
  - a Hinglish YouTube Short frame
- **Originals stay outside the repository.** Only optimised WebP derivatives (≤300 KB, tested) are published.
- **Deliberately NOT published** (found during the audit): a Gmail screenshot of a private partnership email, a university enrolment screenshot with personal IDs, personal ID documents, a private health-tech startup blueprint, NotebookLM mind maps of third-party books, and third-party exam material.
- **Adding client work** requires written permission. Then set `kind: "client"` and `status: "published"`.

## 7. Analytics QA (dataLayer; no form data)

| Event | Trigger |
|---|---|
| `service_view` | Service page load (`track_view`) |
| `service_sample_view` | Samples block ≥40% visible (once per page) |
| `pricing_view` | First price card visible (once per page) |
| `retainer_view` | Monthly plan card visible (once per plan) |
| `quote_estimator_start` / `quote_estimator_complete` | First estimator change / first range after interaction |
| `google_form_open` | "Continue Requirement Form" click |
| `whatsapp_click` | Any WhatsApp CTA |
| `free_audit_click` | Any free audit CTA |
| `portfolio_open` | Sample / portfolio / case-study links |
| `pricing_click`, `service_card_click` | Quote / estimate / details CTAs; router and finder cards |
| `service_filter`, `service_search` | Finder chip/type; search (`has-results`/`no-results` only — query text is never sent) |

GTM trigger regex (replace previous): `^(service_view|service_sample_view|pricing_view|retainer_view|quote_estimator_start|quote_estimator_complete|google_form_open|whatsapp_click|free_audit_click|portfolio_open|pricing_click|service_card_click|service_filter|service_search|form_open|form_start|form_submit|offer_view|offer_cta_click|checkout_click|payment_success|payment_failed|payment_dismissed|payment_verify_failed|product_view|affiliate_click|store_click|hero_cta_click|language_switch)$`

GA4 key events: `google_form_open`, `whatsapp_click`, `quote_estimator_complete`.

## 8. Deployment checklist

- [ ] `python3 build.py && python3 tests/check_site.py && python3 tests/test_payments.py && node --test tests/worker.test.mjs`
- [ ] **Phone (375px):**
  - home: need router, customer types (4 plus expand), samples, how it works
  - `/services/local-business/` tiers; wedding, B2B and coaching pages; the estimator; the finder search for "invoice" and "PPT"
  - WhatsApp opens with the package in the message
- [ ] Old URLs (`/services/presentation-design/` and the rest) redirect to the new pages
- [ ] Google Form: add the optional "Indicative estimate" short-answer question and paste its entry ID into `intake.json entry_ids.estimate`
- [ ] GTM: update the trigger regex and mark the key events
- [ ] Owner review:
  - estimator multipliers
  - 4 remaining draft prices
  - package scopes of the new packages
  - permission and labels before adding any client sample
- [ ] Search Console:
  - request indexing for the 7 new URLs
  - the sitemap updates automatically
  - redirect pages are noindex
- [ ] **Rollback:** revert the merge commit. The redirects and old pages restore together.
