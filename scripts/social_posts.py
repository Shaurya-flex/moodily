#!/usr/bin/env python3
"""Generate Instagram posts (1080x1350) from the SAME verified data the website publishes.

    python3 scripts/social_posts.py         # writes assets/img/social/*.svg + index.html

Why a generator and not a design file: a number on Instagram and the same number on moodily.in
must be the same number. These posts read src/data/evidence.json and src/data/services.json, so a
stat cannot drift between the site and the feed, and a post cannot carry a figure the site's own
source rules would reject. Prices and deliverables come from services.json for the same reason.

Every statistic post prints its source and year on the card itself. That is the whole strategy:
the competition posts round numbers with no provenance, and a shop owner who has been sold to
before can tell the difference.

Layout note: SVG text does not flow, so every block here is placed from its TOP and reports the
bottom it actually occupies, and the next block starts below that. Devanagari needs much more room
than Latin at the same font-size — the shirorekha and the matras above and below it push the line
box to roughly 1.14x the font-size, which is why ASC/DESC are set the way they are. Laying this out
from baselines instead made consecutive lines overlap by 10-13px, invisible in the source and
obvious on the card.

View: open assets/img/social/index.html.   Verify: node scripts/check_social.mjs
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "img" / "social"
W, H = 1080, 1350
PAD = 76
INNER = W - 2 * PAD

# brand tokens, copied from assets/css/site.css (:root). A standalone SVG cannot read CSS vars.
BG, SURF, TEXT, MUTED = "#f7f6f3", "#ffffff", "#14172a", "#565d75"
LINE, PRIMARY, ACCENT = "#e4e1da", "#5b3fd9", "#d95f1e"
PANEL, OK, BAD = "#1d1a3d", "#12795b", "#b23b2b"
DIM = "#cfcaf0"
FONT = ("'Noto Sans Devanagari','Kohinoor Devanagari','Devanagari Sangam MN',"
        "system-ui,-apple-system,'Segoe UI',Roboto,sans-serif")

ASC, DESC = 0.84, 0.36      # em box above/below baseline, measured from rendered Devanagari
LEAD = 1.46                 # line pitch as a multiple of font-size
# Rough advance width per character, used only to choose line breaks; check_social.mjs measures
# the real boxes afterwards.
CPC_LATIN, CPC_DEVA = 0.52, 0.60


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def is_deva(s):
    return bool(re.search(r"[ऀ-ॿ]", s))


def fits(text, size, width):
    return len(text) * size * (CPC_DEVA if is_deva(text) else CPC_LATIN) <= width


def raw(x, baseline, txt, size, fill, weight, anchor="start"):
    return ('<text x="{}" y="{}" font-size="{}" fill="{}" font-weight="{}" '
            'text-anchor="{}">{}</text>').format(x, baseline, size, fill, weight, anchor, esc(txt))


def line(x, top, txt, size=34, fill=TEXT, weight=400, anchor="start"):
    """One line placed from its top. Returns (svg, bottom)."""
    return raw(x, top + size * ASC, txt, size, fill, weight, anchor), top + size * (ASC + DESC)


def split(txt, size, width):
    words, lines, cur = str(txt).split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and not fits(trial, size, width):
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    # A last line holding one short word reads as a mistake on a card this size. Pull a word down
    # from the line above so the ending has some weight, unless that would overflow.
    if len(lines) > 1 and len(lines[-1].split()) == 1 and len(lines[-1]) < 12:
        head = lines[-2].split()
        if len(head) > 1:
            moved = " ".join(head[-1:] + [lines[-1]])
            if fits(moved, size, width):
                lines[-2] = " ".join(head[:-1])
                lines[-1] = moved
    return lines or [""]


def block(x, top, txt, size, fill=TEXT, weight=400, width=INNER, anchor="start"):
    """Wrapped paragraph placed from its top. Returns (svg, bottom)."""
    lines = split(txt, size, width)
    svg = "".join(raw(x, top + size * ASC + i * size * LEAD, ln, size, fill, weight, anchor)
                  for i, ln in enumerate(lines))
    return svg, top + size * ASC + (len(lines) - 1) * size * LEAD + size * DESC


def fit_block(x, top, txt, sizes, fill, weight, max_lines, width=INNER):
    """Step down through `sizes` until the text fits in max_lines, then place it."""
    for size in sizes:
        if len(split(txt, size, width)) <= max_lines:
            return block(x, top, txt, size, fill, weight, width)
    return block(x, top, txt, sizes[-1], fill, weight, width)


def spread(top, heights, end, lo, hi):
    """Pitch for a list that starts at `top` and should finish by `end`. Returns the gap to leave
    between items, clamped: too little room and the list simply runs longer than `end`, which the
    callers absorb by shrinking the note box underneath."""
    n = len(heights)
    if n < 2:
        return lo
    budget = end - top - sum(heights)
    return max(lo, min(hi, budget / (n - 1)))


def note_box(top, end, text, size, fill, width):
    """A tinted box pinned above the footer. `top` is clamped so its text always clears FOOT_TOP."""
    top = min(top, end - 76)
    svg = rect(PAD, top, INNER, end - top - 10, fill[0], 20)
    body, bottom = block(PAD + 34, top + 24, text, size, fill[1], 600, width)
    return svg + body, bottom


def rect(x, y, w, h, fill, rad=0, stroke=None, sw=2):
    st = ' stroke="{}" stroke-width="{}"'.format(stroke, sw) if stroke else ""
    return '<rect x="{}" y="{}" width="{}" height="{}" rx="{}" fill="{}"{}/>'.format(
        x, y, w, h, rad, fill, st)


def shell(body, bg=BG, title=""):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            'font-family="{f}"><title>{ti}</title>{bgr}{b}</svg>').format(
        w=W, h=H, f=FONT, ti=esc(title), bgr=rect(0, 0, W, H, bg), b=body)


def brandbar(top=56, on_dark=False):
    c = "#ffffff" if on_dark else TEXT
    s1, b = line(PAD, top, "moodily", 40, c, 800)
    s2, _ = line(PAD + 192, top + 8, "moodily.in", 26, DIM if on_dark else MUTED)
    dot = '<circle cx="{}" cy="{}" r="7" fill="{}"/>'.format(PAD + 172, top + 18, ACCENT)
    return s1 + dot + s2, b


def footer(cta="मुफ़्त Digital Audit — WhatsApp पर", on_dark=False):
    """Pinned to the bottom. Everything above must finish before FOOT_TOP."""
    c = "#ffffff" if on_dark else TEXT
    sub = DIM if on_dark else MUTED
    svg = rect(PAD, H - 210, INNER, 2, "#ffffff22" if on_dark else LINE)
    s, _ = line(PAD, H - 176, cta, 36, c, 700)
    svg += s
    s, _ = line(PAD, H - 118, "Google · WhatsApp · Website · Catalogue — साफ़ price, लिखित scope",
                25, sub)
    return svg + s


FOOT_TOP = H - 300          # last y any content block may occupy


def source_line(src, year, on_dark=False):
    """Printed on the card, never in the caption alone. A number without its source is exactly
    what the site's evidence registry refuses to publish."""
    s, _ = line(PAD, FOOT_TOP + 28, "Source: {} · {}".format(src.split(",")[0].strip(), year),
                23, DIM if on_dark else MUTED)
    return s


