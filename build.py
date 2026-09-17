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
ROUTERS = load("data/routers.json")
ESTIMATOR = load("data/estimator.json")
REDIRECTS = {k: v for k, v in load("data/redirects.json").items() if not k.startswith("_")}
SAMPLES = {x["id"]: x for x in load("data/samples.json")["samples"]}
SCOPE_NOTE = SVC_DATA["scope_note"]
TPC_LABELS = SVC_DATA["third_party_cost_labels"]
FILTER_LABELS = SVC_DATA["filter_labels"]
CUSTOMER_TYPES = {c["id"]: c for c in ROUTERS["customer_types"]}
ACTIVE = [x for x in SVC_DATA["services"] if x.get("active", True)]
LOCAL_CATS = {"local-business", "google-business-profile", "whatsapp-business", "medical-store", "education-business", "websites"}
PRICE_MODES = SVC_DATA["price_modes"]
CLIENT_PROVIDES = SVC_DATA["client_provides_by_category"]
INTERNAL_KEYS = re.compile(r"(?i)internal|margin|hourly|cost_?price|estimated_?hours")
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
        "timeline": "समय", "not": "क्या शामिल नहीं है", "scope": "Revisions और support", "format": "Delivery format",
        "from": "शुरुआत", "from_suffix": "से", "month": "/महीना", "custom": "Scope के अनुसार quote",
        "enquire": "इस package की enquiry करें", "wa": "WhatsApp पर पूछें", "details": "पूरी जानकारी देखें",
        "sample": "जुड़ा हुआ work sample", "quote": "Quote लें", "sample_btn": "Sample देखें", "estimate": "Estimate करें",
        "audit": "मुफ़्त Digital Audit", "third": "Third-party खर्च (शामिल नहीं)", "home": "Home",
    },
    "en": {
        "for": "Who it is for", "problem": "Problem solved", "get": "Exact deliverables",
        "timeline": "Timeline", "not": "What is not included", "scope": "Revisions & support", "format": "Delivery format",
        "from": "Starts at", "from_suffix": "", "month": "/month", "custom": "Custom quote",
        "enquire": "Enquire about this package", "wa": "Ask on WhatsApp", "details": "See full details",
        "sample": "Related work sample", "quote": "Get a quote", "sample_btn": "See samples", "estimate": "Estimate",
        "audit": "Free digital audit", "third": "Third-party costs (not included)", "home": "Home",
    },
}

ROLE_LABELS = {
    "local-business": "Business owner", "google-business-profile": "Business owner", "whatsapp-business": "Business owner",
    "medical-store": "Medical store owner",
    "education": "School/Coaching", "education-content": "Teacher/Institute", "education-business": "Coaching/Library owner",
    "professionals": "Professional", "creators": "Creator", "research": "Founder/Researcher", "knowledge-to-product": "Expert/Author",
    "ai-workflows": "Business owner", "websites": "[role]", "design": "[role]", "b2b": "Manufacturer/B2B business",
    "presentations": "[role]", "invitations": "[role]", "business-documents": "Business owner", "social-media": "[role]",
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
TIER_LABEL = {"starter": "STARTER", "growth": "GROWTH", "premium": "PREMIUM"}
KIND_LABEL = {"self-initiated": "Self-initiated · Moodily का अपना project", "client": "Client project",
              "concept": "Concept / demo — client project नहीं"}


def split_ids(value):
    return [i.strip() for i in (value or "").split(",") if i.strip()]


def price_text(svc):
    lab = L[svc["lang"]]
    if svc.get("price_unit") == "free":
        return "FREE"
    if svc.get("price_from") is None:
        return lab["custom"]
    return "₹{}{}".format(inr(svc["price_from"]), lab["month"] if svc.get("price_unit") == "month" else "")


def price_label(svc):
    """Mode-aware short label: '₹499' (exact) · '₹1,999 से' (starts at) · 'Custom quote' · 'FREE'."""
    mode = svc.get("price_mode")
    if mode in ("free", "custom_quote") or svc.get("price_from") is None:
        return "FREE" if mode == "free" else "Custom quote"
    return price_text(svc) + ("" if mode == "exact" else " से")


def client_provides(svc):
    return svc.get("client_provides") or CLIENT_PROVIDES.get(svc["category"], "")


def scope_note_html():
    return '<p class="scope-note small muted">{}<br><span lang="en">{}</span></p>'.format(e(SCOPE_NOTE["hi"]), e(SCOPE_NOTE["en"]))


def price_html(svc):
    lab = L[svc["lang"]]
    if svc.get("price_unit") == "free":
        return '<p class="price"><strong>FREE</strong></p>'
    if svc.get("price_from") is None:
        return '<p class="price"><strong>{}</strong> <span class="price-mode">Custom quote</span></p>'.format(lab["custom"])
    unit = lab["month"] if svc["price_unit"] == "month" else ""
    offer = in_offer(svc)
    exact = svc.get("price_mode") == "exact"
    regular = '<p class="price{}">{} <strong>₹{}</strong>{} {}</p>'.format(
        " regular-only" if offer else "", '<span class="price-mode">Fixed price</span>' if exact else '<span class="price-from">{}</span>'.format(lab["from"]),
        inr(svc["price_from"]), '<span class="price-unit">{}</span>'.format(unit) if unit else "",
        "" if exact else '<span class="price-from">{}</span>'.format(lab["from_suffix"]))
    if not offer:
        return regular
    return ('<p class="price offer-only"><span class="badge badge-offer">{pct}% OFF · {name}</span> <strong>₹{op}</strong> '
            '<s class="price-was"><span class="sr-only">Regular starting price </span>₹{reg}</s></p>').format(
        pct=OFFER["discount_pct"], name=e(OFFER["name"]), op=inr(offer_price(svc)), reg=inr(svc["price_from"])) + regular


def card_attrs(svc):
    return ' data-pricing{}'.format(' data-retainer="{}"'.format(svc["id"]) if svc.get("price_unit") == "month" else "")


def service_card(svc, ctx):
    """Compact overview card linking to the service page."""
    lab = L[svc["lang"]]
    items = "".join("<li>{}</li>".format(e(d)) for d in svc["deliverables"][:3])
    return (
        '<article class="card svc-card{feat}"{attrs}>'
        '<p class="eyebrow">{div}</p><h3>{name}</h3><p class="muted">{tag}</p>{price}'
        '<ul class="ticks">{items}</ul><p class="small muted">⏱ {timeline}</p>'
        '<div class="card-actions">{offer_btn}<a class="btn btn-outline" href="{page}#{id}" data-track="service_card_click" data-label="{id}">{details}</a></div>'
        '</article>'
    ).format(feat=" featured" if svc.get("featured") else "", attrs=card_attrs(svc), div=e(DIVISIONS[svc["division"]]), name=e(svc["name"]),
             tag=e(svc["tagline"]), price=price_html(svc), items=items, timeline=e(svc["timeline"]), page=svc["page"], id=svc["id"],
             details=lab["details"], offer_btn=offer_pay_button(svc) if in_offer(svc) else "")


def service_wa(svc, label, cls, track):
    if svc.get("whatsapp_message"):
        return '<a class="{}" href="{}" target="_blank" rel="noopener" data-track="whatsapp_click" data-label="{}">{} {}</a>'.format(
            cls, e(wa_href(svc["whatsapp_message"])), e(track), WA_ICON, e(label))
    name = "{} offer — {} (₹{})".format(OFFER["name"], svc["name"], inr(offer_price(svc))) if in_offer(svc) else svc["name"]
    return wa_button(label, ROLE_LABELS.get(svc["category"], "[role]"), name, cls, track)


def service_ctas(svc):
    lab = L[svc["lang"]]
    offer = in_offer(svc)
    out = [offer_pay_button(svc) if offer else "",
           '<a class="btn btn-primary{}" href="/contact/?service={}" data-track="pricing_click" data-label="{}">{}</a>'.format(
               " regular-only" if offer else "", svc["id"], svc["id"],
               "मुफ़्त Audit माँगें" if svc.get("price_unit") == "free" else lab["quote"]),
           service_wa(svc, lab["wa"], "btn btn-wa", svc["id"]),
           '<a class="btn btn-outline btn-sm" href="#samples" data-track="portfolio_open" data-label="{}">{}</a>'.format(svc["id"], lab["sample_btn"])]
    if svc.get("price_unit") not in ESTIMATOR["excluded_price_units"]:
        out.append('<a class="btn btn-outline btn-sm" href="/services/estimator/?service={0}" data-track="pricing_click" data-label="estimate:{0}">{1}</a>'.format(
            svc["id"], lab["estimate"]))
    if svc["category"] in LOCAL_CATS and svc["id"] != "free-digital-audit":
        out.append('<a class="btn btn-outline btn-sm" href="/contact/?service=free-digital-audit" data-track="free_audit_click" data-label="{}">{}</a>'.format(
            svc["id"], lab["audit"]))
    return "".join(out)


def delivery_html(svc):
    parts = []
    if svc.get("formats"):
        parts.append(format_chips(svc["formats"]))
    if svc.get("editable_source"):
        parts.append('<span class="small">{}</span>'.format(e(svc["editable_source"])))
    return "".join(parts) or "—"


def third_party_html(svc):
    codes = svc.get("third_party_costs") or []
    if not codes:
        return ""
    return ('<details class="not-included third-party"><summary>{}</summary><ul class="crosses">{}</ul>'
            '<p class="small muted">Accounts और bills आपके नाम पर रहना बेहतर है।</p></details>').format(
        L[svc["lang"]]["third"], "".join("<li>{}</li>".format(e(TPC_LABELS[c])) for c in codes))


def service_detail(svc, ctx):
    lab = L[svc["lang"]]
    ctx["services"].append(svc)
    deliver = "".join("<li>{}</li>".format(e(d)) for d in svc["deliverables"])
    excluded = "".join("<li>{}</li>".format(e(d)) for d in svc["not_included"])
    case_html = ""
    case_ids = svc.get("case_study_ids") or ([svc["case_study"]] if svc.get("case_study") else [])
    cs = CASES_BY_SLUG.get(case_ids[0]) if case_ids else None
    if cs:
        href = "/case-studies/{}/".format(cs["slug"]) if cs["status"] == "published" else "/case-studies/#{}".format(cs["slug"])
        case_html = '<p class="case-link">{}: <a href="{}" data-track="portfolio_open" data-label="{}">{}</a></p>'.format(
            lab["sample"], href, cs["slug"], e(cs["title"]))
    compliance = '<p class="notice">{}</p>'.format(e(svc["compliance_note"])) if svc.get("compliance_note") else ""
    tier = TIER_LABEL.get(svc.get("tier") or "")
    return (
        '<article class="svc-detail{feat}" id="{id}" data-service-id="{id}"{attrs}>'
        '<header class="svc-head"><div><p class="eyebrow">{tier}{div}</p><h3>{name}</h3><p class="muted">{tag}</p></div>'
        '<div class="svc-price">{price}{scope}</div></header>'
        '<dl class="facts"><div><dt>{l_for}</dt><dd>{for_}</dd></div><div><dt>{l_problem}</dt><dd>{problem}</dd></div>'
        '<div><dt>{l_time}</dt><dd>{timeline}</dd></div><div><dt>{l_scope}</dt><dd>{rev} · {sup}</dd></div>'
        '<div class="facts-full"><dt>{l_format}</dt><dd>{delivery}</dd></div>{provides}</dl>'
        '<h4>{l_get}</h4><ul class="ticks">{deliver}</ul>'
        '<details class="not-included"><summary>{l_not}</summary><ul class="crosses">{excluded}</ul></details>'
        '{third}{compliance}{case}{offer_meta}<div class="card-actions">{ctas}</div></article>'
    ).format(
        feat=" featured" if svc.get("featured") else "", id=svc["id"], attrs=card_attrs(svc),
        tier="{} · ".format(tier) if tier else "", div=e(DIVISIONS[svc["division"]]), name=e(svc["name"]), tag=e(svc["tagline"]),
        price=price_html(svc), scope=scope_note_html(), l_for=lab["for"], for_=e(svc["for"]), l_problem=lab["problem"],
        problem=e(svc["problem"]), l_time=lab["timeline"], timeline=e(svc["timeline"]), l_scope=lab["scope"], rev=e(svc["revisions"]),
        sup=e(svc["support"]), l_format=lab["format"], delivery=delivery_html(svc), l_get=lab["get"], deliver=deliver,
        l_not=lab["not"], excluded=excluded, third=third_party_html(svc), compliance=compliance, case=case_html,
        provides='<div class="facts-full"><dt>आपको क्या देना होगा</dt><dd>{}</dd></div>'.format(e(client_provides(svc))) if client_provides(svc) else "",
        offer_meta=offer_meta_html() if in_offer(svc) else "", ctas=service_ctas(svc))


def c_services(args, ctx):
    ids = split_ids(args.get("ids"))
    if args.get("category"):
        ids = [x["id"] for x in ACTIVE if x["category"] == args["category"]]
    if args.get("featured"):
        ids = [x["id"] for x in ACTIVE if x.get("featured")]
    missing = [i for i in ids if i not in SERVICES]
    if missing:
        raise SystemExit("Unknown service ids: {} in {}".format(missing, ctx["file"]))
    ids = [i for i in ids if SERVICES[i].get("active", True)]
    if args.get("style") == "detail":
        return '<div class="svc-list">{}</div>'.format("".join(service_detail(SERVICES[i], ctx) for i in ids))
    return '<div class="grid grid-3">{}</div>{}'.format("".join(service_card(SERVICES[i], ctx) for i in ids), scope_note_html())


def c_price_table(args, ctx):
    rows = "".join('<tr><th scope="row"><a href="{}#{}">{}</a></th><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
        x["page"], x["id"], e(x["name"]), e(price_label(x)), e(PRICE_MODE_SHORT[x["price_mode"]]), e(x["timeline"])) for x in ACTIVE)
    return ('<div class="table-wrap"><table class="price-table"><caption>Fixed price = लिखे scope का तय दाम · "से" = starting price · Custom quote = scope देखकर (INR)</caption>'
            '<thead><tr><th scope="col">Service</th><th scope="col">Price</th><th scope="col">Price type</th><th scope="col">Timeline</th></tr></thead>'
            '<tbody>{}</tbody></table></div>{}').format(rows, scope_note_html())


