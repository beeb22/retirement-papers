---
name: retirement-papers
description: >
  Automates the biweekly working paper review for a retirement research team.
  Scrapes 5 sources (NBER, IZA, CESifo, IFS via EconPapers; CRR directly),
  filters for retirement-relevant papers using keyword matching, and formats
  a Microsoft Teams post with titles, links, authors, and abstracts. Use this
  skill whenever the user asks to check for new working papers, run the paper
  scan, update the Teams post, do the paper roundup, or mentions the
  biweekly/fortnightly paper review. Also use when updating "checked until"
  checkpoints, or when asking "any new retirement papers?", "what's new on
  NBER/IZA/CESifo/IFS/CRR", or similar.
---

# Retirement Papers Skill

Automates the RSA biweekly working paper review across 5 economics sources (NBER, IZA, CESifo, IFS, CRR), providing a summary post for a shared Teams channel.

Four sources (NBER, IZA, CESifo, IFS) are scraped via EconPapers/RePEc listing pages. CRR is scraped directly from its website. Abstracts are fetched from EconPapers detail pages for papers that pass the keyword filter (IFS papers have no abstracts on EconPapers — these appear without abstracts in the Teams post).

## Workflow

When the user asks to run the paper check (or similar), do the following steps:

### 1. Check setup

**Skill directory**: All scripts and state files live in the skill's installation directory. If this is the first run (no `state.json` exists), ask: *"Where is this skill installed on your machine? (e.g. `C:\Users\you\.claude\skills\retirement-papers`)"* and use that path for all commands in this session. Save the path to memory so future sessions can use it directly.

If the path is already in memory, use it. All commands below should run from this directory.

**Python path**: Check your memory for the user's Python path before running any scripts. If not stored, ask: *"Where is your Python executable? (e.g. `C:\...\python3.12.exe`)"* and save it to memory before continuing. Never search for Python — always use the stored path directly.

```bash
cd <skill-directory>
"<python-path>" -m pip install -q -r requirements.txt
```

**First-run setup** (if `state.json` does not exist): Ask the user one question:

> *"This is your first run. I can either:*
> **(a)** *check all papers since a paper number/ID you give me (e.g. "NBER 34900, IZA 18400"), or*
> **(b)** *start from the checkpoint values in `state.example.json` (conservative — may fetch a large backlog).*
> *Which would you prefer?"*

Then create `state.json` from `state.example.json`:
- If the user gives **paper numbers**: copy the template and fill in the checkpoint URLs for each source using those numbers.
- If the user gives a **date**: copy the template, set all `checked_until_date` fields to that date, and for EconPapers sources use `--since` with the appropriate paper number.
- If the user isn't sure: suggest starting with recent paper numbers (check the EconPapers listing pages to find the current latest).

### 2. Scrape new papers

**Standard run** (uses checkpoints from `state.json`):
```bash
python scripts/scrape.py
```

**Override all checkpoints with a paper number** (e.g. to check everything after NBER w34900):
```bash
python scripts/scrape.py --since 34900
```
For EconPapers sources this is a paper number; for CRR it is a `YYYY-MM-DD` date.

**Provide per-source checkpoint overrides**:
```bash
python scripts/scrape.py --checkpoints '{"nber": "34900", "iza": "18400", "cesifo": "12500", "crr": "2026-01-01"}'
```
Values are paper numbers for EconPapers sources or `YYYY-MM-DD` dates for CRR.

`--since` and `--checkpoints` override `state.json` for the current run only. `state.json` is only permanently updated by `update_state.py` after user confirmation.

This produces `papers_raw.json` and `scrape_summary.json`. If any source fails, note it and continue with the others.

### 3. Filter for relevance
```bash
python scripts/filter.py
```
This reads `papers_raw.json`, applies a keyword filter (strong signals → include, weak signals → include as borderline, no signals → exclude), fetches missing abstracts from EconPapers detail pages, deduplicates by URL then title, and writes `papers_relevant.json`.

The filter also reads `feedback/overrides.json` (if it exists) to apply learned keywords from past user corrections. See "Learning from feedback" below.

**Note on abstracts**: Abstracts are fetched from EconPapers individual paper pages after filtering. NBER, IZA, and CESifo papers have abstracts on EconPapers. IFS papers do not — these appear without abstracts in the Teams post (the titles are descriptive enough for filtering). CRR abstracts are fetched directly from crr.bc.edu during scraping.

### 4. Format Teams post
```bash
python scripts/format_post.py
```
This writes:
- `teams_post.md` — the full post body ready to copy into Teams (includes "checked until" info at the bottom)
- `last_seen.md` — the most recently published paper per source (title + link)
- `checked_until_update.txt` — new checkpoint values for reference

