"""Weekly AI tip rotator (run by .github/workflows/weekly-tip.yml).

Rewrites the AUTO-GENERATED block in src/pages/learn.html; the workflow then runs build.py.
"""
import re
import random
from datetime import date

TARGET = "src/pages/learn.html"

TIPS = [
    {
        "title": "Use voice-to-text to draft LinkedIn posts in half the time",
        "tip": "Speak your first draft instead of typing it; most people talk faster than they type. Clean it up afterward with an AI writing assistant.",
        "cta_text": "Try the Tool →",
        "cta_href": "/tools/#wispr-flow",
    },
    {
        "title": "Summarize any course PDF before you start",
        "tip": "Paste your course notes into NotebookLM first to get a quick summary and question list. It cuts your study time and improves recall.",
        "cta_text": "Explore Tools →",
        "cta_href": "/tools/#notebooklm",
    },
    {
        "title": "Turn one workflow into five with n8n templates",
        "tip": "Most automations you need already exist as a free template. Search the n8n template library before building one from scratch.",
        "cta_text": "See Workflows →",
        "cta_href": "/services/ai-workflows/",
    },
    {
        "title": "Publish your first project this week, not next month",
        "tip": "A small, finished GitHub project beats a big, unfinished one. Ship something small every week and let your portfolio compound.",
        "cta_text": "View Curriculum →",
        "cta_href": "#curriculum",
    },
    {
        "title": "Use Canva Magic Studio for course thumbnails",
        "tip": "A clean visual makes your LinkedIn posts and project write-ups stand out. Magic Studio can generate one in under a minute.",
        "cta_text": "Try the Tool →",
        "cta_href": "/tools/#canva",
    },
]

BLOCK_RE = re.compile(
    r"<!-- AUTO-GENERATED: weekly tip.*?<!-- /AUTO-GENERATED -->",
    re.DOTALL,
)


def build_block():
    tip = random.choice(TIPS)
    week_num = date.today().isocalendar()[1]
    today = date.today().isoformat()
    return (
        f"<!-- AUTO-GENERATED: weekly tip {today} -->\n"
        f"<section id=\"weekly-tip\">\n"
        f"  <div class=\"container\">\n"
        f"    <div class=\"weekly-tip-box\">\n"
        f"      <div>\n"
        f"        <span class=\"badge-teal\">Week {week_num}</span>\n"
        f"        <h2 style=\"margin:12px 0 8px;font-size:1.25rem;\">{tip['title']}</h2>\n"
        f"        <p class=\"muted\" style=\"max-width:560px;\">{tip['tip']}</p>\n"
        f"      </div>\n"
        f"      <a class=\"btn btn-teal\" href=\"{tip['cta_href']}\">{tip['cta_text']}</a>\n"
        f"    </div>\n"
        f"  </div>\n"
        f"</section>\n"
        f"<!-- /AUTO-GENERATED -->"
    )


def main():
    with open(TARGET, "r", encoding="utf-8") as f:
        content = f.read()

    if not BLOCK_RE.search(content):
        raise SystemExit("Could not find AUTO-GENERATED weekly tip block in " + TARGET)

    new_content = BLOCK_RE.sub(build_block(), content, count=1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("Weekly tip block updated.")


if __name__ == "__main__":
    main()
