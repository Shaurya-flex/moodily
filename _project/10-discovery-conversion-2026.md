# 10 — Discovery & conversion system (2026 commercial rebuild)

Branch `feature/discovery-conversion-2026`. Goal: a visitor understands *what Moodily does, what they get, rough cost, a real example, how to ask* in 30–60 s, and can send a qualified requirement in 2–3 min.

## Audit (before)
- Stack: Python stdlib static generator (`build.py`) → GitHub Pages. 49 pages, CI checks. No brand misspellings found (Modily/Mudli/Moodyly: 0).
- Gaps vs brief: 8-card need router instead of 4 paths; slugs differed from the priority money-page list; no price types (everything "starting price"); prices differed from the brief; no quick-answer block; estimator lacked integrations/revision level; 8-step process; no insights area; case-study template missing gap/workflow/before/after/lessons; sitemap `lastmod` = build date for every URL; render-blocking Google Fonts CSS; analytics names differed (`service_sample_view`, `quote_estimator_*`, `case_study_open`).
- Kept: learning pages, founding offer, Razorpay worker, Google Form intake, samples policy, redirects system.

## Routes
New: `/services/google-business-profile/` (GBP only), `/services/whatsapp-business/`, `/services/brochure-catalogue/`, `/insights/`, `/insights/website-vs-google-business-profile-vs-whatsapp/`, `/insights/digital-services-price-guide-india-2026/`.

Renamed (old URL → noindex redirect page, canonical to new, no chains — tested):
| Old | New |
|---|---|
| /services/local-business/ | /services/local-business-digitalization/ |
| /services/websites/ | /services/business-website/ |
| /services/google-whatsapp/ | /services/google-business-profile/ |
| /services/presentations/ | /services/presentation-design/ |
| /services/social-media/ | /services/social-media-design/ |
| /services/invitations/, /services/invitation-design/ | /services/digital-invitation/ |
| /services/education-business/ | /services/coaching-digital-services/ |
| /services/research/ | /services/research-intelligence/ |
| /services/b2b/ | /services/b2b-digital-sales/ |

Verticals: coaching-digital-services, wedding-event, b2b-digital-sales, local-business-digitalization, professionals, creators. No city/pincode pages.

## Pricing architecture
- Single registry: `src/data/services.json`. Brief field → registry field: id/slug, category, verticals→`customer_types`, title→`name`, shortDescription→`tagline`, problemSolved→`problem`, deliverables, priceType→`price_mode` (`exact`|`starts_at`|`custom_quote`|`free`), displayPrice→`price_from`+`price_unit`, launchOffer→`site.json offer`, timeline, revisionRounds→`revision_rounds`, outputFormats→`formats`, editableSourceAvailable→`editable_source`, thirdPartyCosts, sampleIds, caseStudyIds, formURL→`form_prefill_url`, whatsappTemplate→`whatsapp_message`, seoTitle/seoDescription→page meta, faq→`faqs.json`, featured, active, lastPriceReviewDate→`last_price_review`, what client provides→`client_provides_by_category` (+ per-service override).
- **Internal fields (targetPriceInternal, estimatedHoursInternal, cashCostInternal) are NOT in the repo** (public). They live in gitignored `private/pricing-internal.json`; `python3 scripts/price_floor_check.py` prints floors at ₹750/₹1,250/₹2,000 per hour: `hours × 1.15 revision allowance × 1.15 PM buffer × rate + cash cost`. Build + tests fail if such keys appear in `src/data`.
- Brief values applied (exact): Visiting card 499, Social creative 599, Poster 799, Static invitation 799, WhatsApp Business Basic Setup 1,499 (new), Animated invitation 1,999. Starts at: PPT Formatting/Design 1,999, GBP Optimization 1,999, Brochure 2,999, Logo 4,999, Catalogue 7,999, Landing page 7,999, Starter Brand Kit 9,999, Content + Presentation 9,999, Study Material Bundle 9,999, Monthly Social Content 9,999/mo, Digital Saathi Monthly 9,999/mo, Business Website 19,999, Competitive Intelligence 24,999 (new id), B2B Digital Sales Kit 24,999. Custom quote: Advanced Booking Website, Pitch Deck (new), Research Dossier, Knowledge-to-Product.
- Scope decisions needing owner review: Digital Saathi Monthly absorbed the retired Local Growth scope (`local-growth-monthly` inactive); Monthly Social Content trimmed to 12 creatives + 2 video edits; PPT Formatting keeps "10 slides तक" at the lower price.
- Founding 10 offer untouched (its three packages kept their regular prices, so struck-through prices stay genuine).
- Estimator groups: scope/pages/assets, content readiness, integrations (website/AI only), revision level (max 3 rounds total), turnaround; extras research/editable/formats. Multipliers = scope/complexity only.

## SEO / AEO / generative search
- Answer-first: `@answer-box` on every money page (what, who, what you get, price + price type, time, revisions, what the client provides, what costs extra, Quote/Sample/WhatsApp). New pages follow question → direct answer → cost → who → included → when not needed → example → packages → process → FAQ → CTA.
- Original assets: insights hub with methodology, sources, limitations; live price guide generated from the registry (`@price-guide`).
- Technical: sitemap `lastmod` from content hash (`.build-lastmod.json`), non-blocking font CSS, twitter title/description, og:image:alt, visible article byline + dates, Article.author (Person when founder is filled), Service offers use `price` for exact and `minPrice` for starting prices, no offer for custom quotes, Service nodes de-duplicated. No LocalBusiness, no ratings/reviews, no address. Single bilingual URLs → no hreflang needed.

## Analytics (GTM dataLayer)
`service_view` (page load), `sample_view` (samples section seen), `pricing_view`, `retainer_view`, `quote_start` (Requirement/Quote CTA click or first estimator input; label says which), `quote_complete` (estimator produced a range), `google_form_open`, `whatsapp_click`, `free_audit_click`, `case_study_view` (case-study page load). Labels carry service ids/placements only — never form contents or search text.

GTM custom-event trigger regex:
```
^(service_view|sample_view|pricing_view|retainer_view|quote_start|quote_complete|google_form_open|whatsapp_click|free_audit_click|case_study_view|form_submit|offer_cta_click|checkout_click|payment_success|service_search|service_filter)$
```
Key events: `google_form_open`, `whatsapp_click`, `quote_complete`, `form_submit`.

## Measurement per landing page
Search Console: impressions, clicks, CTR, average position (Performance → Pages, filter URL). GA4: sessions, `quote_start`, `quote_complete`, `google_form_open`, `whatsapp_click`, `free_audit_click` by `page_path`. Sheet: qualified leads + revenue by source page (add a "landing page" column to the lead sheet).

## Prioritising future pages (score 1–5 each, publish ≥ 26/35)
buyer intent · relevance · ability to show proof · project value · repeat demand · competition (5 = low) · unique information.

## Backlog
1. Publish case studies once evidence exists (Rasra Library first — it is a real local-business project).
2. Research pieces: digital gaps across local businesses (needs a documented audit sample), coaching WhatsApp-only admissions, B2B beyond IndiaMART, textbook chapter → learning assets (use the NCERT sample).
3. Per-service Google Form prefill URLs once the form exists.
4. Real client samples for Google/WhatsApp pages (only with written permission).
5. Responsive `srcset` for sample images if more/larger images are added.
