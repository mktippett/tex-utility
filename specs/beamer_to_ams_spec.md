# Spec: beamer_to_ams.py

## 1. Purpose

Convert a Beamer slide deck (`.tex`) to a draft AMS journal manuscript
(`\documentclass{ametsocV6.1}`) suitable for sharing with coauthors.
The script restructures slide content into prose paragraphs and figure
environments, extracts metadata (title, authors, affiliations, abstract)
from the Beamer preamble, and emits a compilable `.tex` file.

---

## 2. Inputs

| File | Relevant content | Notes |
|------|-----------------|-------|
| `slides.tex` | Full Beamer source | Preamble + `\begin{document}...\end{document}` |

Key preamble commands parsed:

| Command | Extracted field |
|---------|----------------|
| `\title[short]{Long title}` | AMS `\title{}` |
| `\author[short]{Name\inst{N} \and Name\inst{N}}` or `\author[short]{Name\inst{N}, Name\inst{N}, and Name\inst{N}}` | AMS `\authors{}` with `\aff{}` and `\correspondingauthor{}` |
| `\institute[]{...}` | AMS `\affiliation{\aff{a}{...}\\...}` |

---

## 3. Outputs

| File | Contents | Format |
|------|----------|--------|
| `<stem>_manuscript.tex` | AMS manuscript skeleton | UTF-8 LaTeX |

Output preamble includes: `\title{}`, `\authors{}`, `\affiliation{}`,
`\abstract{}` (populated from `\section{Abstract}` frame content).

Output postamble:
- **No supplemental section**: `\bibliographystyle{...}` + `\bibliography{...}` + `\end{document}` — built from raw source, not from passthrough events.
- **Supplemental section present**: bib commands are injected into the event list before the supplemental content (see §4.5); postamble is `\end{document}` only.

### `%TC:ignore` / `%TC:endignore` markers (texcount, 2026-07-02)

AMS's word-limit rule excludes the title page, authors/affiliations,
abstract, table text, figures, and references — but (unlike AGU's word-count
rule) it also excludes **captions**. Verified against `texcount -sum`
behavior directly (no file-level directive short of `%TC:ignore` wrapping
reliably zeroes a region; `%TC:macro \caption 0` was tested and has no
effect on `-sum`):

- Front matter: `%TC:ignore` immediately after `\begin{document}`,
  `%TC:endignore` immediately after `\maketitle` (`_build_preamble`) — wraps
  title/authors/affiliation/abstract in one block.
