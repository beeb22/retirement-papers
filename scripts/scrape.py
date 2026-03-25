"""
scrape.py — Fetches new papers from IZA, CRR, and NBER up to the "checked_until" checkpoint.
Outputs: papers_raw.json

NBER: if nber_email_papers.json exists in the working directory, reads papers from
that pre-fetched file (populated by the skill runner before this script runs).
Otherwise falls back to attempting the NBER website.
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


def normalise_url(url: str) -> str:
    """Strip trailing slashes and query strings for checkpoint comparison."""
    return url.rstrip("/").split("?")[0].split("#")[0]


def url_matches(page_url: str, checkpoint_url: str) -> bool:
    return normalise_url(page_url) == normalise_url(checkpoint_url)


# ---------------------------------------------------------------------------
# IZA
# ---------------------------------------------------------------------------

def _iza_dp_number(url: str) -> Optional[str]:
    """Extract numeric DP ID from an IZA URL, e.g. '18356' from .../dp/18356/..."""
    m = re.search(r"/dp/(\d+)/", url)
    return m.group(1) if m else None


def scrape_iza(checkpoint_url: str, since_date: str = "") -> list[Paper]:
    """
    Scrape IZA papers newer than the checkpoint.
    checkpoint_url: stop when this DP number/URL is seen (normal mode).
    since_date: YYYY-MM-DD — stop when a paper's publication date is before this
                (used with --since; fetches date from each paper's detail page).
    """
    checkpoint_dp = _iza_dp_number(checkpoint_url)
    papers = []
    page = 1
    max_pages = 50

    while page <= max_pages:
        url = f"https://www.iza.org/publications/dp?page={page}"
        soup = get_soup(url)
        if not soup:
            break

        # IZA uses <article> tags for each paper entry (Tailwind CSS layout).
        # Each article has 3 direct child divs: DP number, title (with link), authors.
        items = soup.select("article")
        if not items:
            logger.warning(f"IZA: no items found on page {page}")
            break

        found_checkpoint = False
        for item in items:
            link = item.select_one("a[href*='/dp/']")
            if not link:
                continue
            href = link.get("href", "")
            paper_url = ("https://www.iza.org" + href) if href.startswith("/") else href

            # URL/DP-number checkpoint (normal mode)
            if checkpoint_dp and _iza_dp_number(paper_url) == checkpoint_dp:
                found_checkpoint = True
                break
            elif not checkpoint_dp and not since_date and url_matches(paper_url, checkpoint_url):
                found_checkpoint = True
                break

            title = link.get_text(strip=True)

            # Authors are in the last direct child div of the article
            direct_divs = [d for d in item.children if hasattr(d, 'name') and d.name == 'div']
            authors = direct_divs[-1].get_text(strip=True) if direct_divs else ""

            abstract, pub_date = _fetch_abstract_iza(paper_url)

            # Date checkpoint (--since mode): stop when we reach papers before the cutoff
            if since_date and pub_date and pub_date < since_date:
                found_checkpoint = True
                break

            papers.append(Paper("IZA", title, paper_url, authors, abstract))

        if found_checkpoint:
            break
        page += 1
        time.sleep(0.5)

    return papers


_MONTH_TO_NUM = {
    "January": "01", "February": "02", "March": "03", "April": "04",
    "May": "05", "June": "06", "July": "07", "August": "08",
    "September": "09", "October": "10", "November": "11", "December": "12",
}


def _fetch_abstract_iza(url: str) -> tuple[str, str]:
    """Returns (abstract, pub_date) where pub_date is 'YYYY-MM-01' or ''."""
    soup = get_soup(url)
    if not soup:
        return "", ""
    abstract_el = soup.select_one("div.element-copyexpandable")
    abstract = abstract_el.get_text(strip=True) if abstract_el else ""

    # Date is in a text node matching "Month YYYY" somewhere on the detail page.
    # The old Bootstrap layout (div.col-md-9 > p) was replaced by Tailwind divs.
    date_str = ""
    _month_pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})"
    )
    for text_node in soup.find_all(string=_month_pattern):
        m = _month_pattern.search(text_node.strip())
        if m:
            date_str = f"{m.group(2)}-{_MONTH_TO_NUM[m.group(1)]}-01"
            break

    return abstract, date_str


# ---------------------------------------------------------------------------
# CRR (Boston College Center for Retirement Research)
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
    """
    Extract featured/highlighted papers from the top of the CRR listing page.
    CRR displays 1-2 recent papers in a different layout (h1 links in
    div.content-lead-content and div.frame-1) above the main article-card grid.
    """
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
        if author_links:
            authors = ", ".join(a.get_text(strip=True) for a in author_links)
        else:
            authors = ""

        abstract = _fetch_abstract_crr(paper_url)
        featured.append(Paper("CRR", title, paper_url, authors, abstract))

    return featured


def scrape_crr(checkpoint_url: str, checkpoint_date: str = "") -> list[Paper]:
    """
    Scrape CRR working papers newer than the checkpoint.
    CRR's listing isn't in strict chronological order, so we filter by
    publication date (extracted from each article card) rather than URL.
    checkpoint_date should be a YYYY-MM-DD string from state.json's checked_until_date.
    Falls back to URL matching if checkpoint_date is empty (first-run compat).
    """
    from datetime import datetime

    papers = []
    page = 1
    max_pages = 10  # CRR publishes ~10-30 papers/year; 10 pages * ~10 items = 100

    consecutive_old = 0  # stop early if many consecutive old papers seen
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

        # On page 1, also scrape featured papers displayed above the main listing
        if page == 1:
            for p in _scrape_crr_featured(soup, checkpoint_date):
                if p.url not in seen_urls:
                    seen_urls.add(p.url)
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

            # URL-based checkpoint (legacy / first run when no date available)
            if not checkpoint_date and url_matches(paper_url, checkpoint_url):
                found_checkpoint = True
                break

            # Date-based checkpoint
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

            # Collect ALL authors from the byline
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


def _fetch_abstract_crr(url: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""
    # Find the first substantial paragraph (skip short metadata/byline paragraphs)
    for sel in ["div.entry-content p", "div.post-content p", "article p"]:
        for p in soup.select(sel):
            text = p.get_text(strip=True)
            if len(text) > 150:
                return text
    return ""


# ---------------------------------------------------------------------------
# NBER
# ---------------------------------------------------------------------------

def _nber_paper_num(url: str) -> Optional[int]:
    """Extract NBER paper number from URL, e.g. 34897 from .../papers/w34897..."""
    m = re.search(r"/papers/w(\d+)", url)
    return int(m.group(1)) if m else None


def _fetch_abstract_nber(url: str) -> str:
    soup = get_soup(url)
    if not soup:
        return ""
    el = soup.select_one(".page-header__intro-inner")
    return el.get_text(strip=True) if el else ""


def scrape_nber(checkpoint_url: str) -> list[Paper]:
    """
    If nber_email_papers.json exists, parse NBER papers from that file.
    Otherwise attempt the NBER website (often JS-rendered — may return 0 papers).
    """
    email_file = "nber_email_papers.json"
    if os.path.exists(email_file):
        return _scrape_nber_from_email_json(checkpoint_url, email_file)

    # Fallback: try NBER website
    if checkpoint_url.startswith("nber_email_") or checkpoint_url.startswith("nber_w"):
        print("  NBER: no email JSON found and checkpoint is email/number-based.")
        print("  NBER: please check the weekly email digest manually.")
        return []

    papers = []
    page = 1
    max_pages = 10

    while page <= max_pages:
        url = f"https://www.nber.org/papers?page={page}&perPage=50"
        soup = get_soup(url)
        if not soup:
            print("  NBER: site unavailable — skipping.")
            return []

        items = soup.select("article.digest-list-item, div.research-paper, li.paper-listing")
        if not items:
            items = soup.select("div.paper, article")

        found_checkpoint = False
        for item in items:
            link = item.select_one("a[href*='/papers/w']")
            if not link:
                link = item.select_one("h3 a, h2 a, .title a")
            if not link:
                continue
            href = link.get("href", "")
            paper_url = ("https://www.nber.org" + href) if href.startswith("/") else href

            if url_matches(paper_url, checkpoint_url):
                found_checkpoint = True
                break

            title = link.get_text(strip=True)
            authors_el = item.select_one(".authors, .author, .paper-authors")
            authors = authors_el.get_text(strip=True) if authors_el else ""
            abstract = _fetch_abstract_nber(paper_url)

            papers.append(Paper("NBER", title, paper_url, authors, abstract))

        if found_checkpoint:
            break
        page += 1
        time.sleep(0.5)

    return papers


def _scrape_nber_from_email_json(checkpoint_url: str, filepath: str) -> list[Paper]:
    """
    Read pre-fetched NBER papers from email JSON and fetch their abstracts.
    JSON format: [{"title": ..., "url": ..., "authors": ...}, ...]
    Papers should be ordered newest-first (highest paper number first).

    Checkpoint logic:
    - If checkpoint is a full NBER URL (e.g. https://www.nber.org/papers/w34500):
      skip papers with number <= checkpoint number
    - If checkpoint is date-based (nber_email_YYYY-MM-DD): include all papers
      (email was already fetched for the current check period)
    """
    with open(filepath, encoding="utf-8") as f:
        raw_papers = json.load(f)

    # Determine checkpoint paper number (if URL-based)
    checkpoint_num = _nber_paper_num(checkpoint_url)

    papers = []
    for p in raw_papers:
        paper_url = normalise_url(p["url"])
        paper_num = _nber_paper_num(paper_url)

        # Skip if at or before checkpoint
        if checkpoint_num and paper_num and paper_num <= checkpoint_num:
            continue
        if not checkpoint_url.startswith("nber_") and url_matches(paper_url, checkpoint_url):
            continue

        title = p["title"]
        authors = p["authors"]
        # Abstracts are fetched lazily in filter.py for relevant papers only
        # (avoids fetching thousands of abstracts for the full backlog)
        abstract = p.get("abstract", "")

        papers.append(Paper("NBER", title, paper_url, authors, abstract))

    return papers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SCRAPERS = {
    "iza": scrape_iza,
    "crr": scrape_crr,
    "nber": scrape_nber,
}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Scrape new working papers.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Check all papers published after this date (overrides state.json checkpoints for this run).",
    )
    group.add_argument(
        "--checkpoints",
        metavar="JSON",
        help=(
            'Per-source checkpoint overrides as a JSON object, e.g. '
            '\'{"iza": "https://...", "crr": "2026-01-01", "nber": "https://..."}\'. '
            "Values are URLs for IZA/NBER or YYYY-MM-DD dates for CRR."
        ),
    )
    args = parser.parse_args()

    with open("state.json", encoding="utf-8") as f:
        state = json.load(f)

    # Build effective checkpoint overrides (don't mutate state.json)
    checkpoint_overrides: dict[str, dict] = {}  # source_key -> {url, date}
    if args.since:
        print(f"Mode: --since {args.since} (overriding all checkpoints for this run)")
        for key in SCRAPERS:
            checkpoint_overrides[key] = {"url": "", "date": args.since}
    elif args.checkpoints:
        raw = json.loads(args.checkpoints)
        for key, value in raw.items():
            key = key.lower()
            # Detect whether the value is a date or a URL
            if re.match(r"\d{4}-\d{2}-\d{2}$", value):
                checkpoint_overrides[key] = {"url": "", "date": value}
            else:
                checkpoint_overrides[key] = {"url": value, "date": ""}
        print(f"Mode: --checkpoints override for: {', '.join(checkpoint_overrides)}")

    all_papers = []
    # "ok" = scraped successfully (0 or more papers); "error" = exception raised
    scrape_status: dict[str, str] = {}

    for source_key, scraper_fn in SCRAPERS.items():
        source_state = state["sources"].get(source_key, {})
        name = source_state.get("name", source_key)

        # Apply override if present, otherwise use state.json values
        if source_key in checkpoint_overrides:
            override = checkpoint_overrides[source_key]
            checkpoint = override["url"]
            checkpoint_date = override["date"] or source_state.get("checked_until_date", "")
        else:
            checkpoint = source_state.get("checked_until_url", "")
            checkpoint_date = source_state.get("checked_until_date", "")

        print(f"Scraping {name}...")
        try:
            if source_key == "crr":
                papers = scraper_fn(checkpoint, checkpoint_date=checkpoint_date)
            elif source_key == "iza" and source_key in checkpoint_overrides:
                # In override mode: use date to stop scraping at the right cutoff
                papers = scraper_fn(checkpoint, since_date=checkpoint_date)
            else:
                papers = scraper_fn(checkpoint)
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
