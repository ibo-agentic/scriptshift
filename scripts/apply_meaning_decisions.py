"""Apply the author's decisions from data/main/meaning_duplicates.csv.

A decision that starts with "drop <item_id>" removes that item from the main set:
  - its 5 rows are removed from data/main/main_items.csv (refused if it already has Bangla text)
  - data/main/eligible_pool.csv: selected = 0, note filled, batch numbers of the remaining items recomputed
  - data/main/replacements.csv: one log row per dropped item, replaced_by empty (there are no spare items left)
  - the old files are first copied to data/main/backup_before_meaning_dedup/ (an existing backup folder is never
    overwritten; data/main/backup_before_dedup/ is not touched)
Rule (PLAN.md section 4): a pair is a duplicate only if it asks the same question with the same text values; a different
number, date, season or place makes it a different question, and sharing only an entity is not a duplicate.
Decisions "keep both" change nothing.

usage: python scripts/apply_meaning_decisions.py [--dry-run]
"""
import argparse
import csv
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN, POOL = ROOT / "data" / "main" / "main_items.csv", ROOT / "data" / "main" / "eligible_pool.csv"
REPL, DEC = ROOT / "data" / "main" / "replacements.csv", ROOT / "data" / "main" / "meaning_duplicates.csv"
BACKUP = ROOT / "data" / "main" / "backup_before_meaning_dedup"
BATCH = 40


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    cli = ap.parse_args()

    drops = {}                                                    # item -> (other item, decision text)
    for r in csv.DictReader(open(DEC, encoding="utf-8-sig", newline="")):
        m = re.match(r"drop (\S+)", r["decision"].strip())
        if m:
            item = m.group(1)
            other = r["item_b"] if item == r["item_a"] else r["item_a"]
            drops[item] = (other, r["decision"].strip())
    print(f"decisions to apply: {len(drops)} -> {sorted(drops)}")

    rows = list(csv.DictReader(open(MAIN, encoding="utf-8-sig", newline="")))
    fields = list(rows[0].keys())
    present = {r["item_id"] for r in rows}
    already = [i for i in drops if i not in present]
    if already:
        sys.exit(f"already removed or unknown: {already} (nothing done)")
    for r in rows:
        if r["item_id"] in drops and r["form"] != "en" and r["query"].strip():
            sys.exit(f"{r['item_id']} {r['form']} already has Bangla text: refusing to remove it")
    if cli.dry_run:
        print("dry run: nothing changed")
        return
    if BACKUP.exists():
        sys.exit(f"{BACKUP} exists: refusing to overwrite a backup")
    BACKUP.mkdir()
    for p in (MAIN, POOL, REPL, DEC):
        shutil.copy2(p, BACKUP / p.name)

    new_rows = [r for r in rows if r["item_id"] not in drops]
    order = list(dict.fromkeys(r["item_id"] for r in new_rows))
    with open(MAIN, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(new_rows)

    batch_of = {iid: i // BATCH + 1 for i, iid in enumerate(order)}
    pool = list(csv.DictReader(open(POOL, encoding="utf-8-sig", newline="")))
    pool_fields = list(pool[0].keys())
    for p in pool:
        iid = p["item_id"]
        p["selected"] = int(iid in batch_of)
        p["batch"] = batch_of.get(iid, "")
        if iid in drops:
            p["note"] = f"dropped (duplicate by meaning of {drops[iid][0]}); no spare left"
    with open(POOL, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pool_fields)
        w.writeheader()
        w.writerows(pool)

    today = date.today().isoformat()
    with open(REPL, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        for item, (other, text) in sorted(drops.items()):
            category = "simple_python" if item.startswith("simple") else "multiple"
            w.writerow([today, category, item, "", f"duplicate by meaning of {other}: same question and same text values; "
                        f"NO SPARE LEFT, so not replaced ({text})", f"author (decided {today})"])
    n_s = sum(1 for i in order if i.startswith("simple"))
    print(f"applied. backup: {BACKUP}")
    print(f"main_items.csv: {len(order)} items = {n_s} simple_python + {len(order) - n_s} multiple, {len(new_rows)} rows")


if __name__ == "__main__":
    main()
