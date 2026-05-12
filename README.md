# tex-utility

Tools for converting Beamer slide decks to journal manuscript drafts,
and for splitting compiled PDFs into main text and SI files.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/convert.py` | Unified CLI — converts Beamer to AMS or AGU manuscript |
| `scripts/beamer_to_ams.py` | AMS converter (can also be run directly) |
| `scripts/beamer_to_agu.py` | AGU converter (can also be run directly) |
| `scripts/beamer_common.py` | Shared Beamer parsing (imported by both converters) |
| `scripts/split_pdf.py` | Split a compiled PDF into main text and SI at a given page |

### Class files

| Journal | Class | Location |
|---------|-------|----------|
| AMS | `ametsocV6.1.cls`, `ametsocV6.bst` | `ams/` |
| AGU | `agujournal2019.cls`, `agutexSI2019.cls` | `agu/` |

---

## Usage

### Beamer → manuscript

```bash
# Unified CLI (recommended)
python scripts/convert.py --format ams slides.tex
# → slides_manuscript.tex

python scripts/convert.py --format agu slides.tex
# → slides_agu.tex

python scripts/convert.py --format agu slides.tex --journal "Geophysical Research Letters"

# Explicit output path
python scripts/convert.py --format ams slides.tex draft_v1.tex
```

The individual converter scripts can also be run directly and behave identically:

```bash
python scripts/beamer_to_ams.py slides.tex
python scripts/beamer_to_agu.py slides.tex
```

### Compiling the output

```bash
# AMS
TEXINPUTS=./ams/: pdflatex slides_manuscript.tex
bibtex slides_manuscript
TEXINPUTS=./ams/: pdflatex slides_manuscript.tex
TEXINPUTS=./ams/: pdflatex slides_manuscript.tex

# AGU
TEXINPUTS=./agu/: pdflatex slides_agu.tex
bibtex slides_agu
TEXINPUTS=./agu/: pdflatex slides_agu.tex
TEXINPUTS=./agu/: pdflatex slides_agu.tex
```

### Splitting a PDF

```bash
python scripts/split_pdf.py paper.pdf SPLIT_PAGE
```

`SPLIT_PAGE` is 1-based and is the **first page of the second output file**.

```bash
# Split paper.pdf: pages 1–17 → paper-main.pdf, pages 18–end → paper-SI.pdf
python scripts/split_pdf.py paper.pdf 18

# Custom output names
python scripts/split_pdf.py paper.pdf 18 main.pdf si.pdf
```

Requires `pypdf` (`pip install pypdf`).

---

## What the converters do

**From the Beamer preamble:**
- `\title[short]{Long title}` → manuscript title
- `\author{Name\inst{1} and Name\inst{2}}` → author list with affiliations
- `\institute{\inst{1} Affil one \and \inst{2} Affil two}` → affiliation block

**From the body:**
- `\section{}` and `\section*{}` commands become manuscript headings (labels preserved)
- Frame titles are dropped; frame content becomes prose paragraphs
- `\section{Abstract}` and its frames are extracted into the abstract block
- `\includegraphics` is wrapped in `\begin{figure}` with `\caption` and `\label`
- `\captionof{figure}{...}` is converted to `\caption{...}`
- `\fig{path}` (Beamer shorthand macro) expanded to `\includegraphics{path}`
- `enumerate`/`itemize` lists are flattened to prose sentences
- Beamer overlay and layout commands (`\pause`, `\only`, `\alert`, `\columns`, etc.) are stripped
- `\renewcommand\thetable`, `\setcounter{table}`, `\clearpage` passed through verbatim

**AMS-specific:**
- Author affiliations use `\aff{a}`, `\aff{b}`, … (letter-based)
- `\abstract{...}` command form
- `natbib` / `\citep` / `\citet` — kept as-is
- `\bibliographystyle{...}` and `\bibliography{...}` extracted from source and
  injected into the postamble (works regardless of whether they appear inside or outside a frame)

**AGU-specific:**
- Author affiliations use `\affil{1}`, `\affil{2}`, … (number-based)
- `\begin{abstract}...\end{abstract}` environment
- `\section*{Plain Language Summary}` and its frames extracted into the preamble PLS block
- `apacite` — `\citet{key}` → `\citeA{key}`, `\citep{key}` → `\cite{key}`
- `\bibliographystyle` is stripped (the class loads `apacite` automatically)
- `\bibliography{...}` file name extracted from source and appended after end-matter
- End-matter (Open Research, Conflict of Interest, Acknowledgments) extracted from
  comment-sentinel-wrapped frames (see *AGU end-matter sentinels* below); placed before
  any `\section{Supplemental…}` in the output; per-section stubs used when sentinels absent
- Display math wrapped in `\begin{linenomath*}...\end{linenomath*}` for line numbering
- Figures use `\noindent\includegraphics[width=\textwidth]{...}` (no `\centering`)
- Publication-unit guidance comment inserted between `\journalname{}` and `\begin{document}`
- `%TC:ignore` / `%TC:endignore` markers for `texcount`: title+key-points block ignored,
  PLS ignored, endmatter+bibliography+SI ignored; abstract and body are counted

---

## After conversion

Things to fill in before sending to coauthors:

**AMS:**
- Corresponding author email in `\correspondingauthor{}`
- Uncomment `\journal{jcli}` (or the relevant code) if submitting via the full AMS package

**AGU:**
- Journal name in `\journalname{}` — default is `JGR: Atmospheres`
- Corresponding author email — add `%% AGU_EMAIL: you@institution.edu` anywhere in
  the Beamer preamble; the converter inserts it into `\correspondingauthor{}{}` automatically
- Three key points in `\begin{keypoints}` (max 140 characters each)
- Plain Language Summary
- If sentinels were used: review extracted Open Research, COI, Acknowledgments text
- If sentinels were not used: fill in the stub placeholders for those three sections
- Run `texcount <output>_agu.tex` to get a word count; `%TC:ignore` markers are already
  in place to exclude title metadata, key points, PLS, and endmatter per AGU rules

---

## Tips for Beamer source formatting

These habits make the converted manuscript cleaner.

### Metadata

Use `\inst{N}` markers on every author — without them the script assigns
sequential affiliations and may not match your intended grouping:

```latex
\author[]{Jane Smith\inst{1} and John Doe\inst{1,2}}
\institute[]{%
  \inst{1} Department of Geosciences, University A, City, State \and
  \inst{2} Institute B, City, State}
