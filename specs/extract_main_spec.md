# Spec: extract_main.py

## 1. Purpose

Extract a main-text-only manuscript from a combined main+SI `.tex` file, for
the submission/revision step where journals require the main text as its own
file separate from the Supporting Information (SI).

The combined `.tex` (produced by `beamer_to_ams.py` / `beamer_to_agu.py`, or
hand-written) keeps main text and SI in one document so that `\ref{}` in the
main text resolves directly to SI item numbers (e.g. `S1`, `S2`). This script:

- Cuts the document at the SI boundary, **never writing to the input file**.
- Leaves `\ref{}`/`\eqref{}`/`\autoref{}`/`\cref{}`/`\Cref{}` pointing at an SI
  item **unchanged**, and appends a small `\label{}`-reconstruction block
  (built from the combined document's `.aux`) just before `\end{document}`,
  wrapped in `%TC:ignore` since it produces no visible text. LaTeX's normal
  two-pass `\ref` mechanism then resolves these commands to the right `Sn`
  — no dangling references, and no inflation of `texcount`'s word count.
  `\pageref{}` to an SI item *is* replaced with the literal page number from
  the `.aux`, since the SI's own page numbering doesn't exist in `main.tex`.
- Rebases relative `\includegraphics` paths so they resolve from the output
  directory (they resolve against the combined file's own directory, one
  level up from `<stem>_SUBMIT/`); absolute paths are untouched.
- Extracts each `\begin{figure}...\end{figure}` block into its own
  `figN.pdf` (via `make_single_figure.sh`) and rewrites the
  `\includegraphics` path(s) to the bare filename `figN.pdf`, collapsing
  multi-panel figures to the single cropped composite.
- Inlines the compiled `.bbl` in place of `\bibliography{}` and comments out
  `\bibliography{}`/`\bibliographystyle{}`, so `main.tex` compiles with
  `pdflatex` alone (no `bibtex`, no `.bib` database needed on the
  publisher's machine).
- Copies the local `.cls`/`.sty`/`.bst` files `main.tex` loads into the
  output directory, test-compiles `main.tex` there with `TEXINPUTS` unset,
  summarizes the log, and deletes build intermediates (§4.9) — so the
  output directory is the finished submission folder.

---

## 2. Inputs

| File | Notes |
|------|-------|
| `COMBINED.tex` | Combined main+SI document. Read-only. |
| `COMBINED.aux` | `.aux` from compiling `COMBINED.tex`. Default: `<stem>.aux` next to `COMBINED.tex`. Source of SI item numbers (`S1`, `S2`, ...). If absent, SI `\ref{}`s are left unflattened (warning emitted). |
| `COMBINED.bbl` | `.bbl` from running `bibtex` on `COMBINED.tex`. Default: `<stem>.bbl` next to `COMBINED.tex`. Inlined in place of `\bibliography{}`. If absent, `\bibliography{}` is left live (warning emitted). Skipped entirely with `--no-bib`. |

---

## 3. Outputs

All written to `--outdir` (default `<stem>_SUBMIT/`); the input `.tex`/`.aux`
are never written.

| File | Contents |
|------|----------|
| `main.tex` | SI removed; `\ref`/`\eqref`/`\autoref`/`\cref`/`\Cref` to SI items unchanged (resolved via a reconstructed `\label{}` block before `\end{document}`); `\pageref{}` to SI items flattened to a literal page number; figure includes rewritten to `figN.pdf`; `.bbl` inlined as `thebibliography` with `\bibliography{}`/`\bibliographystyle{}` commented out |
| `fig1.pdf`, `fig2.pdf`, ... | One PDF per live figure environment, cropped (via `make_single_figure.sh`) |
| `<class>.cls`, `*.sty`, `*.bst` | Local support files `main.tex` loads, copied from next to the input or from the repo's `ams/`/`agu/` (§4.9.1) |
| `main.pdf` | Result of the test compile (§4.9.2), kept for checking; not part of the submission |
| `main.log` | Kept only when the test compile failed or was unclean |
| `main_figures.*`, `main.aux`/`.out` | Deleted after the run (§4.9.3) unless `--keep-intermediates` |

CLI summary lines report: how the SI boundary was found, how many SI refs were
preserved via the reconstructed `\label{}` block, how many `\pageref{}`s were
flattened, how many figures were generated/rewritten, which support files
were copied, the test-compile result (pages, passes, undefined refs/
citations, overfull `\hbox`es), and which intermediates were removed.
Warnings go to stderr. Exit status is 1 if the test compile fails.

---

## 4. Algorithm

### 4.1 SI boundary detection (`find_si_start`)

Checked in priority order; the first match wins:

1. **Sentinel**: a line containing `%% SI_BEGIN` (emitted by both converters
   at the SI boundary — see `beamer_to_ams_spec.md` §4.5 and
   `beamer_to_agu_spec.md`).
2. **Section marker**: the earliest of `\section*{Supporting Information...}`
   / `\section*{Supporting information...}` / `\section{Supplement...}`
   (covers hand-written/legacy combined files without the sentinel).
3. **Fallback**: `\renewcommand\thefigure{S\arabic{figure}}` (the SI
   figure-numbering redefinition both converters emit).

If none match, the script aborts with an error (suggesting `--no-si`) and
writes nothing.

With `--no-si` (for manuscripts that have no SI — e.g. a no-SI deck converted
by `beamer_to_agu.py`, which emits no `%% SI_BEGIN` in that case), boundary
detection and SI stripping are skipped entirely; the rest of the packaging
(ref flattening — a no-op without S-labels — path rebasing, `.bbl` inlining,
figure extraction) still runs.

### 4.2 SI stripping (`strip_si`)

Truncate the text before the SI boundary, `rstrip()`, and ensure exactly one
trailing `\end{document}` (appended if the truncated text doesn't already end
with one). Because both converters emit the sentinel *after* the
bibliography/`\clearpage` (AMS: appended to the injected `bib_lines` block;
AGU: prepended to `_build_si_header`'s block, itself placed after
`bib_line`), the bibliography is retained in `main.tex`.

Both converters wrap the endmatter+bibliography+SI in a single
`%TC:ignore` ... `%TC:endignore` pair, with the `%% SI_BEGIN` sentinel placed
*inside* this region (after `%TC:ignore`, before `%TC:endignore`). Truncating
at the sentinel therefore removes the `%TC:endignore` that closes this
region, leaving an orphaned `%TC:ignore` that makes `texcount` fail with
`(errors:3)` (`"Reached end of file while waiting for %TC:endignore."`, etc.).
`strip_si` detects this — via `_TC_IGNORE_RE`/`_TC_ENDIGNORE_RE`, counting
ignore/endignore markers in the truncated text — and rebalances by appending
a `%TC:endignore` line immediately before the trailing `\end{document}`.

Before the rebalancing, any run of trailing `\clearpage`/`\cleardoublepage`/
`\newpage` (`_TRAILING_PAGEBREAK_RE`) is stripped from the truncated text.
Because the sentinel follows the bibliography's `\clearpage`, that page break
would otherwise sit directly before the SI label block (§4.5); the block's
`\label` writes would then land on an empty page that LaTeX never outputs, so
every SI `\ref` stays undefined in `main.tex`. The page break only separated
the main text from the SI, so there is no reason to keep it once the SI is
gone.

### 4.3 `.aux` parsing (`parse_aux_labels`)

Line-by-line regex `\newlabel\{(label)\}\{\{(ref)\}\{(page)\}` → `{label:
{'ref': ref, 'page': page}}`. SI labels are those whose `ref` starts with
`"S"` (figure/table counters are reset and redefined to `S\arabic{...}` at
the SI boundary, so any SI item's resolved number begins with `S`).

### 4.4 Ref flattening (`flatten_refs`)

Regex `\\(ref|eqref|pageref|autoref|[Cc]ref)(\*?)\{(label)\}` over the
SI-stripped text. For labels in the SI set (ref text starts with `"S"`):

| Command | Handling |
|---------|----------|
| `\ref{l}`, `\eqref{l}`, `\autoref{l}`, `\cref{l}`, `\Cref{l}` (incl. `*` forms) | **left unchanged** in the text; `l` is recorded in `si_labels_used` for §4.5 to reconstruct |
| `\pageref{l}`, `\pageref*{l}` | replaced with the literal `page` text from the `.aux` |

`\pageref{}` is flattened to a literal because the SI's own page numbering
(`\setcounter{page}{1}` at the SI boundary) doesn't exist in `main.tex` —
there's no page to reconstruct a label onto. (Per project convention,
`\pageref{}` to SI items is rare/unused, so a literal page number is an
acceptable edge case.)

For `\autoref`/`\cref`/`\Cref`, the label is additionally flagged
`needs_noun=True` in `si_labels_used` — see §4.5 for how this affects the
reconstruction.

For any `\ref`-family command whose label is **absent from the `.aux`
entirely** (not just non-SI), a "stale .aux?" warning is emitted once per
label — this also fires for labels referenced only inside commented-out
lines (harmless, but surfaced so the user can confirm).

### 4.5 SI label reconstruction (`build_si_label_block` / `insert_si_label_block`)

For each label in `si_labels_used` (from §4.4), `build_si_label_block`
produces one reconstruction line, all wrapped in a single
`%TC:ignore` ... `%TC:endignore` block (accurate, since the block produces no
visible text):

- **Guessable counter** (label name starts with `fig:`/`figure:`,
  `tab:`/`table:`, or `eq:`/`equation:`, case-insensitive —
  `_guess_counter`/`_LABEL_COUNTER_PREFIXES`): emit
  `{\renewcommand\the<counter>{<ref>}\refstepcounter{<counter>}\label{<label>}}`
  (e.g. `{\renewcommand\thefigure{S1}\refstepcounter{figure}\label{fig:foo}}`).
  `\refstepcounter` sets `\@currentlabel` *and* steps the counter packages
  like `cleveref` key off of, so `\ref`/`\eqref` **and**
  `\autoref`/`\cref`/`\Cref` all resolve correctly (right number *and* right
  noun, e.g. "Figure S1").
- **Unguessable counter**: emit `{\def\@currentlabel{<ref>}\label{<label>}}`.
  This is enough for `\ref{}`/`\eqref{}` to resolve to `<ref>`, but if the
  label was used with `\autoref`/`\cref`/`\Cref` (`needs_noun=True`), a
  warning is emitted — the noun may be missing/wrong and needs a manual fix.

`insert_si_label_block` inserts this block immediately before the trailing
`\end{document}` (after `.bbl` inlining, §4.6). If `si_labels_used` is empty,
`main_text` is returned unchanged and nothing is inserted. The block is its
own `%TC:ignore`/`%TC:endignore` pair, separate from (and after) the one
emitted by `strip_si` (§4.2) around the bibliography/endmatter — sequential,
non-nested ignore regions, which `texcount` handles correctly.

Each `{...}`-wrapped reconstruction line is its own group, so
`\renewcommand`/`\refstepcounter`/`\def\@currentlabel` redefinitions don't
leak between labels (each label gets its own freshly-set counter/value).

Because the reconstruction block is physically *after* every `\ref{}`/
`\eqref{}`/`\Cref{}` usage in `main.tex`, LaTeX's normal two-pass mechanism
applies: the first `pdflatex` pass writes the new `\newlabel{...}` entries to
`main.aux`, and they're available from that pass's `.aux` — verified against
a real manuscript: a single extra `pdflatex` run (i.e. the routine "run
pdflatex twice" already required for any document with cross-references)
resolves all `\ref{}`s to `S1`...`S6` with no `??` and no "Rerun to get
cross-references right" warning on the second pass.

### 4.6 `.bbl` inlining (`inline_bbl`)

Runs by default (after ref flattening, before `main.tex` is written); skipped
entirely with `--no-bib`.

1. Module-level, line-anchored regexes (`re.MULTILINE`) so a leading `%`
   (already-commented line) breaks the `^[ \t]*\` anchor and such lines are
   skipped:
   - `_BIBLIOGRAPHY_RE = re.compile(r'^([ \t]*)(\bibliography\{[^}]*\})', re.M)`
   - `_BIBSTYLE_RE     = re.compile(r'^([ \t]*)(\bibliographystyle\{[^}]*\})', re.M)`
2. If no live `\bibliography{...}` is found, return `'no-bibliography'` and
   leave `main_text` unchanged (warning emitted).
3. Otherwise:
   - Comment out the first live `\bibliographystyle{...}` (if any):
     `\1%\2` (count=1). AMS combined files have one; AGU files don't, so
     this is a no-op for AGU.
   - Replace the first live `\bibliography{...}` (count=1) with its
     commented form followed by the `.bbl` contents (stripped of leading/
     trailing whitespace): `\1%\2\n\n<bbl contents>\n`. Insertion at the
     `\bibliography{}` site preserves the converters' ordering — the
     bibliography already sits before `%% SI_BEGIN`, so it lands in the
     main-only file at the same place a reader would expect references.

`bbl_path` defaults to `<stem>.bbl` next to `COMBINED.tex` (same derivation
as `aux_path`). If `bbl_path` doesn't exist, `\bibliography{}` is left live
and a warning is emitted — same graceful-degradation pattern as a missing
`.aux`.

### 4.6b Graphics path rebasing (`rebase_graphics_paths`)

Runs before `main.tex` is written, whenever `outdir` differs from the
combined file's directory. Every relative `\includegraphics` path is
rewritten via `os.path.relpath(src_dir / path, outdir)` so it resolves from
`outdir` (e.g. `../plots/a.pdf` → `../../plots/a.pdf` for the default
`<stem>_SUBMIT/` layout). Absolute paths are untouched. Without this, both
the `make_single_figure.sh` harness compile (cwd = outdir) and `main.tex`
itself fail to find graphics referenced with the slide convention's
relative paths.

### 4.7 Figure extraction and rewriting

1. `count_figure_envs` / `_live_figure_envs`: find
   `\begin{figure}...\end{figure}` blocks (`re.DOTALL`),
   **skipping any whose `\begin{figure}` is commented out** (`_is_commented`:
   an unescaped `%` earlier on the same line). This matters because AGU
   template boilerplate often leaves commented-out example figure blocks
   (`% \begin{figure} ... % \end{figure}`) in the main body; these produce no
   pages in `make_single_figure.sh`'s harness PDF and must not consume a
   `figN` slot or be miscounted.
2. If `count_figure_envs(main_text) == 0`, skip figure extraction entirely.
3. Otherwise run `make_single_figure.sh main.tex N` (cwd = outdir) →
   `fig1.pdf ... figN.pdf`, one per live figure environment in document
   order. **N (= `count_figure_envs` result) is passed explicitly** so the
   script and Python can never disagree on the count; the script's fallback
   grep and its awk figure filter both skip commented-out `\begin{figure}`
   lines to match `_live_figure_envs`. The harness document uses the plain
   `article` class + `geometry` (1in margins ≈ journal `\textwidth`; no
   journal `.cls` install needed), no-ops `\caption` (optional `[short]`
   arg included), appends `\clearpage` after each figure so page N is
   always figure N, and runs pdflatex with
   `-interaction=nonstopmode -halt-on-error`.
4. `rewrite_figure_includes`: walk the same live figure environments in
   order (1-based `n`). In the `n`-th block, replace the **first**
   `\includegraphics[opts]{...}` with `\includegraphics[opts]{figN.pdf}`
   (bare filename, no directory — so the output compiles in a flat
   submission folder) and **remove** any additional `\includegraphics` in
   that block (multi-panel figures collapse to the single cropped
   composite). Commented-out blocks and all text outside live figure
   environments pass through unchanged.

### 4.8 Safety

- `out_tex.resolve() == combined_tex.resolve()` → abort before writing
  anything (refuses to let `--outdir`/filename collide with the input).
- SHA-256 of the input bytes is checked before and after the run; a mismatch
  aborts with an error (defense in depth — nothing in the algorithm should
  ever write to the input, but this catches it if it ever does). This check
  runs before the compile-failure exit, so it is never skipped.

### 4.9 Submission-folder finishing

Runs after figure extraction, on the final `main.tex`.

#### 4.9.1 Support files (`support_file_names` / `copy_support_files`)

Comments are stripped (`(?<!\\)%.*`), then the names are collected:
`\documentclass[...]{X}` → `X.cls`; each comma-separated name in
`\usepackage`/`\RequirePackage[...]{a,b}` → `a.sty`, `b.sty`; live
`\bibliographystyle{Y}` → `Y.bst`. After `.bbl` inlining the style command
is commented out, so a `.bst` is only picked up with `--no-bib` or when there
was no `.bbl`.

Each name is looked up in order: the input's directory, then the repo's
`ams/`, then `agu/` (`SUPPORT_SEARCH_DIRS`). The first hit is copied into
`outdir` with `shutil.copy2`. Preferring the input's directory means a paper
that carries its own (possibly older) class copy keeps it. Names found
nowhere are assumed to be part of the TeX installation and are skipped
silently, except the class, which prints a note (the test compile settles
whether it really is installed).

#### 4.9.2 Test compile (`compile_main` / `summarize_log`)

Skipped with `--no-compile`. `pdflatex -interaction=nonstopmode
-halt-on-error main.tex` runs in `outdir` with `TEXINPUTS` **removed** from
the environment, so only `outdir` and the TeX installation are searched —
the publisher's situation. A file the folder needs but lacks becomes a
compile error here instead of at the publisher. (`max_print_line=10000` is
set so log lines aren't wrapped before regex scanning.)

Passes: at least 2, then more while the log says `Rerun to get` / `Label(s)
may have changed`, up to `MAX_PASSES = 4`. A third pass is the normal case
for a document with citations: pass 1 prints citations as `?`, pass 2 fills
them in, which moves floats and changes label page numbers, which triggers
"Label(s) may have changed" (seen on the 2026-10-28 real-paper run: 3
passes).

The final pass's log is summarized: page count, undefined references,
undefined citations (with a note when `\bibliography{}` is still live, i.e.
`--no-bib`), whether a rerun is still requested, and the count of `Overfull
\hbox` lines. Undefined refs/citations or a pending rerun are warnings
(exit 0) and mark the compile unclean; overfull boxes are reported only.

A pdflatex failure prints the first three `!` error blocks from the log and
the log path, skips deletion of `main.log`, and makes the script exit 1 after
the input-hash check. `pdflatex` missing from `PATH` aborts with a message
pointing at `--no-compile`.

#### 4.9.3 Cleanup (`prune_intermediates`)

Skipped with `--keep-intermediates`. Deletes only these known names, if
present: `main_figures.tex/.pdf/.log/.aux` (`make_single_figure.sh`'s
harness; its per-figure `main_figures_N.*` files it already removes itself),
`main.aux`, `main.out`, and `main.log` unless the compile was unclean or
failed. `main.pdf` is kept for checking. Files from earlier runs that this
run didn't produce (e.g. a stale `fig11.pdf` after a figure was dropped) are
not touched.

---

## 5. Edge Cases & Error Handling

| Situation | Handling |
|-----------|----------|
| No SI boundary found | Abort, nothing written; error message suggests `--no-si` |
| `--no-si` | Boundary detection and SI stripping skipped; ref flattening (no-op without S-labels), path rebasing, `.bbl` inlining, and figure extraction still run |
| Relative `\includegraphics` paths | Rebased to resolve from `outdir` (§4.6b); absolute paths untouched |
| `.aux` missing | SI refs left as `\ref{...}` (will render `??`, no reconstruction block emitted); warning emitted |
| Label referenced but not in `.aux` | Warning ("stale .aux?"), left unchanged |
| `\ref{}` to a main-text label (ref doesn't start with `S`) | Left unchanged (resolves correctly within `main.tex` itself) |
| `\ref{}`/`\eqref{}`/`\autoref{}`/`\cref{}`/`\Cref{}` to an SI label | Left unchanged; resolved via reconstructed `\label{}` block (§4.5) — needs one extra `pdflatex` pass like any cross-reference |
| `\pageref{}` to an SI label | Flattened to literal page number from `.aux` (no label to reconstruct — SI page numbering doesn't exist in `main.tex`) |
| `\autoref`/`\cref`/`\Cref` to an SI label whose counter can't be guessed from its name (no `fig:`/`tab:`/`eq:` prefix) | `\ref{}`/`\eqref{}` still resolve; noun may be missing/wrong + warning (manual fix) |
| Commented-out `\begin{figure}...\end{figure}` (template boilerplate) | Skipped — not counted, not rewritten, passed through verbatim |
| Multi-panel figure (2+ `\includegraphics` in one `\begin{figure}`) | Collapses to one `\includegraphics{figN.pdf}`; extra includes removed |
| No live figure environments | Figure extraction skipped entirely |
| `--no-figures` | SI strip + ref flattening only; `\includegraphics` paths untouched |
| `--outdir`/output path would collide with input `.tex` | Abort before writing |
| `.bbl` missing | `\bibliography{}`/`\bibliographystyle{}` left live; warning emitted — `main.tex` will need `bibtex` to compile |
| No live `\bibliography{}` in main text | Nothing inlined; warning emitted (`.bbl` contents discarded) |
| `--no-bib` | `.bbl` inlining skipped entirely; `\bibliography{}`/`\bibliographystyle{}` left live |
| Appendix content (added 2026-09-15) | Retained in `main.tex` by construction, no code change — both converters (`beamer_to_ams_spec.md` §4.10, `beamer_to_agu_spec.md` §4.11) always emit the appendix before `%% SI_BEGIN`, so `strip_si` (§4.2) keeps it. `find_si_start`'s three tiers (§4.1) cannot fire on appendix content: the sentinel is exact, the section-title tiers require `Supplement`/`Supporting Information` immediately after the brace, and the literal-`S` `\renewcommand\thefigure{S\arabic{figure}}` fallback can't match AMS's `A`-lettered reset. `flatten_refs` (§4.4) classifies SI labels by `ref.startswith('S')`, so an appendix ref resolving to `A1` is correctly left as a live `\ref{}`, not swept into the SI reconstruction block. `rewrite_figure_includes` (§4.7) maps the Nth live `\begin{figure}` in document order to `figN.pdf` and never reads `\thefigure`, so an appendix counter reset doesn't perturb it. Verified with a regression fixture, not just argued — see §6 |
| Class not next to input nor in `ams/`/`agu/` | Note printed, nothing copied; test compile decides (works if installed system-wide) |
| `.sty` reachable only via the user's `TEXINPUTS` | Not copied, and the test compile fails (exit 1) — intended: the publisher wouldn't have it either. Put the file next to the input to have it copied |
| `\usepackage{...}` commented out | Ignored (comments stripped before scanning) |
| Test compile fails | Error blocks + log path to stderr; `main.log` kept; other intermediates still pruned; exit 1 |
| Undefined refs/citations or rerun still requested after the last pass | Warnings; `main.log` kept; exit 0 |
| `--no-compile` | No `main.pdf`; support files still copied; figure intermediates still pruned |
| `--keep-intermediates` | Nothing deleted |
| Stale files in a reused `--outdir` | Left alone (only known intermediate names are deleted) |
| Appendix figure file naming | `figN.pdf` (sequential, document order), not `figA1.pdf`-style. Recorded limitation, not fixed — journals often want the latter; would require teaching `rewrite_figure_includes` and `make_single_figure.sh` about counter resets, a real change to the positional figure-mapping contract |

---

## 6. Synchronization Log

| Date | Change | Spec updated |
|------|--------|-------------|
| 2026-06-12 | Initial implementation: SI boundary detection (sentinel/section-marker/thefigure fallback), `.aux`-based ref flattening (`\ref`/`\eqref`/`\pageref`; `\autoref`/`\cref`/`\Cref` warn-and-skip), figure extraction via `make_single_figure.sh` with `\includegraphics` rewrite to bare `figN.pdf` and multi-panel collapse, comment-aware figure-env counting | Yes |
| 2026-06-12 | Added `.bbl` inlining (`inline_bbl`): default-on, inlines `<stem>.bbl` as `thebibliography` in place of `\bibliography{}` and comments out `\bibliography{}`/`\bibliographystyle{}`; graceful skip + warning if `.bbl` missing or no live `\bibliography{}`; new `--bbl PATH` / `--no-bib` flags | Yes |
| 2026-06-13 | Changed default `--outdir` suffix from `<stem>_main/` to `<stem>_SUBMIT/` | Yes |
| 2026-06-15 | Fixed orphaned `%TC:ignore` after SI truncation (`strip_si` now rebalances by appending `%TC:endignore` before `\end{document}`) — was causing `texcount (errors:3)` | Yes |
| 2026-06-15 | Replaced literal-number SI ref flattening with `\label{}` reconstruction: `\ref`/`\eqref`/`\autoref`/`\cref`/`\Cref` to SI labels left unchanged, resolved via a `%TC:ignore`-wrapped `\refstepcounter`/`\renewcommand`/`\label{}` block before `\end{document}` (`build_si_label_block`/`insert_si_label_block`), using a `fig:`/`tab:`/`eq:` prefix heuristic to pick the counter; `\pageref{}` to SI labels still flattened to a literal page number. Removes the previously-added `\EMref` wrapper macro/`%TC:macro` directive (rejected as "tricking texcount") | Yes |
| 2026-07-07 | Added `--no-si` (pipeline-gap audit): manuscripts without SI can now use the packaging (previously hard-abort on missing boundary); added `rebase_graphics_paths` so relative `\includegraphics` paths resolve from `outdir` (slide-convention `../plots/...` previously broke the harness compile). Verified end-to-end with a relative-path deck: convert → compile → extract → `main.tex` compiles in `_SUBMIT/`, fig1/fig2 correct with a commented-out figure block present | Yes |
| 2026-07-07 | `make_single_figure.sh` hardened: figure count passed explicitly from `count_figure_envs` (fallback grep and awk filter now skip commented `\begin{figure}` lines — previously a commented block desynchronized the counts); harness switched from V5 `ametsoc` class (machine-specific install) to `article` + `geometry`; `\clearpage` after each figure guarantees page N = figure N; `\caption` no-op accepts `[short]`; pdflatex runs `-interaction=nonstopmode -halt-on-error` | Yes |
| 2026-08-22 | `flatten_refs`'s `repl` treated `\Cref{fig:si1,fig:si2}` (cleveref's comma-joined multi-label syntax) as a single label `'fig:si1,fig:si2'`, which matched neither `si_labels` nor `aux_labels` — the command was left unchanged (correct) but no individual label was ever recorded into `si_labels_used`, so `build_si_label_block` never reconstructed `\label{fig:si1}`/`\label{fig:si2}`, and both rendered as `??` after `strip_si` removed the live labels (ultrareview finding on commit b3863d0). A mixed ref like `\cref{fig:main1,fig:si1}` failed the same way for its SI half. Fixed by splitting the label group on `,` for `ref`/`eqref`/`autoref`/`cref`/`Cref` and resolving each sub-label independently (`\pageref{}` unchanged — it doesn't support cleveref's multi-label form in standard LaTeX, so its group is still treated as one label). **Regression test added same day**: `tests/test_main_si.tex`/`.aux` extended with a second SI figure (`fig:si2`) and a `\Cref{fig:si1,fig:si2}` / `\cref{fig:main1,fig:si2}` pair; `check_extract_main` asserts both are left unchanged and that `fig:si2`'s `\label{}` is reconstructed | Yes |
| 2026-08-22 | `make_single_figure.sh`'s `for ii in $(seq -w 1 $NFIGS)` zero-pads output filenames to equal width once `NFIGS >= 10` (`fig01.pdf`…`fig10.pdf`), while `rewrite_figure_includes` in this script builds unpadded `figN.pdf` references — for any 10+-figure manuscript, `fig1.pdf`…`fig9.pdf` are referenced but don't exist on disk, and the final `pdflatex main.tex` compile fails on the first missing include (ultrareview finding on commit b3863d0; silent from this script's side, since `make_single_figure.sh` exits 0 — only surfaces at the submission-folder compile step, past this script's own test coverage). Fixed by dropping `-w` from the `seq` call so filenames are never padded, matching `rewrite_figure_includes`'s `str(n)` | Yes |
| 2026-09-15 | No code change (appendix support landed in both converters, see `beamer_to_ams_spec.md` §4.10 / `beamer_to_agu_spec.md` §4.11) — this script needed none, by construction (§5). Verified rather than assumed: appendix content added to `tests/test_main_si.tex` (before `%% SI_BEGIN`) with an `A1`-ref `\newlabel` in `tests/test_main_si.aux`; `check_extract_main` extended to assert the appendix figure/command/title survive in `main.tex` and its `A1` ref is left as a live `\ref{}` rather than swept into the SI label-reconstruction block | Yes |
| 2026-10-28 | All 7 SI `\ref`s in a real AMS revision (`hdd-slides-r1_manuscript.tex`) stayed undefined in `main.tex` after two `pdflatex` passes, although the SI label block was present. The converters emit `\clearpage` *before* `%% SI_BEGIN`, so it survived truncation and put the label block on an empty page that LaTeX never outputs; its `\label` writes never reached `main.aux`. Fixed in `strip_si` by dropping trailing `\clearpage`/`\cleardoublepage`/`\newpage` (§4.2). Also, `tests/test_main_si.tex` had the `\clearpage` *after* the sentinel, unlike real converter output, so the bug never showed in tests. The fixture now puts it before the sentinel, and `check_extract_main` asserts that no `\clearpage` comes before the label block; the check was confirmed to fail on the old code. Re-verified on the real paper: 0 undefined references | Yes |
| 2026-10-28 | Folded the manual post-extraction steps into the script (§4.9): copy local `.cls`/`.sty`/`.bst` from the input dir or `ams/`/`agu/`; test-compile `main.tex` in `outdir` with `TEXINPUTS` unset (2–4 passes, until no rerun request), summarizing undefined refs/citations and overfull boxes, exit 1 on failure; prune `main_figures.*`/`main.aux`/`.out`/`.log`. New flags `--no-compile`, `--keep-intermediates`. Real paper (`hdd-slides-r1_manuscript.tex`): class copied, 37 pages in 3 passes, 0 undefined refs/citations, folder left with `main.tex`, `fig1–10.pdf`, `ametsocV6.1.cls`, `main.pdf`. New e2e test `check_compile_and_package` (support-file copy, commented `\usepackage` ignored, pruning, TEXINPUTS-only `.sty` → exit 1 with `main.log` kept); it caught a bug during development where a failed compile exited 0. Existing extract_main tests now pass `--no-compile` | Yes |
