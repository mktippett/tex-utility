#!/usr/bin/env python3
"""
extract_main.py
----------------
Extract a main-text-only manuscript from a combined main+SI .tex file.

The Beamer-to-manuscript converters in this repo produce a single .tex file
containing both the main text and the Supporting Information (SI), so that
\\ref{} commands in the main text can resolve directly to SI figure/table
numbers (S1, S2, ...). At submission/revision, journals require the main text
as its own file, with the SI submitted separately.

This script takes that combined, already-compiled .tex (+ its .aux) and
writes a main-text-only manuscript to an output directory:

  - The SI is cut at a detected boundary (never touching the input file).
  - Any \\ref{}/\\eqref{}/\\pageref{} pointing at an SI item is replaced with
    the literal number from the .aux (e.g. \\ref{fig:foo} -> S3), so the
    main-only file has no dangling references.
  - Each \\begin{figure}...\\end{figure} block is extracted into its own
    fig1.pdf, fig2.pdf, ... (via make_single_figure.sh) and the
    \\includegraphics path(s) in main.tex are rewritten to the bare
    "figN.pdf" filename (multi-panel figures collapse to one image).
  - The compiled .bbl is inlined as a thebibliography environment in place
    of \\bibliography{}, and \\bibliography{}/\\bibliographystyle{} are
    commented out, so main.tex compiles with pdflatex alone (no bibtex,
    no .bib database needed on the publisher's machine).

Usage:
    python extract_main.py COMBINED.tex [COMBINED.aux] [--outdir DIR] \\
        [--no-figures] [--no-bib] [--bbl COMBINED.bbl]

  COMBINED.aux defaults to <stem>.aux next to COMBINED.tex, and must be the
  .aux produced by compiling the *combined* document -- that's where the
  SI item numbers (S1, S2, ...) come from.

  --outdir defaults to <stem>_main/.  All output (main.tex, figN.pdf, and
  make_single_figure.sh's intermediate files) is written there.  The input
  .tex (.aux, and .bbl) are never written to.

  --no-figures skips figure extraction/rewriting (SI strip + ref flattening
  only).

  --bbl defaults to <stem>.bbl next to COMBINED.tex, and must be the .bbl
  produced by running bibtex on the *combined* document.  --no-bib skips
  .bbl inlining and leaves \\bibliography{} live.
"""

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
MAKE_SINGLE_FIGURE = SCRIPT_DIR / 'make_single_figure.sh'


# ---------------------------------------------------------------------------
# SI boundary detection
# ---------------------------------------------------------------------------

# Primary: an explicit sentinel comment, emitted by the converters at the
# point where SI content begins.
_SENTINEL_RE = re.compile(r'^[ \t]*%%\s*SI_BEGIN.*$', re.MULTILINE)

# Fallback: the SI section header itself (covers hand-written combined files
# that predate the sentinel).
_SECTION_PATTERNS = [
    re.compile(r'\\section\*?\{\s*Supporting [Ii]nformation'),
    re.compile(r'\\section\*?\{\s*Supplement'),
]

# Last resort: the SI figure-numbering redefinition that both AMS and AGU
# SI sections use.
_THEFIGURE_RE = re.compile(r'\\renewcommand\\thefigure\{S\\arabic\{figure\}\}')


def find_si_start(text):
    """
    Return (offset, description) of the character where SI content begins,
    or (None, None) if no boundary marker is found.
    """
    m = _SENTINEL_RE.search(text)
    if m:
        return m.start(), 'sentinel (%% SI_BEGIN)'

    candidates = [m for m in (pat.search(text) for pat in _SECTION_PATTERNS) if m]
    if candidates:
        m = min(candidates, key=lambda m: m.start())
        return m.start(), 'section marker (' + m.group(0) + ')'

    m = _THEFIGURE_RE.search(text)
    if m:
        return m.start(), r'\thefigure{S\arabic{figure}} fallback'

    return None, None


def strip_si(text, si_start):
    """Return the text truncated before si_start, with a single trailing
    \\end{document} restored."""
    main = text[:si_start].rstrip() + '\n'
    if not re.search(r'\\end\{document\}\s*\Z', main):
        main += '\n\\end{document}\n'
    return main