- Captions: every generated `\caption{...}` is individually wrapped in
  `%TC:ignore`/`%TC:endignore` (`_restructure_figures`, gated by the
  `caption_tcignore` option threaded through `figure_opts`; AMS sets
  `_AMS_FIGURE_OPTS = {'caption_tcignore': True}`, AGU leaves it `False` so
  its captions still count per AGU's rule).
- Supplemental Information: when a supplemental section is present, the
  injected bib block opens `%TC:ignore` right after `%% SI_BEGIN`; the
  postamble closes it with `%TC:endignore` immediately before
  `\end{document}`. This mirrors AGU's SI wrapping and lets `extract_main.py`'s
  existing orphan-`%TC:ignore` rebalancing (see `specs/extract_main_spec.md`)
  handle the split cleanly — validated end-to-end: `texcount -total -sum` on
  the combined file and on the `extract_main.py`-split `main.tex` both report
  the same Sum, zero "words outside text," and zero errors.
- All markers are emitted flush-left on their own line (required by
  texcount). `%TC:macro` directives were tried and rejected — they didn't
  change `-sum`; only `%TC:ignore` wrapping (or a runtime `-sum=` flag,
  not file-bakeable) works.

---

## 4. Algorithm

### 4.1 Metadata extraction (from full source before `\begin{document}`)

1. **Title**: regex for `\title[opt]{...}`, extract with `_extract_brace_group`.
2. **Authors / affiliations**: call `_parse_inst_blocks(src)` (shared,
   `beamer_common.py`) to parse `\author{...}` and
   `\institute{\inst{N} text \and \inst{N} text}`.  The author list is split
   on either the Beamer `\and` command or a comma-separated English list
   (`_AUTHOR_SEP_RE` in `beamer_common.py`), so both
   `Name\inst{N} \and Name\inst{N}` and
   `Name\inst{N}, Name\inst{N}, and Name\inst{N}` are accepted. Map `\inst{N}`
   numbers to `aff` letters (a, b, …) in order of first appearance.  Build:
   - `\authors{}` joined per the AMS template byline convention: a comma
     immediately after each name (before `\aff{}`) except the last author,
     and a literal `and ` prefix on the last author only — e.g.
     `\authors{Name\aff{a}\correspondingauthor{Abbrev.,\n    email} Name\aff{b} and Name\aff{c}}`
     (not `and`-joined between every pair)
   - `\affiliation{\n  \aff{a}{text}\\\n  \aff{b}{text}\n}`
   First author is assumed corresponding; abbreviated name uses initials
   for all words except the last (`_abbreviate_name`).

### 4.2 Body preprocessing

Operates on the text between `\begin{document}` and `\end{document}`:

1. Strip beamer display commands (`\titlepage`, `\maketitle`, etc.).
2. Strip beamer theme commands (`\usetheme`, `\setbeamercolor`, etc.).
3. Strip `\setcounter` and `\renewcommand` **except** `\thefigure`/`\thetable` resets.
4. Strip comment lines with `(?<!\\)%[^\n]*` (negative lookbehind preserves `\%`).

### 4.3 Event list

Scan the preprocessed body and build a sorted list of `(position, type, content)`:

| Type | Source pattern | Output |
|------|---------------|--------|
| `section` | `\section{Title}`, `\section*{Title}`, `\subsection{Title}`, or `\subsection*{Title}` | Same command, unchanged (`\section{Title}` or `\subsection{Title}`) |
| `frame` | `\begin{frame}...\end{frame}` | transformed prose/figures |
| `passthrough` | `\renewcommand\thefigure{...}`, `\setcounter{figure}{...}`, `\renewcommand\thetable{...}`, `\setcounter{table}{...}`, `\clearpage` outside frames | verbatim |

`build_event_list(body, keep_bibliographystyle=False)` — `\bibliographystyle`
and `\bibliography` are **not** captured as passthrough events; they are
injected explicitly into the postamble (see §4.5).

Passthrough events are filtered to positions **outside** frame ranges to
avoid duplicating commands that also appear inside frame content.

### 4.4 Abstract extraction

Before emitting the body, scan the event list for `section: Abstract`.
Consume the section header and all immediately following `frame` events;
transform their content and join as the `\abstract{}` text.  Remove these
events from the body event list.

### 4.5 Bibliography extraction and supplemental reordering

`_extract_bib_file(src)` and `_extract_bib_style(src)` (both in `beamer_common.py`)
scan the **full raw source** with `re.search`, so they find `\bibliography{...}` and
`\bibliographystyle{...}` regardless of whether those commands appear inside or
outside a Beamer frame.

After extracting the abstract, the event list is scanned for a section whose title
contains `supplement` (case-insensitive):

- **No supplemental section**: `_build_postamble(bib_style, bib_file)` emits:
  ```latex
  \bibliographystyle{<style>}   % omitted if not found in source
  \bibliography{<file>}
  \end{document}
  ```
- **Supplemental section found**:
  1. Any `\bibliography{...}` passthrough events already parsed from the body are
     removed (prevents duplication).
  2. A new passthrough event is inserted immediately before the supplemental section:
     ```latex
     \bibliographystyle{<style>}   % if present
     \bibliography{<file>}
     \clearpage
     %% SI_BEGIN
     ```
  3. The `\section{Supplemental…}` event is stripped (its following frame events
     remain, so the SI content appears after `\clearpage`).
  4. Postamble is reduced to `\end{document}`.

This ensures references always precede supplemental content in the output, mirroring
the explicit reorder logic in `beamer_to_agu.py`. The `%% SI_BEGIN` comment
sentinel marks the SI boundary, consumed by `extract_main.py`
(`specs/extract_main_spec.md`) when splitting out a main-text-only manuscript.

### 4.6 Frame content transformation (`transform_content`)

Applied to each frame's raw content string in order:

1. **Font size/shape stripping** — `_strip_font_size_cmds`: removes `\tiny`,
   `\scriptsize`, `\footnotesize`, `\small`, `\large`, `\Large`, `\LARGE`,
   `\huge`, `\Huge`, `\bfseries`, `\itshape`, etc., and
   `\fontsize{S}{B}\selectfont`.
2. **Spacing/transition commands** — strip `\pause`, `\newpage`, `\medskip`,
   `\vspace{...}`, `\centering`, `\noindent`, `\setlength`, etc.
3. **Overlay commands** — `\only<>{}`, `\visible<>{}`, etc. → keep content.
4. **Unwrap** — `\alert{x}` → `x`; `\textcolor{c}{x}` → `x`; `\structure{x}` → `x`.
5. **Column/minipage tags** — strip `\begin{columns}`, `\column{...}`,
   `\begin{minipage}{...}`, `\end{minipage}` (keep content).
6. **Figure restructuring** — `_restructure_figures`:
   - Convert `\captionof{type}{...}` → `\caption{...}` via balanced-brace matching.
   - Skip `\includegraphics` already inside `\begin{figure}...\end{figure}`.
   - Group consecutive `\includegraphics` into one figure.
   - Look ahead for `\caption{...}` (balanced braces) and `\label{...}`;
     include both inside the figure environment.
   - Strip font size commands from caption text.
   - When `caption_tcignore` is set in `figure_opts` (AMS only, via
     `_AMS_FIGURE_OPTS`), wrap the emitted `\caption{...}` line in
     `%TC:ignore`/`%TC:endignore` so `texcount` excludes it — see the
     `%TC` markers subsection under §3.
7. **List flattening** — `_flatten_lists`: `\begin{enumerate|itemize}...\end{...}`
   → prose paragraph; each `\item` becomes a sentence ending with `.`.
8. **Block environments** — `\begin{block}{Title}` → `\textbf{Title}`.
9. **Center environment** — strip tags, keep content.
10. **Whitespace cleanup** — collapse 3+ blank lines to 2.

### 4.7 Balanced brace helper

`_extract_brace_group(text, start)` — walks character by character tracking
depth; returns `(content, end_index)`.  Used throughout for: frame title
extraction, `\captionof` conversion, caption lookahead, `\frametitle` extraction,
metadata extraction from preamble.

---

## 5. Constants & Scientific Rationale

| Name | Value | Why |
|------|-------|-----|
| Aff letter series | `'abcdefghijklmnopqrstuvwxyz'` | AMS convention for `\aff{}` labels |
| Caption lookahead | ~balanced | Use `_extract_brace_group` rather than fixed char window to handle arbitrary caption length |
| Frame title length limit | 300 chars, no `\n\n` | Distinguishes `{Title}` arg from frame body starting with `{` |

---

## 6. Edge Cases & Error Handling

| Situation | Handling |
|-----------|----------|
| `\captionof` with nested braces (`\ref{}`, `\textbf{}`, `\fontsize{}{}`) | Handled by `_convert_captionof` using `_extract_brace_group` |
| `\%` in source text | Comment regex uses `(?<!\\)%` so `\%` is preserved |
| Frame title containing `\ref{fig:xxx}` | Balanced brace extraction handles nested `{}` in titles |
| `[allowframebreaks]` option prefix | `extract_frames` strips the full `[opt]{title}` prefix using `raw = raw[leading_ws + end:]` |
| Multiple `\includegraphics` side-by-side | Consecutive images (whitespace-separated) collected into one `\begin{figure}` |
| `\includegraphics` already in `\begin{figure}` | `_restructure_figures` detects existing figure env and passes it through unchanged |
| `\bibliographystyle`/`\bibliography` inside a frame | Stripped by `transform_content`; postamble uses values extracted from raw source, so inside-frame location is harmless |
| `\bibliographystyle`/`\bibliography` outside a frame | Same: extracted from raw source, not from passthrough events |
| `\section{Supplemental}` (or `Supplementary…`) present | Bibliography injected before it as a passthrough event; supplemental section marker stripped; `\clearpage` separates references from SI content; postamble = `\end{document}` only |
| No `\bibliography{}` in source | `_extract_bib_file` returns `'references'`; `_extract_bib_style` returns `None` (style line omitted) |
| No `\institute{}` in source | Falls back to per-author `Department, Institution, City, State` placeholder |
| `\author` without `\inst{}` markers | Authors assigned aff letters sequentially; single `\affiliation` placeholder |
| `\section{Abstract}` | Consumed into `\abstract{}` preamble block; removed from body |
| `\section*{...}` | Captured as section event (same as `\section{...}`); appears in output as-is |
| `\subsection{...}` / `\subsection*{...}` outside a frame | Captured as a `section` event (same regex, `(?:sub)?section`); previously unmatched and silently dropped from output. Passes through verbatim — no promotion/demotion to `\section` |

---

## 7. Synchronization Log

| Date | Change | Spec updated |
|------|--------|-------------|
| 2026-04-10 | Initial implementation: frame parser, list flattening, figure restructuring, AMS preamble skeleton | Yes |
| 2026-04-10 | Fixed `\%` stripping (negative lookbehind in comment regex) | Yes |
| 2026-04-10 | Removed `\usepackage{ametsoc}` and `\journal{}` from preamble (conflict/undefined in standalone cls) | Yes |
| 2026-04-10 | Added `_strip_font_size_cmds`; strips `\tiny`, `\scriptsize`, `\fontsize{}{}\selectfont` etc. | Yes |
| 2026-04-10 | Replaced `\captionof` regex with balanced-brace conversion (`_convert_captionof`) | Yes |
| 2026-04-10 | Replaced frame title extraction with balanced-brace matching | Yes |
| 2026-04-10 | Fixed double-wrapping: `_restructure_figures` skips existing `\begin{figure}` environments | Yes |
| 2026-04-10 | Group consecutive `\includegraphics` into single figure; capture `\label` after `\caption` | Yes |
| 2026-04-10 | Fixed `[allowframebreaks]` leaking: strip full `[opt]{title}` prefix in `extract_frames` | Yes |
| 2026-04-10 | Switched to section+frame event model; beamer `\section{}` → manuscript `\section{}`; frame titles dropped | Yes |
| 2026-04-10 | Extracted `\title`, `\author`, `\institute` from beamer preamble for AMS metadata | Yes |
| 2026-04-10 | `\section{Abstract}` frame content → `\abstract{}`; section removed from body | Yes |
| 2026-04-10 | `\authors{}` format: inline `\aff{}`, `\correspondingauthor{}`, `\affiliation{\aff{a}{...}\\...}` | Yes |
| 2026-04-10 | `\renewcommand\thefigure` and `\setcounter{figure}` preserved as passthrough events | Yes |
| 2026-04-16 | Shared: `\fig{path}` expanded to `\includegraphics{path}` in `preprocess_body` (beamer_common) | Yes |
| 2026-04-16 | Shared: `\bibliographystyle`/`\bibliography` stripped from frame content in `transform_content` | Yes |
| 2026-04-16 | Shared: `\thetable`/`\setcounter{table}` added to passthrough and preprocess preserve patterns | Yes |
| 2026-04-16 | Shared: `\clearpage` added to passthrough pattern | Yes |
| 2026-04-16 | Shared: `\label{}` immediately after `\section{}` now passed through | Yes |
| 2026-04-16 | Shared: `\section*{...}` now captured as section events (fixes over-consumption in `extract_abstract`) | Yes |
| 2026-04-26 | Shared: `extract_passthrough_packages` now passes through `\usepackage{bm}` in addition to `amsmath`/`amssymb` | Yes |
| 2026-05-07 | Shared: `_parse_inst_blocks` extracted to `beamer_common.py`; `_parse_authors_affiliations` now calls it | Yes |
| 2026-05-07 | Shared: `_extract_bib_file` and `_extract_bib_style` added to `beamer_common.py` | Yes |
| 2026-05-07 | Script renamed `beamer_to_manuscript.py` → `beamer_to_ams.py`; unified CLI `convert.py` added | Yes |
| 2026-05-07 | Shared: compiled module-level regex patterns for `_strip_font_size_cmds` and `preprocess_body`; `inc_re` extended to capture filename (group 2); double `frame_pat` scan in `build_event_list` eliminated; O(n²) `re.findall` in `_wrap_equations_linenomath` replaced with running depth counter | Yes |
| 2026-05-12 | Bibliography injection made robust to inside-frame location: `_extract_bib_file`/`_extract_bib_style` scan raw source; `_build_postamble` injects explicitly; `keep_bibliographystyle=False` (was `True`) | Yes |
| 2026-05-15 | Supplemental reorder: when `\section{Supplement*}` detected, bib commands + `\clearpage` injected before it; section marker stripped; postamble reduced to `\end{document}`. Mirrors AGU reorder logic. | Yes |
| 2026-06-12 | Appended `%% SI_BEGIN` sentinel after `\clearpage` in the injected bib block, marking the SI boundary for `extract_main.py` | Yes |
| 2026-06-24 | Shared: `extract_passthrough_packages` broadened from math-only to a curated allowlist (adds booktabs, multirow, array, tabularx, makecell, threeparttable, dcolumn, longtable, mathtools) | Yes |
| 2026-07-02 | Shared: fixed `_parse_inst_blocks` author-list split — old `\s+and\s+` regex never matched the Beamer `\and` command and mis-split comma/English-list authors, silently dropping middle co-authors; replaced with `_AUTHOR_SEP_RE` (matches `\and` or comma/"and" list) | Yes |
| 2026-07-03 | Shared: section-event regex extended from `\section` to `\(?:sub\)?section` in `build_event_list` and `extract_abstract`'s title match; `\subsection{...}`/`\subsection*{...}` outside a frame is now captured as a `section` event and passed through verbatim (previously matched no event type and was silently dropped) | Yes |
| 2026-07-02 | `_parse_authors_affiliations` (AMS): `\authors{}` join changed from `and`-between-every-author to the AMS template byline convention — comma after each name except the last, `and` before the last author only | Yes |
| 2026-07-02 | Added `%TC:ignore`/`%TC:endignore` markers for AMS's word-limit rule: front matter (title/authors/affiliation/abstract), every caption (new `caption_tcignore` option on `_restructure_figures`/`figure_opts`, off by default so AGU is unaffected), and the SI region (opens after `%% SI_BEGIN`, closes before `\end{document}`) | Yes |