```

Multi-affiliation authors (`\inst{1,2}`) are not yet parsed; for now list
the primary affiliation only and edit the output by hand.

### Abstract frame

Put the abstract in a dedicated section immediately after `\begin{document}`:

```latex
\section{Abstract}
\begin{frame}{Abstract}
  \begin{enumerate}
  \item First sentence / motivation.
  \item Key method or data.
  \item Main finding.
  \item Implication.
  \end{enumerate}
\end{frame}
```

The converter extracts this into the manuscript abstract block.
Each `\item` becomes a sentence; a period is appended unless the item
already ends with `.`, `!`, `?`, or `:`.

### Sections and frames

Beamer `\section{}` commands become manuscript `\section{}` headings.
Frame titles are dropped, so the section name carries all the structure.
Group logically related frames under one section:

```latex
\section{Data}

\begin{frame}{Observations}
  ...
\end{frame}
\begin{frame}{Model output}
  ...
\end{frame}
```

### Figures

The converter wraps bare `\includegraphics` in a figure environment.
For the cleanest result, place each figure in its own frame and follow
it immediately with `\captionof{figure}{...}` and an optional `\label{}`:

```latex
\begin{frame}{Results}
  \includegraphics[width=0.8\linewidth]{plots/fig1.pdf}
  \captionof{figure}{Caption text. \label{fig:results}}
\end{frame}
```

`\captionof` (from the `caption` package) is the reliable way to attach a
caption inside a Beamer `columns` or `minipage` environment. The converter
converts it to `\caption{}` in the output.

Two side-by-side images in the same frame are grouped into one figure
environment with a shared caption:

```latex
\includegraphics[width=0.49\linewidth]{plots/fig1a.pdf}
\includegraphics[width=0.49\linewidth]{plots/fig1b.pdf}
\captionof{figure}{(a) Left panel. (b) Right panel. \label{fig:pair}}
```

Avoid wrapping `\includegraphics` in explicit `\begin{figure}` inside
Beamer frames — the converter passes existing figure environments through
unchanged, which is correct but means your Beamer captions won't migrate.

### Lists → prose

Both `enumerate` and `itemize` lists are flattened to prose paragraphs.
Write items as complete, self-contained sentences for the best result:

```latex
% Good — each item is a full sentence
\begin{itemize}
  \item The forecast skill peaks at lead week 2.
  \item Skill decreases rapidly beyond week 3.
\end{itemize}

% Avoid — fragments that read oddly when joined
\begin{itemize}
  \item week 2 peak
  \item rapid skill drop beyond week 3
