"""Second duplicate check, by meaning: report only, nothing is changed.

Flags pairs (main vs pilot, main vs main) whose gold calls share the same required text values, whatever the wording
(for example both have "LeBron James", or the same city pair). Pairs the wording check already handles (token_sort_ratio
>= 80) are left out.

For every required gold argument that has text (>= 3 letters) the accepted spellings are one "slot"; a slot of item A
matches a slot of item B if they share a spelling (lowercase, punctuation removed). Slots made only of units, colors,
shapes or generic science terms are ignored. A pair is flagged if
  - all slots of both items match (same set of values), or
  - at least 2 slots match (e.g. the same city pair).
A single shared entity next to other, different values is NOT flagged. A pair that shares only an entity but asks a
different question can still be flagged when it has no other text value; that is why the gold function names and all
text values are printed: the author decides pair by pair. Saved in data/main/meaning_duplicates.csv (empty `decision`).

usage: python scripts/check_meaning_duplicates.py
"""
import csv
import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import select_main_items as S
from check_near_duplicates import GENERIC_SPARE_WORDS, MAIN, PILOT, kind, read_en, read_gold, text_params, token_sort_ratio

ROOT = Path(__file__).resolve().parent.parent


def slots(gt):
    out = {}
    for p, vals in text_params(gt).items():
        variants = {S.words_of(v) for v in vals}
        variants = {v for v in variants if v and not set(v.split()) <= GENERIC_SPARE_WORDS}
        if variants:
            out[p] = variants
    return out


def main():
    main_q, pilot_q = read_en(MAIN), read_en(PILOT)
    gold = {**read_gold(MAIN), **read_gold(PILOT)}
    allq = {**main_q, **pilot_q}
    sl = {i: slots(gold[i]) for i in allq}
    print(f"main items: {len(main_q)} | pilot items: {len(pilot_q)} | items with at least one usable text value: "
          f"{sum(1 for i in allq if sl[i])}")

    def compare(a, b):
        matched = [(pa, pb) for pa, va in sl[a].items() for pb, vb in sl[b].items() if va & vb]
        n = len({pa for pa, _ in matched})
        flagged = bool(sl[a]) and bool(sl[b]) and ((n == len(sl[a]) == len(sl[b])) or n >= 2)
        return flagged, matched

    found = []
    for a in main_q:
        for p in pilot_q:
            ok, m = compare(a, p)
            if ok and token_sort_ratio(main_q[a], pilot_q[p]) < 80:
                found.append((a, p, "main-pilot", m))
    for a, b in combinations(main_q, 2):
        ok, m = compare(a, b)
        if ok and token_sort_ratio(main_q[a], main_q[b]) < 80:
            found.append((a, b, f"main-main {'-'.join(sorted([kind(a), kind(b)]))}", m))

    def show_values(i):
        return "; ".join(f"{p}={sorted(v)[0]!r}" for p, v in sl[i].items())

    rows = []
    for n, (a, b, t, m) in enumerate(sorted(found, key=lambda x: (x[2], x[0])), 1):
        same_fn = gold[a]["name"] == gold[b]["name"]
        shared = sorted({v for pa, pb in m for v in sl[a][pa] & sl[b][pb]})
        rows.append([n, t, a, b, "same" if same_fn else "different", gold[a]["name"], gold[b]["name"], "; ".join(shared),
                     f"{token_sort_ratio(allq[a], allq[b]):.0f}", allq[a], allq[b], ""])
    out = ROOT / "data" / "main" / "meaning_duplicates.csv"
    header = ["pair", "pair_type", "item_a", "item_b", "gold_function", "function_a", "function_b", "shared_values",
              "wording_score", "query_a", "query_b", "decision"]
    # decisions already recorded by the author are carried over (matched by the two item ids, not by the pair number);
    # a decided pair that is no longer flagged (one item was dropped) stays in the file at the end as "resolved"
    old = {}
    if out.exists():
        for r in csv.DictReader(open(out, encoding="utf-8-sig", newline="")):
            old[(r["item_a"], r["item_b"])] = r
    seen = set()
    for r in rows:
        prev = old.get((r[2], r[3])) or old.get((r[3], r[2]))
        if prev:
            r[11] = prev["decision"]
            seen.add((prev["item_a"], prev["item_b"]))
    resolved = [[r[k] for k in header] for key, r in old.items() if key not in seen and r["decision"]]
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
        w.writerows(resolved)
    if resolved:
        print(f"{len(resolved)} earlier decided pairs are no longer flagged and are kept at the end of the file")

    print(f"\nflagged pairs: {len(rows)} (main-pilot {sum(r[1] == 'main-pilot' for r in rows)}, "
          f"main-main {sum(r[1] != 'main-pilot' for r in rows)}); same gold function: {sum(r[4] == 'same' for r in rows)}")
    for r in rows:
        print(f"\n#{r[0]} [{r[1]}] {r[2]}  vs  {r[3]}   function: {r[4]} | shared: {r[7]} | wording score {r[8]}")
        print(f"   A ({r[5]}): {r[9]}")
        print(f"   B ({r[6]}): {r[10]}")
    print(f"\nsaved to {out}; nothing was changed")


if __name__ == "__main__":
    main()
