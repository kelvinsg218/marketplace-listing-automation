# MLA — Marketplace Listing Automation (MLA Web 2.0)

Multi-organization SaaS web app: master catalog → official Mercado Livre bulk-listing sheets (filled copies of the
seller's own template) → adaptive correction rules. UI text is Brazilian Portuguese; code and comments in English.
- `apps/api`: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (SQLite only for local development/tests).
- `apps/web`: Next.js 15 (static export), React 19, Tailwind 4.
- The former Windows desktop app was discontinued on 2026-11-01 (D-030); it lives only in the git history.

## Resume a session (token economy)
1. Read `docs/CURRENT_STATUS.md`, then `docs/NEXT_STEPS.md`. Open `docs/MLA_WEB_ARCHITECTURE.md`,
   `docs/MLA_OFFICIAL_TEMPLATE_ANALYSIS.md` or `docs/DECISIONS.md` only when the task touches them.
2. Locate with Grep, read ranges, edit locally, run the narrowest test file.
3. Logs: `python tools/logscan.py <log>` instead of reading logs. Local LLM policy: DECISIONS.md D-003.
4. Skills: few are active; `python tools/skills_catalog.py list|activate|deactivate <name>`.

## Commands
- API (own venv `apps/api/.venv`, from `apps/api`): tests `.venv\Scripts\python -m pytest` (RLS: `-m postgres` with
  `MLA_TEST_DATABASE_URL`); migrate `.venv\Scripts\python -m alembic upgrade head`; run
  `$env:PYTHONPATH="src"; .venv\Scripts\python -m uvicorn mla_api.asgi:app --reload --reload-dir src`
- Lint: `.venv\Scripts\python -m pyflakes src tests tools migrations` (from `apps/api`)
- Web (from `apps/web`): `npm run dev` (proxies `/api` to :8000) | `npm run typecheck` | `npm run build`
  (stop `dev` before `build`: a build plus the dev auto-restart corrupted `.next` twice, even with `NEXT_DIST_DIR`)
- E2E (Playwright + Edge, any venv with `apps/web/e2e/requirements.txt`): `smoke_flow.py`, `bulk_flow.py`,
  `official_flow.py`, `browser_compare.py` in `apps/web/e2e/`
- Real seller files stay in `docs/ml-research/` (git-ignored); sanitize copies with `apps/api/tools/sanitize_template.py`.

## Hard rules
- Never publish a real listing without explicit user authorization; generating a sheet never means "published".
- Never bypass CAPTCHA/login/blocks; never ask for marketplace passwords, cookies or copied tokens (OAuth only).
- Don't guess marketplace rules: cite the official PDFs (P1–P3) or the real template; hypotheses never block.
- Official sheets: fill a COPY of the seller's file by XML patch (D-027); never synthesize one, never save with openpyxl.
- Every organization-owned table has `organization_id`, is in `TENANT_TABLES` and gets an RLS policy in its migration;
  org routes go through `require(...)`.
- Adaptive rules are data with a closed schema (D-028): no eval, no generated code, no free SQL; explicit approval.
- Never commit seller templates, identifiers, databases, `.env`, tokens or logs with personal data.
- Ask before `git commit`/`push`; no Co-Authored-By trailer. Ask before deleting user data or big architecture changes.
- UI colours/radii/type only from `apps/web/src/app/globals.css` `@theme` tokens (docs/MLA_WEB_UX_DESIGN.md).
- Report honestly: implemented / tested / pending / blocked. No invented metrics.
