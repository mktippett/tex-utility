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

Output preamble includes: `\usepackage[T1]{fontenc}` (first line after
`\documentclass` — `ametsocV6.1.cls` loads Times-like fonts via
`mathptmx`/`newtxtext` but never loads `fontenc` itself, and without T1 the
default OT1 encoding silently mis-substitutes non-ASCII text-mode commands
like `\l`, breaking word spacing; see 2026-08-20 in §7), `\title{}`,
`\authors{}` (corresponding-author
email from the `%% EMAIL:` sentinel, shared with the AGU converter; legacy
`%% AGU_EMAIL:` accepted; placeholder if absent), `\affiliation{}`,
`\abstract{}` (populated from
`\section{Abstract}` frame content), and — after `\maketitle` — a commented
`%\statement` block (see §4.8).

No journal-name/journal-key directive is emitted at all: AMS removed the
per-journal macro from `ametsoc.cls` in package v5.0 (2020; see
`ams/AMS LaTeX Package V6.1/README.txt`, "Removed option to select journal
name for two-column") and neither `ametsocV6.1.cls` nor `templateV6.1.tex`
retains any journal-selection command, live or commented. This differs from
AGU, where `\journalname{}` is a real, live macro (see §4.1b history below
and `specs/beamer_to_agu_spec.md`).

Endmatter (`\acknowledgments` + `\datastatement`, see §4.9) is emitted
immediately before the bibliography in both postamble variants:
- **No supplemental section**: endmatter + `\bibliographystyle{...}` + `\bibliography{...}` + `\end{document}` — bib commands built from raw source, not from passthrough events.
- **Supplemental section present**: endmatter + bib commands are injected into the event list before the supplemental content (see §4.5); postamble is `\end{document}` only.

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
- Captions: every generated `\caption{...}` — figure **and** table — is
  individually wrapped in `%TC:ignore`/`%TC:endignore`
  (`_restructure_figures`/`_restructure_tables`, gated by the
  `caption_tcignore` option threaded through `figure_opts`; AMS sets
  `_AMS_FIGURE_OPTS = {'caption_tcignore': True}`, AGU leaves it `False` so
  its captions still count per AGU's rule) — **except** captions inside the
  Supplemental Information section (see below), which must not get this
  per-caption wrapping.
- texcount's `%TC:ignore`/`%TC:endignore` markers are an on/off **toggle**,
  not a nesting counter: a `%TC:endignore` while already ignoring turns
  ignoring off, even if it was meant to close an "inner" pair. SI content
  already sits inside the outer SI `%TC:ignore` (see below), so if its
  figures/tables were also given the per-caption `caption_tcignore`
  wrapping, the first caption's `%TC:endignore` would flip ignoring off
  mid-SI and desync the toggle from the actual `\begin{figure}`/`\end{figure}`
  pairs for the rest of the document — texcount then reports `Environment
  \begin{document} ended with \end{figure}` and a stray `%TC:endignore
  without corresponding %TC:ignore` (found 2026-07-08). Fixed by splitting
  the event list at the `%% SI_BEGIN` marker (`convert()`) and assembling
  the SI portion with `figure_opts={'caption_tcignore': False}` — SI figures
  get no per-caption ignore markers since the outer SI ignore already covers
  them.
- Endmatter: the `\acknowledgments` + `\datastatement` block is wrapped in
  its own `%TC:ignore`/`%TC:endignore` pair — AMS's word-limit rule excludes
  acknowledgments and the data availability statement.
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

After extracting the abstract (and consuming Key points / PLS, §4.8), the
event list is scanned for a section matching `is_si_section` (shared matcher
in `beamer_common.py`: `supplement` or `supporting information`,
case-insensitive — one matcher for both converters, consistent with
`extract_main.py`'s fallback patterns):

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
     %TC:ignore
     \acknowledgments
     ...
     \datastatement
     ...
     %TC:endignore

     \bibliographystyle{<style>}   % if present
     \bibliography{<file>}
     \clearpage
     %% SI_BEGIN
     %TC:ignore
     \setcounter{page}{1}
     \begin{center}
     {\large\bfseries Supplemental material for:\par}
     \vskip 12pt
     {\large\bfseries <title>\par}
     \vskip 12pt
     {\normalsize <authors with \aff{} letters>\par}
     \vskip 6pt
     {\it <affiliations, one per \aff{} letter>\par}
     \end{center}
     \vskip 12pt
     \noindent{\it Corresponding author}: <first author full name>, <email>
     \clearpage
     ```
     The title page is built by `_build_si_titlepage(title, authors, aff_block,
     email)`, reusing the same `title_text`, `authors` (`(name, letter)` list from
     `_parse_authors_affiliations`), `affiliation_block`, and `email` already
     computed for the main title page — no re-parsing. `\maketitle` cannot be
     reused for this second title page: `ametsocV6.1.cls` does
     `\global\let\maketitle\relax`/`\global\let\@maketitle\relax` at the end of
     its first (and only) call, so the layout is hand-built to mirror
     `\@maketitle` (title in bold, authors normal weight, affiliations italic,
     all centered). Mirrors `beamer_to_agu.py`'s `_build_si_header`, styled after
     the AMS title page rather than AGU's SI header/checklist. Sits inside the
     `%TC:ignore` opened here (word-count exempt, like the main title page).
     Appendices are explicitly out of scope for this converter — an author
     chooses `\appendix` commands manually; nothing here builds one.
  3. The `\section{Supplemental…}` event is stripped (its following frame events
     remain, so the SI content appears after the title page's trailing `\clearpage`).
  4. Postamble is reduced to `\end{document}`.
  5. The event list is split at the `%% SI_BEGIN` passthrough marker: events
     before and including it (`main_events`) are assembled with
     `_AMS_FIGURE_OPTS` (`caption_tcignore=True`, per-caption ignore
     wrapping); events after it (`si_events`, the SI frames themselves) are
     assembled separately with `caption_tcignore=False`, since they already
     sit inside the outer SI `%TC:ignore` block opened in step 2 — see the
     toggle-desync note under §3.

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
   - Caption+label lookahead uses the shared `_parse_caption` helper
     (balanced braces; skips `\captionof`/`\captionsetup`; consumes an
     optional `[short]` argument and a following `\label{}`).
6b. **Table restructuring** — `_restructure_tables` (runs after figures):
   - Wrap bare `tabular`/`tabular*`/`tabularx` blocks in a `\begin{table}`
     float (same `placement`/`centering`/`caption_tcignore` options as
     figures; `_find_env_end` handles same-name nesting).
   - Skip tabulars already inside `\begin{table}...\end{table}`.
   - Attach an adjacent `\caption{}` — immediately **before** the tabular
     (separated only by whitespace; found via `rfind` + `_parse_caption` +
     whitespace-only-gap check) or immediately **after** it — plus the
     caption's `\label{}`. The caption is emitted **above** the tabular
     (journal convention). Previously a slide's `\captionof{table}{...}`
     became a bare `\caption{}` outside any float — a LaTeX error.
7. **List flattening** — `_flatten_lists`: `\begin{enumerate|itemize}...\end{...}`
   → prose paragraph; each `\item` becomes a sentence ending with `.`. An
   item ending in display math (`\]`, `\end{equation*?}`, `\end{align*?}`,
   `\end{gather*?}`, `\end{multline*?}`, `$$`) is checked for terminal
   punctuation **before** that closer (`_item_needs_period`), not after —
   the sentence period conventionally sits inside the math (`\,.\]`), so a
   period is only appended when the equation itself doesn't already end
   in `.`/`!`/`?`/`:`.
8. **Block environments** — `\begin{block}{Title}` → `\textbf{Title}`.
9. **Center environment** — strip tags, keep content.
10. **Whitespace cleanup** — collapse 3+ blank lines to 2.

### 4.7 Balanced brace helper

`_extract_brace_group(text, start)` — walks character by character tracking
depth; returns `(content, end_index)`.  Used throughout for: frame title
extraction, `\captionof` conversion, caption lookahead, `\frametitle` extraction,
metadata extraction from preamble.

### 4.8 AGU-oriented front matter: Key points dropped, PLS → `%\statement`

Slides written for the dual AMS/AGU pipeline carry `\section*{Key points}`
and `\section*{Plain Language Summary}` sections, which have no AMS slot.
After abstract extraction:

1. `extract_key_points(events)` (shared, `beamer_common.py`) consumes the
   Key points section and its frames; the items are **discarded**.
2. `extract_plain_language_summary(events)` (shared) consumes the PLS
   section and its frames, returning the transformed text or `None`.
3. `_build_statement_block(pls_text)` emits a fully commented `%\statement`
   block after `\maketitle`, mirroring the optional significance-statement
   stub in the official `templateV6.1.tex` (all AMS journals except BAMS;
   max 120 words). The PLS text is included as commented lines when found —
   emitted commented-out rather than live because a PLS is typically longer
   than 120 words; the author trims, then uncomments. Placeholder line when
   no PLS is present.

### 4.9 Endmatter from sentinels (`_build_endmatter`)

The AMS converter reads the **same** `%% <LABEL>_BEGIN`/`_END` comment
sentinels as the AGU converter (`extract_sentinel_block`, shared in
`beamer_common.py`; canonical labels `DATA`/`COI`/`ACKS`, with the legacy
AGU-first spellings `AGU_OPENRESEARCH`/`AGU_COI`/`AGU_ACKS` accepted
indefinitely via `_SENTINEL_ALIASES`). Sentinel blocks are
extracted from the raw source before `preprocess_body` (which strips comment
lines) and their regions removed so the wrapped frames never enter the event
list. Frame wrappers are stripped (`strip_frame_wrappers`), `\fig{}` expanded,
and content transformed with `_AMS_FIGURE_OPTS`.

AMS mapping (vs. AGU's three `\section*{}` headers):

| Sentinel | AMS output |
|----------|-----------|
| `ACKS` | `\acknowledgments` paragraph |
| `COI` | appended to the acknowledgments paragraph (AMS has no COI section) |
| `DATA` | `\datastatement` — AMS's **required** data availability statement |

Missing sentinels fall back to stubs (`_ENDMATTER_STUBS`). The block is
wrapped in `%TC:ignore`/`%TC:endignore` and emitted immediately before the
bibliography in both postamble variants (§4.5).

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
| `\section{Supplemental}` (or `Supplement…`, `Supporting Information…`) present | Endmatter + bibliography injected before it as a passthrough event (`is_si_section` shared matcher); supplemental section marker stripped; `\clearpage`, `%% SI_BEGIN`, then a manual "Supplemental material for:" title page (`_build_si_titlepage`) separate references from SI content; postamble = `\end{document}` only |
| No endmatter sentinels in source (either spelling) | Endmatter emitted with stub placeholders (`_ENDMATTER_STUBS`) |
| No `%% EMAIL:` (or legacy `%% AGU_EMAIL:`) sentinel | `\correspondingauthor{}` uses `email@institution.edu` placeholder |
| No Key points / PLS sections | Key points: nothing to drop; `%\statement` block emitted with placeholder text |
| No `\bibliography{}` in source | `_extract_bib_file` returns `'references'`; `_extract_bib_style` returns `None` (style line omitted) |
| `\author` without `\inst{}` markers | All authors share affiliation `a` with the single `\institute{}` text (Beamer semantics: one institute applies to all authors) |
| No `\institute{}` in source (and no `\inst{}`) | All authors share one `Department, Institution, City, State` placeholder |
| Bare `tabular` with `\captionof{table}{...}` before or after it | Wrapped in `\begin{table}[h]` with caption (TC-ignored) above the tabular and `\label{}` attached (`_restructure_tables`) |
| `tabular` already inside `\begin{table}` | Passed through unchanged |
| `\section{Abstract}` | Consumed into `\abstract{}` preamble block; removed from body |
| `\section*{...}` | Captured as section event (same as `\section{...}`); appears in output as-is |
| `\subsection{...}` / `\subsection*{...}` outside a frame | Captured as a `section` event (same regex, `(?:sub)?section`); previously unmatched and silently dropped from output. Passes through verbatim — no promotion/demotion to `\section` |
| `\item` whose text ends in a display-math block that already ends in `\,.` (or other terminal punctuation) before `\]`/`\end{equation}`/`$$` | No period appended after the closer — `_item_needs_period` checks punctuation before the closer, not the literal last character. Previously produced a doubled period (`\,.\n\].`) |

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
| 2026-07-04 | Endmatter added (template-parity audit): AMS converter now reads the same `%% AGU_*` sentinels as AGU — `OPENRESEARCH` → `\datastatement` (required by AMS), `ACKS` → `\acknowledgments`, `COI` folded into acknowledgments; `%TC:ignore`-wrapped, before the bibliography; stubs when absent. Previously sentinel frames leaked into the body as bare unlabeled paragraphs | Yes |
| 2026-07-04 | Key points consumed and dropped; Plain Language Summary consumed and emitted as commented `%\statement` block after `\maketitle` (templateV6.1.tex's optional significance statement). Previously both leaked into the body as `\section*{}` sections | Yes |
| 2026-07-04 | `%% AGU_EMAIL:` sentinel now honored (shared `extract_email` in `beamer_common.py`); previously AMS always emitted the placeholder | Yes |
| 2026-07-04 | Shared: SI section matching unified as `is_si_section` in `beamer_common.py` (`supplement` \| `supporting information`, case-insensitive); AMS previously matched `supplement`, AGU `supplemental` — a `\section{Supplement}` deck reordered in AMS but not AGU | Yes |
| 2026-07-04 | Shared: `extract_sentinel_block`, `strip_frame_wrappers`, `extract_email`, `extract_key_points`, `extract_plain_language_summary` moved from `beamer_to_agu.py` to `beamer_common.py` (KP extractor now returns `[]` and PLS extractor `None` when absent; AGU applies its own defaults) | Yes |
| 2026-07-04 | Shared: sentinel names made generic — canonical `DATA`/`COI`/`ACKS` and `%% EMAIL:` with legacy `AGU_OPENRESEARCH`/`AGU_COI`/`AGU_ACKS`/`%% AGU_EMAIL:` accepted indefinitely (`_SENTINEL_ALIASES` in `beamer_common.py`); internal label `OPENRESEARCH` renamed `DATA`. Output byte-identical for legacy decks (verified against pre-change code) | Yes |
| 2026-07-07 | Shared: `_restructure_tables` added (pipeline-gap audit) — bare `tabular`/`tabular*`/`tabularx` wrapped in a `\begin{table}` float with adjacent caption (before or after the tabular) and label attached, caption emitted above; previously `\captionof{table}` became a bare `\caption{}` outside any float (LaTeX error). Caption+label lookahead factored into shared `_parse_caption` (also used by `_restructure_figures`; figure output byte-identical). AMS TC-ignores table captions like figure captions | Yes |
| 2026-07-07 | Shared: no-`\inst{}` fallback fixed — all authors now share the single `\institute{}` text (affiliation `a`) instead of the real institute being silently replaced by per-author placeholders; placeholder only when `\institute{}` is absent too. Output byte-identical for `\inst{}`-marked decks (verified on both example decks) | Yes |
| 2026-07-08 | `convert()` now splits the event list at the `%% SI_BEGIN` marker and assembles the SI portion with `caption_tcignore=False`; previously SI figures/tables got the same per-caption `%TC:ignore`/`%TC:endignore` wrapping as main-body ones, which desynced texcount's ignore toggle from the outer SI ignore block and produced a bogus `\begin{document}`/`\end{figure}` environment-mismatch error plus a stray trailing `%TC:endignore` (real-world repro: `hdd-slides-v5.tex`, 22 figures + SI). Verified with a toggle/environment-stack simulation and a clean `texcount` run, both on the full manuscript and after `extract_main.py --no-si` | Yes |
| 2026-07-13 | Added `_build_si_titlepage`: a manual "Supplemental material for:" title page (title/authors/affiliations/corresponding author, styled after `\@maketitle`) now emitted after `%% SI_BEGIN`/`%TC:ignore`, before the first SI figure — previously the SI began right after the bibliography with zero visual indication of the transition. `\maketitle` cannot be called twice (self-destructs in `ametsocV6.1.cls`), so the block is hand-built rather than reusing it. Appendices remain out of scope (author-driven `\appendix`, not this converter). Verified: compiled clean with `pdflatex`+`bibtex` against the real AMS class (screenshot-matched to a published example), `texcount` balance clean, `extract_main.py` correctly strips the whole title page for a main-only submission and re-closes the orphaned `%TC:ignore` | Yes |
| 2026-07-13 | Added `_extract_journal_name` + `--journal` CLI flag, mirroring AGU's `%\journalname{}`/`--journal` mechanism for coherence between the two converters. Initial implementation made `\journal{}` live (uncommented) when a key was supplied — caught by a real `pdflatex` compile against `ams/ametsocV6.1.cls` before commit: `\journal{}` is undefined in that standalone class (zero definitions found), raising "Undefined control sequence" and leaking the key text into the typeset body. Fixed to keep the directive always commented (`% \journal{<key>}`). **Reverted later same day** (see next row) once the underlying premise turned out to be false. | Yes, then reverted |
| 2026-07-13 | Reverted the above: removed `_extract_journal_name`, the `journal` param/CLI flag, and the commented `\journal{}` placeholder entirely (also reverted the `--journal` threading briefly added to `convert.py`'s `ams` branch, and the sentinel line added to `examples/starter-slides.tex`). Root cause, found while investigating why `--journal` had no visible effect: `\journal{}` isn't merely undefined in *this* standalone class — AMS deleted the per-journal-name macro from `ametsoc.cls` entirely in package v5.0 (2020; `ams/AMS LaTeX Package V6.1/README.txt`: "Removed option to select journal name for two-column"), and an even older per-journal command (`\bams` et al., pre-2014) is also long gone. Neither the current `.cls` nor `templateV6.1.tex` has any journal-selection command to eventually target, commented or otherwise — unlike AGU's `\journalname{}`, which is real and live. A commented placeholder with nothing to uncomment into was judged not worth keeping; user confirmed via explicit choice ("Remove entirely") over keeping it as an inert placeholder or a plain non-macro comment. | Yes |
| 2026-08-08 | Shared: `_flatten_lists` doubled the sentence period when an `\item` ended in display math that already closed with `\,.` before `\]` (e.g. a hypothesis equation) — the old check only looked at the item's literal last character (`\]`), which is never terminal punctuation, so it always appended a stray `.` after the closer. Added `_item_needs_period` (with `_DISPLAY_MATH_CLOSE_RE` matching `\]`, `\end{equation*?}`, `\end{align*?}`, `\end{gather*?}`, `\end{multline*?}`, `$$`) to check punctuation before the closer instead. Verified against the reported repro and against non-math/no-trailing-period cases (behavior unchanged there) | Yes |
| 2026-08-20 | `_build_preamble` now emits `\usepackage[T1]{fontenc}` as the first line after `\documentclass`. Root cause: `ametsocV6.1.cls` loads `mathptmx`/`newtxtext` (Times-like PostScript fonts) but never loads `fontenc` itself; under the default OT1 encoding, non-ASCII text-mode commands like `\l` have no OT1-encoded glyph in the newtx font and silently fall back to a mismatched Computer Modern substitute mid-word, breaking spacing (e.g. a `P{\l}otka` author surname rendered as two words, "P lotka", instead of "Płotka"). Reproduced and confirmed by compiling a minimal manuscript against the real `ametsocV6.1.cls` + `ametsocV6.bst` with and without T1 (log showed `Font shape 'OT1/ntxtlf/m/n' will be [substituted]`); fix verified to correct the rendering. AGU's `agujournal2019.cls` was checked and does not load Times fonts by default (newtxtext commented out there), so `beamer_to_agu.py` was left unchanged. | Yes |
| 2026-08-22 | Shared: `_restructure_figures`' pass-through branch for a pre-existing `\begin{figure}...\end{figure}` block called `re.search(r'\\end\{figure\}', text, fig_begin)` — the third positional arg to `re.search` is `flags`, not a start position (only a compiled pattern's `.search(string, pos)` takes one), so `fig_begin` (a large int match offset) was being interpreted as a flags bitmask. For most offsets this was silently harmless, but when its bits happened to collide with `re.LOCALE`, Python raises `ValueError: cannot use LOCALE flag with a str pattern`. Real-world repro: `enso-global-temperature-slides-v7.tex`, which has a hand-written `\begin{figure}` block (the composite-maps frame) at an offset that triggered the collision; the otherwise-identical v6 deck didn't hit a bad offset. Fixed by compiling `fig_end_re = re.compile(r'\\end\{figure\}')` once and calling `fig_end_re.search(text, fig_begin)`. Output byte-identical for both example decks and for a full v6/v7 conversion; `tests/run_tests.py` passes. **Regression test added same day** (`check_restructure_figures_passthrough_unit`, a `code-review high` finding — the original fix shipped with no coverage of the exact crashing branch): a fixture with `\begin{figure}` at offset 4 (`re.LOCALE`'s bit set), confirmed to raise the original `ValueError` when run against the pre-fix code, asserts the pass-through block is unchanged and a following bare `\includegraphics` is still wrapped | Yes |
| 2026-08-22 | Fixed duplicate `\bibliography{}` when the source places it outside a frame: `build_event_list` already captures it as a `passthrough` event, and the converter separately injects an explicit copy before/after the SI boundary — previously the passthrough-filter (dropping the parsed copy) ran only inside the `if supp_idx is not None:` branch, so a no-SI manuscript with an outside-frame `\bibliography{}` got two copies and bibtex aborted on the repeated `\bibdata` entry (ultrareview finding, ~5-10 min cloud review of commit b3863d0). Hoisted the filter above the branch so it always runs. Same-day fix applied to `beamer_to_agu.py` (see its sync log). **Regression test added same day**: `check_manuscript` now asserts exactly one `\bibliography{refs}` in `tests/test_input.tex`'s output (already places the bibliography outside a frame — the SI-present branch, already covered by the pre-existing filter); `check_no_si_paths` extended with a `\bibliography{}` in `_NO_SI_DECK` and a `beamer_to_ams.py` no-SI conversion pass asserting the count — confirmed to fail (count=2) against the pre-fix code | Yes |
