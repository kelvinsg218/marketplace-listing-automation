# Development

## Workflow (with Claude Code)
- Session start: `CLAUDE.md` loads automatically → read `docs/CURRENT_STATUS.md` + `docs/NEXT_STEPS.md`.
- Active skills (descriptions always loaded): frontend-design, pyside6-design, webapp-testing, systematic-debugging,
  test-driven-development, verification-before-completion, python-testing, strategic-compact (+ user-level
  token-economy). Activate dormant ones per phase: `python tools/skills_catalog.py activate windows-desktop-e2e`.
- Feature work: test first where practical (unit/automation), implement, run the narrow test file, then the suite.
- UI work: follow `pyside6-design`; review with `tools/ui_snapshots.py`.
- Bugs: `systematic-debugging` (root cause before fixes) + regression test.
- End of phase: update CURRENT_STATUS.md, NEXT_STEPS.md, DECISIONS.md, CHANGELOG.md; then compact.

## Local model (optional, see DECISIONS D-003)
`python tools/ollama_assist.py triage error.txt` gives a quick hint on a traceback. Do not use it for code,
summaries or docs on this hardware. `python tools/ollama_assist.py stats` shows measured usage.

## Adding a marketplace adapter
1. Subclass `BaseMarketplaceAdapter` (`src/mla/automation/base.py`), implement every step with explicit waits on
   ids/labels/roles, raise `ManualActionRequired` for login/CAPTCHA, `AmbiguousStateError` when publication can't be
   proven, `StepError(retryable=False)` for data problems.
2. Register it in `automation/adapters/__init__.py`, add rules to `core/validation.MARKETPLACE_RULES` (mark
   `confirmed`), add a local HTML fixture reproducing the real structure and browser tests.

## Adding a migration
New file `src/mla/persistence/migrations/NNNN_name.sql` (next number, lowercase name). It runs in one transaction;
existing databases get a backup first. Never edit an applied migration.

## Conventions
Code/comments in English, UI text in PT-BR. Units: cents, grams, millimetres. No inline colours in widgets.
