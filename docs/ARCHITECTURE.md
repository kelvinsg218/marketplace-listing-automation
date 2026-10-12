# Architecture

```
ui (PySide6)  ──navigate/refresh──▶ pages ──▶ services ──▶ persistence (SQLite)
   │                                  ▲            ▲
   └── ExecutionBridge (Qt signals) ◀─┤            │
                                      automation (worker thread, Playwright) ──▶ adapters ──▶ Edge
```

## Packages (`src/mla/`)
| Package | Responsibility | Key names |
|---|---|---|
| `config/` | data paths (`%LOCALAPPDATA%\MLA`, `MLA_DATA_DIR`), logging, bundled resources | `AppPaths`, `resource_path` |
| `core/` | enums, dataclasses, money/measure units, validation rules | `Product`, `ListingStatus`, `validate_product`, `MARKETPLACE_RULES` |
| `persistence/` | thread-local SQLite connections, migrations (`migrations/NNNN_*.sql`), backups, repositories | `Database`, `migrate`, `ProductRepository`, `AutomationRepository` |
| `services/` | business rules + composition root | `AppContext`, `CatalogService`, `GroupService`, `ImportExportService`, `ImageStore`, `DashboardService`, `SettingsService` |
| `automation/` | queue, executor, browser profiles, adapters, logging, form check | `QueueManager`, `ExecutionManager`, `BrowserSessionManager`, `BaseMarketplaceAdapter`, `FormValidator`, `ExecutionLogger` |
| `licensing/` | installation id, trial, plans, feature flags (not enforced) | `LicenseManager`, `Plan`, `Feature` |
| `ui/` | theme tokens, icons, widgets, pages, main window, Qt bridge | `MainWindow`, `theme.T`, `PipelineRail` |
| `diagnostics.py` | `--self-test` (DB, resources, Edge+Playwright) | `run_self_test` |

## Data model (SQLite, migration 0001/0002)
products · product_images (content-addressed files in `images/`) · product_variants · product_marketplace_data ·
product_groups + group_products (ordered, many-to-many) · marketplace_accounts (one default per marketplace) ·
automation_jobs → automation_job_items (one per product × marketplace × account; keeps name/SKU snapshot, survives
product deletion) · listings (current state per product × marketplace × account, UNIQUE) · execution_logs
(+ screenshots in `artifacts/`) · application_settings · license_state.
Money = integer cents, weight = grams, dimensions = millimetres.

## Execution flow (one item at a time)
`QueueManager.enqueue` validates, refuses non-integrated marketplaces and duplicates (published or already queued),
creates job + items. `ExecutionManager` (daemon thread) picks the next queued item of a pending/running job:
validate → duplicates → open dedicated profile → login (manual if needed) → open form → category, attributes,
title, images, description, price, stock, logistics (each with explicit waits + controlled retries) → read back +
`FormValidator` → screenshot → **AWAITING_REVIEW, waits for the user** → publish (step persisted before the click)
→ confirm (proof or `AmbiguousStateError` → NEEDS_ATTENTION). Cancel is ignored after the publish click.
Restart recovery: running items → back to queue, except those in publish/confirm → NEEDS_ATTENTION; running jobs → paused.

## Adapters
`SimulatedMarketplaceAdapter` drives `resources/mock_marketplace/*.html` (login, CAPTCHA hook, delayed attributes,
upload, confirmation). `MercadoLivreAdapter`/`ShopeeAdapter` extend `PendingIntegrationAdapter`
(`implemented=False`, every step raises `NotSupportedYet`) until phases 4/6.
