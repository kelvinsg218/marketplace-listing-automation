# Testing

```powershell
.venv\Scripts\python -m pytest                    # everything (~1-2 min)
.venv\Scripts\python -m pytest -m "not browser"   # fast, no browser
.venv\Scripts\python -m pytest -m browser         # E2E with headless Microsoft Edge
```
Each test uses a temporary data folder (`MLA_DATA_DIR` never points at real data).

| Folder | Covers |
|---|---|
| `tests/unit` | units/money, migrations (failure rollback, pre-migration backup), transactions, backup/restore/prune, catalog CRUD + status + SKU uniqueness, duplicate, delete cascade + orphan images, search/filter/sort, image import/headers, validation rules, groups, CSV/JSON round-trips and bad rows, licence trial/activation/flags, settings |
| `tests/automation` | queue (one item per target, skip reasons, duplicates, group order, pause/resume/cancel, restart recovery, requeue, history after deletion), payload, form comparison; **browser**: full login → fill → review → publish, reject, CAPTCHA manual step, missing required attribute |
| `tests/ui` | every page opens, dashboard real data, editor create/validate/bad price, products filters, run → queue report, review panel decisions; **browser**: live flow through the UI with the real executor |

## Rules
- No test publishes to a real marketplace. Real-site checks happen only with explicit authorization (phase 4/6).
- Browser tests use `SimulatedMarketplaceAdapter` and the bundled `resources/mock_marketplace` pages.
- Release check: build with PyInstaller and run `dist\MLA\MLA.exe --self-test` (DB, resources, Edge automation).
