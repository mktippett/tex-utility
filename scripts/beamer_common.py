#!/usr/bin/env python3
"""
beamer_common.py
----------------
Shared Beamer parsing and transformation utilities used by both
beamer_to_manuscript.py (AMS) and beamer_to_agu.py (AGU).
"""

import re


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

_FONTSIZE_SELECTFONT_RE = re.compile(
    r'\\fontsize\{[^}]*\}\{[^}]*\}\s*\\selectfont\b\s*'
)
_FONT_STYLE_RE = re.compile(
    r'\\(?:tiny|scriptsize|footnotesize|small|normalsize|'
    r'large|Large|LARGE|huge|Huge|'
    r'bfseries|itshape|mdseries|upshape|slshape|'
    r'ttfamily|rmfamily|sffamily|selectfont)\b\s*'
)
_BEAMER_BODY_CMDS_RE = re.compile(r'\\(?:titlepage|maketitle|tableofcontents)\b')
_BEAMER_SETUP_RE = re.compile(
    r'\\(?:title|author|institute|date|logo|titlegraphic|'
    r'usetheme|usecolortheme|usefonttheme|useinnertheme|'
    r'useoutertheme|setbeamertemplate|setbeamercolor|'
    r'setbeamerfont|setbeamersize)(?:\[[^\]]*\])?\{[^}]*\}'
)

# Separates entries in \author{...}. Three styles seen in the wild, all
# accepted: the Beamer '\and' command ("A\inst{1} \and B\inst{2}"), a
# comma-separated English list ("A, B, and C"), and a bare-'and' list with
# no commas ("A and B and C"). Alternatives are ordered so a comma (with or
# without a following "and") is preferred over the bare-'and' fallback.
_AUTHOR_SEP_RE = re.compile(r'\s*\\and\b\s*|\s*,\s*and\s+|\s*,\s*|\s+and\s+')

# Curated allowlist for extract_passthrough_packages: packages that are safe
# and useful in both AMS and AGU manuscript classes.  Excludes packages already
# hardcoded in the converter preamble templates (graphicx, natbib, caption,
# url, hyperref) and beamer-only packages (appendixnumberbeamer, themes).
_PASSTHROUGH_PACKAGES = frozenset({
    # math
    'amsmath', 'amssymb', 'bm', 'mathtools',
    # tables
    'booktabs', 'multirow', 'array', 'tabularx',
    'makecell', 'threeparttable', 'dcolumn', 'longtable',
})


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _extract_brace_group(text, start):
    """
    Extract content of balanced {...} starting at text[start], which must be '{'.
    Returns (content, end_index) where end_index is the position after closing '}'.
    Handles nested braces of any depth.
    """
    if start >= len(text) or text[start] != '{':
        return '', start
    depth = 0
    i = start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], len(text)  # unmatched opening brace


def _strip_font_size_cmds(text):
    """
    Strip LaTeX font size and font selection commands that have no argument:
    tiny, scriptsize, fontsize{}{} selectfont, etc.
    """
    text = _FONTSIZE_SELECTFONT_RE.sub('', text)
    text = _FONT_STYLE_RE.sub('', text)
    return text


def _convert_captionof(text):
    """
    Convert \\captionof{type}{caption text} -> \\caption{caption text}
    using balanced brace matching so nested braces in the caption are handled.
    """
    result = []
    i = 0
    pat = re.compile(r'\\captionof')
    while i < len(text):
        m = pat.search(text, i)
        if not m:
            result.append(text[i:])
            break
        result.append(text[i:m.start()])
        pos = m.end()
        # Skip optional whitespace
        while pos < len(text) and text[pos] in ' \t':
            pos += 1
        # First arg: {type} — extract and discard
        if pos < len(text) and text[pos] == '{':
            _, pos = _extract_brace_group(text, pos)
        # Skip whitespace/newlines between args
        while pos < len(text) and text[pos] in ' \t\n':
            pos += 1
        # Second arg: {caption} — extract and keep
        if pos < len(text) and text[pos] == '{':
            cap_content, pos = _extract_brace_group(text, pos)
            result.append(r'\caption{' + cap_content + '}')
        i = pos
    return ''.join(result)


