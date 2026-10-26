# Spec: bib_for_ams.py

## 1. Purpose

AGU requires full journal names in references; AMS requires abbreviated ones.
The master bibliography (`~/tex/bib/all.bib`) holds full names only. This
script writes an AMS copy (`all_ams.bib`) in which only the `journal` field
values are replaced by their AMS abbreviations, so there is a single master
to maintain and the AMS copy is always regenerated, never edited.

## 2. Inputs

- `bib` (positional): master `.bib` with full journal names.
- `journals` (positional): CSV with header `full,ams`. Must list **every**
  journal name in the master; names that are not abbreviated map to
  themselves, so a missing row always means "not yet decided", never
  "intentionally unchanged".
- `-o/--output` (required): output `.bib`.
- `--strict`: if any journal is unmapped, exit 1 and write nothing.

## 3. Outputs

- The output `.bib`: a 2-line "GENERATED ... do not edit" note (no `@`, so
  BibTeX ignores it) followed by the master text with journal values
  replaced. Everything outside journal values is byte-identical.
- stdout: count of fields abbreviated.
- stderr: each unmapped journal name (and any bare `@string` macro used as a
  journal value) with its occurrence count.

## 4. Algorithm

1. Read the CSV into `{normalize(full): normalize(ams)}`; conflicting rows
   for the same full name raise `ValueError`.
2. Scan for `journal = ` at line start (case-insensitive). The value is
   brace-delimited (brace-balanced, may span lines), quote-delimited, or a
   bare macro name.
3. Look up `normalize(value)` (whitespace collapsed), falling back to a
   case-insensitive match. Matched values are rewritten with the original
   delimiter as a single-line value; unmapped values and bare macros are left
   unchanged and reported.

## 5. Edge Cases & Error Handling

- Bare `@string` macros are not expanded (the master has no `@string`
  definitions since the 2026-10-26 cleanup); they are reported as unmapped.
- Multi-line journal values become single-line in the output.
- Without `--strict`, unmapped names pass through with their full name.

## 6. Usage

`~/tex/bib/Makefile`: `make` (or `make bib_for_ams`) in `~/tex/bib` rebuilds
`all_ams.bib` when `all.bib`, `journals.csv`, or the script changes.

## 7. Open items

- **AMS abbreviations not verified.** `journals.csv` was written from memory
  of AMS conventions (Meteor., Wea., "Climate" unabbreviated: `Climate Dyn.`,
  `Nat. Climate Change`), not checked against AMS's published list. Decide
  whether to verify the ~40 journals actually cited in AMS papers or fix
  rows as copyeditors flag them.
- **Unsplit series in `all.bib`.** `Journal of Geophysical Research` (no
  Atmospheres/Oceans section) and `Tellus` vs `Tellus A` were not resolved
  per entry in the 2026-10-26 cleanup; needs per-paper lookup.
- **Non-journal `journal` values** (`submitted, J. Climate`, a conference
  name, NYT, NOAA NCEI, Interscience, National Climate Centre) are mapped to
  themselves; decide whether these entries should change entry type
  (`@misc`/`@inproceedings`) in `all.bib`.

## 8. Synchronization Log

| Date | Change | Spec updated |
|------|--------|-------------|
| 2026-10-26 | Initial implementation: CSV-driven journal abbreviation, whitespace/case-insensitive match, unmapped report, `--strict`; Makefile in `~/tex/bib`. Preceded by a one-time cleanup of `all.bib` to full names (860 fields; backup `all.bib.bak-20261026-pre-journal-cleanup`, log `journal-cleanup-20261026.log`) | Yes |