def c_payg(args, ctx):
    rows = "".join(
        '<tr><th scope="row">{}</th><td>₹{}</td><td>{}</td><td><a class="btn btn-outline btn-sm" href="/contact/?service=linkedin-payg" data-track="pricing_click" data-label="payg-{}">Enquire</a></td></tr>'.format(
            e(p["name"]), inr(p["price"]), e(p["posts"]), e(p["price"])) for p in SVC_DATA["payg_linkedin"])
    return ('<div class="table-wrap"><table class="price-table"><caption>LinkedIn pay-as-you-go packs (one-time, starting prices)</caption>'
            '<thead><tr><th scope="col">Pack</th><th scope="col">Starts at</th><th scope="col">Posts</th><th scope="col"><span class="sr-only">Action</span></th></tr></thead>'
            '<tbody>{}</tbody></table></div>').format(rows)


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
        if KIND_LABEL.get(c.get("kind")):
            badge += ' <span class="badge badge-kind">{}</span>'.format(e(KIND_LABEL[c["kind"]]))
        svc_link = '<a class="small" href="{}#{}">Related service: {} →</a>'.format(svc["page"], svc["id"], e(svc["name"])) if svc else ""
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
            '<p><a class="btn btn-outline" href="{href}" target="_blank" rel="{rel}" data-track="affiliate_click" data-label="{slug}">{name} खोलें ↗</a></p>'
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
]
PRICE_MODE_SHORT = {"exact": "Fixed price", "starts_at": "Starting price", "custom_quote": "Custom quote", "free": "Free"}


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
        '<a class="btn btn-primary btn-lg" href="/contact/?service=free-digital-audit" data-track="free_audit_click" data-label="final-audit">मुफ़्त Digital Audit लें</a>'
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
    roles = ["Individual", "Student", "Teacher", "School", "Coaching Institute", "Creator", "Local Business", "Medical Store", "Clinic",
             "Professional", "Startup", "Agency", "Company", "Other"]
    budgets = ["Under ₹1,000", "₹1,000–₹3,000", "₹3,000–₹7,500", "₹7,500–₹15,000", "₹15,000–₹50,000", "₹50,000+", "Need recommendation"]
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


# ------------------------------------------------------ catalogue & intake
CATALOGUE = load("data/catalogue.json")
INTAKE = load("data/intake.json")
GROUPS = CATALOGUE["groups"]
FORMATS = CATALOGUE["formats"]


def _validate_catalogue_intake():
    cats, extras = INTAKE["categories"], INTAKE["extra_services"]
    for sid in SERVICES:
        if INTAKE["service_map"].get(sid) not in cats:
            raise SystemExit("src/data/intake.json: service_map needs a valid category for service '{}'".format(sid))
    for sid, x in extras.items():
        if x["category"] not in cats:
            raise SystemExit("intake.json extra service '{}' has unknown category".format(sid))
    for g in GROUPS:
        for key in ("price_service", "quote_service"):
            if g.get(key) and g[key] not in SERVICES and g[key] not in extras:
                raise SystemExit("catalogue group {}: {} '{}' is not a known service".format(g["id"], key, g[key]))
        for f in g["formats"]:
            if f not in FORMATS:
                raise SystemExit("catalogue group {}: unknown format '{}'".format(g["id"], f))
    url = INTAKE.get("form_url") or ""
    if url and not url.startswith("https://docs.google.com/forms/"):
        raise SystemExit("intake.json form_url must be a full https://docs.google.com/forms/... link (forms.gle short links drop prefill values)")
    for k, v in INTAKE.get("entry_ids", {}).items():
        if not k.startswith("_") and v and not re.match(r"^(entry\.)?\d+$", str(v)):
            raise SystemExit("intake.json entry_ids.{} must look like entry.1234567890".format(k))
    if not url:
        WARNINGS.append("intake.json form_url is empty — /contact/ shows the built-in fallback form until the Google Form link is added")


