# Moodily.in

Bilingual (Hindi + English) digital business, learning and services platform — **Moodily Learn · Moodily Digital Saathi · Moodily Intelligence Studio · Moodily Store**.

Static site on GitHub Pages (`main:/`, custom domain `moodily.in`). Pages are generated from `src/` by a dependency-free Python script.

```bash
python3 build.py            # generate HTML, sitemap.xml, robots.txt, _project/OWNER-TODO.md
python3 tests/check_site.py # SEO, links, a11y basics, schema, claims policy
python3 -m http.server 8123 # preview at http://localhost:8123
```

- Edit content: [`_project/05-content-editing.md`](_project/05-content-editing.md)
- Audit, IA, conversion & pricing strategy: [`_project/01-audit-strategy.md`](_project/01-audit-strategy.md)
- SEO, schema, Hindi AEO plan: [`_project/02-seo-schema.md`](_project/02-seo-schema.md)
- Forms, WhatsApp, payments, analytics: [`_project/03-forms-payments-analytics.md`](_project/03-forms-payments-analytics.md)
- Deploy, rollback, Search Console, 30-day backlog: [`_project/04-deploy-indexing-backlog.md`](_project/04-deploy-indexing-backlog.md)
- Missing owner information: [`_project/OWNER-TODO.md`](_project/OWNER-TODO.md)

Generated files (`index.html`, route folders, `404.html`, `sitemap.xml`, `robots.txt`) must not be edited by hand.
