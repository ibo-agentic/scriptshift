"""Make the Bangla writing sheets and the Gemini input files for the main set.

Reads data/main/main_items.csv (only the `en` rows are used) and writes, for every batch of 40 items:
  data/main/sheets/batch_XX.xlsx               same layout and colours as data/pilot/bangla_writing_sheet.xlsx
                                               (gray English + Must keep, green Bangla columns, Rules tab)
  data/main/sheets/gemini_input_batch_XX.txt   data/prompts/gemini_native_prompt.txt + the batch items, ready to paste

"Must keep" lists the gold arguments the tool needs (optional arguments, gold list contains "", and booleans are left
out). For `multiple` items only the correct tool's values are shown. A value with several accepted spellings is shown
in the spelling that appears in the English query.

The .xlsx files are built from the pilot workbook (its styles, column widths, frozen panes); only the two sheets'
cells are replaced. They are written with the standard library, no openpyxl needed.
"""
import argparse
import csv
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_bangla import read_sheet
from select_main_items import NUMBER_WORDS, in_query, number_in_query, required, words_of

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "data" / "pilot" / "bangla_writing_sheet.xlsx"
BATCH = 40
COLS = "ABCDEFGH"
STYLE = {"head": 3, "example": 4, "gray": 5, "green": 6, "note": 7, "title": 1, "rule": 2}

RULE_TEXTS = [      # numbered automatically
    'Same meaning in all 4 forms. Every value in "Must keep" must appear.',
    "Numbers follow the English request. English digits stay English digits 0-9, in every form. A number the English writes as a word (\"three\") stays a word: a Bangla word in bn_native and bn_partial, a romanized word in bn_roman, an English word in bn_mixed.",
    "Run import_gemini.py to fill the green columns, then check and edit every form.",
    "bn_native: everything in Bangla script, including names (মেসি, not Messi).",
    "bn_roman: Bangla words in English letters, how YOU type on your phone. No English words except names.",
    "bn_mixed: natural Banglish. Bangla grammar, English words where you really use them.",
    'bn_partial: build it from your edited bn_native: Bangla script, but the "Must keep" values copied exactly in English.',
    "NO EXTRA ANSWER: a form may contain only what the English request contains, written the way the English request writes it. Do not add information. Do not change the format of a value (dates, units, capital letters) to the format the tool wants.",
    "Do not fix spelling to look perfect. Natural typing is the point.",
    "Write all 4 forms of one item, then go to the next item.",
    "Only fill the GREEN columns. Do not change item_id, English, or Must keep.",
    "Awkward item? Write it the way a Bangla speaker would and add a note.",
]
RULES = ([("title", "RULES (read once)"), None]
         + [("rule", f"{i}. {t}") for i, t in enumerate(RULE_TEXTS, 1)]
         + [None, ("rule", "When done: File > Save (keep .xlsx). Give the file to Claude Code to merge.")])


def rules_rows_xml():
    return [f'<row r="{i}">{cell("A", i, rule[1], rule[0])}</row>' for i, rule in enumerate(RULES, 1) if rule]


