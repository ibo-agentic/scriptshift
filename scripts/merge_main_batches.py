"""Merge the filled main-set writing sheets (data/main/sheets/batch_XX.xlsx) into data/main/main_items.csv.

Like merge_bangla.py, but for the 6 main batches:
  - matches rows by item_id + form (bn_native, bn_roman, bn_mixed, bn_partial), skips the EXAMPLE row
  - changes only the `query` column; every other column is checked to be unchanged
  - an empty cell in the sheet leaves the CSV cell as it is
  - a CSV cell that is already filled is only changed with --overwrite (otherwise the difference is reported)
  - the CSV is written as UTF-8 with BOM, through a temp file, so a failed write never leaves a half-written file

Reported per batch: items, forms filled, empty cells, items whose note does not say "author checked".
Warnings (never block the merge; the author decides):
  - English text in the sheet differs from the English query in the CSV
  - bn_native / bn_partial without any Bangla-script character; bn_roman / bn_mixed with Bangla-script characters
  - Bangla digits (০-৯) anywhere: numbers must be English digits 0-9 (or a word, as in the English query)
  - bn_partial missing one of the "Must keep" values, which must be copied exactly in English

usage: python scripts/merge_main_batches.py [sheet.xlsx ...] [--csv data/main/main_items.csv] [--overwrite] [--dry-run]
       (no sheets given = all data/main/sheets/batch_*.xlsx)
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_writing_sheets import must_keep
from merge_bangla import read_sheet

ROOT = Path(__file__).resolve().parent.parent
SHEET_COL = {"bn_native": "D", "bn_roman": "E", "bn_mixed": "F", "bn_partial": "G"}
BANGLA = re.compile("[ঀ-৿]")
BANGLA_DIGITS = re.compile("[০-৯]")
ITEM_ID = re.compile(r"^(simple_python|multiple)_\d+$")
MAX_SHOWN = 40


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheets", nargs="*")
    ap.add_argument("--csv", default=str(ROOT / "data" / "main" / "main_items.csv"))
    ap.add_argument("--overwrite", action="store_true", help="replace CSV cells that are already filled")
    ap.add_argument("--dry-run", action="store_true", help="report only, do not write the CSV")
    cli = ap.parse_args()
    sheets = sorted(cli.sheets or glob.glob(str(ROOT / "data" / "main" / "sheets" / "batch_*.xlsx")))
    if not sheets:
        sys.exit("no sheets found")

    csv_path = Path(cli.csv)
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    original = [dict(r) for r in rows]
    by_key = {(r["item_id"], r["form"]): r for r in rows}

    warnings, totals = [], dict(items=0, filled=0, empty=0, set=0, updated=0, kept_differs=0, unchecked=0)
    print(f"{'sheet':<16}{'items':>6}{'forms filled':>14}{'empty cells':>13}{'no \"author checked\"':>22}")
    for path in sheets:
        sheet = read_sheet(path, "Write here")
        items = [r for r in sheet[1:] if ITEM_ID.match(r.get("A", ""))]
        filled = empty = unchecked = 0
        for r in items:
            iid = r["A"]
            if (iid, "en") not in by_key:
                warnings.append(f"{Path(path).name}: {iid} is not in {csv_path.name}, skipped")
                continue
            en = by_key[(iid, "en")]["query"]
            if r.get("B", "").strip() != en.strip():
                warnings.append(f"{iid}: English in the sheet differs from the CSV")
            gt = json.loads(by_key[(iid, "en")]["gt_call_json"])
            any_filled = False
            for form, col in SHEET_COL.items():
                text = r.get(col, "").strip()
                if not text:
                    empty += 1
                    continue
                any_filled = True
                filled += 1
                if form in ("bn_native", "bn_partial") and not BANGLA.search(text):
                    warnings.append(f"{iid} {form}: no Bangla-script character")
                if form in ("bn_roman", "bn_mixed") and BANGLA.search(text):
                    warnings.append(f"{iid} {form}: contains Bangla-script characters")
                if BANGLA_DIGITS.search(text):
                    warnings.append(f"{iid} {form}: Bangla digits, use English digits 0-9")
                if form == "bn_partial":
                    for line in must_keep(gt, en):
                        value = line.split(" = ", 1)[1]
                        for part in value.split(", ") if "," in value and value not in text else [value]:
                            if part not in text:
                                warnings.append(f"{iid} bn_partial: Must keep value {part!r} not found exactly")
                cur = by_key[(iid, form)]["query"]
                if cur == text:
                    continue
                if not cur:
                    by_key[(iid, form)]["query"] = text
                    totals["set"] += 1
                elif cli.overwrite:
                    by_key[(iid, form)]["query"] = text
                    totals["updated"] += 1
                else:
                    totals["kept_differs"] += 1
                    warnings.append(f"{iid} {form}: CSV already has a different text, kept (use --overwrite to replace)")
            if any_filled and "author checked" not in r.get("H", "").lower():
                unchecked += 1
        print(f"{Path(path).name:<16}{len(items):>6}{filled:>14}{empty:>13}{unchecked:>22}")
        totals["items"] += len(items)
        totals["filled"] += filled
        totals["empty"] += empty
        totals["unchecked"] += unchecked

    for a, b in zip(original, rows):
        assert all(a[k] == b[k] for k in fields if k != "query"), "a column other than query changed"
    print(f"\ntotal: {totals['items']} items, {totals['filled']} forms filled, {totals['empty']} empty cells, "
          f"{totals['unchecked']} filled items without 'author checked'")
    print(f"CSV cells: {totals['set']} newly set, {totals['updated']} overwritten, {totals['kept_differs']} differ and kept")
    print(f"warnings: {len(warnings)}")
    for w in warnings[:MAX_SHOWN]:
        print("  -", w)
    if len(warnings) > MAX_SHOWN:
        print(f"  ... {len(warnings) - MAX_SHOWN} more")

    if cli.dry_run:
        print("dry run: CSV not written")
        return
    tmp = csv_path.with_suffix(".csv.tmp")
    try:
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, csv_path)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        sys.exit(f"cannot write {csv_path}: close it in Excel (or any program that has it open) and run again")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