def short(deliverable, limit=70):
    """A deliverable trimmed to fit a card. The words stay the registry's own — this only drops a
    trailing clause, and only when the line is too long to sit on the card in two lines. Cutting
    at the dash unconditionally was worse: for several services the substance is after the dash
    ("Labels — New enquiry, Order, Paid, Follow-up")."""
    d = deliverable.strip()
    if len(d) <= limit:
        return d
    for sep in (" — ", " ("):
        head = d.split(sep)[0].strip().rstrip(" ,;")
        if len(head) >= 28:
            return head
    return d[:limit].rsplit(" ", 1)[0].rstrip(" ,;") + "…"


# --------------------------------------------------------------------------- post types

def stat_post(card, implication, filename):
    """A verified number, what it costs the reader, and where it came from."""
    body, y = brandbar()
    s, y = line(PAD, y + 76, "आपका ग्राहक कहाँ है", 28, ACCENT, 700)
    body += s
    num = card["number"]
    s, y = line(PAD, y + 34, num, 150 if len(num) <= 5 else 112, PRIMARY, 800)
    body += s
    s, y = fit_block(PAD, y + 20, card["claim"], [46, 42, 38, 34], TEXT, 700, 3)
    body += s
    s, y = block(PAD, y + 34, card["context"], 29, MUTED)
    body += s
    body += rect(PAD, y + 44, INNER, 5, ACCENT)
    s, y = fit_block(PAD, y + 88, implication, [38, 35, 32, 29], TEXT, 600, 3)
    body += s
    assert y < FOOT_TOP, (filename, y)
    body += source_line(card["source"], card["year"]) + footer()
    return filename, shell(body, title="{} — {}".format(num, card["claim"][:60]))


