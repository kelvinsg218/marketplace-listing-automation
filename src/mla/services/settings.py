from __future__ import annotations

from typing import Any

from mla.persistence.repositories import SettingsRepository

DEFAULTS: dict[str, Any] = {
    "browser.channel": "msedge",          # msedge (built into Windows) | chrome | chromium
    "automation.step_timeout_s": 30,
    "automation.max_retries": 2,
    "automation.screenshot_on_failure": True,
    "backup.auto_on_start": True,
    "backup.keep": 15,
}

BROWSER_CHANNELS = {"msedge": "Microsoft Edge (recomendado)", "chrome": "Google Chrome",
                    "chromium": "Chromium do Playwright"}


class SettingsService:
    def __init__(self, repo: SettingsRepository):
        self.repo = repo

    def get(self, key: str) -> Any:
        return self.repo.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(f"Configuração desconhecida: {key}")
        expected = type(DEFAULTS[key])
        if not isinstance(value, expected):
            raise TypeError(f"{key} espera {expected.__name__}")
        if key == "browser.channel" and value not in BROWSER_CHANNELS:
            raise ValueError(f"Navegador inválido: {value}")
        self.repo.set(key, value)

    def all(self) -> dict[str, Any]:
        stored = self.repo.all()
        return {key: stored.get(key, default) for key, default in DEFAULTS.items()}