_validate_catalogue_intake()


def validate_commerce():
    tiers, units = {None, "starter", "growth", "premium"}, {"one-time", "month", "free", "custom"}
    required = ("slug", "customer_types", "filters", "keywords", "third_party_costs", "formats", "sample_ids", "case_study_ids",
                "revision_rounds", "active", "editable_source", "form_prefill_url", "whatsapp_message", "recommended_price")
    for x in SVC_DATA["services"]:
        for key in required:
            if key not in x:
                raise SystemExit("services.json: {} missing '{}'".format(x["id"], key))
        checks = [
            (x["price_unit"] in units, "price_unit"), (x.get("tier") in tiers, "tier"),
            (x["price_unit"] != "free" or x["price_from"] == 0, "free packages need price_from 0"),
            (x["price_unit"] != "custom" or x["price_from"] is None, "custom packages need price_from null"),
            (isinstance(x["revision_rounds"], int) and 0 <= x["revision_rounds"] <= 3, "revision_rounds must be 0–3 (never unlimited)"),
            (all(t in CUSTOMER_TYPES for t in x["customer_types"]), "customer_types"),
            (bool(x["filters"]) and all(f in FILTER_LABELS for f in x["filters"]), "filters"),
            (all(c in TPC_LABELS for c in x["third_party_costs"]), "third_party_costs"),
            (all(f in FORMATS for f in x["formats"]), "formats"),
            (all(i in SAMPLES for i in x["sample_ids"]), "sample_ids"),
            (all(c in CASES_BY_SLUG for c in x["case_study_ids"]), "case_study_ids"),
            (not x["form_prefill_url"] or x["form_prefill_url"].startswith("https://docs.google.com/forms/"), "form_prefill_url"),
        ]
        for ok, what in checks:
            if not ok:
                raise SystemExit("services.json: {} — invalid {}".format(x["id"], what))
    for smp in SAMPLES.values():
        if smp.get("kind") not in KIND_LABEL:
            raise SystemExit("samples.json: {} needs kind self-initiated|client|concept".format(smp["id"]))
        if not (ROOT / smp["image"].lstrip("/")).exists():
            raise SystemExit("samples.json: image missing for {}".format(smp["id"]))
        for sid in smp.get("services", []):
            if sid not in SERVICES:
                raise SystemExit("samples.json: {} references unknown service {}".format(smp["id"], sid))
    for p in ROUTERS["paths"]:
        for sid in p["price_services"]:
            if sid not in SERVICES:
                raise SystemExit("routers.json path {} has unknown price_service {}".format(p["id"], sid))
    for x in SVC_DATA["services"]:
        mode = x.get("price_mode")
        if mode not in PRICE_MODES:
            raise SystemExit("services.json: {} needs price_mode exact|starts_at|custom_quote|free".format(x["id"]))
        if (mode == "custom_quote") != (x["price_unit"] == "custom") or (mode == "free") != (x["price_unit"] == "free"):
            raise SystemExit("services.json: {} price_mode '{}' does not match price_unit '{}'".format(x["id"], mode, x["price_unit"]))
        leaked = [k for k in x if INTERNAL_KEYS.search(k)]
        if leaked:
            raise SystemExit("services.json: {} has internal field(s) {} — keep costs/hours/margins in private/pricing-internal.json".format(x["id"], leaked))


def intake_service(sid):
    if sid in SERVICES:
        return SERVICES[sid]["name"], INTAKE["service_map"][sid]
    x = INTAKE["extra_services"][sid]
    return x["name"], x["category"]


def chip_list(values, cls="chips"):
    return '<ul class="{}">{}</ul>'.format(cls, "".join("<li>{}</li>".format(e(v)) for v in values))


def format_chips(codes):
    return '<ul class="chips fmt-chips" aria-label="Delivery formats">{}</ul>'.format("".join('<li>{}</li>'.format(e(FORMATS[c])) for c in codes))


def c_catalogue_group(args, ctx):
    g = next((x for x in GROUPS if x["id"] == args["id"]), None)
    if not g:
        raise SystemExit("Unknown catalogue group {} in {}".format(args.get("id"), ctx["file"]))
    return ('<div class="grid grid-2 cat-detail"><div><h3>हम क्या बनाते हैं</h3>{items}</div>'
            '<div><h3>Delivery formats</h3>{fmts}<p class="small muted">{note}</p></div></div>').format(
        items=chip_list(g["items"]), fmts=format_chips(g["formats"]), note=e(CATALOGUE["formats_note"]))


def c_revision_policy(args, ctx):
    tiers = [("Basic", "1 revision round", "Digital invitation, visiting card, single creative/poster, design-only PPT"),
             ("Standard", "2 revision rounds", "Brochure, catalogue, logo, websites, content + design"),
             ("Premium", "3 revision rounds या लिखित support period", "Brand kit, lead/booking website, B2B kit, research + strategy")]
    cards = "".join('<div class="card"><p class="eyebrow">{}</p><h3>{}</h3><p class="muted small">{}</p></div>'.format(e(a), e(b), e(c)) for a, b, c in tiers)
    return ('<div class="grid grid-3">{}</div><p class="small muted">एक revision round = एक बार में भेजे गए सभी बदलाव। Revisions की संख्या तय है, असीमित नहीं। '
            'नई requirement, नया content या scope से बाहर के बदलाव का अलग quote होता है।</p>').format(cards)


def c_formats(args, ctx):
    return '{}<p class="small muted">{}</p>'.format(format_chips(list(FORMATS)), e(CATALOGUE["formats_note"]))


SENSITIVE_NOTICE = ('<p class="notice small"><strong>ध्यान दें:</strong> Prescription, Aadhaar, PAN, medical records, passwords, banking credentials या कोई और '
                    'sensitive personal जानकारी form में न भेजें। <span lang="en">Do not submit prescriptions, Aadhaar, PAN, medical records, passwords, '
                    'banking credentials or other sensitive personal information.</span></p>')


