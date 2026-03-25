"""
parse_nber_emails.py — Reference implementation for parsing NBER email digests.

This script shows how to extract paper titles, URLs, and authors from the
NBER weekly email digest HTML. It's used as a template by the skill runner
(Claude reads the emails via Outlook MCP and applies this parsing logic).

Usage (standalone, for testing with saved email files):
    python parse_nber_emails.py file1.txt file2.txt ...

Each file should contain the JSON output from read_resource (Outlook MCP):
    [{"type": "text", "text": "<email-json-string>"}]
"""

import json
import re
import sys
import base64
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup


def decode_sophos_url(href: str) -> str | None:
    """Decode a Sophos-wrapped URL by extracting the base64 `u` parameter."""
    try:
        qs = parse_qs(urlparse(href).query)
        u = qs.get("u", [None])[0]
        if u:
            decoded = base64.b64decode(u + "==").decode("utf-8", errors="replace")
            return decoded.split("?")[0]
    except Exception:
        pass
    if "nber.org/papers" in href:
        return href.split("?")[0]
    return None


def parse_email_file(filepath: str) -> list[dict]:
    """Parse a single saved email file and return a list of paper dicts."""
    with open(filepath, encoding="utf-8") as f:
        raw = f.read()

    outer = json.loads(raw)
    email = json.loads(outer[0]["text"])
    html = email["body"]["content"]
    soup = BeautifulSoup(html, "html.parser")

    papers = {}
    for cell in soup.select("td.text2"):
        link = cell.select_one("a.link-u")
        if not link:
            continue
        href = link.get("href", "")
        url = decode_sophos_url(href)
        if not url or "nber.org/papers/w" not in url:
            continue
        url = url.rstrip("/")
        title = link.get_text(strip=True)

        # Authors are after the <br> tag, with a trailing " #NNNNN" paper number
        br = cell.find("br")
        authors_raw = ""
        if br and br.next_sibling:
            authors_raw = str(br.next_sibling).strip()
        authors = re.sub(r"\s*#\d+\s*$", "", authors_raw).strip()

        if url not in papers:
            papers[url] = {"title": title, "url": url, "authors": authors, "abstract": ""}

    return list(papers.values())


def paper_num(p: dict) -> int:
    m = re.search(r"/w(\d+)", p["url"])
    return int(m.group(1)) if m else 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_nber_emails.py file1.txt [file2.txt ...]")
        sys.exit(1)

    all_papers: dict[str, dict] = {}
    for filepath in sys.argv[1:]:
        for p in parse_email_file(filepath):
            if p["url"] not in all_papers:
                all_papers[p["url"]] = p

    papers = sorted(all_papers.values(), key=paper_num, reverse=True)
    print(f"Total unique NBER papers found: {len(papers)}")
    print("Newest 3:")
    for p in papers[:3]:
        print(f"  {p['url']}  |  {p['title'][:70]}")

    with open("nber_email_papers.json", "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)
    print("Saved nber_email_papers.json")


if __name__ == "__main__":
    main()
