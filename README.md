# tex-utility

Tools for turning a Beamer outline deck into an AMS or AGU manuscript draft,
packaging that draft for submission (main-text `.tex` + per-figure PDFs +
separate SI PDF), and maintaining the shared bibliography in `~/tex/bib`
(AMS-abbreviated copy, missing DOIs).

**Doing it:** Quick reference → Usage → After conversion → Tips for Beamer
source formatting.
**Reference:** Workflow · What the converters do · What extract_main.py does
· Project structure.

---

## Quick reference

For when it's been a few months. Paths assume the repo is at
`~/claude/tex-utility`; run from the directory holding your deck.

```bash
U=~/claude/tex-utility
J=agu            # or ams

# 1. Convert the deck. Name the output explicitly -- the default is
#    slides_agu.tex / slides_manuscript.tex, and the stem you pick here
#    names everything downstream (<stem>.pdf, <stem>_SUBMIT/, ...).
python $U/scripts/convert.py --format $J slides.tex main-and-si.tex
#    AGU only: --journal "Geophysical Research Letters"  (default: JGR: Atmospheres)

# 2. Compile (class files live in $U/agu or $U/ams)
TEXINPUTS=$U/$J/: pdflatex main-and-si
bibtex main-and-si
TEXINPUTS=$U/$J/: pdflatex main-and-si
TEXINPUTS=$U/$J/: pdflatex main-and-si

# 3. SI PDF: open main-and-si.pdf, note the page where the SI starts (e.g. 18)
python $U/scripts/split_pdf.py main-and-si.pdf 18
#    -> main-and-si-main.pdf (discard), main-and-si-SI.pdf (upload)

# 4. Main-text package (never modifies main-and-si.tex). Also copies the
#    class file in, test-compiles main.pdf with TEXINPUTS unset, and deletes
#    the build leftovers. Read its last lines: "0 undefined ref(s),
#    0 undefined citation(s)" means the folder is ready.
python $U/scripts/extract_main.py main-and-si.tex
#    -> main-and-si_SUBMIT/main.tex, fig1.pdf, ..., <class>.cls, main.pdf
#    no SI in the deck? add --no-si
```

Upload from `main-and-si_SUBMIT/`: `main.tex`, `fig*.pdf`, the `.cls`
(`main.pdf` is for your own check). Upload `main-and-si-SI.pdf` separately.

Reminders:

- **Starting a new deck?** Copy `examples/starter-slides.tex` — it already has
  the front-matter sections, end-matter sentinels, and `%% EMAIL:` line the
  converters look for. Its Appendix and `\section{Supplemental}` blocks are
  commented out: uncomment the SI section if the paper has one, otherwise
  step 4 needs `--no-si`. For AMS, change its `\bibliographystyle{plainnat}`
  to `ametsocV6` (see *Bibliography*).
- **After converting**, work through the checklist in *After conversion*
  (key points, PLS, email, word count, ...).
- **Bibliography upkeep** lives in `~/tex/bib`: `make` regenerates
  `all_ams.bib`; `make doi-candidates` / `make doi-apply` add missing DOIs.
  See *Bibliography tools*.
- **Changed a script?** Run `python tests/run_tests.py` and update the
  matching `specs/*.md`.

---

## Usage

Scripts live in `scripts/`. Run them with a Python that has `pypdf` and
`requests` (e.g. the `pangeo-2025` env). Each one accepts `--help`.

### convert.py — Beamer deck → manuscript

```bash
python scripts/convert.py --format ams|agu slides.tex [out.tex] [--journal NAME]
```

- Default output: `slides_manuscript.tex` (AMS) or `slides_agu.tex` (AGU).
- `--journal` is AGU only (sets `\journalname{}`; default `JGR: Atmospheres`).
  AMS has no per-journal setting; it was removed from the class in 2020.
- Compile with the class directory on `TEXINPUTS` (`ams/` or `agu/`), as in
  *Quick reference*, then work through *After conversion*.
