#!/usr/bin/env python3
"""Moodily static site builder.

Python 3.9+, standard library only.  Usage:  python3 build.py

Reads   src/site.json, src/data/*.json, src/pages/**/*.html
Writes  clean-URL HTML to the repo root (GitHub Pages serves main:/),
        plus sitemap.xml, robots.txt and _project/OWNER-TODO.md.

Page files start with a JSON meta block:
    <!--meta { "title": "...", "description": "...", "lang": "hi" } -->
and may contain component tokens:
    <!--@services ids="a,b" -->   <!--@faq set="home" -->
See _project/05-content-editing.md for the full list.
"""
import hashlib
import html
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
MANIFEST = ROOT / ".build-manifest.json"
TODAY = date.today().isoformat()


def load(rel):
    return json.loads((SRC / rel).read_text(encoding="utf-8"))


SITE = load("site.json")
SVC_DATA = load("data/services.json")
SERVICES = {s["id"]: s for s in SVC_DATA["services"]}
DIVISIONS = SVC_DATA["divisions"]
CASES = load("data/case_studies.json")["case_studies"]
CASES_BY_SLUG = {c["slug"]: c for c in CASES}
PRODUCT_DATA = load("data/products.json")
TOOLS = load("data/tools.json")
FAQS = load("data/faqs.json")
LEARN = load("data/learn.json")
BASE = SITE["url"].rstrip("/")
ORG_ID = BASE + "/#organization"
WARNINGS = []

# ---------------------------------------------------------------- offer
OFFER = SITE.get("offer") or {}
PAYMENTS = SITE.get("payments") or {}
HI_MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
HI_DAYS = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]


def _offer_state():
    """Offer is shown only while active, inside its window and with real slots left. Re-evaluated on every build."""
    if not OFFER.get("active"):
        return None
    now = datetime.now(timezone.utc)
    start, end = datetime.fromisoformat(OFFER["starts_at"]), datetime.fromisoformat(OFFER["ends_at"])
    left = int(OFFER["slots_total"]) - int(OFFER["slots_taken"])
    if now < start or now > end or left <= 0:
        return None
    return {"left": left, "end": end}


OFFER_STATE = _offer_state()
NO_BANNER = {"/privacy/", "/terms/", "/refund/", "/contact/thanks/", "/payment/success/", "/404.html", "/offers/{}/".format(OFFER.get("id"))}


def offer_deadline_hi():
    d = OFFER_STATE["end"]
    return "{}, {} {} {}, {}:{:02d} {} IST".format(HI_DAYS[d.weekday()], d.day, HI_MONTHS[d.month - 1], d.year,
                                                  d.hour % 12 or 12, d.minute, "PM" if d.hour >= 12 else "AM")


def in_offer(svc):
    return bool(OFFER_STATE and svc["id"] in OFFER["services"] and svc.get("price_from"))


def offer_price(svc):
    return svc["price_from"] * (100 - int(OFFER["discount_pct"])) // 100


def offer_pay_button(svc, cls="btn btn-primary"):
    """Razorpay Payment Page link when allowed; otherwise an offer-tagged enquiry. Test links never reach production."""
    price = inr(offer_price(svc))
    link = (OFFER.get("payment_links") or {}).get(svc["id"]) or ""
    allowed = PAYMENTS.get("mode") == "live" or os.environ.get("MOODILY_SHOW_TEST_PAYMENTS") == "1"
    api = os.environ.get("MOODILY_CHECKOUT_API") or PAYMENTS.get("api_base") or ""
    if api and allowed:
        test = ' <span class="badge">TEST MODE</span>' if PAYMENTS.get("mode") != "live" else ""
        return '<button type="button" class="{} offer-only" data-checkout="{}" data-api="{}" data-track="checkout_click" data-label="{}-{}">₹{} अभी pay करें</button>{}'.format(
            cls, svc["id"], e(api), OFFER["id"], svc["id"], price, test)
    if link and allowed:
        test = ' <span class="badge">TEST MODE</span>' if PAYMENTS.get("mode") != "live" else ""
        return '<a class="{} offer-only" href="{}" target="_blank" rel="noopener" data-track="checkout_click" data-label="{}-{}">₹{} में slot book करें</a>{}'.format(
            cls, e(link), OFFER["id"], svc["id"], price, test)
    return '<a class="{} offer-only" href="/contact/?service={}&amp;offer={}" data-track="offer_cta_click" data-label="{}">₹{} वाला slot पाएँ</a>'.format(
        cls, svc["id"], OFFER["id"], svc["id"], price)


def offer_meta_html():
    return ('<p class="offer-note offer-only"><strong>{left}/{total}</strong> founding slots बाकी · समय बाकी: <span data-countdown>{deadline} तक</span> · '
            '<a href="/offers/{id}/">शर्तें</a></p>').format(left=OFFER_STATE["left"], total=OFFER["slots_total"], deadline=e(offer_deadline_hi()), id=OFFER["id"])


def offer_banner(route):
    if not OFFER_STATE or route in NO_BANNER:
        return ""
    return ('<aside class="offer-banner offer-only" aria-label="{name} offer"><div class="container offer-inner">'
            '<p><span class="badge badge-offer">{pct}% OFF</span> <strong>{name}:</strong> पहले {total} ग्राहकों के लिए starter packages पर {pct}% छूट</p>'
            '<p class="offer-meta"><strong>{left}/{total}</strong> slots बाकी · समय बाकी: <span data-countdown>{deadline} तक</span></p>'
            '<a class="btn btn-sm offer-btn" href="/offers/{id}/" data-track="offer_cta_click" data-label="banner">Offer देखें →</a></div></aside>').format(
        name=e(OFFER["name"]), pct=OFFER["discount_pct"], total=OFFER["slots_total"], left=OFFER_STATE["left"],
        deadline=e(offer_deadline_hi()), id=OFFER["id"])


def e(value):
    return html.escape("" if value is None else str(value), quote=True)


def inr(n):
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


# ---------------------------------------------------------------- labels
L = {
    "hi": {
        "for": "किसके लिए", "problem": "कौन-सी समस्या हल होती है", "get": "आपको क्या मिलेगा",
        "timeline": "समय", "not": "क्या शामिल नहीं है", "scope": "Revisions और support",
        "from": "शुरुआत", "from_suffix": "से", "month": "/महीना", "custom": "Scope के अनुसार quote",
        "enquire": "इस package की enquiry करें", "wa": "WhatsApp पर पूछें", "details": "पूरी जानकारी देखें",
        "sample": "जुड़ा हुआ work sample", "price_note": "Starting price है। Final quote scope देखकर लिखित में मिलता है।",
        "home": "Home",
    },
    "en": {
        "for": "Who it is for", "problem": "Problem solved", "get": "Exact deliverables",
        "timeline": "Timeline", "not": "What is not included", "scope": "Revisions & support",
        "from": "Starts at", "from_suffix": "", "month": "/month", "custom": "Custom quote",
        "enquire": "Enquire about this package", "wa": "Ask on WhatsApp", "details": "See full details",
        "sample": "Related work sample", "price_note": "Starting price. You get a written quote after scoping.",
        "home": "Home",
    },
}

ROLE_LABELS = {
    "local-business": "Business owner", "medical-store": "Medical store owner", "education": "School/Coaching",
    "professionals": "Professional", "creators": "Creator", "research": "Founder/Researcher",
    "knowledge-to-product": "Expert/Author", "ai-workflows": "Business owner",
}


# -------------------------------------------------------------- whatsapp
def wa_text(role="[role]", service="[service]"):
    return (
        "Namaste Moodily,\n"
        "Main {role} hoon.\n"
        "Mujhe {service} chahiye.\n"
        "Mera business/profession [type] hai.\n"
        "City [city] hai.\n"
        "Budget approx [budget] hai.\n"
        "Current website/social link [URL] hai."
    ).format(role=role, service=service)


def wa_href(text):
    number = SITE["whatsapp"].get("number")
    if not number:
        return "/contact/"
    return "https://wa.me/{}?text={}".format(number, quote(text))