# ---------------------------------------------------------------------------
# Legacy helpers
# ---------------------------------------------------------------------------

def strip_beamer_command(text, cmd):
    """Remove \\cmd{...} entirely (simple, non-nested)."""
    pattern = r'\\' + re.escape(cmd) + r'\{[^{}]*\}'
    return re.sub(pattern, '', text)


def unwrap_beamer_command(text, cmd):
    """Replace \\cmd{content} with just content (simple, non-nested)."""
    pattern = r'\\' + re.escape(cmd) + r'\{([^{}]*)\}'
    return re.sub(pattern, r'\1', text)


def strip_environment(text, env):
    """Remove \\begin{env}...\\end{env} blocks entirely."""
    pattern = r'\\begin\{' + re.escape(env) + r'\}.*?\\end\{' + re.escape(env) + r'\}'
    return re.sub(pattern, '', text, flags=re.DOTALL)


def unwrap_environment(text, env):
    """Remove \\begin{env} and \\end{env} tags but keep the content."""
    text = re.sub(r'\\begin\{' + re.escape(env) + r'\}', '', text)
    text = re.sub(r'\\end\{' + re.escape(env) + r'\}', '', text)
    return text


# ---------------------------------------------------------------------------
# Frame parser
# ---------------------------------------------------------------------------

def extract_frames(body):
    """
    Return a list of dicts: {title: str, content: str}
    Handles \\begin{frame}{Title}, \\begin{frame}[opts]{Title},
    and \\frametitle{Title} inside \\begin{frame}.
    Uses balanced brace matching for title extraction to handle \\ref{} etc.
    """
    frames = []
    frame_pattern = re.compile(
        r'\\begin\{frame\}(.*?)\\end\{frame\}',
        re.DOTALL
    )
    for m in frame_pattern.finditer(body):
        raw = m.group(1)
        title = ''

        stripped = raw.lstrip()
        pos_in_stripped = 0

        # Option A: title given as argument to \begin{frame}
        #   \begin{frame}[opt]{Title}  or  \begin{frame}{Title}

        # First, skip optional [overlay spec]
        ol_m = re.match(r'\[[^\]]*\]\s*', stripped)
        if ol_m:
            pos_in_stripped = ol_m.end()

        # Try to extract {Title} using balanced braces
        if pos_in_stripped < len(stripped) and stripped[pos_in_stripped] == '{':
            title_content, end = _extract_brace_group(stripped, pos_in_stripped)
            # Accept as title only if it looks like a title (no double blank lines,
            # reasonable length, not the body of the frame)
            if len(title_content) < 300 and '\n\n' not in title_content:
                title = title_content.strip()
                # Remove the [option]{Title} prefix from raw; keep only the body
                leading_ws = len(raw) - len(stripped)
                raw = raw[leading_ws + end:]

        # Option B: \frametitle{...} inside the frame
        # Use balanced braces here too
        ft_pat = re.compile(r'\\frametitle')
        ft_m = ft_pat.search(raw)
        if ft_m:
            fp = ft_m.end()
            while fp < len(raw) and raw[fp] in ' \t':
                fp += 1
            if fp < len(raw) and raw[fp] == '{':
                ft_content, ft_end = _extract_brace_group(raw, fp)
                if not title:
                    title = ft_content.strip()
                raw = raw[:ft_m.start()] + raw[ft_end:]

        # Strip \framesubtitle
        raw = re.sub(r'\\framesubtitle\{[^}]*\}', '', raw)

        frames.append({'title': title, 'content': raw})

    return frames


# ---------------------------------------------------------------------------
# Content transformer: one frame's content -> manuscript paragraph(s)
# ---------------------------------------------------------------------------