### 5. Review with the user
- Print the contents of `teams_post.md` so the user can review and copy it
- Print the contents of `last_seen.md` — this shows the newest paper found per source
- Print the contents of `checked_until_update.txt`
- Ask: *"Does this look right? Any papers to add or remove?"*

**If the user flags changes** (e.g. "remove the one about X" or "this paper about Y is missing"), apply their edits to the post and **log the feedback** — see "Learning from feedback" below.

### 6. Update state
Once the user confirms, run:
```bash
python scripts/update_state.py
```
This updates `state.json` with the new "checked_until" URLs from `checked_until_update.txt`.

---

## Sources

All four EconPapers sources use a unified scraper (`scrape_econpapers()` in `scrape.py`). Each source is configured as an entry in `ECONPAPERS_SOURCES` with its RePEc handle, URL patterns, and ID format.

| Source | Backend | EconPapers path | Checkpoint type | Canonical URL pattern |
|--------|---------|-----------------|-----------------|----------------------|
| NBER | EconPapers | `nbrnberwo` | Paper number (int) | `https://www.nber.org/papers/w{number}` |
| IZA | EconPapers | `izaizadps` | Paper number (int) | `https://www.iza.org/publications/dp/{number}` |
| CESifo | EconPapers | `cesceswps` | Paper number (int) | EconPapers URL |
| IFS | EconPapers | `ifsifsewp` | Paper ID (string, e.g. `W26/14`) | EconPapers URL |
| CRR | Direct scrape | N/A | Date (`YYYY-MM-DD`) | crr.bc.edu URL |

To add a new EconPapers source, add an entry to `ECONPAPERS_SOURCES` in `scrape.py` and update the source maps in `format_post.py` and `update_state.py`.

---

## Learning from feedback

The keyword filter improves over time by learning from user corrections. Each time the user adds or removes a paper during review (step 5), log the decision to `feedback/overrides.json`:

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
- `filter.py` reads `feedback/overrides.json` at startup. Any `suggested_keyword` values from "include" actions are added as weak positive signals for that run.
- After 3+ similar corrections accumulate (e.g. multiple papers about "pension fund governance" manually included), suggest to the user that the keyword be added permanently to `filter.py`. Don't modify `filter.py` automatically — the user should confirm keyword changes because a bad keyword can flood the results.
- For "exclude" corrections, note the pattern but don't auto-add negative keywords. Exclusions are harder to get right and more likely to suppress legitimate papers.

This approach keeps the core keyword logic deterministic and transparent while allowing it to evolve with team preferences.

---

## State file format (`state.json`)

```json
{
  "sources": {
    "nber": {
      "name": "NBER Working Papers",
      "checked_until_url": "https://www.nber.org/papers/w34991",
      "checked_until_date": "2026-03-25"
    },
    "iza": {
      "name": "IZA Discussion Papers",
      "checked_until_url": "https://www.iza.org/publications/dp/18460",
      "checked_until_date": "2026-03-25"
    },
    "cesifo": {
      "name": "CESifo Working Papers",
      "checked_until_url": "https://econpapers.repec.org/paper/cesceswps/_5f12566.htm",
      "checked_until_date": "2026-03-25"
    },
    "ifs": {
      "name": "IFS Working Papers",
      "checked_until_url": "https://econpapers.repec.org/paper/ifsifsewp/cwp28_2f24.htm",
      "checked_until_date": "2026-03-25"
    },
    "crr": {
      "name": "CRR (Boston College)",
      "checked_until_url": "",
      "checked_until_date": "2026-03-25"
    }
  }
}
```

For EconPapers sources, the `checked_until_url` contains the canonical URL of the most recent paper seen. The scraper extracts the paper number from this URL and stops when it reaches that number on the listing page.

---

## Reference files

- `references/relevance_guide.md` — Detailed guidance on what counts as relevant, based on the team's Zotero tags. Read this before running filter.py if you need to debug relevance decisions.
- `state.example.json` — Template state file with all 5 sources.

---

## Troubleshooting

- **Scraper returns 0 papers for a source**: The EconPapers HTML structure may have changed (it uses `<dl>`/`<dt>`/`<dd>` tags). Check `scrape_errors.log` and report to user. They may need to check that source manually.
- **Filter seems too strict/loose**: The filter uses a tiered keyword system — strong keywords auto-include a paper, weak keywords mark it as borderline, and negative keywords suppress weak (but not strong) signals. Adjust these lists at the top of `scripts/filter.py`, or read `references/relevance_guide.md` for guidance. Also check `feedback/overrides.json` for accumulated user corrections that may suggest new keywords.
- **IFS papers missing abstracts**: This is expected. IFS does not publish abstracts to EconPapers. The titles are descriptive enough for keyword filtering. If needed, abstracts can be found on the IFS website (ifs.org.uk).
- **EconPapers returns 403 or times out**: The site may be temporarily down. Retry after a few minutes. The scraper logs errors to `scrape_errors.log` and continues with other sources.
