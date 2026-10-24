# ScriptShift: study plan

**Status: DRAFT, not frozen.** Last updated 2026-10-25. Target venue: ACL / EMNLP 2027.
Items marked **[DRAFT]** are proposals written by Claude Code and still need the author's confirmation before the freeze.
Decisions OPEN 1 to 8 were made by the author on 2026-10-25 (section 12). One decision is still open: **OPEN 9** (optional Hindi set).
After the freeze (git tag, done by the author) the hypotheses and scoring rules must not change.

## 1. Research questions

1. **RQ1.** Does an LLM's tool calling change when the same request is written in a different script or style (English, Bangla script, romanized Bangla, mixed, partial)?
2. **RQ2.** If it changes, how does it fail? (Which error types, in which form?)
3. **RQ3.** Does the effect depend on the model family or model size?
4. **RQ4.** Mechanism: what is different inside the model when the request is not English?
5. **RQ5.** Can a simple fix remove the gap?

## 2. Hypotheses [DRAFT]

Written after a 30-item pilot (section 11). They are tested on the 240 new main-set items; the 30 pilot items are excluded (OPEN 2). "Accuracy" means the primary metric (section 8) in the MAIN prompt setting (section 7), headline = lenient format.

- **H1 (confirmatory).** `bn_native` accuracy is lower than `en` accuracy for every model.
- **H2 (confirmatory).** `bn_roman` accuracy is lower than `en` accuracy. The drop is expected to be smaller than the `bn_native` drop of H1, and to depend on the prompt (it changes between the MAIN and ROBUSTNESS prompt settings).
- **H3.** `bn_partial` accuracy is close to `en` (within 10 percentage points). `bn_mixed` lies between `bn_partial` and `bn_roman`.
- **H4.** In `bn_native` the most frequent error is `wrong_lang_arg`. In `bn_roman` the most frequent errors are `no_call` and `wrong_value`.
- **H5.** Going from Qwen3-1.7B to Qwen3-4B does not close the `bn_native` gap.
- **H6a (mechanism, confirmatory).** For `bn_roman` rows labeled `no_call`, on the 101 `multiple` items (several candidate tools), the correct tool is linearly readable from the hidden state at the frozen layer and token position (section 3), above chance. Chance = 1 / number of candidate tools for that item.
- **H6b (mechanism, exploratory).** A readout trained on `en` rows only, applied to `bn_native` and `bn_roman` rows: report the transfer accuracy for each form.

Steering (adding a direction at inference) and all E4 fixes are **exploratory**, not confirmatory. All results are reported.

## 3. Experiments

| id | what | model format |
|---|---|---|
| E1 | Behavior: accuracy per model x form | any |
| E2 | Error taxonomy: error category per model x form | any |
| E3 | Mechanism: linear readout of the tool from hidden states (H6a, H6b); tool vectors, cosine gap and steering (exploratory) | HF transformers, safetensors, fp16, no quantization |
| E4 | Fixes (exploratory) | any |

**E3 protocol.** Model: Qwen3-1.7B (laptop). Token position: the last prompt token before generation. Layer: chosen using only the English rows of the 30 pilot items (the layer with the best tool readout), then frozen before any main-set E3 run (OPEN 8). **[DRAFT]** Readout = a linear classifier (logistic regression) on the hidden state, evaluated with cross-validation across items; the exact setup is written down before the E3 freeze. What is read out: which of the item's candidate tools is the correct one. Each `simple_python` item offers one candidate tool, so H6a uses only the 101 `multiple` items. **[DRAFT]** For H6a the readout is trained on `en` rows of the other `multiple` items (the tested item is never in training). For H6b it is trained on `en` rows only and applied to `bn_native` and `bn_roman` rows. For the layer choice on the pilot items, "tool readout" means how well the item's tool can be told apart from the other pilot items' tools.

## 4. Data