_BLOCK_CMD_RE = re.compile(
    r'^\\(?:begin|end|section\*?|clearpage|renewcommand|setcounter|bibliography)'
)


def _join_paragraph_lines(text):
    """Join internal line breaks within text paragraphs; leave block-level commands/environments intact."""
    out = []
    for block in re.split(r'\n{2,}', text):
        block = block.strip()
        if not block:
            continue
        if _BLOCK_CMD_RE.match(block):
            out.append(block)
        else:
            out.append(' '.join(line.strip() for line in block.splitlines() if line.strip()))
    return '\n\n'.join(out)


def transform_content(content, figure_opts=None):
    """
    Transform a single frame's content string into manuscript LaTeX.
    Returns a string of LaTeX paragraphs / figure environments.

    figure_opts: dict passed to _restructure_figures to control figure format.
      Keys: placement (str), centering (bool), noindent (bool), default_width (str|None),
      caption_tcignore (bool)
      Defaults produce AMS-style figures: [h], \\centering, no \\noindent, caption counted.
    """
    # --- 1. Strip font size / selection commands first ----------------------
    content = _strip_font_size_cmds(content)

    # --- 2. Strip overlay/transition commands that produce no text ----------
    for cmd in ['pause', 'newpage', 'medskip', 'bigskip', 'smallskip',
                'vspace', 'hspace', 'vfill', 'hfill', 'centering',
                'noindent', 'raggedright', 'raggedleft',
                'setlength', 'addtolength',
                'bibliographystyle', 'bibliography']:
        content = re.sub(r'\\' + re.escape(cmd) + r'(\{[^}]*\})?(\[[^\]]*\])?', '', content)

    # Strip \only<...>{...}, \visible<...>{...}, etc. -> keep content
    for cmd in ['only', 'visible', 'uncover', 'onslide', 'temporal']:
        content = re.sub(
            r'\\' + re.escape(cmd) + r'(<[^>]*>)?\{([^{}]*)\}',
            r'\2', content
        )

    # \alert{x} -> x,  \textcolor{c}{x} -> x
    content = unwrap_beamer_command(content, 'alert')
    content = re.sub(r'\\textcolor\{[^}]*\}\{([^{}]*)\}', r'\1', content)

    # \structure{x} -> x
    content = unwrap_beamer_command(content, 'structure')

    # \column{width} and \columns environments -> strip tags
    content = re.sub(r'\\begin\{columns\}(\[[^\]]*\])?', '', content)
    content = re.sub(r'\\end\{columns\}', '', content)
    content = re.sub(r'\\column(\[[^\]]*\])?\{[^}]*\}', '', content)

    # --- 3. Strip minipage tags (keep content) ------------------------------
    content = re.sub(r'\\begin\{minipage\}(\[[^\]]*\])?\{[^}]*\}', '', content)
    content = re.sub(r'\\end\{minipage\}', '', content)

    # --- 4. Figures: restructure \includegraphics + \captionof/caption ------
    opts = figure_opts or {}
    content = _restructure_figures(
        content,
        placement=opts.get('placement', 'h'),
        centering=opts.get('centering', True),
        noindent=opts.get('noindent', False),
        default_width=opts.get('default_width', None),
        caption_tcignore=opts.get('caption_tcignore', False),
    )

    # --- 5. enumerate / itemize -> prose paragraphs -------------------------
    content = _flatten_lists(content)

    # --- 6. Block environments -> plain text --------------------------------
    for env in ['block', 'exampleblock', 'alertblock']:
        content = re.sub(
            r'\\begin\{' + re.escape(env) + r'\}\{([^}]*)\}',
            r'\n\\textbf{\1}\n',
            content
        )
        content = re.sub(r'\\end\{' + re.escape(env) + r'\}', '', content)

    # --- 7. center environment -> keep content, remove tags -----------------
    content = unwrap_environment(content, 'center')

    # --- 8. Clean up extra blank lines --------------------------------------
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = content.strip()

    # --- 9. Join lines within text paragraphs ------------------------------
    content = _join_paragraph_lines(content)

    return content


