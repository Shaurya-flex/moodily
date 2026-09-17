# Amazon Associates — readiness checklist

**Status: prepared, inert.** No affiliate link, tag or earnings claim exists anywhere on Moodily.in
today. `src/site.json → amazon_associates` is `enabled: false`, `tag: ""`.

## Nothing affiliate-related is public today

While `enabled` is false the site publishes **no** affiliate surface at all:
`/affiliate-disclosure/` is not generated, it is absent from the sitemap, the footer carries no link,
and `@affiliate-disclosure` renders an empty string. A page whose message is "Moodily currently earns
no commission" is honest but not worth a public route, so it simply does not exist yet. The template
lives on in `src/pages/affiliate-disclosure.html` with `"gated_on": "amazon_associates"`.

Flipping the four config values regenerates the page, the sitemap entry and the footer link with no
code change. Both directions were tested.

Legal and transparency routes (`/privacy/`, `/terms/`, `/refund/`, and `/affiliate-disclosure/` when
live) render without the promotional banner, the sticky conversion bar and the floating WhatsApp
button — a compliance page should read as clarity, not as a sales surface.

## Build-time guards (verified)

`validate_amazon()` fails the build on every half-configured state:

| Misconfiguration | Result |
|---|---|
| `enabled` true, `tag` empty | ❌ blocked — untagged links earn nothing and mislead readers |
| `disclosure_enabled` true, programme off | ❌ blocked — claims earnings Moodily does not make |
| `enabled` + `tag`, no `disclosure_enabled` | ❌ blocked — disclosure is required, not optional |
| `enabled` + `tag` + disclosure, no `approved_properties` | ❌ blocked — list your Site List URLs first |

All four were tested by temporarily patching `site.json`; each one stopped the build.

`@amazon-link` refuses to emit a link without a real tag — it prints the product name as plain text
instead, so a page keeps its editorial value and never carries a dead affiliate stub.

## Checklist

| Requirement | Status |
|---|---|
| Moodily.in publicly accessible | ⏳ after this PR merges (GitHub Pages, `main:/`) |
| Owner owns moodily.in | ✅ `CNAME` in repo |
| **10+ substantive original pieces** | ✅ **11** (see below) |
| Recent content present | ✅ guides + insights, actively edited |
| Affiliate Disclosure page | ✅ written and **feature-gated** — not generated while the programme is off |
| Required Amazon statement ready | ✅ verbatim, renders only when enabled |
| Link-level disclosure | ✅ `(paid link)` beside each link, not footer-only |
| No prohibited Amazon trademarks/assets | ✅ no Amazon logo, photo, review or copy anywhere |
| Associate tag placeholder | ✅ `tag: ""` + TODO |
| Approved Site URLs documented | ⏳ owner to fill `approved_properties` |
| No offline/PDF affiliate plan | ✅ see "Where links may never go" |
| No incentive language | ✅ no "use my link to support Moodily" anywhere |
| No self-purchase strategy | ✅ none |
| No hard-coded Amazon prices | ✅ CTA is "Amazon पर आज का price देखें" |
| Editorial value without ads | ✅ every page stands on its own |

## The 11 original pieces (word counts measured)

| Piece | Words |
|---|---|
| Digital services price guide India 2026 | 1,782 |
| Website vs Google Business Profile vs WhatsApp | 1,121 |
| Medical store home delivery setup | 861 |
| AI workflow automation क्या है | 842 |
| Research को ebook/course में बदलें | 846 |
| PYQ analysis क्या है | 774 |
| Small business website क्यों ज़रूरी | 742 |
| Coaching digital study material | 731 |
| दुकान Google Maps पर कैसे लाएँ | 566 |
| WhatsApp से local orders | 486 |
| Google Business Profile cost | 327 |

Plus `/tools/` (926) and `/learn/` (747) as resource pages. **No filler was written to reach a count.**

## Where affiliate links may never go

- PDFs, eBooks, email attachments, printed or offline material — including client deliverables.
  Moodily client PDFs are never an affiliate distribution channel.
- WhatsApp link blasts.

Permitted shape: **content / social / video → a Moodily resource page → a disclosed link.**

## Product content rules

Moodily-authored descriptions, owner-created imagery, neutral product names. No scraped Amazon
photos, reviews, copy, pricing or logos. No live price or availability unless it comes through an
Amazon-approved mechanism — until then the CTA sends people to Amazon to see the current price.

Every recommendation answers: who is it for · what problem it solves · why it is relevant ·
limitations · who should skip it · alternatives. Where the owner has not used an item, the wording is
**"researched option"**, never "I tested". No "Top 100 Amazon products" listicles.

## Account rules for the owner

- You can apply **before** any qualifying sale.
- After signup the account must produce **at least 3 qualifying sales within 180 days** for Amazon's
  review. **Your own orders do not count.** No fake orders, no incentives — both risk the account.
- Add every property to **Associates Central → Site List** before promoting from it. The owner expects
  moodily.in and possibly an exact YouTube channel URL; nothing else is assumed approved.
- YouTube: if affiliate links appear there, list that exact channel URL and disclose in the
  description and on-screen. Amazon Associates does **not** require YouTube Partner Programme
  eligibility.

## When the tag arrives

1. `site.json → amazon_associates`: `enabled: true`, `tag: "<real-tag>"`, `disclosure_enabled: true`,
   fill `approved_properties`.
2. `python3 build.py` — the guards pass only if all four are consistent.
3. Verify a link carries `tag=`, shows `(paid link)`, and sits inside real editorial content.
4. Confirm the disclosure renders near the content, not only in the footer.
