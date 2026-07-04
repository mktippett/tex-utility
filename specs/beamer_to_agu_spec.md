# Spec: beamer_to_agu.py

## 1. Purpose

Convert a Beamer slide deck (`.tex`) to a draft AGU journal manuscript
(`\documentclass{agujournal2019}`) suitable for sharing with coauthors.
The script restructures slide content into prose paragraphs and figure
environments, extracts metadata (title, authors, affiliations, abstract)
from the Beamer preamble, and emits a compilable `.tex` file.
Generic Beamer parsing is shared with `beamer_to_ams.py` via
`beamer_common.py`; only AGU-specific formatting lives here.

---

## 2. Inputs

| File | Relevant content | Notes |
|------|-----------------|-------|
| `slides.tex` | Full Beamer source | Preamble + `\begin{document}...\end{document}` |

Key preamble commands parsed:

| Command | Extracted field |
|---------|----------------|
| `\title[short]{Long title}` | AGU `\title{}` |
| `\author[short]{Name\inst{N} \and Name\inst{N}}` or `\author[short]{Name\inst{N}, Name\inst{N}, and Name\inst{N}}` | AGU `\authors{}` with `\affil{N}` numbers |
| `\institute[]{...}` | AGU `\affiliation{N}{...}` lines |

---

## 3. Outputs

| File | Contents | Format |
|------|----------|--------|
| `<stem>_agu.tex` | AGU manuscript skeleton | UTF-8 LaTeX |

Output preamble includes: `\journalname{}`, AGU publication-unit comment block,
`\title{}`, `\authors{}`, `\affiliation{N}{...}` (one per affiliation),
`\correspondingauthor{}{}`, `\begin{keypoints}...\end{keypoints}`,
`\begin{abstract}...\end{abstract}`, `\section*{Plain Language Summary}`.

Output postamble includes: `\section*{Open Research Section}`,
`\section*{Conflict of Interest}`, `\acknowledgments`, `\bibliography{}`,
SI header, `\end{document}`. The SI header begins with a `%% SI_BEGIN`
comment sentinel marking the SI boundary, consumed by
`extract_main.py` (`specs/extract_main_spec.md`) when splitting out a
main-text-only manuscript.

`%TC:ignore` / `%TC:endignore` markers are inserted for `texcount` compatibility:
- Title block (title → key points): ignored
- Plain Language Summary: ignored
- Endmatter through SI header (Open Research → SI header): ignored
- Abstract and body: **counted**

---

## 4. Algorithm

### 4.1 Metadata extraction

Steps 4.1–4.4 are shared with the AMS converter via `beamer_common.py`:

1. **Title**: regex for `\title[opt]{...}`, extract with `_extract_brace_group`.
2. **Authors/affiliations**: `_parse_authors_affiliations_agu` (see §4.2).
3. **Body preprocessing**: `preprocess_body` — strip Beamer theme commands, comments.
4. **Event list**: `build_event_list(body, keep_bibliographystyle=False)` — captures
   `\section{...}`, `\section*{...}`, `\subsection{...}`, and `\subsection*{...}`
   as section events, passed through verbatim (no promotion/demotion between
   levels); AGU omits `\bibliographystyle` passthroughs because the class loads
   `apacite` internally.
5. **End-matter sentinels**: `extract_sentinel_block` (shared, `beamer_common.py`;
   the AMS converter reads the same sentinels) run on original `src` for canonical labels
   `DATA`, `COI`, `ACKS` (legacy `AGU_OPENRESEARCH`/`AGU_COI`/`AGU_ACKS` spellings
   accepted via `_SENTINEL_ALIASES`); sentinel regions stripped from source before preprocessing;
   frame wrappers stripped; AGU headers injected; assembled as single event before Supplemental.
6. **Abstract**: `extract_abstract` — consumes `\section{Abstract}` and following frames.
7. **Plain Language Summary**: `extract_plain_language_summary` (shared) — consumes
   `\section*{Plain Language Summary}` and following frames; injects into preamble
   (returns `None` when absent; AGU substitutes its placeholder text).