# ---------------------------------------------------------------------------
# .aux parsing and \ref-family flattening
# ---------------------------------------------------------------------------

# \newlabel{label}{{ref}{page}...}  -- only ref and page are needed here.
_NEWLABEL_RE = re.compile(r'\\newlabel\{([^}]+)\}\{\{([^}]*)\}\{([^}]*)\}')


def parse_aux_labels(aux_text):
    """Parse \\newlabel entries into {label: {'ref': ..., 'page': ...}}."""
    labels = {}
    for line in aux_text.splitlines():
        m = _NEWLABEL_RE.search(line)
        if m:
            label, ref, page = m.groups()
            labels[label] = {'ref': ref, 'page': page}
    return labels


# \ref, \ref*, \eqref, \eqref*, \pageref, \pageref*, \autoref, \cref, \Cref
_REF_CMD_RE = re.compile(r'\\(ref|eqref|pageref|autoref|[Cc]ref)(\*?)\{([^}]+)\}')


def flatten_refs(text, aux_labels):
    """
    Replace \\ref{}/\\eqref{}/\\pageref{} commands that point at an SI label
    (an .aux \\newlabel whose ref text starts with "S") with the literal
    text the combined document resolved them to.

    \\autoref{}/\\cref{}/\\Cref{} pointing at SI labels are left unchanged --
    the "Figure"/"Table"/"section" noun they print isn't recoverable from
    the .aux -- and reported as warnings for manual fix-up.

    Returns (new_text, n_replaced, warnings).
    """
    si_labels = {label: info for label, info in aux_labels.items()
                  if info['ref'].startswith('S')}

    n_replaced = 0
    warnings = []
    missing_warned = set()

    def repl(m):
        nonlocal n_replaced
        cmd, star, label = m.groups()
        if label not in si_labels:
            if label not in aux_labels and label not in missing_warned:
                missing_warned.add(label)
                warnings.append(
                    f"label '{label}' not found in .aux "
                    "(stale .aux? \\ref will render as ??)")
            return m.group(0)

        info = si_labels[label]
        if cmd == 'ref':
            n_replaced += 1
            return info['ref']
        if cmd == 'eqref':
            n_replaced += 1
            return '(' + info['ref'] + ')'
        if cmd == 'pageref':
            n_replaced += 1
            return info['page']

        # autoref / cref / Cref
        warnings.append(
            f"\\{cmd}{star}{{{label}}} resolves to SI item {info['ref']} but "
            "was left unchanged -- autoref/cref noun text (Figure/Table/"
            "section...) isn't recoverable from the .aux; fix by hand.")
        return m.group(0)

    new_text = _REF_CMD_RE.sub(repl, text)
    return new_text, n_replaced, warnings


# ---------------------------------------------------------------------------
# Figure extraction and \includegraphics rewriting
# ---------------------------------------------------------------------------

_FIGURE_ENV_RE = re.compile(r'\\begin\{figure\}.*?\\end\{figure\}', re.DOTALL)
_INCLUDEGRAPHICS_RE = re.compile(r'\\includegraphics(\[[^\]]*\])?\{[^}]*\}')


def _is_commented(text, pos):
    """True if position `pos` is preceded on its line by an unescaped '%'
    (i.e. `pos` falls inside a LaTeX comment)."""
    line_start = text.rfind('\n', 0, pos) + 1
    line_prefix = text[line_start:pos]
    i = 0
    while True:
        idx = line_prefix.find('%', i)
        if idx == -1:
            return False
        nbs = 0
        j = idx - 1
        while j >= 0 and line_prefix[j] == '\\':
            nbs += 1
            j -= 1
        if nbs % 2 == 0:
            return True
        i = idx + 1


def _live_figure_envs(text):
    """Iterate \\begin{figure}...\\end{figure} blocks, in document order,
    skipping any whose \\begin{figure} is commented out (e.g. leftover
    template boilerplate like '% \\begin{figure}...% \\end{figure}')."""
    for m in _FIGURE_ENV_RE.finditer(text):
        if not _is_commented(text, m.start()):
            yield m


