"""Score pilot outputs. One label per output, scored along two independent switches:

Output format
  strict  - the whole output must be only the call (<tool_call>{json}</tool_call>, a code-fenced JSON block,
            or bare JSON); anything else that still contains a call is labelled format_break.
  lenient - take the first JSON call found anywhere in the text and score it.

Value typing
  norm    - PRIMARY. String-encoded values are converted before comparing: "7" -> 7, "true" -> true,
            '["a","b"]' -> ["a","b"]. (Llama 3.1 writes every value as a string.)
  typed   - SECONDARY. BFCL-style: the value must have the right type as written.

Labels: correct | no_call | wrong_tool | wrong_lang_arg | roman_leak | wrong_value | format_break | other
"""
import argparse
import ast
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


def same_typed(pred, accepted):
    """BFCL-style typing: "7" is not 7, "true" is not true, '["a"]' is not ["a"]."""
    for a in accepted:
        if isinstance(pred, (int, float)) and isinstance(a, (int, float)) and not isinstance(pred, bool):
            if float(pred) == float(a):
                return True
        elif norm(pred) == norm(a):
            return True
        elif isinstance(a, list) and isinstance(pred, list) and [norm(x) for x in pred] == [norm(x) for x in a]:
            return True
    return False


def coerce(v):
    """Undo string-encoding of values: "7" -> 7, "true" -> True, '["a","b"]' and "['a','b']" -> ["a","b"]
    (recursive in lists).
    Anything that does not parse to a non-string JSON value is returned unchanged."""
    if isinstance(v, list):
        return [coerce(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if s.lower() in ("true", "false"):
            return s.lower() == "true"
        try:
            parsed = json.loads(s)
        except ValueError:
            if not (s.startswith("[") and s.endswith("]")):
                return v
            try:  # python-style list written as a string: "['a', 'b']"
                parsed = ast.literal_eval(s)
            except (ValueError, SyntaxError):
                return v
            if not isinstance(parsed, list):
                return v
        return coerce(parsed) if isinstance(parsed, list) else (v if isinstance(parsed, str) else parsed)
    return v


def same(pred, accepted, typing="norm"):
    """typing="norm" (primary): compare the value as given OR with string-encoding undone.
    typing="typed" (secondary): compare the value exactly as given."""
    if same_typed(pred, accepted):
        return True
    return typing == "norm" and same_typed(coerce(pred), accepted)


def score_call(call, gt, typing="norm"):
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
        if same(pred, accepted, typing):
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


def label_output(raw, gt, mode, typing="norm"):
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
            return score_call(strict_call, gt, typing)
        # not exactly one clean call: is there anything call-like at all?
        return "format_break" if ("<tool_call>" in text or first_json_call(text)) else "no_call"
    call = strict_call or first_json_call(text)
    if call is None:
        return "format_break" if "<tool_call>" in text else "no_call"
    return score_call(call, gt, typing)


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
    # column name -> (output format mode, value typing)
    METRICS = {"strict": ("strict", "norm"), "lenient": ("lenient", "norm"),
               "strict_typed": ("strict", "typed"), "lenient_typed": ("lenient", "typed")}
    counts = {k: defaultdict(Counter) for k in METRICS}
    per_row = []
    for r in rows:
        labs = {k: label_output(r["raw_output"], gts[r["item_id"]], mode, typing) for k, (mode, typing) in METRICS.items()}
        for k, l in labs.items():
            counts[k][r["form"]][l] += 1
        per_row.append({"item_id": r["item_id"], "form": r["form"], **labs})

    forms = sorted({r["form"] for r in rows}, key=lambda f: ["en", "bn_native", "bn_roman", "bn_mixed", "bn_partial"].index(f))
    table(counts["strict"], forms, "PRIMARY (types normalized) - STRICT format: whole output must be only the call")
    table(counts["lenient"], forms, "PRIMARY (types normalized) - LENIENT format: first JSON call in the text")
    table(counts["strict_typed"], forms, "SECONDARY (BFCL typing) - STRICT format")
    table(counts["lenient_typed"], forms, "SECONDARY (BFCL typing) - LENIENT format")

    out_csv = run.with_suffix(".scores.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "form", *METRICS])
        w.writeheader()
        w.writerows(per_row)
    print(f"\nper-row labels: {out_csv}")


if __name__ == "__main__":
    main()
