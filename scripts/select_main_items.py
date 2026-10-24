"""Select the main-set items from BFCL v4 simple_python and multiple (raw files are only read).

Rules, applied in this order (counts are printed after each one):
  R1 short, clean request      query <= 200 characters, <= 40 words, no code-like characters
                               (the pilot used about 100 characters; raised for the main set because `multiple`
                               queries are longer. Both limits are needed: 200 characters alone gives 89 multiple items.)
  R2 text value                a required gold argument has a string value (>= 3 letters, not a generic word such as a
                               unit or a sort order) that could change across scripts: names, places, foods, products...
  R3 selection rule (OPEN 6)   every required gold value is present in the English query, in the same wording:
                               strings as a word sequence, numbers as digits or an English number word, lists element
                               by element. Drops items like pilot item 196 (gold date 08-16-2022, query 2022/08/16).
                               Optional arguments (gold list contains "") are ignored. Booleans cannot be checked
                               against the query and are ignored (their number is reported).
  R4 pilot items removed       all 30 pilot items are excluded (OPEN 2)
Then ALL eligible multiple items are taken and the set is filled to 240 with simple_python items drawn at random
with seed 2026 (OPEN 1; 101 multiple + 139 simple_python with the limits above).

"Everyday" cannot be checked by a script: the author sees every drawn item in the writing sheets.
eligible_pool.csv lists the next simple_python items in draw order as replacements (see PLAN.md for the
replacement rule). multiple has no spare items, because all of them are used.

Writes: data/main/main_items.csv (pilot long format, only `en` filled; items grouped in 6 batches of 40,
multiple and simple_python spread evenly over the batches and interleaved) and data/main/eligible_pool.csv
(draw order, selected, batch).
"""
import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pilot_items import FORMS, fix_types

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "bfcl"
OUT_DIR = ROOT / "data" / "main"
SEED = 2026
N_TOTAL = 240
N_BATCHES = 6
SOURCES = {"simple_python": "BFCL_v4_simple_python", "multiple": "BFCL_v4_multiple"}

GENERIC = {"unit", "units", "metric", "imperial", "ascending", "descending", "celsius", "fahrenheit", "kelvin",
           "fastest", "shortest", "default", "all", "none", "yes", "no", "dictionary", "json", "csv"}
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
NUMBER_WORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
                     "hundred": 100, "thousand": 1000})


