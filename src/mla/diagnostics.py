"""Self-test for support and release checks: `MLA.exe --self-test` (or `python -m mla --self-test`).

Writes a plain-text report to <data>/logs/self-test.txt and returns 0 when every check passes.
"""
from __future__ import annotations

import platform
import sys
import time
from collections.abc import Callable

from mla import __version__
from mla.config.paths import AppPaths, resource_path


def _check_database(paths: AppPaths) -> str:
    from mla.services.context import AppContext
    ctx = AppContext.open(paths)
    try:
        version = ctx.db.scalar("SELECT MAX(version) FROM schema_migrations")
        products = ctx.db.scalar("SELECT COUNT(*) FROM products")
        integrity = ctx.db.scalar("PRAGMA integrity_check")
    finally:
        ctx.close()
    if integrity != "ok":
        raise RuntimeError(f"integridade: {integrity}")
    return f"schema v{version}, {products} produto(s), integridade ok"


def _check_resources(_paths: AppPaths) -> str:
    required = ["fonts/Manrope.ttf", "icons/package.svg", "mock_marketplace/sell.html", "app.ico"]
    missing = [r for r in required if not resource_path(*r.split("/")).exists()]
    if missing:
        raise RuntimeError(f"recursos ausentes: {missing}")
    return f"{len(required)} recursos encontrados"


def _check_browser(paths: AppPaths) -> str:
    from playwright.sync_api import sync_playwright

    from mla.services.settings import DEFAULTS
    channel = DEFAULTS["browser.channel"]
    started = time.perf_counter()
    with sync_playwright() as pw:
        kwargs = {"headless": True}
        if channel != "chromium":
            kwargs["channel"] = channel
        browser = pw.chromium.launch(**kwargs)
        try:
            page = browser.new_page()
            page.goto(resource_path("mock_marketplace").as_uri() + "/login.html")
            page.locator("#login-form").wait_for(state="visible", timeout=15_000)
            version = browser.version
        finally:
            browser.close()
    return f"{channel} {version} abriu o marketplace simulado em {time.perf_counter() - started:.1f}s"


CHECKS: list[tuple[str, Callable[[AppPaths], str]]] = [
    ("Banco de dados", _check_database),
    ("Recursos do aplicativo", _check_resources),
    ("Navegador e automação", _check_browser),
]


def run_self_test(paths: AppPaths | None = None) -> tuple[bool, str]:
    paths = (paths or AppPaths.default()).ensure()
    lines = [f"MLA {__version__} | Python {platform.python_version()} | {platform.platform()}",
             f"Executável congelado: {bool(getattr(sys, 'frozen', False))} | Dados: {paths.root}", ""]
    ok = True
    for name, check in CHECKS:
        try:
            lines.append(f"[OK]    {name}: {check(paths)}")
        except Exception as exc:  # report every failure, keep going
            ok = False
            lines.append(f"[FALHA] {name}: {exc.__class__.__name__}: {str(exc).splitlines()[0][:300]}")
    report = "\n".join(lines)
    target = paths.logs / "self-test.txt"
    target.write_text(report + "\n", encoding="utf-8")
    return ok, report


def main() -> int:
    ok, report = run_self_test()
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            print(report)
        except (AttributeError, OSError):
            pass
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