def _restructure_figures(content, placement='h', centering=True,
                          noindent=False, default_width=None,
                          caption_tcignore=False):
    r"""
    Find \includegraphics blocks and wrap each group in a proper figure
    environment.  Skips \includegraphics that are already inside a
    \begin{figure}...\end{figure}.

    Groups consecutive \includegraphics into one figure.
    Attaches a following \caption{} (balanced-brace aware) if present.
    Also captures a \label{} immediately after \caption{}.

    placement: float placement option string (e.g. 'h', 'tbp', '' for none)
    centering: if True, add \centering inside the figure
    noindent: if True, prefix each \includegraphics with \noindent
    default_width: if set (e.g. r'\textwidth'), add width=... when no options present
    caption_tcignore: if True, wrap the emitted \caption{} in flush-left
      %TC:ignore / %TC:endignore markers so texcount excludes it (AMS rules
      exclude captions from the word count; AGU counts them, so this defaults off)
    """
    # Convert any remaining \captionof{type}{...} -> \caption{...}
    content = _convert_captionof(content)

    result = []
    pos = 0
    text = content
    n = len(text)

    inc_re = re.compile(r'\\includegraphics(\[[^\]]*\])?\{([^}]+)\}')

    while pos < n:
        # Look for next \begin{figure} and next bare \includegraphics
        fig_begin = text.find('\\begin{figure}', pos)
        inc_m = inc_re.search(text, pos)

        if inc_m is None:
            # No more \includegraphics — pass remainder through
            result.append(text[pos:])
            break

        # If an existing \begin{figure} comes first, pass it through unchanged
        if fig_begin != -1 and fig_begin < inc_m.start():
            result.append(text[pos:fig_begin])
            fig_end_m = re.search(r'\\end\{figure\}', text, fig_begin)
            if fig_end_m:
                result.append(text[fig_begin:fig_end_m.end()])
                pos = fig_end_m.end()
            else:
                result.append(text[fig_begin:])
                pos = n
            continue

        # Process bare \includegraphics
        result.append(text[pos:inc_m.start()])

        # Collect consecutive \includegraphics (possibly side-by-side)
        graphics = []
        cur = inc_m.start()
        while True:
            im = inc_re.match(text, cur)
            if im:
                g = im.group(0)
                # Add default_width if no options present
                if default_width and not im.group(1):
                    g = r'\includegraphics[width=' + default_width + ']{' + im.group(2) + '}'
                graphics.append(g)
                cur = im.end()
                ws = re.match(r'\s*', text[cur:])
                cur += ws.end() if ws else 0
            else:
                break

        # Look for \caption{...} (with optional [short]) and optional \label{}
        caption_cmd = ''
        label_cmd = ''
        new_cur = cur

        ahead = text[cur:]
        ws_m = re.match(r'\s*', ahead)
        offset = ws_m.end() if ws_m else 0

        # Check for \caption (but not \captionof — already converted above)
        if ahead[offset:offset + 8] == r'\caption' and (
                offset + 8 >= len(ahead) or ahead[offset + 8] in '{[ \t\n'):
            cap_pos = offset + 8
            # Skip optional whitespace and [short caption]
            while cap_pos < len(ahead) and ahead[cap_pos] in ' \t':
                cap_pos += 1
            if cap_pos < len(ahead) and ahead[cap_pos] == '[':
                bracket_end = ahead.find(']', cap_pos)
                cap_pos = bracket_end + 1 if bracket_end != -1 else cap_pos
                while cap_pos < len(ahead) and ahead[cap_pos] in ' \t':
                    cap_pos += 1
            # Extract balanced {caption text}
            if cap_pos < len(ahead) and ahead[cap_pos] == '{':
                cap_content, cap_end_in_ahead = _extract_brace_group(ahead, cap_pos)
                cap_content = _strip_font_size_cmds(cap_content).strip()
                caption_cmd = r'\caption{' + cap_content + '}'
                new_cur = cur + cap_end_in_ahead

                # Look for \label{} immediately after \caption{}
                after_cap = ahead[cap_end_in_ahead:]
                ws_m2 = re.match(r'\s*', after_cap)
                lb_offset = ws_m2.end() if ws_m2 else 0
                if after_cap[lb_offset:lb_offset + 6] == r'\label':
                    lb_pos = lb_offset + 6
                    while lb_pos < len(after_cap) and after_cap[lb_pos] in ' \t':
                        lb_pos += 1
                    if lb_pos < len(after_cap) and after_cap[lb_pos] == '{':
                        lb_content, lb_end = _extract_brace_group(after_cap, lb_pos)
                        label_cmd = r'\label{' + lb_content + '}'
                        new_cur = cur + cap_end_in_ahead + lb_offset + lb_end

        # Build the figure environment
        placement_str = f'[{placement}]' if placement else ''
        fig = f'\n\\begin{{figure}}{placement_str}\n'
        if centering:
            fig += '  \\centering\n'
        for g in graphics:
            prefix = '  \\noindent ' if noindent else '  '
            fig += prefix + g + '\n'
        if caption_cmd:
            if caption_tcignore:
                fig += '%TC:ignore\n'
                fig += '  ' + caption_cmd + '\n'
                fig += '%TC:endignore\n'
            else:
                fig += '  ' + caption_cmd + '\n'
        if label_cmd:
            fig += '  ' + label_cmd + '\n'
        fig += '\\end{figure}\n'

        result.append(fig)
        pos = new_cur if (caption_cmd or label_cmd) else cur

    return ''.join(result)