8. **Body assembly**: `assemble_body(events, figure_opts=_AGU_FIGURE_OPTS)`.

### 4.2 AGU author/affiliation parsing (`_parse_authors_affiliations_agu`)

Calls `_parse_inst_blocks(src)` (shared, `beamer_common.py`) to parse
`\author{...}` and `\institute{...}`, then produces AGU-specific markup.
The author list is split on either the Beamer `\and` command or a
comma-separated English list (`_AUTHOR_SEP_RE`), so both
`Name\inst{N} \and Name\inst{N}` and
`Name\inst{N}, Name\inst{N}, and Name\inst{N}` are accepted:

- `\inst{N}` numbers map **directly** to `\affil{N}` (no letter conversion).
- `\authors{...}` uses comma separation with "and" before the last author
  (e.g., `A\affil{1}, B\affil{2}, and C\affil{3}`).
- One `\affiliation{N}{text}` command per unique affiliation number.
- `\correspondingauthor{Full Name}{email@institution.edu}` — **two** separate
  brace groups (AGU convention); email is a placeholder.

### 4.3 Citation remapping (`_remap_citations_to_apacite`)

The Beamer source uses `natbib` commands; AGU requires `apacite`.
Applied as a final pass over the manuscript body:

| natbib | apacite | Notes |
|--------|---------|-------|
| `\citet{key}` | `\citeA{key}` | Author (year) style |
| `\citet[post]{key}` | `\citeA[post]{key}` | One optional arg |
| `\citet[pre][post]{key}` | `\citeA<pre>[post]{key}` | Two args; prenote in `<>` |
| `\citet[][post]{key}` | `\citeA[post]{key}` | Empty prenote dropped |
| `\citep{key}` | `\cite{key}` | Parenthetical citation |
| `\citep[post]{key}` | `\cite[post]{key}` | |
| `\citep[pre][post]{key}` | `\cite<pre>[post]{key}` | apacite prenote in `<>` |
| `\citealp{key}` | `\cite{key}` | No-paren form; closest match |
| `\citeauthor{key}` | `\citeA{key}` | Author only |
| `\citeyear{key}` | unchanged | apacite has `\citeyear` |

### 4.4 Equation wrapping (`_wrap_equations_linenomath`)

AGU with `\linenumbers` active requires display math inside
`\begin{linenomath*}...\end{linenomath*}` to avoid broken line numbering.

Environments wrapped: `equation`, `equation*`, `eqnarray`, `eqnarray*`,
`align`, `align*`, `multline`, `multline*`, `gather`, `gather*`, and `\[...\]`.
Environments already inside an open `linenomath*` are skipped.

### 4.5 Figure formatting

AGU figures use different conventions from AMS, controlled via
`_AGU_FIGURE_OPTS = {placement: '', centering: False, noindent: True, default_width: r'\textwidth'}`:

- No float placement option (AGU default `tbp` is fine).
- No `\centering`.
- `\noindent` prefixed to each `\includegraphics`.
- `[width=\textwidth]` added only when the `\includegraphics` has no existing
  options; existing width options are preserved.

### 4.6 Passthrough filter

`build_event_list(..., keep_bibliographystyle=False)` passes through verbatim
any occurrences of the following that appear **outside** frame environments:

- `\renewcommand\thefigure{...}` and `\renewcommand\thetable{...}`
- `\setcounter{figure}{...}` and `\setcounter{table}{...}`
- `\clearpage`
- `\bibliography{...}`

`\bibliographystyle{...}` is dropped (AGU class loads `apacite` internally).

`\bibliographystyle{...}` and `\bibliography{...}` that appear **inside** frames
are stripped by `transform_content` (added to the cleanup command list), preventing
duplicate `\bibstyle`/`\bibdata` errors in BibTeX.

