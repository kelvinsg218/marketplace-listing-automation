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
| `core/` | enums, dataclasses, money/measure units, validation rules, marketplace site facts | `Product`, `Listing`, `ListingStatus`, `validate_product`, `CategoryRule`, `MARKETPLACE_RULES`, `SITES` |
| `persistence/` | thread-local SQLite connections, migrations (`migrations/NNNN_*.sql`), backups, repositories | `Database`, `migrate`, `ProductRepository`, `AutomationRepository` |
| `services/` | business rules + composition root | `AppContext`, `CatalogService`, `GroupService`, `ImageStore`, `FileStore`, `CompatibilityService`, `ListingService`, `AccountService`, `MarketService`, `ListingQualityService`, `SuggestionService`, `DashboardService`, `SettingsService`, `ImportExportService` (legacy export/import) |
| `importing/` | import center: readers (CSV/XLSX/JSON/XML/PDF), safe ZIP extraction, column mapping, value parsing, plan/commit | `ImportService`, `Analysis`, `open_source`, `extract_archive`, `suggest_mapping` |
| `automation/` | queue, executor, browser profiles, adapters, logging, form check, connection test | `QueueManager`, `ExecutionManager`, `BrowserSessionManager`, `BaseMarketplaceAdapter`, `FormValidator`, `ExecutionLogger`, `ConnectionTester` |
| `licensing/` | installation id, trial, plans, feature flags (not enforced) | `LicenseManager`, `Plan`, `Feature` |
| `ui/` | theme tokens, icons, widgets, pages, main window, Qt bridge | `MainWindow`, `theme.T`, `PipelineRail` |
| `diagnostics.py` | `--self-test` (DB, resources, Edge+Playwright) | `run_self_test` |

## Data model (SQLite, migrations 0001–0007)
products · product_images (content-addressed files in `images/`) · product_variants · product_marketplace_data ·
product_groups + group_products (ordered, many-to-many) · marketplace_accounts (one default per marketplace) ·
automation_jobs → automation_job_items (one per product × marketplace × account; keeps name/SKU snapshot, survives
product deletion) · listings (current state per product × marketplace × account, UNIQUE) · execution_logs
(+ screenshots in `artifacts/`) · application_settings · license_state.
0003: account seller URL, internal id, default flag, last connection check.
0004: master catalog columns on products (all optional) · product_files (`files/`, content-addressed) ·
product_missing_media · product_compatibilities (source + verification) · image variant/original name.
0005: import_batches (history) · import_rows (planned rows = preview + report) · import_templates.
0006: listings rebuilt = offers with overrides (title, description, price, stock, category, type, attributes,
images, notes, approval fingerprint) and the full lifecycle status.
0007: market_references · market_observations (source + date) · ai_suggestions.
Money = integer cents, weight = grams, dimensions = millimetres.

## Import flow
`ImportService.analyze` (detect format, ZIP → `imports/<staging>`, preview, synonym mapping/template) →
`plan` on a worker thread (rows parsed in chunks of 500, duplicates, field diff vs catalog, media resolved,
written to `import_rows`) → user decisions (create/update/ignore, review rows opt-in) → `commit` (media copied
first, then ONE transaction with a savepoint per row; cancel = rollback) → report. Startup recovery: a plan in
progress becomes failed; a commit in progress (rolled back by SQLite) becomes planned again.

## Listing preparation
Catalog → "Preparar anúncios" (marketplace + account) → `ListingService.prepare` creates listings with no
overrides → editor stores overrides → state derived from `build_payload(product, marketplace, images, listing)`
validation → approve (fingerprint) → `QueueManager.enqueue_listings` (approved only; adapters not implemented
are refused) → executor validates/sends the same effective payload.

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
