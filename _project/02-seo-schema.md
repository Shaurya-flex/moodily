# 02 — Technical SEO specification, schema plan, Hindi AEO & GEO

Covers deliverables **H, I** and sections 18–20 of the brief.

## H. Technical SEO specification

| Item | Implementation | Where |
|---|---|---|
| Titles | Unique per page (build fails on duplicates). Pattern: `<Topic> — <benefit> | Moodily` ; homepage leads with brand. | page meta |
| Descriptions | 50–300 chars (checked), written for the page's language. | page meta |
| Canonical | Absolute `https://moodily.in/<route>/` with trailing slash (checked). | `build.py: layout` |
| Robots meta | `index, follow, max-image-preview:large`; `noindex, follow` on `/contact/thanks/` and 404. | meta `noindex` |
| robots.txt | Allow all, disallow `/contact/thanks/`, sitemap line. | generated |
| sitemap.xml | Every indexable page, `lastmod` = build date. Draft case studies excluded. | generated |
| Language | `<html lang="hi">` or `"en"`, `og:locale` hi_IN/en_IN. No hreflang (no alternates). | meta `lang` |
| Brand entity | Consistent name **Moodily**; `alternateName` Moodily.in, Moodily Digital Saathi; `disambiguatingDescription` vs Moody's / adverb "moodily"; About page states it visibly. | `site.json` |
| Logo | `/assets/img/moodily-logo-512.png` (Organization.logo), SVG favicon. | `scripts/make_images.py` |
| OG image | `/assets/img/og-moodily.png` 1200×630. | same |
| Internal links | Router → service pages; service pages → guides, samples, tools; guides → service anchors; footer links all divisions + legal. Anchors verified by tests. | pages |
| Breadcrumbs | Visible `<nav aria-label="Breadcrumb">` + BreadcrumbList on all inner pages. | meta `breadcrumbs` |
| Alt text | All `<img>` require alt (checked). Case-study screenshots need descriptive alt in JSON. | tests |
| Performance | No framework JS; 1 CSS (~20 KB), 1 deferred JS (~6 KB); fonts `display=swap`, 2 families × 3 weights; no layout-shifting reveal animations; `loading="lazy"` for case-study images. | assets |
| 404 | Custom `404.html` with routes to main sections. | pages |
| Legacy URLs | Old `/#curriculum`, `#services`, `#linkedin`, `#tools`, `#intake` redirect client-side. | `site.js` |

**Not done on purpose:** meta keywords (ignored by Google), `/hi` `/en` duplicates, programmatic city pages, FAQ stuffing.

## I. Schema plan

All JSON-LD is emitted as one `@graph` per page and mirrors visible content.

| Type | Pages | Source / rules |
|---|---|---|
| `Organization` (`@id https://moodily.in/#organization`) | `/`, `/about/` | name, alternateName, url, logo, description, disambiguatingDescription, email, contactPoint (WhatsApp), areaServed, knowsLanguage, department (4 divisions). `sameAs`, `legalName`, `address`, `founder` are added **automatically only when filled** in `site.json`. |
| `WebSite` | `/` | name, alternateName, inLanguage, publisher → Organization. (No SearchAction — no site search.) |
| `BreadcrumbList` | all inner pages | from meta `breadcrumbs` |
| `Service` + `Offer/PriceSpecification(minPrice)` | service pages (one per detailed package); monthly plans use `UnitPriceSpecification` `unitCode MON` | `services.json`; custom-quote services have no offer |
| `FAQPage` | pages with `@faq` | same Q&A rendered visibly (Google shows FAQ rich results mainly for authoritative gov/health sites, but the markup still aids understanding) |
| `Article` | `/guides/*` | headline, dates, inLanguage, author & publisher → Organization. Switch author to `Person` once founder details exist. |
| `Product` + `Offer` | `/store/` | **only** products with `status: available`, price and checkout URL. Waitlist items emit nothing. |

Validate after deploy: Rich Results Test + Schema.org validator for `/`, one service page, one guide.

## 19. Hindi SEO / AEO content plan

Each article: direct answer box first (40–60 words), step-by-step H2s, mistakes/scams, cited official sources, CTA last.

| # | Query | Status | URL |
|---|---|---|---|
| 1 | दुकान को Google Maps पर कैसे लाएं? | **Published** | `/guides/dukan-google-maps-par-kaise-laye/` |
| 2 | Google Business Profile बनवाने की cost कितनी है? | **Published** | `/guides/google-business-profile-cost/` |
| 3 | WhatsApp से local orders कैसे लें? | **Published** | `/guides/whatsapp-se-local-orders/` |
| 4 | Medical Store home delivery setup कैसे करें? | Planned (week 2) | `/guides/medical-store-home-delivery-setup/` — must cite applicable drug-sale rules; legal review |
| 5 | कोचिंग के लिए digital study material कैसे बनता है? | Planned (week 3) | `/guides/coaching-digital-study-material/` |
| 6 | PYQ analysis क्या है? | Planned (week 3) | `/guides/pyq-analysis-kya-hai/` — include a real sample table |
| 7 | AI workflow automation क्या है? | Planned (week 2) | `/guides/ai-workflow-automation-kya-hai/` |
| 8 | Small business website क्यों जरूरी है? | Planned (week 4) | `/guides/small-business-website-kyon-jaruri/` |
| 9 | Research को ebook/course में कैसे बदलें? | Planned (week 4) | `/guides/research-ko-ebook-course-mein-badlen/` |

To add a guide: copy an existing file in `src/pages/guides/`, change meta (`article.published`), add it to `guides/index.html`, build.

## 20. GEO / AI-search approach

- Crawlable static HTML; no content behind JS.
- Entity clarity (About page, disambiguation, consistent NAP once address is supplied).
- Original assets: case studies with **original screenshots** and evidence labels are the main citation magnet — highest priority.
- Clear citations to Google/WhatsApp official docs in guides.
- Structured data that matches visible content only.
- Author transparency: add founder `Person` and bylines once the owner supplies details.
- Explicitly avoided: synthetic mass pages, fake "AI SEO" files, keyword-stuffed Q&A.