def patch_rules_only(paths):
    """Replace only the Rules sheet in existing batch files; the 'Write here' sheet (and anything typed in it) is not touched."""
    with zipfile.ZipFile(TEMPLATE) as z:
        sheet2 = z.read("xl/worksheets/sheet2.xml").decode("utf-8")
    new = sheet_xml(sheet2, rules_rows_xml()).encode("utf-8")
    for p in paths:
        p = Path(p)
        with zipfile.ZipFile(p) as z:
            parts = {i.filename: z.read(i.filename) for i in z.infolist()}
        parts["xl/worksheets/sheet2.xml"] = new
        tmp = p.with_suffix(".xlsx.tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for filename, data in parts.items():
                zout.writestr(filename, data)
        try:
            import os
            os.replace(tmp, p)
        except PermissionError:
            tmp.unlink(missing_ok=True)
            sys.exit(f"cannot write {p}: close it in Excel and run again")
        print(f"rules updated: {p.name}")


def cell(col, row, text, style):
    ref = f"{col}{row}"
    if text == "":
        return f'<c r="{ref}" s="{STYLE[style]}"/>'
    return f'<c r="{ref}" s="{STYLE[style]}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def sheet_xml(template_xml, rows_xml):
    a = template_xml.index("<sheetData>") + len("<sheetData>")
    b = template_xml.index("</sheetData>")
    return template_xml[:a] + "".join(rows_xml) + template_xml[b:]


def show(v):
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def must_keep(gt, query):
    return [f"{p} = {show(v)}" for p, v in must_values(gt, query)]


def must_values(gt, query):
    """[(param, value)] for the required, non-boolean gold arguments; the value is the accepted spelling that appears in the query"""
    qwords = words_of(query)
    out = []
    for p, acc in required(gt["arguments"]).items():
        vals = [a for a in acc if a != ""]
        if not vals or all(isinstance(a, bool) for a in vals):
            continue
        pick = None
        for a in sorted((a for a in vals if not isinstance(a, bool)), key=lambda a: -len(str(a))):
            if isinstance(a, str) and in_query(a, qwords):
                pick = a
            elif isinstance(a, (int, float)) and number_in_query(a, query):
                pick = a
            elif isinstance(a, list) and a and all(
                    (isinstance(x, str) and in_query(x, qwords)) or (isinstance(x, (int, float)) and number_in_query(x, query))
                    for x in a):
                pick = a
            if pick is not None:
                break
        out.append((p, query_form(pick if pick is not None else vals[0], query)))
    return out


def query_form(v, query):
    """the value written the way the English query writes it ("sushi" not "Sushi", "three" not 3, "Apple Inc" not
    "Apple Inc."), so that "Must keep" never tempts a writer to change capitals, number type or punctuation"""
    if isinstance(v, list):
        return [query_form(x, query) for x in v]
    if isinstance(v, str):
        m = re.search(re.escape(v), query, re.I)            # the literal text first (keeps symbols and final punctuation)
        if m:
            return m.group(0)
        tokens = words_of(v).split()
        if tokens:
            pat = r"(?<![A-Za-z0-9])" + r"[^A-Za-z0-9]+".join(map(re.escape, tokens)) + r"(?![A-Za-z0-9])"
            m = re.search(pat, query, re.I)
            if m:
                return m.group(0)
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        for tok in re.findall(r"\d[\d,]*(?:\.\d+)?", query):
            if float(tok.replace(",", "")) == float(v):
                return tok
        for w in re.findall(r"[A-Za-z]+", query):
            if NUMBER_WORDS.get(w.lower()) == v:
                return w
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default=str(ROOT / "data" / "main" / "main_items.csv"))
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "main" / "sheets"))
    ap.add_argument("--prompt", default=str(ROOT / "data" / "prompts" / "gemini_native_prompt.txt"))
    ap.add_argument("--rules-only", action="store_true",
                    help="only replace the Rules tab of the existing batch_XX.xlsx files (keeps everything typed in 'Write here')")
    cli = ap.parse_args()
    out_dir = Path(cli.out_dir)
    if cli.rules_only:
        patch_rules_only(sorted(out_dir.glob("batch_*.xlsx")))
        return
    out_dir.mkdir(parents=True, exist_ok=True)

    items = []
    for r in csv.DictReader(open(cli.items, encoding="utf-8-sig", newline="")):
        if r["form"] == "en":
            items.append((r["item_id"], r["query"], json.loads(r["gt_call_json"])))
    prompt = Path(cli.prompt).read_text(encoding="utf-8").rstrip() + "\n"

    pilot = read_sheet(TEMPLATE, "Write here")
    header, example = pilot[0], next(r for r in pilot if r.get("A") == "EXAMPLE")
    with zipfile.ZipFile(TEMPLATE) as z:
        parts = {i.filename: z.read(i.filename) for i in z.infolist()}
    sheet1, sheet2 = parts["xl/worksheets/sheet1.xml"].decode("utf-8"), parts["xl/worksheets/sheet2.xml"].decode("utf-8")
    empty_sst = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="0" uniqueCount="0"/>')

    rules_rows = rules_rows_xml()

    n_batches = (len(items) + BATCH - 1) // BATCH
    for b in range(n_batches):
        chunk = items[b * BATCH:(b + 1) * BATCH]
        rows = [f'<row r="1" ht="45.0" customHeight="1">' + "".join(cell(c, 1, header[c], "head") for c in COLS) + "</row>",
                "<row r=\"2\">" + "".join(cell(c, 2, example.get(c, ""), "example") for c in COLS) + "</row>"]
        gem = []
        for i, (iid, query, gt) in enumerate(chunk, 3):
            mk = must_keep(gt, query)
            rows.append(f'<row r="{i}">' + cell("A", i, iid, "gray") + cell("B", i, query, "gray")
                        + cell("C", i, "\n".join(mk), "gray")
                        + "".join(cell(c, i, "", "green") for c in "DEFG") + cell("H", i, "", "note") + "</row>")
            gem.append(f"item_id: {iid}\nEnglish: {query} | Must keep: {'; '.join(mk) if mk else '(none)'}")
        name = f"batch_{b + 1:02d}"
        with zipfile.ZipFile(out_dir / f"{name}.xlsx", "w", zipfile.ZIP_DEFLATED) as zout:
            for filename, data in parts.items():
                if filename == "xl/worksheets/sheet1.xml":
                    data = sheet_xml(sheet1, rows).encode("utf-8")
                elif filename == "xl/worksheets/sheet2.xml":
                    data = sheet_xml(sheet2, rules_rows).encode("utf-8")
                elif filename == "xl/sharedStrings.xml":
                    data = empty_sst.encode("utf-8")
                zout.writestr(filename, data)
        text = (prompt + f"\n(batch {b + 1:02d}: {len(chunk)} items)\n\n" + "\n\n".join(gem) + "\n")
        (out_dir / f"gemini_input_{name}.txt").write_text(text, encoding="utf-8")
        print(f"{name}: {len(chunk)} items  ({sum(i.startswith('simple') for i, _, _ in chunk)} simple_python, "
              f"{sum(i.startswith('multiple') for i, _, _ in chunk)} multiple)")
    print(f"wrote {n_batches} sheets + {n_batches} Gemini input files to {out_dir}")


if __name__ == "__main__":
    main()
