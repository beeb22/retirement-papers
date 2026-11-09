"""
filter.py — Keeps retirement-relevant papers using keyword matching on the
title and abstract.
"""

import json
import os
import re

# --- Keyword filter ---

# Strong positive signals — very likely relevant
STRONG_KEYWORDS = [
    r"\bretirement\b", r"\bretire(?:e?s?|d)\b", r"\bpension\b", r"\bannuit[yi]",
    r"\bsocial security\b", r"\bstate pension\b", r"\bold.age\b",
    r"\bolder work", r"\bolder adult", r"\baging work", r"\bageing work",
    r"\bsenior work",
    r"\bearly exit\b", r"\bearly retirement\b",
    r"\bdefined contribution\b", r"\bdefined benefit\b", r"\b401.?k\b",
    r"\bdc plan\b", r"\bdb plan\b",
    r"\bsurvivors? benefit\b", r"\bwidow", r"\bwidower",
    r"\blong.term care\b", r"\bend.of.life\b",
    r"\bdisability insurance\b.*\bolder\b|\bolder\b.*\bdisability insurance\b",
    r"\bsaving for retirement\b", r"\bretirement saving",
    r"\bpension reform\b", r"\bsocial security reform",
    r"\bretirement age\b", r"\bstate pension age\b",
    r"\bwork longer\b", r"\bworking longer\b",
    r"\bjob guarantee.*older\b|\bolder.*job guarantee",
]

# Strong signals only when in the title: US health papers often mention
# Medicare data in the abstract without being about older people
TITLE_ONLY_STRONG_KEYWORDS = [
    r"\bmedicare\b",
]

# Weak positive signals — possibly relevant, included as borderline
WEAK_KEYWORDS = [
    r"\bolder people\b", r"\bolder person\b", r"\bolderly\b",
    r"\bage 5[0-9]\b", r"\bover 50\b", r"\bover 60\b", r"\bover 65\b",
    r"\blife expectancy\b", r"\bmortality\b", r"\blongevity\b", r"\belderly\b",
    r"\bpopulation ag(?:e)?ing\b",
    r"\bfinancial literacy\b",
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


def load_learned_keywords() -> list[str]:
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


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def is_relevant(title: str, abstract: str, learned: list[str] = ()) -> bool:
    """Strong keyword -> relevant. Weak keyword (incl. learned from feedback)
    -> relevant unless a negative keyword also matches. Hard negatives always
    exclude."""
    text = f"{title} {abstract}".lower()
    if _matches(HARD_NEGATIVE_KEYWORDS, text):
        return False
    if _matches(STRONG_KEYWORDS, text) or _matches(TITLE_ONLY_STRONG_KEYWORDS, title.lower()):
        return True
    return _matches(WEAK_KEYWORDS + list(learned), text) and not _matches(NEGATIVE_KEYWORDS, text)


def filter_papers(papers: list[dict]) -> list[dict]:
    """Return relevant papers, deduplicated by title (the same paper is often
    cross-posted, e.g. to IZA and CESifo)."""
    learned = load_learned_keywords()
    relevant, seen_titles = [], set()
    for p in papers:
        title_key = p["title"].strip().lower()
        if title_key in seen_titles or not is_relevant(p["title"], p["abstract"], learned):
            continue
        seen_titles.add(title_key)
        authors = re.sub(r"\s+", " ", re.sub(r",\s*", ", ", p["authors"])).strip()
        relevant.append({**p, "authors": authors})
    return relevant
