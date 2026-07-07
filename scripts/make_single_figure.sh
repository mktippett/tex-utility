#!/bin/bash
# Extract each \begin{figure}...\end{figure} in a manuscript into its own
# cropped figN.pdf.
#
# Usage: make_single_figure.sh manuscript[.tex] [NFIGS]
#
# NFIGS is the number of live (non-commented) figure environments;
# extract_main.py passes its own count. The fallback grep counts only lines
# where \begin{figure} is not preceded by '%', matching the awk filter below.
set -x

if [[ -z "$1" ]]; then
    echo "Usage: $0 manuscript[.tex] [NFIGS]" >&2
    exit 1
fi

FileName="${1%.tex}"
FIGURES="${FileName}_figures"
if [[ -n "$2" ]]; then
    NFIGS="$2"
else
    NFIGS=$(grep -c '^[^%]*\\begin{figure}' "${FileName}.tex")
fi

# Plain article + geometry (1in margins on letter ≈ journal-class \textwidth)
# so no journal .cls needs to be installed. \caption is a no-op (optional
# [short] arg included); the \clearpage the awk filter appends after each
# \end{figure} forces one figure per page so page N == figure N.
cat <<'EOF' > $FIGURES.tex
\documentclass[12pt]{article}
\usepackage[letterpaper,margin=1in]{geometry}
\usepackage{graphicx}
\renewcommand{\caption}[2][]{}
\setlength{\overfullrule}{0pt}
\begin{document}
\pagestyle{empty}
EOF
awk '/^[^%]*\\begin{figure}/,/^[^%]*\\end{figure}/ {
    print
    if ($0 ~ /^[^%]*\\end{figure}/) print "\\clearpage"
}' $FileName.tex >> $FIGURES.tex
echo "\end{document}" >> $FIGURES.tex

pdflatex -interaction=nonstopmode -halt-on-error $FIGURES || exit 1

for ii in $(seq -w 1 $NFIGS) ; do
cat <<EOF > ${FIGURES}_$ii.tex
\documentclass{article}
\usepackage{pdfpages}
\begin{document}
\includepdf[pages=$ii]{${FIGURES}.pdf}
\end{document}
EOF
pdflatex -interaction=nonstopmode -halt-on-error ${FIGURES}_$ii || exit 1
pdfcrop --margins 1 ${FIGURES}_$ii.pdf fig$ii.pdf || exit 1
rm ${FIGURES}_$ii.*
done
