"""
format_post.py — Formats papers_relevant.json into a Teams post and checked_until update.
Outputs: teams_post.md, checked_until_update.txt, last_seen.md
"""

import json
import sys
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Ordered list of all sources (display name -> state.json key)
SOURCE_MAP = {
    "NBER": "nber",
    "IZA": "iza",
    "CESifo": "cesifo",
    "IFS": "ifs",
    "CRR": "crr",
}

SOURCE_KEY_TO_DISPLAY = {v: k for k, v in SOURCE_MAP.items()}


def format_teams_post(papers: list[dict], manual_sources: list[str] = None) -> str:
    lines = []

    if manual_sources:
        lines.append("*Sources checked manually this round:*")
        for src in manual_sources:
            lines.append(f"- {src}")
        lines.append("")
        lines.append("---")
        lines.append("")

    if not papers:
        lines.append("_No new relevant papers found this fortnight._")
        return "\n".join(lines)

    for p in papers:
        title = p.get("title", "Untitled").strip()
        url = p.get("url", "").strip()
        authors = p.get("authors", "").strip()
        abstract = p.get("abstract", "").strip()

        if url:
            lines.append(f"[{title}]({url}) ({authors})")
        else:
            lines.append(f"{title} ({authors})")

        lines.append("")
        lines.append(abstract)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip()


def format_last_seen(papers_raw: list[dict]) -> str:
    """Most recently published paper found per source (first in papers_raw)."""
    first_by_source: dict[str, dict] = {}
    for p in papers_raw:
        src = p["source"]
        if src not in first_by_source:
            first_by_source[src] = p

    if not first_by_source:
        return "_No papers scraped this run._"

    lines = ["**Most recent paper per source (as of this check):**", ""]
    for display_name in SOURCE_MAP:
        p = first_by_source.get(display_name)
        if p:
            title = p.get("title", "Untitled").strip()
            url = p.get("url", "").strip()
            authors = p.get("authors", "").strip()
            entry = f"[{title}]({url})" if url else title
            if authors:
                entry += f" ({authors})"
            lines.append(f"- **{display_name}**: {entry}")
    return "\n".join(lines)


def format_checked_until(state: dict, papers_raw: list[dict]) -> str:
    """New checked_until values based on the most recent paper per source."""
    today = date.today().isoformat()

    first_by_source: dict[str, str] = {}
    for p in papers_raw:
        src = p["source"]
        if src not in first_by_source:
            first_by_source[src] = p["url"]

    lines = [f"checked until ({today}):"]
    for display_name, key in SOURCE_MAP.items():
        old_url = state["sources"].get(key, {}).get("checked_until_url", "")
        new_url = first_by_source.get(display_name, old_url)
        short = new_url[:80] + "\u2026" if len(new_url) > 80 else new_url
        lines.append(f"- {display_name}: {short}")

    return "\n".join(lines)


def main():
    import os

    with open("papers_relevant.json", encoding="utf-8") as f:
        papers = json.load(f)

    with open("papers_raw.json", encoding="utf-8") as f:
        papers_raw = json.load(f)

    with open("state.json", encoding="utf-8") as f:
        state = json.load(f)

    # Determine which sources need manual checking
    if os.path.exists("scrape_summary.json"):
        with open("scrape_summary.json", encoding="utf-8") as f:
            scrape_summary = json.load(f)
        manual = sorted(
            SOURCE_KEY_TO_DISPLAY[key]
            for key, status in scrape_summary.items()
            if status != "ok" and key in SOURCE_KEY_TO_DISPLAY
        )
    else:
        scraped_sources = {p["source"] for p in papers_raw}
        all_sources = set(SOURCE_MAP.keys())
        manual = sorted(all_sources - scraped_sources)

    post = format_teams_post(papers, manual_sources=manual if manual else None)
    checked_until = format_checked_until(state, papers_raw)
    last_seen = format_last_seen(papers_raw)

    post += "\n\n---\n\n" + checked_until

    with open("teams_post.md", "w", encoding="utf-8") as f:
        f.write(post)

    with open("checked_until_update.txt", "w", encoding="utf-8") as f:
        f.write(checked_until)

    with open("last_seen.md", "w", encoding="utf-8") as f:
        f.write(last_seen)

    print("=" * 60)
    print("TEAMS POST:")
    print("=" * 60)
    print(post)
    print()
    print("=" * 60)
    print("LAST SEEN (most recent paper per source):")
    print("=" * 60)
    print(last_seen)
    print()
    print("=" * 60)
    print("CHECKED UNTIL REPLY:")
    print("=" * 60)
    print(checked_until)
    print()
    print("Files saved: teams_post.md, last_seen.md, checked_until_update.txt")


if __name__ == "__main__":
    main()