- `beamer_to_ams.py` / `beamer_to_agu.py` do the same thing if run directly.

### split_pdf.py — cut out the SI PDF

```bash
python scripts/split_pdf.py main-and-si.pdf SPLIT_PAGE [main.pdf si.pdf]
```

- `SPLIT_PAGE` is the first page of the SI (1-based).
- Default outputs: `<stem>-main.pdf` and `<stem>-SI.pdf`.

### extract_main.py — build the submission folder

```bash
python scripts/extract_main.py main-and-si.tex [options]
```

Compile `main-and-si.tex` first: the script reads its `.aux` and `.bbl`. It
never writes to the input. Output goes to `<stem>_SUBMIT/`: `main.tex`,
`fig1.pdf`, …, the journal `.cls`, and `main.pdf` (for checking only; don't
upload it). Its last lines tell you whether the folder is ready:
`Compiled main.pdf (…): 0 undefined ref(s), 0 undefined citation(s)`.
If `main.tex` doesn't compile, it prints the LaTeX error and exits 1.

| Option | Use when |
|--------|----------|
| `--no-si` | the paper has no SI |
| `--outdir DIR` | you want output somewhere other than `<stem>_SUBMIT/` |
| `--bbl FILE`, or a second positional `.aux` | they aren't `<stem>.bbl` / `<stem>.aux` |
| `--no-bib` | you want `\bibliography{}` left live instead of inlined |
| `--no-figures` | you want to keep the original `\includegraphics` paths |
| `--no-compile` | you want to skip the test compile |
| `--keep-intermediates` | you're debugging the figure or compile step |

Gotchas:
- Rerunning into the same folder doesn't delete old files. If you dropped a
  figure, delete the stale `figN.pdf`.
- The test compile ignores your `TEXINPUTS`, as the publisher would. A
  package found only through `TEXINPUTS` makes it fail: put a copy next to
  `main-and-si.tex` and rerun.

Details: *What extract_main.py does*.

### make_single_figure.sh — one PDF per figure

`extract_main.py` runs this for you. To run it on its own:

```bash
bash scripts/make_single_figure.sh manuscript.tex [NFIGS]   # → fig1.pdf, fig2.pdf, …
```

Needs `pdflatex` and `pdfcrop`. It uses the plain `article` class, so no
journal class is needed. Commented-out figure blocks are skipped.

### Bibliography tools — `~/tex/bib`

These maintain the shared bibliography, not a single paper. `all.bib` is the
master, with full journal names (what AGU wants). `all_ams.bib` is generated
from it with AMS abbreviations.

```bash
cd ~/tex/bib
make                  # regenerate all_ams.bib from all.bib + journals.csv
make doi-candidates   # query Crossref -> doi/doi_accept.tsv, doi/doi_review.tsv
                      # review: delete wrong rows from doi_accept.tsv,
                      #         paste good rows in from doi_review.tsv
make doi-apply        # insert those DOIs into all.bib (dated backup first)
```

- New journal in `all.bib`? Add a `full,ams` row to `journals.csv` first,
  or the AMS copy keeps the full name (it's listed on stderr;
  `bib_for_ams.py --strict` makes it an error).
- `doi-candidates` only auto-accepts a match when the title similarity is
  ≥ 0.95, the year is within ±1, and the first-author surname matches.
  Crossref replies are cached in `doi/`, so a rerun only queries new
  entries.
- Direct use: `bib_for_ams.py all.bib journals.csv -o all_ams.bib`;
  `bib_add_doi.py find all.bib --outdir doi --mailto ADDR`, then
  `bib_add_doi.py apply all.bib doi/doi_accept.tsv`.

---

## After conversion

Things to fill in before sending to coauthors:

**AMS:**
- Corresponding author email — add `%% EMAIL: you@institution.edu` anywhere in
  the Beamer preamble (same sentinel as AGU); placeholder is used if absent
- If sentinels were used: review the extracted `\acknowledgments` (COI text is
  appended to it) and `\datastatement`; otherwise fill in their stub placeholders