def service_post(svc, filename, note, count=5):
    """What you actually get for a fixed price. No 'starting from', no asterisk."""
    body = rect(0, 0, W, 308, PANEL)
    bar, _ = brandbar(on_dark=True)
    body += bar
    s, y = line(PAD, 150, svc["name"], 52, "#ffffff", 800)
    body += s
    s, _ = line(PAD, y + 10, "Fixed price · scope लिखित में", 28, DIM)
    body += s
    body += rect(W - PAD - 232, 158, 232, 94, ACCENT, 47)
    s, _ = line(W - PAD - 116, 182, "₹{:,}".format(svc["price_from"]), 50, "#ffffff", 800, "middle")
    body += s
    # Lay the bullets out once to measure them, then spread the leftover room evenly between
    # them rather than leaving a dead gap above the note box.
    items = [short(d) for d in svc["deliverables"][:count]]
    top0, note_h = 404, 150
    heights = [block(0, 0, it, 33, TEXT, 400, INNER - 56)[1] for it in items]
    gap = spread(top0, heights, FOOT_TOP - note_h - 56, 26, 54)
    y = top0
    for it in items:
        body += '<circle cx="{}" cy="{}" r="9" fill="{}"/>'.format(PAD + 16, y + 20, OK)
        s, y = block(PAD + 56, y, it, 33, TEXT, 400, INNER - 56)
        body += s
        y += gap
    s, end = note_box(max(y - gap + 56, FOOT_TOP - note_h), FOOT_TOP, note, 27,
                      ("#fdf0e7", "#8a3c12"), INNER - 68)
    body += s
    assert end < FOOT_TOP, (filename, end)
    body += footer()
    return filename, shell(body, title="{} — ₹{}".format(svc["name"], svc["price_from"]))


def compare_post(price, filename):
    """The same shop, found and not found. The only honest before/after is the listing itself —
    not a results graph we cannot verify."""
    body, y = brandbar()
    s, y = fit_block(PAD, y + 70, "एक ही दुकान. दो नतीजे.", [64, 56], TEXT, 800, 2)
    body += s
    s, y = line(PAD, y + 28, "फ़र्क़ सिर्फ़ इतना — Google पर जानकारी पूरी है या नहीं।", 30, MUTED)
    body += s
    cy = y + 56
    # Split whatever vertical room is left between the two cards, so the pair always reaches the
    # footer rule instead of floating with a dead band underneath.
    slack = max(0, (FOOT_TOP - 12) - (cy + 272 + 28 + 334))
    h1, h2 = 272 + slack * 0.42, 334 + slack * 0.58
    pitch = 54 + slack * 0.09
    body += rect(PAD, cy, INNER, round(h1), SURF, 24, LINE)
    s, _ = line(PAD + 40, cy + 34, "✕  अधूरी listing", 37, BAD, 700)
    body += s
    for i, ln in enumerate(["समय नहीं लिखा · फ़ोटो पुरानी", "नंबर बदल गया · रास्ता गलत",
                            "ग्राहक अगली दुकान पर चला जाता है"]):
        s, _ = line(PAD + 40, cy + 104 + i * pitch, ln, 30, MUTED)
        body += s
    cy += h1 + 28
    body += rect(PAD, cy, INNER, round(h2), SURF, 24, PRIMARY)
    s, _ = line(PAD + 40, cy + 34, "✓  पूरी listing", 37, OK, 700)
    body += s
    for i, ln in enumerate(["समय, फ़ोटो, services, रास्ता", "Call · Directions · WhatsApp एक tap पर",
                            "ग्राहक आने से पहले ही भरोसा"]):
        s, _ = line(PAD + 40, cy + 104 + i * pitch, ln, 30, TEXT)
        body += s
    body += rect(PAD + 40, cy + h2 - 80, 258, 56, PRIMARY, 28)
    s, _ = line(PAD + 169, cy + h2 - 68, "₹{:,} में".format(price), 30, "#ffffff", 700, "middle")
    body += s
    assert cy + h2 < FOOT_TOP + 20, (filename, cy + h2)
    body += footer()
    return filename, shell(body, title="अधूरी बनाम पूरी Google listing")


