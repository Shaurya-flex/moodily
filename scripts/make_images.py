#!/usr/bin/env python3
"""Generates brand raster images (logo PNG for Organization schema, OG share image). Requires Pillow.
Run once after brand changes:  python3 scripts/make_images.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "assets" / "img"
OUT.mkdir(parents=True, exist_ok=True)
VIOLET, SAFFRON, BG, WHITE, MUTED = (123, 47, 255), (255, 107, 53), (10, 11, 15), (241, 241, 241), (163, 168, 191)
FONT_CANDIDATES = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font(size):
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def mark(draw, x, y, s):
    """Rounded violet square with a white 'M' and saffron dot — mirrors moodily-mark.svg."""
    draw.rounded_rectangle([x, y, x + s, y + s], radius=int(s * 0.22), fill=VIOLET)
    f = font(int(s * 0.62))
    bbox = draw.textbbox((0, 0), "M", font=f)
    draw.text((x + (s - (bbox[2] - bbox[0])) / 2 - bbox[0], y + (s - (bbox[3] - bbox[1])) / 2 - bbox[1] - s * 0.03), "M", font=f, fill=WHITE)
    r = s * 0.09
    draw.ellipse([x + s * 0.74 - r, y + s * 0.78 - r, x + s * 0.74 + r, y + s * 0.78 + r], fill=SAFFRON)


logo = Image.new("RGB", (512, 512), BG)
mark(ImageDraw.Draw(logo), 56, 56, 400)
logo.save(OUT / "moodily-logo-512.png", optimize=True)

og = Image.new("RGB", (1200, 630), BG)
d = ImageDraw.Draw(og)
for i in range(630):
    d.line([(0, i), (1200, i)], fill=(10 + int(i * 0.02), 11, 15 + int(i * 0.05)))
mark(d, 80, 80, 120)
d.text((230, 98), "Moodily", font=font(84), fill=WHITE)
d.ellipse([588, 168, 604, 184], fill=SAFFRON)
d.text((80, 280), "Learn · Build · Digitize · Sell · Grow", font=font(56), fill=WHITE)
d.text((80, 370), "Digital Saathi · Intelligence Studio · Free AI Learning", font=font(34), fill=MUTED)
d.text((80, 520), "moodily.in", font=font(38), fill=SAFFRON)
og.save(OUT / "og-moodily.png", optimize=True)
print("wrote", OUT / "moodily-logo-512.png", OUT / "og-moodily.png")
