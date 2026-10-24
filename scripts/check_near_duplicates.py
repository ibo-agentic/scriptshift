"""Near-duplicate check of the main-set English queries by wording, with a plan and (with --apply) the changes.

Compares every main-set query with (a) the 30 pilot queries and (b) every other main-set query.
Score = rapidfuzz.fuzz.token_sort_ratio on normalized text (lowercase, punctuation removed): the words are sorted, then
the Indel similarity of the two strings is 100 * 2 * LCS / (len_a + len_b). rapidfuzz is not installed in this project;
this file computes the same number in pure Python (bit-parallel LCS, tested against a plain dynamic-programming LCS).
Pairs with a score >= 80 are flagged and saved in data/main/near_duplicates.csv.

Rules (PLAN.md section 4):
  - main item ~ pilot item                     -> multiple: dropped | simple_python: replaced by the next spare
  - simple_python item ~ multiple item         -> the simple_python item is replaced by the next spare (multiple stays)
  - multiple item ~ multiple item              -> the one with the higher item number is dropped
  - a spare is skipped if it near-duplicates a pilot item, an item that stays or an earlier replacement, or if all its
    required text values are only units, colors, shapes or generic science terms (GENERIC_SPARE_WORDS)
  - if the spares run out, the main set gets fewer simple_python items (the final count is reported)

usage: python scripts/check_near_duplicates.py            (report and plan only)
       python scripts/check_near_duplicates.py --apply    (changes main_items.csv, eligible_pool.csv, replacements.csv;
                                                           originals are copied to data/main/backup_before_dedup/)
"""
import argparse
import csv
import json
import re
import shutil
import sys
from datetime import date
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import select_main_items as S
from build_pilot_items import FORMS, fix_types

ROOT = Path(__file__).resolve().parent.parent
MAIN, POOL = ROOT / "data" / "main" / "main_items.csv", ROOT / "data" / "main" / "eligible_pool.csv"
PILOT, REPL = ROOT / "data" / "pilot" / "pilot_items.csv", ROOT / "data" / "main" / "replacements.csv"
BATCH = 40

# words that make a required text value "generic": units, colors, shapes, generic science terms (+ small function words)
UNITS = set("""inch inches in cm centimeter centimeters mm millimeter millimeters m meter meters metre metres km kilometer
kilometers kilometre kilometres mile miles ft foot feet yard yards h hr hrs hour hours min minute minutes s sec second
seconds day days week weeks month months year years kg kilogram kilograms g gram grams mg lb lbs pound pounds oz ounce
ounces ton tons tonne tonnes l liter liters litre litres ml gallon gallons joule joules kelvin celsius fahrenheit c f k
watt watts kw volt volts amp amps ohm ohms pascal pascals pa newton newtons hz atm atmosphere atmospheres bar degree
degrees percent percentage per square cubic unit units pixel pixels mph kph mps""".split())
COLORS = set("red blue green yellow orange purple violet pink black white brown gray grey cyan magenta gold silver beige".split())
SHAPES = set("""circle circles rectangle rectangles triangle triangles square squares sphere spheres cube cubes cylinder
cone ellipse oval polygon pentagon hexagon""".split())
SCIENCE = set("""ice water steam gas gases liquid solid air oxygen hydrogen carbon neuron neurons gaba brain cell cells
protein proteins entropy energy force mass speed velocity acceleration temperature pressure heat dynamic static
analysis entire all full part whole molecule molecules atom atoms""".split())
FUNCTION = set("of the a an and in on at to for with by from".split())
GENERIC_SPARE_WORDS = UNITS | COLORS | SHAPES | SCIENCE | FUNCTION


def normalize(s):
    return " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())


def lcs_len(a, b):
    """length of the longest common subsequence (bit-parallel, Hyyro 2004)"""
    if not a or not b:
        return 0
    mask = (1 << len(a)) - 1
    pos = {}
    for i, ch in enumerate(a):
        pos[ch] = pos.get(ch, 0) | (1 << i)
    v = mask
    for ch in b:
        m = pos.get(ch, 0)
        u = v & m
        v = ((v + u) | (v & ~m)) & mask
    return len(a) - bin(v).count("1")


def lcs_len_dp(a, b):
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if ca == cb else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def token_sort_ratio(x, y):
    a, b = " ".join(sorted(normalize(x).split())), " ".join(sorted(normalize(y).split()))
    if not a and not b:
        return 100.0
    return 100.0 * 2 * lcs_len(a, b) / (len(a) + len(b))


def read_en(path):
    return {r["item_id"]: r["query"] for r in csv.DictReader(open(path, encoding="utf-8-sig", newline="")) if r["form"] == "en"}


