#!/usr/bin/env python3
"""
Split a PDF into two PDFs at a specified page.

Usage
-----
python split_pdf.py input.pdf SPLIT_PAGE

python split_pdf.py input.pdf SPLIT_PAGE main.pdf SI.pdf

Notes
-----
SPLIT_PAGE is 1-based and gives the first page of the second output file.

Example
-------
python split_pdf.py paper.pdf 18

This creates:
    paper-main.pdf   pages 1--17
    paper-SI.pdf     pages 18--end
"""

from pathlib import Path
import argparse
import sys

from pypdf import PdfReader, PdfWriter


def default_output_names(input_pdf):
    path = Path(input_pdf)
    if path.suffix.lower() != ".pdf":
        raise ValueError("Input file should have a .pdf extension.")

    main_pdf = path.with_name(f"{path.stem}-main.pdf")
    si_pdf = path.with_name(f"{path.stem}-SI.pdf")
    return main_pdf, si_pdf


def split_pdf(input_pdf, split_page, output_main=None, output_si=None):
    input_pdf = Path(input_pdf)

    if not input_pdf.exists():
        raise FileNotFoundError(f"Input file not found: {input_pdf}")

    reader = PdfReader(str(input_pdf))
    n_pages = len(reader.pages)

    if split_page < 2 or split_page > n_pages:
        raise ValueError(
            f"split_page must be between 2 and {n_pages}. "
            f"It is the first page of the second PDF."
        )

    if output_main is None or output_si is None:
        default_main, default_si = default_output_names(input_pdf)
        output_main = default_main if output_main is None else Path(output_main)
        output_si = default_si if output_si is None else Path(output_si)
    else:
        output_main = Path(output_main)
        output_si = Path(output_si)

    main_writer = PdfWriter()
    si_writer = PdfWriter()

    # Convert from 1-based page number to 0-based index
    split_index = split_page - 1

    for page in reader.pages[:split_index]:
        main_writer.add_page(page)

    for page in reader.pages[split_index:]:
        si_writer.add_page(page)

    with open(output_main, "wb") as f:
        main_writer.write(f)

    with open(output_si, "wb") as f:
        si_writer.write(f)

    print(f"Wrote {output_main} with pages 1--{split_page - 1}")
    print(f"Wrote {output_si} with pages {split_page}--{n_pages}")


def main():
    parser = argparse.ArgumentParser(
        description="Split a PDF into main text and SI PDFs."
    )
    parser.add_argument("input_pdf", help="Input PDF filename")
    parser.add_argument(
        "split_page",
        type=int,
        help="First page of the second output PDF, using 1-based page numbering",
    )
    parser.add_argument(
        "output_main",
        nargs="?",
        help="Output filename for the first PDF",
    )
    parser.add_argument(
        "output_si",
        nargs="?",
        help="Output filename for the second PDF",
    )

    args = parser.parse_args()

    if (args.output_main is None) != (args.output_si is None):
        parser.error("Specify both output filenames or neither.")

    try:
        split_pdf(
            args.input_pdf,
            args.split_page,
            args.output_main,
            args.output_si,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