- Significance statement (optional): trim the commented `%\statement` block after
  `\maketitle` to 120 words and uncomment it, or delete it
- Check `\bibliographystyle{}` is `ametsocV6` — the deck's style is copied
  verbatim, so a `plainnat` deck needs fixing here (or in the deck)
- Run `texcount <output>_manuscript.tex` to get a word count; `%TC:ignore` markers are
  already in place to exclude title/authors/affiliation/abstract, captions,
  references, and SI per AMS's word-limit rule. Acknowledgments, the data
  statement, and appendixes are **counted**, as AMS's limit requires

**AGU:**
- Journal name in `\journalname{}` — default is `JGR: Atmospheres`
- Corresponding author email — add `%% EMAIL: you@institution.edu` anywhere in
  the Beamer preamble; the converter inserts it into `\correspondingauthor{}{}` automatically
- Three key points in `\begin{keypoints}` (max 140 characters each)
- Plain Language Summary
- If sentinels were used: review extracted Open Research, COI, Acknowledgments text
- If sentinels were not used: fill in the stub placeholders for those three sections
- Run `texcount <output>_agu.tex` to get a word count; `%TC:ignore` markers are already
  in place to exclude title metadata, key points, PLS, and endmatter per AGU rules

---

## Tips for Beamer source formatting

These habits make the converted manuscript cleaner. A barebones deck with
all of them already in place is at `examples/starter-slides.tex`.

> **Downstream dependent:** the `/new-project` scaffolding template at
> `~/claude/templates/research/tex/slides.tex` is written to these
> conventions (front-matter sections, endmatter sentinels, `%% EMAIL:`),
> and `examples/starter-slides.tex` is its token-free mirror. If the
> converter conventions change — sentinel names, section-title matching,
> metadata directives — update both files.

### Metadata

Use `\inst{N}` markers on every author — without them every author gets the
whole `\institute{}` text as a single shared affiliation:

```latex
\author[]{Jane Smith\inst{1} and John Doe\inst{2}}
\institute[]{%
  \inst{1} Department of Geosciences, University A, City, State \and
  \inst{2} Institute B, City, State}
```

**Give each author exactly one `\inst{N}`.** Multi-affiliation markers
(`\inst{1,2}`) are not supported, and they do more than lose the second
affiliation: the comma is read as an author separator, so
`John Doe\inst{1,2}` becomes two garbled "authors" (`John Doe\inst{1` and
`2}`). List the primary affiliation in the deck and add the second one to
the converted manuscript by hand.

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

`\subsection{}` is also passed through (unchanged, at its own level) for a
second level of structure within a section:

```latex
\section{Data}

\subsection{Observations}
\begin{frame}{...}
  ...
\end{frame}

\subsection{Model output}
\begin{frame}{...}
  ...
\end{frame}
```

### Appendix

A `\section{}` whose title starts with "Appendix" opens the appendix.
Everything from there up to the SI section (or the end of the deck) becomes
appendix content — `\subsection{}`, frames, and figures all work exactly as
in a normal section:

```latex
\section{Appendix}

\begin{frame}{Extended derivation}
  ...
\end{frame}
```

Each `\section{}` after that opens a new, auto-lettered appendix (A, B, …).
A colon/dash after "Appendix" (and an optional letter) is stripped to give
the appendix its own title, so both of these work:

```latex
\section{Appendix A: Extended derivation}
...
\section{Statistical significance details}   % becomes Appendix B
```

A single appendix is unlettered in AMS output (bare `\appendix`) but always
"Appendix A" in AGU output — `agujournal2019.cls` has no unlettered form.
The appendix is placed per each journal's own template order (AMS:
acknowledgments → data statement → **appendix** → references; AGU: body →
**appendix** → acknowledgments/data statement → references), and it counts
toward the word limit like the rest of the main text — unlike the SI, it is
never `%TC:ignore`-wrapped. It is also retained by `extract_main.py`'s
main/SI split, since it's part of the main text.

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

