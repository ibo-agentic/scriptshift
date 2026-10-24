# Pilot data

- `pilot_items.csv` — 30 BFCL v4 `simple_python` items x 5 forms (long format: item_id, form, query, tools_json, gt_call_json).
  Source: Berkeley Function Calling Leaderboard (Gorilla repo, Apache-2.0), raw copy in `data/raw/bfcl/`.
- `bangla_writing_sheet.xlsx` — the Bangla queries ("Write here" sheet), merged into the CSV by `scripts/merge_bangla.py`.

## How the Bangla forms were made

- `bn_native`: first drafted by Gemini, then reviewed and edited by the author.
- `bn_roman`, `bn_mixed`, `bn_partial`: reviewed by the author.
- All 30 items were checked by the author (notes column says "author checked").
- 9 rows were fixed during review: 8 for answer-format leaks (e.g. a digit written as a word in English but as a digit
  in the draft, capitalised answer values, a date written in the answer format) and 1 for a translation error
  (simple_python_357: নিরামিষ "vegetarian" changed to ভেগান "vegan"). The fix is described in each row's note.

## Forms

| form | meaning |
|---|---|
| en | original BFCL English query |
| bn_native | all Bangla script, names too |
| bn_roman | Bangla in English letters (phone typing) |
| bn_mixed | natural Banglish |
| bn_partial | Bangla script, values kept in English |
