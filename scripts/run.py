"""
run.py — The paper review in one command.

    python scripts/run.py --since 2026-10-26   # papers published on or after this date
    python scripts/run.py --since 2026-10-03 --until 2026-10-16   # a past period

Scrapes all sources, keeps the relevant papers and prints the Teams post.
There is no saved state: whoever runs the review gives the start date (usually
the date of the last post), so it works the same for everyone on the rota.
Can be run from any directory.
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from scrape import scrape_all
from filter import filter_papers
from format_post import format_post

SKILL_DIR = Path(__file__).resolve().parent.parent


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run(since: str, until: str) -> None:
    print(f"Checking papers from {since} to {until}\n")

    papers, failed = scrape_all(since)
    # Scrapers return everything since `since`; drop papers dated after `until`.
    # Papers with no known date are kept so nothing is silently lost.
    raw = [asdict(p) for p in papers if not p.date or p.date <= until]
    relevant = filter_papers(raw)
    post = format_post(relevant, since, until, failed)

    # Working files for reviewing what was kept and left out; not part of the post
    write_json(SKILL_DIR / "papers_raw.json", raw)
    write_json(SKILL_DIR / "papers_relevant.json", relevant)

    print(f"\n{len(raw)} papers scraped, {len(relevant)} relevant.")
    if failed:
        print(f"Failed (check manually back to {since}): {', '.join(failed)}")
    print("\n===== TEAMS POST =====\n")
    print(post)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(filename=SKILL_DIR / "scrape_errors.log", filemode="w",
                        level=logging.WARNING)

    parser = argparse.ArgumentParser(description="Find new retirement-relevant working papers.")
    parser.add_argument("--since", type=date.fromisoformat, metavar="YYYY-MM-DD", required=True,
                        help="check papers published on or after this date")
    parser.add_argument("--until", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        default=date.today(),
                        help="last date to include (default: today); for re-checking a past period")
    args = parser.parse_args()
    if args.since > date.today():
        parser.error(f"--since {args.since} is in the future")
    if args.until < args.since:
        parser.error(f"--until {args.until} is before --since {args.since}")
    run(args.since.isoformat(), args.until.isoformat())


if __name__ == "__main__":
    main()