WA_ICON = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8s-.4-.1-.6.1-.7.8-.8 1-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.3-.4.3-.4.8-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.1 5.1 0 0 0 1.1 2.7 11.6 11.6 0 0 0 4.5 4c1.7.7 2.3.8 3.2.6a2.7 2.7 0 0 0 1.8-1.2 2.2 2.2 0 0 0 .1-1.3c0-.1-.2-.2-.4-.3Z"/></svg>')


def wa_button(label, role="[role]", service="[service]", cls="btn btn-wa", track_label="generic"):
    return '<a class="{}" href="{}" target="_blank" rel="noopener" data-track="whatsapp_click" data-label="{}">{} {}</a>'.format(
        cls, e(wa_href(wa_text(role, service))), e(track_label), WA_ICON, e(label))


# ------------------------------------------------------------ components
def price_html(svc):
    lab = L[svc["lang"]]
    if svc.get("price_from") is None:
        return '<p class="price"><strong>{}</strong></p>'.format(lab["custom"])
    unit = lab["month"] if svc["price_unit"] == "month" else ""
    offer = in_offer(svc)
    regular = '<p class="price{}"><span class="price-from">{}</span> <strong>₹{}</strong>{} <span class="price-from">{}</span></p>'.format(
        " regular-only" if offer else "", lab["from"], inr(svc["price_from"]),
        '<span class="price-unit">{}</span>'.format(unit) if unit else "", lab["from_suffix"])
    if not offer:
        return regular
    return ('<p class="price offer-only"><span class="badge badge-offer">{pct}% OFF · {name}</span> <strong>₹{op}</strong> '
            '<s class="price-was"><span class="sr-only">Regular starting price </span>₹{reg}</s></p>').format(
        pct=OFFER["discount_pct"], name=e(OFFER["name"]), op=inr(offer_price(svc)), reg=inr(svc["price_from"])) + regular


def service_card(svc, ctx):
    """Compact overview card linking to the service page."""
    lab = L[svc["lang"]]
    items = "".join("<li>{}</li>".format(e(d)) for d in svc["deliverables"][:3])
    return (
        '<article class="card svc-card{feat}">'
        '<p class="eyebrow">{div}</p><h3>{name}</h3><p class="muted">{tag}</p>{price}'
        '<ul class="ticks">{items}</ul>'
        '<div class="card-actions">{offer_btn}<a class="btn btn-outline" href="{page}#{id}" data-track="price_click" data-label="{id}">{details}</a></div>'
        '</article>'
    ).format(feat=" featured" if svc.get("featured") else "", div=e(DIVISIONS[svc["division"]]), name=e(svc["name"]),
             tag=e(svc["tagline"]), price=price_html(svc), items=items, page=svc["page"], id=svc["id"], details=lab["details"],
             offer_btn=offer_pay_button(svc) if in_offer(svc) else "")


def service_detail(svc, ctx):
    lab = L[svc["lang"]]
    ctx["services"].append(svc)
    deliver = "".join("<li>{}</li>".format(e(d)) for d in svc["deliverables"])
    excluded = "".join("<li>{}</li>".format(e(d)) for d in svc["not_included"])
    case_html = ""
    cs = CASES_BY_SLUG.get(svc.get("case_study") or "")
    if cs:
        if cs["status"] == "published":
            case_html = '<p class="case-link">{}: <a href="/case-studies/{}/" data-track="case_study_open" data-label="{}">{}</a></p>'.format(
                lab["sample"], cs["slug"], cs["slug"], e(cs["title"]))
        else:
            case_html = '<p class="case-link">{}: <a href="/case-studies/#{}">{}</a></p>'.format(lab["sample"], cs["slug"], e(cs["title"]))
    compliance = ""
    if svc.get("compliance_note"):
        compliance = '<p class="notice">{}</p>'.format(e(svc["compliance_note"]))
    role = ROLE_LABELS.get(svc["category"], "[role]")
    offer = in_offer(svc)
    wa_service = "{} offer — {} (₹{})".format(OFFER["name"], svc["name"], inr(offer_price(svc))) if offer else svc["name"]
    return (
        '<article class="svc-detail{feat}" id="{id}" data-service-id="{id}">'
        '<header class="svc-head"><div><p class="eyebrow">{div}</p><h3>{name}</h3><p class="muted">{tag}</p></div>'
        '<div class="svc-price">{price}<p class="small muted">{note}</p></div></header>'
        '<dl class="facts"><div><dt>{l_for}</dt><dd>{for_}</dd></div><div><dt>{l_problem}</dt><dd>{problem}</dd></div>'
        '<div><dt>{l_time}</dt><dd>{timeline}</dd></div><div><dt>{l_scope}</dt><dd>{rev} · {sup}</dd></div></dl>'
        '<h4>{l_get}</h4><ul class="ticks">{deliver}</ul>'
        '<details class="not-included"><summary>{l_not}</summary><ul class="crosses">{excluded}</ul></details>'
        '{compliance}{case}'
        '{offer_meta}<div class="card-actions">{offer_btn}'
        '<a class="btn btn-primary{reg_cls}" href="/contact/?service={id}" data-track="price_click" data-label="{id}">{enquire}</a>'
        '{wa}</div></article>'
    ).format(
        feat=" featured" if svc.get("featured") else "", id=svc["id"], div=e(DIVISIONS[svc["division"]]), name=e(svc["name"]),
        tag=e(svc["tagline"]), price=price_html(svc), note=lab["price_note"], l_for=lab["for"], for_=e(svc["for"]),
        l_problem=lab["problem"], problem=e(svc["problem"]), l_time=lab["timeline"], timeline=e(svc["timeline"]),
        l_scope=lab["scope"], rev=e(svc["revisions"]), sup=e(svc["support"]), l_get=lab["get"], deliver=deliver,
        l_not=lab["not"], excluded=excluded, compliance=compliance, case=case_html, enquire=lab["enquire"],
        wa=wa_button(lab["wa"], role, wa_service, "btn btn-wa", svc["id"]),
        offer_meta=offer_meta_html() if offer else "", offer_btn=offer_pay_button(svc) if offer else "",
        reg_cls=" regular-only" if offer else "")


def c_services(args, ctx):
    ids = [i.strip() for i in args.get("ids", "").split(",") if i.strip()]
    if args.get("category"):
        ids = [s["id"] for s in SVC_DATA["services"] if s["category"] == args["category"]]
    if args.get("featured"):
        ids = [s["id"] for s in SVC_DATA["services"] if s.get("featured")]
    missing = [i for i in ids if i not in SERVICES]
    if missing:
        raise SystemExit("Unknown service ids: {}".format(missing))
    if args.get("style") == "detail":
        return '<div class="svc-list">{}</div>'.format("".join(service_detail(SERVICES[i], ctx) for i in ids))
    return '<div class="grid grid-3">{}</div>'.format("".join(service_card(SERVICES[i], ctx) for i in ids))


