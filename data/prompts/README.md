# Prompts

- `gemini_native_prompt.txt` — the prompt pasted into Gemini to draft the Bangla forms of each main-set item
  (followed by the items of one batch, 40 per batch, see `scripts/make_writing_sheets.py`). The author edits the
  draft afterwards.

## Status

Author's pilot prompt, updated with the number rule and no-extra-answer rule.
(The text above the line `ITEMS` is the author's text, pasted in unchanged on 2026-10-25. An earlier draft of this
file, written by Claude Code from the writing rules because the pilot prompt was not in the repo, was replaced.)

The prompt asks for all four forms (bn_native, bn_roman, bn_mixed, bn_partial) as a tab-separated table.
`scripts/make_writing_sheets.py` appends the items of a batch after the line `ITEMS` and writes the result to
`data/main/sheets/gemini_input_batch_XX.txt`; change this file and run that script again to rebuild them.
