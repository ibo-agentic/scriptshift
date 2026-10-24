"""Import Gemini's table into the writing sheets.

For each batch XX it reads  data/main/sheets/gemini_output_batch_XX.tsv  (columns: item_id, bn_native, bn_roman,
bn_mixed, bn_partial; a header line, blank lines and ``` lines are ignored) and fills the 4 green columns of
data/main/sheets/batch_XX.xlsx, matched by item_id (not by row order). The note column gets
"gemini draft; author check pending".

  - a cell that already has text is never changed unless --overwrite (the note is then reset to "pending" too)
  - only the cells of the "Write here" sheet are touched; styles, widths and the Rules tab stay as they are
  - reported: item_ids missing from the table, extra or duplicated item_ids in the table, unparsable lines,
    empty cells, cells written / skipped
  - LEAK CHECK on every imported form (a hint for the author, nothing is blocked). It flags text that carries more of
    the answer than the English query, or writes a value differently:
      digits       a number in the form that the English query does not have (digit where English has a word,
                   a date in another format, an added number), English digits of the query missing or changed
                   (Bangla digits, a word instead of the digit)
      capitals     a Latin-letter Must keep value with other capital letters than in the English query
      not copied   bn_partial that does not contain a Must keep value exactly as in the English query
      gold wording a gold value spelling that is NOT in the English query (e.g. "Carbohydrates" for "carbs",
                   "New York City, NY" for "New York City") appearing in the form
    The same report is saved next to the sheet as gemini_import_report_batch_XX.txt.

usage: python scripts/import_gemini.py 01 [02 ...] | --all   [--overwrite] [--dry-run] [--sheets-dir DIR] [--items CSV]
"""
import argparse
import csv
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_writing_sheets import must_values
from select_main_items import GENERIC, in_query, words_of

ROOT = Path(__file__).resolve().parent.parent
FORMS = ["bn_native", "bn_roman", "bn_mixed", "bn_partial"]
COL = {"bn_native": "D", "bn_roman": "E", "bn_mixed": "F", "bn_partial": "G"}
NOTE = "gemini draft; author check pending"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
DIGITS = re.compile(r"\d+(?:[.,/\-]\d+)*")
ITEM_ID = re.compile(r"^(simple_python|multiple)_\d+$")


# ---------------------------------------------------------------- reading the Gemini table
def read_tsv(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit(f"{path}: cannot decode (save it as UTF-8)")
    table, bad, dup = {}, [], []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.strip().startswith("```"):
            continue
        fields = [x.strip() for x in line.split("\t")]
        if fields[0].lower() == "item_id":
            continue                                                  # header line
        if len(fields) != 5:
            bad.append(f"line {n}: {len(fields)} tab-separated fields instead of 5: {line[:60]!r}")
            continue
        if fields[0] in table:
            dup.append(fields[0])
        table[fields[0]] = dict(zip(FORMS, fields[1:]))
    return table, bad, dup


# ---------------------------------------------------------------- reading / writing the sheet xml
def shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])) for si in root.findall("m:si", NS)]


def sheet_cells(xml, sst):
    """{row number: {column letter: text}} for the sheet xml"""
    out = {}
    for row in ET.fromstring(xml).iter("{%s}row" % NS["m"]):
        cells = {}
        for c in row.findall("m:c", NS):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            if c.get("t") == "s":
                v = c.find("m:v", NS)
                text = sst[int(v.text)] if v is not None and v.text is not None else ""
            elif c.get("t") == "inlineStr":
                text = "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))
            else:
                v = c.find("m:v", NS)
                text = v.text if v is not None and v.text is not None else ""
            cells[col] = text
        out[int(row.get("r"))] = cells
    return out


def set_cell(xml, ref, text, style):
    """put `text` (inline string) into cell `ref`, creating the cell in its row if it is missing"""
    inner = f'<is><t xml:space="preserve">{escape(text)}</t></is>'
    m = re.search(r'<c r="%s"([^>]*?)(/>|>.*?</c>)' % ref, xml, re.S)
    if m:
        attrs = re.sub(r'\s+t="[^"]*"', "", m.group(1))
        return xml[:m.start()] + f'<c r="{ref}"{attrs} t="inlineStr">{inner}</c>' + xml[m.end():]
    col, rownum = re.match(r"([A-Z]+)(\d+)", ref).groups()
    rm = re.search(r'(<row r="%s"[^>]*>)(.*?)(</row>)' % rownum, xml, re.S)
    if not rm:
        raise SystemExit(f"row {rownum} not found in the sheet")
    body, new = rm.group(2), f'<c r="{ref}" s="{style}" t="inlineStr">{inner}</c>'
    pos = len(body)
    for cm in re.finditer(r'<c r="([A-Z]+)\d+"', body):
        if cm.group(1) > col:
            pos = cm.start()
            break
    body = body[:pos] + new + body[pos:]
    return xml[:rm.start()] + rm.group(1) + body + rm.group(3) + xml[rm.end():]


# ---------------------------------------------------------------- leak check
def accepted_strings(gt):
    """every string spelling in the gold answer, required or optional (also list elements)"""
    out = set()
    for acc in gt["arguments"].values():
        for a in acc:
            for x in (a if isinstance(a, list) else [a]):
                if isinstance(x, str) and len(re.findall(r"[A-Za-z]", x)) >= 3:
                    out.add(x)
    return out


