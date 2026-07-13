#!/usr/bin/env python3
"""
run_tests.py — regression checks for beamer_to_agu.py and beamer_to_manuscript.py

Runs both converters on tests/test_input.tex and asserts required strings/patterns
are present (or absent) in the output.  Exit code 0 = all pass, 1 = any failure.

Usage:
    python tests/run_tests.py          # from repo root
    python run_tests.py                # from tests/
"""

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR   = Path(__file__).parent
SCRIPTS_DIR = TESTS_DIR.parent / 'scripts'
INPUT       = TESTS_DIR / 'test_input.tex'
EXTRACT_INPUT = TESTS_DIR / 'test_main_si.tex'
EXTRACT_AUX   = TESTS_DIR / 'test_main_si.aux'
EXTRACT_BBL   = TESTS_DIR / 'test_main_si.bbl'
PYTHON      = sys.executable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_failures = []

def check(name, text, pattern, present=True, flags=0):
    found = bool(re.search(pattern, text, flags))
    ok    = found if present else not found
    if not ok:
        adj = 'present' if present else 'absent'
        _failures.append(f'  FAIL  {name}: expected {adj}: {pattern!r}')
    return ok


def run_converter(script, output_tex):
    result = subprocess.run(
        [PYTHON, str(SCRIPTS_DIR / script), str(INPUT), str(output_tex)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _failures.append(f'  FAIL  {script} exited {result.returncode}:\n{result.stderr}')
        return False
    return True


def run_extract_main(outdir):
    result = subprocess.run(
        [PYTHON, str(SCRIPTS_DIR / 'extract_main.py'),
         str(EXTRACT_INPUT), str(EXTRACT_AUX),
         '--outdir', str(outdir), '--no-figures'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _failures.append(f'  FAIL  extract_main.py exited {result.returncode}:\n{result.stderr}')
        return False
    return True


# ---------------------------------------------------------------------------
# AGU checks
# ---------------------------------------------------------------------------

def check_agu(text):
    # --- preamble metadata ---
    check('AGU docclass',              text, r'\\documentclass.*agujournal2019')
    check('journal name',              text, r'\\journalname\{Geophysical Research Letters\}')
    check('author One affil 1',        text, r'Author One\\affil\{1\}')
    check('author Two affil 2',        text, r'Author Two\\affil\{2\}')
    check('author Three affil 1',      text, r'Author Three\\affil\{1\}')
    check('affiliation 1 text',        text, r'\\affiliation\{1\}\{Department of Atmospheric Science')
    check('affiliation 2 text',        text, r'\\affiliation\{2\}\{Institute of Oceanography')
    check('corresponding author name', text, r'\\correspondingauthor\{Author One\}')
    check('email sentinel',            text, r'author@university\.edu')
    check('amsmath pkg',               text, r'\\usepackage\{amsmath\}')
    check('amssymb pkg',               text, r'\\usepackage\{amssymb\}')
    check('bm pkg',                    text, r'\\usepackage\{bm\}')
    check('booktabs pkg',              text, r'\\usepackage\{booktabs\}')
    check('multirow pkg',              text, r'\\usepackage\{multirow\}')
    check('no appendixnumberbeamer',   text, r'appendixnumberbeamer', present=False)
    check('bibliographystyle absent',  text, r'\\bibliographystyle', present=False)

    # --- special AGU preamble sections ---
    check('keypoints block',           text, r'\\begin\{keypoints\}')
    check('keypoint 1',                text, r'Conversion pipeline correctly')
    check('PLS section',               text, r'\\section\*\{Plain Language Summary\}')
    check('PLS text',                  text, r'Scientific papers often begin')
    check('abstract block',            text, r'\\begin\{abstract\}')
    check('abstract text',             text, r'Beamer-to-manuscript conversion')

    # --- citation remapping (natbib → apacite) ---
    check('citet→citeA',               text, r'\\citeA\{wheeler2004\}')
    check('abstract citation remapped', text,
          r'extending \\citeA\{wheeler2004\}')
    check('citep→cite',                text, r'\\cite\{madden1971\}')
    check('citep[post]→cite[post]',    text, r'\\cite\[e\.g\.,\]\{vitart2017\}')
    check('citet[pre][post]→citeA<>',  text, r'\\citeA<see>\[their Fig')
    check('citet[][post]→citeA[post]', text, r'\\citeA\[p\.~5\]\{jones2019\}')
    check('citep[pre][post]→cite<>[]', text, r'\\cite<cf\.>\[Table~2\]\{brown2021\}')
    check('no raw \\citet',            text, r'\\citet\{', present=False)
    check('no raw \\citep',            text, r'\\citep\{', present=False)

    # --- equation wrapping (linenomath*) ---
    check('linenomath* + equation',    text, r'\\begin\{linenomath\*\}\s*\\begin\{equation\}')
    check('linenomath* + align',       text, r'\\begin\{linenomath\*\}\s*\\begin\{align\}')
    check('linenomath* + \\[',         text, r'\\begin\{linenomath\*\}\s*\\\[')

    # --- body content ---
    check('intro section',             text, r'\\section\{Introduction\}')
    check('methods section',           text, r'\\section\{Methods\}')
    check('results section',           text, r'\\section\{Results\}')
    check('conclusions section',       text, r'\\section\{Conclusions\}')
    check('figure environment',        text, r'\\begin\{figure\}')
    check('table environment',         text, r'\\begin\{tabular\}')
    # tabular wrapped in a table float, caption above (AGU: no [h], no centering)
    check('table float wrapper',       text,
          r'\\begin\{table\}\s*\\caption\{Comparison of forecast')
    check('table label kept',          text, r'\\label\{tab:summary\}')
    check('no bare caption after tabular', text,
          r'\\end\{tabular\}\s*\\caption', present=False)

    # --- endmatter sentinels ---
    check('open research section',     text, r'\\section\*\{Open Research Section\}')
    check('open research content',     text, r'zenodo\.org/record/test')
    check('COI section',               text, r'\\section\*\{Conflict of Interest\}')
    check('acknowledgments cmd',       text, r'\\acknowledgments')
    check('acks content',              text, r'NSF grant AGS-0000000')
    check('bibliography',              text, r'\\bibliography\{refs\}')

    # --- SI header ---
    check('SI clearpage+counter',      text, r'\\clearpage\s+\\setcounter\{page\}\{1\}')
    check('SI title',                  text, r'Supporting Information for')
    check('SI figures S1 to S2',       text, r'\\item Figures S1 to S2')
    check('SI table S1 singular',      text, r'\\item Table S1')
    check('SI text commented out',     text, r'%\\item Text S1 to Sx')


# ---------------------------------------------------------------------------
# AMS checks
# ---------------------------------------------------------------------------

def check_manuscript(text):
    # --- preamble metadata ---
    check('AMS docclass',              text, r'\\documentclass\{ametsocV6\.1\}')
    check('author One aff a',          text, r'Author One,\\aff\{a\}')
    check('author Two aff b',          text, r'Author Two,\\aff\{b\}')
    check('author Three aff a',        text, r'and Author Three\\aff\{a\}')
    check('affiliation aff{a} text',   text, r'\\aff\{a\}\{Department of Atmospheric Science')
    check('affiliation aff{b} text',   text, r'\\aff\{b\}\{Institute of Oceanography')
    check('corresponding author',      text, r'\\correspondingauthor\{')
    check('email sentinel',            text, r'author@university\.edu')
    check('amsmath pkg',               text, r'\\usepackage\{amsmath\}')
    check('bm pkg',                    text, r'\\usepackage\{bm\}')
    check('booktabs pkg',              text, r'\\usepackage\{booktabs\}')
    check('multirow pkg',              text, r'\\usepackage\{multirow\}')
    check('no appendixnumberbeamer',   text, r'appendixnumberbeamer', present=False)
    check('bibliographystyle kept',    text, r'\\bibliographystyle\{plainnat\}')

    # --- abstract ---
    check('abstract command',          text, r'\\abstract\{')
    check('abstract text',             text, r'Beamer-to-manuscript conversion')

    # --- commented \statement from Plain Language Summary ---
    check('statement commented',       text, r'^%\\statement', flags=re.MULTILINE)
    check('statement PLS text',        text, r'^%  Scientific papers often begin',
          flags=re.MULTILINE)

    # --- AGU-only front matter consumed, not leaked into the body ---
    check('no Key points section',     text, r'\\section\*?\{Key points\}', present=False)
    check('no PLS section',            text, r'\\section\*?\{Plain Language', present=False)

    # --- endmatter from sentinels ---
    check('acknowledgments cmd',       text, r'^\\acknowledgments', flags=re.MULTILINE)
    check('acks content',              text, r'NSF grant AGS-0000000')
    check('COI folded into acks',      text, r'declare no conflicts of interest')
    check('datastatement cmd',         text, r'^\\datastatement', flags=re.MULTILINE)
    check('datastatement content',     text, r'zenodo\.org/record/test')
    # endmatter must precede the bibliography
    ds_pos  = text.find(r'\datastatement')
    bib_pos = text.find(r'\bibliography{refs}')
    if ds_pos == -1 or bib_pos == -1 or not (ds_pos < bib_pos):
        _failures.append('  FAIL  endmatter-before-bib: \\datastatement must '
                         'precede \\bibliography{}')

    # --- body ---
    check('intro section',             text, r'\\section\{Introduction\}')
    check('methods section',           text, r'\\section\{Methods\}')
    check('results section',           text, r'\\section\{Results\}')
    check('figure environment',        text, r'\\begin\{figure\}')
    check('table environment',         text, r'\\begin\{tabular\}')
    # tabular wrapped in a table float; AMS excludes table captions from the
    # word count, so the caption is %TC:ignore-wrapped like figure captions
    check('table float wrapper',       text,
          r'\\begin\{table\}\[h\]\s*\\centering\s*%TC:ignore\s*'
          r'\\caption\{Comparison of forecast')
    check('table label kept',          text, r'\\label\{tab:summary\}')
    check('bibliography',              text, r'\\bibliography\{refs\}')
    # bibliography must precede supplemental content (not end up after it)
    bib_pos  = text.find(r'\bibliography{refs}')
    si_pos   = text.find('test_si_figure_1')
    if bib_pos == -1 or si_pos == -1:
        _failures.append('  FAIL  bib-before-SI: markers not found for ordering check')
    elif not (bib_pos < si_pos):
        _failures.append('  FAIL  bib-before-SI: \\bibliography{} appears AFTER supplemental content')

    # --- Supplemental material title page (mirrors AGU's SI header) ---
    check('SI titlepage heading',      text, r'Supplemental material for:')
    check('SI titlepage title',        text, r'Full Test Title for Conversion Scripts')
    check('SI titlepage authors',      text,
          r'Author One\\aff\{a\}, Author Two\\aff\{b\}, and Author Three\\aff\{a\}')
    check('SI titlepage corr author',  text, r'Corresponding author\}: Author One, author@university\.edu')
    check('SI titlepage page reset',   text, r'\\setcounter\{page\}\{1\}')
    si_title_pos = text.find('Supplemental material for:')
    if si_title_pos == -1 or bib_pos == -1 or si_pos == -1:
        _failures.append('  FAIL  SI-titlepage-order: markers not found for ordering check')
    elif not (bib_pos < si_title_pos < si_pos):
        _failures.append('  FAIL  SI-titlepage-order: title page must sit between '
                         '\\bibliography{} and the SI content')

    # --- no AGU-specific transforms ---
    check('no \\citeA',                text, r'\\citeA\{',         present=False)
    check('no linenomath',             text, r'linenomath',         present=False)
    check('no keypoints env',          text, r'\\begin\{keypoints\}', present=False)
    check('no AGU journalname',        text, r'\\journalname\{',    present=False)


# ---------------------------------------------------------------------------
# extract_main.py checks
# ---------------------------------------------------------------------------

def check_extract_main(text):
    # --- SI removed ---
    check('SI section removed',       text, r'Supporting Information', present=False)
    check('SI figure removed',        text, r'si_plotA', present=False)
    check('SI equation removed',      text, r'\\begin\{equation\}', present=False)
    check('SI table removed',         text, r'\\begin\{table\}', present=False)
    check('SI sentinel consumed',     text, r'%%\s*SI_BEGIN', present=False)

    # --- exactly one trailing \end{document} ---
    n_end = len(re.findall(r'\\end\{document\}', text))
    if n_end != 1:
        _failures.append(f'  FAIL  single \\end{{document}}: expected 1, got {n_end}')

    # --- .bbl inlined, \bibliography{}/\bibliographystyle{} commented out ---
    check('bibliographystyle commented',  text, r'^%\\bibliographystyle\{plainnat\}', flags=re.MULTILINE)
    check('bibliography commented',       text, r'^%\\bibliography\{refs\}', flags=re.MULTILINE)
    check('bbl content inlined',          text, r'smith2020')
    n_thebib = len(re.findall(r'\\begin\{thebibliography\}', text))
    if n_thebib != 1:
        _failures.append(f'  FAIL  thebibliography count: expected 1, got {n_thebib}')

    # --- %TC:ignore re-closed (its %TC:endignore was inside the removed SI) ---
    n_ignore    = len(re.findall(r'^[ \t]*%TC:ignore[ \t]*$', text, re.MULTILINE))
    n_endignore = len(re.findall(r'^[ \t]*%TC:endignore[ \t]*$', text, re.MULTILINE))
    if n_ignore != n_endignore:
        _failures.append(
            f'  FAIL  TC:ignore balance: {n_ignore} %TC:ignore vs '
            f'{n_endignore} %TC:endignore')
    check('TC:endignore before \\end{document}', text,
          r'%TC:endignore\s*\\end\{document\}')

    # --- main-text figures retained ---
    check('main figure 1 retained',   text, r'plotA\.pdf')
    check('main figure 2 retained',   text, r'plotB1\.pdf')

    # --- \ref{}/\eqref{}/\Cref{} to SI labels left UNCHANGED in text ---
    check('ref to SI figure unchanged', text, r'Figure~\\ref\{fig:si1\}')
    check('ref to SI table unchanged',  text, r'Table~\\ref\{tab:si1\}')
    check('eqref to SI eq unchanged',   text, r'Eq\.~\\eqref\{eq:si1\}')
    check('Cref to SI label unchanged', text, r'\\Cref\{fig:si1\}')

    # --- \pageref{} to SI label flattened to literal page number ---
    check('pageref to SI fig -> 2',     text, r'page~2')
    check('no EMref wrapper left behind', text, r'\\EMref', present=False)

    # --- reconstructed \label{} block for SI refs, wrapped in %TC:ignore ---
    check('SI label reconstruction: fig:si1', text,
          r'\\renewcommand\\thefigure\{S1\}\\refstepcounter\{figure\}\\label\{fig:si1\}')
    check('SI label reconstruction: tab:si1', text,
          r'\\renewcommand\\thetable\{S1\}\\refstepcounter\{table\}\\label\{tab:si1\}')
    check('SI label reconstruction: eq:si1', text,
          r'\\renewcommand\\theequation\{S1\}\\refstepcounter\{equation\}\\label\{eq:si1\}')

    # --- \ref{} to a main-text label left unchanged ---
    check('ref to main figure unchanged', text, r'\\ref\{fig:main1\}')

    # --- stale \ref left unchanged (warn-and-skip on missing .aux entry) ---
    check('stale ref unchanged',          text, r'\\ref\{fig:stale\}')


# ---------------------------------------------------------------------------
# extract_main.py figure-rewrite unit test (no pdflatex/pdfcrop required)
# ---------------------------------------------------------------------------

_FIGURE_REWRITE_SAMPLE = r"""
\begin{figure}
  \includegraphics[width=\linewidth]{plotA.pdf}
  \caption{A}
  \label{fig:a}
\end{figure}

\begin{figure}
  \includegraphics[width=0.49\linewidth]{plotB1.pdf}
  \includegraphics[width=0.49\linewidth]{plotB2.pdf}
  \caption{B}
  \label{fig:b}
\end{figure}

% \begin{figure}
% \includegraphics{template_example.pdf}
% \caption{C}
% \end{figure}
"""


def check_sentinel_aliases_unit():
    """Both sentinel spellings (generic canonical + legacy AGU_*) must be
    accepted.  The end-to-end runs cover generic DATA/EMAIL and legacy
    COI/ACKS; this covers the remaining combinations."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from beamer_common import extract_sentinel_block, extract_email

    cases = [
        ('DATA', '%% DATA_BEGIN\nX\n%% DATA_END\n'),
        ('DATA', '%% AGU_OPENRESEARCH_BEGIN\nX\n%% AGU_OPENRESEARCH_END\n'),
        ('COI',  '%% COI_BEGIN\nX\n%% COI_END\n'),
        ('COI',  '%% AGU_COI_BEGIN\nX\n%% AGU_COI_END\n'),
        ('ACKS', '%% ACKS_BEGIN\nX\n%% ACKS_END\n'),
        ('ACKS', '%% AGU_ACKS_BEGIN\nX\n%% AGU_ACKS_END\n'),
    ]
    for label, src in cases:
        block = extract_sentinel_block(src, label)
        if block is None or 'X' not in block[2]:
            _failures.append(f'  FAIL  sentinel alias: {label} not extracted '
                             f'from {src.splitlines()[0]!r}')

    for src in ('%% EMAIL: a@b.edu\n', '%% AGU_EMAIL: a@b.edu\n'):
        if extract_email(src) != 'a@b.edu':
            _failures.append(f'  FAIL  email alias: not extracted from '
                             f'{src.strip()!r}')


_NO_INST_SRC = r"""
\documentclass{beamer}
\title{No-inst Deck}
\author{First Author and Second Author}
\institute{Shared Institution, City}
\begin{document}
\begin{frame}{A}
Text.
\end{frame}
\end{document}
"""


def check_noinst_fallback_unit():
    r"""\author{} without \inst{} markup: all authors share the single
    \institute{} text; the placeholder is used only when \institute{} is
    absent too."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from beamer_to_ams import _parse_authors_affiliations
    from beamer_to_agu import _parse_authors_affiliations_agu

    authors, aff_block = _parse_authors_affiliations(_NO_INST_SRC)
    if [aff for _, aff in authors] != ['a', 'a']:
        _failures.append('  FAIL  no-inst AMS: both authors should share '
                         f'aff a, got {authors}')
    check('no-inst AMS institute kept', aff_block, r'Shared Institution, City')
    check('no-inst AMS no placeholder', aff_block,
          r'Department, Institution', present=False)

    authors_block, aff_lines, _corr = _parse_authors_affiliations_agu(_NO_INST_SRC)
    check('no-inst AGU shared affil 1', authors_block,
          r'First Author\\affil\{1\} and Second Author\\affil\{1\}')
    if len(aff_lines) != 1 or 'Shared Institution, City' not in aff_lines[0]:
        _failures.append('  FAIL  no-inst AGU: expected one shared '
                         f'affiliation, got {aff_lines}')


_NO_SI_DECK = r"""
\documentclass{beamer}
\title{No SI Deck}
\author{Solo Author}
\institute{Some Institute}
%% EMAIL: solo@example.edu
\begin{document}
\section{Results}
\begin{frame}{Result}
Body text.
\end{frame}
\end{document}
"""


def check_no_si_paths():
    """A deck without an SI section: the AGU converter must not emit the SI
    scaffold or %% SI_BEGIN, and extract_main --no-si must still package the
    resulting manuscript."""
    with tempfile.TemporaryDirectory() as tmpdir:
        deck = Path(tmpdir) / 'no_si.tex'
        deck.write_text(_NO_SI_DECK)
        out = Path(tmpdir) / 'no_si_agu.tex'
        result = subprocess.run(
            [PYTHON, str(SCRIPTS_DIR / 'beamer_to_agu.py'), str(deck), str(out)],
            capture_output=True, text=True)
        if result.returncode != 0:
            _failures.append(f'  FAIL  no-SI AGU convert exited '
                             f'{result.returncode}:\n{result.stderr}')
            return
        text = out.read_text()
        check('no-SI: scaffold absent', text,
              r'Supporting Information for', present=False)
        check('no-SI: sentinel absent', text, r'%% SI_BEGIN', present=False)
        check('no-SI: endmatter still emitted', text,
              r'\\section\*\{Open Research Section\}')

        subdir = Path(tmpdir) / 'SUBMIT'
        result = subprocess.run(
            [PYTHON, str(SCRIPTS_DIR / 'extract_main.py'), str(out),
             '--outdir', str(subdir), '--no-figures', '--no-bib', '--no-si'],
            capture_output=True, text=True)
        if result.returncode != 0:
            _failures.append(f'  FAIL  extract_main --no-si exited '
                             f'{result.returncode}:\n{result.stderr}')
            return
        main_tex = subdir / 'main.tex'
        if not main_tex.exists():
            _failures.append('  FAIL  extract_main --no-si: main.tex not written')
            return
        check('--no-si: body preserved', main_tex.read_text(), r'Body text')


def check_rebase_paths_unit():
    """Relative \\includegraphics paths must be rewritten to resolve from the
    output directory; absolute paths are untouched."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import extract_main as em

    sample = (r'\includegraphics[width=\linewidth]{../plots/a.pdf}' '\n'
              r'\includegraphics{/abs/path/b.pdf}')
    new_text, n = em.rebase_graphics_paths(
        sample, Path('proj/tex'), Path('proj/tex/SUB'))
    if n != 1:
        _failures.append(f'  FAIL  rebase_graphics_paths: expected 1 rebased, got {n}')
    check('rebase relative path', new_text, r'\{\.\./\.\./plots/a\.pdf\}')
    check('rebase keeps options', new_text, r'\[width=\\linewidth\]\{\.\./\.\./plots/a\.pdf\}')
    check('rebase leaves absolute', new_text, r'\{/abs/path/b\.pdf\}')


def check_figure_rewrite_unit():
    sys.path.insert(0, str(SCRIPTS_DIR))
    import extract_main as em

    n = em.count_figure_envs(_FIGURE_REWRITE_SAMPLE)
    if n != 2:
        _failures.append(f'  FAIL  count_figure_envs: expected 2 (commented block '
                          f'excluded), got {n}')

    new_text, n_rewritten = em.rewrite_figure_includes(_FIGURE_REWRITE_SAMPLE)
    if n_rewritten != 2:
        _failures.append(f'  FAIL  rewrite_figure_includes: expected 2 rewritten, '
                          f'got {n_rewritten}')

    check('rewrite fig1 (bare filename)',
          new_text, r'\\includegraphics\[width=\\linewidth\]\{fig1\.pdf\}')
    check('rewrite fig2 (first panel -> figN.pdf)',
          new_text, r'\\includegraphics\[width=0\.49\\linewidth\]\{fig2\.pdf\}')
    check('rewrite fig2 (second panel removed)',
          new_text, r'plotB2\.pdf', present=False)
    check('commented figure block preserved verbatim',
          new_text, r'% \\includegraphics\{template_example\.pdf\}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not INPUT.exists():
        sys.exit(f'Test input not found: {INPUT}')

    converters = [
        ('AGU',  'beamer_to_agu.py',        check_agu),
        ('AMS',  'beamer_to_ams.py',        check_manuscript),
    ]

    total_fail = 0

    for label, script, checker in converters:
        print(f'\n=== {label} ({script}) ===')

        with tempfile.NamedTemporaryFile(suffix='.tex', delete=False) as f:
            out = f.name

        before = len(_failures)
        if not run_converter(script, out):
            print(_failures[-1])
            total_fail += 1
            continue

        checker(Path(out).read_text())
        new_failures = _failures[before:]
        if new_failures:
            for msg in new_failures:
                print(msg)
            total_fail += len(new_failures)
        else:
            print('  all checks passed')

    # --- extract_main.py: SI strip + ref flattening, never-overwrite ---
    print('\n=== extract_main (extract_main.py) ===')
    if not EXTRACT_INPUT.exists() or not EXTRACT_AUX.exists() or not EXTRACT_BBL.exists():
        print(f'  FAIL  fixture not found: {EXTRACT_INPUT} / {EXTRACT_AUX} / {EXTRACT_BBL}')
        total_fail += 1
    else:
        input_hash_before = hashlib.sha256(EXTRACT_INPUT.read_bytes()).hexdigest()
        before = len(_failures)
        with tempfile.TemporaryDirectory() as tmpdir:
            if run_extract_main(tmpdir):
                out_tex = Path(tmpdir) / 'main.tex'
                if out_tex.exists():
                    check_extract_main(out_tex.read_text())
                else:
                    _failures.append('  FAIL  extract_main.py: main.tex not written')

        input_hash_after = hashlib.sha256(EXTRACT_INPUT.read_bytes()).hexdigest()
        if input_hash_before != input_hash_after:
            _failures.append(
                '  FAIL  extract_main.py: input file was modified '
                '(never-overwrite invariant violated)')

        new_failures = _failures[before:]
        if new_failures:
            for msg in new_failures:
                print(msg)
            total_fail += len(new_failures)
        else:
            print('  all checks passed')

    # --- sentinel spelling aliases (unit test) ---
    print('\n=== sentinel aliases (unit) ===')
    before = len(_failures)
    check_sentinel_aliases_unit()
    new_failures = _failures[before:]
    if new_failures:
        for msg in new_failures:
            print(msg)
        total_fail += len(new_failures)
    else:
        print('  all checks passed')

    # --- extract_main.py: \includegraphics rewrite (unit test) ---
    unit_sections = [
        ('extract_main figure rewrite (unit)', check_figure_rewrite_unit),
        ('no-inst affiliation fallback (unit)', check_noinst_fallback_unit),
        ('no-SI conversion + --no-si (e2e)', check_no_si_paths),
        ('graphics path rebasing (unit)', check_rebase_paths_unit),
    ]
    for section, fn in unit_sections:
        print(f'\n=== {section} ===')
        before = len(_failures)
        fn()
        new_failures = _failures[before:]
        if new_failures:
            for msg in new_failures:
                print(msg)
            total_fail += len(new_failures)
        else:
            print('  all checks passed')

    print(f'\n{"All tests passed." if total_fail == 0 else f"{total_fail} failure(s) total."}')
    sys.exit(0 if total_fail == 0 else 1)


if __name__ == '__main__':
    main()
