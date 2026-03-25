"""
scrape.py — Fetches new papers from EconPapers (NBER, IZA, CESifo, IFS) and CRR.
Outputs: papers_raw.json, scrape_summary.json

EconPapers sources use a unified scraper. CRR is scraped directly (not on RePEc).
Abstracts are NOT fetched here — only titles and authors from listing pages.
Abstracts are fetched lazily in filter.py for papers that pass the keyword filter.
"""

import json
import os
import re
import sys
import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional
import requests
from bs4 import BeautifulSoup

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(filename="scrape_errors.log", filemode="w", level=logging.WARNING)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 15


@dataclass
class Paper:
    source: str
    title: str
    url: str
    authors: str
    abstract: str


def get_soup(url: str) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# EconPapers unified scraper
# ---------------------------------------------------------------------------

# Each EconPapers source is defined by its RePEc handle path and how paper
# numbers are extracted from the listing.  The listing page uses <dl>/<dt>/<dd>
# structure:
#   <dt>NUMBER: <a href="SLUG.htm">TITLE</a> ...</dt>
#   <dd><i>Author1</i>, <i>Author2</i> and <i>Author3</i></dd>

ECONPAPERS_SOURCES = {
    "nber": {
        "name": "NBER Working Papers",
        "display": "NBER",
        "path": "nbrnberwo",
        "base_url": "https://econpapers.repec.org/paper/nbrnberwo/",
        # Canonical URL template: paper number -> full URL users will see
        "canonical_url": "https://www.nber.org/papers/w{number}",
        # Regex to extract numeric ID from the <dt> text
        "id_pattern": r"^(\d+):",
        "id_type": "int",  # IDs are pure integers, comparable numerically
    },
    "iza": {
        "name": "IZA Discussion Papers",
        "display": "IZA",
        "path": "izaizadps",
        "base_url": "https://econpapers.repec.org/paper/izaizadps/",
        "canonical_url": "https://www.iza.org/publications/dp/{number}",
        "id_pattern": r"^(\d+):",
        "id_type": "int",
    },
    "cesifo": {
        "name": "CESifo Working Papers",
        "display": "CESifo",
        "path": "cesceswps",
        "base_url": "https://econpapers.repec.org/paper/cesceswps/",
        "canonical_url": "https://econpapers.repec.org/paper/cesceswps/_5f{number}.htm",
        "id_pattern": r"^(\d+):",
        "id_type": "int",
    },
    "ifs": {
        "name": "IFS Working Papers",
        "display": "IFS",
        "path": "ifsifsewp",
        "base_url": "https://econpapers.repec.org/paper/ifsifsewp/",
        "canonical_url": "https://econpapers.repec.org/paper/ifsifsewp/{slug}.htm",
        # IFS uses "W25/33" or "WCWP28/24" style IDs
        "id_pattern": r"^([\w/]+):",
        "id_type": "str",  # Non-numeric; use string comparison
    },
}


def _extract_id(dt_text: str, id_pattern: str) -> Optional[str]:
    """Extract the paper ID from the text of a <dt> element."""
    m = re.match(id_pattern, dt_text.strip())
    return m.group(1) if m else None


def _id_is_past_checkpoint(paper_id: str, checkpoint_id: str, id_type: str) -> bool:
    """Return True if paper_id is AT or BEFORE the checkpoint (i.e. already seen)."""
    if not checkpoint_id:
        return False
    if id_type == "int":
        try:
            return int(paper_id) <= int(checkpoint_id)
        except ValueError:
            return False
    # String comparison for non-numeric IDs
    return paper_id == checkpoint_id


def _extract_checkpoint_id(checkpoint_url: str, source_key: str) -> str:
    """Extract the paper ID from a checkpoint URL for a given source."""
    cfg = ECONPAPERS_SOURCES[source_key]
    if cfg["id_type"] == "int":
        # Look for trailing number in the URL
        m = re.search(r"(\d+)(?:\.\w+)?$", checkpoint_url.rstrip("/"))
        if m:
            return m.group(1)
        # NBER: /papers/wNNNNN
        m = re.search(r"/w(\d+)", checkpoint_url)
        if m:
            return m.group(1)
        # IZA: /dp/NNNNN/
        m = re.search(r"/dp/(\d+)", checkpoint_url)
        if m:
            return m.group(1)
    return ""


