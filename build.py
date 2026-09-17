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
import collections
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
EVIDENCE = load("data/evidence.json")
AMAZON = SITE.get("amazon_associates") or {}
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


def offer_urgency_ok():
    """Countdown + slot counter render ONLY when the owner has confirmed the offer is real and payable.

    Gate (src/site.json -> offer.urgency_confirmed). Until it is true the page still shows the
    introductory pricing and its terms, but no timer and no slot counter — an unverified
    scarcity claim is a dark pattern, and a discount nobody can actually pay for is worse.
    """
    return bool(OFFER.get("urgency_confirmed"))


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
# Legal / transparency routes. These carry no promotional banner, no sticky conversion bar and no
# floating WhatsApp button: a compliance page should read as clarity, not as a sales surface.
LEGAL_ROUTES = {"/privacy/", "/terms/", "/refund/", "/affiliate-disclosure/"}
NO_BANNER = LEGAL_ROUTES | {"/contact/thanks/", "/payment/success/", "/404.html", "/offers/{}/".format(OFFER.get("id"))}


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
    if not offer_urgency_ok():
        return ('<p class="offer-note offer-only">Founding client introductory pricing · '
                '<a href="/offers/{id}/">शर्तें</a></p>').format(id=OFFER["id"])
    return ('<p class="offer-note offer-only"><strong>{left}/{total}</strong> founding slots बाकी · समय बाकी: <span data-countdown>{deadline} तक</span> · '
            '<a href="/offers/{id}/">शर्तें</a></p>').format(left=OFFER_STATE["left"], total=OFFER["slots_total"], deadline=e(offer_deadline_hi()), id=OFFER["id"])


def offer_banner(route):
    if not OFFER_STATE or route in NO_BANNER:
        return ""
    return ('<aside class="offer-banner offer-only" aria-label="{name} offer"><div class="container offer-inner">'
            '<p><span class="badge badge-offer">{pct}% OFF</span> <strong>{name}:</strong> पहले {total} ग्राहकों के लिए starter packages पर {pct}% छूट</p>'
            '{meta}'
            '<a class="btn btn-sm offer-btn" href="/offers/{id}/" data-track="offer_cta_click" data-label="banner">Offer देखें →</a></div></aside>').format(
        name=e(OFFER["name"]), pct=OFFER["discount_pct"], total=OFFER["slots_total"], id=OFFER["id"],
        meta=('<p class="offer-meta"><strong>{}/{}</strong> slots बाकी · समय बाकी: <span data-countdown>{} तक</span></p>'.format(
            OFFER_STATE["left"], OFFER["slots_total"], e(offer_deadline_hi())) if offer_urgency_ok()
            else '<p class="offer-meta">Introductory pricing · <a href="/offers/{}/">पूरी शर्तें</a></p>'.format(OFFER["id"])))


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
    # With no endpoint the form cannot reach a server, so it says so and hands off through WhatsApp in one tap.
    # It must never look like a submission that Moodily has received.
    posts = bool(endpoint)
    return FORM_TEMPLATE.format(endpoint=e(endpoint), success=e(SITE["form"]["success_path"]), roles=opt(roles),
                                btn_class="btn-primary" if posts else "btn-wa",
                                submit_label="Enquiry भेजें →" if posts else "WhatsApp पर भेजें →",
                                route_note=("भेजने के बाद 1 working day में जवाब।" if posts else
                                            "यह form WhatsApp पर भेजा जाएगा — button दबाते ही आपकी भरी हुई जानकारी के साथ "
                                            "WhatsApp खुलेगा, बस Send दबाइए। तब तक Moodily तक कुछ नहीं पहुँचता।"),
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
  <button class="btn {btn_class} btn-lg btn-block" type="submit">{submit_label}</button>
  <p class="small muted" id="formRoute">{route_note}</p>
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
            '{urgency}'
            '<p class="muted small">Scope वही जो regular package में है — सिर्फ़ दाम कम। Slot पूरा payment मिलने पर पक्का होता है। <a href="/offers/{id}/">पूरी शर्तें</a></p></div>'
            '<div class="grid grid-3">{cards}</div></div></section>').format(
        id=OFFER["id"], name=e(OFFER["name"]), total=OFFER["slots_total"], n=len(OFFER["services"]), pct=OFFER["discount_pct"],
        cards="".join(cards),
        urgency=('<p class="lead"><strong>{}/{}</strong> slots बाकी · समय बाकी: <span class="countdown" data-countdown>{} तक</span></p>'.format(
            OFFER_STATE["left"], OFFER["slots_total"], e(offer_deadline_hi())) if offer_urgency_ok()
            else '<p class="lead">Founding client introductory pricing — पहले {} ग्राहकों के लिए।</p>'.format(OFFER["slots_total"])))


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


def validate_form_prefill():
    """A prefill value that is not an exact dropdown option is silently dropped by Google."""
    if not INTAKE.get("form_url"):
        return
    opts = set(INTAKE.get("form_category_options") or [])
    if not opts:
        raise SystemExit("intake.json: form_url is set but form_category_options is empty — cannot verify prefill values")
    for where, mapping in (("form_category_map", INTAKE.get("form_category_map", {})),
                           ("form_category_by_service_category", INTAKE.get("form_category_by_service_category", {})),
                           ("form_category_by_service_id", INTAKE.get("form_category_by_service_id", {}))):
        for key, value in mapping.items():
            if value not in opts:
                raise SystemExit("intake.json: {}['{}'] = '{}' is not an option of the Form's Service Category dropdown — "
                                 "Google would discard it".format(where, key, value))
    if INTAKE.get("form_category_unsure") and INTAKE["form_category_unsure"] not in opts:
        raise SystemExit("intake.json: form_category_unsure is not a Form option")
    # every live service must resolve to a real option, or we send nothing rather than something wrong
    for svc in ACTIVE:
        got = form_category_for(svc)
        if got and got not in opts:
            raise SystemExit("intake.json: service '{}' maps to '{}', which the Form does not offer".format(svc["id"], got))
    for key in ("service_category", "sub_service", "offer_code", "sample_or_estimate"):
        eid = INTAKE.get("entry_ids", {}).get(key, "")
        if eid and not re.fullmatch(r"entry\.\d+", str(eid)):
            raise SystemExit("intake.json: entry_ids['{}'] = '{}' is not an entry.NNNN id".format(key, eid))
    # operational links must never reach the repo or the public site
    blob = json.dumps(INTAKE, ensure_ascii=False) + json.dumps(SITE, ensure_ascii=False)
    for bad in ("/forms/d/1", "spreadsheets.google.com", "/spreadsheets/d/"):
        if bad in blob:
            raise SystemExit("intake.json/site.json contains an owner-only Form-edit or Sheet URL — only the public /viewform URL may be committed")


