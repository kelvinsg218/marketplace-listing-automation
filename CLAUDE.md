# MLA — Marketplace Listing Automation

Two products in one repo. UI text is Brazilian Portuguese; code and comments in English.
- **Desktop (legacy, still shipped):** Windows app in `src/mla` (Python 3.13, PySide6, Playwright, SQLite).
- **MLA Web 2.0 (in development):** `apps/api` (FastAPI, SQLAlchemy 2, Alembic, PostgreSQL) + `apps/web` (Next.js 15
  static export, Tailwind 4). Docs: `docs/MLA_WEB_*.md`, `docs/MLA_MERCADOLIVRE_RESEARCH.md`, `docs/MLA_LEGACY_MIGRATION.md`.

## Resume a session (token economy)
1. Read `docs/CURRENT_STATUS.md`, then `docs/NEXT_STEPS.md`. Open `docs/ARCHITECTURE.md` / `docs/DECISIONS.md`
   only when the task touches them. Don't re-run analyses already recorded in DECISIONS.md.
2. Locate with Grep, read ranges, edit locally, run the narrowest test file.
3. Logs: `python tools/logscan.py <log>` instead of reading logs. Local LLM policy: DECISIONS.md D-003.
4. Skills: few are active; `python tools/skills_catalog.py list|activate|deactivate <name>`.

## Commands
- Run app: `.venv\Scripts\python -m mla` (PYTHONPATH=src, or `pip install -e .`)
- Tests: `.venv\Scripts\python -m pytest` | fast: `-m "not browser"` | E2E only: `-m browser`
- Lint: `.venv\Scripts\python -m pyflakes src tools tests`
- UI screenshots for review: `.venv\Scripts\python tools/ui_snapshots.py <out_dir>`
- Build + package: `.venv\Scripts\python tools/build_release.py` (PyInstaller, exe self-test in a temp data dir,
  `dist\MLA-<ver>-windows.zip` with `installer\` scripts)
- Data dir: `%LOCALAPPDATA%\MLA` (override with `MLA_DATA_DIR`)
- Web API (own venv `apps/api/.venv`): tests `cd apps/api; .venv\Scripts\python -m pytest` (RLS: `-m postgres` with
  `MLA_TEST_DATABASE_URL`); run `alembic upgrade head` then `uvicorn mla_api.asgi:app --reload` with PYTHONPATH=src
- Web frontend: `cd apps/web; npm run dev | typecheck | build`; E2E `.venv\Scripts\python apps/web/e2e/smoke_flow.py <dir> <url>`

## Hard rules
- Never publish a real listing without explicit user authorization; publication always passes human review.
- Never bypass CAPTCHA/login/blocks: adapters raise `ManualActionRequired`. Never read the user's own browser profile.
- Don't guess marketplace selectors or required category attributes; inspect the real form first (phase 4/6).
- Ask before `git commit`/`push`; no Co-Authored-By trailer. Ask before deleting user data or big architecture changes.
- UI colours/radii/type only from tokens: desktop `src/mla/ui/theme.py` (skill `pyside6-design`), web
  `apps/web/src/app/globals.css` `@theme` (docs/MLA_WEB_UX_DESIGN.md).
- Web: every organization-owned table has `organization_id`, is listed in `TENANT_TABLES` and gets an RLS policy in
  its migration; org routes go through `require(...)`. No ML spreadsheet exporter until real official templates are
  analysed (D-025); fill copies of the official file, never synthesize one.
- Report honestly: implemented / tested / pending / blocked. No invented metrics.