def scrape_econpapers(source_key: str, checkpoint_url: str = "",
                      since_id: str = "") -> list[Paper]:
    """
    Scrape papers from an EconPapers listing page.

    checkpoint_url: stop when the paper at this URL/ID is reached.
    since_id: alternative checkpoint as a raw paper ID string.
    """
    cfg = ECONPAPERS_SOURCES[source_key]
    base_url = cfg["base_url"]
    id_pattern = cfg["id_pattern"]
    id_type = cfg["id_type"]

    # Determine the checkpoint ID to stop at
    checkpoint_id = since_id or _extract_checkpoint_id(checkpoint_url, source_key)

    papers = []
    page = 0
    max_pages = 20  # 100 papers/page * 20 = 2000 papers max

    while page < max_pages:
        url = base_url if page == 0 else f"{base_url}default{page * 100}.htm"
        soup = get_soup(url)
        if not soup:
            break

        dl = soup.find("dl")
        if not dl:
            logger.warning(f"{source_key}: no <dl> found on page {page}")
            break

        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        if not dts:
            break

        found_checkpoint = False
        for dt, dd in zip(dts, dds):
            dt_text = dt.get_text(strip=True)
            paper_id = _extract_id(dt_text, id_pattern)
            if not paper_id:
                continue

            # Check if we've reached the checkpoint
            if _id_is_past_checkpoint(paper_id, checkpoint_id, id_type):
                found_checkpoint = True
                break

            # Extract title and link
            link = dt.find("a")
            if not link:
                continue
            title = link.get_text(strip=True)

            # Build canonical URL
            if "{slug}" in cfg["canonical_url"]:
                slug = link.get("href", "").replace(".htm", "")
                paper_url = cfg["canonical_url"].format(slug=slug)
            else:
                paper_url = cfg["canonical_url"].format(number=paper_id)

            # Extract authors from <dd> — names are in <i> tags
            author_tags = dd.find_all("i") if dd else []
            authors = ", ".join(tag.get_text(strip=True) for tag in author_tags)

            papers.append(Paper(cfg["display"], title, paper_url, authors, ""))

        if found_checkpoint:
            break
        page += 1
        time.sleep(0.5)

    return papers


# ---------------------------------------------------------------------------
# CRR (Boston College Center for Retirement Research) — direct scraper
# ---------------------------------------------------------------------------

def _parse_crr_date(item) -> Optional[str]:
    """Extract ISO date string (YYYY-MM-DD) from a CRR article card, or None."""
    from datetime import datetime
    date_el = item.select_one(".date, div.date")
    if not date_el:
        return None
    text = date_el.get_text(strip=True)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _scrape_crr_featured(soup, checkpoint_date: str) -> list[Paper]:
    """Extract featured/highlighted papers from the top of the CRR listing page."""
    featured = []
    seen_urls: set[str] = set()

    for container_sel in ["div.content-lead-content", "div.frame-1"]:
        container = soup.select_one(container_sel)
        if not container:
            continue
        link = container.select_one("h1 a")
        if not link:
            continue
        paper_url = link.get("href", "")
        if not paper_url or paper_url in seen_urls:
            continue
        seen_urls.add(paper_url)

        pub_date = _parse_crr_date(container)
        if checkpoint_date and pub_date and pub_date <= checkpoint_date:
            continue

        title = link.get_text(strip=True)
        author_links = container.select("a.author")
        authors = ", ".join(a.get_text(strip=True) for a in author_links) if author_links else ""

        featured.append(Paper("CRR", title, paper_url, authors, ""))

    return featured


