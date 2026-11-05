# PDF layout XML: state

- **Branch:** `sdlc/pdf-layout-xml` (base: `main`; both unborn until the first commit)
- **Iteration:** 1 of max 5
- **Lanes:** none yet (2 Design, at the gate)
- **Gates:** requirements ✅ approved 2026-11-05 · design ⏳ · release ⏳
- **Mode:** interactive · verify: auto

## Checks
No project yet, so backlog #1 creates them. Planned, all through `uv run`:
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
| Dependencies | `uv run pip-audit` (dev dependency, added by backlog #1) | taken once #1 lands |
| Secrets | `gitleaks git --no-banner .` (installed with Homebrew, approved by the user) | clean: no commits yet |
| Static analysis | ruff's `S` rules, enabled by backlog #1 | no code yet |

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
| PAT-1 | must | none yet | `mypy`, XSD | confirmed |
| PAT-2 | must | none yet | import-scanning test | confirmed |
| PAT-3 | must | none yet | review only | confirmed |
| PAT-4 | must | none yet | AC-22 test | confirmed |

## Acceptance criteria and invariants
AC-1 to AC-25 and INV-1 to INV-3 are all ⬜ open. See `requirements.md`.

## Log
- 2026-11-05 Parser decision changed from pdf.js to pdfplumber, with Python, at the user's condition. Evidence in `parser-evaluation.md`.
- 2026-11-05 Setup done. No commits yet; the first commit is made after the gates so worktrees can exist.
