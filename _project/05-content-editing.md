# 05 — How to edit content

Everything visitors see is generated from `src/`. **Edit `src/`, never the generated HTML.** Then:

```bash
python3 build.py && python3 tests/check_site.py
```
Commit both `src/` changes and the generated output.

## Common edits

| I want to… | Edit |
|---|---|
| Change a price, deliverable, timeline | `src/data/services.json` (appears on cards, service page, price table, schema) |
| Change WhatsApp number / GTM / form endpoint | `src/site.json` |
| Publish a case study | `src/data/case_studies.json`: fill `problem`, `input`, `method`, `built`, `verification`, `screenshots` (`[{ "src": "/assets/img/case-studies/<slug>/1.webp", "alt": "...", "caption": "..." }]`), optional `result`; set `"status": "published"` |
| Make a product purchasable | `src/data/products.json`: real `contents`, `preview` URL, `price`, `checkout_url`, `"status": "available"` |
| Add an affiliate link | `src/data/tools.json → affiliate_url` (rendered with `rel="sponsored"` and an "Affiliate link" badge) |
| Add an FAQ | `src/data/faqs.json` (visible + FAQPage schema) |
| Add a course URL | `src/data/learn.json → url` |
| Edit page text | `src/pages/<route>.html` |
| Add a page | Create `src/pages/<route>.html` with a meta block; it becomes `/<route>/` |

## Page meta block

```html
<!--meta {
  "title": "Unique title — Moodily",
  "description": "50–300 characters",
  "lang": "hi",                         // or "en"
  "bilingual": false,                   // true shows the हिं/EN toggle (.hi/.en spans)
  "breadcrumbs": [["Services", "/services/"], ["Page", "/services/page/"]],
  "track_view": ["service_view", "category"],
  "noindex": false,
  "priority": "0.7",
  "article": {"published": "2026-09-13"} // guides only → Article schema
} -->
```

## Components

| Token | Output |
|---|---|
| `<!--@audience-router -->` | "आप कौन हैं?" cards |
| `<!--@services ids="a,b" -->` / `category="local-business"` + `style="detail"` | Compact cards or full package cards (+ Service schema) |
| `<!--@price-table -->`, `<!--@payg -->` | Pricing tables |
| `<!--@cases limit="6" -->` | Case study cards |
| `<!--@products limit="3" -->`, `<!--@product-categories -->`, `<!--@products-by-category -->` | Store |
| `<!--@tools -->` | Tool guides |
| `<!--@faq set="home" -->` | FAQ + schema |
| `<!--@quality-workflow labels="no" -->` | 7-stage workflow (+ evidence labels unless `no`) |
| `<!--@final-cta title="…" sub="…" lang="en" -->` | Closing CTA band |
| `<!--@wa label="…" role="…" service="…" class="…" track="…" -->` | Prefilled WhatsApp button |
| `<!--@lead-form -->`, `<!--@learn-curriculum -->`, `<!--@founder -->` | Form, curriculum, founder card |
| `{{site.email}}`, `{{site.whatsapp.number}}` | Config values |

## Claims policy (enforced by tests)
No ratings, learner counts, testimonials, results, revenue, "unlimited", official partnerships or government/IIT certificates unless the owner holds evidence — and even then, add the evidence to the case study first.