def read_gold(path):
    return {r["item_id"]: json.loads(r["gt_call_json"]) for r in csv.DictReader(open(path, encoding="utf-8-sig", newline="")) if r["form"] == "en"}


def kind(i):
    return "simple" if i.startswith("simple") else "multiple"


def num(i):
    return int(i.rsplit("_", 1)[1])


def text_params(gt):
    """{param: [accepted text variants]} for the required gold arguments that have text (>= 3 letters)"""
    out = {}
    for p, acc in S.required(gt["arguments"]).items():
        vals = [x for a in acc for x in (a if isinstance(a, list) else [a]) if isinstance(x, str) and len(re.findall(r"[A-Za-z]", x)) >= 3]
        if vals:
            out[p] = vals
    return out


def is_generic(gt):
    """True if all required text values are only units, colors, shapes or generic science terms"""
    tp = text_params(gt)
    return bool(tp) and all(all(set(S.words_of(v).split()) <= GENERIC_SPARE_WORDS for v in vals) for vals in tp.values())


def build_rows(iid):
    """the 5 csv rows of a raw BFCL item (same format as select_main_items.py)"""
    source = "simple_python" if iid.startswith("simple") else "multiple"
    qs, ans = S.load(source)
    q = qs[iid]
    query = q["question"][0][0]["content"].strip().strip("'")
    fname, args = next(iter(ans[iid]["ground_truth"][0].items()))
    tools = [{"type": "function", "function": fix_types(fn)} for fn in q["function"]]
    return [{"item_id": iid, "form": f, "query": query if f == "en" else "",
             "tools_json": json.dumps(tools, ensure_ascii=False), "gt_call_json": json.dumps({"name": fname, "arguments": args}, ensure_ascii=False)}
            for f in FORMS], query


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=80)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true", help="apply even if replacements.csv already has rows")
    cli = ap.parse_args()
    T = cli.threshold

    main_q, pilot_q = read_en(MAIN), read_en(PILOT)
    pool = list(csv.DictReader(open(POOL, encoding="utf-8-sig", newline="")))
    spares = [p for p in sorted(pool, key=lambda p: int(p["draw_rank"])) if p["source"] == "simple_python" and p["selected"] == "0"]
    print(f"main items: {len(main_q)} | pilot items: {len(pilot_q)} | spare simple_python items: {len(spares)} | threshold {T:g}")

    import random
    rnd = random.Random(1)
    for _ in range(300):
        a = "".join(rnd.choice("abc d") for _ in range(rnd.randint(0, 40)))
        b = "".join(rnd.choice("abc d") for _ in range(rnd.randint(0, 40)))
        assert lcs_len(a, b) == lcs_len_dp(a, b), (a, b)
    print("self test: bit-parallel LCS == dynamic-programming LCS on 300 random pairs")

    pairs = []
    for i, q in main_q.items():
        for p, pq in pilot_q.items():
            s = token_sort_ratio(q, pq)
            if s >= T:
                pairs.append((s, i, p, "main-pilot"))
    for (i, qi), (j, qj) in combinations(main_q.items(), 2):
        s = token_sort_ratio(qi, qj)
        if s >= T:
            pairs.append((s, i, j, f"main-main {'-'.join(sorted([kind(i), kind(j)]))}"))
    pairs.sort(key=lambda x: (-x[0], x[1]))
    allq = {**main_q, **pilot_q}
    out = ROOT / "data" / "main" / "near_duplicates.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["score", "item_a", "item_b", "pair_type", "query_a", "query_b"])
        for s, a, b, t in pairs:
            w.writerow([f"{s:.1f}", a, b, t, allq[a], allq[b]])
    print(f"flagged pairs: {len(pairs)} (saved to {out.name})")

    # ---- plan
    remove = {}
    for s, a, b, t in pairs:
        if t == "main-pilot":
            remove.setdefault(a, f"near-duplicate of pilot item {b} (score {s:.0f})")
        elif t == "main-main multiple-simple":
            simple, mult = (a, b) if kind(a) == "simple" else (b, a)
            remove.setdefault(simple, f"near-duplicate of multiple item {mult} (score {s:.0f}); the multiple item stays")
        elif t == "main-main multiple-multiple":
            later = max((a, b), key=num)
            remove.setdefault(later, f"near-duplicate of multiple item {min((a, b), key=num)} (score {s:.0f}); the item with the lower number stays")
    staying = [i for i in main_q if i not in remove]
    spare_gold = S.load("simple_python")[1]
    chosen, plan, skipped = [], [], []
    spare_iter = iter(spares)
    for item, reason in sorted(remove.items(), key=lambda kv: (kind(kv[0]), num(kv[0]))):
        if kind(item) == "multiple":
            plan.append((item, reason, "DROP", "", ""))
            continue
        for sp in spare_iter:
            sid, sq = sp["item_id"], sp["query"]
            gt = {"arguments": next(iter(spare_gold[sid]["ground_truth"][0].values()))}
            if is_generic(gt):
                skipped.append((sid, "all required text values are only units, colors, shapes or generic science terms: "
                                + "; ".join(f"{p}={v[0]!r}" for p, v in text_params(gt).items())))
                continue
            clash = next((o for o in list(pilot_q) + staying + chosen if token_sort_ratio(sq, allq[o]) >= T), None)
            if clash:
                skipped.append((sid, f"near-duplicate of {clash}"))
                continue
            chosen.append(sid)
            allq[sid] = sq
            plan.append((item, reason, "REPLACE", sid, sq))
            break
        else:
            plan.append((item, reason, "NO SPARE LEFT", "", ""))

    print("\n### PLAN")
    for item, reason, action, new, sq in plan:
        print(f"  {item:<20}{action + (' by ' + new if new else ''):<34}{reason}" + (f"\n      new: {sq}" if sq else ""))
    print("\n### SPARES SKIPPED")
    for sid, why in skipped:
        print(f"  {sid:<20}{why}")
    n_drop = sum(1 for p in plan if p[2] == "DROP")
    n_rep = sum(1 for p in plan if p[2] == "REPLACE")
    n_none = sum(1 for p in plan if p[2] == "NO SPARE LEFT")
    final = len(main_q) - n_drop - n_none
    n_simple = sum(1 for i in main_q if kind(i) == "simple") - n_none
    print(f"\nsummary: {n_rep} simple_python replaced, {n_drop} multiple dropped, {n_none} simple_python without a spare -> "
          f"{final} items = {n_simple} simple_python + {final - n_simple} multiple; spares skipped {len(skipped)}, "
          f"spares left {len(spares) - len(skipped) - n_rep}")
    if not cli.apply:
        print("nothing changed (use --apply)")
        return

    # ---- apply
    log = list(csv.reader(open(REPL, encoding="utf-8-sig", newline="")))
    if len(log) > 1 and not cli.force:
        sys.exit("replacements.csv already has rows: refusing to apply twice (use --force)")
    rows = list(csv.DictReader(open(MAIN, encoding="utf-8-sig", newline="")))
    fields = list(rows[0].keys())
    gone = {p[0] for p in plan if p[2] in ("DROP", "NO SPARE LEFT", "REPLACE")}
    for r in rows:
        if r["item_id"] in gone and r["form"] != "en" and r["query"].strip():
            sys.exit(f"{r['item_id']} {r['form']} already has Bangla text: refusing to remove it")
    backup = ROOT / "data" / "main" / "backup_before_dedup"
    backup.mkdir(exist_ok=True)
    for p in (MAIN, POOL, REPL):
        shutil.copy2(p, backup / p.name)
    new_rows, repl_of = [], {p[0]: p[3] for p in plan if p[2] == "REPLACE"}
    done = set()
    for r in rows:
        iid = r["item_id"]
        if iid in repl_of:
            if iid not in done:
                new_rows += build_rows(repl_of[iid])[0]
                done.add(iid)
        elif iid not in gone:
            new_rows.append(r)
    order = list(dict.fromkeys(r["item_id"] for r in new_rows))
    with open(MAIN, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(new_rows)
    batch_of = {iid: i // BATCH + 1 for i, iid in enumerate(order)}
    notes = {p[0]: ("dropped: " if p[2] != "REPLACE" else f"replaced by {p[3]}: ") + p[1] for p in plan}
    notes.update({p[3]: f"replacement for {p[0]}" for p in plan if p[2] == "REPLACE"})
    notes.update({sid: f"spare skipped: {why}" for sid, why in skipped})
    pool_fields = list(pool[0].keys()) + (["note"] if "note" not in pool[0] else [])
    for p in pool:
        p["selected"] = int(p["item_id"] in batch_of)
        p["batch"] = batch_of.get(p["item_id"], "")
        p["note"] = notes.get(p["item_id"], "")
    with open(POOL, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pool_fields)
        w.writeheader()
        w.writerows(pool)
    today = date.today().isoformat()
    with open(REPL, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        for item, reason, action, new, _ in plan:
            w.writerow([today, kind(item) if kind(item) == "multiple" else "simple_python", item, new, reason, "author (approved 2026-10-25)"])
        for sid, why in skipped:
            w.writerow([today, "spare_skipped", sid, "", why, "author (rule approved 2026-10-25)"])
    print(f"\napplied. backup of the old files: {backup}")
    print(f"main_items.csv: {len(order)} items = {sum(1 for i in order if kind(i) == 'simple')} simple_python + "
          f"{sum(1 for i in order if kind(i) == 'multiple')} multiple, {len(new_rows)} rows")


if __name__ == "__main__":
    main()
