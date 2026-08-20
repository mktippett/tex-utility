#!/usr/bin/env python3
"""
beamer_to_ams.py
----------------
Convert a Beamer slide deck (.tex) to an AMS manuscript skeleton
(documentclass{ametsocV6.1}).

Usage:
    python beamer_to_ams.py slides.tex [output.tex]

If no output file is given, writes to <input_stem>_manuscript.tex.
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
    _extract_bib_style,
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


# ---------------------------------------------------------------------------
# AMS-specific: author/affiliation parsing
# ---------------------------------------------------------------------------

def _parse_authors_affiliations(src):
    """
    Parse beamer \\author{} and \\institute{} into AMS-ready structures.

    Returns:
      authors  : [(name_str, aff_letter), ...]   first author is corresponding
      aff_block: the full \\affiliation{...} string
    """
    aff_letters = 'abcdefghijklmnopqrstuvwxyz'
    parsed, inst_map, inst_nums = _parse_inst_blocks(src)

    if not inst_nums:
        # No \inst{} markup: every author shares the single \institute{}
        # (Beamer semantics). Placeholder only when \institute{} is absent too.
        inst_nums = [1]
        inst_map.setdefault(1, 'Department, Institution, City, State')
        parsed = [(name, 1) for name, _ in parsed]

    inst_to_aff = {num: aff_letters[i] for i, num in enumerate(inst_nums)}
    authors = [(name, inst_to_aff.get(num, aff_letters[0]))
               for name, num in parsed]

    entries = []
    for num in inst_nums:
        letter = inst_to_aff[num]
        text = inst_map.get(num, 'Department, Institution, City, State')
        entries.append(r'  \aff{' + letter + '}{' + text + '}')
    aff_block = '\\affiliation{\n' + '\\\\\n'.join(entries) + '\n}'

    return authors, aff_block


def _build_si_titlepage(title, authors, aff_block, email):
    r"""
    Build a manual "Supplemental material for:" title page, mirroring AMS's
    own \@maketitle layout (ametsocV6.1.cls) since \maketitle self-destructs
    after the first call (\global\let\maketitle\relax) and cannot be reused
    for the SI. Analogous to beamer_to_agu.py's _build_si_header(), but styled
    after the AMS title page rather than AGU's SI header.

    authors  : [(name_str, aff_letter), ...] from _parse_authors_affiliations;
               first author is corresponding.
    aff_block: the \affiliation{ \aff{a}{...}\\ \aff{b}{...} } string from
               _parse_authors_affiliations.
    """
    last = len(authors) - 1
    author_parts = []
    for idx, (name, letter) in enumerate(authors):
        part = name + r'\aff{' + letter + '}'
        if idx != last:
            part += ','
        if idx == last and last > 0:
            part = 'and ' + part
        author_parts.append(part)
    authors_line = ' '.join(author_parts)

    aff_entries = re.findall(r'\\aff\{([a-z])\}\{([^}]+)\}', aff_block)
    aff_lines = [r'\aff{' + letter + '}' + re.sub(r'\s+', ' ', text).strip()
                 for letter, text in aff_entries]
    aff_block_text = '\\\\\n'.join(aff_lines)

    corr_name = authors[0][0] if authors else 'First Last'

    return '\n'.join([
        r'\setcounter{page}{1}',
        r'\begin{center}',
        r'{\large\bfseries Supplemental material for:\par}',
        r'\vskip 12pt',
        r'{\large\bfseries ' + title + r'\par}',
        r'\vskip 12pt',
        r'{\normalsize ' + authors_line + r'\par}',
        r'\vskip 6pt',
        r'{\it ' + aff_block_text + r'\par}',
        r'\end{center}',
        r'\vskip 12pt',
        r'\noindent{\it Corresponding author}: ' + corr_name + ', ' + email,
        r'\clearpage',
    ])


# ---------------------------------------------------------------------------
# AMS-specific: preamble and postamble
# ---------------------------------------------------------------------------

def _build_preamble(title, authors_block, affiliation_block, abstract_text,
                    statement_block,
                    pkg_ams=r'\usepackage{amsmath,amssymb}'):
    # No \journal{}-equivalent directive: AMS removed the per-journal
    # macro from ametsoc.cls in package v5.0 (2020) -- see
    # ams/AMS LaTeX Package V6.1/README.txt, "Removed option to select
    # journal name for two-column". Neither the current standalone
    # ametsocV6.1.cls nor templateV6.1.tex has any journal-selection
    # command left to target, live or commented.
    return rf"""\documentclass{{ametsocV6.1}}

%% ametsocV6.1.cls loads mathptmx/newtxtext (Times-like PostScript fonts)
%% but never loads fontenc itself. Without T1, non-ASCII text-mode
%% commands like \l fall back to OT1 Computer Modern glyphs mid-font
%% family, producing broken spacing -- e.g. a Polish surname like
%% Plotka renders as two words instead of one. T1 must come first.
\usepackage[T1]{{fontenc}}

