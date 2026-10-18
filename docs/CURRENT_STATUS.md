# Current status — 2026-10-18, v0.1.0 + phase 9 (committed 371e0f8)

**Phases 0–3 complete; phase 9 (master catalog, import center, compatibility, listing preparation, accounts)
implemented and tested locally.** Committed and pushed in 371e0f8; showcase (README + docs/showcase) updated.
Tests: 178 passed (169 fast + 9 browser/E2E in headless Edge); pyflakes clean.
Fixed the crash found in the owner's first test (log 2026-10-13: Marketplaces "Adicionar conta" received Qt's
`clicked(bool)` instead of the marketplace); same pattern fixed in the catalog "Adicionar ao grupo" menu.
DB schema v7 (migrations 0003–0007 added; additive except `listings`, rebuilt with every row copied).
Migration v2→v7 checked on a copy of the owner's real DB: accounts/settings kept, backup created, integrity ok.

| Area | Status |
|---|---|
| Master catalog | Done, tested: GTIN (check digit), manufacturer code, supplier, cost/promo price, min stock, unit, commercial status, technical description, color, specs, custom attributes, manufacturer refs, internal notes, original description, source; technical files; pending (missing) media; images can carry a variation name. Optional fields only; category rules opt-in (setting `catalog.category_rules`, no UI yet) |
| Import center | Done, tested: CSV (UTF-8/ANSI, `;` `,` tab `|`), XLSX (first sheet with data or chosen sheet), JSON (nested, MLA export with variations), XML (DOCTYPE refused), PDF (aligned table = safe, misaligned/ficha técnica = review), ZIP (safe extraction), image folder by SKU. Synonym mapping with "probable → confirm", templates, per-row validation, duplicates, field-level diff, create/update/ignore decisions, one-transaction commit (cancel = nothing written), report CSV, history, recovery after restart |
| Compatibility | Done, tested: brand/model/version/years/reference/notes/source/verification, dedup, bulk import, page + product tab |
| Listings (offers) | Done, tested: one listing per product × marketplace × account with overrides only; states draft → incomplete → ready for review → approved → queued → running → published confirmed / failed / needs attention; approval revoked if content changes; only approved go to the queue; executor validates and sends the effective content |
| Accounts | Done, tested: add/edit/delete, default, active, validated seller URL (allow-listed domains), dedicated Edge profile per account, connection test (manual login, "Não verificada" when the marketplace check is not mapped) |
| Mercado Livre real test (phase 7 of the brief) | **Blocked: needs the owner's authorization + seller URL.** No real account was opened |
| Market intelligence / AI | Groundwork only: reference URLs + dated observations, collector contract gated by `terms_reviewed`, deterministic completeness score (shown in the listing editor), AI suggestion storage applied only when accepted, external providers blocked unless `ai.external_providers_allowed` |
| Distribution | `mla.spec` not re-validated with openpyxl/pypdf; rebuild + `--self-test` pending |

## Known limitations (honest)
- Marketplace limits in `MARKETPLACE_RULES` still unconfirmed (D-009); ML/Shopee adapters still refuse to run.
- XLSX pictures embedded in cells are not extracted; image URLs in a base are recorded as pending, not downloaded.
- PDF: text PDFs only (no OCR); wrapped cell text in PDF tables is not joined.
- Legacy `ImportExportService.import_csv/json` still rebuild text fields from the row (now keeps images);
  the UI no longer uses it — the import center replaced it.
- One listing per product per account (ML "clássico + premium" of the same product not supported yet).
- No UI yet for: category rules, AI consent switch, market references, assigning an image to a variation.
- UI phase 9 reviewed only through `tools/ui_snapshots.py`; owner has not used it yet.
