# Next steps

## Now — owner review of phase 9 (next session starts here)
1. Owner tests the open app: Importações (CSV/XLSX/ZIP of the company base), Catálogo (filters, editor tabs
   Técnico/Compatibilidade), Compatibilidades, Anúncios (prepare, edit, approve), Marketplaces (add account + URL).
2. Collect feedback; triage bugs / visual / UX; fix with tests and `tools/ui_snapshots.py`.
3. Ask before committing phase 9 (suggested: one commit per area; no Co-Authored-By trailer).

## Blocked on the owner
- **Mercado Livre real inspection** (brief phase 7): owner registers the seller URL in Marketplaces, authorizes,
  logs in by hand in the dedicated Edge window; then map (read-only) the session check page, identity element and
  the path to "anunciar", fill `SITES[MERCADO_LIVRE]` in `core/sites.py` with what was observed, stop before any
  form filling. Never publish or edit real listings.

## Then
- Settings UI: category rules (`catalog.category_rules`), AI consent (`ai.external_providers_allowed`).
- Assign images to a variation in the editor (data model + import already support `ProductImage.variant`).
- Phase 4 (ML adapter) after the inspection: real category/attribute reading, review-gated first run.
- Rebuild with PyInstaller (check openpyxl/pypdf collected), `--self-test`, installer, clean-machine test.
- Market references UI (manual price observations) once the owner wants it; collectors only with reviewed terms.
