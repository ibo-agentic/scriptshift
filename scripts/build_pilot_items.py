"""Build data/pilot/pilot_items.csv from the raw BFCL simple_python files (raw files are only read)."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "bfcl"
OUT = ROOT / "data" / "pilot" / "pilot_items.csv"

# cities / places / people / foods / products with a text argument that can change across scripts
PILOT_IDS = [186, 187, 188, 196, 199, 203, 193, 377, 369, 33,
             205, 250, 394, 273,
             303, 304, 306, 309, 314, 316, 332, 92, 288, 286,
             357, 360, 374, 215, 295, 328]
FORMS = ["en", "bn_native", "bn_roman", "bn_mixed", "bn_partial"]

TYPE_MAP = {"dict": "object", "float": "number", "tuple": "array", "any": "string"}


def fix_types(node):
    """BFCL uses python type names; chat templates expect JSON-schema names."""
    if isinstance(node, dict):
        return {k: (TYPE_MAP.get(v, v) if k == "type" and isinstance(v, str) else fix_types(v))
                for k, v in node.items()}
    if isinstance(node, list):
        return [fix_types(x) for x in node]
    return node


def main():
    questions = {}
    for line in open(RAW / "BFCL_v4_simple_python.json", encoding="utf-8"):
        d = json.loads(line)
        questions[d["id"]] = d
    answers = {}
    for line in open(RAW / "BFCL_v4_simple_python_answer.json", encoding="utf-8"):
        d = json.loads(line)
        answers[d["id"]] = d

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "form", "query", "tools_json", "gt_call_json"])
        for n in PILOT_IDS:
            iid = f"simple_python_{n}"
            q = questions[iid]
            query = q["question"][0][0]["content"].strip().strip("'")
            tools = [{"type": "function", "function": fix_types(fn)} for fn in q["function"]]
            fn_name, fn_args = next(iter(answers[iid]["ground_truth"][0].items()))
            gt = {"name": fn_name, "arguments": fn_args}  # arguments: {param: [accepted values]}
            for form in FORMS:
                w.writerow([iid, form, query if form == "en" else "",
                            json.dumps(tools, ensure_ascii=False),
                            json.dumps(gt, ensure_ascii=False)])
    print(f"wrote {OUT} ({len(PILOT_IDS) * len(FORMS)} rows)")


if __name__ == "__main__":
    main()
