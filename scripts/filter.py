"""
filter.py — Filters papers_raw.json for retirement relevance using keyword matching.
Outputs: papers_relevant.json
"""

import json
import os
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

# --- Keyword filter ---

# Strong positive signals — very likely relevant
STRONG_KEYWORDS = [
    r"\bretirement\b", r"\bretire[sd]?\b", r"\bpension\b", r"\bannuit[yi]",
    r"\bsocial security\b", r"\bstate pension\b", r"\bold.age\b",
    r"\bolder work", r"\bolder adult", r"\baging work", r"\bageing work",
    r"\bearly exit\b", r"\bearly retirement\b",
    r"\bdefined contribution\b", r"\bdefined benefit\b", r"\b401.?k\b",
    r"\bdc plan\b", r"\bdb plan\b",
    r"\bsurvivors? benefit\b", r"\bwidow", r"\bwidower",
    r"\blong.term care\b",
    r"\bdisability insurance\b.*\bolder\b|\bolder\b.*\bdisability insurance\b",
    r"\bmedicare\b",
    r"\bsaving for retirement\b", r"\bretirement saving",
    r"\bpension reform\b", r"\bsocial security reform",
    r"\bretirement age\b", r"\bstate pension age\b",
    r"\bwork longer\b", r"\bworking longer\b",
    r"\bjob guarantee.*older\b|\bolder.*job guarantee",
]

# Weak positive signals — possibly relevant, included as borderline
WEAK_KEYWORDS = [
    r"\bolder people\b", r"\bolder person\b", r"\bolderly\b",
    r"\bage 5[0-9]\b", r"\bover 50\b", r"\bover 60\b", r"\bover 65\b",
    r"\blife expectancy\b", r"\bmortality\b",
    r"\bwealth accumulation\b", r"\bwealth in retirement\b",
    r"\bhousehold saving\b", r"\bprecautionary saving\b",
    r"\bbequest\b", r"\binheritance\b",
    r"\bintergenerational transfer", r"\bintergenerational wealth",
    r"\bfertility\b",  # newer addition per team
    r"\bdisability\b",
    # Labour force participation only counts when paired with older-worker context
    r"\blabou?r force participation\b.{0,80}\b(older|retirement|pension|age[d ])\b|\b(older|retirement|pension|age[d ])\b.{0,80}\blabou?r force participation\b",
    r"\bunemployment.*older\b|\bolder.*unemployment\b",
    # Health-work link only when older workers / retirement angle is explicit
    r"\bhealth\b.{0,60}\b(retire|pension|older worker|older adult)\b|\b(retire|pension|older worker|older adult)\b.{0,60}\bhealth\b",
    r"\bfinancial security\b",
    r"\bconsumption.*old\b|\bold.*consumption\b",
]

# Strong negative signals — likely not relevant even if some signals match
NEGATIVE_KEYWORDS = [
    r"\bchild\b", r"\bchildren\b", r"\bschool\b", r"\beducation\b",
    r"\byouth\b", r"\bteenager\b", r"\bstudent\b",
    r"\bteacher\b", r"\bclassroom\b",
    r"\binfant\b", r"\bbreastfeed", r"\bmaternal health\b", r"\bneonatal\b",
    r"\bfirm\b.*\bproductivity\b",
    r"\btrade policy\b", r"\btariff\b",
    r"\bcryptocurrency\b", r"\bblockchain\b",
    r"\bclimate change\b", r"\benvironment\b",
]

# Hard exclusions — exclude even if strong keywords match.
# Use sparingly: only patterns where the topic is unambiguously outside scope.
HARD_NEGATIVE_KEYWORDS = [
    r"\bstaffing firms?\b",
    r"\bminimum income (recipients?|scheme|benefit)\b",
]


def _load_learned_keywords() -> list[str]:
    """Load suggested keywords from user feedback (feedback/overrides.json).

    When users manually include papers that the filter missed, they can suggest
    keywords. These are added as weak positive signals so the filter catches
    similar papers in future runs. Only "include" actions with a suggested_keyword
    field contribute — this keeps the loop conservative and human-supervised.
    """
    feedback_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                 "feedback", "overrides.json")
    if not os.path.exists(feedback_path):
        return []
    try:
        with open(feedback_path, encoding="utf-8") as f:
            overrides = json.load(f)
        keywords = []
        for entry in overrides:
            if entry.get("action") == "include" and entry.get("suggested_keyword"):
                kw = entry["suggested_keyword"].strip().lower()
                if kw:
                    keywords.append(r"\b" + re.escape(kw) + r"\b")
        if keywords:
            print(f"  Loaded {len(keywords)} learned keyword(s) from feedback.")
        return keywords
    except Exception as e:
        print(f"  Warning: could not load feedback overrides: {e}")
        return []


LEARNED_KEYWORDS: list[str] = []  # populated at runtime in main()


def keyword_score(text: str) -> tuple[int, int]:
    """Returns (strong_hits, weak_hits) for lowercase text."""
    text_lower = text.lower()
    strong = sum(1 for kw in STRONG_KEYWORDS if re.search(kw, text_lower))
    weak = sum(1 for kw in WEAK_KEYWORDS if re.search(kw, text_lower))
    # Learned keywords from user feedback count as weak signals
    weak += sum(1 for kw in LEARNED_KEYWORDS if re.search(kw, text_lower))
    return strong, weak


def has_negative(text: str) -> bool:
    text_lower = text.lower()
    return any(re.search(kw, text_lower) for kw in NEGATIVE_KEYWORDS)


