#!/usr/bin/env python3
"""
beamer_to_agu.py
----------------
Convert a Beamer slide deck (.tex) to an AGU journal manuscript skeleton
(documentclass{agujournal2019}).

Usage:
    python beamer_to_agu.py slides.tex [output.tex]

If no output file is given, writes to <input_stem>_agu.tex.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from beamer_common import (
    _parse_inst_blocks,
    _extract_preamble_arg,
    _abbreviate_name,
    _extract_bib_file,
    extract_passthrough_packages,
    preprocess_body,
    build_event_list,
    extract_abstract,
    extract_email,
    extract_key_points,
    extract_plain_language_summary,
    extract_sentinel_block,
    is_si_section,
    strip_frame_wrappers,
    assemble_body,
    transform_content,
)

_KP_DEFAULTS = [
    'Key point 1 here (under 140 characters)',
    'Key point 2 here (under 140 characters)',
    'Key point 3 here (under 140 characters)',
]


# ---------------------------------------------------------------------------
# AGU-specific: author/affiliation parsing
# ---------------------------------------------------------------------------

def _parse_authors_affiliations_agu(src):
    """
    Parse beamer \\author{} and \\institute{} into AGU-ready structures.

    AGU uses numeric \\affil{N} (not letter-based like AMS), so \\inst{N}
    numbers map directly.

    Returns:
      authors_block      : \\authors{...} string
      affiliation_lines  : list of \\affiliation{N}{text} strings
      corresponding      : (full_name, abbreviated_name) for first author
    """
    parsed, inst_map, inst_nums = _parse_inst_blocks(src)

    if not inst_nums:
        inst_nums = list(range(1, len(parsed) + 1))
        inst_map = {i + 1: 'Department, Institution, City, Country'
                    for i in range(len(parsed))}
        parsed = [(name, i + 1) for i, (name, _) in enumerate(parsed)]

    author_parts = []
    for name, num in parsed:
        n = num if num is not None else inst_nums[0]
        author_parts.append(name + r'\affil{' + str(n) + '}')

    if len(author_parts) == 1:
        authors_block = r'\authors{' + author_parts[0] + '}'
    elif len(author_parts) == 2:
        authors_block = (r'\authors{' + author_parts[0] + ' and ' +
                         author_parts[1] + '}')
    else:
        authors_block = (r'\authors{' + ', '.join(author_parts[:-1]) +
                         ', and ' + author_parts[-1] + '}')

    affiliation_lines = []
    for num in inst_nums:
        text = inst_map.get(num, 'Department, Institution, City, Country')
        affiliation_lines.append(r'\affiliation{' + str(num) + '}{' + text + '}')

    first_name = parsed[0][0] if parsed else 'First Last'
    corresponding = (first_name, _abbreviate_name(first_name))

    return authors_block, affiliation_lines, corresponding


# ---------------------------------------------------------------------------
# AGU-specific: citation remapping (natbib -> apacite)
# ---------------------------------------------------------------------------

def _remap_citations_to_apacite(text):
    r"""
    Convert natbib citation commands to apacite equivalents required by AGU.

    Mappings:
      \citet{key}               -> \citeA{key}
      \citet[post]{key}         -> \citeA[post]{key}   (approximate)
      \citep{key}               -> \cite{key}
      \citep[post]{key}         -> \cite[post]{key}
      \citep[pre][post]{key}    -> \cite<pre>[post]{key}
      \citealp{key}             -> \cite{key}
      \citeauthor{key}          -> \citeA{key}
      \citeyear{key}            -> \citeyear{key}      (unchanged; apacite has \citeyear)
    """
    # \citet[pre][post]{key} -> \citeA<pre>[post]{key} or \citeA[post]{key}
    def _citet_two_args(m):
        pre, post = m.group(1), m.group(2)
        if pre.strip():
            return r'\citeA<' + pre + '>[' + post + ']{'
        else:
            return r'\citeA[' + post + ']{'
    text = re.sub(r'\\citet\[([^\]]*)\]\[([^\]]*)\]\{', _citet_two_args, text)
    # \citet[post]{key} -> \citeA[post]{key}  (one optional arg)
    text = re.sub(r'\\citet\[([^\]]*)\]\{', r'\\citeA[\1]{', text)
    # \citet{key} -> \citeA{key}
    text = re.sub(r'\\citet\{', r'\\citeA{', text)

    # \citep[pre][post]{key} -> \cite<pre>[post]{key}  (two optional args)
    text = re.sub(r'\\citep\[([^\]]*)\]\[([^\]]*)\]\{', r'\\cite<\1>[\2]{', text)
    # \citep[post]{key} -> \cite[post]{key}  (one optional arg)
    text = re.sub(r'\\citep\[([^\]]*)\]\{', r'\\cite[\1]{', text)
    # \citep{key} -> \cite{key}
    text = re.sub(r'\\citep\{', r'\\cite{', text)

    # \citealp -> \cite  (no parentheses in apacite; closest match)
    text = re.sub(r'\\citealp\[([^\]]*)\]\{', r'\\cite[\1]{', text)
    text = re.sub(r'\\citealp\{', r'\\cite{', text)

    # \citeauthor -> \citeA
    text = re.sub(r'\\citeauthor\{', r'\\citeA{', text)

    return text


# ---------------------------------------------------------------------------
# AGU-specific: equation wrapping for line numbers
# ---------------------------------------------------------------------------

def _wrap_equations_linenomath(text):
    r"""
    Wrap display math environments in \begin{linenomath*}...\end{linenomath*}
    as required by AGU when line numbers are active.
    Skips environments already inside linenomath*.
    """
    envs = ['equation', 'equation*', 'eqnarray', 'eqnarray*',
            'align', 'align*', 'multline', 'multline*', 'gather', 'gather*']

    for env in envs:
        pat = re.compile(
            r'(\\begin\{' + re.escape(env) + r'\}.*?\\end\{' + re.escape(env) + r'\})',
            re.DOTALL
        )
        result = []
        pos = 0
        depth = 0
        for m in pat.finditer(text):
            before = text[pos:m.start()]
            result.append(before)
            depth += (before.count('\\begin{linenomath*}') -
                      before.count('\\end{linenomath*}'))
            if depth > 0:
                result.append(m.group(0))
            else:
                result.append(
                    '\\begin{linenomath*}\n' + m.group(0) + '\n\\end{linenomath*}'
                )
            pos = m.end()
        result.append(text[pos:])
        text = ''.join(result)

    # Display math \[...\] (not already in linenomath*)
    disp_pat = re.compile(r'(\\\[.*?\\\])', re.DOTALL)
    result = []
    pos = 0
    depth = 0
    for m in disp_pat.finditer(text):
        before = text[pos:m.start()]
        result.append(before)
        depth += (before.count('\\begin{linenomath*}') -
                  before.count('\\end{linenomath*}'))
        if depth > 0:
            result.append(m.group(0))
        else:
            result.append(
                '\\begin{linenomath*}\n' + m.group(0) + '\n\\end{linenomath*}'
            )
        pos = m.end()
    result.append(text[pos:])
    text = ''.join(result)

    return text


# ---------------------------------------------------------------------------
# AGU-specific: preamble and postamble
# ---------------------------------------------------------------------------


def _make_si_checklist(n_figs, n_tables):
    """Build the Contents of this file enumerate block for the SI header."""
    lines = [
        r'\noindent\textbf{Contents of this file}',
        r'%%%Remove or add items as needed%%%',
        r'\begin{enumerate}',
        r'%\item Text S1 to Sx',   # commented out — no SI text example
    ]
    if n_figs == 0:
        lines.append(r'%\item Figures S1 to Sx')
    elif n_figs == 1:
        lines.append(r'\item Figure S1')
    else:
        lines.append(r'\item Figures S1 to S' + str(n_figs))
    if n_tables == 0:
        lines.append(r'%\item Tables S1 to Sx')
    elif n_tables == 1:
        lines.append(r'\item Table S1')
    else:
        lines.append(r'\item Tables S1 to S' + str(n_tables))
    lines.append(r'%if Tables are larger than 1 page, upload as separate excel file')
    lines.append(r'\end{enumerate}')
    return '\n'.join(lines)


def _build_si_header(title, authors_block, affiliation_lines, n_si_figs=0, n_si_tables=0):
    """Build the SI section header appended after \\bibliography{}.

    Uses $^N$ superscripts for affiliation markers (matching AGU SI style).
    """
    # \affil{N} -> $^N$ for SI-style inline superscripts
    si_authors = re.sub(r'\\affil\{(\d+)\}', lambda m: '$^' + m.group(1) + '$', authors_block)

    aff_items = []
    for line in affiliation_lines:
        m = re.match(r'\\affiliation\{(\d+)\}\{(.+)\}', line, re.DOTALL)
        if m:
            text = re.sub(r'\s+', ' ', m.group(2)).strip()
            aff_items.append(r'\noindent $^' + m.group(1) + r'${' + text + '}')
    aff_block = '\n\n'.join(aff_items)

    contents_boilerplate = _make_si_checklist(n_si_figs, n_si_tables)

    return '\n'.join([
        r'%% SI_BEGIN',
        r'\clearpage',
        r'\setcounter{page}{1}',
        '',
        r"\section*{Supporting Information for ``" + title + "''}",
        r'\begin{center}',
        r'\noindent',
        si_authors,
        '',
        aff_block,
        '',
        r'\end{center}',
        '',
        contents_boilerplate,
        '',
        r'\clearpage',
    ])


def _extract_journal_name(src):
    """
    Return journal name from a commented directive in the Beamer source, e.g.:
      % target journal for AGU conversion:
      %\\journalname{Geophysical Research Letters}
    Falls back to 'JGR: Atmospheres' if not found.
    """
    m = re.search(r'^%\\journalname\{([^}]+)\}', src, re.MULTILINE)
    return m.group(1) if m else 'JGR: Atmospheres'


def _build_agu_preamble(title, authors_block, affiliation_lines,
                         corresponding, abstract_text,
                         pls_text='Enter plain language summary here.',
                         journal='JGR: Atmospheres',
                         keypoints_items=None,
                         pkg_ams='',
                         email='email@institution.edu'):
    """
    Build the AGU manuscript preamble.

    corresponding: (full_name, abbreviated_name) tuple for first author.
    """
    full_name, _abbrev = corresponding
    aff_lines = '\n'.join(affiliation_lines)
    kp = list((keypoints_items or _KP_DEFAULTS)[:3])
    while len(kp) < 3:
        kp.append(_KP_DEFAULTS[len(kp)])
    kp_lines = '\n'.join(r'\item ' + p for p in kp)

    pkg_ams_block = ('\n' + pkg_ams) if pkg_ams else ''
    return rf"""\documentclass[draft]{{agujournal2019}}
