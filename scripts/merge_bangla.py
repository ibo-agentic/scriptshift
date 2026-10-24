"""Copy the Bangla queries from the writing sheet into data/pilot/pilot_items.csv.

Matches rows by item_id + form, fills only the `query` column, skips the EXAMPLE row.
Reads the .xlsx with the standard library (no openpyxl needed).
"""
import csv
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "pilot" / "pilot_items.csv"
SHEET_COL = {"bn_native": "D", "bn_roman": "E", "bn_mixed": "F", "bn_partial": "G"}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def read_sheet(path, sheet_name):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    for s in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
        if s.get("name") != sheet_name:
            continue
        target = rels[s.get("{%s}id" % NS["r"])].lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(target)).iter("{%s}row" % NS["m"]):
            d = {}
            for c in row.findall("m:c", NS):
                col = re.match(r"[A-Z]+", c.get("r")).group()
                v = c.find("m:v", NS)
                if c.get("t") == "s" and v is not None:
                    d[col] = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    d[col] = "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))
                else:
                    d[col] = v.text if v is not None else ""
            rows.append(d)
        return rows
    raise SystemExit(f"sheet {sheet_name!r} not found")


def main():
    xlsx = Path(sys.argv[1])
    sheet = read_sheet(xlsx, "Write here")
    by_item = {r["A"]: r for r in sheet[1:] if r.get("A", "").startswith("simple_python_")}

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    filled, empty, unchecked = 0, [], []
    for r in rows:
        col = SHEET_COL.get(r["form"])
        if col is None:
            continue
        text = by_item.get(r["item_id"], {}).get(col, "").strip()
        if not text:
            empty.append((r["item_id"], r["form"]))
            continue
        r["query"] = text
        filled += 1

    for iid, r in by_item.items():
        note = r.get("H", "")
        if "author checked" not in note.lower():
            unchecked.append((iid, note))

    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"items in sheet: {len(by_item)}; rows filled: {filled}; empty cells: {len(empty)}")
    for e in empty:
        print("  empty:", *e)
    print(f"items whose note does not say 'author checked': {len(unchecked)}")
    for iid, note in unchecked:
        print(f"  {iid}: {note}")


if __name__ == "__main__":
    main()