`extract_passthrough_packages` (in `beamer_common.py`) passes through
`\usepackage` lines whose package names are all in a curated allowlist:
math (`amsmath`, `amssymb`, `bm`, `mathtools`) and tables (`booktabs`,
`multirow`, `array`, `tabularx`, `makecell`, `threeparttable`, `dcolumn`,
`longtable`).  Lines with any package not in the list are dropped (avoids
beamer-only and class-provided duplicates).  Options (`[...]`) are preserved.

### 4.7 Bibliography file extraction (`_extract_bib_file`)

`_extract_bib_file(src)` lives in `beamer_common.py` (shared with AMS converter).
Scans the full source with `re.search(r'\\bibliography\{([^}]+)\}', src)` and
returns the first match (e.g. `all`). Always called; the result is appended as
`\bibliography{name}` at the end of the assembled endmatter block.

### 4.8 Endmatter sentinels

End-matter content (Open Research, Conflict of Interest, Acknowledgments) is
marked in the Beamer source using comment sentinels that wrap normal Beamer
frames. The frames compile and render as slides; the sentinels are invisible
to Beamer (pure `%` comments).

**Convention in the Beamer source** (canonical spellings; the legacy
AGU-first forms `AGU_OPENRESEARCH`/`AGU_COI`/`AGU_ACKS` are accepted
indefinitely via `_SENTINEL_ALIASES` in `beamer_common.py`):

```latex
%% DATA_BEGIN
\begin{frame}{Data Availability}
  \begin{itemize}
    \item Data archived at \url{https://zenodo.org/...}
  \end{itemize}
\end{frame}
%% DATA_END

%% COI_BEGIN
\begin{frame}{Conflict of Interest}
  The authors declare no conflicts of interest.
\end{frame}
%% COI_END

%% ACKS_BEGIN
\begin{frame}{Acknowledgments}
  Supported by NSF grant AGS-0000000.
\end{frame}
%% ACKS_END
```

**Extraction pipeline** (`extract_sentinel_block`, `strip_frame_wrappers` —
both shared in `beamer_common.py`; the AMS converter reads the same sentinels
with its own header mapping, see `specs/beamer_to_ams_spec.md` §4.9):

1. Sentinel detection runs on the **original source** (`src`) before
   `preprocess_body`, because `preprocess_body` strips `%` comment lines.
2. The sentinel-marked regions are **removed from `src`** before calling
   `preprocess_body`, so the wrapped frames never enter the manuscript event list.
3. For each found sentinel, `strip_frame_wrappers` strips the
   `\begin{frame}{...}` / `\end{frame}` wrappers (the frame title is discarded;
   the AGU section header replaces it). `transform_content` processes the body.
4. The converter **injects the AGU section header** from `_SENTINEL_HEADERS`:
   - `DATA` → `\section*{Open Research Section}`
   - `COI` → `\section*{Conflict of Interest}`
   - `ACKS` → `\acknowledgments`
5. Missing sentinel blocks fall back to the per-section stub in `_STUBS`.
6. The three pieces are concatenated in fixed order (Open Research → COI → Acks),
   followed by `\bibliography{bib_file}`.
7. The assembled endmatter event is moved before any Supplemental section (same
   reorder logic as before).

### 4.9 Plain Language Summary extraction (`extract_plain_language_summary`)

Shared in `beamer_common.py`. Mirrors `extract_abstract`. Finds
`\section*{Plain Language Summary}` (matched by `\section\*?\{...\}` regex),
consumes it and all immediately following frame events, transforms their
content, and returns `(pls_text_or_None, remaining_events)`. AGU substitutes
`'Enter plain language summary here.'` when `None`; the text is injected into
the `{pls_text}` slot in `_build_agu_preamble`. Likewise `extract_key_points`
(shared) returns `[]` when no Key points section is found; `_build_agu_preamble`
pads with `_KP_DEFAULTS`.