- **Source.** BFCL v4 (Gorilla repo, Apache-2.0): `simple_python` (one candidate tool) and `multiple` (several candidate tools, one correct). Raw copies in `data/raw/bfcl/`, never edited.
- **Pilot.** 30 `simple_python` items x 5 forms = 150 rows, `data/pilot/pilot_items.csv` (long format: item_id, form, query, tools_json, gt_call_json).
- **Main set (OPEN 1, OPEN 2).** 240 new items = **101 `multiple` + 139 `simple_python`**, x 5 forms = 1,200 rows per model and prompt setting. All 30 pilot items are excluded. Draw (`scripts/select_main_items.py`): apply the item rules and the selection rule to the full pool, remove the pilot items, take **all** 101 eligible `multiple` items, and fill up to 240 with `simple_python` items drawn at random with seed 2026. The items are in `data/main/main_items.csv`, in 6 batches of 40 (23 or 24 `simple_python` + 16 or 17 `multiple` each, mixed evenly).
- **Why 101 + 139 (OPEN 1b, closed).** `multiple` has 200 items in total and only 101 pass the rules, because 59 of them have only numbers as arguments (math and physics tools). The original plan of 120 + 120 was therefore not reachable. Counts of items passing each rule (`simple_python` / `multiple`): all 400 / 200; short and clean 374 / 188; has a text value 265 / 129; selection rule 212 / 101; pilot items removed **185** / **101**. Length limit for "short": at most 200 characters and 40 words (the pilot used about 100 characters; `multiple` queries are longer; 200 characters alone would give only 89 `multiple` items). 27 `simple_python` and 9 `multiple` items that pass have a required boolean argument, which cannot be checked against the query and is not shown in "Must keep".
- **Replacement rule.** An item that cannot be written naturally in Bangla is replaced by the next item of the same category in `data/main/eligible_pool.csv`, and the reason is logged in `data/main/replacements.csv`. This is only allowed before any model output on the main set exists. **`multiple` has no spare items** (all 101 are used; 46 spare `simple_python` items remain). A `multiple` item that cannot be written naturally is **dropped, not replaced**, and logged in `data/main/replacements.csv` (with `replaced_by_item_id` left empty and the reason filled in), again before any model output on the main set exists. The main set is then smaller than 240 and the final item counts are reported.
- **Item rules** (same as the pilot): single-turn requests whose gold arguments include a name, place or other text that could change across scripts (cities, people, foods, products). Short, everyday requests. No items with only numbers.
- **Selection rule (OPEN 6).** Drop items whose gold value needs a format or a word that is not present in the English query (like pilot item 196: the date `08-16-2022` for the query "2022/08/16"). Optional arguments marked `""` in the gold answer are fine.
- **Optional Hindi replication set (OPEN 9, undecided).** About 80 items; native Hindi from BFCL-Hi, romanized and mixed forms written by a Hindi speaker. Decide before the freeze.

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
2. Numbers follow the English query. If English writes digits, all forms use English digits 0-9. If English writes a word ("three"), the forms use the word: a Bangla word in `bn_native` and `bn_partial`, a romanized word in `bn_roman`, an English word in `bn_mixed`. The no-extra-answer rule below overrides everything.
3. Do not fix spelling to look perfect. Natural typing is the point.
4. An awkward item is written the way a Bangla speaker would write it, with a note.

**No-extra-answer rule.** No form may contain more of the answer than the English query does. A value may only appear in the form and wording the English query uses, never in the format the tool wants. Examples of what this forbids: writing a number as a digit when English writes the word ("three"); capitalized answer values when English is lowercase; a date in the tool's format when English writes it another way; an answer word that is not in the English query ("Carbohydrates" for "carbs").