The AGU converter drops the style (the class loads `apacite`), but the AMS
converter copies it verbatim — so if you will convert to AMS, use
`ametsocV6` in the deck (Beamer compiles fine with it; `ams/` must be on
`TEXINPUTS`/`BSTINPUTS`) or fix the style in the output. For the AMS
abbreviated journal names, point `\bibliography{}` at `all_ams` rather than
`all` (see *Bibliography tools*).

### End-matter sentinels

Both converters extract data availability, Conflict of Interest, and
Acknowledgments from normal Beamer frames marked with comment sentinels.
The frames compile and render as slides; the comment lines are invisible
to Beamer (no nav-bar entries, no `\section*` clutter).

```latex
%% DATA_BEGIN
\begin{frame}{Data Availability}
  \begin{itemize}
    \item Data archived at \url{https://zenodo.org/...} (DOI: ...).
    \item Code at \url{https://github.com/...}.
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
  Supported by NSF grant AGS-0000000. We thank ...
\end{frame}
%% ACKS_END
```

- The converter strips the `\begin{frame}{...}` / `\end{frame}` wrappers and
  injects the journal's header. AGU: `\section*{Open Research Section}`,
  `\section*{Conflict of Interest}`, `\acknowledgments`. AMS:
  `\datastatement` (from `DATA`), `\acknowledgments` (from `ACKS`,
  with the `COI` text appended — AMS has no COI section).
- Legacy spellings from when the sentinels were AGU-only are accepted
  indefinitely: `AGU_OPENRESEARCH` (= `DATA`), `AGU_COI`, `AGU_ACKS`, and
  `%% AGU_EMAIL:` (= `%% EMAIL:`). Existing decks need no changes.
- `\bibliography{...}` stays in the References frame as usual; the converter
  appends it after the acknowledgments in the manuscript.
- Any missing sentinel block falls back to a placeholder stub.
- Sentinels can appear anywhere in the source file.

### Things that are stripped

The following are removed silently — no action needed in the source:

- `\usetheme`, `\usecolortheme`, `\setbeamercolor`, `\setbeamerfont`, etc.
- `\pause`; `\only<>{}`, `\visible<>{}`, `\uncover<>{}`, `\onslide<>{}`
  (braced form only — see *Not handled* below)
- `\alert{x}` → `x`; `\structure{x}` → `x`; `\textcolor{c}{x}` → `x`
- `\columns`, `\column{...}`, `\begin{minipage}{...}` (content kept)
- `\begin{block}{Title}` → `\textbf{Title}` (content kept)
- Font size commands: `\tiny`, `\scriptsize`, `\footnotesize`, `\small`, `\large`, etc.
- `\centering`, `\vspace{...}`, `\hspace{...}`, `\medskip`, `\vfill`, etc.
- `\setlength`, `\addtolength`, `\renewcommand` (except `\thefigure` and `\thetable`)
- `\bibliographystyle{...}` and `\bibliography{...}` when inside a frame body
  (the values are extracted separately and injected into the postamble)
- Comment lines (`% ...`); `\%` is preserved

### Not handled

These pass through into the manuscript as literal text — avoid them in the
deck, or clean them up in the output:

- Overlay specs on anything other than the braced commands above:
  `\item<2->` leaves `<2->` in the prose, `\textbf<2>{x}` stays as is.
- The bare switch form `\onslide<3->` (no braces) is left in place.
- `\inst{1,2}` multi-affiliation markers (see *Metadata*).

---

## Workflow

```
slides.tex   (Beamer deck)
    |
    |  convert.py --format ams|agu slides.tex main-and-si.tex
    v
main-and-si.tex   (main text + SI in one file; %% SI_BEGIN marks the boundary)
    |
    |  pdflatex (x2-3) + bibtex
    v
main-and-si.pdf + main-and-si.aux + main-and-si.bbl
    |
    +--> split_pdf.py main-and-si.pdf SPLIT_PAGE  -->  main-and-si-SI.pdf
    |
    +--> extract_main.py main-and-si.tex  -->  main-and-si_SUBMIT/
                                                 main.tex, fig1.pdf, ..., <class>.cls,
                                                 main.pdf (test compile)
                                                 (SI \ref{}s resolve via an
                                                  appended \label{} block;
                                                  bibliography inlined;
                                                  \includegraphics{figN.pdf})
```