### 4.10 Word-count markers (`%TC:ignore` / `%TC:endignore`)

AGU counts words in the abstract and body only; title metadata, key points, PLS,
and endmatter are excluded. `texcount` directive comments implement this:

| Block | Start marker | End marker |
|-------|-------------|-----------|
| `\title{}` → `\end{keypoints}` | `%TC:ignore` (before `\title`) | `%TC:endignore` (after `\end{keypoints}`) |
| Plain Language Summary | `%TC:ignore` (before `\section*{Plain Language Summary}`) | `%TC:endignore` (after PLS text) |
| Endmatter → SI header | `%TC:ignore` (prepended to `em_text`) | `%TC:endignore` (in `_AGU_CLOSE`, before `\end{document}`) |

The `\begin{abstract}...\end{abstract}` block and body sections are outside all
ignore blocks and are counted normally.

A publication-unit guidance comment is injected between `\journalname{}` and
`\begin{document}` (two `%`-prefixed lines explaining the 25 PU limit, word-count
exclusions, and the 12 PU limit for GRL letters).

---

## 5. Constants & Scientific Rationale

| Name | Value | Why |
|------|-------|-----|
| Document class | `agujournal2019` | AGU class file |
| Draft option | `[draft]` | Enables double-spacing and line numbers |
| `\linenumbers` | active | Required for AGU submission; `linenomath*` prevents numbering inside equations |
| Journal name placeholder | `JGR: Atmospheres` | Must be changed to target journal |
| Author separator | comma + "and" before last | AGU authors style guide |
| Affiliation numbering | integers 1, 2, … | AGU `\affil{N}` uses numbers, not letters |
| Citation style | `apacite` | Loaded by `agujournal2019.cls`; no `\bibliographystyle` allowed |

---

## 6. Edge Cases & Error Handling

| Situation | Handling |
|-----------|----------| 
| `%% EMAIL: addr` (or legacy `%% AGU_EMAIL:`) absent | Falls back to `email@institution.edu` placeholder |
| `\citet[][post]{key}` (empty prenote) | `_citet_two_args` detects empty pre, emits `\citeA[post]{key}` (no `<>`) |
| `\bibliographystyle{...}` in source | Dropped from passthrough events (`keep_bibliographystyle=False`) |
| `\includegraphics[width=X]` already has options | `default_width` not applied; existing options preserved |
| Equation already in `linenomath*` | `_wrap_equations_linenomath` counts open/close tags; skips if already inside |
| No `\institute{}` in source | Falls back to per-author `Department, Institution, City, Country` placeholder |
| `\author` without `\inst{}` markers | Authors assigned sequential numbers; single `\affiliation{1}{...}` placeholder |
| `\bibliography{...}` inside a frame | Stripped by `transform_content`; postamble uses bib name extracted from source |
| `\bibliographystyle{...}` inside a frame | Stripped by `transform_content`; prevents duplicate `\bibstyle` BibTeX error |
| `\fig{path}` macro | Expanded to `\includegraphics{path}` in `preprocess_body` (slide size options dropped) |
| `\renewcommand\thetable` / `\setcounter{table}` | Passed through verbatim for supplemental table numbering |
| `\clearpage` outside frames | Passed through verbatim |
| `\section{Abstract}` | Consumed into `\begin{abstract}...\end{abstract}` block; removed from body |
| `\section*{Plain Language Summary}` + frames | Consumed by `extract_plain_language_summary` (shared); injected into preamble PLS slot |
| `\section*{Plain Language Summary}` merging into abstract | Fixed by capturing `\section*{...}` as section events; stops `extract_abstract` over-consuming |
| Sentinel blocks in source | Extracted before `preprocess_body`; frames removed from body; AGU headers injected; assembled as single endmatter event |
| Missing sentinel block | Per-section stub (`_STUBS[label]`) used; other sentinel blocks are unaffected |
| Sentinels inside a frame body (not wrapping a frame) | `strip_frame_wrappers` finds no frame wrappers; content returned as-is |
| End-matter after `\section{Supplemental…}` in source | Reordered to appear before Supplemental in output (`is_si_section` shared matcher: `supplement` or `supporting information`, case-insensitive) |
| No Supplemental section | SI checklist counts stay 0; all three items commented out |
| SI has figures but no `\fig{}`| Falls back to counting `\includegraphics{` in SI frame content |
| SI has tables via `\begin{table}` only (no `tabular`) | Falls back to counting `\begin{table` if `\begin{tabular` count is 0 |
| `\subsection{...}` / `\subsection*{...}` outside a frame | Captured as a `section` event (same regex, `(?:sub)?section`); previously unmatched and silently dropped from output. Passes through verbatim — no promotion/demotion to `\section` |