**How the forms are made (OPEN 3).**
- **Gemini draft.** Gemini drafts all four forms with one fixed prompt, saved in the repo (`data/prompts/gemini_native_prompt.txt`: the author's pilot prompt, updated with the number rule and the no-extra-answer rule). The author saves Gemini's table as `data/main/sheets/gemini_output_batch_XX.tsv` and runs `scripts/import_gemini.py`, which fills the four green columns of `batch_XX.xlsx` by `item_id`, sets the note to "gemini draft; author check pending", never overwrites a cell that already has text (unless `--overwrite`), and reports missing, extra and duplicated item_ids and empty cells. It also runs a leak check and flags, for the author to look at, any form that carries more of the answer than the English query: a number the English does not have (a digit where English writes a word, a date in another format, Bangla digits), English digits that were not kept, a Latin-letter "Must keep" value with other capital letters, a `bn_partial` that does not copy a value exactly, or a gold spelling that is not in the English query (e.g. "NYC" for "New York City"). The use of Gemini is stated in the paper. "Must keep" in the sheets shows every value exactly as the English query writes it ("sushi", "three", "12,000"), so that the list itself never invites a change of capitals, number type or punctuation.
- **Author edit.** The author checks and edits every form: `bn_native`, `bn_roman` and `bn_mixed`.
- **`bn_partial`** is rebuilt from the author's edited `bn_native`, with the "Must keep" values put in English.
- Second-speaker check: a second native Bangla speaker checks a random sample of 50 items (fixed seed) for same meaning and naturalness. **[DRAFT]** For each of the 4 Bangla forms, with agreement reported as percent agreement and Cohen's kappa, and disagreements listed.
- The pilot: `bn_native` was drafted by Gemini and edited by the author; the other three forms were reviewed by the author. Every pilot item has the note "author checked".

## 6. Models

| model | where | role |
|---|---|---|
| Qwen/Qwen3-1.7B | laptop (RTX 4060) or Kaggle | main; size comparison with Qwen3-4B (H5); the E3 model |
| Qwen/Qwen3-4B | Kaggle 2x T4 | main |
| google/gemma-3-4b-it | Kaggle 2x T4 | main |
| meta-llama/Llama-3.1-8B-Instruct | Kaggle 2x T4 | main |

Qwen3-1.7B is in the main tables (OPEN 4). Four models in total.

## 7. Prompt and decoding

- Greedy decoding (`do_sample=False`), `max_new_tokens=256`, seed 0, batch size 1, one user turn.
- Qwen3: thinking off (`enable_thinking=False`).
- dtype fp16 for all models except Gemma-3-4B-it, which runs in float32 (OPEN 7): fp16 produced `<pad>` garbage on the T4, and the T4 has no bf16 support. The precision is the same for all 5 forms within a model, so comparisons between forms within a model are not affected. Comparisons between models mix precisions, and the paper says so.
- Every run saves: model name and revision, prompt template (and the full chat template), decoding settings, dtype, GPU names, library versions, git commit hash, SHA-256 of the items file, and the full prompt and raw output of every row.
- **Tool mode** (saved in the metadata as `tool_mode`):
  - `native`: the model's own chat template with the tool schema. Qwen3 and Llama-3.1 support this. Gemma 3's template has no tool support, so it cannot be run this way.
  - `prompt_injected`: the tool schema in one fixed system message ("You have access to the following functions: ... respond with only a JSON object {"name": ..., "arguments": {...}} and nothing else"), identical for every model.
- **MAIN setting** = each model's recommended interface: `native` for Qwen3-1.7B, Qwen3-4B and Llama-3.1-8B; `prompt_injected` for Gemma-3-4B (it has no native tool template). H1 to H6b are tested in the MAIN setting.
- **ROBUSTNESS setting** = `prompt_injected` for all four models, the one prompt they share. Every result table is also given for this setting. For Gemma the two settings are the same run.

## 8. Scoring

Each output gets exactly one label. Two independent switches give four numbers per output.

**Value typing**
- **PRIMARY: types normalized.** A string-encoded value is converted before comparing: `"7"` -> 7, `"true"` -> true, `'["a","b"]'` -> list, `"['a','b']"` -> list. The value is accepted if it matches either as written or after conversion.
- **SECONDARY: BFCL typing.** The value must have the right type as written (`"7"` is not 7).
- Reason: Llama 3.1 writes every value as a string, which made its English accuracy look like 40%.

**Output format**
- **Strict.** The whole output must be only one call: `<tool_call>{...}</tool_call>`, a code-fenced JSON block, or bare JSON. Anything else around the call is `format_break`.
- **Lenient.** The first JSON call found anywhere in the text is scored.
- **Headline = lenient format** (OPEN 5). Strict is always reported next to it, and `format_break` gets its own table (per model x form x prompt setting).

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

**Manual error code (not part of the automatic scorer).** For `wrong_value` rows in `bn_roman` and `bn_mixed`, the author codes by hand whether the row is **`span_as_value`**: a Bangla word or phrase used as an argument value. Pilot examples: "Garite Kore" as a start location, "agami mashe" as an artist, "bananor" glued onto a dish name. A second coder codes a sample of these rows; **[DRAFT]** agreement is reported as percent agreement and Cohen's kappa, and the sample size is fixed before coding. The `BANGLA-WORD?` hint printed by `scripts/list_errors.py` is only a reading aid and is not the code.

## 9. Planned statistics [DRAFT]

- **Unit.** The item. Rows of the same item in different forms are paired. Results are given pooled over the 240 items and also separately for the `simple_python` and `multiple` parts.
- **H1, H2.** For each model, exact McNemar test (two-sided) of `en` against `bn_native` (H1) and against `bn_roman` (H2). Report accuracy per form, the two discordant counts b and c, their sum, and the p-value. H1 counts as supported only if all four models show `bn_native` < `en` after Holm correction. H2 prompt dependence: McNemar test of `bn_roman` correctness between the MAIN and ROBUSTNESS settings, per model (not possible for Gemma). H2 size: `bn_roman` drop compared with the `bn_native` drop (McNemar test between the two forms).
- **H3.** Accuracy difference `bn_partial` minus `en` with a 95% paired bootstrap interval; supported if the difference is within 10 percentage points. `bn_mixed` between: the point estimates satisfy `bn_roman` <= `bn_mixed` <= `bn_partial`.
- **H4.** Count of error categories per form and model; H4 is supported if `wrong_lang_arg` is the most frequent error in `bn_native`, and `no_call` and `wrong_value` are the two most frequent in `bn_roman`. Exact test of the category distribution across forms is reported as support.
- **H5.** Native gap (`en` minus `bn_native`) for Qwen3-1.7B and Qwen3-4B with a paired bootstrap interval for the difference of the two gaps, and the model x form interaction in a GEE logistic model (item as cluster, exchangeable, statsmodels). Supported if the 4B native gap is still significant (H1) and is not smaller than the 1.7B gap by more than 10 points (**[DRAFT]** threshold, chosen to match H3).
- **H6a.** On `bn_roman` rows labeled `no_call` among the 101 `multiple` items: readout accuracy at the frozen layer vs chance (1 / number of candidate tools for that item, averaged over the rows), with a bootstrap interval over items. **[DRAFT]** Supported if the interval for readout accuracy minus chance excludes 0. If fewer than 20 such rows exist for a model, the result is reported descriptively only.
- **H6b (exploratory).** Transfer accuracy of an `en`-trained readout on `bn_native` rows and on `bn_roman` rows, reported for each form (all rows of the form, and by outcome label).
- **Exploratory.** Cosine gap between hidden states of a non-English row and its English row, and its relation to failure; steering (accuracy before vs after, McNemar); E4 fixes. Layer and position are fixed before looking at main-set accuracy (OPEN 8).
- **Effect size.** Accuracy difference vs `en` with a 95% paired bootstrap interval (resampling items, 10,000 resamples, fixed seed).
- **Multiple tests.** Holm correction over all model x form comparisons in the main table. Raw p-values are shown as well.
- **Both metrics, both settings.** Every test is run under the primary and the secondary scoring metric, in the MAIN and ROBUSTNESS settings, and all are reported.
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

*Gemma used the `prompt_injected` prompt; the others used `native`. This is the MAIN setting of section 7.

Same pilot data with the `prompt_injected` prompt for Qwen3-4B and Llama (the ROBUSTNESS setting; Gemma is the same run as above; `results/pilot/injected/`):

| form | Qwen3-4B native | Qwen3-4B injected | Llama-8B native | Llama-8B injected | Gemma-4B injected |
|---|---|---|---|---|---|
| en | 28 | 28 | 28 | 27 | 28 |
| bn_native | 4 | 1 | 11 | 2 | 19 |
| bn_roman | 13 | 20 | 21 | 12 | 19 |
| bn_mixed | 26 | 28 | 23 | 22 | 25 |
| bn_partial | 30 | 28 | 25 | 17 | 28 |

What the injected run showed:
- The prompt changes the size of the script effect but does not remove it: `bn_native` stays far below `en` in every model and mode.
- Llama degenerates under the injected prompt: 43 of 150 rows have no JSON call (refusals, or rambling in Bangla or Georgian script), and 27 rows hit the 256-token limit.
- Qwen3-4B `bn_roman` rises from 13 to 20 with the injected prompt, while its `bn_native` falls from 4 to 1. This is why H2 is expected to be prompt-sensitive.
- Gemma is still the most robust on `bn_native` with the shared prompt (19 vs 1 and 2), but not on `bn_roman` (19, against 20 for Qwen3-4B).
- Under the primary metric, McNemar tests of en vs `bn_native` and en vs `bn_roman` are significant (unadjusted p < 0.05) in every model-mode pair. Under BFCL typing, Llama with the native prompt is not (p=0.06 for `bn_native`, p=1.0 for `bn_roman`), because its string-encoded values fail even in English. Pilot p-values are descriptive (30 items, no correction); see `scripts/compare_models.py`.

What we changed:

1. **Writing sheet: 9 rows fixed** during the author's review: 8 answer-format leaks (digit instead of the English word, capitalized answer values, dates in the tool's format, an answer word not in the English query) and 1 translation error (item 357: নিরামিষ "vegetarian" changed to ভেগান "vegan"). This created the no-extra-answer rule (section 5).
2. **`roman_leak` rule tightened.** The first version used a similarity ratio and labeled Aminé (for Eminem) and a date format as `roman_leak`. It now uses the edit-distance rule, and only for strings with Latin letters (section 8).
3. **Scorer made model-aware before the Kaggle scores were seen.** Llama's `<|python_tag|>` / `<|eom_id|>` tokens and `parameters` key are accepted; the strict format accepts bare JSON and code fences.
4. **Primary metric changed to normalized types.** Under BFCL typing Llama scored 12/30 in English because it writes every value as a string. Normalization is now primary, BFCL typing secondary. While reading the `bn_roman` errors we found Llama also writes lists as Python-style strings (`"['a','b']"`); the converter was extended for this, for all models and forms.
5. **Prompt fairness.** Gemma 3's chat template has no tool support, so Gemma was given the tools in a system message while the others used their own templates. The notebook got a `TOOL_MODE` setting and the same-prompt run was done. Result: the main study has a MAIN setting (each model's recommended interface) and a ROBUSTNESS setting (`prompt_injected` for all), and both are reported (section 7).
6. **Gemma dtype** set to float32 on Kaggle because fp16 gave `<pad>` garbage on the T4 (OPEN 7).
7. **Notebook fixes:** recursive input-file search on Kaggle; model revision read from the cache path (newer `transformers` no longer exposes it); model cache kept outside the output folder.
8. **Truncation check.** No Kaggle model hit the 256-token limit; Qwen3-1.7B hit it in 3 rows (item 286 `bn_roman`, item 215 `bn_native` and `bn_partial`).
9. **Shared GPU.** A first run was slow because another job was using the GPU, so the GPU is checked before every run.
10. **Hand check of `bn_roman` wrong values** (`results/pilot/bn_roman_wrong_value.md`): some errors are not caused by the script (optional arguments filled in, a date in another format, a count of tickets), and a few are Bangla words read as names ("Garite Kore", "agami mashe", "bananor").

