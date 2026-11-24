# Retirement Papers

Automates the biweekly working paper review. It finds new working papers from NBER, IZA, CESifo, IFS and CRR, keeps the retirement-relevant ones using keyword matching, and produces a Microsoft Teams post with titles, links, authors and abstracts.

Several people take turns running the review, so there are no saved checkpoints: you always say which date to check from (usually the date of the last post).

## Setup

```bash
git pull                          # get the team's latest keywords and feedback
pip install -r requirements.txt
```

## Running it

In Claude Code, say *"check papers since 26 October"*. Claude runs the check, shows the post in the chat, and asks whether to add or remove anything. Or run it directly (from any directory):

```bash
python scripts/run.py --since 2026-10-26
```

A run takes about 4 minutes and prints the post, ready to paste into Teams.

## How it works

| Script | Does |
|--------|------|
| `scripts/run.py` | The command you run: scrape → filter → print the post |
| `scripts/scrape.py` | Fetches papers since the start date, with abstracts |
| `scripts/filter.py` | Keyword lists and relevance filter |
| `scripts/format_post.py` | Formats the Teams post |

Each source is filtered on a day-level date: NBER's release date, the day IZA/CESifo/IFS papers were added to EconPapers, and CRR's publication date. IZA uploads to EconPapers in monthly batches, so a month of IZA papers can arrive at once.

Corrections made during review are logged to `feedback/overrides.json`, which is shared in git so the whole rota benefits. Commit and push it after your review.

## Troubleshooting

- **A source fails or returns nothing**: the site may have changed its HTML. The post lists failed sources for manual checking, and details are in `scrape_errors.log`.
- **Filter seems wrong**: adjust the keyword lists at the top of `scripts/filter.py`; `references/relevance_guide.md` describes what should count as relevant.