def _flatten_lists(content):
    """
    Convert enumerate and itemize environments to prose paragraphs.
    Each \\item becomes a sentence (appending '.' if needed).
    """
    result = []
    pos = 0
    list_pat = re.compile(
        r'\\begin\{(enumerate|itemize)\}(.*?)\\end\{(?:enumerate|itemize)\}',
        re.DOTALL
    )
    for m in list_pat.finditer(content):
        result.append(content[pos:m.start()])
        items_text = m.group(2)
        items = re.split(r'\\item\b', items_text)
        sentences = []
        for item in items:
            item = item.strip()
            if not item:
                continue
            if item[-1] not in '.!?:':
                item += '.'
            sentences.append(item)
        if sentences:
            result.append('\n' + ' '.join(sentences) + '\n')
        pos = m.end()
    result.append(content[pos:])
    return ''.join(result)


# ---------------------------------------------------------------------------
# Preamble metadata helpers
# ---------------------------------------------------------------------------

def _extract_preamble(src):
    """Return text before \\begin{document}, or full src if not found."""
    doc_start = src.find(r'\begin{document}')
    return src[:doc_start] if doc_start != -1 else src


def extract_passthrough_packages(src):
    r"""
    Return \\usepackage lines from the Beamer preamble whose packages are all in
    the curated ``_PASSTHROUGH_PACKAGES`` allowlist (math + table packages).

    A line like ``\usepackage[opts]{a,b}`` is passed through unchanged only if
    every package name (a, b) is in the allowlist.  Options are preserved.
    Deduplicates by exact line content. Returns a newline-joined string, or ''
    if none.
    """
    preamble = _extract_preamble(src)
    seen = set()
    lines = []
    for line in preamble.splitlines():
        s = line.strip()
        if not s.startswith(r'\usepackage'):
            continue
        # Extract the braced package list: \usepackage[...]{pkg1,pkg2}
        m = re.search(r'\{([^}]+)\}', s)
        if not m:
            continue
        pkg_names = {p.strip() for p in m.group(1).split(',')}
        if pkg_names and pkg_names <= _PASSTHROUGH_PACKAGES:
            if s not in seen:
                seen.add(s)
                lines.append(s)
    return '\n'.join(lines)


def _extract_bib_file(src):
    """Return the first bib filename from \\bibliography{...} in src, or 'references'."""
    m = re.search(r'\\bibliography\{([^}]+)\}', src)
    return m.group(1) if m else 'references'


