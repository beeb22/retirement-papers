"""
scrape.py — Fetches working papers published on or after a given date.

Sources and the date each is filtered on:
- NBER: release date. Listing from NBER's own API (EconPapers lags NBER by
  days); release day and full abstract from each paper's nber.org page.
- IZA, CESifo, IFS: the day the paper was added to EconPapers (the hidden
  EPDATE field on each paper page). The visible "Date:" field is only a month
  or year. Note IZA uploads to EconPapers in monthly bulk.
- CRR: publication date shown on crr.bc.edu.

Every paper comes back with its abstract, so filtering can use it.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 15
DELAY = 0.3  # seconds between requests, to be polite to the servers

# Listings are ordered by paper number, which tracks the date closely but not
# exactly (mis-numbered IFS entries, IZA bulk uploads), so stop only after this
# many consecutive papers older than the cutoff.
STOP_AFTER_OLD = 10


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
        # Pass raw bytes so BeautifulSoup reads the page's own charset declaration
        # (requests guesses ISO-8859-1 for EconPapers, which garbles accented names)
        return BeautifulSoup(r.content, "html.parser")
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None
    finally:
        time.sleep(DELAY)


def fix_mojibake(text: str) -> str:
    """Repair UTF-8 text that was mis-decoded as Latin-1 upstream (IZA's
    EconPapers records contain e.g. 'MÃ¤kinen' for 'Mäkinen', sometimes
    several layers deep)."""
    for _ in range(3):
        if not any(marker in text for marker in ("Ã", "Â", "â€")):
            break
        try:
            text = text.encode("cp1252").decode("utf-8")
        except UnicodeError:
            try:
                text = text.encode("latin-1").decode("utf-8")
            except UnicodeError:
                break
    return text


# ---------------------------------------------------------------------------
# EconPapers (IZA, CESifo, IFS)
# ---------------------------------------------------------------------------

# The listing page is newest-first, 100 papers per page, as <dl>/<dt>/<dd>:
#   <dt>NUMBER: <a href="SLUG.htm">TITLE</a></dt>
#   <dd><i>Author1</i>, <i>Author2</i></dd>
# "url" is the link shown in the post; it can use {number} or {slug}.
ECONPAPERS_SOURCES = {
    "iza": {
        "display": "IZA",
        "base_url": "https://econpapers.repec.org/paper/izaizadps/",
        "url": "https://www.iza.org/publications/dp/{number}",
    },
    "cesifo": {
        "display": "CESifo",
        "base_url": "https://econpapers.repec.org/paper/cesceswps/",
        "url": "https://econpapers.repec.org/paper/cesceswps/{slug}.htm",
    },
    "ifs": {
        "display": "IFS",  # EconPapers has no abstracts for IFS papers
        "base_url": "https://econpapers.repec.org/paper/ifsifsewp/",
        "url": "https://econpapers.repec.org/paper/ifsifsewp/{slug}.htm",
    },
}


def fetch_econpapers_detail(detail_url: str) -> tuple[str, Optional[str]]:
    """Fetch an EconPapers paper page and return (abstract, epdate)."""
    soup = get_soup(detail_url)
    if not soup:
        return "", None

    meta = soup.find("meta", attrs={"name": "EPDATE"})
    epdate = meta.get("content") if meta else None

    abstract = ""
    # Abstract follows a <b>Abstract:</b> tag in the bodytext div
    bodytext = soup.find("div", class_="bodytext")
    text = bodytext.get_text() if bodytext else ""
    idx = text.find("Abstract:")
    if idx >= 0:
        remainder = text[idx + len("Abstract:"):]
        for stop in ["Keywords:", "JEL:", "Date:", "Pages:", "References:",
                     "Download info", "Related research"]:
            stop_idx = remainder.find(stop)
            if stop_idx > 0:
                remainder = remainder[:stop_idx]
        if len(remainder.strip()) > 50:
            abstract = fix_mojibake(remainder.strip())
    return abstract, epdate


def scrape_econpapers(source_key: str, since: str) -> list[Paper]:
    cfg = ECONPAPERS_SOURCES[source_key]
    papers = []
    consecutive_old = 0

    for page in range(20):
        url = cfg["base_url"] if page == 0 else f"{cfg['base_url']}default{page * 100}.htm"
        soup = get_soup(url)
        dl = soup.find("dl") if soup else None
        if not dl:
            if page == 0:
                raise RuntimeError(f"could not read listing page {url}")
            break

        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            link = dt.find("a")
            if not link:
                continue
            number = dt.get_text(strip=True).split(":", 1)[0]
            slug = link.get("href", "").removesuffix(".htm")

            abstract, epdate = fetch_econpapers_detail(cfg["base_url"] + link.get("href", ""))
            if not epdate or epdate < since:
                consecutive_old += 1
                if consecutive_old >= STOP_AFTER_OLD:
                    return papers
                continue
            consecutive_old = 0

            authors = ", ".join(i.get_text(strip=True) for i in dd.find_all("i"))
            papers.append(Paper(cfg["display"], fix_mojibake(link.get_text(strip=True)),
                                cfg["url"].format(number=number, slug=slug),
                                fix_mojibake(authors), abstract))
    return papers


# ---------------------------------------------------------------------------
# NBER
# ---------------------------------------------------------------------------

NBER_API = ("https://www.nber.org/api/v1/working_page_listing/"
            "contentType/working_paper/_/_/search")


def _html_to_text(html: Optional[str]) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def fetch_nber_detail(url: str) -> tuple[str, str]:
    """Fetch an NBER paper page and return (abstract, release date YYYY-MM-DD).
    The API only gives a month and cuts abstracts off at 300 characters."""
    soup = get_soup(url)
    meta = soup.find("meta", attrs={"name": "citation_publication_date"}) if soup else None
    if not meta:
        raise RuntimeError(f"no release date found on {url}")
    intro = soup.select_one("div.page-header__intro-inner")
    return (intro.get_text(" ", strip=True) if intro else ""), meta["content"].replace("/", "-")


def scrape_nber(since: str) -> list[Paper]:
    # The API lists papers newest release first, 100 per page
    papers = []
    consecutive_old = 0
    for page in range(1, 11):
        r = requests.get(NBER_API, params={"page": page, "perPage": 100},
                         headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        rows = r.json().get("results", [])
        if not rows:
            break

        for row in rows:
            if "/papers/w" not in row.get("url", ""):
                continue
            url = "https://www.nber.org" + row["url"]
            abstract, released = fetch_nber_detail(url)
            if released < since:
                consecutive_old += 1
                if consecutive_old >= STOP_AFTER_OLD:
                    return papers
                continue
            consecutive_old = 0

            papers.append(Paper("NBER", _html_to_text(row.get("title")), url,
                                ", ".join(_html_to_text(a) for a in row.get("authors") or []),
                                abstract or _html_to_text(row.get("abstract"))))
    return papers


# ---------------------------------------------------------------------------
# CRR (Boston College Center for Retirement Research)
# ---------------------------------------------------------------------------

CRR_LISTING = "https://crr.bc.edu/publication-type/working-paper/"


def _parse_crr_date(element) -> Optional[str]:
    """Extract an ISO date (YYYY-MM-DD) from a CRR article card, or None."""
    date_el = element.select_one(".date, div.date")
    if not date_el:
        return None
    text = date_el.get_text(strip=True)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


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


def _crr_cards(soup, first_page: bool):
    """Yield (link, card) for each paper on a listing page. The first page
    also has featured papers at the top, outside the normal cards."""
    if first_page:
        for sel in ["div.content-lead-content", "div.frame-1"]:
            card = soup.select_one(sel)
            link = card.select_one("h1 a") if card else None
            if link:
                yield link, card
    for card in soup.select("div.article-card"):
        link = (card.select_one("h2 a, h3 a, h4 a, .article-card-title a")
                or card.select_one("a.crr-image-link, a"))
        if link:
            yield link, card


def scrape_crr(since: str) -> list[Paper]:
    papers = []
    seen_urls: set[str] = set()
    consecutive_old = 0

    for page in range(1, 11):
        soup = get_soup(CRR_LISTING if page == 1 else f"{CRR_LISTING}page/{page}/")
        if not soup or not soup.select("div.article-card"):
            if page == 1:
                raise RuntimeError("could not read the CRR listing page")
            break

        for link, card in _crr_cards(soup, first_page=page == 1):
            url = link.get("href", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            pub_date = _parse_crr_date(card)
            if pub_date and pub_date < since:
                consecutive_old += 1
                if consecutive_old >= STOP_AFTER_OLD:
                    return papers
                continue
            consecutive_old = 0

            title_el = card.select_one("h1, h2, h3, h4, .article-card-title")
            authors = card.select("p#publication-byline a.author, a.author")
            papers.append(Paper(
                "CRR",
                (title_el or link).get_text(strip=True),
                url,
                ", ".join(dict.fromkeys(a.get_text(strip=True) for a in authors)),
                _fetch_abstract_crr(url),
            ))
    return papers


# ---------------------------------------------------------------------------

# Source key -> (display name, scraper). Order is the order shown in the post.
SOURCES = {
    "nber": ("NBER", scrape_nber),
    "iza": ("IZA", lambda since: scrape_econpapers("iza", since)),
    "cesifo": ("CESifo", lambda since: scrape_econpapers("cesifo", since)),
    "ifs": ("IFS", lambda since: scrape_econpapers("ifs", since)),
    "crr": ("CRR", scrape_crr),
}


def scrape_all(since: str) -> tuple[list[Paper], list[str]]:
    """Scrape every source for papers on or after `since` (YYYY-MM-DD).
    Returns (papers, display names of sources that failed)."""
    papers, failed = [], []
    for display, scraper in SOURCES.values():
        print(f"Scraping {display}...", flush=True)
        try:
            found = scraper(since)
            print(f"  {len(found)} papers")
            papers += found
        except Exception as e:
            logger.warning(f"Error scraping {display}: {e}")
            print(f"  ERROR: {e} - check {display} manually")
            failed.append(display)
    return papers, failed