def honesty_post(filename):
    """Publishing the unflattering half of the same survey is the most persuasive thing on the
    site. It is also the only honest way to say: do not buy fake reviews."""
    bar, y = brandbar(on_dark=True)
    body = bar
    s, y = fit_block(PAD, y + 76, "हम आपको आधी तस्वीर नहीं दिखाएँगे",
                     [56, 50, 44], "#ffffff", 800, 3)
    body += s
    s, y = line(PAD, y + 40, "3%", 140, ACCENT, 800)
    body += s
    s, y = fit_block(PAD, y + 12, "भारतीयों को ही Google reviews पर ऊँचा भरोसा है।",
                     [42, 38], "#ffffff", 700, 3)
    body += s
    s, y = block(PAD, y + 34,
                 "45% को लगता है reviews सही नहीं होतीं, 37% को लगता है वे positively biased हैं।",
                 29, DIM)
    body += s
    body += rect(PAD, y + 44, INNER, 5, ACCENT)
    s, y = fit_block(PAD, y + 92,
                     "इसलिए नकली review का कोई फ़ायदा नहीं। असली, पूरी और अपडेटेड जानकारी ही "
                     "भरोसा बनाती है।", [36, 33, 30], "#ffffff", 600, 4)
    body += s
    assert y < FOOT_TOP, (filename, y)
    body += source_line("LocalCircles", "2022 · 56,000+ जवाब, 357 ज़िले", on_dark=True)
    body += footer(on_dark=True)
    return filename, shell(body, bg=PANEL, title="केवल 3% को Google reviews पर ऊँचा भरोसा")


def audit_post(filename):
    body, y = brandbar()
    s, y = fit_block(PAD, y + 70, "पहले मुफ़्त Digital Audit. फिर आप तय कीजिए.",
                     [60, 54, 48], TEXT, 800, 3)
    body += s
    s, y = block(PAD, y + 30, "हम आपका Google, WhatsApp, website और social देखकर बताते हैं कि "
                              "सबसे पहले क्या ठीक करना चाहिए।", 32, MUTED)
    body += s
    y += 56
    steps = [("1", "आप business बताइए — WhatsApp पर"),
             ("2", "हम जाँच करके 3 सबसे ज़रूरी सुधार बताते हैं"),
             ("3", "हर सुधार पर: ख़ुद कर सकते हैं / हम मदद करें"),
             ("4", "आगे काम करवाना है या नहीं — आपकी मर्ज़ी")]
    note_h = 120
    heights = [max(68, block(0, 0, v, 32, TEXT, 500, INNER - 96)[1]) for _, v in steps]
    gap = spread(y, heights, FOOT_TOP - note_h - 56, 32, 62)
    for k, v in steps:
        body += '<circle cx="{}" cy="{}" r="34" fill="{}"/>'.format(PAD + 34, y + 24, PRIMARY)
        s, _ = line(PAD + 34, y + 6, k, 36, "#ffffff", 800, "middle")
        body += s
        s, y2 = block(PAD + 96, y, v, 32, TEXT, 500, INNER - 96)
        body += s
        y = max(y2, y + 68) + gap
    s, end = note_box(max(y - gap + 56, FOOT_TOP - note_h), FOOT_TOP,
                      "मुफ़्त है. उसके बाद कुछ ख़रीदना ज़रूरी नहीं.", 32, ("#efecfd", PRIMARY),
                      INNER - 68)
    body += s
    assert end < FOOT_TOP, (filename, end)
    body += footer()
    return filename, shell(body, title="मुफ़्त Digital Audit — चार कदम")


