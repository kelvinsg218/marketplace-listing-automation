# Next steps

## Priority 1 — owner's feedback (next session starts here)
The owner is testing the app (dashboard, product form, photos, descriptions, groups, Run, simulated marketplace,
history, navigation/performance). Collect the feedback list, triage into bugs / visual / UX / features, fix in that
order with tests and `tools/ui_snapshots.py` review. Do not start phase 4 before this.

## Then
- Approve `chrome-devtools` MCP when `claude` asks.
- Phase 4 (Mercado Livre) only with authorization: log in via Marketplaces → "Abrir navegador para login", inspect
  (not publish) the real form, implement `MercadoLivreAdapter`, local fixture, review-gated first run.
- Re-read the form after manual edits before publishing; Settings → "Executar diagnóstico" button.
- Installer + clean-machine test; reports page; signed licence keys (D-011). Phase 6 (Shopee) after phase 4.
