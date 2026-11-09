# Retirement Papers

Automates the biweekly working paper review. It finds new working papers from NBER, IZA, CESifo, IFS and CRR, keeps the retirement-relevant ones using keyword matching, and writes a Microsoft Teams post with titles, links, authors and abstracts.

## Setup

```bash
pip install -r requirements.txt
```

## Running it

In Claude Code, say *"run the retirement paper check"* or *"check papers since 26 October"*. Or run it directly (from any directory):

```bash
python scripts/run.py --since 2026-10-26   # papers since a date
python scripts/run.py                      # papers since the last confirmed run
python scripts/run.py --confirm            # after reviewing: remember this run's date
```

A run takes a couple of minutes and writes `teams_post.md`, ready to paste into Teams. It doesn't change `state.json`; `--confirm` does, so the next run picks up where this one ended. On a first run (no `state.json`), give a start date with `--since`.

## How it works

| Script | Does |
|--------|------|
| `scripts/run.py` | The command you run: scrape → filter → write the post |
| `scripts/scrape.py` | Fetches papers since the start date, with abstracts |
| `scripts/filter.py` | Keyword lists and relevance filter |
| `scripts/format_post.py` | Formats the Teams post |

Each source is filtered on a day-level date: NBER's release date, the day IZA/CESifo/IFS papers were added to EconPapers, and CRR's publication date. IZA uploads to EconPapers in monthly batches, so a month of IZA papers can arrive at once.

Corrections made during review are logged to `feedback/overrides.json`. Suggested keywords from those corrections feed back into the filter.

## Troubleshooting

- **A source fails or returns nothing**: the site may have changed its HTML. The post lists failed sources for manual checking, and details are in `scrape_errors.log`.
- **Filter seems wrong**: adjust the keyword lists at the top of `scripts/filter.py`; `references/relevance_guide.md` describes what should count as relevant.
- **Start from a different date**: edit `last_checked` in `state.json`, or pass `--since`.
