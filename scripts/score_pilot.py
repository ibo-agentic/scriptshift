"""Score pilot outputs. One label per output, two ways:

strict  - the whole output must be only the call (<tool_call>{json}</tool_call>); anything else
          that still contains a call is labelled format_break.
lenient - take the first JSON call found anywhere in the text and score it.

Labels: correct | no_call | wrong_tool | wrong_lang_arg | roman_leak | wrong_value | format_break | other
"""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATS = ["correct", "no_call", "wrong_tool", "wrong_lang_arg", "roman_leak", "wrong_value", "format_break", "other"]
BANGLA = re.compile("[ঀ-৿]")
# strict = the whole output is one call, in any of the formats our models use natively:
# Qwen <tool_call>{..}</tool_call>, a code-fenced JSON block, or bare JSON (Llama / Gemma)
STRICT_RES = [
    re.compile(r"^<tool_call>\s*(\{.*\})\s*</tool_call>$", re.S),
    re.compile(r"^```(?:json)?\s*(\{.*\})\s*```$", re.S),
    re.compile(r"^(\{.*\})$", re.S),
]
SPECIAL_TOKENS = ["<|im_end|>", "<|endoftext|>", "<|eot_id|>", "<|eom_id|>", "<|end_of_text|>",
                  "<|python_tag|>", "<end_of_turn>", "<eos>"]


def clean(raw):
    for t in SPECIAL_TOKENS:
        raw = raw.replace(t, "")
    return raw.strip()


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def skeleton(s):
    """lowercase, accents removed, letters and digits only"""
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


def close_variant(pred, gold):
    """roman_leak rule: pred is the gold value with a small spelling change (Sidney vs Sydney).
    Allowed: edit distance <= max(1, 20% of gold length) on accent-stripped, lowercased letters/digits,
    gold at least 4 characters. A different name (Amine vs Eminem: 2 edits, limit 1) is not a variant."""
    p, g = skeleton(pred), skeleton(gold)
    return len(g) >= 4 and edit_distance(p, g) <= max(1, round(0.2 * len(g)))


def first_json_call(text):
    """First JSON object in text (scanning left to right) that looks like a call."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and "name" in obj:
            return obj
    return None


def norm(v):
    """Same idea as BFCL: lowercase, drop spaces and common punctuation."""
    if isinstance(v, str):
        return re.sub(r"[\s,./\-_*^'\"]", "", v.lower())
    return v


def same(pred, accepted):
    for a in accepted:
        if isinstance(pred, (int, float)) and isinstance(a, (int, float)) and not isinstance(pred, bool):
            if float(pred) == float(a):
                return True
        elif norm(pred) == norm(a):
            return True
        elif isinstance(a, list) and isinstance(pred, list) and [norm(x) for x in pred] == [norm(x) for x in a]:
            return True
    return False


def score_call(call, gt, schema_params):
    name, args = call.get("name"), call.get("arguments", call.get("parameters"))  # Llama 3.1 uses "parameters"
    if not isinstance(name, str) or not isinstance(args, dict):
        return "other"
    if name != gt["name"]:
        return "wrong_tool"
    label = None
    rank = {"wrong_lang_arg": 3, "roman_leak": 2, "wrong_value": 1}

    def mark(l):
        nonlocal label
        if label is None or rank[l] > rank[label]:
            label = l

    for p, accepted in gt["arguments"].items():
        if p not in args:
            if "" not in accepted:  # "" means the parameter may be left out
                mark("wrong_value")
            continue
        pred = args[p]
        if same(pred, accepted):
            continue
        if isinstance(pred, str) and BANGLA.search(pred):
            mark("wrong_lang_arg")
        elif isinstance(pred, str) and re.search("[A-Za-z]{2}", pred) and any(
            isinstance(a, str) and re.search("[A-Za-z]{2}", a) and close_variant(pred, a)
            for a in accepted
        ):
            mark("roman_leak")
        else:
            mark("wrong_value")
    for p in args:
        if p not in gt["arguments"]:
            mark("wrong_value")
    return label or "correct"


def label_output(raw, gt, mode):
    text = clean(raw)
    strict_call = None
    for rx in STRICT_RES:
        m = rx.match(text)
        if m:
            try:
                obj = json.loads(m.group(1))
                strict_call = obj if isinstance(obj, dict) else None
            except ValueError:
                strict_call = None
            break
    if mode == "strict":
        if strict_call is not None:
            return score_call(strict_call, gt, None)
        # not exactly one clean call: is there anything call-like at all?
        return "format_break" if ("<tool_call>" in text or first_json_call(text)) else "no_call"
    call = strict_call or first_json_call(text)
    if call is None:
        return "format_break" if "<tool_call>" in text else "no_call"
    return score_call(call, gt, None)


def table(counts, forms, title):
    print(f"\n{title}")
    print(f"{'form':<12}" + "".join(f"{c:>15}" for c in CATS) + f"{'n':>5}")
    for f in forms:
        c = counts[f]
        print(f"{f:<12}" + "".join(f"{c[k]:>15}" for k in CATS) + f"{sum(c.values()):>5}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", nargs="?", help="results jsonl (default: latest in results/pilot)")
    ap.add_argument("--items", default=str(ROOT / "data" / "pilot" / "pilot_items.csv"))
    args = ap.parse_args()
    run = Path(args.run) if args.run else max((ROOT / "results" / "pilot").glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    print(f"scoring {run.name}")

    gts = {}
    for r in csv.DictReader(open(args.items, encoding="utf-8-sig", newline="")):
        gts[r["item_id"]] = json.loads(r["gt_call_json"])

    rows = [json.loads(l) for l in open(run, encoding="utf-8")]
    rows = [r for r in rows if r.get("type") == "row"]
    counts = {m: defaultdict(Counter) for m in ("strict", "lenient")}
    per_row = []
    for r in rows:
        labs = {m: label_output(r["raw_output"], gts[r["item_id"]], m) for m in counts}
        for m, l in labs.items():
            counts[m][r["form"]][l] += 1
        per_row.append({"item_id": r["item_id"], "form": r["form"], "strict": labs["strict"], "lenient": labs["lenient"]})

    forms = sorted({r["form"] for r in rows}, key=lambda f: ["en", "bn_native", "bn_roman", "bn_mixed", "bn_partial"].index(f))
    table(counts["strict"], forms, "STRICT (whole output must be only the call)")
    table(counts["lenient"], forms, "LENIENT (first JSON call in the text)")

    out_csv = run.with_suffix(".scores.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "form", "strict", "lenient"])
        w.writeheader()
        w.writerows(per_row)
    print(f"\nper-row labels: {out_csv}")


if __name__ == "__main__":
    main()
