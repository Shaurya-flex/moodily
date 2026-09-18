# 15 — Google still shows the old Moodily: root cause and reindex steps

## Diagnosis (2026-09-18)

**Stale Google index / search presentation + residual legacy entity signals.**

- The live homepage is already the new, service-led version (GitHub Pages, `last-modified` 2026-09-18, no service worker, so this is not a deploy or cache problem).
- Google Search and AI Overview still describe the older positioning. That text matches the `<title>`/meta of the first homepage (2026-08-26, commit d7b359e). However, **what Google last crawled and indexed can only be confirmed in Search Console → URL Inspection**, and Google can reconstruct or rewrite snippets from several sources.
- Several secondary site signals still carried the old identity: the Organization schema ("free AI learning"), the About title and lead, the footer tagline, a site-wide course-provider note, and the /learn/ slogan. PR #14 fixes all of them.
- CI now fails if the retired slogans ("AI Seekho", "Kamai Karo", "Future Bano", "AI skilling") reappear anywhere in the built site.

## What each old claim is today

| Google claim | Status | Where it lives now |
|---|---|---|
| Free AI skilling roadmap | Still offered as an optional, **secondary** section | /learn/ ("Moodily Learn — learn practical AI and digital workflows"). The slogan was removed everywhere. /learn/, /resources/ and /tools/ stay indexable and each states that it is secondary to services. |
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
