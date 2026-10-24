"""List rows of one form + one error label with gold and predicted values side by side (for reading by hand).

Uses the PRIMARY metric (types normalized), LENIENT format.
usage: python scripts/list_errors.py <jsonl> [<jsonl> ...] [--form bn_roman] [--label wrong_value] [--out file.md]

BANGLA-WORD? marks a predicted text value that contains a word which is in the item's Bangla-form query
but NOT in the English query and NOT in the gold value (e.g. "Garite Kore": a Bangla phrase read as a name).
This is a hint for the human reader, not a score.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_pilot import clean, first_json_call, label_output, same
from compare_models import SHORT

ROOT = Path(__file__).resolve().parent.parent


def words(s):
    return {w.lower() for w in re.findall(r"[A-Za-z]{3,}", s)}


def problems(call, gt, en_query, form_query):
    """(param, gold, predicted, note) for every argument that does not match"""
    args = call.get("arguments", call.get("parameters")) or {}
    out = []
    for p, accepted in gt["arguments"].items():
        shown = " / ".join(map(str, [a for a in accepted if a != ""][:3])) or "(optional)"
        if p not in args:
            if "" not in accepted:
                out.append((p, shown, "(missing)", ""))
            continue
        pred = args[p]
        if same(pred, accepted, "norm"):
            continue
        note = ""
        if isinstance(pred, str):
            gold_words = set().union(*[words(str(a)) for a in accepted])
            foreign = words(pred) - words(en_query) - gold_words
            if foreign & words(form_query):
                note = "BANGLA-WORD?"
        out.append((p, shown, json.dumps(pred, ensure_ascii=False), note))
    for p in args:
        if p not in gt["arguments"]:
            out.append((p, "(not a parameter in gold)", json.dumps(args[p], ensure_ascii=False), "extra arg"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--form", default="bn_roman")
    ap.add_argument("--label", default="wrong_value")
    ap.add_argument("--items", default=str(ROOT / "data" / "pilot" / "pilot_items.csv"))
    ap.add_argument("--out", default=str(ROOT / "results" / "pilot" / "bn_roman_wrong_value.md"))
    args = ap.parse_args()

    items = list(csv.DictReader(open(args.items, encoding="utf-8-sig", newline="")))
    gts = {r["item_id"]: json.loads(r["gt_call_json"]) for r in items}
    queries = {(r["item_id"], r["form"]): r["query"] for r in items}

    lines = [f"# {args.form} rows labeled {args.label} (primary metric, lenient format)", "",
             "gold = accepted values (first 3 shown); predicted = what the model wrote. "
             "BANGLA-WORD? = predicted text contains a word from the Bangla-form query that is not in the English query.", ""]
    total = 0
    for f in args.files:
        L = [json.loads(l) for l in open(f, encoding="utf-8")]
        meta, rows = L[0], [r for r in L[1:] if r.get("type") == "row"]
        name = SHORT.get(meta["model"], meta["model"]) + f" ({meta.get('tool_mode')})"
        hits = [r for r in rows if r["form"] == args.form
                and label_output(r["raw_output"], gts[r["item_id"]], "lenient", "norm") == args.label]
        en_ok = {r["item_id"]: label_output(r["raw_output"], gts[r["item_id"]], "lenient", "norm") == "correct"
                 for r in rows if r["form"] == "en"}
        lines += [f"## {name}: {len(hits)} rows", "",
                  f"| item | {args.form} query | en correct? | param | gold | predicted | note |", "|---|---|---|---|---|---|---|"]
        for r in hits:
            call = first_json_call(clean(r["raw_output"]))
            en_q = queries[(r["item_id"], "en")]
            for p, gold, pred, note in problems(call, gts[r["item_id"]], en_q, r["query"]):
                lines.append(f"| {r['item_id'].replace('simple_python_', '')} | {r['query']} | "
                             f"{'yes' if en_ok.get(r['item_id']) else 'NO'} | {p} | {gold} | {pred} | {note} |")
        lines.append("")
        total += len(hits)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n{total} rows; written to {args.out}")


if __name__ == "__main__":
    main()
