# Retirement Papers — Setup Guide

This tool automates the biweekly working paper review. It scrapes available sources, filters for retirement-relevant papers using keyword matching, and generates a formatted Microsoft Teams post.

## First-time setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. First run

You don't need to create any config files manually. On your first run, Claude will ask you one question:

> *"How far back should I check? Give me either a date (e.g. 'since January 1') or the last paper URLs you have from a colleague."*

Claude will then create `state.json` for you automatically and run the check. After each run, `state.json` is updated with your new checkpoints so you don't need to touch it again.

**If you're taking over from a colleague**, they can share their "checked until" info (printed at the end of every run) and you can paste it in when prompted.

### 3. Claude Code permissions

The first time you run this skill, Claude Code will ask permission for web fetches and Outlook email access. Accept these as they come up — they'll be remembered for future runs.

---

## Every two weeks: running the check

In Claude Code, just say:

> "Run the retirement paper check"

Claude Code handles everything: fetching NBER emails, scraping, filtering, and presenting the Teams post for your review. Once you confirm, it updates the checkpoints.

Or run manually (see pipeline below). You can also pass a date or checkpoint list — see **Advanced: checkpoint overrides** below.

---

## Sources

| Source | Automation | Method |
|--------|-----------|--------|
| IZA | Automated | HTML scraping, URL checkpoint |
| CRR | Automated | HTML scraping, **date checkpoint** |
| NBER | Semi-automated | Outlook MCP email digest |

### NBER

NBER papers arrive via a weekly email digest from `bulletin@nber.org`. Claude fetches these emails via the Microsoft 365 Outlook MCP tool before running the scraper. The checkpoint is the URL of the highest-numbered paper seen (e.g. `https://www.nber.org/papers/w34916`).

If no emails are found (e.g. not subscribed), NBER is added to the manual-check list.

### CRR

CRR's listing isn't in strict chronological order, so it uses **date-based** filtering rather than URL matching. The `checked_until_date` field in `state.json` is the checkpoint — `checked_until_url` is unused for CRR and left blank.

---

## Pipeline

```
1. Claude fetches NBER emails via Outlook MCP → nber_email_papers.json
2. python scripts/scrape.py                   → papers_raw.json
3. python scripts/filter.py                   → papers_relevant.json
4. python scripts/format_post.py              → teams_post.md, checked_until_update.txt
5. (user confirms post looks correct)
6. python scripts/update_state.py             → state.json (checkpoints advanced)
```

### Filter logic

1. **Keyword filter**: Papers with strong retirement keywords (pension, annuity, 401k, etc.) are included directly. Papers with weak signals (older people, life expectancy, etc.) are included as borderline. Papers with no signals are excluded. See `references/relevance_guide.md` for the full keyword lists and borderline examples.
2. **Abstract fetch**: NBER papers from the email digest arrive without abstracts; these are fetched after filtering.
3. **Deduplication**: Papers are deduplicated by URL first, then by title (catches cross-posting between IZA and NBER).

---

## Checkpoints (`state.json`)

| Source | Checkpoint field used | Format |
|--------|----------------------|--------|
| IZA | `checked_until_url` | Full IZA paper URL |
| NBER | `checked_until_url` | `https://www.nber.org/papers/wNNNNN` |
| CRR | `checked_until_date` | `YYYY-MM-DD` |

After a successful run, `update_state.py` advances the URL checkpoint for IZA and NBER, and the date checkpoint for CRR.

---

## Advanced: checkpoint overrides

Both options override `state.json` for the current run only — `state.json` is only updated after you confirm the post.

**Check all papers since a specific date:**
```bash
python scripts/scrape.py --since 2026-01-01
```
Useful for a first run, after a long gap, or when you know the date but not the URL.

**Resume from someone else's checkpoint list:**
```bash
python scripts/scrape.py --checkpoints '{"iza": "https://www.iza.org/publications/dp/18356/...", "crr": "2026-01-05", "nber": "https://www.nber.org/papers/w34500"}'
```
Values are full paper URLs for IZA/NBER, or `YYYY-MM-DD` dates for CRR. You can include just the sources you want to override; others will use `state.json`.

When running via Claude Code, just say something like *"check papers since January 1"* or *"here's the last checked list: IZA w18356, NBER w34500, CRR 2026-01-05"* and Claude will use the right flag.

---

## Outputs

Each run produces:

| File | Contents |
|------|----------|
| `teams_post.md` | Formatted post ready to paste into Teams |
| `last_seen.md` | Most recently published paper per source (title + link) |
| `checked_until_update.txt` | New checkpoint values (for reference / manual state update) |
| `papers_relevant.json` | All relevant papers found (machine-readable) |

---

## Troubleshooting

**A scraper returns 0 papers**: The site may have changed its HTML structure. Check `scrape_errors.log` and update the CSS selectors in `scripts/scrape.py`.

**Filter seems wrong**: Adjust the keyword lists at the top of `scripts/filter.py`, or edit `references/relevance_guide.md` for guidance on what should be included.

**CRR checkpoint is wrong**: Edit `checked_until_date` in `state.json` directly (format: `YYYY-MM-DD`).

**Other checkpoint is wrong**: Edit `checked_until_url` in `state.json` for the relevant source.