---

## 7. Synchronization Log

| Date | Change | Spec updated |
|------|--------|-------------|
| 2026-04-12 | Initial implementation: AGU preamble, `\affil{N}` numbering, `_remap_citations_to_apacite`, `_wrap_equations_linenomath`, AGU figure opts | Yes |
| 2026-04-12 | Extracted shared code to `beamer_common.py`; `preprocess_body`, `build_event_list`, `extract_abstract`, `assemble_body` now shared | Yes |
| 2026-04-12 | Added two-arg `\citet[pre][post]{key}` handling in `_citet_two_args` | Yes |
| 2026-04-16 | `\fig{path}` expanded to `\includegraphics{path}` in `preprocess_body` | Yes |
| 2026-04-16 | `\bibliographystyle` and `\bibliography` added to `transform_content` strip list (prevents BibTeX duplicates) | Yes |
| 2026-04-16 | `_extract_bib_file()` added; postamble now dynamic via `_agu_postamble(bib_file)` | Yes |
| 2026-04-16 | `\thetable`/`\setcounter{table}` added to passthrough and preprocess preserve patterns | Yes |
| 2026-04-16 | `\clearpage` added to passthrough pattern | Yes |
| 2026-04-16 | `\label{}` immediately after `\section{}` now passed through (section regex extended) | Yes |
| 2026-04-16 | `_find_endmatter_block`: end-matter captured verbatim at source position; moved before Supplemental | Yes |
| 2026-04-19 | Replaced single `AGU_ENDMATTER_BEGIN/END` sentinel with three per-section sentinels (`AGU_OPENRESEARCH`, `AGU_COI`, `AGU_ACKS`); sentinel detection now runs on `src` before preprocessing; wrapped frames are stripped from source before `preprocess_body` to prevent duplication; converter injects AGU headers; per-section stubs for missing blocks | Yes |
| 2026-04-16 | `_extract_plain_language_summary`: PLS frame content extracted into preamble PLS slot | Yes |
| 2026-04-16 | Shared: `\section*{...}` captured as section events; fixes abstract/PLS merge bug | Yes |
| 2026-04-26 | Shared (`beamer_common.py`): `\usepackage{bm}` added to `extract_passthrough_packages` filter | Yes |
| 2026-04-26 | AGU PU comment block added between `\journalname{}` and `\begin{document}`; `%TC:ignore`/`%TC:endignore` markers added around title+keypoints block, PLS block, and endmatter+bibliography+SI block | Yes |
| 2026-04-29 | `_extract_email`: parses `%% AGU_EMAIL: address` sentinel from Beamer source; email threaded into `_build_agu_preamble` replacing hardcoded placeholder | Yes |
| 2026-05-06 | `_build_si_header`: added `\setcounter{page}{1}` after `\clearpage`; SI checklist now dynamic via `_make_si_checklist(n_figs, n_tables)`; Text item always commented out; Figure/Table items commented out if count is 0, singular if 1; `convert()` counts `\fig{}`/`\includegraphics` and `\begin{tabular}`/`\begin{table}` in Supplemental frames before building SI header | Yes |
| 2026-05-07 | Shared: `_parse_inst_blocks` extracted to `beamer_common.py`; `_parse_authors_affiliations_agu` now calls it | Yes |
| 2026-05-07 | `_extract_bib_file` moved to `beamer_common.py` (shared with AMS converter) | Yes |
| 2026-05-07 | Shared: `_extract_bib_style` added to `beamer_common.py` (used by AMS; AGU does not use it) | Yes |
| 2026-05-07 | Script `beamer_to_manuscript.py` renamed to `beamer_to_ams.py`; unified CLI `convert.py --format ams|agu` added | Yes |
| 2026-05-07 | Shared: compiled module-level regex patterns (`_FONTSIZE_SELECTFONT_RE`, `_FONT_STYLE_RE`, `_BEAMER_BODY_CMDS_RE`, `_BEAMER_SETUP_RE`) eliminate per-call compiles in `_strip_font_size_cmds` and `preprocess_body`; `inc_re` extended with filename capture group (group 2); double `frame_pat` scan in `build_event_list` collapsed to single pass; O(n²) `re.findall` in `_wrap_equations_linenomath` replaced with running `depth` counter; `em_idx` search replaced with `len(events)-1` | Yes |
| 2026-05-07 | Shared: `_KP_DEFAULTS` defined once at module level; removes duplicate literal list from `_extract_key_points` and `_build_agu_preamble` | Yes |
| 2026-06-12 | `_build_si_header`: prepend `%% SI_BEGIN` sentinel as the first line of the returned block (before `\clearpage`), marking the SI boundary for `extract_main.py` | Yes |
| 2026-06-24 | Shared: `extract_passthrough_packages` broadened from math-only to a curated allowlist (adds booktabs, multirow, array, tabularx, makecell, threeparttable, dcolumn, longtable, mathtools) | Yes |
| 2026-07-02 | Shared: fixed `_parse_inst_blocks` author-list split — old `\s+and\s+` regex never matched the Beamer `\and` command and mis-split comma/English-list authors, silently dropping middle co-authors; replaced with `_AUTHOR_SEP_RE` (matches `\and` or comma/"and" list) | Yes |
| 2026-07-03 | Shared: section-event regex extended from `\section` to `\(?:sub\)?section` in `build_event_list` and `extract_abstract`'s title match; `\subsection{...}`/`\subsection*{...}` outside a frame is now captured as a `section` event and passed through verbatim (previously matched no event type and was silently dropped) | Yes |
| 2026-07-04 | Shared: `_extract_sentinel_block`, `_strip_frame_wrappers`, `_extract_email`, `_extract_key_points`, `_extract_plain_language_summary` moved to `beamer_common.py` as `extract_sentinel_block`, `strip_frame_wrappers`, `extract_email`, `extract_key_points`, `extract_plain_language_summary` (now also used by the AMS converter). Return-value change: KP extractor returns `[]` and PLS extractor `None` when the section is absent; AGU applies `_KP_DEFAULTS`/placeholder itself. AGU output byte-identical before/after (verified on tests/test_input.tex) | Yes |
| 2026-07-04 | Shared: SI section matching unified as `is_si_section` in `beamer_common.py` (`supplement` \| `supporting information`, case-insensitive; previously AGU matched only `supplemental` — a `\section{Supplement}` or `\section{Supporting Information}` deck was silently not reordered) | Yes |
| 2026-07-04 | Shared: sentinel names made generic — canonical `DATA`/`COI`/`ACKS` and `%% EMAIL:` with legacy `AGU_OPENRESEARCH`/`AGU_COI`/`AGU_ACKS`/`%% AGU_EMAIL:` accepted indefinitely (`_SENTINEL_ALIASES` in `beamer_common.py`); `_STUBS`/`_SENTINEL_HEADERS` keys renamed `OPENRESEARCH` → `DATA`. Output byte-identical for legacy decks | Yes |