def count_figure_envs(text):
    """Count live (non-commented) \\begin{figure}...\\end{figure} blocks --
    one per page produced by make_single_figure.sh's harness."""
    return sum(1 for _ in _live_figure_envs(text))


def rewrite_figure_includes(text):
    """
    Within each \\begin{figure}...\\end{figure} block, in document order,
    replace the first \\includegraphics{...}'s path with a bare 'figN.pdf'
    (N = 1-based position among figure environments, matching the page
    order make_single_figure.sh produces), keeping any [options]. Any
    additional \\includegraphics in the same block (multi-panel figures)
    are removed, since fig N.pdf is the single cropped composite.

    Returns (new_text, n_figs).
    """
    out_parts = []
    last_end = 0
    n = 0
    for m in _live_figure_envs(text):
        out_parts.append(text[last_end:m.start()])
        n += 1
        block = m.group(0)
        matches = list(_INCLUDEGRAPHICS_RE.finditer(block))
        if matches:
            for im in reversed(matches):
                if im is matches[0]:
                    opts = im.group(1) or ''
                    repl = r'\includegraphics' + opts + '{fig' + str(n) + '.pdf}'
                else:
                    repl = ''
                block = block[:im.start()] + repl + block[im.end():]
        out_parts.append(block)
        last_end = m.end()
    out_parts.append(text[last_end:])
    return ''.join(out_parts), n


def make_single_figures(main_tex_path):
    """Run make_single_figure.sh on main_tex_path (in its own directory),
    producing fig1.pdf, fig2.pdf, ... beside it."""
    result = subprocess.run(
        ['bash', str(MAKE_SINGLE_FIGURE.resolve()), main_tex_path.name],
        cwd=main_tex_path.parent,
    )
    if result.returncode != 0:
        sys.exit(f'make_single_figure.sh failed (exit {result.returncode})')


# ---------------------------------------------------------------------------
# Bibliography inlining
# ---------------------------------------------------------------------------

# Line-anchored so a leading '%' (already-commented line) breaks the '^[ \t]*\'
# anchor and is skipped.
_BIBLIOGRAPHY_RE = re.compile(r'^([ \t]*)(\\bibliography\{[^}]*\})', re.MULTILINE)
_BIBSTYLE_RE = re.compile(r'^([ \t]*)(\\bibliographystyle\{[^}]*\})', re.MULTILINE)