def c_intake(args, ctx):
    form_url = INTAKE.get("form_url") or ""
    services = {}
    for sid in list(SERVICES) + list(INTAKE["extra_services"]):
        name, cat = intake_service(sid)
        x = SERVICES.get(sid)
        price = ""
        if x:
            price = price_label(x)
        services[sid] = {"name": name, "category": INTAKE["categories"][cat]["label"], "price": price,
                         "offer_price": "₹" + inr(offer_price(x)) if x and in_offer(x) else "",
                         "prefill_url": (x.get("form_prefill_url") if x else "") or INTAKE.get("service_prefill_urls", {}).get(sid)
                         or INTAKE["categories"][cat].get("prefill_url") or "",
                         "page": "{}#{}".format(x["page"], sid) if x else ""}
    cfg = {"form_url": form_url, "entry_ids": {k: v for k, v in INTAKE.get("entry_ids", {}).items() if not k.startswith("_")},
           "offer": {"id": OFFER.get("id"), "name": OFFER.get("name"), "pct": OFFER.get("discount_pct"), "active": bool(OFFER_STATE)},
           "services": services}
    cfg_json = json.dumps(cfg, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    context = ('<div class="card intake-context" id="intakeContext" hidden><p class="eyebrow">आपने चुना</p>'
               '<h2 class="intake-service" id="intakeService"></h2><p class="muted small" id="intakeCategory"></p>'
               '<p class="price" id="intakePrice"></p><p class="notice small" id="intakeOffer" hidden></p><p class="notice small" id="intakeEstimate" hidden></p>'
               '<p class="small"><a id="intakeDetails" href="/services/">Package details</a> · <a href="/services/#finder">दूसरी service चुनें</a></p></div>')
    if form_url:
        main = ('<div class="card intake-cta featured"><p class="eyebrow">3–5 मिनट · कोई login नहीं</p><h2>Requirement form भरें</h2>'
                '<p>Google Form आपकी चुनी service के हिसाब से सिर्फ़ ज़रूरी सवाल पूछेगा। आपकी जानकारी सीधे Moodily तक पहुँचती है।</p>'
                '<a class="btn btn-primary btn-lg btn-block" id="gformBtn" href="{url}" target="_blank" rel="noopener" data-track="google_form_open" data-label="contact">Continue Requirement Form →</a>'
                '<p class="small muted">Form नई tab में खुलेगा। भेजने के बाद 1 working day में WhatsApp या email पर जवाब।</p>'
                '<details class="not-included"><summary>Form भरने से पहले तैयार रखें</summary><ul class="ticks small">'
                '<li>आपका मुख्य goal और deadline</li><li>Budget का अंदाज़ा (या "Need recommendation")</li>'
                '<li>Reference, existing website/social या Google Drive link</li><li>Text/content जो design में जाना है</li></ul></details>'
                '{sens}</div>').format(url=e(form_url), sens=SENSITIVE_NOTICE)
    else:
        main = '<div class="intake-legacy">{}{}</div>'.format(SENSITIVE_NOTICE, c_lead_form(args, ctx))
    wa = wa_button("WhatsApp पर requirement भेजें", cls="btn btn-wa btn-lg btn-block", track_label="intake").replace("<a class=", '<a id="intakeWa" class=', 1)
    return ('<div class="intake" id="intake" data-mode="{mode}"><script type="application/json" id="intakeConfig">{cfg}</script>'
            '<div class="intake-grid"><div class="intake-main">{context}{main}</div>'
            '<aside class="intake-side"><div class="card"><h2 class="side-h">WhatsApp पर तुरंत</h2><p class="small muted">Form नहीं भरना? अपनी ज़रूरत सीधे WhatsApp करें — voice note भी चलेगा।</p>{wa}'
            '<p class="small muted">या email: <a href="mailto:{email}">{email}</a></p></div>'
            '<div class="card"><h2 class="side-h">आगे क्या होगा</h2><ol class="steps-list small"><li>हम आपकी requirement पढ़ते हैं और ज़रूरत हो तो 1–2 सवाल पूछते हैं।</li>'
            '<li>लिखित scope, timeline, revisions, third-party खर्च और quote भेजते हैं।</li><li>आप हाँ कहें, तभी काम शुरू होता है।</li></ol></div></aside></div></div>').format(
        mode="google-form" if form_url else "fallback", cfg=cfg_json, context=context, main=main, wa=wa, email=e(SITE["email"]))


# ------------------------------------------------------ commerce components
def c_hero_ctas(args, ctx):
    svc = SERVICES[args["service"]]
    lab = L[svc["lang"]]
    parts = ['<a class="btn btn-primary btn-lg" href="/contact/?service={0}" data-track="pricing_click" data-label="hero:{0}">{1}</a>'.format(svc["id"], lab["quote"]),
             service_wa(svc, "WhatsApp Requirement" if svc["lang"] == "hi" else "WhatsApp us", "btn btn-wa btn-lg", "hero-" + svc["id"]),
             '<a class="btn btn-outline btn-lg" href="#samples" data-track="portfolio_open" data-label="hero:{}">{}</a>'.format(svc["id"], lab["sample_btn"])]
    if svc.get("price_unit") not in ESTIMATOR["excluded_price_units"]:
        parts.append('<a class="btn btn-outline btn-lg" href="/services/estimator/?service={0}" data-track="pricing_click" data-label="hero-estimate:{0}">{1}</a>'.format(
            svc["id"], lab["estimate"]))
    audit = ""
    if args.get("audit") == "yes":
        audit = '<p class="small"><a href="/contact/?service=free-digital-audit" data-track="free_audit_click" data-label="hero:{}">पहले {} लें →</a></p>'.format(
            svc["id"], lab["audit"])
    return '<div class="btn-row">{}</div>{}'.format("".join(parts), audit)


def c_samples(args, ctx):
    wanted = split_ids(args.get("services"))
    ids = split_ids(args.get("ids"))
    for sid in wanted:
        if sid not in SERVICES:
            raise SystemExit("@samples: unknown service {} in {}".format(sid, ctx["file"]))
        ids += SERVICES[sid].get("sample_ids", [])
    ids += [k for k, v in SAMPLES.items() if set(v.get("services", [])) & set(wanted)]
    items, seen = [], set()
    for i in ids:
        if i not in SAMPLES:
            raise SystemExit("@samples: unknown sample {} in {}".format(i, ctx["file"]))
        if i not in seen and SAMPLES[i].get("status") == "published":
            seen.add(i)
            items.append(SAMPLES[i])
    cases = []
    for sid in wanted:
        for c in SERVICES[sid].get("case_study_ids", []):
            if c not in cases:
                cases.append(c)
    cards = []
    for smp in items:
        fmts = ", ".join(FORMATS[f] for f in smp.get("formats", []))
        cards.append('<figure class="card sample-card" data-sample="{id}"><div class="mock mock-{frame}"><div class="mock-screen">'
                     '<img src="{img}" alt="{alt}" width="{w}" height="{h}" loading="lazy" decoding="async"></div></div>'
                     '<figcaption><span class="badge badge-kind">{kind}</span><strong>{title}</strong><span class="small muted">{desc}</span>{fmts}</figcaption></figure>'.format(
                         id=smp["id"], frame=e(smp["frame"]), img=e(smp["image"]), alt=e(smp["alt"]), w=smp["width"], h=smp["height"],
                         kind=e(KIND_LABEL[smp["kind"]]), title=e(smp["title"]), desc=e(smp["description"]),
                         fmts='<span class="small">Format: {}</span>'.format(e(fmts)) if fmts else ""))
    for slug in cases:
        c = CASES_BY_SLUG[slug]
        cards.append('<article class="card sample-card sample-case"><span class="badge">Real project · detailed write-up in progress</span><h3>{t}</h3>'
                     '<p class="small muted">{w}</p><a class="small" href="/case-studies/#{s}" data-track="portfolio_open" data-label="{s}">Portfolio में देखें →</a></article>'.format(
                         t=e(c["title"]), w=e(c["work_type"]), s=slug))
    if cards:
        body = '<div class="grid grid-3 samples-grid">{}</div>'.format("".join(cards))
    else:
        body = '<p class="notice small">इस service के published samples जल्द जोड़े जाएँगे। हम नकली या किसी और का काम sample नहीं बनाते।</p>'
    note = ('<p class="small muted sample-note">हर sample पर साफ़ लिखा है कि वह client project है, Moodily का self-initiated project या concept। '
            'और examples चाहिए? {}</p>').format(wa_button("WhatsApp पर samples माँगें", track_label="samples-more", cls="btn btn-wa btn-sm"))
    return '<div id="samples" data-sample-section>{}{}</div>'.format(body, note)


def c_before_after(args, ctx):
    c = ROUTERS["before_after"][args["id"]]

    def col(side, cls):
        return '<div class="ba-col {}"><p class="ba-h">{}</p><ul>{}</ul></div>'.format(cls, e(side["heading"]), "".join("<li>{}</li>".format(e(i)) for i in side["items"]))
    return ('<figure class="before-after"><figcaption><span class="badge">Concept illustration — client project नहीं</span> <strong>{}</strong></figcaption>'
            '<div class="ba-grid">{}<div class="ba-arrow" aria-hidden="true">→</div>{}</div></figure>').format(
        e(c["title"]), col(c["before"], "ba-before"), col(c["after"], "ba-after"))


def c_tiers(args, ctx):
    ids, rec = split_ids(args["ids"]), args.get("recommended")
    fallback = ["STARTER", "GROWTH", "PREMIUM"]
    cards = []
    for i, sid in enumerate(ids):
        if sid not in SERVICES:
            raise SystemExit("@tiers: unknown service {} in {}".format(sid, ctx["file"]))
        x = SERVICES[sid]
        lab = L[x["lang"]]
        label = "MONTHLY" if x.get("price_unit") == "month" else TIER_LABEL.get(x.get("tier") or "", fallback[min(i, 2)])
        is_rec = sid == rec
        cards.append(
            '<article class="card tier-card{rc}"{attrs}>{badge}<p class="eyebrow">{label}</p><h3>{name}</h3>{price}<p class="small muted">{tag}</p>'
            '<ul class="ticks small">{items}</ul><p class="small"><strong>⏱</strong> {timeline}<br><strong>↻</strong> {rev}</p>'
            '<div class="card-actions"><a class="btn btn-primary btn-sm" href="/contact/?service={id}" data-track="pricing_click" data-label="tier:{id}">{quote}</a>'
            '<a class="btn btn-outline btn-sm" href="{page}#{id}" data-track="service_card_click" data-label="tier-details:{id}">{details}</a></div></article>'.format(
                rc=" recommended" if is_rec else "", attrs=card_attrs(x), badge='<span class="badge badge-rec">RECOMMENDED</span>' if is_rec else "",
                label=label, name=e(x["name"]), price=price_html(x), tag=e(x["tagline"]),
                items="".join("<li>{}</li>".format(e(d)) for d in x["deliverables"][:6]), timeline=e(x["timeline"]), rev=e(x["revisions"]),
                id=sid, quote=lab["quote"], page=x["page"], details=lab["details"]))
    return '<div class="grid grid-3 tiers">{}</div>{}'.format("".join(cards), scope_note_html())


def c_third_party_note(args, ctx):
    return ('<div class="card third-party-card"><h3>Third-party खर्च अलग हैं</h3>'
            '<p class="small">नीचे दिए खर्च किसी package में अपने-आप शामिल नहीं होते — जब तक उस package में साफ़ न लिखा हो:</p>{}'
            '<p class="small muted">हम सलाह देते हैं कि domain, hosting, Google, WhatsApp, ads और software accounts सीधे आपके नाम पर हों — Moodily सिर्फ़ manager/admin access लेता है।</p></div>').format(
        chip_list(TPC_LABELS.values()))


def c_how_it_works(args, ctx):
    steps = "".join('<li><span class="step-num">{}</span><div><h3>{}</h3><p>{}</p></div></li>'.format(i + 1, e(t), e(d))
                    for i, (t, d) in enumerate(ROUTERS["how_it_works"]))
    return '<ol class="quality how-steps">{}</ol>'.format(steps)


def c_paths(args, ctx):
    """Homepage four-path router. Each chip links to a page; the path shows its lowest published price."""
    cards = []
    for p in ROUTERS["paths"]:
        priced = [SERVICES[i] for i in p["price_services"] if SERVICES[i].get("price_from")]
        low = min(priced, key=lambda x: x["price_from"]) if priced else None
        chips = "".join('<li><a href="{0}" data-track="service_card_click" data-label="path:{1}:{2}">{2}</a></li>'.format(e(h), p["id"], e(t)) for t, h in p["items"])
        cards.append(
            '<article class="path-card" id="path-{id}"><p class="path-num" aria-hidden="true">{emoji}</p><h3><a href="{href}" data-track="service_card_click" data-label="path:{id}">{title}</a></h3>'
            '<p class="muted small">{sub}</p><ul class="path-chips">{chips}</ul><p class="path-price">{price}</p>'
            '<a class="btn btn-outline btn-sm" href="{href}" data-track="service_card_click" data-label="path-go:{id}">{cta} →</a></article>'.format(
                id=p["id"], emoji=p["emoji"], href=e(p["href"]), title=e(p["title"]), sub=e(p["sub"]), chips=chips, cta=e(p["cta"]),
                price=e("{} से शुरू".format(price_text(low))) if low else "Scope देखकर quote"))
    unsure = ('<div class="path-unsure card"><div><h3>समझ नहीं आ रहा क्या चाहिए?</h3><p class="muted small">{}</p></div>'
              '<a class="btn btn-primary" href="/contact/?service=free-digital-audit" data-track="free_audit_click" data-label="paths-unsure">FREE Digital Audit लें</a></div>').format(
        e(SITE["free_audit"]["promise_hi"]))
    return '<div class="paths-grid">{}</div>{}'.format("".join(cards), unsure)


def c_answer_box(args, ctx):
    """Answers the buyer's first questions in one card: what, who, what you get, price, time, revisions, inputs, extras + actions."""
    svc = SERVICES[args["service"]]
    if svc not in ctx["services"]:
        ctx["services"].append(svc)
    extras = [TPC_LABELS[c] for c in svc.get("third_party_costs", [])] + svc["not_included"][:2]
    rows = [("यह क्या है?", e(svc["tagline"])), ("किसके लिए?", e(svc["for"])),
            ("क्या मिलेगा?", "<ul class=\"ticks small\">{}</ul>".format("".join("<li>{}</li>".format(e(d)) for d in svc["deliverables"][:4]))),
            ("Price", price_html(svc) + '<span class="small muted">{}</span>'.format(e(PRICE_MODES[svc["price_mode"]]))),
            ("कितना समय?", e(svc["timeline"])), ("कितने revisions?", e(svc["revisions"])),
            ("आपको क्या देना होगा?", e(client_provides(svc))), ("क्या extra है?", e(" · ".join(extras)) or "—")]
    dl = "".join('<div><dt>{}</dt><dd>{}</dd></div>'.format(k, v) for k, v in rows if v)
    lab = L[svc["lang"]]
    actions = ('<a class="btn btn-primary" href="/contact/?service={id}" data-track="quote_start" data-label="answer:{id}">{quote}</a>'
               '<a class="btn btn-outline" href="#samples" data-track="portfolio_open" data-label="answer:{id}">Sample देखें</a>{wa}').format(
        id=svc["id"], quote="मुफ़्त Audit माँगें" if svc["price_mode"] == "free" else "Get Quote · Quote लें", wa=service_wa(svc, "WhatsApp", "btn btn-wa", "answer-" + svc["id"]))
    return ('<div class="answer-box card"{attrs} data-service-id="{id}"><p class="eyebrow">एक नज़र में · {name}</p><dl class="answer-dl">{dl}</dl>'
            '<div class="card-actions">{actions}</div>{scope}</div>').format(attrs=card_attrs(svc), id=svc["id"], name=e(svc["name"]), dl=dl,
                                                                         actions=actions, scope=scope_note_html())


def c_price_snapshot(args, ctx):
    ids = split_ids(args["ids"])
    rows = "".join('<li><a href="{}#{}" data-track="service_card_click" data-label="snapshot:{}"><span>{}</span><strong>{}</strong></a></li>'.format(
        SERVICES[i]["page"], i, i, e(SERVICES[i]["name"]), e(price_label(SERVICES[i]))) for i in ids)
    return '<ul class="price-snapshot" data-pricing>{}</ul>{}'.format(rows, scope_note_html())


def c_price_guide(args, ctx):
    """Full live price list grouped by directory category (used by the price-guide insight)."""
    out = []
    for key, label in FILTER_LABELS.items():
        items = [x for x in ACTIVE if x["filters"][0] == key]
        if not items:
            continue
        rows = "".join('<tr><th scope="row"><a href="{}#{}">{}</a></th><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            x["page"], x["id"], e(x["name"]), e(price_label(x)), e(PRICE_MODE_SHORT[x["price_mode"]]), e(x["timeline"])) for x in items)
        out.append('<h3>{}</h3><div class="table-wrap"><table class="price-table" data-pricing><thead><tr><th scope="col">Service</th><th scope="col">Price</th>'
                   '<th scope="col">Price type</th><th scope="col">Timeline</th></tr></thead><tbody>{}</tbody></table></div>'.format(e(label), rows))
    return "".join(out) + '<p class="small muted">Last price review: {} · Source: Moodily service registry (src/data/services.json)</p>{}'.format(
        e(max(x.get("last_price_review", "") for x in ACTIVE)), scope_note_html())


def c_customer_router(args, ctx):
    visible = int(ROUTERS.get("mobile_visible_types", 4))
    types = ROUTERS["customer_types"]
    cards = "".join(
        '<a class="router-card{more}" href="{href}" data-track="service_card_click" data-label="type:{id}"><span class="router-emoji" aria-hidden="true">{emoji}</span>'
        '<span class="router-title">{title}</span><span class="router-sub">{sub}</span><span class="router-go" aria-hidden="true">→</span></a>'.format(
            more=" more-type" if i >= visible else "", href=e(c["href"]), id=c["id"], emoji=c["emoji"], title=e(c["title"]), sub=e(c["sub"]))
        for i, c in enumerate(types))
    closed = "सभी customer types देखें ({} और)".format(len(types) - visible)
    return ('<div class="router types" data-types>{}</div>'
            '<button type="button" class="btn btn-outline types-toggle" data-types-toggle data-label-closed="{}" aria-expanded="false">{}</button>').format(
        cards, e(closed), e(closed))


def c_finder(args, ctx):
    chips = '<button type="button" class="chip-btn" data-filter="" aria-pressed="true">सभी</button>' + "".join(
        '<button type="button" class="chip-btn" data-filter="{}" aria-pressed="false">{}</button>'.format(k, e(v)) for k, v in FILTER_LABELS.items())
    cards = []
    for x in ACTIVE:
        search = " ".join([x["name"], x["tagline"], x["category"], " ".join(x["keywords"]), " ".join(x["deliverables"])]).lower()
        cards.append('<article class="card finder-card" data-tags="{tags}" data-types="{types}" data-search="{search}"{attrs}>'
                     '<p class="eyebrow">{filters}</p><h3><a href="{page}#{id}" data-track="service_card_click" data-label="finder:{id}">{name}</a></h3>'
                     '<p class="muted small">{tag}</p>{price}<p class="small muted">⏱ {timeline}</p>'
                     '<div class="card-actions"><a class="btn btn-primary btn-sm" href="/contact/?service={id}" data-track="pricing_click" data-label="finder:{id}">Quote लें</a></div></article>'.format(
                         tags=" ".join(x["filters"]), types=" ".join(x["customer_types"]), search=e(search), attrs=card_attrs(x),
                         filters=e(" · ".join(FILTER_LABELS[f] for f in x["filters"])), page=x["page"], id=x["id"], name=e(x["name"]),
                         tag=e(x["tagline"]), price=price_html(x), timeline=e(x["timeline"])))
    cards.append('<article class="card finder-card cat-custom" data-always><p class="eyebrow">Custom</p><h3>Something else?</h3>'
                 '<p class="muted small">Need something not listed? Send your requirement — हम साफ़ बताएँगे कि कर सकते हैं या नहीं।</p>'
                 '<div class="card-actions"><a class="btn btn-primary btn-sm" href="/contact/?service=custom-digital-work" data-track="service_card_click" data-label="finder:custom">Requirement भेजें</a></div></article>')
    types = "".join('<option value="{}">{}</option>'.format(c["id"], e(c["title"])) for c in ROUTERS["customer_types"])
    return ('<div class="finder" data-finder><div class="finder-bar"><label class="sr-only" for="finderSearch">Service खोजें</label>'
            '<input id="finderSearch" class="finder-search" type="search" placeholder="खोजें: invoice, PPT, invitation, website, brochure, PDF, thumbnail…" autocomplete="off">'
            '<label class="sr-only" for="finderType">Customer type</label><select id="finderType" class="finder-type"><option value="">सभी customer types</option>{types}</select></div>'
            '<div class="chip-row" role="group" aria-label="Category filter">{chips}</div><p class="small muted" data-finder-count aria-live="polite"></p></div>'
            '<div class="grid grid-3 finder-grid">{cards}</div>'
            '<p class="notice small" data-finder-empty hidden>कोई package नहीं मिला — <a href="/contact/?service=custom-digital-work">अपनी requirement भेजें</a>।</p>{scope}').format(
        types=types, chips=chips, cards="".join(cards), scope=scope_note_html())


def c_estimator(args, ctx):
    rules = {k: v for k, v in ESTIMATOR.items() if not k.startswith("_")}
    svcs = {x["id"]: {"name": x["name"], "price": x["price_from"], "unit": x["price_unit"], "page": "{}#{}".format(x["page"], x["id"]),
                      "integrations": bool(set(x["filters"]) & {"website", "ai"})}
            for x in ACTIVE if x["price_unit"] not in rules["excluded_price_units"]}
    opts = "".join('<option value="{}">{} — {}</option>'.format(sid, e(v["name"]), e(price_label(SERVICES[sid]))) for sid, v in svcs.items())

    def radios(group, legend, default):
        items = "".join(
            '<div class="radio"><input type="radio" id="est-{g}-{k}" name="{g}" value="{k}"{chk}><label for="est-{g}-{k}">{lab}{hint}</label></div>'.format(
                g=group, k=k, chk=" checked" if k == default else "", lab=e(v["label"]),
                hint=' <span class="small muted">— {}</span>'.format(e(v["hint"])) if v.get("hint") else "") for k, v in rules[group].items())
        return '<fieldset class="field-full est-group" data-group="{}"><legend>{}</legend><div class="radio-row">{}</div></fieldset>'.format(group, legend, items)

    extras = "".join('<div class="radio"><input type="checkbox" id="est-x-{0}" name="extras" value="{0}"><label for="est-x-{0}">{1}</label></div>'.format(k, e(v["label"]))
                     for k, v in rules["extras"].items())
    cfg = json.dumps({"rules": rules, "services": svcs}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    wa = wa_button("WhatsApp पर भेजें", cls="btn btn-wa", track_label="estimator").replace("<a class=", '<a id="estWa" class=', 1)
    return ('<form class="estimator card" id="estimator" novalidate><script type="application/json" id="estimatorConfig">{cfg}</script>'
            '<div class="form-grid"><div class="field field-full"><label for="est-service">Service *</label><select id="est-service" name="service">'
            '<option value="">Service चुनें</option>{opts}</select></div>{groups}'
            '<fieldset class="field-full est-group"><legend>Extras</legend><div class="radio-row">{extras}</div></fieldset></div>'
            '<p class="small muted" id="estHint">Service चुनें — indicative range तुरंत दिखेगी।</p>'
            '<div class="est-result" id="estResult" aria-live="polite" hidden><p class="eyebrow">Indicative estimate</p><p class="est-range" id="estRange"></p>'
            '<p class="small muted" id="estBase"></p><p class="notice small"><strong>Final quote after reviewing requirement.</strong> '
            'यह केवल अनुमान है; इस estimate के आधार पर payment नहीं लिया जाता।</p>'
            '<div class="card-actions"><a class="btn btn-primary" id="estQuote" href="/contact/" data-track="pricing_click" data-label="estimator-quote">इस estimate के साथ Quote लें</a>'
            '{wa}<a class="btn btn-outline" id="estDetails" href="/services/">Package details</a></div></div></form>').format(
        cfg=cfg, opts=opts, groups="".join(radios(g["key"], g["legend"], g["default"]) for g in rules["groups"]), extras=extras, wa=wa)


# ------------------------------------------------- reference-framework components
HOME_PACKAGES = ["digital-business-starter", "business-growth-launch", "digital-saathi-monthly"]


def c_packages(args, ctx):
    """Three flagship commercial packages, reference-style: outcome, price, what's inside, one CTA."""
    ids = split_ids(args["ids"]) if args.get("ids") else HOME_PACKAGES
    lead = args.get("lead", ids[0])
    out = []
    for sid in ids:
        svc = SERVICES[sid]
        if svc not in ctx["services"]:
            ctx["services"].append(svc)
        items = "".join("<li>{}</li>".format(e(d)) for d in svc["deliverables"][:5])
        out.append(
            '<article class="pkg{lead}" id="pkg-{id}"{attrs} data-service-id="{id}">'
            '<h3>{name}</h3><p class="pkg-for">{tagline}</p>{price}'
            '<p class="small muted">{mode}</p><ul class="ticks">{items}</ul>'
            '<p class="pkg-meta">{timeline} · {revisions}</p>'
            '<div class="card-actions"><a class="btn btn-primary" href="/contact/?service={id}" data-track="quote_start" data-label="pkg:{id}">Requirement बताएं</a>'
            '<a class="btn btn-outline" href="{page}#{id}" data-track="service_card_click" data-label="pkg-detail:{id}">पूरा scope →</a></div></article>'.format(
                lead=" pkg-lead" if sid == lead else "", id=sid, attrs=card_attrs(svc), name=e(svc["name"]), tagline=e(svc["tagline"]),
                price=price_html(svc), mode=e(PRICE_MODES[svc["price_mode"]]), items=items,
                timeline=e(svc["timeline"]), revisions=e(svc["revisions"]), page=svc["page"]))
    return '<div class="pkg-grid">{}</div>{}'.format("".join(out), scope_note_html())


def c_categories(args, ctx):
    """Directory teaser: one tile per service-filter category, each with a live count and lowest price."""
    tiles = []
    for key, label in FILTER_LABELS.items():
        items = [x for x in ACTIVE if key in x["filters"]]
        if not items:
            continue
        priced = [x for x in items if x.get("price_from")]
        low = min(priced, key=lambda x: x["price_from"]) if priced else None
        sub = "{} services · {}".format(len(items), "{} से".format(price_text(low)) if low else "custom quote")
        tiles.append('<a class="cat-tile" href="/services/#finder" data-track="service_card_click" data-label="cat:{k}"><strong>{l}</strong><span>{s}</span></a>'.format(
            k=key, l=e(label), s=e(sub)))
    return '<div class="cats-grid">{}</div>'.format("".join(tiles))


def c_scorecard(args, ctx):
    """Hero-side Digital Audit scorecard. Illustrative sample, labelled as such — never a real client."""
    rows = [("Google Business Profile आपके नाम पर", "done", "Done"),
            ("समय और फ़ोन नंबर सही", "part", "Partly"),
            ("अंदर, बाहर और team की photos", "fix", "Fix"),
            ("Services और rate list", "fix", "Fix"),
            ("हर customer से review माँगा जाता है", "fix", "Fix"),
            ("WhatsApp Business + catalogue", "part", "Partly"),
            ("Reviews के जवाब", "done", "Done")]
    li = "".join('<li><span>{}</span><span class="score-tag score-{}">{}</span></li>'.format(e(t), k, lab) for t, k, lab in rows)
    top = ["Counter पर QR लगाकर हर customer से review माँगें",
           "Services + rate list डालें और 10 असली photos जोड़ें",
           "WhatsApp catalogue और quick replies सेट करें"]
    return ('<aside class="scorecard" aria-label="Digital Audit scorecard — sample">'
            '<div class="scorecard-head"><h2>Digital Audit scorecard</h2><p class="scorecard-note">Sample — असली business नहीं</p></div>'
            '<p class="scorecard-sub">एक coaching centre: Google Maps और WhatsApp</p>'
            '<p><span class="score-num">43</span><span class="score-den"> / 100</span></p>'
            '<ul class="score-list">{li}</ul>'
            '<div class="score-top"><p>सबसे ज़रूरी तीन सुधार</p><ol>{top}</ol></div></aside>').format(
        li=li, top="".join("<li>{}</li>".format(e(t)) for t in top))


def c_promises(args, ctx):
    """Trust pair: what Moodily does every time, and what it will never do."""
    will = ["हर payment से पहले लिखित scope", "Google, domain, WhatsApp — सब accounts आपके नाम पर",
            "Delivery से पहले एक इंसान by-hand जाँचता है", "Handover checklist जो आप दोबारा इस्तेमाल कर सकें",
            "तय revisions — पहले से लिखे हुए", "Third-party खर्च अलग से, पहले बताए हुए"]
    wont = ["Reviews ख़रीदना, लिखना या incentive देना", "Ranking, followers या sales की guarantee",
            "आपके accounts या passwords अपने पास रखना", "बिना पूछे लोगों को message करना",
            "Textbook copy करना या sources गढ़ना", "बिना आपकी लिखित अनुमति के result या testimonial छापना"]
    return ('<div class="promise-grid"><div class="card promise-card will"><h3>हर project में, हर बार</h3><ul class="ticks">{w}</ul></div>'
            '<div class="card promise-card wont"><h3>ये हम कभी नहीं करते</h3><ul class="crosses">{n}</ul></div></div>').format(
        w="".join("<li>{}</li>".format(e(x)) for x in will), n="".join("<li>{}</li>".format(e(x)) for x in wont))


COMPONENTS = {
    "services": c_services, "price-table": c_price_table, "payg": c_payg,
    "cases": c_cases, "products": c_products, "product-categories": c_product_categories,
    "products-by-category": c_products_by_category, "tools": c_tools, "faq": c_faq,
    "quality-workflow": c_quality_workflow, "final-cta": c_final_cta, "wa": c_wa,
    "learn-curriculum": c_learn_curriculum, "lead-form": c_lead_form, "founder": c_founder,
    "offer-details": c_offer_details, "offer-terms": c_offer_terms,
    "catalogue-group": c_catalogue_group, "revision-policy": c_revision_policy, "formats": c_formats, "intake": c_intake,
    "hero-ctas": c_hero_ctas, "samples": c_samples, "before-after": c_before_after, "tiers": c_tiers,
    "third-party-note": c_third_party_note, "how-it-works": c_how_it_works, "paths": c_paths, "answer-box": c_answer_box,
    "price-snapshot": c_price_snapshot, "price-guide": c_price_guide,
    "packages": c_packages, "categories": c_categories, "scorecard": c_scorecard, "promises": c_promises,
    "customer-router": c_customer_router, "finder": c_finder, "estimator": c_estimator,
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
    seen_ids = set()
    for s in ctx["services"]:
        if s["id"] in seen_ids:
            continue
        seen_ids.add(s["id"])
        node = {"@type": "Service", "@id": BASE + s["page"] + "#" + s["id"], "name": s["name"], "description": s["tagline"],
                "serviceType": s["category"], "provider": {"@id": ORG_ID}, "areaServed": {"@type": "Country", "name": "India"},
                "url": BASE + s["page"] + "#" + s["id"]}
        if s.get("price_from"):  # custom-quote services publish no price; exact vs starting price follow the visible label
            key = "price" if s["price_mode"] == "exact" else "minPrice"
            spec = {"@type": "PriceSpecification", key: s["price_from"], "priceCurrency": "INR"}
            if s["price_unit"] == "month":
                spec = {"@type": "UnitPriceSpecification", key: s["price_from"], "priceCurrency": "INR", "unitCode": "MON"}
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
                      "author": ({"@type": "Person", "name": SITE["founder"]["name"]} if SITE["founder"].get("name") else {"@id": ORG_ID}),
                      "publisher": {"@id": ORG_ID}, "mainEntityOfPage": url, "image": BASE + meta.get("og_image", "/assets/img/og-moodily.png")})
        if not any(n.get("@id") == ORG_ID for n in graph):
            graph.append({"@type": "Organization", "@id": ORG_ID, "name": SITE["name"], "url": BASE + "/"})
    if not graph:
        return ""
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":"))
    return '<script type="application/ld+json">{}</script>'.format(data.replace("</", "<\\/"))