`split_pdf.py` and `extract_main.py` both work from the **compiled** combined
document and can run in either order. Together they produce the
submission/revision package: `main.tex` + `figN.pdf` + the `.cls` for the
main text, and `main-and-si-SI.pdf` for the SI.

---

## What the converters do

**From the Beamer preamble:**
- `\title[short]{Long title}` → manuscript title
- `\author{...}` → author list with affiliations. Accepts either Beamer's
  `\and`-separated form (`Name\inst{1} \and Name\inst{2}`) or a plain
  comma-separated English list (`Name\inst{1}, Name\inst{2}, and Name\inst{3}`)
- `\institute{\inst{1} Affil one \and \inst{2} Affil two}` → affiliation block;
  without `\inst{}` markup, all authors share the single `\institute{}` text
  (placeholder only when `\institute{}` is absent too)

**From the body:**
- `\section{}`, `\section*{}`, `\subsection{}`, and `\subsection*{}` commands
  become manuscript headings (labels preserved; level is unchanged)
- Frame titles are dropped; frame content becomes prose paragraphs
- `\section{Abstract}` and its frames are extracted into the abstract block
- `\includegraphics` is wrapped in `\begin{figure}` with `\caption` and `\label`
- Bare `tabular`/`tabular*`/`tabularx` blocks are wrapped in `\begin{table}`,
  with an adjacent `\caption{}` (immediately before or after the tabular) and
  its `\label{}` attached; the caption is placed above the tabular
- `\captionof{figure}{...}` / `\captionof{table}{...}` are converted to `\caption{...}`
- `\fig{path}` (Beamer shorthand macro) expanded to `\includegraphics{path}`
- `enumerate`/`itemize` lists are flattened to prose sentences
- Beamer overlay and layout commands (`\pause`, `\only`, `\alert`, `\columns`, etc.) are stripped
- `\renewcommand\thetable`, `\setcounter{table}`, `\clearpage` passed through verbatim
- A `%% SI_BEGIN` comment sentinel marks the SI boundary (after the
  bibliography), consumed by `extract_main.py` when splitting out a
  main-text-only manuscript (see *What extract_main.py does* below)

**AMS-specific:**
- Author affiliations use `\aff{a}`, `\aff{b}`, … (letter-based)
- Byline follows the AMS template convention: a comma after each author name
  except the last, and `and` before the last author only (not between every
  pair) — e.g. `Name One,\aff{a} Name Two,\aff{b} and Name Three\aff{c}`
- `\abstract{...}` command form
- Corresponding-author email filled from the `%% EMAIL:` sentinel
  (same sentinel as AGU; placeholder if absent)
