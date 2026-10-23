import os
os.environ.setdefault("HF_HOME", r"C:\projects\scriptshift\hf_cache")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "Qwen/Qwen3-1.7B"
torch.manual_seed(0)

tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float16).to("cuda").eval()

tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    },
}]

prompts = {
    "english": "What is the weather in Dhaka today?",
    "bangla": "আজ ঢাকার আবহাওয়া কেমন?",
    "romanized": "aaj dhakar abohawa kemon?",
}

for name, text in prompts.items():
    msgs = [{"role": "user", "content": text}]
    prompt = tok.apply_chat_template(
        msgs, tools=tools, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    inputs = tok(prompt, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=128, do_sample=False)
    raw = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=False)
    print(f"=== {name}: {text}\n{raw}\n")

with torch.no_grad():
    o = model(**inputs, output_hidden_states=True)
hs = o.hidden_states
print(f"hidden_states tuple length: {len(hs)} (1 embedding + {len(hs) - 1} layers)")
print(f"hidden size: {hs[-1].shape[-1]}")
print(f"VRAM allocated: {torch.cuda.memory_allocated() / 1e9:.2f} GB, peak: {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
