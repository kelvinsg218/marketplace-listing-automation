"""Composition root: opens the database and wires repositories and services."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mla.config.paths import AppPaths
from mla.licensing.license import LicenseManager
from mla.core.validation import CategoryRule
from mla.persistence.backup import create_backup
from mla.persistence.changes import ChangeRepository
from mla.persistence.compatibility import CompatibilityRepository
from mla.persistence.db import Database
from mla.persistence.listings import ListingRepository
from mla.persistence.migrator import migrate
from mla.persistence.repositories import (
    AccountRepository, AutomationRepository, GroupRepository, ProductRepository, SettingsRepository,
)
from mla.services.accounts import AccountService
from mla.services.catalog import CatalogService
from mla.services.compatibility import CompatibilityService
from mla.services.dashboard import DashboardService
from mla.services.files import FileStore
from mla.services.groups import GroupService
from mla.services.images import ImageStore
from mla.services.import_export import ImportExportService
from mla.services.listings import ListingService
from mla.services.market import MarketService
from mla.services.optimization import ListingQualityService, SuggestionService
from mla.services.settings import SettingsService

if TYPE_CHECKING:
    from mla.importing.service import ImportService
    from mla.integrations.mercadolivre import MercadoLivreService

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    paths: AppPaths
    db: Database
    products: ProductRepository
    accounts: AccountRepository
    automation_repo: AutomationRepository
    images: ImageStore
    catalog: CatalogService
    groups: GroupService
    import_export: ImportExportService
    dashboard: DashboardService
    settings: SettingsService
    license: LicenseManager
    account_service: AccountService
    files: FileStore
    compatibility: CompatibilityService
    listings: ListingService
    market: MarketService | None = None
    quality: ListingQualityService | None = None
    suggestions: SuggestionService | None = None
    imports: "ImportService | None" = None
    mercadolivre: "MercadoLivreService | None" = None
    recovered_imports: int = 0

    @classmethod
    def open(cls, paths: AppPaths | None = None, startup_backup: bool = False) -> "AppContext":
        paths = (paths or AppPaths.default()).ensure()
        db = Database(paths.database)
        applied = migrate(db, backup_dir=paths.backups)
        if applied:
            log.info("banco em %s migrado para v%s", paths.database, applied[-1])
        products = ProductRepository(db)
        images = ImageStore(paths.images)
        files = FileStore(paths.files)
        automation_repo = AutomationRepository(db)
        settings = SettingsService(SettingsRepository(db))
        accounts = AccountRepository(db)
        compat_repo = CompatibilityRepository(db)
        catalog = CatalogService(
            products, images, files,
            rules=lambda: [CategoryRule.from_dict(r) for r in settings.get("catalog.category_rules") or []],
            confirmed_compat=compat_repo.confirmed_count, changes=ChangeRepository(db))
        listings = ListingService(ListingRepository(db), products, accounts, catalog, images)
        catalog.after_save.append(listings.refresh_for_product)
        ctx = cls(
            paths=paths, db=db, products=products, accounts=accounts,
            automation_repo=automation_repo, images=images, catalog=catalog,
            groups=GroupService(GroupRepository(db), products),
            import_export=ImportExportService(catalog, images),
            dashboard=DashboardService(products, automation_repo),
            settings=settings, license=LicenseManager(db),
            account_service=AccountService(accounts, paths.browser_profiles),
            files=files, compatibility=CompatibilityService(compat_repo), listings=listings,
            market=MarketService(db), quality=ListingQualityService(listings, products, compat_repo.confirmed_count),
            suggestions=SuggestionService(db, listings, settings),
        )
        from mla.integrations.mercadolivre import MercadoLivreService
        ctx.mercadolivre = MercadoLivreService(db, accounts)
        from mla.importing.service import ImportService  # importing depends on the services above
        from mla.persistence.imports import ImportRepository
        ctx.imports = ImportService(ImportRepository(db), ctx)
        ctx.recovered_imports = ctx.imports.recover_interrupted()
        if startup_backup and not applied and settings.get("backup.auto_on_start"):
            create_backup(db, paths.backups, reason="inicio", keep=int(settings.get("backup.keep")))
        return ctx

    def close(self) -> None:
        self.db.close()
