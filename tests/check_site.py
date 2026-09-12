#!/usr/bin/env python3
"""Static checks for the generated site. Run after build.py:  python3 tests/check_site.py"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://moodily.in"
FAIL = []

# Claims that must never reappear (trust/claims policy) and placeholder leaks.
BANNED = [
    (r"\b4\.8\b", "unsubstantiated rating"), (r"1,200\+", "unsubstantiated learner count"),
    (r"(?i)unlimited revision", "unlimited revisions"), (r"(?i)official certs", "official certs claim"),
    (r"(?i)IIT Madras \+ Govt", "affiliation claim"), (r"(?i)Bharat Sarkar Pramaanpatra", "govt certificate claim"),
    (r"\{\{", "unrendered template variable"),
]
# Checked against raw HTML (attributes included).
RAW_BANNED = [
    (r"wa\.me/9?1?X+", "placeholder WhatsApp number"), (r"rzp_live_", "placeholder payment key"),
    (r"<!--@", "unrendered component token"), (r"_todo", "TODO field leaked into page"),
]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.h1, self.ids, self.links, self.ld = [], 0, set(), [], []
        self.meta, self.canonical, self.imgs_no_alt, self.labels_for, self.controls = {}, None, 0, set(), []
        self.blank_no_rel = 0
        self._in_title = self._in_ld = False
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content", "")
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
            if a.get("target") == "_blank" and "noopener" not in (a.get("rel") or ""):
                self.blank_no_rel += 1
        elif tag == "img" and "alt" not in a:
            self.imgs_no_alt += 1
        elif tag == "label" and a.get("for"):
            self.labels_for.add(a["for"])
        elif tag in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit"):
            self.controls.append(a.get("id"))
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld, self._buf = True, ""

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_ld:
            self.ld.append(self._buf)
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        if self._in_ld:
            self._buf += data


def fail(page, msg):
    FAIL.append("{}: {}".format(page, msg))


def route_of(rel):
    if rel == "404.html":
        return "/404.html"
    return "/" + rel[: -len("index.html")]


def resolve(href):
    path = href.split("#")[0].split("?")[0]
    if not path.startswith("/"):
        return None
    target = ROOT / path.lstrip("/")
    if path.endswith("/"):
        target = target / "index.html"
    return target


def main():
    files = json.loads((ROOT / ".build-manifest.json").read_text())
    pages, titles = {}, {}
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8")
        p = Page()
        p.feed(text)
        pages[rel] = (p, text)
        route = route_of(rel)
        title = "".join(p.title).strip()
        if not title:
            fail(rel, "missing title")
        if title in titles:
            fail(rel, "duplicate title with " + titles[title])
        titles[title] = rel
        desc = p.meta.get("description", "")
        if not 50 <= len(desc) <= 300:
            fail(rel, "description length {}".format(len(desc)))
        if p.canonical != BASE + route and route != "/404.html":
            fail(rel, "canonical {} != {}".format(p.canonical, BASE + route))
        if p.h1 != 1:
            fail(rel, "h1 count {}".format(p.h1))
        if p.imgs_no_alt:
            fail(rel, "{} img without alt".format(p.imgs_no_alt))
        if p.blank_no_rel:
            fail(rel, "{} target=_blank links without noopener".format(p.blank_no_rel))
        for cid in p.controls:
            if cid and cid not in p.labels_for:
                fail(rel, "form control #{} has no <label for>".format(cid))
        for block in p.ld:
            try:
                json.loads(block)
            except ValueError as exc:
                fail(rel, "invalid JSON-LD: {}".format(exc))
        visible = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style|svg)\b.*?</\1>", "", text, flags=re.S))
        for pattern, why in BANNED:
            if re.search(pattern, visible):
                fail(rel, "banned content ({}): /{}/".format(why, pattern))
        for pattern, why in RAW_BANNED:
            if re.search(pattern, text):
                fail(rel, "banned markup ({}): /{}/".format(why, pattern))

    for rel, (p, _) in pages.items():
        for href in p.links:
            target = resolve(href)
            if target is None:
                if href.startswith("#") and len(href) > 1 and href[1:] not in p.ids:
                    fail(rel, "in-page anchor missing: " + href)
                continue
            if not target.exists():
                fail(rel, "broken internal link: " + href)
                continue
            if "#" in href and target.name == "index.html":
                anchor = href.split("#", 1)[1]
                trel = str(target.relative_to(ROOT))
                if anchor and trel in pages and anchor not in pages[trel][0].ids:
                    fail(rel, "anchor #{} not found on {}".format(anchor, trel))

    sm = ET.parse(ROOT / "sitemap.xml").getroot()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for loc in sm.findall("s:url/s:loc", ns):
        url = loc.text
        target = resolve(url.replace(BASE, ""))
        if not target or not target.exists():
            fail("sitemap.xml", "missing file for " + url)
            continue
        rel = str(target.relative_to(ROOT))
        if 'content="noindex' in pages[rel][1]:
            fail("sitemap.xml", "noindex page listed: " + url)

    robots = (ROOT / "robots.txt").read_text()
    if "Sitemap: https://moodily.in/sitemap.xml" not in robots or "Disallow: /\n" in robots:
        fail("robots.txt", "unexpected robots rules")

    if FAIL:
        print("\n".join(FAIL))
        print("\n{} problem(s) found".format(len(FAIL)))
        sys.exit(1)
    print("OK — {} pages checked, {} sitemap URLs".format(len(pages), len(sm)))


if __name__ == "__main__":
    main()