## 12. Decisions and open points

Decided by the author on 2026-10-25 (to be frozen with the plan):

1. **OPEN 1.** Main set = 240 new items: 101 from BFCL v4 `multiple` (all that pass the rules) + 139 from BFCL v4 `simple_python`, same item rules as the pilot except a longer length limit (section 4). Changed on 2026-10-25 from 120 + 120, which was not reachable (OPEN 1b, closed).
2. **OPEN 2.** All 30 pilot items are excluded from the main set.
3. **OPEN 3.** How the forms are made and checked (section 5): Gemini drafts all four forms with a saved prompt, the author edits every form, `bn_partial` is rebuilt from the edited `bn_native`, and a second native Bangla speaker checks a random 50 items. A `simple_python` item that cannot be written naturally is replaced by the next spare item; a `multiple` item is dropped; both are logged in `replacements.csv` (section 4).
4. **OPEN 4.** Qwen3-1.7B is in the main tables.
5. **OPEN 5.** Headline = lenient format; strict always reported; `format_break` has its own table.
6. **OPEN 6.** Selection rule: drop items whose gold value needs a format or word not in the English query; optional `""` arguments are fine.
7. **OPEN 7.** Gemma runs in float32 (fp16 gave `<pad>` garbage on the T4, which has no bf16); precision is constant across forms within a model.
8. **OPEN 8.** E3 layer and token position are chosen on the English rows of the 30 pilot items only (best tool readout), then frozen before any main-set E3 run. Token position = the last prompt token before generation. Steering strength is not fixed here because steering is exploratory.

Still open:

9. **OPEN 9.** Optional Hindi replication set (about 80 items; native Hindi from BFCL-Hi, romanized and mixed forms by a Hindi speaker). Decide before the freeze.

Done: Gemini prompt saved (`data/prompts/gemini_native_prompt.txt`); sampling seed fixed (2026); main set selected (`scripts/select_main_items.py` -> `data/main/main_items.csv`, `eligible_pool.csv`); 6 writing sheets and 6 Gemini input files built (`scripts/make_writing_sheets.py` -> `data/main/sheets/`); Gemini import with leak check (`scripts/import_gemini.py`, tested on synthetic tables); merge script for the batches (`scripts/merge_main_batches.py`, tested on empty and on synthetic filled sheets); replacement log created (`data/main/replacements.csv`).

Things to do before the freeze (not decisions): have the author write and check the Bangla forms (6 batches) and merge them; second-speaker check; write the E3 readout setup; fix the sample sizes and agreement measures for the second-speaker check and the second coder of `span_as_value`; **(OPEN 7)** run Gemma-3-4B in fp16 on 10 `en` rows in the main Kaggle run and save the outputs as evidence for the float32 decision.
