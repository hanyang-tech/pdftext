# PDF layout XML: state

- **Branch:** `sdlc/pdf-layout-xml` (base: `main`; both unborn until the first commit)
- **Iteration:** 2 of max 5
- **Lanes:** iteration 2: 2a (#6) at 4 Build · 2b (#3) at 4 Build · 2c (#5) at 4 Build
- **Gates:** requirements ✅ approved 2026-11-05 · design ✅ approved 2026-11-05 · release ⏳
- **Mode:** interactive · verify: auto

## Checks
All through `uv run`, all passing on `eb494f3`. The full suite takes about 3 s.
- test (full suite): `uv run pytest`
- test (targeted): `uv run pytest <paths>`
- lint: `uv run ruff check .`
- format: `uv run ruff format --check .`
- typecheck: `uv run mypy src`
- build: `uv build`
- coverage: `uv run pytest --cov --cov-branch`

## Lanes setup
- **Parallel-safe:** yes: tests are file-based, with no ports or shared services
- **Max lanes:** 3
- **Worktree root:** `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/`
- **Worktree setup:** `uv sync`

## Scanners
| Category | Command | Baseline (before this work) |
|---|---|---|
| Dependencies | `uv run pip-audit` (dev dependency, added by backlog #1) | clean at `f6a1bde` |
| Secrets | `gitleaks git --no-banner .` (installed with Homebrew, approved by the user) | clean at `f6a1bde`, 5 commits |
| Static analysis | ruff's `S` rules, enabled by backlog #1 | clean at `f6a1bde` |

## Roles
| Role | Agent type | Model |
|---|---|---|
| Driver | this session | opus |
| Architect | general-purpose | opus |
| Engineer | software-engineer | sonnet |
| Reviewer | code-reviewer | opus |
| Tester | general-purpose | sonnet |
| Verifier | general-purpose | sonnet |
| Final reviewer | code-reviewer | opus |
| Security reviewer | general-purpose | opus |
| Skeptic | general-purpose | opus |

## Standards
- **Patterns file:** `docs/patterns.md`
- **Languages:**

| Language | Reference (absolute path) | Formatter | Linter |
|---|---|---|---|
| Python 3.13 | `/Users/wiragamahantareja/.claude/skills/sdlc-fast/references/languages/python.md` | `ruff format` | `ruff check` |

| Pattern | Strength | Exemplar | Check | Status |
|---|---|---|---|---|
| PAT-1 | must | `src/pdftext/model.py` (user-confirmed it. 1) | `mypy`, XSD | confirmed |
| PAT-2 | must | `src/pdftext/adapter.py` (user-confirmed it. 1) | import-scanning test | confirmed |
| PAT-3 | must | `src/pdftext/text.py` (user-confirmed it. 1) | review only | confirmed |
| PAT-4 | must | `src/pdftext/xmlwriter.py` (user-confirmed it. 1) | AC-22 test | confirmed |

## Acceptance criteria and invariants
Verified by the full-suite run on `f6a1bde` (same tree as `eb494f3`), 379 tests:

| ID | Status | Verified by |
|---|---|---|
| AC-1 | ✅ | `tests/test_api.py::TestConvert::test_writes_a_file_per_page_and_a_document_listing_them_all` |
| AC-2 | ✅ | `tests/test_api.py::TestIterPages::test_reads_only_the_first_page_when_only_the_first_is_taken` |
| AC-3 | ✅ | `tests/test_api.py::TestConvert::test_writes_schema_valid_files_that_keep_every_character`, `tests/test_schema.py` |
| AC-4 | ✅ | `tests/test_api.py::TestConvert::test_gives_every_element_a_bbox_and_places_nest_where_the_pdf_draws_it` |
| AC-22 | ✅ | `tests/test_api.py::TestConvert::test_gives_identical_bytes_whatever_the_hash_seed` |
| AC-24 | ✅ | `tests/test_api.py::TestConvert::test_replaces_characters_xml_forbids_and_counts_them` |
| SEC-9 | ✅ | `tests/test_api.py::TestFailedRuns::test_a_planted_symlink_is_replaced_and_its_target_left_alone` |
| SEC-10 | ✅ | `tests/test_cli.py::test_a_refused_run_leaves_neither_an_old_document_nor_old_pages` |
| SEC-11 | ✅ | `tests/test_api.py::TestConvert::test_output_holds_neither_the_input_nor_the_output_path` |
| INV-1 | ✅ | `tests/test_api.py::TestConvert::test_writes_schema_valid_files_that_keep_every_character` |

AC-5 to AC-21, AC-23, AC-25, SEC-1 to SEC-8, SEC-12 to SEC-17, INV-2 and INV-3 are ⬜ open. See `requirements.md`.

## Log
- 2026-11-05 Parser decision changed from pdf.js to pdfplumber, with Python, at the user's condition. Evidence in `parser-evaluation.md`.
- 2026-11-05 Setup done. No commits yet; the first commit is made after the gates so worktrees can exist.
- 2026-11-05 Design approved. User chose to ship without RTL reordering (backlog #8). First commit `8e6166f`. `main` is still unborn and the remote is empty, which matters for the PR at Release.
- 2026-11-05 Iteration 1 closed. The user approved the architect's page-tree walker delta, chose no flag for a short `/Count`, kept the whitespace rule, and confirmed the four exemplars. SEC-16 and SEC-17 added. The architect's first delta round ran `rm -rf big o_*` in the shared scratchpad; later rounds kept to their own subfolder.
