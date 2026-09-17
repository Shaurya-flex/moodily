# 12 — Visual polish pass (2026-09-17)

Branch: `feature/reference-design-rebuild-2026`. Local only — **not pushed.**

## 1. Right-side space — root cause

No horizontal overflow existed on the homepage. Measured at 1440px, the page geometry was
symmetric (gutter 160px both sides). The *perceived* imbalance was
`.section-head{max-width:720px}`: every section intro stopped 540px short of the right gutter.

Fixed by making the section head a two-column block from 900px up (heading left, description
right), so the intro now spans the content width. Right gap at 1440px: **540px → 152px**, equal
to the left gutter.

Two genuine overflow bugs were found and fixed while sweeping the other page types:

1. **`backdrop-filter` on `.site-header`** made the header a containing block for
   `position:fixed` descendants, so the mobile menu drawer anchored to the header instead of the
   viewport. The glass effect now lives on `.site-header::before`, which has no fixed descendants.
2. **A closed `<details>` menu still laid its panel out** (the subtree is only
   `content-visibility:hidden`), contributing real scroll width.
   `.menu:not([open])>.menu-panel{display:none}` removes the box.
   With that mask gone, the actual overflow surfaced: **`.nav-actions` overflowed at 430px on
   bilingual pages** (the extra हिं/EN toggle). The header CTA is now hidden below 720px, where the
   sticky bottom bar already carries it.

`overflow-x:hidden` was **removed** from `body` — it was masking these bugs. Nothing needs it now.

**Sweep result: 14 page types × 8 widths (375/390/430/768/1024/1280/1440/1600) — 0 overflow.**

## 2. Colour system

One semantic scale, two themes, shared identity (violet primary, orange accent, cyan interactive):
`--bg --surface --surface-elevated --surface-sunken --text --text-muted --border --border-strong
--primary --secondary --accent --success --warning --danger --panel`.
Legacy aliases (`--ink`, `--paper`, `--indigo`, `--marigold`…) map onto the new scale so no page broke.

| | Light | Dark |
|---|---|---|
| bg | `#f7f6f3` warm neutral | `#080d1c` |
| surface / elevated | `#ffffff` | `#11182b` / `#17213a` |
| text / muted | `#14172a` / `#565d75` | `#f7f9ff` / `#b9c3d8` |
| primary | `#5b3fd9` | `#8b70ff` |
| accent | `#b8501a` | `#ff7a36` |
| border | `#e4e1da` | `#2b3857` |

The brief's dark violet `#7c5cfc` was lifted to `#8b70ff` because near-black button text on it
measured 4.45:1. Light accent `#d95f1e` was deepened to `#b8501a` (white text was 3.75:1); the
vivid original survives as `--accent-bright` where it sits on dark panels and carries no text.

**The brown pricing slab is gone** — `.offer-section` is now a faint violet radial on the sunken
surface. `--marigold-soft` no longer backs any section.

## 3. Contrast (measured on rendered elements, both themes)

Audited every text node against its resolved background. Failures fixed:

| Element | Before | After |
|---|---|---|
| WhatsApp button, dark | **1.98** | 5.45 |
| WhatsApp button, light | 4.33 | 5.45 |
| Accent button / offer badge, light | 3.75 | 5.00 |
| Primary button + step numbers, dark | 4.45 | 6.65 |
| Path price / router arrow, dark | 4.03 | 4.93 |
| Case-study badge, dark | 3.59 | 4.90 |

Everything now clears WCAG AA. Lowest pair on the page: 4.93:1.

## 4. Menu

Desktop: a 380px popover anchored under the control — **30% of viewport width**, no dimming
(the backdrop is transparent there and only catches the click-outside). Mobile: a right drawer at
`min(84vw, 360px)` = 315px at 375px wide, with a dimmed backdrop, a visible close button, and a
body-scroll lock. Both: Escape closes and returns focus to the trigger, click-outside closes, and
Tab is trapped inside while open. `<details>` still works with JavaScript off.

The desktop inline nav was cut to 4 links (Services, Samples, Pricing, Learn) so the header no
longer wraps to two rows at 1280px; Pricing, Tools, About, Contact and the full service list live
in the popover, which is now available at every width.

## 5. Founding 10 — trust check

Verified against the config, not assumed:

- The deadline is a fixed ISO timestamp in `src/site.json` rendered into `data-offer-ends`.
  It does **not** reset on refresh. ✅
- `slots_taken` is owner-maintained and has never moved off 0. ⚠️
- `payments.api_base` is empty, `mode` is `test`, and every `offer.payment_links` entry is
  blank — **a customer cannot actually pay the discounted price today.** ⚠️

Two of the three could not be verified, so per the brief the urgency UI is off:
**countdown and slot counter removed everywhere** (banner, homepage offer section, offer page).
The introductory pricing and its terms still show. This is gated by one new flag,
`offer.urgency_confirmed` (currently `false`) — flip it to `true` and the timer and counter return.