def inline_bbl(text, bbl_text):
    """
    Replace the first live \\bibliography{...} with the inlined contents of
    bbl_text (a compiled .bbl, i.e. a thebibliography environment), preceded
    by the commented-out \\bibliography{...} line. Also comments out the
    first live \\bibliographystyle{...}, if present.

    Returns (new_text, status), where status is 'inlined' or
    'no-bibliography' (no live \\bibliography{} found; text is unchanged).
    """
    if not _BIBLIOGRAPHY_RE.search(text):
        return text, 'no-bibliography'

    text = _BIBSTYLE_RE.sub(r'\1%\2', text, count=1)

    def repl(m):
        indent, cmd = m.groups()
        return f'{indent}%{cmd}\n\n{bbl_text.strip()}\n'

    text = _BIBLIOGRAPHY_RE.sub(repl, text, count=1)
    return text, 'inlined'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def extract_main(combined_tex, aux_path=None, bbl_path=None, outdir=None,
                  make_figures=True, inline_bib=True):
    """
    Write a main-text-only manuscript derived from combined_tex into outdir.

    combined_tex : path to the combined main+SI .tex (read-only)
    aux_path     : path to the combined document's .aux (default:
                   combined_tex with .aux suffix); used to flatten SI refs
    bbl_path     : path to the combined document's .bbl (default:
                   combined_tex with .bbl suffix); inlined in place of
                   \\bibliography{} if inline_bib is True
    outdir       : output directory (default: <combined_tex stem>_main/)
    make_figures : if True, run make_single_figure.sh and rewrite
                   \\includegraphics to figN.pdf
    inline_bib   : if True, inline the .bbl and comment out
                   \\bibliography{}/\\bibliographystyle{}

    Returns the path to the written main.tex.
    """
    combined_tex = Path(combined_tex)
    if not combined_tex.exists():
        sys.exit(f'Input not found: {combined_tex}')

    aux_path = Path(aux_path) if aux_path else combined_tex.with_suffix('.aux')
    bbl_path = Path(bbl_path) if bbl_path else combined_tex.with_suffix('.bbl')
    outdir = Path(outdir) if outdir else combined_tex.parent / f'{combined_tex.stem}_main'
    out_tex = outdir / 'main.tex'

    if out_tex.resolve() == combined_tex.resolve():
        sys.exit('Refusing to write main.tex over the input file '
                 f'({combined_tex}); choose a different --outdir.')

    input_bytes = combined_tex.read_bytes()
    input_hash = hashlib.sha256(input_bytes).hexdigest()
    text = input_bytes.decode('utf-8')

    si_start, how = find_si_start(text)
    if si_start is None:
        sys.exit(
            'Could not locate the SI boundary: no %% SI_BEGIN sentinel, '
            'no \\section*{Supporting Information.../\\section{Supplement...} '
            'header, and no \\renewcommand\\thefigure{S\\arabic{figure}}. '
            'Aborting -- nothing written.')
    print(f'SI boundary found via {how}')

    main_text = strip_si(text, si_start)

    if aux_path.exists():
        aux_labels = parse_aux_labels(aux_path.read_text(encoding='utf-8'))
    else:
        aux_labels = {}
        print(f'Warning: .aux not found ({aux_path}); SI \\ref{{}}s will not '
              'be flattened and will render as ?? if referenced.',
              file=sys.stderr)

    main_text, n_refs, warnings = flatten_refs(main_text, aux_labels)
    for w in warnings:
        print(f'Warning: {w}', file=sys.stderr)

    if inline_bib:
        if bbl_path.exists():
            main_text, bib_status = inline_bbl(main_text, bbl_path.read_text(encoding='utf-8'))
            if bib_status == 'inlined':
                print(f'Inlined {bbl_path} '
                      r'(\bibliography{}/\bibliographystyle{} commented out)')
            else:
                print(f'Warning: no \\bibliography{{}} found in main text; '
                      f'{bbl_path} not inlined.', file=sys.stderr)
        else:
            print(f'Warning: .bbl not found ({bbl_path}); '
                  r'\bibliography{} left live -- main.tex will need bibtex '
                  'to compile.', file=sys.stderr)

    outdir.mkdir(parents=True, exist_ok=True)
    out_tex.write_text(main_text, encoding='utf-8')
    print(f'Wrote {out_tex} ({n_refs} SI ref(s) flattened)')

    if make_figures:
        n_figs = count_figure_envs(main_text)
        if n_figs == 0:
            print('No figure environments found; skipping figure extraction.')
        else:
            make_single_figures(out_tex)
            final_text, n_rewritten = rewrite_figure_includes(
                out_tex.read_text(encoding='utf-8'))
            out_tex.write_text(final_text, encoding='utf-8')
            print(f'Generated fig1.pdf ... fig{n_figs}.pdf '
                  f'({n_rewritten} figure environment(s) rewritten)')

    # Never-overwrite-input invariant.
    if hashlib.sha256(combined_tex.read_bytes()).hexdigest() != input_hash:
        sys.exit(f'ERROR: input file {combined_tex} was modified during '
                 'extraction. This should never happen.')

    return out_tex


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('combined_tex', help='Combined main+SI .tex (read-only)')
    parser.add_argument('combined_aux', nargs='?',
                         help='Combined document .aux (default: <stem>.aux)')
    parser.add_argument('--outdir', help='Output directory (default: <stem>_main/)')
    parser.add_argument('--no-figures', action='store_true',
                         help='Skip figure extraction and \\includegraphics rewriting')
    parser.add_argument('--bbl', help='Combined document .bbl (default: <stem>.bbl)')
    parser.add_argument('--no-bib', action='store_true',
                         help='Skip .bbl inlining; leave \\bibliography{} live')
    args = parser.parse_args()

    extract_main(args.combined_tex, args.combined_aux, args.bbl, args.outdir,
                  make_figures=not args.no_figures,
                  inline_bib=not args.no_bib)


if __name__ == '__main__':
    main()