def words_of(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def in_query(value, qwords):
    v = words_of(value)
    return bool(v) and f" {v} " in f" {qwords} "


def number_in_query(n, query):
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", query)]
    toks = re.findall(r"[a-z]+", query.lower())
    nums += [NUMBER_WORDS[t] for t in toks if t in NUMBER_WORDS]
    return float(n) in nums


def required(args):
    return {p: acc for p, acc in args.items() if "" not in acc}


def value_ok(acc, query, qwords):
    """is one accepted-value list supported by the query?  returns (ok, is_bool)"""
    kinds = {type(a) for a in acc}
    if kinds <= {bool}:
        return True, True
    for a in acc:
        if isinstance(a, bool):
            continue
        if isinstance(a, str) and in_query(a, qwords):
            return True, False
        if isinstance(a, (int, float)) and number_in_query(a, query):
            return True, False
        if isinstance(a, list) and a and all(
                (isinstance(x, str) and in_query(x, qwords)) or
                (isinstance(x, (int, float)) and not isinstance(x, bool) and number_in_query(x, query)) for x in a):
            return True, False
    return False, False


def has_text_value(args):
    for acc in required(args).values():
        for a in acc:
            for x in (a if isinstance(a, list) else [a]):
                if isinstance(x, str) and len(re.findall(r"[A-Za-z]", x)) >= 3 and words_of(x) not in GENERIC:
                    return True
    return False


MAX_CHARS, MAX_WORDS = 200, 40      # R1; changed with --max-chars / --max-words


def short_clean(q):
    return len(q) <= MAX_CHARS and len(q.split()) <= MAX_WORDS and not re.search(r"[\[\]{}`_=<>\\]", q)


def load(source):
    qs = {}
    for line in open(RAW / f"{SOURCES[source]}.json", encoding="utf-8"):
        d = json.loads(line)
        qs[d["id"]] = d
    ans = {}
    for line in open(RAW / f"{SOURCES[source]}_answer.json", encoding="utf-8"):
        d = json.loads(line)
        ans[d["id"]] = d
    return qs, ans


def main():
    global MAX_CHARS, MAX_WORDS, OUT_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS)
    ap.add_argument("--max-words", type=int, default=MAX_WORDS)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--allow-short", action="store_true", help="write the files even if a source has < 120 eligible items")
    cli = ap.parse_args()
    MAX_CHARS, MAX_WORDS, OUT_DIR = cli.max_chars, cli.max_words, Path(cli.out_dir)
    print(f"R1: <= {MAX_CHARS} characters, <= {MAX_WORDS} words")
    pilot_ids ={r["item_id"] for r in csv.DictReader(open(ROOT / "data" / "pilot" / "pilot_items.csv", encoding="utf-8-sig", newline=""))}
    print(f"pilot items to exclude: {len(pilot_ids)}")
    pools, rows_by_id, stats = {}, {}, {}
    for source in SOURCES:
        qs, ans = load(source)
        ids = sorted(qs, key=lambda i: int(i.rsplit("_", 1)[1]))
        c = Counter(total=len(ids))
        keep = []
        for iid in ids:
            q = qs[iid]
            query = q["question"][0][0]["content"].strip().strip("'")
            fname, args = next(iter(ans[iid]["ground_truth"][0].items()))
            if not short_clean(query):
                continue
            c["R1 short, clean request"] += 1
            if not has_text_value(args):
                continue
            c["R2 text value"] += 1
            qwords = words_of(query)
            checks = [value_ok(acc, query, qwords) for acc in required(args).values()]
            if not all(ok for ok, _ in checks):
                continue
            c["R3 selection rule"] += 1
            if any(is_bool for _, is_bool in checks):
                c["  (of which have a required boolean, not checked)"] += 1
            if iid in pilot_ids:
                continue
            c["R4 pilot items removed"] += 1
            keep.append(iid)
            tools = [{"type": "function", "function": fix_types(fn)} for fn in q["function"]]
            rows_by_id[iid] = (query, tools, {"name": fname, "arguments": args})
        pools[source], stats[source] = keep, c

    print(f"\n{'rule':<52}{'simple_python':>15}{'multiple':>10}")
    for key in ["total", "R1 short, clean request", "R2 text value", "R3 selection rule",
                "  (of which have a required boolean, not checked)", "R4 pilot items removed"]:
        print(f"{key:<52}{stats['simple_python'][key]:>15}{stats['multiple'][key]:>10}")

    rng = random.Random(SEED)
    order = {}
    for source in SOURCES:
        ids = list(pools[source])
        rng.shuffle(ids)
        order[source] = ids
    n_multiple = len(order["multiple"])                 # all eligible multiple items
    n_simple = N_TOTAL - n_multiple                     # filled to the total with simple_python
    if n_simple > len(order["simple_python"]) or n_simple < 0:
        sys.exit(f"cannot reach {N_TOTAL} items: {n_multiple} multiple + {len(order['simple_python'])} simple_python eligible")
    chosen = {"simple_python": order["simple_python"][:n_simple], "multiple": order["multiple"]}
    per_batch = N_TOTAL // N_BATCHES
    sequence, batch_of = [], {}
    m_at = s_at = 0
    for b in range(N_BATCHES):
        m_n = n_multiple // N_BATCHES + (1 if b < n_multiple % N_BATCHES else 0)    # e.g. 101 -> 17,17,17,17,17,16
        m_ids = chosen["multiple"][m_at:m_at + m_n]
        s_ids = chosen["simple_python"][s_at:s_at + per_batch - m_n]
        m_at, s_at = m_at + m_n, s_at + per_batch - m_n
        keyed = [((i + 0.5) / len(s_ids), 0, iid) for i, iid in enumerate(s_ids)] + \
                [((i + 0.5) / len(m_ids), 1, iid) for i, iid in enumerate(m_ids)]
        for _, _, iid in sorted(keyed):                 # evenly mixed
            sequence.append(iid)
            batch_of[iid] = b + 1
    print(f"\nbatches (simple_python + multiple): " + ", ".join(
        f"{sum(1 for i in sequence if batch_of[i] == b and i.startswith('simple'))}+"
        f"{sum(1 for i in sequence if batch_of[i] == b and i.startswith('multiple'))}" for b in range(1, N_BATCHES + 1)))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "main_items.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "form", "query", "tools_json", "gt_call_json"])
        for iid in sequence:
            query, tools, gt = rows_by_id[iid]
            for form in FORMS:
                w.writerow([iid, form, query if form == "en" else "",
                            json.dumps(tools, ensure_ascii=False), json.dumps(gt, ensure_ascii=False)])
    with open(OUT_DIR / "eligible_pool.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "source", "draw_rank", "selected", "batch", "query"])
        for source in SOURCES:
            for rank, iid in enumerate(order[source], 1):
                w.writerow([iid, source, rank, int(iid in batch_of), batch_of.get(iid, ""), rows_by_id[iid][0]])
    print(f"\nseed {SEED}: drawn {sum(len(v) for v in chosen.values())} items "
          f"({', '.join(f'{len(v)} {k}' for k, v in chosen.items())}) in {N_BATCHES} batches")
    print(f"wrote {OUT_DIR / 'main_items.csv'} ({len(sequence) * len(FORMS)} rows) and {OUT_DIR / 'eligible_pool.csv'}")


if __name__ == "__main__":
    main()