def c_price_table(args, ctx):
    rows = []
    for s in SVC_DATA["services"]:
        price = "₹{}{}".format(inr(s["price_from"]), " /month" if s["price_unit"] == "month" else "") if s["price_from"] else "Custom quote"
        rows.append('<tr><th scope="row"><a href="{}#{}">{}</a></th><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            s["page"], s["id"], e(s["name"]), e(DIVISIONS[s["division"]]), e(price), e(s["timeline"])))
    return ('<div class="table-wrap"><table class="price-table"><caption>सभी prices starting prices हैं · All prices are starting prices (INR)</caption>'
            '<thead><tr><th scope="col">Service</th><th scope="col">Division</th><th scope="col">Starts at</th><th scope="col">Timeline</th></tr></thead>'
            '<tbody>{}</tbody></table></div>').format("".join(rows))


def c_payg(args, ctx):
    rows = "".join(
        '<tr><th scope="row">{}</th><td>₹{}</td><td>{}</td><td><a class="btn btn-outline btn-sm" href="/contact/?service=linkedin-payg" data-track="price_click" data-label="payg-{}">Enquire</a></td></tr>'.format(
            e(p["name"]), inr(p["price"]), e(p["posts"]), e(p["price"])) for p in SVC_DATA["payg_linkedin"])
    return ('<div class="table-wrap"><table class="price-table"><caption>LinkedIn pay-as-you-go packs (one-time, starting prices)</caption>'
            '<thead><tr><th scope="col">Pack</th><th scope="col">Starts at</th><th scope="col">Posts</th><th scope="col"><span class="sr-only">Action</span></th></tr></thead>'
            '<tbody>{}</tbody></table></div>').format(rows)


ROUTER = [
    ("🏪", "दुकान / Local Business", "Google Maps, WhatsApp orders, reviews", "/services/local-business/"),
    ("💊", "Medical Store / Clinic", "WhatsApp enquiry से verified delivery तक", "/services/medical-store/"),
    ("🏫", "School / Coaching", "PYQ analysis, tests, worksheets, visual notes", "/services/education/"),
    ("👔", "Professional", "LinkedIn, bio और online credibility", "/services/professionals/"),
    ("🎥", "Creator", "Content plan, scripts, repurposing", "/services/creators/"),
    ("🚀", "Founder / Startup", "Research, competitor intelligence, AI workflows", "/services/research/"),
    ("🎓", "Student", "Free AI learning और study resources", "/learn/"),
]


def c_audience_router(args, ctx):
    cards = "".join(
        '<a class="router-card" href="{}" data-track="audience_select" data-label="{}"><span class="router-emoji" aria-hidden="true">{}</span>'
        '<span class="router-title">{}</span><span class="router-sub">{}</span><span class="router-go" aria-hidden="true">→</span></a>'.format(
            href, e(title), emo, e(title), e(sub)) for emo, title, sub, href in ROUTER)
    return '<div class="router">{}</div>'.format(cards)


def c_cases(args, ctx):
    limit = int(args.get("limit", "0") or 0)
    items = CASES[:limit] if limit else CASES
    cards = []
    for c in items:
        svc = SERVICES.get(c["service"])
        if c["status"] == "published":
            link = '<a class="stretched" href="/case-studies/{0}/" data-track="case_study_open" data-label="{0}">{1}</a>'.format(c["slug"], e(c["title"]))
            badge = '<span class="badge badge-ok">Case study</span>'
        else:
            link = e(c["title"])
            badge = '<span class="badge">Detailed write-up in progress</span>'
        svc_link = '<a class="small" href="{}#{}">{} →</a>'.format(svc["page"], svc["id"], e(svc["name"])) if svc else ""
        cards.append('<article class="card case-card" id="{}"><p class="eyebrow">{} · {}</p><h3>{}</h3><p class="muted small">{}</p>{}<p>{}</p></article>'.format(
            c["slug"], e(c["category"]), e(DIVISIONS[c["division"]]), link, e(c["work_type"]), badge, svc_link))
    return '<div class="grid grid-3">{}</div>'.format("".join(cards))


def c_products(args, ctx):
    cats = PRODUCT_DATA["categories"]
    want = args.get("category")
    limit = int(args.get("limit", "0") or 0)
    items = [p for p in PRODUCT_DATA["products"] if not want or p["category"] == want]
    if limit:
        items = items[:limit]
    cards = []
    for p in items:
        contents = [c for c in p.get("contents", []) if not c.startswith("_todo")]
        contents_html = "<ul class=\"ticks small\">{}</ul>".format("".join("<li>{}</li>".format(e(c)) for c in contents)) if contents else ""
        disclaimer = '<p class="small muted">{}</p>'.format(e(p["disclaimer"])) if p.get("disclaimer") else ""
        if p["status"] == "available" and p.get("price") and p.get("checkout_url"):
            ctx["products"].append(p)
            price = '<p class="price"><strong>₹{}</strong></p>'.format(inr(p["price"]))
            cta = '<a class="btn btn-primary" href="{}" rel="noopener" data-track="checkout_click" data-label="{}">खरीदें · Buy</a>'.format(e(p["checkout_url"]), p["slug"])
        else:
            price = '<p class="price"><span class="badge">जल्द आ रहा है · Coming soon</span></p>'
            cta = wa_button("Waitlist में जुड़ें", "interested buyer", "Store: " + p["title"], "btn btn-outline", "waitlist-" + p["slug"])
            cta = cta.replace('data-track="whatsapp_click"', 'data-track="checkout_click"')
        preview = '<a class="small" href="{}">Preview →</a>'.format(e(p["preview"])) if p.get("preview") else ""
        cards.append(
            '<article class="card product-card" id="{slug}" data-product="{slug}"><div class="thumb" aria-hidden="true">{emoji}</div>'
            '<p class="eyebrow">{cat}</p><h3>{title}</h3>'
            '<dl class="facts compact"><div><dt>किसके लिए</dt><dd>{buyer}</dd></div><div><dt>समस्या</dt><dd>{problem}</dd></div></dl>'
            '{contents}{price}<p class="small muted">Licence: {licence} · <a href="/refund/">Digital goods refund policy</a></p>{disc}'
            '<div class="card-actions">{cta}{preview}</div></article>'.format(
                slug=p["slug"], emoji=p.get("emoji", "📄"), cat=e(cats[p["category"]]), title=e(p["title"]), buyer=e(p["buyer"]),
                problem=e(p["problem"]), contents=contents_html, price=price, licence=e(p.get("licence") or PRODUCT_DATA["default_licence"]),
                disc=disclaimer, cta=cta, preview=preview))
    return '<div class="grid grid-3">{}</div>'.format("".join(cards))


def c_product_categories(args, ctx):
    pills = "".join('<li><a class="pill" href="#cat-{0}">{1}</a></li>'.format(k, e(v)) for k, v in PRODUCT_DATA["categories"].items())
    return '<ul class="pill-row" aria-label="Product categories">{}</ul>'.format(pills)


def c_products_by_category(args, ctx):
    out = []
    for key, label in PRODUCT_DATA["categories"].items():
        if not any(p["category"] == key for p in PRODUCT_DATA["products"]):
            continue
        out.append('<section class="sub-section" id="cat-{}" aria-labelledby="h-cat-{}"><h2 id="h-cat-{}">{}</h2>{}</section>'.format(
            key, key, key, e(label), c_products({"category": key}, ctx)))
    return "".join(out)


def c_tools(args, ctx):
    out = []
    for t in TOOLS["tools"]:
        href = t.get("affiliate_url") or t["official_url"]
        rel = "sponsored noopener" if t.get("affiliate_url") else "noopener"
        tag = '<span class="badge">Affiliate link</span>' if t.get("affiliate_url") else '<span class="badge">No affiliate link</span>'
        lst = lambda xs, cls: '<ul class="{}">{}</ul>'.format(cls, "".join("<li>{}</li>".format(e(x)) for x in xs))
        steps = '<ol class="steps-list">{}</ol>'.format("".join("<li>{}</li>".format(e(x)) for x in t["tutorial"]))
        guide = '<p><a href="{}">पूरी Hindi guide पढ़ें →</a></p>'.format(t["guide"]) if t.get("guide") else ""
        out.append(
            '<article class="tool" id="{slug}"><header class="tool-head"><div><p class="eyebrow">{type}</p><h2>{name}</h2></div>{tag}</header>'
            '<div class="grid grid-2 tool-grid">'
            '<div><h3>क्या करता है</h3><p>{what}</p><h3>Moodily क्यों recommend करता है</h3><p>{use}</p><h3>Real use case</h3><p>{case}</p></div>'
            '<div><h3>Pros</h3>{pros}<h3>Limitations</h3>{cons}<h3>Alternatives</h3>{alts}</div></div>'
            '<h3>Quick tutorial</h3>{steps}{guide}'
            '<p><a class="btn btn-outline" href="{href}" target="_blank" rel="{rel}" data-track="tool_affiliate_click" data-label="{slug}">{name} खोलें ↗</a></p>'
            '</article>'.format(slug=t["slug"], type=e(t["type"]), name=e(t["name"]), tag=tag, what=e(t["what"]), use=e(t["moodily_use"]),
                                case=e(t["use_case"]), pros=lst(t["pros"], "ticks"), cons=lst(t["limitations"], "crosses"),
                                alts=lst(t["alternatives"], "plain"), steps=steps, guide=guide, href=e(href), rel=rel))
    toc = "".join('<li><a class="pill" href="#{}">{}</a></li>'.format(t["slug"], e(t["name"])) for t in TOOLS["tools"])
    return '<ul class="pill-row">{}</ul><p class="small muted">Last reviewed: {}</p>{}'.format(toc, TOOLS["last_reviewed"], "".join(out))


def c_faq(args, ctx):
    items = [{"q": render_prices(i["q"]), "a": render_prices(i["a"])} for i in FAQS[args["set"]]]
    ctx["faqs"].extend(items)
    return '<div class="faq-list">{}</div>'.format("".join(
        '<details class="faq"><summary>{}</summary><p>{}</p></details>'.format(e(i["q"]), e(i["a"])) for i in items))


QUALITY = [
    ("Understand", "समझें", "आपका business, ग्राहक और लक्ष्य — एक छोटी call या WhatsApp voice note से।"),
    ("Research", "Research", "आपके competitors, area और platform guidelines की जाँच।"),
    ("Build", "बनाएँ", "Listing, website, content या workflow — तय scope के अनुसार।"),
    ("Verify", "जाँचें", "Links, नंबर, तथ्य, spelling और mobile view की checklist।"),
    ("Human Review", "Human review", "AI से बना हर हिस्सा इंसान पढ़कर approve करता है।"),
    ("Client Approval", "आपकी approval", "आपकी हाँ के बिना कुछ भी live नहीं होता।"),
    ("Measure & Improve", "मापें और सुधारें", "जो data उपलब्ध है (calls, clicks, enquiries) उसे देखकर अगला सुधार।"),
]


def c_quality_workflow(args, ctx):
    steps = "".join('<li><span class="step-num">{}</span><div><h3>{} <span class="muted small">· {}</span></h3><p>{}</p></div></li>'.format(
        i + 1, e(hi), e(en), e(desc)) for i, (en, hi, desc) in enumerate(QUALITY))
    labels = ""
    if args.get("labels") != "no":
        labels = ('<div class="evidence-labels"><p><strong>Research और education projects में हर बात पर label:</strong></p>'
                  '<ul class="label-row"><li><span class="ev ev-fact">FACT</span> source से प्रमाणित</li>'
                  '<li><span class="ev ev-inf">INFERENCE</span> तथ्यों से निकाला निष्कर्ष</li>'
                  '<li><span class="ev ev-hyp">HYPOTHESIS</span> जाँचने लायक विचार</li>'
                  '<li><span class="ev ev-unv">UNVERIFIED</span> पुष्टि नहीं हो सकी</li></ul></div>')
    return ('<ol class="quality">{}</ol>{}<p class="small muted">यह Moodily की अपनी internal working process है — किसी third-party संस्था का certification नहीं।</p>').format(steps, labels)


def c_final_cta(args, ctx):
    if args.get("lang") == "en":
        return (
            '<section class="final-cta" aria-labelledby="final-cta-h"><div class="container final-cta-inner">'
            '<h2 id="final-cta-h">{title}</h2><p>{sub}</p><div class="btn-row">'
            '<a class="btn btn-primary btn-lg" href="/contact/" data-track="hero_cta_click" data-label="final-enquiry-en">Send an enquiry</a>'
            '{wa}</div></div></section>'
        ).format(title=e(args.get("title", "Let's talk.")), sub=e(args.get("sub", "")),
                 wa=wa_button("WhatsApp us", track_label="final-cta-en", cls="btn btn-wa btn-lg"))
    return (
        '<section class="final-cta" aria-labelledby="final-cta-h"><div class="container final-cta-inner">'
        '<h2 id="final-cta-h">{title}</h2><p>{sub}</p><div class="btn-row">'
        '<a class="btn btn-primary btn-lg" href="/contact/?service=free-digital-audit" data-track="hero_cta_click" data-label="final-audit">मुफ़्त Digital Audit लें</a>'
        '{wa}</div><p class="small">या <a href="/learn/">AI सीखना चाहते हैं? Free Learning देखें →</a></p></div></section>'
    ).format(title=e(args.get("title", "आपका अगला ग्राहक आपको online ढूँढ रहा है।")),
             sub=e(args.get("sub", "5 मिनट में अपनी ज़रूरत बताइए। हम साफ़ बताएँगे कि क्या करना चाहिए — और क्या नहीं।")),
             wa=wa_button("अपनी जरूरत WhatsApp करें", track_label="final-cta", cls="btn btn-wa btn-lg"))


def c_wa(args, ctx):
    return wa_button(args.get("label", "WhatsApp करें"), args.get("role", "[role]"), args.get("service", "[service]"),
                     args.get("class", "btn btn-wa"), args.get("track", "inline"))


def c_learn_curriculum(args, ctx):
    out = []
    for s in LEARN["stages"]:
        tiles = "".join(
            '<li class="course-tile"><span class="badge">{}</span><span class="cname">{}</span><span class="cert small">Certificate, if offered, is issued by the provider</span></li>'.format(
                e(c["provider"]), '<a href="{}" target="_blank" rel="noopener">{}</a>'.format(e(c["url"]), e(c["name"])) if c.get("url") else e(c["name"]))
            for c in s["courses"])
        stars = "".join('<button type="button" class="star" data-stage="{0}" data-value="{1}" aria-label="Rate stage {2}: {1} of 5">★</button>'.format(
            s["id"], k, s["num"]) for k in range(1, 6))
        out.append(
            '<details class="stage" id="stage-{id}"{open}><summary><span class="stage-num">Stage {num}</span><span class="stage-title">{title}</span>'
            '<span class="stage-time">{time}</span></summary><div class="stage-body"><p class="goal-strip">{goal}</p>'
            '<ul class="course-tiles">{tiles}</ul><p class="project-box"><strong>Project:</strong> {project}</p>'
            '<p class="muted"><strong>Skill outcome:</strong> {skill}</p>'
            '<div class="stage-stars" role="group" aria-label="Your private rating (saved on this device only)">{stars}<span class="small muted" id="ratingLabel-{id}"></span></div>'
            '</div></details>'.format(id=s["id"], open=" open" if s["num"] == 1 else "", num=s["num"], title=e(s["title"]), time=e(s["time"]),
                                       goal=e(s["goal"]), tiles=tiles, project=e(s["project"]), skill=e(s["skill"]), stars=stars))
    return ('<div class="stage-controls"><button type="button" class="btn btn-outline btn-sm" data-stages="open">Expand all</button>'
            '<button type="button" class="btn btn-outline btn-sm" data-stages="close">Collapse all</button></div>{}').format("".join(out))


def c_lead_form(args, ctx):
    opt = lambda values: "".join('<option value="{0}">{0}</option>'.format(e(v)) for v in values)
    roles = ["Business", "Medical Store", "Clinic", "School", "Coaching Institute", "Professional", "Creator", "Startup", "Student", "Other"]
    budgets = ["₹2K–₹5K", "₹5K–₹15K", "₹15K–₹50K", "₹50K+", "Need recommendation"]
    service_opts = '<option value="free-digital-audit">मुफ़्त Digital Audit</option>' + "".join(
        '<option value="{}">{}</option>'.format(s["id"], e(s["name"])) for s in SVC_DATA["services"]) + \
        '<option value="linkedin-payg">LinkedIn pay-as-you-go pack</option><option value="store-product">Store / digital product</option><option value="not-sure">पता नहीं — सुझाव चाहिए</option>'
    endpoint = SITE["form"].get("endpoint") or ""
    return FORM_TEMPLATE.format(endpoint=e(endpoint), success=e(SITE["form"]["success_path"]), roles=opt(roles),
                                budgets=opt(budgets), services=service_opts, offer_id=e(OFFER["id"]) if OFFER_STATE else "",
                                offer_note=e("आप {} offer ({}% छूट) के लिए enquiry कर रहे हैं। Slot पूरा payment मिलने पर ही पक्का होता है।".format(
                                    OFFER.get("name", ""), OFFER.get("discount_pct", ""))))


FORM_TEMPLATE = """
<form class="lead-form" id="leadForm" data-endpoint="{endpoint}" data-success="{success}" data-offer-id="{offer_id}" novalidate>
  <p class="small muted">* ज़रूरी fields. आपकी जानकारी केवल आपकी enquiry का जवाब देने के लिए — <a href="/privacy/">Privacy Policy</a>.</p>
  <input type="hidden" id="f-offer" name="offer" value="">
  <p class="notice small" id="offerNote" hidden>{offer_note}</p>
  <fieldset><legend>आपके बारे में</legend>
    <div class="form-grid">
      <div class="field"><label for="f-name">नाम / Name *</label><input id="f-name" name="name" autocomplete="name" required></div>
      <div class="field"><label for="f-wa">WhatsApp number *</label><input id="f-wa" name="whatsapp" type="tel" inputmode="tel" autocomplete="tel" pattern="[0-9+ ]{{10,15}}" placeholder="10-digit mobile number" required aria-describedby="f-wa-hint"><small id="f-wa-hint" class="hint">10 अंक या country code के साथ</small></div>
      <div class="field"><label for="f-email">Email *</label><input id="f-email" name="email" type="email" autocomplete="email" required></div>
      <div class="field"><label for="f-city">City / Country *</label><input id="f-city" name="city" autocomplete="address-level2" required></div>
      <div class="field"><label for="f-role">आप कौन हैं? / Role *</label><select id="f-role" name="role" required><option value="">चुनें</option>{roles}</select></div>
      <div class="field"><label for="f-lang">Preferred language *</label><select id="f-lang" name="language" required><option value="Hindi">हिंदी</option><option value="English">English</option><option value="Hinglish">Hinglish</option></select></div>
    </div>
  </fieldset>
  <fieldset><legend>आपकी ज़रूरत</legend>
    <div class="form-grid">
      <div class="field"><label for="f-service">Service category *</label><select id="f-service" name="service" required>{services}</select></div>
      <div class="field"><label for="f-budget">Budget range *</label><select id="f-budget" name="budget" required><option value="">चुनें</option>{budgets}</select></div>
      <div class="field"><label for="f-deadline">Deadline</label><select id="f-deadline" name="deadline"><option value="Flexible">Flexible</option><option value="1 week">1 हफ़्ते में</option><option value="2-4 weeks">2–4 हफ़्ते</option><option value="1-3 months">1–3 महीने</option></select></div>
      <div class="field"><label for="f-link">Existing website / social profile</label><input id="f-link" name="link" type="url" inputmode="url" placeholder="https://"></div>
      <div class="field field-full"><label for="f-goal">आपका मुख्य goal *</label><input id="f-goal" name="goal" required placeholder="जैसे: Google Maps से ज़्यादा calls, WhatsApp orders व्यवस्थित करना"></div>
      <div class="field field-full"><label for="f-msg">Message</label><textarea id="f-msg" name="message" rows="4"></textarea></div>
      <div class="field field-full"><label for="f-attach">Attachment link (optional)</label><input id="f-attach" name="attachment_link" type="url" inputmode="url" placeholder="Google Drive / Dropbox link" aria-describedby="f-attach-hint"><small id="f-attach-hint" class="hint">Files को link के रूप में share करें। Prescription, ID या कोई medical/sensitive document यहाँ न भेजें।</small></div>
    </div>
  </fieldset>
  <div class="hp" aria-hidden="true"><label for="f-company">Company</label><input id="f-company" name="company_hp" tabindex="-1" autocomplete="off"></div>
  <div class="field consent"><input id="f-consent" name="consent" type="checkbox" value="yes" required><label for="f-consent">मैं सहमत हूँ कि Moodily इस enquiry के बारे में मुझसे WhatsApp/email पर संपर्क करे। *</label></div>
  <p class="form-error" id="formError" role="alert" hidden></p>
  <button class="btn btn-primary btn-lg btn-block" type="submit">Enquiry भेजें →</button>
</form>
"""


def c_offer_details(args, ctx):
    if not OFFER_STATE:
        if args.get("ended") == "hide":
            return ""
        return ('<div class="container"><p class="notice">{} offer अभी उपलब्ध नहीं है — समय समाप्त हो गया या सभी slots भर गए। '
                'Regular starting prices <a href="/services/">यहाँ देखें</a>।</p></div>').format(e(OFFER.get("name", "यह")))
    cards = []
    for sid in OFFER["services"]:
        s = SERVICES[sid]
        if s not in ctx["services"]:
            ctx["services"].append(s)
        items = "".join("<li>{}</li>".format(e(d)) for d in s["deliverables"][:3])
        cards.append('<article class="card offer-card featured"><p class="eyebrow">{div}</p><h3>{name}</h3><p class="muted small">{for_}</p>{price}'
                     '<ul class="ticks small">{items}</ul><div class="card-actions">{btn}<a class="btn btn-outline" href="{page}#{id}">पूरी जानकारी</a></div></article>'.format(
                         div=e(DIVISIONS[s["division"]]), name=e(s["name"]), for_=e(s["for"]), price=price_html(s), items=items,
                         btn=offer_pay_button(s), page=s["page"], id=s["id"]))
    return ('<section class="offer-section offer-only" id="offer-{id}" aria-labelledby="offer-h"><div class="container">'
            '<div class="section-head"><p class="eyebrow">{name} · सिर्फ़ पहले {total} ग्राहक</p>'
            '<h2 id="offer-h">{n} starter packages पर {pct}% छूट</h2>'
            '<p class="lead"><strong>{left}/{total}</strong> slots बाकी · समय बाकी: <span class="countdown" data-countdown>{deadline} तक</span></p>'
            '<p class="muted small">Scope वही जो regular package में है — सिर्फ़ दाम कम। Slot पूरा payment मिलने पर पक्का होता है। <a href="/offers/{id}/">पूरी शर्तें</a></p></div>'
            '<div class="grid grid-3">{cards}</div></div></section>').format(
        id=OFFER["id"], name=e(OFFER["name"]), total=OFFER["slots_total"], n=len(OFFER["services"]), pct=OFFER["discount_pct"],
        left=OFFER_STATE["left"], deadline=e(offer_deadline_hi()), cards="".join(cards))


def c_offer_terms(args, ctx):
    names = ", ".join(e(SERVICES[s]["name"]) for s in OFFER.get("services", []))
    deadline = e(offer_deadline_hi()) if OFFER_STATE else e(OFFER.get("ends_at", ""))
    total, pct = OFFER.get("slots_total"), OFFER.get("discount_pct")
    items = [
        "{} offer: {} पर regular starting price से {}% छूट।".format(e(OFFER.get("name")), names, pct),
        "कुल {} founding slots — इन packages को मिलाकर। Offer {} तक या सभी slots भरने तक, जो पहले हो।".format(total, deadline),
        "Slot तभी पक्का होता है जब founding price का पूरा payment मिल जाए। सिर्फ़ enquiry या WhatsApp message से slot reserve नहीं होता।",
        "हर business के लिए एक founding slot।",
        "Scope, deliverables, timeline और revisions वही हैं जो service page पर regular package में लिखे हैं। Extra काम regular rates पर।",
        "यह offer किसी दूसरे discount के साथ नहीं जुड़ता।",
        "अगर एक साथ payments आने से {} से ज़्यादा bookings हो जाएँ, तो अतिरिक्त bookings का पूरा पैसा 7 working days में लौटाया जाएगा, या आप regular price पर जारी रख सकते हैं।".format(total),
        "काम के बाद हम feedback माँगेंगे। आपका project case study में सिर्फ़ आपकी लिखित अनुमति से दिखेगा — यह offer की शर्त नहीं है। Discount के बदले Google review नहीं माँगा जाता।",
        "Slots का counter हर confirmed booking के बाद update होता है। <a href=\"/refund/\">Refund policy</a> लागू है।",
    ]
    return '<ol class="terms-list">{}</ol>'.format("".join("<li>{}</li>".format(i) for i in items))


def c_founder(args, ctx):
    f = SITE["founder"]
    if not f.get("name"):
        WARNINGS.append("founder details missing — /about/ shows team statement only")
        return ('<p>Moodily एक founder-led, India-based team है। हर project में आपसे सीधे वही लोग बात करते हैं जो काम करते हैं। '
                'सवाल हों तो <a href="mailto:{0}">{0}</a> पर लिखें।</p>').format(e(SITE["email"]))
    li = ' · <a href="{}" rel="noopener" target="_blank">LinkedIn</a>'.format(e(f["linkedin"])) if f.get("linkedin") else ""
    return '<div class="card"><h3>{}</h3><p class="muted">{}{}</p><p>{}</p></div>'.format(e(f["name"]), e(f.get("role", "")), li, e(f.get("bio", "")))


COMPONENTS = {
    "services": c_services, "price-table": c_price_table, "payg": c_payg, "audience-router": c_audience_router,
    "cases": c_cases, "products": c_products, "product-categories": c_product_categories,
    "products-by-category": c_products_by_category, "tools": c_tools, "faq": c_faq,
    "quality-workflow": c_quality_workflow, "final-cta": c_final_cta, "wa": c_wa,
    "learn-curriculum": c_learn_curriculum, "lead-form": c_lead_form, "founder": c_founder,
    "offer-details": c_offer_details, "offer-terms": c_offer_terms,
}

TOKEN_RE = re.compile(r"<!--@([\w-]+)(.*?)-->", re.S)
ARG_RE = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')
VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")
PRICE_RE = re.compile(r"\{\{\s*price:([\w-]+)\s*\}\}")


def render_prices(text):
    """{{price:<service-id>}} -> regular starting price from services.json (single source of truth)."""
    def sub(m):
        s = SERVICES.get(m.group(1))
        if not s or not s.get("price_from"):
            raise SystemExit("Unknown or unpriced service in {{price:%s}}" % m.group(1))
        return "₹" + inr(s["price_from"])
    return PRICE_RE.sub(sub, text)


def render_tokens(body, ctx):
    def sub(m):
        name = m.group(1)
        if name not in COMPONENTS:
            raise SystemExit("Unknown component @{} in {}".format(name, ctx["file"]))
        args = {k: (q if q else u) for k, q, u in ARG_RE.findall(m.group(2))}
        return COMPONENTS[name](args, ctx)

    body = TOKEN_RE.sub(sub, render_prices(body))

    def var(m):
        cur = {"site": SITE, "today": TODAY}
        for part in m.group(1).split("."):
            cur = cur.get(part, "") if isinstance(cur, dict) else ""
        return e(cur)

    return VAR_RE.sub(var, body)


# ---------------------------------------------------------------- schema
def org_schema():
    org = {
        "@type": "Organization", "@id": ORG_ID, "name": SITE["name"], "alternateName": SITE["alternate_names"],
        "url": BASE + "/", "logo": {"@type": "ImageObject", "url": BASE + "/assets/img/moodily-logo-512.png", "width": 512, "height": 512},
        "description": "Bilingual (Hindi + English) platform for free AI learning, digital business services, research and knowledge products in India.",
        "disambiguatingDescription": SITE["disambiguation"], "email": SITE["email"], "areaServed": ["IN", "Worldwide"],
        "knowsLanguage": ["hi", "en"],
        "department": [{"@type": "Organization", "name": v} for v in DIVISIONS.values()],
    }
    if SITE["whatsapp"].get("number"):
        org["contactPoint"] = {"@type": "ContactPoint", "contactType": "sales", "telephone": "+" + SITE["whatsapp"]["number"],
                               "availableLanguage": ["Hindi", "English"], "email": SITE["email"]}
    if SITE["same_as"]:
        org["sameAs"] = SITE["same_as"]
    if SITE["legal"].get("business_name"):
        org["legalName"] = SITE["legal"]["business_name"]
    if SITE["legal"].get("address_city"):
        org["address"] = {"@type": "PostalAddress", "addressLocality": SITE["legal"]["address_city"], "addressCountry": "IN"}
    if SITE["founder"].get("name"):
        founder = {"@type": "Person", "name": SITE["founder"]["name"]}
        if SITE["founder"].get("linkedin"):
            founder["sameAs"] = [SITE["founder"]["linkedin"]]
        org["founder"] = founder
    return org


def page_schema(meta, route, ctx):
    url = BASE + route
    graph = []
    if route in ("/", "/about/"):
        graph.append(org_schema())
    if route == "/":
        graph.append({"@type": "WebSite", "@id": BASE + "/#website", "url": BASE + "/", "name": SITE["name"],
                      "alternateName": SITE["alternate_names"], "inLanguage": ["hi-IN", "en-IN"], "publisher": {"@id": ORG_ID}})
    crumbs = meta.get("breadcrumbs")
    if crumbs:
        items = [{"@type": "ListItem", "position": 1, "name": "Home", "item": BASE + "/"}]
        for i, (name, href) in enumerate(crumbs, start=2):
            items.append({"@type": "ListItem", "position": i, "name": name, "item": BASE + href})
        graph.append({"@type": "BreadcrumbList", "itemListElement": items})
    for s in ctx["services"]:
        node = {"@type": "Service", "@id": BASE + s["page"] + "#" + s["id"], "name": s["name"], "description": s["tagline"],
                "serviceType": s["category"], "provider": {"@id": ORG_ID}, "areaServed": {"@type": "Country", "name": "India"},
                "url": BASE + s["page"] + "#" + s["id"]}
        if s.get("price_from"):
            spec = {"@type": "PriceSpecification", "minPrice": s["price_from"], "priceCurrency": "INR"}
            if s["price_unit"] == "month":
                spec = {"@type": "UnitPriceSpecification", "minPrice": s["price_from"], "priceCurrency": "INR", "unitCode": "MON"}
            node["offers"] = {"@type": "Offer", "priceSpecification": spec, "url": BASE + "/contact/?service=" + s["id"]}
            if in_offer(s):
                node["offers"] = [node["offers"], {"@type": "Offer", "name": OFFER["name"], "price": offer_price(s), "priceCurrency": "INR",
                                                   "priceValidUntil": OFFER["ends_at"][:10], "availability": "https://schema.org/LimitedAvailability",
                                                   "url": BASE + "/offers/" + OFFER["id"] + "/"}]
        graph.append(node)
    for p in ctx["products"]:
        graph.append({"@type": "Product", "name": p["title"], "description": p["problem"], "brand": {"@type": "Brand", "name": "Moodily"},
                      "offers": {"@type": "Offer", "price": p["price"], "priceCurrency": "INR", "availability": "https://schema.org/InStock",
                                 "url": BASE + "/store/#" + p["slug"]}})
    if ctx["faqs"]:
        graph.append({"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in ctx["faqs"]]})
    if meta.get("article"):
        graph.append({"@type": "Article", "headline": meta["h1"] if meta.get("h1") else meta["title"], "description": meta["description"],
                      "inLanguage": meta.get("lang", "hi"), "datePublished": meta["article"]["published"],
                      "dateModified": meta["article"].get("modified", meta["article"]["published"]),
                      "author": {"@id": ORG_ID}, "publisher": {"@id": ORG_ID}, "mainEntityOfPage": url})
        if not any(n.get("@id") == ORG_ID for n in graph):
            graph.append({"@type": "Organization", "@id": ORG_ID, "name": SITE["name"], "url": BASE + "/"})
    if not graph:
        return ""
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":"))
    return '<script type="application/ld+json">{}</script>'.format(data.replace("</", "<\\/"))


# ---------------------------------------------------------------- layout
NAV = [
    ("/learn/", "Learn", "सीखें"), ("/digital-saathi/", "Digital Saathi", "सेवाएँ"), ("/case-studies/", "Samples", "काम"),
    ("/store/", "Store", "खरीदें"), ("/tools/", "Tools", "Tools"),
]
SERVICE_NAV = [
    ("/services/local-business/", "दुकान / Local Business"), ("/services/medical-store/", "Medical Store / Clinic"),
    ("/services/education/", "School / Coaching"), ("/services/professionals/", "Professionals & LinkedIn"),
    ("/services/creators/", "Creators"), ("/services/research/", "Research & Intelligence"),
    ("/services/knowledge-to-product/", "Knowledge-to-Product"), ("/services/ai-workflows/", "AI Workflows"),
    ("/services/", "सभी services और prices"),
]


def header(route, meta):
    def cur(href):
        return ' aria-current="page"' if route.startswith(href) and href != "/" else ""

    links = "".join('<li><a href="{0}"{1}>{2}</a></li>'.format(h, cur(h), e(en)) for h, en, hi in NAV)
    svc = "".join('<li><a href="{0}"{1}>{2}</a></li>'.format(h, cur(h) if h != "/services/" or route == "/services/" else "", e(t)) for h, t in SERVICE_NAV)
    lang_btn = ('<button class="lang-toggle" type="button" id="langToggle" data-track="language_switch" aria-label="Switch language Hindi/English">हिं / EN</button>'
                if meta.get("bilingual") else "")
    return """<a class="skip" href="#main">Skip to content</a>
<header class="site-header"><div class="container nav">
  <a class="logo" href="/" aria-label="Moodily home"><img src="/assets/img/moodily-mark.svg" alt="" width="28" height="28">Moodily<span class="dot" aria-hidden="true"></span></a>
  <nav aria-label="Primary" class="nav-main">
    <ul class="nav-desktop">{links}<li><a href="/services/"{services}>Services</a></li><li><a href="/contact/"{contact}>Contact</a></li></ul>
    <details class="menu"><summary aria-label="Menu"><span class="burger" aria-hidden="true"></span><span class="menu-label">Menu</span></summary>
      <div class="menu-panel">
        <ul class="nav-links">{links}<li><a href="/about/"{about}>About</a></li><li><a href="/contact/"{contact}>Contact</a></li></ul>
        <p class="menu-heading">Services</p><ul class="nav-sub">{svc}</ul>
      </div>
    </details>
  </nav>
  <div class="nav-actions">{lang}<button class="icon-btn" type="button" id="themeToggle" aria-label="Toggle dark/light theme">◐</button>
    <a class="btn btn-primary btn-sm nav-cta" href="/contact/?service=free-digital-audit" data-track="hero_cta_click" data-label="nav-audit">Free Audit</a></div>
</div></header>""".format(links=links, svc=svc, lang=lang_btn, about=cur("/about/"), contact=cur("/contact/"), services=cur("/services/"))


def footer():
    svc = "".join('<li><a href="{}">{}</a></li>'.format(h, e(t)) for h, t in SERVICE_NAV[:-1])
    return """<footer class="site-footer"><div class="container">
  <div class="footer-grid">
    <div><a class="logo" href="/">Moodily<span class="dot" aria-hidden="true"></span></a>
      <p class="muted small">Moodily.in — सीखें. डिजिटल बनें. बढ़ें.<br>Learn · Build · Digitize · Sell · Grow</p>
      <p class="small"><a href="mailto:{email}">{email}</a></p>
      {wa}
    </div>
    <div><h2 class="footer-h">Moodily</h2><ul>
      <li><a href="/learn/">Moodily Learn</a></li><li><a href="/digital-saathi/">Moodily Digital Saathi</a></li>
      <li><a href="/services/research/">Moodily Intelligence Studio</a></li><li><a href="/store/">Moodily Store</a></li>
      <li><a href="/case-studies/">Work samples</a></li><li><a href="/guides/">Hindi guides</a></li><li><a href="/tools/">Tools</a></li></ul></div>
    <div><h2 class="footer-h">Services</h2><ul>{svc}</ul></div>
    <div><h2 class="footer-h">Company</h2><ul>
      <li><a href="/about/">About</a></li><li><a href="/contact/">Contact</a></li><li><a href="/services/">Pricing</a></li>
      <li><a href="/privacy/">Privacy</a></li><li><a href="/terms/">Terms</a></li><li><a href="/refund/">Refund policy</a></li></ul></div>
  </div>
  <p class="footer-note small muted">Moodily curates learning paths using courses offered by recognised providers. Certificates, where applicable, are issued by the respective providers. Moodily has no official partnership with the providers listed unless stated. Some tool links may be affiliate links and are labelled.</p>
  <p class="footer-bottom small muted">© {year} Moodily · moodily.in</p>
</div></footer>
<a class="fab-wa" href="{wa_href}" target="_blank" rel="noopener" data-track="whatsapp_click" data-label="floating" aria-label="WhatsApp पर Moodily से बात करें">{icon}<span>WhatsApp</span></a>""".format(
        email=e(SITE["email"]), svc=svc, year=date.today().year, wa=wa_button("WhatsApp", track_label="footer", cls="btn btn-wa btn-sm"),
        wa_href=e(wa_href(wa_text())), icon=WA_ICON)


def gtm_head():
    gid = SITE.get("gtm_id")
    if not gid:
        return ""
    return ("<script>window.dataLayer=window.dataLayer||[];(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':new Date().getTime(),event:'gtm.js'}});"
            "var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;"
            "f.parentNode.insertBefore(j,f);}})(window,document,'script','dataLayer','{}');</script>").format(gid)


def gtm_body():
    gid = SITE.get("gtm_id")
    if not gid:
        return ""
    return '<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={}" height="0" width="0" style="display:none;visibility:hidden" title="GTM"></iframe></noscript>'.format(gid)


def breadcrumbs_html(meta):
    crumbs = meta.get("breadcrumbs")
    if not crumbs:
        return ""
    parts = ['<li><a href="/">Home</a></li>']
    for i, (name, href) in enumerate(crumbs):
        if i == len(crumbs) - 1:
            parts.append('<li><span aria-current="page">{}</span></li>'.format(e(name)))
        else:
            parts.append('<li><a href="{}">{}</a></li>'.format(href, e(name)))
    return '<nav class="container breadcrumbs" aria-label="Breadcrumb"><ol>{}</ol></nav>'.format("".join(parts))


def layout(meta, body, route, ctx):
    lang = meta.get("lang", "hi")
    canonical = BASE + route
    robots = '<meta name="robots" content="noindex, follow">' if meta.get("noindex") else '<meta name="robots" content="index, follow, max-image-preview:large">'
    og_img = BASE + meta.get("og_image", "/assets/img/og-moodily.png")
    view = meta.get("track_view")
    view_attr = ' data-view-event="{}" data-view-label="{}"'.format(e(view[0]), e(view[1])) if view else ""
    return """<!DOCTYPE html>
<html lang="{lang}" data-lang="{dlang}" data-theme="dark"{offer_attr}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
{robots}
<meta name="theme-color" content="#0A0B0F">
<meta property="og:site_name" content="Moodily">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="{ogtype}">
<meta property="og:locale" content="{locale}">
<meta property="og:image" content="{og_img}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/img/moodily-mark.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/assets/img/moodily-logo-512.png">
<script>(function(){{try{{var t=localStorage.getItem('moodily_theme');if(t)document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('moodily_lang');if(l&&document.documentElement.getAttribute('data-bilingual')!==null)document.documentElement.setAttribute('data-lang',l);}}catch(e){{}}var oe=document.documentElement.getAttribute('data-offer-ends');if(oe&&Date.now()>Date.parse(oe))document.documentElement.classList.add('offer-ended');document.documentElement.classList.add('js');}})();</script>
{gtm}
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap">
<link rel="stylesheet" href="/assets/css/site.css?v={ver}">
{schema}
<script src="/assets/js/site.js?v={ver}" defer></script>
</head>
<body{view}>
{gtm_body}
{header}
{banner}
{crumbs}
<main id="main">
{body}
</main>
{footer}
</body>
</html>
""".format(lang=lang, dlang="en" if lang == "en" else "hi", title=e(meta["title"]), desc=e(meta["description"]), canonical=canonical,
           robots=robots, ogtype="article" if meta.get("article") else "website", locale="en_IN" if lang == "en" else "hi_IN",
           og_img=og_img, gtm=gtm_head(), ver=ASSET_VERSION, schema=page_schema(meta, route, ctx), view=view_attr, gtm_body=gtm_body(),
           header=header(route, meta), crumbs=breadcrumbs_html(meta), body=body, footer=footer(), banner=offer_banner(route),
           offer_attr=' data-offer-ends="{}" data-offer-id="{}"'.format(OFFER["ends_at"], OFFER["id"]) if OFFER_STATE else "").replace(
        '<html lang="{}" data-lang'.format(lang), '<html lang="{}"{} data-lang'.format(lang, " data-bilingual" if meta.get("bilingual") else ""), 1)


# ---------------------------------------------------------- case pages
def case_page(c):
    shots = "".join('<figure><img src="{}" alt="{}" loading="lazy" decoding="async"><figcaption>{}</figcaption></figure>'.format(
        e(s["src"]), e(s["alt"]), e(s.get("caption", ""))) for s in c.get("screenshots", []))
    svc = SERVICES.get(c["service"])
    section = lambda h, v: '<section class="case-sec"><h2>{}</h2><p>{}</p></section>'.format(h, e(v)) if v else ""
    result = c.get("result") or "No measured result is claimed for this project yet."
    body = """<section class="page-hero"><div class="container narrow"><p class="eyebrow">{cat} · {div}</p><h1>{title}</h1><p class="lead">{work}</p></div></section>
<div class="container narrow case">{problem}{input}{method}{built}<section class="case-sec"><h2>Screenshots</h2><div class="shots">{shots}</div></section>{verify}
<section class="case-sec"><h2>Result</h2><p>{result}</p></section>
<section class="case-sec cta-box"><h2>ऐसा ही काम चाहिए?</h2><p><a class="btn btn-primary" href="/contact/?service={sid}">{sname} की enquiry करें</a> {wa}</p></section></div>""".format(
        cat=e(c["category"]), div=e(DIVISIONS[c["division"]]), title=e(c["title"]), work=e(c["work_type"]),
        problem=section("Problem", c.get("problem")), input=section("Input", c.get("input")), method=section("Method", c.get("method")),
        built=section("What we built", c.get("built")), shots=shots, verify=section("Quality verification", c.get("verification")),
        result=e(result), sid=svc["id"], sname=e(svc["name"]), wa=wa_button("WhatsApp", "interested client", svc["name"], track_label="case-" + c["slug"]))
    meta = {"title": "{} — Case study | Moodily".format(c["title"]), "description": "{}: problem, method, what Moodily built and how quality was verified.".format(c["title"]),
            "lang": "en", "breadcrumbs": [["Case studies", "/case-studies/"], [c["title"], "/case-studies/{}/".format(c["slug"])]],
            "track_view": ["case_study_open", c["slug"]]}
    return meta, body


# ----------------------------------------------------------------- build
META_RE = re.compile(r"\A\s*<!--meta\s*(\{.*?\})\s*-->", re.S)
ASSET_VERSION = hashlib.sha1(b"".join((ROOT / "assets" / p).read_bytes() for p in ("css/site.css", "js/site.js"))).hexdigest()[:10]


def route_for(path):
    rel = path.relative_to(SRC / "pages").with_suffix("")
    parts = list(rel.parts)
    if parts == ["404"]:
        return "/404.html", ROOT / "404.html"
    if parts[-1] == "index":
        parts = parts[:-1]
    route = "/" + "/".join(parts) + ("/" if parts else "")
    return route, ROOT.joinpath(*parts, "index.html")


def validate_services():
    for s in SVC_DATA["services"]:
        for key in ("for", "problem", "deliverables", "timeline", "not_included", "revisions", "support"):
            if not s.get(key):
                raise SystemExit("Service {} missing '{}'".format(s["id"], key))
        blob = json.dumps(s, ensure_ascii=False).lower()
        if "unlimited" in blob:
            raise SystemExit("Service {} mentions 'unlimited' — use defined revision scope".format(s["id"]))


def owner_todo():
    lines = ["# Owner TODO (auto-generated by build.py on {})".format(TODAY), "",
             "Values the site needs from the owner. Nothing here was invented — fill real data, then run `python3 build.py`.", ""]

    def walk(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.startswith("_todo"):
                    lines.append("- **{}**: {}".format(path or "site", v))
                else:
                    walk(v, (path + "." + k) if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, str) and v.startswith("_todo"):
                    lines.append("- **{}[{}]**: {}".format(path, i, v))
                else:
                    walk(v, "{}[{}]".format(path, i))

    lines.append("## src/site.json")
    walk(SITE, "")
    lines += ["", "## src/data/services.json"]
    walk(SVC_DATA, "")
    lines += ["", "## src/data/products.json"]
    walk(PRODUCT_DATA, "")
    lines += ["", "## src/data/tools.json"]
    walk(TOOLS, "")
    drafts = [c["title"] for c in CASES if c["status"] != "published"]
    lines += ["", "## Case studies still in draft ({} of {})".format(len(drafts), len(CASES)),
              "Add problem/input/method/built/screenshots/verification (+ result if measured) in src/data/case_studies.json, then set status to published."]
    lines += ["- " + d for d in drafts]
    lines += ["", "## Learn curriculum", "Add verified provider URLs for each course in src/data/learn.json (currently {} of {} have URLs).".format(
        sum(1 for s in LEARN["stages"] for c in s["courses"] if c.get("url")), sum(len(s["courses"]) for s in LEARN["stages"]))]
    (ROOT / "_project").mkdir(exist_ok=True)
    (ROOT / "_project" / "OWNER-TODO.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_checkout_catalog():
    """Server-side price list for the payments API (worker/ and scripts/dev_server.py). Browsers never choose the amount."""
    items = {}
    for sid in OFFER.get("services", []):
        s = SERVICES[sid]
        items[sid] = {"name": "{} — {}".format(OFFER["name"], s["name"]), "amount_paise": offer_price(s) * 100}
    data = {"currency": "INR", "items": items,
            "offer": {"id": OFFER.get("id"), "active": bool(OFFER_STATE), "ends_at": OFFER.get("ends_at"),
                      "slots_left": OFFER_STATE["left"] if OFFER_STATE else 0}}
    out = ROOT / "assets" / "data" / "checkout-prices.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_offer():
    if not OFFER:
        return
    if int(OFFER["slots_taken"]) > int(OFFER["slots_total"]):
        raise SystemExit("offer.slots_taken cannot exceed offer.slots_total")
    for sid in OFFER["services"]:
        if sid not in SERVICES or not SERVICES[sid].get("price_from"):
            raise SystemExit("offer service {} is missing or has no price".format(sid))
    if OFFER.get("active") and not OFFER_STATE:
        WARNINGS.append("offer '{}' is active in site.json but outside its window or sold out — not shown".format(OFFER["id"]))


def main():
    validate_services()
    validate_offer()
    old = set(json.loads(MANIFEST.read_text())) if MANIFEST.exists() else set()
    written, sitemap = [], []

    jobs = []
    for path in sorted((SRC / "pages").rglob("*.html")):
        raw = path.read_text(encoding="utf-8")
        m = META_RE.match(raw)
        if not m:
            raise SystemExit("Missing <!--meta {...} --> block in " + str(path))
        meta = json.loads(m.group(1))
        route, out = route_for(path)
        jobs.append((meta, raw[m.end():], route, out, str(path.relative_to(ROOT))))
    for c in CASES:
        if c["status"] == "published":
            meta, body = case_page(c)
            jobs.append((meta, body, "/case-studies/{}/".format(c["slug"]), ROOT / "case-studies" / c["slug"] / "index.html", "case:" + c["slug"]))

    titles = {}
    for meta, body, route, out, src in jobs:
        meta["title"], meta["description"] = render_prices(meta.get("title", "")), render_prices(meta.get("description", ""))
        for key in ("title", "description"):
            if not meta.get(key):
                raise SystemExit("{} missing meta '{}'".format(src, key))
        if meta["title"] in titles:
            raise SystemExit("Duplicate title '{}' in {} and {}".format(meta["title"], src, titles[meta["title"]]))
        titles[meta["title"]] = src
        ctx = {"services": [], "products": [], "faqs": [], "file": src}
        html_out = layout(meta, render_tokens(body, ctx), route, ctx)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_out, encoding="utf-8")
        written.append(str(out.relative_to(ROOT)))
        if not meta.get("noindex") and route != "/404.html":
            sitemap.append((route, meta.get("priority", "0.7")))

    for stale in sorted(old - set(written)):
        p = ROOT / stale
        if p.exists():
            p.unlink()
            try:
                p.parent.rmdir()
            except OSError:
                pass
            print("removed stale", stale)

    urls = "".join("<url><loc>{}{}</loc><lastmod>{}</lastmod><priority>{}</priority></url>".format(BASE, r, TODAY, p) for r, p in sitemap)
    (ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</urlset>\n'.format(urls), encoding="utf-8")
    (ROOT / "robots.txt").write_text("User-agent: *\nAllow: /\nDisallow: /contact/thanks/\nDisallow: /payment/\n\nSitemap: {}/sitemap.xml\n".format(BASE), encoding="utf-8")
    MANIFEST.write_text(json.dumps(sorted(written), indent=0))
    write_checkout_catalog()
    owner_todo()
    print("Built {} pages, {} in sitemap. Owner TODOs: _project/OWNER-TODO.md".format(len(written), len(sitemap)))
    for w in WARNINGS:
        print("WARNING:", w, file=sys.stderr)


if __name__ == "__main__":
    main()
