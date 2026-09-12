# 04 — Testing, deployment, rollback, Search Console, 30-day backlog

Covers deliverables **J, L, M, N, O**.

## J. File / component change plan (as implemented)

| Path | Change |
|---|---|
| `build.py` | **New.** Stdlib generator: layout, header/footer, components, schema, sitemap, robots, owner TODO report, stale-file cleanup. |
| `src/site.json` | **New.** Config: WhatsApp, GTM, form endpoint, payments, legal/founder/sameAs placeholders. |
| `src/data/*.json` | **New.** services, case_studies, products, tools, faqs, learn (curriculum migrated from old inline JS). |
| `src/pages/**` | **New.** 26 page sources (meta + HTML + component tokens). |
| `assets/css/site.css`, `assets/js/site.js` | **New.** Extracted and extended design system; tracking, form, legacy anchors, ratings. |
| `assets/img/*` | **New.** SVG mark, logo PNG, OG image (`scripts/make_images.py`). |
| `index.html` + route folders, `404.html`, `sitemap.xml`, `robots.txt` | **Generated** — do not hand-edit. |
| `rebuild_site.py`, `.github/workflows/weekly-tip.yml` | Updated to target `src/pages/learn.html` and rebuild + test. |
| `.github/workflows/check.yml` | **New.** CI: build, ensure output committed, run checks. |
| `_config.yml` | **New.** Excludes source/tests/scripts from Pages. |
| `tests/check_site.py` | **New.** Site checks. |

## L. Testing

Automated (`python3 build.py && python3 tests/check_site.py`), fails on:
unique title / description length / canonical / exactly one h1 / img alt / `target=_blank` without noopener / unlabeled form controls / invalid JSON-LD / broken internal links and anchors / sitemap ↔ files ↔ noindex / robots rules / **banned claims** (4.8, 1,200+, unlimited revisions, official certs, govt-certificate wording) / placeholder WhatsApp or Razorpay keys / leaked `_todo` or template tokens.
Build also fails on missing service fields, "unlimited", duplicate titles, unknown components/service ids.

Manual (done on this branch via local server, mobile 375px + desktop): see PR description for screenshots and results. Re-test after each content change: home, one service page, contact submit (both endpoint states), thanks WhatsApp link, theme + language toggle, keyboard-only navigation through menu and form.

## M. Deployment checklist

Before merge
- [ ] Owner confirms WhatsApp number `919354123255` (or replaces it) in `src/site.json`.
- [ ] Owner approves draft package scopes in `src/data/services.json` and legal pages (lawyer review recommended for privacy/terms/refund).
- [ ] (Recommended) Apps Script endpoint added to `form.endpoint`.
- [ ] `python3 build.py && python3 tests/check_site.py` passes; commit generated files.
- [ ] CI "Build & check site" green on the PR.

Merge & verify (GitHub Pages rebuilds from `main` in ~1–2 min)
- [ ] https://moodily.in/ loads; https://www.moodily.in/ redirects; HTTPS padlock.
- [ ] `/learn/`, `/services/medical-store/`, `/contact/`, `/sitemap.xml`, `/robots.txt`, a bad URL → custom 404.
- [ ] `https://moodily.in/src/site.json` and `/_project/…` return 404 (Jekyll exclude working).
- [ ] WhatsApp FAB opens the right number with prefilled text on a phone.
- [ ] Test form submission reaches Sheet (or WhatsApp hand-off shown).
- [ ] GTM Preview shows events.
- [ ] Old link `https://moodily.in/#curriculum` lands on `/learn/#curriculum`.

Configuration ("environment variables")
Static site — no runtime env vars or secrets. All config is public in `src/site.json`: `whatsapp.number`, `gtm_id`, `form.endpoint`, `payments.provider`, `legal.*`, `founder.*`, `same_as`. Never put API keys/secrets in this repo; server-side keys belong in Apps Script / n8n.

Local development
```bash
python3 build.py
python3 tests/check_site.py
python3 -m http.server 8123   # open http://localhost:8123
```
Pillow is needed only to regenerate images (`python3 scripts/make_images.py`).

