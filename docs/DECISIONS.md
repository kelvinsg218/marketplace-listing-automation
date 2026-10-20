# Decisions (newest last)

**D-001 (2026-10-12) Skills: vendor selected files, no whole plugins.** Copied individual skills (pinned commits in
TOOLS_INVENTORY.md) into `.claude/skills/`; others dormant in `tools/skills-catalog/`. Rejected: installing the
Superpowers plugin (its SessionStart hook injects ~700 tokens every session and mandates skill checks on every
message) and ECC wholesale (311 skills, 71 agents, hooks).

**D-002 (2026-10-12) Frontend skill repos not installed.** frontend-ai-skills and frontend-skills: 1 star each,
React/Vue-specific; the three UI skills read were identical generic templates. Useful principles went into the
project skill `pyside6-design`. shadcn/ui used only as a reference (no dependency).

**D-003 (2026-10-12) Local LLM: qwen2.5-coder:1.5b, hints only.** Hardware allows ~1 GB models (system already
paging). Measured with tools/ollama_assist.py: code generation 0/3 correct (executed against asserts); log summary
missed both real errors (78.7 s); code explanation in English with a false claim; error triage right cause, wrong
type (17.8 s). Policy: never delegate code, docs or summaries; triage hints only, always verified. Deterministic
`tools/logscan.py` replaces log summarization (found 4/4 issues in 0.8 s). Re-evaluate with ≥16 GB RAM
(qwen2.5-coder:7b or newer). Rejected: Aider (requires Python <3.13; weak with small models), OpenCode
(anomalyco/opencode; useless with 1.5B models), `ollama launch claude` (replaces Claude instead of assisting).

**D-004 (2026-10-12) MCP: only Chrome DevTools MCP**, project scope, pinned 1.10.1, `--isolated` (temporary
profile), telemetry off, performance/memory/emulation tools off. Reference MCP servers (filesystem, git, fetch,
memory, time) duplicate built-in tools.

**D-005 (2026-10-12) Browser = system Microsoft Edge via Playwright `channel="msedge"`.** Ships with Windows 10/11,
so the installer does not bundle ~170 MB of Chromium. Settings allow Chrome or Playwright Chromium.

**D-006 (2026-10-12) Persistence:** SQLite WAL, one connection per thread, explicit `BEGIN IMMEDIATE`, numbered SQL
migrations with automatic backup before migrating an existing DB. Integer units (cents, g, mm).

**D-007 (2026-10-12) Images are content-addressed copies** inside the data folder (sha256 name), dimensions read
from file headers (no Pillow). Exports copy images next to the CSV/JSON with relative paths (portable).

**D-008 (2026-10-12) Status model:** catalog readiness (draft/incomplete/ready) is derived from validation;
per-marketplace-and-account state lives in `listings`; per-attempt state in `automation_job_items`.

**D-009 (2026-10-12) Marketplace rules kept minimal and flagged.** Only ML title ≤ 60 and Shopee title ≤ 120 /
9 images, all `confirmed=False` until checked against the real forms. Category-required attributes are read from
the form at run time, never hard-coded.

**D-010 (2026-10-12) Executor is Qt-free** (threading + callbacks) so it is testable with plain pytest; Qt gets
signals through `ExecutionBridge`. Pause takes effect after the current item. Manual-action loops capped at 5.

**D-011 (2026-10-12) Licensing placeholder.** Offline checksum keys (forgeable by design) only to build the flow;
`enforce=False`. Replace with signed keys (Ed25519) or a license server before selling.

**D-012 (2026-10-12) Distribution:** PyInstaller one-folder build (219 MB), Playwright driver collected via
`collect_data_files("playwright")` (no contrib hook exists). `MLA.exe --self-test` validated DB + resources + Edge.

**D-013 (2026-10-18) Import formats: openpyxl 3.1.5 (XLSX, read-only, macros never loaded) and pypdf 6.1.3
(PDF text, layout mode)**, both pure Python. CSV/JSON/XML use the standard library; XML with DOCTYPE/ENTITY is
refused. No OCR (scanned PDFs are refused with a clear message). Rejected: pandas (heavy for an 8 GB laptop),
pdfplumber (pulls pdfminer + pypdfium2 + Pillow).

**D-014 (2026-10-18) Import pipeline = analyze → plan → decide → commit.** The plan (per-row action, field changes
old→new, issues, media) is stored in `import_rows`, so previews are paged from SQLite and survive restarts.
Updates only touch fields the file fills and that differ; a field edited after the analysis is kept. Media are
copied before the transaction (content-addressed) and only ever added. Commit = one transaction with a SAVEPOINT
per row (row errors isolated, cancel/crash = nothing written). ZIPs are extracted to `imports/` with an
allow-list (tables, images, documents); executables, scripts, macro documents, nested archives, links and
escaping paths are skipped. Column recognition is a synonym dictionary (no AI); ambiguous names need confirmation.

**D-015 (2026-10-18) Listing = offer of a master product on one account.** Stored in `listings` (rebuilt in
migration 0006 to widen the status CHECK; all rows copied) with overrides only (empty = master value). One status
column holds the lifecycle; preparation states are derived from validating the effective content; approval keeps a
fingerprint and is revoked when the content changes. Only approved listings are queued; the executor validates and
sends the effective content; PUBLISHED still only comes from a confirmed publication. UNIQUE(product, marketplace,
account) kept (two offers of one product in the same account not supported yet).

**D-016 (2026-10-18) Provenance.** Compatibilities carry source (client/manufacturer/external) and verification;
client data starts confirmed, everything else unverified; nothing is inferred. External observations
(`market_observations`) and AI suggestions (`ai_suggestions`) live in their own tables; suggestions only change a
listing override when accepted, never the master product. External AI providers need the setting
`ai.external_providers_allowed` (default off). Collectors must declare `terms_reviewed`; none ships.

**D-017 (2026-10-19) Client companies = one data folder per company.** `config/workspaces.py` keeps the list in
`<base>/workspaces.json` (atomic write). The first company ("principal") is the existing data folder, so old
installations open unchanged; new companies live in `<base>/empresas/<slug>/` with their own database, images,
files, backups, logs and Edge profiles (marketplace sessions never cross companies). Switching happens in-process
(`app.CompanySession`): stop the executor, open the new context, replace the window, close the old context; on
failure the current company stays open. No company deletion in the UI (user data). Known limitation: the license
trial is stored per database (licensing is still a placeholder, D-011). No shared database with a company column:
isolation by folder is simpler to audit, back up and hand over to a client.

**D-018 (2026-10-19) Change history + bulk edit.** Every `CatalogService.save` records field-level differences in
`product_changes` (migration 0008) inside the same transaction, with the origin ("Edição manual", "Importação #N",
"Edição em lote", "Duplicado de X"). Values are stored as the user reads them (R$, labels), long texts up to 2,000
characters; rows survive product deletion (product_id NULL, SKU kept). Bulk edit only touches descriptive fields
(categoria, subcategoria, marca, fornecedor, unidade, garantia, condição, status comercial); price, stock, GTIN and
SKU are never changed in bulk. It always shows a preview first and writes all-or-nothing in one transaction.