- End-matter extracted from the same comment-sentinel-wrapped frames as AGU
  (see *End-matter sentinels* below): `DATA` → `\datastatement`
  (AMS's required data availability statement), `ACKS` → `\acknowledgments`;
  `COI` has no AMS section of its own, so its text is appended to the
  acknowledgments paragraph. Placed before the bibliography; stubs when
  sentinels absent
- `\section*{Key points}` and its frames are consumed and dropped (AGU-only
  front matter); `\section*{Plain Language Summary}` is consumed and emitted
  as a commented `%\statement` block after `\maketitle` (AMS's optional
  significance statement, max 120 words — trim, then uncomment)
- `natbib` / `\citep` / `\citet` — kept as-is
- `\bibliographystyle{...}` and `\bibliography{...}` extracted from source and
  injected into the postamble (works regardless of whether they appear inside or outside a frame).
  The style is passed through **verbatim** — a deck using `plainnat` (as
  `examples/starter-slides.tex` does) gives AMS output with `plainnat`, not
  `ametsocV6`
- `\section{Supplemental…}` is reordered: bibliography + `\clearpage` are injected
  before it so references always precede SI content (mirrors AGU behavior).
  A manual "Supplemental material for:" title page (title/authors/affiliations/
  corresponding author, styled after the AMS `\@maketitle` layout) is then
  emitted before the SI content itself, since `\maketitle` cannot be called a
  second time
- `\section{Appendix…}` opens the appendix (see *Appendix* below); the
  appendix block sits between the endmatter and the bibliography (AMS
  template order)
- `%TC:ignore` / `%TC:endignore` markers for `texcount`: title/authors/affiliation/
  abstract block ignored, every figure/table caption ignored, SI ignored —
  AMS's word-limit rule excludes captions in particular, unlike AGU, which
  counts them. Body text, acknowledgments/data statement, and appendixes are
  **not** ignored — AMS's published limit counts all of these

**AGU-specific:**
- Author affiliations use `\affil{1}`, `\affil{2}`, … (number-based)
- `\begin{abstract}...\end{abstract}` environment
- `\section*{Plain Language Summary}` and its frames extracted into the preamble PLS block
- `apacite` — `\citet{key}` → `\citeA{key}`, `\citep{key}` → `\cite{key}`
  (applied to the body and to the abstract / Plain Language Summary /
  key points extracted into the preamble)
- `\bibliographystyle` is stripped (the class loads `apacite` automatically)
- `\bibliography{...}` file name extracted from source and appended after end-matter
- End-matter (Open Research, Conflict of Interest, Acknowledgments) extracted from
  comment-sentinel-wrapped frames (see *End-matter sentinels* below); placed before
  any `\section{Supplemental…}` in the output; per-section stubs used when sentinels absent
- `\section{Appendix…}` opens the appendix (see *Appendix* below); the
  appendix block sits ahead of the endmatter (AGU template order: body →
  Appendix → Open Research/COI/Acknowledgments → References)
- The SI scaffold (`%% SI_BEGIN`, cover page, "Contents of this file"
  checklist) is emitted only when the deck has a `\section{Supplemental…}`;
  a no-SI deck gets endmatter + bibliography and nothing after (use
  `extract_main.py --no-si` on such a manuscript)
- Display math wrapped in `\begin{linenomath*}...\end{linenomath*}` for line numbering
- Figures use `\noindent\includegraphics[width=\textwidth]{...}` (no `\centering`)
- Publication-unit guidance comment inserted between `\journalname{}` and `\begin{document}`
- `%TC:ignore` / `%TC:endignore` markers for `texcount`: title+key-points block ignored,
  PLS ignored, endmatter+bibliography+SI ignored; abstract, body, and the
  appendix are counted

---

## What extract_main.py does

The converters write main text and SI into one `.tex`, so `\ref{}` in the
main text resolves to SI numbers (`S1`, `S2`, …). `extract_main.py` turns
that into a main-text-only submission folder:

- The SI is cut at a detected boundary. New conversions emit a
  `%% SI_BEGIN` comment sentinel automatically; legacy combined files
  without the sentinel fall back to detecting
  `\section*{Supporting Information...}` / `\section{Supplement...}`, or
  finally `\renewcommand\thefigure{S\arabic{figure}}`.
- `\ref{}`/`\eqref{}`/`\autoref{}`/`\cref{}`/`\Cref{}` pointing at an SI
  item are left unchanged; an invisible block of `\label{}` reconstructions
  (built from the `.aux`'s `S1`, `S2`, ... numbers) is inserted before
  `\end{document}` so they resolve normally — no dangling references.
  `\pageref{}` to an SI item is flattened to the literal page number.
  `\autoref`/`\cref`/`\Cref` on labels without a `fig:`/`tab:`/`eq:` prefix
  get a warning (the printed noun may need a manual fix).
- Relative `\includegraphics` paths are rebased so they resolve from the
  output directory (the combined file's paths resolve from its own
  directory, one level up from `<stem>_SUBMIT/`); absolute paths are left
  alone.
- Each `\begin{figure}...\end{figure}` block is extracted into its own
  `fig1.pdf`, `fig2.pdf`, ... (via `make_single_figure.sh`) and
  `\includegraphics` is rewritten to the bare filename `figN.pdf` — no
  directory path — so the output compiles in the publisher's flat
  submission folder. Multi-panel figures collapse to the single cropped
  composite.
- The compiled `.bbl` (from the same `bibtex` run that produced the `.aux`)
  is inlined as a `thebibliography` environment in place of
  `\bibliography{}`, and `\bibliography{}`/`\bibliographystyle{}` are
  commented out — so `main.tex` compiles with `pdflatex` alone, with no
  `bibtex` run and no `.bib` database needed on the publisher's machine.
- Local `.cls`/`.sty` files that `main.tex` loads are copied into the output
  folder — taken from next to the combined `.tex` if there (your paper's own
  class copy wins), otherwise from this repo's `ams/`/`agu/`. Anything found
  in neither place is assumed to be part of the TeX installation.
- `main.tex` is then test-compiled in the output folder with **`TEXINPUTS`
  unset**, so only what's in the folder (plus the TeX installation) is
  visible — the publisher's situation. It runs `pdflatex` 2–4 times, until
  LaTeX stops asking for a rerun (3 is typical with citations), and reports
  pages, undefined references/citations, and overfull boxes. A failed
  compile prints the LaTeX error and exits 1. A package that compiled
  for you only because it is on your `TEXINPUTS` will fail here: put a copy
  next to the combined `.tex` and rerun.
- Build leftovers are deleted: `main_figures.*` (figure harness) and
  `main.aux`/`.out`/`.log`. `main.log` is kept if the compile failed or
  reported problems. `main.pdf` is kept for checking — don't upload it.

---

## Project structure

```
tex-utility/
  scripts/
    convert.py              Unified CLI (--format ams|agu)
    beamer_to_ams.py        AMS converter
    beamer_to_agu.py        AGU converter
    beamer_common.py        Shared Beamer parsing
    extract_main.py         Split combined main+SI .tex into main-only manuscript
    split_pdf.py            PDF splitter (main text / SI)
    make_single_figure.sh   Extract each figure into its own figN.pdf
    bib_for_ams.py          Generate AMS-abbreviated copy of a .bib
    bib_add_doi.py          Find (Crossref) and insert missing DOIs
  specs/                    Behavioral specs -- update alongside the script
    beamer_to_ams_spec.md
    beamer_to_agu_spec.md
    extract_main_spec.md
    bib_for_ams_spec.md
    bib_add_doi_spec.md
  tests/
    run_tests.py            Regression suite: python tests/run_tests.py
    test_input.tex          Test Beamer source
    test_main_si.tex        Test combined main+SI source (extract_main.py)
    test_main_si.aux        Matching .aux fixture (extract_main.py)
    test_main_si.bbl        Matching .bbl fixture (extract_main.py)
  examples/
    starter-slides.tex      Barebones deck pre-tagged with all conversion hooks
                            (start new decks from this)
    slides-v2.tex, slides-v3.tex          Real decks used during development
    slides-v2_agu.tex                     ... and converted output
    enso-global-temperature-slides-v5.tex Real deck, with converted output
      (_agu.tex, _manuscript.tex)
  ams/
    ametsocV6.1.cls, ametsocV6.bst
    AMS LaTeX Package V6.1/ Full publisher package (untracked; docs, template)
  agu/
    agujournal2019.cls, agutexSI2019.cls, trackchanges.sty
    agujournaltemplate.tex  Publisher main-text template
    si_template_2019.tex    Publisher SI template
    Sep-2025-agujournal2019 template/  Full publisher package (untracked)
```

LaTeX build products (`.aux`, `.log`, `.pdf`, …) in `examples/` and `agu/`
are gitignored, as is a duplicate `agujournal2019.cls` at the repo root
(identical to `agu/`'s copy).
