"""Compare pilot results across models: accuracy table, form x category tables, examples, McNemar tests.

usage: python scripts/compare_models.py <jsonl> [<jsonl> ...]     (first = label order; uses score_pilot rules)
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_pilot import CATS, label_output

ROOT = Path(__file__).resolve().parent.parent
FORMS = ["en", "bn_native", "bn_roman", "bn_mixed", "bn_partial"]
SHORT = {"Qwen/Qwen3-1.7B": "Qwen3-1.7B", "Qwen/Qwen3-4B": "Qwen3-4B",
         "google/gemma-3-4b-it": "Gemma-3-4B", "meta-llama/Llama-3.1-8B-Instruct": "Llama-3.1-8B"}
ORDER = list(SHORT.values())


def load(path, gts):
    lines = [json.loads(l) for l in open(path, encoding="utf-8")]
    meta, rows = lines[0], [r for r in lines[1:] if r.get("type") == "row"]
    for r in rows:
        for mode in ("strict", "lenient"):
            r[mode] = label_output(r["raw_output"], gts[r["item_id"]], mode)
    return SHORT.get(meta["model"], meta["model"]), rows


def mcnemar(rows, other, mode="lenient"):
    ok = {(r["item_id"], r["form"]): r[mode] == "correct" for r in rows}
    items = sorted({i for i, _ in ok})
    b = sum(ok[(i, "en")] and not ok[(i, other)] for i in items)   # en right, other wrong
    c = sum(not ok[(i, "en")] and ok[(i, other)] for i in items)   # en wrong, other right
    p = binomtest(b, b + c, 0.5).pvalue if b + c else 1.0
    return b, c, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--items", default=str(ROOT / "data" / "pilot" / "pilot_items.csv"))
    ap.add_argument("--examples-out", default=str(ROOT / "results" / "pilot" / "examples_by_category.txt"))
    args = ap.parse_args()
    gts = {r["item_id"]: json.loads(r["gt_call_json"])
           for r in csv.DictReader(open(args.items, encoding="utf-8-sig", newline=""))}
    data = dict(load(f, gts) for f in args.files)
    models = [m for m in ORDER if m in data] + [m for m in data if m not in ORDER]

    for mode in ("strict", "lenient"):
        print(f"\n### Accuracy ({mode}), correct / 30")
        print(f"{'form':<12}" + "".join(f"{m:>15}" for m in models))
        for f in FORMS:
            cells = []
            for m in models:
                k = sum(r[mode] == "correct" for r in data[m] if r["form"] == f)
                cells.append(f"{k}/30 ({k / 30:.0%})")
            print(f"{f:<12}" + "".join(f"{c:>15}" for c in cells))

    for m in models:
        print(f"\n### {m}: form x category (lenient)")
        print(f"{'form':<12}" + "".join(f"{c:>15}" for c in CATS))
        for f in FORMS:
            c = Counter(r["lenient"] for r in data[m] if r["form"] == f)
            print(f"{f:<12}" + "".join(f"{c[k]:>15}" for k in CATS))

    print("\n### McNemar exact (lenient): en vs other form, paired by item")
    print("b = en right & other wrong, c = en wrong & other right, discordant = b + c")
    print(f"{'model':<14}{'pair':<18}{'b':>4}{'c':>4}{'discordant':>12}{'p':>10}")
    for m in models:
        for other in ("bn_native", "bn_roman"):
            b, c, p = mcnemar(data[m], other)
            print(f"{m:<14}{'en vs ' + other:<18}{b:>4}{c:>4}{b + c:>12}{p:>10.4f}")

    lines = []
    for m in models:
        lines.append(f"\n===== {m}")
        for cat in CATS[1:]:
            mode = "strict" if cat == "format_break" else "lenient"
            hits = [r for r in data[m] if r[mode] == cat]
            pick, seen = [], set()
            for r in sorted(hits, key=lambda r: r["form"] == "en"):   # prefer non-English rows, distinct forms
                if r["form"] not in seen:
                    pick.append(r)
                    seen.add(r["form"])
            pick = (pick + [r for r in hits if r not in pick])[:2]
            lines.append(f"--- {cat} ({mode}; {len(hits)} rows)")
            for r in pick:
                lines.append(f"[{r['item_id']} | {r['form']}] {r['raw_output'].strip()!r}")
    Path(args.examples_out).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nexamples written to {args.examples_out}")


if __name__ == "__main__":
    main()