def _extract_bib_style(src):
    """Return the \\bibliographystyle argument from src, or None if not present."""
    m = re.search(r'\\bibliographystyle\{([^}]+)\}', src)
    return m.group(1) if m else None


def _parse_inst_blocks(src):
    """Parse \\author{} and \\institute{} from Beamer source.

    Returns (parsed, inst_map, inst_nums):
      parsed:    [(clean_name, inst_num_or_None), ...]
      inst_map:  {inst_num: affiliation_text}
      inst_nums: ordered list of inst numbers referenced by authors
                 (empty when no \\inst markup is present)
    The caller handles the no-\\inst fallback (default text differs by format).
    """
    author_raw = _extract_preamble_arg(src, 'author') or ''
    raw_authors = [a.strip() for a in _AUTHOR_SEP_RE.split(author_raw) if a.strip()]
    parsed = []
    for entry in raw_authors:
        inst_m = re.search(r'\\inst\{(\d+)\}', entry)
        if inst_m:
            parsed.append((entry[:inst_m.start()].strip(), int(inst_m.group(1))))
        else:
            parsed.append((entry.strip(), None))

    institute_raw = _extract_preamble_arg(src, 'institute') or ''
    institute_raw = re.sub(r'(?<!\\)%[^\n]*', '', institute_raw)
    inst_parts = re.split(r'\\and\b', institute_raw)
    inst_map = {}
    for part in inst_parts:
        part = part.strip()
        if not part:
            continue
        inst_m = re.search(r'\\inst\{(\d+)\}', part)
        if inst_m:
            inst_map[int(inst_m.group(1))] = part[inst_m.end():].strip()
        else:
            inst_map.setdefault(1, part)

    inst_nums = []
    seen = set()
    for _, num in parsed:
        if num is not None and num not in seen:
            inst_nums.append(num)
            seen.add(num)

    return parsed, inst_map, inst_nums


def _extract_preamble_arg(src, cmd):
    """
    Extract the main brace argument of \\cmd[opt]{arg} anywhere in src.
    Uses balanced brace matching so nested braces are handled.
    Returns the content string, or None if not found.
    """
    m = re.search(r'\\' + re.escape(cmd) + r'(\[[^\]]*\])?\s*\{', src)
    if not m:
        return None
    content, _ = _extract_brace_group(src, m.end() - 1)
    return content.strip()


def _abbreviate_name(full_name):
    """
    'Michael K. Tippett' -> 'M. K. Tippett'
    Each word before the last becomes its first letter + period.
    Words already ending in '.' are kept as-is.
    """
    parts = full_name.strip().split()
    if len(parts) <= 1:
        return full_name
    initials = [p if p.endswith('.') else p[0] + '.' for p in parts[:-1]]
    return ' '.join(initials) + ' ' + parts[-1]


# ---------------------------------------------------------------------------
# Pipeline helpers shared by both converters
# ---------------------------------------------------------------------------

def preprocess_body(src):
    """
    Extract the body between \\begin{document} and \\end{document},
    strip Beamer theme/display commands, and strip comment lines.
    Returns the cleaned body string.
    """
    doc_match = re.search(
        r'\\begin\{document\}(.*?)\\end\{document\}',
        src, re.DOTALL
    )
    body = doc_match.group(1) if doc_match else src

    body = _BEAMER_BODY_CMDS_RE.sub('', body)
    body = _BEAMER_SETUP_RE.sub('', body)

    # Strip beamer housekeeping outside frames, but NOT counter resets for
    # figure/table (\renewcommand\thefigure/\thetable and \setcounter{figure/table}
    # are passed through to the manuscript for supplemental numbering).
    body = re.sub(r'\\setcounter\{(?!(?:figure|table)\})[^}]*\}\{[^}]*\}', '', body)
    body = re.sub(r'\\renewcommand\\(?!the(?:figure|table)\b)[a-zA-Z]+(\[[^\]]*\])?\{[^}]*\}', '', body)

    # Strip comment lines — negative lookbehind preserves \%
    body = re.sub(r'(?<!\\)%[^\n]*', '', body)

    # Expand \fig{path} -> \includegraphics{path}
    # \fig is the standard Beamer shorthand defined in CLAUDE.md; slide-specific
    # size options are stripped here so _restructure_figures can apply
    # manuscript-appropriate widths.
    body = re.sub(r'\\fig\{([^}]+)\}', r'\\includegraphics{\1}', body)

    return body