%% AMS packages (ametsoc.sty is already loaded by the class)
\usepackage{{graphicx}}
{pkg_ams}
\usepackage{{natbib}}
\usepackage{{caption}}

\begin{{document}}

%TC:ignore
\title{{{title}}}

{authors_block}

{affiliation_block}

\abstract{{
  {abstract_text}
}}

\maketitle
%TC:endignore

{statement_block}
"""


def _build_statement_block(pls_text):
    r"""
    Commented \statement block, mirroring the optional significance-statement
    stub in the official templateV6.1.tex (all AMS journals except BAMS;
    max 120 words).

    When the slides carry a Plain Language Summary, its text is included
    (commented) as a starting point.  Emitted commented-out rather than live
    because a PLS is typically longer than 120 words -- the author trims,
    then uncomments.
    """
    lines = [
        '%% Significance statement (optional, max 120 words): trim the text',
        r'%% below, then uncomment \statement and the text lines.',
        r'%\statement',
    ]
    if pls_text:
        for line in pls_text.splitlines():
            lines.append('%  ' + line.strip())
    else:
        lines.append('%  Enter significance statement here, no more than 120 words.')
    return '\n'.join(lines)


# AMS word-count rules exclude figure/table captions (unlike AGU, which counts
# them) -- caption_tcignore=True wraps each generated \caption{} in
# %TC:ignore/%TC:endignore so texcount -sum excludes it.
_AMS_FIGURE_OPTS = {
    'caption_tcignore': True,
}

# Endmatter sentinel labels shared with beamer_to_agu.py (%% <LABEL>_BEGIN/END
# around normal Beamer frames; canonical labels from
# beamer_common._SENTINEL_ALIASES, legacy AGU_* spellings accepted).
# AMS mapping: DATA -> the required \datastatement, ACKS -> \acknowledgments;
# COI has no AMS section of its own, so its text is appended to the
# acknowledgments paragraph.
_ENDMATTER_STUBS = {
    'ACKS': 'Enter acknowledgments here.',
    'DATA': ('Data availability statement here: where the data '
             'supporting the findings can be accessed (repository '
             'and DOI/URL). If access is restricted, state that '
             'here.'),
}


def _sentinel_content(sentinel_inner, label):
    """Frame body of a sentinel block, transformed to manuscript prose,
    or None if the sentinel is absent."""
    inner = sentinel_inner.get(label)
    if inner is None:
        return None
    frame_body = strip_frame_wrappers(inner)
    frame_body = re.sub(r'\\fig\{([^}]+)\}', r'\\includegraphics{\1}', frame_body)
    return transform_content(frame_body, figure_opts=_AMS_FIGURE_OPTS).strip()


def _build_endmatter(sentinel_inner):
    r"""
    \acknowledgments + \datastatement block, emitted immediately before the
    bibliography.  Wrapped in %TC:ignore -- AMS's word-limit rule excludes
    acknowledgments and the data availability statement.
    """
    acks = _sentinel_content(sentinel_inner, 'ACKS') or _ENDMATTER_STUBS['ACKS']
    coi = _sentinel_content(sentinel_inner, 'COI')
    if coi:
        acks += '\n\n' + coi
    data = (_sentinel_content(sentinel_inner, 'DATA')
            or _ENDMATTER_STUBS['DATA'])
    return '\n'.join([
        '%TC:ignore',
        r'\acknowledgments',
        acks,
        '',
        r'\datastatement',
        data,
        '%TC:endignore',
    ])


def _build_postamble(bib_style, bib_file):
    lines = []
    if bib_style:
        lines.append(r'\bibliographystyle{' + bib_style + '}')
    lines.append(r'\bibliography{' + bib_file + '}')
    lines.append(r'\end{document}')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert(input_path, output_path):
    src = Path(input_path).read_text(encoding='utf-8')

    title_text = _extract_preamble_arg(src, 'title') or 'TITLE'

    # --- Extract endmatter sentinel blocks BEFORE preprocessing --------------
    # Same %% <LABEL>_BEGIN/END convention as beamer_to_agu.py: the sentinel
    # comment lines are stripped by preprocess_body, so detection must run on
    # the original source, and the wrapped frames are removed from src so
    # they never enter the manuscript event list.
    sentinel_inner = {}   # label -> raw inner text (frame + content)
    sentinel_regions = [] # (start, end) in src
    for label in ('DATA', 'COI', 'ACKS'):
        block = extract_sentinel_block(src, label)
        if block:
            start, end, inner = block
            sentinel_inner[label] = inner
            sentinel_regions.append((start, end))

    src_for_body = src
    for start, end in sorted(sentinel_regions, reverse=True):
        src_for_body = src_for_body[:start] + src_for_body[end:]

    authors, affiliation_block = _parse_authors_affiliations(src)

    email = extract_email(src)
    author_parts = []
    last = len(authors) - 1
    for idx, (name, aff) in enumerate(authors):
        part = name
        if idx != last:
            part += ','
        part += r'\aff{' + aff + '}'
        if idx == 0:
            abbrev = _abbreviate_name(name)
            part += r'\correspondingauthor{' + abbrev + ',\n    ' + email + '}'
        if idx == last and last > 0:
            part = 'and ' + part
        author_parts.append(part)
    authors_block = r'\authors{' + ' '.join(author_parts) + '}'

    body = preprocess_body(src_for_body)
    events = build_event_list(body, keep_bibliographystyle=False)
    abstract_text, events = extract_abstract(events)

    # AGU-oriented front matter has no AMS slot: Key points are dropped;
    # the Plain Language Summary feeds the commented \statement block.
    _keypoints, events = extract_key_points(events)
    pls_text, events = extract_plain_language_summary(events)
    statement_block = _build_statement_block(pls_text)

    endmatter = _build_endmatter(sentinel_inner)

    bib_style = _extract_bib_style(src)
    bib_file = _extract_bib_file(src)

    # Move endmatter + bibliography before any supplemental section,
    # mirroring AGU logic.
    supp_idx = next(
        (i for i, (_, etype, content) in enumerate(events)
         if etype == 'section' and is_si_section(content)),
        None
    )
    if supp_idx is not None:
        # Drop any \bibliography{} passthrough events already parsed from the body
        # to avoid duplication when we inject it explicitly below.
        events = [e for e in events
                  if not (e[1] == 'passthrough' and
                          re.search(r'\\bibliography\{', e[2]))]
        supp_idx = next(
            (i for i, (_, etype, content) in enumerate(events)
             if etype == 'section' and is_si_section(content)),
            None
        )
        bib_lines = [endmatter, '']
        if bib_style:
            bib_lines.append(r'\bibliographystyle{' + bib_style + '}')
        bib_lines.append(r'\bibliography{' + bib_file + '}')
        bib_lines.append(r'\clearpage')
        bib_lines.append(r'%% SI_BEGIN')
        # SI is not counted against the AMS word limit -- open the ignore
        # region here; extract_main.py closes/rebalances it when it later
        # strips the SI back out for a main-only submission.
        bib_lines.append(r'%TC:ignore')
        # Supplemental material title page (title/authors/affiliations),
        # mirroring beamer_to_agu.py's _build_si_header -- otherwise the SI
        # starts right after the bibliography with no indication of what's
        # going on.
        bib_lines.append(_build_si_titlepage(title_text, authors,
                                             affiliation_block, email))
        events.insert(supp_idx, (0, 'passthrough', '\n'.join(bib_lines)))
        events = [e for e in events
                  if not (e[1] == 'section' and is_si_section(e[2]))]
        postamble = '%TC:endignore\n' + r'\end{document}' + '\n'
        # Everything from the SI_BEGIN marker onward already sits inside the
        # outer %TC:ignore/%TC:endignore region opened above. texcount's
        # ignore markers are an on/off toggle, not a nesting counter, so
        # wrapping individual SI captions in their own %TC:ignore pair (as
        # _AMS_FIGURE_OPTS does for main-body figures) would flip the
        # toggle back off mid-SI and desync it from the actual
        # \begin{figure}/\end{figure} pairs. Split events at the marker and
        # assemble the SI portion without per-caption ignore wrapping.
        si_marker_idx = next(
            i for i, e in enumerate(events)
            if e[1] == 'passthrough' and 'SI_BEGIN' in e[2]
        )
        main_events = events[:si_marker_idx + 1]
        si_events = events[si_marker_idx + 1:]
    else:
        postamble = endmatter + '\n\n' + _build_postamble(bib_style, bib_file)
        main_events = events
        si_events = []

    if not events:
        print("Warning: no frames or sections found; writing body as-is.",
              file=sys.stderr)
        manuscript_body = transform_content(body, figure_opts=_AMS_FIGURE_OPTS)
    else:
        manuscript_body = assemble_body(main_events, figure_opts=_AMS_FIGURE_OPTS)
        if si_events:
            si_body = assemble_body(si_events, figure_opts={'caption_tcignore': False})
            if si_body.strip():
                manuscript_body += '\n\n' + si_body

    pkg_ams = extract_passthrough_packages(src) or r'\usepackage{amsmath,amssymb}'
    preamble = _build_preamble(title_text, authors_block, affiliation_block, abstract_text,
                               statement_block, pkg_ams=pkg_ams)
    out = preamble + '\n' + manuscript_body + '\n' + postamble
    Path(output_path).write_text(out, encoding='utf-8')
    print(f"Written: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='Beamer .tex file')
    parser.add_argument('output', nargs='?', help='Output .tex file (default: <input>_manuscript.tex)')
    args = parser.parse_args()

    output_file = args.output or str(Path(args.input).stem) + '_manuscript.tex'
    convert(args.input, output_file)
