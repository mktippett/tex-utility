#!/bin/bash
set -x

if [[ -z "$1" ]]; then
    echo "Usage: $0 manuscript[.tex]" >&2
    exit 1
fi

FileName="${1%.tex}"
FIGURES="${FileName}_figures"
NFIGS=$(grep -c '\\begin{figure' "${FileName}.tex")

cat <<EOF > $FIGURES.tex
\documentclass[nofiglist]{ametsoc}
\renewcommand{\caption}[1]{}
\setlength{\overfullrule}{0pt}
%
\makeatletter
\@fpsep\textheight
\makeatother
%
\begin{document}
\pagestyle{empty}
EOF
awk '/\\begin{figure}/,/\\end{figure}/' $FileName.tex >> $FIGURES.tex
echo "\end{document}" >> $FIGURES.tex

pdflatex $FIGURES

for ii in $(seq -w 1 $NFIGS) ; do
cat <<EOF > ${FIGURES}_$ii.tex
\documentclass{article}
\usepackage{pdfpages}
\begin{document}
\includepdf[pages=$ii]{${FIGURES}.pdf}
\end{document}
EOF
pdflatex ${FIGURES}_$ii
pdfcrop --margins 1 ${FIGURES}_$ii.pdf fig$ii.pdf
rm ${FIGURES}_$ii.*
done
