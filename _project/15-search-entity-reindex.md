# 15 — Google still shows the old Moodily: root cause and reindex steps

## Root cause (verified 2026-09-18)

- Google shows this text: "AI Seekho. Kamai Karo. India ka Future Bano" / "Free AI skilling roadmap… LinkedIn ghostwriting from ₹15,000/month. AI workflow setup from ₹7,500. IIT Madras + Government of India certificates."
- That text is, **word for word, the `<title>` and meta description of the first homepage**, uploaded 2026-08-26 (commit d7b359e). That version was a single-page site.
- Live https://moodily.in/ already serves the new service-led homepage (GitHub Pages, `last-modified` 2026-09-18, no service worker).
- **So this is not a deployment problem.** Google has not yet recrawled and reprocessed "/".
- A few live signals still leaned the old way. This branch fixes them:
  - Organization schema: "platform for free AI learning…"
  - About title and lead: Learn first
  - Footer: "सीखें. डिजिटल बनें. बढ़ें. Learn · Build…"
  - A course-provider "no official partnership" note on every page
  - /learn/ H1: "AI Seekho. Kamai Karo."

## What each old claim is today

| Google claim | Status | Where it lives now |
|---|---|---|
| Free AI skilling roadmap | Still true, **secondary** | Only /learn/ ("Moodily Learn — a free AI learning path"); the slogan is a small motto there |
| LinkedIn ghostwriting ₹15,000/month | Current service, **secondary** | /services/professionals/ and the services list |
| AI workflow setup ₹7,500 | Current service, **secondary** | /services/ai-workflows/ and one tile among 15 on the homepage |
| IIT Madras + Govt of India certificates | **Legacy, removed.** CI (`check_site.py`) bans the claim | Nowhere public. "Government of India" appears only as a Copyright Office citation in 2 guides |
| Partnership / affiliation | Moodily has **no** partnership | Disclaimer now shown only on /learn/, /resources/ and /tools/ |

## After this branch is merged and deployed — owner steps in Search Console (once, not repeatedly)

1. In Search Console, open **URL Inspection** for `https://moodily.in/` and click **Test live URL**.
2. Check that Google sees the title "Moodily.in — Websites, Google, WhatsApp, Design & Digital Services" and the H1 "अपनी Digital जरूरत बताइए…".
3. Click **Request indexing** once.
4. In **Sitemaps**, resubmit `https://moodily.in/sitemap.xml`.
5. Inspect `/services/`, `/samples/` and `/about/`, and request indexing for those as well.
6. Over the next 1–4 weeks, watch **Pages** (indexing) and **Performance**. Useful queries: `moodily`, `moodily.in`, and service searches.

## Four separate states — report them separately

| State | How to verify |
|---|---|
| LIVE HTML UPDATED | `curl -s https://moodily.in/ \| grep -o '<title>[^<]*'` |
| GOOGLE RECRAWLED | URL Inspection → "Last crawl" date after the deploy |
| GOOGLE INDEX UPDATED | URL Inspection → "View crawled page" shows the new HTML |
| SEARCH PRESENTATION UPDATED | Search "moodily.in" in a logged-out or incognito window |

Google may keep showing old text for days or weeks, and it can rewrite titles and snippets. A stale result is **not** proof that the deploy failed. Changing the meta description is a site signal, not a guarantee.