def leak_check(form, text, query, gt):
    issues = []
    q_digits, f_digits = set(DIGITS.findall(query)), set(DIGITS.findall(text))
    if f_digits - q_digits:
        issues.append(f"digits not in the English query: {sorted(f_digits - q_digits)}")
    if q_digits - f_digits:
        issues.append(f"English digits not kept: {sorted(q_digits - f_digits)}")
    if re.search("[০-৯]", text):
        issues.append("Bangla digits (use English digits 0-9)")
    qwords, fwords = words_of(query), words_of(text)
    for param, value in must_values(gt, query):
        for v in (value if isinstance(value, list) else [value]):
            if not isinstance(v, str):
                continue
            m = re.search(re.escape(v), query, re.I)
            if not m:
                continue
            span = m.group(0)
            if span in text:
                continue
            if span.lower() in text.lower():
                got = re.search(re.escape(span), text, re.I).group(0)
                issues.append(f"capital letters differ from the English query: {got!r} vs {span!r}")
            elif form == "bn_partial":
                issues.append(f"bn_partial: Must keep value {span!r} not copied exactly")
    for a in sorted(accepted_strings(gt)):
        w = words_of(a)
        if w and w not in GENERIC and not in_query(a, qwords) and f" {w} " in f" {fwords} ":
            issues.append(f"gold wording {a!r} is not in the English query")
    return issues


# ---------------------------------------------------------------- one batch
def import_batch(num, sheets_dir, items, overwrite, dry_run):
    tsv, xlsx = sheets_dir / f"gemini_output_batch_{num}.tsv", sheets_dir / f"batch_{num}.xlsx"
    report = [f"=== batch {num}"]
    if not tsv.exists() or not xlsx.exists():
        report.append(f"missing file: {tsv if not tsv.exists() else xlsx}")
        return report, False
    table, bad_lines, dups = read_tsv(tsv)
    with zipfile.ZipFile(xlsx) as z:
        parts = {i.filename: z.read(i.filename) for i in z.infolist()}
        sst = shared_strings(z)
    xml = parts["xl/worksheets/sheet1.xml"].decode("utf-8")
    cells = sheet_cells(xml, sst)
    row_of = {c["A"]: r for r, c in cells.items() if ITEM_ID.match(c.get("A", ""))}

    missing = [i for i in row_of if i not in table]
    extra = [i for i in table if i not in row_of]
    written = skipped = empty = 0
    leaks, notes_set = [], 0
    for iid, forms in table.items():
        if iid not in row_of:
            continue
        r = row_of[iid]
        query, gt = items[iid]
        wrote_any = False
        for form in FORMS:
            text = forms[form]
            if not text:
                empty += 1
                report.append(f"empty: {iid} {form}")
                continue
            for issue in leak_check(form, text, query, gt):
                leaks.append(f"{iid} {form}: {issue}")
            ref = f"{COL[form]}{r}"
            if cells[r].get(COL[form], "").strip() and not overwrite:
                skipped += 1
                continue
            xml = set_cell(xml, ref, text, 6)
            written += 1
            wrote_any = True
        if wrote_any and (overwrite or not cells[r].get("H", "").strip()):
            xml = set_cell(xml, f"H{r}", NOTE, 7)
            notes_set += 1

    report.append(f"items in the sheet: {len(row_of)} | rows in the table: {len(table)}")
    report.append(f"cells written: {written} | skipped (already had text): {skipped} | empty in the table: {empty} | notes set: {notes_set}")
    report.append(f"missing item_ids (in the sheet, not in the table): {len(missing)}" + (f" -> {missing}" if missing else ""))
    report.append(f"extra item_ids (in the table, not in the sheet): {len(extra)}" + (f" -> {extra}" if extra else ""))
    if dups:
        report.append(f"duplicated item_ids in the table (last one used): {sorted(set(dups))}")
    for b in bad_lines:
        report.append(f"unparsable: {b}")
    report.append(f"leak check: {len(leaks)} flags")
    report += [f"  - {x}" for x in leaks]

    ok = True
    if not dry_run and written + notes_set:
        parts["xl/worksheets/sheet1.xml"] = xml.encode("utf-8")
        tmp = xlsx.with_suffix(".xlsx.tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for filename, data in parts.items():
                zout.writestr(filename, data)
        try:
            os.replace(tmp, xlsx)
        except PermissionError:
            tmp.unlink(missing_ok=True)
            report.append(f"CANNOT WRITE {xlsx.name}: close it in Excel and run again")
            ok = False
    if dry_run:
        report.append("dry run: nothing written")
    (sheets_dir / f"gemini_import_report_batch_{num}.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    return report, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batches", nargs="*", help="batch numbers, e.g. 01 02")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sheets-dir", default=str(ROOT / "data" / "main" / "sheets"))
    ap.add_argument("--items", default=str(ROOT / "data" / "main" / "main_items.csv"))
    cli = ap.parse_args()
    sheets_dir = Path(cli.sheets_dir)
    nums = [f"{int(b):02d}" for b in cli.batches]
    if cli.all:
        nums = sorted(re.findall(r"batch_(\d+)\.xlsx$", p.name)[0] for p in sheets_dir.glob("batch_*.xlsx"))
    if not nums:
        sys.exit("give batch numbers (e.g. 01 02) or --all")
    items = {}
    for r in csv.DictReader(open(cli.items, encoding="utf-8-sig", newline="")):
        if r["form"] == "en":
            items[r["item_id"]] = (r["query"], json.loads(r["gt_call_json"]))
    all_ok = True
    for n in nums:
        report, ok = import_batch(n, sheets_dir, items, cli.overwrite, cli.dry_run)
        print("\n".join(report))
        all_ok &= ok
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