# ---------------------------------------------------------------- layout
NAV = [
    ("/services/", "Services", "सेवाएँ"), ("/case-studies/", "Samples", "काम"), ("/insights/", "Insights", "Insights"),
    ("/learn/", "Learn", "सीखें"), ("/digital-saathi/", "Digital Saathi", "Saathi"),
]
SERVICE_NAV = [
    ("/services/local-business-digitalization/", "Local Business Digitalization"), ("/services/google-business-profile/", "Google Business Profile"),
    ("/services/whatsapp-business/", "WhatsApp Business"), ("/services/business-website/", "Business Website"),
    ("/services/brochure-catalogue/", "Brochure / Catalogue"), ("/services/design/", "Logo · Poster · Visiting card"),
    ("/services/social-media-design/", "Social Media Design"), ("/services/presentation-design/", "PPT / Presentation Design"),
    ("/services/digital-invitation/", "Digital Invitation"), ("/services/coaching-digital-services/", "Coaching / Library"),
    ("/services/education-content/", "Education Content"), ("/services/wedding-event/", "Wedding / Event vendors"),
    ("/services/b2b-digital-sales/", "B2B Digital Sales"), ("/services/research-intelligence/", "Research Intelligence"),
    ("/services/knowledge-to-product/", "Knowledge-to-Product"), ("/services/ai-workflows/", "AI Workflows"),
    ("/services/medical-store/", "Medical Store / Clinic"), ("/services/professionals/", "Professionals & LinkedIn"),
    ("/services/creators/", "Creators"), ("/services/estimator/", "Price estimator"),
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
    <ul class="nav-desktop">{links}<li><a href="/contact/"{contact}>Contact</a></li></ul>
    <details class="menu"><summary aria-label="Menu"><span class="burger" aria-hidden="true"></span><span class="menu-label">Menu</span></summary>
      <div class="menu-panel">
        <ul class="nav-links">{links}<li><a href="/about/"{about}>About</a></li><li><a href="/contact/"{contact}>Contact</a></li>
          <li><a href="/contact/?service=free-digital-audit" data-track="free_audit_click" data-label="menu-audit">Free Digital Audit</a></li></ul>
        <p class="menu-heading">Services</p><ul class="nav-sub">{svc}</ul>
      </div>
    </details>
  </nav>
  <div class="nav-actions">{lang}<button class="icon-btn" type="button" id="themeToggle" aria-label="Toggle dark/light theme">◐</button>
    <a class="btn btn-warm btn-sm nav-cta" href="/contact/" data-track="quote_start" data-label="nav-requirement">Requirement बताएं</a></div>
</div></header>""".format(links=links, svc=svc, lang=lang_btn, about=cur("/about/"), contact=cur("/contact/"))


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
      <li><a href="/services/research-intelligence/">Moodily Intelligence Studio</a></li><li><a href="/store/">Moodily Store</a></li>
      <li><a href="/case-studies/">Work samples</a></li><li><a href="/insights/">Insights</a></li><li><a href="/guides/">Hindi guides</a></li><li><a href="/tools/">Tools</a></li></ul></div>
    <div><h2 class="footer-h">Services</h2><ul>{svc}</ul></div>
    <div><h2 class="footer-h">Company</h2><ul>
      <li><a href="/about/">About</a></li><li><a href="/contact/">Contact</a></li><li><a href="/services/">Pricing</a></li>
      <li><a href="/privacy/">Privacy</a></li><li><a href="/terms/">Terms</a></li><li><a href="/refund/">Refund policy</a></li></ul></div>
  </div>
  <p class="footer-note small muted">Moodily curates learning paths using courses offered by recognised providers. Certificates, where applicable, are issued by the respective providers. Moodily has no official partnership with the providers listed unless stated. Some tool links may be affiliate links and are labelled.</p>
  <p class="footer-bottom small muted">© {year} Moodily · moodily.in</p>
</div></footer>
<a class="fab-wa" href="{wa_href}" target="_blank" rel="noopener" data-track="whatsapp_click" data-label="floating" aria-label="WhatsApp पर Moodily से बात करें">{icon}<span>WhatsApp</span></a>
<nav class="mobile-cta" aria-label="Quick actions"><a class="btn btn-primary" href="/contact/" data-track="quote_start" data-label="mobile-bar">Requirement बताएं</a><a class="btn btn-wa" href="{wa_href}" target="_blank" rel="noopener" data-track="whatsapp_click" data-label="mobile-bar">{icon} WhatsApp</a></nav>""".format(
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


def byline_html(meta):
    art = meta.get("article")
    if not art:
        return ""
    who = SITE["founder"]["name"] or "Moodily Editorial"
    mod = art.get("modified", art["published"])
    return ('<p class="container byline small muted">By {} · Published <time datetime="{p}">{p}</time>{upd}</p>').format(
        e(who), p=e(art["published"]), upd=' · Last updated <time datetime="{0}">{0}</time>'.format(e(mod)) if mod != art["published"] else "")


def layout(meta, body, route, ctx):
    lang = meta.get("lang", "hi")
    canonical = BASE + route
    robots = '<meta name="robots" content="noindex, follow">' if meta.get("noindex") else '<meta name="robots" content="index, follow, max-image-preview:large">'
    og_img = BASE + meta.get("og_image", "/assets/img/og-moodily.png")
    view = meta.get("track_view")
    view_attr = ' data-view-event="{}" data-view-label="{}"'.format(e(view[0]), e(view[1])) if view else ""
    return """<!DOCTYPE html>
<html lang="{lang}" data-lang="{dlang}" data-theme="light"{offer_attr}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
{robots}
<meta name="theme-color" content="#f7f5f0">
<meta property="og:site_name" content="Moodily">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="{ogtype}">
<meta property="og:locale" content="{locale}">
<meta property="og:image" content="{og_img}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Moodily — digital services, samples and starting prices">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<link rel="icon" href="/assets/img/moodily-mark.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/assets/img/moodily-logo-512.png">
<script>(function(){{try{{var t=localStorage.getItem('moodily_theme');if(t)document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('moodily_lang');if(l&&document.documentElement.getAttribute('data-bilingual')!==null)document.documentElement.setAttribute('data-lang',l);}}catch(e){{}}var oe=document.documentElement.getAttribute('data-offer-ends');if(oe&&Date.now()>Date.parse(oe))document.documentElement.classList.add('offer-ended');document.documentElement.classList.add('js');}})();</script>
{gtm}
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@500;600;700&family=Mukta:wght@300;400;600;700&display=swap" onload="this.onload=null;this.rel='stylesheet'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@500;600;700&family=Mukta:wght@300;400;600;700&display=swap"></noscript>
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
{byline}{body}
</main>
{footer}
</body>
</html>
""".format(lang=lang, dlang="en" if lang == "en" else "hi", title=e(meta["title"]), desc=e(meta["description"]), canonical=canonical,
           robots=robots, ogtype="article" if meta.get("article") else "website", locale="en_IN" if lang == "en" else "hi_IN",
           og_img=og_img, gtm=gtm_head(), ver=ASSET_VERSION, schema=page_schema(meta, route, ctx), view=view_attr, gtm_body=gtm_body(),
           header=header(route, meta), crumbs=breadcrumbs_html(meta), body=body, footer=footer(), banner=offer_banner(route), byline=byline_html(meta),
           offer_attr=' data-offer-ends="{}" data-offer-id="{}"'.format(OFFER["ends_at"], OFFER["id"]) if OFFER_STATE else "").replace(
        '<html lang="{}" data-lang'.format(lang), '<html lang="{}"{} data-lang'.format(lang, " data-bilingual" if meta.get("bilingual") else ""), 1)


# ---------------------------------------------------------- case pages
def case_page(c):
    shots = "".join('<figure><img src="{}" alt="{}" loading="lazy" decoding="async"><figcaption>{}</figcaption></figure>'.format(
        e(s["src"]), e(s["alt"]), e(s.get("caption", ""))) for s in c.get("screenshots", []))
    svc = SERVICES.get(c["service"])

    def section(h, v):
        if not v:
            return ""
        inner = "<ul class=\"ticks\">{}</ul>".format("".join("<li>{}</li>".format(e(i)) for i in v)) if isinstance(v, list) else "<p>{}</p>".format(e(v))
        return '<section class="case-sec"><h2>{}</h2>{}</section>'.format(h, inner)
    result = c.get("result") or "No measured result is claimed for this project yet."
    ba = ""
    if c.get("before") or c.get("after"):
        ba = '<section class="case-sec"><h2>Before → After</h2><div class="ba-grid">{}<div class="ba-arrow" aria-hidden="true">→</div>{}</div></section>'.format(
            '<div class="ba-col ba-before"><p class="ba-h">Before</p><p>{}</p></div>'.format(e(c.get("before") or "—")),
            '<div class="ba-col ba-after"><p class="ba-h">After</p><p>{}</p></div>'.format(e(c.get("after") or "—")))
    body = """<section class="page-hero"><div class="container narrow"><p class="eyebrow">{cat} · {div}</p><h1>{title}</h1><p class="lead">{work}</p>{kind}</div></section>
<div class="container narrow case">{ctype}{problem}{gap}{input}{built}{workflow}{ba}{deliverables}{time}<section class="case-sec"><h2>Screenshots</h2><div class="shots">{shots}</div></section>{verify}
<section class="case-sec"><h2>Result</h2><p>{result}</p></section>{lessons}
<section class="case-sec cta-box"><h2>ऐसा ही काम चाहिए?</h2><p>Related service: <a href="{spage}#{sid}">{sname}</a></p><p><a class="btn btn-primary" href="/contact/?service={sid}" data-track="quote_start" data-label="case-{slug}">{sname} की requirement भेजें</a> {wa}</p></section></div>""".format(
        cat=e(c["category"]), div=e(DIVISIONS[c["division"]]), title=e(c["title"]), work=e(c["work_type"]), slug=c["slug"],
        kind='<p><span class="badge badge-kind">{}</span></p>'.format(e(KIND_LABEL[c["kind"]])) if KIND_LABEL.get(c.get("kind")) else "",
        ctype=section("Client / project type", c.get("client_type")), problem=section("Problem", c.get("problem")),
        gap=section("Observed gap", c.get("observed_gap")), input=section("Input", c.get("input")),
        built=section("What Moodily created", c.get("built")), workflow=section("Workflow", c.get("workflow") or c.get("method")), ba=ba,
        deliverables=section("Deliverables", c.get("deliverables")), time=section("Time", c.get("time")), shots=shots,
        verify=section("Quality verification", c.get("verification")), result=e(result), lessons=section("Lessons", c.get("lessons")),
        spage=svc["page"], sid=svc["id"], sname=e(svc["name"]), wa=wa_button("WhatsApp", "interested client", svc["name"], track_label="case-" + c["slug"]))
    meta = {"title": "{} — Case study | Moodily".format(c["title"]), "description": "{}: problem, method, what Moodily built and how quality was verified.".format(c["title"]),
            "lang": "en", "breadcrumbs": [["Case studies", "/case-studies/"], [c["title"], "/case-studies/{}/".format(c["slug"])]],
            "track_view": ["case_study_view", c["slug"]]}
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
    lines += ["", "## src/data/intake.json (Google Form)"]
    walk(load("data/intake.json"), "")
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


REDIRECT_TEMPLATE = """<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Moved: {old} → {path} | Moodily</title>
<meta name="description" content="यह Moodily page अब नए पते पर है: {path}। Page अपने-आप खुल जाएगा; न खुले तो link पर click करें।">
<link rel="canonical" href="{url}">
<meta name="robots" content="noindex, follow">
<meta name="moodily-redirect" content="{path}">
<meta http-equiv="refresh" content="0; url={path}">
<script>location.replace("{path}" + location.search + location.hash);</script>
</head>
<body><h1>यह page अब <a href="{path}">{path}</a> पर है</h1></body>
</html>
"""


def main():
    validate_services()
    validate_offer()
    validate_commerce()
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

    lastmod_file = ROOT / ".build-lastmod.json"
    lastmods = json.loads(lastmod_file.read_text()) if lastmod_file.exists() else {}
    new_lastmods = {}
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
        # sitemap lastmod changes only when the page content changes (asset hashes, countdown numbers and year ignored)
        stable = re.sub(r"\?v=[0-9a-f]+|<strong>\d+/\d+</strong>|© \d{4}|data-offer-ends=\"[^\"]*\"", "", html_out)
        digest = hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]
        prev = lastmods.get(route)
        new_lastmods[route] = [digest, prev[1] if prev and prev[0] == digest else TODAY]
        if not meta.get("noindex") and route != "/404.html":
            sitemap.append((route, meta.get("priority", "0.7")))

    for old_route, new_route in REDIRECTS.items():
        target = ROOT.joinpath(*old_route.strip("/").split("/"), "index.html")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(REDIRECT_TEMPLATE.format(old=e(old_route), path=e(new_route), url=e(BASE + new_route)), encoding="utf-8")
        written.append(str(target.relative_to(ROOT)))

    for stale in sorted(old - set(written)):
        p = ROOT / stale
        if p.exists():
            p.unlink()
            try:
                p.parent.rmdir()
            except OSError:
                pass
            print("removed stale", stale)

    lastmod_file.write_text(json.dumps(new_lastmods, indent=0, sort_keys=True) + "\n")
    urls = "".join("<url><loc>{}{}</loc><lastmod>{}</lastmod><priority>{}</priority></url>".format(BASE, r, new_lastmods[r][1], p) for r, p in sitemap)
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
