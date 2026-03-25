"""
update_state.py — Updates state.json with new checked_until URLs after a successful run.
"""

import json
from datetime import date

source_map = {
    "IZA": "iza",
    "CRR": "crr",
    "NBER": "nber",
}


def main():
    with open("state.json", encoding="utf-8") as f:
        state = json.load(f)

    with open("papers_raw.json", encoding="utf-8") as f:
        papers_raw = json.load(f)

    today = date.today().isoformat()

    # First paper per source = most recent = new checkpoint
    first_by_source: dict[str, str] = {}
    for p in papers_raw:
        src = p["source"]
        if src not in first_by_source:
            first_by_source[src] = p["url"]

    updated = []
    for display_name, key in source_map.items():
        if display_name in first_by_source:
            if key == "crr":
                # CRR uses date-based filtering — update the date, not the URL
                state["sources"][key]["checked_until_date"] = today
                updated.append(f"  {display_name}: date -> {today}")
            else:
                new_url = first_by_source[display_name]
                state["sources"][key]["checked_until_url"] = new_url
                state["sources"][key]["checked_until_date"] = today
                updated.append(f"  {display_name}: {new_url[:70]}...")

    with open("state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    if updated:
        print("Updated checkpoints:")
        for line in updated:
            print(line)
    else:
        print("No checkpoints updated (no new papers found).")

    print("state.json saved.")


if __name__ == "__main__":
    main()
