# Changelog

## 0.1.0 — 2026-10-12
First working build (phases 0–3, parts of 5, 7 and 8).
- Development environment: curated Claude Code skills, Chrome DevTools MCP config, Ollama benchmark, token-economy
  workflow and tools (logscan, skills catalog, UI snapshots).
- App foundation: SQLite with migrations, backups, logging, settings, dark PySide6 UI with 8 sections.
- Catalog: products with images, variants, logistics and per-marketplace data; validation; groups; CSV/JSON.
- Automation: persistent queue, sequential executor with human review, retries, manual-action pauses, crash
  recovery, duplicate prevention, screenshots; simulated marketplace adapter. ML/Shopee adapters pending.
- Licensing module (trial, plans, feature flags; not enforced). PyInstaller folder build with `--self-test`.
