# Project context

**What:** MLA (Marketplace Listing Automation) — Windows desktop app to register products once and prepare listings
on Mercado Livre, Shopee and later others, with a human review before every publication.
**For whom:** individual sellers, small shops, agencies; non-programmers. Sold later as Starter/Professional/Business.
**Owner:** solo developer (PT-BR). Machine: Ryzen 5 7520U, 8 GB RAM (5.7 visible), no dedicated GPU.

## Stack
Python 3.13 · PySide6 6.12 (UI) · Playwright 1.63 (automation, drives system Microsoft Edge) · SQLite (WAL) ·
pytest 9 + pytest-qt 4.5 · PyInstaller 6.22 (folder build). No web frontend.

## Scope boundaries
- Real marketplace forms are integrated only after inspecting them with an authorized account (phases 4 and 6).
- No automatic publishing without approval; no CAPTCHA/login bypass; no reading the user's personal browser.
- No real billing in the MVP; licensing module exists but never blocks features (enforce=False).

## Where things are
- Code: `src/mla/` — see ARCHITECTURE.md. Tests: `tests/` (unit, automation, ui).
- Dev tools: `tools/` (logscan, ollama_assist, skills_catalog, ui_snapshots, make_icon).
- Claude Code: `CLAUDE.md`, `.claude/skills/` (active), `tools/skills-catalog/` (dormant), `.mcp.json`.
- Tooling inventory: `docs/TOOLS_INVENTORY.md`.
