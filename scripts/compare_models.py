"""Compare pilot results across models: accuracy, form x category tables, McNemar tests, examples.

PRIMARY metric   = value types normalized ("7" -> 7), column `lenient` / `strict` (output format)
SECONDARY metric = BFCL-style typing,                column `lenient_typed` / `strict_typed`

usage: python scripts/compare_models.py <jsonl> [<jsonl> ...]
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
# column -> (output format, value typing)
METRICS = {"strict": ("strict", "norm"), "lenient": ("lenient", "norm"),
           "strict_typed": ("strict", "typed"), "lenient_typed": ("lenient", "typed")}
TITLES = {"norm": "PRIMARY (types normalized)", "typed": "SECONDARY (BFCL typing)"}


def load(path, gts):
    """returns (label, tool_mode, rows) with the 4 metric labels attached to every row"""
    lines = [json.loads(l) for l in open(path, encoding="utf-8")]
    meta, rows = lines[0], [r for r in lines[1:] if r.get("type") == "row"]
    for r in rows:
        for k, (mode, typing) in METRICS.items():
            r[k] = label_output(r["raw_output"], gts[r["item_id"]], mode, typing)
    return SHORT.get(meta["model"], meta["model"]), meta.get("tool_mode"), rows


def mcnemar(rows, other, col="lenient"):
    ok = {(r["item_id"], r["form"]): r[col] == "correct" for r in rows}
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
    ap.add_argument("--labels", nargs="*", help="override column names (e.g. when two runs use the same model)")
    args = ap.parse_args()
    gts = {r["item_id"]: json.loads(r["gt_call_json"])
           for r in csv.DictReader(open(args.items, encoding="utf-8-sig", newline=""))}
    data, modes = {}, {}
    for i, f in enumerate(args.files):
        name, tool_mode, rows = load(f, gts)
        if args.labels:
            name = args.labels[i]
        data[name], modes[name] = rows, tool_mode
    models = [m for m in ORDER if m in data] + [m for m in data if m not in ORDER]
    print("tool_mode:", {m: modes[m] for m in models})

    for typing in ("norm", "typed"):
        for fmt in ("lenient", "strict"):
            col = fmt if typing == "norm" else fmt + "_typed"
            print(f"\n### {TITLES[typing]} - {fmt.upper()} format: correct / 30")
            print(f"{'form':<12}" + "".join(f"{m:>15}" for m in models))
            for f in FORMS:
                cells = []
                for m in models:
                    k = sum(r[col] == "correct" for r in data[m] if r["form"] == f)
                    cells.append(f"{k}/30 ({k / 30:.0%})")
                print(f"{f:<12}" + "".join(f"{c:>15}" for c in cells))

    for typing in ("norm", "typed"):
        col = "lenient" if typing == "norm" else "lenient_typed"
        for m in models:
            print(f"\n### {m}: form x category - {TITLES[typing]}, LENIENT format")
            print(f"{'form':<12}" + "".join(f"{c:>15}" for c in CATS))
            for f in FORMS:
                c = Counter(r[col] for r in data[m] if r["form"] == f)
                print(f"{f:<12}" + "".join(f"{c[k]:>15}" for k in CATS))

    for typing in ("norm", "typed"):
        col = "lenient" if typing == "norm" else "lenient_typed"
        print(f"\n### McNemar exact - {TITLES[typing]}, LENIENT format: en vs other form, paired by item")
        print("b = en right & other wrong, c = en wrong & other right, discordant = b + c")
        print(f"{'model':<14}{'pair':<18}{'b':>4}{'c':>4}{'discordant':>12}{'p':>10}")
        for m in models:
            for other in ("bn_native", "bn_roman"):
                b, c, p = mcnemar(data[m], other, col)
                print(f"{m:<14}{'en vs ' + other:<18}{b:>4}{c:>4}{b + c:>12}{p:>10.4f}")

    lines = ["Examples use the PRIMARY metric (types normalized); format_break is the STRICT-format label."]
    for m in models:
        lines.append(f"\n===== {m}")
        for cat in CATS[1:]:
            col = "strict" if cat == "format_break" else "lenient"
            hits = [r for r in data[m] if r[col] == cat]
            pick, seen = [], set()
            for r in sorted(hits, key=lambda r: r["form"] == "en"):   # prefer non-English rows, distinct forms
                if r["form"] not in seen:
                    pick.append(r)
                    seen.add(r["form"])
            pick = (pick + [r for r in hits if r not in pick])[:2]
            lines.append(f"--- {cat} ({col}; {len(hits)} rows)")
            for r in pick:
                lines.append(f"[{r['item_id']} | {r['form']}] {r['raw_output'].strip()!r}")
    Path(args.examples_out).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nexamples written to {args.examples_out}")


if __name__ == "__main__":
    main()
