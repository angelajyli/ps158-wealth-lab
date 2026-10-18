---
name: data-to-figure
description: Turn a research question into a validated, reproducible figure from official survey or statistical data - find and verify the source, download it with a script, build processed data, check it against the source's own published tables, add margins of error, compare with an independent source, and produce a clearly labeled chart. Use when asked to answer a data question with a chart, build a get_data/process/plot pipeline, or validate a published number.
---

# Data to figure

A workflow for going from a research question to a figure you can defend.
Accuracy, reproducibility, and transparent method come before speed.

## Phase 1: discover, download, report, then STOP

1. **Find the official source.** Prefer the agency's own site. Never invent
   datasets, variable names, or URLs. Each claim must be traceable to a page
   or file you actually read.
2. **Verify every variable in every year.** Download the codebooks and search
   them (use Python with `encoding="latin-1"`; old codebooks defeat `grep`).
   Build a year × variable presence table.
   - Don't assume a variable exists in every year: it may first appear partway through the series.
   - Distinguish similar-looking measures. For example, a respondent's own education is not their parents' education.
3. **Decide microdata vs. published tables.** If the published tables don't
   cross the dimensions you need, you need microdata.
4. **Write `get_data.py`.**
   - Download raw files to `data/raw/` unmodified.
   - Integrity-check them (zip CRC; reject HTML error pages saved as data).
   - Keep intact existing files. Move corrupt ones aside instead of overwriting them.
   - Record each file's URL, size and SHA-256 in `MANIFEST.csv`.
   - Confirm the required variables are present.
   - Use script-relative paths.
5. **Report and wait for approval.** Cover:
   - sources and URLs;
   - years available;
   - files downloaded and where they are stored;
   - which variables measure what;
   - whether the question can be answered consistently across years;
   - decisions that need the user's input.

   Do not clean, analyze or plot yet. Do not silently change the research
   question when data is missing: say so and propose alternatives.

## Phase 2: process, validate, quantify uncertainty

1. **Process** into `data/processed/`. Use the source's own definitions
   wherever possible (for example the agency's derived variables). Write down
   any grouping rule and why it is used.
2. **Use survey design correctly.** Apply the weights. Combine multiple
   imputations the way the agency does. Use the agency's own price base and
   inflation index rather than re-deflating.
3. **Validate against the source's published tables.**
   - Reproduce published statistics (overall and by key groups, every year) and fail loudly if they diverge.
   - When the exact cell isn't published, validate the method on cells that are, then apply the same code to the subset.
4. **Margins of error.**
   - Port the agency's own standard-error method (for example replicate weights plus imputation variance).
   - Check the port against any standard errors the agency publishes before trusting it.
   - Report standard errors and 95% intervals for headline numbers, gaps and ratios.
5. **Independent comparison.** Find at least one other source.
   - Rebuild your estimate on *that* source's definitions to compare like with like.
   - Say where they agree, where they don't, and why (sample design, unit, education or children definitions, year and dollars).

## Phase 3: figure and claims audit

1. **Plot** (load the `dataviz` skill first).
   - The title states the finding.
   - The subtitle gives the measure, sample and units.
   - Label the first and last values directly.
   - The footnote gives source, price base, sample, group definitions, what's excluded, missing years, whether standard errors are shown, and "descriptive, not causal".
2. **Look at the rendered image.** Fix clipped subtitles, labels colliding with the axis, and overflowing notes.
3. **Audit every printed number** against the processed data with a script, not by eye.
4. **Audit every word.** Common failures:
   - an ambiguous "parents" (whose?);
   - "went to college" when the group is bachelor's or higher;
   - "head" when the data's "reference person" is assigned by a rule;
   - implied causation;
   - year-to-year changes presented without their margins of error.
5. **Median vs mean.** If asked for both, show both and explain the gap using the skew within each group (mean/median ratio, top-decile share).

## Habits that caught real bugs

- Integer ID columns from Stata can overflow in arithmetic: cast to int64 and assert the expected values.
- Official spreadsheets can have labels shifted by one row: match values, not labels.
- Duplicate row labels exist (for example "Total" appearing twice): take the intended block, not "the" match.
- An "obvious" number (for example a standard error twice as big as expected) means a bug until proven otherwise.

## Communicating

- Answer the question first, then the method.
- Name the files and the year's dollars.
- When the user's instruction conflicts with what the data supports, say so plainly and offer options with a recommendation.
- Record approved decisions in the project's CLAUDE.md.
