"""Mercado Livre official API in the UI: account connection (OAuth), listing tools and import of existing listings.

Nothing here publishes: validation uses POST /items/validate, which never creates a listing.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLineEdit, QMenu, QPlainTextEdit, QVBoxLayout, QWidget,
)

from mla.integrations.mercadolivre import MLApiError, MLCancelled, MLNotConnected
from mla.ui.widgets.common import Callout, button, inform, label
from mla.ui.workers import TaskRunner

DEVCENTER = "https://developers.mercadolivre.com.br/devcenter"


# ============================================================================ connection dialog
class MLConnectDialog(QDialog):
    """Connect one Mercado Livre account through the official OAuth flow (the user's own app credentials)."""

    def __init__(self, ctx, account, parent=None):
        super().__init__(parent)
        self.ctx, self.account = ctx, account
        self.service = ctx.mercadolivre
        self.result_connection = None
        self.setWindowTitle(f"Conectar {account.label} à API oficial do Mercado Livre")
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(label("Conectar pela API oficial", object_name="sectionTitle"))
        layout.addWidget(label(
            "1. No portal de desenvolvedores do Mercado Livre, crie um aplicativo (gratuito) com a sua conta, "
            "ative PKCE e cadastre uma URI de redirecionamento HTTPS.\n"
            "2. Copie aqui o App ID, a Secret Key e a mesma URI.\n"
            "3. Abra a autorização, entre na sua conta e autorize. O navegador vai para a URI cadastrada com "
            "code=… no endereço: copie o endereço inteiro e cole abaixo.\n"
            "O MLA nunca pede nem guarda a sua senha do Mercado Livre. Os códigos ficam criptografados para o seu "
            "usuário do Windows.", role="muted", wrap=True))
        portal = button("Abrir portal de desenvolvedores", "ghost", "external-link",
                        lambda: QDesktopServices.openUrl(QUrl(DEVCENTER)))
        row = QHBoxLayout()
        row.addWidget(portal)
        row.addStretch(1)
        layout.addLayout(row)
        form = QFormLayout()
        current = self.service.connection(account.id)
        self.client_id = QLineEdit(current.client_id if current else "")
        self.client_id.setPlaceholderText("Número do App ID (client_id)")
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText("Secret Key do aplicativo (não é a sua senha)")
        self.redirect = QLineEdit(current.redirect_uri if current else "")
        self.redirect.setPlaceholderText("https://… exatamente como cadastrada no aplicativo")
        form.addRow("App ID", self.client_id)
        form.addRow("Secret Key", self.secret)
        form.addRow("URI de redirecionamento", self.redirect)
        layout.addLayout(form)
        self.open_btn = button("Abrir autorização no navegador", "secondary", "log-in", self._open)
        layout.addWidget(self.open_btn)
        self.pasted = QLineEdit()
        self.pasted.setPlaceholderText("Cole aqui o endereço final (com code=…)")
        self.pasted.setEnabled(False)
        layout.addWidget(self.pasted)
        self.note = Callout()
        self.note.setVisible(False)
        layout.addWidget(self.note)
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(button("Fechar", "ghost", None, self.reject))
        self.finish_btn = button("Concluir conexão", "primary", "check", self._finish)
        self.finish_btn.setEnabled(False)
        foot.addWidget(self.finish_btn)
        layout.addLayout(foot)
        self.runner = TaskRunner(self)
        self.runner.finished.connect(self._done)
        self.runner.failed.connect(self._failed)

    def _open(self) -> None:
        try:
            url = self.service.start_connect(self.account.id, self.client_id.text(), self.secret.text(),
                                             self.redirect.text())
        except MLApiError as exc:
            self.note.set_text(str(exc))
            return
        QDesktopServices.openUrl(QUrl(url))
        self.pasted.setEnabled(True)
        self.finish_btn.setEnabled(True)
        self.pasted.setFocus()
        self.note.set_text("Autorize no navegador e cole aqui o endereço final.")

    def _finish(self) -> None:
        text = self.pasted.text()
        self.finish_btn.setEnabled(False)
        self.note.set_text("Conectando…")
        self.runner.start(lambda _p, _c: self.service.finish_connect(self.account.id, text))

    def _done(self, connection) -> None:
        self.result_connection = connection
        inform(self, "Conta conectada", f"Conectada à API oficial como {connection.nickname} "
                                        f"(usuário {connection.remote_user_id}).")
        self.accept()

    def _failed(self, message: str) -> None:
        self.finish_btn.setEnabled(True)
        self.note.set_text(f"Não foi possível conectar: {message}")


def connection_text(ctx, account) -> str:
    connection = ctx.mercadolivre.connection(account.id) if ctx.mercadolivre else None
    if connection is None:
        return "API oficial: não conectada"
    if connection.last_error:
        return f"API oficial: {connection.last_error}"
    return f"API oficial: conectada como {connection.nickname or connection.remote_user_id}"


# ============================================================================ listing editor tools
class MLListingTools(QWidget):
    """Category suggestion, required attributes and validation WITHOUT publishing, inside the listing editor."""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.service = editor.ctx.mercadolivre
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(label("Mercado Livre (API oficial)", object_name="sectionTitle"))
        self.status = label(connection_text(editor.ctx, editor.ctx.accounts.get(editor.listing.account_id)),
                            role="hint", wrap=True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.suggest_btn = button("Sugerir categoria", "ghost", "search", self._suggest)
        self.attrs_btn = button("Atributos", "ghost", "list-checks", self._attributes)
        row.addWidget(self.suggest_btn)
        row.addWidget(self.attrs_btn)
        layout.addLayout(row)
        self.validate_btn = button("Validar no Mercado Livre (sem publicar)", "secondary", "badge-check",
                                   self._validate)
        layout.addWidget(self.validate_btn)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(150)
        self.output.setVisible(False)
        layout.addWidget(self.output)
        self.runner = TaskRunner(self)
        self.runner.finished.connect(self._done)
        self.runner.failed.connect(self._failed)
        self._task = ""
        self._suggestions: list[dict] = []

    def _busy(self, task: str, text: str) -> None:
        self._task = task
        for b in (self.suggest_btn, self.attrs_btn, self.validate_btn):
            b.setEnabled(False)
        self._show(text)

    def _show(self, text: str) -> None:
        self.output.setPlainText(text)
        self.output.setVisible(True)

    def _current(self):
        listing, problem = self.editor.collect()
        return listing, problem, self.editor.ctx.listings.payload(listing, self.editor.product)

    def _suggest(self) -> None:
        _, _, payload = self._current()
        self._busy("suggest", "Consultando o preditor de categorias do Mercado Livre…")
        self.runner.start(lambda _p, _c: self.service.suggest_categories(payload.title))

    def _attributes(self) -> None:
        _, _, payload = self._current()
        category = payload.category_id
        self._busy("attrs", f"Lendo os atributos da categoria {category}…")
        self.runner.start(lambda _p, _c: (category, self.service.required(self.service.category_attributes(category))))

    def _validate(self) -> None:
        listing, problem, payload = self._current()
        if problem:
            self._show(problem)
            return
        product = self.editor.product
        self._busy("validate", "Validando no Mercado Livre (nada é publicado)…")
        self.runner.start(lambda _p, _c: self.service.validate_listing(listing.account_id, product, payload))

    def _failed(self, message: str) -> None:
        self._enable()
        self._show(f"Não foi possível concluir: {message}")

    def _enable(self) -> None:
        for b in (self.suggest_btn, self.attrs_btn, self.validate_btn):
            b.setEnabled(self.editor.editable or b is self.validate_btn)

    def _done(self, result) -> None:
        task, self._task = self._task, ""
        self._enable()
        if task == "suggest":
            if not result:
                self._show("O Mercado Livre não sugeriu categorias para este título.")
                return
            self._show("\n".join(f"{r['category_id']} — {r['category_name']} ({r['domain_name']})" for r in result)
                       + "\n\nClique em uma sugestão no menu para usá-la.")
            menu = QMenu(self)
            for r in result:
                menu.addAction(f"{r['category_id']} — {r['category_name']}",
                               lambda _c=False, cid=r["category_id"]: self.editor.category_id.setText(cid))
            menu.popup(self.suggest_btn.mapToGlobal(QPoint(0, self.suggest_btn.height())))
        elif task == "attrs":
            category, required = result
            existing = {self.editor.attributes.item(r, 0).text().strip().lower()
                        for r in range(self.editor.attributes.rowCount()) if self.editor.attributes.item(r, 0)}
            lines, added = [], 0
            for attr in required:
                lines.append(f"{attr['_kind']}: {attr.get('name')} ({attr['id']})")
                if attr["_kind"] == "obrigatório" and attr["id"] not in ("BRAND", "MODEL", "GTIN", "SELLER_SKU") \
                        and attr.get("name", "").lower() not in existing and self.editor.editable:
                    self.editor._add_attribute(attr.get("name", attr["id"]), "")
                    added += 1
            text = f"Categoria {category}: {len(required)} atributo(s) obrigatório(s) ou condicional(is).\n"
            text += "\n".join(lines)
            if added:
                text += f"\n\n{added} linha(s) adicionada(s) à tabela de atributos: preencha os valores (nada é inventado)."
            self._show(text)
        elif task == "validate":
            head = ("VÁLIDO: o Mercado Livre aceitaria este anúncio (nada foi publicado)." if result.valid else
                    "NÃO VÁLIDO: o Mercado Livre apontou problemas (nada foi publicado).")
            lines = [head]
            lines += [f"[{'erro' if s == 'error' else 'aviso'}] {m}" for s, m in result.problems]
            if result.local:
                lines.append("\nObservações do MLA:")
                lines += [f"- {m}" for _s, m in result.local]
            self._show("\n".join(lines))


# ============================================================================ import of existing listings
def import_ml_listings(page, account) -> None:
    """Fetch the account's listings (read-only) into a JSON file and open the import wizard on it."""
    from datetime import datetime

    from mla.ui.pages.imports import ImportWizard
    from mla.ui.widgets.common import confirm
    ctx = page.ctx
    if ctx.mercadolivre.connection(account.id) is None:
        inform(page, "Importar do Mercado Livre", "Conecte a conta à API oficial em Marketplaces primeiro.")
        return
    if not confirm(page, "Importar do Mercado Livre", f"Ler os anúncios da conta {account.label} (até 1.000) e abrir "
                   "a revisão da importação? Nada é alterado no Mercado Livre e nada é gravado no catálogo antes "
                   "da sua confirmação.", "Ler anúncios"):
        return
    folder = Path(ctx.paths.imports) / f"mercadolivre-{datetime.now():%Y%m%d-%H%M%S}"
    runner = TaskRunner(page, cancelled_types=(MLCancelled,))
    page._ml_runner = runner  # keep alive

    def finished(path):
        wizard = ImportWizard(ctx, page, path=Path(path))
        wizard.exec()
        page.refresh()

    def failed(message):
        prefix = "Conecte a conta de novo. " if "conect" in message.lower() else ""
        inform(page, "Importar do Mercado Livre", f"{prefix}{message}", error=True)

    runner.finished.connect(finished)
    runner.failed.connect(failed)
    runner.start(lambda progress, cancel: ctx.mercadolivre.export_seller_listings(account.id, folder, progress,
                                                                                   cancel))


__all__ = ["MLConnectDialog", "MLListingTools", "connection_text", "import_ml_listings", "MLNotConnected"]
