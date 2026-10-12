"""Composition root: opens the database and wires repositories and services."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from mla.config.paths import AppPaths
from mla.licensing.license import LicenseManager
from mla.persistence.backup import create_backup
from mla.persistence.db import Database
from mla.persistence.migrator import migrate
from mla.persistence.repositories import (
    AccountRepository, AutomationRepository, GroupRepository, ProductRepository, SettingsRepository,
)
from mla.services.catalog import CatalogService
from mla.services.dashboard import DashboardService
from mla.services.groups import GroupService
from mla.services.images import ImageStore
from mla.services.import_export import ImportExportService
from mla.services.settings import SettingsService

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

    @classmethod
    def open(cls, paths: AppPaths | None = None, startup_backup: bool = False) -> "AppContext":
        paths = (paths or AppPaths.default()).ensure()
        db = Database(paths.database)
        applied = migrate(db, backup_dir=paths.backups)
        if applied:
            log.info("banco em %s migrado para v%s", paths.database, applied[-1])
        products = ProductRepository(db)
        images = ImageStore(paths.images)
        catalog = CatalogService(products, images)
        automation_repo = AutomationRepository(db)
        settings = SettingsService(SettingsRepository(db))
        ctx = cls(
            paths=paths, db=db, products=products, accounts=AccountRepository(db),
            automation_repo=automation_repo, images=images, catalog=catalog,
            groups=GroupService(GroupRepository(db), products),
            import_export=ImportExportService(catalog, images),
            dashboard=DashboardService(products, automation_repo),
            settings=settings, license=LicenseManager(db),
        )
        if startup_backup and not applied and settings.get("backup.auto_on_start"):
            create_backup(db, paths.backups, reason="inicio", keep=int(settings.get("backup.keep")))
        return ctx

    def close(self) -> None:
        self.db.close()
