---
name: retirement-papers
description: >
  Automates the biweekly working paper review for a retirement research team.
  Scrapes 3 sources (NBER, IZA, CRR), filters for retirement-relevant papers
  using keyword matching, and formats a Microsoft Teams post with titles,
  links, authors, and abstracts. Use this skill whenever the user asks to check
  for new working papers, run the paper scan, update the Teams post, do the
  paper roundup, or mentions the biweekly/fortnightly paper review. Also use
  when updating "checked until" checkpoints, or when asking "any new retirement
  papers?", "what's new on NBER/IZA/CRR", or similar.
---

# Retirement Papers Skill

Automates the RSA biweekly working paper review across 3 economics sources (NBER, IZA, CRR), providing a summary post for a shared Teams channel.

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
> **(a)** *check all papers since a date you give me (e.g. "since January 1"), or*
> **(b)** *start from specific checkpoint URLs if you have them (e.g. from a colleague's last run).*
> *Which would you prefer?"*

Then create `state.json` from `state.example.json`:
- If the user gives a **date**: copy the template, set all three `checked_until_date` fields to that date, leave `checked_until_url` fields at their defaults, and run with `--since <date>`.
- If the user gives **checkpoint URLs/papers**: copy the template and fill in the URLs/dates they provide for each source.
- If the user isn't sure: suggest starting with a date 2 weeks ago.

### 2. Fetch NBER email papers (before scraping)

NBER papers arrive via weekly email digest from `bulletin@nber.org`, fetched through the Microsoft 365 Outlook MCP tool. This step requires the **Claude AI Microsoft 365** MCP to be active.

**If the MCP is not available**, tell the user:

> *"I need the Microsoft 365 MCP to fetch NBER emails. To activate it:*
> *1. Open Claude Code settings (or your Claude.ai integration settings)*
> *2. Enable the 'Claude AI Microsoft 365' MCP server*
> *3. Start a new Claude Code session so the MCP loads*
> *Then run the paper check again. I'll skip NBER for now and continue with IZA and CRR."*

Proceed with the other sources — don't block the whole run on NBER.

**When the MCP is available:**

1. Read `state.json` to get the NBER checkpoint date (extract from `checked_until_url` if it starts with `nber_email_YYYY-MM-DD`, otherwise use `checked_until_date`).
2. Search for NBER emails since that date:
   ```
   outlook_email_search(query="Latest NBER Research", sender="bulletin@nber.org", afterDateTime=<checkpoint_date>)
   ```
3. For each email found (process all, most-recent first), read the email using `read_resource`, then parse it. Read `scripts/parse_nber_emails.py` for the reference implementation — it handles the Outlook JSON structure, Sophos URL decoding, and author extraction. Follow that same logic.
4. Combine papers from all emails, deduplicate by URL, sort newest-first (by paper number, highest first).
5. Save to `nber_email_papers.json` as a JSON array of `{"title", "url", "authors"}` objects.

If no emails are found (e.g. user isn't subscribed), note it and continue. The scraper falls back gracefully.

### 3. Scrape new papers

**Standard run** (uses checkpoints from `state.json`):
```bash
python scripts/scrape.py
```

**Check all papers since a specific date** (overrides checkpoints for this run only):
```bash
python scripts/scrape.py --since 2026-01-01
```

**Provide your own checkpoint list** (e.g. resuming from a colleague's last check):
```bash
python scripts/scrape.py --checkpoints '{"iza": "https://www.iza.org/publications/dp/18356/...", "crr": "2026-01-05", "nber": "https://www.nber.org/papers/w34500"}'
```
Each value is either a full URL (for IZA/NBER) or a `YYYY-MM-DD` date (for CRR).

`--since` and `--checkpoints` override `state.json` for the current run only. `state.json` is only permanently updated by `update_state.py` after user confirmation.

This produces `papers_raw.json` and `scrape_summary.json`. If any source fails, note it and continue with the others.

### 4. Filter for relevance
```bash
python scripts/filter.py
```
This reads `papers_raw.json`, applies a keyword filter (strong signals → include, weak signals → include as borderline, no signals → exclude), fetches missing abstracts, deduplicates by URL then title, and writes `papers_relevant.json`.

The filter also reads `feedback/overrides.json` (if it exists) to apply learned keywords from past user corrections. See "Learning from feedback" below.

### 5. Format Teams post
```bash
python scripts/format_post.py
```
This writes:
- `teams_post.md` — the full post body ready to copy into Teams (includes "checked until" info at the bottom)
- `last_seen.md` — the most recently published paper per source (title + link)
- `checked_until_update.txt` — new checkpoint values for reference

### 6. Review with the user
- Print the contents of `teams_post.md` so the user can review and copy it
- Print the contents of `last_seen.md` — this shows the newest paper found per source
- Print the contents of `checked_until_update.txt`
- Ask: *"Does this look right? Any papers to add or remove?"*

**If the user flags changes** (e.g. "remove the one about X" or "this paper about Y is missing"), apply their edits to the post and **log the feedback** — see "Learning from feedback" below.

### 7. Update state
Once the user confirms, run:
```bash
python scripts/update_state.py
```
This updates `state.json` with the new "checked_until" URLs from `checked_until_update.txt`.

---

## Learning from feedback

The keyword filter improves over time by learning from user corrections. Each time the user adds or removes a paper during review (step 6), log the decision to `feedback/overrides.json`:

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
    "iza": {
      "name": "IZA Discussion Papers",
      "checked_until_url": "https://www.iza.org/publications/dp/18356/...",
      "checked_until_date": "2025-01-05"
    },
    "crr": {
      "name": "CRR (Boston College)",
      "checked_until_url": "",
      "checked_until_date": "2025-01-05"
    },
    "nber": {
      "name": "NBER Working Papers",
      "checked_until_url": "nber_email_2025-01-05",
      "checked_until_date": "2025-01-05",
      "note": "NBER is accessed via weekly email digest. See NBER handling below."
    }
  }
}
```

---

## NBER handling

NBER papers are fetched from the weekly email digest (`bulletin@nber.org`) via the Microsoft 365 Outlook MCP tool. This happens in step 2 (before running scrape.py).

The NBER checkpoint in `state.json` can be either:
- `nber_email_YYYY-MM-DD` — date-based (legacy), means "all papers from emails after this date"
- `https://www.nber.org/papers/wNNNNN` — URL of the last seen paper (papers with number ≤ this are skipped)

After a successful NBER scrape, the checkpoint becomes the URL of the highest-numbered paper found (e.g. `https://www.nber.org/papers/w34897`).

---

## Reference files

- `references/relevance_guide.md` — Detailed guidance on what counts as relevant, based on the team's Zotero tags. Read this before running filter.py if you need to debug relevance decisions.
- `state.example.json` — Template state file
- `scripts/parse_nber_emails.py` — Reference implementation for parsing NBER email digests. Read this when executing step 2 to understand the JSON structure and URL decoding logic.

---

## Troubleshooting

- **Scraper returns 0 papers for a source**: The site's HTML structure may have changed. Check `scrape_errors.log` and report to user. They may need to check that source manually.
- **Filter seems too strict/loose**: The filter uses a tiered keyword system — strong keywords auto-include a paper, weak keywords mark it as borderline, and negative keywords suppress weak (but not strong) signals. Adjust these lists at the top of `scripts/filter.py`, or read `references/relevance_guide.md` for guidance. Also check `feedback/overrides.json` for accumulated user corrections that may suggest new keywords.
- **Microsoft 365 MCP not available**: See step 2 above for activation instructions.
- **NBER site down / no emails found**: The scraper falls back gracefully — NBER appears in the "check manually" section of the Teams post.
