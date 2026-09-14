#!/usr/bin/env python3
"""Static checks for the generated site. Run after build.py:  python3 tests/check_site.py"""
import html as html_lib
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


def check_prices(pages):
    """One price per service: no hard-coded amounts in sources, and every rendered 'Service name … ₹X' must match services.json."""
    site = json.loads((ROOT / "src/site.json").read_text(encoding="utf-8"))
    services = json.loads((ROOT / "src/data/services.json").read_text(encoding="utf-8"))["services"]
    offer = site.get("offer") or {}

    for f in sorted((ROOT / "src/pages").rglob("*.html")) + [ROOT / "src/data/faqs.json"]:
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"₹\s?\d[\d,]*", text):
            fail(str(f.relative_to(ROOT)), "hard-coded price {} — use {{{{price:<service-id>}}}}".format(m.group(0)))

    allowed = {}
    for s in services:
        if not s.get("price_from") or len(s["name"]) < 12:
            continue
        ok = {s["price_from"]}
        if s["id"] in offer.get("services", []):
            ok.add(s["price_from"] * (100 - int(offer["discount_pct"])) // 100)
        allowed[s["name"]] = ok
    name_re = re.compile("|".join(re.escape(n) for n in sorted(allowed, key=len, reverse=True)))
    price_re = re.compile(r"₹\s?([0-9][0-9,]*)")
    for rel, (_, text) in pages.items():
        plain = re.sub(r"<(script|style|svg)\b.*?</\1>", "", text, flags=re.S)
        plain = re.sub(r"</(p|h[1-6]|li|dt|dd|div|td|th)>", " ¦ ", plain)  # names must not match across block boundaries
        plain = re.sub(r"<[^>]+>", " ", plain)
        plain = re.sub(r"\s+", " ", html_lib.unescape(plain))
        found = [(m.end(), m.group(0), m.start()) for m in name_re.finditer(plain)]
        for i, (end, name, _) in enumerate(found):
            stop = min(found[i + 1][2] if i + 1 < len(found) else len(plain), end + 90)
            pm = price_re.search(plain, end, min(len(plain), stop + 16))  # let a number that starts inside the window finish
            if pm and pm.start() < stop and int(pm.group(1).rstrip(",").replace(",", "")) not in allowed[name]:
                fail(rel, "price mismatch: '{}' shown with ₹{} (allowed {})".format(name, pm.group(1), sorted(allowed[name])))
        if (site.get("payments") or {}).get("mode") != "live":
            if re.search(r'href="[^"]*(razorpay\.com|rzp\.io|razorpay\.me)', text):
                fail(rel, "Razorpay link rendered while payments.mode is not 'live' (test links must never reach production)")
            if "data-checkout=" in text:
                fail(rel, "checkout button rendered while payments.mode is not 'live' (rebuild without MOODILY_SHOW_TEST_PAYMENTS)")


def check_no_secrets():
    """Razorpay keys must never be committed: only .env (gitignored) may hold them."""
    env = ROOT / ".env"
    secret_values = []
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                value = line.split("=", 1)[1].strip()
                if len(value) >= 12:
                    secret_values.append(value)
    ignore = {".git", "node_modules", ".wrangler", "__pycache__", ".claude", ".claude-flow"}
    key_re = re.compile(r"rzp_(test|live)_[A-Za-z0-9]{10,}")
    for path in ROOT.rglob("*"):
        if path.is_dir() or any(part in ignore for part in path.parts) or path.name in (".env", ".dev.vars"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(path.relative_to(ROOT))
        if key_re.search(text):
            fail(rel, "Razorpay key id found in a committed file — keys belong in .env / Worker secrets only")
        for value in secret_values:
            if value in text:
                fail(rel, "a value from .env appears in this file — never commit secrets")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    if ".env" not in gitignore.split():
        fail(".gitignore", ".env must be gitignored")


def check_commerce(pages):
    """Sample-first service pages: scope note with prices, samples next to package details, honest concept labels, estimator disclaimer."""
    services = json.loads((ROOT / "src/data/services.json").read_text(encoding="utf-8"))
    note = services["scope_note"]["en"]
    for rel, (_, text) in pages.items():
        if 'name="moodily-redirect"' in text:
            continue
        if "data-pricing" in text and note not in text:
            fail(rel, "prices shown without the scope note")
        if 'class="svc-detail' in text and 'id="samples"' not in text:
            fail(rel, "package details without a samples section")
        if text.count('class="before-after"') > text.count("Concept illustration"):
            fail(rel, "before/after without a concept label")
        if 'id="estimator"' in text and "Final quote after reviewing requirement" not in text:
            fail(rel, "estimator without the final-quote disclaimer")
    for smp in json.loads((ROOT / "src/data/samples.json").read_text(encoding="utf-8"))["samples"]:
        f = ROOT / smp["image"].lstrip("/")
        if not f.exists():
            fail("samples.json", "missing image " + smp["image"])
        elif f.stat().st_size > 300000:
            fail("samples.json", "{} is {} KB — publish an optimized derivative".format(smp["image"], f.stat().st_size // 1024))
    redirects = json.loads((ROOT / "src/data/redirects.json").read_text(encoding="utf-8"))
    for old, new in redirects.items():
        if old.startswith("_"):
            continue
        target = resolve(new)
        if not target or not target.exists():
            fail("redirects.json", "redirect target missing: " + new)
        elif new in redirects or 'name="moodily-redirect"' in target.read_text(encoding="utf-8"):
            fail("redirects.json", "redirect chain: {} → {} is itself a redirect".format(old, new))

    # Every quick-answer card needs a samples section for its "Sample देखें" button, and internal cost data must never ship.
    internal = re.compile(r"(?i)targetPriceInternal|estimatedHoursInternal|cashCostInternal|pricing-internal\.json\"|hourly_floors")
    for rel, (_, text) in pages.items():
        if 'class="answer-box card"' in text and 'id="samples"' not in text:
            fail(rel, "answer box without a samples section")
        if internal.search(text):
            fail(rel, "internal pricing data leaked into a public page")
    for data_file in (ROOT / "src/data").glob("*.json"):
        if re.search(r"(?i)\"(targetPriceInternal|estimatedHoursInternal|cashCostInternal)\"", data_file.read_text(encoding="utf-8")):
            fail(str(data_file.relative_to(ROOT)), "internal pricing fields belong in private/pricing-internal.json (gitignored)")
    if "private/" not in (ROOT / ".gitignore").read_text(encoding="utf-8").split():
        fail(".gitignore", "private/ (internal pricing) must be gitignored")

    # Price type must be visible: exact prices never say "से", custom quotes never show a rupee amount next to the name.
    for s in services["services"]:
        if s.get("active", True) and s.get("price_mode") not in ("exact", "starts_at", "custom_quote", "free"):
            fail("services.json", "{} has no valid price_mode".format(s["id"]))


def main():
    files = json.loads((ROOT / ".build-manifest.json").read_text())
    pages, titles = {}, {}
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8")
        p = Page()
        p.feed(text)
        pages[rel] = (p, text)
        route = route_of(rel)
        is_redirect = 'name="moodily-redirect"' in text
        title = "".join(p.title).strip()
        if not title:
            fail(rel, "missing title")
        if title in titles:
            fail(rel, "duplicate title with " + titles[title])
        titles[title] = rel
        desc = p.meta.get("description", "")
        if not is_redirect and not 50 <= len(desc) <= 300:
            fail(rel, "description length {}".format(len(desc)))
        if p.canonical != BASE + route and route != "/404.html" and not is_redirect:
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

    check_prices(pages)
    check_commerce(pages)
    check_no_secrets()

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