def has_hard_negative(text: str) -> bool:
    text_lower = text.lower()
    return any(re.search(kw, text_lower) for kw in HARD_NEGATIVE_KEYWORDS)


def keyword_decision(title: str, abstract: str) -> str:
    """Returns 'yes', 'no', or 'maybe' (borderline — included by default)."""
    combined = f"{title} {abstract}"
    if has_hard_negative(combined):
        return "no"
    strong, weak = keyword_score(combined)
    neg = has_negative(combined)
    if strong >= 1 and not neg:
        return "yes"
    if strong >= 1 and neg:
        return "maybe"
    if weak >= 1 and not neg:
        return "maybe"
    return "no"


def _econpapers_abstract_url(paper_url: str) -> str | None:
    """Convert a canonical paper URL to its EconPapers detail page URL."""
    # NBER: https://www.nber.org/papers/w34966 -> econpapers.repec.org/paper/nbrnberwo/34966.htm
    m = re.search(r"nber\.org/papers/w(\d+)", paper_url)
    if m:
        return f"https://econpapers.repec.org/paper/nbrnberwo/{m.group(1)}.htm"

    # IZA: https://www.iza.org/publications/dp/18460 -> econpapers.repec.org/paper/izaizadps/dp18460.htm
    m = re.search(r"iza\.org/publications/dp/(\d+)", paper_url)
    if m:
        return f"https://econpapers.repec.org/paper/izaizadps/dp{m.group(1)}.htm"

    # CESifo: already an EconPapers URL
    if "cesceswps" in paper_url:
        return paper_url

    # IFS: EconPapers has no abstracts for IFS papers — skip
    # (IFS website uses Drupal with no clean abstract selector)
    if "ifsifsewp" in paper_url:
        return None

    # CRR: fetched directly by the scraper, shouldn't need this path
    return None


def _fetch_missing_abstracts(papers: list[dict]) -> None:
    """Fetch abstracts from EconPapers detail pages for papers missing them."""
    if requests is None or BeautifulSoup is None:
        print("  requests/beautifulsoup4 not installed — skipping abstract fetch.")
        return

    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    for p in papers:
        url = p.get("url", "")
        ep_url = _econpapers_abstract_url(url)
        if not ep_url:
            continue
        try:
            r = requests.get(ep_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            # EconPapers: abstract follows a <b>Abstract:</b> tag in the bodytext div
            bodytext = soup.find("div", class_="bodytext")
            if bodytext:
                abstract_text = bodytext.get_text()
                idx = abstract_text.find("Abstract:")
                if idx >= 0:
                    # Extract text after "Abstract:" until the next section
                    remainder = abstract_text[idx + len("Abstract:"):].strip()
                    # Clean up — take until "Keywords:" or "JEL:" or "Date:" or end
                    for stop in ["Keywords:", "JEL:", "Date:", "Pages:", "References:",
                                 "Download info", "Related research"]:
                        stop_idx = remainder.find(stop)
                        if stop_idx > 0:
                            remainder = remainder[:stop_idx]
                    abstract = remainder.strip()
                    if len(abstract) > 50:
                        p["abstract"] = abstract
                        print(f"  Fetched abstract for: {p['title'][:60]}...")
        except Exception as e:
            print(f"  Warning: could not fetch abstract for '{p['title'][:50]}': {e}")
        time.sleep(0.3)


def main():
    global LEARNED_KEYWORDS
    LEARNED_KEYWORDS = _load_learned_keywords()

    with open("papers_raw.json", encoding="utf-8") as f:
        papers = json.load(f)

    if not papers:
        print("No papers to filter.")
        with open("papers_relevant.json", "w") as f:
            json.dump([], f)
        return

    # Step 1: keyword filter
    included = []
    excluded = []

    for p in papers:
        decision = keyword_decision(p["title"], p.get("abstract", ""))
        if decision in ("yes", "maybe"):
            included.append(p)
        else:
            excluded.append(p)

    print(f"Keyword filter: {len(included)} included, {len(excluded)} excluded")

    # Step 2: Fetch missing abstracts for included papers
    # (NBER papers from email digest arrive without abstracts)
    missing_abstract = [p for p in included if not p.get("abstract")]
    if missing_abstract:
        print(f"\nFetching abstracts for {len(missing_abstract)} papers without one...")
        _fetch_missing_abstracts(missing_abstract)

    # Step 3: Deduplicate — URL-first (normalised), then title fallback
    # Same paper can appear in IZA + NBER with the same URL or near-identical title
    def _norm_url(u: str) -> str:
        return u.rstrip("/").split("?")[0].split("#")[0].lower()

    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    deduped = []
    for p in included:
        url_key = _norm_url(p.get("url", ""))
        title_key = p.get("title", "").strip().lower()
        if url_key and url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        deduped.append(p)
    if len(deduped) < len(included):
        print(f"Removed {len(included) - len(deduped)} duplicate(s).")
    included = deduped

    # Step 4: Normalise author strings — ensure exactly one space after each comma
    for p in included:
        if p.get("authors"):
            p["authors"] = re.sub(r",\s*", ", ", p["authors"].strip())

    print(f"\nTotal relevant papers: {len(included)}")

    with open("papers_relevant.json", "w", encoding="utf-8") as f:
        json.dump(included, f, indent=2, ensure_ascii=False)

    print("Saved to papers_relevant.json")


if __name__ == "__main__":
    main()
