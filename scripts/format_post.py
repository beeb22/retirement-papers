"""
format_post.py — Formats papers_relevant.json into a Teams post and checked_until update.
Outputs: teams_post.md, checked_until_update.txt
"""

import json
import sys
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


MANUAL_CHECK_URLS = {
    "NBER": "https://www.nber.org/papers",
}

SOURCE_KEY_TO_DISPLAY = {
    "iza": "IZA",
    "crr": "CRR",
    "nber": "NBER",
}


def format_teams_post(papers: list[dict], manual_sources: list[str] = None) -> str:
    lines = []

    if manual_sources:
        lines.append("*Sources checked manually this round:*")
        for src in manual_sources:
            url = MANUAL_CHECK_URLS.get(src, "")
            lines.append(f"- [{src}]({url})" if url else f"- {src}")
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

        # Title as hyperlink, authors in plain text
        if url:
            lines.append(f"[{title}]({url}) ({authors})")
        else:
            lines.append(f"{title} ({authors})")

        lines.append("")  # blank line before abstract
        lines.append(abstract)
        lines.append("")  # blank line between papers
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip()


def format_last_seen(papers_raw: list[dict]) -> str:
    """
    Produces a 'last seen' summary: the most recently published paper found per
    automated source (= first paper in papers_raw, since scraping is newest-first).
    """
    first_by_source: dict[str, dict] = {}
    for p in papers_raw:
        src = p["source"]
        if src not in first_by_source:
            first_by_source[src] = p

    if not first_by_source:
        return "_No papers scraped this run._"

    lines = ["**Most recent paper per source (as of this check):**", ""]
    for src in ["IZA", "CRR", "NBER"]:  # automated sources only
        p = first_by_source.get(src)
        if p:
            title = p.get("title", "Untitled").strip()
            url = p.get("url", "").strip()
            authors = p.get("authors", "").strip()
            entry = f"[{title}]({url})" if url else title
            if authors:
                entry += f" ({authors})"
            lines.append(f"- **{src}**: {entry}")
    return "\n".join(lines)


def format_checked_until(state: dict, papers_raw: list[dict]) -> str:
    """
    For each source, the new "checked_until" URL is the FIRST paper scraped
    (i.e. the most recent one on the page at time of scraping).
    If no new papers were found for a source, keep the old checkpoint.
    """
    today = date.today().isoformat()

    # Group raw papers by source, preserving order (first = most recent)
    first_by_source: dict[str, str] = {}
    for p in papers_raw:
        src = p["source"]
        if src not in first_by_source:
            first_by_source[src] = p["url"]

    source_map = {
        "IZA": "iza",
        "CRR": "crr",
        "NBER": "nber",
    }

    lines = [f"checked until ({today}):"]
    for display_name, key in source_map.items():
        old_url = state["sources"].get(key, {}).get("checked_until_url", "")
        new_url = first_by_source.get(display_name, old_url)
        short = new_url[:80] + "…" if len(new_url) > 80 else new_url
        if display_name == "NBER" and not first_by_source.get("NBER"):
            note = state["sources"].get("nber", {}).get("checked_until_url", "")
            lines.append(f"- NBER email {today} — {note} (unchanged, check email manually)")
        else:
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

    # Determine which sources need manual checking.
    # Use scrape_summary.json (written by scrape.py) when available — it distinguishes
    # between sources that errored and sources that ran successfully with 0 papers.
    # Fall back to inferring from papers_raw if the summary file doesn't exist.
    if os.path.exists("scrape_summary.json"):
        with open("scrape_summary.json", encoding="utf-8") as f:
            scrape_summary = json.load(f)
        # Sources with status != "ok" need manual checking
        manual = sorted(
            SOURCE_KEY_TO_DISPLAY[key]
            for key, status in scrape_summary.items()
            if status != "ok" and key in SOURCE_KEY_TO_DISPLAY
        )
    else:
        # Legacy fallback: any source not in papers_raw is assumed skipped
        scraped_sources = {p["source"] for p in papers_raw}
        all_sources = {"IZA", "CRR", "NBER"}
        manual = sorted(all_sources - scraped_sources)

    post = format_teams_post(papers, manual_sources=manual if manual else None)
    checked_until = format_checked_until(state, papers_raw)
    last_seen = format_last_seen(papers_raw)

    # Append "checked until" to the Teams post
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
