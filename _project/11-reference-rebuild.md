# 11 — Reference-framework rebuild (2026-09-17)

Branch: `feature/reference-design-rebuild-2026`. Companion to
[`REFERENCE_DESIGN_AUDIT.md`](REFERENCE_DESIGN_AUDIT.md).

## A. Existing-Moodily audit (what was found)

| Area | State before | Verdict |
|---|---|---|
| Stack | Python 3.9 static generator (`build.py`, 1.6k lines), stdlib only. JSON data → clean-URL HTML at repo root | **Keep** — component tokens + one data source are exactly the architecture the brief asks for |
| Hosting | GitHub Pages from `main:/`, `CNAME` = moodily.in, `_config.yml` excludes source | **Keep**. No Vercel project exists (see §F) |
| Pricing | `src/data/services.json`, 50 services, `price_from` + `price_mode`, rendered by `{{price:id}}` and `@price-*` components | **Keep** — already single-source and already matches the brief's canonical list (§C) |
| SEO | canonical, robots, sitemap, OG/Twitter, breadcrumbs, JSON-LD per page type, redirects map | **Keep** |
| Design | Dark-first `#0A0B0F` / violet `#7B2FFF` / saffron / teal, Inter + Noto Sans Devanagari, 12px radius, purple glow shadows | **Replace** — this is the whole gap vs the reference |
| Homepage IA | hero → paths → prices → samples → audience → how → quality → FAQ → CTA (9 sections) | **Restructure** to the 14-section brief order |
| Learn / Tools / Guides / Insights | 10 Hindi guides, 2 insight pages, tools page, learn curriculum | **Keep untouched** (brief §33) |
| Forms | Google Form wrapper + built-in fallback, `src/data/intake.json` | **Keep**; form URL is still an owner TODO |
| Payments | Razorpay via Cloudflare Worker, keys never in repo | **Keep**; accent colour retuned to indigo |

Nothing was deleted. No page was dropped. 61 pages built before, 61 after.

## B. What changed

1. **`assets/css/site.css` — full rewrite (447 → 545 lines).** Same class names throughout, so all
   61 pages inherited the new language with no per-page edits. Warm paper surface, indigo primary,
   marigold accent, Baloo 2 + Mukta, 22px cards on hairlines, flat depth, hairline section rhythm,
   dark ink footer. Dark mode kept as an opt-in theme derived from the same hues.
2. **`build.py`** — font link swapped to Baloo 2 + Mukta (one request, both scripts);
   `data-theme` default `dark` → `light`; `theme-color` → `#f7f5f0`; Razorpay accent → `#232c6b`;
   header CTA → marigold.
3. **Four new components** (`build.py`): `@packages`, `@categories`, `@scorecard`, `@promises`.
4. **`src/pages/index.html`** — rebuilt to the 14-section order.

## C. Pricing reconciliation

All 26 prices in the brief's canonical list were checked against `src/data/services.json`.
**All 26 already matched** — ₹499 visiting card, ₹599 social creative, ₹799 poster / invitation,
₹1,499 WhatsApp, ₹1,999 PPT / GBP / animated invitation, ₹2,999 brochure, ₹4,999 logo / Google+WhatsApp
starter, ₹7,999 catalogue / landing page, ₹9,999 brand kit / content+presentation / study material /
social monthly / Digital Saathi monthly, ₹12,999 growth kit, ₹19,999 website, ₹24,999 competitive
intelligence / B2B kit, and custom quote for booking site, pitch deck, research dossier,
knowledge-to-product. **No price was edited.** Prices stay centrally configurable in that one file.

## D. Homepage information architecture (as built)

| # | Section | Component |
|---|---|---|
| 1 | Header | `header()` |
| 2 | Hero + Digital Audit scorecard | `@scorecard` |
| 3 | What do you need? (4 paths) | `@paths` |
| — | Founding-10 offer (auto-hides when it ends) | `@offer-details` |
| 4 | Featured packages (3) | `@packages` |
| 5 | Real work / samples | `@samples` |
| 6 | Who we help | `@customer-router` |
| 7 | Service categories | `@categories` |
| 8 | How Moodily works | `@how-it-works` |
| 9 | Pricing examples | `@price-snapshot` |
| 10 | Case studies | `@cases limit="3"` |
| 11 | Quality workflow + promises / won't-do | `@quality-workflow`, `@promises` |
| 12 | FAQ | `@faq set="home"` |
| 13 | Final CTA | `@final-cta` |
| 14 | Footer | `footer()` |

## E. QA results (measured on the local build)

- Build: 61 pages, 45 sitemap URLs. `tests/check_site.py` → **OK**.
- Console errors: **0**. Network: all **200**.
- Contrast: lowest pair **5.81:1** (muted text on paper) — AA pass, most pairs AAA.
- Images without `alt`: **0**. `<h1>` per page: **1**. Unlabelled form controls: **0**.
- Horizontal overflow at 375px: **none** (`scrollWidth == clientWidth == 375`).
- Tap targets: every control ≥ 44px on ≤720px viewports.

## F. Deployment note — Vercel vs GitHub Pages

The brief asks for a Vercel preview. **This repo has no Vercel project and no `vercel.json`** — it is
a GitHub Pages site served from `main:/` with `CNAME` = moodily.in. Two safe options, neither taken
without the owner's go-ahead because both touch live infrastructure:

1. **Open a PR from this branch.** CI (`.github/workflows/check.yml`) rebuilds and runs the checks.
   Reviewing the branch is the like-for-like "preview" for a Pages site.
2. **Import the repo into Vercel as a static project** (output dir `.`, no build command, since HTML
   is committed). Preview URLs must carry `noindex` — `build.py` already emits
   `noindex, follow` for any page whose meta sets it, and preview deploys should set
   `X-Robots-Tag: noindex` at the Vercel project level so preview URLs never compete with moodily.in.

`SITE["url"]` is `https://moodily.in` and every canonical/OG URL is built from it, so production
metadata already points at the canonical domain regardless of where a preview runs.
