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