Rollback
- Fastest: GitHub → Pull request → **Revert** → merge. Pages redeploys the previous site in ~2 minutes.
- CLI: `git revert -m 1 <merge-commit> && git push origin main`.
- The pre-branch site is the single `index.html` at commit `15a2485`. `git checkout 15a2485 -- index.html` restores just the old homepage file if needed (remove generated folders too for a full revert).
- The weekly-tip action on the old layout expects `index.html`; reverting the merge reverts the workflow too, so they stay consistent.

## N. Search Console & indexing checklist

1. Add **Domain property** `moodily.in` in Google Search Console (DNS TXT verification at the domain registrar). Also add Bing Webmaster Tools (import from GSC).
2. Submit `https://moodily.in/sitemap.xml`.
3. URL Inspection → Request indexing: `/`, `/digital-saathi/`, `/services/local-business/`, `/services/medical-store/`, `/learn/`, `/about/`, 3 guides.
4. Check Page indexing report after 3–7 days: "Duplicate without user-selected canonical" (should be none), "Crawled – currently not indexed" (improve content), 404s from old URLs.
5. Rich Results Test: `/` (Organization), a service page (Breadcrumb/FAQ), a guide (Article).
6. Brand entity: search `Moodily`, `Moodily.in`, `Moodily Digital Saathi` weekly; once social profiles exist, add them to `same_as` and link back to moodily.in from each profile bio.
7. Create/claim Moodily's own **Google Business Profile** only if there is a real service address or service area that meets Google's guidelines.
8. Core Web Vitals report (mobile) after 28 days of data; PageSpeed Insights on `/` and `/contact/` now.
9. Performance report: filter queries containing "moodily" vs non-brand; track guide impressions.

## O. 30-day optimization backlog

Priority = impact on qualified enquiries ÷ effort.

| Week | Item | Owner input? | Metric |
|---|---|---|---|
| 1 | Confirm WhatsApp number; connect Apps Script endpoint; GA4 tag + key events in GTM | ✔ | form_submit & whatsapp_click recorded |
| 1 | Search Console + sitemap + request indexing | ✔ (DNS) | pages indexed |
| 1 | Fill founder, legal name, city, sameAs → About + Organization schema | ✔ | entity search results |
| 1 | Approve/adjust package scopes & prices; set education starting price | ✔ | — |
| 1 | Lawyer review of privacy/terms/refund | ✔ | — |
| 2 | **Publish first 3 case studies** with original screenshots (Rasra Library, NCERT visual learning, grocery gap analysis) | ✔ evidence | case_study_open, price_click from case pages |
| 2 | Guides #4 (medical delivery setup) and #7 (AI workflow automation) | partial | impressions |
| 2 | Add verified provider URLs to all 15 learning courses; remove any course that no longer exists/free | ✔ | learn engagement |
| 2 | Real affiliate URLs for tools that have programmes; keep disclosure | ✔ | tool_affiliate_click |
| 3 | First store product live: preview PDF + price + hosted payment link (after provider decision) | ✔ | product_view → checkout_click |
| 3 | Guides #5, #6 with a real PYQ sample table | partial | impressions |
| 3 | Audit-offer landing variant for WhatsApp/Instagram sharing (short URL, QR) | — | audit requests |
| 3 | Add Cloudflare Turnstile to form if spam > 5/week | — | spam rate |
| 4 | Review funnel: price_click→enquiry by service; rewrite weakest service hero | — | conversion rate |
| 4 | Guides #8, #9; internal links from service pages | — | impressions/CTR |
| 4 | Collect first genuine client testimonials (written permission) — publish with name/business only if client agrees | ✔ | — |
| 4 | Consider Hindi twin for `/services/research/` and `/services/knowledge-to-product/` if Hindi queries appear in GSC | — | query language mix |
| Ongoing | Weekly: GSC queries, GTM events, lead Sheet → qualified %, response time < 24h | ✔ | — |
