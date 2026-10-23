"""Run the pilot: Qwen3-1.7B, fp16, greedy, thinking off, official chat template with tool schema.

Rows with an empty query are skipped. Raw outputs go to results/pilot/<run>.jsonl
(first line = run metadata, then one line per row).
"""
import argparse
import csv
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(ROOT / "hf_cache"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "Qwen/Qwen3-1.7B"
SEED = 0
MAX_NEW_TOKENS = 256


def git_state():
    def run(*a):
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()
    return {"commit": run("rev-parse", "HEAD") or None, "dirty": bool(run("status", "--porcelain"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default=str(ROOT / "data" / "pilot" / "pilot_items.csv"))
    ap.add_argument("--out-dir", default=str(ROOT / "results" / "pilot"))
    args = ap.parse_args()

    torch.manual_seed(SEED)
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float16).to("cuda").eval()
    snap = next((ROOT / "hf_cache" / "hub" / "models--Qwen--Qwen3-1.7B" / "snapshots").iterdir()).name

    meta = {
        "type": "meta",
        "model": MODEL,
        "revision": snap,
        "dtype": "float16",
        "decoding": {"do_sample": False, "max_new_tokens": MAX_NEW_TOKENS, "seed": SEED},
        "enable_thinking": False,
        "prompt_template": "tokenizer chat template, tools=<tools_json>, one user turn, no system prompt, add_generation_prompt=True",
        "chat_template": tok.chat_template,
        "git": git_state(),
        "torch": torch.__version__,
        "time": datetime.now().isoformat(timespec="seconds"),
    }

    rows = list(csv.DictReader(open(args.items, encoding="utf-8-sig", newline="")))
    todo = [r for r in rows if r["query"].strip()]
    print(f"{len(todo)} rows to run, {len(rows) - len(todo)} skipped (empty query)")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"qwen3-1.7b_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for r in todo:
            prompt = tok.apply_chat_template(
                [{"role": "user", "content": r["query"]}],
                tools=json.loads(r["tools_json"]),
                tokenize=False, add_generation_prompt=True, enable_thinking=False,
            )
            inputs = tok(prompt, return_tensors="pt").to("cuda")
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
            raw = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=False)
            f.write(json.dumps({"type": "row", "item_id": r["item_id"], "form": r["form"],
                                "query": r["query"], "prompt": prompt, "raw_output": raw},
                               ensure_ascii=False) + "\n")
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
