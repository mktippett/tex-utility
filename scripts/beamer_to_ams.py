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
        inst_nums = list(range(1, len(parsed) + 1))
        inst_map = {i + 1: 'Department, Institution, City, State'
                    for i in range(len(parsed))}
        parsed = [(name, i + 1) for i, (name, _) in enumerate(parsed)]

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


# ---------------------------------------------------------------------------
# AMS-specific: preamble and postamble
# ---------------------------------------------------------------------------

def _build_preamble(title, authors_block, affiliation_block, abstract_text,
                    pkg_ams=r'\usepackage{amsmath,amssymb}'):
    return rf"""\documentclass{{ametsocV6.1}}

%% AMS packages (ametsoc.sty is already loaded by the class)
\usepackage{{graphicx}}
{pkg_ams}
\usepackage{{natbib}}
\usepackage{{caption}}

% \journal{{jcli}}  % uncomment if using full ametsoc submission package

\begin{{document}}

\title{{{title}}}

{authors_block}

{affiliation_block}

\abstract{{
  {abstract_text}
}}

\maketitle
"""


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

    authors, affiliation_block = _parse_authors_affiliations(src)

    author_parts = []
    for idx, (name, aff) in enumerate(authors):
        part = name + r'\aff{' + aff + '}'
        if idx == 0:
            abbrev = _abbreviate_name(name)
            part += r'\correspondingauthor{' + abbrev + ',\n    email@institution.edu}'
        author_parts.append(part)
    authors_block = r'\authors{' + ' and '.join(author_parts) + '}'

    body = preprocess_body(src)
    events = build_event_list(body, keep_bibliographystyle=False)
    abstract_text, events = extract_abstract(events)

    if not events:
        print("Warning: no frames or sections found; writing body as-is.",
              file=sys.stderr)
        manuscript_body = transform_content(body)
    else:
        manuscript_body = assemble_body(events)

    pkg_ams = extract_passthrough_packages(src) or r'\usepackage{amsmath,amssymb}'
    preamble = _build_preamble(title_text, authors_block, affiliation_block, abstract_text,
                               pkg_ams=pkg_ams)
    postamble = _build_postamble(_extract_bib_style(src), _extract_bib_file(src))
    out = preamble + '\n' + manuscript_body + '\n' + postamble
    Path(output_path).write_text(out, encoding='utf-8')
    print(f"Written: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) >= 3 else str(Path(input_file).stem) + '_manuscript.tex'
    convert(input_file, output_file)
