#!/usr/bin/env python3
"""Refuse to let a Razorpay credential or a .env file into git.

    python3 scripts/secret_scan.py            # scan every tracked file   (CI)
    python3 scripts/secret_scan.py --staged   # scan what is about to be committed (pre-commit hook)

Reports only the file and line — never the matched value, so the scan itself cannot leak a secret
into a terminal, a CI log or a screenshot.
"""
import re
import subprocess
import sys

# A real key id is rzp_live_/rzp_test_ + 14 alphanumerics. Placeholders (rzp_live_XXXX…, rzp_test_YOUR_KEY_ID)
# are deliberately not matched.
KEY_ID = re.compile(r"rzp_(?:live|test)_(?!X+\b)[A-Za-z0-9]{14}\b")
# A secret assignment with a real-looking value (not "replace_me" / empty / a ${VAR} reference).
SECRET = re.compile(r"RAZORPAY_KEY_SECRET\s*[=:]\s*[\"']?(?!replace_me|your_|\$\{|<)[A-Za-z0-9]{16,}")
# .env, .env.local, .env.production … and .dev.vars (Wrangler's local secrets file)
ENV_FILE = re.compile(r"(^|/)(\.env(\.[^/]*)?|\.dev\.vars)$")
ALLOWED_ENV = {".env.example"}


def git(*args):
    return subprocess.run(("git",) + args, capture_output=True, text=True, check=True).stdout


def main():
    staged = "--staged" in sys.argv
    files = [f for f in (git("diff", "--cached", "--name-only", "--diff-filter=ACMR") if staged else git("ls-files")).splitlines() if f]
    problems = []
    for f in files:
        if ENV_FILE.search(f) and f.split("/")[-1] not in ALLOWED_ENV:
            problems.append("{}: secret files (.env*, .dev.vars) must never be committed".format(f))
            continue
        try:
            text = git("show", ":" + f) if staged else open(f, encoding="utf-8", errors="ignore").read()
        except (subprocess.CalledProcessError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if KEY_ID.search(line):
                problems.append("{}:{}: looks like a Razorpay key id".format(f, n))
            if SECRET.search(line):
                problems.append("{}:{}: looks like a Razorpay key secret".format(f, n))
    if problems:
        print("Blocked — possible Razorpay credential:\n  " + "\n  ".join(problems))
        print("Keys belong in the gitignored .env (local) or in Cloudflare Worker secrets (production).")
        return 1
    print("secret scan: clean ({} files)".format(len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
