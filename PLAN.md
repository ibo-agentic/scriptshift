# ScriptShift: study plan

**Status: DRAFT, not frozen.** Last updated 2026-10-24. Target venue: ACL / EMNLP 2027.
Items marked **[DRAFT]** are proposals written by Claude Code from the pilot and need the author's decision before the freeze.
Items marked **[OPEN]** are decisions nobody has made yet (listed again at the end).
After the freeze (git tag, done by the author) the hypotheses and scoring rules must not change.

## 1. Research questions

1. **RQ1.** Does an LLM's tool calling change when the same request is written in a different script or style (English, Bangla script, romanized Bangla, mixed, partial)?
2. **RQ2.** If it changes, how does it fail? (Which error types, in which form?)
3. **RQ3.** Does the effect depend on the model family or model size?
4. **RQ4.** Mechanism: what is different inside the model when the request is not English?
5. **RQ5.** Can a simple fix remove the gap?

## 2. Hypotheses [DRAFT]

Written after a 30-item pilot (section 11). The main run must test them on data that was not used to build the scorer (see OPEN 2).

- **H1 (script effect).** For each model, tool-calling accuracy in `bn_native` and in `bn_roman` is lower than in `en`.
- **H2 (more Latin letters, smaller drop).** Accuracy follows this order: `en` and `bn_partial` highest, then `bn_mixed`, then `bn_roman` and `bn_native` lowest. The more of the request that stays in English letters, the smaller the drop.
- **H3 (error types differ by form).** In `bn_native` most errors are `wrong_lang_arg` (the model copies the value in Bangla script). In `bn_roman` most errors are `no_call` (the model does not call the tool) or a wrong value.
- **H4 (model dependence).** Going from Qwen3-1.7B to Qwen3-4B does not remove the gap. The size of the gap differs between model families.
- **H5 (mechanism).** Inside the model, the tool-related hidden representation of a non-English request is further from the English one (larger cosine gap), and a larger gap goes with a higher chance of failure. Adding the English-minus-Bangla direction at inference recovers part of the lost accuracy.

E4 (fixes) is exploratory: no confirmatory hypothesis, all results are reported.

## 3. Experiments

| id | what | model format |
|---|---|---|
| E1 | Behavior: accuracy per model x form | any |
| E2 | Error taxonomy: error category per model x form | any |
| E3 | Mechanism: tool vectors, cosine gap, steering (H5) | HF transformers, safetensors, fp16, no quantization |
| E4 | Fixes (exploratory) | any |

## 4. Data

- **Source.** BFCL v4 `simple_python` (Gorilla repo, Apache-2.0). Raw copy in `data/raw/bfcl/`, never edited.
- **Pilot.** 30 items x 5 forms = 150 rows, `data/pilot/pilot_items.csv` (long format: item_id, form, query, tools_json, gt_call_json).
- **Item choice.** Single-turn requests whose gold arguments include a name, place or other text that could change across scripts (cities, people, foods, products). Short, everyday requests. No items with only numbers.
- **Main set.** Size and selection: **[OPEN 1]**.

## 5. The five forms and their writing rules

| form | meaning |
|---|---|
| `en` | original BFCL English query |
| `bn_native` | all Bangla script, names too |
| `bn_roman` | Bangla words in English letters, the way the author types on a phone. No English words except names |
| `bn_mixed` | natural Banglish: Bangla grammar, English words where a speaker really uses them |
| `bn_partial` | Bangla script, but the values the tool needs ("Must keep") copied exactly in English |