## 6. Visual storytelling

- **"Moodily क्या बना सकता है?"** — 12 concrete outputs, each with a line-art icon, starting price
  and link to its service.
- **"Digital Saathi से क्या बदलता है?"** — three before → after split cards (local business,
  coaching/library, professional/creator). Before is grayscaled and muted; after is branded.
  Labelled in-page as illustrative examples with no client names, numbers or claimed results.

Both use **inline SVG** — no new image files, no requests, and they theme with the tokens.

## 7. Cleanup candidates (NOT deleted — owner approval required)

25 CSS classes are defined but referenced nowhere in the repo, left over from removed features:

`cat-card cat-emoji cat-head cta-row format-filter center sample-line`
`mock-grid mock-poster mock-thumb`
`need-card need-emoji need-grid need-main need-price need-sub need-sublinks need-title`
`outcome-card outcome-emoji outcome-examples outcome-grid outcome-price outcome-sub outcome-title`

Roughly 60 lines of CSS. No orphaned image assets. Two dead rules added during this pass
(`btn-ghost`, `case-grid`) were removed straight away.

---

# Phase 2 — Sample catalogue (2026-09-17)

Extends the visual-polish baseline. Nothing from Phase 1 was reverted.

## Sample registry — one file, no parallel pricing

`src/data/samples.json` is the single catalogue registry. **No sample carries a price.**
Each maps to a `service` id and the price, timeline and revisions are read from
`src/data/services.json` at build time. Both `build.py` and `tests/check_site.py` now *fail the
build* if a sample grows a `price`, `price_from`, `amount` or `starting_price` key, or references
an unknown service, customer type or case study.

17 samples: **5 with real web-optimised assets**, **12 concept previews**.
Types present: 2 Moodily-internal, 3 self-initiated, 12 concept. **Zero claim to be client work.**

## Asset policy (no storage clutter)

Concept previews are **inline SVG generated in `build.py`** (`_sample_preview`), not image files.
Phase 2 therefore added **0 bytes** of binary assets — 14 inline previews across the site.
Real assets remain the five existing `.webp` files under `/assets/img/samples/`; none were
duplicated, renamed or re-encoded. The registry holds the canonical path; there is no second copy.

## Evidence — verified, India-only

`src/data/evidence.json`. Three cards, each with source, year, link and context. `build.py`
refuses to render a card missing any of those fields.

| Number | Claim | Source |
|---|---|---|
| 109 करोड़ | India internet subscribers (1,092.79 M, 31 Mar 2026) | TRAI, Indian Telecom Services Performance Indicator Report Jan–Mar 2026, via PIB |
| 57% | of active internet users are rural (~548 M of 958 M) | IAMAI–Kantar, Internet in India Report 2025 |
| 61% | watched short-video content in 2025 (588 M) | IAMAI–Kantar, Internet in India Report 2025 |

UPI/NPCI figures were researched but **omitted**: the monthly volume could only be confirmed
through secondary reporting, not NPCI or PIB directly (both blocked automated fetch). Per the
brief, a weak source means no card. Each entry carries `last_reviewed` and `review_due`
(2027-03-31) so the numbers do not quietly go stale.

No causal claim is made anywhere. Every statistic is followed by a
"आपके business के लिए इसका मतलब" block that turns the trend into a practical step and links
the relevant services — trend → implication → what to do.

## Routes added

`/samples/` (catalogue, search + browse-by-need + browse-by-customer-type) and
`/samples/<slug>/` × 17. 61 → **79 pages**, 45 → **63 sitemap URLs**.

## Conversion journey

Sample tile → `इसे मेरे लिए बनाइए` → `/contact/?service=<id>&sample=<slug>` → the enquiry page
names the sample, shows the service and its price, and the WhatsApp hand-off carries
`Sample: <title> (moodily.in/samples/<slug>/)`. The Google Form URL is still empty, so the
built-in form is used; prefill support is already wired for when the form is configured.
**No Form entry ID was invented.**

## Analytics

`samples_page_view`, `sample_card_view`, `sample_card_click`, `sample_detail_view`,
`customize_sample_click`, `customize_sample_start`, `sample_filter`, `sample_search`,
`evidence_card_view`, `before_after_view`, plus the existing quote/WhatsApp/form events.
Labels only — no enquiry content is ever sent to analytics.

## Bug found and fixed during QA

The footer's `color:#dcdff0!important` was repainting `.btn-wa` inside the footer, dropping the
WhatsApp button to **4.11:1**. The override is now scoped with `:not(.btn)`. Contrast audits on
`/`, `/samples/` and a sample detail page measured from first paint: **0 failures in either theme.**

## Still open

- Google Form URL and entry IDs (owner).
- The 11 case studies remain `draft`; sample pages link to them but the write-ups are unpublished.
- 25 unused CSS classes — **re-audit deferred to after Phase 2 review, as instructed.**
