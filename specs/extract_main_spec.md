# Spec: extract_main.py

## 1. Purpose

Extract a main-text-only manuscript from a combined main+SI `.tex` file, for
the submission/revision step where journals require the main text as its own
file separate from the Supporting Information (SI).

The combined `.tex` (produced by `beamer_to_ams.py` / `beamer_to_agu.py`, or
hand-written) keeps main text and SI in one document so that `\ref{}` in the
main text resolves directly to SI item numbers (e.g. `S1`, `S2`). This script:

- Cuts the document at the SI boundary, **never writing to the input file**.
- Replaces any `\ref{}`/`\eqref{}`/`\pageref{}` pointing at an SI item with
  the literal number it resolved to in the combined document's `.aux`, so
  the main-only file has no dangling references.
- Extracts each `\begin{figure}...\end{figure}` block into its own
  `figN.pdf` (via `make_single_figure.sh`) and rewrites the
  `\includegraphics` path(s) to the bare filename `figN.pdf`, collapsing
  multi-panel figures to the single cropped composite.

---

## 2. Inputs

| File | Notes |
|------|-------|
| `COMBINED.tex` | Combined main+SI document. Read-only. |
| `COMBINED.aux` | `.aux` from compiling `COMBINED.tex`. Default: `<stem>.aux` next to `COMBINED.tex`. Source of SI item numbers (`S1`, `S2`, ...). If absent, SI `\ref{}`s are left unflattened (warning emitted). |

---

## 3. Outputs

All written to `--outdir` (default `<stem>_main/`); the input `.tex`/`.aux`
are never written.

| File | Contents |
|------|----------|
| `main.tex` | SI removed, SI refs flattened, figure includes rewritten to `figN.pdf` |
| `fig1.pdf`, `fig2.pdf`, ... | One PDF per live figure environment, cropped (via `make_single_figure.sh`) |
| `main_figures*.tex/.pdf/.log` | `make_single_figure.sh` intermediates (not cleaned up) |

CLI summary lines report: how the SI boundary was found, how many SI refs
were flattened, and how many figures were generated/rewritten. Warnings go to
stderr.

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

If none match, the script aborts with an error and writes nothing.

### 4.2 SI stripping (`strip_si`)

Truncate the text before the SI boundary, `rstrip()`, and ensure exactly one
trailing `\end{document}` (appended if the truncated text doesn't already end
with one). Because both converters emit the sentinel *after* the
bibliography/`\clearpage` (AMS: appended to the injected `bib_lines` block;
AGU: prepended to `_build_si_header`'s block, itself placed after
`bib_line`), the bibliography is retained in `main.tex`.

### 4.3 `.aux` parsing (`parse_aux_labels`)

Line-by-line regex `\newlabel\{(label)\}\{\{(ref)\}\{(page)\}` → `{label:
{'ref': ref, 'page': page}}`. SI labels are those whose `ref` starts with
`"S"` (figure/table counters are reset and redefined to `S\arabic{...}` at
the SI boundary, so any SI item's resolved number begins with `S`).

### 4.4 Ref flattening (`flatten_refs`)

Regex `\\(ref|eqref|pageref|autoref|[Cc]ref)(\*?)\{(label)\}` over the
SI-stripped text. For labels in the SI set:

| Command | Replacement |
|---------|-------------|
| `\ref{l}`, `\ref*{l}` | literal `ref` text (e.g. `S3`) |
| `\eqref{l}`, `\eqref*{l}` | literal `(ref)` (amsmath wraps `\eqref` in parens) |
| `\pageref{l}`, `\pageref*{l}` | literal `page` text from the `.aux` |
| `\autoref{l}`, `\cref{l}`, `\Cref{l}` | **left unchanged** + warning |

`\autoref`/`\cref`/`\Cref` are left as-is because the noun they print
("Figure"/"Table"/"section"/...) isn't recoverable from `\newlabel` without
assuming a specific package's anchor-naming convention; producing a wrong
noun silently would be worse than flagging it for a manual fix. (The target
workflow's combined files use plain `\ref{}` only.)

For any `\ref`-family command whose label is **absent from the `.aux`
entirely** (not just non-SI), a "stale .aux?" warning is emitted once per
label — this also fires for labels referenced only inside commented-out
lines (harmless, but surfaced so the user can confirm).

### 4.5 Figure extraction and rewriting

1. `count_figure_envs` / `_live_figure_envs`: find
   `\begin{figure}...\end{figure}` blocks (`re.DOTALL`, matching
   `make_single_figure.sh`'s `awk '/\\begin{figure}/,/\\end{figure}/'` range),
   **skipping any whose `\begin{figure}` is commented out** (`_is_commented`:
   an unescaped `%` earlier on the same line). This matters because AGU
   template boilerplate often leaves commented-out example figure blocks
   (`% \begin{figure} ... % \end{figure}`) in the main body; these produce no
   pages in `make_single_figure.sh`'s harness PDF and must not consume a
   `figN` slot or be miscounted.
2. If `count_figure_envs(main_text) == 0`, skip figure extraction entirely.
3. Otherwise run `make_single_figure.sh main.tex` (cwd = outdir) →
   `fig1.pdf ... figN.pdf`, one per live figure environment in document
   order (N = `count_figure_envs` result).
4. `rewrite_figure_includes`: walk the same live figure environments in
   order (1-based `n`). In the `n`-th block, replace the **first**
   `\includegraphics[opts]{...}` with `\includegraphics[opts]{figN.pdf}`
   (bare filename, no directory — so the output compiles in a flat
   submission folder) and **remove** any additional `\includegraphics` in
   that block (multi-panel figures collapse to the single cropped
   composite). Commented-out blocks and all text outside live figure
   environments pass through unchanged.

### 4.6 Safety

- `out_tex.resolve() == combined_tex.resolve()` → abort before writing
  anything (refuses to let `--outdir`/filename collide with the input).
- SHA-256 of the input bytes is checked before and after the run; a mismatch
  aborts with an error (defense in depth — nothing in the algorithm should
  ever write to the input, but this catches it if it ever does).

---

## 5. Edge Cases & Error Handling

| Situation | Handling |
|-----------|----------|
| No SI boundary found | Abort, nothing written |
| `.aux` missing | SI refs left as `\ref{...}` (will render `??`); warning emitted |
| Label referenced but not in `.aux` | Warning ("stale .aux?"), left unchanged |
| `\ref{}` to a main-text label (ref doesn't start with `S`) | Left unchanged (resolves correctly within `main.tex` itself) |
| `\autoref`/`\cref`/`\Cref` to an SI label | Left unchanged + warning (manual fix) |
| Commented-out `\begin{figure}...\end{figure}` (template boilerplate) | Skipped — not counted, not rewritten, passed through verbatim |
| Multi-panel figure (2+ `\includegraphics` in one `\begin{figure}`) | Collapses to one `\includegraphics{figN.pdf}`; extra includes removed |
| No live figure environments | Figure extraction skipped entirely |
| `--no-figures` | SI strip + ref flattening only; `\includegraphics` paths untouched |
| `--outdir`/output path would collide with input `.tex` | Abort before writing |

---

## 6. Synchronization Log

| Date | Change | Spec updated |
|------|--------|-------------|
| 2026-06-12 | Initial implementation: SI boundary detection (sentinel/section-marker/thefigure fallback), `.aux`-based ref flattening (`\ref`/`\eqref`/`\pageref`; `\autoref`/`\cref`/`\Cref` warn-and-skip), figure extraction via `make_single_figure.sh` with `\includegraphics` rewrite to bare `figN.pdf` and multi-panel collapse, comment-aware figure-env counting | Yes |