def promise_post(filename):
    """The pinned post. What we will not do is more distinctive than what we will."""
    body, y = brandbar()
    s, y = fit_block(PAD, y + 70, "जो हम कभी नहीं करेंगे", [64, 58], TEXT, 800, 2)
    body += s
    s, y = line(PAD, y + 28, "कीमत बताने से पहले यह जान लीजिए।", 30, MUTED)
    body += s
    y += 54
    items = ["Google पर पहले नंबर की guarantee — कोई भी ईमानदार agency नहीं दे सकती",
             "नकली या ख़रीदे हुए reviews",
             "आपके accounts की ownership — वे आपके ही नाम पर रहते हैं",
             "छुपी हुई fees — हर काम का scope और price लिखित में"]
    note_h = 150
    heights = [block(0, 0, it, 33, TEXT, 500, INNER - 62)[1] for it in items]
    gap = spread(y, heights, FOOT_TOP - note_h - 56, 28, 56)
    for ln in items:
        s, _ = line(PAD + 8, y, "✕", 34, BAD, 700)
        body += s
        s, y = block(PAD + 62, y, ln, 33, TEXT, 500, INNER - 62)
        body += s
        y += gap
    s, end = note_box(max(y - gap + 56, FOOT_TOP - note_h), FOOT_TOP,
                      "जो करेंगे: आपकी जानकारी Google, WhatsApp और website पर पूरी, सही और "
                      "अपडेटेड रखना.", 29, ("#eef7f2", OK), INNER - 68)
    body += s
    assert end < FOOT_TOP, (filename, end)
    body += footer()
    return filename, shell(body, title="जो हम कभी नहीं करेंगे")


INDEX = """<!doctype html><html lang="hi"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- This contact sheet is served from the public site but is a working file, not a page:
     keep it out of the index so it never competes with a real page in search. -->
<meta name="robots" content="noindex,nofollow">
<title>Moodily — Instagram posts</title>
<style>
 body{{margin:0;padding:32px;background:#1d1a3d;color:#fff;
      font:16px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}}
 h1{{font-size:24px;margin:0 0 6px}} p{{color:#cfcaf0;margin:0 0 28px;max-width:62ch}}
 code{{background:#ffffff1a;padding:1px 5px;border-radius:4px}}
 .grid{{display:grid;gap:22px;grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}}
 figure{{margin:0}} img{{width:100%;display:block;border-radius:12px;background:#fff}}
 figcaption{{font-size:13px;color:#cfcaf0;padding:8px 2px}}
</style>
<h1>Moodily — Instagram posts (1080×1350)</h1>
<p>Generated by <code>scripts/social_posts.py</code> from the same evidence and pricing registry
the website publishes, so a number here cannot drift from the number on moodily.in. Right-click an
image to save it. Captions and posting order are in <code>_project/29-instagram-launch.md</code>.</p>
<div class="grid">{cards}</div>
</html>
"""


def main():
    ev = json.loads((ROOT / "src/data/evidence.json").read_text(encoding="utf-8"))
    svc = {s["id"]: s for s in json.loads(
        (ROOT / "src/data/services.json").read_text(encoding="utf-8"))["services"]}
    by = {c["id"]: c for c in ev["cards"]}
    OUT.mkdir(parents=True, exist_ok=True)
    posts = [
        promise_post("01-what-we-never-do.svg"),
        stat_post(by["google-connections"],
                  "3.5 करोड़ businesses पहले से वहाँ हैं। सवाल यह है कि आपकी दुकान उनमें है या नहीं।",
                  "02-google-connections.svg"),
        audit_post("03-free-audit.svg"),
        stat_post(by["health-reviews"],
                  "Clinic, dentist या medical store हैं? मरीज़ आने से पहले आपको पढ़ रहा है।",
                  "04-health-reviews.svg"),
        compare_post(svc["google-business-fix"]["price_from"], "05-listing-before-after.svg"),
        service_post(svc["google-business-fix"], "06-google-quick-fix.svg",
                     "Verification Google ख़ुद करता है — उसका समय हम तय नहीं कर सकते, "
                     "और rank की कोई guarantee नहीं देते।"),
        stat_post(by["review-habit"],
                  "वे आपका नंबर ढूँढते-ढूँढते reviews भी पढ़ लेते हैं — एक ही स्क्रीन पर।",
                  "07-review-habit.svg"),
        service_post(svc["whatsapp-business-setup"], "08-whatsapp-basic.svg",
                     "Catalogue, quick replies और QR — ताकि एक ही जवाब बार-बार टाइप न करना पड़े।"),
        honesty_post("09-honest-reviews.svg"),
    ]
    for name, svg in posts:
        (OUT / name).write_text(svg, encoding="utf-8")
    cards = "".join(
        '<figure><img src="{n}" alt=""><figcaption>{n}</figcaption></figure>'.format(n=n)
        for n, _ in posts)
    (OUT / "index.html").write_text(INDEX.format(cards=cards), encoding="utf-8")
    print("wrote {} posts to {}".format(len(posts), OUT.relative_to(ROOT)))


if __name__ == "__main__":
    main()
