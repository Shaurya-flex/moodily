#!/usr/bin/env python3
"""International public-launch gate.

usage: python3 tests/launch_gate.py [browser-results.json]

Static checks on the repository, its history and the generated site, plus the results of
tests/browser_launch_check.mjs (layout, accessibility, analytics privacy). Prints one line per check and
PUBLIC_LAUNCH_ALLOWED = TRUE only when every mandatory check passes. Never prints secret values.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://moodily.in"
checks = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


SECRET_PATTERNS = {
    "Razorpay key id": r"rzp_(live|test)_[A-Za-z0-9]{14}",
    "Stripe secret/restricted key": r"\b(sk|rk)_(live|test)_[A-Za-z0-9]{16,}",
    "Stripe webhook secret": r"\bwhsec_[A-Za-z0-9]{16,}",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "Google API key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{36,}\b",
    "Slack token": r"\bxox[abpors]-[A-Za-z0-9-]{10,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "secret assignment": r"\b[A-Z][A-Z0-9_]*(SECRET|TOKEN|API_KEY|PASSWORD)[A-Z0-9_]*\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}",
    "Razorpay order/payment id": r"\b(order|pay)_[A-Za-z0-9]{14}\b",
}
PLACEHOLDER = re.compile(r"_(X{14}|x{14})$|X{10,}")


FIXTURE = re.compile(r"unit|test|order_ABC|pay_ABC", re.I)


def scan_secrets(text, fixtures_ok=False):
    """fixtures_ok: test files may hold obviously fake values (e.g. a secret named 'unit…test', order_ABC…)."""
    found = []
    for label, pat in SECRET_PATTERNS.items():
        for m in re.finditer(pat, text):
            v = m.group(0)
            if PLACEHOLDER.search(v):
                continue
            if fixtures_ok and label in ("secret assignment", "Razorpay order/payment id") and FIXTURE.search(v.split(":", 1)[-1].split("=", 1)[-1]):
                continue
            found.append(label)
    return found


# 1. secrets — tracked files, generated output, full git history
tracked = [p for p in git("ls-files").split("\n") if p]
hits = {}
for rel in tracked:
    f = ROOT / rel
    if f.suffix.lower() in (".png", ".webp", ".jpg", ".jpeg", ".ico", ".pdf", ".mp4", ".woff", ".woff2") or not f.is_file():
        continue
    try:
        found = scan_secrets(f.read_text(encoding="utf-8", errors="ignore"), fixtures_ok=rel.startswith("tests/"))
    except OSError:
        continue
    if found:
        hits[rel] = sorted(set(found))
check("no secrets in tracked files", not hits, "; ".join("{}: {}".format(k, ", ".join(v)) for k, v in hits.items()))
history = git("log", "--all", "-p", "--no-color")
hist_hits = []
for chunk in re.split(r"(?m)^diff --git ", history):
    path = chunk.split(" ", 1)[0][2:] if chunk.startswith("a/") else ""
    hist_hits += scan_secrets(chunk, fixtures_ok=path.startswith("tests/"))
hist_hits = sorted(set(hist_hits))
check("no secrets in git history", not hist_hits, ", ".join(hist_hits))
# strongest check (local only): real values from a .env must not appear in any tracked file or in history
env_file = Path(__import__("os").environ.get("MOODILY_ENV_FILE", ROOT / ".env"))
if env_file.exists():
    values = [l.split("=", 1)[1].strip().strip('"') for l in env_file.read_text().splitlines() if "=" in l and not l.startswith("#")]
    values = [v for v in values if len(v) >= 8]
    tracked_text = "".join((ROOT / p).read_text(encoding="utf-8", errors="ignore") for p in git("ls-files").split()
                           if (ROOT / p).is_file() and not p.endswith((".png", ".webp", ".jpg", ".ico")))
    exposed = sum(1 for v in values if v in history or v in tracked_text)
    check("real .env values absent from repo and history", exposed == 0, "{} value(s) exposed — rotate before launch".format(exposed))
env_tracked = [p for p in tracked if re.search(r"(^|/)\.env(\.|$)", p) and not p.endswith(".env.example")]
env_hist = git("log", "--all", "--format=%h", "--", ".env", ".env.local", ".env.production").strip()
ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
check(".env ignored and never committed", ignored and not env_tracked and not env_hist)

# 2. private material is not tracked or served
PRIVATE_DIRS = [d.strip() for d in __import__("os").environ.get("MOODILY_PRIVATE_DIRS", "").split(",") if d.strip()]
private_paths = [p for p in tracked if any(p == d or p.startswith(d.rstrip("/") + "/") for d in PRIVATE_DIRS)]
check("no private folders tracked", not private_paths, ", ".join(private_paths[:10]))
excluded_dirs = ("src/", "tests/", "scripts/", "worker/", "_project/", ".github/", "private/")
served_docs = [p for p in tracked if p.lower().endswith((".md", ".csv", ".diff", ".patch", ".log")) and not p.startswith(excluded_dirs)
               and p not in ("README.md",) and not Path(p).name.startswith(("_", "."))]
check("no planning docs served by the site", not served_docs, ", ".join(served_docs))

# 3. generated public output — leakage and internal wording
manifest = json.loads((ROOT / ".build-manifest.json").read_text())
public_files = manifest + [str(p.relative_to(ROOT)) for p in (ROOT / "assets").rglob("*") if p.is_file() and p.suffix in (".js", ".css", ".json", ".svg")] + ["robots.txt", "sitemap.xml"]
LEAK = re.compile(r"/Users/|~/|localhost|127\.0\.0\.1|:\d{4}/|\b[\w-]+\.(md|csv|diff|patch)\b|\b[A-Z]+_[A-Z_]+\.md\b|feature/|fix/")
leaks = {}
for rel in public_files:
    t = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
    m = LEAK.search(t)
    if m:
        leaks[rel] = m.group(0)
check("no local paths / private names in public files", not leaks, "; ".join("{}: {}".format(k, v) for k, v in list(leaks.items())[:10]))

intl_pages = [p for p in manifest if p.startswith("international/")]
ALLOWED_CONTEXT = ["loss of business or profit"]
INTERNAL = re.compile(r"\b(owner (approval|input|blocker|to confirm)|hypothes\w*|draft price|internal(ly)?|margin|profit\w*|lead score|prospect\w*|"
                      r"roadmap|worktree|approval required|test key|api key|secret)\b", re.I)
internal_hits = {}
for rel in intl_pages:
    text = (ROOT / rel).read_text(encoding="utf-8")
    visible = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", "", text, flags=re.S))
    for ok_phrase in ALLOWED_CONTEXT:  # inspected manually: legitimate client-facing wording
        visible = visible.replace(ok_phrase, " ")
    found = sorted(set(m.group(0).lower() for m in INTERNAL.finditer(visible)))
    if found:
        internal_hits[rel] = found
check("no internal/strategy wording on International pages", not internal_hits, "; ".join("{}: {}".format(k, v) for k, v in internal_hits.items()))

# 4. data rules
intl = json.loads((ROOT / "src/data/international.json").read_text(encoding="utf-8"))
site = json.loads((ROOT / "src/site.json").read_text(encoding="utf-8"))
check("launch mode is public", intl["launch"]["mode"] == "public")
check("all published prices approved, USD", all(s["price"].get("approved") and s["price"]["currency"] == "USD" for s in intl["services"]))
f = intl["founder"]
check("founder identity complete (name, role, bio)", all(f.get(k) for k in ("name", "role", "bio")))
labels_ok = all(it["label"] in intl["portfolio_labels"] and (it["label"] != "concept" or "concept" in it["outcome"].lower()) for it in intl["portfolio"])
check("portfolio labels truthful", labels_ok)
flags = {k: v for k, v in site["payment_flags"].items() if not k.startswith("_")}
needed = {"wise_enabled", "paypal_enabled", "stripe_enabled", "razorpay_india_enabled", "razorpay_international_enabled", "lemon_squeezy_store_enabled"}
check("payment flags present", needed <= set(flags), ", ".join(sorted(needed - set(flags))))
bad_methods = [m["id"] for m in intl["payment_methods"] if flags.get(m["flag"]) and not m.get("details_confirmed")]
check("enabled payment methods are confirmed", not bad_methods, ", ".join(bad_methods))
pay_markup = [rel for rel in intl_pages if re.search(r"data-checkout|data-pay=|rzp\.io|lemonsqueezy\.com/checkout|checkout\.stripe|paypal\.com/(checkoutnow|invoice)",
                                                       (ROOT / rel).read_text(encoding="utf-8"))]
active = [m for m in intl["payment_methods"] if flags.get(m["flag"]) and m.get("details_confirmed")]
check("payment buttons match verified rails", not pay_markup or active, ", ".join(pay_markup))
js = "".join((ROOT / "assets/js" / n).read_text(encoding="utf-8") for n in ("site.js", "intl.js"))
check("payment success never trusted from URL", not re.search(r"(status|payment)\s*[=:]\s*['\"]?(paid|success)", js, re.I))

# 5. pages, policies, contact, SEO
need = ["international/{}index.html".format(p) for p in ("", "services/", "pricing/", "process/", "industries/", "customer-education/", "work/",
                                                          "about/", "contact/", "privacy/", "terms/", "refund/", "payments/", "pay/")]
missing = [p for p in need if p not in manifest]
check("required International pages built", not missing, ", ".join(missing))
pol_ok = all('lang="en"' in (ROOT / "international" / p / "index.html").read_text(encoding="utf-8") for p in ("privacy", "terms", "refund", "payments"))
check("English policies available", pol_ok)
contact = (ROOT / "international/contact/index.html").read_text(encoding="utf-8")
check("contact route valid (form + email)", 'id="intlIntake"' in contact and "mailto:" in contact)
sitemap = (ROOT / "sitemap.xml").read_text()
in_map = set(re.findall(r"<loc>{}(/international/[^<]*)</loc>".format(re.escape(BASE)), sitemap))
expected = {"/" + p[: -len("index.html")] for p in need if "pay/" not in p}
check("sitemap lists public International pages", expected <= in_map, ", ".join(sorted(expected - in_map)))
check("sitemap excludes payment page", "/international/pay/" not in in_map)
canon_bad = []
for p in need:
    t = (ROOT / p).read_text(encoding="utf-8")
    route = "/" + p[: -len("index.html")]
    if '<link rel="canonical" href="{}{}">'.format(BASE, route) not in t:
        canon_bad.append(route)
    if ("noindex" in t) != (route == "/international/pay/"):
        canon_bad.append(route + " (robots)")
check("canonical + robots meta correct", not canon_bad, ", ".join(canon_bad))
robots = (ROOT / "robots.txt").read_text()
check("robots.txt correct", "Disallow: /international/pay/" in robots and "Sitemap: {}/sitemap.xml".format(BASE) in robots and "Disallow: /\n" not in robots)

# 6. browser results
if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
    b = json.loads(Path(sys.argv[1]).read_text())
    layout_bad = [r for r in b["pages"] if r["overflow"] or r["brokenImgs"] or r["emptyLinks"] or r["consoleErrors"] or r["h1"] != 1]
    check("mobile/tablet/desktop layout (1440/768/390/375)", not layout_bad,
          "; ".join("{} {}".format(r["page"], r["viewport"]) for r in layout_bad[:8]))
    check("no preview text in browser", not [r for r in b["pages"] if r["preview"]])
    a11y_bad = [r for r in b["a11y"] if r["violations"]]
    check("accessibility (axe serious/critical = 0)", not a11y_bad,
          "; ".join("{}: {}".format(r["page"], ",".join(v["id"] for v in r["violations"])) for r in a11y_bad))
    priv_bad = [r["test"] for r in b["privacy"] if r.get("dataLayerLeak") or r.get("storageLeak") or r.get("cookieLeak")
                or r.get("urlLeak") or r.get("networkLeak") or r.get("gtmLoaded")]
    check("analytics PII tests (form, WhatsApp, payment success, pay page)", not priv_bad and len(b["privacy"]) >= 5, ", ".join(priv_bad))
else:
    check("browser checks supplied", False, "run tests/browser_launch_check.mjs and pass its JSON")

width = max(len(c[0]) for c in checks)
for name, ok, detail in checks:
    print("{}  {}{}".format("PASS" if ok else "FAIL", name.ljust(width), ("  — " + detail) if detail and not ok else ""))
allowed = all(ok for _, ok, _ in checks)
print("\nPUBLIC_LAUNCH_ALLOWED = {}".format("TRUE" if allowed else "FALSE"))
sys.exit(0 if allowed else 1)
