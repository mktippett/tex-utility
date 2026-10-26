#!/usr/bin/env python3
"""
Find missing DOIs for @article entries via the Crossref API, then add the
reviewed ones to the .bib.

Usage
-----
python bib_add_doi.py find  all.bib --outdir doi/ --mailto you@example.com
python bib_add_doi.py apply all.bib doi/doi_accept.tsv

Notes
-----
``find`` never modifies the .bib. For each @article without a ``doi`` field
it queries Crossref (title + first-author surname) and writes:

    doi_accept.tsv   matches that pass all checks (title similarity >= 0.95,
                     year within +/-1, first-author surname matches)
    doi_review.tsv   best candidate that failed a check, or no candidate

Crossref responses are cached in ``crossref_cache.jsonl`` in the outdir, so an
interrupted run resumes where it stopped and a rerun costs no requests.

``apply`` reads a TSV (edit doi_accept.tsv first: delete rows you reject,
paste rows from doi_review.tsv you accept), writes a dated backup of the .bib,
and inserts ``doi = {...},`` after each entry's opening line. Entries that
already have a doi, unknown keys, and DOIs already used by another entry are
skipped and reported.
"""

from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
import argparse
import csv
import json
import re
import shutil
import sys
import time
import unicodedata

import requests

CROSSREF = 'https://api.crossref.org/works'
TITLE_MIN = 0.95
FIELDS = ['key', 'status', 'reason', 'score', 'doi', 'cr_title', 'cr_journal',
          'cr_year', 'bib_title', 'bib_journal', 'bib_year', 'journal_differs']

# LaTeX accent commands -> combining characters (enough for author surnames)
ACCENTS = {"'": '\u0301', '`': '\u0300', '^': '\u0302', '"': '\u0308',
           '~': '\u0303', 'c': '\u0327', 'v': '\u030c', 'u': '\u0306',
           '=': '\u0304', '.': '\u0307', 'H': '\u030b'}


# --- .bib parsing -----------------------------------------------------------