\end{itemize}
```

AGU does not allow bulleted lists; all lists are converted to prose
regardless of whether they are `enumerate` or `itemize`.

### Citations

Use `natbib` commands in the Beamer source (`\citet`, `\citep`).
The AMS converter leaves these unchanged. The AGU converter remaps them:

| In Beamer source | AMS output | AGU output |
|-----------------|-----------|-----------|
| `\citet{key}` | `\citet{key}` | `\citeA{key}` |
| `\citep{key}` | `\citep{key}` | `\cite{key}` |
| `\citep[see][]{key}` | `\citep[see][]{key}` | `\cite<see>[]{key}` |
| `\citet[][their Fig.~2]{key}` | unchanged | `\citeA[their Fig.~2]{key}` |

### Bibliography

Place `\bibliographystyle{...}` and `\bibliography{...}` anywhere in the
source — inside or outside a frame. Both converters extract these from the
raw source text, so their location doesn't matter.

```latex
\begin{frame}[allowframebreaks]{References}
  \bibliographystyle{ametsocV6}
  \bibliography{references}
\end{frame}
```

### AGU end-matter sentinels

The AGU converter extracts Open Research, Conflict of Interest, and
Acknowledgments from normal Beamer frames marked with comment sentinels.
The frames compile and render as slides; the comment lines are invisible
to Beamer (no nav-bar entries, no `\section*` clutter).

```latex
%% AGU_OPENRESEARCH_BEGIN
\begin{frame}{Open Research}
  \begin{itemize}
    \item Data archived at \url{https://zenodo.org/...} (DOI: ...).
    \item Code at \url{https://github.com/...}.
  \end{itemize}
\end{frame}
%% AGU_OPENRESEARCH_END

%% AGU_COI_BEGIN
\begin{frame}{Conflict of Interest}
  The authors declare no conflicts of interest.
\end{frame}
%% AGU_COI_END

%% AGU_ACKS_BEGIN
\begin{frame}{Acknowledgments}
  Supported by NSF grant AGS-0000000. We thank ...
\end{frame}
%% AGU_ACKS_END
```

- The converter strips the `\begin{frame}{...}` / `\end{frame}` wrappers and
  injects the required AGU header (`\section*{Open Research Section}`,
  `\section*{Conflict of Interest}`, `\acknowledgments`).
- `\bibliography{...}` stays in the References frame as usual; the converter
  appends it after the acknowledgments in the manuscript.
- Any missing sentinel block falls back to a placeholder stub.
- Sentinels can appear anywhere in the source file.

### Things that are stripped

The following are removed silently — no action needed in the source:

- `\usetheme`, `\usecolortheme`, `\setbeamercolor`, `\setbeamerfont`, etc.
- `\pause`, `\only<>{}`, `\visible<>{}`, `\uncover<>{}`, `\onslide<>{}`
- `\alert{x}` → `x`; `\structure{x}` → `x`; `\textcolor{c}{x}` → `x`
- `\columns`, `\column{...}`, `\begin{minipage}{...}` (content kept)
- `\begin{block}{Title}` → `\textbf{Title}` (content kept)
- Font size commands: `\tiny`, `\scriptsize`, `\footnotesize`, `\small`, `\large`, etc.
- `\centering`, `\vspace{...}`, `\hspace{...}`, `\medskip`, `\vfill`, etc.
- `\setlength`, `\addtolength`, `\renewcommand` (except `\thefigure` and `\thetable`)
- `\bibliographystyle{...}` and `\bibliography{...}` when inside a frame body
  (the values are extracted separately and injected into the postamble)
- Comment lines (`% ...`); `\%` is preserved

---

## Project structure

```
tex-utility/
  scripts/
    convert.py              Unified CLI (--format ams|agu)
    beamer_to_ams.py        AMS converter
    beamer_to_agu.py        AGU converter
    beamer_common.py        Shared Beamer parsing
    split_pdf.py            PDF splitter (main text / SI)
  specs/
    beamer_to_ams_spec.md   AMS converter behavioral spec
    beamer_to_agu_spec.md   AGU converter behavioral spec
  tests/
    run_tests.py            Regression test suite
    test_input.tex          Test Beamer source
  examples/                 Example Beamer sources and converted outputs
  ams/
    ametsocV6.1.cls
    ametsocV6.bst
  agu/
    agujournal2019.cls
    agutexSI2019.cls
    agujournaltemplate.tex
    si_template_2019.tex
```
