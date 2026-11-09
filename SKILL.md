---
name: retirement-papers
description: >
  Automates the biweekly working paper review for a retirement research team.
  Scrapes 5 sources (NBER, IZA, CESifo, IFS, CRR) for papers since a date,
  filters for retirement-relevant papers using keyword matching, and formats
  a Microsoft Teams post with titles, links, authors, and abstracts. Use this
  skill whenever the user asks to check for new working papers, run the paper
  scan, update the Teams post, do the paper roundup, or mentions the
  biweekly/fortnightly paper review. Also use when asking "any new retirement
  papers?", "papers since <date>", "what's new on NBER/IZA/CESifo/IFS/CRR",
  or similar.
---

# Retirement Papers Skill

Automates the RSA biweekly working paper review across 5 economics sources (NBER, IZA, CESifo, IFS, CRR), producing a summary post for a shared Teams channel.

Everything is date-based: a run finds papers published on or after a start date, and `state.json` just remembers the date of the last confirmed run.

## Workflow

### 1. Setup

**Skill directory and Python**: use the paths stored in memory. If either is missing, ask the user (*"Where is this skill installed?"*, *"Where is your Python executable?"*) and save the answer to memory. Never search for Python — always use the stored path.

```bash
"<python-path>" -m pip install -q -r <skill-directory>/requirements.txt
```

### 2. Run

```bash
"<python-path>" <skill-directory>/scripts/run.py --since 2026-10-26   # user gave a date
"<python-path>" <skill-directory>/scripts/run.py                      # since the last confirmed run
```

If the user gives a date (e.g. "since 26/10"), pass it with `--since` — never convert dates to paper numbers. With no `--since`, the run starts from `last_checked` in `state.json`; if there's no `state.json` yet, ask the user for a start date.

A run takes a couple of minutes. It scrapes all sources, filters, and writes to the skill directory:
- `teams_post.md` — the post, ready to paste into Teams
- `papers_relevant.json` / `papers_raw.json` — the relevant / all scraped papers
- `last_run.json` — this run's dates, used by `--confirm`
- `scrape_errors.log` — warnings, if anything failed

If a source fails, the run carries on and the post lists it under "check manually".

### 3. Review with the user

Show the post (the run prints it) and ask: *"Does this look right? Any papers to add or remove?"*

If the user flags changes, edit `teams_post.md` and **log the feedback** (see "Learning from feedback").

### 4. Confirm

Once the user is happy:
```bash
"<python-path>" <skill-directory>/scripts/run.py --confirm
```
This sets `last_checked` in `state.json` to the run's date, so the next run starts where this one ended.

---

## Sources and dates

Each source is filtered on a day-level date:

| Source | Listing from | Date used | Link in post |
|--------|-------------|-----------|--------------|
| NBER | NBER API | Release date (nber.org paper metadata) | nber.org |
| IZA | EconPapers | Day added to EconPapers (hidden `EPDATE` field) | iza.org |
| CESifo | EconPapers | Day added to EconPapers | EconPapers |
| IFS | EconPapers | Day added to EconPapers | EconPapers |
| CRR | crr.bc.edu | Publication date | crr.bc.edu |

- **IZA uploads to EconPapers in monthly bulk**, so a whole month of IZA papers can appear on one day.
- **IFS papers have no abstracts** on EconPapers, so they're filtered on title only.
- EconPapers also lists a few mis-numbered IFS papers (e.g. `W46/46`) at the top of its listing; date filtering handles these correctly.

To add an EconPapers source, add an entry to `ECONPAPERS_SOURCES` and `SOURCES` in `scripts/scrape.py`.

---

## Learning from feedback

The keyword filter improves over time by learning from user corrections. Each time the user adds or removes a paper during review, log the decision to `feedback/overrides.json`:

```json
[
  {
    "date": "2026-03-25",
    "action": "exclude",
    "title": "Paper Title Here",
    "reason": "not about older workers",
    "keywords_present": ["unemployment", "labour force participation"]
  },
  {
    "date": "2026-03-25",
    "action": "include",
    "title": "Another Paper Title",
    "reason": "user said it's relevant — about pension fund governance",
    "suggested_keyword": "pension fund governance"
  }
]
```

**How this feeds back into filtering:**
- `filter.py` reads `feedback/overrides.json` on every run. Any `suggested_keyword` values from "include" actions count as weak positive signals.
- After 3+ similar corrections accumulate, suggest to the user that the keyword be added permanently to `filter.py`. Don't modify `filter.py` automatically — a bad keyword can flood the results.
- For "exclude" corrections, note the pattern but don't auto-add negative keywords. Exclusions are harder to get right and more likely to suppress legitimate papers.

---

## How the filter works

Keyword lists are at the top of `scripts/filter.py`, matched against title + abstract:
- **Strong** keyword → included
- **Weak** keyword (or learned from feedback) → included, unless a **negative** keyword also matches
- **Hard negative** → always excluded

Duplicates (same title, e.g. cross-posted to IZA and CESifo) are removed.

`references/relevance_guide.md` has guidance on what counts as relevant, based on the team's Zotero tags. Read it when debugging relevance decisions.

---

## Troubleshooting

- **A source returns 0 papers or fails**: the site's HTML may have changed. Check `scrape_errors.log`, tell the user, and they can check that source manually.
- **Filter too strict/loose**: adjust the keyword lists in `scripts/filter.py` (with the user's agreement), and check `feedback/overrides.json` for accumulated corrections.
- **EconPapers returns 403 or times out**: the site may be temporarily down. Retry after a few minutes.