def split_entries(src):
    """Yield (start, end, type, key, body) for each @entry (not @string/@comment)."""
    for m in re.finditer(r'@(\w+)\s*\{\s*([^,\s]+)\s*,', src):
        etype = m.group(1).lower()
        if etype in ('string', 'comment', 'preamble'):
            continue
        depth, j = 0, src.index('{', m.start())
        while True:
            if src[j] == '{':
                depth += 1
            elif src[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        yield m.start(), j + 1, etype, m.group(2), src[m.start():j + 1]


def field(body, name):
    """Return the raw value of field `name` in an entry body, or None."""
    m = re.search(r'(?im)^\s*' + name + r'\s*=\s*', body)
    if not m:
        return None
    i = m.end()
    c = body[i]
    if c == '{':
        depth, j = 0, i
        while True:
            if body[j] == '{':
                depth += 1
            elif body[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        return body[i + 1:j]
    if c == '"':
        return body[i + 1:body.index('"', i + 1)]
    return re.match(r'[\w:-]+', body[i:]).group(0)


def detex(s):
    """Plain text from a BibTeX value: accents resolved, math/braces/commands dropped."""
    s = re.sub(r'\\([\'`^"~=.])\s*\{?\\?([A-Za-z])\}?',
               lambda m: m.group(2) + ACCENTS[m.group(1)], s)
    s = re.sub(r'\\([cvuH])\s*\{\\?([A-Za-z])\}',
               lambda m: m.group(2) + ACCENTS[m.group(1)], s)
    s = re.sub(r'\$[^$]*\$', ' ', s)
    s = s.replace('\\&', '&').replace('--', '-')
    s = re.sub(r'\\[A-Za-z]+\s*', ' ', s)
    s = s.replace('{', '').replace('}', '').replace('~', ' ')
    return unicodedata.normalize('NFC', ' '.join(s.split()))


def fold(s):
    """Lowercase ASCII alphanumerics only, for comparisons."""
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', s.lower()).split())


def first_surname(author):
    first = re.split(r'\s+and\s+', author.strip(), maxsplit=1)[0]
    first = detex(first)
    if ',' in first:
        return first.split(',')[0].strip()
    return first.split()[-1] if first.split() else ''


# --- Crossref ---------------------------------------------------------------

def load_cache(path):
    cache = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            rec = json.loads(line)
            cache[rec['key']] = rec['items']
    return cache


def query_crossref(session, title, surname, mailto):
    params = {'query.bibliographic': title, 'rows': 5, 'mailto': mailto,
              'select': 'DOI,title,author,issued,published-print,'
                        'published-online,container-title,type'}
    if surname:
        params['query.author'] = surname
    for attempt in range(4):
        r = session.get(CROSSREF, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()['message']['items']
        time.sleep(2 ** attempt * 2)
    r.raise_for_status()


def item_years(item):
    years = set()
    for k in ('issued', 'published-print', 'published-online'):
        parts = (item.get(k) or {}).get('date-parts') or [[None]]
        if parts[0] and parts[0][0]:
            years.add(int(parts[0][0]))
    return years


def judge(entry, items):
    """Return a result row for one bib entry given Crossref items."""
    title, year = entry['title'], entry['year']
    best, best_score = None, 0.0
    for it in items:
        if 'Deleted DOIs' in (it.get('container-title') or []):
            continue
        cr_title = detex(' '.join(it.get('title') or []))
        score = SequenceMatcher(None, fold(title), fold(cr_title)).ratio()
        if score > best_score:
            best, best_score = it, score
    row = {'key': entry['key'], 'bib_title': title, 'bib_year': year,
           'bib_journal': entry['journal'], 'score': f'{best_score:.3f}'}
    if best is None:
        return {**row, 'status': 'review', 'reason': 'no candidate'}
    years = item_years(best)
    cr_journal = detex(' '.join(best.get('container-title') or []))
    row.update(doi=best['DOI'],
               cr_title=detex(' '.join(best.get('title') or [])),
               cr_journal=cr_journal,
               cr_year=','.join(str(y) for y in sorted(years)),
               journal_differs='yes' if cr_journal and entry['journal'] and
               fold(cr_journal) != fold(entry['journal']) else '')
    reasons = []
    if best_score < TITLE_MIN:
        reasons.append('title')
    if not year.isdigit() or not any(abs(y - int(year)) <= 1 for y in years):
        reasons.append('year')
    cr_surnames = {fold(a.get('family', '')) for a in (best.get('author') or [])[:1]}
    if fold(entry['surname']) not in cr_surnames:
        reasons.append('author')
    row['status'] = 'review' if reasons else 'accept'
    row['reason'] = ','.join(reasons)
    return row


def cmd_find(args):
    src = Path(args.bib).read_text(encoding='utf-8')
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cache_path = outdir / 'crossref_cache.jsonl'
    cache = load_cache(cache_path)

    todo = []
    for _, _, etype, key, body in split_entries(src):
        if etype != 'article' or field(body, 'doi') is not None:
            continue
        title = detex(field(body, 'title') or '')
        if not title:
            continue
        todo.append({'key': key, 'title': title,
                     'year': detex(field(body, 'year') or ''),
                     'journal': detex(field(body, 'journal') or ''),
                     'surname': first_surname(field(body, 'author') or '')})
    print(f'bib_add_doi: {len(todo)} @article entries without doi '
          f'({sum(e["key"] in cache for e in todo)} cached)', flush=True)

    session = requests.Session()
    session.headers['User-Agent'] = f'bib_add_doi.py (mailto:{args.mailto})'
    rows = []
    with open(cache_path, 'a', encoding='utf-8') as cache_f:
        for n, entry in enumerate(todo, 1):
            if entry['key'] not in cache:
                items = query_crossref(session, entry['title'], entry['surname'],
                                       args.mailto)
                cache[entry['key']] = items
                cache_f.write(json.dumps({'key': entry['key'], 'items': items}) + '\n')
                cache_f.flush()
                time.sleep(args.delay)
            rows.append(judge(entry, cache[entry['key']]))
            if n % 50 == 0:
                print(f'  {n}/{len(todo)}', flush=True)

    # A DOI proposed for two keys is a duplicate entry or a wrong match
    doi_keys = {}
    for r in rows:
        if r.get('doi'):
            doi_keys.setdefault(r['doi'].lower(), []).append(r['key'])
    for r in rows:
        if r['status'] == 'accept' and len(doi_keys[r['doi'].lower()]) > 1:
            r['status'] = 'review'
            r['reason'] = 'doi shared with ' + ','.join(
                k for k in doi_keys[r['doi'].lower()] if k != r['key'])

    for status in ('accept', 'review'):
        path = outdir / f'doi_{status}.tsv'
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, FIELDS, delimiter='\t', extrasaction='ignore')
            w.writeheader()
            w.writerows(r for r in rows if r['status'] == status)
    n_acc = sum(r['status'] == 'accept' for r in rows)
    n_jd = sum(r['status'] == 'accept' and r.get('journal_differs') == 'yes'
               for r in rows)
    print(f'bib_add_doi: {n_acc} accept, {len(rows) - n_acc} review '
          f'({n_jd} accepted rows have a different Crossref journal name) '
          f'-> {outdir}/doi_accept.tsv, doi_review.tsv')


def cmd_apply(args):
    bib = Path(args.bib)
    src = bib.read_text(encoding='utf-8')
    with open(args.tsv, newline='', encoding='utf-8') as f:
        wanted = {r['key']: r['doi'].strip() for r in csv.DictReader(f, delimiter='\t')
                  if r.get('doi', '').strip()}

    existing = {}
    entries = {}
    for start, end, etype, key, body in split_entries(src):
        entries[key] = (start, body)
        d = field(body, 'doi')
        if d:
            existing[d.strip().lower()] = key

    inserts, skipped = [], []
    for key, doi in wanted.items():
        if key not in entries:
            skipped.append(f'{key}: not in {bib.name}')
        elif field(entries[key][1], 'doi') is not None:
            skipped.append(f'{key}: already has a doi')
        elif doi.lower() in existing:
            skipped.append(f'{key}: {doi} already used by {existing[doi.lower()]}')
        else:
            start, body = entries[key]
            line_end = start + body.index('\n') + 1
            inserts.append((line_end, f'  doi = {{{doi}}},\n'))
            existing[doi.lower()] = key

    for s in skipped:
        print(f'  skip {s}', file=sys.stderr)
    if not inserts:
        print('bib_add_doi: nothing to apply')
        return
    backup = bib.with_name(f'{bib.name}.bak-{date.today():%Y%m%d}-pre-doi')
    n = 1
    while backup.exists():
        backup = bib.with_name(f'{bib.name}.bak-{date.today():%Y%m%d}-pre-doi-{n}')
        n += 1
    shutil.copy2(bib, backup)
    for pos, text in sorted(inserts, reverse=True):
        src = src[:pos] + text + src[pos:]
    bib.write_text(src, encoding='utf-8')
    print(f'bib_add_doi: added {len(inserts)} doi fields to {bib} '
          f'(backup {backup.name}; {len(skipped)} skipped)')


def main():
    parser = argparse.ArgumentParser(description='Add missing DOIs via Crossref.')
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('find', help='query Crossref, write accept/review TSVs')
    p.add_argument('bib')
    p.add_argument('--outdir', default='doi')
    p.add_argument('--mailto', required=True,
                   help='email for the Crossref polite pool')
    p.add_argument('--delay', type=float, default=0.2,
                   help='seconds between uncached requests')
    p = sub.add_parser('apply', help='insert DOIs from a reviewed TSV')
    p.add_argument('bib')
    p.add_argument('tsv')
    args = parser.parse_args()
    cmd_find(args) if args.cmd == 'find' else cmd_apply(args)


if __name__ == '__main__':
    main()