Writing rules (from the author's writing sheet):

1. Same meaning in all forms. Every value in "Must keep" must appear.
2. Numbers are always English digits 0-9, in every form.
3. Do not fix spelling to look perfect. Natural typing is the point.
4. An awkward item is written the way a Bangla speaker would write it, with a note.

**No-extra-answer rule.** No form may contain more of the answer than the English query does. A value may only appear in the form and wording the English query uses, never in the format the tool wants. Examples of what this forbids: writing a number as a digit when English writes the word ("three"); capitalized answer values when English is lowercase; a date in the tool's format when English writes it another way; an answer word that is not in the English query ("Carbohydrates" for "carbs").

Process: the `bn_native` form was first drafted by Gemini, then reviewed and edited by the author. `bn_roman`, `bn_mixed` and `bn_partial` were reviewed by the author. Every item has the note "author checked". [DRAFT: for the main set, state here who writes the forms and how they are checked, OPEN 3.]

## 6. Models

| model | where | role |
|---|---|---|
| Qwen/Qwen3-1.7B | laptop (RTX 4060) | pilot, debugging, E3 development |
| Qwen/Qwen3-4B | Kaggle 2x T4 | main |
| google/gemma-3-4b-it | Kaggle 2x T4 | main |
| meta-llama/Llama-3.1-8B-Instruct | Kaggle 2x T4 | main |

Whether Qwen3-1.7B is part of the main tables: **[OPEN 4]**.

## 7. Prompt and decoding

- Greedy decoding (`do_sample=False`), `max_new_tokens=256`, seed 0, batch size 1, one user turn.
- Qwen3: thinking off (`enable_thinking=False`).
- dtype fp16 for all models except Gemma-3-4B-it, which was run in float32 on Kaggle [author to add the reason].
- Every run saves: model name and revision, prompt template (and the full chat template), decoding settings, dtype, GPU names, library versions, git commit hash, SHA-256 of `pilot_items.csv`, and the full prompt and raw output of every row.
- **Tool mode** (saved in the metadata as `tool_mode`):
  - `native`: the model's own chat template with the tool schema. Qwen3 and Llama-3.1 support this. Gemma 3's template has no tool support, so it cannot be run this way.
  - `prompt_injected`: the tool schema in one fixed system message ("You have access to the following functions: ... respond with only a JSON object {"name": ..., "arguments": {...}} and nothing else"), identical for every model. Gemma was run this way.
  - **[DRAFT]** The cross-model comparison uses `prompt_injected` (the only prompt all three models share). `native` results are reported next to it for the models that support it.

## 8. Scoring

Each output gets exactly one label. Two independent switches give four numbers per output.

**Value typing**
- **PRIMARY: types normalized.** A string-encoded value is converted before comparing: `"7"` -> 7, `"true"` -> true, `'["a","b"]'` -> list, `"['a','b']"` -> list. The value is accepted if it matches either as written or after conversion.
- **SECONDARY: BFCL typing.** The value must have the right type as written (`"7"` is not 7).
- Reason: Llama 3.1 writes every value as a string, which made its English accuracy look like 40%.

**Output format**
- **Strict.** The whole output must be only one call: `<tool_call>{...}</tool_call>`, a code-fenced JSON block, or bare JSON. Anything else around the call is `format_break`.
- **Lenient.** The first JSON call found anywhere in the text is scored.
- **[OPEN 5]** Which format mode is the headline. Both are always reported.

**Every scorer rule** (`scripts/score_pilot.py`)

1. *Cleaning.* These tokens are removed before parsing: `<|im_end|>`, `<|endoftext|>`, `<|eot_id|>`, `<|eom_id|>`, `<|end_of_text|>`, `<|python_tag|>`, `<end_of_turn>`, `<eos>`. Llama's `<|python_tag|>` and `<|eom_id|>` are normal tool-call tokens and are not a format error.
2. *Strict parse.* The cleaned text must match one of the three allowed wrappers and the inside must be a JSON object. If it does not, but a call-like text exists (a `<tool_call>` tag or a JSON object with a `name`), the label is `format_break`; if there is no call at all, `no_call`.
3. *Lenient parse.* Scan the text left to right for the first JSON object that has a `name` key. If none: `format_break` when a `<tool_call>` tag exists (call is broken), otherwise `no_call`. Only the first call is scored; parallel calls are out of scope.
4. *Arguments key.* `arguments`, or `parameters` (Llama 3.1).
5. *Structure.* If `name` is not a string or the arguments are not an object: `other`.
6. *Tool name.* If it differs from the gold name: `wrong_tool`.
7. *Optional and missing arguments.* The gold value list for an argument may contain `""`, which means the argument may be left out. A missing argument without `""`: `wrong_value`.
8. *Value match (BFCL style).* Strings: lowercase, remove whitespace and `, . / - _ * ^ ' "`, then compare to any accepted gold value. Numbers: equal as floats (booleans are not numbers). Lists: element by element in order; the gold list holds the accepted orders.
9. *Extra arguments.* An argument that is not in the gold arguments: `wrong_value`.
10. *Classifying a wrong value*, in this priority order when several arguments are wrong:
    1. `wrong_lang_arg`: the predicted string contains a Bangla-script character (U+0980 to U+09FF).
    2. `roman_leak`: the predicted string is a close spelling variant of an accepted gold string. Both must contain at least 2 Latin letters, the gold string must have at least 4 characters after cleaning, and the edit distance between them must be at most max(1, round(0.2 x gold length)). Before measuring, both strings are lowercased, accents removed, and reduced to letters and digits. Sidney vs Sydney counts; Aminé vs Eminem (2 edits, limit 1) does not.
    3. `wrong_value`: everything else (a different value, a wrong type, a date or number in another format).
11. *Not handled.* A Bangla-script value that is a reasonable translation of the English value is still `wrong_lang_arg`, because the tool expects the English value. Accent-only differences (Beyoncé vs Beyonce) can be labeled `roman_leak`. Truncated outputs (256-token limit) get whatever label the parse gives; the number of such rows is reported per model.

**Error categories**

| label | meaning |
|---|---|
| correct | right tool, all arguments match |
| no_call | no tool call in the output (a question, a refusal, plain text) |
| wrong_tool | a call to a different tool |
| wrong_lang_arg | an argument written in Bangla script |
| roman_leak | an argument that is a close spelling variant of the gold value |
| wrong_value | right tool, but a different, missing, extra or wrongly formatted argument |
| format_break | strict mode only: a call exists but there is text around it or the JSON is broken |
| other | a call-like object with an unusable structure |

## 9. Planned statistics [DRAFT]

- **Unit.** The item. Rows of the same item in different forms are paired.
- **Main test (H1, H2).** For each model, exact McNemar test (two-sided) of `en` against each other form. Report accuracy per form, the two discordant counts b and c, their sum, and the p-value.
- **Effect size.** Accuracy difference vs `en` with a 95% paired bootstrap interval (resampling items, 10,000 resamples, fixed seed).
- **Multiple tests.** Holm correction over all model x form comparisons in the main table. Raw p-values are shown as well.
- **Pooled model.** Logistic regression of correct/incorrect on form and model with item as the cluster (GEE, exchangeable, statsmodels), to test the form x model interaction (H4).
- **Error types (H3).** Exact test (Fisher/chi-square with simulated p) of the error-category distribution across forms, per model.
- **Mechanism (H5).** Per row: the cosine gap between hidden states of the non-English row and its English row at the decision position, then the relation to failure (logistic regression, rank correlation). Steering: accuracy before vs after with McNemar. Layer and position are fixed before looking at accuracy.
- **Both metrics.** Every test is run under the primary and the secondary scoring metric and both are reported.
- **Honesty.** Null and bad results are reported. Nothing is tuned on the test set. Pilot p-values are descriptive only (30 items per form, no correction).

## 10. Compute and logging

- Laptop (RTX 4060, 8 GB): pilots and debugging, models up to about 4B. Check that no other job holds the GPU before a run (at least 4 GB free).
- Kaggle 2x T4: main runs. The notebook `notebooks/kaggle_pilot_multi.ipynb` runs one model at a time and frees memory between models; `notebooks/kaggle_pilot_injected.ipynb` is the same code with `TOOL_MODE="prompt_injected"` for Qwen3-4B and Llama-3.1-8B.
- Kaggle has no git: the commit hash is typed into the notebook by hand (`GIT_COMMIT`).

## 11. Pilot lessons: what we changed because of the pilot

Pilot: 30 items, 5 forms, 4 models, greedy. Main numbers (primary metric, lenient format, correct out of 30):

| form | Qwen3-1.7B | Qwen3-4B | Gemma-3-4B* | Llama-3.1-8B |
|---|---|---|---|---|
| en | 28 | 28 | 28 | 28 |
| bn_native | 6 | 4 | 19 | 11 |
| bn_roman | 11 | 13 | 19 | 21 |
| bn_mixed | 24 | 26 | 25 | 23 |
| bn_partial | 25 | 30 | 28 | 25 |

*Gemma used the `prompt_injected` prompt; the others used `native`. A same-prompt run for Qwen3-4B and Llama is planned and may change this table.

What we changed:

1. **Writing sheet: 9 rows fixed** during the author's review: 8 answer-format leaks (digit instead of the English word, capitalized answer values, dates in the tool's format, an answer word not in the English query) and 1 translation error (item 357: নিরামিষ "vegetarian" changed to ভেগান "vegan"). This created the no-extra-answer rule (section 5).
2. **`roman_leak` rule tightened.** The first version used a similarity ratio and labeled Aminé (for Eminem) and a date format as `roman_leak`. It now uses the edit-distance rule, and only for strings with Latin letters (section 8).
3. **Scorer made model-aware before the Kaggle scores were seen.** Llama's `<|python_tag|>` / `<|eom_id|>` tokens and `parameters` key are accepted; the strict format accepts bare JSON and code fences.
4. **Primary metric changed to normalized types.** Under BFCL typing Llama scored 12/30 in English because it writes every value as a string. Normalization is now primary, BFCL typing secondary. While reading the `bn_roman` errors we found Llama also writes lists as Python-style strings (`"['a','b']"`); the converter was extended for this, for all models and forms.
5. **Prompt fairness.** Gemma 3's chat template has no tool support, so Gemma was given the tools in a system message while the others used their own templates. The notebook got a `TOOL_MODE` setting and a same-prompt run was planned.
6. **Gemma dtype** set to float32 on Kaggle.
7. **Notebook fixes:** recursive input-file search on Kaggle; model revision read from the cache path (newer `transformers` no longer exposes it); model cache kept outside the output folder.
8. **Truncation check.** No Kaggle model hit the 256-token limit; Qwen3-1.7B hit it in 3 rows (item 286 `bn_roman`, item 215 `bn_native` and `bn_partial`).
9. **Shared GPU.** A first run was slow because another job was using the GPU, so the GPU is checked before every run.
10. **Hand check of `bn_roman` wrong values** (`results/pilot/bn_roman_wrong_value.md`): some errors are not caused by the script (optional arguments filled in, a date in another format, a count of tickets), and a few are Bangla words read as names ("Garite Kore", "agami mashe", "bananor").

## 12. Open decisions

1. **OPEN 1.** Size and selection of the main item set (more BFCL items? other BFCL categories?).
2. **OPEN 2.** Are the 30 pilot items excluded from the main set, or kept and flagged? (The scorer was built looking at them.)
3. **OPEN 3.** Who writes and checks the forms for the main set; how many people; whether a second Bangla speaker checks a sample.
4. **OPEN 4.** Is Qwen3-1.7B in the main tables?
5. **OPEN 5.** Headline format mode (strict or lenient).
6. **OPEN 6.** Items whose gold value needs a format that is not in the query (item 196: date `08-16-2022`; some optional arguments in gold). Fix, drop or keep and flag.
7. **OPEN 7.** Why Gemma runs in float32; whether the other models should too for a fair comparison.
8. **OPEN 8.** The exact layer, token position and steering strength for E3 (fixed before looking at accuracy).
