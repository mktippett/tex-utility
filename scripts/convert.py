#!/usr/bin/env python3
"""
convert.py — unified Beamer-to-manuscript converter.

Usage:
    python convert.py --format ams  slides.tex [output.tex]
    python convert.py --format agu  slides.tex [output.tex] [--journal NAME]

Formats:
    ams   AMS journal manuscript  (documentclass{ametsocV6.1})
    agu   AGU journal manuscript  (documentclass{agujournal2019})

Default output filenames:
    ams   <input_stem>_manuscript.tex
    agu   <input_stem>_agu.tex
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--format', required=True, choices=['ams', 'agu'],
                        help='Target journal format')
    parser.add_argument('input', help='Beamer .tex source file')
    parser.add_argument('output', nargs='?', help='Output .tex file (default: see above)')
    parser.add_argument('--journal', metavar='NAME',
                        help='Journal name for AGU \\journalname{} (AGU only; '
                             'overrides %%\\journalname{} directive in source)')
    args = parser.parse_args()

    stem = Path(args.input).stem

    if args.format == 'ams':
        from beamer_to_ams import convert
        output = args.output or f'{stem}_manuscript.tex'
        convert(args.input, output)
    else:
        from beamer_to_agu import convert
        output = args.output or f'{stem}_agu.tex'
        convert(args.input, output, journal=args.journal)


if __name__ == '__main__':
    main()
