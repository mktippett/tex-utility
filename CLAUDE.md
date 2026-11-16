# CLAUDE.md — tex-utility

Beamer outline deck → AMS / AGU manuscript converters, submission packaging
(`extract_main.py`, `split_pdf.py`, `make_single_figure.sh`), and bibliography
tools for `~/tex/bib`. User-facing docs: `README.md`. Behavior and history:
`specs/<script>_spec.md`.

## Layout

| Path | Role |
|---|---|
| `scripts/beamer_common.py` | Shared parsing/transform code — **changes affect both converters** |
| `scripts/beamer_to_ams.py`, `beamer_to_agu.py` | Journal-specific front matter, endmatter, word-count markers |
| `scripts/convert.py` | Entry point dispatching to the two converters |
| `scripts/extract_main.py` | Main/SI split + submission folder; never modifies its input |
| `scripts/bib_for_ams.py`, `bib_add_doi.py` | `~/tex/bib` tools (driven by its Makefile) |
| `ams/`, `agu/` | Journal class files (AMS template V6.1) |
| `tests/run_tests.py` | All tests; fixture deck `tests/test_input.tex` |
| `examples/` | Sample decks and committed outputs (outputs may be stale — see AMS spec open items) |

## Working rules

- **Run the tests after every change:**
  `/Users/tippett/miniforge3/envs/pangeo-2025/bin/python tests/run_tests.py`
  — it must end with `All tests passed.` Any change to `beamer_common.py` is
  checked against both the AGU and AMS outputs.
- **Every bug fix gets a regression test, confirmed to fail on the pre-fix
  code** (e.g. `git stash push scripts/<file>.py`, run, `git stash pop`).
  Add fixture content to `tests/test_input.tex` when needed, and update any
  float/section counts it shifts (e.g. the AGU "Figures S1 to SN" check).
- **Verify on a real deck, output to the scratchpad.** Papers live under
  `~/tex/papers/`; never write converter output into those directories
  unless the user asks. Compile-check with the journal class copied next to
  the output.
- **Specs:** every behavior change updates `specs/<script>_spec.md` and adds
  a changelog row. Things found but not fixed go in the spec's open-items
  table, worded as the decision to be made.
- **README:** the user runs this a few times a year, so the README is a
  reminder sheet. Any change to the interface, workflow, or output updates the
  *Quick reference* / *After conversion* sections, not just the reference half.
  Scripts should print a one-line verdict rather than expect a log to be read.
- **Downstream dependent:** `~/claude/templates/research/tex/slides.tex`
  (`/new-project` template, not under git) is pre-tagged with the converters'
  sentinels. Changing a sentinel or deck convention means updating it too.
- Never use `sed` on `.tex` files (global rule); use Edit, or Python with an
  exact-match `assert` before replacing.

## texcount conventions

- `%TC:ignore` / `%TC:endignore` are an on/off **toggle**, not nested, and
  must be flush-left on their own line. Never emit an inner pair inside an
  already-ignored region (SI, front matter) — it switches ignoring off.
- **AMS** (7500-word limit): body, acknowledgments, data statement (open
  item) and appendixes count; title page, abstract, captions, references
  and SI are excluded. The abstract goes to the "words outside text" counter
  via `%TC:macro \abstract [other]`; count with
  `texcount -sum=1,1,0,0,0,1,1` (user alias `tc`): Sum = body, outside
  text = abstract. Plain `-sum` adds the abstract to the Sum.
- **AGU**: captions and abstract count; key points / PLS are excluded.
- `%TC:macro` cannot zero a region under `-sum`; only `%TC:ignore` wrapping
  or `-sum=` weights can.