def build_event_list(body, keep_bibliographystyle=True):
    """
    Scan preprocessed body and return a sorted list of
    (position, type, content) events.

    Types:
      'section'     — \\section{Title}
      'frame'       — frame content (transformed later)
      'passthrough' — figure-counter resets and bibliography commands

    keep_bibliographystyle: if False, \\bibliographystyle{} commands are
      omitted from passthrough events (AGU class sets this automatically).
    """
    events = []

    for m in re.finditer(r'\\section\*?\{([^}]*)\}(?:\s*\\label\{[^}]*\})?', body):
        events.append((m.start(), 'section', m.group(0).strip()))

    frame_pat = re.compile(r'\\begin\{frame\}.*?\\end\{frame\}', re.DOTALL)
    frame_ranges = []
    for m in frame_pat.finditer(body):
        frame_ranges.append((m.start(), m.end()))
        raw_frames = extract_frames(m.group(0))
        if raw_frames:
            events.append((m.start(), 'frame', raw_frames[0]['content']))

    # Pass through verbatim: figure-counter resets and bibliography commands.
    # Only capture occurrences that are OUTSIDE frame environments.

    bib_style_pat = r'\\bibliographystyle\{[^}]*\}|' if keep_bibliographystyle else ''
    passthrough_pat = re.compile(
        r'\\renewcommand\\the(?:figure|table)\{(?:[^{}]|\{[^}]*\})*\}'
        r'|\\setcounter\{(?:figure|table)\}\{[^}]*\}'
        r'|\\clearpage\b'
        r'|' + bib_style_pat +
        r'\\bibliography\{[^}]*\}'
    )
    for m in passthrough_pat.finditer(body):
        if not any(start <= m.start() < end for start, end in frame_ranges):
            events.append((m.start(), 'passthrough', m.group(0)))

    events.sort(key=lambda x: x[0])
    return events


def extract_abstract(events):
    """
    Find \\section{Abstract} in events, consume the section header and all
    immediately following frame events, transform their content, and return
    (abstract_text, remaining_events).
    """
    abstract_text = 'Abstract text here.'
    i = 0
    while i < len(events):
        _pos, etype, content = events[i]
        sec_title_m = re.match(r'\\section\*?\{([^}]*)\}', content)
        sec_title = sec_title_m.group(1).strip().lower() if sec_title_m else ''
        if etype == 'section' and sec_title == 'abstract':
            abstract_parts = []
            j = i + 1
            while j < len(events) and events[j][1] == 'frame':
                transformed = transform_content(events[j][2])
                if transformed.strip():
                    abstract_parts.append(transformed.strip())
                j += 1
            if abstract_parts:
                abstract_text = '\n  '.join(abstract_parts)
            remaining = events[:i] + events[j:]
            return abstract_text, remaining
        i += 1
    return abstract_text, events


def assemble_body(events, figure_opts=None):
    """
    Iterate events, transform frames, and join into a manuscript body string.
    figure_opts is passed through to transform_content.
    """
    if not events:
        return ''
    parts = []
    for _pos, etype, content in events:
        if etype == 'section':
            parts.append(content)  # full \section{...} possibly with \label
        elif etype == 'passthrough':
            parts.append(content)
        else:
            transformed = transform_content(content, figure_opts=figure_opts)
            if transformed.strip():
                parts.append(transformed)
    return '\n\n'.join(parts)
