# Commercial roadmap

## Plans (feature flags in `licensing/features.py`, not enforced yet)
| | Starter | Professional | Business |
|---|---|---|---|
| Catalog, single run, basic history | ✓ | ✓ | ✓ |
| Mercado Livre | ✓ | ✓ | ✓ |
| Shopee, groups, batch, import/export, reports | | ✓ | ✓ |
| Multiple accounts, catalogs, workspaces, agency features | | | ✓ |

Trial: 30 days, all features. MVP: nothing is blocked.

## Before selling
1. Mercado Livre integration validated on real accounts (phase 4) — the product's core promise.
2. Signed licence keys (Ed25519, public key in the app) or a small licence server; offline grace period; no DRM.
3. Installer with code signing (SmartScreen), auto-update channel, clean uninstall with optional data removal.
4. Privacy/terms: data stays local; browser profiles never leave the machine; no credential storage by MLA.
5. Support kit: `--self-test` report, log folder shortcut, versioned backups.
6. Multi-catalog/workspaces (one SQLite file per workspace) for agencies.

## Risks
- Marketplace UI changes break adapters → selectors centralised per adapter, fixtures + quick patch releases.
- Platform policies on automation → human review before publishing, no bypass of verification, respectful pacing.
- Official APIs (e.g., Mercado Livre API) may be a more stable path than browser automation for some operations;
  evaluate in phase 4 with the user.