def validate_amazon():
    """Refuse to build a half-configured affiliate programme."""
    if AMAZON.get("enabled") and not AMAZON.get("tag"):
        raise SystemExit("site.json: amazon_associates.enabled is true but tag is empty — untagged affiliate links would earn nothing and mislead readers")
    if AMAZON.get("disclosure_enabled") and not AMAZON.get("enabled"):
        raise SystemExit("site.json: amazon_associates.disclosure_enabled is true while the programme is off — that claims earnings Moodily does not make")
    if AMAZON.get("enabled") and not AMAZON.get("disclosure_enabled"):
        raise SystemExit("site.json: affiliate links are enabled without disclosure_enabled — disclosure is required, not optional")
    if AMAZON.get("enabled") and not AMAZON.get("approved_properties"):
        raise SystemExit("site.json: list the exact URLs approved in Associates Central before enabling affiliate links")


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
    ctype_ids = {c["id"] for c in ROUTERS["customer_types"]}
    seen_slugs = set()
    for smp in SAMPLES.values():
        if smp.get("kind") not in KIND_LABEL:
            raise SystemExit("samples.json: {} needs kind self-initiated|client|concept".format(smp["id"]))
        # a sample either ships a real, present asset or a named concept preview — never a broken image
        if smp.get("image"):
            if not (ROOT / smp["image"].lstrip("/")).exists():
                raise SystemExit("samples.json: image missing for {}".format(smp["id"]))
        elif not smp.get("preview"):
            raise SystemExit("samples.json: {} needs either an image or a preview key".format(smp["id"]))
        for sid in smp.get("services", []):
            if sid not in SERVICES:
                raise SystemExit("samples.json: {} references unknown service {}".format(smp["id"], sid))
        if not smp.get("slug"):
            continue
        # catalogue entries carry the full model and must never invent a price of their own
        if smp["slug"] in seen_slugs:
            raise SystemExit("samples.json: duplicate slug {}".format(smp["slug"]))
        seen_slugs.add(smp["slug"])
        if smp.get("sample_type") not in SAMPLE_TYPE:
            raise SystemExit("samples.json: {} needs sample_type real-client|moodily-internal|self-initiated|concept".format(smp["id"]))
        if smp.get("category") not in SAMPLE_CATS:
            raise SystemExit("samples.json: {} has unknown category {}".format(smp["id"], smp.get("category")))
        if smp.get("service") and smp["service"] not in SERVICES:
            raise SystemExit("samples.json: {} references unknown service {}".format(smp["id"], smp["service"]))
        for t in smp.get("customer_types", []):
            if t not in ctype_ids:
                raise SystemExit("samples.json: {} has unknown customer_type {}".format(smp["id"], t))
        if smp.get("case_study") and smp["case_study"] not in CASES_BY_SLUG:
            raise SystemExit("samples.json: {} references unknown case study {}".format(smp["id"], smp["case_study"]))
        for k in ("price", "price_from", "amount"):
            if k in smp:
                raise SystemExit("samples.json: {} must not carry its own {} — price comes from services.json".format(smp["id"], k))
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
        services[sid] = {"name": name, "category": INTAKE["categories"][cat]["label"],
                         # what the Form's dropdown actually accepts — anything else is discarded by Google
                         "form_category": form_category_for(x) if x else INTAKE.get("form_category_map", {}).get(cat, ""),
                         "price": price,
                         "offer_price": "₹" + inr(offer_price(x)) if x and in_offer(x) else "",
                         "prefill_url": (x.get("form_prefill_url") if x else "") or INTAKE.get("service_prefill_urls", {}).get(sid)
                         or INTAKE["categories"][cat].get("prefill_url") or "",
                         "page": "{}#{}".format(x["page"], sid) if x else ""}
    cfg = {"form_url": form_url, "samples": {x["slug"]: x["catalogue_title"] for x in SAMPLE_CATALOGUE},
           "entry_ids": {k: v for k, v in INTAKE.get("entry_ids", {}).items() if not k.startswith("_")},
           "offer": {"id": OFFER.get("id"), "name": OFFER.get("name"), "pct": OFFER.get("discount_pct"), "active": bool(OFFER_STATE)},
           "services": services}
    cfg_json = json.dumps(cfg, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    context = ('<div class="card intake-context" id="intakeContext" hidden><p class="eyebrow">आपने चुना</p>'
               '<h2 class="intake-service" id="intakeService"></h2><p class="muted small" id="intakeCategory"></p>'
               '<p class="price" id="intakePrice"></p><p class="notice small" id="intakeSample" hidden></p>'
               '<p class="notice small" id="intakeOffer" hidden></p><p class="notice small" id="intakeEstimate" hidden></p>'
               '<p class="small"><a id="intakeDetails" href="/services/">Package details</a> · <a href="/services/#finder">दूसरी service चुनें</a></p></div>')
    if form_url:
        main = ('<div class="card intake-cta featured"><p class="eyebrow">3–5 मिनट · कोई login नहीं</p><h2>Requirement Form</h2>'
                '<p>अपनी requirement record करने के लिए secure Google Form भरें। आपने जो service या sample चुना है, '
                'वह पहले से भरा मिलेगा — दोबारा लिखने की ज़रूरत नहीं।</p>'
                '<a class="btn btn-primary btn-lg btn-block" id="gformBtn" href="{url}" target="_blank" rel="noopener" data-track="google_form_open" data-label="contact">Requirement Form खोलें →</a>'
                '<p class="small muted">Form नई tab में खुलेगा। <strong>यही एक रास्ता है जिससे आपकी requirement record होती है।</strong> '
                'भेजने के बाद 1 working day में WhatsApp या email पर जवाब।</p>'
                '<details class="not-included"><summary>Form भरने से पहले तैयार रखें</summary><ul class="ticks small">'
                '<li>आपका मुख्य goal और deadline</li><li>Budget का अंदाज़ा (या "Need recommendation")</li>'
                '<li>Reference, existing website/social या Google Drive link</li><li>Text/content जो design में जाना है</li></ul></details>'
                '{sens}</div>').format(url=e(form_url), sens=SENSITIVE_NOTICE)
    else:
        main = '<div class="intake-legacy">{}{}</div>'.format(SENSITIVE_NOTICE, c_lead_form(args, ctx))
    # label matches the framing: the Form records, WhatsApp is for talking
    wa = wa_button("WhatsApp पर बात करें" if form_url else "WhatsApp पर requirement भेजें",
                   cls="btn btn-wa btn-lg btn-block", track_label="intake").replace("<a class=", '<a id="intakeWa" class=', 1)
    return ('<div class="intake" id="intake" data-mode="{mode}"><script type="application/json" id="intakeConfig">{cfg}</script>'
            '<div class="intake-grid"><div class="intake-main">{context}{main}</div>'
            '<aside class="intake-side"><div class="card"><h2 class="side-h">WhatsApp पर बात करें</h2><p class="small muted">सवाल पूछना है या जल्दी बात करनी है? WhatsApp कीजिए — voice note भी चलेगा। {wa_note}</p>{wa}'
            '<p class="small muted">या email: <a href="mailto:{email}">{email}</a></p></div>'
            '<div class="card"><h2 class="side-h">आगे क्या होगा</h2><ol class="steps-list small"><li>हम आपकी requirement पढ़ते हैं और ज़रूरत हो तो 1–2 सवाल पूछते हैं।</li>'
            '<li>लिखित scope, timeline, revisions, third-party खर्च और quote भेजते हैं।</li><li>आप हाँ कहें, तभी काम शुरू होता है।</li></ol></div></aside></div></div>').format(
        mode="google-form" if form_url else "fallback", cfg=cfg_json, context=context, main=main, wa=wa, email=e(SITE["email"]),
        wa_note=("यह बातचीत के लिए है — requirement record करने के लिए ऊपर वाला Form भरिए।" if form_url else
                 "आपका message भेजते ही Moodily तक पहुँच जाता है।"))


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
        if smp.get("image"):
            visual = ('<div class="mock mock-{frame}"><div class="mock-screen"><img src="{img}" alt="{alt}" '
                      'width="{w}" height="{h}" loading="lazy" decoding="async"></div></div>').format(
                frame=e(smp["frame"]), img=e(smp["image"]), alt=e(smp["alt"]), w=smp["width"], h=smp["height"])
        else:
            visual = '<div class="sample-shot is-concept">{}</div>'.format(_sample_preview(smp.get("preview", ""), smp["title"]))
        more = ('<a class="small" href="/samples/{0}/" data-track="sample_card_click" data-label="grid-{0}">पूरा sample देखें →</a>'.format(
            smp["slug"]) if smp.get("slug") else "")
        cards.append('<figure class="card sample-card" data-sample="{id}">{visual}'
                     '<figcaption><span class="badge badge-kind">{kind}</span><strong>{title}</strong><span class="small muted">{desc}</span>{fmts}{more}</figcaption></figure>'.format(
                         id=smp["id"], visual=visual, kind=e(KIND_LABEL[smp["kind"]]), title=e(smp["title"]), desc=e(smp["description"]),
                         fmts='<span class="small">Format: {}</span>'.format(e(fmts)) if fmts else "", more=more))
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
            '<h3>{name}</h3><p class="pkg-for">{who}</p><p class="pkg-outcome">{tagline}</p>{price}'
            '<p class="small muted">{mode}</p><ul class="ticks">{items}</ul>'
            '<p class="pkg-meta"><span>⏱ {timeline}</span><span>↻ {revisions}</span></p>'
            '<div class="card-actions"><a class="btn btn-primary" href="/contact/?service={id}" data-track="quote_start" data-label="pkg:{id}">Requirement बताएं</a>'
            '<a class="btn btn-outline" href="{page}#{id}" data-track="service_card_click" data-label="pkg-detail:{id}">पूरा scope →</a></div></article>'.format(
                lead=" pkg-lead" if sid == lead else "", id=sid, attrs=card_attrs(svc), name=e(svc["name"]), tagline=e(svc["tagline"]),
                who=e(svc["for"].split("।")[0].split(" जो ")[0].strip(" ,।")[:88]),
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


# ------------------------------------------------- visual storytelling components
# Tiny inline SVG mockups. Inline so they theme with currentColor, add no requests and
# no image files to the repo. Every one is aria-hidden with the meaning carried in text.
def _mock(kind):
    """Illustrative interface mockups, inline SVG. Never a real screenshot, never real client data.

    'before' states are deliberately sparse: missing photos, blank fields, no way to act.
    'after' states show what a finished Moodily handover actually looks like — a business that can
    be found, judged and contacted. Every one is captioned as a sample in the markup around it.
    """
    P, A, G, S = "var(--primary)", "var(--accent)", "var(--success)", "var(--secondary)"
    MUT, LINE, CARD, SUNK = "var(--border-strong)", "var(--border)", "var(--surface)", "var(--surface-sunken)"

    def r(x, y, w, h, c=MUT, rad=3):
        return '<rect x="{}" y="{}" width="{}" height="{}" rx="{}" fill="{}"/>'.format(x, y, w, h, rad, c)

    def star(cx, cy, c=A, sc=1.0):
        pts = "0,-5 1.5,-1.6 5,-1.6 2.2,0.7 3.1,4.2 0,2.2 -3.1,4.2 -2.2,0.7 -5,-1.6 -1.5,-1.6"
        return '<polygon points="{}" fill="{}" transform="translate({},{}) scale({})"/>'.format(pts, c, cx, cy, sc)

    def stars(x, y, n=5, filled=5):
        return "".join(star(x + i * 13, y, A if i < filled else LINE) for i in range(n))

    def pin(cx, cy, c=A):
        return ('<path d="M{cx} {t}c-4.4 0-8 3.6-8 8 0 5.6 8 13 8 13s8-7.4 8-13c0-4.4-3.6-8-8-8z" fill="{c}"/>'
                '<circle cx="{cx}" cy="{ic}" r="3" fill="#fff"/>').format(cx=cx, t=cy - 10, ic=cy - 2, c=c)

    def chip(x, y, w, c, label_c=None):
        return r(x, y, w, 15, c, 7)

    # a faint map backdrop: roads only, no real geography
    def maplet(x, y, w, h):
        return (r(x, y, w, h, SUNK, 6)
                + '<path d="M{a} {b}h{w}M{a} {c}h{w}M{d} {y}v{h}M{e} {y}v{h}" stroke="{l}" stroke-width="2" fill="none" opacity=".9"/>'.format(
                    a=x, b=y + h * 0.34, c=y + h * 0.7, w=w, d=x + w * 0.3, e=x + w * 0.68, y=y, h=h, l=LINE))

    M = {}
    # ---- local business: an unfindable shop vs a shop you can find, judge and contact
    M["gbp-before"] = (r(14, 14, 78, 54, LINE, 6) + '<text x="53" y="45" font-size="11" fill="{}" text-anchor="middle">no photo</text>'.format(MUT)
                       + r(102, 16, 104, 10, MUT) + r(102, 32, 62, 7) + r(102, 46, 44, 7)
                       + stars(108, 62, 5, 0) + r(176, 57, 30, 8)
                       + r(14, 80, 120, 8) + r(14, 94, 86, 8)
                       + r(14, 112, 238, 22, SUNK, 11) + '<text x="133" y="127" font-size="10" fill="{}" text-anchor="middle">कोई action button नहीं</text>'.format(MUT))
    M["gbp-after"] = (maplet(14, 12, 104, 74) + pin(66, 56, A)
                      + r(126, 14, 110, 11, "var(--text)") + stars(128, 36) + r(196, 31, 40, 9, G, 4)
                      + r(126, 50, 92, 7) + r(126, 62, 66, 7)
                      + r(126, 76, 26, 26, LINE, 4) + r(156, 76, 26, 26, LINE, 4) + r(186, 76, 26, 26, LINE, 4) + r(216, 76, 26, 26, LINE, 4)
                      + chip(14, 96, 48, P) + chip(66, 96, 48, G)
                      + chip(14, 116, 74, P) + chip(94, 116, 74, G) + chip(174, 116, 78, A))
    # ---- coaching / library: fees on the phone vs a page that answers and captures
    M["wa-before"] = (r(14, 14, 238, 26, LINE, 6) + '<text x="133" y="31" font-size="10" fill="{}" text-anchor="middle">"fees kitni hai?" — हर बार call</text>'.format(MUT)
                      + r(14, 50, 150, 8) + r(14, 64, 116, 8) + r(14, 78, 134, 8)
                      + r(14, 100, 96, 22, SUNK, 11) + '<text x="62" y="115" font-size="10" fill="{}" text-anchor="middle">no page</text>'.format(MUT))
    M["wa-after"] = (r(14, 12, 238, 30, CARD, 6) + r(24, 20, 104, 12, "var(--text)") + chip(200, 19, 44, G)
                     + r(14, 50, 114, 34, SUNK, 6) + r(24, 58, 60, 8, P) + r(24, 70, 84, 6)
                     + r(138, 50, 114, 34, SUNK, 6) + r(148, 58, 60, 8, P) + r(148, 70, 84, 6)
                     + r(14, 92, 238, 20, CARD, 6) + r(24, 99, 120, 7) + chip(196, 94, 48, A)
                     + chip(14, 118, 114, P) + chip(138, 118, 114, G))
    # ---- professional / creator: scattered files vs a presence that sells for you
    M["doc-before"] = (r(14, 14, 56, 46, LINE, 4) + r(78, 14, 56, 46, LINE, 4) + r(142, 14, 56, 46, LINE, 4) + r(206, 14, 46, 46, LINE, 4)
                       + '<text x="133" y="80" font-size="10" fill="{}" text-anchor="middle">files इधर-उधर</text>'.format(MUT)
                       + r(14, 92, 150, 8) + r(14, 106, 104, 8) + r(14, 120, 128, 8))
    M["doc-after"] = (r(14, 12, 238, 20, CARD, 6) + r(24, 18, 44, 8, "var(--text)") + chip(206, 15, 38, A)
                      + r(14, 40, 140, 12, "var(--text)") + r(14, 58, 104, 7) + r(14, 70, 122, 7)
                      + chip(14, 84, 70, P) + chip(90, 84, 64, G)
                      + r(166, 40, 86, 62, SUNK, 6) + r(176, 50, 66, 8, P) + r(176, 62, 52, 6) + r(176, 74, 66, 6) + chip(176, 86, 46, A)
                      + r(14, 112, 238, 22, SUNK, 6) + r(24, 120, 96, 7) + chip(196, 115, 48, G))
    art = M.get(kind, "")
    return ('<svg class="ba-mock" viewBox="0 0 266 148" role="img" aria-label="{}" preserveAspectRatio="xMidYMid meet">'
            '<rect width="266" height="148" fill="{}"/>{}</svg>').format(
        e(BA_MOCK_ALT.get(kind, "Illustrative interface sample")), "var(--surface-sunken)", art)


BA_MOCK_ALT = {
    "gbp-before": "नमूना: अधूरी business listing — कोई photo नहीं, कोई rating नहीं, कोई action button नहीं",
    "gbp-after": "नमूना: पूरी business listing — map पर pin, rating, photos और call/WhatsApp/directions buttons",
    "wa-before": "नमूना: fees और batch की जानकारी सिर्फ़ call पर, कोई course page नहीं",
    "wa-after": "नमूना: course और batch cards, WhatsApp enquiry button और brochure download",
    "doc-before": "नमूना: काम बिखरी हुई files में, भेजने लायक कुछ नहीं",
    "doc-after": "नमूना: एक page जो काम दिखाता है, साथ में lead magnet और enquiry form",
}



BA_EXAMPLES = [
    {"h": "दुकान / local business", "sub": "एक ऐसी दुकान जो Google पर अधूरी दिखती है",
     "mock": "gbp", "before": ["Google listing अधूरी — गलत समय, पुराना नंबर", "WhatsApp पर enquiry का कोई साफ़ रास्ता नहीं",
                               "न website, न digital catalogue", "हर जगह अलग-अलग नाम और logo"],
     "after": ["Google Maps पर pin, सही समय और directions", "Photos, services और rate list — सब listing पर",
               "Call · WhatsApp · Directions — तीनों एक tap पर", "Counter पर review QR, ताकि rating असली ग्राहकों से बने",
               "Digital catalogue जो chat में भेजा जा सके"]},
    {"h": "Coaching / library", "sub": "एक coaching centre जहाँ हर जानकारी फ़ोन पर ही मिलती है",
     "mock": "wa", "before": ["Batch और fees की जानकारी सिर्फ़ call पर", "कोई course brochure नहीं",
                              "Enquiry कहाँ आई, कहाँ गई — पता नहीं", "Study material बिखरा हुआ"],
     "after": ["Course और batch cards, fees लिखी हुई", "WhatsApp enquiry button — हर पूछने वाला record होता है",
               "Digital brochure — PDF और link दोनों", "Google पर centre दिखता है, study resources एक जगह"]},
    {"h": "Manufacturer / B2B", "sub": "एक manufacturer जो अब तक marketplace और जान-पहचान पर चलता है",
     "mock": "doc", "before": ["Catalogue हर buyer को हाथ से भेजना पड़ता है", "अपनी कोई website नहीं — सिर्फ़ marketplace listing",
                               "Company profile presentation पुरानी है", "Enquiry कहाँ से आई, पता नहीं चलता"],
     "after": ["अपनी website — marketplace के भरोसे नहीं", "Professional catalogue और company profile PDF",
               "Product presentation buyer meeting के लिए", "WhatsApp, QR और enquiry form एक साथ"]},
    {"h": "Wedding / event business", "sub": "एक decorator या photographer जिसका काम Instagram में दबा है",
     "mock": "gbp", "before": ["Portfolio Instagram posts में बिखरा", "हर पूछने वाले को rate list दोबारा टाइप करना",
                               "Enquiry DM, call और status में बँटी", "Package क्या-क्या है, साफ़ नहीं"],
     "after": ["एक portfolio page जो link में भेजा जा सके", "Packages और rate card लिखित",
               "WhatsApp enquiry एक जगह", "Reel और social assets, ज़रूरत हो तो Google presence"]},
    {"h": "Professional / creator", "sub": "एक consultant जिसका काम अच्छा है पर दिखता नहीं",
     "mock": "doc", "before": ["सालों का knowledge files में बिखरा", "Presentation हर बार नए सिरे से बनती है",
                               "कोई ऐसा asset नहीं जो lead लाए", "पूछने वाले को भेजने के लिए कुछ नहीं"],
     "after": ["एक page जो काम का सबूत देता है", "तैयार PPT / pitch deck template",
               "Lead magnet — guide, checklist या report", "Structured enquiry form, ताकि कोई पूछने वाला छूटे नहीं"]},
]


def c_before_after_saathi(args, ctx):
    """Illustrative before → after for three buyer types. Service examples, not client results."""
    out = []
    for i, x in enumerate(BA_EXAMPLES, 1):
        out.append(
            '<article class="ba-card"><header><h3>{h}</h3><p>{sub}</p></header><div class="ba-split">'
            '<div class="ba-side is-before"><p class="ba-label is-before">पहले</p><figure class="ba-fig">{mb}'
            '<figcaption>नमूना चित्र · illustrative</figcaption></figure><ul>{before}</ul></div>'
            '<div class="ba-step" aria-hidden="true"><span>→</span></div>'
            '<div class="ba-side is-after"><p class="ba-label is-after">Moodily के बाद</p><figure class="ba-fig">{ma}'
            '<figcaption>नमूना चित्र · illustrative</figcaption></figure><ul>{after}</ul></div>'
            '</div></article>'.format(
                h=e(x["h"]), sub=e(x["sub"]), mb=_mock(x["mock"] + "-before"), ma=_mock(x["mock"] + "-after"),
                before="".join("<li>{}</li>".format(e(b)) for b in x["before"]),
                after="".join("<li>{}</li>".format(e(a)) for a in x["after"])))
    note = ('<p class="small muted ba-note">ऊपर के चित्र नमूने हैं — किसी client का नाम, number या result नहीं। '
            'असली काम <a href="#work">samples</a> और <a href="/case-studies/">case studies</a> में देखिए।</p>')
    return '<div class="ba-saathi">{}</div>{}'.format("".join(out), note)


# icon set — 24px line glyphs, one path each, inherit currentColor
_ICONS = {
    "globe": "M12 3a9 9 0 100 18 9 9 0 000-18zm0 0c2.5 2.3 3.8 5.3 3.8 9s-1.3 6.7-3.8 9m0-18C9.5 5.3 8.2 8.3 8.2 12s1.3 6.7 3.8 9M3.3 9h17.4M3.3 15h17.4",
    "pin": "M12 21s7-5.6 7-11a7 7 0 10-14 0c0 5.4 7 11 7 11zm0-8.2a2.8 2.8 0 110-5.6 2.8 2.8 0 010 5.6z",
    "chat": "M21 11.5A7.5 8.5 0 0112 20a9.7 9.7 0 01-3.4-.6L3 21l1.7-4.6A8.3 8.3 0 013 11.5 7.5 8.5 0 0112 3a7.5 8.5 0 019 8.5z",
    "deck": "M3 4h18v11H3zM3 15l9 5 9-5M9 8.5h6M9 11.5h4",
    "book": "M4 4h7a2 2 0 012 2v14a2 2 0 00-2-2H4zm16 0h-7a2 2 0 00-2 2v14a2 2 0 012-2h7z",
    "grid": "M4 4h7v7H4zm9 0h7v7h-7zM4 13h7v7H4zm9 0h7v7h-7z",
    "mail": "M3 6h18v12H3zm0 .6l9 6.6 9-6.6",
    "image": "M3 5h18v14H3zm3.5 4.5a1.4 1.4 0 102.8 0 1.4 1.4 0 00-2.8 0zM3 16l5.2-4.6L13 16m0 0l3.3-2.8L21 17",
    "file": "M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8zm0 0v5h5M8.5 13h7M8.5 16.5h5",
    "search": "M11 4a7 7 0 100 14 7 7 0 000-14zm5 12l4.5 4.5",
    "spark": "M12 3l2 5.4L19.4 10 14 12l-2 5.4L10 12 4.6 10 10 8.4zM18.5 16l.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9z",
    "flow": "M6 4h5v5H6zm7 11h5v5h-5zM8.5 9v4a2 2 0 002 2h2.5M15.5 4h3v3h-3z",
}

CREATES = [
    ("globe", "Website", "Landing page से business website तक", "business-website"),
    ("pin", "Google Business", "Maps पर सही दिखना", "google-business-fix"),
    ("chat", "WhatsApp Setup", "Catalogue + quick replies", "whatsapp-business-setup"),
    ("deck", "PPT / Deck", "Formatting से pitch deck तक", "presentation-design-only"),
    ("file", "Brochure", "Print और WhatsApp दोनों के लिए", "business-brochure"),
    ("grid", "Catalogue", "Product list जो भेजी जा सके", "product-catalogue"),
    ("mail", "Invitation", "Static और animated", "invitation-digital"),
    ("image", "Poster / Creative", "Social और print", "print-design-single"),
    ("book", "Study PDF", "Chapter से पूरा learning kit", "education-content-pack"),
    ("search", "Research", "Market और competitor brief", "research-intelligence-sprint"),
    ("spark", "Logo / Brand Kit", "एक जैसी पहचान हर जगह", "logo-starter"),
    ("flow", "AI Workflow", "दोहराने वाला काम automate", "ai-automation-starter"),
]


def c_creates(args, ctx):
    """A visual answer to 'what do I actually receive?' — concrete outputs, each linked and priced."""
    tiles = []
    for icon, name, sub, sid in CREATES:
        svc = SERVICES.get(sid)
        price = price_text(svc) + " से" if svc and svc.get("price_from") else "Custom quote"
        href = "{}#{}".format(svc["page"], sid) if svc else "/services/"
        tiles.append(
            '<a class="create-tile" href="{href}" data-track="service_card_click" data-label="creates:{sid}">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="{d}"/></svg>'
            '<span>{name}<em>{price}</em></span></a>'.format(href=e(href), sid=sid, d=_ICONS[icon], name=e(name), price=e(price)))
    return '<div class="creates">{}</div>'.format("".join(tiles))


# ------------------------------------------------- sample catalogue
# Concept previews are inline SVG: they theme with the design tokens, cost no request and
# add no binary file to the repo. A concept preview is ALWAYS labelled as a concept.
def _sample_preview(key, title):
    P, A, G, S = "var(--primary)", "var(--accent)", "var(--success)", "var(--secondary)"
    MUT, LINE, CARD = "var(--border-strong)", "var(--border)", "var(--surface)"

    def r(x, y, w, h, c=MUT, rad=3):
        return '<rect x="{}" y="{}" width="{}" height="{}" rx="{}" fill="{}"/>'.format(x, y, w, h, rad, c)

    def c(cx, cy, rr, col):
        return '<circle cx="{}" cy="{}" r="{}" fill="{}"/>'.format(cx, cy, rr, col)
    art = {
        "gbp": r(14, 14, 84, 62, P, 8) + r(108, 16, 118, 10, "var(--text)") + r(108, 32, 84, 8) + r(108, 46, 140, 8)
               + c(114, 66, 5, A) + c(128, 66, 5, A) + c(142, 66, 5, A) + c(156, 66, 5, A) + c(170, 66, 5, LINE)
               + r(14, 88, 110, 22, G, 11) + r(134, 88, 110, 22, P, 11) + r(14, 120, 230, 8),
        "whatsapp": r(14, 12, 236, 30, CARD, 8) + r(24, 20, 96, 12, "var(--text)") + r(24, 52, 150, 26, LINE, 13)
                    + r(100, 86, 150, 26, G, 13) + r(14, 120, 120, 10) + r(212, 118, 38, 16, A, 8),
        "starter": r(14, 14, 74, 54, P, 8) + r(96, 14, 74, 54, G, 8) + r(178, 14, 74, 54, A, 8)
                   + r(14, 80, 238, 9, "var(--text)") + r(14, 96, 180, 8) + r(14, 112, 120, 22, P, 11),
        "catalogue": r(14, 14, 70, 56, LINE, 6) + r(96, 14, 70, 56, LINE, 6) + r(178, 14, 70, 56, LINE, 6)
                     + r(14, 76, 50, 8) + r(96, 76, 50, 8) + r(178, 76, 50, 8)
                     + r(14, 90, 34, 12, A, 6) + r(96, 90, 34, 12, A, 6) + r(178, 90, 34, 12, A, 6)
                     + r(14, 116, 238, 10, P, 5),
        "brochure": r(14, 12, 74, 122, CARD, 4) + r(92, 12, 74, 122, CARD, 4) + r(170, 12, 74, 122, P, 4)
                    + r(22, 20, 56, 30, LINE, 3) + r(22, 56, 56, 7) + r(22, 68, 40, 7)
                    + r(100, 20, 58, 8, "var(--text)") + r(100, 34, 58, 6) + r(100, 46, 44, 6) + r(100, 62, 40, 12, A, 6),
        "vcard": r(30, 26, 206, 96, P, 12) + r(46, 44, 62, 10, "#fff") + r(46, 62, 96, 7, "#ffffffaa")
                 + r(46, 90, 44, 16, A, 8) + r(98, 90, 44, 16, "#ffffff44", 8) + c(206, 74, 18, "#ffffff33"),
        "landing": r(14, 12, 238, 18, CARD, 6) + r(22, 18, 40, 6, "var(--text)") + r(200, 17, 44, 9, A, 5)
                   + r(14, 38, 140, 12, "var(--text)") + r(14, 56, 110, 8) + r(14, 70, 96, 20, P, 10)
                   + r(166, 38, 86, 52, LINE, 6) + r(14, 102, 74, 32, CARD, 6) + r(96, 102, 74, 32, CARD, 6) + r(178, 102, 74, 32, CARD, 6),
        "social": r(14, 14, 70, 70, P, 6) + r(96, 14, 70, 70, A, 6) + r(178, 14, 70, 70, G, 6)
                  + r(14, 94, 70, 8) + r(96, 94, 56, 8) + r(178, 94, 64, 8) + r(14, 112, 100, 18, P, 9),
        "ppt": r(14, 12, 238, 94, CARD, 6) + r(28, 24, 104, 12, "var(--text)") + r(28, 44, 84, 7) + r(28, 58, 96, 7)
               + r(28, 76, 52, 14, A, 7) + r(148, 24, 90, 66, P, 6)
               + r(14, 116, 52, 14, LINE, 4) + r(72, 116, 52, 14, LINE, 4) + r(130, 116, 52, 14, P, 4),
        "invite": r(58, 10, 150, 124, CARD, 8) + r(72, 26, 122, 1.5, A) + r(86, 42, 94, 12, "var(--text)")
                  + r(100, 62, 66, 8) + c(133, 90, 13, A) + r(86, 110, 94, 8) + r(72, 124, 122, 1.5, A),
        "research": r(14, 12, 116, 122, CARD, 6) + r(26, 24, 84, 10, "var(--text)") + r(26, 42, 92, 6) + r(26, 54, 70, 6)
                    + r(26, 70, 92, 6) + r(26, 82, 56, 6) + r(26, 102, 60, 14, G, 7)
                    + r(140, 12, 112, 58, P, 6) + r(140, 78, 112, 26, LINE, 6) + r(140, 112, 112, 22, A, 6),
        "knowledge": c(133, 44, 20, P) + c(58, 96, 14, A) + c(133, 104, 14, G) + c(208, 96, 14, S)
                     + '<path d="M133 64 L58 82 M133 64 L133 90 M133 64 L208 82" stroke="{}" stroke-width="2" fill="none"/>'.format(MUT)
                     + r(20, 120, 64, 7) + r(101, 120, 64, 7) + r(182, 120, 64, 7),
        "workflow": r(10, 52, 52, 34, LINE, 6) + r(76, 52, 52, 34, P, 6) + r(142, 52, 52, 34, A, 6) + r(208, 52, 48, 34, G, 6)
                    + '<path d="M62 69 h14 M128 69 h14 M194 69 h14" stroke="{}" stroke-width="2"/>'.format(MUT)
                    + r(76, 100, 118, 14, CARD, 7) + r(86, 104, 98, 6, G) + r(10, 22, 246, 8),
    }.get(key, "")
    return ('<svg class="sample-art" viewBox="0 0 266 148" role="img" aria-label="{}" preserveAspectRatio="xMidYMid meet">'
            '<rect width="266" height="148" fill="var(--surface-sunken)"/>{}</svg>').format(e(title + " — concept preview"), art)


SAMPLE_TYPE = {
    "real-client": ("Client project", "बाहरी client के लिए किया गया असली काम, उनकी अनुमति से।"),
    "moodily-internal": ("Moodily का अपना project", "Moodily ने अपने लिए बनाया और खुद चला रहा है।"),
    "self-initiated": ("Self-initiated", "Moodily ने अपनी मर्ज़ी से बनाया — किसी client का काम नहीं।"),
    "concept": ("Concept sample", "यह दिखाने के लिए बनाया गया concept है कि क्या बन सकता है — किसी client का काम नहीं।"),
}
SAMPLE_CATS = collections.OrderedDict([
    ("business", "Business setup"), ("google-business", "Google Business"), ("whatsapp", "WhatsApp"),
    ("website", "Website"), ("catalogue", "Catalogue"), ("design", "Design & print"),
    ("presentation", "PPT / Presentation"), ("invitation", "Invitation"), ("social", "Social / Creator"),
    ("creator", "Creator"), ("education", "Study material"), ("research", "Research"),
    ("knowledge", "Knowledge product"), ("ai", "AI workflow"),
])
SAMPLE_CATALOGUE = [s for s in SAMPLES.values() if s.get("status") == "published" and s.get("slug")]
SAMPLE_BY_SLUG = {s["slug"]: s for s in SAMPLE_CATALOGUE}


def sample_service(smp):
    return SERVICES.get(smp.get("service") or (smp.get("services") or [None])[0])


def sample_visual(smp, lazy=True):
    """Real asset if we have one, otherwise a clearly-labelled inline concept preview."""
    if smp.get("image"):
        return ('<div class="sample-shot"><img src="{}" alt="{}" width="{}" height="{}"{} decoding="async"></div>'.format(
            e(smp["image"]), e(smp["alt"]), smp["width"], smp["height"], ' loading="lazy"' if lazy else ""))
    return '<div class="sample-shot is-concept">{}</div>'.format(_sample_preview(smp.get("preview", ""), smp["catalogue_title"]))


def sample_price_line(smp):
    svc = sample_service(smp)
    if not svc:
        return '<span class="sample-price">Custom quote</span>'
    return '<span class="sample-price">{}</span><span class="small muted">{}</span>'.format(
        e(price_label(svc)), e(PRICE_MODE_SHORT[svc["price_mode"]]))


def customise_href(smp):
    """'Customize this for me' goes straight to the prefilled Google Form when one is configured,
    so the visitor never re-answers what Moodily already knows. Falls back to /contact/ otherwise."""
    svc = sample_service(smp)
    direct = form_prefill_url(svc, sample=smp["catalogue_title"])
    if direct:
        return direct
    return "/contact/?service={}&sample={}".format(svc["id"] if svc else "custom", smp["slug"])


def customise_attrs(smp):
    """An external Form link needs the new-tab treatment and its own event; a fallback does not."""
    return (' target="_blank" rel="noopener" data-track="google_form_open"'
            if customise_href(smp).startswith("http") else ' data-track="customize_sample_click"')


def sample_wa(smp, label="WhatsApp", cls="btn btn-wa btn-sm", track="sample"):
    return wa_button(label, "customer", "{} jaisa kaam (sample: {})".format(smp["catalogue_title"], smp["slug"]),
                     cls=cls, track_label="{}-{}".format(track, smp["slug"]))


def sample_card(smp, lazy=True):
    svc = sample_service(smp)
    label, _ = SAMPLE_TYPE[smp["sample_type"]]
    types = " ".join(smp.get("customer_types", []))
    hay = " ".join([smp["catalogue_title"], smp.get("who", ""), smp.get("solves", ""), smp.get("category", ""),
                    svc["name"] if svc else "", " ".join(smp.get("customer_types", []))]).lower()
    return (
        '<article class="card sample-tile" data-sample="{slug}" data-cat="{cat}" data-types="{types}" data-search="{hay}">'
        '{visual}<span class="badge badge-kind">{label}</span>'
        '<h3><a class="stretched" href="/samples/{slug}/" data-track="sample_card_click" data-label="{slug}">{title}</a></h3>'
        '<p class="sample-who">{who}</p><p class="small muted sample-solves">{solves}</p>'
        '<p class="sample-meta">{price}</p><p class="small muted">{timeline}</p>'
        '<div class="card-actions"><a class="btn btn-primary btn-sm" href="{cust}"{cattrs} data-label="{slug}">इसे मेरे लिए बनाइए</a>'
        '<a class="btn btn-outline btn-sm" href="/samples/{slug}/" data-track="sample_card_click" data-label="view-{slug}">Sample देखें</a></div>'
        '</article>').format(
            slug=smp["slug"], cat=e(smp.get("category", "")), types=e(types), hay=e(hay), visual=sample_visual(smp, lazy),
            label=e(label), title=e(smp["catalogue_title"]), who=e(smp.get("who", "")), solves=e(smp.get("solves", "")),
            price=sample_price_line(smp), timeline=e(svc["timeline"]) if svc else "Scope देखकर", cust=e(customise_href(smp)), cattrs=customise_attrs(smp))


def c_sample_grid(args, ctx):
    """Full catalogue with search + browse-by-need + browse-by-customer-type."""
    items = SAMPLE_CATALOGUE
    if args.get("featured"):
        items = [s for s in items if s.get("featured")]
    limit = int(args.get("limit", "0") or 0)
    if limit:
        items = items[:limit]
    for smp in items:
        svc = sample_service(smp)
        if svc and svc not in ctx["services"]:
            ctx["services"].append(svc)
    # only the catalogue page has tiles above the fold; every embedded strip is below it
    top = 3 if args.get("filters") == "yes" else 0
    cards = "".join(sample_card(s, lazy=(i >= top)) for i, s in enumerate(items))
    if args.get("filters") != "yes":
        return '<div class="sample-grid">{}</div>'.format(cards)
    cats = collections.OrderedDict((k, v) for k, v in SAMPLE_CATS.items() if any(s.get("category") == k for s in items))
    chips = "".join('<button class="chip-btn" type="button" data-filter-cat="{}" aria-pressed="false">{}</button>'.format(k, e(v)) for k, v in cats.items())
    # the emoji is a separate field — the title is already the full label, so never split it
    tchips = "".join('<button class="chip-btn" type="button" data-filter-type="{}" aria-pressed="false">{}{}</button>'.format(
        c["id"], (c["emoji"] + " ") if c.get("emoji") else "", e(c["title"])) for c in ROUTERS["customer_types"])
    return ('<div class="sample-filters">'
            '<label class="sr-only" for="sampleSearch">Sample खोजें</label>'
            '<input id="sampleSearch" class="finder-search" type="search" placeholder="खोजें — catalogue, PPT, invitation, Google, website…" autocomplete="off">'
            '<p class="filter-label" id="fl-need">क्या चाहिए</p><div class="chip-row" role="group" aria-labelledby="fl-need">'
            '<button class="chip-btn" type="button" data-filter-cat="" aria-pressed="true">सभी</button>{chips}</div>'
            '<p class="filter-label" id="fl-who">आप कौन हैं</p><div class="chip-row" role="group" aria-labelledby="fl-who">'
            '<button class="chip-btn" type="button" data-filter-type="" aria-pressed="true">सभी</button>{tchips}</div>'
            '<p class="small muted" data-sample-count aria-live="polite"></p></div>'
            '<div class="sample-grid" data-sample-grid>{cards}</div>'
            '<p class="notice small" data-sample-empty hidden>इस combination में अभी कोई sample नहीं है — '
            '<a href="/contact/?service=custom">अपनी requirement भेजिए</a>, हम scope और quote बनाकर देंगे।</p>').format(
        chips=chips, tchips=tchips, cards=cards)


def c_evidence(args, ctx):
    """Verified India-only numbers, each paired with the action it implies.

    One card = one number + what it measures + what to do about it + the source. Pairing the
    'so what' with the number (instead of a separate block of three) keeps it useful rather than
    reading like a report dump. A card missing source, year or link is a build error.
    """
    means = {m.get("card"): m for m in EVIDENCE["means"] if m.get("card")}
    cards = []
    for cd in EVIDENCE["cards"]:
        for key in ("number", "claim", "source", "year", "url", "context"):
            if not cd.get(key):
                raise SystemExit("evidence.json: {} is missing {} — a number without a checkable source is not published".format(cd.get("id"), key))
        act = means.get(cd["id"])
        action = ""
        if act:
            links = " · ".join('<a href="{}#{}">{}</a>'.format(SERVICES[x]["page"], x, e(SERVICES[x]["name"]))
                               for x in act.get("services", []) if x in SERVICES)
            action = ('<div class="evidence-act"><p class="evidence-act-h">आपको क्या करना चाहिए</p>'
                      '<p>{do}</p><p class="small">{links}</p></div>').format(do=e(act["solution"]), links=links)
        cards.append(
            '<article class="evidence" data-view="evidence_card_view|{id}">'
            '<p class="evidence-num">{num}</p><p class="evidence-claim">{claim}</p>'
            '<p class="evidence-src">{src} · {year} · <a href="{url}" rel="nofollow noopener" target="_blank">source</a></p>'
            '{action}</article>'.format(
                id=cd["id"], num=e(cd["number"]), claim=e(cd["claim"]),
                url=e(cd["url"]), src=e(cd["source"].split(",")[0]), year=e(cd["year"]), action=action))
    note = ('<p class="small muted evidence-note">हर आँकड़ा भारत का है, source और साल के साथ — दूसरे देश का आँकड़ा '
            'भारत के नाम पर नहीं दिखाया जाता। ये आँकड़े बाज़ार के बारे में हैं, किसी एक business के नतीजे की guarantee नहीं। '
            'पिछली जाँच: {}।</p>').format(e(EVIDENCE["last_reviewed"]))
    return '<div class="evidence-grid">{}</div>{}'.format("".join(cards), note)



# ------------------------------------------------- Amazon Associates (inert until configured)
# Nothing here renders an affiliate link, a tag or an earnings claim unless the owner has both
# enabled the programme AND supplied a real Associate tracking ID. A missing tag is a build error
# at the point of use, never a silently broken or untagged link.
def amazon_live():
    """True only when real affiliate links can be emitted."""
    return bool(AMAZON.get("enabled")) and bool(AMAZON.get("tag"))


def amazon_public():
    """True only when Moodily genuinely earns affiliate commission and says so.

    While this is False nothing affiliate-related is published: no /affiliate-disclosure/ page,
    no footer link, no sitemap entry, no disclosure block. A page whose message is "we currently
    earn nothing" is honest but not worth a public route, so it simply is not generated.
    The template and components stay in source, gated — not deleted.
    """
    return amazon_live() and bool(AMAZON.get("disclosure_enabled"))


def amazon_disclosure(inline=False):
    """The required statement. Shown only when affiliate links are actually live on the page."""
    if not amazon_live() or not AMAZON.get("disclosure_enabled"):
        return ""
    if inline:
        return '<p class="affiliate-note small">इस section में कुछ links affiliate links हैं <span class="paid-link">(paid link)</span>. {}</p>'.format(
            e(AMAZON_STATEMENT))
    return ('<aside class="affiliate-disclosure" role="note"><p><strong>Affiliate disclosure.</strong> {} '
            '<a href="/affiliate-disclosure/">पूरी जानकारी</a></p></aside>').format(e(AMAZON_STATEMENT))


AMAZON_STATEMENT = "As an Amazon Associate I earn from qualifying purchases."


def c_affiliate_disclosure(args, ctx):
    """Dormant while the programme is off — renders nothing at all, not a 'we earn nothing' notice."""
    if not amazon_public():
        return ""
    return amazon_disclosure(inline=args.get("inline") == "yes")


def c_amazon_link(args, ctx):
    """A single Special Link. Refuses to render without a real tag — never a fabricated one."""
    name = args.get("name") or ""
    url = args.get("url") or ""
    if not name:
        raise SystemExit("@amazon-link needs a product name in {}".format(ctx["file"]))
    if not amazon_live():
        # Name the product, link nowhere. The page keeps its editorial value with no dead affiliate stub.
        return '<span class="amazon-link is-off">{}</span>'.format(e(name))
    if not url or "amazon." not in url:
        raise SystemExit("@amazon-link for '{}' needs a real amazon.in product URL in {}".format(name, ctx["file"]))
    joiner = "&" if "?" in url else "?"
    href = "{}{}tag={}".format(url, joiner, AMAZON["tag"])
    return ('<a class="amazon-link" href="{href}" rel="nofollow sponsored noopener" target="_blank" '
            'data-track="affiliate_link_click" data-label="{slug}">{name} — Amazon पर आज का price देखें '
            '<span class="paid-link">(paid link)</span></a>').format(
        href=e(href), slug=e(args.get("id") or name.lower().replace(" ", "-")[:40]), name=e(name))


# ------------------------------------------------- Google Form prefill
# The Form's "Service Category" question is a dropdown: Google silently discards any value that is
# not an exact option string. Every mapping is validated against the Form's real option list at
# build time, so a typo fails the build instead of quietly losing the answer.
def form_category_for(svc):
    if not svc:
        return ""
    by_id = INTAKE.get("form_category_by_service_id", {})
    if svc.get("id") in by_id:
        return by_id[svc["id"]]
    by_cat = INTAKE.get("form_category_by_service_category", {})
    if svc.get("category") in by_cat:
        return by_cat[svc["category"]]
    _, intake_cat = intake_service(svc["id"])
    return INTAKE.get("form_category_map", {}).get(intake_cat, "")


def form_prefill_url(svc=None, sample=None, unsure=False):
    """Build a prefilled Form URL. Only fills what Moodily actually knows."""
    base = (svc.get("form_prefill_url") if svc else "") or INTAKE.get("service_prefill_urls", {}).get(
        svc["id"] if svc else "", "") or INTAKE.get("form_url") or ""
    if not base:
        return ""
    ids = {k: v for k, v in INTAKE.get("entry_ids", {}).items() if not k.startswith("_")}
    params = []

    def add(key, value):
        eid = ids.get(key)
        if eid and value:
            params.append("{}={}".format(quote(str(eid), safe=""), quote(str(value), safe="")))
    add("service_category", INTAKE.get("form_category_unsure") if unsure else form_category_for(svc))
    if svc:
        add("sub_service", svc["name"])
    if svc and in_offer(svc) and OFFER_STATE:
        add("offer_code", OFFER["id"])
    if sample:
        add("sample_or_estimate", sample)
    if not params:
        return base
    return "{}?{}".format(base, "&".join(["usp=pp_url"] + params))


FEATURE_GATES = {"amazon_associates": amazon_public}

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
    "packages": c_packages, "sample-grid": c_sample_grid, "evidence": c_evidence, "affiliate-disclosure": c_affiliate_disclosure, "amazon-link": c_amazon_link, "before-after-saathi": c_before_after_saathi, "creates": c_creates, "categories": c_categories, "scorecard": c_scorecard, "promises": c_promises,
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
    ("/services/", "Services", "सेवाएँ"), ("/samples/", "Samples", "Samples"), ("/case-studies/", "Case studies", "काम"),
    ("/insights/", "Insights", "Insights"), ("/learn/", "Learn", "सीखें"), ("/digital-saathi/", "Digital Saathi", "Saathi"),
]
# the inline desktop row stays short so the header never wraps; the rest is in the Menu popover
NAV_DESKTOP = [("/services/", "Services"), ("/samples/", "Samples"), ("/services/#prices", "Pricing"), ("/learn/", "Learn")]
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
    top = "".join('<li><a href="{0}"{1}>{2}</a></li>'.format(h, cur(h.split("#")[0]), e(t)) for h, t in NAV_DESKTOP)
    svc = "".join('<li><a href="{0}"{1}>{2}</a></li>'.format(h, cur(h) if h != "/services/" or route == "/services/" else "", e(t)) for h, t in SERVICE_NAV)
    lang_btn = ('<button class="lang-toggle" type="button" id="langToggle" data-track="language_switch" aria-label="Switch language Hindi/English">हिं / EN</button>'
                if meta.get("bilingual") else "")
    return """<a class="skip" href="#main">Skip to content</a>
<header class="site-header"><div class="container nav">
  <a class="logo" href="/" aria-label="Moodily home"><img src="/assets/img/moodily-mark.svg" alt="" width="28" height="28">Moodily<span class="dot" aria-hidden="true"></span></a>
  <nav aria-label="Primary" class="nav-main">
    <ul class="nav-desktop">{top}</ul>
    <details class="menu" id="siteMenu"><summary aria-haspopup="menu"><span class="burger" aria-hidden="true"></span><span class="menu-label">Menu</span></summary>
      <div class="menu-panel" role="menu" aria-label="Site navigation">
        <button class="menu-close" type="button" data-menu-close aria-label="Menu बंद करें">&times;</button>
        <ul class="nav-links">{links}<li><a href="/services/#prices">Pricing</a></li><li><a href="/tools/"{tools}>Tools</a></li>
          <li><a href="/about/"{about}>About</a></li><li><a href="/contact/"{contact}>Contact</a></li>
          <li><a href="/contact/?service=free-digital-audit" data-track="free_audit_click" data-label="menu-audit">Free Digital Audit</a></li></ul>
        <p class="menu-heading">Services</p><ul class="nav-sub">{svc}</ul>
        <div class="menu-cta"><a class="btn btn-primary btn-sm" href="/contact/" data-track="quote_start" data-label="menu-requirement">Requirement बताएं</a>{menuwa}</div>
      </div>
    </details>
  </nav>
  <div class="nav-actions">{lang}<button class="icon-btn" type="button" id="themeToggle" aria-label="Toggle dark/light theme">◐</button>
    <a class="btn btn-warm btn-sm nav-cta" href="/contact/" data-track="quote_start" data-label="nav-requirement">Requirement बताएं</a></div>
</div></header>""".format(links=links, svc=svc, top=top, lang=lang_btn, about=cur("/about/"), contact=cur("/contact/"), tools=cur("/tools/"),
               menuwa=wa_button("WhatsApp", "customer", "digital help", track_label="menu"))


def footer(route=""):
    plain = route in LEGAL_ROUTES
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
      <li><a href="/privacy/">Privacy</a></li><li><a href="/terms/">Terms</a></li><li><a href="/refund/">Refund policy</a></li>{affiliate}</ul></div>
  </div>
  <p class="footer-note small muted">Moodily curates learning paths using courses offered by recognised providers. Certificates, where applicable, are issued by the respective providers. Moodily has no official partnership with the providers listed unless stated. Some tool links may be affiliate links and are labelled.</p>
  <p class="footer-bottom small muted">© {year} Moodily · moodily.in</p>
</div></footer>
{sticky}""".format(
        email=e(SITE["email"]), svc=svc, year=date.today().year, wa=wa_button("WhatsApp", track_label="footer", cls="btn btn-wa btn-sm"),
        affiliate='<li><a href="/affiliate-disclosure/">Affiliate disclosure</a></li>' if amazon_public() else "",
        sticky="" if plain else STICKY_CTA.format(wa_href=e(wa_href(wa_text())), icon=WA_ICON))


STICKY_CTA = """
<a class="fab-wa" href="{wa_href}" target="_blank" rel="noopener" data-track="whatsapp_click" data-label="floating" aria-label="WhatsApp पर Moodily से बात करें">{icon}<span>WhatsApp</span></a>
<nav class="mobile-cta" aria-label="Quick actions"><a class="btn btn-primary" href="/contact/" data-track="quote_start" data-label="mobile-bar">Requirement बताएं</a><a class="btn btn-wa" href="{wa_href}" target="_blank" rel="noopener" data-track="whatsapp_click" data-label="mobile-bar">{icon} WhatsApp</a></nav>"""


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
           header=header(route, meta), crumbs=breadcrumbs_html(meta), body=body, footer=footer(route), banner=offer_banner(route), byline=byline_html(meta),
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


def sample_page(smp):
    """One reusable template per sample — answers the buyer's questions in a fixed order."""
    svc = sample_service(smp)
    label, label_note = SAMPLE_TYPE[smp["sample_type"]]
    ctx_services = [svc] if svc else []
    rows = [("यह क्या है?", e(smp.get("solves", ""))),
            ("किसके लिए है?", e(smp.get("who", ""))),
            ("Moodily इसमें क्या customize करेगा?",
             '<ul class="ticks small">{}</ul>'.format("".join("<li>{}</li>".format(e(x)) for x in smp.get("customises", [])))),
            ("क्या मिलेगा?", '<ul class="ticks small">{}</ul>'.format(
                "".join("<li>{}</li>".format(e(d)) for d in svc["deliverables"][:5])) if svc else "Scope के अनुसार"),
            ("कौन-से formats?", e(", ".join(FORMATS[f] for f in smp.get("formats", []))) or "Scope तय होने पर"),
            ("Price?", (price_html(svc) + '<span class="small muted">{}</span>'.format(e(PRICE_MODES[svc["price_mode"]]))) if svc else "Custom quote"),
            ("कितना समय?", e(svc["timeline"]) if svc else "Scope देखकर"),
            ("कितने revisions?", e(svc["revisions"]) if svc else "Scope में लिखा जाएगा"),
            ("आपको क्या देना होगा?", e(client_provides(svc)) if svc else "—")]
    dl = "".join('<div><dt>{}</dt><dd>{}</dd></div>'.format(k, v) for k, v in rows if v)

    related = [x for x in SAMPLE_CATALOGUE if x["slug"] != smp["slug"] and
               (x.get("category") == smp.get("category") or set(x.get("customer_types", [])) & set(smp.get("customer_types", [])))][:3]
    rel_html = ('<section class="section" aria-labelledby="rel-h"><div class="section-head"><h2 id="rel-h">मिलते-जुलते samples</h2></div>'
                '<div class="sample-grid sample-grid-3">{}</div></section>'.format("".join(sample_card(x) for x in related))) if related else ""

    case = CASES_BY_SLUG.get(smp.get("case_study") or "")
    case_html = ""
    if case:
        link = ('<a href="/case-studies/{0}/">{1} →</a>'.format(case["slug"], e(case["title"])) if case["status"] == "published"
                else '<a href="/case-studies/#{0}">{1} →</a>'.format(case["slug"], e(case["title"])))
        case_html = ('<p class="notice small"><strong>इससे जुड़ा असली project:</strong> {} '
                     '<span class="muted">Case study = जो काम सच में हुआ। Sample = जो बन सकता है।</span></p>'.format(link))

    svc_html = ('<p class="small">पूरी service और scope: <a href="{}#{}" data-track="service_card_click" data-label="sample-svc-{}">{} →</a></p>'.format(
        svc["page"], svc["id"], smp["slug"], e(svc["name"]))) if svc else ""

    actions = ('<a class="btn btn-primary btn-lg" href="{cust}"{cattrs} data-label="detail-{slug}">इसे मेरे लिए बनाइए</a>'
               '{wa}').format(cust=e(customise_href(smp)), cattrs=customise_attrs(smp), slug=smp["slug"],
                              wa=sample_wa(smp, "WhatsApp पर पूछें", "btn btn-wa btn-lg", "sample-detail"))

    body = """<section class="page-hero"><div class="container"><p class="eyebrow">Sample · {cat}</p>
<h1>{title}</h1><p class="lead">{solves}</p>
<p><span class="badge badge-kind">{label}</span> <span class="small muted">{note}</span></p></div></section>
<div class="container sample-detail">
  <div class="sample-detail-grid">
    <div class="sample-detail-visual">{visual}{fmtnote}</div>
    <div class="sample-detail-body"><h2 class="sample-answers-h">एक नज़र में</h2><dl class="answer-dl">{dl}</dl>{svc}{case}
      <div class="btn-row">{actions}</div>{scope}</div>
  </div>
  {rel}
  <section class="section"><div class="card path-unsure"><div><h3>यह बिल्कुल वैसा नहीं चाहिए?</h3>
    <p class="muted small">Sample सिर्फ़ शुरुआत है। अपनी requirement बताइए — हम scope और quote बनाकर देंगे।</p></div>
    <a class="btn btn-primary" href="/contact/?service={svcid}" data-track="quote_start" data-label="sample-custom-{slug}">अपनी requirement भेजें</a></div></section>
</div>""".format(
        cat=e(SAMPLE_CATS.get(smp.get("category"), "Sample")), title=e(smp["catalogue_title"]), solves=e(smp.get("solves", "")),
        label=e(label), note=e(label_note), visual=sample_visual(smp, lazy=False), dl=dl, svc=svc_html, case=case_html,
        actions=actions, scope=scope_note_html(), rel=rel_html, slug=smp["slug"], svcid=svc["id"] if svc else "custom",
        fmtnote=('<p class="small muted sample-fmt">Formats: {}</p>'.format(e(", ".join(FORMATS[f] for f in smp.get("formats", [])))) if smp.get("formats") else ""))

    price_bit = " — {}".format(price_label(svc)) if svc else ""
    meta = {"title": "{} sample{} | Moodily".format(smp["catalogue_title"], price_bit),
            "description": "{} {} Moodily इसे आपके business के लिए customize करता है — starting price, delivery time और formats साफ़ लिखे हैं।".format(
                smp.get("solves", "")[:110], smp.get("who", "")[:70]),
            "lang": "hi", "breadcrumbs": [["Samples", "/samples/"], [smp["catalogue_title"], "/samples/{}/".format(smp["slug"])]],
            "track_view": ["sample_detail_view", smp["slug"]], "sample": smp["slug"],
            "schema_services": [svc["id"]] if svc else []}
    return meta, body, ctx_services


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
    validate_amazon()
    validate_form_prefill()
    old = set(json.loads(MANIFEST.read_text())) if MANIFEST.exists() else set()
    written, sitemap = [], []

    jobs = []
    for path in sorted((SRC / "pages").rglob("*.html")):
        raw = path.read_text(encoding="utf-8")
        m = META_RE.match(raw)
        if not m:
            raise SystemExit("Missing <!--meta {...} --> block in " + str(path))
        meta = json.loads(m.group(1))
        # Feature-gated pages stay in source but are not generated while their gate is off,
        # so they never reach the sitemap, the footer or an internal link.
        gate = meta.get("gated_on")
        if gate and not FEATURE_GATES[gate]():
            continue
        route, out = route_for(path)
        jobs.append((meta, raw[m.end():], route, out, str(path.relative_to(ROOT))))
    for c in CASES:
        if c["status"] == "published":
            meta, body = case_page(c)
            jobs.append((meta, body, "/case-studies/{}/".format(c["slug"]), ROOT / "case-studies" / c["slug"] / "index.html", "case:" + c["slug"]))
    for smp in SAMPLE_CATALOGUE:
        meta, body, _ = sample_page(smp)
        jobs.append((meta, body, "/samples/{}/".format(smp["slug"]), ROOT / "samples" / smp["slug"] / "index.html", "sample:" + smp["slug"]))

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
        # pages built in Python (not from tokens) name their service so schema still matches what is visible
        for sid in meta.get("schema_services", []):
            if sid in SERVICES and SERVICES[sid] not in ctx["services"]:
                ctx["services"].append(SERVICES[sid])
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