\usepackage{{url}}
\usepackage{{lineno}}{pkg_ams_block}
\linenumbers

%% Journal name — change to match target journal
%% Options: JGR Atmospheres, JGR Oceans, GRL, GC Cubed, etc.
\journalname{{{journal}}}

%For most journals, Research Articles are allowed to be up to 25 publication units (PU), where 1 PU is 500 words or 1 display element (figure or table). Research Letters for Geophysical Research Letters have a maximum length of 12 publication units. Longer papers are not considered in GRL and will be returned for shortening.

%Word count does NOT include the title, authors, affiliations, key points, keywords, text in tables (but not captions) and references. Longer papers are assessed an excess length fee. For most journals, Commentaries are limited to 6 publication units (recommended length is about 2000 words and 1-2 figures).

\begin{{document}}

%TC:ignore
\title{{{title}}}

{authors_block}

{aff_lines}

\correspondingauthor{{{full_name}}}{{{email}}}

\begin{{keypoints}}
{kp_lines}
\end{{keypoints}}
%TC:endignore

\begin{{abstract}}
{abstract_text}
\end{{abstract}}

%TC:ignore
\section*{{Plain Language Summary}}
{pls_text}
%TC:endignore

"""


_AGU_CLOSE = r"""
%TC:endignore
\end{document}
"""

# Per-section stubs (fallback when sentinel not present in source).
# Each stub includes the AGU header so it can be emitted standalone.
_STUBS = {
    'OPENRESEARCH': (
        '\\section*{Open Research Section}\n'
        'Data and code availability statement here. Data cannot be listed as\n'
        "``available from the authors.''"
    ),
    'COI': (
        '\\section*{Conflict of Interest}\n'
        'The authors declare no conflicts of interest.'
    ),
    'ACKS': (
        '\\acknowledgments\n'
        'Enter acknowledgments here.'
    ),
}

# AGU headers injected by the converter for each sentinel label.
_SENTINEL_HEADERS = {
    'OPENRESEARCH': r'\section*{Open Research Section}',
    'COI':          r'\section*{Conflict of Interest}',
    'ACKS':         r'\acknowledgments',
}


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

_AGU_FIGURE_OPTS = {
    'placement': '',        # no [h]; AGU default float is tbp
    'centering': False,     # no \centering
    'noindent': True,       # \noindent before \includegraphics
    'default_width': r'\textwidth',  # add width=\textwidth when no options
}


def convert(input_path, output_path, journal=None):
    src = Path(input_path).read_text(encoding='utf-8')

    # --- Extract title and authors from beamer preamble ---------------------
    title_text = _extract_preamble_arg(src, 'title') or 'TITLE'

    authors_block, affiliation_lines, corresponding = \
        _parse_authors_affiliations_agu(src)

    # --- Extract sentinel blocks from src BEFORE preprocessing ---------------
    # Sentinel comment lines (%% AGU_*_BEGIN/END) are stripped by
    # preprocess_body, so detection must run on the original source.
    # The sentinel-wrapped content is removed from src before preprocessing
    # so those frames never enter the manuscript event list.
    sentinel_inner = {}   # label -> raw inner text (frame + content)
    sentinel_regions = [] # (start, end) in src
    for label in _SENTINEL_HEADERS:
        block = extract_sentinel_block(src, label)
        if block:
            start, end, inner = block
            sentinel_inner[label] = inner
            sentinel_regions.append((start, end))

    src_for_body = src
    for start, end in sorted(sentinel_regions, reverse=True):
        src_for_body = src_for_body[:start] + src_for_body[end:]

    # --- Preprocess body (sentinel-stripped source) -------------------------
    body = preprocess_body(src_for_body)

    # --- Build event list (AGU: strip \bibliographystyle) -------------------
    events = build_event_list(body, keep_bibliographystyle=False)

    # --- Assemble endmatter from sentinel blocks (or stubs) -----------------
    # Each sentinel wraps a Beamer frame that renders in slides normally;
    # the converter strips the frame wrappers and injects the AGU section header.
    endmatter_pieces = []
    for label, agu_header in _SENTINEL_HEADERS.items():
        if label in sentinel_inner:
            frame_body = strip_frame_wrappers(sentinel_inner[label])
            frame_body = re.sub(r'\\fig\{([^}]+)\}', r'\\includegraphics{\1}', frame_body)
            processed = transform_content(frame_body, figure_opts=_AGU_FIGURE_OPTS)
            endmatter_pieces.append(agu_header + '\n' + processed.strip())
        else:
            endmatter_pieces.append(_STUBS[label])

    bib_file = _extract_bib_file(src)
    bib_line = r'\bibliography{' + bib_file + '}'

    # Count SI figures and tables for the checklist (scan before appending endmatter)
    _supp_i = next(
        (i for i, (_, etype, content) in enumerate(events)
         if etype == 'section' and is_si_section(content)),
        None
    )
    n_si_figs, n_si_tables = 0, 0
    if _supp_i is not None:
        _si_raw = '\n'.join(c for _, t, c in events[_supp_i + 1:] if t == 'frame')
        n_si_figs = len(re.findall(r'\\fig\{', _si_raw))
        if n_si_figs == 0:
            n_si_figs = len(re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{', _si_raw))
        n_si_tables = len(re.findall(r'\\begin\{tabular', _si_raw))
        if n_si_tables == 0:
            n_si_tables = len(re.findall(r'\\begin\{table', _si_raw))

    si_header = _build_si_header(title_text, authors_block, affiliation_lines,
                                 n_si_figs=n_si_figs, n_si_tables=n_si_tables)
    em_text = '%TC:ignore\n\n' + '\n\n'.join(endmatter_pieces) + '\n\n' + bib_line + '\n\n' + si_header

    # Append at end of body; the Supplemental reorder below repositions it.
    events.append((len(body) + 1, 'passthrough', em_text))
    events.sort(key=lambda x: x[0])

    # Move end-matter before any Supplemental section so references
    # appear before the appendix in the output.
    supp_idx = next(
        (i for i, (_, etype, content) in enumerate(events)
         if etype == 'section' and is_si_section(content)),
        None
    )
    # em_text was appended with position len(body)+1 — always sorts last
    em_idx = len(events) - 1
    if supp_idx is not None and em_idx > supp_idx:
        em_event = events.pop(em_idx)
        events.insert(supp_idx, em_event)

    # Strip the supplemental section marker (keep its content frames).
    events = [e for e in events
              if not (e[1] == 'section' and is_si_section(e[2]))]

    postamble = _AGU_CLOSE

    # --- Extract preamble blocks from events --------------------------------
    abstract_text, events = extract_abstract(events)
    pls_text, events = extract_plain_language_summary(events)
    if pls_text is None:
        pls_text = 'Enter plain language summary here.'
    keypoints_items, events = extract_key_points(events)

    # --- Build manuscript body ----------------------------------------------
    if not events:
        print("Warning: no frames or sections found; writing body as-is.",
              file=sys.stderr)
        manuscript_body = transform_content(body, figure_opts=_AGU_FIGURE_OPTS)
    else:
        manuscript_body = assemble_body(events, figure_opts=_AGU_FIGURE_OPTS)

    # --- AGU post-processing ------------------------------------------------
    manuscript_body = _remap_citations_to_apacite(manuscript_body)
    manuscript_body = _wrap_equations_linenomath(manuscript_body)

    # --- Write output -------------------------------------------------------
    journal_name = journal or _extract_journal_name(src)
    pkg_ams = extract_passthrough_packages(src)
    preamble = _build_agu_preamble(
        title_text, authors_block, affiliation_lines,
        corresponding, abstract_text, pls_text, journal_name, keypoints_items,
        pkg_ams=pkg_ams,
        email=extract_email(src),
    )
    out = preamble + manuscript_body + '\n' + postamble
    Path(output_path).write_text(out, encoding='utf-8')
    print(f"Written: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='Beamer .tex file')
    parser.add_argument('output', nargs='?', help='Output .tex file (default: <input>_agu.tex)')
    parser.add_argument('--journal', metavar='NAME',
                        help='Journal name for \\journalname{}; overrides %\\journalname{} in source')
    args = parser.parse_args()

    output_file = args.output or str(Path(args.input).stem) + '_agu.tex'
    convert(args.input, output_file, journal=args.journal)
