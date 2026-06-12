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
    check('author One aff a',          text, r'Author One\\aff\{a\}')
    check('author Two aff b',          text, r'Author Two\\aff\{b\}')
    check('author Three aff a',        text, r'Author Three\\aff\{a\}')
    check('affiliation aff{a} text',   text, r'\\aff\{a\}\{Department of Atmospheric Science')
    check('affiliation aff{b} text',   text, r'\\aff\{b\}\{Institute of Oceanography')
    check('corresponding author',      text, r'\\correspondingauthor\{')
    check('amsmath pkg',               text, r'\\usepackage\{amsmath\}')
    check('bm pkg',                    text, r'\\usepackage\{bm\}')
    check('bibliographystyle kept',    text, r'\\bibliographystyle\{plainnat\}')

    # --- abstract ---
    check('abstract command',          text, r'\\abstract\{')
    check('abstract text',             text, r'Beamer-to-manuscript conversion')

    # --- body ---
    check('intro section',             text, r'\\section\{Introduction\}')
    check('methods section',           text, r'\\section\{Methods\}')
    check('results section',           text, r'\\section\{Results\}')
    check('figure environment',        text, r'\\begin\{figure\}')
    check('table environment',         text, r'\\begin\{tabular\}')
    check('bibliography',              text, r'\\bibliography\{refs\}')
    # bibliography must precede supplemental content (not end up after it)
    bib_pos  = text.find(r'\bibliography{refs}')
    si_pos   = text.find('test_si_figure_1')
    if bib_pos == -1 or si_pos == -1:
        _failures.append('  FAIL  bib-before-SI: markers not found for ordering check')
    elif not (bib_pos < si_pos):
        _failures.append('  FAIL  bib-before-SI: \\bibliography{} appears AFTER supplemental content')

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

    # --- main-text figures retained ---
    check('main figure 1 retained',   text, r'plotA\.pdf')
    check('main figure 2 retained',   text, r'plotB1\.pdf')

    # --- \ref{} to SI label flattened to literal S1 ---
    check('ref to SI figure -> S1',   text, r'Figure~S1')
    check('ref to SI table -> S1',    text, r'Table~S1')
    check('eqref to SI eq -> (S1)',   text, r'Eq\.~\(S1\)')
    check('pageref to SI fig -> 2',   text, r'page~2')

    # --- \ref{} to a main-text label left unchanged ---
    check('ref to main figure unchanged', text, r'\\ref\{fig:main1\}')

    # --- \Cref/stale \ref left unchanged (warn-and-skip / stale .aux) ---
    check('Cref to SI label unchanged',   text, r'\\Cref\{fig:si1\}')
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

    # --- extract_main.py: \includegraphics rewrite (unit test) ---
    print('\n=== extract_main figure rewrite (unit) ===')
    before = len(_failures)
    check_figure_rewrite_unit()
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
