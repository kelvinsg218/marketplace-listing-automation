# Current status — 2026-10-12, v0.1.0

**Phases 0–3 complete.** Tests: 71 passed in 63 s (66 fast + 5 browser/E2E incl. 1 live UI flow); pyflakes clean.
Build: `dist\MLA\MLA.exe` (219 MB folder, not in git — rebuild with `pyinstaller mla.spec`); `--self-test` passed.

| Phase | Status |
|---|---|
| 0 Environment | Done (skills, MCP config, Ollama benchmark — see DECISIONS.md) |
| 1 Foundation | Done, tested: SQLite migrations, backups, logging, settings, 8-page UI |
| 2 Catalog | Done, tested: products, images, variants, validation, groups, CSV/JSON, search/filter/sort |
| 3 Automation | Done, tested on the simulated marketplace: queue, Run, human review, retries, manual login/CAPTCHA pause, crash recovery, duplicate prevention, history |
| 4 Mercado Livre / 6 Shopee | **Pending real integration** (adapters refuse to run; needs authorized account to inspect forms) |
| 5 Batches | Mostly done (sequential queue, pause/resume/cancel); reports = history CSV |
| 7 Distribution | Folder build + self-test OK; no installer, no clean-machine test |
| 8 Commercial | Licensing/flags module, not enforced; placeholder keys |

## Known limitations
- Marketplace limits in `MARKETPLACE_RULES` unconfirmed (D-009).
- Manual edits made in the browser during review are not re-read before publishing.
- Pause takes effect after the current item. No workspaces/multi-catalog. Placeholder licence keys (D-011).
- Chrome DevTools MCP configured but pending approval in an interactive `claude` session.
- UI has not yet been reviewed by the owner; first hands-on test happening now.
