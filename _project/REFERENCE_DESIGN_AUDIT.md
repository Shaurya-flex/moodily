# Reference design audit — digital-saathi-for-you.vercel.app

Audited 2026-09-17 against the live deployment. Values are computed styles read from the
running page, not guesses. This file is the source of truth for Moodily's v3 design system
(`assets/css/site.css`).

## 1. Ownership call

The reference app's design tokens (`--indigo #232c6b`, `--marigold #e8a33d`, `--paper #f7f5f0`,
Baloo 2 + Mukta) are a bespoke Indian-market palette, and the app sells the same Digital Saathi
service line Moodily sells. Source ownership is **not confirmed from inside this repo** — the app
is a Next.js build with no published source here.

**Decision:** treat it as a *visual/layout reference only*. Every token, component and rule below was
re-implemented independently in Moodily's own CSS. **No reference markup, images, illustrations,
icons or copy were copied.** Moodily's own copy, prices, samples and service data are used throughout.

## 2. Design tokens (measured)

| Token | Value | Role |
|---|---|---|
| `--indigo` | `#232c6b` | primary; headings on cards, primary buttons, links |
| `--indigo-2` | `#39449b` | primary hover |
| `--indigo-soft` | `#eef0fa` | tinted hover/active surfaces |
| `--marigold` | `#e8a33d` | the single action accent (main CTA only) |
| `--marigold-ink` | `#3a2a06` | text on marigold (6.43:1) |
| `--marigold-soft` | `#fdf3e2` | warning/offer surfaces |
| `--leaf` / `--leaf-soft` | `#1b7a5a` / `#e6f3ee` | "done", positive, answer boxes |
| `--chilli` / `--chilli-soft` | `#c0392b` / `#fbeceb` | "fix", errors, won't-do list |
| `--paper` | `#f7f5f0` | page background (warm, not white) |
| `--card` | `#ffffff` | card surface |
| `--ink` / `--ink-2` | `#191b27` / `#5a5f72` | text / muted text |
| `--line` / `--line-2` | `#e4e1d9` / `#c9cbe0` | hairline borders / control borders |

Contrast measured on Moodily's build: ink/paper **15.70**, muted/paper **5.81**,
indigo/paper **11.72**, white/indigo **12.77**, marigold-ink/marigold **6.43**,
footer text/ink **11.15**. All pass WCAG AA; most pass AAA.

## 3. Typography

- Display: **Baloo 2** 500/600/700 — headings, prices, logo. Covers Latin **and Devanagari**.
- Text: **Mukta** 300/400/600/700 — body, buttons, labels. Also covers Devanagari.
- One Google Fonts request serves both scripts, so the old separate Noto Sans Devanagari load is gone.
- h1 `52.8px / 1.15 / -0.01em / 700`; h2 `32.8px / 1.15 / -0.01em / 700`; body `16px / 1.55`.
- Eyebrow: `12.5px`, `700`, `.07em`, uppercase, muted.

## 4. Shape, depth and rhythm

- Radius: **22px** cards/panels (`--r-lg`), **14px** small tiles/inputs (`--r-card`), **999px** buttons.
- Borders: **1px hairline** `--line` on cards; **1.5px** on interactive controls.
- Shadows: **almost none**. Cards are flat with a border. `--shadow` is reserved for menus,
  recommended tiers and the WhatsApp FAB.
- Section rhythm: `clamp(40px, 5vw, 60px)` vertical padding, sections separated by a **1px top border**,
  not by alternating colour slabs. `.alt` is a faint `#f2efe8`, used sparingly.
- Container: **1120px**, 20px gutter.

## 5. Components

- **Header** — sticky, `paper` at 92% + `blur(8px)`, 1px bottom border, ~68px tall. Logo left,
  nav centre-right, actions right. Below 1080px the desktop nav collapses to a bordered "Menu" pill.
- **Buttons** — pill only. `btn-primary` indigo/white; `btn-warm` marigold (used for *one* CTA per view);
  `btn-outline` transparent + border; `btn-wa` WhatsApp green. Sizes `sm 40px` / default `44px` / `lg 52px`.
- **Cards** — white, 22px radius, 1px border, 22px padding, no shadow, actions pinned to the bottom.
- **Hero** — two columns: copy left, a concrete artefact right (the reference uses a Digital Audit
  scorecard). Moodily re-implements the scorecard idea with its own Hindi content, labelled as a sample.
- **Pricing** — a ladder of bands from Free to Premium, each naming the packages it contains,
  rather than a three-tier SaaS table.
- **Trust** — an explicit "every time" / "what we won't do" pair. Moodily ships the same idea
  with its own commitments.
- **Footer** — dark ink panel (`#191b27`), muted `#cfd0da` links, marigold hover.

## 6. What was deliberately **not** copied

- The reference's headline, subhead, FAQ answers and package names — Moodily's own copy is used.
- The reference's price bands (₹1,999 / ₹2,999 entry) — Moodily's canonical price list is used.
- The scorecard's exact rows — rewritten in Hindi for a coaching-centre example.
- Any image, illustration, icon set or logo.
