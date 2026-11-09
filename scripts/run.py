"""
run.py — The paper review in one command.

    python scripts/run.py --since 2026-10-26   # papers since a date
    python scripts/run.py                      # papers since the last confirmed run
    python scripts/run.py --confirm            # after review: save this run's date

A run scrapes all sources, keeps the relevant papers and writes teams_post.md.
It never changes state.json; --confirm does, so the next run starts where this
one ended. Can be run from any directory.
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
STATE = SKILL_DIR / "state.json"
LAST_RUN = SKILL_DIR / "last_run.json"


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(since: str) -> None:
    run_date = date.today().isoformat()
    print(f"Checking papers from {since} to {run_date}\n")

    papers, failed = scrape_all(since)
    raw = [asdict(p) for p in papers]
    relevant = filter_papers(raw)
    post = format_post(relevant, since, run_date, failed)

    write_json(SKILL_DIR / "papers_raw.json", raw)
    write_json(SKILL_DIR / "papers_relevant.json", relevant)
    (SKILL_DIR / "teams_post.md").write_text(post, encoding="utf-8")
    write_json(LAST_RUN, {"since": since, "run_date": run_date, "failed_sources": failed})

    print(f"\n{len(raw)} papers scraped, {len(relevant)} relevant.")
    if failed:
        print(f"Failed (check manually): {', '.join(failed)}")
    print(f"Post written to {SKILL_DIR / 'teams_post.md'}\n")
    print(post)


def confirm() -> None:
    last_run = read_json(LAST_RUN)
    write_json(STATE, {"last_checked": last_run["run_date"]})
    print(f"Saved: next run will check papers from {last_run['run_date']}.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(filename=SKILL_DIR / "scrape_errors.log", filemode="w",
                        level=logging.WARNING)

    parser = argparse.ArgumentParser(description="Find new retirement-relevant working papers.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--since", type=date.fromisoformat, metavar="YYYY-MM-DD",
                       help="check papers published on or after this date")
    group.add_argument("--confirm", action="store_true",
                       help="save the last run's date so the next run starts from it")
    args = parser.parse_args()

    if args.confirm:
        confirm()
    elif args.since:
        run(args.since.isoformat())
    elif STATE.exists():
        run(read_json(STATE)["last_checked"])
    else:
        parser.error("no state.json yet: give a start date with --since YYYY-MM-DD")


if __name__ == "__main__":
    main()
