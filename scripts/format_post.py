"""
format_post.py — Formats relevant papers as a Microsoft Teams post (Markdown).
"""


def format_post(papers: list[dict], since: str, run_date: str,
                failed_sources: list[str]) -> str:
    lines = []

    if failed_sources:
        lines += ["*Sources to check manually this round (scraping failed):*"]
        lines += [f"- {src}" for src in failed_sources]
        lines += ["", "---", ""]

    if not papers:
        lines += ["_No new relevant papers found this fortnight._", ""]

    for p in papers:
        title = p["title"].strip()
        authors = f" ({p['authors']})" if p["authors"] else ""
        lines += [f"[{title}]({p['url']}){authors}", ""]
        if p["abstract"]:
            lines += [p["abstract"].strip(), ""]
        lines += ["---", ""]

    lines.append(f"Checked papers from {since} to {run_date}.")
    return "\n".join(lines)