def _fetch_abstract_crr(url: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""
    for sel in ["div.entry-content p", "div.post-content p", "article p"]:
        for p in soup.select(sel):
            text = p.get_text(strip=True)
            if len(text) > 150:
                return text
    return ""


def scrape_crr(checkpoint_url: str, checkpoint_date: str = "") -> list[Paper]:
    """Scrape CRR working papers newer than the checkpoint."""
    papers = []
    page = 1
    max_pages = 10
    consecutive_old = 0
    seen_urls: set[str] = set()

    while page <= max_pages:
        url = (
            f"https://crr.bc.edu/publication-type/working-paper/page/{page}/"
            if page > 1
            else "https://crr.bc.edu/publication-type/working-paper/"
        )
        soup = get_soup(url)
        if not soup:
            break

        if page == 1:
            for p in _scrape_crr_featured(soup, checkpoint_date):
                if p.url not in seen_urls:
                    seen_urls.add(p.url)
                    # Fetch abstract for CRR (small volume, always worth it)
                    p.abstract = _fetch_abstract_crr(p.url)
                    papers.append(p)

        items = soup.select("div.article-card")
        if not items:
            logger.warning(f"CRR: no items found on page {page}")
            break

        found_checkpoint = False
        for item in items:
            link = item.select_one("h2 a, h3 a, h4 a, .article-card-title a")
            if not link:
                link = item.select_one("a.crr-image-link, a")
            if not link:
                continue
            paper_url = link.get("href", "")
            if not paper_url or paper_url in seen_urls:
                continue

            if not checkpoint_date and checkpoint_url:
                norm = lambda u: u.rstrip("/").split("?")[0].split("#")[0]
                if norm(paper_url) == norm(checkpoint_url):
                    found_checkpoint = True
                    break

            if checkpoint_date:
                pub_date = _parse_crr_date(item)
                if pub_date and pub_date <= checkpoint_date:
                    consecutive_old += 1
                    if consecutive_old >= 5:
                        found_checkpoint = True
                    continue
                consecutive_old = 0

            title_el = item.select_one("h2, h3, h4, .article-card-title")
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

            author_links = item.select("p#publication-byline a.author")
            if author_links:
                authors = ", ".join(a.get_text(strip=True) for a in author_links)
            else:
                authors_el = item.select_one(".author, .byline")
                authors = authors_el.get_text(strip=True) if authors_el else ""

            abstract = _fetch_abstract_crr(paper_url)

            seen_urls.add(paper_url)
            papers.append(Paper("CRR", title, paper_url, authors, abstract))

        if found_checkpoint:
            break
        page += 1
        time.sleep(0.5)

    return papers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# All sources and their scraper callables
# EconPapers sources are wrapped in lambdas to pass source_key
SCRAPERS = {
    "nber": lambda cp, **kw: scrape_econpapers("nber", cp, **kw),
    "iza": lambda cp, **kw: scrape_econpapers("iza", cp, **kw),
    "cesifo": lambda cp, **kw: scrape_econpapers("cesifo", cp, **kw),
    "ifs": lambda cp, **kw: scrape_econpapers("ifs", cp, **kw),
    "crr": lambda cp, **kw: scrape_crr(cp, **kw),
}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Scrape new working papers.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--since",
        metavar="ID_OR_DATE",
        help=(
            "Check all papers after this checkpoint. "
            "For EconPapers sources: a paper number (e.g. 34900 for NBER). "
            "For CRR: a YYYY-MM-DD date. "
            "Overrides state.json for this run."
        ),
    )
    group.add_argument(
        "--checkpoints",
        metavar="JSON",
        help=(
            'Per-source checkpoint overrides as JSON, e.g. '
            '\'{"nber": "34900", "iza": "18400", "crr": "2026-01-01"}\'. '
            "Values are paper numbers for EconPapers sources or dates for CRR."
        ),
    )
    args = parser.parse_args()

    with open("state.json", encoding="utf-8") as f:
        state = json.load(f)

    # Build effective checkpoint overrides
    checkpoint_overrides: dict[str, dict] = {}
    if args.since:
        print(f"Mode: --since {args.since} (overriding all checkpoints for this run)")
        for key in SCRAPERS:
            if key == "crr":
                # For CRR, --since is always a date
                checkpoint_overrides[key] = {"url": "", "date": args.since}
            else:
                # For EconPapers sources, --since is a paper number/ID
                checkpoint_overrides[key] = {"url": "", "since_id": args.since}
    elif args.checkpoints:
        raw = json.loads(args.checkpoints)
        for key, value in raw.items():
            key = key.lower()
            if key == "crr":
                checkpoint_overrides[key] = {"url": "", "date": value}
            else:
                checkpoint_overrides[key] = {"url": "", "since_id": value}
        print(f"Mode: --checkpoints override for: {', '.join(checkpoint_overrides)}")

    all_papers = []
    scrape_status: dict[str, str] = {}

    for source_key, scraper_fn in SCRAPERS.items():
        source_state = state["sources"].get(source_key, {})
        name = source_state.get("name", source_key)

        if source_key in checkpoint_overrides:
            override = checkpoint_overrides[source_key]
            kwargs = {}
            if source_key == "crr":
                cp = override.get("url", "")
                kwargs["checkpoint_date"] = override.get("date", "")
            else:
                cp = override.get("url", "")
                kwargs["since_id"] = override.get("since_id", "")
        else:
            cp = source_state.get("checked_until_url", "")
            kwargs = {}
            if source_key == "crr":
                kwargs["checkpoint_date"] = source_state.get("checked_until_date", "")

        print(f"Scraping {name}...")
        try:
            papers = scraper_fn(cp, **kwargs)
            print(f"  Found {len(papers)} new papers.")
            all_papers.extend([asdict(p) for p in papers])
            scrape_status[source_key] = "ok"
        except Exception as e:
            logger.warning(f"Error scraping {source_key}: {e}")
            print(f"  ERROR: {e} — skipping {name}.")
            scrape_status[source_key] = f"error: {e}"

    with open("papers_raw.json", "w", encoding="utf-8") as f:
        json.dump(all_papers, f, indent=2, ensure_ascii=False)

    with open("scrape_summary.json", "w", encoding="utf-8") as f:
        json.dump(scrape_status, f, indent=2)

    print(f"\nTotal new papers found: {len(all_papers)}")
    print("Saved to papers_raw.json")


if __name__ == "__main__":
    main()
