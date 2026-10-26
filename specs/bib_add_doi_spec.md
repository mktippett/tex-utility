# Spec: bib_add_doi.py

## 1. Purpose

Fill in missing `doi` fields for `@article` entries in the master `.bib`
(`~/tex/bib/all.bib`) by deterministic lookup against the Crossref REST API,
with a review step between lookup and edit. A language model is deliberately
not used to supply DOIs: a plausible-looking wrong DOI is worse than none.

## 2. Inputs

- `find BIB --outdir DIR --mailto EMAIL [--delay S]`: the `.bib` (read
  only); output directory; email for Crossref's polite pool (sent as
  `mailto=` and in the User-Agent); pause between uncached requests
  (default 0.2 s).
- `apply BIB TSV`: the `.bib` to edit; a TSV with at least `key` and `doi`
  columns (normally the reviewed `doi_accept.tsv`).

## 3. Outputs

`find` (never touches the `.bib`):
- `DIR/crossref_cache.jsonl`: one line `{key, items}` per queried entry,
  appended and flushed as each answer arrives, so an interrupted run resumes
  and reruns cost no requests for cached keys.
- `DIR/doi_accept.tsv`, `DIR/doi_review.tsv`: columns `key, status, reason,
  score, doi, cr_title, cr_journal, cr_year, bib_title, bib_journal,
  bib_year, journal_differs`. Both are **rewritten** on every `find`, so
  hand edits are lost if `find` is rerun.

`apply`:
- Dated backup `BIB.bak-YYYYMMDD-pre-doi[-N]` (only if something is applied),
  then `  doi = {...},` inserted on the line after each entry's `@type{key,`.

## 4. Algorithm

`find`:
1. Select `@article` entries with a `title` and no `doi` field.
2. Plain-text the title, first-author surname, year and journal (`detex`:
   LaTeX accents → Unicode, math/commands/braces dropped).
3. Query `GET /works` with `query.bibliographic=title`,
   `query.author=surname`, `rows=5`; retry with backoff on non-200.
4. Among returned items (skipping any in Crossref's "Deleted DOIs"
   container), pick the best title by `SequenceMatcher` ratio on folded
   (lowercase ASCII alphanumeric) strings.
5. Accept only if all hold: title ratio ≥ `TITLE_MIN` = 0.95; some
   Crossref year (issued / published-print / published-online) within ±1 of
   the bib year; folded first-author family name equals the bib surname.
   Otherwise `review` with the failing checks in `reason`.
6. A DOI proposed for more than one key demotes those rows to `review`
   (`doi shared with ...`): either duplicate entries or a wrong match.
7. `journal_differs=yes` flags rows where Crossref's container title differs
   from the bib journal (informational; does not change status).

`apply`: skip keys not in the `.bib`, entries that already have a `doi`, and
DOIs already present on another entry (case-insensitive). Rerunning on the
same TSV is a no-op.

## 5. Edge Cases & Error Handling

- DOIs are written in Crossref's returned case; comparisons are
  case-insensitive.
- Known false-accept patterns caught only by review of `journal_differs`:
  conference version vs journal version of the same title, and entries
  whose bib journal is wrong (Crossref is then right).
- Known review-only patterns that are usually correct: archive journals that
  registered DOIs years later (E-Journal of Severe Storms Meteorology),
  surname written differently (`van den Dool`), small title wording
  differences.
- Known review-only patterns that are wrong: preprints (Research Square,
  NBER, SSRN), book reprints/chapters of journal papers, EGU abstracts.

## 6. Usage

`~/tex/bib/Makefile`: `make doi-candidates` (find → `~/tex/bib/doi/`),
`make doi-apply` (apply `doi/doi_accept.tsv`).

## 7. Open items

- **OpenAlex fallback not in the script.** An ad hoc OpenAlex
  (`api.openalex.org/works?search=title`) + DataCite pass over the 59
  Crossref leftovers found 19 correct DOIs Crossref had mismatched
  (Uppala05, Saha2006, Knutson2010, Kaplan1998, ...), plus 2 via corrected
  Crossref titles (Kalnay96 title typo; Zebiak1987, whose Crossref title has
  a garbled "Niño"). Decide whether to add OpenAlex as a `find` fallback for
  rows that fail the Crossref checks, using the same title/year/author tests.
- **~38 entries still without a DOI** (rows in
  `~/tex/bib/doi/doi_review.tsv` not since applied): mostly reports,
  conference preprints, IMD memoirs, web/newspaper, and the 1997–99
  non-normality manuscripts. Notables: Camargo2007 (WMO Bulletin) has only
  a Columbia repository DataCite DOI `10.7916/hthk-d786` (not added — decide
  if repository DOIs are acceptable); PChang2007's bib title "A
  Thermodynamic Trigger…" may be wrong (OpenAlex's Chang et al. 2007 GRL is
  "Pacific meridional mode and El Niño–Southern Oscillation"); Liebmann1996
  (BAMS) appears to have no registered DOI.
- **Duplicate entries in `all.bib`** (~23 pairs, e.g. `Toth97`/`Toth1997`,
  `Dee98a`/`Dee99a`, `Kleeman2001`/`Kleeman2002`, `Black94`/`Black1994`);
  only one key of each pair has the DOI. Decide whether to merge (older
  papers may cite either key) or give both keys the DOI (needs an `apply`
  option to bypass the uniqueness check).
- **Suspect entries:** `DELee2014` vs `LeeENSO:2016` share DOI
  `10.1007/s00382-015-2825-5` but differ in year; `Todling96` has year 1996
  but its DOI is Part I (1994); `Kleeman2004` ("geostrophic turbulence",
  2004) may be the same paper as `Kleeman2005`.

## 8. Synchronization Log

| Date | Change | Spec updated |
|------|--------|-------------|
| 2026-10-26 | Initial implementation: Crossref find (cached, resumable; title ≥ 0.95, year ±1, first-author checks; shared-DOI demotion; Deleted-DOIs skip) and apply (dated backup, skip existing/duplicate DOIs). First run on all.bib: 771 candidates → 632 + 59 DOIs applied after manual triage; 7 wrong journal fields and Majda2003 volume corrected from Crossref; Glahn1968 wrong DOI fixed | Yes |
| 2026-10-26 | No code change. Ad hoc OpenAlex/DataCite second pass on Crossref leftovers: 21 more DOIs applied; Kalnay96 title typo and Liu97 author (→ Lui) corrected in all.bib; open items updated | Yes |
