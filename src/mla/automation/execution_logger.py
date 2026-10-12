from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mla.core.models import ExecutionLog, JobItem
from mla.persistence.repositories import AutomationRepository

if TYPE_CHECKING:
    from playwright.sync_api import Page

log = logging.getLogger("mla.automation")


class ExecutionLogger:
    """Writes per-item execution logs to the database and diagnostic screenshots to disk."""

    def __init__(self, repo: AutomationRepository, item: JobItem, artifacts_dir: Path,
                 on_entry: Callable[[ExecutionLog], None] | None = None):
        self.repo = repo
        self.item = item
        self.artifacts_dir = artifacts_dir
        self.on_entry = on_entry
        self.step = ""

    def _write(self, level: str, message: str, details: dict[str, Any] | None = None, screenshot: str = "") -> None:
        entry = ExecutionLog(level=level, message=message, step=self.step, job_id=self.item.job_id,
                             item_id=self.item.id, product_id=self.item.product_id,
                             marketplace=self.item.marketplace.value, details=details or {}, screenshot=screenshot)
        self.repo.add_log(entry)
        log.log(getattr(logging, level, logging.INFO), "item=%s step=%s %s", self.item.id, self.step, message)
        if self.on_entry:
            self.on_entry(entry)

    def info(self, message: str, **details: Any) -> None:
        self._write("INFO", message, details)

    def warning(self, message: str, **details: Any) -> None:
        self._write("WARNING", message, details)

    def error(self, message: str, **details: Any) -> None:
        self._write("ERROR", message, details)

    def screenshot(self, page: "Page | None", label: str, level: str = "INFO", message: str = "") -> str:
        if page is None:
            return ""
        folder = self.artifacts_dir / f"item-{self.item.id}"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{datetime.now():%H%M%S}-{label}.png"
        try:
            page.screenshot(path=str(folder / name), full_page=True, timeout=10_000)
        except Exception as exc:  # screenshots are best effort
            log.warning("falha ao capturar tela: %s", exc)
            return ""
        relative = f"{folder.name}/{name}"
        self._write(level, message or f"Captura de tela: {label}", screenshot=relative)
        return relative
